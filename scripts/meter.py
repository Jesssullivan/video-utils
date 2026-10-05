#!/usr/bin/env python3
"""Bounded, source-bound accent-cycle hypotheses; notation can remain unknown."""
from __future__ import annotations

import argparse
import bisect
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys

from dag import load, number, sha256

PERIODS = (2, 3, 4, 5, 6, 7, 8, 9, 10, 12)
LIMITS = {"maximum_feature_frames": 36001, "maximum_pulses": 14400,
          "minimum_cycles": 4, "maximum_local_windows": 96}
THRESHOLDS = {"minimum_explained_variance": .55, "minimum_holdout_similarity": .8,
              "minimum_rank_margin": .04, "minimum_accent_range": 1e-4}


def rank_accents(values: list[float]) -> dict:
    """Rank cyclic means, validating alternating complete cycles independently."""
    if not isinstance(values, list) or len(values) > LIMITS["maximum_pulses"]:
        raise ValueError("Accent sequence exceeds pulse bounds")
    values = [number(value, "accent value") for value in values]
    if len(values) < 12:
        return {"status": "unknown", "reason": "insufficient_pulses", "selected": None, "candidates": []}
    if max(values) - min(values) < THRESHOLDS["minimum_accent_range"]:
        return {"status": "unknown", "reason": "uniform_or_continuous_energy", "selected": None, "candidates": []}
    candidates = []
    for period in PERIODS:
        cycles = len(values) // period
        if cycles < LIMITS["minimum_cycles"]:
            continue
        observations = values[:cycles * period]
        center = statistics.mean(observations)
        total = sum((value - center) ** 2 for value in observations)
        template = [statistics.mean(observations[position::period]) for position in range(period)]
        residual = sum((value - template[index % period]) ** 2 for index, value in enumerate(observations))
        explained = max(0., 1 - residual / max(total, 1e-20))
        even = [statistics.mean(observations[c * period + k] for c in range(0, cycles, 2)) for k in range(period)]
        odd = [statistics.mean(observations[c * period + k] for c in range(1, cycles, 2)) for k in range(period)]
        a, b = statistics.mean(even), statistics.mean(odd)
        norm = math.sqrt(sum((v-a)**2 for v in even) * sum((v-b)**2 for v in odd))
        similarity = sum((x-a)*(y-b) for x, y in zip(even, odd)) / norm if norm > 1e-20 else 0.
        similarity = max(-1., min(1., similarity))
        score = explained * max(0., similarity) - .01 * (period - 2)
        candidates.append({"cycle_pulses": period, "complete_cycles": cycles,
                           "explained_variance": explained, "holdout_similarity": similarity,
                           "ranking_score": score, "score_kind": "heuristic_not_probability",
                           "accent_means": template, "strongest_accent_position": max(range(period), key=template.__getitem__)})
    candidates.sort(key=lambda item: (-item["ranking_score"], item["cycle_pulses"]))
    selected = None
    reason = "weak_or_conflicting_accent_cycles"
    if candidates:
        best = candidates[0]
        # Nested multiples describe the same primitive cycle, not independent alternatives.
        rivals = [item for item in candidates[1:] if item["cycle_pulses"] % best["cycle_pulses"] != 0]
        margin = best["ranking_score"] - (rivals[0]["ranking_score"] if rivals else 0.)
        if (best["explained_variance"] >= THRESHOLDS["minimum_explained_variance"]
                and best["holdout_similarity"] >= THRESHOLDS["minimum_holdout_similarity"]
                and margin >= THRESHOLDS["minimum_rank_margin"]):
            selected = best
            reason = "repeatable_accent_cycle_not_confirmed_meter"
    return {"status": "accent_cycle_hypothesis" if selected else "unknown", "reason": reason,
            "selected": selected, "candidates": candidates}


