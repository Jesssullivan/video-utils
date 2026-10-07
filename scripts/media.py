#!/usr/bin/env python3
"""Offline FFmpeg media worker. Original media is never modified.

Stdlib only. FFMPEG and FFPROBE may select executables; otherwise use PATH.
All media outputs are private local artifacts, not publication approvals.
"""
from __future__ import annotations

import argparse
import array
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid
import wave

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 600
THREADS = "2"
COMMANDS: list[list[str]] = []


# Operator decision 2026-10-06 (TIN-5599): FULLER is the default and always needs a
# reviewed per-take capture interval; conservative3 stays selectable explicitly.
DEFAULT_PROFILE = "fuller"


class MediaError(RuntimeError):
    def __init__(self, message="", code="media_error"):
        super().__init__(message)
        self.code = code


def executable(name: str) -> str:
    selected = os.environ.get(name.upper(), name)
    found = shutil.which(selected)
    if not found:
        raise MediaError(f"{name} not available; set {name.upper()} or add it to PATH")
    return found


def run(command: list[str], timeout: int = TIMEOUT) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, timeout=timeout,
                                check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaError(f"{Path(command[0]).name} could not finish: {exc}") from exc
    if result.returncode:
        # Log tails omit the initial input/path listings and bound console output.
        tail = result.stderr[-2500:]
        raise MediaError(f"{Path(command[0]).name} failed ({result.returncode}): {tail}")
    return result


def ffmpeg(arguments: list[str]) -> subprocess.CompletedProcess:
    command = [executable("ffmpeg"), "-hide_banner", "-nostdin", "-loglevel", "info",
                "-threads", THREADS, "-filter_threads", THREADS,
                "-filter_complex_threads", THREADS, "-n", *arguments]
    COMMANDS.append(command)
    return run(command)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def source_path(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise MediaError(f"input is not a regular file: {path}")
    return path


def probe(path: Path) -> dict:
    result = run([executable("ffprobe"), "-v", "error", "-show_format", "-show_streams",
                  "-of", "json", str(path)], timeout=60)
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaError("ffprobe returned invalid JSON") from exc
    streams = raw.get("streams", [])
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    video = next((s for s in streams if s.get("codec_type") == "video"
                  and not s.get("disposition", {}).get("attached_pic")), None)
    if audio is None:
        raise MediaError("input has no audio stream")
    rate = int(audio.get("sample_rate", 0))
    channels = int(audio.get("channels", 0))
    if rate <= 0 or channels <= 0:
        raise MediaError("audio sample rate or channel count is unavailable")
    audio = dict(audio, sample_rate=rate, channels=channels,
                 start_time=number(audio.get("start_time")), duration=number(audio.get("duration")))
    fmt = dict(raw.get("format", {}))
    fmt["start_time"] = number(fmt.get("start_time"))
    fmt["duration"] = number(fmt.get("duration"))
    return {"format": fmt, "audio": audio, "video": video, "streams": streams}


def audio_timeline_origin(path: Path, metadata: dict) -> dict:
    """Retain stated origin, or measure first decoded PTS when metadata omits it."""
    stated = number(metadata["audio"].get("start_time"))
    if stated is not None:
        return {"seconds": stated, "basis": "audio_stream_start_metadata"}
    command = [executable("ffprobe"), "-v", "error", "-select_streams",
               str(metadata["audio"]["index"]), "-read_intervals", "%+#1",
               "-show_frames", "-show_entries", "frame=pts_time,best_effort_timestamp_time",
               "-of", "json", str(path)]
    COMMANDS.append(command)
    result = run(command, timeout=60)
    if len(result.stdout.encode("utf-8")) > 65536:
        raise MediaError("first-frame timestamp receipt is oversized")
    try:
        frames = json.loads(result.stdout).get("frames", [])
    except (ValueError, AttributeError) as exc:
        raise MediaError("first-frame timestamp probe returned invalid JSON") from exc
    if not isinstance(frames, list) or len(frames) > 64:
        raise MediaError("first-frame timestamp receipt is invalid")
    frame = frames[0] if frames and isinstance(frames[0], dict) else {}
    timestamp = number(frame.get("pts_time"))
    if timestamp is None:
        timestamp = number(frame.get("best_effort_timestamp_time"))
    return {"seconds": timestamp,
            "basis": "first_decoded_frame_timestamp" if timestamp is not None else "unknown",
            "source_stream_start_metadata": None, "first_frame": frame,
            "command": command,
            "scope": "decoded audio axis; not BWF time reference, acoustic latency or physical A/V sync"}


def load_profile(value: str | Path) -> dict:
    path = Path(value).expanduser()
    if not path.is_file():
        path = ROOT / "profiles" / f"{value}.json"
    try:
        profile = json.loads(path.read_text(), object_pairs_hook=_profile_object)
    except (OSError, json.JSONDecodeError) as exc:
        raise MediaError(f"cannot read profile: {value}") from exc
    return validate_profile(profile)


def _profile_object(pairs: list) -> dict:
    """Plain dict (last key wins, as json.loads) except a repeated low_shelf is refused.

    Only low_shelf is checked so that one profile file can never smuggle a second
    shelf past the at-most-one rule; general duplicate-key hardening is separate."""
    if sum(1 for key, _ in pairs if key == "low_shelf") > 1:
        raise MediaError("profile may contain at most one low_shelf", "low_shelf_multiple")
    return dict(pairs)


def validate_profile(profile: dict) -> dict:
    if not isinstance(profile, dict) or profile.get("schema_version") != 1:
        raise MediaError("profile requires schema_version: 1")
    allowed = {"schema_version", "name", "description", "denoise", "reduction_db",
               "noise_floor_db", "gain_smooth", "preserve_low_fundamental_hz",
               "integrated_lufs", "true_peak_dbtp", "noise_capture_seconds",
               "noise_capture_authorized", "noise_capture_source_sha256",
               "noise_capture_review", "adaptivity", "peaking_eq", "compressor",
               "noise_capture_required", "low_shelf", "operator_review_status",
               "listening_acceptance"}
    if set(profile) - allowed:
        raise MediaError("profile contains unsupported fields")
    if not isinstance(profile.get("denoise"), bool):
        raise MediaError("profile denoise must be a boolean")
    if "noise_capture_required" in profile and (not isinstance(profile["noise_capture_required"], bool)
                                                or (profile["noise_capture_required"] and not profile["denoise"])):
        raise MediaError("noise_capture_required must be a boolean and requires denoise")
    limits = {"integrated_lufs": (-70, -5), "true_peak_dbtp": (-9, 0),
              "reduction_db": (0.01, 12), "noise_floor_db": (-80, -20),
              "gain_smooth": (0, 50)}
    required = ["integrated_lufs", "true_peak_dbtp"]
    if profile["denoise"]:
        required += ["reduction_db", "noise_floor_db", "gain_smooth"]
    for key in set(required) | (set(profile) & set(limits)):
        val = profile.get(key)
        low, high = limits[key]
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or not low <= val <= high:
            raise MediaError(f"profile {key} must be between {low} and {high}")
    if "gain_smooth" in profile and (isinstance(profile["gain_smooth"], bool)
                                    or not isinstance(profile["gain_smooth"], int)):
        raise MediaError("profile gain_smooth must be an integer")
    for key in ("name", "description", "noise_capture_review"):
        if key in profile and (not isinstance(profile[key], str) or len(profile[key]) > 2000):
            raise MediaError(f"profile {key} must be bounded text")
    if "noise_capture_authorized" in profile and not isinstance(profile["noise_capture_authorized"], bool):
        raise MediaError("noise_capture_authorized must be a boolean")
    if "preserve_low_fundamental_hz" in profile:
        numeric_control(profile["preserve_low_fundamental_hz"], 28, 40, "preserve_low_fundamental_hz")
    if "adaptivity" in profile:
        numeric_control(profile["adaptivity"], 0, 1, "adaptivity")
    interval = profile.get("noise_capture_seconds")
    if interval is not None:
        if (not profile["denoise"] or profile.get("noise_capture_authorized") is not True
                or not isinstance(interval, list) or len(interval) != 2
                or any(isinstance(x, bool) or not isinstance(x, (int, float))
                       or not math.isfinite(x) for x in interval)
                or interval[0] < 0 or not 0.1 <= interval[1] - interval[0] <= 10):
            raise MediaError("noise capture needs an explicitly authorized [start, end] interval")
        capture_hash = profile.get("noise_capture_source_sha256")
        if (not isinstance(capture_hash, str) or len(capture_hash) != 64
                or any(char not in "0123456789abcdef" for char in capture_hash)):
            raise MediaError("noise capture requires original source SHA-256 binding")
    elif any(key in profile for key in ("noise_capture_source_sha256", "noise_capture_authorized", "noise_capture_review")):
        raise MediaError("noise capture metadata requires an interval")
    validate_post_controls(profile)
    return profile


def check_capture_request(profile: dict, interval, review) -> None:
    """Typed refusals for a per-take capture binding; runs before hashing or decode."""
    if profile.get("noise_capture_seconds") is not None:
        raise MediaError("profile already binds a noise capture interval; omit --capture-interval",
                         "capture_interval_conflict")
    if not isinstance(review, str) or not review.strip() or len(review) > 2000:
        raise MediaError("--capture-interval requires non-empty --capture-review text of at most 2000 characters",
                         "capture_review_required")
    if (not profile["denoise"] or not isinstance(interval, (list, tuple)) or len(interval) != 2
            or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
                   for x in interval)
            or interval[0] < 0 or not 0.1 <= interval[1] - interval[0] <= 10):
        raise MediaError("capture interval needs finite START >= 0, a 0.1-10 second duration and a denoise profile",
                         "capture_interval_invalid")


