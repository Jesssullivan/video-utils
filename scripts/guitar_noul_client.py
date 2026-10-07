#!/usr/bin/env python3
"""guitar_noul gateway client for the TIN-5619 closed contract; outputs are detector hypotheses only.

Input (closed): {run_dir, windows:[{source_start_s, source_end_s}], timeout_seconds}.
Configuration comes only from the environment:
  VIDEO_UTILS_GUITAR_NOUL_GATEWAY        https URL on models.xoxd.ai or *.ts.net (unset -> gateway_not_configured)
  VIDEO_UTILS_GUITAR_NOUL_ALLOW_REAL_TAKE exact value "v6-private-operator-lab-host" permits real-take windows (V6)
The gateway is assumed tailnet-only behind tsidp (Jess-only) and is not deployed;
the client holds no credentials. The wire format (tin-5619-v0) is provisional and
unratified. Contract: docs/spec/sprints/MODEL_LANES_S3.md section 4.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import wave

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
from beat_this_compare import read_wav_mono, sha256_file, wav_header  # noqa: E402

CONTRACT = 'tin-5619-v0'
GATEWAY_ENV = 'VIDEO_UTILS_GUITAR_NOUL_GATEWAY'
ALLOW_ENV = 'VIDEO_UTILS_GUITAR_NOUL_ALLOW_REAL_TAKE'
ALLOW_VALUE = 'v6-private-operator-lab-host'
PAYLOAD_RATE = 16000
PAYLOAD_KIND = 'pcm16_wav_mono_16k_b64'
LIMITS = {'windows': 64, 'window_min_seconds': .25, 'window_max_seconds': 30.0, 'timeout_min': 1, 'timeout_max': 120,
          'manifest_bytes': 1024**2, 'request_bytes': 8 * 1024**2, 'response_bytes': 1024**2, 'attempts': 2}
ALLOWED_RUN_BASES = (Path('artifacts/runs'), Path('artifacts/s2/model_lanes/fixtures'))
OUTPUT_BASE = Path('artifacts/s2/model_lanes')
LABEL = re.compile(r'[a-z0-9_.:-]{1,64}')
GGUF = re.compile(r'[0-9a-f]{64}')
CATALOG = re.compile(r'xoxd/rune-26b-a4b-v3-xoruby-[a-z0-9][a-z0-9._-]{0,63}-(\d{8}|\d{4}-\d{2}-\d{2})')
FIXED_WINDOW_FIELDS = {
    'claim_class': 'detector_hypothesis', 'authorship': 'detector:guitar_noul', 'is_label': False,
    'user_reported': False, 'note_correctness': None, 'performance_issue': None,
    'label_vocabulary_ratified': False, 'confidence_kind': 'gateway_reported_uncalibrated',
}


class Refused(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class TransportTimeout(Exception):
    pass


class TransportUnreachable(Exception):
    pass


def refusal(code: str, message: str, transport_invoked: bool = False) -> dict:
    return {'schema_version': 1, 'status': 'refused', 'refusal_code': code, 'message': message,
            'contract': CONTRACT, 'transport_invoked': transport_invoked, 'claim_class': 'detector_hypothesis'}


def finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


# --------------------------------------------------------------------------- validation

def validate_request(request, root: Path = ROOT) -> dict:
    if not isinstance(request, dict) or set(request) != {'run_dir', 'windows', 'timeout_seconds'}:
        raise Refused('input_schema_invalid', 'Closed input requires exactly run_dir, windows and timeout_seconds')
    timeout = request['timeout_seconds']
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not LIMITS['timeout_min'] <= timeout <= LIMITS['timeout_max']:
        raise Refused('input_schema_invalid', 'timeout_seconds must be an integer 1-120')
    raw = request['run_dir']
    if not isinstance(raw, str) or not 1 <= len(raw) <= 4096:
        raise Refused('input_schema_invalid', 'run_dir must be a 1-4096 character string')
    if '..' in Path(raw).parts:
        raise Refused('input_schema_invalid', 'run_dir must not contain traversal components')
    path = Path(os.path.abspath(raw if Path(raw).is_absolute() else root / raw))
    if not any(path.is_relative_to(root / base) and path != root / base for base in ALLOWED_RUN_BASES):
        raise Refused('input_schema_invalid', 'run_dir must be beneath artifacts/runs/ or artifacts/s2/model_lanes/fixtures/')
    for item in (path, *path.parents):
        if item.is_symlink():
            raise Refused('input_schema_invalid', 'run_dir must not contain symlinked components')
        if item == root:
            break
    if not path.is_dir():
        raise Refused('input_schema_invalid', 'run_dir must be an existing directory')
    manifest_path = path / 'manifest.json'
    if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size > LIMITS['manifest_bytes']:
        raise Refused('input_schema_invalid', 'run_dir needs a regular manifest.json of at most 1 MiB')
    manifest_bytes = manifest_path.read_bytes()
    try:
        manifest = json.loads(manifest_bytes)
    except ValueError:
        raise Refused('input_schema_invalid', 'manifest.json is not JSON')
    duration = manifest.get('pcm', {}).get('duration_seconds') if isinstance(manifest, dict) and isinstance(manifest.get('pcm'), dict) else None
    if not finite(duration) or duration <= 0:
        raise Refused('input_schema_invalid', 'manifest pcm.duration_seconds must be a known positive duration')
    windows = request['windows']
    if not isinstance(windows, list) or not 1 <= len(windows) <= LIMITS['windows']:
        raise Refused('window_invalid', 'windows must hold 1-64 windows')
    parsed = []
    for index, window in enumerate(windows):
        if not isinstance(window, dict) or set(window) != {'source_start_s', 'source_end_s'}:
            raise Refused('window_invalid', f'window {index} must have exactly source_start_s and source_end_s')
        start, end = window['source_start_s'], window['source_end_s']
        if not finite(start) or not finite(end) or not 0 <= start < end <= duration:
            raise Refused('window_invalid', f'window {index} must satisfy 0 <= start < end <= manifest duration')
        if not LIMITS['window_min_seconds'] <= end - start <= LIMITS['window_max_seconds']:
            raise Refused('window_invalid', f'window {index} length must be 0.25-30 seconds')
        parsed.append({'index': index, 'source_start_s': float(start), 'source_end_s': float(end)})
    ordered = sorted(parsed, key=lambda w: w['source_start_s'])
    if any(b['source_start_s'] < a['source_end_s'] for a, b in zip(ordered, ordered[1:])):
        raise Refused('window_invalid', 'windows must not overlap')
    return {'run_dir': path, 'manifest': manifest, 'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
            'duration_seconds': float(duration), 'windows': parsed, 'timeout_seconds': timeout}


def gateway_config(env) -> tuple[str, str]:
    url = env.get(GATEWAY_ENV, '')
    if not url:
        raise Refused('gateway_not_configured', f'{GATEWAY_ENV} is unset; the models.xoxd.ai gateway is not deployed (TIN-5590/TIN-5619)')
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or '').lower()
    try:
        port = parsed.port
    except ValueError:
        port = -1
    if (parsed.scheme != 'https' or parsed.username or parsed.password or '@' in parsed.netloc or port not in (None, 443)
            or not (host == 'models.xoxd.ai' or (host.endswith('.ts.net') and len(host) > len('.ts.net')))):
        raise Refused('gateway_url_rejected', 'Gateway must be https, no userinfo, port 443, host models.xoxd.ai or *.ts.net')
    return url, host


def is_real_take(manifest: dict) -> bool:
    """Synthetic only when explicitly declared as a generated fixture with generator id and seed; fail closed."""
    source = manifest.get('source')
    synthetic = (isinstance(source, dict) and source.get('kind') == 'generated_fixture'
                 and isinstance(source.get('generator'), str) and bool(source.get('generator'))
                 and isinstance(source.get('seed'), int) and not isinstance(source.get('seed'), bool))
    return not synthetic


# --------------------------------------------------------------------------- payload

def resample_linear(samples: list[float], rate: int, target: int = PAYLOAD_RATE) -> list[float]:
    """Boxcar pre-average then linear interpolation; a provisional wire payload, not an analysis master."""
    if rate == target or not samples:
        return list(samples)
    width = max(1, int(rate // target))
    if width > 1:
        smoothed, total = [], 0.0
        for i, value in enumerate(samples):
            total += value
            if i >= width:
                total -= samples[i - width]
            smoothed.append(total / min(i + 1, width))
        samples = smoothed
    count = int(len(samples) * target / rate)
    out = []
    for n in range(count):
        position = n * rate / target
        i = int(position)
        frac = position - i
        nxt = samples[i + 1] if i + 1 < len(samples) else samples[i]
        out.append(samples[i] * (1 - frac) + nxt * frac)
    return out


def window_payload(audio: Path, origin: float, window: dict) -> str:
    samples, rate = read_wav_mono(audio, window['source_start_s'] - origin, window['source_end_s'] - origin)
    pcm = resample_linear(samples, rate)
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(PAYLOAD_RATE)
        writer.writeframes(b''.join(max(-32768, min(32767, int(round(v * 32767)))).to_bytes(2, 'little', signed=True) for v in pcm))
    return base64.b64encode(buffer.getvalue()).decode('ascii')


def build_request(validated: dict) -> tuple[bytes, dict]:
    manifest, run_dir = validated['manifest'], validated['run_dir']
    audio = run_dir / 'denoised.wav'
    recorded = manifest.get('output_sha256', {}).get('denoised.wav') if isinstance(manifest.get('output_sha256'), dict) else None
    if audio.is_symlink() or not audio.is_file() or recorded is None or sha256_file(audio) != recorded:
        raise Refused('input_schema_invalid', 'Payload reads only a manifest-verified regular denoised.wav')
    timeline = manifest.get('timeline')
    origin = timeline.get('audio_start_seconds') if isinstance(timeline, dict) else None
    if not finite(origin):
        raise Refused('input_schema_invalid', 'Manifest timeline.audio_start_seconds must be explicit')
    header = wav_header(audio)
    for window in validated['windows']:
        if window['source_end_s'] - origin > header['duration_seconds'] + 1e-6 or window['source_start_s'] < origin:
            raise Refused('window_invalid', f"window {window['index']} lies outside denoised.wav")
    source = manifest.get('source', {}) if isinstance(manifest.get('source'), dict) else {}
    body = {'contract': CONTRACT, 'source_sha256': source.get('sha256'), 'signal_version': f'sha256:{recorded}',
            'windows': [{**w, 'payload_kind': PAYLOAD_KIND, 'payload': window_payload(audio, origin, w)} for w in validated['windows']]}
    data = json.dumps(body, separators=(',', ':')).encode()
    if len(data) > LIMITS['request_bytes']:
        raise Refused('window_invalid', 'Request payload exceeds 8 MiB; send fewer or shorter windows')
    identity = {'run_dir': str(run_dir), 'manifest_sha256': validated['manifest_sha256'], 'source_sha256': source.get('sha256'),
                'signal_version': f'sha256:{recorded}', 'payload_kind': PAYLOAD_KIND, 'payload_rate': PAYLOAD_RATE,
                'payload_resampling': 'boxcar_preaverage_then_linear_interpolation', 'request_sha256': hashlib.sha256(data).hexdigest(),
                'request_bytes': len(data)}
    return data, identity


# --------------------------------------------------------------------------- transport

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def urllib_transport(url: str, body: bytes, timeout: float) -> tuple[int, bytes]:
    """Default transport: one HTTPS POST, no redirects, no credentials, bounded response."""
    request = urllib.request.Request(url, data=body, method='POST',
                                     headers={'Content-Type': 'application/json', 'User-Agent': 'video-utils-guitar-noul/0'})
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read(LIMITS['response_bytes'] + 1)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(LIMITS['response_bytes'] + 1) if exc.fp else b''
    except (socket.timeout, TimeoutError) as exc:
        raise TransportTimeout(str(exc))
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            raise TransportTimeout(str(exc))
        raise TransportUnreachable(str(exc))
    except OSError as exc:
        raise TransportUnreachable(str(exc))


# --------------------------------------------------------------------------- response handling

def _window_record(window: dict, **decision) -> dict:
    record = {'index': window['index'], 'source_start_s': window['source_start_s'], 'source_end_s': window['source_end_s'],
              'decision': {'label': None}, 'abstain': True, 'abstain_reason': None, 'confidence_label': None,
              'model_identity': None, 'raw_response_sha256': None}
    record.update(decision)
    record.update(FIXED_WINDOW_FIELDS)
    return record


def _valid_identity(identity) -> bool:
    return (isinstance(identity, dict) and set(identity) == {'gguf_sha256', 'catalog_name'}
            and isinstance(identity['gguf_sha256'], str) and GGUF.fullmatch(identity['gguf_sha256']) is not None
            and isinstance(identity['catalog_name'], str) and CATALOG.fullmatch(identity['catalog_name']) is not None)


def parse_window(item) -> dict | None:
    """Returns the decision fields or None when the gateway item is invalid."""
    if not isinstance(item, dict):
        return None
    label, abstain = item.get('label'), item.get('abstain', False)
    reason, confidence, identity = item.get('abstain_reason'), item.get('confidence_label'), item.get('model_identity')
    if not isinstance(abstain, bool) or (label is not None) == abstain:
        return None  # exactly one of label / abstain
    if label is not None and (not isinstance(label, str) or LABEL.fullmatch(label) is None):
        return None
    if confidence is not None and (not isinstance(confidence, str) or LABEL.fullmatch(confidence) is None):
        return None
    if abstain and (not isinstance(reason, str) or LABEL.fullmatch(reason) is None):
        return None
    if not abstain and reason is not None:
        return None
    if label is not None and not _valid_identity(identity):
        return None
    if identity is not None and not _valid_identity(identity):
        return None
    return {'decision': {'label': label}, 'abstain': abstain, 'abstain_reason': f'gateway:{reason}' if abstain else None,
            'confidence_label': confidence, 'model_identity': identity}


def interpret(windows: list[dict], raw: bytes) -> list[dict]:
    digest = hashlib.sha256(raw).hexdigest()
    try:
        body = json.loads(raw) if len(raw) <= LIMITS['response_bytes'] else None
    except ValueError:
        body = None
    items = body.get('windows') if isinstance(body, dict) and body.get('contract') == CONTRACT else None
    if not isinstance(items, list):
        return [_window_record(w, abstain_reason='gateway_response_invalid', raw_response_sha256=digest) for w in windows]
    by_index, duplicates = {}, set()
    for item in items:
        index = item.get('index') if isinstance(item, dict) else None
        if isinstance(index, int) and not isinstance(index, bool):
            if index in by_index:
                duplicates.add(index)
            by_index[index] = item
    records = []
    for window in windows:
        i = window['index']
        if i not in by_index:
            records.append(_window_record(window, abstain_reason='missing_from_response', raw_response_sha256=digest))
            continue
        decision = None if i in duplicates else parse_window(by_index[i])
        if decision is None:
            records.append(_window_record(window, abstain_reason='gateway_response_invalid', raw_response_sha256=digest))
        else:
            records.append(_window_record(window, **decision, raw_response_sha256=digest))
    return records


# --------------------------------------------------------------------------- entry

def decide(request, env=None, transport=None, root: Path = ROOT, clock=time.monotonic) -> dict:
    env = os.environ if env is None else env
    started = clock()
    try:
        validated = validate_request(request, root)
        url, host = gateway_config(env)
        real = is_real_take(validated['manifest'])
        permission = env.get(ALLOW_ENV) == ALLOW_VALUE
        if real and not permission:
            raise Refused('real_take_not_permitted', f'Real-take windows leave video-utils only with {ALLOW_ENV}={ALLOW_VALUE} (V6); fail closed')
        body, identity = build_request(validated)
    except Refused as exc:
        return refusal(exc.code, str(exc))
    send = transport or urllib_transport
    deadline = started + validated['timeout_seconds']
    attempts, status, raw, outcome = 0, None, b'', None
    while attempts < LIMITS['attempts']:
        remaining = deadline - clock()
        if remaining <= 0:
            outcome = 'timeout'
            break
        attempts += 1
        try:
            status, raw = send(url, body, remaining)
            outcome = 'response'
            break
        except TransportTimeout:
            outcome = 'timeout'
            break
        except TransportUnreachable:
            outcome = 'unreachable'
    receipt = {'attempts': attempts, 'elapsed_seconds': clock() - started, 'http_status': status,
               'max_attempts': LIMITS['attempts'], 'retry_policy': 'one retry on connection error only'}
    if outcome == 'unreachable':
        return {**refusal('gateway_unreachable', 'Gateway connection failed (tailnet/tsidp path unavailable)', True), 'transport_receipt': receipt}
    if outcome == 'response' and status in (401, 403):
        return {**refusal('gateway_auth_refused', f'Gateway refused identity with HTTP {status}; the client holds no credentials', True),
                'transport_receipt': receipt}
    if outcome == 'timeout':
        windows = [_window_record(w, abstain_reason='timeout') for w in validated['windows']]
    elif status != 200:
        windows = [_window_record(w, abstain_reason='gateway_response_invalid', raw_response_sha256=hashlib.sha256(raw).hexdigest())
                   for w in validated['windows']]
    else:
        windows = interpret(validated['windows'], raw)
    doc = {'schema_version': 1, 'status': 'completed', 'tool': 'guitar_noul_decide', 'contract': CONTRACT,
           'gateway_wire_schema_ratified': False, 'gateway': {'url_host': host, 'configured': True},
           'gateway_assumptions': 'tailnet-only behind tsidp, Jess-only, not verified by this client',
           'real_take': real, 'real_take_permission': ALLOW_VALUE if real else None,
           'input_identity': {k: v for k, v in identity.items() if k != 'run_dir'},
           'transport_receipt': receipt, 'windows': windows,
           'claim_class': 'detector_hypothesis', 'labels_are_opaque': True,
           'mapping_to_annotations': None, 'default_adoption': False,
           'limitations': ['Per-window decisions are gateway detector hypotheses, never labels, flags, review badges or note verdicts.',
                           'Label vocabulary and wire schema are unratified; confidence labels are gateway-reported and uncalibrated.',
                           'Gateway identity (tsidp/tailnet) is assumed, not verified by the client.']}
    if real:
        doc['privacy'] = 'V6_private_real_take_derived'
    return doc


def write_output(doc: dict, out: Path, run_dir: Path | None, root: Path = ROOT) -> Path:
    if '..' in Path(out).parts:
        raise Refused('input_schema_invalid', 'Output path must not contain traversal')
    target = Path(os.path.abspath(out if Path(out).is_absolute() else root / out))
    if not target.is_relative_to(root / OUTPUT_BASE) or (run_dir is not None and target.is_relative_to(run_dir)):
        raise Refused('input_schema_invalid', f'Output must be beneath {OUTPUT_BASE} and never inside run_dir')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x') as handle:
        handle.write(json.dumps(doc, indent=2, allow_nan=False) + '\n')
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--request', type=Path, help='JSON request file (default: stdin)')
    parser.add_argument('--out', type=Path, help=f'write guitar_noul_decisions.json beneath {OUTPUT_BASE}')
    args = parser.parse_args(argv)
    try:
        text = args.request.read_text() if args.request else sys.stdin.read()
        request = json.loads(text)
    except (OSError, ValueError) as exc:
        print(json.dumps(refusal('input_schema_invalid', f'Unreadable request: {exc}')))
        return 2
    doc = decide(request)
    try:
        if args.out and doc['status'] == 'completed':
            run_dir = Path(os.path.abspath(request['run_dir'] if Path(request['run_dir']).is_absolute() else ROOT / request['run_dir']))
            print(json.dumps({'status': doc['status'], 'output': str(write_output(doc, args.out, run_dir))}))
        else:
            print(json.dumps(doc))
    except Refused as exc:
        print(json.dumps(refusal(exc.code, str(exc))))
        return 2
    return 0 if doc['status'] == 'completed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
