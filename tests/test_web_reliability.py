"""S2 web_reliability: executable WEB demo, bounded failure injections and an opt-in real-take web job.

Contract: docs/spec/sprints/WEB_RELIABILITY_S2.md (frozen 665b5ee). Everything runs in-process
against ``web_api.WebAPIServer`` on an ephemeral 127.0.0.1 port; the optional BFF arm runs the
built SvelteKit app as a test-owned ``node serve.js`` process group on loopback. Nothing here
forks a service, detaches or opens a non-loopback listener. Product modules are imported only.

Claim classes: every number this module records is a measurement on this host (no SLO), a
static check, or an explicit unknown. No listening, tone, ~32 Hz low-register, musical or
note-correctness claim is made; the synthetic fixture's 32.70 Hz sine is content only.
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
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))

import test_web_jobs as wj  # noqa: E402  (fixtures and helpers, import only)
import tool_api  # noqa: E402
import web_api  # noqa: E402
import web_jobs  # noqa: E402
from web_jobs import WebJobs, WebJobsError  # noqa: E402

SPEC = ROOT / 'docs' / 'spec' / 'sprints' / 'WEB_RELIABILITY_S2.md'
OUT_DIR = ROOT / 'artifacts' / 's2' / 'web_reliability'
LOOPBACK = '127.0.0.1'
DEMO_PARAMETERS = {'height': 240, 'timeout_seconds': 120}
STUB_POLL_S, REAL_POLL_S = 30, 180
BEAT_S, GONE_S = 15, 10
STATUS_RUN = ('run_exact', 'run_adapted', 'run_partial')

# --------------------------------------------------------------------------- frozen injection table (section 6)

INJECTIONS = (
    {'id': 'FI-1', 'listed_class': 'expired lease', 'listed_in': 'a', 'status': 'run_adapted',
     'reason': 'web_jobs has no lease timer; instance loss with a running attempt (instance_id != current) '
               'is the closest real failure and is injected instead',
     'sub_cases': ('a_dead_worker', 'b_live_unowned_worker'), 'not_run_sub_cases': ()},
    {'id': 'FI-2', 'listed_class': 'duplicate delivery', 'listed_in': 'a', 'status': 'run_exact', 'reason': None,
     'sub_cases': ('a_8_concurrent_identical_posts', 'b_second_supervisor_same_state_root'), 'not_run_sub_cases': ()},
    {'id': 'FI-3', 'listed_class': 'quota exhaustion', 'listed_in': 'a', 'status': 'run_partial',
     'reason': 'only the queue, request-body and source-size bounds exist in web_jobs/web_api',
     'sub_cases': ('a_queue_full', 'b_body_too_large', 'c_source_too_large'),
     'not_run_sub_cases': (
         {'name': 'disk', 'reason': 'no disk quota exists'},
         {'name': 'rss', 'reason': 'no memory (RSS) quota exists'},
         {'name': 'cpu', 'reason': 'no CPU quota exists'},
         {'name': 'per_operator_rate', 'reason': 'no per-operator rate limit exists'})},
    {'id': 'FI-4', 'listed_class': 'access denial', 'listed_in': 'a', 'status': 'run_exact', 'reason': None,
     'sub_cases': ('token_host_origin_private_unknown',), 'not_run_sub_cases': ()},
    {'id': 'FI-5', 'listed_class': 'hash mismatch', 'listed_in': 'a', 'status': 'run_exact', 'reason': None,
     'sub_cases': ('a_source_changed_before_claim', 'b_published_bytes_changed', 'c_published_file_deleted'),
     'not_run_sub_cases': ()},
    {'id': 'FI-6', 'listed_class': 'model absence', 'listed_in': 'a', 'status': 'not_applicable',
     'reason': 'share_export, the only admitted job type, uses no model; nothing is injected',
     'sub_cases': (), 'not_run_sub_cases': ()},
    {'id': 'FI-7', 'listed_class': 'output committed before transport failure', 'listed_in': 'a',
     'status': 'run_exact', 'reason': None, 'sub_cases': ('client_closes_before_response',), 'not_run_sub_cases': ()},
    {'id': 'FI-8', 'listed_class': 'crash around enqueue', 'listed_in': 'b', 'status': 'run_exact', 'reason': None,
     'sub_cases': ('queued_then_restart',), 'not_run_sub_cases': ()},
    {'id': 'FI-9', 'listed_class': 'crash around lease (claim)', 'listed_in': 'b', 'status': 'run_adapted',
     'reason': 'no seam exists between claim and launch; the instance is stopped after claim with the worker '
               'running and the test kills its own stub',
     'sub_cases': ('stop_after_claim_then_replay_retry',), 'not_run_sub_cases': ()},
    {'id': 'FI-10', 'listed_class': 'crash during render', 'listed_in': 'b', 'status': 'run_exact', 'reason': None,
     'sub_cases': ('sigkill_own_stub_group_server_alive',), 'not_run_sub_cases': ()},
    {'id': 'FI-11', 'listed_class': 'crash around publication', 'listed_in': 'b', 'status': 'run_exact',
     'reason': None, 'sub_cases': ('after_publish_before_commit',), 'not_run_sub_cases': ()},
)
FI = {row['id']: row for row in INJECTIONS}

# --------------------------------------------------------------------------- explicit unknowns (section 9)

UNKNOWN_KEYS = frozenset({
    'listening_acceptance', 'master_adopted', 'low_register_preservation', 'low_register_preservation_reason',
    'musical_review', 'musical_review_reason', 'decoded_picture_identity', 'decoded_picture_identity_reason',
    'physical_capture_sync', 'physical_capture_sync_reason', 'slo', 'hosted_rollout', 'exactly_once',
    'memory_bytes_peak', 'memory_bytes_peak_reason', 'cpu_seconds', 'cpu_seconds_reason',
    'injection_classes_not_run', 'bff_arm', 'bff_arm_reason', 'ui_rendering', 'ui_rendering_reason',
    'output_determinism_vs_prior_run', 'host_load'})
DETERMINISM = ('observed_equal', 'observed_not_equal', 'not_compared')


def injection_classes_not_run():
    rows = [{'id': row['id'], 'reason': row['reason']} for row in INJECTIONS if row['status'] not in STATUS_RUN]
    for row in INJECTIONS:
        rows += [{'id': f'{row["id"]}/{sub["name"]}', 'reason': sub['reason']} for sub in row['not_run_sub_cases']]
    return rows


def build_unknowns(*, bff_arm=None, bff_reason='BFF arm not executed in this process',
                   determinism='not_compared', host_load=None):
    if determinism not in DETERMINISM:
        raise ValueError('unknown determinism observation')
    return {
        'listening_acceptance': 'not_established',
        'master_adopted': False,
        'low_register_preservation': None,
        'low_register_preservation_reason': 'the lossy AAC sharing derivative is not measured at ~32 Hz by this lane',
        'musical_review': None,
        'musical_review_reason': 'no note-correctness, missed-note or phrase verdicts',
        'decoded_picture_identity': None,
        'decoded_picture_identity_reason': 'packet PTS and frame counts only, no per-picture comparison',
        'physical_capture_sync': None,
        'physical_capture_sync_reason': 'not verified',
        'slo': 'not_claimed',
        'hosted_rollout': 'not_claimed',
        'exactly_once': 'not_claimed',
        'memory_bytes_peak': None,
        'memory_bytes_peak_reason': 'not measured; no OS quota',
        'cpu_seconds': None,
        'cpu_seconds_reason': 'not measured; no OS quota',
        'injection_classes_not_run': injection_classes_not_run(),
        'bff_arm': bff_arm,
        'bff_arm_reason': None if bff_arm == 'run' else bff_reason,
        'ui_rendering': None,
        'ui_rendering_reason': 'no browser render or screenshot in this lane',
        'output_determinism_vs_prior_run': determinism,
        'host_load': host_load,
    }


def loadavg():
    with contextlib.suppress(OSError, AttributeError):
        return [round(value, 2) for value in os.getloadavg()]
    return None


def host_facts():
    """Descriptive, path-free and hostname-free host facts."""
    def first_line(command):
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        lines = [line for line in (done.stdout or done.stderr).splitlines() if line.strip()]
        return lines[0].strip()[:120] if lines else None
    ffmpeg = None
    if wj.HAVE_FFMPEG:
        line = first_line([wj.FFMPEG, '-version'])
        ffmpeg = ' '.join(line.split()[:3]) if line else None
    return {'system_machine': f'{platform.system()} {platform.machine()}',
            'cpu': first_line(['sysctl', '-n', 'machdep.cpu.brand_string']) if platform.system() == 'Darwin' else None,
            'logical_cpus': os.cpu_count(), 'python': platform.python_version(),
            'node': first_line(['node', '--version']) if shutil.which('node') else None,
            'pnpm': first_line(['pnpm', '--version']) if shutil.which('pnpm') else None, 'ffmpeg': ffmpeg}


METRICS = {
    'schema': 'video-utils/web-reliability-metrics', 'schema_version': 1, 'lane': 'web_reliability',
    'sprint': '20261006-s2', 'tracker': 'TIN-5616', 'spec': 'docs/spec/sprints/WEB_RELIABILITY_S2.md',
    'claim_class': 'measurement_this_host_only', 'slo': 'not_claimed',
    'api_demo': None, 'bff_demo': None, 'injections': {}, 'skips': {},
    'leak': {'responses_checked': 0, 'leaking_responses': 0},
    'servers_bound': [], 'node_apps_started': 0, 'runs_tree_unchanged_classes': [],
    'host_load_start': loadavg(), 'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
NODE_APPS = []
_LOCK = threading.Lock()


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- HTTP plumbing

class Resp:
    def __init__(self, status, headers, payload):
        self.status = status
        self.headers = headers
        self.payload = payload
        kind = headers.get('content-type', '')
        self.json = None
        if payload and kind.startswith('application/json'):
            with contextlib.suppress(ValueError):
                self.json = json.loads(payload)


def http_request(test, port, method, path, data=None, headers=None, timeout=60):
    connection = http.client.HTTPConnection(LOOPBACK, port, timeout=timeout)
    try:
        connection.request(method, path, body=data, headers=headers or {})
        response = connection.getresponse()
        result = Resp(response.status, {k.lower(): v for k, v in response.getheaders()}, response.read())
    finally:
        connection.close()
    test.assert_no_leak(result)
    return result


class ApiTransport:
    """Direct /api/v1 calls with the per-start bearer token."""

    arm = 'api'
    prefix = '/api/v1'

    def __init__(self, test, env):
        self.test = test
        self.bind(env)

    def bind(self, env):
        self.env = env
        self.port = env.server.server_address[1]
        self.token = env.server.token

    def request(self, method, path, body=None, token=None):
        headers = {'Host': f'{LOOPBACK}:{self.port}', 'Authorization': 'Bearer ' + (token or self.token)}
        data = None
        if method == 'POST':
            data = json.dumps({} if body is None else body).encode()
            headers['Content-Type'] = 'application/json'
        return http_request(self.test, self.port, method, self.prefix + path, data, headers)

    def get(self, path):
        return self.request('GET', path)

    def post(self, path, body=None):
        return self.request('POST', path, body)

    @staticmethod
    def code(response):
        return (response.json or {}).get('code')

    @staticmethod
    def wrapper_code(_response):
        return None

    @staticmethod
    def job_body(source, key, parameters):
        return {'tool': 'share_export', 'source_artifact_id': source, 'idempotency_key': key, 'parameters': parameters}

    @staticmethod
    def key(name):
        return name

    def old_token_probe(self, job_id, old_tokens):
        observed = []
        for token in old_tokens:
            response = self.request('GET', f'/jobs/{job_id}', token=token)
            observed.append({'http_status': response.status, 'code': self.code(response)})
        ok = bool(observed) and all(o == {'http_status': 401, 'code': 'token_required'} for o in observed)
        return ok, observed

    def close(self):
        pass


class BffTransport:
    """Calls through the built SvelteKit BFF (`/api/*`), same-origin, test-owned `node serve.js`."""

    arm = 'bff'
    prefix = '/api'

    def __init__(self, test, env, ws):
        self.test = test
        self.ws = ws
        self.app = None
        self.bind(env)

    def _start(self, port, token):
        type(self.test).extra_forbidden.append(f'{LOOPBACK}:{port}')
        app = self.ws._App(f'http://{LOOPBACK}:{port}', token=token)
        NODE_APPS.append(app)
        METRICS['node_apps_started'] += 1
        return app

    def bind(self, env):
        self.close()
        self.env = env
        self.app = self._start(env.server.server_address[1], env.server.token)

    def request(self, method, path, body=None, app=None):
        app = app or self.app
        headers = {'accept': 'application/json, text/html'}
        data = None
        if method == 'POST':
            data = json.dumps({} if body is None else body).encode()
            headers['origin'] = app.origin
            headers['content-type'] = 'application/json'
        return http_request(self.test, app.port, method, self.prefix + path, data, headers)

    def get(self, path):
        return self.request('GET', path)

    def post(self, path, body=None):
        return self.request('POST', path, body)

    @staticmethod
    def code(response):
        body = response.json or {}
        return body.get('upstream_code') or body.get('code')

    @staticmethod
    def wrapper_code(response):
        return (response.json or {}).get('code')

    @staticmethod
    def job_body(source, key, parameters):
        return {'source_artifact_id': source, 'parameters': parameters, 'idempotency_key': key}

    @staticmethod
    def key(name):
        # The BFF accepts only ^ui-[0-9a-f]{32}$ keys (web/src/lib/server/job-request.ts); the frozen
        # `bff-` names are mapped deterministically and the mapping is recorded in the receipt.
        return 'ui-' + sha_bytes(('bff-' + name).encode())[:32]

    def old_token_probe(self, job_id, old_tokens):
        observed = []
        for token in old_tokens[-1:]:
            app = self._start(self.env.server.server_address[1], token)
            try:
                response = self.request('GET', f'/jobs/{job_id}', app=app)
            finally:
                app.close()
            body = response.json or {}
            observed.append({'http_status': response.status, 'code': body.get('code'),
                             'upstream_status': body.get('upstream_status')})
        ok = bool(observed) and all(o == {'http_status': 502, 'code': 'control_api_token_refused',
                                          'upstream_status': 401} for o in observed)
        return ok, observed

    def close(self):
        if self.app is not None:
            self.app.close()
            self.app = None


# --------------------------------------------------------------------------- shared base

class ReliabilityBase(unittest.TestCase):
    tokens: list
    extra_forbidden: list

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix='web-reliability-')
        cls.raw_base = cls._tmp.name
        cls.base = Path(cls._tmp.name).resolve()
        cls.tokens = []
        cls.extra_forbidden = []
        cls.counter = 0

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    # ----------------------------------------------------------------- leak checks

    def forbidden(self):
        needles = {str(self.base), self.raw_base, wj.SENTINEL, str(ROOT), 'RUN-A/', *self.tokens,
                   *self.extra_forbidden}
        return sorted((n for n in needles if n), key=len)

    def assert_no_leak(self, response):
        headers = getattr(response, 'headers', {}) or {}
        blob = response.payload + json.dumps(headers, sort_keys=True).encode()
        leaked = [needle for needle in self.forbidden() if needle.encode() in blob]
        with _LOCK:
            METRICS['leak']['responses_checked'] += 1
            METRICS['leak']['leaking_responses'] += bool(leaked)
        self.assertFalse(leaked, f'response leaked {len(leaked)} forbidden host-path/selector/token needle(s)')

    # ----------------------------------------------------------------- environments

    def state(self, label='s'):
        type(self).counter += 1
        return self.base / 'states' / f'{self._testMethodName}-{label}-{type(self).counter}'

    def env(self, state_root, runs_root=None, **kwargs):
        env = wj.Env(self, state_root, runs_root=runs_root or self.R, **kwargs)
        host = env.server.server_address[0]
        METRICS['servers_bound'].append(host)
        self.assertEqual(host, LOOPBACK)
        type(self).tokens.append(env.server.token)
        return env

    # ----------------------------------------------------------------- store inspection (read-only)

    @staticmethod
    def ro(state_root):
        return sqlite3.connect((Path(state_root) / web_jobs.DB_NAME).as_uri() + '?mode=ro', uri=True, timeout=5)

    def db_counts(self, state_root):
        connection = self.ro(state_root)
        try:
            return {table: connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                    for table in ('sources', 'jobs', 'attempts', 'artifacts')}
        finally:
            connection.close()

    @staticmethod
    def publications(state_root):
        return sorted(f'{p.parent.parent.name}/{p.parent.name}'
                      for p in (Path(state_root) / 'jobs').glob('*/attempt-*/publication.json'))

    @staticmethod
    def attempt_dirs(state_root):
        return sorted(f'{p.parent.name}/{p.name}' for p in (Path(state_root) / 'jobs').glob('*/attempt-*')
                      if p.is_dir())

    def audit(self, state_root, accepted):
        """Lost job records and duplicate publications for one execution (section 6 reporting)."""
        connection = self.ro(state_root)
        try:
            jobs = {row[0] for row in connection.execute('SELECT job_id FROM jobs')}
            succeeded = {}
            for job_id, _attempt in connection.execute("SELECT job_id, attempt FROM attempts WHERE state = 'succeeded'"):
                succeeded[job_id] = succeeded.get(job_id, 0) + 1
            rows = {}
            for (job_id,) in connection.execute('SELECT job_id FROM artifacts'):
                rows[job_id] = rows.get(job_id, 0) + 1
            attempts = connection.execute('SELECT count(*) FROM attempts').fetchone()[0]
        finally:
            connection.close()
        publications = {}
        for item in self.publications(state_root):
            job_id = item.split('/', 1)[0]
            publications[job_id] = publications.get(job_id, 0) + 1
        duplicate = sum(max(0, n - succeeded.get(job, 0)) for job, n in publications.items())
        duplicate += sum(max(0, n - 3 * succeeded.get(job, 0)) for job, n in rows.items())
        return {'accepted_job_ids': len(set(accepted)), 'lost_job_records': len(set(accepted) - jobs),
                'duplicate_publications': duplicate, 'jobs': len(jobs), 'attempts': attempts,
                'publications': sum(publications.values()), 'artifact_rows': sum(rows.values())}

    # ----------------------------------------------------------------- waits

    def wait_beat(self, builder, count, timeout=BEAT_S):
        """Heartbeat of the ``count``-th stub launch (pid and same-group child pid)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if len(builder.beats) >= count and builder.beats[count - 1].exists():
                with contextlib.suppress(ValueError):
                    return json.loads(builder.beats[count - 1].read_text())
            time.sleep(0.02)
        self.fail(f'stub heartbeat {count} not observed within {timeout} s')

    @staticmethod
    def alive(pid):
        try:
            os.kill(pid, 0)  # signal 0: existence check, nothing delivered
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def wait_gone(self, pid, timeout=GONE_S):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if not self.alive(pid):
                return True
            time.sleep(0.02)
        return False

    def poll(self, transport, job_id, bound, interval, until=web_jobs.TERMINAL):
        observed, end = [], time.monotonic() + bound
        while True:
            response = transport.get(f'/jobs/{job_id}')
            self.assertEqual(response.status, 200, response.json)
            job = response.json
            seen = [job['state'], job.get('phase')]
            if not observed or observed[-1] != seen:
                observed.append(seen)
            if job['state'] in until:
                return job, observed, False
            if time.monotonic() > end:
                return job, observed, True
            time.sleep(interval)


