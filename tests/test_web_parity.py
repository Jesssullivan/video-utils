"""S2 web_ui_binding: /api/v1 control API, CLI/MCP/web parity and the end-to-end walkthrough.

Contract: docs/spec/sprints/WEB_UI_S2.md (sections 4, 8, 9.2 and 10). Tests run against HTTP on
ephemeral loopback ports with synthetic sources only; the real take is never opened. FFmpeg-,
node- or pnpm-dependent cases skip with an explicit reason (reported, never counted as a pass).
No randomness is asserted: IDs, tokens and idempotency keys are never compared by value.
"""
from __future__ import annotations

import contextlib
import datetime
import hashlib
import http.client
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import annotation_v2  # noqa: E402
import mcp_server  # noqa: E402
import test_web_jobs as wj  # noqa: E402  (helpers only; its test classes are not re-collected here)
import tool_api  # noqa: E402
import web_api  # noqa: E402
import web_jobs  # noqa: E402
from web_jobs import WebJobs  # noqa: E402

WEB = ROOT / 'web'
PARITY = WEB / 'fixtures' / 'parity'
KNOB_MIRROR = WEB / 'src' / 'lib' / 'share-export-knobs.json'
JOB_REQUEST_MODULE = WEB / 'src' / 'lib' / 'server' / 'job-request.ts'
OUT_DIR = ROOT / 'artifacts' / 's2' / 'web_ui_binding'
FAKE_MOV = wj.FAKE_MOV
MiB = 1024 * 1024
MAX_UPLOAD = 8 * MiB
METRICS = {}
PLACEHOLDER_SOURCE = 'art_' + '0' * 32
UNKNOWN_JOB = 'job_' + '0' * 32
UNKNOWN_ART = 'art_' + 'f' * 32
ENVELOPE_KEYS = ('schema_version', 'tool', 'evidence_kind', 'implementation_status', 'limitations', 'skill',
                 'instrument_context')
V1_EXTRA_KEYS = {'schema_version', 'phase', 'phase_reason', 'progress', 'progress_reason', 'eta_seconds',
                 'eta_seconds_reason', 'created_at', 'updated_at', 'tool_envelope'}
SOURCE_RECORD_KEYS = {'source_artifact_id', 'source_id', 'source_id_reason', 'source_binding', 'kind', 'sha256',
                      'size_bytes', 'admitted_at', 'origin', 'state', 'rechecked', 'state_reason',
                      'duration_seconds', 'duration_seconds_reason'}
JOB_SUMMARY_KEYS = {'job_id', 'state', 'reason_code', 'parameters', 'created_at', 'updated_at', 'attempt_count',
                    'artifact_count'}

# Frozen before implementation (WEB_UI_S2.md section 8); web/fixtures/parity/cases.json mirrors it.
CASES = (
    ('defaults', {}, 'accept'),
    ('height_min', {'height': 240}, 'accept'),
    ('height_max', {'height': 1080}, 'accept'),
    ('crf_min', {'crf': 18}, 'accept'),
    ('crf_max', {'crf': 32}, 'accept'),
    ('audio_kbps_min', {'audio_kbps': 64}, 'accept'),
    ('audio_kbps_max', {'audio_kbps': 192}, 'accept'),
    ('timeout_seconds_min', {'timeout_seconds': 30}, 'accept'),
    ('timeout_seconds_max', {'timeout_seconds': 900}, 'accept'),
    ('height_below_min', {'height': 239}, 'refuse'),
    ('height_above_max', {'height': 1081}, 'refuse'),
    ('crf_below_min', {'crf': 17}, 'refuse'),
    ('crf_above_max', {'crf': 33}, 'refuse'),
    ('audio_kbps_below_min', {'audio_kbps': 63}, 'refuse'),
    ('audio_kbps_above_max', {'audio_kbps': 193}, 'refuse'),
    ('timeout_seconds_below_min', {'timeout_seconds': 29}, 'refuse'),
    ('timeout_seconds_above_max', {'timeout_seconds': 901}, 'refuse'),
    ('height_odd', {'height': 721}, 'refuse'),
    ('codec_av1', {'codec': 'av1'}, 'refuse'),
    ('unknown_knob_bitrate', {'bitrate': 4000}, 'refuse'),
    ('crf_boolean_true', {'crf': True}, 'refuse'),
    ('crf_float', {'crf': 27.5}, 'refuse'),
    ('crf_string', {'crf': '27'}, 'refuse'),
    ('codec_hevc', {'codec': 'hevc'}, 'accept'),
    ('codec_copy', {'codec': 'copy'}, 'accept'),
)
CLI_PATHS = {'source': 'RUN-A/export/clip.mov', 'output': 'parity-out/share.mp4'}

# The web_jobs stub, plus a synthetic packet extent so annotation clocks exist without FFmpeg.
# The extent is a fixture value, not a measurement; real extents come from the e2e walkthrough.
STUB_PROOF = wj.STUB.replace(
    "'master_adopted': False, 'listening_accepted': False}))",
    "'master_adopted': False, 'listening_accepted': False,\n"
    "                  'video_proof': {'method': 'synthetic_stub_extent', 'packet_count': 48,\n"
    "                                  'source_start_seconds': 0.0, 'source_end_seconds': 2.0}}))")
assert STUB_PROOF != wj.STUB, 'stub proof patch did not apply'


class ProofStubBuilder(wj.StubBuilder):
    def __call__(self, args):
        with self.lock:
            mode = self.modes.pop(0) if self.modes else self.default
            beat = self.beats_dir / f'beat-{len(self.beats)}-{mode}-{os.urandom(4).hex()}.json'
            self.beats.append(beat)
        return [sys.executable, '-c', STUB_PROOF, mode, str(beat), args['source'], args['output']]


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def cli_verdict(parameters):
    """CLI validation path: tool_api.validate + validate_tool_arguments (tool_api.py run)."""
    args = {**CLI_PATHS, **parameters}
    try:
        tool_api.validate(args, tool_api.descriptor('share_export')['inputSchema'])
        tool_api.validate_tool_arguments('share_export', args)
    except tool_api.ValidationError:
        return 'refuse'
    return 'accept'


def host_facts():
    """Descriptive host facts for receipts (no paths)."""
    def last_line(command):
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        lines = [line for line in (done.stdout or done.stderr).splitlines() if line.strip()]
        return lines[-1].strip()[:120] if lines else None
    ffmpeg = None
    if wj.HAVE_FFMPEG:
        first = subprocess.run([wj.FFMPEG, '-version'], capture_output=True, text=True, timeout=30).stdout.splitlines()
        ffmpeg = ' '.join(first[0].split()[:3]) if first else None
    return {'uname_sm': f'{platform.system()} {platform.machine()}',
            'cpu': last_line(['sysctl', '-n', 'machdep.cpu.brand_string']) if platform.system() == 'Darwin' else None,
            'python': platform.python_version(),
            'node': last_line(['node', '--version']) if shutil.which('node') else None,
            'pnpm': last_line(['pnpm', '--version']) if shutil.which('pnpm') else None,
            'ffmpeg': ffmpeg}


class Env:
    """In-process WebJobs + WebAPIServer on an ephemeral loopback port (no daemon)."""

    def __init__(self, test, *, runs_root=None, builder='stub', start=True, allow_uploads=False,
                 max_upload_bytes=MAX_UPLOAD, **kwargs):
        state_root = test.state()
        if builder == 'stub':
            builder = ProofStubBuilder(Path(state_root).parent / (Path(state_root).name + '-beats'))
        self.builder = builder
        self.jobs = WebJobs(runs_root or test.R, state_root, command_builder=builder, **kwargs)
        if start:
            self.jobs.start()
        self.server = web_api.WebAPIServer(self.jobs, 0, allow_uploads=allow_uploads,
                                           max_upload_bytes=max_upload_bytes)
        test.tokens.append(self.server.token)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.05},
                                       daemon=True)
        self.thread.start()
        self.client = wj.Client(test, self.server)
        self.port = self.server.server_address[1]
        self.stopped = False
        test.addCleanup(self.cleanup)

    def cleanup(self):
        if not self.stopped:
            self.stopped = True
            self.server.stop()
            self.thread.join(timeout=10)
            self.jobs.close()
        for process in self.jobs._detached:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass  # Darwin killpg(2) gives EPERM for an own group whose members are all zombies
            process.wait(timeout=10)


def raw_http(test, port, method, path, *, headers=None, body=b'', shutdown_write=False, token=None):
    """Hand-written HTTP/1.1 request (for header-only, chunked and short-body cases)."""
    sock = socket.create_connection(('127.0.0.1', port), timeout=30)
    try:
        lines = [f'{method} {path} HTTP/1.1', f'Host: 127.0.0.1:{port}', 'Connection: close']
        if token:
            lines.append(f'Authorization: Bearer {token}')
        lines += [f'{key}: {value}' for key, value in (headers or {}).items()]
        sock.sendall(('\r\n'.join(lines) + '\r\n\r\n').encode('ascii') + body)
        if shutdown_write:
            sock.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            try:
                chunk = sock.recv(65536)
            except ConnectionResetError:
                break
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        sock.close()
    data = b''.join(chunks)
    head, _, payload = data.partition(b'\r\n\r\n')
    status_line, *header_lines = head.decode('latin-1').split('\r\n')
    status = int(status_line.split()[1])
    parsed = {}
    for line in header_lines:
        key, _, value = line.partition(':')
        parsed[key.strip()] = value.strip()
    response = wj.Response(status, parsed, payload)
    test.assert_no_leak(response)
    return response


