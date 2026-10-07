#!/usr/bin/env python3
"""Durable local job store and bounded supervisor for a closed allowlist of job types (stdlib only).

Contracts: ``docs/spec/sprints/WEB_JOBS_S2.md`` (store, supervisor, idempotency,
cancel, interrupted/retry, atomic publication) and
``docs/spec/sprints/ROUTES_PROCESSING_S3.md`` (allowlist, capture reviews,
schema version 2, one active media job per host). One operator, one host, one
SQLite file (WAL, ``PRAGMA user_version = 2``) and one in-process supervisor
thread per state root.

``JOB_TYPES`` is a closed allowlist: ``share_export`` (S2, root-admitted),
``denoise``, ``capture_profile`` and ``apply_capture_profile``. A type runs only
when ``program/capabilities.json`` lists its ``adapters.web_job`` as
``admitted``; every other allowlisted type is refused
``tool_pending_admission``. Workers run with ``tool_api``'s validated argument
checks and fixed argv, timeout-bounded, in a new session so that cancellation
signals only the owned process group (R-N11).

Sources and outputs are addressed only by opaque IDs: sources by
``artifact_ids`` ``art_`` IDs confined to ``<runs_root>/artifacts/runs``;
outputs by ``art_`` IDs and run IDs. No public record contains a host path, a
selector or worker stderr.

Capture reviews are operator assertions bound to a source sha256 and to a
baseline run's manifest and PCM sha256; nothing here proposes, prefills or
auto-confirms an interval, and an interval overlapping the first five seconds
of the decoded audio is never promoted to ``reviewed_candidate``.

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
from types import MappingProxyType

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import artifact_ids  # noqa: E402  (import only, never edited)
import tool_api  # noqa: E402  (import only, never edited)

ROOT = tool_api.ROOT
SCHEMA_VERSION = 2
PRIOR_SCHEMA_VERSION = 1  # migrated forward once (schema_migrated_1_2)
TOOL = 'share_export'  # the S2 job type; JOB_TYPES below is the closed allowlist
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

# --------------------------------------------------------------------------- S3 allowlist


@dataclass(frozen=True)
class JobType:
    """One allowlisted web job type. Knob bounds always come from the live tool descriptor."""

    tool: str
    resource_class: str            # 'media' holds the host media lock; 'analysis' is serialized only
    parameter_keys: tuple          # web ``parameters`` keys (closed)
    bound_field: object            # body field naming the bound input, or None
    worker_scripts: tuple          # hashed into capability_revision(tool)
    web_only_constraints: tuple    # stricter-than-tool web rules (listed in the catalogue, counted in M2)


CAPTURE_CONTROL_KEYS = ('reduction_db', 'noise_floor_db', 'adaptivity', 'gain_smooth',
                        'integrated_lufs', 'true_peak_dbtp')
CAPTURE_OPTIONAL_KEYS = ('peaking_eq', 'compressor')
CAPTURE_PRESETS = ('fuller', 'custom')

JOB_TYPES = MappingProxyType({
    'share_export': JobType('share_export', 'media', PARAMETER_KEYS, None, ('share_export.py',),
                            ('parameters.height must be even (also enforced by tool_api)',)),
    'denoise': JobType('denoise', 'media', ('profile', 'timeout_seconds'), None, ('media.py',),
                       ('parameters.profile is required (no silent tool default)',
                        'captured* profiles are refused profile_source_mismatch unless the admitted source sha256 '
                        'equals the profile noise_capture_source_sha256',
                        'input is always the re-hashed admitted source; no browser path')),
    'capture_profile': JobType('capture_profile', 'analysis',
                               ('preset',) + CAPTURE_CONTROL_KEYS + CAPTURE_OPTIONAL_KEYS + ('timeout_seconds',),
                               'capture_review_id', ('capture_profile.py', 'media.py'),
                               ('parameters.preset is required: fuller | custom',
                                "preset 'fuller' forbids any explicit control (expanded verbatim from profiles/fuller.json)",
                                "preset 'custom' requires every required control explicitly",
                                'capture_review_id is required; a review with authorization_scope '
                                'experimental_capture_render and status other than rejected_contaminated',
                                'capture interval, run_dir and review are derived from the saved review, never the body')),
    'apply_capture_profile': JobType('apply_capture_profile', 'media', ('timeout_seconds',),
                                     'capture_profile_job_id',
                                     ('apply_capture_profile.py', 'capture_application_adapter.py', 'media.py'),
                                     ('capture_profile_job_id is required: a succeeded capture_profile job for the '
                                      'same source whose publication is authored_unrendered with scope '
                                      'experimental_capture_render',
                                      'authoring_dir and receipt_sha256 are read from that job publication')),
})
JOB_TYPE_NAMES = tuple(JOB_TYPES)
PROCESSING_TOOLS = tuple(name for name in JOB_TYPES if name != TOOL)
WORKER_KINDS = ('tool_api_share_export', 'test_stub', 'tool_api_denoise', 'tool_api_capture_profile',
                'tool_api_apply_capture_profile')
CAPABILITIES_PATH = ROOT / 'program' / 'capabilities.json'
MAX_CAPABILITIES_BYTES = 1024 * 1024
FULLER_PROFILE = ROOT / 'profiles' / 'fuller.json'
PROFILES_DIR = ROOT / 'profiles'
HOST_MEDIA_LOCK = '.host-media.lock'
WAITING_HOST_SLOT = 'waiting_host_media_slot'

# Capture review enumerations: exactly scripts/capture_profile.py validate_review (parity-tested).
REVIEW_STATUSES = ('reviewed_candidate', 'reviewed_possible_contamination', 'rejected_contaminated')
AUTHORIZATION_SCOPES = ('profile_authoring', 'experimental_capture_render')
CONTENT_STATUSES = ('unknown', 'suspected', 'reviewed_no_obvious_content', 'reviewed_present')
AMBIENT_STATUSES = ('not_reported', 'suspected', 'reviewed_absent', 'reviewed_present')
SETUP_INTERVAL_SECONDS = 5.0
SETUP_ALLOWED_STATUSES = ('reviewed_possible_contamination', 'rejected_contaminated')
WEB_REVIEWER = 'operator via loopback browser (unauthenticated assertion)'
REVIEW_ID = re.compile(r'rev_[0-9a-f]{32}')
REVIEW_DIR = 'web-capture-reviews'
MAX_REVIEW_BYTES = 16 * 1024
MAX_NOTE_CHARS = 2000
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_PCM_BYTES = 1024 ** 3
MAX_RUN_SCAN = 4096
MIN_CAPTURE_SECONDS, MAX_CAPTURE_SECONDS = 0.1, 10.0
RUN_MEDIA_ROLES = MappingProxyType({'source': 'source.wav', 'denoised': 'denoised.wav', 'cleaned': 'cleaned.wav',
                                    'processed': 'processed.wav', 'residue': 'residue.wav'})
RUN_OUTPUT_ROLES = ('source', 'denoised', 'baseline', 'cleaned', 'residue', 'processed')
FRAME_SECONDS = 0.1
TRANSIENT_DB_ABOVE_MEDIAN = 6.0
CLIP_THRESHOLD = 0.999
DBFS_FLOOR = -200.0

# Contract section 9: keys every processing projection, publication, review and
# measurement carries with value null (master_adopted: false) and a reason.
PROCESSING_UNKNOWN_REASONS = {
    'listening_acceptance': 'operator listening not performed for this version',
    'low_register_preservation': '~32 Hz content not measured by a job service',
    'capture_noise_only': 'the reviewed interval is not verified noise-only',
    'music_or_click_presence': 'operator assertion only unless reviewed_present',
    'fuller_listening_transfer': ('FULLER acceptance covers one source/interval only '
                                  '(a522115f4e72, native samples [180810, 218295)); not transferred'),
    'musical_review': 'no note-correctness, missed-note or phrase verdict',
    'level_matched': 'span audition is not level-matched',
    'memory_bytes_peak': 'not measured; no OS memory quota is applied',
    'cpu_seconds': 'not measured; no OS CPU quota is applied',
}


def processing_unknowns():
    """Fresh section-9 block: every key null with its reason, master_adopted false."""
    block = {'master_adopted': False,
             'master_adopted_reason': 'the web job service never adopts a master or latest pointer'}
    for key, reason in PROCESSING_UNKNOWN_REASONS.items():
        block[key] = None
        block[key + '_reason'] = reason
    return block


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


def _split_sql(script):
    """Split a DDL script on statement ends, keeping CREATE TRIGGER ... END; bodies whole."""
    statements, current = [], []
    for line in script.splitlines():
        if not line.strip():
            continue
        current.append(line)
        text = '\n'.join(current).strip()
        if text.endswith(';') and (not text.upper().startswith('CREATE TRIGGER') or text.upper().endswith('END;')):
            statements.append(text)
            current = []
    if current and '\n'.join(current).strip():
        statements.append('\n'.join(current).strip())
    return statements


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


def _in_list(values):
    return '(' + ', '.join(repr(value) for value in values) + ')'


# Version 2 (ROUTES_PROCESSING_S3 section 6.4): applied after SCHEMA_SQL on a fresh
# store and, once, on a version-1 store inside one transaction under the state lock.
SCHEMA_V2_SQL = f"""
ALTER TABLE jobs ADD COLUMN bound_input_json TEXT;
CREATE TABLE capture_reviews(
  review_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE, fingerprint TEXT NOT NULL,
  source_artifact_id TEXT NOT NULL REFERENCES sources(source_artifact_id), source_sha256 TEXT NOT NULL,
  run_id TEXT NOT NULL, manifest_sha256 TEXT NOT NULL, pcm_sha256 TEXT NOT NULL, review_sha256 TEXT NOT NULL,
  start_seconds REAL NOT NULL, end_seconds REAL NOT NULL, start_sample INTEGER NOT NULL,
  end_sample INTEGER NOT NULL, sample_rate INTEGER NOT NULL,
  review_status TEXT NOT NULL CHECK (review_status IN {_in_list(REVIEW_STATUSES)}),
  authorization_scope TEXT NOT NULL CHECK (authorization_scope IN {_in_list(AUTHORIZATION_SCOPES)}),
  music_status TEXT NOT NULL CHECK (music_status IN {_in_list(CONTENT_STATUSES)}),
  click_status TEXT NOT NULL CHECK (click_status IN {_in_list(CONTENT_STATUSES)}),
  ambient_music_status TEXT NOT NULL CHECK (ambient_music_status IN {_in_list(AMBIENT_STATUSES)}),
  overlaps_setup_interval INTEGER NOT NULL CHECK (overlaps_setup_interval IN (0, 1)),
  setup_interval_acknowledged INTEGER NOT NULL CHECK (setup_interval_acknowledged IN (0, 1)),
  note TEXT NOT NULL, rel_path TEXT NOT NULL, created_at TEXT NOT NULL,
  CHECK (NOT (overlaps_setup_interval = 1 AND review_status = 'reviewed_candidate')),
  CHECK (overlaps_setup_interval = 0 OR setup_interval_acknowledged = 1));
