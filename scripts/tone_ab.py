#!/usr/bin/env python3
"""S2 tone_ab: stage-attributed, level-matched band/attack A/B over an existing run.

Experimental helper for lane tone_ab (sprint 20261006-s2, TIN-5601). The frozen
contract and preregistration are in docs/spec/sprints/TONE_S2.md (commit
9bc259d6cf964cab8498e4e90ae6ae27f85be3fc). Stdlib plus FFmpeg/FFprobe only.

The helper reads an existing run's stage files read-only, verifies each against
the run manifest (sha256 and native RIFF extent), measures integrated LUFS and a
static gain match over an explicit common region, reports six mixture-band
energies and 20 ms attack energy/centroid at hash-bound analysis positions, and
renders one reversible low-shelf trial plus three blind 15 s excerpt pairs into a
fresh output directory. It never writes into a run directory, never adopts a
default, profile or master, and never claims listening, room-response recovery,
note correctness or fan/music separation.
"""
from __future__ import annotations

import argparse
import array
import cmath
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import statistics
import struct
import subprocess
import sys
import time
import types
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import media  # noqa: E402  (repository stdlib FFmpeg helpers)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
TOOL = "tone_ab"
SPEC = "docs/spec/sprints/TONE_S2.md"
SPEC_COMMIT = "9bc259d6cf964cab8498e4e90ae6ae27f85be3fc"
RULING = ("R-N13; R-HOOK-CONVERGENCE-20261004; TIN-3692 comment "
          "98cf680c-7299-4949-bfb2-60079053ad43")
SKILL = ".agents/skills/guitar-tone-ab/SKILL.md"

SETUP_EXCLUDED_SECONDS = 5.0
MIN_REGION_SECONDS = 45.0
EXCERPT_SECONDS = 15.0
EXCERPT_COUNT = 3
TIMEOUT_DEFAULT = 1200
TIMEOUT_MIN = 1
TIMEOUT_MAX = 1800
SUBPROCESS_CAP_SECONDS = 120.0
FFPROBE_CAP_SECONDS = 60.0
MATCH_TOLERANCE_LU = 0.3
MAX_MATCH_CORRECTIONS = 3
BANDS = ((20, 45), (45, 90), (90, 160), (160, 400), (400, 2000), (2000, 8000))
WELCH_N = 16384
ATTACK_WINDOW_SECONDS = 0.020
CENTROID_LOW_HZ = 20.0
CENTROID_HIGH_HZ = 20000.0
BLIND_SEED = 20261006
TRIAL_LABEL = "trial_lowshelf"
TRIAL_STATUS = "rejected_or_unreviewed_trial"
TRIAL_CONTROLS = {"type": "lowshelf", "frequency_hz": 100.0, "width_type": "q",
                  "width": 0.7, "gain_db": 1.5, "precision": "f64"}
CURRENT_SCHEMA_MIN_HZ = 160  # media.validate_post_controls EQ frequency floor
MAX_JSON_BYTES = 64 * 1024 * 1024
INPUT_FIELDS = ("run_dir", "candidate_run_dir", "common_region_start",
                "common_region_end", "timeout_seconds")
REQUIRED_FIELDS = ("run_dir", "common_region_start", "common_region_end")
MAX_REGION_SECONDS = 86400.0

# (label, manifest output key, default file, required, stage meaning)
STAGES = (
    ("source", "source", "source.wav", True,
     "Decoded native source PCM"),
    ("pure_denoise", "denoised", "denoised.wav", True,
     "Pure denoise stage output (latency-compensated); see manifest restoration_stages"),
    ("tone_dynamics_pre_gain", "processed", "processed.wav", False,
     "Post-denoise EQ and compressor combined, before delivery gain; EQ and compressor "
     "cannot be separated from this file"),
    ("delivery_master", "cleaned", "cleaned.wav", True,
     "Delivery PCM after loudness normalization (mode copied from manifest)"),
)
CANDIDATE_STAGES = ("pure_denoise", "tone_dynamics_pre_gain", "delivery_master")
STAGE_DELTAS = (
    ("denoise_stage", "pure_denoise", "source"),
    ("tone_dynamics_stage_combined", "tone_dynamics_pre_gain", "pure_denoise"),
    ("delivery_normalization", "delivery_master", "tone_dynamics_pre_gain"),
    ("end_to_end", "delivery_master", "source"),
    ("trial", TRIAL_LABEL, "delivery_master"),
)

UNKNOWN_FIELDS = {
    "operator_preference": (None, "The operator has not listened to the blind excerpt pairs; "
                            "preference is operator-owned listening evidence (class L)."),
    "listening_accepted": (False, "No listening review exists for these renders; numbers alone "
                           "never close the thin/nasal feedback."),
    "room_response_recovered": (False, "No capture-chain, microphone or room measurement exists; "
                                "EQ cannot recreate uncaptured room or amp response."),
    "perceived_fullness": (None, "Perceived fullness is a listening judgement; band energy is "
                           "not perception."),
    "nasal_quality": (None, "Nasal quality is a listening judgement; mid-band share is not "
                      "perception."),
    "fan_only_gain": (None, "Band levels are mixture energy; fan and music are not separated."),
    "music_only_gain": (None, "Band levels are mixture energy; fan and music are not separated."),
    "fundamental_32hz_presence": (None, "A 20-45 Hz band level is mixture energy, not a measured "
                                  "played C1 fundamental."),
    "capture_chain_response": (None, "Phone/Photo Booth microphone, AGC and codec response were "
                               "not measured."),
    "monitoring_device": (None, "The operator's playback device and level are unknown."),
    "attack_identity": ("unverified", "Attack positions are detector hypotheses (periodic "
                        "high-frequency transients and superflux candidates); they may be clicks, "
                        "picks or noise and are not verified notes or a metronome."),
    "true_peak_dbtp": (None, "True peak was not measured; only sample peak is reported."),
    "stage_separation_eq_vs_compressor": ("not_separable_combined_stage",
                                          "processed.wav contains EQ and compressor together; no "
                                          "intermediate file isolates either."),
    "default_adopted": (False, "This lane never adopts a default detector, profile or master."),
    "master_changed": (False, "The accepted master is read-only; protected readback verifies it."),
}


