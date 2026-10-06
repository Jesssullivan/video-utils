#!/usr/bin/env python3
"""Private loopback listening review and source-bound annotation storage."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
import threading
from urllib.parse import unquote, urlsplit
import uuid

import report
import annotation_v2

MAX_BODY = 20000
MAX_ANNOTATIONS = 200
MAX_STORE_BYTES = 1_000_000
CATEGORIES = {"rhythm", "phrase", "tone", "noise", "other"}
STATES = {"needs_review", "accepted_observation", "dismissed_candidate"}
ASSETS = Path(__file__).resolve().parents[1] / "review"
SHA = re.compile(r"[a-fA-F0-9]{64}\Z")


class ReviewError(Exception):
    def __init__(self, code, status=400):
        self.code = code
        self.status = status
        super().__init__(code)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReviewError("invalid_source_span")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReviewError("invalid_source_span") from exc
    if not math.isfinite(result):
        raise ReviewError("invalid_source_span")
    return result


def atomic_json(path, value):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".review-", suffix=".json", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


@contextmanager
def storage_lock(root):
    fd = os.open(root / ".review-annotations.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ReviewError("annotation_store_busy_retry", 409) from exc
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def file_signature(fd):
    stat = os.fstat(fd)
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


class Media:
    def __init__(self, path, expected):
        self.name = path.name
        self.fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            self.signature = file_signature(self.fd)
            self.size = self.signature[2]
            digest = hashlib.sha256()
            offset = 0
            while offset < self.size:
                chunk = os.pread(self.fd, min(1024 * 1024, self.size - offset), offset)
                if not chunk:
                    raise ReviewError("media_changed_during_validation", 409)
                digest.update(chunk)
                offset += len(chunk)
            if digest.hexdigest() != expected or file_signature(self.fd) != self.signature:
                raise ReviewError("media_hash_mismatch", 409)
            self.content_type = mimetypes.guess_type(self.name)[0] or "application/octet-stream"
        except BaseException:
            os.close(self.fd)
            raise

    def close(self):
        os.close(self.fd)


class Session:
    def __init__(self, root, open_media=True, bounded_metadata=False):
        self.root = Path(root).resolve(strict=True)
        self.metadata_access = annotation_v2.MetadataAccess(self.root) if bounded_metadata else None
        load_json = self.metadata_access.load_json if self.metadata_access else report.load_json
        metadata_hash = self.metadata_access.sha256 if self.metadata_access else report.sha256
        self.manifest_path = self.root / "manifest.json"
        for relative in ("manifest.json", "analysis.json", "dag.json", "flags.json", "markers.json", "export/outcome.json"):
            metadata = self.root / relative
            if metadata.is_symlink() or (metadata.exists() and not metadata.resolve().is_relative_to(self.root)):
                raise ReviewError("metadata_outside_run_rejected")
        self.manifest = load_json(self.manifest_path)
        self.source_hash = report.source_identity(self.manifest)
        if not isinstance(self.source_hash, str) or not SHA.fullmatch(self.source_hash):
            raise ReviewError("manifest_source_hash_required")
        self.manifest_hash = metadata_hash(self.manifest_path)
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.media = {}
        self.media_status = {}
        self.annotations_path = self.root / "review-annotations.json"
        timeline = self.manifest.get("timeline", {})
        if not isinstance(timeline, dict):
            raise ReviewError("invalid_run_timeline")
        self.audio_start = number(timeline.get("audio_start_seconds", 0))
        self.format_start = number(timeline.get("format_start_seconds", 0))
        pcm = self.manifest.get("pcm", {})
        if not isinstance(pcm, dict):
            raise ReviewError("invalid_run_pcm")
        duration = pcm.get("duration_seconds")
        if duration is None and pcm.get("sample_count") and pcm.get("sample_rate"):
            duration = pcm["sample_count"] / pcm["sample_rate"]
        self.duration = number(duration)
        if not 0 < self.duration <= 43200:
            raise ReviewError("invalid_run_duration")
        self.source_min = min(self.audio_start, self.format_start)
        self.source_max = self.audio_start + self.duration
        outcome, self.export_status = report.export_evidence(self.root, self.manifest) if open_media else ({}, "not_opened_for_annotation_access")
        paths = report.media_paths(self.root, self.manifest, outcome)
        hashes = self.manifest.get("output_sha256", {})
        hashes = hashes if isinstance(hashes, dict) else {}
        export_hashes = outcome.get("output_sha256", {})
        export_hashes = export_hashes if isinstance(export_hashes, dict) else {}
        try:
            if open_media:
                for role in ("original", "clean", "residual", "video"):
                    name = paths.get(role)
                    if not name:
                        self.media_status[role] = "unavailable"
                        continue
                    expected = export_hashes.get(Path(name).name) if role == "video" else hashes.get(Path(name).name)
                    if not isinstance(expected, str) or not SHA.fullmatch(expected):
                        self.media_status[role] = "unverified_hash_omitted"
                        continue
                    safe = report.artifact(self.root, name)
                    if not safe:
                        self.media_status[role] = "unsafe_path_omitted"
                        continue
                    try:
                        self.media[role] = Media((self.root / safe).resolve(), expected)
                        self.media_status[role] = "hash_verified"
                    except (OSError, ReviewError):
                        self.media_status[role] = "modified_or_unavailable_omitted"
            self.auxiliary, self.auxiliary_status = report.auxiliary_evidence(self.root, self.manifest,
                **({"load_json": load_json, "sha256": metadata_hash} if self.metadata_access else {}))
            candidate_name = "markers" if "markers" in self.auxiliary else "flags" if "flags" in self.auxiliary else None
            payload = self.auxiliary.get(candidate_name, {})
            self.candidate_hash = metadata_hash(self.root / f"{candidate_name}.json") if candidate_name else None
            self.provenance_hashes = {self.root / f"{name}.json": metadata_hash(self.root / f"{name}.json") for name in self.auxiliary}
            self.markers = self.marker_items(payload.get("markers", payload.get("flags", [])))
            self.marker_ids = {item["id"] for item in self.markers}
            self.analysis = load_json(self.root / "analysis.json")
            self.analysis_status = report.analysis_lineage(self.root, self.manifest, self.analysis,
                **({"sha256": metadata_hash} if self.metadata_access else {}))
            if self.analysis_status.startswith("rejected"):
                self.analysis = {}
            self.read_annotations()
        except BaseException:
            self.close()
            raise

    def close(self):
        for media in self.media.values():
            media.close()
        self.media.clear()

    def marker_items(self, values):
        if not isinstance(values, list) or len(values) > 50000:
            raise ReviewError("invalid_candidate_collection")
        markers = []
        for item in values:
            if not isinstance(item, dict):
                continue
            start = report.finite(item.get("source_time_seconds"))
            end = report.finite(item.get("end_seconds", start))
            if start is None or end is None or end < start:
                continue
            kind = str(item.get("name", item.get("kind", "review_candidate")))[:256]
            identity = {"source_sha256": self.source_hash, "kind": kind, "start": start, "end": end}
            fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            markers.append({"id": fingerprint, "kind": kind, "source_start_seconds": start,
                            "source_end_seconds": end, "confidence": str(item.get("confidence", "unknown"))[:256],
                            "status": str(item.get("status", "needs_review"))[:128]})
        return sorted(markers, key=lambda item: (item["source_start_seconds"], item["kind"]))

    def empty_store(self):
        return {"schema_version": 1, "source_sha256": self.source_hash, "revision": 0,
                "annotations": [], "listening_acceptance": "not_established"}

    def read_annotations(self):
        path = self.annotations_path
        if path.is_symlink() or (path.exists() and not path.resolve().is_relative_to(self.root)):
            raise ReviewError("unsafe_annotation_store")
        if not path.exists():
            return self.empty_store()
        if path.stat().st_size > MAX_STORE_BYTES:
            raise ReviewError("oversized_annotation_store")
        value = self.metadata_access.load_json(path, max_bytes=MAX_STORE_BYTES) if self.metadata_access else report.load_json(path)
        if value.get("source_sha256") != self.source_hash:
            raise ReviewError("annotation_source_mismatch", 409)
        revision = value.get("revision")
        annotations = value.get("annotations")
        if value.get("schema_version") != 1 or type(revision) is not int or revision < 0 or not isinstance(annotations, list) or len(annotations) > MAX_ANNOTATIONS:
            raise ReviewError("invalid_annotation_store")
        if value.get("listening_acceptance") != "not_established":
            raise ReviewError("invalid_annotation_acceptance_state")
        identifiers = set()
        for item in annotations:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise ReviewError("invalid_annotation_store")
            try:
                identifier = str(uuid.UUID(item["id"]))
            except (ValueError, TypeError, AttributeError) as exc:
                raise ReviewError("invalid_annotation_store_id") from exc
            if identifier != item["id"] or identifier in identifiers:
                raise ReviewError("invalid_annotation_store_id")
            identifiers.add(identifier)
            start, end = number(item.get("source_start_seconds")), number(item.get("source_end_seconds"))
            if start < self.source_min or end > self.source_max or end < start:
                raise ReviewError("invalid_annotation_store_span")
            if not isinstance(item.get("category"), str) or item["category"] not in CATEGORIES or not isinstance(item.get("status"), str) or item["status"] not in STATES:
                raise ReviewError("invalid_annotation_store")
            if not isinstance(item.get("note"), str) or not 1 <= len(item["note"].strip()) <= 4000 or not isinstance(item.get("created_at"), str) or not isinstance(item.get("created_with"), dict):
                raise ReviewError("invalid_annotation_store")
        return value

    def annotate(self, request):
        if not isinstance(request, dict) or set(request) != {"expected_revision", "annotation"}:
            raise ReviewError("invalid_annotation_request")
        item = request["annotation"]
        if not isinstance(item, dict) or set(item) - {"id", "source_start_seconds", "source_end_seconds", "category", "status", "note", "candidate_id"}:
            raise ReviewError("invalid_annotation_fields")
        start = number(item.get("source_start_seconds"))
        end = number(item.get("source_end_seconds"))
        if start < self.source_min or end > self.source_max or end < start:
            raise ReviewError("source_span_out_of_bounds")
        category, status, note = item.get("category"), item.get("status"), item.get("note")
        if not isinstance(category, str) or category not in CATEGORIES or not isinstance(status, str) or status not in STATES or not isinstance(note, str) or not 1 <= len(note.strip()) <= 4000:
            raise ReviewError("invalid_annotation_content")
        identifier = item.get("id")
        if identifier is not None:
            try:
                if str(uuid.UUID(identifier)) != identifier:
                    raise ValueError("noncanonical")
            except (ValueError, TypeError, AttributeError) as exc:
                raise ReviewError("invalid_annotation_id") from exc
        with self.lock, storage_lock(self.root):
            if report.sha256(self.manifest_path) != self.manifest_hash:
                raise ReviewError("session_manifest_changed_restart_review", 409)
            if any(not path.is_file() or report.sha256(path) != fingerprint for path, fingerprint in self.provenance_hashes.items()):
                raise ReviewError("session_candidates_changed_restart_review", 409)
            store = self.read_annotations()
            if type(request["expected_revision"]) is not int or request["expected_revision"] != store["revision"]:
                raise ReviewError("stale_annotation_revision", 409)
            existing = next((entry for entry in store["annotations"] if entry.get("id") == identifier), None) if identifier else None
            if identifier and existing is None:
                raise ReviewError("annotation_not_found", 404)
            if existing is None and len(store["annotations"]) >= MAX_ANNOTATIONS:
                raise ReviewError("annotation_limit_reached", 413)
            candidate = item.get("candidate_id")
            if candidate is not None and (not isinstance(candidate, str) or candidate not in self.marker_ids):
                if existing is None or candidate != existing.get("candidate_id"):
                    raise ReviewError("candidate_not_in_current_session")
            now = utc_now()
            receipt = {"manifest_sha256": self.manifest_hash, "candidate_artifact_sha256": self.candidate_hash}
            saved = {"id": identifier or str(uuid.uuid4()), "source_start_seconds": start, "source_end_seconds": end,
                     "category": category, "status": status, "note": note.strip(), "candidate_id": candidate,
                     "created_at": existing["created_at"] if existing else now, "updated_at": now,
                     "created_with": existing["created_with"] if existing else receipt, "updated_with": receipt}
            if existing:
                store["annotations"][store["annotations"].index(existing)] = saved
            else:
                store["annotations"].append(saved)
            store["revision"] += 1
            store["annotations"].sort(key=lambda entry: (entry["source_start_seconds"], entry["id"]))
            if len(json.dumps(store, ensure_ascii=False, indent=2).encode("utf-8")) > MAX_STORE_BYTES:
                raise ReviewError("annotation_store_size_limit", 413)
            atomic_json(self.annotations_path, store)
            return store

    def read_annotations_v2(self):
        try:
            return annotation_v2.AnnotationStore(self).read()
        except annotation_v2.AnnotationError as error:
            raise ReviewError(error.code, error.status) from error

    def annotate_v2(self, request):
        try:
            return annotation_v2.AnnotationStore(self).write(request)
        except annotation_v2.AnnotationError as error:
            raise ReviewError(error.code, error.status) from error

    def data(self):
        source = self.manifest.get("source", {})
        name = str(source.get("path", source.get("filename", "Private recording"))).replace("\\", "/").split("/")[-1]
        declared = self.analysis.get("declared_tempo") or {}
        grid = self.analysis.get("click_grid") or {}
        declared = declared if isinstance(declared, dict) else {}
        grid = grid if isinstance(grid, dict) else {}
        interpretations = self.analysis.get("metrical_interpretations", [])
        pulse_options = [{"bpm": report.finite(item.get("bpm")), "pulse_multiplier": report.finite(item.get("pulse_multiplier"))} for item in interpretations if isinstance(item, dict)] if isinstance(interpretations, list) else []
        pulse_options = [item for item in pulse_options if item["bpm"] is not None]
        return {"schema_version": 1, "source_name": name, "source_sha256": self.source_hash,
                "run_name": self.root.name, "manifest_sha256": self.manifest_hash,
                "token": self.token, "timeline": {"audio_start_seconds": self.audio_start,
                "format_start_seconds": self.format_start, "source_min_seconds": self.source_min,
                "source_max_seconds": self.source_max, "audio_duration_seconds": self.duration},
                "media": {role: f"/media/{role}" for role in self.media}, "media_status": self.media_status,
                "declared_bpm": report.finite(declared.get("bpm")), "fitted_bpm": report.finite(grid.get("bpm")),
                "metrical_interpretations": pulse_options,
                "markers": self.markers, "candidate_artifact_sha256": self.candidate_hash,
                "candidate_evidence": self.auxiliary_status, "analysis_lineage": self.analysis_status,
                "annotations": self.read_annotations(), "listening_acceptance": "not_established"}


def byte_range(header, size):
    if header is None:
        return 0, max(0, size - 1), False
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header)
    if not match or size == 0 or not any(match.groups()):
        raise ReviewError("invalid_byte_range", 416)
    first, last = match.groups()
    if len(first) > 20 or len(last) > 20:
        raise ReviewError("invalid_byte_range", 416)
    if first:
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1
    else:
        suffix = int(last)
        if suffix <= 0:
            raise ReviewError("invalid_byte_range", 416)
        start, end = max(0, size - suffix), size - 1
    if start >= size or end < start:
        raise ReviewError("invalid_byte_range", 416)
    return start, end, True


class ReviewHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def __init__(self, session, port=8765):
        self.session = session
        self.workers = threading.BoundedSemaphore(16)
        super().__init__(("127.0.0.1", port), Handler)

    def process_request(self, request, address):
        if not self.workers.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.workers.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.workers.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalGuitarReview/1"

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *_):
        pass

    def trusted_request(self, mutation=False):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in hosts:
            raise ReviewError("unexpected_host", 403)
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{host}" for host in hosts}:
            raise ReviewError("unexpected_origin", 403)
        if mutation:
            token = self.headers.get("X-Review-Token", "")
            if not origin or not token.isascii() or not secrets.compare_digest(token, self.server.session.token):
                raise ReviewError("annotation_token_required", 403)

    def send_headers(self, status, kind, size, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; media-src 'self'; connect-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def json_response(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_headers(status, "application/json; charset=utf-8", len(body))
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            self.trusted_request()
            path = unquote(urlsplit(self.path).path)
            if path == "/api/session":
                self.json_response(self.server.session.data())
            elif path == "/api/annotations":
                self.json_response(self.server.session.read_annotations())
            elif path == "/api/annotations-v2":
                self.json_response(self.server.session.read_annotations_v2())
            elif path in {"/", "/index.html", "/app.js", "/practice.js", "/style.css"}:
                name = "index.html" if path in {"/", "/index.html"} else path[1:]
                body = (ASSETS / name).read_bytes()
                kind = "text/html; charset=utf-8" if name.endswith("html") else "text/javascript; charset=utf-8" if name.endswith("js") else "text/css; charset=utf-8"
                self.send_headers(200, kind, len(body))
                if self.command != "HEAD":
                    self.wfile.write(body)
            elif path.startswith("/media/") and path[7:] in self.server.session.media:
                self.send_media(self.server.session.media[path[7:]])
            else:
                raise ReviewError("route_not_found", 404)
        except ReviewError as error:
            self.json_response({"error": error.code}, error.status)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (OSError, ValueError, TypeError):
            self.json_response({"error": "local_artifact_unavailable"}, 500)

    def send_media(self, media):
        if file_signature(media.fd) != media.signature:
            raise ReviewError("media_changed_restart_review", 409)
        try:
            start, end, partial = byte_range(self.headers.get("Range"), media.size)
        except ReviewError as error:
            body = json.dumps({"error": error.code}).encode()
            self.send_headers(416, "application/json", len(body), {"Content-Range": f"bytes */{media.size}"})
            if self.command != "HEAD":
                self.wfile.write(body)
            return
        length = max(0, end - start + 1) if media.size else 0
        extra = {"Accept-Ranges": "bytes"}
        if partial:
            extra["Content-Range"] = f"bytes {start}-{end}/{media.size}"
        self.send_headers(206 if partial else 200, media.content_type, length, extra)
        if self.command == "HEAD":
            return
        remaining = length
        while remaining:
            chunk = os.pread(media.fd, min(65536, remaining), start)
            if not chunk:
                break
            self.wfile.write(chunk)
            start += len(chunk)
            remaining -= len(chunk)

    def do_POST(self):
        try:
            self.trusted_request(mutation=True)
            path = urlsplit(self.path).path
            if path not in {"/api/annotations", "/api/annotations-v2"}:
                raise ReviewError("route_not_found", 404)
            if self.headers.get("Transfer-Encoding"):
                raise ReviewError("transfer_encoding_unsupported", 400)
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ReviewError("invalid_request_length") from exc
            if not 0 < length <= MAX_BODY:
                raise ReviewError("annotation_request_too_large_or_empty", 413)
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
                raise ReviewError("json_content_type_required", 415)
            self.connection.settimeout(10)
            body = self.rfile.read(length)
            if path == "/api/annotations-v2":
                try:
                    payload = json.loads(body, object_pairs_hook=annotation_v2.no_duplicate_keys,
                                         parse_constant=lambda _: (_ for _ in ()).throw(annotation_v2.AnnotationError("nonfinite_json_number")))
                except annotation_v2.AnnotationError as error:
                    raise ReviewError(error.code, error.status) from error
                self.json_response(self.server.session.annotate_v2(payload))
            else:
                payload = json.loads(body)
                self.json_response(self.server.session.annotate(payload))
        except ReviewError as error:
            self.json_response({"error": error.code}, error.status)
        except (ValueError, UnicodeDecodeError, TimeoutError, RecursionError):
            self.json_response({"error": "invalid_json_request"}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (OSError, TypeError):
            self.json_response({"error": "annotation_storage_failed"}, 500)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    serve = subparsers.add_parser("serve", help="Serve the private local review screen")
    serve.add_argument("run_dir", type=Path)
    serve.add_argument("--port", type=int, default=8765)
    read = subparsers.add_parser("annotations", help="Read source-bound saved annotations")
    read.add_argument("run_dir", type=Path)
    annotate = subparsers.add_parser("annotate", help="Save one source-bound annotation without a server")
    annotate.add_argument("run_dir", type=Path)
    annotate.add_argument("--input", type=Path, required=True)
    arguments = parser.parse_args()
    session = None
    server = None
    try:
        session = Session(arguments.run_dir, open_media=arguments.command == "serve")
        if arguments.command == "serve":
            if not 0 <= arguments.port <= 65535:
                raise ReviewError("invalid_port")
            server = ReviewHTTPServer(session, arguments.port)
            print(json.dumps({"url": f"http://127.0.0.1:{server.server_port}", "source_sha256": session.source_hash,
                              "status": "local_review_ready", "listening_acceptance": "not_established"}), flush=True)
            server.serve_forever(poll_interval=.25)
        else:
            if arguments.command == "annotate":
                if arguments.input.stat().st_size > MAX_BODY:
                    raise ReviewError("annotation_request_too_large_or_empty", 413)
                value = session.annotate(report.load_json(arguments.input))
            else:
                value = session.read_annotations()
            print(json.dumps({**value, "count": len(value["annotations"]),
                              "status": "annotations_saved" if arguments.command == "annotate" else "annotations_loaded"}, ensure_ascii=False))
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, ReviewError, TypeError, KeyError) as error:
        print(json.dumps({"error": error.code if isinstance(error, ReviewError) else "invalid_local_review_artifact"}), file=sys.stderr)
        return 1
    finally:
        if server:
            server.server_close()
        if session:
            session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
