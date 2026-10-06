#!/usr/bin/env python3
"""Write non-executed FCPXML 1.10 or Resolve marker previews from a verified uniform plan; abstain otherwise.

The exporter reuses ``editor_marker_plan`` unchanged, verifies that the editor
fixture grid matches a complete, uniform, hash-bound source PTS table, and only
then stages ``review.fcpxmld/Info.fcpxml`` or ``resolve-operations.json`` plus an
exact-time sidecar. Anything unverified (variable or unknown cadence, period or
origin mismatch, unsupported timecode rate, missing media reference) produces a
typed ``calibration_required`` result on stdout and creates no file or directory.
Nothing here launches, connects to or imports into an editor. Contract:
docs/spec/EDITOR_MARKER_EXPORT.md and docs/spec/sprints/EDITOR_EXPORT_S2.md.
"""
from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import editor_marker_plan as planner
import timecode

markers = planner.markers
require = planner.require
ratio = planner.ratio

FORMATS = ("fcpxml", "resolve_ops")
TARGET_FOR_FORMAT = {"fcpxml": "final_cut_pro", "resolve_ops": "davinci_resolve"}
FCPXML_NAME = "review.fcpxmld/Info.fcpxml"
RESOLVE_NAME = "resolve-operations.json"
SIDECAR_NAME = "editor-marker-export.sidecar.json"
MAX_FCPXML_BYTES = 4 * 1024 * 1024
MAX_PAYLOAD_JSON_BYTES = 16 * 1024 * 1024
MAX_SIDECAR_BYTES = 16 * 1024 * 1024
MAX_SUMMARY_BYTES = 64 * 1024
MAX_ERROR_BYTES = 16 * 1024
MAX_DTD_BYTES = 1024 * 1024
MAX_TEXT = 256
MAX_URL = 4096
MAX_DIMENSION = 32768
MAX_HISTOGRAM_KEYS = 256
DTD_TIMEOUT_SECONDS = 30
XMLLINT = "/usr/bin/xmllint"
DISPLAY_TIMECODE_BASIS = "asset_local_from_asset_start_plus_profile_origin_unverified_against_host"
FRAME_ID_BASIS = "fixture_grid_frame_id_origin_unverified_against_host"
# Closed, ordered abstention vocabulary. The first eleven are frozen by the S2
# contract; asset_mapping_unknown, clip_bounds_off_grid and clip_outside_asset_extent
# are additive conservative checks documented in docs/spec/EDITOR_MARKER_EXPORT.md.
REASONS = ("plan_selection_required", "plan_calibration_required", "cadence_unknown_no_pts",
           "cadence_variable", "grid_pts_period_mismatch", "grid_origin_misaligned",
           "asset_mapping_unknown", "clip_bounds_off_grid", "clip_outside_asset_extent",
           "rate_unsupported_for_timecode", "drop_frame_rate_unsupported", "media_reference_missing",
           "negative_native_time_unverified")
NATIVE_STATUSES = ("written_unverified", "calibration_required", "nothing_exportable", "selection_required")
EXPORT_FIELDS = {"schema_version", "format", "plan_profile", "plan_profile_sha256", "timecode", "fcpxml"}
TIMECODE_FIELDS = {"drop_frame", "origin_label"}
FCPXML_FIELDS = {"event_name", "asset_name", "media_src_url", "width", "height"}
# RFC 3986 characters permitted in an already percent-encoded absolute file URL path.
FILE_URL = re.compile(r"file:///(?:[A-Za-z0-9\-._~!$&'()*+,;=:@/]|%[0-9A-Fa-f]{2})*")
XML_INVALID = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿\ud800-\udfff]")
FIXED_UNKNOWN_FIELDS = {"application_import": "not_performed", "native_contract_status": "native_contract_unverified",
                        "executable": False, "api_contract": "unverified", "final_cut_version": None,
                        "resolve_version": None, "host_frame_id": None,
                        "display_timecode_basis": DISPLAY_TIMECODE_BASIS,
                        "listening_acceptance": "not_established", "musical_verdict": "not_established"}
