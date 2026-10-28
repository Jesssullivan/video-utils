"""Narrated-video jobs and the records they name (docs/spec/NARRATED_VIDEO.md).

A job is the dhall-to-json render of one NarratedVideo record. It holds digests and record ids, never paths. The
records it names (narrate jobs, voices, consents and music beds) are dhall-to-json renders too, read from one
records directory with the file names narrate/dhall/examples uses: jobs.json, voices.json, consents.json and
music-beds.json. The fixture records are that examples directory; real records live in the private store.

DEFAULTS mirrors NarratedVideo.defaults. `init` builds a simple job from it: a colour card or a still, one segment
anchored Auto, the bed only when one is named, tighten off (NV-2). The kitpip avatar is on by default for an edition
that allows one (NV-8, TIN-7476 comment df0ed8e6), so it needs a persona label; --no-avatar turns it off. See
"Avatar default" in docs/spec/NARRATED_VIDEO.md.
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
    "engines": "engines.json",
    "pronunciation": "pronunciation.json",
}
# Tables a job may not need: a missing file is an empty table. engines.json and pronunciation.json are narrate's own
# records; the voice stage keys the engine and pronunciation table its narrate job names, and narrate refuses a
# missing one when it renders.
OPTIONAL_RECORDS = ("music_beds", "engines", "pronunciation")
MAX_RECORD_BYTES = 16 * 1024 * 1024
EDITIONS = ("Internal", "OwnContent", "ClientVoiceOnly", "ClientNarrated")
CLIENT_EDITIONS = ("ClientVoiceOnly", "ClientNarrated")
# NV-6 (TIN-7476 comment 92605219): a client delivery is ClientNarrated unless its project picks ClientVoiceOnly.
# NarratedVideo.defaults.clientEdition (narrate/dhall/NarratedVideo.dhall) holds the same value.
CLIENT_DEFAULT_EDITION = "ClientNarrated"
BASE_KINDS = ("still", "card", "video", "deck")
FIELDS = (
    "id", "edition", "base", "segments", "avatar", "slides", "music", "tighten", "captions", "labels", "delivery",
)  # fmt: skip
AVATAR_EDITIONS = ("Internal", "OwnContent", "ClientNarrated")  # Edition.check refuses an avatar in ClientVoiceOnly

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
        "avatarOff": [],
        "fadeS": 0.35,
    },
    # The slide card (docs/spec/NARRATED_VIDEO.md, "Slides"): off by default (layout Full); a job sets
    # CardLowerLeft and its pages.
    "slides": {"layout": "Full", "cardWidth": 0.42, "marginPx": 64, "fadeS": 0.35, "dimTo": 0.5},
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
    """{jobs, voices, consents, music_beds, engines, pronunciation}: each {id: record}. A file may hold one record
    or a list (narrate renders pronunciation.json as one table). A missing optional file is an empty table."""
    if directory is None:
        raise JobError("records_missing", "no records directory: pass --records or set NARRATED_VIDEO_RECORDS")
    directory = Path(directory)
    if not directory.is_dir():
        raise JobError("records_missing", "the records directory does not exist")
    records = {}
    for name, file in RECORD_FILES.items():
        if name in OPTIONAL_RECORDS and not (directory / file).exists():
            records[name] = {}
            continue
        rows = read_json(directory / file, "records")
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list) or not all(isinstance(r, dict) and isinstance(r.get("id"), str) for r in rows):
            raise JobError("records_invalid", f"{file} is not a list of records with ids")
        table = {r["id"]: r for r in rows}
        if len(table) != len(rows):
            raise JobError("records_invalid", f"{file}: ids repeat")
        records[name] = table
    return records


# The NarratedVideo JSON shape (narrate/dhall/NarratedVideo.dhall rendered by dhall-to-json). A dict is a record with
# exactly those fields; a tuple of strings is an enum; ("optional", s) is null or s; ("union", {tag: s}, (names))
# is one {tag: payload} or one of the bare names. check_shape walks every field, so no stage meets a KeyError later.
TEXT, BOOL, NATURAL, DOUBLE, DIGEST = "text", "bool", "natural", "double", "sha256"
RATE = {"num": NATURAL, "den": NATURAL}
SIZE = {"w": NATURAL, "h": NATURAL}
SHAPE = {
    "base": (
        "union",
        {
            "still": {"sha256": DIGEST, "size": SIZE, "fps": RATE, "tailS": DOUBLE},
            "card": {"colour": TEXT, "size": SIZE, "fps": RATE, "tailS": DOUBLE},
            "video": {"sha256": DIGEST, "keepBaseAudio": BOOL},
            "deck": {
                "producer": TEXT,
                "videoSha256": DIGEST,
                "timelineSha256": DIGEST,
                "stemsSha256": DIGEST,
                "tightenEditsSha256": ("optional", DIGEST),
            },
        },
        (),
    ),
    "segment": {
        "id": TEXT,
        "narrateJob": TEXT,
        "scriptSha256": DIGEST,
        "anchor": ("union", {"atSeconds": DOUBLE, "page": TEXT}, ("Auto",)),
        "avatar": BOOL,
    },
    "avatar": (
        "optional",
        {
            "external": TEXT,
            "rig": ("optional", TEXT),
            "rigRevisionSha256": ("optional", DIGEST),
            "renderSize": NATURAL,
            "corner": ("BR", "BL", "TR", "TL"),
            "width": DOUBLE,
            "marginPx": NATURAL,
            "avatarOff": ("list", TEXT),
            "fadeS": DOUBLE,
        },
    ),
    "slides": (
        "optional",
        {
            "layout": ("Full", "CardLowerLeft"),
            "cardWidth": DOUBLE,
            "marginPx": NATURAL,
            "fadeS": DOUBLE,
            "dimTo": DOUBLE,
            "pages": (
                "list",
                {
                    "id": TEXT,
                    "startS": DOUBLE,
                    "endS": DOUBLE,
                    "show": ("union", {"slide": {"sha256": DIGEST}}, ("Base", "Hold")),
                },
            ),
        },
    ),
    "music": (
        "optional",
        {
            "bed": TEXT,
            "bedBelowVoiceLu": DOUBLE,
            "duckMode": ("Sidechain", "EdlEnvelope"),
            "duckDb": DOUBLE,
            "attackMs": NATURAL,
            "releaseMs": NATURAL,
            "fadeInS": DOUBLE,
            "fadeOutS": DOUBLE,
            "tailS": DOUBLE,
        },
    ),
    "tighten": {"enabled": BOOL},
    "captions": {"soft": BOOL, "burn": BOOL, "srt": BOOL, "vtt": BOOL},
    "labels": {"persona": ("optional", TEXT), "personaCue": ("optional", TEXT), "extraNotice": ("optional", TEXT)},
    "delivery": {
        "profile": ("Web1080p30", "Talk", "Contingency"),
        "targetLufs": DOUBLE,
        "truePeakDbtp": DOUBLE,
        "driftLu": DOUBLE,
        "channels": ("Mono", "Stereo"),
        "upload": BOOL,
        "handoff": BOOL,
        "voiceOnlyListen": ("optional", TEXT),
    },
}


def shape_problem(value, shape, where):
    """The first way value departs from shape, as text, or None when it fits."""
    if shape == TEXT:
        return None if isinstance(value, str) else f"{where} is not text"
    if shape == BOOL:
        return None if isinstance(value, bool) else f"{where} is not a bool"
    if shape == NATURAL:
        ok = isinstance(value, int) and not isinstance(value, bool) and value >= 0
        return None if ok else f"{where} is not a natural number"
    if shape == DOUBLE:
        ok = isinstance(value, (int, float)) and not isinstance(value, bool) and value == value
        return None if ok and abs(value) != float("inf") else f"{where} is not a finite number"
    if shape == DIGEST:
        return None if isinstance(value, str) and SHA256.match(value) else f"{where} is not a lowercase SHA-256"
    if isinstance(shape, dict):
        if not isinstance(value, dict):
            return f"{where} is not a record"
        if set(value) != set(shape):
            missing, extra = sorted(set(shape) - set(value)), sorted(set(value) - set(shape))
            return f"{where} has fields {sorted(shape)}; missing {missing}, unknown {extra}"
        for name, field in shape.items():
            problem = shape_problem(value[name], field, f"{where}.{name}")
            if problem:
                return problem
        return None
    if shape[0] == "optional":
        return None if value is None else shape_problem(value, shape[1], where)
    if shape[0] == "list":
        if not isinstance(value, list):
            return f"{where} is not a list"
        return next((p for i, v in enumerate(value) if (p := shape_problem(v, shape[1], f"{where}[{i}]"))), None)
    if shape[0] == "union":
        _, payloads, names = shape
        if isinstance(value, str) and value in names:
            return None
        if not isinstance(value, dict) or len(value) != 1 or next(iter(value)) not in payloads:
            return f"{where} is not one of {', '.join(list(names) + sorted(payloads))}"
        tag = next(iter(value))
        return shape_problem(value[tag], payloads[tag], f"{where}.{tag}")
    return None if value in shape else f"{where} {value!r} is not one of {', '.join(shape)}"


def check_shape(job):
    """The structure the graph reads: every field of the NarratedVideo shape (SHAPE), so a misshapen record is
    refused before anything is written. Values and cross-references are admit's (admit.py)."""
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
    problems = [shape_problem(job["base"], SHAPE["base"], "base")]
    problems += [shape_problem(s, SHAPE["segment"], f"segments[{i}]") for i, s in enumerate(job["segments"])]
    records = ("avatar", "slides", "music", "tighten", "captions", "labels", "delivery")
    problems += [shape_problem(job[f], SHAPE[f], f) for f in records]
    problem = next((p for p in problems if p), None)
    if problem:
        raise JobError("job_invalid", problem)
    if "card" in job["base"] and not COLOUR.match(job["base"]["card"]["colour"]):
        raise JobError("job_invalid", "base.card.colour is not a #rrggbb colour")
    return job


