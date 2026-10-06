#!/usr/bin/env python3
"""Preview an actual run with an owned isolated Chrome profile and muted playback."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from review_server import ReviewHTTPServer, Session


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
            browser.wait(timeout=3)
        except subprocess.TimeoutExpired:
            browser.kill()
            browser.wait(timeout=3)
        receipt["result"] = "owned_browser_terminated"
    else:
        receipt["result"] = "owned_browser_closed"
    receipt["exit_code"] = browser.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--chrome", type=Path, default=Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
    parser.add_argument("--startup-timeout", type=int, default=45)
    parser.add_argument("--annotation-smoke", action="store_true", help="Exercise note save/edit only in a synthetic-named fixture")
    args = parser.parse_args()
    if not 1 <= args.startup_timeout <= 60:
        parser.error("startup timeout must be between 1 and 60 seconds")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    session = Session(args.run_dir)
    if args.annotation_smoke and not session.data()["source_name"].startswith("synthetic-"):
        session.close()
        parser.error("annotation smoke requires a synthetic-named fixture; actual take notes are preserved")
    server = ReviewHTTPServer(session, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval":.1}, daemon=True)
    thread.start()
    browser = None
    receipt = {"actor":"review-lane", "ruling":"R-N11; R-HOOK-CONVERGENCE-20261004", "reason":"bounded isolated graphical review verification"}
    try:
        with tempfile.TemporaryDirectory(prefix="review-owned-profile-", dir=output) as temporary:
            profile = Path(temporary)
            try:
                with (output / "chrome.log").open("wb") as log:
                    browser = subprocess.Popen([str(args.chrome), "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--disable-background-networking", "--disable-component-update", "--enable-logging=stderr", "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0", f"--user-data-dir={profile}", "about:blank"], stdout=log, stderr=log)
                    receipt.update(target_pid=browser.pid, ownership="spawned_by_this_check_unique_temporary_profile", prior_state="new_owned_process")
                    deadline = time.monotonic()+args.startup_timeout
                    endpoint = profile / "DevToolsActivePort"
                    while not endpoint.exists() and time.monotonic()<deadline and browser.poll() is None:
                        time.sleep(.1)
                    if not endpoint.exists():
                        raise RuntimeError("Owned Chrome did not expose its debugging port")
                    port = endpoint.read_text().splitlines()[0]
                    command = ["node", str(Path(__file__).with_suffix(".mjs")), port, f"http://127.0.0.1:{server.server_port}", str(output / "review-preview.png")]
                    if args.annotation_smoke:
                        command.append("synthetic-annotation")
                    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
                    if result.returncode:
                        raise RuntimeError("Browser verification failed: "+result.stderr[-1000:])
                    evidence = json.loads(result.stdout)
                    (output / "browser-evidence.json").write_text(json.dumps(evidence,indent=2)+"\n")
                    print(json.dumps(evidence),flush=True)
            finally:
                stop_owned_browser(browser, profile, receipt)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
        session.close()
        (output / "cleanup-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")


if __name__ == "__main__":
    main()