def read_features(analysis: dict) -> tuple[list[float], list[float]]:
    features = (analysis.get("librosa") or {}).get("features") or {}
    if not features:
        return [], []
    if features.get("matrix_layout") != "feature_by_frame":
        raise ValueError("Expected feature_by_frame features")
    times, matrix = features.get("frame_times_audio_relative_seconds"), features.get("mfcc")
    if not isinstance(times, list) or not 4 <= len(times) <= LIMITS["maximum_feature_frames"]:
        raise ValueError("Feature frame count is outside bounds")
    if not isinstance(matrix, list) or len(matrix) != 13 or any(not isinstance(row, list) or len(row) != len(times) for row in matrix):
        raise ValueError("Expected aligned 13-row MFCC matrix")
    times = [number(value, "feature time", 0) for value in times]
    if any(a >= b for a, b in zip(times, times[1:])) or times[-1] > 1800:
        raise ValueError("Feature times must increase within 1800 seconds")
    energy = [number(value, "MFCC0 energy proxy") for value in matrix[0]]
    # Validate ignored rows too: malformed evidence must not be accepted silently.
    for row in matrix[1:]:
        for value in row:
            number(value, "MFCC value")
    return times, energy


def aggregate_pulses(times: list[float], energy: list[float], period: float, phase: float) -> tuple[list[float], list[float]]:
    first = phase + math.ceil(-phase / period) * period
    pulse_times, accents = [], []
    time = first
    while time + period <= times[-1] + 1e-9:
        left, right = bisect.bisect_left(times, time), bisect.bisect_left(times, time + period)
        if right == left:
            raise ValueError("Pulse resolution is finer than feature frame spacing")
        pulse_times.append(time)
        accents.append(statistics.mean(energy[left:right]))
        if len(accents) > LIMITS["maximum_pulses"]:
            raise ValueError("Pulse count exceeds bounds")
        time += period
    return pulse_times, accents


def infer(analysis: dict) -> dict:
    times, energy = read_features(analysis)
    result = {"schema_version": 1, "status": "unknown", "time_signature": None,
              "confidence_kind": "heuristic_not_probability", "aliases": [], "local_windows": [],
              "evidence": "existing_MFCC0_mean_per_pulse_energy_proxy_not_instrument_specific",
              "limits": LIMITS, "thresholds": THRESHOLDS,
              "limitations": ["Repeated energy accents are not notated meter or verified downbeats.",
                              "A uniform metronome establishes pulse, not beats per bar; an accented click can mimic meter.",
                              "MFCC energy includes guitar and click; compressed distortion may hide intended accents.",
                              "Seven-unit riffs, tuplets and cross-rhythms can resemble additive meter.",
                              "Tapping, sweeps and legato can lack discrete attacks; no error grading follows.",
                              "Quarter/eighth pulse units and additive groupings are not established."]}
    grid = analysis.get("click_grid")
    if not times or not isinstance(grid, dict):
        result["reason"] = "missing_comparative_features_or_pulse_grid"
        return result
    period = number(grid.get("period_seconds"), "grid period", .15)
    if period > 3:
        raise ValueError("Grid period must be between .15 and 3 seconds")
    phase = number(grid.get("phase_seconds_audio_relative"), "grid phase")
    if abs(phase) > times[-1] + period:
        raise ValueError("Grid phase lies outside the recording extent")
    start = number((analysis.get("timeline") or {}).get("audio_stream_start_seconds", 0), "source timeline start")
    signatures = {2: "2/4", 3: "3/4", 4: "4/4", 5: "5/4", 6: "6/8", 7: "7/8", 8: "8/8", 9: "9/8", 10: "10/8", 12: "12/8"}
    for factor in (.5, 1., 2.):
        pulse_times, accents = aggregate_pulses(times, energy, period * factor, phase)
        ranking = rank_accents(accents)
        for candidate in ranking["candidates"]:
            n = candidate["cycle_pulses"]
            candidate.update(cycle_seconds=n*period*factor,
                             notation_hypothesis=signatures[n],
                             notation_assumption="quarter pulse for 2..5; eighth pulse for 6..12; neither inferred",
                             additive_grouping=None)
        alias = {"pulse_period_seconds": period*factor, "pulse_bpm": 60/(period*factor),
                 "factor_relative_to_fitted_pulse": factor, "pulse_count": len(accents), **ranking}
        selected = alias["selected"]
        if selected:
            origin = pulse_times[selected["strongest_accent_position"]]
            alias["accent_cycle_start_source_seconds"] = start + origin
            result["status"] = "accent_cycle_hypotheses_not_confirmed_meter"
        result["aliases"].append(alias)
        if factor != 1:
            continue
        for offset in range(0, max(0, len(accents) - 83), 42):
            if len(result["local_windows"]) >= LIMITS["maximum_local_windows"]:
                break
            local = rank_accents(accents[offset:offset+84])
            result["local_windows"].append({"source_start_seconds": start+pulse_times[offset],
                "source_end_seconds": start+pulse_times[offset+83]+period, "status": local["status"],
                "cycle_pulses": local["selected"]["cycle_pulses"] if local["selected"] else None})
    local_cycles = {item["cycle_pulses"] for item in result["local_windows"] if item["cycle_pulses"] is not None}
    result["local_structure"] = "mixed_or_nonstationary_accent_evidence" if len(local_cycles) > 1 else "unknown_or_stationary_accent_evidence"
    result["reason"] = "notation_and_instrument_identity_unresolved"
    return result