def init_job(
    job_id,
    narrate_job,
    script_sha256,
    *,
    still=None,
    colour=None,
    bed=None,
    edition=None,
    avatar=None,
    persona=None,
    client=False,
):
    """A simple job from DEFAULTS. still is a SHA-256 (with the default size, rate and tail); otherwise a card.

    client: a client delivery. Its edition is CLIENT_DEFAULT_EDITION (ClientNarrated, NV-6); a non-client edition
    refuses edition_not_client. The defaults voice seg-1 with a synthetic narrate job, which ClientVoiceOnly
    refuses at Plan, so init refuses ClientVoiceOnly up front: that job comes from a render through --from.

    avatar None takes the default: on for an edition that allows one (NV-8), off for ClientVoiceOnly. With the
    avatar on, persona is required (admit refuses persona_label_missing without it). avatar False turns it off."""
    d = DEFAULTS
    if client:
        if edition is not None and edition not in CLIENT_EDITIONS:
            raise JobError("edition_not_client", f"a client delivery is {' or '.join(CLIENT_EDITIONS)}, not {edition}")
        edition = edition or CLIENT_DEFAULT_EDITION
    if edition == "ClientVoiceOnly":
        raise JobError(
            "edition_voice_refused",
            "edition ClientVoiceOnly at Plan: init voices seg-1 with a synthetic narrate job; write a voice-only"
            " job with --from FILE (a rendered NarratedVideo record)",
        )
    if avatar is None:
        avatar = (edition or d["edition"]) in AVATAR_EDITIONS
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
        "slides": None,
        "music": copy.deepcopy(d["music"]) | {"bed": bed} if bed else None,
        "tighten": copy.deepcopy(d["tighten"]),
        "captions": copy.deepcopy(d["captions"]),
        "labels": copy.deepcopy(d["labels"]) | ({"persona": persona} if persona else {}),
        "delivery": copy.deepcopy(d["delivery"]),
    }
    return check_shape(job)
