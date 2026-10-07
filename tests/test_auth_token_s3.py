"""S3 auth_token lane: the valid-token Cloudflare Access path, end to end on the BUILT server.

Contract: docs/spec/sprints/AUTH_TOKEN_S3.md (frozen at 360086b2333803b1f852d701fe50c2c0364609e6).

Stdlib only. The adapter-node build (web/build) is started through `node --import <seam> serve.js`
in VIDEO_UTILS_AUTH_MODE=tailnet mode. The seam is a test-only Node preload module GENERATED at run
time under artifacts/s2/auth_token/<stamp>/ (gitignored, never under web/). It redirects exactly the
derived JWKS URL of the reserved test team to a loopback JWKS server run by this module, refuses all
other non-loopback egress, and supplies a virtual wall clock read from clock.json. It refuses to load
under NODE_ENV=production, a Kubernetes pod environment, cwd /app, a non-loopback HOST, a
non-reserved team domain, or a missing/wrong per-run nonce.

RSA key pairs are generated per run inside a one-shot node subprocess; private keys never leave
that process and tokens never touch the disk. Nothing contacts Cloudflare or any external host.
Every subprocess has a timeout <= 60 s; only one server process runs at a time.

Run from the worktree root:  PYTHONPATH=tests python3 -m unittest test_auth_token_s3 -v
"""

from __future__ import annotations

import http.client
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "web"
AUTH = WEB / "src" / "lib" / "server" / "auth"
CONTRACT = REPO / "docs" / "spec" / "sprints" / "AUTH_TOKEN_S3.md"
RECEIPT_DIR = REPO / "docs" / "agent-notes" / "sprints" / "20261007-s3"
RECEIPT = RECEIPT_DIR / "auth_token-implementation-receipt.json"
ARTIFACT_ROOT = REPO / "artifacts" / "s2" / "auth_token"

SUBPROCESS_TIMEOUT_S = 60
LISTEN_WAIT_S = 30
REQUEST_TIMEOUT_S = 10

# ---- Reserved / example configuration (section 5) -------------------------------------------
TEAM = "videoutils-authtoken-test.cloudflareaccess.com"
ISS = f"https://{TEAM}"
JWKS_PROD_URL = f"https://{TEAM}/cdn-cgi/access/certs"
AUD_A = "AudTokenLaneA0123456789abcdef"
AUD_B = "AudTokenLaneB9876543210fedcba"
PUBLIC_HOST = "video-utils.example.org"
ALLOWLIST_RAW = " Operator@Example.org , second@example.org"
NONCE_ENV = "VIDEO_UTILS_AUTH_TOKEN_SEAM_NONCE"
ALL_INTERFACES = ".".join(["0"] * 4)
V0_MS = 1_900_000_000_000
JWKS_CAP = 64 * 1024

IDENTITY_MESSAGE = "Access to this app requires an approved operator identity."
DENY_BODY = [
    ("status", "error"),
    ("code", "bff_identity_refused"),
    ("message", IDENTITY_MESSAGE),
    ("upstream_status", None),
    ("upstream_code", None),
    ("upstream_detail_code", None),
]
GATE_CODES = {"bff_identity_refused", "bff_host_refused", "bff_auth_unconfigured"}

# Section 7.1: carried in case-table.json and the receipt; null or the string shown, never omitted.
UNKNOWN_FIELDS: dict[str, Any] = {
    "public_hostname": None,
    "cloudflare_tunnel_id": None,
    "access_application_aud": None,
    "access_idp_ids": None,
    "tsidp_claims_in_access_jwt": "unknown",
    "assertion_idp_visible_to_app": "unknown",
    "real_access_token_claim_shape": "unknown",
    "real_cloudflare_jwks_contacted": False,
    "jwks_tls_path": "not_exercised",
    "dns_resolution": "not_exercised",
    "jwks_transport": "loopback_http_via_test_seam",
    "clock": "virtual_via_test_seam",
    "virtual_epoch_ms": V0_MS,
    "jwks_fetch_timeout_5s": "not_exercised",
    "tailscale_serve_identity": "not_accepted",
    "applied": False,
    "served_proof": "not_run",
    "container_built": False,
}

DOD_GROUPS = ["J1", "J13", "expired", "not_yet_valid", "wrong_aud", "wrong_iss", "unknown_kid", "rotation",
              "alg_none_hs256", "oversize_jwks", "endpoint_down_stale"]


# ---------------------------------------------------------------------------------------------
# Session state (one stamp directory per test session)
# ---------------------------------------------------------------------------------------------

_SESSION: dict[str, Any] = {
    "stamp": None,
    "dir": None,
    "fixtures": None,
    "nonces": [],
    "processes": [],
    "cases": [],
    "seam_guards": [],
    "observations": [],
}


def _session_dir() -> Path:
    if _SESSION["dir"] is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
        path = ARTIFACT_ROOT / stamp
        path.mkdir(parents=True, exist_ok=False)
        _SESSION["stamp"] = stamp
        _SESSION["dir"] = path
    return _SESSION["dir"]


def _prerequisite_skip(case: unittest.TestCase) -> None:
    if shutil.which("node") is None:
        case.skipTest("node not on PATH")
    index = WEB / "build" / "index.js"
    if not index.is_file():
        case.skipTest("web/build absent (run `pnpm install --frozen-lockfile --offline && pnpm run build` in web/)")
    built = index.stat().st_mtime
    newest = max((f.stat().st_mtime for f in (WEB / "src").rglob("*") if f.is_file()), default=0.0)
    newest = max(newest, (WEB / "serve.js").stat().st_mtime)
    if newest > built:
        case.skipTest("web/build is older than web sources (stale build; rebuild with `pnpm run build`)")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _base_env(**overrides: str | None) -> dict[str, str]:
    """Scrubbed launch environment: no NODE_OPTIONS, no inherited VIDEO_UTILS_*, NODE_ENV or KUBERNETES_*."""
    env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "TMPDIR") if k in os.environ}
    for key, value in overrides.items():
        if value is not None:
            env[key] = value
    return env


