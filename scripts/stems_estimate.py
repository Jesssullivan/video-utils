#!/usr/bin/env python3
"""Experimental htdemucs_6s stem *estimates* from a mono mixture; never a recovered stem, never a default.

Closed-schema request and result (contract docs/spec/sprints/STEMS_S3.md, sections 4-7).
Fails closed with typed refusals and never downloads: until root registers a
hash-bound ``demucs-htdemucs_6s-5c90dfd2`` entry in ``program/models.json`` every
valid request refuses ``model_not_registered``. Inference, when admitted, runs in
an isolated child interpreter (``infer --task``) on a source-timed excerpt of a
manifest-verified run WAV. The parent measures a low-end check (20-45 Hz band
energy of each estimate against the input) and mixture consistency in the
stdlib. Also hosts the deterministic ``s3-stems-1`` fixture generator and the
seal-before-truth harness (section 8).

Top-level imports are stdlib only. torch/torchaudio/demucs/numpy are imported
only inside ``infer_task`` in the child interpreter.
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
import shutil
import signal
import statistics
import struct
import subprocess
import sys
import time
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
TOOL = 'stems_estimate'
MODEL_ID = 'demucs-htdemucs_6s-5c90dfd2'
SOURCES = ('drums', 'bass', 'other', 'vocals', 'guitar', 'piano')  # upstream order as recalled; runtime lane confirms
MODEL_RATE = 44100
MODEL_CHANNELS = 2
SEED = 20261007
THREADS = 2
APPLY_SETTINGS = {'shifts': 1, 'overlap': 0.25, 'split': True, 'segment': None}  # recalled CLI defaults; runtime lane confirms
# Pinned by a separate root-run runtime lane after qualification. None refuses runtime_unavailable / not_pinned.
DEMUCS_PIN: str | None = None
TORCH_PIN: str | None = None
RUNTIME_ENV_VAR = 'VIDEO_UTILS_STEMS_RUNTIME_PYTHON'
LIMITS = {'input_seconds': 300.0, 'excerpt_min_seconds': 1.0, 'excerpt_max_seconds': 30.0,
          'deadline_seconds': 600, 'rss_bytes': 3 * 1024**3, 'manifest_bytes': 1024**2, 'registry_bytes': 1024**2,
          'max_model_bytes': 2 * 1024**3, 'request_bytes': 64 * 1024, 'probe_seconds': 60, 'ffmpeg_seconds': 120,
          'log_bytes': 10 * 1024**2, 'timeout_default': 660, 'timeout_max': 900}
RUNS_REL = Path('artifacts/runs')
LANE_REL = Path('artifacts/s2/stems_contract')
FIXTURES_REL = LANE_REL / 'fixtures'
ESTIMATES_REL = LANE_REL / 'estimates'
RUNTIME_REL = Path('artifacts/model-runtime-env')
UNREACHABLE_PROXY = 'http://127.0.0.1:9'
FORWARD_FILTER = f'aresample={MODEL_RATE}:resampler=swr'
BAND_HZ = (20.0, 45.0)
REFERENCE_BAND_HZ = (45.0, 120.0)
BUTTERWORTH4_Q = (0.5412, 1.3066)
LOW_END_FILTER = 'rbj_butterworth4_bandpass_cascade'
REQUEST_KEYS = {'run_dir', 'input_role', 'excerpt_start_seconds', 'excerpt_end_seconds', 'timeout_seconds'}
REQUIRED_REQUEST_KEYS = {'run_dir', 'excerpt_start_seconds', 'excerpt_end_seconds'}
INPUT_ROLES = {'denoised': 'denoised.wav', 'source': 'source.wav'}

# Contract 7.1: always present at exactly these values (17).
UNKNOWN_FIELDS = {
    'estimate_from_mono_mixture': True,
    'recovered_original_stem': False,
    'stem_semantics': 'model_target_allocation_not_instrument_identity',
    'instrument_presence_claim': 'none',
    'separation_accuracy': 'unknown',
    'low_end_preservation_verdict': None,
    'listening_accepted': False,
    'bleed_artifact_review': 'not_performed',
    'default_adoption': False,
    'cleanup_default': False,
    'master_eligible': False,
    'in_room_tone_recreated': False,
    'note_correctness': None,
    'performance_issue': None,
    'expected_rhythm_reference': None,
    'claim_class': 'model_output_measurement',
    'redistribution_permitted': False,
}
# Contract 7.2.
LIMITATIONS = [
    'All six outputs are htdemucs_6s allocations of one mono mixture to trained target labels, not recovered original stems; '
    'a drums, bass, vocals or piano label does not identify an instrument or assert that it is present.',
    'Low-end numbers are 20-45 Hz band-energy measurements on estimates; they do not show that ~32 Hz content of the '
    'nine-string is musically preserved, and listening review is a separate, unperformed step.',
    'C1 (32.70 Hz theoretical) guitar energy may be allocated to bass and click attacks to drums; read guitar_plus_bass '
    'and per-stem band shares before reading the guitar estimate alone.',
    'The model was trained on full-band music (MUSDB18-HQ plus undisclosed sets); its behaviour on a heavily distorted '
    'down-tuned nine-string recorded on a phone with a box fan is unknown (separation_accuracy unknown).',
    'The weights are limited to personal/research use by the maintainer; real-take outputs are private (V6), stay under '
    'ignored artifacts and are never redistributed.',
    'An estimate is never a cleanup, denoise, tone, dynamics or master input by default and never replaces the run audio.',
]
RESULT_KEYS = frozenset({'schema_version', 'status', 'tool', 'model_identity', 'runtime_identity', 'input_identity',
                         'excerpt', 'analysed_input', 'stems', 'low_end_check', 'mixture_consistency',
                         'resource_receipt', 'privacy', 'limitations', *UNKNOWN_FIELDS})


class Refused(Exception):
    def __init__(self, code: str, message: str, runtime_reason: str | None = None):
        super().__init__(message)
        self.code = code
        self.runtime_reason = runtime_reason


class Failed(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def refusal(code: str, message: str, runtime_reason: str | None = None) -> dict:
    return {'schema_version': 1, 'status': 'refused', 'refusal_code': code, 'message': message,
            'runtime_reason': runtime_reason, 'model_id': MODEL_ID, 'network_used': False, 'model_acquired': False,
            'default_adoption': False, 'recovered_original_stem': False}


def failure(code: str, message: str) -> dict:
    return {'schema_version': 1, 'status': 'failed', 'failure_code': code, 'message': message[:2000],
            'model_id': MODEL_ID, 'network_used': False, 'model_acquired': False, 'default_adoption': False,
            'recovered_original_stem': False}


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


def strict_loads(data) -> object:
    def reject(value):
        raise ValueError(f'non-finite JSON number {value}')
    return json.loads(data, parse_constant=reject)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- request (orders 1-2, no I/O)

def validate_request(request) -> dict:
    if not isinstance(request, dict):
        raise Refused('request_invalid', 'Request must be a JSON object')
    extra = set(request) - REQUEST_KEYS
    missing = REQUIRED_REQUEST_KEYS - set(request)
    if extra or missing:
        raise Refused('request_invalid', f'Closed request schema: extra={sorted(extra)} missing={sorted(missing)}')
    run_dir = request['run_dir']
    if not isinstance(run_dir, str) or not 1 <= len(run_dir) <= 4096 or '\0' in run_dir:
        raise Refused('request_invalid', 'run_dir must be a string of 1-4096 characters without NUL')
    role = request.get('input_role', 'denoised')
    if role not in INPUT_ROLES:
        raise Refused('request_invalid', 'input_role must be denoised or source')
    start, end = request['excerpt_start_seconds'], request['excerpt_end_seconds']
    if not finite_number(start) or not finite_number(end):
        raise Refused('request_invalid', 'excerpt bounds must be finite numbers')
    if start < 0 or end <= start:
        raise Refused('request_invalid', 'excerpt_start_seconds >= 0 and excerpt_end_seconds > start are required')
    timeout = request.get('timeout_seconds', LIMITS['timeout_default'])
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= LIMITS['timeout_max']:
        raise Refused('request_invalid', 'timeout_seconds must be an integer in [1, 900]')
    length = end - start
    if length < LIMITS['excerpt_min_seconds']:
        raise Refused('request_invalid', 'Excerpt must be at least 1.0 s')
    if length > LIMITS['excerpt_max_seconds']:
        raise Refused('excerpt_too_long', 'Excerpt must be at most 30.0 s (contract section 4)')
    return {'run_dir': run_dir, 'input_role': role, 'excerpt_start_seconds': float(start),
            'excerpt_end_seconds': float(end), 'timeout_seconds': timeout}


# --------------------------------------------------------------------------- registry and model file (orders 3-8)

def resolve_model(root: Path = ROOT) -> dict:
    """Reads only program/models.json and models/<id>.bin. Never downloads; never falls back."""
    registry_path = root / 'program' / 'models.json'
    try:
        if registry_path.is_symlink() or not registry_path.is_file():
            raise ValueError('registry missing or symlinked')
        registry_bytes = read_bounded(registry_path, LIMITS['registry_bytes'])
        registry = strict_loads(registry_bytes)
    except (OSError, ValueError) as exc:
        raise Refused('model_not_registered', f'program/models.json unreadable ({exc}); no download is attempted')
    models = registry.get('models') if isinstance(registry, dict) else None
    if not isinstance(registry, dict) or registry.get('schema_version') != 1 or not isinstance(models, dict):
        raise Refused('model_not_registered', 'Model registry requires schema_version 1 with a models object')
    entry = models.get(MODEL_ID)
    if not isinstance(entry, dict):
        raise Refused('model_not_registered', f'{MODEL_ID} is not registered; root adds it after an explicit hash-bound fetch '
                      'and the operator terms acknowledgement (draft: program/model-drafts/htdemucs_6s.json)')
    digest = entry.get('sha256')
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise Refused('model_hash_not_registered', f'{MODEL_ID} has no registered lowercase sha256 (null or placeholder)')
    url, license_text, limit = entry.get('url'), entry.get('license'), entry.get('max_bytes')
    parsed = urllib.parse.urlparse(url) if isinstance(url, str) else None
    if (not isinstance(license_text, str) or not license_text.strip() or not isinstance(limit, int) or isinstance(limit, bool)
            or not 0 < limit <= LIMITS['max_model_bytes'] or parsed is None or parsed.scheme != 'https'
            or not parsed.hostname or parsed.username or parsed.password):
        raise Refused('model_registry_entry_invalid', f'{MODEL_ID} entry needs a licence, max_bytes in (0, 2 GiB] and an HTTPS url without userinfo')
    ack = entry.get('operator_terms_acknowledgement')
    if not isinstance(ack, str) or not ack.strip():
        raise Refused('model_terms_not_acknowledged', 'The maintainer limits these weights to personal/research use; an explicit '
                      'operator acknowledgement receipt is required before first use (research condition 5)')
    models_dir = root / 'models'
    model_path = models_dir / f'{MODEL_ID}.bin'
    if models_dir.is_symlink() or model_path.is_symlink() or not model_path.is_file() or model_path.stat().st_size > limit:
        raise Refused('model_file_missing', f'models/{MODEL_ID}.bin missing, symlinked or larger than max_bytes; '
                      f'root runs an explicit hash-bound prefetch')
    if sha256_file(model_path) != digest:
        raise Refused('model_hash_mismatch', f'models/{MODEL_ID}.bin sha256 differs from the registry')
    return {'model_id': MODEL_ID, 'sha256': digest, 'source_url': url, 'license': license_text,
            'license_verdict': entry.get('license_verdict'), 'terms_acknowledgement': ack,
            'registry_sha256': sha256_bytes(registry_bytes), 'path': str(model_path), 'bytes': model_path.stat().st_size}


# --------------------------------------------------------------------------- runtime (order 9)

RUNTIME_PROBE = (
    'import importlib.metadata as m, json, platform, sys\n'
    'def v(name):\n'
    '    try:\n'
    '        return m.version(name)\n'
    '    except Exception:\n'
    '        return None\n'
    'print(json.dumps({"python": platform.python_version(), "machine": platform.machine(), "system": sys.platform,'
    ' "torch": v("torch"), "demucs": v("demucs")}))\n')


def isolated_env(empty: Path) -> dict:
    threads = str(THREADS)
    return {'PATH': '/usr/bin:/bin', 'HOME': str(empty), 'TORCH_HOME': str(empty), 'HF_HOME': str(empty),
            'XDG_CACHE_HOME': str(empty), 'HTTP_PROXY': UNREACHABLE_PROXY, 'HTTPS_PROXY': UNREACHABLE_PROXY,
            'http_proxy': UNREACHABLE_PROXY, 'https_proxy': UNREACHABLE_PROXY, 'NO_PROXY': '', 'no_proxy': '',
            'OMP_NUM_THREADS': threads, 'OPENBLAS_NUM_THREADS': threads, 'MKL_NUM_THREADS': threads,
            'PYTHONDONTWRITEBYTECODE': '1', 'CUDA_VISIBLE_DEVICES': ''}


def default_probe(interpreter: Path) -> dict:
    empty = Path(os.path.abspath(interpreter)).parent  # never written; HOME only
    completed = subprocess.run([str(interpreter), '-I', '-c', RUNTIME_PROBE], stdin=subprocess.DEVNULL,
                               capture_output=True, text=True, timeout=LIMITS['probe_seconds'], env=isolated_env(empty),
                               check=False)
    if completed.returncode:
        raise RuntimeError(f'probe exited {completed.returncode}')
    report = strict_loads(completed.stdout.strip().splitlines()[-1])
    if not isinstance(report, dict):
        raise RuntimeError('probe returned a non-object')
    return report


def default_runtime_resolver(root: Path = ROOT, environ: dict | None = None, system: str | None = None,
                             probe=None) -> dict:
    environ = os.environ if environ is None else environ
    system = sys.platform if system is None else system
    raw = environ.get(RUNTIME_ENV_VAR)
    if not raw:
        raise Refused('runtime_unavailable', f'{RUNTIME_ENV_VAR} is not set; a separate root-run runtime lane prepares it',
                      'not_configured')
    if not system.startswith('linux'):
        raise Refused('runtime_unavailable', 'htdemucs_6s inference is qualified only on Linux CPU (honey)', 'platform_unsupported')
    base = root / RUNTIME_REL
    path = Path(raw)
    if not path.is_absolute() or '..' in path.parts or not Path(os.path.abspath(path)).is_relative_to(base):
        raise Refused('runtime_unavailable', f'Runtime interpreter must be an absolute path beneath {RUNTIME_REL}', 'path_rejected')
    for item in (path, *path.parents):
        if item.is_symlink():
            raise Refused('runtime_unavailable', f'Symlinked runtime path component: {item.name}', 'path_rejected')
        if item == root:
            break
    if not path.is_file() or not os.access(path, os.X_OK):
        raise Refused('runtime_unavailable', 'Runtime interpreter is not an executable regular file', 'path_rejected')
    if DEMUCS_PIN is None or TORCH_PIN is None:
        raise Refused('runtime_unavailable', 'DEMUCS_PIN/TORCH_PIN are unset until the runtime lane qualifies them', 'not_pinned')
    try:
        report = (probe or default_probe)(path)
    except Exception as exc:  # noqa: BLE001 - any probe failure, incl. timeout, is identity_failed
        raise Refused('runtime_unavailable', f'Runtime identity probe failed: {type(exc).__name__}', 'identity_failed')
    if report.get('torch') != TORCH_PIN or report.get('demucs') != DEMUCS_PIN:
        raise Refused('runtime_unavailable', f'Runtime versions torch={report.get("torch")} demucs={report.get("demucs")} '
                      f'differ from pins torch={TORCH_PIN} demucs={DEMUCS_PIN}', 'not_pinned')
    rel = path.relative_to(root) if path.is_relative_to(root) else path
    return {'kind': 'isolated_child', 'python': str(rel), 'interpreter': str(path), 'python_version': report.get('python'),
            'torch': report.get('torch'), 'demucs': report.get('demucs'),
            'platform': f"{str(report.get('system', 'linux')).rstrip('0123456789')}-{report.get('machine')}"}


# --------------------------------------------------------------------------- WAV I/O (stdlib)

def wav_header(path: Path) -> dict:
    """RIFF/WAVE: PCM 16/24/32-bit or IEEE float32, incl. WAVE_FORMAT_EXTENSIBLE."""
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
                if (kind is None or channels < 1 or rate < 1 or align != channels * bits // 8
                        or (kind == 'pcm' and bits not in (16, 24, 32)) or (kind == 'float' and bits != 32)):
                    raise ValueError('unsupported WAV sample format')
                frames = size // align
                return {'format': kind, 'channels': channels, 'rate': rate, 'bits': bits, 'block_align': align,
                        'data_offset': source.tell(), 'frames': frames, 'duration_seconds': frames / rate}
            else:
                source.seek(size + (size % 2), 1)
    raise ValueError('no data chunk')


def read_wav(path: Path, first: int = 0, count: int | None = None) -> tuple[list[array.array], int]:
    """Exact frames [first, first+count) as per-channel float arrays in [-1, 1] (float32 values stay exact)."""
    header = wav_header(path)
    channels, align = header['channels'], header['block_align']
    count = header['frames'] - first if count is None else count
    if first < 0 or count < 0 or first + count > header['frames']:
        raise ValueError('frame range outside the WAV')
    with Path(path).open('rb') as source:
        source.seek(header['data_offset'] + first * align)
        raw = source.read(count * align)
    if len(raw) != count * align:
        raise ValueError('short WAV data')
    width = header['bits'] // 8
    if header['format'] == 'float':
        values, scale = array.array('f'), None
        values.frombytes(raw)
    elif width == 2:
        values, scale = array.array('h'), 1 / 32768
        values.frombytes(raw)
    elif width == 4:
        values, scale = array.array('i'), 1 / 2147483648
        values.frombytes(raw)
    else:
        values = array.array('i', (int.from_bytes(raw[i:i + 3], 'little', signed=True) for i in range(0, len(raw), 3)))
        scale = 1 / 8388608
    if sys.byteorder != 'little' and width != 3:
        values.byteswap()
    out = []
    for c in range(channels):
        lane = values[c::channels]
        out.append(array.array('d', lane) if scale is None else array.array('d', (v * scale for v in lane)))
    return out, header['rate']


def wav_float_bytes(channels: list, rate: int) -> bytes:
    """Interleaved IEEE float32 WAV (format tag 3) bytes."""
    n_ch, frames = len(channels), len(channels[0])
    if any(len(ch) != frames for ch in channels):
        raise ValueError('channel lengths differ')
    data = array.array('f', bytes(4 * frames * n_ch))
    for c, ch in enumerate(channels):
        data[c::n_ch] = array.array('f', ch)
    if sys.byteorder != 'little':
        data.byteswap()
    payload = data.tobytes()
    fmt = struct.pack('<HHIIHH', 3, n_ch, rate, rate * 4 * n_ch, 4 * n_ch, 32)
    body = b'WAVE' + b'fmt ' + struct.pack('<I', len(fmt)) + fmt + b'data' + struct.pack('<I', len(payload)) + payload
    return b'RIFF' + struct.pack('<I', len(body)) + body


def write_wav_float(path: Path, channels: list, rate: int) -> str:
    data = wav_float_bytes(channels, rate)
    with Path(path).open('xb') as target:
        target.write(data)
    return sha256_bytes(data)


# --------------------------------------------------------------------------- input (order 10)

def no_symlink_components(path: Path, root: Path, code: str = 'input_not_admitted') -> None:
    for item in (path, *path.parents):
        if item.is_symlink():
            raise Refused(code, f'Symlinked path component: {item.name}')
        if item == root:
            return


def contained(raw: str | Path, root: Path, allowed: tuple[Path, ...], code: str = 'input_not_admitted') -> Path:
    if '..' in Path(raw).parts or '\\' in str(raw):
        raise Refused(code, 'Traversal or backslash components are rejected')
    path = Path(raw) if Path(raw).is_absolute() else root / raw
    path = Path(os.path.abspath(path))
    if not any(path.is_relative_to(root / base) and path != root / base for base in allowed):
        raise Refused(code, 'Path must be beneath ' + ' or '.join(str(b) for b in allowed))
    no_symlink_components(path, root, code)
    return path


def is_generated_fixture(manifest: dict) -> bool:
    source = manifest.get('source')
    return (isinstance(source, dict) and source.get('kind') == 'generated_fixture'
            and isinstance(source.get('generator'), str) and bool(source.get('generator'))
            and isinstance(source.get('seed'), int) and not isinstance(source.get('seed'), bool))


def resolve_input(root: Path, request: dict) -> dict:
    directory = contained(request['run_dir'], root, (RUNS_REL, FIXTURES_REL))
    if not directory.is_dir():
        raise Refused('input_not_admitted', 'run_dir must be an existing directory')
    manifest_path = directory / 'manifest.json'
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise Refused('input_not_admitted', 'Regular manifest.json required')
    try:
        manifest_bytes = read_bounded(manifest_path, LIMITS['manifest_bytes'])
        manifest = strict_loads(manifest_bytes)
    except (OSError, ValueError) as exc:
        raise Refused('input_not_admitted', f'Manifest unreadable, invalid or over 1 MiB: {exc}')
    if not isinstance(manifest, dict):
        raise Refused('input_not_admitted', 'Manifest must be a JSON object')
    name = INPUT_ROLES[request['input_role']]
    audio = directory / name
    if audio.is_symlink() or not audio.is_file():
        raise Refused('input_not_admitted', f'Regular {name} required')
    recorded = manifest.get('output_sha256')
    recorded = recorded.get(name) if isinstance(recorded, dict) else None
    identity = sha256_file(audio)
    if recorded != identity:
        raise Refused('input_not_admitted', f'{name} sha256 differs from manifest output_sha256')
    timeline = manifest.get('timeline')
    origin = timeline.get('audio_start_seconds') if isinstance(timeline, dict) else None
    if not finite_number(origin):
        raise Refused('input_not_admitted', 'timeline.audio_start_seconds must be explicit and finite; never defaulted to zero')
    source = manifest.get('source')
    source_sha = source.get('sha256') if isinstance(source, dict) else None
    if not isinstance(source_sha, str) or not re.fullmatch(r'[0-9a-f]{64}', source_sha):
        raise Refused('input_not_admitted', 'manifest source.sha256 must be 64 lowercase hex')
    try:
        header = wav_header(audio)
    except (OSError, ValueError) as exc:
        raise Refused('input_not_admitted', f'Unreadable or unsupported WAV: {exc}')
    if header['channels'] != 1:
        raise Refused('input_not_admitted', 'Input must be mono so every output is an estimate from a mono mixture')
    if not 0 < header['duration_seconds'] <= LIMITS['input_seconds']:
        raise Refused('input_not_admitted', 'Input duration must be in (0, 300] seconds')
    rate = header['rate']
    start_frame = round(request['excerpt_start_seconds'] * rate)
    end_frame = round(request['excerpt_end_seconds'] * rate)
    if end_frame > header['frames']:
        raise Refused('input_not_admitted', 'Excerpt end lies beyond the input duration')
    under_fixtures = directory.is_relative_to(root / FIXTURES_REL)
    return {'directory': directory, 'path': audio, 'input_role': request['input_role'],
            'path_role': f"{'fixture_case' if under_fixtures else 'run'}_{request['input_role']}_wav",
            'input_sha256': identity, 'run_manifest_sha256': sha256_bytes(manifest_bytes), 'source_sha256': source_sha,
            'origin': float(origin), 'rate': rate, 'frames': header['frames'], 'start_frame': start_frame,
            'frame_count': end_frame - start_frame, 'real_take': not is_generated_fixture(manifest)}


# --------------------------------------------------------------------------- DSP (stdlib)

def biquad_coefficients(kind: str, frequency: float, q: float, rate: int) -> tuple[float, ...]:
    """RBJ audio-EQ-cookbook high/low-pass, normalised by a0."""
    w0 = 2 * math.pi * frequency / rate
    cos_w, alpha = math.cos(w0), math.sin(w0) / (2 * q)
    if kind == 'highpass':
        b0, b1, b2 = (1 + cos_w) / 2, -(1 + cos_w), (1 + cos_w) / 2
    elif kind == 'lowpass':
        b0, b1, b2 = (1 - cos_w) / 2, 1 - cos_w, (1 - cos_w) / 2
    else:
        raise ValueError(kind)
    a0, a1, a2 = 1 + alpha, -2 * cos_w, 1 - alpha
    return b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0


def biquad(samples, coefficients) -> array.array:
    b0, b1, b2, a1, a2 = coefficients
    out = array.array('d', bytes(8 * len(samples)))
    z1 = z2 = 0.0
    for i, x in enumerate(samples):
        y = b0 * x + z1
        z1 = b1 * x - a1 * y + z2
        z2 = b2 * x - a2 * y
        out[i] = y
    return out


def bandpass(samples, rate: int, low: float, high: float) -> array.array:
    """Butterworth-4 high-pass at `low` then Butterworth-4 low-pass at `high` (2 + 2 RBJ biquads)."""
    out = samples
    for q in BUTTERWORTH4_Q:
        out = biquad(out, biquad_coefficients('highpass', low, q, rate))
    for q in BUTTERWORTH4_Q:
        out = biquad(out, biquad_coefficients('lowpass', high, q, rate))
    return out


def mean_square(samples, skip: int = 0) -> float:
    n = len(samples) - skip
    if n <= 0:
        return 0.0
    return math.fsum(v * v for v in samples[skip:]) / n


def db_ratio(numerator: float, denominator: float, zero_reference: str, zero_numerator: str) -> tuple[float | None, str | None]:
    if denominator <= 0:
        return None, zero_reference
    if numerator <= 0:
        return None, zero_numerator
    return 10 * math.log10(numerator / denominator), None


def low_end_measurements(input_mono, stems_mono: dict, rate: int, length_seconds: float) -> tuple[dict, dict]:
    """Contract 7: band energies (mean squares over measured frames at R) and mixture consistency."""
    settle = min(0.25, 0.25 * length_seconds)
    skip = min(len(input_mono), round(settle * rate))
    inp_band = bandpass(input_mono, rate, *BAND_HZ)
    inp_ref = bandpass(input_mono, rate, *REFERENCE_BAND_HZ)
    e_in_band, e_in_ref = mean_square(inp_band, skip), mean_square(inp_ref, skip)
    band = {name: bandpass(stems_mono[name], rate, *BAND_HZ) for name in SOURCES}
    energies = {name: mean_square(band[name], skip) for name in SOURCES}
    stem_sum = math.fsum(energies.values())
    per_stem = {}
    for name in SOURCES:
        ratio, reason = db_ratio(energies[name], e_in_band, 'zero_input_band_energy', 'zero_stem_band_energy')
        per_stem[name] = {'band_energy': energies[name],
                          'reference_band_energy': mean_square(bandpass(stems_mono[name], rate, *REFERENCE_BAND_HZ), skip),
                          'band_ratio_to_input_db': ratio, 'band_ratio_to_input_db_reason': reason,
                          'band_share_of_stem_sum': energies[name] / stem_sum if stem_sum > 0 else None,
                          'band_share_of_stem_sum_reason': None if stem_sum > 0 else 'zero_stem_band_sum'}
    gb = array.array('d', (g + b for g, b in zip(band['guitar'], band['bass'])))
    g_db, g_reason = db_ratio(energies['guitar'], e_in_band, 'zero_input_band_energy', 'zero_guitar_band_energy')
    gb_db, gb_reason = db_ratio(mean_square(gb, skip), e_in_band, 'zero_input_band_energy', 'zero_guitar_plus_bass_band_energy')
    low_end = {'band_hz': list(BAND_HZ), 'reference_band_hz': list(REFERENCE_BAND_HZ), 'filter': LOW_END_FILTER,
               'biquad_q': list(BUTTERWORTH4_Q), 'rate_hz': rate, 'settle_excluded_seconds': settle,
               'measured_frames': len(input_mono) - skip,
               'input': {'band_energy': e_in_band, 'reference_band_energy': e_in_ref},
               'per_stem': per_stem,
               'guitar_vs_input_band_db': g_db, 'guitar_vs_input_band_db_reason': g_reason,
               'guitar_plus_bass_vs_input_band_db': gb_db, 'guitar_plus_bass_vs_input_band_db_reason': gb_reason,
               'status': 'measured' if e_in_band > 0 else 'zero_reference',
               'claim_class': 'measurement_on_model_output'}
    residual = array.array('d', (sum(parts) - x for parts, x in zip(zip(*(stems_mono[name] for name in SOURCES)), input_mono)))
    residual_band = array.array('d', (sum(parts) - x for parts, x in zip(zip(*(band[name] for name in SOURCES)), inp_band)))
    full_db, full_reason = db_ratio(mean_square(residual, skip), mean_square(input_mono, skip), 'zero_input_energy', 'zero_residual_energy')
    band_db, band_reason = db_ratio(mean_square(residual_band, skip), e_in_band, 'zero_input_band_energy', 'zero_residual_band_energy')
    mixture = {'residual_vs_input_full_db': full_db, 'residual_vs_input_full_db_reason': full_reason,
               'residual_vs_input_band_db': band_db, 'residual_vs_input_band_db_reason': band_reason,
               'residual_definition': 'sum of six estimates minus input excerpt, measured frames after settle exclusion',
               'claim_class': 'measurement_on_model_output'}
    return low_end, mixture


# --------------------------------------------------------------------------- sample-rate conversion (FFmpeg swr)

def return_filter(rate: int) -> str:
    return f'aresample={int(rate)}:resampler=swr'


def ffmpeg_resample(samples, from_rate: int, filter_string: str, scratch: Path, tag: str) -> list:
    sys.path.insert(0, str(SCRIPTS))
    import media  # stdlib; honours FFMPEG
    try:
        executable = media.executable('ffmpeg')
    except media.MediaError as exc:
        raise Failed('resampler_unavailable', str(exc))
    source, target = scratch / f'{tag}-in.wav', scratch / f'{tag}-out.wav'
    write_wav_float(source, [samples], from_rate)
    command = [executable, '-hide_banner', '-nostdin', '-loglevel', 'error', '-threads', str(THREADS),
               '-i', str(source), '-af', filter_string, '-c:a', 'pcm_f32le', '-f', 'wav', '-n', str(target)]
    try:
        completed = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                   timeout=LIMITS['ffmpeg_seconds'], check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Failed('resampler_failed', f'ffmpeg did not finish: {type(exc).__name__}')
    if completed.returncode:
        raise Failed('resampler_failed', f'ffmpeg exited {completed.returncode}: {completed.stderr[-500:]}')
    channels, _ = read_wav(target)
    source.unlink()
    target.unlink()
    return channels[0]


def fit_length(samples, frames: int) -> tuple[array.array, int]:
    adjust = frames - len(samples)
    out = array.array('d', samples[:frames])
    if adjust > 0:
        out.extend([0.0] * adjust)
    return out, adjust


# --------------------------------------------------------------------------- isolated child separator

def bounded_child(command: list[str], workdir: Path, env: dict, deadline_seconds: float) -> dict:
    """Own process group, deadline and RSS ceiling (R-N11: direct child checked by PPID)."""
    peak, stopped, error = 0, None, None
    started = time.monotonic()
    deadline = started + deadline_seconds
    with (workdir / 'worker.stdout.log').open('xb') as stdout, (workdir / 'worker.stderr.log').open('xb') as stderr:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, env=env,
                                   cwd=workdir, start_new_session=True)
        try:
            while process.poll() is None:
                snapshot = subprocess.run(['ps', '-p', str(process.pid), '-o', 'ppid=,rss='], capture_output=True,
                                          text=True, timeout=5).stdout.split()
                if len(snapshot) == 2:
                    if int(snapshot[0]) != os.getpid():
                        raise ValueError('inference worker ownership mismatch')
                    peak = max(peak, int(snapshot[1]) * 1024)
                if peak > LIMITS['rss_bytes'] or time.monotonic() >= deadline:
                    stopped = 'rss_bound' if peak > LIMITS['rss_bytes'] else 'deadline'
                    break
                if stdout.tell() + stderr.tell() > LIMITS['log_bytes']:
                    stopped = 'log_byte_bound'
                    break
                time.sleep(.1)
        except Exception as exc:  # noqa: BLE001
            stopped, error = 'monitor_error', exc
        finally:
            if process.poll() is None:
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(process.pid, sig)
                    except (ProcessLookupError, PermissionError):
                        pass
                    try:
                        process.wait(timeout=3)
                        break
                    except subprocess.TimeoutExpired:
                        continue
            else:
                process.wait(timeout=3)
    receipt = {'pid': process.pid, 'owner_pid': os.getpid(), 'ownership': 'Popen direct child in its own session/process group',
               'ruling': 'R-N11', 'termination_reason': stopped, 'returncode': process.returncode,
               'observed_peak_rss_bytes': peak, 'rss_bound_bytes': LIMITS['rss_bytes'],
               'deadline_seconds': deadline_seconds, 'elapsed_seconds': time.monotonic() - started}
    (workdir / 'worker-resource.json').write_text(json.dumps(receipt, indent=2) + '\n')
    if stopped or process.returncode:
        tail = (workdir / 'worker.stderr.log').read_text(errors='replace')[-800:]
        raise Failed('inference_failed', 'Bounded htdemucs_6s inference failed: ' + str(error or stopped or tail))
    return receipt


class ChildSeparator:
    """Default separator: runs this file's `infer --task` in the qualified isolated interpreter."""

    def __init__(self, root: Path, runtime: dict):
        self.root, self.runtime, self.last_receipt = root, runtime, None

    def __call__(self, stereo_44k, model: dict, workdir: Path) -> dict:
        model_input = workdir / 'model_input.wav'
        header = wav_header(model_input)
        if header['frames'] != len(stereo_44k[0]) or header['channels'] != MODEL_CHANNELS or header['rate'] != MODEL_RATE:
            raise Failed('analysed_input_mismatch', 'model_input.wav differs from the in-memory analysed input')
        # Re-verify immediately before launch: a pickle-format package is only unpickled after this check.
        if sha256_file(Path(model['path'])) != model['sha256']:
            raise Failed('model_changed', 'Checkpoint sha256 changed before inference')
        empty = workdir / 'empty-cache'
        empty.mkdir(mode=0o700)
        out = workdir / 'model_out'
        out.mkdir(mode=0o700)
        task = {'model_path': model['path'], 'model_sha256': model['sha256'], 'input_path': str(model_input),
                'input_sha256': sha256_file(model_input), 'output_dir': str(out), 'sources': list(SOURCES),
                'seed': SEED, 'threads': THREADS, 'apply_settings': APPLY_SETTINGS, 'model_rate': MODEL_RATE,
                'model_channels': MODEL_CHANNELS}
        task_path = workdir / 'task.json'
        task_path.write_text(json.dumps(task, indent=2) + '\n')
        receipt = bounded_child([self.runtime['interpreter'], '-I', str(Path(__file__).resolve()), 'infer', '--task', str(task_path)],
                                workdir, isolated_env(empty), LIMITS['deadline_seconds'])
        report = strict_loads(read_bounded(workdir / 'inference.json', 1024**2))
        stems = {}
        for name in SOURCES:
            channels, rate = read_wav(out / f'{name}.wav')
            if rate != MODEL_RATE or len(channels) != MODEL_CHANNELS:
                raise Failed('separator_output_invalid', f'{name} estimate is not {MODEL_RATE} Hz stereo')
            stems[name] = channels
        self.last_receipt = {'checkpoint_load': report.get('checkpoint_load'), 'torch': report.get('torch'),
                             'demucs': report.get('demucs'), 'python': report.get('python'),
                             'max_rss_bytes': receipt['observed_peak_rss_bytes'], 'elapsed_seconds': receipt['elapsed_seconds']}
        return stems


