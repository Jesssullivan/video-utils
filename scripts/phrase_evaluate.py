#!/usr/bin/env python3
"""Evaluate generated-fixture phrase evidence; never feed truth into discovery."""
from __future__ import annotations

import argparse
import bisect
from collections import Counter
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import statistics
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
LIMITS = {"fixtures": 12, "duration_seconds": 120, "json_bytes": 20_000_000,
          "aggregate_json_bytes": 64_000_000, "items": 512, "matching_edges": 65_536,
          "comparisons": 60, "path_landmarks": 384, "numerical_threads": 2,
          "source_file_bytes":128_000_000,"aggregate_hashed_bytes":512_000_000,"json_depth":128}
SETTINGS = {"boundary_tolerances_seconds": [.020, .050, .100],
            "span_iou_thresholds": [.50, .75], "exclude_recording_endpoints": True,
            "zero_denominator_policy": "zero_except_both_empty_null",
            "percentile": "descriptive_nearest_rank_with_sample_count_not_confidence",
            "limits": LIMITS}


def encoded_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def finite(value, label="number"):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f"Invalid finite {label}")
    return float(value)


def sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Invalid SHA256")
    return value


def local_path(value, base=None, directory=False, new=False):
    if not isinstance(value, (str, Path)) or not str(value) or "\\" in str(value):
        raise ValueError("Invalid local path")
    supplied = Path(value)
    if any(part in ("..", ".") for part in str(value).split("/")):
        raise ValueError("Path traversal is prohibited")
    path = supplied if supplied.is_absolute() else (base or ROOT) / supplied
    # Check components before resolving, including nonexistent output parents.
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError("Symlink paths prohibited")
    path = path.resolve()
    allowed = (ROOT / "artifacts" / "benchmarks").resolve()
    if not path.is_relative_to(allowed) or path == allowed:
        raise ValueError("Paths must be beneath artifacts/benchmarks")
    if new:
        if path.exists():
            raise ValueError("Output directory must be new")
    elif directory:
        if not path.is_dir():
            raise ValueError("Missing run directory")
    elif not path.is_file():
        raise ValueError("Missing artifact")
    return path


