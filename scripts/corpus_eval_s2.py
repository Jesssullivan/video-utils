#!/usr/bin/env python3
"""Coverage-first evaluation of untouched detector proposals on a sparse corpus.

Coverage is computed before any metric. Unlabelled time is unknown, never a
negative, so precision stays null; recall is reported only with sufficient
reviewer-attended coverage and at least one literal operator assertion. No audio
is read and proposals are never filtered, re-thresholded or re-ranked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import annotation_v2  # noqa: E402
import corpus  # noqa: E402
import corpus_split_s1  # noqa: E402
from dag import atomic_write  # noqa: E402
import flags_triage  # noqa: E402

SCHEMA_ID = "video-utils.corpus-eval.s2"
COVERAGE_THRESHOLD = 0.5
MATCH_TOLERANCE_SECONDS = 0.25  # dag AUTOMATIC_REVIEW_SETTINGS motif_match_window_maximum_seconds
MAX_PROPOSAL_BYTES = 20_000_000
ORIGINAL_AXIS = "original_source_stream_timestamps_seconds"
COVERAGE_BASES = ("operator_assertion", "operator_context", "reference_comparison")
ERROR_AXES = {"timing": ("rhythm_timing", "rhythm_pattern"), "omission": ("phrase_omission",),
              "duration": ("phrase_duration",), "pitch": ("melodic_pitch",)}
ARTICULATION_AXES = ("palm_mute", "legato", "tapping", "sweep", "rest", "chord")
ARTICULATION_KINDS = {"rest": ("rest_execution",)}
UNSPECIFIED_ARTICULATION_KINDS = ("articulation",)
NOT_SCORED_KINDS = {"meter_mismatch": "meter_context_not_a_performance_axis",
                    "tone": "tone_capture_context_not_a_performance_axis",
                    "noise": "capture_noise_context_not_a_performance_axis",
                    "other": "unclassified_kind_not_scored"}
PRECISION_REASON = "false_positive_requires_reviewed_absence_label"
ALIGNED = "same_source_original_clock_declared"
assert set(annotation_v2.KINDS) == ({kind for kinds in ERROR_AXES.values() for kind in kinds}
                                    | {kind for kinds in ARTICULATION_KINDS.values() for kind in kinds}
                                    | set(UNSPECIFIED_ARTICULATION_KINDS) | set(NOT_SCORED_KINDS))


class EvaluationError(corpus.CorpusError):
    pass


def require(condition, code):
    if not condition:
        raise EvaluationError(code)


def finite(value):
    return type(value) in (int, float) and math.isfinite(float(value))


def labelled_positive(item):
    """V5 'labelled' rule: literal operator assertion that was accepted as an observation."""
    return (item.get("basis") == "operator_assertion" and item.get("status") == "accepted_observation"
            and isinstance(item.get("operator_quote"), str) and bool(item["operator_quote"].strip()))


def union_seconds(intervals, low, high):
    clipped = sorted((max(low, a), min(high, b)) for a, b in intervals if min(high, b) > max(low, a))
    merged = []
    for a, b in clipped:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return sum(b - a for a, b in merged), merged


def overlaps(proposal, low, high):
    start, end = proposal["start"], proposal["end"]
    return low <= start <= high if start == end else (start < high and low < end)


def _widen(start, end):
    return (start - MATCH_TOLERANCE_SECONDS, end + MATCH_TOLERANCE_SECONDS) if start == end else (start, end)


def matches(positives, proposals):
    """One-to-one, earliest-first: each positive takes the earliest unused intersecting proposal."""
    used, pairs = set(), []
    for item in sorted(positives, key=lambda row: (float(row["source_span"]["start_seconds"]), row["id"])):
        span = item["source_span"]
        low, high = _widen(float(span["start_seconds"]), float(span["end_seconds"]))
        for proposal in proposals:
            if proposal["flag_index"] in used:
                continue
            a, b = _widen(proposal["start"], proposal["end"])
            if a <= high and low <= b:
                used.add(proposal["flag_index"])
                pairs.append({"annotation_id": item["id"], "annotation_kind": item["kind"],
                              "flag_index": proposal["flag_index"], "flag_id": proposal["flag_id"],
                              "flag_kind": proposal["kind"]})
                break
    return pairs


def axis_result(kinds, selected, proposals, gate_reason, *, detector):
    positives = [item for item in selected if item["kind"] in kinds and labelled_positive(item)]
    result = {"kinds": list(kinds), "labelled_positive_count": len(positives), "eligible": False,
              "precision": None, "precision_reason": PRECISION_REASON, "recall": None,
              "recall_numerator": None, "recall_denominator": None, "status": "unknown", "reason": None,
              "detector_for_axis": detector}
    if gate_reason is not None:
        result["reason"] = gate_reason
    elif not positives:
        result["reason"] = "no_labelled_positives"
    else:
        found = matches(positives, proposals)
        result.update(eligible=True, status="recall_measured_precision_unknown",
                      recall=len(found) / len(positives), recall_numerator=len(found),
                      recall_denominator=len(positives), matches=found)
    return result


def read_proposals(path, expected_sha256):
    require(isinstance(expected_sha256, str) and corpus.SHA.fullmatch(expected_sha256), "invalid_proposals_sha256")
    try:
        data = annotation_v2.read_bytes(Path(path), MAX_PROPOSAL_BYTES)
    except annotation_v2.AnnotationError as exc:
        raise EvaluationError("proposals_" + exc.code) from exc
    except OSError as exc:
        raise EvaluationError("proposals_unreadable_or_unsafe") from exc
    digest = hashlib.sha256(data).hexdigest()
    require(digest == expected_sha256, "stale_proposals")
    try:
        value = annotation_v2.parse_json(data)
    except (annotation_v2.AnnotationError, ValueError, RecursionError, UnicodeError) as exc:
        raise EvaluationError("invalid_proposals_json") from exc
    require(isinstance(value, dict) and isinstance(value.get("flags"), list)
            and len(value["flags"]) <= flags_triage.MAX_FLAGS, "invalid_proposals_collection")
    return value, digest


def proposal_manifest_sha256(path):
    """Hash the proposal run's sibling manifest when present; None means unknown."""
    sibling = Path(path).parent / "manifest.json"
    if not sibling.is_file() or sibling.is_symlink():
        return None
    try:
        return annotation_v2.hash_provenance(sibling, max_bytes=MAX_PROPOSAL_BYTES)
    except (OSError, annotation_v2.AnnotationError):
        return None