CREATE TRIGGER capture_reviews_no_update BEFORE UPDATE ON capture_reviews
BEGIN SELECT RAISE(ABORT, 'append_only_review'); END;
CREATE TRIGGER capture_reviews_no_delete BEFORE DELETE ON capture_reviews
BEGIN SELECT RAISE(ABORT, 'append_only_review'); END;
CREATE TRIGGER jobs_tool_allowlist BEFORE INSERT ON jobs WHEN NEW.tool NOT IN {_in_list(JOB_TYPE_NAMES)}
BEGIN SELECT RAISE(ABORT, 'tool_not_allowlisted'); END;
CREATE TRIGGER jobs_tool_immutable BEFORE UPDATE OF tool ON jobs
BEGIN SELECT RAISE(ABORT, 'immutable_tool'); END;
"""
V1_TABLES = frozenset({'meta', 'sources', 'jobs', 'attempts', 'artifacts', 'events'})


def load_web_job_states(path=None):
    """Allowlisted tool -> capabilities.json adapters.web_job state (missing -> 'unknown')."""
    path = Path(path) if path is not None else CAPABILITIES_PATH
    try:
        digest, size = hash_regular_file(path, MAX_CAPABILITIES_BYTES)
        data = strict_json(path.read_bytes(), 'capabilities')
    except (OSError, ValueError):
        return {name: 'unknown' for name in JOB_TYPES}
    states = {name: 'unknown' for name in JOB_TYPES}
    for entry in data.get('capabilities', []) if isinstance(data, dict) else []:
        if isinstance(entry, dict) and entry.get('tool') in JOB_TYPES:
            adapters = entry.get('adapters') if isinstance(entry.get('adapters'), dict) else {}
            state = adapters.get('web_job')
            states[entry['tool']] = state if state in ('planned', 'unsupported', 'admitted') else 'unknown'
    return states


def load_fuller_controls(path=None):
    """The FULLER capture_profile controls, copied verbatim from profiles/fuller.json."""
    path = Path(path) if path is not None else FULLER_PROFILE
    profile = strict_json(path.read_bytes(), 'fuller profile')
    controls = {key: profile[key] for key in CAPTURE_CONTROL_KEYS}
    for key in CAPTURE_OPTIONAL_KEYS:
        if key in profile:
            controls[key] = profile[key]
    if profile.get('noise_capture_required') is not True or 'noise_capture_seconds' in profile:
        raise ValueError('fuller profile must require, and never bake in, a per-take capture interval')
    return controls


def profile_source_binding(name):
    """noise_capture_source_sha256 of a fixed denoise profile, or None when it binds no source."""
    if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9-]{1,64}', name):
        return None
    try:
        profile = strict_json((PROFILES_DIR / f'{name}.json').read_bytes(), 'profile')
    except (OSError, ValueError):
        return None
    value = profile.get('noise_capture_source_sha256') if isinstance(profile, dict) else None
    return value if isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) else None


# --------------------------------------------------------------------------- native PCM (stdlib)

PCM_FORMATS = {(1, 16): ('pcm_s16le', 'h'), (1, 24): ('pcm_s24le', None), (1, 32): ('pcm_s32le', 'i'),
               (3, 32): ('pcm_f32le', 'f')}


def wav_header(descriptor, size):
    """Bounded RIFF/WAVE header walk over an open descriptor: format, data offset and frame count."""
    import struct
    head = os.pread(descriptor, 12, 0)
    if len(head) != 12 or head[:4] != b'RIFF' or head[8:] != b'WAVE':
        raise WebJobsError('pcm_format_unsupported', 422, 'baseline source.wav is not RIFF/WAVE')
    end = min(struct.unpack('<I', head[4:8])[0] + 8, size)
    offset, fmt, data = 12, None, None
    for _ in range(4096):
        if offset + 8 > end:
            break
        kind, length = struct.unpack('<4sI', os.pread(descriptor, 8, offset))
        body = offset + 8
        if kind == b'fmt ':
            if not 16 <= length <= 256:
                raise WebJobsError('pcm_format_unsupported', 422, 'unsupported WAV fmt chunk')
            raw = os.pread(descriptor, length, body)
            code, channels, rate, byte_rate, alignment, bits = struct.unpack('<HHIIHH', raw[:16])
            if code == 0xFFFE and len(raw) >= 40:
                code = struct.unpack('<I', raw[24:28])[0]
            fmt = (code, channels, rate, byte_rate, alignment, bits)
        elif kind == b'data':
            data = (body, min(length, end - body))
            break
        offset = body + length + (length % 2)
    if fmt is None or data is None:
        raise WebJobsError('pcm_format_unsupported', 422, 'WAV lacks fmt or data chunk')
    code, channels, rate, _byte_rate, alignment, bits = fmt
    known = PCM_FORMATS.get((code, bits))
    if known is None or not 1 <= channels <= 8 or not 8000 <= rate <= 192000 or alignment != channels * bits // 8:
        raise WebJobsError('pcm_format_unsupported', 422, 'WAV sample format is not s16/s24/s32/f32 PCM')
    return {'codec': known[0], 'typecode': known[1], 'channels': channels, 'sample_rate': rate,
            'bytes_per_sample': bits // 8, 'block_alignment': alignment, 'data_offset': data[0],
            'sample_count': data[1] // alignment}


def decode_frames(raw, header):
    """Interleaved PCM bytes -> per-channel float lists in [-1, 1] (s16/s24/s32/f32 little-endian)."""
    import array
    channels = header['channels']
    if header['typecode'] is None:  # 24-bit
        values = []
        for index in range(0, len(raw) - 2, 3):
            integer = raw[index] | (raw[index + 1] << 8) | (raw[index + 2] << 16)
            values.append((integer - (1 << 24) if integer & 0x800000 else integer) / 8388608.0)
    else:
        values = array.array(header['typecode'])
        values.frombytes(raw[:len(raw) - len(raw) % values.itemsize])
        if sys.byteorder != 'little':
            values.byteswap()
        scale = {'h': 32768.0, 'i': 2147483648.0, 'f': 1.0}[header['typecode']]
        values = [value / scale for value in values] if scale != 1.0 else list(values)
    return [values[channel::channels] for channel in range(channels)]


def dbfs(value):
    return round(20 * math.log10(value), 6) if value > 0 else DBFS_FLOOR


def interval_statistics(channels, rate):
    """Section 7.4 measurements of the mixture per channel; nothing here selects or confirms an interval."""
    frame = max(1, round(rate * FRAME_SECONDS))
    result = []
    for samples in channels:
        count = len(samples)
        if not count:
            raise WebJobsError('interval_out_of_range', 422, 'interval holds no samples')
        peak = max(abs(value) for value in samples)
        rms = math.sqrt(math.fsum(value * value for value in samples) / count)
        frames = [samples[start:start + frame] for start in range(0, count - frame + 1, frame)]
        levels = [dbfs(math.sqrt(math.fsum(v * v for v in chunk) / len(chunk))) for chunk in frames]
        ordered = sorted(levels)
        median = None
        if ordered:
            middle = len(ordered) // 2
            median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
        result.append({
            'sample_peak_dbfs': dbfs(peak), 'sample_peak_is_true_peak': False, 'rms_dbfs': dbfs(rms),
            'frame_rms_dbfs': {'min': ordered[0] if ordered else None, 'median': median,
                               'max': ordered[-1] if ordered else None,
                               'spread_db': (ordered[-1] - ordered[0]) if ordered else None},
            'frame_count': len(levels), 'frame_samples': frame,
            'unframed_tail_samples': count - len(levels) * frame,
            'transient_frames': sum(level > median + TRANSIENT_DB_ABOVE_MEDIAN for level in levels) if ordered else 0,
            'transient_frames_label': ('possible attack/windup indicator (inference): frames more than '
                                       f'{TRANSIENT_DB_ABOVE_MEDIAN:g} dB above the interval median'),
            'clipped_samples': sum(abs(value) >= CLIP_THRESHOLD for value in samples),
            'clip_threshold_fs': CLIP_THRESHOLD, 'sample_count': count})
    return result


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
                 queue_limit=4, cancel_grace_s=5.0, command_builder=None, fault=None, admitted_tools=None,
                 host_lock_path=None):
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
        if admitted_tools is not None:
            # Test-only seam: the product never self-admits a web adapter (root decision).
            if command_builder is None:
                raise ValueError('admitted_tools is a test-only seam and requires a stub command_builder')
            if not isinstance(admitted_tools, (set, frozenset, tuple, list)) \
                    or not set(admitted_tools) <= set(JOB_TYPES):
                raise ValueError('admitted_tools must name allowlisted job types only')
        self.max_source_bytes = max_source_bytes
        self.queue_limit = queue_limit
        self.cancel_grace_s = float(cancel_grace_s)
        self.command_builder = command_builder
        self.worker_kind = 'tool_api_share_export' if command_builder is None else 'test_stub'
        self._seam_admitted = frozenset(admitted_tools or ())
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
        self.host_lock_path = Path(host_lock_path) if host_lock_path is not None \
            else self.state_root.parent / HOST_MEDIA_LOCK
        self._host_fd = None
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
            self.descriptors = {name: tool_api.descriptor(name) for name in JOB_TYPES}
            self.capability_revisions = {name: self._tool_revision(name) for name in JOB_TYPES}
            self.capability_states = load_web_job_states()
            self.fuller_controls = load_fuller_controls()
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

    def _tool_revision(self, tool):
        """capability_revision(tool): sha256 of the descriptor plus its worker script(s)."""
        if tool == TOOL:
            return self.capability_revision  # unchanged S2 derivation (v1 fingerprints stay replayable)
        digest = hashlib.sha256(sha256_hex(canonical(tool_api.descriptor(tool)).encode('ascii')).encode('ascii'))
        for script in JOB_TYPES[tool].worker_scripts:
            digest.update(sha256_hex((ROOT / 'scripts' / script).read_bytes()).encode('ascii'))
        return digest.hexdigest()

    def admission_state(self, tool):
        """('admitted' | 'pending_root_admission', raw capabilities.json web_job state)."""
        raw = self.capability_states.get(tool)
        if raw == 'admitted' or tool in self._seam_admitted:
            return 'admitted', raw
        return 'pending_root_admission', raw

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
        self.migration = None
        with self._db() as conn:
            version = conn.execute('PRAGMA user_version').fetchone()[0]
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                      if not row[0].startswith('sqlite_')}
            if version == 0 and not tables:
                if conn.execute('PRAGMA journal_mode=WAL').fetchone()[0].lower() != 'wal':
                    raise WebJobsError('state_root_unsafe', 500, 'WAL journal mode unavailable')
                self._script(conn, SCHEMA_SQL + SCHEMA_V2_SQL + f'PRAGMA user_version = {SCHEMA_VERSION};\n')
                with contextlib.suppress(OSError):
                    os.chmod(self.db_path, 0o600)
                conn.execute('INSERT INTO meta(key, value) VALUES (?, ?), (?, ?)',
                             ('schema_version', str(SCHEMA_VERSION), 'created_at', utc_now()))
            elif version == PRIOR_SCHEMA_VERSION and V1_TABLES <= tables and 'capture_reviews' not in tables:
                if conn.execute('PRAGMA journal_mode=WAL').fetchone()[0].lower() != 'wal':
                    raise WebJobsError('state_root_unsafe', 500, 'WAL journal mode unavailable')
                now = utc_now()
                self._script(conn, SCHEMA_V2_SQL + f'PRAGMA user_version = {SCHEMA_VERSION};\n'
                             + "UPDATE meta SET value = '2' WHERE key = 'schema_version';\n"
                             + f"INSERT INTO meta(key, value) VALUES ('schema_migrated_1_2', '{now}');\n"
                             + "INSERT INTO events(job_id, attempt, from_state, to_state, reason_code, at) "
                             + f"VALUES ('schema', NULL, '1', '2', 'schema_migrated_1_2', '{now}');\n")
                self.migration = {'event': 'schema_migrated_1_2', 'from': PRIOR_SCHEMA_VERSION,
                                  'to': SCHEMA_VERSION, 'at': now}
            elif version != SCHEMA_VERSION or 'capture_reviews' not in tables:
                raise WebJobsError('schema_version_mismatch', 500,
                                   f'job database schema version {version} is not {SCHEMA_VERSION}; not migrated')
            elif conn.execute('PRAGMA journal_mode=WAL').fetchone()[0].lower() != 'wal':
                raise WebJobsError('state_root_unsafe', 500, 'WAL journal mode unavailable')
            conn.execute('INSERT INTO meta(key, value) VALUES (?, ?) '
                         'ON CONFLICT(key) DO UPDATE SET value = excluded.value',
                         ('instance_id', self.instance_id))

    @staticmethod
    def _script(conn, body):
        """One IMMEDIATE transaction for a DDL script; rolled back whole on any failure."""
        conn.execute('BEGIN IMMEDIATE')
        try:
            for statement in _split_sql(body):
                conn.execute(statement)
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                conn.execute('ROLLBACK')
            raise
        conn.execute('COMMIT')

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
        self._release_host_slot()
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
        """POST /jobs: (202 new | 200 replayed, projection). Closed allowlist; typed refusals."""
        self._check_open()
        closed_object(body, {'tool': str, 'source_artifact_id': str, 'idempotency_key': str},
                      {'parameters': dict, 'capture_review_id': str, 'capture_profile_job_id': str})
        tool = body['tool']
        if tool not in JOB_TYPES:
            raise WebJobsError('tool_not_admitted', 400, 'tool is not in the closed web job allowlist')
        spec = JOB_TYPES[tool]
        extra = {'capture_review_id', 'capture_profile_job_id'} & set(body)
        if extra - ({spec.bound_field} if spec.bound_field else set()):
            raise WebJobsError('unknown_field', 400, f'request contains {len(extra)} unsupported field(s) for {tool}')
        admission, raw = self.admission_state(tool)
        if admission != 'admitted':
            raise WebJobsError('tool_pending_admission', 409, f'{tool} is allowlisted but its web_job adapter '
                               'awaits root admission', capability_state=raw, admission_state=admission)
        if not IDEMPOTENCY_KEY.fullmatch(body['idempotency_key']):
            raise WebJobsError('invalid_idempotency_key', 400, 'idempotency_key must match [A-Za-z0-9._-]{8,128}')
        if not ARTIFACT_ID.fullmatch(body['source_artifact_id']):
            raise WebJobsError('malformed_id', 400, 'source_artifact_id must be art_ followed by 32 hex digits')
        if tool == TOOL:
            return self._submit_share(body)
        return self._submit_processing(tool, body)

    def _submit_share(self, body):
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
        self._require_current(source)
        return self._insert_job(TOOL, key, fingerprint, source, parameters, None)

    def _require_current(self, source):
        state, path = self._resolve_source(source)
        if state == 'stale':
            raise WebJobsError('source_stale', 409, 'admitted source bytes changed; admit the new version')
        if state == 'missing':
            raise WebJobsError('source_missing', 410, 'admitted source is no longer present')
        return path

    def _insert_job(self, tool, key, fingerprint, source, parameters, bound):
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
                    'capability_revision, state, reason_code, cancel_requested, created_at, updated_at, '
                    "bound_input_json) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', NULL, 0, ?, ?, ?)",
                    (job_id, key, fingerprint, tool, source['source_artifact_id'], canonical(parameters),
                     self.capability_revisions[tool], now, now, canonical(bound) if bound is not None else None))
                conn.execute("INSERT INTO attempts(job_id, attempt, state) VALUES (?, 1, 'queued')", (job_id,))
                self._event(conn, job_id, 1, None, 'queued', 'submitted')
        if existing is not None:
            return self._replay(existing, fingerprint)
        self._wake.set()
        return 202, dict(self.project(job_id), replayed=False)

    # ----------------------------------------------------------------- S3 processing submission

    @staticmethod
    def _invalid(error):
        text = str(error)[:200]
        match = re.match(r'parameters\.([A-Za-z_]+)', text)
        extra = {'field': match.group(1)} if match else {}
        return WebJobsError('invalid_parameters', 400, text, **extra)

    def _validate_subset(self, tool, values, keys, label='parameters'):
        properties = self.descriptors[tool]['inputSchema']['properties']
        schema = {'type': 'object', 'properties': {key: properties[key] for key in keys},
                  'required': [], 'additionalProperties': False}
        try:
            tool_api.validate(values, schema, label)
        except tool_api.ValidationError as error:
            raise self._invalid(error) from None

    def normalize_processing_parameters(self, tool, parameters, source_sha256):
        """Closed per-type parameters; bounds from the live descriptor; web-only rules typed."""
        if not isinstance(parameters, dict):
            raise WebJobsError('invalid_parameters', 400, 'parameters must be an object')
        spec = JOB_TYPES[tool]
        unknown = sorted(set(parameters) - set(spec.parameter_keys))
        if unknown:
            raise WebJobsError('invalid_parameters', 400, f'parameters contain {len(unknown)} unsupported knob(s)')
        timeout_default = self.descriptors[tool]['inputSchema']['properties']['timeout_seconds']['default']
        if tool == 'denoise':
            if 'profile' not in parameters:
                raise WebJobsError('invalid_parameters', 400, 'parameters.profile is required (web-only rule)',
                                   field='profile', web_only=True)
            filled = {'profile': parameters['profile'],
                      'timeout_seconds': parameters.get('timeout_seconds', timeout_default)}
            self._validate_subset(tool, filled, ('profile', 'timeout_seconds'))
            bound = profile_source_binding(filled['profile'])
            if bound is not None and bound != source_sha256:
                raise WebJobsError('profile_source_mismatch', 409, f'profile {filled["profile"]} is bound to another '
                                   'source recording', field='profile', web_only=True)
            return filled
        if tool == 'apply_capture_profile':
            filled = {'timeout_seconds': parameters.get('timeout_seconds', timeout_default)}
            self._validate_subset(tool, filled, ('timeout_seconds',))
            return filled
        preset = parameters.get('preset')
        if preset not in CAPTURE_PRESETS:
            raise WebJobsError('invalid_parameters', 400, 'parameters.preset must be fuller or custom (web-only rule)',
                               field='preset', web_only=True)
        controls = {key: parameters[key] for key in CAPTURE_CONTROL_KEYS + CAPTURE_OPTIONAL_KEYS if key in parameters}
        if preset == 'fuller':
            if controls:
                raise WebJobsError('preset_controls_forbidden', 400, 'preset fuller is expanded verbatim from '
                                   'profiles/fuller.json; explicit controls are refused', web_only=True)
            controls = json.loads(canonical(self.fuller_controls))
        else:
            missing = [key for key in CAPTURE_CONTROL_KEYS if key not in controls]
            if missing:
                raise WebJobsError('invalid_parameters', 400, f'parameters.{missing[0]} is required for preset custom',
                                   field=missing[0])
        filled = {**controls, 'timeout_seconds': parameters.get('timeout_seconds', timeout_default)}
        self._validate_subset(tool, filled, tuple(filled))
        return {'preset': preset, **filled}

    def _review_row(self, conn, review_id):
        if not isinstance(review_id, str) or not REVIEW_ID.fullmatch(review_id):
            raise WebJobsError('malformed_id', 400, 'capture_review_id must be rev_ followed by 32 hex digits')
        row = conn.execute('SELECT * FROM capture_reviews WHERE review_id = ?', (review_id,)).fetchone()
        if row is None:
            raise WebJobsError('unknown_capture_review', 404, 'capture review id is not recorded')
        return dict(row)

    def _bound_capture_review(self, conn, source, body):
        review_id = body.get('capture_review_id')
        if review_id is None:
            raise WebJobsError('capture_interval_required', 409, 'a saved, reviewed capture interval is required '
                               'before capture_profile (FULLER never runs without one)')
        review = self._review_row(conn, review_id)
        if review['source_artifact_id'] != source['source_artifact_id'] or review['source_sha256'] != source['sha256']:
            raise WebJobsError('review_source_mismatch', 409, 'capture review is bound to another source')
        if review['review_status'] == 'rejected_contaminated':
            raise WebJobsError('capture_review_rejected', 409, 'capture review is rejected_contaminated')
        if review['authorization_scope'] != 'experimental_capture_render':
            raise WebJobsError('capture_interval_required', 409, 'capture review scope is profile_authoring; a '
                               'review authorizing experimental_capture_render is required',
                               detail_code='review_scope_authoring_only')
        return review, {'capture_review_id': review['review_id'], 'review_sha256': review['review_sha256'],
                        'run_id': review['run_id']}

    def _bound_authoring(self, conn, source, body):
        parent_id = body.get('capture_profile_job_id')
        if parent_id is None:
            raise WebJobsError('capture_interval_required', 409, 'apply needs a succeeded capture_profile job authored '
                               'from a reviewed capture interval')
        parent = self._job_row(conn, parent_id)
        if parent['tool'] != 'capture_profile' or parent['source_artifact_id'] != source['source_artifact_id']:
            raise WebJobsError('parent_job_mismatch', 409, 'capture_profile_job_id names another tool or source')
        if parent['state'] != 'succeeded':
            raise WebJobsError('authoring_not_renderable', 409, 'parent capture_profile job has not succeeded',
                               state=parent['state'])
        attempt = conn.execute("SELECT attempt FROM attempts WHERE job_id = ? AND state = 'succeeded' "
                               'ORDER BY attempt DESC LIMIT 1', (parent_id,)).fetchone()
        publication = self._read_publication(conn, parent_id, attempt['attempt']) if attempt else None
        if (publication is None or publication.get('worker_status') != 'authored_unrendered'
                or publication.get('authorization_scope') != 'experimental_capture_render'
                or not isinstance(publication.get('authoring_id'), str)):
            raise WebJobsError('authoring_not_renderable', 409, 'parent authoring is not an authored_unrendered '
                               'profile with experimental_capture_render scope')
        receipt = next((o for o in publication.get('outputs', []) if o.get('role') == 'capture_receipt'), None)
        if receipt is None:
            raise WebJobsError('authoring_not_renderable', 409, 'parent publication lacks the authoring receipt')
        return {'capture_profile_job_id': parent_id, 'receipt_sha256': receipt['sha256'],
                'run_id': publication['run_id'], 'authoring_id': publication['authoring_id']}

    def processing_fingerprint(self, tool, source, parameters, bound):
        return sha256_hex(canonical({
            'tool': tool, 'source_artifact_id': source['source_artifact_id'], 'source_sha256': source['sha256'],
            'parameters': parameters, 'bound_input': bound,
            'capability_revision': self.capability_revisions[tool]}).encode('ascii'))

    def _submit_processing(self, tool, body):
        key = body['idempotency_key']
        with self._db() as conn:
            source = self._source_row(conn, body['source_artifact_id'])
            if source is None:
                raise WebJobsError('unknown_source', 404, 'source artifact id is not admitted')
            source = dict(source)
            parameters = self.normalize_processing_parameters(tool, body.get('parameters', {}), source['sha256'])
            bound = None
            if tool == 'capture_profile':
                _review, bound = self._bound_capture_review(conn, source, body)
            elif tool == 'apply_capture_profile':
                bound = self._bound_authoring(conn, source, body)
            fingerprint = self.processing_fingerprint(tool, source, parameters, bound)
            existing = conn.execute('SELECT job_id, fingerprint FROM jobs WHERE idempotency_key = ?',
                                    (key,)).fetchone()
        if existing is not None:
            return self._replay(existing, fingerprint)
        source_path = self._require_current(source)
        args = self.derive_args(tool, source, source_path, parameters, bound, recheck=True)
        try:
            tool_api.validate(args, self.descriptors[tool]['inputSchema'])
            tool_api.validate_tool_arguments(tool, args)
        except tool_api.ValidationError as error:
            raise self._invalid(error) from None
        return self._insert_job(tool, key, fingerprint, source, parameters, bound)

    def derive_args(self, tool, source, source_path, parameters, bound, *, recheck):
        """Server-derived tool arguments; paths are private and never projected."""
        timeout = parameters['timeout_seconds']
        if tool == 'denoise':
            return {'input': str(source_path), 'profile': parameters['profile'], 'timeout_seconds': timeout}
        if tool == 'capture_profile':
            with self._db() as conn:
                review = self._review_row(conn, bound['capture_review_id'])
            run_dir = self.runs_dir / review['run_id']
            if recheck:
                self.check_review_current(review, source_path)
            args = {'input': str(source_path), 'run_dir': str(run_dir),
                    'review': str(run_dir / review['rel_path'].split('/', 1)[1]),
                    'capture_start_seconds': review['start_seconds'], 'capture_end_seconds': review['end_seconds']}
            args.update({key: value for key, value in parameters.items() if key != 'preset'})
            return args
        authoring = self.runs_dir / bound['run_id'] / 'capture-profiles' / bound['authoring_id']
        if recheck:
            try:
                digest, _ = hash_regular_file(authoring / 'receipt.json', 64 * 1024)
            except (OSError, ValueError):
                digest = None
            if digest != bound['receipt_sha256'] or not self._confined_dir(authoring):
                raise WebJobsError('authoring_stale', 409, 'authored capture profile receipt changed or is missing')
        return {'input': str(source_path), 'authoring_dir': str(authoring),
                'receipt_sha256': bound['receipt_sha256'], 'timeout_seconds': timeout}

    def _confined_dir(self, directory):
        """True when every component below runs_dir is a real (non-symlink) directory."""
        try:
            relative = Path(directory).relative_to(self.runs_dir)
        except ValueError:
            return False
        cursor = self.runs_dir
        for part in relative.parts:
            cursor = cursor / part
            try:
                info = os.lstat(cursor)
            except OSError:
                return False
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                return False
        return True

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
                self._release_host_slot()
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
            finally:
                if not self.crashed:
                    self._release_host_slot()

    # ----------------------------------------------------------------- host media slot

    def _try_host_slot(self):
        """Non-blocking host-wide advisory flock for one media-class attempt."""
        if self._host_fd is not None:
            return True
        flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0)
        try:
            descriptor = os.open(self.host_lock_path, flags, 0o600)
        except OSError:
            return False
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(descriptor)
            return False
        self._host_fd = descriptor
        return True

    def _release_host_slot(self):
        descriptor, self._host_fd = self._host_fd, None
        if descriptor is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            with contextlib.suppress(OSError):
                os.close(descriptor)

    def _claim(self):
        if self._stopping.is_set():
            return None
        with self._db() as conn:
            row = conn.execute(
                "SELECT a.job_id, a.attempt, j.tool FROM attempts a JOIN jobs j ON j.job_id = a.job_id "
                "WHERE a.state = 'queued' ORDER BY a.rowid LIMIT 1").fetchone()
        if row is None:
            return None
        if JOB_TYPES[row['tool']].resource_class == 'media' and not self._try_host_slot():
            with self._tx() as conn:
                last = conn.execute('SELECT reason_code FROM events WHERE job_id = ? ORDER BY seq DESC LIMIT 1',
                                    (row['job_id'],)).fetchone()
                still = conn.execute("SELECT state FROM attempts WHERE job_id = ? AND attempt = ?",
                                     (row['job_id'], row['attempt'])).fetchone()
                if still and still['state'] == 'queued' and (last is None or last['reason_code'] != WAITING_HOST_SLOT):
                    self._event(conn, row['job_id'], row['attempt'], 'queued', 'queued', WAITING_HOST_SLOT)
            return None
        with self._tx() as conn:
            current = conn.execute("SELECT state FROM attempts WHERE job_id = ? AND attempt = ?",
                                   (row['job_id'], row['attempt'])).fetchone()
            if current is None or current['state'] != 'queued':
                return None  # cancelled while the host slot was being taken; the loop releases it
            job = conn.execute('SELECT * FROM jobs WHERE job_id = ?', (row['job_id'],)).fetchone()
            fence = secrets.token_hex(16)
            now = utc_now()
            kind = self._kind(job['tool'])
            conn.execute("UPDATE attempts SET state = 'running', fence = ?, instance_id = ?, worker_kind = ?, "
                         'started_at = ? WHERE job_id = ? AND attempt = ?',
                         (fence, self.instance_id, kind, now, row['job_id'], row['attempt']))
            conn.execute("UPDATE jobs SET state = 'running', updated_at = ? WHERE job_id = ?", (now, row['job_id']))
            self._event(conn, row['job_id'], row['attempt'], 'queued', 'running', 'claimed')
            source = self._source_row(conn, job['source_artifact_id'])
        return {'job_id': row['job_id'], 'attempt': row['attempt'], 'fence': fence, 'tool': job['tool'],
                'parameters': json.loads(job['parameters_json']), 'source': dict(source), 'worker_kind': kind,
                'bound': json.loads(job['bound_input_json']) if job['bound_input_json'] else None}

    def _kind(self, tool):
        return 'test_stub' if self.command_builder is not None else f'tool_api_{tool}'

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

    @staticmethod
    def real_command(tool, args):
        """Exact product argv for an allowlisted tool (fixed repository scripts, never a shell).

        ``tool_api.worker_command`` has no ``apply_capture_profile`` branch: ``tool_api.execute``
        runs ``ApplicationAdapter`` in-process. The supervisor therefore launches tool_api's own
        ``run`` CLI for that tool, which repeats validate + validate_tool_arguments and runs the
        same adapter as the CLI/MCP path, inside this supervisor's owned process group.
        """
        if tool == 'apply_capture_profile':
            interpreter = os.environ.get('VIDEO_UTILS_PYTHON', sys.executable)
            return [interpreter, str(ROOT / 'scripts' / 'tool_api.py'), 'run', tool, '--arguments', canonical(args)]
        return tool_api.worker_command(tool, args)

    def _build_processing_command(self, tool, args):
        tool_api.validate(args, self.descriptors[tool]['inputSchema'])
        tool_api.validate_tool_arguments(tool, args)
        if self.command_builder is None:
            return self.real_command(tool, args)
        command = self.command_builder(dict(args, _web_job={'tool': tool, 'runs_dir': str(self.runs_dir)}))
        if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
            raise tool_api.ToolError('test command builder must return a non-empty argv list')
        return command

    def _run_attempt(self, claim):
        if claim.get('tool', TOOL) != TOOL:
            self._run_processing(claim)
            return
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

    # ----------------------------------------------------------------- S3 processing attempts

    def _launch(self, claim, command, stdout, stderr):
        try:
            process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stdout,
                                       stderr=stderr, start_new_session=True, close_fds=True)
        except OSError:
            return None, None
        pgid = live_pgid(process.pid)
        birth = process_birth(process.pid)
        with self._tx() as conn:
            conn.execute("UPDATE attempts SET pid = ?, pgid = ?, worker_birth = ? WHERE job_id = ? AND attempt = ? "
                         "AND state = 'running' AND fence = ?",
                         (process.pid, pgid, birth, claim['job_id'], claim['attempt'], claim['fence']))
            self._event(conn, claim['job_id'], claim['attempt'], 'running', 'running', 'worker_started')
        return process, pgid

    def _fresh_snapshot(self, tool, args):
        """Names that existed before launch, so a published output must be a fresh directory."""
        directory = (Path(args['run_dir']) / 'capture-profiles') if tool == 'capture_profile' else self.runs_dir
        try:
            return frozenset(os.listdir(directory))
        except FileNotFoundError:
            return frozenset()

    def _run_processing(self, claim):
        tool = claim['tool']
        job_dir = self._job_directory(claim['job_id'])
        state, source_path = self._resolve_source(claim['source'])
        if state != 'current':
            self._finish(claim, 'failed', 'source_changed' if state == 'stale' else 'source_missing')
            return
        self._phase(claim, 'validating')
        try:
            args = self.derive_args(tool, claim['source'], source_path, claim['parameters'], claim['bound'],
                                    recheck=True)
        except WebJobsError as error:
            self._finish(claim, 'failed', error.code if error.code in ('review_stale', 'authoring_stale')
                         else 'launch_refused')
            return
        except (OSError, ValueError, KeyError, TypeError):
            self._finish(claim, 'failed', 'launch_refused')
            return
        try:
            command = self._build_processing_command(tool, args)
        except (tool_api.ValidationError, tool_api.ToolError, ValueError, OSError):
            self._finish(claim, 'failed', 'launch_refused')
            return
        before = self._fresh_snapshot(tool, args)
        timeout = claim['parameters']['timeout_seconds'] + OUTER_HEADROOM_S
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process, pgid = self._launch(claim, command, stdout, stderr)
            if process is None:
                self._finish(claim, 'failed', 'launch_failed')
                return
            outcome, receipt = self._wait(claim, process, pgid, timeout)
            if outcome == 'cancelled':
                self._finish(claim, 'cancelled', 'cancel_requested', receipt=receipt)
                return
            if outcome == 'deadline':
                self._finish(claim, 'failed', 'deadline_exceeded', receipt=receipt)
                return
            self._complete_processing(claim, process.returncode, stdout, args, before, job_dir)

    def _complete_processing(self, claim, returncode, stdout, args, before, job_dir):
        tool = claim['tool']
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
            checks = {'status': 'error', 'returncode': returncode}
            reason = 'worker_failed'
            if (tool == 'capture_profile' and isinstance(result, dict) and result.get('status') == 'error'
                    and isinstance(result.get('error'), dict)):
                code = result['error'].get('code')
                checks['code'] = code[:128] if isinstance(code, str) and re.fullmatch(r'[a-z_]{1,128}', code) else None
                reason = 'worker_rejected'
            self._finish(claim, 'failed', reason, result=checks)
            return
        if not isinstance(result, dict):
            self._finish(claim, 'failed', 'malformed_result')
            return
        try:
            verified = self._verify_processing(claim, result, args, before)
        except WebJobsError as error:
            reason = error.code if error.code in ('source_changed', 'malformed_result') else 'publication_failed'
            self._finish(claim, 'failed', reason, result={'status': 'unverified', 'code': error.code})
            return
        except (OSError, ValueError, KeyError, TypeError, artifact_ids.ArtifactIdError):
            self._finish(claim, 'failed', 'publication_failed', result={'status': 'unverified'})
            return
        self._phase(claim, 'finalizing')
        try:
            rows = self._publish_processing(claim, verified, job_dir)
        except _SimulatedCrash:
            raise
        except (OSError, ValueError, WebJobsError):
            self._finish(claim, 'failed', 'publication_failed', result=verified['checks'])
            return
        self._finish(claim, 'succeeded', None, result=verified['checks'], artifacts=rows, event_reason='published')

    # ----------------------------------------------------------------- verification helpers

    def _fresh_dir(self, parent, name, reported, before):
        """A directory the worker created during this attempt: fresh name, real dir, reported identity."""
        if not isinstance(name, str) or name in before:
            raise WebJobsError('publication_failed', 500, 'worker output directory is not fresh')
        artifact_ids.check_run_id(name)
        path = parent / name
        if not self._confined_dir(path):
            raise WebJobsError('publication_failed', 500, 'worker output directory is not confined')
        if not isinstance(reported, str):
            raise WebJobsError('publication_failed', 500, 'worker result lacks its output directory')
        try:
            observed, expected = os.stat(reported), os.lstat(path)
        except OSError:
            raise WebJobsError('publication_failed', 500, 'reported output directory is unavailable') from None
        if (observed.st_dev, observed.st_ino) != (expected.st_dev, expected.st_ino):
            raise WebJobsError('publication_failed', 500, 'reported output directory is outside artifacts/runs')
        return path

    @staticmethod
    def _read_json_file(path, limit):
        descriptor, before = _open_regular_nofollow(path)
        try:
            digest, size = hash_descriptor(descriptor, limit)
            data = os.pread(descriptor, limit + 1, 0)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if file_signature(before) != file_signature(after) or len(data) != size:
            raise ValueError('file changed while reading')
        return strict_json(data, 'worker json'), digest, size

    @staticmethod
    def _output_row(selector, role, name, digest, size, content_type, served):
        return {'role': role, 'name': name, 'artifact_id': artifact_ids.artifact_id_for(selector, digest),
                'sha256': digest, 'size_bytes': size, 'content_type': content_type, 'served_via_run_media': served}

    def _verify_run_outputs(self, run_id, run_dir, manifest):
        outputs, hashes = manifest.get('outputs'), manifest.get('output_sha256')
        if not isinstance(outputs, dict) or not isinstance(hashes, dict):
            raise WebJobsError('publication_failed', 500, 'run manifest lacks outputs and hashes')
        rows = []
        for role, name in sorted(outputs.items()):
            if role not in RUN_OUTPUT_ROLES or name != f'{role}.wav':
                raise WebJobsError('publication_failed', 500, 'run manifest names an unexpected output role')
            digest, size = hash_regular_file(run_dir / name, MAX_PCM_BYTES)
            if hashes.get(name) != digest:
                raise WebJobsError('publication_failed', 500, 'run output bytes differ from the manifest hash')
            rows.append(self._output_row(f'{run_id}/{name}', role, name, digest, size, 'audio/wav',
                                         role in RUN_MEDIA_ROLES))
        if 'source' not in outputs:
            raise WebJobsError('publication_failed', 500, 'run manifest lacks its native source output')
        return rows

    @staticmethod
    def _pcm_summary(manifest):
        pcm = manifest.get('pcm') if isinstance(manifest.get('pcm'), dict) else {}
        return {key: pcm.get(key) for key in ('sample_rate', 'channels', 'sample_count', 'duration_seconds', 'codec')
                if isinstance(pcm.get(key), (int, float, str)) and not isinstance(pcm.get(key), bool)}

    @staticmethod
    def _numbers(value, depth=0):
        """Numeric-only copy (lists of numbers / nulls) of a worker capture block; strings dropped."""
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, list) and depth < 2:
            return [WebJobs._numbers(item, depth + 1) for item in value[:8]]
        return None

    def _verify_processing(self, claim, result, args, before):
        tool = claim['tool']
        sha = claim['source']['sha256']
        if tool == 'denoise':
            if result.get('status') != 'rendered_unreviewed' or not isinstance(result.get('source'), dict):
                raise WebJobsError('malformed_result', 500, 'denoise result is not rendered_unreviewed')
            if result['source'].get('sha256') != sha:
                raise WebJobsError('source_changed', 409, 'worker hashed different source bytes')
            run_id = result.get('run_id')
            run_dir = self._fresh_dir(self.runs_dir, run_id, result.get('run_dir'), before)
            manifest, manifest_sha, manifest_size = self._read_json_file(run_dir / 'manifest.json', MAX_MANIFEST_BYTES)
            if manifest != result:
                raise WebJobsError('publication_failed', 500, 'run manifest differs from the worker result')
            outputs = self._verify_run_outputs(run_id, run_dir, manifest)
            outputs.append(self._output_row(f'{run_id}/manifest.json', 'manifest', 'manifest.json', manifest_sha,
                                            manifest_size, 'application/json', False))
            profile = manifest.get('profile') if isinstance(manifest.get('profile'), dict) else {}
            preservation = manifest.get('frequency_preservation') if isinstance(
                manifest.get('frequency_preservation'), dict) else {}
            checks = {'status': 'rendered_unreviewed', 'run_id': run_id, 'source_sha256': sha,
                      'profile_name': profile.get('name') if isinstance(profile.get('name'), str) else None,
                      'pcm': self._pcm_summary(manifest), 'outputs': outputs,
                      'high_pass_applied': preservation.get('high_pass_applied'),
                      'hum_notches_applied': preservation.get('hum_notches_applied'),
                      'dsp_performed': True, 'master_adopted': False, 'listening_accepted': False}
            return {'run_id': run_id, 'authoring_id': None, 'worker_status': 'rendered_unreviewed',
                    'authorization_scope': None, 'outputs': outputs, 'checks': checks}
        if tool == 'capture_profile':
            status = result.get('status')
            if status not in ('authored_unrendered', 'draft_authorization_incomplete', 'needs_reselection') \
                    or result.get('dsp_performed') is not False or result.get('listening_accepted') is not False:
                raise WebJobsError('malformed_result', 500, 'capture_profile result status is not an authoring status')
            if result.get('source_sha256') != sha:
                raise WebJobsError('source_changed', 409, 'worker hashed different source bytes')
            run_id = claim['bound']['run_id']
            output = result.get('output_dir')
            name = Path(output).name if isinstance(output, str) else None
            parent = self.runs_dir / run_id / 'capture-profiles'
            directory = self._fresh_dir(parent, name, output, before)
            receipt, receipt_sha, receipt_size = self._read_json_file(directory / 'receipt.json', 64 * 1024)
            if receipt_sha != result.get('receipt_sha256') or receipt.get('status') != status:
                raise WebJobsError('publication_failed', 500, 'authoring receipt differs from the worker result')
            selector = f'{run_id}/capture-profiles/{name}'
            outputs = [self._output_row(f'{selector}/receipt.json', 'capture_receipt', 'receipt.json', receipt_sha,
                                        receipt_size, 'application/json', False)]
            for role, file_name, digest_key in (('capture_profile', 'profile.json', 'profile_sha256'),
                                                ('capture_proposal', 'proposal.json', None)):
                path = directory / file_name
                if not os.path.lexists(path):
                    continue
                digest, size = hash_regular_file(path, MAX_REVIEW_BYTES)
                if digest_key and digest != result.get(digest_key):
                    raise WebJobsError('publication_failed', 500, 'authored profile differs from the worker result')
                outputs.append(self._output_row(f'{selector}/{file_name}', role, file_name, digest, size,
                                                'application/json', False))
            if status == 'authored_unrendered' and not any(o['role'] == 'capture_profile' for o in outputs):
                raise WebJobsError('publication_failed', 500, 'authored_unrendered without profile.json')
            review = receipt.get('review') if isinstance(receipt.get('review'), dict) else {}
            assertions = review.get('assertions') if isinstance(review.get('assertions'), dict) else {}
            scope = assertions.get('authorization_scope')
            capture = result.get('capture') if isinstance(result.get('capture'), dict) else {}
            checks = {'status': status, 'run_id': run_id, 'authoring_id': name, 'source_sha256': sha,
                      'authorization_scope': scope if scope in AUTHORIZATION_SCOPES else None,
                      'review_status': assertions.get('review_status') if assertions.get('review_status')
                      in REVIEW_STATUSES else None,
                      'capture': {key: self._numbers(capture.get(key)) for key in
                                  ('requested_seconds', 'native_samples', 'source_media_span_seconds')},
                      'outputs': outputs, 'dsp_performed': False, 'master_adopted': False,
                      'listening_accepted': False}
            return {'run_id': run_id, 'authoring_id': name, 'worker_status': status,
                    'authorization_scope': checks['authorization_scope'], 'outputs': outputs, 'checks': checks}
        # apply_capture_profile: tool_api `run` envelope around the application summary
        summary = result.get('result')
        if result.get('status') != 'completed' or result.get('tool') != tool or not isinstance(summary, dict):
            raise WebJobsError('malformed_result', 500, 'apply result is not a completed tool_api envelope')
        if (summary.get('status') != 'rendered_unreviewed' or summary.get('dsp_performed') is not True
                or summary.get('listening_accepted') is not False or summary.get('master_adopted') is not False):
            raise WebJobsError('malformed_result', 500, 'apply summary claims differ from the contract')
        if summary.get('source_sha256') != sha:
            raise WebJobsError('source_changed', 409, 'worker hashed different source bytes')
        if summary.get('authoring_receipt_sha256') != claim['bound']['receipt_sha256']:
            raise WebJobsError('publication_failed', 500, 'applied authoring receipt differs from the bound input')
        reported = summary.get('run_dir')
        run_id = Path(reported).name if isinstance(reported, str) else None
        run_dir = self._fresh_dir(self.runs_dir, run_id, reported, before)
        manifest, manifest_sha, manifest_size = self._read_json_file(run_dir / 'manifest.json', MAX_MANIFEST_BYTES)
        if manifest_sha != summary.get('manifest_sha256'):
            raise WebJobsError('publication_failed', 500, 'applied run manifest differs from the worker summary')
        receipt_sha, receipt_size = hash_regular_file(run_dir / 'application-receipt.json', 64 * 1024)
        if receipt_sha != summary.get('receipt_sha256'):
            raise WebJobsError('publication_failed', 500, 'application receipt differs from the worker summary')
        outputs = self._verify_run_outputs(run_id, run_dir, manifest)
        outputs.append(self._output_row(f'{run_id}/manifest.json', 'manifest', 'manifest.json', manifest_sha,
                                        manifest_size, 'application/json', False))
        outputs.append(self._output_row(f'{run_id}/application-receipt.json', 'application_receipt',
                                        'application-receipt.json', receipt_sha, receipt_size, 'application/json',
                                        False))
        capture = summary.get('capture') if isinstance(summary.get('capture'), dict) else {}
        export = summary.get('export') if isinstance(summary.get('export'), dict) else {}
        checks = {'status': 'rendered_unreviewed', 'run_id': run_id, 'source_sha256': sha,
                  'pcm': self._pcm_summary(manifest), 'outputs': outputs,
                  'capture': {key: self._numbers(capture.get(key)) for key in
                              ('requested_seconds', 'profile_seconds', 'native_samples', 'source_media_span_seconds')},
                  'export_status': export.get('status') if isinstance(export.get('status'), str) else None,
                  'dsp_performed': True, 'master_adopted': False, 'listening_accepted': False}
        return {'run_id': run_id, 'authoring_id': None, 'worker_status': 'rendered_unreviewed',
                'authorization_scope': None, 'outputs': outputs, 'checks': checks}

    def _publish_processing(self, claim, verified, job_dir):
        """Fenced, path-free publication.json for a processing attempt (no media is copied)."""
        job_id, attempt = claim['job_id'], claim['attempt']
        staging = job_dir / f'.staging-{attempt}-{secrets.token_hex(8)}'
        os.mkdir(staging, 0o700)
        target = job_dir / f'attempt-{attempt}'
        publication = {'schema': 'video-utils/web-job-publication', 'schema_version': 2, 'job_id': job_id,
                       'attempt': attempt, 'fence': claim['fence'], 'tool': claim['tool'],
                       'worker_kind': claim.get('worker_kind'),
                       'source_artifact_id': claim['source']['source_artifact_id'],
                       'source_sha256': claim['source']['sha256'], 'run_id': verified['run_id'],
                       'authoring_id': verified['authoring_id'], 'worker_status': verified['worker_status'],
                       'authorization_scope': verified['authorization_scope'], 'bound_input': claim['bound'],
                       'parameters': claim['parameters'], 'outputs': verified['outputs'],
                       'worker_checks': verified['checks'], 'claim_class': CLAIM_CLASS,
                       'unknowns': processing_unknowns(), 'master_adopted': False, 'listening_accepted': False,
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
        digest = sha256_hex(data)
        rows = [{'artifact_id': output_artifact_id(job_id, attempt, 'publication', digest), 'role': 'publication',
                 'sha256': digest, 'size_bytes': len(data), 'content_type': ROLES['publication'][1],
                 'rel_path': f'jobs/{job_id}/attempt-{attempt}/{ROLES["publication"][0]}'}]
        if self.fault == 'after_publish_before_commit':
            raise _SimulatedCrash()
        return rows

    def _read_publication(self, conn, job_id, attempt):
        """Hash-verified private publication.json of one attempt, or None."""
        row = conn.execute("SELECT * FROM artifacts WHERE job_id = ? AND attempt = ? AND role = 'publication'",
                           (job_id, attempt)).fetchone()
        if row is None:
            return None
        path = self.state_root / row['rel_path']
        try:
            data, digest, _ = self._read_json_file(path, MAX_PUBLICATION_BYTES)
        except (OSError, ValueError):
            return None
        if digest != row['sha256'] or not isinstance(data, dict):
            return None
        return data

    def check_review_current(self, review, source_path):
        """review_stale unless source, baseline manifest, source.wav and review file hashes still match."""
        run_dir = self.runs_dir / review['run_id']
        checks = ((source_path, review['source_sha256'], self.max_source_bytes),
                  (run_dir / 'manifest.json', review['manifest_sha256'], MAX_MANIFEST_BYTES),
                  (run_dir / 'source.wav', review['pcm_sha256'], MAX_PCM_BYTES),
                  (self.runs_dir.joinpath(*review['rel_path'].split('/')), review['review_sha256'], MAX_REVIEW_BYTES))
        if not self._confined_dir(run_dir) or not self._confined_dir(run_dir / REVIEW_DIR):
            raise WebJobsError('review_stale', 409, 'capture review run directory changed')
        for path, expected, limit in checks:
            try:
                digest, _ = hash_regular_file(path, limit)
            except (OSError, ValueError):
                digest = None
            if digest != expected:
                raise WebJobsError('review_stale', 409, 'capture review binding no longer matches its bytes')

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
                'source_full_frame_decode_verified', 'physical_capture_sync_verified',
                'comparison_scope', 'source_packet_count_total', 'output_packet_count_total',
                'source_presented_packet_count', 'output_presented_packet_count',
                'source_decode_only_packets', 'output_decode_only_packets') if key in video} or None,
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
                or publication.get('attempt') != attempt or publication.get('fence') != row['fence']):
            return None
        if publication.get('tool') in PROCESSING_TOOLS:
            return self._adoptable_processing(publication, job_id, attempt, digest, size)
        if not isinstance(publication.get('artifacts'), list):
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

    def _output_base(self, publication):
        run_id = publication.get('run_id')
        artifact_ids.check_run_id(run_id)
        base = self.runs_dir / run_id
        if publication.get('tool') == 'capture_profile':
            authoring = publication.get('authoring_id')
            artifact_ids.check_run_id(authoring)
            base = base / 'capture-profiles' / authoring
        return base

    def _adoptable_processing(self, publication, job_id, attempt, digest, size):
        """A fenced processing publication whose listed run outputs still re-hash; else None."""
        try:
            base = self._output_base(publication)
        except artifact_ids.ArtifactIdError:
            return None
        if not self._confined_dir(base) or not isinstance(publication.get('outputs'), list):
            return None
        for item in publication['outputs']:
            name = item.get('name') if isinstance(item, dict) else None
            if not isinstance(name, str) or '/' in name or name.startswith('.'):
                return None
            try:
                observed, observed_size = hash_regular_file(base / name, MAX_PCM_BYTES)
            except (OSError, ValueError):
                return None
            if observed != item.get('sha256') or observed_size != item.get('size_bytes'):
                return None
        rows = [{'artifact_id': output_artifact_id(job_id, attempt, 'publication', digest), 'role': 'publication',
                 'sha256': digest, 'size_bytes': size, 'content_type': ROLES['publication'][1],
                 'rel_path': f'jobs/{job_id}/attempt-{attempt}/{ROLES["publication"][0]}'}]
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
        projection = {
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
        if job['tool'] == TOOL:
            return projection  # S2 share_export shape, unchanged
        latest_success = next((row for row in reversed(attempt_rows) if row['state'] == 'succeeded'), None)
        checks = latest_success['worker_checks'] if latest_success else None
        checks = checks if isinstance(checks, dict) else {}
        for key in ('source_duration_seconds', 'source_duration_seconds_reason'):
            unknowns.pop(key, None)
        unknowns.update(processing_unknowns())
        projection.update({
            'bound_input': json.loads(job['bound_input_json']) if job['bound_input_json'] else None,
            'run_id': checks.get('run_id'), 'authoring_id': checks.get('authoring_id'),
            'worker_status': checks.get('status') if latest_success else None,
            'outputs': checks.get('outputs', []) if latest_success else [],
            'admission_state': self.admission_state(job['tool'])[0],
            'unknowns': unknowns,
        })
        return projection

    def get_job(self, job_id):
        return 200, self.project(job_id)

    # ----------------------------------------------------------------- S3 runs, capture reviews, measurement

    def _source_or_404(self, source_artifact_id):
        if not isinstance(source_artifact_id, str) or not ARTIFACT_ID.fullmatch(source_artifact_id):
            raise WebJobsError('malformed_id', 400, 'source artifact id must be art_ followed by 32 hex digits')
        with self._db() as conn:
            row = self._source_row(conn, source_artifact_id)
        if row is None:
            raise WebJobsError('unknown_source', 404, 'source artifact id is not admitted')
        return dict(row)

    def _run_manifest(self, run_id):
        """(manifest dict, sha256) of a confined run, or raises a typed refusal."""
        try:
            artifact_ids.check_run_id(run_id)
        except artifact_ids.ArtifactIdError:
            raise WebJobsError('malformed_id', 400, 'run id must be one safe component') from None
        run_dir = self.runs_dir / run_id
        if not self._confined_dir(run_dir):
            raise WebJobsError('unknown_run', 404, 'run id names no run directory')
        try:
            manifest, digest, _ = self._read_json_file(run_dir / 'manifest.json', MAX_MANIFEST_BYTES)
        except (OSError, ValueError):
            raise WebJobsError('run_not_baseline', 422, 'run lacks a bounded regular manifest.json') from None
        if not isinstance(manifest, dict):
            raise WebJobsError('run_not_baseline', 422, 'run manifest is not an object')
        return run_dir, manifest, digest

    def _source_path_matches(self, manifest, source):
        """True when the manifest names exactly the admitted source file (capture_profile requires it)."""
        claimed = manifest.get('source', {}).get('path') if isinstance(manifest.get('source'), dict) else None
        if not isinstance(claimed, str):
            return False
        try:
            private = self.runs_dir.joinpath(*source['selector'].split('/'))
            return os.path.realpath(claimed) == os.path.realpath(private)
        except (OSError, ValueError):
            return False

    @staticmethod
    def _baseline_shape(manifest):
        return (manifest.get('schema_version') == 1
                and all(isinstance(manifest.get(key), dict) for key in ('source', 'outputs', 'output_sha256',
                                                                        'timeline', 'pcm'))
                and manifest['outputs'].get('source') == 'source.wav'
                and manifest['timeline'].get('no_time_stretch') is True)

    def list_runs(self, source_artifact_id):
        """Runs whose manifest source sha256 equals the admitted source (no paths; claimed hashes labelled)."""
        source = self._source_or_404(source_artifact_id)
        runs, scanned, truncated = [], 0, False
        try:
            entries = sorted(os.scandir(self.runs_dir), key=lambda entry: entry.name)
        except OSError:
            entries = []
        for entry in entries:
            if scanned >= MAX_RUN_SCAN:
                truncated = True
                break
            scanned += 1
            if entry.name.startswith('.') or not entry.is_dir(follow_symlinks=False):
                continue
            try:
                artifact_ids.check_run_id(entry.name)
                run_dir, manifest, manifest_sha = self._run_manifest(entry.name)
            except (artifact_ids.ArtifactIdError, WebJobsError):
                continue
            claimed = manifest.get('source') if isinstance(manifest.get('source'), dict) else {}
            if claimed.get('sha256') != source['sha256']:
                continue
            baseline = self._baseline_shape(manifest) and os.path.isfile(run_dir / 'source.wav') \
                and not os.path.islink(run_dir / 'source.wav')
            candidate = os.path.isfile(run_dir / 'application-receipt.json')
            path_ok = self._source_path_matches(manifest, source)
            outputs = manifest.get('outputs') if isinstance(manifest.get('outputs'), dict) else {}
            hashes = manifest.get('output_sha256') if isinstance(manifest.get('output_sha256'), dict) else {}
            profile = manifest.get('profile') if isinstance(manifest.get('profile'), dict) else {}
            output_rows = []
            for role, name in sorted(outputs.items()):
                digest = hashes.get(name) if isinstance(name, str) else None
                if role in RUN_OUTPUT_ROLES and name == f'{role}.wav' and isinstance(digest, str) \
                        and re.fullmatch(r'[0-9a-f]{64}', digest):
                    output_rows.append({'role': role, 'artifact_id': artifact_ids.artifact_id_for(
                        f'{entry.name}/{name}', digest), 'sha256_claimed': digest,
                        'served_via_run_media': role in RUN_MEDIA_ROLES})
            runs.append({
                'run_id': entry.name,
                'role': 'capture_candidate' if candidate else ('baseline' if baseline else 'other'),
                'baseline_eligible': bool(baseline and path_ok),
                'baseline_eligibility_reason': (
                    'bounded manifest + source.wav + native timeline; manifest names the admitted file'
                    if baseline and path_ok else
                    'manifest names another copy of these bytes; capture_profile requires the exact admitted file'
                    if baseline else 'no native source.wav baseline in this run'),
                'profile_name': profile.get('name') if isinstance(profile.get('name'), str) else None,
                'status': manifest.get('status') if isinstance(manifest.get('status'), str) else None,
                'pcm': self._pcm_summary(manifest), 'manifest_sha256': manifest_sha, 'outputs': output_rows,
                'output_hash_basis': 'manifest-claimed sha256, not re-hashed by this listing; media and '
                                     'capture routes re-hash'})
        return 200, {'schema_version': 1, 'source_artifact_id': source_artifact_id, 'runs': runs,
                     'scanned_entries': scanned, 'truncated': truncated,
                     'unknowns': {'probe_duration_seconds': None,
                                  'probe_duration_seconds_reason': 'listing reports bound run manifest PCM only; '
                                                                   'no container probe'}}

    def _baseline(self, source, run_id, *, rehash_pcm=True):
        """Validated baseline binding: run_dir, manifest sha, pcm sha, header. Typed refusals."""
        run_dir, manifest, manifest_sha = self._run_manifest(run_id)
        claimed = manifest.get('source') if isinstance(manifest.get('source'), dict) else {}
        if claimed.get('sha256') != source['sha256']:
            raise WebJobsError('run_not_bound', 409, 'run manifest source sha256 differs from this source')
        if not self._baseline_shape(manifest):
            raise WebJobsError('run_not_baseline', 422, 'run lacks a bounded native source.wav baseline')
        if not self._source_path_matches(manifest, source):
            raise WebJobsError('run_not_bound', 409, 'run manifest names another file with these bytes',
                               detail_code='source_path_differs')
        pcm_path = run_dir / 'source.wav'
        try:
            descriptor, before = _open_regular_nofollow(pcm_path)
        except OSError:
            raise WebJobsError('run_not_baseline', 422, 'run lacks a regular source.wav') from None
        try:
            if before.st_size > MAX_PCM_BYTES:
                raise WebJobsError('run_not_baseline', 422, 'source.wav exceeds 1 GiB')
            header = wav_header(descriptor, before.st_size)
            pcm_sha = hash_descriptor(descriptor, MAX_PCM_BYTES)[0] if rehash_pcm else None
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if file_signature(before) != file_signature(after):
            raise WebJobsError('run_not_baseline', 422, 'source.wav changed while reading')
        claimed_pcm = manifest['output_sha256'].get('source.wav')
        if rehash_pcm and pcm_sha != claimed_pcm:
            raise WebJobsError('run_not_baseline', 422, 'source.wav bytes differ from the manifest hash',
                               detail_code='pcm_hash_mismatch')
        reference = manifest['pcm']
        for key in ('sample_rate', 'channels', 'sample_count'):
            if reference.get(key) != header[key]:
                raise WebJobsError('run_not_baseline', 422, f'manifest pcm {key} differs from the WAV header')
        return {'run_dir': run_dir, 'manifest': manifest, 'manifest_sha256': manifest_sha,
                'pcm_sha256': pcm_sha or claimed_pcm, 'header': header}

    @staticmethod
    def _interval(start, end, header):
        """Native sample interval exactly as capture_profile maps it; typed out-of-range refusal."""
        rate, count = header['sample_rate'], header['sample_count']
        if not (math.isfinite(start) and math.isfinite(end)) or start < 0 or end <= start:
            raise WebJobsError('interval_out_of_range', 422, 'interval needs finite 0 <= start < end')
        if not MIN_CAPTURE_SECONDS - 1e-10 <= end - start <= MAX_CAPTURE_SECONDS + 1e-10:
            raise WebJobsError('interval_out_of_range', 422, 'interval duration must be 0.1-10 seconds')
        samples = [round(start * rate), round(end * rate)]
        if not 0 <= samples[0] < samples[1] <= count or not (rate + 9) // 10 <= samples[1] - samples[0] <= rate * 10:
            raise WebJobsError('interval_out_of_range', 422, 'interval lies outside the native decoded extent')
        return samples

    @staticmethod
    def overlaps_setup(start_seconds):
        """True when [start, end) intersects the first five decoded seconds [0, 5)."""
        return start_seconds < SETUP_INTERVAL_SECONDS

    def measure_interval(self, source_artifact_id, body):
        """POST capture-measurements: section 7.4 statistics of the mixture. Writes nothing."""
        closed_object(body, {'run_id': str, 'start_seconds': (int, float), 'end_seconds': (int, float)})
        source = self._source_or_404(source_artifact_id)
        self._require_current(source)
        base = self._baseline(source, body['run_id'])
        header = base['header']
        samples = self._interval(float(body['start_seconds']), float(body['end_seconds']), header)
        offset = header['data_offset'] + samples[0] * header['block_alignment']
        length = (samples[1] - samples[0]) * header['block_alignment']
        descriptor, _ = _open_regular_nofollow(base['run_dir'] / 'source.wav')
        try:
            raw = os.pread(descriptor, length, offset)
        finally:
            os.close(descriptor)
        if len(raw) != length:
            raise WebJobsError('interval_out_of_range', 422, 'interval extends past the data chunk')
        channels = interval_statistics(decode_frames(raw, header), header['sample_rate'])
        unknowns = processing_unknowns()
        for key, reason in (('noise_only', 'no statistic establishes a noise-only interval'),
                            ('fan_band_energy', 'no fan-band model is measured here'),
                            ('music_or_click_presence', 'not detected; operator assertion only'),
                            ('low_register_content_hz_32', '~32 Hz content is not separated from the mixture')):
            unknowns[key] = None
            unknowns[key + '_reason'] = reason
        return 200, {
            'schema_version': 1, 'claim_class': 'measurement_of_mixture', 'source_artifact_id': source_artifact_id,
            'source_sha256': source['sha256'], 'run_id': body['run_id'], 'manifest_sha256': base['manifest_sha256'],
            'pcm_sha256': base['pcm_sha256'], 'pcm_rehashed': True,
            'interval': {'start_seconds': float(body['start_seconds']), 'end_seconds': float(body['end_seconds']),
                         'start_sample': samples[0], 'end_sample': samples[1],
                         'sample_rate': header['sample_rate'], 'channels': header['channels'],
                         'codec': header['codec'], 'time_axis': 'decoded_source_audio_samples',
                         'duration_seconds': (samples[1] - samples[0]) / header['sample_rate']},
            'overlaps_setup_interval': self.overlaps_setup(float(body['start_seconds'])),
            'setup_interval_note': ('the first five seconds include setup guitar/amp sounds and possible windup; '
                                    'never auto-confirmed as noise'),
            'channels': channels, 'selects_interval': False, 'run_noise_json': self._run_noise(base, source),
            'unknowns': unknowns, 'writes': 'none'}

    def _run_noise(self, base, source):
        path = base['run_dir'] / 'noise.json'
        if not os.path.lexists(path):
            return {'present': False}
        try:
            data, _, _ = self._read_json_file(path, MAX_MANIFEST_BYTES)
        except (OSError, ValueError):
            return {'present': True, 'readable': False}
        bound = isinstance(data, dict) and isinstance(data.get('source'), dict) \
            and data['source'].get('sha256') == source['sha256']
        if not bound:
            return {'present': True, 'readable': True, 'bound_to_source': False, 'fields': None}
        fields = {key: value for key, value in data.items()
                  if isinstance(value, (int, float)) and not isinstance(value, bool)}
        return {'present': True, 'readable': True, 'bound_to_source': True, 'fields': dict(list(fields.items())[:32])}

    REVIEW_BODY = {'idempotency_key': str, 'run_id': str, 'expected_source_sha256': str,
                   'start_seconds': (int, float), 'end_seconds': (int, float), 'review_status': str,
                   'authorization_scope': str, 'music_status': str, 'click_status': str,
                   'ambient_music_status': str, 'note': str, 'setup_interval_acknowledged': bool}

    def review_projection(self, row, replayed=None):
        record = {
            'review_id': row['review_id'], 'source_artifact_id': row['source_artifact_id'],
            'source_sha256': row['source_sha256'], 'run_id': row['run_id'],
            'manifest_sha256': row['manifest_sha256'], 'pcm_sha256': row['pcm_sha256'],
            'review_sha256': row['review_sha256'],
            'interval': {'start_seconds': row['start_seconds'], 'end_seconds': row['end_seconds'],
                         'start_sample': row['start_sample'], 'end_sample': row['end_sample'],
                         'sample_rate': row['sample_rate'], 'time_axis': 'decoded_source_audio_samples',
                         'duration_seconds': (row['end_sample'] - row['start_sample']) / row['sample_rate']},
            'review_status': row['review_status'], 'authorization_scope': row['authorization_scope'],
            'music_status': row['music_status'], 'click_status': row['click_status'],
            'ambient_music_status': row['ambient_music_status'], 'note': row['note'],
            'overlaps_setup_interval': bool(row['overlaps_setup_interval']),
            'setup_interval_acknowledged': bool(row['setup_interval_acknowledged']),
            'selected_by': WEB_REVIEWER, 'reviewed_by': WEB_REVIEWER,
            'authorization_reference': f'video-utils web capture review {row["review_id"]}',
            'identity_authenticated': False, 'created_at': row['created_at'],
            'renderable': (row['authorization_scope'] == 'experimental_capture_render'
                           and row['review_status'] != 'rejected_contaminated'),
            'rechecked': False, 'rechecked_reason': 'listing does not re-hash; job submission re-verifies all four hashes',
            'claim_class': 'operator_assertion_record', 'unknowns': processing_unknowns()}
        if replayed is not None:
            record['replayed'] = replayed
        return record

    def list_capture_reviews(self, source_artifact_id):
        self._source_or_404(source_artifact_id)
        with self._db() as conn:
            rows = conn.execute('SELECT * FROM capture_reviews WHERE source_artifact_id = ? ORDER BY created_at DESC, '
                                'rowid DESC LIMIT 200', (source_artifact_id,)).fetchall()
        return 200, {'schema_version': 1, 'source_artifact_id': source_artifact_id,
                     'reviews': [self.review_projection(dict(row)) for row in rows], 'truncated': len(rows) >= 200}

    def create_capture_review(self, source_artifact_id, body):
        """POST capture-reviews: immutable, create-only review record bound to source/run/PCM hashes."""
        self._check_open()
        closed_object(body, self.REVIEW_BODY)
        source = self._source_or_404(source_artifact_id)
        key = body['idempotency_key']
        if not IDEMPOTENCY_KEY.fullmatch(key):
            raise WebJobsError('invalid_idempotency_key', 400, 'idempotency_key must match [A-Za-z0-9._-]{8,128}')
        start, end = float(body['start_seconds']), float(body['end_seconds'])
        fingerprint = sha256_hex(canonical({'source_artifact_id': source_artifact_id, 'source_sha256': source['sha256'],
                                            **{k: v for k, v in body.items() if k != 'idempotency_key'},
                                            'start_seconds': start, 'end_seconds': end}).encode('ascii'))
        with self._db() as conn:
            existing = conn.execute('SELECT * FROM capture_reviews WHERE idempotency_key = ?', (key,)).fetchone()
        if existing is not None:
            if existing['fingerprint'] != fingerprint:
                raise WebJobsError('idempotency_conflict', 409, 'idempotency key already names a different review')
            return 200, self.review_projection(dict(existing), replayed=True)
        if not re.fullmatch(r'[0-9a-f]{64}', body['expected_source_sha256']) \
                or body['expected_source_sha256'] != source['sha256']:
            raise WebJobsError('source_stale', 409, 'expected_source_sha256 differs from the admitted source')
        source_path = self._require_current(source)
        for field, allowed in (('review_status', REVIEW_STATUSES), ('authorization_scope', AUTHORIZATION_SCOPES),
                               ('music_status', CONTENT_STATUSES), ('click_status', CONTENT_STATUSES),
                               ('ambient_music_status', AMBIENT_STATUSES)):
            if body[field] not in allowed:
                raise WebJobsError('invalid_review', 400, f'{field} is not a capture_profile enumeration value',
                                   field=field)
        note = body['note']
        if not note.strip() or len(note) > MAX_NOTE_CHARS or '\0' in note:
            raise WebJobsError('invalid_review', 400, f'note must be meaningful text up to {MAX_NOTE_CHARS} characters',
                               field='note')
        base = self._baseline(source, body['run_id'])
        samples = self._interval(start, end, base['header'])
        overlaps = self.overlaps_setup(start)
        if overlaps and not body['setup_interval_acknowledged']:
            raise WebJobsError('setup_interval_unacknowledged', 422, 'interval overlaps the first five seconds '
                               '(setup guitar/amp sounds, possible windup); acknowledge it explicitly')
        if overlaps and body['review_status'] not in SETUP_ALLOWED_STATUSES:
            raise WebJobsError('setup_interval_status_refused', 422, 'an interval overlapping the first five seconds '
                               'may only be reviewed_possible_contamination or rejected_contaminated')
        review_id = 'rev_' + secrets.token_hex(16)
        record = {'schema_version': 1, 'source_sha256': source['sha256'],
                  'source_run_manifest_sha256': base['manifest_sha256'], 'source_pcm_sha256': base['pcm_sha256'],
                  'start_seconds': start, 'end_seconds': end, 'time_axis': 'decoded_source_audio_samples',
                  'selected_by': WEB_REVIEWER, 'reviewed_by': WEB_REVIEWER,
                  'review_status': body['review_status'], 'authorization_scope': body['authorization_scope'],
                  'authorization_reference': f'video-utils web capture review {review_id}',
                  'music_status': body['music_status'], 'click_status': body['click_status'],
                  'ambient_music_status': body['ambient_music_status'], 'note': note}
        data = (json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')
        if len(data) > MAX_REVIEW_BYTES:
            raise WebJobsError('invalid_review', 400, f'review record exceeds {MAX_REVIEW_BYTES} bytes')
        directory = base['run_dir'] / REVIEW_DIR
        try:
            os.mkdir(directory, 0o700)
        except FileExistsError:
            pass
        if not self._confined_dir(directory):
            raise WebJobsError('run_not_baseline', 422, 'review directory is not a real directory')
        path = directory / f'{review_id}.json'
        _write_new_file(path, data)
        _fsync_directory(directory)
        # Binding is re-read after the write: every recorded hash names the bytes on disk now.
        self.check_review_current({'run_id': body['run_id'], 'source_sha256': source['sha256'],
                                   'manifest_sha256': base['manifest_sha256'], 'pcm_sha256': base['pcm_sha256'],
                                   'rel_path': f'{body["run_id"]}/{REVIEW_DIR}/{review_id}.json',
                                   'review_sha256': sha256_hex(data)}, source_path)
        row = {'review_id': review_id, 'idempotency_key': key, 'fingerprint': fingerprint,
               'source_artifact_id': source_artifact_id, 'source_sha256': source['sha256'], 'run_id': body['run_id'],
               'manifest_sha256': base['manifest_sha256'], 'pcm_sha256': base['pcm_sha256'],
               'review_sha256': sha256_hex(data), 'start_seconds': start, 'end_seconds': end,
               'start_sample': samples[0], 'end_sample': samples[1], 'sample_rate': base['header']['sample_rate'],
               'review_status': body['review_status'], 'authorization_scope': body['authorization_scope'],
               'music_status': body['music_status'], 'click_status': body['click_status'],
               'ambient_music_status': body['ambient_music_status'], 'overlaps_setup_interval': int(overlaps),
               'setup_interval_acknowledged': int(body['setup_interval_acknowledged']), 'note': note,
               'rel_path': f'{body["run_id"]}/{REVIEW_DIR}/{review_id}.json', 'created_at': utc_now()}
        try:
            with self._tx() as conn:
                conn.execute(f'INSERT INTO capture_reviews({", ".join(row)}) VALUES ({", ".join("?" for _ in row)})',
                             tuple(row.values()))
        except sqlite3.IntegrityError:
            with self._db() as conn:
                existing = conn.execute('SELECT * FROM capture_reviews WHERE idempotency_key = ?', (key,)).fetchone()
            if existing is None:
                raise
            # A concurrent identical request won; this file is unreferenced and removed (it is ours).
            with contextlib.suppress(OSError):
                os.unlink(path)
            if existing['fingerprint'] != fingerprint:
                raise WebJobsError('idempotency_conflict', 409, 'idempotency key already names a different review') \
                    from None
            return 200, self.review_projection(dict(existing), replayed=True)
        return 201, self.review_projection(row, replayed=False)

    def open_run_media(self, run_id, role):
        """Re-hashed WAV of a run bound to an admitted source, for span audition (inline)."""
        if role not in RUN_MEDIA_ROLES:
            raise WebJobsError('unknown_role', 404, 'media role must be source, denoised, cleaned, processed or residue')
        run_dir, manifest, _ = self._run_manifest(run_id)
        claimed = manifest.get('source') if isinstance(manifest.get('source'), dict) else {}
        with self._db() as conn:
            bound = conn.execute('SELECT source_artifact_id FROM sources WHERE sha256 = ? LIMIT 1',
                                 (claimed.get('sha256'),)).fetchone() if isinstance(claimed.get('sha256'), str) else None
        if bound is None:
            raise WebJobsError('run_not_bound', 409, 'run is not bound to an admitted source')
        name = RUN_MEDIA_ROLES[role]
        outputs = manifest.get('outputs') if isinstance(manifest.get('outputs'), dict) else {}
        hashes = manifest.get('output_sha256') if isinstance(manifest.get('output_sha256'), dict) else {}
        if outputs.get(role) != name or not isinstance(hashes.get(name), str):
            raise WebJobsError('unknown_role', 404, 'run has no such media role')
        try:
            descriptor, before = _open_regular_nofollow(run_dir / name)
        except FileNotFoundError:
            raise WebJobsError('artifact_missing', 410, 'run media is missing') from None
        except OSError:
            raise WebJobsError('confinement_refused', 403, 'run media is not a regular file') from None
        try:
            digest, size = hash_descriptor(descriptor, MAX_PCM_BYTES)
            after = os.fstat(descriptor)
        except BaseException:
            os.close(descriptor)
            raise
        if file_signature(before) != file_signature(after) or digest != hashes[name]:
            os.close(descriptor)
            raise WebJobsError('artifact_stale', 409, 'run media bytes differ from the manifest hash')
        artifact_id = artifact_ids.artifact_id_for(f'{run_id}/{name}', digest)
        return ServedArtifact(artifact_id, descriptor, size, digest, 'audio/wav', file_signature(after))

    def job_types(self):
        """Closed job-type catalogue with knob specs copied from the live descriptors."""
        catalogue = []
        groups = {'reduction_db': 'cleanup', 'noise_floor_db': 'cleanup', 'adaptivity': 'cleanup',
                  'gain_smooth': 'cleanup', 'peaking_eq': 'tone', 'compressor': 'dynamics',
                  'integrated_lufs': 'delivery_loudness', 'true_peak_dbtp': 'delivery_loudness',
                  'timeout_seconds': 'supervision', 'profile': 'preset', 'height': 'delivery', 'crf': 'delivery',
                  'audio_kbps': 'delivery', 'codec': 'delivery'}
        spec_keys = ('type', 'minimum', 'maximum', 'enum', 'default', 'description', 'items', 'properties',
                     'required', 'minItems', 'maxItems')
        for name, spec in JOB_TYPES.items():
            properties = self.descriptors[name]['inputSchema']['properties']
            knobs = {}
            for key in spec.parameter_keys:
                if key == 'preset':
                    knobs[key] = {'type': 'string', 'enum': list(CAPTURE_PRESETS), 'web_only': True,
                                  'group': 'preset', 'description': 'fuller expands profiles/fuller.json verbatim; '
                                                                    'custom requires every control explicitly'}
                    continue
                knob = {field: properties[key][field] for field in spec_keys if field in properties[key]}
                knob['group'] = groups.get(key, 'other')
                knob['required_by_tool'] = key in self.descriptors[name]['inputSchema'].get('required', [])
                knobs[key] = json.loads(canonical(knob))
            timeout = properties['timeout_seconds']
            admission, raw = self.admission_state(name)
            entry = {'tool': name, 'admission_state': admission, 'capability_state': raw,
                     'resource_class': spec.resource_class, 'bound_field': spec.bound_field,
                     'knobs': knobs, 'web_only_constraints': list(spec.web_only_constraints),
                     'timeout_seconds': {'minimum': timeout['minimum'], 'maximum': timeout['maximum'],
                                         'default': timeout['default']},
                     'outer_headroom_seconds': OUTER_HEADROOM_S,
                     'implementation_status': self.descriptors[name]['implementation_status'],
                     'evidence_kind': self.descriptors[name]['evidence_kind'],
                     'capability_revision': self.capability_revisions[name]}
            if name == 'denoise':
                entry['profiles'] = [{'name': profile, 'source_bound_sha256': profile_source_binding(profile)}
                                     for profile in properties['profile']['enum']]
            if name == 'capture_profile':
                entry['presets'] = {'fuller': {'controls': self.fuller_controls, 'source': 'profiles/fuller.json',
                                               'default_selection': True,
                                               'listening_acceptance_scope': PROCESSING_UNKNOWN_REASONS[
                                                   'fuller_listening_transfer']},
                                    'custom': {'controls': None, 'default_selection': False}}
                entry['low_shelf'] = {'available': False,
                                      'reason': 'no typed tool exposes the shelf (capture_profile schema has no '
                                                'low_shelf control and denoise profiles have no shelf profile)'}
            catalogue.append(entry)
        return 200, {'schema_version': 1, 'job_types': catalogue, 'allowlist': list(JOB_TYPE_NAMES),
                     'claim_class': 'contract_catalogue'}

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