def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def guarded_json(text):
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 128:
                raise ValueError("JSON depth exceeds 128")
        elif char in "]}":
            depth -= 1
    def float_value(value):
        return finite(float(value), "JSON float")
    return json.loads(text, object_pairs_hook=strict_pairs, parse_float=float_value,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


class Reader:
    def __init__(self):
        self.receipts, self.bytes = {}, 0

    def hash_budget(self,path):
        size=path.stat().st_size
        if size>LIMITS["source_file_bytes"] or (str(path) not in self.receipts and
                sum(Path(item).stat().st_size for item in self.receipts)+size>LIMITS["aggregate_hashed_bytes"]):
            raise ValueError("Hashed input byte budget exceeded")

    def read(self, path, expected=None):
        self.hash_budget(path)
        size = path.stat().st_size
        if size > LIMITS["json_bytes"]:
            raise ValueError("JSON exceeds file budget")
        if str(path) not in self.receipts:
            self.bytes += size
        if self.bytes > LIMITS["aggregate_json_bytes"]:
            raise ValueError("JSON exceeds aggregate budget")
        before = digest(path)
        if expected is not None and before != sha(expected):
            raise ValueError("Artifact hash mismatch")
        result = guarded_json(path.read_text())
        if not isinstance(result, dict) or digest(path) != before:
            raise ValueError("Unstable or nonobject JSON")
        self.receipts[str(path)] = before
        return result

    def verify(self):
        if sum(Path(path).stat().st_size for path in self.receipts)>LIMITS["aggregate_hashed_bytes"]:
            raise ValueError("Aggregate hashed input budget exceeded")
        if any(digest(Path(path)) != value for path, value in self.receipts.items()):
            raise ValueError("Input changed during evaluation")


def optimal_matching(first, second, score):
    """Independent min-cost flow: maximum cardinality, then maximum score."""
    if max(len(first), len(second)) > LIMITS["items"]:
        raise ValueError("Matching item budget exceeded")
    n, m = len(first), len(second)
    sink = n + m + 1
    graph = [[] for _ in range(sink + 1)]
    def edge(a, b, cost):
        graph[a].append([b, len(graph[b]), 1, cost])
        graph[b].append([a, len(graph[a])-1, 0, -cost])
    for i in range(n):
        edge(0, i+1, 0.)
    for j in range(m):
        edge(n+j+1, sink, 0.)
    candidates = []
    for i, a in enumerate(first):
        for j, b in enumerate(second):
            value = score(a, b)
            if value is not None:
                if len(candidates) >= LIMITS["matching_edges"]:
                    raise ValueError("Matching edge budget exceeded")
                value = finite(value, "matching score")
                if not 0 <= value <= 1:
                    raise ValueError("Matching score outside 0..1")
                candidates.append((i, j, len(graph[i+1]), value))
                edge(i+1, n+j+1, 1-value)
    potential = [0.] * len(graph)
    while True:
        distances, previous = [math.inf] * len(graph), [None] * len(graph)
        distances[0] = 0.
        heap = [(0., 0)]
        while heap:
            distance, node = heapq.heappop(heap)
            if distance > distances[node] + 1e-12:
                continue
            for k, (target, _, capacity, cost) in enumerate(graph[node]):
                if not capacity:
                    continue
                proposed = distance + max(0., cost + potential[node] - potential[target])
                if proposed < distances[target] - 1e-12:
                    distances[target], previous[target] = proposed, (node, k)
                    heapq.heappush(heap, (proposed, target))
        if previous[sink] is None:
            break
        for i, distance in enumerate(distances):
            if math.isfinite(distance):
                potential[i] += distance
        node = sink
        while node:
            parent, k = previous[node]
            item = graph[parent][k]
            item[2] = 0
            graph[node][item[1]][2] = 1
            node = parent
    return [(i, j, value) for i,j,k,value in candidates if graph[i+1][k][2] == 0]


def prf(reference_count, estimate_count, matches):
    tp = len(matches)
    empty = reference_count == estimate_count == 0
    precision = None if empty else tp / estimate_count if estimate_count else 0.
    recall = None if empty else tp / reference_count if reference_count else 0.
    f1 = None if empty else 2*tp/(reference_count+estimate_count)
    return {"tp": tp, "fp": estimate_count-tp, "fn": reference_count-tp,
            "precision": precision, "recall": recall, "f1": f1,
            "status": "not_applicable_empty_reference_and_estimate" if empty else
                      "empty_reference_false_positives_visible" if not reference_count else "evaluated"}


def errors(values):
    absolute = sorted(abs(finite(value)) for value in values)
    return {"sample_count": len(absolute), "mean_absolute_seconds": statistics.mean(absolute) if absolute else None,
            "median_absolute_seconds": statistics.median(absolute) if absolute else None,
            "descriptive_p95_absolute_seconds": absolute[math.ceil(.95*len(absolute))-1] if absolute else None,
            "percentile_qualification": "descriptive_sample_quantile_not_confidence"}


def times(values, duration):
    if not isinstance(values, list) or len(values) > LIMITS["items"]:
        raise ValueError("Invalid timestamp array")
    result = [finite(value, "timestamp") for value in values]
    if any(not 0 <= value <= duration for value in result):
        raise ValueError("Timestamp outside generated source")
    return result


def boundaries(reference, estimates, duration, tolerance):
    refs = [x for x in times(reference, duration) if 0 < x < duration]
    preds = [x for x in times(estimates, duration) if 0 < x < duration]
    pairs = optimal_matching(refs, preds, lambda a,b: max(0., 1-abs(a-b)/(tolerance+1e-9))
                             if abs(a-b) <= tolerance+1e-9 else None)
    offsets = [preds[j]-refs[i] for i,j,_ in pairs]
    return {**prf(len(refs),len(preds),pairs), "tolerance_seconds": tolerance,
            "matches": [{"reference_seconds": refs[i], "estimate_seconds": preds[j],
                         "signed_offset_seconds": preds[j]-refs[i]} for i,j,_ in pairs],
            "unmatched_reference": [a for i,a in enumerate(refs) if i not in {x[0] for x in pairs}],
            "unmatched_estimates": [a for j,a in enumerate(preds) if j not in {x[1] for x in pairs}],
            "displacement": errors(offsets)}


def span(value, duration):
    if isinstance(value, dict):
        value = [value.get("start_seconds"), value.get("end_seconds")]
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("Invalid span")
    a,b = (finite(x, "span endpoint") for x in value)
    if not 0 <= a < b <= duration:
        raise ValueError("Invalid source span extent")
    return [a,b]


def iou(a,b):
    return max(0., min(a[1],b[1])-max(a[0],b[0])) / (max(a[1],b[1])-min(a[0],b[0]))


def span_metrics(reference, estimates, duration, threshold):
    refs, preds = [span(x,duration) for x in reference], [span(x,duration) for x in estimates]
    pairs = optimal_matching(refs,preds,lambda a,b: iou(a,b) if iou(a,b)+1e-12 >= threshold else None)
    return {**prf(len(refs),len(preds),pairs), "iou_threshold": threshold,
            "mean_matched_iou": statistics.mean(x[2] for x in pairs) if pairs else None,
            "matches": [{"reference_index": i,"estimate_index": j,"iou": value} for i,j,value in pairs]}


def pair_spans(item, duration, comparison=False):
    if comparison:
        item = item["spans"]
    if "first_span_seconds" in item:
        return [span(item["first_span_seconds"],duration),span(item["second_span_seconds"],duration)]
    return [span([item["first_start_seconds"],item["first_end_seconds"]],duration),
            span([item["second_start_seconds"],item["second_end_seconds"]],duration)]


def recurrence_metrics(reference, estimates, duration, threshold):
    refs, preds = [pair_spans(x,duration) for x in reference], [pair_spans(x,duration) for x in estimates]
    def score(a,b):
        scores = [iou(a[k],b[k]) for k in (0,1)]
        return statistics.mean(scores) if min(scores)+1e-12 >= threshold else None
    pairs = optimal_matching(refs,preds,score)
    return {**prf(len(refs),len(preds),pairs), "iou_threshold": threshold,
            "matches": [{"reference_index":i,"estimate_index":j,"mean_iou":value} for i,j,value in pairs]}


def interpolate(time, points):
    if not points or time < points[0][0]-1e-9 or time > points[-1][0]+1e-9:
        return None
    index = bisect.bisect_right([a for a,_ in points],time)
    if index == len(points):
        return points[-1][1]
    if index == 0:
        return points[0][1]
    a,b = points[index-1],points[index]
    return a[1]+(time-a[0])/(b[0]-a[0])*(b[1]-a[1])


def alignment_metrics(reference, comparison, duration):
    warp = reference.get("warp_reference")
    if not isinstance(warp, dict):
        return {"status":"excluded_no_generated_warp"}
    if warp.get("mapping_kind") not in ("affine","piecewise_linear"):
        raise ValueError("Unsupported generated warp mapping kind")
    a,b = pair_spans(reference,duration)
    xs,ys = times(warp.get("source_times_seconds"),duration),times(warp.get("target_times_seconds"),duration)
    if len(xs) != len(ys) or not 2 <= len(xs) <= LIMITS["path_landmarks"] or any(x>=y for x,y in zip(xs,xs[1:])) or any(x>=y for x,y in zip(ys,ys[1:])):
        raise ValueError("Generated warp landmarks must be equal-length strictly monotonic arrays")
    if any(not a[0]<=x<=a[1] for x in xs) or any(not b[0]<=y<=b[1] for y in ys):
        raise ValueError("Generated warp outside recurrence spans")
    truth_points = [(x-a[0],y-b[0]) for x,y in zip(xs,ys)]
    rates = [(y1-y0)/(x1-x0) for (x0,y0),(x1,y1) in zip(truth_points,truth_points[1:])]
    predicted_spans = pair_spans(comparison,duration,True)
    path = comparison.get("path_audio_relative_seconds",[])
    if not isinstance(path,list) or len(path)>LIMITS["path_landmarks"]:
        raise ValueError("Comparison path landmark budget exceeded")
    # Collapse duplicate source coordinates only for interpolation; retain receipt path.
    grouped = {}
    for item in path:
        x,y = finite(item["first_seconds"]),finite(item["second_seconds"])
        if not predicted_spans[0][0]<=x<=predicted_spans[0][1] or not predicted_spans[1][0]<=y<=predicted_spans[1][1]:
            raise ValueError("Comparison path outside declared windows")
        grouped.setdefault(x-a[0],[]).append(y-b[0])
    points = [(x,statistics.mean(values)) for x,values in grouped.items()]
    if any(x1<=x0 or y1<y0 for (x0,y0),(x1,y1) in zip(points,points[1:])):
        raise ValueError("Comparison path must be monotonic")
    qualified = comparison.get("status") == "aligned_hypothesis"
    estimates = [interpolate(x,points) if qualified else None for x,_ in truth_points]
    residuals = [estimate-y for estimate,(_,y) in zip(estimates,truth_points) if estimate is not None]
    # Existing producer median is a median of y-x, not an affine intercept.
    raw_offsets = [y-x for x,y in truth_points]
    expected_median = statistics.median(raw_offsets)
    estimated_median = comparison.get("median_relative_offset_seconds") if qualified else None
    if estimated_median is not None:
        estimated_median=finite(estimated_median)
    expected_rate = rates[0] if warp.get("mapping_kind") == "affine" and max(rates)-min(rates)<1e-8 else None
    estimated_rate = comparison.get("interior_rate_median") if qualified else None
    if estimated_rate is not None:
        estimated_rate=finite(estimated_rate)
    intervals=[]
    for k,rate in enumerate(rates):
        estimate = ((estimates[k+1]-estimates[k])/(truth_points[k+1][0]-truth_points[k][0])
                    if estimates[k] is not None and estimates[k+1] is not None else None)
        intervals.append({"reference_rate":rate,"estimated_rate":estimate,
            "absolute_ratio_error":abs(estimate-rate) if estimate is not None else None})
    post = errors(residuals)
    changed_landmarks=[k for k,value in enumerate(raw_offsets) if abs(value)>=.06-1e-9]
    covered_changed_landmarks=[k for k in changed_landmarks if estimates[k] is not None]
    changed_intervals=[k for k,value in enumerate(rates) if abs(value-1)>=.10-1e-9]
    covered_changed_intervals=[k for k in changed_intervals if estimates[k] is not None and estimates[k+1] is not None]
    absorbed=any(abs(estimates[k]-truth_points[k][1])<.020 for k in covered_changed_landmarks) or any(
        abs(estimates[k]-truth_points[k][1])<.020 and abs(estimates[k+1]-truth_points[k+1][1])<.020
        for k in covered_changed_intervals)
    change_status=("covered_change_absorption_diagnostic" if absorbed else
                   "unknown_generated_change_outside_path_support" if (changed_landmarks or changed_intervals) and
                   not (covered_changed_landmarks or covered_changed_intervals) else "covered_change_not_absorbed" if
                   (covered_changed_landmarks or covered_changed_intervals) else "no_large_generated_landmark_or_rate_change")
    return {"status":"evaluated" if qualified else "alignment_abstained", "producer_status":comparison.get("status"),
            "reference_relative_shift_seconds":truth_points[0][1]-truth_points[0][0],
            "reference_median_relative_offset_seconds":expected_median,
            "estimated_median_relative_offset_seconds":estimated_median,
            "median_relative_offset_absolute_error_seconds":abs(estimated_median-expected_median) if estimated_median is not None else None,
            "reference_affine_rate":expected_rate,"estimated_interior_rate":estimated_rate,
            "absolute_ratio_error":abs(estimated_rate-expected_rate) if estimated_rate is not None and expected_rate is not None else None,
            "relative_rate_percent_error":100*abs(estimated_rate/expected_rate-1) if estimated_rate is not None and expected_rate is not None else None,
            "piecewise_interval_rates":intervals,"landmark_count":len(xs),"covered_landmark_count":len(residuals),
            "landmark_coverage":len(residuals)/len(xs),"warped_landmark_error":post,
            "raw_prewarp_landmark_offsets_seconds":raw_offsets,"postwarp_landmark_residuals_seconds":residuals,
            "detected_motif_timing": {"raw_prewarp_detected_offsets_seconds":[
                finite(item["observed_second_offset_seconds"])-finite(item["first_offset_seconds"])
                for item in comparison.get("motif_comparison",{}).get("matches",[])],
                "postwarp_detected_residuals_seconds":[finite(item["alignment_residual_seconds"])
                for item in comparison.get("motif_comparison",{}).get("matches",[])],
                "qualification":"producer_detected_attack_matches_not_generated_note_correspondence"},
            "dtw_absorbed_generated_timing_change": absorbed,
            "timing_change_coverage":{"status":change_status,"changed_landmark_count":len(changed_landmarks),
                "covered_changed_landmark_count":len(covered_changed_landmarks),"changed_rate_interval_count":len(changed_intervals),
                "covered_changed_rate_interval_count":len(covered_changed_intervals)},
            "warning":"Small postwarp residual does not erase generated timing variation or establish a performance error."}


def unsupported_claims(payload):
    count=0
    if isinstance(payload,dict):
        if any(payload.get(key) is True for key in ("performance_issue_confirmed","note_correctness_confirmed",
                "missed_notes_confirmed","extra_notes_confirmed")):
            count+=1
        if payload.get("performance_grade") not in (None,"not_graded","unknown","not_assessed"):
            count+=1
        count+=sum(unsupported_claims(value) for value in payload.values())
    elif isinstance(payload,list):
        count+=sum(unsupported_claims(value) for value in payload)
    return count


def source_validation(truth, bank, reader):
    if truth.get("schema_version") != 2 or truth.get("kind") != "synthetic_generated_signal_and_score_truth" or truth.get("ground_truth_scope") != "generator_only_not_musician":
        raise ValueError("Only schema2 generator-only truth is accepted")
    source=truth["source"]
    path=local_path(source["path"],bank)
    reader.hash_budget(path)
    if path.stat().st_size>LIMITS["source_file_bytes"]:
        raise ValueError("Source waveform exceeds byte budget")
    expected=sha(source["sha256"])
    if digest(path)!=expected:
        raise ValueError("Generated source hash mismatch")
    with wave.open(str(path),"rb") as handle:
        extent=(handle.getframerate(),handle.getnchannels(),handle.getnframes())
    declared=(source["sample_rate"],source["channels"],source["sample_count"])
    if extent!=declared or any(isinstance(x,bool) or not isinstance(x,int) for x in declared):
        raise ValueError("Generated native sample extent mismatch")
    if not 8000<=extent[0]<=192000 or not 1<=extent[1]<=4 or not 0<extent[2]<=extent[0]*120:
        raise ValueError("Generated PCM bounds exceeded")
    duration=extent[2]/extent[0]
    declared_duration=source.get("duration_seconds",source.get("duration"))
    if abs(finite(declared_duration)-duration)>1/extent[0] or source.get("audio_start_seconds")!=0 or not source.get("origin_evidence"):
        raise ValueError("Unverified generated source origin/duration")
    reader.receipts[str(path)]=expected
    artifacts=truth.get("artifacts",{})
    if not isinstance(artifacts,dict) or len(artifacts)>8:
        raise ValueError("Malformed generated component receipts")
    for receipt in artifacts.values():
        if not isinstance(receipt,dict):
            raise ValueError("Malformed generated component receipt")
        component=local_path(receipt["path"],bank)
        reader.hash_budget(component)
        if component.stat().st_size>LIMITS["source_file_bytes"] or digest(component)!=sha(receipt["sha256"]):
            raise ValueError("Generated component hash/size mismatch")
        reader.receipts[str(component)]=receipt["sha256"]
    return duration,expected


def artifact(receipt,base,reader,source_hash,kind):
    if not isinstance(receipt,dict):
        raise ValueError("Missing pilot artifact receipt")
    path=local_path(receipt["path"],base)
    payload=reader.read(path,receipt["sha256"])
    identity=payload.get("analysis_input_sha256") if kind=="comparisons" else payload.get("source",{}).get("sha256")
    if identity!=source_hash or (kind=="comparisons" and payload.get("source_sha256")!=source_hash):
        raise ValueError("Pilot source identity mismatch")
    analyzed_path=payload.get("source",{}).get("path")
    if analyzed_path is not None:
        analyzed_path=local_path(analyzed_path,path.parent)
        reader.hash_budget(analyzed_path)
        if digest(analyzed_path)!=source_hash:
            raise ValueError("Discovery audio input changed")
        reader.receipts[str(analyzed_path)]=source_hash
    if kind=="phrases" and not isinstance(payload.get("observations"),dict):
        raise ValueError("Malformed phrase discovery observations")
    if kind=="analysis" and not isinstance(payload.get("events"),list):
        raise ValueError("Malformed rhythm discovery events")
    start=payload.get("source",{}).get("audio_stream_start_seconds",0) if kind=="phrases" else payload.get("timeline",{}).get("audio_stream_start_seconds",0)
    if finite(start,"pilot source origin") != 0:
        raise ValueError("Pilot must use generated source-sample zero")
    settings=payload.get("settings",payload.get("configuration",payload.get("analysis",{})))
    if not isinstance(settings,dict):
        raise ValueError("Invalid producer settings")
    computed=encoded_hash(settings)
    producer_declared=payload.get("settings_sha256")
    declared=producer_declared if producer_declared is not None else receipt.get("settings_sha256")
    if declared is not None and sha(declared)!=computed:
        raise ValueError("Pilot settings hash mismatch")
    for name,value in payload.get("artifact_hashes",{}).items():
        upstream=local_path(name,path.parent)
        reader.hash_budget(upstream)
        if upstream.stat().st_size>LIMITS["json_bytes"]:
            raise ValueError("Comparison upstream exceeds JSON byte budget")
        if digest(upstream)!=sha(value):
            raise ValueError("Stale comparison upstream")
        reader.receipts[str(upstream)]=value
    return payload,{"path":str(path),"sha256":reader.receipts[str(path)],"settings_sha256":computed,
                    "settings_binding":"producer_receipt_verified" if producer_declared is not None else
                    "pilot_receipt_verified_producer_receipt_not_recorded" if declared is not None else "derived_payload_not_producer_receipt"}


def evaluate(fixture_index, pilot_index):
    fixture_index=local_path(fixture_index)
    pilot_index=local_path(pilot_index)
    reader=Reader()
    bank=reader.read(fixture_index)
    pilot=reader.read(pilot_index)
    registry=ROOT/"program/instrument.json"
    registry_hash=digest(registry)
    if bank.get("schema_version")!=2 or bank.get("suite")!="technical-v2" or pilot.get("schema_version")!=1:
        raise ValueError("Unsupported bank/pilot schema")
    if pilot.get("bank_index_sha256")!=digest(fixture_index) or bank.get("instrument_registry_sha256")!=registry_hash or pilot.get("instrument_registry_sha256")!=registry_hash:
        raise ValueError("Bank/instrument context hash mismatch")
    cases, jobs=bank.get("cases"),pilot.get("cases")
    if not isinstance(cases,list) or not 1<=len(cases)<=LIMITS["fixtures"] or bank.get("case_count")!=len(cases) or not isinstance(jobs,list) or len(jobs)>LIMITS["fixtures"]:
        raise ValueError("Fixture count budget mismatch")
    if any(not isinstance(item,dict) for item in cases+jobs):
        raise ValueError("Malformed bank/pilot case")
    ids=[item.get("id") for item in cases]
    job_ids=[item.get("id") for item in jobs]
    if any(not isinstance(value,str) or not value or len(value)>64 for value in ids+job_ids) or len(set(ids))!=len(ids) or len(set(job_ids))!=len(job_ids) or set(job_ids)!=set(ids):
        raise ValueError("Pilot must cover each unique bank fixture exactly once")
    rows=[]
    duration_sum=0.
    for case in cases:
        truth_path=local_path(case["truth"],fixture_index.parent)
        truth=reader.read(truth_path,case["truth_sha256"])
        for key in ("instrument_registry_sha256","configuration_sha256","generator_sha256","legacy_generator_sha256"):
            if key in bank and (sha(bank[key])!=truth.get(key)):
                raise ValueError("Generated truth context differs from bank")
        duration,source_hash=source_validation(truth,fixture_index.parent,reader)
        if abs(finite(case["duration_seconds"])-duration)>1e-6:
            raise ValueError("Case duration mismatch")
        duration_sum+=duration
        if duration_sum>LIMITS["duration_seconds"]+1e-9:
            raise ValueError("Aggregate duration budget exceeded")
        job=next(item for item in jobs if item["id"]==case["id"])
        run_dir=local_path(job["run_dir"],pilot_index.parent,directory=True)
        phrases,phrase_receipt=artifact(job["phrases"],pilot_index.parent,reader,source_hash,"phrases")
        analysis,analysis_receipt=artifact(job["analysis"],pilot_index.parent,reader,source_hash,"analysis")
        comparison,comparison_receipt=artifact(job["comparisons"],pilot_index.parent,reader,source_hash,"comparisons") if job.get("comparisons") else ({"comparisons":[],"flags":[]},None)
        for receipt in (phrase_receipt,analysis_receipt,comparison_receipt):
            if receipt and not Path(receipt["path"]).is_relative_to(run_dir):
                raise ValueError("Pilot artifact is outside its named run directory")
        observations=phrases.get("observations",{})
        segments=observations.get("segment_candidates",[])
        if not isinstance(segments,list) or len(segments)>LIMITS["items"]:
            raise ValueError("Segment budget exceeded")
        references=truth.get("phrase_spans_seconds")
        boundary_refs=truth.get("boundaries_seconds")
        # Nullable semantic references remain excluded, not automatic zero recall.
        estimates=[span(item,duration) for item in segments]
        boundary_estimates=sorted(set(x for item in estimates for x in item))
        levels=sorted(set(item.get("hierarchy_level","unclassified") for item in references if isinstance(item,dict))) if references else []
        if len(levels)>1:
            span_results={level:[span_metrics([item for item in references if item.get("hierarchy_level")==level],
                [item for item in segments if item.get("hierarchy_level")==level],duration,t) for t in SETTINGS["span_iou_thresholds"]] for level in levels}
        else:
            span_results={"single_declared_level":[span_metrics(references or [],estimates,duration,t) for t in SETTINGS["span_iou_thresholds"]]} if references is not None else None
        recurrences=observations.get("recurrence_candidates",[])
        reference_pairs=truth.get("recurrence_pairs",[])
        if not isinstance(reference_pairs,list) or len(reference_pairs)>LIMITS["items"]:
            raise ValueError("Generated recurrence budget exceeded")
        # Validate generated landmarks even if discovery found no comparable pair.
        for reference_pair in reference_pairs:
            ref_spans=pair_spans(reference_pair,duration)
            if ref_spans[0][1]>ref_spans[1][0]:
                raise ValueError("Generated recurrence windows overlap or are reversed")
            dummy={"status":"not_evaluated","spans":{"first_start_seconds":ref_spans[0][0],
                "first_end_seconds":ref_spans[0][1],"second_start_seconds":ref_spans[1][0],
                "second_end_seconds":ref_spans[1][1]},"path_audio_relative_seconds":[]}
            alignment_metrics(reference_pair,dummy,duration)
        pair_results=[recurrence_metrics(reference_pairs,recurrences,duration,t) for t in SETTINGS["span_iou_thresholds"]]
        comparisons=comparison.get("comparisons",[])
        if not isinstance(comparisons,list) or len(comparisons)>LIMITS["comparisons"]:
            raise ValueError("Comparison count budget exceeded")
        mapped=recurrence_metrics(reference_pairs,[item["spans"] for item in comparisons],duration,.5)
        alignments=[{"reference_pair_index":item["reference_index"],"comparison_index":item["estimate_index"],
                    **alignment_metrics(reference_pairs[item["reference_index"]],comparisons[item["estimate_index"]],duration)} for item in mapped["matches"]]
        score=truth.get("generated_score",{})
        events=score.get("events",[])
        if not isinstance(events,list) or len(events)>LIMITS["items"]:
            raise ValueError("Generated attack event budget exceeded")
        event_refs=[]
        event_ids=[]
        for event in events:
            if not isinstance(event,dict):
                raise ValueError("Malformed generated score event")
            if score.get("status")=="complete_generated_score" or "onset_native_sample" in event:
                identity=event.get("id")
                native=event.get("onset_native_sample")
                onset=event.get("onset_source_seconds")
                if not isinstance(identity,str) or not identity or identity in event_ids:
                    raise ValueError("Invalid or duplicate generated event ID")
                event_ids.append(identity)
                if (native is None)!=(onset is None):
                    raise ValueError("Generated omitted onset must have both axes null")
                if native is not None and (isinstance(native,bool) or not isinstance(native,int) or
                    not 0<=native<truth["source"]["sample_count"] or
                    abs(finite(onset)-native/truth["source"]["sample_rate"])>1e-9):
                    raise ValueError("Generated onset source/native axes disagree")
            if event.get("articulation") in ("picked_attack","pick","picked") and event.get("injected_edit") not in ("omit","omitted"):
                onset=event.get("onset_source_seconds",event.get("observed_source_seconds"))
                if onset is not None:
                    event_refs.append(onset)
        # Per-attack renderer timing injections need not change the phrase's
        # ideal geometric warp. Retain that separate context in concealment checks.
        for alignment in alignments:
            target=pair_spans(reference_pairs[alignment["reference_pair_index"]],duration)[1]
            injections=[finite(event["injected_offset_seconds"]) for event in events
                if event.get("onset_source_seconds") is not None and target[0]<=event["onset_source_seconds"]<target[1]
                and event.get("injected_offset_seconds") is not None]
            alignment["generated_attack_injected_offsets_seconds"]=injections
            alignment["generated_attack_shift_scope"]="renderer_operations_only_not_warp_absorption_proof"
        onset_context=analysis.get("librosa") or {}
        detector=(onset_context.get("onsets") or {}).get("superflux") or (onset_context.get("onsets") or {}).get("spectral_flux")
        attack_estimates=detector.get("audio_relative_seconds",[]) if isinstance(detector,dict) else [item["audio_relative_seconds"] for item in analysis.get("events",[]) if item.get("kind") in ("broadband_attack","spectral_flux_attack","broadband_attack_candidate")]
        attack_reference_known=bool(events) or score.get("status") in ("complete_generated_score","complete") or score.get("attack_reference_known") is True
        if score.get("status")=="legacy_attack_times_only_not_full_score":
            legacy=truth.get("guitar_onsets_seconds")
            if legacy is not None:
                event_refs=legacy
                attack_reference_known=True
        reasons=Counter()
        if not comparisons:
            reasons["no_discovered_recurrence_comparison"]=1
        for item in comparisons:
            motif=item.get("motif_comparison",{})
            for reason in motif.get("abstention_reasons",[]):
                reasons[reason]+=1
            if item.get("status")!="aligned_hypothesis":
                reasons[str(item.get("status","unknown"))]+=1
        claims=sum(unsupported_claims(payload) for payload in (phrases,analysis,comparison))
        rows.append({"id":case["id"],"duration_seconds":duration,"source_sha256":source_hash,"truth_sha256":digest(truth_path),
            "receipts":{"phrases":phrase_receipt,"analysis":analysis_receipt,"comparisons":comparison_receipt},
            "boundary_metrics":[boundaries(boundary_refs,boundary_estimates,duration,t) for t in SETTINGS["boundary_tolerances_seconds"]] if boundary_refs is not None else None,
            "span_metrics":span_results,"recurrence_metrics":pair_results,"relative_alignment_metrics":alignments,
            "alignment_unmatched_reference_count":mapped["fn"],"alignment_unmatched_estimate_count":mapped["fp"],
            "attack_detection_metrics":[boundaries(event_refs,attack_estimates,duration,t) for t in SETTINGS["boundary_tolerances_seconds"]] if attack_reference_known else None,
            "abstention_counts":dict(reasons),"comparison_count":len(comparisons),
            "unsupported_confirmed_claim_count":claims,"expected_abstention_reasons":truth.get("expected_abstention_reasons",[]),
            "excluded_semantic_boundaries":boundary_refs is None,"excluded_semantic_spans":references is None})
    if abs(finite(bank.get("total_duration_seconds"))-duration_sum)>1e-6:
        raise ValueError("Bank total duration mismatch")
    reader.verify()
    if digest(registry)!=registry_hash:
        raise ValueError("Instrument context changed")
    def aggregate_scores(applicable,total):
        tp,fp,fn=(sum(item[key] for item in applicable) for key in ("tp","fp","fn"))
        values=[item["f1"] for item in applicable if item["f1"] is not None]
        return {**prf(tp+fn,tp+fp,[(0,0,0)]*tp),
                "macro_f1":statistics.mean(values) if values else None,
                "macro_applicable_fixture_count":len(values),"excluded_fixture_count":total-len(applicable)}
    aggregate=[{"tolerance_seconds":t,**aggregate_scores(
        [row["boundary_metrics"][k] for row in rows if row["boundary_metrics"] is not None],len(rows))}
        for k,t in enumerate(SETTINGS["boundary_tolerances_seconds"])]
    attack_aggregate=[{"tolerance_seconds":t,**aggregate_scores(
        [row["attack_detection_metrics"][k] for row in rows if row["attack_detection_metrics"] is not None],len(rows))}
        for k,t in enumerate(SETTINGS["boundary_tolerances_seconds"])]
    recurrence_aggregate=[{"iou_threshold":t,**aggregate_scores([row["recurrence_metrics"][k] for row in rows],len(rows))}
        for k,t in enumerate(SETTINGS["span_iou_thresholds"])]
    levels=sorted({level for row in rows for level in (row["span_metrics"] or {})})
    span_aggregate={level:[{"iou_threshold":t,**aggregate_scores(
        [row["span_metrics"][level][k] for row in rows if row["span_metrics"] is not None and level in row["span_metrics"]],len(rows))}
        for k,t in enumerate(SETTINGS["span_iou_thresholds"])] for level in levels}
    hard_gates=all(row["unsupported_confirmed_claim_count"]==0 for row in rows)
    return {"schema_version":1,"status":"generated_fixture_calibration" if hard_gates else "generated_fixture_calibration_failed_hard_gates","ground_truth_scope":"generator_only_not_musician",
        "source_read":True,"source_audio_decoded":False,"inference_invoked":False,"listening_acceptance":False,
        "settings":SETTINGS,"settings_sha256":encoded_hash(SETTINGS),"evaluator_sha256":digest(Path(__file__)),
        "bank_index_sha256":digest(fixture_index),"pilot_index_sha256":digest(pilot_index),
        "instrument_registry_sha256":registry_hash,"input_hashes":reader.receipts,"fixtures":rows,
        "fixture_count":len(rows),"total_duration_seconds":duration_sum,"boundary_aggregate":aggregate,
        "attack_aggregate":attack_aggregate,"span_aggregate":span_aggregate,"recurrence_aggregate":recurrence_aggregate,
        "unsupported_confirmed_claim_count":sum(row["unsupported_confirmed_claim_count"] for row in rows),
        "hard_gates_passed":hard_gates,
        "limitations":["Audio-derived phrase F1/IoU are visible baselines, not musician or listening acceptance.",
            "Generated landmarks are consumed only by this evaluator after discovery and DTW.",
            "Median y-minus-x is not an affine shift intercept when rate differs; both are labeled separately.",
            "Unknown semantic references are excluded; sparse alignment coverage never counts as zero error."]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-index",required=True,type=Path)
    parser.add_argument("--pilot-index",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--summary",action="store_true",help="Compact stdout after full validation (default also compact)")
    args=parser.parse_args()
    try:
        destination=local_path(args.output,new=True)
        result=evaluate(args.fixture_index,args.pilot_index)
        text=json.dumps(result,indent=2,allow_nan=False)+"\n"
        if len(text.encode())>LIMITS["json_bytes"]:
            raise ValueError("Output exceeds JSON budget")
        destination.mkdir(parents=True,mode=0o700)
        path=destination/"phrase-evaluation.json"
        pending=destination/".phrase-evaluation.pending"
        pending.write_text(text)
        os.chmod(pending,0o600)
        pending.replace(path)
        summary={key:result[key] for key in ("status","fixture_count","total_duration_seconds","unsupported_confirmed_claim_count",
            "hard_gates_passed","source_read","source_audio_decoded","inference_invoked","ground_truth_scope","listening_acceptance")}
        summary["evaluation_json"]=str(path)
        print(json.dumps(summary))
        if not result["hard_gates_passed"]:
            print(f"phrase evaluate: unsupported confirmed claims; diagnostic receipt retained at {path}",file=sys.stderr)
        return 0 if result["hard_gates_passed"] else 1
    except (OSError,ValueError,TypeError,KeyError,wave.Error,ZeroDivisionError) as exc:
        print(f"phrase evaluate: {exc}",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