class ParityBase(unittest.TestCase):
    """Synthetic runs root R (read-only for the class) and per-test state roots."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix='web-ui-parity-')
        cls.raw_base = cls._tmp.name
        cls.base = Path(cls._tmp.name).resolve()
        cls.R = cls.base / 'R'
        cls.populate(cls.R)
        cls.clip_available = False
        if wj.HAVE_FFMPEG:
            wj.make_clip(cls.R / 'artifacts' / 'runs' / 'RUN-A' / 'export' / 'clip.mov')
            cls.clip_available = True
        cls.runs_digest = wj.tree_digest(cls.R / 'artifacts' / 'runs')
        cls.counter = 0

    @staticmethod
    def populate(root):
        run = wj.make_runs_root(root)
        (run / 'export' / 'fake2.mov').write_bytes(FAKE_MOV + b'variant-2')
        (run / 'notes.txt').write_text('practice notes, not media')
        (run / 'bad.mov').write_bytes(b'\x00\x01')
        other = Path(root) / 'artifacts' / 'runs' / 'RUN-B' / 'export'
        other.mkdir(parents=True)
        (other / 'nomanifest.mov').write_bytes(FAKE_MOV + b'variant-b')
        return run

    @classmethod
    def tearDownClass(cls):
        try:
            if wj.tree_digest(cls.R / 'artifacts' / 'runs') != cls.runs_digest:
                raise AssertionError('class artifacts/runs fixture tree changed during the test class')
            METRICS.setdefault('runs_tree_unchanged_classes', []).append(cls.__name__)
        finally:
            cls._tmp.cleanup()

    def setUp(self):
        self.tokens = []

    @property
    def forbidden(self):
        return sorted({str(self.base), self.raw_base, str(self.R), wj.SENTINEL, str(ROOT), 'RUN-A/', 'RUN-B/',
                       'web-upload-', '/upload/source', *self.tokens}, key=len)

    def assert_no_leak(self, response):
        blob = response.payload + json.dumps(response.headers).encode()
        for needle in self.forbidden:
            self.assertNotIn(needle.encode(), blob, 'response leaked a host path, selector or token')
        METRICS['responses_checked_for_leaks'] = METRICS.get('responses_checked_for_leaks', 0) + 1

    def state(self, label='s'):
        type(self).counter += 1
        return self.base / 'states' / f'{self._testMethodName}-{label}-{type(self).counter}'

    def fresh_runs(self):
        type(self).counter += 1
        root = self.base / f'runs-{self._testMethodName}-{type(self).counter}'
        self.populate(root)
        return root

    # ----------------------------------------------------------------- helpers

    def admit(self, client, selector='RUN-A/export/fake.mov', prefix='/api/v1'):
        response = client.post(f'{prefix}/sources', {'selector': selector})
        self.assertIn(response.status, (200, 201), response.json)
        return response.json['source_artifact_id']

    def submit(self, client, source, key, parameters=None, prefix='/api/v1'):
        body = {'tool': 'share_export', 'source_artifact_id': source, 'idempotency_key': key}
        if parameters is not None:
            body['parameters'] = parameters
        return client.post(f'{prefix}/jobs', body)

    def wait_job(self, client, job_id, states, prefix='/api/v1', timeout=30):
        end = time.monotonic() + timeout
        while True:
            response = client.get(f'{prefix}/jobs/{job_id}')
            self.assertEqual(response.status, 200, response.json)
            if response.json['state'] in states:
                return response.json
            if time.monotonic() > end:
                self.fail(f'job did not reach {states}; last state {response.json["state"]}')
            time.sleep(0.05)

    def staged_runs(self, runs_root):
        runs = Path(runs_root) / 'artifacts' / 'runs'
        staged = sorted(p.name for p in runs.iterdir() if p.name.startswith('web-upload-'))
        partials = [str(p) for p in runs.rglob('*.partial')]
        return staged, partials

    def pre_existing_digest(self, runs_root):
        """Digest of every runs entry except web-upload-* staging runs (confinement metric 15)."""
        runs = Path(runs_root) / 'artifacts' / 'runs'
        rows = []
        for entry in sorted(runs.iterdir()):
            if entry.name.startswith('web-upload-'):
                continue
            rows.append([entry.name, wj.tree_digest(entry) if entry.is_dir() else wj.sha_file(entry)])
        return sha_bytes(json.dumps(rows).encode())

    def annotation_request(self, store, key, *, revision=None, start=1.0, end=None, basis='operator_assertion',
                           reported_by=None, kind='rhythm_timing', note='synthetic fixture note'):
        operator = basis == 'operator_assertion'
        return {'schema_version': 2, 'expected_revision': store['revision'] if revision is None else revision,
                'idempotency_key': key, 'source_sha256': store['source_sha256'],
                'manifest_sha256': store['manifest_sha256'],
                'annotation': {'kind': kind, 'basis': basis, 'status': 'needs_review',
                               'source_span': {'start_seconds': start, 'end_seconds': start if end is None else end,
                                               'extent_known': end is not None},
                               'reported_by': reported_by or {'actor': 'operator', 'via': 'browser'},
                               'operator_certainty': 'uncertain' if operator else None,
                               'operator_quote': 'felt late here (synthetic)' if operator else None,
                               'note': note}}

    def succeeded_source(self, env, selector='RUN-A/export/fake.mov', key='clock-job-0001'):
        source = self.admit(env.client, selector)
        job = self.submit(env.client, source, key).json['job_id']
        self.wait_job(env.client, job, ('succeeded',))
        return source, job


# --------------------------------------------------------------------------- 1-5 validation parity

class ParityValidationTests(ParityBase):

    # 1
    def test_case_table_frozen_and_covers_all_knobs(self):
        table = json.loads((PARITY / 'cases.json').read_text())
        mirrored = [(c['case_id'], c['parameters'], c['expected_verdict']) for c in table['cases']]
        self.assertEqual(json.dumps(mirrored), json.dumps([list(c) for c in CASES]))
        self.assertGreaterEqual(len(CASES), 20)
        self.assertEqual(len({c[0] for c in CASES}), len(CASES))
        covered = {key for _, parameters, _ in CASES for key in parameters}
        self.assertTrue(set(web_jobs.PARAMETER_KEYS) <= covered, set(web_jobs.PARAMETER_KEYS) - covered)
        props = tool_api.descriptor('share_export')['inputSchema']['properties']
        values = {}
        for _, parameters, _ in CASES:
            for key, value in parameters.items():
                values.setdefault(key, []).append(value)
        for key in web_jobs.PARAMETER_KEYS:
            if props[key]['type'] != 'integer':
                continue
            low, high = props[key]['minimum'], props[key]['maximum']
            with self.subTest(knob=key):
                self.assertTrue({low, high, low - 1, high + 1} <= set(v for v in values[key] if type(v) is int))
        # The UI knob mirror is the descriptor, not invented values.
        mirror = json.loads(KNOB_MIRROR.read_text())
        self.assertEqual(mirror['order'], list(web_jobs.PARAMETER_KEYS))
        for key in web_jobs.PARAMETER_KEYS:
            expected = {k: props[key][k] for k in ('type', 'minimum', 'maximum', 'enum', 'default', 'description')
                        if k in props[key]}
            self.assertEqual(mirror['knobs'][key], expected, key)
        METRICS['parity_case_table'] = {'cases': len(CASES), 'knobs_covered': sorted(covered & set(props)),
                                        'mirror_matches_descriptor': True}

    # 2
    def test_cli_and_web_validation_verdicts_agree(self):
        requests = {r['case_id']: r['body'] for r in json.loads((PARITY / 'requests.json').read_text())['requests']}
        env = Env(self, start=False, queue_limit=64)
        source = self.admit(env.client)
        rows, disagreements = [], []
        for case_id, parameters, expected in CASES:
            with self.subTest(case=case_id):
                cli = cli_verdict(parameters)
                try:
                    env.jobs.normalize_parameters(parameters)
                    direct = 'accept'
                except web_jobs.WebJobsError as error:
                    self.assertEqual(error.code, 'invalid_parameters')
                    direct = 'refuse'
                body = dict(requests[case_id], source_artifact_id=source)
                response = env.client.post('/api/v1/jobs', body)
                if response.status == 202:
                    web = 'accept'
                elif (response.status, response.code) == (400, 'invalid_parameters'):
                    web = 'refuse'
                else:
                    self.fail(f'unexpected web outcome {response.status} {response.code}')
                rows.append({'case_id': case_id, 'expected': expected, 'cli': cli, 'web_http': web,
                             'web_normalize': direct})
                if not cli == web == direct == expected:
                    disagreements.append(case_id)
                self.assertEqual((cli, web, direct), (expected, expected, expected))
        METRICS['parity_validation'] = {'cases': len(CASES), 'agree': len(CASES) - len(disagreements),
                                        'disagreements': disagreements, 'rows': rows,
                                        'web_body_source': 'web/fixtures/parity/requests.json (job-request.ts)'}

    # 3
    def test_mcp_tools_call_refuses_same_cases_before_worker(self):
        server = mcp_server.Server()
        init = server.handle({'jsonrpc': '2.0', 'id': 0, 'method': 'initialize', 'params': {
            'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'parity', 'version': '0'}}})
        self.assertIn('result', init)
        server.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        launched, built = [], []

        def no_worker(*args, **kwargs):
            launched.append(args)
            raise AssertionError('parity test must never launch a worker')

        def sentinel(name, args):
            built.append(name)
            raise tool_api.ToolError('parity_sentinel_worker_not_launched')

        rows = []
        with mock.patch.object(tool_api, 'run_worker', no_worker), \
                mock.patch.object(tool_api, 'worker_command', sentinel):
            for index, (case_id, parameters, expected) in enumerate(CASES, start=1):
                with self.subTest(case=case_id):
                    reply = server.handle({'jsonrpc': '2.0', 'id': index, 'method': 'tools/call', 'params': {
                        'name': 'share_export', 'arguments': {**CLI_PATHS, **parameters}}})
                    if 'error' in reply:
                        self.assertEqual(reply['error']['code'], -32602)
                        verdict = 'refuse'
                    else:
                        result = reply['result']
                        self.assertTrue(result['isError'])
                        self.assertIn('parity_sentinel_worker_not_launched', result['content'][0]['text'])
                        verdict = 'accept'
                    rows.append({'case_id': case_id, 'mcp': verdict, 'cli': cli_verdict(parameters)})
                    self.assertEqual(verdict, cli_verdict(parameters))
                    self.assertEqual(verdict, expected)
        self.assertEqual(launched, [])
        self.assertEqual(len(built), sum(1 for c in CASES if c[2] == 'accept'))
        METRICS['parity_mcp'] = {'cases': len(CASES), 'agree_with_cli': sum(r['mcp'] == r['cli'] for r in rows),
                                 'workers_launched': len(launched), 'refusal_code': -32602}

    # 4
    def test_bff_parity_fixtures_match_job_request_module_shape(self):
        document = json.loads((PARITY / 'requests.json').read_text())
        self.assertEqual(document['generated_by'], 'web/src/lib/server/job-request.ts via web/fixtures/parity/generate.mjs')
        requests = document['requests']
        self.assertEqual([r['case_id'] for r in requests], [c[0] for c in CASES])
        keys = set()
        for request, (case_id, parameters, _) in zip(requests, CASES):
            body = request['body']
            with self.subTest(case=case_id):
                self.assertEqual(set(body), {'tool', 'source_artifact_id', 'parameters', 'idempotency_key'})
                self.assertEqual(body['tool'], 'share_export')
                self.assertEqual(body['source_artifact_id'], PLACEHOLDER_SOURCE)
                self.assertRegex(body['idempotency_key'], r'^ui-[0-9a-f]{32}$')
                self.assertTrue(web_jobs.IDEMPOTENCY_KEY.fullmatch(body['idempotency_key']))
                self.assertEqual(json.dumps(body['parameters'], sort_keys=True), json.dumps(parameters, sort_keys=True))
                keys.add(body['idempotency_key'])
        self.assertEqual(len(keys), len(requests))
        if shutil.which('node') is None:
            METRICS['parity_module_regeneration'] = 'skipped: node not on PATH'
            return
        script = """
