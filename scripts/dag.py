#!/usr/bin/env python3
"""Record a guitar-analysis DAG and reference-based review candidates, locally."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MAX_JSON_BYTES = 20_000_000
MAX_EVENTS = 20_000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError(f"Oversized JSON artifact: {path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {path.name}")
    return value


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def number(value, name: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    value = float(value)
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def validate_reference(reference: dict, source_hash: str | None) -> dict:
    if reference.get("schema_version") != 1:
        raise ValueError("Reference schema_version must be 1")
    if reference.get("source_sha256") and reference["source_sha256"] != source_hash:
        raise ValueError("Reference source_sha256 does not match the original recording")
    # Unapproved annotations are retained as a receipt, never used to grade.
    if reference.get("approved") is not True:
        return {"approved": False, "status": "unapproved_not_used"}
    bpm = number(reference.get("bpm"), "reference bpm", 20)
    if bpm > 400:
        raise ValueError("Reference bpm must be <= 400")
    subdivision = reference.get("subdivision")
    if isinstance(subdivision, bool) or not isinstance(subdivision, int) or not 1 <= subdivision <= 64:
        raise ValueError("Reference subdivision must be an integer in 1..64; annotate tuplets explicitly")
    expected = reference.get("expected_onsets_seconds")
    if not isinstance(expected, list) or not 1 <= len(expected) <= MAX_EVENTS:
        raise ValueError("Approved reference needs 1..20000 explicit expected_onsets_seconds")
    expected = [number(item, "expected onset", 0) for item in expected]
    if any(a >= b for a, b in zip(expected, expected[1:])):
        raise ValueError("Expected onsets must be strictly increasing; chords use one attack")
    tolerance = number(reference.get("tolerance_seconds", .03), "tolerance_seconds", 0)
    window = number(reference.get("match_window_seconds", min(.2, 30 / bpm / subdivision)), "match_window_seconds", .000001)
    if tolerance > window or window > 1:
        raise ValueError("Require tolerance_seconds <= match_window_seconds <= 1")
    calibration = reference.get("onset_latency_seconds")
    if calibration is not None:
        calibration = number(calibration, "onset_latency_seconds")
    phrases = reference.get("phrase_spans", [])
    if not isinstance(phrases, list) or len(phrases) > 1000:
        raise ValueError("phrase_spans must contain at most 1000 objects")
    checked = []
    for span in phrases:
        if not isinstance(span, dict):
            raise ValueError("Each phrase span must be an object")
        start = number(span.get("start_seconds"), "phrase start_seconds", 0)
        end = number(span.get("end_seconds"), "phrase end_seconds", 0)
        if end <= start:
            raise ValueError("Phrase end must follow its start")
        checked.append({"start_seconds": start, "end_seconds": end, "name": str(span.get("name", "phrase"))[:256]})
    return {**reference, "bpm": bpm, "subdivision": subdivision, "expected_onsets_seconds": expected,
            "tolerance_seconds": tolerance, "match_window_seconds": window,
            "onset_latency_seconds": calibration, "phrase_spans": checked, "status": "approved"}


def match_onsets(expected: list[float], observed: list[float], window: float) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Maximize monotonic match count, then minimize total absolute timing error.

    Sparse sequence matching uses a Fenwick tree, bounded to 200000 candidate
    edges. Delayed updates prevent two observations matching one expectation.
    """
    import bisect
    tree = [(0, 0.0, None)] * (len(observed) + 1)
    nodes = []
    edge_count = 0

    def better(a, b):
        return a if (a[0], -a[1]) > (b[0], -b[1]) else b

    def query(end):
        best = (0, 0.0, None)
        while end > 0:
            best = better(tree[end], best)
            end -= end & -end
        return best

    def update(index, value):
        index += 1
        while index < len(tree):
            tree[index] = better(value, tree[index])
            index += index & -index

    for i, target in enumerate(expected):
        start = bisect.bisect_left(observed, target - window)
        end = bisect.bisect_right(observed, target + window)
        pending = []
        for j in range(start, end):
            edge_count += 1
            if edge_count > 200_000:
                raise ValueError("Too many onset match candidates; trim input or narrow match window")
            count, cost, previous = query(j)
            node = len(nodes)
            nodes.append((i, j, previous))
            pending.append((j, (count + 1, cost + abs(observed[j] - target), node)))
        for j, value in pending:
            update(j, value)
    pairs = []
    node = query(len(observed))[2]
    while node is not None:
        i, j, node = nodes[node]
        pairs.append((i, j))
    used_expected = {i for i, _ in pairs}
    used_observed = {j for _, j in pairs}
    return sorted(pairs), [i for i in range(len(expected)) if i not in used_expected], [j for j in range(len(observed)) if j not in used_observed]


