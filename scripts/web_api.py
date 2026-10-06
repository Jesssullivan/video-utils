#!/usr/bin/env python3
"""Loopback control API for the bounded local job service (stdlib http.server only).

Versioned routes (contract ``docs/spec/sprints/WEB_UI_S2.md`` section 4)::

    GET  /api/v1/sources                          path-free source listing (?limit=1..500)
    POST /api/v1/sources                          admit an existing file under artifacts/runs by selector
    POST /api/v1/uploads                          raw upload into a private staging run, then admission
    GET  /api/v1/sources/{id}/media               admitted source bytes (re-hashed, inline, compare player)
    GET  /api/v1/sources/{id}/annotations         source-timed annotation_v2 store (public projection)
    POST /api/v1/sources/{id}/annotations         operator/browser annotation write (annotation_v2 semantics)
    GET  /api/v1/jobs                             job listing (?source_artifact_id=art_..&limit=1..200)
    POST /api/v1/jobs                             submit share_export over a source artifact id (idempotent)
    GET  /api/v1/jobs/{job_id}                    closed v1 job projection
    POST /api/v1/jobs/{job_id}/cancel             cancel (queued -> cancelled, running -> cancel_requested)
    POST /api/v1/jobs/{job_id}/retry              explicit retry of interrupted/failed jobs (attempt n+1)
    GET  /api/v1/artifacts/{artifact_id}          published job output bytes, re-hashed before sending

The six unversioned web_jobs routes (``/sources``, ``/jobs``, ``/jobs/{id}``,
``/jobs/{id}/cancel``, ``/jobs/{id}/retry``, ``/artifacts/{id}``) remain as
aliases in the same dispatch table and return the legacy projection
(``docs/spec/sprints/WEB_JOBS_S2.md`` section 4.4).

The server binds 127.0.0.1 only, checks Host/Origin, and requires a per-start
bearer token compared in constant time. It runs only as a foreground process
started by the operator (``serve``); Ctrl-C stops it. Stopping the server is not
a cancel: running attempts are reconciled on the next start. Uploads are off
unless ``--allow-uploads`` is passed. No response carries a host path, a
selector, worker stderr, the token or the state root.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import errno
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import sqlite3
import stat
import sys
import threading
from urllib.parse import parse_qsl, urlsplit

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import annotation_v2  # noqa: E402  (import only, never edited)
import artifact_ids  # noqa: E402  (import only, never edited)
import tool_api  # noqa: E402  (import only, never edited)
import web_jobs  # noqa: E402  (import only, never edited)
from web_jobs import WebJobs, WebJobsError  # noqa: E402

BIND_ADDRESS = '127.0.0.1'
MAX_BODY = 16 * 1024
MAX_DRAIN = 1024 * 1024
MAX_HANDLERS = 16
SOCKET_TIMEOUT_S = 10
STREAM_CHUNK = 1024 * 1024
API_SCHEMA_VERSION = 1
DEFAULT_MAX_UPLOAD_BYTES = 3 * 1024 ** 3
SOURCE_LIST_DEFAULT, SOURCE_LIST_MAX = 100, 500
JOB_LIST_DEFAULT, JOB_LIST_MAX = 100, 200
MAX_CLOCK_MANIFEST_BYTES = 64 * 1024

UPLOAD_TYPES = {
    'video/quicktime': '.mov',
    'video/mp4': '.mp4',
    'video/x-m4v': '.m4v',
    'video/x-matroska': '.mkv',
    'video/webm': '.webm',
}
SUFFIX_TYPES = {suffix: content_type for content_type, suffix in UPLOAD_TYPES.items()}
UPLOAD_RUN_PREFIX = 'web-upload-'
UPLOAD_RUN = re.compile(r'web-upload-\d{8}T\d{6}Z-([0-9a-f]{16})')
UPLOAD_LABEL = re.compile(r'[\x20-\x7e]{1,120}')
LIMIT = re.compile(r'[1-9][0-9]{0,3}')

LIFECYCLE_STEPS = (
    ('submitted', ('submitted', 'explicit_retry')),
    ('claimed', ('claimed',)),
    ('validating', ('validating',)),
    ('worker_started', ('worker_started',)),
    ('finalizing', ('finalizing',)),
    ('published', ('published', 'reconciled_publication')),
)
PROGRESS_REASON = ('lifecycle step count from the job event log; not an encode fraction; '
                   'share_export reports no incremental progress')
ETA_REASON = 'not estimated'
PHASE_REASON = ('latest job event reason code, read from a separate read-only snapshot; '
                'it may lead or lag state by one event')
SOURCE_STATE_REASON = 'listing does not re-hash; submit and media re-verify'
DURATION_KNOWN_REASON = ('worker video packet presentation extent of the newest succeeded job for this '
                         'source (source_end - source_start); not a container probe')
DURATION_UNKNOWN_REASON = 'unknown until a share_export job for this source succeeds; admission does not probe'
SOURCE_ID_BOUND_REASON = 'bound by the run manifest source hash'
SOURCE_ID_UNKNOWN_REASON = 'no run manifest binds this file to an original source'
CLOCK_BASIS = 'share_export video packet presentation extent (inference, not a container probe)'
PLAYER_CLOCK_REASON = ('span seconds = player currentTime + source_start_seconds; whether the browser media '
                       'clock matches the container presentation timeline is not verified')
BROWSER_AUTHOR = {'actor': 'operator', 'via': 'browser'}
BROWSER_BASES = ('operator_assertion', 'operator_context')

SEGMENT = r'([^/]{1,128})'
V1 = '/api/v1'
LIST_ACTIONS = ('list_sources', 'list_jobs')  # the only actions that accept a query string
# (pattern, route name, {method: action}, projection flavour)
ROUTES = (
    # Unversioned web_jobs aliases (legacy projection, unchanged behaviour).
    (re.compile(r'/sources'), 'sources', {'POST': 'admit'}, 'legacy'),
    (re.compile(r'/jobs'), 'jobs', {'POST': 'submit'}, 'legacy'),
    (re.compile(rf'/jobs/{SEGMENT}'), 'job', {'GET': 'job'}, 'legacy'),
    (re.compile(rf'/jobs/{SEGMENT}/cancel'), 'cancel', {'POST': 'cancel'}, 'legacy'),
    (re.compile(rf'/jobs/{SEGMENT}/retry'), 'retry', {'POST': 'retry'}, 'legacy'),
    (re.compile(rf'/artifacts/{SEGMENT}'), 'artifact', {'GET': 'artifact'}, 'legacy'),
    # Versioned routes.
    (re.compile(rf'{V1}/sources'), 'v1_sources', {'GET': 'list_sources', 'POST': 'admit'}, 'v1'),
    (re.compile(rf'{V1}/uploads'), 'v1_uploads', {'POST': 'upload'}, 'v1'),
    (re.compile(rf'{V1}/sources/{SEGMENT}/media'), 'v1_media', {'GET': 'media'}, 'v1'),
    (re.compile(rf'{V1}/sources/{SEGMENT}/annotations'), 'v1_annotations',
     {'GET': 'annotations_read', 'POST': 'annotations_write'}, 'v1'),
    (re.compile(rf'{V1}/jobs'), 'v1_jobs', {'GET': 'list_jobs', 'POST': 'submit'}, 'v1'),
    (re.compile(rf'{V1}/jobs/{SEGMENT}'), 'v1_job', {'GET': 'job'}, 'v1'),
    (re.compile(rf'{V1}/jobs/{SEGMENT}/cancel'), 'v1_cancel', {'POST': 'cancel'}, 'v1'),
    (re.compile(rf'{V1}/jobs/{SEGMENT}/retry'), 'v1_retry', {'POST': 'retry'}, 'v1'),
    (re.compile(rf'{V1}/artifacts/{SEGMENT}'), 'v1_artifact', {'GET': 'artifact'}, 'v1'),
)
# Kept for callers of the S2 web_jobs module surface: legacy route name -> method.
METHODS = {name: next(iter(methods)) for _, name, methods, flavour in ROUTES if flavour == 'legacy'}


def utc_stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def tool_envelope():
    """The typed envelope fields ``tool_api.execute`` attaches to a share_export result."""
    info = tool_api.descriptor(web_jobs.TOOL)
    return {'schema_version': 1, 'tool': web_jobs.TOOL, 'evidence_kind': info['evidence_kind'],
            'implementation_status': info['implementation_status'], 'limitations': list(info['limitations']),
            'skill': info['skill'], 'instrument_context': tool_api.load_registry()['instrument_context']}


def lifecycle_progress(reasons):
    """Count lifecycle steps reached in order for one attempt's event reasons."""
    seen = set(reasons)
    completed = 0
    for _step, aliases in LIFECYCLE_STEPS:
        if not seen.intersection(aliases):
            break
        completed += 1
    return {'completed': completed, 'denominator': len(LIFECYCLE_STEPS), 'unit': 'lifecycle_steps'}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class WebAnnotationSession:
    """Duck-typed ``annotation_v2.AnnotationStore`` session over a web clock manifest.

    No marker candidates and no provenance files exist for a web source, so
    ``marker_ids`` is empty and ``candidate_hash`` is None: a candidate-bound
    annotation is refused by annotation_v2 itself.
    """

    def __init__(self, root, manifest_path, manifest, manifest_hash, lock):
        timeline, pcm = manifest['timeline'], manifest['pcm']
        self.root = root
        self.manifest_path = manifest_path
        self.manifest = manifest
        self.manifest_hash = manifest_hash
        self.source_hash = manifest['source_sha256']
        self.audio_start = float(timeline['audio_start_seconds'])
        self.format_start = float(timeline['format_start_seconds'])
        self.duration = float(pcm['duration_seconds'])
        self.source_min = min(self.audio_start, self.format_start)
        self.source_max = self.audio_start + self.duration
        self.lock = lock
        self.provenance_hashes = {}
        self.marker_ids = set()
        self.candidate_hash = None


