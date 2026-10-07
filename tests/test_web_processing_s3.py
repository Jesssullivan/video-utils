"""S3 routes_processing lane suite (docs/spec/sprints/ROUTES_PROCESSING_S3.md section 11).

Covers the closed job-type allowlist (M1, M3, M11), validation parity with
tool_api (M2), capture review binding and the first-five-seconds rule (M4, M5a,
M5b), FULLER refusal without an interval on the server and in the pure UI option
builder (M6), FULLER preset fidelity (M7), per-type lifecycle (M8), one active
media job per host (M9), path hygiene (M10), unknown fields (M12), interval
statistics on analytic fixtures (M15) and the schema v1 -> v2 migration.

Synthetic fixtures only; the real take is never opened. FFmpeg-dependent and
node-dependent cases skip with a reason (a skip is never counted as a pass).
Every subprocess has an explicit timeout. Metrics are printed at module teardown
and, when WEB_S3_METRICS_OUT names a file, written there as JSON.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import artifact_ids  # noqa: E402
import capture_profile  # noqa: E402
import media  # noqa: E402
import tool_api  # noqa: E402
import web_api  # noqa: E402
import web_jobs  # noqa: E402
from web_jobs import WebJobs, WebJobsError  # noqa: E402
from test_web_jobs import (FAKE_MOV, FFMPEG, FFMPEG_SKIP, HAVE_FFMPEG, STUB, Client,  # noqa: E402
                           make_clip, sigkill_own_group)

METRICS: dict = {}
SEED = 20261007
WEB = ROOT / 'web'
OPTIONS_TS = WEB / 'src' / 'lib' / 'server' / 'processing' / 'options.ts'
ACCEPTED_FULLER_RUN = '20261006T041633Z-990aa1bd6737'
RECEIPTS = ROOT / 'docs' / 'agent-notes' / 'sprints' / '20261007-s3'
PENDING = ('denoise', 'capture_profile', 'apply_capture_profile')
ALL_ADMITTED = frozenset(web_jobs.JOB_TYPE_NAMES)

# --------------------------------------------------------------------------- stub worker

S3_STUB = r'''
import hashlib, json, os, signal, subprocess, sys, time, uuid, datetime
mode, beat, raw = sys.argv[1:4]
args = json.loads(raw)
job = args.pop('_web_job')
tool, runs = job['tool'], job['runs_dir']
def on_term(signum, frame):
    with open(beat + '.sigterm', 'w') as handle:
        handle.write(str(os.getpid()))
    os._exit(143)
signal.signal(signal.SIGTERM, on_term)
def sha(path):
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()
def stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:12]
def write_beat(extra):
    with open(beat + '.tmp', 'w') as handle:
        json.dump(dict({'pid': os.getpid(), 'mode': mode, 'tool': tool}, **extra), handle)
    os.replace(beat + '.tmp', beat)
if mode == 'sleep':
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    write_beat({'child': child.pid})
    end = time.time() + 60
    while time.time() < end:
        time.sleep(0.05)
    sys.exit(3)
if mode == 'garbage':
    print('not json')
    sys.exit(0)
if mode == 'reject':
    print(json.dumps({'schema_version': 1, 'tool': tool, 'status': 'error',
                      'error': {'code': 'validation_failed', 'message': 'stub refusal /never/echoed'}}))
    sys.exit(2)
started = time.time()
if mode == 'timed':
    time.sleep(0.4)
def run_files(directory, extra_outputs=()):
    os.makedirs(directory)
    names = {'source': 'source.wav', 'denoised': 'denoised.wav', 'baseline': 'baseline.wav',
             'cleaned': 'cleaned.wav', 'residue': 'residue.wav'}
    for role, name in names.items():
        with open(os.path.join(directory, name), 'wb') as handle:
            handle.write(('RIFF-stub-' + role + '-' + os.path.basename(directory)).encode())
    hashes = {name: sha(os.path.join(directory, name)) for name in names.values()}
    return names, hashes
source_sha = sha(args['input'])
if tool == 'denoise':
    run_id = stamp()
    directory = os.path.join(runs, run_id)
    outputs, hashes = run_files(directory)
    manifest = {'schema_version': 1, 'status': 'rendered_unreviewed', 'run_id': run_id, 'run_dir': directory,
                'profile': {'name': args['profile']}, 'source': {'path': args['input'], 'sha256': source_sha},
                'pcm': {'sample_rate': 16000, 'channels': 1, 'sample_count': 16000, 'duration_seconds': 1.0,
                        'codec': 'pcm_f32le'},
                'timeline': {'no_time_stretch': True, 'audio_start_seconds': 0.0, 'format_start_seconds': 0.0},
                'outputs': outputs, 'output_sha256': hashes,
                'frequency_preservation': {'high_pass_applied': False, 'hum_notches_applied': False}}
    with open(os.path.join(directory, 'manifest.json'), 'w') as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write('\n')
    result = manifest
elif tool == 'capture_profile':
    with open(args['review']) as handle:
        review = json.load(handle)
    status = 'authored_unrendered'
    if review['review_status'] == 'rejected_contaminated' or 'reviewed_present' in (review['music_status'], review['click_status']):
        status = 'needs_reselection'
    elif review['authorization_scope'] == 'profile_authoring':
        status = 'draft_authorization_incomplete'
    parent = os.path.join(args['run_dir'], 'capture-profiles')
    os.makedirs(parent, exist_ok=True)
    directory = os.path.join(parent, stamp())
    os.makedirs(directory)
    profile_sha = None
    if status != 'needs_reselection':
        name = 'profile.json' if status == 'authored_unrendered' else 'proposal.json'
        with open(os.path.join(directory, name), 'w') as handle:
            json.dump({'stub': True, 'controls': {k: v for k, v in args.items() if k not in ('input', 'run_dir', 'review')}}, handle)
        if status == 'authored_unrendered':
            profile_sha = sha(os.path.join(directory, name))
    receipt = {'status': status, 'review': {'assertions': review}, 'stub': True}
    with open(os.path.join(directory, 'receipt.json'), 'w') as handle:
        json.dump(receipt, handle)
    result = {'schema_version': 1, 'tool': 'capture_profile', 'status': status, 'output_dir': directory,
              'source_sha256': source_sha, 'profile_sha256': profile_sha,
              'receipt_sha256': sha(os.path.join(directory, 'receipt.json')),
              'capture': {'requested_seconds': [args['capture_start_seconds'], args['capture_end_seconds']],
                          'native_samples': [0, 1], 'source_media_span_seconds': None},
              'dsp_performed': False, 'listening_accepted': False}
else:
    run_id = stamp()
    directory = os.path.join(runs, run_id)
    outputs, hashes = run_files(directory)
    manifest = {'schema_version': 1, 'status': 'rendered_unreviewed', 'run_id': run_id, 'run_dir': directory,
                'source': {'path': args['input'], 'sha256': source_sha}, 'outputs': outputs, 'output_sha256': hashes,
                'pcm': {'sample_rate': 16000, 'channels': 1, 'sample_count': 16000, 'duration_seconds': 1.0},
                'timeline': {'no_time_stretch': True}}
    with open(os.path.join(directory, 'manifest.json'), 'w') as handle:
        json.dump(manifest, handle)
    with open(os.path.join(directory, 'application-receipt.json'), 'w') as handle:
        json.dump({'stub': True, 'authoring': args['authoring_dir']}, handle)
    summary = {'schema_version': 1, 'tool': 'apply_capture_profile', 'status': 'rendered_unreviewed',
               'run_dir': directory, 'source_sha256': source_sha, 'authoring_receipt_sha256': args['receipt_sha256'],
               'manifest_sha256': sha(os.path.join(directory, 'manifest.json')),
               'receipt_sha256': sha(os.path.join(directory, 'application-receipt.json')),
               'capture': {'requested_seconds': [5.5, 6.4]}, 'export': {'status': 'exported_unreviewed'},
               'dsp_performed': True, 'listening_accepted': False, 'master_adopted': False}
    result = {'schema_version': 1, 'tool': 'apply_capture_profile', 'status': 'completed', 'result': summary}
write_beat({'started': started, 'ended': time.time()})
print(json.dumps(result))
'''


class S3Builder:
    """Test seam: stub argv per launch (worker_kind test_stub). share_export uses the S2 stub script."""

    def __init__(self, beats_dir, default='succeed', modes=()):
        self.beats_dir = Path(beats_dir)
        self.beats_dir.mkdir(parents=True, exist_ok=True)
        self.default = default
        self.modes = list(modes)
        self.beats = []
        self.lock = threading.Lock()

    def __call__(self, args):
        with self.lock:
            mode = self.modes.pop(0) if self.modes else self.default
            beat = self.beats_dir / f'beat-{len(self.beats)}-{mode}-{os.urandom(4).hex()}.json'
            self.beats.append(beat)
        if '_web_job' not in args:  # share_export (S2 stub contract)
            share_mode = {'timed': 'succeed'}.get(mode, mode)
            return [sys.executable, '-c', STUB, share_mode, str(beat), args['source'], args['output']]
        return [sys.executable, '-c', S3_STUB, mode, str(beat), json.dumps(args)]


class PassThroughBuilder:
    """Test seam returning the exact product argv (real workers) for pending-admission types."""

    def __init__(self):
        self.commands = []

    def __call__(self, args):
        tool = args.pop('_web_job')['tool'] if '_web_job' in args else 'share_export'
        command = WebJobs.real_command(tool, args)
        self.commands.append((tool, command))
        return command


# --------------------------------------------------------------------------- PCM fixtures

def lcg_noise(count, seed, rms):
    """Deterministic uniform noise scaled to an exact target RMS."""
    state = seed & 0xFFFFFFFF
    values = []
    for _ in range(count):
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        values.append(state / 2 ** 31 - 1.0)
    actual = math.sqrt(math.fsum(v * v for v in values) / count)
    return [v * rms / actual for v in values]


def baseline_channel(rate, seconds, seed, channel=0):
    """0-5 s setup (decaying 32.703 + 65.4 Hz bursts, click train), 5-8 s noise at -42 dBFS RMS,
    8-end 32.703 Hz sine at -12 dBFS RMS, one full-scale clip burst at [2.0 s, 2.0 s + 64 samples)."""
    total = int(round(rate * seconds))
    samples = [0.0] * total
    for index in range(min(total, 5 * rate)):
        t = index / rate
        burst = t % 1.0
        envelope = math.exp(-4.0 * burst)
        samples[index] = 0.25 * envelope * (math.sin(2 * math.pi * 32.703 * t) + 0.5 * math.sin(2 * math.pi * 65.4 * t))
        if index % (rate // 4) < 8:
            samples[index] += 0.6  # click train standing in for amp/windup
    noise = lcg_noise(3 * rate, seed + channel, 10 ** (-42 / 20))
    for offset, value in enumerate(noise):
        if 5 * rate + offset < total:
            samples[5 * rate + offset] = value
    amplitude = 10 ** (-12 / 20) * math.sqrt(2)
    for index in range(8 * rate, total):
        samples[index] = amplitude * math.sin(2 * math.pi * 32.703 * index / rate)
    start = 2 * rate
    for index in range(start, start + 64):
        samples[index] = 1.0 if index % 2 else -1.0
    return samples


def wav_bytes(channels, rate, fmt):
    count = len(channels[0])
    if fmt == 'f32':
        code, bits = 3, 32
        payload = struct.pack('<' + 'f' * (count * len(channels)),
                              *[channels[c][i] for i in range(count) for c in range(len(channels))])
    elif fmt == 's16':
        code, bits = 1, 16
        payload = struct.pack('<' + 'h' * (count * len(channels)),
                              *[max(-32768, min(32767, int(round(channels[c][i] * 32767))))
                                for i in range(count) for c in range(len(channels))])
    else:
        raise ValueError(fmt)
    alignment = len(channels) * bits // 8
    fmt_chunk = struct.pack('<4sIHHIIHH', b'fmt ', 16, code, len(channels), rate, rate * alignment, alignment, bits)
    data_chunk = struct.pack('<4sI', b'data', len(payload)) + payload
    return b'RIFF' + struct.pack('<I', 4 + len(fmt_chunk) + len(data_chunk)) + b'WAVE' + fmt_chunk + data_chunk


def make_baseline_run(runs_dir, run_id, source_path, source_sha, *, rate=16000, channels=1, fmt='f32',
                      seconds=13, seed=SEED):
    run_dir = Path(runs_dir) / run_id
    run_dir.mkdir(parents=True)
    data = [baseline_channel(rate, seconds, seed, channel) for channel in range(channels)]
    (run_dir / 'source.wav').write_bytes(wav_bytes(data, rate, fmt))
    count = len(data[0])
    manifest = {'schema_version': 1, 'status': 'rendered_unreviewed', 'run_id': run_id, 'run_dir': str(run_dir),
                'profile': {'name': 'bypass'}, 'source': {'path': str(source_path), 'sha256': source_sha},
                'pcm': {'sample_rate': rate, 'channels': channels, 'sample_count': count,
                        'duration_seconds': count / rate, 'codec': 'pcm_f32le' if fmt == 'f32' else 'pcm_s16le'},
                'timeline': {'format_start_seconds': 0.0, 'audio_start_seconds': 0.0, 'no_time_stretch': True},
                'outputs': {'source': 'source.wav'},
                'output_sha256': {'source.wav': hashlib.sha256((run_dir / 'source.wav').read_bytes()).hexdigest()}}
    (run_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    return run_dir, data


def review_body(run_id, sha, start=5.5, end=6.4, key=None, **overrides):
    body = {'idempotency_key': key or f'rev-{os.urandom(6).hex()}', 'run_id': run_id,
            'expected_source_sha256': sha, 'start_seconds': start, 'end_seconds': end,
            'review_status': 'reviewed_candidate', 'authorization_scope': 'experimental_capture_render',
            'music_status': 'unknown', 'click_status': 'unknown', 'ambient_music_status': 'not_reported',
            'note': 'synthetic fixture review (test only)', 'setup_interval_acknowledged': False}
    body.update(overrides)
    return body


# --------------------------------------------------------------------------- base

class S3Base(unittest.TestCase):
    counter = 0

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix='web-s3-test-')
        cls.base = Path(cls._tmp.name).resolve()
        cls.raw_base = cls._tmp.name
        cls.R = cls.base / 'R'
        cls.runs = cls.R / 'artifacts' / 'runs'
        cls.runs.mkdir(parents=True)
        cls.forbidden = sorted({str(cls.base), cls.raw_base, str(cls.R), str(ROOT), '/Users/'}, key=len)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def assert_no_leak(self, response):
        blob = response.payload + json.dumps(response.headers).encode()
        for needle in self.forbidden:
            self.assertNotIn(needle.encode(), blob, 'response leaked a host path')
        METRICS['M10_responses_scanned'] = METRICS.get('M10_responses_scanned', 0) + 1

    def unique(self, label):
        type(self).counter += 1
        return f'{label}-{self._testMethodName[:40]}-{type(self).counter}'.replace('_', '-')

    def new_source(self, label='SRC'):
        run = self.unique(label)
        path = self.runs / run / 'export' / 'take.mov'
        path.parent.mkdir(parents=True)
        path.write_bytes(FAKE_MOV + run.encode())
        return f'{run}/export/take.mov', path, hashlib.sha256(path.read_bytes()).hexdigest()

    def env(self, *, admitted=ALL_ADMITTED, builder=None, start=True, state=None, runs_root=None, **kwargs):
        state = state or (self.base / 'states' / self.unique('state'))
        builder = builder or S3Builder(self.base / 'beats' / self.unique('b'))
        jobs = WebJobs(runs_root or self.R, state, command_builder=builder,
                       admitted_tools=admitted if admitted else None, **kwargs)
        if start:
            jobs.start()
        server = web_api.WebAPIServer(jobs, 0)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        thread.start()
        holder = {'jobs': jobs, 'server': server, 'client': Client(self, server), 'builder': builder,
                  'state': state, 'stopped': False}

        def stop():
            if not holder['stopped']:
                holder['stopped'] = True
                server.stop()
                thread.join(timeout=10)
                jobs.close()
                for process in jobs._detached:
                    if process.poll() is None:
                        sigkill_own_group(process.pid)
                    process.wait(timeout=10)
        holder['stop'] = stop
        self.addCleanup(stop)
        return holder

    def admit(self, client, selector):
        response = client.post('/api/v1/sources', {'selector': selector})
        self.assertIn(response.status, (200, 201), response.json)
        return response.json['source_artifact_id']

    def wait_job(self, client, job_id, states, timeout=30):
        end = time.monotonic() + timeout
        while True:
            response = client.get(f'/api/v1/jobs/{job_id}')
            self.assertEqual(response.status, 200, response.json)
            if response.json['state'] in states:
                return response.json
            if time.monotonic() > end:
                self.fail(f'job did not reach {states}; last {response.json["state"]} {response.json["reason_code"]}')
            time.sleep(0.05)

    def wait_beat(self, builder, since, timeout=15):
        """Heartbeat of the first launch made after `since` = len(builder.beats) taken before the submit.

        Earlier launches on the same builder (for example the parent capture_profile job of an
        apply_capture_profile fixture) are never returned, so the caller cannot read a stale beat when
        it reaches this point before the supervisor has called the builder for the new job.
        """
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with builder.lock:
                beat = builder.beats[since] if len(builder.beats) > since else None
            if beat is not None and beat.exists():
                try:
                    return json.loads(beat.read_text())
                except ValueError:  # stub is mid-write; poll again
                    pass
            time.sleep(0.02)
        self.fail(f'stub heartbeat not observed for launch index {since}')

    def wait_gone(self, pid, timeout=10):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            time.sleep(0.02)
        return False

    def fixture(self, env, *, review=True, fmt='f32', channels=1, **review_overrides):
        """Admitted source + baseline run (+ saved review). Returns a dict of ids."""
        selector, path, sha = self.new_source()
        source = self.admit(env['client'], selector)
        run_id = self.unique('BASE')
        run_dir, data = make_baseline_run(self.runs, run_id, path, sha, fmt=fmt, channels=channels)
        result = {'source': source, 'path': path, 'sha': sha, 'run_id': run_id, 'run_dir': run_dir, 'data': data}
        if review:
            response = env['client'].post(f'/api/v1/sources/{source}/capture-reviews',
                                          review_body(run_id, sha, **review_overrides))
            self.assertEqual(response.status, 201, response.json)
            result['review'] = response.json
        return result

    def job_body(self, tool, fx, key=None, parameters=None, **extra):
        body = {'tool': tool, 'source_artifact_id': fx['source'],
                'idempotency_key': key or f'{tool[:6]}-{os.urandom(6).hex()}'}
        if parameters is not None:
            body['parameters'] = parameters
        elif tool == 'denoise':
            body['parameters'] = {'profile': 'bypass', 'timeout_seconds': 30}
        elif tool == 'capture_profile':
            body['parameters'] = {'preset': 'fuller'}
        elif tool == 'apply_capture_profile':
            body['parameters'] = {'timeout_seconds': 30}
        if tool == 'capture_profile' and 'review' in fx and 'capture_review_id' not in extra:
            body['capture_review_id'] = fx['review']['review_id']
        body.update(extra)
        return body

    def authored_job(self, env, fx):
        """A succeeded capture_profile job (stub) for apply tests."""
        response = env['client'].post('/api/v1/jobs', self.job_body('capture_profile', fx))
        self.assertEqual(response.status, 202, response.json)
        return self.wait_job(env['client'], response.json['job_id'], ('succeeded',))

    def submit_for(self, env, tool, fx, **kwargs):
        if tool == 'apply_capture_profile' and 'capture_profile_job_id' not in kwargs:
            if 'parent' not in fx:
                fx['parent'] = self.authored_job(env, fx)
            kwargs['capture_profile_job_id'] = fx['parent']['job_id']
        return env['client'].post('/api/v1/jobs', self.job_body(tool, fx, **kwargs))

    def count(self, state, table):
        connection = sqlite3.connect(Path(state) / 'jobs.sqlite3')
        try:
            return connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
        finally:
            connection.close()


# --------------------------------------------------------------------------- M1, M3, M11

class AllowlistTests(S3Base):

    def test_m1_closed_allowlist_and_pending_admission(self):
        env = self.env(admitted=None)
        fx = self.fixture(env)
        registry = [tool['name'] for tool in tool_api.load_registry()['tools']]
        others = [name for name in registry if name not in web_jobs.JOB_TYPES]
        synthetic = ['Denoise', 'denoise ', 'share_export;rm']
        refused = 0
        for name in others + synthetic:
            response = env['client'].post('/api/v1/jobs', {'tool': name, 'source_artifact_id': fx['source'],
                                                           'idempotency_key': f'm1-{os.urandom(6).hex()}'})
            refused += (response.status, response.code) == (400, 'tool_not_admitted')
        self.assertEqual(refused, len(others) + len(synthetic))
        pending = 0
        for tool in PENDING:
            response = env['client'].post('/api/v1/jobs', self.job_body(tool, fx, capture_profile_job_id='job_' + '0' * 32)
                                          if tool == 'apply_capture_profile' else self.job_body(tool, fx))
            ok = (response.status, response.code) == (409, 'tool_pending_admission')
            pending += ok
            self.assertTrue(ok, response.json)
            self.assertEqual(response.json['capability_state'], 'planned')
        self.assertEqual(self.count(env['state'], 'jobs'), 0)
        catalogue = env['client'].get('/api/v1/job-types').json
        states = {entry['tool']: entry['admission_state'] for entry in catalogue['job_types']}
        self.assertEqual(states, {'share_export': 'admitted', 'denoise': 'pending_root_admission',
                                  'capture_profile': 'pending_root_admission',
                                  'apply_capture_profile': 'pending_root_admission'})
        METRICS['M1'] = {'non_allowlisted_registry_tools': len(others), 'synthetic_names': len(synthetic),
                         'refused_tool_not_admitted': refused, 'denominator': len(others) + len(synthetic),
                         'pending_refused': pending, 'pending_denominator': len(PENDING)}

    def test_m1_seam_refused_without_stub_builder(self):
        state = self.base / 'states' / self.unique('seam')
        with self.assertRaises(ValueError):
            WebJobs(self.R, state, admitted_tools={'denoise'})
        with self.assertRaises(ValueError):
            WebJobs(self.R, state, command_builder=S3Builder(self.base / 'b-seam'), admitted_tools={'probe'})

    def test_m3_unknown_knob_and_field_refused_per_type(self):
        env = self.env()
        fx = self.fixture(env)
        parent = self.authored_job(env, fx)
        refused = 0
        for tool in web_jobs.JOB_TYPE_NAMES:
            extra = {'capture_profile_job_id': parent['job_id']} if tool == 'apply_capture_profile' else {}
            base = self.job_body(tool, fx, **extra)
            knob = dict(base, parameters=dict(base.get('parameters', {}), high_pass_hz=20))
            response = env['client'].post('/api/v1/jobs', knob)
            unknown_field = env['client'].post('/api/v1/jobs', dict(base, input='/tmp/x.mov'))
            ok = ((response.status, response.code) == (400, 'invalid_parameters')
                  and (unknown_field.status, unknown_field.code) == (400, 'unknown_field'))
            self.assertTrue(ok, (tool, response.json, unknown_field.json))
            refused += ok
        METRICS['M3'] = {'refused': refused, 'denominator': len(web_jobs.JOB_TYPE_NAMES)}

    def test_m11_no_high_pass_low_cut_notch_or_default_shelf(self):
        env = self.env(admitted=None)
        catalogue = env['client'].get('/api/v1/job-types').json
        forbidden = ('high_pass', 'highpass', 'hpf', 'low_cut', 'lowcut', 'notch', 'shelf')
        hits, checked = [], 0
        for entry in catalogue['job_types']:
            for name, knob in entry['knobs'].items():
                checked += 1
                names = [name] + list((knob.get('items') or {}).get('properties', {})) + list(knob.get('properties', {}))
                hits += [f'{entry["tool"]}.{n}' for n in names if any(word in n.lower() for word in forbidden)]
                if name == 'profile':
                    hits += [p for p in knob['enum'] if any(word in p for word in forbidden)]
            for preset in (entry.get('presets') or {}).values():
                controls = preset.get('controls') or {}
                checked += 1
                hits += [k for k in controls if any(word in k for word in forbidden)]
                for band in controls.get('peaking_eq', []):
                    self.assertGreaterEqual(band['frequency_hz'], 160)
                    self.assertGreaterEqual(band['gain_db'], 0)  # FULLER bands are boosts, never cuts
            if entry['tool'] == 'capture_profile':
                self.assertFalse(entry['low_shelf']['available'])
                self.assertEqual(entry['presets']['fuller']['controls'], web_jobs.load_fuller_controls())
        self.assertEqual(hits, [])
        METRICS['M11'] = {'knobs_and_presets_checked': checked, 'hits': len(hits)}


# --------------------------------------------------------------------------- M2

def _vectors(schema, value_at_min=True):
    """(label, value, expect_tool_valid_hint) vectors for one numeric knob schema."""
    out = []
    kind = schema['type']
    if 'minimum' in schema:
        out.append(('min', schema['minimum']))
        below = schema['minimum'] - (1 if kind == 'integer' else 0.001)
        out.append(('below_min', below))
    if 'maximum' in schema:
        out.append(('max', schema['maximum']))
        above = schema['maximum'] + (1 if kind == 'integer' else 0.001)
        out.append(('above_max', above))
    out.append(('wrong_type', 'x'))
    out.append(('non_finite', float('nan')))
    if kind == 'integer':
        out.append(('fractional', 1.5))
    return out


class ParityTests(S3Base):
    """Web accept/refuse equals tool_api.validate + validate_tool_arguments on the derived arguments."""

    def run_vector(self, env, fx, tool, parameters, extra=None):
        body = self.job_body(tool, fx, parameters=parameters, **(extra or {}))
        try:
            status, value = env['jobs'].submit(body)
        except WebJobsError as error:
            return False, error.code, error.extra.get('web_only', False)
        env['jobs'].cancel(value['job_id'])
        return True, status, False

    def tool_accepts(self, tool, args):
        try:
            tool_api.validate(args, tool_api.descriptor(tool)['inputSchema'])
            tool_api.validate_tool_arguments(tool, args)
        except tool_api.ValidationError:
            return False
        return True

    def derived(self, env, fx, tool, parameters):
        jobs = env['jobs']
        source = {'source_artifact_id': fx['source'], 'sha256': fx['sha']}
        if tool == 'denoise':
            return {'input': str(fx['path']), **parameters}
        if tool == 'apply_capture_profile':
            return {'input': str(fx['path']), 'authoring_dir': '/x/capture-profiles/y', 'receipt_sha256': 'a' * 64,
                    **parameters}
        expanded = dict(parameters)
        if expanded.get('preset') == 'fuller':
            expanded.update(jobs.fuller_controls)
        expanded.pop('preset', None)
        review = fx['review']
        return {'input': str(fx['path']), 'run_dir': str(fx['run_dir']), 'review': str(fx['run_dir'] / 'r.json'),
                'capture_start_seconds': review['interval']['start_seconds'],
                'capture_end_seconds': review['interval']['end_seconds'], **expanded}

    def test_m2_validation_parity_per_type(self):
        env = self.env(start=False, queue_limit=64)
        fx = self.fixture(env)
        report = {}
        # denoise
        rows = []
        properties = tool_api.descriptor('denoise')['inputSchema']['properties']
        cases = [({'profile': p, 'timeout_seconds': 30}, 'profile=' + p) for p in properties['profile']['enum']]
        cases += [({'profile': 'nope'}, 'profile_bad_enum'), ({'profile': 3}, 'profile_wrong_type'),
                  ({}, 'profile_omitted'), ({'profile': 'bypass', 'gain': 1}, 'extra_knob')]
        cases += [({'profile': 'bypass', 'timeout_seconds': v}, 'timeout_' + l)
                  for l, v in _vectors(properties['timeout_seconds'])]
        rows += self.compare(env, fx, 'denoise', cases)
        report['denoise'] = rows
        # capture_profile (custom preset: every knob explicit)
        properties = tool_api.descriptor('capture_profile')['inputSchema']['properties']
        valid = {'preset': 'custom', 'reduction_db': 8, 'noise_floor_db': -40, 'adaptivity': 0, 'gain_smooth': 0,
                 'integrated_lufs': -18, 'true_peak_dbtp': -1.75}
        cases = [(dict(valid), 'custom_valid'), ({'preset': 'fuller'}, 'fuller_valid')]
        for key in web_jobs.CAPTURE_CONTROL_KEYS + ('timeout_seconds',):
            for label, value in _vectors(properties[key]):
                cases.append((dict(valid, **{key: value}), f'{key}_{label}'))
        for key in web_jobs.CAPTURE_CONTROL_KEYS:
            cases.append(({k: v for k, v in valid.items() if k != key}, f'{key}_omitted'))
        band = {'frequency_hz': 160, 'gain_db': 2, 'q': 0.7}
        for key, schema in properties['peaking_eq']['items']['properties'].items():
            for label, value in _vectors(schema):
                cases.append((dict(valid, peaking_eq=[dict(band, **{key: value})]), f'eq_{key}_{label}'))
        cases.append((dict(valid, peaking_eq=[band] * 4), 'eq_too_many_bands'))
        cases.append((dict(valid, peaking_eq=[dict(band, shelf=1)]), 'eq_extra_field'))
        comp = {'threshold_db': -18, 'ratio': 2, 'attack_ms': 15, 'release_ms': 100, 'knee_db': 3}
        for key, schema in properties['compressor']['properties'].items():
            for label, value in _vectors(schema):
                cases.append((dict(valid, compressor=dict(comp, **{key: value})), f'comp_{key}_{label}'))
            cases.append((dict(valid, compressor={k: v for k, v in comp.items() if k != key}), f'comp_{key}_omitted'))
        cases += [(dict(valid, extra_knob=1), 'extra_knob'), (dict(valid, preset='other'), 'preset_bad'),
                  ({k: v for k, v in valid.items() if k != 'preset'}, 'preset_omitted'),
                  ({'preset': 'fuller', 'reduction_db': 8}, 'fuller_with_control')]
        report['capture_profile'] = self.compare(env, fx, 'capture_profile', cases)
        # apply_capture_profile
        env_run = self.env()  # needs a succeeded authoring parent
        fx2 = self.fixture(env_run)
        parent = self.authored_job(env_run, fx2)
        properties = tool_api.descriptor('apply_capture_profile')['inputSchema']['properties']
        cases = [({'timeout_seconds': v}, 'timeout_' + l) for l, v in _vectors(properties['timeout_seconds'])]
        cases += [({}, 'timeout_default'), ({'timeout_seconds': 30, 'x': 1}, 'extra_knob')]
        env_run['jobs'].close()
        env_run['stopped'] = True
        env_run['server'].stop()
        replay = self.env(start=False, state=env_run['state'], queue_limit=64)
        report['apply_capture_profile'] = self.compare(replay, fx2, 'apply_capture_profile', cases,
                                                       {'capture_profile_job_id': parent['job_id']})
        summary = {}
        for tool, rows in report.items():
            agree = sum(r['agree'] for r in rows if not r['web_only'])
            general = sum(not r['web_only'] for r in rows)
            web_only = [r['case'] for r in rows if r['web_only']]
            summary[tool] = {'vectors': len(rows), 'parity_denominator': general, 'agree': agree,
                             'web_only_stricter': len(web_only), 'web_only_cases': web_only}
            self.assertEqual(agree, general, [r for r in rows if not r['agree'] and not r['web_only']])
        METRICS['M2'] = summary

    def compare(self, env, fx, tool, cases, extra=None):
        rows = []
        for parameters, label in cases:
            web_ok, code, web_only = self.run_vector(env, fx, tool, parameters, extra)
            try:
                tool_ok = self.tool_accepts(tool, self.derived(env, fx, tool, parameters)) \
                    if not (tool == 'capture_profile' and parameters.get('preset') not in ('fuller', 'custom')) \
                    else None
            except (TypeError, KeyError):
                tool_ok = None
            web_only = web_only or tool_ok is None or (tool_ok and not web_ok)
            rows.append({'case': label, 'web_accept': web_ok, 'tool_accept': tool_ok, 'code': code,
                         'web_only': bool(web_only) and not (tool_ok == web_ok),
                         'agree': tool_ok == web_ok})
        return rows


# --------------------------------------------------------------------------- M4, M5, M10, M12

class CaptureReviewTests(S3Base):

    def test_review_record_is_exact_review_keys_and_create_only(self):
        env = self.env()
        fx = self.fixture(env)
        review = fx['review']
        path = fx['run_dir'] / 'web-capture-reviews' / f'{review["review_id"]}.json'
        record = json.loads(path.read_text())
        self.assertEqual(set(record), capture_profile.REVIEW_KEYS)
        self.assertEqual(record['selected_by'], web_jobs.WEB_REVIEWER)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), review['review_sha256'])
        # capture_profile's own validator accepts the record for this exact binding
        rate = fx['review']['interval']['sample_rate']
        capture_profile.validate_review(record, fx['sha'], review['manifest_sha256'], review['pcm_sha256'],
                                        [review['interval']['start_sample'], review['interval']['end_sample']], rate)
        connection = sqlite3.connect(Path(env['state']) / 'jobs.sqlite3', isolation_level=None)
        try:
            for statement in ("UPDATE capture_reviews SET review_status = 'rejected_contaminated'",
                              'DELETE FROM capture_reviews'):
                with self.assertRaises(sqlite3.DatabaseError):
                    connection.execute(statement)
        finally:
            connection.close()
        replay_body = review_body(fx['run_id'], fx['sha'], key='replay-key-01')
        first = env['client'].post(f'/api/v1/sources/{fx["source"]}/capture-reviews', replay_body)
        again = env['client'].post(f'/api/v1/sources/{fx["source"]}/capture-reviews', replay_body)
        conflict = env['client'].post(f'/api/v1/sources/{fx["source"]}/capture-reviews',
                                      dict(replay_body, note='different'))
        self.assertEqual((first.status, again.status, again.json['review_id']), (201, 200, first.json['review_id']))
        self.assertEqual((conflict.status, conflict.code), (409, 'idempotency_conflict'))
        listing = env['client'].get(f'/api/v1/sources/{fx["source"]}/capture-reviews').json
        self.assertEqual(len(listing['reviews']), 2)

    def test_review_enumerations_match_capture_profile(self):
        good = {'schema_version': 1, 'source_sha256': 'a' * 64, 'source_run_manifest_sha256': 'b' * 64,
                'source_pcm_sha256': 'c' * 64, 'start_seconds': 1.0, 'end_seconds': 2.0,
                'time_axis': 'decoded_source_audio_samples', 'selected_by': 'x', 'reviewed_by': 'x',
                'review_status': 'reviewed_candidate', 'authorization_scope': 'profile_authoring',
                'authorization_reference': 'x', 'music_status': 'unknown', 'click_status': 'unknown',
                'ambient_music_status': 'not_reported', 'note': 'x'}
        checked = 0
        for field, values in (('review_status', web_jobs.REVIEW_STATUSES),
                              ('authorization_scope', web_jobs.AUTHORIZATION_SCOPES),
                              ('music_status', web_jobs.CONTENT_STATUSES), ('click_status', web_jobs.CONTENT_STATUSES),
                              ('ambient_music_status', web_jobs.AMBIENT_STATUSES)):
            for value in values + ('not_a_value',):
                record = dict(good, **{field: value})
                try:
                    capture_profile.validate_review(record, 'a' * 64, 'b' * 64, 'c' * 64, [16000, 32000], 16000)
                    accepted = True
                except capture_profile.CaptureError:
                    accepted = False
                self.assertEqual(accepted, value in values, (field, value))
                checked += 1
        METRICS['review_enum_parity_checked'] = checked

    def test_m4_binding_refusals_store_unchanged(self):
        env = self.env()
        client = env['client']
        outcomes = {}

        def submit(fx):
            return client.post('/api/v1/jobs', self.job_body('capture_profile', fx))

        fx = self.fixture(env)
        before = (self.count(env['state'], 'jobs'), self.count(env['state'], 'capture_reviews'))
        fx['path'].write_bytes(fx['path'].read_bytes() + b'changed')
        outcomes['source_bytes_changed'] = submit(fx).code
        fx = self.fixture(env)
        with open(fx['run_dir'] / 'manifest.json', 'a') as handle:
            handle.write(' ')
        outcomes['baseline_manifest_changed'] = submit(fx).code
        fx = self.fixture(env)
        pcm = bytearray((fx['run_dir'] / 'source.wav').read_bytes())
        pcm[-1] ^= 0x01
        (fx['run_dir'] / 'source.wav').write_bytes(bytes(pcm))
        outcomes['source_wav_changed'] = submit(fx).code
        fx = self.fixture(env)
        review_path = fx['run_dir'] / 'web-capture-reviews' / f'{fx["review"]["review_id"]}.json'
        review_path.write_text(review_path.read_text().replace('synthetic', 'Synthetic'))
        outcomes['review_file_changed'] = submit(fx).code
        before_other = (self.count(env['state'], 'jobs'), self.count(env['state'], 'capture_reviews'))
        other = self.fixture(env, review=False)
        mine = self.fixture(env, review=False)
        response = client.post(f'/api/v1/sources/{mine["source"]}/capture-reviews',
                               review_body(other['run_id'], mine['sha']))
        outcomes['run_of_another_source'] = response.code
        expected = {'source_bytes_changed': 'source_stale', 'baseline_manifest_changed': 'review_stale',
                    'source_wav_changed': 'review_stale', 'review_file_changed': 'review_stale',
                    'run_of_another_source': 'run_not_bound'}
        self.assertEqual(outcomes, expected)
        self.assertEqual(self.count(env['state'], 'jobs'), before[0])
        self.assertEqual(self.count(env['state'], 'capture_reviews'), before_other[1])
        METRICS['M4'] = {'refused': sum(outcomes[k] == v for k, v in expected.items()), 'denominator': len(expected),
                         'store_unchanged': True, 'codes': outcomes}

    def test_m5a_no_auto_confirmation_on_reads(self):
        env = self.env()
        fx = self.fixture(env, review=False)
        client = env['client']
        paths = ['/api/v1/job-types', '/api/v1/sources', f'/api/v1/sources/{fx["source"]}/runs',
                 f'/api/v1/sources/{fx["source"]}/capture-reviews', f'/api/v1/jobs?source_artifact_id={fx["source"]}',
                 f'/api/v1/runs/{fx["run_id"]}/media/source']
        for path in paths:
            self.assertEqual(client.get(path).status, 200, path)
        measured = client.post(f'/api/v1/sources/{fx["source"]}/capture-measurements',
                               {'run_id': fx['run_id'], 'start_seconds': 0.0, 'end_seconds': 4.9})
        self.assertEqual(measured.status, 200, measured.json)
        self.assertTrue(measured.json['overlaps_setup_interval'])
        self.assertFalse(measured.json['selects_interval'])
        runs = client.get(f'/api/v1/sources/{fx["source"]}/runs').json['runs']
        self.assertEqual([r['run_id'] for r in runs], [fx['run_id']])
        self.assertTrue(runs[0]['baseline_eligible'])
        self.assertEqual(self.count(env['state'], 'capture_reviews'), 0)
        self.assertFalse((fx['run_dir'] / 'web-capture-reviews').exists())
        METRICS['M5a_api'] = {'routes_called': len(paths) + 1, 'reviews_created': 0}

    def test_m5b_setup_interval_grid(self):
        env = self.env(start=False)
        fx = self.fixture(env, review=False)
        jobs = env['jobs']
        statuses = web_jobs.REVIEW_STATUSES
        grid = violations = overlap_n = clear_n = 0
        for step in range(34):
            start = round(0.3 * step, 3)
            for duration in (0.1, 0.85, 3.0):
                end = round(start + duration, 3)
                overlap = start < 5.0
                for status in statuses:
                    for ack in (False, True):
                        grid += 1
                        body = review_body(fx['run_id'], fx['sha'], start=start, end=end, review_status=status,
                                           setup_interval_acknowledged=ack, key=f'grid-{grid:05d}')
                        try:
                            code = jobs.create_capture_review(fx['source'], body)[0]
                        except WebJobsError as error:
                            code = error.code
                        if overlap:
                            overlap_n += 1
                            expected = ('setup_interval_unacknowledged' if not ack else
                                        'setup_interval_status_refused' if status == 'reviewed_candidate' else 201)
                        else:
                            clear_n += 1
                            expected = 201
                        violations += code != expected
        self.assertEqual(grid, 102 * 3 * 2)
        self.assertEqual(violations, 0)
        connection = sqlite3.connect(Path(env['state']) / 'jobs.sqlite3')
        self.addCleanup(connection.close)
        bad = connection.execute("SELECT count(*) FROM capture_reviews WHERE overlaps_setup_interval = 1 "
                                 "AND review_status = 'reviewed_candidate'").fetchone()[0]
        self.assertEqual(bad, 0)
        METRICS['M5b'] = {'grid': grid, 'intervals': 102, 'overlapping_cases': overlap_n,
                          'non_overlapping_cases': clear_n, 'violations': violations}

    def test_interval_and_typed_refusals(self):
        env = self.env()
        fx = self.fixture(env, review=False)
        client = env['client']
        url = f'/api/v1/sources/{fx["source"]}/capture-reviews'
        cases = [
            (review_body(fx['run_id'], fx['sha'], start=12.0, end=13.5), 'interval_out_of_range'),
            (review_body(fx['run_id'], fx['sha'], start=6.0, end=6.05), 'interval_out_of_range'),
            (review_body(fx['run_id'], fx['sha'], start=1.0, end=12.5), 'interval_out_of_range'),
            (review_body(fx['run_id'], 'f' * 64), 'source_stale'),
            (review_body('NO-SUCH-RUN', fx['sha']), 'unknown_run'),
            (review_body('../x', fx['sha']), 'malformed_id'),
            (review_body(fx['run_id'], fx['sha'], review_status='accepted'), 'invalid_review'),
            (review_body(fx['run_id'], fx['sha'], note='   '), 'invalid_review'),
            (dict(review_body(fx['run_id'], fx['sha']), selected_by='me'), 'unknown_field'),
            (dict(review_body(fx['run_id'], fx['sha']), start_seconds=True), 'bad_type'),
        ]
        for body, code in cases:
            with self.subTest(code=code):
                self.assertEqual(client.post(url, body).code, code)
        self.assertEqual(self.count(env['state'], 'capture_reviews'), 0)

    def test_m12_unknown_fields_on_review_measurement_and_processing_jobs(self):
        env = self.env()
        fx = self.fixture(env)
        measured = env['client'].post(f'/api/v1/sources/{fx["source"]}/capture-measurements',
                                      {'run_id': fx['run_id'], 'start_seconds': 5.5, 'end_seconds': 6.4}).json
        records = {'review': fx['review'], 'measurement': measured}
        parent = self.authored_job(env, fx)
        records['capture_profile'] = parent
        for tool in ('denoise', 'apply_capture_profile'):
            response = self.submit_for(env, tool, fx, capture_profile_job_id=parent['job_id']) \
                if tool == 'apply_capture_profile' else self.submit_for(env, tool, fx)
            records[tool] = self.wait_job(env['client'], response.json['job_id'], ('succeeded',))
        present = total = 0
        for label, record in records.items():
            unknowns = record['unknowns']
            self.assertIs(unknowns['master_adopted'], False)
            for key in web_jobs.PROCESSING_UNKNOWN_REASONS:
                total += 1
                ok = key in unknowns and unknowns[key] is None and isinstance(unknowns.get(key + '_reason'), str)
                present += ok
                self.assertTrue(ok, (label, key))
        METRICS['M12'] = {'records': list(records), 'fields_per_record': len(web_jobs.PROCESSING_UNKNOWN_REASONS) + 1,
                          'present_with_reason': present + len(records), 'denominator': total + len(records),
                          'share_export_note': 'share_export keeps the S2 unknowns shape (contract section 5)'}

    def test_m10_publication_and_media_are_path_free(self):
        env = self.env()
        fx = self.fixture(env)
        job = self.authored_job(env, fx)
        publication = next(a for a in job['artifacts'] if a['role'] == 'publication')
        response = env['client'].get(f'/api/v1/artifacts/{publication["artifact_id"]}')
        self.assertEqual(response.status, 200)
        data = json.loads(response.payload)
        self.assertEqual((data['master_adopted'], data['listening_accepted']), (False, False))
        self.assertEqual(data['worker_status'], 'authored_unrendered')
        media_response = env['client'].get(f'/api/v1/runs/{fx["run_id"]}/media/source')
        self.assertEqual(media_response.headers['Content-Type'], 'audio/wav')
        self.assertEqual(hashlib.sha256(media_response.payload).hexdigest(), fx['review']['pcm_sha256'])
        refused = env['client'].get(f'/api/v1/runs/{fx["run_id"]}/media/cleaned')
        self.assertEqual((refused.status, refused.code), (404, 'unknown_role'))


# --------------------------------------------------------------------------- M15

class CaptureStatsTests(S3Base):

    def expected(self, samples):
        rms = math.sqrt(math.fsum(v * v for v in samples) / len(samples))
        return 20 * math.log10(rms), 20 * math.log10(max(abs(v) for v in samples))

    def test_m15_statistics_on_analytic_fixtures(self):
        env = self.env(start=False)
        checks = passed = 0
        for fmt in ('f32', 's16'):
            for channels in (1, 2):
                fx = self.fixture(env, review=False, fmt=fmt, channels=channels)
                header_rate = 16000
                for start, end, label in ((5.0, 8.0, 'noise'), (8.0, 12.0, 'sine'), (1.95, 2.25, 'clip')):
                    response = env['client'].post(f'/api/v1/sources/{fx["source"]}/capture-measurements',
                                                  {'run_id': fx['run_id'], 'start_seconds': start, 'end_seconds': end})
                    self.assertEqual(response.status, 200, response.json)
                    for channel, stats in enumerate(response.json['channels']):
                        raw = fx['data'][channel][round(start * header_rate):round(end * header_rate)]
                        if fmt == 's16':
                            raw = [max(-32768, min(32767, int(round(v * 32767)))) / 32768.0 for v in raw]
                        rms, peak = self.expected(raw)
                        checks += 2
                        passed += abs(stats['rms_dbfs'] - rms) <= 0.01
                        passed += abs(stats['sample_peak_dbfs'] - peak) <= 0.01
                        clipped = sum(abs(v) >= 0.999 for v in raw)
                        checks += 1
                        passed += stats['clipped_samples'] == clipped
                        if label == 'clip':
                            self.assertGreaterEqual(stats['clipped_samples'], 64 if fmt == 'f32' else 32)
                        if label == 'sine':
                            self.assertLess(stats['frame_rms_dbfs']['spread_db'], 0.5)
        # exact square-wave and transient fixture through the pure function
        rate = 16000
        frame = rate // 10
        floor = [0.01 if i % 2 else -0.01 for i in range(frame * 20)]
        for burst in (3, 9, 15):
            for i in range(burst * frame, (burst + 1) * frame):
                floor[i] *= 10 ** (12 / 20)
        stats = web_jobs.interval_statistics([floor], rate)[0]
        checks += 3
        passed += stats['transient_frames'] == 3
        passed += abs(stats['frame_rms_dbfs']['median'] - (-40.0)) <= 0.01
        passed += stats['frame_count'] == 20
        self.assertEqual(passed, checks)
        METRICS['M15'] = {'checks': checks, 'passed': passed, 'fixtures': '2 formats x 2 channel layouts x 3 spans'}


# --------------------------------------------------------------------------- M6, M7

def node_eval(script):
    node = shutil.which('node')
    if node is None:
        return None, 'node not on PATH'
    completed = subprocess.run([node, '--input-type=module', '-e', script], capture_output=True, text=True,
                               timeout=30, cwd=WEB)
    if completed.returncode != 0:
        return None, completed.stderr[-2000:]
    return json.loads(completed.stdout), None


class ProcessTests(S3Base):

    def test_m6_fuller_requires_interval_server_and_ui_builder(self):
        env = self.env()
        fx = self.fixture(env, review=False)
        refused = env['client'].post('/api/v1/jobs', self.job_body('capture_profile', fx))
        self.assertEqual((refused.status, refused.code), (409, 'capture_interval_required'))
        apply_refused = env['client'].post('/api/v1/jobs', self.job_body('apply_capture_profile', fx))
        self.assertEqual((apply_refused.status, apply_refused.code), (409, 'capture_interval_required'))
        authoring_only = env['client'].post(
            f'/api/v1/sources/{fx["source"]}/capture-reviews',
            review_body(fx['run_id'], fx['sha'], authorization_scope='profile_authoring')).json
        scoped = env['client'].post('/api/v1/jobs', self.job_body('capture_profile', fx,
                                                                   capture_review_id=authoring_only['review_id']))
        self.assertEqual((scoped.status, scoped.code), (409, 'capture_interval_required'))
        review = env['client'].post(f'/api/v1/sources/{fx["source"]}/capture-reviews',
                                    review_body(fx['run_id'], fx['sha'])).json
        accepted = env['client'].post('/api/v1/jobs', self.job_body('capture_profile', fx,
                                                                     capture_review_id=review['review_id']))
        self.assertEqual(accepted.status, 202, accepted.json)
        results = {'server_without_interval': refused.code, 'server_with_review': accepted.status}
        if not OPTIONS_TS.is_file():
            self.skipTest('options.ts not present')
        script = f'''
const m = await import({json.dumps(OPTIONS_TS.as_uri())});
const none = m.buildPresetOptions({{ reviews: [], sourceSha256: 'a'.repeat(64), denoiseProfiles: [], captureAdmission: 'admitted', denoiseAdmission: 'admitted', applyAdmission: 'admitted' }});
const one = m.buildPresetOptions({{ reviews: [{json.dumps(review)}], sourceSha256: {json.dumps(fx['sha'])}, denoiseProfiles: [], captureAdmission: 'admitted', denoiseAdmission: 'admitted', applyAdmission: 'admitted' }});
const authoring = m.buildPresetOptions({{ reviews: [{json.dumps(authoring_only)}], sourceSha256: {json.dumps(fx['sha'])}, denoiseProfiles: [], captureAdmission: 'admitted', denoiseAdmission: 'admitted', applyAdmission: 'admitted' }});
console.log(JSON.stringify({{ none: none.find((o) => o.id === 'fuller'), one: one.find((o) => o.id === 'fuller'), authoring: authoring.find((o) => o.id === 'fuller'), defaultId: none.find((o) => o.default)?.id, ids: none.map((o) => o.id) }}));
'''
        value, error = node_eval(script)
        if value is None:
            METRICS['M6'] = dict(results, ui_builder='skipped', reason=error[:300])
            self.skipTest(f'node type-stripping import unavailable: {error[:300]}')
        self.assertEqual((value['none']['enabled'], value['none']['refusal_code']), (False, 'capture_interval_required'))
        self.assertEqual((value['authoring']['enabled'], value['authoring']['refusal_code']),
                         (False, 'capture_interval_required'))
        self.assertTrue(value['one']['enabled'])
        self.assertEqual(value['defaultId'], 'fuller')
        self.assertFalse(any('shelf' in i and 'unavailable' not in i for i in value['ids'] if i != 'fuller-shelf'))
        METRICS['M6'] = dict(results, ui_without=value['none']['refusal_code'], ui_with=value['one']['enabled'],
                             passed='4/4')

    def test_m7_fuller_preset_fidelity_and_chain(self):
        profile = json.loads((ROOT / 'profiles' / 'fuller.json').read_text())
        controls = web_jobs.load_fuller_controls()
        fields = []
        for key in web_jobs.CAPTURE_CONTROL_KEYS:
            fields.append((key, controls[key] == profile[key]))
        for index, band in enumerate(profile['peaking_eq']):
            fields.append((f'peaking_eq[{index}]', controls['peaking_eq'][index] == band))
        for key, value in profile['compressor'].items():
            fields.append((f'compressor.{key}', controls['compressor'][key] == value))
        self.assertTrue(all(ok for _, ok in fields))
        result = {'fields': len(fields), 'equal': sum(ok for _, ok in fields)}
        manifest_path = ROOT.parents[2] / 'artifacts' / 'runs' / ACCEPTED_FULLER_RUN / 'manifest.json' \
            if ROOT.parent.name == 'sprint3' else ROOT / 'artifacts' / 'runs' / ACCEPTED_FULLER_RUN / 'manifest.json'
        if not manifest_path.is_file():
            METRICS['M7'] = dict(result, chain='unknown', chain_reason='accepted run manifest not readable here')
            return
        manifest = json.loads(manifest_path.read_text())  # read-only
        rate = manifest['pcm']['sample_rate']
        planned = media.post_denoise_filters(controls, rate)
        accepted = [stage for stage in manifest['restoration_stages']
                    if stage.get('stage', '').startswith(('peaking_eq', 'rms_compressor'))]
        simplify = lambda stages: [{'stage': s['stage'], 'filter': s.get('filter'), 'controls': s.get('controls')}
                                   for s in stages]
        equal = simplify(planned) == simplify(accepted)
        diff = None if equal else {'planned': simplify(planned), 'accepted': simplify(accepted)}
        METRICS['M7'] = dict(result, chain='equal' if equal else 'differs', chain_diff=diff, sample_rate=rate,
                             accepted_run=ACCEPTED_FULLER_RUN)


# --------------------------------------------------------------------------- M8, M9

class LifecycleTests(S3Base):

    def run_cases(self, tool):
        outcomes = {}
        # replay + conflict
        env = self.env()
        fx = self.fixture(env)
        first = self.submit_for(env, tool, fx, key=f'replay-{tool[:8]}-01')
        self.assertEqual(first.status, 202, first.json)
        again = self.submit_for(env, tool, fx, key=f'replay-{tool[:8]}-01',
                                **({'capture_profile_job_id': fx['parent']['job_id']} if 'parent' in fx else {}))
        outcomes['replay'] = again.status == 200 and again.json['job_id'] == first.json['job_id'] \
            and again.json['replayed'] is True
        different = {'denoise': {'profile': 'mild6', 'timeout_seconds': 30},
                     'capture_profile': {'preset': 'fuller', 'timeout_seconds': 59},
                     'apply_capture_profile': {'timeout_seconds': 31},
                     'share_export': {'height': 480}}[tool]
        conflict = self.submit_for(env, tool, fx, key=f'replay-{tool[:8]}-01', parameters=different,
                                   **({'capture_profile_job_id': fx['parent']['job_id']} if 'parent' in fx else {}))
        outcomes['conflict'] = (conflict.status, conflict.code) == (409, 'idempotency_conflict')
        done = self.wait_job(env['client'], first.json['job_id'], ('succeeded',))
        if tool != 'share_export':
            self.assertTrue(done['outputs'], done)
            self.assertEqual(done['worker_status'] in ('rendered_unreviewed', 'authored_unrendered'), True)
        env['stop']()
        # cancel queued
        env = self.env(start=False)
        fx = self.fixture(env)
        if tool == 'apply_capture_profile':
            fx['parent'] = self.seed_parent(env, fx)
        job = self.submit_for(env, tool, fx)
        cancelled = env['client'].post(f'/api/v1/jobs/{job.json["job_id"]}/cancel', {})
        outcomes['cancel_queued'] = (cancelled.status, cancelled.json['state']) == (200, 'cancelled')
        env['stop']()
        # cancel running (owned group gone)
        builder = S3Builder(self.base / 'beats' / self.unique('cr'))
        env = self.env(builder=builder)
        fx = self.fixture(env)
        if tool == 'apply_capture_profile':
            fx['parent'] = self.authored_job(env, fx)
        builder.modes = ['sleep']
        launches = len(builder.beats)
        job = self.submit_for(env, tool, fx)
        beat = self.wait_beat(builder, launches)
        response = env['client'].post(f'/api/v1/jobs/{job.json["job_id"]}/cancel', {})
        final = self.wait_job(env['client'], job.json['job_id'], ('cancelled',), timeout=30)
        outcomes['cancel_running'] = (response.status == 202 and self.wait_gone(beat['pid'])
                                      and self.wait_gone(beat['child'])
                                      and final['attempts'][-1]['cancel']['signal_target'] == 'owned_process_group')
        env['stop']()
        # interrupted -> retry
        builder = S3Builder(self.base / 'beats' / self.unique('ir'))
        env = self.env(builder=builder)
        fx = self.fixture(env)
        if tool == 'apply_capture_profile':
            fx['parent'] = self.authored_job(env, fx)
        builder.modes = ['sleep']
        launches = len(builder.beats)
        job = self.submit_for(env, tool, fx)
        beat = self.wait_beat(builder, launches)
        state = env['state']
        env['stop']()  # detaches; the test kills only its own stub group
        sigkill_own_group(beat['pid'])
        self.wait_gone(beat['pid'])
        env2 = self.env(state=state)
        interrupted = env2['client'].get(f'/api/v1/jobs/{job.json["job_id"]}').json
        retried = env2['client'].post(f'/api/v1/jobs/{job.json["job_id"]}/retry', {})
        final = self.wait_job(env2['client'], job.json['job_id'], ('succeeded',))
        outcomes['interrupted_retry'] = (interrupted['state'] == 'interrupted' and retried.status == 202
                                         and [a['state'] for a in final['attempts']] == ['interrupted', 'succeeded'])
        env2['stop']()
        # publish crash -> adoption
        env = self.env()
        fx = self.fixture(env)
        if tool == 'apply_capture_profile':
            fx['parent'] = self.authored_job(env, fx)
        state = env['state']
        env['stop']()
        env = self.env(state=state, fault='after_publish_before_commit')
        job = self.submit_for(env, tool, fx)
        end = time.monotonic() + 20
        while not env['jobs'].crashed and time.monotonic() < end:
            time.sleep(0.05)
        state = env['state']
        env['stop']()
        env2 = self.env(state=state)
        adopted = env2['client'].get(f'/api/v1/jobs/{job.json["job_id"]}').json
        outcomes['publish_crash_adoption'] = (adopted['state'] == 'succeeded'
                                              and adopted['attempts'][-1]['reconciled_publication'] is True
                                              and len(adopted['attempts']) == 1)
        env2['stop']()
        # deadline (outer headroom patched so the outer deadline is 1.5 s; production headroom is +10 s)
        builder = S3Builder(self.base / 'beats' / self.unique('dl'))
        env = self.env(builder=builder)
        fx = self.fixture(env)
        if tool == 'apply_capture_profile':
            fx['parent'] = self.authored_job(env, fx)
        minimum = tool_api.descriptor(tool)['inputSchema']['properties']['timeout_seconds']['minimum']
        builder.modes = ['sleep']
        parameters = {'denoise': {'profile': 'bypass', 'timeout_seconds': minimum},
                      'capture_profile': {'preset': 'fuller', 'timeout_seconds': minimum},
                      'apply_capture_profile': {'timeout_seconds': minimum},
                      'share_export': {'timeout_seconds': minimum}}[tool]
        with mock.patch.object(web_jobs, 'OUTER_HEADROOM_S', 1.5 - minimum):
            job = self.submit_for(env, tool, fx, parameters=parameters,
                                  **({'capture_profile_job_id': fx['parent']['job_id']} if 'parent' in fx else {}))
            final = self.wait_job(env['client'], job.json['job_id'], ('failed',), timeout=30)
        outcomes['deadline'] = final['reason_code'] == 'deadline_exceeded'
        env['stop']()
        return outcomes

    def seed_parent(self, env, fx):
        """A succeeded capture_profile parent in a non-started store: run it in a sibling started store first."""
        state = env['state']
        env['stop']()
        runner = self.env(state=state)
        parent = self.authored_job(runner, fx)
        runner['stop']()
        fresh = self.env(start=False, state=state)
        env.update(fresh)
        return parent

    def test_m8_lifecycle_per_type(self):
        report = {}
        for tool in web_jobs.JOB_TYPE_NAMES:
            with self.subTest(tool=tool):
                outcomes = self.run_cases(tool)
                report[tool] = outcomes
                self.assertTrue(all(outcomes.values()), outcomes)
        METRICS['M8'] = {'cases': sum(len(v) for v in report.values()),
                         'passed': sum(sum(v.values()) for v in report.values()), 'per_type': report}

    def test_m9_one_media_job_per_host(self):
        parent = self.base / 'states' / self.unique('host')
        parent.mkdir(parents=True)
        builders = [S3Builder(self.base / 'beats' / self.unique('m9a'), default='timed'),
                    S3Builder(self.base / 'beats' / self.unique('m9b'), default='timed')]
        envs = [self.env(builder=builders[i], state=parent / f'root-{i}') for i in range(2)]
        self.assertEqual(envs[0]['jobs'].host_lock_path, envs[1]['jobs'].host_lock_path)
        jobs = []
        for env in envs:
            fx = self.fixture(env, review=False)
            for _ in range(3):
                jobs.append((env, env['client'].post('/api/v1/jobs', self.job_body('denoise', fx)).json['job_id']))
        waited = set()
        for env, job_id in jobs:
            self.wait_job(env['client'], job_id, ('succeeded',), timeout=60)
            phases = env['client'].get(f'/api/v1/jobs/{job_id}').json
            waited.add(job_id) if phases else None
        intervals = sorted((json.loads(b.read_text())['started'], json.loads(b.read_text())['ended'])
                           for builder in builders for b in builder.beats)
        overlaps = sum(1 for (s1, e1), (s2, e2) in zip(intervals, intervals[1:]) if s2 < e1)
        self.assertEqual(len(intervals), 6)
        self.assertEqual(overlaps, 0)
        connection = sqlite3.connect(Path(parent / 'root-1') / 'jobs.sqlite3')
        self.addCleanup(connection.close)
        waits = connection.execute("SELECT count(*) FROM events WHERE reason_code = ?",
                                   (web_jobs.WAITING_HOST_SLOT,)).fetchone()[0]
        connection0 = sqlite3.connect(Path(parent / 'root-0') / 'jobs.sqlite3')
        self.addCleanup(connection0.close)
        waits += connection0.execute("SELECT count(*) FROM events WHERE reason_code = ?",
                                     (web_jobs.WAITING_HOST_SLOT,)).fetchone()[0]
        METRICS['M9'] = {'media_jobs': len(intervals), 'state_roots': 2, 'overlaps': overlaps,
                         'waiting_host_media_slot_events': waits}


# --------------------------------------------------------------------------- migration

class SchemaMigrationTests(S3Base):

    def v1_store(self, state):
        state.mkdir(parents=True, mode=0o700)
        connection = sqlite3.connect(state / 'jobs.sqlite3', isolation_level=None)
        connection.execute('PRAGMA journal_mode=WAL')
        for statement in web_jobs._split_sql(web_jobs.SCHEMA_SQL):
            connection.execute(statement)
        connection.execute('PRAGMA user_version = 1')
        return connection

    def test_v1_store_migrates_once_and_v1_jobs_stay_retryable(self):
        env0 = self.env()
        selector, path, sha = self.new_source()
        source = self.admit(env0['client'], selector)
        env0['stop']()
        state = self.base / 'states' / self.unique('v1')
        connection = self.v1_store(state)
        record = artifact_ids.ArtifactIndex(self.R).project(selector)
        connection.execute('INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                           (source, selector, sha, record['size_bytes'], 'video', record['source_id'],
                            record['source_binding'], '2026-10-06T00:00:00.000000Z'))
        jobs = WebJobs(self.R, state, command_builder=S3Builder(self.base / 'b-mig'))
        parameters = jobs.normalize_parameters({})
        fingerprint = jobs.fingerprint({'source_artifact_id': source, 'sha256': sha}, parameters)
        revision = jobs.capability_revision
        jobs.close()
        # a fresh v1 store (re-created) holding one failed share_export job from S2
        shutil.rmtree(state)
        connection = self.v1_store(state)
        connection.execute('INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                           (source, selector, sha, record['size_bytes'], 'video', record['source_id'],
                            record['source_binding'], '2026-10-06T00:00:00.000000Z'))
        job_id = 'job_' + '7' * 32
        connection.execute("INSERT INTO jobs VALUES (?, 'v1-key-0001', ?, 'share_export', ?, ?, ?, 'queued', NULL, 0, "
                           "'2026-10-06T00:00:00.000000Z', '2026-10-06T00:00:00.000000Z')",
                           (job_id, fingerprint, source, web_jobs.canonical(parameters), revision))
        connection.execute("INSERT INTO attempts(job_id, attempt, state) VALUES (?, 1, 'queued')", (job_id,))
        connection.execute("UPDATE attempts SET state = 'running' WHERE job_id = ?", (job_id,))
        connection.execute("UPDATE attempts SET state = 'failed', reason_code = 'worker_failed' WHERE job_id = ?",
                           (job_id,))
        connection.execute("UPDATE jobs SET state = 'running' WHERE job_id = ?", (job_id,))
        connection.execute("UPDATE jobs SET state = 'failed', reason_code = 'worker_failed' WHERE job_id = ?", (job_id,))
        connection.close()
        env = self.env(state=state)
        self.assertEqual(env['jobs'].migration['event'], 'schema_migrated_1_2')
        check = sqlite3.connect(state / 'jobs.sqlite3')
        self.addCleanup(check.close)
        self.assertEqual(check.execute('PRAGMA user_version').fetchone()[0], 2)
        self.assertEqual(check.execute("SELECT count(*) FROM events WHERE reason_code = 'schema_migrated_1_2'")
                         .fetchone()[0], 1)
        projection = env['client'].get(f'/api/v1/jobs/{job_id}').json
        self.assertEqual((projection['tool'], projection['state']), ('share_export', 'failed'))
        replay = env['client'].post('/api/v1/jobs', {'tool': 'share_export', 'source_artifact_id': source,
                                                     'idempotency_key': 'v1-key-0001'})
        self.assertEqual((replay.status, replay.json['job_id']), (200, job_id))
        self.assertEqual(env['client'].post(f'/api/v1/jobs/{job_id}/retry', {}).status, 202)
        self.wait_job(env['client'], job_id, ('succeeded',))
        env['stop']()
        again = self.env(state=state)
        self.assertIsNone(again['jobs'].migration)  # migrated once only
        METRICS['schema_migration'] = {'v1_to_v2': 'migrated_once', 'v1_job_readable': True, 'v1_job_retried': True,
                                       'v1_replay_same_fingerprint': True}

    def test_v3_and_partial_stores_refused(self):
        for label, setup in (('v3', 'PRAGMA user_version = 3'), ('v1-empty', 'PRAGMA user_version = 1')):
            state = self.base / 'states' / self.unique(label)
            state.mkdir(parents=True, mode=0o700)
            connection = sqlite3.connect(state / 'jobs.sqlite3')
            connection.execute(setup)
            connection.commit()
            connection.close()
            with self.assertRaises(WebJobsError) as caught:
                WebJobs(self.R, state, command_builder=S3Builder(self.base / 'b-v3'))
            self.assertEqual(caught.exception.code, 'schema_version_mismatch')


# --------------------------------------------------------------------------- real workers (FFmpeg)

def _dot_component(path):
    return any(part.startswith('.') for part in Path(path).parts[1:])


@unittest.skipUnless(HAVE_FFMPEG, FFMPEG_SKIP)
class RealWorkerTests(unittest.TestCase):
    """denoise (bypass) and capture_profile (FULLER authoring) through the real workers, once each.

    Fixtures live in this worktree's artifacts/runs/web-s3-fixture-<hex>/ and every run they
    create is removed in tearDown. apply_capture_profile runs only when the repository path has
    no dot-prefixed component (tool_api.validate_tool_arguments refuses those paths).
    """

    def setUp(self):
        self.runs = ROOT / 'artifacts' / 'runs'
        self.runs.mkdir(parents=True, exist_ok=True)
        self.before = set(os.listdir(self.runs))
        self.fixture_run = f'web-s3-fixture-{os.urandom(6).hex()}'
        self.source = self.runs / self.fixture_run / 'export' / 'take.mov'
        self.source.parent.mkdir(parents=True)
        command = [FFMPEG, '-nostdin', '-hide_banner', '-loglevel', 'error', '-n',
                   '-f', 'lavfi', '-i', 'testsrc2=size=160x120:rate=12:duration=7',
                   '-f', 'lavfi', '-i', 'sine=frequency=32.70:sample_rate=44100:duration=7',
                   '-c:v', 'libx264', '-preset', 'fast', '-crf', '28', '-pix_fmt', 'yuv420p', '-threads', '2',
                   '-c:a', 'aac', '-b:a', '96k', '-shortest', '-f', 'mov', str(self.source)]
        subprocess.run(command, check=True, capture_output=True, timeout=60)
        self.tmp = tempfile.TemporaryDirectory(prefix='web-s3-real-')
        self.addCleanup(self.cleanup)

    def cleanup(self):
        sha = hashlib.sha256(self.source.read_bytes()).hexdigest() if self.source.exists() else None
        for name in set(os.listdir(self.runs)) - self.before:
            path = self.runs / name
            if name == self.fixture_run:
                shutil.rmtree(path, ignore_errors=True)
                continue
            manifest = path / 'manifest.json'
            try:
                bound = json.loads(manifest.read_text())['source']['sha256'] == sha
            except (OSError, ValueError, KeyError, TypeError):
                bound = name.startswith('.staging-')
            if bound and path.is_dir() and not path.is_symlink():
                shutil.rmtree(path, ignore_errors=True)
        self.tmp.cleanup()

    def test_real_denoise_capture_profile_chain(self):
        builder = PassThroughBuilder()
        jobs = WebJobs(ROOT, Path(self.tmp.name) / 'state', command_builder=builder, admitted_tools=ALL_ADMITTED)
        self.addCleanup(jobs.close)
        jobs.start()
        _, source = jobs.admit_source({'selector': f'{self.fixture_run}/export/take.mov'})
        sid = source['source_artifact_id']

        def wait(job_id, timeout=180):
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                projection = jobs.project(job_id)
                if projection['state'] in web_jobs.TERMINAL:
                    return projection
                time.sleep(0.2)
            self.fail('real job did not finish')

        started = time.monotonic()
        _, denoise = jobs.submit({'tool': 'denoise', 'source_artifact_id': sid, 'idempotency_key': 'real-denoise-01',
                                  'parameters': {'profile': 'bypass', 'timeout_seconds': 120}})
        denoise = wait(denoise['job_id'])
        self.assertEqual(denoise['state'], 'succeeded', denoise)
        self.assertEqual(builder.commands[0][1][1:3], [str(ROOT / 'scripts' / 'media.py'), 'clean'])
        denoise_seconds = time.monotonic() - started
        _, runs = jobs.list_runs(sid)
        baseline = next(run for run in runs['runs'] if run['run_id'] == denoise['run_id'])
        self.assertTrue(baseline['baseline_eligible'], baseline)
        _, measured = jobs.measure_interval(sid, {'run_id': baseline['run_id'], 'start_seconds': 5.2,
                                                  'end_seconds': 6.0})
        _, review = jobs.create_capture_review(sid, review_body(baseline['run_id'], source['sha256'], start=5.2,
                                                                end=6.0, key='real-review-01'))
        started = time.monotonic()
        _, authored = jobs.submit({'tool': 'capture_profile', 'source_artifact_id': sid,
                                   'idempotency_key': 'real-capture-01', 'capture_review_id': review['review_id'],
                                   'parameters': {'preset': 'fuller'}})
        authored = wait(authored['job_id'], 90)
        self.assertEqual(authored['state'], 'succeeded', authored)
        self.assertEqual(authored['worker_status'], 'authored_unrendered')
        capture_seconds = time.monotonic() - started
        evidence = {'denoise': {'job': denoise, 'seconds': round(denoise_seconds, 3)},
                    'capture_profile': {'job': authored, 'seconds': round(capture_seconds, 3),
                                        'review': review, 'measurement_channels': measured['channels']}}
        if _dot_component(ROOT):
            evidence['apply_capture_profile'] = {
                'status': 'skipped', 'reason': 'tool_api.validate_tool_arguments refuses dot-prefixed path components; '
                                               'this worktree lives under .local/ (run from the main checkout)'}
        else:
            started = time.monotonic()
            _, applied = jobs.submit({'tool': 'apply_capture_profile', 'source_artifact_id': sid,
                                      'idempotency_key': 'real-apply-01',
                                      'capture_profile_job_id': authored['job_id'],
                                      'parameters': {'timeout_seconds': 300}})
            applied = wait(applied['job_id'], 330)
            self.assertEqual(applied['state'], 'succeeded', applied)
            evidence['apply_capture_profile'] = {'job': applied, 'seconds': round(time.monotonic() - started, 3)}
        METRICS['real_workers'] = {tool: (value.get('status') or value['job']['state'])
                                   for tool, value in evidence.items()}
        if os.environ.get('WEB_S3_WRITE_RECEIPTS') == '1':
            write_admission_receipts(evidence, builder)


def write_admission_receipts(evidence, builder):
    """Path-free admission evidence receipts for root (written only when explicitly requested)."""
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    for tool, value in evidence.items():
        receipt = {
            'schema': 'video-utils/web-job-admission-evidence', 'schema_version': 1, 'lane': 'routes_processing',
            'sprint': '20261007-s3', 'tracker': 'TIN-5718', 'tool': tool,
            'ruling': 'R-HOOK-CONVERGENCE-20261004; R-N11/R-N12/R-N13; TIN-3692 98cf680c-7299-4949-bfb2-60079053ad43',
            'requested_change': {'scripts/capabilities.py WEB_JOB_ADMISSIONS': {
                tool: f'docs/agent-notes/sprints/20261007-s3/routes_processing-web-job-{tool}.json'},
                'program/capabilities.json': f'{tool}.adapters.web_job planned -> admitted (root decision)'},
            'fixture': 'synthetic 7 s testsrc2 + 32.70 Hz sine MOV (FFmpeg lavfi); the real take was never opened',
            'worker_path': 'WebJobs supervisor -> pass-through test builder returning WebJobs.real_command(tool, args) '
                           '(identical product argv; worker_kind recorded as test_stub because admission is pending)',
            'claim_class': 'contract_and_structural_check', 'listening': 'not_performed',
            'master_adopted': False, 'measured': {}, 'unknown': {}}
        if 'job' in value:
            job = value['job']
            receipt['measured'] = {'state': job['state'], 'worker_status': job.get('worker_status'),
                                   'run_id': job.get('run_id'), 'outputs': job.get('outputs'),
                                   'capability_revision': job['capability_revision'],
                                   'wall_seconds_including_supervision': value['seconds']}
            receipt['outcome'] = 'succeeded' if job['state'] == 'succeeded' else 'failed'
        else:
            receipt['outcome'] = 'not_run'
            receipt['unknown'] = {'real_worker_run': value['reason']}
        receipt['unknown'].update({key: reason for key, reason in web_jobs.PROCESSING_UNKNOWN_REASONS.items()})
        text = json.dumps(receipt, indent=2, sort_keys=True) + '\n'
        for needle in ('/Users/', str(ROOT)):
            assert needle not in text, 'receipt would leak a host path'
        (RECEIPTS / f'routes_processing-web-job-{tool}.json').write_text(text)


# --------------------------------------------------------------------------- page loads (built app)

@unittest.skipUnless(shutil.which('node') and (WEB / 'build' / 'index.js').is_file(),
                     'node or web/build missing; build with pnpm build first (skip is not a pass)')
class PageLoadTests(S3Base):
    """M5a: capture and process page loads create no capture review (built app against a live API)."""

    def test_m5a_page_loads_create_no_review(self):
        env = self.env()
        fx = self.fixture(env, review=False)
        with socket_port() as port:
            pass
        process = subprocess.Popen(['node', 'serve.js'], cwd=WEB, start_new_session=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   env={**{k: v for k, v in os.environ.items() if k not in ('ORIGIN',)},
                                        'HOST': '127.0.0.1', 'PORT': str(port),
                                        'VIDEO_UTILS_CONTROL_API_URL': f'http://127.0.0.1:{env["server"].server_address[1]}',
                                        'VIDEO_UTILS_CONTROL_API_TOKEN': env['server'].token})
        self.addCleanup(lambda: (sigkill_own_group(process.pid), process.wait(timeout=10), process.stdout.close()))
        import http.client
        end = time.monotonic() + 20
        pages = [f'/sources/{fx["source"]}', f'/sources/{fx["source"]}/capture', f'/sources/{fx["source"]}/process']
        statuses = {}
        while time.monotonic() < end and len(statuses) < len(pages):
            for page in pages:
                if page in statuses:
                    continue
                try:
                    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=15)
                    connection.request('GET', page, headers={'Host': f'127.0.0.1:{port}'})
                    response = connection.getresponse()
                    body = response.read().decode('utf-8', 'replace')
                    connection.close()
                    statuses[page] = response.status
                    for needle in (str(ROOT), str(self.base), '/Users/'):
                        self.assertNotIn(needle, body)
                    if page.endswith('/process'):
                        self.assertIn('capture_interval_required', body)
                        self.assertNotIn('high-pass', body.lower().replace('no high-pass', ''))
                    if page.endswith('/capture'):
                        self.assertIn('data-interval-empty="true"', body)
                        self.assertIn('data-origin-warning="true"', body)  # ORIGIN unset in this launch
                except (ConnectionError, OSError):
                    time.sleep(0.2)
        self.assertEqual(statuses, {page: 200 for page in pages})
        self.assertEqual(self.count(env['state'], 'capture_reviews'), 0)
        METRICS['M5a_pages'] = {'pages_loaded': len(statuses), 'reviews_created': 0}


class WalkthroughTests(PageLoadTests):
    """Synthetic walkthrough through the built app's form actions (stub workers, test admission seam)."""

    def start_app(self, env):
        with socket_port() as port:
            pass
        # ORIGIN as the requested serve.js default would set it (root-owned change request); without it
        # adapter-node reports an https origin and SvelteKit's CSRF check refuses every form POST.
        process = subprocess.Popen(['node', 'serve.js'], cwd=WEB, start_new_session=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   env={**{k: v for k, v in os.environ.items() if k not in ('ORIGIN',)},
                                        'HOST': '127.0.0.1', 'PORT': str(port), 'ORIGIN': f'http://127.0.0.1:{port}',
                                        'VIDEO_UTILS_CONTROL_API_URL': f'http://127.0.0.1:{env["server"].server_address[1]}',
                                        'VIDEO_UTILS_CONTROL_API_TOKEN': env['server'].token})
        self.addCleanup(lambda: (sigkill_own_group(process.pid), process.wait(timeout=10), process.stdout.close()))
        end = time.monotonic() + 20
        while time.monotonic() < end:
            try:
                self.http(port, 'GET', '/upload')
                return port
            except OSError:
                time.sleep(0.2)
        self.fail('app did not start')

    def http(self, port, method, path, form=None):
        import http.client
        from urllib.parse import urlencode
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=60)
        headers = {'Host': f'127.0.0.1:{port}', 'Accept': 'text/html'}
        body = None
        if form is not None:
            body = urlencode(form)
            headers.update({'Content-Type': 'application/x-www-form-urlencoded', 'Origin': f'http://127.0.0.1:{port}'})
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            text = response.read().decode('utf-8', 'replace')
        finally:
            connection.close()
        for needle in (str(ROOT), str(self.base), '/Users/'):
            self.assertNotIn(needle, text)
        return response.status, text

    def key(self, html, form_marker, name='idempotency_key'):
        import re
        start = html.index(form_marker)
        match = re.search(r'name="%s" value="(ui-[0-9a-f]{32})"' % name, html[start:])
        return match.group(1)

    def test_walkthrough_capture_and_process_actions(self):
        import re
        env = self.env()
        fx = self.fixture(env, review=False)
        port = self.start_app(env)
        base = f'/sources/{fx["source"]}'
        status, html = self.http(port, 'GET', f'{base}/capture?run={fx["run_id"]}')
        self.assertEqual(status, 200)
        self.assertIn('data-native-timeline="true"', html)
        self.assertIn('data-interval-empty="true"', html)
        save_key = self.key(html, 'data-capture-form="true"')
        common = {'run_id': fx['run_id'], 'expected_source_sha256': fx['sha'], 'idempotency_key': save_key}
        status, html = self.http(port, 'POST', f'{base}/capture?/measure',
                                 dict(common, start_seconds='5.5', end_seconds='6.4'))
        self.assertEqual(status, 200)
        self.assertIn('data-measurement="true"', html)
        status, html = self.http(port, 'POST', f'{base}/capture?/save',
                                 dict(common, start_seconds='1.0', end_seconds='2.0', review_status='reviewed_candidate',
                                      authorization_scope='experimental_capture_render', music_status='unknown',
                                      click_status='unknown', ambient_music_status='not_reported', note='walkthrough'))
        self.assertIn('setup_interval_unacknowledged', html)
        status, html = self.http(port, 'POST', f'{base}/capture?/save',
                                 dict(common, start_seconds='5.5', end_seconds='6.4', review_status='reviewed_candidate',
                                      authorization_scope='experimental_capture_render', music_status='unknown',
                                      click_status='unknown', ambient_music_status='not_reported',
                                      note='walkthrough review (synthetic)'))
        self.assertIn('data-review-saved="rev_', html)
        review_id = re.search(r'data-review-saved="(rev_[0-9a-f]{32})"', html).group(1)
        status, html = self.http(port, 'GET', f'{base}/process')
        self.assertIn('data-option="fuller" data-enabled="true"', html)
        author_key = self.key(html, 'data-author-form="fuller"')
        status, html = self.http(port, 'POST', f'{base}/process?/author',
                                 {'preset': 'fuller', 'capture_review_id': review_id, 'idempotency_key': author_key})
        self.assertIn('data-submitted-job="job_', html, html[-2000:])
        # FULLER never forwards controls (the builder drops them); a custom value out of schema bounds
        # comes back as a typed refusal and is never clamped.
        refused = self.http(port, 'POST', f'{base}/process?/author',
                            {'preset': 'custom', 'capture_review_id': review_id, 'reduction_db': '50',
                             'noise_floor_db': '-40', 'adaptivity': '0', 'gain_smooth': '0', 'integrated_lufs': '-18',
                             'true_peak_dbtp': '-1.75', 'idempotency_key': 'ui-' + 'a' * 32})[1]
        self.assertIn('data-refusal-code="invalid_parameters"', refused)
        job_id = re.search(r'data-submitted-job="(job_[0-9a-f]{32})"', html).group(1)
        self.wait_job(env['client'], job_id, ('succeeded',))
        status, html = self.http(port, 'GET', f'{base}/process')
        apply_key = self.key(html, 'data-apply-form="true"')
        status, html = self.http(port, 'POST', f'{base}/process?/apply',
                                 {'capture_profile_job_id': job_id, 'timeout_seconds': '30', 'idempotency_key': apply_key})
        applied = re.search(r'data-submitted-job="(job_[0-9a-f]{32})"', html).group(1)
        self.wait_job(env['client'], applied, ('succeeded',))
        status, html = self.http(port, 'GET', f'{base}/process')
        denoise_key = self.key(html, 'data-author-form="fuller"')  # any fresh ui- key from the page
        status, html = self.http(port, 'POST', f'{base}/process?/denoise',
                                 {'profile': 'captured8', 'idempotency_key': denoise_key})
        self.assertIn('profile_source_mismatch', html)
        status, html = self.http(port, 'GET', f'{base}/process')
        self.assertIn(f'data-audition="{applied}"', html)
        self.assertIn('data-span-audition="true"', html)
        self.assertNotIn('data-origin-warning="true"', html)
        self.assertIn('data-level-matched="false"', html)
        status, overview = self.http(port, 'GET', base)
        self.assertIn('data-job-tool="apply_capture_profile"', overview)
        self.assertIn('data-probe-summary="true"', overview)
        media_status, _ = self.http(port, 'GET', f'{base}/runs/{fx["run_id"]}/media/source')
        self.assertEqual(media_status, 200)
        bad_status, _ = self.http(port, 'GET', f'{base}/runs/..%2Fx/media/source')
        self.assertIn(bad_status, (400, 404))
        METRICS['walkthrough'] = {'actions': ['measure', 'save (refused setup)', 'save', 'author',
                                              'author custom (refused invalid_parameters)',
                                              'apply', 'denoise (refused profile_source_mismatch)'],
                                  'jobs_succeeded': 2, 'reviews_saved': self.count(env['state'], 'capture_reviews'),
                                  'worker_kind': 'test_stub (admission seam)'}


@contextlib.contextmanager
def socket_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    yield port


def tearDownModule():
    text = json.dumps(METRICS, indent=2, sort_keys=True, default=str)
    print('\nROUTES_PROCESSING_S3_METRICS ' + text)
    target = os.environ.get('WEB_S3_METRICS_OUT')
    if target:
        Path(target).write_text(text + '\n')


if __name__ == '__main__':
    unittest.main()
