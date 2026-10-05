#!/usr/bin/env python3
"""Bounded within-take feature DTW and uncertain motif-edit review hypotheses."""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

from dag import atomic_write, load, match_onsets, number, sha256

LIMITS = {"maximum_pairs": 60, "maximum_frames_per_window": 384,
          "maximum_cells_per_pair": 100_000, "maximum_cells_per_run": 2_000_000}
DEFAULTS = {"max_pairs": 30, "band_fraction": .20, "min_rate": .5, "max_rate": 2.,
            "skip_step_penalty": .05, "maximum_mean_feature_cost": .35,
            "minimum_detector_confidence": .7, "minimum_boundary_confidence": .6,
            "minimum_motif_attacks": 3, "minimum_timing_difference_seconds": .03}


def validate_settings(**changes) -> dict:
    settings = {**DEFAULTS, **changes}
    pairs = settings["max_pairs"]
    if isinstance(pairs, bool) or not isinstance(pairs, int) or not 1 <= pairs <= LIMITS["maximum_pairs"]:
        raise ValueError("max_pairs must be an integer in 1..60")
    for key in ("band_fraction", "min_rate", "max_rate"):
        settings[key] = number(settings[key], key, .000001)
    if not 0 < settings["band_fraction"] <= .5:
        raise ValueError("band_fraction must be in (0,.5]")
    if not .25 <= settings["min_rate"] <= 1 <= settings["max_rate"] <= 4:
        raise ValueError("Require .25 <= min_rate <= 1 <= max_rate <= 4")
    settings["local_steps"] = [[1, 1], [2, 1], [1, 2]]
    settings["rate_axis"] = "second_elapsed_seconds_per_first_elapsed_seconds"
    settings["limits"] = LIMITS
    return settings


def feature_vectors(features: dict) -> tuple[list[float], list[list[float]]]:
    if features.get("matrix_layout") != "feature_by_frame":
        raise ValueError("Feature matrix_layout must be feature_by_frame")
    times = features.get("frame_times_audio_relative_seconds")
    mfcc, chroma = features.get("mfcc"), features.get("chroma")
    if not isinstance(times, list) or not 4 <= len(times) <= 36_001:
        raise ValueError("Feature timestamps must contain 4..36001 frames")
    times = [number(value, "feature time", 0) for value in times]
    if any(a >= b for a, b in zip(times, times[1:])):
        raise ValueError("Feature times must be strictly increasing")
    if not isinstance(mfcc, list) or len(mfcc) != 13 or not isinstance(chroma, list) or len(chroma) != 12:
        raise ValueError("Expected 13 MFCC rows and 12 chroma rows")
    rows = mfcc[1:] + chroma  # MFCC0 carries absolute energy, not comparative tone.
    if any(not isinstance(row, list) or len(row) != len(times) for row in rows + mfcc[:1]):
        raise ValueError("Feature rows and timestamps must have the same length")
    for value in mfcc[0]:
        number(value, "MFCC0 value")  # Validate excluded energy data without using it.
    rows = [[number(value, "feature value") for value in row] for row in rows]
    return times, [list(vector) for vector in zip(*rows)]


def prepare_vectors(first: list[list[float]], second: list[list[float]]) -> tuple[list[list[float]], list[list[float]], bool]:
    joined = first + second
    width = len(joined[0])
    if width != 24 or any(len(vector) != width for vector in joined):
        raise ValueError("Comparative feature vectors must have 24 components")
    centers = [statistics.mean(row[k] for row in joined) for k in range(12)]
    scales = [max(1e-6, math.sqrt(statistics.mean((row[k] - centers[k]) ** 2 for row in joined))) for k in range(12)]
    # A constant texture has no temporal anchors, even if tone is highly similar.
    dynamic = any(max(row[k] for row in first) - min(row[k] for row in first) > 1e-5
                  and max(row[k] for row in second) - min(row[k] for row in second) > 1e-5 for k in range(width))

    def transform(vectors):
        result = []
        for row in vectors:
            mfcc = [(row[k] - centers[k]) / scales[k] for k in range(12)]
            chroma = row[12:]
            a = math.sqrt(sum(x*x for x in mfcc))
            b = math.sqrt(sum(x*x for x in chroma))
            result.append([x / max(a, 1e-12) / math.sqrt(2) for x in mfcc] +
                          [x / max(b, 1e-12) / math.sqrt(2) for x in chroma])
        return result
    return transform(first), transform(second), dynamic


