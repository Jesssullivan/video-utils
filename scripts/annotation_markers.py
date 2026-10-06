#!/usr/bin/env python3
"""Project a hash-pinned v2 review store into generic review markers; read-only.

The projection reuses the annotation_v2 owner validator and the markers.COLUMNS
interchange shape. It never reclassifies kind/basis/state, never writes into the
run directory, and never turns an annotation into a musical verdict.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import annotation_v2  # noqa: E402
import corpus  # noqa: E402
from dag import atomic_write  # noqa: E402
from markers import COLUMNS  # noqa: E402

SCHEMA_ID = "video-utils.annotation-markers.s2"
CSV_COLUMNS = COLUMNS + ["basis_label"]
MAX_MANIFEST_BYTES = annotation_v2.MAX_PROVENANCE_BYTES
VISIBLE_CALLOUT_LIMIT = 2
POINT_PRESENTATION_DWELL_SECONDS = 1.0  # marked_video presentation dwell; never a duration.
BASIS_PRIORITY = ("operator_assertion", "reference_comparison", "detector_hypothesis", "operator_context")
OPERATOR_BASES = frozenset({"operator_assertion", "operator_context"})
VISIBILITY_RULE = {
    "id": "annotation-markers-visibility-v1",
    "steps": [
        "dismissed_candidate rows are suppressed with reason dismissed_candidate_state",
        "remaining rows are ordered by basis priority operator_assertion > reference_comparison > "
        "detector_hypothesis > operator_context, then source start, then annotation_id",
        "a row is suppressed with reason exceeds_two_visible_callouts when, at any instant of its "
        "interval, two earlier-ordered visible rows are already active",
        "zero-length rows use a 1.0 s presentation dwell for overlap only; no duration is written",
    ],
    "visible_callout_limit": VISIBLE_CALLOUT_LIMIT,
    "point_presentation_dwell_seconds": POINT_PRESENTATION_DWELL_SECONDS,
}


class ProjectionError(ValueError):
    """Stable refusal code; nothing is written when it is raised."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _read(path, limit):
    try:
        return annotation_v2.read_bytes(path, limit)
    except annotation_v2.AnnotationError as exc:
        raise ProjectionError(exc.code) from exc
    except FileNotFoundError as exc:
        raise ProjectionError("annotation_projection_input_missing") from exc
    except OSError as exc:
        raise ProjectionError("unsafe_annotation_file") from exc


def _parse(data, code):
    try:
        value = annotation_v2.parse_json(data)
    except annotation_v2.AnnotationError as exc:
        raise ProjectionError(exc.code) from exc
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise ProjectionError(code) from exc
    if not isinstance(value, dict):
        raise ProjectionError(code)
    return value


def _interval(record):
    span = record["source_span"]
    start, end = float(span["start_seconds"]), float(span["end_seconds"])
    if end == start:
        end = start + POINT_PRESENTATION_DWELL_SECONDS
    return start, end


def _max_active(visible, start, end):
    """Maximum count of half-open visible intervals active at any t in [start, end)."""
    probes = {start} | {low for low, _ in visible if start < low < end}
    return max((sum(1 for low, high in visible if low <= t < high) for t in probes), default=0)


def _row(record, *, include_text):
    basis, span = record["basis"], record["source_span"]
    label = annotation_v2.LABELS[basis]
    evidence = {"annotation_id": record["id"], "basis": basis, "claim_label": record["claim_label"],
                "operator_certainty": record["operator_certainty"], "candidate_id": record["candidate_id"],
                "reference_sha256": record["reference_sha256"], "extent_known": span["extent_known"],
                "text_included": bool(include_text)}
    if include_text:
        evidence["note"] = record["note"]
        evidence["operator_quote"] = record["operator_quote"]
    start = float(span["start_seconds"])
    # A point stays a point: end equals start and no extent is invented.
    end = float(span["end_seconds"]) if span["extent_known"] else start
    return {"source_time_seconds": start, "end_seconds": end, "name": record["kind"],
            "confidence": ("not_applicable_human_annotation" if basis in OPERATOR_BASES
                           else "unknown_uncalibrated"),
            "status": record["status"], "evidence": evidence,
            "basis_label": label, "display_label": f"{label}: {record['kind']}", "label_basis": basis,
            "annotation_id": record["id"], "kind": record["kind"], "basis": basis,
            "review_state": record["status"], "extent_known": span["extent_known"],
            "musical_verdict": "not_established", "performance_issue_confirmed": False}


def visibility(records):
    """Return (visible_records, [(record, reason)]) by the frozen visibility rule."""
    suppressed, remaining = [], []
    for record in records:
        if record["status"] == "dismissed_candidate":
            suppressed.append((record, "dismissed_candidate_state"))
        else:
            remaining.append(record)
    remaining.sort(key=lambda item: (BASIS_PRIORITY.index(item["basis"]),
                                     float(item["source_span"]["start_seconds"]), item["id"]))
    visible, intervals = [], []
    for record in remaining:
        start, end = _interval(record)
        if _max_active(intervals, start, end) >= VISIBLE_CALLOUT_LIMIT:
            suppressed.append((record, "exceeds_two_visible_callouts"))
        else:
            visible.append(record)
            intervals.append((start, end))
    return visible, suppressed


