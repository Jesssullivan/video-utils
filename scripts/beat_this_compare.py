#!/usr/bin/env python3
"""Experimental Beat This (CPJKU, final0) beat/downbeat comparator; never a default.

Consumes an already-installed, registry-verified checkpoint through the isolated
Linux CPU runtime from ``beat_this_runtime_setup.py``. Fails closed with typed
refusals and never downloads. Reports beats, downbeats, the half/double relation
against the project click grid and, for generated fixtures only, F-measure at
70 ms. ``meter_claim`` is always ``"none"``. Also hosts the deterministic
``s3-beat-1`` fixture generator and the seal-before-truth experiment harness.
Contract: docs/spec/sprints/MODEL_LANES_S3.md (sections 3 and 7).

Top-level imports are stdlib only: the same file runs as the inference worker
inside the isolated runtime (``--infer-task``).
"""
from __future__ import annotations

import argparse
import array
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import secrets
import statistics
import struct
import subprocess
import sys
import time
import urllib.parse
import wave

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
MODEL_ID = 'cpjku-beat-this-final0'
CHECKPOINT = 'final0'
ANALYSIS_RATE = 22050
MODEL_FPS = 50
F_TOLERANCE = 0.07
RELATION_TOLERANCE = 0.04
MIN_BEATS_FOR_RATIO = 4
RELATIONS = (('1/3', 1 / 3), ('1/2', 1 / 2), ('2/3', 2 / 3), ('1', 1.0), ('3/2', 3 / 2), ('2', 2.0), ('3', 3.0))
LIMITS = {'input_seconds': 300, 'deadline_seconds': 600, 'rss_bytes': 2 * 1024**3, 'manifest_bytes': 1024**2,
          'registry_bytes': 1024**2, 'max_model_bytes': 2 * 1024**3, 'events': 20000, 'log_bytes': 10 * 1024**2,
          'threads': 2}
RUNS_REL = Path('artifacts/runs')
LANE_REL = Path('artifacts/s2/model_lanes')
FIXTURES_REL = LANE_REL / 'fixtures'
UNREACHABLE_PROXY = 'http://127.0.0.1:9'

# The exact unknown/abstain values of contract 3.2 (13) plus two explicit nulls
# (intended tempo, bar lines) the lane adds so no consumer infers them (15).
UNKNOWN_FIELDS = {
    'meter_claim': 'none', 'time_signature': None,
    'downbeat_semantics': 'model_hypothesis_not_bar_line',
    'tempo_identity': 'unknown', 'physical_capture_latency': 'uncalibrated',
    'real_take_accuracy': 'unknown', 'note_correctness': None, 'performance_issue': None,
    'expected_rhythm_reference': None, 'listening_accepted': False, 'default_adoption': False,
    'claim_class': 'model_output_measurement', 'confidence_kind': 'uncalibrated_model_activation',
    'intended_tempo_bpm': None, 'bar_lines': None,
}
LIMITATIONS = [
    'Beats from a mono mixture with an in-room click are model hypotheses, not identified pulses of the performance.',
    'Downbeat spacing does not establish meter, time signature or bar lines; the model was trained mostly on 3/4 and 4/4 popular music.',
    'Half/double relations are arithmetic on model and heuristic-grid outputs, not an identification of intended tempo.',
    'Generated-fixture F-measure measures agreement with constructed truth only; real-take accuracy is unknown.',
    'Upstream LogMelSpect starts at f_min 30 Hz on a 22.05 kHz downmix; ~32 Hz content sits at the bottom mel band and protection of that content is not implied.',
    'No DBN postprocessing (madmom not qualified); upstream minimal peak-picking at 50 frames per second.',
]


