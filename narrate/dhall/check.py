"""Checks behind `just narrate-dhall-check` that need more than dhall: references, policy and drafts.

The example voice and consent in examples/ are bound to synthetic fixtures this script generates: a
ten-second 375 Hz sine (24 kHz mono, 16-bit PCM WAV), a fixture transcript and a fixture consent
statement. No real clip exists or is committed. The script regenerates them in memory and checks the
rendered example JSON carries their sha256.

It also checks every cross-reference a job depends on (engine, voice, speakers, pronunciation table,
consent record, scope, revocation, hosted and confidential refusals), using a port of
Engine.dhall's `consistent` and `mayRunConfidential`. It validates the models.json v2 drafts in
program/model-drafts/ against the draft schema and cross-checks their file lists and byte counts
with narrate/bench/sources.json.

It also checks the narrated-video examples (docs/spec/NARRATED_VIDEO.md): the music-bed records against two
generated E-major sine loops (48 kHz mono, 16-bit PCM WAV, 2 s and 3 s), the deck base against four
generated placeholder files, the slide pages against two generated slide pictures (320x180 RGB PNG, stored
deflate blocks so every zlib writes the same bytes), and every job against a port of Edition.dhall's `check` (at
the Plan point), the persona label rule, the tighten rule, the slide and avatarOff rules, the delivery gates and the
bounds the spec sets.

`--self-test` is the negative control: it mutates copies of the examples and drafts and expects
every mutation to be refused.

Usage: python3 -I narrate/dhall/check.py [--write-fixtures DIR] [--self-test]
Exit 0 when every check holds, 1 otherwise. Standard library only.
"""

import argparse
import copy
import functools
import hashlib
import io
import json
import math
import re
import struct
import sys
import wave
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "narrate" / "dhall" / "examples"
DRAFT_SCHEMA = ROOT / "program" / "model-drafts" / "models-v2.schema.json"
DRAFT_ENTRIES = ROOT / "program" / "model-drafts" / "narrate-tts-v2.json"
BENCH_SOURCES = ROOT / "narrate" / "bench" / "sources.json"

RATE_HZ = 24000
TONE_HZ = 375
SECONDS = 10
AMPLITUDE = 8192
REF_CLIP_SECONDS = (10, 30)
TEMPO_RANGE = (0.5, 2.0)  # Voice.dhall tempo; narrate/audio.py TEMPO_RANGE
FIXTURE_TEXT = "Synthetic sine fixture. This is not a voice and no person spoke it.\n"
FIXTURE_CONSENT = ("Fixture consent record for the synthetic sine voice used by narrate tests. "
                   "It grants nothing for any real speaker.\n")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
# Files a draft may leave out of a pinned snapshot's listing: model cards only.
OMITTABLE = {"README.md"}

# Engine.dhall, ported. Keep in step with Engine.dhall and policy-test.dhall.
PROFILE_BACKENDS = {
    "GpuSwitch": {"VulkanAudioCpp", "QwenTtsCpp", "LlamaTts"},
    "GpuDirect": {"VulkanAudioCpp", "QwenTtsCpp", "LlamaTts", "AudioCppBatch"},
    "MacMlx": {"MlxAudio"},
    "RentedOpen": {"RentedOpen"},
    "Hosted": {"Hosted"},
    "Fake": {"Fake"},
}


def is_hosted(engine: dict) -> bool:
    return bool(engine["hosted"]) or engine["profile"] == "Hosted" or engine["backend"] == "Hosted"


def is_rented(engine: dict) -> bool:
    return engine["profile"] == "RentedOpen" or engine["backend"] == "RentedOpen"


def consistent(engine: dict) -> bool:
    fits = engine["backend"] in PROFILE_BACKENDS.get(engine["profile"], set())
    return fits and bool(engine["hosted"]) == (engine["profile"] == "Hosted")


def may_run_confidential(engine: dict) -> bool:
    return (consistent(engine) and not is_hosted(engine) and bool(engine["confidentialAllowed"])
            and (not is_rented(engine) or bool(engine["estateControlled"])))


def sine_wav() -> bytes:
    """A deterministic 16-bit mono WAV. 64 samples per period, so the table repeats exactly."""
    period = RATE_HZ // TONE_HZ
    table = [round(AMPLITUDE * math.sin(2 * math.pi * k / period)) for k in range(period)]
    frames = b"".join(struct.pack("<h", table[n % period]) for n in range(RATE_HZ * SECONDS))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE_HZ)
        out.writeframes(frames)
    return buffer.getvalue()


# Bed loops: E-major triads at 48 kHz from whole-sample periods (146, 116 and 97 samples: about 329, 414 and
# 495 Hz, near E4, G#4 and B4), so each table repeats exactly. Loop A holds the triad 2 s; loop B the root and
# fifth 3 s.
BED_RATE_HZ = 48000
BED_LOOPS = {"bed-loop-a.wav": (2, (146, 116, 97)), "bed-loop-b.wav": (3, (146, 97))}
BED_AMPLITUDE = 2000
DECK_FIXTURES = {
    "deck-video.txt": "Synthetic deck video placeholder. No deck, slide or client material.\n",
    "deck-timeline.txt": "Synthetic deck timeline placeholder. No deck, slide or client material.\n",
    "deck-stems.txt": "Synthetic deck stems placeholder. No deck, slide or client material.\n",
    "deck-tighten-edits.txt": "Synthetic deck tighten-edits placeholder. No deck, slide or client material.\n",
}