def infer_task(task_path: Path) -> int:  # pragma: no cover - executed only in the isolated Linux runtime
    """Child entry. Loads only the sha256-verified local file; hub/URL loaders are disabled."""
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[key] = str(THREADS)
    task = strict_loads(read_bounded(Path(task_path), 1024**2))
    if sha256_file(Path(task['model_path'])) != task['model_sha256'] or sha256_file(Path(task['input_path'])) != task['input_sha256']:
        raise ValueError('Model or input identity changed before inference')
    import socket

    def no_network(*args, **kwargs):
        raise RuntimeError('network disabled in the stems_estimate child')
    socket.socket.connect = no_network
    socket.create_connection = no_network
    import importlib.metadata
    import resource
    import numpy as np
    import torch
    torch.set_num_threads(THREADS)
    random.seed(SEED)
    torch.manual_seed(SEED)
    torch.hub.load_state_dict_from_url = no_network
    torch.hub.download_url_to_file = no_network
    from demucs.apply import apply_model
    from demucs.states import load_model
    path = Path(task['model_path'])
    if path.is_symlink() or not path.is_file():
        raise ValueError('Only the verified local checkpoint may be loaded')
    try:
        package = torch.load(str(path), map_location='cpu', weights_only=True)
        mode = 'weights_only'
    except Exception:  # noqa: BLE001 - demucs packages pickle the model class
        if sha256_file(path) != task['model_sha256']:
            raise ValueError('Checkpoint changed between verification and load')
        package = torch.load(str(path), map_location='cpu', weights_only=False)
        mode = 'pickle_after_sha256_verify'
    model = load_model(package)
    model.eval()
    if tuple(model.sources) != tuple(task['sources']) or model.samplerate != task['model_rate'] or model.audio_channels != task['model_channels']:
        raise ValueError(f'model identity mismatch: sources={list(model.sources)} rate={model.samplerate} channels={model.audio_channels}')
    channels, rate = read_wav(Path(task['input_path']))
    if rate != task['model_rate'] or len(channels) != task['model_channels']:
        raise ValueError('analysed input is not model-rate stereo')
    wav = torch.tensor(np.array([np.asarray(c, dtype=np.float32) for c in channels]))
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std()
    std = std if float(std) > 0 else torch.tensor(1.0)
    settings = task['apply_settings']
    with torch.no_grad():
        sources = apply_model(model, ((wav - mean) / std)[None], shifts=settings['shifts'], split=settings['split'],
                              overlap=settings['overlap'], segment=settings['segment'], progress=False, device='cpu',
                              num_workers=0)[0]
    sources = sources * std + mean
    if not torch.isfinite(sources).all():
        raise ValueError('non-finite separator output')
    out = Path(task['output_dir'])
    for index, name in enumerate(task['sources']):
        data = sources[index].numpy().astype('<f4')
        write_wav_float(out / f'{name}.wav', [data[0].tolist(), data[1].tolist()], rate)
    report = {'checkpoint_load': mode, 'torch': torch.__version__, 'demucs': importlib.metadata.version('demucs'),
              'numpy': np.__version__, 'python': platform.python_version(),
              'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
              'normalisation': 'upstream separate-CLI mixture mean/std (std 0 guarded to 1)', 'sources': list(model.sources)}
    (Path(task_path).parent / 'inference.json').write_text(json.dumps(report, allow_nan=False) + '\n')
    return 0