LIMITATIONS = [
    "No editor was launched, connected, written or imported; application_import is not_performed.",
    "Fixture frame IDs and FCPXML times follow a uniform grid verified only against the source PTS table, "
    "not against any host editor's interpretation; host_frame_id stays null.",
    "Valid XML or a passing supplied DTD is not a successful Final Cut Pro import; Resolve operations are "
    "a non-executable preview of an unverified API contract.",
    "Display timecode labels are sidecar identifiers only and never change media time or samples.",
    "Markers remain needs_review hypotheses: no note-correctness, missed/extra-note or mistake verdict, "
    "and no listening acceptance.",
]


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def fcp_time(value):
    """Reduced rational seconds as FCPXML text: ``Ns`` or ``n/ds``."""
    value = Fraction(value)
    return f"{value.numerator}s" if value.denominator == 1 else f"{value.numerator}/{value.denominator}s"


def bounded_text(value, label, maximum=MAX_TEXT):
    require(isinstance(value, str) and 1 <= len(value) <= maximum, f"{label} must be text of 1-{maximum} characters")
    require(not XML_INVALID.search(value), f"{label} contains an XML-unrepresentable character")
    return value


def xml_attr(value):
    """Escape attribute text so ElementTree round-trips it unchanged, including newlines and tabs."""
    require(isinstance(value, str) and not XML_INVALID.search(value), "XML-unrepresentable character in attribute")
    return ('"' + value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
            .replace("\t", "&#9;").replace("\n", "&#10;").replace("\r", "&#13;") + '"')


def file_url_from_path(path):
    """Percent-encode an absolute local path as a file URL (helper; never derived from manifests)."""
    from urllib.parse import quote
    require(isinstance(path, str) and path.startswith("/"), "Absolute POSIX path required")
    return "file://" + quote(path, safe="/-._~!$&'()*+,;=:@")


def validate_export_profile(profile, export_format):
    """Closed export-profile schema; unknown keys, bool versions and loose text reject."""
    require(export_format in FORMATS, "Unsupported export format")
    require(isinstance(profile, dict) and set(profile) <= EXPORT_FIELDS, "Unknown export profile fields")
    require(type(profile.get("schema_version")) is int and profile["schema_version"] == 1,
            "Export profile schema_version must be integer 1")
    require(profile.get("format") == "editor_marker_export_profile", "Export profile format must be editor_marker_export_profile")
    planner.relative_json_name(profile.get("plan_profile"))
    require(isinstance(profile.get("plan_profile_sha256"), str) and planner.HASH.fullmatch(profile["plan_profile_sha256"]),
            "Export profile requires plan_profile_sha256")
    clock = profile.get("timecode")
    require(isinstance(clock, dict) and set(clock) == TIMECODE_FIELDS, "Timecode block requires exactly drop_frame, origin_label")
    require(type(clock["drop_frame"]) is bool, "timecode.drop_frame must be boolean")
    require(isinstance(clock["origin_label"], str) and 1 <= len(clock["origin_label"]) <= 16,
            "timecode.origin_label must be short text")
    if export_format == "fcpxml":
        block = profile.get("fcpxml")
        require(isinstance(block, dict) and set(block) == FCPXML_FIELDS,
                "fcpxml block requires exactly event_name, asset_name, media_src_url, width, height")
        bounded_text(block["event_name"], "fcpxml.event_name")
        bounded_text(block["asset_name"], "fcpxml.asset_name")
        url = block["media_src_url"]
        if url is not None:
            require(isinstance(url, str) and len(url) <= MAX_URL and FILE_URL.fullmatch(url),
                    "media_src_url must be an explicit absolute percent-encoded file:/// URL")
        for key in ("width", "height"):
            value = block[key]
            require(value is None or (type(value) is int and 1 <= value <= MAX_DIMENSION),
                    f"fcpxml.{key} must be null or an integer 1-{MAX_DIMENSION}")
    else:
        require("fcpxml" not in profile, "fcpxml block is refused for resolve_ops")
    return profile


