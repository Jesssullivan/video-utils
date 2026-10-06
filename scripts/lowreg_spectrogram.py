#!/usr/bin/env python3
"""Low-register spectrogram v1 (xoruby V4) deterministic reference implementation.

Experimental research helper, not an advertised tool. It renders a frozen
log-spaced 20-2000 Hz power spectrogram (log-power dB and experimental PCEN) at
8000 Hz with a 4096-sample (512 ms) periodic Hann window and a 160-sample hop.
It restores no audio, separates no stem, identifies no note and makes no pitch
resolution claim. The short-window attack branch (log-mel rhythm frontend)
stays separate and remains the source of onset/timing evidence.

Stdlib-first: the default backend reuses ``scripts/guitar_features.fft``. The
optional ``numpy`` backend uses ``numpy.fft.rfft`` with the same formulas and
must match the golden within tolerance. Normative prose:
``docs/spec/LOW_REGISTER_SPECTROGRAM_SPEC.md``; machine spec:
``program/spectrogram-lowreg-v1.json``; contract:
``docs/spec/sprints/LOWREG_SPEC_S2.md``.
"""
from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'scripts') not in sys.path:
    sys.path.insert(0, str(ROOT / 'scripts'))
from guitar_features import fft as _radix2_fft  # noqa: E402  (stdlib radix-2 FFT, reused)

SPEC_PATH = ROOT / 'program' / 'spectrogram-lowreg-v1.json'
GOLDEN_PATH = ROOT / 'tests' / 'fixtures' / 'lowreg-golden-v1.json'
SPEC_VERSION = 'lowreg-spectrogram-v1'
GOLDEN_SCHEMA = 'lowreg-golden-v1'
RENDER_SCHEMA = 'lowreg-render-v1'

RATE = 8000
N_FFT = 4096
HOP = 160
N_FFT_BINS = N_FFT // 2 + 1
BIN_HZ = RATE / N_FFT  # 1.953125, exact
WINDOW_SUM = 2048.0  # analytic sum of the periodic Hann of length 4096
FMIN = 20.0
FMAX = 2000.0
BINS_PER_OCTAVE = 24
N_BANDS = int(math.floor(BINS_PER_OCTAVE * math.log2(FMAX / FMIN))) + 1  # 160
LOG_FLOOR = 1e-10
PCEN_SCALE = 2.0 ** 31
PCEN_GAIN = 0.98
PCEN_BIAS = 2.0
PCEN_POWER = 0.5
PCEN_TIME_CONSTANT = 0.4
PCEN_EPS = 1e-6
PCEN_T_FRAMES = PCEN_TIME_CONSTANT * RATE / HOP  # 20.0
PCEN_B = (math.sqrt(1 + 4 * PCEN_T_FRAMES ** 2) - 1) / (2 * PCEN_T_FRAMES ** 2)
INTERPOLATED_BELOW_LEFT_HZ = BIN_HZ / (1 - 2 ** (-1 / BINS_PER_OCTAVE))
INTERPOLATED_BELOW_RIGHT_HZ = BIN_HZ / (2 ** (1 / BINS_PER_OCTAVE) - 1)
TOLERANCE = {'abs': 1e-9, 'rel': 1e-9}
GOLDEN_MAX_BYTES = 50_000
GOLDEN_FRAMES = (0, 17, 94)
GOLDEN_BINS = (0, 17, 28, 41, 150)
MATRICES = ('log_power_db', 'pcen')

