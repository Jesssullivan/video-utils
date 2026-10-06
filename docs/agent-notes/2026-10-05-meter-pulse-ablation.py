#!/usr/bin/env python3
"""Isolated cached-feature ablation; generator truth opens after predictions."""
import argparse
import bisect
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT/"artifacts/benchmarks/root-calibration-pilot-20261005T2300/phrase-pilot-index.json"
BANK = ROOT/"artifacts/benchmarks/root-calibration-bank-20261005T2255/fixtures.json"
ACTUAL = ROOT/"artifacts/runs/20261005T232741Z-2b5dc43fd009/analysis.json"
IDS = ("low32-sustain", "palm-muted-recurrence", "legato-recurrence", "c1-missing-fundamental", "timing-reference", "timing-errors")
SETTINGS = {"pulse_factors": [.5, 1., 2.], "grid_exclusion_seconds": .025,
            "subdivisions": [1, 2, 3, 4, 5, 7, 8], "generated_duration_limit": 60.,
            "truth_used_during_prediction": False, "audio_decoded": False, "maximum_seconds": 120}


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def read(path, expected=None):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 20_000_000:
        raise ValueError("Unsafe or oversized JSON input")
    if expected and digest(path) != expected:
        raise ValueError("Input identity differs")
    return json.loads(path.read_text())


def write(path, data):
    with path.open("x") as handle:
        json.dump(data, handle, indent=2, allow_nan=False)
        handle.write("\n")


