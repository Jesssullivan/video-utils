#!/usr/bin/env python3
"""Render or extend a private demo with explicitly selected analysis evidence."""
from __future__ import annotations

import argparse
import contextlib
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_HISTORY_FILE_BYTES = 20_000_000
MAX_HISTORY_JSON_BYTES = 40_000_000
MAX_HISTORY_TOTAL_BYTES = 64_000_000
HISTORY_ARTIFACTS = ('manifest.json', 'analysis.json', 'events.csv', 'noise.json', 'tone.json',
                     'notes.json', 'phrases.json', 'pitch.json', 'tonal/tonal.json',
                     'phrase-comparisons.json', 'dag.json', 'flags.json', 'markers.json',
                     'markers.csv', 'report.html', 'demo.json', 'export/outcome.json')
# Operator decision 2026-10-06 (TIN-5599): FULLER default with a required reviewed capture interval.
DEFAULT_PROFILE = 'fuller'
AUTHORITY = 'R-HOOK-CONVERGENCE-20261004; TIN-3692 98cf680c-7299-4949-bfb2-60079053ad43'
OPTIONAL_OUTPUTS = {'clicks': ('clicks_json', 'clicks'), 'pitch': ('pitch_json', 'pitch'),
                    'meter': ('output', 'meter'), 'tonal': ('tonal_json', 'tonal'),
                    'comparisons': ('comparisons_json', 'comparisons')}
OVERWRITTEN_OUTPUTS = {'rhythm': ('analysis.json', 'events.csv'), 'noise': ('noise.json',),
                       'tone': ('tone.json',), 'notes': ('notes.json',), 'phrases': ('phrases.json',),
                       'pitch': ('pitch.json',), 'tonal': ('tonal/tonal.json',),
                       'comparisons': ('phrase-comparisons.json',)}

# S2 robustness lane (TIN-5609, docs/spec/sprints/ROBUSTNESS_S2.md): crash recovery
# for one recorded invocation. Resume never infers settings, adopts a run by
# discovery, deletes outputs or signals another process.
INVOCATION_ID_PATTERN = re.compile(r'[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}')
MAX_RECEIPT_BYTES = 2 * 1024 * 1024
MAX_RUN_SCAN_ENTRIES = 10_000
SUCCESS_TERMINAL = frozenset({'completed', 'measured_candidates', 'existing_media_verified_unreviewed',
                              'existing_delivery_hash_verified_unreviewed', 'not_available'})
BASE_STAGES = ('media', 'export', 'rhythm', 'noise', 'tone', 'notes', 'phrases')
EXTENDED_STAGES = ('clicks', 'pitch', 'meter', 'tonal', 'comparisons')
FINAL_STAGES = ('dag', 'markers', 'report')
STAGE_TIMEOUTS = {'media': 1200, 'export': 1200,
                  **{name: 600 for name in BASE_STAGES[2:]},
                  **{name: 300 for name in EXTENDED_STAGES},
                  **{name: 180 for name in FINAL_STAGES}}
STAGE_WORKERS = {'media': 'media.py', 'export': 'media.py', 'rhythm': 'rhythm.py',
                 'noise': 'guitar_features.py', 'tone': 'guitar_features.py', 'notes': 'guitar_features.py',
                 'phrases': 'guitar_features.py', 'clicks': 'clicks.py', 'pitch': 'pitch.py', 'meter': 'meter.py',
                 'tonal': 'tonal.py', 'comparisons': 'phrase_compare.py', 'dag': 'dag.py',
                 'markers': 'markers.py', 'report': 'report.py'}
# Fixed run-relative outputs per stage (extended selectors come from selected_evidence).
STAGE_OUTPUTS = {'rhythm': ('analysis.json', 'events.csv'), 'noise': ('noise.json',), 'tone': ('tone.json',),
                 'notes': ('notes.json',), 'phrases': ('phrases.json',), 'pitch': ('pitch.json',),
                 'tonal': ('tonal/tonal.json',), 'comparisons': ('phrase-comparisons.json',),
                 'dag': ('dag.json', 'flags.json'), 'markers': ('markers.json', 'markers.csv'),
                 'report': ('report.html',)}
# Dependency table frozen at the implementation commit after reading worker inputs:
# rhythm/noise/tone/notes read only the manifest and denoised.wav; phrases also reads
# analysis.json and notes.json (guitar_features.phrase_context). Extended workers,
# dag, markers and report read run-directory state that is not fully enumerated, so
# each depends on every earlier stage of the invocation.
DIRECT_DEPENDENCIES = {'media': (), 'export': ('media',), 'rhythm': ('media',), 'noise': ('media',),
                       'tone': ('media',), 'notes': ('media',), 'phrases': ('media', 'rhythm', 'notes')}
RESUME_CONFLICTS = ('input', 'existing_run', 'profile', 'capture_interval', 'capture_review', 'bpm',
                    'backend', 'features', 'analysis_python', 'pitch_seconds')
RESUME_ARGUMENT_KEYS = ('mode', 'input_path', 'input_sha256', 'existing_run_dir', 'profile', 'capture_interval',
                        'capture_review', 'bpm', 'backend', 'features', 'analysis_python', 'pitch_seconds',
                        'no_latest')
MEMORY_UNKNOWN = {'memory_ceiling_bytes': None, 'memory_ceiling_status': 'unknown_not_measured'}


