#!/usr/bin/env python3
"""Project operator arrangement intent onto a fitted click grid from one anchor.

Deterministic stdlib arithmetic (PHRASES_S2 section 4). It never decodes audio,
reruns a detector, or moves a boundary toward an observation. Output spans are
an intent projection, not detected phrases; real-take phrase correctness stays
unknown until the operator marks boundaries. The scorer compares the primary
projection with >= 10 operator-authored boundary marks and otherwise abstains.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_AREA = ROOT / "artifacts" / "s2" / "phrase_anchor_riff"
SCHEMA_VERSION = 1
MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_EVENTS = 200_000
WINDOW_OPERATOR_CLICKS = 4
SUPPORTED_MIN_FRACTION = .75
SUPPORTED_MAX_MEDIAN_OFFSET_MS = 30.
WEAK_MIN_FRACTION = .25
SHIFT_HYPOTHESES_CLICKS = (-2, -1, 1, 2)
MIN_OPERATOR_MARKS = 10
SCORE_TOLERANCE_SECONDS = .1
ORDINAL = {"unsupported": 0, "uncertain": 1, "weak": 2, "supported": 3}
GRID_ORDINAL = {"grid_supported": "supported", "grid_weak": "weak", "grid_unsupported": "unsupported"}
STRUCTURAL_ORDINAL = {"nominal": "supported", "breakdown_execution_uncertain": "uncertain",
                      "uncertain_upstream_breakdown": "uncertain", "presumed_repeat_section": "uncertain",
                      "outside_source": "unsupported"}
MARKS_SCHEMA = "phrase-boundaries-v1"
ANNOTATION_BASES = ("operator_assertion", "operator_context")
ANNOTATION_KIND = "phrase_duration"
ANCHOR_UNCONFIRMED = "review_candidate_not_confirmed_downbeat"
ANCHOR_OPERATOR = "operator_marked_anchor_downbeat_unconfirmed"
UNKNOWNS = {
    "real_take_phrase_correctness": "unknown_until_operator_marks_boundaries",
    "observed_click_count": None,
    "click_identity": "unverified",
    "physical_capture_latency": "uncalibrated",
    "detector_delay": "uncalibrated",
    "downbeat_confirmed": False,
    "meter": "unknown",
    "breakdown1_execution": "unknown_operator_reported_possible_rush_or_skip",
    "chorus2_count_provenance": "presumed_repeat",
    "performance_issue_confirmed": False,
    "missed_or_extra_notes": "not_assessed_no_approved_reference",
    "listening_acceptance": "not_performed",
}
LIMITATIONS = [
    "Spans are operator intent projected on a constant-period global grid fit; they are not detected phrases.",
    "clicks_per_grid_period is an operator-supplied mapping, never inferred; odd lattice indices under r=2 are interpolated half-periods, not observed clicks.",
    "The anchor is a review candidate unless an operator-authored mark supports it; a one-click anchor error shifts every span by one operator click.",
    "join_confidence is an ordinal heuristic with engineering thresholds, not a probability or calibrated error bound.",
    "Every boundary after breakdown 1 starts inherits its unknown execution; breakdown shift hypotheses are never adopted.",
    "Local clock drift appears only as measured grid offsets near each join; detector and capture latency are uncalibrated.",
]


class DomainError(ValueError):
    """Bounded, user-facing refusal reason (exit status 2)."""


def require(test, reason):
    if not test:
        raise DomainError(reason)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha256(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def is_sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def finite(value, label, low=-math.inf, high=math.inf):
    require(type(value) in (int, float) and math.isfinite(float(value)) and low <= float(value) <= high,
            f"invalid_{label}")
    return float(value)


def _unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "duplicate_json_key")
        value[key] = item
    return value


def _nonfinite(_):
    raise DomainError("nonfinite_json_number")


def _float(text):
    value = float(text)
    require(math.isfinite(value), "nonfinite_json_number")
    return value


def parse_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_unique, parse_constant=_nonfinite, parse_float=_float)
    except DomainError:
        raise
    except (ValueError, RecursionError) as exc:
        raise DomainError("invalid_json") from exc


class Input:
    """A bounded, local, non-symlink regular JSON file hashed at read time."""

    def __init__(self, path):
        path = Path(path).expanduser().absolute()
        require(".." not in path.parts, "input_path_traversal")
        require(not path.is_symlink(), "input_symlink_rejected")
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except OSError as exc:
            raise DomainError("input_unreadable") from exc
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode), "input_regular_file_required")
            require(before.st_size <= MAX_INPUT_BYTES, "input_byte_bound")
            with os.fdopen(os.dup(fd), "rb") as handle:
                raw = handle.read(MAX_INPUT_BYTES + 1)
            after = os.fstat(fd)
        finally:
            os.close(fd)
        require(len(raw) == before.st_size <= MAX_INPUT_BYTES, "input_read_extent_bound")
        require((before.st_size, before.st_mtime_ns, before.st_ino) == (after.st_size, after.st_mtime_ns, after.st_ino),
                "input_changed_during_read")
        self.path, self.raw, self.sha256 = path, raw, sha256(raw)
        self.value = parse_json(raw)

    def unchanged(self):
        try:
            return not self.path.is_symlink() and file_sha256(self.path) == self.sha256
        except OSError:
            return False


def recheck(inputs):
    for item in inputs:
        require(item.unchanged(), "input_changed_after_read")


def output_path(value):
    path = Path(value).expanduser().absolute()
    area = OUTPUT_AREA.absolute()
    require(".." not in path.parts and path.is_relative_to(area) and path != area, "output_outside_lane_area")
    for parent in (path, *path.parents):
        if parent == area.parent:
            break
        require(not parent.is_symlink(), "output_symlink_rejected")
    require(not path.exists(), "output_exists")
    return path


def write_new(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    require(len(raw) <= MAX_OUTPUT_BYTES, "output_byte_bound")
    path = output_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
    return sha256(raw)


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def worker_sha256():
    return file_sha256(Path(__file__).resolve())


# ---------------------------------------------------------------- grid ----

def parse_grid(value):
    """Validate the fitted click grid fields this lane consumes."""
    require(isinstance(value, dict) and value.get("schema_version") == 1, "clicks_schema_unsupported")
    grid = value.get("click_grid")
    require(isinstance(grid, dict), "click_grid_missing")
    period = finite(grid.get("period_seconds"), "grid_period", 1e-3, 10.)
    require(period > 0, "invalid_grid_period")
    phase = finite(grid.get("phase_seconds_audio_relative"), "grid_phase", -3600., 3600.)
    timeline = value.get("timeline")
    require(isinstance(timeline, dict), "clicks_timeline_missing")
    start = finite(timeline.get("audio_stream_start_seconds"), "audio_stream_start", -86400., 86400.)
    pcm = value.get("pcm")
    require(isinstance(pcm, dict), "clicks_pcm_missing")
    duration = finite(pcm.get("duration_seconds"), "pcm_duration", 1e-6, 86400.)
    require(duration > 0, "invalid_pcm_duration")
    events = grid.get("observed_events")
    require(isinstance(events, list) and len(events) <= MAX_EVENTS, "observed_events_bound")
    best = {}
    for event in events:
        require(isinstance(event, dict), "observed_event_object_required")
        index = event.get("beat_index")
        require(type(index) is int and abs(index) <= 10_000_000, "observed_event_beat_index")
        offset = finite(event.get("grid_offset_ms"), "observed_event_offset", -60000., 60000.)
        if index not in best or abs(offset) < abs(best[index]):
            best[index] = offset
    source = value.get("source") if isinstance(value.get("source"), dict) else {}
    lineage = value.get("source_lineage") if isinstance(value.get("source_lineage"), dict) else {}
    analyzed = source.get("sha256", lineage.get("analyzed_input_sha256"))
    require(is_sha(analyzed), "grid_analyzed_input_sha256_missing")
    require(lineage.get("analyzed_input_sha256") in (None, analyzed), "grid_analyzed_input_binding_mismatch")
    original = lineage.get("original_source_sha256")
    require(original is None or is_sha(original), "grid_original_source_sha256_invalid")
    mapping = lineage.get("sample_mapping") if isinstance(lineage.get("sample_mapping"), dict) else {}
    return {"period": period, "phase": phase, "start": start, "duration": duration,
            "observed_offsets_ms": best, "observed_event_count": len(events),
            "analyzed_input_sha256": analyzed, "original_source_sha256": original,
            "no_time_stretch_verified": mapping.get("no_time_stretch") is True,
            "bpm": grid.get("bpm"), "identity": grid.get("identity"),
            "median_absolute_residual_ms": grid.get("median_absolute_residual_ms"),
            "candidate_coverage": grid.get("candidate_coverage")}


class Lattice:
    """Operator-click lattice t(k) = s0 + phi + k * P / r."""

    def __init__(self, grid, clicks_per_grid_period):
        require(type(clicks_per_grid_period) is int and clicks_per_grid_period in (1, 2),
                "clicks_per_grid_period_must_be_1_or_2")
        self.grid, self.r = grid, clicks_per_grid_period
        self.P, self.phi, self.s0 = grid["period"], grid["phase"], grid["start"]
        self.p = self.P / self.r
        self.end = self.s0 + grid["duration"]

    def time(self, k):
        return self.s0 + self.phi + k * self.p

    def beat_time(self, j):
        return self.s0 + self.phi + j * self.P

    def interpolated(self, k):
        return self.r == 2 and k % 2 == 1

    def beat_index(self, k):
        return None if self.interpolated(k) else k // self.r

    def within(self, seconds):
        return self.s0 <= seconds <= self.end

    def snap(self, seconds):
        seconds = finite(seconds, "anchor_seconds", -86400., 86400.)
        k = math.floor((seconds - self.s0 - self.phi) / self.p + .5)
        require(k >= 0, "anchor_before_grid_origin")
        residual = seconds - self.time(k)
        require(abs(residual) <= self.p / 4 + 1e-12, "anchor_snap_residual_exceeds_quarter_click")
        return k, residual

    def components(self, k):
        """Measured grid support in a +-4 operator-click window around lattice index k."""
        center = self.time(k)
        half = WINDOW_OPERATOR_CLICKS * self.p
        low, high = max(center - half, self.s0), min(center + half, self.end)
        expected = []
        if low <= high:
            first = math.ceil((low - self.s0 - self.phi) / self.P - 1e-9)
            last = math.floor((high - self.s0 - self.phi) / self.P + 1e-9)
            expected = [j for j in range(first, last + 1) if self.within(self.beat_time(j))]
        offsets = [self.grid["observed_offsets_ms"][j] for j in expected if j in self.grid["observed_offsets_ms"]]
        support = len(offsets) / len(expected) if expected else None
        median = None
        if offsets:
            ordered = sorted(abs(v) for v in offsets)
            middle = len(ordered) // 2
            median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
        if support is not None and support >= SUPPORTED_MIN_FRACTION and median is not None \
                and median <= SUPPORTED_MAX_MEDIAN_OFFSET_MS:
            label = "grid_supported"
        elif support is not None and support >= WEAK_MIN_FRACTION:
            label = "grid_weak"
        else:
            label = "grid_unsupported"
        return {"window_operator_clicks": WINDOW_OPERATOR_CLICKS, "window_seconds": [center - half, center + half],
                "expected_grid_beats": len(expected), "observed_grid_beats": len(offsets),
                "support_fraction": support, "median_abs_grid_offset_ms": median,
                "on_interpolated_half_period": self.interpolated(k), "grid_label": label,
                "basis": "measured_fitted_grid_observed_events"}


# --------------------------------------------------------- expansion ----

def anchor_from_args(lattice, lattice_index=None, seconds=None):
    require((lattice_index is None) != (seconds is None), "exactly_one_anchor_required")
    if lattice_index is not None:
        require(type(lattice_index) is int and 0 <= lattice_index <= 1_000_000, "invalid_anchor_lattice_index")
        return {"method": "lattice_index", "input_value": lattice_index, "k0": lattice_index,
                "snap_residual_seconds": None}
    k0, residual = lattice.snap(seconds)
    return {"method": "source_seconds_snapped_to_lattice", "input_value": float(seconds), "k0": k0,
            "snap_residual_seconds": residual, "snap_residual_sign": "input_minus_lattice_time",
            "snap_refusal_bound_seconds": lattice.p / 4}


def evidence_summary(evidence, lattice, anchor_time, original_sha):
    if evidence is None:
        return {"evidence_sha256": None, "evidence_path": None, "evidence_analyzed_input_sha256": None,
                "evidence_source_sha256": None, "operator_authored": False, "matched_evidence_candidate": None}
    value = evidence.value
    require(isinstance(value, dict), "anchor_evidence_object_required")
    source = value.get("source_sha256")
    require(source is None or is_sha(source), "anchor_evidence_source_invalid")
    require(source is None or original_sha is None or source == original_sha, "anchor_evidence_source_mismatch")
    analyzed = value.get("analyzed_input_sha256")
    operator = False
    if value.get("schema_version") == MARKS_SCHEMA:
        for mark in value.get("marks", []) if isinstance(value.get("marks"), list) else []:
            if isinstance(mark, dict) and mark.get("author") == "operator" and type(mark.get("source_seconds")) in (int, float) \
                    and math.isfinite(mark["source_seconds"]) and abs(mark["source_seconds"] - anchor_time) <= lattice.p / 4:
                operator = True
    matched = None
    candidates = value.get("first_phrase_candidates")
    if isinstance(candidates, list):
        for row in candidates:
            if isinstance(row, dict) and type(row.get("candidate_source_seconds")) in (int, float) \
                    and math.isfinite(row["candidate_source_seconds"]) \
                    and abs(row["candidate_source_seconds"] - anchor_time) <= lattice.p / 4:
                matched = {"candidate_source_seconds": row["candidate_source_seconds"],
                           "candidate_status": row.get("status"),
                           "lattice_minus_candidate_seconds": anchor_time - row["candidate_source_seconds"]}
                break
    return {"evidence_sha256": evidence.sha256, "evidence_path": str(evidence.path),
            "evidence_analyzed_input_sha256": analyzed if is_sha(analyzed) else None,
            "evidence_source_sha256": source, "operator_authored": operator, "matched_evidence_candidate": matched}


def structural(units, boundary_count):
    """Per-boundary structural flags from arrangement kinds/provenance only."""
    flags = [[] for _ in range(boundary_count)]
    upstream = [[] for _ in range(boundary_count)]
    presumed_upstream = [[] for _ in range(boundary_count)]
    for index, unit in enumerate(units):
        touching = (index, index + 1)
        if unit["kind"] == "breakdown":
            for b in touching:
                flags[b].append("breakdown_execution_uncertain")
            for b in range(index + 1, boundary_count):
                upstream[b].append(unit["id"])
        if unit.get("section_provenance") == "presumed_repeat":
            for b in touching:
                flags[b].append("presumed_repeat_section")
            for b in range(index + 1, boundary_count):
                presumed_upstream[b].append(unit["id"])
    for b in range(boundary_count):
        if upstream[b]:
            flags[b].append("uncertain_upstream_breakdown")
        flags[b] = list(dict.fromkeys(flags[b]))
    return flags, upstream, presumed_upstream


def join_confidence(grid_label, statuses):
    levels = [GRID_ORDINAL[grid_label]] + [STRUCTURAL_ORDINAL[s] for s in statuses]
    return min(levels, key=lambda level: ORDINAL[level])


def coverage(lattice, start, end=None):
    if end is None:
        return "within_source" if lattice.within(start) else "outside_source"
    if start >= lattice.s0 and end <= lattice.end:
        return "within_source"
    if end <= lattice.s0 or start >= lattice.end:
        return "outside_source"
    return "partially_outside_source"


def project(grid, arrangement_value, clicks_per_grid_period, lattice_index=None, anchor_seconds=None,
            evidence=None, assessment=None):
    """Pure projection; inputs are parsed values (evidence/assessment are Input-like or None)."""
    reference_module = load_module("phrase_anchor_arrangement_reference", "scripts/arrangement_reference.py")
    try:
        expanded = reference_module.validate_reference(arrangement_value)
    except DomainError:
        raise
    except ValueError as exc:
        raise DomainError("arrangement_invalid:" + str(exc)[:200]) from exc
    original = grid["original_source_sha256"]
    require(original is None or expanded["source_sha256"] == original, "arrangement_source_mismatch")
    lattice = Lattice(grid, clicks_per_grid_period)
    anchor = anchor_from_args(lattice, lattice_index, anchor_seconds)
    k0 = anchor["k0"]
    anchor_time = lattice.time(k0)
    proof = evidence_summary(evidence, lattice, anchor_time, original)
    units_in = expanded["units"]
    positions = [unit["start_click_index"] for unit in units_in] + [expanded["totals"]["intended_click_count"]]
    flags, upstream, presumed = structural(units_in, len(positions))
    checker = checker_cross_reference(assessment, original)
    units = []
    for unit in units_in:
        start, end = lattice.time(k0 + unit["start_click_index"]), lattice.time(k0 + unit["end_click_index"])
        units.append({"id": unit["id"], "section_id": unit["section_id"], "kind": unit["kind"],
                      "section_unit_index": unit["section_unit_index"],
                      "start_click_index": unit["start_click_index"], "end_click_index": unit["end_click_index"],
                      "click_count": unit["click_count"],
                      "start_lattice_index": k0 + unit["start_click_index"], "end_lattice_index": k0 + unit["end_click_index"],
                      "start_source_seconds": start, "end_source_seconds": end,
                      "coverage": coverage(lattice, start, end),
                      "section_provenance": unit["section_provenance"],
                      "musical_phrase": unit["kind"] == "phrase",
                      "basis": "operator_intent_projected_on_fitted_grid_not_detection"})
    boundaries = []
    for b, click in enumerate(positions):
        k = k0 + click
        seconds = lattice.time(k)
        components = lattice.components(k)
        statuses = list(flags[b])
        if not lattice.within(seconds):
            statuses.append("outside_source")
        if not statuses:
            statuses = ["nominal"]
        row = {"id": f"boundary:{b}", "click_index": click, "lattice_index": k,
               "grid_beat_index": lattice.beat_index(k), "source_seconds": seconds,
               "coverage": coverage(lattice, seconds), "grid": components,
               "structural_status": statuses, "upstream_uncertain_breakdown_units": upstream[b],
               "upstream_presumed_repeat_units": presumed[b],
               "join_confidence": join_confidence(components["grid_label"], statuses),
               "confidence_kind": "heuristic_not_probability", "moved_to_fit_observation": False}
        if checker is not None:
            row["checker_cross_reference"] = checker["boundaries"].get(row["id"])
        boundaries.append(row)
    hypotheses = []
    for index, unit in enumerate(units_in):
        if unit["kind"] != "breakdown":
            continue
        for shift in SHIFT_HYPOTHESES_CLICKS:
            shifted = []
            for b in range(index + 1, len(positions)):
                click = positions[b] + shift
                k = k0 + click
                shifted.append({"id": f"boundary:{b}", "click_index": click, "lattice_index": k,
                                "source_seconds": lattice.time(k), "on_interpolated_half_period": lattice.interpolated(k),
                                "coverage": coverage(lattice, lattice.time(k))})
            hypotheses.append({"breakdown_unit_id": unit["id"], "shift_clicks": shift,
                               "hypothesized_breakdown_clicks": unit["click_count"] + shift,
                               "basis": ("operator_reported_possible_rush_or_skip" if unit["section_id"] == "breakdown1"
                                         else "intended_length_only_execution_unverified"),
                               "status": "hypothesis_not_adopted", "downstream_boundaries": shifted})
    counts = {}
    for row in boundaries:
        counts.setdefault("join_confidence", {}).setdefault(row["join_confidence"], 0)
        counts["join_confidence"][row["join_confidence"]] += 1
        counts.setdefault("grid_label", {}).setdefault(row["grid"]["grid_label"], 0)
        counts["grid_label"][row["grid"]["grid_label"]] += 1
        for status in row["structural_status"]:
            counts.setdefault("structural_status", {}).setdefault(status, 0)
            counts["structural_status"][status] += 1
    counts["boundary_count"] = len(boundaries)
    counts["interpolated_half_period_boundaries"] = sum(row["grid"]["on_interpolated_half_period"] for row in boundaries)
    counts["outside_source_boundaries"] = sum(row["coverage"] == "outside_source" for row in boundaries)
    status = ANCHOR_OPERATOR if proof["operator_authored"] else ANCHOR_UNCONFIRMED
    return {"lattice": lattice, "anchor": dict(anchor, anchor_lattice_seconds=anchor_time, status=status, **proof),
            "expanded": expanded, "units": units, "boundaries": boundaries, "hypotheses": hypotheses,
            "counts": counts, "checker": checker}


def checker_cross_reference(assessment, original):
    if assessment is None:
        return None
    value = assessment.value
    require(isinstance(value, dict) and value.get("tool") == "arrangement_reference", "assessment_tool_mismatch")
    require(original is None or value.get("source_sha256") == original, "assessment_source_mismatch")
    rows = {}
    for row in value.get("boundaries", []) if isinstance(value.get("boundaries"), list) else []:
        if not isinstance(row, dict) or not isinstance(row.get("expected"), dict):
            continue
        identity = row["expected"].get("id")
        if not isinstance(identity, str):
            continue
        observed = row.get("observed") if isinstance(row.get("observed"), dict) else {}
        rows[identity] = {"checker_status": row.get("status") if row.get("status") in (
                              "matched_boundary_candidate",) else "unknown_or_unmatched",
                          "checker_raw_status": row.get("status") if isinstance(row.get("status"), str) else None,
                          "checker_observed_source_seconds": observed.get("source_seconds"),
                          "basis": "cross_reference_only_checker_178bpm_reference_timing_not_used_for_confidence"}
    return {"sha256": assessment.sha256, "path": str(assessment.path),
            "analyzed_input_sha256": value.get("analyzed_input_sha256"), "boundaries": rows}


def spans_document(grid_input, grid, arrangement_input, result, clicks_per_grid_period, anchor_source):
    lattice = result["lattice"]
    expanded = result["expanded"]
    anchor = result["anchor"]
    totals = dict(expanded["totals"], unit_count=len(result["units"]), boundary_count=len(result["boundaries"]))
    document = {
        "schema_version": SCHEMA_VERSION, "tool": "phrase_anchor",
        "status": "intent_projection_not_detection",
        "claim_class": "inference_intent_projection_not_detection",
        "lattice": {"formula": "t(k) = s0 + phi + k * P / r", "grid_period_seconds": lattice.P,
                    "phase_seconds_audio_relative": lattice.phi, "audio_stream_start_seconds": lattice.s0,
                    "clicks_per_grid_period": lattice.r, "operator_click_period_seconds": lattice.p,
                    "operator_click_equivalent_bpm": 60 / lattice.p,
                    "interpolated_half_periods": "odd lattice indices when r=2 are interpolated, never observed clicks"},
        "source_extent": {"start_seconds": lattice.s0, "end_seconds": lattice.end,
                          "duration_seconds": grid["duration"], "basis": "grid_pcm_duration"},
        "arrangement_totals": totals,
        "units": result["units"], "boundaries": result["boundaries"],
        "breakdown_hypotheses": result["hypotheses"],
        "uncertainty_summary": result["counts"],
        "join_confidence_rules": {
            "window_operator_clicks": WINDOW_OPERATOR_CLICKS,
            "grid_supported": f"support_fraction >= {SUPPORTED_MIN_FRACTION} and median_abs_grid_offset_ms <= {SUPPORTED_MAX_MEDIAN_OFFSET_MS}",
            "grid_weak": f"support_fraction >= {WEAK_MIN_FRACTION}", "grid_unsupported": "otherwise or no expected beats",
            "ordinal": "supported > weak > uncertain > unsupported",
            "join_confidence": "ordinal minimum of grid label and every structural status",
            "confidence_kind": "heuristic_not_probability",
            "threshold_basis": "engineering_choice_frozen_in_PHRASES_S2_not_calibrated"},
        "provenance": {
            "grid_sha256": grid_input.sha256, "grid_path": str(grid_input.path),
            "grid_analyzed_input_sha256": grid["analyzed_input_sha256"],
            "original_source_sha256": grid["original_source_sha256"],
            "timeline_no_stretch_verified": grid["no_time_stretch_verified"],
            "grid_identity": grid["identity"], "grid_bpm": grid["bpm"],
            "grid_median_absolute_residual_ms": grid["median_absolute_residual_ms"],
            "grid_observed_event_count": grid["observed_event_count"],
            "arrangement_sha256": arrangement_input.sha256, "arrangement_path": str(arrangement_input.path),
            "anchor": {"source_label": anchor_source, "method": anchor["method"], "input_value": anchor["input_value"],
                       "k0": anchor["k0"], "anchor_lattice_seconds": anchor["anchor_lattice_seconds"],
                       "snap_residual_seconds": anchor["snap_residual_seconds"],
                       "evidence_sha256": anchor["evidence_sha256"], "evidence_path": anchor["evidence_path"],
                       "evidence_analyzed_input_sha256": anchor["evidence_analyzed_input_sha256"],
                       "evidence_source_sha256": anchor["evidence_source_sha256"],
                       "matched_evidence_candidate": anchor["matched_evidence_candidate"],
                       "status": anchor["status"], "adopted": False},
            "clicks_per_grid_period": {"value": clicks_per_grid_period, "mapping_basis": "operator_supplied_not_inferred"},
            "checker_assessment": None if result["checker"] is None else {
                "sha256": result["checker"]["sha256"], "path": result["checker"]["path"],
                "analyzed_input_sha256": result["checker"]["analyzed_input_sha256"], "role": "cross_reference_only"},
            "worker_sha256": worker_sha256(), "audio_decoded": False, "detector_rerun": False},
        "default_adoption": False,
        "limitations": LIMITATIONS,
    }
    document.update(UNKNOWNS)
    return document


# ------------------------------------------------------------- scorer ----

def marks_from_lane_json(value):
    require(value.get("schema_version") == MARKS_SCHEMA, "marks_schema_unsupported")
    require(is_sha(value.get("source_sha256")), "marks_source_sha256_required")
    marks = value.get("marks")
    require(isinstance(marks, list) and len(marks) <= 10_000, "marks_list_bound")
    accepted, excluded = [], {}
    for mark in marks:
        require(isinstance(mark, dict) and {"source_seconds", "author", "basis", "note"} <= set(mark), "mark_fields_required")
        seconds = finite(mark["source_seconds"], "mark_source_seconds", -86400., 86400.)
        if mark["author"] != "operator":
            excluded["non_operator_author"] = excluded.get("non_operator_author", 0) + 1
            continue
        accepted.append({"source_seconds": seconds, "origin": "phrase-boundaries-v1", "basis": mark["basis"]})
    return value["source_sha256"], accepted, excluded


def marks_from_annotation_store(value):
    module = load_module("phrase_anchor_annotation_v2", "scripts/annotation_v2.py")
    require(isinstance(value, dict) and is_sha(value.get("source_sha256")) and is_sha(value.get("manifest_sha256")),
            "annotation_store_invalid")
    try:
        module.validate_store(value, source_sha256=value["source_sha256"], manifest_sha256=value["manifest_sha256"],
                              source_min_seconds=-86400., source_max_seconds=86400.)
    except Exception as exc:  # AnnotationError carries a bounded code
        raise DomainError("annotation_store_invalid:" + str(exc)[:200]) from exc
    accepted, excluded = [], {}

    def skip(reason):
        excluded[reason] = excluded.get(reason, 0) + 1

    for item in value["annotations"]:
        if item["reported_by"]["actor"] != "operator":
            skip("non_operator_actor")
        elif item["basis"] not in ANNOTATION_BASES:
            skip("basis_not_operator")
        elif item["status"] == "dismissed_candidate":
            skip("dismissed_candidate")
        elif item["kind"] != ANNOTATION_KIND:
            skip("kind_not_phrase_duration")
        else:
            span = item["source_span"]
            accepted.append({"source_seconds": float(span["start_seconds"]), "origin": "annotation_v2:" + item["id"] + ":start",
                             "basis": item["basis"]})
            if span["extent_known"] and span["end_seconds"] != span["start_seconds"]:
                accepted.append({"source_seconds": float(span["end_seconds"]), "origin": "annotation_v2:" + item["id"] + ":end",
                                 "basis": item["basis"]})
    return value["source_sha256"], accepted, excluded


def validate_spans(value):
    require(isinstance(value, dict) and value.get("tool") == "phrase_anchor" and value.get("schema_version") == SCHEMA_VERSION
            and value.get("status") == "intent_projection_not_detection", "spans_document_required")
    boundaries = value.get("boundaries")
    require(isinstance(boundaries, list) and boundaries, "spans_boundaries_required")
    for row in boundaries:
        require(isinstance(row, dict) and isinstance(row.get("id"), str), "spans_boundary_invalid")
        finite(row.get("source_seconds"), "spans_boundary_seconds")
    period = finite(value.get("lattice", {}).get("operator_click_period_seconds"), "spans_click_period", 1e-4, 10.)
    provenance = value.get("provenance")
    require(isinstance(provenance, dict), "spans_provenance_required")
    return boundaries, period, provenance


def match(marks, boundaries, tolerance, evaluator):
    left = [row["source_seconds"] for row in marks]
    right = [row["source_seconds"] for row in boundaries]

    def score(a, b):
        distance = abs(a - b)
        return max(0., 1 - distance / tolerance) if distance <= tolerance + 1e-12 else None

    found = evaluator.optimal_matching(left, right, score)
    matches = []
    for i, j, _ in sorted(found):
        boundary = boundaries[j]
        matches.append({"mark_index": i, "mark_source_seconds": left[i], "mark_origin": marks[i]["origin"],
                        "boundary_id": boundary["id"], "predicted_source_seconds": right[j],
                        "signed_offset_seconds": right[j] - left[i],
                        "structural_status": boundary.get("structural_status"),
                        "join_confidence": boundary.get("join_confidence")})
    matched_marks = {row["mark_index"] for row in matches}
    matched_ids = {row["boundary_id"] for row in matches}
    hits = len(matches)
    return {"tolerance_seconds": tolerance, "hits": hits, "accepted_marks": len(marks),
            "hit_fraction_of_accepted_marks": hits / len(marks) if marks else None,
            "matches": matches,
            "mae_seconds": sum(abs(row["signed_offset_seconds"]) for row in matches) / hits if hits else None,
            "mae_denominator": hits,
            "unmatched_mark_indices": [i for i in range(len(marks)) if i not in matched_marks],
            "not_reviewed_boundary_ids": [row["id"] for row in boundaries if row["id"] not in matched_ids],
            "unmatched_predicted_boundaries_role": "not_reviewed_not_false_positive"}


def score_document(spans_input, marks_input, marks_format):
    boundaries, period, provenance = validate_spans(spans_input.value)
    value = marks_input.value
    require(isinstance(value, dict), "marks_object_required")
    if marks_format == "boundaries":
        mark_source, accepted, excluded = marks_from_lane_json(value)
    else:
        mark_source, accepted, excluded = marks_from_annotation_store(value)
    accepted.sort(key=lambda row: (row["source_seconds"], row["origin"]))
    original = provenance.get("original_source_sha256")
    analyzed = provenance.get("grid_analyzed_input_sha256")
    if mark_source == original and original is not None:
        binding = "original_source_sha256"
    elif mark_source == analyzed and provenance.get("timeline_no_stretch_verified") is True:
        binding = "run_derivative_no_stretch_timeline"
    else:
        binding = None
    base = {"schema_version": SCHEMA_VERSION, "tool": "phrase_anchor_score",
            "spans_sha256": spans_input.sha256, "spans_path": str(spans_input.path),
            "marks_sha256": marks_input.sha256, "marks_path": str(marks_input.path), "marks_format": marks_format,
            "marks_source_sha256": mark_source, "source_binding": binding,
            "accepted_mark_count": len(accepted), "required": MIN_OPERATOR_MARKS,
            "excluded_mark_counts": excluded,
            "accepted_mark_rule": ("phrase-boundaries-v1 author=operator" if marks_format == "boundaries" else
                                   "annotation v2: reported_by.actor=operator, basis in operator_assertion/operator_context, "
                                   "status!=dismissed_candidate, kind=phrase_duration; span start, plus end when extent_known"),
            "detector_hypotheses_counted": False,
            "precision": None, "precision_reason": "no_fully_reviewed_interval_supplied_sparse_coverage",
            "worker_sha256": worker_sha256(), "default_adoption": False,
            "missed_or_extra_notes": "not_assessed_no_approved_reference", "performance_issue_confirmed": False,
            "listening_acceptance": "not_performed"}
    if binding is None:
        return dict(base, result=None, reason="source_binding_mismatch",
                    real_take_phrase_correctness="unknown_until_operator_marks_boundaries")
    if len(accepted) < MIN_OPERATOR_MARKS:
        return dict(base, result=None, reason="insufficient_operator_boundaries",
                    real_take_phrase_correctness="unknown_until_operator_marks_boundaries")
    evaluator = load_module("phrase_anchor_phrase_evaluate", "scripts/phrase_evaluate.py")
    first, last = boundaries[0]["source_seconds"], boundaries[-1]["source_seconds"]
    outside = [i for i, row in enumerate(accepted) if row["source_seconds"] < first - period or row["source_seconds"] > last + period]
    seconds = match(accepted, boundaries, SCORE_TOLERANCE_SECONDS, evaluator)
    clicks = match(accepted, boundaries, period, evaluator)
    diagnostics = []
    for hypothesis in spans_input.value.get("breakdown_hypotheses", []):
        shifted = {row["id"]: row["source_seconds"] for row in hypothesis.get("downstream_boundaries", [])}
        rows = [dict(row, source_seconds=shifted.get(row["id"], row["source_seconds"])) for row in boundaries]
        result = match(accepted, rows, SCORE_TOLERANCE_SECONDS, evaluator)
        diagnostics.append({"breakdown_unit_id": hypothesis.get("breakdown_unit_id"),
                            "shift_clicks": hypothesis.get("shift_clicks"),
                            "hits_at_100ms": result["hits"], "accepted_marks": result["accepted_marks"],
                            "selected": False, "role": "post_hoc_diagnostic_never_selected"})
    return dict(base, reason=None,
                result={"hits_at_100ms": seconds, "hits_at_one_click": clicks,
                        "marks_outside_predicted_extent": outside,
                        "predicted_extent_seconds": [first, last],
                        "post_hoc_breakdown_hypothesis_diagnostics": diagnostics,
                        "matching": "one_to_one_optimal_matching_max_cardinality_then_min_offset"},
                real_take_phrase_correctness="operator_mark_agreement_measured_sparse_coverage_not_musical_correctness")


# ---------------------------------------------------------------- CLI ----

def run_spans(args):
    grid_input = Input(args.clicks)
    arrangement_input = Input(args.arrangement)
    evidence = Input(args.anchor_evidence) if args.anchor_evidence else None
    assessment = Input(args.assessment) if args.assessment else None
    require(isinstance(args.anchor_source, str) and 0 < len(args.anchor_source) <= 256, "anchor_source_label_required")
    out = output_path(args.output)
    grid = parse_grid(grid_input.value)
    result = project(grid, arrangement_input.value, args.clicks_per_grid_period,
                     lattice_index=args.anchor_lattice_index, anchor_seconds=args.anchor_seconds,
                     evidence=evidence, assessment=assessment)
    document = spans_document(grid_input, grid, arrangement_input, result, args.clicks_per_grid_period, args.anchor_source)
    recheck([item for item in (grid_input, arrangement_input, evidence, assessment) if item is not None])
    digest = write_new(out, document)
    return {"status": "written", "path": str(out), "sha256": digest,
            "boundary_count": len(document["boundaries"]), "unit_count": len(document["units"]),
            "anchor_k0": document["provenance"]["anchor"]["k0"],
            "join_confidence_counts": document["uncertainty_summary"]["join_confidence"],
            "real_take_phrase_correctness": document["real_take_phrase_correctness"]}


def run_score(args):
    spans_input = Input(args.spans)
    marks_input = Input(args.boundaries or args.annotation_store)
    out = output_path(args.output)
    document = score_document(spans_input, marks_input, "boundaries" if args.boundaries else "annotation_store")
    recheck([spans_input, marks_input])
    digest = write_new(out, document)
    return {"status": "written", "path": str(out), "sha256": digest, "result_null": document["result"] is None,
            "reason": document["reason"], "accepted_mark_count": document["accepted_mark_count"]}


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    spans = sub.add_parser("spans", help="Project the arrangement onto the fitted grid from one anchor")
    spans.add_argument("--clicks", required=True)
    spans.add_argument("--arrangement", required=True)
    spans.add_argument("--clicks-per-grid-period", required=True, type=int, choices=(1, 2))
    group = spans.add_mutually_exclusive_group(required=True)
    group.add_argument("--anchor-lattice-index", type=int)
    group.add_argument("--anchor-seconds", type=float)
    spans.add_argument("--anchor-source", required=True)
    spans.add_argument("--anchor-evidence")
    spans.add_argument("--assessment")
    spans.add_argument("--output", required=True)
    score = sub.add_parser("score", help="Score the primary projection against >=10 operator boundary marks")
    score.add_argument("--spans", required=True)
    marks = score.add_mutually_exclusive_group(required=True)
    marks.add_argument("--boundaries")
    marks.add_argument("--annotation-store")
    score.add_argument("--output", required=True)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = run_spans(args) if args.command == "spans" else run_score(args)
    except DomainError as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)[:500]}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
