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


def high_frequency_peak_indices(values: list[float]) -> list[int]:
    """Periodic high-frequency candidate peaks; shared by grid, drift and delay calibration."""
    return peak_indices(values, max(statistics.median(values) * 3, max(values) * .04), 4)


def broadband_peak_indices(attacks: list[float]) -> list[int]:
    """Broadband RMS-novelty attack peaks; shared by analyze() and delay calibration."""
    threshold = max(statistics.median(attacks) * 4, max(attacks, default=0) * .08)
    return peak_indices(attacks, threshold, 6)


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
    event_indices = high_frequency_peak_indices(values)
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


DRIFT_RATE_BOUND = .05
DRIFT_MIN_EVENTS = 6
DRIFT_MAX_RMS_SECONDS = .015
DRIFT_TRACK_TOLERANCE = .12
DRIFT_MAX_MISSES = 3
DRIFT_MIN_DIVIDED_PERIOD = .25
DRIFT_SELECT_COVERAGE = .7
DRIFT_OUTLIER_FLOOR_SECONDS = .012
DRIFT_ANCHORS = 24
DRIFT_TRACK_SIGMA_FRACTION = .03
DRIFT_TRACK_MIN_SUPPORT = .10
DRIFT_DIVISOR_RMS_RATIO = 1.25
DRIFT_DIVISOR_RMS_SLACK_SECONDS = .0015
DRIFT_ESTIMATE_FIELDS = ("period_change_per_second", "drift_ppm", "drift_ppm_standard_error",
                         "reference_time_seconds_audio_relative", "period_at_reference_seconds",
                         "period_at_first_event_seconds", "period_at_last_event_seconds",
                         "total_period_change_fraction", "residual_ms_rms", "constant_period_residual_ms_rms",
                         "model_parameters")


def _quantile(ordered: list[float], q: float) -> float:
    """Inclusive linear-interpolation quantile of an already sorted list."""
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def drift_basis(rate: float, beat: float) -> tuple[float, float]:
    """(A_b, B_b) with t_b = t0*A_b + P0*B_b for IOI(t) = P0 + r*t; B_b -> b as r -> 0."""
    if rate == 0:
        return 1.0, float(beat)
    growth = beat * math.log1p(rate)
    return math.exp(growth), math.expm1(growth) / rate


def drift_click_time(parameters: dict, beat: float) -> float:
    """Predicted click time (audio-relative seconds) for a beat index of a fitted linear_period model."""
    scale, increment = drift_basis(parameters["period_change_per_second"], beat)
    return parameters["anchor_click_seconds_audio_relative"] * scale + parameters["ioi_intercept_seconds_at_audio_time_zero"] * increment


def drift_beat_position(parameters: dict, time: float) -> float | None:
    """Continuous beat coordinate of an audio-relative time under the fitted model (inverse of drift_click_time)."""
    rate = parameters["period_change_per_second"]
    anchor = parameters["anchor_click_seconds_audio_relative"]
    origin_period = parameters["ioi_intercept_seconds_at_audio_time_zero"] + rate * anchor
    if origin_period <= 0:
        return None
    if rate == 0:
        return (time - anchor) / origin_period
    argument = 1 + rate * (time - anchor) / origin_period
    if argument <= 0:
        return None
    return math.log(argument) / math.log1p(rate)


def _drift_solve(rate: float, beats: list[int], times: list[float]):
    """Closed-form least squares for (t0, P0) at a fixed period-change rate."""
    saa = sab = sbb = sat = sbt = 0.0
    basis = []
    for beat, time in zip(beats, times):
        a, b = drift_basis(rate, beat)
        basis.append((a, b))
        saa += a * a
        sab += a * b
        sbb += b * b
        sat += a * time
        sbt += b * time
    determinant = saa * sbb - sab * sab
    if not math.isfinite(determinant) or determinant <= 1e-12 * max(1.0, saa * sbb):
        return None
    anchor = (sat * sbb - sbt * sab) / determinant
    intercept = (saa * sbt - sab * sat) / determinant
    residuals = [time - (anchor * a + intercept * b) for (a, b), time in zip(basis, times)]
    return anchor, intercept, sum(value * value for value in residuals), residuals


