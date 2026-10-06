#!/usr/bin/env python3
"""Bounded source-bound issue annotations; v1 storage is never migrated."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import uuid

MAX_REQUEST_BYTES = 20000
MAX_STORE_BYTES = 1_000_000
MAX_PROVENANCE_BYTES = 20_000_000
MAX_METADATA_TOTAL_BYTES = 40_000_000
MAX_SESSION_HASH_BYTES = 512 * 1024 * 1024
MAX_SESSION_FILES = 256
MAX_ANNOTATIONS = 200
MAX_REPLAY_RECEIPTS = 512
KINDS = frozenset({"rhythm_timing", "rhythm_pattern", "phrase_omission", "phrase_duration",
                   "melodic_pitch", "articulation", "rest_execution", "meter_mismatch",
                   "tone", "noise", "other"})
BASES = frozenset({"operator_assertion", "operator_context", "detector_hypothesis", "reference_comparison"})
STATES = frozenset({"needs_review", "accepted_observation", "dismissed_candidate"})
LABELS = {"operator_assertion": "USER REPORTED", "operator_context": "INTENT",
          "detector_hypothesis": "REVIEW", "reference_comparison": "REFERENCE REVIEW"}
SHA = re.compile(r"[a-f0-9]{64}\Z")
KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}\Z")
CONTENT_FIELDS = {"kind", "basis", "status", "source_span", "reported_by", "operator_certainty", "operator_quote", "note"}
OPTIONAL_FIELDS = {"id", "candidate_id", "reference_sha256"}
STORED_FIELDS = {"id", "candidate_id", "reference_sha256", "created_at", "updated_at", "created_with", "updated_with", "claim_label", "musical_verdict"}
REQUEST_FIELDS = {"schema_version", "expected_revision", "idempotency_key", "source_sha256", "manifest_sha256", "annotation"}
STORE_FIELDS = {"schema_version", "source_sha256", "manifest_sha256", "revision", "annotations", "listening_acceptance", "replay_receipts"}
RECEIPT_FIELDS = {"manifest_sha256", "candidate_artifact_sha256"}


class AnnotationError(Exception):
    """Stable machine code plus HTTP status; errors never authorize a verdict."""
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


def require(condition, code, status=400):
    if not condition:
        raise AnnotationError(code, status)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def finite(value):
    require(type(value) in (int, float), "invalid_source_span")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise AnnotationError("invalid_source_span") from exc
    require(math.isfinite(result), "invalid_source_span")
    return result


def valid_id(value):
    require(isinstance(value, str), "invalid_annotation_id")
    try:
        require(str(uuid.UUID(value)) == value, "invalid_annotation_id")
    except (ValueError, AttributeError) as exc:
        raise AnnotationError("invalid_annotation_id") from exc


def text(value, field, *, optional=False):
    if optional and value is None:
        return
    require(isinstance(value, str) and 1 <= len(value.strip()) <= 4000 and len(value) <= 4000,
            "invalid_annotation_" + field)
    require(not any(ord(char) < 32 and char not in "\t\n\r" for char in value), "invalid_annotation_" + field)


def timestamp(value):
    require(isinstance(value, str), "invalid_annotation_store_timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AnnotationError("invalid_annotation_store_timestamp") from exc
    require(parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0,
            "invalid_annotation_store_timestamp")


def validate_annotation(item, *, source_min_seconds, source_max_seconds, stored=False):
    """Validate a closed issue record without I/O. Preserve literal user wording."""
    require(isinstance(item, dict), "invalid_annotation_fields")
    allowed = CONTENT_FIELDS | (STORED_FIELDS if stored else OPTIONAL_FIELDS)
    require(set(item) <= allowed and CONTENT_FIELDS <= set(item), "invalid_annotation_fields")
    if stored:
        require(set(item) == CONTENT_FIELDS | STORED_FIELDS, "invalid_annotation_store_fields")
    for field, allowed_values in (("kind", KINDS), ("basis", BASES), ("status", STATES)):
        require(isinstance(item[field], str) and item[field] in allowed_values, "invalid_annotation_" + field)
    span = item["source_span"]
    require(isinstance(span, dict) and set(span) == {"start_seconds", "end_seconds", "extent_known"}, "invalid_source_span")
    start, end = finite(span["start_seconds"]), finite(span["end_seconds"])
    require(type(span["extent_known"]) is bool, "invalid_source_span")
    require(source_min_seconds <= start <= end <= source_max_seconds, "source_span_out_of_bounds")
    require(span["extent_known"] or start == end, "unknown_extent_must_be_point")
    who = item["reported_by"]
    require(isinstance(who, dict) and set(who) == {"actor", "via"}, "invalid_annotation_authorship")
    require(who["actor"] in ("operator", "agent", "detector") and who["via"] in ("browser", "agent", "cli"), "invalid_annotation_authorship")
    basis = item["basis"]
    if basis == "operator_assertion":
        require(who["actor"] == "operator", "operator_assertion_requires_operator_authorship")
        require(item["operator_certainty"] in ("uncertain", "confirmed"), "invalid_operator_certainty")
        text(item["operator_quote"], "operator_quote")
    else:
        require(item["operator_certainty"] is None and item["operator_quote"] is None, "nonoperator_assertion_cannot_claim_operator_certainty")
        if basis == "operator_context":
            require(who["actor"] == "operator", "operator_context_requires_operator_authorship")
        if basis == "detector_hypothesis":
            require(who["actor"] == "detector", "detector_hypothesis_requires_detector_authorship")
    text(item["note"], "note")
    if "id" in item:
        valid_id(item["id"])
    for field in ("candidate_id", "reference_sha256"):
        if item.get(field) is not None:
            require(sha(item[field]), "invalid_annotation_" + field)
    if basis == "reference_comparison":
        require(sha(item.get("reference_sha256")), "reference_comparison_requires_reference_hash")
    if stored:
        for field in ("created_at", "updated_at"):
            timestamp(item[field])
        require(item["updated_at"] >= item["created_at"], "invalid_annotation_store_timestamp")
        for field in ("created_with", "updated_with"):
            receipt = item[field]
            require(isinstance(receipt, dict) and set(receipt) == RECEIPT_FIELDS, "invalid_annotation_provenance")
            require(sha(receipt["manifest_sha256"]) and (receipt["candidate_artifact_sha256"] is None or sha(receipt["candidate_artifact_sha256"])), "invalid_annotation_provenance")
        require(item["claim_label"] == LABELS[basis] and item["musical_verdict"] == "not_established", "invalid_annotation_claim_boundary")
    return item


def validate_store(value, *, source_sha256, manifest_sha256, source_min_seconds, source_max_seconds, public=False):
    """Pure validation. Public projections intentionally omit replay receipts."""
    require(isinstance(value, dict), "invalid_annotation_store")
    fields = STORE_FIELDS - {"replay_receipts"} if public else STORE_FIELDS
    require(set(value) == fields and type(value["schema_version"]) is int and value["schema_version"] == 2, "invalid_annotation_store")
    require(sha(value["source_sha256"]) and sha(source_sha256) and value["source_sha256"] == source_sha256, "annotation_source_mismatch", 409)
    require(sha(value["manifest_sha256"]) and sha(manifest_sha256) and value["manifest_sha256"] == manifest_sha256, "annotation_manifest_mismatch", 409)
    require(type(value["revision"]) is int and 0 <= value["revision"] <= MAX_REPLAY_RECEIPTS, "invalid_annotation_store_revision")
    require(value["listening_acceptance"] == "not_established", "invalid_annotation_acceptance_state")
    records = value["annotations"]
    require(isinstance(records, list) and len(records) <= MAX_ANNOTATIONS, "invalid_annotation_store")
    identifiers = set()
    for item in records:
        validate_annotation(item, source_min_seconds=source_min_seconds, source_max_seconds=source_max_seconds, stored=True)
        require(item["id"] not in identifiers, "duplicate_annotation_id")
        identifiers.add(item["id"])
        require(item["created_with"]["manifest_sha256"] == manifest_sha256 and item["updated_with"]["manifest_sha256"] == manifest_sha256, "annotation_provenance_manifest_mismatch", 409)
    if not public:
        receipts = value["replay_receipts"]
        require(isinstance(receipts, list) and len(receipts) == value["revision"] <= MAX_REPLAY_RECEIPTS, "invalid_replay_receipts")
        keys, revisions = set(), set()
        for item in receipts:
            require(isinstance(item, dict) and set(item) == {"key", "request_sha256", "annotation_id", "committed_revision"}, "invalid_replay_receipts")
            key = item["key"]
            require(isinstance(key, str) and KEY.fullmatch(key) is not None and key not in keys, "invalid_replay_receipts")
            require(sha(item["request_sha256"]) and isinstance(item["annotation_id"], str) and item["annotation_id"] in identifiers, "invalid_replay_receipts")
            revision = item["committed_revision"]
            require(type(revision) is int and 1 <= revision <= value["revision"] and revision not in revisions, "invalid_replay_receipts")
            keys.add(key)
            revisions.add(revision)
        require(identifiers <= {item["annotation_id"] for item in receipts}, "uncommitted_annotation_record")
    return value


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def read_bytes(path, limit, *, expected_size=None):
    """Nonblocking bounded regular-file snapshot, with identity checks."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode), "unsafe_annotation_file")
        require(0 < info.st_size <= limit, "annotation_file_size_limit", 413)
        require(expected_size is None or info.st_size == expected_size, "annotation_file_changed_before_read", 409)
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(limit + 1)
        require(len(data) <= limit, "annotation_file_size_limit", 413)
        after = os.fstat(fd)
        require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) and len(data) == info.st_size,
                "annotation_file_changed_during_read", 409)
        return data
    finally:
        os.close(fd)


