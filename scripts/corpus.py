#!/usr/bin/env python3
"""Validate bounded, explicitly attributed local review metadata; never read audio."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE = 1_000_000
MAX_TOTAL = 16_000_000
MAX_SUMMARY_BYTES = 1_000_000
SHA = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
CATEGORIES = {"rhythm", "phrase", "tone", "noise", "other"}
STATES = {"needs_review", "accepted_observation", "dismissed_candidate"}


class CorpusError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise CorpusError(code)


def fields(value, expected, code):
    require(isinstance(value, dict) and set(value) == set(expected), code)


def text(value, limit=120):
    require(isinstance(value, str) and 0 < len(value.strip()) <= limit, "invalid_text")
    return value


def identifier(value):
    require(isinstance(value, str) and IDENTIFIER.fullmatch(value), "invalid_identifier")
    return value


def fingerprint(value):
    require(isinstance(value, str) and SHA.fullmatch(value), "invalid_sha256")
    return value


def integer(value, minimum=0):
    require(type(value) is int and value >= minimum, "invalid_revision")
    return value


def number(value):
    require(type(value) in (int, float), "invalid_source_seconds")
    try:
        value = float(value)
    except OverflowError as exc:
        raise CorpusError("invalid_source_seconds") from exc
    require(math.isfinite(value), "invalid_source_seconds")
    return value


def timestamp(value):
    require(isinstance(value, str) and len(value) <= 40, "invalid_review_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CorpusError("invalid_review_timestamp") from exc
    require(parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed),
            "review_timestamp_must_be_utc")
    return parsed


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "duplicate_json_key")
        value[key] = item
    return value


class Metadata:
    """Dirfd traversal and bounded reads hold each file's byte receipt together."""
    def __init__(self, root):
        root = Path(root)
        require(root.is_dir() and not root.is_symlink(), "invalid_corpus_root")
        self.root = root.resolve(strict=True)
        self.total = 0
        self.cache = {}

    def relative(self, name):
        require(isinstance(name, str) and 0 < len(name) <= 4096 and "\\" not in name,
                "unsafe_metadata_path")
        path = PurePosixPath(name)
        require(not path.is_absolute() and all(part not in (".", "..") for part in name.split("/"))
                and ":" not in name and "\x00" not in name, "unsafe_metadata_path")
        return path

    def read(self, name, expected=None):
        path = self.relative(name)
        if name in self.cache:
            value, digest = self.cache[name]
        else:
            descriptors = []
            try:
                parent = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                descriptors.append(parent)
                for component in path.parts[:-1]:
                    parent = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                     dir_fd=parent)
                    descriptors.append(parent)
                fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                descriptors.append(fd)
                before = os.fstat(fd)
                require(stat.S_ISREG(before.st_mode), "metadata_not_regular_file")
                require(before.st_size <= MAX_FILE, "metadata_file_limit")
                self.total += before.st_size
                require(self.total <= MAX_TOTAL, "metadata_total_limit")
                chunks, size = [], 0
                while True:
                    chunk = os.read(fd, min(65536, MAX_FILE + 1 - size))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    require(size <= MAX_FILE, "metadata_file_limit")
                after = os.fstat(fd)
                require((before.st_ino, before.st_size, before.st_mtime_ns) ==
                        (after.st_ino, after.st_size, after.st_mtime_ns) and size == before.st_size,
                        "metadata_changed_during_read")
                raw = b"".join(chunks)
                digest = hashlib.sha256(raw).hexdigest()
                value = json.loads(raw, object_pairs_hook=unique_object,
                                   parse_constant=lambda _: (_ for _ in ()).throw(CorpusError("nonfinite_json")))
                require(isinstance(value, dict), "metadata_object_required")
                self.cache[name] = value, digest
            except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
                raise CorpusError("metadata_unreadable_or_unsafe") from exc
            finally:
                for fd in reversed(descriptors):
                    os.close(fd)
        if expected is not None:
            require(digest == fingerprint(expected), "metadata_hash_mismatch")
        return value, digest