def bind_capture(profile: dict, interval, review, source_sha256: str) -> dict:
    """Bind a reviewed per-take interval to a template, then rerun profile validation."""
    check_capture_request(profile, interval, review)
    bound = {key: value for key, value in profile.items() if key != "noise_capture_required"}
    bound.update(noise_capture_seconds=[float(interval[0]), float(interval[1])],
                 noise_capture_authorized=True, noise_capture_review=review,
                 noise_capture_source_sha256=source_sha256)
    return validate_profile(bound)


def numeric_control(value, low: float, high: float, name: str) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not low <= value <= high):
        raise MediaError(f"{name} must be numeric between {low} and {high}")
    return float(value)


# Operator ruling 2026-10-07 (S2R, TIN-5487): a capped, reversible low-shelf is an
# explicit profile option below 160 Hz; FULLER stays the default; never a cut or
# notch near the ~32 Hz fundamental. Q <= 1/sqrt(2) keeps the RBJ shelf monotonic,
# so a boost never dips below unity at any frequency. Widening the status enums
# after operator listening is a root/operator decision, not a lane decision.
LOW_SHELF_KEYS = frozenset({"frequency_hz", "gain_db", "q"})
LOW_SHELF_FREQUENCY_HZ = (80.0, 160.0)
LOW_SHELF_GAIN_DB = (0.0, 2.0)
LOW_SHELF_Q = (0.5, 0.707)
OPERATOR_REVIEW_STATUSES = ("unreviewed_trial",)
LISTENING_ACCEPTANCE_STATUSES = ("not_performed",)


def _shelf_number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MediaError(f"low_shelf {name} must be a finite number", "low_shelf_invalid")
    try:
        result = float(value)
    except OverflowError as exc:
        raise MediaError(f"low_shelf {name} must be a finite number", "low_shelf_invalid") from exc
    if not math.isfinite(result):
        raise MediaError(f"low_shelf {name} must be a finite number", "low_shelf_invalid")
    return result


def validate_low_shelf(profile: dict) -> dict | None:
    """Typed refusals for the optional single boost-only low shelf; None when absent."""
    if "low_shelf" not in profile:
        return None
    shelf = profile["low_shelf"]
    if isinstance(shelf, list):
        raise MediaError("profile may contain at most one low_shelf object, never a list",
                         "low_shelf_multiple")
    if not isinstance(shelf, dict) or set(shelf) != LOW_SHELF_KEYS:
        raise MediaError("low_shelf requires exactly frequency_hz, gain_db and q", "low_shelf_invalid")
    frequency = _shelf_number(shelf["frequency_hz"], "frequency_hz")
    gain = _shelf_number(shelf["gain_db"], "gain_db")
    q = _shelf_number(shelf["q"], "q")
    low, high = LOW_SHELF_FREQUENCY_HZ
    if not low <= frequency <= high:
        raise MediaError(f"low_shelf frequency_hz must be between {low:g} and {high:g}",
                         "low_shelf_frequency_out_of_bounds")
    if gain < 0 or math.copysign(1.0, gain) < 0:
        raise MediaError("low_shelf is boost only; a negative gain_db (cut) is refused",
                         "low_shelf_cut_refused")
    if gain > LOW_SHELF_GAIN_DB[1]:
        raise MediaError(f"low_shelf gain_db must be at most +{LOW_SHELF_GAIN_DB[1]:g} dB",
                         "low_shelf_gain_out_of_bounds")
    low, high = LOW_SHELF_Q
    if not low <= q <= high:
        raise MediaError(f"low_shelf q must be between {low:g} and {high:g}", "low_shelf_q_out_of_bounds")
    return shelf


