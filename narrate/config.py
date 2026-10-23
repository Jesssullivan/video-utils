"""Load narrate.toml, read the rendered Dhall JSON it names and run the tools.

One narrate.toml names the script, the rendered job, engine, voice, consent and pronunciation JSON (from
`narrate/dhall`, rendered by `dhall-to-json`), the private store that holds reference clips, transcripts and
consent evidence by digest, and the pinned xoxd-lexical release directory. Paths are relative to the file.
The store and the lexical release live outside git: NARRATE_STORE and NARRATE_LEXICAL_DIR override them.
"""

import json
import os
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "narrate"  # outside artifacts/runs/: never a guitar run
FF = ("ffmpeg", "-hide_banner", "-nostdin", "-y")
TIMEOUT_S = float(os.environ.get("NARRATE_TOOL_TIMEOUT_S", 900))
STORE_ENV, LEXICAL_ENV = "NARRATE_STORE", "NARRATE_LEXICAL_DIR"

INPUT = {
    "edl": "",  # CondenseWords: the condense edl.json whose output clock the words map to
    "clip": "",  # CondenseWords: the clip the words were transcribed from
    "sentence_gap_s": 1.0,  # CondenseWords: a longer gap between two words ends a segment
}
FIT = {
    # Speed knob ceiling for a segment that overruns its target. The engine's speed is tried first; atempo
    # then stretches within the job's fitMaxStretch; anything left is flagged overrun, never truncated.
    "speed_max": 1.15,
}
ENGINE = {
    "timeout_s": 300.0,  # one /v1/audio/speech request
    "max_reply_bytes": 256 << 20,
    "ref_audio": "data_uri",  # how ref_audio travels: data_uri (base64 WAV) or omit
}
WHISPER = {
    "model": "models/ggerganov-whisper-cpp-ggml-small.en.bin",  # relative to the repository root
    "language": "en",
    "threads": 4,
}
SIM = {"model": ""}  # a registered speaker-verification model; empty: SIM is not_measured


class Config:
    def __init__(self, path, overrides=None):
        path = Path(path).resolve()
        raw = tomllib.loads(path.read_text()) | (overrides or {})
        base = path.parent
        self.path, self.base = path, base

        def rel(value):
            return (base / value).resolve() if value else None

        self.input = rel(raw.get("input", ""))
        self.input_opts = INPUT | raw.get("input_options", {})
        for key in ("edl",):
            if self.input_opts[key]:
                self.input_opts[key] = str(rel(self.input_opts[key]))
        self.job_file, self.job_id = rel(raw["job"]), raw.get("job_id", "")
        self.engines_file, self.voices_file = rel(raw["engines"]), rel(raw["voices"])
        self.consents_file, self.pronunciation_file = rel(raw["consents"]), rel(raw["pronunciation"])
        self.store = Path(os.environ[STORE_ENV]) if os.environ.get(STORE_ENV) else rel(raw.get("store", ""))
        lexical = os.environ.get(LEXICAL_ENV)
        self.lexical = Path(lexical) if lexical else rel(raw.get("lexical", ""))
        self.out = rel(raw["out"]) if raw.get("out") else ARTIFACTS
        self.fit = FIT | raw.get("fit", {})
        self.engine_opts = ENGINE | raw.get("engine", {})
        self.whisper = WHISPER | raw.get("whisper", {})
        self.sim = SIM | raw.get("sim", {})
        model = os.environ.get("WHISPER_MODEL") or self.whisper["model"]
        self.whisper_model = Path(model) if Path(model).is_absolute() else ROOT / model
        if not 1.0 <= float(self.fit["speed_max"]) <= 2.0:
            raise ValueError(f"fit.speed_max = {self.fit['speed_max']!r}: from 1.0 to 2.0")
        if self.engine_opts["ref_audio"] not in ("data_uri", "omit"):
            raise ValueError(f"engine.ref_audio = {self.engine_opts['ref_audio']!r}: data_uri or omit")

    def job(self):
        """The job named by job_id (or the only job) from the rendered job JSON."""
        jobs = read_list(self.job_file)
        if self.job_id:
            found = [j for j in jobs if j.get("id") == self.job_id]
            if len(found) != 1:
                raise ValueError(f"{self.job_file}: no single job {self.job_id!r}")
            return found[0]
        if len(jobs) != 1:
            raise ValueError(f"{self.job_file}: {len(jobs)} jobs; set job_id")
        return jobs[0]

    def registry(self):
        """{engines, voices, consents, pronunciation}: each keyed by id."""
        return {
            "engines": {e["id"]: e for e in read_list(self.engines_file)},
            "voices": {v["id"]: v for v in read_list(self.voices_file)},
            "consents": {c["id"]: c for c in read_list(self.consents_file)},
            "pronunciation": {t["id"]: t for t in read_list(self.pronunciation_file)},
        }


def read_list(path):
    """A rendered Dhall value that is one record or a list of records."""
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    return value if isinstance(value, list) else [value]


def run(*args, cwd=None, timeout=None, input=None):
    """Run a tool. Return the finished process, or raise with the end of its stderr or on timeout."""
    timeout = TIMEOUT_S if timeout is None else timeout
    try:
        p = subprocess.run(
            [str(a) for a in args],
            capture_output=True,
            text=input is None or isinstance(input, str),
            errors="replace" if input is None or isinstance(input, str) else None,
            cwd=cwd,
            timeout=timeout,
            input=input,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{args[0]} ran over {timeout:g} s (NARRATE_TOOL_TIMEOUT_S)") from None
    if p.returncode:
        err = p.stderr if isinstance(p.stderr, str) else p.stderr.decode(errors="replace")
        raise RuntimeError(f"{args[0]} failed ({p.returncode}):\n{err[-2000:]}")
    return p
