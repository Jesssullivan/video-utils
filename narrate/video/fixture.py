"""A synthetic narrated-video workspace for `just nv-fixture`, `nv-quick` checks and the tests.

write(directory) lays out three directories and returns their paths:

  records/   the committed example records (narrate/dhall/examples), with the narrate job's lexical pin pointed at the
             fixture release below instead of a real xoxd-lexical release
  store/     the private-store stand-in: the generated sine voice and its consent text, the two generated E-major bed
             loops, the deck placeholders (narrate/dhall/check.py fixtures()) and the example script
  lexical/   the fixture lexicon (narrate/tests/fixtures/lexical): a synthetic release, never a vendored one

Every byte is generated or committed as a synthetic fixture: no voice clip, recording, loop or transcript. The
workspace lives wherever the caller names, outside git; nothing here writes into the repository.

write_bundle(directory) writes a synthetic demo bundle (docs/spec/NARRATED_VIDEO.md, "Demo bundle intake") named
demo-fixture: the two generated slide pictures, an unused 1x1 GIF, a two-beat script.md and a claims.json whose
receipts are fixture ids. No real demo, client text or receipt is in it.
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


BUNDLE = "demo-fixture"
# A 1x1 GIF89a: an asset the intake must refuse when a beat cites it (no stage reads GIF).
GIF_1X1 = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00"
    b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)
BUNDLE_SCRIPT = """# Demo fixture

> Synthetic bundle for the narrated-video intake tests. No real demo, recording or client text.

## intro

- target_s: 8
- asset_id: slide-a
- claims: build-ms

```voiced
This synthetic fixture stands in for a demo.

Its build took seventeen point eight seven seven milliseconds.
```

## result

- target_s: 8.5
- asset_id: slide-b
- claims: cache-rate, files

```voiced
The fixture cache then answered forty two percent of its requests.

It did so across four hundred generated files.
```
"""
BUNDLE_CLAIMS = [
    {
        "id": "build-ms",
        "value": {"spoken": "seventeen point eight seven seven milliseconds", "number": 17.877, "unit": "ms"},
        "receipt": "fixture-receipt-build",
    },
    {
        "id": "cache-rate",
        "value": {"spoken": "forty two percent", "number": 42, "unit": "percent"},
        "receipt": "fixture-receipt-cache",
    },
    {
        "id": "files",
        "value": {"spoken": "four hundred", "number": 400, "unit": ""},
        "receipt": "fixture-receipt-files",
    },
]


def write_bundle(directory, slug=BUNDLE):
    """directory/slug: a synthetic demo bundle. Returns its path."""
    bundle = Path(directory) / slug
    (bundle / "assets").mkdir(parents=True)
    files = port().fixtures()
    assets = []
    for asset_id, name, kind, data in (
        ("slide-a", "slide-a.png", "png", files["slide-a.png"]),
        ("slide-b", "slide-b.png", "png", files["slide-b.png"]),
        ("loop-a", "loop-a.gif", "gif", GIF_1X1),
    ):
        (bundle / "assets" / name).write_bytes(data)
        asset = {
            "id": asset_id,
            "path": f"assets/{name}",
            "sha256": hashlib.sha256(data).hexdigest(),
            "kind": kind,
            "receipt": f"fixture-receipt-{asset_id}",
        }
        if kind == "png":
            asset["size"] = {"w": 320, "h": 180}
        assets.append(asset)
    (bundle / "manifest.json").write_text(json.dumps({"assets": assets}, indent=1) + "\n", encoding="utf-8")
    (bundle / "script.md").write_text(BUNDLE_SCRIPT, encoding="utf-8")
    (bundle / "claims.json").write_text(json.dumps(BUNDLE_CLAIMS, indent=1) + "\n", encoding="utf-8")
    return bundle
