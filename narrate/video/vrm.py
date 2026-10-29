"""The VRM offline renderer: the second avatar external (docs/spec/NARRATED_VIDEO.md, "VRM external", SPR-128 on
TIN-7125 comment 33022456, SPR-120 on comment 59b5cb12).

A job selects it with avatar.external "vrm". avatar.rig names a VRM model record in the private avatars.json, and
the model itself is a private-store blob by SHA-256. No .vrm, rendered frame or model art enters git; the tests draw
a synthetic GLB and a synthetic stub renderer.

Registration and pin. program/externals.json registers the external publicly (shape, manifest schema
avatar.manifest/v1, mapping avatar_overlay_v1, face schema face.timeline/v1, how the renderer resolves) with no pin
value. The pin is the vrm entry of the private externals record (NARRATED_VIDEO_EXTERNALS): version, source commit,
per-system renderer digests and byte counts, the engine (its kind and the SHA-256 of its dependency lock), a
visibility and a gate state. VRM_RENDERER_BIN names the renderer. Its digest and size are checked against the pin at
plan and before every spawn. A pin with no renderer digest yet says gate_state commit_pinned_digest_pending and blocks
both avatar stages (vrm_pin_pending).

The renderer. The registered engine is @pixiv/three-vrm in headless Chromium: the page loads the model, and for each
face frame i it sets the expressions, look-at and head from face.json and calls vrm.update(1 / fps) once, so time
advances only by frame steps and never by the wall clock. That stepping is the renderer's contract: the wrapper cannot
watch the page's clock. It checks what the renderer reports instead, so a report whose step is not the rational
{num, den} equal to 1 / fps, or whose engine.kind is not the pin's, refuses vrm_report_invalid. Blender with the VRM
add-on is the noted fallback; neither is built in this repository yet (gate_state stays
commit_pinned_digest_pending until one is). The wrapper speaks one command shape:

  RENDERER --version                                     one JSON line on stdout: {version, commit}
  RENDERER render --vrm FILE --face FILE --size WxH      stdout: raw RGBA8 frames, straight alpha, rows top-down,
                                                         exactly frames * W * H * 4 bytes, frames and fps from face.json
                                                         stderr: its last line is one JSON report
                                                         {frames, step: {num, den}, renderer: {name, version,
                                                         engine: {kind}}, gpu: {vendor, renderer, driver}} on exit
                                                         0, or {refused: code, detail} on exit 1

The wrapper hashes the pipe as it streams it into FFmpeg (ProRes 4444, yuva444p10le, the overlay compose reads) and
writes the avatar.manifest/v1 itself. GPU raster is not bit-exact, so the manifest says frames_identity per_host:
frames_sha256 matches only another render on the same host, renderer and driver. It never passes --badge or
--realtime.

Gates. The VRM path refuses at admit, and again before the renderer spawns, without the model's likeness consent
(SP-R13: the record's likenessConsent {id, ruling} names a consents.json row with the Likeness scope, granted by
the operator and unrevoked) and its appearance approval (TIN-7130: approved by the operator for this model digest).
Whether offline VRM video carries a burned-in badge is open: no renderer draws one, the manifest records badge
{burned_in: false, decision: open}, and a record that tries to settle it refuses vrm_badge_undecided. Until a ruling
after the 11-14 bench, only the Internal edition may carry a VRM overlay (vrm_edition_unruled); the demos keep kitpip
(SPR-120, SPR-128).
"""

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import threading
from pathlib import Path

from ..config import ROOT
from ..ir import sha256_file
from . import avatar_manifest, face, labels
from .common import StageRefused, upstream, write_json
from .job import JobError, read_json