class WebAPIServer(ThreadingHTTPServer):
    """Loopback-only server; one ``WebJobs`` store; bounded handler threads."""

    daemon_threads = True
    request_queue_size = 8
    allow_reuse_address = False

    def __init__(self, jobs, port=0, token=None, *, allow_uploads=False, max_upload_bytes=DEFAULT_MAX_UPLOAD_BYTES):
        if not isinstance(port, int) or isinstance(port, bool) or not 0 <= port <= 65535:
            raise ValueError('port must be an integer in 0..65535')
        if not isinstance(max_upload_bytes, int) or isinstance(max_upload_bytes, bool) or max_upload_bytes <= 0:
            raise ValueError('max_upload_bytes must be a positive integer')
        self.jobs = jobs
        self.token = token or secrets.token_urlsafe(32)
        self.shutting_down = False
        self.allow_uploads = bool(allow_uploads)
        self.max_upload_bytes = min(max_upload_bytes, jobs.max_source_bytes)
        self.envelope = tool_envelope()
        self.handlers = threading.BoundedSemaphore(MAX_HANDLERS)
        self._annotation_locks = {}
        self._annotation_guard = threading.Lock()
        super().__init__((BIND_ADDRESS, port), Handler)

    @property
    def hosts(self):
        port = self.server_address[1]
        return {f'127.0.0.1:{port}', f'localhost:{port}'}

    def process_request(self, request, client_address):
        if not self.handlers.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.handlers.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.handlers.release()

    def stop(self):
        """Stop serving (no cancel). The caller closes the ``WebJobs`` store."""
        self.shutting_down = True
        self.shutdown()
        self.server_close()

    # ----------------------------------------------------------------- read-only store access

    @contextlib.contextmanager
    def read_only(self):
        """Separate read-only SQLite connection (WAL reader); never takes the write lock."""
        conn = sqlite3.connect(self.jobs.db_path.as_uri() + '?mode=ro', uri=True, timeout=5,
                               check_same_thread=False)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA busy_timeout=5000')
            version = conn.execute('PRAGMA user_version').fetchone()[0]
            if version != web_jobs.SCHEMA_VERSION:
                raise WebJobsError('schema_version_mismatch', 500, 'job database schema is not the version read here')
            yield conn
        finally:
            conn.close()

    def source_row(self, source_artifact_id):
        if not isinstance(source_artifact_id, str) or not web_jobs.ARTIFACT_ID.fullmatch(source_artifact_id):
            raise WebJobsError('malformed_id', 400, 'source artifact id must be art_ followed by 32 hex digits')
        with self.read_only() as conn:
            row = conn.execute('SELECT * FROM sources WHERE source_artifact_id = ?', (source_artifact_id,)).fetchone()
        if row is None:
            raise WebJobsError('unknown_source', 404, 'source artifact id is not admitted')
        return dict(row)

    # ----------------------------------------------------------------- projections

    def v1_projection(self, legacy):
        """Legacy projection plus phase, lifecycle progress, ETA, timestamps and the tool envelope."""
        job_id = legacy['job_id']
        with self.read_only() as conn:
            job = conn.execute('SELECT created_at, updated_at FROM jobs WHERE job_id = ?', (job_id,)).fetchone()
            events = conn.execute('SELECT attempt, reason_code FROM events WHERE job_id = ? ORDER BY seq',
                                  (job_id,)).fetchall()
            latest = conn.execute('SELECT max(attempt) FROM attempts WHERE job_id = ?', (job_id,)).fetchone()[0]
        if job is None:
            raise WebJobsError('unknown_job', 404, 'job id is not known to this state root')
        phase = events[-1]['reason_code'] if events else None
        progress = None
        if events:
            progress = lifecycle_progress(e['reason_code'] for e in events if e['attempt'] == latest)
        return {**legacy, 'schema_version': API_SCHEMA_VERSION, 'phase': phase, 'phase_reason': PHASE_REASON,
                'progress': progress, 'progress_reason': PROGRESS_REASON,
                'eta_seconds': None, 'eta_seconds_reason': ETA_REASON,
                'created_at': job['created_at'], 'updated_at': job['updated_at'],
                'tool_envelope': self.envelope}

    def newest_extent(self, conn, source_artifact_id, sha256):
        """(start, end, job_id, attempt) of the newest succeeded attempt's video packet extent, or None."""
        rows = conn.execute(
            "SELECT a.job_id, a.attempt, a.result_json FROM attempts a JOIN jobs j ON j.job_id = a.job_id "
            "WHERE j.source_artifact_id = ? AND a.state = 'succeeded' ORDER BY a.ended_at DESC, a.rowid DESC "
            'LIMIT 16', (source_artifact_id,)).fetchall()
        for row in rows:
            try:
                checks = json.loads(row['result_json']) if row['result_json'] else None
            except ValueError:
                continue
            if not isinstance(checks, dict) or checks.get('source_sha256') != sha256:
                continue
            proof = checks.get('video_proof') or {}
            start, end = proof.get('source_start_seconds'), proof.get('source_end_seconds')
            if _finite(start) and _finite(end) and end > start:
                return start, end, row['job_id'], row['attempt']
        return None

    def list_sources(self, query):
        limit = parse_query(query, {'limit': SOURCE_LIST_DEFAULT}, SOURCE_LIST_MAX)['limit']
        with self.read_only() as conn:
            rows = conn.execute('SELECT * FROM sources ORDER BY admitted_at DESC, rowid DESC LIMIT ?',
                                (limit + 1,)).fetchall()
            records = []
            for row in rows[:limit]:
                extent = self.newest_extent(conn, row['source_artifact_id'], row['sha256'])
                duration = (extent[1] - extent[0]) if extent else None
                records.append({
                    'source_artifact_id': row['source_artifact_id'], 'source_id': row['source_id'],
                    'source_id_reason': SOURCE_ID_BOUND_REASON if row['source_id'] else SOURCE_ID_UNKNOWN_REASON,
                    'source_binding': row['source_binding'], 'kind': row['kind'], 'sha256': row['sha256'],
                    'size_bytes': row['size_bytes'], 'admitted_at': row['admitted_at'],
                    'origin': 'upload' if row['selector'].startswith(UPLOAD_RUN_PREFIX) else 'run_selector',
                    'state': 'admitted', 'rechecked': False, 'state_reason': SOURCE_STATE_REASON,
                    'duration_seconds': duration,
                    'duration_seconds_reason': DURATION_KNOWN_REASON if extent else DURATION_UNKNOWN_REASON})
        return 200, {'schema_version': API_SCHEMA_VERSION, 'sources': records, 'truncated': len(rows) > limit}

    def list_jobs(self, query):
        values = parse_query(query, {'limit': JOB_LIST_DEFAULT, 'source_artifact_id': None}, JOB_LIST_MAX)
        source = values['source_artifact_id']
        if source is not None and not web_jobs.ARTIFACT_ID.fullmatch(source):
            raise WebJobsError('malformed_id', 400, 'source_artifact_id must be art_ followed by 32 hex digits')
        limit = values['limit']
        with self.read_only() as conn:
            where, args = ('WHERE j.source_artifact_id = ?', (source,)) if source else ('', ())
            rows = conn.execute(
                'SELECT j.job_id, j.state, j.reason_code, j.parameters_json, j.created_at, j.updated_at, '
                '(SELECT count(*) FROM attempts a WHERE a.job_id = j.job_id) AS attempt_count, '
                '(SELECT count(*) FROM artifacts r WHERE r.job_id = j.job_id) AS artifact_count '
                f'FROM jobs j {where} ORDER BY j.created_at DESC, j.rowid DESC LIMIT ?',
                (*args, limit + 1)).fetchall()
        jobs = [{'job_id': r['job_id'], 'state': r['state'], 'reason_code': r['reason_code'],
                 'parameters': json.loads(r['parameters_json']), 'created_at': r['created_at'],
                 'updated_at': r['updated_at'], 'attempt_count': r['attempt_count'],
                 'artifact_count': r['artifact_count']} for r in rows[:limit]]
        return 200, {'schema_version': API_SCHEMA_VERSION, 'jobs': jobs, 'truncated': len(rows) > limit}

    # ----------------------------------------------------------------- annotations

    def annotation_lock(self, source_artifact_id):
        with self._annotation_guard:
            return self._annotation_locks.setdefault(source_artifact_id, threading.Lock())

    def _private_dir(self, path):
        try:
            os.mkdir(path, 0o700)
        except FileExistsError:
            pass
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise WebJobsError('state_root_unsafe', 500, 'annotation directory must be a non-symlink directory')
        return path

    def annotation_session(self, source_artifact_id):
        """Annotation session bound to the no-clobber source clock manifest (section 4.5)."""
        source = self.source_row(source_artifact_id)
        base = self.jobs.state_root / 'annotations'
        root = base / source_artifact_id
        manifest_path = root / 'clock-manifest.json'
        if not os.path.lexists(manifest_path):
            with self.read_only() as conn:
                extent = self.newest_extent(conn, source_artifact_id, source['sha256'])
            if extent is None:  # nothing is created or saved without a measured clock
                raise WebJobsError('annotation_source_clock_unknown', 409,
                                   'source clock unknown; run the share preview first')
            self._private_dir(base)
            self._private_dir(root)
            start, end, job_id, attempt = extent
            manifest = {'schema': 'video-utils/web-annotation-clock', 'schema_version': 1,
                        'timeline': {'format_start_seconds': start, 'audio_start_seconds': start},
                        'pcm': {'duration_seconds': end - start},
                        'source_sha256': source['sha256'], 'source_artifact_id': source_artifact_id,
                        'job_id': job_id, 'attempt': attempt, 'clock_basis': CLOCK_BASIS}
            data = (json.dumps(manifest, sort_keys=True, allow_nan=False) + '\n').encode('ascii')
            with contextlib.suppress(FileExistsError):
                web_jobs._write_new_file(manifest_path, data)  # O_EXCL: written once, never clobbered
        for directory in (base, root):
            info = os.lstat(directory)
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise WebJobsError('state_root_unsafe', 500, 'annotation directory must be a non-symlink directory')
        try:
            manifest = annotation_v2.read_json(manifest_path, MAX_CLOCK_MANIFEST_BYTES)
            manifest_hash = annotation_v2.hash_provenance(manifest_path, max_bytes=MAX_CLOCK_MANIFEST_BYTES)
            if manifest.get('source_sha256') != source['sha256'] or manifest.get('source_artifact_id') != source_artifact_id:
                raise ValueError('clock manifest names another source')
            session = WebAnnotationSession(root, manifest_path, manifest, manifest_hash,
                                           self.annotation_lock(source_artifact_id))
        except (annotation_v2.AnnotationError, OSError, ValueError, KeyError, TypeError):
            raise WebJobsError('annotation_source_clock_unknown', 409, 'source clock manifest is unusable') from None
        return session

    @staticmethod
    def clock_public(session):
        manifest = session.manifest
        return {'source_start_seconds': session.source_min, 'source_end_seconds': session.source_max,
                'duration_seconds': session.duration, 'clock_basis': manifest['clock_basis'],
                'job_id': manifest['job_id'], 'attempt': manifest['attempt'],
                'manifest_sha256': session.manifest_hash,
                'player_clock_offset_verified': False, 'player_clock_offset_reason': PLAYER_CLOCK_REASON}

    def annotations_read(self, source_artifact_id):
        session = self.annotation_session(source_artifact_id)
        try:
            store = annotation_v2.AnnotationStore(session).read()
        except annotation_v2.AnnotationError as error:
            raise WebJobsError(error.code, error.status, 'annotation store refused the read') from None
        return 200, {'schema_version': API_SCHEMA_VERSION, 'store': store, 'clock': self.clock_public(session)}

    def annotations_write(self, source_artifact_id, body):
        if not isinstance(source_artifact_id, str) or not web_jobs.ARTIFACT_ID.fullmatch(source_artifact_id):
            raise WebJobsError('malformed_id', 400, 'source artifact id must be art_ followed by 32 hex digits')
        annotation = body.get('annotation')
        if not isinstance(annotation, dict):
            raise WebJobsError('invalid_annotation_request', 400, 'annotation must be an object')
        # Authorship boundary before any store I/O: the browser writes operator records only.
        if annotation.get('reported_by') != BROWSER_AUTHOR or annotation.get('basis') not in BROWSER_BASES:
            raise WebJobsError('annotation_actor_refused', 400,
                               'browser writes require operator/browser authorship and an operator basis')
        session = self.annotation_session(source_artifact_id)
        try:
            result = annotation_v2.AnnotationStore(session).write(body)
        except annotation_v2.AnnotationError as error:
            raise WebJobsError(error.code, error.status, 'annotation store refused the write') from None
        mutation = result.pop('mutation')
        return 200, {'schema_version': API_SCHEMA_VERSION, 'store': result, 'mutation': mutation,
                     'clock': self.clock_public(session)}