def inspect_analysis(worker, analysis):
    times, energy = worker.read_features(analysis)
    grid = analysis.get("click_grid")
    if not times or not grid:
        return {"status": "missing_evidence", "aliases": []}
    period, phase = grid["period_seconds"], grid["phase_seconds_audio_relative"]
    spectral = [event["audio_relative_seconds"] for event in analysis["events"] if event["kind"] == "spectral_flux_attack_candidate"]
    superflux = [event["audio_relative_seconds"] for event in analysis["events"] if event["kind"] == "superflux_attack_candidate"]
    away = [value for value in spectral if abs(value-phase-round((value-phase)/period)*period) > SETTINGS["grid_exclusion_seconds"]]
    rows = []
    for factor in SETTINGS["pulse_factors"]:
        pulse = period*factor
        starts, accents = worker.aggregate_pulses(times, energy, pulse, phase)
        variants = {"mfcc_energy": worker.rank_accents(accents)}
        for name, values in (("spectral_count", spectral), ("superflux_count", superflux), ("spectral_away_fitted_grid", away)):
            values = sorted(values)
            counts = [bisect.bisect_left(values, start+pulse)-bisect.bisect_left(values, start) for start in starts]
            variants[name] = worker.rank_accents(counts)
            variants[name]["retained_events"] = len(values)
            variants[name]["nonempty_pulse_fraction"] = sum(value>0 for value in counts)/len(counts) if counts else None
        residuals = []
        for subdivision in SETTINGS["subdivisions"]:
            interval = pulse/subdivision
            offsets = [abs(value-phase-round((value-phase)/interval)*interval) for value in spectral]
            residuals.append({"subdivision": subdivision, "median_residual_ms": 1000*statistics.median(offsets) if offsets else None,
                "event_count": len(offsets), "interpretation": "descriptive_not_alias_selection_or_tuplet_detection"})
        rows.append({"factor": factor, "pulse_bpm": 60/pulse, "pulse_count": len(accents),
                     "four_pulse_window_seconds": 4*pulse, "variants": variants, "subdivision_residuals": residuals})
    return {"aliases": rows, "time_signature": None, "spectral_events": len(spectral), "superflux_events": len(superflux),
            "fitted_grid_rejected_fraction": 1-len(away)/len(spectral) if spectral else None,
            "identity_warning": "Neither spectral attacks nor grid-excluded events are identified guitar notes or isolated click stems",
            "declared_tempo_retained_as_context_only": analysis.get("declared_tempo")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT/"artifacts/experiments/meter-pulse") or output.exists():
        raise ValueError("Use a new isolated meter-pulse output")
    started = time.monotonic()
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
        os.environ[name] = "2"
    output.mkdir(parents=True)
    sources = output/"sources"
    sources.mkdir()
    tracked = [PILOT, BANK, ACTUAL, ROOT/"scripts/meter.py", ROOT/"scripts/dag.py", Path(__file__).resolve()]
    before = {str(path.relative_to(ROOT)): digest(path) for path in tracked}
    for name in ("meter.py", "dag.py"):
        shutil.copyfile(ROOT/"scripts"/name, sources/name)
    sys.path.insert(0, str(sources))
    spec = importlib.util.spec_from_file_location("frozen_meter", sources/"meter.py")
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    pilot = read(PILOT)
    rows = []
    total = 0.
    # Prediction phase: no bank index/truth content has been loaded.
    for index, identifier in enumerate(IDS):
        case = next(item for item in pilot["cases"] if item["id"] == identifier)
        path = PILOT.parent/case["analysis"]["path"]
        analysis = read(path, case["analysis"]["sha256"])
        source = Path(analysis["source"]["path"]).resolve()
        if not source.is_relative_to(ROOT/"artifacts") or digest(source) != analysis["source"]["sha256"]:
            raise ValueError("Changed cached source")
        before[str(path.relative_to(ROOT))] = digest(path)
        before[str(source.relative_to(ROOT))] = digest(source)
        total += analysis["analysis"]["duration_seconds"]
        if total > SETTINGS["generated_duration_limit"]:
            raise ValueError("Generated audio extent exceeds admitted budget")
        prediction = inspect_analysis(worker, analysis)
        prediction["provenance"] = {"source_sha256": digest(source), "analysis_sha256": digest(path), "settings": SETTINGS}
        target = output/f"case-{index+1:02d}.json"
        write(target, prediction)
        rows.append({"id": identifier, "prediction": target.name, "prediction_sha256": digest(target),
                     "source_sha256": digest(source), "duration_seconds": analysis["analysis"]["duration_seconds"]})
        if time.monotonic()-started > 120:
            raise ValueError("Elapsed bound exceeded")
    analysis = read(ACTUAL)
    source = Path(analysis["source"]["path"]).resolve()
    if not source.is_relative_to(ROOT/"artifacts") or digest(source) != analysis["source"]["sha256"]:
        raise ValueError("Real-run source identity differs")
    before[str(source.relative_to(ROOT))] = digest(source)
    write(output/"actual-observation.json", inspect_analysis(worker, analysis))
    write(output/"prediction-phase-complete.json", {"cases": rows, "truth_opened": False,
          "unique_generated_duration_seconds": total, "actual_audio_decoded": False})
    # Evaluation phase: truth now supplies only renderer metadata, never ranking knobs.
    bank = read(BANK, pilot["bank_index_sha256"])
    evaluation = []
    for row in rows:
        case = next(item for item in bank["cases"] if item["id"] == row["id"])
        truth = read(BANK.parent/case["truth"], case["truth_sha256"])
        if truth["source"]["sha256"] != row["source_sha256"]:
            raise ValueError("Truth source identity differs")
        prediction = read(output/row["prediction"], row["prediction_sha256"])
        job = next(item for item in pilot["cases"] if item["id"] == row["id"])
        observed = read(PILOT.parent/job["analysis"]["path"], job["analysis"]["sha256"])
        event_times = sorted(event["audio_relative_seconds"] for event in observed["events"]
                             if event["kind"] == "spectral_flux_attack_candidate")
        # Evaluation descriptors only: nearest mixture attack is not a classified click.
        offsets = [min(event_times, key=lambda event: abs(event-click))-click
                   for click in truth.get("click_times_seconds", [])] if event_times else []
        evaluation.append({**row, "truth_keys": sorted(truth), "truth_sha256": case["truth_sha256"],
            "meter_truth_available": any(key in truth for key in ("meter", "time_signature", "downbeats")),
            "meter_accuracy": None, "reason": "No annotated intended meter/downbeat truth; rendering timing is not meter",
            "rendering_bpm_evaluation_only": truth.get("bpm"),
            "alias_rendering_bpm_relative_errors_evaluation_only": [abs(alias["pulse_bpm"]-truth["bpm"])/truth["bpm"]
                for alias in prediction["aliases"]] if truth.get("bpm") else None,
            "nearest_mixture_spectral_event_to_renderer_click": {"click_count": len(offsets),
                "median_signed_offset_ms": 1000*statistics.median(offsets) if offsets else None,
                "median_absolute_offset_ms": 1000*statistics.median(abs(value) for value in offsets) if offsets else None,
                "identity": "nearest_mixture_attack_not_identified_click_or_detector_calibration"}})
    after = {key: digest(ROOT/key) for key in before}
    if before != after:
        raise ValueError("Canonical or cached input changed")
    write(output/"receipt.json", {"created_utc": datetime.now(timezone.utc).isoformat(),
        "settings": SETTINGS, "cases": evaluation, "inputs_before_sha256": before, "inputs_after_sha256": after,
        "canonical_and_cached_inputs_unchanged": True, "seconds": time.monotonic()-started,
        "meter_ground_truth_accuracy_claimed": False, "actual_observation_sha256": digest(output/"actual-observation.json")})
    print(json.dumps({"output": str(output), "receipt_sha256": digest(output/"receipt.json"),
                      "seconds": time.monotonic()-started, "unique_generated_seconds": total}))


if __name__ == "__main__":
    main()
