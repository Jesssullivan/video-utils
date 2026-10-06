#!/usr/bin/env python3
"""Preregistered cached-feature pulse experiment; no canonical processing writes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
PLAN = Path(__file__).with_name("2026-10-06-joint-pulse-ranking-plan.md")
ANALYSIS = ROOT/"artifacts/runs/20261005T232741Z-2b5dc43fd009/analysis.json"
SETTINGS = {"pulse_factors": [.5, 1.], "subdivisions": [1, 2, 3],
    "proxies": ["spectral_flux_attack_candidate", "superflux_attack_candidate"],
    "phase_bins": 64, "alignment_tolerance_seconds": .015, "local_window_seconds": 8.,
    "minimum_events": 12, "minimum_support": .65, "minimum_slot_coverage": .5,
    "minimum_populated_windows": 3, "minimum_local_pass_fraction": .8,
    "maximum_proxy_phase_difference_seconds": .005, "minimum_family_score_margin": .1,
    "maximum_events": 20000, "maximum_duration_seconds": 1800, "actual_variants": 12,
    "expected_bpm_used_to_fit": False, "audio_decoded": False}


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write(path, value):
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def wrapped(value, interval):
    return value-round(value/interval)*interval


def measure(events, interval, duration):
    tolerance = SETTINGS["alignment_tolerance_seconds"]
    best = None
    for index in range(SETTINGS["phase_bins"]):
        phase = interval*index/SETTINGS["phase_bins"]
        residuals = [wrapped(value-phase, interval) for value in events]
        aligned = [value for value in residuals if abs(value) <= tolerance]
        key = (len(aligned), -statistics.median(abs(value) for value in residuals) if residuals else 0, -index)
        if best is None or key > best[0]:
            best = (key, phase, aligned)
    phase = (best[1]+(statistics.median(best[2]) if best[2] else 0)) % interval
    residuals = [wrapped(value-phase, interval) for value in events]
    aligned = [value for value in residuals if abs(value) <= tolerance]
    support = len(aligned)/len(events) if events else 0.
    slots = {round((value-phase)/interval) for value, residual in zip(events, residuals) if abs(residual)<=tolerance}
    possible = max(1, math.floor((duration-phase)/interval)+1)
    coverage = min(1., len(slots)/possible)
    chance = min(1., 2*tolerance/interval)
    score = max(0., (support-chance)/max(1e-9, 1-chance))*coverage
    windows = []
    for left in range(0, math.ceil(duration), int(SETTINGS["local_window_seconds"])):
        selected = [residual for value, residual in zip(events, residuals) if left<=value<min(duration,left+8)]
        if len(selected) >= SETTINGS["minimum_events"]:
            windows.append({"start_seconds": left, "event_count": len(selected),
                "support_fraction": sum(abs(value)<=tolerance for value in selected)/len(selected)})
    passes = sum(window["support_fraction"]>=SETTINGS["minimum_support"] for window in windows)
    reasons = []
    if len(events)<SETTINGS["minimum_events"]:
        reasons.append("insufficient_events")
    if support<SETTINGS["minimum_support"]:
        reasons.append("weak_global_alignment")
    if coverage<SETTINGS["minimum_slot_coverage"]:
        reasons.append("sparse_grid_coverage")
    if len(windows)<SETTINGS["minimum_populated_windows"]:
        reasons.append("insufficient_local_windows")
    elif passes/len(windows)<SETTINGS["minimum_local_pass_fraction"]:
        reasons.append("inconsistent_local_subdivision_evidence")
    return {"grid_interval_seconds": interval, "fitted_phase_seconds_modulo_interval": phase,
        "event_count": len(events), "support_fraction": support, "occupied_slot_fraction": coverage,
        "random_phase_opportunity": chance, "ranking_score": score,
        "score_kind": "heuristic_not_probability", "median_absolute_residual_ms": 1000*statistics.median(abs(value) for value in residuals) if residuals else None,
        "local_windows": windows, "status": "physical_grid_hypothesis" if not reasons else "unknown",
        "unknown_reasons": reasons}


def rank(proxies, fitted_period, duration):
    variants = []
    for factor in SETTINGS["pulse_factors"]:
        for subdivision in SETTINGS["subdivisions"]:
            for name in SETTINGS["proxies"]:
                result = measure(proxies[name], fitted_period*factor/subdivision, duration)
                result.update(proxy=name, pulse_factor=factor, pulse_bpm=60/(fitted_period*factor), subdivision_hypothesis=subdivision)
                variants.append(result)
    families = []
    for item in variants:
        if item["status"] != "physical_grid_hypothesis":
            continue
        peer = next(value for value in variants if value["pulse_factor"]==item["pulse_factor"]
            and value["subdivision_hypothesis"]==item["subdivision_hypothesis"] and value["proxy"]!=item["proxy"])
        if peer["status"] != "physical_grid_hypothesis":
            continue
        if abs(wrapped(item["fitted_phase_seconds_modulo_interval"]-peer["fitted_phase_seconds_modulo_interval"], item["grid_interval_seconds"])) > SETTINGS["maximum_proxy_phase_difference_seconds"]:
            continue
        existing = next((group for group in families if abs(group["grid_interval_seconds"]-item["grid_interval_seconds"])<1e-9), None)
        representation = {"pulse_bpm": item["pulse_bpm"], "subdivision_hypothesis": item["subdivision_hypothesis"]}
        if existing is None:
            existing = {"grid_interval_seconds": item["grid_interval_seconds"],
                "ranking_score": min(item["ranking_score"], peer["ranking_score"]), "representations": []}
            families.append(existing)
        if representation not in existing["representations"]:
            existing["representations"].append(representation)
    families.sort(key=lambda value: -value["ranking_score"])
    selected = None
    reason = "no_cross_proxy_stable_grid"
    if families:
        margin = families[0]["ranking_score"]-(families[1]["ranking_score"] if len(families)>1 else 0)
        if margin>=SETTINGS["minimum_family_score_margin"]:
            selected = families[0]
            reason = "pulse_level_alias_ambiguity" if len(selected["representations"])>1 else "event_grid_does_not_establish_musical_pulse"
        else:
            reason = "competing_physical_grid_families"
    return {"variants": variants, "physical_grid_families": families, "selected_physical_grid": selected,
        "pulse_bpm": None, "time_signature": None, "intended_subdivision": None, "performance_issue_confirmed": False,
        "unknown_reason": reason, "identity": "mixture_attacks_not_click_or_guitar_identity"}


def controls():
    period, duration = .674, 32.
    uniform = [.036+n*period/2 for n in range(math.floor((duration-.036)/(period/2)))]
    alternating = []
    for left, right, subdivision in ((0,16,2),(16,32,3)):
        alternating += [.036+left+n*period/subdivision for n in range(math.floor((right-left-.036)/(period/subdivision)))]
    rng = random.Random(104206)
    jitter = sorted(rng.uniform(0,duration) for _ in range(90))
    result = {}
    for name, events in (("uniform_delayed", uniform), ("alternating_duplet_triplet", alternating), ("irregular_jitter", jitter)):
        prediction = rank({proxy: events for proxy in SETTINGS["proxies"]}, period, duration)
        result[name] = prediction
    assert result["uniform_delayed"]["selected_physical_grid"] is not None
    assert result["uniform_delayed"]["unknown_reason"] == "pulse_level_alias_ambiguity"
    assert result["alternating_duplet_triplet"]["selected_physical_grid"] is None
    assert result["irregular_jitter"]["selected_physical_grid"] is None
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT/"artifacts/experiments/meter-pulse"):
        raise ValueError("Use a new isolated output")
    started = time.monotonic()
    output.mkdir(parents=True)
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
        os.environ[name] = "2"
    # Persist the exact preregistration and pass controls before actual file reads.
    write(output/"freeze.json", {"settings": SETTINGS, "plan_sha256": digest(PLAN),
        "harness_sha256": digest(Path(__file__)), "frozen_utc": datetime.now(timezone.utc).isoformat(), "actual_read": False})
    write(output/"controls.json", controls())
    tracked = [ANALYSIS, ANALYSIS.parent/"manifest.json", ROOT/"scripts/meter.py", ROOT/"scripts/rhythm.py", ROOT/"scripts/guitar_features.py"]
    before = {str(path.relative_to(ROOT)): digest(path) for path in tracked}
    analysis = json.loads(ANALYSIS.read_text())
    analysis.pop("declared_tempo", None)  # Operator prior is excluded from all ranking inputs.
    source = Path(analysis["source"]["path"]).resolve()
    if not source.is_relative_to(ANALYSIS.parent) or digest(source)!=analysis["source"]["sha256"]:
        raise ValueError("Source identity differs")
    manifest = json.loads((ANALYSIS.parent/"manifest.json").read_text())
    if manifest["output_sha256"].get(source.name)!=digest(source):
        raise ValueError("Manifest source identity differs")
    before[str(source.relative_to(ROOT))] = digest(source)
    duration = analysis["analysis"]["duration_seconds"]
    if not 0<duration<=SETTINGS["maximum_duration_seconds"]:
        raise ValueError("Extent is outside bounds")
    proxies = {name: sorted(item["audio_relative_seconds"] for item in analysis["events"] if item["kind"]==name) for name in SETTINGS["proxies"]}
    if any(len(values)>SETTINGS["maximum_events"] or any(not math.isfinite(value) or not 0<=value<=duration for value in values) for values in proxies.values()):
        raise ValueError("Event bounds exceeded")
    prediction = rank(proxies, analysis["click_grid"]["period_seconds"], duration)
    prediction["provenance"] = {"analysis_sha256": digest(ANALYSIS), "source_sha256": digest(source),
        "original_source_sha256": manifest["source"]["sha256"], "timeline": analysis["timeline"], "settings": SETTINGS}
    write(output/"predictions.json", prediction)
    # Prior comparison starts only after exclusive, durable prediction output.
    operator_prior = {"bpm": 178., "provenance": "operator_approximate_statement", "ground_truth": False}
    write(output/"prior-comparison.json", {"operator_prior": operator_prior,
        "prediction_sha256": digest(output/"predictions.json"), "comparison_used_to_rank": False,
        "observed_pulse_family": [{"bpm": 60/(analysis["click_grid"]["period_seconds"]*factor),
            "relative_distance_to_approximate_prior": abs(60/(analysis["click_grid"]["period_seconds"]*factor)-178)/178}
            for factor in SETTINGS["pulse_factors"]]})
    after = {key: digest(ROOT/key) for key in before}
    if before!=after:
        raise ValueError("Input or canonical source changed")
    write(output/"receipt.json", {"inputs_before": before, "inputs_after": after, "unchanged": True,
        "actual_variants": len(prediction["variants"]), "seconds": time.monotonic()-started,
        "prediction_sha256": digest(output/"predictions.json"), "controls_sha256": digest(output/"controls.json")})
    print(json.dumps({"output": str(output), "receipt_sha256": digest(output/"receipt.json"),
        "unknown_reason": prediction["unknown_reason"], "physical_grid_families": len(prediction["physical_grid_families"])}))


if __name__ == "__main__":
    main()