def _drift_fit(beats: list[int], times: list[float]):
    """Bounded 1-D search over r with profiled (t0, P0); returns (r, t0, P0, sse, residuals)."""
    span = max(abs(beat) for beat in beats) or 1
    limit = min(DRIFT_RATE_BOUND, math.expm1(50 / span))
    grid = [-limit + 2 * limit * index / 400 for index in range(401)]
    evaluated = []
    for rate in grid:
        solved = _drift_solve(rate, beats, times)
        evaluated.append(solved[2] if solved and math.isfinite(solved[2]) else math.inf)
    best = min(range(len(grid)), key=lambda index: (evaluated[index], abs(grid[index])))
    if not math.isfinite(evaluated[best]):
        return None
    low, high = grid[max(0, best - 1)], grid[min(len(grid) - 1, best + 1)]

    def cost(rate):
        solved = _drift_solve(rate, beats, times)
        return solved[2] if solved and math.isfinite(solved[2]) else math.inf

    ratio = (math.sqrt(5) - 1) / 2
    left, right = high - ratio * (high - low), low + ratio * (high - low)
    cost_left, cost_right = cost(left), cost(right)
    for _ in range(120):
        if high - low <= 1e-14:
            break
        if cost_left <= cost_right:
            high, right, cost_right = right, left, cost_left
            left = high - ratio * (high - low)
            cost_left = cost(left)
        else:
            low, left, cost_left = left, right, cost_right
            right = low + ratio * (high - low)
            cost_right = cost(right)
    candidates = [(evaluated[best], grid[best]), (cost_left, left), (cost_right, right), (cost(0.0), 0.0)]
    rate = min(candidates, key=lambda item: (item[0], abs(item[1])))[1]
    solved = _drift_solve(rate, beats, times)
    if solved is None:
        return None
    return (rate, *solved)


def _constant_fit_rms(beats: list[int], times: list[float]) -> float | None:
    mean_b, mean_t = statistics.mean(beats), statistics.mean(times)
    variance = sum((beat - mean_b) ** 2 for beat in beats)
    if variance == 0:
        return None
    slope = sum((beat - mean_b) * (time - mean_t) for beat, time in zip(beats, times)) / variance
    residuals = [time - (mean_t + slope * (beat - mean_b)) for beat, time in zip(beats, times)]
    return math.sqrt(sum(value * value for value in residuals) / len(residuals))


def _drift_rate_standard_error(rate, anchor, intercept, beats, sse):
    """Linearized SE of r from the 3-parameter Jacobian; heuristic under quantized detections."""
    count = len(beats)
    if count <= 3:
        return None
    step = max(1e-9, abs(rate) * 1e-4)
    rows = []
    for beat in beats:
        a, b = drift_basis(rate, beat)
        up = drift_basis(rate + step, beat)
        down = drift_basis(rate - step, beat)
        derivative = (anchor * (up[0] - down[0]) + intercept * (up[1] - down[1])) / (2 * step)
        rows.append((a, b, derivative))
    matrix = [[sum(row[i] * row[j] for row in rows) for j in range(3)] for i in range(3)]
    (a, b, c), (d, e, f), (g, h, k) = matrix
    determinant = a * (e * k - f * h) - b * (d * k - f * g) + c * (d * h - e * g)
    if not math.isfinite(determinant) or abs(determinant) < 1e-300:
        return None
    inverse_rr = (a * e - b * d) / determinant
    variance = sse / (count - 3) * inverse_rr
    return math.sqrt(variance) if variance >= 0 and math.isfinite(variance) else None


def _local_period(recent: list[tuple[int, float]], seed: float) -> float:
    window = recent[-8:]
    beats = [beat for beat, _ in window]
    if len(window) < 3 or max(beats) - min(beats) < 2:
        return seed
    mean_b = statistics.mean(beats)
    mean_t = statistics.mean(time for _, time in window)
    variance = sum((beat - mean_b) ** 2 for beat in beats)
    slope = sum((beat - mean_b) * (time - mean_t) for beat, time in window) / variance
    return slope if .7 * seed <= slope <= 1.3 * seed else seed