def project(run_dir, *, expected_store_sha256, include_text=False):
    """Return (payload, csv_text) for RUN_DIR's v2 store pinned by its sha256."""
    if not annotation_v2.sha(expected_store_sha256):
        raise ProjectionError("invalid_expected_store_sha256")
    run_dir = Path(run_dir)
    if not run_dir.is_dir() or run_dir.is_symlink():
        raise ProjectionError("invalid_run_directory")
    manifest_path, store_path = run_dir / "manifest.json", run_dir / "review-annotations-v2.json"
    store_bytes = _read(store_path, annotation_v2.MAX_STORE_BYTES)
    store_sha = hashlib.sha256(store_bytes).hexdigest()
    if store_sha != expected_store_sha256:
        raise ProjectionError("stale_annotation_store")
    manifest_bytes = _read(manifest_path, MAX_MANIFEST_BYTES)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = _parse(manifest_bytes, "invalid_run_manifest")
    store = _parse(store_bytes, "invalid_annotation_store")
    try:
        source_sha = corpus.source_identity(manifest)
        source_min, source_max = corpus.source_bounds(manifest)
    except corpus.CorpusError as exc:
        raise ProjectionError(str(exc)) from exc
    public = "replay_receipts" not in store
    try:
        annotation_v2.validate_store(store, source_sha256=source_sha, manifest_sha256=manifest_sha,
                                     source_min_seconds=source_min, source_max_seconds=source_max,
                                     public=public)
    except annotation_v2.AnnotationError as exc:
        raise ProjectionError(exc.code) from exc
    visible, suppressed = visibility(store["annotations"])
    markers = sorted((_row(item, include_text=include_text) for item in visible),
                     key=lambda row: (row["source_time_seconds"], row["annotation_id"]))
    hidden = sorted(({**_row(item, include_text=include_text), "suppression_reason": reason}
                     for item, reason in suppressed),
                    key=lambda row: (row["source_time_seconds"], row["annotation_id"]))
    by_reason = {}
    for row in hidden:
        by_reason[row["suppression_reason"]] = by_reason.get(row["suppression_reason"], 0) + 1
    counts = {"record_count": len(store["annotations"]), "visible_count": len(markers),
              "suppressed_count": len(hidden), "suppressed_by_reason": dict(sorted(by_reason.items()))}
    if counts["visible_count"] + counts["suppressed_count"] != counts["record_count"]:
        raise ProjectionError("annotation_projection_count_identity_failed")
    payload = {
        "schema_id": SCHEMA_ID, "schema_version": 1, "format": "generic_review_markers_seconds",
        "source_sha256": source_sha, "manifest_sha256": manifest_sha, "store_sha256": store_sha,
        "store_revision": store["revision"], "store_form": "public_projection" if public else "full",
        "timeline": {"axis": "original_source_stream_timestamps_seconds",
                     "source_min_seconds": source_min, "source_max_seconds": source_max},
        "columns": CSV_COLUMNS, "text_included": bool(include_text),
        "visibility_rule": VISIBILITY_RULE, "markers": markers, "suppressed_markers": hidden,
        "counts": counts, "musical_verdict": "not_established",
        "listening_acceptance": "not_established", "picture_coverage": "not_evaluated",
        "editor_import": "not_validated",
        "limitations": [
            "Annotation markers keep the v2 kind, basis and review state verbatim; they are not detector output or a musical verdict.",
            "Operator-basis confidence is not applicable; detector/reference confidence is unknown and uncalibrated.",
            "Point annotations keep end equal to start; the 1.0 s dwell is presentation-only overlap accounting.",
            "Generic JSON/CSV is an interchange pilot; editor import and picture coverage are not validated.",
            "Note and operator quote text are omitted unless --include-text is supplied.",
        ],
    }
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for row in markers:
        writer.writerow({**{key: row[key] for key in CSV_COLUMNS},
                         "evidence": json.dumps(row["evidence"], ensure_ascii=False, allow_nan=False)})
    # Both inputs must still be the exact bytes that were validated.
    if (hashlib.sha256(_read(store_path, annotation_v2.MAX_STORE_BYTES)).hexdigest() != store_sha or
            hashlib.sha256(_read(manifest_path, MAX_MANIFEST_BYTES)).hexdigest() != manifest_sha):
        raise ProjectionError("annotation_file_changed_during_read")
    return payload, stream.getvalue()


def write_outputs(run_dir, output_dir, payload, csv_text):
    run_dir, output_dir = Path(run_dir).resolve(), Path(output_dir).expanduser().resolve()
    if output_dir == run_dir or output_dir.is_relative_to(run_dir):
        raise ProjectionError("output_inside_run_dir")
    json_path, csv_path = output_dir / "annotation-markers.json", output_dir / "annotation-markers.csv"
    atomic_write(json_path, json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    atomic_write(csv_path, csv_text)
    return json_path, csv_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--store-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--include-text", action="store_true")
    args = parser.parse_args(argv)
    try:
        run_dir, output_dir = args.run_dir.resolve(), args.output_dir.expanduser().resolve()
        if output_dir == run_dir or output_dir.is_relative_to(run_dir):
            raise ProjectionError("output_inside_run_dir")
        payload, csv_text = project(args.run_dir, expected_store_sha256=args.store_sha256,
                                    include_text=args.include_text)
        json_path, csv_path = write_outputs(args.run_dir, args.output_dir, payload, csv_text)
    except ProjectionError as exc:
        print(json.dumps({"status": "rejected", "error": exc.code}), file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError):
        print(json.dumps({"status": "rejected", "error": "invalid_or_unreadable_metadata"}), file=sys.stderr)
        return 1
    print(json.dumps({"status": "annotation_markers_projected", "markers_json": str(json_path),
                      "markers_csv": str(csv_path), **payload["counts"],
                      "editor_import": "not_validated"}, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