# --------------------------------------------------------------------------- worker entry

def lane_dir(root: Path, relative: Path, name: str) -> Path:
    base = root / relative
    target = base / name
    no_symlink_components(base, root, 'output_path_rejected')
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    no_symlink_components(base, root, 'output_path_rejected')
    target.mkdir(mode=0o700)
    return target


def validate_separator_output(stems, frames: int) -> dict:
    if not isinstance(stems, dict) or set(stems) != set(SOURCES):
        raise Failed('separator_output_invalid', f'Separator must return exactly {list(SOURCES)}')
    out = {}
    for name in SOURCES:
        channels = stems[name]
        if len(channels) != MODEL_CHANNELS or any(len(c) != frames for c in channels):
            raise Failed('separator_output_invalid', f'{name} must be {MODEL_CHANNELS} x {frames} at {MODEL_RATE} Hz')
        left, right = channels
        if not all(math.isfinite(v) for v in left) or not all(math.isfinite(v) for v in right):
            raise Failed('separator_output_invalid', f'{name} contains non-finite samples')
        out[name] = array.array('d', ((a + b) * 0.5 for a, b in zip(left, right)))  # stereo_mean_to_mono
    return out


def run_estimate(request, root: Path = ROOT, separator=None, runtime_resolver=None) -> tuple[dict, Path | None]:
    """Returns (document, output_dir). Refusals write nothing."""
    try:
        req = validate_request(request)                               # orders 1-2
        try:
            model = resolve_model(root)                               # orders 3-8
        except OSError as exc:
            raise Refused('model_file_missing', f'Model file unreadable: {type(exc).__name__}')
        runtime = (runtime_resolver or default_runtime_resolver)(root)  # order 9
        try:
            inp = resolve_input(root, req)                            # order 10
        except (OSError, ValueError) as exc:
            raise Refused('input_not_admitted', f'Input unreadable: {type(exc).__name__}: {exc}')
    except Refused as exc:
        return refusal(exc.code, str(exc), exc.runtime_reason), None
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(4)
    try:
        workdir = lane_dir(root, ESTIMATES_REL, stamp)
    except (Refused, OSError) as exc:
        return failure('output_path_rejected', str(exc)), None
    try:
        doc = _estimate(root, req, model, runtime, inp, workdir, separator)
    except Failed as exc:
        doc = failure(exc.code, str(exc))
    except Exception as exc:  # noqa: BLE001 - unexpected faults are failures, never refusals
        doc = failure('internal_error', f'{type(exc).__name__}: {exc}')
    (workdir / ('stems_estimate.json' if doc['status'] == 'completed' else 'failure.json')).write_text(
        json.dumps(doc, indent=2, allow_nan=False) + '\n')
    return doc, workdir