def _track_clicks(times: list[float], strengths: list[float], period: float, anchor: int,
                  end_time: float) -> dict[int, float]:
    """Seeded tracker over peaks within ±12 % of the local period.

    A candidate's support is strength * exp(-0.5*(dt/(0.03*local))^2), so a nearby click wins over
    dense weak noise peaks and over a stronger but displaced attack. A beat is a miss when the best
    support is below 10 % of the median accepted strength; three consecutive misses stop a direction.
    """
    import bisect
    pairs = {0: times[anchor]}
    used = {anchor}
    accepted_strengths = [strengths[anchor]]
    for direction in (1, -1):
        if direction == 1:
            recent = [(0, times[anchor])]
        else:
            recent = sorted(pairs.items())[:8][::-1]
        beat, misses = 0, 0
        while misses < DRIFT_MAX_MISSES:
            beat += direction
            local = _local_period(recent, period)
            last_beat, last_time = recent[-1]
            predicted = last_time + local * (beat - last_beat)
            window = DRIFT_TRACK_TOLERANCE * local
            if predicted < -window or predicted > end_time + window:
                break
            low = bisect.bisect_left(times, predicted - window)
            high = bisect.bisect_right(times, predicted + window)
            sigma = DRIFT_TRACK_SIGMA_FRACTION * local
            best, support = None, 0.0
            for index in range(low, high):
                if index in used:
                    continue
                value = strengths[index] * math.exp(-.5 * ((times[index] - predicted) / sigma) ** 2)
                if value > support:
                    best, support = index, value
            if best is None or support < DRIFT_TRACK_MIN_SUPPORT * statistics.median(accepted_strengths):
                misses += 1
                continue
            misses = 0
            used.add(best)
            pairs[beat] = times[best]
            accepted_strengths.append(strengths[best])
            recent.append((beat, times[best]))
    return pairs


def _reject_and_fit(pairs: dict[int, float]):
    """Fit, then up to three outlier passes with threshold max(12 ms, 3*1.4826*MAD)."""
    retained = sorted(pairs.items())
    fit = None
    for attempt in range(4):
        if len(retained) < DRIFT_MIN_EVENTS:
            return retained, None
        origin = retained[0][0]
        beats = [beat - origin for beat, _ in retained]
        times = [time for _, time in retained]
        fit = _drift_fit(beats, times)
        if fit is None or attempt == 3:
            break
        residuals = fit[4]
        center = statistics.median(residuals)
        spread = statistics.median(abs(value - center) for value in residuals)
        threshold = max(DRIFT_OUTLIER_FLOOR_SECONDS, 3 * 1.4826 * spread)
        kept = [pair for pair, value in zip(retained, residuals) if abs(value) <= threshold]
        if len(kept) == len(retained):
            break
        retained = kept
    if len(retained) < DRIFT_MIN_EVENTS:
        return retained, None
    return retained, fit


def _empty_drift(status: str, **diagnostics) -> dict:
    result = {"model": "linear_period", "status": status,
              "confidence_label": "not_estimated", "confidence_kind": "heuristic_not_probability",
              "identity": "periodic_high_frequency_transients_not_verified_metronome",
              "click_identity": "unverified",
              "interpretation": ("Linear inter-click-interval change IOI(t)=P0+r*t fitted to detected periodic high-frequency "
                                 "transients. The fit does not separate mechanical-metronome wind-down, device clock drift "
                                 "or detector bias; it is not a tempo, meter or performance claim."),
              "drift_ppm_units": "ppm_of_reference_period_per_second",
              "candidate_event_count": 0, "retained_event_count": 0, "rejected_event_count": 0,
              "beat_span": None, "coverage": None, "pulse_divisor": None, "seed_period_seconds": None,
              "seed_provenance": None, "high_frequency_peak_count": 0, "divisor_attempts": [],
              "tracked_events": []}
    result.update({field: None for field in DRIFT_ESTIMATE_FIELDS})
    result.update(diagnostics)
    return result


