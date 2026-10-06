#!/usr/bin/env python3
"""Author bounded source-bound restoration settings; never decode or render audio."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import signal
import stat
import struct
import sys
import tempfile
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO
MAX_SOURCE_BYTES = 3 * 1024**3
MAX_PCM_BYTES = 1024**3
MAX_REVIEW_BYTES = 16 * 1024
MAX_MANIFEST_BYTES = 1024**2
MAX_CONTEXT_BYTES = 64 * 1024
MAX_RECEIPT_BYTES = 64 * 1024
MAX_PROFILE_BYTES = 16 * 1024
MAX_RESULT_BYTES = 16 * 1024
REVIEW_KEYS = {"schema_version", "source_sha256", "source_run_manifest_sha256",
               "source_pcm_sha256", "start_seconds", "end_seconds", "time_axis",
               "selected_by", "reviewed_by", "review_status", "authorization_scope",
               "authorization_reference", "music_status", "click_status",
               "ambient_music_status", "note"}
CONTROL_LIMITS = {"reduction_db": (.01, 12), "noise_floor_db": (-80, -20),
                  "adaptivity": (0, 1), "gain_smooth": (0, 50),
                  "integrated_lufs": (-70, -5), "true_peak_dbtp": (-9, 0)}
module_spec = importlib.util.spec_from_file_location("_capture_media_validator", REPO / "scripts/media.py")
media = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(media)


class CaptureError(ValueError):
    def __init__(self, message: str, code: str = "validation_failed"):
        super().__init__(message)
        self.code = code


class Deadline:
    def __init__(self, seconds: int):
        if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= 60:
            raise CaptureError("timeout_seconds must be an integer between 1 and 60")
        self.started = time.monotonic()
        self.ends = self.started + seconds
        self.seconds = seconds

    def check(self):
        if time.monotonic() >= self.ends:
            raise CaptureError("capture-profile authoring deadline exceeded", "deadline_exceeded")

    def remaining(self) -> float:
        self.check()
        return self.ends - time.monotonic()


def safe_path(value, *, directory: bool = False) -> Path:
    if not isinstance(value, (str, Path)) or not 1 <= len(str(value)) <= 4096:
        raise CaptureError("path must be local bounded text")
    original = Path(value)
    if ".." in original.parts or "://" in str(value):
        raise CaptureError("path traversal and URLs are unsupported")
    try:
        path = original.expanduser().absolute()
        cursor = Path(path.anchor)
        for part in path.parts[1:]:
            cursor /= part
            if cursor.is_symlink():
                raise CaptureError("symlink path components are unsupported")
        if not (path.is_dir() if directory else path.is_file()):
            raise CaptureError("required local directory/file is unavailable")
        if not directory and not stat.S_ISREG(path.stat().st_mode):
            raise CaptureError("input must be a regular file")
        return path.resolve()
    except CaptureError:
        raise
    except (RuntimeError, ValueError, OSError) as exc:
        raise CaptureError("local path cannot be normalized or inspected") from exc


def underneath(path: Path, parent: Path):
    if not path.is_relative_to(parent):
        raise CaptureError("path is outside its verified local run")


def file_signature(path: Path) -> tuple:
    info = path.stat()
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def hash_file(path: Path, deadline: Deadline, max_bytes: int, label: str) -> str:
    deadline.check()
    path = safe_path(path)
    before = file_signature(path)
    if not 0 < before[2] <= max_bytes:
        raise CaptureError(f"{label} byte extent is outside the authoring bound")
    digest = hashlib.sha256()
    total = 0
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as handle:
        while chunk := handle.read(1024**2):
            deadline.check()
            total += len(chunk)
            if total > max_bytes:
                raise CaptureError(f"{label} exceeds its byte bound")
            digest.update(chunk)
    if before != file_signature(path) or total != before[2]:
        raise CaptureError(f"{label} changed while reading", "source_changed")
    deadline.check()
    return digest.hexdigest()


def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CaptureError("JSON contains duplicate fields")
        result[key] = value
    return result


def json_bytes(data: dict, limit: int) -> bytes:
    try:
        raw = (json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    except (TypeError, ValueError) as exc:
        raise CaptureError("output contains unsupported JSON values") from exc
    if len(raw) > limit:
        raise CaptureError("output exceeds its byte bound")
    return raw


def read_json(path: Path, limit: int, deadline: Deadline, label: str) -> tuple[dict, str]:
    expected_hash = hash_file(path, deadline, limit, label)
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as handle:
        raw = handle.read(limit + 1)
    deadline.check()
    if len(raw) > limit or hashlib.sha256(raw).hexdigest() != expected_hash:
        raise CaptureError(f"{label} changed while reading", "source_changed")
    try:
        data = json.loads(raw, object_pairs_hook=reject_duplicates,
                          parse_constant=lambda value: (_ for _ in ()).throw(CaptureError("nonfinite JSON is unsupported")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise CaptureError(f"{label} is not valid bounded JSON") from exc
    if not isinstance(data, dict):
        raise CaptureError(f"{label} must be a JSON object")
    return data, expected_hash


def numeric(value, low, high, name):
    try:
        return media.numeric_control(value, low, high, name)
    except (media.MediaError, OverflowError) as exc:
        raise CaptureError(str(exc)) from exc


def integer(value, low, high, name):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise CaptureError(f"{name} must be an integer between {low} and {high}")
    return value


def hex_digest(value, name):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise CaptureError(f"{name} must be lowercase SHA-256")
    return value


def bounded_text(value, limit, name):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise CaptureError(f"{name} must be meaningful text up to {limit} characters")
    return value


def enum(value, choices, name):
    if not isinstance(value, str) or value not in choices:
        raise CaptureError(f"unsupported {name}")
    return value


def native_pcm(path: Path, deadline: Deadline) -> dict:
    """Inspect bounded RIFF headers only; seek over PCM, never decode samples."""
    deadline.check()
    before = file_signature(path)
    fmt = None
    data_bytes = None
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)), "rb") as handle:
        header = handle.read(12)
        if len(header) != 12 or header[:4] != b"RIFF" or header[8:] != b"WAVE":
            raise CaptureError("native source must be bounded RIFF/WAVE PCM")
        end = struct.unpack("<I", header[4:8])[0] + 8
        if end > before[2] or end < 12:
            raise CaptureError("native WAV header extent is invalid")
        chunks = 0
        while handle.tell() < end:
            deadline.check()
            chunks += 1
            if chunks > 4096:
                raise CaptureError("native WAV contains too many header chunks")
            chunk = handle.read(8)
            if len(chunk) != 8:
                raise CaptureError("native WAV chunk header is truncated")
            kind, size = struct.unpack("<4sI", chunk)
            position = handle.tell()
            if position + size > end:
                raise CaptureError("native WAV chunk exceeds declared extent")
            if kind == b"fmt ":
                if fmt is not None or not 16 <= size <= 256:
                    raise CaptureError("native WAV format header is unsupported")
                raw = handle.read(size)
                code, channels, rate, byte_rate, alignment, bits = struct.unpack("<HHIIHH", raw[:16])
                if code == 0xFFFE:
                    if len(raw) < 40 or raw[28:40] != bytes.fromhex("00001000800000aa00389b71"):
                        raise CaptureError("native WAV extensible format is unsupported")
                    code = struct.unpack("<I", raw[24:28])[0]
                    valid_bits = struct.unpack("<H", raw[18:20])[0]
                    if valid_bits != bits:
                        raise CaptureError("native WAV valid-bit packing is unsupported")
                codec = ({8: "pcm_u8", 16: "pcm_s16le", 24: "pcm_s24le", 32: "pcm_s32le"}.get(bits)
                         if code == 1 else {32: "pcm_f32le", 64: "pcm_f64le"}.get(bits) if code == 3 else None)
                if codec is None or alignment != channels * (bits // 8) or byte_rate != rate * alignment:
                    raise CaptureError("native WAV is not supported uncompressed PCM")
                fmt = {"sample_rate": rate, "channels": channels, "codec": codec,
                       "block_alignment": alignment}
            elif kind == b"data":
                if data_bytes is not None:
                    raise CaptureError("multiple native WAV data chunks are unsupported")
                data_bytes = size
            handle.seek(position + size + size % 2)
        if handle.tell() != end:
            raise CaptureError("native WAV padding/extent is invalid")
    if fmt is None or data_bytes is None or not fmt["block_alignment"] or data_bytes % fmt["block_alignment"]:
        raise CaptureError("native WAV lacks an integral PCM sample extent")
    if before != file_signature(path):
        raise CaptureError("native PCM changed during header inspection", "source_changed")
    info = {key: fmt[key] for key in ("sample_rate", "channels", "codec")}
    info["sample_count"] = data_bytes // fmt["block_alignment"]
    rate, channels = info["sample_rate"], info["channels"]
    integer(rate, 8000, 192000, "native sample_rate")
    integer(channels, 1, 2, "native channels")
    integer(info["sample_count"], 1, rate * 600, "native sample_count")
    return info


def validate_review(review, source_hash, manifest_hash, pcm_hash, samples, rate):
    if set(review) != REVIEW_KEYS:
        raise CaptureError("review JSON requires exactly the registered source/review fields")
    integer(review["schema_version"], 1, 1, "review schema_version")
    for key, actual in (("source_sha256", source_hash), ("source_run_manifest_sha256", manifest_hash),
                        ("source_pcm_sha256", pcm_hash)):
        if hex_digest(review[key], key) != actual:
            raise CaptureError(f"review {key} is stale or belongs to another source")
    start = numeric(review["start_seconds"], 0, 600, "review start_seconds")
    end = numeric(review["end_seconds"], 0, 600, "review end_seconds")
    if [round(start * rate), round(end * rate)] != samples:
        raise CaptureError("review interval differs from requested native sample mapping")
    if review["time_axis"] != "decoded_source_audio_samples":
        raise CaptureError("review time axis must be decoded_source_audio_samples")
    for key in ("selected_by", "reviewed_by"):
        bounded_text(review[key], 128, key)
    bounded_text(review["authorization_reference"], 512, "authorization_reference")
    bounded_text(review["note"], 2000, "note")
    enum(review["review_status"], {"reviewed_candidate", "reviewed_possible_contamination", "rejected_contaminated"}, "review_status")
    enum(review["authorization_scope"], {"profile_authoring", "experimental_capture_render"}, "authorization_scope")
    for key in ("music_status", "click_status"):
        enum(review[key], {"unknown", "suspected", "reviewed_no_obvious_content", "reviewed_present"}, key)
    enum(review["ambient_music_status"], {"not_reported", "suspected", "reviewed_absent", "reviewed_present"}, "ambient_music_status")


def publish_directory(staging: Path, final: Path):
    if final.exists() or final.is_symlink():
        raise CaptureError("authoring output already exists")
    staging.rename(final)


def author(input_value, run_dir_value, review_value, *, capture_start_seconds,
           capture_end_seconds, reduction_db, noise_floor_db, adaptivity, gain_smooth,
           integrated_lufs, true_peak_dbtp, peaking_eq=None, compressor=None,
           timeout_seconds=60) -> dict:
    deadline = Deadline(timeout_seconds)
    source = safe_path(input_value)
    run_dir = safe_path(run_dir_value, directory=True)
    underneath(run_dir, safe_path(ROOT / "artifacts/runs", directory=True))
    review_path = safe_path(review_value)
    underneath(review_path, run_dir)
    manifest_path = safe_path(run_dir / "manifest.json")
    pcm_path = safe_path(run_dir / "source.wav")
    manifest, manifest_hash = read_json(manifest_path, MAX_MANIFEST_BYTES, deadline, "source manifest")
    for key in ("source", "outputs", "output_sha256", "timeline", "pcm"):
        if not isinstance(manifest.get(key), dict):
            raise CaptureError(f"baseline manifest {key} must be a provenance object")
    source_hash = hash_file(source, deadline, MAX_SOURCE_BYTES, "original source")
    pcm_hash = hash_file(pcm_path, deadline, MAX_PCM_BYTES, "source PCM")
    try:
        integer(manifest["schema_version"], 1, 1, "manifest schema_version")
        if (safe_path(manifest["source"]["path"]) != source
                or hex_digest(manifest["source"]["sha256"], "manifest source sha256") != source_hash
                or manifest["outputs"]["source"] != "source.wav"
                or hex_digest(manifest["output_sha256"]["source.wav"], "manifest PCM sha256") != pcm_hash):
            raise CaptureError("baseline run does not bind this original source and PCM")
        if manifest["timeline"]["no_time_stretch"] is not True:
            raise CaptureError("baseline native source sample mapping is unavailable")
        reference = manifest["pcm"]
    except (KeyError, TypeError) as exc:
        raise CaptureError("baseline manifest lacks source/native provenance") from exc
    pcm = native_pcm(pcm_path, deadline)
    for key in ("sample_rate", "channels", "sample_count"):
        expected = integer(reference.get(key), 1, 192000 * 600, f"manifest {key}")
        if pcm[key] != expected:
            raise CaptureError(f"baseline PCM {key} differs from its header")
    origin = manifest["timeline"].get("audio_start_seconds")
    if origin is not None:
        origin = numeric(origin, -86400, 86400, "source audio origin")
    start = numeric(capture_start_seconds, 0, 600, "capture_start_seconds")
    end = numeric(capture_end_seconds, 0, 600, "capture_end_seconds")
    rate = pcm["sample_rate"]
    samples = [round(start * rate), round(end * rate)]
    if not 0 <= samples[0] < samples[1] <= pcm["sample_count"]:
        raise CaptureError("capture interval exceeds native source extent")
    if not (rate + 9) // 10 <= samples[1] - samples[0] <= rate * 10:
        raise CaptureError("native capture duration must be between 0.1 and 10 seconds")
    # The frozen media validator checks a floating-point seconds subtraction.
    # Encode the exact native interval, shifting only the start by one ULP at
    # the interval's magnitude if that subtraction rounds outside its bounds.
    # Keeping end fixed preserves the original extent, including end-of-file.
    profile_seconds = [sample / rate for sample in samples]
    encoded_duration = profile_seconds[1] - profile_seconds[0]
    if encoded_duration < .1 or encoded_duration > 10:
        ulp = math.ulp(max(abs(value) for value in profile_seconds))
        profile_seconds[0] += -ulp if encoded_duration < .1 else ulp
    if (not .1 <= profile_seconds[1] - profile_seconds[0] <= 10
            or [round(value * rate) for value in profile_seconds] != samples
            or not 0 <= profile_seconds[0] < profile_seconds[1] <= pcm["sample_count"] / rate):
        raise CaptureError("native capture cannot be encoded within frozen profile bounds")
    controls = {"reduction_db": reduction_db, "noise_floor_db": noise_floor_db,
                "adaptivity": adaptivity, "gain_smooth": gain_smooth,
                "integrated_lufs": integrated_lufs, "true_peak_dbtp": true_peak_dbtp}
    for key, (low, high) in CONTROL_LIMITS.items():
        numeric(controls[key], low, high, key)
    integer(gain_smooth, 0, 50, "gain_smooth")
    if peaking_eq is not None:
        controls["peaking_eq"] = peaking_eq
    if compressor is not None:
        controls["compressor"] = compressor
    try:
        planned_stages = media.post_denoise_filters(controls, rate)
    except (media.MediaError, OverflowError) as exc:
        raise CaptureError(str(exc)) from exc
    review, review_hash = read_json(review_path, MAX_REVIEW_BYTES, deadline, "source review")
    validate_review(review, source_hash, manifest_hash, pcm_hash, samples, rate)
    contexts = {}
    input_bindings = [(source, source_hash, MAX_SOURCE_BYTES, "original source"),
                      (pcm_path, pcm_hash, MAX_PCM_BYTES, "source PCM"),
                      (manifest_path, manifest_hash, MAX_MANIFEST_BYTES, "source manifest"),
                      (review_path, review_hash, MAX_REVIEW_BYTES, "source review")]
    for name in ("instrument.json", "capture-context.json"):
        path = safe_path(ROOT / "program" / name)
        context, digest = read_json(path, MAX_CONTEXT_BYTES, deadline, name)
        integer(context.get("schema_version"), 1, 1, f"{name} schema_version")
        if name == "instrument.json":
            if (context.get("string_count") != 9 or context.get("tuning_direction") != "lowest_to_highest"
                    or not isinstance(context.get("strings"), list) or len(context["strings"]) != 9):
                raise CaptureError("instrument context must retain the registered nine-string tuning")
        else:
            artists = context.get("tone_reference_artists")
            if (not isinstance(artists, list) or len(artists) != 6
                    or any(not isinstance(artist, dict) or not isinstance(artist.get("name"), str)
                           or not artist["name"].strip() for artist in artists)):
                raise CaptureError("capture context must retain six artist references")
        contexts[name] = {"path": str(path), "sha256": digest, "snapshot": context}
        input_bindings.append((path, digest, MAX_CONTEXT_BYTES, name))
    settings_digest = hashlib.sha256(json_bytes(controls, MAX_PROFILE_BYTES)).hexdigest()
    capture = {"requested_seconds": [start, end], "native_samples": samples,
               "actual_seconds": [sample / rate for sample in samples],
               "profile_seconds": profile_seconds,
               "profile_seconds_encoding": "Native sample bounds divided by rate; start adjusted by at most one interval-scale ULP only for frozen-validator duration roundoff; native bounds unchanged.",
               "audio_origin_seconds": origin,
               "source_media_span_seconds": ([origin + sample / rate for sample in samples] if origin is not None else None),
               "time_axis": "decoded_source_audio_samples",
               "sample_rounding": "Python round(seconds * native sample_rate), matching frozen media worker",
               "noise_only_verified": False}
    status = "authored_unrendered"
    if review["review_status"] == "rejected_contaminated" or any(review[key] == "reviewed_present" for key in ("music_status", "click_status")):
        status = "needs_reselection"
    elif review["authorization_scope"] == "profile_authoring":
        status = "draft_authorization_incomplete"
    identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex
    parent = run_dir / "capture-profiles"
    if parent.is_symlink():
        raise CaptureError("capture profile output parent is a symlink")
    parent.mkdir(mode=0o700, exist_ok=True)
    safe_path(parent, directory=True)
    final = parent / identifier
    if final.exists():
        raise CaptureError("authoring output already exists")
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
    try:
        profile_path = None
        profile_hash = None
        profile = {"schema_version": 1, "name": f"source-{source_hash[:12]}-{settings_digest[:12]}",
                   "denoise": True, "preserve_low_fundamental_hz": 32, **controls,
                   "noise_capture_seconds": profile_seconds,
                   "noise_capture_authorized": status == "authored_unrendered",
                   "noise_capture_source_sha256": source_hash,
                   "noise_capture_review": (f"Selected by {review['selected_by']}; reviewed by {review['reviewed_by']}; "
                                            f"scope {review['authorization_scope']}; supplied assertions, not authenticated listening. "
                                            f"Music {review['music_status']}; clicks {review['click_status']}. " + review["note"])[:2000],
                   "description": "Source-bound authored experimental settings; no audio processing, learned band shape, separation or listening acceptance occurred during authoring."}
        proposal_path = None
        if status != "needs_reselection":
            name = "profile.json" if status == "authored_unrendered" else "proposal.json"
            raw = json_bytes(profile, MAX_PROFILE_BYTES)
            (staging / name).write_bytes(raw)
            if status == "authored_unrendered":
                try:
                    media.load_profile(staging / name)
                except media.MediaError as exc:
                    raise CaptureError(str(exc)) from exc
                profile_path = str(final / name)
                profile_hash = hashlib.sha256(raw).hexdigest()
            else:
                proposal_path = str(final / name)
        warnings = ["Review and authorization identities are supplied assertions, not authenticated.",
                    "Quiet/click/tone diagnostics do not establish a fan-only capture or isolated guitar stem.",
                    "Captured band shape is learned only by a separately authorized render; the absolute noise floor remains an explicit control."]
        if review["ambient_music_status"] in {"suspected", "reviewed_present"}:
            warnings.append("Ambient music is reported or suspected; no automatic separation or fan-noise classification is authorized by authoring.")
        if planned_stages:
            warnings.append("Planned EQ has frequency-dependent phase and compression changes amplitude; pure denoise residue cannot describe these later stages.")
        worker_hash = hash_file(Path(__file__).resolve(), deadline, MAX_MANIFEST_BYTES, "authoring worker")
        validator_hash = hash_file(REPO / "scripts/media.py", deadline, MAX_MANIFEST_BYTES, "frozen profile validator")
        input_bindings += [(Path(__file__).resolve(), worker_hash, MAX_MANIFEST_BYTES, "authoring worker"),
                           (REPO / "scripts/media.py", validator_hash, MAX_MANIFEST_BYTES, "frozen profile validator")]
        receipt = {"schema_version": 1, "tool": "capture_profile", "status": status,
                   "evidence_kind": "source_bound_profile_authoring", "created_utc": datetime.now(timezone.utc).isoformat(),
                   "source": {"path": str(source), "sha256": source_hash},
                   "baseline": {"run_dir": str(run_dir), "manifest_sha256": manifest_hash,
                                "pcm_path": str(pcm_path), "pcm_sha256": pcm_hash, "pcm": pcm,
                                "binding_scope": "current supplied baseline hashes/native header verified; original-to-PCM decoder history is retained, not independently rerun"},
                   "capture": capture, "review": {"path": str(review_path), "sha256": review_hash,
                                                  "assertions": review, "identity_authenticated": False},
                   "settings": controls, "settings_sha256": settings_digest,
                   "context": contexts, "planned_post_denoise_stages": planned_stages,
                   "profile_path": profile_path, "profile_sha256": profile_hash, "proposal_path": proposal_path,
                   "producer": {"worker_sha256": worker_hash, "validator_sha256": validator_hash,
                                "python_version": sys.version.split()[0],
                                "identity_scope": "current source-file hashes observed and rechecked during authoring; not code signing or remote attestation"},
                   "bounds": {"timeout_seconds": timeout_seconds, "original_source_bytes_max": MAX_SOURCE_BYTES,
                              "native_pcm_bytes_max": MAX_PCM_BYTES, "receipt_bytes_max": MAX_RECEIPT_BYTES},
                   "dsp_performed": False, "audio_decoded": False, "learned_band_shape": False,
                   "native_header_inspection": "bounded stdlib RIFF/WAVE fmt/data parsing; PCM payload is sought over, never decoded",
                   "listening_accepted": False, "warnings": warnings}
        raw_receipt = json_bytes(receipt, MAX_RECEIPT_BYTES)
        (staging / "receipt.json").write_bytes(raw_receipt)
        # Check every input again before atomically publishing owned metadata.
        for path, expected, bound, label in input_bindings:
            if hash_file(path, deadline, bound, label) != expected:
                raise CaptureError(f"{label} changed before publication", "source_changed")
        deadline.check()
        summary = {"schema_version": 1, "tool": "capture_profile", "status": status,
                   "evidence_kind": "source_bound_profile_authoring", "run_dir": str(run_dir),
                   "output_dir": str(final), "source_sha256": source_hash,
                   "profile_path": profile_path, "profile_sha256": profile_hash,
                   "proposal_path": proposal_path,
                   "receipt_path": str(final / "receipt.json"),
                   "receipt_sha256": hashlib.sha256(raw_receipt).hexdigest(),
                   "capture": {key: capture[key] for key in ("requested_seconds", "native_samples", "source_media_span_seconds")},
                   "dsp_performed": False, "listening_accepted": False}
        json_bytes(summary, MAX_RESULT_BYTES)
        publish_directory(staging, final)
        return summary
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--review", required=True)
    for flag, target in (("capture-start", "capture_start_seconds"), ("capture-end", "capture_end_seconds"),
                         ("reduction-db", "reduction_db"), ("noise-floor-db", "noise_floor_db"),
                         ("adaptivity", "adaptivity"), ("integrated-lufs", "integrated_lufs"),
                         ("true-peak-dbtp", "true_peak_dbtp")):
        parser.add_argument(f"--{flag}", dest=target, required=True, type=float)
    parser.add_argument("--gain-smooth", type=int, required=True)
    parser.add_argument("--eq", type=float, nargs=3, action="append")
    for key in ("threshold-db", "ratio", "attack-ms", "release-ms", "knee-db"):
        parser.add_argument(f"--compressor-{key}", type=float)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    args = vars(parser.parse_args(argv))
    input_value, run_dir_value, review_value = args.pop("input"), args.pop("run_dir"), args.pop("review")
    eq = args.pop("eq")
    compressor = {key: args.pop(f"compressor_{key}") for key in ("threshold_db", "ratio", "attack_ms", "release_ms", "knee_db")}
    previous_handler = None
    alarm_started = None
    previous_timer = None
    try:
        seconds = integer(args["timeout_seconds"], 1, 60, "timeout_seconds")
        # The standalone Unix worker also interrupts a blocking local read;
        # chunk/deadline checks alone cannot stop a stalled read system call.
        previous_handler = signal.getsignal(signal.SIGALRM)
        previous_timer = signal.getitimer(signal.ITIMER_REAL)
        if previous_timer != (0.0, 0.0):
            raise CaptureError("standalone authoring worker has an existing timer")
        def expired(signum, frame):
            raise CaptureError("capture-profile authoring deadline exceeded", "deadline_exceeded")
        signal.signal(signal.SIGALRM, expired)
        alarm_started = time.monotonic()
        signal.setitimer(signal.ITIMER_REAL, seconds)
        if any(value is not None for value in compressor.values()) and any(value is None for value in compressor.values()):
            raise CaptureError("compressor flags must be all-or-none")
        result = author(input_value, run_dir_value, review_value, **args,
                        peaking_eq=[dict(zip(("frequency_hz", "gain_db", "q"), band)) for band in eq] if eq else None,
                        compressor=compressor if all(value is not None for value in compressor.values()) else None)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (CaptureError, OSError) as exc:
        error = {"schema_version": 1, "tool": "capture_profile", "status": "error",
                 "evidence_kind": "source_bound_profile_authoring",
                 "error": {"code": getattr(exc, "code", "io_failed"), "message": str(exc)[:1000]},
                 "dsp_performed": False, "listening_accepted": False}
        print(json.dumps(error, sort_keys=True, allow_nan=False))
        return 2
    finally:
        if alarm_started is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)


if __name__ == "__main__":
    raise SystemExit(main())