def estimate(request, root: Path = ROOT, separator=None, runtime_resolver=None) -> dict:
    return run_estimate(request, root, separator, runtime_resolver)[0]


def _estimate(root: Path, req: dict, model: dict, runtime: dict, inp: dict, workdir: Path, separator) -> dict:
    rate, start_frame, frame_count = inp['rate'], inp['start_frame'], inp['frame_count']
    (excerpt,), _ = read_wav(inp['path'], start_frame, frame_count)
    scratch = workdir / 'scratch'
    scratch.mkdir(mode=0o700)
    applied = rate != MODEL_RATE
    model_mono = ffmpeg_resample(excerpt, rate, FORWARD_FILTER, scratch, 'forward') if applied else excerpt
    stereo = [model_mono, model_mono]                                   # mono_duplicated_to_stereo
    analysed_sha = write_wav_float(workdir / 'model_input.wav', stereo, MODEL_RATE)
    if separator is None:
        if runtime.get('kind') != 'isolated_child':
            raise Failed('separator_unavailable', 'No separator for a non-isolated runtime')
        separator = ChildSeparator(root, runtime)
    began = time.monotonic()
    try:
        raw = separator(stereo, model, workdir)
    except Failed:
        raise
    except Exception as exc:  # noqa: BLE001 - separator faults are failures, never refusals
        raise Failed('inference_failed', f'{type(exc).__name__}: {exc}')
    elapsed = time.monotonic() - began
    stems_44k = validate_separator_output(raw, len(model_mono))
    if sha256_file(inp['path']) != inp['input_sha256'] or sha256_file(Path(model['path'])) != model['sha256']:
        raise Failed('input_or_model_changed', 'Input or checkpoint changed during inference')
    stems_mono, adjust = {}, 0
    for name in SOURCES:
        back = ffmpeg_resample(stems_44k[name], MODEL_RATE, return_filter(rate), scratch, f'return-{name}') if applied else stems_44k[name]
        fitted, delta = fit_length(back, frame_count)
        if abs(delta) > abs(adjust):
            adjust = delta
        if abs(delta) > 2:
            raise Failed('round_trip_length_mismatch', f'{name} returned {len(back)} frames for {frame_count}')
        stems_mono[name] = fitted
    shutil.rmtree(scratch)
    stems_dir = workdir / 'stems'
    stems_dir.mkdir(mode=0o700)
    origin = inp['origin']
    first_s, last_s = origin + start_frame / rate, origin + (start_frame + frame_count) / rate
    stems = []
    for name in SOURCES:
        digest = write_wav_float(stems_dir / f'{name}.wav', [stems_mono[name]], rate)
        stems.append({'name': name, 'model_target_label': f'htdemucs_6s:{name}', 'path': f'stems/{name}.wav',
                      'sha256': digest, 'rate': rate, 'channels': 1, 'frames': frame_count,
                      'source_start_seconds': first_s, 'source_end_seconds': last_s, 'estimate': True})
    measure_began = time.monotonic()
    low_end, mixture = low_end_measurements(excerpt, stems_mono, rate, frame_count / rate)
    measurement = time.monotonic() - measure_began
    receipt = getattr(separator, 'last_receipt', None) or {}
    fake = runtime.get('kind') != 'isolated_child'
    doc = {
        'schema_version': 1, 'status': 'completed', 'tool': TOOL,
        'model_identity': {'model_id': model['model_id'], 'sha256': model['sha256'], 'registry_sha256': model['registry_sha256'],
                           'source_url': model['source_url'], 'license_verdict': model['license_verdict'],
                           'terms_acknowledgement': model['terms_acknowledgement'],
                           'checkpoint_load': receipt.get('checkpoint_load') or ('not_loaded_injected_fake' if fake else None)},
        'runtime_identity': {'kind': 'injected_fake' if fake else 'isolated_child', 'python': receipt.get('python') or runtime.get('python'),
                             'torch': receipt.get('torch', runtime.get('torch')), 'demucs': receipt.get('demucs', runtime.get('demucs')),
                             'platform': runtime.get('platform') or f'{platform.system().lower()}-{platform.machine()}',
                             'host_label': platform.node().split('.')[0] or None, 'threads': THREADS, 'seed': SEED,
                             'apply_settings': dict(APPLY_SETTINGS)},
        'input_identity': {'input_role': inp['input_role'], 'path_role': inp['path_role'], 'input_sha256': inp['input_sha256'],
                           'run_manifest_sha256': inp['run_manifest_sha256'], 'source_sha256': inp['source_sha256'],
                           'signal_version': f"sha256:{inp['input_sha256']}", 'source_rate': rate, 'source_channels': 1,
                           'real_take': inp['real_take']},
        'excerpt': {'source_timeline_origin_seconds': origin, 'source_start_seconds': first_s, 'source_end_seconds': last_s,
                    'start_frame': start_frame, 'frame_count': frame_count, 'rate': rate},
        'analysed_input': {'sha256': analysed_sha, 'rate': MODEL_RATE, 'channels': MODEL_CHANNELS, 'frames': len(model_mono),
                           'sample_rate_conversion': {'input_rate': rate, 'model_rate': MODEL_RATE, 'applied': applied,
                                                      'forward_filter': FORWARD_FILTER if applied else None,
                                                      'return_filter': return_filter(rate) if applied else None,
                                                      'length_adjust_frames': adjust},
                           'channel_conversion': {'to_model': 'mono_duplicated_to_stereo', 'from_model': 'stereo_mean_to_mono'}},
        'stems': stems,
        'low_end_check': low_end,
        'mixture_consistency': mixture,
        'resource_receipt': {'elapsed_seconds': receipt.get('elapsed_seconds', elapsed), 'deadline_seconds': LIMITS['deadline_seconds'],
                             'rss_ceiling_bytes': LIMITS['rss_bytes'], 'max_rss_bytes': receipt.get('max_rss_bytes'),
                             'measurement_seconds': measurement},
        'privacy': 'V6_private_real_take_derived' if inp['real_take'] else 'generated_fixture',
        'limitations': list(LIMITATIONS),
    }
    doc.update(UNKNOWN_FIELDS)
    if set(doc) != RESULT_KEYS:
        raise Failed('result_schema_violation', 'result key set differs from contract section 7')
    return doc