EXTERNAL = "vrm"
EXTERNALS_ENV = "NARRATED_VIDEO_EXTERNALS"
BIN_ENV = "VRM_RENDERER_BIN"
BINARY = "vrm-renderer"
MANIFEST_SCHEMA = avatar_manifest.SCHEMA_V1
MAPPING = avatar_manifest.MAPPING
FACE_SCHEMA = face.SCHEMA
FORBIDDEN_FLAGS = ("--badge", "--realtime")
ENGINES = ("three-vrm-chromium", "blender-vrm", "stub")
VISIBILITIES = ("private", "test_fixture")
PENDING = "commit_pinned_digest_pending"
TIMEOUT_S = 900
REGISTRY = ROOT / "program" / "externals.json"
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
NARRATION = "narration"
LIKENESS_SCOPE = "Likeness"
LIKENESS_RULING = "SP-R13"
LIKENESS_GRANTOR = "Operator"
APPROVAL_REF = "TIN-7130"
EDITIONS = ("Internal",)
MAX_VRM_BYTES = 512 * 1024 * 1024
MAX_GLB_JSON = 64 * 1024 * 1024
LICENCE_FIELDS = {
    "1.0": (
        "licenseUrl",
        "avatarPermission",
        "commercialUsage",
        "creditNotation",
        "allowRedistribution",
        "modification",
        "allowExcessivelyViolentUsage",
        "allowExcessivelySexualUsage",
        "allowPoliticalOrReligiousUsage",
        "allowAntisocialOrHateUsage",
        "otherLicenseUrl",
    ),
    "0.x": (
        "licenseName",
        "allowedUserName",
        "commercialUssageName",
        "violentUssageName",
        "sexualUssageName",
        "otherPermissionUrl",
        "otherLicenseUrl",
    ),
}
REQUIRED_LICENCE = {"1.0": ("licenseUrl", "avatarPermission", "commercialUsage"), "0.x": ("licenseName",)}


class VrmRefused(StageRefused):
    """The VRM external, or the wrapper around it, refused. verdict as StageRefused."""


# The registration and the pin ----------------------------------------------------------------------------------
def load_registry(path=REGISTRY):
    """The public vrm registration in program/externals.json: shape and resolution rules, never pin values."""
    record = read_json(path, "externals registry")
    entry = (record.get("externals") or {}).get(EXTERNAL) if isinstance(record, dict) else None
    if record.get("schema_version") != 1 or not isinstance(entry, dict):
        raise JobError("externals_invalid", "program/externals.json has no schema_version 1 vrm entry")
    leaked = sorted(set(entry) & {"source_commit", "binaries", "version", "engine_lock_sha256"})
    if entry.get("pin") != "private_record" or leaked:
        raise JobError("externals_invalid", f"the public vrm entry holds pin values {leaked}")
    return entry


def load_pin(path):
    """The vrm entry of an externals record, or None when no record is named or the record pins no vrm renderer."""
    from . import kitpip

    if path is None:
        return None
    record = read_json(path, "externals")
    if not isinstance(record, dict) or not isinstance(record.get("externals"), dict):
        raise JobError("externals_invalid", "the externals record is not an object with an externals table")
    pin = record["externals"].get(EXTERNAL)
    if pin is None:
        return None
    if record.get("schema_version") != 1 or not isinstance(pin, dict):
        raise JobError("externals_invalid", "the externals record's vrm entry is not a schema_version 1 object")
    for field in (
        "version",
        "source_commit",
        "renderer_kind",
        "manifest_schema",
        "timeline_mapping",
        "face_schema",
        "engine",
        "binaries",
        "visibility",
        "gate_state",
    ):
        if field not in pin:
            raise JobError("externals_invalid", f"the vrm pin has no {field}")
    expected = (EXTERNAL, MANIFEST_SCHEMA, MAPPING, FACE_SCHEMA)
    if (pin["renderer_kind"], pin["manifest_schema"], pin["timeline_mapping"], pin["face_schema"]) != expected:
        raise JobError("externals_invalid", f"the vrm pin is not {MANIFEST_SCHEMA} with {MAPPING} and {FACE_SCHEMA}")
    if pin["visibility"] not in VISIBILITIES:
        raise JobError("externals_invalid", f"the vrm pin's visibility is not one of {', '.join(VISIBILITIES)}")
    if not isinstance(pin["source_commit"], str) or not HEX40.fullmatch(pin["source_commit"]):
        raise JobError("externals_invalid", "the vrm pin's source_commit is not a full 40-hex commit")
    engine = pin["engine"]
    if not isinstance(engine, dict) or engine.get("kind") not in ENGINES:
        raise JobError("externals_invalid", f"the vrm pin's engine.kind is not one of {', '.join(ENGINES)}")
    lock = engine.get("lock_sha256")
    if not (HEX64.fullmatch(str(lock)) or (lock is None and pin["visibility"] == "test_fixture")):
        raise JobError("externals_invalid", "the vrm pin's engine.lock_sha256 is a 64-hex digest of its lockfile")
    if (engine["kind"] == "stub") != (pin["visibility"] == "test_fixture"):
        raise JobError("externals_invalid", "only the test-only record pins the stub engine")
    table = pin["binaries"].get(BINARY) if isinstance(pin["binaries"], dict) else None
    if not isinstance(table, dict):
        raise JobError("externals_invalid", f"the vrm pin has no binaries.{BINARY} table")
    for name, entry in table.items():
        if (
            not isinstance(entry, dict)
            or not HEX64.fullmatch(str(entry.get("sha256")))
            or not isinstance(entry.get("bytes"), int)
            or entry["bytes"] < 1
        ):
            raise JobError("externals_invalid", f"binaries.{BINARY}.{name} needs a 64-hex sha256 and a byte count")
    if not table and pin["gate_state"] != PENDING:
        raise JobError("externals_invalid", f"a vrm pin with no renderer digest must say gate_state {PENDING}")
    kitpip.no_locator(pin, "vrm pin")
    return pin


