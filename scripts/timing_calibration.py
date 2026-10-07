#!/usr/bin/env python3
"""Experimental capture-latency calibration for click-relative phrase timing (analysis only).

`analyze` turns an operator calibration clip (click only, offbeat palm-muted and open
attacks, optional played-on-click segment) plus mic distances into a closed-schema
calibration record: an offset correction with a GUM expanded uncertainty, built from an
acoustic path term, an amp-chain term, per-transient-class detector bias and a residual
floor. It abstains when the expanded uncertainty exceeds the 5 ms decision margin.

`apply` writes a new calibrated phrase-timing view. Direction is emitted only when the
calibrated per-phrase median exceeds the combined uncertainty (and the margin); otherwise
`within_uncertainty`. The source phrase-timing file is never modified.

Nothing here writes audio, filters audio, grades a performance or identifies notes.
Played-on-click attacks are a consistency check, never ground truth. Contract:
docs/spec/sprints/TIMING_CALIBRATION_S3.md.
"""
from __future__ import annotations

import argparse
import array
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import signal
import statistics
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rhythm = _load("timing_calibration_rhythm", "rhythm.py")
phrase_timing = _load("timing_calibration_phrase_timing", "phrase_timing.py")

SCHEMA_VERSION = 1
TOOL = "timing_calibration"
RECORD_KIND = "capture_latency_calibration_record"
VIEW_KIND = "calibrated_phrase_timing_view"
RATE = rhythm.RATE
HOP = rhythm.HOP
HOP_SECONDS = HOP / RATE

# Preregistered (spec section 7.6); analytic, not fitted.
DECISION_MARGIN_MS = 5.0
assert DECISION_MARGIN_MS == phrase_timing.WITHIN_MS
COVERAGE_FACTOR = 2
DISTANCE_HALF_WIDTH_M = {"measured": .05, "estimated": .30}
DISTANCE_BOUNDS_M = (0.0, 20.0)
TEMPERATURE_HALF_WIDTH_C = 2.0
UNDECLARED_TEMPERATURE_RANGE_C = (15.0, 30.0)
AMP_CHAIN_ANALOG_HALF_WIDTH_MS = .1
AMP_CHAIN_DECLARED_HALF_WIDTH_MS = .5
AMP_CHAIN_UNKNOWN_RANGE_MS = (0.0, 10.0)
AMP_CHAIN_DECLARED_BOUNDS_MS = (0.0, 50.0)
RESIDUAL_HALF_WIDTH_MS = 1.0
MIN_CLICK_EVENTS = 16
MIN_ATTACK_EVENTS = 12
MEDIAN_CI_COVERAGE = .95
ISOLATION_SECONDS = .100  # pre-registered 150 ms tightened in development (section 10); covers the fine windows
PLAUSIBILITY_BAND_MS = (-60.0, 30.0)
PHRASE_MEDIAN_FACTOR = 1.858  # 2 * 1.253 * (IQR / 1.349) / sqrt(n)

# Fine-onset reference estimator (frozen at the eval commit; spec 7.6 and section 10).
FINE_SMOOTH_SAMPLES = 8
FINE_FLOOR_WINDOW_SECONDS = (-.060, -.020)
FINE_PEAK_WINDOW_SECONDS = (-.010, .040)
FINE_THRESHOLD_FRACTION = .2
FINE_SEARCH_START_SECONDS = -.015
FINE_PROBE_CELL_SAMPLES = RATE
FINE_PROBE_LEAD_SAMPLES = 1600

# Event association rules (frozen at the eval commit; spec section 10).
GRID_MIN_EVENTS = 8
GRID_SPAN_MIN_COVERAGE = .5
GRID_REJECT_FLOOR_SECONDS = .012
CLICK_ASSOCIATION_SECONDS = .025
OFFBEAT_WINDOW_FRACTION = .25
ATTACK_MAGNITUDE_FACTOR = 1.5
ATTACK_MAGNITUDE_QUANTILE = .95
ON_CLICK_MIN_EVENTS = 8
PHASE_LOCK_RESULTANT = .9
CLICK_COINCIDENCE_HALF_WIDTH_MS = HOP / RATE / 2 * 1000  # half a hop (2.5 ms); development guard (section 10)
CLICK_SELF_MIN_EVENTS = 8
# Post-eval fix R2 (spec section 11): strong-event floor for high-frequency peaks in click_only spans.
CLICK_STRENGTH_FRACTION = .3
CLICK_REFERENCE_SECONDS_PER_EVENT = 2.0

MAX_AUDIO_SECONDS = 600
MAX_JSON_BYTES = 64 * 1024 * 1024
DECODE_TIMEOUT_SECONDS = 180
ANALYZE_TIMEOUT_SECONDS = 600
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "s2" / "timing_calibration"

SEGMENT_KINDS = ("click_only", "offbeat_palm_muted", "offbeat_open", "on_click_palm_muted")
REQUIRED_SEGMENT_KINDS = SEGMENT_KINDS[:3]
ATTACK_CLASS_BY_SEGMENT = {"offbeat_palm_muted": "palm_muted_pick_attack", "offbeat_open": "open_pick_attack"}
CLASS_PATH = {"click": "high_frequency_novelty", "palm_muted_pick_attack": "broadband_rms_novelty",
              "open_pick_attack": "broadband_rms_novelty"}
CLASS_PRIOR_KIND = {"click": "periodic_high_frequency_candidate", "palm_muted_pick_attack": "broadband_attack_candidate",
                    "open_pick_attack": "broadband_attack_candidate"}
FINE_PROBE_CLASSES = {"unit_impulse": "click", "click_3500hz_exp": "click", "mechanical_wood_click": "click",
                      "distorted_c1_attack": "palm_muted_pick_attack", "open_sustained_c1": "open_pick_attack"}
ABSTAIN_REASON_TEMPLATES = ("segment_missing:{kind}", "insufficient_click_events", "insufficient_attack_events:{class}",
                            "click_grid_not_fitted", "distance_out_of_bounds",
                            "expanded_uncertainty_exceeds_decision_margin", "played_on_click_consistency_failed",
                            "decode_failed")
ABSTAIN_REASONS = tuple([f"segment_missing:{kind}" for kind in REQUIRED_SEGMENT_KINDS]
                        + ["insufficient_click_events"]
                        + [f"insufficient_attack_events:{name}" for name in ATTACK_CLASS_BY_SEGMENT.values()]
                        + ["click_grid_not_fitted", "distance_out_of_bounds",
                           "expanded_uncertainty_exceeds_decision_margin", "played_on_click_consistency_failed",
                           "decode_failed"])
REFUSAL_CODES = ("calibration_record_required", "calibration_record_invalid", "calibration_abstained",
                 "detector_identity_mismatch", "setup_id_mismatch", "phrase_timing_schema_unsupported",
                 "output_under_accepted_runs",
                 # analyze input refusals (typed, nothing written)
                 "segments_invalid", "distances_invalid", "amp_chain_invalid", "input_invalid", "audio_too_long")
FIXED_UNKNOWNS = {
    "human_intent_is_ground_truth": False,
    "phone_input_latency": "common_mode_within_one_recording_inference",
    "av_picture_offset": "not_applicable_audio_only",
    "click_identity_in_take": "unverified",
    "listening_ab": "not_performed",
    "performance_grading": "not_performed",
    "expected_rhythm_reference": None,
    "audio_written": False,
    "filters_applied": [],
    "real_take_direction": "not_claimed_by_lane",
}
RECORD_KEYS = frozenset({
    "schema_version", "tool", "kind", "run_id", "status", "abstain_reasons", "producer", "claims", "input",
    "segments", "capture_setup", "distances", "reference_definition", "listener_view", "components",
    "offset_correction_ms", "decision_margin_ms", "abstain_rule", "consistency_check", "click_grid",
    "detector_identity", "limitations", *FIXED_UNKNOWNS})
COMPONENT_KEYS = frozenset({"estimate_ms", "interval_ms", "standard_uncertainty_ms", "distribution", "basis"})
COMPONENT_NAMES = ("acoustic_path", "amp_chain", "detector_bias", "attack_class_hull", "residual")
CLASS_KEYS = frozenset({"status", "path", "event_count", "isolated_event_count", "valid_fine_onset_count",
                        "detector_minus_fine_median_ms", "detector_minus_fine_ci_ms", "ci_order_statistics",
                        "ci_coverage", "fine_estimator_synthetic_bias_ms", "fine_estimator_spread_half_range_ms",
                        "synthetic_probe_prior_ms", "sub_hop_phase_resultant", "sub_hop_phase_locked",
                        "bias_estimate_ms", "standard_uncertainty_ms", "interval_ms"})
OFFSET_KEYS = frozenset({"estimate", "expanded_uncertainty_ms", "interval_ms", "coverage_factor", "combination",
                         "attempted_estimate", "attempted_expanded_uncertainty_ms", "standard_uncertainty_budget_ms"})
CONSISTENCY_KEYS = frozenset({"n", "calibrated_median_ms", "iqr_ms", "plausibility_band_ms", "status", "role",
                              "used_in_offset_estimate"})
VIEW_KEYS = frozenset({
    "schema_version", "tool", "kind", "run_id", "producer", "claims", "inputs", "source_phrase_timing_unmodified",
    "calibration_consumed", "direction_meaning", "rules", "summary", "phrases", "limitations",
    "real_take_status", "click_identity", *FIXED_UNKNOWNS})
CALIBRATED_KEYS = frozenset({"basis_field", "calibrated_median_offset_ms", "phrase_median_uncertainty_ms",
                             "combined_uncertainty_ms", "direction_threshold_ms", "direction", "direction_status",
                             "listener_view_offset_ms", "withheld_basis"})
WITHHELD_BASES = ("source_phrase_abstained", "onset_median_coincides_with_click_self_detection")
DIRECTION_MEANING = ("sign of the calibrated source-emission offset relative to the click; a review hypothesis "
                     "for listening, never a performance grade")
RECORD_LIMITATIONS = [
    "Detector bias is measured on the operator's real click and isolated real attacks against a fine-onset "
    "reference whose own per-class bias comes from noise-free synthetic probes; real transients may differ.",
    "The acoustic path uses operator-declared distances and a temperature-bounded speed of sound; reflections, "
    "speaker and metronome acoustic centres are covered only by the residual floor.",
    "Phone or Mac input latency, ADC and encoder delay are treated as common-mode within one recording (inference); "
    "signal-dependent device processing is not modelled.",
    "Played-on-click attacks are a consistency check only; human synchronization typically anticipates the click, "
    "so they never set or tune the offset.",
    "Legato, tapping and sweeps are uncalibrated; the attack hull covers palm-muted and open pick attacks only.",
    "The record is valid only for the declared setup (same device, app, room, amp, metronome and placement); "
    "placement match is operator-declared, not measured.",
]
VIEW_LIMITATIONS = [
    "Directions are review hypotheses about the calibrated source-emission offset, emitted only beyond the "
    "combined uncertainty; they are not performance grades or note-level verdicts.",
    "Phrase onsets are unclassified, so the correction uses the palm-muted/open attack hull; legato, tapping and "
    "sweep phrases are uncalibrated.",
    "The click identity in the take is unverified; a guitar attack can mask or displace a click.",
    "The calibration applies only to a take recorded with the declared setup and placement.",
]


