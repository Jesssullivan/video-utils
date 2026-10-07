#!/usr/bin/env python3
"""S3 routes_review read API over existing run evidence (stdlib only; read-only).

Routes (contract ``docs/spec/sprints/ROUTES_REVIEW_S3.md`` section 4), mounted into
``scripts/web_api.py`` by a root-applied registration hunk after the loopback, Host,
Origin and bearer checks::

    GET /api/v1/runs                                              run listing (?limit=1..500)
    GET /api/v1/runs/{run_id}                                     run graph: stages, signal versions, evidence
    GET /api/v1/runs/{run_id}/layers                              bound review layers (?evidence=evd_...)
    GET /api/v1/runs/{run_id}/layers/media/{evidence_id}/{name}   re-hashed layer media
    GET /api/v1/runs/{run_id}/artifacts/{artifact_id}             re-hashed run or attachment file
    GET /api/v1/capabilities                                      tools, capability metadata, model registry

Everything here is a view over evidence other tools produced. Nothing is rendered,
decoded, fitted, re-analysed, adopted or written; no subprocess is started. Reads are
confined to ``<root>/artifacts`` (``artifacts/runs`` for runs; ``artifacts/{s2,s3,experiments}``
for evidence attachments) plus the pinned listening-acceptance receipts and the
``program/*.json`` registries of this checkout. No response carries a host path, a
selector, a command string, the token or the state root.
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
import datetime
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import threading
from urllib.parse import parse_qsl, urlsplit

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import artifact_ids  # noqa: E402  (import only, never edited)
import web_jobs  # noqa: E402  (import only, never edited)
from web_jobs import WebJobsError  # noqa: E402

REPO = SCRIPTS.parent
SCHEMA_VERSION = 1
SCHEMA_IDS = {
    'list': 'video-utils.web-runs.list',
    'run': 'video-utils.web-runs.run',
    'layers': 'video-utils.web-runs.layers',
    'capabilities': 'video-utils.web-runs.capabilities',
}
MiB = 1024 * 1024
MAX_RESPONSE_BYTES = 4 * MiB
MAX_MANIFEST_BYTES = 20 * MiB
MAX_EVIDENCE_BYTES = 20 * MiB
MAX_RECEIPT_BYTES = 1 * MiB
MAX_REGISTRY_BYTES = 4 * MiB
MAX_STAGE_BYTES = artifact_ids.DEFAULT_MAX_BYTES
STREAM_CHUNK = MiB
EVIDENCE_ROOTS = ('s2', 's3', 'experiments')
MAX_DEPTH = 5
MAX_ENTRIES = 20_000
RUN_LIST_DEFAULT, RUN_LIST_MAX = 100, 500
MAX_TEXT = 2000

EVIDENCE_DOMAIN = b'video-utils/run-evidence/v1\0'
EVIDENCE_ID = re.compile(r'evd_[0-9a-f]{32}')
ARTIFACT_ID = artifact_ids.ARTIFACT_ID
SHA256 = artifact_ids.SHA256
MEDIA_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,95}')
LIMIT = re.compile(r'[1-9][0-9]{0,3}')
ISO_PREFIX = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}')

# Pinned listening-acceptance receipts: (repo-relative path, sha256). The only read outside
# artifacts/; resolved against this checkout, never against a caller-supplied path.
ACCEPTANCE_PINS = (
    ('docs/agent-notes/2026-10-06-fuller-listening-acceptance.json',
     '0f8d3dbff43e8f8c2bdaed94856d697b94f3de9cf78cf5f72a0e6ee982578e92'),
)

ROLE_BASIS = 'routes_review filename map; not a manifest field'
STAGE_ROLES = {
    'source.wav': 'Decoded native source PCM',
    'denoised.wav': 'Pure denoise (afftdn)',
    'processed.wav': 'Tone and dynamics',
    'cleaned.wav': 'Delivery master',
    'baseline.wav': 'Normalization-only baseline',
    'residue.wav': 'Removed-signal estimate',
}
EXPORT_ROLE = 'Restored video export (hash-identified; bound only when export/outcome.json records it)'
GRAPH_EDGES = (
    ('source.wav', 'denoised.wav'),
    ('denoised.wav', 'processed.wav'),
    ('processed.wav', 'cleaned.wav'),
    ('source.wav', 'baseline.wav'),
    ('source.wav', 'residue.wav'),
    ('denoised.wav', 'residue.wav'),
)
SPECTROGRAM_STAGE_PREFERENCE = ('cleaned.wav', 'processed.wav', 'denoised.wav', 'source.wav', 'baseline.wav')
CONTENT_TYPES = {
    '.wav': 'audio/wav', '.mov': 'video/quicktime', '.mp4': 'video/mp4', '.m4v': 'video/x-m4v',
    '.mkv': 'video/x-matroska', '.webm': 'video/webm', '.json': 'application/json',
    '.fcpxml': 'application/xml', '.f64le': 'application/octet-stream',
}
VIDEO_SUFFIXES = artifact_ids.VIDEO_SUFFIXES

PRACTICE_SCHEMA_ID = 'video-utils.practice-s2.bundle'
RENDER_SCHEMA = 'lowreg-render-v1'
SIDECAR_FORMAT = 'editor_marker_export_sidecar'
SIDECAR_NAME = 'editor-marker-export.sidecar.json'
MARKER_PAYLOADS = {'review.fcpxmld/Info.fcpxml': 'FCPXML marker preview (Final Cut Pro)',
                   'resolve-operations.json': 'Resolve marker operations preview (DaVinci Resolve)'}
MARKED_COMPACT_NAME = 'marked-compact.mov'
CANDIDATE_NAMES = ('bundle.json', 'render.json', SIDECAR_NAME, 'receipt.json')
INVALIDATION_REASONS = ('bound_manifest_changed', 'analyzed_input_not_current', 'file_hash_mismatch',
                        'source_mismatch')
TIMING_RUN_KINDS = ('real_take', 'synthetic_fixture')
DIRECTION_WITHHELD = 'withheld_uncalibrated'
DIRECTION_SYNTHETIC = 'synthetic_known_offset_fixture'
DIRECTION_CLASSES = ('within_5_ms', 'ahead_of_click', 'behind_click')
LAYER_NAMES = ('tone_ab', 'coverage', 'flags_triage', 'phrase_timing')

# Copied layer documents never carry these keys (host paths, command strings, input lists).
DROP_KEYS = frozenset({'path', 'run_dir', 'output_dir', 'authoring_dir', 'commands', 'command', 'argv',
                       'inputs', 'output', 'input_path', 'filter', 'audio_master', 'picture_preview'})
HOST_PATH = re.compile(r'^(/|~|[A-Za-z]:\\)|/Users/|/home/|/private/|/tmp/|/Volumes/|/nix/store/')
PATH_WITHHELD = '[host path withheld]'

CLAIM_BOUNDARY = {
    'musical_verdict': 'not_established',
    'missed_or_extra_notes': 'not_assessed_no_approved_reference',
    'default_adopted': False,
    'master_changed': False,
}
CLOCK = {
    'layer_axis': 'original source decoded-audio seconds',
    'annotation_axis': 'web clock manifest: share_export video packet presentation extent (source seconds)',
    'alignment': 'unverified',
    'reason': ('Layers use the decoded source audio clock; annotations use the web clock manifest. Their '
               'alignment, and the browser media clock, are not verified.'),
}
SPECTROGRAM_CLAIM = 'visualisation only; no pitch, note or stem claim'
BPM_NO_GRID = 'no fitted click grid in bound evidence'
BPM_GRID_ONLY = ('no BPM field in bound evidence; a recorded click period is shown as a navigation grid '
                 '(click identity unverified)')
AREA_BASIS = 'routes_review presentation map; not a registry field'
DOMAIN_BASIS = 'program/capabilities.json domain'
CAPABILITY_NULL_REASON = 'capability pilot covers 8 tools'
MODEL_GATE_REASON = 'not recorded in program/models.json'
MODEL_NOTE = ('S3 model lanes (Beat This, guitar_noul, stems) are tracked in TIN-5721 and appear here only once '
              'root registers them in program/models.json.')
TOOL_AREAS = {
    'probe': 'analysis', 'denoise': 'restoration', 'bpm': 'phrase_rhythm', 'noise': 'restoration',
    'tone': 'restoration', 'notes': 'pitch', 'rhythm': 'phrase_rhythm', 'phrases': 'phrase_rhythm',
    'export': 'delivery', 'report': 'pipeline_report', 'pipeline': 'pipeline_report', 'markers': 'review',
    'clicks': 'phrase_rhythm', 'phrase_compare': 'phrase_rhythm', 'benchmark': 'corpus_eval',
    'review': 'review', 'pitch': 'pitch', 'meter': 'phrase_rhythm', 'tonal': 'pitch', 'corpus': 'corpus_eval',
    'pitch_evaluate': 'pitch', 'phrase_evaluate': 'phrase_rhythm', 'marked_video': 'delivery',
    'basic_pitch_compare': 'pitch', 'capture_profile': 'restoration', 'editor_marker_plan': 'delivery',
    'learned_pitch_evaluate': 'pitch', 'apply_capture_profile': 'restoration',
    'arrangement_reference': 'phrase_rhythm', 'share_export': 'delivery', 'annotation_v2': 'review',
    'corpus_split': 'corpus_eval', 'editor_marker_export': 'delivery', 'annotation_markers': 'review',
    'flags_triage': 'review', 'corpus_eval_s2': 'corpus_eval', 'marked_compact': 'delivery',
    'phrase_timing': 'phrase_rhythm', 'tone_ab': 'review', 'report_bundle': 'pipeline_report',
    'beat_this_compare': 'phrase_rhythm', 'guitar_noul_decide': 'analysis',
    'take_intake': 'pipeline_report', 'timing_calibration_analyze': 'phrase_rhythm',
    'timing_calibration_apply': 'phrase_rhythm', 'stems_estimate': 'analysis',
}
AREAS = ('restoration', 'analysis', 'phrase_rhythm', 'pitch', 'review', 'delivery', 'corpus_eval',
         'pipeline_report')
MODEL_PASSTHROUGH = ('lane', 'gate', 'gate_state', 'status')

S2_UNKNOWN_KEYS = (
    'operator_preference', 'listening_acceptance', 'perceived_fullness', 'nasal_quality',
    'fundamental_32hz_presence', 'monitoring_device', 'true_peak_dbtp', 'fan_only_gain', 'music_only_gain',
    'click_identity', 'physical_capture_latency', 'detector_delay', 'meter', 'downbeat_confirmed',
    'anchor_adopted', 'breakdown1_execution', 'real_take_phrase_correctness', 'missed_or_extra_notes',
    'phrase_timing.real_take_status', 'browser_level_match', 'walkthrough_listening',
)
S3_UNKNOWN_KEYS = (
    'clock_alignment', 'bpm', 'annotation_source', 'editor_import', 'share_low_register_preservation',
    'model_local_presence', 'model_gate_state', 'tool_area_basis', 'physical_av_sync', 'spectrogram_binding',
    'room_response_recovered', 'stems',
)
# S2 defaults when no practice bundle is bound (mirrors review/practice_s2_bundle.py with no layers).
S2_DEFAULTS = {
    'operator_preference': (None, 'not recorded'),
    'listening_acceptance': ('not_established', 'No operator listening review exists for these renders.'),
    'perceived_fullness': (None, 'Perceived fullness is a listening judgement.'),
    'nasal_quality': (None, 'Nasal quality is a listening judgement.'),
    'fundamental_32hz_presence': (None, 'A band level is not a measured played C1 fundamental.'),
    'monitoring_device': (None, "The operator's playback device and level are unknown."),
    'true_peak_dbtp': (None, 'True peak was not measured; only sample peak is reported.'),
    'fan_only_gain': (None, 'Fan and music are not separated.'),
    'music_only_gain': (None, 'Fan and music are not separated.'),
    'click_identity': ('unverified', 'Periodic high-frequency transients are not a verified metronome.'),
    'physical_capture_latency': ('uncalibrated', 'Microphone and capture-chain latency were never measured.'),
    'detector_delay': ('uncalibrated', 'No detector delay calibration was supplied.'),
    'meter': ('unknown', 'Meter and downbeat are not identified by any layer.'),
    'downbeat_confirmed': (False, 'The anchor is a review candidate, not a confirmed downbeat.'),
    'anchor_adopted': (False, 'Arrangement anchors are review candidates; none is adopted.'),
    'breakdown1_execution': ('unknown_operator_reported_possible_rush_or_skip',
                             'Operator context copied verbatim; execution of breakdown 1 is unknown.'),
    'real_take_phrase_correctness': ('unknown_until_operator_marks_boundaries',
                                     'Phrase correctness needs operator-marked boundaries.'),
    'missed_or_extra_notes': ('not_assessed_no_approved_reference',
                              'No approved expected-rhythm or note reference exists.'),
    'phrase_timing.real_take_status': ('unvalidated_until_operator_spot_check',
                                       'Phrase timing offsets are unvalidated until an operator spot check.'),
    'browser_level_match': ('excerpt files pre-gained by tone_ab; browser output level and device unmeasured',
                            'The page applies no gain; playback level depends on the device.'),
    'walkthrough_listening': ('not_performed', 'Automated browser checks are muted; nobody listened.'),
}


# --------------------------------------------------------------------------- helpers

class _Missing(Exception):
    """Internal: no regular file at a confined location."""


class _Confined(Exception):
    """Internal: a symbolic link or non-directory component was met."""


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _num(value):
    return value if _finite(value) else None


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _sha(value):
    return value if isinstance(value, str) and SHA256.fullmatch(value) else None


def _text(value, limit=MAX_TEXT):
    if not isinstance(value, str):
        return None
    value = value[:limit]
    return PATH_WITHHELD if HOST_PATH.search(value) else value


def _bool(value):
    return value if isinstance(value, bool) else None


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def evidence_id_for(rel_to_artifacts, file_sha256):
    digest = hashlib.sha256(EVIDENCE_DOMAIN + rel_to_artifacts.encode('utf-8') + b'\0'
                            + file_sha256.encode('ascii')).hexdigest()
    return 'evd_' + digest[:32]


def attachment_artifact_id(evidence_id, name, content_sha256):
    """Opaque download ID of a file inside an evidence attachment (no selector is exposed)."""
    return artifact_ids.artifact_id_for(f'evidence/{evidence_id}/{name}', content_sha256)


def scrub(value, depth=0):
    """Copy a producer document without host paths, command strings or input lists."""
    if depth > 64:
        return None
    if isinstance(value, dict):
        return {str(key): scrub(item, depth + 1) for key, item in value.items() if key not in DROP_KEYS}
    if isinstance(value, list):
        return [scrub(item, depth + 1) for item in value]
    if isinstance(value, str):
        return PATH_WITHHELD if HOST_PATH.search(value) else value
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def strict_json(data, where):
    return artifact_ids._strict_json(data, where)


def encode(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True,
                      separators=(',', ':')).encode('ascii')


def content_type_for(name):
    return CONTENT_TYPES.get(Path(name).suffix.lower(), 'application/octet-stream')


def _parse_time(text):
    if not isinstance(text, str) or not ISO_PREFIX.match(text):
        return None
    try:
        parsed = datetime.datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.timestamp()


def check_timing_directions(document):
    """phrase_timing schema-2 direction policy (mirrors review/practice_s2_bundle.py). Returns a code or None."""
    expected = DIRECTION_SYNTHETIC if document.get('run_kind') == 'synthetic_fixture' else DIRECTION_WITHHELD
    for row in _list(document.get('phrases')):
        if not isinstance(row, dict) or 'tendency_label' in row or 'tendency_basis' in row:
            return 'layer_schema_unknown'
        status, direction = row.get('direction_status'), row.get('direction')
        if row.get('status') == 'measured':
            if status != expected:
                return 'layer_direction_policy_violation'
            if status == DIRECTION_SYNTHETIC and direction not in DIRECTION_CLASSES:
                return 'layer_direction_policy_violation'
            if status == DIRECTION_WITHHELD and direction is not None:
                return 'layer_direction_policy_violation'
        elif status is not None or direction is not None:
            return 'layer_direction_policy_violation'
    return None


@dataclass
class Attachment:
    evidence_id: str
    kind: str
    rel: str                      # private: path relative to artifacts/ (never returned)
    directory: Path               # private
    file_sha256: str
    document: dict | None
    state: str
    reason: str | None
    bound_signal_version: str | None
    generated_utc: str | None
    media: dict = field(default_factory=dict)   # name -> {rel_parts, sha256, ...}
    files: list = field(default_factory=list)   # deliverables: public dicts + private parts
    now: str | None = None

    def public(self):
        return {'evidence_id': self.evidence_id, 'kind': self.kind, 'state': self.state, 'reason': self.reason,
                'bound_signal_version': self.bound_signal_version, 'generated_utc': self.generated_utc,
                'files': [{key: item[key] for key in ('name', 'role', 'artifact_id', 'sha256', 'size_bytes',
                                                      'import_verified')} for item in self.files]}


@dataclass
class RunContext:
    run_id: str
    run_dir: Path
    manifest: dict
    manifest_sha256: str
    source_sha256: str | None
    stages: list                  # public stage dicts (with private '_parts')
    outputs: dict                 # filename -> recorded sha256
    states: dict                  # filename -> state
    observed: dict                # filename -> observed sha256 or None


# --------------------------------------------------------------------------- the API

class RunsAPI:
    """Read-only projections over ``<root>/artifacts``. Signature-cached; no background work."""

    def __init__(self, root=None, *, acceptance_pins=ACCEPTANCE_PINS, docs_root=None, program_root=None,
                 max_stage_bytes=MAX_STAGE_BYTES):
        base = Path(root if root is not None else web_jobs.ROOT)
        try:
            self.root = base.resolve(strict=True)
        except OSError:
            raise WebJobsError('runs_root_invalid', 500, 'runs root is not available') from None
        self.artifacts = self.root / 'artifacts'
        self.runs = self.artifacts / 'runs'
        self.docs_root = Path(docs_root if docs_root is not None else REPO)
        self.program_root = Path(program_root if program_root is not None else REPO / 'program')
        self.acceptance_pins = tuple(acceptance_pins)
        self.max_stage_bytes = max_stage_bytes
        self.before_send = None  # test seam: called after verification, before streaming bytes
        self._lock = threading.Lock()
        self._hash_cache = {}
        self._doc_cache = {}

    # ----------------------------------------------------------------- confinement

    def _check_tree(self):
        for directory in (self.artifacts, self.runs):
            try:
                info = os.lstat(directory)
            except OSError:
                raise WebJobsError('unknown_run', 404, 'no runs directory exists') from None
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise WebJobsError('confinement_refused', 403, 'artifacts/runs is not a confined directory')

    def _walk(self, base, parts):
        """lstat every component below ``base``; returns the leaf path. Raises _Missing/_Confined."""
        cursor = base
        for index, part in enumerate(parts):
            if part in ('', '.', '..') or '/' in part or '\0' in part:
                raise _Confined()
            cursor = cursor / part
            try:
                info = os.lstat(cursor)
            except FileNotFoundError:
                raise _Missing() from None
            except OSError:
                raise _Missing() from None
            if stat.S_ISLNK(info.st_mode):
                raise _Confined()
            if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
                raise _Missing()
        return cursor

    def _open(self, base, parts):
        """Open a confined regular file without following links: (fd, fstat)."""
        path = self._walk(base, parts)
        try:
            return web_jobs._open_regular_nofollow(path)
        except FileNotFoundError:
            raise _Missing() from None
        except OSError as error:
            if error.errno == errno.ELOOP:
                raise _Confined() from None
            raise _Missing() from None

    def _read_bytes(self, base, parts, limit):
        descriptor, info = self._open(base, parts)
        try:
            if info.st_size > limit:
                raise ValueError('file exceeds its bound')
            chunks, total = [], 0
            while True:
                chunk = os.read(descriptor, MiB)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise ValueError('file exceeds its bound')
                chunks.append(chunk)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if _signature(info)[:4] != _signature(after)[:4]:
            raise ValueError('file changed while reading')
        return b''.join(chunks), after

    def _hash(self, base, parts, limit):
        """(sha256, size) of a confined regular file, cached by identity signature."""
        descriptor, info = self._open(base, parts)
        try:
            key = (str(base), tuple(parts), _signature(info))
            with self._lock:
                cached = self._hash_cache.get(key)
            if cached is not None:
                return cached
            if info.st_size > limit:
                raise ValueError('file exceeds its bound')
            digest, size = web_jobs.hash_descriptor(descriptor, limit)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if _signature(info) != _signature(after) or size != after.st_size:
            raise ValueError('file changed while hashing')
        with self._lock:
            if len(self._hash_cache) > 4096:
                self._hash_cache.clear()
            self._hash_cache[key] = (digest, size)
        return digest, size

    # ----------------------------------------------------------------- manifests

    def _run_dir(self, run_id):
        try:
            artifact_ids.check_run_id(run_id)
        except artifact_ids.ArtifactIdError:
            raise WebJobsError('malformed_id', 400, 'run id must be one safe path component') from None
        self._check_tree()
        run_dir = self.runs / run_id
        try:
            info = os.lstat(run_dir)
        except OSError:
            raise WebJobsError('unknown_run', 404, 'run id is not known') from None
        if stat.S_ISLNK(info.st_mode):
            raise WebJobsError('confinement_refused', 403, 'run directory is not confined')
        if not stat.S_ISDIR(info.st_mode):
            raise WebJobsError('unknown_run', 404, 'run id is not known')
        return run_dir

    def _manifest(self, run_id):
        run_dir = self._run_dir(run_id)
        try:
            data, _ = self._read_bytes(self.runs, [run_id, 'manifest.json'], MAX_MANIFEST_BYTES)
        except _Missing:
            raise WebJobsError('unknown_run', 404, 'run has no regular manifest.json') from None
        except _Confined:
            raise WebJobsError('confinement_refused', 403, 'run manifest is not confined') from None
        except (OSError, ValueError):
            raise WebJobsError('manifest_unreadable', 422, 'run manifest is unreadable or too large') from None
        try:
            manifest = strict_json(data, 'manifest')
        except ValueError:
            raise WebJobsError('manifest_unreadable', 422, 'run manifest is not strict finite JSON') from None
        if not isinstance(manifest, dict):
            raise WebJobsError('manifest_unreadable', 422, 'run manifest is not a JSON object')
        return run_dir, manifest, hashlib.sha256(data).hexdigest()

    def _stage_node(self, run_id, name, recorded):
        node = {'stage': name, 'file_role': STAGE_ROLES.get(name, 'unknown'), 'role_basis': ROLE_BASIS,
                'artifact_id': None, 'signal_version': f'sha256:{recorded}' if recorded else None,
                'state': 'missing', 'size_bytes': None}
        observed = None
        safe = isinstance(name, str) and artifact_ids.COMPONENT.fullmatch(name) and '.partial' not in name
        if safe:
            try:
                observed, size = self._hash(self.runs, [run_id, name], self.max_stage_bytes)
                node['size_bytes'] = size
                node['state'] = 'unbound' if recorded is None else ('current' if observed == recorded else 'stale')
            except _Confined:
                raise WebJobsError('confinement_refused', 403, 'a run stage file is not confined') from None
            except (_Missing, OSError, ValueError):
                node['state'] = 'missing'
            identity = recorded or observed
            if identity:
                node['artifact_id'] = artifact_ids.artifact_id_for(f'{run_id}/{name}', identity)
        node['_parts'] = [run_id, name] if safe else None
        node['_bound'] = recorded
        node['_observed'] = observed
        return node

    def _export_nodes(self, run_id):
        """export/* video files: hash-identified; bound when export/outcome.json records the same hash."""
        try:
            directory = self._walk(self.runs, [run_id, 'export'])
        except _Missing:
            return []
        except _Confined:
            raise WebJobsError('confinement_refused', 403, 'run export directory is not confined') from None
        if not stat.S_ISDIR(os.lstat(directory).st_mode):
            return []
        recorded = {}
        try:
            data, _ = self._read_bytes(self.runs, [run_id, 'export', 'outcome.json'], MAX_MANIFEST_BYTES)
            outcome = strict_json(data, 'outcome')
            recorded = {key: value for key, value in _dict(_dict(outcome).get('output_sha256')).items()
                        if _sha(value)}
        except (_Missing, _Confined, OSError, ValueError):
            recorded = {}
        nodes = []
        try:
            names = sorted(entry.name for entry in os.scandir(directory))
        except OSError:
            return []
        for name in names:
            if not name.lower().endswith(VIDEO_SUFFIXES) or name.startswith('.'):
                continue
            stage = f'export/{name}'
            node = {'stage': stage, 'file_role': EXPORT_ROLE, 'role_basis': ROLE_BASIS, 'artifact_id': None,
                    'signal_version': None, 'state': 'missing', 'size_bytes': None, '_parts': None,
                    '_bound': None, '_observed': None}
            try:
                artifact_ids.check_selector(f'{run_id}/export/{name}')
                observed, size = self._hash(self.runs, [run_id, 'export', name], self.max_stage_bytes)
            except _Confined:
                raise WebJobsError('confinement_refused', 403, 'a run export file is not confined') from None
            except (artifact_ids.ArtifactIdError, _Missing, OSError, ValueError):
                continue
            bound = recorded.get(name)
            node.update(artifact_id=artifact_ids.artifact_id_for(f'{run_id}/export/{name}', observed),
                        signal_version=f'sha256:{observed}', size_bytes=size,
                        state='unbound' if bound is None else ('current' if bound == observed else 'stale'),
                        _parts=[run_id, 'export', name], _bound=bound or observed, _observed=observed)
            nodes.append(node)
        return nodes

    def _context(self, run_id):
        run_dir, manifest, manifest_sha = self._manifest(run_id)
        source = _dict(manifest.get('source'))
        outputs = _dict(manifest.get('outputs'))
        hashes = _dict(manifest.get('output_sha256'))
        stages, seen = [], set()
        for name in outputs.values():
            if not isinstance(name, str) or name in seen:
                continue
            seen.add(name)
            stages.append(self._stage_node(run_id, name, _sha(hashes.get(name))))
        order = list(STAGE_ROLES)
        stages.sort(key=lambda node: (order.index(node['stage']) if node['stage'] in order else len(order),
                                      node['stage']))
        stages.extend(self._export_nodes(run_id))
        recorded = {node['stage']: node['_bound'] for node in stages if not node['stage'].startswith('export/')
                    and node['_bound']}
        return RunContext(run_id=run_id, run_dir=run_dir, manifest=manifest, manifest_sha256=manifest_sha,
                          source_sha256=_sha(source.get('sha256')), stages=stages, outputs=recorded,
                          states={node['stage']: node['state'] for node in stages},
                          observed={node['stage']: node['_observed'] for node in stages})

    # ----------------------------------------------------------------- evidence discovery

    def _candidates(self):
        """Bounded, symlink-free walk of artifacts/{s2,s3,experiments}. Never enters artifacts/runs."""
        found, examined, truncated = [], 0, False
        try:
            info = os.lstat(self.artifacts)
        except OSError:
            return found, False
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            return found, False
        for top_name in EVIDENCE_ROOTS:
            top = self.artifacts / top_name
            try:
                top_info = os.lstat(top)
            except OSError:
                continue
            if stat.S_ISLNK(top_info.st_mode) or not stat.S_ISDIR(top_info.st_mode):
                continue
            stack = [(top, 0, top_name)]
            while stack and not truncated:
                directory, depth, rel = stack.pop()
                try:
                    with os.scandir(directory) as iterator:
                        entries = sorted(iterator, key=lambda entry: entry.name)
                except OSError:
                    continue
                for entry in entries:
                    examined += 1
                    if examined > MAX_ENTRIES:
                        truncated = True
                        break
                    if entry.name.startswith('.'):
                        continue
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if depth + 1 <= MAX_DEPTH:
                                stack.append((Path(entry.path), depth + 1, f'{rel}/{entry.name}'))
                        elif entry.name in CANDIDATE_NAMES and entry.is_file(follow_symlinks=False):
                            found.append((f'{rel}/{entry.name}', entry.stat(follow_symlinks=False)))
                    except OSError:
                        continue
            if truncated:
                break
        return found, truncated

    def _load_candidate(self, rel, info):
        """(sha256, document|None, refusal|None) for one candidate file, cached by signature."""
        key = (rel, _signature(info))
        with self._lock:
            cached = self._doc_cache.get(key)
        if cached is not None:
            return cached
        parts = rel.split('/')
        try:
            data, after = self._read_bytes(self.artifacts, parts, MAX_EVIDENCE_BYTES)
        except (_Missing, _Confined, OSError):
            return None
        except ValueError:
            result = (None, None, 'evidence_too_large')
        else:
            digest = hashlib.sha256(data).hexdigest()
            try:
                document = strict_json(data, 'evidence')
                result = (digest, document if isinstance(document, dict) else None,
                          None if isinstance(document, dict) else 'evidence_not_object')
            except ValueError:
                result = (digest, None, 'evidence_unparseable')
            key = (rel, _signature(after))
        with self._lock:
            if len(self._doc_cache) > 4096:
                self._doc_cache.clear()
            self._doc_cache[key] = result
        return result

    def _media_hash(self, parts):
        try:
            return self._hash(self.artifacts, parts, MAX_STAGE_BYTES)
        except (_Missing, _Confined, OSError, ValueError):
            return None, None

    def _attachments(self, ctx):
        candidates, truncated = self._candidates()
        attachments = []
        for rel, info in candidates:
            loaded = self._load_candidate(rel, info)
            if loaded is None:
                continue
            digest, document, refusal = loaded
            name = rel.rsplit('/', 1)[-1]
            directory_parts = rel.split('/')[:-1]
            if digest is None:
                continue
            evidence_id = evidence_id_for(rel, digest)
            base = dict(evidence_id=evidence_id, rel=rel, directory=self.artifacts.joinpath(*directory_parts),
                        file_sha256=digest, document=document)
            attachment = None
            if name == 'bundle.json':
                attachment = self._classify_bundle(ctx, base, document, refusal)
            elif name == 'render.json':
                attachment = self._classify_render(ctx, base, document, directory_parts)
            elif name == SIDECAR_NAME:
                attachment = self._classify_sidecar(ctx, base, document, refusal, directory_parts)
            elif name == 'receipt.json':
                attachment = self._classify_marked_compact(ctx, base, document, directory_parts)
            if attachment is not None:
                attachments.append(attachment)
        attachments.sort(key=lambda item: (item.kind, item.evidence_id))
        return attachments, truncated

    def _classify_bundle(self, ctx, base, document, refusal):
        if document is None:
            return None
        if document.get('schema_id') != PRACTICE_SCHEMA_ID:
            return None
        binding = _dict(document.get('session_binding'))
        if binding.get('run_id') != ctx.run_id:
            return None
        generated = _text(document.get('generated_utc'), 64)
        common = dict(base, kind='practice_bundle', generated_utc=generated,
                      bound_signal_version=(f'sha256:{binding["manifest_sha256"]}'
                                            if _sha(binding.get('manifest_sha256')) else None))
        if document.get('schema_version') != 1:
            return Attachment(**common, state='refused', reason='bundle_schema_version_unknown')
        if not isinstance(document.get('layers'), dict) or not isinstance(document.get('media', {}), dict):
            return Attachment(**common, state='refused', reason='bundle_schema_invalid')
        media = {}
        for media_name, record in _dict(document.get('media')).items():
            record = _dict(record)
            if isinstance(media_name, str) and MEDIA_NAME.fullmatch(media_name) \
                    and record.get('file') == f'media/{media_name}' and _sha(record.get('sha256')):
                media[media_name] = {'parts': base['rel'].split('/')[:-1] + ['media', media_name],
                                     'sha256': record['sha256'], 'frames': _int(record.get('frames')),
                                     'sample_rate': _int(record.get('sample_rate')),
                                     'channels': _int(record.get('channels')),
                                     'role': _text(record.get('role'), 200)}
        if binding.get('original_source_sha256') != ctx.source_sha256:
            state, reason, now = 'invalidated', 'source_mismatch', (f'sha256:{ctx.source_sha256}'
                                                                     if ctx.source_sha256 else None)
        elif binding.get('manifest_sha256') != ctx.manifest_sha256:
            state, reason, now = 'invalidated', 'bound_manifest_changed', f'sha256:{ctx.manifest_sha256}'
        else:
            state, reason, now = 'current', None, f'sha256:{ctx.manifest_sha256}'
        return Attachment(**common, state=state, reason=reason, media=media, now=now)

    def _stage_for_hash(self, ctx, sha):
        for stage, recorded in ctx.outputs.items():
            if recorded == sha:
                return stage
        return None

    def _classify_render(self, ctx, base, document, directory_parts):
        if document is None or document.get('schema') != RENDER_SCHEMA:
            return None
        resampler = document.get('resampler') if isinstance(document.get('resampler'), dict) else None
        parent = _sha(_dict(resampler).get('source_sha256'))
        input_sha = _sha(_dict(document.get('input')).get('sha256'))
        parent_stage = self._stage_for_hash(ctx, parent) if parent else None
        input_stage = self._stage_for_hash(ctx, input_sha) if input_sha else None
        if parent_stage is None and input_stage is None:
            return None
        common = dict(base, kind='lowreg_render', generated_utc=None)
        files, media = _dict(document.get('files')), {}
        shape = _dict(document.get('shape'))
        valid = _int(shape.get('frames')) and _int(shape.get('bands'))
        for matrix in ('log_power_db', 'pcen'):
            record = _dict(files.get(matrix))
            file_name = record.get('path')
            if not (isinstance(file_name, str) and MEDIA_NAME.fullmatch(file_name) and _sha(record.get('sha256'))):
                valid = False
                continue
            media[file_name] = {'parts': directory_parts + [file_name], 'sha256': record['sha256'],
                                'matrix': matrix, 'dtype': _text(record.get('dtype'), 64),
                                'layout': _text(record.get('layout'), 64), 'bytes': _int(record.get('bytes'))}
        if not valid:
            return Attachment(**common, state='refused', reason='render_schema_invalid',
                              bound_signal_version=None)
        if resampler is None or parent_stage is None:
            return Attachment(**common, state='unbound',
                              reason='no resampler record binds the analysed input to a run stage',
                              bound_signal_version=f'sha256:{input_sha}' if input_sha else None, media=media)
        if ctx.states.get(parent_stage) != 'current':
            observed = ctx.observed.get(parent_stage)
            return Attachment(**common, state='invalidated', reason='analyzed_input_not_current',
                              bound_signal_version=f'sha256:{parent}', media=media,
                              now=f'sha256:{observed}' if observed else None)
        attachment = Attachment(**common, state='current', reason=None, bound_signal_version=f'sha256:{parent}',
                                media=media, now=f'sha256:{parent}')
        attachment.parent_stage = parent_stage
        return attachment

    def _classify_sidecar(self, ctx, base, document, refusal, directory_parts):
        if document is None or document.get('format') != SIDECAR_FORMAT:
            return None
        source = _sha(document.get('source_sha256'))
        if source is None or source != ctx.source_sha256:
            return None
        common = dict(base, kind='editor_marker_export', generated_utc=None,
                      bound_signal_version=f'sha256:{source}')
        payload = _dict(document.get('payload_sha256'))
        entries = [(name, sha) for name, sha in payload.items() if name in MARKER_PAYLOADS and _sha(sha)]
        if not entries or len(entries) != len(payload):
            return Attachment(**common, state='refused', reason='sidecar_schema_invalid')
        files, mismatch = [], False
        for name, recorded in entries:
            parts = directory_parts + name.split('/')
            observed, size = self._media_hash(parts)
            if observed != recorded:
                mismatch = True
                continue
            files.append(self._file_entry(base['evidence_id'], name.rsplit('/', 1)[-1], MARKER_PAYLOADS[name],
                                          parts, recorded, size, import_verified=False))
        sidecar_parts = directory_parts + [SIDECAR_NAME]
        files.append(self._file_entry(base['evidence_id'], SIDECAR_NAME, 'Exact-time marker sidecar (JSON)',
                                      sidecar_parts, base['file_sha256'],
                                      self._media_hash(sidecar_parts)[1], import_verified=None))
        if mismatch:
            return Attachment(**common, state='invalidated', reason='file_hash_mismatch', now=None)
        return Attachment(**common, state='current', reason=None, files=files, now=f'sha256:{source}')

    def _classify_marked_compact(self, ctx, base, document, directory_parts):
        if document is None or document.get('tool') != 'marked_compact':
            return None
        branch = _dict(document.get('audio_branch'))
        cleaned = _sha(branch.get('cleaned_sha256'))
        if cleaned is None or cleaned != ctx.outputs.get('cleaned.wav'):
            return None
        generated = _text(document.get('created_utc'), 64)
        common = dict(base, kind='marked_compact', generated_utc=generated, bound_signal_version=f'sha256:{cleaned}')
        if document.get('status') != 'marked_compact_composition_verified' or not _sha(document.get('output_sha256')):
            return Attachment(**common, state='refused', reason='composition_not_verified')
        manifest = _sha(branch.get('manifest_sha256'))
        if manifest is not None and manifest != ctx.manifest_sha256:
            return Attachment(**common, state='invalidated', reason='bound_manifest_changed',
                              now=f'sha256:{ctx.manifest_sha256}')
        if ctx.states.get('cleaned.wav') != 'current':
            observed = ctx.observed.get('cleaned.wav')
            return Attachment(**common, state='invalidated', reason='analyzed_input_not_current',
                              now=f'sha256:{observed}' if observed else None)
        output = document.get('output')
        name = Path(output).name if isinstance(output, str) else MARKED_COMPACT_NAME
        if not MEDIA_NAME.fullmatch(name):
            name = MARKED_COMPACT_NAME
        parts = directory_parts + [name]
        observed, size = self._media_hash(parts)
        if observed != document['output_sha256']:
            return Attachment(**common, state='invalidated', reason='file_hash_mismatch', now=None)
        files = [self._file_entry(base['evidence_id'], name, 'Marked compact movie (overlay over the accepted audio)',
                                  parts, observed, size, import_verified=None)]
        return Attachment(**common, state='current', reason=None, files=files, now=f'sha256:{cleaned}')

    @staticmethod
    def _file_entry(evidence_id, name, role, parts, sha, size, *, import_verified):
        return {'name': name, 'role': role, 'artifact_id': attachment_artifact_id(evidence_id, name, sha),
                'sha256': sha, 'size_bytes': size, 'import_verified': import_verified, '_parts': parts}

    # ----------------------------------------------------------------- acceptance

    def _listening_acceptance(self, ctx):
        cleaned = ctx.outputs.get('cleaned.wav')
        not_established = {'value': 'not_established', 'scope': None, 'receipt_sha256': None,
                           'master_adopted': False, 'accepted_file_sha256': []}
        for relative, pin in self.acceptance_pins:
            parts = relative.split('/')
            try:
                data, _ = self._read_bytes(self.docs_root, parts, MAX_RECEIPT_BYTES)
            except (_Missing, _Confined, OSError, ValueError):
                continue
            if hashlib.sha256(data).hexdigest() != pin:
                continue
            try:
                receipt = strict_json(data, 'receipt')
            except ValueError:
                continue
            if not isinstance(receipt, dict) or receipt.get('run_id') != ctx.run_id:
                continue
            if receipt.get('manifest_sha256') != ctx.manifest_sha256 or receipt.get('cleaned_wav_sha256') != cleaned:
                continue
            if receipt.get('listening_accepted') is not True or ctx.states.get('cleaned.wav') != 'current':
                continue
            accepted = [value for value in (receipt.get('cleaned_wav_sha256'), receipt.get('export_video_sha256'))
                        if _sha(value)]
            return {'value': 'accepted', 'reason': ('pinned acceptance receipt re-hashes to its pin and names this '
                                                    'run, manifest and current cleaned.wav'),
                    'scope': _text(receipt.get('scope'), 600), 'receipt_sha256': pin, 'master_adopted': False,
                    'accepted_file_sha256': accepted}
        return {**not_established, 'reason': ('no pinned acceptance receipt re-hashes to its pin and names this run, '
                                              'manifest and current cleaned.wav')}

    # ----------------------------------------------------------------- source lookup

    def _admitted_sources(self, server, ctx):
        """Read-only lookup in the web_jobs sources table; None when unavailable."""
        read_only = getattr(server, 'read_only', None)
        if read_only is None:
            return None
        source_id = artifact_ids.source_id_for(ctx.source_sha256) if ctx.source_sha256 else None
        prefix = f'{ctx.run_id}/'
        try:
            with read_only() as conn:
                rows = conn.execute(
                    'SELECT source_artifact_id, kind, sha256 FROM sources WHERE (source_id IS NOT NULL AND source_id = ?) '
                    'OR substr(selector, 1, ?) = ? ORDER BY admitted_at DESC, rowid DESC LIMIT 64',
                    (source_id, len(prefix), prefix)).fetchall()
                result = []
                for row in rows:
                    extent = self._newest_extent(server, conn, row['source_artifact_id'], row['sha256'])
                    result.append({'source_artifact_id': row['source_artifact_id'], 'kind': row['kind'],
                                   'has_annotation_clock': extent is not None})
                return result
        except (sqlite3.Error, WebJobsError, OSError, KeyError, IndexError):
            return None

    @staticmethod
    def _newest_extent(server, conn, source_artifact_id, sha256):
        method = getattr(server, 'newest_extent', None)
        if callable(method):
            return method(conn, source_artifact_id, sha256)
        rows = conn.execute(
            "SELECT a.result_json FROM attempts a JOIN jobs j ON j.job_id = a.job_id "
            "WHERE j.source_artifact_id = ? AND a.state = 'succeeded' ORDER BY a.ended_at DESC LIMIT 16",
            (source_artifact_id,)).fetchall()
        for row in rows:
            try:
                checks = json.loads(row['result_json']) if row['result_json'] else None
            except ValueError:
                continue
            proof = _dict(_dict(checks).get('video_proof'))
            start, end = proof.get('source_start_seconds'), proof.get('source_end_seconds')
            if _dict(checks).get('source_sha256') == sha256 and _finite(start) and _finite(end) and end > start:
                return start, end
        return None

    # ----------------------------------------------------------------- projections

    def _processing(self, manifest):
        profile = _dict(manifest.get('profile'))
        latency = _dict(manifest.get('dsp_latency'))
        denoise = _dict(latency.get('denoise'))
        frequency = _dict(manifest.get('frequency_preservation'))
        loudness = _dict(manifest.get('loudness'))
        targets = {}
        for stage, block in sorted(loudness.items()):
            block = _dict(block)
            values = {key: _num(value) for key, value in block.items() if isinstance(key, str)
                      and key.startswith('target_')}
            if values:
                targets[str(stage)[:64]] = values
        peaking = [{key: _num(_dict(item).get(key)) for key in ('frequency_hz', 'gain_db', 'q')}
                   for item in _list(profile.get('peaking_eq'))][:16]
        compressor = profile.get('compressor')
        compressor = ({key: _num(value) for key, value in compressor.items() if isinstance(key, str)}
                      if isinstance(compressor, dict) else None)
        noise = _dict(manifest.get('noise_capture'))
        selected = noise.get('selected_seconds', noise.get('actual_selected_seconds'))
        selected = [_num(value) for value in selected][:2] if isinstance(selected, list) else None
        application = _dict(manifest.get('capture_profile_application'))
        return {
            'profile_name': _text(profile.get('name'), 200),
            'denoise': {'filter': _text(denoise.get('filter'), 64), 'delay_samples': _int(denoise.get('delay_samples')),
                        'status': _text(denoise.get('status'), 120)},
            'tone': {'peaking_eq': peaking, 'compressor': compressor},
            'loudness_targets': targets,
            'high_pass_applied': _bool(frequency.get('high_pass_applied')),
            'hum_notches_applied': _bool(frequency.get('hum_notches_applied')),
            'intentional_low_fundamental_hz': _num(frequency.get('intentional_low_fundamental_hz')),
            'noise_capture': {'selected_seconds': selected, 'review': _text(noise.get('review'), MAX_TEXT)},
            'dsp_latency_status': {str(key)[:64]: _text(_dict(value).get('status'), 120)
                                   for key, value in sorted(latency.items()) if isinstance(value, dict)},
            'manifest_listening_accepted_field': _bool(application.get('listening_accepted')),
        }

    def _unknown_fields(self, bundle, *, acceptance, bpm, physical_sync, spectrogram_binding, annotation_source):
        recorded = _dict(bundle.document.get('unknown_fields')) if bundle is not None else {}
        result = {}
        for key in S2_UNKNOWN_KEYS:
            entry = recorded.get(key)
            if isinstance(entry, dict) and 'value' in entry and isinstance(entry.get('reason'), str):
                item = {'value': scrub(entry['value']), 'reason': _text(entry['reason'], MAX_TEXT)}
                if isinstance(entry.get('basis'), str):
                    item['basis'] = _text(entry['basis'], 300)
                result[key] = item
            else:
                value, reason = S2_DEFAULTS[key]
                result[key] = {'value': value, 'reason': reason,
                               'basis': 'S2 default (no practice bundle value bound)'}
        if acceptance['value'] == 'accepted':
            result['listening_acceptance'] = {
                'value': 'accepted_exact_files_only', 'reason': acceptance['scope'] or acceptance['reason'],
                'basis': 'pinned acceptance receipt; applies only to the files it names'}
        result['clock_alignment'] = {'value': 'unverified', 'reason': (
            'Layer axis is decoded source audio. Annotation axis is the web clock manifest (share_export packet '
            'extent).')}
        result['bpm'] = {'value': bpm['value'], 'reason': bpm['reason']}
        result['annotation_source'] = (
            {'value': annotation_source, 'reason': 'most recent admitted source of this run with a share_export clock'}
            if annotation_source else
            {'value': None, 'reason': 'no admitted source of this run has a share_export annotation clock'})
        result['editor_import'] = {'value': 'unverified', 'reason': 'No editor application import proof exists.'}
        result['share_low_register_preservation'] = {'value': 'not_claimed', 'reason': (
            'Lossy AAC sharing derivative; ~32 Hz content is not measured in it.')}
        result['model_local_presence'] = {'value': 'not_checked', 'reason': 'This read API never inspects model caches.'}
        result['model_gate_state'] = {'value': None, 'reason': MODEL_GATE_REASON}
        result['tool_area_basis'] = {'value': AREA_BASIS, 'reason': (
            'Tool areas come from program/capabilities.json domains where present, else this presentation map.')}
        result['physical_av_sync'] = {'value': physical_sync, 'reason': (
            'Copied from manifest dsp_latency.physical_audio_video_sync_verified.' if physical_sync is not None
            else 'The run manifest does not record physical audio/video sync verification.')}
        result['spectrogram_binding'] = spectrogram_binding
        result['room_response_recovered'] = {'value': False, 'reason': (
            'No room or microphone response is measured or inverted; EQ does not recreate the in-room amp tone.')}
        result['stems'] = {'value': 'not_available', 'reason': (
            'No stem lane is admitted, and an estimate would never be an original stem.')}
        return result

    def _select_bundle(self, attachments, requested):
        bundles = [item for item in attachments if item.kind == 'practice_bundle']
        current = [item for item in bundles if item.state == 'current']
        current.sort(key=lambda item: (-(_parse_time(item.generated_utc) or float('-inf')), item.evidence_id))
        selected = current[0] if current else None
        if requested is not None:
            match = next((item for item in attachments if item.evidence_id == requested), None)
            if match is None or match.kind != 'practice_bundle':
                raise WebJobsError('unknown_evidence', 404, 'evidence id is not a practice bundle of this run')
            if match.state != 'current':
                raise WebJobsError('evidence_invalidated', 409, 'the selected evidence is no longer current')
            selected = match
        alternatives = [item.evidence_id for item in current if selected is None or item.evidence_id != selected.evidence_id]
        return selected, sorted(alternatives)

    def _bpm(self, bundle):
        layers = _dict(bundle.document.get('layers')) if bundle is not None else {}
        triage = _dict(layers.get('flags_triage'))
        document = _dict(triage.get('document')) if triage.get('status') == 'available' else {}
        basis = _dict(document.get('window_basis'))
        timing_files = _list(_dict(layers.get('phrase_timing')).get('files'))
        explicit, explicit_basis = None, None
        for doc in [_dict(_dict(item).get('document')) for item in timing_files]:
            reference = _dict(doc.get('click_reference'))
            for key in ('bpm', 'tempo_bpm'):
                if _finite(reference.get(key)) and reference[key] > 0:
                    explicit, explicit_basis = reference[key], f'phrase_timing click_reference.{key} (copied)'
                    break
            if explicit is not None:
                break
        if explicit is None:
            for key in ('bpm', 'tempo_bpm'):
                if _finite(basis.get(key)) and basis[key] > 0:
                    explicit, explicit_basis = basis[key], f'flags_triage window_basis.{key} (copied)'
                    break
        period, phase = basis.get('period_seconds'), basis.get('phase_seconds_source')
        grid = None
        if _finite(period) and period > 0 and _finite(phase):
            grid = {'period_seconds': period, 'phase_seconds': phase,
                    'window_seconds': _num(basis.get('window_seconds')),
                    'basis': ('flags_triage window_basis: periodic transient navigation grid; not bars, meter or a '
                              'verified metronome')}
        if explicit is not None:
            reason = 'copied from bound evidence; click identity unverified'
        elif grid is not None:
            reason = BPM_GRID_ONLY
        else:
            reason = BPM_NO_GRID
        return {'value': explicit, 'reason': reason, 'basis': explicit_basis, 'grid': grid}

    @staticmethod
    def _envelope(layer):
        if not isinstance(layer, dict):
            return {'status': 'unavailable', 'reason': 'layer_missing', 'document': None}
        status = layer.get('status') if layer.get('status') in ('available', 'unavailable') else 'unavailable'
        reason = layer.get('reason') if isinstance(layer.get('reason'), str) else None
        if status != 'available':
            return {'status': 'unavailable', 'reason': (reason or 'layer_unavailable')[:120], 'document': None}
        return {'status': 'available', 'reason': None,
                'document': scrub({key: value for key, value in layer.items() if key not in ('status', 'reason')})}

    def _timing(self, layer):
        if not isinstance(layer, dict) or layer.get('status') != 'available':
            return self._envelope(layer)
        kept, refused = [], [{'file': _text(_dict(item).get('file'), 200), 'reason': _text(_dict(item).get('reason'), 120)}
                              for item in _list(layer.get('refused'))]
        for item in _list(layer.get('files')):
            item = _dict(item)
            document = _dict(item.get('document'))
            label = _text(item.get('file'), 200)
            if document.get('tool') != 'phrase_timing' or not isinstance(document.get('phrases'), list):
                refused.append({'file': label, 'reason': 'layer_schema_unknown'})
            elif document.get('schema_version') == 1:
                refused.append({'file': label, 'reason': 'layer_schema_superseded'})
            elif document.get('schema_version') != 2 or document.get('run_kind') not in TIMING_RUN_KINDS:
                refused.append({'file': label, 'reason': 'layer_schema_unknown'})
            else:
                code = check_timing_directions(document)
                if code:
                    refused.append({'file': label, 'reason': code})
                else:
                    kept.append({'file': label, 'sha256': _sha(item.get('sha256')),
                                 'analyzed_input_sha256': _sha(item.get('analyzed_input_sha256')),
                                 'source_binding': _text(item.get('source_binding'), 200),
                                 'run_kind': document['run_kind'], 'document': scrub(document)})
        if not kept:
            reason = refused[0]['reason'] if refused else 'input_not_supplied'
            return {'status': 'unavailable', 'reason': reason or 'layer_unavailable',
                    'document': {'files': [], 'refused': refused}}
        return {'status': 'available', 'reason': None, 'document': {'files': kept, 'refused': refused}}

    def _instrument_lines(self):
        try:
            data, _ = self._read_bytes(self.program_root, ['instrument.json'], MiB)
            instrument = strict_json(data, 'instrument')
        except (_Missing, _Confined, OSError, ValueError):
            return []
        lines = []
        for string in _list(_dict(instrument).get('strings')):
            string = _dict(string)
            if string.get('string_number') == 9 and _finite(string.get('frequency_hz')):
                lines.append({'label': f'theoretical {_text(string.get("note"), 8) or "C1"} (instrument.json)',
                              'hz': string['frequency_hz']})
        return lines

    def _spectrogram(self, ctx, attachments):
        renders = [item for item in attachments if item.kind == 'lowreg_render']
        current = [item for item in renders if item.state == 'current']
        empty = {'status': 'unavailable', 'reason': None, 'evidence_id': None, 'signal_version': None, 'stage': None,
                 'shape': None, 'band_centre_hz': [], 'band_centre_hz_range': None, 'hop_seconds': None,
                 'window_seconds': None, 'first_frame_centre_seconds': None, 'axis_offset_seconds': None,
                 'matrices': [], 'reference_lines': [], 'claim': SPECTROGRAM_CLAIM, 'pcen_status': None}
        if not current:
            if any(item.state == 'unbound' for item in renders):
                return {**empty, 'status': 'unbound', 'reason': 'render present but no resampler record binds it'}, \
                    {'value': 'unbound', 'reason': 'A low-register render exists but is not bound to a current stage.'}
            reason = ('bound render invalidated' if any(item.state == 'invalidated' for item in renders)
                      else 'no low-register render bound to this run')
            return {**empty, 'reason': reason}, {'value': 'unavailable', 'reason': reason}

        def preference(item):
            stage = getattr(item, 'parent_stage', None)
            rank = SPECTROGRAM_STAGE_PREFERENCE.index(stage) if stage in SPECTROGRAM_STAGE_PREFERENCE else 99
            return rank, item.evidence_id
        chosen = sorted(current, key=preference)[0]
        document = chosen.document
        shape = _dict(document.get('shape'))
        centres = [value for value in _list(document.get('band_centre_hz')) if _finite(value)][:4096]
        timeline = _dict(ctx.manifest.get('timeline'))
        coverage = _dict(document.get('coverage'))
        matrices = []
        for media_name, record in sorted(chosen.media.items(), key=lambda pair: pair[1]['matrix']):
            matrices.append({'name': record['matrix'], 'media_name': media_name, 'sha256': record['sha256'],
                             'dtype': record['dtype'], 'layout': record['layout'],
                             'status': ('experimental_fixed_knobs_not_tuned' if record['matrix'] == 'pcen'
                                        else 'baseline_log_power')})
        spectrogram = {**empty, 'status': 'available', 'evidence_id': chosen.evidence_id,
                       'signal_version': chosen.bound_signal_version, 'stage': getattr(chosen, 'parent_stage', None),
                       'shape': {'frames': _int(shape.get('frames')), 'bands': _int(shape.get('bands'))},
                       'band_centre_hz': centres,
                       'band_centre_hz_range': [min(centres), max(centres)] if centres else None,
                       'hop_seconds': _num(document.get('hop_seconds')),
                       'window_seconds': _num(document.get('temporal_support_seconds')),
                       'first_frame_centre_seconds': _num(coverage.get('first_frame_centre_seconds')),
                       'axis_offset_seconds': _num(timeline.get('audio_start_seconds')) or 0.0,
                       'matrices': matrices, 'reference_lines': self._instrument_lines(),
                       'pcen_status': _text(document.get('pcen_status'), 80)}
        return spectrogram, {'value': 'bound', 'reason': 'A current lowreg-render-v1 is bound through its resampler '
                                                          'record to a current run stage.'}

    # ----------------------------------------------------------------- public reads

    def list_runs(self, query):
        values = parse_query(query, {'limit': RUN_LIST_DEFAULT})
        limit = values['limit']
        if not isinstance(limit, int) or not 1 <= limit <= RUN_LIST_MAX:
            raise WebJobsError('bad_query', 400, f'limit must be an integer in 1..{RUN_LIST_MAX}')
        rows, truncated = [], False
        try:
            self._check_tree()
            with os.scandir(self.runs) as iterator:
                names = sorted((entry.name for entry in iterator), reverse=True)
        except WebJobsError:
            names = []
        except OSError:
            names = []
        for name in names:
            if not artifact_ids.COMPONENT.fullmatch(name) or '.partial' in name:
                continue
            try:
                info = os.lstat(self.runs / name)
                manifest_info = os.lstat(self.runs / name / 'manifest.json')
            except OSError:
                continue
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or not stat.S_ISREG(manifest_info.st_mode):
                continue
            if len(rows) == limit:
                truncated = True
                break
            row = {'run_id': name, 'run_status': None, 'source_id': None, 'source_sha256': None,
                   'manifest_sha256': None, 'manifest_readable': False, 'stage_count': None,
                   'state_basis': 'listing does not re-hash'}
            try:
                data, _ = self._read_bytes(self.runs, [name, 'manifest.json'], MAX_MANIFEST_BYTES)
                manifest = strict_json(data, 'manifest')
            except (_Missing, _Confined, OSError, ValueError):
                manifest = None
            if isinstance(manifest, dict):
                source = _sha(_dict(manifest.get('source')).get('sha256'))
                row.update(run_status=_text(manifest.get('status'), 120), source_sha256=source,
                           source_id=artifact_ids.source_id_for(source) if source else None,
                           manifest_sha256=hashlib.sha256(data).hexdigest(), manifest_readable=True,
                           stage_count=len(_dict(manifest.get('outputs'))))
            rows.append(row)
        return {'schema_id': SCHEMA_IDS['list'], 'schema_version': SCHEMA_VERSION, 'runs': rows,
                'truncated': truncated}

    def run_graph(self, run_id, server=None):
        ctx = self._context(run_id)
        attachments, truncated = self._attachments(ctx)
        manifest = ctx.manifest
        pcm, timeline = _dict(manifest.get('pcm')), _dict(manifest.get('timeline'))
        admitted = self._admitted_sources(server, ctx)
        acceptance = self._listening_acceptance(ctx)
        bundle, _ = self._select_bundle(attachments, None)
        _, binding = self._spectrogram(ctx, attachments)
        clocked = [item['source_artifact_id'] for item in admitted or [] if item['has_annotation_clock']]
        physical = _bool(_dict(manifest.get('dsp_latency')).get('physical_audio_video_sync_verified'))
        names = {node['stage'] for node in ctx.stages}
        edges = [{'from': a, 'to': b, 'edge_basis': ROLE_BASIS} for a, b in GRAPH_EDGES if a in names and b in names]
        return {
            'schema_id': SCHEMA_IDS['run'], 'schema_version': SCHEMA_VERSION, 'run_id': run_id,
            'run_status': _text(manifest.get('status'), 120), 'manifest_sha256': ctx.manifest_sha256,
            'source_sha256': ctx.source_sha256,
            'source_id': artifact_ids.source_id_for(ctx.source_sha256) if ctx.source_sha256 else None,
            'admitted_sources': admitted or [],
            'admitted_sources_lookup': 'available' if admitted is not None else 'unavailable',
            'pcm': {'sample_rate': _int(pcm.get('sample_rate')), 'channels': _int(pcm.get('channels')),
                    'sample_count': _int(pcm.get('sample_count')), 'duration_seconds': _num(pcm.get('duration_seconds'))},
            'timeline': {'audio_start_seconds': _num(timeline.get('audio_start_seconds')),
                         'format_start_seconds': _num(timeline.get('format_start_seconds')),
                         'no_time_stretch': _bool(timeline.get('no_time_stretch')),
                         'axis': 'decoded source audio seconds'},
            'stages': [{key: value for key, value in node.items() if not key.startswith('_')} for node in ctx.stages],
            'edges': edges,
            'processing': self._processing(manifest),
            'evidence': [item.public() for item in attachments],
            'invalidation': [{'evidence_id': item.evidence_id, 'reason': item.reason,
                              'was_bound_to': item.bound_signal_version, 'now': item.now}
                             for item in attachments if item.state == 'invalidated'],
            'listening_acceptance': acceptance,
            'claim_boundary': {'listening_acceptance_scope': acceptance['scope'], **CLAIM_BOUNDARY},
            'unknown_fields': self._unknown_fields(bundle, acceptance=acceptance, bpm=self._bpm(bundle),
                                                   physical_sync=physical, spectrogram_binding=binding,
                                                   annotation_source=clocked[0] if clocked else None),
            'discovery_truncated': truncated,
        }

    def run_layers(self, run_id, query, server=None):
        values = parse_query(query, {'evidence': None})
        requested = values['evidence']
        if requested is not None and not EVIDENCE_ID.fullmatch(requested):
            raise WebJobsError('bad_query', 400, 'evidence must be evd_ followed by 32 hex digits')
        ctx = self._context(run_id)
        attachments, truncated = self._attachments(ctx)
        bundle, alternatives = self._select_bundle(attachments, requested)
        acceptance = self._listening_acceptance(ctx)
        spectrogram, binding = self._spectrogram(ctx, attachments)
        bpm = self._bpm(bundle)
        admitted = self._admitted_sources(server, ctx)
        clocked = [item['source_artifact_id'] for item in admitted or [] if item['has_annotation_clock']]
        physical = _bool(_dict(ctx.manifest.get('dsp_latency')).get('physical_audio_video_sync_verified'))
        no_bundle = {'status': 'unavailable', 'reason': 'no current practice bundle is bound to this run',
                     'document': None}
        if bundle is not None:
            source_layers = _dict(bundle.document.get('layers'))
            layers = {name: self._envelope(source_layers.get(name)) for name in ('tone_ab', 'coverage', 'flags_triage')}
            layers['phrase_timing'] = self._timing(source_layers.get('phrase_timing'))
            media = {name: {'evidence_id': bundle.evidence_id, 'sha256': record['sha256'], 'frames': record['frames'],
                            'sample_rate': record['sample_rate'], 'channels': record['channels'],
                            'role': record['role']} for name, record in sorted(bundle.media.items())}
        else:
            layers = {name: dict(no_bundle) for name in LAYER_NAMES}
            media = {}
        layers['spectrogram'] = {'status': spectrogram['status'], 'reason': spectrogram['reason'], 'document': None}
        layers['bpm'] = bpm
        return {
            'schema_id': SCHEMA_IDS['layers'], 'schema_version': SCHEMA_VERSION, 'run_id': run_id,
            'manifest_sha256': ctx.manifest_sha256,
            'selected_evidence_id': bundle.evidence_id if bundle is not None else None,
            'selected_generated_utc': bundle.generated_utc if bundle is not None else None,
            'alternatives': alternatives, 'layers': layers, 'media': media, 'spectrogram': spectrogram,
            'clock': dict(CLOCK),
            'source_extent': {'audio_start_seconds': _num(_dict(ctx.manifest.get('timeline')).get('audio_start_seconds')),
                              'duration_seconds': _num(_dict(ctx.manifest.get('pcm')).get('duration_seconds'))},
            'unknown_fields': self._unknown_fields(bundle, acceptance=acceptance, bpm=bpm, physical_sync=physical,
                                                   spectrogram_binding=binding,
                                                   annotation_source=clocked[0] if clocked else None),
            'claim_boundary': {'listening_acceptance_scope': acceptance['scope'], **CLAIM_BOUNDARY},
            'discovery_truncated': truncated,
        }

    # ----------------------------------------------------------------- byte routes

    def open_layer_media(self, run_id, evidence_id, name):
        if not isinstance(evidence_id, str) or not EVIDENCE_ID.fullmatch(evidence_id):
            raise WebJobsError('malformed_id', 400, 'evidence id must be evd_ followed by 32 hex digits')
        if not isinstance(name, str) or not MEDIA_NAME.fullmatch(name):
            raise WebJobsError('unknown_media', 404, 'media name is not in the attachment media table')
        ctx = self._context(run_id)
        attachments, _ = self._attachments(ctx)
        attachment = next((item for item in attachments if item.evidence_id == evidence_id), None)
        if attachment is None or name not in attachment.media:
            raise WebJobsError('unknown_media', 404, 'media name is not in the attachment media table')
        if attachment.state != 'current':
            raise WebJobsError('media_stale', 409, 'the attachment is no longer bound to this run')
        record = attachment.media[name]
        return self._open_verified(self.artifacts, record['parts'], record['sha256'], evidence_id,
                                   content_type_for(name), stale_code='media_stale', missing_code='media_missing')

    def open_run_artifact(self, run_id, artifact_id):
        if not isinstance(artifact_id, str) or not ARTIFACT_ID.fullmatch(artifact_id):
            raise WebJobsError('malformed_id', 400, 'artifact id must be art_ followed by 32 hex digits')
        ctx = self._context(run_id)
        for node in ctx.stages:
            if node['artifact_id'] == artifact_id:
                if node['_parts'] is None:
                    raise WebJobsError('artifact_missing', 410, 'the run file is not present')
                expected = node['_bound'] or node['_observed']
                served = self._open_verified(self.runs, node['_parts'], expected, artifact_id,
                                             content_type_for(node['stage']), stale_code='artifact_stale',
                                             missing_code='artifact_missing')
                return served, f'{artifact_id}{Path(node["stage"]).suffix.lower()}'
        attachments, _ = self._attachments(ctx)
        for attachment in attachments:
            if attachment.state != 'current' or attachment.kind not in ('editor_marker_export', 'marked_compact'):
                continue
            for item in attachment.files:
                if item['artifact_id'] == artifact_id:
                    served = self._open_verified(self.artifacts, item['_parts'], item['sha256'], artifact_id,
                                                 content_type_for(item['name']), stale_code='artifact_stale',
                                                 missing_code='artifact_missing')
                    return served, f'{artifact_id}{Path(item["name"]).suffix.lower()}'
        raise WebJobsError('unknown_artifact', 404, 'artifact id is not a file of this run')

    def _open_verified(self, base, parts, expected, identifier, content_type, *, stale_code, missing_code):
        try:
            descriptor, before = self._open(base, parts)
        except _Missing:
            raise WebJobsError(missing_code, 410, 'the file is no longer present') from None
        except _Confined:
            raise WebJobsError('confinement_refused', 403, 'the file location is not confined') from None
        try:
            digest, size = web_jobs.hash_descriptor(descriptor, MAX_STAGE_BYTES)
            after = os.fstat(descriptor)
        except BaseException:
            os.close(descriptor)
            raise
        if web_jobs.file_signature(before) != web_jobs.file_signature(after) or digest != expected \
                or size != after.st_size:
            os.close(descriptor)
            raise WebJobsError(stale_code, 409, 'the file bytes no longer match the recorded sha256')
        return web_jobs.ServedArtifact(identifier, descriptor, size, digest, content_type,
                                       web_jobs.file_signature(after))

    # ----------------------------------------------------------------- capabilities

    def _registry(self, name):
        try:
            data, _ = self._read_bytes(self.program_root, [name], MAX_REGISTRY_BYTES)
            document = strict_json(data, name)
        except (_Missing, _Confined, OSError, ValueError):
            raise WebJobsError('registry_unreadable', 500, 'a program registry is unreadable') from None
        if not isinstance(document, dict):
            raise WebJobsError('registry_unreadable', 500, 'a program registry is unreadable')
        return document, hashlib.sha256(data).hexdigest()

    def capabilities(self):
        tools_doc, tools_sha = self._registry('tools.json')
        caps_doc, caps_sha = self._registry('capabilities.json')
        models_doc, models_sha = self._registry('models.json')
        capabilities = {item.get('tool'): item for item in _list(caps_doc.get('capabilities')) if isinstance(item, dict)}
        tools = []
        for descriptor in _list(tools_doc.get('tools')):
            if not isinstance(descriptor, dict) or not isinstance(descriptor.get('name'), str):
                raise WebJobsError('registry_unreadable', 500, 'a program registry is unreadable')
            name = descriptor['name']
            capability = capabilities.get(name)
            if capability is not None and isinstance(capability.get('domain'), str):
                area, area_basis = capability['domain'], DOMAIN_BASIS
            elif name in TOOL_AREAS:
                area, area_basis = TOOL_AREAS[name], AREA_BASIS
            else:
                area, area_basis = 'unmapped', 'absent from program/capabilities.json and the presentation map'
            schema = _dict(descriptor.get('inputSchema'))
            annotations = _dict(descriptor.get('annotations'))
            dependencies = _dict(descriptor.get('dependencies'))
            limitations = [_text(text, MAX_TEXT) for text in _list(descriptor.get('limitations')) if isinstance(text, str)]
            tools.append({
                'name': name[:64], 'title': _text(descriptor.get('title'), 120), 'area': area, 'area_basis': area_basis,
                'implementation_status': _text(descriptor.get('implementation_status'), 64),
                'evidence_kind': _text(descriptor.get('evidence_kind'), 64),
                'annotations': {key: _bool(annotations.get(key)) for key in
                                ('readOnlyHint', 'destructiveHint', 'idempotentHint', 'openWorldHint')},
                'skill': _text(descriptor.get('skill'), 300),
                'limitations_count': len(limitations), 'limitations': limitations[:64],
                'dependencies': {
                    'recommended_prior_tools': [str(item)[:64] for item in
                                                _list(dependencies.get('recommended_prior_tools'))][:32],
                    'enforced': _bool(dependencies.get('enforced')),
                    'note': _text(dependencies.get('note'), 600)},
                'input': {'properties': sorted(str(key)[:64] for key in _dict(schema.get('properties')))[:128],
                          'required': sorted(str(key)[:64] for key in _list(schema.get('required')))[:128]},
                'capability': self._capability(capability) if capability is not None else None,
                'capability_reason': None if capability is not None else CAPABILITY_NULL_REASON,
            })
        models = []
        for model_id, record in sorted(_dict(models_doc.get('models')).items()):
            record = _dict(record)
            url = record.get('url')
            host = urlsplit(url).hostname if isinstance(url, str) else None
            sha, max_bytes = _sha(record.get('sha256')), _int(record.get('max_bytes'))
            entry = {'model_id': str(model_id)[:128], 'format': _text(record.get('format'), 64),
                     'license': _text(record.get('license'), 300), 'sha256': sha, 'max_bytes': max_bytes,
                     'source_commit': _text(record.get('source_commit'), 64), 'url_host': _text(host, 255),
                     'registration': 'registered_hash_bound' if sha and max_bytes else 'registered_incomplete',
                     'local_presence': 'not_checked'}
            for key in ('lane', 'gate', 'status'):
                entry[key] = _text(record.get(key), 200) if isinstance(record.get(key), str) else None
            gate_state = record.get('gate_state')
            entry['gate_state'] = ({'value': _text(gate_state, 200), 'reason': 'recorded in program/models.json'}
                                   if isinstance(gate_state, str) else {'value': None, 'reason': MODEL_GATE_REASON})
            models.append(entry)
        areas = {}
        for tool in tools:
            areas.setdefault(tool['area'], []).append(tool['name'])
        return {
            'schema_id': SCHEMA_IDS['capabilities'], 'schema_version': SCHEMA_VERSION,
            'tool_count': len(tools), 'pilot_tool_count': sum(1 for tool in tools if tool['capability'] is not None),
            'tools': tools,
            'areas': [{'area': area, 'tools': names} for area, names in sorted(areas.items())],
            'models': models, 'model_note': MODEL_NOTE,
            'registry_sha256': {'tools': tools_sha, 'capabilities': caps_sha, 'models': models_sha},
            'unknown_fields': {
                'model_local_presence': {'value': 'not_checked', 'reason': 'This read API never inspects model caches.'},
                'model_gate_state': {'value': None, 'reason': 'per model: gate_state is copied only when recorded'},
                'tool_area_basis': {'value': AREA_BASIS, 'reason': (
                    'Tool areas come from program/capabilities.json domains where present, else this presentation map.')},
            },
        }

    @staticmethod
    def _capability(capability):
        effects = _dict(capability.get('effects'))
        resources = _dict(capability.get('resources'))
        timeout = _dict(resources.get('timeout_seconds'))
        return {
            'domain': _text(capability.get('domain'), 64), 'stage': _text(capability.get('stage'), 64),
            'effects': {'reads': [str(item)[:64] for item in _list(effects.get('reads'))][:32],
                        'writes': [str(item)[:64] for item in _list(effects.get('writes'))][:32],
                        'renders_audio': _bool(effects.get('renders_audio')),
                        'renders_video': _bool(effects.get('renders_video')),
                        'network': _bool(effects.get('network')),
                        'model_acquisition': _bool(effects.get('model_acquisition')),
                        'overwrites_input': _bool(effects.get('overwrites_input'))},
            'resources': {'resource_class': _text(resources.get('resource_class'), 64),
                          'heavy_numeric': _bool(resources.get('heavy_numeric')),
                          'timeout_seconds': {key: _num(timeout.get(key)) for key in ('min', 'max', 'default')}},
            'parameters': {str(name)[:64]: {'default_owner': _text(_dict(spec).get('default_owner'), 32),
                                            'default_policy': _text(_dict(spec).get('default_policy'), 64)}
                           for name, spec in sorted(_dict(capability.get('parameters')).items())},
        }


# --------------------------------------------------------------------------- query parsing

def parse_query(query, defaults):
    """Strict query: known keys only, each at most once. ``limit`` is parsed as a positive integer."""
    values = dict(defaults)
    if not query:
        return values
    try:
        pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True, max_num_fields=4)
    except ValueError:
        raise WebJobsError('bad_query', 400, 'query string is malformed') from None
    seen = set()
    for key, value in pairs:
        if key not in defaults or key in seen:
            raise WebJobsError('bad_query', 400, 'query names an unsupported or repeated parameter')
        seen.add(key)
        if key == 'limit':
            if not LIMIT.fullmatch(value):
                raise WebJobsError('bad_query', 400, f'limit must be an integer in 1..{RUN_LIST_MAX}')
            values[key] = int(value)
        else:
            values[key] = value
    return values


# --------------------------------------------------------------------------- HTTP entry points

_APIS = {}
_APIS_LOCK = threading.Lock()


def api_for(server):
    """The server's RunsAPI: an explicit ``server.runs_api`` or one per runs root (cached)."""
    explicit = getattr(server, 'runs_api', None)
    if explicit is not None:
        return explicit
    root = server.jobs.runs_root
    with _APIS_LOCK:
        api = _APIS.get(str(root))
        if api is None:
            api = _APIS[str(root)] = RunsAPI(root)
        return api


def match(path):
    """Route tuple for a request path, or None when this module does not own the path."""
    if path == '/api/v1/runs':
        return ('runs', ())
    if path == '/api/v1/capabilities':
        return ('capabilities', ())
    if path.startswith('/api/v1/runs/'):
        return ('run', tuple(path[len('/api/v1/runs/'):].split('/')))
    if path.startswith('/api/v1/capabilities/'):
        return ('unknown', ())
    return None


def _segment(value):
    return isinstance(value, str) and value.isascii() and artifact_ids.COMPONENT.fullmatch(value) is not None \
        and '.partial' not in value


def _no_query(query):
    if query:
        raise WebJobsError('bad_query', 400, 'this route accepts no query string')


def send_json(handler, status, value):
    try:
        body = encode(value)
    except (TypeError, ValueError):
        raise WebJobsError('internal_error', 500, 'internal_error') from None
    if len(body) > MAX_RESPONSE_BYTES:
        raise WebJobsError('layers_too_large', 507, f'response exceeds {MAX_RESPONSE_BYTES} bytes')
    handler._headers(status, 'application/json', len(body))
    handler.wfile.write(body)


def stream(handler, served, disposition, filename, before_send=None):
    """Whole-file response; bytes that change mid-stream end in a short body and a closed connection."""
    try:
        if before_send is not None:
            before_send()
        handler._headers(200, served.content_type, served.size_bytes, {
            'X-Artifact-Sha256': served.sha256,
            'Content-Disposition': f'{disposition}; filename="{filename}"',
            'Accept-Ranges': 'none'})
        offset = 0
        while offset < served.size_bytes:
            chunk = os.pread(served.descriptor, min(STREAM_CHUNK, served.size_bytes - offset), offset)
            if not chunk:
                break
            handler.wfile.write(chunk)
            offset += len(chunk)
        if offset != served.size_bytes or web_jobs.file_signature(os.fstat(served.descriptor)) != served.signature:
            handler.close_connection = True
    finally:
        served.close()


def serve(handler, route, query):
    """Serve one matched route. Raises ``WebJobsError`` for every refusal (web_api writes the body)."""
    if handler.command != 'GET':
        raise WebJobsError('method_not_allowed', 405, 'only GET is allowed on the runs read API')
    kind, parts = route
    server = handler.server
    api = api_for(server)
    if kind == 'runs':
        send_json(handler, 200, api.list_runs(query))
        return
    if kind == 'capabilities':
        _no_query(query)
        send_json(handler, 200, api.capabilities())
        return
    if kind != 'run':
        raise WebJobsError('route_not_found', 404, 'unknown route')
    if not parts or not _segment(parts[0]):
        raise WebJobsError('malformed_id', 400, 'run id must be one safe path component')
    run_id = parts[0]
    rest = parts[1:]
    if not rest:
        _no_query(query)
        send_json(handler, 200, api.run_graph(run_id, server))
    elif rest == ('layers',):
        send_json(handler, 200, api.run_layers(run_id, query, server))
    elif len(rest) >= 2 and rest[:2] == ('layers', 'media'):
        _no_query(query)
        if len(rest) != 4:
            raise WebJobsError('unknown_media', 404, 'media name is not in the attachment media table')
        served = api.open_layer_media(run_id, rest[2], rest[3])
        stream(handler, served, 'inline', f'{rest[2]}-{rest[3]}', api.before_send)
    elif len(rest) == 2 and rest[0] == 'artifacts':
        disposition = parse_query(query, {'disposition': 'attachment'})['disposition']
        if disposition not in ('inline', 'attachment'):
            raise WebJobsError('bad_query', 400, 'disposition must be inline or attachment')
        served, filename = api.open_run_artifact(run_id, rest[1])
        stream(handler, served, disposition, filename, api.before_send)
    else:
        raise WebJobsError('route_not_found', 404, 'unknown route')


if __name__ == '__main__':  # read-only CLI preview: python3 scripts/web_runs_api.py <run_id> [--layers]
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('run_id', nargs='?')
    parser.add_argument('--layers', action='store_true')
    parser.add_argument('--root', default=None)
    args = parser.parse_args()
    api = RunsAPI(args.root)
    try:
        if args.run_id is None:
            value = api.list_runs('')
        elif args.layers:
            value = api.run_layers(args.run_id, '')
        else:
            value = api.run_graph(args.run_id)
    except WebJobsError as error:
        print(json.dumps(error.body(), sort_keys=True), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(value, indent=1, sort_keys=True))