def _tailnet_env(port: int, nonce: str, **overrides: str | None) -> dict[str, str]:
    values: dict[str, str | None] = {
        "VIDEO_UTILS_AUTH_MODE": "tailnet",
        "VIDEO_UTILS_CF_ACCESS_TEAM_DOMAIN": TEAM,
        "VIDEO_UTILS_CF_ACCESS_AUDS": f"{AUD_A},{AUD_B}",
        "VIDEO_UTILS_OPERATOR_ALLOWLIST": ALLOWLIST_RAW,
        "VIDEO_UTILS_PUBLIC_HOSTS": PUBLIC_HOST,
        "ORIGIN": f"https://{PUBLIC_HOST}",
        "HOST": "127.0.0.1",
        "PORT": str(port),
        NONCE_ENV: nonce,
    }
    values.update(overrides)
    return _base_env(**values)


# ---------------------------------------------------------------------------------------------
# Test-only seam (section 4), generated per server process
# ---------------------------------------------------------------------------------------------

SEAM_TEMPLATE = r"""// auth_token S3 TEST-ONLY seam. Generated at test runtime by tests/test_auth_token_s3.py.
// Never under web/, never committed, never in the image. See docs/spec/sprints/AUTH_TOKEN_S3.md section 4.
import { readFileSync, appendFileSync } from 'node:fs';

const NONCE = __NONCE__;
const TEST_TEAM = 'videoutils-authtoken-test.cloudflareaccess.com';
const JWKS_PROD_URL = `https://${TEST_TEAM}/cdn-cgi/access/certs`;
const JWKS_LOOPBACK_URL = __JWKS_LOOPBACK_URL__;
const CLOCK_FILE = __CLOCK_FILE__;
const ATTEMPTS_LOG = __ATTEMPTS_LOG__;
const EGRESS_LOG = __EGRESS_LOG__;

function refuse(rule) {
	throw new Error(`auth_token test seam refused: ${rule}`);
}
const env = process.env;
if (env.NODE_ENV === 'production') refuse('NODE_ENV');
if (env.KUBERNETES_SERVICE_HOST !== undefined) refuse('KUBERNETES_SERVICE_HOST');
if (env.KUBERNETES_PORT !== undefined) refuse('KUBERNETES_PORT');
if (process.cwd() === '/app') refuse('cwd');
if (env.HOST !== '127.0.0.1') refuse('HOST');
if (env.VIDEO_UTILS_CF_ACCESS_TEAM_DOMAIN !== TEST_TEAM) refuse('VIDEO_UTILS_CF_ACCESS_TEAM_DOMAIN');
if (env.VIDEO_UTILS_AUTH_TOKEN_SEAM_NONCE !== NONCE) refuse('VIDEO_UTILS_AUTH_TOKEN_SEAM_NONCE');
delete env.VIDEO_UTILS_AUTH_TOKEN_SEAM_NONCE;

// 1. Wall clock: virtual_ms + real elapsed since set_at_real_ms; read on every call; loud on failure.
const realNow = Date.now;
Date.now = function seamNow() {
	const clock = JSON.parse(readFileSync(CLOCK_FILE, 'utf8'));
	if (!Number.isFinite(clock.virtual_ms) || !Number.isFinite(clock.set_at_real_ms)) {
		throw new Error('auth_token test seam clock invalid');
	}
	return clock.virtual_ms + (realNow() - clock.set_at_real_ms);
};

// 2. JWKS destination: only the reserved team's derived URL is re-issued to loopback, init unchanged.
const realFetch = globalThis.fetch;
globalThis.fetch = function seamFetch(input, init) {
	const url = typeof input === 'string' ? input : input instanceof URL ? input.href : String(input?.url ?? input);
	if (url === JWKS_PROD_URL) {
		const headers = new Headers(init?.headers ?? {});
		appendFileSync(ATTEMPTS_LOG, JSON.stringify({
			real_ms: realNow(),
			method: init?.method ?? null,
			redirect: init?.redirect ?? null,
			signal: init?.signal instanceof AbortSignal,
			accept: headers.get('accept')
		}) + '\n');
		return realFetch(JWKS_LOOPBACK_URL, init);
	}
	let host = null;
	try {
		host = new URL(url).hostname;
	} catch {
		host = null;
	}
	if (host === '127.0.0.1') return realFetch(input, init);
	appendFileSync(EGRESS_LOG, JSON.stringify({ real_ms: realNow(), host }) + '\n');
	return Promise.reject(new TypeError('auth_token test seam: non-loopback egress refused'));
};
"""


@dataclass
class SeamFiles:
    dir: Path
    seam: Path
    nonce: str
    clock: Path
    attempts: Path
    egress: Path


def _write_seam(name: str, jwks_port: int) -> SeamFiles:
    proc_dir = _session_dir() / name
    proc_dir.mkdir(parents=True, exist_ok=False)
    nonce = secrets.token_hex(16)  # 128-bit; lives only in this generated file and the launch env
    _SESSION["nonces"].append(nonce)
    files = SeamFiles(proc_dir, proc_dir / "seam.mjs", nonce, proc_dir / "clock.json",
                      proc_dir / "jwks-attempts.log", proc_dir / "egress-refused.log")
    text = (SEAM_TEMPLATE
            .replace("__NONCE__", json.dumps(nonce))
            .replace("__JWKS_LOOPBACK_URL__", json.dumps(f"http://127.0.0.1:{jwks_port}/cdn-cgi/access/certs"))
            .replace("__CLOCK_FILE__", json.dumps(str(files.clock)))
            .replace("__ATTEMPTS_LOG__", json.dumps(str(files.attempts)))
            .replace("__EGRESS_LOG__", json.dumps(str(files.egress))))
    files.seam.write_text(text)
    files.attempts.write_text("")
    files.egress.write_text("")
    _set_clock(files, 0)
    return files


def _set_clock(files: SeamFiles, offset_s: int) -> None:
    tmp = files.clock.with_suffix(".tmp")
    tmp.write_text(json.dumps({"virtual_ms": V0_MS + offset_s * 1000, "set_at_real_ms": int(time.time() * 1000)}))
    os.replace(tmp, files.clock)