class Refusal(Exception):
    """Typed refusal; nothing is written."""

    def __init__(self, code: str, message: str):
        if code not in REFUSAL_CODES:
            raise ValueError(f"unknown refusal code {code}")
        super().__init__(f"{code}: {message}")
        self.code = code


# ---------------------------------------------------------------------------------------------
# Small numeric helpers


def speed_of_sound(temperature_c: float) -> float:
    return 331.3 * math.sqrt(1 + temperature_c / 273.15)


def _binomial_cdf(k: int, n: int) -> float:
    return sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n


def median_ci(ordered: list[float], coverage: float = MEDIAN_CI_COVERAGE):
    """Narrowest symmetric order-statistic CI (x_(j), x_(n-j+1)) of the median with coverage >= target."""
    n = len(ordered)
    best = None
    for j in range(1, n // 2 + 1):
        achieved = 1 - 2 * _binomial_cdf(j - 1, n)
        if achieved >= coverage:
            best = (j, achieved)
        else:
            break
    if best is None:
        return None
    j, achieved = best
    return ordered[j - 1], ordered[n - j], j, achieved


def _quantile(values: list[float], q: float) -> float:
    return rhythm._quantile(sorted(values), q)


def _ms(seconds: float | None) -> float | None:
    return None if seconds is None else seconds * 1000


def _circular_resultant(times: list[float]) -> float | None:
    if not times:
        return None
    angles = [2 * math.pi * ((t * RATE) % HOP) / HOP for t in times]
    return math.hypot(sum(math.cos(a) for a in angles), sum(math.sin(a) for a in angles)) / len(angles)


def canonical_sha256(document) -> str:
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
                          .encode()).hexdigest()


def samples_sha256(samples) -> str:
    return hashlib.sha256(array.array("f", samples).tobytes()).hexdigest()


def producer_hashes() -> dict:
    return {"timing_calibration_sha256": rhythm.file_hash(Path(__file__)),
            "rhythm_sha256": rhythm.file_hash(SCRIPTS / "rhythm.py")}


# ---------------------------------------------------------------------------------------------
# Fine-onset reference estimator


def fine_onset(samples, detector_time: float) -> float | None:
    """First crossing of floor + 0.2*(peak - floor) on an 8-sample trailing mean of |x|.

    Floor: median over [det-60, det-20] ms; peak: max over [det-10, det+40] ms; search forward
    from det-15 ms. Returns None when the window leaves the signal, there is no transient, or the
    smoothed level is already above threshold at the search start.
    """
    det = round(detector_time * RATE)
    floor_lo = det + round(FINE_FLOOR_WINDOW_SECONDS[0] * RATE)
    floor_hi = det + round(FINE_FLOOR_WINDOW_SECONDS[1] * RATE)
    peak_lo = det + round(FINE_PEAK_WINDOW_SECONDS[0] * RATE)
    peak_hi = det + round(FINE_PEAK_WINDOW_SECONDS[1] * RATE)
    start = det + round(FINE_SEARCH_START_SECONDS * RATE)
    base = floor_lo - FINE_SMOOTH_SAMPLES + 1
    if base < 0 or peak_hi >= len(samples):
        return None
    smoothed = {}
    running = sum(abs(samples[i]) for i in range(base, base + FINE_SMOOTH_SAMPLES - 1))
    for i in range(floor_lo, peak_hi + 1):
        running += abs(samples[i])
        smoothed[i] = running / FINE_SMOOTH_SAMPLES
        running -= abs(samples[i - FINE_SMOOTH_SAMPLES + 1])
    floor = statistics.median(smoothed[i] for i in range(floor_lo, floor_hi + 1))
    peak_index = max(range(peak_lo, peak_hi + 1), key=lambda i: smoothed[i])
    peak = smoothed[peak_index]
    if peak - floor <= 1e-9 or peak <= 1.5 * floor:
        return None
    threshold = floor + FINE_THRESHOLD_FRACTION * (peak - floor)
    if smoothed[start] >= threshold or peak_index <= start:
        return None
    for i in range(start + 1, peak_index + 1):
        if smoothed[i] >= threshold:
            previous = smoothed[i - 1]
            fraction = (threshold - previous) / (smoothed[i] - previous) if smoothed[i] > previous else 1.0
            return (i - 1 + fraction) / RATE
    return None


# ---------------------------------------------------------------------------------------------
# Synthetic waveforms (shared by the probe table, the tests and the sealed evaluation)


def wood_click_waveform(amplitude: float, rng: random.Random) -> list[float]:
    """4 ms white burst x exp(-t/0.8 ms) through a two-pole resonator at 2.2 kHz, Q 6; peak-normalised."""
    length = round(.009 * RATE)
    burst = round(.004 * RATE)
    excitation = [rng.uniform(-1, 1) * math.exp(-(j / RATE) / .0008) if j < burst else 0.0 for j in range(length)]
    radius = math.exp(-math.pi * (2200 / 6) / RATE)
    coefficient = 2 * radius * math.cos(2 * math.pi * 2200 / RATE)
    output, y1, y2 = [], 0.0, 0.0
    for value in excitation:
        y = value + coefficient * y1 - radius * radius * y2
        output.append(y)
        y1, y2 = y, y1
    peak = max(abs(v) for v in output) or 1.0
    return [amplitude * v / peak for v in output]


def click_waveform(model: str, amplitude: float, rng: random.Random) -> list[float]:
    if model == "click_3500hz_exp":
        return [amplitude * math.exp(-(j / RATE) / .0018) * math.sin(2 * math.pi * 3500 * j / RATE)
                for j in range(round(.009 * RATE))]
    if model == "mechanical_wood_click":
        return wood_click_waveform(amplitude, rng)
    raise ValueError("unknown click model")


def attack_waveform(kind: str, midi: int, drive: float, tau: float, gain: float, extent: int,
                    release: int) -> list[float]:
    """Distorted pick attack: tanh drive, 1.5 ms rise, palm-muted or open sustain; no high-pass."""
    frequency = 440 * 2 ** ((midi - 69) / 12)
    out = []
    for j in range(extent):
        age = j / RATE
        envelope = min(1.0, age / .0015, (extent - j) / max(1, release))
        if kind == "palm":
            envelope *= math.exp(-age / tau)
        else:
            envelope *= (.35 + .65 * math.exp(-age / tau)) * math.exp(-age / .6)
        out.append(gain * envelope * math.tanh(drive * math.sin(2 * math.pi * frequency * age)))
    return out


def fine_probe_waveform(kind: str) -> list[float]:
    if kind in rhythm.DELAY_PROBES:
        return rhythm.delay_probe_waveform(kind)
    if kind == "mechanical_wood_click":
        return wood_click_waveform(.1, random.Random(0))
    if kind == "open_sustained_c1":
        return attack_waveform("open", 24, 3.5, .3, .3, round(.3 * RATE), round(.01 * RATE))
    raise ValueError("unknown fine probe")


_FINE_TABLE: dict | None = None


def fine_estimator_bias_table() -> dict:
    """Per-class fine-onset bias from noise-free probes at the 16 sub-hop offsets (never from eval seeds)."""
    global _FINE_TABLE
    if _FINE_TABLE is None:
        per_probe = {}
        for probe, klass in FINE_PROBE_CLASSES.items():
            waveform = fine_probe_waveform(probe)
            offsets = rhythm.DELAY_SAMPLE_OFFSETS
            samples = [0.0] * (FINE_PROBE_CELL_SAMPLES * len(offsets))
            onsets = []
            for cell, offset in enumerate(offsets):
                start = cell * FINE_PROBE_CELL_SAMPLES + FINE_PROBE_LEAD_SAMPLES + offset
                onsets.append(start / RATE)
                for j, value in enumerate(waveform):
                    samples[start + j] += value
            times = rhythm.detector_peak_times(samples)[CLASS_PATH[klass]]
            values = []
            for onset in onsets:
                found = next((t for t in times if onset - .010 <= t <= onset + .040), None)
                fine = fine_onset(samples, found) if found is not None else None
                if fine is not None:
                    values.append(fine - onset)
            per_probe[probe] = {"class": klass, "path": CLASS_PATH[klass], "probe_count": len(onsets),
                                "valid_count": len(values),
                                "median_ms": _ms(statistics.median(values)) if values else None,
                                "min_ms": _ms(min(values)) if values else None,
                                "max_ms": _ms(max(values)) if values else None, "_values": values}
        classes = {}
        for klass in ("click", "palm_muted_pick_attack", "open_pick_attack"):
            values = [v for row in per_probe.values() if row["class"] == klass for v in row["_values"]]
            low, high = min(values), max(values)
            classes[klass] = {"bias_ms": _ms((low + high) / 2), "half_range_ms": _ms((high - low) / 2),
                              "value_count": len(values),
                              "probes": [p for p, row in per_probe.items() if row["class"] == klass]}
        for row in per_probe.values():
            row.pop("_values")
        _FINE_TABLE = {"probes": per_probe, "classes": classes,
                       "rule": "bias = midpoint of [min, max] of (fine onset - true onset) over the class probes x 16 "
                               "sub-hop offsets, noise-free; spread = half-range, treated as uniform"}
    return json.loads(json.dumps(_FINE_TABLE))


# ---------------------------------------------------------------------------------------------
# Input parsing


def parse_distances(text: str) -> dict:
    allowed = ("mic_to_metronome", "mic_to_amp", "ear_to_metronome", "ear_to_amp")
    values = {}
    if not isinstance(text, str) or not text.strip():
        raise Refusal("distances_invalid", "empty distances")
    for item in text.split(","):
        if "=" not in item:
            raise Refusal("distances_invalid", f"expected name=metres, got {item!r}")
        name, raw = (part.strip() for part in item.split("=", 1))
        if name not in allowed or name in values:
            raise Refusal("distances_invalid", f"unknown or repeated distance {name!r}")
        try:
            value = float(raw)
        except ValueError as exc:
            raise Refusal("distances_invalid", f"non-numeric distance {raw!r}") from exc
        if not math.isfinite(value):
            raise Refusal("distances_invalid", "non-finite distance")
        values[name] = value
    if "mic_to_metronome" not in values or "mic_to_amp" not in values:
        raise Refusal("distances_invalid", "mic_to_metronome and mic_to_amp are required")
    if ("ear_to_metronome" in values) != ("ear_to_amp" in values):
        raise Refusal("distances_invalid", "ear distances must be given as a pair")
    return values


def parse_amp_chain(text: str) -> tuple[str, float | None]:
    if text in ("analog", "unknown"):
        return text, None
    if isinstance(text, str) and text.startswith("declared:"):
        try:
            value = float(text.split(":", 1)[1])
        except ValueError as exc:
            raise Refusal("amp_chain_invalid", "declared amp chain needs a number of ms") from exc
        if not math.isfinite(value) or not AMP_CHAIN_DECLARED_BOUNDS_MS[0] <= value <= AMP_CHAIN_DECLARED_BOUNDS_MS[1]:
            raise Refusal("amp_chain_invalid", "declared amp chain must be within [0, 50] ms")
        return "declared", value
    raise Refusal("amp_chain_invalid", "amp chain must be analog, declared:MS or unknown")