def measure_cadence(pts):
    """Measured cadence of the complete PTS table (ticks), never from average/nominal metadata."""
    if pts is None:
        return {"cadence": "unknown", "evidence": None}
    tick = planner.rational(pts.get("time_base"), "PTS time base")
    frames = pts["frames"]
    starts = [row["best_effort_timestamp"] for row in frames]
    durations = [row["duration"] for row in frames]
    steps = Counter(b - a for a, b in zip(starts, starts[1:]))
    lengths = Counter(durations)
    uniform = len(lengths) == 1 and all(step == durations[0] for step in steps)

    def histogram(counter):
        keys = sorted(counter)
        return {"ticks": {str(k): counter[k] for k in keys[:MAX_HISTOGRAM_KEYS]},
                "distinct_values": len(keys), "truncated": len(keys) > MAX_HISTOGRAM_KEYS}

    evidence = {"class": "measured_source_pts_table", "frame_count": len(frames), "time_base": ratio(tick),
                "first_tick": starts[0], "last_tick": starts[-1], "last_duration_ticks": durations[-1],
                "coverage_start_seconds": ratio(starts[0] * tick),
                "coverage_end_seconds": ratio((starts[-1] + durations[-1]) * tick),
                "extent_seconds": ratio((starts[-1] + durations[-1] - starts[0]) * tick),
                "step_histogram": histogram(steps), "duration_histogram": histogram(lengths),
                "uniform_period_seconds": ratio(durations[0] * tick) if uniform else None}
    return {"cadence": "uniform" if uniform else "variable", "evidence": evidence}


def metadata_hint(generic, frame_rate_metadata=None):
    """Average/nominal metadata as a labelled inference; never used for decisions."""
    rates = frame_rate_metadata if isinstance(frame_rate_metadata, dict) else (
        generic.get("frame_rate") if isinstance(generic.get("frame_rate"), dict) else {})
    average, nominal = rates.get("average_rational"), rates.get("nominal_rational")
    if average is None and nominal is None:
        return None
    try:
        differs = Fraction(str(average)) != Fraction(str(nominal))
    except (ValueError, ZeroDivisionError):
        differs = None
    return {"class": "metadata_inference", "average_rational": average, "nominal_rational": nominal,
            "average_differs_from_nominal": differs,
            "inference": ("average_differs_from_nominal_suggests_variable_cadence" if differs else
                          "metadata_alone_cannot_establish_cadence"),
            "used_for_decisions": False}


def lexeme(value):
    if isinstance(value, planner.SourceDecimal):
        return value.encoded
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, str)):
        return str(value)
    return repr(value)


def quantization(text):
    if text is None:
        return None
    value = Fraction(text)
    return {"exact_seconds": ratio(value), "display_ms": round(float(value) * 1000, 6)}


def origins_of(profile):
    fields = ("source_origin", "asset_origin", "clip_in", "clip_out", "parent_offset")
    return {key: planner.rational(profile[key], key) for key in fields if profile.get(key) is not None}


