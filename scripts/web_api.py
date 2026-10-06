#!/usr/bin/env python3
"""Loopback control API for the bounded local job service (stdlib http.server only).

Routes (contract ``docs/spec/sprints/WEB_JOBS_S2.md`` section 4.4)::

    POST /sources                 admit an existing file under artifacts/runs by selector
    POST /jobs                    submit share_export over a source artifact id (idempotent)
    GET  /jobs/{job_id}           closed job projection
    POST /jobs/{job_id}/cancel    cancel (queued -> cancelled, running -> cancel_requested)
    POST /jobs/{job_id}/retry     explicit retry of interrupted/failed jobs (attempt n+1)
    GET  /artifacts/{artifact_id} published job output bytes, re-hashed before sending

The server binds 127.0.0.1 only, checks Host/Origin, and requires a per-start
bearer token compared in constant time. It runs only as a foreground process
started by the operator (``serve``); Ctrl-C stops it. Stopping the server is not
a cancel: running attempts are reconciled on the next start. A FastAPI app may
later mount the same routes on the same ``WebJobs`` object (section 4.6); the
HTTP tests are the conformance suite for that swap.
"""
from __future__ import annotations

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import signal
import sys
import threading
from urllib.parse import urlsplit

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import web_jobs  # noqa: E402
from web_jobs import WebJobs, WebJobsError  # noqa: E402

BIND_ADDRESS = '127.0.0.1'
MAX_BODY = 16 * 1024
MAX_DRAIN = 1024 * 1024
MAX_HANDLERS = 16
SOCKET_TIMEOUT_S = 10
STREAM_CHUNK = 1024 * 1024
SEGMENT = r'([^/]{1,128})'
ROUTES = (
    (re.compile(r'/sources'), 'sources'),
    (re.compile(r'/jobs'), 'jobs'),
    (re.compile(rf'/jobs/{SEGMENT}'), 'job'),
    (re.compile(rf'/jobs/{SEGMENT}/cancel'), 'cancel'),
    (re.compile(rf'/jobs/{SEGMENT}/retry'), 'retry'),
    (re.compile(rf'/artifacts/{SEGMENT}'), 'artifact'),
)
METHODS = {'sources': 'POST', 'jobs': 'POST', 'job': 'GET', 'cancel': 'POST', 'retry': 'POST', 'artifact': 'GET'}


class WebAPIServer(ThreadingHTTPServer):
    """Loopback-only server; one ``WebJobs`` store; bounded handler threads."""

    daemon_threads = True
    request_queue_size = 8
    allow_reuse_address = False

    def __init__(self, jobs, port=0, token=None):
        if not isinstance(port, int) or isinstance(port, bool) or not 0 <= port <= 65535:
            raise ValueError('port must be an integer in 0..65535')
        self.jobs = jobs
        self.token = token or secrets.token_urlsafe(32)
        self.shutting_down = False
        self.handlers = threading.BoundedSemaphore(MAX_HANDLERS)
        super().__init__((BIND_ADDRESS, port), Handler)

    @property
    def hosts(self):
        port = self.server_address[1]
        return {f'127.0.0.1:{port}', f'localhost:{port}'}

    def process_request(self, request, client_address):
        if not self.handlers.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.handlers.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.handlers.release()

    def stop(self):
        """Stop serving (no cancel). The caller closes the ``WebJobs`` store."""
        self.shutting_down = True
        self.shutdown()
        self.server_close()