# --------------------------------------------------------------------------- 1 static contract checks

class ContractStaticTests(ReliabilityBase):

    def test_injection_table_frozen_with_denominator(self):
        self.assertEqual([row['id'] for row in INJECTIONS], [f'FI-{n}' for n in range(1, 12)])
        statuses = {}
        for row in INJECTIONS:
            statuses[row['status']] = statuses.get(row['status'], 0) + 1
            if row['status'] in ('not_applicable', 'run_partial', 'run_adapted'):
                self.assertTrue(row['reason'], row['id'])
            if row['status'] == 'run_partial':
                self.assertTrue(row['not_run_sub_cases'], row['id'])
            if row['status'] in STATUS_RUN:
                self.assertTrue(row['sub_cases'], row['id'])
        # Row-level frozen statuses (spec section 6 table). The spec's summary sentence ("9 run: 6 exact,
        # 2 adapted, 1 partial") miscounts its own table (6+2+1+1 = 10 != 11 rows); the rows are authoritative
        # and the discrepancy is recorded, not corrected after the fact (spec section 14, appended).
        self.assertEqual(statuses, {'run_exact': 7, 'run_adapted': 2, 'run_partial': 1, 'not_applicable': 1})
        self.assertEqual(sum(statuses.get(s, 0) for s in STATUS_RUN), 10)
        self.assertEqual(({r['listed_in'] for r in INJECTIONS if r['id'] in ('FI-8', 'FI-9', 'FI-10', 'FI-11')},
                          sum(r['listed_in'] == 'a' for r in INJECTIONS)), ({'b'}, 7))
        # The module table and the frozen spec table agree row by row (id, class, status).
        spec_rows = re.findall(r'^\| (FI-\d+) \| ([^|]+?) \| (\w+) \|', SPEC.read_text(), re.M)
        self.assertEqual([(i, c.strip(), s) for i, c, s in spec_rows],
                         [(r['id'], r['listed_class'], r['status']) for r in INJECTIONS])
        names = {f'test_fi{n:02d}' for n in range(1, 12)}
        defined = {name[:9] for name in dir(FailureInjectionTests) if name.startswith('test_fi')}
        self.assertEqual(defined, names)
        METRICS['injection_table'] = {
            'listed': len(INJECTIONS), 'status_counts': statuses,
            'planned_run': sum(statuses.get(s, 0) for s in STATUS_RUN),
            'frozen_summary_text_discrepancy': 'spec section 6 summary says 9 run (6 exact); its own 11-row table '
                                               'has 7 run_exact rows, i.e. 10 run; rows are authoritative'}

    def test_servers_bind_loopback_only(self):
        self.assertEqual(web_api.BIND_ADDRESS, LOOPBACK)
        runs = self.base / 'R-static'
        wj.make_runs_root(runs)
        jobs = WebJobs(runs, self.base / 'state-static', command_builder=wj.StubBuilder(self.base / 'beats-static'))
        try:
            server = web_api.WebAPIServer(jobs, 0)
            try:
                METRICS['servers_bound'].append(server.server_address[0])
                self.assertEqual(server.server_address[0], LOOPBACK)
            finally:
                server.server_close()
        finally:
            jobs.close()
        source = Path(__file__).read_text()
        colons = ':' + ':'
        wildcard = ('0.0.' + '0.0', "'" + colons + "'", '"' + colons + '"')
        service = ('os.' + 'fork', 'os.' + 'setsid', 'daemon' + '(', 'launch' + 'ctl', 'no' + 'hup', 'Launch' + 'Agents')
        self.assertEqual([needle for needle in wildcard + service if needle in source], [])
        # Every server constructed anywhere in this module so far was loopback.
        self.assertEqual({host for host in METRICS['servers_bound']}, {LOOPBACK})

    def test_receipt_unknowns_shape(self):
        for kwargs in ({}, {'bff_arm': 'run'}, {'determinism': 'observed_equal', 'host_load': {'start': [1.0]}}):
            unknowns = build_unknowns(**kwargs)
            self.assertEqual(set(unknowns), UNKNOWN_KEYS)
            self.assertEqual((unknowns['listening_acceptance'], unknowns['master_adopted'], unknowns['slo'],
                              unknowns['hosted_rollout'], unknowns['exactly_once']),
                             ('not_established', False, 'not_claimed', 'not_claimed', 'not_claimed'))
            for key in ('low_register_preservation', 'musical_review', 'decoded_picture_identity',
                        'physical_capture_sync', 'memory_bytes_peak', 'cpu_seconds', 'ui_rendering'):
                self.assertIsNone(unknowns[key])
                self.assertIsInstance(unknowns[key + '_reason'], str)
            if unknowns['bff_arm'] is None:
                self.assertIsInstance(unknowns['bff_arm_reason'], str)
            self.assertIn(unknowns['output_determinism_vs_prior_run'], DETERMINISM)
        not_run = [row['id'] for row in build_unknowns()['injection_classes_not_run']]
        self.assertEqual(not_run, ['FI-6', 'FI-3/disk', 'FI-3/rss', 'FI-3/cpu', 'FI-3/per_operator_rate'])
        with self.assertRaises(ValueError):
            build_unknowns(determinism='claimed_equal')