class Refused(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def refusal(code: str, message: str) -> dict:
    return {'schema_version': 1, 'status': 'refused', 'refusal_code': code, 'message': message,
            'model_id': MODEL_ID, 'network_used': False, 'model_acquired': False, 'default_adoption': False}


def sha256_file(path: Path) -> str:
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_bounded(path: Path, limit: int) -> bytes:
    with Path(path).open('rb') as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError('file exceeds byte bound')
    return data


def finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


# --------------------------------------------------------------------------- WAV I/O (stdlib)

def wav_header(path: Path) -> dict:
    """Parse a RIFF/WAVE header: PCM 16/24/32-bit or IEEE float32, incl. WAVE_FORMAT_EXTENSIBLE."""
    with Path(path).open('rb') as source:
        head = source.read(12)
        if len(head) != 12 or head[:4] != b'RIFF' or head[8:12] != b'WAVE':
            raise ValueError('not a RIFF/WAVE file')
        fmt = None
        for _ in range(64):
            chunk = source.read(8)
            if len(chunk) < 8:
                break
            name, size = chunk[:4], struct.unpack('<I', chunk[4:])[0]
            if name == b'fmt ':
                body = source.read(size)
                if len(body) < 16:
                    raise ValueError('short fmt chunk')
                tag, channels, rate, _, align, bits = struct.unpack('<HHIIHH', body[:16])
                if tag == 0xFFFE and len(body) >= 26:
                    tag = struct.unpack('<H', body[24:26])[0]
                fmt = (tag, channels, rate, align, bits)
                if size % 2:
                    source.read(1)
            elif name == b'data':
                if fmt is None:
                    raise ValueError('data chunk before fmt chunk')
                tag, channels, rate, align, bits = fmt
                kind = {1: 'pcm', 3: 'float'}.get(tag)
                if kind is None or channels < 1 or rate < 1 or (kind == 'pcm' and bits not in (16, 24, 32)) or (kind == 'float' and bits != 32):
                    raise ValueError('unsupported WAV sample format')
                frames = size // align
                return {'format': kind, 'channels': channels, 'rate': rate, 'bits': bits, 'block_align': align,
                        'data_offset': source.tell(), 'data_bytes': size, 'frames': frames,
                        'duration_seconds': frames / rate}
            else:
                source.seek(size + (size % 2), 1)
    raise ValueError('no data chunk')


def read_wav_mono(path: Path, start_seconds: float = 0.0, end_seconds: float | None = None) -> tuple[list[float], int]:
    """Read a mono downmix (channel mean) of a WAV excerpt as floats in [-1, 1]."""
    header = wav_header(path)
    rate, channels, align = header['rate'], header['channels'], header['block_align']
    first = max(0, min(header['frames'], int(round(start_seconds * rate))))
    last = header['frames'] if end_seconds is None else max(first, min(header['frames'], int(round(end_seconds * rate))))
    with Path(path).open('rb') as source:
        source.seek(header['data_offset'] + first * align)
        raw = source.read((last - first) * align)
    width = header['bits'] // 8
    if header['format'] == 'float':
        values = array.array('f')
        values.frombytes(raw)
        scale = 1.0
    elif width == 2:
        values = array.array('h')
        values.frombytes(raw)
        scale = 1 / 32768
    elif width == 4:
        values = array.array('i')
        values.frombytes(raw)
        scale = 1 / 2147483648
    else:
        values = [int.from_bytes(raw[i:i + 3], 'little', signed=True) for i in range(0, len(raw) - 2, 3)]
        scale = 1 / 8388608
    if sys.byteorder != 'little' and isinstance(values, array.array):
        values.byteswap()
    mono = [sum(values[i:i + channels]) * scale / channels for i in range(0, len(values) - channels + 1, channels)]
    return mono, rate


# --------------------------------------------------------------------------- model / input resolution

def resolve_model(root: Path = ROOT) -> dict:
    """Contract 3.1 orders 1-5. Never downloads; never falls back."""
    registry_path = root / 'program' / 'models.json'
    try:
        if registry_path.is_symlink() or not registry_path.is_file():
            raise ValueError('registry missing')
        registry_bytes = read_bounded(registry_path, LIMITS['registry_bytes'])
        registry = json.loads(registry_bytes)
    except (OSError, ValueError) as exc:
        raise Refused('model_not_registered', f'program/models.json unreadable or missing ({exc}); no download is attempted')
    models = registry.get('models') if isinstance(registry, dict) else None
    if not isinstance(registry, dict) or registry.get('schema_version') != 1 or not isinstance(models, dict):
        raise Refused('model_not_registered', 'Model registry requires schema_version 1 with a models object')
    entry = models.get(MODEL_ID)
    if not isinstance(entry, dict):
        raise Refused('model_not_registered', f'{MODEL_ID} is not registered; root adds the entry after its explicit hash-bound fetch')
    digest = entry.get('sha256')
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise Refused('model_hash_not_registered', f'{MODEL_ID} has no registered lowercase sha256 (placeholder or invalid)')
    url, license_text, limit = entry.get('url'), entry.get('license'), entry.get('max_bytes')
    parsed = urllib.parse.urlparse(url) if isinstance(url, str) else None
    if (not isinstance(license_text, str) or not license_text.strip() or not isinstance(limit, int) or isinstance(limit, bool)
            or not 0 < limit <= LIMITS['max_model_bytes'] or parsed is None or parsed.scheme != 'https'
            or not parsed.hostname or parsed.username or parsed.password):
        raise Refused('model_registry_entry_invalid', f'{MODEL_ID} registry entry needs license, max_bytes and an HTTPS url')
    models_dir = root / 'models'
    model_path = models_dir / f'{MODEL_ID}.bin'
    if models_dir.is_symlink() or model_path.is_symlink() or not model_path.is_file() or model_path.stat().st_size > limit:
        raise Refused('model_file_missing', f'models/{MODEL_ID}.bin missing, symlinked or oversized; run explicit just model-prefetch {MODEL_ID} (root)')
    if sha256_file(model_path) != digest:
        raise Refused('model_hash_mismatch', f'models/{MODEL_ID}.bin sha256 differs from the registry')
    return {'model_id': MODEL_ID, 'sha256': digest, 'checkpoint': CHECKPOINT, 'source_url': url, 'license': license_text,
            'registry_sha256': sha256_bytes(registry_bytes), 'source_commit': entry.get('source_commit'),
            'path': str(model_path), 'bytes': model_path.stat().st_size}


def default_runtime_checker(root: Path = ROOT) -> dict:
    sys.path.insert(0, str(SCRIPTS))
    try:
        import beat_this_runtime_setup as setup
        report = setup.check(root)
    except Exception as exc:  # any failure of the identity check is order 6
        raise Refused('runtime_not_qualified', f'Isolated Beat This runtime missing or failed its identity check: {exc}')
    return report


def require_linux(system: str | None = None) -> None:
    system = sys.platform if system is None else system
    if not system.startswith('linux'):
        raise Refused('platform_unsupported', 'Beat This inference is qualified only on Linux CPU (honey via the flake ml shell)')


def no_symlink_components(path: Path, root: Path) -> None:
    for item in (path, *path.parents):
        if item.is_symlink():
            raise Refused('input_rejected', f'Symlinked path component: {item}')
        if item == root:
            return


def contained(raw: Path, root: Path, allowed: tuple[Path, ...]) -> Path:
    if '..' in Path(raw).parts:
        raise Refused('input_rejected', 'Traversal components are rejected')
    path = Path(raw) if Path(raw).is_absolute() else root / raw
    path = Path(os.path.abspath(path))
    if not any(path.is_relative_to(root / base) and path != root / base for base in allowed):
        raise Refused('input_rejected', 'Input must be beneath ' + ' or '.join(str(b) for b in allowed))
    no_symlink_components(path, root)
    return path


def load_manifest(path: Path) -> tuple[dict, str]:
    if path.is_symlink() or not path.is_file():
        raise Refused('input_rejected', f'Regular manifest required: {path.name}')
    try:
        data = read_bounded(path, LIMITS['manifest_bytes'])
        manifest = json.loads(data)
    except (OSError, ValueError) as exc:
        raise Refused('input_rejected', f'Manifest unreadable or over 1 MiB: {exc}')
    if not isinstance(manifest, dict):
        raise Refused('input_rejected', 'Manifest must be a JSON object')
    return manifest, sha256_bytes(data)


def is_generated_fixture(manifest: dict) -> bool:
    source = manifest.get('source')
    return (isinstance(source, dict) and source.get('kind') == 'generated_fixture'
            and isinstance(source.get('generator'), str) and bool(source.get('generator'))
            and isinstance(source.get('seed'), int) and not isinstance(source.get('seed'), bool))


def checked_duration(path: Path) -> float:
    try:
        header = wav_header(path)
    except (OSError, ValueError) as exc:
        raise Refused('input_rejected', f'Unreadable WAV: {exc}')
    if not 0 < header['duration_seconds'] <= LIMITS['input_seconds']:
        raise Refused('input_rejected', f'Input duration must be in (0, {LIMITS["input_seconds"]}] seconds')
    return header['duration_seconds']


def resolve_input(root: Path = ROOT, run_dir: Path | None = None, fixture_wav: Path | None = None) -> dict:
    """Contract 3.1 order 8: verified run denoised.wav or suite-manifest-bound fixture WAV."""
    if (run_dir is None) == (fixture_wav is None):
        raise Refused('input_rejected', 'Exactly one of run_dir or fixture_wav is required')
    if run_dir is not None:
        directory = contained(Path(run_dir), root, (RUNS_REL, FIXTURES_REL))
        if not directory.is_dir():
            raise Refused('input_rejected', 'run_dir must be an existing directory')
        manifest, manifest_sha = load_manifest(directory / 'manifest.json')
        audio = directory / 'denoised.wav'
        if audio.is_symlink() or not audio.is_file():
            raise Refused('input_rejected', 'Regular denoised.wav required')
        identity = sha256_file(audio)
        recorded = manifest.get('output_sha256', {}).get('denoised.wav') if isinstance(manifest.get('output_sha256'), dict) else None
        if recorded != identity:
            raise Refused('input_rejected', 'denoised.wav sha256 differs from manifest output_sha256')
        timeline = manifest.get('timeline')
        origin = timeline.get('audio_start_seconds') if isinstance(timeline, dict) else None
        if not finite_number(origin):
            raise Refused('input_rejected', 'Manifest timeline.audio_start_seconds must be explicit; unknown origin never defaults to zero')
        duration = checked_duration(audio)
        synthetic = is_generated_fixture(manifest)
        return {'path_role': 'run_denoised_wav', 'path': str(audio), 'sha256': identity, 'run_manifest_sha256': manifest_sha,
                'signal_version': f'sha256:{identity}', 'source_timeline_origin_seconds': float(origin),
                'duration_seconds': duration, 'real_take': not synthetic, 'fixture': None}
    wav_path = contained(Path(fixture_wav), root, (FIXTURES_REL,))
    if wav_path.suffix != '.wav' or wav_path.parent.name != 'cases' or wav_path.is_symlink() or not wav_path.is_file():
        raise Refused('input_rejected', 'Fixture input must be <suite>/cases/<case>.wav')
    suite_dir = wav_path.parent.parent
    manifest, manifest_sha = load_manifest(suite_dir / 'manifest.json')
    case_id = wav_path.stem
    case = manifest.get('cases', {}).get(case_id) if isinstance(manifest.get('cases'), dict) else None
    identity = sha256_file(wav_path)
    if not isinstance(case, dict) or case.get('wav_sha256') != identity or manifest.get('generator', {}).get('id') != 'beat_this_compare.generate_fixture':
        raise Refused('input_rejected', 'Fixture WAV is not bound by its suite manifest')
    duration = checked_duration(wav_path)
    return {'path_role': 'generated_fixture_wav', 'path': str(wav_path), 'sha256': identity, 'run_manifest_sha256': None,
            'suite_manifest_sha256': manifest_sha, 'signal_version': f'sha256:{identity}', 'source_timeline_origin_seconds': 0.0,
            'duration_seconds': duration, 'real_take': False,
            'fixture': {'suite_dir': str(suite_dir), 'suite': manifest.get('suite'), 'role': manifest.get('role'),
                        'case': case_id, 'cohort': case.get('cohort'), 'seed': case.get('seed'),
                        'construction_click_period_seconds': case.get('construction_click_period_seconds')}}


# --------------------------------------------------------------------------- measurements

def half_double(click_period: float | None, beats: list[float], source: str = 'rhythm.analyze.click_grid') -> dict:
    """ratio = click_grid_period / median IBI (Beat This tempo over click-grid tempo)."""
    result = {'click_grid_source': source, 'click_grid_period_seconds': click_period, 'ratio': None,
              'nearest_relation': None, 'relative_error': None, 'status': None,
              'relation_tolerance': RELATION_TOLERANCE, 'interpretation': 'arithmetic on outputs; not an intended-tempo identification'}
    if click_period is None or not finite_number(click_period) or click_period <= 0:
        result['click_grid_period_seconds'] = None
        result['status'] = 'no_click_grid'
        return result
    if len(beats) < MIN_BEATS_FOR_RATIO:
        result['status'] = 'insufficient_beats'
        return result
    ibi = statistics.median(b - a for a, b in zip(beats, beats[1:]))
    if ibi <= 0:
        result['status'] = 'insufficient_beats'
        return result
    return {**result, **classify_ratio(click_period / ibi), 'status': 'measured'}


def classify_ratio(ratio: float) -> dict:
    name, value = min(RELATIONS, key=lambda item: abs(ratio - item[1]) / item[1])
    error = abs(ratio - value) / value
    return {'ratio': ratio, 'nearest_relation': name if error <= RELATION_TOLERANCE + 1e-12 else 'unrelated',
            'relative_error': error}


def f70(truth: list[float], predicted: list[float]) -> dict:
    """One case: ordered one-to-one maximum-cardinality matching within 70 ms."""
    sys.path.insert(0, str(SCRIPTS))
    import benchmark
    metrics = benchmark.event_metrics_v2(list(truth), list(predicted), tolerance=F_TOLERANCE)
    return pooled([{'tp': metrics['matched_count'], 'truth_count': len(truth), 'pred_count': len(predicted)}])


def pooled(rows: list[dict]) -> dict:
    """Pooled sums over cases; rates are never averaged."""
    tp = sum(r['tp'] for r in rows)
    n_truth = sum(r['truth_count'] for r in rows)
    n_pred = sum(r['pred_count'] for r in rows)
    precision = tp / n_pred if n_pred else None
    recall = tp / n_truth if n_truth else None
    if precision is None or recall is None:
        f = None
    else:
        f = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return {'tp': tp, 'truth_count': n_truth, 'pred_count': n_pred, 'cases': len(rows),
            'precision': precision, 'recall': recall, 'f_measure': f, 'tolerance_seconds': F_TOLERANCE,
            'precision_null_reason': None if n_pred else 'no_predictions',
            'recall_null_reason': None if n_truth else 'empty_truth',
            'f_null_reason': None if f is not None else ('no_predictions' if not n_pred else 'empty_truth'),
            'aggregation': 'pooled_sums_not_averaged_rates', 'matcher': 'benchmark.event_metrics_v2'}


def clean_events(values, name: str) -> list[float]:
    if not isinstance(values, list) or len(values) > LIMITS['events']:
        raise ValueError(f'{name} must be a bounded list')
    if any(not finite_number(v) or v < 0 for v in values):
        raise ValueError(f'{name} must be finite non-negative seconds')
    return sorted(float(v) for v in values)


def assemble(model: dict, runtime: dict, inp: dict, beats: list[float], downbeats: list[float],
             click_grid_period: float | None, truth: dict | None = None) -> dict:
    beats, downbeats = clean_events(beats, 'beats'), clean_events(downbeats, 'downbeats')
    origin = inp['source_timeline_origin_seconds']
    ibis = [b - a for a, b in zip(beats, beats[1:])]
    median_ibi = statistics.median(ibis) if ibis else None
    doc = {
        'schema_version': 1, 'status': 'completed', 'tool': 'beat_this_compare', 'experimental': True,
        'recorded_utc': datetime.now(timezone.utc).isoformat(),
        'model_identity': {k: model[k] for k in ('model_id', 'sha256', 'checkpoint', 'source_url', 'license', 'registry_sha256')},
        'runtime_identity': {k: runtime.get(k) for k in ('lock_sha256', 'python', 'torch', 'beat_this_version', 'platform', 'host_label')},
        'input_identity': {'path_role': inp['path_role'], 'sha256': inp['sha256'], 'run_manifest_sha256': inp['run_manifest_sha256'],
                           'signal_version': inp['signal_version'], 'analysis_rate': ANALYSIS_RATE,
                           'resampling': 'soxr_in_upstream_preprocess', 'downmix': 'channel_mean_in_worker',
                           'source_timeline_origin_seconds': origin, 'duration_seconds': inp['duration_seconds']},
        'settings': {'device': 'cpu', 'float16': False, 'dbn': False, 'postprocessing': 'upstream_minimal',
                     'model_fps': MODEL_FPS, 'tunable_knobs': []},
        'beats': [{'model_seconds': b, 'source_timeline_seconds': origin + b} for b in beats],
        'downbeats': [{'model_seconds': d, 'source_timeline_seconds': origin + d} for d in downbeats],
        'beat_count': len(beats), 'downbeat_count': len(downbeats),
        'median_ibi_seconds': median_ibi, 'ibi_tempo_bpm': 60 / median_ibi if median_ibi else None,
        'ibi_tempo_claim_class': 'measurement_on_model_output',
        'half_double_ratio_vs_click_grid': half_double(click_grid_period, beats),
        'real_take': inp['real_take'],
    }
    if inp['real_take']:
        doc['privacy'] = 'V6_private_real_take_derived'
    if inp.get('fixture'):
        doc['fixture'] = {k: v for k, v in inp['fixture'].items() if k != 'suite_dir'}
        doc['half_double_ratio_vs_construction_click'] = half_double(
            inp['fixture'].get('construction_click_period_seconds'), beats, 'fixture_construction_click_period')
    if truth is not None and inp.get('fixture'):
        doc['generated_truth_scores'] = {'beat': f70(truth['beats'], beats), 'downbeat': f70(truth['downbeats'], downbeats),
                                         'truth_sha256': truth['_sha256'], 'claim_class': 'measurement_on_generated_fixture'}
        doc['generated_truth_scores_reason'] = None
    else:
        doc['generated_truth_scores'] = None
        doc['generated_truth_scores_reason'] = 'no_generated_truth'
    doc.update(UNKNOWN_FIELDS)
    doc['limitations'] = list(LIMITATIONS)
    return doc


# --------------------------------------------------------------------------- click grid (A0 / ratio reference)

def rhythm_reference(path: Path, duration: float) -> dict:
    """rhythm.analyze() with default settings on an FFmpeg 16 kHz mono analysis copy."""
    sys.path.insert(0, str(SCRIPTS))
    import rhythm
    samples = rhythm.decode(Path(path))
    analysis = rhythm.analyze(samples)
    grid = analysis.get('click_grid')
    selected = analysis.get('selected_periodicity')
    beats, basis = [], 'none'
    if grid:
        period, phase = grid['period_seconds'], grid['phase_seconds_audio_relative']
        basis = 'click_grid'
    elif selected:
        period = selected['period_seconds']
        _, high = rhythm.envelopes(samples)
        peaks = rhythm.high_frequency_peak_indices(rhythm.novelty(high))
        phase = (peaks[0] + .5) * rhythm.HOP / rhythm.RATE if peaks else None
        basis = 'selected_periodicity_anchored_first_high_frequency_peak' if phase is not None else 'none'
    if basis != 'none':
        first, last = math.ceil(-phase / period), math.floor((duration - phase) / period)
        beats = [phase + k * period for k in range(first, last + 1) if 0 <= phase + k * period <= duration]
    return {'click_grid_period_seconds': grid['period_seconds'] if grid else None, 'beats': beats, 'basis': basis,
            'selected_periodicity_period_seconds': selected['period_seconds'] if selected else None,
            'rhythm_settings': 'analyze() defaults: stdlib backend, no bpm seed'}


# --------------------------------------------------------------------------- isolated runner

def bounded_child(command: list[str], workdir: Path, env: dict, deadline: float) -> dict:
    peak, stopped, error = 0, None, None
    with (workdir / 'worker.stdout.log').open('xb') as stdout, (workdir / 'worker.stderr.log').open('xb') as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=env, cwd=workdir)
        try:
            while process.poll() is None:
                snapshot = subprocess.run(['ps', '-p', str(process.pid), '-o', 'ppid=,rss='], capture_output=True, text=True, timeout=5).stdout.split()
                if len(snapshot) == 2:
                    if int(snapshot[0]) != os.getpid():
                        raise ValueError('Inference worker ownership mismatch')
                    peak = max(peak, int(snapshot[1]) * 1024)
                if peak > LIMITS['rss_bytes'] or time.monotonic() >= deadline:
                    stopped = 'rss_bound' if peak > LIMITS['rss_bytes'] else 'deadline'
                    break
                if stdout.tell() + stderr.tell() > LIMITS['log_bytes']:
                    stopped = 'log_byte_bound'
                    break
                time.sleep(.1)
        except Exception as exc:
            stopped, error = 'monitor_error', exc
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            else:
                process.wait(timeout=3)
    receipt = {'pid': process.pid, 'owner_pid': os.getpid(), 'ownership': 'Popen direct child checked by PPID',
               'ruling': 'R-N11', 'termination_reason': stopped, 'returncode': process.returncode,
               'observed_peak_rss_bytes': peak, 'rss_bound_bytes': LIMITS['rss_bytes'], 'deadline_seconds': LIMITS['deadline_seconds']}
    (workdir / 'worker-resource.json').write_text(json.dumps(receipt, indent=2) + '\n')
    if stopped or process.returncode:
        tail = (workdir / 'worker.stderr.log').read_text(errors='replace')[-1000:]
        raise RuntimeError('Bounded Beat This inference failed: ' + str(error or stopped or tail))
    return receipt