class Handler(BaseHTTPRequestHandler):
    server_version = 'VideoUtilsWebJobs/1'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(SOCKET_TIMEOUT_S)

    def log_message(self, *_args):
        pass

    # ----------------------------------------------------------------- responses

    def _headers(self, status, content_type, length, extra=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(length))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def _json(self, status, value):
        body = json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True).encode('ascii')
        self._headers(status, 'application/json', len(body))
        if self.command != 'HEAD':
            self.wfile.write(body)

    # ----------------------------------------------------------------- checks

    def _trusted(self):
        hosts = self.server.hosts
        if self.headers.get('Host') not in hosts:
            raise WebJobsError('host_refused', 403, 'unexpected Host header')
        origin = self.headers.get('Origin')
        if origin is not None and origin not in {f'http://{host}' for host in hosts}:
            raise WebJobsError('origin_refused', 403, 'unexpected Origin header')
        supplied = self.headers.get('Authorization', '')
        scheme, _, token = supplied.partition(' ')
        if (scheme != 'Bearer' or not token.isascii()
                or not hmac.compare_digest(token.encode('ascii'), self.server.token.encode('ascii'))):
            raise WebJobsError('token_required', 401, 'bearer token required')

    def _drain(self):
        """Read and discard a bounded unread body so an early refusal is not lost to a TCP reset."""
        if self._consumed or self.headers.get('Transfer-Encoding'):
            return
        self._consumed = True
        text = self.headers.get('Content-Length', '')
        if text.isdigit() and 0 < int(text) <= MAX_DRAIN:
            remaining = int(text)
            while remaining:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)

    def _body(self):
        if self.headers.get('Transfer-Encoding'):
            raise WebJobsError('length_required', 411, 'chunked bodies are unsupported; send Content-Length')
        length_text = self.headers.get('Content-Length')
        if length_text is None or not length_text.isdigit():
            raise WebJobsError('length_required', 411, 'Content-Length is required')
        length = int(length_text)
        if length > MAX_BODY:
            self._drain()
            raise WebJobsError('body_too_large', 413, f'request body exceeds {MAX_BODY} bytes')
        self._consumed = True
        data = self.rfile.read(length)
        if len(data) != length:
            raise WebJobsError('malformed_json', 400, 'request body ended early')
        content_type = self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
        if content_type != 'application/json':
            raise WebJobsError('content_type', 415, 'Content-Type must be application/json')
        try:
            body = web_jobs.strict_json(data)
        except ValueError:
            raise WebJobsError('malformed_json', 400, 'request body must be strict finite JSON without duplicate keys') from None
        if not isinstance(body, dict):
            raise WebJobsError('bad_type', 400, 'request body must be a JSON object')
        return body

    @staticmethod
    def _route(path):
        for pattern, name in ROUTES:
            match = pattern.fullmatch(path)
            if match:
                return name, (match.group(1) if match.groups() else None)
        return None, None

    # ----------------------------------------------------------------- dispatch

    def _dispatch(self):
        self._consumed = False
        try:
            self._trusted()
            if self.server.shutting_down or self.server.jobs.closed:
                raise WebJobsError('shutting_down', 503, 'server is shutting down')
            name, identifier = self._route(urlsplit(self.path).path)
            if name is None:
                raise WebJobsError('route_not_found', 404, 'unknown route')
            if self.command != METHODS[name]:
                raise WebJobsError('method_not_allowed', 405, 'method not allowed for this route')
            jobs = self.server.jobs
            if name == 'artifact':
                self._send_artifact(jobs.open_artifact(identifier))
                return
            if name == 'job':
                status, value = jobs.get_job(identifier)
            elif name == 'sources':
                status, value = jobs.admit_source(self._body())
            elif name == 'jobs':
                status, value = jobs.submit(self._body())
            elif name == 'cancel':
                body = self._body()
                status, value = jobs.cancel(identifier, body)
            else:
                body = self._body()
                status, value = jobs.retry(identifier, body)
            self._json(status, value)
        except WebJobsError as error:
            self._safe_drain()
            self._safe_json(error.status, error.body())
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception:  # never echo internals, paths or stderr
            self._safe_drain()
            self._safe_json(500, {'status': 'error', 'code': 'internal_error', 'error': 'internal_error'})

    def _safe_drain(self):
        try:
            self._drain()
        except (OSError, ValueError):
            pass

    def _safe_json(self, status, value):
        try:
            self._json(status, value)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass

    def _send_artifact(self, served):
        try:
            self._headers(200, served.content_type, served.size_bytes, {
                'X-Artifact-Sha256': served.sha256,
                'Content-Disposition': f'attachment; filename="{served.artifact_id}"'})
            offset = 0
            while offset < served.size_bytes:
                chunk = os.pread(served.descriptor, min(STREAM_CHUNK, served.size_bytes - offset), offset)
                if not chunk:
                    break
                self.wfile.write(chunk)
                offset += len(chunk)
        finally:
            served.close()

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _dispatch


# --------------------------------------------------------------------------- foreground entrypoint

def serve(runs_root, state_root, port, out=sys.stdout):
    """Foreground only: blocks until Ctrl-C/SIGTERM. No fork, no detach, no service registration."""
    jobs = WebJobs(runs_root, state_root)
    server = None
    try:
        jobs.start()
        server = WebAPIServer(jobs, port)
        out.write(json.dumps({'url': f'http://127.0.0.1:{server.server_address[1]}', 'token': server.token,
                              'foreground': True, 'daemon': False, 'stop': 'Ctrl-C',
                              'reconciliation': jobs.reconciliation}, sort_keys=True) + '\n')
        out.flush()

        def terminate(_signum, _frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, terminate)
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            pass
    finally:
        if server is not None:
            server.shutting_down = True
            server.server_close()
        jobs.close()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('serve', help='serve the loopback control API in the foreground')
    run.add_argument('--port', type=int, default=0, help='0 picks an ephemeral port')
    run.add_argument('--state-root', default=str(web_jobs.DEFAULT_STATE_ROOT))
    run.add_argument('--runs-root', default=str(web_jobs.ROOT), help='repository root holding artifacts/runs')
    args = parser.parse_args(argv)
    try:
        return serve(args.runs_root, args.state_root, args.port)
    except WebJobsError as error:
        print(json.dumps(error.body(), sort_keys=True), file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(json.dumps({'status': 'error', 'code': 'serve_failed', 'error': type(error).__name__}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
