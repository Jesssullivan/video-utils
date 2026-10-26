"""Per-chunk QA (docs/spec/NARRATE.md, "Dataflow" step 6).

WER: the take is read back through condense's whisper path (condense.transcribe.read: whisper-cli with the
registered model, or condense's loopback STT backend) and compared word by word with the chunk's spoken text.
Without whisper-cli or the model the status is not_measured, as condense's check.json says it, and no gate
judges the take. The model file is hashed once per path and must match a sha256 in program/models.json; an
unregistered or partial file leaves WER not_measured. The manifest records the model's digest and registry id, or
the loopback endpoint of the http backend. Numbers are compared as digits on both sides ("seven" and "7" are one
word), so whisper writing numerals is not an error. SIM: render does not score takes in v0; `narrate evaluate`
scores the delivered chunks with the registered speaker-verification model (narrate/sim.py).

A take that fails a measured gate is synthesised again with the next seed, at most maxTakes takes in all. The
best take by WER, then SIM, is kept; every take's numbers and the failure are recorded. A chunk that never
passes is flagged qa_failed, never silently accepted. WER is a regression gate, not a ranking.
"""

import json
import re
import shutil
import tempfile
import urllib.parse
from pathlib import Path

from .ir import sha256_file

PAD = 0.5  # seconds of silence around a take read back by whisper
MODELS = Path(__file__).resolve().parents[1] / "program" / "models.json"

UNITS = {
    w: n
    for n, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
        "seventeen eighteen nineteen".split()
    )
}
TENS = {w: 10 * n for n, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split(), 2)}
SCALES = {"thousand": 10**3, "million": 10**6, "billion": 10**9}


def numerals(tokens):
    """tokens with each spoken number made digits: "twenty one" -> "21", "two point five" -> "2.5",
    "one two three" -> "1 2 3" (a run joins only where English grammar does)."""
    out, i = [], 0
    while i < len(tokens):
        total, current, last, scale, j = 0, 0, None, None, i
        while j < len(tokens):
            t = tokens[j]
            n = UNITS.get(t)
            if n is not None and n < 10 and last in (None, "tens", "hundred", "scale", "and") and t != "zero":
                current, last = current + n, "unit"
            elif n is not None and last in (None, "hundred", "scale", "and") and (n >= 10 or t == "zero"):
                current, last = current + n, "teen" if n >= 10 else "zero"
            elif t in TENS and last in (None, "hundred", "scale", "and"):
                current, last = current + TENS[t], "tens"
            elif t == "hundred" and last in ("unit", "teen") and current < 100:
                current, last = current * 100, "hundred"
            elif t in SCALES and last in ("unit", "teen", "tens", "hundred") and (scale is None or SCALES[t] < scale):
                total, current, last, scale = total + current * SCALES[t], 0, "scale", SCALES[t]
            elif (
                t == "and"
                and last in ("hundred", "scale")
                and j + 1 < len(tokens)
                and (tokens[j + 1] in UNITS or tokens[j + 1] in TENS)
            ):
                last = "and"
            else:
                break
            j += 1
            if last == "zero":
                break
        if j == i:
            out.append(tokens[i])
            i += 1
            continue
        number = str(total + current)
        if j + 1 < len(tokens) and tokens[j] == "point" and tokens[j + 1] in UNITS and UNITS[tokens[j + 1]] < 10:
            digits, j = [], j + 1
            while j < len(tokens) and tokens[j] in UNITS and UNITS[tokens[j]] < 10:
                digits.append(str(UNITS[tokens[j]]))
                j += 1
            number += "." + "".join(digits)
        out.append(number)
        i = j
    return out


def words(text):
    text = text.lower().replace("’", "'")
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)  # 1,000 -> 1000
    text = text.replace("%", " percent ")
    text = re.sub(r"[^\w\s'.-]", " ", text)
    text = re.sub(r"(?<!\d)[.](?!\d)|(?<!\w)'|'(?!\w)|(?<!\w)-|-(?!\w)", " ", text)
    tokens = []
    for token in text.split():
        parts = token.split("-")
        spoken_number = len(parts) == 2 and parts[0] in TENS and parts[1] in UNITS and UNITS[parts[1]] < 10
        tokens += parts if spoken_number else [token]
    return numerals(tokens)


_DIGESTS = {}


def model_digest(path):
    """The sha256 of a model file, hashed once per (path, size, mtime) in this process."""
    st = Path(path).stat()
    key = (str(path), st.st_size, st.st_mtime_ns)
    if key not in _DIGESTS:
        _DIGESTS[key] = sha256_file(path)
    return _DIGESTS[key]


def registered(digest, models=None):
    """The program/models.json id whose sha256 is digest, else None."""
    try:
        entries = json.loads(Path(models or MODELS).read_text(encoding="utf-8"))["models"]
    except (OSError, ValueError, KeyError):
        return None
    return next((k for k, v in entries.items() if isinstance(v, dict) and v.get("sha256") == digest), None)


def unsay(tokens, aliases):
    """tokens with each alias's spoken words put back as its written words, alias by alias in the given order."""
    for spoken, written in aliases:
        said, wrote = words(spoken), words(written)
        if not said or said == wrote:
            continue
        out, i = [], 0
        while i < len(tokens):
            if tokens[i : i + len(said)] == said:
                out += wrote
                i += len(said)
            else:
                out.append(tokens[i])
                i += 1
        tokens = out
    return tokens


