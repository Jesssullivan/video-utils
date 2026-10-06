#!/usr/bin/env python3
"""Durable local job store and bounded supervisor for one admitted job type (stdlib only).

Contract: ``docs/spec/sprints/WEB_JOBS_S2.md``. One operator, one host, one
SQLite file (WAL, ``PRAGMA user_version = 1``) and one in-process supervisor
thread per state root. The only admitted job type is ``share_export`` (a short
preview/sharing MP4) executed through ``tool_api``'s validated argument
checks and fixed ``worker_command`` argv, timeout-bounded, in a new session so
that cancellation signals only the owned process group (R-N11).

Sources and outputs are addressed only by opaque IDs: sources by
``artifact_ids`` ``art_`` IDs confined to ``<runs_root>/artifacts/runs``;
outputs by ``art_`` IDs in a separate domain, published atomically into a
private per-job directory under the state root. No public record contains a
host path, a selector or worker stderr.

This module never forks a background service: it is imported by the
foreground ``web_api.py serve`` process or by tests. Listening acceptance,
low-register (~32 Hz) preservation, musical review, memory/CPU quotas,
exactly-once execution and any SLO remain explicitly unknown / not claimed.
"""
from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass
import datetime
import errno
import fcntl
import hashlib
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
import subprocess
import sys
import tempfile
import threading
import time

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import artifact_ids  # noqa: E402  (import only, never edited)
import tool_api  # noqa: E402  (import only, never edited)

ROOT = tool_api.ROOT
SCHEMA_VERSION = 1
TOOL = 'share_export'
DEFAULT_STATE_ROOT = ROOT / 'artifacts' / 'web-jobs'
DB_NAME = 'jobs.sqlite3'
LOCK_NAME = '.lock'
CLAIM_CLASS = 'job_state_record'
RULING = 'R-N11; R-HOOK-CONVERGENCE-20261004; TIN-3692 98cf680c-7299-4949-bfb2-60079053ad43'

STATES = ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'interrupted')
TERMINAL = ('succeeded', 'failed', 'cancelled', 'interrupted')
ATTEMPT_TRANSITIONS = frozenset({
    ('queued', 'running'), ('queued', 'cancelled'), ('queued', 'failed'),
    ('running', 'succeeded'), ('running', 'failed'), ('running', 'cancelled'), ('running', 'interrupted')})
# Job-level re-entry exists only through an explicit retry that inserts attempt n+1.
JOB_TRANSITIONS = ATTEMPT_TRANSITIONS | {('interrupted', 'queued'), ('failed', 'queued')}
RETRYABLE = ('interrupted', 'failed')
LIVENESS = ('dead', 'alive_unowned', 'unknown')

JOB_ID = re.compile(r'job_[0-9a-f]{32}')
ARTIFACT_ID = artifact_ids.ARTIFACT_ID
IDEMPOTENCY_KEY = re.compile(r'[A-Za-z0-9._-]{8,128}')
OUTPUT_DOMAIN = b'video-utils/web-job-artifact-id/v1\0'
# role -> (file name inside attempt-<n>/, content type, downloadable over HTTP)
ROLES = {
    'share_mp4': ('share.mp4', 'video/mp4', True),
    # The worker's sidecar receipt records host paths (source/staging); it is
    # listed with its hash but never served, so no response carries a path.
    'share_receipt': ('share.mp4.receipt.json', 'application/json', False),
    'publication': ('publication.json', 'application/json', True),
}
PARAMETER_KEYS = ('height', 'crf', 'audio_kbps', 'codec', 'timeout_seconds')
WORKER_KINDS = ('tool_api_share_export', 'test_stub')
FAULTS = (None, 'after_publish_before_commit')
SHARE_FAILURE_STATUSES = ('failed_no_export_published', 'exported_unreviewed_reporting_interrupted',
                          'publication_outcome_unknown')

MAX_WORKER_STDOUT = tool_api.MAX_WORKER_OUTPUT  # 2 MiB
MAX_PUBLICATION_BYTES = 64 * 1024
MAX_JSON_NESTING = 64
OUTER_HEADROOM_S = 10
POLL_S = 0.1
CHUNK = 1024 * 1024
PS_TIMEOUT_S = 5
CLOSE_JOIN_S = 60
REAP_TIMEOUT_S = 30

ADMISSION_PATH_ESCAPE = frozenset({'host_path_refused', 'outside_runs_root', 'symlink_component',
                                   'unsafe_component', 'filter_string_refused'})
MEDIA_FTYP_SUFFIXES = ('.mov', '.mp4', '.m4v')
MEDIA_EBML_SUFFIXES = ('.mkv', '.webm')
EBML_MAGIC = b'\x1a\x45\xdf\xa3'

UNKNOWN_REASONS = {
    'low_register_preservation': 'lossy AAC sharing derivative; ~32 Hz content is not measured by this lane',
    'musical_review': 'no note-correctness, missed-note or phrase verdicts are made by a job service',
    'memory_bytes_peak': 'not measured; no OS memory quota is applied',
    'cpu_seconds': 'not measured; no OS CPU quota is applied',
}


class WebJobsError(Exception):
    """Typed refusal. ``body()`` never contains a host path, selector or stderr."""

    def __init__(self, code, status=400, message='', **extra):
        super().__init__(f'{code}: {message}' if message else code)
        self.code = code
        self.status = status
        self.message = message or code
        self.extra = extra

    def body(self):
        return {'status': 'error', 'code': self.code, 'error': self.message, **self.extra}


class _SimulatedCrash(BaseException):
    """Test fault: the supervisor stops as if the process died at this point."""


class _Detached(BaseException):
    """close() while a worker runs: leave the attempt for startup reconciliation."""


# --------------------------------------------------------------------------- helpers

def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def parse_utc(text):
    return datetime.datetime.strptime(text, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=datetime.timezone.utc)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def strict_json(data, where='request'):
    """Strict finite JSON from bytes: UTF-8, bounded nesting, duplicate keys refused."""
    try:
        text = data.decode('utf-8') if isinstance(data, (bytes, bytearray)) else data
    except UnicodeDecodeError:
        raise ValueError(f'{where} is not UTF-8') from None
    depth = 0
    quoted = escaped = False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == '\\':
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in '[{':
            depth += 1
            if depth > MAX_JSON_NESTING:
                raise ValueError(f'{where} nesting exceeds {MAX_JSON_NESTING}')
        elif character in ']}':
            depth -= 1

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'{where} repeats a key')
            result[key] = value
        return result

    def constant(_value):
        raise ValueError(f'{where} has a non-finite number')

    def finite(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError(f'{where} has a non-finite number')
        return parsed

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant, parse_float=finite)
    except RecursionError:
        raise ValueError(f'{where} nesting exceeds parser limits') from None


def closed_object(body, required, optional=None):
    """Closed request object: unknown, missing and mistyped fields are typed 400s."""
    optional = optional or {}
    if not isinstance(body, dict):
        raise WebJobsError('bad_type', 400, 'request body must be a JSON object')
    unknown = set(body) - set(required) - set(optional)
    if unknown:
        raise WebJobsError('unknown_field', 400, f'request contains {len(unknown)} unsupported field(s)')
    missing = sorted(set(required) - set(body))
    if missing:
        raise WebJobsError('missing_field', 400, 'request lacks required field(s)', fields=missing)
    for name, kind in {**required, **optional}.items():
        if name in body:
            value = body[name]
            if not isinstance(value, kind) or (isinstance(value, bool) and kind is not bool):
                raise WebJobsError('bad_type', 400, f'field {name} has the wrong JSON type', field=name)
    return body


def output_artifact_id(job_id, attempt, role, content_sha256):
    digest = hashlib.sha256(OUTPUT_DOMAIN + job_id.encode('ascii') + b'\0' + str(attempt).encode('ascii')
                            + b'\0' + role.encode('ascii') + b'\0' + content_sha256.encode('ascii')).hexdigest()
    return 'art_' + digest[:32]