def bounded_dtw(first: list[list[float]], second: list[list[float]], first_times: list[float],
                second_times: list[float], settings: dict, cell_budget: int | None = None) -> dict:
    n, m = len(first), len(second)
    if min(n, m) < 4:
        return {"status": "insufficient_feature_frames", "cells_visited": 0}
    if max(n, m) > LIMITS["maximum_frames_per_window"]:
        return {"status": "window_frame_limit", "cells_visited": 0}
    if len(first_times) != n or len(second_times) != m:
        raise ValueError("Window vectors and timestamps differ in length")
    duration_rate = (second_times[-1] - second_times[0]) / (first_times[-1] - first_times[0])
    if not settings["min_rate"] <= duration_rate <= settings["max_rate"]:
        return {"status": "duration_rate_outside_bounds", "duration_rate": duration_rate, "cells_visited": 0}
    budget = min(LIMITS["maximum_cells_per_pair"], cell_budget if cell_budget is not None else LIMITS["maximum_cells_per_pair"])
    rows, predecessors = {}, {}
    cells = 0
    for i in range(n):
        current = {}
        center = i / (n - 1)
        lower = max(0, math.ceil((center - settings["band_fraction"]) * (m - 1) - 1e-12))
        upper = min(m - 1, math.floor((center + settings["band_fraction"]) * (m - 1) + 1e-12))
        for j in range(lower, upper + 1):
            cells += 1
            if cells > budget:
                return {"status": "cell_budget_exhausted", "cells_visited": budget}
            cost = sum((a - b) ** 2 for a, b in zip(first[i], second[j])) / 4
            if i == 0 and j == 0:
                current[j] = cost
                predecessors[(i, j)] = None
                continue
            choices = []
            for di, dj in settings["local_steps"]:
                if i < di or j < dj:
                    continue
                previous = rows.get(i - di, {}).get(j - dj)
                if previous is None:
                    continue
                rate = (second_times[j] - second_times[j-dj]) / (first_times[i] - first_times[i-di])
                if settings["min_rate"] - 1e-9 <= rate <= settings["max_rate"] + 1e-9:
                    penalty = settings["skip_step_penalty"] if di != dj else 0
                    choices.append((previous + cost + penalty, di != dj, (i-di, j-dj)))
            if choices:
                best, _, previous_cell = min(choices)
                current[j] = best
                predecessors[(i, j)] = previous_cell
        rows[i] = current
        rows.pop(i - 3, None)
    if m - 1 not in rows[n-1]:
        return {"status": "no_valid_constrained_path", "cells_visited": cells, "duration_rate": duration_rate}
    path, cell = [], (n-1, m-1)
    while cell is not None:
        path.append(cell)
        cell = predecessors[cell]
    path.reverse()
    feature_costs = [sum((a-b)**2 for a, b in zip(first[i], second[j])) / 4 for i, j in path]
    return {"status": "aligned_hypothesis", "cells_visited": cells, "duration_rate": duration_rate,
            "mean_feature_cost": statistics.mean(feature_costs), "accumulated_cost": rows[n-1][m-1],
            "path": [[i, j] for i, j in path], "skipped_frame_steps": sum(di != dj for (a,b),(c,d) in zip(path,path[1:]) for di,dj in [(c-a,d-b)]),
            "path_coverage": {"first_frames": len({i for i,j in path}) / n, "second_frames": len({j for i,j in path}) / m}}


def map_time(time: float, path_times: list[tuple[float, float]]) -> float:
    first = [x for x, _ in path_times]
    index = bisect.bisect_right(first, time)
    if index == 0:
        return path_times[0][1] + time - path_times[0][0]
    if index == len(path_times):
        return path_times[-1][1] + time - path_times[-1][0]
    x0, y0 = path_times[index-1]
    x1, y1 = path_times[index]
    return y0 + (time-x0) / (x1-x0) * (y1-y0)