def fit_click_drift(values: list[float], seed_period: float | None, hop_seconds: float,
                    seed_provenance: str | None = None, anchor_hint: float | None = None) -> dict:
    """Additive linear_period drift model of the periodic high-frequency transient train."""
    if not seed_period or not math.isfinite(seed_period) or seed_period <= 0:
        return _empty_drift("no_periodic_seed", seed_provenance=seed_provenance)
    if not values or max(values, default=0) < 1e-7:
        return _empty_drift("no_periodic_seed", seed_period_seconds=seed_period, seed_provenance=seed_provenance)
    indices = high_frequency_peak_indices(values)
    times = [(index + .5) * hop_seconds for index in indices]
    strengths = [values[index] for index in indices]
    end_time = len(values) * hop_seconds
    base = {"seed_period_seconds": seed_period, "seed_provenance": seed_provenance, "high_frequency_peak_count": len(times)}
    if len(times) < DRIFT_MIN_EVENTS:
        return _empty_drift("insufficient_events", candidate_event_count=len(times),
                            retained_event_count=len(times), **base)
    anchors = sorted(range(len(times)), key=lambda index: (-strengths[index], index))[:DRIFT_ANCHORS]
    if anchor_hint is not None:
        import bisect
        position = min(max(bisect.bisect_left(times, anchor_hint), 0), len(times) - 1)
        nearest = min((index for index in (position - 1, position) if 0 <= index < len(times)),
                      key=lambda index: abs(times[index] - anchor_hint))
        if nearest not in anchors:
            anchors.append(nearest)
    attempts = []
    for divisor in (1, 2, 3):
        period = seed_period / divisor
        if divisor > 1 and period < DRIFT_MIN_DIVIDED_PERIOD:
            continue
        best = None
        by_time = dict(zip(times, strengths))
        for anchor in anchors:
            pairs = _track_clicks(times, strengths, period, anchor, end_time)
            key = (round(sum(by_time[time] for time in pairs.values()), 12), len(pairs), -anchor)
            if best is None or key > best[0]:
                best = (key, pairs)
        pairs = best[1]
        retained, fit = _reject_and_fit(pairs)
        span = (retained[-1][0] - retained[0][0]) if retained else 0
        rms = math.sqrt(fit[3] / len(retained)) if fit else None
        attempts.append({"pulse_divisor": divisor, "period_seconds": period, "pairs": pairs, "retained": retained,
                         "fit": fit, "rms": rms, "coverage": len(retained) / (span + 1) if retained else 0.0,
                         "tracked_coverage": len(pairs) / (max(pairs) - min(pairs) + 1)})
    reference = attempts[0]
    chosen = reference
    for attempt in sorted(attempts, key=lambda item: -item["pulse_divisor"]):
        if attempt["fit"] is None or attempt["coverage"] < DRIFT_SELECT_COVERAGE:
            continue
        if attempt["pulse_divisor"] > 1 and reference["rms"] is not None and reference["coverage"] >= DRIFT_SELECT_COVERAGE:
            bound = max(DRIFT_DIVISOR_RMS_RATIO * reference["rms"], reference["rms"] + DRIFT_DIVISOR_RMS_SLACK_SECONDS)
            if attempt["rms"] > bound:
                continue
        chosen = attempt
        break
    divisor_attempts = [{"pulse_divisor": item["pulse_divisor"], "period_seconds": item["period_seconds"],
                         "tracked_event_count": len(item["pairs"]), "retained_event_count": len(item["retained"]),
                         "tracked_coverage": item["tracked_coverage"], "retained_coverage": item["coverage"],
                         "residual_ms_rms": item["rms"] * 1000 if item["rms"] is not None else None,
                         "selected": item is chosen} for item in attempts]
    pairs, retained, fit = chosen["pairs"], chosen["retained"], chosen["fit"]
    retained_beats = {beat for beat, _ in retained}
    origin = retained[0][0] if retained else 0
    tracked = [{"beat_index": beat - origin, "audio_relative_seconds": time, "retained": beat in retained_beats}
               for beat, time in sorted(pairs.items())]
    span = (retained[-1][0] - retained[0][0]) if retained else None
    diagnostics = dict(base, candidate_event_count=len(pairs), retained_event_count=len(retained),
                       rejected_event_count=len(pairs) - len(retained), beat_span=span,
                       coverage=chosen["coverage"] if retained else None, pulse_divisor=chosen["pulse_divisor"],
                       divisor_attempts=divisor_attempts, tracked_events=tracked,
                       selection_rule=("fastest divisor in {1,2,3} with retained coverage >= 0.7, divided period >= 0.25 s, "
                                       "and rms <= max(1.25 x, +1.5 ms) of the seed-level fit when that fit qualifies"))
    if fit is None or len(retained) < DRIFT_MIN_EVENTS:
        return _empty_drift("insufficient_events", **diagnostics)
    rate, anchor, intercept, sse, residuals = fit
    rms = math.sqrt(sse / len(retained))
    for row, value in zip((row for row in tracked if row["retained"]), residuals):
        row["residual_ms"] = value * 1000
    if rms > DRIFT_MAX_RMS_SECONDS:
        return _empty_drift("fit_residual_exceeds_bound", attempted_fit_residual_ms_rms=rms * 1000, **diagnostics)
    beats = [beat - origin for beat, _ in retained]
    first_time, last_time = retained[0][1], retained[-1][1]
    reference_time = (first_time + last_time) / 2
    reference_period = intercept + rate * reference_time
    if reference_period <= 0 or intercept + rate * first_time <= 0 or intercept + rate * last_time <= 0:
        return _empty_drift("fit_residual_exceeds_bound", attempted_fit_residual_ms_rms=rms * 1000,
                            nonphysical_period=True, **diagnostics)
    standard_error = _drift_rate_standard_error(rate, anchor, intercept, beats, sse)
    ppm = 1e6 * rate / reference_period
    ppm_error = 1e6 * standard_error / reference_period if standard_error is not None else None
    constant_rms = _constant_fit_rms(beats, [time for _, time in retained])
    if ppm_error is not None and abs(ppm) <= 3 * ppm_error:
        label = "no_material_drift_evidence"
    elif (ppm_error is not None and chosen["coverage"] >= DRIFT_SELECT_COVERAGE and len(retained) >= 12
          and rms <= .010):
        label = "strong_drift_evidence"
    else:
        label = "limited_drift_evidence"
    period_first, period_last = intercept + rate * first_time, intercept + rate * last_time
    result = _empty_drift("fitted", **diagnostics)
    result.update(period_change_per_second=rate, drift_ppm=ppm, drift_ppm_standard_error=ppm_error,
                  reference_time_seconds_audio_relative=reference_time, period_at_reference_seconds=reference_period,
                  period_at_first_event_seconds=period_first, period_at_last_event_seconds=period_last,
                  total_period_change_fraction=(period_last - period_first) / period_first,
                  residual_ms_rms=rms * 1000,
                  constant_period_residual_ms_rms=constant_rms * 1000 if constant_rms is not None else None,
                  model_parameters={"anchor_click_seconds_audio_relative": anchor,
                                    "ioi_intercept_seconds_at_audio_time_zero": intercept,
                                    "period_change_per_second": rate,
                                    "beat_index_origin": "first_retained_event",
                                    "retained_beat_index_range": [0, beats[-1]],
                                    "position_formula": "t_b = t0*(1+r)^b + P0*((1+r)^b - 1)/r"},
                  confidence_label=label)
    return result