def compare_reference(events: list[dict], reference: dict, source_start: float = 0) -> dict:
    if reference.get("approved") is not True:
        return {"status": "not_graded_reference_unapproved", "flags": [], "matches": []}
    attacks = []
    for event in events:
        if event.get("kind") != "broadband_attack_candidate":
            continue
        time = number(event.get("audio_relative_seconds"), "observed onset", 0)
        attacks.append(time)
    if len(attacks) > MAX_EVENTS:
        raise ValueError("Too many observed attacks; trim analysis")
    raw = sorted(set(attacks))
    latency = reference["onset_latency_seconds"]
    calibrated = latency is not None
    observed = [time - (latency or 0) for time in raw]
    expected = reference["expected_onsets_seconds"]
    pairs, missing, extra = match_onsets(expected, observed, reference["match_window_seconds"])
    flags, matches = [], []

    def flag(kind, start, end=None, **evidence):
        flags.append({"kind": kind, "audio_relative_seconds": start,
                      "source_time_seconds": source_start + start,
                      "end_seconds": source_start + (start if end is None else end),
                      "confidence": "unvalidated_transient_reference_candidate", "status": "needs_review",
                      "evidence": evidence, "performance_issue_confirmed": False})

    for i, j in pairs:
        offset = observed[j] - expected[i]
        matches.append({"expected_index": i, "observed_index": j, "expected_seconds": expected[i],
                        "observed_raw_seconds": raw[j], "observed_corrected_seconds": observed[j],
                        "offset_seconds": offset, "calibration_applied": calibrated})
        if abs(offset) > reference["tolerance_seconds"]:
            kind = ("early_attack_candidate" if offset < 0 else "late_attack_candidate") if calibrated else "uncalibrated_offset_review"
            flag(kind, raw[j], expected_index=i, expected_seconds=expected[i], offset_seconds=offset,
                 corrected_audio_relative_seconds=observed[j], onset_latency_seconds=latency)
    for i in missing:
        flag("expected_attack_not_detected_candidate", expected[i], expected_index=i,
             warning="Detector miss, merged/legato attack or masked transient; does not prove a missed note.")
    # Only grade extras within the explicitly annotated expected-event range.
    for j in extra:
        if expected[0] - reference["match_window_seconds"] <= observed[j] <= expected[-1] + reference["match_window_seconds"]:
            flag("unmatched_attack_candidate", raw[j], corrected_audio_relative_seconds=observed[j],
                 warning="May be click, noise, grace note or omitted reference event; does not prove an extra note.")
    by_expected = {i: j for i, j in pairs}
    for span in reference["phrase_spans"]:
        indices = [i for i, t in enumerate(expected) if span["start_seconds"] <= t < span["end_seconds"]]
        if not indices:
            flag("phrase_reference_has_no_attacks_review", span["start_seconds"], span["end_seconds"], phrase=span["name"])
            continue
        for label, i in (("start", indices[0]), ("last_attack", indices[-1])):
            j = by_expected.get(i)
            if j is None:
                flag(f"phrase_{label}_not_detected_candidate", expected[i], phrase=span["name"], expected_index=i)
            elif calibrated and abs(observed[j] - expected[i]) > reference["tolerance_seconds"]:
                flag(f"phrase_{label}_alignment_candidate", raw[j], phrase=span["name"],
                     offset_seconds=observed[j] - expected[i],
                     warning="Last attack does not identify phrase release or sustain end.")
    return {"status": "reference_comparison_candidates" if calibrated else "reference_comparison_uncalibrated",
            "calibration": {"onset_latency_seconds": latency, "explicit": calibrated},
            "matching_method": "maximum_count_minimum_total_offset_monotonic_one_to_one", "matches": matches,
            "flags": sorted(flags, key=lambda item: (item["source_time_seconds"], item["kind"]))}