def binary_pin(pin):
    from . import kitpip

    table = pin["binaries"].get(BINARY, {})
    entry = table.get(kitpip.system())
    if entry is None and pin["visibility"] == "test_fixture":
        entry = table.get("any")
    return entry


def resolve(pin, env=None):
    """{state, binary, tool, detail} as kitpip.resolve: unregistered, pending, missing, mismatch or resolved."""
    env = os.environ if env is None else env
    if pin is None:
        return {"state": "unregistered", "binary": None, "tool": None, "detail": "no vrm renderer is pinned"}
    want = binary_pin(pin)
    tool = {"name": BINARY, "version": pin["version"], "binary_sha256": want["sha256"] if want else None}
    if want is None and pin["gate_state"] == PENDING:
        detail = f"the pin names commit {pin['source_commit'][:12]}; its renderer digest is pending"
        return {"state": "pending", "binary": None, "tool": tool, "detail": detail}
    if want is None:
        return {"state": "missing", "binary": None, "tool": tool, "detail": "the pin has no renderer for this system"}
    path = env.get(BIN_ENV)
    if not path or not Path(path).is_file():
        return {"state": "missing", "binary": None, "tool": tool, "detail": f"{BIN_ENV} names no file"}
    real = Path(path).resolve()
    if real.stat().st_size != want["bytes"] or sha256_file(real) != want["sha256"]:
        return {"state": "mismatch", "binary": None, "tool": tool, "detail": "the renderer's digest is not its pin's"}
    return {"state": "resolved", "binary": str(real), "tool": tool, "detail": None}


def pin_check(pin, env=None, registry=REGISTRY):
    """vrm pin-check: the public registration, the private pin against it, and VRM_RENDERER_BIN against the pin."""
    entry = load_registry(registry)
    if pin is None:
        return {"ok": False, "state": "unregistered", "detail": f"no vrm entry in the record named by {EXTERNALS_ENV}"}
    for field in ("manifest_schema", "timeline_mapping", "face_schema"):
        if pin[field] != entry[field]:
            raise JobError("externals_invalid", f"the vrm pin's {field} is not the registered one")
    resolution = resolve(pin, env)
    return {
        "ok": resolution["state"] == "resolved",
        "state": resolution["state"],
        "pin": {k: pin[k] for k in ("version", "source_commit", "gate_state", "engine", "visibility")},
        "binary_sha256": (resolution["tool"] or {}).get("binary_sha256"),
        "detail": resolution["detail"],
    }


# The model record and its gates --------------------------------------------------------------------------------
def model_problems(record):
    """Shape problems of one avatars.json VRM model record (an empty list when it reads)."""
    problems = []
    if record.get("kind") != EXTERNAL:
        problems.append("kind is not vrm")
    if not HEX64.fullmatch(str(record.get("sha256"))):
        problems.append("sha256 is not 64-hex")
    if not isinstance(record.get("bytes"), int) or record["bytes"] < 1 or record["bytes"] > MAX_VRM_BYTES:
        problems.append(f"bytes is not 1 to {MAX_VRM_BYTES}")
    for block in ("likenessConsent", "approval", "badge"):
        if not isinstance(record.get(block), dict):
            problems.append(f"{block} is not an object")
    return problems


def likeness_consent(reference, records):
    """The consents.json row a model's likenessConsent reference names, or None."""
    table = records.get("consents")
    consent_id = reference.get("id")
    if not isinstance(table, dict) or not isinstance(consent_id, str) or not consent_id:
        return None
    row = table.get(consent_id)
    return row if isinstance(row, dict) else None