def pcm_wav(rate: int, frames: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(frames)
    return buffer.getvalue()


def loop_wav(seconds: int, periods: tuple) -> bytes:
    """A deterministic chord: one exact table per period, summed. Never a recording."""
    tables = [[round(BED_AMPLITUDE * math.sin(2 * math.pi * k / p)) for k in range(p)] for p in periods]
    frames = b"".join(struct.pack("<h", sum(t[n % len(t)] for t in tables)) for n in range(BED_RATE_HZ * seconds))
    return pcm_wav(BED_RATE_HZ, frames)


# Slide pictures for the slides example: a light field with one dark bar, in two colourings. Synthetic shapes, no
# deck, slide or client material. 320x180 RGB, written with stored deflate blocks.
SLIDE_SIZE = (320, 180)
SLIDE_FIXTURES = {
    "slide-a.png": ((232, 228, 216), (40, 52, 70)),
    "slide-b.png": ((214, 228, 240), (90, 40, 60)),
}


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def stored_zlib(raw: bytes) -> bytes:
    """A zlib stream of stored (uncompressed) deflate blocks: the same bytes from every zlib implementation."""
    out = bytearray(b"\x78\x01")
    for start in range(0, max(len(raw), 1), 65535):
        block = raw[start : start + 65535]
        final = 1 if start + 65535 >= len(raw) else 0
        out += bytes([final]) + struct.pack("<HH", len(block), 0xFFFF ^ len(block)) + block
    return bytes(out) + struct.pack(">I", zlib.adler32(raw) & 0xFFFFFFFF)


def slide_png(field: tuple, bar: tuple) -> bytes:
    w, h = SLIDE_SIZE
    plain, f, b = b"\x00" + bytes(field) * w, bytes(field), bytes(bar)
    title = b"\x00" + f * 24 + b * (w - 48) + f * 24
    line = b"\x00" + f * 24 + b * (w // 2 - 24) + f * (w // 2)
    rows = [title if 24 <= y < 52 else line if 72 <= y < 80 else plain for y in range(h)]
    header = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", stored_zlib(b"".join(rows)))
        + png_chunk(b"IEND", b"")
    )


def fixtures() -> dict:
    """Every generated fixture by file name. Generated once per process (the self-test checks 79 mutations)."""
    return dict(_fixtures())


@functools.cache
def _fixtures() -> dict:
    files = {"sine.wav": sine_wav(), "ref.txt": FIXTURE_TEXT.encode(), "consent.txt": FIXTURE_CONSENT.encode()}
    files.update({name: loop_wav(*spec) for name, spec in BED_LOOPS.items()})
    files.update({name: text.encode() for name, text in DECK_FIXTURES.items()})
    files.update({name: slide_png(*colours) for name, colours in SLIDE_FIXTURES.items()})
    return files


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_examples() -> dict:
    tables = load_json(EXAMPLES / "pronunciation.json")
    return {
        "narrated_videos": load_json(EXAMPLES / "narrated-videos.json"),
        "music_beds": load_json(EXAMPLES / "music-beds.json"),
        "voices": load_json(EXAMPLES / "voices.json"),
        "consents": load_json(EXAMPLES / "consents.json"),
        "engines": load_json(EXAMPLES / "engines.json"),
        "jobs": load_json(EXAMPLES / "jobs.json"),
        "pronunciation": tables if isinstance(tables, list) else [tables],
        "script": (EXAMPLES / "script.md").read_bytes(),
    }


def check_voice_for_job(job: dict, voice_id: str, data: dict, engine, errors: list) -> None:
    voices = {v["id"]: v for v in data["voices"]}
    consents = {c["id"]: c for c in data["consents"]}
    where = f"examples: job {job['id']} voice {voice_id}"
    voice = voices.get(voice_id)
    if voice is None:
        errors.append(f"{where} is unknown")
        return
    consent = consents.get(voice["consentId"])
    if consent is None:
        errors.append(f"{where}: consent_missing ({voice['consentId']})")
        return
    if consent["revokedAt"] is not None:
        errors.append(f"{where}: consent_revoked ({consent['id']})")
    if voice["scope"] not in consent["scopes"]:
        errors.append(f"{where}: consent_scope (voice scope {voice['scope']} not granted)")
    if job["scope"] not in consent["scopes"]:
        errors.append(f"{where}: consent_scope (job scope {job['scope']} not granted)")
    if voice["scope"] != job["scope"]:
        errors.append(f"{where}: voice scope {voice['scope']} differs from job scope {job['scope']}")
    if job["engine"] not in voice["allowedEngines"]:
        errors.append(f"{where}: engine {job['engine']} is not in the voice's allowedEngines")
    if engine is not None and is_hosted(engine) and not consent["hostedAllowed"]:
        errors.append(f"{where}: hosted engine without the consent record's hostedAllowed")


def check_examples(data: dict, errors: list) -> None:
    files = fixtures()
    voices, consents, engines = data["voices"], data["consents"], data["engines"]
    if not [v for v in voices if v["fixture"]]:
        errors.append("examples: no fixture voice")
    consent_ids = {c["id"]: c for c in consents}
    for voice in voices:
        if voice["consentId"] not in consent_ids:
            errors.append(f"examples: voice {voice['id']} names no consent record")
        low, high = REF_CLIP_SECONDS
        if not low <= voice["refClipSeconds"] <= high:
            errors.append(f"examples: voice {voice['id']} reference clip is not {low} to {high} s")
        tempo = voice.get("tempo")
        if tempo is not None and (isinstance(tempo, bool) or not isinstance(tempo, (int, float))
                                  or not TEMPO_RANGE[0] <= tempo <= TEMPO_RANGE[1]):
            errors.append(f"examples: voice {voice['id']} tempo {tempo!r} is not {TEMPO_RANGE[0]} to {TEMPO_RANGE[1]}")
        if not voice["fixture"]:
            errors.append(f"examples: voice {voice['id']} is not a fixture; real voices live outside git")
            continue
        if voice["refClipSha256"] != sha(files["sine.wav"]):
            errors.append(f"examples: voice {voice['id']} refClipSha256 is not the generated sine")
        if voice["refTextSha256"] != sha(files["ref.txt"]):
            errors.append(f"examples: voice {voice['id']} refTextSha256 is not the fixture transcript")
        if voice["refClipSampleRateHz"] != RATE_HZ or voice["refClipSeconds"] != SECONDS:
            errors.append(f"examples: voice {voice['id']} rate or duration differs from the fixture")
        consent = consent_ids.get(voice["consentId"], {})
        if consent.get("evidenceSha256") != sha(files["consent.txt"]):
            errors.append(f"examples: consent {voice['consentId']} evidence is not the fixture statement")

    engine_ids = {e["id"]: e for e in engines}
    for engine in engines:
        if engine["backend"] != "Fake" or engine["profile"] != "Fake" or is_hosted(engine):
            errors.append(f"examples: engine {engine['id']} is not the fake engine; real engines live outside git")
        if not consistent(engine):
            errors.append(f"examples: engine {engine['id']} profile {engine['profile']} and backend "
                          f"{engine['backend']} disagree")
        for item in engine["files"]:
            if not SHA256.match(item.get("sha256", "")):
                errors.append(f"examples: engine {engine['id']} file {item.get('path')} sha256 is not hex")

    table_ids = {t["id"] for t in data["pronunciation"]}
    for job in data["jobs"]:
        if job["inputSha256"] != sha(data["script"]):
            errors.append(f"examples: job {job['id']} inputSha256 is not examples/script.md")
        if job["pronunciation"] not in table_ids:
            errors.append(f"examples: job {job['id']} pronunciation table {job['pronunciation']} is unknown")
        engine = engine_ids.get(job["engine"])
        if engine is None:
            errors.append(f"examples: job {job['id']} engine {job['engine']} is unknown")
        else:
            if job["confidential"] and not may_run_confidential(engine):
                errors.append(f"examples: job {job['id']}: confidential_engine_refused ({engine['id']})")
            if is_hosted(engine) and not job["allowHosted"]:
                errors.append(f"examples: job {job['id']}: hosted engine {engine['id']} without allowHosted")
            if not consistent(engine):
                errors.append(f"examples: job {job['id']} engine {engine['id']} is inconsistent")
        for voice_id in [job["voice"]] + [s["voice"] for s in job["speakers"]]:
            check_voice_for_job(job, voice_id, data, engine, errors)


# Edition.dhall and NarratedVideo.dhall, ported. Keep in step with them and narrated-video-test.dhall.
EDITIONS = ("Internal", "OwnContent", "ClientVoiceOnly", "ClientNarrated")
CLIENT_EDITIONS = ("ClientVoiceOnly", "ClientNarrated")
# Edition.clientDefault and NarratedVideo.defaults.clientEdition: a client delivery is ClientNarrated (NV-6, TIN-7476
# comment 92605219) unless its project picks ClientVoiceOnly.
CLIENT_DEFAULT_EDITION = "ClientNarrated"
POINTS = ("Plan", "Place", "DeliverCheck")
EDITION_REFUSALS = {"VoiceRefused": "edition_voice_refused", "PipRefused": "edition_pip_refused",
                    "BedRefused": "edition_bed_refused"}
LEAVES = ("syntheticVoice", "avatar", "pip", "bed", "bedCleared")
NV_BOUNDS = {"avatar.width": (0.10, 0.30), "music.bedBelowVoiceLu": (10.0, 30.0), "music.duckDb": (0.0, 12.0),
             "avatar.fadeS": (0.0, 2.0), "slides.cardWidth": (0.25, 0.60), "slides.fadeS": (0.0, 2.0),
             "slides.dimTo": (0.0, 1.0)}
SLIDE_LAYOUTS = ("Full", "CardLowerLeft")
NV_DRIFT_MAX_LU = 0.5
NV_TRUE_PEAK_MAX_DBTP = -1.5
BED_LAYERS = (2, 3)
BED_TEMPO_RANGE = (0.5, 2.0)


def edition_check(point: str, edition: str, leaves: dict) -> dict:
    """Edition.check: the one rule the Plan, Place and DeliverCheck points run, each over its own leaves."""
    if point not in POINTS or edition not in EDITIONS or set(leaves) != set(LEAVES):
        raise ValueError(f"edition_check: bad point {point!r}, edition {edition!r} or leaves {sorted(leaves)}")
    codes = []
    if edition == "ClientVoiceOnly":
        if leaves["syntheticVoice"]:
            codes.append("VoiceRefused")
        if leaves["avatar"] or leaves["pip"]:
            codes.append("PipRefused")
    elif edition in CLIENT_EDITIONS and leaves["pip"]:
        codes.append("PipRefused")
    if edition in CLIENT_EDITIONS and leaves["bed"] and not leaves["bedCleared"]:
        codes.append("BedRefused")
    if not codes:
        return {"verdict": "Admitted"}
    return {"verdict": "Refused", "point": point, "codes": codes}


def client_edition(project_edition=None) -> str:
    """The edition of a client delivery: CLIENT_DEFAULT_EDITION, or the client edition its project picks."""
    if project_edition is None:
        return CLIENT_DEFAULT_EDITION
    if project_edition not in CLIENT_EDITIONS:
        raise ValueError(f"client_edition: {project_edition!r} is not a client edition")
    return project_edition


def bed_licence_cleared(bed: dict) -> bool:
    """MusicBed.licenceCleared: a certified licence PDF digest and a clear Content ID result."""
    content_id = bed["licence"]["contentIdCheck"]
    return bed["licence"]["certifiedPdfSha256"] is not None and isinstance(content_id, dict) and "clear" in content_id


def avatar_on(job: dict) -> bool:
    return job["avatar"] is not None and any(s["avatar"] for s in job["segments"])


def plan_leaves(job: dict, bed) -> dict:
    """NarratedVideo.planLeaves. `bed` is the resolved record the job's music names, or None. A job has no camera
    field, so pip is False at Plan; Place reads camera picture-in-picture from a deck's stems."""
    return {"syntheticVoice": bool(job["segments"]), "avatar": job["avatar"] is not None, "pip": False,
            "bed": job["music"] is not None,
            "bedCleared": bed is not None and bed_licence_cleared(bed)
            and job["delivery"]["voiceOnlyListen"] is not None}


def within(value, bounds) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and bounds[0] <= value <= bounds[1]


def check_music_beds(data: dict, errors: list) -> None:
    files = fixtures()
    loops = {sha(files[name]): (name, len(files[name])) for name in BED_LOOPS}
    for bed in data["music_beds"]:
        where = f"examples: music bed {bed['id']}"
        if bed["acquisition"]["acquiredBy"] != "Operator":
            errors.append(f"{where}: bed_acquisition_agent ({bed['acquisition']['acquiredBy']!r})")
        if not bed["acquisition"]["rulingRef"]:
            errors.append(f"{where}: acquisition names no ruling")
        layers = bed["layers"]
        if not BED_LAYERS[0] <= len(layers) <= BED_LAYERS[1]:
            errors.append(f"{where}: bed_layers_invalid ({len(layers)} layers; a bed arranges 2 or 3 loops)")
        if len({layer["sha256"] for layer in layers}) != len(layers):
            errors.append(f"{where}: bed_layers_invalid (a loop is layered twice)")
        for layer in layers:
            if not within(layer["tempoFactor"], BED_TEMPO_RANGE):
                errors.append(f"{where}: tempoFactor {layer['tempoFactor']!r} is not 0.5 to 2.0")
            if layer["source"] != "Fixture":
                errors.append(f"{where}: layer source {layer['source']} is not Fixture; real beds live outside git")
                continue
            loop = loops.get(layer["sha256"])
            if loop is None:
                errors.append(f"{where}: bed_digest_mismatch (layer {layer['sha256'][:12]} is no generated loop)")
            elif (layer["bytes"], layer["rateHz"], layer["channels"]) != (loop[1], BED_RATE_HZ, 1):
                errors.append(f"{where}: layer {loop[0]} bytes, rate or channels differ from the fixture")
        licence = bed["licence"]
        pdf = licence["certifiedPdfSha256"]
        if pdf is not None and not SHA256.match(pdf):
            errors.append(f"{where}: certifiedPdfSha256 is not hex")
        content_id = licence["contentIdCheck"]
        if content_id != "NotRun" and not (isinstance(content_id, dict) and len(content_id) == 1
                                           and set(content_id) <= {"clear", "claimed"}):
            errors.append(f"{where}: contentIdCheck {content_id!r} is not NotRun, clear or claimed")


def check_base(nv: dict, where: str, files: dict, errors: list) -> None:
    base = nv["base"]
    if not isinstance(base, dict) or len(base) != 1 or next(iter(base)) not in ("still", "card", "video", "deck"):
        errors.append(f"{where}: base {base!r} is not one of still, card, video or deck")
        return
    kind, body = next(iter(base.items()))
    if kind in ("still", "video") and not SHA256.match(body["sha256"]):
        errors.append(f"{where}: {kind} sha256 is not hex")
    if kind in ("still", "card") and (body["fps"]["num"] < 1 or body["fps"]["den"] < 1 or body["tailS"] < 0):
        errors.append(f"{where}: {kind} fps or tailS is invalid")
    if kind == "deck":
        for field, name in (("videoSha256", "deck-video.txt"), ("timelineSha256", "deck-timeline.txt"),
                            ("stemsSha256", "deck-stems.txt")):
            if body[field] != sha(files[name]):
                errors.append(f"{where}: deck {field} is not the generated {name}")
        edits = body["tightenEditsSha256"]
        if edits is not None and edits != sha(files["deck-tighten-edits.txt"]):
            errors.append(f"{where}: deck tightenEditsSha256 is not the generated deck-tighten-edits.txt")
        if edits is not None and nv["segments"] and not nv["tighten"]["enabled"]:
            errors.append(f"{where}: tighten_on_synthetic (tighten edits on narrate segments need tighten.enabled; "
                          "it is off by default, NV-2)")


def slides_problems(nv: dict) -> list:
    """The ways a job's slides block and avatarOff list break the slide rules (docs/spec/NARRATED_VIDEO.md,
    "Slides"): ordered, non-overlapping pages with unique ids, each slide page at least two fades long, the
    layout bounds, and avatarOff naming only pages the job defines. A deck base brings its own pages (lane L8),
    so avatarOff is not checked against it here. Each problem is (code, text): slides_invalid, page_unknown or
    knob_out_of_bounds, the codes admit refuses with (narrate/video/admit.py)."""
    out = []

    def bad(text, code="slides_invalid"):
        out.append((code, text))

    slides, avatar = nv.get("slides"), nv.get("avatar")
    pages = (slides or {}).get("pages") or []
    if slides is not None:
        if slides["layout"] not in SLIDE_LAYOUTS:
            bad(f"slides layout {slides['layout']!r} is not one of {', '.join(SLIDE_LAYOUTS)}")
        for key in ("cardWidth", "fadeS", "dimTo"):
            low, high = NV_BOUNDS[f"slides.{key}"]
            value = slides[key]
            if not within(value, NV_BOUNDS[f"slides.{key}"]) or (key == "fadeS" and value == 0):
                bad(f"slides {key} {value!r} is not {low} to {high}", "knob_out_of_bounds")
        ids = [p["id"] for p in pages]
        if len(set(ids)) != len(ids):
            bad("slides page ids repeat")
        if not pages:
            bad("slides has no pages")
        previous_end = 0.0
        for page in pages:
            if not 0 <= page["startS"] < page["endS"]:
                bad(f"slides page {page['id']} does not start at or after 0 and end after its start")
            if page["startS"] < previous_end - 1e-9:
                bad(f"slides page {page['id']} starts before the previous page ends")
            previous_end = max(previous_end, page["endS"])
            show = page["show"]
            if isinstance(show, dict) and set(show) == {"slide"}:
                if not SHA256.match(show["slide"]["sha256"]):
                    bad(f"slides page {page['id']} slide sha256 is not hex")
                if page["endS"] - page["startS"] < 2 * slides["fadeS"]:
                    bad(f"slides page {page['id']} is shorter than two fades")
            elif show not in ("Base", "Hold"):
                bad(f"slides page {page['id']} show {show!r} is not Base, Hold or a slide")
    if avatar is not None:
        if not within(avatar["fadeS"], NV_BOUNDS["avatar.fadeS"]):
            bad(f"avatar fadeS {avatar['fadeS']!r} is not 0.0 to 2.0", "knob_out_of_bounds")
        known = {p["id"] for p in pages}
        unknown = sorted(set(avatar["avatarOff"]) - known)
        if unknown and "deck" not in nv["base"]:
            bad(f"avatarOff names {len(unknown)} pages the job does not define", "page_unknown")
    return out


def check_narrated_videos(data: dict, errors: list) -> None:
    files = fixtures()
    jobs = {j["id"]: j for j in data["jobs"]}
    voices = {v["id"]: v for v in data["voices"]}
    consents = {c["id"]: c for c in data["consents"]}
    beds = {b["id"]: b for b in data["music_beds"]}
    ids = [nv["id"] for nv in data["narrated_videos"]]
    if len(set(ids)) != len(ids):
        errors.append("examples: narrated-video ids repeat")
    for edition in CLIENT_EDITIONS:
        if edition not in {nv["edition"] for nv in data["narrated_videos"]}:
            errors.append(f"examples: no {edition} narrated video")
    for nv in data["narrated_videos"]:
        where = f"examples: narrated video {nv['id']}"
        if nv["edition"] not in EDITIONS:
            errors.append(f"{where}: edition {nv['edition']!r} is unknown")
            continue
        if not isinstance(nv["tighten"], dict) or not isinstance(nv["tighten"].get("enabled"), bool):
            errors.append(f"{where}: tighten {nv['tighten']!r} is not {{enabled: bool}}")
            continue
        check_base(nv, where, files, errors)
        segment_ids = [s["id"] for s in nv["segments"]]
        if len(set(segment_ids)) != len(segment_ids):
            errors.append(f"{where}: segment ids repeat")
        personas = set()
        for segment in nv["segments"]:
            job = jobs.get(segment["narrateJob"])
            if job is None:
                errors.append(f"{where}: segment {segment['id']} narrate job {segment['narrateJob']} is unknown")
                continue
            if segment["scriptSha256"] != job["inputSha256"]:
                errors.append(f"{where}: segment {segment['id']} scriptSha256 is not its job's input")
            anchor = segment["anchor"]
            if anchor != "Auto" and not (isinstance(anchor, dict) and len(anchor) == 1
                                         and set(anchor) <= {"atSeconds", "page"}):
                errors.append(f"{where}: segment {segment['id']} anchor {anchor!r} is invalid")
            for voice_id in [job["voice"]] + [s["voice"] for s in job["speakers"]]:
                consent = consents.get(voices.get(voice_id, {}).get("consentId"))
                if consent is not None and consent.get("persona") is not None:
                    personas.add(consent["persona"])
        labels = nv["labels"]
        if avatar_on(nv) and labels["persona"] is None:
            errors.append(f"{where}: persona_label_missing (an avatar is on)")
        for persona in sorted(personas):
            if labels["persona"] != persona:
                errors.append(f"{where}: persona_label_missing (a voice's consent names a persona the labels lack)")
        if nv["avatar"] is not None:
            if nv["avatar"]["external"] != "kitpip":
                errors.append(f"{where}: avatar external {nv['avatar']['external']!r} is not kitpip")
            if not within(nv["avatar"]["width"], NV_BOUNDS["avatar.width"]):
                errors.append(f"{where}: avatar width {nv['avatar']['width']!r} is not 0.10 to 0.30")
        for _, problem in slides_problems(nv):
            errors.append(f"{where}: {problem}")
        for page in (nv.get("slides") or {}).get("pages") or []:
            show = page["show"]
            if isinstance(show, dict) and "slide" in show:
                if show["slide"]["sha256"] not in {sha(files[n]) for n in SLIDE_FIXTURES}:
                    errors.append(f"{where}: slides page {page['id']} is not a generated slide fixture")
        bed = None
        if nv["music"] is not None:
            music = nv["music"]
            bed = beds.get(music["bed"])
            if bed is None:
                errors.append(f"{where}: bed_record_missing ({music['bed']})")
            for key in ("bedBelowVoiceLu", "duckDb"):
                if not within(music[key], NV_BOUNDS[f"music.{key}"]) or (key == "duckDb" and music[key] == 0):
                    errors.append(f"{where}: music {key} {music[key]!r} is out of bounds")
            if min(music["fadeInS"], music["fadeOutS"], music["tailS"]) < 0:
                errors.append(f"{where}: music fades and tail must not be negative")
        delivery = nv["delivery"]
        if not 0 < delivery["driftLu"] <= NV_DRIFT_MAX_LU:
            errors.append(f"{where}: driftLu {delivery['driftLu']!r} is not above 0 and at most 0.5")
        if delivery["truePeakDbtp"] > NV_TRUE_PEAK_MAX_DBTP:
            errors.append(f"{where}: truePeakDbtp {delivery['truePeakDbtp']!r} is above -1.5")
        verdict = edition_check("Plan", nv["edition"], plan_leaves(nv, bed))
        if verdict["verdict"] != "Admitted":
            refusals = ", ".join(EDITION_REFUSALS[c] for c in verdict["codes"])
            errors.append(f"{where}: refused at Plan: {refusals}")


def validate(value, schema: dict, root: dict, where: str, errors: list) -> None:
    """The JSON Schema subset the v2 draft schema uses: $ref, oneOf, const, enum, type, pattern,
    minLength, minimum, required, properties, additionalProperties false, items and minItems."""
    if "$ref" in schema:
        node = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            node = node[part]
        validate(value, node, root, where, errors)
        return
    if "oneOf" in schema:
        matches = 0
        for option in schema["oneOf"]:
            trial: list = []
            validate(value, option, root, where, trial)
            matches += not trial
        if matches != 1:
            errors.append(f"{where}: {value!r} matches {matches} of the oneOf options, not exactly one")
        return
    if "const" in schema and value != schema["const"]:
        errors.append(f"{where}: {value!r} is not {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{where}: {value!r} is not one of {schema['enum']}")
    if "type" in schema:
        kinds = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        checks = {
            "string": lambda v: isinstance(v, str),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
            "null": lambda v: v is None,
            "object": lambda v: isinstance(v, dict),
            "array": lambda v: isinstance(v, list),
        }
        if not any(checks[k](value) for k in kinds):
            errors.append(f"{where}: {value!r} is not of type {kinds}")
            return
    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{where}: {value!r} does not match {schema['pattern']}")
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{where}: {value!r} is shorter than {schema['minLength']}")
    if isinstance(value, (int, float)) and "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{where}: {value!r} is below {schema['minimum']}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{where}: lacks {key}")
        properties = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties:
                validate(item, properties[key], root, f"{where}.{key}", errors)
            elif extra is False:
                errors.append(f"{where}: unexpected key {key}")
            elif isinstance(extra, dict):
                validate(item, extra, root, f"{where}.{key}", errors)
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{where}: has fewer than {schema['minItems']} items")
        if "items" in schema:
            for index, item in enumerate(value):
                validate(item, schema["items"], root, f"{where}[{index}]", errors)