class IsolatedRunner:
    """Runs this file's --infer-task inside the qualified runtime; no network, no hub cache."""

    def __init__(self, root: Path = ROOT):
        self.root = root

    def __call__(self, wav_path: str, model: dict, workdir: Path, runtime: dict) -> dict:
        interpreter = Path(runtime['runtime_dir']) / 'python' / 'bin' / 'python'
        empty = workdir / 'empty-cache'
        empty.mkdir(mode=0o700)
        task = {'model_path': model['path'], 'model_sha256': model['sha256'], 'input_path': wav_path,
                'input_sha256': sha256_file(Path(wav_path)), 'output': str(workdir / 'inference.json')}
        task_path = workdir / 'task.json'
        task_path.write_text(json.dumps(task, indent=2) + '\n')
        threads = str(LIMITS['threads'])
        env = {'PATH': '/usr/bin:/bin', 'HOME': str(empty), 'TORCH_HOME': str(empty), 'HF_HOME': str(empty),
               'XDG_CACHE_HOME': str(empty), 'HTTP_PROXY': UNREACHABLE_PROXY, 'HTTPS_PROXY': UNREACHABLE_PROXY,
               'http_proxy': UNREACHABLE_PROXY, 'https_proxy': UNREACHABLE_PROXY, 'NO_PROXY': '', 'no_proxy': '',
               'OMP_NUM_THREADS': threads, 'OPENBLAS_NUM_THREADS': threads, 'MKL_NUM_THREADS': threads,
               'PYTHONDONTWRITEBYTECODE': '1', 'CUDA_VISIBLE_DEVICES': ''}
        receipt = bounded_child([str(interpreter), '-B', str(Path(__file__).resolve()), '--infer-task', str(task_path)],
                                workdir, env, time.monotonic() + LIMITS['deadline_seconds'])
        result = json.loads(read_bounded(workdir / 'inference.json', 8 * 1024**2))
        result['resource_receipt'] = receipt
        return result