# --------------------------------------------------------------------------- 2-3 WEB demo (shared storyline)

class DemoBase(ReliabilityBase):
    ARM = None

    def step(self, name, request, fn):
        started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds')
        clock = time.perf_counter()
        record = {'step': len(self.steps) + 1, 'name': name, 'request': request, 'started_at': started}
        self.steps.append(record)
        try:
            status, code, assertions, extra = fn()
        except BaseException as error:
            record.update({'passed': False, 'error': type(error).__name__,
                           'wall_ms': round((time.perf_counter() - clock) * 1000, 1)})
            raise
        record.update({'http_status': status, 'code': code, 'wall_ms': round((time.perf_counter() - clock) * 1000, 1),
                       'assertions': assertions, **extra})
        failed = [key for key, ok in assertions.items() if not ok]
        record['passed'] = not failed
        self.assertEqual(failed, [], f'{self.ARM} step {record["step"]} {name}: {failed}; {extra}')
        return record

    def run_story(self, make_transport):
        arm = self.ARM
        base = self.base / f'demo-{arm}'
        R = type(self).R = base / 'R'
        run = wj.make_runs_root(R)
        (run / 'notes.txt').write_text('practice notes, not media')
        wj.make_clip(run / 'export' / 'clip.mov')
        runs_digest = wj.tree_digest(R / 'artifacts' / 'runs')
        S = base / 'S'
        self.steps = []
        keys = {}
        result = {'arm': arm, 'steps': self.steps, 'keys': keys, 'transport': None,
                  'fixture': 'synthetic 2 s testsrc2 320x240@24 + sine 32.70 Hz, H.264/AAC MOV (no spectral claim)'}
        METRICS[f'{arm}_demo'] = result
        transport = None
        try:
            transport = self._story(make_transport, R, S, run, runs_digest, keys, result)
        finally:
            if transport is not None:
                transport.close()
            passed = sum(1 for s in self.steps if s.get('passed'))
            result['steps_passed'] = passed
            result['steps_total'] = 13 if arm == 'bff' else 12
            result['steps_completed'] = f'{passed}/{result["steps_total"]}'

    def _story(self, make_transport, R, S, run, runs_digest, keys, result):
        arm = self.ARM
        ids = {}
        env1 = self.env(S, R, builder=None)
        t = make_transport(env1)
        result['transport'] = {'api': 'in-process web_api /api/v1', 'bff': 'built web/ node serve.js /api/*'}[arm]
        keys.update({'A': t.key('demo-preview-A1'), 'B': t.key('demo-cancel-B1'), 'C': t.key('demo-interrupt-C1')})
        p = t.prefix
        old_tokens = [env1.server.token]
        bodies = {}

        def s1():
            response = t.post('/sources', {'selector': 'RUN-A/export/clip.mov'})
            ids['source'] = (response.json or {}).get('source_artifact_id')
            listing = t.get('/sources')
            listed = [s.get('source_artifact_id') for s in (listing.json or {}).get('sources', [])]
            return response.status, t.code(response), {
                'status_201': response.status == 201,
                'art_id': bool(ids['source'] and web_jobs.ARTIFACT_ID.fullmatch(ids['source'])),
                'no_selector_in_body': b'RUN-A' not in response.payload,
                'listing_200': listing.status == 200, 'listed': ids['source'] in listed}, {
                'source_artifact_id': ids['source'], 'sha256': (response.json or {}).get('sha256'),
                'listing_status': listing.status}
        self.step('admit', f'POST {p}/sources', s1)

        def s2():
            before = (env1.jobs.counts(), self.db_counts(S))
            listing_before = t.get('/sources').json
            response = t.post('/sources', {'selector': 'RUN-A/notes.txt'})
            after = (env1.jobs.counts(), self.db_counts(S))
            listing_after = t.get('/sources').json
            return response.status, t.code(response), {
                'status_422': response.status == 422, 'code_not_media': t.code(response) == 'not_media',
                'store_counts_unchanged': before == after, 'listing_unchanged': listing_before == listing_after}, {
                'wrapper_code': t.wrapper_code(response)}
        self.step('rejected_input', f'POST {p}/sources', s2)

        bodies['A'] = t.job_body(ids['source'], keys['A'], dict(DEMO_PARAMETERS))

        def s3():
            response = t.post('/jobs', bodies['A'])
            ids['A'] = (response.json or {}).get('job_id')
            return response.status, t.code(response), {
                'status_202': response.status == 202, 'replayed_false': (response.json or {}).get('replayed') is False,
                'job_id': bool(ids['A'] and web_jobs.JOB_ID.fullmatch(ids['A']))}, {
                'job_id': ids['A'], 'state_at_submit': (response.json or {}).get('state')}
        self.step('submit_preview', f'POST {p}/jobs', s3)

        def s4():
            clock = time.perf_counter()
            job, observed, timed_out = self.poll(t, ids['A'], REAL_POLL_S, 0.25)
            ids['A_job'] = job
            attempt = job['attempts'][0]
            checks = attempt['worker_checks'] or {}
            return 200, job['reason_code'], {
                'not_timed_out': not timed_out, 'succeeded': job['state'] == 'succeeded',
                'worker_kind_real': attempt['worker_kind'] == 'tool_api_share_export',
                'exported_unreviewed': checks.get('status') == 'exported_unreviewed',
                'master_not_adopted': checks.get('master_adopted') is False,
                'listening_not_accepted': checks.get('listening_accepted') is False}, {
                'observed_state_phase_sequence': observed,
                'submit_to_terminal_seconds_host': round(time.perf_counter() - clock, 3),
                'worker_kind': attempt['worker_kind']}
        self.step('poll_terminal', f'GET {p}/jobs/{{A}}', s4)

        def s5():
            roles = {a['role']: a for a in ids['A_job']['artifacts']}
            mp4 = roles['share_mp4']
            response = t.get(f'/artifacts/{mp4["artifact_id"]}')
            private = t.get(f'/artifacts/{roles["share_receipt"]["artifact_id"]}')
            body_sha = sha_bytes(response.payload)
            ids['A_mp4'] = mp4
            return response.status, t.code(private), {
                'status_200': response.status == 200, 'body_eq_header': body_sha == response.headers.get('x-artifact-sha256'),
                'header_eq_row': response.headers.get('x-artifact-sha256') == mp4['sha256'],
                'bytes_eq_row': len(response.payload) == mp4['size_bytes'],
                'receipt_private_403': private.status == 403 and t.code(private) == 'artifact_private'}, {
                'share_mp4': {'artifact_id': mp4['artifact_id'], 'sha256': mp4['sha256'], 'bytes': mp4['size_bytes']},
                'receipt_refusal': {'http_status': private.status, 'code': t.code(private),
                                    'wrapper_code': t.wrapper_code(private)}}
        self.step('private_download', f'GET {p}/artifacts/{{share_mp4}}', s5)

        def s6():
            replays = [t.post('/jobs', bodies['A']) for _ in range(3)]
            counts = self.db_counts(S)
            ok = [(r.status, (r.json or {}).get('replayed'), (r.json or {}).get('job_id')) == (200, True, ids['A'])
                  for r in replays]
            return replays[-1].status, None, {
                'replays_same_job': all(ok), 'jobs_1': counts['jobs'] == 1, 'attempts_1': counts['attempts'] == 1,
                'artifact_rows_3': counts['artifacts'] == 3,
                'one_attempt_dir': sorted(os.listdir(S / 'jobs' / ids['A'])) == ['attempt-1'],
                'one_publication': self.publications(S) == [f'{ids["A"]}/attempt-1']}, {
                'replays': len(replays), 'replays_same_job': sum(ok), 'counts': counts}
        self.step('idempotent_resubmit', f'POST {p}/jobs x3', s6)
        a_digest = wj.tree_digest(S / 'jobs' / ids['A'])

        # Instance I2: stub builder (sleep, sleep) on the same state root.
        env1.stop()
        env2 = self.env(S, R, builder=wj.StubBuilder(S.parent / 'beats-I2', modes=['sleep', 'sleep']))
        old_tokens.append(env2.server.token)
        t.bind(env2)

        bodies['B'] = t.job_body(ids['source'], keys['B'], dict(DEMO_PARAMETERS))

        def s7():
            submitted = t.post('/jobs', bodies['B'])
            ids['B'] = (submitted.json or {}).get('job_id')
            self.poll(t, ids['B'], STUB_POLL_S, 0.05, until=('running',) + web_jobs.TERMINAL)
            beat = self.wait_beat(env2.builder, 1)
            pids = [beat['pid'], beat['child']]
            alive_before = [self.alive(pid) for pid in pids]
            cancel = t.post(f'/jobs/{ids["B"]}/cancel', {})
            job, observed, timed_out = self.poll(t, ids['B'], STUB_POLL_S, 0.05)
            gone = [self.wait_gone(pid) for pid in pids]
            receipt = job['attempts'][0]['cancel'] or {}
            entries = sorted(os.listdir(S / 'jobs' / ids['B'])) if (S / 'jobs' / ids['B']).exists() else []
            return cancel.status, job['reason_code'], {
                'submit_202': submitted.status == 202, 'alive_before_cancel': all(alive_before),
                'cancel_202': cancel.status == 202, 'not_timed_out': not timed_out,
                'cancelled': job['state'] == 'cancelled', 'owned_pids_gone': gone == [True, True],
                'ack_le_observed_stop': bool(receipt.get('ack_at') and receipt.get('observed_stop_at')
                                             and receipt['ack_at'] <= receipt['observed_stop_at']),
                'owned_group_signalled': receipt.get('signal_target') == 'owned_process_group',
                'zero_artifacts': job['artifacts'] == [],
                'no_attempt_dir': not [e for e in entries if e.startswith('attempt-')],
                'no_staging_dir': not [e for e in entries if e.startswith('.staging-')]}, {
                'job_id': ids['B'], 'owned_pids_gone': f'{sum(gone)}/{len(gone)}', 'signals_sent': receipt.get('signals_sent'),
                'observed_state_phase_sequence': observed, 'worker_kind': job['attempts'][0]['worker_kind']}
        self.step('cancel_mid_run', f'POST {p}/jobs/{{B}}/cancel', s7)

        bodies['C'] = t.job_body(ids['source'], keys['C'], dict(DEMO_PARAMETERS))
        c_state = {}

        def s8():
            submitted = t.post('/jobs', bodies['C'])
            ids['C'] = (submitted.json or {}).get('job_id')
            running, _, _ = self.poll(t, ids['C'], STUB_POLL_S, 0.05, until=('running',) + web_jobs.TERMINAL)
            beat = self.wait_beat(env2.builder, 2)
            env2.stop()  # server stop + store close: cancels nothing
            wj.sigkill_own_group(beat['pid'])  # R-N11: only the group this test's own I2 instance created
            env2.kill_detached()
            gone = [self.wait_gone(pid) for pid in (beat['pid'], beat['child'])]
            c_state['digest'] = wj.tree_digest(S / 'jobs' / ids['C'])
            entries = sorted(os.listdir(S / 'jobs' / ids['C']))
            return submitted.status, None, {
                'submit_202': submitted.status == 202, 'was_running': running['state'] == 'running',
                'owned_stub_group_gone': gone == [True, True],
                'staging_left_for_reconciliation': len([e for e in entries if e.startswith('.staging-1-')]) == 1}, {
                'job_id': ids['C'], 'job_dir_entries': len(entries), 'attempt1_tree_digest': c_state['digest'][0],
                'kill_target': 'own stub process group (leader + same-group child)'}
        self.step('interrupt_mid_run', f'POST {p}/jobs (C) + stop I2', s8)

        if arm == 'bff':
            def s_down():
                before = (self.db_counts(S), wj.tree_digest(S / 'jobs'))
                response = t.get(f'/jobs/{ids["A"]}')
                after = (self.db_counts(S), wj.tree_digest(S / 'jobs'))
                body = response.json or {}
                return response.status, body.get('code'), {
                    'status_ge_500': response.status >= 500, 'json_code_non_empty': bool(body.get('code')),
                    'store_unchanged': before == after}, {'observed_code': body.get('code'),
                                                          'upstream_status': body.get('upstream_status')}
            self.step('control_api_down', f'GET {p}/jobs/{{A}} (web_api stopped)', s_down)

        # Instance I3: restart with the real dispatcher, new port and new token.
        env3 = self.env(S, R, builder=None)
        t.bind(env3)

        def s9():
            reconciliation = env3.jobs.reconciliation
            again = t.get(f'/jobs/{ids["A"]}')
            before = ids['A_job']
            differing = sorted(k for k in set(again.json or {}) | set(before) if (again.json or {}).get(k) != before.get(k))
            c = t.get(f'/jobs/{ids["C"]}').json or {}
            c_attempt = (c.get('attempts') or [{}])[0]
            old_ok, old_observed = t.old_token_probe(ids['A'], old_tokens)
            return again.status, None, {
                'interrupted_reconciled_1': reconciliation['interrupted'] == 1,
                'token_changed': env3.server.token not in old_tokens,
                'a_projection_equal': again.status == 200 and differing == [],
                'c_interrupted': c.get('state') == 'interrupted', 'c_liveness_dead': c_attempt.get('liveness') == 'dead',
                'c_reason_supervisor_restarted': c_attempt.get('reason_code') == 'supervisor_restarted',
                'old_token_refused': old_ok}, {
                'reconciliation': reconciliation, 'differing_keys': differing,
                'port_changed': env3.server.server_address[1] != env1.server.server_address[1],
                'old_token_probe': old_observed}
        self.step('reconnect_poll', f'GET {p}/jobs/{{A}},{{C}} on I3', s9)

        def s10():
            response = t.post('/jobs', bodies['C'])
            body = response.json or {}
            time.sleep(0.5)
            later = t.get(f'/jobs/{ids["C"]}').json or {}
            entries = sorted(os.listdir(S / 'jobs' / ids['C']))
            return response.status, None, {
                'status_200': response.status == 200, 'replayed': body.get('replayed') is True,
                'same_job': body.get('job_id') == ids['C'], 'still_interrupted': body.get('state') == 'interrupted'
                and later.get('state') == 'interrupted',
                'one_attempt': len(body.get('attempts') or []) == 1 and len(later.get('attempts') or []) == 1,
                'no_new_run': [e for e in entries if not e.startswith('.staging-1-')] == []}, {}
        self.step('replay_interrupted', f'POST {p}/jobs (C replay)', s10)

        def s11():
            response = t.post(f'/jobs/{ids["C"]}/retry', {})
            body = response.json or {}
            job, observed, timed_out = self.poll(t, ids['C'], REAL_POLL_S, 0.25)
            ids['C_job'] = job
            c_dir = S / 'jobs' / ids['C']
            entries = sorted(os.listdir(c_dir))
            aside = S / 'jobs' / (ids['C'] + '-attempt-2-aside')
            os.rename(c_dir / 'attempt-2', aside)
            try:
                attempt1_equal = wj.tree_digest(c_dir) == c_state['digest']
            finally:
                os.rename(aside, c_dir / 'attempt-2')
            a_now = t.get(f'/jobs/{ids["A"]}').json or {}
            download = t.get(f'/artifacts/{ids["A_mp4"]["artifact_id"]}')
            attempts = job['attempts']
            return response.status, job['reason_code'], {
                'retry_202': response.status == 202, 'two_attempts_at_retry': len(body.get('attempts') or []) == 2,
                'not_timed_out': not timed_out, 'succeeded': job['state'] == 'succeeded',
                'attempt_states': [a['state'] for a in attempts] == ['interrupted', 'succeeded'],
                'attempt2_real_worker': attempts[-1]['worker_kind'] == 'tool_api_share_export',
                'artifacts_attempt2_only': {a['attempt'] for a in job['artifacts']} == {2} and len(job['artifacts']) == 3,
                'attempt2_dir_published': 'attempt-2' in entries and 'attempt-1' not in entries,
                'attempt1_staging_byte_identical': attempt1_equal,
                'a_tree_unchanged': wj.tree_digest(S / 'jobs' / ids['A']) == a_digest,
                'a_rows_unchanged': a_now.get('artifacts') == ids['A_job']['artifacts'],
                'a_download_hash_equal': download.status == 200 and sha_bytes(download.payload) == ids['A_mp4']['sha256']}, {
                'observed_state_phase_sequence': observed, 'attempt_worker_kinds': [a['worker_kind'] for a in attempts]}
        self.step('explicit_retry', f'POST {p}/jobs/{{C}}/retry', s11)

        def s12():
            counts = self.db_counts(S)
            publications = self.publications(S)
            expected = sorted([f'{ids["A"]}/attempt-1', f'{ids["C"]}/attempt-2'])
            replays = {name: t.post('/jobs', bodies[name]) for name in ('A', 'B', 'C')}
            same = {name: (r.status, (r.json or {}).get('job_id')) == (200, ids[name]) for name, r in replays.items()}
            return 200, None, {
                'jobs_3': counts['jobs'] == 3, 'attempts_4': counts['attempts'] == 4,
                'artifact_rows_6': counts['artifacts'] == 6, 'publication_dirs_2': self.attempt_dirs(S) == expected,
                'publication_json_2': publications == expected, 'replays_same_ids': all(same.values()),
                'counts_unchanged_after_replays': self.db_counts(S) == counts and self.publications(S) == publications,
                'runs_tree_unchanged': wj.tree_digest(R / 'artifacts' / 'runs') == runs_digest}, {
                'counts': counts, 'publications': len(publications), 'replays_same_job': sum(same.values())}
        self.step('no_duplicate_publish_audit', 'sqlite read-only + replays', s12)

        result['attempt_worker_kinds'] = {
            'A': [a['worker_kind'] for a in ids['A_job']['attempts']],
            'B': ['test_stub'], 'C': [a['worker_kind'] for a in ids['C_job']['attempts']]}
        result['restarts'] = 2
        return t