def parse_json(data):
    return json.loads(data, object_pairs_hook=no_duplicate_keys,
                      parse_constant=lambda _: (_ for _ in ()).throw(AnnotationError("nonfinite_json_number")))


def read_json(path, limit):
    return parse_json(read_bytes(path, limit))


def hash_provenance(path, *, max_bytes=None, expected_size=None):
    """Hash only bounded regular pinned metadata, with no leaf symlink follow."""
    if max_bytes is None:
        max_bytes = MAX_PROVENANCE_BYTES
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= max_bytes, "unsafe_provenance_file", 409)
        require(expected_size is None or info.st_size == expected_size, "provenance_changed_before_read", 409)
        fingerprint = hashlib.sha256()
        offset = 0
        while offset < info.st_size:
            chunk = os.pread(fd, min(65536, info.st_size - offset), offset)
            require(bool(chunk), "provenance_changed_during_read", 409)
            fingerprint.update(chunk)
            offset += len(chunk)
        after = os.fstat(fd)
        require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), "provenance_changed_during_read", 409)
        return fingerprint.hexdigest()
    finally:
        os.close(fd)


class MetadataAccess:
    """Bounded immutable JSON snapshots for new CLI session construction only.

    Existing report semantics receive injected I/O dependencies; no globals or
    musical interpretation are replaced. Selected raw media is streamed under a
    separate hash budget rather than a JSON-sized cap.
    """
    def __init__(self, root):
        self.root = root
        self.values = {}
        self.hashes = {}
        self.metadata_bytes = 0
        self.hash_bytes = 0

    def budget(self, path, *, metadata=False, limit=MAX_SESSION_HASH_BYTES):
        require(not path.is_symlink(), "unsafe_session_artifact")
        info = path.stat()
        require(stat.S_ISREG(info.st_mode), "unsafe_session_artifact")
        require(len(self.hashes) < MAX_SESSION_FILES, "session_artifact_count_limit", 413)
        require(info.st_size <= limit and self.hash_bytes + info.st_size <= MAX_SESSION_HASH_BYTES,
                "session_hash_byte_limit", 413)
        if metadata:
            require(self.metadata_bytes + info.st_size <= MAX_METADATA_TOTAL_BYTES, "session_metadata_byte_limit", 413)
        return info.st_size

    def load_json(self, path, *, max_bytes=MAX_PROVENANCE_BYTES):
        path = Path(path)
        if path in self.values:
            require(len(canonical(self.values[path])) <= max_bytes, "annotation_file_size_limit", 413)
            return self.values[path]
        try:
            size = self.budget(path, metadata=True, limit=max_bytes)
            data = read_bytes(path, max_bytes, expected_size=size)
        except FileNotFoundError:
            return {}
        value = parse_json(data)
        require(isinstance(value, dict), "session_metadata_object_required")
        if path.name == "dag.json" and isinstance(value.get("artifact_hashes"), dict):
            require(len(value["artifact_hashes"]) <= MAX_SESSION_FILES, "session_artifact_count_limit", 413)
        self.metadata_bytes += len(data)
        self.hash_bytes += len(data)
        self.values[path] = value
        self.hashes[path] = hashlib.sha256(data).hexdigest()
        return value

    def sha256(self, path):
        path = Path(path)
        if path in self.hashes:
            return self.hashes[path]
        size = self.budget(path, limit=MAX_PROVENANCE_BYTES if path.suffix == ".json" else MAX_SESSION_HASH_BYTES)
        fingerprint = hash_provenance(path, max_bytes=min(MAX_PROVENANCE_BYTES if path.suffix == ".json" else MAX_SESSION_HASH_BYTES, MAX_SESSION_HASH_BYTES - self.hash_bytes), expected_size=size)
        self.hash_bytes += size
        self.hashes[path] = fingerprint
        return fingerprint

    def verify_snapshot(self):
        """Recheck all selected files before publishing any new v2 annotation."""
        total = 0
        for path, expected in self.hashes.items():
            size = self.budget_for_recheck(path)
            total += size
            require(total <= MAX_SESSION_HASH_BYTES, "session_hash_byte_limit", 413)
            require(hash_provenance(path, max_bytes=min(MAX_PROVENANCE_BYTES if path.suffix == ".json" else MAX_SESSION_HASH_BYTES, MAX_SESSION_HASH_BYTES - total + size), expected_size=size) == expected,
                    "session_selected_artifact_changed_restart_review", 409)

    @staticmethod
    def budget_for_recheck(path):
        require(not path.is_symlink(), "unsafe_session_artifact")
        info = path.stat()
        require(stat.S_ISREG(info.st_mode), "unsafe_session_artifact")
        return info.st_size


