"""S2 web_jobs: durable local job store, bounded supervisor and loopback control API.

Contract: docs/spec/sprints/WEB_JOBS_S2.md. Tests run against HTTP on an
ephemeral loopback port, so they double as the conformance suite for a later
FastAPI drop-in. FFmpeg-dependent cases skip (reported, never counted as pass)
when the qualified FFMPEG/FFPROBE env is unset. No randomness is asserted.
"""
from __future__ import annotations

import datetime
import hashlib
import http.client
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import sqlite3
import stat
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import artifact_ids  # noqa: E402
import web_api  # noqa: E402
import web_jobs  # noqa: E402
from web_jobs import WebJobs, WebJobsError  # noqa: E402

FFMPEG = os.environ.get('FFMPEG')
FFPROBE = os.environ.get('FFPROBE')
HAVE_FFMPEG = bool(FFMPEG and FFPROBE and Path(FFMPEG).is_file() and Path(FFPROBE).is_file())
FFMPEG_SKIP = 'qualified FFMPEG/FFPROBE env unset; real-dispatcher case skipped (not a pass)'
SENTINEL = '/private/sentinel/original-take-never-served.mov'
FIXTURE_SOURCE_SHA = hashlib.sha256(b'fixture-source').hexdigest()
FAKE_MOV = b'\x00\x00\x00\x14ftypqt  \x00\x00\x02\x00qt  ' + bytes(range(256)) * 16
METRICS = {}

STUB = r'''
import hashlib, json, os, signal, subprocess, sys, time
mode, beat, source, output = sys.argv[1:5]
def on_term(signum, frame):
    with open(beat + '.sigterm', 'w') as handle:
        handle.write(str(os.getpid()))
    os._exit(143)
signal.signal(signal.SIGTERM, on_term)
def sha(path):
    with open(path, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()
if mode == 'sleep':
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    with open(beat + '.tmp', 'w') as handle:
        json.dump({'pid': os.getpid(), 'child': child.pid}, handle)
    os.replace(beat + '.tmp', beat)
    end = time.time() + 60
    while time.time() < end:
        time.sleep(0.05)
    sys.exit(3)
if mode == 'reject':
    print(json.dumps({'status': 'rejected', 'error': 'stub rejection', 'code': 'stub_rejected'}))
    sys.exit(0)
if mode == 'garbage':
    print('not json')
    sys.exit(0)
src = os.path.realpath(source)
out = os.path.realpath(output)
with open(src, 'rb') as handle:
    data = b'\x00\x00\x00\x18ftypisom' + hashlib.sha256(handle.read()).digest() * 64
with open(out, 'xb') as handle:
    handle.write(data)
receipt = out + '.receipt.json'
with open(receipt, 'x') as handle:
    json.dump({'stub': True, 'output_sha256': hashlib.sha256(data).hexdigest()}, handle)
os.makedirs(os.path.join(os.path.dirname(out), '.share-export-stub'), exist_ok=True)
with open(beat, 'w') as handle:
    json.dump({'pid': os.getpid(), 'mode': mode}, handle)
print(json.dumps({'schema_version': 1, 'status': 'exported_unreviewed',
                  'source': {'path': src, 'sha256': sha(src), 'bytes': os.path.getsize(src)},
                  'output': {'path': out, 'sha256': sha(out), 'bytes': os.path.getsize(out),
                             'receipt_path': receipt, 'receipt_sha256': sha(receipt)},
                  'master_adopted': False, 'listening_accepted': False}))
'''


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_digest(root, mtimes=True):
    """Digest of paths, types, sizes, (mtime_ns) and sha256 without following links or opening FIFOs."""
    rows = []
    root = Path(root)
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        for name in sorted(dirnames + filenames):
            path = Path(directory) / name
            info = os.lstat(path)
            rel = str(path.relative_to(root))
            if stat.S_ISLNK(info.st_mode):
                rows.append([rel, 'link', os.readlink(path)])
            elif stat.S_ISREG(info.st_mode):
                rows.append([rel, 'file', info.st_size, info.st_mtime_ns if mtimes else None, sha_file(path)])
            elif stat.S_ISDIR(info.st_mode):
                rows.append([rel, 'dir'])
            else:
                rows.append([rel, 'other', stat.S_IFMT(info.st_mode)])
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(), len(rows)


def make_clip(path):
    command = [FFMPEG, '-nostdin', '-hide_banner', '-loglevel', 'error', '-n',
               '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=24:duration=2',
               '-f', 'lavfi', '-i', 'sine=frequency=32.70:sample_rate=44100:duration=2',
               '-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p', '-threads', '2',
               '-c:a', 'aac', '-b:a', '96k', '-shortest', '-f', 'mov', str(path)]
    subprocess.run(command, check=True, capture_output=True, timeout=60)


def make_runs_root(root, run='RUN-A'):
    run_dir = Path(root) / 'artifacts' / 'runs' / run
    (run_dir / 'export').mkdir(parents=True)
    (run_dir / 'manifest.json').write_text(json.dumps({'source': {'sha256': FIXTURE_SOURCE_SHA, 'path': SENTINEL}}))
    (run_dir / 'export' / 'fake.mov').write_bytes(FAKE_MOV)
    return run_dir


class StubBuilder:
    """Test seam: argv for a stub worker (worker_kind test_stub). Modes are popped per launch."""

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
        return [sys.executable, '-c', STUB, mode, str(beat), args['source'], args['output']]


class Response:
    def __init__(self, status, headers, payload):
        self.status = status
        self.headers = headers
        self.payload = payload
        content_type = headers.get('Content-Type', '')
        self.json = json.loads(payload) if payload and content_type.startswith('application/json') else None

    @property
    def code(self):
        return (self.json or {}).get('code')


class Client:
    def __init__(self, test, server):
        self.test = test
        self.server = server

    @property
    def port(self):
        return self.server.server_address[1]

    def call(self, method, path, body=None, *, raw=None, headers=None, host=None, token=None,
             content_type='application/json'):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=30)
        sent = {'Host': host if host is not None else f'127.0.0.1:{self.port}'}
        bearer = self.server.token if token is None else token
        if bearer is not False:
            sent['Authorization'] = 'Bearer ' + bearer
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        if data is not None and content_type:
            sent['Content-Type'] = content_type
        sent.update(headers or {})
        try:
            connection.request(method, path, body=data, headers=sent)
            response = connection.getresponse()
            result = Response(response.status, dict(response.getheaders()), response.read())
        finally:
            connection.close()
        self.test.assert_no_leak(result)
        return result

    def get(self, path, **kwargs):
        return self.call('GET', path, **kwargs)

    def post(self, path, body=None, **kwargs):
        return self.call('POST', path, {} if body is None and 'raw' not in kwargs else body, **kwargs)


def sigkill_own_group(pgid):
    """SIGKILL a process group this test's own WebJobs instance created.

    Darwin's killpg(2) returns EPERM (not ESRCH) when every member of the group is
    already a zombie awaiting reaping, which happens when a previous SIGKILL to the
    same group landed before ``Popen.poll()`` reaped the leader. EPERM therefore means
    "nothing left alive to signal" for a test-owned group; it is not a foreign process.
    The caller's ``process.wait(timeout=...)`` still fails if the leader survives.
    """
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


class Env:
    """In-process WebJobs + loopback server on an ephemeral port (no daemon)."""

    def __init__(self, test, state_root, *, runs_root=None, builder='stub', start=True, **kwargs):
        if builder == 'stub':
            builder = StubBuilder(Path(state_root).parent / (Path(state_root).name + '-beats'))
        self.builder = builder
        self.jobs = WebJobs(runs_root or test.R, state_root, command_builder=builder, **kwargs)
        if start:
            self.jobs.start()
        self.server = web_api.WebAPIServer(self.jobs, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.05},
                                       daemon=True)
        self.thread.start()
        self.client = Client(test, self.server)
        self.stopped = False
        test.addCleanup(self.cleanup)

    def stop(self):
        """Server shutdown + store close: cancels nothing (a running attempt is abandoned)."""
        if not self.stopped:
            self.stopped = True
            self.server.stop()
            self.thread.join(timeout=10)
            self.jobs.close()

    def kill_detached(self):
        """The test kills only the stub processes its own WebJobs instance started."""
        for process in self.jobs._detached:
            if process.poll() is None:
                sigkill_own_group(process.pid)
            process.wait(timeout=10)  # a genuinely surviving leader still fails the test here

    def cleanup(self):
        self.stop()
        self.kill_detached()