def normalize_segments(document) -> list[dict]:
    """Closed SEG.json schema: {schema_version: 1, segments: [{kind, start_seconds, end_seconds, review_text}]}."""
    if not isinstance(document, dict) or set(document) - {"schema_version", "segments", "source_sha256", "note"}:
        raise Refusal("segments_invalid", "unknown top-level keys or not an object")
    if document.get("schema_version") != 1 or not isinstance(document.get("segments"), list):
        raise Refusal("segments_invalid", "schema_version 1 with a segments list is required")
    spans = []
    for index, span in enumerate(document["segments"]):
        if not isinstance(span, dict) or set(span) != {"kind", "start_seconds", "end_seconds", "review_text"}:
            raise Refusal("segments_invalid", f"segment {index} must have exactly kind, start_seconds, end_seconds, review_text")
        kind, start, end, text = span["kind"], span["start_seconds"], span["end_seconds"], span["review_text"]
        if kind not in SEGMENT_KINDS:
            raise Refusal("segments_invalid", f"segment {index} kind {kind!r} is not in the closed enum")
        if (isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, (int, float))
                or not isinstance(end, (int, float)) or not math.isfinite(start) or not math.isfinite(end)
                or start < 0 or end <= start or end > MAX_AUDIO_SECONDS):
            raise Refusal("segments_invalid", f"segment {index} needs finite 0 <= start < end <= 600")
        if not isinstance(text, str) or not text.strip():
            raise Refusal("segments_invalid", f"segment {index} needs review_text")
        spans.append({"index": index, "kind": kind, "start_seconds": float(start), "end_seconds": float(end),
                      "review_text": text})
    ordered = sorted(spans, key=lambda s: s["start_seconds"])
    for left, right in zip(ordered, ordered[1:]):
        if right["start_seconds"] < left["end_seconds"]:
            raise Refusal("segments_invalid", "segments overlap")
    return spans


# ---------------------------------------------------------------------------------------------
# Components


def _component(estimate, interval, u, distribution, basis) -> dict:
    return {"estimate_ms": estimate, "interval_ms": interval, "standard_uncertainty_ms": u,
            "distribution": distribution, "basis": basis}


def acoustic_path_component(distances: dict, method: str, room_temp_c: float | None) -> tuple[dict, dict]:
    half = DISTANCE_HALF_WIDTH_M[method]
    if room_temp_c is None:
        t_lo, t_hi = UNDECLARED_TEMPERATURE_RANGE_C
        t_mid = (t_lo + t_hi) / 2
    else:
        t_lo, t_hi, t_mid = room_temp_c - TEMPERATURE_HALF_WIDTH_C, room_temp_c + TEMPERATURE_HALF_WIDTH_C, room_temp_c
    c_lo, c_hi, c_mid = speed_of_sound(t_lo), speed_of_sound(t_hi), speed_of_sound(t_mid)
    d_met, d_amp = distances["mic_to_metronome"], distances["mic_to_amp"]
    difference = d_amp - d_met
    estimate = difference / c_mid * 1000
    d_lo, d_hi = difference - 2 * half, difference + 2 * half
    candidates = [d / c for d in (d_lo, d_hi) for c in (c_lo, c_hi)]
    interval = [min(candidates) * 1000, max(candidates) * 1000]
    u_distance = half / math.sqrt(3) / c_mid * 1000
    u_c = (c_hi - c_lo) / (2 * math.sqrt(3))
    u = math.sqrt(2 * u_distance ** 2 + (estimate * u_c / c_mid) ** 2)
    block = {"values_m": dict(distances), "method": method, "per_distance_half_width_m": half,
             "room_temp_c": room_temp_c, "speed_of_sound_interval_m_s": [c_lo, c_hi],
             "speed_of_sound_formula": "331.3*sqrt(1+T/273.15)",
             "temperature_interval_c": [t_lo, t_hi]}
    component = _component(estimate, interval, u, "uniform_distance_and_speed_of_sound_GUM_propagation",
                           "(d_mic_amp - d_mic_metronome) / c; interval arithmetic over distance half-widths and c")
    return component, block


def listener_component(distances: dict, method: str, room_temp_c: float | None) -> dict:
    if "ear_to_metronome" not in distances:
        return {"status": "not_computed", "estimate_ms": None, "interval_ms": None, "direction_bearing": False,
                "basis": "ear distances not supplied"}
    swapped = {"mic_to_metronome": distances["ear_to_metronome"], "mic_to_amp": distances["ear_to_amp"]}
    component, _ = acoustic_path_component(swapped, method, room_temp_c)
    return {"status": "computed", "estimate_ms": component["estimate_ms"], "interval_ms": component["interval_ms"],
            "direction_bearing": False,
            "basis": "arithmetic only: (d_ear_amp - d_ear_metronome)/c added to the calibrated source-emission offset"}


def amp_chain_component(mode: str, value: float | None) -> dict:
    if mode == "analog":
        hw = AMP_CHAIN_ANALOG_HALF_WIDTH_MS
        return _component(0.0, [-hw, hw], hw / math.sqrt(3), "uniform", "operator-declared analog amp chain: 0 +/- 0.1 ms")
    if mode == "declared":
        hw = AMP_CHAIN_DECLARED_HALF_WIDTH_MS
        return _component(value, [value - hw, value + hw], hw / math.sqrt(3), "uniform",
                          f"operator-declared amp chain latency {value} +/- 0.5 ms")
    lo, hi = AMP_CHAIN_UNKNOWN_RANGE_MS
    return _component((lo + hi) / 2, [lo, hi], (hi - lo) / math.sqrt(12), "uniform",
                      "unknown amp chain: uniform [0, 10] ms (always exceeds the decision margin)")


def residual_component() -> dict:
    hw = RESIDUAL_HALF_WIDTH_MS
    return _component(0.0, [-hw, hw], hw / math.sqrt(3), "uniform",
                      "preregistered floor for reflections, acoustic centres and unmodelled terms")


# ---------------------------------------------------------------------------------------------
# Event extraction


class Envelopes:
    def __init__(self, samples):
        rms, high = rhythm.envelopes(samples)
        self.paths = {"high_frequency_novelty": rhythm.novelty(high), "broadband_rms_novelty": rhythm.novelty(rms)}

    def events(self, path: str, start: float, end: float) -> list[tuple[float, float]]:
        """(frame-midpoint time, novelty value) of the path's peaks inside [start, end) audio-relative seconds."""
        values = self.paths[path]
        lo = max(0, math.ceil(start / HOP_SECONDS))
        hi = min(len(values), math.floor(end / HOP_SECONDS))
        sub = values[lo:hi]
        if len(sub) < 3 or max(sub) < 1e-7:
            return []
        picker = rhythm.high_frequency_peak_indices if path == "high_frequency_novelty" else rhythm.broadband_peak_indices
        return [((lo + i + .5) * HOP_SECONDS, sub[i]) for i in picker(sub)]


def _least_squares(pairs: list[tuple[int, float]]) -> tuple[float, float] | None:
    beats = [b for b, _ in pairs]
    if len(set(beats)) < 2:
        return None
    mean_b, mean_t = statistics.mean(beats), statistics.mean(t for _, t in pairs)
    variance = sum((b - mean_b) ** 2 for b in beats)
    period = sum((b - mean_b) * (t - mean_t) for b, t in pairs) / variance
    return mean_t - mean_b * period, period


def fit_session_grid(span_events: list[list[float]]) -> dict:
    """Constant-period click grid from click_only spans (high-frequency novelty times)."""
    failed = {"status": "not_fitted", "period_seconds": None, "phase_seconds_audio_relative": None,
              "retained_event_count": 0, "median_abs_residual_ms": None, "per_span": [],
              "basis": "click_only_spans_high_frequency_novelty_least_squares"}
    if not span_events:
        return dict(failed, reason="no_click_only_span")
    longest = max(span_events, key=len)
    if len(longest) < 4:
        return dict(failed, reason="fewer_than_4_click_candidates")
    iois = [b - a for a, b in zip(longest, longest[1:]) if .15 <= b - a <= 2.0]
    if len(iois) < 3:
        return dict(failed, reason="no_plausible_inter_onset_intervals")
    seed = statistics.median(iois)
    pairs, beat, last = [(0, longest[0])], 0, longest[0]
    for time in longest[1:]:
        steps = round((time - last) / seed)
        if steps < 1 or abs(time - last - steps * seed) > .25 * seed:
            continue
        beat += steps
        pairs.append((beat, time))
        last = time
    fit = _least_squares(pairs)
    if fit is None:
        return dict(failed, reason="degenerate_fit")
    phase, period = fit
    everything = sorted(t for span in span_events for t in span)
    retained = []
    for _ in range(4):
        by_beat = {}
        for time in everything:
            index = round((time - phase) / period)
            residual = time - (phase + index * period)
            if index not in by_beat or abs(residual) < abs(by_beat[index][1]):
                by_beat[index] = (time, residual)
        residuals = [r for _, r in by_beat.values()]
        center = statistics.median(residuals)
        spread = statistics.median(abs(r - center) for r in residuals)
        bound = max(GRID_REJECT_FLOOR_SECONDS, 3 * 1.4826 * spread)
        retained = [(b, t) for b, (t, r) in sorted(by_beat.items()) if abs(r - center) <= bound]
        fit = _least_squares(retained)
        if fit is None:
            return dict(failed, reason="degenerate_fit")
        phase, period = fit
    residuals = [t - (phase + b * period) for b, t in retained]
    median_abs = statistics.median(abs(r) for r in residuals) if residuals else math.inf
    per_span = []
    coverage_ok = True
    for index, span in enumerate(span_events):
        inside = [(b, t) for b, t in retained if span and span[0] - 1e-9 <= t <= span[-1] + 1e-9]
        expected = (max(b for b, _ in inside) - min(b for b, _ in inside) + 1) if inside else 0
        coverage = len(inside) / expected if expected else 0.0
        span_residuals = [t - (phase + b * period) for b, t in inside]
        per_span.append({"span_order": index, "candidate_count": len(span), "retained_count": len(inside),
                         "coverage": coverage,
                         "median_abs_residual_ms": _ms(statistics.median(abs(r) for r in span_residuals))
                         if span_residuals else None,
                         "median_residual_ms": _ms(statistics.median(span_residuals)) if span_residuals else None})
        if len(span) >= 4 and coverage < GRID_SPAN_MIN_COVERAGE:
            coverage_ok = False
    result = {"status": "fitted", "period_seconds": period, "phase_seconds_audio_relative": phase,
              "retained_event_count": len(retained), "median_abs_residual_ms": _ms(median_abs),
              "per_span": per_span, "basis": "click_only_spans_high_frequency_novelty_least_squares",
              "bpm": 60 / period if period > 0 else None, "seed_period_seconds": seed,
              "bracket_median_residual_shift_ms": (per_span[-1]["median_residual_ms"] - per_span[0]["median_residual_ms"])
              if len(per_span) > 1 and per_span[0]["median_residual_ms"] is not None
              and per_span[-1]["median_residual_ms"] is not None else None,
              "drift_model": "constant_period; bracket shift between first and last click_only span reported",
              "identity": "periodic_high_frequency_transients_in_operator_declared_click_only_spans"}
    if (period <= 0 or len(retained) < GRID_MIN_EVENTS or median_abs > min(.025, .05 * period) or not coverage_ok):
        return dict(result, status="not_fitted", reason="residual_coverage_or_count_bound")
    return result