DELAY_SAMPLE_OFFSETS = tuple(range(0, 80, 5))
DELAY_CELL_SAMPLES = RATE // 4
DELAY_LEAD_SAMPLES = 1600
DELAY_WINDOW_SECONDS = (-.010, .040)
DELAY_MINIMUM_DETECTIONS = 12
DELAY_PROBES = {
    "unit_impulse": "one sample of amplitude 0.5",
    "click_3500hz_exp": "holdout click: 0.1*sin(2*pi*3500*t)*exp(-t/1.8 ms), 9 ms",
    "distorted_c1_attack": "0.3*min(1,t/1.5 ms)*exp(-t/23 ms)*tanh(3.5*sin(2*pi*32.70*t)), 40 ms, no high-pass",
}
DELAY_COMPENSATION_PATHS = {
    "periodic_high_frequency_candidate": ("high_frequency_novelty", "click_3500hz_exp"),
    "broadband_attack_candidate": ("broadband_rms_novelty", "distorted_c1_attack"),
    "spectral_flux_attack_candidate": None,
    "superflux_attack_candidate": None,
}
_DELAY_CACHE: dict | None = None


def delay_probe_waveform(kind: str) -> list[float]:
    if kind == "unit_impulse":
        return [.5]
    if kind == "click_3500hz_exp":
        return [.1 * math.exp(-(j / RATE) / .0018) * math.sin(2 * math.pi * 3500 * j / RATE) for j in range(round(.009 * RATE))]
    if kind == "distorted_c1_attack":
        return [.3 * min(1.0, (j / RATE) / .0015) * math.exp(-(j / RATE) / .023)
                * math.tanh(3.5 * math.sin(2 * math.pi * 32.70 * j / RATE)) for j in range(round(.040 * RATE))]
    raise ValueError("Unknown delay probe")