def infer_task(task_path: Path) -> int:
    """Executed only by the isolated interpreter. Loads weights_only from the local path; hub download is disabled."""
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[key] = str(LIMITS['threads'])
    task = json.loads(Path(task_path).read_text())
    if sha256_file(Path(task['model_path'])) != task['model_sha256'] or sha256_file(Path(task['input_path'])) != task['input_sha256']:
        raise ValueError('Model or input identity changed before inference')
    import importlib.metadata
    import numpy as np
    import torch
    torch.set_num_threads(LIMITS['threads'])
    import beat_this.inference as upstream

    def local_checkpoint(path, device='cpu'):
        local = Path(path)
        if local.is_symlink() or not local.is_file() or str(local) != task['model_path']:
            raise ValueError('Only the verified local checkpoint may be loaded')
        return torch.load(str(local), map_location='cpu', weights_only=True)

    def no_download(*args, **kwargs):
        raise RuntimeError('Network checkpoint acquisition is disabled in the video-utils comparator')

    upstream.load_checkpoint = local_checkpoint
    torch.hub.load_state_dict_from_url = no_download
    header = wav_header(Path(task['input_path']))
    with Path(task['input_path']).open('rb') as source:
        source.seek(header['data_offset'])
        raw = source.read(header['frames'] * header['block_align'])
    if header['format'] == 'float':
        data = np.frombuffer(raw, dtype='<f4').astype(np.float64)
    elif header['bits'] == 16:
        data = np.frombuffer(raw, dtype='<i2').astype(np.float64) / 32768
    elif header['bits'] == 32:
        data = np.frombuffer(raw, dtype='<i4').astype(np.float64) / 2147483648
    else:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        data = ((b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)) ^ 0x800000) - 0x800000
        data = data.astype(np.float64) / 8388608
    signal = data.reshape(-1, header['channels']).mean(axis=1)
    if not np.isfinite(signal).all():
        raise ValueError('Non-finite input samples')
    tracker = upstream.Audio2Beats(checkpoint_path=task['model_path'], device='cpu', float16=False, dbn=False)
    beats, downbeats = tracker(signal, header['rate'])
    import resource
    result = {'beats': [float(x) for x in beats], 'downbeats': [float(x) for x in downbeats],
              'versions': {'torch': torch.__version__, 'beat-this': importlib.metadata.version('beat-this'),
                           'numpy': np.__version__, 'soxr': importlib.metadata.version('soxr')},
              'python': platform.python_version(), 'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              'input_rate': header['rate'], 'input_channels': header['channels']}
    Path(task['output']).write_text(json.dumps(result, allow_nan=False) + '\n')
    return 0


# --------------------------------------------------------------------------- comparator entry

def lane_output_dir(root: Path, out: Path | None, label: str = 'beat_this') -> Path:
    base = root / LANE_REL
    if out is None:
        target = base / label / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(4))
    else:
        if '..' in Path(out).parts:
            raise Refused('input_rejected', 'Output path must not contain traversal')
        target = Path(os.path.abspath(out if Path(out).is_absolute() else root / out))
        if not target.is_relative_to(base):
            raise Refused('input_rejected', f'Output must be beneath {LANE_REL}')
    no_symlink_components(target.parent if target.parent.exists() else base, root)
    target.mkdir(parents=True, exist_ok=False, mode=0o700)
    return target


