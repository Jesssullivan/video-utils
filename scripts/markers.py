#!/usr/bin/env python3
"""Export generic review markers in original-source seconds; no editor import claim."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
import re
import sys

from dag import ROOT, atomic_write, load, number, sha256

COLUMNS = ["source_time_seconds", "end_seconds", "name", "confidence", "status", "evidence"]
SELECTED_SLOTS = {"clicks", "pitch", "meter", "tonal", "comparisons"}


def local_artifact(root: Path, name: str) -> Path:
    """Resolve a lexical run-relative file without following symbolic links."""
    if (not isinstance(name, str) or not name or "\\" in name or ":" in name
            or "\0" in name or Path(name).is_absolute()
            or any(part in ("", ".", "..") for part in name.split("/"))):
        raise ValueError("DAG artifact path must be a local filename or nested relative path")
    root = root.resolve()
    candidate = root
    for part in name.split("/"):
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError(f"DAG symbolic-link artifact is rejected: {name}")
    if not candidate.is_file() or not candidate.resolve().is_relative_to(root):
        raise ValueError(f"DAG artifact missing or outside run directory: {name}")
    return candidate


def checked_hashes(root: Path, hashes: dict, tracked: dict[Path, str]) -> None:
    if not isinstance(hashes, dict) or len(hashes) > 5000:
        raise ValueError("DAG artifact hashes must be an object with at most 5000 entries")
    for name, expected in hashes.items():
        path = local_artifact(root, name)
        if (not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected)
                or sha256(path) != expected or (path in tracked and tracked[path] != expected)):
            raise ValueError(f"DAG upstream artifact is stale: {name}; rerun dag.py")
        tracked[path] = expected


def selected_bindings(graph: dict, flags: dict) -> dict:
    """Bind selected flags to verified graph rows without importing candidates."""
    selected = graph.get("selected_evidence", {})
    bindings = flags.get("evidence_artifacts", {})
    if (not isinstance(selected, dict) or set(selected) - SELECTED_SLOTS
            or not isinstance(bindings, dict) or set(bindings) - SELECTED_SLOTS):
        raise ValueError("Invalid selected-evidence slots in marker graph")
    hashes = graph.get("artifact_hashes", {})
    external = graph.get("external_context_hashes", {})
    for slot, row in selected.items():
        if not isinstance(row, dict):
            raise ValueError("Selected-evidence row must be an object")
        if row.get("status") != "verified":
            if slot in bindings:
                raise ValueError("Marker evidence binding references an unverified selection")
            continue
        selector, digest = row.get("selector"), row.get("artifact_sha256")
        if not isinstance(selector, str) or hashes.get(selector) != digest:
            raise ValueError("Verified selection is missing its graph artifact hash")
        binding = bindings.get(slot)
        if not isinstance(binding, dict) or binding != {"selector": selector, "sha256": digest}:
            raise ValueError("Marker selected-evidence binding differs from the graph")
        for key, values in (("upstream_hashes", hashes), ("external_context_hashes", external)):
            context = row.get(key, {})
            if not isinstance(context, dict) or any(values.get(name) != expected for name, expected in context.items()):
                raise ValueError("Selected-evidence context is absent or differs from graph hashes")
    if any(slot not in selected or selected[slot].get("status") != "verified" for slot in bindings):
        raise ValueError("Marker evidence binding references an unverified selection")
    for flag in flags.get("flags", []):
        if not isinstance(flag, dict):
            raise ValueError("Marker flag must be an object")
        slot = flag.get("selected_evidence_slot")
        if slot is not None:
            binding = bindings.get(slot) if isinstance(slot, str) else None
            if (not binding or flag.get("selected_artifact") != binding["selector"]
                    or flag.get("selected_artifact_sha256") != binding["sha256"]):
                raise ValueError("Selected marker flag does not match verified graph evidence")
            if flag.get("performance_issue_confirmed") is True or flag.get("status", "needs_review") != "needs_review":
                raise ValueError("Selected markers must remain unconfirmed review hypotheses")
    return bindings


def build(run_dir: Path) -> tuple[dict, str]:
    run_dir = run_dir.resolve()
    flags_path = local_artifact(run_dir, "flags.json")
    manifest_path = local_artifact(run_dir, "manifest.json")
    input_hashes = {path: sha256(path) for path in (flags_path, manifest_path)}
    flags = load(flags_path)
    manifest = load(manifest_path)
    source_hash = manifest.get("source", {}).get("sha256")
    if not source_hash or flags.get("source_sha256") != source_hash:
        raise ValueError("Marker source hash must match the run manifest")
    graph_path = run_dir / "dag.json"
    bindings = {}
    if graph_path.exists() or graph_path.is_symlink():
        graph_path = local_artifact(run_dir, "dag.json")
        input_hashes[graph_path] = sha256(graph_path)
        graph = load(graph_path)
        if graph.get("source_sha256") != source_hash or graph.get("flags_sha256") != sha256(flags_path):
            raise ValueError("DAG flags hash is stale or source identity differs; rerun dag.py")
        checked_hashes(run_dir, graph.get("artifact_hashes", {}), input_hashes)
        external = graph.get("external_context_hashes", {})
        if not isinstance(external, dict) or set(external) - {"program/instrument.json"}:
            raise ValueError("Only the repository instrument registry is supported external context")
        checked_hashes(ROOT, external, input_hashes)
        bindings = selected_bindings(graph, flags)
    elif flags.get("evidence_artifacts") or any(isinstance(item, dict) and "selected_evidence_slot" in item for item in flags.get("flags", [])):
        raise ValueError("Selected marker evidence requires a verified DAG")
    items = flags.get("flags", [])
    if not isinstance(items, list) or len(items) > 50_000:
        raise ValueError("Marker input must contain at most 50000 flags")
    markers, seen = [], set()
    for item in items:
        start = number(item.get("source_time_seconds"), "marker source_time_seconds")
        end = number(item.get("end_seconds", start), "marker end_seconds")
        if end < start:
            raise ValueError("Marker end precedes its start")
        marker = {"source_time_seconds": start, "end_seconds": end,
                        "name": str(item.get("kind", "review_candidate"))[:256],
                        "confidence": item.get("confidence", "unknown"),
                        "status": item.get("status", "needs_review"), "evidence": item.get("evidence", {})}
        for key in ("selected_evidence_slot", "selected_artifact", "selected_artifact_sha256"):
            if key in item:
                marker[key] = item[key]
        fingerprint = json.dumps(marker, sort_keys=True, allow_nan=False)
        if fingerprint not in seen:
            seen.add(fingerprint)
            markers.append(marker)
    markers.sort(key=lambda item: (item["source_time_seconds"], item["name"]))
    probe = manifest.get("source", {}).get("probe", {})
    video = probe.get("video") or {}
    result = {"schema_version": 1, "format": "generic_review_markers_seconds", "source_sha256": source_hash,
              "flags_sha256": sha256(flags_path), "timeline": flags.get("timeline"),
              "evidence_artifacts": bindings,
              "frame_rate": {"average_rational": video.get("avg_frame_rate"), "nominal_rational": video.get("r_frame_rate"),
                             "frame_indices": None, "status": "not_converted_variable_rate_and_editor_origin_require_validation"},
              "editor_import": {"final_cut_pro": "unsupported_pending_adapter_and_host_validation", "davinci_resolve": "unsupported_pending_adapter_and_host_validation"},
              "markers": markers, "limitations": ["Generic CSV/JSON is a review exchange format, not validated native editor import.",
                  "Times use original source stream timestamps; an editor may reset clip origin or conform frame rate.",
                  "Flags remain hypotheses; this exporter does not confirm musical mistakes."]}
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=COLUMNS)
    writer.writeheader()
    for marker in markers:
        writer.writerow({**{key: marker[key] for key in COLUMNS}, "evidence": json.dumps(marker["evidence"], ensure_ascii=False, allow_nan=False)})
    for path, expected in input_hashes.items():
        root = run_dir if path.is_relative_to(run_dir) else ROOT.resolve()
        local_artifact(root, path.relative_to(root).as_posix())
        if sha256(path) != expected:
            raise ValueError("Marker input changed during export preparation; rerun against stable artifacts")
    return result, stream.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    try:
        directory = args.run_dir.expanduser().resolve(strict=True)
        payload, encoded_csv = build(directory)
        atomic_write(directory / "markers.json", json.dumps(payload, indent=2, allow_nan=False) + "\n")
        atomic_write(directory / "markers.csv", encoded_csv)
        print(json.dumps({"markers_json": str(directory / "markers.json"), "markers_csv": str(directory / "markers.csv"),
                          "marker_count": len(payload["markers"]), "editor_import": "not_validated"}))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"markers: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
