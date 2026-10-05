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
EVIDENCE_SLOTS = ("clicks", "pitch", "meter", "tonal", "comparisons")
MAX_SELECTED_BYTES = 40_000_000
AUTOMATIC_REVIEW_SETTINGS = {"duration_difference_minimum_pulses": .25,
    "motif_offset_minimum_seconds": .03, "motif_offset_minimum_pulse_fraction": .15,
    "motif_match_window_maximum_seconds": .25, "motif_match_window_pulse_fraction": .45,
    "minimum_matched_motif_attacks": 3, "attack_density_difference_fraction": .25}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError(f"Oversized JSON artifact: {path.name}")
    with path.open("rb") as handle:
        encoded = handle.read(MAX_JSON_BYTES + 1)
    if len(encoded) > MAX_JSON_BYTES:
        raise ValueError(f"Oversized JSON artifact: {path.name}")
    value = json.loads(encoded)
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
    window = number(reference.get("match_window_seconds", min(.2, 30 / bpm / subdivision)), "match_window_seconds", .000001)
    tolerance = number(reference.get("tolerance_seconds", min(.03, window)), "tolerance_seconds", 0)
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
    # Compare one detector stream. Combining detectors would double-count attacks.
    detected_kinds = {event.get("kind") for event in events}
    attack_kind = next((kind for kind in ("superflux_attack_candidate", "spectral_flux_attack_candidate", "broadband_attack_candidate")
                        if kind in detected_kinds), "broadband_attack_candidate")
    for event in events:
        if event.get("kind") != attack_kind:
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
            "attack_detector": attack_kind,
            "matching_method": "maximum_count_minimum_total_offset_monotonic_one_to_one", "matches": matches,
            "flags": sorted(flags, key=lambda item: (item["source_time_seconds"], item["kind"]))}


def lineage(payload: dict, original_hash: str | None, processed_hashes: dict[str, bool]) -> str:
    identity = payload.get("source", {}).get("sha256")
    if identity and identity in processed_hashes:
        return "post_denoise" if processed_hashes[identity] else "rejected_unverified_processed_artifact"
    if identity and identity == original_hash:
        return "preliminary_raw_source"
    return "rejected_source_mismatch"


def safe_artifact(run_dir: Path, selector: str) -> Path:
    """Reject aliases before resolving; selectors preserve explicit identities."""
    if not isinstance(selector, str) or not 1 <= len(selector) <= 1024:
        raise ValueError("Evidence selector must contain 1..1024 characters")
    parts = selector.split("/")
    if (Path(selector).is_absolute() or ":" in selector or "\\" in selector
            or not selector.endswith(".json") or any(not p or p.startswith(".") or ".partial" in p for p in parts)):
        raise ValueError("Evidence selector must be a safe run-relative JSON path")
    candidate = run_dir
    for part in parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError("Evidence selector cannot contain a symbolic link")
    if not candidate.is_file() or not candidate.resolve().is_relative_to(run_dir.resolve()):
        raise ValueError("Evidence selector must name an existing run-local regular file")
    return candidate