def file_signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def hash_descriptor(descriptor, limit=None):
    """SHA-256 and byte count read through one open descriptor with pread."""
    digest = hashlib.sha256()
    offset = 0
    while True:
        chunk = os.pread(descriptor, CHUNK, offset)
        if not chunk:
            break
        offset += len(chunk)
        if limit is not None and offset > limit:
            raise ValueError('file exceeds its byte bound')
        digest.update(chunk)
    return digest.hexdigest(), offset


def _open_regular_nofollow(path):
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_CLOEXEC', 0)
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise OSError(errno.EINVAL, 'not a regular file')
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor, info


def hash_regular_file(path, limit=None):
    """(sha256, size) of a non-symlink regular file with a stable identity."""
    descriptor, before = _open_regular_nofollow(path)
    try:
        digest, size = hash_descriptor(descriptor, limit)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if file_signature(before) != file_signature(after) or size != after.st_size:
        raise ValueError('file changed while hashing')
    return digest, size


def _fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_CLOEXEC', 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_new_file(path, data):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _inside(directory, ancestor):
    """Filesystem-identity containment of ``directory`` under ``ancestor`` (or equal)."""
    try:
        target = os.stat(ancestor)
    except OSError:
        return False
    key = (target.st_dev, target.st_ino)
    for candidate in (directory, *directory.parents):
        try:
            info = os.stat(candidate)
        except OSError:
            continue
        if (info.st_dev, info.st_ino) == key:
            return True
    return False


# --------------------------------------------------------------------------- process evidence

def process_probe(pid):
    """(stat, lstart) from ``ps``; ('', None) when no such process; (None, None) when ps is unavailable."""
    try:
        completed = subprocess.run(['ps', '-o', 'stat=', '-o', 'lstart=', '-p', str(int(pid))],
                                   stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                   timeout=PS_TIMEOUT_S, check=False)
    except (OSError, subprocess.SubprocessError):
        return None, None
    line = completed.stdout.strip()
    if not line:
        return ('', None) if completed.returncode in (0, 1) else (None, None)
    parts = line.split(None, 1)
    if len(parts) != 2:
        return parts[0], None
    return parts[0], ' '.join(parts[1].split())


def process_birth(pid):
    _stat, lstart = process_probe(pid)
    return lstart


def process_liveness(pid, birth):
    """dead / alive_unowned / unknown for a recorded worker. Never sends a signal."""
    if pid is None:
        return 'dead'
    with contextlib.suppress(ChildProcessError, OSError):
        # Reap the PID only if it is an exited child of this very process
        # (in-process restarts in tests); a reparented worker is unaffected.
        os.waitpid(pid, os.WNOHANG)
    try:
        os.kill(pid, 0)  # signal 0: existence check only, nothing is delivered
    except ProcessLookupError:
        return 'dead'
    except PermissionError:
        pass
    state, lstart = process_probe(pid)
    if state == '':
        return 'dead'
    if state and state.startswith('Z'):
        return 'dead'
    if lstart is None or birth is None:
        return 'unknown'
    return 'alive_unowned' if lstart == birth else 'dead'


def live_pgid(pid):
    try:
        return os.getpgid(pid)
    except (ProcessLookupError, PermissionError):
        return None


def group_alive(pgid):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# --------------------------------------------------------------------------- schema

def _transition_clause(pairs):
    grouped = {}
    for start, end in sorted(pairs):
        grouped.setdefault(start, []).append(end)
    terms = [f"(OLD.state = '{start}' AND NEW.state IN ({', '.join(repr(e) for e in ends)}))"
             for start, ends in grouped.items()]
    return ' OR '.join(terms)


STATE_CHECK = 'state IN (' + ', '.join(repr(s) for s in STATES) + ')'
SCHEMA_SQL = f"""
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE sources(
  source_artifact_id TEXT PRIMARY KEY, selector TEXT NOT NULL, sha256 TEXT NOT NULL,
  size_bytes INTEGER NOT NULL, kind TEXT NOT NULL, source_id TEXT, source_binding TEXT NOT NULL,
  admitted_at TEXT NOT NULL);
CREATE TABLE jobs(
  job_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE, fingerprint TEXT NOT NULL,
  tool TEXT NOT NULL, source_artifact_id TEXT NOT NULL REFERENCES sources(source_artifact_id),
  parameters_json TEXT NOT NULL, capability_revision TEXT NOT NULL,
  state TEXT NOT NULL CHECK ({STATE_CHECK}), reason_code TEXT,
  cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1)),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE attempts(
  job_id TEXT NOT NULL REFERENCES jobs(job_id), attempt INTEGER NOT NULL CHECK (attempt >= 1),
  state TEXT NOT NULL CHECK ({STATE_CHECK}), fence TEXT, instance_id TEXT, worker_kind TEXT,
  pid INTEGER, pgid INTEGER, worker_birth TEXT, started_at TEXT, ended_at TEXT, reason_code TEXT,
  cancel_receipt_json TEXT, liveness TEXT CHECK (liveness IS NULL OR liveness IN ('dead', 'alive_unowned', 'unknown')),
  result_json TEXT,
  PRIMARY KEY(job_id, attempt));
CREATE TABLE artifacts(
  artifact_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(job_id), attempt INTEGER NOT NULL,
  role TEXT NOT NULL, rel_path TEXT NOT NULL, sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
  content_type TEXT NOT NULL, published_at TEXT NOT NULL, UNIQUE(job_id, attempt, role));
CREATE TABLE events(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, attempt INTEGER, from_state TEXT,
  to_state TEXT, reason_code TEXT, at TEXT NOT NULL);
CREATE TRIGGER jobs_initial_state BEFORE INSERT ON jobs WHEN NEW.state <> 'queued'
BEGIN SELECT RAISE(ABORT, 'illegal_initial_state'); END;
CREATE TRIGGER attempts_initial_state BEFORE INSERT ON attempts WHEN NEW.state <> 'queued'
BEGIN SELECT RAISE(ABORT, 'illegal_initial_state'); END;
CREATE TRIGGER jobs_state_transition BEFORE UPDATE OF state ON jobs
WHEN NOT ({_transition_clause(JOB_TRANSITIONS)})
BEGIN SELECT RAISE(ABORT, 'illegal_transition'); END;
CREATE TRIGGER attempts_state_transition BEFORE UPDATE OF state ON attempts
WHEN NOT ({_transition_clause(ATTEMPT_TRANSITIONS)})
BEGIN SELECT RAISE(ABORT, 'illegal_transition'); END;
CREATE TRIGGER artifacts_no_update BEFORE UPDATE ON artifacts BEGIN SELECT RAISE(ABORT, 'immutable_artifact'); END;
CREATE TRIGGER artifacts_no_delete BEFORE DELETE ON artifacts BEGIN SELECT RAISE(ABORT, 'immutable_artifact'); END;
CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'append_only_event'); END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'append_only_event'); END;
"""


@dataclass
class ServedArtifact:
    """An open, verified, published artifact. The caller streams and closes ``descriptor``."""

    artifact_id: str
    descriptor: int
    size_bytes: int
    sha256: str
    content_type: str
    signature: tuple

    def close(self):
        with contextlib.suppress(OSError):
            os.close(self.descriptor)


# --------------------------------------------------------------------------- store + supervisor