def _lines(path: Path) -> list[str]:
    return [line for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


# ---------------------------------------------------------------------------------------------
# Loopback JWKS server (section 5)
# ---------------------------------------------------------------------------------------------


class _JwksHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args: object) -> None:  # quiet
        return

    def do_GET(self) -> None:  # noqa: N802
        owner: JwksServer = self.server.owner  # type: ignore[attr-defined]
        with owner.lock:
            owner.count += 1
            kind, arg = owner.mode
        try:
            if self.path != "/cdn-cgi/access/certs":
                self._plain(404, b"")
            elif kind == "status":
                self._plain(int(arg), b"")
            elif kind == "status_body":
                status, size = arg
                self._plain(int(status), b" " * int(size))
            elif kind == "serve":
                self._plain(200, arg.encode("utf-8"))
            elif kind == "oversize_declared":
                doc, size = arg
                self._plain(200, _pad(doc, size))
            elif kind == "oversize_chunked":
                doc, size = arg
                body = _pad(doc, size)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Connection", "close")
                self.end_headers()
                for start in range(0, len(body), 8192):
                    chunk = body[start:start + 8192]
                    self.wfile.write(f"{len(chunk):x}\r\n".encode("ascii") + chunk + b"\r\n")
                self.wfile.write(b"0\r\n\r\n")
            else:
                self._plain(500, b"")
        except (BrokenPipeError, ConnectionResetError):
            pass  # the client may cancel an over-cap body; that is the behaviour under test

    def _plain(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if body:
            self.wfile.write(body)


def _pad(doc: str, size: int) -> bytes:
    raw = doc.encode("utf-8")
    if len(raw) > size:
        raise ValueError("JWKS document larger than the padded size")
    return raw + b" " * (size - len(raw))  # JSON whitespace keeps the document valid


class JwksServer:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.count = 0
        self.mode: tuple[str, Any] = ("status", 503)
        self.port = 0
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self, port: int = 0) -> None:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), _JwksHandler)
        httpd.daemon_threads = True
        httpd.owner = self  # type: ignore[attr-defined]
        self._httpd = httpd
        self.port = httpd.server_address[1]
        self._thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self._thread.start()

    @property
    def up(self) -> bool:
        return self._httpd is not None

    def close(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def set_mode(self, kind: str, arg: Any = None) -> None:
        with self.lock:
            self.mode = (kind, arg)


# ---------------------------------------------------------------------------------------------
# Fixtures: keys and tokens, minted in one node process (section 5)
# ---------------------------------------------------------------------------------------------

MINT_SCRIPT = r"""
import { generateKeyPairSync, sign, createHmac } from 'node:crypto';

const PLAN = __PLAN__;
const gen = () => generateKeyPairSync('rsa', { modulusLength: 2048 });
// k1 = kid-a, k2 = kid-b, kx = unpublished signer used under kid-a. Memory only; dies with this process.
const pairs = { k1: gen(), k2: gen(), kx: gen() };
const publicJwk = (name, kid) => ({ ...pairs[name].publicKey.export({ format: 'jwk' }), kid, use: 'sig', alg: 'RS256' });
const pub = { k1: publicJwk('k1', 'kid-a'), k2: publicJwk('k2', 'kid-b') };
const jwks = {
	k1: JSON.stringify({ keys: [pub.k1] }),
	k1k2: JSON.stringify({ keys: [pub.k1, pub.k2] }),
	k2: JSON.stringify({ keys: [pub.k2] })
};
const b64 = (v) => Buffer.from(typeof v === 'string' ? v : JSON.stringify(v)).toString('base64url');
const rsa = (kid, claims, name) => {
	const signed = `${b64({ alg: 'RS256', kid, typ: 'JWT' })}.${b64(claims)}`;
	return `${signed}.${sign('sha256', Buffer.from(signed), pairs[name].privateKey).toString('base64url')}`;
};
const hmac = (claims, secret) => {
	const signed = `${b64({ alg: 'HS256', kid: 'kid-a', typ: 'JWT' })}.${b64(claims)}`;
	return `${signed}.${createHmac('sha256', secret).update(signed).digest('base64url')}`;
};
const none = (claims, signature) => `${b64({ alg: 'none', kid: 'kid-a', typ: 'JWT' })}.${b64(claims)}.${signature}`;

const tokens = {};
for (const { id, signer, claims } of PLAN) {
	if (signer === 'k1') tokens[id] = rsa('kid-a', claims, 'k1');
	else if (signer === 'k2') tokens[id] = rsa('kid-b', claims, 'k2');
	else if (signer === 'kx') tokens[id] = rsa('kid-a', claims, 'kx');
	else if (signer === 'k1_unknown_kid') tokens[id] = rsa('kid-zzz', claims, 'k1');
	else if (signer === 'none_empty') tokens[id] = none(claims, '');
	else if (signer === 'none_garbage') tokens[id] = none(claims, b64('not-a-signature-at-all'));
	else if (signer === 'hs_pem') tokens[id] = hmac(claims, pairs.k1.publicKey.export({ format: 'pem', type: 'spki' }));
	else if (signer === 'hs_jwks') tokens[id] = hmac(claims, Buffer.from(jwks.k1, 'utf8'));
	else throw new Error(`unknown signer ${signer}`);
}
const privateMembers = ['d', 'p', 'q', 'dp', 'dq', 'qi'];
process.stdout.write(JSON.stringify({
	jwks,
	tokens,
	keys: {
		generated: Object.keys(pairs).length,
		modulus_bits: Object.values(pairs).map((p) => p.publicKey.asymmetricKeyDetails.modulusLength),
		private_members_in_public_jwks: [pub.k1, pub.k2].some((k) => privateMembers.some((m) => m in k))
	}
}));
"""


@dataclass
class Case:
    id: str
    proc: str
    step: int
    signer: str | None
    claims: dict[str, Any] | None
    expected: str  # allow | deny | host
    dfetch: int
    group: str
    label: str
    host: str = "public"  # public | rebind | loopback
    jwks: tuple[str, Any] | None = None  # JWKS mode change applied before this case
    restart_jwks: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def _claims(step: int, **over: Any) -> dict[str, Any]:
    now = V0_MS // 1000 + step
    claims: dict[str, Any] = {"iss": ISS, "aud": [AUD_A], "sub": "synthetic", "email": "Operator@EXAMPLE.org",
                              "iat": now - 10, "nbf": now - 10, "exp": now + 600}
    for key, value in over.items():
        claims[key] = value(now) if callable(value) else value
    return claims


def _plan() -> list[Case]:
    a, b, c = "P_A", "P_B", "P_C"
    cases = [
        # ---- 6.1 P_A: decisions, unknown kid, rotation (JWKS starts as {k1}) ----
        Case("E00a", a, 0, "k1", _claims(0), "host", 0, "host_precedence", "valid k1, Host rebind.example.org",
             host="rebind", jwks=("serve", "k1")),
        Case("E00b", a, 0, "k1", _claims(0), "host", 0, "host_precedence", "valid k1, Host 127.0.0.1:<port>",
             host="loopback"),
        Case("E01", a, 0, "k1", _claims(0), "allow", 1, "J1", "J1 valid k1, email Operator@EXAMPLE.org"),
        Case("E02", a, 0, "k1", _claims(0, email="stranger@example.org"), "deny", 0, "J13",
             "J13 valid k1, not allowlisted"),
        Case("E03", a, 0, "k1", _claims(0, exp=lambda n: n - 61), "deny", 0, "expired", "exp = now - 61"),
        Case("E03c", a, 0, "k1", _claims(0, exp=lambda n: n - 30), "allow", 0, "expired",
             "control: exp = now - 30 (within skew)"),
        Case("E04", a, 0, "k1", _claims(0, nbf=lambda n: n + 120), "deny", 0, "not_yet_valid", "nbf = now + 120"),
        Case("E04b", a, 0, "k1", _claims(0, iat=lambda n: n + 120), "deny", 0, "not_yet_valid", "iat = now + 120"),
        Case("E04c", a, 0, "k1", _claims(0, nbf=lambda n: n + 30), "allow", 0, "not_yet_valid",
             "control: nbf = now + 30"),
        Case("E05", a, 0, "k1", _claims(0, aud=["AudTokenLaneZ0000000000000000"]), "deny", 0, "wrong_aud",
             "aud not configured"),
        Case("E05b", a, 0, "k1", _claims(0, aud=[AUD_A.lower()]), "deny", 0, "wrong_aud", "AUD case-folded"),
        Case("E06", a, 0, "k1", _claims(0, iss="https://other-team.cloudflareaccess.com"), "deny", 0, "wrong_iss",
             "other team issuer"),
        Case("E06b", a, 0, "k1", _claims(0, iss=ISS + "/"), "deny", 0, "wrong_iss", "issuer with trailing /"),
        Case("E06c", a, 0, "k1", _claims(0, iss="http://" + TEAM), "deny", 0, "wrong_iss", "issuer with http://"),
        Case("E07a", a, 0, "none_empty", _claims(0), "deny", 0, "alg_none_hs256", "alg none, empty signature"),
        Case("E07b", a, 0, "none_garbage", _claims(0), "deny", 0, "alg_none_hs256", "alg none, garbage signature"),
        Case("E07c", a, 0, "hs_pem", _claims(0), "deny", 0, "alg_none_hs256", "HS256 keyed with k1 SPKI PEM"),
        Case("E07d", a, 0, "hs_jwks", _claims(0), "deny", 0, "alg_none_hs256", "HS256 keyed with served JWKS bytes"),
        Case("E07e", a, 0, "kx", _claims(0), "deny", 0, "signature", "RS256 kid-a signed by unpublished kx"),
        Case("E08", a, 0, "k1_unknown_kid", _claims(0), "deny", 0, "unknown_kid", "kid-zzz within cooldown"),
        Case("E09", a, 40, "k1_unknown_kid", _claims(40), "deny", 1, "unknown_kid", "kid-zzz: one refetch"),
        Case("E09b", a, 40, "k1_unknown_kid", _claims(40), "deny", 0, "unknown_kid", "kid-zzz again (cooldown)"),
        Case("E10", a, 80, "k2", _claims(80), "allow", 1, "rotation", "rotated key k2 (kid-b)",
             jwks=("serve", "k1k2")),
        Case("E10b", a, 80, "k1", _claims(80), "allow", 0, "rotation", "k1 after rotation publish"),
        Case("E11", a, 120, "k1", _claims(120), "allow", 0, "rotation", "retired k1 within fresh TTL (designed lag)",
             jwks=("serve", "k2")),
        Case("E12", a, 740, "k1", _claims(740), "deny", 1, "rotation", "retired k1 after fresh TTL"),
        Case("E12b", a, 740, "k2", _claims(740), "allow", 0, "rotation", "k2 after retirement"),
        # ---- 6.2 P_B: oversize JWKS, cold cache ----
        Case("E13", b, 0, "k1", _claims(0), "deny", 1, "oversize_jwks", "declared Content-Length 65537",
             jwks=("oversize_declared", ("k1", JWKS_CAP + 1))),
        Case("E13b", b, 40, "k1", _claims(40), "deny", 1, "oversize_jwks", "chunked body 65537 bytes",
             jwks=("oversize_chunked", ("k1", JWKS_CAP + 1))),
        Case("E13c", b, 80, "k1", _claims(80), "allow", 1, "oversize_jwks", "control: declared 65536 (at cap)",
             jwks=("oversize_declared", ("k1", JWKS_CAP))),
        # ---- 6.3 P_C: endpoint down, stale-within-max, then deny (JWKS {k1}) ----
        Case("E14a", c, 0, "k1", _claims(0), "allow", 1, "endpoint_down_stale", "serve", jwks=("serve", "k1")),
        Case("E14b", c, 660, "k1", _claims(660), "allow", 1, "endpoint_down_stale", "503, stale allow",
             jwks=("status", 503)),
        Case("E14c", c, 670, "k1", _claims(670), "allow", 0, "endpoint_down_stale", "503, cooldown, stale allow"),
        Case("E14d", c, 1800, "k1", _claims(1800), "allow", 1, "endpoint_down_stale", "closed, stale allow",
             jwks=("closed", None)),
        Case("E14e", c, 3540, "k1", _claims(3540), "allow", 1, "endpoint_down_stale",
             "closed, stale allow (age < 60 min)"),
        Case("E14f", c, 3660, "k1", _claims(3660), "deny", 1, "endpoint_down_stale", "closed, age > 60 min"),
        Case("E14g", c, 3720, "k1", _claims(3720), "allow", 1, "endpoint_down_stale", "serve again on same port",
             jwks=("serve", "k1"), restart_jwks=True),
    ]
    return cases


def _fixtures(case: unittest.TestCase) -> dict[str, Any]:
    if _SESSION["fixtures"] is None:
        plan = [{"id": c.id, "signer": c.signer, "claims": c.claims} for c in _plan() if c.signer is not None]
        proc = subprocess.run(["node", "--input-type=module", "-"],
                              input=MINT_SCRIPT.replace("__PLAN__", json.dumps(plan)),
                              capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_S, env=_base_env(), cwd=REPO)
        if proc.returncode != 0:
            case.fail(f"key/token mint failed: {proc.stderr[-2000:]}")
        _SESSION["fixtures"] = json.loads(proc.stdout)
    return _SESSION["fixtures"]


# ---------------------------------------------------------------------------------------------
# Server process
# ---------------------------------------------------------------------------------------------


class ServerProcess:
    def __init__(self, files: SeamFiles, env: dict[str, str]) -> None:
        self.files = files
        self.env = env
        self.port = int(env["PORT"])
        self.stdout = open(files.dir / "server-stdout.log", "w")  # noqa: SIM115
        self.stderr = open(files.dir / "server-stderr.log", "w")  # noqa: SIM115
        self.proc = subprocess.Popen(["node", "--import", files.seam.as_uri(), "serve.js"], cwd=WEB, env=env,
                                     stdout=self.stdout, stderr=self.stderr)
        self.ever_listened = False

    def wait_listening(self) -> bool:
        deadline = time.monotonic() + LISTEN_WAIT_S
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                return False
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    self.ever_listened = True
                    return True
            except OSError:
                time.sleep(0.1)
        return False

    def wait_exit_watching_port(self) -> int | None:
        deadline = time.monotonic() + LISTEN_WAIT_S
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.2):
                    self.ever_listened = True
            except OSError:
                pass
            code = self.proc.poll()
            if code is not None:
                return code
            time.sleep(0.05)
        return None

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        self.stdout.close()
        self.stderr.close()

    def stderr_text(self) -> str:
        if not self.stderr.closed:
            self.stderr.flush()
        return (self.files.dir / "server-stderr.log").read_text()