def verify(plan, plan_profile, export_profile, pts, export_format):
    """Return (reasons, context) for the uniform-grid gate; reasons are ordered by REASONS."""
    reasons = set()
    measured = measure_cadence(pts)
    cadence = measured["cadence"]
    if plan["plan_status"] == "selection_required":
        reasons.add("plan_selection_required")
    if plan["plan_status"] == "calibration_required":
        reasons.add("plan_calibration_required")
    if pts is None:
        reasons.add("cadence_unknown_no_pts")
    elif cadence == "variable":
        reasons.add("cadence_variable")
    origins = origins_of(plan_profile)
    mapping_known = {"source_origin", "asset_origin", "clip_in", "clip_out"} <= set(origins)
    grid = plan_profile.get("fixture_grid")
    context = {"cadence": cadence, "cadence_evidence": measured["evidence"], "origins": origins,
               "period": None, "grid_origin": None, "frame_id_origin": None, "clock": None,
               "origin_frame": None, "asset_start": None, "asset_end": None, "rate": None}
    if grid is not None:
        context["period"] = period = planner.rational(grid["frame_duration"], "frame duration")
        context["grid_origin"] = grid_origin = planner.rational(grid["origin"], "grid origin")
        context["frame_id_origin"] = grid["frame_id_origin"]
        if not mapping_known:
            reasons.add("asset_mapping_unknown")
        if pts is not None and mapping_known:
            tick = planner.rational(pts["time_base"], "PTS time base")
            to_local = lambda source: origins["asset_origin"] + source - origins["source_origin"]
            first, last = pts["frames"][0], pts["frames"][-1]
            context["asset_start"] = to_local(first["best_effort_timestamp"] * tick)
            context["asset_end"] = to_local((last["best_effort_timestamp"] + last["duration"]) * tick)
        if cadence == "uniform":
            if Fraction(measured["evidence"]["uniform_period_seconds"]) != period:
                reasons.add("grid_pts_period_mismatch")
            elif mapping_known:
                tick = planner.rational(pts["time_base"], "PTS time base")
                to_local = lambda source: origins["asset_origin"] + source - origins["source_origin"]
                aligned = all(((to_local(row["best_effort_timestamp"] * tick) - grid_origin) / period).denominator == 1
                              for row in pts["frames"])
                if not aligned:
                    reasons.add("grid_origin_misaligned")
                elif export_format == "fcpxml":
                    if any(((origins[key] - grid_origin) / period).denominator != 1 for key in ("clip_in", "clip_out")):
                        reasons.add("clip_bounds_off_grid")
                    if not context["asset_start"] <= origins["clip_in"] < origins["clip_out"] <= context["asset_end"]:
                        reasons.add("clip_outside_asset_extent")
        try:
            context["rate"] = rate = timecode.parse_rate(1 / period)
        except timecode.TimecodeError:
            reasons.add("rate_unsupported_for_timecode")
        else:
            drop = export_profile["timecode"]["drop_frame"]
            if drop and not timecode.drop_frame_allowed(rate):
                reasons.add("drop_frame_rate_unsupported")
            else:
                clock = timecode.Clock(rate, drop)
                try:
                    context["origin_frame"] = clock.frame(export_profile["timecode"]["origin_label"])
                except timecode.TimecodeError as exc:
                    raise ValueError(f"Invalid timecode.origin_label: {exc}") from exc
                context["clock"] = clock
    if export_format == "fcpxml":
        if export_profile["fcpxml"]["media_src_url"] is None:
            reasons.add("media_reference_missing")
        native = [Fraction(action["fixture_start_seconds"]) for action in plan["actions"]]
        native += [origins[key] for key in ("clip_in", "parent_offset") if key in origins]
        if context["asset_start"] is not None:
            native.append(context["asset_start"])
        if any(value < 0 for value in native):
            reasons.add("negative_native_time_unverified")
    elif any(action["fixture_frame_id"] < 0 for action in plan["actions"]):
        reasons.add("negative_native_time_unverified")
    return [reason for reason in REASONS if reason in reasons], context


def display_label(context, frame_id):
    """Sidecar-only display timecode for a fixture frame ID, or (None, reason)."""
    clock, period = context["clock"], context["period"]
    if clock is None or context["asset_start"] is None or frame_id is None:
        return None, "display_clock_unavailable"
    position = context["grid_origin"] + (frame_id - context["frame_id_origin"]) * period
    offset = (position - context["asset_start"]) / period
    if offset.denominator != 1:
        return None, "display_position_off_grid"
    frame = offset.numerator + context["origin_frame"]
    if not 0 <= frame < clock.per_day:
        return None, "display_frame_out_of_24h_range"
    return clock.label(frame), None


def sidecar_rows(plan, generic, context, colliding, status):
    actions_by_id = {}
    for action in plan["actions"]:
        actions_by_id.setdefault(action["marker_id"], []).append(action)
    items = generic.get("markers", [])
    rows = []
    for row in plan["markers"]:
        identity = row["marker_id"]
        item = items[row["marker_index"]]
        own = actions_by_id.get(identity, [])
        positions = row.get("fixture_positions") or {}
        collisions = [{"role": a["role"], "fixture_frame_id": a["fixture_frame_id"], "collision": a["collision"]}
                      for a in own if a["collision"] != "none"]
        if identity in colliding:
            exclusion = ("preserve_existing_marker" if any(c["collision"] == "preserve_existing_marker" for c in collisions)
                         else "planned_same_frame_conflict")
        elif not own:
            exclusion = row["disposition"]
        elif status != "written_unverified":
            exclusion = f"native_export_{status}"
        else:
            exclusion = None
        if status == "written_unverified":
            start_label, start_reason = display_label(context, positions.get("start_frame"))
            end_label, end_reason = display_label(context, positions.get("end_frame"))
        else:  # no display labels on an unverified grid
            start_label = end_label = None
            start_reason, end_reason = "native_export_not_written", None
        start_value = item.get("source_time_seconds")
        end_value = item.get("end_seconds", start_value)
        rows.append({"marker_id": identity, "marker_index": row["marker_index"], "kind": row["kind"],
                     "original_start_decimal": lexeme(start_value), "original_end_decimal": lexeme(end_value),
                     "source_start": row["source_start"], "source_end": row["source_end"],
                     "asset_local_start": row["asset_local_start"], "asset_local_end": row["asset_local_end"],
                     "parent_time": row["parent_time"], "preview_frame_index": row["preview_frame_index"],
                     "fixture_start_frame": positions.get("start_frame"), "fixture_end_frame": positions.get("end_frame"),
                     "start_quantization_error_seconds": quantization(positions.get("start_error_seconds")),
                     "end_quantization_error_seconds": quantization(positions.get("end_error_seconds")),
                     "display_timecode_start": start_label, "display_timecode_end": end_label,
                     "display_timecode_status": start_reason or end_reason or "label_unverified_against_host",
                     "collisions": collisions, "disposition": row["disposition"],
                     "exported": exclusion is None, "exclusion_reason": exclusion,
                     "native_roles": [a["role"] for a in own] if exclusion is None else [],
                     "host_frame_id": None, "status": row["status"], "confidence": row["confidence"],
                     "title": row["title"], "notes": row["notes"]})
    return rows