def strong_click_events(events: list[tuple[float, float]], span_seconds: float) -> list[tuple[float, float]]:
    """Keep high-frequency peaks with novelty >= 0.3 x the median of the strongest ceil(span/2 s) peaks.

    In a click-only span no attack sets the peak picker's maximum, so fan-noise peaks pass its adaptive
    threshold; the strongest ceil(span/2 s) peaks are clicks at any tempo of at least 30 BPM.
    """
    if not events:
        return []
    count = max(1, min(len(events), math.ceil(span_seconds / CLICK_REFERENCE_SECONDS_PER_EVENT)))
    reference = statistics.median(sorted((value for _, value in events), reverse=True)[:count])
    return [(time, value) for time, value in events if value >= CLICK_STRENGTH_FRACTION * reference]


def _isolated(time: float, value: float, events: list[tuple[float, float]]) -> bool:
    """No other same-path event in the preceding 100 ms and no stronger one in the following 100 ms."""
    for other, strength in events:
        if other == time:
            continue
        if time - ISOLATION_SECONDS <= other < time:
            return False
        if time < other <= time + ISOLATION_SECONDS and strength > value:
            return False
    return True


def _class_summary(klass: str, rows: list[dict], fine_table: dict, prior_table: dict, required: int) -> dict:
    values = sorted(row["det_minus_fine"] for row in rows if row["valid"])
    fine = fine_table["classes"][klass]
    prior = (prior_table.get(CLASS_PRIOR_KIND[klass]) or {}).get("delay_seconds")
    summary = {"status": "insufficient_events", "path": CLASS_PATH[klass], "event_count": len(rows),
               "isolated_event_count": sum(row["isolated"] for row in rows), "valid_fine_onset_count": len(values),
               "detector_minus_fine_median_ms": None, "detector_minus_fine_ci_ms": None,
               "ci_order_statistics": None, "ci_coverage": None,
               "fine_estimator_synthetic_bias_ms": fine["bias_ms"],
               "fine_estimator_spread_half_range_ms": fine["half_range_ms"],
               "synthetic_probe_prior_ms": _ms(prior), "sub_hop_phase_resultant": None, "sub_hop_phase_locked": None,
               "bias_estimate_ms": None, "standard_uncertainty_ms": None, "interval_ms": None}
    if values:
        summary["detector_minus_fine_median_ms"] = _ms(statistics.median(values))
    ci = median_ci(values) if len(values) >= required else None
    if ci is None:
        return summary
    lo, hi, j, achieved = ci
    resultant = _circular_resultant([row["fine"] for row in rows if row["valid"]])
    locked = resultant is not None and resultant >= PHASE_LOCK_RESULTANT
    u_stat = (hi - lo) / 2 / 1.96 * 1000
    u_fine = fine["half_range_ms"] / math.sqrt(3)
    u_lock = (HOP_SECONDS / 2 * 1000) / math.sqrt(3) if locked else 0.0
    u = math.sqrt(u_stat ** 2 + u_fine ** 2 + u_lock ** 2)
    estimate = summary["detector_minus_fine_median_ms"] + fine["bias_ms"]
    widen = fine["half_range_ms"] + (HOP_SECONDS / 2 * 1000 if locked else 0.0)
    summary.update(status="calibrated", detector_minus_fine_ci_ms=[lo * 1000, hi * 1000],
                   ci_order_statistics=[j, len(values) - j + 1], ci_coverage=achieved,
                   sub_hop_phase_resultant=resultant, sub_hop_phase_locked=locked,
                   bias_estimate_ms=estimate, standard_uncertainty_ms=u,
                   interval_ms=[lo * 1000 + fine["bias_ms"] - widen, hi * 1000 + fine["bias_ms"] + widen])
    return summary


def measure_session(samples, spans: list[dict], audio_start_seconds: float = 0.0) -> dict:
    """Detector events, fine onsets and the click grid for each declared span (internal diagnostics)."""
    env = Envelopes(samples)
    duration = len(samples) / RATE
    rel = [dict(span, start=span["start_seconds"] - audio_start_seconds, end=span["end_seconds"] - audio_start_seconds)
           for span in spans]
    rel = [span for span in rel if span["end"] > 0 and span["start"] < duration]
    click_spans = sorted((s for s in rel if s["kind"] == "click_only"), key=lambda s: s["start"])
    hf_by_span = [strong_click_events(env.events("high_frequency_novelty", s["start"], s["end"]), s["end"] - s["start"])
                  for s in click_spans]
    grid = fit_session_grid([[t for t, _ in events] for events in hf_by_span])
    out = {"grid": grid, "classes": {"click": [], "palm_muted_pick_attack": [], "open_pick_attack": []},
           "on_click": [], "click_broadband_reference": None, "click_broadband_self_offsets": []}
    if grid["status"] != "fitted":
        return out
    period, phase = grid["period_seconds"], grid["phase_seconds_audio_relative"]
    window = min(CLICK_ASSOCIATION_SECONDS, .1 * period)
    for events in hf_by_span:
        by_beat = {}
        for time, value in events:
            beat = round((time - phase) / period)
            residual = time - (phase + beat * period)
            if abs(residual) <= window and (beat not in by_beat or abs(residual) < abs(by_beat[beat][0] - (phase + beat * period))):
                by_beat[beat] = (time, value)
        for beat, (time, value) in sorted(by_beat.items()):
            fine = fine_onset(samples, time)
            isolated = _isolated(time, value, events)
            out["classes"]["click"].append({"det": time, "fine": fine, "beat": beat, "isolated": isolated,
                                            "valid": isolated and fine is not None,
                                            "det_minus_fine": (time - fine) if fine is not None else None})
    self_offsets = []
    for s in click_spans:
        chosen = {}
        for time, _ in env.events("broadband_rms_novelty", s["start"], s["end"]):
            beat = round((time - phase) / period)
            offset = time - (phase + beat * period)
            if abs(offset) <= window and (beat not in chosen or abs(offset) < abs(chosen[beat])):
                chosen[beat] = offset
        self_offsets.extend(chosen.values())
    out["click_broadband_self_offsets"] = self_offsets
    reference_values = [value for s in click_spans for _, value in env.events("broadband_rms_novelty", s["start"], s["end"])]
    reference = _quantile(reference_values, ATTACK_MAGNITUDE_QUANTILE) if reference_values else 0.0
    out["click_broadband_reference"] = reference
    floor = ATTACK_MAGNITUDE_FACTOR * reference
    for span in rel:
        if span["kind"] in ATTACK_CLASS_BY_SEGMENT:
            klass = ATTACK_CLASS_BY_SEGMENT[span["kind"]]
            events = env.events("broadband_rms_novelty", span["start"], span["end"])
            first_by_slot = {}
            for time, value in events:
                position = (time - phase) / period
                fraction = position - math.floor(position)
                if value < floor or abs(fraction - .5) > OFFBEAT_WINDOW_FRACTION:
                    continue
                first_by_slot.setdefault(math.floor(position), (time, value))
            for slot in sorted(first_by_slot):
                time, value = first_by_slot[slot]
                fine = fine_onset(samples, time)
                isolated = _isolated(time, value, events)
                out["classes"][klass].append({"det": time, "fine": fine, "isolated": isolated,
                                              "valid": isolated and fine is not None,
                                              "det_minus_fine": (time - fine) if fine is not None else None})
        elif span["kind"] == "on_click_palm_muted":
            chosen = {}
            for time, value in env.events("broadband_rms_novelty", span["start"], span["end"]):
                if value < floor:
                    continue
                beat = round((time - phase) / period)
                offset = time - (phase + beat * period)
                if beat not in chosen or abs(offset) < abs(chosen[beat]):
                    chosen[beat] = offset
            out["on_click"].extend(chosen[beat] for beat in sorted(chosen))
    return out


# ---------------------------------------------------------------------------------------------
# analyze


def _abstain_offset(attempt_estimate=None, attempt_u=None, budget=None) -> dict:
    return {"estimate": None, "expanded_uncertainty_ms": None, "interval_ms": None, "coverage_factor": COVERAGE_FACTOR,
            "combination": "GUM_root_sum_square_of_standard_uncertainties",
            "attempted_estimate": attempt_estimate, "attempted_expanded_uncertainty_ms": attempt_u,
            "standard_uncertainty_budget_ms": budget}


