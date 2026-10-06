#!/usr/bin/env python3
"""Build and verify a metadata-only, hash-bound report bundle for one run.

Standard library only. The bundle holds the run manifest, the bound analysis
and graph payloads, the fixed S2 receipt registry and small derived CSV tables
for the optional Quarto report. It never copies, decodes or links media. The
plain `scripts/report.py` HTML report stays the primary report; binding rules
are reused from it, never reimplemented (docs/spec/sprints/REPORT_S2.md).
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys

REPO = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("report", REPO / "scripts" / "report.py")
report = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(report)

SCHEMA = "video-utils.report-bundle/1"
HASH_SCOPE = ("run", "members", "receipts", "unknowns")
RECEIPTS_DIR = REPO / "docs" / "agent-notes" / "sprints" / "20261006-s2"
RECEIPT_REGISTRY = (
    ("tone_ab", "tone_ab-20261006T120702Z-actual-run.json"),
    ("rhythm_clicks", "rhythm_clicks-real-take.json"),
    ("phrase_anchor_riff_spans", "phrase_anchor_riff-real-take-spans.json"),
    ("phrase_anchor_riff_bench", "phrase_anchor_riff-heldout-score.json"),
    ("annot_corpus", "annot_corpus-implementation.json"),
)
DEFAULT_STORE_REL = "artifacts/experiments/s1-demo-context-20261006T0627/review-annotations-v2.json"
BINDING_CLASSES = ("run_bound", "source_bound_same_analyzed_input", "source_bound_different_analyzed_input",
                   "metadata_bound", "synthetic_bank_not_take", "unbound_context_only")
MEDIA_EXTENSIONS = frozenset({"wav", "flac", "aiff", "aif", "mp3", "aac", "m4a", "mov", "mp4", "m4v",
                              "mkv", "webm", "caf"})
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_RECEIPT_BYTES = 8 * 1024 * 1024
MAX_INPUT_JSON_BYTES = 64 * 1024 * 1024
MAX_FLAG_ROWS = 200
SHA = re.compile(r"[0-9a-f]{64}\Z")
PHRASE_LABEL_KINDS = frozenset({"phrase_omission", "phrase_duration"})
NOTE_LABEL_KINDS = frozenset({"melodic_pitch"})
BOUND_LINEAGE = ("original_source_hash_bound", "verified_run_derivative_hash_bound")
PROTECTED_HOME_DIRS = tuple(dict.fromkeys(
    [Path("/Users/jess/Documents"), Path("/Users/jess/Desktop"), Path.home() / "Documents", Path.home() / "Desktop"]))

UNKNOWNS = (
    ("listening_accepted", False, "No operator listening review is bound to this bundle."),
    ("listening_acceptance", "not_established", "Listening acceptance is a separate operator state."),
    ("operator_preference", None, "No blind or sighted operator preference has been recorded."),
    ("perceived_fullness", None, "Low-end fullness feedback is open; band energy deltas are not perception."),
    ("nasal_quality", None, "Thin/nasal balance feedback is open; no listening verdict exists."),
    ("expected_rhythm_reference_approved", None, "No approved expected-rhythm reference exists for this take."),
    ("note_correctness", None, "Note correctness requires tuning plus an approved reference; none is bound."),
    ("missed_or_extra_notes", None, "Missed or extra notes require an approved expected-rhythm reference."),
    ("performance_grade", "not_performed", "No performance grading is performed by this bundle or report."),
    ("click_identity", "unverified", "High-frequency click candidates are not verified metronome clicks."),
    ("physical_capture_latency", "uncalibrated", "Microphone and room propagation latency are uncalibrated."),
    ("meter", None, "Meter and downbeat are not identified; any value shown is a candidate only."),
    ("tonic", None, "Tonic is not established; tonal output is hypothesis context only."),
    ("mode", None, "Mode is not established; tonal output is hypothesis context only."),
    ("fundamental_32hz_presence", None, "Presence of the ~32.7 Hz C1 fundamental is not established by metadata."),
    ("room_response_recovered", False, "EQ or band energy cannot recover the uncaptured in-room amp response."),
    ("stems", "not_produced", "No stem separation was produced; a mono-mixture residual is not a stem."),
    ("editor_import_proven", False, "Final Cut/Resolve import requires actual application proof."),
    ("default_adopted", False, "This lane adopts no detector, profile or master default."),
    ("master_changed", False, "The bundle is metadata-only and never writes the master."),
    ("quarto_render_status", "not_attempted",
     "The bundle is never rewritten; the render receipt carries the render outcome."),
)

FIGURES = {
    "tone_ab": (
        ("loudness match delta (LU)", "loudness_match/match_lu_delta"),
        ("loudness match status", "loudness_match/match_status"),
        ("denoise stage 20-45 Hz, matched (dB)", "stage_deltas_db/denoise_stage/20-45/matched_db"),
        ("end-to-end 20-45 Hz, matched (dB)", "stage_deltas_db/end_to_end/20-45/matched_db"),
        ("trial low-shelf minus master 20-45 Hz, matched (dB)", "experiment/delta_20_45_db/matched"),
        ("trial status", "experiment/status"),
        ("listening preference", "metrics/5_excerpt_pairs/preference"),
    ),
    "rhythm_clicks": (
        ("fitted click-grid BPM", "R2_regression/click_grid_scalars/bpm/accepted"),
        ("drift (ppm)", "R1_drift/drift_ppm"),
        ("drift standard error (ppm)", "R1_drift/drift_ppm_standard_error"),
        ("drift confidence label", "R1_drift/confidence_label"),
        ("phrases measured / total", ("P4_phrase_timing/reference_conditioned_alignment_candidate/summary/measured_count",
                                      "P4_phrase_timing/reference_conditioned_alignment_candidate/summary/phrase_count")),
        ("click identity", "unknowns/click_identity"),
        ("physical capture latency", "detector_delay/physical_capture_latency"),
    ),
    "phrase_anchor_riff_spans": (
        ("intended click total (intent, not observed)", "arrangement_totals/intended_click_count"),
        ("operator-click-equivalent BPM (lattice)", "lattice/operator_click_equivalent_bpm"),
        ("operator-boundary scorer", "scorer_check/reason"),
        ("real-take phrase correctness", "real_take_phrase_correctness"),
        ("breakdown 1 execution", "breakdown1_execution"),
        ("meter", "meter"),
    ),
    "phrase_anchor_riff_bench": (
        ("R1_lag pair IoU>=0.5 TP / references", ("aggregate/arms/R1_lag/pair_iou/0/tp",
                                                  "aggregate/arms/R1_lag/pair_iou/0/reference_count")),
        ("R1_lag pair IoU>=0.5 FP", "aggregate/arms/R1_lag/pair_iou/0/fp"),
        ("Araw pair IoU>=0.5 TP / references", ("aggregate/arms/Araw/pair_iou/0/tp",
                                                "aggregate/arms/Araw/pair_iou/0/reference_count")),
        ("S1_support pair IoU>=0.5 TP / references", ("aggregate/arms/S1_support/pair_iou/0/tp",
                                                      "aggregate/arms/S1_support/pair_iou/0/reference_count")),
        ("accuracy scope", "continuous_riff_accuracy_scope"),
        ("real-take accuracy", "real_take_accuracy"),
    ),
    "annot_corpus": (
        ("operator-labelled seconds / take seconds",
         ("measurements/metric_6_real_corpus_evaluation/covered_seconds",
          "measurements/metric_6_real_corpus_evaluation/total_seconds")),
        ("precision", "measurements/metric_6_real_corpus_evaluation/precision"),
        ("precision reason", "measurements/metric_6_real_corpus_evaluation/precision_reason"),
        ("recall reason", "measurements/metric_6_real_corpus_evaluation/recall_reason"),
        ("triage flags shown / total", "measurements/metric_4_real_take_triage/fractions/shown_of_total"),
    ),
}

RUN_MANIFEST_PTRS = ("run/manifest_sha256",)
RUN_ID_PTRS = ("run/run_id",)
SOURCE_PTRS = ("run/source_sha256", "inputs/original_source_sha256", "source/original_source_sha256",
               "source_lineage/original_source_sha256", "original_source_sha256")
ANALYZED_PTRS = ("source/analyzed_input_sha256", "inputs/grid_analyzed_input_sha256",
                 "inputs/analyzed_input_sha256", "analyzed_input_sha256")
ANALYZED_PATH_PTRS = ("source/analyzed_input",)


class Refusal(Exception):
    """A stable machine code; never carries paths or private text."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pointer(value, path):
    for part in path.split("/"):
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def first_pointer(value, paths):
    for path in paths:
        found = pointer(value, path)
        if found is not None:
            return path, found
    return None, None