def digest_value(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def timing_status(manifest: dict, identity: str | None) -> str:
    outputs = manifest.get("output_sha256", {})
    if identity == manifest.get("source", {}).get("sha256") or identity == outputs.get("source.wav"):
        return "raw_recording_axis_detector_delay_unqualified"
    denoise = (manifest.get("dsp_latency", {}).get("denoise") or {})
    if (denoise.get("status") == "measured_and_compensated"
            and denoise.get("remaining_bulk_delay_samples") == 0):
        return "bulk_dsp_delay_compensated_detector_and_physical_sync_unverified"
    return "dsp_delay_uncalibrated"


def evidence_metadata(payload: dict) -> dict:
    analysis = payload.get("analysis") or {}
    coverage_keys = ("coverage_seconds", "coverage_fraction", "coverage_spans_audio_relative",
                     "coverage_spans_source_timeline", "sampling", "frame_samples", "frame_seconds", "hop_seconds")
    result = {key: payload.get(key) for key in ("status", "confidence_kind", "identity_status", "time_signature",
        "tonic", "mode", "summary", "interpretation", "pitch_context", "feature_context", "requires_expected_intent", "performance_grade")}
    result["coverage"] = {key: analysis.get(key) for key in coverage_keys}
    result["comparison_count"] = len(payload["comparisons"]) if isinstance(payload.get("comparisons"), list) else None
    result["flag_count"] = len(payload["flags"]) if isinstance(payload.get("flags"), list) else None
    if len(json.dumps(result, allow_nan=False).encode()) > 64_000:
        raise ValueError("metadata_limit")
    return result


def select_evidence(run_dir: Path, manifest: dict, selectors: dict | None) -> tuple[dict, dict, dict, dict]:
    selectors = selectors or {}
    if not isinstance(selectors, dict) or set(selectors) - set(EVIDENCE_SLOTS):
        raise ValueError("Unknown evidence selector slot")
    paths = {slot: safe_artifact(run_dir, value) for slot, value in selectors.items()}
    if sum(path.stat().st_size for path in paths.values()) > MAX_SELECTED_BYTES:
        raise ValueError("Selected evidence exceeds the 40 MB aggregate bound")
    original = manifest["source"]["sha256"]
    manifest_hash = sha256(run_dir / "manifest.json")
    rows, verified, run_hashes, external_hashes = {}, {}, {}, {}
    for slot in EVIDENCE_SLOTS:
        row = {"status": "not_selected", "selector": selectors.get(slot), "artifact_sha256": None,
               "payload_status": None, "analysis_input_sha256": None, "analysis_lineage": None,
               "timing_status": None, "metadata": None, "upstream_hashes": {}, "external_context_hashes": {},
               "settings_sha256": None, "settings_binding_kind": None, "manifest_binding_kind": None,
               "producer_worker_sha256": None, "producer_worker_status": "not_recorded"}
        rows[slot] = row
        if slot not in paths:
            continue
        path = paths[slot]
        try:
            before = sha256(path)
            row["artifact_sha256"] = before
            if selectors[slot] in ("dag.json", "flags.json", "markers.json", "manifest.json", "analysis.json", "phrases.json"):
                raise ValueError("incompatible_artifact_type")
            payload = load(path)
            if type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
                raise ValueError("schema_version")
            for key in ("source", "provenance", "source_lineage", "lineage", "analysis", "instrument_context", "settings", "artifact_hashes"):
                if payload.get(key) is not None and not isinstance(payload[key], dict):
                    raise ValueError("invalid_metadata_shape")
            compatible = {"clicks": isinstance(payload.get("events"), list) and "identity_status" in payload,
                "pitch": payload.get("tool") == "pitch", "meter": "time_signature" in payload,
                "tonal": payload.get("tool") == "tonal",
                "comparisons": isinstance(payload.get("comparisons"), list) and isinstance(payload.get("flags"), list)}
            if not compatible[slot]:
                raise ValueError("incompatible_artifact_type")
            row["payload_status"] = payload.get("status")
            source = payload.get("source") or {}
            provenance = payload.get("provenance") or {}
            canonical_parent = payload.get("lineage") or {}
            parent = payload.get("source_lineage") or canonical_parent
            inputs = {v for v in (source.get("sha256"), payload.get("analysis_input_sha256"),
                      provenance.get("analyzed_input_sha256"), parent.get("analyzed_input_sha256"),
                      canonical_parent.get("input_sha256")) if v is not None}
            if len(inputs) != 1 or not all(digest_value(value) for value in inputs):
                raise ValueError("analysis_input_identity")
            identity = next(iter(inputs))
            row["analysis_input_sha256"] = identity
            originals = [value for value in (payload.get("source_sha256"), payload.get("original_source_sha256"),
                         provenance.get("original_source_sha256"), parent.get("original_source_sha256")) if value is not None]
            if any(value != original for value in originals) or (not originals and identity != original):
                raise ValueError("original_source_identity")
            upstream = dict(payload.get("artifact_hashes") or {})
            for field, name in (("analysis_sha256", "analysis.json"), ("manifest_sha256", "manifest.json")):
                if provenance.get(field) is not None:
                    if name in upstream and upstream[name] != provenance[field]:
                        raise ValueError("inconsistent_upstream_hashes")
                    upstream[name] = provenance[field]
            if parent.get("manifest_sha256") is not None:
                if "manifest.json" in upstream and upstream["manifest.json"] != parent["manifest_sha256"]:
                    raise ValueError("inconsistent_manifest_hashes")
                upstream["manifest.json"] = parent["manifest_sha256"]
            row["manifest_binding_kind"] = "producer_receipt_verified"
            if "manifest.json" not in upstream and slot == "pitch" and canonical_parent.get("status") == "verified_canonical_derivative":
                claimed_pcm = canonical_parent.get("canonical_pcm") or {}
                current_pcm = manifest.get("pcm") or {}
                pcm_keys = ("sample_rate", "channels", "sample_count")
                if (not all(key in claimed_pcm and claimed_pcm[key] == current_pcm.get(key) for key in pcm_keys)
                        or canonical_parent.get("input_sha256") != identity
                        or canonical_parent.get("original_source_sha256") != original):
                    raise ValueError("canonical_pcm_binding")
                # This verifies current compatibility, not a missing producer receipt.
                upstream["manifest.json"] = manifest_hash
                row["manifest_binding_kind"] = "derived_current_canonical_pcm_not_producer_manifest_hash"
            if upstream.get("manifest.json") != manifest_hash:
                raise ValueError("missing_or_stale_manifest_binding")
            row["upstream_hashes"] = upstream
            for name, expected in upstream.items():
                upstream_path = safe_artifact(run_dir, name)
                if not digest_value(expected) or sha256(upstream_path) != expected:
                    raise ValueError("stale_upstream")
            matches = [name for name in ("source.wav", "denoised.wav", "cleaned.wav")
                       if manifest.get("output_sha256", {}).get(name) == identity]
            if identity != original and not matches:
                raise ValueError("unrelated_analysis_input")
            for name in matches:
                media_path = run_dir / name
                if media_path.is_symlink() or not media_path.is_file() or sha256(media_path) != identity:
                    raise ValueError("modified_analysis_media")
            if matches and manifest.get("timeline", {}).get("no_time_stretch") is not True:
                raise ValueError("missing_source_time_mapping")
            expected_start = manifest.get("timeline", {}).get("audio_start_seconds", 0)
            claimed_starts = [value for value in (parent.get("original_audio_start_seconds"),
                (payload.get("timeline") or {}).get("audio_stream_start_seconds"),
                source.get("audio_stream_start_seconds"),
                (provenance.get("timeline") or {}).get("audio_stream_start_seconds")) if value is not None]
            if any(abs(number(value, "selected source timeline") - number(expected_start, "manifest source timeline")) > 1e-9 for value in claimed_starts):
                raise ValueError("source_time_mapping")
            row["analysis_lineage"] = "post_denoise" if any(name in ("denoised.wav", "cleaned.wav") for name in matches) else "preliminary_raw_source"
            row["timing_status"] = timing_status(manifest, identity)
            if slot in ("clicks", "pitch") and identity != original:
                allowed = ("hash_bound_run_derivative", "verified_canonical_derivative") if slot == "pitch" else ("hash_bound_run_derivative",)
                if parent.get("status") not in allowed or parent.get("original_source_sha256") != original:
                    raise ValueError("missing_derivative_lineage")
            if slot == "meter" and "analysis.json" not in upstream:
                raise ValueError("missing_analysis_binding")
            if slot in ("tonal", "comparisons") and "analysis.json" not in upstream:
                raise ValueError("missing_analysis_binding")
            settings = payload.get("settings")
            if settings is None:
                settings = payload.get("analysis", {"limits": payload.get("limits"), "thresholds": payload.get("thresholds")})
            computed_settings = hashlib.sha256(json.dumps(settings, sort_keys=True, allow_nan=False).encode()).hexdigest()
            if payload.get("settings_sha256") is not None and payload["settings_sha256"] != computed_settings:
                raise ValueError("settings_hash")
            row["settings_sha256"] = computed_settings
            row["settings_binding_kind"] = "producer_receipt_verified" if payload.get("settings_sha256") else "derived_from_selected_payload_not_producer_receipt"
            row["producer_worker_sha256"] = provenance.get("worker_sha256")
            row["producer_worker_status"] = "reported_not_current_code_reverified" if provenance.get("worker_sha256") else "not_recorded"
            tuning_hash = (payload.get("instrument_context") or {}).get("tuning_metadata_sha256")
            if tuning_hash is not None:
                registry = ROOT / "program/instrument.json"
                if not digest_value(tuning_hash) or not registry.is_file() or sha256(registry) != tuning_hash:
                    raise ValueError("stale_instrument_context")
                row["external_context_hashes"] = {"program/instrument.json": tuning_hash}
            row["metadata"] = evidence_metadata(payload)
            if slot == "comparisons":
                selected_comparison_flags(row, payload)
            if sha256(path) != before:
                raise ValueError("artifact_changed_during_read")
            row["status"] = "verified"
            verified[slot] = payload
            run_hashes[selectors[slot]] = before
            run_hashes.update(upstream)
            # Include PCM identities as graph inputs, not silently trusted metadata.
            run_hashes.update({name: identity for name in matches})
            external_hashes.update(row["external_context_hashes"])
        except (ValueError, TypeError, KeyError, OSError) as exc:
            reason = str(exc)
            known = {"incompatible_artifact_type", "schema_version", "analysis_input_identity", "original_source_identity",
                "inconsistent_upstream_hashes", "inconsistent_manifest_hashes", "missing_or_stale_manifest_binding", "stale_upstream",
                "unrelated_analysis_input", "modified_analysis_media", "missing_derivative_lineage", "missing_analysis_binding",
                "settings_hash", "stale_instrument_context", "metadata_limit", "artifact_changed_during_read"}
            known.update(("missing_source_time_mapping", "source_time_mapping"))
            known.add("canonical_pcm_binding")
            known.add("invalid_metadata_shape")
            row["status"] = "rejected_" + (reason if reason in known else "invalid_payload_or_upstream")
            row["metadata"] = None
    return rows, verified, run_hashes, external_hashes


def selected_comparison_flags(row: dict, payload: dict) -> list[dict]:
    candidates = payload.get("flags", [])
    if not isinstance(candidates, list) or len(candidates) > MAX_EVENTS:
        raise ValueError("Selected comparison flags must contain at most 20000 candidates")
    flags = []
    for item in candidates:
        if not isinstance(item, dict) or item.get("status") != "needs_review" or item.get("performance_issue_confirmed") is not False:
            raise ValueError("Selected comparison flags must remain unconfirmed review candidates")
        start = number(item.get("source_time_seconds"), "selected flag source start")
        end = number(item.get("end_seconds", start), "selected flag source end")
        if end < start:
            raise ValueError("Selected comparison flag end precedes start")
        flags.append({**item, "selected_evidence_slot": "comparisons", "selected_artifact": row["selector"],
            "selected_artifact_sha256": row["artifact_sha256"], "timing_status": row["timing_status"]})
    return flags


def archive_current(run_dir: Path) -> str | None:
    """Preserve prior derived presentation state before replacing DAG/flags."""
    names = ("dag.json", "flags.json", "report.html", "markers.json", "markers.csv")
    contents = {}
    remaining = 64_000_000
    for name in names:
        path = run_dir / name
        if path.is_symlink():
            raise ValueError("Cannot archive a symlinked graph/report artifact")
        if path.is_file():
            if path.stat().st_size > remaining:
                raise ValueError("Graph history snapshot exceeds 64 MB")
            with path.open("rb") as handle:
                content = handle.read(remaining + 1)
            if len(content) > remaining:
                raise ValueError("Graph history snapshot exceeds 64 MB")
            contents[name] = content
            remaining -= len(content)
    if not contents:
        return None
    if sum(len(content) for content in contents.values()) > 64_000_000:
        raise ValueError("Graph history snapshot exceeds 64 MB")
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in contents.items()}
    snapshot = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    folder = run_dir / "graph-history" / snapshot
    if (run_dir / "graph-history").is_symlink() or folder.is_symlink():
        raise ValueError("Graph history cannot contain symbolic links")
    folder.mkdir(parents=True, exist_ok=True)
    receipt = {"schema_version": 1, "status": "prior_derived_snapshot_not_revalidated", "artifact_hashes": hashes,
               "authority": "R-HOOK-CONVERGENCE-20261004/R-N13; operator-authorized graph rerun"}
    contents["receipt.json"] = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    for name, content in contents.items():
        target = folder / name
        if target.is_symlink():
            raise ValueError("History artifact cannot be a symbolic link")
        try:
            with target.open("xb") as handle:
                os.chmod(target, 0o600)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            if target.read_bytes() != content:
                raise ValueError("Existing graph history is inconsistent; preserve and inspect it")
    if any(sha256(run_dir / name) != expected for name, expected in hashes.items()):
        raise ValueError("Prior graph/report changed during archive; rerun against stable artifacts")
    return folder.relative_to(run_dir).as_posix()