@unittest.skipUnless(wj.HAVE_FFMPEG, wj.FFMPEG_SKIP)
class WebDemoApiTest(DemoBase):
    ARM = 'api'

    def test_web_demo_end_to_end_api(self):
        self.run_story(lambda env: ApiTransport(self, env))


class WebDemoBffTest(DemoBase):
    ARM = 'bff'

    @classmethod
    def tearDownClass(cls):
        try:
            for app in NODE_APPS:
                with contextlib.suppress(Exception):
                    app.close()
        finally:
            super().tearDownClass()

    def test_web_demo_end_to_end_bff(self):
        def skip(reason):
            METRICS['bff_demo'] = {'arm': 'bff', 'skipped': reason}
            METRICS['skips']['WebDemoBffTest'] = reason
            self.skipTest(reason)
        if not wj.HAVE_FFMPEG:
            skip(wj.FFMPEG_SKIP)
        if shutil.which('node') is None or shutil.which('pnpm') is None:
            skip('node or pnpm not on PATH; BFF arm skipped (not a pass)')
        import test_web_stack as ws  # build helpers and the test-owned node app only
        clock = time.perf_counter()
        try:
            ws._ensure_build(self)
        except unittest.SkipTest as error:
            skip(str(error))
        except BaseException as error:  # a build failure or timeout is a test error, never a skip
            METRICS['bff_demo'] = {'arm': 'bff', 'error': f'install/build failed: {type(error).__name__}',
                                   'install_build_seconds_host': round(time.perf_counter() - clock, 1),
                                   'build_timeout_seconds': ws.BUILD_TIMEOUT_S, 'host_load_at_error': loadavg()}
            raise
        build_s = round(time.perf_counter() - clock, 1)
        try:
            self.run_story(lambda env: BffTransport(self, env, ws))
        finally:
            if METRICS.get('bff_demo'):
                METRICS['bff_demo']['install_build_seconds_host'] = build_s
                METRICS['bff_demo']['key_mapping'] = 'ui-' + 'sha256("bff-" + frozen key)[:32]'