def load_generated_truth(path: Path, inp: dict) -> dict:
    fixture = inp.get('fixture')
    if not fixture:
        raise Refused('input_rejected', 'Generated truth applies only to generated fixtures; real takes carry no truth')
    if fixture.get('role') != 'dev':
        raise Refused('input_rejected', 'Held-out truth is read only by the sealed score step')
    expected = Path(fixture['suite_dir']) / 'truth' / f"{fixture['case']}.json"
    if Path(os.path.abspath(path)) != expected:
        raise Refused('input_rejected', 'Truth file must be the suite truth for this case')
    data = expected.read_bytes()
    truth = json.loads(data)
    truth['_sha256'] = sha256_bytes(data)
    return truth


def compare(root: Path = ROOT, run_dir: Path | None = None, fixture_wav: Path | None = None, out: Path | None = None,
            generated_truth: Path | None = None, runner=None, runtime_checker=None, system: str | None = None,
            click_grid_provider=None, write: bool = True) -> dict:
    try:
        model = resolve_model(root)                                       # orders 1-5
        runtime = (runtime_checker or default_runtime_checker)(root)      # order 6
        require_linux(system)                                             # order 7
        inp = resolve_input(root, run_dir, fixture_wav)                   # order 8
        truth = load_generated_truth(Path(generated_truth), inp) if generated_truth else None
        workdir = lane_output_dir(root, out) if write else None
    except Refused as exc:
        return refusal(exc.code, str(exc))
    runner = runner or IsolatedRunner(root)
    if workdir is None:
        workdir = root / LANE_REL / 'scratch' / secrets.token_hex(6)
        workdir.mkdir(parents=True, mode=0o700)
    result = runner(inp['path'], model, workdir, runtime)
    if sha256_file(Path(inp['path'])) != inp['sha256'] or sha256_file(Path(model['path'])) != model['sha256']:
        raise RuntimeError('Input or model changed during inference')
    versions = result.get('versions', {})
    runtime_identity = {'lock_sha256': runtime.get('lock_sha256'), 'python': result.get('python', runtime.get('python')),
                        'torch': versions.get('torch', runtime.get('versions', {}).get('torch')),
                        'beat_this_version': versions.get('beat-this', runtime.get('versions', {}).get('beat-this')),
                        'platform': f"{platform.system().lower()}-{runtime.get('machine', platform.machine())}",
                        'host_label': platform.node().split('.')[0] or None}
    provider = click_grid_provider or (lambda item: rhythm_reference(Path(item['path']), item['duration_seconds'])['click_grid_period_seconds'])
    doc = assemble(model, runtime_identity, inp, result['beats'], result['downbeats'], provider(inp), truth)
    doc['worker_resources'] = result.get('resource_receipt')
    doc['output_dir'] = str(workdir.relative_to(root)) if workdir.is_relative_to(root) else str(workdir)
    if write:
        (workdir / 'beat_this_comparison.json').write_text(json.dumps(doc, indent=2, allow_nan=False) + '\n')
    return doc


# --------------------------------------------------------------------------- fixture generator (suite s3-beat-1)

FIXTURE_RATE = 48000
COHORTS = ('c1-chug178', 'c2-halftime89', 'c3-odd7', 'c4-drift', 'c5-rests', 'c6-legato', 'c7-noclick', 'c8-negative')
DEV_SEED = 3001
HELDOUT_SEEDS = (3101, 3203)
EXCLUDED_SEEDS = (211, 307, 617, 719, 1009, 1301, 1423, 1511, 1613)
MIDI = {'C1': 24, 'F1': 29, 'Ab3': 56, 'F4': 65}
TABLE = 2048


def midi_hz(note: int) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)  # theoretical A4=440 equal temperament, not measured


