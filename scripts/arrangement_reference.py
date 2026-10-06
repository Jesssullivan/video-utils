#!/usr/bin/env python3
"""Compare supplied arrangement intent with independent, source-timed boundaries."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

MAX_UNITS = 128
MAX_BOUNDARIES = 2048
MAX_RESULT_BYTES = 2 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]
SETTINGS = {"expected_skip_cost": 1.2, "observed_skip_cost": .6,
            "ambiguity_cost_margin": .1, "maximum_pair_distance_reference_clicks": 2,
            "maximum_expected_units": MAX_UNITS, "maximum_observed_boundaries": MAX_BOUNDARIES,
            "canonical_end_clip_analysis_sample_seconds_max": 1 / 16000}


def finite_tree(value, maximum_nodes=250000):
    pending, nodes = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        require(nodes <= maximum_nodes and depth <= 24, "metadata node/depth bound")
        if isinstance(item, dict):
            require(all(isinstance(key, str) and len(key) <= 128 for key in item), "JSON key bound")
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is float:
            require(math.isfinite(item), "all metadata numbers must be finite")
        elif type(item) is int:
            require(item.bit_length() <= 64, "metadata integer bound")
        elif isinstance(item, str):
            require(len(item) <= 4096, "metadata string bound")
        else:
            require(item is None or type(item) is bool, "JSON metadata type required")


def require(test, message):
    if not test:
        raise ValueError(message)


def number(value, low, high, label):
    require(type(value) in (int, float), f"{label}: finite nonboolean number required")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label}: numeric overflow") from exc
    require(math.isfinite(result) and low <= result <= high, f"{label}: outside bounds")
    return result


def text(value, label, limit=512):
    require(isinstance(value, str) and 0 < len(value) <= limit, f"{label}: bounded text required")
    return value


def fingerprint(value):
    require(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value), "invalid source SHA256")
    return value


def closed(value, required, optional=()):
    require(isinstance(value, dict) and set(required) <= set(value)
            and not set(value) - (set(required) | set(optional)), "closed schema fields differ")


def validate_reference(reference, source_hash=None):
    """Expand intent only; do not extract or fabricate observed boundaries."""
    finite_tree(reference, 20000)
    ref = copy.deepcopy(reference)
    closed(ref, ("schema_version", "source_sha256", "provenance", "tempo", "anchors", "sections"))
    require(type(ref["schema_version"]) is int and ref["schema_version"] == 1, "reference schema unsupported")
    fingerprint(ref["source_sha256"])
    require(source_hash is None or ref["source_sha256"] == fingerprint(source_hash), "reference source mismatch")
    closed(ref["provenance"], ("status", "authority_reference", "assumptions"))
    require(ref["provenance"]["status"] == "operator_supplied_expected_arrangement", "expected intent provenance required")
    text(ref["provenance"]["authority_reference"], "authority reference", 4096)
    require(isinstance(ref["provenance"]["assumptions"], list) and len(ref["provenance"]["assumptions"]) <= 64,
            "assumptions bound")
    for item in ref["provenance"]["assumptions"]:
        text(item, "assumption", 2048)
    closed(ref["tempo"], ("bpm", "precision"))
    bpm = number(ref["tempo"]["bpm"], 20, 400, "reference tempo")
    require(ref["tempo"]["precision"] == "approximate", "tempo precision must remain approximate")
    closed(ref["anchors"], ("first_phrase_source_seconds", "click_start_approx_seconds"))
    anchor = ref["anchors"]["first_phrase_source_seconds"]
    require(isinstance(anchor, list) and len(anchor) == 2, "first phrase requires an interval")
    lo, hi = [number(v, -86400, 86400, "first phrase anchor") for v in anchor]
    require(0 <= hi - lo <= 10, "anchor interval reversed or oversized")
    number(ref["anchors"]["click_start_approx_seconds"], -86400, 86400, "click start")
    sections = ref["sections"]
    require(isinstance(sections, list) and 0 < len(sections) <= 64, "section bound")
    ids, units, cursor, phrases = set(), [], 0, 0
    for section in sections:
        closed(section, ("id", "label", "kind", "phrase_count", "clicks_per_phrase"),
               ("section_provenance", "assumption"))
        sid = text(section["id"], "section id", 128)
        require(sid not in ids, "section IDs must be unique")
        ids.add(sid)
        text(section["label"], "section label")
        require(section["kind"] in ("phrase", "breakdown", "rest"), "section kind unsupported")
        for key in ("section_provenance", "assumption"):
            if key in section:
                text(section[key], key, 2048)
        count, clicks = section["phrase_count"], section["clicks_per_phrase"]
        require(type(count) is int and 1 <= count <= MAX_UNITS and type(clicks) is int and 1 <= clicks <= 128,
                "section count bounds")
        require(len(units) + count <= MAX_UNITS, "expected unit bound")
        if section["kind"] == "phrase":
            phrases += count
        for index in range(count):
            units.append({"id": f"{sid}:{index + 1}", "section_id": sid, "label": section["label"],
                          "kind": section["kind"], "section_unit_index": index + 1,
                          "start_click_index": cursor, "end_click_index": cursor + clicks,
                          "click_count": clicks, "section_provenance": section.get("section_provenance", "operator_supplied"),
                          "assumption": section.get("assumption")})
            cursor += clicks
    require(cursor <= 10000, "expected click bound")
    period = 60 / bpm
    positions = [unit["start_click_index"] for unit in units] + [cursor]
    boundaries = [{"id": f"boundary:{i}", "click_index": click,
                   "source_seconds_range": [lo + click * period, hi + click * period]}
                  for i, click in enumerate(positions)]
    return {**ref, "units": units, "boundaries": boundaries, "reference_click_period_seconds": period,
            "totals": {"intended_click_count": cursor, "musical_phrase_count": phrases,
                       "breakdown_group_count": sum(s["phrase_count"] for s in sections if s["kind"] == "breakdown"),
                       "rest_click_count": sum(s["phrase_count"] * s["clicks_per_phrase"] for s in sections if s["kind"] == "rest")}}


def validate_observations(value, source_hash):
    finite_tree(value, 50000)
    observations = copy.deepcopy(value)
    closed(observations, ("schema_version", "source_sha256", "timeline", "boundaries"),
           ("analyzed_input_sha256", "pulse_candidates", "binding"))
    require(type(observations["schema_version"]) is int and observations["schema_version"] == 1,
            "observation schema unsupported")
    require(fingerprint(observations["source_sha256"]) == source_hash, "observation source mismatch")
    if "analyzed_input_sha256" in observations:
        fingerprint(observations["analyzed_input_sha256"])
    closed(observations["timeline"], ("source_start_seconds", "duration_seconds"), ("boundary_latency_status", "native_pcm"))
    start = number(observations["timeline"]["source_start_seconds"], -86400, 86400, "source origin")
    duration = number(observations["timeline"]["duration_seconds"], .000001, 300, "source duration")
    status = observations["timeline"].get("boundary_latency_status", "uncalibrated")
    require(status in ("uncalibrated", "calibrated"), "boundary latency status unsupported")
    observations["timeline"]["boundary_latency_status"] = status
    native = observations["timeline"].get("native_pcm")
    if native is not None:
        closed(native, ("sample_rate", "sample_count", "channels"))
        require(type(native["sample_rate"]) is int and 8000 <= native["sample_rate"] <= 192000
                and type(native["sample_count"]) is int and 0 < native["sample_count"] <= native["sample_rate"] * 300
                and type(native["channels"]) is int and native["channels"] in (1, 2), "native PCM bounds")
        require(abs(duration - native["sample_count"] / native["sample_rate"]) < 1e-9, "native source duration differs")
    pulse = observations.get("pulse_candidates", [])
    require(isinstance(pulse, list) and len(pulse) <= 16, "pulse candidate bound")
    for candidate in pulse:
        closed(candidate, ("bpm", "period_seconds", "identity", "reference_click_unit_mapping"))
        number(candidate["bpm"], 20, 400, "candidate BPM")
        number(candidate["period_seconds"], .05, 10, "candidate period")
        require(candidate["identity"] == "unverified_periodic_candidate"
                and candidate["reference_click_unit_mapping"] is None, "pulse identity/mapping remains unverified")
    binding = observations.get("binding", {})
    closed(binding, (), ("reference", "manifest", "analysis", "phrases", "observations", "input_hashes",
                         "analyzed_input_sha256", "source_identity_scope"))
    for key in ("reference", "manifest", "analysis", "phrases", "observations"):
        if key in binding:
            closed(binding[key], ("path", "sha256"))
            text(binding[key]["path"], "binding path", 4096)
            fingerprint(binding[key]["sha256"])
    if "input_hashes" in binding:
        require(isinstance(binding["input_hashes"], dict) and len(binding["input_hashes"]) <= 8, "input hash count")
        for name, digest in binding["input_hashes"].items():
            require(isinstance(name, str) and name not in (".", "..") and "/" not in name and "\\" not in name,
                    "run-local input hash filename required")
            fingerprint(digest)
    if "analyzed_input_sha256" in binding:
        require(fingerprint(binding["analyzed_input_sha256"]) == observations.get("analyzed_input_sha256"), "analyzed binding mismatch")
    if "source_identity_scope" in binding:
        text(binding["source_identity_scope"], "identity scope", 1024)
    bounds = observations["boundaries"]
    require(isinstance(bounds, list) and len(bounds) <= MAX_BOUNDARIES, "observed boundary bound")
    ids = set()
    for item in bounds:
        closed(item, ("id", "source_seconds", "confidence", "evidence"),
               ("uncertainty_seconds", "source_seconds_original", "extent_adjustment"))
        identity = text(item["id"], "boundary id", 128)
        require(identity not in ids, "observed boundary IDs must be unique")
        ids.add(identity)
        item["source_seconds"] = number(item["source_seconds"], start, start + duration, "observed source boundary")
        item["uncertainty_seconds"] = number(item.get("uncertainty_seconds", 0), 0, 10, "boundary uncertainty")
        require(item["confidence"] in ("unvalidated", "operator_reviewed", "ambiguous"), "boundary confidence unsupported")
        text(item["evidence"], "boundary evidence", 1024)
        if "source_seconds_original" in item or "extent_adjustment" in item:
            require(item.get("extent_adjustment") == "canonical_end_clipped_at_most_one_analysis_sample"
                    and item["source_seconds"] == start + duration, "extent adjustment scope differs")
            number(item.get("source_seconds_original"), start + duration,
                   start + duration + SETTINGS["canonical_end_clip_analysis_sample_seconds_max"], "original edge")
    bounds.sort(key=lambda row: (row["source_seconds"], row["id"]))
    return observations


def align_arrangement(reference, observations):
    """Monotonic partial matching, with near-optimal alternatives retained."""
    ref = validate_reference(reference)
    obs = validate_observations(observations, ref["source_sha256"])
    expected, measured = ref["boundaries"], obs["boundaries"]
    period = ref["reference_click_period_seconds"]
    n, m = len(expected), len(measured)
    require(n * max(1, m) <= (MAX_UNITS + 1) * MAX_BOUNDARIES, "alignment cell bound")
    ends = time.monotonic() + 30
    start = obs["timeline"]["source_start_seconds"]
    end = start + obs["timeline"]["duration_seconds"]

    def cost(i, j):
        lo, hi = expected[i]["source_seconds_range"]
        item = measured[j]
        if hi < start or lo > end:
            return math.inf
        t, u = item["source_seconds"], item["uncertainty_seconds"]
        distance = max(lo - (t + u), (t - u) - hi, 0)
        return distance / period if distance <= period * 2 else math.inf

    # Deletions retain absent evidence; insertions retain extra observations.
    skip_expected, skip_observed, near_optimal = (SETTINGS[key] for key in
        ("expected_skip_cost", "observed_skip_cost", "ambiguity_cost_margin"))
    forward = [[math.inf] * (m + 1) for _ in range(n + 1)]
    backward = [[math.inf] * (m + 1) for _ in range(n + 1)]
    forward[0][0] = 0.
    for i in range(n + 1):
        require(time.monotonic() < ends, "alignment deadline exceeded")
        for j in range(m + 1):
            value = forward[i][j]
            if i < n:
                forward[i + 1][j] = min(forward[i + 1][j], value + skip_expected)
            if j < m:
                forward[i][j + 1] = min(forward[i][j + 1], value + skip_observed)
            if i < n and j < m:
                forward[i + 1][j + 1] = min(forward[i + 1][j + 1], value + cost(i, j))
    backward[n][m] = 0.
    for i in range(n, -1, -1):
        require(time.monotonic() < ends, "alignment deadline exceeded")
        for j in range(m, -1, -1):
            values = []
            if i < n:
                values.append(skip_expected + backward[i + 1][j])
            if j < m:
                values.append(skip_observed + backward[i][j + 1])
            if i < n and j < m:
                values.append(cost(i, j) + backward[i + 1][j + 1])
            if values:
                backward[i][j] = min(values)
    optimum = forward[n][m]
    rows, flags, used = [], [], set()
    for i, boundary in enumerate(expected):
        require(time.monotonic() < ends, "alignment deadline exceeded")
        alternatives = [j for j in range(m) if forward[i][j] + cost(i, j) + backward[i + 1][j + 1] <= optimum + near_optimal + 1e-9]
        unmatched_possible = any(forward[i][j] + skip_expected + backward[i + 1][j] <= optimum + near_optimal + 1e-9 for j in range(m + 1))
        lo, hi = boundary["source_seconds_range"]
        coverage = "within_source" if start <= lo <= hi <= end else (
            "right_censored" if lo > end else "left_censored" if hi < start else "partially_censored")
        chosen = measured[alternatives[0]] if len(alternatives) == 1 and not unmatched_possible else None
        if chosen and chosen["confidence"] == "ambiguous":
            chosen = None
        state = "matched_boundary_candidate" if chosen else (
            "ambiguous_boundary_alignment" if alternatives else "unobserved_boundary")
        if coverage != "within_source" and chosen is None:
            state = coverage
        delta = None if chosen is None else [chosen["source_seconds"] - chosen["uncertainty_seconds"] - hi,
                                             chosen["source_seconds"] + chosen["uncertainty_seconds"] - lo]
        if chosen:
            require(chosen["id"] not in used, "one observation cannot satisfy two expected boundaries")
            used.add(chosen["id"])
        expected_row = {**boundary, "boundary_id": boundary["id"],
                        "section_id": ref["units"][min(i, len(ref["units"]) - 1)]["section_id"],
                        "label": ref["units"][min(i, len(ref["units"]) - 1)]["label"],
                        "basis": "operator_intent_conditional_on_approximate_tempo_not_detection"}
        row = {"expected": expected_row, "status": state, "coverage": coverage,
               "observed": copy.deepcopy(chosen), "candidate_observation_ids": [measured[j]["id"] for j in alternatives[:16]],
               "candidate_observation_count": len(alternatives), "unmatched_alignment_possible": unmatched_possible,
               "deviation": None if delta is None else {"seconds_range": delta,
                    "outside_expected_window": delta[0] > 0 or delta[1] < 0},
               "confidence": "reference_conditioned_uncalibrated" if chosen else "observation_ambiguous_or_absent",
               "performance_issue_confirmed": False}
        rows.append(row)
        if coverage in ("within_source", "partially_censored"):
            mark_lo = chosen["source_seconds"] if chosen else max(start, lo)
            mark_hi = mark_lo if chosen else min(end, hi)
            flags.append({"kind": "arrangement_boundary_review_candidate", "status": "needs_review",
                          "source_time_seconds": mark_lo, "end_seconds": mark_hi,
                          "expected": expected_row, "observed": copy.deepcopy(chosen), "deviation": row["deviation"],
                          "confidence": row["confidence"], "performance_issue_confirmed": False,
                          "evidence": {"alignment_status": state, "candidate_observation_ids": row["candidate_observation_ids"],
                                       "time_basis": "observed_boundary" if chosen else "intended_boundary_interval",
                                       "warning": "Absence of novelty is not a missed phrase; repetition can hide boundaries."}})
    units = []
    for i, unit in enumerate(ref["units"]):
        a, b = rows[i]["observed"], rows[i + 1]["observed"]
        duration = b["source_seconds"] - a["source_seconds"] if a and b else None
        equivalent = duration / period if duration is not None else None
        duration_range = None if duration is None else [max(0., duration - a["uncertainty_seconds"] - b["uncertainty_seconds"]),
            min(obs["timeline"]["duration_seconds"], duration + a["uncertainty_seconds"] + b["uncertainty_seconds"])]
        units.append({"expected": {**unit, "duration_seconds": unit["click_count"] * period},
                      "observed": None if duration is None else {"start_seconds": a["source_seconds"],
                          "end_seconds": b["source_seconds"], "duration_seconds": duration,
                          "duration_seconds_range": duration_range,
                          "duration_value_basis": "nominal_boundary_centers_with_uncertainty_range",
                          "reference_equivalent_clicks_range": [value / period for value in duration_range],
                          "reference_equivalent_clicks": equivalent, "observed_click_count": None,
                          "click_count_basis": "duration_divided_by_supplied_approximate_period_not_detected_clicks"},
                      "deviation": None if equivalent is None else {"reference_equivalent_clicks_delta": equivalent - unit["click_count"],
                          "reference_equivalent_clicks_delta_range": [value / period - unit["click_count"] for value in duration_range],
                          "duration_seconds_delta_range": [value - unit["click_count"] * period for value in duration_range],
                          "duration_seconds_delta": duration - unit["click_count"] * period},
                      "status": "duration_review_candidate" if duration is not None else "boundary_support_unavailable",
                      "confidence": "conditional_duration_comparison_not_performance_grade",
                      "performance_issue_confirmed": False})
        intended = {**units[-1]["expected"], "source_start_seconds_range": rows[i]["expected"]["source_seconds_range"],
                    "source_end_seconds_range": rows[i + 1]["expected"]["source_seconds_range"]}
        mark_start = a["source_seconds"] if a else max(start, intended["source_start_seconds_range"][0])
        mark_end = b["source_seconds"] if b else min(end, intended["source_end_seconds_range"][1])
        if start <= mark_start <= mark_end <= end:
            flags.append({"kind": "arrangement_unit_review_candidate", "status": "needs_review",
                          "source_time_seconds": mark_start, "end_seconds": mark_end, "expected": intended,
                          "observed": units[-1]["observed"], "deviation": units[-1]["deviation"],
                          "confidence": units[-1]["confidence"], "performance_issue_confirmed": False,
                          "evidence": {"time_basis": "observed_boundary_pair" if duration is not None else "intended_extent_interval",
                                       "warning": "Intended extent is uncertain; duration quotient is not detected clicks or a rushed-beat grade."}})
    flags.sort(key=lambda item: (item["source_time_seconds"], item["end_seconds"], item["kind"]))
    return {"schema_version": 1, "tool": "arrangement_reference", "status": "reference_conditioned_review_candidates",
            "source_sha256": ref["source_sha256"], "analyzed_input_sha256": obs.get("analyzed_input_sha256"),
            "timeline": obs["timeline"], "binding": obs.get("binding", {}),
            "reference": {"provenance": ref["provenance"], "tempo": ref["tempo"], "anchors": ref["anchors"],
                          "totals": ref["totals"], "pulse_mapping": "supplied_click_unit_not_automatic_grid_alias"},
            "observed_boundary_count": m, "observed_click_count": None,
            "observations": measured, "boundaries": rows, "units": units, "review_candidates": flags,
            "unassigned_observation_ids": [item["id"] for item in measured if item["id"] not in used],
            "pulse_candidates": obs.get("pulse_candidates", []),
            "alignment": {"method": "bounded_monotonic_partial_matching_with_near_optimal_alternatives",
                          "cost": optimum, "ambiguity_cost_margin": near_optimal, "maximum_pair_distance_reference_clicks": 2,
                          "maximum_units": MAX_UNITS, "maximum_observed_boundaries": MAX_BOUNDARIES},
            "performance_issue_confirmed": False, "meter": None,
            "limitations": ["Intent and approximate timing windows are supplied assertions, not observed musical truth.",
                "178 BPM is an approximate reference unit; half/double candidate pulse rates remain separate.",
                "Boundary and detector delays are uncalibrated; offsets cannot establish rushed or missed notes.",
                "Repeated phrases may lack novelty. Ambiguous, absent and censored boundaries remain unknown.",
                "Reference-equivalent click duration is not a detected metronome event count; rests are intended context."]}


def observations_from_run(manifest, analysis, phrases, manifest_hash):
    """Adapt immutable cached candidate evidence, verifying lineage metadata."""
    original = fingerprint(manifest["source"]["sha256"])
    input_hash = fingerprint(analysis["source"]["sha256"])
    origin = number(manifest["timeline"]["audio_start_seconds"], -86400, 86400, "original audio origin")
    require(manifest["timeline"].get("no_time_stretch") is True, "native no-stretch mapping required")
    pcm = manifest["pcm"]
    require(type(pcm["sample_rate"]) is int and type(pcm["sample_count"]) is int
            and type(pcm["channels"]) is int and pcm["channels"] in (1, 2), "native PCM types")
    rate = number(pcm["sample_rate"], 8000, 192000, "native sample rate")
    count = number(pcm["sample_count"], 1, 192000 * 300, "native sample extent")
    duration = count / rate
    require(duration <= 300, "native duration bound")
    lineage = analysis.get("source_lineage", {})
    if input_hash != original:
        require(input_hash in [manifest.get("output_sha256", {}).get(name) for name in ("source.wav", "denoised.wav", "cleaned.wav")],
                "analysis derivative hash does not match current manifest")
        require(lineage.get("original_source_sha256") == original and lineage.get("timeline_rebased") is True
                and lineage.get("manifest_sha256") == manifest_hash, "analysis native lineage stale")
    require(abs(number(analysis["timeline"]["audio_stream_start_seconds"], -86400, 86400, "analysis origin") - origin) <= 1e-9,
            "analysis source origin differs")
    require(abs(number(analysis["analysis"]["duration_seconds"], .000001, 300.001, "analysis duration") - duration) <= 1 / 16000,
            "analysis source duration differs")
    require(phrases["source"]["sha256"] == input_hash, "phrase and analysis inputs differ")
    if input_hash != original:
        require(phrases.get("lineage", {}).get("original_source_sha256") == original
                and phrases.get("lineage", {}).get("status") == "verified_canonical_derivative", "phrase native lineage missing")
    require(abs(number(phrases["source"]["audio_stream_start_seconds"], -86400, 86400, "phrase origin") - origin) <= 1e-9,
            "phrase source origin differs")
    require(abs(number(phrases["analysis"]["duration_seconds"], .000001, 300.001, "phrase duration") - duration) <= 1 / 16000,
            "phrase source duration differs")
    segments = phrases.get("observations", {}).get("segment_candidates", [])
    require(isinstance(segments, list) and len(segments) <= 1024, "segment observation bound")
    times = {}
    for index, segment in enumerate(segments):
        require(number(segment["start_seconds"], 0, duration + 1 / 16000, "segment start")
                < number(segment["end_seconds"], 0, duration + 1 / 16000, "segment end"), "segment extent reversed or empty")
        for side in ("start", "end"):
            relative = number(segment[f"{side}_seconds"], 0, duration + 1 / 16000, "segment time")
            source = segment.get(f"source_{side}_seconds", origin + relative)
            number(source, origin, origin + duration + 1 / 16000, "segment source time")
            require(abs(source - (origin + relative)) <= 1e-9, "segment source axis differs")
            # Exact shared segment edges are one detector observation, not two.
            original_edge = source
            source = min(source, origin + duration)
            record = times.setdefault(source, {"ids": [], "original_edge": source})
            record["ids"].append(f"segment:{index}:{side}")
            record["original_edge"] = max(original_edge, record["original_edge"])
    boundaries = [{"id": f"cached_boundary:{index}", "source_seconds": timestamp,
                   "confidence": "unvalidated", "uncertainty_seconds": 0,
                   "evidence": "independent_cached_feature_segment_edges:" + ",".join(record["ids"])[:800],
                   **({"source_seconds_original": record["original_edge"],
                       "extent_adjustment": "canonical_end_clipped_at_most_one_analysis_sample"}
                      if record["original_edge"] > timestamp else {})}
                  for index, (timestamp, record) in enumerate(sorted(times.items()))]
    grid = analysis.get("click_grid")
    pulse = [] if grid is None else [{"bpm": grid.get("bpm"), "period_seconds": grid.get("period_seconds"),
                                    "identity": "unverified_periodic_candidate", "reference_click_unit_mapping": None}]
    return {"schema_version": 1, "source_sha256": original, "analyzed_input_sha256": input_hash,
            "timeline": {"source_start_seconds": origin, "duration_seconds": duration,
                         "boundary_latency_status": "uncalibrated", "native_pcm": {key: pcm[key] for key in
                            ("sample_rate", "sample_count", "channels")}},
            "boundaries": boundaries, "pulse_candidates": pulse}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON field")
        result[key] = value
    return result


def local_path(value):
    require(isinstance(value, (str, Path)) and 0 < len(str(value)) <= 4096, "local path bound")
    try:
        raw = Path(value).expanduser()
    except (RuntimeError, ValueError, OSError) as exc:
        raise ValueError("local path cannot be expanded") from exc
    require(".." not in raw.parts and "://" not in str(raw), "local path required")
    raw = Path(os.path.abspath(raw))
    for parent in [raw, *raw.parents]:
        require(not parent.is_symlink(), "symlink path rejected")
    return raw


def read_json(file, limit):
    file = local_path(file)
    require(file.is_file() and file.stat().st_size <= limit, "input file missing or oversized")
    raw = file.read_bytes()
    require(len(raw) <= limit, "input grew beyond byte limit")
    # Bound nesting before the standard parser, excluding escaped string text.
    depth, quoted, escaped = 0, False, False
    for character in raw.decode("utf-8"):
        if escaped:
            escaped = False
        elif quoted and character == "\\":
            escaped = True
        elif character == '"':
            quoted = not quoted
        elif not quoted and character in "[{":
            depth += 1
            require(depth <= 24, "JSON nesting bound")
        elif not quoted and character in "]}":
            depth -= 1
    result = json.loads(raw, object_pairs_hook=unique_object,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    finite_tree(result)
    return result, hashlib.sha256(raw).hexdigest(), file


def file_hash(file, limit):
    file = local_path(file)
    require(file.is_file() and file.stat().st_size <= limit, "native input file bound")
    before = file.stat()
    digest, size = hashlib.sha256(), 0
    with file.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            size += len(block)
            require(size <= limit, "input grew beyond byte limit")
            digest.update(block)
    after = file.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), "native input changed during hashing")
    return digest.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference")
    evidence = parser.add_mutually_exclusive_group(required=True)
    evidence.add_argument("--run-dir")
    evidence.add_argument("--observations")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    staging = None
    try:
        producer_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        reference, reference_hash, reference_path = read_json(args.reference, 64 * 1024)
        inputs = {str(reference_path): reference_hash}
        input_limits = {str(reference_path): 64 * 1024}
        selector = str(reference_path.relative_to(ROOT)) if reference_path.is_relative_to(ROOT) else str(reference_path)
        binding = {"reference": {"path": selector, "sha256": reference_hash},
                   "source_identity_scope": "current cached metadata hashes verified; raw media not rehashed or decoded"}
        if args.run_dir:
            run = local_path(args.run_dir)
            payloads = {}
            for name, limit in (("manifest", 1024 * 1024), ("analysis", 16 * 1024 * 1024), ("phrases", 4 * 1024 * 1024)):
                payload, digest, file = read_json(run / f"{name}.json", limit)
                payloads[name] = payload
                inputs[str(file)] = digest
                input_limits[str(file)] = limit
                binding[name] = {"path": str(file), "sha256": digest}
            observations = observations_from_run(payloads["manifest"], payloads["analysis"], payloads["phrases"],
                                                  binding["manifest"]["sha256"])
            binding["input_hashes"] = {Path(name).name: digest for name, digest in inputs.items() if Path(name).parent == run}
            matched = [name for name in ("denoised.wav", "source.wav", "cleaned.wav")
                       if payloads["manifest"].get("output_sha256", {}).get(name) == observations["analyzed_input_sha256"]]
            require(bool(matched), "run adapter requires a canonical run-local PCM input")
            native_path = local_path(run / matched[0])
            require(file_hash(native_path, 1024 ** 3) == observations["analyzed_input_sha256"], "live analyzed PCM hash differs")
            inputs[str(native_path)] = observations["analyzed_input_sha256"]
            input_limits[str(native_path)] = 1024 ** 3
            binding["input_hashes"][matched[0]] = observations["analyzed_input_sha256"]
            binding["source_identity_scope"] = "cached metadata and canonical input PCM hashes verified; original encoded media not rehashed or decoded"
        else:
            observations, digest, file = read_json(args.observations, 2 * 1024 * 1024)
            inputs[str(file)] = digest
            input_limits[str(file)] = 2 * 1024 * 1024
            binding["observations"] = {"path": str(file), "sha256": digest}
        observations["binding"] = binding
        if observations.get("analyzed_input_sha256"):
            binding["analyzed_input_sha256"] = observations["analyzed_input_sha256"]
        result = align_arrangement(reference, observations)
        result["reference"].update(path=selector, sha256=reference_hash)
        destination = local_path(args.output)
        require(not destination.exists(), "output must be a fresh directory")
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".arrangement-", dir=destination.parent))
        artifacts = {"assessment.json": result, "review-candidates.json": {
            "schema_version": 1, "source_sha256": result["source_sha256"],
            "analyzed_input_sha256": result["analyzed_input_sha256"], "timeline": result["timeline"],
            "binding": binding, "reference": result["reference"], "review_candidates": result["review_candidates"]}}
        hashes = {}
        for name, payload in artifacts.items():
            raw = (json.dumps(payload, indent=2, allow_nan=False) + "\n").encode()
            require(len(raw) <= MAX_RESULT_BYTES, "arrangement artifact byte bound")
            (staging / name).write_bytes(raw)
            hashes[name] = hashlib.sha256(raw).hexdigest()
        for name, digest in inputs.items():
            require(file_hash(Path(name), input_limits[name]) == digest, "input changed before publication")
        require(hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == producer_hash, "producer changed before publication")
        receipt = {"schema_version": 1, "tool": "arrangement_reference", "status": result["status"],
                   "source_sha256": result["source_sha256"], "analyzed_input_sha256": result["analyzed_input_sha256"],
                   "input_sha256": inputs, "output_sha256": hashes,
                   "producer_sha256": producer_hash,
                   "settings": SETTINGS, "settings_sha256": hashlib.sha256(json.dumps(SETTINGS, sort_keys=True).encode()).hexdigest(),
                   "property_testing": "deterministic randomized properties; no Hypothesis installed",
                   "canonical_pcm_read_for_hash": bool(args.run_dir), "audio_decoded": False,
                   "dsp_performed": False, "performance_issue_confirmed": False}
        raw = (json.dumps(receipt, indent=2, allow_nan=False) + "\n").encode()
        require(len(raw) <= 64 * 1024, "receipt byte bound")
        (staging / "receipt.json").write_bytes(raw)
        require(not destination.exists(), "output collision before publication")
        staging.rename(destination)
        staging = None
        print(json.dumps({"status": result["status"], "output": str(destination), "output_sha256": hashes,
                          "source_sha256": result["source_sha256"], "analyzed_input_sha256": result["analyzed_input_sha256"],
                          "intended_click_count": result["reference"]["totals"]["intended_click_count"],
                          "observed_click_count": None, "review_candidate_count": len(result["review_candidates"])}))
        return 0
    except (ValueError, OSError, KeyError, TypeError, OverflowError, RecursionError) as exc:
        message = str(exc)[:1000]
        print(message, file=sys.stderr)
        print(json.dumps({"status": "error", "error": message, "dsp_performed": False}))
        return 2
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