# --------------------------------------------------------------------------- 4 failure injections

class FailureInjectionTests(ReliabilityBase):
    """Section 6 injections. Stub builder, fresh state root per case, API level /api/v1."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.R = cls.base / 'R'
        wj.make_runs_root(cls.R)
        cls.runs_digest = wj.tree_digest(cls.R / 'artifacts' / 'runs')

    @classmethod
    def tearDownClass(cls):
        try:
            if wj.tree_digest(cls.R / 'artifacts' / 'runs') != cls.runs_digest:
                raise AssertionError('artifacts/runs fixture tree changed during the injection class')
            METRICS['runs_tree_unchanged_classes'].append(cls.__name__)
        finally:
            super().tearDownClass()

    # ----------------------------------------------------------------- helpers

    @contextlib.contextmanager
    def execution(self, fi_id, sub_case):
        entry = METRICS['injections'].setdefault(fi_id, {'listed_class': FI[fi_id]['listed_class'],
                                                         'status': FI[fi_id]['status'], 'executions': []})
        record = {'sub_case': sub_case, 'outcome': 'error', 'observed': {}}
        entry['executions'].append(record)
        clock = time.perf_counter()
        try:
            yield record
            record['outcome'] = 'pass'
        except AssertionError:
            record['outcome'] = 'fail'
            raise
        finally:
            record['wall_ms_host'] = round((time.perf_counter() - clock) * 1000, 1)

    def admit(self, client, selector='RUN-A/export/fake.mov'):
        response = client.post('/api/v1/sources', {'selector': selector})
        self.assertIn(response.status, (200, 201), response.json)
        return response.json['source_artifact_id']

    @staticmethod
    def body(source, key, parameters=None):
        body = {'tool': 'share_export', 'source_artifact_id': source, 'idempotency_key': key}
        if parameters is not None:
            body['parameters'] = parameters
        return body

    def submit(self, client, source, key, parameters=None):
        return client.post('/api/v1/jobs', self.body(source, key, parameters))

    def wait_job(self, client, job_id, states, timeout=STUB_POLL_S):
        end = time.monotonic() + timeout
        while True:
            response = client.get(f'/api/v1/jobs/{job_id}')
            self.assertEqual(response.status, 200, response.json)
            if response.json['state'] in states:
                return response.json
            if time.monotonic() > end:
                self.fail(f'job did not reach {states}; last state {response.json["state"]}')
            time.sleep(0.05)

    def kill_own(self, env, pid):
        wj.sigkill_own_group(pid)  # R-N11: a group this test's own WebJobs instance created
        env.kill_detached()

    def digest_without(self, job_dir, attempt_name):
        aside = job_dir.parent / (job_dir.name + f'-{attempt_name}-aside')
        os.rename(job_dir / attempt_name, aside)
        try:
            return wj.tree_digest(job_dir)
        finally:
            os.rename(aside, job_dir / attempt_name)

    # ----------------------------------------------------------------- FI-1

    def test_fi01_expired_lease_adapted(self):
        with self.execution('FI-1', 'a_dead_worker') as record:
            state = self.state('a')
            env1 = self.env(state)
            env1.builder.modes = ['sleep']
            source = self.admit(env1.client)
            job_id = self.submit(env1.client, source, 'fi01-dead-0001').json['job_id']
            self.wait_job(env1.client, job_id, ('running',))
            beat = self.wait_beat(env1.builder, 1)
            env1.stop()
            self.kill_own(env1, beat['pid'])
            env2 = self.env(state)
            job = env2.client.get(f'/api/v1/jobs/{job_id}').json
            self.assertEqual((job['state'], job['attempts'][0]['liveness']), ('interrupted', 'dead'))
            self.assertEqual(env2.client.post(f'/api/v1/jobs/{job_id}/retry', {}).status, 202)
            self.assertEqual(self.wait_job(env2.client, job_id, web_jobs.TERMINAL)['state'], 'succeeded')
            record['observed'] = {'reconciliation': env2.jobs.reconciliation, 'liveness': 'dead'}
            record.update(self.audit(state, [job_id]))
        with self.execution('FI-1', 'b_live_unowned_worker') as record:
            state = self.state('b')
            env1 = self.env(state)
            env1.builder.modes = ['sleep']
            source = self.admit(env1.client)
            job_id = self.submit(env1.client, source, 'fi01-live-0001').json['job_id']
            self.wait_job(env1.client, job_id, ('running',))
            beat = self.wait_beat(env1.builder, 1)
            marker = Path(str(env1.builder.beats[0]) + '.sigterm')
            env1.stop()
            env2 = self.env(state)
            job = env2.client.get(f'/api/v1/jobs/{job_id}').json
            liveness = job['attempts'][0]['liveness']
            self.assertEqual(job['state'], 'interrupted')
            self.assertIn(liveness, ('alive_unowned', 'unknown'))
            refused = env2.client.post(f'/api/v1/jobs/{job_id}/retry', {})
            self.assertEqual((refused.status, refused.code), (409, 'prior_worker_alive'))
            alive = [self.alive(pid) for pid in (beat['pid'], beat['child'])]
            self.assertEqual(alive, [True, True])  # the new instance sent nothing
            self.assertFalse(marker.exists())
            self.kill_own(env1, beat['pid'])
            self.assertEqual(env2.client.post(f'/api/v1/jobs/{job_id}/retry', {}).status, 202)
            self.assertEqual(self.wait_job(env2.client, job_id, web_jobs.TERMINAL)['state'], 'succeeded')
            record['observed'] = {'liveness': liveness, 'signals_sent_by_new_instance': 0,
                                  'retry_refused_code': refused.code}
            record.update(self.audit(state, [job_id]))

    # ----------------------------------------------------------------- FI-2

    def test_fi02_duplicate_delivery(self):
        with self.execution('FI-2', 'a_8_concurrent_identical_posts') as record:
            state = self.state('a')
            env = self.env(state)
            source = self.admit(env.client)
            barrier = threading.Barrier(8)
            responses, errors = [], []

            def post():
                try:
                    barrier.wait(timeout=10)
                    response = self.submit(env.client, source, 'fi02-dup-00001')
                    with _LOCK:
                        responses.append(response)
                except Exception as error:  # recorded and asserted below
                    with _LOCK:
                        errors.append(type(error).__name__)
            threads = [threading.Thread(target=post) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=60)
            self.assertEqual(errors, [])
            statuses = sorted(r.status for r in responses)
            job_ids = {r.json['job_id'] for r in responses}
            self.assertEqual(statuses, [200] * 7 + [202])
            self.assertEqual(len(job_ids), 1)
            self.assertTrue(all(r.json['replayed'] is True for r in responses if r.status == 200))
            job_id = job_ids.pop()
            self.wait_job(env.client, job_id, ('succeeded',))
            audit = self.audit(state, [job_id])
            self.assertEqual((audit['jobs'], audit['attempts'], audit['publications']), (1, 1, 1))
            self.assertEqual(len(env.builder.beats), 1)
            record['observed'] = {'statuses': statuses, 'stub_launches': len(env.builder.beats)}
            record.update(audit)
        with self.execution('FI-2', 'b_second_supervisor_same_state_root') as record:
            with self.assertRaises(WebJobsError) as caught:
                WebJobs(self.R, state, command_builder=wj.StubBuilder(self.base / 'beats-fi02b'))
            self.assertEqual((caught.exception.code, caught.exception.status), ('state_root_locked', 409))
            record['observed'] = {'code': caught.exception.code}
            record.update(self.audit(state, [job_id]))
            self.assertEqual(record['publications'], 1)

    # ----------------------------------------------------------------- FI-3

    def test_fi03_quota_exhaustion_partial(self):
        with self.execution('FI-3', 'a_queue_full') as record:
            state = self.state('a')
            env = self.env(state, queue_limit=4)
            env.builder.modes = ['sleep']
            source = self.admit(env.client)
            running = self.submit(env.client, source, 'fi03-run-0001').json['job_id']
            self.wait_job(env.client, running, ('running',))
            self.wait_beat(env.builder, 1)
            queued = [self.submit(env.client, source, f'fi03-queue-000{n}') for n in range(1, 5)]
            self.assertEqual([r.status for r in queued], [202] * 4)
            before = env.jobs.counts()
            full = self.submit(env.client, source, 'fi03-queue-0005')
            self.assertEqual((full.status, full.code), (429, 'queue_full'))
            self.assertEqual(env.jobs.counts(), before)
            accepted = [running] + [r.json['job_id'] for r in queued]
            for response in queued:
                self.assertEqual(env.client.post(f'/api/v1/jobs/{response.json["job_id"]}/cancel', {}).status, 200)
            self.assertEqual(env.client.post(f'/api/v1/jobs/{running}/cancel', {}).status, 202)
            self.wait_job(env.client, running, ('cancelled',))
            record['observed'] = {'refusal': [full.status, full.code], 'queued_before_refusal': 4}
            record.update(self.audit(state, accepted))
        with self.execution('FI-3', 'b_body_too_large') as record:
            before = (env.jobs.counts(), self.db_counts(state))
            response = env.client.call('POST', '/api/v1/jobs', raw=b'{"a":"' + b'x' * (17 * 1024) + b'"}')
            self.assertEqual((response.status, response.code), (413, 'body_too_large'))
            self.assertEqual((env.jobs.counts(), self.db_counts(state)), before)
            record['observed'] = {'refusal': [response.status, response.code]}
            record.update(self.audit(state, accepted))
        with self.execution('FI-3', 'c_source_too_large') as record:
            small_state = self.state('c')
            small = self.env(small_state, max_source_bytes=1024)
            response = small.client.post('/api/v1/sources', {'selector': 'RUN-A/export/fake.mov'})
            self.assertEqual((response.status, response.code), (422, 'too_large'))
            self.assertEqual(self.db_counts(small_state), {'sources': 0, 'jobs': 0, 'attempts': 0, 'artifacts': 0})
            record['observed'] = {'refusal': [response.status, response.code]}
            record.update(self.audit(small_state, []))
        METRICS['injections']['FI-3']['not_run_sub_cases'] = [dict(s) for s in FI['FI-3']['not_run_sub_cases']]

    # ----------------------------------------------------------------- FI-4

    def test_fi04_access_denial(self):
        with self.execution('FI-4', 'token_host_origin_private_unknown') as record:
            state = self.state()
            env = self.env(state)
            source = self.admit(env.client)
            job_id = self.submit(env.client, source, 'fi04-seed-0001').json['job_id']
            job = self.wait_job(env.client, job_id, ('succeeded',))
            roles = {a['role']: a for a in job['artifacts']}
            before = (env.jobs.counts(), self.db_counts(state), self.publications(state))
            new = self.body(source, 'fi04-denied-01')
            port = env.client.port
            cases = [
                ('GET job, missing token', lambda: env.client.get(f'/api/v1/jobs/{job_id}', token=False), 401, 'token_required'),
                ('GET job, wrong token', lambda: env.client.get(f'/api/v1/jobs/{job_id}', token='x' * 43), 401, 'token_required'),
                ('POST job, missing token', lambda: env.client.post('/api/v1/jobs', new, token=False), 401, 'token_required'),
                ('GET job, bad Host', lambda: env.client.get(f'/api/v1/jobs/{job_id}', host='evil.example'), 403, 'host_refused'),
                ('GET job, Host with another port', lambda: env.client.get(
                    f'/api/v1/jobs/{job_id}', host=f'{LOOPBACK}:{port + 1 if port < 65535 else 1}'), 403, 'host_refused'),
                ('POST job, bad Origin', lambda: env.client.post('/api/v1/jobs', new,
                                                                 headers={'Origin': 'http://evil.example'}), 403, 'origin_refused'),
                ('GET share_receipt', lambda: env.client.get(f'/api/v1/artifacts/{roles["share_receipt"]["artifact_id"]}'),
                 403, 'artifact_private'),
                ('GET unknown artifact', lambda: env.client.get('/api/v1/artifacts/art_' + '0' * 32), 404, 'unknown_artifact'),
            ]
            observed = []
            for label, call, status, code in cases:
                with self.subTest(case=label):
                    response = call()
                    observed.append({'case': label, 'http_status': response.status, 'code': response.code})
                    self.assertEqual((response.status, response.code), (status, code))
            self.assertEqual((env.jobs.counts(), self.db_counts(state), self.publications(state)), before)
            record['observed'] = {'cases': observed, 'store_unchanged': True}
            record.update(self.audit(state, [job_id]))

    # ----------------------------------------------------------------- FI-5

    def test_fi05_hash_mismatch(self):
        with self.execution('FI-5', 'a_source_changed_before_claim') as record:
            runs = self.base / 'R-fi05'
            run = wj.make_runs_root(runs, 'RUN-B')
            state = self.state('a')
            env = self.env(state, runs_root=runs, start=False)
            source = self.admit(env.client, 'RUN-B/export/fake.mov')
            job_id = self.submit(env.client, source, 'fi05-changed-01').json['job_id']
            with open(run / 'export' / 'fake.mov', 'ab') as handle:
                handle.write(b'changed after submit')
            env.jobs.start()
            job = self.wait_job(env.client, job_id, web_jobs.TERMINAL)
            self.assertEqual((job['state'], job['reason_code']), ('failed', 'source_changed'))
            self.assertEqual(env.builder.beats, [])  # no worker launched
            stale = self.submit(env.client, source, 'fi05-changed-02')
            self.assertEqual((stale.status, stale.code), (409, 'source_stale'))
            record['observed'] = {'state': job['state'], 'reason_code': job['reason_code'], 'stub_launches': 0,
                                  'resubmit': [stale.status, stale.code]}
            record.update(self.audit(state, [job_id]))
        with self.execution('FI-5', 'b_published_bytes_changed') as record:
            state = self.state('b')
            env = self.env(state)
            source = self.admit(env.client)
            job_id = self.submit(env.client, source, 'fi05-tamper-01').json['job_id']
            job = self.wait_job(env.client, job_id, ('succeeded',))
            mp4 = next(a for a in job['artifacts'] if a['role'] == 'share_mp4')
            target = f'/api/v1/artifacts/{mp4["artifact_id"]}'
            self.assertEqual(env.client.get(target).status, 200)
            leaf = state / 'jobs' / job_id / 'attempt-1' / 'share.mp4'
            with open(leaf, 'ab') as handle:
                handle.write(b'tamper')
            response = env.client.get(target)
            self.assertEqual((response.status, response.code), (409, 'artifact_stale'))
            record['observed'] = {'refusal': [response.status, response.code]}
            record.update(self.audit(state, [job_id]))
        with self.execution('FI-5', 'c_published_file_deleted') as record:
            leaf.unlink()
            response = env.client.get(target)
            self.assertEqual((response.status, response.code), (410, 'artifact_missing'))
            record['observed'] = {'refusal': [response.status, response.code]}
            record.update(self.audit(state, [job_id]))

    # ----------------------------------------------------------------- FI-6

    def test_fi06_model_absence_not_applicable(self):
        descriptor = tool_api.descriptor('share_export')
        registry = json.loads((ROOT / 'program' / 'models.json').read_text())
        capability = next(c for c in json.loads((ROOT / 'program' / 'capabilities.json').read_text())['capabilities']
                          if c.get('tool') == 'share_export')
        text = json.dumps(descriptor)
        self.assertEqual([model for model in registry['models'] if model in text], [])
        self.assertNotIn('share_export', json.dumps(registry))
        self.assertIs(capability['effects']['model_acquisition'], False)
        self.assertEqual(web_jobs.TOOL, 'share_export')  # the only admitted job type
        METRICS['injections']['FI-6'] = {'listed_class': FI['FI-6']['listed_class'], 'status': 'not_applicable',
                                         'reason': FI['FI-6']['reason'], 'executions': [],
                                         'static_evidence': {'descriptor_names_registered_model': False,
                                                             'capability_model_acquisition': False}}

    # ----------------------------------------------------------------- FI-7

    def test_fi07_output_committed_before_transport_failure(self):
        with self.execution('FI-7', 'client_closes_before_response') as record:
            state = self.state()
            env = self.env(state)
            source = self.admit(env.client)
            body = json.dumps(self.body(source, 'fi07-drop-0001')).encode()
            port = env.client.port
            head = (f'POST /api/v1/jobs HTTP/1.1\r\nHost: {LOOPBACK}:{port}\r\n'
                    f'Authorization: Bearer {env.server.token}\r\nContent-Type: application/json\r\n'
                    f'Content-Length: {len(body)}\r\nConnection: close\r\n\r\n').encode('ascii')
            sock = socket.create_connection((LOOPBACK, port), timeout=10)
            try:
                sock.sendall(head + body)
            finally:
                sock.close()  # complete request sent; response never read
            end = time.monotonic() + 10
            listing = []
            while time.monotonic() < end and not listing:
                listing = env.client.get('/api/v1/jobs').json['jobs']
                time.sleep(0.05)
            self.assertEqual(len(listing), 1, 'the dropped-connection submission was not committed')
            replay = self.submit(env.client, source, 'fi07-drop-0001')
            self.assertEqual((replay.status, replay.json['replayed'], replay.json['job_id'], len(replay.json['attempts'])),
                             (200, True, listing[0]['job_id'], 1))
            job_id = listing[0]['job_id']
            self.wait_job(env.client, job_id, ('succeeded',))
            audit = self.audit(state, [job_id])
            self.assertEqual((audit['jobs'], audit['attempts'], audit['publications']), (1, 1, 1))
            self.assertEqual(env.client.get(f'/api/v1/jobs/{job_id}').status, 200)  # server keeps serving
            record['observed'] = {'replay': [replay.status, replay.json['replayed']], 'server_kept_serving': True}
            record.update(audit)

    # ----------------------------------------------------------------- FI-8

    def test_fi08_crash_around_enqueue(self):
        with self.execution('FI-8', 'queued_then_restart') as record:
            state = self.state()
            env1 = self.env(state, start=False)
            source = self.admit(env1.client)
            submitted = self.submit(env1.client, source, 'fi08-queued-01')
            self.assertEqual((submitted.status, submitted.json['state']), (202, 'queued'))
            job_id = submitted.json['job_id']
            env1.stop()
            env2 = self.env(state, start=False)
            self.assertEqual(env2.client.get(f'/api/v1/jobs/{job_id}').json['state'], 'queued')
            self.assertEqual((env2.jobs.reconciliation['adopted'], env2.jobs.reconciliation['interrupted']), (0, 0))
            env2.jobs.start()
            job = self.wait_job(env2.client, job_id, web_jobs.TERMINAL)
            self.assertEqual((job['state'], len(job['attempts'])), ('succeeded', 1))
            audit = self.audit(state, [job_id])
            self.assertEqual(audit['publications'], 1)
            self.assertEqual(len(env1.builder.beats) + len(env2.builder.beats), 1)
            record['observed'] = {'state_after_restart_before_start': 'queued', 'final_state': job['state']}
            record.update(audit)

    # ----------------------------------------------------------------- FI-9

    def test_fi09_crash_around_claim_adapted(self):
        with self.execution('FI-9', 'stop_after_claim_then_replay_retry') as record:
            state = self.state()
            env1 = self.env(state)
            env1.builder.modes = ['sleep']
            source = self.admit(env1.client)
            job_id = self.submit(env1.client, source, 'fi09-claim-001').json['job_id']
            self.wait_job(env1.client, job_id, ('running',))
            beat = self.wait_beat(env1.builder, 1)
            env1.stop()
            self.kill_own(env1, beat['pid'])
            job_dir = state / 'jobs' / job_id
            before = wj.tree_digest(job_dir)
            env2 = self.env(state)
            job = env2.client.get(f'/api/v1/jobs/{job_id}').json
            self.assertEqual((job['state'], job['attempts'][0]['liveness'], job['attempts'][0]['reason_code']),
                             ('interrupted', 'dead', 'supervisor_restarted'))
            replay = self.submit(env2.client, source, 'fi09-claim-001')
            self.assertEqual((replay.status, replay.json['job_id'], replay.json['state'], len(replay.json['attempts'])),
                             (200, job_id, 'interrupted', 1))
            self.assertEqual(env2.client.post(f'/api/v1/jobs/{job_id}/retry', {}).status, 202)
            done = self.wait_job(env2.client, job_id, web_jobs.TERMINAL)
            self.assertEqual([a['state'] for a in done['attempts']], ['interrupted', 'succeeded'])
            self.assertEqual(self.digest_without(job_dir, 'attempt-2'), before)
            record['observed'] = {'attempt_states': [a['state'] for a in done['attempts']],
                                  'attempt1_staging_byte_identical': True}
            record.update(self.audit(state, [job_id]))

    # ----------------------------------------------------------------- FI-10

    def test_fi10_crash_during_render(self):
        with self.execution('FI-10', 'sigkill_own_stub_group_server_alive') as record:
            state = self.state()
            env = self.env(state)
            env.builder.modes = ['sleep']
            source = self.admit(env.client)
            job_id = self.submit(env.client, source, 'fi10-render-01').json['job_id']
            self.wait_job(env.client, job_id, ('running',))
            beat = self.wait_beat(env.builder, 1)
            connection = self.ro(state)
            try:
                pid, pgid = connection.execute('SELECT pid, pgid FROM attempts WHERE job_id = ? AND attempt = 1',
                                               (job_id,)).fetchone()
            finally:
                connection.close()
            self.assertEqual((pid, pgid), (beat['pid'], beat['pid']))  # owned: leader of its own group
            wj.sigkill_own_group(pgid)
            job = self.wait_job(env.client, job_id, web_jobs.TERMINAL)
            self.assertEqual((job['state'], job['reason_code'], job['artifacts']), ('failed', 'worker_failed', []))
            job_dir = state / 'jobs' / job_id
            before = wj.tree_digest(job_dir)
            self.assertEqual(env.client.post(f'/api/v1/jobs/{job_id}/retry', {}).status, 202)
            done = self.wait_job(env.client, job_id, web_jobs.TERMINAL)
            self.assertEqual((done['state'], [a['state'] for a in done['attempts']]), ('succeeded', ['failed', 'succeeded']))
            self.assertEqual({a['attempt'] for a in done['artifacts']}, {2})
            self.assertEqual(self.digest_without(job_dir, 'attempt-2'), before)
            record['observed'] = {'reason_code': 'worker_failed', 'attempt1_unchanged': True,
                                  'group_gone': [self.wait_gone(beat['pid']), self.wait_gone(beat['child'])]}
            record.update(self.audit(state, [job_id]))

    # ----------------------------------------------------------------- FI-11

    def test_fi11_crash_around_publication(self):
        with self.execution('FI-11', 'after_publish_before_commit') as record:
            state = self.state()
            env1 = self.env(state, fault='after_publish_before_commit')
            source = self.admit(env1.client)
            job_id = self.submit(env1.client, source, 'fi11-crash-001').json['job_id']
            end = time.monotonic() + STUB_POLL_S
            while not env1.jobs.crashed and time.monotonic() < end:
                time.sleep(0.02)
            self.assertTrue(env1.jobs.crashed)
            self.assertEqual(env1.client.get(f'/api/v1/jobs/{job_id}').json['state'], 'running')
            env1.stop()
            env2 = self.env(state)
            self.assertEqual(env2.jobs.reconciliation['adopted'], 1)
            job = env2.client.get(f'/api/v1/jobs/{job_id}').json
            self.assertEqual((job['state'], job['attempts'][0]['reconciled_publication'], len(job['artifacts'])),
                             ('succeeded', True, 3))
            self.assertEqual(sorted(os.listdir(state / 'jobs' / job_id)), ['attempt-1'])
            self.assertEqual(len(env1.builder.beats) + len(env2.builder.beats), 1)
            replay = self.submit(env2.client, source, 'fi11-crash-001')
            self.assertEqual((replay.status, replay.json['job_id'], len(replay.json['attempts'])), (200, job_id, 1))
            record['observed'] = {'reconciliation': env2.jobs.reconciliation, 'stub_launches': 1}
            record.update(self.audit(state, [job_id]))


# --------------------------------------------------------------------------- 5 opt-in real-take web job

VIDEO_PROOF_KEYS = ('comparison_scope', 'packet_count', 'source_packet_count_total', 'output_packet_count_total',
                    'source_presented_packet_count', 'output_presented_packet_count', 'source_decode_only_packets',
                    'output_decode_only_packets', 'maximum_pts_delta_seconds', 'tail_extent_delta_seconds',
                    'tolerance_seconds', 'source_start_seconds', 'source_end_seconds')
SAFE_TOKEN = re.compile(r'[A-Za-z0-9_.:-]{0,128}')


def allowlisted_proof(proof):
    """Path-free allowlisted scalars from the job-private receipt's video_proof."""
    out = {}
    for key in VIDEO_PROOF_KEYS:
        value = (proof or {}).get(key)
        if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
            out[key] = value
        elif isinstance(value, str) and SAFE_TOKEN.fullmatch(value):
            out[key] = value
        else:
            out[key] = None
    return out