class WebJobsTestBase(unittest.TestCase):
    leak_checks = 0

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix='web-jobs-test-')
        cls.raw_base = cls._tmp.name
        cls.base = Path(cls._tmp.name).resolve()
        cls.R = cls.base / 'R'
        run = make_runs_root(cls.R)
        (run / 'notes.txt').write_text('practice notes, not media')
        (run / 'hashbang.mov').write_bytes(b'#!/bin/sh\necho refused\n' + FAKE_MOV)
        (run / 'exec.mov').write_bytes(FAKE_MOV)
        os.chmod(run / 'exec.mov', 0o755)
        outside = cls.base / 'outside.mov'
        outside.write_bytes(FAKE_MOV)
        (run / 'escape.mov').symlink_to(outside)
        (run / 'take.partial.mov').write_bytes(FAKE_MOV)
        os.mkfifo(run / 'pipe.mov')
        (run / 'bad.mov').write_bytes(b'\x00\x01')
        cls.clip_available = False
        if HAVE_FFMPEG:
            make_clip(run / 'export' / 'clip.mov')
            cls.clip_available = True
        cls.runs_digest = tree_digest(cls.R / 'artifacts' / 'runs')
        cls.forbidden = sorted({str(cls.base), cls.raw_base, str(cls.R), SENTINEL, str(ROOT)}, key=len)
        cls.counter = 0

    @classmethod
    def tearDownClass(cls):
        try:
            after = tree_digest(cls.R / 'artifacts' / 'runs')
            if after != cls.runs_digest:
                raise AssertionError('artifacts/runs fixture tree changed during the test class')
            METRICS.setdefault('runs_tree_unchanged_classes', []).append(cls.__name__)
        finally:
            cls._tmp.cleanup()

    # ----------------------------------------------------------------- helpers

    def assert_no_leak(self, response):
        blob = response.payload + json.dumps(response.headers).encode()
        for needle in self.forbidden:
            self.assertNotIn(needle.encode(), blob, 'response leaked a host path or selector-private string')
        type(self).leak_checks += 1
        METRICS['responses_checked_for_paths'] = METRICS.get('responses_checked_for_paths', 0) + 1

    def state(self, label='s'):
        type(self).counter += 1
        return self.base / 'states' / f'{self._testMethodName}-{label}-{type(self).counter}'

    def admit(self, client, selector='RUN-A/export/fake.mov'):
        response = client.post('/sources', {'selector': selector})
        self.assertIn(response.status, (200, 201), response.json)
        return response.json['source_artifact_id']

    def submit(self, client, source, key, parameters=None):
        body = {'tool': 'share_export', 'source_artifact_id': source, 'idempotency_key': key}
        if parameters is not None:
            body['parameters'] = parameters
        return client.post('/jobs', body)

    def wait_job(self, client, job_id, states, timeout=30):
        end = time.monotonic() + timeout
        while True:
            response = client.get(f'/jobs/{job_id}')
            self.assertEqual(response.status, 200, response.json)
            if response.json['state'] in states:
                return response.json
            if time.monotonic() > end:
                self.fail(f'job did not reach {states}; last state {response.json["state"]}')
            time.sleep(0.05)

    def wait_beat(self, builder, index=-1, timeout=15):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if builder.beats:
                beat = builder.beats[index]
                if beat.exists():
                    return json.loads(beat.read_text())
            time.sleep(0.02)
        self.fail('stub heartbeat not observed')

    def wait_gone(self, pid, timeout=10):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            time.sleep(0.02)
        return False

    def kill_own_stub(self, env, pid):
        """Simulated crash cleanup: the test kills the stub group its own instance created."""
        sigkill_own_group(pid)
        env.kill_detached()

    def db(self, state_root):
        connection = sqlite3.connect(Path(state_root) / 'jobs.sqlite3', isolation_level=None)
        self.addCleanup(connection.close)
        return connection