def cross_check_sources(model_id: str, serving: dict, sources: dict, errors: list) -> None:
    """A draft file list must be the bench lane's listing of the same snapshot, minus model cards,
    with the same byte counts, and a bound sha256 must equal the Hub-declared one."""
    where = f"drafts: {model_id} {serving.get('hf_repo')}"
    source = sources.get((serving.get("hf_repo"), serving.get("hf_revision")))
    if source is None:
        errors.append(f"{where}@{serving.get('hf_revision')} is not in narrate/bench/sources.json")
        return
    listed = {f["path"]: f for f in source["files"]}
    drafted = {f.get("path"): f for f in serving.get("files", [])}
    for path, item in drafted.items():
        if path not in listed:
            errors.append(f"{where}: {path} is not in the bench listing")
            continue
        if item.get("bytes") != listed[path]["bytes"]:
            errors.append(f"{where}: {path} bytes {item.get('bytes')} differ from the bench listing "
                          f"{listed[path]['bytes']}")
        digest, declared = item.get("sha256"), listed[path].get("sha256")
        if digest != "pending" and declared is not None and digest != declared:
            errors.append(f"{where}: {path} sha256 differs from the Hub-declared digest")
    for path in sorted(set(listed) - set(drafted) - OMITTABLE):
        errors.append(f"{where}: lacks {path}, which the bench listing has")
    stated = (source.get("converted_from") or {}).get("revision")
    if stated is not None and (serving.get("upstream") or {}).get("revision") != stated:
        errors.append(f"{where}: upstream revision is not the conversion's stated source {stated}")