@unittest.skipUnless(os.environ.get('WEB_RELIABILITY_REAL') == '1' and wj.HAVE_FFMPEG,
                     'opt-in real-take web job (WEB_RELIABILITY_REAL=1 and qualified FFmpeg); not part of the pass count')
class RealTakeWebJob(ReliabilityBase):
    """One structural delivery check on the accepted FULLER run export through web_api; not an experiment."""

    RUN = '20261006T041633Z-990aa1bd6737'
    SELECTOR = RUN + '/export/cleaned-video.mov'
    EXPECTED_SOURCE_PREFIX = '91b2f436'
    PRIOR_OUTPUT_SHA = '2eba932afe629d06ad45eaaccb8bdddf0e73aff828808a3c5b78f50e690e27db'
    BOUND_S = 1100
    WORKER_TIMEOUT_S = 900

    def test_real_take_web_job(self):
        runs_root = Path(os.environ.get('WEB_RELIABILITY_RUNS_ROOT', str(ROOT.parents[2]))).resolve()
        run_dir = runs_root / 'artifacts' / 'runs' / self.RUN
        self.assertTrue(run_dir.is_dir())
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        state_root = ROOT / 'artifacts' / 'web-jobs' / f's2-web_reliability-real-{stamp}'
        type(self).extra_forbidden += [str(runs_root), str(state_root), self.SELECTOR, 'cleaned-video', '/Users/']
        load_start, facts = loadavg(), host_facts()
        tree_before = wj.tree_digest(run_dir)
        jobs = WebJobs(runs_root, state_root)
        jobs.start()
        server = web_api.WebAPIServer(jobs, 0)
        METRICS['servers_bound'].append(server.server_address[0])
        self.assertEqual(server.server_address[0], LOOPBACK)
        type(self).tokens.append(server.token)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        thread.start()
        receipt = {'receipt': 'web_reliability-real-web-job', 'lane': 'web_reliability', 'sprint': '20261006-s2',
                   'tracker': 'TIN-5616', 'spec': 'docs/spec/sprints/WEB_RELIABILITY_S2.md section 7',
                   'claim_class': 'structural_delivery_check', 'experiment': False, 'run_id': self.RUN,
                   'role': 'accepted FULLER audio run, export video (run-dir export, read-only)',
                   'state_root_relative': f'artifacts/web-jobs/s2-web_reliability-real-{stamp}',
                   'server': {'bind': server.server_address[0], 'uploads': server.allow_uploads, 'daemon': False,
                              'dispatcher': 'default (tool_api share_export worker)'},
                   'host': facts, 'host_load': {'start': load_start}}
        transport = ApiTransport(self, types.SimpleNamespace(server=server))
        outcome = 'not_started'
        try:
            admitted = transport.post('/sources', {'selector': self.SELECTOR})
            self.assertIn(admitted.status, (200, 201), admitted.json)
            source = admitted.json
            receipt['source'] = {k: source[k] for k in ('source_artifact_id', 'source_id', 'source_binding', 'sha256',
                                                        'size_bytes')}
            receipt['source']['sha256_prefix_matches_handoff'] = source['sha256'].startswith(self.EXPECTED_SOURCE_PREFIX)
            body = transport.job_body(source['source_artifact_id'], f'real-{stamp}',
                                      {'timeout_seconds': self.WORKER_TIMEOUT_S})
            clock = time.perf_counter()
            submitted = transport.post('/jobs', body)
            self.assertEqual(submitted.status, 202, submitted.json)
            job_id = submitted.json['job_id']
            job, observed, timed_out = self.poll(transport, job_id, self.BOUND_S, 5)
            wall = time.perf_counter() - clock
            outcome = 'timed_out_waiting' if timed_out else job['state']
            if timed_out:
                cancel = transport.post(f'/jobs/{job_id}/cancel', {})
                receipt['timeout_cancel'] = {'http_status': cancel.status, 'state': (cancel.json or {}).get('state')}
                job, _, _ = self.poll(transport, job_id, 60, 1)
            attempt = job['attempts'][-1]
            checks = attempt['worker_checks'] or {}
            receipt.update({'job_id': job_id, 'state': job['state'], 'outcome': outcome,
                            'reason_code': job['reason_code'], 'parameters': job['parameters'],
                            'capability_revision': job['capability_revision'], 'worker_kind': attempt['worker_kind'],
                            'worker_checks': checks, 'observed_state_phase_sequence': observed,
                            'submit_to_terminal_seconds_host': round(wall, 3), 'bound_seconds': self.BOUND_S,
                            'artifacts': job['artifacts'], 'unknowns_projection': job['unknowns']})
            roles = {a['role']: a for a in job['artifacts']}
            download_ok = ffprobe_frames = None
            proof = {}
            if 'share_mp4' in roles:
                mp4 = roles['share_mp4']
                clock = time.perf_counter()
                response = transport.get(f'/artifacts/{mp4["artifact_id"]}')
                download_s = time.perf_counter() - clock
                body_sha = sha_bytes(response.payload)
                download_ok = (response.status == 200 and body_sha == mp4['sha256']
                               == response.headers.get('x-artifact-sha256'))
                receipt['download'] = {'http_status': response.status, 'bytes': len(response.payload),
                                       'sha256': body_sha, 'header_sha256': response.headers.get('x-artifact-sha256'),
                                       'row_sha256': mp4['sha256'], 'equal': download_ok,
                                       'download_seconds_host': round(download_s, 3)}
                copy = state_root / 'downloaded-share.mp4'
                copy.write_bytes(response.payload)
                probe = subprocess.run([wj.FFPROBE, '-v', 'error', '-select_streams', 'v:0', '-count_frames',
                                        '-show_entries', 'stream=nb_read_frames,nb_frames', '-of', 'json', str(copy)],
                                       capture_output=True, text=True, timeout=300, check=False)
                with contextlib.suppress(ValueError, KeyError, IndexError, TypeError):
                    ffprobe_frames = int(json.loads(probe.stdout)['streams'][0]['nb_read_frames'])
                receipt['ffprobe_count_frames'] = {'decoded_video_frames': ffprobe_frames, 'returncode': probe.returncode,
                                                   'method': 'ffprobe -count_frames nb_read_frames on downloaded bytes'}
                attempt_dir = state_root / 'jobs' / job_id / f'attempt-{attempt["attempt"]}'
                private = attempt_dir / 'share.mp4.receipt.json'
                worker_receipt = json.loads(private.read_text())
                proof = allowlisted_proof(worker_receipt.get('video_proof'))
                receipt['displayed_frames'] = {
                    **proof, 'worker_checks_video_proof_packet_count': (checks.get('video_proof') or {}).get('packet_count'),
                    'read_from': 'job-private share.mp4.receipt.json (403 artifact_private over HTTP), allowlisted keys'}
                receipt['hashes'] = {
                    'source_sha256': source['sha256'], 'download_sha256': body_sha,
                    'receipt_sha256': wj.sha_file(private), 'receipt_bytes': private.stat().st_size,
                    'publication_sha256': wj.sha_file(attempt_dir / 'publication.json'),
                    'publication_bytes': (attempt_dir / 'publication.json').stat().st_size}
                equal = body_sha == self.PRIOR_OUTPUT_SHA
                receipt['output_determinism_vs_prior_run'] = 'observed_equal' if equal else 'observed_not_equal'
                receipt['prior_run_comparison_note'] = ('share_export_fix real-take sha256 2eba932a...; equality is '
                                                        'neither required nor claimed')
            else:
                receipt['output_determinism_vs_prior_run'] = 'not_compared'
            replay = transport.post('/jobs', body)
            counts = self.db_counts(state_root)
            publications = self.publications(state_root)
            receipt['replay'] = {'http_status': replay.status, 'same_job': (replay.json or {}).get('job_id') == job_id,
                                 'replayed': (replay.json or {}).get('replayed'),
                                 'attempts': len((replay.json or {}).get('attempts') or [])}
            receipt['store'] = {'counts': counts, 'publication_dirs': len(publications)}
        finally:
            server.stop()
            thread.join(timeout=10)
            jobs.close()
        tree_after = wj.tree_digest(run_dir)
        receipt['accepted_run_tree'] = {'before_sha256': tree_before[0], 'after_sha256': tree_after[0],
                                        'entries': tree_before[1], 'unchanged': tree_before == tree_after,
                                        'method': 'relative paths + type + size + mtime_ns + sha256'}
        receipt['host_load']['end'] = loadavg()
        criteria = {
            'succeeded_exported_unreviewed': receipt.get('state') == 'succeeded'
            and (receipt.get('worker_checks') or {}).get('status') == 'exported_unreviewed',
            'output_presented_eq_source_presented': proof.get('output_presented_packet_count') is not None
            and proof.get('output_presented_packet_count') == proof.get('source_presented_packet_count'),
            'output_decode_only_zero_and_presented_scope': proof.get('output_decode_only_packets') == 0
            and proof.get('comparison_scope') == 'presented_packets_excluding_edit_list_discard',
            'ffprobe_decoded_eq_output_presented': ffprobe_frames is not None
            and ffprobe_frames == proof.get('output_presented_packet_count'),
            'download_sha_eq_row': bool(download_ok),
            'replay_same_job_one_publication': receipt['replay']['same_job'] and receipt['replay']['attempts'] == 1
            and receipt['store']['publication_dirs'] == 1,
            'accepted_run_tree_unchanged': receipt['accepted_run_tree']['unchanged']}
        receipt['confirmation_criteria'] = criteria
        receipt['confirmation_criteria_met'] = f'{sum(criteria.values())}/{len(criteria)}'
        receipt['share_export_fix_confirmed_on_web_path'] = all(criteria.values())
        receipt['agreement_with_share_export_fix_receipt'] = {
            'fix_receipt': {'source_total': 3631, 'source_presented': 3621, 'source_decode_only': 10},
            'this_run': {'source_total': proof.get('source_packet_count_total'),
                         'source_presented': proof.get('source_presented_packet_count'),
                         'source_decode_only': proof.get('source_decode_only_packets')},
            'note': 'reported as agreement, not a criterion'}
        receipt['unknowns'] = build_unknowns(bff_arm=None, bff_reason='the real-take rerun is API-level only',
                                             determinism=receipt['output_determinism_vs_prior_run'],
                                             host_load=receipt['host_load'])
        receipt['promotion_recommended'] = receipt['share_export_fix_confirmed_on_web_path']
        public = json.dumps(receipt, indent=2, sort_keys=True)
        for needle in self.forbidden() + [str(Path.home())]:
            self.assertNotIn(needle, public)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / 'real-web-job.json').write_text(public + '\n')
        METRICS['real_take'] = {'state': receipt.get('state'), 'outcome': outcome,
                                'criteria_met': receipt['confirmation_criteria_met']}
        self.assertTrue(receipt['accepted_run_tree']['unchanged'])
        self.assertTrue(receipt['replay']['same_job'])
        self.assertIn(receipt.get('state'), ('succeeded', 'failed'))
        if receipt.get('state') == 'succeeded':
            self.assertEqual([k for k, ok in criteria.items() if not ok], [])