def parse_query(query, defaults, max_limit):
    """Strict listing query: known keys only, each at most once; limit 1..max_limit."""
    values = dict(defaults)
    if not query:
        return values
    try:
        pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True, max_num_fields=8)
    except ValueError:
        raise WebJobsError('bad_query', 400, 'query string is malformed') from None
    seen = set()
    for key, value in pairs:
        if key not in defaults or key in seen:
            raise WebJobsError('bad_query', 400, 'query names an unsupported or repeated parameter')
        seen.add(key)
        if key == 'limit':
            if not LIMIT.fullmatch(value) or int(value) > max_limit:
                raise WebJobsError('bad_query', 400, f'limit must be an integer in 1..{max_limit}')
            values[key] = int(value)
        else:
            values[key] = value
    return values


class Handler(BaseHTTPRequestHandler):
    server_version = 'VideoUtilsWebJobs/1'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(SOCKET_TIMEOUT_S)

    def log_message(self, *_args):
        pass

    # ----------------------------------------------------------------- responses

    def _headers(self, status, content_type, length, extra=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(length))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def _json(self, status, value):
        body = json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True).encode('ascii')
        self._headers(status, 'application/json', len(body))
        if self.command != 'HEAD':
            self.wfile.write(body)

    # ----------------------------------------------------------------- checks

    def _trusted(self):
        hosts = self.server.hosts
        if self.headers.get('Host') not in hosts:
            raise WebJobsError('host_refused', 403, 'unexpected Host header')
        origin = self.headers.get('Origin')
        if origin is not None and origin not in {f'http://{host}' for host in hosts}:
            raise WebJobsError('origin_refused', 403, 'unexpected Origin header')
        supplied = self.headers.get('Authorization', '')
        scheme, _, token = supplied.partition(' ')
        if (scheme != 'Bearer' or not token.isascii()
                or not hmac.compare_digest(token.encode('ascii'), self.server.token.encode('ascii'))):
            raise WebJobsError('token_required', 401, 'bearer token required')

    def _drain(self):
        """Read and discard a bounded unread body so an early refusal is not lost to a TCP reset."""
        if self._consumed or self.headers.get('Transfer-Encoding'):
            return
        self._consumed = True
        text = self.headers.get('Content-Length', '')
        if text.isdigit() and 0 < int(text) <= MAX_DRAIN:
            remaining = int(text)
            while remaining:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)

    def _body(self):
        if self.headers.get('Transfer-Encoding'):
            raise WebJobsError('length_required', 411, 'chunked bodies are unsupported; send Content-Length')
        length_text = self.headers.get('Content-Length')
        if length_text is None or not length_text.isdigit():
            raise WebJobsError('length_required', 411, 'Content-Length is required')
        length = int(length_text)
        if length > MAX_BODY:
            self._drain()
            raise WebJobsError('body_too_large', 413, f'request body exceeds {MAX_BODY} bytes')
        self._consumed = True
        data = self.rfile.read(length)
        if len(data) != length:
            raise WebJobsError('malformed_json', 400, 'request body ended early')
        content_type = self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
        if content_type != 'application/json':
            raise WebJobsError('content_type', 415, 'Content-Type must be application/json')
        try:
            body = web_jobs.strict_json(data)
        except ValueError:
            raise WebJobsError('malformed_json', 400, 'request body must be strict finite JSON without duplicate keys') from None
        if not isinstance(body, dict):
            raise WebJobsError('bad_type', 400, 'request body must be a JSON object')
        return body

    @staticmethod
    def _route(path):
        for pattern, name, methods, flavour in ROUTES:
            match = pattern.fullmatch(path)
            if match:
                return name, (match.group(1) if match.groups() else None), methods, flavour
        return None, None, None, None

    # ----------------------------------------------------------------- dispatch

    def _dispatch(self):
        self._consumed = False
        try:
            self._trusted()
            if self.server.shutting_down or self.server.jobs.closed:
                raise WebJobsError('shutting_down', 503, 'server is shutting down')
            parts = urlsplit(self.path)
            name, identifier, methods, flavour = self._route(parts.path)
            if name is None:
                raise WebJobsError('route_not_found', 404, 'unknown route')
            action = methods.get(self.command)
            if action is None:
                raise WebJobsError('method_not_allowed', 405, 'method not allowed for this route')
            if parts.query and action not in LIST_ACTIONS:
                raise WebJobsError('bad_query', 400, 'this route accepts no query string')
            self._act(action, identifier, flavour, parts.query)
        except WebJobsError as error:
            self._safe_drain()
            self._safe_json(error.status, error.body())
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception:  # never echo internals, paths or stderr
            self._safe_drain()
            self._safe_json(500, {'status': 'error', 'code': 'internal_error', 'error': 'internal_error'})

    def _act(self, action, identifier, flavour, query):
        server = self.server
        jobs = server.jobs
        if action == 'artifact':
            self._send_file(jobs.open_artifact(identifier), 'attachment')
            return
        if action == 'media':
            self._send_source_media(identifier)
            return
        if action == 'upload':
            status, value = self._upload()
        elif action == 'list_sources':
            status, value = server.list_sources(query)
        elif action == 'list_jobs':
            status, value = server.list_jobs(query)
        elif action == 'annotations_read':
            status, value = server.annotations_read(identifier)
        elif action == 'annotations_write':
            status, value = server.annotations_write(identifier, self._body())
        elif action == 'admit':
            status, value = jobs.admit_source(self._body())
        elif action == 'job':
            status, value = jobs.get_job(identifier)
        elif action == 'submit':
            status, value = jobs.submit(self._body())
        elif action == 'cancel':
            body = self._body()
            status, value = jobs.cancel(identifier, body)
        else:
            body = self._body()
            status, value = jobs.retry(identifier, body)
        if flavour == 'v1' and action in ('job', 'submit', 'cancel', 'retry'):
            value = server.v1_projection(value)
        self._json(status, value)

    def _safe_drain(self):
        try:
            self._drain()
        except (OSError, ValueError):
            pass

    def _safe_json(self, status, value):
        try:
            self._json(status, value)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass

    def _send_file(self, served, disposition):
        try:
            self._headers(200, served.content_type, served.size_bytes, {
                'X-Artifact-Sha256': served.sha256,
                'Content-Disposition': f'{disposition}; filename="{served.artifact_id}"',
                **({'Accept-Ranges': 'none'} if disposition == 'inline' else {})})
            offset = 0
            while offset < served.size_bytes:
                chunk = os.pread(served.descriptor, min(STREAM_CHUNK, served.size_bytes - offset), offset)
                if not chunk:
                    break
                self.wfile.write(chunk)
                offset += len(chunk)
            if disposition == 'inline' and web_jobs.file_signature(os.fstat(served.descriptor)) != served.signature:
                self.close_connection = True  # bytes changed mid-stream: the client sees a short body
        finally:
            served.close()

    # ----------------------------------------------------------------- source media

    def _send_source_media(self, source_artifact_id):
        server = self.server
        jobs = server.jobs
        row = server.source_row(source_artifact_id)
        selector = row['selector']
        index = artifact_ids.ArtifactIndex(jobs.runs_root, jobs.max_source_bytes)
        try:
            record = index.project(selector)
        except artifact_ids.ArtifactIdError as error:
            if error.code in ('not_regular_file', 'outside_runs_root'):
                raise WebJobsError('source_missing', 410, 'admitted source is no longer present') from None
            if error.code == 'symlink_component':
                raise WebJobsError('confinement_refused', 403, 'source location is not confined') from None
            raise WebJobsError('source_stale', 409, 'admitted source no longer verifies') from None
        if record['artifact_id'] != row['source_artifact_id'] or record['sha256'] != row['sha256']:
            raise WebJobsError('source_stale', 409, 'admitted source bytes changed; admit the new version')
        cursor = index.runs
        parts = selector.split('/')
        for part in parts[:-1]:
            cursor = cursor / part
            info = os.lstat(cursor)
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise WebJobsError('confinement_refused', 403, 'source location is not confined')
        try:
            descriptor, before = web_jobs._open_regular_nofollow(cursor / parts[-1])
        except FileNotFoundError:
            raise WebJobsError('source_missing', 410, 'admitted source is no longer present') from None
        except OSError as error:
            if error.errno == errno.ELOOP:
                raise WebJobsError('confinement_refused', 403, 'source leaf is a symbolic link') from None
            raise WebJobsError('confinement_refused', 403, 'source is not a regular file') from None
        try:
            digest, size = web_jobs.hash_descriptor(descriptor, jobs.max_source_bytes)
            after = os.fstat(descriptor)
        except BaseException:
            os.close(descriptor)
            raise
        if web_jobs.file_signature(before) != web_jobs.file_signature(after) or digest != row['sha256'] \
                or size != row['size_bytes']:
            os.close(descriptor)
            raise WebJobsError('source_stale', 409, 'admitted source bytes changed; admit the new version')
        suffix = Path(parts[-1]).suffix.lower()
        served = web_jobs.ServedArtifact(row['source_artifact_id'], descriptor, size, digest,
                                         SUFFIX_TYPES.get(suffix, 'application/octet-stream'),
                                         web_jobs.file_signature(after))
        self._send_file(served, 'inline')

    # ----------------------------------------------------------------- uploads

    def _upload(self):
        """Stream raw bytes into a new private staging run, then admit by selector (section 4.3)."""
        server = self.server
        jobs = server.jobs
        if not server.allow_uploads:
            raise WebJobsError('uploads_disabled', 403, 'uploads are disabled; start serve with --allow-uploads')
        if self.headers.get('Transfer-Encoding'):
            raise WebJobsError('length_required', 411, 'chunked uploads are unsupported; send Content-Length')
        length_text = self.headers.get('Content-Length')
        if length_text is None or not length_text.isdigit():
            raise WebJobsError('length_required', 411, 'Content-Length is required')
        content_type = self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
        suffix = UPLOAD_TYPES.get(content_type)
        if suffix is None:
            raise WebJobsError('upload_type_refused', 415, 'Content-Type must be an allowlisted video type')
        label = self.headers.get('X-Upload-Label')
        if label is not None and not UPLOAD_LABEL.fullmatch(label):
            raise WebJobsError('upload_label_refused', 400, 'X-Upload-Label must be 1..120 printable ASCII')
        length = int(length_text)
        if length > server.max_upload_bytes:
            raise WebJobsError('upload_too_large', 413, f'upload exceeds {server.max_upload_bytes} bytes')
        if length == 0:
            raise WebJobsError('upload_empty', 400, 'upload body is empty')
        suffix_hex = secrets.token_hex(8)
        run_name = f'{UPLOAD_RUN_PREFIX}{utc_stamp()}-{suffix_hex}'
        run_dir = jobs.runs_dir / run_name
        os.mkdir(run_dir, 0o700)  # refuses an existing path: an existing run is never written to
        try:
            upload_dir = run_dir / 'upload'
            os.mkdir(upload_dir, 0o700)
            name = f'source{suffix}'
            partial = upload_dir / f'{name}.partial'
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0)
            digest = hashlib.sha256()
            received = 0
            self._consumed = True
            descriptor = os.open(partial, flags, 0o600)
            try:
                while received < length:
                    chunk = self.rfile.read(min(STREAM_CHUNK, length - received))
                    if not chunk:
                        break
                    view = memoryview(chunk)
                    while view:
                        view = view[os.write(descriptor, view):]
                    digest.update(chunk)
                    received += len(chunk)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            if received != length:
                raise WebJobsError('upload_incomplete', 400, 'upload body ended before Content-Length bytes')
            os.rename(partial, upload_dir / name)
            web_jobs._fsync_directory(upload_dir)
            sha256 = digest.hexdigest()
            upload = {'upload_id': f'upl_{suffix_hex}', 'bytes': received, 'sha256': sha256}
            existing = self._existing_upload(sha256, run_name)
            if existing is not None:
                status, record = existing
                self._remove_upload_run(run_dir)
                return status, {'schema_version': API_SCHEMA_VERSION, 'upload': {**upload, 'deduplicated': True},
                                'source': record}
            receipt = {'schema': 'video-utils/web-upload', 'schema_version': 1, 'upload_id': upload['upload_id'],
                       'bytes': received, 'sha256': sha256, 'content_type': content_type, 'label': label,
                       'received_at': web_jobs.utc_now(), 'claim_class': 'hash_measurement'}
            web_jobs._write_new_file(run_dir / 'upload-receipt.json',
                                     (json.dumps(receipt, sort_keys=True) + '\n').encode('ascii'))
            status, record = jobs.admit_source({'selector': f'{run_name}/upload/{name}'})
            if record['sha256'] != sha256:
                raise WebJobsError('upload_hash_mismatch', 500, 'admitted bytes differ from the streamed bytes')
            return status, {'schema_version': API_SCHEMA_VERSION, 'upload': {**upload, 'deduplicated': False},
                            'source': record}
        except WebJobsError:
            self._remove_upload_run(run_dir)
            raise
        except (TimeoutError, ConnectionError):
            self._remove_upload_run(run_dir)
            raise WebJobsError('upload_incomplete', 400, 'upload body stalled or the connection dropped') from None
        except BaseException:
            self._remove_upload_run(run_dir)
            raise WebJobsError('internal_error', 500, 'internal_error') from None

    def _existing_upload(self, sha256, own_run):
        """Same bytes already admitted from an earlier upload run and still current -> (200, record)."""
        server = self.server
        with server.read_only() as conn:
            rows = conn.execute('SELECT selector FROM sources WHERE sha256 = ? ORDER BY admitted_at, rowid',
                                (sha256,)).fetchall()
        for row in rows:
            selector = row['selector']
            run = selector.split('/', 1)[0]
            if not UPLOAD_RUN.fullmatch(run) or run == own_run:
                continue
            try:
                return server.jobs.admit_source({'selector': selector})
            except WebJobsError:
                continue
        return None

    def _remove_upload_run(self, run_dir):
        """Remove only a staging run this request created (name pattern + direct child of runs)."""
        jobs = self.server.jobs
        with contextlib.suppress(FileNotFoundError):
            info = os.lstat(run_dir)
            if (stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode)
                    and run_dir.parent == jobs.runs_dir and UPLOAD_RUN.fullmatch(run_dir.name)):
                shutil.rmtree(run_dir)

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _dispatch