class WebJobs:
    """Durable job store, admission, single-job-type supervisor and reconciliation."""

    def __init__(self, runs_root, state_root, *, max_source_bytes=artifact_ids.DEFAULT_MAX_BYTES,
                 queue_limit=4, cancel_grace_s=5.0, command_builder=None, fault=None):
        if not isinstance(max_source_bytes, int) or isinstance(max_source_bytes, bool) or max_source_bytes <= 0:
            raise ValueError('max_source_bytes must be a positive integer')
        if not isinstance(queue_limit, int) or isinstance(queue_limit, bool) or not 1 <= queue_limit <= 64:
            raise ValueError('queue_limit must be an integer in 1..64')
        if not isinstance(cancel_grace_s, (int, float)) or not 0 < cancel_grace_s <= 60:
            raise ValueError('cancel_grace_s must be in (0, 60]')
        if fault not in FAULTS:
            raise ValueError('unknown fault seam')
        if command_builder is not None and not callable(command_builder):
            raise ValueError('command_builder must be callable')
        self.max_source_bytes = max_source_bytes
        self.queue_limit = queue_limit
        self.cancel_grace_s = float(cancel_grace_s)
        self.command_builder = command_builder
        self.worker_kind = 'tool_api_share_export' if command_builder is None else 'test_stub'
        self.fault = fault
        try:
            index = artifact_ids.ArtifactIndex(runs_root, max_source_bytes)
        except artifact_ids.ArtifactIdError as error:
            raise WebJobsError('runs_root_invalid', 500, 'runs root lacks a confined artifacts/runs tree',
                               detail_code=error.code) from None
        self.runs_root = index.root
        self.runs_dir = index.runs
        self.state_root = self._prepare_state_root(Path(state_root))
        self.jobs_dir = self.state_root / 'jobs'
        self.db_path = self.state_root / DB_NAME
        self._lock_fd = self._acquire_lock()
        self.instance_id = secrets.token_hex(16)
        self._stopping = threading.Event()
        self._wake = threading.Event()
        self._cancel_wake = threading.Event()
        self._thread = None
        self._detached = []
        self._closed = False
        self.crashed = False
        self.last_error = None
        try:
            self._descriptor = tool_api.descriptor(TOOL)
            self.capability_revision = self._capability_revision()
            self._init_db()
            self.reconciliation = self.reconcile()
        except BaseException:
            self._release_lock()
            raise

    # ----------------------------------------------------------------- setup

    def _prepare_state_root(self, state_root):
        path = Path(os.path.abspath(os.fspath(state_root)))
        # Refuse an overlap with artifacts/runs before creating anything.
        existing, pending = path, []
        while not os.path.lexists(existing):
            pending.append(existing.name)
            existing = existing.parent
        try:
            projected = existing.resolve(strict=True).joinpath(*reversed(pending))
        except OSError:
            raise WebJobsError('state_root_unsafe', 500, 'state root ancestry cannot be resolved') from None
        runs = self.runs_dir.resolve()
        if (_inside(existing.resolve(), self.runs_dir) or projected.is_relative_to(runs)
                or runs.is_relative_to(projected)):
            raise WebJobsError('state_root_unsafe', 500, 'state root may not overlap artifacts/runs')
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.mkdir(path, 0o700)
            except FileExistsError:
                pass
            info = os.lstat(path)
        except OSError:
            raise WebJobsError('state_root_unsafe', 500, 'state root cannot be created') from None
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise WebJobsError('state_root_unsafe', 500, 'state root must be a non-symlink directory')
        resolved = path.resolve(strict=True)
        if _inside(resolved, self.runs_dir) or _inside(self.runs_dir, resolved):
            raise WebJobsError('state_root_unsafe', 500, 'state root may not overlap artifacts/runs')
        if info.st_mode & 0o077:
            os.chmod(resolved, 0o700)
        jobs = resolved / 'jobs'
        try:
            os.mkdir(jobs, 0o700)
        except FileExistsError:
            pass
        jobs_info = os.lstat(jobs)
        if stat.S_ISLNK(jobs_info.st_mode) or not stat.S_ISDIR(jobs_info.st_mode):
            raise WebJobsError('state_root_unsafe', 500, 'state jobs directory must be a non-symlink directory')
        return resolved

    def _acquire_lock(self):
        flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0)
        try:
            descriptor = os.open(self.state_root / LOCK_NAME, flags, 0o600)
        except OSError:
            raise WebJobsError('state_root_unsafe', 500, 'state lock cannot be opened') from None
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(descriptor)
            raise WebJobsError('state_root_locked', 409, 'another job service instance owns this state root') from None
        return descriptor

    def _release_lock(self):
        descriptor, self._lock_fd = getattr(self, '_lock_fd', None), None
        if descriptor is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            with contextlib.suppress(OSError):
                os.close(descriptor)

    def _capability_revision(self):
        descriptor_sha = sha256_hex(canonical(self._descriptor).encode('ascii'))
        script_sha = sha256_hex((ROOT / 'scripts' / 'share_export.py').read_bytes())
        return sha256_hex((descriptor_sha + script_sha).encode('ascii'))

    @contextlib.contextmanager
    def _db(self):
        conn = sqlite3.connect(self.db_path, timeout=5, isolation_level=None, check_same_thread=False)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA busy_timeout=5000')
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('PRAGMA synchronous=FULL')
            yield conn
        finally:
            conn.close()

    @contextlib.contextmanager
    def _tx(self):
        with self._db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                yield conn
            except BaseException:
                conn.execute('ROLLBACK')
                raise
            conn.execute('COMMIT')

    def _init_db(self):
        existed = self.db_path.exists()
        if existed:
            info = os.lstat(self.db_path)
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise WebJobsError('state_root_unsafe', 500, 'job database must be a regular file')
        with self._db() as conn:
            version = conn.execute('PRAGMA user_version').fetchone()[0]
            tables = conn.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
            if version == 0 and tables == 0:
                if conn.execute('PRAGMA journal_mode=WAL').fetchone()[0].lower() != 'wal':
                    raise WebJobsError('state_root_unsafe', 500, 'WAL journal mode unavailable')
                conn.executescript('BEGIN IMMEDIATE;\n' + SCHEMA_SQL
                                   + f'PRAGMA user_version = {SCHEMA_VERSION};\nCOMMIT;')
                with contextlib.suppress(OSError):
                    os.chmod(self.db_path, 0o600)
                conn.execute('INSERT INTO meta(key, value) VALUES (?, ?), (?, ?)',
                             ('schema_version', str(SCHEMA_VERSION), 'created_at', utc_now()))
            elif version != SCHEMA_VERSION:
                raise WebJobsError('schema_version_mismatch', 500,
                                   f'job database schema version {version} is not {SCHEMA_VERSION}; not migrated')
            elif conn.execute('PRAGMA journal_mode=WAL').fetchone()[0].lower() != 'wal':
                raise WebJobsError('state_root_unsafe', 500, 'WAL journal mode unavailable')
            conn.execute('INSERT INTO meta(key, value) VALUES (?, ?) '
                         'ON CONFLICT(key) DO UPDATE SET value = excluded.value',
                         ('instance_id', self.instance_id))

    # ----------------------------------------------------------------- lifecycle

    def start(self):
        if self._closed:
            raise WebJobsError('shutting_down', 503, 'job service is closed')
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name='web-jobs-supervisor', daemon=True)
            self._thread.start()

    def close(self):
        """Stop accepting work. Cancels nothing; a running attempt is left for reconciliation."""
        if self._closed:
            return
        self._closed = True
        self._stopping.set()
        self._wake.set()
        self._cancel_wake.set()
        if self._thread is not None:
            self._thread.join(timeout=CLOSE_JOIN_S)
        self._release_lock()

    @property
    def closed(self):
        return self._closed

    def _check_open(self):
        if self._closed:
            raise WebJobsError('shutting_down', 503, 'job service is closing')

    # ----------------------------------------------------------------- events

    @staticmethod
    def _event(conn, job_id, attempt, from_state, to_state, reason=None):
        conn.execute('INSERT INTO events(job_id, attempt, from_state, to_state, reason_code, at) '
                     'VALUES (?, ?, ?, ?, ?, ?)', (job_id, attempt, from_state, to_state, reason, utc_now()))

    def _phase(self, claim, phase):
        with self._tx() as conn:
            self._event(conn, claim['job_id'], claim['attempt'], 'running', 'running', phase)

    # ----------------------------------------------------------------- admission

    def _admission_error(self, error):
        if error.code in ADMISSION_PATH_ESCAPE:
            return WebJobsError('path_escape', 422, 'selector refused by artifact-id confinement',
                                detail_code=error.code)
        if error.code in ('not_regular_file', 'executable_refused', 'too_large', 'changed_during_hash'):
            return WebJobsError(error.code, 422, error.message)
        return WebJobsError('admission_refused', 422, 'source refused', detail_code=error.code)

    def _read_head(self, parts):
        """Leading bytes plus identity, only along a symlink-free confined walk; else None."""
        cursor = self.runs_dir
        for index, part in enumerate(parts):
            cursor = cursor / part
            try:
                info = os.lstat(cursor)
            except OSError:
                return None
            if stat.S_ISLNK(info.st_mode):
                return None
            if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
                return None
        try:
            descriptor, info = _open_regular_nofollow(cursor)
        except OSError:
            return None
        try:
            head = os.pread(descriptor, 64, 0)
        finally:
            os.close(descriptor)
        return cursor, head, file_signature(info)

    @staticmethod
    def _media_magic(selector, head):
        lower = selector.lower()
        if lower.endswith(MEDIA_FTYP_SUFFIXES):
            return len(head) >= 8 and head[4:8] == b'ftyp'
        if lower.endswith(MEDIA_EBML_SUFFIXES):
            return head[:4] == EBML_MAGIC
        return False

    def admit_source(self, body):
        """POST /sources. Returns (http_status, public record). No FFmpeg probe."""
        self._check_open()
        closed_object(body, {'selector': str})
        selector = body['selector']
        index = artifact_ids.ArtifactIndex(self.runs_root, self.max_source_bytes)
        try:
            parts = artifact_ids.check_selector(selector)
        except artifact_ids.ArtifactIdError as error:
            raise self._admission_error(error) from None
        head = self._read_head(parts)
        try:
            record = index.project(selector)
        except artifact_ids.ArtifactIdError as error:
            raise self._admission_error(error) from None
        if record['kind'] != 'video':
            raise WebJobsError('not_media', 422, 'source kind is not video')
        if head is None:
            raise WebJobsError('changed_during_hash', 422, 'source identity changed during admission')
        path, leading, signature = head
        try:
            after = file_signature(os.lstat(path))
        except OSError:
            raise WebJobsError('changed_during_hash', 422, 'source disappeared during admission') from None
        if after != signature or after[2] != record['size_bytes']:
            raise WebJobsError('changed_during_hash', 422, 'source identity changed during admission')
        if not self._media_magic(selector, leading):
            raise WebJobsError('not_media', 422, 'leading bytes lack the container signature for this suffix')
        with self._tx() as conn:
            cursor = conn.execute(
                'INSERT OR IGNORE INTO sources(source_artifact_id, selector, sha256, size_bytes, kind, source_id, '
                'source_binding, admitted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (record['artifact_id'], selector, record['sha256'], record['size_bytes'], record['kind'],
                 record['source_id'], record['source_binding'], utc_now()))
            created = cursor.rowcount == 1
            if not created:
                conn.execute('UPDATE sources SET source_id = ?, source_binding = ? WHERE source_artifact_id = ?',
                             (record['source_id'], record['source_binding'], record['artifact_id']))
        public = {'source_artifact_id': record['artifact_id'], 'source_id': record['source_id'],
                  'source_binding': record['source_binding'], 'kind': record['kind'],
                  'sha256': record['sha256'], 'size_bytes': record['size_bytes'], 'state': 'current'}
        return (201 if created else 200), public

    def _resolve_source(self, row):
        """Re-hash the admitted selector: ('current', private path) | ('stale'|'missing', None)."""
        try:
            index = artifact_ids.ArtifactIndex(self.runs_root, self.max_source_bytes)
            record = index.project(row['selector'])
        except artifact_ids.ArtifactIdError as error:
            if error.code in ('not_regular_file', 'outside_runs_root'):
                return 'missing', None
            return 'stale', None
        if record['artifact_id'] != row['source_artifact_id'] or record['sha256'] != row['sha256']:
            return 'stale', None
        return 'current', index.runs.joinpath(*row['selector'].split('/'))

    # ----------------------------------------------------------------- submission

    def normalize_parameters(self, parameters):
        if not isinstance(parameters, dict):
            raise WebJobsError('invalid_parameters', 400, 'parameters must be an object')
        if set(parameters) - set(PARAMETER_KEYS):
            raise WebJobsError('invalid_parameters', 400, 'parameters contain unsupported knobs')
        properties = self._descriptor['inputSchema']['properties']
        filled = {key: parameters.get(key, properties[key]['default']) for key in PARAMETER_KEYS}
        schema = {'type': 'object', 'properties': {key: properties[key] for key in PARAMETER_KEYS},
                  'required': [], 'additionalProperties': False}
        try:
            tool_api.validate(filled, schema, 'parameters')
        except tool_api.ValidationError as error:
            raise WebJobsError('invalid_parameters', 400, str(error)[:200]) from None
        if filled['height'] % 2:
            raise WebJobsError('invalid_parameters', 400, 'parameters.height must be even')
        return filled

    def fingerprint(self, source_row, parameters):
        return sha256_hex(canonical({
            'tool': TOOL, 'source_artifact_id': source_row['source_artifact_id'],
            'source_sha256': source_row['sha256'], 'parameters': parameters,
            'capability_revision': self.capability_revision}).encode('ascii'))

    def _source_row(self, conn, source_artifact_id):
        return conn.execute('SELECT * FROM sources WHERE source_artifact_id = ?', (source_artifact_id,)).fetchone()

    def _replay(self, existing, fingerprint):
        if existing['fingerprint'] != fingerprint:
            raise WebJobsError('idempotency_conflict', 409,
                               'idempotency key already names a different request')
        return 200, dict(self.project(existing['job_id']), replayed=True)

    def submit(self, body):
        """POST /jobs: (202 new | 200 replayed, projection)."""
        self._check_open()
        closed_object(body, {'tool': str, 'source_artifact_id': str, 'idempotency_key': str},
                      {'parameters': dict})
        if body['tool'] != TOOL:
            raise WebJobsError('tool_not_admitted', 400, 'only share_export is admitted as a web job')
        if not IDEMPOTENCY_KEY.fullmatch(body['idempotency_key']):
            raise WebJobsError('invalid_idempotency_key', 400, 'idempotency_key must match [A-Za-z0-9._-]{8,128}')
        if not ARTIFACT_ID.fullmatch(body['source_artifact_id']):
            raise WebJobsError('malformed_id', 400, 'source_artifact_id must be art_ followed by 32 hex digits')
        parameters = self.normalize_parameters(body.get('parameters', {}))
        key = body['idempotency_key']
        with self._db() as conn:
            source = self._source_row(conn, body['source_artifact_id'])
            if source is None:
                raise WebJobsError('unknown_source', 404, 'source artifact id is not admitted')
            fingerprint = self.fingerprint(source, parameters)
            existing = conn.execute('SELECT job_id, fingerprint FROM jobs WHERE idempotency_key = ?',
                                    (key,)).fetchone()
        if existing is not None:
            return self._replay(existing, fingerprint)
        state, _ = self._resolve_source(source)
        if state == 'stale':
            raise WebJobsError('source_stale', 409, 'admitted source bytes changed; admit the new version')
        if state == 'missing':
            raise WebJobsError('source_missing', 410, 'admitted source is no longer present')
        job_id = 'job_' + secrets.token_hex(16)
        now = utc_now()
        with self._tx() as conn:
            existing = conn.execute('SELECT job_id, fingerprint FROM jobs WHERE idempotency_key = ?',
                                    (key,)).fetchone()
            if existing is None:
                queued = conn.execute("SELECT count(*) FROM attempts WHERE state = 'queued'").fetchone()[0]
                if queued >= self.queue_limit:
                    raise WebJobsError('queue_full', 429, f'at most {self.queue_limit} jobs may be queued')
                conn.execute(
                    'INSERT INTO jobs(job_id, idempotency_key, fingerprint, tool, source_artifact_id, parameters_json, '
                    "capability_revision, state, reason_code, cancel_requested, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', NULL, 0, ?, ?)",
                    (job_id, key, fingerprint, TOOL, source['source_artifact_id'], canonical(parameters),
                     self.capability_revision, now, now))
                conn.execute("INSERT INTO attempts(job_id, attempt, state) VALUES (?, 1, 'queued')", (job_id,))
                self._event(conn, job_id, 1, None, 'queued', 'submitted')
        if existing is not None:
            return self._replay(existing, fingerprint)
        self._wake.set()
        return 202, dict(self.project(job_id), replayed=False)

    # ----------------------------------------------------------------- cancel / retry

    def _job_row(self, conn, job_id):
        if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
            raise WebJobsError('malformed_id', 400, 'job id must be job_ followed by 32 hex digits')
        row = conn.execute('SELECT * FROM jobs WHERE job_id = ?', (job_id,)).fetchone()
        if row is None:
            raise WebJobsError('unknown_job', 404, 'job id is not known to this state root')
        return row

    @staticmethod
    def _latest_attempt(conn, job_id):
        return conn.execute('SELECT * FROM attempts WHERE job_id = ? ORDER BY attempt DESC LIMIT 1',
                            (job_id,)).fetchone()

    def cancel(self, job_id, body=None):
        """POST /jobs/{id}/cancel: 200 cancelled (queued) | 202 cancel_requested | 200 late no-op."""
        self._check_open()
        closed_object({} if body is None else body, {})
        with self._tx() as conn:
            job = self._job_row(conn, job_id)
            state = job['state']
            now = utc_now()
            if state == 'queued':
                attempt = self._latest_attempt(conn, job_id)
                conn.execute("UPDATE attempts SET state = 'cancelled', ended_at = ?, reason_code = 'cancel_requested' "
                             'WHERE job_id = ? AND attempt = ?', (now, job_id, attempt['attempt']))
                conn.execute("UPDATE jobs SET state = 'cancelled', reason_code = 'cancel_requested', "
                             'cancel_requested = 1, updated_at = ? WHERE job_id = ?', (now, job_id))
                self._event(conn, job_id, attempt['attempt'], 'queued', 'cancelled', 'cancel_requested')
                status, late = 200, False
            elif state == 'running':
                attempt = self._latest_attempt(conn, job_id)
                if not job['cancel_requested']:
                    conn.execute('UPDATE jobs SET cancel_requested = 1, updated_at = ? WHERE job_id = ?', (now, job_id))
                    self._event(conn, job_id, attempt['attempt'], 'running', 'running', 'cancel_requested')
                status, late = 202, False
            else:
                status, late = 200, True
        self._cancel_wake.set()
        return status, dict(self.project(job_id), late_cancel=late)

    def retry(self, job_id, body=None):
        """POST /jobs/{id}/retry: insert attempt n+1; earlier attempts and files are untouched."""
        self._check_open()
        closed_object({} if body is None else body, {})
        with self._db() as conn:
            job = self._job_row(conn, job_id)
            if job['state'] not in RETRYABLE:
                raise WebJobsError('not_retryable', 409, f'only {"/".join(RETRYABLE)} jobs can be retried',
                                   state=job['state'])
            last = self._latest_attempt(conn, job_id)
            source = self._source_row(conn, job['source_artifact_id'])
        if last['liveness'] in ('alive_unowned', 'unknown'):
            observed = process_liveness(last['pid'], last['worker_birth'])
            with self._db() as conn:
                conn.execute('UPDATE attempts SET liveness = ? WHERE job_id = ? AND attempt = ?',
                             (observed, job_id, last['attempt']))
            if observed != 'dead':
                raise WebJobsError('prior_worker_alive', 409,
                                   'an earlier worker this instance did not start may still run; it is not signalled',
                                   liveness=observed)
        state, _ = self._resolve_source(source)
        if state == 'stale':
            raise WebJobsError('source_stale', 409, 'admitted source bytes changed; admit the new version')
        if state == 'missing':
            raise WebJobsError('source_missing', 410, 'admitted source is no longer present')
        with self._tx() as conn:
            job = self._job_row(conn, job_id)
            current = self._latest_attempt(conn, job_id)
            if job['state'] not in RETRYABLE or current['attempt'] != last['attempt']:
                raise WebJobsError('not_retryable', 409, 'job changed concurrently', state=job['state'])
            queued = conn.execute("SELECT count(*) FROM attempts WHERE state = 'queued'").fetchone()[0]
            if queued >= self.queue_limit:
                raise WebJobsError('queue_full', 429, f'at most {self.queue_limit} jobs may be queued')
            number = last['attempt'] + 1
            conn.execute("INSERT INTO attempts(job_id, attempt, state) VALUES (?, ?, 'queued')", (job_id, number))
            conn.execute("UPDATE jobs SET state = 'queued', reason_code = NULL, cancel_requested = 0, updated_at = ? "
                         'WHERE job_id = ?', (utc_now(), job_id))
            self._event(conn, job_id, number, job['state'], 'queued', 'explicit_retry')
        self._wake.set()
        return 202, self.project(job_id)

    # ----------------------------------------------------------------- supervisor

    def _loop(self):
        while not self._stopping.is_set():
            try:
                claim = self._claim()
            except Exception as error:  # store contention: report, back off, keep serving
                self.last_error = type(error).__name__
                self._wake.wait(0.5)
                self._wake.clear()
                continue
            if claim is None:
                self._wake.wait(0.2)
                self._wake.clear()
                continue
            try:
                self._run_attempt(claim)
            except _SimulatedCrash:
                self.crashed = True
                return
            except _Detached:
                return
            except Exception as error:
                self.last_error = type(error).__name__
                with contextlib.suppress(Exception):
                    self._finish(claim, 'failed', 'internal_error')

    def _claim(self):
        if self._stopping.is_set():
            return None
        with self._tx() as conn:
            row = conn.execute(
                "SELECT a.job_id, a.attempt FROM attempts a WHERE a.state = 'queued' ORDER BY a.rowid LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            job = conn.execute('SELECT * FROM jobs WHERE job_id = ?', (row['job_id'],)).fetchone()
            fence = secrets.token_hex(16)
            now = utc_now()
            conn.execute("UPDATE attempts SET state = 'running', fence = ?, instance_id = ?, worker_kind = ?, "
                         'started_at = ? WHERE job_id = ? AND attempt = ?',
                         (fence, self.instance_id, self.worker_kind, now, row['job_id'], row['attempt']))
            conn.execute("UPDATE jobs SET state = 'running', updated_at = ? WHERE job_id = ?", (now, row['job_id']))
            self._event(conn, row['job_id'], row['attempt'], 'queued', 'running', 'claimed')
            source = self._source_row(conn, job['source_artifact_id'])
        return {'job_id': row['job_id'], 'attempt': row['attempt'], 'fence': fence,
                'parameters': json.loads(job['parameters_json']), 'source': dict(source)}

    def _finish(self, claim, state, reason, *, receipt=None, result=None, artifacts=(), event_reason=None):
        """Fenced terminal transition of a running attempt and its job."""
        now = utc_now()
        with self._tx() as conn:
            cursor = conn.execute(
                'UPDATE attempts SET state = ?, ended_at = ?, reason_code = ?, cancel_receipt_json = ?, '
                "result_json = ? WHERE job_id = ? AND attempt = ? AND state = 'running' AND fence = ?",
                (state, now, reason, canonical(receipt) if receipt is not None else None,
                 canonical(result) if result is not None else None,
                 claim['job_id'], claim['attempt'], claim['fence']))
            if cursor.rowcount != 1:
                raise WebJobsError('fence_lost', 409, 'attempt is no longer owned by this supervisor')
            for row in artifacts:
                conn.execute('INSERT INTO artifacts(artifact_id, job_id, attempt, role, rel_path, sha256, size_bytes, '
                             'content_type, published_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                             (row['artifact_id'], claim['job_id'], claim['attempt'], row['role'], row['rel_path'],
                              row['sha256'], row['size_bytes'], row['content_type'], now))
            conn.execute('UPDATE jobs SET state = ?, reason_code = ?, updated_at = ? WHERE job_id = ?',
                         (state, None if state == 'succeeded' else reason, now, claim['job_id']))
            self._event(conn, claim['job_id'], claim['attempt'], 'running', state, event_reason or reason)

    def _cancel_flag(self, claim):
        with self._db() as conn:
            row = conn.execute('SELECT cancel_requested FROM jobs WHERE job_id = ?', (claim['job_id'],)).fetchone()
        return bool(row and row['cancel_requested'])

    def _job_directory(self, job_id):
        path = self.jobs_dir / job_id
        try:
            os.mkdir(path, 0o700)
        except FileExistsError:
            pass
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise WebJobsError('state_root_unsafe', 500, 'job directory must be a non-symlink directory')
        return path

    def _build_command(self, args):
        tool_api.validate(args, self._descriptor['inputSchema'])
        tool_api.validate_tool_arguments(TOOL, args)
        if self.command_builder is None:
            return tool_api.worker_command(TOOL, args)
        command = self.command_builder(dict(args))
        if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
            raise tool_api.ToolError('test command builder must return a non-empty argv list')
        return command

    def _run_attempt(self, claim):
        job_dir = self._job_directory(claim['job_id'])
        state, source_path = self._resolve_source(claim['source'])
        if state != 'current':
            self._finish(claim, 'failed', 'source_changed' if state == 'stale' else 'source_missing')
            return
        staging = job_dir / f'.staging-{claim["attempt"]}-{secrets.token_hex(8)}'
        os.mkdir(staging, 0o700)
        args = {'source': str(source_path), 'output': str(staging / ROLES['share_mp4'][0]), **claim['parameters']}
        self._phase(claim, 'validating')
        try:
            command = self._build_command(args)
        except (tool_api.ValidationError, tool_api.ToolError, ValueError, OSError):
            self._finish(claim, 'failed', 'launch_refused')
            return
        timeout = claim['parameters']['timeout_seconds'] + OUTER_HEADROOM_S
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            try:
                process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stdout,
                                           stderr=stderr, start_new_session=True, close_fds=True)
            except OSError:
                self._finish(claim, 'failed', 'launch_failed')
                return
            pgid = live_pgid(process.pid)
            birth = process_birth(process.pid)
            with self._tx() as conn:
                conn.execute("UPDATE attempts SET pid = ?, pgid = ?, worker_birth = ? WHERE job_id = ? AND attempt = ? "
                             "AND state = 'running' AND fence = ?",
                             (process.pid, pgid, birth, claim['job_id'], claim['attempt'], claim['fence']))
                self._event(conn, claim['job_id'], claim['attempt'], 'running', 'running', 'worker_started')
            outcome, receipt = self._wait(claim, process, pgid, timeout)
            if outcome == 'cancelled':
                self._remove_private_dir(staging, job_dir)
                self._finish(claim, 'cancelled', 'cancel_requested', receipt=receipt)
                return
            if outcome == 'deadline':
                self._finish(claim, 'failed', 'deadline_exceeded', receipt=receipt)
                return
            self._complete(claim, process.returncode, stdout, args, staging, job_dir)

    def _wait(self, claim, process, pgid, timeout):
        deadline = time.monotonic() + timeout
        while True:
            if process.poll() is not None:
                return 'exited', None
            if self._stopping.is_set():
                self._detached.append(process)
                raise _Detached()
            if self._cancel_flag(claim):
                return 'cancelled', self._stop_group(claim, process, pgid, 'cancel_requested')
            if time.monotonic() >= deadline:
                return 'deadline', self._stop_group(claim, process, pgid, f'outer deadline exceeded ({timeout}s)')
            self._cancel_wake.wait(POLL_S)
            self._cancel_wake.clear()

    def _requested_at(self, claim):
        with self._db() as conn:
            row = conn.execute("SELECT at FROM events WHERE job_id = ? AND attempt = ? AND reason_code = "
                               "'cancel_requested' ORDER BY seq LIMIT 1",
                               (claim['job_id'], claim['attempt'])).fetchone()
        return row['at'] if row else None

    def _stop_group(self, claim, process, pgid, reason):
        """Terminate only the process group this instance created; receipt per R-N11."""
        ack_at = utc_now()
        observed = live_pgid(process.pid)
        owned = observed is not None and observed == pgid == process.pid
        signals = []
        signal_at = None
        if owned:
            signal_at = utc_now()
            with contextlib.suppress(ProcessLookupError):
                os.killpg(pgid, signal.SIGTERM)
                signals.append('SIGTERM')
            target = 'owned_process_group'
        elif observed is None:
            target = 'already_exited'
        else:
            target = 'pgid_mismatch_not_signalled'
        try:
            process.wait(timeout=self.cancel_grace_s)
        except subprocess.TimeoutExpired:
            if live_pgid(process.pid) == pgid == process.pid:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(pgid, signal.SIGKILL)
                    signals.append('SIGKILL')
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=REAP_TIMEOUT_S)
        group_empty = None
        if owned:
            # The leader is reaped; remaining members of the owned group (worker
            # children that stayed in it) still hold the group id.
            end = time.monotonic() + self.cancel_grace_s
            while group_alive(pgid) and time.monotonic() < end:
                time.sleep(0.02)
            if group_alive(pgid):
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(pgid, signal.SIGKILL)
                    signals.append('SIGKILL_group_remainder')
                end = time.monotonic() + self.cancel_grace_s
                while group_alive(pgid) and time.monotonic() < end:
                    time.sleep(0.02)
            group_empty = not group_alive(pgid)
        return {'actor': 'video-utils/web_jobs', 'instance_id': self.instance_id, 'reason': reason,
                'ruling': RULING,
                'target_ownership': {'pid': process.pid, 'recorded_pgid': pgid, 'observed_pgid': observed,
                                     'created_by_this_instance': True, 'new_session_requested': True},
                'requested_at': self._requested_at(claim) if reason == 'cancel_requested' else None,
                'ack_at': ack_at, 'signal_at': signal_at, 'observed_stop_at': utc_now(),
                'signal_target': target, 'signals_sent': signals, 'returncode': process.returncode,
                'group_empty_observed': group_empty,
                'limitation': 'worker children that start their own session are outside the owned group'}

    def _remove_private_dir(self, path, job_dir):
        """Remove a job-private staging directory (never anything outside the job directory)."""
        with contextlib.suppress(FileNotFoundError):
            info = os.lstat(path)
            if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode) and path.parent == job_dir \
                    and path.name.startswith('.staging-'):
                shutil.rmtree(path)

    @staticmethod
    def _worker_checks(result):
        """Bounded, path-free projection of the worker's structural checks."""
        if not isinstance(result, dict):
            return None
        projected = {'status': result.get('status')}
        if result.get('status') != 'exported_unreviewed':
            code = result.get('code')
            projected['code'] = code[:128] if isinstance(code, str) else None
            return projected
        video = result.get('video_proof') if isinstance(result.get('video_proof'), dict) else {}
        audio = result.get('audio_proof') if isinstance(result.get('audio_proof'), dict) else {}
        output = result.get('output') if isinstance(result.get('output'), dict) else {}
        source = result.get('source') if isinstance(result.get('source'), dict) else {}
        projected.update({
            'source_sha256': source.get('sha256'), 'source_bytes': source.get('bytes'),
            'output_sha256': output.get('sha256'), 'output_bytes': output.get('bytes'),
            'byte_reduction_fraction': result.get('byte_reduction_fraction'),
            'settings': result.get('settings'), 'codecs': result.get('codecs'),
            'dimensions': result.get('dimensions'), 'video_encode_count': result.get('video_encode_count'),
            'video_proof': {key: video.get(key) for key in (
                'method', 'packet_count', 'maximum_pts_delta_seconds', 'tail_extent_delta_seconds',
                'tolerance_seconds', 'source_start_seconds', 'source_end_seconds',
                'source_full_frame_decode_verified', 'physical_capture_sync_verified') if key in video} or None,
            'audio_proof': {key: audio.get(key) for key in (
                'method', 'sample_rate', 'channels', 'priming_padding_allowance_seconds',
                'exact_pcm_sample_identity', 'audio_reencoded') if key in audio} or None,
            'loudness': result.get('loudness'),
            'output_decode_errors_checked': result.get('output_decode_errors_checked'),
            'master_adopted': result.get('master_adopted'), 'listening_accepted': result.get('listening_accepted'),
        })
        return projected

    def _complete(self, claim, returncode, stdout, args, staging, job_dir):
        stdout.seek(0, os.SEEK_END)
        if stdout.tell() > MAX_WORKER_STDOUT:
            self._finish(claim, 'failed', 'malformed_result')
            return
        stdout.seek(0)
        try:
            result = strict_json(stdout.read(), 'worker result')
        except ValueError:
            result = None
        if returncode != 0:
            self._finish(claim, 'failed', 'worker_failed', result={'returncode': returncode})
            return
        if not isinstance(result, dict):
            self._finish(claim, 'failed', 'malformed_result')
            return
        try:
            tool_api.classify_share_export_result(result, args)
        except tool_api.ToolError as error:
            status = result.get('status')
            if error.receipt and status == 'rejected':
                reason = 'worker_rejected'
            elif error.receipt and status in SHARE_FAILURE_STATUSES:
                reason = 'worker_failed'
            else:
                reason = 'malformed_result'
            checks = self._worker_checks(result) if reason != 'malformed_result' else None
            self._finish(claim, 'failed', reason, result=checks)
            return
        checks = self._worker_checks(result)
        if result['source']['sha256'] != claim['source']['sha256']:
            self._finish(claim, 'failed', 'source_changed', result=checks)
            return
        self._phase(claim, 'finalizing')
        try:
            rows = self._publish(claim, result, staging, job_dir, checks)
        except _SimulatedCrash:
            raise
        except (OSError, ValueError, WebJobsError):
            self._finish(claim, 'failed', 'publication_failed', result=checks)
            return
        self._finish(claim, 'succeeded', None, result=checks, artifacts=rows, event_reason='published')

    def _publish(self, claim, result, staging, job_dir, checks):
        """Verify staged outputs, write fenced publication.json, rename staging -> attempt-<n>."""
        job_id, attempt = claim['job_id'], claim['attempt']
        expected = {
            'share_mp4': (result['output']['sha256'], result['output']['bytes']),
            'share_receipt': (result['output']['receipt_sha256'], None),
        }
        target = job_dir / f'attempt-{attempt}'
        rows = []
        for role, (digest, size) in expected.items():
            name, content_type, _ = ROLES[role]
            observed_digest, observed_size = hash_regular_file(staging / name)
            if observed_digest != digest or (size is not None and observed_size != size):
                raise ValueError(f'staged {role} does not match the worker result')
            rows.append({'artifact_id': output_artifact_id(job_id, attempt, role, observed_digest), 'role': role,
                         'name': name, 'sha256': observed_digest, 'size_bytes': observed_size,
                         'content_type': content_type})
        allowed = {ROLES['share_mp4'][0], ROLES['share_receipt'][0]}
        for entry in os.scandir(staging):
            if entry.name in allowed:
                continue
            if entry.name.startswith('.share-export-') and entry.is_dir(follow_symlinks=False):
                shutil.rmtree(entry.path)  # worker intermediates in this job-private staging dir
                continue
            raise ValueError('unexpected entry in job staging directory')
        publication = {'schema': 'video-utils/web-job-publication', 'schema_version': 1, 'job_id': job_id,
                       'attempt': attempt, 'fence': claim['fence'], 'tool': TOOL, 'worker_kind': self.worker_kind,
                       'source_artifact_id': claim['source']['source_artifact_id'],
                       'source_sha256': claim['source']['sha256'], 'artifacts': rows, 'worker_checks': checks,
                       'claim_class': CLAIM_CLASS, 'master_adopted': False, 'listening_accepted': False,
                       'published_at': utc_now()}
        data = (canonical(publication) + '\n').encode('ascii')
        if len(data) > MAX_PUBLICATION_BYTES:
            raise ValueError('publication record exceeds its byte bound')
        _write_new_file(staging / ROLES['publication'][0], data)
        _fsync_directory(staging)
        if os.path.lexists(target):
            raise ValueError('attempt publication directory already exists')
        os.rename(staging, target)
        _fsync_directory(job_dir)
        rows.append({'artifact_id': output_artifact_id(job_id, attempt, 'publication', sha256_hex(data)),
                     'role': 'publication', 'name': ROLES['publication'][0], 'sha256': sha256_hex(data),
                     'size_bytes': len(data), 'content_type': ROLES['publication'][1]})
        for row in rows:
            row['rel_path'] = f'jobs/{job_id}/attempt-{attempt}/{row.pop("name")}'
        if self.fault == 'after_publish_before_commit':
            raise _SimulatedCrash()
        return rows

    # ----------------------------------------------------------------- reconciliation

    def _adoptable(self, row):
        """Rows for a fenced, hash-verified publication of this attempt, else None."""
        job_id, attempt = row['job_id'], row['attempt']
        target = self.jobs_dir / job_id / f'attempt-{attempt}'
        for directory in (self.jobs_dir / job_id, target):
            try:
                info = os.lstat(directory)
            except OSError:
                return None
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                return None
        try:
            descriptor, _ = _open_regular_nofollow(target / ROLES['publication'][0])
        except OSError:
            return None
        try:
            digest, size = hash_descriptor(descriptor, MAX_PUBLICATION_BYTES)
            data = os.pread(descriptor, MAX_PUBLICATION_BYTES + 1, 0)
        except (OSError, ValueError):
            return None
        finally:
            os.close(descriptor)
        try:
            publication = strict_json(data, 'publication')
        except ValueError:
            return None
        if (not isinstance(publication, dict) or publication.get('job_id') != job_id
                or publication.get('attempt') != attempt or publication.get('fence') != row['fence']
                or not isinstance(publication.get('artifacts'), list)):
            return None
        rows = []
        for item in publication['artifacts']:
            if not isinstance(item, dict) or item.get('role') not in ('share_mp4', 'share_receipt'):
                return None
            name, content_type, _ = ROLES[item['role']]
            if item.get('name') != name:
                return None
            try:
                observed, observed_size = hash_regular_file(target / name)
            except (OSError, ValueError):
                return None
            if (observed != item.get('sha256') or observed_size != item.get('size_bytes')
                    or item.get('artifact_id') != output_artifact_id(job_id, attempt, item['role'], observed)):
                return None
            rows.append({'artifact_id': item['artifact_id'], 'role': item['role'], 'sha256': observed,
                         'size_bytes': observed_size, 'content_type': content_type,
                         'rel_path': f'jobs/{job_id}/attempt-{attempt}/{name}'})
        if sorted(r['role'] for r in rows) != ['share_mp4', 'share_receipt']:
            return None
        rows.append({'artifact_id': output_artifact_id(job_id, attempt, 'publication', digest),
                     'role': 'publication', 'sha256': digest, 'size_bytes': size,
                     'content_type': ROLES['publication'][1],
                     'rel_path': f'jobs/{job_id}/attempt-{attempt}/{ROLES["publication"][0]}'})
        return rows, publication.get('worker_checks')

    def reconcile(self):
        """Startup reconciliation of attempts left running by a different instance. Sends no signal."""
        with self._db() as conn:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM attempts WHERE state = 'running' AND (instance_id IS NULL OR instance_id <> ?) "
                'ORDER BY rowid', (self.instance_id,))]
        summary = {'adopted': 0, 'interrupted': 0, 'liveness': {name: 0 for name in LIVENESS}}
        for row in rows:
            claim = {'job_id': row['job_id'], 'attempt': row['attempt'], 'fence': row['fence']}
            adopted = self._adoptable(row)
            if adopted is not None:
                artifacts, checks = adopted
                self._finish(claim, 'succeeded', None, result=checks, artifacts=artifacts,
                             event_reason='reconciled_publication')
                summary['adopted'] += 1
                continue
            liveness = process_liveness(row['pid'], row['worker_birth'])
            with self._tx() as conn:
                conn.execute('UPDATE attempts SET liveness = ? WHERE job_id = ? AND attempt = ?',
                             (liveness, row['job_id'], row['attempt']))
            self._finish(claim, 'interrupted', 'supervisor_restarted')
            summary['interrupted'] += 1
            summary['liveness'][liveness] += 1
        return summary

    # ----------------------------------------------------------------- projection

    def project(self, job_id):
        """Closed public job projection (section 6). No path, selector or stderr."""
        with self._db() as conn:
            job = self._job_row(conn, job_id)
            source = self._source_row(conn, job['source_artifact_id'])
            attempts = conn.execute('SELECT * FROM attempts WHERE job_id = ? ORDER BY attempt', (job_id,)).fetchall()
            artifacts = conn.execute('SELECT * FROM artifacts WHERE job_id = ? ORDER BY attempt, role',
                                     (job_id,)).fetchall()
            reconciled = {r['attempt'] for r in conn.execute(
                "SELECT attempt FROM events WHERE job_id = ? AND to_state = 'succeeded' "
                "AND reason_code = 'reconciled_publication'", (job_id,))}
        attempt_rows = []
        duration = None
        for row in attempts:
            receipt = json.loads(row['cancel_receipt_json']) if row['cancel_receipt_json'] else None
            checks = json.loads(row['result_json']) if row['result_json'] else None
            if row['state'] == 'succeeded' and isinstance(checks, dict):
                proof = checks.get('video_proof') or {}
                start, end = proof.get('source_start_seconds'), proof.get('source_end_seconds')
                if isinstance(start, (int, float)) and isinstance(end, (int, float)):
                    duration = end - start
            attempt_rows.append({
                'attempt': row['attempt'], 'state': row['state'], 'worker_kind': row['worker_kind'],
                'reason_code': row['reason_code'], 'started_at': row['started_at'], 'ended_at': row['ended_at'],
                'liveness': row['liveness'], 'reconciled_publication': row['attempt'] in reconciled,
                'cancel': None if receipt is None else {key: receipt.get(key) for key in (
                    'reason', 'requested_at', 'ack_at', 'signal_at', 'observed_stop_at', 'signal_target',
                    'signals_sent', 'group_empty_observed')},
                'worker_checks': checks})
        latest = attempts[-1] if attempts else None
        birth_recorded = bool(latest is not None and latest['worker_birth'])
        unknowns = {
            'listening_acceptance': 'not_established',
            'master_adopted': False,
            'low_register_preservation': None,
            'low_register_preservation_reason': UNKNOWN_REASONS['low_register_preservation'],
            'musical_review': None,
            'musical_review_reason': UNKNOWN_REASONS['musical_review'],
            'source_duration_seconds': duration,
            'source_duration_seconds_reason': (
                'worker video packet presentation extent (source_end - source_start); not a container probe'
                if duration is not None else 'unknown until the worker reports it; admission does not probe'),
            'memory_bytes_peak': None,
            'memory_bytes_peak_reason': UNKNOWN_REASONS['memory_bytes_peak'],
            'cpu_seconds': None,
            'cpu_seconds_reason': UNKNOWN_REASONS['cpu_seconds'],
            'exactly_once': 'not_claimed',
            'slo': 'not_claimed',
            'worker_birth': 'recorded' if birth_recorded else None,
            'worker_birth_reason': ('ps lstart recorded for the latest attempt' if birth_recorded
                                    else 'ps evidence unavailable or worker not launched'),
        }
        return {
            'job_id': job['job_id'], 'tool': job['tool'], 'state': job['state'], 'reason_code': job['reason_code'],
            'source_artifact_id': job['source_artifact_id'], 'source_id': source['source_id'],
            'source_binding': source['source_binding'], 'parameters': json.loads(job['parameters_json']),
            'capability_revision': job['capability_revision'], 'idempotency_key': job['idempotency_key'],
            'cancel_requested': bool(job['cancel_requested']), 'attempts': attempt_rows,
            'artifacts': [{'artifact_id': a['artifact_id'], 'attempt': a['attempt'], 'role': a['role'],
                           'sha256': a['sha256'], 'size_bytes': a['size_bytes'], 'content_type': a['content_type'],
                           'downloadable': ROLES[a['role']][2]} for a in artifacts],
            'claim_class': CLAIM_CLASS, 'unknowns': unknowns,
        }

    def get_job(self, job_id):
        return 200, self.project(job_id)

    # ----------------------------------------------------------------- download

    def open_artifact(self, artifact_id):
        """Verify and open a published artifact for streaming (GET /artifacts/{id})."""
        if not isinstance(artifact_id, str) or not ARTIFACT_ID.fullmatch(artifact_id):
            raise WebJobsError('malformed_id', 400, 'artifact id must be art_ followed by 32 hex digits')
        with self._db() as conn:
            row = conn.execute('SELECT * FROM artifacts WHERE artifact_id = ?', (artifact_id,)).fetchone()
        if row is None:
            raise WebJobsError('unknown_artifact', 404, 'artifact id is not a published job artifact')
        if not ROLES[row['role']][2]:
            raise WebJobsError('artifact_private', 403, 'this artifact role is listed but not served')
        parts = row['rel_path'].split('/')
        if any(part in ('', '.', '..') for part in parts) or len(parts) != 4:
            raise WebJobsError('confinement_refused', 403, 'artifact location is not confined')
        cursor = self.state_root
        for part in parts[:-1]:
            cursor = cursor / part
            try:
                info = os.lstat(cursor)
            except FileNotFoundError:
                raise WebJobsError('artifact_missing', 410, 'published artifact is missing') from None
            except OSError:
                raise WebJobsError('confinement_refused', 403, 'artifact location cannot be verified') from None
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise WebJobsError('confinement_refused', 403, 'artifact location contains a non-directory component')
        if not _inside(cursor.resolve(), self.state_root):
            raise WebJobsError('confinement_refused', 403, 'artifact location escapes the state root')
        try:
            descriptor, before = _open_regular_nofollow(cursor / parts[-1])
        except FileNotFoundError:
            raise WebJobsError('artifact_missing', 410, 'published artifact is missing') from None
        except OSError as error:
            if error.errno == errno.ELOOP:
                raise WebJobsError('confinement_refused', 403, 'artifact leaf is a symbolic link') from None
            raise WebJobsError('confinement_refused', 403, 'artifact is not a regular file') from None
        try:
            digest, size = hash_descriptor(descriptor)
            after = os.fstat(descriptor)
        except BaseException:
            os.close(descriptor)
            raise
        if file_signature(before) != file_signature(after) or digest != row['sha256'] or size != row['size_bytes']:
            os.close(descriptor)
            raise WebJobsError('artifact_stale', 409, 'published artifact bytes changed')
        return ServedArtifact(artifact_id, descriptor, size, digest, row['content_type'], file_signature(after))

    # ----------------------------------------------------------------- status

    def counts(self):
        with self._db() as conn:
            jobs = {r['state']: r['n'] for r in conn.execute('SELECT state, count(*) AS n FROM jobs GROUP BY state')}
            artifacts = conn.execute('SELECT count(*) FROM artifacts').fetchone()[0]
        return {'jobs': {state: jobs.get(state, 0) for state in STATES}, 'artifacts': artifacts}