def likeness_problem(reference, records):
    """(code, detail) of the model's SP-R13 likeness consent, or (None, None) when it holds.

    The model record carries only a reference, {id, ruling}. The consent itself is a Consent row in consents.json,
    the table voice consent goes through: its scopes list holds Likeness, the operator granted it, its evidence is a
    64-hex digest and it is not revoked. A consent written inside the model record grants nothing."""
    consent_id = reference.get("id")
    if not isinstance(consent_id, str) or not consent_id:
        return "vrm_consent_missing", "the model's likenessConsent.id names no consent"
    if reference.get("ruling") != LIKENESS_RULING:
        return "vrm_consent_missing", f"the model's likeness consent is not under {LIKENESS_RULING}"
    consent = likeness_consent(reference, records)
    if consent is None:
        return "vrm_consent_missing", f"likeness consent {consent_id} is not in consents.json"
    scopes = consent.get("scopes")
    if (
        not isinstance(scopes, list)
        or not all(isinstance(scope, str) for scope in scopes)
        or LIKENESS_SCOPE not in scopes
        or consent.get("grantedBy") != LIKENESS_GRANTOR
        or not HEX64.fullmatch(str(consent.get("evidenceSha256")))
    ):
        detail = f"consent {consent_id} is not a {LIKENESS_SCOPE} grant by the {LIKENESS_GRANTOR} with evidence"
        return "vrm_consent_missing", detail
    if consent.get("revokedAt") is not None:
        return "vrm_consent_revoked", f"likeness consent {consent_id} is revoked"
    return None, None


def gates(job, records):
    """[(code, detail)] the VRM path refuses at admit for this job; empty when every gate holds.

    The model record must exist and read; the job's rigRevisionSha256, when set, must be its digest; its likeness
    consent (SP-R13) must resolve in consents.json with the Likeness scope, the operator as grantor, an evidence digest
    and no revocation (likeness_problem); its appearance approval
    (TIN-7130) must be approved by the operator for this model digest; the badge decision must still be open; and
    the edition must be one a VRM overlay is ruled for."""
    avatar = job["avatar"]
    out = []
    if job["edition"] not in EDITIONS:
        out.append(("vrm_edition_unruled", f"a VRM overlay is ruled only for {', '.join(EDITIONS)} (SPR-120)"))
    model_id = avatar.get("rig")
    record = (records.get("avatars") or {}).get(model_id) if model_id else None
    if record is None:
        out.append(("vrm_model_missing", "avatar.rig names no VRM model record in avatars.json"))
        return out
    problems = model_problems(record)
    if problems:
        out.append(("vrm_model_invalid", f"VRM model {model_id}: " + "; ".join(problems)))
        return out
    if avatar.get("rigRevisionSha256") not in (None, record["sha256"]):
        out.append(("vrm_digest_mismatch", "avatar.rigRevisionSha256 is not the model record's sha256"))
    code, detail = likeness_problem(record["likenessConsent"], records)
    if code is not None:
        out.append((code, detail))
    approval = record["approval"]
    if (
        approval.get("ref") != APPROVAL_REF
        or approval.get("state") != "approved"
        or approval.get("decidedBy") != "Operator"
        or approval.get("vrmSha256") != record["sha256"]
        or not HEX64.fullmatch(str(approval.get("evidenceSha256")))
    ):
        out.append(("vrm_approval_missing", f"the model has no {APPROVAL_REF} operator approval for this digest"))
    if record["badge"].get("burnedIn") is not None:
        out.append(("vrm_badge_undecided", "whether offline VRM video carries a burned-in badge is not ruled"))
    return out


def model(job, records):
    return records["avatars"][job["avatar"]["rig"]]


def knobs(job, records, pin):
    """The avatar stage's knobs for a VRM overlay: the model and its digest, the render size, the persona, the
    likeness consent and approval evidence, the engine lock and the face source."""
    record = model(job, records)
    engine = (pin or {}).get("engine") or {}
    return {
        "external": EXTERNAL,
        "rig": record["id"],
        "rigRevisionSha256": record["sha256"],
        "renderSize": job["avatar"]["renderSize"],
        "persona": job["labels"]["persona"],
        "likenessConsentId": record["likenessConsent"]["id"],
        "approval": {"ref": record["approval"]["ref"], "evidenceSha256": record["approval"]["evidenceSha256"]},
        "engine": {"kind": engine.get("kind"), "lock_sha256": engine.get("lock_sha256")},
        "face": {"schema": FACE_SCHEMA, "source": "loudness_envelope"},
    }