def lineage(payload: dict, original_hash: str | None, processed_hashes: dict[str, bool]) -> str:
    identity = payload.get("source", {}).get("sha256")
    if identity and identity in processed_hashes:
        return "post_denoise" if processed_hashes[identity] else "rejected_unverified_processed_artifact"
    if identity and identity == original_hash:
        return "preliminary_raw_source"
    return "rejected_source_mismatch"


def build(run_dir: Path, reference_path: Path | None = None) -> tuple[dict, dict]:
    manifest = load(run_dir / "manifest.json")
    original_hash = manifest.get("source", {}).get("sha256")
    if not isinstance(original_hash, str) or len(original_hash) != 64:
        raise ValueError("Manifest must identify original source sha256")
    cleaned_hash = manifest.get("output_sha256", {}).get("cleaned.wav")
    cleaned = run_dir / "cleaned.wav"
    clean_verified = bool(cleaned_hash and cleaned.is_file() and sha256(cleaned) == cleaned_hash)
    processed_hashes = {}
    for name in ("denoised.wav", "cleaned.wav"):
        fingerprint = manifest.get("output_sha256", {}).get(name)
        artifact_path = run_dir / name
        if fingerprint:
            processed_hashes[fingerprint] = bool(artifact_path.is_file() and sha256(artifact_path) == fingerprint)
    start = number(manifest.get("timeline", {}).get("audio_start_seconds", 0), "audio_start_seconds")
    registry_path = ROOT / "program/dags/guitar-take.json"
    registry = load(registry_path)
    payloads, stage_rows = {}, []
    artifact_hashes = {"manifest.json": sha256(run_dir / "manifest.json")}
    for stage in registry["stages"]:
        artifact = stage.get("artifact")
        path = run_dir / artifact if artifact else None
        row = {**stage, "dependency_ids": stage["depends_on"], "source_sha256": original_hash,
               "status": "not_available", "artifact_sha256": None, "settings": None}
        if stage["id"] == "denoise":
            row.update(status="rendered_unreviewed" if clean_verified else "unverified_restoration",
                       artifact_sha256=artifact_hashes["manifest.json"], settings=manifest.get("profile"),
                       output_sha256=cleaned_hash, clean_artifact_verified=clean_verified)
        elif stage["id"] != "flags" and path and path.is_file():
            row["artifact_sha256"] = sha256(path)
            if stage["id"] == "report":
                # Reports render this graph: binding their hash as a graph input
                # creates a stale self-reference as soon as report.py rewrites it.
                row["status"] = "prior_report_snapshot_unreviewed"
            else:
                artifact_hashes[artifact] = row["artifact_sha256"]
                payload = load(path)
                row["settings"] = payload.get("analysis", payload.get("settings"))
                row["status"] = lineage(payload, original_hash, processed_hashes)
                row["analysis_input_sha256"] = payload.get("source", {}).get("sha256")
                if not row["status"].startswith("rejected"):
                    payloads[stage["id"]] = payload
        stage_rows.append(row)
    reference = None
    reference_receipt = {"status": "not_supplied", "sha256": None}
    if reference_path is not None:
        reference = validate_reference(load(reference_path), original_hash)
        reference_receipt = {"status": reference["status"], "path": str(reference_path),
                             "sha256": sha256(reference_path), "source_binding": "hash_verified" if reference.get("source_sha256") else "operator_approval_without_source_hash"}
    analysis = payloads.get("bpm", {})
    analysis_state = next(row["status"] for row in stage_rows if row["id"] == "bpm")
    if reference and reference.get("approved") is True and analysis:
        performance = compare_reference(analysis.get("events", []), reference, start)
    else:
        performance = {"status": "not_graded_analysis_unavailable" if reference and reference.get("approved") else "not_graded_no_approved_reference", "matches": [], "flags": []}
        if not analysis or not analysis.get("click_grid"):
            performance["flags"].append({"kind": "tempo_context_unresolved_review", "source_time_seconds": start,
                "end_seconds": start, "confidence": "unknown", "status": "needs_review", "evidence": {"reason": "No accepted periodicity grid"},
                "performance_issue_confirmed": False})
    phrases = payloads.get("phrases", {})
    for span in phrases.get("observations", {}).get("proposed_review_spans", []):
        a = number(span.get("start_seconds"), "review span start", 0)
        b = number(span.get("end_seconds"), "review span end", 0)
        if b < a:
            raise ValueError("Phrase review span end precedes start")
        performance["flags"].append({"kind": span.get("kind", "phrase_review_candidate"),
            "source_time_seconds": start + a, "end_seconds": start + b,
            "confidence": "unvalidated_heuristic_not_probability", "status": "needs_review",
            "evidence": span, "performance_issue_confirmed": False})
    notes = payloads.get("notes", {}).get("interpretation", {})
    flags = {"schema_version": 1, "source_sha256": original_hash, "analysis_lineage": analysis_state,
             "timeline": {"audio_start_seconds": start, "axis": "original_source_stream_timestamps_seconds"},
             "reference": reference_receipt, "musical_context": {"tonic": notes.get("tonic"), "mode": notes.get("mode"),
                 "status": "nullable_experimental_context_not_confirmed_intent"},
             **performance, "limitations": ["Flags compare mixture transient candidates with an approved reference; they are not detected note mistakes.",
                "Envelope recurrence does not establish repeated riffs or tonal identity.", "Raw-source analysis remains preliminary until post-denoise analysis is recorded.",
                "32 Hz fundamentals and intentional distortion are musical content, not automatic noise targets."]}
    flags["flags"].sort(key=lambda item: (item["source_time_seconds"], item["kind"]))
    encoded = json.dumps(flags, indent=2, allow_nan=False) + "\n"
    flags_hash = hashlib.sha256(encoded.encode()).hexdigest()
    artifact_hashes["flags.json"] = flags_hash
    for row in stage_rows:
        if row["id"] == "flags":
            row.update(status=performance["status"], artifact_sha256=flags_hash,
                       settings={"reference_sha256": reference_receipt["sha256"], "analysis_lineage": analysis_state})
        row["settings_sha256"] = hashlib.sha256(json.dumps(row["settings"], sort_keys=True, allow_nan=False).encode()).hexdigest()
    by_id = {row["id"]: row for row in stage_rows}
    for row in stage_rows:
        row["dependency_artifact_hashes"] = {key: by_id[key]["artifact_sha256"] for key in row["depends_on"]}
    graph = {"schema_version": 1, "kind": "artifact_provenance_DAG_not_an_execution_engine", "source_sha256": original_hash,
             "registry_sha256": sha256(registry_path), "artifact_hashes": artifact_hashes,
             "reference": reference_receipt, "stages": stage_rows, "flags_sha256": flags_hash,
             "instrument_context": registry["instrument_context"], "listening_accepted": False,
             "report_binding": "report_stage_is_prior_snapshot_not_validated_input_to_avoid_summary_self_reference"}
    return graph, flags


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args()
    try:
        directory = args.run_dir.expanduser().resolve(strict=True)
        reference = args.reference.expanduser().resolve(strict=True) if args.reference else None
        if reference in {directory / "flags.json", directory / "dag.json"}:
            raise ValueError("Reference cannot be an output artifact")
        graph, flags = build(directory, reference)
        atomic_write(directory / "flags.json", json.dumps(flags, indent=2, allow_nan=False) + "\n")
        atomic_write(directory / "dag.json", json.dumps(graph, indent=2, allow_nan=False) + "\n")
        print(json.dumps({"dag_json": str(directory / "dag.json"), "flags_json": str(directory / "flags.json"),
                          "status": flags["status"], "flag_count": len(flags["flags"])}))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"dag: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