def analyze_samples(samples, segments_document, *, distances: dict, distance_method: str, setup_id: str,
                    amp_chain: str = "analog", room_temp_c: float | None = None, device_label: str | None = None,
                    app_label: str | None = None, metronome_label: str | None = None,
                    placement_note: str | None = None, audio_start_seconds: float = 0.0,
                    input_info: dict | None = None, run_id: str | None = None,
                    decode_error: str | None = None) -> dict:
    """Pure analysis over decoded 16 kHz mono samples; returns a closed-schema calibration record."""
    if distance_method not in DISTANCE_HALF_WIDTH_M:
        raise Refusal("distances_invalid", "distance method must be measured or estimated")
    if not isinstance(setup_id, str) or not setup_id.strip() or len(setup_id) > 200:
        raise Refusal("input_invalid", "setup id is required (at most 200 characters)")
    if room_temp_c is not None and (not math.isfinite(room_temp_c) or not -10 <= room_temp_c <= 45):
        raise Refusal("input_invalid", "room temperature must be within [-10, 45] C")
    if len(samples) / RATE > MAX_AUDIO_SECONDS:
        raise Refusal("audio_too_long", "calibration audio exceeds 600 s")
    amp_mode, amp_value = parse_amp_chain(amp_chain)
    spans = normalize_segments(segments_document)
    reasons: list[str] = []
    present = {span["kind"] for span in spans}
    for kind in REQUIRED_SEGMENT_KINDS:
        if kind not in present:
            reasons.append(f"segment_missing:{kind}")
    in_bounds = all(DISTANCE_BOUNDS_M[0] < value <= DISTANCE_BOUNDS_M[1] for value in distances.values())
    if not in_bounds:
        reasons.append("distance_out_of_bounds")
    fine_table = fine_estimator_bias_table()
    prior_table = rhythm.onset_detector_delay_calibration()["compensation_table"]
    if decode_error is None:
        measured = measure_session(samples, spans, audio_start_seconds)
    else:
        reasons.append("decode_failed")
        measured = {"grid": {"status": "not_fitted", "period_seconds": None, "phase_seconds_audio_relative": None,
                             "retained_event_count": 0, "median_abs_residual_ms": None, "per_span": [],
                             "basis": "click_only_spans_high_frequency_novelty_least_squares",
                             "reason": "decode_failed"},
                    "classes": {"click": [], "palm_muted_pick_attack": [], "open_pick_attack": []},
                    "on_click": [], "click_broadband_reference": None, "click_broadband_self_offsets": []}
    grid = measured["grid"]
    if "click_only" in present and grid["status"] != "fitted" and decode_error is None:
        reasons.append("click_grid_not_fitted")
    classes = {"click": _class_summary("click", measured["classes"]["click"], fine_table, prior_table, MIN_CLICK_EVENTS)}
    for klass in ("palm_muted_pick_attack", "open_pick_attack"):
        classes[klass] = _class_summary(klass, measured["classes"][klass], fine_table, prior_table, MIN_ATTACK_EVENTS)
    if grid["status"] == "fitted" and classes["click"]["status"] != "calibrated":
        reasons.append("insufficient_click_events")
    if grid["status"] == "fitted":
        for segment, klass in ATTACK_CLASS_BY_SEGMENT.items():
            if segment in present and classes[klass]["status"] != "calibrated":
                reasons.append(f"insufficient_attack_events:{klass}")
    classes["legato_tapping_sweep"] = {"status": "uncalibrated"}

    acoustic, distance_block = (acoustic_path_component(distances, distance_method, room_temp_c) if in_bounds else
                                (_component(None, None, None, "not_computed", "distance out of bounds"),
                                 {"values_m": dict(distances), "method": distance_method,
                                  "per_distance_half_width_m": DISTANCE_HALF_WIDTH_M[distance_method],
                                  "room_temp_c": room_temp_c, "speed_of_sound_interval_m_s": None,
                                  "speed_of_sound_formula": "331.3*sqrt(1+T/273.15)", "temperature_interval_c": None}))
    amp = amp_chain_component(amp_mode, amp_value)
    residual = residual_component()
    attack_ok = all(classes[k]["status"] == "calibrated" for k in ("palm_muted_pick_attack", "open_pick_attack"))
    click_ok = classes["click"]["status"] == "calibrated"
    if attack_ok:
        pm, op = classes["palm_muted_pick_attack"], classes["open_pick_attack"]
        low, high = sorted((pm["bias_estimate_ms"], op["bias_estimate_ms"]))
        midpoint, half = (low + high) / 2, (high - low) / 2
        u_hull = math.sqrt((half / math.sqrt(3)) ** 2 + max(pm["standard_uncertainty_ms"], op["standard_uncertainty_ms"]) ** 2)
        hull = _component(midpoint, [min(pm["interval_ms"][0], op["interval_ms"][0]), max(pm["interval_ms"][1], op["interval_ms"][1])],
                          u_hull, "uniform_hull_plus_larger_class_uncertainty",
                          "union over palm-muted and open pick-attack classes; phrase-timing onsets are unclassified")
        hull["point_estimate_hull_ms"] = [low, high]
    else:
        hull = _component(None, None, None, "not_computed", "attack classes not calibrated")
        hull["point_estimate_hull_ms"] = None
    if attack_ok and click_ok:
        click = classes["click"]
        det_estimate = hull["estimate_ms"] - click["bias_estimate_ms"]
        det_u = math.sqrt(hull["standard_uncertainty_ms"] ** 2 + click["standard_uncertainty_ms"] ** 2)
        detector = _component(det_estimate, [hull["interval_ms"][0] - click["interval_ms"][1],
                                             hull["interval_ms"][1] - click["interval_ms"][0]],
                              det_u, "GUM_root_sum_square", "attack-hull midpoint minus click bias (both vs fine-onset reference)")
    else:
        detector = _component(None, None, None, "not_computed", "click or attack classes not calibrated")
    detector["classes"] = classes

    offset = _abstain_offset()
    budget = None
    if acoustic["estimate_ms"] is not None and detector["estimate_ms"] is not None:
        budget = {"acoustic_path": acoustic["standard_uncertainty_ms"], "amp_chain": amp["standard_uncertainty_ms"],
                  "click_bias": classes["click"]["standard_uncertainty_ms"],
                  "attack_hull": hull["standard_uncertainty_ms"], "residual": residual["standard_uncertainty_ms"]}
        estimate = acoustic["estimate_ms"] + amp["estimate_ms"] + detector["estimate_ms"]
        expanded = COVERAGE_FACTOR * math.sqrt(sum(value ** 2 for value in budget.values()))
        if expanded > DECISION_MARGIN_MS:
            reasons.append("expanded_uncertainty_exceeds_decision_margin")
        offset = _abstain_offset(estimate, expanded, budget)
        offset.update(estimate=estimate, expanded_uncertainty_ms=expanded,
                      interval_ms=[estimate - expanded, estimate + expanded])

    on_click = [value * 1000 for value in measured["on_click"]]
    consistency = {"n": len(on_click), "calibrated_median_ms": None, "iqr_ms": None,
                   "plausibility_band_ms": list(PLAUSIBILITY_BAND_MS), "status": "not_available",
                   "role": "consistency_check_not_ground_truth", "used_in_offset_estimate": False}
    if offset["attempted_estimate"] is not None and len(on_click) >= ON_CLICK_MIN_EVENTS:
        calibrated = sorted(value - offset["attempted_estimate"] for value in on_click)
        median = statistics.median(calibrated)
        consistency.update(calibrated_median_ms=median,
                           iqr_ms=[_quantile(calibrated, .25), _quantile(calibrated, .75)],
                           status="passed" if PLAUSIBILITY_BAND_MS[0] <= median <= PLAUSIBILITY_BAND_MS[1] else "failed")
        if consistency["status"] == "failed":
            reasons.append("played_on_click_consistency_failed")

    reasons = [reason for reason in ABSTAIN_REASONS if reason in reasons]
    status = "abstained" if reasons else "calibrated"
    if status == "abstained":
        offset = _abstain_offset(offset["attempted_estimate"], offset["attempted_expanded_uncertainty_ms"], budget)
    producer = producer_hashes()
    info = input_info or {"kind": "in_memory_samples", "path": None, "sha256": samples_sha256(samples),
                          "signal_chain": "in_memory_samples", "profile_id": None, "manifest_sha256": None}
    info = dict(info, audio_start_seconds=audio_start_seconds, analysis_rate=RATE,
                duration_seconds=len(samples) / RATE)
    record = {
        "schema_version": SCHEMA_VERSION, "tool": TOOL, "kind": RECORD_KIND,
        "run_id": run_id or _run_id(), "status": status, "abstain_reasons": reasons,
        "producer": producer,
        "claims": {"measured": ["components.detector_bias.classes.*.detector_minus_fine_median_ms",
                                "components.detector_bias.classes.*.event_count", "click_grid",
                                "consistency_check.played_on_click"],
                   "inferred": ["components.acoustic_path", "components.amp_chain", "components.attack_class_hull",
                                "components.residual", "offset_correction_ms", "phone_input_latency"],
                   "listening": []},
        "input": info,
        "segments": [{k: span[k] for k in ("kind", "start_seconds", "end_seconds", "review_text")} for span in spans],
        "capture_setup": {"setup_id": setup_id, "device_label": device_label, "app_label": app_label,
                          "metronome_label": metronome_label, "placement_note": placement_note,
                          "amp_chain": amp_chain, "declared_by": "operator",
                          "placement_match_basis": "operator_declared_not_measured"},
        "distances": distance_block,
        "reference_definition": "source_emission",
        "listener_view": listener_component(distances, distance_method, room_temp_c) if in_bounds else
        {"status": "not_computed", "estimate_ms": None, "interval_ms": None, "direction_bearing": False,
         "basis": "distance out of bounds"},
        "components": {"acoustic_path": acoustic, "amp_chain": amp, "detector_bias": detector,
                       "attack_class_hull": hull, "residual": residual},
        "offset_correction_ms": offset,
        "decision_margin_ms": DECISION_MARGIN_MS,
        "abstain_rule": "expanded_uncertainty_ms > decision_margin_ms",
        "consistency_check": {"played_on_click": consistency},
        "click_grid": {**grid, "click_broadband_reference": measured["click_broadband_reference"],
                       "click_broadband_self_offset": _self_offset_summary(measured["click_broadband_self_offsets"])},
        "detector_identity": {"rhythm_sha256": producer["rhythm_sha256"], "rate": RATE, "hop": HOP,
                              "paths": ["high_frequency_novelty", "broadband_rms_novelty"]},
        "limitations": list(RECORD_LIMITATIONS),
        **copy.deepcopy(FIXED_UNKNOWNS),
    }
    return json.loads(json.dumps(record, allow_nan=False))


def _self_offset_summary(offsets: list[float]) -> dict:
    """Where the click itself appears on the broadband attack path, relative to the fitted grid (measured)."""
    values = sorted(value * 1000 for value in offsets)
    if len(values) < CLICK_SELF_MIN_EVENTS:
        return {"status": "not_detected_in_click_only_spans", "n": len(values), "median_ms": None, "iqr_ms": None,
                "coincidence_half_width_ms": CLICK_COINCIDENCE_HALF_WIDTH_MS}
    return {"status": "measured", "n": len(values), "median_ms": statistics.median(values),
            "iqr_ms": [_quantile(values, .25), _quantile(values, .75)],
            "coincidence_half_width_ms": CLICK_COINCIDENCE_HALF_WIDTH_MS}


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------------------------
# apply


