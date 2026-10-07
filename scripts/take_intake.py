#!/usr/bin/env python3
"""One-command intake for a new take: plan, run (with resume) and evidence packet.

Contract: docs/spec/sprints/TAKE_INTAKE_S3.md (S3 lane take_intake, Linear TIN-5186).
Authority: operator ruling 2026-10-07 "Second take | New take family plus full
pipeline" (docs/agent-notes/2026-10-07-s2-operator-rulings.md), repository
AGENTS.md, R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13.

Stdlib only. This orchestrator never implements DSP, analysis or export: every
stage is an existing repository entrypoint launched as a bounded subprocess
(exact argv, no shell). It never writes to the source, never writes outside
ROOT/artifacts, never adopts a default, never sends anything to Linear or a
peer, and never signals a process it did not start (R-N11).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import artifact_ids  # noqa: E402  (reused: source_id_for)
import corpus  # noqa: E402  (reused: identifier, fingerprint, IDENTIFIER)
import corpus_split_s1  # noqa: E402  (reused: validate_split, SCHEMA)
import run_demo  # noqa: E402  (reused: sha256, strict_json, atomic_json, pid_alive, group_alive)

SCHEMA_PLAN = 'video-utils.take-intake.plan.s3'
SCHEMA_STATE = 'video-utils.take-intake.state.s3'
SCHEMA_PACKET = 'video-utils.take-intake.packet.s3'
SCHEMA_DRAFT = 'video-utils.take-intake.xoruby-draft.s3'
SCHEMA_ROW_DRAFT = 'video-utils.take-intake.corpus-row-draft.s3'
SCHEMA_REPLAY = 'video-utils.take-intake.replay-arguments.local.s3'
SCHEMA_VERSION = 1
AUTHORITY = ('Operator ruling 2026-10-07 (second take: new take family plus full pipeline); '
             'R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13; TIN-3692 98cf680c-7299-4949-bfb2-60079053ad43')
FAMILY_DOMAIN = b'video-utils/take-family/v1\0'
FIRST_TAKE_SHA256 = 'a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6'
BUILTIN_FAMILIES = {'demo-oct5-2026': FIRST_TAKE_SHA256, 'october5-demo': FIRST_TAKE_SHA256}
REGISTRY_GLOBS = ('docs/spec/examples/corpus-split/*.json', 'docs/agent-notes/sprints/*/corpus-*.json',
                  'docs/agent-notes/peers/xoruby/*.json')
MAX_REGISTRY_FILE_BYTES = 2 * 1024 * 1024
MAX_REGISTRY_FILES = 500
MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_STDOUT_PARSE_BYTES = 2 * 1024 * 1024
TAIL_BYTES = 4096
SETUP_WINDOW_SECONDS = (0.0, 5.0)
CAPTURE_MIN_SECONDS, CAPTURE_MAX_SECONDS = 0.1, 10.0
MAX_REVIEW_CHARS = 2000
V6_REFERENCE = 'docs/agent-notes/2026-10-07-s2-operator-rulings.md'
FIRST_TAKE_ARRANGEMENT = 'program/demo-arrangement.json'
PROFILE = 'fuller'
PROFILE_TARGETS = {'integrated_lufs': -18.0, 'true_peak_dbtp': -1.75}
INTAKE_ID_PATTERN = re.compile(r'[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}')
STAGE_NAMES = ('demo', 'flags_triage', 'arrangement_reference', 'arrangement_markers', 'phrase_anchor',
               'phrase_timing', 'marked_video', 'marked_compact', 'share_export', 'packet')
STAGE_TIMEOUTS = {'demo': 7800, 'flags_triage': 180, 'arrangement_reference': 300, 'arrangement_markers': 180,
                  'phrase_anchor': 300, 'phrase_timing': 300, 'marked_video': 900, 'marked_compact': 1260,
                  'share_export': 960, 'packet': 300}
SUCCESS_STATUSES = frozenset({'completed', 'completed_with_stage_failures', 'abstained_no_reference',
                              'abstained_no_anchor', 'abstained_clicks_not_selected',
                              'abstained_arrangement_markers_required'})
FAILURE_STATUSES = frozenset({'failed', 'killed', 'timed_out', 'skipped_dependency_failed', 'running', 'pending'})
SETTING_FLAGS = ('capture_interval', 'capture_review', 'interval_reviewed_includes_setup', 'family', 'arrangement',
                 'anchor_seconds', 'anchor_source', 'clicks_per_grid_period', 'bpm', 'features', 'analysis_python',
                 'origin', 'source')
ABS_PATH = re.compile(r'(?<![\w.~<>/:-])/[\w.~+@%-]+(?:/[\w.~+@%-]*)*')
HEX64 = re.compile(r'[0-9a-fA-F]{64}')
LOW_REGISTER_PATTERNS = (
    ('highpass', re.compile(r'\bhighpass\b|\bhpf\b', re.I)),
    ('bandreject', re.compile(r'\bbandreject\b|\bbandstop\b', re.I)),
    ('anequalizer', re.compile(r'\banequalizer\b', re.I)),
    ('mains_notch', re.compile(r'\b(?:equalizer|bandreject|notch)\b[^,;\]]*?\b(?:f|frequency)=(?:50|60|100|120)(?:\.0+)?\b', re.I)),
)
LOWPASS = re.compile(r'\blowpass\b[^,;\]]*?\b(?:f|frequency)=([0-9.]+)', re.I)

UNKNOWNS = {
    'split': {'value': None, 'split_status': 'pending_operator_choice', 'class': 'operator_input_required',
              'reason': 'corpus split is an operator choice; the lane never assigns one'},
    'arrangement_reference': {'value': None, 'class': 'operator_input_required',
                              'reason': 'no source-bound arrangement reference supplied for this take'},
    'operator_bpm': {'value': None, 'class': 'operator_input_required', 'reason': 'not supplied'},
    'meter': {'value': None, 'class': 'inferred', 'reason': 'not_established'},
    'time_signature': {'value': None, 'class': 'inferred', 'reason': 'not_established'},
    'tonic': {'value': None, 'class': 'inferred', 'reason': 'not_established'},
    'mode': {'value': None, 'class': 'inferred', 'reason': 'not_established'},
    'capture_interval_noise_only_verified': {'value': False, 'class': 'needs_listening',
                                             'reason': 'no worker verifies that the reviewed interval holds only fan/background noise'},
    'capture_interval_setup_override': {'value': None, 'class': 'measured',
                                        'reason': 'operator flag record, or null when the interval starts at or after 5.0 s'},
    'click_identity': {'value': 'unverified', 'class': 'not_performed',
                       'reason': 'periodic high-frequency transients are not verified as the metronome'},
    'physical_capture_latency': {'value': 'uncalibrated', 'class': 'operator_input_required',
                                 'reason': 'needs an operator capture-latency calibration recording'},
    'phrase_timing_direction': {'value': 'withheld_uncalibrated', 'class': 'not_performed',
                                'reason': 'ahead/behind direction needs calibrated latency and click identity'},
    'phrase_boundary_correctness': {'value': 'unknown', 'class': 'operator_input_required',
                                    'reason': 'needs at least 10 operator-marked boundaries on this take'},
    'phrase_anchor_adopted': {'value': False, 'class': None, 'reason': 'no anchor projection is adopted by this lane'},
    'note_correctness': {'value': 'not_performed', 'class': 'not_performed', 'reason': 'no approved intended-note reference'},
    'missed_or_extra_notes': {'value': 'not_performed', 'class': 'not_performed',
                              'reason': 'no approved expected-rhythm reference; attack counts never identify missed notes'},
    'listening_acceptance': {'value': 'not_performed', 'class': 'needs_listening',
                             'reason': 'FULLER-v1 acceptance covers only the accepted October 5 chain'},
    'low_end_fullness_feedback': {'value': 'open', 'class': 'needs_listening',
                                  'reason': 'operator feedback on low-end fullness and thin/nasal balance remains open'},
    'editor_import': {'value': 'not_performed', 'class': 'not_performed',
                      'reason': 'Final Cut / Resolve import needs actual application proof'},
    'cfr_vfr_status': {'value': 'unknown', 'class': 'measured', 'reason': 'from the ffprobe declared frame rates'},
    'memory_ceiling': {'value': 'unknown_not_measured', 'class': 'unknown', 'reason': 'no RSS limit is enforced or measured'},
    'xoruby_delivery': {'value': 'draft_not_sent', 'class': None, 'reason': 'root sends the TIN-5186 draft after operator review'},
    'default_adoption': {'value': 'none', 'class': None, 'reason': 'no detector, profile or master is adopted'},
}
CLAIM_CLASSES = ('measured', 'inferred', 'needs_listening', 'operator_input_required', 'not_performed')
DRAFT_KEYS = frozenset({'schema_id', 'schema_version', 'status', 'issue', 'take_family_id', 'family_basis', 'origin',
                        'intake_status', 'stage_status_counts', 'probe_class', 'unknowns', 'claim_class_counts',
                        'split', 'v6_statement_reference', 'note'})
PROBE_CLASS_KEYS = frozenset({'container_duration_rounded_0_1', 'video_codec', 'audio_codec', 'sample_rate_hz',
                              'channel_count', 'cfr_vfr_status'})


class IntakeRefusal(Exception):
    def __init__(self, code: str, message: str, **details):
        super().__init__(message)
        self.code = code
        self.details = details


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def family_id_for(source_sha256: str) -> str:
    """take-<16 hex>: domain-separated, content-bound, path-independent (contract section 4)."""
    corpus.fingerprint(source_sha256)
    return 'take-' + hashlib.sha256(FAMILY_DOMAIN + source_sha256.encode('ascii')).hexdigest()[:16]


# ----------------------------------------------------------------- scrubbing

class Scrubber:
    """Replace absolute host paths in recorded strings (contract M9)."""

    def __init__(self, root: Path = ROOT, source: Path | None = None, extra: dict | None = None):
        pairs = []
        for value, label in ((source, '<SOURCE>'), (source.parent if source else None, '<SOURCE_DIR>'),
                             (Path(sys.executable), '<PYTHON>'), (root, '<ROOT>')):
            if value is not None:
                pairs.append((str(value), label))
                try:
                    resolved = str(Path(value).resolve())
                    if resolved != str(value):
                        pairs.append((resolved, label))
                except OSError:
                    pass
        for value, label in (extra or {}).items():
            pairs.append((value, label))
        self.pairs = sorted(pairs, key=lambda item: len(item[0]), reverse=True)

    def text(self, value: str) -> str:
        for raw, label in self.pairs:
            if raw and raw != '/':
                value = value.replace(raw, label)
        return ABS_PATH.sub('<ABS>', value)

    def deep(self, value):
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.deep(item) for item in value]
        if isinstance(value, dict):
            return {self.text(key) if isinstance(key, str) else key: self.deep(item) for key, item in value.items()}
        return value


def absolute_paths_in(value) -> list[str]:
    found = []
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            found.extend(ABS_PATH.findall(item))
        elif isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return found


# ------------------------------------------------------------------ helpers

def bounded_json(path: Path, limit: int = MAX_STATE_BYTES) -> dict:
    return run_demo.bounded_json_file(path, limit)


def file_identity(path: Path) -> dict:
    stat = path.stat()
    return {'sha256': run_demo.sha256(path), 'size_bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def git(arguments: list[str], cwd: Path, timeout: int = 20) -> subprocess.CompletedProcess | None:
    executable = shutil.which('git')
    if executable is None:
        return None
    try:
        return subprocess.run([executable, *arguments], cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def load_media():
    spec = importlib.util.spec_from_file_location('take_intake_media', SCRIPTS / 'media.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def under_artifacts_runs(path: Path) -> bool:
    parts = path.parts
    return any(parts[index:index + 2] == ('artifacts', 'runs') for index in range(len(parts) - 1))


# ------------------------------------------------------------- source checks

def check_source(value, repo_root: Path | None = None) -> tuple[Path, dict]:
    """Section 5 source refusals; reads metadata only (no hashing, no decode)."""
    raw = Path(str(value)).expanduser()
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    if raw.is_symlink():
        raise IntakeRefusal('source_is_symlink', 'SOURCE is a symlink; pass the regular file itself')
    if not raw.exists():
        raise IntakeRefusal('source_missing', 'SOURCE does not exist')
    resolved = raw.resolve()
    if not resolved.is_file():
        raise IntakeRefusal('source_not_regular_file', 'SOURCE is not a regular file')
    if under_artifacts_runs(resolved):
        raise IntakeRefusal('source_is_derived_artifact', 'SOURCE lies inside an artifacts/runs directory (a derived run artifact)')
    location = {'inside_repository': False, 'tracked': None, 'ignored': None, 'basis': None}
    toplevel = repo_root
    if toplevel is None:
        result = git(['rev-parse', '--show-toplevel'], ROOT)
        toplevel = Path(result.stdout.strip()).resolve() if result is not None and result.returncode == 0 else None
        location['basis'] = 'git_toplevel_of_tool_root' if toplevel else 'git_unavailable_tool_root_used'
        if toplevel is None:
            toplevel = ROOT
    else:
        toplevel = Path(toplevel).resolve()
        location['basis'] = 'injected_repository_root'
    if resolved.is_relative_to(toplevel):
        location['inside_repository'] = True
        relative = str(resolved.relative_to(toplevel))
        tracked = git(['ls-files', '--error-unmatch', '--', relative], toplevel)
        ignored = git(['check-ignore', '-q', '--', relative], toplevel)
        if tracked is None or ignored is None:
            raise IntakeRefusal('source_in_repository_tracked_path',
                                'SOURCE is inside the repository and git is unavailable to prove it is ignored')
        location['tracked'] = tracked.returncode == 0
        location['ignored'] = ignored.returncode == 0
        if location['tracked'] or not location['ignored']:
            raise IntakeRefusal('source_in_repository_tracked_path',
                                'SOURCE is inside the repository and is tracked or not ignored; originals stay out of Git')
    location['result'] = 'accepted'
    return resolved, location


def probe_summary(path: Path) -> dict:
    media = load_media()
    try:
        metadata = media.probe(path)
    except Exception as exc:  # noqa: BLE001 - every probe failure is the typed refusal below.
        raise IntakeRefusal('probe_failed', 'ffprobe could not summarize SOURCE: ' + type(exc).__name__) from exc
    video = metadata.get('video') or {}
    audio = metadata.get('audio') or {}
    fmt = metadata.get('format') or {}

    def field(container, key, convert=None):
        value = container.get(key)
        if value in (None, '', 'N/A'):
            return None
        return convert(value) if convert else value

    avg, real = field(video, 'avg_frame_rate'), field(video, 'r_frame_rate')
    if not video:
        cfr = 'unknown'
    elif avg and real and avg not in ('0/0',) and real not in ('0/0',):
        cfr = 'cfr_declared' if avg == real else 'vfr_suspected'
    else:
        cfr = 'unknown'
    summary = {
        'container_duration_seconds': number(fmt.get('duration')),
        'format_name': field(fmt, 'format_name'),
        'video': None if not video else {
            'codec': field(video, 'codec_name'), 'width': field(video, 'width', int), 'height': field(video, 'height', int),
            'avg_frame_rate': avg, 'r_frame_rate': real, 'time_base': field(video, 'time_base')},
        'audio': {'codec': field(audio, 'codec_name'), 'sample_rate_hz': field(audio, 'sample_rate', int),
                  'channels': field(audio, 'channels', int), 'start_time_seconds': number(audio.get('start_time')),
                  'duration_seconds': number(audio.get('duration'))},
        'cfr_vfr_status': cfr,
        'null_reasons': {},
        'scope': 'ffprobe declared container/stream fields only; no decode, no listening',
    }
    if not video:
        summary['null_reasons']['video'] = 'no non-attached-picture video stream'
    if summary['container_duration_seconds'] is None:
        summary['null_reasons']['container_duration_seconds'] = 'format duration not declared'
    if summary['audio']['duration_seconds'] is None:
        summary['null_reasons']['audio.duration_seconds'] = 'stream duration not declared'
    return summary


def audio_extent_seconds(probe: dict) -> float | None:
    audio = probe['audio']
    return audio['duration_seconds'] if audio['duration_seconds'] is not None else probe['container_duration_seconds']


# ----------------------------------------------------------------- registry

def registry_entries(root: Path, state_root: Path | None) -> dict:
    """Read-only bounded registry of known (take_family_id, source_sha256) pairs."""
    files, entries = [], []
    for family, source in sorted(BUILTIN_FAMILIES.items()):
        entries.append({'take_family_id': family, 'source_sha256': source, 'basis': 'builtin_floor'})
    candidates = []
    for pattern in REGISTRY_GLOBS:
        candidates.extend(sorted(root.glob(pattern)))
    prior = []
    if state_root is not None and state_root.is_dir():
        prior = sorted(state_root.glob('*/*/intake.json'))
    for path in (candidates + prior)[:MAX_REGISTRY_FILES]:
        is_prior = path in prior
        label = ('state:' + str(path.relative_to(state_root))) if is_prior else str(path.relative_to(root))
        row = {'path': label, 'sha256': None, 'status': 'read'}
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_REGISTRY_FILE_BYTES:
                row['status'] = 'skipped_not_bounded_regular_file'
            else:
                raw = path.read_bytes()
                row['sha256'] = hashlib.sha256(raw).hexdigest()
                document = json.loads(raw)
                found = []
                pending = [] if is_prior else [document]
                if is_prior and isinstance(document, dict) and isinstance(document.get('take_family_id'), str):
                    found.append((document['take_family_id'], (document.get('source') or {}).get('sha256')))
                while pending:
                    item = pending.pop()
                    if isinstance(item, dict):
                        if isinstance(item.get('take_family_id'), str):
                            found.append((item['take_family_id'], item.get('source_sha256')))
                        pending.extend(item.values())
                    elif isinstance(item, list):
                        pending.extend(item)
                for family, source in found:
                    entries.append({'take_family_id': family,
                                    'source_sha256': source if isinstance(source, str) else None,
                                    'basis': 'prior_intake' if is_prior else 'registry_file',
                                    'file': label,
                                    **({'intake_id': path.parent.name, 'intake_status': document.get('status')}
                                       if is_prior else {})})
        except (OSError, ValueError, UnicodeError, RecursionError):
            row['status'] = 'skipped_unreadable'
        files.append(row)
    truncated = len(candidates) + len(prior) > MAX_REGISTRY_FILES
    return {'files': files, 'entries': entries, 'truncated': truncated,
            'bounds': {'max_file_bytes': MAX_REGISTRY_FILE_BYTES, 'max_files': MAX_REGISTRY_FILES}}


def resolve_family(source_sha256: str, family_arg: str | None, registry: dict, *, allow_same_family_intake=False) -> tuple[str, str, dict]:
    if family_arg is not None:
        try:
            corpus.identifier(family_arg)
        except corpus.CorpusError as exc:
            raise IntakeRefusal('family_invalid', '--family must satisfy corpus.IDENTIFIER') from exc
        family, basis = family_arg, 'operator_supplied'
    else:
        family, basis = family_id_for(source_sha256), 'derived_v1'
    corpus.identifier(family)
    same_source = [entry for entry in registry['entries'] if entry['source_sha256'] == source_sha256]
    registered = [entry for entry in same_source if entry['basis'] != 'prior_intake']
    if registered:
        raise IntakeRefusal('source_already_registered',
                            'This source sha256 already belongs to a registered take family; it is not a new take',
                            families=sorted({entry['take_family_id'] for entry in registered}))
    prior_other_family = [entry for entry in same_source if entry['basis'] == 'prior_intake' and entry['take_family_id'] != family]
    if prior_other_family:
        raise IntakeRefusal('source_already_registered',
                            'A prior intake already bound this source to another take family',
                            families=sorted({entry['take_family_id'] for entry in prior_other_family}))
    clashes = [entry for entry in registry['entries'] if entry['take_family_id'] == family
               and entry['source_sha256'] != source_sha256]
    if clashes:
        raise IntakeRefusal('family_collision', 'The chosen take_family_id already exists with a different or unknown source',
                            family=family)
    prior_same = sorted({entry['intake_id'] for entry in same_source
                         if entry['basis'] == 'prior_intake' and entry['take_family_id'] == family})
    check = {'result': 'no_collision', 'registry_files': registry['files'], 'registry_truncated': registry['truncated'],
             'prior_intakes_same_source_and_family': prior_same}
    return family, basis, check


# --------------------------------------------------------------- corpus row

def corpus_row_draft(family: str, source_sha256: str, origin: str) -> dict:
    return {'schema_id': SCHEMA_ROW_DRAFT, 'schema_version': SCHEMA_VERSION,
            'split_status': 'pending_operator_choice',
            'row': {'id': f'{family}-take'[:80], 'take_family_id': family, 'split': None, 'origin': origin,
                    'source_sha256': source_sha256, 'artifact_sha256': source_sha256, 'parent_ids': [],
                    'augmentation_group_ids': [], 'manifest': None, 'annotation_refs': []},
            'row_schema': corpus_split_s1.SCHEMA,
            'note': 'A null split is not a valid corpus-split row by design; the operator chooses the split. '
                    'The lane never writes a corpus manifest.'}


def admissibility_check(draft: dict, root: Path, state_root: Path) -> dict:
    """validate_split on an in-memory copy with split 'unassigned' in state_root/.scratch (deleted)."""
    created = []
    probe_dir = state_root
    while not probe_dir.exists():
        created.append(probe_dir)
        probe_dir = probe_dir.parent
    scratch_parent = state_root / '.scratch'
    if not scratch_parent.exists():
        created.insert(0, scratch_parent)
    result = {'checked_split': 'unassigned', 'validator': 'corpus_split_s1.validate_split'}
    scratch = None
    try:
        scratch_parent.mkdir(parents=True, exist_ok=True)
        scratch = Path(tempfile.mkdtemp(prefix='row-', dir=scratch_parent))
        row = dict(draft['row'], split='unassigned')
        manifest = {'schema_id': corpus_split_s1.SCHEMA, 'schema_version': 1, 'corpus_id': 'take-intake-admissibility',
                    'revision': 1, 'coverage': 'sparse_or_unknown_no_negative_inference',
                    'approval_state': 'unreviewed', 'records': [row], 'context_refs': []}
        path = scratch / 'split.json'
        path.write_text(json.dumps(manifest, sort_keys=True))
        validated = corpus_split_s1.validate_split(path, root, summary=True)
        result.update(status='admissible_once_split_chosen', record_count=validated['record_count'],
                      group_count=validated['group_count'])
    except (corpus.CorpusError, OSError, ValueError) as exc:
        result.update(status='not_admissible', error=str(exc)[:200])
    finally:
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
        for directory in created:
            try:
                directory.rmdir()
            except OSError:
                pass
    return result


# ---------------------------------------------------------------- arguments

def validate_capture(interval, review, setup_flag: bool) -> dict | None:
    if interval is None:
        raise IntakeRefusal('capture_interval_required',
                            'run needs a reviewed per-take --capture-interval START END (review it on /sources/[id]/capture or with just review)')
    if not isinstance(review, str) or not review.strip() or len(review) > MAX_REVIEW_CHARS:
        raise IntakeRefusal('capture_review_required', '--capture-review must be non-empty text of at most 2000 characters')
    start, end = interval
    if (not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in interval)
            or start < 0 or not CAPTURE_MIN_SECONDS <= end - start <= CAPTURE_MAX_SECONDS):
        raise IntakeRefusal('capture_interval_invalid', 'capture interval needs finite START >= 0 and a 0.1-10 second duration')
    if start < SETUP_WINDOW_SECONDS[1] and not setup_flag:
        raise IntakeRefusal('capture_interval_in_setup_window',
                            'the first 5.0 s are setup (guitar/amp sounds, possible windup) and are never auto-confirmed; '
                            'pass --interval-reviewed-includes-setup only after reviewing this interval')
    if start < SETUP_WINDOW_SECONDS[1]:
        return {'start_seconds': float(start), 'setup_window_seconds': list(SETUP_WINDOW_SECONDS),
                'operator_flag': True, 'recorded_at': now(),
                'meaning': 'operator asserts the interval was reviewed; never a claim that it is noise-only'}
    return None


def resolve_state_root(value, root: Path = ROOT) -> Path:
    """Default ROOT/artifacts/take-intake; must resolve beneath ROOT/artifacts and not beneath artifacts/runs."""
    root_resolved = Path(root).resolve()
    path = Path(value).expanduser() if value else root_resolved / 'artifacts' / 'take-intake'
    if not path.is_absolute():
        path = root_resolved / path
    path = Path(os.path.abspath(path))
    probe, tail = path, []
    while not probe.exists() and probe != probe.parent:
        tail.insert(0, probe.name)
        probe = probe.parent
    resolved = probe.resolve().joinpath(*tail)
    base = (root_resolved / 'artifacts')
    base = base.resolve() if base.exists() else base
    if (not resolved.is_relative_to(base) or resolved == base
            or under_artifacts_runs(Path('artifacts') / resolved.relative_to(base))):
        raise IntakeRefusal('state_root_invalid', 'state root must resolve beneath ROOT/artifacts and not beneath artifacts/runs')
    return resolved


def arrangement_check(value, source_sha256: str, root: Path) -> dict | None:
    if value is None:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024:
            raise IntakeRefusal('arrangement_source_mismatch', 'arrangement reference must be a bounded regular file')
        raw = path.read_bytes()
        document = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise IntakeRefusal('arrangement_source_mismatch', 'arrangement reference is unreadable') from exc
    if not isinstance(document, dict) or document.get('source_sha256') != source_sha256:
        raise IntakeRefusal('arrangement_source_mismatch',
                            'arrangement reference is not bound to this source sha256 '
                            '(program/demo-arrangement.json belongs to the first take)')
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bound_source': 'matches_source_sha256',
            'first_take_reference': path.resolve() == (root / FIRST_TAKE_ARRANGEMENT).resolve()}


# --------------------------------------------------------------- stage argv

def stage_argv(name: str, v: dict) -> list[str]:
    """Exact argv for each reused entrypoint; ``v`` holds actual values or placeholders."""
    s = v['scripts']
    if name == 'demo':
        if v.get('demo_resume_id'):
            return [v['python'], f'{s}/run_demo.py', '--resume', v['demo_resume_id'], '--no-latest']
        argv = [v['python'], f'{s}/run_demo.py', v['source'], '--profile', PROFILE,
                '--capture-interval', v['capture_start'], v['capture_end'], '--capture-review', v['capture_review'],
                '--features', v['features'], '--backend', 'stdlib', '--no-latest']
        if v.get('bpm') is not None:
            argv += ['--bpm', v['bpm']]
        if v.get('analysis_python') is not None:
            argv += ['--analysis-python', v['analysis_python']]
        return argv
    if name == 'flags_triage':
        return [v['python'], f'{s}/flags_triage.py', v['run'], '--output', f"{v['intake']}/flags-triage.json"]
    if name == 'arrangement_reference':
        return [v['python'], f'{s}/arrangement_reference.py', v['arrangement'], '--run-dir', v['run'],
                '--output', f"{v['run']}/arrangement-reference"]
    if name == 'arrangement_markers':
        return [v['python'], f'{s}/arrangement_markers.py', v['run'], '--assessment', 'arrangement-reference/assessment.json',
                '--output', 'arrangement-markers.json']
    if name == 'phrase_anchor':
        argv = [v['python'], f'{s}/phrase_anchor.py', 'spans', '--clicks', f"{v['run']}/{v['clicks']}",
                '--arrangement', v['arrangement'], '--clicks-per-grid-period', v['clicks_per_grid_period'],
                '--anchor-seconds', v['anchor_seconds'], '--anchor-source', v['anchor_source'],
                '--output', v['anchor_output']]
        if v.get('assessment'):
            argv[-2:-2] = ['--assessment', v['assessment']]
        return argv
    if name == 'phrase_timing':
        return [v['python'], f'{s}/phrase_timing.py', '--analysis', f"{v['run']}/analysis.json",
                '--phrases', v['phrases_input'], '--output-root', f"{v['intake']}/phrase-timing", '--run-kind', 'real_take']
    if name == 'marked_video':
        argv = [v['python'], f'{s}/marked_video.py', '--run-dir', v['run'], '--output', f"{v['run']}/marked-preview"]
        if v.get('with_arrangement_markers'):
            return argv + ['--selection', 'all-review', '--arrangement-markers', 'arrangement-markers.json']
        return argv + ['--selection', 'phrase-review']
    if name == 'marked_compact':
        return [v['python'], f'{s}/marked_compact.py', v['run'], '--picture-preview', f"{v['run']}/marked-preview",
                '--arrangement-markers', 'arrangement-markers.json', '--output', f"{v['intake']}/marked-compact",
                '--timeout-seconds', '1200']
    if name == 'share_export':
        return [v['python'], f'{s}/share_export.py', v['share_input'], f"{v['intake']}/share/marked-share.mp4",
                '--height', '720', '--audio-kbps', '96', '--codec', 'h264', '--crf', '27', '--timeout-seconds', '900']
    raise ValueError(name)


PLAN_VALUES = {'python': '<PYTHON>', 'scripts': 'scripts', 'source': '<SOURCE>', 'capture_start': '<CAPTURE_START>',
               'capture_end': '<CAPTURE_END>', 'capture_review': '<CAPTURE_REVIEW>', 'run': '<RUN_DIR>',
               'intake': '<INTAKE_DIR>', 'arrangement': '<ARRANGEMENT>', 'clicks': '<CLICKS_SELECTOR>',
               'clicks_per_grid_period': '<CLICKS_PER_GRID_PERIOD>', 'anchor_seconds': '<ANCHOR_SECONDS>',
               'anchor_source': '<ANCHOR_SOURCE>',
               'anchor_output': 'artifacts/s2/phrase_anchor_riff/take-intake/<INTAKE_ID>/phrase-anchor-spans.json',
               'assessment': '<RUN_DIR>/arrangement-reference/assessment.json',
               'phrases_input': '<RUN_DIR>/arrangement-markers.json or <RUN_DIR>/phrases.json',
               'share_input': '<INTAKE_DIR>/marked-compact/marked-compact.mov or <RUN_DIR>/marked-preview/marked-video.mov'}

STAGE_DOC = {
    'demo': ('scripts/run_demo.py', 'always', 'FULLER per-take capture binding via media.py; media, export, rhythm, noise, tone, notes, phrases, (extended), dag, markers, report'),
    'flags_triage': ('scripts/flags_triage.py', 'demo produced flags.json', 'frozen ordering rule v1; no verdicts'),
    'arrangement_reference': ('scripts/arrangement_reference.py', '--arrangement supplied', 'reference must bind this source sha256'),
    'arrangement_markers': ('scripts/arrangement_markers.py', 'arrangement_reference completed', 'known limitation: the worker currently binds program/demo-arrangement.json only'),
    'phrase_anchor': ('scripts/phrase_anchor.py', '--arrangement, an operator anchor and extended clicks selection', 'projection only; adopted false'),
    'phrase_timing': ('scripts/phrase_timing.py', 'demo produced analysis.json and phrases.json', 'run-kind real_take: direction withheld_uncalibrated'),
    'marked_video': ('scripts/marked_video.py', 'demo export verified', 'uncertain review callouts; picture reencoded'),
    'marked_compact': ('scripts/marked_compact.py', 'arrangement_markers and marked_video completed', 'abstains arrangement_markers_required otherwise'),
    'share_export': ('scripts/share_export.py', 'marked_compact or marked_video completed', 'lossy sharing copy; master retained'),
    'packet': ('scripts/take_intake.py packet (inline)', 'always', 'evidence packet and TIN-5186 draft (not sent)'),
}


def plan_steps(settings: dict) -> list[dict]:
    steps = []
    has_ref = settings.get('arrangement') is not None
    has_anchor = settings.get('anchor_seconds') is not None
    extended = settings.get('features') == 'extended'
    values = dict(PLAN_VALUES, features=settings.get('features', 'base'),
                  bpm=None if settings.get('bpm') is None else '<BPM>',
                  analysis_python=None if settings.get('analysis_python') is None else '<ANALYSIS_PYTHON>')
    for index, name in enumerate(STAGE_NAMES, 1):
        entrypoint, condition, note = STAGE_DOC[name]
        if name == 'demo':
            disposition, reason = 'needs_operator_input', 'reviewed capture interval and review text are required'
        elif name in ('arrangement_reference', 'arrangement_markers'):
            disposition, reason = ('conditional', 'runs with the supplied reference') if has_ref else ('will_abstain', 'abstained_no_reference')
        elif name == 'phrase_anchor':
            if not has_ref:
                disposition, reason = 'will_abstain', 'abstained_no_reference'
            elif not has_anchor:
                disposition, reason = 'will_abstain', 'abstained_no_anchor'
            elif not extended:
                disposition, reason = 'will_abstain', 'abstained_clicks_not_selected'
            else:
                disposition, reason = 'conditional', 'runs when the extended clicks selection exists'
        elif name == 'marked_compact':
            disposition, reason = ('conditional', 'needs arrangement markers') if has_ref else ('will_abstain', 'abstained_arrangement_markers_required')
        else:
            disposition, reason = 'will_run', 'runs when its dependency completed'
        argv = None if name == 'packet' else stage_argv(name, values)
        steps.append({'index': index, 'name': name, 'entrypoint': entrypoint, 'argv': argv, 'cwd': '<ROOT>',
                      'timeout_seconds': STAGE_TIMEOUTS[name], 'condition': condition, 'disposition': disposition,
                      'reason': reason, 'note': note})
    return steps


def required_operator_inputs(settings: dict, source_id: str) -> dict:
    return {
        'capture_interval': {'required': True, 'value': None,
                             'review_surfaces': [f'/sources/{source_id}/capture (web route)', 'just review'],
                             'rule': 'reviewed per take; the first 5.0 s are setup and never auto-confirmed; '
                                     'starting before 5.0 s needs --interval-reviewed-includes-setup',
                             'bounds_seconds': [CAPTURE_MIN_SECONDS, CAPTURE_MAX_SECONDS]},
        'capture_review': {'required': True, 'value': None, 'max_chars': MAX_REVIEW_CHARS},
        'arrangement_reference': {'required': False, 'supplied': settings.get('arrangement') is not None,
                                  'rule': 'a new reference bound to this source sha256; program/demo-arrangement.json belongs to the first take and is refused'},
        'anchor_seconds': {'required': False, 'supplied': settings.get('anchor_seconds') is not None,
                           'requires': ['arrangement_reference', 'anchor_source', 'clicks_per_grid_period', 'features extended']},
        'bpm': {'required': False, 'supplied': settings.get('bpm') is not None,
                'meaning': 'approximate operator pulse; not an intended score'},
        'split': {'required': 'later', 'value': None, 'split_status': 'pending_operator_choice'},
    }


CLAIM_BOUNDARIES = [
    'Measurements, inferences and listening claims are kept distinct; every packet item carries a claim class.',
    'No note-correctness, missed-note or extra-note verdict without an approved reference.',
    'Phrase timing reports measured signed offsets only; direction is withheld_uncalibrated.',
    'Arrangement intent (including any click total) is intent, not an observed count.',
    'No default detector, profile or master is adopted; FULLER stays the existing default unchanged.',
    'The capture interval is operator-reviewed; no worker verifies it is noise-only.',
    'Protect ~32 Hz content: no high-pass, low cut or mains notch is added by this orchestrator.',
    'Real-take outputs stay private under ignored artifacts/ (V6); the TIN-5186 draft carries only non-media metadata.',
]


# --------------------------------------------------------------------- plan

def build_plan(source_value, *, family=None, arrangement=None, bpm=None, features='base', origin='real_recording',
               state_root=None, analysis_python=None, anchor_seconds=None, root: Path = ROOT,
               repo_root: Path | None = None) -> dict:
    if bpm is not None and (not math.isfinite(bpm) or not 20 <= bpm <= 400):
        raise IntakeRefusal('bpm_invalid', '--bpm must be finite and between 20 and 400')
    source, location = check_source(source_value, repo_root)
    probe = probe_summary(source)
    source_sha = run_demo.sha256(source)
    try:
        state_path = resolve_state_root(state_root, root)
    except IntakeRefusal:
        state_path = None
    registry = registry_entries(root, state_path)
    family_id, basis, collision = resolve_family(source_sha, family, registry)
    reference = arrangement_check(arrangement, source_sha, root)
    draft = corpus_row_draft(family_id, source_sha, origin)
    admissible = (admissibility_check(draft, root, state_path) if state_path is not None
                  else {'status': 'not_checked_state_root_invalid'})
    settings = {'arrangement': arrangement, 'bpm': bpm, 'features': features, 'analysis_python': analysis_python,
                'anchor_seconds': anchor_seconds}
    source_id = artifact_ids.source_id_for(source_sha)
    unknowns = json.loads(json.dumps(UNKNOWNS))
    unknowns['cfr_vfr_status']['value'] = probe['cfr_vfr_status']
    if bpm is not None:
        unknowns['operator_bpm'].update(value=bpm, reason='operator supplied; approximate pulse, not an intended score')
    if reference is not None:
        unknowns['arrangement_reference'].update(value={'sha256': reference['sha256']}, reason='operator supplied, bound to this source')
    return {
        'schema_id': SCHEMA_PLAN, 'schema_version': SCHEMA_VERSION, 'mode': 'read_only_plan',
        'source': {'sha256': source_sha, 'size_bytes': source.stat().st_size, 'source_id': source_id,
                   'display_name': source.name, 'location_check': location},
        'probe': probe,
        'take_family_id': family_id, 'family_basis': basis, 'collision_check': collision,
        'arrangement_reference': reference,
        'corpus_row_draft': draft, 'corpus_row_admissibility': admissible,
        'steps': plan_steps(settings),
        'required_operator_inputs': required_operator_inputs(settings, source_id),
        'unknowns': unknowns, 'claim_boundaries': CLAIM_BOUNDARIES,
        'writes': 'nothing (stdout only; a temporary admissibility file beneath <state-root>/.scratch is deleted)',
        'authority': AUTHORITY,
    }


# ---------------------------------------------------------------- execution

class Stage:
    """A stage definition: ``run(ctx)`` records one terminal entry; ``locations(ctx)`` are fresh-output paths."""

    def __init__(self, name, run, locations=None, timeout=None):
        self.name = name
        self.run = run
        self.locations = locations or (lambda ctx: [])
        self.timeout = timeout or STAGE_TIMEOUTS.get(name, 300)


class Context:
    def __init__(self, root: Path, state_root: Path, intake_dir: Path, state: dict, replay: dict,
                 scrubber: Scrubber, stages: list):
        self.root, self.state_root, self.intake_dir = root, state_root, intake_dir
        self.state, self.replay, self.scrubber, self.stages = state, replay, scrubber, stages

    # -- persistence
    def save(self):
        self.state['updated_at'] = now()
        clean = self.scrubber.deep(self.state)
        run_demo.atomic_json(self.intake_dir / 'intake.json', clean)

    def entry(self, name) -> dict:
        return self.state['stages'][name]

    def status(self, name):
        return self.state['stages'].get(name, {}).get('status')

    def ok(self, name) -> bool:
        return self.status(name) in ('completed', 'completed_with_stage_failures')

    # -- paths
    def run_dir(self) -> Path | None:
        relative = (self.state.get('run') or {}).get('dir')
        return self.root / relative if relative else None

    def resolve(self, selector: str) -> Path:
        scope, _, relative = selector.partition(':')
        if not relative or relative.startswith('/') or any(part in ('', '.', '..') for part in relative.split('/')):
            raise ValueError('unsafe selector')
        base = {'intake': self.intake_dir, 'run': self.run_dir(), 'root': self.root}.get(scope)
        if base is None:
            raise ValueError('selector scope unavailable: ' + scope)
        return base / relative

    def selector_for(self, path: Path) -> str:
        path = Path(os.path.abspath(path))
        run = self.run_dir()
        for scope, base in (('intake', self.intake_dir), ('run', run), ('root', self.root)):
            if base is not None and path.is_relative_to(base):
                return f'{scope}:{path.relative_to(base).as_posix()}'
        raise ValueError('path outside intake, run and root')

    def hash_outputs(self, selectors) -> dict:
        hashes = {}
        for selector in selectors:
            path = self.resolve(selector)
            if path.is_dir() and not path.is_symlink():
                for child in sorted(path.rglob('*')):
                    if child.is_file() and not child.is_symlink() and not any(part.startswith('.') for part in child.relative_to(path).parts):
                        hashes[self.selector_for(child)] = run_demo.sha256(child)
            elif path.is_file() and not path.is_symlink():
                hashes[selector] = run_demo.sha256(path)
        return hashes

    def values(self) -> dict:
        settings, replay = self.state['settings'], self.replay
        run = self.run_dir()
        return {'python': sys.executable, 'scripts': str(self.root / 'scripts'), 'source': replay['source_path'],
                'capture_start': repr(float(settings['capture_interval'][0])),
                'capture_end': repr(float(settings['capture_interval'][1])),
                'capture_review': replay['capture_review'], 'features': settings['features'],
                'bpm': None if settings.get('bpm') is None else repr(float(settings['bpm'])),
                'analysis_python': replay.get('analysis_python'),
                'run': str(run) if run else '<RUN_DIR_UNBOUND>', 'intake': str(self.intake_dir),
                'arrangement': replay.get('arrangement_path'),
                'clicks_per_grid_period': None if settings.get('clicks_per_grid_period') is None else str(settings['clicks_per_grid_period']),
                'anchor_seconds': None if settings.get('anchor_seconds') is None else repr(float(settings['anchor_seconds'])),
                'anchor_source': replay.get('anchor_source'),
                'anchor_output': str(self.root / 'artifacts/s2/phrase_anchor_riff/take-intake' / self.state['intake_id']
                                     / 'phrase-anchor-spans.json')}

    # -- terminal recorders
    def abstain(self, name, status, reason):
        self.state['stages'][name] = {'status': status, 'reason': reason, 'completed_at': now()}
        self.save()

    def skip(self, name, dependencies):
        self.state['stages'][name] = {'status': 'skipped_dependency_failed', 'dependencies': list(dependencies),
                                      'completed_at': now()}
        self.save()

    def execute(self, name, argv, timeout, *, on_poll=None) -> dict:
        """Run one owned child in a new session with a hard deadline; record a bounded scrubbed receipt."""
        entry = {'status': 'running', 'argv': list(argv), 'timeout_seconds': timeout, 'started_at': now(),
                 'orchestrator_pid': os.getpid(), 'child_pid': None}
        self.state['stages'][name] = entry
        self.save()
        environment = os.environ.copy()
        for variable in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS'):
            environment[variable] = '2'
        started = time.monotonic()
        timed_out = False
        with tempfile.TemporaryFile(dir=self.intake_dir) as out, tempfile.TemporaryFile(dir=self.intake_dir) as err:
            try:
                process = subprocess.Popen(argv, cwd=self.root, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                           start_new_session=True, env=environment)
            except OSError as exc:
                entry.update(status='failed', reason='failed_to_start: ' + type(exc).__name__, completed_at=now())
                self.save()
                return {'returncode': None, 'stdout': '', 'stderr': '', 'entry': entry}
            entry['child_pid'] = process.pid
            self.save()
            while True:
                try:
                    returncode = process.wait(timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if on_poll is not None:
                    on_poll()
                if time.monotonic() - started > timeout:
                    timed_out = True
                    entry['timeout_receipt'] = stop_owned_child(process)
                    returncode = process.returncode
                    break
            if on_poll is not None:
                on_poll()
            stdout, stderr = read_stream(out), read_stream(err)
        entry.update(exit_code=returncode, duration_seconds=round(time.monotonic() - started, 3), completed_at=now(),
                     stdout_tail=stdout[-TAIL_BYTES:], stderr_tail=stderr[-TAIL_BYTES:])
        if timed_out:
            entry['status'] = 'timed_out'
        elif returncode is not None and returncode < 0:
            entry['status'] = 'killed'
            entry['signal'] = -returncode
        elif returncode == 0:
            entry['status'] = 'completed'
        else:
            entry['status'] = 'failed'
            lines = [line.strip() for line in stderr.splitlines() if line.strip()]
            entry['reason'] = (lines[-1] if lines else f'exit code {returncode}')[:300]
        self.save()
        return {'returncode': returncode, 'stdout': stdout, 'stderr': stderr, 'entry': entry}

    def finish(self, name, outputs, *, consumed=None, extra=None):
        entry = self.state['stages'][name]
        try:
            entry['outputs'] = self.hash_outputs(outputs)
        except (OSError, ValueError) as exc:
            entry.update(status='failed', reason='output_hashing_failed: ' + type(exc).__name__)
        if consumed:
            entry['consumed_inputs'] = consumed
        if extra:
            entry.update(extra)
        self.save()


def read_stream(handle) -> str:
    handle.flush()
    size = handle.seek(0, os.SEEK_END)
    handle.seek(max(0, size - MAX_STDOUT_PARSE_BYTES))
    return handle.read().decode('utf-8', 'replace')


def stop_owned_child(process: subprocess.Popen) -> dict:
    """Deadline enforcement for a child this orchestrator started in its own session (R-N11)."""
    result, observed = 'already_exited', None
    try:
        observed = os.getpgid(process.pid)
        if observed == process.pid:
            os.killpg(observed, signal.SIGKILL)
            result = 'owned_process_group'
        elif process.poll() is None:
            process.kill()
            result = 'owned_child_only'
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        result += '_wait_timed_out'
    return {'actor': 'video-utils/take_intake', 'target_ownership': {'child_pid': process.pid, 'observed_pgid': observed,
            'created_by_this_orchestrator': True, 'new_session_requested': True},
            'reason': 'stage deadline exceeded', 'ruling': 'R-N11; ' + AUTHORITY, 'result': result}


def parse_json_output(text: str) -> dict | None:
    text = text.strip()
    for candidate in (text, text.splitlines()[-1] if text else ''):
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except ValueError:
            continue
    start = text.find('{')
    if start >= 0:
        try:
            value = json.loads(text[start:])
            return value if isinstance(value, dict) else None
        except ValueError:
            return None
    return None


# -------------------------------------------------------- demo invocation binding

def list_invocations(root: Path) -> list[str]:
    directory = root / 'artifacts' / 'demo-invocations'
    if not directory.is_dir():
        return []
    return sorted(entry.name for entry in os.scandir(directory)
                  if entry.is_dir(follow_symlinks=False) and run_demo.INVOCATION_ID_PATTERN.fullmatch(entry.name))[:10000]


def read_invocation_receipt(root: Path, invocation_id: str) -> dict | None:
    bootstrap = root / 'artifacts' / 'demo-invocations' / invocation_id / 'receipt.json'
    try:
        data = bounded_json(bootstrap, 2 * 1024 * 1024)
        if set(data) == {'schema_version', 'invocation_id', 'run_dir', 'receipt'}:
            data = bounded_json(Path(data['receipt']), 2 * 1024 * 1024)
        return data
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        return None


def bind_demo_invocation(root: Path, before: list[str], source_sha256: str, interval) -> str:
    """Exactly one new invocation whose resume_arguments match this intake; else demo_invocation_unbound."""
    known = set(before)
    candidates = []
    for name in list_invocations(root):
        if name in known:
            continue
        receipt = read_invocation_receipt(root, name)
        arguments = (receipt or {}).get('resume_arguments') or {}
        recorded = arguments.get('capture_interval')
        if (arguments.get('input_sha256') == source_sha256 and isinstance(recorded, list) and len(recorded) == 2
                and [float(x) for x in recorded] == [float(x) for x in interval]):
            candidates.append(name)
    if len(candidates) != 1:
        raise IntakeRefusal('demo_invocation_unbound',
                            f'expected exactly one new matching run_demo invocation, found {len(candidates)}',
                            candidates=len(candidates))
    return candidates[0]


# ------------------------------------------------------------ default stages

def demo_stage(ctx: Context):
    name = 'demo'
    demo = ctx.state.setdefault('demo', {'invocation_id': None, 'invocations_before': None})
    values = ctx.values()
    source_sha = ctx.state['source']['sha256']
    interval = ctx.state['settings']['capture_interval']
    if demo.get('invocation_id'):
        receipt = read_invocation_receipt(ctx.root, demo['invocation_id'])
        if receipt is not None and receipt.get('status') == 'completed_unreviewed':
            ctx.state['stages'][name] = {'status': 'running', 'adopted_terminal_invocation': True, 'started_at': now()}
            return record_demo(ctx, receipt, None)
        values['demo_resume_id'] = demo['invocation_id']
    else:
        demo['invocations_before'] = list_invocations(ctx.root)
    ctx.save()

    def poll():
        if not demo.get('invocation_id'):
            try:
                demo['invocation_id'] = bind_demo_invocation(ctx.root, demo['invocations_before'], source_sha, interval)
                demo['bound_at'] = now()
                ctx.save()
            except IntakeRefusal:
                pass

    result = ctx.execute(name, stage_argv(name, values), STAGE_TIMEOUTS[name], on_poll=poll)
    parsed = parse_json_output(result['stdout']) or {}
    if not demo.get('invocation_id') and isinstance(parsed.get('demo_receipt'), str):
        candidate = Path(parsed['demo_receipt']).parent.name
        if run_demo.INVOCATION_ID_PATTERN.fullmatch(candidate):
            demo['invocation_id'] = candidate
    receipt = read_invocation_receipt(ctx.root, demo['invocation_id']) if demo.get('invocation_id') else None
    return record_demo(ctx, receipt, result)


def record_demo(ctx: Context, receipt: dict | None, result: dict | None):
    entry = ctx.entry('demo')
    status = entry.get('status')
    if receipt is None:
        if status == 'completed':
            entry.update(status='failed', reason='run_demo receipt unbound or unreadable')
        ctx.save()
        return
    run_dir = receipt.get('run_dir')
    if isinstance(run_dir, str):
        path = Path(run_dir)
        runs = (ctx.root / 'artifacts' / 'runs').resolve()
        if path.is_absolute() and path.resolve().is_relative_to(runs):
            ctx.state['run'] = {'dir': path.resolve().relative_to(ctx.root.resolve()).as_posix(),
                                'manifest_sha256': (receipt.get('stages', {}).get('media', {}).get('artifacts') or {}).get('manifest.json')}
    receipt_status = receipt.get('status')
    entry['run_demo_status'] = receipt_status
    entry['run_demo_stage_status'] = {key: value.get('status') for key, value in (receipt.get('stages') or {}).items()
                                      if isinstance(value, dict)}
    entry['failed_run_demo_stages'] = receipt.get('failed_stages')
    if status in ('killed', 'timed_out'):
        pass
    elif receipt_status == 'completed_unreviewed' and receipt.get('report'):
        entry['status'] = 'completed'
    elif receipt_status == 'completed_with_stage_failures' and receipt.get('report'):
        entry['status'] = 'completed_with_stage_failures'
    else:
        entry['status'] = 'failed'
        entry.setdefault('reason', f'run_demo status {receipt_status}')
    recorded = {}
    for value in (receipt.get('stages') or {}).values():
        if isinstance(value, dict) and isinstance(value.get('artifacts'), dict):
            recorded.update({'run:' + relative: digest for relative, digest in value['artifacts'].items()})
    if ctx.run_dir() is None:
        return ctx.save()
    ctx.finish('demo', sorted(recorded), extra={'invocation_id': ctx.state['demo'].get('invocation_id'),
                                                'selected_evidence': receipt.get('selected_evidence')})
    drift = sorted(selector for selector, digest in recorded.items() if entry.get('outputs', {}).get(selector) != digest)
    if drift:
        entry.update(status='failed', reason='run_artifact_hash_drift', drifted_outputs=drift)
        ctx.save()


def flags_triage_stage(ctx: Context):
    run = ctx.run_dir()
    if not ctx.ok('demo') or run is None or not (run / 'flags.json').is_file():
        return ctx.skip('flags_triage', ['demo'])
    result = ctx.execute('flags_triage', stage_argv('flags_triage', ctx.values()), STAGE_TIMEOUTS['flags_triage'])
    if result['entry']['status'] == 'completed':
        ctx.finish('flags_triage', ['intake:flags-triage.json'], consumed=ctx.hash_outputs(['run:flags.json', 'run:manifest.json']))


def arrangement_reference_stage(ctx: Context):
    if ctx.replay.get('arrangement_path') is None:
        return ctx.abstain('arrangement_reference', 'abstained_no_reference', 'no source-bound arrangement reference supplied')
    if not ctx.ok('demo'):
        return ctx.skip('arrangement_reference', ['demo'])
    result = ctx.execute('arrangement_reference', stage_argv('arrangement_reference', ctx.values()),
                         STAGE_TIMEOUTS['arrangement_reference'])
    if result['entry']['status'] == 'completed':
        ctx.finish('arrangement_reference', ['run:arrangement-reference'])


def arrangement_markers_stage(ctx: Context):
    if ctx.replay.get('arrangement_path') is None:
        return ctx.abstain('arrangement_markers', 'abstained_no_reference', 'no source-bound arrangement reference supplied')
    if not ctx.ok('arrangement_reference'):
        return ctx.skip('arrangement_markers', ['arrangement_reference'])
    result = ctx.execute('arrangement_markers', stage_argv('arrangement_markers', ctx.values()),
                         STAGE_TIMEOUTS['arrangement_markers'])
    if result['entry']['status'] == 'completed':
        ctx.finish('arrangement_markers', ['run:arrangement-markers.json'])


def phrase_anchor_stage(ctx: Context):
    settings = ctx.state['settings']
    if ctx.replay.get('arrangement_path') is None:
        return ctx.abstain('phrase_anchor', 'abstained_no_reference', 'no source-bound arrangement reference supplied')
    if settings.get('anchor_seconds') is None:
        return ctx.abstain('phrase_anchor', 'abstained_no_anchor', 'no operator anchor supplied')
    selected = (ctx.entry('demo').get('selected_evidence') or {}).get('clicks') if ctx.ok('demo') else None
    if settings.get('features') != 'extended' or not selected:
        return ctx.abstain('phrase_anchor', 'abstained_clicks_not_selected', 'phrase_anchor needs an extended clicks selection')
    values = ctx.values()
    values['clicks'] = selected['selector']
    if ctx.ok('arrangement_reference'):
        values['assessment'] = str(ctx.run_dir() / 'arrangement-reference' / 'assessment.json')
    result = ctx.execute('phrase_anchor', stage_argv('phrase_anchor', values), STAGE_TIMEOUTS['phrase_anchor'])
    if result['entry']['status'] == 'completed':
        ctx.finish('phrase_anchor', [ctx.selector_for(Path(values['anchor_output']))], extra={'adopted': False})


def phrase_timing_stage(ctx: Context):
    run = ctx.run_dir()
    if not ctx.ok('demo') or run is None or not (run / 'analysis.json').is_file() or not (run / 'phrases.json').is_file():
        return ctx.skip('phrase_timing', ['demo'])
    values = ctx.values()
    basis = 'arrangement-markers.json' if ctx.ok('arrangement_markers') else 'phrases.json'
    values['phrases_input'] = str(run / basis)
    result = ctx.execute('phrase_timing', stage_argv('phrase_timing', values), STAGE_TIMEOUTS['phrase_timing'])
    if result['entry']['status'] == 'completed':
        parsed = parse_json_output(result['stdout']) or {}
        output = parsed.get('phrase_timing_json')
        if not isinstance(output, str):
            ctx.entry('phrase_timing').update(status='failed', reason='phrase_timing did not name its output')
            return ctx.save()
        ctx.finish('phrase_timing', [ctx.selector_for(Path(output))], extra={'phrase_input': 'run:' + basis},
                   consumed=ctx.hash_outputs(['run:analysis.json', 'run:' + basis]))


def marked_video_stage(ctx: Context):
    run = ctx.run_dir()
    if (not ctx.ok('demo') or run is None or not (run / 'export' / 'outcome.json').is_file()
            or not (run / 'export' / 'cleaned-video.mov').is_file()):
        return ctx.skip('marked_video', ['demo'])
    values = ctx.values()
    values['with_arrangement_markers'] = ctx.ok('arrangement_markers')
    result = ctx.execute('marked_video', stage_argv('marked_video', values), STAGE_TIMEOUTS['marked_video'])
    if result['entry']['status'] == 'completed':
        ctx.finish('marked_video', ['run:marked-preview'],
                   consumed=ctx.hash_outputs(['run:manifest.json', 'run:dag.json', 'run:flags.json', 'run:markers.json',
                                              'run:export/outcome.json', 'run:export/cleaned-video.mov']))


def marked_compact_stage(ctx: Context):
    if not ctx.ok('arrangement_markers'):
        return ctx.abstain('marked_compact', 'abstained_arrangement_markers_required',
                           'marked_compact needs verified arrangement markers for this take')
    if not ctx.ok('marked_video'):
        return ctx.skip('marked_compact', ['marked_video'])
    result = ctx.execute('marked_compact', stage_argv('marked_compact', ctx.values()), STAGE_TIMEOUTS['marked_compact'])
    if result['entry']['status'] == 'completed':
        ctx.finish('marked_compact', ['intake:marked-compact'])


def share_export_stage(ctx: Context):
    values = ctx.values()
    if ctx.ok('marked_compact'):
        values['share_input'] = str(ctx.intake_dir / 'marked-compact' / 'marked-compact.mov')
    elif ctx.ok('marked_video'):
        values['share_input'] = str(ctx.run_dir() / 'marked-preview' / 'marked-video.mov')
    else:
        return ctx.skip('share_export', ['marked_compact', 'marked_video'])
    (ctx.intake_dir / 'share').mkdir(exist_ok=True)
    result = ctx.execute('share_export', stage_argv('share_export', values), STAGE_TIMEOUTS['share_export'])
    if result['entry']['status'] == 'completed':
        share_input = ctx.selector_for(Path(values['share_input']))
        ctx.finish('share_export', ['intake:share/marked-share.mp4', 'intake:share/marked-share.mp4.receipt.json'],
                   extra={'share_input': share_input}, consumed=ctx.hash_outputs([share_input]))


def packet_stage(ctx: Context):
    ctx.state['stages']['packet'] = {'status': 'completed', 'started_at': now(), 'inline': True}
    ctx.state['status'] = intake_status(ctx.state)
    ctx.save()
    try:
        write_packet(ctx.intake_dir, root=ctx.root)
        ctx.finish('packet', ['intake:evidence-packet.json', 'intake:tin-5186-message-draft.json'])
        ctx.entry('packet')['completed_at'] = now()
    except (OSError, ValueError, KeyError, TypeError, IntakeRefusal) as exc:
        ctx.entry('packet').update(status='failed', reason=type(exc).__name__ + ': ' + str(exc)[:300])
    ctx.save()


DEFAULT_STAGES = [
    Stage('demo', demo_stage),
    Stage('flags_triage', flags_triage_stage, lambda ctx: ['intake:flags-triage.json']),
    Stage('arrangement_reference', arrangement_reference_stage,
          lambda ctx: ['run:arrangement-reference'] if ctx.run_dir() else []),
    Stage('arrangement_markers', arrangement_markers_stage,
          lambda ctx: ['run:arrangement-markers.json'] if ctx.run_dir() else []),
    Stage('phrase_anchor', phrase_anchor_stage,
          lambda ctx: [f"root:artifacts/s2/phrase_anchor_riff/take-intake/{ctx.state['intake_id']}/phrase-anchor-spans.json"]),
    Stage('phrase_timing', phrase_timing_stage, lambda ctx: ['intake:phrase-timing']),
    Stage('marked_video', marked_video_stage, lambda ctx: ['run:marked-preview'] if ctx.run_dir() else []),
    Stage('marked_compact', marked_compact_stage, lambda ctx: ['intake:marked-compact']),
    Stage('share_export', share_export_stage, lambda ctx: ['intake:share']),
    Stage('packet', packet_stage, lambda ctx: []),
]


def intake_status(state: dict) -> str:
    statuses = {name: (entry or {}).get('status') for name, entry in state['stages'].items()}
    considered = {name: status for name, status in statuses.items() if name != 'packet' or status not in (None, 'pending')}
    if state.get('failure') == 'source_changed':
        return 'failed'
    demo = considered.get('demo')
    if demo not in ('completed', 'completed_with_stage_failures') and 'demo' in considered:
        return 'failed'
    values = set(considered.values())
    if values & {'failed', 'killed', 'timed_out', 'skipped_dependency_failed', 'running', 'pending', None,
                 'completed_with_stage_failures'}:
        return 'partial'
    if any(str(value).startswith('abstained') for value in values):
        return 'completed_with_abstentions'
    return 'completed'


# -------------------------------------------------------------- lock & state

def check_lock(intake_dir: Path):
    """Read-only: refuse intake_locked when the recorded lock PID is alive (signal-0 inspection only)."""
    lock = intake_dir / '.lock'
    if not (lock.exists() or lock.is_symlink()):
        return None
    try:
        prior = bounded_json(lock, 4096).get('pid')
    except (OSError, ValueError) as exc:
        raise IntakeRefusal('intake_locked', 'intake lock exists but is unreadable') from exc
    if run_demo.pid_alive(prior):
        raise IntakeRefusal('intake_locked', f'intake lock held by live PID {prior} (signal-0 inspection only)')
    return prior


def acquire_lock(intake_dir: Path) -> dict:
    lock = intake_dir / '.lock'
    payload = json.dumps({'pid': os.getpid(), 'acquired_at': now()}).encode()
    prior = check_lock(intake_dir)
    if lock.exists() or lock.is_symlink():
        staging = intake_dir / f'.lock.{uuid.uuid4().hex}'
        staging.write_bytes(payload)
        staging.replace(lock)
        return {'status': 'stale_taken_over', 'prior_pid': prior,
                'receipt': {'actor': 'video-utils/take_intake', 'target': 'own recorded intake lock',
                            'reason': 'recorded orchestrator PID no longer alive', 'ruling': 'R-N11',
                            'result': 'lock replaced; no signal sent to any process'}}
    descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as handle:
        handle.write(payload)
    return {'status': 'acquired', 'prior_pid': None}


def release_lock(intake_dir: Path):
    lock = intake_dir / '.lock'
    try:
        if bounded_json(lock, 4096).get('pid') == os.getpid():
            lock.unlink()
    except (OSError, ValueError):
        pass


def displace(ctx: Context, stage: Stage, entry: dict | None, resume_index: int):
    """Move (never delete) prior outputs and fresh-output locations aside before a rerun."""
    moved = {}
    if stage.name == 'demo':
        return moved  # run_demo --resume owns its run directory and displacement (ROBUSTNESS_S2)
    selectors = list((entry or {}).get('outputs') or {}) + list(stage.locations(ctx))
    target_root = ctx.intake_dir / f'resume-{resume_index}' / 'displaced'
    for selector in dict.fromkeys(selectors):
        try:
            path = ctx.resolve(selector)
        except ValueError:
            continue
        if not (path.exists() or path.is_symlink()):
            continue
        scope, _, relative = selector.partition(':')
        target = target_root / scope / relative
        if target.exists():
            target = target.with_name(target.name + '.' + uuid.uuid4().hex[:6])
        target.parent.mkdir(parents=True, exist_ok=True)
        os.rename(path, target)
        moved[selector] = ctx.selector_for(target)
    return moved


def verify_outputs(ctx: Context, entry: dict) -> str | None:
    for selector, digest in (entry.get('outputs') or {}).items():
        try:
            path = ctx.resolve(selector)
        except ValueError:
            return 'output_unresolvable'
        if not path.is_file() or path.is_symlink():
            return 'output_missing'
        if run_demo.sha256(path) != digest:
            return 'output_hash_mismatch'
    return None


def check_source_identity(ctx: Context, phase: str) -> bool:
    path = Path(ctx.replay['source_path'])
    expected = ctx.state['source']['identity']
    try:
        observed = file_identity(path) if path.is_file() and not path.is_symlink() else None
    except OSError:
        observed = None
    unchanged = observed == expected
    ctx.state.setdefault('source_checks', []).append({'phase': phase, 'at': now(), 'unchanged': unchanged})
    if not unchanged:
        ctx.state['failure'] = 'source_changed'
    ctx.save()
    return unchanged


def drive(ctx: Context, *, resume_index: int | None = None) -> int:
    history = None
    if resume_index is not None:
        history = ctx.state['resume_history'][-1]
    invalidated = False
    for stage in ctx.stages:
        entry = ctx.state['stages'].get(stage.name)
        status = (entry or {}).get('status')
        if history is not None and not invalidated and stage.name != 'packet':
            if status in SUCCESS_STATUSES:
                problem = verify_outputs(ctx, entry)
                if problem is None:
                    history['skipped_stages'].append(stage.name)
                    continue
                history['invalidated'][stage.name] = problem
            else:
                history['rerun_reasons'][stage.name] = status or 'missing'
            invalidated = True
        if history is not None and stage.name != 'packet':
            moved = displace(ctx, stage, entry, resume_index)
            if moved:
                history['displaced'].update(moved)
            history['rerun_stages'].append(stage.name)
            ctx.state['stages'][stage.name] = {'status': 'pending', 'superseded_status': status}
            ctx.save()
        if stage.name == 'packet' and not check_source_identity(ctx, 'after_last_stage'):
            ctx.state['stages']['packet'] = {'status': 'failed', 'reason': 'source_changed'}
            ctx.state['status'] = 'failed'
            ctx.save()
            continue
        stage.run(ctx)
    ctx.state['status'] = intake_status(ctx.state)
    ctx.state['completed_at'] = now()
    ctx.save()
    return 0 if ctx.state['status'] in ('completed', 'completed_with_abstentions') else 1


def new_intake_id() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:12]


def run_intake(source_value, *, capture_interval=None, capture_review=None, interval_reviewed_includes_setup=False,
               family=None, arrangement=None, anchor_seconds=None, anchor_source=None, clicks_per_grid_period=None,
               bpm=None, features='base', analysis_python=None, origin='real_recording', state_root=None,
               root: Path = ROOT, repo_root: Path | None = None, stages=None) -> tuple[int, dict]:
    # 1. argument refusals (nothing written)
    override = validate_capture(capture_interval, capture_review, interval_reviewed_includes_setup)
    if anchor_seconds is not None and arrangement is None:
        raise IntakeRefusal('anchor_requires_arrangement', '--anchor-seconds needs --arrangement')
    if anchor_seconds is not None and (not anchor_source or clicks_per_grid_period not in (1, 2) or not math.isfinite(anchor_seconds)):
        raise IntakeRefusal('anchor_inputs_incomplete', '--anchor-seconds needs --anchor-source and --clicks-per-grid-period 1|2')
    if bpm is not None and (not math.isfinite(bpm) or not 20 <= bpm <= 400):
        raise IntakeRefusal('bpm_invalid', '--bpm must be finite and between 20 and 400')
    if features not in ('base', 'extended') or origin not in ('real_recording', 'synthetic_fixture'):
        raise IntakeRefusal('settings_invalid', 'features must be base|extended and origin real_recording|synthetic_fixture')
    # 2. source refusals
    source, location = check_source(source_value, repo_root)
    probe = probe_summary(source)
    extent = audio_extent_seconds(probe)
    if extent is not None and capture_interval[1] > extent:
        raise IntakeRefusal('capture_interval_outside_source', 'capture interval ends beyond the probed audio duration')
    identity = file_identity(source)
    # 3. family
    try:
        candidate_root = resolve_state_root(state_root, root)
    except IntakeRefusal:
        candidate_root = None
    registry = registry_entries(root, candidate_root)
    family_id, basis, collision = resolve_family(identity['sha256'], family, registry)
    reference = arrangement_check(arrangement, identity['sha256'], root)
    # 4. state root
    state_path = resolve_state_root(state_root, root)
    STATE_ROOT_HINT['path'] = state_path
    if collision['prior_intakes_same_source_and_family']:
        raise IntakeRefusal('intake_exists', 'an intake for this source and family already exists; use run --resume INTAKE_ID '
                            'or an explicit new --family', intake_ids=collision['prior_intakes_same_source_and_family'])
    intake_id = new_intake_id()
    intake_dir = state_path / family_id / intake_id
    intake_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    lock = acquire_lock(intake_dir)
    replay = {'schema_id': SCHEMA_REPLAY, 'schema_version': SCHEMA_VERSION, 'scope': 'local only; never copied into the packet or draft',
              'source_path': str(source), 'capture_review': capture_review, 'analysis_python': analysis_python,
              'arrangement_path': None if arrangement is None else str((Path(arrangement) if Path(arrangement).is_absolute() else root / arrangement).resolve()),
              'anchor_source': anchor_source}
    run_demo.atomic_json(intake_dir / 'replay-arguments.local.json', replay)
    unknowns = json.loads(json.dumps(UNKNOWNS))
    unknowns['capture_interval_setup_override']['value'] = override
    unknowns['cfr_vfr_status']['value'] = probe['cfr_vfr_status']
    if bpm is not None:
        unknowns['operator_bpm'].update(value=bpm, reason='operator supplied; approximate pulse, not an intended score')
    if reference is not None:
        unknowns['arrangement_reference'].update(value={'sha256': reference['sha256']}, reason='operator supplied, bound to this source')
    draft = corpus_row_draft(family_id, identity['sha256'], origin)
    state = {
        'schema_id': SCHEMA_STATE, 'schema_version': SCHEMA_VERSION, 'intake_id': intake_id,
        'take_family_id': family_id, 'family_basis': basis, 'origin': origin, 'status': 'running',
        'created_at': now(), 'authority': AUTHORITY,
        'source': {'sha256': identity['sha256'], 'identity': identity, 'source_id': artifact_ids.source_id_for(identity['sha256']),
                   'display_name': source.name, 'location_check': location},
        'probe': probe,
        'settings': {'profile': PROFILE, 'capture_interval': [float(capture_interval[0]), float(capture_interval[1])],
                     'capture_review_sha256': hashlib.sha256(capture_review.encode('utf-8')).hexdigest(),
                     'interval_reviewed_includes_setup': bool(interval_reviewed_includes_setup),
                     'features': features, 'bpm': bpm, 'backend': 'stdlib',
                     'analysis_python_supplied': analysis_python is not None,
                     'arrangement_reference': reference, 'anchor_seconds': anchor_seconds,
                     'anchor_source_supplied': anchor_source is not None, 'clicks_per_grid_period': clicks_per_grid_period},
        'capture_interval_setup_override': override,
        'collision_check': {key: value for key, value in collision.items() if key != 'registry_files'},
        'registry_files_read': len(collision['registry_files']),
        'corpus_row_draft': draft,
        'unknowns': unknowns,
        'stage_order': [stage.name for stage in (stages or DEFAULT_STAGES)],
        'stages': {stage.name: {'status': 'pending'} for stage in (stages or DEFAULT_STAGES)},
        'orchestrator': {'pid': os.getpid(), 'started_at': now(), 'lock': lock},
        'resume_history': [], 'source_checks': [],
        'run': None,
    }
    ctx = Context(root, state_path, intake_dir, state, replay, Scrubber(root, source), stages or DEFAULT_STAGES)
    try:
        ctx.save()
        if not check_source_identity(ctx, 'before_first_stage'):
            state['status'] = 'failed'
            ctx.save()
            return 1, state
        code = drive(ctx)
        return code, ctx.state
    finally:
        release_lock(intake_dir)


def locate_intake(state_root: Path, intake_id: str) -> Path:
    if not isinstance(intake_id, str) or not INTAKE_ID_PATTERN.fullmatch(intake_id):
        raise IntakeRefusal('intake_not_found', 'INTAKE_ID must match YYYYMMDDTHHMMSSZ-<12 hex>')
    matches = [path for path in sorted(state_root.glob(f'*/{intake_id}')) if (path / 'intake.json').is_file()]
    if len(matches) != 1:
        raise IntakeRefusal('intake_not_found', f'expected one intake directory for {intake_id}, found {len(matches)}')
    return matches[0]


def resume_intake(intake_id: str, *, state_root=None, root: Path = ROOT, stages=None) -> tuple[int, dict]:
    state_path = resolve_state_root(state_root, root)
    STATE_ROOT_HINT['path'] = state_path
    intake_dir = locate_intake(state_path, intake_id)
    check_lock(intake_dir)
    state = bounded_json(intake_dir / 'intake.json')
    if state.get('schema_id') != SCHEMA_STATE:
        raise IntakeRefusal('not_an_intake_run_dir', 'intake.json has an unexpected schema')
    replay = bounded_json(intake_dir / 'replay-arguments.local.json')
    stage_list = stages or DEFAULT_STAGES
    if [stage.name for stage in stage_list] != state.get('stage_order'):
        raise IntakeRefusal('resume_settings_conflict', 'recorded stage order differs from this orchestrator')
    for name, entry in state['stages'].items():
        child = (entry or {}).get('child_pid')
        if (entry or {}).get('status') == 'running' and run_demo.group_alive(child):
            raise IntakeRefusal('prior_stage_worker_alive', f'stage {name} worker group {child} is still alive; no signal was sent')
    lock = acquire_lock(intake_dir)
    source = Path(replay['source_path'])
    ctx = Context(root, state_path, intake_dir, state, replay, Scrubber(root, source), stage_list)
    try:
        prior = state.get('orchestrator')
        index = len(state.get('resume_history') or []) + 1
        state.setdefault('resume_history', []).append({
            'resume_index': index, 'resumed_at': now(), 'orchestrator_pid': os.getpid(), 'prior_orchestrator': prior,
            'prior_status': state.get('status'), 'lock': lock, 'skipped_stages': [], 'rerun_stages': [],
            'rerun_reasons': {}, 'invalidated': {}, 'displaced': {}})
        state['orchestrator'] = {'pid': os.getpid(), 'started_at': now(), 'lock': lock}
        state['status'] = 'running'
        state.pop('failure', None)
        if not check_source_identity(ctx, f'resume_{index}'):
            state['status'] = 'failed'
            ctx.save()
            raise IntakeRefusal('source_changed', 'SOURCE sha256, size or mtime_ns changed since the intake started')
        demo = state.get('demo') or {}
        demo_entry = state['stages'].get('demo') or {}
        if (stage_list is DEFAULT_STAGES and demo_entry.get('status') not in SUCCESS_STATUSES
                and demo_entry.get('status') != 'pending' and not demo.get('invocation_id')):
            demo['invocation_id'] = bind_demo_invocation(root, demo.get('invocations_before') or [], state['source']['sha256'],
                                                         state['settings']['capture_interval'])
            state['demo'] = demo
        code = drive(ctx, resume_index=index)
        return code, ctx.state
    finally:
        release_lock(intake_dir)


# ------------------------------------------------------------------- packet

def read_run_json(run: Path | None, relative: str) -> dict | None:
    if run is None:
        return None
    path = run / relative
    try:
        return bounded_json(path, 64 * 1024 * 1024) if path.is_file() else None
    except (OSError, ValueError, UnicodeError):
        return None


def ffmpeg_commands(document) -> list[list[str]]:
    found, pending = [], [document]
    while pending:
        item = pending.pop()
        if isinstance(item, list):
            if item and all(isinstance(x, str) for x in item) and Path(item[0]).name in ('ffmpeg', 'ffmpeg.exe'):
                found.append(item)
            else:
                pending.extend(item)
        elif isinstance(item, dict):
            pending.extend(item.values())
    return found


def low_register_guard(documents: list) -> dict:
    graphs = []
    for document in documents:
        for command in ffmpeg_commands(document):
            for index, token in enumerate(command[:-1]):
                if token in ('-af', '-filter_complex', '-filter:a', '-vf', '-lavfi'):
                    graphs.append(command[index + 1])
    violations = []
    for graph in graphs:
        for label, pattern in LOW_REGISTER_PATTERNS:
            if pattern.search(graph):
                violations.append(label)
        for match in LOWPASS.finditer(graph):
            if number(match.group(1)) is not None and float(match.group(1)) < 60:
                violations.append('lowpass_below_60_hz')
    return {'filter_graphs_inspected': len(graphs), 'violations': len(violations), 'violation_kinds': sorted(set(violations)),
            'patterns': [label for label, _ in LOW_REGISTER_PATTERNS] + ['lowpass_below_60_hz'],
            'scope': 'static text inspection of recorded FFmpeg filter graphs; not a spectral or listening check'}


def tool_versions(root: Path, state: dict) -> dict:
    head = git(['rev-parse', 'HEAD'], root)
    dirty = git(['status', '--porcelain', '--untracked-files=no'], root)
    scripts = {}
    for name in ('take_intake.py', 'run_demo.py', 'media.py', 'flags_triage.py', 'arrangement_reference.py',
                 'arrangement_markers.py', 'phrase_anchor.py', 'phrase_timing.py', 'marked_video.py',
                 'marked_compact.py', 'share_export.py', 'apply_capture_profile.py'):
        path = root / 'scripts' / name
        scripts[name] = run_demo.sha256(path) if path.is_file() else None
    binaries = {}
    for name in ('ffmpeg', 'ffprobe'):
        executable = shutil.which(os.environ.get(name.upper(), name))
        row = {'version_line': None, 'binary_sha256': None}
        if executable:
            try:
                result = subprocess.run([executable, '-version'], stdin=subprocess.DEVNULL, capture_output=True,
                                        text=True, timeout=30, check=False)
                row['version_line'] = (result.stdout.splitlines() or [None])[0]
                row['binary_sha256'] = run_demo.sha256(Path(executable).resolve())
            except (OSError, subprocess.TimeoutExpired):
                pass
        binaries[name] = row
    profile = root / 'profiles' / f'{PROFILE}.json'
    return {'repository': {'head': head.stdout.strip() if head is not None and head.returncode == 0 else None,
                           'tracked_dirty': bool(dirty.stdout.strip()) if dirty is not None and dirty.returncode == 0 else None},
            'scripts_sha256': scripts, 'python_version': platform.python_version(), **binaries,
            'profile': {'name': PROFILE, 'sha256': run_demo.sha256(profile) if profile.is_file() else None}}


def signal_versions(run: Path | None, manifest: dict | None, state: dict, intake_dir: Path) -> list[dict]:
    rows = []
    current = ((manifest or {}).get('output_sha256') or {}).get('denoised.wav')
    for relative in ('analysis.json', 'noise.json', 'tone.json', 'notes.json', 'phrases.json'):
        document = read_run_json(run, relative)
        if document is None:
            rows.append({'artifact': 'run:' + relative, 'declared_analyzed_input_sha256': None, 'status': 'artifact_absent'})
            continue
        declared = (document.get('lineage') or {}).get('input_sha256') or (document.get('source') or {}).get('sha256')
        rows.append({'artifact': 'run:' + relative, 'declared_analyzed_input_sha256': declared,
                     'declared_signal': 'denoised.wav', 'current_sha256': current,
                     'status': 'current' if declared and declared == current else 'stale_invalidated' if declared else 'undeclared'})
    timing_selector = next(iter((state['stages'].get('phrase_timing') or {}).get('outputs') or {}), None)
    if timing_selector:
        try:
            document = bounded_json(intake_dir / timing_selector.partition(':')[2], 16 * 1024 * 1024)
            declared = (document.get('inputs') or {}).get('analyzed_input_sha256')
            rows.append({'artifact': timing_selector, 'declared_analyzed_input_sha256': declared, 'declared_signal': 'denoised.wav',
                         'current_sha256': current,
                         'status': 'undeclared' if not declared else 'current' if declared == current else 'stale_invalidated'})
        except (OSError, ValueError):
            pass
    triage = intake_dir / 'flags-triage.json'
    if triage.is_file() and run is not None and (run / 'manifest.json').is_file():
        document = bounded_json(triage, 16 * 1024 * 1024)
        manifest_hash = run_demo.sha256(run / 'manifest.json')
        rows.append({'artifact': 'intake:flags-triage.json', 'declared_manifest_sha256': document.get('manifest_sha256'),
                     'current_sha256': manifest_hash,
                     'status': 'current' if document.get('manifest_sha256') == manifest_hash else 'stale_invalidated'})
    return rows


def build_packet(intake_dir: Path, root: Path = ROOT) -> tuple[dict, dict]:
    intake_dir = Path(os.path.abspath(intake_dir))
    state_path = intake_dir / 'intake.json'
    if not state_path.is_file():
        raise IntakeRefusal('not_an_intake_run_dir', 'RUN_DIR is not an intake run directory (no intake.json); '
                            'pipeline artifacts/runs directories are never guessed into an intake')
    state = bounded_json(state_path)
    if state.get('schema_id') != SCHEMA_STATE:
        raise IntakeRefusal('not_an_intake_run_dir', 'intake.json has an unexpected schema')
    run = root / state['run']['dir'] if state.get('run') and state['run'].get('dir') else None
    manifest = read_run_json(run, 'manifest.json')
    manifest_binding = None
    if run is not None and (run / 'manifest.json').is_file():
        observed = run_demo.sha256(run / 'manifest.json')
        manifest_binding = {'recorded_sha256': state['run'].get('manifest_sha256'), 'observed_sha256': observed,
                            'status': 'bound' if observed == state['run'].get('manifest_sha256') else 'run_manifest_drift'}
    stages = state['stages']
    counts = {}
    for entry in stages.values():
        status = (entry or {}).get('status') or 'pending'
        counts[status] = counts.get(status, 0) + 1
    completed = sum(1 for entry in stages.values() if (entry or {}).get('status') in ('completed', 'completed_with_stage_failures'))
    abstained = sum(1 for entry in stages.values() if str((entry or {}).get('status')).startswith('abstained'))
    failed = sum(1 for entry in stages.values() if (entry or {}).get('status') in ('failed', 'killed', 'timed_out'))
    skipped = sum(1 for entry in stages.values() if (entry or {}).get('status') == 'skipped_dependency_failed')
    table = [{'index': index, 'name': name, 'status': (stages.get(name) or {}).get('status'),
              'reason': (stages.get(name) or {}).get('reason'), 'exit_code': (stages.get(name) or {}).get('exit_code'),
              'duration_seconds': (stages.get(name) or {}).get('duration_seconds')}
             for index, name in enumerate(state['stage_order'], 1)]
    export = read_run_json(run, 'export/outcome.json') or {}
    verification = export.get('verification') or {}
    final_loudness = export.get('final_audio_loudness') or {}
    timing_doc = None
    timing_selector = next(iter((stages.get('phrase_timing') or {}).get('outputs') or {}), None)
    if timing_selector:
        try:
            timing_doc = bounded_json(intake_dir / timing_selector.partition(':')[2], 16 * 1024 * 1024)
        except (OSError, ValueError):
            timing_doc = None
    if timing_doc is not None:
        phrases = [{key: phrase.get(key) for key in ('phrase_id', 'label', 'label_basis', 'span_source_seconds', 'status',
                                                     'abstain_reason', 'median_offset_ms', 'iqr_ms', 'iqr_width_ms',
                                                     'median_offset_ms_delay_compensated', 'click_proximal_onset_count',
                                                     'onset_count_in_span', 'direction', 'direction_status')}
                   for phrase in timing_doc.get('phrases', [])]
        summary = timing_doc.get('summary') or {}
        phrase_timing = {'status': stages['phrase_timing']['status'], 'run_kind': timing_doc.get('run_kind'),
                         'direction_status': 'withheld_uncalibrated', 'ahead_behind_label': None,
                         'phrases_measured': summary.get('measured_count'), 'phrases_total': summary.get('phrase_count'),
                         'abstain_reason_counts': summary.get('abstain_reason_counts'),
                         'click_reference_basis': (timing_doc.get('click_reference') or {}).get('basis'),
                         'phrase_basis': timing_doc.get('phrase_basis'), 'phrases': phrases,
                         'claim_class': 'measured', 'interpretation': 'signed offsets only; not a performance verdict'}
        if any(row.get('direction') is not None for row in phrases):
            phrase_timing['direction_violation'] = True
    else:
        phrase_timing = {'status': (stages.get('phrase_timing') or {}).get('status'), 'direction_status': 'withheld_uncalibrated',
                         'ahead_behind_label': None, 'phrases_measured': None, 'phrases_total': None,
                         'reason': (stages.get('phrase_timing') or {}).get('reason') or 'no phrase-timing output'}
    triage = None
    if (intake_dir / 'flags-triage.json').is_file():
        try:
            triage = bounded_json(intake_dir / 'flags-triage.json', 16 * 1024 * 1024)
        except (OSError, ValueError):
            triage = None
    denominators = (triage or {}).get('denominators') or {}
    flags_triage = {'status': (stages.get('flags_triage') or {}).get('status'),
                    'shown': denominators.get('shown'), 'total': denominators.get('total_flags'),
                    'navigation_hidden': denominators.get('navigation_hidden'),
                    'suppressed_lower_priority': denominators.get('suppressed_lower_priority'),
                    'view': (triage or {}).get('view'), 'claim_class': 'inferred',
                    'interpretation': 'ordering of detector hypotheses; no verdict'}
    anchor_entry = stages.get('phrase_anchor') or {}
    phrase_anchor = {'status': anchor_entry.get('status'), 'reason': anchor_entry.get('reason'), 'adopted': False,
                     'outputs': anchor_entry.get('outputs') or {}}
    deliverables = []
    for stage_name, kinds in (('marked_video', ('marked-video.mov',)), ('marked_compact', ('marked-compact.mov',)),
                              ('share_export', ('marked-share.mp4',))):
        for selector, digest in ((stages.get(stage_name) or {}).get('outputs') or {}).items():
            if selector.rsplit('/', 1)[-1] in kinds:
                deliverables.append({'stage': stage_name, 'selector': selector, 'sha256': digest,
                                     'review_status': 'exported_unreviewed', 'listening_accepted': False})
    capture_record = (manifest or {}).get('noise_capture') or {}
    capture = {'interval_seconds': state['settings']['capture_interval'],
               'review_text_sha256': state['settings']['capture_review_sha256'],
               'review_text_location': 'local replay-arguments file only',
               'setup_override': state.get('capture_interval_setup_override'),
               'noise_only_verified_by_worker': False,
               'bound_selected_samples': capture_record.get('selected_samples'),
               'profile_update_status': capture_record.get('profile_update_status'),
               'claim_class': 'operator_input_required'}
    measurements = {
        'export_frames': {'source_decoded_video_frames': verification.get('source_decoded_video_frames'),
                          'export_decoded_video_frames': verification.get('export_decoded_video_frames'),
                          'class': 'measured'},
        'final_loudness': {'integrated_lufs': number(final_loudness.get('output_i')),
                           'true_peak_dbtp': number(final_loudness.get('output_tp')),
                           'targets': PROFILE_TARGETS, 'class': 'measured',
                           'scope': 'delivery AAC measurement from export/outcome.json; not listening acceptance'},
        'master_loudness': (((manifest or {}).get('loudness') or {}).get('cleaned') or {}).get('output'),
    }
    share_receipt = None
    if (intake_dir / 'share' / 'marked-share.mp4.receipt.json').is_file():
        try:
            share_receipt = bounded_json(intake_dir / 'share' / 'marked-share.mp4.receipt.json', 4 * 1024 * 1024)
        except (OSError, ValueError):
            share_receipt = None
    guard_documents = [document for document in (manifest, export, read_run_json(run, 'marked-preview/outcome.json'),
                                                 share_receipt) if document]
    guard = low_register_guard(guard_documents)
    run_demo_stages = (stages.get('demo') or {}).get('run_demo_stage_status') or {}
    claims = [
        {'item': 'source identity unchanged across invocations', 'class': 'measured'},
        {'item': 'probe summary (duration, codecs, rates, cfr/vfr declaration)', 'class': 'measured'},
        {'item': 'stage statuses and output hashes', 'class': 'measured'},
        {'item': 'export frame counts source/export', 'class': 'measured'},
        {'item': 'final integrated loudness and true peak vs profile targets', 'class': 'measured'},
        {'item': 'phrase timing signed offsets (median, IQR, count)', 'class': 'measured'},
        {'item': 'flags triage denominators', 'class': 'measured'},
        {'item': 'low-register filter-graph guard', 'class': 'measured'},
        {'item': 'phrase review spans and review flags (detector hypotheses)', 'class': 'inferred'},
        {'item': 'BPM / click grid candidates', 'class': 'inferred'},
        {'item': 'meter, time signature, tonic, mode', 'class': 'inferred'},
        {'item': 'restoration quality, fan residue audibility, low-end fullness', 'class': 'needs_listening'},
        {'item': 'capture interval is noise-only', 'class': 'needs_listening'},
        {'item': 'listening acceptance of this take', 'class': 'needs_listening'},
        {'item': 'corpus split', 'class': 'operator_input_required'},
        {'item': 'arrangement reference for this take', 'class': 'operator_input_required'},
        {'item': 'physical capture latency calibration', 'class': 'operator_input_required'},
        {'item': 'phrase boundary correctness (>=10 operator marks)', 'class': 'operator_input_required'},
        {'item': 'phrase timing direction (ahead/behind)', 'class': 'not_performed'},
        {'item': 'note correctness, missed or extra notes', 'class': 'not_performed'},
        {'item': 'click identity verification', 'class': 'not_performed'},
        {'item': 'editor (Final Cut / Resolve) import', 'class': 'not_performed'},
    ]
    stage_hashes = {name: (stages.get(name) or {}).get('outputs') or {} for name in state['stage_order']}
    packet = {
        'schema_id': SCHEMA_PACKET, 'schema_version': SCHEMA_VERSION, 'generated_at': now(),
        'intake': {'take_family_id': state['take_family_id'], 'family_basis': state['family_basis'],
                   'intake_id': state['intake_id'], 'origin': state['origin'], 'status': state.get('status'),
                   'stage_table': table,
                   'stage_counts': {'planned': len(state['stage_order']), 'completed': completed, 'abstained': abstained,
                                    'failed': failed, 'skipped_dependency_failed': skipped,
                                    'completed_over_planned': f"{completed}/{len(state['stage_order'])}"},
                   'status_counts': counts, 'run_demo_stage_status': run_demo_stages,
                   'run_binding': {'run_dir': state['run']['dir'] if state.get('run') else None, 'manifest': manifest_binding},
                   'resume_count': len(state.get('resume_history') or []),
                   'source_checks': {'unchanged': sum(1 for row in state.get('source_checks', []) if row.get('unchanged')),
                                     'total': len(state.get('source_checks', []))}},
        'stage_hashes': stage_hashes,
        'signal_versions_consumed': signal_versions(run, manifest, state, intake_dir),
        'tool_versions': tool_versions(root, state),
        'capture': capture,
        'phrase_timing': phrase_timing,
        'phrase_anchor': phrase_anchor,
        'flags_triage': flags_triage,
        'deliverables': deliverables,
        'measurements': measurements,
        'low_register_guard': guard,
        'claims': claims,
        'claim_class_counts': {name: sum(1 for claim in claims if claim['class'] == name) for name in CLAIM_CLASSES},
        'unknowns': state['unknowns'],
        'corpus_row_draft': state['corpus_row_draft'],
        'authority': AUTHORITY,
    }
    packet = Scrubber(root).deep(packet)
    draft = message_draft(state, packet)
    return packet, draft


def message_draft(state: dict, packet: dict) -> dict:
    probe = state['probe']
    duration = probe.get('container_duration_seconds')
    stage_counts = {}
    for entry in state['stages'].values():
        status = (entry or {}).get('status') or 'pending'
        stage_counts[status] = stage_counts.get(status, 0) + 1
    draft = {
        'schema_id': SCHEMA_DRAFT, 'schema_version': SCHEMA_VERSION, 'status': 'draft_not_sent', 'issue': 'TIN-5186',
        'take_family_id': state['take_family_id'], 'family_basis': state['family_basis'], 'origin': state['origin'],
        'intake_status': state.get('status'), 'stage_status_counts': dict(sorted(stage_counts.items())),
        'probe_class': {'container_duration_rounded_0_1': None if duration is None else round(duration, 1),
                        'video_codec': (probe.get('video') or {}).get('codec'),
                        'audio_codec': probe['audio'].get('codec'), 'sample_rate_hz': probe['audio'].get('sample_rate_hz'),
                        'channel_count': probe['audio'].get('channels'), 'cfr_vfr_status': probe.get('cfr_vfr_status')},
        'unknowns': sorted(state['unknowns']),
        'claim_class_counts': packet['claim_class_counts'],
        'split': None,
        'v6_statement_reference': V6_REFERENCE,
        'note': 'New take family registered by intake; non-media metadata only (V6). Root sends after operator review.',
    }
    violations = draft_violations(draft)
    if violations:
        raise IntakeRefusal('draft_privacy_violation', 'message draft failed V6 checks: ' + ', '.join(violations))
    return draft


SECONDS_TIMESTAMP = re.compile(r'\b\d+(?:\.\d+)?\s?(?:s|sec|seconds)\b|\b\d{1,2}:\d{2}(?::\d{2})?\b')
MEDIA_NAME = re.compile(r'\.(?:mov|mp4|m4v|wav|aac|flac|mp3)\b', re.I)
SOURCE_IDS = re.compile(r'\b(?:src|art)_[0-9a-f]+')


def draft_violations(draft: dict) -> list[str]:
    """M8: closed key set and six pattern checks; returns violation labels."""
    violations = []
    if set(draft) != DRAFT_KEYS:
        violations.append('key_set_not_closed')
    if isinstance(draft.get('probe_class'), dict) and set(draft['probe_class']) != PROBE_CLASS_KEYS:
        violations.append('probe_class_keys')
    text = json.dumps(draft, sort_keys=True)
    if absolute_paths_in(draft):
        violations.append('absolute_path')
    if HEX64.search(text):
        violations.append('hex64')
    if SOURCE_IDS.search(text):
        violations.append('src_or_art_id')
    if MEDIA_NAME.search(text):
        violations.append('media_file_name')
    strings = []
    pending = [draft]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, str):
            strings.append(item)
    numeric_lists = []
    pending = [draft]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            if item and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in item):
                numeric_lists.append(item)
            pending.extend(item)
    if any(SECONDS_TIMESTAMP.search(value) for value in strings) or numeric_lists:
        violations.append('seconds_timestamp_or_span')
    if len(text.encode('utf-8')) > 4096:
        violations.append('size_over_4_kib')
    return violations


def write_packet(intake_dir: Path, root: Path = ROOT) -> dict:
    packet, draft = build_packet(intake_dir, root)
    found = absolute_paths_in(packet)
    if found:
        raise IntakeRefusal('packet_privacy_violation', f'packet would carry {len(found)} absolute path(s)')
    run_demo.atomic_json(Path(intake_dir) / 'evidence-packet.json', packet)
    run_demo.atomic_json(Path(intake_dir) / 'tin-5186-message-draft.json', draft)
    return {'status': 'packet_written', 'evidence_packet': 'evidence-packet.json',
            'message_draft': 'tin-5186-message-draft.json', 'intake_status': packet['intake']['status'],
            'stage_counts': packet['intake']['stage_counts']}


# ---------------------------------------------------------------------- CLI

def intake_location(state: dict) -> str:
    return Scrubber().text(str(STATE_ROOT_HINT.get('path', '<STATE_ROOT>'))) + f"/{state.get('take_family_id')}/{state.get('intake_id')}"


STATE_ROOT_HINT: dict = {}


def refusal(exc: IntakeRefusal) -> int:
    payload = {'status': 'refused', 'reason': exc.code, 'message': Scrubber().text(str(exc))}
    if exc.details:
        payload['details'] = Scrubber().deep(exc.details)
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    plan = sub.add_parser('plan', help='Read-only intake plan (stdout JSON only)')
    plan.add_argument('source')
    plan.add_argument('--family')
    plan.add_argument('--arrangement')
    plan.add_argument('--bpm', type=float)
    plan.add_argument('--features', choices=('base', 'extended'), default='base')
    plan.add_argument('--origin', choices=('real_recording', 'synthetic_fixture'), default='real_recording')
    plan.add_argument('--anchor-seconds', type=float)
    plan.add_argument('--state-root')
    run = sub.add_parser('run', help='Run the ordered stage graph, or --resume INTAKE_ID')
    run.add_argument('source', nargs='?')
    run.add_argument('--capture-interval', nargs=2, type=float, metavar=('START', 'END'))
    run.add_argument('--capture-review')
    run.add_argument('--interval-reviewed-includes-setup', action='store_true', default=None)
    run.add_argument('--family')
    run.add_argument('--arrangement')
    run.add_argument('--anchor-seconds', type=float)
    run.add_argument('--anchor-source')
    run.add_argument('--clicks-per-grid-period', type=int, choices=(1, 2))
    run.add_argument('--bpm', type=float)
    run.add_argument('--features', choices=('base', 'extended'))
    run.add_argument('--analysis-python')
    run.add_argument('--origin', choices=('real_recording', 'synthetic_fixture'))
    run.add_argument('--state-root')
    run.add_argument('--resume', metavar='INTAKE_ID')
    packet = sub.add_parser('packet', help='Build the evidence packet and TIN-5186 draft for an intake run directory')
    packet.add_argument('run_dir')
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == 'plan':
            document = build_plan(args.source, family=args.family, arrangement=args.arrangement, bpm=args.bpm,
                                  features=args.features, origin=args.origin, state_root=args.state_root,
                                  anchor_seconds=args.anchor_seconds)
            print(json.dumps(Scrubber().deep(document), sort_keys=True, indent=2, allow_nan=False))
            return 0
        if args.command == 'packet':
            path = Path(args.run_dir).expanduser()
            path = path if path.is_absolute() else Path.cwd() / path
            print(json.dumps(write_packet(path), sort_keys=True))
            return 0
        if args.resume is not None:
            conflicts = [name for name in SETTING_FLAGS if getattr(args, name, None) is not None]
            if conflicts:
                raise IntakeRefusal('resume_settings_conflict', '--resume replays recorded settings; remove: '
                                    + ', '.join(conflicts))
            code, state = resume_intake(args.resume, state_root=args.state_root)
        else:
            if args.source is None:
                raise IntakeRefusal('source_missing', 'run needs SOURCE (or --resume INTAKE_ID)')
            code, state = run_intake(
                args.source, capture_interval=args.capture_interval, capture_review=args.capture_review,
                interval_reviewed_includes_setup=bool(args.interval_reviewed_includes_setup), family=args.family,
                arrangement=args.arrangement, anchor_seconds=args.anchor_seconds, anchor_source=args.anchor_source,
                clicks_per_grid_period=args.clicks_per_grid_period, bpm=args.bpm, features=args.features or 'base',
                analysis_python=args.analysis_python, origin=args.origin or 'real_recording', state_root=args.state_root)
        print(json.dumps({'status': state.get('status'), 'intake_id': state.get('intake_id'),
                          'take_family_id': state.get('take_family_id'),
                          'stage_status': {name: (entry or {}).get('status') for name, entry in state['stages'].items()},
                          'intake_dir': intake_location(state)},
                         sort_keys=True))
        return code
    except IntakeRefusal as exc:
        return refusal(exc)


if __name__ == '__main__':
    raise SystemExit(main())