# Every key here is normative; the machine spec must carry exactly these values.
PARAMETERS = {
    'arithmetic': 'ieee754_float64',
    'analysis_rate_hz': RATE,
    'channels_policy': 'arithmetic_mean_of_channels_float64',
    'input_decode': 'pcm16_wav_int16_divided_by_32768.0',
    'preprocessing': 'none: no DC removal, pre-emphasis, high-pass, notch or dither',
    'other_rates': 'refused_exit_2; explicit external resample is a recorded caller pre-stage',
    'window': 'periodic_hann: w[n] = 0.5 - 0.5*cos(2*pi*n/4096)',
    'window_length': N_FFT,
    'window_sum': WINDOW_SUM,
    'n_fft': N_FFT,
    'n_fft_bins': N_FFT_BINS,
    'fft_bin_spacing_hz': BIN_HZ,
    'hop_samples': HOP,
    'hop_seconds': HOP / RATE,
    'temporal_support_seconds': N_FFT / RATE,
    'centre_padding': False,
    'frame_rule': 'frame t uses samples [160t, 160t+4096); n_frames = 1 + floor((N-4096)/160); N < 4096 refused',
    'frame_centre_formula': '(160t + 2048)/8000 seconds from the first analysed sample',
    'first_frame_centre_seconds': (N_FFT / 2) / RATE,
    'spectrum_policy': 'power',
    'power_formula': 'P[t,j] = (Re X[t,j]^2 + Im X[t,j]^2) / 2048.0^2',
    'one_sided_doubling': False,
    'magnitude_filterbank': 'not_part_of_v1; sqrt of band power is not a magnitude filterbank',
    'fmin_hz': FMIN,
    'fmax_hz': FMAX,
    'bins_per_octave': BINS_PER_OCTAVE,
    'n_bands': N_BANDS,
    'band_centre_formula': 'f_k = 20 * 2^(k/24), k = 0..159',
    'filter_shape': ('triangle in Hz at f_j = 1.953125 j; left half-width L_k = max(f_k - f_k*2^(-1/24), 1.953125), '
                     'right R_k = max(f_k*2^(1/24) - f_k, 1.953125); weight max(0, 1 - |f_j - f_k|/(L_k if f_j <= f_k else R_k))'),
    'filter_normalization': 'unit_sum_per_filter',
    'band_energy_formula': 'E[t,k] = sum_j W[k,j] * P[t,j], ascending j',
    'log_formula': 'D[t,k] = 10*log10(max(E[t,k], 1e-10))',
    'log_floor': LOG_FLOOR,
    'log_floor_policy': 'absolute_not_max_relative',
    'pcen': {
        'status': 'experimental_fixed_knobs_not_tuned',
        'input_formula': 'Z = E * 2^31',
        'input_scale': PCEN_SCALE,
        'gain': PCEN_GAIN,
        'bias': PCEN_BIAS,
        'power': PCEN_POWER,
        'time_constant_seconds': PCEN_TIME_CONSTANT,
        'eps': PCEN_EPS,
        'smoother_frames_T': PCEN_T_FRAMES,
        'smoother_coefficient_formula': 'b = (sqrt(1 + 4 T^2) - 1) / (2 T^2)',
        'smoother_coefficient': PCEN_B,
        'smoother_recursion': 'M[0] = Z[0]; M[t] = (1 - b) M[t-1] + b Z[t]',
        'output_formula': 'PCEN = (Z / (eps + M)^gain + bias)^power - bias^power',
        'state': 'causal; smoother row M carried across frames and streamed blocks; block equals batch exactly',
        'reset_on_block_boundary': False,
    },
    'output_layout': 'row_major_frames_by_bands_float64_little_endian',
}

FIXTURE = {
    'generator': 'python_stdlib_integers_and_math_sin_no_numpy',
    'sample_rate_hz': RATE,
    'channels': 1,
    'n_samples': 19200,
    'broadband': {'formula': 'b[n] = 0.02 * (2 u_n - 1); u_n = (z_n >> 11) * 2^-53',
                  'prng': 'splitmix64', 'seed': 20261006, 'amplitude': 0.02, 'draws_per_sample': 1},
    'harmonic': {'f0_formula': '440 * 2^((24 - 69)/12)', 'f0_hz': 440 * 2 ** ((24 - 69) / 12),
                 'f0_evidence': 'equal_temperament_theory_not_measured (C1 per program/instrument.json)',
                 'amplitudes': [0.30, 0.15, 0.10, 0.06, 0.04, 0.03], 'phase': 'zero',
                 'formula': 'h[n] = e[n] * sum_{m=1..6} a_m sin(2 pi m f0 n / 8000)'},
    'envelope': {'silent_before_sample': 4800, 'attack_samples': 80,
                 'formula': 'e = 0 for n < 4800; (n - 4800)/80 for 4800 <= n < 4880; 1 afterwards'},
    'mix': 'x = h + b',
    'encode': 'pcm16: clamp(round(x * 32768), -32768, 32767), Python round half-even',
    'container': 'RIFF WAVE PCM16 mono via stdlib wave, 44-byte header',
}

