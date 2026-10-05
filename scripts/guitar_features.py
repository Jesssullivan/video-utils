#!/usr/bin/env python3
"""Bounded, local, experimental measurements for low-tuned distorted guitar.

No dependency installation, model downloads, media modification or transcription.
"""
from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile

RATE = 16000
MAX_SECONDS = 300
FRAME = 4096
BANDS = ((28, 80), (80, 250), (250, 2000), (2000, 8000))
INSTRUMENT = {"instrument": "nine_string_down_tuned_distorted_guitar", "lowest_expected_hz": 32,
              "exact_tuning": None, "low_frequency_is_not_automatically_noise": True}


def db(value: float) -> float | None:
    return round(20 * math.log10(value), 4) if value > 0 else None


def fft(values: list[complex], inverse: bool = False) -> list[complex]:
    """Radix-2 FFT; inverse includes 1/N normalization."""
    n = len(values)
    if n == 0 or n & (n - 1):
        raise ValueError("FFT length must be a nonzero power of two")
    result = list(values)
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            result[i], result[j] = result[j], result[i]
    size = 2
    while size <= n:
        angle = (2 if inverse else -2) * math.pi / size
        step = complex(math.cos(angle), math.sin(angle))
        for start in range(0, n, size):
            phase = 1 + 0j
            for offset in range(size // 2):
                left = result[start + offset]
                right = result[start + offset + size // 2] * phase
                result[start + offset] = left + right
                result[start + offset + size // 2] = left - right
                phase *= step
        size *= 2
    return [v / n for v in result] if inverse else result


def spectrum(samples, rate: int = RATE) -> dict:
    if not samples:
        raise ValueError("Empty spectrum frame")
    size = 1 << (len(samples) - 1).bit_length()
    center = statistics.mean(samples)
    window = [.5 - .5 * math.cos(2 * math.pi * i / (len(samples) - 1))
              for i in range(len(samples))] if len(samples) > 1 else [1.0]
    values = [(v - center) * w for v, w in zip(samples, window)]
    transformed = fft(values + [0.0] * (size - len(values)))
    norm = size * sum(w * w for w in window)
    powers = [(abs(v) ** 2 / norm) * (1 if i in (0, size // 2) else 2)
              for i, v in enumerate(transformed[:size // 2 + 1])]
    bands = []
    total = sum(powers)
    for low, high in BANDS:
        energy = sum(power for i, power in enumerate(powers)
                     if low <= i * rate / size < high)
        bands.append({"low_hz": low, "high_hz_exclusive": high,
                      "mean_square": energy, "rms_dbfs": db(math.sqrt(energy)),
                      "fraction_of_ac_energy": energy / total if total > 0 else None})
    peaks = [i for i in range(1, len(powers) - 1)
             if powers[i] > powers[i - 1] and powers[i] >= powers[i + 1] and powers[i] > 1e-12]
    peaks = sorted(peaks, key=lambda i: powers[i], reverse=True)[:8]
    return {"bands": bands, "ac_mean_square": total,
            "spectral_peaks": [{"bin_center_hz": i * rate / size, "mean_square": powers[i]}
                               for i in peaks], "bin_width_hz": rate / size}


def rms_windows(samples, rate: int = RATE) -> list[dict]:
    result = []
    size = rate // 2
    for start in range(0, len(samples), size):
        block = samples[start:start + size]
        rms = math.sqrt(sum(x * x for x in block) / len(block))
        result.append({"start_seconds": start / rate, "end_seconds": (start + len(block)) / rate,
                       "rms": rms, "rms_dbfs": db(rms)})
    return result


def noise(samples) -> dict:
    windows = rms_windows(samples)
    count = min(20, max(1, math.ceil(len(windows) * .1)))
    candidates = sorted(windows, key=lambda x: x["rms"])[:count]
    for candidate in candidates:
        start = round(candidate["start_seconds"] * RATE)
        candidate["measured_spectrum"] = spectrum(samples[start:start + FRAME])
    return {"observations": {"quiet_candidate_windows": sorted(candidates, key=lambda x: x["start_seconds"]),
                              "whole_signal_rms_dbfs": db(math.sqrt(sum(x*x for x in samples) / len(samples)))},
            "interpretation": {"background_noise_identity": "unknown", "noise_only_profile": None,
                               "next_action": "Audition candidates; approve a noise-only interval before profiling.",
                               "warning": "Quiet passages may contain 32 Hz notes, sustained guitar, metronome or room sound."}}


def tone(samples) -> dict:
    frames = [spectrum(samples[start:start + FRAME]) for start in range(0, len(samples) - FRAME + 1, RATE)]
    if not frames:
        frames = [spectrum(samples)]
    bands = []
    total = statistics.mean(f["ac_mean_square"] for f in frames)
    for index, (low, high) in enumerate(BANDS):
        energy = statistics.mean(f["bands"][index]["mean_square"] for f in frames)
        bands.append({"low_hz": low, "high_hz_exclusive": high, "mean_square": energy,
                      "rms_dbfs": db(math.sqrt(energy)), "fraction_of_ac_energy": energy / total if total > 0 else None})
    return {"observations": {"sampled_band_energies": bands, "measured_frames": len(frames),
                              "sample_peak": max(abs(x) for x in samples),
                              "near_full_scale_sample_fraction": sum(abs(x) >= .999 for x in samples) / len(samples)},
            "interpretation": {"tone_quality": "requires_listening", "intentional_distortion": "unknown",
                               "clipping_damage": "not_inferred_from_near_full_scale_samples",
                               "warning": "Band energies describe the mono mixture; they do not identify guitar or nuisance sources."}}


def periodicity(samples, rate: int = RATE) -> dict:
    if len(samples) < rate // 4:
        return {"frequency_hz": None, "reason": "less_than_250ms"}
    center = statistics.mean(samples)
    values = [x - center for x in samples]
    energy = sum(x*x for x in values)
    if energy / len(values) < 1e-10:
        return {"frequency_hz": None, "reason": "insufficient_ac_energy"}
    n = 1 << (2 * len(values) - 1).bit_length()
    transformed = fft(values + [0.0] * (n - len(values)))
    correlation = fft([abs(v) ** 2 for v in transformed], inverse=True)
    prefix = [0.0]
    for x in values:
        prefix.append(prefix[-1] + x*x)
    lag_min, lag_max = max(2, round(rate / 1000)), min(len(values)//2, round(rate / 28))
    scores = {}
    for lag in range(lag_min - 1, lag_max + 2):
        left = prefix[len(values) - lag]
        right = energy - prefix[lag]
        scores[lag] = correlation[lag].real / math.sqrt(max(1e-30, left * right))
    peaks = [lag for lag in range(lag_min, lag_max + 1)
             if scores[lag] > .6 and scores[lag] >= scores[lag-1] and scores[lag] > scores[lag+1]]
    if not peaks:
        return {"frequency_hz": None, "reason": "no_strong_periodicity", "highest_score": max(scores.values())}
    strongest = max(scores[lag] for lag in peaks)
    # Shortest strong repeat reduces subharmonic selection; octave ambiguity remains.
    lag = next(lag for lag in peaks if scores[lag] >= .95 * strongest)
    a, b, c = scores[lag - 1], scores[lag], scores[lag + 1]
    correction = .5 * (a - c) / (a - 2*b + c) if abs(a - 2*b + c) > 1e-12 else 0.0
    frequency = rate / (lag + max(-.5, min(.5, correction)))
    return {"frequency_hz": frequency, "normalized_autocorrelation_score": b,
            "score_kind": "heuristic_not_probability", "harmonic_octave_ambiguity": True,
            "alternative_repeat_hz": [rate / other for other in peaks if other != lag][:6]}


def notes(samples) -> dict:
    starts = list(range(0, len(samples) - FRAME + 1, RATE))
    if len(starts) > 120:
        starts = [starts[round(i * (len(starts) - 1) / 119)] for i in range(120)]
    frames = []
    for start in starts:
        block = samples[start:start + FRAME]
        frames.append({"start_seconds": start / RATE, "end_seconds": (start + FRAME) / RATE,
                       "periodicity_candidate": periodicity(block),
                       "spectral_peaks": spectrum(block)["spectral_peaks"]})
    return {"observations": {"sparse_analysis_frames": frames},
            "interpretation": {"note_transcription": "unsupported", "polyphonic_transcription": "unsupported",
                               "intended_notes": None, "string_identity": None, "tuning_reference": None,
                               "tonic": None, "mode": None, "tonal_inference_status": "unsupported_from_sparse_mixture_periodicity",
                               "performance_grade": "not_graded",
                               "warning": "Mixture periodicity may be harmonics, clicks or another source; sparse frames miss attacks. Exact tuning and intended notes require an approved reference."}}


def phrases(samples) -> dict:
    windows = rms_windows(samples)
    energies = [w["rms"] for w in windows]
    median = statistics.median(energies)
    threshold = median * .15
    gaps = []
    opened = None
    for index, value in enumerate(energies + [float("inf")]):
        quiet = value <= threshold and median > 1e-8
        if quiet and opened is None:
            opened = index
        elif not quiet and opened is not None:
            if index - opened >= 2:
                gaps.append({"start_seconds": windows[opened]["start_seconds"],
                             "end_seconds": windows[index-1]["end_seconds"], "kind": "low_energy_gap_candidate"})
            opened = None
    repeated = []
    size = 16  # eight seconds of the half-second amplitude envelope
    for first in range(0, len(energies) - size + 1, 8):
        a = energies[first:first + size]
        if max(a, default=0) < 1e-8:
            continue
        mean_a = statistics.mean(a)
        a = [x - mean_a for x in a]
        norm_a = sum(x*x for x in a)
        if norm_a < 1e-10:
            continue
        for second in range(first + size, len(energies) - size + 1, 8):
            b = energies[second:second + size]
            mean_b = statistics.mean(b)
            if mean_b < 1e-8:
                continue
            b = [x - mean_b for x in b]
            norm_b = sum(x*x for x in b)
            score = sum(x*y for x,y in zip(a,b)) / math.sqrt(max(1e-30, norm_a * norm_b))
            if score > .9:
                repeated.append({"first_start_seconds": first * .5, "second_start_seconds": second * .5,
                                 "duration_seconds": 8, "envelope_similarity": score})
    repeated = sorted(repeated, key=lambda x: x["envelope_similarity"], reverse=True)[:20]
    return {"observations": {"low_energy_gap_candidates": gaps, "similar_envelope_region_candidates": repeated},
            "interpretation": {"semantic_phrases": "unknown", "phrase_mistakes": "not_graded",
                               "phrase_confidence": "unvalidated_heuristic_not_probability",
                               "warning": "Envelope resemblance is not a repeated riff. Confirm phrases and an expected-rhythm reference before judging mistakes."}}


def inherit_manifest_lineage(result: dict, run_dir: Path) -> None:
    """Rebase only a cryptographically matched, untimed canonical PCM derivative."""
    manifest_path = run_dir / "manifest.json"
    source = result["source"]
    source["probed_input_audio_start_seconds"] = source["audio_stream_start_seconds"]
    result["lineage"] = {"status": "input_stream_timeline", "input_sha256": source["sha256"],
                         "original_source_sha256": None, "canonical_pcm": None,
                         "timeline_basis": "probed_input_audio_stream_start"}
    if not manifest_path.exists():
        return
    try:
        if manifest_path.stat().st_size > 5_000_000:
            raise ValueError("oversized_manifest")
        manifest = json.loads(manifest_path.read_text())
        matches = [name for name in ("source.wav", "denoised.wav", "cleaned.wav")
                   if manifest.get("output_sha256", {}).get(name) == source["sha256"]]
        if not matches:
            raise ValueError("input_hash_not_canonical_derivative")
        timeline = manifest["timeline"]
        start = float(timeline["audio_start_seconds"])
        pcm = manifest["pcm"]
        if timeline.get("no_time_stretch") is not True or not math.isfinite(start):
            raise ValueError("canonical_timeline_not_verified")
        if (not isinstance(pcm, dict) or pcm.get("sample_rate") != source["sample_rate"]
                or pcm.get("channels") != source["channels"]
                or not isinstance(pcm.get("sample_count"), int) or pcm["sample_count"] <= 0):
            raise ValueError("canonical_pcm_metadata_mismatch")
        expected_duration = pcm["sample_count"] / pcm["sample_rate"]
        if abs(result["analysis"]["duration_seconds"] - expected_duration) > 2 / RATE:
            raise ValueError("canonical_decoded_length_mismatch")
        original_hash = manifest["source"]["sha256"]
        if not isinstance(original_hash, str) or not original_hash:
            raise ValueError("missing_original_source_hash")
        source["audio_stream_start_seconds"] = start
        result["lineage"] = {"status": "verified_canonical_derivative", "input_sha256": source["sha256"],
                             "original_source_sha256": original_hash, "canonical_pcm": pcm,
                             "matched_artifact_names": matches, "manifest": str(manifest_path),
                             "timeline_basis": "hash_matched_canonical_pcm_original_audio_stream_start",
                             "original_audio_start_seconds": start}
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        result["lineage"]["manifest_status"] = "rejected"
        result["lineage"]["manifest_rejection_reason"] = str(exc)


def phrase_context(result: dict, run_dir: Path) -> None:
    """Attach same-source DAG context without converting estimates into truth."""
    context = {}
    for name in ("analysis", "notes"):
        path = run_dir / f"{name}.json"
        if not path.exists():
            context[name] = {"status": "not_available"}
            continue
        if path.stat().st_size > 5_000_000:
            context[name] = {"status": "rejected_oversized_context"}
            continue
        try:
            payload = json.loads(path.read_text())
            if not isinstance(payload, dict) or payload.get("source", {}).get("sha256") != result["source"]["sha256"]:
                context[name] = {"status": "rejected_source_mismatch"}
                continue
            if name == "analysis":
                grid = payload.get("click_grid") or {}
                context[name] = {"status": "experimental_same_source", "path": str(path),
                                 "bpm_candidate": grid.get("bpm"), "meter": payload.get("meter"),
                                 "grid_identity": grid.get("identity"), "reference_approved": False}
            else:
                interpretation = payload.get("interpretation", {})
                context[name] = {"status": "experimental_same_source", "path": str(path),
                                 "tonic": interpretation.get("tonic"), "mode": interpretation.get("mode"),
                                 "note_transcription": interpretation.get("note_transcription"),
                                 "reference_approved": False}
        except (ValueError, OSError, TypeError, AttributeError):
            context[name] = {"status": "invalid_context"}
    result["dag_context"] = context
    spans = []
    for item in result["observations"]["low_energy_gap_candidates"]:
        spans.append({"start_seconds": item["start_seconds"], "end_seconds": item["end_seconds"],
                      "kind": "phrase_boundary_review_candidate", "evidence": "low_energy_gap",
                      "uncertainty": "may_be_intended_rest_or_recording_gap", "performance_issue": None})
    for item in result["observations"]["similar_envelope_region_candidates"]:
        spans.append({"start_seconds": item["second_start_seconds"],
                      "end_seconds": item["second_start_seconds"] + item["duration_seconds"],
                      "kind": "recurrence_review_candidate", "reference_start_seconds": item["first_start_seconds"],
                      "evidence": "amplitude_envelope_similarity", "score": item["envelope_similarity"],
                      "uncertainty": "same_envelope_does_not_establish_same_notes_or_intent", "performance_issue": None})
    start = result["source"]["audio_stream_start_seconds"]
    for span in spans:
        span["source_start_seconds"] = start + span["start_seconds"]
        span["source_end_seconds"] = start + span["end_seconds"]
    result["observations"]["proposed_review_spans"] = sorted(spans, key=lambda s: s["start_seconds"])


def load(source: Path) -> tuple[array.array, dict]:
    probe_command = [os.environ.get("FFPROBE", "ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(source)]
    result = subprocess.run(probe_command, capture_output=True, timeout=30, check=True)
    probe = json.loads(result.stdout)
    audio = next((s for s in probe.get("streams", []) if s.get("codec_type") == "audio"), None)
    if audio is None:
        raise ValueError("Input has no audio stream")
    duration = float(audio.get("duration", probe.get("format", {}).get("duration", "nan")))
    if not math.isfinite(duration) or not 0 < duration <= MAX_SECONDS:
        raise ValueError(f"Audio duration must be known, positive and <= {MAX_SECONDS} seconds; explicitly trim longer inputs")
    command = [os.environ.get("FFMPEG", "ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-threads", "2", "-i", str(source), "-map", "0:a:0", "-vn", "-t", str(MAX_SECONDS), "-ac", "1", "-ar", str(RATE), "-filter_threads", "2", "-threads", "2", "-f", "f32le", "pipe:1"]
    decoded = subprocess.run(command, capture_output=True, timeout=300, check=True)
    samples = array.array("f")
    samples.frombytes(decoded.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples or len(samples) > RATE * MAX_SECONDS + RATE or any(not math.isfinite(x) for x in samples):
        raise ValueError("Invalid or oversized decoded audio")
    return samples, {"audio_stream": audio, "decode_command": command, "probe_command": probe_command}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool", choices=("noise", "tone", "notes", "phrases"))
    parser.add_argument("input", type=Path)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        source = args.input.expanduser().resolve(strict=True)
        if not source.is_file():
            raise ValueError("Input must be a regular file")
        destination = args.run_dir.expanduser().resolve() / f"{args.tool}.json"
        if source == destination:
            raise ValueError("Output cannot overwrite source")
        samples, provenance = load(source)
        digest = hashlib.sha256()
        with source.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        audio = provenance["audio_stream"]
        result = {"schema_version": 1, "tool": args.tool, "status": "experimental",
                  "instrument_context": INSTRUMENT, "source": {"path": str(source), "sha256": digest.hexdigest(),
                  "audio_stream_start_seconds": float(audio.get("start_time", 0)),
                  "sample_rate": int(audio["sample_rate"]), "channels": audio["channels"]},
                  "analysis": {"sample_rate": RATE, "channels": 1, "sample_format": "f32le",
                  "duration_seconds": len(samples) / RATE, "maximum_input_seconds": MAX_SECONDS,
                  "frame_samples": FRAME, "frame_seconds": FRAME / RATE, "spectral_hop_seconds": 1,
                  "pitch_maximum_frames": 120, "pitch_range_hz": [28, 1000], "rms_window_seconds": .5,
                  "timestamp_basis": "decoded_audio_relative_add_source_audio_stream_start_for_source_timeline",
                  "maximum_ffmpeg_threads": 2, "ffmpeg_timeout_seconds": 300,
                  "protected_fundamental_guard_band_hz": [28, 80],
                  "expected_lowest_fundamental_hz": 32,
                  "band_boundaries_hz": [list(b) for b in BANDS], "spectrum_method": "demeaned_Hann_radix2_FFT",
                  "pitch_method": "zero_padded_FFT_normalized_autocorrelation_not_YIN",
                  "quiet_candidate_rule": "lowest_10_percent_RMS_windows_maximum20",
                  "phrase_rule": "gaps_at_15percent_median_RMS_minimum1second_and_8second_envelope_similarity_above0.9",
                  "settings_are_fixed_in_this_pilot": True}, "provenance": provenance,
                  **globals()[args.tool](samples)}
        inherit_manifest_lineage(result, destination.parent)
        if args.tool == "phrases":
            phrase_context(result, destination.parent)
        destination.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
        with tempfile.NamedTemporaryFile("w", dir=destination.parent, prefix=f".{args.tool}-", delete=False) as handle:
            handle.write(encoded)
            temporary = Path(handle.name)
        temporary.replace(destination)
        print(encoded, end="")
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"guitar features: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
