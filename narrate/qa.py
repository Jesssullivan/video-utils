"""Per-chunk QA (docs/spec/NARRATE.md, "Dataflow" step 6).

WER: the take is read back through condense's whisper path (condense.transcribe.read: whisper-cli with the
registered model, or condense's loopback STT backend) and compared word by word with the chunk's spoken text.
Without whisper-cli or the model the status is not_measured, as condense's check.json says it, and no gate
judges the take. The model file is hashed once per path and must match a sha256 in program/models.json; an
unregistered or partial file leaves WER not_measured. The manifest records the model's digest and registry id, or
the loopback endpoint of the http backend. Numbers are compared as digits on both sides ("seven" and "7" are one
word), so whisper writing numerals is not an error. Both sides go through the same normalisation (NORMALISATION
names its version and every WER receipt records it): a hyphen or en dash between letters splits a word, a unit
symbol after a number is said as its unit word, a British spelling from SPELLING is folded to its American form,
and a closed compound scores equal to its open form when the letters concatenate to the same word.

SIM: render does not score takes in v0; `narrate evaluate` scores the delivered chunks with the registered
speaker-verification model (narrate/sim.py). Whisper runs with at most MAX_WHISPER_THREADS threads, whatever
narrate.toml asks ("Host placement and memory").

A take that fails a measured gate is synthesised again with the next seed, at most maxTakes takes in all. The
best take by WER, then SIM, is kept; every take's numbers and the failure are recorded. A chunk that never
passes is flagged qa_failed, never silently accepted. WER is a regression gate, not a ranking. A prerendered
batch (narrate/prerender.py) already holds its takes, so best_of scores every take it holds (exhaustive) and keeps
the best rather than the first that passes. It may hold fewer takes than maxTakes: synth raises NoTake for a seed
the batch lacks, the next seed is tried, and the record lists the missing seeds; a chunk with no take re-raises.
"""

import json
import re
import shutil
import tempfile
import urllib.parse
from pathlib import Path

from .amounts import _SYMBOLS as _UNIT_SYMBOLS
from .amounts import _TIGHT_REFUSED
from .amounts import say as say_amounts
from .ir import sha256_file
from .lexical import UNITS as _SHARED_UNITS

PAD = 0.5  # seconds of silence around a take read back by whisper
MAX_WHISPER_THREADS = 4  # the host placement rule's whisper ceiling
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

# The WER normalisation version. narrate-wer-1 (no field in a receipt) kept hyphenated words whole, left unit
# symbols as written and scored spelling variants and open compounds as errors; narrate-wer-2 is words() below.
NORMALISATION = "narrate-wer-2"

# Unit symbols said as words: the shared table (lexical.UNITS, each symbol with its singular and plural spoken
# alias) and the units below, which only WER reads. % is said by words() itself; x is left out because "3 x 4" is
# said "by" as often as "times". A symbol maps only after a number (32 Hz, 5mA), case sensitive, except
# STANDALONE ones, which no English word spells. s and B written against the digits (1990s, 20B) stay as written.
_EXTRA_UNITS = {
    "mm": ("millimeter", "millimeters"),
    "cm": ("centimeter", "centimeters"),
    "km": ("kilometer", "kilometers"),
    "nm": ("nanometer", "nanometers"),
    "µm": ("micrometer", "micrometers"),
    "μm": ("micrometer", "micrometers"),
    "um": ("micrometer", "micrometers"),
    "V": ("volt", "volts"),
    "mV": ("millivolt", "millivolts"),
    "kV": ("kilovolt", "kilovolts"),
    "A": ("ampere", "amperes"),
    "mA": ("milliampere", "milliamperes"),
    "µA": ("microampere", "microamperes"),
    "μA": ("microampere", "microamperes"),
    "uA": ("microampere", "microamperes"),
    "W": ("watt", "watts"),
    "mW": ("milliwatt", "milliwatts"),
    "kW": ("kilowatt", "kilowatts"),
    "Ω": ("ohm", "ohms"),
    "kΩ": ("kilohm", "kilohms"),
    "µs": ("microsecond", "microseconds"),
    "μs": ("microsecond", "microseconds"),
    "ns": ("nanosecond", "nanoseconds"),
    "°C": ("degree celsius", "degrees celsius"),
    "°F": ("degree fahrenheit", "degrees fahrenheit"),
    "°": ("degree", "degrees"),
}