# --------------------------------------------------------------------------- fixture generator (suite s3-stems-1)

FIXTURE_RATE = MODEL_RATE
FIXTURE_SECONDS = 10.0
COHORTS = ('k1-c1-chug', 'k2-low-sustain', 'k3-high-legato', 'k4-negative')
DEV_SEED = 4001
HELDOUT_SEEDS = (4103, 4211)
EXCLUDED_SEEDS = (211, 307, 617, 719, 1009, 1301, 1423, 1511, 1613, 3001, 3101, 3203)
MIDI = {'C1': 24, 'F1': 29, 'Bb1': 34, 'Ab3': 56, 'C4': 60, 'F4': 65}
LEGATO_RUN = (56, 58, 60, 61, 63, 65, 63, 61, 60, 58)  # Ab3..F4, deterministic (seeds drive only fan and jitter)
TABLE = 2048
GENERATOR_ID = 'stems_estimate.generate_fixture'
SUITE_NAME = re.compile(r'[a-z0-9][a-z0-9-]{0,62}')


def midi_hz(note: int) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)  # theoretical A4=440 equal temperament, not measured


def _cycle(frequency: float, palm: bool, rate: int) -> list[float]:
    cut = 10 ** (-12 / 20)
    partials = [(k, (1 / k) * (cut if palm and k > 8 else 1.0)) for k in range(1, 13) if frequency * k < rate * .45]
    cycle = [sum(a * math.sin(2 * math.pi * k * i / TABLE) for k, a in partials) for i in range(TABLE)]
    peak = max(abs(v) for v in cycle) or 1.0
    return [v / peak for v in cycle]


