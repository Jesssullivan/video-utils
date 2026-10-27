"""A synthetic narrated-video workspace for `just nv-fixture`, `nv-quick` checks and the tests.

write(directory) lays out three directories and returns their paths:

  records/   the committed example records (narrate/dhall/examples), with the narrate job's lexical pin pointed at the
             fixture release below instead of a real xoxd-lexical release
  store/     the private-store stand-in: the generated sine voice and its consent text, the two generated E-major bed
             loops, the deck placeholders (narrate/dhall/check.py fixtures()) and the example script
  lexical/   the fixture lexicon (narrate/tests/fixtures/lexical): a synthetic release, never a vendored one

Every byte is generated or committed as a synthetic fixture: no voice clip, recording, loop or transcript. The
workspace lives wherever the caller names, outside git; nothing here writes into the repository.
"""

import hashlib
import json
import shutil
from pathlib import Path

from ..config import ROOT
from .admit import port

EXAMPLES = ROOT / "narrate" / "dhall" / "examples"
LEXICAL = ROOT / "narrate" / "tests" / "fixtures" / "lexical"
NARRATE_JOB = "job-fixture-fake"
BED = "bed-fixture-emaj"
RECORDS = ("jobs.json", "voices.json", "consents.json", "engines.json", "pronunciation.json", "music-beds.json")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def lexical_pin(directory):
    """The pin of the fixture release in directory (the slides register, as narrate's own tests pin it)."""
    directory = Path(directory)
    lexicon = json.loads((directory / "estate-lexicon.json").read_text(encoding="utf-8"))
    return {
        "release": f"xoxd-lexical@{lexicon['version']}",
        "commit": "0" * 40,
        "lexiconSha256": sha(directory / "estate-lexicon.json"),
        "promptDigestSha256": sha(directory / "prompt-digest.txt"),
        "valeRegister": "slides",
        "valeRegisterSha256": sha(directory / "vale" / "registers" / "slides.ini"),
        "rewriteCheck": True,
    }


def write(directory):
    """{records, store, lexical, script}: the three directories and the script's path in the store."""
    directory = Path(directory)
    records, store, lexical = directory / "records", directory / "store", directory / "lexical"
    for path in (records, store):
        path.mkdir(parents=True, exist_ok=True)
    shutil.copytree(LEXICAL, lexical, dirs_exist_ok=True)
    for name, data in port().fixtures().items():
        (store / name).write_bytes(data)
    script = store / "script.md"
    shutil.copyfile(EXAMPLES / "script.md", script)
    for name in RECORDS:
        shutil.copyfile(EXAMPLES / name, records / name)
    jobs = json.loads((records / "jobs.json").read_text(encoding="utf-8"))
    for job in jobs:
        job["lexical"] = lexical_pin(lexical)
    (records / "jobs.json").write_text(json.dumps(jobs, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"records": records, "store": store, "lexical": lexical, "script": script}