def detector_peak_times(samples) -> dict[str, list[float]]:
    """Frame-midpoint peak times of both stdlib paths exactly as analyze() computes them."""
    hop_seconds = HOP / RATE
    rms, high = envelopes(samples)
    high_novelty = novelty(high)
    attacks = novelty(rms)
    high_peaks = high_frequency_peak_indices(high_novelty) if max(high_novelty, default=0) >= 1e-7 else []
    return {"high_frequency_novelty": [(index + .5) * hop_seconds for index in high_peaks],
            "broadband_rms_novelty": [(index + .5) * hop_seconds for index in broadband_peak_indices(attacks)]}


def _calibrate_detector_delay() -> dict:
    cells = {}
    for kind in DELAY_PROBES:
        waveform = delay_probe_waveform(kind)
        samples = [0.0] * (DELAY_CELL_SAMPLES * len(DELAY_SAMPLE_OFFSETS))
        onsets = []
        for cell, offset in enumerate(DELAY_SAMPLE_OFFSETS):
            start = cell * DELAY_CELL_SAMPLES + DELAY_LEAD_SAMPLES + offset
            onsets.append(start / RATE)
            for j, value in enumerate(waveform):
                samples[start + j] += value
        peaks = detector_peak_times(samples)
        for path, times in peaks.items():
            delays = []
            for onset in onsets:
                found = next((time for time in times if onset + DELAY_WINDOW_SECONDS[0] <= time <= onset + DELAY_WINDOW_SECONDS[1]), None)
                if found is not None:
                    delays.append(found - onset)
            ordered = sorted(delays)
            cells.setdefault(path, {})[kind] = {
                "median_seconds": statistics.median(ordered) if ordered else None,
                "q1_seconds": _quantile(ordered, .25) if ordered else None,
                "q3_seconds": _quantile(ordered, .75) if ordered else None,
                "min_seconds": ordered[0] if ordered else None,
                "max_seconds": ordered[-1] if ordered else None,
                "probe_count": len(onsets), "detected_count": len(ordered), "undetected_count": len(onsets) - len(ordered)}
    table = {}
    for kind, route in DELAY_COMPENSATION_PATHS.items():
        if route is None:
            table[kind] = None
            continue
        cell = cells[route[0]][route[1]]
        usable = cell["detected_count"] >= DELAY_MINIMUM_DETECTIONS and cell["median_seconds"] is not None
        table[kind] = {"path": route[0], "probe": route[1], "delay_seconds": cell["median_seconds"] if usable else None,
                       "status": "measured_on_synthetic_impulses_not_physical_av_offset" if usable
                       else "calibration_probe_detection_insufficient"}
    return {"schema_version": 1, "paths": {"high_frequency_novelty": "first-difference RMS envelope novelty, threshold max(3*median, 4% max), min gap 4 frames",
                                            "broadband_rms_novelty": "RMS envelope novelty, threshold max(4*median, 8% max), min gap 6 frames"},
            "probes": dict(DELAY_PROBES), "sample_rate": RATE, "hop_samples": HOP,
            "sub_hop_offsets_samples": list(DELAY_SAMPLE_OFFSETS), "cell_seconds": DELAY_CELL_SAMPLES / RATE,
            "probe_onset_within_cell_samples": DELAY_LEAD_SAMPLES,
            "detection_rule": "first path peak in [onset-10 ms, onset+40 ms]; delay = reported frame-midpoint time minus true onset",
            "minimum_detections_for_use": DELAY_MINIMUM_DETECTIONS, "results": cells,
            "compensation_table": table,
            "uncalibrated_kinds_status": "uncalibrated",
            "status": "measured_on_synthetic_impulses_not_physical_av_offset",
            "limitations": ["Synthetic probes measure the analysis detector's frame/novelty delay only.",
                            "Physical microphone, device, AAC/encoder and A/V capture latency are uncalibrated.",
                            "Real attacks and clicks differ from the probes; per-event residual delay is unknown."]}