UNKNOWN_REASONS = {
    'note_identity': 'no approved reference; spectral peaks are not played notes',
    'intended_note_reference': 'no approved intended-note reference is bound to this transform',
    'tonic': 'not estimated by this transform; no approved reference',
    'mode': 'not estimated by this transform; no approved reference',
    'onset_timing': '512 ms support blurs ~84 ms sixteenths; use the separate short-window attack branch',
}


class Refusal(Exception):
    """A refused request (CLI exit 2); inputs and existing outputs are untouched."""


# ---------------------------------------------------------------------------
# hashing and spec identity

def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def spec_hash(spec: dict) -> str:
    """sha256 of the canonical JSON of the machine spec without its own hash field."""
    return sha256_bytes(canonical({k: v for k, v in spec.items() if k != 'spec_sha256'}))


def load_spec(path=SPEC_PATH) -> dict:
    """Load the machine spec and refuse a self-hash, version or parameter mismatch."""
    try:
        spec = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise Refusal(f'cannot read machine spec {path}: {exc}') from exc
    recomputed = spec_hash(spec)
    if spec.get('spec_sha256') != recomputed:
        raise Refusal(f'spec hash mismatch: stored {spec.get("spec_sha256")} recomputed {recomputed}')
    if spec.get('version') != SPEC_VERSION:
        raise Refusal(f'spec version {spec.get("version")!r} is not {SPEC_VERSION!r}')
    if spec.get('parameters') != PARAMETERS or spec.get('fixture') != FIXTURE:
        raise Refusal('machine spec parameters or fixture differ from this reference implementation')
    return spec


# ---------------------------------------------------------------------------
# geometry

def periodic_hann() -> list[float]:
    return [0.5 - 0.5 * math.cos(2 * math.pi * n / N_FFT) for n in range(N_FFT)]


def band_centres() -> list[float]:
    return [FMIN * 2 ** (k / BINS_PER_OCTAVE) for k in range(N_BANDS)]


def filterbank() -> list[tuple[int, list[float]]]:
    """Sparse unit-sum triangles: (first FFT bin index, weights) per band."""
    bank = []
    for fk in band_centres():
        left = max(fk - fk * 2 ** (-1 / BINS_PER_OCTAVE), BIN_HZ)
        right = max(fk * 2 ** (1 / BINS_PER_OCTAVE) - fk, BIN_HZ)
        weights = []
        for j in range(N_FFT_BINS):
            fj = BIN_HZ * j
            width = left if fj <= fk else right
            weights.append(max(0.0, 1 - abs(fj - fk) / width))
        nonzero = [j for j, w in enumerate(weights) if w > 0]
        if not nonzero:
            raise AssertionError(f'empty filter at {fk} Hz')
        first, last = nonzero[0], nonzero[-1]
        total = 0.0
        for j in range(first, last + 1):
            total += weights[j]
        bank.append((first, [weights[j] / total for j in range(first, last + 1)]))
    return bank


def frame_count(n_samples: int) -> int:
    if n_samples < N_FFT:
        raise Refusal(f'{n_samples} samples < {N_FFT}: no complete 512 ms frame')
    return 1 + (n_samples - N_FFT) // HOP


def frame_centre_seconds(t: int) -> float:
    return (HOP * t + N_FFT / 2) / RATE


def coverage(n_samples: int) -> dict:
    frames = frame_count(n_samples)
    last_centre = frame_centre_seconds(frames - 1)
    analysed_end = HOP * (frames - 1) + N_FFT
    return {
        'n_samples': n_samples,
        'duration_seconds': n_samples / RATE,
        'n_frames': frames,
        'first_frame_centre_seconds': frame_centre_seconds(0),
        'last_frame_centre_seconds': last_centre,
        'head_partial_support_seconds': [0.0, frame_centre_seconds(0)],
        'tail_partial_support_seconds': [last_centre, n_samples / RATE],
        'unanalysed_tail_samples': n_samples - analysed_end,
        'policy': 'no centre padding; head and tail have partial support and are reported, not silently dropped',
    }


# ---------------------------------------------------------------------------
# transforms

def _check_samples(samples) -> list[float]:
    values = [float(v) for v in samples]
    if not all(math.isfinite(v) for v in values):
        raise Refusal('non-finite sample values')
    frame_count(len(values))
    return values


def _power_stdlib(frame: list[float]) -> list[float]:
    spectrum = _radix2_fft(frame)
    scale = WINDOW_SUM * WINDOW_SUM
    return [(x.real * x.real + x.imag * x.imag) / scale for x in spectrum[:N_FFT_BINS]]


