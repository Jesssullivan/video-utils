"""Narrated-video jobs and the records they name (docs/spec/NARRATED_VIDEO.md).

A job is the dhall-to-json render of one NarratedVideo record. It holds digests and record ids, never paths. The
records it names (narrate jobs, voices, consents and music beds) are dhall-to-json renders too, read from one
records directory with the file names narrate/dhall/examples uses: jobs.json, voices.json, consents.json and
music-beds.json. The fixture records are that examples directory; real records live in the private store.

DEFAULTS mirrors NarratedVideo.defaults. `init` builds a simple job from it: a colour card or a still, one segment
anchored Auto, no avatar, the bed only when one is named, tighten off (NV-2).
"""

import copy
import json
import re
from pathlib import Path

ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COLOUR = re.compile(r"^#[0-9a-fA-F]{6}$")
RECORD_FILES = {
    "jobs": "jobs.json",
    "voices": "voices.json",
    "consents": "consents.json",
    "music_beds": "music-beds.json",
}
MAX_RECORD_BYTES = 16 * 1024 * 1024
EDITIONS = ("Internal", "OwnContent", "ClientVoiceOnly", "ClientNarrated")
BASE_KINDS = ("still", "card", "video", "deck")
FIELDS = ("id", "edition", "base", "segments", "avatar", "music", "tighten", "captions", "labels", "delivery")

# NarratedVideo.defaults (narrate/dhall/NarratedVideo.dhall). tests/test_narrated_video_graph.py pins init's output
# to the nv-fixture-card example, which is built from these defaults.
DEFAULTS = {
    "edition": "Internal",
    "fps": {"num": 30, "den": 1},
    "size": {"w": 1920, "h": 1080},
    "tailS": 1,
    "colour": "#101820",
    "avatar": {
        "external": "kitpip",
        "rig": None,
        "rigRevisionSha256": None,
        "renderSize": 512,
        "corner": "BR",
        "width": 0.22,
        "marginPx": 32,
    },
    "music": {
        "bedBelowVoiceLu": 20,
        "duckMode": "Sidechain",
        "duckDb": 7,
        "attackMs": 50,
        "releaseMs": 400,
        "fadeInS": 3,
        "fadeOutS": 5,
        "tailS": 5,
    },
    "tighten": {"enabled": False},
    "labels": {"persona": None, "personaCue": None, "extraNotice": None},
    "captions": {"soft": True, "burn": False, "srt": True, "vtt": True},
    "delivery": {
        "profile": "Web1080p30",
        "targetLufs": -16,
        "truePeakDbtp": -1.5,
        "driftLu": 0.5,
        "channels": "Mono",
        "upload": False,
        "handoff": False,
        "voiceOnlyListen": None,
    },
}


class JobError(ValueError):
    """A job or record the graph refuses. code is the typed refusal."""

    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def read_json(path, what):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise JobError("records_missing", f"{what}: {path.name} is not a regular file")
    if path.stat().st_size > MAX_RECORD_BYTES:
        raise JobError("records_invalid", f"{what}: {path.name} is larger than {MAX_RECORD_BYTES} bytes")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JobError("records_invalid", f"{what}: {path.name}: {exc}") from None


def load_records(directory):
    """{jobs, voices, consents, music_beds}: each {id: record}. A missing music-beds.json is an empty table."""
    if directory is None:
        raise JobError("records_missing", "no records directory: pass --records or set NARRATED_VIDEO_RECORDS")
    directory = Path(directory)
    if not directory.is_dir():
        raise JobError("records_missing", "the records directory does not exist")
    records = {}
    for name, file in RECORD_FILES.items():
        if name == "music_beds" and not (directory / file).exists():
            records[name] = {}
            continue
        rows = read_json(directory / file, "records")
        if not isinstance(rows, list) or not all(isinstance(r, dict) and isinstance(r.get("id"), str) for r in rows):
            raise JobError("records_invalid", f"{file} is not a list of records with ids")
        table = {r["id"]: r for r in rows}
        if len(table) != len(rows):
            raise JobError("records_invalid", f"{file}: ids repeat")
        records[name] = table
    return records


def check_shape(job):
    """The structure the graph reads. Values and cross-references are admit's (admit.py)."""
    if not isinstance(job, dict) or set(job) != set(FIELDS):
        missing = sorted(set(FIELDS) - set(job)) if isinstance(job, dict) else FIELDS
        raise JobError("job_invalid", f"a NarratedVideo record has exactly {', '.join(FIELDS)}; missing {missing}")
    if not isinstance(job["id"], str) or not ID.match(job["id"]):
        raise JobError("job_invalid", "id is 1 to 64 of a-z, 0-9, '.', '_' and '-', starting with a letter or digit")
    if job["edition"] not in EDITIONS:
        raise JobError("job_invalid", f"edition {job['edition']!r} is not one of {', '.join(EDITIONS)}")
    base = job["base"]
    if not isinstance(base, dict) or len(base) != 1 or next(iter(base)) not in BASE_KINDS:
        raise JobError("job_invalid", "base is one of still, card, video or deck")
    if not isinstance(job["segments"], list):
        raise JobError("job_invalid", "segments is a list")
    ids = []
    for segment in job["segments"]:
        if not isinstance(segment, dict) or not isinstance(segment.get("id"), str) or not ID.match(segment["id"]):
            raise JobError("job_invalid", "every segment has an id of a-z, 0-9, '.', '_' and '-'")
        ids.append(segment["id"])
    if len(set(ids)) != len(ids):
        raise JobError("job_invalid", "segment ids repeat")
    if not isinstance(job["tighten"], dict) or not isinstance(job["tighten"].get("enabled"), bool):
        raise JobError("job_invalid", "tighten is {enabled: bool}")
    return job


def init_job(
    job_id, narrate_job, script_sha256, *, still=None, colour=None, bed=None, edition=None, avatar=False, persona=None
):
    """A simple job from DEFAULTS. still is a SHA-256 (with the default size, rate and tail); otherwise a card."""
    d = DEFAULTS
    if still is not None and not SHA256.match(still):
        raise JobError("job_invalid", "--still is the still's SHA-256 in the private store, never a path")
    if colour is not None and not COLOUR.match(colour):
        raise JobError("job_invalid", "--card is a #rrggbb colour")
    picture = {"size": copy.deepcopy(d["size"]), "fps": copy.deepcopy(d["fps"]), "tailS": d["tailS"]}
    base = {"still": {"sha256": still} | picture} if still else {"card": {"colour": colour or d["colour"]} | picture}
    job = {
        "id": job_id,
        "edition": edition or d["edition"],
        "base": base,
        "segments": [
            {"id": "seg-1", "narrateJob": narrate_job, "scriptSha256": script_sha256, "anchor": "Auto", "avatar": True}
        ],
        "avatar": copy.deepcopy(d["avatar"]) if avatar else None,
        "music": copy.deepcopy(d["music"]) | {"bed": bed} if bed else None,
        "tighten": copy.deepcopy(d["tighten"]),
        "captions": copy.deepcopy(d["captions"]),
        "labels": copy.deepcopy(d["labels"]) | ({"persona": persona} if persona else {}),
        "delivery": copy.deepcopy(d["delivery"]),
    }
    return check_shape(job)