def check_drafts(schema: dict, draft: dict, bench: dict, errors: list) -> None:
    validate(draft, schema, schema, "drafts", errors)
    sources = {(s["repo"], s["revision"]): s for s in bench.get("sources", []) if s.get("kind") == "hf"}
    for model_id, entry in draft.get("models", {}).items():
        if not isinstance(entry, dict):
            continue
        cross_check_sources(model_id, entry, sources, errors)
        for variant in entry.get("variants", []):
            if isinstance(variant, dict):
                cross_check_sources(model_id, variant, sources, errors)
        serving = [entry] + [v for v in entry.get("variants", []) if isinstance(v, dict)]
        pending = any(f.get("sha256") == "pending" for s in serving for f in s.get("files", []))
        if entry.get("gate_state") == "registered" and pending:
            errors.append(f"drafts: {model_id} is registered with a pending hash")


def run_checks(data: dict, schema: dict, draft: dict, bench: dict) -> list:
    errors: list = []
    for name, step in (("examples", lambda: check_examples(data, errors)),
                       ("music beds", lambda: check_music_beds(data, errors)),
                       ("narrated videos", lambda: check_narrated_videos(data, errors)),
                       ("drafts", lambda: check_drafts(schema, draft, bench, errors))):
        try:
            step()
        except (KeyError, TypeError, AttributeError) as exc:
            errors.append(f"{name}: malformed input ({type(exc).__name__}: {exc})")
    return errors


