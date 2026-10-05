#!/usr/bin/env python3
"""Bounded composite calibration: blind generated-audio discovery, then evaluation."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('video_utils_calibration_workflow', ROOT / 'scripts/run_demo.py')
workflow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow)
MAX_JSON_BYTES = 5_000_000
MAX_ARTIFACT_BYTES = 20_000_000
MAX_AUDIO_BYTES = 3_000_000
MAX_TOTAL_JSON_BYTES = 64_000_000
CASE_IDS = ('low32-sustain', 'palm-muted-recurrence', 'legato-recurrence', 'c1-missing-fundamental',
            'tuning-ladder', 'legato-transition', 'sweep-and-polyphony', 'rest-syncopation-tuplets',
            'variable-tempo', 'click-overlap-abstention', 'timing-reference', 'timing-errors')
DURATIONS = (8, 8, 8, 8, 8, 10, 10, 12, 12, 12, 12, 12)
PITCH_PLAN = (('c1-missing-fundamental', 'clean', 8), ('tuning-ladder', 'clean', 8),
              ('legato-transition', 'mix', 6), ('sweep-and-polyphony', 'mix', 8))
WORKERS = ('rhythm.py', 'guitar_features.py', 'phrase_compare.py', 'pitch.py',
           'pitch_evaluate.py', 'phrase_evaluate.py')
SOURCES = WORKERS + ('dag.py', 'run_demo.py', 'calibration_pilot.py')
OPERATIONAL_ENVIRONMENT = ('PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'FFMPEG', 'FFPROBE',
                           'NUMBA_CACHE_DIR', 'SYSTEMROOT', 'SSL_CERT_FILE', 'SSL_CERT_DIR')
AUTHORITY = workflow.AUTHORITY


class PilotError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise PilotError(reason)


def digest(path: Path) -> str:
    return workflow.sha256(path)


def fingerprint(value):
    require(isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value),
            'Expected a lowercase SHA256 fingerprint')
    return value


def local_path(value, base=None, new=False) -> Path:
    require(isinstance(value, (str, Path)) and bool(str(value)), 'Expected local path')
    supplied = Path(value).expanduser()
    require('..' not in supplied.parts and '\\' not in str(value), 'Path traversal or aliases prohibited')
    path = supplied if supplied.is_absolute() else (base or ROOT) / supplied
    allowed = (ROOT / 'artifacts/benchmarks').resolve()
    require(path.is_relative_to(allowed) and path != allowed, 'Path must be beneath artifacts/benchmarks')
    current = allowed
    require(not current.is_symlink(), 'Benchmark root must not be a symlink')
    for part in path.relative_to(allowed).parts:
        current = current / part
        require(not current.is_symlink(), 'Local paths must not contain a symlink')
    require(not path.exists() if new else path.is_file(), 'Output must be new' if new else 'Missing regular input file')
    return path


def read_json(path: Path, expected=None, limit=MAX_JSON_BYTES) -> tuple[dict, str]:
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= limit, 'JSON file bound or type invalid')
    before = digest(path)
    if expected is not None:
        require(before == fingerprint(expected), 'JSON receipt hash mismatch')
    with path.open('rb') as handle:
        content = handle.read(limit + 1)
    require(len(content) <= limit, 'JSON grew beyond its byte bound')
    try:
        result = workflow.strict_json(content.decode('utf-8'))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise PilotError('JSON must be a single finite object') from exc
    require(digest(path) == before, 'JSON changed during read')
    return result, before


def audio_identity(path: Path, expected: str, duration: int) -> dict:
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_AUDIO_BYTES,
            'Audio file type or size exceeds generated-bank bound')
    require(digest(path) == fingerprint(expected), 'Generated audio hash mismatch')
    with wave.open(str(path), 'rb') as handle:
        info = {'sample_rate': handle.getframerate(), 'channels': handle.getnchannels(),
                'sample_count': handle.getnframes(), 'sample_width_bytes': handle.getsampwidth()}
    require(info == {'sample_rate': 48000, 'channels': 1, 'sample_count': duration * 48000,
                     'sample_width_bytes': 2}, 'Generated audio native PCM header mismatch')
    return {**info, 'sha256': expected, 'bytes': path.stat().st_size}


def load_bank(path: Path) -> tuple[dict, list[dict], dict]:
    bank, bank_hash = read_json(path)
    require(bank.get('schema_version') == 2 and bank.get('suite') == 'technical-v2', 'Expected technical-v2 fixture bank')
    cases = bank.get('cases')
    require(isinstance(cases, list) and len(cases) == bank.get('case_count') == 12,
            'Pilot requires all twelve fixture cases')
    require(tuple(item.get('id') for item in cases) == CASE_IDS
            and tuple(item.get('duration_seconds') for item in cases) == DURATIONS
            and bank.get('total_duration_seconds') == 120, 'Fixture case plan or 120-second audio budget differs')
    registry = ROOT / 'program/instrument.json'
    require(registry.is_file() and not registry.is_symlink() and registry.stat().st_size <= 64_000,
            'Instrument registry missing, aliased or oversized')
    registry_hash = digest(registry)
    require(bank.get('instrument_registry_sha256') == registry_hash, 'Fixture bank instrument registry is stale')
    identities = {str(path): bank_hash, str(registry): registry_hash}
    total_json = path.stat().st_size
    jobs = []
    for case, duration in zip(cases, DURATIONS):
        truth_path = local_path(case['truth'], path.parent)
        truth, truth_hash = read_json(truth_path, case['truth_sha256'])
        total_json += truth_path.stat().st_size
        require(total_json <= MAX_TOTAL_JSON_BYTES, 'Fixture metadata exceeds aggregate JSON bound')
        require(truth.get('schema_version') == 2 and truth.get('id') == case['id']
                and truth.get('instrument_registry_sha256') == registry_hash, 'Fixture truth identity differs from bank')
        source = truth.get('source', {})
        require(source.get('sample_rate') == 48000 and source.get('channels') == 1
                and source.get('sample_count') == duration * 48000 and source.get('duration_seconds') == duration
                and source.get('audio_start_seconds') == 0
                and source.get('origin_evidence') == 'synthetic_generator_sample_zero',
                'Generated source identity or sample-zero evidence missing')
        identities[str(truth_path)] = truth_hash
        components = {}
        requested_components = ('mix', 'clean') if any(plan[0] == case['id'] and plan[1] == 'clean' for plan in PITCH_PLAN) else ('mix',)
        for component in requested_components:
            receipt = truth.get('artifacts', {}).get(component, {})
            audio = local_path(receipt['path'], path.parent)
            info = audio_identity(audio, receipt['sha256'], duration)
            require(receipt.get('bytes') == info['bytes'], 'Component byte-size receipt differs')
            if component == 'mix':
                require(source.get('path') == receipt['path'] and source.get('sha256') == info['sha256'],
                        'Source mixture differs from component receipt')
            identities[str(audio)] = info['sha256']
            components[component] = {'path': audio, **info}
        jobs.append({'id': case['id'], 'duration_seconds': duration,
                     'truth_path': truth_path, 'truth_sha256': truth_hash, 'components': components})
    return bank, jobs, identities


@contextmanager
def operational_environment():
    """A dedicated sequential controller exposes no fixture labels in child env."""
    original = dict(os.environ)
    minimal = {name: original[name] for name in OPERATIONAL_ENVIRONMENT if name in original}
    minimal['PYTHONDONTWRITEBYTECODE'] = '1'
    try:
        os.environ.clear()
        os.environ.update(minimal)
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


def artifact_receipt(path: Path, output: Path, source_hash: str, kind: str) -> dict:
    path = local_path(path)
    require(path.is_relative_to(output), 'Discovery receipt escaped pilot output')
    payload, identity = read_json(path, limit=MAX_ARTIFACT_BYTES)
    actual = payload.get('analysis_input_sha256') if kind == 'comparisons' else payload.get('source', {}).get('sha256')
    require(actual == source_hash, 'Discovery artifact source hash differs from raw input')
    if kind == 'comparisons':
        require(payload.get('source_sha256') == source_hash, 'Comparison original source differs')
    settings = payload.get('settings', payload.get('configuration', payload.get('analysis', {})))
    require(isinstance(settings, dict), 'Discovery settings must be an object')
    settings_hash = hashlib.sha256(json.dumps(settings, sort_keys=True, allow_nan=False).encode()).hexdigest()
    if payload.get('settings_sha256') is not None:
        require(payload['settings_sha256'] == settings_hash, 'Producer settings hash mismatch')
    return {'path': path.relative_to(output).as_posix(), 'sha256': identity, 'settings_sha256': settings_hash}


def run_pilot(fixture_index: Path, output: Path, analysis_python: str,
              backend='librosa', overall_timeout=900) -> dict:
    fixture_index = local_path(fixture_index)
    output = local_path(output, new=True)
    bank, cases, input_identities = load_bank(fixture_index)
    require(not output.exists(), 'Pilot output must be a fresh directory')
    require(backend in {'stdlib', 'librosa'}, 'Unknown discovery backend')
    require(isinstance(analysis_python, str) and analysis_python and '\0' not in analysis_python,
            'Explicit analysis interpreter required; no dependency installation occurs')
    require(type(overall_timeout) in (int, float) and 30 <= overall_timeout <= 1800, 'Overall deadline must be 30–1800 seconds')
    source_hashes = {name: digest(ROOT / 'scripts' / name) for name in SOURCES}
    worker_hashes = {name: source_hashes[name] for name in WORKERS}
    bank_hash = input_identities[str(fixture_index)]
    registry_hash = bank['instrument_registry_sha256']
    output.mkdir(parents=True, mode=0o700)
    (output / 'inputs').mkdir(mode=0o700)
    (output / 'sources').mkdir(mode=0o700)
    for name in SOURCES:
        shutil.copyfile(ROOT / 'scripts' / name, output / 'sources' / name)
        require(digest(output / 'sources' / name) == source_hashes[name], 'Worker source changed during snapshot')
    receipt = {'schema_version': 1, 'status': 'running', 'created_at': datetime.now(timezone.utc).isoformat(),
               'bank_index': str(fixture_index), 'bank_index_sha256': bank_hash,
               'instrument_registry_sha256': registry_hash, 'worker_sha256': worker_hashes,
               'source_sha256': source_hashes,
               'bank_producer_identity': {key: bank.get(key) for key in ('generator_sha256', 'legacy_generator_sha256', 'configuration_sha256')},
               'settings': {'backend': backend, 'tempo_seed': None, 'reference_grid_supplied': False,
                            'discovery_audio_seconds': 120, 'pitch_coverage_budget_seconds': 30,
                            'worker_timeout_seconds': 120, 'pitch_timeout_seconds': 240,
                            'overall_timeout_seconds': overall_timeout, 'math_threads': 2,
                            'truth_input_scope': 'evaluation_only', 'discovery_audio_aliases': 'opaque_byte_identical_copies'},
               'cases': [], 'pitch_jobs': [], 'evaluations': {}, 'listening_accepted': False,
               'ground_truth_scope': 'generator_only_not_musician', 'authority': AUTHORITY + '/R-N13'}
    phrase_index = {'schema_version': 1, 'bank_index_sha256': bank_hash,
                    'instrument_registry_sha256': registry_hash, 'cases': []}
    pitch_index = {'schema_version': 1, 'bank_index_sha256': bank_hash,
                   'instrument_registry_sha256': registry_hash, 'budget_seconds': 30, 'jobs': []}
    started = time.monotonic()
    aliases = {}
    failures = []

    def save():
        workflow.atomic_json(output / 'pilot.json', receipt)
        workflow.atomic_json(output / 'phrase-pilot-index.json', phrase_index)
        workflow.atomic_json(output / 'pitch-pilot-index.json', pitch_index)

    def alias(component):
        identity = component['sha256']
        if identity not in aliases:
            destination = output / 'inputs' / f'audio-{len(aliases)+1:02d}.wav'
            with component['path'].open('rb') as source, destination.open('xb') as target:
                shutil.copyfileobj(source, target, length=65536)
            os.chmod(destination, 0o600)
            require(digest(destination) == identity, 'Audio changed while making opaque input alias')
            aliases[identity] = destination
        return aliases[identity]

    def stage(row, name, script, arguments, timeout=120, optional_interpreter=False):
        execution = {}
        row['stages'][name] = {'status': 'running', 'execution': execution}
        save()
        remaining = overall_timeout - (time.monotonic() - started)
        try:
            require(remaining > 0, 'Pilot overall deadline reached; remaining jobs retained as failed receipts')
            with operational_environment():
                result = workflow.invoke(script, arguments, min(timeout, remaining),
                                         analysis_python if optional_interpreter else None, execution)
            require(execution['worker_sha256'] == worker_hashes[script], 'Worker differs from pilot source snapshot')
            row['stages'][name].update(status='completed_measurements', result=result)
            save()
            return result, execution
        except (workflow.StageError, OSError, ValueError, KeyError) as exc:
            row['stages'][name].update(status='failed', reason=str(exc))
            if isinstance(exc, workflow.StageError):
                row['stages'][name]['execution'] = exc.receipt
            failures.append(f'{row["job_id"]}/{name}')
            save()
            return None, execution

    def source_manifest(directory, audio, component):
        # Generic PCM/sample-zero facts only. No case ID, component class, score,
        # pitch, articulation, phrase boundary, attack or warp truth enters here.
        workflow.atomic_json(directory / 'manifest.json', {'schema_version': 1,
            'source': {'path': str(audio), 'sha256': component['sha256']}, 'output_sha256': {},
            'pcm': {key: component[key] for key in ('sample_rate', 'channels', 'sample_count')},
            'timeline': {'audio_start_seconds': 0., 'no_time_stretch': True,
                         'origin_basis': 'generated_PCM_sample_zero'},
            'scope': 'raw_generated_source_not_restored_not_musician_ground_truth'})

    save()
    for position, case in enumerate(cases, 1):
        row = {'job_id': f'case-{position:02d}', 'case_id': case['id'], 'stages': {}, 'status': 'running'}
        receipt['cases'].append(row)
        directory = output / 'discovery' / row['job_id']
        directory.mkdir(parents=True, mode=0o700)
        component = case['components']['mix']
        audio = alias(component)
        source_manifest(directory, audio, component)
        try:
            result, _ = stage(row, 'rhythm', 'rhythm.py', [str(audio), '--run-dir', str(directory), '--backend', backend], optional_interpreter=backend == 'librosa')
            if result is None:
                raise PilotError('Rhythm discovery failed; dependent discovery skipped')
            analysis_path = local_path(result['analysis_json'])
            require(analysis_path == directory / 'analysis.json', 'Rhythm returned a different run artifact')
            analysis = artifact_receipt(analysis_path, output, component['sha256'], 'analysis')
            result, _ = stage(row, 'phrases', 'guitar_features.py', ['phrases', str(audio), '--run-dir', str(directory), '--backend', backend], optional_interpreter=backend == 'librosa')
            if result is None:
                raise PilotError('Phrase discovery failed; comparison skipped')
            # This existing primitive prints its payload; its artifact path is a
            # fixed documented CLI contract, not discovered through directory scans.
            phrases = artifact_receipt(directory / 'phrases.json', output, component['sha256'], 'phrases')
            result, _ = stage(row, 'comparisons', 'phrase_compare.py', [str(directory)])
            comparisons = None
            if result is not None:
                comparison_path = local_path(result['comparisons_json'])
                require(comparison_path == directory / 'phrase-comparisons.json', 'Comparison receipt escaped its run')
                comparisons = artifact_receipt(comparison_path, output, component['sha256'], 'comparisons')
            phrase_index['cases'].append({'id': case['id'], 'run_dir': directory.relative_to(output).as_posix(),
                                          'analysis': analysis, 'phrases': phrases, 'comparisons': comparisons})
            row['status'] = 'completed_measurements' if comparisons is not None else 'partial_comparison_failed'
        except (OSError, ValueError, KeyError) as exc:
            row.update(status='failed', reason=str(exc))
            failures.append(row['job_id'])
        save()

    for position, (case_id, component_name, budget) in enumerate(PITCH_PLAN, 1):
        case = next(item for item in cases if item['id'] == case_id)
        component = case['components'][component_name]
        row = {'job_id': f'pitch-{position:02d}', 'case_id': case_id, 'component': component_name,
               'requested_budget_seconds': budget, 'stages': {}, 'status': 'running'}
        receipt['pitch_jobs'].append(row)
        directory = output / 'discovery' / row['job_id']
        directory.mkdir(parents=True, mode=0o700)
        audio = alias(component)
        source_manifest(directory, audio, component)
        try:
            result, execution = stage(row, 'pitch', 'pitch.py', [str(audio), '--run-dir', str(directory),
                                      '--max-analysis-seconds', str(budget), '--start-seconds', '0'],
                                      timeout=240, optional_interpreter=True)
            if result is None:
                raise PilotError('Pitch discovery failed')
            pitch_path = local_path(result['pitch_json'])
            require(pitch_path == directory / 'pitch.json', 'Pitch returned a different run artifact')
            payload, pitch_hash = read_json(pitch_path, limit=MAX_ARTIFACT_BYTES)
            require(payload.get('source', {}).get('sha256') == component['sha256']
                    and payload.get('source', {}).get('path') == str(audio), 'Pitch input alias identity differs')
            provenance = payload['provenance']
            require(provenance['worker_sha256'] == execution['worker_sha256'], 'Pitch producer worker hash differs')
            observed = payload['analysis']['coverage_spans_audio_relative']
            require(observed == [{'start_seconds': 0.0, 'end_seconds': float(budget)}], 'Pitch coverage differs from agreed aggregate plan')
            versions = [excerpt['versions'] for excerpt in payload['observations']['analyzed_excerpts']]
            require(versions and all(item == versions[0] for item in versions), 'Pitch excerpts contain inconsistent library versions')
            job = {'case_id': case_id, 'component': component_name,
                   'input_path': audio.relative_to(output).as_posix(), 'input_sha256': component['sha256'],
                   'mixture_parent_path': str(case['components']['mix']['path']), 'mixture_parent_sha256': case['components']['mix']['sha256'],
                   'truth_path': str(case['truth_path']), 'truth_sha256': case['truth_sha256'],
                   'pitch_path': pitch_path.relative_to(output).as_posix(), 'pitch_sha256': pitch_hash,
                   'command': execution['command'], 'worker_sha256': execution['worker_sha256'],
                   'versions': {**versions[0], 'python': provenance['python_version']},
                   'requested_start_seconds': 0, 'requested_budget_seconds': budget,
                   'observed_coverage_spans': observed, 'wall_seconds': execution['elapsed_seconds'],
                   'status': 'completed_measurements'}
            pitch_index['jobs'].append(job)
            row['status'] = 'completed_measurements'
            row['pitch_receipt'] = {'path': job['pitch_path'], 'sha256': pitch_hash}
        except (OSError, ValueError, KeyError) as exc:
            row.update(status='failed', reason=str(exc))
            failures.append(row['job_id'])
        save()

    # Truth is intentionally introduced only now, to standalone evaluation
    # primitives, after the discovery indexes carry explicit artifact receipts.
    for name, script, index_path, ready in [
        ('phrases', 'phrase_evaluate.py', output / 'phrase-pilot-index.json', len(phrase_index['cases']) == 12),
        ('pitch', 'pitch_evaluate.py', output / 'pitch-pilot-index.json', len(pitch_index['jobs']) == 4),
    ]:
        row = {'job_id': 'evaluation-' + name, 'stages': {}}
        receipt['evaluations'][name] = row
        if not ready:
            row.update(status='skipped_incomplete_discovery', reason='No partial pilot index is presented as complete calibration')
            failures.append(row['job_id'])
            save()
            continue
        index_hash = digest(index_path)
        evaluation_dir = output / ('evaluation-' + name)
        evaluation_path = evaluation_dir / ('phrase-evaluation.json' if name == 'phrases' else 'pitch-calibration.json')
        result, _ = stage(row, 'evaluate', script, ['--fixture-index', str(fixture_index),
                                '--pilot-index', str(index_path), '--output', str(evaluation_dir), '--summary'])
        row['status'] = 'completed_generated_reference_evaluation' if result is not None else 'failed'
        try:
            require(digest(index_path) == index_hash, 'Evaluator modified its discovery index')
            if result is not None:
                require(local_path(result['evaluation_json']) == evaluation_path, 'Evaluator returned an unexpected artifact')
            if evaluation_path.exists():
                evaluation_path = local_path(evaluation_path)
                evaluation, evaluation_hash = read_json(evaluation_path, limit=MAX_ARTIFACT_BYTES)
                for key, expected in [('bank_index_sha256', bank_hash), ('pilot_index_sha256', index_hash)]:
                    require(evaluation.get(key, expected) == expected, 'Evaluation index binding differs')
                row['artifact'] = {'path': evaluation_path.relative_to(output).as_posix(), 'sha256': evaluation_hash,
                                   'status': evaluation.get('status'), 'hard_gates_passed': evaluation.get('hard_gates_passed'),
                                   'bank_index_sha256': bank_hash, 'pilot_index_sha256': index_hash}
                if result is not None:
                    require(evaluation.get('hard_gates_passed') is True, 'Evaluation did not pass hard gates')
            else:
                require(result is None, 'Evaluator reported success without its exact artifact')
        except (OSError, ValueError, KeyError) as exc:
            row.update(status='failed', reason=str(exc))
            failures.append(row['job_id'] + '/artifact')
        save()
    def unchanged(path, expected):
        try:
            return path.is_file() and not path.is_symlink() and digest(path) == expected
        except OSError:
            return False
    for path, expected in input_identities.items():
        if not unchanged(Path(path), expected):
            failures.append('input_changed:' + path)
    for script, expected in source_hashes.items():
        if not unchanged(ROOT / 'scripts' / script, expected):
            failures.append('worker_changed:' + script)
    for expected, path in aliases.items():
        if not unchanged(path, expected):
            failures.append('alias_changed:' + str(path))
    receipt.update(status='completed_generated_calibration_pilot' if not failures else 'partial_calibration_pilot',
                   failures=failures, elapsed_seconds=time.monotonic()-started,
                   pitch_observed_budget_seconds=sum(job['requested_budget_seconds'] for job in pitch_index['jobs']),
                   original_input_hashes_preserved=not any(item.startswith('input_changed:') for item in failures),
                   original_source_and_component_hashes=input_identities,
                   discovery_alias_hashes_preserved=not any(item.startswith('alias_changed:') for item in failures),
                   limitations=['Generated reference evaluation is not musician, real-guitar or listening acceptance.',
                                'Opaque discovery inputs omit truth labels; this is input isolation, not a filesystem security sandbox.',
                                'Bounded candidate algorithms may abstain, miss structure, or make octave and onset errors.'])
    save()
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture-index', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--analysis-python', required=True)
    parser.add_argument('--backend', choices=('stdlib', 'librosa'), default='librosa')
    parser.add_argument('--overall-timeout', type=int, default=900)
    args = parser.parse_args(argv)
    output = None
    try:
        index = local_path(args.fixture_index)
        output = local_path(args.output, new=True)
        receipt = run_pilot(index, output, args.analysis_python, args.backend, args.overall_timeout)
        print(json.dumps({'status': receipt['status'], 'output': str(output), 'receipt': str(output / 'pilot.json'),
                          'phrase_pilot_index': str(output / 'phrase-pilot-index.json'),
                          'pitch_pilot_index': str(output / 'pitch-pilot-index.json'),
                          'failures': receipt['failures'], 'listening_accepted': False}, allow_nan=False, indent=2))
        return 0 if receipt['status'] == 'completed_generated_calibration_pilot' else 1
    except (OSError, ValueError, KeyError, wave.Error) as exc:
        # Any already checkpointed jobs survive a top-level controller failure.
        if output is not None and output.is_dir():
            workflow.atomic_json(output / 'controller-failure.json', {'status': 'controller_failed_preserving_artifacts',
                                'error': str(exc), 'authority': AUTHORITY + '/R-N13'})
        print(json.dumps({'status': 'error', 'error': str(exc), 'output': str(output) if output else None}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