class WebJobsTests(WebJobsTestBase):

    # 1
    def test_schema_version_wal_and_triggers_installed(self):
        state = self.state()
        jobs = WebJobs(self.R, state, command_builder=StubBuilder(self.base / 'beats-schema'))
        self.addCleanup(jobs.close)
        connection = self.db(state)
        self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], 2)  # S3 schema v2
        self.assertEqual(connection.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
        triggers = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
        self.assertTrue({'jobs_state_transition', 'attempts_state_transition', 'artifacts_no_update',
                         'artifacts_no_delete', 'events_no_update', 'events_no_delete'} <= triggers)
        self.assertEqual(stat.S_IMODE(os.lstat(state).st_mode), 0o700)
        connection.execute("INSERT INTO sources VALUES ('art_" + '1' * 32 + "', 'RUN-A/x.mov', '" + 'a' * 64
                           + "', 1, 'video', NULL, 'unknown', 'now')")
        reach = {'queued': [], 'running': ['running'], 'succeeded': ['running', 'succeeded'],
                 'failed': ['running', 'failed'], 'cancelled': ['cancelled'],
                 'interrupted': ['running', 'interrupted']}
        accepted_illegal = refused_legal = checked = number = 0
        for table, allowed in (('jobs', web_jobs.JOB_TRANSITIONS), ('attempts', web_jobs.ATTEMPT_TRANSITIONS)):
            for start in web_jobs.STATES:
                for end in web_jobs.STATES:
                    number += 1
                    job_id = f'job_{number:032x}'
                    connection.execute("INSERT INTO jobs VALUES (?, ?, 'f', 'share_export', 'art_" + '1' * 32
                                       + "', '{}', 'r', 'queued', NULL, 0, 'now', 'now', NULL)",
                                       (job_id, f'key-{number:08d}'))
                    connection.execute("INSERT INTO attempts(job_id, attempt, state) VALUES (?, 1, 'queued')",
                                       (job_id,))
                    for step in reach[start]:
                        connection.execute(f'UPDATE {table} SET state = ? WHERE job_id = ?', (step, job_id))
                    try:
                        connection.execute(f'UPDATE {table} SET state = ? WHERE job_id = ?', (end, job_id))
                        accepted = True
                    except sqlite3.DatabaseError:
                        accepted = False
                    checked += 1
                    if (start, end) in allowed:
                        refused_legal += not accepted
                    else:
                        accepted_illegal += accepted
        self.assertEqual((accepted_illegal, refused_legal, checked), (0, 0, 72))
        with self.assertRaises(sqlite3.DatabaseError):
            connection.execute("INSERT INTO jobs VALUES ('job_" + 'f' * 32 + "', 'key-insert-x', 'f', 'share_export', "
                               "'art_" + '1' * 32 + "', '{}', 'r', 'running', NULL, 0, 'now', 'now', NULL)")
        connection.execute("INSERT INTO artifacts VALUES ('art_" + '2' * 32 + "', 'job_" + '0' * 31 + "1', 1, "
                           "'share_mp4', 'jobs/x/attempt-1/share.mp4', '" + 'b' * 64 + "', 1, 'video/mp4', 'now')")
        for statement in ("UPDATE artifacts SET size_bytes = 2", 'DELETE FROM artifacts',
                          "UPDATE events SET reason_code = 'x'", 'DELETE FROM events'):
            connection.execute("INSERT INTO events(job_id, attempt, from_state, to_state, reason_code, at) "
                               "VALUES ('job_x', 1, NULL, 'queued', 'test', 'now')")
            with self.assertRaises(sqlite3.DatabaseError):
                connection.execute(statement)
        METRICS['illegal_transitions'] = {'pairs_checked': checked, 'illegal_pairs': 72 - 9 - 7,
                                          'illegal_accepted': accepted_illegal, 'legal_refused': refused_legal}

    # 2
    def test_server_binds_loopback_and_refuses_bad_host_origin_and_token(self):
        env = Env(self, self.state())
        client = env.client
        self.assertEqual(env.server.server_address[0], '127.0.0.1')
        path = '/jobs/job_' + '0' * 32
        cases = [
            (dict(host='evil.example'), 403, 'host_refused'),
            (dict(host=f'127.0.0.1:{client.port + 1 if client.port < 65535 else 1}'), 403, 'host_refused'),
            (dict(host='evil.example', token=False), 403, 'host_refused'),
            (dict(headers={'Origin': 'http://evil.example'}), 403, 'origin_refused'),
            (dict(headers={'Origin': f'https://127.0.0.1:{client.port}'}), 403, 'origin_refused'),
            (dict(token=False), 401, 'token_required'),
            (dict(token='x' * 43), 401, 'token_required'),
            (dict(headers={'Authorization': 'Basic Zm9vOmJhcg=='}), 401, 'token_required'),
            (dict(), 404, 'unknown_job'),
            (dict(host=f'localhost:{client.port}', headers={'Origin': f'http://localhost:{client.port}'}),
             404, 'unknown_job'),
        ]
        for kwargs, status, code in cases:
            with self.subTest(kwargs=kwargs):
                response = client.get(path, **kwargs)
                self.assertEqual((response.status, response.code), (status, code))
        self.assertEqual(client.call('DELETE', path).status, 405)
        self.assertEqual(client.get('/sources').code, 'method_not_allowed')
        self.assertEqual(client.post('/jobs/job_' + '0' * 32, {}).code, 'method_not_allowed')
        self.assertEqual(client.get('/nope').code, 'route_not_found')
        self.assertEqual(client.get('/jobs/not-a-job').code, 'malformed_id')

    # 3
    def test_admit_source_returns_ids_without_host_path(self):
        env = Env(self, self.state())
        first = env.client.post('/sources', {'selector': 'RUN-A/export/fake.mov'})
        self.assertEqual(first.status, 201)
        self.assertEqual(set(first.json), {'source_artifact_id', 'source_id', 'source_binding', 'kind', 'sha256',
                                           'size_bytes', 'state'})
        self.assertEqual(first.json['sha256'], hashlib.sha256(FAKE_MOV).hexdigest())
        self.assertEqual(first.json['source_id'], artifact_ids.source_id_for(FIXTURE_SOURCE_SHA))
        self.assertEqual((first.json['source_binding'], first.json['kind'], first.json['state']),
                         ('bound', 'video', 'current'))
        self.assertTrue(artifact_ids.ARTIFACT_ID.fullmatch(first.json['source_artifact_id']))
        again = env.client.post('/sources', {'selector': 'RUN-A/export/fake.mov'})
        self.assertEqual((again.status, again.json), (200, first.json))
        self.assertNotIn(b'RUN-A', first.payload)

    # 4
    def test_rejected_inputs_have_typed_reasons(self):
        state = self.state()
        env = Env(self, state)
        connection = self.db(state)

        def snapshot():
            return (connection.execute('SELECT * FROM sources').fetchall(),
                    connection.execute('SELECT count(*) FROM jobs').fetchone()[0],
                    sorted(os.listdir(Path(state) / 'jobs')))

        absolute = str(self.R / 'artifacts' / 'runs' / 'RUN-A' / 'export' / 'fake.mov')
        cases = [
            ({'selector': 'RUN-A/export/fake.mov', 'extra': 1}, 400, 'unknown_field', None),
            ({}, 400, 'missing_field', None),
            ({'selector': 5}, 400, 'bad_type', None),
            ({'selector': 'RUN-A/notes.txt'}, 422, 'not_media', None),
            ({'selector': 'RUN-A/bad.mov'}, 422, 'not_media', None),
            ({'selector': 'RUN-A/../RUN-A/export/fake.mov'}, 422, 'path_escape', 'outside_runs_root'),
            ({'selector': absolute}, 422, 'path_escape', 'host_path_refused'),
            ({'selector': 'RUN-A/escape.mov'}, 422, 'path_escape', 'symlink_component'),
            ({'selector': 'RUN-A/exec.mov'}, 422, 'executable_refused', None),
            ({'selector': 'RUN-A/hashbang.mov'}, 422, 'executable_refused', None),
            ({'selector': 'RUN-A/take.partial.mov'}, 422, 'path_escape', 'unsafe_component'),
            ({'selector': 'RUN-A/pipe.mov'}, 422, 'not_regular_file', None),
            ({'selector': 'RUN-A/absent.mov'}, 422, 'not_regular_file', None),
            ({'selector': 'RUN-A/export/fake.mov;rm'}, 422, 'path_escape', 'filter_string_refused'),
        ]
        before = snapshot()
        for body, status, code, detail in cases:
            with self.subTest(body=body):
                response = env.client.post('/sources', body)
                self.assertEqual((response.status, response.code), (status, code), response.json)
                if detail is not None:
                    self.assertEqual(response.json['detail_code'], detail)
                self.assertEqual(snapshot(), before)
        small = Env(self, self.state('small'), max_source_bytes=1024)
        response = small.client.post('/sources', {'selector': 'RUN-A/export/fake.mov'})
        self.assertEqual((response.status, response.code), (422, 'too_large'))
        self.assertEqual(snapshot(), before)
        METRICS['rejected_inputs'] = {'refused_with_expected_reason': len(cases) + 1, 'cases': len(cases) + 1}

    # 5
    def test_unknown_fields_and_unadmitted_tool_refused_on_submit(self):
        state = self.state()
        env = Env(self, state)
        source = self.admit(env.client)
        base = {'tool': 'share_export', 'source_artifact_id': source, 'idempotency_key': 'key-00000001'}
        cases = [
            (dict(base, tool='probe'), 400, 'tool_not_admitted'),
            (dict(base, output='/tmp/x.mp4'), 400, 'unknown_field'),
            (dict(base, parameters={'filter': 'x'}), 400, 'invalid_parameters'),
            (dict(base, parameters={'height': 721}), 400, 'invalid_parameters'),
            (dict(base, parameters={'timeout_seconds': 29}), 400, 'invalid_parameters'),
            (dict(base, parameters={'codec': 'shell'}), 400, 'invalid_parameters'),
            (dict(base, parameters={'crf': True}), 400, 'invalid_parameters'),
            (dict(base, parameters='x'), 400, 'bad_type'),
            (dict(base, source_artifact_id='art_' + '0' * 32), 404, 'unknown_source'),
            (dict(base, source_artifact_id='RUN-A/export/fake.mov'), 400, 'malformed_id'),
            (dict(base, idempotency_key='short'), 400, 'invalid_idempotency_key'),
            ({key: value for key, value in base.items() if key != 'idempotency_key'}, 400, 'missing_field'),
        ]
        for body, status, code in cases:
            with self.subTest(body=body):
                response = env.client.post('/jobs', body)
                self.assertEqual((response.status, response.code), (status, code), response.json)
        self.assertEqual(self.db(state).execute('SELECT count(*) FROM jobs').fetchone()[0], 0)

    # 6
    @unittest.skipUnless(HAVE_FFMPEG, FFMPEG_SKIP)
    def test_real_share_export_job_succeeds_and_publishes_atomically(self):
        state = self.state()
        env = Env(self, state, builder=None)
        source = self.admit(env.client, 'RUN-A/export/clip.mov')
        started = time.monotonic()
        response = self.submit(env.client, source, 'real-job-0001', {'timeout_seconds': 120})
        self.assertEqual(response.status, 202, response.json)
        job = self.wait_job(env.client, response.json['job_id'], web_jobs.TERMINAL, timeout=180)
        wall = time.monotonic() - started
        self.assertEqual(job['state'], 'succeeded', job)
        attempt = job['attempts'][0]
        self.assertEqual(attempt['worker_kind'], 'tool_api_share_export')
        checks = attempt['worker_checks']
        self.assertEqual((checks['status'], checks['master_adopted'], checks['listening_accepted']),
                         ('exported_unreviewed', False, False))
        job_dir = Path(state) / 'jobs' / job['job_id']
        self.assertEqual(sorted(os.listdir(job_dir)), ['attempt-1'])
        self.assertEqual(sorted(os.listdir(job_dir / 'attempt-1')),
                         ['publication.json', 'share.mp4', 'share.mp4.receipt.json'])
        roles = {row['role']: row for row in job['artifacts']}
        self.assertEqual(set(roles), {'share_mp4', 'share_receipt', 'publication'})
        download = env.client.get(f'/artifacts/{roles["share_mp4"]["artifact_id"]}')
        self.assertEqual(download.status, 200)
        self.assertEqual(download.headers['Content-Type'], 'video/mp4')
        self.assertEqual(hashlib.sha256(download.payload).hexdigest(), roles['share_mp4']['sha256'])
        self.assertEqual(download.headers['X-Artifact-Sha256'], roles['share_mp4']['sha256'])
        self.assertEqual(checks['output_sha256'], roles['share_mp4']['sha256'])
        self.assertEqual(env.client.get(f'/artifacts/{roles["share_receipt"]["artifact_id"]}').code, 'artifact_private')
        self.assertAlmostEqual(job['unknowns']['source_duration_seconds'], 2.0, delta=0.5)
        METRICS['real_dispatcher_synthetic'] = {'succeeded': 1, 'submitted': 1, 'wall_seconds': round(wall, 3),
                                                'checks': {k: checks[k] for k in ('codecs', 'dimensions',
                                                                                  'output_bytes', 'video_encode_count')}}

    # 7
    def test_idempotent_replay_returns_same_job_and_no_duplicate_publish(self):
        state = self.state()
        env = Env(self, state)
        source = self.admit(env.client)
        first = self.submit(env.client, source, 'replay-key-0001')
        self.assertEqual((first.status, first.json['replayed']), (202, False))
        done = self.wait_job(env.client, first.json['job_id'], ('succeeded',))
        replays = [self.submit(env.client, source, 'replay-key-0001') for _ in range(3)]
        for replay in replays:
            self.assertEqual((replay.status, replay.json['replayed'], replay.json['job_id']),
                             (200, True, first.json['job_id']))
            self.assertEqual(replay.json['artifacts'], done['artifacts'])
        connection = self.db(state)
        counts = tuple(connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                       for table in ('jobs', 'attempts', 'artifacts'))
        self.assertEqual(counts, (1, 1, 3))
        self.assertEqual(sorted(os.listdir(Path(state) / 'jobs' / first.json['job_id'])), ['attempt-1'])
        self.assertEqual(len(env.builder.beats), 1)
        METRICS['idempotent_replay'] = {'replays_same_job': 3, 'replays': 3, 'jobs': counts[0],
                                        'attempts': counts[1], 'artifacts': counts[2]}

    # 8
    def test_same_key_different_request_conflicts(self):
        state = self.state()
        env = Env(self, state)
        source = self.admit(env.client)
        self.assertEqual(self.submit(env.client, source, 'conflict-key-01', {'crf': 27}).status, 202)
        # Default-filled parameters fingerprint identically: an explicit default replays.
        self.assertEqual(self.submit(env.client, source, 'conflict-key-01').status, 200)
        response = self.submit(env.client, source, 'conflict-key-01', {'crf': 30})
        self.assertEqual((response.status, response.code), (409, 'idempotency_conflict'))
        self.assertEqual(self.db(state).execute('SELECT count(*) FROM jobs').fetchone()[0], 1)

    # 9
    def test_cancel_queued_job(self):
        env = Env(self, self.state())
        env.builder.modes = ['sleep']
        source = self.admit(env.client)
        running = self.submit(env.client, source, 'cancel-q-run-1').json['job_id']
        self.wait_job(env.client, running, ('running',))
        self.wait_beat(env.builder)
        queued = self.submit(env.client, source, 'cancel-q-wait-1')
        self.assertEqual((queued.status, queued.json['state']), (202, 'queued'))
        cancelled = env.client.post(f'/jobs/{queued.json["job_id"]}/cancel', {})
        self.assertEqual((cancelled.status, cancelled.json['state'], cancelled.json['late_cancel']),
                         (200, 'cancelled', False))
        self.assertEqual((cancelled.json['attempts'][0]['state'], cancelled.json['attempts'][0]['worker_kind']),
                         ('cancelled', None))
        self.assertEqual(env.client.post(f'/jobs/{running}/cancel', {}).status, 202)
        self.wait_job(env.client, running, ('cancelled',), timeout=20)
        time.sleep(0.5)
        final = env.client.get(f'/jobs/{queued.json["job_id"]}').json
        self.assertEqual((final['state'], final['artifacts']), ('cancelled', []))
        self.assertEqual(len(env.builder.beats), 1)

    # 10
    def test_cancel_during_run_kills_owned_process_group(self):
        state = self.state()
        env = Env(self, state)
        env.builder.modes = ['sleep']
        source = self.admit(env.client)
        job_id = self.submit(env.client, source, 'cancel-run-001').json['job_id']
        self.wait_job(env.client, job_id, ('running',))
        beat = self.wait_beat(env.builder)
        pids = [beat['pid'], beat['child']]
        for pid in pids:
            os.kill(pid, 0)  # both owned group members are alive before the cancel
        response = env.client.post(f'/jobs/{job_id}/cancel', {})
        self.assertEqual((response.status, response.json['state'], response.json['cancel_requested']),
                         (202, 'running', True))
        job = self.wait_job(env.client, job_id, web_jobs.TERMINAL, timeout=20)
        self.assertEqual((job['state'], job['reason_code']), ('cancelled', 'cancel_requested'))
        gone = [self.wait_gone(pid, 10) for pid in pids]
        self.assertEqual(gone, [True, True])
        self.assertTrue(Path(str(env.builder.beats[-1]) + '.sigterm').exists())
        cancel = job['attempts'][0]['cancel']
        self.assertEqual(cancel['signal_target'], 'owned_process_group')
        self.assertLessEqual(cancel['requested_at'], cancel['ack_at'])
        self.assertLessEqual(cancel['ack_at'], cancel['observed_stop_at'])
        self.assertTrue(cancel['group_empty_observed'])
        self.assertEqual(job['artifacts'], [])
        self.assertEqual(os.listdir(Path(state) / 'jobs' / job_id), [])
        late = env.client.post(f'/jobs/{job_id}/cancel', {})
        self.assertEqual((late.status, late.json['late_cancel'], late.json['state']), (200, True, 'cancelled'))
        METRICS['cancel_during_run'] = {'owned_pids_terminated': sum(gone), 'owned_pids': len(pids),
                                        'artifacts_published': 0}

    # 11
    def test_late_cancel_after_success_reports_actual_state(self):
        env = Env(self, self.state())
        source = self.admit(env.client)
        job_id = self.submit(env.client, source, 'late-cancel-01').json['job_id']
        done = self.wait_job(env.client, job_id, ('succeeded',))
        response = env.client.post(f'/jobs/{job_id}/cancel', {})
        self.assertEqual((response.status, response.json['late_cancel'], response.json['state']),
                         (200, True, 'succeeded'))
        self.assertEqual(response.json['artifacts'], done['artifacts'])
        self.assertFalse(response.json['cancel_requested'])

    # 12
    def test_interrupted_then_replayed_and_retried_keeps_earlier_artifacts(self):
        state = self.state()
        env1 = Env(self, state)
        env1.builder.modes = ['succeed', 'sleep']
        source = self.admit(env1.client)
        job_a = self.submit(env1.client, source, 'earlier-job-A1').json['job_id']
        done_a = self.wait_job(env1.client, job_a, ('succeeded',))
        a_digest = tree_digest(Path(state) / 'jobs' / job_a)
        job_b = self.submit(env1.client, source, 'abandon-job-B1').json['job_id']
        self.wait_job(env1.client, job_b, ('running',))
        pid = self.wait_beat(env1.builder)['pid']
        env1.stop()
        self.kill_own_stub(env1, pid)
        b_before = tree_digest(Path(state) / 'jobs' / job_b)
        env2 = Env(self, state)
        self.assertEqual(env2.jobs.reconciliation['interrupted'], 1)
        interrupted = env2.client.get(f'/jobs/{job_b}').json
        self.assertEqual((interrupted['state'], interrupted['attempts'][0]['liveness'],
                          interrupted['attempts'][0]['reason_code']), ('interrupted', 'dead', 'supervisor_restarted'))
        replay = self.submit(env2.client, source, 'abandon-job-B1')
        self.assertEqual((replay.status, replay.json['replayed'], replay.json['job_id'], replay.json['state'],
                          len(replay.json['attempts'])), (200, True, job_b, 'interrupted', 1))
        retry = env2.client.post(f'/jobs/{job_b}/retry', {})
        self.assertEqual((retry.status, len(retry.json['attempts'])), (202, 2))
        self.assertIn(retry.json['state'], ('queued', 'running', 'succeeded'))  # supervisor may claim at once
        done_b = self.wait_job(env2.client, job_b, web_jobs.TERMINAL)
        self.assertEqual((done_b['state'], [a['state'] for a in done_b['attempts']]),
                         ('succeeded', ['interrupted', 'succeeded']))
        self.assertEqual({a['attempt'] for a in done_b['artifacts']}, {2})
        b_dir = Path(state) / 'jobs' / job_b
        self.assertIn('attempt-2', os.listdir(b_dir))
        self.assertNotIn('attempt-1', os.listdir(b_dir))
        moved = Path(state) / 'jobs' / (job_b + '-attempt-2-aside')
        os.rename(b_dir / 'attempt-2', moved)
        try:
            self.assertEqual(tree_digest(b_dir), b_before)  # earlier attempt staging byte-identical
        finally:
            os.rename(moved, b_dir / 'attempt-2')
        self.assertEqual(tree_digest(Path(state) / 'jobs' / job_a), a_digest)
        self.assertEqual(env2.client.get(f'/jobs/{job_a}').json['artifacts'], done_a['artifacts'])
        again = self.submit(env2.client, source, 'abandon-job-B1')
        self.assertEqual((again.status, again.json['job_id'], len(again.json['attempts'])), (200, job_b, 2))
        self.assertEqual(self.db(state).execute('SELECT count(*) FROM artifacts').fetchone()[0], 6)
        METRICS['interrupted_replay_retry'] = {'scenarios_passed': 1, 'scenarios': 1,
                                               'earlier_artifacts_byte_identical': True}

    # 13
    def test_reconcile_alive_unowned_worker_is_not_signalled_and_blocks_retry(self):
        state = self.state()
        env1 = Env(self, state)
        env1.builder.modes = ['sleep']
        source = self.admit(env1.client)
        job_id = self.submit(env1.client, source, 'unowned-job-01').json['job_id']
        self.wait_job(env1.client, job_id, ('running',))
        beat = self.wait_beat(env1.builder)
        sigterm_marker = Path(str(env1.builder.beats[-1]) + '.sigterm')
        env1.stop()
        env2 = Env(self, state)
        job = env2.client.get(f'/jobs/{job_id}').json
        liveness = job['attempts'][0]['liveness']
        self.assertEqual(job['state'], 'interrupted')
        self.assertIn(liveness, ('alive_unowned', 'unknown'))
        refused = env2.client.post(f'/jobs/{job_id}/retry', {})
        self.assertEqual((refused.status, refused.code), (409, 'prior_worker_alive'))
        for pid in (beat['pid'], beat['child']):
            os.kill(pid, 0)  # still alive: the new instance sent nothing
        self.assertFalse(sigterm_marker.exists())
        self.kill_own_stub(env1, beat['pid'])
        retried = env2.client.post(f'/jobs/{job_id}/retry', {})
        self.assertEqual(retried.status, 202, retried.json)
        self.assertEqual(retried.json['attempts'][0]['liveness'], 'dead')
        self.assertEqual(self.wait_job(env2.client, job_id, web_jobs.TERMINAL)['state'], 'succeeded')
        METRICS['unowned_live_worker'] = {'signals_sent_by_new_instance': 0, 'retry_refused': True,
                                          'observed_liveness': liveness}

    # 14
    def test_reconnect_and_poll_after_restart(self):
        state = self.state()
        env1 = Env(self, state)
        env1.builder.modes = ['succeed', 'sleep']
        source = self.admit(env1.client)
        done = self.submit(env1.client, source, 'reconnect-J1-01').json['job_id']
        projection = self.wait_job(env1.client, done, ('succeeded',))
        busy = self.submit(env1.client, source, 'reconnect-J2-01').json['job_id']
        self.wait_job(env1.client, busy, ('running',))
        pid = self.wait_beat(env1.builder)['pid']
        waiting = self.submit(env1.client, source, 'reconnect-J3-01').json['job_id']
        old_token = env1.server.token
        env1.stop()
        self.kill_own_stub(env1, pid)
        env2 = Env(self, state)
        self.assertNotEqual(env2.server.token, old_token)
        self.assertEqual(env2.client.get(f'/jobs/{done}', token=old_token).status, 401)
        self.assertEqual(env2.client.get(f'/jobs/{done}').json, projection)
        self.assertEqual(env2.client.get(f'/jobs/{busy}').json['state'], 'interrupted')
        self.assertEqual(self.wait_job(env2.client, waiting, web_jobs.TERMINAL)['state'], 'succeeded')
        METRICS['reconnect_after_restart'] = {'projection_equal': 1, 'checked': 1, 'queued_job_ran_after_restart': True}

    # 15
    def test_crash_after_publish_before_commit_is_adopted_not_republished(self):
        state = self.state()
        env1 = Env(self, state, fault='after_publish_before_commit')
        source = self.admit(env1.client)
        job_id = self.submit(env1.client, source, 'crash-adopt-01').json['job_id']
        end = time.monotonic() + 20
        while not env1.jobs.crashed and time.monotonic() < end:
            time.sleep(0.02)
        self.assertTrue(env1.jobs.crashed)
        self.assertEqual(env1.client.get(f'/jobs/{job_id}').json['state'], 'running')
        env1.stop()
        env2 = Env(self, state)
        self.assertEqual(env2.jobs.reconciliation['adopted'], 1)
        job = env2.client.get(f'/jobs/{job_id}').json
        self.assertEqual((job['state'], job['attempts'][0]['reconciled_publication'], len(job['artifacts'])),
                         ('succeeded', True, 3))
        self.assertEqual(sorted(os.listdir(Path(state) / 'jobs' / job_id)), ['attempt-1'])
        replay = self.submit(env2.client, source, 'crash-adopt-01')
        self.assertEqual((replay.status, replay.json['job_id'], len(replay.json['attempts'])), (200, job_id, 1))
        mp4 = next(a for a in job['artifacts'] if a['role'] == 'share_mp4')
        self.assertEqual(env2.client.get(f'/artifacts/{mp4["artifact_id"]}').status, 200)
        self.assertEqual(self.db(state).execute('SELECT count(*) FROM artifacts').fetchone()[0], 3)
        self.assertEqual(len(env1.builder.beats) + len(env2.builder.beats), 1)
        METRICS['crash_after_publish'] = {'adopted': 1, 'scenarios': 1, 'publications': 1}

    # 16
    def test_source_changed_after_submit_fails_without_worker(self):
        runs = self.base / f'R-{self._testMethodName}'
        run = make_runs_root(runs, 'RUN-B')
        env = Env(self, self.state(), runs_root=runs, start=False)
        source = self.admit(env.client, 'RUN-B/export/fake.mov')
        job_id = self.submit(env.client, source, 'changed-src-01').json['job_id']
        with open(run / 'export' / 'fake.mov', 'ab') as handle:
            handle.write(b'changed after submit')
        env.jobs.start()
        job = self.wait_job(env.client, job_id, web_jobs.TERMINAL)
        self.assertEqual((job['state'], job['reason_code'], job['attempts'][0]['reason_code']),
                         ('failed', 'source_changed', 'source_changed'))
        self.assertEqual(env.builder.beats, [])
        stale = self.submit(env.client, source, 'changed-src-02')
        self.assertEqual((stale.status, stale.code), (409, 'source_stale'))
        self.assertEqual(env.client.post(f'/jobs/{job_id}/retry', {}).code, 'source_stale')
        (run / 'export' / 'fake.mov').unlink()
        missing = self.submit(env.client, source, 'changed-src-03')
        self.assertEqual((missing.status, missing.code), (410, 'source_missing'))

    # 17
    def test_artifact_download_confinement(self):
        state = self.state()
        env = Env(self, state)
        source = self.admit(env.client)
        jobs = [self.wait_job(env.client, self.submit(env.client, source, f'confine-{n}-0001').json['job_id'],
                              ('succeeded',)) for n in (1, 2)]
        first = {a['role']: a for a in jobs[0]['artifacts']}
        mp4 = env.client.get(f'/artifacts/{first["share_mp4"]["artifact_id"]}')
        self.assertEqual(mp4.status, 200)
        self.assertEqual((mp4.headers['X-Artifact-Sha256'], hashlib.sha256(mp4.payload).hexdigest(),
                          int(mp4.headers['Content-Length'])),
                         (first['share_mp4']['sha256'], first['share_mp4']['sha256'], first['share_mp4']['size_bytes']))
        publication = env.client.get(f'/artifacts/{first["publication"]["artifact_id"]}')
        self.assertEqual((publication.status, publication.json['job_id'], publication.json['master_adopted']),
                         (200, jobs[0]['job_id'], False))
        hostile = [
            ('/artifacts/art_XYZ', 400, 'malformed_id'),
            ('/artifacts/art_' + 'G' * 32, 400, 'malformed_id'),
            ('/artifacts/src_' + '0' * 32, 400, 'malformed_id'),
            ('/artifacts/..%2F..%2Fjobs.sqlite3', 400, 'malformed_id'),
            ('/artifacts/../jobs.sqlite3', 404, 'route_not_found'),
            ('/artifacts/jobs/x/attempt-1/share.mp4', 404, 'route_not_found'),
            ('/artifacts/art_' + '0' * 32, 404, 'unknown_artifact'),
            (f'/artifacts/{source}', 404, 'unknown_artifact'),
            (f'/artifacts/{first["share_receipt"]["artifact_id"]}', 403, 'artifact_private'),
        ]
        second = {a['role']: a for a in jobs[1]['artifacts']}
        target = f'/artifacts/{second["share_mp4"]["artifact_id"]}'
        attempt_dir = Path(state) / 'jobs' / jobs[1]['job_id'] / 'attempt-1'
        leaf = attempt_dir / 'share.mp4'
        original = leaf.read_bytes()
        refused = 0
        for path, status, code in hostile:
            with self.subTest(path=path):
                response = env.client.get(path)
                self.assertEqual((response.status, response.code), (status, code))
                refused += 1
        aside = attempt_dir.with_name('attempt-1-aside')
        os.rename(attempt_dir, aside)
        attempt_dir.symlink_to(aside)
        self.assertEqual(env.client.get(target).code, 'confinement_refused')
        attempt_dir.unlink()
        os.rename(aside, attempt_dir)
        os.rename(leaf, leaf.with_name('share.real'))
        leaf.symlink_to(leaf.with_name('share.real'))
        self.assertEqual(env.client.get(target).code, 'confinement_refused')
        leaf.unlink()
        os.rename(leaf.with_name('share.real'), leaf)
        self.assertEqual(env.client.get(target).status, 200)
        with open(leaf, 'ab') as handle:
            handle.write(b'tamper')
        self.assertEqual(env.client.get(target).code, 'artifact_stale')
        leaf.write_bytes(original)
        self.assertEqual(env.client.get(target).status, 200)
        leaf.unlink()
        self.assertEqual(env.client.get(target).code, 'artifact_missing')
        refused += 4
        self.assertEqual(tree_digest(self.R / 'artifacts' / 'runs'), self.runs_digest)
        METRICS['confinement'] = {'hostile_download_cases_refused': refused, 'hostile_download_cases': refused,
                                  'runs_tree_hash_equal': True}

    # 18
    def test_queue_limit_and_body_limit(self):
        env = Env(self, self.state(), queue_limit=2)
        env.builder.modes = ['sleep']
        source = self.admit(env.client)
        running = self.submit(env.client, source, 'queue-limit-01').json['job_id']
        self.wait_job(env.client, running, ('running',))
        self.wait_beat(env.builder)
        queued = [self.submit(env.client, source, f'queue-limit-0{n}') for n in (2, 3)]
        self.assertEqual([r.status for r in queued], [202, 202])
        full = self.submit(env.client, source, 'queue-limit-04')
        self.assertEqual((full.status, full.code), (429, 'queue_full'))
        cases = [
            (dict(raw=b'{"a":"' + b'x' * (17 * 1024) + b'"}'), 413, 'body_too_large'),
            (dict(raw=b'{}', content_type='text/plain'), 415, 'content_type'),
            (dict(raw=b'{"tool":"share_export","tool":"x"}'), 400, 'malformed_json'),
            (dict(raw=b'{"x": NaN}'), 400, 'malformed_json'),
            (dict(raw=b'\xff\xfe'), 400, 'malformed_json'),
            (dict(raw=b'[1, 2]'), 400, 'bad_type'),
            (dict(raw=b'[' * 100 + b']' * 100), 400, 'malformed_json'),
        ]
        for kwargs, status, code in cases:
            with self.subTest(code=code):
                response = env.client.call('POST', '/jobs', **kwargs)
                self.assertEqual((response.status, response.code), (status, code))
        connection = http.client.HTTPConnection('127.0.0.1', env.client.port, timeout=10)
        connection.putrequest('POST', '/jobs', skip_host=True, skip_accept_encoding=True)
        connection.putheader('Host', f'127.0.0.1:{env.client.port}')
        connection.putheader('Authorization', 'Bearer ' + env.server.token)
        connection.putheader('Content-Type', 'application/json')
        connection.endheaders()
        response = connection.getresponse()
        self.assertEqual((response.status, json.loads(response.read())['code']), (411, 'length_required'))
        connection.close()
        for job in queued:
            self.assertEqual(env.client.post(f'/jobs/{job.json["job_id"]}/cancel', {}).status, 200)
        self.assertEqual(env.client.post(f'/jobs/{running}/cancel', {}).status, 202)
        self.wait_job(env.client, running, ('cancelled',), timeout=20)

    # 19
    def test_projection_carries_all_unknowns_and_claim_class(self):
        env = Env(self, self.state())
        source = self.admit(env.client)
        submitted = self.submit(env.client, source, 'projection-01')
        self.assertIn('replayed', submitted.json)
        job = self.wait_job(env.client, submitted.json['job_id'], ('succeeded',))
        self.assertEqual(set(job), {'job_id', 'tool', 'state', 'reason_code', 'source_artifact_id', 'source_id',
                                    'source_binding', 'parameters', 'capability_revision', 'idempotency_key',
                                    'cancel_requested', 'attempts', 'artifacts', 'claim_class', 'unknowns'})
        self.assertEqual(job['claim_class'], 'job_state_record')
        self.assertEqual(job['parameters'], {'height': 720, 'crf': 27, 'audio_kbps': 96, 'codec': 'h264',
                                             'timeout_seconds': 900})
        unknowns = job['unknowns']
        self.assertEqual(set(unknowns), {
            'listening_acceptance', 'master_adopted', 'low_register_preservation', 'low_register_preservation_reason',
            'musical_review', 'musical_review_reason', 'source_duration_seconds', 'source_duration_seconds_reason',
            'memory_bytes_peak', 'memory_bytes_peak_reason', 'cpu_seconds', 'cpu_seconds_reason', 'exactly_once',
            'slo', 'worker_birth', 'worker_birth_reason'})
        self.assertEqual((unknowns['listening_acceptance'], unknowns['master_adopted'], unknowns['exactly_once'],
                          unknowns['slo']), ('not_established', False, 'not_claimed', 'not_claimed'))
        for key in ('low_register_preservation', 'musical_review', 'memory_bytes_peak', 'cpu_seconds',
                    'source_duration_seconds'):
            self.assertIsNone(unknowns[key])
            self.assertIsInstance(unknowns[key + '_reason'], str)
        self.assertEqual(set(job['attempts'][0]), {'attempt', 'state', 'worker_kind', 'reason_code', 'started_at',
                                                   'ended_at', 'liveness', 'reconciled_publication', 'cancel',
                                                   'worker_checks'})
        self.assertEqual(job['attempts'][0]['worker_kind'], 'test_stub')
        self.assertEqual(set(job['artifacts'][0]), {'artifact_id', 'attempt', 'role', 'sha256', 'size_bytes',
                                                    'content_type', 'downloadable'})

    # 20
    def test_schema_version_mismatch_refused(self):
        for label, setup in (('v3', 'PRAGMA user_version = 3'), ('v1-no-tables', 'PRAGMA user_version = 1'),
                             ('v0-tables', 'CREATE TABLE stray(x)')):
            state = self.state(label)
            state.mkdir(parents=True, mode=0o700)
            connection = sqlite3.connect(state / 'jobs.sqlite3')
            connection.execute(setup)
            connection.commit()
            connection.close()
            for _ in range(2):  # the lock is released after the refusal
                with self.assertRaises(WebJobsError) as caught:
                    WebJobs(self.R, state, command_builder=StubBuilder(self.base / 'beats-mismatch'))
                self.assertEqual(caught.exception.code, 'schema_version_mismatch')

    # 21
    def test_state_root_lock_refuses_second_instance(self):
        state = self.state()
        first = WebJobs(self.R, state, command_builder=StubBuilder(self.base / 'beats-lock'))
        with self.assertRaises(WebJobsError) as caught:
            WebJobs(self.R, state, command_builder=StubBuilder(self.base / 'beats-lock'))
        self.assertEqual(caught.exception.code, 'state_root_locked')
        first.close()
        WebJobs(self.R, state, command_builder=StubBuilder(self.base / 'beats-lock')).close()
        for unsafe in (self.R / 'artifacts' / 'runs' / 'RUN-A' / 'state', self.R / 'artifacts' / 'runs' / 'new' / 'x',
                       self.R / 'artifacts'):
            with self.assertRaises(WebJobsError) as inside:
                WebJobs(self.R, unsafe)
            self.assertEqual(inside.exception.code, 'state_root_unsafe')
            self.assertFalse((self.R / 'artifacts' / 'runs' / 'RUN-A' / 'state').exists())
            self.assertFalse((self.R / 'artifacts' / 'runs' / 'new').exists())

    # 22
    def test_worker_rejection_and_malformed_result_fail_with_typed_reasons(self):
        env = Env(self, self.state())
        env.builder.modes = ['reject', 'garbage']
        source = self.admit(env.client)
        rejected = self.wait_job(env.client, self.submit(env.client, source, 'reject-job-01').json['job_id'],
                                 web_jobs.TERMINAL)
        self.assertEqual((rejected['state'], rejected['reason_code']), ('failed', 'worker_rejected'))
        self.assertEqual(rejected['attempts'][0]['worker_checks'], {'status': 'rejected', 'code': 'stub_rejected'})
        garbage = self.wait_job(env.client, self.submit(env.client, source, 'garbage-job-01').json['job_id'],
                                web_jobs.TERMINAL)
        self.assertEqual((garbage['state'], garbage['reason_code']), ('failed', 'malformed_result'))
        retried = env.client.post(f'/jobs/{rejected["job_id"]}/retry', {})
        self.assertEqual(retried.status, 202)
        done = self.wait_job(env.client, rejected['job_id'], ('succeeded',))
        self.assertEqual([a['state'] for a in done['attempts']], ['failed', 'succeeded'])
        refused = env.client.post(f'/jobs/{done["job_id"]}/retry', {})
        self.assertEqual((refused.status, refused.code), (409, 'not_retryable'))
        self.assertEqual(env.client.post(f'/jobs/{done["job_id"]}/retry', {'x': 1}).code, 'unknown_field')

    # 23
    def test_cli_status_is_read_only_and_reconcile_respects_lock(self):
        state = self.state()
        env = Env(self, state)
        source = self.admit(env.client)
        self.wait_job(env.client, self.submit(env.client, source, 'cli-status-01').json['job_id'], ('succeeded',))
        script = str(ROOT / 'scripts' / 'web_jobs.py')
        status = subprocess.run([sys.executable, script, '--state-root', str(state), '--runs-root', str(self.R),
                                 'status'], capture_output=True, text=True, timeout=30)
        self.assertEqual(status.returncode, 0, status.stderr)
        counts = json.loads(status.stdout)
        self.assertEqual((counts['jobs']['succeeded'], counts['artifacts'], counts['daemon']), (1, 3, False))
        locked = subprocess.run([sys.executable, script, '--state-root', str(state), '--runs-root', str(self.R),
                                 'reconcile'], capture_output=True, text=True, timeout=30)
        self.assertEqual((locked.returncode, json.loads(locked.stderr)['code']), (1, 'state_root_locked'))
        for needle in self.forbidden:
            self.assertNotIn(needle, status.stdout + locked.stderr)

    # 24
    def test_server_code_is_foreground_only(self):
        for name in ('web_api.py', 'web_jobs.py'):
            source = (ROOT / 'scripts' / name).read_text()
            for forbidden in ('os.fork', 'daemon(', 'os.setsid', 'launchctl', 'LaunchAgents', 'nohup', 'double_fork'):
                self.assertNotIn(forbidden, source)
        api = (ROOT / 'scripts' / 'web_api.py').read_text()
        self.assertIn("BIND_ADDRESS = '127.0.0.1'", api)
        self.assertIn('serve_forever', api)
        METRICS['foreground_only_static'] = True


def _percentiles(values):
    ordered = sorted(values)
    if not ordered:
        return {'n': 0, 'p50_ms': None, 'p95_ms': None, 'max_ms': None}

    def pick(fraction):
        return ordered[min(len(ordered) - 1, max(0, int(round(fraction * len(ordered) + 0.5)) - 1))]
    return {'n': len(ordered), 'p50_ms': round(statistics.median(ordered) * 1000, 3),
            'p95_ms': round(pick(0.95) * 1000, 3), 'max_ms': round(ordered[-1] * 1000, 3)}


def _host_facts():
    def run(command):
        try:
            return subprocess.run(command, capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
    return {'uname': run(['uname', '-a']), 'cpu': run(['sysctl', '-n', 'machdep.cpu.brand_string']),
            'python': platform.python_version(),
            'ffmpeg': (run([FFMPEG, '-version']) or '').splitlines()[0] if HAVE_FFMPEG else None}


@unittest.skipUnless(os.environ.get('WEB_JOBS_MEASURE') == '1', 'opt-in local latency measurement (WEB_JOBS_MEASURE=1)')
class LocalLatencyMeasurement(WebJobsTestBase):
    """Descriptive measurements on this host only; no SLO claim, no comparison verdict."""

    def test_measure_local_latencies(self):
        out = {'claim_class': 'measurement_this_host_only', 'slo': 'not_claimed', 'host': _host_facts(),
               'measured_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'state': 'warm_process_not_cold_boot',
               'one_heavy_job_at_a_time': True}
        env = Env(self, self.state('latency'), queue_limit=4)
        source = self.admit(env.client)
        job_id = self.wait_job(env.client, self.submit(env.client, source, 'latency-seed-01').json['job_id'],
                               ('succeeded',))['job_id']
        sequential, failures = [], 0
        for _ in range(500):
            start = time.perf_counter()
            failures += env.client.get(f'/jobs/{job_id}').status != 200
            sequential.append(time.perf_counter() - start)
        concurrent, lock = [], threading.Lock()
        errors = []

        def worker():
            for _ in range(50):
                start = time.perf_counter()
                try:
                    ok = env.client.get(f'/jobs/{job_id}').status == 200
                except Exception:  # recorded as a failure in the denominator
                    ok = False
                with lock:
                    concurrent.append(time.perf_counter() - start)
                    if not ok:
                        errors.append(1)
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=300)
        out['get_job_sequential'] = dict(_percentiles(sequential), failures=failures, attempted=500)
        out['get_job_10_concurrent'] = dict(_percentiles(concurrent), failures=len(errors), attempted=500)
        accept, replay, submit_failures = [], [], 0
        keys = []
        for batch in range(0, 50, 4):
            batch_ids = []
            for n in range(batch, min(batch + 4, 50)):
                key = f'latency-new-{n:04d}'
                start = time.perf_counter()
                response = self.submit(env.client, source, key)
                accept.append(time.perf_counter() - start)
                submit_failures += response.status != 202
                batch_ids.append(response.json.get('job_id'))
                keys.append(key)
            for identifier in batch_ids:
                if identifier:
                    self.wait_job(env.client, identifier, web_jobs.TERMINAL, timeout=60)
        replay_failures = 0
        for key in keys:
            start = time.perf_counter()
            replay_failures += self.submit(env.client, source, key).status != 200
            replay.append(time.perf_counter() - start)
        out['post_jobs_new'] = dict(_percentiles(accept), failures=submit_failures, attempted=50, worker='test_stub')
        out['post_jobs_replay'] = dict(_percentiles(replay), failures=replay_failures, attempted=50)
        acks, stops, cancel_failures = [], [], 0
        for n in range(10):
            env.builder.modes = ['sleep']
            identifier = self.submit(env.client, source, f'latency-cancel-{n:03d}').json['job_id']
            self.wait_job(env.client, identifier, ('running',))
            self.wait_beat(env.builder)
            start = time.perf_counter()
            response = env.client.post(f'/jobs/{identifier}/cancel', {})
            acks.append(time.perf_counter() - start)
            job = self.wait_job(env.client, identifier, web_jobs.TERMINAL, timeout=30)
            cancel_failures += response.status != 202 or job['state'] != 'cancelled'
            receipt = job['attempts'][-1]['cancel'] or {}
            if receipt.get('signal_at') and receipt.get('observed_stop_at'):
                stops.append((web_jobs.parse_utc(receipt['observed_stop_at'])
                              - web_jobs.parse_utc(receipt['signal_at'])).total_seconds())
        out['cancel_ack_http'] = dict(_percentiles(acks), failures=cancel_failures, attempted=10, worker='test_stub')
        out['observed_stop_after_signal'] = dict(_percentiles(stops), attempted=10, worker='test_stub')
        env.cleanup()
        reconcile_times, reconcile_failures = [], 0
        for n in range(10):
            state = self.state(f'reconcile-{n}')
            first = Env(self, state)
            first.builder.modes = ['sleep']
            src = self.admit(first.client)
            identifier = self.submit(first.client, src, f'latency-abandon-{n:03d}').json['job_id']
            self.wait_job(first.client, identifier, ('running',))
            pid = self.wait_beat(first.builder)['pid']
            first.stop()
            self.kill_own_stub(first, pid)
            start = time.perf_counter()
            jobs = WebJobs(self.R, state, command_builder=StubBuilder(self.base / f'beats-r{n}'))
            reconcile_times.append(time.perf_counter() - start)
            reconcile_failures += jobs.reconciliation['interrupted'] != 1
            jobs.close()
        out['restart_to_reconciled'] = dict(_percentiles(reconcile_times), failures=reconcile_failures, attempted=10,
                                            includes='WebJobs construction: lock, schema check, descriptor load, reconcile')
        if self.clip_available:
            real_env = Env(self, self.state('real'), builder=None)
            clip = self.admit(real_env.client, 'RUN-A/export/clip.mov')
            walls, real_failures = [], 0
            for n in range(3):
                start = time.perf_counter()
                identifier = self.submit(real_env.client, clip, f'latency-real-{n:03d}',
                                         {'timeout_seconds': 120}).json['job_id']
                job = self.wait_job(real_env.client, identifier, web_jobs.TERMINAL, timeout=600)
                walls.append(time.perf_counter() - start)
                real_failures += job['state'] != 'succeeded'
            out['real_share_export_2s_clip'] = dict(_percentiles(walls), failures=real_failures, attempted=3,
                                                    worker='tool_api_share_export')
        else:
            out['real_share_export_2s_clip'] = {'n': 0, 'skipped': FFMPEG_SKIP}
        target = ROOT / 'artifacts' / 's2' / 'web_jobs'
        target.mkdir(parents=True, exist_ok=True)
        (target / 'latency.json').write_text(json.dumps(out, indent=2, sort_keys=True) + '\n')


@unittest.skipUnless(os.environ.get('WEB_JOBS_DEMO') == '1' and HAVE_FFMPEG,
                     'opt-in actual-demo structural job (WEB_JOBS_DEMO=1 and qualified FFmpeg)')
class ActualDemoJob(unittest.TestCase):
    """One read-only structural delivery check on the accepted FULLER run; not an experiment."""

    RUN = '20261006T041633Z-990aa1bd6737'

    def assert_no_leak(self, response):
        for needle in (str(self.runs_root), str(self.state_root), self.RUN + '/', 'cleaned-video'):
            self.assertNotIn(needle.encode(), response.payload)

    def test_actual_demo_job(self):
        self.runs_root = Path(os.environ.get('WEB_JOBS_DEMO_RUNS_ROOT', str(ROOT.parents[2]))).resolve()
        run_dir = self.runs_root / 'artifacts' / 'runs' / self.RUN
        self.assertTrue(run_dir.is_dir())
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        self.state_root = ROOT / 'artifacts' / 's2' / 'web_jobs' / f'demo-state-{stamp}'
        before = tree_digest(run_dir)
        jobs = WebJobs(self.runs_root, self.state_root)
        jobs.start()
        server = web_api.WebAPIServer(jobs, 0)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        thread.start()
        try:
            client = Client(self, server)
            admitted = client.post('/sources', {'selector': f'{self.RUN}/export/cleaned-video.mov'})
            self.assertIn(admitted.status, (200, 201), admitted.json)
            started = time.monotonic()
            submitted = client.post('/jobs', {'tool': 'share_export', 'idempotency_key': f'demo-{stamp}',
                                              'source_artifact_id': admitted.json['source_artifact_id'],
                                              'parameters': {'timeout_seconds': 900}})
            self.assertEqual(submitted.status, 202, submitted.json)
            job_id = submitted.json['job_id']
            end = time.monotonic() + 960
            while True:
                job = client.get(f'/jobs/{job_id}').json
                if job['state'] in web_jobs.TERMINAL or time.monotonic() > end:
                    break
                time.sleep(1)
            wall = time.monotonic() - started
            download = None
            artifacts = {a['role']: a for a in job['artifacts']}
            if 'share_mp4' in artifacts:
                response = client.get(f'/artifacts/{artifacts["share_mp4"]["artifact_id"]}')
                download = {'status': response.status, 'bytes': len(response.payload),
                            'sha256': hashlib.sha256(response.payload).hexdigest(),
                            'matches_published_row': hashlib.sha256(response.payload).hexdigest()
                            == artifacts['share_mp4']['sha256']}
            replay = client.post('/jobs', {'tool': 'share_export', 'idempotency_key': f'demo-{stamp}',
                                           'source_artifact_id': admitted.json['source_artifact_id'],
                                           'parameters': {'timeout_seconds': 900}})
            counts = jobs.counts()
        finally:
            server.stop()
            thread.join(timeout=10)
            jobs.close()
        after = tree_digest(run_dir)
        receipt = {
            'receipt': 'web_jobs-demo-receipt', 'claim_class': 'structural_delivery_check',
            'run_id': self.RUN, 'role': 'accepted FULLER audio run, export/cleaned-video',
            'source': {k: admitted.json[k] for k in ('source_artifact_id', 'source_id', 'source_binding', 'sha256',
                                                       'size_bytes')},
            'job_id': job_id, 'state': job['state'], 'reason_code': job['reason_code'],
            'parameters': job['parameters'], 'capability_revision': job['capability_revision'],
            'attempts': job['attempts'], 'artifacts': job['artifacts'], 'download': download,
            'wall_seconds_submit_to_terminal': round(wall, 3),
            'replay': {'status': replay.status, 'same_job': replay.json.get('job_id') == job_id,
                       'replayed': replay.json.get('replayed'), 'attempts': len(replay.json.get('attempts', []))},
            'store_counts_after': counts,
            'accepted_run_tree': {'before_sha256': before[0], 'after_sha256': after[0], 'entries': before[1],
                                  'unchanged': before == after,
                                  'method': 'relative paths + type + size + mtime_ns + sha256'},
            'unknowns': job['unknowns'], 'host': _host_facts(),
        }
        target = ROOT / 'artifacts' / 's2' / 'web_jobs'
        target.mkdir(parents=True, exist_ok=True)
        (target / 'demo-receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
        self.assertEqual(before, after)
        self.assertTrue(receipt['replay']['same_job'])
        self.assertIn(job['state'], ('succeeded', 'failed'))


def tearDownModule():
    target = os.environ.get('WEB_JOBS_METRICS')
    if target:
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_text(json.dumps(METRICS, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    unittest.main()