def band_energy(samples, backend: str = 'stdlib') -> list[list[float]]:
    """E[t,k] for every complete frame; float64, row-major frames x bands."""
    values = _check_samples(samples)
    frames = frame_count(len(values))
    window = periodic_hann()
    bank = filterbank()
    if backend == 'stdlib':
        rows = []
        for t in range(frames):
            start = HOP * t
            frame = [values[start + n] * window[n] for n in range(N_FFT)]
            power = _power_stdlib(frame)
            row = []
            for first, weights in bank:
                acc = 0.0
                for i, w in enumerate(weights):
                    acc += w * power[first + i]
                row.append(acc)
            rows.append(row)
        return rows
    if backend == 'numpy':
        try:
            import numpy as np
        except ImportError as exc:
            raise Refusal('numpy backend requested but numpy is not importable') from exc
        x = np.asarray(values, dtype=np.float64)
        w = np.asarray(window, dtype=np.float64)
        dense = np.zeros((N_BANDS, N_FFT_BINS), dtype=np.float64)
        for k, (first, weights) in enumerate(bank):
            dense[k, first:first + len(weights)] = weights
        rows = []
        for t in range(frames):
            spectrum = np.fft.rfft(x[HOP * t:HOP * t + N_FFT] * w)
            power = (spectrum.real * spectrum.real + spectrum.imag * spectrum.imag) / (WINDOW_SUM * WINDOW_SUM)
            rows.append([float(v) for v in dense @ power])
        return rows
    raise Refusal(f'unknown backend {backend!r}')


def log_power_db(energy: list[list[float]]) -> list[list[float]]:
    return [[10 * math.log10(max(e, LOG_FLOOR)) for e in row] for row in energy]


class PcenState:
    """Causal PCEN whose smoother row M is carried across frames and streamed blocks."""

    def __init__(self, n_bands: int = N_BANDS):
        self.n_bands = n_bands
        self.smoother: list[float] | None = None
        self.frames = 0

    def process(self, block: list[list[float]]) -> list[list[float]]:
        out = []
        bias_power = PCEN_BIAS ** PCEN_POWER
        for row in block:
            if len(row) != self.n_bands:
                raise Refusal(f'PCEN row has {len(row)} bands, expected {self.n_bands}')
            z = [e * PCEN_SCALE for e in row]
            if not all(math.isfinite(v) and v >= 0 for v in z):
                raise Refusal('PCEN input must be finite and non-negative')
            if self.smoother is None:
                self.smoother = list(z)
            else:
                self.smoother = [(1 - PCEN_B) * m + PCEN_B * v for m, v in zip(self.smoother, z)]
            out.append([(v / (PCEN_EPS + m) ** PCEN_GAIN + PCEN_BIAS) ** PCEN_POWER - bias_power
                        for v, m in zip(z, self.smoother)])
            self.frames += 1
        return out


def pcen(energy: list[list[float]]) -> list[list[float]]:
    return PcenState(len(energy[0]) if energy else N_BANDS).process(energy)


def render_samples(samples, backend: str = 'stdlib') -> dict:
    """Render D and PCEN matrices for mono 8000 Hz float samples (API; refuses non-finite)."""
    energy = band_energy(samples, backend)
    return {'band_energy': energy, 'log_power_db': log_power_db(energy), 'pcen': pcen(energy),
            'n_frames': len(energy), 'n_bands': N_BANDS, 'backend': backend}


# ---------------------------------------------------------------------------
# fixture

def splitmix64(seed: int):
    mask = (1 << 64) - 1
    state = seed & mask
    while True:
        state = (state + 0x9E3779B97F4A7C15) & mask
        z = state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & mask
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & mask
        yield z ^ (z >> 31)