def validate_review_status(profile: dict) -> None:
    for key, allowed in (("operator_review_status", OPERATOR_REVIEW_STATUSES),
                         ("listening_acceptance", LISTENING_ACCEPTANCE_STATUSES)):
        if key in profile and (not isinstance(profile[key], str) or profile[key] not in allowed):
            raise MediaError(f"{key} must be one of {', '.join(allowed)}", "low_shelf_review_status_invalid")
    if "low_shelf" in profile and not all(key in profile for key in ("operator_review_status",
                                                                    "listening_acceptance")):
        raise MediaError("low_shelf requires operator_review_status and listening_acceptance",
                         "low_shelf_review_status_required")


def validate_post_controls(profile: dict):
    validate_low_shelf(profile)
    validate_review_status(profile)
    bands = profile.get("peaking_eq", [])
    if not isinstance(bands, list) or len(bands) > 3:
        raise MediaError("peaking_eq must contain at most three numeric bands")
    for band in bands:
        if not isinstance(band, dict) or set(band) != {"frequency_hz", "gain_db", "q"}:
            raise MediaError("EQ bands require exactly frequency_hz, gain_db and q")
        numeric_control(band["frequency_hz"], 160, 6000, "EQ frequency_hz")
        numeric_control(band["gain_db"], -3, 3, "EQ gain_db")
        numeric_control(band["q"], 0.5, 2, "EQ q")
    compressor = profile.get("compressor")
    if compressor is not None:
        limits = {"threshold_db": (-36, -6), "ratio": (1, 3),
                  "attack_ms": (8, 20), "release_ms": (60, 200), "knee_db": (0, 6)}
        if not isinstance(compressor, dict) or set(compressor) != set(limits):
            raise MediaError("compressor requires exactly threshold_db, ratio, attack_ms, release_ms and knee_db")
        for key, (low, high) in limits.items():
            numeric_control(compressor[key], low, high, f"compressor {key}")


def post_denoise_filters(profile: dict, sample_rate: int) -> list[dict]:
    """Build a closed set of serial stages; profile values cannot inject filters."""
    validate_post_controls(profile)
    stages = []
    shelf = profile.get("low_shelf")
    if shelf is not None:
        if shelf["frequency_hz"] >= sample_rate / 2:
            raise MediaError("low_shelf frequency must be below source Nyquist", "low_shelf_above_nyquist")
        stages.append({"stage": "low_shelf", "controls": dict(shelf),
                       "filter": (f"lowshelf=f={float(shelf['frequency_hz']):.9g}:t=q:"
                                  f"w={float(shelf['q']):.9g}:g={float(shelf['gain_db']):.9g}:r=f64"),
                       "timing": {"sample_axis_policy": "causal forward IIR; no block delay or time stretch",
                                  "frequency_dependent_phase": True,
                                  "acoustic_alignment_verified": False},
                       "boost_only": True,
                       "reversibility": ("procedural: re-render the unchanged source with profile fuller; "
                                         "the shelf is not inverted from a rendered master"),
                       "recreates_uncaptured_fundamental": False})
    for index, band in enumerate(profile.get("peaking_eq", [])):
        if band["frequency_hz"] >= sample_rate / 2:
            raise MediaError("EQ frequency must be below source Nyquist")
        stages.append({"stage": f"peaking_eq_{index + 1}", "controls": dict(band),
                       "filter": (f"equalizer=f={float(band['frequency_hz']):.9g}:t=q:"
                                  f"w={float(band['q']):.9g}:g={float(band['gain_db']):.9g}:b=0:r=f64"),
                       "timing": {"sample_axis_policy": "causal forward IIR; no block delay or time stretch",
                                  "frequency_dependent_phase": True,
                                  "acoustic_alignment_verified": False}})
    compressor = profile.get("compressor")
    if compressor is not None:
        threshold = 10 ** (compressor["threshold_db"] / 20)
        knee = 10 ** (compressor["knee_db"] / 20)
        stages.append({"stage": "rms_compressor", "controls": dict(compressor),
                       "fixed_parallel_wet_fraction": 0.25,
                       "maximum_stage_attenuation_db": -20 * math.log10(0.75),
                       "filter": (f"acompressor=threshold={threshold:.12g}:ratio={float(compressor['ratio']):.9g}:"
                                  f"attack={float(compressor['attack_ms']):.9g}:release={float(compressor['release_ms']):.9g}:"
                                  f"knee={knee:.12g}:makeup=1:level_in=1:mode=downward:link=maximum:detection=rms:mix=0.25"),
                       "timing": {"sample_axis_policy": "causal gain envelope; no lookahead or sample-axis trimming",
                                  "attack_release_change_amplitude": True,
                                  "acoustic_alignment_verified": False}})
    return stages


def render_post_denoise(input_path: Path, output_path: Path, profile: dict,
                        reference: dict) -> list[dict]:
    stages = post_denoise_filters(profile, reference["sample_rate"])
    if not stages:
        return []
    ffmpeg(["-i", str(input_path), "-af", ",".join(stage["filter"] for stage in stages),
            "-ar", str(reference["sample_rate"]), "-ac", str(reference["channels"]),
            "-c:a", "pcm_f32le", str(output_path)])
    ensure_pcm_matches(output_path, reference)
    return stages


def pcm_info(path: Path) -> dict:
    audio = probe(path)["audio"]
    # PCM WAV duration_ts/time_base yields integer decoded sample count.
    samples = None
    if audio.get("duration_ts") is not None and audio.get("time_base"):
        numerator, denominator = audio["time_base"].split("/")
        samples = round(int(audio["duration_ts"]) * int(numerator)
                        * audio["sample_rate"] / int(denominator))
    return {"sample_rate": audio["sample_rate"], "channels": audio["channels"],
            "sample_count": samples, "duration_seconds": audio["duration"],
            "codec": audio.get("codec_name")}