def source_bounds(manifest):
    timeline, pcm = manifest.get("timeline"), manifest.get("pcm")
    require(isinstance(timeline, dict) and isinstance(pcm, dict), "source_timeline_required")
    # Unlike playback defaults, a corpus may not guess an unknown source origin.
    start = number(timeline.get("audio_start_seconds"))
    format_start = number(timeline.get("format_start_seconds"))
    duration = pcm.get("duration_seconds")
    if duration is None:
        count, rate = pcm.get("sample_count"), pcm.get("sample_rate")
        require(type(count) is int and count > 0 and type(rate) is int and rate > 0,
                "source_duration_required")
        duration = count / rate
    duration = number(duration)
    require(0 < duration <= 43200, "source_duration_limit")
    return min(start, format_start), start + duration


def source_identity(manifest):
    source = manifest.get("source")
    require(isinstance(source, dict), "manifest_source_required")
    return fingerprint(source.get("sha256"))


def annotations(store, source_hash, revision, bounds):
    require(store.get("schema_version") == 1 and type(store.get("schema_version")) is int,
            "invalid_annotation_schema")
    require(store.get("source_sha256") == source_hash, "annotation_source_mismatch")
    require(integer(store.get("revision")) == revision, "stale_annotation_revision")
    require(store.get("listening_acceptance") == "not_established", "invalid_acceptance_claim")
    items = store.get("annotations")
    require(isinstance(items, list) and len(items) <= 200, "annotation_count_limit")
    found = {}
    for item in items:
        require(isinstance(item, dict), "invalid_annotation")
        name = item.get("id")
        try:
            require(str(uuid.UUID(name)) == name, "invalid_annotation_id")
        except (ValueError, TypeError, AttributeError) as exc:
            raise CorpusError("invalid_annotation_id") from exc
        require(name not in found, "duplicate_annotation_id")
        start, end = number(item.get("source_start_seconds")), number(item.get("source_end_seconds"))
        require(bounds[0] <= start <= end <= bounds[1], "annotation_span_out_of_bounds")
        require(isinstance(item.get("category"), str) and item["category"] in CATEGORIES and
                isinstance(item.get("status"), str) and item["status"] in STATES, "invalid_annotation_state")
        text(item.get("note"), 4000)
        created_receipt = item.get("created_with")
        fields(created_receipt, ("manifest_sha256", "candidate_artifact_sha256"), "annotation_receipt_required")
        fingerprint(created_receipt["manifest_sha256"])
        if created_receipt["candidate_artifact_sha256"] is not None:
            fingerprint(created_receipt["candidate_artifact_sha256"])
        created = timestamp(item.get("created_at"))
        updated = timestamp(item.get("updated_at", item.get("created_at")))
        require(updated >= created, "annotation_timestamp_order")
        found[name] = item
    return found


def verify_annotation_receipt(item, manifest_hash, run, metadata, source_hash):
    receipt = item.get("updated_with", item.get("created_with"))
    fields(receipt, ("manifest_sha256", "candidate_artifact_sha256"), "annotation_receipt_required")
    require(receipt["manifest_sha256"] == manifest_hash, "stale_annotation_manifest")
    candidate = receipt["candidate_artifact_sha256"]
    if candidate is None:
        require(item.get("candidate_id") is None, "candidate_receipt_required")
        return None
    fingerprint(candidate)
    for filename in ("markers.json", "flags.json"):
        name = str(run / filename)
        # Missing optional siblings are allowed; unsafe or malformed siblings are not.
        full = metadata.root / name
        if not full.exists() and not full.is_symlink():
            continue
        payload, digest = metadata.read(name)
        if digest == candidate:
            require(payload.get("source_sha256") == source_hash, "candidate_source_mismatch")
            candidate_id = item.get("candidate_id")
            if candidate_id is not None:
                fingerprint(candidate_id)
                values = payload.get("markers", payload.get("flags", []))
                require(isinstance(values, list) and len(values) <= 50000, "invalid_candidate_collection")
                found = False
                for marker in values:
                    if not isinstance(marker, dict):
                        continue
                    try:
                        start = number(marker.get("source_time_seconds"))
                        end = number(marker.get("end_seconds", start))
                    except CorpusError:
                        continue
                    if end < start:
                        continue
                    # Identical source-time identity convention to review_server.Session.marker_items.
                    kind = str(marker.get("name", marker.get("kind", "review_candidate")))[:256]
                    identity = {"source_sha256": source_hash, "kind": kind, "start": start, "end": end}
                    if hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest() == candidate_id:
                        found = True
                        break
                require(found, "candidate_id_not_in_receipt")
            return {"path": name, "sha256": digest}
    raise CorpusError("stale_candidate_artifact")