class StageError(RuntimeError):
    def __init__(self, message: str, receipt: dict | None = None):
        super().__init__(message)
        self.receipt = receipt or {}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def strict_json(text: str) -> dict:
    def reject(value):
        raise ValueError(f'Non-finite JSON number: {value}')
    result = json.loads(text, parse_constant=reject)
    if not isinstance(result, dict):
        raise ValueError('Worker or manifest must return a JSON object')
    # Also reject overflowed exponents, recursively, with a parser-sized bound.
    pending = [(result, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > 128:
            raise ValueError('JSON nesting exceeds 128 levels')
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Non-finite JSON exponent')
        if isinstance(value, dict):
            pending.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            pending.extend((child, depth + 1) for child in value)
    return result


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            os.chmod(temporary, 0o600)
            json.dump(payload, handle, indent=2, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def stop_owned(process: subprocess.Popen, reason: str) -> dict:
    observed = None
    result = 'already_exited'
    try:
        observed = os.getpgid(process.pid)
        if observed == process.pid:
            os.killpg(observed, signal.SIGKILL)
            result = 'owned_process_group'
        elif process.poll() is None:
            process.kill()
            result = 'owned_worker_only'
    except ProcessLookupError:
        # A leader can exit while its children retain our newly created group.
        # A live group reserves its ID, preventing reuse by another session.
        try:
            os.killpg(process.pid, 0)
            observed = process.pid
            os.killpg(process.pid, signal.SIGKILL)
            result = 'owned_descendant_process_group_after_leader_exit'
        except ProcessLookupError:
            pass
    process.wait(timeout=5)
    return {'actor': 'video-utils/run_demo',
            'target_ownership': {'pid': process.pid, 'observed_pgid': observed,
                                 'created_by_invocation': True, 'new_session_requested': True},
            'reason': reason, 'ruling': 'R-N11; ' + AUTHORITY,
            'prior_state': 'recorded worker/group inspected for liveness before signal',
            'result': {'signal_target': result, 'worker_returncode': process.returncode}}


def invoke(script: str, arguments: list[str], timeout: int = 1200,
           interpreter: str | None = None, execution: dict | None = None, *, on_started=None) -> dict:
    """Actively bound both pipes and the entire owned worker process group.

    ``on_started`` (optional) is called once the worker PID is recorded so the
    orchestrator can checkpoint it; resume inspects that PID group for liveness."""
    worker = ROOT / 'scripts' / script
    if worker.name != script or not worker.is_file():
        raise StageError(f'Worker unavailable: {script}')
    receipt = execution if execution is not None else {}
    command = [interpreter or sys.executable, str(worker), *arguments]
    receipt.update(command=command, worker_sha256=sha256(worker), timeout_seconds=timeout,
                   max_output_bytes_per_stream=MAX_OUTPUT_BYTES, status='starting')
    started = time.monotonic()
    environment = os.environ.copy()
    for variable in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS'):
        environment[variable] = '2'
    try:
        process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
                                   env=environment)
    except OSError as exc:
        receipt.update(status='failed_to_start', error=str(exc))
        raise StageError(f'{script}: could not start: {exc}', receipt) from exc
    receipt.update(pid=process.pid, new_session_requested=True)
    buffers = {'stdout': bytearray(), 'stderr': bytearray()}
    issue = None
    try:
        if on_started is not None:
            on_started()
        with selectors.DefaultSelector() as selector:
            for label, pipe in [('stdout', process.stdout), ('stderr', process.stderr)]:
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, label)
            while selector.get_map():
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    issue = f'worker hard deadline exceeded ({timeout}s)'
                    break
                for key, _ in selector.select(min(remaining, .1)):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    buffer = buffers[key.data]
                    room = MAX_OUTPUT_BYTES - len(buffer)
                    buffer.extend(data[:room])
                    if len(data) > room:
                        issue = f'worker {key.data} exceeds {MAX_OUTPUT_BYTES} byte limit'
                        break
                if issue:
                    break
            if not issue:
                remaining = timeout - (time.monotonic() - started)
                try:
                    process.wait(timeout=max(.001, remaining))
                except subprocess.TimeoutExpired:
                    issue = f'worker hard deadline exceeded ({timeout}s)'
        if issue:
            receipt['process_escape_hatch'] = stop_owned(process, issue)
        receipt.update(elapsed_seconds=time.monotonic()-started, returncode=process.returncode,
                       stdout_bytes=len(buffers['stdout']), stderr_bytes=len(buffers['stderr']))
        receipt['stderr_tail'] = buffers['stderr'][-3000:].decode('utf-8', errors='replace')
        if issue or process.returncode:
            receipt.update(status='failed', error=issue or f'worker exited {process.returncode}')
            raise StageError(f'{script}: {receipt["error"]}; {receipt["stderr_tail"]}', receipt)
        try:
            result = strict_json(buffers['stdout'].decode('utf-8'))
        except (UnicodeError, ValueError, RecursionError) as exc:
            receipt.update(status='invalid_result', error=str(exc))
            raise StageError(f'{script}: invalid finite JSON result', receipt) from exc
        if sha256(worker) != receipt['worker_sha256']:
            receipt.update(status='worker_changed_during_execution')
            raise StageError(f'{script}: worker source changed during invocation', receipt)
        receipt['status'] = 'completed'
        return result
    finally:
        if process.poll() is None:
            receipt['process_escape_hatch'] = stop_owned(process, 'worker invocation unwound before completion')
        process.stdout.close()
        process.stderr.close()


def verify_pcm(directory: Path, manifest: dict) -> None:
    spec = importlib.util.spec_from_file_location('video_utils_demo_media', ROOT / 'scripts/media.py')
    media = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(media)
    for name in ('denoised.wav', 'cleaned.wav'):
        media.ensure_pcm_matches(directory / name, manifest['pcm'])


def validate_existing(directory: Path) -> dict:
    """Verify immutable media identity before starting any analysis workers."""
    path = directory / 'manifest.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError('Existing run requires a bounded regular manifest.json')
    before = sha256(path)
    manifest = strict_json(path.read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 1:
        raise ValueError('Existing manifest schema_version must be 1')
    if Path(manifest.get('run_dir', '')).resolve() != directory:
        raise ValueError('Existing manifest run_dir differs from requested directory')
    for key, media_path in [('source', Path(manifest['source']['path'])),
                            ('denoised.wav', directory / 'denoised.wav'),
                            ('cleaned.wav', directory / 'cleaned.wav')]:
        expected = manifest['source']['sha256'] if key == 'source' else manifest['output_sha256'][key]
        if (not isinstance(expected, str) or len(expected) != 64
                or media_path.is_symlink() or not media_path.is_file() or sha256(media_path) != expected):
            raise ValueError(f'Existing run {key} hash or regular-file identity does not match manifest')
    # Reuse the qualified native-PCM extent check; it performs read-only ffprobe.
    verify_pcm(directory, manifest)
    if sha256(path) != before:
        raise ValueError('Existing manifest changed during validation')
    return manifest


def exact_selector(directory: Path, returned: str) -> tuple[str, str]:
    """Use only the successful worker's exact JSON path, with no discovery."""
    path = Path(returned)
    if not path.is_absolute():
        raise ValueError('Worker artifact receipt must provide an absolute path')
    relative = path.relative_to(directory)
    parts = relative.parts
    if (not parts or path.suffix != '.json' or any(part.startswith('.') or '.partial' in part for part in parts)
            or ':' in relative.as_posix() or '\\' in relative.as_posix()):
        raise ValueError('Worker returned an unsafe run-relative JSON artifact')
    check = directory
    for part in parts:
        check = check / part
        if check.is_symlink():
            raise ValueError('Worker artifact receipt contains a symlink component')
    if not path.is_file():
        raise ValueError('Worker artifact receipt does not exist')
    return relative.as_posix(), sha256(path)


def existing_export(directory: Path, manifest: dict) -> dict | None:
    """Reuse a hash-bound delivery receipt without invoking the encoder."""
    path = directory / 'export' / 'outcome.json'
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError('Existing export receipt must be a bounded regular file')
    data = strict_json(path.read_text(encoding='utf-8'))
    if data.get('source_sha256') != manifest['source']['sha256']:
        raise ValueError('Existing export differs from original source identity')
    for name, identity in data.get('output_sha256', {}).items():
        artifact = directory / 'export' / name
        if (Path(name).name != name or artifact.is_symlink() or not artifact.is_file()
                or sha256(artifact) != identity):
            raise ValueError('Existing export output hash or path differs from receipt')
    if data.get('video') is not None:
        expected = directory / 'export' / 'cleaned-video.mov'
        if data['video'] != str(expected) or 'cleaned-video.mov' not in data.get('output_sha256', {}):
            raise ValueError('Existing export video path lacks an exact hash-bound receipt')
        if data.get('verification', {}).get('final_true_peak_within_target') is not True:
            raise ValueError('Existing export video lacks a passing decoded true-peak receipt')
    return data


def snapshot_existing(directory: Path, manifest: dict) -> dict:
    """Archive only a fixed overwrite allowlist before touching an existing run."""
    contents = {}
    json_bytes = total_bytes = 0
    for name in HISTORY_ARTIFACTS:
        path = directory
        for part in name.split('/'):
            path = path / part
            if path.is_symlink():
                raise ValueError('Prior artifact snapshot cannot follow symlink components')
        if not path.exists():
            continue
        if not path.is_file() or path.stat().st_size > MAX_HISTORY_FILE_BYTES:
            raise ValueError('Prior artifact snapshot file exceeds 20 MB or is not regular')
        with path.open('rb') as handle:
            content = handle.read(MAX_HISTORY_FILE_BYTES + 1)
        if len(content) > MAX_HISTORY_FILE_BYTES:
            raise ValueError('Prior artifact snapshot file changed beyond 20 MB bound')
        total_bytes += len(content)
        json_bytes += len(content) if name.endswith('.json') else 0
        if total_bytes > MAX_HISTORY_TOTAL_BYTES or json_bytes > MAX_HISTORY_JSON_BYTES:
            raise ValueError('Prior artifact snapshot exceeds 64 MB total or 40 MB JSON bound')
        contents[name] = content
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in contents.items()}
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    parent = directory / 'demo-history'
    target = parent / identity
    if parent.is_symlink() or target.is_symlink():
        raise ValueError('Demo history must not contain symlink components')
    history = {'schema_version': 1, 'status': 'prior_artifact_snapshot_not_revalidated',
               'artifact_hashes': hashes, 'total_bytes': total_bytes, 'json_bytes': json_bytes,
               'media_copied': False, 'source_sha256': manifest['source']['sha256'],
               'authority': AUTHORITY + '/R-N13', 'allowlist': list(HISTORY_ARTIFACTS)}
    if any(sha256(directory / name) != value for name, value in hashes.items()):
        raise ValueError('Prior artifacts changed while snapshot was prepared; run preserved')
    parent.mkdir(exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.snapshot-', dir=parent))
    try:
        for name, content in contents.items():
            destination = staging / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('xb') as handle:
                os.chmod(destination, 0o600)
                handle.write(content)
        atomic_json(staging / 'receipt.json', history)
        if target.exists():
            for name, content in contents.items():
                existing = target
                for part in name.split('/'):
                    existing = existing / part
                    if existing.is_symlink():
                        raise ValueError('Existing demo history contains a symlink')
                if (not existing.is_file() or existing.stat().st_size > MAX_HISTORY_FILE_BYTES
                        or sha256(existing) != hashes[name]):
                    raise ValueError('Existing content-addressed demo history differs from receipt')
            saved_receipt = target / 'receipt.json'
            if (saved_receipt.is_symlink() or saved_receipt.stat().st_size > MAX_MANIFEST_BYTES
                    or saved_receipt.read_bytes() != (staging / 'receipt.json').read_bytes()):
                raise ValueError('Existing demo history receipt is inconsistent')
        else:
            staging.rename(target)
        if any(sha256(directory / name) != value for name, value in hashes.items()):
            raise ValueError('Prior artifacts changed during snapshot publication; no analysis launched')
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {'path': target.relative_to(directory).as_posix(), 'snapshot_sha256': identity,
            'artifact_hashes': hashes, 'total_bytes': total_bytes, 'media_copied': False,
            'status': 'prior_artifact_snapshot_not_revalidated'}


def profile_requires_capture(value: str) -> bool:
    """Mirror media.load_profile resolution; True only for a readable capture-required template.

    Unreadable or invalid profiles fall through to media.py, which owns validation."""
    path = Path(value).expanduser()
    if not path.is_file():
        path = ROOT / 'profiles' / f'{value}.json'
    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            return False
        profile = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    return (isinstance(profile, dict) and profile.get('noise_capture_required') is True
            and profile.get('noise_capture_seconds') is None)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_pid() -> int:
    return os.getpid()


def pid_alive(pid) -> bool:
    """Signal-0 inspection only (R-N11): nothing is delivered to any process."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True  # EPERM: a live process owned by someone else.
    return True


def group_alive(pgid) -> bool:
    """Signal-0 inspection of a recorded worker process group; never signals it."""
    if not isinstance(pgid, int) or isinstance(pgid, bool) or pgid <= 1:
        return False
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def stage_order(features: str) -> tuple:
    return BASE_STAGES + (EXTENDED_STAGES if features == 'extended' else ()) + FINAL_STAGES


def stage_dependencies(name: str, order: tuple) -> tuple:
    if name in DIRECT_DEPENDENCIES:
        return DIRECT_DEPENDENCIES[name]
    return order[:order.index(name)]


def run_path(directory: Path, relative: str) -> Path:
    """Resolve a recorded run-relative path without following symlink components."""
    if (not isinstance(relative, str) or not relative or relative.startswith('/') or '\\' in relative
            or any(part in ('', '.', '..') for part in relative.split('/'))):
        raise ValueError(f'Unsafe run-relative artifact path: {relative!r}')
    path = directory
    for part in relative.split('/'):
        path = path / part
        if path.is_symlink():
            raise ValueError(f'Artifact path has a symlink component: {relative}')
    return path


def bounded_json_file(path: Path, limit: int = MAX_RECEIPT_BYTES) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError(f'{path.name} must be a bounded regular non-symlink file')
    with path.open('rb') as handle:
        content = handle.read(limit + 1)
    if len(content) > limit:
        raise ValueError(f'{path.name} grew beyond its bound')
    return strict_json(content.decode('utf-8'))


def stage_artifacts(name: str, directory: Path, selected: dict, manifest: dict | None) -> dict:
    """Fixed per-stage artifact table (ROBUSTNESS_S2 §3.4), hashed as found on disk."""
    if name == 'media':
        names = ['manifest.json', *sorted((manifest or {}).get('output_sha256', {}))]
    elif name == 'export':
        names = []
        outcome_path = directory / 'export' / 'outcome.json'
        if outcome_path.exists() or outcome_path.is_symlink():
            outcome = bounded_json_file(outcome_path)
            names = ['export/outcome.json']
            for output in sorted(outcome.get('output_sha256', {}) or {}):
                if Path(output).name != output:
                    raise ValueError('Export receipt names a non-local output')
                names.append('export/' + output)
    elif name in OPTIONAL_OUTPUTS:
        evidence = selected.get(OPTIONAL_OUTPUTS[name][1])
        names = [evidence['selector']] if evidence else []
    else:
        names = list(STAGE_OUTPUTS.get(name, ()))
    artifacts = {}
    for relative in names:
        path = run_path(directory, relative)
        if path.is_file():
            artifacts[relative] = sha256(path)
    return artifacts


class ResumeRefusal(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', nargs='?')
    parser.add_argument('--existing-run', type=Path, help='Extend validated media without rerendering')
    parser.add_argument('--profile', default=None,
                        help=f'Profile name or path (default {DEFAULT_PROFILE}); default fuller requires --capture-interval START END')
    parser.add_argument('--capture-interval', nargs=2, type=float, metavar=('START', 'END'),
                        help='Reviewed per-take noise capture interval passed to media.py clean')
    parser.add_argument('--capture-review', help='Non-empty review text for --capture-interval')
    parser.add_argument('--bpm', type=float, help='Approximate operator pulse; not an intended score')
    parser.add_argument('--backend', choices=('stdlib', 'librosa'), default=None, help='Default stdlib')
    parser.add_argument('--features', choices=('base', 'extended'), default=None, help='Default base')
    parser.add_argument('--analysis-python', help='Explicit interpreter with already-installed optional dependencies')
    parser.add_argument('--pitch-seconds', type=float, default=None, help='Bounded excerpt coverage, 1–30 seconds (default 20)')
    parser.add_argument('--no-latest', action='store_true', help='Keep the operator latest pointer unchanged, useful for fixtures')
    parser.add_argument('--resume', metavar='INVOCATION_ID',
                        help='Crash-recover one recorded invocation in place; replays its recorded settings')
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.resume is not None:
        conflicts = [name for name in RESUME_CONFLICTS if getattr(args, name) is not None]
        if conflicts:
            parser.error('--resume replays recorded settings and cannot be combined with: '
                         + ', '.join('--' + name.replace('_', '-') if name != 'input' else 'INPUT' for name in conflicts))
        return resume(args.resume, args.no_latest)
    args.profile = DEFAULT_PROFILE if args.profile is None else args.profile
    args.backend = 'stdlib' if args.backend is None else args.backend
    args.features = 'base' if args.features is None else args.features
    args.pitch_seconds = 20 if args.pitch_seconds is None else args.pitch_seconds
    if bool(args.input) == bool(args.existing_run):
        parser.error('Supply either INPUT or --existing-run RUN_DIR')
    if args.existing_run and (args.capture_interval is not None or args.capture_review is not None):
        parser.error('--capture-interval/--capture-review apply only to a new INPUT render')
    if args.input and args.capture_interval is None and profile_requires_capture(args.profile):
        print(json.dumps({'status': 'error', 'reason': 'capture_interval_required',
                          'message': f'profile {args.profile} requires a reviewed per-take capture interval: pass '
                                     '--capture-interval START END --capture-review TEXT for this take, or select '
                                     '--profile conservative3 explicitly (no capture binding)'}), file=sys.stderr)
        return 1
    if args.bpm is not None and (not math.isfinite(args.bpm) or not 20 <= args.bpm <= 400):
        parser.error('--bpm must be finite and between 20 and 400')
    if not math.isfinite(args.pitch_seconds) or not 1 <= args.pitch_seconds <= 30:
        parser.error('--pitch-seconds must be finite and between 1 and 30')
    analysis_python = args.analysis_python or os.environ.get('VIDEO_UTILS_ANALYSIS_PYTHON', sys.executable)
    input_path = input_sha256 = None
    if args.input:
        candidate = Path(args.input).expanduser().resolve()
        input_path = str(candidate)
        try:
            input_sha256 = sha256(candidate) if candidate.is_file() else None
        except OSError:
            input_sha256 = None
    invocation_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:12]
    settings = SimpleNamespace(
        input=args.input, existing_run=args.existing_run, profile=args.profile,
        capture_interval=args.capture_interval, capture_review=args.capture_review, bpm=args.bpm,
        backend=args.backend, features=args.features, analysis_python=analysis_python,
        pitch_seconds=args.pitch_seconds, no_latest=args.no_latest)
    receipt = {'schema_version': 1, 'created_at': now(),
               'invocation_id': invocation_id, 'mode': 'existing_run' if args.existing_run else 'new_render',
               'analysis_settings': {'backend': args.backend, 'operator_bpm': args.bpm,
                                     'features': args.features, 'analysis_interpreter': analysis_python,
                                     'pitch_max_analysis_seconds': args.pitch_seconds},
               'stages': {}, 'selected_evidence': {}, 'listening_accepted': False,
               'authority': 'Operator approved implementation; ' + AUTHORITY + '/R-N13',
               # Additive (ROBUSTNESS_S2 §3.2): recorded before any stage so a crash is resumable.
               'resume_arguments': {
                   'mode': 'existing_run' if args.existing_run else 'new_render',
                   'input_path': input_path, 'input_sha256': input_sha256,
                   'existing_run_dir': str(args.existing_run.expanduser().absolute()) if args.existing_run else None,
                   'profile': args.profile,
                   'capture_interval': list(args.capture_interval) if args.capture_interval is not None else None,
                   'capture_review': args.capture_review, 'bpm': args.bpm, 'backend': args.backend,
                   'features': args.features, 'analysis_python': analysis_python,
                   'pitch_seconds': args.pitch_seconds, 'no_latest': args.no_latest},
               'orchestrator': {'pid': current_pid(), 'started_at': now()},
               'resource_limits': resource_limits()}
    checkpoint = ROOT / 'artifacts' / 'demo-invocations' / invocation_id / 'receipt.json'
    return run_pipeline(settings, receipt, checkpoint)


def resource_limits() -> dict:
    return {'stage_timeouts_seconds': dict(STAGE_TIMEOUTS), 'max_output_bytes_per_stream': MAX_OUTPUT_BYTES,
            'worker_thread_environment': 2, **MEMORY_UNKNOWN,
            'memory_note': 'No RSS limit is enforced or measured; the memory ceiling is unknown.'}


def run_pipeline(settings, receipt: dict, checkpoint: Path, resume_state: dict | None = None) -> int:
    """Run (or, with ``resume_state``, continue) the recorded stage graph.

    A fresh invocation passes no resume state and behaves exactly as before."""
    stages = receipt['stages']
    selected = receipt['selected_evidence']
    invocation_id = receipt['invocation_id']
    skip = resume_state['skip'] if resume_state else set()
    directory = resume_state.get('directory') if resume_state else None
    manifest = resume_state.get('manifest') if resume_state else None
    bootstrap = ROOT / 'artifacts' / 'demo-invocations' / invocation_id / 'receipt.json'
    analysis_python = settings.analysis_python
    options = ['--backend', settings.backend]
    if settings.bpm is not None:
        options += ['--bpm', str(settings.bpm)]

    def save():
        atomic_json(checkpoint, receipt)
        if directory is not None:
            atomic_json(directory / 'demo.json', receipt)

    def displace(name):
        """Move (never delete) a rerun stage's current outputs aside with their hashes."""
        if resume_state is None or directory is None or name in ('media', 'export'):
            return
        pending = stages.get(name, {}) if isinstance(stages.get(name), dict) else {}
        relatives = list(STAGE_OUTPUTS.get(name, ()))
        superseded = pending.get('superseded_selection')
        if isinstance(superseded, dict) and isinstance(superseded.get('selector'), str):
            relatives.append(superseded['selector'])
        snapshot = receipt.get('prior_artifact_snapshot', {}).get('artifact_hashes', {}) if settings.existing_run else {}
        entry = resume_state['entry']
        root = directory / 'demo-invocations' / invocation_id / f'resume-{entry["resume_index"]}' / 'displaced'
        for relative in dict.fromkeys(relatives):
            path = run_path(directory, relative)
            if not path.exists():
                continue
            if not path.is_file():
                raise ValueError(f'Cannot displace non-regular output {relative}')
            digest = sha256(path)
            if name in OVERWRITTEN_OUTPUTS and snapshot.get(relative) == digest:
                continue  # Exact prior bytes are archived; existing-run retirement handles them.
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() or target.is_symlink():
                raise ValueError(f'Displacement target already exists: {relative}')
            path.rename(target)
            if sha256(target) != digest:
                raise ValueError(f'Displaced output changed while moving: {relative}')
            entry['displaced_outputs'][relative] = digest
        save()

    def finish_inline(name, entry):
        """Record artifacts for an inline (worker-free) stage entry."""
        entry.setdefault('started_at', now())
        entry['completed_at'] = now()
        if entry['status'] in SUCCESS_TERMINAL:
            entry['artifacts'] = stage_artifacts(name, directory, selected, manifest)

    def stage(name, script, arguments, timeout=600, interpreter=None, select=False):
        if name in skip:
            print(f'Skipping hash-verified {name}…', file=sys.stderr)
            return stages[name].get('result')
        print(f'Running {name}…', file=sys.stderr)
        execution = {}
        prior = stages.get(name)
        stages[name] = {'status': 'running', 'execution': execution, 'started_at': now()}
        if isinstance(prior, dict) and prior.get('status') == 'pending_resume_rerun':
            stages[name]['superseded_selection'] = prior.get('superseded_selection')
        save()
        try:
            displace(name)
            if settings.existing_run and name in OVERWRITTEN_OUTPUTS:
                # A failed current stage must not leave its older root result
                # available to implicit primitive-worker inputs. Exact prior
                # bytes were archived before any workflow mutation.
                retired = {}
                for relative in OVERWRITTEN_OUTPUTS[name]:
                    path = directory
                    for part in relative.split('/'):
                        path = path / part
                        if path.is_symlink():
                            raise ValueError('Current derived artifact became a symlink after snapshot')
                    if not path.exists():
                        continue
                    expected = receipt['prior_artifact_snapshot']['artifact_hashes'].get(relative)
                    if expected is None or sha256(path) != expected:
                        raise ValueError('Current derived artifact changed after snapshot; refusing to retire it')
                    retired[relative] = expected
                    path.unlink()
                stages[name]['prior_artifacts_retired_to_snapshot'] = retired
            data = invoke(script, arguments, timeout, interpreter, execution, on_started=save)
            stages[name].update(status='measured_candidates' if name not in {'media', 'export', 'dag', 'markers', 'report'} else 'completed', result=data)
            if select:
                key, slot = OPTIONAL_OUTPUTS[name]
                selector, identity = exact_selector(directory, data[key])
                if data.get('sha256') is not None and data['sha256'] != identity:
                    raise ValueError('Worker artifact hash differs from returned receipt')
                selected[slot] = {'selector': selector, 'sha256': identity}
            if name == 'dag':
                relative, _ = exact_selector(directory, data['dag_json'])
                if relative != 'dag.json' or (directory / relative).stat().st_size > MAX_HISTORY_FILE_BYTES:
                    raise ValueError('Graph receipt must identify bounded run-local dag.json')
                graph = strict_json((directory / relative).read_text(encoding='utf-8'))
                rows = graph.get('selected_evidence', {})
                verdicts = {}
                for slot in OPTIONAL_OUTPUTS:
                    row = rows.get(slot, {})
                    verdicts[slot] = row.get('status', 'missing')
                    if slot in selected:
                        evidence = selected[slot]
                        if (row.get('status') != 'verified' or row.get('selector') != evidence['selector']
                                or row.get('artifact_sha256') != evidence['sha256']):
                            raise ValueError(f'Graph did not verify the current exact {slot} receipt')
                    elif row.get('status') != 'not_selected':
                        raise ValueError(f'Graph unexpectedly selected historical {slot} evidence')
                stages[name]['selected_evidence_verdicts'] = verdicts
            if name == 'media':
                stages[name]['artifacts'] = stage_artifacts(name, Path(data['run_dir']).resolve(strict=True), selected, data)
            else:
                stages[name]['artifacts'] = stage_artifacts(name, directory, selected, manifest)
        except (StageError, OSError, ValueError, KeyError) as exc:
            stages[name].update(status='failed', reason=str(exc))
            if isinstance(exc, StageError):
                stages[name]['execution'] = exc.receipt
            stages[name].pop('artifacts', None)
            if select:
                selected.pop(OPTIONAL_OUTPUTS[name][1], None)
        stages[name]['completed_at'] = now()
        save()
        return stages[name].get('result') if stages[name]['status'] != 'failed' else None

    def dependency_skip(name, dependencies):
        if resume_state is not None:
            if name in OPTIONAL_OUTPUTS:
                selected.pop(OPTIONAL_OUTPUTS[name][1], None)
            displace(name)
        stages[name] = {'status': 'skipped_dependency_failed', 'dependencies': list(dependencies)}
        save()

    try:
        save()
        if 'media' in skip:
            print('Skipping hash-verified media…', file=sys.stderr)
        elif settings.existing_run:
            if settings.existing_run.is_symlink():
                raise ValueError('Existing run directory must not be a symlink')
            candidate = settings.existing_run.expanduser().resolve(strict=True)
            manifest = validate_existing(candidate)
            receipt['prior_artifact_snapshot'] = snapshot_existing(candidate, manifest)
            directory = candidate
            stages['media'] = {'status': 'existing_media_verified_unreviewed',
                               'manifest_sha256': sha256(directory / 'manifest.json'),
                               'denoised_sha256': manifest['output_sha256']['denoised.wav'],
                               'cleaned_sha256': manifest['output_sha256']['cleaned.wav'], 'media_rerendered': False}
            finish_inline('media', stages['media'])
        else:
            # Separate clean/export retains a known run and its completed master
            # even when lossy delivery validation fails.
            capture = ((['--capture-interval', *(repr(value) for value in settings.capture_interval)]
                        if settings.capture_interval is not None else [])
                       + (['--capture-review', settings.capture_review] if settings.capture_review is not None else []))
            manifest = stage('media', 'media.py', ['clean', settings.input, settings.profile, *capture],
                             STAGE_TIMEOUTS['media'])
            if manifest is None:
                raise StageError('Media restoration failed; inspect invocation receipt')
            directory = Path(manifest['run_dir']).resolve(strict=True)
        receipt['run_dir'] = str(directory)
        if checkpoint == bootstrap:
            checkpoint = directory / 'demo-invocations' / invocation_id / 'receipt.json'
            prior_demo = directory / 'demo.json'
            if settings.existing_run and 'media' not in skip and prior_demo.is_file():
                if prior_demo.is_symlink() or prior_demo.stat().st_size > MAX_MANIFEST_BYTES:
                    raise ValueError('Prior demo receipt must be a bounded regular file')
                atomic_json(checkpoint.parent / 'prior-demo.json', strict_json(prior_demo.read_text(encoding='utf-8')))
            save()
            # Keep the bootstrap receipt as a durable pointer, never orphaned scratch.
            atomic_json(bootstrap, {'schema_version': 1, 'invocation_id': invocation_id,
                                    'run_dir': str(directory), 'receipt': str(checkpoint)})
        else:
            save()
        if not settings.existing_run:
            stage('export', 'media.py', ['export', str(directory)], STAGE_TIMEOUTS['export'])
        elif 'export' not in skip:
            try:
                delivery = existing_export(directory, manifest)
                stages['export'] = ({'status': 'existing_delivery_hash_verified_unreviewed', 'result': delivery,
                                     'media_rerendered': False} if delivery is not None else
                                    {'status': 'not_available', 'reason': 'Existing-run mode does not create a delivery export'})
                finish_inline('export', stages['export'])
            except (OSError, ValueError, KeyError) as exc:
                stages['export'] = {'status': 'failed', 'reason': str(exc), 'media_rerendered': False}
            save()
        processing_input = str(directory / 'denoised.wav')
        for name, script, arguments in [
            ('rhythm', 'rhythm.py', [processing_input, '--run-dir', str(directory), *options]),
            ('noise', 'guitar_features.py', ['noise', processing_input, '--run-dir', str(directory)]),
            ('tone', 'guitar_features.py', ['tone', processing_input, '--run-dir', str(directory)]),
            ('notes', 'guitar_features.py', ['notes', processing_input, '--run-dir', str(directory)]),
            ('phrases', 'guitar_features.py', ['phrases', processing_input, '--run-dir', str(directory), *options]),
        ]:
            stage(name, script, arguments, STAGE_TIMEOUTS[name],
                  interpreter=analysis_python if name in {'rhythm', 'phrases'} and settings.backend == 'librosa' else None)
        if settings.features == 'extended':
            bpm = ['--bpm', str(settings.bpm)] if settings.bpm is not None else []
            for name, script, arguments, interpreter in [
                ('clicks', 'clicks.py', [processing_input, '--run-dir', str(directory), *bpm], analysis_python),
                ('pitch', 'pitch.py', [processing_input, '--run-dir', str(directory), '--max-analysis-seconds', str(settings.pitch_seconds)], analysis_python),
                ('meter', 'meter.py', ['--run-dir', str(directory)], None),
                ('tonal', 'tonal.py', [str(directory)], None),
                ('comparisons', 'phrase_compare.py', [str(directory)], None),
            ]:
                dependencies = (('rhythm',) if name == 'meter' else ('rhythm', 'phrases', 'pitch')
                                if name == 'tonal' else ('rhythm', 'phrases') if name == 'comparisons' else ())
                if name not in skip and any(stages[dependency]['status'] == 'failed' for dependency in dependencies):
                    dependency_skip(name, dependencies)
                    continue
                stage(name, script, arguments, STAGE_TIMEOUTS[name], interpreter, select=True)
        dag_args = [str(directory)]
        for slot, evidence in selected.items():
            if sha256(directory / evidence['selector']) != evidence['sha256']:
                raise StageError(f'Selected {slot} evidence changed before graph evaluation')
            dag_args += ['--' + slot + '-artifact', evidence['selector']]
        if 'dag' not in skip and (stages['rhythm']['status'] == 'failed' or stages['phrases']['status'] == 'failed'):
            dependency_skip('dag', ('rhythm', 'phrases'))
        else:
            stage('dag', 'dag.py', dag_args, STAGE_TIMEOUTS['dag'])
        if 'markers' not in skip and stages['dag']['status'] in {'failed', 'skipped_dependency_failed'}:
            dependency_skip('markers', ('dag',))
        else:
            stage('markers', 'markers.py', [str(directory)], STAGE_TIMEOUTS['markers'])
        report = stage('report', 'report.py', [str(directory)], STAGE_TIMEOUTS['report'])
        validated = validate_existing(directory)
        if validated['source']['sha256'] != manifest['source']['sha256']:
            raise StageError('Original source identity changed during demo workflow')
        receipt['final_media_identity_verification'] = 'original_source_and_native_PCM_hashes_and_extents_verified'
        failures = [name for name, value in stages.items() if value['status'] in {'failed', 'skipped_dependency_failed'}]
        receipt.update(status='completed_with_stage_failures' if failures else 'completed_unreviewed',
                       failed_stages=failures, report=report)
        if resume_state is not None:
            resume_state['entry'].update(completed_at=now(), outcome_status=receipt['status'])
        save()
        if report is not None and not settings.no_latest:
            atomic_json(ROOT / 'artifacts' / 'latest.json', {'run_dir': str(directory), 'report': str(directory / 'report.html'),
                                                          'demo_receipt': str(checkpoint)})
        export_result = stages.get('export', {}).get('result', {}) or {}
        print(json.dumps({'status': 'rendered_unreviewed', 'analysis_status': receipt['status'],
                          'run_dir': str(directory), 'cleaned_wav': str(directory / 'cleaned.wav'),
                          'video': export_result.get('video'), 'report': str(directory / 'report.html') if report else None,
                          'demo_receipt': str(checkpoint), 'selected_evidence': selected,
                          'stage_status': {key: value['status'] for key, value in stages.items()}}, indent=2))
        return 1 if report is None or 'export' in failures or (settings.features == 'extended' and failures) else 0
    except (StageError, OSError, ValueError, KeyError, ImportError) as exc:
        receipt.update(status='failed_preserving_media', error=str(exc))
        if resume_state is not None:
            resume_state['entry'].update(completed_at=now(), outcome_status=receipt['status'])
        save()
        print(json.dumps({'status': 'error', 'message': str(exc), 'receipt': str(checkpoint)}, allow_nan=False), file=sys.stderr)
        return 1


# --- Resume (ROBUSTNESS_S2 §3): every check below runs before the lock is taken and writes nothing.

def read_bootstrap(invocation_id: str) -> tuple[dict, Path]:
    """Locate the full receipt for an ID without discovery (§3.3)."""
    bootstrap = ROOT / 'artifacts' / 'demo-invocations' / invocation_id / 'receipt.json'
    if not bootstrap.exists() and not bootstrap.is_symlink():
        raise ResumeRefusal('receipt_not_found', f'No bootstrap receipt for invocation {invocation_id}')
    try:
        data = bounded_json_file(bootstrap)
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        raise ResumeRefusal('receipt_invalid', f'Bootstrap receipt is unreadable: {exc}') from exc
    if data.get('invocation_id') != invocation_id:
        raise ResumeRefusal('receipt_invalid', 'Bootstrap receipt invocation_id differs from the requested ID')
    if set(data) == {'schema_version', 'invocation_id', 'run_dir', 'receipt'}:
        run_dir = data['run_dir']
        if not isinstance(run_dir, str) or not Path(run_dir).is_absolute() or str(Path(run_dir).resolve()) != run_dir:
            raise ResumeRefusal('receipt_invalid', 'Pointer run_dir is not an absolute symlink-free path')
        expected = str(Path(run_dir) / 'demo-invocations' / invocation_id / 'receipt.json')
        if data['receipt'] != expected:
            raise ResumeRefusal('receipt_invalid', 'Pointer receipt path differs from <run_dir>/demo-invocations/<id>/receipt.json')
        target = Path(expected)
        try:
            receipt = bounded_json_file(target)
        except (OSError, ValueError, UnicodeError, RecursionError) as exc:
            raise ResumeRefusal('receipt_invalid', f'Run-local receipt is unreadable: {exc}') from exc
        if receipt.get('invocation_id') != invocation_id or receipt.get('run_dir') != run_dir:
            raise ResumeRefusal('receipt_invalid', 'Run-local receipt identity differs from the pointer')
        return receipt, target
    return data, bootstrap


def validate_resume_arguments(recorded) -> dict:
    if not isinstance(recorded, dict) or set(recorded) != set(RESUME_ARGUMENT_KEYS):
        raise ResumeRefusal('receipt_invalid', 'resume_arguments has an unexpected shape')
    mode = recorded['mode']
    checks = [mode in ('new_render', 'existing_run'),
              recorded['backend'] in ('stdlib', 'librosa'), recorded['features'] in ('base', 'extended'),
              isinstance(recorded['profile'], str) and recorded['profile'],
              isinstance(recorded['analysis_python'], str) and recorded['analysis_python'],
              isinstance(recorded['no_latest'], bool),
              recorded['bpm'] is None or (isinstance(recorded['bpm'], (int, float)) and 20 <= recorded['bpm'] <= 400),
              isinstance(recorded['pitch_seconds'], (int, float)) and 1 <= recorded['pitch_seconds'] <= 30,
              recorded['capture_review'] is None or isinstance(recorded['capture_review'], str),
              recorded['capture_interval'] is None or (isinstance(recorded['capture_interval'], list)
                                                      and len(recorded['capture_interval']) == 2
                                                      and all(isinstance(value, (int, float)) and not isinstance(value, bool)
                                                              for value in recorded['capture_interval']))]
    if mode == 'new_render':
        checks += [isinstance(recorded['input_path'], str) and Path(recorded['input_path']).is_absolute(),
                   recorded['existing_run_dir'] is None]
    else:
        checks += [isinstance(recorded['existing_run_dir'], str) and Path(recorded['existing_run_dir']).is_absolute(),
                   recorded['input_path'] is None, recorded['capture_interval'] is None]
    if not all(checks):
        raise ResumeRefusal('receipt_invalid', 'resume_arguments values are outside the recorded contract')
    return recorded


def scan_runs(input_sha256: str | None, lower_bound: datetime | None) -> tuple[list[str], int]:
    """Bounded read-only scan of published runs (§3.5); never adopts or deletes."""
    runs = ROOT / 'artifacts' / 'runs'
    candidates, staging = [], 0
    if not runs.is_dir() or runs.is_symlink():
        return candidates, staging
    with os.scandir(runs) as entries:
        for index, entry in enumerate(entries):
            if index >= MAX_RUN_SCAN_ENTRIES:
                break
            if entry.name.startswith('.staging-'):
                staging += 1
                continue
            if entry.name.startswith('.') or input_sha256 is None or lower_bound is None:
                continue
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
                data = bounded_json_file(Path(entry.path) / 'manifest.json')
                run_id = data.get('run_id')
                stamp = datetime.strptime(run_id[:16], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
            except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
                continue
            if data.get('source', {}).get('sha256') == input_sha256 and stamp >= lower_bound.replace(microsecond=0):
                candidates.append(entry.path)
    return sorted(candidates), staging


def verify_snapshot(directory: Path, snapshot) -> None:
    try:
        hashes = snapshot['artifact_hashes']
        identity = snapshot['snapshot_sha256']
        if snapshot['path'] != f'demo-history/{identity}':
            raise ValueError('snapshot path differs from its content identity')
        if hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest() != identity:
            raise ValueError('snapshot identity differs from recorded hashes')
        target = run_path(directory, snapshot['path'])
        if not target.is_dir() or not (target / 'receipt.json').is_file() or (target / 'receipt.json').is_symlink():
            raise ValueError('snapshot directory or its receipt is missing')
        for name, digest in hashes.items():
            path = run_path(target, name)
            if not path.is_file() or sha256(path) != digest:
                raise ValueError(f'snapshot artifact {name} differs')
    except (KeyError, TypeError, OSError, ValueError) as exc:
        raise ResumeRefusal('snapshot_hash_drift', f'Prior artifact snapshot differs from its receipt: {exc}') from exc


def prepare_resume(invocation_id: str) -> dict:
    if not isinstance(invocation_id, str) or not INVOCATION_ID_PATTERN.fullmatch(invocation_id):
        raise ResumeRefusal('invalid_invocation_id', 'Invocation ID must match YYYYMMDDTHHMMSSZ-<12 hex>')
    receipt, checkpoint = read_bootstrap(invocation_id)
    if 'resume_arguments' not in receipt:
        raise ResumeRefusal('receipt_lacks_resume_arguments',
                            'Receipt predates resume_arguments; resume never infers settings')
    recorded = validate_resume_arguments(receipt['resume_arguments'])
    stages = receipt.get('stages')
    if not isinstance(stages, dict) or not isinstance(receipt.get('selected_evidence'), dict) \
            or any(not isinstance(value, dict) for value in stages.values()):
        raise ResumeRefusal('receipt_invalid', 'Receipt stages or selected_evidence are malformed')
    if receipt.get('mode') != recorded['mode']:
        raise ResumeRefusal('receipt_invalid', 'Receipt mode differs from resume_arguments')
    if receipt.get('status') == 'completed_unreviewed':
        raise ResumeRefusal('invocation_already_terminal', 'Invocation completed without stage failures; nothing to resume')
    orchestrator = receipt.get('orchestrator')
    if not isinstance(orchestrator, dict) or not isinstance(orchestrator.get('pid'), int):
        raise ResumeRefusal('receipt_invalid', 'Receipt orchestrator record is missing')
    if pid_alive(orchestrator['pid']):
        raise ResumeRefusal('orchestrator_may_be_alive',
                            f'Recorded orchestrator PID {orchestrator["pid"]} responds to signal 0 (PID reuse gives a safe false refusal)')
    for name, entry in stages.items():
        execution = entry.get('execution')
        if entry.get('status') in ('running', 'starting') and isinstance(execution, dict) \
                and group_alive(execution.get('pid')):
            raise ResumeRefusal('prior_worker_group_alive',
                                f'Stage {name} worker process group {execution.get("pid")} is still alive; no signal was sent')
    lock = checkpoint.parent / 'resume.lock'
    prior_lock_pid = None
    if lock.exists() or lock.is_symlink():
        try:
            prior_lock_pid = bounded_json_file(lock, 4096)['pid']
        except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
            raise ResumeRefusal('resume_lock_held', f'Resume lock exists but is unreadable: {exc}') from exc
        if pid_alive(prior_lock_pid):
            raise ResumeRefusal('resume_lock_held', f'Resume lock is held by live PID {prior_lock_pid}')
    mode = recorded['mode']
    media_entry = stages.get('media', {})
    media_done = media_entry.get('status') in SUCCESS_TERMINAL
    verified = {'source_sha256': None, 'manifest_sha256': None, 'denoised_sha256': None, 'cleaned_sha256': None}
    if mode == 'new_render':
        source = Path(recorded['input_path'])
        if not isinstance(recorded['input_sha256'], str) or len(recorded['input_sha256']) != 64:
            raise ResumeRefusal('source_hash_drift', 'Recorded input hash is unavailable; the input cannot be re-verified')
        if source.is_symlink() or not source.is_file() or sha256(source) != recorded['input_sha256']:
            raise ResumeRefusal('source_hash_drift', f'Input {source} differs from the recorded sha256')
        verified['source_sha256'] = recorded['input_sha256']
    directory = manifest = None
    if media_done:
        run_dir = receipt.get('run_dir') or (media_entry.get('result') or {}).get('run_dir')
        if not isinstance(run_dir, str) or not Path(run_dir).is_absolute() or str(Path(run_dir).resolve()) != run_dir:
            raise ResumeRefusal('receipt_invalid', 'Recorded run_dir is not an absolute symlink-free path')
        directory = Path(run_dir)
        if 'run_dir' in receipt and checkpoint.parent != directory / 'demo-invocations' / invocation_id:
            raise ResumeRefusal('receipt_invalid', 'Full receipt is not stored under its recorded run_dir')
        manifest_path = directory / 'manifest.json'
        expected_manifest = (media_entry.get('artifacts') or {}).get('manifest.json') or media_entry.get('manifest_sha256')
        try:
            manifest = bounded_json_file(manifest_path, MAX_MANIFEST_BYTES)
            manifest_hash = sha256(manifest_path)
        except (OSError, ValueError, UnicodeError, RecursionError) as exc:
            raise ResumeRefusal('media_hash_drift', f'manifest.json is missing or unreadable: {exc}') from exc
        if not isinstance(expected_manifest, str) or manifest_hash != expected_manifest:
            raise ResumeRefusal('media_hash_drift', 'manifest.json differs from the recorded media stage')
        try:
            source = Path(manifest['source']['path'])
            source_hash = manifest['source']['sha256']
            source_ok = (not source.is_symlink() and source.is_file() and sha256(source) == source_hash
                         and (mode == 'existing_run' or source_hash == recorded['input_sha256']))
        except (KeyError, TypeError, OSError) as exc:
            raise ResumeRefusal('source_hash_drift', f'Manifest source cannot be re-verified: {exc}') from exc
        if not source_ok:
            raise ResumeRefusal('source_hash_drift', 'Original source differs from the manifest or recorded input hash')
        try:
            validate_existing(directory)
        except Exception as exc:  # noqa: BLE001 - every failure here is media identity drift (incl. MediaError).
            raise ResumeRefusal('media_hash_drift', f'Media identity or native-PCM extent check failed: {exc}') from exc
        recorded_media = media_entry.get('artifacts') or {}
        for name, key in (('denoised.wav', 'denoised_sha256'), ('cleaned.wav', 'cleaned_sha256')):
            expected = recorded_media.get(name) or media_entry.get(key)
            if expected != manifest['output_sha256'].get(name):
                raise ResumeRefusal('media_hash_drift', f'{name} differs from the recorded media stage')
        verified.update(source_sha256=source_hash, manifest_sha256=manifest_hash,
                        denoised_sha256=manifest['output_sha256']['denoised.wav'],
                        cleaned_sha256=manifest['output_sha256']['cleaned.wav'])
        if mode == 'existing_run':
            if str(Path(recorded['existing_run_dir']).resolve()) != run_dir:
                raise ResumeRefusal('receipt_invalid', 'Recorded existing_run_dir differs from run_dir')
            verify_snapshot(directory, receipt.get('prior_artifact_snapshot'))
    order = stage_order(recorded['features'])
    skip, rerun, reasons = set(), [], {}
    for name in order:
        entry = stages.get(name)
        if not entry or entry.get('status') not in SUCCESS_TERMINAL or directory is None:
            rerun.append(name)
            reasons[name] = 'not_success_terminal' if entry else 'missing_stage_entry'
            continue
        artifacts = entry.get('artifacts')
        if isinstance(artifacts, dict):
            for relative, digest in artifacts.items():
                try:
                    path = run_path(directory, relative)
                    intact = path.is_file() and not path.is_symlink() and sha256(path) == digest
                except (OSError, ValueError):
                    intact = False
                if not intact:
                    raise ResumeRefusal('stage_artifact_hash_drift',
                                        f'Stage {name} artifact {relative} is missing, a symlink or differs from its recorded sha256')
        if not all(dependency in skip for dependency in stage_dependencies(name, order)):
            rerun.append(name)
            reasons[name] = 'dependency_rerun'
            continue
        if not isinstance(artifacts, dict):
            rerun.append(name)
            reasons[name] = 'artifacts_unrecorded'
            continue
        execution = entry.get('execution')
        if isinstance(execution, dict):
            recorded_worker = execution.get('worker_sha256')
            if not isinstance(recorded_worker, str):
                rerun.append(name)
                reasons[name] = 'worker_hash_unrecorded'
                continue
            worker = ROOT / 'scripts' / STAGE_WORKERS[name]
            if not worker.is_file() or sha256(worker) != recorded_worker:
                raise ResumeRefusal('worker_hash_drift', f'Stage {name} worker {worker.name} changed since it ran')
        skip.add(name)
    lower_bound = None
    if not media_done and mode == 'new_render':
        try:
            lower_bound = datetime.fromisoformat(media_entry.get('started_at') or receipt['created_at'])
        except (KeyError, TypeError, ValueError) as exc:
            raise ResumeRefusal('receipt_invalid', 'Media start time is unrecorded') from exc
    candidates, orphans = scan_runs(recorded['input_sha256'], lower_bound)
    if candidates:
        raise ResumeRefusal('media_outcome_unrecorded_run_dir_exists',
                            'Published run(s) for this source appeared after the media stage started but were never '
                            'recorded; resume never adopts a run by discovery: ' + ', '.join(candidates))
    return {'receipt': receipt, 'checkpoint': checkpoint, 'recorded': recorded, 'lock': lock,
            'prior_lock_pid': prior_lock_pid, 'directory': directory, 'manifest': manifest, 'skip': skip,
            'rerun': rerun, 'reasons': reasons, 'verified': verified, 'orphans': orphans, 'order': order}


def acquire_lock(lock: Path, prior_pid) -> dict:
    payload = json.dumps({'pid': current_pid(), 'acquired_at': now()}).encode()
    if prior_pid is None:
        try:
            descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise ResumeRefusal('resume_lock_held', 'Resume lock appeared concurrently') from exc
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(payload)
        return {'status': 'acquired', 'prior_pid': None}
    staging = lock.with_name(f'.resume.lock.{uuid.uuid4().hex}')
    staging.write_bytes(payload)
    os.chmod(staging, 0o600)
    staging.replace(lock)
    return {'status': 'stale_taken_over', 'prior_pid': prior_pid}


def refuse(invocation_id, reason: str, message: str) -> int:
    shown = invocation_id[:64] if isinstance(invocation_id, str) else None
    print(json.dumps({'status': 'error', 'reason': reason, 'invocation_id': shown, 'message': message}), file=sys.stderr)
    return 1


def resume(invocation_id: str, no_latest: bool = False) -> int:
    try:
        plan = prepare_resume(invocation_id)
        lock_state = acquire_lock(plan['lock'], plan['prior_lock_pid'])
    except ResumeRefusal as exc:
        return refuse(invocation_id, exc.reason, str(exc))
    try:
        receipt, recorded = plan['receipt'], plan['recorded']
        stages, selected = receipt['stages'], receipt['selected_evidence']
        prior_status = receipt.get('status')
        prior_orchestrator = receipt.get('orchestrator')
        for key in ('status', 'error', 'failed_stages', 'final_media_identity_verification', 'report'):
            receipt.pop(key, None)
        receipt['orchestrator'] = {'pid': current_pid(), 'started_at': now()}
        receipt['resource_limits'] = resource_limits()
        history = receipt.setdefault('resume_history', [])
        entry = {'resume_index': len(history) + 1, 'resumed_at': now(), 'orchestrator_pid': current_pid(),
                 'prior_orchestrator': prior_orchestrator, 'prior_status': prior_status,
                 'skipped_stages': [name for name in plan['order'] if name in plan['skip']],
                 'rerun_stages': list(plan['rerun']), 'rerun_reasons': plan['reasons'],
                 'verified': plan['verified'], 'displaced_outputs': {},
                 'orphan_staging_dirs_observed': plan['orphans'], 'lock': lock_state,
                 'no_latest_effective': bool(recorded['no_latest'] or no_latest), **MEMORY_UNKNOWN}
        history.append(entry)
        # Invalidate every rerun stage before any work so a crash during this
        # resume can never leave a stale success-terminal stage downstream of a
        # rerun one (AGENTS.md downstream invalidation).
        for name in plan['rerun']:
            if name == 'media' or name not in stages:
                continue
            superseded = stages[name]
            pending = {'status': 'pending_resume_rerun', 'resume_index': entry['resume_index'],
                       'superseded_status': superseded.get('status')}
            if name in OPTIONAL_OUTPUTS:
                pending['superseded_selection'] = selected.pop(OPTIONAL_OUTPUTS[name][1], None)
            stages[name] = pending
        settings = SimpleNamespace(
            input=recorded['input_path'],
            existing_run=Path(recorded['existing_run_dir']) if recorded['existing_run_dir'] else None,
            profile=recorded['profile'],
            capture_interval=tuple(recorded['capture_interval']) if recorded['capture_interval'] is not None else None,
            capture_review=recorded['capture_review'], bpm=recorded['bpm'], backend=recorded['backend'],
            features=recorded['features'], analysis_python=recorded['analysis_python'],
            pitch_seconds=recorded['pitch_seconds'], no_latest=entry['no_latest_effective'])
        state = {'skip': plan['skip'], 'directory': plan['directory'], 'manifest': plan['manifest'], 'entry': entry}
        return run_pipeline(settings, receipt, plan['checkpoint'], state)
    finally:
        with contextlib.suppress(OSError, ValueError, AttributeError):
            current = json.loads(plan['lock'].read_text())
            if current.get('pid') == current_pid():
                plan['lock'].unlink()


if __name__ == '__main__':
    raise SystemExit(main())