def automatic_phrase_flags(phrases: dict, source_start: float) -> list[dict]:
    """Discover review spans and relative recurrence differences without a score.

    Segmentation and self-consistency compare observable patterns, not intent.
    The initial proposal remains hypothetical even with high similarity.
    """
    observations = phrases.get("observations", {})
    result = []

    def add(kind, start, end, evidence, confidence="unvalidated_automatic_phrase_candidate"):
        start = number(start, "automatic phrase start", 0)
        end = number(end, "automatic phrase end", 0)
        if end < start:
            raise ValueError("Automatic phrase end precedes start")
        result.append({"kind": kind, "audio_relative_seconds": start,
            "source_time_seconds": source_start + start, "end_seconds": source_start + end,
            "confidence": confidence, "status": "needs_review", "evidence": evidence,
            "performance_issue_confirmed": False, "requires_expected_intent": False})

    segments = observations.get("segment_candidates", [])
    recurrences = observations.get("recurrence_candidates", [])
    bars = observations.get("bar_proxy_candidates", [])
    if not all(isinstance(items, list) for items in (segments, recurrences, bars)) or len(segments) + len(recurrences) + len(bars) > 5000:
        raise ValueError("Automatic phrase context must contain at most 5000 segment/recurrence candidates")
    for span in observations.get("proposed_review_spans", []):
        if span.get("kind") == "multifeature_recurrence_candidate" and recurrences:
            continue  # The full recurrence below carries both motifs and lineage.
        add(span.get("kind", "phrase_review_candidate"), span.get("start_seconds"), span.get("end_seconds"), span)
    for segment in segments:
        add(segment.get("kind", "automatic_segment_review_candidate"), segment.get("start_seconds"), segment.get("end_seconds"),
            {**segment, "warning": "Unsupervised texture/rhythm boundary; bar identity, breakdown and musical intent remain review hypotheses."})
    for bar in bars:
        add("four_pulse_group_review_candidate", bar.get("start_seconds"), bar.get("end_seconds"),
            {**bar, "time_signature": None, "warning": "Four-pulse grouping is a navigation proxy; downbeat phase and musical bar/meter are not identified."},
            "navigation_proxy_not_confirmed_bar")
    for recurrence in recurrences:
        a = number(recurrence.get("first_start_seconds"), "recurrence first start", 0)
        b = number(recurrence.get("first_end_seconds"), "recurrence first end", 0)
        c = number(recurrence.get("second_start_seconds"), "recurrence second start", 0)
        d = number(recurrence.get("second_end_seconds"), "recurrence second end", 0)
        if not a < b <= c < d:
            raise ValueError("Recurrence spans must be ordered and nonoverlapping")
        evidence = {**recurrence, "comparison_basis": "within_take_pattern_self_consistency_not_expected_score",
                    "warning": "Repeated texture is a hypothesis; intentional variation, legato and segmentation error remain possible."}
        add("automatic_recurrence_review_candidate", c, d, evidence)
        pulse = recurrence.get("pulse_period_seconds")
        if pulse is None:
            continue
        pulse = number(pulse, "recurrence pulse period", .001)
        duration_difference = (d - c) - (b - a)
        if abs(duration_difference) / pulse > AUTOMATIC_REVIEW_SETTINGS["duration_difference_minimum_pulses"]:
            add("recurrence_duration_difference_review", c, d, {**evidence,
                "duration_difference_seconds": duration_difference, "duration_difference_pulses": duration_difference / pulse,
                "warning": "Loop/phrase duration differs; this does not prove skipped beats or a rushed phrase."})
        first = recurrence.get("first_onset_offsets_seconds")
        second = recurrence.get("second_onset_offsets_seconds")
        if first is None or second is None:
            continue
        if not isinstance(first, list) or not isinstance(second, list) or max(len(first), len(second)) > 2000:
            raise ValueError("Recurrence onset motifs must be arrays with at most 2000 attacks")
        first = sorted(set(number(time, "first motif onset", 0) for time in first))
        second = sorted(set(number(time, "second motif onset", 0) for time in second))
        if any(time > b - a for time in first) or any(time > d - c for time in second):
            raise ValueError("Recurrence motif onset lies outside its phrase span")
        window = min(AUTOMATIC_REVIEW_SETTINGS["motif_match_window_maximum_seconds"],
                     pulse * AUTOMATIC_REVIEW_SETTINGS["motif_match_window_pulse_fraction"])
        pairs, _, _ = match_onsets(first, second, window)
        if len(pairs) >= AUTOMATIC_REVIEW_SETTINGS["minimum_matched_motif_attacks"]:
            offsets = [second[j] - first[i] for i, j in pairs]
            threshold = max(AUTOMATIC_REVIEW_SETTINGS["motif_offset_minimum_seconds"],
                            pulse * AUTOMATIC_REVIEW_SETTINGS["motif_offset_minimum_pulse_fraction"])
            for (i, j), offset in zip(pairs, offsets):
                if abs(offset) > threshold:
                    add("recurrence_motif_timing_difference_review", c + second[j], c + second[j],
                        {"first_phrase_start_seconds": a, "second_phrase_start_seconds": c,
                         "first_motif_attack_seconds": first[i], "second_motif_attack_seconds": second[j],
                         "relative_difference_seconds": offset, "relative_difference_pulses": offset / pulse,
                         "recording_latency": "constant_offset_cancels_in_relative_comparison_detector_and_boundary_bias_unknown",
                         "warning": "Within-take attack alignment differs; intentional variation or detection error remains possible."},
                        "unvalidated_relative_motif_difference")
        if max(len(first), len(second)) >= 3 and abs(len(first) - len(second)) / max(len(first), len(second)) > AUTOMATIC_REVIEW_SETTINGS["attack_density_difference_fraction"]:
            add("recurrence_attack_density_difference_review", c, d,
                {**evidence, "first_detected_attack_count": len(first), "second_detected_attack_count": len(second),
                 "warning": "Attack density differs; legato, masking, clicks or intended variation can explain it. No missing/extra note inference."})
    # Older proposed spans can duplicate a new segmentation/recurrence marker.
    unique = {}
    for item in result:
        key = (item["kind"], item["source_time_seconds"], item["end_seconds"])
        unique[key] = item
    return list(unique.values())