# --------------------------------------------------------------------------- CLI

def read_only_status(state_root):
    """Status without taking the lock or reconciling (safe while a server runs)."""
    path = Path(state_root).resolve() / DB_NAME
    if not path.is_file():
        raise WebJobsError('unknown_state_root', 404, 'no job database under this state root')
    conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=5)
    try:
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        if version != SCHEMA_VERSION:
            raise WebJobsError('schema_version_mismatch', 500, f'schema version {version} is not {SCHEMA_VERSION}')
        jobs = dict(conn.execute('SELECT state, count(*) FROM jobs GROUP BY state').fetchall())
        attempts = dict(conn.execute('SELECT state, count(*) FROM attempts GROUP BY state').fetchall())
        artifacts = conn.execute('SELECT count(*) FROM artifacts').fetchone()[0]
        sources = conn.execute('SELECT count(*) FROM sources').fetchone()[0]
    finally:
        conn.close()
    return {'schema_version': version, 'sources': sources, 'artifacts': artifacts,
            'jobs': {state: jobs.get(state, 0) for state in STATES},
            'attempts': {state: attempts.get(state, 0) for state in STATES},
            'claim_class': CLAIM_CLASS, 'daemon': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--state-root', default=str(DEFAULT_STATE_ROOT))
    parser.add_argument('--runs-root', default=str(ROOT), help='repository root holding artifacts/runs')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status', help='read-only counts (no lock, no reconciliation)')
    commands.add_parser('reconcile', help='take the lock, reconcile abandoned attempts, release')
    args = parser.parse_args(argv)
    try:
        if args.command == 'status':
            result = read_only_status(args.state_root)
        else:
            jobs = WebJobs(args.runs_root, args.state_root)
            try:
                result = {'reconciliation': jobs.reconciliation, **jobs.counts(), 'claim_class': CLAIM_CLASS}
            finally:
                jobs.close()
    except WebJobsError as error:
        print(json.dumps(error.body(), sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