def mutations() -> list:
    """(name, mutate(data, draft)) pairs. Each must make run_checks report at least one error."""
    def job(d):
        return d["jobs"][0]

    def voice(d):
        return d["voices"][0]

    def consent(d):
        return d["consents"][0]

    def entry(m, model_id="ming-3.0-tts-0.5b-gguf-bf16"):
        return m["models"][model_id]

    def variant(m):
        return entry(m)["variants"][0]

    hosted_engine = {"id": "probe-hosted", "profile": "GpuDirect", "backend": "Hosted", "hosted": False,
                     "confidentialAllowed": True, "estateControlled": True}
    rented_engine = {"id": "probe-rented", "profile": "MacMlx", "backend": "RentedOpen", "hosted": False,
                     "confidentialAllowed": True, "estateControlled": False}
    switch_batch = {"id": "probe-batch", "profile": "GpuSwitch", "backend": "AudioCppBatch", "hosted": False,
                    "endpoint": "audiocpp://voxcpm2", "confidentialAllowed": True, "estateControlled": True}

    def with_engine(probe, confidential):
        def mutate(d, m):
            d["engines"].append({**d["engines"][0], **probe})
            job(d)["engine"] = probe["id"]
            job(d)["confidential"] = confidential
            voice(d)["allowedEngines"].append(probe["id"])
        return mutate

    return [
        ("job engine unknown", lambda d, m: job(d).update(engine="no-such-engine")),
        ("job pronunciation table unknown", lambda d, m: job(d).update(pronunciation="no-such-table")),
        ("job voice unknown", lambda d, m: job(d).update(voice="no-such-voice")),
        ("engine not allowed for voice", lambda d, m: voice(d).update(allowedEngines=["no-such-engine"])),
        ("consent revoked", lambda d, m: consent(d).update(revokedAt="2026-10-23")),
        ("voice scope not granted", lambda d, m: voice(d).update(scope="ClientDisclosed")),
        ("job scope not granted", lambda d, m: job(d).update(scope="ClientDisclosed")),
        ("voice names no consent", lambda d, m: voice(d).update(consentId="no-such-consent")),
        ("voice tempo out of range", lambda d, m: voice(d).update(tempo=0.4)),
        ("unmapped dialog speaker voice", lambda d, m: job(d).update(
            speakers=[{"speaker": "B", "voice": "no-such-voice"}])),
        ("reference clip too short", lambda d, m: voice(d).update(refClipSeconds=1.0)),
        ("non-fixture voice in git", lambda d, m: voice(d).update(fixture=False)),
        ("fake backend on a non-fake profile", lambda d, m: d["engines"][0].update(profile="GpuDirect")),
        ("hosted backend behind a local profile, confidential", with_engine(hosted_engine, True)),
        ("rented backend behind the Mac profile, confidential", with_engine(rented_engine, True)),
        ("audio.cpp batch behind the switch profile, confidential", with_engine(switch_batch, True)),
        ("hosted engine without allowHosted", with_engine(
            {**hosted_engine, "id": "probe-h2", "profile": "Hosted", "hosted": True}, False)),
        ("fixture digest changed", lambda d, m: voice(d).update(refClipSha256="0" * 64)),
        ("draft hf_revision short", lambda d, m: entry(m).update(hf_revision="abc")),
        ("draft kind invalid", lambda d, m: entry(m).update(kind="music")),
        ("draft gate_state invalid", lambda d, m: entry(m).update(gate_state="approved")),
        ("draft links empty", lambda d, m: entry(m).update(links=[])),
        ("draft runtime commit short", lambda d, m: entry(m)["runtime"].update(commit="abc123")),
        ("variant hf_revision invalid", lambda d, m: variant(m).update(hf_revision="zz")),
        ("variant lacks runtime", lambda d, m: variant(m).pop("runtime")),
        ("variant lacks vocab.json", lambda d, m: variant(m).update(
            files=[f for f in variant(m)["files"] if f["path"] != "vocab.json"])),
        ("draft bytes differ from bench", lambda d, m: entry(m)["files"][0].update(bytes=1)),
        ("draft sha256 malformed", lambda d, m: entry(m)["files"][0].update(sha256="abc")),
        ("draft upstream revision missing", lambda d, m: entry(m, "fish-audio-drama-3")["variants"][0].pop(
            "upstream")),
        ("registered with pending hashes", lambda d, m: entry(m).update(gate_state="registered")),
        ("draft unexpected key", lambda d, m: entry(m).update(sha256_list=[])),
    ] + narrated_video_mutations()


