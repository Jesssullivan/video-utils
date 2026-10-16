#!/usr/bin/env python3
"""Operator onset labels versus detector onset candidates (D6, docs/spec/ONSET_LABELS.md).

Joins user-authored `onset` labels from a run's v2 annotation store to each detector
`*_attack_candidate` kind in the run's bound analysis.json, one-to-one, at 10, 25 and
50 ms. Pure metadata arithmetic: no audio is read, no detector runs, no label or
detection is moved. Abstains below 10 scored labels; never a note-correctness verdict.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def read_json(path: Path, limit=5_000_000):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Missing, symlinked or oversized JSON input")
    return json.loads(path.read_text())


def ordered_pairs(first, second, tolerance):
    """One-to-one matching of two sorted time lists: maximum matched count, then
    minimum total absolute offset. Returns (first_index, second_index) pairs in order.

    On a line, any maximum matching under an absolute tolerance can be uncrossed
    without losing a pair or adding offset, so this ordered dynamic programme is
    optimal among all one-to-one matchings. Ties keep the earlier option.

    This is the same programme as scripts/benchmark.py event_metrics_v2, whose bytes
    are frozen by the admitted holdout plan; a test checks both agree.
    """
    scores=[[(0,0.0)]*(len(second)+1) for _ in range(len(first)+1)]
    back={}
    for i,a in enumerate(first,1):
        for j,b in enumerate(second,1):
            options=[(scores[i-1][j],(i-1,j)),(scores[i][j-1],(i,j-1))]
            if abs(b-a)<=tolerance:
                count,cost=scores[i-1][j-1]
                options.append(((count+1,cost+abs(b-a)),(i-1,j-1)))
            score,previous=max(options,key=lambda item:(item[0][0],-item[0][1]))
            scores[i][j],back[i,j]=score,previous
    i,j=len(first),len(second)
    pairs=[]
    while i and j:
        previous=back[i,j]
        if previous==(i-1,j-1):
            pairs.append((i-1,j-1))
        i,j=previous
    pairs.reverse()
    return pairs


ONSET_TOLERANCES_SECONDS=(.010,.025,.050)
ONSET_MIN_OPERATOR_LABELS=10
ONSET_LABEL_SCHEMA="onset-label-benchmark-v1"
ONSET_OPERATOR_BASES=("operator_assertion","operator_context")
ONSET_TIME_AXES=(("source_timeline_seconds","uncompensated"),
                 ("delay_compensated_source_timeline_seconds","synthetic_probe_delay_compensated"))
ONSET_MAX_LABELS=512
ONSET_MAX_CANDIDATES=4096
ONSET_CLAIMS={"note_correctness":"not_assessed_no_approved_reference",
              "missed_or_extra_notes":"not_assessed_no_approved_reference",
              "musical_verdict":"not_established",
              "operator_label_timing_error":"unknown_not_calibrated",
              "physical_capture_latency":"uncalibrated",
              "detector_identity":"each detector kind is scored separately and never merged",
              "interpretation":"agreement between operator-heard onset times and detector onset candidates; not a performance grade"}


def _finite_number(value):
    return value if type(value) in (int,float) and math.isfinite(value) else None


def onset_operator_labels(store):
    """Operator onset points and fully-labelled segments from a v2 store dict.

    Accepted: kind onset/onset_segment, reported_by.actor operator, basis
    operator_assertion/operator_context, status other than dismissed_candidate.
    Everything else is counted by reason and never scored.
    """
    labels,segments,excluded=[],[],{}
    def skip(reason):
        excluded[reason]=excluded.get(reason,0)+1
    records=store.get("annotations") if isinstance(store,dict) and isinstance(store.get("annotations"),list) else []
    for item in records:
        if not isinstance(item,dict) or item.get("kind") not in ("onset","onset_segment"):
            continue
        span=item.get("source_span") if isinstance(item.get("source_span"),dict) else {}
        start,end=_finite_number(span.get("start_seconds")),_finite_number(span.get("end_seconds"))
        reported=item.get("reported_by") if isinstance(item.get("reported_by"),dict) else {}
        if reported.get("actor")!="operator":
            skip("non_operator_actor")
        elif item.get("basis") not in ONSET_OPERATOR_BASES:
            skip("basis_not_operator")
        elif item.get("status")=="dismissed_candidate":
            skip("dismissed_candidate")
        elif start is None or end is None:
            skip("source_span_invalid")
        elif item["kind"]=="onset":
            if span.get("extent_known") is not False or start!=end:
                skip("onset_not_a_point")
            else:
                labels.append({"seconds":float(start),"certainty":item.get("operator_certainty"),
                               "status":item.get("status")})
        elif span.get("extent_known") is not True or end<=start:
            skip("segment_not_a_span")
        else:
            segments.append([float(start),float(end)])
    segments.sort()
    merged=[]
    for start,end in segments:
        if merged and start<=merged[-1][1]:
            merged[-1][1]=max(merged[-1][1],end)
        else:
            merged.append([start,end])
    labels.sort(key=lambda row:row["seconds"])
    return labels,merged,dict(sorted(excluded.items()))


def onset_detector_sets(analysis):
    """Attack-candidate times per detector kind and time axis; click candidates excluded."""
    events=analysis.get("events") if isinstance(analysis,dict) and isinstance(analysis.get("events"),list) else []
    kinds=sorted({event.get("kind") for event in events if isinstance(event,dict) and isinstance(event.get("kind"),str)
                  and event["kind"].endswith("_attack_candidate")})
    result=[]
    for kind in kinds:
        rows=[event for event in events if isinstance(event,dict) and event.get("kind")==kind]
        for field,axis in ONSET_TIME_AXES:
            times=[_finite_number(event.get(field)) for event in rows]
            if any(value is None for value in times):
                if axis=="uncompensated":
                    result.append({"kind":kind,"time_axis":axis,"time_field":field,"event_count":len(rows),
                                   "status":"source_time_missing","times":None})
                continue
            result.append({"kind":kind,"time_axis":axis,"time_field":field,"event_count":len(rows),
                           "status":"available","times":sorted(float(value) for value in times)})
    return result


def _inside(seconds,segments):
    return any(start<=seconds<=end for start,end in segments)


def onset_agreement(labels,detections,tolerance,segments=None):
    """Score operator onset times against one detector's times at one tolerance.

    Without declared segments only recall is defined: unlabelled time is unknown, not
    onset-free. With segments, labels outside them are not scored, and an unmatched
    detection is a false positive only when it lies inside a declared segment.
    """
    if not math.isfinite(tolerance) or tolerance<=0:
        raise ValueError("Onset tolerance must be positive")
    if len(labels)>ONSET_MAX_LABELS:
        raise ValueError("Too many operator onset labels for bounded matching")
    if segments:
        labels=[value for value in labels if _inside(value,segments)]
    labels,detections=sorted(labels),sorted(detections)
    # Only detections within the tolerance of some label can match; the rest stay
    # unmatched and count as false positives only inside a declared segment.
    index=[j for j,value in enumerate(detections) if _near(value,labels,tolerance)]
    if len(index)>ONSET_MAX_CANDIDATES:
        raise ValueError("Too many detector candidates for bounded matching")
    candidates=[detections[j] for j in index]
    pairs=ordered_pairs(labels,candidates,tolerance)
    offsets=[candidates[j]-labels[i] for i,j in pairs]
    matched=len(pairs)
    used={index[j] for _,j in pairs}
    contested_detections=sum(1 for value in candidates if sum(abs(value-label)<=tolerance for label in labels)>=2)
    contested_labels=sum(1 for label in labels if sum(abs(value-label)<=tolerance for value in candidates)>=2)
    recall=None if not labels else matched/len(labels)
    if segments:
        in_scope=[j for j,value in enumerate(detections) if _inside(value,segments)]
        false_positives=sum(1 for j in in_scope if j not in used)
        precision=None if matched+false_positives==0 else matched/(matched+false_positives)
        precision_reason=None if precision is not None else "no_detections_in_declared_segments"
        detections_in_scope=len(in_scope)
    else:
        false_positives=precision=detections_in_scope=None
        precision_reason="no_operator_declared_fully_labelled_segment"
    f1=None if precision is None or recall is None else 0.0 if precision+recall==0 else 2*precision*recall/(precision+recall)
    absolute=sorted(abs(value) for value in offsets)
    return {"tolerance_seconds":tolerance,"operator_label_count":len(labels),"detections_in_scope":detections_in_scope,
            "matched_count":matched,"missed_label_count":len(labels)-matched,"false_positive_count":false_positives,
            "precision":precision,"precision_reason":precision_reason,"recall":recall,"f1":f1,
            "signed_offsets_seconds":offsets,"offset_convention":"detector_minus_operator",
            "median_signed_offset_seconds":statistics.median(offsets) if offsets else None,
            "mean_absolute_offset_seconds":sum(absolute)/len(absolute) if absolute else None,
            "contested_detection_count":contested_detections,"contested_label_count":contested_labels}


def _near(value,labels,tolerance):
    position=_bisect(labels,value)
    return any(abs(value-labels[k])<=tolerance for k in (position-1,position) if 0<=k<len(labels))


def _bisect(values,target):
    low,high=0,len(values)
    while low<high:
        middle=(low+high)//2
        if values[middle]<target:
            low=middle+1
        else:
            high=middle
    return low


def onset_label_benchmark(store,analysis,tolerances=ONSET_TOLERANCES_SECONDS,minimum=ONSET_MIN_OPERATOR_LABELS):
    """Join operator onset labels to every detector onset kind at each tolerance.

    Pure and deterministic: no audio, no detector run, no label moved. Abstains below
    `minimum` scored labels instead of reporting small-sample rates.
    """
    labels,segments,excluded=onset_operator_labels(store)
    by_status,by_certainty={},{}
    for row in labels:
        by_status[row["status"]]=by_status.get(row["status"],0)+1
        key=row["certainty"] if isinstance(row["certainty"],str) else "not_applicable"
        by_certainty[key]=by_certainty.get(key,0)+1
    scored=[row for row in labels if not segments or _inside(row["seconds"],segments)]
    subsets={"all_operator_labels":[row["seconds"] for row in labels],
             "confirmed_only":[row["seconds"] for row in labels if row["certainty"]=="confirmed"]}
    detectors=onset_detector_sets(analysis)
    document={"schema":ONSET_LABEL_SCHEMA,"tool":"onset_label_benchmark",
              "tolerances_seconds":list(tolerances),"minimum_operator_labels":minimum,
              "scoring_mode":"declared_segments_precision_and_recall" if segments else "recall_only_no_declared_segment",
              "declared_segments_seconds":segments,
              "declared_segment_total_seconds":round(sum(end-start for start,end in segments),6),
              "operator_labels":{"count":len(labels),"scored_count":len(scored),
                                 "outside_declared_segments":len(labels)-len(scored),
                                 "by_status":dict(sorted(by_status.items())),
                                 "by_certainty":dict(sorted(by_certainty.items())),"excluded":excluded},
              "label_rule":"kind onset (point) by an operator basis, status not dismissed_candidate; "
                           "kind onset_segment (span) declares every audible onset inside is labelled",
              "detector_rule":"analysis.json events whose kind ends in _attack_candidate, per kind and time axis; "
                              "periodic click candidates excluded",
              "matching":"one_to_one_ordered_maximum_count_then_minimum_total_absolute_offset",
              "claims":dict(ONSET_CLAIMS),"detectors":[]}
    if not labels:
        document["status"]="no_operator_onset_labels"
    elif len(scored)<minimum:
        document["status"]="insufficient_operator_onset_labels"
    elif not any(row["status"]=="available" for row in detectors):
        document["status"]="no_detector_onsets"
    else:
        document["status"]="measured_operator_label_agreement"
    for row in detectors:
        entry={key:row[key] for key in ("kind","time_axis","time_field","event_count","status")}
        entry["subsets"]={}
        for name,values in subsets.items():
            count=len([value for value in values if not segments or _inside(value,segments)])
            if row["status"]!="available":
                entry["subsets"][name]={"status":row["status"],"scored_label_count":count,"by_tolerance":None}
            elif count<minimum:
                entry["subsets"][name]={"status":"insufficient_operator_onset_labels" if count else "no_operator_onset_labels",
                                        "scored_label_count":count,"by_tolerance":None}
            else:
                entry["subsets"][name]={"status":"measured","scored_label_count":count,
                                        "by_tolerance":[onset_agreement(values,row["times"],tolerance,segments)
                                                        for tolerance in tolerances]}
        document["detectors"].append(entry)
    return document


def onset_benchmark_rows(document):
    """Flat rows for a CSV table; one per detector, axis, subset and tolerance (rates rounded to 4 places)."""
    rows=[]
    for detector in document.get("detectors",[]):
        for subset,value in detector["subsets"].items():
            for metrics in value.get("by_tolerance") or []:
                rows.append({"detector_kind":detector["kind"],"time_axis":detector["time_axis"],"label_subset":subset,
                             "tolerance_ms":round(metrics["tolerance_seconds"]*1000),
                             "operator_labels":metrics["operator_label_count"],"matched":metrics["matched_count"],
                             "missed_labels":metrics["missed_label_count"],
                             "false_positives":metrics["false_positive_count"],
                             **{key:None if metrics[key] is None else round(metrics[key],4) for key in ("precision","recall","f1")},
                             "median_signed_offset_ms":None if metrics["median_signed_offset_seconds"] is None
                             else round(metrics["median_signed_offset_seconds"]*1000,3)})
    return rows


def _load_script(name):
    spec=importlib.util.spec_from_file_location(f"video_utils_onset_{name}",ROOT/"scripts"/f"{name}.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def onset_labels_receipt(run_dir: Path, store_path: Path|None=None, analysis_path: Path|None=None):
    """Bind store and detector analysis to one run, then score. Paths stay out of the receipt."""
    run_dir=Path(run_dir)
    manifest_path=run_dir/"manifest.json"
    manifest=read_json(manifest_path)
    manifest_sha=digest(manifest_path)
    source_sha=(manifest.get("source") or {}).get("sha256") if isinstance(manifest.get("source"),dict) else None
    if not isinstance(source_sha,str) or not re.fullmatch(r"[0-9a-f]{64}",source_sha):
        raise ValueError("Run manifest has no source sha256")
    annotations=_load_script("annotation_v2")
    store_path=Path(store_path) if store_path is not None else run_dir/"review-annotations-v2.json"
    if store_path.is_file() and not store_path.is_symlink():
        store=read_json(store_path,annotations.MAX_STORE_BYTES)
        try:
            annotations.validate_store(store,source_sha256=source_sha,manifest_sha256=manifest_sha,
                                       source_min_seconds=-86400.,source_max_seconds=86400.)
        except annotations.AnnotationError as error:
            raise ValueError(f"Annotation store refused: {error.code}") from None
        store_binding={"status":"bound","sha256":digest(store_path),"revision":store["revision"]}
    elif store_path.exists():
        raise ValueError("Annotation store must be a regular file")
    else:
        store,store_binding={"annotations":[]},{"status":"annotation_store_absent","sha256":None,"revision":None}
    analysis_path=Path(analysis_path) if analysis_path is not None else run_dir/"analysis.json"
    analysis,analysis_binding={},{"status":"unavailable","sha256":None,"analyzed_input_sha256":None}
    if analysis_path.is_file() and not analysis_path.is_symlink():
        candidate=read_json(analysis_path,64_000_000)
        lineage=_load_script("report").analysis_lineage(run_dir,manifest,candidate)
        analysis_binding={"status":lineage,"sha256":digest(analysis_path),
                          "analyzed_input_sha256":(candidate.get("source") or {}).get("sha256") if isinstance(candidate.get("source"),dict) else None}
        if lineage in ("original_source_hash_bound","verified_run_derivative_hash_bound"):
            analysis=candidate
    document=onset_label_benchmark(store,analysis)
    if document["status"]=="no_detector_onsets" and not analysis:
        document["status"]="detector_analysis_unbound"
    return {**document,"created_at":datetime.now(timezone.utc).isoformat(),
            "inputs":{"run_id":manifest.get("run_id") if isinstance(manifest.get("run_id"),str) else None,
                      "manifest_sha256":manifest_sha,"source_sha256":source_sha,
                      "annotation_store":store_binding,"analysis":analysis_binding,
                      "source_clock":"original source timeline seconds for labels and detector events"},
            "worker_sha256":digest(Path(__file__))}


def write_new_json(path: Path, value):
    path=Path(path)
    if path.suffix!=".json" or path.exists() or path.is_symlink():
        raise ValueError("Onset benchmark output must be a new .json file")
    path.parent.mkdir(parents=True,exist_ok=True)
    data=json.dumps(value,indent=2,allow_nan=False)+"\n"
    with path.open("x") as stream:
        stream.write(data)
    return hashlib.sha256(data.encode()).hexdigest()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir",required=True,type=Path)
    parser.add_argument("--annotation-store",type=Path)
    parser.add_argument("--analysis",type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        receipt=onset_labels_receipt(args.run_dir,args.annotation_store,args.analysis)
        written=write_new_json(args.output,receipt)
    except (ValueError,OSError) as exc:
        print(json.dumps({"status":"error","message":str(exc)}),file=sys.stderr)
        return 2
    print(json.dumps({"status":receipt["status"],"output":str(args.output),"sha256":written,
                      "operator_onset_labels":receipt["operator_labels"]["count"],
                      "scored_labels":receipt["operator_labels"]["scored_count"],
                      "scoring_mode":receipt["scoring_mode"],"detector_sets":len(receipt["detectors"])}))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