# --------------------------------------------------------------------------- foreground entrypoint

def serve(runs_root, state_root, port, out=sys.stdout, *, allow_uploads=False,
          max_upload_bytes=DEFAULT_MAX_UPLOAD_BYTES):
    """Foreground only: blocks until Ctrl-C/SIGTERM. No fork, no detach, no service registration."""
    jobs = WebJobs(runs_root, state_root)
    server = None
    try:
        jobs.start()
        server = WebAPIServer(jobs, port, allow_uploads=allow_uploads, max_upload_bytes=max_upload_bytes)
        out.write(json.dumps({'url': f'http://127.0.0.1:{server.server_address[1]}', 'token': server.token,
                              'api': V1, 'uploads': server.allow_uploads,
                              'max_upload_bytes': server.max_upload_bytes,
                              'foreground': True, 'daemon': False, 'stop': 'Ctrl-C',
                              'reconciliation': jobs.reconciliation}, sort_keys=True) + '\n')
        out.flush()

        def terminate(_signum, _frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, terminate)
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            pass
    finally:
        if server is not None:
            server.shutting_down = True
            server.server_close()
        jobs.close()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('serve', help='serve the loopback control API in the foreground')
    run.add_argument('--port', type=int, default=0, help='0 picks an ephemeral port')
    run.add_argument('--state-root', default=str(web_jobs.DEFAULT_STATE_ROOT))
    run.add_argument('--runs-root', default=str(web_jobs.ROOT), help='repository root holding artifacts/runs')
    run.add_argument('--allow-uploads', action='store_true',
                     help='enable POST /api/v1/uploads (writes new web-upload-* runs under artifacts/runs)')
    run.add_argument('--max-upload-bytes', type=int, default=DEFAULT_MAX_UPLOAD_BYTES)
    args = parser.parse_args(argv)
    try:
        return serve(args.runs_root, args.state_root, args.port, allow_uploads=args.allow_uploads,
                     max_upload_bytes=args.max_upload_bytes)
    except WebJobsError as error:
        print(json.dumps(error.body(), sort_keys=True), file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(json.dumps({'status': 'error', 'code': 'serve_failed', 'error': type(error).__name__}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