def fixture_pcm() -> tuple[array.array, int]:
    """Deterministic PCM16 fixture samples and the clipped-sample count."""
    spec = FIXTURE
    f0 = spec['harmonic']['f0_hz']
    amps = spec['harmonic']['amplitudes']
    onset = spec['envelope']['silent_before_sample']
    attack = spec['envelope']['attack_samples']
    rng = splitmix64(spec['broadband']['seed'])
    pcm = array.array('h')
    clipped = 0
    for n in range(spec['n_samples']):
        u = (next(rng) >> 11) * 2.0 ** -53
        b = 0.02 * (2 * u - 1)
        if n < onset:
            e = 0.0
        elif n < onset + attack:
            e = (n - onset) / attack
        else:
            e = 1.0
        s = 0.0
        for m, a in enumerate(amps, start=1):
            s += a * math.sin(2 * math.pi * m * f0 * n / RATE)
        x = e * s + b
        q = round(x * 32768)
        if q > 32767 or q < -32768:
            clipped += 1
            q = max(-32768, min(32767, q))
        pcm.append(q)
    return pcm, clipped


def _pcm_le_bytes(pcm: array.array) -> bytes:
    data = array.array('h', pcm)
    if sys.byteorder == 'big':
        data.byteswap()
    return data.tobytes()


