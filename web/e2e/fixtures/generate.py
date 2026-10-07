#!/usr/bin/env python3
"""Regenerate the Playwright mock control-API fixtures from real /api/v1 responses (WEB_TESTS_S3 5.2).

Synthetic only. The real scripts/web_api.py + scripts/web_runs_api.py serve a temporary runs root built by
the existing test builders (tests/test_web_runs_s3.Fixture, tests/test_web_processing_s3.make_baseline_run),
imported read-only. One share_export job runs the real worker on a 2 s testsrc2 + 32.70 Hz sine clip (the
annotation clock needs a measured video extent); denoise / capture_profile / apply_capture_profile run the
test stub worker under the test admission seam. Nothing here reads a recording, and no response supports a
listening, low-register or musical claim.

Every id, hash and timestamp is rewritten to a counter value so committed fixtures are low entropy and
stable. Numbers measured by the FFmpeg worker (sizes, loudness) are kept as served and may differ between
FFmpeg builds; `shape()` is the comparison tests/test_web_house_stack_s3.FixtureDrift gates on.

Run from the repository root with the qualified FFMPEG/FFPROBE environment:
    python3 web/e2e/fixtures/generate.py            # rewrite web/e2e/fixtures/control-api/
    python3 web/e2e/fixtures/generate.py --out DIR  # write elsewhere (drift check)
Exit 75 with a JSON line {"code": "fixture_generation_unavailable"} when a dependency is missing.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / 'control-api'
UNAVAILABLE_EXIT = 75
JOB_WAIT_S = 180
RUNNING_WAIT_S = 30
STUB_RUN_SPACING_S = 1.1
UPSTREAM_MARKER = 'UPSTREAM_TEXT_MARKER_e2e'
UPSTREAM_KEY = 'upstream_unexpected_field_e2e'
BAD_JOB_ID = 'job_' + 'f' * 31 + '1'
HOST_MARKERS = ('/' + 'Users/', '/' + 'private/', '/' + 'tmp/', '/' + 'nix/store/', '/' + 'Volumes/', '/' + 'home/')


def unavailable(reason):
    print(json.dumps({'status': 'skipped', 'code': 'fixture_generation_unavailable', 'reason': reason}))
    return UNAVAILABLE_EXIT


class _NoLeakCheck:
    def assert_no_leak(self, response):
        pass


class HybridBuilder:
    """Test seam argv: the real share_export worker, or a stub mode popped per share launch; S3 stub otherwise."""

    def __init__(self, beats_dir, proc, wj, web_jobs):
        self.beats_dir = Path(beats_dir)
        self.beats_dir.mkdir(parents=True, exist_ok=True)
        self.share_modes = []
        self.beats = []
        self.lock = threading.Lock()
        self.proc, self.wj, self.web_jobs = proc, wj, web_jobs

    def __call__(self, args):
        with self.lock:
            beat = self.beats_dir / f'beat-{len(self.beats)}.json'
            self.beats.append(beat)
            share = '_web_job' not in args
            mode = (self.share_modes.pop(0) if self.share_modes else 'real') if share else 'succeed'
        if not share:
            return [sys.executable, '-c', self.proc.S3_STUB, mode, str(beat), json.dumps(args)]
        if mode == 'real':
            return self.web_jobs.WebJobs.real_command('share_export', dict(args))
        return [sys.executable, '-c', self.wj.STUB, mode, str(beat), args['source'], args['output']]


# --------------------------------------------------------------------------- normalisation

ID_RE = re.compile(r'\b(job|art|src|rev|evd)_([0-9a-f]{32})\b')
UPLOAD_RE = re.compile(r'\bupl_[0-9a-f]{16}\b')
SHA_RE = re.compile(r'(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])')
UUID_RE = re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b')
STAMP_RUN_RE = re.compile(r'\b\d{8}T\d{6}Z-[0-9a-f]{12}\b')
TIME_RE = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|\+00:00)')
EPOCH = datetime.datetime(2026, 10, 7, 12, 0, 0, tzinfo=datetime.timezone.utc)


class Normaliser:
    """Deterministic counter values in first-seen order over the documents in a fixed order."""

    def __init__(self, keep=()):
        self.maps = {'id': {}, 'sha': {}, 'uuid': {}, 'run': {}, 'upl': {}}
        self.counts = {}
        self.keep = set(keep)
        self.times = {}

    def _next(self, kind):
        self.counts[kind] = self.counts.get(kind, 0) + 1
        return self.counts[kind]

    def _id(self, match):
        whole = match.group(0)
        if whole in self.keep:
            return whole
        table = self.maps['id']
        if whole not in table:
            prefix = match.group(1)
            table[whole] = f'{prefix}_{self._next(prefix):032x}'
        return table[whole]

    def _simple(self, kind, render):
        def replace(match):
            whole = match.group(0)
            table = self.maps[kind]
            if whole not in table:
                table[whole] = render(self._next(kind))
            return table[whole]
        return replace

    def collect_times(self, text):
        for value in TIME_RE.findall(text):
            self.times.setdefault(value, None)

    def finish_times(self):
        def instant(value):
            body = value[:-1] if value.endswith('Z') else value[:-6]
            seconds, _, fraction = body.partition('.')
            parsed = datetime.datetime.strptime(seconds, '%Y-%m-%dT%H:%M:%S')
            return parsed, (fraction or '').ljust(9, '0')
        ordered = sorted({instant(value) for value in self.times})
        index = {key: number for number, key in enumerate(ordered)}
        for value in self.times:
            stamp = (EPOCH + datetime.timedelta(seconds=index[instant(value)])).strftime('%Y-%m-%dT%H:%M:%S')
            self.times[value] = stamp + ('Z' if value.endswith('Z') else '+00:00')

    def apply(self, text):
        text = STAMP_RUN_RE.sub(self._simple('run', lambda n: f'RUN-STUB-{n:02d}'), text)
        text = ID_RE.sub(self._id, text)
        text = UPLOAD_RE.sub(self._simple('upl', lambda n: f'upl_{n:016x}'), text)
        text = SHA_RE.sub(self._simple('sha', lambda n: f'{n:064x}'), text)
        text = UUID_RE.sub(self._simple('uuid', lambda n: f'00000000-0000-0000-0000-{n:012x}'), text)
        return TIME_RE.sub(lambda match: self.times[match.group(0)], text)


def shape(value):
    """Keys and JSON types only (numbers, strings and list lengths excluded): the drift comparison basis."""
    if isinstance(value, dict):
        return {key: shape(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        seen = []
        for item in value:
            item_shape = shape(item)
            if item_shape not in seen:
                seen.append(item_shape)
        return ['list', sorted(seen, key=lambda item: json.dumps(item, sort_keys=True))]
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'boolean'
    if isinstance(value, (int, float)):
        return 'number'
    return 'string'


# --------------------------------------------------------------------------- capture

class Recorder:
    def __init__(self, client):
        self.client = client
        self.documents = []  # (file, method, path, status, json)

    def get(self, file, path):
        response = self.client.get(path)
        if response.json is None:
            raise SystemExit(f'{path}: no JSON body (HTTP {response.status})')
        self.documents.append((file, 'GET', path, response.status, response.json))
        return response

    def add(self, file, method, path, status, body):
        self.documents.append((file, method, path, status, body))


def wait_job(client, job_id, states, timeout=JOB_WAIT_S):
    end = time.monotonic() + timeout
    while True:
        body = client.get(f'/api/v1/jobs/{job_id}').json
        if body['state'] in states:
            return body
        if time.monotonic() > end:
            raise SystemExit(f'job {body.get("tool")} did not reach {states}; last {body["state"]} {body.get("reason_code")}')
        time.sleep(0.05)


def submit(client, body, expect=(200, 201, 202)):
    response = client.post('/api/v1/jobs', body)
    if response.status not in expect:
        raise SystemExit(f'submit {body.get("tool")}: HTTP {response.status} {response.json}')
    return response


def generate(out_dir):
    sys.path.insert(0, str(ROOT / 'scripts'))
    sys.path.insert(0, str(ROOT / 'tests'))
    try:
        import test_web_jobs as wj
        import test_web_processing_s3 as proc
        import test_web_runs_s3 as runs
        import web_api
        import web_jobs
    except Exception as error:  # a generator dependency is missing on this host
        return unavailable(f'import failed: {type(error).__name__}')
    if not wj.HAVE_FFMPEG:
        return unavailable('qualified FFMPEG/FFPROBE environment is unset')

    with tempfile.TemporaryDirectory(prefix='web-e2e-fixtures-') as tmp:
        base = Path(tmp).resolve()
        fx = runs.Fixture(base, clip=True)
        builder = HybridBuilder(base / 'beats', proc, wj, web_jobs)
        jobs = web_jobs.WebJobs(fx.R, base / 'state', command_builder=builder, queue_limit=8,
                                admitted_tools=frozenset(web_jobs.JOB_TYPE_NAMES))
        jobs.start()
        server = web_api.WebAPIServer(jobs, 0)
        server.runs_api = fx.api()
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        thread.start()
        client = wj.Client(_NoLeakCheck(), server)
        rec = Recorder(client)
        ids = {}
        try:
            # --- reviewed source: the run's own 2 s clip, one real share_export, one operator note
            clip = fx.run_dir / 'export' / 'clip.mov'
            reviewed = client.post('/api/v1/sources', {'selector': f'{runs.RUN}/export/clip.mov'}).json
            src_a, sha_a = reviewed['source_artifact_id'], reviewed['sha256']
            share = submit(client, {'tool': 'share_export', 'source_artifact_id': src_a,
                                    'idempotency_key': 'fixture-00000001',
                                    'parameters': {'height': 240, 'crf': 30, 'audio_kbps': 96, 'codec': 'h264',
                                                   'timeout_seconds': 120}}).json
            wait_job(client, share['job_id'], ('succeeded',))
            store = client.get(f'/api/v1/sources/{src_a}/annotations').json
            note = client.post(f'/api/v1/sources/{src_a}/annotations', {
                'schema_version': 2, 'expected_revision': store['store']['revision'],
                'idempotency_key': 'fixture-00000002', 'source_sha256': store['store']['source_sha256'],
                'manifest_sha256': store['store']['manifest_sha256'],
                'annotation': {'kind': 'tone', 'basis': 'operator_assertion', 'status': 'needs_review',
                               'source_span': {'start_seconds': 0.5, 'end_seconds': 0.5, 'extent_known': False},
                               'reported_by': {'actor': 'operator', 'via': 'browser'}, 'operator_certainty': 'uncertain',
                               'operator_quote': 'synthetic fixture quote', 'note': 'synthetic fixture note (no recording was heard)'}})
            if note.status != 200:
                raise SystemExit(f'annotation write: HTTP {note.status} {note.json}')
            proc.make_baseline_run(fx.runs, 'BASE-REVIEWED', clip, sha_a)
            review = client.post(f'/api/v1/sources/{src_a}/capture-reviews',
                                 proc.review_body('BASE-REVIEWED', sha_a, key='fixture-00000003'))
            if review.status != 201:
                raise SystemExit(f'review: HTTP {review.status} {review.json}')
            denoise = submit(client, {'tool': 'denoise', 'source_artifact_id': src_a,
                                      'idempotency_key': 'fixture-00000004',
                                      'parameters': {'profile': 'bypass', 'timeout_seconds': 30}}).json
            wait_job(client, denoise['job_id'], ('succeeded',))
            author = submit(client, {'tool': 'capture_profile', 'source_artifact_id': src_a,
                                     'idempotency_key': 'fixture-00000005', 'parameters': {'preset': 'fuller'},
                                     'capture_review_id': review.json['review_id']}).json
            wait_job(client, author['job_id'], ('succeeded',))
            # The stub names its runs <UTC second>-<random hex> and the API lists runs by id: keep the two stub runs in
            # different seconds so the recorded list order does not depend on the random suffix.
            time.sleep(STUB_RUN_SPACING_S)
            applied = submit(client, {'tool': 'apply_capture_profile', 'source_artifact_id': src_a,
                                      'idempotency_key': 'fixture-00000006',
                                      'parameters': {'timeout_seconds': 30},
                                      'capture_profile_job_id': author['job_id']}).json
            wait_job(client, applied['job_id'], ('succeeded',))
            stub_runs = {}
            for label, job in (('DENOISE', denoise), ('AUTHORING', author), ('APPLY', applied)):
                projection = client.get(f'/api/v1/jobs/{job["job_id"]}').json
                for key in ('run_id', 'authoring_id'):
                    value = projection.get(key)
                    if isinstance(value, str) and STAMP_RUN_RE.fullmatch(value):
                        stub_runs.setdefault(value, f'RUN-STUB-{label}')

            # --- plain source: admitted bytes only (no job, no review), with a baseline run for the capture page
            plain_path = fx.runs / 'RUN-PLAIN' / 'export' / 'take.mov'
            plain_path.parent.mkdir(parents=True)
            plain_path.write_bytes(wj.FAKE_MOV + b'plain')
            plain = client.post('/api/v1/sources', {'selector': 'RUN-PLAIN/export/take.mov'}).json
            src_b, sha_b = plain['source_artifact_id'], plain['sha256']
            proc.make_baseline_run(fx.runs, 'BASE-PLAIN', plain_path, sha_b)

            # --- job states: failed, then running + queued (captured while they are in that state)
            builder.share_modes = ['reject', 'sleep']
            failed = submit(client, {'tool': 'share_export', 'source_artifact_id': src_a,
                                     'idempotency_key': 'fixture-00000007'}).json
            wait_job(client, failed['job_id'], ('failed',))
            running = submit(client, {'tool': 'share_export', 'source_artifact_id': src_a,
                                      'idempotency_key': 'fixture-00000008', 'parameters': {'crf': 30}}).json
            end = time.monotonic() + RUNNING_WAIT_S
            while client.get(f'/api/v1/jobs/{running["job_id"]}').json['phase'] != 'worker_started':
                if time.monotonic() > end:
                    raise SystemExit('running fixture job never reached worker_started')
                time.sleep(0.05)
            queued = submit(client, {'tool': 'share_export', 'source_artifact_id': src_a,
                                     'idempotency_key': 'fixture-00000009'}).json

            # --- snapshot every read route the BFF uses
            rec.get('sources.json', '/api/v1/sources?limit=500')
            all_jobs = rec.get('jobs_all.json', '/api/v1/jobs?limit=200').json
            rec.get('job_types.json', '/api/v1/job-types')
            for alias, source in (('reviewed', src_a), ('plain', src_b)):
                rec.get(f'jobs_{alias}.json', f'/api/v1/jobs?source_artifact_id={source}&limit=200')
                rec.get(f'annotations_{alias}.json', f'/api/v1/sources/{source}/annotations')
                rec.get(f'source_runs_{alias}.json', f'/api/v1/sources/{source}/runs')
                rec.get(f'reviews_{alias}.json', f'/api/v1/sources/{source}/capture-reviews')
            names = {share['job_id']: 'share_succeeded', failed['job_id']: 'share_failed',
                     running['job_id']: 'share_running', queued['job_id']: 'share_queued',
                     denoise['job_id']: 'denoise_succeeded', author['job_id']: 'capture_profile_succeeded',
                     applied['job_id']: 'apply_succeeded'}
            for row in all_jobs['jobs']:
                rec.get(f'job_{names[row["job_id"]]}.json', f'/api/v1/jobs/{row["job_id"]}')
            run_list = rec.get('runs_list.json', '/api/v1/runs?limit=500').json
            for row in run_list['runs']:
                name = stub_runs.get(row['run_id'], row['run_id'])
                if STAMP_RUN_RE.fullmatch(name):
                    raise SystemExit('a stub run is listed that no fixture job created')
                slug = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
                rec.get(f'run_{slug}.json', f'/api/v1/runs/{row["run_id"]}')
                rec.get(f'layers_{slug}.json', f'/api/v1/runs/{row["run_id"]}/layers')
            rec.get('capabilities.json', '/api/v1/capabilities')

            # --- closed-schema violation derived from the running projection (synthetic edge)
            running_now = client.get(f'/api/v1/jobs/{running["job_id"]}').json
            bad = json.loads(json.dumps(running_now).replace(running['job_id'], BAD_JOB_ID))
            bad[UPSTREAM_KEY] = f'{UPSTREAM_MARKER} must never be rendered'
            rec.add('job_bad_unknown_key.json', 'GET', f'/api/v1/jobs/{BAD_JOB_ID}', 200, bad)

            # --- recorded write responses (taken after the snapshot; replayed by the mock, never re-evaluated)
            upload = client.call('POST', '/api/v1/uploads', raw=wj.FAKE_MOV, content_type='video/mp4')
            rec.add('upload_refused.json', 'POST', '/api/v1/uploads', upload.status, upload.json)
            refused_job = client.post('/api/v1/jobs', {'tool': 'capture_profile', 'source_artifact_id': src_b,
                                                       'idempotency_key': 'fixture-00000010',
                                                       'parameters': {'preset': 'fuller'}})
            rec.add('submit_refused.json', 'POST', '/api/v1/jobs', refused_job.status, refused_job.json)
            measured = client.post(f'/api/v1/sources/{src_b}/capture-measurements',
                                   {'run_id': 'BASE-PLAIN', 'start_seconds': 5.5, 'end_seconds': 6.4})
            rec.add('measurement.json', 'POST', f'/api/v1/sources/{src_b}/capture-measurements', measured.status, measured.json)
            setup = dict(start=1.0, end=2.0, review_status='reviewed_possible_contamination',
                         authorization_scope='profile_authoring')
            unack = client.post(f'/api/v1/sources/{src_b}/capture-reviews',
                                proc.review_body('BASE-PLAIN', sha_b, key='fixture-00000011', **setup))
            rec.add('review_refused_setup.json', 'POST', f'/api/v1/sources/{src_b}/capture-reviews#unacknowledged',
                    unack.status, unack.json)
            acked = client.post(f'/api/v1/sources/{src_b}/capture-reviews',
                                proc.review_body('BASE-PLAIN', sha_b, key='fixture-00000012',
                                                 setup_interval_acknowledged=True, **setup))
            rec.add('review_saved_acknowledged.json', 'POST', f'/api/v1/sources/{src_b}/capture-reviews#acknowledged',
                    acked.status, acked.json)
            expected = {'upload_refused.json': 403, 'submit_refused.json': 409, 'measurement.json': 200,
                        'review_refused_setup.json': 422, 'review_saved_acknowledged.json': 201}
            for file, _method, _path, status, _body in rec.documents:
                if file in expected and status != expected[file]:
                    raise SystemExit(f'{file}: expected HTTP {expected[file]}, served {status}')

            ids = {'source_reviewed': src_a, 'source_plain': src_b, 'run_main': runs.RUN, 'run_other': runs.OTHER,
                   'baseline_reviewed': 'BASE-REVIEWED', 'baseline_plain': 'BASE-PLAIN',
                   'review_reviewed': review.json['review_id'],
                   'jobs': {name: job_id for job_id, name in names.items()} | {'bad_unknown_key': BAD_JOB_ID}}
            client.post(f'/api/v1/jobs/{running["job_id"]}/cancel', {})
            client.post(f'/api/v1/jobs/{queued["job_id"]}/cancel', {})
            wait_job(client, running['job_id'], ('cancelled',), timeout=60)
            wait_job(client, queued['job_id'], ('cancelled', 'succeeded', 'failed'), timeout=JOB_WAIT_S)
            token = server.token
        finally:
            server.stop()
            thread.join(timeout=10)
            jobs.close()
            for process in jobs._detached:
                if process.poll() is None:
                    wj.sigkill_own_group(process.pid)
                process.wait(timeout=10)

        # --- product-default admission catalogue (no seam): what a real server reports at this commit
        default_jobs = web_jobs.WebJobs(fx.R, base / 'state-default')
        try:
            status, catalogue = default_jobs.job_types()
        finally:
            default_jobs.close()
        rec.add('job_types_product_default.json', 'GET', '/api/v1/job-types#product_default', status, catalogue)
        forbidden = [str(base), os.path.realpath(tmp), str(ROOT), token, *HOST_MARKERS]

    # --- normalise, check and write
    normaliser = Normaliser(keep={BAD_JOB_ID})
    normaliser.maps['run'].update(stub_runs)
    rec.documents.sort(key=lambda item: item[0])
    raw = [(file, method, path, status, json.dumps(body, sort_keys=True)) for file, method, path, status, body in rec.documents]
    ids_text = json.dumps(ids, sort_keys=True)
    for _file, _method, path, _status, text in raw:
        normaliser.collect_times(text)
    normaliser.finish_times()
    routes, written = [], {}
    for file, method, path, status, text in raw:
        for needle in forbidden:
            if needle in text:
                raise SystemExit(f'{file}: a host path or the server token would be committed')
        written[file] = json.loads(normaliser.apply(text))
        variant = None
        if '#' in path:
            path, variant = path.split('#', 1)
        path = re.sub(r'([?&])limit=\d+', r'\1', normaliser.apply(path)).rstrip('?&').replace('?&', '?')
        routes.append({'method': method, 'path': path, 'variant': variant, 'status': status, 'file': file})
    written['ids.json'] = json.loads(normaliser.apply(ids_text))
    written['routes.json'] = {'schema_version': 1, 'claim_class': 'synthetic_fixture',
                              'note': 'method + path (limit removed) -> recorded response; variant rows are chosen by the mock',
                              'routes': sorted(routes, key=lambda row: (row['path'], row['method'], row['variant'] or ''))}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob('*.json'):
        stale.unlink()
    for file, value in sorted(written.items()):
        (out_dir / file).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    tool_names = [tool['name'] for tool in written['capabilities.json']['tools']]
    print(json.dumps({'status': 'written', 'files': len(written), 'routes': len(routes),
                      'tool_count': written['capabilities.json']['tool_count'], 'tools_listed': len(tool_names),
                      'real_ffmpeg_share_export': True, 'processing_worker': 'test_stub (admission seam)',
                      'rewritten': {kind: len(table) for kind, table in normaliser.maps.items()},
                      'timestamps_rewritten': len(normaliser.times)}))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', default=str(DEFAULT_OUT), help='output directory (default: the committed fixture set)')
    args = parser.parse_args(argv)
    return generate(args.out)


if __name__ == '__main__':
    sys.exit(main())
