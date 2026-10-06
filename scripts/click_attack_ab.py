#!/usr/bin/env python3
"""Experimental click/attack A/B: synthetic isolated vs coincident attacks through clicks.experiment.

The synthetic arms measure what the existing opt-in, overlap-guarded attenuation does to
known guitar attacks. The real-take block is detection-only and makes no attenuation claim.
No listening A/B is performed; click identity is unverified.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
RATE = 48000
PERIOD_SECONDS = .6757
CLICK_PHASE_SECONDS = .3
DELTAS_MS = (-5, 0, 2, 5, 10)
NOTES = (24, 29, 34, 39, 46)
ARTICULATIONS = {"palm_mute": .023, "sustained": .300}
ATTACK_WINDOW_SECONDS = (-.005, .050)
MATCH_TOLERANCE_SECONDS = .010
REAL_COINCIDENT_TOLERANCE_SECONDS = .020
TEMPLATE_SECONDS = .020
ATTACK_PROXIMAL_CLICK_SECONDS = .060
STRENGTH = .5
ATTACKS_PER_ARM = 20
NOISE_AMPLITUDE = .001
ENERGY_DELTA_THRESHOLD_DB = .5
NAMESPACES = {"dev": "rhythm-s2-click-ab-dev", "eval": "rhythm-s2-click-ab-eval"}
SEED_SETS = {"dev": (1, 2, 3), "eval": (8101, 8102, 8103, 8104)}
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "s2" / "rhythm_clicks" / "click-ab"
FIXED_FIELDS = {"click_identity": "unverified", "listening_ab": "not_performed",
                "physical_capture_latency": "uncalibrated", "onset_detector_delay_compensated": False,
                "performance_grading": "not_performed", "expected_rhythm_reference": None}

_spec = importlib.util.spec_from_file_location("click_ab_clicks", Path(__file__).with_name("clicks.py"))
clicks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(clicks)


def unit(namespace: str, seed: int, knob: str) -> float:
    return int.from_bytes(hashlib.sha256(f"{namespace}:{seed}:{knob}".encode()).digest()[:8], "big") / 2**64


def render_arm(arm: str, seed: int, namespace: str, attack_count: int = ATTACKS_PER_ARM) -> dict:
    """48 kHz mono fixture; clicks every 0.6757 s; one attack on every other click after the template click."""
    np, _, _, _, _ = clicks.dependencies()
    if arm not in ("isolated", "coincident"):
        raise ValueError("Arm must be isolated or coincident")
    beats = 2 + 2 * attack_count + 2
    length = round((CLICK_PHASE_SECONDS + beats * PERIOD_SECONDS + .5) * RATE)
    click_amplitude = .06 + .06 * unit(namespace, seed, "click_amplitude")
    size = round(.009 * RATE)
    age = np.arange(size) / RATE
    click_wave = click_amplitude * np.exp(-age / .0018) * np.sin(2 * np.pi * 3500 * age)
    click_track = np.zeros(length)
    click_samples = [round((CLICK_PHASE_SECONDS + beat * PERIOD_SECONDS) * RATE) for beat in range(beats)]
    for sample in click_samples:
        click_track[sample:sample + size] += click_wave
    attacks = []
    for index in range(attack_count):
        host = click_samples[2 + 2 * index]
        if arm == "isolated":
            delta_ms = None
            onset = host + round(PERIOD_SECONDS / 2 * RATE)
        else:
            delta_ms = DELTAS_MS[index % len(DELTAS_MS)]
            onset = host + round(delta_ms / 1000 * RATE)
        knob = f"{arm}:{index}"
        articulation = "palm_mute" if unit(namespace, seed, knob + ":articulation") < .5 else "sustained"
        attacks.append({"index": index, "onset_sample": onset, "host_click_sample": host, "delta_ms": delta_ms,
                        "nearest_click_distance_ms": min(abs(onset - sample) for sample in click_samples) / RATE * 1000,
                        "midi": NOTES[int(unit(namespace, seed, knob + ":note") * len(NOTES)) % len(NOTES)],
                        "articulation": articulation, "decay_seconds": ARTICULATIONS[articulation],
                        "drive": 2.6 + 2.0 * unit(namespace, seed, knob + ":drive"),
                        "gain": .17 * (.65 + .35 * unit(namespace, seed, knob + ":gain"))})
    guitar = np.zeros(length)
    for position, attack in enumerate(attacks):
        following = attacks[position + 1]["onset_sample"] if position + 1 < len(attacks) else length
        extent = min(following - attack["onset_sample"], round(1.0 * RATE), length - attack["onset_sample"])
        j = np.arange(extent)
        t = j / RATE
        envelope = np.minimum.reduce([np.ones(extent), t / .0015, (extent - j) / (.006 * RATE)])
        frequency = 440 * 2 ** ((attack["midi"] - 69) / 12)
        guitar[attack["onset_sample"]:attack["onset_sample"] + extent] += (
            attack["gain"] * envelope * np.exp(-t / attack["decay_seconds"])
            * np.tanh(attack["drive"] * np.sin(2 * np.pi * frequency * t)))
    generator = np.random.default_rng(int.from_bytes(hashlib.sha256(f"{namespace}:{seed}:{arm}:noise".encode()).digest()[:8], "big"))
    noise = NOISE_AMPLITUDE * generator.uniform(-1, 1, length)
    mix = (guitar + click_track + noise).astype(np.float32)
    if float(np.max(np.abs(mix))) >= .999:
        raise ValueError("A/B fixture would clip; normalization is not applied")
    template_start = click_samples[0] / RATE
    return {"arm": arm, "seed": seed, "namespace": namespace, "mix": mix, "guitar": guitar, "clean_guitar": guitar,
            "click_track": click_track, "noise": noise, "click_samples": click_samples, "attacks": attacks,
            "template_window": (template_start, template_start + TEMPLATE_SECONDS),
            "parameters": {"sample_rate": RATE, "period_seconds": PERIOD_SECONDS, "click_amplitude": click_amplitude,
                           "click_waveform": "sin(2*pi*3500*t)*exp(-t/1.8 ms), 9 ms", "noise_amplitude": NOISE_AMPLITUDE,
                           "attack_count": attack_count, "generated_click_count": len(click_samples),
                           "template_identity": "first_click_operator_style_click_only_declaration",
                           "low_frequency_content": "32.70 Hz (MIDI 24) notes retained; no high-pass"}}


def spectral_centroid(segment) -> float | None:
    np, _, _, _, _ = clicks.dependencies()
    window = np.hanning(len(segment))
    magnitude = np.abs(np.fft.rfft(segment * window))
    total = float(np.sum(magnitude))
    if total <= 1e-20:
        return None
    return float(np.sum(np.fft.rfftfreq(len(segment), 1 / RATE) * magnitude) / total)


def _difference(left, right):
    return None if left is None or right is None else left - right


def _distribution(values: list) -> dict:
    present = sorted(value for value in values if value is not None)
    if not present:
        return {"median": None, "q1": None, "q3": None, "count": 0, "denominator": len(values)}
    return {"median": statistics.median(present), "q1": clicks.rhythm._quantile(present, .25),
            "q3": clicks.rhythm._quantile(present, .75), "count": len(present), "denominator": len(values)}


def window_metrics(fixture: dict, processed) -> list[dict]:
    np, _, _, _, _ = clicks.dependencies()
    mix = fixture["mix"].astype(np.float64)
    out = processed[:, 0].astype(np.float64)
    removal = mix - out
    rows = []
    for attack in fixture["attacks"]:
        start = max(0, attack["onset_sample"] + round(ATTACK_WINDOW_SECONDS[0] * RATE))
        end = min(len(mix), attack["onset_sample"] + round(ATTACK_WINDOW_SECONDS[1] * RATE))
        window = slice(start, end)
        mix_energy = float(np.sum(mix[window] ** 2))
        out_energy = float(np.sum(out[window] ** 2))
        clean = fixture["clean_guitar"][window]
        clean_energy = float(np.sum(clean ** 2))
        removed = removal[window]
        removed_energy = float(np.sum(removed ** 2))
        click = fixture["click_track"][window]
        click_energy = float(np.sum(click ** 2))
        if removed_energy <= 1e-12 * max(clean_energy, 1e-20):
            error_db, error_reason = None, "no_removal_energy_in_window"
        else:
            scale = float(np.dot(removed, click)) / click_energy if click_energy > 1e-20 else 0.0
            unexplained = removed - scale * click
            error_db = 10 * math.log10(max(float(np.sum(unexplained ** 2)), 1e-30) / max(clean_energy, 1e-30))
            error_reason = None
        centroid_mix = spectral_centroid(mix[window])
        centroid_out = spectral_centroid(out[window])
        centroid_clean = spectral_centroid(clean)
        rows.append({"attack_index": attack["index"], "onset_seconds": attack["onset_sample"] / RATE,
                     "delta_ms": attack["delta_ms"], "nearest_click_distance_ms": attack["nearest_click_distance_ms"],
                     "midi": attack["midi"], "articulation": attack["articulation"],
                     "window_seconds": [start / RATE, end / RATE],
                     "attack_energy_delta_db": 10 * math.log10(max(out_energy, 1e-30) / max(mix_energy, 1e-30)),
                     "guitar_component_error_db": error_db, "guitar_component_error_reason": error_reason,
                     "removed_energy_fraction_of_mix": removed_energy / max(mix_energy, 1e-30),
                     "centroid_hz_mix": centroid_mix, "centroid_hz_processed": centroid_out, "centroid_hz_clean_guitar": centroid_clean,
                     "centroid_delta_hz_vs_mix": _difference(centroid_out, centroid_mix),
                     "centroid_delta_hz_vs_clean_guitar": _difference(centroid_out, centroid_clean),
                     "baseline_centroid_delta_hz_mix_vs_clean": _difference(centroid_mix, centroid_clean)})
    return rows


def click_decisions(fixture: dict, result: dict) -> dict:
    tolerance = round(MATCH_TOLERANCE_SECONDS * RATE)
    events = result["events"]
    used, decisions, reasons = set(), [], {}
    for sample in fixture["click_samples"]:
        best = None
        for index, event in enumerate(events):
            distance = abs(event["aligned_window_start_sample"] - sample)
            if index not in used and distance <= tolerance and (best is None or distance < best[0]):
                best = (distance, index)
        if best is None:
            decisions.append("unmatched")
            continue
        used.add(best[1])
        event = events[best[1]]
        decisions.append(event["decision"])
        if event["decision"] == "abstained":
            for reason in event["reason"].split(";"):
                reasons[reason] = reasons.get(reason, 0) + 1
    proximity = round(ATTACK_PROXIMAL_CLICK_SECONDS * RATE)
    proximal = [any(abs(attack["onset_sample"] - sample) <= proximity for attack in fixture["attacks"])
                for sample in fixture["click_samples"]]
    return {"decisions": decisions, "attack_proximal": proximal, "abstain_reason_counts": dict(sorted(reasons.items())),
            "unmatched_candidate_count": len(events) - len(used)}


def run_arm(arm: str, seed: int, namespace: str) -> dict:
    fixture = render_arm(arm, seed, namespace)
    result, processed, removed = clicks.experiment(
        fixture["mix"], RATE, template_window=fixture["template_window"], attenuate=True,
        template_click_only=True, strength=STRENGTH, bpm=60 / PERIOD_SECONDS)
    matched = click_decisions(fixture, result)
    rows = window_metrics(fixture, processed)
    return {"fixture": fixture, "result": result, "decisions": matched, "windows": rows}


def summarize_arm(runs: list[dict]) -> dict:
    decisions = [decision for run in runs for decision in run["decisions"]["decisions"]]
    windows = [row for run in runs for row in run["windows"]]
    reasons: dict[str, int] = {}
    for run in runs:
        for reason, count in run["decisions"]["abstain_reason_counts"].items():
            reasons[reason] = reasons.get(reason, 0) + count
    denominator = len(decisions)
    counts = {name: sum(decision == key for decision in decisions)
              for name, key in (("attenuated_count", "attenuated"), ("abstained_count", "abstained"),
                                ("analyze_only_count", "analyze_only"), ("unmatched_generated_click_count", "unmatched"))}
    over = sum(abs(row["attack_energy_delta_db"]) > ENERGY_DELTA_THRESHOLD_DB for row in windows)
    proximal = [decision for run in runs for decision, near in zip(run["decisions"]["decisions"], run["decisions"]["attack_proximal"]) if near]
    proximal_counts = {key: sum(decision == key for decision in proximal)
                       for key in ("attenuated", "abstained", "analyze_only", "unmatched")}
    summary = {"generated_click_count": denominator, **counts,
               "attenuated_fraction": counts["attenuated_count"] / denominator if denominator else None,
               "count_denominator": "generated_click_count",
               "attack_proximal_clicks": {"rule": f"generated click within {ATTACK_PROXIMAL_CLICK_SECONDS * 1000:.0f} ms of an attack onset",
                                          "denominator": len(proximal), "decision_counts": proximal_counts,
                                          "attenuated_fraction": proximal_counts["attenuated"] / len(proximal) if proximal else None},
               "abstain_reason_counts": dict(sorted(reasons.items())),
               "unmatched_candidate_count": sum(run["decisions"]["unmatched_candidate_count"] for run in runs),
               "attack_window_count": len(windows),
               "attack_window_seconds": list(ATTACK_WINDOW_SECONDS),
               "windows_with_abs_energy_delta_over_0_5_db": {"count": over, "denominator": len(windows)},
               "attack_energy_delta_db": _distribution([row["attack_energy_delta_db"] for row in windows]),
               "guitar_component_error_db": {**_distribution([row["guitar_component_error_db"] for row in windows]),
                                             "null_reason_counts": {"no_removal_energy_in_window": sum(
                                                 row["guitar_component_error_reason"] == "no_removal_energy_in_window" for row in windows)}},
               "centroid_delta_hz_vs_mix": _distribution([row["centroid_delta_hz_vs_mix"] for row in windows]),
               "centroid_delta_hz_vs_clean_guitar": _distribution([row["centroid_delta_hz_vs_clean_guitar"] for row in windows]),
               "baseline_centroid_delta_hz_mix_vs_clean": _distribution([row["baseline_centroid_delta_hz_mix_vs_clean"] for row in windows]),
               "frequency_preservation_per_seed": [{"seed": run["fixture"]["seed"], **run["result"]["frequency_preservation"]} for run in runs],
               "windows": windows}
    return summary


def synthetic(seed_set: str) -> dict:
    if seed_set not in SEED_SETS:
        raise ValueError("Unknown seed set")
    namespace, seeds = NAMESPACES[seed_set], SEED_SETS[seed_set]
    arms, per_seed = {}, []
    for arm in ("isolated", "coincident"):
        runs = [run_arm(arm, seed, namespace) for seed in seeds]
        arms[arm] = summarize_arm(runs)
        for run in runs:
            per_seed.append({"arm": arm, "seed": run["fixture"]["seed"], "parameters": run["fixture"]["parameters"],
                             "summary": run["result"]["summary"], "periodicity": run["result"].get("periodicity"),
                             "template": run["result"].get("template"),
                             "click_decisions": run["decisions"]["decisions"]})
    isolated, coincident = arms["isolated"]["attenuated_fraction"], arms["coincident"]["attenuated_fraction"]
    return {"seed_set": seed_set, "seeds": list(seeds), "namespace": namespace, "arms": arms, "per_seed": per_seed,
            "comparison": {"attenuated_fraction_isolated": isolated, "attenuated_fraction_coincident": coincident,
                           "coincident_lower_than_isolated": (coincident < isolated) if None not in (isolated, coincident) else None,
                           "prediction_recorded_before_run": "coincident attenuated fraction < isolated; isolated windows over 0.5 dB = 0"}}


def real_take(source: Path, analysis_path: Path) -> dict:
    """Detection-only clicks.experiment (no template, no attenuation, no audio written)."""
    source = source.expanduser().resolve(strict=True)
    analysis = json.loads(analysis_path.expanduser().resolve(strict=True).read_text(encoding="utf-8"))
    source_hash = clicks.rhythm.file_hash(source)
    if (analysis.get("source") or {}).get("sha256") != source_hash:
        raise ValueError("Analysis is not bound to the real-take input sha256")
    metadata = clicks.rhythm.probe(source)
    pcm, rate = clicks.decode_native(source, metadata)
    declared = (analysis.get("declared_tempo") or {}).get("bpm")
    result, processed, removed = clicks.experiment(pcm, rate, bpm=declared)
    if processed is not None or removed is not None:
        raise ValueError("Detection-only run unexpectedly produced audio")
    if clicks.rhythm.file_hash(source) != source_hash:
        raise ValueError("Input changed during detection")
    attacks = sorted(event["audio_relative_seconds"] for event in analysis.get("events", [])
                     if event.get("kind") == "broadband_attack_candidate")
    import bisect
    coincident = 0
    for event in result["events"]:
        time = event["audio_relative_seconds"]
        position = bisect.bisect_left(attacks, time)
        if any(0 <= index < len(attacks) and abs(attacks[index] - time) <= REAL_COINCIDENT_TOLERANCE_SECONDS
               for index in (position - 1, position)):
            coincident += 1
    total = len(result["events"])
    drift = result.get("click_grid_drift") or {}
    return {"status": "detection_only", "attenuation_claim": "none_detection_only", "audio_written": False,
            "input": {"path": str(source), "sha256": source_hash, "sample_rate": rate, "channels": int(pcm.shape[1])},
            "analysis": {"path": str(analysis_path), "sha256": clicks.rhythm.file_hash(analysis_path.expanduser().resolve()),
                         "broadband_attack_candidate_count": len(attacks)},
            "declared_bpm_seed": declared, "candidate_count": total,
            "coincident_candidate_count": coincident, "isolated_candidate_count": total - coincident,
            "coincidence_rule": f"candidate within {REAL_COINCIDENT_TOLERANCE_SECONDS * 1000:.0f} ms of a broadband attack candidate",
            "coincident_fraction": coincident / total if total else None,
            "click_grid": {key: value for key, value in (result.get("click_grid") or {}).items()
                           if key not in ("observed_events", "drift")} or None,
            "click_grid_drift": {key: value for key, value in drift.items() if key not in ("tracked_events",)},
            "claim_class": "M-real_unvalidated"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-set", choices=tuple(SEED_SETS), default="dev")
    parser.add_argument("--skip-synthetic", action="store_true")
    parser.add_argument("--real-input", type=Path)
    parser.add_argument("--real-analysis", type=Path)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    try:
        if args.seed_set == "eval" and not args.skip_synthetic and os.environ.get("CLICK_AB_S2_SEALED_EVAL") != "1":
            raise ValueError("Sealed eval seeds require CLICK_AB_S2_SEALED_EVAL=1")
        if (args.real_input is None) != (args.real_analysis is None):
            raise ValueError("--real-input and --real-analysis are required together")
        parts = args.output_root.expanduser().resolve().parts
        if any(parts[index:index + 2] == ("artifacts", "runs") for index in range(len(parts) - 1)):
            raise ValueError("Output may not be written under accepted run directories")
        np, scipy, _, _, _ = clicks.dependencies()
        result = {"schema_version": SCHEMA_VERSION, "tool": "click_attack_ab", "status": "experimental_synthetic_ab",
                  **FIXED_FIELDS,
                  "settings": {"rate": RATE, "period_seconds": PERIOD_SECONDS, "deltas_ms": list(DELTAS_MS), "notes_midi": list(NOTES),
                               "articulation_decay_seconds": ARTICULATIONS, "strength": STRENGTH, "attenuate": True,
                               "template_seconds": TEMPLATE_SECONDS, "match_tolerance_seconds": MATCH_TOLERANCE_SECONDS,
                               "attacks_per_arm_per_seed": ATTACKS_PER_ARM, "protected_subtraction_below_hz": clicks.PROTECTED_HZ},
                  "versions": {"numpy": np.__version__, "scipy": scipy.__version__},
                  "producer": {"click_attack_ab_sha256": clicks.rhythm.file_hash(Path(__file__)),
                               "clicks_sha256": clicks.rhythm.file_hash(Path(__file__).with_name("clicks.py")),
                               "rhythm_sha256": clicks.rhythm.file_hash(Path(__file__).with_name("rhythm.py"))},
                  "synthetic": None if args.skip_synthetic else synthetic(args.seed_set),
                  "real_take": real_take(args.real_input, args.real_analysis) if args.real_input else {"status": "not_requested"},
                  "limitations": ["Synthetic attacks and clicks are generator constructs; real clicks vary with AGC, room and mechanism.",
                                  "Energy and centroid deltas are DFT/window measurements, not listening acceptance.",
                                  "The real-take block counts detection candidates only; no attenuation was applied or claimed."]}
        if result["synthetic"]:
            result["arms"] = {arm: {key: value for key, value in data.items() if key != "windows"}
                              for arm, data in result["synthetic"]["arms"].items()}
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
        result["run_id"] = run_id
        destination = args.output_root.expanduser().resolve() / run_id
        destination.mkdir(parents=True, exist_ok=False)
        clicks.rhythm.atomic_write(destination / "click_attack_ab.json", json.dumps(result, indent=2, allow_nan=False) + "\n")
        print(json.dumps({"click_attack_ab_json": str(destination / "click_attack_ab.json"),
                          "arms": {arm: {key: data[key] for key in ("generated_click_count", "attenuated_count", "abstained_count",
                                                                     "analyze_only_count", "unmatched_generated_click_count",
                                                                     "windows_with_abs_energy_delta_over_0_5_db")}
                                   for arm, data in (result.get("arms") or {}).items()},
                          "real_take": {key: result["real_take"].get(key) for key in ("status", "candidate_count", "coincident_candidate_count",
                                                                                     "isolated_candidate_count")}}))
        return 0
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"click_attack_ab: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