def _render(buffer: list[float], start: float, length: float, frequency: float, gain_db: float, palm: bool,
            attack: float, tau: float, rate: int, cache: dict) -> None:
    key = (round(frequency, 6), palm)
    if key not in cache:
        cache[key] = _cycle(frequency, palm, rate)
    cycle = cache[key]
    begin = int(round(start * rate))
    count = min(int(length * rate), len(buffer) - begin)
    if begin < 0 or count <= 0:
        return
    step = frequency * TABLE / rate
    attack_n, release_n = max(1, int(attack * rate)), int(.003 * rate)
    decay = math.exp(-1 / (tau * rate))
    drive, tanh = 4.0, math.tanh
    scale = 10 ** (gain_db / 20) / math.tanh(drive)
    env, phase, tail = 1.0, 0.0, count - release_n
    for n in range(count):
        shape = env
        if n < attack_n:
            shape *= n / attack_n
        if n > tail:
            shape *= (count - n) / release_n
        buffer[begin + n] += scale * tanh(drive * shape * cycle[int(phase) % TABLE])
        phase += step
        env *= decay


def _fan(rng: random.Random, count: int, rate: int) -> list[float]:
    a = math.exp(-2 * math.pi * 400 / rate)
    y, out = 0.0, []
    for _ in range(count):
        y = a * y + (1 - a) * (rng.random() - .5)
        out.append(y)
    rms = math.sqrt(math.fsum(v * v for v in out) / count) or 1.0
    target = 10 ** (-42 / 20)
    return [v * target / rms for v in out]


def _clicks(count: int, times: list[float], rate: int) -> list[float]:
    out = [0.0] * count
    width, peak = int(.001 * rate), 10 ** (-18 / 20)
    for at in times:
        begin = int(round(at * rate))
        for n in range(width):
            if 0 <= begin + n < count:
                window = .5 - .5 * math.cos(2 * math.pi * n / (width - 1))
                out[begin + n] += peak * window * math.sin(2 * math.pi * 3000 * n / rate)
    return out


def _grid(t0: float, period: float, end: float) -> list[float]:
    out, k = [], 0
    while t0 + k * period < end:
        out.append(t0 + k * period)
        k += 1
    return out


def generate_fixture(cohort: str, seed: int, duration: float = FIXTURE_SECONDS) -> dict:
    """Deterministic stdlib fixture at 44.1 kHz: components rendered separately and summed into the mixture."""
    if cohort not in COHORTS:
        raise ValueError(f'unknown cohort {cohort}')
    rate = FIXTURE_RATE
    rng = random.Random(seed)
    count = int(round(duration * rate))
    end = duration - .05
    t0 = .25
    jitter = lambda: max(-.005, min(.005, rng.gauss(0, .002)))  # noqa: E731
    voices: list[list[tuple]] = []  # each voice: (start, frequency, gain_db, palm, attack, tau)
    if cohort == 'k1-c1-chug':
        bpm = 178
        sixteenth = 60 / bpm / 4
        voices.append([(t + jitter(), midi_hz(MIDI['C1'] if t < t0 + 4.0 else MIDI['F1']), 0.0, True, .002, .06)
                       for t in _grid(t0, sixteenth, end)])
    elif cohort == 'k2-low-sustain':
        bpm = 120
        notes = (MIDI['C1'], MIDI['F1'], MIDI['Bb1'])
        voices.append([(t + jitter(), midi_hz(notes[i % 3]), 0.0, False, .002, .4) for i, t in enumerate(_grid(t0, 1.5, end))])
    elif cohort == 'k3-high-legato':
        bpm = 160
        beat = 60 / bpm
        voices.append([(t + jitter(), midi_hz(MIDI['C1']), 0.0, False, .002, .4) for t in _grid(t0, 2 * beat, end)])
        voices.append([(t + jitter(), midi_hz(LEGATO_RUN[i % len(LEGATO_RUN)]), -8.0, False, .03, .4)
                       for i, t in enumerate(_grid(t0, beat / 4, end))])
    else:
        bpm = 178
    guitar = [0.0] * count
    cache: dict = {}
    for voice in voices:
        voice.sort()
        for i, (start, frequency, gain_db, palm, attack, tau) in enumerate(voice):
            nxt = voice[i + 1][0] if i + 1 < len(voice) else duration
            _render(guitar, max(0.0, start), max(.005, nxt - start), frequency, gain_db, palm, attack, tau, rate, cache)
    peak = max((abs(v) for v in guitar), default=0.0)
    if peak > 0:
        scale = 10 ** (-6 / 20) / peak
        guitar = [v * scale for v in guitar]
    fan = _fan(rng, count, rate)
    click_times = _grid(t0, 60 / bpm, end)
    click = _clicks(count, click_times, rate)
    mixture = [g + f + k for g, f, k in zip(guitar, fan, click)]
    truth = {'schema_version': 1, 'cohort': cohort, 'seed': seed, 'duration_seconds': duration, 'rate': rate,
             'click_bpm': bpm, 'click_times': click_times, 'note_onsets': sorted(n[0] for v in voices for n in v),
             'guitar_is_digital_silence': peak == 0, 'truth_kind': 'constructed_generator_truth',
             'tuning': 'program/instrument.json theoretical A4=440 (C1 32.70 Hz .. F4)',
             'components': ['guitar', 'fan', 'click'], 'mixture': 'guitar + fan + click (float32)'}
    return {'mixture': mixture, 'guitar': guitar, 'fan': fan, 'click': click, 'truth': truth, 'rate': rate}


def default_a1_runnable(root: Path) -> None:
    resolve_model(root)
    default_runtime_resolver(root)