def validate(path, root=ROOT):
    metadata = Metadata(root)
    path = Path(path).absolute()
    try:
        relative = str(path.relative_to(metadata.root))
    except ValueError as exc:
        raise CorpusError("manifest_outside_corpus_root") from exc
    corpus, corpus_hash = metadata.read(relative)
    fields(corpus, ("schema_version", "corpus_id", "revision", "units", "coverage", "reviewers", "sources"),
           "invalid_corpus_fields")
    require(type(corpus["schema_version"]) is int and corpus["schema_version"] == 1, "unsupported_corpus_schema")
    identifier(corpus["corpus_id"])
    integer(corpus["revision"], 1)
    require(corpus["units"] == "source_seconds", "source_seconds_units_required")
    require(corpus["coverage"] == "sparse_reviewed_spans", "sparse_coverage_required")
    reviewers = corpus["reviewers"]
    require(isinstance(reviewers, list) and 0 < len(reviewers) <= 100, "reviewer_count_limit")
    identities = {}
    for reviewer in reviewers:
        fields(reviewer, ("id", "identity"), "invalid_reviewer_fields")
        name = identifier(reviewer["id"])
        require(name not in identities, "duplicate_reviewer_id")
        identities[name] = text(reviewer["identity"], 400)
    sources = corpus["sources"]
    require(isinstance(sources, list) and 0 < len(sources) <= 100, "source_count_limit")
    seen_sources, seen_hashes, results, label_count = set(), set(), [], 0
    origin_counts = {"real_recording": 0, "synthetic_fixture": 0}
    for source in sources:
        fields(source, ("id", "origin", "source_sha256", "manifest", "annotations", "labels"), "invalid_source_fields")
        name = identifier(source["id"])
        require(name not in seen_sources, "duplicate_source_id")
        seen_sources.add(name)
        origin = source["origin"]
        require(isinstance(origin, str) and origin in origin_counts, "explicit_source_origin_required")
        source_hash = fingerprint(source["source_sha256"])
        require(source_hash not in seen_hashes, "duplicate_source_hash")
        seen_hashes.add(source_hash)
        origin_counts[origin] += 1
        mr, ar = source["manifest"], source["annotations"]
        fields(mr, ("path", "sha256"), "invalid_manifest_receipt")
        fields(ar, ("path", "sha256", "revision"), "invalid_store_receipt")
        run = metadata.relative(mr["path"]).parent
        require(metadata.relative(mr["path"]).name == "manifest.json" and
                metadata.relative(ar["path"]) == run / "review-annotations.json", "run_local_receipts_required")
        manifest, mh = metadata.read(mr["path"], mr["sha256"])
        require(source_identity(manifest) == source_hash, "manifest_source_mismatch")
        bounds = source_bounds(manifest)
        store, sh = metadata.read(ar["path"], ar["sha256"])
        rows = annotations(store, source_hash, integer(ar["revision"]), bounds)
        labels = source["labels"]
        require(isinstance(labels, list), "labels_list_required")
        label_count += len(labels)
        require(label_count <= 5000, "selected_label_count_limit")
        seen_labels, selected = set(), []
        for label in labels:
            fields(label, ("annotation_id", "reviewer_id", "reviewed_at", "source_start_seconds",
                           "source_end_seconds", "label", "certainty", "alternatives"), "invalid_label_fields")
            annotation_id, reviewer_id = label["annotation_id"], label["reviewer_id"]
            require(isinstance(annotation_id, str) and annotation_id in rows, "annotation_not_found")
            require(isinstance(reviewer_id, str) and reviewer_id in identities, "reviewer_not_found")
            key = annotation_id, reviewer_id
            require(key not in seen_labels, "duplicate_reviewer_label")
            seen_labels.add(key)
            item = rows[annotation_id]
            reviewed_at = timestamp(label["reviewed_at"])
            require(reviewed_at >= timestamp(item.get("updated_at", item["created_at"])), "review_predates_annotation")
            start, end = number(label["source_start_seconds"]), number(label["source_end_seconds"])
            require((start, end) == (item["source_start_seconds"], item["source_end_seconds"]), "label_span_mismatch")
            text(label["label"])
            certainty = label["certainty"]
            require(certainty in ("observation", "ambiguous"), "invalid_label_certainty")
            require(certainty != "observation" or item["status"] == "accepted_observation",
                    "observation_requires_accepted_review")
            alternatives = label["alternatives"]
            require(isinstance(alternatives, list) and len(alternatives) <= 8, "alternatives_limit")
            for alternative in alternatives:
                text(alternative)
            require(len(set(alternatives)) == len(alternatives), "duplicate_alternative")
            require(certainty == "ambiguous" or not alternatives, "alternatives_require_ambiguity")
            candidate = verify_annotation_receipt(item, mh, run, metadata, source_hash)
            selected.append({**label, "category": item["category"], "review_status": item["status"],
                             "candidate_artifact_receipt": candidate})
        results.append({"id": name, "origin": origin, "source_sha256": source_hash,
                        "manifest_sha256": mh, "annotation_store_sha256": sh,
                        "annotation_revision": ar["revision"], "source_bounds_seconds": list(bounds),
                        "selected_labels": selected})
    return {"schema_version": 1, "status": "metadata_validated", "corpus_id": corpus["corpus_id"],
            "corpus_revision": corpus["revision"], "corpus_sha256": corpus_hash,
            "units": "source_seconds", "coverage": "sparse_reviewed_spans", "reviewers": reviewers,
            "source_count": len(results), "label_count": label_count, "source_origin_counts": origin_counts,
            "metadata_bytes_read": metadata.total, "sources": results,
            "source_audio_read": False, "ground_truth_established": False,
            "listening_acceptance": "not_established",
            "unlabelled_intervals": "unknown_not_negative",
            "assertion_boundary": "origin_reviewer_identity_and_label_authorship_are_supplied_not_authenticated",
            "synthetic_labels": "fixture_only_never_real_recording_ground_truth"}