def onset_detector_delay_calibration() -> dict:
    """Deterministic, process-cached calibration through the stdlib 16 kHz detector paths."""
    global _DELAY_CACHE
    if _DELAY_CACHE is None:
        _DELAY_CACHE = _calibrate_detector_delay()
    return json.loads(json.dumps(_DELAY_CACHE))


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
    if grid:
        drift_seed, drift_provenance = grid["period_seconds"], "constant_click_grid_fit"
    elif selected:
        drift_seed, drift_provenance = selected["period_seconds"], "selected_audio_periodicity"
    elif bpm:
        drift_seed, drift_provenance = 60 / bpm, "operator_declared_approximate_bpm"
    else:
        drift_seed, drift_provenance = None, None
    middle = None
    if grid and grid["observed_events"]:
        middle = grid["observed_events"][len(grid["observed_events"]) // 2]["audio_relative_seconds"]
    drift = fit_click_drift(high_novelty, drift_seed, hop_seconds, drift_provenance, middle)
    if grid:
        grid["drift"] = drift
    calibration = onset_detector_delay_calibration()
    attacks = novelty(rms)
    indices = broadband_peak_indices(attacks)
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
    for event in events:
        entry = calibration["compensation_table"].get(event["kind"])
        delay = entry["delay_seconds"] if entry else None
        event["delay_compensated_source_timeline_seconds"] = event["source_timeline_seconds"] - delay if delay is not None else None
        event["delay_compensation"] = ("synthetic_probe_median_subtracted" if delay is not None
                                       else "uncalibrated_path" if entry is None else entry["status"])
    attack_times = optional["onsets"]["superflux"]["audio_relative_seconds"] if optional else [(index + .5) * hop_seconds for index in indices]
    attack_delay = calibration["compensation_table"]["broadband_attack_candidate"]["delay_seconds"]
    return {"schema_version": 1, "backend": backend, "analysis": {"sample_rate": RATE, "channels": 1, "samples": len(samples),
            "duration_seconds": len(samples) / RATE, "hop_samples": HOP, "hop_seconds": hop_seconds,
            "frame_timestamp": "frame_midpoint", "frame_midpoint_offset_seconds": hop_seconds / 2,
            "event_timestamp_conventions": {"stdlib": "frame_midpoint", "librosa": "librosa_frame_time_center_compensated"},
            "onset_detector_delay_seconds": attack_delay,
            "onset_detector_delay_status": ("measured_on_synthetic_impulses_not_physical_av_offset" if attack_delay is not None
                                            else "calibration_probe_detection_insufficient"),
            "onset_detector_delay_compensated": False, "physical_capture_latency": "uncalibrated",
            "onset_detector_delay_calibration": calibration,
            "resampling": "FFmpeg mono analysis copy; source unchanged"},
            "timeline": {"audio_stream_start_seconds": source_start, "event_time_origin": "first_decoded_audio_sample",
                         "source_axis": "audio_stream_start_plus_audio_relative_time", "decoder_priming_correction": "FFmpeg_decoder_handled_not_independently_verified"},
            "tempo_candidates": candidates, "selected_periodicity": selected, "click_grid": grid,
            "click_grid_drift": drift,
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