def build(run_dir: Path, reference_path: Path | None = None, evidence_selectors: dict | None = None) -> tuple[dict, dict]:
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
    selected_rows, selected_payloads, selected_hashes, external_hashes = select_evidence(run_dir, manifest, evidence_selectors)
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
                row["timing_status"] = timing_status(manifest, row["analysis_input_sha256"])
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
    automatic_flags = automatic_phrase_flags(phrases, start)
    performance["flags"].extend(automatic_flags)
    if "comparisons" in selected_payloads:
        performance["flags"].extend(selected_comparison_flags(selected_rows["comparisons"], selected_payloads["comparisons"]))
    if automatic_flags and not (reference and reference.get("approved") is True):
        performance["status"] = "automatic_phrase_review_candidates"
    notes = payloads.get("notes", {}).get("interpretation", {})
    flags = {"schema_version": 1, "source_sha256": original_hash, "analysis_lineage": analysis_state,
             "timing_status": timing_status(manifest, analysis.get("source", {}).get("sha256")),
             "evidence_artifacts": {slot: {"selector": row["selector"], "sha256": row["artifact_sha256"]}
                                    for slot, row in selected_rows.items() if row["status"] == "verified"},
             "timeline": {"audio_start_seconds": start, "axis": "original_source_stream_timestamps_seconds"},
             "reference": reference_receipt, "musical_context": {"tonic": notes.get("tonic"), "mode": notes.get("mode"),
                 "status": "nullable_experimental_context_not_confirmed_intent"},
             **performance, "automatic_review_settings": AUTOMATIC_REVIEW_SETTINGS,
             "performance_grade": "not_graded_human_review_required",
             "limitations": ["Automatic segmentation and self-consistency differences need no intended-score reference; they remain hypotheses.",
                "Approved-score comparisons are mixture transient mismatches, not confirmed note mistakes.",
                "Texture/envelope recurrence does not establish identical notes or tonal identity.", "Raw-source analysis remains preliminary until post-denoise analysis is recorded.",
                "32 Hz fundamentals and intentional distortion are musical content, not automatic noise targets."]}
    flags["flags"].sort(key=lambda item: (item["source_time_seconds"], item["kind"]))
    encoded = json.dumps(flags, indent=2, allow_nan=False) + "\n"
    flags_hash = hashlib.sha256(encoded.encode()).hexdigest()
    artifact_hashes.update(selected_hashes)
    artifact_hashes["flags.json"] = flags_hash
    for row in stage_rows:
        if row["id"] == "flags":
            row.update(status=performance["status"], artifact_sha256=flags_hash,
                       settings={"reference_sha256": reference_receipt["sha256"], "analysis_lineage": analysis_state,
                                 "automatic_review": AUTOMATIC_REVIEW_SETTINGS})
        row["settings_sha256"] = hashlib.sha256(json.dumps(row["settings"], sort_keys=True, allow_nan=False).encode()).hexdigest()
    by_id = {row["id"]: row for row in stage_rows}
    for row in stage_rows:
        row["dependency_artifact_hashes"] = {key: by_id[key]["artifact_sha256"] for key in row["depends_on"]}
    graph = {"schema_version": 1, "kind": "artifact_provenance_DAG_not_an_execution_engine", "source_sha256": original_hash,
             "registry_sha256": sha256(registry_path), "artifact_hashes": artifact_hashes,
             "reference": reference_receipt, "stages": stage_rows, "flags_sha256": flags_hash,
             "selected_evidence": selected_rows, "external_context_hashes": external_hashes,
             "timing_status": flags["timing_status"],
             "instrument_context": registry["instrument_context"], "listening_accepted": False,
             "report_binding": "report_stage_is_prior_snapshot_not_validated_input_to_avoid_summary_self_reference"}
    for name, expected in artifact_hashes.items():
        if name != "flags.json" and sha256(run_dir / name) != expected:
            raise ValueError("Graph input changed during evaluation; rerun against stable artifacts")
    for name, expected in external_hashes.items():
        if sha256(ROOT / name) != expected:
            raise ValueError("Instrument context changed during graph evaluation")
    return graph, flags


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--reference", type=Path)
    for slot in EVIDENCE_SLOTS:
        parser.add_argument(f"--{slot}-artifact")
    args = parser.parse_args()
    try:
        directory = args.run_dir.expanduser().resolve(strict=True)
        reference = args.reference.expanduser().resolve(strict=True) if args.reference else None
        if reference in {directory / "flags.json", directory / "dag.json"}:
            raise ValueError("Reference cannot be an output artifact")
        selectors = {slot: getattr(args, f"{slot}_artifact") for slot in EVIDENCE_SLOTS if getattr(args, f"{slot}_artifact") is not None}
        graph, flags = build(directory, reference, selectors)
        snapshot = archive_current(directory)
        graph["prior_snapshot"] = snapshot
        atomic_write(directory / "flags.json", json.dumps(flags, indent=2, allow_nan=False) + "\n")
        atomic_write(directory / "dag.json", json.dumps(graph, indent=2, allow_nan=False) + "\n")
        print(json.dumps({"dag_json": str(directory / "dag.json"), "flags_json": str(directory / "flags.json"),
                          "status": flags["status"], "flag_count": len(flags["flags"]), "prior_snapshot": snapshot}))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"dag: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