def _said_units():
    out = {}
    for unit, aliases in _SHARED_UNITS.items():
        spoken = [a for a in aliases if a not in _UNIT_SYMBOLS]
        if unit in ("%", "x") or not spoken:
            continue
        for symbol in (a for a in aliases if a in _UNIT_SYMBOLS):
            out[symbol] = (spoken[0], spoken[-1])
    return out | _EXTRA_UNITS


UNIT_WORDS = _said_units()
STANDALONE = set("Hz kHz MHz GHz dB dBFS dBTP LUFS mV kV mA uA µA μA mW kW kΩ µs μs µm μm °C °F".split())
_NUMBER_UNIT = re.compile(
    r"(?<![\w.,])(?P<n>\d+(?:[.,]\d+)*)(?P<gap>[ \N{NO-BREAK SPACE}]?)(?P<u>"
    + "|".join(re.escape(u) for u in sorted(UNIT_WORDS, key=len, reverse=True))
    + r")(?![\w°])"
)
_BARE_UNIT = re.compile(
    r"(?<![\w°])(" + "|".join(re.escape(u) for u in sorted(STANDALONE, key=len, reverse=True)) + r")(?!\w)"
)
# Unit words with a singular and a plural that no other English word shares: both score as the plural.
# second, minute, hour, degree, unit and times are ordinary words too, so their number is kept.
_UNIT_PLURAL = {
    one: many
    for one, many in UNIT_WORDS.values()
    if " " not in one and one != many and one not in ("second", "minute", "hour", "degree", "unit")
}

# British spellings folded to American ones, a closed list (-our/-or, -re/-er, -ise/-ize, -yse/-yze, doubled l
# and single words); a word not listed is scored as written. Each stem takes the inflections its rule lists.
_OUR = "armour behaviour colour endeavour favour flavour harbour honour humour labour neighbour odour rumour vapour"
_RE = "calibre centre fibre litre lustre metre centimetre millimetre kilometre micrometre nanometre sabre theatre"
_ISE = (
    "apologise authorise categorise characterise customise emphasise finalise initialise maximise memorise "
    "minimise normalise optimise organise prioritise realise recognise serialise specialise stabilise "
    "standardise summarise synchronise utilise visualise"
)
_LL = "cancel channel equal fuel label level model signal travel"


def _spelling():
    table = {}
    for word in _OUR.split():
        stem = word[:-3]
        for end in ("", "s", "ed", "ing", "ite", "ites", "able", "ful"):
            table[stem + "our" + end] = stem + "or" + end
    for word in _RE.split():
        stem = word[:-2]
        for uk, us in (("re", "er"), ("res", "ers"), ("red", "ered"), ("ring", "ering")):
            table[stem + uk] = stem + us
    for word in _ISE.split():
        stem = word[:-3]
        for end in ("e", "ed", "es", "ing", "ation", "ations", "er", "ers"):
            table[stem + "is" + end] = stem + "iz" + end
    for stem in ("analy", "paraly", "cataly"):
        for end in ("se", "sed", "sing"):
            table[stem + end] = stem + "z" + end[1:]
    for stem in _LL.split():
        for end in ("ed", "ing", "er", "ers"):
            table[stem + "l" + end] = stem + end
    table |= {
        "grey": "gray",
        "greys": "grays",
        "greyed": "grayed",
        "greyish": "grayish",
        "aluminium": "aluminum",
        "tyre": "tire",
        "tyres": "tires",
        "programme": "program",
        "programmes": "programs",
        "catalogue": "catalog",
        "catalogues": "catalogs",
        "analogue": "analog",
        "defence": "defense",
        "licence": "license",
        "offence": "offense",
        "practise": "practice",
        "practised": "practiced",
        "practising": "practicing",
        "jewellery": "jewelry",
        "sulphur": "sulfur",
        "mould": "mold",
        "plough": "plow",
        "manoeuvre": "maneuver",
        "aeroplane": "airplane",
    }
    return table


SPELLING = _spelling()


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


def _say_unit(m):
    n, gap, unit = m.group("n"), m.group("gap"), m.group("u")
    if unit in _TIGHT_REFUSED and not gap:
        return m.group(0)
    one, many = UNIT_WORDS[unit]
    return f"{n} {one if n == '1' else many}"