def _request(port: int, host: str, assertion: str | None, path: str = "/") -> dict[str, Any]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=REQUEST_TIMEOUT_S)
    try:
        headers = {"Host": host}
        if assertion is not None:
            headers["Cf-Access-Jwt-Assertion"] = assertion
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        body_pairs = None
        if raw[:1] == b"{":
            try:
                body_pairs = json.loads(raw.decode("utf-8"), object_pairs_hook=list)
            except ValueError:
                body_pairs = None
        return {"status": resp.status, "cache_control": resp.getheader("cache-control") or "",
                "content_type": resp.getheader("content-type") or "", "body_pairs": body_pairs,
                "raw_sha_len": len(raw), "raw": raw}
    finally:
        conn.close()


def _decision(resp: dict[str, Any]) -> tuple[str, str | None]:
    pairs = resp["body_pairs"]
    code = dict(pairs).get("code") if isinstance(pairs, list) else None
    if resp["status"] == 421 and code == "bff_host_refused":
        return "host", code
    if resp["status"] == 403 and pairs == DENY_BODY and resp["cache_control"] == "no-store":
        return "deny", code
    if resp["status"] not in (403, 421) and code not in GATE_CODES:
        return "allow", code
    return "other", code


def _run_process(case: unittest.TestCase, name: str) -> list[dict[str, Any]]:
    fixtures = _fixtures(case)
    jwks_docs: dict[str, str] = fixtures["jwks"]
    tokens: dict[str, str] = fixtures["tokens"]
    cases = [c for c in _plan() if c.proc == name]
    jwks = JwksServer()
    jwks.set_mode("serve", jwks_docs["k1"])
    jwks.start()
    files = _write_seam(name, jwks.port)
    port = _free_port()
    server = ServerProcess(files, _tailnet_env(port, files.nonce))
    rows: list[dict[str, Any]] = []
    try:
        if not server.wait_listening():
            case.fail(f"{name}: server did not listen: {server.stderr_text()[-2000:]}")
        current_step: int | None = None
        for c in cases:
            if c.jwks is not None:
                kind, arg = c.jwks
                if kind == "closed":
                    jwks.close()
                else:
                    if c.restart_jwks or not jwks.up:
                        jwks.start(jwks.port)
                    if kind == "serve":
                        jwks.set_mode("serve", jwks_docs[arg])
                    elif kind in ("oversize_declared", "oversize_chunked"):
                        jwks.set_mode(kind, (jwks_docs[arg[0]], arg[1]))
                    else:
                        jwks.set_mode(kind, arg)
            if c.step != current_step:
                _set_clock(files, c.step)
                current_step = c.step
            host = {"public": PUBLIC_HOST, "rebind": "rebind.example.org", "loopback": f"127.0.0.1:{port}"}[c.host]
            seam_before = len(_lines(files.attempts))
            server_before = jwks.count
            listener_up = jwks.up
            resp = _request(port, host, tokens[c.id] if c.signer else None)
            seam_delta = len(_lines(files.attempts)) - seam_before
            server_delta = (jwks.count - server_before) if listener_up else None
            decision, code = _decision(resp)
            expected_status = {"deny": 403, "host": 421, "allow": None}[c.expected]
            expected_code = {"deny": "bff_identity_refused", "host": "bff_host_refused", "allow": None}[c.expected]
            row = {
                "id": c.id, "process": name, "step_s": c.step, "group": c.group, "case": c.label,
                "jwks_mode": (c.jwks[0] if c.jwks else None),
                "expected": {"decision": c.expected, "status": expected_status, "code": expected_code,
                             "delta_fetch": c.dfetch},
                "observed": {"decision": decision, "status": resp["status"], "code": code,
                             "cache_control": resp["cache_control"],
                             "deny_body_exact": resp["body_pairs"] == DENY_BODY,
                             "delta_fetch_seam": seam_delta, "delta_fetch_server": server_delta},
                "decision_match": decision == c.expected,
                "fetch_match": seam_delta == c.dfetch and (server_delta is None or server_delta == seam_delta),
                "_raw": resp["raw"] if decision == "deny" else None,
            }
            rows.append(row)
        egress = _lines(files.egress)
        attempts = [json.loads(line) for line in _lines(files.attempts)]
        _SESSION["processes"].append({
            "process": name, "jwks_attempts": len(attempts), "jwks_server_requests": jwks.count,
            "egress_refused": len(egress),
            "attempt_init_conformant": sum(1 for a in attempts if a.get("redirect") == "error" and a.get("signal") is True
                                           and a.get("method") == "GET" and a.get("accept") == "application/json"),
            "server_exit_code": None,
        })
    finally:
        server.stop()
        jwks.close()
        if _SESSION["processes"] and _SESSION["processes"][-1]["process"] == name:
            _SESSION["processes"][-1]["server_exit_code"] = server.proc.returncode
    _SESSION["cases"].extend(rows)
    return rows