def note_text(action):
    return (f"{action['notes']}; marker_id={action['marker_id']}; role={action['role']}; "
            f"fixture_frame_id={action['fixture_frame_id']} (hypothetical, not a host frame)")


def render_fcpxml(plan, export_profile, context, exported):
    block = export_profile["fcpxml"]
    period, origins = context["period"], context["origins"]
    clock = context["clock"]
    format_attrs = f'id="r1" frameDuration={xml_attr(fcp_time(period))}'
    for key in ("width", "height"):
        if block[key] is not None:
            format_attrs += f' {key}="{block[key]}"'
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<!DOCTYPE fcpxml>", '<fcpxml version="1.10">',
             "    <resources>", f"        <format {format_attrs}/>",
             (f'        <asset id="r2" name={xml_attr(block["asset_name"])} start={xml_attr(fcp_time(context["asset_start"]))} '
              f'duration={xml_attr(fcp_time(context["asset_end"] - context["asset_start"]))} hasVideo="1" format="r1">'),
             f'            <media-rep kind="original-media" src={xml_attr(block["media_src_url"])}/>',
             "        </asset>", "    </resources>", "    <library>",
             f'        <event name={xml_attr(block["event_name"])}>',
             (f'            <asset-clip ref="r2" name={xml_attr(block["asset_name"])} '
              f'offset={xml_attr(fcp_time(origins.get("parent_offset", Fraction(0))))} '
              f'start={xml_attr(fcp_time(origins["clip_in"]))} '
              f'duration={xml_attr(fcp_time(origins["clip_out"] - origins["clip_in"]))} format="r1" '
              f'tcFormat="{"DF" if clock.drop_frame else "NDF"}">')]
    for action in sorted(exported, key=lambda a: (Fraction(a["fixture_start_seconds"]), a["fixture_frame_id"])):
        require(Fraction(action["fixture_duration_seconds"]) == period, "Marker duration differs from frame duration")
        lines.append(f'                <marker start={xml_attr(fcp_time(Fraction(action["fixture_start_seconds"])))} '
                     f'duration={xml_attr(fcp_time(period))} value={xml_attr(action["title"])} '
                     f'note={xml_attr(note_text(action))}/>')
    lines += ["            </asset-clip>", "        </event>", "    </library>", "</fcpxml>", ""]
    data = "\n".join(lines).encode("utf-8")
    require(len(data) <= MAX_FCPXML_BYTES, "Info.fcpxml exceeds 4 MiB bound")
    return data