def motif_compare(pair: dict, path_times: list[tuple[float, float]], settings: dict) -> dict:
    first = pair.get("first_onset_offsets_seconds", [])
    second = pair.get("second_onset_offsets_seconds", [])
    if not isinstance(first, list) or not isinstance(second, list) or max(len(first),len(second)) > 2000:
        raise ValueError("Motifs must contain at most 2000 onset offsets")
    first = sorted(set(number(value, "first motif onset", 0) for value in first))
    second = sorted(set(number(value, "second motif onset", 0) for value in second))
    first_duration = pair["first_end_seconds"] - pair["first_start_seconds"]
    second_duration = pair["second_end_seconds"] - pair["second_start_seconds"]
    if any(value >= first_duration for value in first) or any(value >= second_duration for value in second):
        raise ValueError("Motif offset is outside its half-open phrase span")
    predicted = [map_time(value, path_times) for value in first]
    pulse = number(pair.get("pulse_period_seconds", .5), "pulse_period_seconds", .001)
    window = max(.03, min(.12, pulse * .2))
    matched, absent, additional = match_onsets(predicted, second, window)
    hint = str(pair.get("articulation_hint") or "unknown").lower()
    confidence_keys = ("detector_confidence", "first_boundary_confidence", "second_boundary_confidence")
    confidences = {key: pair.get(key) for key in confidence_keys}
    for key,value in confidences.items():
        if value is not None and not 0 <= number(value, key, 0) <= 1:
            raise ValueError("Confidence must be null or a heuristic score in 0..1")
    qualified = all(confidences[key] is not None and confidences[key] >=
                    (settings["minimum_detector_confidence"] if key == "detector_confidence" else settings["minimum_boundary_confidence"])
                    for key in confidence_keys)
    reasons = []
    if any(value < 0 or value >= second_duration for value in predicted):
        reasons.append("mapped_attack_outside_target_boundary")
    if "legato" in hint or "tap" in hint or "sweep" in hint:
        reasons.append("articulation_can_hide_or_merge_attacks")
    if not qualified:
        reasons.append("detector_or_boundary_confidence_unknown_or_weak")
    if min(len(first),len(second)) < settings["minimum_motif_attacks"]:
        reasons.append("too_few_detected_attacks")
    return {"status": "attack_edit_review_hypotheses" if not reasons else "attack_edits_abstained",
            "abstention_reasons": reasons, "detector": pair.get("onset_detector"), "confidence_kind": "heuristic_not_probability",
            "confidences": confidences, "articulation_hint": pair.get("articulation_hint"),
            "matching_window_seconds": window, "first_attack_count": len(first), "second_attack_count": len(second),
            "matches": [{"first_index": i, "second_index": j, "first_offset_seconds": first[i],
                "predicted_second_offset_seconds": predicted[i], "observed_second_offset_seconds": second[j],
                "alignment_residual_seconds": second[j]-predicted[i]} for i,j in matched],
            "unmatched_first": [{"index": i, "predicted_second_offset_seconds": predicted[i]} for i in absent],
            "unmatched_second": [{"index": j, "second_offset_seconds": second[j]} for j in additional],
            "warning": "Unmatched detected attacks are not missed/extra notes; intentional variation, rests and masking remain possible."}


