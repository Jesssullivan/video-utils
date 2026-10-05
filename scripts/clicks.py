#!/usr/bin/env python3
"""Offline click candidates and opt-in, overlap-guarded attenuation experiments."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

ANALYSIS_RATE = 16000
PROTECTED_HZ = 1200
MAX_SECONDS = 600
MAX_PCM_SAMPLES = 16_000_000
MAX_EVENTS = 5000

_spec = importlib.util.spec_from_file_location("click_rhythm", Path(__file__).with_name("rhythm.py"))
rhythm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rhythm)


def dependencies():
    try:
        import numpy as np
        import scipy
        from scipy import signal
        from scipy.io import wavfile
        from threadpoolctl import threadpool_limits
    except ImportError as exc:
        raise RuntimeError("Click experiments require the locked analysis environment; run just analysis-setup explicitly") from exc
    return np, scipy, signal, wavfile, threadpool_limits


def decode_native(source: Path, metadata: dict):
    np, _, _, _, _ = dependencies()
    audio = metadata["audio"]
    rate, channels = int(audio["sample_rate"]), int(audio["channels"])
    duration = float(audio.get("duration", metadata.get("format", {}).get("duration", 0)))
    if not 8000 <= rate <= 192000 or not 1 <= channels <= 2 or not 0 < duration <= MAX_SECONDS:
        raise ValueError("Click input needs known duration <=600 s, 8–192 kHz rate and one or two channels")
    if duration * rate * channels > MAX_PCM_SAMPLES:
        raise ValueError("Input exceeds the 16 million interleaved PCM sample bound")
    raw = rhythm.run([os.environ.get("FFMPEG", "ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin",
                      "-threads", "1", "-i", str(source), "-map", "0:a:0", "-vn", "-t", str(min(MAX_SECONDS, MAX_PCM_SAMPLES / (rate * channels))),
                      "-ac", str(channels), "-ar", str(rate), "-filter_threads", "1", "-threads", "1",
                      "-f", "f32le", "pipe:1"], timeout=180)
    data = np.frombuffer(raw, dtype="<f4")
    if data.size > MAX_PCM_SAMPLES or data.size % channels or not data.size or not np.all(np.isfinite(data)):
        raise ValueError("Decoded PCM is empty, non-finite or exceeds its sample bound")
    if abs(data.size / channels / rate - duration) > .05 + 1024 / rate:
        raise ValueError("Decoded extent differs materially from declared audio duration; truncated input not analyzed")
    return data.reshape(-1, channels), rate


def validate_controls(template_window, attenuate, template_click_only, strength, bpm):
    if not isinstance(strength, (int, float)) or not math.isfinite(strength) or not 0 <= strength <= .5:
        raise ValueError("Strength must be between 0 and 0.5")
    if bpm is not None and (not math.isfinite(bpm) or not 20 <= bpm <= 400):
        raise ValueError("BPM must be between 20 and 400")
    if template_window is not None:
        start, end = template_window
        if (not all(math.isfinite(value) for value in template_window) or start < 0
                or not .005 <= end - start <= .120 + 1e-10):
            raise ValueError("Template interval must be nonnegative and between 5 and 120 ms long")
    if attenuate and (template_window is None or not template_click_only):
        raise ValueError("Attenuation needs a supplied template and an explicit click-only template declaration")


def protected_estimate(estimate, rate: int):
    """Zero low-frequency DFT bins in the subtraction component, not the master."""
    np, _, _, _, _ = dependencies()
    spectrum = np.fft.rfft(estimate, axis=0)
    spectrum[np.fft.rfftfreq(estimate.shape[0], 1 / rate) < PROTECTED_HZ, :] = 0
    return np.fft.irfft(spectrum, n=estimate.shape[0], axis=0).astype(np.float32)


def measure_protected_delta(original, processed, rate):
    np, _, _, _, _ = dependencies()
    before, after = np.fft.rfft(original, axis=0), np.fft.rfft(processed, axis=0)
    frequencies = np.fft.rfftfreq(original.shape[0], 1 / rate)
    mask = (frequencies >= 28) & (frequencies <= 80)
    scale = max(float(np.max(np.abs(before[mask]))) if np.any(mask) else 0, 1e-12)
    delta = float(np.max(np.abs(after[mask] - before[mask]))) / scale if np.any(mask) else None
    index = int(np.argmin(np.abs(frequencies - 32)))
    denominator = max(float(np.linalg.norm(before[index])), 1e-12)
    return {"28_80_hz_max_complex_bin_relative_delta": delta,
            "nearest_32_hz_bin": float(frequencies[index]),
            "32_hz_complex_bin_relative_delta": float(np.linalg.norm(after[index] - before[index])) / denominator,
            "interpretation": "finite-recording_DFT_measurement_not_listening_acceptance"}


def experiment(pcm, rate: int, *, template_window=None, attenuate=False,
               template_click_only=False, strength=.5, bpm=None, source_start=0.0):
    np, scipy, signal, _, threadpool_limits = dependencies()
    validate_controls(template_window, attenuate, template_click_only, strength, bpm)
    data = np.asarray(pcm, dtype=np.float32)
    if data.ndim == 1:
        data = data[:, None]
    if (data.ndim != 2 or not 1 <= data.shape[1] <= 2 or not 8000 <= rate <= 192000
            or data.size > MAX_PCM_SAMPLES or not len(data) or len(data) / rate > MAX_SECONDS
            or not np.all(np.isfinite(data))):
        raise ValueError("PCM violates the finite, native-rate/channel duration/sample bounds")
    if not math.isfinite(source_start):
        raise ValueError("Source origin must be finite")
    result = {"schema_version": 1, "status": "candidate_analysis_only", "identity_status": "unverified",
              "confidence_kind": "heuristic_not_probability", "listening_acceptance": "not_performed",
              "pcm": {"sample_rate": rate, "channels": data.shape[1], "sample_count": len(data),
                      "duration_seconds": len(data) / rate},
              "settings": {"analysis_rate": ANALYSIS_RATE, "declared_bpm": bpm, "attenuation_requested": attenuate,
                           "strength": strength, "protected_subtraction_below_hz": PROTECTED_HZ,
                           "template_window_audio_relative_seconds": list(template_window) if template_window else None,
                           "template_click_only_declared": bool(template_click_only),
                           "candidate_correlation_threshold": .82, "native_fit_correlation_threshold": .90,
                           "maximum_residual_energy_fraction": .08, "gain_bounds": [.1, 2.0]},
              "versions": {"numpy": np.__version__, "scipy": scipy.__version__},
              "timeline": {"audio_stream_start_seconds": source_start, "event_timestamp": "aligned_template_peak_native_sample"},
              "events": [],
              "limitations": ["A click-like waveform can be a guitar attack; identity remains unverified.",
                              "A click-only template declaration is operator metadata, not machine proof.",
                              "AGC, AAC, accents and room reflections can invalidate a fixed click template.",
                              "Overlap abstention can leave many audible clicks; silence is not an expected rhythm reference.",
                              "Protecting low DFT bins leaves low-frequency click content and can cause ringing.",
                              "The estimated component is not a recovered original metronome stem."]}
    with threadpool_limits(limits=1):
        divisor = math.gcd(rate, ANALYSIS_RATE)
        mono = data.mean(axis=1)
        analysis = signal.resample_poly(mono, ANALYSIS_RATE // divisor, rate // divisor)
        if template_window is None:
            measured = rhythm.analyze(analysis, source_start, bpm=bpm)
            for event in measured["events"]:
                if event["kind"] != "periodic_high_frequency_candidate":
                    continue
                position = round(event["audio_relative_seconds"] * rate)
                result["events"].append({"native_sample": position, "audio_relative_seconds": position / rate,
                                         "source_timeline_seconds": source_start + position / rate,
                                         "confidence_label": event["confidence_label"], "decision": "analyze_only",
                                         "reason": "no_waveform_template_identity_unverified"})
            result.update(tempo_candidates=measured["tempo_candidates"], declared_tempo=measured["declared_tempo"],
                          grid_fit_attempts=measured["grid_fit_attempts"], click_grid=measured["click_grid"])
            result["timeline"]["event_timestamp"] = "high_frequency_envelope_frame_midpoint_mapped_to_native_sample"
            result["summary"] = {"candidate_count": len(result["events"]), "accepted_fit_count": 0, "attenuated_count": 0,
                                 "abstained_count": 0}
            return result, None, None
        start, end = [round(value * rate) for value in template_window]
        if end > len(data) or end <= start:
            raise ValueError("Template interval extends beyond decoded audio")
        template = data[start:end].copy()
        template -= template.mean(axis=0)
        template_energy = float(np.sum(template.astype(np.float64) ** 2))
        if template_energy < 1e-10:
            raise ValueError("Template has insufficient waveform energy")
        low_spectrum = np.fft.rfft(template, axis=0)
        low_mask = np.fft.rfftfreq(len(template), 1 / rate) < PROTECTED_HZ
        low_fraction = float(np.sum(np.abs(low_spectrum[low_mask]) ** 2) / max(np.sum(np.abs(low_spectrum) ** 2), 1e-20))
        result["template"] = {"native_start_sample": start, "native_end_sample": end,
                              "low_frequency_energy_fraction": low_fraction,
                              "identity": "operator_declared_click_only" if template_click_only else "unverified_supplied_waveform"}
        resampled_template = signal.resample_poly(template.mean(axis=1), ANALYSIS_RATE // divisor, rate // divisor)
        highpass = signal.butter(2, PROTECTED_HZ, "highpass", fs=ANALYSIS_RATE, output="sos")
        high, model = signal.sosfilt(highpass, analysis), signal.sosfilt(highpass, resampled_template)
        correlation = signal.correlate(high, model, mode="valid", method="fft")
        cumulative = np.concatenate(([0.0], np.cumsum(high * high, dtype=np.float64)))
        moving_energy = cumulative[len(model):] - cumulative[:-len(model)]
        normalized = np.clip(correlation / np.sqrt(np.maximum(moving_energy * np.sum(model * model), 1e-20)), -1, 1)
        period = 60 / bpm if bpm else None
        distance_seconds = max(.12, min(.3, period * .4)) if period else .12
        # Correlation magnitude locates the complete transient. Maximizing normalized
        # similarity alone can choose arbitrarily faint tails of a decaying sinusoid.
        peaks, _ = signal.find_peaks(correlation, height=float(np.sum(model * model)) * .1,
                                     distance=max(1, round(distance_seconds * ANALYSIS_RATE)))
        peaks = peaks[normalized[peaks] >= .82]
        if len(peaks) > MAX_EVENTS:
            raise ValueError("Matched candidates exceed the 5000-event bound")
        positions = []
        radius = max(3, math.ceil(rate / ANALYSIS_RATE) * 2)
        for peak in peaks:
            guessed = round(int(peak) * rate / ANALYSIS_RATE)
            best = None
            for position in range(max(0, guessed - radius), min(len(data) - len(template), guessed + radius) + 1):
                window = data[position:position + len(template)]
                centered = window - window.mean(axis=0)
                gain = np.sum(centered * template, axis=0) / np.maximum(np.sum(template * template, axis=0), 1e-20)
                residual = centered - template * gain
                energy = float(np.sum(centered.astype(np.float64) ** 2))
                residual_fraction = float(np.sum(residual.astype(np.float64) ** 2)) / max(energy, 1e-20)
                agreement = max(-1.0, min(1.0, float(np.sum(centered * template)) / math.sqrt(max(energy * template_energy, 1e-20))))
                candidate = (agreement, position, gain, residual_fraction, float(np.max(np.abs(window))))
                if best is None or agreement > best[0]:
                    best = candidate
            if best is not None:
                positions.append((int(peak), best))
        times = [best[1] / rate for _, best in positions]
        declared_period = period
        observed_fit = False
        if period is not None and len(times) >= 3:
            gaps = [right - left for left, right in zip(times, times[1:]) if right > left]
            fitted = float(np.median([gap / max(1, round(gap / period)) for gap in gaps]))
            if abs(fitted - period) <= period * .03:
                period, observed_fit = fitted, True
        if period is None and len(times) >= 3:
            gaps = [right - left for left, right in zip(times, times[1:]) if .15 <= right - left <= 1.5]
            period = float(np.median(gaps)) if gaps else None
        phase = times[0] if times else 0
        support = [abs(time - phase - round((time - phase) / period) * period) <= .025 for time in times] if period else [False] * len(times)
        recurring_count = sum(support)
        raw_estimate = np.zeros_like(data)
        peak_in_template = int(np.argmax(np.abs(template.mean(axis=1))))
        for (peak, (agreement, position, gain, residual_fraction, maximum)), supported in zip(positions, support):
            reasons = []
            if low_fraction > .20:
                reasons.append("template_has_substantial_low_frequency_content")
            if agreement < .90:
                reasons.append("native_waveform_mismatch")
            if residual_fraction > .08:
                reasons.append("overlap_or_non_template_energy")
            if maximum >= .98:
                reasons.append("clipped_or_near_clipped_window")
            if np.any(gain < .1) or np.any(gain > 2.0):
                reasons.append("fitted_gain_out_of_bounds")
            if not supported or recurring_count < 3:
                reasons.append("insufficient_recurring_template_support")
            accepted = not reasons
            decision = "attenuated" if accepted and attenuate and strength > 0 else "analyze_only" if accepted else "abstained"
            if decision == "attenuated":
                raw_estimate[position:position + len(template)] += template * gain * strength
            native_sample = position + peak_in_template
            result["events"].append({"native_sample": native_sample, "aligned_window_start_sample": position,
                                     "audio_relative_seconds": native_sample / rate,
                                     "source_timeline_seconds": source_start + native_sample / rate,
                                     "analysis_template_correlation": float(normalized[peak]),
                                     "native_template_correlation": agreement, "fitted_gain_per_channel": gain.tolist(),
                                     "residual_energy_fraction": residual_fraction,
                                     "recurring_support": bool(supported), "confidence_label": "template_fit_candidate_identity_unverified",
                                     "decision": decision, "reason": ";".join(reasons) if reasons else "conservative_template_fit_accepted"})
        result["periodicity"] = {"period_seconds": period, "recurring_candidate_count": recurring_count,
                                 "basis": "operator_bpm_seed" if bpm else "median_candidate_spacing",
                                 "declared_period_seconds": declared_period, "observed_seed_family_fit": observed_fit,
                                 "identity_status": "unverified"}
        removed = protected_estimate(raw_estimate, rate) if attenuate else None
        processed = (data - removed).astype(np.float32) if attenuate else None
        result["summary"] = {"candidate_count": len(result["events"]),
                             "accepted_fit_count": sum(event["decision"] != "abstained" for event in result["events"]),
                             "attenuated_count": sum(event["decision"] == "attenuated" for event in result["events"]),
                             "abstained_count": sum(event["decision"] == "abstained" for event in result["events"])}
        if attenuate:
            result["status"] = "experimental_variant_rendered_unreviewed"
            result["frequency_preservation"] = measure_protected_delta(data, processed, rate)
        return result, processed, removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--bpm", type=float)
    parser.add_argument("--template-start", type=float)
    parser.add_argument("--template-end", type=float)
    parser.add_argument("--template-click-only", action="store_true")
    parser.add_argument("--attenuate", action="store_true")
    parser.add_argument("--strength", type=float, default=.5)
    args = parser.parse_args()
    staging = None
    try:
        if (args.template_start is None) != (args.template_end is None):
            raise ValueError("Both --template-start and --template-end are required together")
        window = (args.template_start, args.template_end) if args.template_start is not None else None
        validate_controls(window, args.attenuate, args.template_click_only, args.strength, args.bpm)
        source = args.input.expanduser().resolve(strict=True)
        metadata = rhythm.probe(source)
        source_hash = rhythm.file_hash(source)
        origin, lineage = rhythm.input_timeline(source, source_hash, metadata, args.run_dir)
        pcm, rate = decode_native(source, metadata)
        result, processed, removed = experiment(pcm, rate, template_window=window, attenuate=args.attenuate,
                                               template_click_only=args.template_click_only, strength=args.strength,
                                               bpm=args.bpm, source_start=origin)
        if rhythm.file_hash(source) != source_hash:
            raise ValueError("Input changed during click analysis; outputs not published")
        result.update(source={"path": str(source), "sha256": source_hash, "probe": metadata}, source_lineage=lineage)
        directory = args.run_dir.resolve() / "clicks"
        directory.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
        destination = directory / run_id
        staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=directory))
        outputs = {"analysis": "clicks.json", "events": "click-events.csv"}
        if processed is not None:
            _, _, _, wavfile, _ = dependencies()
            for name, data in (("click-attenuated.wav", processed), ("click-estimate.wav", removed)):
                wavfile.write(staging / name, rate, data)
                verified_rate, verified = wavfile.read(staging / name)
                shape = verified.shape if verified.ndim == 2 else (len(verified), 1)
                if verified_rate != rate or shape != pcm.shape or not (verified == data.squeeze() if data.shape[1] == 1 else verified == data).all():
                    raise ValueError("Rendered click experiment PCM differs in extent or samples")
            outputs.update(variant="click-attenuated.wav", estimate="click-estimate.wav")
        result.update(run_id=run_id, artifact_dir=str(destination), outputs=outputs,
                      output_sha256={path.name: rhythm.file_hash(path) for path in staging.glob("*.wav")})
        stream = io.StringIO()
        fields = ["native_sample", "audio_relative_seconds", "source_timeline_seconds", "analysis_template_correlation",
                  "native_template_correlation", "residual_energy_fraction", "confidence_label", "decision", "reason"]
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(result["events"])
        (staging / "click-events.csv").write_text(stream.getvalue(), encoding="utf-8")
        (staging / "clicks.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        staging.rename(destination)
        staging = None
        print(json.dumps({"artifact_dir": str(destination), "clicks_json": str(destination / "clicks.json"),
                          "events_csv": str(destination / "click-events.csv"), "status": result["status"],
                          "summary": result["summary"], "outputs": outputs, "identity_status": "unverified"}))
        return 0
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"clicks: {exc}", file=sys.stderr)
        return 1
    finally:
        if staging is not None:
            shutil.rmtree(staging)


if __name__ == "__main__":
    raise SystemExit(main())
