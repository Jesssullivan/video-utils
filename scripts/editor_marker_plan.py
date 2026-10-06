#!/usr/bin/env python3
"""Plan source-time editor review markers as JSON; never invoke an editor."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import markers

MAX_BYTES = 20_000_000
MAX_TOTAL_BYTES = 64_000_000
MAX_MARKERS = 50_000
MAX_ACTIONS = 1000
MAX_FRAMES = 120_000
HASH = re.compile(r"[0-9a-f]{64}")


class SourceDecimal(float):
    """Retain the numeric JSON lexeme for exact time conversion, not ID encoding."""

    def __new__(cls, encoded):
        value = super().__new__(cls, encoded)
        value.encoded = encoded
        return value

    def __str__(self):
        return self.encoded


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pairs_unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"Non-finite JSON constant: {value}")


def read_json(path):
    require(path.stat().st_size <= MAX_BYTES, "JSON byte bound exceeded")
    with path.open("rb") as stream:
        encoded = stream.read(MAX_BYTES + 1)
    require(len(encoded) <= MAX_BYTES, "JSON grew beyond byte bound")
    value = json.loads(encoded, object_pairs_hook=pairs_unique, parse_constant=reject_constant,
                       parse_float=SourceDecimal)
    require(isinstance(value, dict), "JSON input must be an object")
    # Also rejects numeric overflow such as 1e999, accepted by the standard decoder.
    json.dumps(value, allow_nan=False)
    return value, hashlib.sha256(encoded).hexdigest(), len(encoded)


def rational(value, label):
    require(not isinstance(value, bool) and isinstance(value, (int, float, str)),
            f"Invalid {label}")
    if isinstance(value, float):
        require(math.isfinite(value), f"Non-finite {label}")
    require(len(str(value)) <= 128, f"Oversized {label}")
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"Invalid rational {label}") from exc
    require(abs(result.numerator) <= 2**127 - 1 and result.denominator <= 2**127 - 1,
            f"Rational bound exceeded: {label}")
    return result


def ratio(value):
    return f"{value.numerator}/{value.denominator}"


def marker_id(index, item):
    digest = hashlib.sha256(json.dumps(item, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return f"marker-{index:04d}-{digest[:12]}"


def pts_table(payload, source_hash):
    require(payload.get("source_sha256") == source_hash, "PTS source identity differs")
    require(payload.get("clock") == "original_source_stream_timestamps_seconds",
            "PTS must explicitly use original source timestamps")
    tick = rational(payload.get("time_base"), "PTS time base")
    require(tick > 0, "PTS time base must be positive")
    frames = payload.get("frames")
    require(isinstance(frames, list) and 0 < len(frames) <= MAX_FRAMES,
            "PTS frame count outside bound")
    starts, ends = [], []
    for row in frames:
        require(isinstance(row, dict), "PTS frame must be an object")
        values = [row.get("best_effort_timestamp"), row.get("duration")]
        require(all(isinstance(v, int) and not isinstance(v, bool) for v in values),
                "PTS ticks and durations must be integers")
        require(values[1] > 0, "PTS frame duration unknown or nonpositive")
        starts.append(values[0] * tick)
        ends.append((values[0] + values[1]) * tick)
    require(all(a < b for a, b in zip(starts, starts[1:])),
            "Duplicate or nonmonotonic PTS")
    # A newer presented frame supersedes the earlier frame even if its reported
    # duration overlaps. This avoids using an old interval to bridge a later gap.
    ends = [min(end, starts[i + 1]) if i + 1 < len(starts) else end
            for i, end in enumerate(ends)]
    return starts, ends


def frame_at(time, starts, ends):
    index = bisect_right(starts, time) - 1
    return index if index >= 0 and time < ends[index] else None


def covered(start, end, starts, ends):
    index = frame_at(start, starts, ends)
    if index is None:
        return False
    if start == end:
        return True
    extent = ends[index]
    while extent < end:
        index += 1
        if index >= len(starts) or starts[index] > extent:
            return False
        extent = max(extent, ends[index])
    return True


def grid_point(value):
    return (value + Fraction(1, 2)).numerator // (value + Fraction(1, 2)).denominator


def make_plan(generic, selection, profile, pts=None, input_hashes=None):
    """Pure coordinate planning. Host contracts remain unverified for every profile."""
    source_hash = generic.get("source_sha256")
    require(isinstance(source_hash, str) and HASH.fullmatch(source_hash), "Invalid source hash")
    require(selection.get("source_sha256") == profile.get("source_sha256") == source_hash,
            "Selection/profile source identity differs")
    require(profile.get("target") in ("final_cut_pro", "davinci_resolve"), "Unsupported editor target")
    require(profile.get("mapping_kind", "unretimed") == "unretimed", "Unsupported retiming or nested mapping")
    require(profile.get("target_sha256", source_hash) == source_hash,
            "Derivative mapping unsupported in this planner")
    items = generic.get("markers")
    require(isinstance(items, list) and len(items) <= MAX_MARKERS, "Marker count outside bound")
    chosen = selection.get("selected_markers")
    require(isinstance(chosen, list) and len(chosen) <= MAX_MARKERS, "Explicit selection required")
    starts, ends = pts_table(pts, source_hash) if pts is not None else ([], [])
    origin_fields = ("source_origin", "asset_origin", "clip_in", "clip_out", "parent_offset")
    origins = {key: rational(profile[key], key) for key in origin_fields if profile.get(key) is not None}
    if "clip_in" in origins and "clip_out" in origins:
        require(origins["clip_out"] > origins["clip_in"], "Invalid clip bounds")
    grid = profile.get("fixture_grid")
    if grid is not None:
        require(isinstance(grid, dict), "Fixture grid must be an object")
        period = rational(grid.get("frame_duration"), "frame duration")
        grid_origin = rational(grid.get("origin"), "grid origin")
        frame_origin = grid.get("frame_id_origin")
        require(period > 0 and isinstance(frame_origin, int) and not isinstance(frame_origin, bool),
                "Explicit positive grid and integer frame-ID origin required")
        require(abs(frame_origin) <= 2**31 - 1, "Frame-ID origin exceeds bound")
    rows, actions, selected_ids, seen = [], [], [], set()
    for selected in chosen:
        require(isinstance(selected, dict), "Selection row must be an object")
        index = selected.get("marker_index")
        require(isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(items),
                "Selection index outside generic markers")
        item = items[index]
        require(isinstance(item, dict), "Marker must be an object")
        identity = marker_id(index, item)
        require(selected.get("marker_id") == identity, "Selection ID or marker content is stale")
        if identity in seen:
            continue
        seen.add(identity)
        selected_ids.append(identity)
        require(item.get("status") == "needs_review" and item.get("performance_issue_confirmed") is not True,
                "Markers must remain unconfirmed review hypotheses")
        start = rational(item.get("source_time_seconds"), "marker start")
        end = rational(item.get("end_seconds", item.get("source_time_seconds")), "marker end")
        require(end >= start, "Marker end precedes start")
        local = None
        if "source_origin" in origins and "asset_origin" in origins:
            local = origins["asset_origin"] + start - origins["source_origin"]
        local_end = None if local is None else local + end - start
        inside_clip = (local is not None and "clip_in" in origins and "clip_out" in origins
                       and origins["clip_in"] <= local < origins["clip_out"]
                       and local_end <= origins["clip_out"])
        coverage = covered(start, end, starts, ends) if starts else False
        disposition = ("outside_clip" if set(origin_fields[:4]).issubset(origins) and not inside_clip else
                       "video_coverage_unverified" if not starts else
                       "outside_video_coverage" if not coverage else
                       "clip_origin_or_bounds_unverified" if not set(origin_fields[:4]).issubset(origins) else
                       "outside_clip" if not inside_clip else "native_contract_unverified")
        title = f"REVIEW · uncertain candidate · {identity}"
        notes = (f"needs_review; source [{ratio(start)}, {ratio(end)}) seconds; "
                 f"candidate={item.get('name', 'unknown')}; confidence={item.get('confidence', 'unknown')}; "
                 "not a confirmed musical mistake; native contract unverified")
        row = {"marker_id": identity, "marker_index": index, "kind": "point" if start == end else "range",
               "source_start": ratio(start), "source_end": ratio(end),
               "asset_local_start": None if local is None else ratio(local),
               "asset_local_end": None if local_end is None else ratio(local_end),
               "parent_time": (ratio(origins["parent_offset"] + local - origins["clip_in"])
                               if local is not None and "parent_offset" in origins and "clip_in" in origins else None),
               "preview_frame_index": frame_at(start, starts, ends) if starts else None,
               "host_frame_id": None, "disposition": disposition, "status": "needs_review",
               "confidence": item.get("confidence"), "evidence": item.get("evidence", {}),
               "title": title, "notes": notes, "fixture_positions": None}
        if grid is not None and local is not None:
            raw_start, raw_end = (local - grid_origin) / period, (local_end - grid_origin) / period
            first = grid_point(raw_start) if start == end else raw_start.numerator // raw_start.denominator
            last = first if start == end else -((-raw_end.numerator) // raw_end.denominator)
            snapped_start, snapped_end = grid_origin + first * period, grid_origin + last * period
            row["fixture_positions"] = {"start_frame": first + frame_origin, "end_frame": last + frame_origin,
                "duration_frames": max(1, last - first), "frame_duration": ratio(period),
                "start_error_seconds": ratio(snapped_start - local),
                "end_error_seconds": ratio(snapped_end - local_end),
                "mapping_status": "hypothetical_uniform_grid_not_host_verified"}
            quantized_inside = (inside_clip and snapped_start >= origins["clip_in"]
                                and snapped_start + period <= origins["clip_out"]
                                and snapped_end <= origins["clip_out"])
            if not quantized_inside:
                row["disposition"] = "fixture_quantization_outside_clip"
            elif coverage:
                if profile["target"] == "final_cut_pro":
                    endpoints = [("POINT" if start == end else "START", first, snapped_start)]
                    if start != end:
                        endpoints.append(("END", last, snapped_end))
                    if any(position + period > origins["clip_out"] for _, _, position in endpoints):
                        row["disposition"] = "exclusive_end_boundary_unrepresentable"
                        rows.append(row)
                        continue
                    source_endpoints = [(origins["source_origin"] + position - origins["asset_origin"],
                                         origins["source_origin"] + position + period - origins["asset_origin"])
                                        for _, _, position in endpoints]
                    if not covered(source_endpoints[0][0], source_endpoints[-1][1], starts, ends):
                        row["disposition"] = "fixture_quantization_outside_video_coverage"
                        rows.append(row)
                        continue
                    for role, frame, position in endpoints:
                        actions.append({"marker_id": identity, "role": role,
                            "receiver": "source_asset_clip", "fixture_frame_id": frame + frame_origin,
                            "fixture_start_seconds": ratio(position), "fixture_duration_seconds": ratio(period),
                            "title": f"{role} · {title}", "notes": notes, "executable": False})
                else:
                    required_end = snapped_start + period if start == end else snapped_end
                    quantized_source_start = origins["source_origin"] + snapped_start - origins["asset_origin"]
                    quantized_source_end = origins["source_origin"] + required_end - origins["asset_origin"]
                    if not covered(quantized_source_start, quantized_source_end, starts, ends):
                        row["disposition"] = "fixture_quantization_outside_video_coverage"
                    else:
                        actions.append({"marker_id": identity, "role": row["kind"],
                            "receiver": "explicit_original_MediaPoolItem", "fixture_frame_id": first + frame_origin,
                            "fixture_duration_frames": max(1, last-first), "title": title, "notes": notes,
                            "executable": False, "api_contract": "unverified"})
        rows.append(row)
    if len(actions) > MAX_ACTIONS:
        actions = []
        plan_status = "selection_required"
    else:
        plan_status = "fixture_only" if grid is not None else "calibration_required"
    existing = profile.get("existing_markers", [])
    require(isinstance(existing, list) and len(existing) <= MAX_ACTIONS, "Existing-marker snapshot exceeds bound")
    existing_frames = set()
    for item in existing:
        require(isinstance(item, dict) and isinstance(item.get("fixture_frame_id"), int)
                and not isinstance(item.get("fixture_frame_id"), bool), "Invalid existing-marker snapshot")
        existing_frames.add(item["fixture_frame_id"])
    counts = {}
    for action in actions:
        key = (action["receiver"], action["fixture_frame_id"])
        counts[key] = counts.get(key, 0) + 1
    for action in actions:
        key = (action["receiver"], action["fixture_frame_id"])
        action["collision"] = ("preserve_existing_marker" if action["fixture_frame_id"] in existing_frames else
                               "planned_same_frame_conflict" if counts[key] > 1 else "none")
    return {"schema_version": 1, "format": "editor_marker_dry_run", "source_sha256": source_hash,
        "target": profile["target"], "plan_status": plan_status,
        "native_contract_status": "native_contract_unverified", "executable": False,
        "input_sha256": input_hashes or {}, "selected_ids": selected_ids,
        "excluded_ids": [marker_id(i, item) for i, item in enumerate(items) if marker_id(i, item) not in seen],
        "marker_count": len(items), "selected_count": len(rows), "markers": rows, "actions": actions,
        "existing_marker_inspection": "unverified_fixture_only" if existing else "pending",
        "limitations": ["No editor invocation or native import file is produced.",
            "Fixture frame IDs are hypothetical and are never host coordinates.",
            "Review observations are not confirmed notes, beats, meter, or performance mistakes."]}


def build(run_dir, selection_name, profile_name):
    require(not Path(run_dir).is_symlink(), "Run directory symlink rejected")
    directory = Path(run_dir).resolve(strict=True)
    paths, documents, digests, total = {}, {}, {}, 0

    def acquire(name):
        nonlocal total
        if name in documents:
            return documents[name]
        path = markers.local_artifact(directory, name)
        value, digest, size = read_json(path)
        total += size
        require(total <= MAX_TOTAL_BYTES, "Aggregate JSON byte bound exceeded")
        paths[name], documents[name], digests[name] = path, value, digest
        return value

    generic, manifest = acquire("markers.json"), acquire("manifest.json")
    selection, profile = acquire(selection_name), acquire(profile_name)
    require(selection_name != profile_name and selection_name not in ("markers.json", "manifest.json")
            and profile_name not in ("markers.json", "manifest.json"), "Input roles must be distinct")
    require(manifest.get("source", {}).get("sha256") == generic.get("source_sha256"), "Manifest source mismatch")
    # Preflight every JSON artifact that the existing provenance verifier will read.
    acquire("flags.json")
    graph_path = directory / "dag.json"
    if graph_path.exists() or graph_path.is_symlink():
        graph = acquire("dag.json")
        for name in graph.get("artifact_hashes", {}):
            if name.endswith(".json"):
                acquire(name)
            else:
                path = markers.local_artifact(directory, name)
                total += path.stat().st_size
                require(total <= MAX_TOTAL_BYTES, "Aggregate input byte bound exceeded")
                paths[name], digests[name] = path, markers.sha256(path)
    expected, _ = markers.build(directory)
    require(generic == expected, "Generic markers are stale or differ from verified graph")
    pts_name = profile.get("pts_artifact")
    pts = acquire(pts_name) if pts_name is not None else None
    expected_hashes = profile.get("input_sha256")
    require(isinstance(expected_hashes, dict), "Explicit input digests required in profile")
    needed = {"markers.json", "manifest.json", selection_name}
    if pts_name is not None:
        needed.add(pts_name)
    for name in needed:
        digest = expected_hashes.get(name)
        require(isinstance(digest, str) and HASH.fullmatch(digest) and digest == digests[name],
                f"Stale or missing profile input digest: {name}")
    result = make_plan(generic, selection, profile, pts, dict(digests))
    result["source_identity_verification"] = "manifest_and_graph_bound_source_hash_original_media_not_rehashed"
    result["profile_sha256"] = digests[profile_name]
    result["worker_sha256"] = markers.sha256(Path(__file__))
    for name, path in paths.items():
        require(markers.local_artifact(directory, name) == path and markers.sha256(path) == digests[name],
                "Input changed during planning")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("selection", help="Run-relative selection JSON")
    parser.add_argument("profile", help="Run-relative editor profile JSON")
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.run_dir, args.selection, args.profile), ensure_ascii=False, allow_nan=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(f"editor-marker-plan: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
