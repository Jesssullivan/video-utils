#!/usr/bin/env python3
"""S2 practice walkthrough in an owned headless Chrome with muted playback.

The review server runs in-process on an ephemeral loopback port. Its handler is
a subclass that wires ``practice_s2_routes`` exactly as the requested root diff
(``review/practice_s2_review_server.diff``) does. Chrome runs on a unique
temporary profile; only that PID is stopped, after its profile argument is
verified. Saves happen only for a ``synthetic-`` fixture.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import unquote, urlsplit

REVIEW = Path(__file__).resolve().parent
ROOT = REVIEW.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(REVIEW))
from review_server import ASSETS, Handler, Media, ReviewError, ReviewHTTPServer, Session  # noqa: E402
import practice_s2_routes  # noqa: E402

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


class PracticeS2Handler(Handler):
    """Mirror of the requested review_server.py routes for S2 (read-only)."""

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if path not in (practice_s2_routes.API_PATH, practice_s2_routes.ASSET) and not path.startswith(practice_s2_routes.MEDIA_PREFIX):
            return super().do_GET()
        try:
            self.trusted_request()
            if path == practice_s2_routes.API_PATH:
                status, value = practice_s2_routes.api_response(self.server.practice_s2)
                self.json_response(value, status)
            elif path == practice_s2_routes.ASSET:
                body = (ASSETS / "practice_s2.js").read_bytes()
                self.send_headers(200, "text/javascript; charset=utf-8", len(body))
                if self.command != "HEAD":
                    self.wfile.write(body)
            else:
                media = practice_s2_routes.media_for(self.server.practice_s2, path[len(practice_s2_routes.MEDIA_PREFIX):])
                if media is None:
                    raise ReviewError("route_not_found", 404)
                self.send_media(media)
        except ReviewError as error:
            self.json_response({"error": error.code}, error.status)
        except (BrokenPipeError, ConnectionResetError):
            pass


class PracticeS2Server(ReviewHTTPServer):
    def __init__(self, session, port=0, practice_s2=None):
        self.practice_s2 = practice_s2
        super().__init__(session, port)
        self.RequestHandlerClass = PracticeS2Handler


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stop_owned_browser(browser, profile, receipt):
    if browser is None:
        return
    if browser.poll() is None:
        arguments = subprocess.run(["ps", "-p", str(browser.pid), "-o", "args="], capture_output=True, text=True, timeout=2).stdout
        receipt["live_unique_profile_verified"] = f"--user-data-dir={profile}" in arguments
        if not receipt["live_unique_profile_verified"]:
            raise RuntimeError("Owned Chrome identity changed; no process was signalled")
        browser.terminate()
        try:
            browser.wait(timeout=5)
        except subprocess.TimeoutExpired:
            browser.kill()
            browser.wait(timeout=5)
        receipt["result"] = "owned_browser_terminated"
    else:
        receipt["result"] = "owned_browser_closed"
    receipt["exit_code"] = browser.returncode


def phrase_anchor_acceptance(run_dir):
    import importlib.util
    spec = importlib.util.spec_from_file_location("phrase_anchor_walkthrough", ROOT / "scripts" / "phrase_anchor.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    store = json.loads((Path(run_dir) / "review-annotations-v2.json").read_text())
    _, accepted, excluded = module.marks_from_annotation_store(store)
    return {"accepted": len(accepted), "excluded": excluded, "store_revision": store["revision"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("bundle_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--mode", choices=("synthetic", "real"), required=True)
    parser.add_argument("--chrome", type=Path, default=CHROME)
    parser.add_argument("--startup-timeout", type=int, default=45)
    parser.add_argument("--walkthrough-timeout", type=int, default=300)
    parser.add_argument("--protect", type=Path, nargs="*", default=[], help="Files hashed before and after (must stay unchanged)")
    args = parser.parse_args()
    if not 1 <= args.startup_timeout <= 60 or not 10 <= args.walkthrough_timeout <= 600:
        parser.error("timeouts out of range")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    receipt = {"actor": "ui_core-lane", "ruling": "R-N11; R-HOOK-CONVERGENCE-20261004", "mode": args.mode,
               "reason": "bounded isolated graphical walkthrough of the S2 practice page"}
    if not args.chrome.is_file():
        receipt["status"] = f"skipped: chrome_not_found {args.chrome}"
        (output / "cleanup-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt))
        return 0
    protected_before = {str(path): sha256(path) for path in args.protect}
    session = Session(args.run_dir)
    if args.mode == "synthetic" and not session.data()["source_name"].startswith("synthetic-"):
        session.close()
        parser.error("synthetic mode requires a synthetic-named fixture; real-take notes are never written")
    practice = practice_s2_routes.load(args.bundle_dir, session, Media)
    server = PracticeS2Server(session, 0, practice)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .1}, daemon=True)
    thread.start()
    browser = None
    evidence = None
    try:
        with tempfile.TemporaryDirectory(prefix="review-s2-owned-profile-", dir=output) as temporary:
            profile = Path(temporary)
            try:
                with (output / "chrome.log").open("wb") as log:
                    browser = subprocess.Popen([str(args.chrome), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                                                "--disable-extensions", "--disable-background-networking", "--disable-component-update",
                                                "--mute-audio", "--autoplay-policy=user-gesture-required",
                                                "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
                                                f"--user-data-dir={profile}", "about:blank"], stdout=log, stderr=log)
                    receipt.update(target_pid=browser.pid, ownership="spawned_by_this_check_unique_temporary_profile", prior_state="new_owned_process")
                    deadline = time.monotonic() + args.startup_timeout
                    endpoint = profile / "DevToolsActivePort"
                    while not endpoint.exists() and time.monotonic() < deadline and browser.poll() is None:
                        time.sleep(.1)
                    if not endpoint.exists():
                        raise RuntimeError("Owned Chrome did not expose its debugging port")
                    port = endpoint.read_text().splitlines()[0]
                    command = ["node", str(REVIEW / "browser_smoke_s2.mjs"), port, f"http://127.0.0.1:{server.server_port}", str(output), args.mode]
                    started = time.monotonic()
                    result = subprocess.run(command, capture_output=True, text=True, timeout=args.walkthrough_timeout)
                    receipt["walkthrough_seconds"] = round(time.monotonic() - started, 2)
                    if result.returncode:
                        raise RuntimeError("Browser walkthrough failed: " + result.stderr[-2000:])
                    evidence = json.loads(result.stdout)
            finally:
                stop_owned_browser(browser, profile, receipt)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
        practice_s2_routes.close(practice)
        session.close()
        receipt["protected_after_equal"] = {path: sha256(path) == digest for path, digest in protected_before.items()}
        (output / "cleanup-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    evidence["practice_s2_route"] = {"status": practice.status, "reason": practice.reason, "media_status": practice.media_status}
    if args.mode == "synthetic":
        evidence["phrase_anchor_acceptance"] = phrase_anchor_acceptance(args.run_dir)
    evidence["protected"] = {"count": len(protected_before), "unchanged": sum(receipt["protected_after_equal"].values())}
    (output / "browser-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({"status": "walkthrough_complete", "output": str(output), "configs": [item["name"] for item in evidence["configs"]]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