def wer(reference, hypothesis, aliases=()):
    """Word error rate of hypothesis against reference: (substitutions + deletions + insertions) / len(reference).
    An empty reference scores 0.0 against an empty hypothesis and 1.0 otherwise. aliases, (spoken, written) pairs
    from the pronunciation tables, map the hypothesis back to written words before it is scored."""
    ref, hyp = words(reference), unsay(words(hypothesis), aliases)
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        current = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (r != h))
        previous = current
    return round(previous[-1] / len(ref), 4)


def chunk_wer(written, spoken, heard, aliases=()):
    """A chunk's WER: the better of heard against the written text (spoken table forms in heard mapped back
    through aliases) and heard against the spoken projection. A transcriber writes "MCP" or "M C P" for the
    same correct reading; neither may fail the gate."""
    return min(wer(written, heard, aliases), wer(spoken, heard))


class Whisper:
    """condense's whisper path for one narrate config. available() says whether WER can be measured."""

    def __init__(self, cfg):
        from condense import config as condense_config

        self.cfg = cfg
        self.backend = cfg.whisper.get("backend", "cli")
        self.whisper = condense_config.WHISPER | {k: v for k, v in cfg.whisper.items() if k != "model"}
        self.model = str(cfg.whisper_model)
        self.work = None
        self.model_sha256, self.model_id, self.endpoint = None, None, None

    def available(self):
        if self.backend == "http":
            from condense import transcribe

            try:
                url = transcribe.stt_url(self)
            except ValueError as error:
                return False, str(error)
            parts = urllib.parse.urlsplit(url)
            self.endpoint = f"{parts.scheme}://{parts.netloc}{parts.path}"
            return True, "condense loopback STT backend"
        if not shutil.which("whisper-cli"):
            return False, "whisper-cli is not on PATH (nix develop .#condense)"
        if not Path(self.model).is_file():
            return False, "no whisper model (just condense-model, or [whisper] model, NARRATE_WHISPER_MODEL)"
        digest = model_digest(self.model)
        model_id = registered(digest)
        if model_id is None:
            return False, f"whisper model sha256 {digest[:12]} is not registered in program/models.json"
        self.model_sha256, self.model_id = digest, model_id
        return True, f"whisper-cli with {model_id}"

    def identity(self):
        """What measured WER: the backend with the model digest and registry id, or the loopback endpoint."""
        return {
            "backend": self.backend,
            "model_sha256": self.model_sha256,
            "model_id": self.model_id,
            "endpoint": self.endpoint,
        }

    def read(self, pcm):
        """Whisper's text for one take. The take is read with PAD seconds of silence on each side: whisper drops a
        first sentence that starts on the first sample."""
        from condense import transcribe

        from .audio import Pcm

        padded = Pcm(pcm.rate)
        padded.silence(PAD)
        padded.extend(pcm)
        padded.silence(PAD)
        with tempfile.TemporaryDirectory() as work:
            self.work = Path(work)
            path = padded.write(self.work / "take.wav")
            return transcribe.read(self, path, 0.0, padded.seconds)


def not_measured(reason):
    return {"status": "not_measured", "reason": reason}


def sim(cfg):
    if not cfg.sim.get("model"):
        return not_measured("no registered speaker-verification model")
    return not_measured("render does not score takes in v0; narrate evaluate scores the delivered chunks")


def best_of(chunk_text, synth, measure, gates, base_seed):
    """Run takes until one passes or maxTakes ran. synth(seed) -> (pcm, facts); measure(pcm) -> {wer, sim}.
    Returns (best pcm, best facts, record)."""
    takes, kept = [], None
    max_takes = max(1, int(gates["maxTakes"]))
    for k in range(max_takes):
        seed = base_seed + k
        pcm, facts = synth(seed)
        scores = measure(pcm, chunk_text)
        w, s = scores["wer"], scores["sim"]
        measured_wer = w.get("status") == "measured"
        measured_sim = s.get("status") == "measured"
        passed_wer = not measured_wer or w["value"] <= gates["maxChunkWer"]
        passed_sim = not measured_sim or s["value"] >= gates["minSim"]
        take = {
            "take": k + 1,
            "seed": seed,
            "seconds": round(pcm.seconds, 4),
            "wer": w,
            "sim": s,
            "passed": passed_wer and passed_sim if (measured_wer or measured_sim) else None,
            **facts,
        }
        takes.append((take, pcm, facts))
        if not (measured_wer or measured_sim) or (passed_wer and passed_sim):
            break

    def rank(item):
        take = item[0]
        w = take["wer"]["value"] if take["wer"].get("status") == "measured" else 0.0
        s = take["sim"]["value"] if take["sim"].get("status") == "measured" else 0.0
        return (not take["passed"] if take["passed"] is not None else False, w, -s, take["take"])

    kept = min(takes, key=rank)
    status = "not_measured" if kept[0]["passed"] is None else ("passed" if kept[0]["passed"] else "failed")
    record = {
        "status": status,
        "wer_status": kept[0]["wer"].get("status"),
        "sim_status": kept[0]["sim"].get("status"),
        "kept_take": kept[0]["take"],
        "seed": kept[0]["seed"],
        "takes": [t for t, _, _ in takes],
        "flags": ["qa_failed"] if status == "failed" else [],
    }
    return kept[1], kept[2], record
