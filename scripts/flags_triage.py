#!/usr/bin/env python3
"""Order a run's existing review flags into a compact default view; read-only.

At most one flag per window is shown. Navigation proxies are hidden by default
but retained verbatim. No flag kind is added, no flag is altered or dropped, and
uncalibrated numeric confidence never ranks anything. This is a review ordering,
not a performance grade or a musical verdict.
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
from dag import atomic_write  # noqa: E402
from markers import local_artifact  # noqa: E402
import marked_video  # noqa: E402

SCHEMA_ID = "video-utils.flags-triage.s2"
MAX_JSON_BYTES = 20_000_000
MAX_FLAGS = 50_000
WINDOW_GRID_PERIODS = 16
ORIGINAL_AXIS = "original_source_stream_timestamps_seconds"
NAVIGATION_KIND = "four_pulse_group_review_candidate"
NAVIGATION_CONFIDENCE = "navigation_proxy_not_confirmed_bar"
NAVIGATION_EVIDENCE_KIND = "four_pulse_bar_proxy"
# The T1 table is the renderer's own comparison set (imported, never copied);
# importing marked_video only defines functions and runs no media tool.
COMPARISON_KINDS = tuple(sorted(marked_video.COMPARISON_KINDS))
TIERS = (
    ("T1", "within_take_comparison_difference", COMPARISON_KINDS),
    ("T2", "automatic_recurrence", ("automatic_recurrence_review_candidate",)),
    ("T3", "register_or_ending_texture", ("low_register_riff_or_breakdown_candidate",
                                          "bright_ending_texture_candidate")),
    ("T4", "spectral_texture_region", ("spectral_texture_region_candidate",)),
)
UNRANKED_TIER = ("T5", "unranked_kind")
PRIORITY_RULE = {
    "id": "flags-triage-priority-v1",
    "ordering": "lexicographic_deterministic",
    "keys": [
        "1. tier by existing kind: " + "; ".join(f"{tier} {name} = {', '.join(kinds)}"
                                                 for tier, name, kinds in TIERS)
        + "; T5 unranked_kind = any other kind (kept eligible, never dropped)",
        "2. flags with a hash-bound selected_evidence_slot before flags without",
        "3. earlier source_time_seconds; then kind; then original flag index",
    ],
    "tiers": [{"tier": tier, "name": name, "kinds": list(kinds)} for tier, name, kinds in TIERS]
    + [{"tier": UNRANKED_TIER[0], "name": UNRANKED_TIER[1], "kinds": "any_other_kind"}],
    "numeric_confidence_used": False,
    "numeric_confidence_note": "confidence and similarity values are uncalibrated and not probabilities",
    "per_window_shown_maximum": 1,
    "navigation_proxy_rule": {
        "match": "any upstream token below equals the flag field",
        "action": "hidden by default; retained verbatim in hidden_navigation",
        "upstream_tokens": {"kind": NAVIGATION_KIND, "confidence": NAVIGATION_CONFIDENCE,
                            "evidence.kind": NAVIGATION_EVIDENCE_KIND},
    },
}
GENERATED_FORBIDDEN_WORDS = ("mistake", "error", "wrong", "missed", "incorrect", "confirmed")


class TriageError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def finite(value):
    return type(value) in (int, float) and math.isfinite(float(value))


def read_json(path, limit=MAX_JSON_BYTES):
    """Bounded, no-follow, duplicate-key and NaN rejecting snapshot plus its sha256."""
    try:
        data = annotation_v2.read_bytes(path, limit)
        value = annotation_v2.parse_json(data)
    except annotation_v2.AnnotationError as exc:
        raise TriageError(exc.code) from exc
    except FileNotFoundError as exc:
        raise TriageError("triage_input_missing") from exc
    except (OSError, ValueError, RecursionError, UnicodeError) as exc:
        raise TriageError("triage_input_unreadable") from exc
    if not isinstance(value, dict):
        raise TriageError("triage_input_object_required")
    return value, hashlib.sha256(data).hexdigest()


def run_file(run_dir, name):
    try:
        return local_artifact(run_dir, name)
    except ValueError as exc:
        raise TriageError("unsafe_or_missing_run_artifact") from exc


def flag_id(index, flag):
    """marked_video convention: index plus first 12 hex of the canonical flag sha256."""
    canonical = json.dumps(flag, sort_keys=True, allow_nan=False).encode()
    return f"flag-{index:04d}-" + hashlib.sha256(canonical).hexdigest()[:12]


def is_navigation_proxy(flag):
    evidence = flag.get("evidence")
    return (flag.get("kind") == NAVIGATION_KIND or flag.get("confidence") == NAVIGATION_CONFIDENCE
            or (isinstance(evidence, dict) and evidence.get("kind") == NAVIGATION_EVIDENCE_KIND))


def tier_of(kind):
    for rank, (tier, name, kinds) in enumerate(TIERS):
        if kind in kinds:
            return rank, tier, name
    return len(TIERS), UNRANKED_TIER[0], UNRANKED_TIER[1]


def selected_slot_verified(run_dir, flags, flag, cache):
    """True only when the slot binding agrees with flags.evidence_artifacts and file bytes."""
    slot = flag.get("selected_evidence_slot")
    bindings = flags.get("evidence_artifacts")
    if not isinstance(slot, str) or not isinstance(bindings, dict):
        return False
    binding = bindings.get(slot)
    if (not isinstance(binding, dict) or flag.get("selected_artifact") != binding.get("selector")
            or flag.get("selected_artifact_sha256") != binding.get("sha256")):
        return False
    selector = binding.get("selector")
    if selector not in cache:
        try:
            path = local_artifact(run_dir, selector)
            cache[selector] = annotation_v2.hash_provenance(path, max_bytes=MAX_JSON_BYTES * 2)
        except (ValueError, OSError, annotation_v2.AnnotationError):
            cache[selector] = None
    return cache[selector] is not None and cache[selector] == binding.get("sha256")


def phrase_basis(run_dir, source_hash):
    """Return (spans, receipt) or (None, status) for list-valued semantic phrase spans."""
    path = run_dir / "phrases.json"
    if not path.exists() and not path.is_symlink():
        return None, "phrases_json_absent"
    phrases, digest = read_json(run_file(run_dir, "phrases.json"))
    interpretation = phrases.get("interpretation")
    spans = interpretation.get("semantic_phrases") if isinstance(interpretation, dict) else None
    if not isinstance(spans, list) or not spans:
        return None, "semantic_phrases_not_a_nonempty_list"
    rows = []
    for index, span in enumerate(spans):
        if not (isinstance(span, dict) and finite(span.get("source_start_seconds"))
                and finite(span.get("source_end_seconds"))
                and float(span["source_end_seconds"]) > float(span["source_start_seconds"])):
            return None, "semantic_phrases_without_finite_source_spans"
        rows.append((float(span["source_start_seconds"]), float(span["source_end_seconds"]), index))
    graph_path = run_dir / "dag.json"
    if graph_path.exists() or graph_path.is_symlink():
        graph, _ = read_json(run_file(run_dir, "dag.json"))
        hashes = graph.get("artifact_hashes")
        if not isinstance(hashes, dict) or hashes.get("phrases.json") != digest:
            raise TriageError("stale_phrase_spans")
        if graph.get("source_sha256") not in (None, source_hash):
            raise TriageError("flags_source_mismatch")
    rows.sort()
    return rows, {"artifact": {"selector": "phrases.json", "sha256": digest}}


def grid_basis(run_dir, flags):
    bindings = flags.get("evidence_artifacts")
    binding = bindings.get("clicks") if isinstance(bindings, dict) else None
    if not isinstance(binding, dict) or not isinstance(binding.get("selector"), str):
        return None
    clicks, digest = read_json(run_file(run_dir, binding["selector"]))
    if digest != binding.get("sha256"):
        raise TriageError("stale_click_grid")
    grid = clicks.get("click_grid")
    timeline = flags.get("timeline")
    if not (isinstance(grid, dict) and finite(grid.get("period_seconds")) and float(grid["period_seconds"]) > 0
            and finite(grid.get("phase_seconds_audio_relative"))):
        return None
    if not (isinstance(timeline, dict) and finite(timeline.get("audio_start_seconds"))):
        return None
    period = float(grid["period_seconds"])
    phase = float(timeline["audio_start_seconds"]) + float(grid["phase_seconds_audio_relative"])
    return {"artifact": {"selector": binding["selector"], "sha256": digest}, "period_seconds": period,
            "phase_seconds_source": phase, "window_seconds": WINDOW_GRID_PERIODS * period,
            "bpm_as_recorded": grid.get("bpm") if finite(grid.get("bpm")) else None,
            "grid_identity_as_recorded": grid.get("identity") if isinstance(grid.get("identity"), str) else None}


def grid_id(k):
    return f"grid_{k:+03d}"


def grid_window(t, grid):
    return math.floor((t - grid["phase_seconds_source"]) / grid["window_seconds"])


def triage(run_dir):
    run_dir = Path(run_dir).resolve()
    flags_path = run_file(run_dir, "flags.json")
    flags, flags_digest = read_json(flags_path)
    manifest, manifest_digest = read_json(run_file(run_dir, "manifest.json"))
    try:
        source_hash = corpus.source_identity(manifest)
    except corpus.CorpusError as exc:
        raise TriageError("flags_source_mismatch") from exc
    if flags.get("source_sha256") != source_hash:
        raise TriageError("flags_source_mismatch")
    timeline = flags.get("timeline")
    if isinstance(timeline, dict) and timeline.get("axis") not in (None, ORIGINAL_AXIS):
        raise TriageError("flags_timeline_axis_unknown")
    items = flags.get("flags")
    if not isinstance(items, list) or len(items) > MAX_FLAGS:
        raise TriageError("invalid_flag_collection")
    intervals = []
    for flag in items:
        if not isinstance(flag, dict) or not finite(flag.get("source_time_seconds")):
            raise TriageError("invalid_flag_interval")
        start = float(flag["source_time_seconds"])
        end = flag.get("end_seconds", start)
        if not finite(end) or float(end) < start:
            raise TriageError("invalid_flag_interval")
        intervals.append((start, float(end)))
    try:
        bounds = corpus.source_bounds(manifest)
    except corpus.CorpusError:
        bounds = None

    spans, phrase_status = phrase_basis(run_dir, source_hash)
    grid = None
    if spans is not None:
        window_basis = {"kind": "phrase_spans", **phrase_status, "span_count": len(spans),
                        "residual_window": "unspanned", "bar_or_downbeat_identified": False}
        defined = [f"phrase-{rank:03d}" for rank in range(len(spans))]
    else:
        grid = grid_basis(run_dir, flags)
        if grid is None:
            raise TriageError("triage_window_basis_unavailable")
        window_basis = {"kind": "click_grid_16_period_navigation_windows", **grid,
                        "grid_periods_per_window": WINDOW_GRID_PERIODS,
                        "window_formula": "floor((source_time_seconds - phase_seconds_source) / (16 * period_seconds))",
                        "phrase_spans_status": phrase_status, "bar_or_downbeat_identified": False,
                        "note": "navigation windows from a periodic transient grid; not bars, phrases or meter"}
        defined = []
        if bounds is not None:
            first = grid_window(bounds[0], grid)
            last = max(first, math.ceil((bounds[1] - grid["phase_seconds_source"]) / grid["window_seconds"]) - 1)
            defined = [grid_id(k) for k in range(first, last + 1)]

    def locate(start, end):
        if spans is not None:
            for rank, (low, high, _) in enumerate(spans):
                if low <= start <= high:
                    return f"phrase-{rank:03d}", end > high
            return "unspanned", None
        k = grid_window(start, grid)
        k_end = k if end <= start else math.ceil((end - grid["phase_seconds_source"]) / grid["window_seconds"]) - 1
        return grid_id(k), k_end > k

    slot_cache = {}
    hidden, candidates = [], {}
    for index, flag in enumerate(items):
        identifier = flag_id(index, flag)
        if is_navigation_proxy(flag):
            hidden.append({"flag_index": index, "flag_id": identifier,
                           "reason": "navigation_proxy_hidden_by_default", "flag": flag})
            continue
        window, crosses = locate(*intervals[index])
        rank, tier, tier_name = tier_of(flag.get("kind"))
        bound = selected_slot_verified(run_dir, flags, flag, slot_cache)
        kind = flag.get("kind") if isinstance(flag.get("kind"), str) else ""
        key = (rank, 0 if bound else 1, intervals[index][0], kind, index)
        candidates.setdefault(window, []).append((key, {
            "flag_index": index, "flag_id": identifier, "window_id": window, "tier": tier,
            "tier_name": tier_name, "selected_evidence_hash_bound": bound,
            "crosses_window_boundary": crosses, "flag": flag}))

    shown, suppressed = [], []
    for window in sorted(candidates):
        ranked = sorted(candidates[window], key=lambda pair: pair[0])
        winner = ranked[0][1]
        shown.append(winner)
        for _, item in ranked[1:]:
            suppressed.append({**item, "reason": "lower_priority_in_window", "winner_flag_id": winner["flag_id"]})
    shown.sort(key=lambda item: (intervals[item["flag_index"]][0], item["flag_index"]))
    suppressed.sort(key=lambda item: item["flag_index"])
    used = set(candidates)
    windows = list(dict.fromkeys(defined + sorted(used - set(defined))))
    denominators = {"total_flags": len(items), "navigation_hidden": len(hidden),
                    "suppressed_lower_priority": len(suppressed), "shown": len(shown),
                    "window_count": len(windows), "windows_with_shown": len(shown)}
    if denominators["shown"] + denominators["suppressed_lower_priority"] + denominators["navigation_hidden"] != len(items):
        raise TriageError("triage_denominator_identity_failed")
    kinds_in = {}
    for flag in items:
        kinds_in[str(flag.get("kind"))] = kinds_in.get(str(flag.get("kind")), 0) + 1
    return {
        "schema_id": SCHEMA_ID, "schema_version": 1, "source_sha256": source_hash,
        "flags_sha256": flags_digest, "manifest_sha256": manifest_digest,
        "timeline": {"axis": ORIGINAL_AXIS}, "window_basis": window_basis,
        "windows": windows, "priority_rule": PRIORITY_RULE, "denominators": denominators,
        "input_kind_counts": dict(sorted(kinds_in.items())),
        "shown": shown, "suppressed": suppressed, "hidden_navigation": hidden,
        "view": "default_review_ordering_not_verdict", "performance_grade": "not_assigned",
        "musical_verdict": "not_established", "listening_acceptance": "not_established",
        "new_flag_kinds": [], "flags_modified": False,
        "limitations": [
            "Ordering only: every input flag is kept, either shown, suppressed within its window, or hidden as navigation.",
            "Numeric confidence and similarity are uncalibrated and are not used for ordering.",
            "Grid windows are navigation spans from a periodic transient grid, not bars, phrases or meter.",
            "Copied flag objects are unchanged; their own wording is the producing detector's.",
        ],
    }


def generated_strings(value, *, skip=("flag", "upstream_tokens")):
    """Yield generated keys/strings, skipping copied flags and quoted upstream tokens."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            if key not in skip:
                yield from generated_strings(item, skip=skip)
    elif isinstance(value, list):
        for item in value:
            yield from generated_strings(item, skip=skip)
    elif isinstance(value, str):
        yield value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        run_dir, output = args.run_dir.resolve(), args.output.expanduser().resolve()
        if output.is_relative_to(run_dir):
            raise TriageError("output_inside_run_dir")
        payload = triage(run_dir)
        atomic_write(output, json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    except TriageError as exc:
        print(json.dumps({"status": "rejected", "error": exc.code}), file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError):
        print(json.dumps({"status": "rejected", "error": "invalid_or_unreadable_metadata"}), file=sys.stderr)
        return 1
    print(json.dumps({"status": "flags_triage_written", "output": str(output), **payload["denominators"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