# ---------------------------------------------------------------------------------------------
# Case table output (written at module teardown; never contains tokens, keys or nonces)
# ---------------------------------------------------------------------------------------------


def _case_table() -> dict[str, Any]:
    cases = [{k: v for k, v in row.items() if k != "_raw"} for row in _SESSION["cases"]]
    denies = [row for row in _SESSION["cases"] if row["observed"]["decision"] == "deny"]
    groups = {}
    for g in DOD_GROUPS:
        members = [row for row in cases if row["group"] == g]
        groups[g] = {"cases": len(members),
                     "all_matched": bool(members) and all(r["decision_match"] and r["fetch_match"] for r in members)}
    fixtures = _SESSION["fixtures"] or {}
    return {
        "schema": "video-utils.auth-token-case-table.v1",
        "lane": "auth_token",
        "sprint": "20261007-s3",
        "stamp": _SESSION["stamp"],
        "contract": "docs/spec/sprints/AUTH_TOKEN_S3.md",
        "claim_class": "e2e-local",
        "cases": cases,
        "metrics": {
            "decision_matched": {"numerator": sum(r["decision_match"] for r in cases), "denominator": len(cases)},
            "fetch_matched": {"numerator": sum(r["fetch_match"] for r in cases), "denominator": len(cases)},
            "expected_mix": {k: sum(1 for r in cases if r["expected"]["decision"] == k) for k in ("allow", "deny", "host")},
            "distinct_identity_deny_bodies": {"distinct": len({row["_raw"] for row in denies}),
                                              "denies": len(denies)},
            "dod_groups_covered": {"numerator": sum(1 for g in groups.values() if g["all_matched"]),
                                   "denominator": len(DOD_GROUPS), "groups": groups},
            "egress_refused_total": sum(p["egress_refused"] for p in _SESSION["processes"]),
            "jwks_attempts_total": sum(p["jwks_attempts"] for p in _SESSION["processes"]),
            "attempt_init_conformant_total": sum(p["attempt_init_conformant"] for p in _SESSION["processes"]),
        },
        "processes": _SESSION["processes"],
        "seam_guards": _SESSION["seam_guards"],
        "static_asset_observation": _SESSION["observations"],
        "static_checks": _SESSION.get("static", {}),
        "keys": fixtures.get("keys"),
        "committed_key_material": False,
        "unknowns": {**UNKNOWN_FIELDS,
                     "static_asset_gate": ({o["id"]: o["observed_status"] for o in _SESSION["observations"]}
                                           if _SESSION["observations"] else "not_run")},
    }