const m = await import(process.argv[1]);
const cases = JSON.parse(process.argv[2]);
const key = 'ui-' + 'a'.repeat(32);
const out = cases.map((c) => m.buildJobRequest({ sourceArtifactId: process.argv[3], parameters: c.parameters, idempotencyKey: key }));
const refusals = [
  m.buildJobRequest({ sourceArtifactId: 'art_x', parameters: {}, idempotencyKey: key }),
  m.buildJobRequest({ sourceArtifactId: process.argv[3], parameters: {}, idempotencyKey: 'bad key' }),
  m.buildJobRequest({ sourceArtifactId: process.argv[3], parameters: [1], idempotencyKey: key }),
  m.buildJobRequest({ sourceArtifactId: process.argv[3], parameters: { 'Bad-Key': 1 }, idempotencyKey: key }),
  m.buildJobRequest({ sourceArtifactId: process.argv[3], parameters: { crf: { nested: 1 } }, idempotencyKey: key })
].map((r) => r.ok ? 'accepted' : r.code);
console.log(JSON.stringify({ out, refusals }));
"""
        cases = json.dumps([{'parameters': p} for _, p, _ in CASES])
        done = subprocess.run(['node', '--input-type=module', '-e', script, JOB_REQUEST_MODULE.as_uri(), cases,
                               PLACEHOLDER_SOURCE], capture_output=True, text=True, timeout=60, cwd=WEB)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        produced = json.loads(done.stdout.strip().splitlines()[-1])
        for result, request in zip(produced['out'], requests):
            self.assertTrue(result['ok'])
            regenerated = dict(result['body'], idempotency_key=request['body']['idempotency_key'])
            self.assertEqual(json.dumps(regenerated, sort_keys=True), json.dumps(request['body'], sort_keys=True))
        self.assertEqual(produced['refusals'], ['invalid_source_id', 'invalid_idempotency_key',
                                                'invalid_parameters_shape', 'invalid_parameters_shape',
                                                'invalid_parameters_shape'])
        METRICS['parity_module_regeneration'] = {'cases': len(requests), 'equal_except_random_key': len(requests)}

    # 5
    def test_v1_projection_tool_envelope_matches_tool_api_envelope(self):
        fake = {'status': 'exported_unreviewed'}
        with mock.patch.object(tool_api, 'worker_command', lambda name, args: ['true']), \
                mock.patch.object(tool_api, 'run_worker', lambda *a, **k: fake), \
                mock.patch.object(tool_api, 'classify_share_export_result', lambda result, args: result):
            cli = tool_api.execute('share_export', dict(CLI_PATHS))
        cli_envelope = {key: cli[key] for key in ENVELOPE_KEYS}
        env = Env(self, start=False)
        source = self.admit(env.client)
        submitted = self.submit(env.client, source, 'envelope-0001')
        self.assertEqual(submitted.status, 202)
        self.assertEqual(V1_EXTRA_KEYS - set(submitted.json), set())
        projection = env.client.get(f'/api/v1/jobs/{submitted.json["job_id"]}').json
        self.assertEqual(set(projection['tool_envelope']), set(ENVELOPE_KEYS))
        equal = [key for key in ENVELOPE_KEYS if projection['tool_envelope'][key] == cli_envelope[key]]
        self.assertEqual(equal, list(ENVELOPE_KEYS))
        self.assertEqual(projection['phase'], 'submitted')
        self.assertEqual(projection['progress'], {'completed': 1, 'denominator': 6, 'unit': 'lifecycle_steps'})
        self.assertIsNone(projection['eta_seconds'])
        self.assertEqual(projection['eta_seconds_reason'], 'not estimated')
        self.assertIn('not an encode fraction', projection['progress_reason'])
        legacy = env.client.get(f'/jobs/{submitted.json["job_id"]}').json
        self.assertEqual(V1_EXTRA_KEYS & set(legacy), set())
        self.assertEqual({k: v for k, v in projection.items() if k not in V1_EXTRA_KEYS}, legacy)
        METRICS['parity_envelope'] = {'keys': len(ENVELOPE_KEYS), 'equal': len(equal)}


# --------------------------------------------------------------------------- 6 result parity (FFmpeg)

class ParityResultTests(ParityBase):

    # 6
    def test_cli_and_web_share_export_typed_fields_agree(self):
        if not self.clip_available:
            METRICS['parity_result'] = {'skipped': wj.FFMPEG_SKIP}
            self.skipTest(wj.FFMPEG_SKIP)
        clip = self.R / 'artifacts' / 'runs' / 'RUN-A' / 'export' / 'clip.mov'
        out_dir = self.base / 'cli-out'
        out_dir.mkdir()
        parameters = {'timeout_seconds': 300}
        start = time.perf_counter()
        cli = tool_api.execute('share_export', {'source': str(clip), 'output': str(out_dir / 'share.mp4'),
                                                **parameters})
        cli_wall = time.perf_counter() - start
        env = Env(self, builder=None)
        source = self.admit(env.client, 'RUN-A/export/clip.mov')
        start = time.perf_counter()
        job = self.submit(env.client, source, 'result-parity-01', parameters).json['job_id']
        web = self.wait_job(env.client, job, web_jobs.TERMINAL, timeout=300)
        web_wall = time.perf_counter() - start
        self.assertEqual(web['state'], 'succeeded', web['attempts'][-1])
        envelope_equal = [key for key in ENVELOPE_KEYS if web['tool_envelope'][key] == cli[key]]
        self.assertEqual(envelope_equal, list(ENVELOPE_KEYS))
        cli_checks = web_jobs.WebJobs._worker_checks(cli['result'])
        web_checks = web['attempts'][-1]['worker_checks']
        structural = ('status', 'source_sha256', 'source_bytes', 'settings', 'codecs', 'dimensions',
                      'video_encode_count', 'audio_proof', 'master_adopted', 'listening_accepted')
        for key in structural:
            with self.subTest(field=key):
                self.assertEqual(web_checks[key], cli_checks[key])
        for key in ('method', 'packet_count', 'source_start_seconds', 'source_end_seconds'):
            with self.subTest(video_proof=key):
                self.assertEqual(web_checks['video_proof'][key], cli_checks['video_proof'][key])
        METRICS['parity_result'] = {
            'envelope_keys_equal': f'{len(envelope_equal)}/{len(ENVELOPE_KEYS)}',
            'worker_checks_structural_equal': '1/1 run',
            'output_sha256_equal': web_checks['output_sha256'] == cli_checks['output_sha256'],
            'output_bytes': {'cli': cli_checks['output_bytes'], 'web': web_checks['output_bytes']},
            'loudness_equal': web_checks['loudness'] == cli_checks['loudness'],
            'encode_byte_determinism': 'unknown',
            'wall_seconds': {'cli': round(cli_wall, 3), 'web_submit_to_terminal': round(web_wall, 3)}}


# --------------------------------------------------------------------------- 7-16 control API v1

class ControlApiV1Tests(ParityBase):

    def _alias_sequence(self, prefix):
        builder = ProofStubBuilder(self.base / f'beats-alias-{prefix.strip("/").replace("/", "-") or "legacy"}',
                                   modes=['reject'])
        env = Env(self, builder=builder)
        c = env.client
        out = []

        def note(step, response):
            out.append((step, response.status, response.code))
            return response

        source = note('admit', c.post(f'{prefix}/sources', {'selector': 'RUN-A/export/fake.mov'})).json[
            'source_artifact_id']
        note('admit_host_path', c.post(f'{prefix}/sources', {'selector': '/etc/take.mov'}))
        job = note('submit', self.submit(c, source, 'alias-job-0001', prefix=prefix)).json['job_id']
        self.wait_job(c, job, ('failed',), prefix=prefix)
        note('submit_bad_parameters', self.submit(c, source, 'alias-job-0002', {'crf': 99}, prefix=prefix))
        note('get', c.get(f'{prefix}/jobs/{job}'))
        note('get_unknown', c.get(f'{prefix}/jobs/{UNKNOWN_JOB}'))
        note('get_malformed', c.get(f'{prefix}/jobs/not-a-job'))
        note('retry', c.post(f'{prefix}/jobs/{job}/retry', {}))
        done = self.wait_job(c, job, ('succeeded',), prefix=prefix)
        note('retry_not_retryable', c.post(f'{prefix}/jobs/{job}/retry', {}))
        note('cancel_late', c.post(f'{prefix}/jobs/{job}/cancel', {}))
        note('cancel_unknown', c.post(f'{prefix}/jobs/{UNKNOWN_JOB}/cancel', {}))
        roles = {a['role']: a['artifact_id'] for a in done['artifacts']}
        note('artifact', c.get(f'{prefix}/artifacts/{roles["share_mp4"]}'))
        note('artifact_private', c.get(f'{prefix}/artifacts/{roles["share_receipt"]}'))
        note('artifact_unknown', c.get(f'{prefix}/artifacts/{UNKNOWN_ART}'))
        return out, c.get(f'{prefix}/jobs/{job}').json

    # 7
    def test_v1_routes_and_aliases_share_codes(self):
        legacy, legacy_body = self._alias_sequence('')
        versioned, v1_body = self._alias_sequence('/api/v1')
        self.assertEqual(versioned, legacy)
        expected = [('admit', 201, None), ('admit_host_path', 422, 'path_escape'), ('submit', 202, None),
                    ('submit_bad_parameters', 400, 'invalid_parameters'), ('get', 200, None),
                    ('get_unknown', 404, 'unknown_job'), ('get_malformed', 400, 'malformed_id'), ('retry', 202, None),
                    ('retry_not_retryable', 409, 'not_retryable'), ('cancel_late', 200, None),
                    ('cancel_unknown', 404, 'unknown_job'), ('artifact', 200, None),
                    ('artifact_private', 403, 'artifact_private'), ('artifact_unknown', 404, 'unknown_artifact')]
        self.assertEqual(legacy, expected)
        self.assertEqual(V1_EXTRA_KEYS & set(legacy_body), set())
        self.assertEqual(V1_EXTRA_KEYS - set(v1_body), set())
        self.assertEqual(v1_body['phase'], 'published')
        self.assertEqual(v1_body['progress'], {'completed': 6, 'denominator': 6, 'unit': 'lifecycle_steps'})
        METRICS['v1_alias_equivalence'] = {'aliased_routes': 6, 'steps': len(expected),
                                           'status_and_code_equal': sum(a == b for a, b in zip(legacy, versioned))}

    # 8
    def test_v1_loopback_host_origin_token_refusals(self):
        env = Env(self, start=False, allow_uploads=True)
        port = env.port
        self.assertEqual(env.server.server_address[0], '127.0.0.1')
        art = 'art_' + '1' * 32
        routes = [('GET', '/api/v1/sources'), ('POST', '/api/v1/sources'), ('POST', '/api/v1/uploads'),
                  ('GET', f'/api/v1/sources/{art}/media'), ('POST', '/api/v1/jobs'), ('GET', '/api/v1/jobs'),
                  ('GET', f'/api/v1/jobs/{UNKNOWN_JOB}'), ('POST', f'/api/v1/jobs/{UNKNOWN_JOB}/cancel'),
                  ('POST', f'/api/v1/jobs/{UNKNOWN_JOB}/retry'), ('GET', f'/api/v1/artifacts/{art}'),
                  ('GET', f'/api/v1/sources/{art}/annotations'), ('POST', f'/api/v1/sources/{art}/annotations')]
        classes = [(dict(host='evil.example'), 403, 'host_refused'),
                   (dict(headers={'Origin': 'http://evil.example'}), 403, 'origin_refused'),
                   (dict(token=False), 401, 'token_required'),
                   (dict(token='x' * 43), 401, 'token_required')]
        accepted = 0
        for method, path in routes:
            for kwargs, status, code in classes:
                with self.subTest(route=f'{method} {path}', refusal=code):
                    response = env.client.call(method, path, b'{}' if method == 'POST' else None,
                                               raw=b'{}' if method == 'POST' else None, **kwargs)
                    accepted += response.status < 400
                    self.assertEqual((response.status, response.code), (status, code))
        ok = env.client.get('/api/v1/sources', host=f'localhost:{port}',
                            headers={'Origin': f'http://localhost:{port}'})
        self.assertEqual(ok.status, 200)
        self.assertEqual(env.client.get('/api/v1/nope').code, 'route_not_found')
        self.assertEqual(env.client.call('DELETE', '/api/v1/sources').code, 'method_not_allowed')
        self.assertEqual(env.client.get('/api/v1/uploads').code, 'method_not_allowed')
        METRICS['v1_refusals'] = {'routes': len(routes), 'refusal_classes': len(classes),
                                  'requests': len(routes) * len(classes), 'accepted': accepted}

    # 9
    def test_sources_listing_is_path_free_and_bounded(self):
        env = Env(self, start=False)
        bound = self.admit(env.client, 'RUN-A/export/fake.mov')
        second = self.admit(env.client, 'RUN-A/export/fake2.mov')
        unbound = self.admit(env.client, 'RUN-B/export/nomanifest.mov')
        listing = env.client.get('/api/v1/sources')
        self.assertEqual(listing.status, 200)
        self.assertEqual(set(listing.json), {'schema_version', 'sources', 'truncated'})
        self.assertFalse(listing.json['truncated'])
        records = listing.json['sources']
        self.assertEqual([r['source_artifact_id'] for r in records], [unbound, second, bound])
        for record in records:
            with self.subTest(source=record['source_artifact_id']):
                self.assertEqual(set(record), SOURCE_RECORD_KEYS)
                self.assertEqual((record['state'], record['rechecked'], record['origin'], record['kind']),
                                 ('admitted', False, 'run_selector', 'video'))
                self.assertIsNone(record['duration_seconds'])
                self.assertIn('admission does not probe', record['duration_seconds_reason'])
        by_id = {r['source_artifact_id']: r for r in records}
        self.assertIsNone(by_id[unbound]['source_id'])
        self.assertEqual(by_id[unbound]['source_binding'], 'unknown')
        self.assertIn('no run manifest', by_id[unbound]['source_id_reason'])
        self.assertRegex(by_id[bound]['source_id'], r'^src_[0-9a-f]{32}$')
        self.assertEqual(by_id[bound]['sha256'], sha_bytes(FAKE_MOV))
        limited = env.client.get('/api/v1/sources?limit=2')
        self.assertEqual((len(limited.json['sources']), limited.json['truncated']), (2, True))
        self.assertFalse(env.client.get('/api/v1/sources?limit=3').json['truncated'])
        bad = ['limit=0', 'limit=501', 'limit=abc', 'limit=', 'foo=1', 'limit=1&limit=2', 'limit=01', 'limit=-1',
               'limit=1;x', '%zz']
        for query in bad:
            with self.subTest(query=query):
                self.assertEqual(env.client.get(f'/api/v1/sources?{query}').code, 'bad_query')
        self.assertEqual(env.client.get(f'/api/v1/jobs/{UNKNOWN_JOB}?x=1').code, 'bad_query')
        self.assertEqual(env.client.post('/api/v1/sources?limit=1', {'selector': 'RUN-A/export/fake.mov'}).code,
                         'bad_query')
        self.assertEqual(env.client.post('/sources?limit=1', {'selector': 'RUN-A/export/fake.mov'}).code, 'bad_query')
        METRICS['sources_listing'] = {'records': len(records), 'bad_queries_refused': len(bad) + 3,
                                      'selector_or_path_in_body': 0}

    # 10
    def test_upload_bounds_and_typed_refusals_leave_no_staging(self):
        runs_root = self.fresh_runs()
        before = self.pre_existing_digest(runs_root)
        disabled = Env(self, runs_root=runs_root, start=False)
        response = disabled.client.post('/api/v1/uploads', raw=FAKE_MOV, content_type='video/quicktime')
        outcomes = [('disabled', response.status, response.code)]
        self.assertEqual(self.staged_runs(runs_root), ([], []))
        disabled.cleanup()
        env = Env(self, runs_root=runs_root, start=False, allow_uploads=True)
        token = env.server.token
        cases = []
        oversize = raw_http(self, env.port, 'POST', '/api/v1/uploads', token=token,
                            headers={'Content-Type': 'video/quicktime', 'Content-Length': str(MAX_UPLOAD + 1)})
        cases.append(('oversize', oversize))
        cases.append(('bad_type', env.client.post('/api/v1/uploads', raw=b'practice notes, not media',
                                                  content_type='text/plain')))
        cases.append(('chunked', raw_http(self, env.port, 'POST', '/api/v1/uploads', token=token,
                                          headers={'Content-Type': 'video/quicktime',
                                                   'Transfer-Encoding': 'chunked'},
                                          body=b'5\r\nhello\r\n0\r\n\r\n')))
        cases.append(('short_body', raw_http(self, env.port, 'POST', '/api/v1/uploads', token=token,
                                             headers={'Content-Type': 'video/quicktime', 'Content-Length': '1000'},
                                             body=FAKE_MOV[:10], shutdown_write=True)))
        cases.append(('no_ftyp', env.client.post('/api/v1/uploads', raw=b'\x00\x01', content_type='video/quicktime')))
        expected = {'disabled': (403, 'uploads_disabled'), 'oversize': (413, 'upload_too_large'),
                    'bad_type': (415, 'upload_type_refused'), 'chunked': (411, 'length_required'),
                    'short_body': (400, 'upload_incomplete'), 'no_ftyp': (422, 'not_media')}
        for name, response in cases:
            outcomes.append((name, response.status, response.code))
            with self.subTest(case=name):
                self.assertEqual(self.staged_runs(runs_root), ([], []))
        for name, status, code in outcomes:
            with self.subTest(case=name):
                self.assertEqual((status, code), expected[name])
        self.assertEqual(self.pre_existing_digest(runs_root), before)
        METRICS['upload_refusals'] = {'cases': len(outcomes),
                                      'typed': sum((s, c) == expected[n] for n, s, c in outcomes),
                                      'staged_dirs_remaining': 0, 'partial_files_remaining': 0}

    # 11
    def test_upload_success_admits_and_is_idempotent_by_hash(self):
        runs_root = self.fresh_runs()
        before = self.pre_existing_digest(runs_root)
        env = Env(self, runs_root=runs_root, allow_uploads=True)
        first = env.client.post('/api/v1/uploads', raw=FAKE_MOV, content_type='video/quicktime',
                                headers={'X-Upload-Label': 'synthetic fake take'})
        self.assertEqual(first.status, 201, first.json)
        upload, source = first.json['upload'], first.json['source']
        self.assertRegex(upload['upload_id'], r'^upl_[0-9a-f]{16}$')
        self.assertEqual((upload['bytes'], upload['sha256']), (len(FAKE_MOV), sha_bytes(FAKE_MOV)))
        self.assertEqual(source['sha256'], upload['sha256'])
        self.assertFalse(upload['deduplicated'])
        self.assertIsNone(source['source_id'])
        second = env.client.post('/api/v1/uploads', raw=FAKE_MOV, content_type='video/quicktime')
        self.assertEqual(second.status, 200, second.json)
        self.assertEqual(second.json['source']['source_artifact_id'], source['source_artifact_id'])
        self.assertNotEqual(second.json['upload']['upload_id'], upload['upload_id'])
        self.assertTrue(second.json['upload']['deduplicated'])
        staged, partials = self.staged_runs(runs_root)
        self.assertEqual((len(staged), partials), (1, []))
        run_dir = runs_root / 'artifacts' / 'runs' / staged[0]
        self.assertEqual(sorted(str(p.relative_to(run_dir)) for p in run_dir.rglob('*')),
                         ['upload', 'upload-receipt.json', 'upload/source.mov'])
        self.assertEqual(stat.S_IMODE(os.lstat(run_dir).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.lstat(run_dir / 'upload' / 'source.mov').st_mode), 0o600)
        receipt = json.loads((run_dir / 'upload-receipt.json').read_text())
        self.assertEqual((receipt['label'], receipt['sha256']), ('synthetic fake take', sha_bytes(FAKE_MOV)))
        listing = env.client.get('/api/v1/sources').json['sources']
        self.assertEqual([(r['source_artifact_id'], r['origin']) for r in listing],
                         [(source['source_artifact_id'], 'upload')])
        job = self.submit(env.client, source['source_artifact_id'], 'upload-job-0001').json['job_id']
        self.assertEqual(self.wait_job(env.client, job, web_jobs.TERMINAL)['state'], 'succeeded')
        self.assertEqual(self.pre_existing_digest(runs_root), before)
        METRICS['upload_success'] = {'first_status': 201, 'second_status': 200, 'same_source_artifact_id': True,
                                     'distinct_upload_ids': True, 'staged_runs': 1,
                                     'pre_existing_entries_hash_equal': True}

    # 12
    def test_source_media_rehashes_and_refuses_changed_bytes(self):
        runs_root = self.fresh_runs()
        env = Env(self, runs_root=runs_root, start=False)
        source = self.admit(env.client)
        media = env.client.get(f'/api/v1/sources/{source}/media', headers={'Range': 'bytes=0-1'})
        self.assertEqual(media.status, 200)
        self.assertEqual(media.payload, FAKE_MOV)
        self.assertEqual(media.headers['X-Artifact-Sha256'], sha_bytes(FAKE_MOV))
        self.assertEqual(media.headers['Content-Type'], 'video/quicktime')
        self.assertEqual(media.headers['Accept-Ranges'], 'none')
        self.assertTrue(media.headers['Content-Disposition'].startswith('inline;'))
        path = runs_root / 'artifacts' / 'runs' / 'RUN-A' / 'export' / 'fake.mov'
        path.write_bytes(FAKE_MOV[:-1] + b'\x00')  # same size, different last byte
        self.assertEqual(env.client.get(f'/api/v1/sources/{source}/media').code, 'source_stale')
        outside = self.base / f'outside-{self._testMethodName}.mov'
        outside.write_bytes(FAKE_MOV)
        path.unlink()
        path.symlink_to(outside)
        self.assertEqual(env.client.get(f'/api/v1/sources/{source}/media').code, 'confinement_refused')
        path.unlink()
        self.assertEqual(env.client.get(f'/api/v1/sources/{source}/media').code, 'source_missing')
        self.assertEqual(env.client.get(f'/api/v1/sources/{UNKNOWN_ART}/media').code, 'unknown_source')
        self.assertEqual(env.client.get('/api/v1/sources/art_x/media').code, 'malformed_id')
        METRICS['source_media'] = {'rehash_equal': True, 'refusals': ['source_stale', 'confinement_refused',
                                                                      'source_missing', 'unknown_source',
                                                                      'malformed_id'], 'range_supported': False}

    # 13
    def test_iterate_new_job_keeps_earlier_artifacts(self):
        env = Env(self)
        source = self.admit(env.client)
        job_a = self.submit(env.client, source, 'iterate-a-0001').json['job_id']
        a = self.wait_job(env.client, job_a, ('succeeded',))
        a_mp4 = next(x for x in a['artifacts'] if x['role'] == 'share_mp4')
        a_bytes = env.client.get(f'/api/v1/artifacts/{a_mp4["artifact_id"]}').payload
        self.assertEqual(sha_bytes(a_bytes), a_mp4['sha256'])
        conflict = self.submit(env.client, source, 'iterate-a-0001', {'crf': 30})
        self.assertEqual((conflict.status, conflict.code), (409, 'idempotency_conflict'))
        job_b = self.submit(env.client, source, 'iterate-b-0001', {'crf': 30}).json['job_id']
        b = self.wait_job(env.client, job_b, ('succeeded',))
        self.assertNotEqual(job_a, job_b)
        self.assertEqual(b['parameters']['crf'], 30)
        self.assertEqual(a['parameters']['crf'], 27)
        again = env.client.get(f'/api/v1/jobs/{job_a}').json
        self.assertEqual(again['artifacts'], a['artifacts'])
        after = env.client.get(f'/api/v1/artifacts/{a_mp4["artifact_id"]}').payload
        self.assertEqual(sha_bytes(after), sha_bytes(a_bytes))
        self.assertFalse({x['artifact_id'] for x in a['artifacts']} & {x['artifact_id'] for x in b['artifacts']})
        listing = env.client.get(f'/api/v1/jobs?source_artifact_id={source}').json['jobs']
        self.assertEqual([j['job_id'] for j in listing], [job_b, job_a])
        METRICS['iterate_retention'] = {'earlier_artifacts_sha256_equal': '1/1', 'distinct_job_ids': True,
                                        'changed_knob_same_key': 'idempotency_conflict'}

    # 14
    def test_annotation_clock_unknown_then_saved_replayed_and_conflicted(self):
        env = Env(self)
        source = self.admit(env.client)
        unknown = env.client.get(f'/api/v1/sources/{source}/annotations')
        self.assertEqual((unknown.status, unknown.code), (409, 'annotation_source_clock_unknown'))
        early = env.client.post(f'/api/v1/sources/{source}/annotations', self.annotation_request(
            {'revision': 0, 'source_sha256': 'a' * 64, 'manifest_sha256': 'b' * 64}, 'ui-ann-early-0001'))
        self.assertEqual((early.status, early.code), (409, 'annotation_source_clock_unknown'))
        self.assertFalse((env.jobs.state_root / 'annotations').exists())
        job = self.submit(env.client, source, 'clock-job-0001').json['job_id']
        self.wait_job(env.client, job, ('succeeded',))
        read = env.client.get(f'/api/v1/sources/{source}/annotations')
        self.assertEqual(read.status, 200, read.json)
        store, clock = read.json['store'], read.json['clock']
        self.assertEqual((store['revision'], store['annotations'], store['listening_acceptance']),
                         (0, [], 'not_established'))
        self.assertNotIn('replay_receipts', store)
        self.assertEqual((clock['source_start_seconds'], clock['source_end_seconds'], clock['duration_seconds']),
                         (0.0, 2.0, 2.0))
        self.assertIs(clock['player_clock_offset_verified'], False)
        self.assertIn('inference, not a container probe', clock['clock_basis'])
        self.assertEqual(clock['job_id'], job)
        request = self.annotation_request(store, 'ui-ann-save-0001')
        saved = env.client.post(f'/api/v1/sources/{source}/annotations', request)
        self.assertEqual(saved.status, 200, saved.json)
        self.assertEqual(saved.json['mutation']['outcome'], 'saved')
        record = saved.json['store']['annotations'][0]
        self.assertEqual((record['claim_label'], record['musical_verdict']), ('USER REPORTED', 'not_established'))
        self.assertEqual(record['reported_by'], {'actor': 'operator', 'via': 'browser'})
        replay = env.client.post(f'/api/v1/sources/{source}/annotations', request)
        self.assertEqual((replay.status, replay.json['mutation']['outcome']), (200, 'replayed'))
        stale = env.client.post(f'/api/v1/sources/{source}/annotations',
                                self.annotation_request(store, 'ui-ann-stale-0001', revision=0))
        self.assertEqual((stale.status, stale.code), (409, 'stale_annotation_revision'))
        current = saved.json['store']
        bounds = env.client.post(f'/api/v1/sources/{source}/annotations',
                                 self.annotation_request(current, 'ui-ann-oob-0001', start=5.0))
        self.assertEqual((bounds.status, bounds.code), (400, 'source_span_out_of_bounds'))
        second = self.submit(env.client, source, 'clock-job-0002', {'crf': 30}).json['job_id']
        self.wait_job(env.client, second, ('succeeded',))
        self.assertEqual(env.client.get(f'/api/v1/sources/{source}/annotations').json['clock']['job_id'], job)
        METRICS['annotation_semantics'] = {'clock_unknown_refused': True, 'saved': True, 'replayed': True,
                                           'stale_conflict': True, 'out_of_bounds_refused': True,
                                           'clock_no_clobber': True,
                                           'clock_basis': 'synthetic stub extent in this test (fixture, not measured)'}

    # 15
    def test_annotation_authorship_boundary_and_detector_track_distinct(self):
        env = Env(self)
        fresh = self.admit(env.client, 'RUN-A/export/fake2.mov')
        placeholder = {'revision': 0, 'source_sha256': 'a' * 64, 'manifest_sha256': 'b' * 64}
        refused_cases = [
            ('detector_via_browser', dict(basis='detector_hypothesis', reported_by={'actor': 'detector', 'via': 'browser'})),
            ('agent', dict(basis='operator_context', reported_by={'actor': 'agent', 'via': 'agent'})),
            ('operator_via_cli', dict(basis='operator_assertion', reported_by={'actor': 'operator', 'via': 'cli'})),
            ('reference_basis', dict(basis='reference_comparison')),
            ('detector_basis_from_browser', dict(basis='detector_hypothesis')),
        ]
        for name, kwargs in refused_cases:
            with self.subTest(case=name):
                response = env.client.post(f'/api/v1/sources/{fresh}/annotations',
                                           self.annotation_request(placeholder, f'ui-ann-{name.replace("_", "-")}', **kwargs))
                self.assertEqual((response.status, response.code), (400, 'annotation_actor_refused'))
        self.assertFalse((env.jobs.state_root / 'annotations').exists())
        source, _ = self.succeeded_source(env)
        store = env.client.get(f'/api/v1/sources/{source}/annotations').json['store']
        user = env.client.post(f'/api/v1/sources/{source}/annotations',
                               self.annotation_request(store, 'ui-ann-user-0001', start=0.5)).json['store']
        intent = env.client.post(f'/api/v1/sources/{source}/annotations', self.annotation_request(
            user, 'ui-ann-intent-0001', start=1.0, end=1.5, basis='operator_context', kind='phrase_duration',
            note='intended phrase length (synthetic)'))
        self.assertEqual(intent.status, 200, intent.json)
        session = env.server.annotation_session(source)
        seeded = annotation_v2.AnnotationStore(session).write(self.annotation_request(
            intent.json['store'], 'seed-detector-0001', start=1.25, basis='detector_hypothesis',
            reported_by={'actor': 'detector', 'via': 'cli'}, note='synthetic seeded detector record (test fixture)'))
        self.assertEqual(seeded['mutation']['outcome'], 'saved')
        records = env.client.get(f'/api/v1/sources/{source}/annotations').json['store']['annotations']
        operator = [r for r in records if r['reported_by']['actor'] == 'operator']
        detector = [r for r in records if r['basis'] == 'detector_hypothesis']
        self.assertEqual(sorted(r['claim_label'] for r in operator), ['INTENT', 'USER REPORTED'])
        self.assertEqual([r['claim_label'] for r in detector], ['REVIEW'])
        self.assertFalse({id(r) for r in operator} & {id(r) for r in detector})
        self.assertEqual({r['musical_verdict'] for r in records}, {'not_established'})
        METRICS['annotation_authorship'] = {'browser_refusals': len(refused_cases),
                                            'refused_before_store_io': True,
                                            'tracks': {'operator': len(operator), 'detector_review': len(detector)}}

    # 16
    def test_jobs_listing_by_source(self):
        env = Env(self, start=False, queue_limit=8)
        first = self.admit(env.client, 'RUN-A/export/fake.mov')
        second = self.admit(env.client, 'RUN-A/export/fake2.mov')
        ids = [self.submit(env.client, first, f'listing-a-{i:04d}', {'crf': 20 + i}).json['job_id'] for i in range(3)]
        other = self.submit(env.client, second, 'listing-b-0001').json['job_id']
        listing = env.client.get(f'/api/v1/jobs?source_artifact_id={first}')
        self.assertEqual(listing.status, 200)
        jobs = listing.json['jobs']
        self.assertEqual([j['job_id'] for j in jobs], list(reversed(ids)))
        for job in jobs:
            self.assertEqual(set(job), JOB_SUMMARY_KEYS)
            self.assertEqual((job['state'], job['attempt_count'], job['artifact_count']), ('queued', 1, 0))
        self.assertEqual(jobs[0]['parameters']['crf'], 22)
        limited = env.client.get(f'/api/v1/jobs?source_artifact_id={first}&limit=2').json
        self.assertEqual((len(limited['jobs']), limited['truncated']), (2, True))
        self.assertEqual([j['job_id'] for j in env.client.get(f'/api/v1/jobs?source_artifact_id={second}').json['jobs']],
                         [other])
        self.assertEqual(env.client.get(f'/api/v1/jobs?source_artifact_id={UNKNOWN_ART}').json['jobs'], [])
        self.assertEqual(len(env.client.get('/api/v1/jobs').json['jobs']), 4)
        self.assertEqual(env.client.get('/api/v1/jobs?source_artifact_id=art_x').code, 'malformed_id')
        self.assertEqual(env.client.get('/api/v1/jobs?limit=201').code, 'bad_query')
        self.assertEqual(env.client.get('/api/v1/jobs?state=queued').code, 'bad_query')
        METRICS['jobs_listing'] = {'filtered_equal': True, 'bounded': True}


# --------------------------------------------------------------------------- 17 end-to-end walkthrough

def _headless_browser():
    cache = Path.home() / 'Library' / 'Caches' / 'ms-playwright'
    for candidate in sorted(cache.glob('chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell'),
                            reverse=True):
        if os.access(candidate, os.X_OK):
            return candidate, 'playwright chromium headless shell'
    chrome = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    if os.access(chrome, os.X_OK):
        return chrome, 'google chrome --headless=new'
    return None, None


class EndToEndWalkthrough(unittest.TestCase):
    """Upload -> process -> compare -> annotate -> iterate -> download through the built BFF (section 10).

    web_api runs in-process (real share_export dispatcher, uploads enabled, 8 MiB bound) over a synthetic
    runs root; the built BFF is a test-owned `node serve.js` process group killed in tearDownClass.
    """

    POLL_S = 2.0  # WEB_STACK 5.2 base policy
    POLL_BOUND_S = 300

    @classmethod
    def setUpClass(cls):
        cls.skip_reason = None
        if not wj.HAVE_FFMPEG:
            cls.skip_reason = wj.FFMPEG_SKIP
        elif shutil.which('node') is None or shutil.which('pnpm') is None:
            cls.skip_reason = 'node or pnpm not on PATH; BFF walkthrough skipped (not a pass)'
        cls.app = None
        cls.server = None
        cls.jobs = None
        cls._tmp = None
        if cls.skip_reason:
            return
        cls._tmp = tempfile.TemporaryDirectory(prefix='web-ui-e2e-')
        cls.base = Path(cls._tmp.name).resolve()
        cls.R = cls.base / 'R'
        run = wj.make_runs_root(cls.R)
        wj.make_clip(run / 'export' / 'clip.mov')
        cls.clip = (run / 'export' / 'clip.mov').read_bytes()
        cls.runs_before = {entry.name: wj.tree_digest(entry) for entry in (cls.R / 'artifacts' / 'runs').iterdir()}
        cls.wire = []
        cls.jobs = WebJobs(cls.R, cls.base / 'T' / 'state')
        original_submit = cls.jobs.submit

        def recording_submit(body):  # the recording control API: exact bodies the BFF sent
            cls.wire.append(json.loads(json.dumps(body)))
            return original_submit(body)

        cls.jobs.submit = recording_submit
        cls.jobs.start()
        cls.server = web_api.WebAPIServer(cls.jobs, 0, allow_uploads=True, max_upload_bytes=MAX_UPLOAD)
        cls.thread = threading.Thread(target=cls.server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        try:
            if cls.app is not None:
                cls.app.close()
        finally:
            if cls.server is not None:
                cls.server.stop()
                cls.thread.join(timeout=10)
            if cls.jobs is not None:
                cls.jobs.close()
            if cls._tmp is not None:
                cls._tmp.cleanup()

    # ----------------------------------------------------------------- helpers

    def bff(self, method, path, body=None, *, content_type='application/json', headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.app.port, timeout=60)
        sent = {'accept': 'application/json, text/html', **(headers or {})}
        if method == 'POST':
            sent['origin'] = self.app.origin
            sent['content-type'] = content_type
        data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
        try:
            conn.request(method, path, body=data, headers=sent)
            response = conn.getresponse()
            payload = response.read()
            headers_out = {k.lower(): v for k, v in response.getheaders()}
        finally:
            conn.close()
        kind = headers_out.get('content-type', '')
        if kind.startswith(('application/json', 'text/html')):
            for needle in self.forbidden:
                self.assertNotIn(needle.encode(), payload, f'{path} leaked a host path, selector or token')
            self.leak_checked += 1
        parsed = json.loads(payload) if kind.startswith('application/json') else None
        return response.status, headers_out, payload, parsed

    def step(self, name, method, path, fn):
        started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds')
        clock = time.perf_counter()
        status, code, assertions, extra = fn()
        wall_ms = round((time.perf_counter() - clock) * 1000, 1)
        record = {'step': len(self.steps) + 1, 'name': name, 'request': f'{method} {path}', 'http_status': status,
                  'code': code, 'started_at': started, 'wall_ms': wall_ms, 'assertions': assertions, **extra}
        self.steps.append(record)
        failed = [key for key, ok in assertions.items() if not ok]
        self.assertEqual(failed, [], f'step {record["step"]} {name}: {failed}')
        return record

    def poll(self, job_id):
        observed, end = [], time.monotonic() + self.POLL_BOUND_S
        while True:
            status, _, _, job = self.bff('GET', f'/api/jobs/{job_id}')
            self.assertEqual(status, 200, job)
            seen = {'state': job['state'], 'phase': job['phase'],
                    'progress': None if job['progress'] is None else job['progress']['completed']}
            if not observed or observed[-1] != seen:
                observed.append(seen)
            if job['state'] in web_jobs.TERMINAL:
                return job, observed
            self.assertLess(time.monotonic(), end, f'job {job_id} not terminal within {self.POLL_BOUND_S} s')
            time.sleep(self.POLL_S)

    # 17
    def test_walkthrough_upload_process_compare_annotate_iterate_download(self):
        if self.skip_reason:
            METRICS['walkthrough'] = {'skipped': self.skip_reason}
            self.skipTest(self.skip_reason)
        import test_web_stack as ws  # build helpers only (offline frozen install + build)
        build_clock = time.perf_counter()
        ws._ensure_build(self)
        build_s = round(time.perf_counter() - build_clock, 1)
        token = self.server.token
        api_port = self.server.server_address[1]
        type(self).app = ws._App(f'http://127.0.0.1:{api_port}', token=token)
        self.forbidden = sorted({str(self.base), str(self.R), str(ROOT), wj.SENTINEL, token, 'RUN-A/',
                                 '/upload/source', 'web-upload-', f'127.0.0.1:{api_port}'}, key=len)
        self.leak_checked = 0
        self.steps = []
        clip_sha = sha_bytes(self.clip)
        ids = {}

        def s1():
            status, _, payload, _ = self.bff('GET', '/')
            return status, None, {'status_200': status == 200, 'empty_list_rendered': b'data-empty="true"' in payload,
                                  'pilot_banner': 'Local loopback pilot'.encode() in payload}, {}
        self.step('sources_empty', 'GET', '/', s1)

        def s2():
            status, _, _, body = self.bff('POST', '/api/uploads', self.clip, content_type='video/quicktime',
                                          headers={'x-upload-label': 'synthetic e2e clip'})
            ids['source'] = body['source']['source_artifact_id']
            return status, None, {'status_201': status == 201, 'sha_matches_clip': body['upload']['sha256'] == clip_sha,
                                  'admission_sha_equal': body['source']['sha256'] == clip_sha,
                                  'bytes_equal': body['upload']['bytes'] == len(self.clip)}, {
                'source_artifact_id': ids['source'], 'bytes': len(self.clip), 'sha256': clip_sha}
        self.step('upload_admit', 'POST', '/api/uploads', s2)

        def s3():
            refused_status, _, _, refused = self.bff('POST', '/api/sources', {'selector': '/abs/take.mov'})
            status, _, _, body = self.bff('POST', '/api/sources', {'selector': 'RUN-A/export/clip.mov'})
            ids['run_source'] = body['source_artifact_id']
            return status, refused['upstream_code'], {
                'absolute_path_refused_422': refused_status == 422,
                'path_escape_typed': refused['upstream_code'] == 'path_escape',
                'detail_code_host_path_refused': refused['upstream_detail_code'] == 'host_path_refused',
                'selector_admitted_201': status == 201, 'same_bytes_as_upload': body['sha256'] == clip_sha}, {
                'refusal': {'http_status': refused_status, 'upstream_code': refused['upstream_code'],
                            'upstream_detail_code': refused['upstream_detail_code']}}
        self.step('selector_refusal_then_admit', 'POST', '/api/sources', s3)

        key_a = 'ui-' + os.urandom(16).hex()

        def s4():
            status, _, _, job = self.bff('POST', '/api/jobs', {'source_artifact_id': ids['source'], 'parameters': {},
                                                               'idempotency_key': key_a})
            ids['A'] = job['job_id']
            replay_status, _, _, replay = self.bff('POST', '/api/jobs', {
                'source_artifact_id': ids['source'], 'parameters': {}, 'idempotency_key': key_a})
            return status, None, {'status_202': status == 202, 'state_queued_or_running': job['state'] in ('queued', 'running'),
                                  'double_submit_replays_same_job': replay_status == 200 and replay['job_id'] == job['job_id'],
                                  'v1_envelope_present': job['tool_envelope']['tool'] == 'share_export'}, {
                'job_id': job['job_id'], 'state_at_submit': job['state']}
        self.step('submit_defaults', 'POST', '/api/jobs', s4)

        def s5():
            job, observed = self.poll(ids['A'])
            ids['A_job'] = job
            return 200, job['reason_code'], {'terminal': job['state'] in web_jobs.TERMINAL,
                                             'succeeded': job['state'] == 'succeeded',
                                             'eta_unknown': job['eta_seconds'] is None}, {
                'observed_sequence': observed, 'terminal_state': job['state'],
                'poll_policy_s': self.POLL_S}
        self.step('poll_to_terminal', 'GET', f'/api/jobs/{ids["A"]}', s5)

        def s6():
            status, _, payload, _ = self.bff('GET', f'/jobs/{ids["A"]}')
            return status, None, {'status_200': status == 200, 'compare_bound': b'data-compare="bound"' in payload,
                                  'source_player': b'data-player="source"' in payload,
                                  'processed_player': b'data-player="processed"' in payload,
                                  'fixed_note': b'Levels are not matched by this page.' in payload,
                                  'low_register_note': b'~32 Hz low-string preservation not measured' in payload,
                                  'unknowns_block': b'data-unknowns-block="true"' in payload}, {}
        self.step('compare_ssr', 'GET', f'/jobs/{ids["A"]}', s6)

        def s7():
            status, headers, payload, _ = self.bff('GET', f'/api/sources/{ids["source"]}/media')
            return status, None, {'status_200': status == 200, 'rehash_equal_admission': sha_bytes(payload) == clip_sha,
                                  'header_sha_equal': headers.get('x-artifact-sha256') == clip_sha,
                                  'inline': headers.get('content-disposition', '').startswith('inline'),
                                  'no_ranges': headers.get('accept-ranges') == 'none'}, {'bytes': len(payload)}
        self.step('source_media', 'GET', f'/api/sources/{ids["source"]}/media', s7)

        def s8():
            status, _, _, read = self.bff('GET', f'/api/sources/{ids["source"]}/annotations')
            store, clock = read['store'], read['clock']
            player_time = 1.0
            start = round(player_time + clock['source_start_seconds'], 6)
            request = {'schema_version': 2, 'expected_revision': store['revision'],
                       'idempotency_key': 'ui-ann-' + os.urandom(16).hex(), 'source_sha256': store['source_sha256'],
                       'manifest_sha256': store['manifest_sha256'],
                       'annotation': {'kind': 'rhythm_timing', 'basis': 'operator_assertion', 'status': 'needs_review',
                                      'source_span': {'start_seconds': start, 'end_seconds': start, 'extent_known': False},
                                      'reported_by': {'actor': 'operator', 'via': 'browser'},
                                      'operator_certainty': 'uncertain',
                                      'operator_quote': 'synthetic walkthrough note', 'note': 'e2e fixture note'}}
            saved_status, _, _, saved = self.bff('POST', f'/api/sources/{ids["source"]}/annotations', request)
            replay_status, _, _, replay = self.bff('POST', f'/api/sources/{ids["source"]}/annotations', request)
            stale = dict(request, idempotency_key='ui-ann-' + os.urandom(16).hex())
            stale_status, _, _, stale_body = self.bff('POST', f'/api/sources/{ids["source"]}/annotations', stale)
            record = saved['store']['annotations'][0]
            return saved_status, stale_body['upstream_code'], {
                'clock_known_200': status == 200, 'saved': saved['mutation']['outcome'] == 'saved',
                'user_reported_label': record['claim_label'] == 'USER REPORTED',
                'verdict_not_established': record['musical_verdict'] == 'not_established',
                'replayed': replay_status == 200 and replay['mutation']['outcome'] == 'replayed',
                'stale_409': stale_status == 409 and stale_body['upstream_code'] == 'stale_annotation_revision',
                'player_clock_unverified': clock['player_clock_offset_verified'] is False}, {
                'clock': {k: clock[k] for k in ('source_start_seconds', 'source_end_seconds', 'duration_seconds',
                                                'clock_basis', 'player_clock_offset_verified')},
                'note_source_seconds': start}
        self.step('annotate', 'POST', f'/api/sources/{ids["source"]}/annotations', s8)

        a_artifacts_before = ids['A_job']['artifacts']

        def s9():
            status, _, _, job = self.bff('POST', '/api/jobs', {'source_artifact_id': ids['source'], 'parameters': {'crf': 30},
                                                               'idempotency_key': 'ui-' + os.urandom(16).hex()})
            ids['B'] = job['job_id']
            final, observed = self.poll(ids['B'])
            ids['B_job'] = final
            return status, final['reason_code'], {'status_202': status == 202, 'new_job': ids['B'] != ids['A'],
                                                  'crf_30': final['parameters']['crf'] == 30,
                                                  'terminal': final['state'] in web_jobs.TERMINAL}, {
                'job_id': ids['B'], 'terminal_state': final['state'], 'observed_sequence': observed}
        self.step('iterate_changed_knob', 'POST', '/api/jobs', s9)

        def s10():
            status, _, _, listing = self.bff('GET', f'/api/sources/{ids["source"]}/jobs')
            _, _, _, again = self.bff('GET', f'/api/jobs/{ids["A"]}')
            listed = [j['job_id'] for j in listing['jobs']]
            return status, None, {'status_200': status == 200, 'a_and_b_listed': listed[:2] == [ids['B'], ids['A']],
                                  'a_artifacts_unchanged': again['artifacts'] == a_artifacts_before}, {'listed': listed}
        self.step('jobs_by_source', 'GET', f'/api/sources/{ids["source"]}/jobs', s10)

        def s11():
            roles = {a['role']: a for a in ids['A_job']['artifacts']}
            share = roles['share_mp4']
            status, headers, payload, _ = self.bff('GET', f'/api/artifacts/{share["artifact_id"]}')
            p_status, _, _, private = self.bff('GET', f'/api/artifacts/{roles["share_receipt"]["artifact_id"]}')
            ids['A_share_sha'] = share['sha256']
            return status, private['upstream_code'], {
                'status_200': status == 200, 'bytes_sha_equal_header': sha_bytes(payload) == headers.get('x-artifact-sha256'),
                'header_equal_projection': headers.get('x-artifact-sha256') == share['sha256'],
                'size_equal_projection': len(payload) == share['size_bytes'],
                'receipt_private_403': p_status == 403 and private['upstream_code'] == 'artifact_private'}, {
                'share_mp4': {'artifact_id': share['artifact_id'], 'sha256': share['sha256'], 'bytes': share['size_bytes']}}
        self.step('download', 'GET', '/api/artifacts/{share_mp4}', s11)

        def s12():
            status, _, _, job = self.bff('POST', '/api/jobs', {'source_artifact_id': ids['source'], 'parameters': {'crf': 31},
                                                               'idempotency_key': 'ui-' + os.urandom(16).hex()})
            ids['C'] = job['job_id']
            c_status, _, _, cancel = self.bff('POST', f'/api/jobs/{ids["C"]}/cancel', {})
            final, observed = self.poll(ids['C'])
            return c_status, final['reason_code'], {
                'submitted_202': status == 202, 'cancel_accepted': c_status in (200, 202),
                'cancelled': final['state'] == 'cancelled', 'no_artifacts': final['artifacts'] == []}, {
                'job_id': ids['C'], 'state_at_cancel': cancel['state'], 'cancel_http_status': c_status,
                'observed_sequence': observed}
        self.step('cancel', 'POST', '/api/jobs/{C}/cancel', s12)

        screenshots, skipped = [], None
        browser, browser_kind = _headless_browser()
        if browser is None:
            skipped = 'no headless Chromium (Playwright cache) or Google Chrome found on this host'
        else:
            screens = OUT_DIR / 'screens'
            screens.mkdir(parents=True, exist_ok=True)
            for name, path in (('sources', '/'), ('source', f'/sources/{ids["source"]}'), ('job', f'/jobs/{ids["A"]}')):
                target = screens / f'{name}.png'
                with contextlib.suppress(FileNotFoundError):
                    target.unlink()
                profile = tempfile.mkdtemp(prefix='web-ui-shot-', dir=self.base)
                clock = time.perf_counter()
                proc = subprocess.Popen([str(browser), '--headless=new', '--disable-gpu', '--no-first-run',
                                         '--no-default-browser-check', f'--user-data-dir={profile}',
                                         '--window-size=1280,900', f'--screenshot={target}',
                                         f'{self.app.origin}{path}'],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                try:
                    proc.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    pass
                finally:
                    with contextlib.suppress(ProcessLookupError, PermissionError):  # Darwin zombie-only group
                        os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=10)
                if target.is_file() and target.stat().st_size > 0:
                    screenshots.append({'name': f'{name}.png', 'route': path.split('/')[1] or 'index',
                                        'bytes': target.stat().st_size, 'sha256': wj.sha_file(target),
                                        'wall_ms': round((time.perf_counter() - clock) * 1000, 1)})
            if not screenshots:
                skipped = f'{browser_kind} produced no screenshot'
        self.steps.append({'step': 13, 'name': 'screenshots_optional', 'request': 'headless browser GET / , /sources/{id}, /jobs/{A}',
                           'http_status': None, 'code': None, 'started_at': None, 'wall_ms': None,
                           'assertions': {}, 'captured': len(screenshots)})

        # Wire parity: the exact bodies the BFF sent validate like the CLI/MCP call.
        wire_ok = []
        for body in self.wire:
            closed = set(body) == {'tool', 'source_artifact_id', 'parameters', 'idempotency_key'}
            keyed = re.fullmatch(r'ui-[0-9a-f]{32}', body['idempotency_key']) is not None
            wire_ok.append(closed and keyed and cli_verdict(body['parameters']) == 'accept')
        self.assertTrue(wire_ok and all(wire_ok), self.wire)
        runs_after = {entry.name: wj.tree_digest(entry) for entry in (self.R / 'artifacts' / 'runs').iterdir()}
        added = sorted(set(runs_after) - set(self.runs_before))
        preexisting_equal = all(runs_after.get(name) == digest for name, digest in self.runs_before.items())
        self.assertTrue(preexisting_equal)
        self.assertEqual(len(added), 1)
        self.assertTrue(added[0].startswith('web-upload-'))
        facts = host_facts()
        receipt = {
            'receipt': 'web_ui_binding-walkthrough', 'lane': 'web_ui_binding', 'sprint': '20261006-s2', 'tracker': 'TIN-5615',
            'spec': 'docs/spec/sprints/WEB_UI_S2.md section 10', 'claim_class': 'measurement_this_host_only',
            'slo': 'not_claimed', 'daemon': False, 'real_take_used': False,
            'fixture': 'synthetic 2 s testsrc2 320x240@24 + sine 32.70 Hz 44.1 kHz, H.264/AAC MOV (C1 content; no spectral claim)',
            'control_api': 'scripts/web_api.py in-process, real share_export dispatcher, uploads enabled, 8 MiB bound',
            'bff': 'built web/ via node serve.js (HOST=127.0.0.1, ephemeral PORT, URL + token env), test-owned process group',
            'build_seconds_this_run': build_s,
            'steps_completed': f'{sum(1 for s in self.steps if s["step"] <= 12)}/12',
            'steps': self.steps,
            'wire_bodies': {'captured': len(self.wire), 'closed_shape_and_cli_valid': sum(wire_ok)},
            'leak_scan': {'responses_scanned': self.leak_checked, 'hits': 0},
            'confinement': {'preexisting_runs_entries_hash_equal': preexisting_equal, 'added_runs': len(added),
                            'added_kind': 'upload staging run (name prefix web-upload)'},
            'screenshots': screenshots,
            **({'screenshots_skipped_reason': skipped} if skipped else {}),
            'screenshot_note': 'headless captures after load; they do not prove hydration, playback or accessibility',
            'browser_playback_verified': None,
            'browser_playback_verified_reason': 'no media playback was observed in a browser; Range requests unsupported in S2',
            'hydration_verified': None,
            'hydration_verified_reason': 'no client-side assertion ran in a browser; screenshots are visual captures only',
            'level_matched': False, 'listening_comparison': 'not_established', 'low_register_preservation': None,
            'musical_verdicts': 'none made',
            'host': facts,
        }
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / 'walkthrough.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
        public = json.dumps(receipt, indent=2, sort_keys=True)
        for needle in self.forbidden + [str(Path.home()), str(OUT_DIR)]:
            self.assertNotIn(needle, public)
        self.assertIsNone(re.search(r'127\.0\.0\.1:\d+', public))
        (OUT_DIR / 'walkthrough-public.json').write_text(public + '\n')
        METRICS['walkthrough'] = {'steps_completed': receipt['steps_completed'], 'screenshots': len(screenshots)}


@unittest.skipUnless(os.environ.get('WEB_UI_DEMO') == '1' and wj.HAVE_FFMPEG and shutil.which('node')
                     and shutil.which('pnpm'), 'opt-in read-only demo walkthrough (WEB_UI_DEMO=1, FFmpeg, node, pnpm)')
class DemoWalkthrough(unittest.TestCase):
    """Optional: admit the accepted FULLER run's export by selector into a lane-local state root (uploads off).

    Read-only on the accepted run (tree hash before == after). The real take is never opened. A share_export
    rejection is a valid recorded outcome; the compare view must then show the Prototype label.
    """

    RUN = '20261006T041633Z-990aa1bd6737'
    SELECTOR = f'{RUN}/export/cleaned-video.mov'

    def test_demo_walkthrough_read_only(self):
        import test_web_stack as ws
        runs_root = Path(os.environ.get('WEB_UI_DEMO_RUNS_ROOT', str(ROOT.parents[2]))).resolve()
        run_dir = runs_root / 'artifacts' / 'runs' / self.RUN
        if not (run_dir / 'export' / 'cleaned-video.mov').is_file():
            self.skipTest('accepted demo run export not present on this host')
        before = wj.tree_digest(run_dir)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        state = OUT_DIR / f'demo-state-{stamp}'
        jobs = WebJobs(runs_root, state)
        jobs.start()
        server = web_api.WebAPIServer(jobs, 0, allow_uploads=False)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.1}, daemon=True)
        thread.start()
        app = None
        try:
            ws._ensure_build(self)
            app = ws._App(f'http://127.0.0.1:{server.server_address[1]}', token=server.token)
            headers = {'content-type': 'application/json', 'origin': app.origin}
            status, _, payload, _ = app.request('POST', '/api/sources', json.dumps({'selector': self.SELECTOR}).encode(), headers)
            self.assertIn(status, (200, 201), payload[:300])
            source = json.loads(payload)['source_artifact_id']
            start = time.perf_counter()
            status, _, payload, _ = app.request('POST', '/api/jobs', json.dumps({
                'source_artifact_id': source, 'parameters': {}, 'idempotency_key': 'ui-' + os.urandom(16).hex()}).encode(), headers)
            self.assertEqual(status, 202, payload[:300])
            job_id = json.loads(payload)['job_id']
            end = time.monotonic() + 1100
            while True:
                _, _, payload, _ = app.request('GET', f'/api/jobs/{job_id}')
                job = json.loads(payload)
                if job['state'] in web_jobs.TERMINAL:
                    break
                self.assertLess(time.monotonic(), end)
                time.sleep(5)
            wall = round(time.perf_counter() - start, 3)
            _, _, page, _ = app.request('GET', f'/jobs/{job_id}')
            compare = 'bound' if b'data-compare="bound"' in page else 'absent' if b'data-compare="absent"' in page else 'missing'
            if job['state'] != 'succeeded':
                self.assertEqual(compare, 'absent')
                self.assertIn(b'Comparison data absent', page)
            for needle in (str(runs_root), str(ROOT), server.token, self.SELECTOR):
                self.assertNotIn(needle.encode(), page)
                self.assertNotIn(needle.encode(), payload)
        finally:
            if app is not None:
                app.close()
            server.stop()
            thread.join(timeout=10)
            jobs.close()
        after = wj.tree_digest(run_dir)
        self.assertEqual(after, before)
        receipt = {'receipt': 'web_ui_binding-demo-walkthrough', 'claim_class': 'structural_delivery_check',
                   'experiment': False, 'real_take_opened': False, 'uploads_enabled': False,
                   'accepted_run': self.RUN, 'selector_admitted_read_only': True,
                   'accepted_run_tree': {'before_sha256': before[0], 'after_sha256': after[0], 'entries': before[1],
                                         'unchanged': before == after},
                   'job': {'state': job['state'], 'reason_code': job['reason_code'],
                           'worker_checks': [a['worker_checks'] for a in job['attempts']],
                           'artifacts': len(job['artifacts']), 'submit_to_terminal_seconds': wall},
                   'compare_view': compare, 'host': host_facts(),
                   'not_claimed': ['listening', 'low-register (~32 Hz) preservation', 'tone', 'musical correctness',
                                   'derivative adoption']}
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / 'demo-walkthrough.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
        METRICS['demo_walkthrough'] = {'state': job['state'], 'compare_view': compare}


def tearDownModule():
    target = os.environ.get('WEB_UI_METRICS')
    if target:
        Path(target).write_text(json.dumps(METRICS, indent=2, sort_keys=True, default=str) + '\n')


if __name__ == '__main__':
    unittest.main()
