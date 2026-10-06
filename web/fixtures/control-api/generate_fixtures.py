#!/usr/bin/env python3
"""Regenerate the mock control-API fixtures from real scripts/web_api.py /api/v1 responses.

Synthetic only: a temporary runs root with a 2 s testsrc2 + 32.70 Hz sine clip (when the qualified
FFMPEG/FFPROBE env is set) and the web_jobs stub worker. Job IDs are rewritten to fixed synthetic
values that tests/test_web_stack.py addresses; everything else is the projection as served.
Run from the repository root:  python3 web/fixtures/control-api/generate_fixtures.py
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))

import test_web_jobs as wj  # noqa: E402  (synthetic fixtures + stub worker)
import web_api  # noqa: E402
from web_jobs import WebJobs  # noqa: E402

OUT = Path(__file__).resolve().parent
JOB_IDS = {name: 'job_' + '0' * 31 + digit for name, digit in (
    ('queued', '1'), ('running', '2'), ('succeeded', '3'), ('failed', '4'),
    ('bad_unknown_key', '5'), ('bad_enum', '6'))}
MARKER = 'UPSTREAM_TEXT_MARKER_7f3a'


class _Test:
    def assert_no_leak(self, response):
        pass


def serve(runs_root, state_root, builder):
    jobs = WebJobs(runs_root, state_root, command_builder=builder, queue_limit=8)
    jobs.start()
    server = web_api.WebAPIServer(jobs, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
    thread.start()
    return jobs, server, wj.Client(_Test(), server)


def wait(client, job_id, states, timeout=300):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        body = client.get(f'/api/v1/jobs/{job_id}').json
        if body['state'] in states:
            return body
        time.sleep(0.05)
    raise SystemExit(f'job did not reach {states}')


def rename(body, name):
    text = json.dumps(body).replace(body['job_id'], JOB_IDS[name])
    return json.loads(text)


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def main():
    with tempfile.TemporaryDirectory(prefix='web-ui-fixtures-') as tmp:
        base = Path(tmp).resolve()
        run = wj.make_runs_root(base / 'R')
        selector = 'RUN-A/export/fake.mov'
        builder = None
        if wj.HAVE_FFMPEG:
            wj.make_clip(run / 'export' / 'clip.mov')
            selector = 'RUN-A/export/clip.mov'
        else:
            builder = wj.StubBuilder(base / 'beats-real')
        jobs, server, client = serve(base / 'R', base / 'state', builder)
        try:
            source = client.post('/api/v1/sources', {'selector': selector}).json['source_artifact_id']
            job = client.post('/api/v1/jobs', {'tool': 'share_export', 'source_artifact_id': source,
                                               'idempotency_key': 'fixture-succeeded-000000'}).json['job_id']
            succeeded = rename(wait(client, job, ('succeeded',)), 'succeeded')
            unbound_dir = base / 'R' / 'artifacts' / 'runs' / 'RUN-B' / 'export'
            unbound_dir.mkdir(parents=True)
            (unbound_dir / 'take.mov').write_bytes(wj.FAKE_MOV + b'unbound')
            client.post('/api/v1/sources', {'selector': 'RUN-B/export/take.mov'})
            sources = client.get('/api/v1/sources').json
        finally:
            server.stop()
            jobs.close()
        stub = wj.StubBuilder(base / 'beats', modes=['reject', 'sleep'])
        jobs, server, client = serve(base / 'R', base / 'state-stub', stub)
        try:
            source = client.post('/api/v1/sources', {'selector': 'RUN-A/export/fake.mov'}).json['source_artifact_id']
            failed_id = client.post('/api/v1/jobs', {'tool': 'share_export', 'source_artifact_id': source,
                                                     'idempotency_key': 'fixture-failed-000000'}).json['job_id']
            failed = rename(wait(client, failed_id, ('failed',)), 'failed')
            running_id = client.post('/api/v1/jobs', {'tool': 'share_export', 'source_artifact_id': source,
                                                      'idempotency_key': 'fixture-running-000000',
                                                      'parameters': {'crf': 30}}).json['job_id']
            end = time.monotonic() + 30
            while True:
                running = client.get(f'/api/v1/jobs/{running_id}').json
                if running['phase'] == 'worker_started' or time.monotonic() > end:
                    break
                time.sleep(0.05)
            running = rename(running, 'running')
            queued = rename(client.post('/api/v1/jobs', {'tool': 'share_export', 'source_artifact_id': source,
                                                         'idempotency_key': 'fixture-queued-000000'}).json, 'queued')
            client.post(f'/api/v1/jobs/{running_id}/cancel', {})
            wait(client, running_id, ('cancelled',), timeout=60)
        finally:
            server.stop()
            jobs.close()
            wj.Env.kill_detached(type('E', (), {'jobs': jobs})())
    queued.pop('replayed', None)
    # Synthetic edge: no event row yet, so phase and lifecycle progress are null (schema-legal).
    queued.update(phase=None, progress=None)
    write('sources.json', sources)
    write('job_queued.json', queued)
    write('job_running.json', running)
    write('job_succeeded.json', succeeded)
    write('job_failed.json', failed)
    bad_key = dict(running, job_id=JOB_IDS['bad_unknown_key'], upstream_unexpected_field_ZQX=f'{MARKER} must never be echoed')
    write('job_bad_unknown_key.json', bad_key)
    write('job_bad_enum.json', dict(running, job_id=JOB_IDS['bad_enum'], state=f'{MARKER}_state'))
    print(json.dumps({'written': 7, 'real_ffmpeg_succeeded_job': wj.HAVE_FFMPEG}))


if __name__ == '__main__':
    main()