def analyze_run(run_dir: Path) -> dict:
    analysis_path = run_dir / "analysis.json"
    analysis_hash = sha256(analysis_path)
    analysis = load(analysis_path)
    manifest_path = run_dir / "manifest.json"
    manifest_hash = sha256(manifest_path)
    manifest = load(manifest_path)
    source = analysis.get("source") or {}
    input_path = Path(source.get("path", ""))
    if input_path.resolve().parent != run_dir.resolve() or input_path.name not in ("source.wav", "denoised.wav", "cleaned.wav"):
        raise ValueError("Meter worker requires a run-local media derivative")
    actual = sha256(input_path)
    if source.get("sha256") != actual or (manifest.get("output_sha256") or {}).get(input_path.name) != actual:
        raise ValueError("Analyzed media hash differs from source or manifest")
    lineage = analysis.get("source_lineage") or {}
    original_hash = (manifest.get("source") or {}).get("sha256")
    if (lineage.get("status") != "hash_bound_run_derivative" or lineage.get("manifest_sha256") != manifest_hash
            or lineage.get("original_source_sha256") != original_hash or lineage.get("analyzed_input_sha256") != actual):
        raise ValueError("Analysis source lineage does not match the run")
    if not isinstance(original_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", original_hash):
        raise ValueError("Invalid original recording hash")
    timeline, mapping = manifest.get("timeline") or {}, lineage.get("sample_mapping") or {}
    origin = number(timeline.get("audio_start_seconds"), "manifest audio start")
    analysis_origin = number((analysis.get("timeline") or {}).get("audio_stream_start_seconds"), "analysis audio start")
    lineage_origin = number(lineage.get("original_audio_start_seconds"), "lineage audio start")
    if (abs(origin-analysis_origin) > 1e-9 or abs(origin-lineage_origin) > 1e-9
            or timeline.get("no_time_stretch") is not True or mapping.get("no_time_stretch") is not True):
        raise ValueError("Source timeline or no-stretch provenance differs from the run")
    result = infer(analysis)
    if sha256(analysis_path) != analysis_hash or sha256(manifest_path) != manifest_hash or sha256(input_path) != actual:
        raise ValueError("Inputs changed during inference")
    result["provenance"] = {"analysis_sha256": analysis_hash, "manifest_sha256": manifest_hash,
                            "analyzed_input_sha256": actual, "original_source_sha256": original_hash,
                            "timeline": analysis.get("timeline"), "no_media_changes": True}
    result["provenance"]["original_recording"] = "manifest_identity_preserved_not_reopened"
    result["declared_tempo"] = analysis.get("declared_tempo")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        run_dir = args.run_dir.expanduser().resolve(strict=True)
        result = analyze_run(run_dir)
        # Exclusive creation preserves earlier evidence instead of replacing a shared result.
        tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output_dir = run_dir / "meter" / tag
        output_dir.mkdir(parents=True, exist_ok=False)
        target = output_dir / "meter.json"
        with target.open("x", encoding="utf-8") as handle:
            os.chmod(target, 0o600)
            json.dump(result, handle, indent=2, allow_nan=False)
            handle.write("\n")
        print(json.dumps({"status": result["status"], "output": str(target), "sha256": sha256(target)}))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
