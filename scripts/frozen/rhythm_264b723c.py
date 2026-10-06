#!/usr/bin/env python3
"""Bounded offline rhythm measurements; detected attacks are not graded notes."""
from __future__ import annotations

import argparse
import array
import csv
from fractions import Fraction
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import tempfile

RATE = 16000
HOP = 80
MAX_SECONDS = 1800


def run(command: list[str], timeout: int = 180) -> bytes:
    result = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace")[-2000:])
    return result.stdout


def probe(source: Path) -> dict:
    result = json.loads(run([os.environ.get("FFPROBE", "ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(source)], 30))
    audio = next((s for s in result["streams"] if s["codec_type"] == "audio"), None)
    if audio is None:
        raise ValueError("Input has no audio stream")
    duration = float(audio.get("duration", result.get("format", {}).get("duration", "nan")))
    if not math.isfinite(duration) or duration <= 0 or duration > MAX_SECONDS:
        raise ValueError(f"Audio duration must be known and between 0 and {MAX_SECONDS} seconds")
    return {"audio": audio, "format": result.get("format", {})}


def decode(source: Path) -> array.array:
    raw = run([os.environ.get("FFMPEG", "ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-threads", "1", "-i", str(source),
               "-map", "0:a:0", "-vn", "-t", str(MAX_SECONDS), "-ac", "1", "-ar", str(RATE), "-filter_threads", "1", "-threads", "1", "-f", "f32le", "pipe:1"])
    samples = array.array("f")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples or any(not math.isfinite(x) for x in samples):
        raise ValueError("Decoded audio is empty or contains non-finite samples")
    return samples


def envelopes(samples, rate: int = RATE, hop: int = HOP) -> tuple[list[float], list[float]]:
    """RMS and first-difference RMS: latter emphasizes high frequencies, not identity."""
    rms, difference = [], []
    previous = 0.0
    for start in range(0, len(samples), hop):
        block = samples[start:start + hop]
        energy = high = 0.0
        for value in block:
            energy += value * value
            high += (value - previous) ** 2
            previous = value
        rms.append(math.sqrt(energy / len(block)))
        difference.append(math.sqrt(high / len(block)))
    return rms, difference


def novelty(envelope: list[float]) -> list[float]:
    return [0.0] + [max(0.0, envelope[i] - envelope[i - 1]) for i in range(1, len(envelope))]


def peak_indices(values: list[float], threshold: float, min_gap: int = 5) -> list[int]:
    candidates = [i for i in range(1, len(values) - 1)
                  if values[i] > threshold and values[i] >= values[i - 1] and values[i] > values[i + 1]]
    kept = []
    for candidate in candidates:
        if kept and candidate - kept[-1] < min_gap:
            if values[candidate] > values[kept[-1]]:
                kept[-1] = candidate
        else:
            kept.append(candidate)
    return kept


def tempo_candidates(envelope: list[float], hop_seconds: float) -> list[dict]:
    """Normalized autocorrelation of transient envelope; scores are heuristic."""
    if len(envelope) < 100 or max(envelope, default=0) < 1e-7:
        return []
    center = statistics.mean(envelope)
    values = [v - center for v in envelope]
    lag_min = max(2, round(60 / 240 / hop_seconds))
    lag_max = min(round(60 / 40 / hop_seconds), len(values) // 3)
    scores = {}
    energy = sum(v * v for v in values)
    if energy < 1e-12:
        return []
    for lag in range(lag_min, lag_max + 1):
        cross = sum(values[i] * values[i - lag] for i in range(lag, len(values)))
        left = energy - sum(v * v for v in values[:lag])
        right = energy - sum(v * v for v in values[-lag:])
        scores[lag] = cross / math.sqrt(max(1e-20, left * right))
    peaks = [lag for lag, score in scores.items() if score > .08 and
             score >= scores.get(lag - 1, -1) and score >= scores.get(lag + 1, -1)]
    ranked = sorted(peaks, key=lambda lag: scores[lag], reverse=True)
    result = []
    for lag in ranked:
        # Refine the peak below envelope-hop resolution with a parabola.
        a, b, c = scores.get(lag - 1, scores[lag]), scores[lag], scores.get(lag + 1, scores[lag])
        correction = .5 * (a - c) / (a - 2 * b + c) if abs(a - 2 * b + c) > 1e-12 else 0
        period = (lag + max(-.5, min(.5, correction))) * hop_seconds
        bpm = 60 / period
        if any(abs(bpm - item["bpm"]) < 2 for item in result):
            continue
        result.append({"bpm": round(bpm, 3), "period_seconds": period,
                       "autocorrelation_score": round(scores[lag], 4), "evidence": "first_difference_transient_periodicity"})
        if len(result) == 8:
            break
    return result


def choose_tempo(candidates: list[dict]) -> dict | None:
    if not candidates:
        return None
    best = candidates[0]
    # Prefer a common practice pulse within the strongest family; alternatives stay visible.
    family = [c for c in candidates if c["autocorrelation_score"] >= .85 * best["autocorrelation_score"]
              and 70 <= c["bpm"] <= 150]
    return max(family, key=lambda c: c["autocorrelation_score"]) if family else best


def fit_click_grid(values: list[float], period: float, hop_seconds: float) -> dict | None:
    if not values or max(values, default=0) < 1e-7 or period <= 0:
        return None
    bins = max(8, round(period / hop_seconds))
    histogram = [0.0] * bins
    for index, value in enumerate(values):
        histogram[round((index * hop_seconds % period) / period * bins) % bins] += value
    phase = max(range(bins), key=lambda i: histogram[i]) / bins * period
    event_indices = peak_indices(values, max(statistics.median(values) * 3, max(values) * .04), 4)
    by_beat = {}
    for index in event_indices:
        time = (index + .5) * hop_seconds
        beat = round((time - phase) / period)
        residual = time - (phase + beat * period)
        if abs(residual) <= period * .12 and (beat not in by_beat or values[index] > values[by_beat[beat]]):
            by_beat[beat] = index
    if len(by_beat) < 4:
        return None
    pairs = [(beat, (index + .5) * hop_seconds) for beat, index in sorted(by_beat.items())]
    # Iteratively fit and reject phase outliers; keep real events separate from fitted times.
    fitted_phase, fitted_period = phase, period
    for _ in range(3):
        retained = [(b, t) for b, t in pairs if abs(t - (fitted_phase + b * fitted_period)) <= period * .08]
        if len(retained) < 4:
            break
        mean_b = statistics.mean(b for b, _ in retained)
        mean_t = statistics.mean(t for _, t in retained)
        variance = sum((b - mean_b) ** 2 for b, _ in retained)
        if variance == 0:
            break
        fitted_period = sum((b - mean_b) * (t - mean_t) for b, t in retained) / variance
        fitted_phase = mean_t - mean_b * fitted_period
    residuals = [t - (fitted_phase + b * fitted_period) for b, t in pairs]
    coverage = len(pairs) / max(1, pairs[-1][0] - pairs[0][0] + 1)
    median_error = statistics.median(abs(r) for r in residuals)
    if median_error > min(.025, period * .05) or coverage < .2:
        return None
    # These labels describe evidence quality, not probability of instrument identity.
    label = "strong_periodic_evidence" if coverage > .7 and median_error < .02 else "limited_periodic_evidence"
    return {"bpm": 60 / fitted_period, "period_seconds": fitted_period,
            "phase_seconds_audio_relative": fitted_phase, "candidate_coverage": coverage,
            "median_absolute_residual_ms": median_error * 1000,
            "confidence_label": label, "confidence_kind": "heuristic_not_probability",
            "identity": "periodic_high_frequency_transients_not_verified_metronome",
            "observed_events": [{"analysis_frame": by_beat[b], "beat_index": b,
                                  "audio_relative_seconds": t, "grid_offset_ms": r * 1000}
                                 for (b, t), r in zip(pairs, residuals)]}


def grid_offset(time: float, grid: dict) -> tuple[int, float]:
    beat = round((time - grid["phase_seconds_audio_relative"]) / grid["period_seconds"])
    return beat, (time - (grid["phase_seconds_audio_relative"] + beat * grid["period_seconds"])) * 1000


def subdivision_candidates(times: list[float], grid: dict | None) -> dict:
    """Describe attack alignment with possible subdivisions, without a score/reference."""
    if not grid or len(times) < 4:
        return {"status": "insufficient_grid_or_attack_evidence", "candidates": []}
    candidates = []
    period, phase = grid["period_seconds"], grid["phase_seconds_audio_relative"]
    for subdivisions in (1, 2, 3, 4, 6, 8):
        step = period / subdivisions
        errors = [abs((time - phase) - round((time - phase) / step) * step) for time in times]
        tolerance = min(.020, step * .10)
        fraction = sum(error <= tolerance for error in errors) / len(errors)
        chance_coverage = min(1.0, 2 * tolerance / step)
        excess = (fraction - chance_coverage) / max(1e-9, 1 - chance_coverage)
        candidates.append({"subdivisions_per_declared_or_fitted_pulse": subdivisions,
                           "subdivision_seconds": step, "within_tolerance_fraction": fraction,
                           "tolerance_ms": tolerance * 1000, "median_absolute_offset_ms": statistics.median(errors) * 1000,
                           "alignment_excess_over_uniform_phase": excess,
                           "confidence_kind": "heuristic_not_probability", "status": "candidate_not_intended_rhythm"})
    return {"status": "automatic_candidates", "event_basis": "detected_attack_candidates_not_note_transcription",
            "candidates": sorted(candidates, key=lambda c: c["alignment_excess_over_uniform_phase"], reverse=True),
            "limitations": "Denser grids, syncopation, blended clicks and detector bias can mimic subdivision support; mixed subdivisions are allowed."}


def librosa_analysis(samples) -> dict:
    try:
        os.environ.setdefault("NUMBA_NUM_THREADS", "1")
        import librosa
        import numpy as np
        from threadpoolctl import threadpool_limits
    except ImportError as exc:
        raise RuntimeError("librosa backend requested but dependencies are not installed; use --backend stdlib") from exc
    with threadpool_limits(limits=1):
        signal = np.asarray(samples, dtype=np.float32)
        mel = librosa.feature.melspectrogram(y=signal, sr=RATE, n_fft=1024, hop_length=HOP,
                                            n_mels=128, fmin=27.5)
        log_mel = librosa.power_to_db(mel, ref=np.max)
        flux = librosa.onset.onset_strength(S=log_mel, sr=RATE, hop_length=HOP, lag=1, max_size=1)
        superflux = librosa.onset.onset_strength(S=log_mel, sr=RATE, hop_length=HOP, lag=2, max_size=3)
        onsets = {}
        for name, envelope in (("spectral_flux", flux), ("superflux", superflux)):
            frames = librosa.onset.onset_detect(onset_envelope=envelope, sr=RATE, hop_length=HOP, units="frames")
            onsets[name] = {"frames": np.asarray(frames, dtype=int).tolist(),
                            "audio_relative_seconds": librosa.frames_to_time(frames, sr=RATE, hop_length=HOP).tolist()}
        tempo, beats = librosa.beat.beat_track(onset_envelope=superflux, sr=RATE, hop_length=HOP, units="time")
        feature_stride = 10
        mfcc = librosa.feature.mfcc(S=log_mel, sr=RATE, n_mfcc=13)[:, ::feature_stride]
        chroma = librosa.feature.chroma_stft(y=signal, sr=RATE, n_fft=4096, hop_length=HOP * feature_stride)
        count = min(mfcc.shape[1], chroma.shape[1])
        features = {"status": "automatic_comparative_features_not_tonic_or_note_inference",
                    "matrix_layout": "feature_by_frame", "hop_samples": HOP * feature_stride,
                    "frame_times_audio_relative_seconds": (np.arange(count) * HOP * feature_stride / RATE).tolist(),
                    "mfcc": np.round(mfcc[:, :count], 5).tolist(), "chroma": np.round(chroma[:, :count], 5).tolist(),
                    "mfcc_fft_samples": 1024, "chroma_fft_samples": 4096,
                    "limitations": "Distortion harmonics, changing articulation and click contamination can create artificial similarity; features do not prove notes or tonal center."}
    return {"version": librosa.__version__, "bpm": np.asarray(tempo).tolist(),
            "beats_audio_relative_seconds": np.asarray(beats).tolist(), "onsets": onsets, "features": features,
            "onset_parameters": {"sample_rate": RATE, "hop_samples": HOP, "n_fft": 1024, "n_mels": 128,
                                 "fmin_hz": 27.5, "spectral_flux": {"lag": 1, "max_size": 1},
                                 "superflux": {"lag": 2, "max_size": 3},
                                 "timestamp_convention": "librosa_frame_time_center_compensated", "delay_status": "uncalibrated"},
            "interpretation": "unverified_classical_analysis_independent_of_declared_tempo_and_click_grid"}


def analyze(samples, source_start: float = 0.0, bpm: float | None = None, backend: str = "stdlib") -> dict:
    hop_seconds = HOP / RATE
    rms, high = envelopes(samples)
    high_novelty = novelty(high)
    candidates = tempo_candidates(high_novelty, hop_seconds)
    selected = choose_tempo(candidates)
    period = 60 / bpm if bpm else selected["period_seconds"] if selected else None
    grid = fit_click_grid(high_novelty, period, hop_seconds) if period else None
    attempts = []
    selection = "manual_bpm_seed_then_observed_fit" if bpm else "heuristic_preference_70_to_150_bpm_when_comparable"
    fit_seed_bpm = bpm if bpm else 60 / period if period else None
    if period:
        attempts.append({"seed_bpm": fit_seed_bpm,
                         "provenance": "operator_declared_approximate" if bpm else "audio_periodicity_heuristic",
                         "status": "observed_fit" if grid else "no_stable_observed_fit"})
    if grid is None and bpm and selected:
        period = selected["period_seconds"]
        fit_seed_bpm = 60 / period
        grid = fit_click_grid(high_novelty, period, hop_seconds)
        selection = "audio_periodicity_fallback_after_declared_seed_fit_abstention"
        attempts.append({"seed_bpm": fit_seed_bpm, "provenance": "audio_periodicity_heuristic_fallback",
                         "status": "observed_fit" if grid else "no_stable_observed_fit"})
    if grid:
        grid["selection"] = selection
        grid["tempo_seed_bpm"] = bpm
        grid["tempo_seed_provenance"] = "operator_declared_approximate" if bpm else "audio_periodicity_heuristic"
        grid["observed_fit_seed_bpm"] = fit_seed_bpm
        grid["autocorrelation_score"] = selected["autocorrelation_score"] if selected else None
        if not selected or selected["autocorrelation_score"] < .4:
            grid["confidence_label"] = "limited_periodic_evidence"
    interpretation_period = grid["period_seconds"] if grid else period
    attacks = novelty(rms)
    threshold = max(statistics.median(attacks) * 4, max(attacks, default=0) * .08)
    indices = peak_indices(attacks, threshold, 6)
    events = []
    for item in grid["observed_events"] if grid else []:
        events.append({"kind": "periodic_high_frequency_candidate", **item,
                       "source_timeline_seconds": source_start + item["audio_relative_seconds"],
                       "analysis_sample_position": (item["analysis_frame"] + .5) * HOP,
                       "timestamp_convention": "frame_midpoint",
                       "confidence_label": grid["confidence_label"]})
    for index in indices:
        time = (index + .5) * hop_seconds
        beat, offset = grid_offset(time, grid) if grid else (None, None)
        events.append({"kind": "broadband_attack_candidate", "analysis_frame": index,
                       "analysis_sample_position": (index + .5) * HOP, "timestamp_convention": "frame_midpoint",
                       "audio_relative_seconds": time, "source_timeline_seconds": source_start + time,
                       "beat_index": beat, "grid_offset_ms": offset, "confidence_label": "unvalidated_attack_approximation"})
    optional = None
    if backend == "librosa":
        optional = librosa_analysis(samples)
        for name, data in optional["onsets"].items():
            for frame, time in zip(data["frames"], data["audio_relative_seconds"]):
                beat, offset = grid_offset(time, grid) if grid else (None, None)
                events.append({"kind": name + "_attack_candidate", "analysis_frame": frame,
                               "analysis_sample_position": frame * HOP,
                               "timestamp_convention": "librosa_frame_time_center_compensated",
                               "audio_relative_seconds": time, "source_timeline_seconds": source_start + time,
                               "beat_index": beat, "grid_offset_ms": offset,
                               "confidence_label": "unvalidated_spectral_attack_not_note_identity"})
    attack_times = optional["onsets"]["superflux"]["audio_relative_seconds"] if optional else [(index + .5) * hop_seconds for index in indices]
    return {"schema_version": 1, "backend": backend, "analysis": {"sample_rate": RATE, "channels": 1, "samples": len(samples),
            "duration_seconds": len(samples) / RATE, "hop_samples": HOP, "hop_seconds": hop_seconds,
            "frame_timestamp": "frame_midpoint", "frame_midpoint_offset_seconds": hop_seconds / 2,
            "event_timestamp_conventions": {"stdlib": "frame_midpoint", "librosa": "librosa_frame_time_center_compensated"},
            "onset_detector_delay_seconds": None, "onset_detector_delay_status": "uncalibrated",
            "resampling": "FFmpeg mono analysis copy; source unchanged"},
            "timeline": {"audio_stream_start_seconds": source_start, "event_time_origin": "first_decoded_audio_sample",
                         "source_axis": "audio_stream_start_plus_audio_relative_time", "decoder_priming_correction": "FFmpeg_decoder_handled_not_independently_verified"},
            "tempo_candidates": candidates, "selected_periodicity": selected, "click_grid": grid,
            "grid_fit_attempts": attempts,
            "declared_tempo": {"bpm": bpm, "provenance": "operator_statement_via_--bpm", "precision": "approximate",
                               "status": "operator_declared_not_audio_verified"} if bpm else None,
            "subdivisions": subdivision_candidates(attack_times, grid),
            "metrical_interpretations": [{"bpm": round((60 / interpretation_period) * factor, 3), "pulse_multiplier": factor,
                                          "basis": "observed_fitted_grid" if grid else "unfitted_seed_or_periodicity_candidate",
                                          "evidence": "derived_half_double_ambiguity_not_independent_detection"}
                                         for factor in (.5, 1, 2)] if interpretation_period else [],
            "meter": {"status": "unknown", "time_signature": None}, "phrases": {"status": "not_estimated"},
            "performance": {"status": "not_graded", "expected_rhythm_reference": None}, "librosa": optional,
            "instrument_context": {"source": "operator_statement", "guitar_strings": 9, "lowest_fundamental_hz": 32,
                                   "style": "downtuned_deathcore_technical_guitar", "pitch_estimation": "not_performed",
                                   "analysis_rate_role": "transient_analysis_only_not_master_or_note_classifier"},
            "limitations": ["Transient candidates may contain clicks, pick attacks, handling noise or recording artifacts.",
                            "Audio BPM is periodicity; operator-declared approximate tempo is recorded separately from fitted estimates.",
                            "Offsets measure uncalibrated recorded transients against a heuristic grid, not player errors.",
                            "Automatic segmentation and subdivision suggestions need no predeclared intent; calling notes missed/extra requires an approved expected pattern.",
                            "Sweeps, tapping and legato may contain continuous or weak attacks; onset gaps do not establish rests, skipped notes or incomplete phrases."],
            "events": sorted(events, key=lambda e: e["audio_relative_seconds"])}


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    os.replace(temporary, path)


def file_hash(source: Path) -> str:
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_timeline(source: Path, input_hash: str, metadata: dict, run_dir: Path | None) -> tuple[float, dict]:
    """Rebase only a hash-bound, unchanged-length PCM derivative from this run."""
    raw_start = metadata["audio"].get("start_time")
    decoded_start = float(raw_start) if raw_start is not None else 0.0
    if not math.isfinite(decoded_start):
        raise ValueError("Input audio start is not finite")
    lineage = {"status": "direct_input", "analyzed_input_sha256": input_hash,
               "analyzed_input_path": str(source), "decoded_file_audio_start_seconds": decoded_start}
    manifest_path = run_dir / "manifest.json" if run_dir else None
    if not manifest_path or not manifest_path.exists():
        return decoded_start, lineage
    if manifest_path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Run manifest exceeds the 2 MiB provenance bound")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        outputs = manifest["output_sha256"]
        parent = manifest["source"]
        if not isinstance(outputs, dict) or not isinstance(parent, dict):
            raise ValueError("Invalid run manifest provenance")
        matches = [name for name in ("denoised.wav", "cleaned.wav", "source.wav")
                   if outputs.get(name) == input_hash]
        if not matches:
            if source.name in ("denoised.wav", "cleaned.wav", "source.wav"):
                raise ValueError("Input derivative hash does not match run manifest; timeline not rebased")
            lineage.update(status="input_not_manifest_derivative", manifest_path=str(manifest_path),
                           timeline_rebased=False)
            return decoded_start, lineage
        parent_hash = parent["sha256"]
        if not isinstance(parent_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", parent_hash):
            raise ValueError("Invalid original source hash in run manifest")
        timeline, reference = manifest["timeline"], manifest["pcm"]
        if timeline.get("no_time_stretch") is not True:
            raise ValueError("Run manifest does not establish an unchanged time scale")
        start = float(timeline["audio_start_seconds"])
        if not math.isfinite(start):
            raise ValueError("Original media audio start is unknown or non-finite")
        audio = metadata["audio"]
        rate, channels = int(audio["sample_rate"]), int(audio["channels"])
        expected_rate, expected_channels = int(reference["sample_rate"]), int(reference["channels"])
        expected_count = int(reference["sample_count"])
        if not str(audio.get("codec_name", "")).startswith("pcm_") or rate <= 0 or expected_count <= 0:
            raise ValueError("Derivative provenance requires positive, measurable PCM metadata")
        count = Fraction(str(audio["duration_ts"])) * Fraction(audio["time_base"]) * rate
        if (rate, channels, count) != (expected_rate, expected_channels, expected_count):
            raise ValueError("Derivative PCM sample rate, channels or count differs from run manifest")
        lineage.update(status="hash_bound_run_derivative", manifest_path=str(manifest_path),
                       manifest_sha256=file_hash(manifest_path), run_id=manifest.get("run_id"),
                       matched_artifact_names=matches, original_source_sha256=parent_hash,
                       original_source_path=parent.get("path"), original_audio_start_seconds=start,
                       timeline_rebased=True,
                       sample_mapping={"status": "manifest_no_stretch_and_pcm_extent_verified",
                                       "no_time_stretch": True, "original_pcm_sample_rate": rate,
                                       "original_pcm_sample_count": expected_count, "channels": channels,
                                       "analysis_sample_rate": RATE,
                                       "original_samples_per_analysis_sample": str(Fraction(rate, RATE)),
                                       "original_samples_per_analysis_frame": str(Fraction(rate * HOP, RATE)),
                                       "analysis_frame_midpoint_original_samples": str(Fraction(rate * HOP, 2 * RATE)),
                                       "mapping": "original_audio_start + event.analysis_sample_position / analysis_sample_rate",
                                       "stdlib_frame_origin": "frame_midpoint", "librosa_frame_origin": "center_compensated_frame_time",
                                       "filter_or_detector_delay": "uncalibrated; no physical alignment guarantee"})
        return start, lineage
    except (KeyError, TypeError, json.JSONDecodeError, ZeroDivisionError) as exc:
        raise ValueError("Run manifest lacks valid hash-bound PCM timeline provenance") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    location = parser.add_mutually_exclusive_group()
    location.add_argument("--output", type=Path)
    location.add_argument("--run-dir", type=Path)
    parser.add_argument("--backend", choices=["stdlib", "librosa"], default="stdlib")
    parser.add_argument("--bpm", type=float, help="Manual tempo seed; does not establish intended rhythm")
    args = parser.parse_args()
    try:
        source = args.input.expanduser().resolve(strict=True)
        if args.bpm is not None and (not math.isfinite(args.bpm) or not 20 <= args.bpm <= 400):
            raise ValueError("Manual BPM must be between 20 and 400")
        metadata = probe(source)
        output = args.run_dir or args.output or Path("artifacts/rhythm") / source.stem
        # Refuse a destination that would overwrite an input with one of our artifact names.
        if source in {(output / "analysis.json").resolve(), (output / "events.csv").resolve()}:
            raise ValueError("Output would overwrite input")
        input_hash = file_hash(source)
        source_start, lineage = input_timeline(source, input_hash, metadata, args.run_dir)
        samples = decode(source)
        result = analyze(samples, source_start, args.bpm, args.backend)
        if file_hash(source) != input_hash:
            raise ValueError("Input changed during analysis; outputs not published")
        result["source"] = {"path": str(source), "sha256": input_hash, "probe": metadata}
        result["source_lineage"] = lineage
        result["timeline"]["provenance"] = lineage["status"]
        atomic_write(output / "analysis.json", json.dumps(result, indent=2, allow_nan=False) + "\n")
        stream = io.StringIO()
        columns = ["kind", "analysis_frame", "analysis_sample_position", "timestamp_convention", "audio_relative_seconds", "source_timeline_seconds", "beat_index", "grid_offset_ms", "confidence_label"]
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(result["events"])
        atomic_write(output / "events.csv", stream.getvalue())
        print(json.dumps({"analysis_json": str(output / "analysis.json"), "events_csv": str(output / "events.csv"),
                          "declared_tempo": result["declared_tempo"], "subdivisions": result["subdivisions"],
                          "grid_fit_attempts": result["grid_fit_attempts"], "metrical_interpretations": result["metrical_interpretations"],
                          "librosa_version": result["librosa"]["version"] if result["librosa"] else None,
                          "tempo_candidates": result["tempo_candidates"], "click_grid": {k: v for k, v in (result["click_grid"] or {}).items() if k != "observed_events"},
                          "event_count": len(result["events"])}))
        return 0
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"rhythm: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
