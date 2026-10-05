#!/usr/bin/env python3
"""Offline FFmpeg media worker. Original media is never modified.

Stdlib only. FFMPEG and FFPROBE may select executables; otherwise use PATH.
All media outputs are private local artifacts, not publication approvals.
"""
from __future__ import annotations

import argparse
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

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 600
THREADS = "2"
COMMANDS: list[list[str]] = []


class MediaError(RuntimeError):
    pass


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


def load_profile(value: str | Path) -> dict:
    path = Path(value).expanduser()
    if not path.is_file():
        path = ROOT / "profiles" / f"{value}.json"
    try:
        profile = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise MediaError(f"cannot read profile: {value}") from exc
    if not isinstance(profile, dict) or profile.get("schema_version") != 1:
        raise MediaError("profile requires schema_version: 1")
    if not isinstance(profile.get("denoise"), bool):
        raise MediaError("profile denoise must be a boolean")
    limits = {"integrated_lufs": (-70, -5), "true_peak_dbtp": (-9, 0),
              "reduction_db": (0.01, 12), "noise_floor_db": (-80, -20),
              "gain_smooth": (0, 50)}
    required = ["integrated_lufs", "true_peak_dbtp"]
    if profile["denoise"]:
        required += ["reduction_db", "noise_floor_db", "gain_smooth"]
    for key in required:
        val = profile.get(key)
        low, high = limits[key]
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or not low <= val <= high:
            raise MediaError(f"profile {key} must be between {low} and {high}")
    interval = profile.get("noise_capture_seconds")
    if interval is not None:
        if (not profile["denoise"] or profile.get("noise_capture_authorized") is not True
                or not isinstance(interval, list) or len(interval) != 2
                or any(isinstance(x, bool) or not isinstance(x, (int, float))
                       or not math.isfinite(x) for x in interval)
                or interval[0] < 0 or interval[1] <= interval[0]):
            raise MediaError("noise capture needs an explicitly authorized [start, end] interval")
    return profile


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
                             "video_duration_delta_seconds": duration_delta,
                             "video_header_duration_diagnostic_only": True,
                             "audio_duration_delta_seconds": audio_duration_delta,
                             "aac_timing_tolerance_seconds": tolerance,
                             "final_true_peak_target_dbtp": target_peak,
                             "final_true_peak_within_target": None if peak is None else peak <= target_peak}}


def clean(value: str | Path, profile_value: str | Path) -> dict:
    command_origin = len(COMMANDS)
    source = source_path(value)
    profile = load_profile(profile_value)
    source_stat = source.stat()
    source_hash = sha256(source)
    metadata = probe(source)
    audio = metadata["audio"]
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
        if interval is not None and interval[1] > reference["sample_count"] / reference["sample_rate"]:
            raise MediaError("noise capture interval extends beyond decoded audio")
        if profile["denoise"]:
            audio_filter = (f"afftdn=nr={profile['reduction_db']}:nf={profile['noise_floor_db']}:"
                            f"tn=0:gs={profile['gain_smooth']}")
            if interval is not None:
                audio_filter = (f"asendcmd=c='{interval[0]} afftdn sn start;"
                                f"{interval[1]} afftdn sn stop'," + audio_filter)
                assumptions.append("Operator-approved noise capture updates the filter after the selected interval; earlier audio uses the fixed floor.")
            else:
                assumptions.append(f"Fixed noise floor {profile['noise_floor_db']} dB is an unverified diagnostic heuristic, not a measured noise profile; tracking is disabled.")
            ffmpeg(["-i", str(working), "-af", audio_filter, "-ar", str(audio["sample_rate"]),
                    "-ac", str(audio["channels"]), "-c:a", "pcm_f32le", str(denoised)])
        else:
            shutil.copyfile(working, denoised)
        ensure_pcm_matches(denoised, reference)
        residue = staging / "residue.wav"
        ffmpeg(["-i", str(working), "-i", str(denoised), "-filter_complex",
                "[1:a]volume=-1[negative];[0:a][negative]amix=inputs=2:normalize=0:duration=longest",
                "-ar", str(audio["sample_rate"]), "-ac", str(audio["channels"]),
                "-c:a", "pcm_f32le", str(residue)])
        ensure_pcm_matches(residue, reference)
        baseline = normalize(working, staging / "baseline.wav", profile, audio)
        restored = normalize(denoised, staging / "cleaned.wav", profile, audio)
        ensure_pcm_matches(staging / "baseline.wav", reference)
        ensure_pcm_matches(staging / "cleaned.wav", reference)
        if source.stat().st_size != source_stat.st_size or source.stat().st_mtime_ns != source_stat.st_mtime_ns or sha256(source) != source_hash:
            raise MediaError("source changed during processing; outputs not published")
        manifest = {"schema_version": 1, "status": "rendered_unreviewed", "run_id": run_id,
                    "run_dir": str(final), "profile": profile,
                    "source": {"path": str(source), "sha256": source_hash, "probe": metadata},
                    "pcm": reference,
                    "timeline": {"format_start_seconds": metadata["format"]["start_time"],
                                 "audio_start_seconds": audio["start_time"],
                                 "decoded_audio_origin": "first decoded source audio sample",
                                 "no_time_stretch": True},
                    "outputs": {"source": "source.wav", "denoised": "denoised.wav",
                                "baseline": "baseline.wav", "cleaned": "cleaned.wav", "residue": "residue.wav"},
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
        else:
            outcome["final_audio_loudness"] = loudness(cleaned, manifest["profile"])
        # Upgrade older completed receipts without rewriting media.
        receipt = destination / (".outcome-" + uuid.uuid4().hex + ".json")
        json_write(receipt, outcome)
        receipt.replace(destination / "outcome.json")
        return outcome
    staging = Path(tempfile.mkdtemp(prefix=".export-staging-", dir=directory))
    try:
        metadata = manifest["source"]["probe"]
        outcome = {"schema_version": 1, "status": "exported_unreviewed", "run_dir": str(directory),
                   "audio_master": str(cleaned), "video": None, "source_sha256": manifest["source"]["sha256"],
                   "listening_accepted": False}
        if metadata["video"] is not None:
            audio_start = metadata["audio"]["start_time"] or 0.0
            format_start = metadata["format"]["start_time"] or 0.0
            video = staging / "cleaned-video.mov"
            ffmpeg(["-copyts", "-i", str(source), "-itsoffset", str(audio_start), "-i", str(cleaned),
                    "-map", f"0:{metadata['video']['index']}", "-map", "1:a:0", "-map_metadata", "0",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-threads", THREADS,
                    "-output_ts_offset", str(-format_start), "-avoid_negative_ts", "disabled",
                    "-movflags", "+faststart", str(video)])
            outcome.update(verify_video_export(video, manifest, destination / video.name))
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
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("probe")
    inspect.add_argument("input")
    restore = sub.add_parser("clean")
    restore.add_argument("input")
    restore.add_argument("profile", nargs="?", default="conservative3")
    deliver = sub.add_parser("export")
    deliver.add_argument("run_dir")
    demo = sub.add_parser("demo")
    demo.add_argument("input")
    demo.add_argument("--profile", default="conservative3")
    args = parser.parse_args(argv)
    try:
        if args.command == "probe":
            path = source_path(args.input)
            result = {"path": str(path), "sha256": sha256(path), "probe": probe(path)}
        elif args.command == "clean":
            result = clean(args.input, args.profile)
        elif args.command == "export":
            result = export(args.run_dir)
        else:
            manifest = clean(args.input, args.profile)
            result = dict(manifest, export=export(manifest["run_dir"]))
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 0
    except (MediaError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