def generate_suite(root: Path, name: str, role: str, seeds: list[int], duration: float = FIXTURE_SECONDS,
                   cohorts: tuple[str, ...] = COHORTS, a1_runnable=None) -> Path:
    if role not in ('dev', 'heldout') or not SUITE_NAME.fullmatch(name):
        raise ValueError('role must be dev or heldout and name a simple slug')
    if any(s in EXCLUDED_SEEDS for s in seeds):
        raise ValueError('seed already consumed elsewhere')
    if role == 'dev' and list(seeds) != [DEV_SEED]:
        raise ValueError('dev seed is sealed as 4001')
    if role == 'heldout':
        if sorted(seeds) != sorted(HELDOUT_SEEDS):
            raise ValueError('held-out seeds are sealed as 4103 and 4211')
        (a1_runnable or default_a1_runnable)(root)  # Refused => blocked_with_receipt; nothing generated
    if not set(cohorts) <= set(COHORTS):
        raise ValueError('unknown cohort')
    suite = lane_dir(root, FIXTURES_REL, name)
    for sub in ('cases', 'truth'):
        (suite / sub).mkdir(mode=0o700)
    cases = {}
    for seed in seeds:
        for cohort in cohorts:
            case = f'{cohort}-s{seed}'
            fixture = generate_fixture(cohort, seed, duration)
            case_dir = suite / 'cases' / case
            case_dir.mkdir(mode=0o700)
            mix = wav_float_bytes([fixture['mixture']], fixture['rate'])
            mix_sha = sha256_bytes(mix)
            for wav in ('denoised.wav', 'source.wav'):
                (case_dir / wav).write_bytes(mix)
            manifest = {'schema_version': 1, 'source': {'kind': 'generated_fixture', 'generator': GENERATOR_ID, 'seed': seed,
                                                        'cohort': cohort, 'suite': name, 'sha256': mix_sha},
                        'output_sha256': {'denoised.wav': mix_sha, 'source.wav': mix_sha},
                        'timeline': {'audio_start_seconds': 0.0, 'no_time_stretch': True},
                        'pcm': {'rate': fixture['rate'], 'channels': 1, 'format': 'pcm_f32le', 'duration_seconds': duration}}
            (case_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
            truth_dir = suite / 'truth' / case
            truth_dir.mkdir(mode=0o700)
            truth_files = {}
            for component in ('guitar', 'fan', 'click'):
                data = wav_float_bytes([fixture[component]], fixture['rate'])
                path = truth_dir / f'{component}.wav'
                path.write_bytes(data)
                path.chmod(0o400)
                truth_files[f'truth/{case}/{component}.wav'] = sha256_bytes(data)
            truth_bytes = (json.dumps(fixture['truth'], indent=2) + '\n').encode()
            truth_json = suite / 'truth' / f'{case}.json'
            truth_json.write_bytes(truth_bytes)
            truth_json.chmod(0o400)
            truth_files[f'truth/{case}.json'] = sha256_bytes(truth_bytes)
            cases[case] = {'cohort': cohort, 'seed': seed, 'case_dir': f'cases/{case}', 'mixture_sha256': mix_sha,
                           'manifest_sha256': sha256_file(case_dir / 'manifest.json'), 'truth_files': truth_files,
                           'duration_seconds': duration, 'guitar_case': cohort != 'k4-negative'}
    manifest = {'schema_version': 1, 'suite': name, 'role': role, 'seeds': list(seeds), 'sample_rate': FIXTURE_RATE,
                'format': 'pcm_f32le mono', 'generator': {'id': GENERATOR_ID, 'script_sha256': sha256_file(Path(__file__))},
                'preregistration': 'docs/spec/sprints/STEMS_S3.md section 8 (commit e900b997)',
                'cohorts': list(cohorts), 'complete_preregistered_suite': tuple(cohorts) == COHORTS and duration == FIXTURE_SECONDS,
                'recorded_utc': utc_now(), 'cases': cases}
    (suite / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return suite


# --------------------------------------------------------------------------- experiment harness (seal before truth)

ARMS = ('A0', 'A1')


def _suite(root: Path, suite_dir) -> tuple[Path, dict]:
    suite = contained(suite_dir, root, (FIXTURES_REL,))
    manifest = strict_loads(read_bounded(suite / 'manifest.json', LIMITS['manifest_bytes']))
    return suite, manifest


def predict(root: Path, suite_dir, arm: str, a1=None) -> list[Path]:
    """Writes predictions/<arm>/<case>/. Never opens truth/."""
    suite, manifest = _suite(root, suite_dir)
    if arm not in ARMS:
        raise ValueError('arm must be A0 or A1')
    if (suite / 'seal.json').exists():
        raise ValueError('Suite already sealed; predictions are immutable')
    written = []
    for case, info in sorted(manifest['cases'].items()):
        case_dir = suite / info['case_dir']
        mixture = case_dir / 'denoised.wav'
        if sha256_file(mixture) != info['mixture_sha256']:
            raise ValueError('Case audio changed: ' + case)
        out = suite / 'predictions' / arm / case
        out.mkdir(parents=True, exist_ok=False)
        record = {'schema_version': 1, 'arm': arm, 'case': case, 'input_sha256': info['mixture_sha256'], 'recorded_utc': utc_now()}
        if arm == 'A0':
            shutil.copyfile(mixture, out / 'guitar.wav')
            record.update(estimate='mixture_passthrough', files={'guitar.wav': sha256_file(out / 'guitar.wav')})
        else:
            request = {'run_dir': str(case_dir.relative_to(root)), 'input_role': 'denoised',
                       'excerpt_start_seconds': 0.0, 'excerpt_end_seconds': info['duration_seconds']}
            doc, workdir = (a1 or (lambda req: run_estimate(req, root)))(request)
            if doc.get('status') != 'completed':
                record.update(estimate=None, refusal=doc)
            else:
                files = {}
                for name in ('guitar', 'bass'):
                    shutil.copyfile(workdir / 'stems' / f'{name}.wav', out / f'{name}.wav')
                    files[f'{name}.wav'] = sha256_file(out / f'{name}.wav')
                record.update(estimate='htdemucs_6s_guitar', secondary='htdemucs_6s_guitar_plus_bass', files=files,
                              model_identity=doc['model_identity'], runtime_identity=doc['runtime_identity'],
                              low_end_check_guitar_vs_input_band_db=doc['low_end_check']['guitar_vs_input_band_db'])
        path = out / 'record.json'
        path.write_text(json.dumps(record, indent=2, allow_nan=False) + '\n')
        written.append(path)
    return written


def seal(root: Path, suite_dir, arms: tuple[str, ...] = ARMS) -> Path:
    suite, manifest = _suite(root, suite_dir)
    files = {}
    for arm in arms:
        for case in sorted(manifest['cases']):
            folder = suite / 'predictions' / arm / case
            if not (folder / 'record.json').is_file():
                raise ValueError(f'Missing prediction {arm}/{case}; the seal covers every case of every arm')
            for path in sorted(folder.iterdir()):
                files[str(path.relative_to(suite))] = sha256_file(path)
    target = suite / 'seal.json'
    if target.exists():
        raise ValueError('Seal already exists')
    target.write_text(json.dumps({'schema_version': 1, 'sealed_utc': utc_now(), 'sealed_epoch': time.time(),
                                  'arms': list(arms), 'files': files}, indent=2) + '\n')
    target.chmod(0o400)
    return target


def _metric(value: float | None, undefined_reason: str | None = None) -> dict:
    if value is None:
        return {'value': None, 'reason': undefined_reason}
    if value == float('-inf'):
        return {'value': None, 'reason': 'minus_infinity_zero_numerator_energy'}
    if value == float('inf'):
        return {'value': None, 'reason': 'plus_infinity_zero_error_energy'}
    return {'value': value, 'reason': None}


def _db(num: float, den: float) -> float | None:
    if den <= 0:
        return None
    if num <= 0:
        return float('-inf')
    return 10 * math.log10(num / den)


def _dot(a, b, skip: int = 0) -> float:
    return math.fsum(x * y for x, y in zip(a[skip:], b[skip:]))


def si_sdr(estimate_signal, target) -> float | None:
    gg = _dot(target, target)
    if gg <= 0:
        return None
    alpha = _dot(estimate_signal, target) / gg
    t_energy = alpha * alpha * gg
    noise = math.fsum((e - alpha * g) ** 2 for e, g in zip(estimate_signal, target))
    if noise <= 0:
        return float('inf')
    return _db(t_energy, noise) if t_energy > 0 else float('-inf')


def projection_coefficients(e, basis: list, skip: int = 0) -> list[float] | None:
    """Least squares e ~ sum c_i basis_i via normal equations (Gaussian elimination with partial pivoting)."""
    n = len(basis)
    gram = [[_dot(basis[i], basis[j], skip) for j in range(n)] + [_dot(basis[i], e, skip)] for i in range(n)]
    scale = max(gram[i][i] for i in range(n))
    if scale <= 0:
        return None
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(gram[r][col]))
        if abs(gram[pivot][col]) <= 1e-12 * scale:
            return None
        gram[col], gram[pivot] = gram[pivot], gram[col]
        for r in range(n):
            if r != col:
                f = gram[r][col] / gram[col][col]
                gram[r] = [x - f * y for x, y in zip(gram[r], gram[col])]
    return [gram[i][n] / gram[i][i] for i in range(n)]


def score_case(cohort: str, rate: int, mixture, guitar, fan, click, estimates: dict) -> dict:
    """Contract 8.4 per case. `estimates` maps readout -> signal (A0, A1, A1-gb); missing readouts are skipped."""
    duration = len(mixture) / rate
    skip = min(len(mixture), round(min(0.25, 0.25 * duration) * rate))
    band = lambda x: bandpass(x, rate, *BAND_HZ)  # noqa: E731
    out = {'cohort': cohort, 'band_settle_excluded_seconds': skip / rate, 'readouts': {}}
    if cohort != 'k4-negative':
        g_b, f_b, k_b = band(guitar), band(fan), band(click)
        e_f, e_fb = mean_square(fan), mean_square(f_b, skip)
    else:
        m_b = band(mixture)
    for readout, e in estimates.items():
        if e is None:
            continue
        if len(e) != len(mixture):
            raise ValueError(f'{readout} estimate length differs from the case')
        e_b = band(e)
        if cohort != 'k4-negative':
            eg, gg, ee = _dot(e_b, g_b, skip), _dot(g_b, g_b, skip), _dot(e_b, e_b, skip)
            rho = eg / math.sqrt(gg * ee) if gg > 0 and ee > 0 else None
            full = projection_coefficients(e, [guitar, fan, click])
            low = projection_coefficients(e_b, [g_b, f_b, k_b], skip)
            out['readouts'][readout] = {
                'S1_low_band_retention_db': _metric(_db(mean_square(e_b, skip), mean_square(g_b, skip)), 'zero_truth_band_energy'),
                'S1_band_correlation': _metric(rho, 'zero_band_energy'),
                'S2_si_sdr_db': _metric(si_sdr(e, guitar), 'zero_truth_energy'),
                'S3_fan_leakage_full_db': _metric(None if full is None else _db(full[1] ** 2 * e_f, e_f), 'singular_projection'),
                'S3_fan_leakage_band_db': _metric(None if low is None else _db(low[1] ** 2 * e_fb, e_fb), 'singular_projection'),
            }
        else:
            out['readouts'][readout] = {
                'S4_false_allocation_full_db': _metric(_db(mean_square(e), mean_square(mixture)), 'zero_mixture_energy'),
                'S4_false_allocation_band_db': _metric(_db(mean_square(e_b, skip), mean_square(m_b, skip)), 'zero_mixture_band_energy'),
            }
    return out


def _raw(entry: dict):
    """Back to a float for medians: reason-coded infinities return as infinities, undefined as None."""
    if entry['value'] is not None:
        return entry['value']
    return {'minus_infinity_zero_numerator_energy': float('-inf'), 'plus_infinity_zero_error_energy': float('inf')}.get(entry['reason'])


def aggregate(per_case: dict) -> dict:
    """Medians over guitar cases (S1-S3) and negative cases (S4); every case listed; rates never averaged."""
    summary = {}
    for case, row in sorted(per_case.items()):
        for readout, metrics in row['readouts'].items():
            for metric, entry in metrics.items():
                bucket = summary.setdefault(readout, {}).setdefault(metric, {'per_case': {}, 'median': None})
                bucket['per_case'][case] = entry
    for readout, metrics in summary.items():
        for metric, bucket in metrics.items():
            values = [_raw(e) for e in bucket['per_case'].values()]
            defined = [v for v in values if v is not None]
            bucket['n_cases'] = len(values)
            bucket['n_defined'] = len(defined)
            if defined:
                median = statistics.median(defined)
                bucket['median'] = _metric(median)
            else:
                bucket['median'] = _metric(None, 'no_defined_case_value')
    return summary


def decide(summary: dict) -> dict:
    def med(readout, metric):
        bucket = summary.get(readout, {}).get(metric)
        return None if bucket is None else _raw(bucket['median'])
    s2_a1, s2_a0 = med('A1', 'S2_si_sdr_db'), med('A0', 'S2_si_sdr_db')
    s1_a1, s1_gb = med('A1', 'S1_low_band_retention_db'), med('A1-gb', 'S1_low_band_retention_db')
    s4_a1 = med('A1', 'S4_false_allocation_full_db')
    inputs = (s2_a1, s2_a0, s1_a1, s4_a1)
    separates = None not in inputs and s2_a1 >= s2_a0 + 3 and s1_a1 >= -3 and s4_a1 <= -10
    return {'rule': 'median S2(A1) >= median S2(A0) + 3 dB AND median S1(A1) >= -3 dB AND median full-band S4(A1) <= -10 dB',
            'outcome': ('A1 separates without low-band loss on generated fixtures' if separates
                        else 'no separation benefit shown on generated fixtures'),
            'inputs_defined': None not in inputs,
            'low_band_loss_observed': None if s1_a1 is None else s1_a1 < -3,
            'low_band_loss_observed_A1_gb': None if s1_gb is None else s1_gb < -3,
            'descriptive_only': True, 'default_adoption': False, 'real_take_claim': None}


def score(root: Path, suite_dir) -> dict:
    """Contract 8.3-8.4. Refuses unless a matching seal predates scorer start; dev suites are never scored."""
    started = time.time()
    suite, manifest = _suite(root, suite_dir)
    seal_path = suite / 'seal.json'
    if not seal_path.is_file():
        raise ValueError('Scorer refuses: seal.json missing')
    sealed = strict_loads(seal_path.read_bytes())
    if sealed['sealed_epoch'] >= started:
        raise ValueError('Scorer refuses: seal does not precede scorer start')
    present = {str(p.relative_to(suite)) for p in (suite / 'predictions').rglob('*') if p.is_file()}
    if present != set(sealed['files']):
        raise ValueError('Scorer refuses: prediction files differ from the sealed set')
    for relative, digest in sealed['files'].items():
        if sha256_file(suite / relative) != digest:
            raise ValueError('Scorer refuses: sealed prediction changed: ' + relative)
    if manifest.get('role') != 'heldout':
        raise ValueError('Scorer refuses: dev suites are never scored')
    per_case, a1_refusals = {}, {}
    for case, info in sorted(manifest['cases'].items()):
        for relative, digest in info['truth_files'].items():
            if sha256_file(suite / relative) != digest:
                raise ValueError('Truth file changed: ' + relative)
        load = lambda p: read_wav(p)[0][0]  # noqa: E731
        mixture = load(suite / info['case_dir'] / 'denoised.wav')
        g, f, k = (load(suite / 'truth' / case / f'{c}.wav') for c in ('guitar', 'fan', 'click'))
        estimates = {'A0': load(suite / 'predictions' / 'A0' / case / 'guitar.wav')} if 'A0' in sealed['arms'] else {}
        if 'A1' in sealed['arms']:
            folder = suite / 'predictions' / 'A1' / case
            if (folder / 'guitar.wav').is_file():
                guitar_e, bass_e = load(folder / 'guitar.wav'), load(folder / 'bass.wav')
                estimates['A1'] = guitar_e
                estimates['A1-gb'] = array.array('d', (a + b for a, b in zip(guitar_e, bass_e)))
            else:
                a1_refusals[case] = strict_loads((folder / 'record.json').read_bytes()).get('refusal')
        per_case[case] = score_case(info['cohort'], manifest['sample_rate'], mixture, g, f, k, estimates)
    summary = aggregate(per_case)
    result = {'schema_version': 1, 'suite': manifest['suite'], 'scored_utc': utc_now(), 'seal_sha256': sha256_file(seal_path),
              'complete_preregistered_suite': manifest.get('complete_preregistered_suite'), 'per_case': per_case,
              'summary': summary, 'a1_refusals': a1_refusals, 'decision': decide(summary),
              'claim_class': 'measurement_on_generated_fixtures', 'separation_accuracy_real_take': 'unknown',
              'default_adoption': False}
    (suite / 'scores.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return result


# --------------------------------------------------------------------------- CLI

def read_request(args) -> object:
    if args.request_json is not None:
        if len(args.request_json.encode()) > LIMITS['request_bytes']:
            raise ValueError('request exceeds 64 KiB')
        return strict_loads(args.request_json)
    if args.request == '-':
        data = sys.stdin.buffer.read(LIMITS['request_bytes'] + 1)
        if len(data) > LIMITS['request_bytes']:
            raise ValueError('request exceeds 64 KiB')
        return strict_loads(data)
    return strict_loads(read_bounded(Path(args.request), LIMITS['request_bytes']))


def summary_of(doc: dict, workdir: Path | None, root: Path = ROOT) -> dict:
    if doc['status'] != 'completed':
        return doc
    low = doc['low_end_check']
    return {'schema_version': 1, 'status': 'completed', 'tool': TOOL,
            'output_dir': str(workdir.relative_to(root)) if workdir and workdir.is_relative_to(root) else str(workdir),
            'result': 'stems_estimate.json', 'stems': [s['path'] for s in doc['stems']],
            'excerpt': doc['excerpt'], 'guitar_vs_input_band_db': low['guitar_vs_input_band_db'],
            'guitar_plus_bass_vs_input_band_db': low['guitar_plus_bass_vs_input_band_db'], 'low_end_status': low['status'],
            'privacy': doc['privacy'], 'estimate_from_mono_mixture': True, 'recovered_original_stem': False,
            'default_adoption': False, 'listening_accepted': False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Experimental htdemucs_6s stem estimates (never recovered stems)')
    sub = parser.add_subparsers(dest='command')
    e = sub.add_parser('estimate', help='closed-schema request (JSON) -> stems_estimate.json or a typed refusal')
    group = e.add_mutually_exclusive_group(required=True)
    group.add_argument('--request', help='request JSON file, or - for stdin')
    group.add_argument('--request-json', help='request JSON text (tool_api dispatch)')
    i = sub.add_parser('infer', help=argparse.SUPPRESS)
    i.add_argument('--task', type=Path, required=True)
    g = sub.add_parser('generate-suite')
    g.add_argument('--name', required=True)
    g.add_argument('--role', choices=('dev', 'heldout'), required=True)
    g.add_argument('--seeds', type=int, nargs='+', required=True)
    p = sub.add_parser('predict')
    p.add_argument('--suite-dir', required=True)
    p.add_argument('--arm', choices=ARMS, required=True)
    s = sub.add_parser('seal')
    s.add_argument('--suite-dir', required=True)
    r = sub.add_parser('score')
    r.add_argument('--suite-dir', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'infer':
            return infer_task(args.task)
        if args.command == 'estimate':
            try:
                request = read_request(args)
            except (OSError, ValueError) as exc:
                print(json.dumps(refusal('request_invalid', f'Unreadable request: {exc}')))
                return 2
            doc, workdir = run_estimate(request, ROOT)
            print(json.dumps(summary_of(doc, workdir), allow_nan=False))
            return {'completed': 0, 'refused': 2}.get(doc['status'], 1)
        if args.command == 'generate-suite':
            print(json.dumps({'suite_dir': str(generate_suite(ROOT, args.name, args.role, args.seeds))}))
        elif args.command == 'predict':
            print(json.dumps({'written': [str(x) for x in predict(ROOT, args.suite_dir, args.arm)]}))
        elif args.command == 'seal':
            print(json.dumps({'seal': str(seal(ROOT, args.suite_dir))}))
        elif args.command == 'score':
            print(json.dumps(score(ROOT, args.suite_dir)['decision']))
        else:
            parser.print_help()
            return 1
        return 0
    except Refused as exc:
        print(json.dumps(refusal(exc.code, str(exc), exc.runtime_reason)))
        return 2
    except Exception as exc:  # noqa: BLE001 - never raises past main
        print(json.dumps(failure('internal_error', f'{type(exc).__name__}: {exc}')))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
