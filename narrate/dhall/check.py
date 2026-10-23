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

`--self-test` is the negative control: it mutates copies of the examples and drafts and expects
every mutation to be refused.

Usage: python3 -I narrate/dhall/check.py [--write-fixtures DIR] [--self-test]
Exit 0 when every check holds, 1 otherwise. Standard library only.
"""

import argparse
import copy
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
BENCH_SOURCES = ROOT / "narrate" / "bench" / "sources.json"

RATE_HZ = 24000
TONE_HZ = 375
SECONDS = 10
AMPLITUDE = 8192
REF_CLIP_SECONDS = (10, 30)
FIXTURE_TEXT = "Synthetic sine fixture. This is not a voice and no person spoke it.\n"
FIXTURE_CONSENT = ("Fixture consent record for the synthetic sine voice used by narrate tests. "
                   "It grants nothing for any real speaker.\n")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
# Files a draft may leave out of a pinned snapshot's listing: model cards only.
OMITTABLE = {"README.md"}

# Engine.dhall, ported. Keep in step with Engine.dhall and policy-test.dhall.
PROFILE_BACKENDS = {
    "GpuSwitch": {"VulkanAudioCpp", "QwenTtsCpp", "LlamaTts"},
    "GpuDirect": {"VulkanAudioCpp", "QwenTtsCpp", "LlamaTts"},
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


def fixtures() -> dict:
    return {"sine.wav": sine_wav(), "ref.txt": FIXTURE_TEXT.encode(), "consent.txt": FIXTURE_CONSENT.encode()}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_examples() -> dict:
    tables = load_json(EXAMPLES / "pronunciation.json")
    return {
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
        ("unmapped dialog speaker voice", lambda d, m: job(d).update(
            speakers=[{"speaker": "B", "voice": "no-such-voice"}])),
        ("reference clip too short", lambda d, m: voice(d).update(refClipSeconds=1.0)),
        ("non-fixture voice in git", lambda d, m: voice(d).update(fixture=False)),
        ("fake backend on a non-fake profile", lambda d, m: d["engines"][0].update(profile="GpuDirect")),
        ("hosted backend behind a local profile, confidential", with_engine(hosted_engine, True)),
        ("rented backend behind the Mac profile, confidential", with_engine(rented_engine, True)),
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