class ToneABError(RuntimeError):
    """Refusal or failure with a stable code."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Closed input schema
# ---------------------------------------------------------------------------

def _finite_number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToneABError("invalid_arguments", f"{name} must be a finite number, not {type(value).__name__}")
    result = float(value)
    if not math.isfinite(result):
        raise ToneABError("invalid_arguments", f"{name} must be finite")
    return result


def _path_text(value, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096 or "\x00" in value:
        raise ToneABError("invalid_arguments", f"{name} must be a non-empty local path string")
    if "://" in value:
        raise ToneABError("invalid_arguments", f"{name} must be a local path, not a URL")
    return value


def validate_arguments(arguments) -> dict:
    """Closed schema: unknown fields, booleans-as-numbers and non-finite values refuse."""
    if not isinstance(arguments, dict):
        raise ToneABError("invalid_arguments", "arguments must be an object")
    unknown = sorted(set(arguments) - set(INPUT_FIELDS))
    if unknown:
        raise ToneABError("invalid_arguments", f"unknown fields: {unknown}")
    missing = [field for field in REQUIRED_FIELDS if field not in arguments]
    if missing:
        raise ToneABError("invalid_arguments", f"missing required fields: {missing}")
    result = {"run_dir": _path_text(arguments["run_dir"], "run_dir"),
              "candidate_run_dir": None}
    if arguments.get("candidate_run_dir") is not None:
        result["candidate_run_dir"] = _path_text(arguments["candidate_run_dir"], "candidate_run_dir")
    start = _finite_number(arguments["common_region_start"], "common_region_start")
    end = _finite_number(arguments["common_region_end"], "common_region_end")
    timeout = arguments.get("timeout_seconds", TIMEOUT_DEFAULT)
    if isinstance(timeout, bool) or not isinstance(timeout, int):
        raise ToneABError("timeout_out_of_bounds", "timeout_seconds must be an integer")
    if not TIMEOUT_MIN <= timeout <= TIMEOUT_MAX:
        raise ToneABError("timeout_out_of_bounds",
                          f"timeout_seconds must be {TIMEOUT_MIN}..{TIMEOUT_MAX}")
    if start < SETUP_EXCLUDED_SECONDS:
        raise ToneABError("region_out_of_bounds",
                          f"common_region_start must be >= {SETUP_EXCLUDED_SECONDS} s; the 0-5 s "
                          "setup guitar/amp and windup interval is never measured")
    if end > MAX_REGION_SECONDS:
        raise ToneABError("region_out_of_bounds", "common_region_end exceeds the schema maximum")
    if end <= start:
        raise ToneABError("region_out_of_bounds", "common_region_end must exceed common_region_start")
    if end - start < MIN_REGION_SECONDS:
        raise ToneABError("region_out_of_bounds",
                          f"common region must be >= {MIN_REGION_SECONDS} s so three "
                          f"{EXCERPT_SECONDS:g} s excerpts fit without overlap")
    result.update(common_region_start=start, common_region_end=end, timeout_seconds=timeout)
    return result


def exact_directory(value: str, name: str) -> Path:
    """Exact local directory: no '..' and no symlink component (tool_api convention)."""
    original = Path(value).expanduser().absolute()
    if ".." in original.parts:
        raise ToneABError("invalid_arguments", f"{name} cannot contain '..' components")
    current = Path(original.anchor)
    for part in original.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ToneABError("invalid_arguments", f"{name} cannot contain a symlink component: {current}")
    if not original.is_dir():
        raise ToneABError("run_dir_missing", f"{name} is not an existing directory: {original}")
    return original


def region_samples(start: float, end: float, pcm: dict) -> dict:
    rate, count = pcm["sample_rate"], pcm["sample_count"]
    duration = count / rate
    if end > duration + 1e-9:
        raise ToneABError("region_out_of_bounds",
                          f"common_region_end {end} exceeds run duration {duration:.6f} s")
    start_sample, end_sample = round(start * rate), min(round(end * rate), count)
    return {"start_seconds": start, "end_seconds": end, "start_sample": start_sample,
            "end_sample_exclusive": end_sample, "frames": end_sample - start_sample,
            "sample_rate": rate, "rounding": "round(seconds * native_rate); end exclusive",
            "excluded_setup_interval_seconds": [0.0, SETUP_EXCLUDED_SECONDS]}


# ---------------------------------------------------------------------------
# Files, RIFF parsing, hashing, protected readback
# ---------------------------------------------------------------------------

def load_json_file(path: Path, code: str) -> dict:
    try:
        if path.is_symlink() or not path.is_file():
            raise ToneABError(code, f"{path} is not a regular file")
        if path.stat().st_size > MAX_JSON_BYTES:
            raise ToneABError(code, f"{path} exceeds {MAX_JSON_BYTES} bytes")
        def reject(value):
            raise ValueError(f"non-finite JSON constant {value}")
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle, parse_constant=reject)
    except (OSError, ValueError) as error:
        raise ToneABError(code, f"{path}: {error}") from error
    if not isinstance(data, dict):
        raise ToneABError(code, f"{path} is not a JSON object")
    return data


def read_wav_header(path: Path) -> dict:
    """Stdlib RIFF/WAVE parser for format tags 1, 3 and 0xFFFE."""
    with path.open("rb") as handle:
        head = handle.read(12)
        if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            raise ToneABError("native_extent_mismatch", f"{path.name} is not RIFF/WAVE")
        fmt = None
        for _ in range(256):
            chunk = handle.read(8)
            if len(chunk) < 8:
                break
            chunk_id, size = chunk[:4], struct.unpack("<I", chunk[4:])[0]
            if chunk_id == b"fmt ":
                body = handle.read(size)
                if len(body) < 16:
                    raise ToneABError("native_extent_mismatch", f"{path.name} fmt chunk too short")
                tag, channels, rate, _byte_rate, block_align, bits = struct.unpack("<HHIIHH", body[:16])
                container = tag
                if tag == 0xFFFE:
                    if len(body) < 40:
                        raise ToneABError("native_extent_mismatch",
                                          f"{path.name} extensible fmt chunk too short")
                    tag = struct.unpack("<H", body[24:26])[0]
                fmt = {"format_tag": tag, "container_format_tag": container, "channels": channels,
                       "sample_rate": rate, "bits_per_sample": bits, "block_align": block_align}
                if size & 1:
                    handle.read(1)
            elif chunk_id == b"data":
                if fmt is None:
                    raise ToneABError("native_extent_mismatch", f"{path.name} data before fmt")
                if fmt["format_tag"] not in (1, 3):
                    raise ToneABError("native_extent_mismatch",
                                      f"{path.name} unsupported format tag {fmt['format_tag']}")
                if fmt["block_align"] <= 0 or size == 0xFFFFFFFF or size % fmt["block_align"]:
                    raise ToneABError("native_extent_mismatch",
                                      f"{path.name} data size is not whole frames")
                return dict(fmt, data_offset=handle.tell(), data_bytes=size,
                            frames=size // fmt["block_align"], parser="stdlib_riff")
            else:
                handle.seek(size + (size & 1), os.SEEK_CUR)
    raise ToneABError("native_extent_mismatch", f"{path.name} has no data chunk")


def read_wav_samples(path: Path) -> tuple[array.array, dict]:
    """Interleaved float samples for 16/24/32-bit PCM and 32-bit float WAV."""
    header = read_wav_header(path)
    with path.open("rb") as handle:
        handle.seek(header["data_offset"])
        raw = handle.read(header["data_bytes"])
    tag, bits = header["format_tag"], header["bits_per_sample"]
    out = array.array("f")
    if tag == 3 and bits == 32:
        out.frombytes(raw)
        if sys.byteorder == "big":
            out.byteswap()
    elif tag == 1 and bits == 16:
        values = array.array("h")
        values.frombytes(raw)
        if sys.byteorder == "big":
            values.byteswap()
        out = array.array("f", (v / 32768.0 for v in values))
    elif tag == 1 and bits == 24:
        out = array.array("f", (int.from_bytes(raw[i:i + 3], "little", signed=True) / 8388608.0
                                for i in range(0, len(raw), 3)))
    elif tag == 1 and bits == 32:
        values = array.array("i")
        values.frombytes(raw)
        if sys.byteorder == "big":
            values.byteswap()
        out = array.array("f", (v / 2147483648.0 for v in values))
    else:
        raise ToneABError("native_extent_mismatch", f"{path.name} unsupported sample format")
    return out, header


def snapshot(directory: Path) -> dict:
    """sha256/size/mtime of every regular file (recursive, symlinks not followed)."""
    files = {}
    for root, dirs, names in os.walk(directory, followlinks=False):
        dirs.sort()
        for name in sorted(names):
            path = Path(root) / name
            relative = str(path.relative_to(directory))
            stat = os.lstat(path)
            if path.is_symlink():
                files[relative] = {"symlink": True, "target": os.readlink(path)}
            elif path.is_file():
                files[relative] = {"sha256": media.sha256(path), "size": stat.st_size,
                                   "mtime_ns": stat.st_mtime_ns}
    return files


def compare_snapshots(before: dict, after: dict) -> list[str]:
    return sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))


def is_protected_location(path: Path, protected: list[Path]) -> bool:
    for directory in protected:
        if path == directory or path.is_relative_to(directory):
            return True
    parts = path.parts
    return any(parts[i] == "artifacts" and parts[i + 1] == "runs" for i in range(len(parts) - 1))


# ---------------------------------------------------------------------------
# Bounded subprocesses
# ---------------------------------------------------------------------------

class Runner:
    """One child at a time; each timeout is min(cap, remaining overall deadline)."""

    def __init__(self, deadline: float):
        self.deadline = deadline
        self.commands: list[dict] = []

    def remaining(self) -> float:
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise ToneABError("deadline_exceeded", "overall timeout_seconds deadline exceeded")
        return left

    def check(self):
        self.remaining()

    def run(self, command: list[str], cap: float = SUBPROCESS_CAP_SECONDS) -> subprocess.CompletedProcess:
        timeout = min(cap, self.remaining())
        started = time.monotonic()
        try:
            result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as error:
            raise ToneABError("deadline_exceeded",
                              f"{Path(command[0]).name} exceeded {timeout:.1f} s") from error
        except OSError as error:
            raise ToneABError("ffmpeg_failed", f"{Path(command[0]).name} could not start: {error}") from error
        self.commands.append({"argv": [Path(command[0]).name, *command[1:]],
                              "timeout_seconds": round(timeout, 3),
                              "elapsed_seconds": round(time.monotonic() - started, 3),
                              "returncode": result.returncode})
        if result.returncode:
            tail = result.stderr.decode("utf-8", "replace")[-2000:]
            raise ToneABError("ffmpeg_failed", f"{Path(command[0]).name} failed ({result.returncode}): {tail}")
        return result

    def ffmpeg(self, arguments: list[str], loglevel: str = "info") -> subprocess.CompletedProcess:
        try:
            binary = media.executable("ffmpeg")
        except media.MediaError as error:
            raise ToneABError("ffmpeg_unavailable", str(error)) from error
        return self.run([binary, "-hide_banner", "-nostdin", "-nostats", "-loglevel", loglevel,
                         "-threads", media.THREADS, "-filter_threads", media.THREADS, *arguments])


def ffprobe_extent(runner: Runner, path: Path) -> dict | None:
    try:
        binary = media.executable("ffprobe")
    except media.MediaError:
        return None
    result = runner.run([binary, "-v", "error", "-select_streams", "a:0", "-show_entries",
                         "stream=sample_rate,channels,duration_ts,time_base", "-of", "json", str(path)],
                        cap=FFPROBE_CAP_SECONDS)
    try:
        stream = json.loads(result.stdout)["streams"][0]
        numerator, denominator = (int(v) for v in stream["time_base"].split("/"))
        rate = int(stream["sample_rate"])
        frames = round(int(stream["duration_ts"]) * numerator * rate / denominator)
        return {"sample_rate": rate, "channels": int(stream["channels"]), "frames": frames}
    except (KeyError, IndexError, ValueError, TypeError, ZeroDivisionError) as error:
        raise ToneABError("native_extent_mismatch", f"ffprobe extent unreadable for {path.name}") from error


def region_filter(start_sample: int, end_sample: int) -> str:
    return f"atrim=start_sample={start_sample}:end_sample={end_sample}"


def gain_filter(gain_db: float) -> str:
    return f"volume={gain_db:.6f}dB:precision=double"


def measure_lufs(runner: Runner, path: Path, region: dict, gain_db: float | None = None) -> float | None:
    chain = [region_filter(region["start_sample"], region["end_sample_exclusive"])]
    if gain_db is not None:
        chain.append(gain_filter(gain_db))
    chain.append("loudnorm=print_format=json")
    result = runner.ffmpeg(["-i", str(path), "-map", "0:a:0", "-af", ",".join(chain), "-f", "null", "-"])
    try:
        data = media.loudnorm_json(types.SimpleNamespace(stderr=result.stderr.decode("utf-8", "replace")))
    except media.MediaError as error:
        raise ToneABError("loudness_unavailable", str(error)) from error
    return media.number(data.get("input_i"))


def decode_region(runner: Runner, path: Path, region: dict, channels: int) -> array.array:
    result = runner.ffmpeg(["-i", str(path), "-map", "0:a:0", "-af",
                            region_filter(region["start_sample"], region["end_sample_exclusive"]),
                            "-c:a", "pcm_f32le", "-f", "f32le", "-"], loglevel="error")
    samples = array.array("f")
    samples.frombytes(result.stdout)
    if sys.byteorder == "big":
        samples.byteswap()
    expected = region["frames"] * channels
    if len(samples) != expected:
        raise ToneABError("decode_extent_mismatch",
                          f"{path.name} decoded {len(samples)} samples, expected {expected}")
    return samples


def trial_filter(gain_db: float = TRIAL_CONTROLS["gain_db"]) -> str:
    return (f"lowshelf=f={TRIAL_CONTROLS['frequency_hz']:g}:t=q:w={TRIAL_CONTROLS['width']:g}:"
            f"g={gain_db:g}:r=f64")


def render_trial(runner: Runner, source: Path, output: Path, pcm: dict,
                 gain_db: float = TRIAL_CONTROLS["gain_db"]) -> dict:
    """Full native extent, f32 so it cannot clip; never touches the input file."""
    audio_filter = trial_filter(gain_db)
    runner.ffmpeg(["-i", str(source), "-map", "0:a:0", "-af", audio_filter, "-c:a", "pcm_f32le",
                   "-f", "wav", str(output)])
    header = read_wav_header(output)
    if (header["sample_rate"], header["channels"], header["frames"]) != (
            pcm["sample_rate"], pcm["channels"], pcm["sample_count"]):
        raise ToneABError("trial_extent_mismatch",
                          f"trial render extent {header['frames']} differs from {pcm['sample_count']}")
    return {"filter": audio_filter, "header": header}


# ---------------------------------------------------------------------------
# Loudness match (pure logic, testable with a fake meter)
# ---------------------------------------------------------------------------

def match_gains(labels: list[str], measure, tolerance: float = MATCH_TOLERANCE_LU,
                max_corrections: int = MAX_MATCH_CORRECTIONS) -> dict:
    """measure(label, gain_db|None) -> LUFS|None. Target = min LUFS; every gain <= 0 dB."""
    before = {label: measure(label, None) for label in labels}
    undefined = sorted(label for label, value in before.items() if value is None)
    if undefined:
        return {"target_lufs": None, "match_lu_delta": None, "match_status": "unmatched",
                "reason": f"undefined_integrated_loudness: {undefined}",
                "per_arm": {label: {"lufs_before": before[label], "gain_db": None, "lufs_after": None,
                                    "iterations": []} for label in labels}}
    target = min(before.values())
    per_arm = {}
    for label in labels:
        gain = target - before[label]
        after = measure(label, gain)
        iterations = [{"gain_db": gain, "lufs_after": after}]
        clamped = False
        corrections = 0
        while after is not None and abs(after - target) > tolerance and corrections < max_corrections:
            proposed = gain + (target - after)
            clamped = clamped or proposed > 0
            gain = min(0.0, proposed)
            after = measure(label, gain)
            iterations.append({"gain_db": gain, "lufs_after": after})
            corrections += 1
        per_arm[label] = {"lufs_before": before[label], "gain_db": gain, "lufs_after": after,
                          "abs_delta_lu": abs(after - target) if after is not None else None,
                          "corrections": corrections, "clamped_to_non_positive": clamped,
                          "iterations": iterations}
    deltas = [value["abs_delta_lu"] for value in per_arm.values()]
    if any(delta is None for delta in deltas):
        return {"target_lufs": target, "match_lu_delta": None, "match_status": "unmatched",
                "reason": "undefined_loudness_after_gain", "per_arm": per_arm}
    delta = max(deltas)
    matched = delta <= tolerance
    return {"target_lufs": target, "match_lu_delta": delta,
            "match_status": "matched" if matched else "unmatched",
            "reason": None if matched else f"residual {delta:.3f} LU exceeds {tolerance} LU after "
                                           f"{max_corrections} corrections",
            "per_arm": per_arm}


# ---------------------------------------------------------------------------
# Spectral measurements (stdlib FFT)
# ---------------------------------------------------------------------------

_TWIDDLES: dict[int, list[complex]] = {}


def _twiddles(n: int) -> list[complex]:
    table = _TWIDDLES.get(n)
    if table is None:
        table = _TWIDDLES[n] = [cmath.exp(-2j * math.pi * k / n) for k in range(n // 2)]
    return table


def fft(values: list[complex]) -> list[complex]:
    """Recursive radix-2 decimation-in-time FFT (power-of-two length)."""
    n = len(values)
    if n == 1:
        return list(values)
    if n == 2:
        a, b = values
        return [a + b, a - b]
    even, odd = fft(values[0::2]), fft(values[1::2])
    twisted = [o * w for o, w in zip(odd, _twiddles(n))]
    return [e + t for e, t in zip(even, twisted)] + [e - t for e, t in zip(even, twisted)]


def rfft_power(x: list[float], kmax: int | None = None) -> list[float]:
    """|X_k|^2 for k = 0..kmax (<= N/2) of a real power-of-two-length sequence."""
    n = len(x)
    if n < 4 or n & (n - 1):
        raise ValueError("rfft length must be a power of two >= 4")
    half = n // 2
    kmax = half if kmax is None else min(kmax, half)
    spectrum = fft([complex(a, b) for a, b in zip(x[0::2], x[1::2])])
    twiddle = _twiddles(n)
    out = [0.0] * (kmax + 1)
    z0 = spectrum[0]
    out[0] = (z0.real + z0.imag) ** 2
    for k in range(1, kmax + 1):
        if k == half:
            out[k] = (z0.real - z0.imag) ** 2
            break
        a, b = spectrum[k], spectrum[half - k].conjugate()
        value = (a + b) * 0.5 + twiddle[k] * ((a - b) * -0.5j)
        out[k] = value.real * value.real + value.imag * value.imag
    return out


def periodic_hann(n: int) -> list[float]:
    return [0.5 - 0.5 * math.cos(2 * math.pi * i / n) for i in range(n)]


def db10(value: float) -> float | None:
    return 10 * math.log10(value) if value > 0 else None


def band_energies(samples: array.array, channels: int, rate: int, check=lambda: None,
                  n: int = WELCH_N) -> dict:
    """Welch, periodic Hann, hop N, frames fully inside the decoded region.

    Band power = 2 * sum_{lo<=f_k<hi} |X_k|^2 / (N * sum w^2), averaged over frames
    and channels, so a sine of amplitude A reads A^2/2 (dB re 1.0 mean square).
    """
    nyquist = rate / 2
    window = periodic_hann(n)
    window_power = sum(w * w for w in window)
    kmax = min(n // 2, math.ceil(max(hi for _, hi in BANDS) * n / rate) + 1)
    frames = len(samples) // (n * channels)
    accumulated = [0.0] * (kmax + 1)
    for frame in range(frames):
        check()
        for channel in range(channels):
            begin = frame * n * channels + channel
            segment = samples[begin:begin + n * channels:channels]
            power = rfft_power([s * w for s, w in zip(segment, window)], kmax)
            accumulated = [a + b for a, b in zip(accumulated, power)]
    scale = 2.0 / (n * window_power * max(frames, 1) * channels)
    bands = []
    for low, high in BANDS:
        record = {"band": f"{low}-{high}", "low_hz": low, "high_hz_exclusive": high,
                  "frame_count": frames, "bin_width_hz": rate / n}
        if high >= nyquist:
            bands.append(dict(record, mean_square=None, level_dbfs_raw=None, bin_count=0,
                              status="above_nyquist"))
            continue
        bins = [k for k in range(kmax + 1) if low <= k * rate / n < high]
        energy = scale * sum(accumulated[k] for k in bins) if frames else None
        bands.append(dict(record, mean_square=energy, bin_count=len(bins),
                          level_dbfs_raw=db10(energy) if energy is not None else None,
                          status="measured" if energy else ("no_full_frame" if not frames else "zero_energy")))
    total = sum(b["mean_square"] for b in bands if b["mean_square"])
    for band in bands:
        band["share_db"] = (db10(band["mean_square"] / total)
                            if band["mean_square"] and total > 0 else None)
    return {"bands": bands, "frame_count": frames, "window": "periodic_hann", "frame_length": n,
            "hop": n, "channel_policy": "mean power across channels",
            "level_reference": "dB re 1.0 mean square (full-scale sine = -3.01 dBFS)"}


def attack_metrics(samples: array.array, channels: int, rate: int, region: dict,
                   positions: list[int], check=lambda: None) -> list[dict | None]:
    """20 ms window from each attack sample: mean-square dBFS and Hann centroid."""
    width = round(ATTACK_WINDOW_SECONDS * rate)
    nfft = 1 << (width - 1).bit_length()
    window = periodic_hann(width)
    high = min(CENTROID_HIGH_HZ, rate / 2)
    bins = [k for k in range(nfft // 2 + 1) if CENTROID_LOW_HZ <= k * rate / nfft <= high]
    results: list[dict | None] = []
    for index, position in enumerate(positions):
        if index % 64 == 0:
            check()
        offset = position - region["start_sample"]
        if offset < 0 or position + width > region["end_sample_exclusive"]:
            results.append(None)
            continue
        block = samples[offset * channels:(offset + width) * channels]
        mean_square = sum(v * v for v in block) / len(block)
        power_sum = [0.0] * (nfft // 2 + 1)
        for channel in range(channels):
            segment = block[channel::channels]
            padded = [s * w for s, w in zip(segment, window)] + [0.0] * (nfft - width)
            power_sum = [a + b for a, b in zip(power_sum, rfft_power(padded))]
        magnitude = [math.sqrt(p) for p in power_sum]
        weight = sum(magnitude[k] for k in bins)
        centroid = (sum(k * rate / nfft * magnitude[k] for k in bins) / weight) if weight > 0 else None
        results.append({"energy_dbfs_raw": db10(mean_square), "centroid_hz": centroid})
    return results


# ---------------------------------------------------------------------------
# Attack analysis binding
# ---------------------------------------------------------------------------

def find_attack_analysis(run_dir: Path, manifest: dict, denoised_sha: str, pcm: dict) -> dict:
    candidates = [("run_dir", run_dir / "analysis.json")]
    authoring = (manifest.get("capture_profile_application") or {}).get("authoring_dir")
    if isinstance(authoring, str) and authoring:
        authoring_path = Path(authoring)
        if authoring_path.is_absolute() and len(authoring_path.parents) >= 2:
            candidates.append(("parent_run_from_capture_profile_authoring_dir",
                               authoring_path.parents[1] / "analysis.json"))
    tried = []
    for basis, path in candidates:
        if not path.is_file() or path.is_symlink():
            tried.append({"path": str(path), "basis": basis, "status": "absent"})
            continue
        try:
            data = load_json_file(path, "analysis_unreadable")
        except ToneABError as error:
            tried.append({"path": str(path), "basis": basis, "status": error.code})
            continue
        lineage = data.get("source_lineage") or {}
        mapping = lineage.get("sample_mapping") or {}
        if lineage.get("analyzed_input_sha256") != denoised_sha:
            tried.append({"path": str(path), "basis": basis, "status": "analyzed_input_sha256_mismatch",
                          "analyzed_input_sha256": lineage.get("analyzed_input_sha256")})
            continue
        if (mapping.get("original_pcm_sample_rate") != pcm["sample_rate"]
                or mapping.get("original_pcm_sample_count") != pcm["sample_count"]):
            tried.append({"path": str(path), "basis": basis, "status": "native_extent_mismatch"})
            continue
        return {"status": "hash_bound", "path": str(path), "basis": basis,
                "sha256": media.sha256(path), "analyzed_input_sha256": denoised_sha,
                "data": data, "tried": tried}
    return {"status": "no_hash_bound_attack_analysis", "path": None, "sha256": None,
            "data": None, "tried": tried}


def _event_seconds(event) -> float | None:
    if not isinstance(event, dict):
        return None
    value = event.get("audio_relative_seconds")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def attack_panels(analysis: dict) -> dict:
    click_grid = analysis.get("click_grid") or {}
    events = analysis.get("events") if isinstance(analysis.get("events"), list) else []
    primary = click_grid.get("observed_events") if isinstance(click_grid.get("observed_events"), list) else []
    return {
        "primary": {"source": "click_grid.observed_events",
                    "identity": click_grid.get("identity",
                                               "periodic_high_frequency_transients_not_verified_metronome"),
                    "seconds": [_event_seconds(e) for e in primary]},
        "secondary": {"source": "events[kind=superflux_attack_candidate]",
                      "identity": "superflux_attack_candidate_not_note_identity",
                      "seconds": [_event_seconds(e) for e in events
                                  if isinstance(e, dict) and e.get("kind") == "superflux_attack_candidate"]},
    }


def _median(values):
    return statistics.median(values) if values else None


def _iqr(values):
    if len(values) < 2:
        return None
    q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return {"q1": q1, "q3": q3, "iqr": q3 - q1}


def summarize_attacks(per_arm: dict, gains: dict, references: dict) -> dict:
    summary = {}
    for label, rows in per_arm.items():
        gain = gains.get(label)
        energies = [r["energy_dbfs_raw"] for r in rows if r and r["energy_dbfs_raw"] is not None]
        centroids = [r["centroid_hz"] for r in rows if r and r["centroid_hz"] is not None]
        median_raw = _median(energies)
        iqr = _iqr(energies)
        record = {"count_with_energy": len(energies), "count_with_centroid": len(centroids),
                  "median_energy_dbfs_raw": median_raw,
                  "median_energy_dbfs_matched": (median_raw + gain) if (median_raw is not None
                                                                       and gain is not None) else None,
                  "energy_iqr_db": iqr, "median_centroid_hz": _median(centroids),
                  "paired_median_deltas": {}}
        for reference in references.get(label, ()):
            other = per_arm.get(reference)
            if other is None or reference == label:
                continue
            energy_deltas = [a["energy_dbfs_raw"] - b["energy_dbfs_raw"] for a, b in zip(rows, other)
                             if a and b and a["energy_dbfs_raw"] is not None and b["energy_dbfs_raw"] is not None]
            centroid_deltas = [a["centroid_hz"] - b["centroid_hz"] for a, b in zip(rows, other)
                               if a and b and a["centroid_hz"] is not None and b["centroid_hz"] is not None]
            raw = _median(energy_deltas)
            g_a, g_b = gains.get(label), gains.get(reference)
            record["paired_median_deltas"][f"vs_{reference}"] = {
                "pairs": len(energy_deltas),
                "energy_db_raw": raw,
                "energy_db_matched": (raw + g_a - g_b) if (raw is not None and g_a is not None
                                                           and g_b is not None) else None,
                "centroid_hz": _median(centroid_deltas), "centroid_pairs": len(centroid_deltas)}
        summary[label] = record
    return summary


# ---------------------------------------------------------------------------
# Arms and identity gate
# ---------------------------------------------------------------------------

def _pcm_from_manifest(manifest: dict, where: str) -> dict:
    pcm = manifest.get("pcm") or {}
    values = {key: pcm.get(key) for key in ("sample_rate", "channels", "sample_count")}
    if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in values.values()):
        raise ToneABError("native_extent_mismatch", f"{where} manifest.pcm lacks positive integer extent")
    return values


def _stage_file(run_dir: Path, manifest: dict, key: str, default: str) -> str | None:
    outputs = manifest.get("outputs") or {}
    name = outputs.get(key)
    if name is None:
        return None
    if not isinstance(name, str) or "/" in name or "\\" in name or name in ("", ".", ".."):
        raise ToneABError("stage_missing", f"manifest output {key} is not a plain file name")
    return name


def collect_arms(run_dir: Path, manifest: dict, files: dict, pcm: dict, runner: Runner,
                 prefix: str = "", stages=STAGES) -> tuple[list[dict], list[dict]]:
    hashes = manifest.get("output_sha256") or {}
    arms, absent = [], []
    for label, key, default, required, meaning in stages:
        full_label = prefix + label
        name = _stage_file(run_dir, manifest, key, default)
        reason = None
        if name is None:
            reason = f"manifest.outputs lacks {key}"
        elif name not in files or "sha256" not in files[name]:
            reason = f"{name} is not a regular file in run_dir"
        elif not isinstance(hashes.get(name), str):
            reason = f"manifest.output_sha256 lacks {name}"
        if reason:
            if required:
                code = "stage_hash_mismatch" if "output_sha256" in reason else "stage_missing"
                raise ToneABError(code, f"{full_label}: {reason}")
            absent.append({"label": full_label, "status": "absent", "reason": reason})
            continue
        path = run_dir / name
        actual = files[name]["sha256"]
        if actual != hashes[name]:
            raise ToneABError("stage_hash_mismatch",
                              f"{full_label} {name} sha256 {actual} != manifest {hashes[name]}")
        header = read_wav_header(path)
        riff = {"sample_rate": header["sample_rate"], "channels": header["channels"],
                "frames": header["frames"]}
        if (riff["sample_rate"], riff["channels"], riff["frames"]) != (
                pcm["sample_rate"], pcm["channels"], pcm["sample_count"]):
            raise ToneABError("native_extent_mismatch",
                              f"{full_label} {name} RIFF {riff} != manifest.pcm {pcm}")
        probed = ffprobe_extent(runner, path)
        if probed is not None and probed != riff:
            raise ToneABError("native_extent_mismatch",
                              f"{full_label} {name} ffprobe {probed} != RIFF {riff}")
        arm = {"label": full_label, "stage": label, "file": name, "path": str(path),
               "stage_meaning": meaning, "sha256": actual, "manifest_sha256": hashes[name],
               "hash_verified": True,
               "native_extent": {"riff": dict(riff, format_tag=header["format_tag"],
                                              bits_per_sample=header["bits_per_sample"]),
                                 "ffprobe": probed,
                                 "ffprobe_status": "cross_checked" if probed else "ffprobe_unavailable",
                                 "manifest_pcm": pcm, "verified": True},
               "flags": []}
        if label == "delivery_master":
            arm["delivery_normalization_mode"] = ((manifest.get("loudness") or {}).get("cleaned") or {}).get("mode")
        arms.append(arm)
    by_stage = {a["stage"]: a for a in arms}
    if "tone_dynamics_pre_gain" in by_stage and "pure_denoise" in by_stage and (
            by_stage["tone_dynamics_pre_gain"]["sha256"] == by_stage["pure_denoise"]["sha256"]):
        by_stage["tone_dynamics_pre_gain"]["flags"].append("identical_to_pure_denoise")
    return arms, absent


# ---------------------------------------------------------------------------
# Descriptor draft (root-owned insertion requested; not registered by this lane)
# ---------------------------------------------------------------------------

DESCRIPTOR_DRAFT = {
    "name": "tone_ab",
    "title": "Stage-attributed level-matched tone A/B",
    "description": ("Read an existing run's source, pure-denoise, tone/dynamics and delivery stage files "
                    "(sha256- and native-extent-verified), static-gain match them over an explicit common "
                    "region (>=5 s, >=45 s long), report six mixture-band energies and 20 ms attack "
                    "energy/centroid at hash-bound analysis positions, render one reversible preregistered "
                    "low-shelf trial and three blind 15 s excerpt pairs into a fresh artifacts/s2/tone_ab "
                    "directory. Never writes a run directory or adopts a master."),
    "intent": ("Attribute low-end and thin/nasal balance changes to pipeline stages at matched "
               "presentation level, and hand the operator blind excerpt pairs, without claiming "
               "perception, room response, fan/music separation or note identity."),
    "inputSchema": {
        "type": "object",
        "properties": {
            "run_dir": {"type": "string", "minLength": 1, "maxLength": 4096,
                        "description": "Existing run directory with manifest.json and hash-recorded "
                                       "source/denoised/cleaned (processed optional) WAV stage files; read-only."},
            "candidate_run_dir": {"type": "string", "minLength": 1, "maxLength": 4096,
                                  "description": "Optional second run of the same source sha256; its stage "
                                                 "files become candidate_* arms, flagged confounded when "
                                                 "its denoise basis differs."},
            "common_region_start": {"type": "number", "minimum": 5, "maximum": 86400,
                                    "description": "Native-source seconds; the 0-5 s setup interval is "
                                                   "never measured."},
            "common_region_end": {"type": "number", "minimum": 50, "maximum": 86400,
                                  "description": "Exclusive end in native-source seconds; must be <= run "
                                                 "duration and >= start + 45."},
            "timeout_seconds": {"type": "integer", "minimum": TIMEOUT_MIN, "maximum": TIMEOUT_MAX,
                                "default": TIMEOUT_DEFAULT,
                                "description": "Overall monotonic deadline; each FFmpeg child is "
                                               "bounded by min(120 s, remaining)."},
        },
        "required": list(REQUIRED_FIELDS),
        "additionalProperties": False,
    },
    "skill": SKILL,
    "implementation_status": "experimental",
    "evidence_kind": "level_matched_mixture_band_and_attack_measurements_with_unreviewed_trial",
    "limitations": [
        "Band and attack values are mixture energy; fan and music are not separated, and a 20-45 Hz level "
        "is not a measured played C1 fundamental.",
        "processed.wav combines EQ and compressor; the two cannot be attributed separately.",
        "Attack positions are unverified detector hypotheses with +/-5 ms hop quantization and "
        "uncalibrated detector delay.",
        "The low-shelf trial is a single preregistered, unreviewed arm (rejected_or_unreviewed_trial); it is "
        "never adopted or forwarded to a capture profile.",
        "Excerpts are for operator listening; preference, fullness and nasal quality stay null until the "
        "operator responds. True peak is not measured.",
    ],
    "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False,
                    "openWorldHint": False},
    "dependencies": {
        "recommended_prior_tools": ["denoise", "apply_capture_profile", "bpm"],
        "enforced": False,
        "note": ("Requires an existing run with manifest-recorded stage hashes; attack panels need an "
                 "analysis.json bound to the run's denoised sha256 (run dir or capture-profile parent run), "
                 "otherwise attack metrics are null with a reason."),
    },
    "agent_workflow": {
        "identify": ("Confirm the run, its stage hashes, native extent and the musical common region after "
                     "the 0-5 s setup interval; note whether processed.wav exists."),
        "research": ("Read docs/spec/sprints/TONE_S2.md and docs/spec/future/MASTERING_AND_CAPTURE_RESPONSE.md; "
                     "keep measurements, inferences and listening claims separate."),
        "iterate": ("Run once per fixed region; do not tune the shelf, bands or region after seeing results. "
                    "Compare candidates only against the same source sha256."),
        "acceptance": ("match_lu_delta <= 0.3 LU and verified extents are measurement checks only; listening "
                       "acceptance, preference and any EQ floor change remain root/operator decisions."),
        "max_comparison_candidates_default": 1,
    },
}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safe_run_id(manifest: dict, run_dir: Path) -> str:
    value = manifest.get("run_id")
    if isinstance(value, str) and value and all(c.isalnum() or c in "-_T" for c in value) and len(value) <= 128:
        return value
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in run_dir.name)[:128] or "run"


def _write_json(path: Path, data: dict):
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def _script_sha256() -> str:
    return media.sha256(Path(__file__).resolve())


def _band_lookup(bands: dict, label: str, band: str, key: str):
    for record in (bands.get(label) or {}).get("bands", []):
        if record["band"] == band:
            return record.get(key)
    return None


def _delta(a, b):
    return (a - b) if (a is not None and b is not None) else None


def run(arguments: dict, output_dir: str | Path | None = None, *, _trial_gain_db: float | None = None) -> dict:
    """Validate, gate identities, measure, render and publish. Returns the tone-ab.json record."""
    started_wall = datetime.now(timezone.utc).isoformat()
    script_sha256 = _script_sha256()  # bind the code that actually runs
    params = validate_arguments(arguments)
    deadline = time.monotonic() + params["timeout_seconds"]
    runner = Runner(deadline)

    run_dir = exact_directory(params["run_dir"], "run_dir")
    if not (run_dir / "manifest.json").is_file():
        raise ToneABError("manifest_missing", f"run_dir has no manifest.json: {run_dir}")
    manifest = load_json_file(run_dir / "manifest.json", "manifest_missing")
    pcm = _pcm_from_manifest(manifest, "run")
    region = region_samples(params["common_region_start"], params["common_region_end"], pcm)

    candidate_dir = None
    candidate_manifest = None
    if params["candidate_run_dir"] is not None:
        candidate_dir = exact_directory(params["candidate_run_dir"], "candidate_run_dir")
        if candidate_dir == run_dir:
            raise ToneABError("invalid_arguments", "candidate_run_dir must differ from run_dir")
        if not (candidate_dir / "manifest.json").is_file():
            raise ToneABError("manifest_missing", f"candidate_run_dir has no manifest.json: {candidate_dir}")
        candidate_manifest = load_json_file(candidate_dir / "manifest.json", "manifest_missing")
        run_source = (manifest.get("source") or {}).get("sha256")
        if not run_source or (candidate_manifest.get("source") or {}).get("sha256") != run_source:
            raise ToneABError("candidate_source_mismatch",
                              "candidate manifest.source.sha256 differs from the run's source")
        if _pcm_from_manifest(candidate_manifest, "candidate") != pcm:
            raise ToneABError("native_extent_mismatch", "candidate manifest.pcm differs from the run's pcm")

    run_id = _safe_run_id(manifest, run_dir)
    protected = [run_dir] + ([candidate_dir] if candidate_dir else [])
    if output_dir is None:
        output = (ROOT / "artifacts" / "s2" / "tone_ab" / f"{run_id}-{_utc_stamp()}").resolve()
    else:
        output = Path(output_dir).expanduser().resolve()
    if output.exists() or output.is_symlink():
        raise ToneABError("output_dir_exists", f"output directory must be fresh: {output}")
    if is_protected_location(output, protected):
        raise ToneABError("output_dir_protected",
                          f"output may not resolve inside a run directory or artifacts/runs: {output}")

    # Protected readback snapshot doubles as the streamed stage hash source.
    before = {"run_dir": snapshot(run_dir)}
    if candidate_dir:
        before["candidate_run_dir"] = snapshot(candidate_dir)
    runner.check()
    arms, absent = collect_arms(run_dir, manifest, before["run_dir"], pcm, runner)
    if candidate_dir:
        candidate_stages = tuple(s for s in STAGES if s[0] in CANDIDATE_STAGES)
        c_arms, c_absent = collect_arms(candidate_dir, candidate_manifest, before["candidate_run_dir"],
                                        pcm, runner, prefix="candidate_", stages=candidate_stages)
        run_denoised = next(a["sha256"] for a in arms if a["stage"] == "pure_denoise")
        for arm in c_arms:
            arm["candidate_run_dir"] = str(candidate_dir)
            c_denoised = next((a["sha256"] for a in c_arms if a["stage"] == "pure_denoise"), None)
            if c_denoised != run_denoised:
                arm["flags"].append("denoise_basis_differs_confounded")
        arms += c_arms
        absent += c_absent

    denoised_sha = next(a["sha256"] for a in arms if a["label"] == "pure_denoise")
    analysis = find_attack_analysis(run_dir, manifest, denoised_sha, pcm)
    analysis_before = analysis["sha256"]

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f".{output.name}.partial-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        record = _measure_and_render(params, runner, run_dir, manifest, pcm, region, arms, absent,
                                     analysis, staging, run_id, _trial_gain_db)
        after = {"run_dir": snapshot(run_dir)}
        if candidate_dir:
            after["candidate_run_dir"] = snapshot(candidate_dir)
        changed = {key: compare_snapshots(before[key], after[key]) for key in before}
        analysis_after = media.sha256(Path(analysis["path"])) if analysis["path"] else None
        readback = {
            "status": "unchanged" if not any(changed.values()) and analysis_after == analysis_before
            else "protected_input_changed",
            "directories": {key: {"path": str(run_dir if key == "run_dir" else candidate_dir),
                                  "files_checked": len(before[key]), "changed": changed[key],
                                  "fields": ["sha256", "size", "mtime_ns"]} for key in before},
            "analysis_file": {"path": analysis["path"], "sha256_before": analysis_before,
                              "sha256_after": analysis_after},
            "run_dir_files_before": before["run_dir"],
        }
        record["script_sha256"] = script_sha256
        for arm in record["arms"]:
            if arm["label"] == TRIAL_LABEL:
                arm["path"] = str(output / arm["file"])
        record["protected_readback"] = readback
        record["master_changed"] = readback["status"] != "unchanged"
        if readback["status"] != "unchanged":
            raise ToneABError("protected_input_changed", f"protected inputs changed: {changed}")
        record["metrics"]["7_run_dir_unchanged"] = {
            "numerator": len(before["run_dir"]) - len(changed["run_dir"]),
            "denominator": len(before["run_dir"]), "class": "M"}
        record["commands"] = runner.commands
        record["timing"] = {"started_utc": started_wall,
                            "finished_utc": datetime.now(timezone.utc).isoformat(),
                            "timeout_seconds": params["timeout_seconds"],
                            "remaining_seconds_at_finish": round(deadline - time.monotonic(), 3)}
        record["output_dir"] = str(output)
        record["status"] = "completed"
        _write_json(staging / "tone-ab.json", record)
        if output.exists():
            raise ToneABError("output_dir_exists", f"output appeared during the run: {output}")
        os.rename(staging, output)
        return record
    except BaseException as error:  # keep only the failure record, never a partial publication
        code = error.code if isinstance(error, ToneABError) else type(error).__name__
        for child in staging.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        _write_json(staging / "tone-ab.failed.json", {
            "schema_version": SCHEMA_VERSION, "tool": TOOL, "status": "failed", "code": code,
            "reason": str(error)[:4000], "run_dir": str(run_dir), "intended_output_dir": str(output),
            "commands": runner.commands, "spec": SPEC, "spec_commit": SPEC_COMMIT, "ruling": RULING,
            "master_changed": code == "protected_input_changed", "default_adopted": False})
        failed = output.parent / f"{output.name}.failed"
        if failed.exists():
            failed = output.parent / f"{output.name}.failed-{uuid.uuid4().hex[:8]}"
        os.rename(staging, failed)
        raise


def _measure_and_render(params, runner, run_dir, manifest, pcm, region, arms, absent, analysis,
                        staging, run_id, trial_gain_override) -> dict:
    rate, channels = pcm["sample_rate"], pcm["channels"]
    by_label = {a["label"]: a for a in arms}

    # Trial arm: exactly one, rendered from the accepted master into staging.
    trial_path = staging / "trial-lowshelf.wav"
    trial_gain = TRIAL_CONTROLS["gain_db"] if trial_gain_override is None else trial_gain_override
    trial = render_trial(runner, Path(by_label["delivery_master"]["path"]), trial_path, pcm, trial_gain)
    trial_arm = {"label": TRIAL_LABEL, "stage": TRIAL_LABEL, "file": trial_path.name,
                 "path": str(trial_path), "stage_meaning": "Reversible preregistered low-shelf trial derived "
                 "from delivery_master; separate deletable file", "sha256": media.sha256(trial_path),
                 "derived_from": {"label": "delivery_master", "sha256": by_label["delivery_master"]["sha256"]},
                 "filter": trial["filter"], "hash_verified": True,
                 "native_extent": {"riff": {"sample_rate": trial["header"]["sample_rate"],
                                            "channels": trial["header"]["channels"],
                                            "frames": trial["header"]["frames"],
                                            "format_tag": trial["header"]["format_tag"],
                                            "bits_per_sample": trial["header"]["bits_per_sample"]},
                                   "manifest_pcm": pcm, "verified": True},
                 "flags": ["experiment_arm"]}
    measured = arms + [trial_arm]
    labels = [a["label"] for a in measured]
    paths = {a["label"]: Path(a["path"]) for a in measured}

    # 1. Loudness match.
    match = match_gains(labels, lambda label, gain: measure_lufs(runner, paths[label], region, gain))
    gains = {label: match["per_arm"][label]["gain_db"] for label in labels}
    match_flag = match["match_status"] != "matched"

    # 2. Band energies and 4. attack panels per arm (one decode per arm, one child at a time).
    panels = attack_panels(analysis["data"]) if analysis["data"] else None
    panel_positions = {}
    if panels:
        for name, panel in panels.items():
            seconds = panel["seconds"]
            valid = [s for s in seconds if s is not None]
            in_region = [s for s in valid if region["start_seconds"] <= s < region["end_seconds"]]
            panel_positions[name] = {"seconds": in_region, "samples": [round(s * rate) for s in in_region],
                                     "events_in_analysis": len(seconds), "invalid_timestamps": len(seconds) - len(valid),
                                     "in_region": len(in_region)}
    bands, attack_rows = {}, {name: {} for name in panel_positions}
    for label in labels:
        samples = decode_region(runner, paths[label], region, channels)
        result = band_energies(samples, channels, rate, runner.check)
        gain = gains[label]
        for band in result["bands"]:
            raw = band["level_dbfs_raw"]
            band["level_dbfs_matched"] = (raw + gain) if (raw is not None and gain is not None) else None
            if match_flag:
                band["flags"] = ["loudness_unmatched"]
        bands[label] = result
        for name, positions in panel_positions.items():
            attack_rows[name][label] = attack_metrics(samples, channels, rate, region,
                                                      positions["samples"], runner.check)
        del samples

    # 3. Stage deltas.
    stage_deltas = {}
    for name, a, b in STAGE_DELTAS:
        if a not in bands or b not in bands:
            missing = [x for x in (a, b) if x not in bands]
            stage_deltas[name] = {"minuend": a, "subtrahend": b, "status": "absent",
                                  "reason": f"arm absent: {missing}", "bands": None}
            continue
        stage_deltas[name] = {"minuend": a, "subtrahend": b, "status": "measured",
                              "kind": "mixture_energy_change",
                              "bands": {band: {"raw_db": _delta(_band_lookup(bands, a, band, "level_dbfs_raw"),
                                                                _band_lookup(bands, b, band, "level_dbfs_raw")),
                                               "matched_db": _delta(_band_lookup(bands, a, band, "level_dbfs_matched"),
                                                                    _band_lookup(bands, b, band, "level_dbfs_matched")),
                                               "share_db": _delta(_band_lookup(bands, a, band, "share_db"),
                                                                  _band_lookup(bands, b, band, "share_db"))}
                                        for band in (f"{lo}-{hi}" for lo, hi in BANDS)},
                              "fan_only_gain": None, "music_only_gain": None}
    for label, arm in by_label.items():
        if label.startswith("candidate_"):
            stage = arm["stage"]
            stage_deltas[f"{label}_minus_{stage}"] = {
                "minuend": label, "subtrahend": stage, "status": "measured" if stage in bands else "absent",
                "kind": "mixture_energy_change", "confounded": "denoise_basis_differs_confounded" in arm["flags"],
                "bands": {band: {"raw_db": _delta(_band_lookup(bands, label, band, "level_dbfs_raw"),
                                                  _band_lookup(bands, stage, band, "level_dbfs_raw")),
                                 "matched_db": _delta(_band_lookup(bands, label, band, "level_dbfs_matched"),
                                                      _band_lookup(bands, stage, band, "level_dbfs_matched"))}
                          for band in (f"{lo}-{hi}" for lo, hi in BANDS)} if stage in bands else None}

    # Attack summary and per-position file.
    references = {label: [r for r in ("source", "pure_denoise") if r != label] for label in labels}
    references[TRIAL_LABEL] = ["source", "pure_denoise", "delivery_master"]
    attacks = {"status": analysis["status"],
               "analysis": {"path": analysis["path"], "sha256": analysis["sha256"],
                            "basis": analysis.get("basis"), "analyzed_input_sha256": analysis.get("analyzed_input_sha256"),
                            "tried": analysis["tried"]},
               "window": {"seconds": ATTACK_WINDOW_SECONDS, "samples": round(ATTACK_WINDOW_SECONDS * rate),
                          "start": "n0 = round(t * native_rate); window [n0, n0 + round(0.020 * rate))",
                          "centroid": f"periodic Hann over the window, zero-padded to next power of two, "
                                      f"magnitude-weighted over bins {CENTROID_LOW_HZ:g} Hz..min({CENTROID_HIGH_HZ:g} Hz, Nyquist)",
                          "energy": "10*log10(mean square), dB re 1.0; matched = raw + arm gain_db"},
               "attack_identity": "unverified", "panels": {}}
    if analysis["data"]:
        meta = analysis["data"].get("analysis") or {}
        attacks["timestamp_uncertainty"] = {
            "analysis_hop_seconds": meta.get("hop_seconds"), "frame_timestamp": meta.get("frame_timestamp"),
            "onset_detector_delay_seconds": meta.get("onset_detector_delay_seconds"),
            "onset_detector_delay_status": meta.get("onset_detector_delay_status", "uncalibrated"),
            "note": "+/-5 ms analysis hop quantization and uncalibrated detector delay; a 20 ms window may "
                    "start before or after the physical transient"}
        positions_file = {}
        for name, positions in panel_positions.items():
            rows = attack_rows[name]
            used = sum(1 for row in rows[labels[0]] if row is not None) if labels else 0
            attacks["panels"][name] = {
                "source": panels[name]["source"], "identity": panels[name]["identity"],
                "denominators": {"events_in_analysis": positions["events_in_analysis"],
                                 "invalid_timestamps": positions["invalid_timestamps"],
                                 "in_region": positions["in_region"], "used": used},
                "per_arm": summarize_attacks(rows, gains, references)}
            positions_file[name] = {"seconds": positions["seconds"], "samples": positions["samples"],
                                    "arms": {label: rows[label] for label in labels}}
        _write_json(staging / "attack-positions.json", {"schema_version": SCHEMA_VERSION,
                                                        "region": region, "panels": positions_file})
        attacks["positions_file"] = {"file": "attack-positions.json",
                                     "sha256": media.sha256(staging / "attack-positions.json")}
    else:
        attacks["reason"] = "no_hash_bound_attack_analysis"
        attacks["panels"] = {"primary": None, "secondary": None}

    # 5. Excerpt pairs (source vs delivery_master, shared static gains, blind labels).
    excerpts = _render_excerpts(runner, staging, region, pcm, paths, gains)

    # 6. Experiment record.
    trial_bands = stage_deltas["trial"]["bands"]
    delta_20_45 = {"raw": trial_bands["20-45"]["raw_db"], "matched": trial_bands["20-45"]["matched_db"]}
    experiment = {
        "arm": TRIAL_LABEL, "count": 1, "status": TRIAL_STATUS, "adopted": False,
        "forwarded_to_profile": False, "controls": dict(TRIAL_CONTROLS, gain_db=trial_gain),
        "filter": trial["filter"], "applied_to": {"label": "delivery_master",
                                                  "sha256": by_label["delivery_master"]["sha256"]},
        "file": trial_path.name, "sha256": trial_arm["sha256"], "extent_verified": True,
        "reversibility": "accepted master untouched; trial is a separate deletable f32 file; root decides retention",
        "delta_20_45_db": delta_20_45, "band_deltas_vs_delivery_master": trial_bands,
        "attack_deltas_vs_delivery_master": {
            name: (panel["per_arm"].get(TRIAL_LABEL, {}).get("paired_median_deltas", {}).get("vs_delivery_master")
                   if panel else None) for name, panel in attacks["panels"].items()},
        "expectation_inference": ("Filter theory (inference, not measurement): about +1.3 to +1.5 dB raw at "
                                  "20-45 Hz, smaller after the loudness match."),
        "preregistration": {"spec": SPEC, "commit": SPEC_COMMIT,
                            "fixed_before_truth": ["shelf parameters", "bands", "Welch/attack parameters",
                                                   "region", "excerpt rule", "blind seed", "0.3 LU tolerance"]},
    }
    if trial_gain_override is not None:
        experiment["preregistered_gain_overridden_for_test"] = True
    eq_floor = {"current_schema_min_hz": CURRENT_SCHEMA_MIN_HZ, "trial_shelf_hz": TRIAL_CONTROLS["frequency_hz"],
                "measured_delta_20_45_db": delta_20_45, "decision": "root_and_operator_review_required",
                "adopted": False,
                "note": "A measured increase is not evidence of fuller perceived tone, a recovered fundamental "
                        "or room response."}

    # Claims, metrics and the explicit unknowns.
    bands_cells = sum(1 for label in labels for b in bands[label]["bands"]
                      if b["level_dbfs_raw"] is not None and b["level_dbfs_matched"] is not None)
    stage_count = sum(1 for a in arms if not a["label"].startswith("candidate_"))
    metrics = {
        "1_stage_files_verified": {"numerator": len(arms), "denominator": len(arms) + len(absent),
                                   "trial_extent_equal": "1/1", "class": "M"},
        "2_loudness_match": {"match_lu_delta": match["match_lu_delta"], "match_status": match["match_status"],
                             "arms_measured": len(labels), "class": "M"},
        "3_band_cells": {"numerator": bands_cells, "denominator": len(BANDS) * len(labels), "class": "M"},
        "4_attack_positions": {name: (p["denominators"] if p else None) for name, p in attacks["panels"].items()},
        "5_excerpt_pairs": {"numerator": sum(1 for p in excerpts["pairs"] if p["extent_verified"]),
                            "denominator": EXCERPT_COUNT, "files": 2 * len(excerpts["pairs"]),
                            "class": "M", "preference": "L pending"},
        "6_experiment_arm": {"numerator": 1, "denominator": 1, "status": TRIAL_STATUS, "class": "M + I"},
        "8_unknown_fields": {"numerator": len(UNKNOWN_FIELDS), "denominator": 15, "class": "contract"},
        "stage_arms_present": {"numerator": stage_count, "denominator": len(STAGES)},
    }
    claims = {
        "measurements": [
            f"Integrated LUFS (FFmpeg loudnorm input_i, BS.1770 gating) over native samples "
            f"[{region['start_sample']}, {region['end_sample_exclusive']}) for {len(labels)} arms; "
            f"match_lu_delta={_fmt(match['match_lu_delta'])} LU ({match['match_status']}).",
            f"Welch band energies for {bands_cells}/{len(BANDS) * len(labels)} arm-band cells, raw and gain-matched.",
            f"Trial minus delivery_master 20-45 Hz: raw {_fmt(delta_20_45['raw'])} dB, "
            f"matched {_fmt(delta_20_45['matched'])} dB.",
            f"{len(excerpts['pairs'])} excerpt pairs rendered at exactly {excerpts['frames_per_file']} frames each.",
        ],
        "inferences": [
            "Stage deltas are mixture-energy changes attributed to the stage between two files; they do not "
            "separate fan from music.",
            "tone_dynamics_pre_gain - pure_denoise combines EQ and compressor effects.",
            experiment["expectation_inference"],
        ],
        "listening": [],
    }
    record = {
        "schema_version": SCHEMA_VERSION, "tool": TOOL, "status": "in_progress",
        "spec": SPEC, "spec_commit": SPEC_COMMIT, "ruling": RULING, "skill": SKILL,
        "script_sha256": None,
        "inputs": {"run_dir": str(run_dir), "candidate_run_dir": params["candidate_run_dir"],
                   "common_region_start": params["common_region_start"],
                   "common_region_end": params["common_region_end"],
                   "timeout_seconds": params["timeout_seconds"]},
        "run": {"run_id": run_id, "status": manifest.get("status"),
                "manifest_sha256": media.sha256(run_dir / "manifest.json"),
                "source_sha256": (manifest.get("source") or {}).get("sha256"), "pcm": pcm},
        "region": region,
        "arms": measured, "absent_arms": absent,
        "loudness_match": dict(match, meter="FFmpeg loudnorm print_format=json input_i (BS.1770 gating), "
                                            "same meter as media.loudness",
                               tolerance_lu=MATCH_TOLERANCE_LU, max_corrections=MAX_MATCH_CORRECTIONS,
                               gain_filter="volume=<g>dB:precision=double",
                               policy="target = minimum region LUFS; one static gain per arm; no per-phrase "
                                      "normalization; all gains <= 0 dB"),
        "bands": bands, "stage_deltas": stage_deltas, "attacks": attacks, "excerpts": excerpts,
        "experiment": experiment, "eq_floor_change_proposed": eq_floor,
        "claims": claims, "metrics": metrics,
        "unknown_field_reasons": {name: reason for name, (_, reason) in UNKNOWN_FIELDS.items()},
        "limitations": DESCRIPTOR_DRAFT["limitations"],
    }
    for name, (value, _) in UNKNOWN_FIELDS.items():
        record[name] = value
    return record


def _fmt(value) -> str:
    return "null" if value is None else f"{value:.3f}"


def excerpt_windows(region: dict, rate: int) -> list[dict]:
    start, end = region["start_seconds"], region["end_seconds"]
    frames = round(EXCERPT_SECONDS * rate)
    windows = []
    for index in range(EXCERPT_COUNT):
        center = start + (end - start) * (2 * index + 1) / (2 * EXCERPT_COUNT)
        begin = round((center - EXCERPT_SECONDS / 2) * rate)
        if begin < region["start_sample"] or begin + frames > region["end_sample_exclusive"]:
            raise ToneABError("region_out_of_bounds", f"excerpt {index + 1} does not fit the region")
        swap = random.Random(BLIND_SEED + index).random() < 0.5
        windows.append({"pair": index + 1, "center_seconds": center,
                        "start_seconds": center - EXCERPT_SECONDS / 2, "start_sample": begin,
                        "end_sample_exclusive": begin + frames, "frames": frames,
                        "key": {"X": "delivery_master" if swap else "source",
                                "Y": "source" if swap else "delivery_master"}})
    return windows


def _render_excerpts(runner, staging, region, pcm, paths, gains) -> dict:
    rate = pcm["sample_rate"]
    pairs, key = [], []
    for window in excerpt_windows(region, rate):
        files = {}
        verified = True
        for blind, label in window["key"].items():
            name = f"excerpt-{window['pair']}-{blind}.wav"
            out = staging / name
            gain = gains.get(label)
            chain = [region_filter(window["start_sample"], window["end_sample_exclusive"]),
                     "asetpts=N/SR/TB"]
            if gain is not None:
                chain.append(gain_filter(gain))
            runner.ffmpeg(["-i", str(paths[label]), "-map", "0:a:0", "-af", ",".join(chain),
                           "-c:a", "pcm_f32le", "-f", "wav", str(out)])
            samples, header = read_wav_samples(out)
            ok = (header["sample_rate"], header["channels"], header["frames"]) == (
                rate, pcm["channels"], window["frames"])
            verified = verified and ok
            if not ok:
                raise ToneABError("excerpt_extent_mismatch", f"{name} has {header['frames']} frames")
            peak = max((abs(v) for v in samples), default=0.0)
            lufs = measure_lufs(runner, out, {"start_sample": 0, "end_sample_exclusive": window["frames"]})
            files[blind] = {"file": name, "sha256": media.sha256(out), "frames": header["frames"],
                            "sample_rate": header["sample_rate"], "channels": header["channels"],
                            "static_gain_db": gain, "level_matched": gain is not None,
                            "sample_peak_dbfs": (20 * math.log10(peak)) if peak > 0 else None,
                            "excerpt_lufs_informational": lufs, "true_peak_dbtp": None}
        pairs.append({"pair": window["pair"], "start_seconds": window["start_seconds"],
                      "center_seconds": window["center_seconds"], "start_sample": window["start_sample"],
                      "end_sample_exclusive": window["end_sample_exclusive"], "files": files,
                      "extent_verified": verified})
        key.append({"pair": window["pair"], **window["key"]})
    return {"rule": "center_i = S + (E - S) * (2i + 1) / 6, window [center - 7.5, center + 7.5] s",
            "comparison": "source vs delivery_master, region static gains applied",
            "seed": f"random.Random({BLIND_SEED} + i).random() < 0.5 -> X = delivery_master",
            "frames_per_file": round(EXCERPT_SECONDS * rate), "format": "native rate/channels f32 WAV",
            "pairs": pairs,
            "blind_key_notice": "Listen to the X/Y files before reading blind_key.",
            "blind_key": key, "operator_preference": None}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def summary(record: dict) -> dict:
    output = Path(record["output_dir"])
    return {"status": record["status"], "tool": TOOL, "output_dir": str(output),
            "tone_ab_json": str(output / "tone-ab.json"),
            "tone_ab_sha256": media.sha256(output / "tone-ab.json"),
            "match_status": record["loudness_match"]["match_status"],
            "match_lu_delta": record["loudness_match"]["match_lu_delta"],
            "trial_status": record["experiment"]["status"],
            "delta_20_45_db": record["experiment"]["delta_20_45_db"],
            "attack_status": record["attacks"]["status"],
            "excerpt_pairs": len(record["excerpts"]["pairs"]),
            "protected_readback": record["protected_readback"]["status"],
            "operator_preference": None, "room_response_recovered": False, "default_adopted": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="measure and render a tone A/B for one run")
    run_parser.add_argument("--run-dir", required=True)
    run_parser.add_argument("--candidate-run-dir")
    run_parser.add_argument("--common-region-start", required=True, type=float)
    run_parser.add_argument("--common-region-end", required=True, type=float)
    run_parser.add_argument("--timeout-seconds", type=int, default=TIMEOUT_DEFAULT)
    run_parser.add_argument("--output-dir", help="fresh output directory (default artifacts/s2/tone_ab/<run_id>-<UTC>)")
    commands.add_parser("describe", help="print the typed tool descriptor draft")
    args = parser.parse_args(argv)
    if args.command == "describe":
        print(json.dumps(DESCRIPTOR_DRAFT, indent=2, allow_nan=False))
        return 0
    arguments = {"run_dir": args.run_dir, "common_region_start": args.common_region_start,
                 "common_region_end": args.common_region_end, "timeout_seconds": args.timeout_seconds}
    if args.candidate_run_dir:
        arguments["candidate_run_dir"] = args.candidate_run_dir
    try:
        record = run(arguments, args.output_dir)
    except ToneABError as error:
        print(json.dumps({"status": "refused_or_failed", "code": error.code, "error": error.message[:4000]},
                         allow_nan=False), file=sys.stderr)
        return 2
    print(json.dumps(summary(record), indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