def words(text):
    """The scored tokens of text, normalised as NORMALISATION names (the module docstring)."""
    text = text.replace("’", "'")
    text = _NUMBER_UNIT.sub(_say_unit, text)
    text = _BARE_UNIT.sub(lambda m: UNIT_WORDS[m.group(1)][1], text)
    text = text.lower()
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)  # 1,000 -> 1000
    text = text.replace("%", " percent ")
    # tool-head, tool–head: a hyphen, non-breaking hyphen or en dash between letters splits the word
    text = re.sub(r"(?<=[^\W\d_])[-\u2010\u2011\u2013](?=[^\W\d_])", " ", text)
    text = re.sub(r"[^\w\s'.-]", " ", text)
    text = re.sub(r"(?<!\d)[.](?!\d)|(?<!\w)'|'(?!\w)|(?<!\w)-|-(?!\w)", " ", text)
    tokens = [SPELLING.get(t, t) for t in numerals(text.split())]
    return [_UNIT_PLURAL.get(t, t) for t in tokens]


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


COMPOUND_PARTS = 3  # the most words an open compound is written in (head board rail)


def _closed(parts):
    """The closed compound parts spell, or None when any part is not two or more letters: numbers never join, and
    spelled letters (M C P) never join into a word, which only a pronunciation alias allows."""
    return "".join(parts) if all(p.isalpha() and len(p) > 1 for p in parts) else None


def wer(reference, hypothesis, aliases=()):
    """Word error rate of hypothesis against reference: (substitutions + deletions + insertions) / len(reference).
    An empty reference scores 0.0 against an empty hypothesis and 1.0 otherwise. aliases, (spoken, written) pairs
    from the pronunciation tables, map the hypothesis back to written words before it is scored. One word on one
    side matches 2 to COMPOUND_PARTS words on the other at no cost when their letters concatenate to it
    (toolhead and tool head); the reference length stays the count of its words."""
    ref, hyp = words(reference), unsay(words(hypothesis), aliases)
    if not ref:
        return 0.0 if not hyp else 1.0
    d = [[i + j if not (i and j) else 0 for j in range(len(hyp) + 1)] for i in range(len(ref) + 1)]
    for i in range(1, len(ref) + 1):
        for j in range(1, len(hyp) + 1):
            best = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]))
            for k in range(2, COMPOUND_PARTS + 1):
                if j >= k and ref[i - 1].isalpha() and ref[i - 1] == _closed(hyp[j - k : j]):
                    best = min(best, d[i - 1][j - k])
                if i >= k and hyp[j - 1].isalpha() and hyp[j - 1] == _closed(ref[i - k : i]):
                    best = min(best, d[i - k][j - 1])
            d[i][j] = best
    return round(d[-1][-1] / len(ref), 4)


def chunk_wer(written, spoken, heard, aliases=()):
    """A chunk's WER: the best of heard against the written text (spoken table forms in heard mapped back
    through aliases) and heard against the spoken projection, each with heard as written and with any range or
    dollar amount heard wrote in digits said in words (amounts.say). A transcriber writes "MCP" or "M C P", and
    "$5 to $10" or "five to ten dollars", for the same correct reading; neither may fail the gate."""
    said = say_amounts(heard)
    return min(wer(written, heard, aliases), wer(spoken, heard), wer(written, said, aliases), wer(spoken, said))


class Whisper:
    """condense's whisper path for one narrate config. available() says whether WER can be measured."""

    def __init__(self, cfg):
        from condense import config as condense_config

        self.cfg = cfg
        self.backend = cfg.whisper.get("backend", "cli")
        self.whisper = condense_config.WHISPER | {k: v for k, v in cfg.whisper.items() if k != "model"}
        self.whisper["threads"] = max(1, min(int(self.whisper["threads"]), MAX_WHISPER_THREADS))
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


class NoTake(LookupError):
    """synth has no take for this seed (a prerendered batch that did not render it)."""


def best_of(chunk_text, synth, measure, gates, base_seed, exhaustive=False):
    """Run takes until one passes or maxTakes ran; with exhaustive (takes that already exist), score every take
    unless nothing is measured. synth(seed) -> (pcm, facts), or NoTake for a seed with no take; measure(pcm) ->
    {wer, sim}. Returns (best pcm, best facts, record)."""
    takes, kept, missing, absent = [], None, [], None
    max_takes = max(1, int(gates["maxTakes"]))
    for k in range(max_takes):
        seed = base_seed + k
        try:
            pcm, facts = synth(seed)
        except NoTake as error:
            missing.append(seed)
            absent = absent or error
            continue
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
        if not (measured_wer or measured_sim) or (passed_wer and passed_sim and not exhaustive):
            break
    if not takes:
        raise absent

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
    if missing:
        record["missing_seeds"] = missing
    return kept[1], kept[2], record