def tearDownModule() -> None:  # noqa: N802
    if _SESSION["dir"] is not None:
        (_SESSION["dir"] / "case-table.json").write_text(json.dumps(_case_table(), indent=2) + "\n")


# ---------------------------------------------------------------------------------------------
# 6.4 static checks (always run)
# ---------------------------------------------------------------------------------------------

PEM_MARK = "-" * 5 + "BEGIN"
JWT_SHAPE = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.")
KTY_MEMBER = re.compile(chr(34) + "k" + "ty" + chr(34))
PRIVATE_MEMBER = re.compile(r'"(?:' + "|".join(["d", "p", "q", "dp", "dq", "qi"]) + r')"\s*:')


def _owned_files() -> list[Path]:
    return [Path(__file__).resolve(), CONTRACT, *sorted(RECEIPT_DIR.glob("auth_token-*.json")),
            *sorted(AUTH.glob("*.js")), *sorted(AUTH.glob("*.test.ts"))]


def _sh1_findings(paths: list[Path]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        text = path.read_text(errors="replace")
        rel = str(path.relative_to(REPO)) if path.is_relative_to(REPO) else path.name
        if PEM_MARK in text:
            findings.append(f"{rel}: PEM block")
        if KTY_MEMBER.search(text) and PRIVATE_MEMBER.search(text):
            findings.append(f"{rel}: JWK private member beside kty")
        if JWT_SHAPE.search(text):
            findings.append(f"{rel}: JWT-shaped string")
        for nonce in _SESSION["nonces"]:
            if nonce in text:
                findings.append(f"{rel}: seam nonce value")
    return findings


class SeamStaticTests(unittest.TestCase):
    def test_sg6_seam_cannot_ship(self) -> None:
        needles = [NONCE_ENV.encode(), b"seam.mjs", b"--import"]
        skip_dirs = {"node_modules", "build", ".svelte-kit"}
        scanned = 0
        hits: list[str] = []
        for root, dirs, names in os.walk(WEB):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for name in names:
                path = Path(root) / name
                data = path.read_bytes()
                scanned += 1
                for needle in needles:
                    if needle in data:
                        hits.append(f"{path.relative_to(REPO)}: {needle.decode()}")
        container = (WEB / "Containerfile").read_text()
        mode = (AUTH / "mode.js").read_text()
        checks = {
            "web_tree_free_of_seam_references": hits == [],
            "containerfile_no_import_flag": "--import" not in container,
            "containerfile_no_node_options": "NODE_OPTIONS" not in container,
            "image_sets_node_env_production": "ENV NODE_ENV=production" in container,
            "image_workdir_is_app": "WORKDIR /app" in container,
            "mode_js_jwks_url_derivation_unchanged":
                "\t\t\tjwksUrl: `https://${teamDomain}/cdn-cgi/access/certs`,\n" in mode,
            "mode_js_team_domain_pattern_unchanged":
                "const TEAM_DOMAIN_PATTERN = /^[a-z0-9-]+\\.cloudflareaccess\\.com$/;" in mode,
            "auth_dir_exactly_four_modules":
                sorted(p.name for p in AUTH.glob("*.js")) == ["allowlist.js", "cf-access.js", "gate.js", "mode.js"],
        }
        _SESSION.setdefault("static", {})["sg6"] = {"web_files_scanned": scanned, "hits": hits,
                                                    "sub_checks": len(checks),
                                                    "sub_checks_holding": sum(checks.values()), "checks": checks}
        self.assertEqual(hits, [])
        self.assertEqual([k for k, v in checks.items() if not v], [])

    def test_sg6b_seam_template_guards_present(self) -> None:
        # The generated seam text carries every refusal rule before any patch is installed.
        head = SEAM_TEMPLATE.split("const realNow", 1)[0]
        for rule in ("NODE_ENV", "KUBERNETES_SERVICE_HOST", "KUBERNETES_PORT", "cwd", "HOST",
                     "VIDEO_UTILS_CF_ACCESS_TEAM_DOMAIN", NONCE_ENV):
            self.assertIn(f"refuse('{rule}')", head)
        self.assertNotIn("globalThis.fetch", head)
        self.assertNotIn("Date.now", head)

    def test_sh1_secret_hygiene(self) -> None:
        paths = _owned_files()
        findings = _sh1_findings(paths)
        artifact_files: list[Path] = []
        if _SESSION["dir"] is not None:  # generated logs never carry tokens (seam.mjs itself holds its nonce)
            artifact_files = [p for p in _SESSION["dir"].rglob("*") if p.is_file() and p.name != "seam.mjs"]
            for path in artifact_files:
                text = path.read_text(errors="replace")
                if JWT_SHAPE.search(text) or PEM_MARK in text:
                    findings.append(f"artifact {path.name}: token or key material")
        self.assertEqual(findings, [])
        _SESSION.setdefault("static", {})["sh1"] = {"files_scanned": len(paths), "artifact_files_scanned":
                                                    len(artifact_files), "findings": len(findings)}


class ReceiptTests(unittest.TestCase):
    """The committed receipt keeps the 7.1 unknown fields and the frozen denominators (schema-stable)."""

    def test_receipt_shape(self) -> None:
        if not RECEIPT.is_file():
            self.skipTest("receipt not written yet")
        doc = json.loads(RECEIPT.read_text())
        self.assertEqual(doc["lane"], "auth_token")
        for key, value in UNKNOWN_FIELDS.items():
            self.assertIn(key, doc["unknowns"])
            self.assertEqual(doc["unknowns"][key], value, key)
        self.assertIn("static_asset_gate", doc["unknowns"])
        self.assertIs(doc["committed_key_material"], False)
        self.assertIs(doc["preregistered"], False)
        metrics = doc["results"]["metrics"]
        self.assertEqual(metrics["decision_matched"]["denominator"], 37)
        self.assertEqual(metrics["fetch_matched"]["denominator"], 37)
        self.assertEqual(metrics["dod_groups_covered"]["denominator"], 11)
        self.assertEqual(metrics["seam_guard_refusals"]["denominator"], 5)
        self.assertEqual(len(doc["results"]["case_table"]), 37)
        self.assertIn("not_claimed", doc)


# ---------------------------------------------------------------------------------------------
# Section 8 regression D1 (node only, module loaded directly as the auth_hosting harness does)
# ---------------------------------------------------------------------------------------------

D1_SCRIPT = r"""
import { pathToFileURL } from 'node:url';
const cf = await import(pathToFileURL(`${process.env.AUTH_DIR}/cf-access.js`).href);
const cache = cf.createJwksCache({ jwksUrl: process.env.JWKS_URL });
const key = await cache.resolveKey('kid-a');
// Keep the event loop alive past the server's close of the unread body (the crash fired on socket end).
await new Promise((resolve) => setTimeout(resolve, 1500));
process.stdout.write(JSON.stringify({ key_resolved: key !== null, stats: cache.stats, alive: true }));
"""


class CfAccessRegressionTests(unittest.TestCase):
    """D1: an unread JWKS body (declared over the cap, or a non-OK status) left a paused undici parser;
    when the peer then closed the socket, undici's internal assert(!this.paused) threw uncaught and the
    whole server process exited (observed on the built server at E13 and standalone 3/3 per shape)."""

    def test_d1_unread_jwks_body_cannot_crash_process(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("node not on PATH")
        shapes = [("oversize_declared_200", "oversize_declared", None), ("status_503_65537", "status_body", 503)]
        results = []
        for name, kind, status in shapes:
            with self.subTest(shape=name):
                jwks = JwksServer()
                if kind == "oversize_declared":
                    jwks.set_mode("oversize_declared", ('{"keys":[]}', JWKS_CAP + 1))
                else:
                    jwks.set_mode("status_body", (status, JWKS_CAP + 1))
                jwks.start()
                try:
                    proc = subprocess.run(
                        ["node", "--input-type=module", "-"], input=D1_SCRIPT, capture_output=True, text=True,
                        timeout=SUBPROCESS_TIMEOUT_S, cwd=REPO,
                        env=_base_env(AUTH_DIR=str(AUTH),
                                      JWKS_URL=f"http://127.0.0.1:{jwks.port}/cdn-cgi/access/certs"))
                finally:
                    jwks.close()
                results.append({"shape": name, "exit_code": proc.returncode, "server_requests": jwks.count})
                self.assertEqual(proc.returncode, 0, proc.stderr[-1500:])
                out = json.loads(proc.stdout)
                self.assertEqual(out, {"key_resolved": False, "stats": {"fetches": 1, "failures": 1}, "alive": True})
                self.assertEqual(jwks.count, 1)
        _SESSION.setdefault("static", {})["d1_regression"] = results


# ---------------------------------------------------------------------------------------------
# 6.4 seam guards (node + build)
# ---------------------------------------------------------------------------------------------


class SeamGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        _prerequisite_skip(self)

    def _refused(self, sg: str, rule: str, **overrides: str | None) -> None:
        files = _write_seam(sg, 9)  # discard port; the seam must refuse before any fetch could happen
        port = _free_port()
        env = _tailnet_env(port, files.nonce)
        env.update({k: v for k, v in overrides.items() if v is not None})
        server = ServerProcess(files, env)
        try:
            code = server.wait_exit_watching_port()
        finally:
            server.stop()
        stderr = server.stderr_text()
        observed = {"id": sg, "rule": rule, "exit_code": code, "ever_listened": server.ever_listened,
                    "stderr_names_rule": f"auth_token test seam refused: {rule}" in stderr}
        _SESSION["seam_guards"].append(observed)
        self.assertIsNotNone(code, "seam guard did not stop the process")
        self.assertNotEqual(code, 0)
        self.assertFalse(server.ever_listened)
        self.assertTrue(observed["stderr_names_rule"], stderr[-1500:])
        for nonce in _SESSION["nonces"]:
            self.assertNotIn(nonce, stderr)

    def test_sg1_node_env_production(self) -> None:
        self._refused("SG1", "NODE_ENV", NODE_ENV="production")

    def test_sg2_kubernetes_pod_shape(self) -> None:
        self._refused("SG2", "KUBERNETES_SERVICE_HOST", KUBERNETES_SERVICE_HOST="10.0.0.1")

    def test_sg3_all_interfaces_host(self) -> None:
        self._refused("SG3", "HOST", HOST=ALL_INTERFACES)

    def test_sg4_wrong_nonce(self) -> None:
        self._refused("SG4", NONCE_ENV, **{NONCE_ENV: secrets.token_hex(16)})

    def test_sg5_non_reserved_team(self) -> None:
        self._refused("SG5", "VIDEO_UTILS_CF_ACCESS_TEAM_DOMAIN",
                      VIDEO_UTILS_CF_ACCESS_TEAM_DOMAIN="videoutils-test.cloudflareaccess.com")


# ---------------------------------------------------------------------------------------------
# 6.1-6.3 end-to-end decision cases (node + build), one server process per method
# ---------------------------------------------------------------------------------------------


class AccessTokenE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        _prerequisite_skip(self)

    def _check(self, rows: list[dict[str, Any]], expected_ids: list[str]) -> None:
        self.assertEqual([r["id"] for r in rows], expected_ids)
        for row in rows:
            with self.subTest(case=row["id"]):
                self.assertTrue(row["decision_match"], json.dumps(row["observed"]))
                self.assertTrue(row["fetch_match"], json.dumps(row["observed"]))
        process = _SESSION["processes"][-1]
        self.assertEqual(process["egress_refused"], 0, "SG7: non-loopback egress attempted")
        self.assertEqual(process["attempt_init_conformant"], process["jwks_attempts"],
                         "every JWKS fetch carries redirect:error, an AbortSignal, GET and accept json")

    def test_p_a_decisions_unknown_kid_rotation(self) -> None:
        rows = _run_process(self, "P_A")
        self._check(rows, ["E00a", "E00b", "E01", "E02", "E03", "E03c", "E04", "E04b", "E04c", "E05", "E05b",
                           "E06", "E06b", "E06c", "E07a", "E07b", "E07c", "E07d", "E07e", "E08", "E09", "E09b",
                           "E10", "E10b", "E11", "E12", "E12b"])
        deny_raw = {r["_raw"] for r in rows if r["observed"]["decision"] == "deny"}
        self.assertEqual(len(deny_raw), 1, "identity denies must share one body")

    def test_p_b_oversize_jwks(self) -> None:
        rows = _run_process(self, "P_B")
        self._check(rows, ["E13", "E13b", "E13c"])

    def test_p_c_endpoint_down_stale_then_deny(self) -> None:
        rows = _run_process(self, "P_C")
        self._check(rows, ["E14a", "E14b", "E14c", "E14d", "E14e", "E14f", "E14g"])


# ---------------------------------------------------------------------------------------------
# 6.5 static asset observation (not in the decision denominator)
# ---------------------------------------------------------------------------------------------


class StaticAssetObservationTests(unittest.TestCase):
    def setUp(self) -> None:
        _prerequisite_skip(self)

    def test_o1_client_assets_before_hooks(self) -> None:
        jwks = JwksServer()
        jwks.set_mode("status", 503)
        jwks.start()
        files = _write_seam("O1", jwks.port)
        port = _free_port()
        server = ServerProcess(files, _tailnet_env(port, files.nonce))
        try:
            if not server.wait_listening():
                self.fail(f"O1: server did not listen: {server.stderr_text()[-2000:]}")
            control = _request(port, PUBLIC_HOST, None, "/")
            immutable = sorted((WEB / "build" / "client" / "_app" / "immutable").rglob("*.js"))
            self.assertTrue(immutable, "web/build has no immutable client bundle")
            bundle = "/" + immutable[0].relative_to(WEB / "build" / "client").as_posix()
            # Root fix (serve.js gates every request before adapter-node's static handler): static files
            # now answer exactly like pages, 403 without an identity and 421 on a wrong Host.
            for oid, host, path, expected in (("O1a", PUBLIC_HOST, "/favicon.svg", 403),
                                              ("O1b", PUBLIC_HOST, "/_app/version.json", 403),
                                              ("O1c", PUBLIC_HOST, bundle, 403),
                                              ("O1d", "evil.example.org", "/favicon.svg", 421)):
                resp = _request(port, host, None, path)
                _SESSION["observations"].append({
                    "id": oid, "path": path, "spec_expectation_auth_hosting_4_5": expected,
                    "observed_status": resp["status"], "observed_content_type": resp["content_type"],
                    "control_root_status": control["status"]})
                with self.subTest(observation=oid):
                    self.assertEqual(resp["status"], expected)
            self.assertEqual(control["status"], 403)
            self.assertEqual(len(_lines(files.attempts)), 0)
            self.assertEqual(len(_lines(files.egress)), 0)
        finally:
            server.stop()
            jwks.close()


if __name__ == "__main__":
    unittest.main()
