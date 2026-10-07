"""S2 web_stack lane tests (docs/spec/sprints/WEB_STACK_S2.md section 7), rescoped by web_ui_binding.

WEB_UI_S2.md section 9.3: S1-S7, B1-B5 and N1-N13 keep their IDs; S8, S9, N1-N5 and N12 are
rescoped to the bound UI and the real /api/v1 shapes (reasons in the web_ui_binding tests receipt);
S10 and N14-N18 are new.

Stdlib only. Static checks always run. Build and integration checks need `node` and
`pnpm` on PATH and an already-populated pnpm store (offline frozen install); they skip
with an explicit reason otherwise. Every subprocess is bounded by a timeout, and every
process this module starts is terminated in tearDown/tearDownClass.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "web"
FIXTURES = WEB / "fixtures" / "control-api"
RECEIPT_DIR = REPO / "docs" / "agent-notes" / "sprints" / "20261006-s2"

EXACT_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
REQUIRED_MAJORS = {
    "@sveltejs/kit": 2,
    "svelte": 5,
    "effect": 4,
    "@skeletonlabs/skeleton": 5,
    "@skeletonlabs/skeleton-svelte": 5,
}
PROTOTYPE_ROUTES = ("compare", "review", "download")
BOUND_ROUTES = ("upload", "sources/[id=artifactid]", "jobs/[id=jobid]")
GENERATED_DIRS = ("node_modules", "build", ".svelte-kit")
SECRET_OR_HOST_PATTERNS = (
    re.compile(r"/Users/"),
    re.compile(r"/home/"),
    re.compile(r"/private/"),
    re.compile(r"/Volumes/"),
    re.compile(r"/nix/store/"),
    re.compile(r"C:\\"),
    re.compile(r"_authToken"),
    re.compile(r"npm_[A-Za-z0-9]{36}"),
    re.compile(r"ghp_"),
    re.compile(r"github_pat_"),
    re.compile(r"-----BEGIN"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
)
UPSTREAM_MARKER = "UPSTREAM_TEXT_MARKER_7f3a"
UPSTREAM_KEY_MARKER = "upstream_unexpected_field_ZQX"
TOKEN = "integration-token-" + "Q" * 24  # synthetic; never a real control-API token
TOKEN_ENV = "VIDEO_UTILS_CONTROL_API_TOKEN"
URL_ENV = "VIDEO_UTILS_CONTROL_API_URL"
JOB = {name: "job_" + "0" * 31 + digit for name, digit in (
    ("queued", "1"), ("running", "2"), ("succeeded", "3"), ("failed", "4"), ("bad_unknown_key", "5"),
    ("bad_enum", "6"), ("http_500", "7"), ("missing", "8"), ("slow", "9"), ("huge", "a"),
    ("huge_stream", "b"), ("token_refused", "c"))}
ART_OK = "art_" + "a" * 32
ART_PRIVATE = "art_" + "b" * 32
ART_BYTES = b"synthetic-share-mp4-bytes;" * 400
ERROR_KEYS = {"status", "code", "message", "upstream_status", "upstream_code", "upstream_detail_code"}

INSTALL_TIMEOUT_S = 300
CHECK_TIMEOUT_S = 300
BUILD_TIMEOUT_S = 300
OFFLINE_MISSING_MARKERS = ("ERR_PNPM_NO_OFFLINE_META", "ERR_PNPM_NO_OFFLINE_TARBALL")
PNPM_GATE_UNAVAILABLE_EXIT = 75  # EX_TEMPFAIL from this host's pnpm storage gate


def _git(*args: str) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, timeout=60, check=True
    ).stdout
    return [line for line in out.splitlines() if line]


def _web_files_to_commit() -> list[Path]:
    """Tracked plus untracked-not-ignored files under web/ (generated dirs excluded)."""
    names = set(_git("ls-files", "web")) | set(_git("ls-files", "--others", "--exclude-standard", "web"))
    files = []
    for name in sorted(names):
        parts = Path(name).parts
        if any(part in GENERATED_DIRS for part in parts):
            continue
        path = REPO / name
        if path.is_file():
            files.append(path)
    return files


def _receipt_files() -> list[Path]:
    return sorted([*RECEIPT_DIR.glob("web_stack-*.json"), *RECEIPT_DIR.glob("web_ui_binding-*.json")])


def _lock_importer_specifiers(lock_text: str) -> dict[str, str]:
    """Stdlib line parse of `importers['.']` dependency specifiers in pnpm-lock.yaml v9."""
    specs: dict[str, str] = {}
    lines = lock_text.splitlines()
    in_importers = in_root = False
    current: str | None = None
    for line in lines:
        if line == "importers:":
            in_importers = True
            continue
        if in_importers and line and not line.startswith(" "):
            break
        if not in_importers:
            continue
        if line == "  .:":
            in_root = True
            continue
        if in_root and re.match(r"^  \S", line):
            break
        if not in_root:
            continue
        dep = re.match(r"^      ('?)([^']+?)\1:$", line)
        if dep:
            current = dep.group(2)
            continue
        spec = re.match(r"^        specifier: (.+)$", line)
        if spec and current:
            specs[current] = spec.group(1).strip().strip("'\"")
            current = None
    return specs


def _clean_env(**overrides: str | None) -> dict[str, str]:
    env = dict(os.environ)
    for key in ("HOST", "PORT", "SOCKET_PATH", "ORIGIN", "BODY_SIZE_LIMIT", URL_ENV, TOKEN_ENV):
        env.pop(key, None)
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


def _toolchain_missing() -> str | None:
    if shutil.which("node") is None:
        return "node not on PATH"
    if shutil.which("pnpm") is None:
        return "pnpm not on PATH"
    return None


def _run(cmd: list[str], timeout: int, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=WEB, capture_output=True, text=True, timeout=timeout, env=env or _clean_env()
    )


_BUILD_STATE: dict[str, object] = {}


def _offline_install() -> tuple[str, str]:
    """Returns ("ok"|"skip"|"fail", detail)."""
    if "install" in _BUILD_STATE:
        return _BUILD_STATE["install"]  # type: ignore[return-value]
    proc = _run(["pnpm", "install", "--frozen-lockfile", "--offline"], INSTALL_TIMEOUT_S)
    output = proc.stdout + proc.stderr
    if proc.returncode == 0:
        result = ("ok", "")
    elif any(marker in output for marker in OFFLINE_MISSING_MARKERS):
        result = ("skip", "offline install: packages/metadata missing from the local pnpm store")
    elif proc.returncode == PNPM_GATE_UNAVAILABLE_EXIT:
        result = ("skip", "pnpm storage gate unavailable on this host (exit 75)")
    else:
        result = ("fail", output[-4000:])
    _BUILD_STATE["install"] = result
    return result


def _require_install(case: unittest.TestCase) -> None:
    missing = _toolchain_missing()
    if missing:
        case.skipTest(missing)
    status, detail = _offline_install()
    if status == "skip":
        case.skipTest(detail)
    if status == "fail":
        case.fail(f"pnpm install --frozen-lockfile --offline failed:\n{detail}")


def _ensure_build(case: unittest.TestCase) -> None:
    _require_install(case)
    if "build" not in _BUILD_STATE:
        proc = _run(["pnpm", "run", "build"], BUILD_TIMEOUT_S)
        _BUILD_STATE["build"] = (proc.returncode, (proc.stdout + proc.stderr)[-4000:])
    code, output = _BUILD_STATE["build"]  # type: ignore[misc]
    if code != 0:
        case.fail(f"pnpm run build failed:\n{output}")


# --------------------------------------------------------------------------------------
# Static checks (always run)
# --------------------------------------------------------------------------------------


class WebStackStaticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.package = json.loads((WEB / "package.json").read_text())

    def test_s1_lockfile_and_package_exist(self) -> None:
        lock = WEB / "pnpm-lock.yaml"
        self.assertTrue((WEB / "package.json").is_file())
        self.assertTrue(lock.is_file())
        text = lock.read_text()
        self.assertGreater(len(text), 0)
        self.assertRegex(text, r"(?m)^lockfileVersion: '?\d")

    def test_s2_exact_pins_and_required_majors(self) -> None:
        declared = {
            **self.package.get("dependencies", {}),
            **self.package.get("devDependencies", {}),
        }
        self.assertGreater(len(declared), 0)
        for name, spec in declared.items():
            with self.subTest(package=name):
                self.assertRegex(spec, EXACT_VERSION)
                self.assertFalse(spec.startswith(("^", "~")))
        for name, major in REQUIRED_MAJORS.items():
            with self.subTest(required=name):
                self.assertIn(name, declared)
                self.assertEqual(int(declared[name].split(".")[0]), major)
        self.assertIn("@sveltejs/adapter-node", declared)
        self.assertIn("effect", self.package.get("dependencies", {}), "effect is a runtime dependency")
        self.assertEqual(self.package.get("packageManager"), "pnpm@11.25.0")

    def test_s3_lock_importer_specifiers_match_package(self) -> None:
        declared = {
            **self.package.get("dependencies", {}),
            **self.package.get("devDependencies", {}),
        }
        specs = _lock_importer_specifiers((WEB / "pnpm-lock.yaml").read_text())
        self.assertEqual(specs, declared)

    def test_s4_adapter_node_only_no_remote_functions(self) -> None:
        config = (WEB / "svelte.config.js").read_text()
        self.assertIn("@sveltejs/adapter-node", config)
        for forbidden in ("adapter-static", "adapter-auto", "remoteFunctions"):
            self.assertNotIn(forbidden, config)
        self.assertNotRegex(config, r"experimental\s*:")
        vite = (WEB / "vite.config.ts").read_text()
        self.assertNotIn("remoteFunctions", vite)

    def test_s5_gitignore_and_no_generated_files_tracked(self) -> None:
        ignore = (WEB / ".gitignore").read_text().splitlines()
        stripped = {line.strip().rstrip("/") for line in ignore}
        for entry in ("node_modules", "build", ".svelte-kit", ".env"):
            self.assertIn(entry, stripped)
        for name in _git("ls-files", "web"):
            parts = Path(name).parts
            self.assertFalse(any(part in GENERATED_DIRS for part in parts), name)
            self.assertFalse(Path(name).name.startswith(".env"), name)
        for name in _git("ls-files", "--others", "--exclude-standard", "web"):
            parts = Path(name).parts
            self.assertFalse(any(part in GENERATED_DIRS for part in parts), f"not ignored: {name}")

    def test_s6_no_secrets_or_host_paths(self) -> None:
        files = _web_files_to_commit() + _receipt_files()
        self.assertGreater(len(files), 0)
        hits = []
        for path in files:
            text = path.read_text(errors="replace")
            for pattern in SECRET_OR_HOST_PATTERNS:
                if pattern.search(text):
                    hits.append(f"{path.relative_to(REPO)}: {pattern.pattern}")
        self.assertEqual(hits, [], f"scanned {len(files)} files")
        for path in files:
            self.assertFalse(path.name.startswith(".env"), path)
        npmrc = (WEB / ".npmrc").read_text().splitlines()
        for line in npmrc:
            body = line.strip()
            if not body or body.startswith(("#", ";")):
                continue
            self.assertNotRegex(body, r"(?i)(_auth|_password|token|username|//[^=]*:)", body)

    def test_s7_loopback_only(self) -> None:
        vite = (WEB / "vite.config.ts").read_text()
        self.assertRegex(vite, r"server:\s*\{[^}]*host:\s*'127\.0\.0\.1'")
        self.assertRegex(vite, r"preview:\s*\{[^}]*host:\s*'127\.0\.0\.1'")
        self.assertRegex(vite, r"server:\s*\{[^}]*strictPort:\s*true")
        for path in _web_files_to_commit():
            if path.suffix not in {".js", ".ts", ".svelte", ".json", ".html", ".yaml"}:
                continue
            if path.name == "pnpm-lock.yaml":
                continue
            text = path.read_text()
            with self.subTest(file=str(path.relative_to(REPO))):
                self.assertNotIn("0.0.0.0", text)
                self.assertNotRegex(text, r"host:\s*true")
        self.assertEqual(self.package["scripts"]["start"], "node serve.js")
        serve = (WEB / "serve.js").read_text()
        self.assertIn("process.exit(REFUSAL_EXIT_CODE)", serve)
        self.assertLess(serve.index("process.exit(REFUSAL_EXIT_CODE)"), serve.index("import('./build/index.js')"))

    def test_s8_prototype_routes_label_only(self) -> None:
        """Rescoped (WEB_UI_S2 9.3; ROUTES_REVIEW_S3 6.8): bound routes post only to /api/* BFF endpoints; client
        files never name the control API URL, the token env or fetch('http://; the former prototype stubs
        (/compare, /review, /download) are run pickers that redirect (303) to /runs/[id]/... with no form."""
        for slug in PROTOTYPE_ROUTES:
            route = WEB / "src" / "routes" / slug / "+page.svelte"
            with self.subTest(route=slug):
                text = route.read_text()
                loader = (route.parent / "+page.server.ts").read_text()
                self.assertNotIn("PrototypeNotice", text + loader)
                self.assertIn("redirect(303", loader)
                self.assertIn("/runs/", text + loader)
                self.assertNotIn("<form", text)
                self.assertNotIn("<input", text)
                self.assertFalse((route.parent / "+server.ts").exists())
        notice = (WEB / "src" / "lib" / "components" / "PrototypeNotice.svelte").read_text()
        self.assertIn("Not implemented in S2", notice)
        self.assertNotIn("<form", notice)
        self.assertNotIn("<input", notice)
        client_files = [
            path for path in (WEB / "src").rglob("*")
            if path.is_file() and path.suffix in {".svelte", ".ts", ".js"}
            and "server" not in path.relative_to(WEB / "src").parts
            and not path.name.endswith((".server.ts", ".server.js")) and path.name != "+server.ts"
        ]
        self.assertGreater(len(client_files), 10)
        fetches = 0
        for path in client_files:
            text = path.read_text()
            with self.subTest(client_file=str(path.relative_to(REPO))):
                for forbidden in (URL_ENV, TOKEN_ENV, "fetch('http://", 'fetch("http://', "fetch(`http://",
                                  "$env/dynamic/private", "$env/static/private"):
                    self.assertNotIn(forbidden, text)
                for match in re.finditer(r"fetch\(\s*([`'\"])([^`'\"]*)", text):
                    fetches += 1
                    self.assertTrue(match.group(2).startswith("/api/"), match.group(0))
        self.assertGreaterEqual(fetches, 6)
        for slug in BOUND_ROUTES:
            with self.subTest(bound=slug):
                self.assertTrue((WEB / "src" / "routes" / slug / "+page.svelte").is_file())

    def test_s9_fixtures_parse_and_cover_cases(self) -> None:
        """Rescoped (WEB_UI_S2 9.3): the real v1 fixture set generated from web_api responses."""
        required = {
            "sources.json", "job_queued.json", "job_running.json", "job_succeeded.json", "job_failed.json",
            "job_bad_unknown_key.json", "job_bad_enum.json",
        }
        present = {path.name for path in FIXTURES.glob("*.json")}
        self.assertTrue(required <= present, required - present)
        for path in FIXTURES.glob("*.json"):
            text = path.read_text()
            json.loads(text)
            for pattern in SECRET_OR_HOST_PATTERNS:
                self.assertIsNone(pattern.search(text), f"{path.name}: {pattern.pattern}")
            self.assertNotRegex(text, r"(?i)\.(mov|mp4|wav|m4v)\b", path.name)
        readme = json.loads((FIXTURES / "README.json").read_text())
        self.assertEqual(readme["control_api_contract_source"], "web_jobs_s2_merged")
        sources = json.loads((FIXTURES / "sources.json").read_text())
        self.assertEqual(sources["schema_version"], 1)
        self.assertTrue(any(s["source_id"] is None and s["duration_seconds"] is None for s in sources["sources"]))
        for record in sources["sources"]:
            self.assertTrue(record["duration_seconds_reason"] and record["source_id_reason"])
        queued = json.loads((FIXTURES / "job_queued.json").read_text())
        self.assertIsNone(queued["progress"])
        self.assertIsNone(queued["eta_seconds"])
        running = json.loads((FIXTURES / "job_running.json").read_text())
        self.assertEqual(running["progress"]["denominator"], 6)
        succeeded = json.loads((FIXTURES / "job_succeeded.json").read_text())
        self.assertIn("share_mp4", {a["role"] for a in succeeded["artifacts"]})
        for name, job_id in JOB.items():
            path = FIXTURES / f"job_{name}.json"
            if path.is_file():
                self.assertEqual(json.loads(path.read_text())["job_id"], job_id, name)

    def test_s10_client_bundle_has_no_token_or_control_url(self) -> None:
        """New (WEB_UI_S2 9.3): the built client bundle never carries the token, its env name or a control URL."""
        _ensure_build(self)
        files = [path for path in (WEB / "build" / "client").rglob("*") if path.is_file()]
        self.assertGreater(len(files), 0)
        hits = []
        for path in files:
            text = path.read_bytes().decode("utf-8", errors="replace")
            for needle in (TOKEN, TOKEN_ENV, URL_ENV):
                if needle in text:
                    hits.append(f"{path.name}: {needle}")
            if re.search(r"127\.0\.0\.1:\d+", text):
                hits.append(f"{path.name}: loopback url")
        self.assertEqual(hits, [], f"scanned {len(files)} client files")


# --------------------------------------------------------------------------------------
# Build checks (node + pnpm + populated store)
# --------------------------------------------------------------------------------------


class WebStackBuildTests(unittest.TestCase):
    def test_b1_offline_frozen_install(self) -> None:
        _require_install(self)

    def test_b2_check(self) -> None:
        _require_install(self)
        proc = _run(["pnpm", "run", "check"], CHECK_TIMEOUT_S)
        output = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, output[-4000:])
        match = re.search(r"(\d+) ERRORS? (\d+) WARNINGS?", output) or re.search(
            r"(\d+) errors? and (\d+) warnings?", output
        )
        self.assertIsNotNone(match, output[-2000:])
        self.assertEqual(int(match.group(1)), 0)

    def test_b3_build_outputs(self) -> None:
        _ensure_build(self)
        self.assertTrue((WEB / "build" / "index.js").is_file())
        self.assertTrue((WEB / "build" / "handler.js").is_file())
        self.assertTrue((WEB / "build" / "client").is_dir())

    def test_b4_serve_refuses_non_loopback_host(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("node not on PATH")
        for host in ("0.0.0.0", "localhost", "192.0.2.1"):
            with self.subTest(host=host):
                proc = subprocess.run(
                    ["node", "serve.js"],
                    cwd=WEB,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    env=_clean_env(HOST=host, PORT=str(_free_port())),
                )
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertIn("refusing HOST", proc.stderr)
                self.assertNotIn("Listening", proc.stdout)

    def test_b5_polling_policy(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("node not on PATH")
        script = """
const m = await import(process.argv[1]);
const out = {
  terminal: m.TERMINAL_STATES.map((s) => m.nextPollDecision({ lastState: s, consecutiveErrors: 0 }).action),
  running: m.nextPollDecision({ lastState: 'running', consecutiveErrors: 0 }),
  backoff: [1, 2, 3, 4].map((n) => m.nextPollDecision({ lastState: 'running', consecutiveErrors: n }).delayMs),
  paused: m.nextPollDecision({ lastState: 'running', consecutiveErrors: 5 }),
  hidden: m.nextPollDecision({ lastState: 'running', consecutiveErrors: 0, hidden: true }),
  constants: [m.POLL_BASE_MS, m.POLL_BACKOFF_CAP_MS, m.POLL_MAX_CONSECUTIVE_ERRORS],
  terminalStates: m.TERMINAL_STATES,
  frozen: Object.isFrozen(m.TERMINAL_STATES)
};
console.log(JSON.stringify(out));
"""
        module_url = (WEB / "src" / "lib" / "polling.js").as_uri()
        proc = subprocess.run(
            ["node", "--input-type=module", "-e", script, module_url],
            capture_output=True,
            text=True,
            timeout=30,
            env=_clean_env(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(set(out["terminal"]), {"stop"})
        self.assertEqual(
            sorted(out["terminalStates"]),
            sorted(["succeeded", "failed", "cancelled", "needs_reconciliation", "interrupted"]),
        )
        self.assertTrue(out["frozen"])
        self.assertEqual(out["running"], {"action": "poll", "delayMs": 2000, "reason": "base"})
        self.assertEqual(out["backoff"], [4000, 8000, 16000, 30000])
        self.assertEqual(out["paused"], {"action": "paused", "reason": "polling_paused"})
        self.assertEqual(out["hidden"]["action"], "paused")
        self.assertEqual(out["constants"], [2000, 30000, 5])


# --------------------------------------------------------------------------------------
# Integration: built app against a stdlib mock control API
# --------------------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _MockControlApi:
    """Stdlib mock of the /api/v1 control API serving the real-shape fixtures. Records every request."""

    def __init__(self) -> None:
        self.requests: list[str] = []
        self.authorizations: list[str | None] = []
        self.stop = threading.Event()
        jobs = {}
        for path in FIXTURES.glob("job_*.json"):
            jobs[json.loads(path.read_text())["job_id"]] = path.read_bytes()
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:  # quiet
                return

            def _send(self, status: int, body: bytes, content_type: str = "application/json", extra: dict | None = None) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                for key, value in (extra or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def _typed(self, status: int, code: str, detail: str | None = None) -> None:
                body = {"status": "error", "code": code, "error": f"{UPSTREAM_MARKER} /Users/never/echoed"}
                if detail:
                    body["detail_code"] = detail
                self._send(status, json.dumps(body).encode())

            def _record(self) -> str:
                mock.requests.append(f"{self.command} {self.path}")
                mock.authorizations.append(self.headers.get("Authorization"))
                return self.path.split("?", 1)[0]

            def do_POST(self) -> None:  # noqa: N802
                path = self._record()
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 16 * 1024 * 1024:
                    self.rfile.read(length)
                if path == "/api/v1/uploads":
                    self._typed(415, "upload_type_refused")
                elif path == "/api/v1/sources":
                    self._typed(422, "path_escape", "host_path_refused")
                else:
                    self._send(404, b'{"detail":"no route"}')

            def do_GET(self) -> None:  # noqa: N802
                path = self._record()
                if path == "/api/v1/sources":
                    self._send(200, (FIXTURES / "sources.json").read_bytes())
                    return
                if path == f"/api/v1/artifacts/{ART_OK}":
                    self._send(200, ART_BYTES, "video/mp4", {
                        "X-Artifact-Sha256": hashlib.sha256(ART_BYTES).hexdigest(),
                        "Content-Disposition": f'attachment; filename="{ART_OK}"'})
                    return
                if path == f"/api/v1/artifacts/{ART_PRIVATE}":
                    self._typed(403, "artifact_private")
                    return
                prefix = "/api/v1/jobs/"
                if not path.startswith(prefix):
                    self._send(404, b'{"detail":"no route"}')
                    return
                job = path[len(prefix):]
                if job == JOB["http_500"]:
                    self._send(500, f"Traceback {UPSTREAM_MARKER}".encode(), "text/plain")
                elif job == JOB["missing"]:
                    self._send(404, f'{{"detail":"{UPSTREAM_MARKER}"}}'.encode())
                elif job == JOB["token_refused"]:
                    self._typed(401, "token_required")
                elif job == JOB["slow"]:
                    if mock.stop.wait(7.0):
                        return
                    self._send(200, (FIXTURES / "job_running.json").read_bytes())
                elif job in (JOB["huge"], JOB["huge_stream"]):
                    snapshot = json.loads((FIXTURES / "job_running.json").read_text())
                    snapshot["tool_envelope"]["limitations"] = ["x" * 400] * 3000  # ~1.2 MB
                    body = json.dumps(snapshot).encode()
                    if job == JOB["huge"]:
                        self._send(200, body)
                        return
                    # No Content-Length: the BFF must count bytes while streaming.
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    try:
                        for offset in range(0, len(body), 65536):
                            self.wfile.write(body[offset : offset + 65536])
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                elif job in jobs:
                    self._send(200, jobs[job])
                else:
                    self._typed(404, "unknown_job")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.server.block_on_close = False
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "_MockControlApi":
        self.thread.start()
        return self

    def close(self) -> None:
        self.stop.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=10)


class _App:
    """`node serve.js` on loopback with an ephemeral port, in its own process group."""

    def __init__(self, control_api_url: str | None, token: str | None = TOKEN) -> None:
        self.port = _free_port()
        self.origin = f"http://127.0.0.1:{self.port}"
        env = _clean_env(HOST="127.0.0.1", PORT=str(self.port), **{URL_ENV: control_api_url, TOKEN_ENV: token})
        self.proc = subprocess.Popen(
            ["node", "serve.js"],
            cwd=WEB,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"app exited early: {self.proc.stdout.read().decode(errors='replace')}")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.1)
        self.close()
        raise RuntimeError("app did not start listening within 30 s")

    def request(self, method: str, path: str, body: bytes | None = None, headers: dict | None = None,
                timeout: float = 15.0) -> tuple[int, dict, bytes, float]:
        start = time.monotonic()
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        try:
            conn.request(method, path, body=body, headers={"accept": "application/json, text/html", **(headers or {})})
            response = conn.getresponse()
            payload = response.read()
            return response.status, {k.lower(): v for k, v in response.getheaders()}, payload, time.monotonic() - start
        finally:
            conn.close()

    def get(self, path: str, timeout: float = 15.0) -> tuple[int, str, float]:
        status, _, payload, elapsed = self.request("GET", path, timeout=timeout)
        return status, payload.decode("utf-8", errors="replace"), elapsed

    def post_json(self, path: str, value: object, origin: str | None = "same") -> tuple[int, dict]:
        headers = {"content-type": "application/json"}
        if origin == "same":
            headers["origin"] = self.origin
        elif origin is not None:
            headers["origin"] = origin
        status, _, payload, _ = self.request("POST", path, json.dumps(value).encode(), headers)
        return status, json.loads(payload)

    def close(self) -> None:
        if self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass  # Darwin killpg(2) gives EPERM for an own group whose members are all zombies
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
                self.proc.wait(timeout=10)
        if self.proc.stdout:
            self.proc.stdout.close()


def _listen_addresses(pid: int) -> list[str] | None:
    """Optional socket check; None when lsof is unavailable."""
    lsof = shutil.which("lsof")
    if lsof is None:
        return None
    proc = subprocess.run(
        [lsof, "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", str(pid)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    addresses = []
    for line in proc.stdout.splitlines()[1:]:
        match = re.search(r"TCP (\S+):\d+ \(LISTEN\)", line)
        if match:
            addresses.append(match.group(1))
    return addresses


class WebStackIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mock = None
        cls.app = None

    def setUp(self) -> None:
        _ensure_build(self)
        if WebStackIntegrationTests.mock is None:
            WebStackIntegrationTests.mock = _MockControlApi().__enter__()
            WebStackIntegrationTests.app = _App(f"http://127.0.0.1:{self.mock.port}")
        self.mock = WebStackIntegrationTests.mock
        self.app = WebStackIntegrationTests.app

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.app is not None:
            cls.app.close()
        if cls.mock is not None:
            cls.mock.close()

    def _json(self, path: str) -> tuple[int, dict, float]:
        status, body, elapsed = self.app.get(path)
        return status, json.loads(body), elapsed

    def test_n01_sources_page_renders_unknown(self) -> None:
        sources = json.loads((FIXTURES / "sources.json").read_text())["sources"]
        status, body, _ = self.app.get("/")
        self.assertEqual(status, 200)
        for source in sources:
            self.assertIn(source["source_artifact_id"], body)
        self.assertIn('data-unknown="true"', body)
        self.assertGreaterEqual(body.count(">Unknown<"), 2)
        self.assertIn("admission does not probe", body)
        self.assertNotIn("NaN", body)
        self.assertIn("Local loopback pilot — private; not a hosted service.", body)

    def test_n02_running_job_preserves_null_progress(self) -> None:
        """Rescoped: a queued job with progress null keeps null (and eta null) through the BFF."""
        status, body, _ = self._json(f"/api/jobs/{JOB['queued']}")
        self.assertEqual(status, 200)
        self.assertEqual(body["state"], "queued")
        self.assertIn("progress", body)
        self.assertIsNone(body["progress"])
        self.assertIsNone(body["eta_seconds"])
        self.assertEqual(body["eta_seconds_reason"], "not estimated")

    def test_n03_progress_denominator_preserved(self) -> None:
        """Rescoped: lifecycle progress (k / 6) is preserved with its reason."""
        status, body, _ = self._json(f"/api/jobs/{JOB['running']}")
        self.assertEqual(status, 200)
        self.assertEqual(body["progress"], {"completed": 4, "denominator": 6, "unit": "lifecycle_steps"})
        self.assertIn("not an encode fraction", body["progress_reason"])

    def test_n04_job_page_ssr(self) -> None:
        """Rescoped: SSR state, the unknowns block and the compare note (or Prototype label when absent)."""
        succeeded = json.loads((FIXTURES / "job_succeeded.json").read_text())
        status, body, _ = self.app.get(f"/jobs/{JOB['succeeded']}")
        self.assertEqual(status, 200)
        self.assertIn('data-job-state="succeeded"', body)
        self.assertIn(succeeded["created_at"], body)
        self.assertIn(succeeded["updated_at"], body)
        self.assertIn("6 / 6 lifecycle steps", body)
        self.assertIn('data-unknowns-block="true"', body)
        self.assertIn('data-compare="bound"', body)
        self.assertIn("Levels are not matched by this page.", body)
        self.assertIn("~32 Hz low-string preservation not measured", body)
        self.assertIn('data-level-matched="false"', body)
        self.assertIn("private (contains host paths)", body)
        share = next(a for a in succeeded["artifacts"] if a["role"] == "share_mp4")
        self.assertIn(f'href="/api/artifacts/{share["artifact_id"]}"', body)
        status, body, _ = self.app.get(f"/jobs/{JOB['queued']}")
        self.assertEqual(status, 200)
        self.assertIn('data-progress="unknown"', body)
        self.assertIn('data-eta="unknown"', body)
        status, body, _ = self.app.get(f"/jobs/{JOB['failed']}")
        self.assertIn('data-compare="absent"', body)
        self.assertIn("Comparison data absent", body)
        # invalid id via the param matcher: 404 without any upstream request
        before = len(self.mock.requests)
        for path in ("/jobs/a%20b", "/jobs/job_running", "/sources/not-an-id"):
            status, _, _ = self.app.get(path)
            self.assertEqual(status, 404, path)
        self.assertEqual(len(self.mock.requests), before)

    def test_n05_decode_errors_do_not_echo_upstream(self) -> None:
        for job in (JOB["bad_unknown_key"], JOB["bad_enum"]):
            with self.subTest(job=job):
                status, body, _ = self.app.get(f"/api/jobs/{job}")
                self.assertEqual(status, 502)
                parsed = json.loads(body)
                self.assertEqual(parsed["code"], "control_api_decode_error")
                self.assertEqual(set(parsed), ERROR_KEYS)
                self.assertNotIn(UPSTREAM_MARKER, body)
                self.assertNotIn(UPSTREAM_KEY_MARKER, body)

    def test_n06_upstream_500(self) -> None:
        status, body, _ = self.app.get(f"/api/jobs/{JOB['http_500']}")
        self.assertEqual(status, 502)
        parsed = json.loads(body)
        self.assertEqual(parsed["code"], "control_api_http_error")
        self.assertEqual(parsed["upstream_status"], 500)
        self.assertNotIn(UPSTREAM_MARKER, body)

    def test_n07_upstream_404(self) -> None:
        status, body, _ = self._json(f"/api/jobs/{JOB['missing']}")
        self.assertEqual(status, 404)
        self.assertEqual(body["code"], "job_not_found")
        status, page, _ = self.app.get(f"/jobs/{JOB['missing']}")
        self.assertEqual(status, 404)
        self.assertNotIn(UPSTREAM_MARKER, page)

    def test_n08_timeout(self) -> None:
        status, body, elapsed = self._json(f"/api/jobs/{JOB['slow']}")
        self.assertEqual(status, 504)
        self.assertEqual(body["code"], "control_api_timeout")
        self.assertLess(elapsed, 6.5)

    def test_n09_too_large(self) -> None:
        for job in (JOB["huge"], JOB["huge_stream"]):
            with self.subTest(job=job):
                status, body, _ = self._json(f"/api/jobs/{job}")
                self.assertEqual(status, 502)
                self.assertEqual(body["code"], "control_api_too_large")

    def test_n10_invalid_job_id_no_upstream_call(self) -> None:
        before = len(self.mock.requests)
        for path in ("/api/jobs/..%2Fetc", "/api/jobs/a%20b", "/api/jobs/job_running", "/api/jobs/JOB_" + "0" * 32):
            with self.subTest(path=path):
                status, body, _ = self._json(path)
                self.assertEqual(status, 400)
                self.assertEqual(body["code"], "invalid_job_id")
        self.assertEqual(len(self.mock.requests), before)

    def test_n11_unconfigured(self) -> None:
        app = _App(None)
        try:
            status, body, _ = app.get("/")
            self.assertEqual(status, 200)
            self.assertIn("control_api_unconfigured", body)
            status, body, _ = app.get(f"/api/jobs/{JOB['queued']}")
            self.assertEqual(status, 503)
            self.assertEqual(json.loads(body)["code"], "control_api_unconfigured")
        finally:
            app.close()

    def test_n12_refused_hosts(self) -> None:
        """Rescoped: /upload is a bound page that renders the typed config refusal."""
        for url in ("http://192.0.2.1:9", "http://localhost:9"):
            with self.subTest(url=url):
                app = _App(url)
                try:
                    status, body, elapsed = app.get(f"/api/jobs/{JOB['running']}")
                    self.assertEqual(status, 503)
                    self.assertEqual(json.loads(body)["code"], "control_api_refused_host")
                    self.assertLess(elapsed, 1.0)
                    status, body, _ = app.get("/upload")
                    self.assertEqual(status, 200)
                    self.assertIn("control_api_refused_host", body)
                    self.assertIn('data-upload-form="true"', body)
                finally:
                    app.close()

    def test_n13_listeners_loopback_only(self) -> None:
        """Optional M11 socket check; skips (listen_address_verified: null) without lsof."""
        for label, pid in (("app", self.app.proc.pid), ("mock", os.getpid())):
            with self.subTest(process=label):
                addresses = _listen_addresses(pid)
                if addresses is None:
                    self.skipTest("lsof not available; listen_address_verified: null")
                self.assertGreater(len(addresses), 0)
                for address in addresses:
                    self.assertIn(address, {"127.0.0.1", "[::1]"})


    def test_n14_upload_refusal_code_mapping(self) -> None:
        before = len(self.mock.requests)
        status, _, payload, _ = self.app.request("POST", "/api/uploads", b"notes", {
            "content-type": "application/octet-stream", "origin": self.app.origin})
        body = json.loads(payload)
        self.assertEqual((status, body["code"]), (415, "bff_content_type_refused"))
        self.assertEqual(len(self.mock.requests), before)
        status, _, payload, _ = self.app.request("POST", "/api/uploads", b"\x00\x00\x00\x14ftypqt  " + b"\x00" * 64, {
            "content-type": "video/quicktime", "origin": self.app.origin, "x-upload-label": "synthetic"})
        body = json.loads(payload)
        self.assertEqual(status, 415)
        self.assertEqual(set(body), ERROR_KEYS)
        self.assertEqual((body["code"], body["upstream_code"], body["upstream_status"]),
                         ("control_api_refused", "upload_type_refused", 415))
        self.assertNotIn(UPSTREAM_MARKER.encode(), payload)
        self.assertNotIn(b"/Users/", payload)
        status, body = self.app.post_json("/api/sources", {"selector": "/abs/take.mov"})
        self.assertEqual((status, body["upstream_code"], body["upstream_detail_code"]),
                         (422, "path_escape", "host_path_refused"))

    def test_n15_cross_origin_post_refused_without_upstream_call(self) -> None:
        before = len(self.mock.requests)
        cases = [("/api/jobs", {"source_artifact_id": ART_OK, "parameters": {}, "idempotency_key": "ui-" + "0" * 32}),
                 (f"/api/jobs/{JOB['running']}/cancel", {}), ("/api/sources", {"selector": "RUN/x.mov"}),
                 (f"/api/sources/{ART_OK}/annotations", {})]
        for path, value in cases:
            for origin in ("http://evil.example", None):
                with self.subTest(path=path, origin=origin):
                    status, body = self.app.post_json(path, value, origin=origin)
                    self.assertEqual((status, body["code"]), (403, "bff_cross_origin_refused"))
        for method, path in (("GET", "/api/sources"), ("POST", "/api/jobs")):
            with self.subTest(host_rebinding=path):
                status, _, payload, _ = self.app.request(method, path, b"{}", {
                    "host": f"rebind.example:{self.app.port}", "origin": f"http://rebind.example:{self.app.port}",
                    "content-type": "application/json"})
                self.assertEqual((status, json.loads(payload)["code"]), (421, "bff_host_refused"))
        self.assertEqual(len(self.mock.requests), before)

    def test_n16_invalid_artifact_id_no_upstream_call(self) -> None:
        before = len(self.mock.requests)
        for path, code in (("/api/artifacts/art_x", "invalid_artifact_id"),
                           ("/api/artifacts/..%2Fjobs.sqlite3", "invalid_artifact_id"),
                           ("/api/artifacts/ART_" + "a" * 32, "invalid_artifact_id"),
                           ("/api/sources/x/media", "invalid_source_id"),
                           ("/api/sources/x/jobs", "invalid_source_id")):
            with self.subTest(path=path):
                status, body, _ = self._json(path)
                self.assertEqual((status, body["code"]), (400, code))
        self.assertEqual(len(self.mock.requests), before)

    def test_n17_download_pass_through_headers(self) -> None:
        status, headers, payload, _ = self.app.request("GET", f"/api/artifacts/{ART_OK}")
        self.assertEqual(status, 200)
        self.assertEqual(payload, ART_BYTES)
        self.assertEqual(headers["content-type"], "video/mp4")
        self.assertEqual(headers["content-length"], str(len(ART_BYTES)))
        self.assertEqual(headers["x-artifact-sha256"], hashlib.sha256(ART_BYTES).hexdigest())
        self.assertEqual(headers["content-disposition"], f'attachment; filename="{ART_OK}"')
        self.assertEqual(headers["cache-control"], "no-store")
        status, _, payload, _ = self.app.request("GET", f"/api/artifacts/{ART_PRIVATE}")
        body = json.loads(payload)
        self.assertEqual((status, body["code"], body["upstream_code"]), (403, "control_api_refused", "artifact_private"))
        self.assertNotIn(UPSTREAM_MARKER.encode(), payload)

    def test_n18_upstream_401_token_refused(self) -> None:
        status, body, _ = self._json(f"/api/jobs/{JOB['token_refused']}")
        self.assertEqual((status, body["code"], body["upstream_status"]), (502, "control_api_token_refused", 401))
        self.assertNotIn(TOKEN, json.dumps(body))
        seen = {value for value in self.mock.authorizations if value}
        self.assertEqual(seen, {f"Bearer {TOKEN}"})
        app = _App(f"http://127.0.0.1:{self.mock.port}", token=None)
        try:
            status, body, _ = app.get(f"/api/jobs/{JOB['queued']}")
            self.assertEqual((status, json.loads(body)["code"]), (503, "control_api_unauthenticated"))
        finally:
            app.close()


if __name__ == "__main__":
    unittest.main()
