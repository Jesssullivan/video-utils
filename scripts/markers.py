#!/usr/bin/env python3
"""Export generic review markers in original-source seconds; no editor import claim."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
import sys

from dag import atomic_write, load, number, sha256

COLUMNS = ["source_time_seconds", "end_seconds", "name", "confidence", "status", "evidence"]


def build(run_dir: Path) -> tuple[dict, str]:
    flags_path = run_dir / "flags.json"
    flags = load(flags_path)
    manifest = load(run_dir / "manifest.json")
    source_hash = manifest.get("source", {}).get("sha256")
    if not source_hash or flags.get("source_sha256") != source_hash:
        raise ValueError("Marker source hash must match the run manifest")
    graph_path = run_dir / "dag.json"
    if graph_path.is_file():
        graph = load(graph_path)
        if graph.get("source_sha256") != source_hash or graph.get("flags_sha256") != sha256(flags_path):
            raise ValueError("DAG flags hash is stale or source identity differs; rerun dag.py")
    items = flags.get("flags", [])
    if not isinstance(items, list) or len(items) > 50_000:
        raise ValueError("Marker input must contain at most 50000 flags")
    markers = []
    for item in items:
        start = number(item.get("source_time_seconds"), "marker source_time_seconds")
        end = number(item.get("end_seconds", start), "marker end_seconds")
        if end < start:
            raise ValueError("Marker end precedes its start")
        markers.append({"source_time_seconds": start, "end_seconds": end,
                        "name": str(item.get("kind", "review_candidate"))[:256],
                        "confidence": item.get("confidence", "unknown"),
                        "status": item.get("status", "needs_review"), "evidence": item.get("evidence", {})})
    markers.sort(key=lambda item: (item["source_time_seconds"], item["name"]))
    probe = manifest.get("source", {}).get("probe", {})
    video = probe.get("video") or {}
    result = {"schema_version": 1, "format": "generic_review_markers_seconds", "source_sha256": source_hash,
              "flags_sha256": sha256(flags_path), "timeline": flags.get("timeline"),
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
        writer.writerow({**marker, "evidence": json.dumps(marker["evidence"], ensure_ascii=False, allow_nan=False)})
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
