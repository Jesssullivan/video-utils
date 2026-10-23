"""Checks behind `just narrate-dhall-check` that need more than dhall: fixture digests and model drafts.

The example voice and consent in examples/ are bound to synthetic fixtures this script generates: a
one-second 375 Hz sine (24 kHz mono, 16-bit PCM WAV), a fixture transcript and a fixture consent
statement. No real clip exists or is committed. The script regenerates them in memory and
checks the rendered example JSON carries their sha256. It also checks the models.json v2 drafts in
program/model-drafts/ against the draft schema's required fields.

Usage: python3 -I narrate/dhall/check.py [--write-fixtures DIR]
Exit 0 when every check holds, 1 otherwise. Standard library only.
"""

import argparse
import hashlib
import io
import json
import math
import re
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "narrate" / "dhall" / "examples"
DRAFT_SCHEMA = ROOT / "program" / "model-drafts" / "models-v2.schema.json"
DRAFT_ENTRIES = ROOT / "program" / "model-drafts" / "narrate-tts-v2.json"

RATE_HZ = 24000
TONE_HZ = 375
SECONDS = 1
AMPLITUDE = 8192
FIXTURE_TEXT = "Synthetic sine fixture. This is not a voice and no person spoke it.\n"
FIXTURE_CONSENT = ("Fixture consent record for the synthetic sine voice used by narrate tests. "
                   "It grants nothing for any real speaker.\n")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
BACKENDS = {"VulkanAudioCpp", "QwenTtsCpp", "LlamaTts", "MlxAudio", "RentedOpen", "Hosted", "Fake"}


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


def fixtures() -> dict:
    return {"sine.wav": sine_wav(), "ref.txt": FIXTURE_TEXT.encode(), "consent.txt": FIXTURE_CONSENT.encode()}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_examples(errors: list) -> None:
    files = fixtures()
    voices = json.loads((EXAMPLES / "voices.json").read_text(encoding="utf-8"))
    consents = json.loads((EXAMPLES / "consents.json").read_text(encoding="utf-8"))
    fixture_voices = [v for v in voices if v["fixture"]]
    if not fixture_voices:
        errors.append("examples: no fixture voice")
    consent_ids = {c["id"]: c for c in consents}
    for voice in voices:
        if voice["consentId"] not in consent_ids:
            errors.append(f"examples: voice {voice['id']} names no consent record")
        if voice["fixture"]:
            if voice["refClipSha256"] != sha(files["sine.wav"]):
                errors.append(f"examples: voice {voice['id']} refClipSha256 is not the generated sine")
            if voice["refTextSha256"] != sha(files["ref.txt"]):
                errors.append(f"examples: voice {voice['id']} refTextSha256 is not the fixture transcript")
            if voice["refClipSampleRateHz"] != RATE_HZ or voice["refClipSeconds"] != SECONDS:
                errors.append(f"examples: voice {voice['id']} rate or duration differs from the fixture")
            consent = consent_ids.get(voice["consentId"], {})
            if consent.get("evidenceSha256") != sha(files["consent.txt"]):
                errors.append(f"examples: consent {voice['consentId']} evidence is not the fixture statement")
    script = (EXAMPLES / "script.md").read_bytes()
    for job in json.loads((EXAMPLES / "jobs.json").read_text(encoding="utf-8")):
        if job["inputSha256"] != sha(script):
            errors.append(f"examples: job {job['id']} inputSha256 is not examples/script.md")
        if job["voice"] not in {v["id"] for v in voices}:
            errors.append(f"examples: job {job['id']} names an unknown voice")
    engines = json.loads((EXAMPLES / "engines.json").read_text(encoding="utf-8"))
    for engine in engines:
        if engine["backend"] != "Fake" or engine["hosted"]:
            errors.append(f"examples: engine {engine['id']} is not the fake engine; real engines live outside git")


def check_drafts(errors: list) -> None:
    schema = json.loads(DRAFT_SCHEMA.read_text(encoding="utf-8"))
    draft = json.loads(DRAFT_ENTRIES.read_text(encoding="utf-8"))
    entry_required = schema["$defs"]["entry"]["required"]
    file_required = schema["$defs"]["file"]["required"]
    if draft.get("schema_version") != 2:
        errors.append("drafts: schema_version is not 2")
    for model_id, entry in draft.get("models", {}).items():
        for key in entry_required:
            if key not in entry:
                errors.append(f"drafts: {model_id} lacks {key}")
        if entry.get("backend") not in BACKENDS:
            errors.append(f"drafts: {model_id} backend {entry.get('backend')!r} is not an Engine backend")
        if not entry.get("files"):
            errors.append(f"drafts: {model_id} lists no files")
        for variant in entry.get("variants", []):
            if variant.get("backend") not in BACKENDS or not variant.get("files"):
                errors.append(f"drafts: {model_id} variant {variant.get('hf_repo')} lacks a backend or files")
        listed = entry.get("files", []) + [f for v in entry.get("variants", []) for f in v.get("files", [])]
        for item in listed:
            for key in file_required:
                if key not in item:
                    errors.append(f"drafts: {model_id} file {item.get('path')} lacks {key}")
            digest = item.get("sha256")
            if digest != "pending" and not (isinstance(digest, str) and SHA256.match(digest)):
                errors.append(f"drafts: {model_id} file {item.get('path')} sha256 is neither pending nor hex")
            if not isinstance(item.get("bytes"), int) or item["bytes"] <= 0:
                errors.append(f"drafts: {model_id} file {item.get('path')} bytes is not a positive integer")
        if entry.get("gate_state") == "registered" and any(f.get("sha256") == "pending" for f in entry["files"]):
            errors.append(f"drafts: {model_id} is registered with a pending hash")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write-fixtures", type=Path, help="also write the fixtures into this directory")
    args = parser.parse_args()
    if args.write_fixtures:
        args.write_fixtures.mkdir(parents=True, exist_ok=True)
        for name, data in fixtures().items():
            (args.write_fixtures / name).write_bytes(data)
    errors: list = []
    check_examples(errors)
    check_drafts(errors)
    if sine_wav() != sine_wav():
        errors.append("fixtures: the sine is not deterministic")
    for line in errors:
        print(line, file=sys.stderr)
    print(json.dumps({"ok": not errors, "errors": len(errors),
                      "fixtures": {name: sha(data) for name, data in fixtures().items()}}, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