def compare_pair(pair: dict, frame_times: list[float], vectors: list[list[float]], settings: dict,
                 source_start: float = 0, cell_budget: int | None = None) -> dict:
    spans = {key: number(pair.get(key), key, 0) for key in ("first_start_seconds", "first_end_seconds", "second_start_seconds", "second_end_seconds")}
    a,b,c,d = (spans[key] for key in ("first_start_seconds", "first_end_seconds", "second_start_seconds", "second_end_seconds"))
    if not a < b <= c < d:
        raise ValueError("Comparison spans must be ordered, nonoverlapping and positive")
    first_indices = list(range(bisect.bisect_left(frame_times,a), bisect.bisect_left(frame_times,b)))
    second_indices = list(range(bisect.bisect_left(frame_times,c), bisect.bisect_left(frame_times,d)))
    result = {"spans": spans, "recurrence_similarity": pair.get("similarity"), "flags": [],
              "source_time_seconds": source_start+c, "end_seconds": source_start+d,
              "boundary_confidence": {key: pair.get(key) for key in ("first_boundary_confidence","second_boundary_confidence")}}
    if min(len(first_indices),len(second_indices)) < 4 or max(len(first_indices),len(second_indices)) > LIMITS["maximum_frames_per_window"]:
        return {**result,"status":"window_frame_limits","cells_visited":0}
    first,second,dynamic = prepare_vectors([vectors[i] for i in first_indices], [vectors[i] for i in second_indices])
    if not dynamic:
        return {**result,"status":"constant_texture_alignment_ambiguous","cells_visited":0}
    first_times = [frame_times[i]-a for i in first_indices]
    second_times = [frame_times[i]-c for i in second_indices]
    alignment = bounded_dtw(first,second,first_times,second_times,settings,cell_budget)
    result.update(alignment)
    if alignment["status"] != "aligned_hypothesis":
        return result
    path_times = [(first_times[i],second_times[j]) for i,j in alignment["path"]]
    result["path_audio_relative_seconds"] = [{"first_seconds": a+x,"second_seconds":c+y} for x,y in path_times]
    if alignment["mean_feature_cost"] > settings["maximum_mean_feature_cost"]:
        result["status"] = "feature_mismatch_alignment_unreliable"
        return result
    offsets = [y-x for x,y in path_times]
    result["median_relative_offset_seconds"] = statistics.median(offsets)
    # Report an interior robust rate, separate from the forced endpoint rate.
    sampled = path_times[::max(1,len(path_times)//24)]
    slopes = [(y1-y0)/(x1-x0) for x0,y0 in sampled for x1,y1 in sampled
              if x1-x0 >= max(.2,(b-a)*.2) and x0 >= (b-a)*.1 and x1 <= (b-a)*.9]
    result["interior_rate_median"] = statistics.median(slopes) if slopes else None
    motif = motif_compare({**pair,**spans},path_times,settings)
    result["motif_comparison"] = motif

    def flag(kind,time,end,evidence):
        result["flags"].append({"kind":kind,"audio_relative_seconds":time,"source_time_seconds":source_start+time,
            "end_seconds":source_start+end,"confidence":"unvalidated_relative_alignment_hypothesis",
            "status":"needs_review","requires_expected_intent":False,"performance_issue_confirmed":False,"evidence":evidence})
    threshold = settings["minimum_timing_difference_seconds"]
    if abs(result["median_relative_offset_seconds"]) > threshold:
        flag("recurrence_relative_alignment_shift_review",c,d,{"median_relative_offset_seconds":result["median_relative_offset_seconds"],
            "warning":"Constant phrase-boundary bias or deliberate variation can explain the relative shift."})
    interior_rate = result["interior_rate_median"]
    if interior_rate is not None and abs(interior_rate-1) > .08:
        flag("recurrence_relative_rate_difference_review",c,d,{"second_per_first_time_rate":interior_rate,
            "warning":"Relative feature motion differs; this is not an absolute rushed/late performance grade."})
    if motif["status"] == "attack_edit_review_hypotheses":
        for item in motif["unmatched_first"]:
            time = c+item["predicted_second_offset_seconds"]
            flag("recurrence_attack_detection_gap_review",time,time,{**item,"warning":motif["warning"]})
        for item in motif["unmatched_second"]:
            time = c+item["second_offset_seconds"]
            flag("recurrence_additional_detection_review",time,time,{**item,"warning":motif["warning"]})
    return result


def build(directory: Path, settings: dict) -> dict:
    paths = {name:directory/f"{name}.json" for name in ("manifest","analysis","phrases")}
    fingerprints = {path.name:sha256(path) for path in paths.values()}
    payloads = {name:load(path) for name,path in paths.items()}
    if any(sha256(path) != fingerprints[path.name] for path in paths.values()):
        raise ValueError("Input artifact changed while reading; rerun against stable artifacts")
    manifest,analysis,phrases = (payloads[name] for name in ("manifest","analysis","phrases"))
    original_path = manifest.get("source", {}).get("path")
    if original_path and Path(original_path).expanduser().resolve() == (directory / "phrase-comparisons.json").resolve():
        raise ValueError("Comparison output would overwrite original source")
    original_hash = manifest.get("source",{}).get("sha256")
    identity = analysis.get("source",{}).get("sha256")
    if not all(isinstance(value,str) and len(value)==64 and all(c in "0123456789abcdef" for c in value) for value in (original_hash,identity)) or phrases.get("source",{}).get("sha256") != identity:
        raise ValueError("Manifest, analysis and phrases must provide matching analysis-input identity")
    lineage = "preliminary_raw_source" if identity == original_hash else None
    for name in ("denoised.wav","cleaned.wav"):
        if manifest.get("output_sha256",{}).get(name) == identity:
            if not (directory/name).is_file() or sha256(directory/name) != identity:
                raise ValueError("Restored analysis input failed manifest hash verification")
            lineage = "post_denoise"
    if lineage is None:
        raise ValueError("Analysis input is unrelated to the manifest original/restored artifacts")
    result = {"schema_version":1,"status":"within_take_comparison_hypotheses","source_sha256":original_hash,
              "analysis_input_sha256":identity,"analysis_lineage":lineage,"artifact_hashes":fingerprints,
              "settings":settings,"settings_sha256":hashlib.sha256(json.dumps(settings,sort_keys=True,allow_nan=False).encode()).hexdigest(),
              "requires_expected_intent":False,"comparisons":[],"flags":[],"performance_grade":"not_graded",
              "limitations":["DTW aligns comparative feature frames, not guitar notes or intended musical phrases.",
                  "Local step constraints can omit feature frames; omitted frames are not omitted notes.",
                  "Feature timestamps and detector/boundary uncertainty limit timing accuracy; confidence is heuristic.",
                  "Constant capture latency cancels in relative within-take timing, but detector/boundary bias does not.",
                  "Intentional rests, variation, legato, sweeps and tapping can differ between valid recurrences."]}
    features = (analysis.get("librosa") or {}).get("features")
    if not isinstance(features,dict):
        return {**result,"status":"feature_alignment_unavailable","reason":"analysis.librosa.features required; no implicit analysis rerun"}
    times,vectors = feature_vectors(features)
    pairs = phrases.get("observations",{}).get("recurrence_candidates",[])
    if not isinstance(pairs,list) or len(pairs)>5000:
        raise ValueError("recurrence_candidates must contain at most 5000 pairs")
    if not pairs:
        result["status"] = "no_recurrence_candidates"
    source_start = number(manifest.get("timeline",{}).get("audio_start_seconds",0),"source audio start")
    budget = LIMITS["maximum_cells_per_run"]
    for pair in pairs[:settings["max_pairs"]]:
        comparison = compare_pair(pair,times,vectors,settings,source_start,budget)
        result["comparisons"].append(comparison)
        result["flags"].extend(comparison["flags"])
        budget -= comparison.get("cells_visited",0)
        if budget <= 0:
            result["resource_status"] = "run_cell_budget_exhausted"
            break
    # Reject artifacts changed during this read-only computation.
    if any(sha256(path) != fingerprints[path.name] for path in paths.values()):
        raise ValueError("Input artifact changed during comparison; rerun against stable artifacts")
    result["cells_visited"] = LIMITS["maximum_cells_per_run"]-budget
    result["pairs_available"] = len(pairs)
    result["flags"].sort(key=lambda item:(item["source_time_seconds"],item["kind"]))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir",type=Path)
    parser.add_argument("--max-pairs",type=int,default=DEFAULTS["max_pairs"])
    parser.add_argument("--band-fraction",type=float,default=DEFAULTS["band_fraction"])
    parser.add_argument("--min-rate",type=float,default=DEFAULTS["min_rate"])
    parser.add_argument("--max-rate",type=float,default=DEFAULTS["max_rate"])
    args = parser.parse_args()
    try:
        directory = args.run_dir.expanduser().resolve(strict=True)
        settings = validate_settings(max_pairs=args.max_pairs,band_fraction=args.band_fraction,min_rate=args.min_rate,max_rate=args.max_rate)
        result = build(directory,settings)
        output = directory/"phrase-comparisons.json"
        atomic_write(output,json.dumps(result,indent=2,allow_nan=False)+"\n")
        print(json.dumps({"comparisons_json":str(output),"comparison_count":len(result["comparisons"]),
                          "status":result["status"],"review_flag_count":len(result["flags"])}))
        return 0
    except (OSError,ValueError,TypeError,KeyError,ZeroDivisionError) as exc:
        print(f"phrase compare: {exc}",file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