# --------------------------------------------------------------------------- module receipt

def tearDownModule():
    for app in NODE_APPS:
        with contextlib.suppress(Exception):
            app.close()
    injections = METRICS['injections']
    executions = [e for entry in injections.values() for e in entry['executions']]
    passed_classes = sorted(fi for fi, entry in injections.items()
                            if entry['executions'] and all(e['outcome'] == 'pass' for e in entry['executions']))
    statuses = {}
    for row in INJECTIONS:
        statuses[row['status']] = statuses.get(row['status'], 0) + 1
    METRICS['injection_summary'] = {
        'classes_listed': len(INJECTIONS), 'status_counts_frozen': statuses,
        'classes_run_all_executions_passed': passed_classes,
        'classes_run_over_listed': f'{len(passed_classes)}/{len(INJECTIONS)}',
        'executions_n': len(executions),
        'executions_passed': sum(e['outcome'] == 'pass' for e in executions),
        'lost_job_records': sum(e.get('lost_job_records', 0) for e in executions),
        'duplicate_publications': sum(e.get('duplicate_publications', 0) for e in executions),
        'not_run': injection_classes_not_run(),
        'note': 'measurement over these executions only; WEB_BACKEND 30-injection SLO row not met or claimed'}
    if METRICS.get('api_demo') is None and not wj.HAVE_FFMPEG:
        METRICS['api_demo'] = {'arm': 'api', 'skipped': wj.FFMPEG_SKIP}
        METRICS['skips']['WebDemoApiTest'] = wj.FFMPEG_SKIP
    api, bff = METRICS.get('api_demo') or {}, METRICS.get('bff_demo') or {}
    differences = []
    if api.get('steps') and bff.get('steps'):
        by_name = {s['name']: s for s in api['steps']}
        for step in bff['steps']:
            other = by_name.get(step['name'])
            if other is None:
                differences.append({'step': step['name'], 'api': None, 'bff': [step.get('http_status'), step.get('code')]})
            elif [other.get('http_status'), other.get('code')] != [step.get('http_status'), step.get('code')]:
                differences.append({'step': step['name'], 'api': [other.get('http_status'), other.get('code')],
                                    'bff': [step.get('http_status'), step.get('code')]})
        METRICS['bff_vs_api_differences'] = differences
    bff_run = 'run' if bff.get('steps') else None
    METRICS['unknowns'] = build_unknowns(bff_arm=bff_run, bff_reason=bff.get('skipped') or bff.get('error')
                                         or 'BFF arm not executed',
                                         host_load={'start': METRICS['host_load_start'], 'end': loadavg()})
    METRICS['loopback_only'] = set(METRICS['servers_bound']) <= {LOOPBACK}
    METRICS['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    target = os.environ.get('WEB_RELIABILITY_METRICS')
    if target:
        Path(target).parent.mkdir(parents=True, exist_ok=True)
        Path(target).write_text(json.dumps(METRICS, indent=2, sort_keys=True, default=str) + '\n')


if __name__ == '__main__':
    unittest.main()