def narrated_video_mutations() -> list:
    """(name, mutate(data, draft)) pairs for the music-bed and narrated-video examples."""
    def nv(d, nv_id):
        return next(x for x in d["narrated_videos"] if x["id"] == nv_id)

    def bed(d):
        return d["music_beds"][0]

    def layer(d):
        return bed(d)["layers"][0]

    def client(d):
        return nv(d, "nv-fixture-client-deck")

    def card(d):
        return nv(d, "nv-fixture-card")

    def clear_bed(d):
        bed(d)["licence"].update(certifiedPdfSha256="f" * 64, contentIdCheck={"clear": "probe-receipt"})

    def client_with(**fields):
        def mutate(d, m):
            client(d).update({k: copy.deepcopy(v(d)) for k, v in fields.items()})
        return mutate

    def client_cleared_bed_without_listen(d, m):
        clear_bed(d)
        client(d).update(music=copy.deepcopy(card(d)["music"]))

    def narrated(d):
        return nv(d, "nv-fixture-client-narrated")

    def client_narrated_bed(d, m):
        narrated(d).update(music=copy.deepcopy(card(d)["music"]))

    def client_narrated_cleared_bed_without_listen(d, m):
        clear_bed(d)
        client_narrated_bed(d, m)

    def persona_differs(d, m):
        d["consents"][0].update(persona="fixture-persona-other")

    def slides(d):
        return nv(d, "nv-fixture-slides")["slides"]

    def page(d, i):
        return slides(d)["pages"][i]

    return [
        ("bed acquired by an agent", lambda d, m: bed(d)["acquisition"].update(acquiredBy="Agent")),
        ("bed of one loop as-is", lambda d, m: bed(d).update(layers=bed(d)["layers"][:1])),
        ("bed layers one loop twice", lambda d, m: bed(d)["layers"][1].update(sha256=layer(d)["sha256"])),
        ("bed loop digest changed", lambda d, m: layer(d).update(sha256="0" * 64)),
        ("bed loop bytes changed", lambda d, m: layer(d).update(bytes=1)),
        ("bed loop not a fixture in git", lambda d, m: layer(d).update(source="Splice")),
        ("bed tempoFactor out of range", lambda d, m: layer(d).update(tempoFactor=2.5)),
        ("bed content id malformed", lambda d, m: bed(d)["licence"].update(contentIdCheck="Clear")),
        ("bed acquisition without ruling", lambda d, m: bed(d)["acquisition"].update(rulingRef="")),
        ("client edition with a synthetic segment", client_with(segments=lambda d: card(d)["segments"])),
        ("client edition with an avatar block", client_with(
            avatar=lambda d: nv(d, "nv-fixture-avatar")["avatar"])),
        ("client edition with an uncleared bed", client_with(music=lambda d: card(d)["music"])),
        ("client edition with a cleared bed and no voice-only listen", client_cleared_bed_without_listen),
        ("tighten edits on synthetic narration with tighten off",
         lambda d, m: narrated(d).update(tighten={"enabled": False})),
        ("tighten edits digest changed", lambda d, m: narrated(d)["base"]["deck"].update(tightenEditsSha256="e" * 64)),
        ("tighten knob malformed", lambda d, m: card(d).update(tighten=True)),
        ("client narrated with an uncleared bed", client_narrated_bed),
        ("client narrated with a cleared bed and no voice-only listen", client_narrated_cleared_bed_without_listen),
        ("deck digest changed", lambda d, m: client(d)["base"]["deck"].update(stemsSha256="0" * 64)),
        ("base kind unknown", lambda d, m: card(d).update(base={"slides": {}})),
        ("segment narrate job unknown", lambda d, m: card(d)["segments"][0].update(narrateJob="no-such-job")),
        ("segment script digest wrong", lambda d, m: card(d)["segments"][0].update(scriptSha256="0" * 64)),
        ("segment anchor malformed", lambda d, m: card(d)["segments"][0].update(anchor={"at": 1})),
        ("bed record missing", lambda d, m: card(d)["music"].update(bed="no-such-bed")),
        ("avatar without a persona label", lambda d, m: nv(d, "nv-fixture-avatar")["labels"].update(persona=None)),
        ("consent persona the labels lack", persona_differs),
        ("avatar external not kitpip", lambda d, m: nv(d, "nv-fixture-avatar")["avatar"].update(external="x")),
        ("avatar width out of range", lambda d, m: nv(d, "nv-fixture-avatar")["avatar"].update(width=0.4)),
        ("duck above 12 dB", lambda d, m: card(d)["music"].update(duckDb=13.0)),
        ("bed level out of range", lambda d, m: card(d)["music"].update(bedBelowVoiceLu=5.0)),
        ("drift gate loosened", lambda d, m: card(d)["delivery"].update(driftLu=0.6)),
        ("true peak above -1.5 dBTP", lambda d, m: card(d)["delivery"].update(truePeakDbtp=-1.0)),
        ("edition unknown", lambda d, m: card(d).update(edition="Public")),
        ("no ClientVoiceOnly example", lambda d, m: client(d).update(edition="Internal")),
        ("no ClientNarrated example", lambda d, m: narrated(d).update(edition="Internal")),
        ("slide layout unknown", lambda d, m: slides(d).update(layout="Corner")),
        ("slide card width out of range", lambda d, m: slides(d).update(cardWidth=0.9)),
        ("slide fade of zero", lambda d, m: slides(d).update(fadeS=0)),
        ("slide dim above 1", lambda d, m: slides(d).update(dimTo=1.5)),
        ("slide pages without pages", lambda d, m: slides(d).update(pages=[])),
        ("slide page ids repeat", lambda d, m: page(d, 1).update(id=page(d, 0)["id"])),
        ("slide pages overlap", lambda d, m: page(d, 1).update(startS=1.5)),
        ("slide page ends before it starts", lambda d, m: page(d, 2).update(endS=3.0)),
        ("slide page shorter than two fades", lambda d, m: page(d, 0).update(endS=0.5)),
        ("slide picture not a fixture", lambda d, m: page(d, 0)["show"]["slide"].update(sha256="0" * 64)),
        ("slide page show unknown", lambda d, m: page(d, 3).update(show="Blank")),
        ("avatarOff names an unknown page", lambda d, m: nv(d, "nv-fixture-slides")["avatar"].update(
            avatarOff=["no-such-page"])),
        ("avatar fade out of range", lambda d, m: nv(d, "nv-fixture-slides")["avatar"].update(fadeS=3.0)),
    ]


