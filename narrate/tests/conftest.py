"""Synthetic narration workspaces. Every input is made here or committed as a fixture: the Dhall example JSON, the
generated sine voice (narrate/dhall/check.py), a tiny fixture lexicon and scripts written by each test. No clip,
model, network or GPU is used; the fake engine makes every take.
"""

import copy
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[1]
EXAMPLES = PACKAGE / "dhall" / "examples"
LEXICAL = Path(__file__).resolve().parent / "fixtures" / "lexical"


@pytest.fixture(autouse=True)
def hermetic_env(monkeypatch, tmp_path):
    """The fixtures name every input. `just` exports WHISPER_MODEL (just/condense.just), and an operator may export
    the private store, lexical release or engine token; none of them may reach a test. Each test has its own
    one-scorer lock file, so a scorer running on the host never turns a test's SIM into not_measured."""
    monkeypatch.setenv("NARRATE_SCORER_LOCK", str(tmp_path / "scorer.lock"))
    monkeypatch.setenv("NARRATE_RUNS_DIR", str(tmp_path / "narrate-runs"))  # GPU run records (serve/finalize.py)
    for name in (
        "NARRATE_LEASE_HOLDER",
        "WHISPER_MODEL",
        "NARRATE_WHISPER_MODEL",
        "NARRATE_STORE",
        "NARRATE_LEXICAL_DIR",
        "NARRATE_ENGINE_TOKEN",
        "NARRATE_SIM_MODEL",
        "NARRATE_SIM_PYTHON",
    ):
        monkeypatch.delenv(name, raising=False)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dhall_check():
    """narrate/dhall/check.py as a module: its fixture generator and its port of Engine.dhall."""
    spec = importlib.util.spec_from_file_location("narrate_dhall_check", PACKAGE / "dhall" / "check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_pin():
    return {
        "release": "xoxd-lexical@0.0.0-fixture",
        "commit": "0" * 40,
        "lexiconSha256": sha((LEXICAL / "estate-lexicon.json").read_bytes()),
        "promptDigestSha256": sha((LEXICAL / "prompt-digest.txt").read_bytes()),
        "valeRegister": "slides",
        "valeRegisterSha256": sha((LEXICAL / "vale" / "registers" / "slides.ini").read_bytes()),
        "rewriteCheck": True,
    }


FIXTURE_UPSTREAM = {
    "id": "fixture-upstream",
    "language": "en",
    "entries": [
        {
            "id": "fixture-1",
            "written": "ABC",
            "spoken": "A B C",
            "caseSensitive": True,
            "wholeWord": True,
            "note": None,
        },
    ],
}


def narration_fixture(directory, table=None):
    """A synthetic narration-register release in directory and its pin: the fixture lexicon with a public
    pronunciation table (FIXTURE_UPSTREAM unless table is given), never a vendored private lexical table."""
    directory = Path(directory)
    shutil.copytree(LEXICAL, directory, dirs_exist_ok=True)
    data = json.loads((directory / "estate-lexicon.json").read_text())
    data["pronunciation"] = copy.deepcopy(table or FIXTURE_UPSTREAM)
    (directory / "estate-lexicon.json").write_text(json.dumps(data))
    (directory / "prompt-digest-narration.txt").write_text("# fixture narration-only prompt\n")
    register = directory / "vale" / "registers" / "narration.ini"
    register.write_text("BasedOnStyles = FixtureNarration\n")
    return fixture_pin() | {
        "valeRegister": "narration",
        "lexiconSha256": sha((directory / "estate-lexicon.json").read_bytes()),
        "promptDigestSha256": sha((directory / "prompt-digest-narration.txt").read_bytes()),
        "valeRegisterSha256": sha(register.read_bytes()),
    }


class Workspace:
    """A narrate.toml with its rendered records, a fixture store and the fixture lexicon, all under one directory.
    Records are the committed examples, edited per test before write()."""

    def __init__(self, base):
        self.base = Path(base)
        self.store = self.base / "store"
        self.store.mkdir(parents=True)
        for name, data in dhall_check().fixtures().items():
            (self.store / name).write_bytes(data)
        load = lambda name: json.loads((EXAMPLES / name).read_text())  # noqa: E731
        self.job = copy.deepcopy(load("jobs.json")[0])
        self.job["lexical"] = fixture_pin()
        self.job["inputSha256"] = ""
        self.engines = load("engines.json")
        self.voices = load("voices.json")
        self.consents = load("consents.json")
        self.pronunciation = load("pronunciation.json")
        self.options = {}
        self.extra = ""
        self.lexical = LEXICAL

    def use_narration(self, table=None):
        """Pin a synthetic narration-register release (narration_fixture) instead of the slides fixture."""
        self.lexical = self.base / "lexical-narration"
        self.job["lexical"] = narration_fixture(self.lexical, table)

    def add_voice(self, voice_id, consent_id=None):
        """A second consented fixture voice bound to the same generated sine and consent evidence."""
        voice = {**copy.deepcopy(self.voices[0]), "id": voice_id}
        if consent_id:
            voice["consentId"] = consent_id
        self.voices.append(voice)
        return voice

    def write(self, script, kind="Markdown", name=None):
        suffix = {
            "Markdown": ".md",
            "PlainText": ".txt",
            "Srt": ".srt",
            "Vtt": ".vtt",
            "Dialog": ".txt",
            "CondenseWords": ".words.json",
        }[kind]
        path = self.base / (name or f"script{suffix}")
        path.write_text(script if isinstance(script, str) else json.dumps(script))
        self.job["input"] = kind
        records = {
            "jobs.json": [self.job],
            "engines.json": self.engines,
            "voices.json": self.voices,
            "consents.json": self.consents,
            "pronunciation.json": self.pronunciation,
        }
        for file, value in records.items():
            (self.base / file).write_text(json.dumps(value, indent=1))
        options = "".join(f"{k} = {json.dumps(v)}\n" for k, v in self.options.items())
        toml = (
            f'input = "{path.name}"\njob = "jobs.json"\nengines = "engines.json"\nvoices = "voices.json"\n'
            f'consents = "consents.json"\npronunciation = "pronunciation.json"\nstore = "store"\n'
            f'lexical = "{self.lexical}"\nout = "runs"\n'
            f'[whisper]\nmodel = "{self.base / "no-such-model.bin"}"\n'
            + (f"[input_options]\n{options}" if options else "")
            + self.extra
        )
        (self.base / "narrate.toml").write_text(toml)
        return self.base / "narrate.toml"

    def runs(self):
        root = self.base / "runs"
        return sorted(p.name for p in root.iterdir()) if root.is_dir() else []


@pytest.fixture
def workspace(tmp_path):
    return Workspace(tmp_path / "ws")


@pytest.fixture(scope="session")
def ffmpeg():
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is not on PATH (nix develop .#condense)")
    return True


SLIDE = """---
slide: 3
target_seconds: 30
---

# Gate numbers

Narrate reads this slide with the fake engine. Version 2 of the gate allows 8% of stretch.

[pause 400ms]

The MCP tool lists every voice and its consent state.

Sources: none; this text is synthetic.
"""