def _cycle(frequency: float, palm: bool) -> list[float]:
    """One normalised cycle of partials 1-12 (amplitude 1/k; palm mute: partials >8 at -12 dB)."""
    cut = 10 ** (-12 / 20)
    partials = [(k, (1 / k) * (cut if palm and k > 8 else 1.0)) for k in range(1, 13) if frequency * k < FIXTURE_RATE * .45]
    cycle = [sum(a * math.sin(2 * math.pi * k * i / TABLE) for k, a in partials) for i in range(TABLE)]
    peak = max(abs(v) for v in cycle) or 1.0
    return [v / peak for v in cycle]


def _render_note(buffer: list[float], start: float, length: float, frequency: float, gain_db: float, palm: bool,
                 attack: float = .002, tau: float | None = None, cache: dict | None = None) -> None:
    rate = FIXTURE_RATE
    key = (round(frequency, 6), palm)
    if cache is None:
        cache = {}
    if key not in cache:
        cache[key] = _cycle(frequency, palm)
    cycle = cache[key]
    tau = (.06 if palm else .4) if tau is None else tau
    begin = int(round(start * rate))
    count = min(int(length * rate), len(buffer) - begin)
    if begin < 0 or count <= 0:
        return
    gain = 10 ** (gain_db / 20)
    step = frequency * TABLE / rate
    attack_n, release_n = max(1, int(attack * rate)), int(.003 * rate)
    decay = math.exp(-1 / (tau * rate))
    drive = 4.0
    norm = 1 / math.tanh(drive)
    env, phase, scale = 1.0, 0.0, gain * norm
    tail = count - release_n
    tanh = math.tanh
    for n in range(count):
        shape = env
        if n < attack_n:
            shape *= n / attack_n
        if n > tail:
            shape *= (count - n) / release_n
        buffer[begin + n] += scale * tanh(drive * shape * cycle[int(phase) % TABLE])
        phase += step
        env *= decay


def _fan(rng: random.Random, count: int) -> list[float]:
    a = math.exp(-2 * math.pi * 400 / FIXTURE_RATE)
    y, out = 0.0, []
    for _ in range(count):
        y = a * y + (1 - a) * (rng.random() - .5)
        out.append(y)
    rms = math.sqrt(sum(v * v for v in out) / count) or 1.0
    target = 10 ** (-42 / 20)
    return [v * target / rms for v in out]


def _click(buffer: list[float], at: float) -> None:
    begin, width = int(round(at * FIXTURE_RATE)), int(.001 * FIXTURE_RATE)
    peak = 10 ** (-18 / 20)
    for n in range(width):
        if 0 <= begin + n < len(buffer):
            window = .5 - .5 * math.cos(2 * math.pi * n / (width - 1))
            buffer[begin + n] += peak * window * math.sin(2 * math.pi * 3000 * n / FIXTURE_RATE)


def _grid(t0: float, period: float, end: float) -> list[float]:
    out, k = [], 0
    while t0 + k * period < end:
        out.append(t0 + k * period)
        k += 1
    return out


def generate_fixture(cohort: str, seed: int, duration: float = 30.0) -> tuple[bytes, dict]:
    """Deterministic stdlib fixture: (pcm16 mono 48 kHz WAV bytes, truth). Same seed -> same bytes on a host."""
    if cohort not in COHORTS:
        raise ValueError(f'unknown cohort {cohort}')
    rng = random.Random(seed)
    count = int(round(duration * FIXTURE_RATE))
    guitar = [0.0] * count
    cache: dict = {}
    end = duration - .25
    t0 = .5 + rng.uniform(0, .2)
    jitter = lambda: max(-.005, min(.005, rng.gauss(0, .002)))
    vel = lambda: rng.uniform(-1, 1)
    beats, downbeats, has_click, period = [], [], cohort not in ('c7-noclick', 'c8-negative'), None
    notes = []  # (start, frequency, gain_db, palm, attack, tau)

    def chugs(beat_times: list[float], per_beat: int, rests: set[int] = frozenset()) -> None:
        for index, beat in enumerate(beat_times):
            if index // 4 in rests:
                continue
            nxt = beat_times[index + 1] if index + 1 < len(beat_times) else beat + (beat - beat_times[index - 1])
            pitch = midi_hz(rng.choice((MIDI['C1'], MIDI['F1'])))
            for j in range(per_beat):
                notes.append((beat + j * (nxt - beat) / per_beat + jitter(), pitch, (4.0 if j == 0 else 0.0) + vel(), True, .002, None))

    if cohort in ('c1-chug178', 'c5-rests', 'c7-noclick'):
        period = 60 / 178
        beats = _grid(t0, period, end)
        chugs(beats, 4, {5, 6, 13, 14} if cohort == 'c5-rests' else set())
        downbeats = beats[::4]
    elif cohort == 'c2-halftime89':
        period = 60 / 89
        beats = _grid(t0, period, end)
        sixteenth = (60 / 178) / 4
        for k, t in enumerate(_grid(t0, sixteenth, end)):
            accent = k % 8 == 0
            notes.append((t + jitter(), midi_hz(MIDI['C1']) if accent else midi_hz(rng.choice((MIDI['C1'], MIDI['F1']))),
                          (6.0 if accent else -2.0) + vel(), not accent, .002, None))
        downbeats = beats[::4]
    elif cohort == 'c3-odd7':
        eighth = .2
        bars = _grid(t0, 7 * eighth, end)
        for bar in bars:
            for offset in (0, 2, 4):
                if bar + offset * eighth < end:
                    beats.append(bar + offset * eighth)
            for j in range(7):
                if bar + j * eighth < end:
                    notes.append((bar + j * eighth + jitter(), midi_hz(rng.choice((MIDI['C1'], MIDI['F1']))),
                                  (4.0 if j in (0, 2, 4) else 0.0) + vel(), True, .002, None))
        downbeats = list(bars)
        period = statistics.median(b - a for a, b in zip(beats, beats[1:]))
    elif cohort == 'c4-drift':
        t = t0
        while t < end:
            beats.append(t)
            bpm = 178 + (172 - 178) * (t - t0) / (end - t0)
            t += 60 / bpm
        chugs(beats, 2)
        downbeats = beats[::4]
        period = statistics.median(b - a for a, b in zip(beats, beats[1:]))
    elif cohort == 'c6-legato':
        period = 60 / 160
        beats = _grid(t0, period, end)
        midi = 60
        for t in _grid(t0, period / 4, end):
            midi = max(MIDI['Ab3'], min(MIDI['F4'], midi + rng.choice((-2, -1, 1, 2))))
            notes.append((t + jitter(), midi_hz(midi), -8.0 + vel(), False, .03, .3))
        downbeats = beats[::4]
    elif cohort == 'c8-negative':
        frequency, swell = midi_hz(MIDI['C1']), rng.uniform(0, 2 * math.pi)
        cycle = _cycle(frequency, False)
        step, phase = frequency * TABLE / FIXTURE_RATE, 0.0
        norm = 1 / math.tanh(4.0)
        for n in range(count):
            shape = .55 + .45 * math.sin(2 * math.pi * .11 * n / FIXTURE_RATE + swell)
            guitar[n] = norm * math.tanh(4.0 * shape * cycle[int(phase) % TABLE])
            phase += step
    notes.sort()
    for i, (start, frequency, gain_db, palm, attack, tau) in enumerate(notes):
        nxt = notes[i + 1][0] if i + 1 < len(notes) else duration
        _render_note(guitar, max(0.0, start), max(.005, nxt - start), frequency, gain_db, palm, attack, tau, cache)
    peak = max((abs(v) for v in guitar), default=0.0) or 1.0
    scale = 10 ** (-6 / 20) / peak
    fan = _fan(rng, count)
    mix = [g * scale + f for g, f in zip(guitar, fan)]
    clicks = list(beats) if has_click else []
    for at in clicks:
        _click(mix, at)
    pcm = array.array('h', (max(-32768, min(32767, int(round(v * 32767)))) for v in mix))
    if sys.byteorder != 'little':
        pcm.byteswap()
    import io
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(FIXTURE_RATE)
        writer.writeframes(pcm.tobytes())
    truth = {'schema_version': 1, 'cohort': cohort, 'seed': seed, 'duration_seconds': duration,
             'beats': beats, 'downbeats': downbeats if cohort != 'c8-negative' else [], 'click_times': clicks,
             'construction_click_period_seconds': period, 'truth_kind': 'constructed_generator_truth',
             'tuning': 'program/instrument.json theoretical A4=440 (C1 32.70 Hz .. F4)'}
    return buffer.getvalue(), truth


