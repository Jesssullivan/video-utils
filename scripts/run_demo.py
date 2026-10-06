#!/usr/bin/env python3
"""Render or extend a private demo with explicitly selected analysis evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time
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
           interpreter: str | None = None, execution: dict | None = None) -> dict:
    """Actively bound both pipes and the entire owned worker process group."""
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', nargs='?')
    parser.add_argument('--existing-run', type=Path, help='Extend validated media without rerendering')
    parser.add_argument('--profile', default=DEFAULT_PROFILE,
                        help='Profile name or path; default fuller requires --capture-interval START END')
    parser.add_argument('--capture-interval', nargs=2, type=float, metavar=('START', 'END'),
                        help='Reviewed per-take noise capture interval passed to media.py clean')
    parser.add_argument('--capture-review', help='Non-empty review text for --capture-interval')
    parser.add_argument('--bpm', type=float, help='Approximate operator pulse; not an intended score')
    parser.add_argument('--backend', choices=('stdlib', 'librosa'), default='stdlib')
    parser.add_argument('--features', choices=('base', 'extended'), default='base')
    parser.add_argument('--analysis-python', help='Explicit interpreter with already-installed optional dependencies')
    parser.add_argument('--pitch-seconds', type=float, default=20, help='Bounded excerpt coverage, 1–30 seconds')
    parser.add_argument('--no-latest', action='store_true', help='Keep the operator latest pointer unchanged, useful for fixtures')
    args = parser.parse_args(argv)
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
    options = ['--backend', args.backend]
    if args.bpm is not None:
        options += ['--bpm', str(args.bpm)]
    invocation_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:12]
    stages = {}
    selected = {}
    receipt = {'schema_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
               'invocation_id': invocation_id, 'mode': 'existing_run' if args.existing_run else 'new_render',
               'analysis_settings': {'backend': args.backend, 'operator_bpm': args.bpm,
                                     'features': args.features, 'analysis_interpreter': analysis_python,
                                     'pitch_max_analysis_seconds': args.pitch_seconds},
               'stages': stages, 'selected_evidence': selected, 'listening_accepted': False,
               'authority': 'Operator approved implementation; ' + AUTHORITY + '/R-N13'}
    checkpoint = ROOT / 'artifacts' / 'demo-invocations' / invocation_id / 'receipt.json'
    directory = None

    def save():
        atomic_json(checkpoint, receipt)
        if directory is not None:
            atomic_json(directory / 'demo.json', receipt)

    def stage(name, script, arguments, timeout=600, interpreter=None, select=False):
        print(f'Running {name}…', file=sys.stderr)
        execution = {}
        stages[name] = {'status': 'running', 'execution': execution}
        save()
        try:
            if args.existing_run and name in OVERWRITTEN_OUTPUTS:
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
            data = invoke(script, arguments, timeout, interpreter, execution)
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
        except (StageError, OSError, ValueError, KeyError) as exc:
            stages[name].update(status='failed', reason=str(exc))
            if isinstance(exc, StageError):
                stages[name]['execution'] = exc.receipt
        save()
        return stages[name].get('result') if stages[name]['status'] != 'failed' else None

    try:
        save()
        if args.existing_run:
            if args.existing_run.is_symlink():
                raise ValueError('Existing run directory must not be a symlink')
            candidate = args.existing_run.expanduser().resolve(strict=True)
            manifest = validate_existing(candidate)
            receipt['prior_artifact_snapshot'] = snapshot_existing(candidate, manifest)
            directory = candidate
            stages['media'] = {'status': 'existing_media_verified_unreviewed',
                               'manifest_sha256': sha256(directory / 'manifest.json'),
                               'denoised_sha256': manifest['output_sha256']['denoised.wav'],
                               'cleaned_sha256': manifest['output_sha256']['cleaned.wav'], 'media_rerendered': False}
        else:
            # Separate clean/export retains a known run and its completed master
            # even when lossy delivery validation fails.
            capture = ((['--capture-interval', *(repr(value) for value in args.capture_interval)]
                        if args.capture_interval is not None else [])
                       + (['--capture-review', args.capture_review] if args.capture_review is not None else []))
            manifest = stage('media', 'media.py', ['clean', args.input, args.profile, *capture], 1200)
            if manifest is None:
                raise StageError('Media restoration failed; inspect invocation receipt')
            directory = Path(manifest['run_dir']).resolve(strict=True)
        receipt['run_dir'] = str(directory)
        old_checkpoint = checkpoint
        checkpoint = directory / 'demo-invocations' / invocation_id / 'receipt.json'
        prior_demo = directory / 'demo.json'
        if args.existing_run and prior_demo.is_file():
            if prior_demo.is_symlink() or prior_demo.stat().st_size > MAX_MANIFEST_BYTES:
                raise ValueError('Prior demo receipt must be a bounded regular file')
            atomic_json(checkpoint.parent / 'prior-demo.json', strict_json(prior_demo.read_text(encoding='utf-8')))
        save()
        # Keep the bootstrap receipt as a durable pointer, never orphaned scratch.
        atomic_json(old_checkpoint, {'schema_version': 1, 'invocation_id': invocation_id,
                                     'run_dir': str(directory), 'receipt': str(checkpoint)})
        if not args.existing_run:
            stage('export', 'media.py', ['export', str(directory)], 1200)
        else:
            try:
                delivery = existing_export(directory, manifest)
                stages['export'] = ({'status': 'existing_delivery_hash_verified_unreviewed', 'result': delivery,
                                     'media_rerendered': False} if delivery is not None else
                                    {'status': 'not_available', 'reason': 'Existing-run mode does not create a delivery export'})
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
            stage(name, script, arguments, interpreter=analysis_python if name in {'rhythm', 'phrases'} and args.backend == 'librosa' else None)
        if args.features == 'extended':
            bpm = ['--bpm', str(args.bpm)] if args.bpm is not None else []
            for name, script, arguments, interpreter in [
                ('clicks', 'clicks.py', [processing_input, '--run-dir', str(directory), *bpm], analysis_python),
                ('pitch', 'pitch.py', [processing_input, '--run-dir', str(directory), '--max-analysis-seconds', str(args.pitch_seconds)], analysis_python),
                ('meter', 'meter.py', ['--run-dir', str(directory)], None),
                ('tonal', 'tonal.py', [str(directory)], None),
                ('comparisons', 'phrase_compare.py', [str(directory)], None),
            ]:
                dependencies = (('rhythm',) if name == 'meter' else ('rhythm', 'phrases', 'pitch')
                                if name == 'tonal' else ('rhythm', 'phrases') if name == 'comparisons' else ())
                if any(stages[dependency]['status'] == 'failed' for dependency in dependencies):
                    stages[name] = {'status': 'skipped_dependency_failed', 'dependencies': list(dependencies)}
                    save()
                    continue
                stage(name, script, arguments, 300, interpreter, select=True)
        dag_args = [str(directory)]
        for slot, evidence in selected.items():
            if sha256(directory / evidence['selector']) != evidence['sha256']:
                raise StageError(f'Selected {slot} evidence changed before graph evaluation')
            dag_args += ['--' + slot + '-artifact', evidence['selector']]
        if stages['rhythm']['status'] == 'failed' or stages['phrases']['status'] == 'failed':
            stages['dag'] = {'status': 'skipped_dependency_failed', 'dependencies': ['rhythm', 'phrases']}
            save()
        else:
            stage('dag', 'dag.py', dag_args, 180)
        if stages['dag']['status'] in {'failed', 'skipped_dependency_failed'}:
            stages['markers'] = {'status': 'skipped_dependency_failed', 'dependencies': ['dag']}
            save()
        else:
            stage('markers', 'markers.py', [str(directory)], 180)
        report = stage('report', 'report.py', [str(directory)], 180)
        validated = validate_existing(directory)
        if validated['source']['sha256'] != manifest['source']['sha256']:
            raise StageError('Original source identity changed during demo workflow')
        receipt['final_media_identity_verification'] = 'original_source_and_native_PCM_hashes_and_extents_verified'
        failures = [name for name, value in stages.items() if value['status'] in {'failed', 'skipped_dependency_failed'}]
        receipt.update(status='completed_with_stage_failures' if failures else 'completed_unreviewed',
                       failed_stages=failures, report=report)
        save()
        if report is not None and not args.no_latest:
            atomic_json(ROOT / 'artifacts' / 'latest.json', {'run_dir': str(directory), 'report': str(directory / 'report.html'),
                                                          'demo_receipt': str(checkpoint)})
        export_result = stages.get('export', {}).get('result', {})
        print(json.dumps({'status': 'rendered_unreviewed', 'analysis_status': receipt['status'],
                          'run_dir': str(directory), 'cleaned_wav': str(directory / 'cleaned.wav'),
                          'video': export_result.get('video'), 'report': str(directory / 'report.html') if report else None,
                          'demo_receipt': str(checkpoint), 'selected_evidence': selected,
                          'stage_status': {key: value['status'] for key, value in stages.items()}}, indent=2))
        return 1 if report is None or 'export' in failures or (args.features == 'extended' and failures) else 0
    except (StageError, OSError, ValueError, KeyError, ImportError) as exc:
        receipt.update(status='failed_preserving_media', error=str(exc))
        save()
        print(json.dumps({'status': 'error', 'message': str(exc), 'receipt': str(checkpoint)}, allow_nan=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