def json_write(path: Path, data: dict):
    with path.open("w") as handle:
        json.dump(data, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def loudnorm_json(result: subprocess.CompletedProcess) -> dict:
    begin, end = result.stderr.rfind("{"), result.stderr.rfind("}")
    try:
        return json.loads(result.stderr[begin:end + 1])
    except json.JSONDecodeError as exc:
        raise MediaError("FFmpeg loudness measurement returned no JSON") from exc


def loudness(path: Path, profile: dict) -> dict:
    audio_filter = (f"loudnorm=I={profile['integrated_lufs']}:TP={profile['true_peak_dbtp']}:"
                    "LRA=50:print_format=json")
    return loudnorm_json(ffmpeg(["-i", str(path), "-map", "0:a:0", "-af", audio_filter,
                                "-f", "null", "-"]))


def normalize(input_path: Path, output_path: Path, profile: dict, audio: dict) -> dict:
    measured = loudness(input_path, profile)
    values = [number(measured.get(key)) for key in
              ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")]
    if all(value is not None for value in values):
        i, tp, lra, thresh, offset = values
        audio_filter = (f"loudnorm=I={profile['integrated_lufs']}:TP={profile['true_peak_dbtp']}:"
                        f"LRA=50:measured_I={i}:measured_TP={tp}:measured_LRA={lra}:"
                        f"measured_thresh={thresh}:offset={offset}:linear=true:print_format=json")
        mode = "two_pass_linear_requested"
    else:
        # Silence/very short signals have undefined LUFS; don't fabricate a gain.
        audio_filter = "anull"
        mode = "bypass_undefined_loudness"
    rendered = ffmpeg(["-i", str(input_path), "-map", "0:a:0", "-af", audio_filter,
                       "-ar", str(audio["sample_rate"]), "-ac", str(audio["channels"]),
                       "-c:a", "pcm_s24le", str(output_path)])
    return {"input": measured, "output": loudness(output_path, profile), "mode": mode,
            "render": loudnorm_json(rendered) if mode != "bypass_undefined_loudness" else None,
            "target_integrated_lufs": profile["integrated_lufs"],
            "target_true_peak_dbtp": profile["true_peak_dbtp"]}


def ensure_pcm_matches(path: Path, reference: dict) -> dict:
    info = pcm_info(path)
    for key in ("sample_rate", "channels", "sample_count"):
        if info[key] != reference[key]:
            raise MediaError(f"{path.name} changed {key}: {reference[key]} -> {info[key]}")
    return info


def calibrate_denoise_latency(directory: Path, audio_filter: str, rate: int,
                              channels: int) -> dict:
    """Validate the actual afftdn binary's insertion delay, rather than its PTS.

    High-amplitude separated impulses exercise the overlap-add path. This is a
    bounded filter calibration, not an alignment score for the musician's take.
    """
    advance = rate // 80
    if advance < 1:
        raise MediaError("sample rate is too low for afftdn latency calibration")
    delay = 2 * advance
    count = rate
    positions = [rate // 4, rate * 3 // 5]
    samples = array.array("h", [0]) * (count * channels)
    for position in positions:
        for channel in range(channels):
            samples[position * channels + channel] = 24576
    source, output = directory / ".latency-input.wav", directory / ".latency-output.f32"
    try:
        with wave.open(str(source), "wb") as handle:
            handle.setnchannels(channels)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(samples.tobytes())
        ffmpeg(["-i", str(source), "-af", audio_filter, "-ar", str(rate),
                "-ac", str(channels), "-c:a", "pcm_f32le", "-f", "f32le", str(output)])
        rendered = array.array("f")
        with output.open("rb") as handle:
            rendered.fromfile(handle, output.stat().st_size // rendered.itemsize)
        if sys.byteorder != "little":
            rendered.byteswap()
        if len(rendered) != count * channels:
            raise MediaError("denoiser latency calibration changed sample extent")
        offsets = []
        for position in positions:
            for channel in range(channels):
                start, end = max(0, position - delay), min(count, position + 2 * delay + 1)
                peak = max(range(start, end), key=lambda i: abs(rendered[i * channels + channel]))
                if abs(rendered[peak * channels + channel]) < 0.1:
                    raise MediaError("denoiser calibration impulse was not observable")
                offsets.append(peak - position)
        if any(offset != delay for offset in offsets):
            raise MediaError(f"afftdn latency differs from calibrated source model: {offsets}, expected {delay}")
        return {"status": "measured_and_compensated", "filter": "afftdn",
                "sample_advance": advance, "delay_samples": delay,
                "delay_seconds": delay / rate, "measured_impulse_offsets_samples": offsets,
                "method": "two isolated impulses in each native-rate channel; exact output peak displacement",
                "source_model": "FFmpeg 8.1 af_afftdn.c: window_length=3*(sample_rate/80); insertion offset=2*(sample_rate/80)",
                "compensation": "pad input tail before filtering, discard filter leading delay, trim to original extent, reset sample timestamps",
                "remaining_bulk_delay_samples": 0,
                "actual_recording_waveform_alignment_measured": False}
    finally:
        source.unlink(missing_ok=True)
        output.unlink(missing_ok=True)


def video_frame_count(path: Path, stream_index: int) -> int:
    result = run([executable("ffprobe"), "-v", "error", "-threads", THREADS,
                  "-count_frames", "-select_streams", str(stream_index),
                  "-show_entries", "stream=nb_read_frames", "-of", "json", str(path)])
    try:
        return int(json.loads(result.stdout)["streams"][0]["nb_read_frames"])
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
        raise MediaError("could not verify decoded video frame count") from exc


def video_packets(path: Path, stream_index: int) -> list[dict]:
    result = run([executable("ffprobe"), "-v", "error", "-select_streams", str(stream_index),
                  "-show_packets", "-show_entries", "packet=pts,dts,duration,data_hash",
                  "-show_data_hash", "sha256", "-of", "json", str(path)])
    try:
        packets = json.loads(result.stdout)["packets"]
    except (KeyError, json.JSONDecodeError) as exc:
        raise MediaError("could not inspect ordered video packets") from exc
    if not isinstance(packets, list) or not packets:
        raise MediaError("video stream has no inspectable packets")
    return packets


def compare_video_packets(source_packets: list[dict], output_packets: list[dict],
                          source_time_base: str, output_time_base: str,
                          expected_translation: Fraction) -> dict:
    if len(source_packets) != len(output_packets):
        raise MediaError("video export changed packet count")
    source_tick, output_tick = Fraction(source_time_base), Fraction(output_time_base)
    # Allow at most one tick in the coarser stream clock for muxer rounding.
    tolerance = max(source_tick, output_tick)
    largest = {key: Fraction(0) for key in ("pts", "dts", "duration")}
    payload_hashes_verified = True
    for index, (before, after) in enumerate(zip(source_packets, output_packets)):
        for key in largest:
            old, new = before.get(key), after.get(key)
            if old is None or new is None:
                if old != new or key == "pts":
                    raise MediaError(f"video packet {index} has unverifiable {key}")
                continue
            translation = Fraction(0) if key == "duration" else expected_translation
            delta = abs(int(new) * output_tick - int(old) * source_tick - translation)
            if delta > tolerance:
                raise MediaError(f"video packet {index} changed {key} by {float(delta):.9f}s")
            largest[key] = max(largest[key], delta)
        old_hash, new_hash = before.get("data_hash"), after.get("data_hash")
        if old_hash is None or new_hash is None:
            payload_hashes_verified = False
        elif old_hash != new_hash:
            raise MediaError(f"video packet {index} encoded payload changed")
    return {"source_video_packets": len(source_packets), "export_video_packets": len(output_packets),
            "video_packet_verification_method": "ordered ffprobe packet PTS/DTS/durations in rational stream clocks and SHA256 encoded payloads",
            "video_packet_timeline_preserved": True,
            "video_packet_payload_hashes_preserved": payload_hashes_verified,
            "video_packet_expected_translation_seconds": float(expected_translation),
            "video_packet_clock_tolerance_seconds": float(tolerance),
            "video_packet_max_pts_delta_seconds": float(largest["pts"]),
            "video_packet_max_dts_delta_seconds": float(largest["dts"]),
            "video_packet_max_duration_delta_seconds": float(largest["duration"])}


def verify_video_export(video: Path, manifest: dict, final_path: Path) -> dict:
    source = Path(manifest["source"]["path"])
    original = manifest["source"]["probe"]
    if sha256(source) != manifest["source"]["sha256"]:
        raise MediaError("source hash differs during video verification")
    output = probe(video)
    output["format"]["filename"] = str(final_path)
    packet_evidence = compare_video_packets(
        video_packets(source, original["video"]["index"]), video_packets(video, output["video"]["index"]),
        original["video"]["time_base"], output["video"]["time_base"],
        -Fraction(str(original["format"]["start_time"] or 0)))
    cache_path = Path(manifest["run_dir"]) / ".video-frame-count-cache.json"
    try:
        count_cache = json.loads(cache_path.read_text())
    except (OSError, json.JSONDecodeError):
        count_cache = {}
    if not isinstance(count_cache, dict):
        count_cache = {}
    def cached_count(path: Path, stream_index: int, content_hash: str) -> int:
        key = f"{content_hash}:{stream_index}"
        cached = count_cache.get(key)
        if isinstance(cached, int) and not isinstance(cached, bool) and cached > 0:
            return cached
        count = video_frame_count(path, stream_index)
        count_cache[key] = count
        return count
    source_frames = cached_count(source, original["video"]["index"], manifest["source"]["sha256"])
    output_frames = cached_count(video, output["video"]["index"], sha256(video))
    cache_stage = cache_path.with_name(cache_path.name + "." + uuid.uuid4().hex)
    json_write(cache_stage, count_cache)
    cache_stage.replace(cache_path)
    if source_frames != output_frames:
        raise MediaError(f"video export changed frame count: {source_frames} -> {output_frames}")
    tolerance = 1024 / manifest["pcm"]["sample_rate"] + 0.002
    original_audio_start = number(original["audio"].get("start_time"))
    original_video_start = number(original["video"].get("start_time"))
    output_audio_start = number(output["audio"].get("start_time"))
    output_video_start = number(output["video"].get("start_time"))
    offset_delta = None
    if all(value is not None for value in (original_audio_start, original_video_start,
                                           output_audio_start, output_video_start)):
        offset_delta = (output_audio_start - output_video_start) - (original_audio_start - original_video_start)
        if abs(offset_delta) > tolerance:
            raise MediaError(f"video export changed audio/video start offset by {offset_delta:.6f}s")
    duration_delta = None
    old_duration = number(original["video"].get("duration"))
    new_duration = number(output["video"].get("duration"))
    if old_duration is not None and new_duration is not None:
        duration_delta = new_duration - old_duration
    output_duration = number(output["audio"].get("duration"))
    expected_duration = manifest["pcm"]["sample_count"] / manifest["pcm"]["sample_rate"]
    audio_duration_delta = None if output_duration is None else output_duration - expected_duration
    if audio_duration_delta is not None and abs(audio_duration_delta) > tolerance:
        raise MediaError(f"video export changed audio duration by {audio_duration_delta:.6f}s")
    measurement = loudness(video, manifest["profile"])
    peak = number(measurement.get("input_tp"))
    target_peak = manifest["profile"]["true_peak_dbtp"]
    return {"video_probe": output, "final_audio_loudness": measurement,
            "verification": {**packet_evidence,
                             "source_hash_verified": True,
                             "video_frame_count_verification_method": "ffprobe decoded frame counts; private cache keyed by exact media SHA256 and stream index",
                             "source_decoded_video_frames": source_frames,
                             "export_decoded_video_frames": output_frames,
                             "video_frame_count_preserved": True,
                             "relative_audio_video_start_delta_seconds": offset_delta,
                             "relative_audio_video_start_verified": offset_delta is not None,
                             "dsp_latency_compensation_recorded": manifest.get("dsp_latency", {}).get("denoise", {}).get("status") in ("measured_and_compensated", "bypass_no_filter_delay"),
                             "physical_audio_video_sync_verified": False,
                             "video_duration_delta_seconds": duration_delta,
                             "video_header_duration_diagnostic_only": True,
                             "audio_duration_delta_seconds": audio_duration_delta,
                             "aac_timing_tolerance_seconds": tolerance,
                             "final_true_peak_target_dbtp": target_peak,
                             "final_true_peak_within_target": (peak <= target_peak if peak is not None else
                                                               True if measurement.get("input_tp") == "-inf" else None)}}


def clean(value: str | Path, profile_value: str | Path, capture_interval=None,
          capture_review=None) -> dict:
    command_origin = len(COMMANDS)
    source = source_path(value)
    profile = load_profile(profile_value)
    if capture_interval is None:
        if capture_review is not None:
            raise MediaError("--capture-review requires --capture-interval START END",
                             "capture_interval_required")
        if profile.get("noise_capture_required") is True and profile.get("noise_capture_seconds") is None:
            raise MediaError(f"profile {profile.get('name', profile_value)} requires a reviewed per-take capture "
                             "interval: pass --capture-interval START END --capture-review TEXT for this take, "
                             "or select profile conservative3 explicitly (no capture binding)",
                             "capture_interval_required")
    else:
        check_capture_request(profile, capture_interval, capture_review)
    source_stat = source.stat()
    source_hash = sha256(source)
    if capture_interval is not None:
        profile = bind_capture(profile, capture_interval, capture_review, source_hash)
    if (profile.get("noise_capture_seconds") is not None
            and profile["noise_capture_source_sha256"] != source_hash):
        raise MediaError("noise capture source SHA-256 differs from this recording", "capture_source_mismatch")
    metadata = probe(source)
    audio = metadata["audio"]
    audio_origin = audio_timeline_origin(source, metadata)
    run_root = ROOT / "artifacts" / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    final = run_root / run_id
    staging = Path(tempfile.mkdtemp(prefix=".staging-" + run_id + "-", dir=run_root))
    try:
        working, denoised = staging / "source.wav", staging / "denoised.wav"
        ffmpeg(["-i", str(source), "-map", f"0:{audio['index']}", "-vn",
                "-ar", str(audio["sample_rate"]), "-ac", str(audio["channels"]),
                "-c:a", "pcm_f32le", str(working)])
        reference = pcm_info(working)
        if not reference["sample_count"]:
            raise MediaError("decoded audio has no samples")
        assumptions = ["No listening acceptance has been performed.",
                       "No metronome removal, timing correction, source separation, or declipping is applied.",
                       "Nine-string down-tuned guitar can contain intentional fundamentals near 32 Hz. No high-pass, rumble filter, or mains-hum notch is applied; denoising still requires review for low-frequency damage."]
        interval = profile.get("noise_capture_seconds")
        capture = None
        if interval is not None and interval[1] > reference["sample_count"] / reference["sample_rate"]:
            raise MediaError("noise capture interval extends beyond decoded audio",
                             "capture_interval_outside_source")
        if profile["denoise"]:
            audio_filter = (f"afftdn=nr={profile['reduction_db']}:nf={profile['noise_floor_db']}:"
                            f"tn=0:gs={profile['gain_smooth']}")
            if "adaptivity" in profile:
                audio_filter += f":ad={float(profile['adaptivity']):.9g}"
            latency = calibrate_denoise_latency(staging, audio_filter, audio["sample_rate"], audio["channels"])
            delay = latency["delay_samples"]
            if interval is not None:
                rate = reference["sample_rate"]
                start, end = round(interval[0] * rate), round(interval[1] * rate)
                if not 0 <= start < end <= reference["sample_count"]:
                    raise MediaError("noise capture sample interval is outside decoded audio",
                                     "capture_interval_outside_source")
                training_samples = end - start
                guard = math.ceil(rate / 10)
                prefix = training_samples + guard
                stop = training_samples / rate
                # Training is private preroll, not inserted into the published
                # source axis. The silence guard keeps frame-quantized stop
                # delivery away from original guitar/click samples.
                audio_filter = (f"[0:a]asplit=2[noise][body];"
                                f"[noise]atrim=start_sample={start}:end_sample={end},"
                                f"asetpts=N/SR/TB,apad=pad_len={guard}[training];"
                                f"[body]asetpts=N/SR/TB[take];"
                                f"[training][take]concat=n=2:v=0:a=1,apad=pad_len={delay},"
                                f"asendcmd=c='0 afftdn sn start;{stop:.12g} afftdn sn stop',"
                                f"{audio_filter},atrim=start_sample={prefix + delay}:"
                                f"end_sample={prefix + delay + reference['sample_count']},asetpts=N/SR/TB[out]")
                capture = {"source_sha256": source_hash,
                           "selected_seconds": interval, "selected_samples": [start, end],
                           "actual_selected_seconds": [start / rate, end / rate],
                           "interval_time_axis": "relative to first decoded original audio sample",
                           "source_media_span_seconds": ([audio_origin["seconds"] + start / rate,
                                                          audio_origin["seconds"] + end / rate]
                                                         if audio_origin["seconds"] is not None else None),
                           "authorization": "authorized_source_bound_noise_interval",
                           "review": profile.get("noise_capture_review", "selection supplied; absence of music/clicks not machine-verified"),
                           "noise_only_verified_by_worker": False,
                           "method": "selected source interval copied into internal afftdn sampling preroll",
                           "capture_stop_filter_seconds": stop,
                           "command_boundary_scope": "FFmpeg commands applied at audio-frame boundaries; silence guard separates stop from original body",
                           "guard_samples": guard, "preroll_samples_removed": prefix,
                           "filter_delay_samples_removed": delay,
                           "applies_to_original_start": True,
                           "absolute_noise_floor_db": profile["noise_floor_db"],
                           "absolute_floor_basis": "explicit candidate control; captured band shape is centered, not an independently measured absolute floor",
                           "source_axis_sample_count_preserved": True}
                assumptions.append("Source-bound noise sampling occurs in internal preroll; selected noise and silence guard plus calibrated afftdn delay are removed before publication, so the measured profile applies from original sample zero.")
                rendered_capture = ffmpeg(["-i", str(working), "-filter_complex", audio_filter, "-map", "[out]",
                                           "-ar", str(audio["sample_rate"]), "-ac", str(audio["channels"]),
                                           "-c:a", "pcm_f32le", str(denoised)])
                measured_bands = []
                for line in rendered_capture.stderr.splitlines():
                    if "bn=" in line:
                        try:
                            bands = [float(item) for item in line.split("bn=", 1)[1].split()]
                        except ValueError as exc:
                            raise MediaError("captured noise-band update is unreadable") from exc
                        if len(bands) != 15 or any(not math.isfinite(item) for item in bands):
                            raise MediaError("captured noise-band update is invalid")
                        measured_bands.append(bands)
                if len(measured_bands) != audio["channels"]:
                    raise MediaError("FFmpeg did not confirm one captured noise-band profile per channel")
                capture["captured_band_shape_db_per_channel"] = measured_bands
                capture["profile_update_status"] = "observed_ffmpeg_afftdn_band_profile_update"
            else:
                assumptions.append(f"Fixed noise floor {profile['noise_floor_db']} dB is an unverified diagnostic heuristic, not a measured noise profile; tracking is disabled.")
                # Padding precedes the delayed filter to retain original tail.
                audio_filter = (f"apad=pad_len={delay}," + audio_filter +
                                f",atrim=start_sample={delay}:end_sample={delay + reference['sample_count']},asetpts=N/SR/TB")
                ffmpeg(["-i", str(working), "-af", audio_filter, "-ar", str(audio["sample_rate"]),
                        "-ac", str(audio["channels"]), "-c:a", "pcm_f32le", str(denoised)])
        else:
            shutil.copyfile(working, denoised)
            latency = {"status": "bypass_no_filter_delay", "delay_samples": 0,
                       "remaining_bulk_delay_samples": 0,
                       "actual_recording_waveform_alignment_measured": True}
        ensure_pcm_matches(denoised, reference)
        residue = staging / "residue.wav"
        ffmpeg(["-i", str(working), "-i", str(denoised), "-filter_complex",
                "[1:a]volume=-1[negative];[0:a][negative]amix=inputs=2:normalize=0:duration=longest",
                "-ar", str(audio["sample_rate"]), "-ac", str(audio["channels"]),
                "-c:a", "pcm_f32le", str(residue)])
        ensure_pcm_matches(residue, reference)
        processed = staging / "processed.wav"
        post_stages = render_post_denoise(denoised, processed, profile, reference)
        final_pre_gain = processed if post_stages else denoised
        if post_stages:
            assumptions.append("Optional forward peaking EQ changes frequency-dependent phase; RMS compression changes attack/sustain amplitudes. No complete acoustic alignment or improved-tone acceptance is claimed.")
        baseline = normalize(working, staging / "baseline.wav", profile, audio)
        restored = normalize(final_pre_gain, staging / "cleaned.wav", profile, audio)
        ensure_pcm_matches(staging / "baseline.wav", reference)
        ensure_pcm_matches(staging / "cleaned.wav", reference)
        if source.stat().st_size != source_stat.st_size or source.stat().st_mtime_ns != source_stat.st_mtime_ns or sha256(source) != source_hash:
            raise MediaError("source changed during processing; outputs not published")
        manifest = {"schema_version": 1, "status": "rendered_unreviewed", "run_id": run_id,
                    "run_dir": str(final), "profile": profile,
                    "source": {"path": str(source), "sha256": source_hash, "probe": metadata},
                    "pcm": reference,
                    "noise_capture": capture,
                    "restoration_stages": [{"stage": "afftdn" if profile["denoise"] else "denoise_bypass",
                                             "output": "denoised.wav", "latency": latency},
                                            *post_stages,
                                            {"stage": "measured_loudness_normalization", "input": final_pre_gain.name,
                                             "output": "cleaned.wav"}],
                    "timeline": {"format_start_seconds": metadata["format"]["start_time"],
                                 "audio_start_seconds": audio_origin["seconds"],
                                 "audio_origin_receipt": audio_origin,
                                 "decoded_audio_origin": "first decoded source audio sample",
                                 "no_time_stretch": True},
                    "dsp_latency": {"denoise": latency,
                                    "post_denoise": {"stages": [stage["timing"] for stage in post_stages],
                                                     "sample_count_preserved": True,
                                                     "complete_acoustic_alignment_verified": False},
                                    "normalization": {"policy": "FFmpeg loudnorm native compensated timestamps; no additional trimming",
                                                      "actual_recording_waveform_alignment_measured": False,
                                                      "validation": "separate 44.1/48 kHz dynamic-mode impulse regression; not a listening or complete physical A/V synchronization claim"},
                                    "analysis_derivative_sample_mapping": "denoised sample zero maps to decoded source sample zero after calibrated filter-delay compensation",
                                    "physical_audio_video_sync_verified": False},
                    "outputs": {"source": "source.wav", "denoised": "denoised.wav",
                                "baseline": "baseline.wav", "cleaned": "cleaned.wav", "residue": "residue.wav",
                                **({"processed": "processed.wav"} if post_stages else {})},
                    "loudness": {"baseline": baseline, "cleaned": restored},
                    "tools": {name: run([executable(name), "-version"], 30).stdout.splitlines()[0]
                              for name in ("ffmpeg", "ffprobe")},
                    "threads": 2, "assumptions": assumptions,
                    "frequency_preservation": {"intentional_low_fundamental_hz": 32,
                                               "high_pass_applied": False, "hum_notches_applied": False,
                                               "music_preservation_listening_verified": False},
                    "commands": COMMANDS[command_origin:],
                    "output_sha256": {path.name: sha256(path) for path in staging.glob("*.wav")}}
        json_write(staging / "manifest.json", manifest)
        staging.rename(final)
        return manifest
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def encode_video_with_headroom(source: Path, cleaned: Path, video: Path,
                               manifest: dict, attempts: list[dict]) -> dict:
    """Bound delivery-only AAC gain by decoded true-peak measurements."""
    original = manifest["source"]["probe"]
    target = manifest["profile"]["true_peak_dbtp"]
    gain_db = 0.0
    max_attempts, max_attenuation, safety_margin = 3, 1.0, 0.05
    for index in range(max_attempts):
        audio_start = original["audio"]["start_time"] or 0.0
        format_start = original["format"]["start_time"] or 0.0
        args = ["-copyts", "-i", str(source), "-itsoffset", str(audio_start), "-i", str(cleaned),
                "-map", f"0:{original['video']['index']}", "-map", "1:a:0", "-map_metadata", "0",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-threads", THREADS]
        if gain_db:
            args += ["-af", f"volume={gain_db:.8f}dB"]
        args += ["-output_ts_offset", str(-format_start), "-avoid_negative_ts", "disabled",
                 "-movflags", "+faststart", str(video)]
        ffmpeg(args)
        measured = loudness(video, manifest["profile"])
        peak = number(measured.get("input_tp"))
        within = peak is not None and peak <= target
        # True digital silence cannot overshoot; other undefined measurements
        # cannot support a bounded attenuation estimate.
        if peak is None and measured.get("input_tp") == "-inf":
            within = True
        attempts.append({"attempt": index + 1, "feed_gain_db": gain_db,
                         "decoded_true_peak_dbtp": peak, "loudness": measured,
                         "true_peak_within_target": within, "encoded_sha256": sha256(video)})
        if within:
            return {"status": "decoded_aac_true_peak_verified", "target_true_peak_dbtp": target,
                    "feed_gain_db": gain_db, "attempts": attempts,
                    "max_attempts": max_attempts, "max_attenuation_db": max_attenuation,
                    "retry_safety_margin_db": safety_margin,
                    "scope": "delivery AAC feed only; PCM master unchanged; no performance correction"}
        if peak is None:
            raise MediaError("AAC true peak is unavailable; export cannot be verified")
        proposed = gain_db - (peak - target + safety_margin)
        if index + 1 == max_attempts or proposed < -max_attenuation:
            raise MediaError(f"AAC true peak {peak:.2f} dBTP exceeds target {target:.2f}; bounded headroom retries exhausted")
        gain_db = proposed
        video.unlink()  # Owned failed staging encode; its measurements/hash survive.
    raise MediaError("AAC headroom verification did not finish")


def export(value: str | Path) -> dict:
    command_origin = len(COMMANDS)
    directory = Path(value).expanduser().resolve()
    try:
        manifest = json.loads((directory / "manifest.json").read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise MediaError("run directory has no valid manifest") from exc
    source = source_path(manifest["source"]["path"])
    if sha256(source) != manifest["source"]["sha256"]:
        raise MediaError("source hash differs from the completed run")
    cleaned = directory / "cleaned.wav"
    ensure_pcm_matches(cleaned, manifest["pcm"])
    if sha256(cleaned) != manifest["output_sha256"]["cleaned.wav"]:
        raise MediaError("audio master hash differs from the completed run")
    destination = directory / "export"
    if destination.exists():
        try:
            outcome = json.loads((destination / "outcome.json").read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise MediaError("export directory already exists without a valid outcome") from exc
        for name, expected_hash in outcome.get("output_sha256", {}).items():
            if Path(name).name != name or sha256(destination / name) != expected_hash:
                raise MediaError("cached export output integrity check failed")
        if manifest["source"]["probe"]["video"] is not None:
            video = destination / "cleaned-video.mov"
            if "cleaned-video.mov" not in outcome.get("output_sha256", {}):
                raise MediaError("cached video export has no integrity receipt")
            outcome.update(verify_video_export(video, manifest, video))
            if outcome["verification"]["final_true_peak_within_target"] is False:
                raise MediaError("cached AAC export exceeds its true-peak target; preserve it as a revision before creating a fresh export")
        else:
            outcome["final_audio_loudness"] = loudness(cleaned, manifest["profile"])
        # Upgrade older completed receipts without rewriting media.
        receipt = destination / (".outcome-" + uuid.uuid4().hex + ".json")
        json_write(receipt, outcome)
        receipt.replace(destination / "outcome.json")
        return outcome
    staging = Path(tempfile.mkdtemp(prefix=".export-staging-", dir=directory))
    peak_attempts: list[dict] = []
    try:
        metadata = manifest["source"]["probe"]
        outcome = {"schema_version": 1, "status": "exported_unreviewed", "run_dir": str(directory),
                   "audio_master": str(cleaned), "video": None, "source_sha256": manifest["source"]["sha256"],
                   "dsp_latency": manifest.get("dsp_latency", {"status": "legacy_uncalibrated"}),
                   "listening_accepted": False}
        if metadata["video"] is not None:
            video = staging / "cleaned-video.mov"
            outcome["aac_headroom"] = encode_video_with_headroom(source, cleaned, video, manifest, peak_attempts)
            outcome.update(verify_video_export(video, manifest, destination / video.name))
            if outcome["verification"]["final_true_peak_within_target"] is False:
                raise MediaError("verified final AAC peak disagrees with successful headroom measurement")
            outcome.update(video=str(destination / video.name),
                           timeline_policy="copy original video timestamps; place replacement audio at original audio start; shift both by original container start; no shortest truncation")
        else:
            outcome["final_audio_loudness"] = loudness(cleaned, manifest["profile"])
        if sha256(source) != manifest["source"]["sha256"]:
            raise MediaError("source changed during export; outputs not published")
        outcome["commands"] = COMMANDS[command_origin:]
        outcome["output_sha256"] = {path.name: sha256(path) for path in staging.glob("*.mov")}
        json_write(staging / "outcome.json", outcome)
        staging.rename(destination)
        return outcome
    except BaseException as exc:
        if peak_attempts:
            failure_dir = directory / "export-failures"
            failure_dir.mkdir(exist_ok=True)
            json_write(failure_dir / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12] + ".json"),
                       {"status": "export_failed_master_retained", "error": str(exc),
                        "source_sha256": manifest["source"]["sha256"],
                        "master_sha256": manifest["output_sha256"]["cleaned.wav"],
                        "aac_attempts": peak_attempts, "commands": COMMANDS[command_origin:]})
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("probe")
    inspect.add_argument("input")
    restore = sub.add_parser("clean")
    restore.add_argument("input")
    restore.add_argument("profile", nargs="?", default=DEFAULT_PROFILE,
                         help="Profile name or path; default fuller requires --capture-interval")
    restore.add_argument("--capture-interval", nargs=2, type=float, metavar=("START", "END"),
                         help="Reviewed per-take noise capture interval in decoded-source seconds")
    restore.add_argument("--capture-review", help="Non-empty review text for --capture-interval")
    deliver = sub.add_parser("export")
    deliver.add_argument("run_dir")
    demo = sub.add_parser("demo")
    demo.add_argument("input")
    demo.add_argument("--profile", default=DEFAULT_PROFILE,
                      help="Profile name or path; default fuller requires --capture-interval")
    demo.add_argument("--capture-interval", nargs=2, type=float, metavar=("START", "END"),
                      help="Reviewed per-take noise capture interval in decoded-source seconds")
    demo.add_argument("--capture-review", help="Non-empty review text for --capture-interval")
    args = parser.parse_args(argv)
    try:
        if args.command == "probe":
            path = source_path(args.input)
            result = {"path": str(path), "sha256": sha256(path), "probe": probe(path)}
        elif args.command == "clean":
            result = clean(args.input, args.profile, args.capture_interval, args.capture_review)
        elif args.command == "export":
            result = export(args.run_dir)
        else:
            manifest = clean(args.input, args.profile, args.capture_interval, args.capture_review)
            result = dict(manifest, export=export(manifest["run_dir"]))
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except (MediaError, OSError, ValueError, KeyError) as exc:
        reason = exc.code if isinstance(exc, MediaError) else type(exc).__name__
        print(json.dumps({"status": "error", "error": str(exc), "reason": reason}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