def render_resolve(plan, context, exported):
    operations = []
    for action in sorted(exported, key=lambda a: (a["fixture_frame_id"], a["marker_id"])):
        frame_id, duration = action["fixture_frame_id"], action["fixture_duration_frames"]
        require(type(frame_id) is int and type(duration) is int and duration >= 1, "Resolve frame fields must be ints")
        operations.append({"receiver": "explicit_original_MediaPoolItem", "role": action["role"],
                           "frameId": frame_id, "duration_frames": duration, "name": action["title"],
                           "note": note_text(action), "custom_data": action["marker_id"], "color": None,
                           "marker_id": action["marker_id"], "executable": False, "api_contract": "unverified",
                           "host_frame_id": None})
    document = {"schema_version": 1, "format": "resolve_marker_operations_preview", "source_sha256": plan["source_sha256"],
                "executable": False, "api_contract": "unverified", "application_import": "not_performed",
                "resolve_version": None, "native_contract_status": "native_contract_unverified",
                "receiver": "explicit_original_MediaPoolItem", "frame_id_basis": FRAME_ID_BASIS,
                "frame_duration": ratio(context["period"]), "operations": operations}
    data = (json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
    require(len(data) <= MAX_PAYLOAD_JSON_BYTES, "resolve-operations.json exceeds bound")
    return data


def plan_counts(plan, rows):
    dispositions, collisions = Counter(row["disposition"] for row in plan["markers"]), Counter(
        action["collision"] for action in plan["actions"])
    return {"marker_count": plan["marker_count"], "selected_count": plan["selected_count"],
            "excluded_count": len(plan["excluded_ids"]), "action_count": len(plan["actions"]),
            "exported_marker_count": sum(row["exported"] for row in rows),
            "disposition_counts": dict(sorted(dispositions.items())), "collision_counts": dict(sorted(collisions.items()))}


def export_plan(plan, generic, plan_profile, export_profile, pts, export_format, input_hashes=None,
                entrypoint="pure_make_plan", frame_rate_metadata=None):
    """Pure gate + serialization. Returns (result, payload files); writes nothing.

    ``frame_rate_metadata`` ({average_rational, nominal_rational}) only feeds the
    metadata_cadence_hint inference when the marker document lacks frame_rate.
    """
    validate_export_profile(export_profile, export_format)
    require(plan_profile.get("target") == TARGET_FOR_FORMAT[export_format] == plan["target"],
            "Export format does not match the planner target")
    require(plan["format"] == "editor_marker_dry_run" and plan["executable"] is False
            and plan["native_contract_status"] == "native_contract_unverified", "Unexpected planner output")
    require(generic.get("source_sha256") == plan["source_sha256"], "Generic markers differ from plan source")
    reasons, context = verify(plan, plan_profile, export_profile, pts, export_format)
    colliding = {action["marker_id"] for action in plan["actions"] if action["collision"] != "none"}
    exported = [action for action in plan["actions"] if action["marker_id"] not in colliding]
    if "plan_selection_required" in reasons:
        status = "selection_required"
    elif reasons:
        status = "calibration_required"
    elif not exported:
        status = "nothing_exportable"
    else:
        status = "written_unverified"
    rows = sidecar_rows(plan, generic, context, colliding, status)
    clock = context["clock"]
    result = {"schema_version": 1, "format": "editor_marker_export_result", "export_format": export_format,
              "entrypoint": entrypoint, "source_sha256": plan["source_sha256"], "target": plan["target"],
              "plan_status": plan["plan_status"], "native_export_status": status, "reasons": reasons,
              "cadence": context["cadence"], "cadence_evidence": context["cadence_evidence"],
              "metadata_cadence_hint": metadata_hint(generic, frame_rate_metadata), **FIXED_UNKNOWN_FIELDS,
              "dtd_validation": "not_performed", "dtd_validator": None,
              "grid": None if context["period"] is None else {
                  "frame_duration": ratio(context["period"]), "origin": ratio(context["grid_origin"]),
                  "frame_id_origin": context["frame_id_origin"],
                  "rate": None if context["rate"] is None else ratio(context["rate"]),
                  "verification": ("pts_uniform_period_and_origin_aligned" if status == "written_unverified"
                                   else "not_verified")},
              "timecode": {"drop_frame": export_profile["timecode"]["drop_frame"],
                           "tc_format": "DF" if export_profile["timecode"]["drop_frame"] else "NDF",
                           "origin_label": export_profile["timecode"]["origin_label"],
                           "origin_frame": context["origin_frame"],
                           "frames_per_day": None if clock is None else clock.per_day},
              "counts": plan_counts(plan, rows), "input_sha256": dict(sorted((input_hashes or {}).items())),
              "worker_sha256": {"editor_marker_export.py": markers.sha256(Path(__file__)),
                                "editor_marker_plan.py": markers.sha256(Path(planner.__file__)),
                                "timecode.py": markers.sha256(Path(timecode.__file__))},
              "output_dir": None, "files_written": 0, "output_sha256": {}, "output_bytes": {},
              "limitations": LIMITATIONS}
    files = {}
    if status == "written_unverified":
        if export_format == "fcpxml":
            files[FCPXML_NAME] = render_fcpxml(plan, export_profile, context, exported)
        else:
            files[RESOLVE_NAME] = render_resolve(plan, context, exported)
        result["asset"] = {"start": ratio(context["asset_start"]), "end": ratio(context["asset_end"]),
                           "clip_in": ratio(context["origins"]["clip_in"]),
                           "clip_out": ratio(context["origins"]["clip_out"]),
                           "parent_offset": ratio(context["origins"].get("parent_offset", Fraction(0)))}
    result["markers"] = rows
    return result, files


def sidecar_bytes(result):
    payload = {key: value for key, value in result.items()
               if key not in ("format", "output_dir", "files_written", "output_sha256", "output_bytes")}
    payload["format"] = "editor_marker_export_sidecar"
    payload["payload_sha256"] = dict(result["output_sha256"])
    data = (json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
    require(len(data) <= MAX_SIDECAR_BYTES, "Sidecar exceeds 16 MiB bound")
    return data


def check_dtd_path(dtd):
    path = Path(dtd)
    require(1 <= len(str(dtd)) <= planner.MAX_RUN_DIR_PATH, "DTD path exceeds bound")
    require(not path.is_symlink(), "DTD symlink rejected")
    require(path.is_file(), "DTD must be an existing regular local file")
    data = path.read_bytes()
    require(len(data) <= MAX_DTD_BYTES, "DTD exceeds 1 MiB bound")
    return path.resolve(strict=True), sha256_bytes(data)


def dtd_validate(document, dtd_path, dtd_sha256, cwd=None):
    """Validate one local document with xmllint against a supplied DTD; never fetches anything."""
    validator = {"validator_path": XMLLINT, "validator_version": None, "dtd_path": str(dtd_path),
                 "dtd_sha256": dtd_sha256, "returncode": None, "diagnostics_tail": "",
                 "scope": "supplied_dtd_only; a synthetic or unverified DTD does not establish FCPXML 1.10 conformance"}
    if not (os.path.isfile(XMLLINT) and os.access(XMLLINT, os.X_OK)):
        validator["diagnostics_tail"] = "validator_missing"
        return "unavailable", validator
    try:
        version = subprocess.run([XMLLINT, "--version"], capture_output=True, timeout=DTD_TIMEOUT_SECONDS,
                                 stdin=subprocess.DEVNULL)
        validator["validator_version"] = (version.stderr or version.stdout).decode("utf-8", "replace").splitlines()[0][:200]
        run = subprocess.run([XMLLINT, "--noout", "--nonet", "--dtdvalid", str(dtd_path), str(document)],
                             capture_output=True, timeout=DTD_TIMEOUT_SECONDS, cwd=cwd, stdin=subprocess.DEVNULL)
    except (OSError, IndexError, subprocess.TimeoutExpired) as exc:
        validator["diagnostics_tail"] = type(exc).__name__
        return "unavailable", validator
    validator["returncode"] = run.returncode
    validator["diagnostics_tail"] = (run.stdout + run.stderr)[-2000:].decode("utf-8", "replace")
    return ("passed" if run.returncode == 0 else "failed"), validator


def write_exclusive(output_dir, result, files, dtd=None, before_publish=None):
    """Stage payload + sidecar in a sibling directory, then rename it to an absent output path."""
    output_dir = Path(output_dir)
    require(1 <= len(str(output_dir)) <= planner.MAX_RUN_DIR_PATH, "Output path exceeds bound")
    require(not os.path.lexists(output_dir), "Output directory already exists; refusing to overwrite")
    parent = output_dir.parent.resolve(strict=True)
    require(parent.is_dir(), "Output parent must be an existing directory")
    target = parent / output_dir.name
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=parent))
    try:
        for name, data in files.items():
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(data)
        if dtd is not None and FCPXML_NAME in files:
            result["dtd_validation"], result["dtd_validator"] = dtd_validate(FCPXML_NAME, dtd[0], dtd[1], cwd=staging)
        result["output_sha256"] = {name: sha256_bytes(data) for name, data in sorted(files.items())}
        sidecar = sidecar_bytes(result)
        with (staging / SIDECAR_NAME).open("xb") as stream:
            stream.write(sidecar)
        result["output_sha256"][SIDECAR_NAME] = sha256_bytes(sidecar)
        result["output_bytes"] = {**{name: len(data) for name, data in sorted(files.items())}, SIDECAR_NAME: len(sidecar)}
        if before_publish is not None:
            before_publish()
        require(not os.path.lexists(target), "Output directory appeared during staging; refusing to overwrite")
        os.rename(staging, target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    result["output_dir"] = str(target)
    result["files_written"] = len(files) + 1
    return result


def build(run_dir, selection_name, profile_name, export_format):
    """Disk entrypoint: verify export profile digest binding, run planner.build, then gate."""
    require(export_format in FORMATS, "Unsupported export format")
    require(1 <= len(str(run_dir)) <= planner.MAX_RUN_DIR_PATH, "Run directory path exceeds bound")
    planner.relative_json_name(profile_name)
    require(not Path(run_dir).is_symlink(), "Run directory symlink rejected")
    directory = Path(run_dir).resolve(strict=True)
    export_profile, export_digest, _ = planner.read_json(markers.local_artifact(directory, profile_name))
    validate_export_profile(export_profile, export_format)
    plan_name = export_profile["plan_profile"]
    require(len({profile_name, plan_name, selection_name, "markers.json", "manifest.json"}) == 5,
            "Input roles must be distinct")
    plan_profile, plan_digest, _ = planner.read_json(markers.local_artifact(directory, plan_name))
    require(plan_digest == export_profile["plan_profile_sha256"], "Stale plan_profile_sha256 in export profile")
    plan = planner.build(directory, selection_name, plan_name)
    require(plan["profile_sha256"] == plan_digest, "Plan profile changed during planning")
    require(profile_name not in plan["input_sha256"], "Export profile must not double as a planner input")
    generic, generic_digest, _ = planner.read_json(markers.local_artifact(directory, "markers.json"))
    require(generic_digest == plan["input_sha256"]["markers.json"], "Generic markers changed during export")
    pts = None
    pts_name = plan_profile.get("pts_artifact")
    if pts_name is not None:
        pts, pts_digest, _ = planner.read_json(markers.local_artifact(directory, pts_name))
        require(pts_digest == plan["input_sha256"][pts_name], "PTS artifact changed during export")
    hashes = dict(plan["primary_input_sha256"])
    hashes[profile_name] = export_digest
    result, files = export_plan(plan, generic, plan_profile, export_profile, pts, export_format, hashes, "build")
    result["plan_summary"] = planner.make_summary(plan)

    def unchanged():
        for name, digest in hashes.items():
            require(markers.sha256(markers.local_artifact(directory, name)) == digest, f"Input changed during export: {name}")
    return result, files, unchanged


def summary_view(result):
    view = {key: value for key, value in result.items() if key not in ("markers", "limitations")}
    data = json.dumps(view, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    require(len(data.encode()) <= MAX_SUMMARY_BYTES, "Summary exceeds 64 KiB bound")
    return data


def emit_error(message):
    encoded = ("editor-marker-export: " + str(message)).encode("utf-8")[:MAX_ERROR_BYTES - 1]
    sys.stderr.write(encoded.decode("utf-8", errors="ignore") + "\n")


class BoundedParser(argparse.ArgumentParser):
    def error(self, message):
        emit_error(message)
        raise SystemExit(2)


def main(argv=None):
    parser = BoundedParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir")
    parser.add_argument("selection", help="Run-relative selection JSON")
    parser.add_argument("profile", help="Run-relative closed export profile JSON (binds the planner profile)")
    parser.add_argument("--format", required=True, choices=FORMATS, dest="export_format")
    parser.add_argument("--output-dir", required=True, help="Absent directory; created only when export is written")
    parser.add_argument("--dtd", help="Optional local DTD file for xmllint validation (never fetched)")
    parser.add_argument("--summary", action="store_true", help="Compact result without per-marker rows")
    args = parser.parse_args(argv)
    try:
        dtd = check_dtd_path(args.dtd) if args.dtd is not None else None
        require(not os.path.lexists(args.output_dir), "Output directory already exists; refusing to overwrite")
        result, files, unchanged = build(args.run_dir, args.selection, args.profile, args.export_format)
        result["dtd_supplied"] = dtd is not None
        if files:
            write_exclusive(args.output_dir, result, files, dtd, before_publish=unchanged)
        else:
            unchanged()
        text = summary_view(result) if args.summary else json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2)
        print(text)
        return 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        emit_error(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
