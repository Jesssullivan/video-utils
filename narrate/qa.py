"""Per-chunk QA (docs/spec/NARRATE.md, "Dataflow" step 6).

WER: the take is read back through condense's whisper path (condense.transcribe.read: whisper-cli with the
registered model, or condense's loopback STT backend) and compared word by word with the chunk's spoken text.
Without whisper-cli or the model the status is not_measured, as condense's check.json says it, and no gate
judges the take. SIM: not_measured until a speaker-verification model is registered (docs/spec/NARRATE.md).

A take that fails a measured gate is synthesised again with the next seed, at most maxTakes takes in all. The
best take by WER, then SIM, is kept; every take's numbers and the failure are recorded. A chunk that never
passes is flagged qa_failed, never silently accepted. WER is a regression gate, not a ranking.
"""

import re
import shutil
import tempfile
from pathlib import Path

PAD = 0.5  # seconds of silence around a take read back by whisper


def words(text):
    text = text.lower().replace("’", "'")
    text = re.sub(r"[^\w\s'%.-]", " ", text)
    text = re.sub(r"(?<!\d)[.](?!\d)|(?<!\w)'|'(?!\w)|(?<!\w)-|-(?!\w)", " ", text)
    return text.split()


def wer(reference, hypothesis):
    """Word error rate of hypothesis against reference: (substitutions + deletions + insertions) / len(reference).
    An empty reference scores 0.0 against an empty hypothesis and 1.0 otherwise."""
    ref, hyp = words(reference), words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        current = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (r != h))
        previous = current
    return round(previous[-1] / len(ref), 4)


class Whisper:
    """condense's whisper path for one narrate config. available() says whether WER can be measured."""

    def __init__(self, cfg):
        from condense import config as condense_config

        self.cfg = cfg
        self.backend = cfg.whisper.get("backend", "cli")
        self.whisper = condense_config.WHISPER | {k: v for k, v in cfg.whisper.items() if k != "model"}
        self.model = str(cfg.whisper_model)
        self.work = None

    def available(self):
        if self.backend == "http":
            return True, "condense loopback STT backend"
        if not shutil.which("whisper-cli"):
            return False, "whisper-cli is not on PATH (nix develop .#condense)"
        if not Path(self.model).is_file():
            return False, "no whisper model (just condense-model, or WHISPER_MODEL)"
        return True, f"whisper-cli with {Path(self.model).name}"

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
    return not_measured("registered SIM models have no scorer in narrate v0")


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
        "kept_take": kept[0]["take"],
        "seed": kept[0]["seed"],
        "takes": [t for t, _, _ in takes],
        "flags": ["qa_failed"] if status == "failed" else [],
    }
    return kept[1], kept[2], record