def evaluate(split_manifest, *, local_root, proposals_path, proposals_sha256):
    validated = corpus_split_s1.validate_split(split_manifest, local_root, summary=False)
    payload, proposals_digest = read_proposals(proposals_path, proposals_sha256)
    timeline = payload.get("timeline") if isinstance(payload.get("timeline"), dict) else {}
    proposal_source = payload.get("source_sha256")
    eligible, navigation = [], 0
    for index, flag in enumerate(payload["flags"]):
        require(isinstance(flag, dict) and finite(flag.get("source_time_seconds")), "invalid_proposal_interval")
        start = float(flag["source_time_seconds"])
        end = flag.get("end_seconds", start)
        require(finite(end) and float(end) >= start, "invalid_proposal_interval")
        if flags_triage.is_navigation_proxy(flag):
            navigation += 1
            continue
        eligible.append({"flag_index": index, "flag_id": flags_triage.flag_id(index, flag),
                         "kind": str(flag.get("kind", "review_candidate"))[:256], "start": start,
                         "end": float(end)})
    eligible.sort(key=lambda row: (row["start"], row["flag_index"]))
    proposal_manifest = proposal_manifest_sha256(proposals_path)
    metadata = corpus.Metadata(local_root)
    records, skipped = [], []
    for row in validated["records"]:
        refs = row["validated_annotation_refs"]
        selected, seen, v1_count = [], set(), 0
        for ref in refs:
            for item in ref["selected_annotations"]:
                if ref["schema_version"] != 2:
                    v1_count += 1
                elif item["id"] not in seen:
                    seen.add(item["id"])
                    selected.append(item)
        if not selected:
            skipped.append({"record_id": row["id"], "reason": ("v1_annotations_not_evaluated_in_s2" if v1_count
                                                               else "no_selected_v2_annotations")})
            continue
        manifest_hashes = sorted({ref["manifest_sha256"] for ref in refs if ref["schema_version"] == 2})
        manifest, _ = metadata.read(row["manifest"]["path"], row["manifest"]["sha256"])
        clock = ALIGNED
        try:
            low, high = corpus.source_bounds(manifest)
        except corpus.CorpusError:
            low = high = None
            clock = "clock_unknown"
        if proposal_source != row["source_sha256"]:
            clock = "source_mismatch"
        elif timeline.get("axis") != ORIGINAL_AXIS:
            clock = "clock_unknown"
        attended = [(float(item["source_span"]["start_seconds"]), float(item["source_span"]["end_seconds"]))
                    for item in selected
                    if item["basis"] in COVERAGE_BASES and item["source_span"]["extent_known"]]
        if low is None:
            covered, merged, total, fraction = None, [], None, None
        else:
            covered, merged = union_seconds(attended, low, high)
            total = high - low
            fraction = covered / total if total > 0 else None
        meets = fraction is not None and fraction >= COVERAGE_THRESHOLD
        gate = (clock if clock != ALIGNED else
                "coverage_below_threshold" if not meets else None)
        overall = axis_result(tuple(sorted(annotation_v2.KINDS)), selected, eligible, gate,
                              detector="kind_agnostic_interval_overlap")
        overall.pop("kinds")
        in_covered = sum(1 for proposal in eligible if any(overlaps(proposal, a, b) for a, b in merged))
        records.append({
            "record_id": row["id"], "take_family_id": row["take_family_id"], "split": row["split"],
            "origin": row["origin"], "source_sha256": row["source_sha256"],
            "annotation_manifest_sha256": manifest_hashes,
            "annotation_store_sha256": sorted({ref["store_sha256"] for ref in refs}),
            "selected_annotation_count": len(selected),
            "selected_annotations": [{"annotation_id": item["id"], "kind": item["kind"], "basis": item["basis"],
                                      "review_state": item["status"],
                                      "extent_known": item["source_span"]["extent_known"],
                                      "start_seconds": float(item["source_span"]["start_seconds"]),
                                      "end_seconds": float(item["source_span"]["end_seconds"]),
                                      "labelled_positive": labelled_positive(item),
                                      "musical_verdict": item.get("musical_verdict", "not_established")}
                                     for item in sorted(selected, key=lambda x: (x["source_span"]["start_seconds"], x["id"]))],
            "v1_annotations_not_evaluated": v1_count,
            "clock_alignment_status": clock, "detector_latency": "uncalibrated",
            "proposal_manifest_sha256": proposal_manifest,
            "proposal_lineage_differs_from_annotation_manifest": (
                None if proposal_manifest is None else proposal_manifest not in manifest_hashes),
            "coverage": {"covered_seconds": covered, "total_seconds": total, "coverage_fraction": fraction,
                         "coverage_threshold": COVERAGE_THRESHOLD, "meets_threshold": meets,
                         "covered_intervals": [[a, b] for a, b in merged],
                         "coverage_bases": list(COVERAGE_BASES), "point_annotations_add_seconds": 0,
                         "total_seconds_basis": "corpus.source_bounds_extent",
                         "meaning": "reviewer_attended_region_not_reviewed_absence"},
            "proposals": {"eligible_count": len(eligible), "navigation_excluded": navigation,
                          "eligible_overlapping_covered_region": in_covered},
            "metrics": {**overall, "negatives": None, "true_negatives": None, "false_positives": None},
            "error_axes": {name: {**axis_result(kinds, selected, eligible, gate,
                                                detector="none_kind_agnostic_interval_overlap"),
                                  **({"reference_required": True, "note_correctness": "not_established"}
                                     if name == "pitch" else {})}
                           for name, kinds in ERROR_AXES.items()},
            "articulation_axes": {name: (axis_result(ARTICULATION_KINDS[name], selected, eligible, gate,
                                                     detector="none")
                                         if name in ARTICULATION_KINDS else
                                         {"kinds": [], "labelled_positive_count": 0, "eligible": False,
                                          "precision": None, "precision_reason": PRECISION_REASON,
                                          "recall": None, "recall_numerator": None, "recall_denominator": None,
                                          "status": "unknown", "reason": "no_subtype_in_v2_schema",
                                          "detector_for_axis": "none"})
                                  for name in ARTICULATION_AXES},
            "articulation_unspecified": {**axis_result(UNSPECIFIED_ARTICULATION_KINDS, selected, eligible, gate,
                                                       detector="none"),
                                         "spread_to_articulation_axes": False},
            "not_scored_kinds": {kind: {"selected_count": sum(item["kind"] == kind for item in selected),
                                        "reason": reason} for kind, reason in NOT_SCORED_KINDS.items()},
        })
    # The proposals must still be the exact bytes that were hashed.
    again = annotation_v2.read_bytes(Path(proposals_path), MAX_PROPOSAL_BYTES)
    require(hashlib.sha256(again).hexdigest() == proposals_digest, "proposals_changed_during_evaluation")
    return {
        "schema_id": SCHEMA_ID, "schema_version": 1, "status": "coverage_first_evaluation_recorded",
        "split_manifest_sha256": validated["manifest_sha256"], "corpus_id": validated["corpus_id"],
        "corpus_revision": validated["revision"], "approval_state": validated["approval_state"],
        "group_receipts": validated["groups"], "contexts": validated["contexts"],
        "proposals_sha256": proposals_digest, "proposals_source_sha256": proposal_source,
        "proposals_timeline_axis": timeline.get("axis"), "proposal_count": len(payload["flags"]),
        "navigation_excluded": navigation, "eligible_proposal_count": len(eligible),
        "proposals_modified": False, "proposal_selection": "untouched_except_navigation_proxy_rule",
        "coverage_threshold": COVERAGE_THRESHOLD, "match_tolerance_seconds": MATCH_TOLERANCE_SECONDS,
        "match_rule": "closed interval intersection; zero-length side widened by match_tolerance_seconds; one-to-one earliest-first",
        "labelled_positive_rule": "operator_assertion + accepted_observation + literal operator_quote",
        "records": records, "skipped_records": skipped,
        "summary": {"records_evaluated": len(records), "records_skipped": len(skipped),
                    "labelled_positive_total": sum(r["metrics"]["labelled_positive_count"] for r in records),
                    "records_meeting_coverage_threshold": sum(r["coverage"]["meets_threshold"] for r in records),
                    "records_with_recall": sum(r["metrics"]["recall"] is not None for r in records)},
        "negatives_inferred": 0, "unlabelled_intervals": "unknown_not_negative",
        "ground_truth_established": False, "listening_acceptance": "not_established",
        "source_audio_read": False, "performance_grade": "not_assigned",
        "limitations": [
            "Precision needs reviewed-absence labels; the v2 schema has none, so precision is always null.",
            "Recall counts kind-agnostic interval overlap of untouched proposals; no flag kind identifies an error type or technique.",
            "Coverage is reviewer-attended time from selected spans, not evidence that unlabelled time is free of issues.",
            "Detector latency and physical sync are uncalibrated; matching tolerance is the existing 0.25 s motif window.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    run = commands.add_parser("evaluate")
    run.add_argument("split_manifest", type=Path)
    run.add_argument("--root", type=Path, default=corpus_split_s1.ROOT)
    run.add_argument("--proposals", type=Path, required=True)
    run.add_argument("--proposals-sha256", required=True)
    run.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = args.output.expanduser().resolve()
        proposals = args.proposals.expanduser().resolve()
        require(output != proposals and not output.is_relative_to(proposals.parent),
                "output_inside_proposal_run_dir")
        result = evaluate(args.split_manifest, local_root=args.root, proposals_path=proposals,
                          proposals_sha256=args.proposals_sha256)
        atomic_write(output, json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    except (corpus.CorpusError, OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        error = str(exc) if isinstance(exc, corpus.CorpusError) else "invalid_or_unreadable_metadata"
        print(json.dumps({"status": "rejected", "error": error}), file=sys.stderr)
        return 1
    print(json.dumps({"status": result["status"], "output": str(output), **result["summary"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