def shown(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            return "non_finite"
        return str(value) if isinstance(value, int) else f"{number:.6g}"
    if isinstance(value, str):
        return value[:120]
    return "structured"


def is_media_name(name):
    return Path(name).suffix.lower().lstrip(".") in MEDIA_EXTENSIONS


def has_media_magic(data):
    head = bytes(data[:12])
    return ((head[:4] == b"RIFF" and head[8:12] in (b"WAVE", b"AVI ")) or head[4:8] == b"ftyp"
            or head[:3] == b"ID3" or head[:4] in (b"fLaC", b"OggS", b"FORM", b"caff")
            or head[:4] == b"\x1a\x45\xdf\xa3")


def safe_directory(value, code):
    """Existing local directory, no `..` and no symlink component."""
    if value is None:
        raise Refusal(code)
    text = str(value)
    if not text or "\x00" in text or ".." in Path(text).parts:
        raise Refusal(code)
    path = Path(os.path.abspath(text))
    probe = Path(path.anchor)
    for part in path.parts[1:]:
        probe = probe / part
        if probe.is_symlink():
            raise Refusal(code)
    if not path.is_dir():
        raise Refusal(code)
    return path


def inside(path, root):
    try:
        return Path(path).is_relative_to(root)
    except (TypeError, ValueError):
        return False


class Tracker:
    """Record sha256/size/mtime_ns for every opened input; recheck before publishing."""

    def __init__(self):
        self.seen = {}

    @staticmethod
    def _stat(path):
        info = path.stat()
        return info.st_size, info.st_mtime_ns

    def _record(self, path, sha, before):
        key = str(Path(os.path.abspath(path)))
        if self._stat(path) != before:
            raise Refusal("input_changed_during_build")
        prior = self.seen.get(key)
        if prior and (prior["sha256"], prior["size"], prior["mtime_ns"]) != (sha, *before):
            raise Refusal("input_changed_during_build")
        self.seen[key] = {"sha256": sha, "size": before[0], "mtime_ns": before[1]}

    def sha256(self, path):
        path = Path(path)
        key = str(Path(os.path.abspath(path)))
        before = self._stat(path)
        prior = self.seen.get(key)
        if prior and (prior["size"], prior["mtime_ns"]) == before:
            return prior["sha256"]
        sha = report.sha256(path)
        self._record(path, sha, before)
        return sha

    def read_bytes(self, path, limit):
        path = Path(path)
        before = self._stat(path)
        if before[0] > limit:
            raise Refusal("input_too_large")
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise Refusal("input_too_large")
        self._record(path, digest(data), before)
        return data

    def load_json(self, path):
        """Drop-in for report.load_json that records the bytes it parsed."""
        path = Path(path)
        if not path.is_file():
            return {}
        value = json.loads(self.read_bytes(path, MAX_INPUT_JSON_BYTES))
        if not isinstance(value, dict):
            raise ValueError(f"{path.name} must contain a JSON object")
        return value

    def recheck(self):
        changed = []
        for key, expected in sorted(self.seen.items()):
            path = Path(key)
            try:
                size, mtime = self._stat(path)
                same = (size, mtime) == (expected["size"], expected["mtime_ns"]) and \
                    report.sha256(path) == expected["sha256"]
            except OSError:
                same = False
            if not same:
                changed.append(key)
        return changed


def load_json_bytes(tracker, path, limit, invalid):
    data = tracker.read_bytes(path, limit)
    try:
        value = json.loads(data)
    except (ValueError, UnicodeError):
        raise Refusal(invalid) from None
    if not isinstance(value, dict):
        raise Refusal(invalid)
    return data, value


def data_root_for(run_dir, repo_root):
    if run_dir.parent.name == "runs" and run_dir.parent.parent.name == "artifacts":
        return run_dir.parents[2]
    return repo_root


def check_output_dir(output, run_dir, analysis_run_dir):
    if output.exists() or output.is_symlink():
        raise Refusal("output_dir_exists")
    for sibling in (Path(f"{output}.failed"),):
        if sibling.exists():
            raise Refusal("output_dir_exists")
    resolved = Path(os.path.realpath(output))
    parts = resolved.parts
    protected = [run_dir.resolve()] + ([analysis_run_dir.resolve()] if analysis_run_dir else [])
    protected += [Path(os.path.realpath(home)) for home in PROTECTED_HOME_DIRS]
    if any(inside(resolved, root) for root in protected):
        raise Refusal("output_dir_protected")
    if any(parts[index:index + 2] == ("artifacts", "runs") for index in range(len(parts) - 1)):
        raise Refusal("output_dir_protected")
    if any(parts[index:index + 2] == (".local", "sprint1") for index in range(len(parts) - 1)):
        raise Refusal("output_dir_protected")
    return resolved


def classify_receipt(receipt, context, tracker):
    """Binding class from hashes and IDs inside the receipt only (never names or mtimes)."""
    evidence = {}
    manifest_ptr, manifest_value = first_pointer(receipt, RUN_MANIFEST_PTRS)
    id_ptr, id_value = first_pointer(receipt, RUN_ID_PTRS)
    if manifest_value == context["manifest_sha256"] and (id_value is None or id_value == context["run_id"]):
        evidence = {"pointer": manifest_ptr, "run_id_pointer": id_ptr}
        return "run_bound", "run_manifest_sha256_equal", evidence, None
    source_ptr, source_value = first_pointer(receipt, SOURCE_PTRS)
    analyzed_ptr, analyzed_value = first_pointer(receipt, ANALYZED_PTRS)
    same = analyzed_value is not None and analyzed_value == context["analyzed_sha256"]
    evidence = {"source_pointer": source_ptr, "analyzed_pointer": analyzed_ptr,
                "analyzed_input_sha256": analyzed_value if isinstance(analyzed_value, str) else None,
                "run_analyzed_input_sha256": context["analyzed_sha256"]}
    if source_value is not None:
        if source_value != context["source_sha256"]:
            return "unbound_context_only", "source_identity_differs", evidence, None
        cls = "source_bound_same_analyzed_input" if same else "source_bound_different_analyzed_input"
        return cls, "original_source_sha256_equal", evidence, None
    chain = chain_manifest(receipt, context, tracker, analyzed_value)
    if chain:
        cls = "source_bound_same_analyzed_input" if same else "source_bound_different_analyzed_input"
        evidence["chain_run_id"] = chain["run_id"]
        evidence["chain_manifest_sha256"] = chain["sha256"]
        return cls, "analyzed_input_run_manifest_chain", evidence, chain
    found = find_manifest_hash(receipt, context["manifest_sha256"])
    if found:
        return "metadata_bound", "run_manifest_sha256_referenced", {"pointer": found}, None
    status = receipt.get("status")
    if isinstance(receipt.get("bank_sha256"), str) and (
            receipt.get("continuous_riff_accuracy_scope") == "generated_only"
            or (isinstance(status, str) and status.startswith("generated"))):
        return "synthetic_bank_not_take", "generated_bank_identity", {"bank_sha256": receipt["bank_sha256"]}, None
    return "unbound_context_only", "no_matching_identity", {}, None


def chain_manifest(receipt, context, tracker, analyzed_value):
    """Follow a receipt's analyzed-input hash to the run manifest that produced it."""
    _, location = first_pointer(receipt, ANALYZED_PATH_PTRS)
    if not isinstance(analyzed_value, str) or not SHA.match(analyzed_value) or not isinstance(location, str):
        return None
    candidate = Path(location)
    if not candidate.is_absolute() or ".." in candidate.parts:
        return None
    run = candidate.parent
    if run.parent.name != "runs" or run.parent.parent.name != "artifacts":
        return None
    if not inside(Path(os.path.abspath(run)), Path(os.path.abspath(context["data_root"] / "artifacts" / "runs"))):
        return None
    try:
        run = safe_directory(run, "chain_unavailable")
    except Refusal:
        return None
    manifest_path = run / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        return None
    data = tracker.read_bytes(manifest_path, MAX_RECEIPT_BYTES)
    try:
        manifest = json.loads(data)
    except (ValueError, UnicodeError):
        return None
    hashes = manifest.get("output_sha256") if isinstance(manifest, dict) else None
    if not isinstance(hashes, dict) or hashes.get(candidate.name) != analyzed_value:
        return None
    if report.source_identity(manifest) != context["source_sha256"]:
        return None
    return {"path": manifest_path, "bytes": data, "sha256": digest(data),
            "run_id": manifest.get("run_id") if isinstance(manifest.get("run_id"), str) else run.name}


def find_manifest_hash(value, expected, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            here = f"{path}/{key}" if path else str(key)
            if key in ("manifest", "manifest_sha256") and item == expected:
                return here
            found = find_manifest_hash(item, expected, here)
            if found:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = find_manifest_hash(item, expected, f"{path}/{index}")
            if found:
                return found
    return None


def claim_class(receipt, binding):
    if isinstance(receipt.get("claim_class"), str):
        return receipt["claim_class"][:120]
    claims = receipt.get("claims")
    if isinstance(claims, dict):
        counts = [f"{label} x{len(claims.get(key) or [])}" for label, key in
                  (("M", "measurements"), ("I", "inferences"), ("L", "listening"))]
        return "; ".join(counts)
    if binding == "synthetic_bank_not_take":
        status = receipt.get("status")
        return f"S ({status})" if isinstance(status, str) else "S"
    legend = pointer(receipt, "measurements/claim_class_legend")
    if isinstance(legend, dict):
        return "M on metadata (per-metric claim_class)"
    return "unstated"


def receipt_figures(key, receipt):
    rows = []
    for label, path in FIGURES.get(key, ()):
        if isinstance(path, tuple):
            numerator, denominator = pointer(receipt, path[0]), pointer(receipt, path[1])
            value = "absent" if numerator is None and denominator is None else f"{shown(numerator)}/{shown(denominator)}"
            rows.append({"key": key, "label": label, "value": value, "pointer": " / ".join(path)})
        else:
            found = pointer(receipt, path)
            rows.append({"key": key, "label": label, "value": "absent" if found is None and not _has(receipt, path)
                         else shown(found), "pointer": path})
    return rows


def _has(value, path):
    parts = path.split("/")
    for part in parts[:-1]:
        value = value.get(part) if isinstance(value, dict) else None
    return isinstance(value, dict) and parts[-1] in value


def coverage_union(spans, duration):
    clipped = sorted((max(0.0, start), min(duration, end)) for start, end in spans
                     if duration is not None and end > start)
    total, current = 0.0, None
    for start, end in clipped:
        if end <= start:
            continue
        if current is None or start > current[1]:
            if current:
                total += current[1] - current[0]
            current = [start, end]
        else:
            current[1] = max(current[1], end)
    if current:
        total += current[1] - current[0]
    return round(total, 6)


def project_store(store):
    rows = []
    revision = store.get("revision") if isinstance(store.get("revision"), int) else None
    for item in store.get("annotations") or []:
        if not isinstance(item, dict):
            continue
        span = item.get("source_span") if isinstance(item.get("source_span"), dict) else {}
        reported = item.get("reported_by") if isinstance(item.get("reported_by"), dict) else {}
        rows.append({
            "id": item.get("id") if isinstance(item.get("id"), str) else None,
            "kind": item.get("kind") if isinstance(item.get("kind"), str) else None,
            "basis": item.get("basis") if isinstance(item.get("basis"), str) else None,
            "claim_label": item.get("claim_label") if isinstance(item.get("claim_label"), str) else None,
            "review_state": item.get("status") if isinstance(item.get("status"), str) else None,
            "reported_by_actor": reported.get("actor") if isinstance(reported.get("actor"), str) else None,
            "source_time_seconds": report.finite(span.get("start_seconds")),
            "end_seconds": report.finite(span.get("end_seconds")),
            "extent_known": span.get("extent_known") if isinstance(span.get("extent_known"), bool) else None,
            "musical_verdict": item.get("musical_verdict") if isinstance(item.get("musical_verdict"), str) else None,
            "revision": revision,
        })
    return rows


def count_by(rows, field):
    counts = {}
    for row in rows:
        label = row.get(field) or "unknown"
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def operator_corpus(store_status, rows, duration):
    base = {"origin": "operator_labelled", "claim_class": "M on metadata", "store_status": store_status,
            "store_bound": store_status == "bound", "approved_expected_rhythm_reference": False,
            "duration_seconds": duration}
    if store_status != "bound":
        base.update({"annotation_count": None, "by_kind": None, "by_basis": None, "by_claim_label": None,
                     "by_review_state": None, "by_reported_actor": None, "covered_seconds": None,
                     "coverage_fraction": None, "musical_phrase_labels": None, "note_labels": None,
                     "reason": store_status, "statement": "operator-labelled coverage unknown: " + store_status})
        return base
    spans = [(row["source_time_seconds"], row["end_seconds"]) for row in rows
             if row["extent_known"] and row["source_time_seconds"] is not None and row["end_seconds"] is not None]
    covered = coverage_union(spans, duration) if duration else None
    fraction = round(covered / duration, 6) if covered is not None and duration else None
    phrases = sum(1 for row in rows if row["kind"] in PHRASE_LABEL_KINDS)
    notes = sum(1 for row in rows if row["kind"] in NOTE_LABEL_KINDS)
    labels = ("0 musical phrase or note labels" if phrases == notes == 0
              else f"{phrases} musical phrase labels and {notes} note labels")
    base.update({"annotation_count": len(rows), "by_kind": count_by(rows, "kind"), "by_basis": count_by(rows, "basis"),
                 "by_claim_label": count_by(rows, "claim_label"), "by_review_state": count_by(rows, "review_state"),
                 "by_reported_actor": count_by(rows, "reported_by_actor"), "covered_seconds": covered,
                 "coverage_fraction": fraction, "musical_phrase_labels": phrases, "note_labels": notes,
                 "phrase_label_kinds": sorted(PHRASE_LABEL_KINDS), "note_label_kinds": sorted(NOTE_LABEL_KINDS),
                 "reason": None,
                 "statement": (f"small labelled corpus: {len(rows)} operator annotation"
                               f"{'' if len(rows) == 1 else 's'} covering {covered:.1f} of "
                               f"{duration:.2f} s; {labels}" if duration and covered is not None
                               else "duration unknown"),
                 "absence_note": "Absence of labels is not evidence of correctness."})
    return base


def generated_banks(receipts):
    for entry, payload in receipts:
        if entry["binding_class"] != "synthetic_bank_not_take":
            continue
        cases = payload.get("cases") if isinstance(payload.get("cases"), list) else []
        cohorts = sorted({case.get("cohort") for case in cases if isinstance(case, dict)
                          and isinstance(case.get("cohort"), str)})
        totals = pointer(payload, "scoring/reference_totals")
        return [{"origin": "synthetic_generated_bank", "claim_class": "S", "receipt_key": entry["key"],
                 "suite": payload.get("suite") if isinstance(payload.get("suite"), str) else None,
                 "bank_sha256": payload.get("bank_sha256"), "case_count": len(cases), "cohorts": cohorts,
                 "reference_totals": totals if isinstance(totals, dict) else None,
                 "real_take_accuracy": shown(payload.get("real_take_accuracy")),
                 "accuracy_scope": shown(payload.get("continuous_riff_accuracy_scope")),
                 "note": "Generated-bank cases are never operator-labelled coverage of the take."}]
    return []


def csv_bytes(fields, rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in fields})
    return buffer.getvalue().encode("utf-8")


def unknowns_with_candidates(analysis):
    values = {name: {"value": value, "reason": reason, "candidate": None} for name, value, reason in UNKNOWNS}
    meter = analysis.get("meter") if isinstance(analysis.get("meter"), dict) else None
    if meter:
        signature = meter.get("time_signature")
        values["meter"]["candidate"] = (f"analysis.meter status={shown(meter.get('status'))}, "
                                        f"time_signature={shown(signature)} (candidate only)")
    return values


def build(run_dir, analysis_run_dir=None, annotation_store=None, output_dir=None, *, receipts_dir=RECEIPTS_DIR,
          registry=RECEIPT_REGISTRY, repo_root=REPO, now=None, after_stage_hook=None):
    tracker = Tracker()
    run_dir = safe_directory(run_dir, "run_dir_invalid")
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise Refusal("manifest_missing")
    manifest_bytes, manifest = load_json_bytes(tracker, manifest_path, MAX_MEMBER_BYTES, "manifest_invalid")
    if not manifest:
        raise Refusal("manifest_invalid")
    source_sha = report.source_identity(manifest)
    if not isinstance(source_sha, str) or not SHA.match(source_sha):
        raise Refusal("source_identity_missing")
    hashes = manifest.get("output_sha256")
    if not isinstance(hashes, dict) or any(not isinstance(v, str) or not SHA.match(v) for v in hashes.values()):
        raise Refusal("manifest_invalid")
    manifest_sha = digest(manifest_bytes)
    run_id = manifest.get("run_id") if isinstance(manifest.get("run_id"), str) else run_dir.name
    safe_id = re.sub(r"[^A-Za-z0-9._-]", "_", run_id)[:96] or "run"
    pcm = manifest.get("pcm") if isinstance(manifest.get("pcm"), dict) else {}
    duration = report.finite(pcm.get("duration_seconds"))
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")

    # Rule 2: stream-hash every listed stage file; names and hashes only.
    stage_files = []
    for name, expected in sorted(hashes.items()):
        local = report.strict_artifact(run_dir, name)
        if not local:
            reason = "listed_file_absent" if not (run_dir / name).exists() else "unsafe_path_not_hashed"
            stage_files.append({"name": name, "expected_sha256": expected, "status": "absent", "reason": reason})
            continue
        if tracker.sha256(run_dir / local) != expected:
            raise Refusal("stage_hash_mismatch")
        stage_files.append({"name": name, "expected_sha256": expected, "status": "verified", "reason": None})

    # Rule 3: analysis-run selection.
    analysis_dir, basis = None, "unavailable"
    if (run_dir / "analysis.json").is_file():
        analysis_dir, basis = run_dir, "run_local"
    elif analysis_run_dir is not None:
        analysis_dir, basis = safe_directory(analysis_run_dir, "analysis_run_dir_invalid"), "explicit"
    else:
        application = manifest.get("capture_profile_application")
        authoring = application.get("authoring_dir") if isinstance(application, dict) else None
        if isinstance(authoring, str) and Path(authoring).is_absolute() and len(Path(authoring).parts) > 3:
            analysis_dir = safe_directory(Path(authoring).parents[1], "analysis_run_dir_invalid")
            basis = "parent_run_from_capture_profile_authoring_dir"
    analysis_manifest, analysis_manifest_sha = {}, None
    if analysis_dir is not None:
        if analysis_dir == run_dir:
            analysis_manifest, analysis_manifest_sha = manifest, manifest_sha
        else:
            path = analysis_dir / "manifest.json"
            if not path.is_file() or path.is_symlink():
                raise Refusal("analysis_run_manifest_missing")
            data, analysis_manifest = load_json_bytes(tracker, path, MAX_MEMBER_BYTES, "analysis_run_manifest_invalid")
            analysis_manifest_sha = digest(data)
            if report.source_identity(analysis_manifest) != source_sha:
                raise Refusal("analysis_run_source_mismatch")

    output = Path(output_dir) if output_dir is not None else \
        repo_root / "artifacts" / "s2" / "report_d6" / "bundles" / f"{safe_id}-{stamp}"
    output = check_output_dir(Path(os.path.abspath(output)), run_dir, analysis_dir)

    # Rule 4: analysis binding through report.analysis_lineage.
    members = {}
    analysis, analysis_sha, lineage, analysis_status = {}, None, "unavailable", "unavailable"
    if analysis_dir is not None and (analysis_dir / "analysis.json").is_file():
        try:
            raw = tracker.read_bytes(analysis_dir / "analysis.json", MAX_INPUT_JSON_BYTES)
            candidate = json.loads(raw)
        except (ValueError, UnicodeError):
            candidate, raw = None, b""
        if not isinstance(candidate, dict):
            lineage = analysis_status = "rejected_invalid_json"
        else:
            lineage = report.analysis_lineage(run_dir, manifest, candidate, sha256=tracker.sha256)
            original = pointer(candidate, "source_lineage/original_source_sha256")
            if lineage in BOUND_LINEAGE and original is not None and original != source_sha:
                analysis_status = "rejected_original_source_mismatch"
            elif lineage in BOUND_LINEAGE:
                analysis_status = "bound"
                analysis, analysis_sha = candidate, digest(raw)
                members["analysis.json"] = member(raw, "bound_payload", analysis_dir / "analysis.json", lineage)
            else:
                analysis_status = lineage
    analyzed_sha = report.source_identity(analysis) if analysis else hashes.get("denoised.wav")

    # Rule 5: dag/flags/markers via report.auxiliary_evidence, plus the bound-analysis hash.
    auxiliary = {name: {"status": "unavailable", "copied": False} for name in ("dag", "flags", "markers", "phrases")}
    payloads = {}
    if analysis_dir is not None:
        payloads, statuses = report.auxiliary_evidence(analysis_dir, analysis_manifest, load_json=tracker.load_json,
                                                       sha256=tracker.sha256)
        for name, status in statuses.items():
            auxiliary[name]["status"] = status
        graph_hashes = payloads.get("dag", {}).get("artifact_hashes", {})
        if isinstance(graph_hashes, dict) and "analysis.json" in graph_hashes and \
                (analysis_sha is None or graph_hashes["analysis.json"] != analysis_sha):
            for name in ("dag", "flags", "markers"):
                if name in payloads:
                    auxiliary[name]["status"] = "rejected_stale_analysis_binding"
            payloads = {}
        for name in ("dag", "flags", "markers"):
            if name in payloads:
                path = analysis_dir / f"{name}.json"
                members[f"{name}.json"] = member(tracker.read_bytes(path, MAX_INPUT_JSON_BYTES), "bound_payload",
                                                 path, auxiliary[name]["status"])
                auxiliary[name]["copied"] = True
        phrases_path = analysis_dir / "phrases.json"
        if phrases_path.is_file():
            try:
                raw = tracker.read_bytes(phrases_path, MAX_INPUT_JSON_BYTES)
                phrases = json.loads(raw)
            except (ValueError, UnicodeError):
                phrases = None
            if not isinstance(phrases, dict):
                auxiliary["phrases"]["status"] = "rejected_invalid_json"
            else:
                state = report.analysis_lineage(run_dir, manifest, phrases, sha256=tracker.sha256)
                original = pointer(phrases, "source_lineage/original_source_sha256")
                if state in BOUND_LINEAGE and original is not None and original != source_sha:
                    state = "rejected_original_source_mismatch"
                auxiliary["phrases"]["status"] = state
                if state in BOUND_LINEAGE:
                    members["phrases.json"] = member(raw, "bound_payload", phrases_path, state)
                    auxiliary["phrases"]["copied"] = True

    # Rule 7: fixed S2 receipt registry.
    data_root = data_root_for(run_dir, repo_root)
    context = {"run_id": run_id, "manifest_sha256": manifest_sha, "source_sha256": source_sha,
               "analyzed_sha256": analyzed_sha, "data_root": data_root}
    receipts, receipt_payloads, figures = [], [], []
    for key, name in registry:
        path = Path(receipts_dir) / name
        if is_media_name(name):
            raise Refusal("media_member_refused")
        if not path.is_file() or path.is_symlink():
            raise Refusal("receipt_missing")
        if path.stat().st_size > MAX_RECEIPT_BYTES:
            raise Refusal("receipt_too_large")
        data = tracker.read_bytes(path, MAX_RECEIPT_BYTES)
        if has_media_magic(data):
            raise Refusal("media_member_refused")
        try:
            payload = json.loads(data)
        except (ValueError, UnicodeError):
            raise Refusal("receipt_invalid") from None
        if not isinstance(payload, dict):
            raise Refusal("receipt_invalid")
        binding, binding_basis, evidence, chain = classify_receipt(payload, context, tracker)
        members[f"receipts/{key}.json"] = member(data, "s2_receipt", path, binding)
        if chain:
            members[f"receipts/{key}.chain-manifest.json"] = member(chain["bytes"], "binding_evidence",
                                                                    chain["path"], binding)
        entry = {"key": key, "file": name, "sha256": digest(data), "bytes": len(data), "binding_class": binding,
                 "binding_basis": binding_basis, "binding_evidence": evidence,
                 "claim_class": claim_class(payload, binding),
                 "presentation": "receipt's own figures, quoted not re-measured"}
        receipts.append(entry)
        receipt_payloads.append((entry, payload))
        figures.extend(dict(row, claim_class=entry["claim_class"], binding_class=binding)
                       for row in receipt_figures(key, payload))

    # Rule 8: operator annotation store (structured fields only).
    store_path = Path(annotation_store) if annotation_store is not None else data_root / DEFAULT_STORE_REL
    store_status, store_rows, store_sha = "annotation_store_absent", [], None
    if store_path.is_file() and not store_path.is_symlink():
        try:
            data = tracker.read_bytes(store_path, MAX_RECEIPT_BYTES)
            store = json.loads(data)
        except Refusal:
            store, data = None, b""
        except (ValueError, UnicodeError):
            store, data = None, b""
        store_sha = digest(data) if data else None
        if not isinstance(store, dict):
            store_status = "annotation_store_invalid"
        elif store.get("source_sha256") != source_sha or store.get("manifest_sha256") != manifest_sha:
            store_status = "annotation_store_unbound"
        else:
            store_status = "bound"
            store_rows = project_store(store)
            projection = {"schema": SCHEMA + "#annotations", "store_sha256": store_sha,
                          "source_sha256": source_sha, "manifest_sha256": manifest_sha,
                          "text_included": False, "annotations": store_rows}
            members["annotations.json"] = member(canonical(projection), "derived_projection", store_path, "bound",
                                                 derived_from=store_path.name, origin_sha256=store_sha)
    corpus = {"operator_labelled": operator_corpus(store_status, store_rows, duration),
              "generated_banks": generated_banks(receipt_payloads),
              "pools_summed": False,
              "annotation_store_sha256": store_sha}

    unknowns = unknowns_with_candidates(analysis)

    # Derived base-R tables.
    events = analysis.get("events") if isinstance(analysis.get("events"), list) else []
    event_rows = [{"audio_relative_seconds": report.finite(event.get("audio_relative_seconds")),
                   "kind": event.get("kind") if isinstance(event.get("kind"), str) else "unknown"}
                  for event in events if isinstance(event, dict)]
    if analysis:
        members["tables/events.csv"] = member(csv_bytes(["audio_relative_seconds", "kind"], event_rows),
                                              "derived_table", analysis_dir / "analysis.json", "bound",
                                              derived_from="analysis.json", origin_sha256=analysis_sha)
    flags = payloads.get("flags", {}).get("flags") if "flags" in payloads else None
    flag_rows = []
    flags_total = len(flags) if isinstance(flags, list) else 0
    for index, flag in enumerate(flags[:MAX_FLAG_ROWS] if isinstance(flags, list) else []):
        if not isinstance(flag, dict):
            continue
        flag_rows.append({"index": index, "kind": shown(flag.get("kind")),
                          "source_time_seconds": report.finite(flag.get("source_time_seconds")),
                          "end_seconds": report.finite(flag.get("end_seconds")),
                          "confidence": shown(flag.get("confidence")), "status": shown(flag.get("status")),
                          "performance_issue_confirmed": shown(flag.get("performance_issue_confirmed")),
                          "authorship": "detector_hypothesis"})
    if "flags" in payloads:
        members["tables/review_flags.csv"] = member(
            csv_bytes(["index", "kind", "source_time_seconds", "end_seconds", "confidence", "status",
                       "performance_issue_confirmed", "authorship"], flag_rows),
            "derived_table", analysis_dir / "flags.json", "bound", derived_from="flags.json",
            origin_sha256=digest(members["flags.json"]["bytes"]))
    tables = {
        "identity.csv": (["field", "value"], [
            {"field": "run_id", "value": run_id},
            {"field": "manifest_sha256", "value": manifest_sha},
            {"field": "source_sha256", "value": source_sha},
            {"field": "duration_seconds", "value": shown(duration)},
            {"field": "analysis_basis", "value": basis},
            {"field": "analysis_run_id", "value": analysis_manifest.get("run_id") if analysis_dir else None},
            {"field": "analysis_lineage", "value": lineage},
            {"field": "analysis_status", "value": analysis_status},
            {"field": "analysis_sha256", "value": analysis_sha},
            {"field": "event_count", "value": len(event_rows)},
            {"field": "review_flags_total", "value": flags_total},
            {"field": "review_flags_rows", "value": len(flag_rows)},
            {"field": "declared_tempo_bpm", "value": shown(pointer(analysis, "declared_tempo/bpm")) if analysis else None},
            {"field": "fitted_pulse_bpm", "value": shown(pointer(analysis, "click_grid/bpm")) if analysis else None},
        ]),
        "stage_files.csv": (["name", "status", "expected_sha256", "reason"], stage_files),
        "auxiliary.csv": (["payload", "status", "copied"],
                          [{"payload": name, "status": row["status"], "copied": shown(row["copied"])}
                           for name, row in auxiliary.items()]),
        "receipts.csv": (["key", "file", "sha256", "binding_class", "binding_basis", "claim_class"], receipts),
        "receipt_figures.csv": (["key", "label", "value", "binding_class", "claim_class", "pointer"], figures),
        "annotations.csv": (["id", "kind", "basis", "claim_label", "review_state", "reported_by_actor",
                             "source_time_seconds", "end_seconds", "extent_known", "musical_verdict"], store_rows),
        "corpus.csv": (["pool", "field", "value"], corpus_rows(corpus)),
        "unknowns.csv": (["field", "value", "reason", "candidate"],
                         [{"field": name, "value": shown(row["value"]), "reason": row["reason"],
                           "candidate": row["candidate"]} for name, row in unknowns.items()]),
    }
    for name, (fields, rows) in tables.items():
        members[f"tables/{name}"] = member(csv_bytes(fields, rows), "derived_table", None, "derived",
                                           derived_from="bundle_index")
    members["manifest.json"] = member(manifest_bytes, "run_manifest", manifest_path, "run_identity")
    listing = sorted(members)
    members["tables/members.csv"] = member(csv_bytes(
        ["bundle_path", "role", "binding_status", "bytes", "bundle_sha256", "origin"],
        [dict(members[path]["meta"], bundle_path=path,
              origin=members[path]["meta"]["derived_from"] or Path(members[path]["meta"]["origin_path"] or "").name)
         for path in listing]), "derived_table", None, "derived", derived_from="bundle_index")

    total = 0
    for path, row in members.items():
        if is_media_name(path) or has_media_magic(row["bytes"]):
            raise Refusal("media_member_refused")
        if len(row["bytes"]) > MAX_MEMBER_BYTES:
            raise Refusal("bundle_too_large")
        total += len(row["bytes"])
    if total > MAX_TOTAL_BYTES:
        raise Refusal("bundle_too_large")
    member_list = [dict(members[path]["meta"], bundle_path=path) for path in sorted(members)]

    run = {"run_id": run_id, "manifest_sha256": manifest_sha, "source_sha256": source_sha,
           "duration_seconds": duration, "stage_files": stage_files,
           "stage_files_verified": sum(1 for row in stage_files if row["status"] == "verified"),
           "stage_files_listed": len(stage_files),
           "analysis": {"basis": basis, "analysis_run_id": analysis_manifest.get("run_id") if analysis_dir else None,
                        "analysis_run_manifest_sha256": analysis_manifest_sha, "lineage": lineage,
                        "status": analysis_status, "sha256": analysis_sha, "analyzed_input_sha256": analyzed_sha,
                        "event_count": len(event_rows)},
           "auxiliary": auxiliary, "corpus_sha256": digest(canonical(corpus)),
           "review_flags": {"total": flags_total, "rows": len(flag_rows), "row_cap": MAX_FLAG_ROWS,
                            "authorship": "detector_hypothesis"},
           "annotation_store_status": store_status}

    # Stage, recheck protected inputs, then publish atomically.
    staging = Path(f"{output}.staging-{os.getpid()}")
    if staging.exists():
        raise Refusal("output_dir_exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        staging.mkdir()
        for path in sorted(members):
            target = staging / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(members[path]["bytes"])
        if after_stage_hook:
            after_stage_hook()
        changed = tracker.recheck()
        if changed:
            raise Refusal("input_changed_during_build")
        run["readback"] = {"status": "unchanged", "files_checked": len(tracker.seen), "changed": [],
                           "fields": ["sha256", "size", "mtime_ns"],
                           "files": [{"path": key, "sha256": value["sha256"], "size": value["size"]}
                                     for key, value in sorted(tracker.seen.items())]}
        index = {"schema": SCHEMA, "hash_scope": list(HASH_SCOPE), "run": run, "members": member_list,
                 "receipts": receipts, "unknowns": unknowns}
        index["bundle_sha256"] = digest(canonical({key: index[key] for key in HASH_SCOPE}))
        index.update({
            "corpus": corpus, "created_utc": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "builder": {"script": "scripts/report_bundle.py", "script_sha256": report.sha256(Path(__file__)),
                        "report_py_sha256": report.sha256(REPO / "scripts" / "report.py")},
            "limits": {"member_bytes": MAX_MEMBER_BYTES, "total_bytes": MAX_TOTAL_BYTES,
                       "receipt_bytes": MAX_RECEIPT_BYTES, "review_flag_rows": MAX_FLAG_ROWS},
            "total_member_bytes": total,
            "media_policy": "no audio/video bytes, no media URLs; stage files recorded by name and sha256 only",
            "claims": {"measurements": "file hashes, sizes and metadata counts computed by this build",
                       "quoted": "receipt figures are each receipt's own measurements, not re-measured",
                       "listening": "none", "adoption": "none"},
        })
        temporary = staging / ".bundle.json.tmp"
        temporary.write_bytes(json.dumps(index, indent=1, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        os.replace(temporary, staging / "bundle.json")
        if output.exists():
            raise Refusal("output_dir_exists")
        os.rename(staging, output)
    except BaseException as error:
        shutil.rmtree(staging, ignore_errors=True)
        reason = error.code if isinstance(error, Refusal) else type(error).__name__
        failed = Path(f"{output}.failed")
        try:
            failed.mkdir(parents=True, exist_ok=True)
            (failed / "report-bundle.failed.json").write_text(json.dumps(
                {"status": "refused" if isinstance(error, Refusal) else "error", "reason": reason,
                 "published": False}, sort_keys=True) + "\n", encoding="utf-8")
        except OSError:
            pass
        raise
    return {"status": "built", "bundle_dir": str(output), "bundle_sha256": index["bundle_sha256"],
            "member_count": len(member_list), "total_member_bytes": total, "run_id": run_id,
            "analysis_lineage": lineage, "analysis_status": analysis_status,
            "receipts": {entry["key"]: entry["binding_class"] for entry in receipts},
            "annotation_store_status": store_status, "readback": "unchanged",
            "files_checked": len(tracker.seen)}


def member(data, role, origin_path, binding_status, *, derived_from=None, origin_sha256=None):
    data = bytes(data)
    sha = digest(data)
    if origin_sha256 is None and derived_from is None and origin_path is not None:
        origin_sha256 = sha
    return {"bytes": data, "meta": {
        "role": role, "origin_path": str(origin_path) if origin_path is not None else None,
        "derived_from": derived_from, "origin_sha256": origin_sha256, "bundle_sha256": sha,
        "bytes": len(data), "binding_status": binding_status}}


def corpus_rows(corpus):
    rows = []
    operator = corpus["operator_labelled"]
    for field in ("statement", "store_status", "store_bound", "annotation_count", "covered_seconds",
                  "duration_seconds", "coverage_fraction", "musical_phrase_labels", "note_labels",
                  "approved_expected_rhythm_reference", "absence_note"):
        rows.append({"pool": "operator_labelled", "field": field, "value": shown(operator.get(field))})
    for field in ("by_kind", "by_basis", "by_claim_label", "by_review_state", "by_reported_actor"):
        value = operator.get(field)
        rows.append({"pool": "operator_labelled", "field": field,
                     "value": "; ".join(f"{k}={v}" for k, v in value.items()) if isinstance(value, dict) else "null"})
    if not corpus["generated_banks"]:
        rows.append({"pool": "generated_banks", "field": "status", "value": "no generated-bank receipt bound"})
    for bank in corpus["generated_banks"]:
        for field in ("origin", "suite", "case_count", "real_take_accuracy", "accuracy_scope", "note"):
            rows.append({"pool": "generated_banks", "field": field, "value": shown(bank.get(field))})
        rows.append({"pool": "generated_banks", "field": "cohorts", "value": "; ".join(bank["cohorts"])})
        totals = bank.get("reference_totals")
        if isinstance(totals, dict):
            rows.append({"pool": "generated_banks", "field": "reference_totals",
                         "value": "; ".join(f"{k}={shown(v)}" for k, v in sorted(totals.items()))})
    return rows


def verify(bundle_dir, *, check_origin=False):
    """Return (status, details); status is 'verified' or 'refused:<reason>'."""
    try:
        root = safe_directory(bundle_dir, "bundle_missing")
    except Refusal as refusal:
        return f"refused:{refusal.code}", {}
    index_path = root / "bundle.json"
    if not index_path.is_file() or index_path.is_symlink():
        return "refused:bundle_missing", {}
    try:
        index = json.loads(index_path.read_bytes())
    except (ValueError, UnicodeError, OSError):
        return "refused:bundle_invalid", {}
    if not isinstance(index, dict) or index.get("schema") != SCHEMA or not isinstance(index.get("members"), list) \
            or any(key not in index for key in HASH_SCOPE):
        return "refused:bundle_invalid", {}
    listed = set()
    total = 0
    for row in index["members"]:
        name = row.get("bundle_path") if isinstance(row, dict) else None
        if not isinstance(name, str) or not name or Path(name).is_absolute() or ".." in Path(name).parts \
                or name == "bundle.json" or "\\" in name:
            return "refused:bundle_invalid", {}
        if is_media_name(name):
            return "refused:media_member_refused", {}
        path = root / name
        if path.is_symlink() or not path.is_file():
            return "refused:member_missing", {"member": name}
        if path.stat().st_size > MAX_MEMBER_BYTES:
            return "refused:bundle_too_large", {"member": name}
        data = path.read_bytes()
        total += len(data)
        if has_media_magic(data):
            return "refused:media_member_refused", {"member": name}
        if digest(data) != row.get("bundle_sha256") or len(data) != row.get("bytes"):
            return "refused:member_hash_mismatch", {"member": name}
        listed.add(name)
    if total > MAX_TOTAL_BYTES:
        return "refused:bundle_too_large", {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir() and not path.is_symlink():
            continue
        if relative != "bundle.json" and relative not in listed:
            return "refused:unexpected_member", {"member": relative}
    expected = digest(canonical({key: index[key] for key in HASH_SCOPE}))
    if expected != index.get("bundle_sha256"):
        return "refused:bundle_hash_mismatch", {}
    run = index.get("run") if isinstance(index.get("run"), dict) else {}
    if "corpus" in index and run.get("corpus_sha256") != digest(canonical(index["corpus"])):
        return "refused:bundle_hash_mismatch", {"field": "corpus"}
    if check_origin:
        for row in index["members"]:
            origin, sha = row.get("origin_path"), row.get("origin_sha256")
            if not origin or not sha:
                continue
            path = Path(origin)
            if not path.is_file():
                return "refused:origin_missing", {"member": row["bundle_path"]}
            if report.sha256(path) != sha:
                return "refused:origin_changed", {"member": row["bundle_path"]}
    return "verified", {"bundle_sha256": index["bundle_sha256"], "member_count": len(listed),
                        "total_member_bytes": total, "origin_checked": bool(check_origin)}


def describe():
    return {
        "schema": SCHEMA, "tool": "report_bundle", "stdlib_only": True,
        "commands": {
            "build": "build --run-dir D [--analysis-run-dir A] [--annotation-store S] [--output-dir O]",
            "verify": "verify --bundle-dir B [--check-origin] [--status-only]",
            "describe": "describe",
        },
        "exit_codes": {"0": "built or verified", "2": "refused", "1": "unexpected error (class name only)"},
        "refusals": sorted({"run_dir_invalid", "manifest_missing", "manifest_invalid", "source_identity_missing",
                            "stage_hash_mismatch", "analysis_run_dir_invalid", "analysis_run_manifest_missing",
                            "analysis_run_manifest_invalid", "analysis_run_source_mismatch", "receipt_missing",
                            "receipt_invalid", "receipt_too_large", "media_member_refused", "bundle_too_large",
                            "output_dir_exists", "output_dir_protected", "input_changed_during_build",
                            "input_too_large", "member_hash_mismatch", "member_missing", "unexpected_member",
                            "bundle_hash_mismatch", "bundle_missing", "bundle_invalid", "origin_changed",
                            "origin_missing"}),
        "binding_classes": list(BINDING_CLASSES),
        "receipt_registry": [{"key": key, "file": name} for key, name in RECEIPT_REGISTRY],
        "hash_scope": list(HASH_SCOPE),
        "unknown_fields": [name for name, _, _ in UNKNOWNS],
        "limits": {"member_bytes": MAX_MEMBER_BYTES, "total_bytes": MAX_TOTAL_BYTES,
                   "receipt_bytes": MAX_RECEIPT_BYTES, "review_flag_rows": MAX_FLAG_ROWS},
        "media": {"extensions_refused": sorted(MEDIA_EXTENSIONS),
                  "magic_refused": ["RIFF/WAVE", "ftyp", "ID3", "fLaC", "OggS", "FORM", "caff", "EBML"]},
        "never": ["decode media", "copy audio or video", "write run directories", "adopt defaults",
                  "claim listening acceptance", "grade note correctness"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build")
    build_parser.add_argument("--run-dir", required=True)
    build_parser.add_argument("--analysis-run-dir")
    build_parser.add_argument("--annotation-store")
    build_parser.add_argument("--output-dir")
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--bundle-dir", required=True)
    verify_parser.add_argument("--check-origin", action="store_true")
    verify_parser.add_argument("--status-only", action="store_true")
    commands.add_parser("describe")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "describe":
            print(json.dumps(describe(), indent=1, sort_keys=True))
            return 0
        if arguments.command == "verify":
            status, details = verify(arguments.bundle_dir, check_origin=arguments.check_origin)
            if arguments.status_only:
                print(status)
            else:
                print(json.dumps({"status": status, **details}, sort_keys=True))
            return 0 if status == "verified" else 2
        result = build(arguments.run_dir, arguments.analysis_run_dir, arguments.annotation_store,
                       arguments.output_dir)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Refusal as refusal:
        print(json.dumps({"status": "refused", "reason": refusal.code}, sort_keys=True))
        return 2
    except Exception as error:  # noqa: BLE001 - class name only, never paths or private text
        print(json.dumps({"status": "error", "error": type(error).__name__}, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