@contextmanager
def storage_lock(root):
    fd = os.open(root / ".review-annotations-v2.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), "unsafe_annotation_lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AnnotationError("annotation_store_busy_retry", 409) from exc
        yield
    finally:
        os.close(fd)


def atomic_json(path, value):
    encoded = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
    require(len(encoded) <= MAX_STORE_BYTES, "annotation_store_size_limit", 413)
    temporary = None
    try:
        fd, name = tempfile.mkstemp(dir=path.parent, prefix=".review-v2-", suffix=".json")
        temporary = Path(name)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


class AnnotationStore:
    """Use one pinned review session and an independent, bounded v2 store."""
    def __init__(self, session):
        require(sha(session.source_hash) and sha(session.manifest_hash), "invalid_annotation_session_identity")
        timeline = session.manifest.get("timeline")
        pcm = session.manifest.get("pcm")
        require(isinstance(timeline, dict) and isinstance(pcm, dict) and
                {"audio_start_seconds", "format_start_seconds"} <= set(timeline),
                "annotation_source_clock_unknown", 409)
        try:
            audio_start = finite(timeline["audio_start_seconds"])
            format_start = finite(timeline["format_start_seconds"])
            duration = pcm.get("duration_seconds")
            if duration is None:
                count, rate = pcm.get("sample_count"), pcm.get("sample_rate")
                require(type(count) is int and count > 0 and type(rate) is int and rate > 0,
                        "annotation_source_clock_unknown", 409)
                duration = count / rate
            duration = finite(duration)
            require(0 < duration <= 43200 and duration == session.duration and
                    audio_start == session.audio_start and format_start == session.format_start and
                    session.source_min == min(audio_start, format_start) and
                    session.source_max == audio_start + duration,
                    "annotation_source_clock_unknown", 409)
        except (AnnotationError, ValueError, TypeError, OverflowError, KeyError) as error:
            raise AnnotationError("annotation_source_clock_unknown", 409) from error
        self.session = session
        self.path = session.root / "review-annotations-v2.json"

    def empty(self):
        return {"schema_version": 2, "source_sha256": self.session.source_hash,
                "manifest_sha256": self.session.manifest_hash, "revision": 0, "annotations": [],
                "listening_acceptance": "not_established", "replay_receipts": []}

    def bindings(self):
        return {"source_sha256": self.session.source_hash, "manifest_sha256": self.session.manifest_hash,
                "source_min_seconds": self.session.source_min, "source_max_seconds": self.session.source_max}

    def current_manifest(self):
        path = self.session.manifest_path
        require(not path.is_symlink() and path.is_file() and hash_provenance(path) == self.session.manifest_hash,
                "session_manifest_changed_restart_review", 409)

    def load(self):
        self.current_manifest()
        require(not self.path.is_symlink(), "unsafe_annotation_store")
        try:
            value = read_json(self.path, MAX_STORE_BYTES)
        except FileNotFoundError:
            value = self.empty()
        except (ValueError, RecursionError) as error:
            raise AnnotationError("invalid_annotation_store") from error
        return validate_store(value, **self.bindings())

    @staticmethod
    def project(store, mutation=None):
        result = {key: value for key, value in store.items() if key != "replay_receipts"}
        if mutation is not None:
            result["mutation"] = mutation
        return result

    def read(self):
        return self.project(self.load())

    def write(self, request):
        require(isinstance(request, dict) and set(request) == REQUEST_FIELDS, "invalid_annotation_request")
        require(type(request["schema_version"]) is int and request["schema_version"] == 2, "invalid_annotation_schema")
        require(request["source_sha256"] == self.session.source_hash, "annotation_source_mismatch", 409)
        require(request["manifest_sha256"] == self.session.manifest_hash, "annotation_manifest_mismatch", 409)
        require(type(request["expected_revision"]) is int and 0 <= request["expected_revision"] <= MAX_REPLAY_RECEIPTS, "invalid_expected_revision")
        key = request["idempotency_key"]
        require(isinstance(key, str) and KEY.fullmatch(key) is not None, "invalid_idempotency_key")
        item = request["annotation"]
        validate_annotation(item, source_min_seconds=self.session.source_min, source_max_seconds=self.session.source_max)
        require(len(canonical(request)) <= MAX_REQUEST_BYTES, "annotation_request_too_large_or_empty", 413)
        fingerprint = digest(request)
        with self.session.lock, storage_lock(self.session.root):
            store = self.load()
            access = getattr(self.session, "metadata_access", None)
            if access is not None:
                access.verify_snapshot()
            for path, expected in self.session.provenance_hashes.items():
                require(not path.is_symlink() and path.is_file() and hash_provenance(path) == expected,
                        "session_candidates_changed_restart_review", 409)
            replay = next((entry for entry in store["replay_receipts"] if entry["key"] == key), None)
            if replay is not None:
                require(replay["request_sha256"] == fingerprint, "idempotency_key_conflict", 409)
                return self.project(store, {"outcome": "replayed", "annotation_id": replay["annotation_id"], "committed_revision": replay["committed_revision"]})
            require(request["expected_revision"] == store["revision"], "stale_annotation_revision", 409)
            require(len(store["replay_receipts"]) < MAX_REPLAY_RECEIPTS, "annotation_replay_limit_reached", 413)
            identifier = item.get("id")
            existing = next((entry for entry in store["annotations"] if entry["id"] == identifier), None)
            require(identifier is None or existing is not None, "annotation_not_found", 404)
            require(existing is not None or len(store["annotations"]) < MAX_ANNOTATIONS, "annotation_limit_reached", 413)
            candidate = item.get("candidate_id")
            require(candidate is None or candidate in self.session.marker_ids, "candidate_not_in_current_session")
            now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            receipt = {"manifest_sha256": self.session.manifest_hash, "candidate_artifact_sha256": self.session.candidate_hash}
            saved = {**item, "id": identifier or str(uuid.uuid4()), "candidate_id": candidate,
                     "reference_sha256": item.get("reference_sha256"),
                     "created_at": existing["created_at"] if existing else now, "updated_at": now,
                     "created_with": existing["created_with"] if existing else receipt, "updated_with": receipt,
                     "claim_label": LABELS[item["basis"]], "musical_verdict": "not_established"}
            if existing is None:
                store["annotations"].append(saved)
            else:
                store["annotations"][store["annotations"].index(existing)] = saved
            store["revision"] += 1
            store["annotations"].sort(key=lambda entry: (entry["source_span"]["start_seconds"], entry["id"]))
            replay = {"key": key, "request_sha256": fingerprint, "annotation_id": saved["id"], "committed_revision": store["revision"]}
            store["replay_receipts"].append(replay)
            validate_store(store, **self.bindings())
            atomic_json(self.path, store)
            return self.project(store, {"outcome": "saved", "annotation_id": saved["id"], "committed_revision": store["revision"]})


def request_schema():
    """Closed structural JSON schema; write() enforces contextual invariants."""
    nullable_sha = {"anyOf": [{"type": "string", "pattern": "^[a-f0-9]{64}$"}, {"type": "null"}]}
    return {"type": "object", "additionalProperties": False, "required": sorted(REQUEST_FIELDS), "properties": {
        "schema_version": {"type": "integer", "const": 2}, "expected_revision": {"type": "integer", "minimum": 0, "maximum": MAX_REPLAY_RECEIPTS},
        "idempotency_key": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$"},
        "source_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}, "manifest_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "annotation": {"type": "object", "additionalProperties": False, "required": sorted(CONTENT_FIELDS), "properties": {
            "id": {"type": "string", "format": "uuid"}, "kind": {"type": "string", "enum": sorted(KINDS)},
            "basis": {"type": "string", "enum": sorted(BASES)}, "status": {"type": "string", "enum": sorted(STATES)},
            "source_span": {"type": "object", "additionalProperties": False, "required": ["start_seconds", "end_seconds", "extent_known"], "properties": {
                "start_seconds": {"type": "number"}, "end_seconds": {"type": "number"}, "extent_known": {"type": "boolean"}}},
            "reported_by": {"type": "object", "additionalProperties": False, "required": ["actor", "via"], "properties": {
                "actor": {"type": "string", "enum": ["operator", "agent", "detector"]}, "via": {"type": "string", "enum": ["browser", "agent", "cli"]}}},
            "operator_certainty": {"enum": ["uncertain", "confirmed", None]},
            "operator_quote": {"anyOf": [{"type": "string", "minLength": 1, "maxLength": 4000}, {"type": "null"}]},
            "note": {"type": "string", "minLength": 1, "maxLength": 4000},
            "candidate_id": nullable_sha, "reference_sha256": nullable_sha}}}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("read", "write"))
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--input", type=Path)
    args = parser.parse_args(argv)
    if (args.operation == "write") != (args.input is not None):
        parser.error("--input is required only for write")
    import review_server
    session = None
    try:
        session = review_server.Session(args.run_dir, open_media=False, bounded_metadata=True)
        store = AnnotationStore(session)
        value = store.write(read_json(args.input, MAX_REQUEST_BYTES)) if args.operation == "write" else store.read()
        print(json.dumps({**value, "count": len(value["annotations"]), "status": "annotations_v2_saved" if args.operation == "write" else "annotations_v2_loaded"}, ensure_ascii=False, allow_nan=False))
    except (AnnotationError, review_server.ReviewError, OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        print(json.dumps({"error": error.code if isinstance(error, (AnnotationError, review_server.ReviewError)) else "invalid_local_review_artifact"}), file=sys.stderr)
        return 1
    finally:
        if session is not None:
            session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