def write_fixture(out) -> dict:
    out = Path(out)
    if os.path.lexists(out):
        raise Refusal(f'refusing to overwrite existing path {out}')
    pcm, clipped = fixture_pcm()
    data = _pcm_le_bytes(pcm)
    with open(out, 'xb') as handle:
        with wave.open(handle, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(data)
    return {'path': str(out), 'wav_sha256': sha256_file(out), 'pcm_sha256': sha256_bytes(data),
            'n_samples': len(pcm), 'clipped_samples': clipped, 'bytes': out.stat().st_size}


# ---------------------------------------------------------------------------
# WAV input

def read_wav(path) -> tuple[list[float], dict]:
    path = Path(path)
    if path.is_symlink():
        raise Refusal(f'refusing symlinked input {path}')
    if not path.is_file():
        raise Refusal(f'input is not a regular file: {path}')
    try:
        with wave.open(str(path), 'rb') as w:
            channels, width, rate, count = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            comptype = w.getcomptype()
            raw = w.readframes(count)
    except (wave.Error, EOFError) as exc:
        raise Refusal(f'not a PCM16 WAV readable by stdlib wave: {exc}') from exc
    if comptype != 'NONE' or width != 2:
        raise Refusal(f'v1 requires PCM16; got sample width {width} bytes, compression {comptype}')
    if rate != RATE:
        raise Refusal(f'v1 requires {RATE} Hz input; got {rate} Hz (resample explicitly as a recorded pre-stage)')
    if channels < 1:
        raise Refusal('no channels')
    data = array.array('h')
    data.frombytes(raw[:len(raw) - len(raw) % (2 * channels)])
    if sys.byteorder == 'big':
        data.byteswap()
    if channels == 1:
        samples = [v / 32768.0 for v in data]
        downmix = 'none_mono'
    else:
        samples = []
        for i in range(0, len(data), channels):
            acc = 0.0
            for c in range(channels):
                acc += data[i + c] / 32768.0
            samples.append(acc / channels)
        downmix = 'arithmetic_mean_of_channels_float64'
    frame_count(len(samples))
    return samples, {'sample_rate': rate, 'channels': channels, 'downmix': downmix,
                     'sample_width_bytes': width, 'n_samples': len(samples)}


# ---------------------------------------------------------------------------
# declared fields shared by render.json and the golden

def declared_fields(input_record: dict, resampler: dict | None, spec: dict) -> dict:
    return {
        'spec_version': SPEC_VERSION,
        'spec_sha256': spec['spec_sha256'],
        'input': input_record,
        'pitch_resolution_claim': 'none',
        'note_identity': None,
        'intended_note_reference': None,
        'tonic': None,
        'mode': None,
        'onset_timing': None,
        'null_reasons': dict(UNKNOWN_REASONS,
                             resampler_group_delay_samples=('native 8000 Hz input; no resampler'
                                                            if resampler is None else
                                                            'unmeasured caller pre-stage resampler')),
        'temporal_support_seconds': N_FFT / RATE,
        'hop_seconds': HOP / RATE,
        'temporal_caveat': ('the 512 ms support (~16.7 C1 cycles) blurs a 178 BPM sixteenth (~84.27 ms) across ~6 '
                            'subdivisions; the 20 ms hop samples a 512 ms-smoothed trajectory and is not 20 ms '
                            'time resolution; the short-window attack branch stays separate'),
        'frequency_caveat': ('Hann main lobe spans +/-3.9 Hz while a semitone at C1 is ~1.94 Hz; energy near '
                             '32.7 Hz is not C1 identification and a dominant peak is not a played note'),
        'interpolated_below_hz': {'left': INTERPOLATED_BELOW_LEFT_HZ, 'right': INTERPOLATED_BELOW_RIGHT_HZ,
                                  'meaning': ('below these centres a filter half-width is clamped to one FFT bin '
                                              'and the band is linear interpolation of adjacent FFT bins; '
                                              'adjacent low bands are not independent measurements')},
        'resampler': resampler,
        'resampler_group_delay_samples': None,
        'calibration': {'scale': 'uncalibrated_digital_scale', 'microphone_response': 'unknown',
                        'meaning': 'window-normalized power samples, not dBFS or SPL'},
        'denoise_or_profile_applied': 'unknown',
        'denoise_or_profile_reason': 'caller did not bind the input to a run manifest',
        'pcen_status': 'experimental_fixed_knobs_not_tuned',
        'baseline': 'log-power (log-mel remains project baseline)',
        'listening_acceptance': 'not_assessed',
        'adoption': 'none',
        'adoption_note': 'no default, detector, profile or master change',
    }


def _load_resampler_record(path, input_sha: str) -> dict:
    try:
        record = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise Refusal(f'cannot read resampler record {path}: {exc}') from exc
    missing = [k for k in ('command', 'tool_version', 'output_sha256') if not record.get(k)]
    if missing:
        raise Refusal(f'resampler record lacks {missing}')
    if record['output_sha256'] != input_sha:
        raise Refusal('resampler record output_sha256 does not match the input WAV')
    return {'command': record['command'], 'tool_version': record['tool_version'],
            'output_sha256': record['output_sha256'], 'source_sha256': record.get('source_sha256'),
            'record_sha256': sha256_file(path), 'evidence': 'caller_supplied'}


# ---------------------------------------------------------------------------
# render CLI

def _f64le(matrix: list[list[float]]) -> bytes:
    data = array.array('d', (v for row in matrix for v in row))
    if sys.byteorder == 'big':
        data.byteswap()
    return data.tobytes()


def render(wav, out_dir, backend: str = 'stdlib', spec_path=SPEC_PATH, resampler_record=None,
           keep: dict | None = None) -> dict:
    """Render a native 8000 Hz PCM16 WAV; ``keep`` (a dict) receives the in-memory matrices."""
    spec = load_spec(spec_path)
    wav = Path(wav)
    out_dir = Path(out_dir)
    if os.path.lexists(out_dir) and (out_dir.is_symlink() or not out_dir.is_dir()):
        raise Refusal(f'output directory is a symlink or not a directory: {out_dir}')
    targets = {name: out_dir / name for name in ('render.json', 'log_power_db.f64le', 'pcen.f64le')}
    existing = [str(p) for p in targets.values() if os.path.lexists(p)]
    if existing:
        raise Refusal(f'refusing to overwrite existing outputs {existing}')
    if wav.is_symlink():
        raise Refusal(f'refusing symlinked input {wav}')
    before = sha256_file(wav) if wav.is_file() else None
    samples, meta = read_wav(wav)
    resampler = _load_resampler_record(resampler_record, before) if resampler_record else None
    result = render_samples(samples, backend)
    after = sha256_file(wav)
    if after != before:
        raise Refusal('input changed during render; outputs not written')
    out_dir.mkdir(parents=True, exist_ok=True)
    if out_dir.is_symlink():
        raise Refusal(f'output directory is a symlink: {out_dir}')
    files = {}
    for name in MATRICES:
        raw = _f64le(result[name])
        with open(targets[f'{name}.f64le'], 'xb') as handle:
            handle.write(raw)
        files[name] = {'path': f'{name}.f64le', 'sha256': sha256_bytes(raw), 'bytes': len(raw),
                       'dtype': 'float64_little_endian', 'layout': 'row_major_frames_by_bands',
                       'shape': [result['n_frames'], N_BANDS]}
    input_record = dict(meta, path=str(wav), sha256=before, sha256_after_render=after,
                        unchanged=after == before, signal_version=f'sha256:{before}')
    payload = {'schema': RENDER_SCHEMA, **declared_fields(input_record, resampler, spec),
               'backend': backend, 'shape': {'frames': result['n_frames'], 'bands': N_BANDS},
               'coverage': coverage(meta['n_samples']),
               'band_centre_hz': band_centres(), 'files': files,
               'script_sha256': sha256_file(__file__)}
    with open(targets['render.json'], 'x') as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write('\n')
    if keep is not None:
        keep.update(result)
    return payload


# ---------------------------------------------------------------------------
# golden

def _aggregates(matrix: list[list[float]]) -> dict:
    flat = [v for row in matrix for v in row]
    return {'sum': math.fsum(flat), 'min': min(flat), 'max': max(flat)}


def fixture_wav_bytes(pcm: array.array) -> bytes:
    import io
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(_pcm_le_bytes(pcm))
    return buffer.getvalue()


def assemble_golden(result: dict, pcm: array.array, clipped: int, spec: dict) -> dict:
    """Build the golden payload from a full fixture render (in memory or via render())."""
    data = _pcm_le_bytes(pcm)
    wav_bytes = fixture_wav_bytes(pcm)
    rows = {name: [list(result[name][t]) for t in GOLDEN_FRAMES] for name in MATRICES}
    trajectories = {name: [[row[k] for row in result[name]] for k in GOLDEN_BINS] for name in MATRICES}
    input_record = {'path': 'generated fixture (scripts/lowreg_spectrogram.py fixture)',
                    'sha256': sha256_bytes(wav_bytes), 'sample_rate': RATE, 'channels': 1,
                    'downmix': 'none_mono', 'signal_version': f'sha256:{sha256_bytes(wav_bytes)}'}
    centres = band_centres()
    return {
        'schema': GOLDEN_SCHEMA,
        **declared_fields(input_record, None, spec),
        'fixture': dict(FIXTURE, wav_sha256=sha256_bytes(wav_bytes), pcm_sha256=sha256_bytes(data),
                        wav_bytes=len(wav_bytes), clipped_samples=clipped),
        'shape': {'frames': result['n_frames'], 'bands': N_BANDS},
        'backend': result['backend'],
        'tolerance': dict(TOLERANCE, rule='math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)'),
        'coverage': coverage(len(pcm)),
        'stored_frames': list(GOLDEN_FRAMES),
        'stored_frame_centre_seconds': [frame_centre_seconds(t) for t in GOLDEN_FRAMES],
        'stored_bins': list(GOLDEN_BINS),
        'stored_bin_centre_hz': [centres[k] for k in GOLDEN_BINS],
        'rows': rows,
        'trajectories': trajectories,
        'aggregates': {name: _aggregates(result[name]) for name in MATRICES},
        'stored_value_count': (len(GOLDEN_FRAMES) * N_BANDS + len(GOLDEN_BINS) * result['n_frames']) * len(MATRICES),
        'reduction': None,
        'generator': {'script': 'scripts/lowreg_spectrogram.py', 'sha256': sha256_file(__file__),
                      'role': 'provenance_only_not_a_test_gate'},
    }


def golden_payload(backend: str = 'stdlib', spec_path=SPEC_PATH) -> tuple[dict, dict]:
    """Regenerate the golden payload (and the full render) from the generated fixture."""
    spec = load_spec(spec_path)
    pcm, clipped = fixture_pcm()
    result = render_samples([v / 32768.0 for v in pcm], backend)
    return assemble_golden(result, pcm, clipped, spec), result


def serialize_golden(payload: dict) -> str:
    text = json.dumps(payload, indent=1, sort_keys=True, allow_nan=False)
    # Collapse purely numeric arrays onto one line; floats keep Python repr.
    return re.sub(r'\[\s*([-0-9.eE+]+(?:,\s*[-0-9.eE+]+)*)\s*\]',
                  lambda m: '[' + ','.join(p.strip() for p in m.group(1).split(',')) + ']', text) + '\n'


def compare_golden(stored: dict, regenerated: dict) -> dict:
    """Count stored values, aggregates, shape and identities matching within tolerance."""
    def close(a, b):
        return math.isclose(a, b, rel_tol=TOLERANCE['rel'], abs_tol=TOLERANCE['abs'])
    total = matched = 0
    worst = 0.0
    for section in ('rows', 'trajectories'):
        for name in MATRICES:
            for srow, rrow in zip(stored[section][name], regenerated[section][name]):
                if len(srow) != len(rrow):
                    total += max(len(srow), len(rrow))
                    continue
                for a, b in zip(srow, rrow):
                    total += 1
                    matched += close(a, b)
                    worst = max(worst, abs(a - b))
    agg_total = agg_matched = 0
    for name in MATRICES:
        for key in ('sum', 'min', 'max'):
            agg_total += 1
            agg_matched += close(stored['aggregates'][name][key], regenerated['aggregates'][name][key])
    shape_matched = sum(stored['shape'][k] == regenerated['shape'][k] for k in ('frames', 'bands'))
    identities = {
        'wav_sha256': stored['fixture']['wav_sha256'] == regenerated['fixture']['wav_sha256'],
        'pcm_sha256': stored['fixture']['pcm_sha256'] == regenerated['fixture']['pcm_sha256'],
        'spec_sha256': stored['spec_sha256'] == regenerated['spec_sha256'],
    }
    ok = (matched == total == stored['stored_value_count'] and agg_matched == agg_total == 6
          and shape_matched == 2 and all(identities.values()))
    return {'ok': ok, 'values_matched': matched, 'values_total': total, 'aggregates_matched': agg_matched,
            'aggregates_total': agg_total, 'shape_matched': shape_matched, 'shape_total': 2,
            'identities': identities, 'max_abs_difference': worst}


def check_golden(path=GOLDEN_PATH, backend: str = 'stdlib', spec_path=SPEC_PATH) -> dict:
    stored = json.loads(Path(path).read_text())
    regenerated, _ = golden_payload(backend, spec_path)
    report = compare_golden(stored, regenerated)
    report['golden_bytes'] = Path(path).stat().st_size
    report['golden_sha256'] = sha256_file(path)
    report['backend'] = backend
    return report


def write_golden(path, spec_path=SPEC_PATH) -> dict:
    path = Path(path)
    if os.path.lexists(path):
        raise Refusal(f'refusing to overwrite golden {path}; a new golden needs a new spec version')
    payload, _ = golden_payload('stdlib', spec_path)
    text = serialize_golden(payload)
    if len(text.encode()) > GOLDEN_MAX_BYTES:
        raise Refusal(f'golden would be {len(text.encode())} bytes > {GOLDEN_MAX_BYTES}; apply the contract reduction')
    with open(path, 'x') as handle:
        handle.write(text)
    return {'path': str(path), 'sha256': sha256_file(path), 'bytes': path.stat().st_size,
            'stored_value_count': payload['stored_value_count']}


# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('fixture', help='write the deterministic generated fixture WAV')
    p.add_argument('--out', required=True)
    p = sub.add_parser('render', help='render D and PCEN matrices for an 8000 Hz PCM16 WAV')
    p.add_argument('--wav', required=True)
    p.add_argument('--out-dir', required=True)
    p.add_argument('--backend', choices=('stdlib', 'numpy'), default='stdlib')
    p.add_argument('--spec', default=str(SPEC_PATH))
    p.add_argument('--resampler-record', help='JSON {command, tool_version, output_sha256} for an external 8 kHz pre-stage')
    p = sub.add_parser('golden', help='check or (new spec version only) write the golden file')
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', metavar='PATH')
    mode.add_argument('--write', metavar='PATH')
    p.add_argument('--backend', choices=('stdlib', 'numpy'), default='stdlib')
    p.add_argument('--spec', default=str(SPEC_PATH))
    p = sub.add_parser('spec', help='print the recomputed machine-spec hash')
    p.add_argument('--sha', action='store_true', required=True)
    p.add_argument('--spec', default=str(SPEC_PATH))
    args = parser.parse_args(argv)
    try:
        if args.command == 'fixture':
            result = write_fixture(args.out)
        elif args.command == 'render':
            payload = render(args.wav, args.out_dir, args.backend, args.spec, args.resampler_record)
            result = {'out_dir': args.out_dir, 'shape': payload['shape'], 'input_sha256': payload['input']['sha256'],
                      'files': {k: v['sha256'] for k, v in payload['files'].items()}}
        elif args.command == 'golden':
            if args.check:
                result = check_golden(args.check, args.backend, args.spec)
                print(json.dumps(result, indent=2, sort_keys=True))
                return 0 if result['ok'] else 1
            result = write_golden(args.write, args.spec)
        else:
            spec = json.loads(Path(args.spec).read_text())
            recomputed = spec_hash(spec)
            print(recomputed)
            return 0 if spec.get('spec_sha256') == recomputed else 1
    except Refusal as exc:
        print(f'refused: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