def summarize(result):
    """Project an already fully validated receipt; never skip a selected label."""
    keys = ("schema_version", "status", "corpus_id", "corpus_revision", "corpus_sha256", "units",
            "coverage", "source_count", "label_count", "source_origin_counts", "metadata_bytes_read",
            "source_audio_read", "ground_truth_established", "listening_acceptance", "unlabelled_intervals",
            "assertion_boundary", "synthetic_labels")
    summary = {key: result[key] for key in keys}
    summary.update(result_mode="metadata_summary", reviewer_count=len(result["reviewers"]),
                   source_origin_label_counts={"real_recording": 0, "synthetic_fixture": 0}, sources=[])
    for source in result["sources"]:
        row = {key: source[key] for key in ("id", "origin", "source_sha256", "manifest_sha256",
                                           "annotation_store_sha256", "annotation_revision", "source_bounds_seconds")}
        row.update(label_count=len(source["selected_labels"]),
                   certainty_counts={"observation": 0, "ambiguous": 0},
                   review_status_counts={state: 0 for state in sorted(STATES)})
        for label in source["selected_labels"]:
            row["certainty_counts"][label["certainty"]] += 1
            row["review_status_counts"][label["review_status"]] += 1
        summary["source_origin_label_counts"][source["origin"]] += row["label_count"]
        summary["sources"].append(row)
    # Guard even unusually large revision integers without altering full validation.
    require(len(json.dumps(summary, separators=(",", ":"), allow_nan=False).encode("utf-8")) + 1
            <= MAX_SUMMARY_BYTES, "summary_output_limit")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    command = sub.add_parser("validate")
    command.add_argument("manifest", type=Path)
    command.add_argument("--root", type=Path, default=ROOT)
    command.add_argument("--summary", action="store_true", help="Return compact receipts after complete validation")
    args = parser.parse_args()
    try:
        result = validate(args.manifest, args.root)
        if args.summary:
            result = summarize(result)
    except (CorpusError, OSError) as exc:
        print(json.dumps({"status": "rejected", "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, separators=(",", ":"), allow_nan=False) if args.summary
          else json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
