#!/usr/bin/env python3
"""Read-only, bounded corpus family/split metadata validation; never open audio."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path
import sys

import corpus

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "video-utils.corpus-split.s1"
SPLITS = ("train", "validation", "test", "unassigned")
MAX_RECORDS = 500
MAX_REFERENCES = 1000
MAX_SELECTED = 5000
MAX_RESULT = 1_000_000


class SplitError(corpus.CorpusError):
    pass


def require(value, code):
    if not value:
        raise SplitError(code)


def fields(value, names, code):
    require(isinstance(value, dict) and set(value) == set(names), code)


def identifiers(value, maximum, code):
    require(isinstance(value, list) and len(value) <= maximum, code)
    for item in value:
        corpus.identifier(item)
    require(len(set(value)) == len(value), "duplicate_" + code)
    return value


def receipt(value, code):
    fields(value, ("path", "sha256"), code)
    corpus.fingerprint(value["sha256"])
    return value


class Families:
    """Deterministic union-find; stable group keys use sorted record identities."""
    def __init__(self, names):
        self.parents = {name: name for name in names}

    def find(self, name):
        root = name
        while self.parents[root] != root:
            root = self.parents[root]
        while self.parents[name] != name:
            previous = self.parents[name]
            self.parents[name] = root
            name = previous
        return root

    def join(self, left, right):
        left, right = self.find(left), self.find(right)
        if left != right:
            self.parents[max(left, right)] = min(left, right)


def selected_annotations(metadata, row, reference):
    """Reuse owner validators; no local annotation kind/basis ontology is defined."""
    fields(reference, ("store", "schema_version", "revision", "selected_ids"),
           "invalid_annotation_reference")
    store_ref = receipt(reference["store"], "invalid_annotation_store_receipt")
    require(type(reference["schema_version"]) is int and reference["schema_version"] in (1, 2),
            "unsupported_annotation_schema")
    corpus.integer(reference["revision"])
    selected = reference["selected_ids"]
    require(isinstance(selected, list) and len(selected) <= 200, "selected_annotation_limit")
    require(all(isinstance(item, str) and 0 < len(item) <= 80 for item in selected),
            "invalid_selected_annotation_id")
    require(len(set(selected)) == len(selected), "duplicate_selected_annotation_id")
    require(row["manifest"] is not None, "annotation_manifest_required")
    mr = row["manifest"]
    manifest, manifest_hash = metadata.read(mr["path"], mr["sha256"])
    require(corpus.source_identity(manifest) == row["source_sha256"], "manifest_source_mismatch")
    bounds = corpus.source_bounds(manifest)
    store, store_hash = metadata.read(store_ref["path"], store_ref["sha256"])
    require(type(store.get("schema_version")) is int and
            store["schema_version"] == reference["schema_version"], "annotation_schema_mismatch")
    require(store.get("source_sha256") == row["source_sha256"], "annotation_source_mismatch")
    require(type(store.get("revision")) is int and store["revision"] == reference["revision"],
            "stale_annotation_revision")
    require(store.get("listening_acceptance") == "not_established", "invalid_acceptance_claim")
    run = metadata.relative(mr["path"]).parent
    require(metadata.relative(mr["path"]).name == "manifest.json", "run_manifest_name_required")
    if reference["schema_version"] == 1:
        require(metadata.relative(store_ref["path"]) == run / "review-annotations.json",
                "run_local_annotation_store_required")
        found = corpus.annotations(store, row["source_sha256"], reference["revision"], bounds)
    else:
        require(metadata.relative(store_ref["path"]) == run / "review-annotations-v2.json",
                "run_local_annotation_store_required")
        try:
            import annotation_v2
        except ImportError as exc:
            raise SplitError("annotation_v2_validator_unavailable") from exc
        try:
            annotation_v2.validate_store(store, source_sha256=row["source_sha256"],
                                         manifest_sha256=manifest_hash,
                                         source_min_seconds=bounds[0], source_max_seconds=bounds[1])
        except annotation_v2.AnnotationError as exc:
            raise SplitError("annotation_v2_rejected:" + exc.code) from exc
        found = {item["id"]: item for item in store["annotations"]}
    # Both store versions use the review owner's same candidate receipt/identity
    # convention. Pure v2 structural validation alone cannot detect stale files.
    for item in found.values():
        corpus.verify_annotation_receipt(item, manifest_hash, run, metadata,
                                         row["source_sha256"])
    require(all(item in found for item in selected), "selected_annotation_not_found")
    return {"store_sha256": store_hash, "manifest_sha256": manifest_hash,
            "schema_version": reference["schema_version"], "revision": reference["revision"],
            "selected_annotations": [found[item] for item in selected]}


def validate_split(manifest_path, local_root=ROOT, summary=False):
    metadata = corpus.Metadata(local_root)
    path = Path(manifest_path).absolute()
    try:
        name = str(path.relative_to(metadata.root))
    except ValueError as exc:
        raise SplitError("manifest_outside_corpus_root") from exc
    payload, digest = metadata.read(name)
    fields(payload, ("schema_id", "schema_version", "corpus_id", "revision", "coverage",
                     "approval_state", "records", "context_refs"), "invalid_split_manifest_fields")
    require(payload["schema_id"] == SCHEMA and type(payload["schema_version"]) is int and
            payload["schema_version"] == 1, "unsupported_split_schema")
    corpus.identifier(payload["corpus_id"])
    corpus.integer(payload["revision"], 1)
    require(payload["coverage"] == "sparse_or_unknown_no_negative_inference", "invalid_coverage")
    require(payload["approval_state"] == "unreviewed", "unsupported_approval_state")
    records = payload["records"]
    require(isinstance(records, list) and 0 < len(records) <= MAX_RECORDS, "record_count_limit")
    rows = {}
    for row in records:
        fields(row, ("id", "take_family_id", "split", "origin", "source_sha256",
                     "artifact_sha256", "parent_ids", "augmentation_group_ids", "manifest",
                     "annotation_refs"), "invalid_split_record_fields")
        name = corpus.identifier(row["id"])
        require(name not in rows, "duplicate_record_id")
        corpus.identifier(row["take_family_id"])
        require(isinstance(row["split"], str) and row["split"] in SPLITS, "invalid_split")
        require(row["origin"] in ("real_recording", "synthetic_fixture"), "invalid_origin")
        corpus.fingerprint(row["source_sha256"])
        corpus.fingerprint(row["artifact_sha256"])
        identifiers(row["parent_ids"], 32, "parent_ids")
        require(name not in row["parent_ids"], "self_parent")
        identifiers(row["augmentation_group_ids"], 32, "augmentation_group_ids")
        if row["manifest"] is not None:
            mr = receipt(row["manifest"], "invalid_record_manifest")
            manifest, _ = metadata.read(mr["path"], mr["sha256"])
            require(corpus.source_identity(manifest) == row["source_sha256"], "manifest_source_mismatch")
            corpus.source_bounds(manifest)
        require(isinstance(row["annotation_refs"], list) and len(row["annotation_refs"]) <= 8,
                "annotation_reference_limit")
        rows[name] = row

    families = Families(rows)
    identity_owners = {}
    children = defaultdict(list)
    indegree = {name: 0 for name in rows}
    for name, row in rows.items():
        for parent in row["parent_ids"]:
            require(parent in rows, "missing_parent")
            require(row["source_sha256"] == rows[parent]["source_sha256"], "parent_source_mismatch")
            families.join(name, parent)
            children[parent].append(name)
            indegree[name] += 1
        identities = [("family", row["take_family_id"]), ("source", row["source_sha256"]),
                      ("artifact", row["artifact_sha256"])]
        identities += [("augmentation", group) for group in row["augmentation_group_ids"]]
        for identity in identities:
            if identity in identity_owners:
                families.join(name, identity_owners[identity])
            else:
                identity_owners[identity] = name
    queue = deque(name for name in rows if indegree[name] == 0)
    visited = 0
    while queue:
        name = queue.popleft()
        visited += 1
        for child in children[name]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    require(visited == len(rows), "parent_cycle")

    reference_count = selected_count = 0
    validated_refs = {}
    reference_owners = {}
    selected_owners = {}
    for name, row in rows.items():
        results = []
        seen_refs = set()
        for reference in row["annotation_refs"]:
            reference_count += 1
            require(reference_count <= MAX_REFERENCES, "total_annotation_reference_limit")
            validated = selected_annotations(metadata, row, reference)
            key = validated["store_sha256"]
            require(key not in seen_refs, "duplicate_annotation_reference")
            seen_refs.add(key)
            if key in reference_owners:
                families.join(name, reference_owners[key])
            else:
                reference_owners[key] = name
            selected_count += len(validated["selected_annotations"])
            require(selected_count <= MAX_SELECTED, "total_selected_annotation_limit")
            for item in validated["selected_annotations"]:
                # Same selected UUID and original source cannot become held-out truth
                # by republishing a store at a new revision/hash.
                annotation_key = row["source_sha256"], item["id"]
                if annotation_key in selected_owners:
                    families.join(name, selected_owners[annotation_key])
                else:
                    selected_owners[annotation_key] = name
            results.append(validated)
        validated_refs[name] = results

    groups = defaultdict(list)
    for name in sorted(rows):
        groups[families.find(name)].append(name)
    group_receipts = []
    for members in sorted(groups.values()):
        group_rows = [rows[name] for name in members]
        splits = {row["split"] for row in group_rows if row["split"] != "unassigned"}
        require(len(splits) <= 1, "cross_split_family_leakage")
        require(len({row["take_family_id"] for row in group_rows}) == 1,
                "conflicting_take_family_identity")
        require(len({row["origin"] for row in group_rows}) == 1, "conflicting_family_origin")
        artifacts = defaultdict(set)
        for row in group_rows:
            artifacts[row["artifact_sha256"]].add(row["source_sha256"])
        require(all(len(values) == 1 for values in artifacts.values()), "conflicting_artifact_source")
        # Key excludes split assignments and input order; changing content/lineage
        # changes the key rather than silently preserving an evaluation identity.
        key_rows = [{**{key: row[key] for key in ("id", "source_sha256", "artifact_sha256")},
                     "parent_ids": sorted(row["parent_ids"]),
                     "augmentation_group_ids": sorted(row["augmentation_group_ids"])}
                    for row in group_rows]
        group_key = hashlib.sha256(json.dumps(key_rows, sort_keys=True,
                                             separators=(",", ":")).encode()).hexdigest()
        group_receipts.append({"group_sha256": group_key, "record_ids": members,
                               "take_family_id": group_rows[0]["take_family_id"],
                               "assigned_split": next(iter(splits), None),
                               "unassigned_record_count": sum(row["split"] == "unassigned"
                                                              for row in group_rows)})

    contexts = payload["context_refs"]
    require(isinstance(contexts, list) and len(contexts) <= 32, "context_reference_limit")
    context_receipts = []
    seen_context = set()
    sources = {row["source_sha256"] for row in rows.values()}
    for context in contexts:
        fields(context, ("metadata", "source_sha256", "basis"), "invalid_context_reference")
        require(context["basis"] == "operator_context", "context_is_not_detected_ground_truth")
        corpus.fingerprint(context["source_sha256"])
        require(context["source_sha256"] in sources, "context_source_not_in_corpus")
        meta_ref = receipt(context["metadata"], "invalid_context_receipt")
        value, sha = metadata.read(meta_ref["path"], meta_ref["sha256"])
        require(value.get("source_sha256") == context["source_sha256"], "context_source_mismatch")
        require(sha not in seen_context, "duplicate_context_reference")
        seen_context.add(sha)
        context_receipts.append({"metadata_sha256": sha, "source_sha256": context["source_sha256"],
                                 "basis": "operator_context", "detected_ground_truth": False})

    selected_unique = len(selected_owners)
    result = {"schema_id": SCHEMA, "schema_version": 1, "status": "split_metadata_validated",
              "corpus_id": payload["corpus_id"], "revision": payload["revision"],
              "manifest_sha256": digest, "approval_state": "unreviewed",
              "coverage": payload["coverage"], "record_count": len(rows),
              "group_count": len(group_receipts), "groups": group_receipts,
              "record_split_counts": {split: sum(row["split"] == split for row in rows.values())
                                      for split in SPLITS},
              "origin_counts": dict(Counter(row["origin"] for row in rows.values())),
              "selected_annotation_reference_count": selected_count,
              "unique_selected_annotation_count": selected_unique,
              "absence_denominator": 0, "negative_examples_inferred": 0,
              "unlabelled_intervals": "unknown_not_negative", "source_audio_read": False,
              "ground_truth_established": False, "listening_acceptance": "not_established",
              "training_performed": False, "split_assignment_authored_not_randomized": True,
              "metadata_bytes_read": metadata.total, "contexts": context_receipts,
              "assertion_boundary": "source_origin_lineage_and_authorship_are_declared_not_authenticated",
              "annotation_semantics": "validated_by_existing_schema_owner_not_reclassified",
              "result_mode": "summary" if summary else "full"}
    if not summary:
        result["records"] = [{**rows[name], "validated_annotation_refs": validated_refs[name]}
                             for name in sorted(rows)]
    # Stop before materializing an expanded multi-record full receipt. A small
    # store can be referenced repeatedly; input byte bounds alone do not bound
    # the serialized output expansion.
    output_bytes = 1  # final CLI newline
    for fragment in json.JSONEncoder(separators=(",", ":"), allow_nan=False).iterencode(result):
        output_bytes += len(fragment.encode("utf-8"))
        require(output_bytes <= MAX_RESULT, "result_output_limit")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("manifest", type=Path)
    validate.add_argument("--root", type=Path, default=ROOT)
    validate.add_argument("--summary", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = validate_split(args.manifest, args.root, summary=args.summary)
    except (corpus.CorpusError, OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        # Do not disclose absolute paths or OS diagnostics in tool replies.
        error = str(exc) if isinstance(exc, corpus.CorpusError) else "invalid_or_unreadable_metadata"
        print(json.dumps({"status": "rejected", "error": error}), file=sys.stderr)
        return 1
    print(json.dumps(result, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