def generate_suite(root: Path, name: str, role: str, seeds: list[int], duration: float = 30.0,
                   cohorts: tuple[str, ...] = COHORTS) -> Path:
    if role not in ('dev', 'heldout'):
        raise ValueError('role must be dev or heldout')
    if any(s in EXCLUDED_SEEDS for s in seeds):
        raise ValueError('seed already consumed elsewhere')
    if role == 'heldout' and sorted(seeds) != sorted(HELDOUT_SEEDS):
        raise ValueError('held-out seeds are sealed as 3101 and 3203')
    if role == 'dev' and seeds != [DEV_SEED]:
        raise ValueError('dev seed is sealed as 3001')
    suite = lane_output_dir(root, root / FIXTURES_REL / name)
    (suite / 'cases').mkdir()
    (suite / 'truth').mkdir()
    cases = {}
    if not set(cohorts) <= set(COHORTS):
        raise ValueError('unknown cohort')
    for seed in seeds:
        for cohort in cohorts:
            case = f'{cohort}-s{seed}'
            audio, truth = generate_fixture(cohort, seed, duration)
            wav_path, truth_path = suite / 'cases' / f'{case}.wav', suite / 'truth' / f'{case}.json'
            wav_path.write_bytes(audio)
            truth_bytes = (json.dumps(truth, indent=2) + '\n').encode()
            truth_path.write_bytes(truth_bytes)
            truth_path.chmod(0o400)
            cases[case] = {'cohort': cohort, 'seed': seed, 'wav': f'cases/{case}.wav', 'wav_sha256': sha256_bytes(audio),
                           'truth': f'truth/{case}.json', 'truth_sha256': sha256_bytes(truth_bytes), 'duration_seconds': duration,
                           'has_click': bool(truth['click_times']),
                           'construction_click_period_seconds': truth['construction_click_period_seconds']}
    manifest = {'schema_version': 1, 'suite': 's3-beat-1', 'role': role, 'seeds': seeds, 'sample_rate': FIXTURE_RATE,
                'format': 'pcm16 mono', 'generator': {'id': 'beat_this_compare.generate_fixture', 'script_sha256': sha256_file(Path(__file__))},
                'source': {'kind': 'generated_fixture', 'generator': 'beat_this_compare.generate_fixture', 'seed': seeds[0]},
                'preregistration': 'docs/spec/sprints/MODEL_LANES_S3.md section 7 (commit faf91d6)',
                'cohorts': list(cohorts), 'complete_preregistered_suite': tuple(cohorts) == COHORTS and duration == 30.0,
                'recorded_utc': datetime.now(timezone.utc).isoformat(), 'cases': cases}
    (suite / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return suite


# --------------------------------------------------------------------------- experiment harness (seal before truth)

def _suite(root: Path, suite_dir: Path) -> tuple[Path, dict]:
    suite = contained(Path(suite_dir), root, (FIXTURES_REL,))
    manifest, _ = load_manifest(suite / 'manifest.json')
    return suite, manifest


def predict(root: Path, suite_dir: Path, arm: str, a1=None, a0=None) -> list[Path]:
    """Writes predictions/<arm>/<case>.json. Never opens truth/."""
    suite, manifest = _suite(root, suite_dir)
    if arm not in ('A0', 'A1'):
        raise ValueError('arm must be A0 or A1')
    if (suite / 'seal.json').exists():
        raise ValueError('Suite already sealed; predictions are immutable')
    out = suite / 'predictions' / arm
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for case, info in sorted(manifest['cases'].items()):
        wav = suite / info['wav']
        if sha256_file(wav) != info['wav_sha256']:
            raise ValueError('Case audio changed: ' + case)
        if arm == 'A0':
            reference = (a0 or rhythm_reference)(wav, info['duration_seconds'])
            record = {'beats': reference['beats'], 'downbeats': None, 'downbeat_null_reason': 'arm_has_no_downbeats',
                      'a0_basis': reference['basis'], 'click_grid_period_seconds': reference['click_grid_period_seconds']}
        else:
            doc = (a1 or (lambda path: compare(root, fixture_wav=path, write=False)))(wav)
            if doc.get('status') != 'completed':
                record = {'beats': None, 'downbeats': None, 'refusal': doc}
            else:
                record = {'beats': [b['model_seconds'] for b in doc['beats']], 'downbeats': [d['model_seconds'] for d in doc['downbeats']],
                          'model_identity': doc['model_identity'], 'runtime_identity': doc['runtime_identity']}
        record.update(schema_version=1, arm=arm, case=case, input_sha256=info['wav_sha256'], recorded_utc=datetime.now(timezone.utc).isoformat())
        path = out / f'{case}.json'
        path.write_text(json.dumps(record, indent=2, allow_nan=False) + '\n')
        written.append(path)
    return written


def seal(root: Path, suite_dir: Path, arms: tuple[str, ...] = ('A0', 'A1')) -> Path:
    suite, manifest = _suite(root, suite_dir)
    files = {}
    for arm in arms:
        for case in sorted(manifest['cases']):
            path = suite / 'predictions' / arm / f'{case}.json'
            if not path.is_file():
                raise ValueError(f'Missing prediction {arm}/{case}; seal covers every case of every arm')
            files[str(path.relative_to(suite))] = sha256_file(path)
    target = suite / 'seal.json'
    if target.exists():
        raise ValueError('Seal already exists')
    target.write_text(json.dumps({'schema_version': 1, 'sealed_utc': datetime.now(timezone.utc).isoformat(),
                                  'sealed_epoch': time.time(), 'arms': list(arms), 'files': files}, indent=2) + '\n')
    target.chmod(0o400)
    return target


def score(root: Path, suite_dir: Path) -> dict:
    """Section 7.4. Refuses unless a matching seal predates scorer start."""
    started = time.time()
    suite, manifest = _suite(root, suite_dir)
    if manifest.get('role') != 'heldout':
        raise ValueError('Dev suites are never scored')
    seal_path = suite / 'seal.json'
    if not seal_path.is_file():
        raise ValueError('Scorer refuses: seal.json missing')
    sealed = json.loads(seal_path.read_text())
    if sealed['sealed_epoch'] >= started:
        raise ValueError('Scorer refuses: seal does not precede scorer start')
    for relative, digest in sealed['files'].items():
        if sha256_file(suite / relative) != digest:
            raise ValueError('Scorer refuses: sealed prediction changed: ' + relative)
    cases = manifest['cases']
    pred = {arm: {case: json.loads((suite / 'predictions' / arm / f'{case}.json').read_text()) for case in cases} for arm in sealed['arms']}
    truth = {}
    for case, info in cases.items():
        data = (suite / info['truth']).read_bytes()
        if sha256_bytes(data) != info['truth_sha256']:
            raise ValueError('Truth file changed: ' + case)
        truth[case] = json.loads(data)
    sys.path.insert(0, str(SCRIPTS))
    import benchmark

    def row(t, p):
        m = benchmark.event_metrics_v2(list(t), list(p or []), tolerance=F_TOLERANCE)
        return {'tp': m['matched_count'], 'truth_count': len(t), 'pred_count': len(p or [])}

    positive = [c for c in cases if cases[c]['cohort'] != 'c8-negative']
    negative = [c for c in cases if cases[c]['cohort'] == 'c8-negative']
    result = {'schema_version': 1, 'suite': manifest['suite'], 'scored_utc': datetime.now(timezone.utc).isoformat(),
              'seal_sha256': sha256_file(seal_path), 'arms': {}, 'claim_class': 'measurement_on_generated_fixtures',
              'real_take_accuracy': 'unknown', 'default_adoption': False}
    for arm in sealed['arms']:
        beat_rows = {c: row(truth[c]['beats'], pred[arm][c]['beats']) for c in positive}
        per_cohort = {}
        for c in positive:
            per_cohort.setdefault(cases[c]['cohort'], []).append(beat_rows[c])
        entry = {'beat_f70_overall': pooled(list(beat_rows.values())),
                 'beat_f70_per_cohort': {k: pooled(v) for k, v in sorted(per_cohort.items())}}
        if arm == 'A1':
            entry['downbeat_f70_overall'] = pooled([row(truth[c]['downbeats'], pred[arm][c]['downbeats']) for c in positive])
        else:
            entry['downbeat_f70_overall'] = None
            entry['downbeat_null_reason'] = 'arm_has_no_downbeats'
        minutes = sum(cases[c]['duration_seconds'] for c in negative) / 60
        false_beats = sum(len(pred[arm][c]['beats'] or []) for c in negative)
        entry['c8_false_beats_per_minute'] = {'value': false_beats / minutes if minutes else None, 'predicted': false_beats, 'minutes': minutes}
        relations = {'vs_construction_click': {}, 'vs_a0_click_grid': {}}
        for c in positive:
            beats = pred[arm][c]['beats'] or []
            a = half_double(cases[c]['construction_click_period_seconds'], beats, 'construction')
            b = half_double(pred['A0'][c].get('click_grid_period_seconds') if 'A0' in pred else None, beats, 'a0_click_grid')
            for key, item in (('vs_construction_click', a), ('vs_a0_click_grid', b)):
                label = item['nearest_relation'] or item['status']
                relations[key][label] = relations[key].get(label, 0) + 1
        entry['half_double_relation_counts'] = {**relations, 'denominator_cases': len(positive)}
        result['arms'][arm] = entry
    if {'A0', 'A1'} <= set(result['arms']):
        f0 = result['arms']['A0']['beat_f70_overall']['f_measure']
        f1 = result['arms']['A1']['beat_f70_overall']['f_measure']
        n0 = result['arms']['A0']['c8_false_beats_per_minute']['value']
        n1 = result['arms']['A1']['c8_false_beats_per_minute']['value']
        better = None not in (f0, f1, n0, n1) and f1 >= f0 + .05 and n1 <= n0 + 5
        result['decision'] = {'rule': 'F70(A1) >= F70(A0)+0.05 on c1-c7 AND c8 false beats/min(A1) <= A0+5',
                              'outcome': 'A1 better on generated fixtures' if better else 'no improvement shown',
                              'descriptive_only': True, 'default_adoption': False}
    (suite / 'scores.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return result


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--infer-task', type=Path, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest='command')
    c = sub.add_parser('compare', help='run the comparator on one verified input')
    group = c.add_mutually_exclusive_group(required=True)
    group.add_argument('--run-dir', type=Path)
    group.add_argument('--fixture-wav', type=Path)
    c.add_argument('--generated-truth', type=Path, help='dev-suite fixture truth only')
    c.add_argument('--out', type=Path, help=f'directory beneath {LANE_REL}')
    g = sub.add_parser('generate-suite')
    g.add_argument('--name', required=True)
    g.add_argument('--role', choices=('dev', 'heldout'), required=True)
    g.add_argument('--seeds', type=int, nargs='+', required=True)
    g.add_argument('--duration', type=float, default=30.0)
    p = sub.add_parser('predict')
    p.add_argument('--suite-dir', type=Path, required=True)
    p.add_argument('--arm', choices=('A0', 'A1'), required=True)
    s = sub.add_parser('seal')
    s.add_argument('--suite-dir', type=Path, required=True)
    s.add_argument('--arms', nargs='+', default=['A0', 'A1'])
    r = sub.add_parser('score')
    r.add_argument('--suite-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.infer_task:
        return infer_task(args.infer_task)
    try:
        if args.command == 'compare':
            doc = compare(ROOT, args.run_dir, args.fixture_wav, args.out, args.generated_truth)
            summary = doc if doc['status'] == 'refused' else {
                'status': doc['status'], 'output_dir': doc['output_dir'], 'beat_count': doc['beat_count'],
                'downbeat_count': doc['downbeat_count'], 'half_double': doc['half_double_ratio_vs_click_grid'],
                'meter_claim': doc['meter_claim'], 'default_adoption': False}
            print(json.dumps(summary))
            return 0 if doc['status'] == 'completed' else 2
        if args.command == 'generate-suite':
            print(json.dumps({'suite_dir': str(generate_suite(ROOT, args.name, args.role, args.seeds, args.duration))}))
        elif args.command == 'predict':
            print(json.dumps({'written': [str(p) for p in predict(ROOT, args.suite_dir, args.arm)]}))
        elif args.command == 'seal':
            print(json.dumps({'seal': str(seal(ROOT, args.suite_dir, tuple(args.arms)))}))
        elif args.command == 'score':
            print(json.dumps(score(ROOT, args.suite_dir).get('decision')))
        else:
            parser.print_help()
            return 1
        return 0
    except Refused as exc:
        print(json.dumps(refusal(exc.code, str(exc))))
        return 2
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