# The model file ------------------------------------------------------------------------------------------------
def read_meta(path):
    """{spec_version, meta} of a VRM file: a binary glTF whose JSON chunk carries VRMC_vrm (1.0) or VRM (0.x).
    meta holds only the licence fields (absent ones as null). vrm_invalid or vrm_meta_missing otherwise."""
    with open(path, "rb") as stream:
        head = stream.read(20)
        if len(head) < 20:
            raise VrmRefused("vrm_invalid", "the model is not a binary glTF")
        magic, version, _, chunk_length, chunk_type = struct.unpack("<4sIIII", head)
        if magic != b"glTF" or version != 2 or chunk_type != 0x4E4F534A or chunk_length > MAX_GLB_JSON:
            raise VrmRefused("vrm_invalid", "the model is not a glTF 2.0 binary with a JSON chunk")
        try:
            document = json.loads(stream.read(chunk_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise VrmRefused("vrm_invalid", "the model's JSON chunk does not parse") from None
    extensions = document.get("extensions") if isinstance(document, dict) else None
    extensions = extensions if isinstance(extensions, dict) else {}
    if isinstance(extensions.get("VRMC_vrm"), dict):
        spec, meta = "1.0", extensions["VRMC_vrm"].get("meta")
    elif isinstance(extensions.get("VRM"), dict):
        spec, meta = "0.x", extensions["VRM"].get("meta")
    else:
        raise VrmRefused("vrm_invalid", "the model carries neither VRMC_vrm nor VRM")
    if not isinstance(meta, dict) or any(meta.get(k) in (None, "") for k in REQUIRED_LICENCE[spec]):
        raise VrmRefused("vrm_meta_missing", f"the model's VRM {spec} meta lacks its licence fields")
    return {"spec_version": spec, "meta": {k: meta.get(k) for k in LICENCE_FIELDS[spec]}}


# The renderer --------------------------------------------------------------------------------------------------
def last_json(data):
    for line in reversed(data.decode("utf-8", "replace").splitlines()):
        if line.strip():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                return None
            return value if isinstance(value, dict) else None
    return None


def call_version(resolution, pin, timeout_s=60):
    """RENDERER --version, after re-checking the renderer against its pin."""
    binary = recheck(resolution, pin)
    try:
        done = subprocess.run(
            [binary, "--version"], capture_output=True, timeout=timeout_s, check=False, env=spawn_env()
        )
    except subprocess.TimeoutExpired:
        raise VrmRefused("vrm_timeout", "the renderer's --version ran too long", verdict=False) from None
    result = last_json(done.stdout)
    if done.returncode != 0 or result is None:
        raise VrmRefused("vrm_renderer_error", f"the renderer's --version exited {done.returncode}", verdict=False)
    return result


def spawn_env():
    return {"PATH": os.environ.get("PATH", ""), "LC_ALL": "C"}


def recheck(resolution, pin):
    again = resolve(pin, {BIN_ENV: resolution.get("binary") or ""})
    if again["state"] != "resolved":
        code = "vrm_pin_mismatch" if again["state"] == "mismatch" else "vrm_renderer_missing"
        raise VrmRefused(code, again["detail"], verdict=False)
    return again["binary"]


def render(resolution, pin, vrm_path, face_path, size, fps, frames, out_mov, timeout_s=TIMEOUT_S):
    """Run the renderer and stream its raw RGBA frames into a ProRes 4444 overlay. (report, frames_sha256)."""
    args = ["render", "--vrm", str(vrm_path), "--face", str(face_path), "--size", f"{size}x{size}"]
    if any(flag in args for flag in FORBIDDEN_FLAGS):
        raise VrmRefused("contract_invalid", "the wrapper never passes --badge or --realtime")
    binary = recheck(resolution, pin)
    ffmpeg = shutil.which(os.environ.get("FFMPEG", "ffmpeg"))
    if ffmpeg is None:
        raise VrmRefused("ffmpeg_missing", "no ffmpeg on PATH", verdict=False)
    frame_bytes = size * size * 4
    total = frames * frame_bytes
    encode = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "-s",
        f"{size}x{size}",
        "-r",
        f"{fps['num']}/{fps['den']}",
        "-i",
        "pipe:0",
        "-frames:v",
        str(frames),
        "-c:v",
        "prores_ks",
        "-profile:v",
        "4444",
        "-pix_fmt",
        "yuva444p10le",
        "-fflags",
        "+bitexact",
        "-flags:v",
        "+bitexact",
        "-an",
        str(out_mov),
    ]
    digest = hashlib.sha256()
    got, timed_out = 0, threading.Event()
    with tempfile.TemporaryFile() as err, tempfile.TemporaryFile() as ff_err:
        renderer = subprocess.Popen(
            [binary, *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=err, env=spawn_env()
        )
        encoder = subprocess.Popen(encode, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=ff_err)

        def kill():
            timed_out.set()
            for process in (renderer, encoder):
                if process.poll() is None:
                    process.kill()

        timer = threading.Timer(timeout_s, kill)
        timer.start()
        encoder_open = True
        try:
            while True:
                chunk = renderer.stdout.read(min(frame_bytes, 1 << 20))
                if not chunk:
                    break
                got += len(chunk)
                if got > total:
                    continue  # drain and refuse below: the renderer wrote more frames than the face timeline holds
                digest.update(chunk)
                if encoder_open:
                    try:
                        encoder.stdin.write(chunk)
                    except BrokenPipeError:
                        encoder_open = False
            try:
                encoder.stdin.close()
            except BrokenPipeError:
                pass
            renderer_code, encoder_code = renderer.wait(), encoder.wait()
        finally:
            timer.cancel()
            renderer.stdout.close()
            for process in (renderer, encoder):
                if process.poll() is None:
                    process.kill()
                    process.wait()
        err.seek(0)
        report = last_json(err.read())
    if timed_out.is_set():
        raise VrmRefused("vrm_timeout", f"the renderer ran past {timeout_s} s", verdict=False)
    if renderer_code == 1 and isinstance(report, dict) and isinstance(report.get("refused"), str):
        raise VrmRefused(report["refused"], str(report.get("detail", "")))
    if renderer_code != 0 or report is None:
        raise VrmRefused("vrm_renderer_error", f"the renderer exited {renderer_code}", verdict=False)
    if got != total or report.get("frames") != frames:
        raise VrmRefused("vrm_frames_mismatch", f"the renderer wrote {got} bytes, not {frames} frames of {size}x{size}")
    if encoder_code != 0:
        raise VrmRefused("ffmpeg_failed", "ffmpeg could not encode the overlay", verdict=False)
    check_report(report, pin, fps)
    return report, digest.hexdigest()


def is_step(step, fps):
    """True when step is the rational {num, den}, both positive integers, equal to 1 / fps."""
    if not isinstance(step, dict) or set(step) != {"num", "den"}:
        return False
    num, den = step["num"], step["den"]
    if not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in (num, den)):
        return False
    return num * fps["num"] == den * fps["den"]


def check_report(report, pin, fps):
    """vrm_report_invalid unless the report names the renderer, its engine (the pin's kind), a frame step of exactly
    1 / fps and the GPU vendor, renderer string and driver."""
    gpu = report.get("gpu") if isinstance(report.get("gpu"), dict) else {}
    named = report.get("renderer") if isinstance(report.get("renderer"), dict) else {}
    if not all(isinstance(gpu.get(k), str) and gpu[k] for k in ("vendor", "renderer", "driver")) or not all(
        isinstance(named.get(k), str) and named[k] for k in ("name", "version")
    ):
        raise VrmRefused("vrm_report_invalid", "the renderer's report names no renderer, GPU vendor or driver")
    engine = named.get("engine") if isinstance(named.get("engine"), dict) else {}
    if engine.get("kind") != pin["engine"]["kind"]:
        raise VrmRefused("vrm_report_invalid", f"the renderer reports engine {engine.get('kind')!r}, not its pin's")
    if not is_step(report.get("step"), fps):
        raise VrmRefused(
            "vrm_report_invalid", f"the renderer's step is not {{num, den}} equal to {fps['den']}/{fps['num']} s"
        )


# The stages ----------------------------------------------------------------------------------------------------
def stage_context(rc):
    pin, resolution = rc.ctx.get("vrm_pin"), rc.ctx.get("vrm")
    if pin is None or not resolution or resolution.get("state") != "resolved":
        raise VrmRefused("vrm_renderer_missing", "no resolved vrm renderer for its pin", verdict=False)
    return pin, resolution


def recheck_gates(job, records):
    for code, detail in gates(job, records):
        raise VrmRefused(code, detail)


def model_file(env, record):
    """The model's path in the private store, re-hashed against its record."""
    path = env.source(record["sha256"], "the VRM model")
    if path.stat().st_size != record["bytes"] or sha256_file(path) != record["sha256"]:
        raise VrmRefused("vrm_digest_mismatch", "the stored model is not its record's", verdict=False)
    return path


def overlay_manifest(record, meta, report, pin, frames_sha256, fps, size, face_doc, outputs, narration_labels):
    consent_ids, voice_ids = narration_labels
    frames = face_doc["frames"]
    return {
        "schema": MANIFEST_SCHEMA,
        "kind": "avatar_overlay",
        "synthetic": True,
        "show_badge": False,
        "badge": dict(avatar_manifest.BADGE_OPEN),
        "consent_ids": consent_ids,
        "voice_ids": voice_ids,
        "likeness_consent_id": record["likenessConsent"]["id"],
        "approval": {"ref": record["approval"]["ref"], "evidence_sha256": record["approval"]["evidenceSha256"]},
        "status": "private_unaccepted",
        "lip_sync_acceptance": "pending_operator",
        "rig": {"id": record["id"], "sha256": record["sha256"]},
        "vrm": {"sha256": record["sha256"], "bytes": record["bytes"]} | meta,
        "renderer": {
            "kind": EXTERNAL,
            "name": report["renderer"]["name"],
            "version": report["renderer"]["version"],
            "engine": {"kind": pin["engine"]["kind"], "lock_sha256": pin["engine"].get("lock_sha256")},
            "step": {"num": report["step"]["num"], "den": report["step"]["den"]},
            "gpu": {k: report["gpu"][k] for k in ("vendor", "renderer", "driver")},
        },
        "rate": fps,
        "size": {"w": size, "h": size},
        "frames": frames,
        "frames_sha256": frames_sha256,
        "frames_identity": "per_host",
        "face": {
            "schema": face_doc["schema"],
            "sha256": outputs["face.json"],
            "clock": face_doc["clock"],
            "source": face_doc["source"],
        },
        "outputs": [{"file": name, "sha256": digest} for name, digest in sorted(outputs.items())],
        "timeline": {"mapping": MAPPING, "no_time_stretch": False, "clock": avatar_manifest.CLOCK, "base_sha256": None},
    }


def render_overlay(rc, partial, narrate_run, fps, job_knobs, pin, resolution, timeout_s=TIMEOUT_S):
    """Build the face timeline, render the model through the pinned renderer and write the v1 manifest. The stage
    manifest fields."""
    from . import kitpip

    recheck_gates(rc.job, rc.records)
    record = model(rc.job, rc.records)
    vrm_path = model_file(rc.env, record)
    meta = read_meta(vrm_path)
    manifest, consent_ids, voice_ids = kitpip.narration(narrate_run)
    face_doc = face.from_narration(narrate_run, manifest, fps)
    face.validate(face_doc, fps, {"run_id": manifest["run_id"], "content_sha256": manifest["content_sha256"]})
    overlay = partial / "overlay"
    overlay.mkdir(parents=True)
    write_json(overlay / "face.json", face_doc)
    size, frames = job_knobs["renderSize"], face_doc["frames"]
    report, frames_sha256 = render(
        resolution, pin, vrm_path, overlay / "face.json", size, fps, frames, overlay / "overlay.mov", timeout_s
    )
    (overlay / "frames.sha256").write_text(frames_sha256 + "\n", encoding="utf-8")
    outputs = {name: sha256_file(overlay / name) for name in ("face.json", "frames.sha256", "overlay.mov")}
    written = overlay_manifest(
        record, meta, report, pin, frames_sha256, fps, size, face_doc, outputs, (consent_ids, voice_ids)
    )
    write_json(overlay / "manifest.json", written)
    seen, problems = avatar_manifest.verify_dir(overlay, EXTERNAL)
    if problems:
        raise VrmRefused("avatar_manifest_invalid", "; ".join(problems))
    persona = job_knobs["persona"]
    likeness = record["likenessConsent"]["id"]
    return {
        "measurements": {
            "frames": frames,
            "frames_sha256": frames_sha256,
            "frames_identity": "per_host",
            "fps": fps,
            "size": {"w": size, "h": size},
            "rig": {"id": record["id"], "sha256": record["sha256"]},
            "show_badge": False,
            "renderer": {"kind": EXTERNAL, "name": seen["renderer"]["name"], "version": seen["renderer"]["version"]},
            "gpu": written["renderer"]["gpu"],
            "vrm": {"spec_version": meta["spec_version"], "meta": meta["meta"]},
        },
        "labels": {
            "synthetic": True,
            "consent_ids": sorted(set(consent_ids) | {likeness}),
            "voice_ids": voice_ids,
            "persona": persona,
        },
        "synthetic": True,
        "timeline": {
            "mapping": MAPPING,
            "no_time_stretch": False,
            "stretch_applied": False,
            "fps": fps,
            "total_frames": frames,
            "narration": {"run_id": manifest["run_id"], "content_sha256": manifest["content_sha256"]},
            "output_axis": "overlay frame index / fps on its segment's narration clock; compose places frame 0 "
            "at the segment anchor",
            "source_axis": "none: the overlay is drawn from the face timeline on the narration clock; no source "
            "media is time-stretched",
        },
        "states": {
            "source_checks": "passed",
            "render": "stub" if pin["visibility"] == "test_fixture" else "local",
            "lip_sync": "pending_operator",
            "appearance_approval": "approved",
            "badge_decision": "open",
            "frames_identity": "per_host",
        },
    }


def run_avatar_stage(rc, row, partial):
    """The executor's avatar runner for a VRM overlay: one segment, at the base's fps, inside the job store."""
    from . import kitpip
    from .graph import knobs_for

    pin, resolution = stage_context(rc)
    segment = next(s for s in rc.job["segments"] if s["id"] == row["segment"])
    _, voice_dir = upstream(rc.store, f"voice/{segment['id']}")
    base, _ = upstream(rc.store, "base")
    job_knobs = knobs_for("avatar", segment, rc.job, rc.records, pin)
    narrate_run = (voice_dir / NARRATION).resolve()
    kitpip.guard_partial(rc.store, partial, narrate_run)
    return render_overlay(rc, partial, narrate_run, base["measurements"]["fps"], job_knobs, pin, resolution)


def run_avatar_check(rc, row, partial):
    """The executor's avatar_check runner for a VRM overlay: re-hash the overlay under its v1 manifest, keep the
    frame digest the avatar stage measured and the narration's consent ids, and grow the labels.

    frames_sha256 is the digest of the renderer's raw RGBA stream. The ProRes encode is not lossless, so the check
    cannot recompute it from overlay.mov; it re-hashes the files the manifest lists and keeps the recorded digest."""
    stage_context(rc)
    recheck_gates(rc.job, rc.records)
    segment = row["segment"]
    voice, _ = upstream(rc.store, f"voice/{segment}")
    avatar, avatar_dir = upstream(rc.store, f"avatar/{segment}")
    seen, problems = avatar_manifest.verify_dir(avatar_dir / "overlay", EXTERNAL)
    if seen is None or problems:
        raise VrmRefused("digest_mismatch", "; ".join(problems))
    if not (seen["synthetic"] and seen["consent_ids"]):
        raise VrmRefused("vrm_unlabelled", "the overlay manifest is not synthetic with consent ids")
    frames_sha256 = avatar["measurements"].get("frames_sha256")
    if seen["frames_sha256"] != frames_sha256:
        raise VrmRefused("label_chain_broken", "the stored overlay's frames are not the ones the avatar measured")
    if seen["consent_ids"] != labels.of(voice)["consent_ids"]:
        raise VrmRefused("label_chain_broken", "the overlay's consent ids are not the narration's")
    persona = rc.job["labels"]["persona"]
    grown = labels.grow([voice, avatar], persona)
    labels.check(grown, [voice, avatar], persona)
    likeness = model(rc.job, rc.records)["likenessConsent"]["id"]
    write_json(
        partial / "check.json",
        {
            "verified": True,
            "labelled": True,
            "renderer_kind": EXTERNAL,
            "frames_sha256": frames_sha256,
            "frames_identity": "per_host",
            "consent_ids": grown["consent_ids"],
            "likeness_consent_id": likeness,
            "avatar_content_sha256": avatar["content_sha256"],
        },
    )
    return {
        "synthetic": True,
        "measurements": {"labelled": True, "frames_sha256": frames_sha256, "frames_identity": "per_host"},
        "labels": grown,
        "states": {"source_checks": "passed", "lip_sync": "pending_operator", "badge_decision": "open"},
    }