def self_test(data: dict, schema: dict, draft: dict, bench: dict) -> list:
    errors = []
    baseline = run_checks(data, schema, draft, bench)
    if baseline:
        errors.append(f"self-test: the committed inputs fail {len(baseline)} checks; fix them first")
        return errors
    for name, mutate in mutations():
        d, m = copy.deepcopy(data), copy.deepcopy(draft)
        mutate(d, m)
        if not run_checks(d, schema, m, bench):
            errors.append(f"self-test: mutation '{name}' was not refused")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write-fixtures", type=Path, help="also write the fixtures into this directory")
    parser.add_argument("--self-test", action="store_true", help="run the negative controls instead")
    args = parser.parse_args()
    if args.write_fixtures:
        args.write_fixtures.mkdir(parents=True, exist_ok=True)
        for name, data in fixtures().items():
            (args.write_fixtures / name).write_bytes(data)
    inputs = (load_examples(), load_json(DRAFT_SCHEMA), load_json(DRAFT_ENTRIES), load_json(BENCH_SOURCES))
    if args.self_test:
        errors = self_test(*inputs)
        for line in errors:
            print(line, file=sys.stderr)
        print(json.dumps({"ok": not errors, "self_test_mutations": len(mutations()), "errors": len(errors)},
                         sort_keys=True))
        return 1 if errors else 0
    errors = run_checks(*inputs)
    if sine_wav() != sine_wav():
        errors.append("fixtures: the sine is not deterministic")
    for line in errors:
        print(line, file=sys.stderr)
    print(json.dumps({"ok": not errors, "errors": len(errors),
                      "fixtures": {name: sha(data) for name, data in fixtures().items()}}, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