def validate_record(record) -> None:
    def bad(message):
        raise Refusal("calibration_record_invalid", message)

    if not isinstance(record, dict):
        bad("record is not an object")
    if set(record) != RECORD_KEYS:
        bad(f"closed-schema key set differs: extra {sorted(set(record) - RECORD_KEYS)}, missing {sorted(RECORD_KEYS - set(record))}")
    if record["kind"] != RECORD_KIND or record["schema_version"] != SCHEMA_VERSION or record["tool"] != TOOL:
        bad("wrong kind, tool or schema version")
    if record["status"] not in ("calibrated", "abstained"):
        bad("unknown status")
    if not isinstance(record["abstain_reasons"], list) or any(r not in ABSTAIN_REASONS for r in record["abstain_reasons"]):
        bad("abstain reasons outside the closed enum")
    for key, value in FIXED_UNKNOWNS.items():
        if record[key] != value:
            bad(f"fixed unknown {key} altered")
    offset = record["offset_correction_ms"]
    if not isinstance(offset, dict) or set(offset) != OFFSET_KEYS:
        bad("offset_correction_ms key set differs")
    components = record["components"]
    if not isinstance(components, dict) or set(components) != set(COMPONENT_NAMES):
        bad("components key set differs")
    if record["decision_margin_ms"] != DECISION_MARGIN_MS:
        bad("decision margin differs from the preregistered 5.0 ms")
    if not isinstance(record.get("capture_setup"), dict) or not isinstance(record["capture_setup"].get("setup_id"), str):
        bad("capture_setup.setup_id missing")
    if not isinstance(record.get("detector_identity"), dict) or not isinstance(record["detector_identity"].get("rhythm_sha256"), str):
        bad("detector_identity.rhythm_sha256 missing")
    if record["status"] == "calibrated":
        if record["abstain_reasons"]:
            bad("calibrated record carries abstain reasons")
        for key in ("estimate", "expanded_uncertainty_ms"):
            value = offset[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                bad(f"offset_correction_ms.{key} is not a finite number")
        if offset["expanded_uncertainty_ms"] < 0 or offset["expanded_uncertainty_ms"] > DECISION_MARGIN_MS:
            bad("calibrated record's expanded uncertainty violates the abstain rule")
    elif offset["estimate"] is not None or offset["expanded_uncertainty_ms"] is not None:
        bad("abstained record carries numeric estimates")


def _check_phrase_timing(document) -> None:
    if (not isinstance(document, dict) or document.get("schema_version") != phrase_timing.SCHEMA_VERSION
            or document.get("tool") != "phrase_timing" or not isinstance(document.get("phrases"), list)):
        raise Refusal("phrase_timing_schema_unsupported", "phrase timing must be phrase_timing schema 2")


def calibrated_entry(entry: dict, correction: float, expanded: float, listener_ms: float | None,
                     click_self_ms: float | None = None) -> dict:
    block = {"basis_field": "median_offset_ms", "calibrated_median_offset_ms": None,
             "phrase_median_uncertainty_ms": None, "combined_uncertainty_ms": None,
             "direction_threshold_ms": None, "direction": None, "direction_status": "phrase_abstained",
             "listener_view_offset_ms": None, "withheld_basis": "source_phrase_abstained"}
    median, iqr, count = entry.get("median_offset_ms"), entry.get("iqr_width_ms"), entry.get("click_proximal_onset_count")
    if (entry.get("status") != "measured" or not isinstance(median, (int, float)) or not isinstance(iqr, (int, float))
            or not isinstance(count, int) or count < 1):
        return block
    if click_self_ms is not None and abs(median - click_self_ms) <= CLICK_COINCIDENCE_HALF_WIDTH_MS:
        # The onset median sits where the click itself appears on the attack path: the phrase-timing
        # nearest-onset rule may have measured the click, not the guitar. Withhold rather than guess.
        block["withheld_basis"] = "onset_median_coincides_with_click_self_detection"
        return block
    block["withheld_basis"] = None
    calibrated = median - correction
    u_median = PHRASE_MEDIAN_FACTOR * iqr / math.sqrt(count)
    combined = math.sqrt(expanded ** 2 + u_median ** 2)
    threshold = max(combined, DECISION_MARGIN_MS)
    if abs(calibrated) > threshold:
        direction, status = ("ahead_of_click" if calibrated < 0 else "behind_click"), "calibrated_direction"
    else:
        direction, status = "within_uncertainty", "within_uncertainty"
    block.update(calibrated_median_offset_ms=calibrated, phrase_median_uncertainty_ms=u_median,
                 combined_uncertainty_ms=combined, direction_threshold_ms=threshold, direction=direction,
                 direction_status=status,
                 listener_view_offset_ms=calibrated + listener_ms if listener_ms is not None else None)
    return block


def apply_view(phrase_timing_document, record, setup_id: str, *, phrase_timing_sha256: str | None = None,
               record_sha256: str | None = None, phrase_timing_path: str | None = None,
               record_path: str | None = None, run_id: str | None = None) -> dict:
    """Pure: calibrated phrase-timing view. Raises Refusal with a closed code; never mutates its inputs."""
    if record is None:
        raise Refusal("calibration_record_required", "a calibration record is required to emit any direction")
    validate_record(record)
    if record["status"] != "calibrated":
        raise Refusal("calibration_abstained", "the calibration record abstained: " + ", ".join(record["abstain_reasons"]))
    _check_phrase_timing(phrase_timing_document)
    producer = phrase_timing_document.get("producer") or {}
    if producer.get("rhythm_sha256") != record["detector_identity"]["rhythm_sha256"]:
        raise Refusal("detector_identity_mismatch", "phrase timing and calibration used different rhythm detectors")
    if setup_id != record["capture_setup"]["setup_id"]:
        raise Refusal("setup_id_mismatch", "setup id differs from the calibration record")
    source = copy.deepcopy(phrase_timing_document)
    offset = record["offset_correction_ms"]
    correction, expanded = offset["estimate"], offset["expanded_uncertainty_ms"]
    listener = record["listener_view"]
    listener_ms = listener["estimate_ms"] if listener.get("status") == "computed" else None
    click_self = (record.get("click_grid") or {}).get("click_broadband_self_offset") or {}
    click_self_ms = click_self.get("median_ms") if click_self.get("status") == "measured" else None
    phrases = []
    for entry in source["phrases"]:
        phrases.append({"source_entry": copy.deepcopy(entry),
                        "calibrated": calibrated_entry(entry, correction, expanded, listener_ms, click_self_ms)})
    counts = {key: sum(p["calibrated"]["direction_status"] == key for p in phrases)
              for key in ("calibrated_direction", "within_uncertainty", "phrase_abstained")}
    withheld = {key: sum(p["calibrated"]["withheld_basis"] == key for p in phrases) for key in WITHHELD_BASES}
    view = {
        "schema_version": SCHEMA_VERSION, "tool": TOOL, "kind": VIEW_KIND, "run_id": run_id or _run_id(),
        "producer": {**producer_hashes(), "phrase_timing_sha256": rhythm.file_hash(SCRIPTS / "phrase_timing.py")},
        "claims": {"measured": ["phrases[].source_entry (copied verbatim from the phrase-timing input)"],
                   "inferred": ["phrases[].calibrated.calibrated_median_offset_ms",
                                "phrases[].calibrated.combined_uncertainty_ms", "phrases[].calibrated.direction"],
                   "listening": []},
        "inputs": {"phrase_timing_path": phrase_timing_path,
                   "phrase_timing_sha256": phrase_timing_sha256 or canonical_sha256(phrase_timing_document),
                   "calibration_record_path": record_path,
                   "calibration_record_sha256": record_sha256 or canonical_sha256(record),
                   "setup_id": setup_id,
                   "analyzed_input_sha256": (source.get("inputs") or {}).get("analyzed_input_sha256")},
        "source_phrase_timing_unmodified": True,
        "calibration_consumed": {"offset_correction_ms": copy.deepcopy(offset),
                                 "decision_margin_ms": record["decision_margin_ms"],
                                 "calibration_run_id": record["run_id"],
                                 "reference_definition": record["reference_definition"],
                                 "listener_view_status": listener.get("status"),
                                 "click_broadband_self_offset_ms": click_self_ms},
        "direction_meaning": DIRECTION_MEANING,
        "rules": {"calibrated_median": "median_offset_ms - offset_correction_ms.estimate (raw detector-frame median; "
                                       "the synthetic-probe-compensated median is not used, so detector bias is not counted twice)",
                  "phrase_median_uncertainty": "1.858 * iqr_width_ms / sqrt(click_proximal_onset_count)",
                  "combined_uncertainty": "sqrt(expanded_calibration_uncertainty^2 + phrase_median_uncertainty^2)",
                  "direction_threshold": "max(combined_uncertainty, decision_margin_ms)",
                  "direction": "emitted only when |calibrated median| > direction threshold; else within_uncertainty",
                  "sign": "negative = ahead_of_click, positive = behind_click",
                  "click_coincidence_guard": ("phrase withheld (phrase_abstained, withheld_basis "
                                              "onset_median_coincides_with_click_self_detection) when |median_offset_ms - "
                                              "click broadband self-offset| <= 2.5 ms: the onset median may be the click itself")},
        "summary": {"phrase_count": len(phrases), "direction_status_counts": counts, "withheld_basis_counts": withheld,
                    "direction_counts": {key: sum(p["calibrated"]["direction"] == key for p in phrases)
                                         for key in ("ahead_of_click", "behind_click", "within_uncertainty")}},
        "phrases": phrases,
        "limitations": list(VIEW_LIMITATIONS),
        **copy.deepcopy(FIXED_UNKNOWNS),
        "real_take_status": source.get("real_take_status"),
        "click_identity": "unverified",
    }
    return json.loads(json.dumps(view, allow_nan=False))


# ---------------------------------------------------------------------------------------------
# Deterministic synthetic sessions and takes (tests and the sealed evaluation)

TUNING_MIDI = (24, 29, 34, 39, 46, 51, 56, 60, 65)
PERIOD_CHOICES = (60 / 178, .6757, 60 / 150)
DEV_NAMESPACE = "timing-calibration-s3-dev"
EVAL_NAMESPACE = "timing-calibration-s3-eval"
DEV_SEEDS = (11, 12, 13)
EVAL_SEEDS = tuple(range(5501, 5509))
EVAL_SEEDS_R2 = tuple(range(5601, 5609))  # newly preregistered after the R1 seal (spec section 11)


def knob(namespace: str, seed: int, arm: str, name: str) -> float:
    digest = hashlib.sha256(f"{namespace}:{seed}:{arm}:{name}".encode()).hexdigest()
    return int(digest[:16], 16) / 2 ** 64


def _rng(namespace: str, seed: int, arm: str, name: str) -> random.Random:
    return random.Random(int(hashlib.sha256(f"{namespace}:{seed}:{arm}:{name}".encode()).hexdigest()[:16], 16))


def case_params(namespace: str, seed: int) -> dict:
    k = lambda name: knob(namespace, seed, "case", name)  # noqa: E731
    temperature = 18 + 6 * k("room_temp_c")
    order = sorted(range(6), key=lambda i: k(f"phrase_order_{i}"))
    deltas = ([-2 + 4 * k("on_time_0"), -2 + 4 * k("on_time_1")]
              + [-30 + 22 * k("ahead_0"), -30 + 22 * k("ahead_1")]
              + [8 + 22 * k("behind_0"), 8 + 22 * k("behind_1")])
    return {"namespace": namespace, "seed": seed,
            "d_mic_metronome": .3 + 2.7 * k("d_mic_metronome"), "d_mic_amp": .3 + 2.7 * k("d_mic_amp"),
            "room_temp_c": temperature, "c_true": speed_of_sound(temperature),
            "period": PERIOD_CHOICES[min(2, int(3 * k("period")))],
            "click_model": "click_3500hz_exp" if seed % 2 else "mechanical_wood_click",
            "click_amplitude": .06 + .06 * k("click_amplitude"),
            "noise_amplitude": .004 + .008 * k("noise_amplitude"), "noise_ar": .55 + .30 * k("noise_ar"),
            "mu_player_s": (-40 + 50 * k("mu_player")) / 1000, "sigma_player_s": (4 + 8 * k("sigma_player")) / 1000,
            "session_sub_hop_samples": int(HOP * k("session_sub_hop")),
            "take_sub_hop_samples": int(HOP * k("take_sub_hop")),
            "take_deltas_s": [deltas[i] / 1000 for i in order]}


def distance_errors(namespace: str, seed: int) -> dict:
    return {"mic_to_metronome": -.25 + .5 * knob(namespace, seed, "E2", "d_mic_metronome_error"),
            "mic_to_amp": -.25 + .5 * knob(namespace, seed, "E2", "d_mic_amp_error")}


def _noise(length: int, amplitude: float, ar: float, rng: random.Random) -> list[float]:
    out, colored = [0.0] * length, 0.0
    for index in range(length):
        white = rng.uniform(-1, 1)
        colored = ar * colored + (1 - ar) * white
        out[index] = amplitude * (.5 * white + .5 * colored)
    return out


def _add(samples: list[float], start: int, waveform: list[float]) -> None:
    for j, value in enumerate(waveform):
        if 0 <= start + j < len(samples):
            samples[start + j] += value


def path_delay_samples(params: dict, amp_extra_m: float = 0.0) -> int:
    return round((params["d_mic_amp"] + amp_extra_m - params["d_mic_metronome"]) / params["c_true"] * RATE)


def synthetic_session(params: dict, *, open_midis=None, on_click_shift_s: float = 0.0,
                      noise_amplitude: float | None = None, noise_ar: float | None = None) -> tuple[list[float], dict, dict]:
    """Section-4 calibration clip: click only, offbeat palm, offbeat open, on-click palm, click only."""
    ns, seed = params["namespace"], params["seed"]
    rng = _rng(ns, seed, "case", "session_rng")
    period = params["period"]
    delta = path_delay_samples(params)
    lead = round(.5 * RATE) + params["session_sub_hop_samples"]
    n1, n5 = math.ceil(20 / period), math.ceil(10 / period)
    blocks = [("click_only", n1), (None, 2), ("offbeat_palm_muted", 32), (None, 2), ("offbeat_open", 64), (None, 2),
              ("on_click_palm_muted", 32), (None, 2), ("click_only", n5)]
    total = sum(n for _, n in blocks)
    length = round(lead + (total + 3) * period * RATE)
    amplitude = params["noise_amplitude"] if noise_amplitude is None else noise_amplitude
    samples = _noise(length, amplitude, params["noise_ar"] if noise_ar is None else noise_ar, rng)
    click_at = lambda b: lead + round(b * period * RATE)  # noqa: E731
    click_wave = click_waveform(params["click_model"], params["click_amplitude"], rng)
    for beat in range(total):
        _add(samples, click_at(beat), click_wave)
    segments, truth = [], {"path_delay_samples": delta, "clicks": [], "palm_muted_pick_attack": [],
                           "open_pick_attack": [], "on_click_emission_offsets_s": []}
    open_choices = tuple(open_midis) if open_midis else TUNING_MIDI
    beat = 0
    for kind, count in blocks:
        if kind is not None:
            segments.append({"kind": kind, "start_seconds": (click_at(beat) - .25 * period * RATE) / RATE,
                             "end_seconds": (click_at(beat + count) - .25 * period * RATE) / RATE,
                             "review_text": f"synthetic {kind} span (generator layout)"})
        if kind == "click_only":
            truth["clicks"].extend(click_at(b) / RATE for b in range(beat, beat + count))
        elif kind in ("offbeat_palm_muted", "offbeat_open"):
            step = 2 if kind == "offbeat_palm_muted" else 4
            for index, k in enumerate(range(0, count, step)):
                jitter = rng.gauss(0, params["sigma_player_s"])
                onset = click_at(beat + k) + round((period / 2 + jitter) * RATE) + delta
                if kind == "offbeat_palm_muted":
                    wave = attack_waveform("palm", 24, rng.uniform(2.6, 4.6), rng.uniform(.015, .040),
                                           .17 * rng.uniform(.65, 1.0), round(.25 * RATE), round(.006 * RATE))
                    truth["palm_muted_pick_attack"].append(onset / RATE)
                else:
                    midi = 24 if index == 0 else rng.choice(open_choices)
                    wave = attack_waveform("open", midi, rng.uniform(2.6, 4.6), rng.uniform(.25, .40),
                                           .17 * rng.uniform(.65, 1.0), round(2.5 * period * RATE), round(.010 * RATE))
                    truth["open_pick_attack"].append(onset / RATE)
                _add(samples, onset, wave)
        elif kind == "on_click_palm_muted":
            for k in range(0, count, 2):
                emission = params["mu_player_s"] + on_click_shift_s + rng.gauss(0, params["sigma_player_s"])
                onset = click_at(beat + k) + round(emission * RATE) + delta
                truth["on_click_emission_offsets_s"].append((onset - delta - click_at(beat + k)) / RATE)
                _add(samples, onset, attack_waveform("palm", 24, rng.uniform(2.6, 4.6), rng.uniform(.015, .040),
                                                     .17 * rng.uniform(.65, 1.0), round(.25 * RATE), round(.006 * RATE)))
        beat += count
    click_rms = math.sqrt(sum(v * v for v in click_wave) / len(click_wave))
    noise_rms = math.sqrt(statistics.mean(v * v for v in _noise(RATE, amplitude, params["noise_ar"] if noise_ar is None else noise_ar,
                                                                 random.Random(1))))
    truth["click_snr_db"] = 20 * math.log10(click_rms / noise_rms)
    return samples, {"schema_version": 1, "segments": segments}, truth


def synthetic_take(params: dict, *, amp_extra_m: float = 0.0, lead_beats: int = 2, phrase_beats: int = 8,
                   gap_beats: int = 4, jitter_s: float = .003) -> tuple[list[float], list[dict], list[float]]:
    """phrase_fixture layout: 8 click-aligned attacks at click + path + delta + N(0, 3 ms), 4 subdivisions, one masker."""
    ns, seed = params["namespace"], params["seed"]
    rng = _rng(ns, seed, "case", "take_rng")
    period, deltas = params["period"], params["take_deltas_s"]
    delta = path_delay_samples(params, amp_extra_m)
    total = lead_beats + len(deltas) * (phrase_beats + gap_beats)
    start = round(.3 * RATE) + params["take_sub_hop_samples"]
    length = round(start + (total * period + .6) * RATE)
    samples = _noise(length, params["noise_amplitude"], params["noise_ar"], rng)
    click_wave = click_waveform(params["click_model"], params["click_amplitude"], rng)
    clicks = [start + round(beat * period * RATE) for beat in range(total)]
    for sample in clicks:
        _add(samples, sample, click_wave)
    attacks, phrases, truths = [], [], []
    for number, offset in enumerate(deltas):
        first = lead_beats + number * (phrase_beats + gap_beats)
        masked = rng.randrange(phrase_beats)
        emissions = []
        for step in range(phrase_beats):
            click = clicks[first + step]
            onset = round(click + (offset + rng.gauss(0, jitter_s)) * RATE) + delta
            emissions.append((onset - delta - click) / RATE)
            attacks.append((onset, 1.6 if step == masked else 1.0))
        divisor = rng.choice((3, 2))
        for step in sorted(rng.sample(range(phrase_beats), 4)):
            attacks.append((clicks[first + step] + round(period / divisor * RATE) + delta, 1.0))
        phrases.append({"phrase_id": f"phrase-{number}", "label": f"generated phrase {number}",
                        "label_basis": "synthetic_fixture_span",
                        "span_source_seconds": [clicks[first] / RATE - period / 2,
                                                clicks[first + phrase_beats - 1] / RATE + period / 2]})
        truths.append(statistics.median(emissions))
    attacks.sort()
    for index, (onset, boost) in enumerate(attacks):
        following = attacks[index + 1][0] if index + 1 < len(attacks) else length
        extent = max(1, min(following - onset, round(.5 * RATE), length - onset))
        open_note = rng.random() < .5
        midi = rng.choice(TUNING_MIDI)
        tau = rng.uniform(.25, .40) if open_note else rng.uniform(.015, .040)
        _add(samples, onset, attack_waveform("open" if open_note else "palm", midi, rng.uniform(2.6, 4.6), tau,
                                             .17 * rng.uniform(.65, 1.0) * boost, extent, round(.006 * RATE)))
    return samples, phrases, truths


def synthetic_phrase_timing(samples, phrases) -> dict:
    """rhythm.analyze -> phrase_timing.measure(synthetic_fixture) with run()-equivalent producer/inputs blocks."""
    analysis = rhythm.analyze(samples)
    sha = samples_sha256(samples)
    analysis["source"] = {"sha256": sha}
    result = phrase_timing.measure(analysis, phrases, phrase_basis="synthetic_fixture_span", run_kind="synthetic_fixture")
    result["inputs"] = {"analyzed_input_sha256": sha, "analysis_path": None, "phrases_path": None}
    result["producer"] = {"phrase_timing_sha256": rhythm.file_hash(SCRIPTS / "phrase_timing.py"),
                          "rhythm_sha256": rhythm.file_hash(SCRIPTS / "rhythm.py")}
    result["run_id"] = "synthetic"
    return result


def true_distances(params: dict) -> str:
    return f"mic_to_metronome={params['d_mic_metronome']!r},mic_to_amp={params['d_mic_amp']!r}"


def score_view(view: dict, truths: list[float]) -> list[dict]:
    rows = []
    for phrase, truth in zip(view["phrases"], truths):
        cal = phrase["calibrated"]
        estimate = cal["calibrated_median_offset_ms"]
        truth_ms = truth * 1000
        rows.append({"truth_ms": truth_ms, "calibrated_ms": estimate,
                     "abs_error_ms": abs(estimate - truth_ms) if estimate is not None else None,
                     "covered": (abs(estimate - truth_ms) <= cal["combined_uncertainty_ms"]) if estimate is not None else None,
                     "direction": cal["direction"], "direction_status": cal["direction_status"],
                     "withheld_basis": cal["withheld_basis"]})
    return rows


def _median_with_inf(values: list[float | None]) -> float | str:
    """Median with abstentions as +inf; an infinite median is reported as the string 'inf' (JSON-safe)."""
    median = statistics.median([math.inf if v is None else v for v in values]) if values else math.inf
    return "inf" if math.isinf(median) else median


def _case_record(params: dict, samples, segments, arm: str) -> dict:
    if arm == "E2":
        errors = distance_errors(params["namespace"], params["seed"])
        distances = {"mic_to_metronome": params["d_mic_metronome"] + errors["mic_to_metronome"],
                     "mic_to_amp": params["d_mic_amp"] + errors["mic_to_amp"]}
        return analyze_samples(samples, segments, distances=distances, distance_method="estimated",
                               setup_id="synthetic", run_id=f"{arm}-{params['seed']}")
    distances = {"mic_to_metronome": params["d_mic_metronome"], "mic_to_amp": params["d_mic_amp"]}
    return analyze_samples(samples, segments, distances=distances, distance_method="measured", room_temp_c=21.0,
                           setup_id="synthetic", run_id=f"{arm}-{params['seed']}")


def _case_result(params: dict, arm: str, truth: dict, record: dict, timing: dict, truths: list[float]) -> dict:
    offset = record["offset_correction_ms"]
    case = {"seed": params["seed"], "arm": arm, "period": params["period"], "click_model": params["click_model"],
            "path_delay_ms_true": truth["path_delay_samples"] / RATE * 1000,
            "record_status": record["status"], "abstain_reasons": record["abstain_reasons"],
            "offset_estimate_ms": offset["estimate"], "expanded_uncertainty_ms": offset["expanded_uncertainty_ms"],
            "attempted_estimate_ms": offset["attempted_estimate"],
            "attempted_expanded_uncertainty_ms": offset["attempted_expanded_uncertainty_ms"],
            "consistency": record["consistency_check"]["played_on_click"]["status"],
            "phrase_timing_abstained": sum(p["status"] != "measured" for p in timing["phrases"]),
            "phrases": []}
    if record["status"] == "calibrated":
        case["phrases"] = score_view(apply_view(timing, record, "synthetic"), truths)
    else:
        case["phrases"] = [{"truth_ms": t * 1000, "calibrated_ms": None, "abs_error_ms": None, "covered": None,
                            "direction": None, "direction_status": "calibration_abstained"} for t in truths]
    return case


def run_seed(params: dict, arms=("E1", "E2", "E3")) -> dict:
    """Evaluation cases for one seed: E1 measured, E2 estimated distances, E3 = E1 record on a moved-amp take."""
    samples, segments, truth = synthetic_session(params)
    records = {arm: _case_record(params, samples, segments, arm) for arm in set(arms) & {"E1", "E2"}}
    if "E3" in arms and "E1" not in records:
        records["E1"] = _case_record(params, samples, segments, "E1")
    out = {}
    if {"E1", "E2"} & set(arms):
        take, phrases, truths = synthetic_take(params)
        timing = synthetic_phrase_timing(take, phrases)
        for arm in ("E1", "E2"):
            if arm in arms:
                out[arm] = _case_result(params, arm, truth, records[arm], timing, truths)
    if "E3" in arms:
        take, phrases, truths = synthetic_take(params, amp_extra_m=1.5)
        timing = synthetic_phrase_timing(take, phrases)
        out["E3"] = _case_result(params, "E3", truth, records["E1"], timing, truths)
    return out


def summarize_arm(cases: list[dict]) -> dict:
    rows = [row for case in cases for row in case["phrases"]]
    measured = [row for row in rows if row["calibrated_ms"] is not None]
    emitted = [row for row in measured if row["direction"] in ("ahead_of_click", "behind_click")]
    correct = [row for row in emitted if (row["direction"] == "ahead_of_click") == (row["truth_ms"] < 0)]
    on_time = [row for row in rows if abs(row["truth_ms"]) <= 2.0]
    large = [row for row in rows if abs(row["truth_ms"]) >= 15.0]
    return {"case_count": len(cases), "calibrated_case_count": sum(c["record_status"] == "calibrated" for c in cases),
            "abstained_case_count": sum(c["record_status"] != "calibrated" for c in cases),
            "phrase_count": len(rows), "measured_phrase_count": len(measured),
            "median_abs_error_ms_inf_for_abstained": _median_with_inf([row["abs_error_ms"] for row in rows]),
            "median_abs_error_ms_measured_only": statistics.median(r["abs_error_ms"] for r in measured) if measured else None,
            "coverage": {"covered": sum(bool(r["covered"]) for r in measured), "denominator": len(measured)},
            "direction": {"emitted": len(emitted), "sign_correct": len(correct),
                          "on_time_phrases": len(on_time),
                          "emissions_on_on_time": sum(r["direction"] in ("ahead_of_click", "behind_click") for r in on_time),
                          "large_offset_phrases": len(large),
                          "emissions_on_large": sum(r["direction"] in ("ahead_of_click", "behind_click") for r in large)},
            "wrong_sign_count": len(emitted) - len(correct)}


def sealed_evaluation(seeds=EVAL_SEEDS, namespace: str = EVAL_NAMESPACE) -> dict:
    arms = {"E1": [], "E2": [], "E3": []}
    for seed in seeds:
        cases = run_seed(case_params(namespace, seed))
        for arm in arms:
            arms[arm].append(cases[arm])
    return {"namespace": namespace, "seeds": list(seeds), "cases": arms,
            "summary": {arm: summarize_arm(cases) for arm, cases in arms.items()}}


# ---------------------------------------------------------------------------------------------
# CLI


def _under_accepted_runs(path: Path) -> bool:
    parts = path.expanduser().resolve().parts
    return any(parts[index:index + 2] == ("artifacts", "runs") for index in range(len(parts) - 1))


def _safe_json_path(raw: str, code: str) -> Path:
    if "://" in raw or ".." in Path(raw).parts:
        raise Refusal(code, "URL or traversal components are not allowed")
    path = Path(raw).expanduser()
    if path.is_symlink():
        raise Refusal(code, "a symlinked input file is not allowed")
    if path.suffix.lower() != ".json" or not path.is_file():
        raise Refusal(code, "a regular .json file is required")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise Refusal(code, "JSON exceeds the 64 MiB bound")
    return path.resolve()


def _read_json(path: Path, code: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Refusal(code, f"unreadable JSON: {exc}") from exc


def _resolve_input(raw: str) -> tuple[Path, dict, Path | None]:
    path = Path(raw).expanduser()
    if "://" in raw or not path.exists():
        raise Refusal("input_invalid", "input must be an existing local file or run directory")
    if path.is_dir():
        audio, manifest = path / "denoised.wav", path / "manifest.json"
        if not audio.is_file() or not manifest.is_file():
            raise Refusal("input_invalid", "run directory needs denoised.wav and manifest.json")
        if manifest.stat().st_size > 2 * 1024 * 1024:
            raise Refusal("input_invalid", "manifest exceeds 2 MiB")
        document = _read_json(manifest, "input_invalid")
        profile = document.get("profile") if isinstance(document, dict) else None
        info = {"kind": "run_dir", "path": str(audio.resolve()), "sha256": rhythm.file_hash(audio),
                "signal_chain": "run_denoised",
                "profile_id": profile.get("name") if isinstance(profile, dict) else None,
                "manifest_sha256": rhythm.file_hash(manifest)}
        return audio.resolve(), info, path.resolve()
    if path.suffix.lower() not in (".wav", ".mov", ".m4a", ".mp4"):
        raise Refusal("input_invalid", "input file must be WAV, MOV, M4A or MP4")
    return path.resolve(), {"kind": "file", "path": str(path.resolve()), "sha256": rhythm.file_hash(path),
                            "signal_chain": "source_audio", "profile_id": None, "manifest_sha256": None}, None


class _Deadline(Exception):
    pass


def _deadline_handler(signum, frame):
    raise _Deadline("analysis exceeded its timeout")


def command_analyze(args) -> Path:
    output_root = Path(args.output_root)
    if _under_accepted_runs(output_root):
        raise Refusal("output_under_accepted_runs", "output may not be written under artifacts/runs")
    source, info, run_dir = _resolve_input(args.input)
    segments_path = _safe_json_path(args.segments, "segments_invalid")
    segments = _read_json(segments_path, "segments_invalid")
    distances = parse_distances(args.distances)
    metadata = rhythm.probe(source)
    start, lineage = rhythm.input_timeline(source, info["sha256"], metadata, run_dir)
    info["timeline_lineage_status"] = lineage["status"]
    info["segments_sha256"] = rhythm.file_hash(segments_path)
    decode_error = None
    try:
        samples = rhythm.decode(source)
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        samples, decode_error = array.array("f"), str(exc)[-500:]
    if len(samples) / RATE > MAX_AUDIO_SECONDS:
        raise Refusal("audio_too_long", "calibration audio exceeds 600 s")
    record = analyze_samples(samples, segments, distances=distances, distance_method=args.distance_method,
                             setup_id=args.setup_id, amp_chain=args.amp_chain, room_temp_c=args.room_temp_c,
                             device_label=args.device_label, app_label=args.app_label,
                             metronome_label=args.metronome_label, placement_note=args.placement_note,
                             audio_start_seconds=start, input_info=info, decode_error=decode_error)
    if rhythm.file_hash(source) != info["sha256"]:
        raise RuntimeError("input changed during analysis; nothing written")
    destination = output_root.expanduser().resolve() / "records" / record["run_id"]
    destination.mkdir(parents=True, exist_ok=False)
    path = destination / "calibration-record.json"
    rhythm.atomic_write(path, json.dumps(record, indent=2, allow_nan=False) + "\n")
    return path


def command_apply(args) -> Path:
    output_root = Path(args.output_root)
    if _under_accepted_runs(output_root):
        raise Refusal("output_under_accepted_runs", "output may not be written under artifacts/runs")
    try:
        record_path = _safe_json_path(args.calibration, "calibration_record_required")
    except Refusal as exc:
        raise Refusal("calibration_record_required", str(exc)) from exc
    record = _read_json(record_path, "calibration_record_required")
    timing_path = _safe_json_path(args.phrase_timing, "phrase_timing_schema_unsupported")
    timing = _read_json(timing_path, "phrase_timing_schema_unsupported")
    timing_hash, record_hash = rhythm.file_hash(timing_path), rhythm.file_hash(record_path)
    view = apply_view(timing, record, args.setup_id, phrase_timing_sha256=timing_hash, record_sha256=record_hash,
                      phrase_timing_path=str(timing_path), record_path=str(record_path))
    destination = output_root.expanduser().resolve() / "views" / view["run_id"]
    destination.mkdir(parents=True, exist_ok=False)
    path = destination / "phrase-timing-calibrated.json"
    rhythm.atomic_write(path, json.dumps(view, indent=2, allow_nan=False) + "\n")
    if rhythm.file_hash(timing_path) != timing_hash or rhythm.file_hash(record_path) != record_hash:
        path.unlink(missing_ok=True)
        raise RuntimeError("an input changed while the view was written; output removed")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze", help="calibration clip -> calibration-record.json")
    analyze.add_argument("input", help="calibration clip (WAV/MOV/M4A/MP4) or run dir with denoised.wav + manifest.json")
    analyze.add_argument("--segments", required=True, help="operator-reviewed SEG.json")
    analyze.add_argument("--distances", required=True,
                         help="mic_to_metronome=M,mic_to_amp=M[,ear_to_metronome=M,ear_to_amp=M] in metres")
    analyze.add_argument("--distance-method", required=True, choices=("measured", "estimated"))
    analyze.add_argument("--room-temp-c", type=float)
    analyze.add_argument("--amp-chain", required=True, help="analog | declared:MS | unknown")
    analyze.add_argument("--setup-id", required=True)
    for name in ("--device-label", "--app-label", "--metronome-label", "--placement-note"):
        analyze.add_argument(name)
    analyze.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    apply = sub.add_parser("apply", help="phrase-timing.json + calibration record -> phrase-timing-calibrated.json")
    apply.add_argument("--phrase-timing", required=True)
    apply.add_argument("--calibration", required=True)
    apply.add_argument("--setup-id", required=True)
    apply.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    previous = None
    if args.command == "analyze" and hasattr(signal, "SIGALRM"):
        previous = signal.signal(signal.SIGALRM, _deadline_handler)
        signal.alarm(ANALYZE_TIMEOUT_SECONDS)
    try:
        path = command_analyze(args) if args.command == "analyze" else command_apply(args)
        document = json.loads(path.read_text(encoding="utf-8"))
        brief = ({"calibration_record": str(path), "status": document["status"],
                  "abstain_reasons": document["abstain_reasons"],
                  "offset_correction_ms": document["offset_correction_ms"]}
                 if args.command == "analyze" else
                 {"calibrated_view": str(path), "summary": document["summary"]})
        print(json.dumps(brief))
        return 0
    except Refusal as exc:
        print(json.dumps({"refusal": exc.code, "message": str(exc)}), file=sys.stderr)
        return 2
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired, _Deadline) as exc:
        print(f"timing_calibration: {exc}", file=sys.stderr)
        return 1
    finally:
        if previous is not None:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)


if __name__ == "__main__":
    raise SystemExit(main())
