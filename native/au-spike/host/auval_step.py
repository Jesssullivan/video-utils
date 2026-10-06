#!/usr/bin/env python3
"""Read-only AU discovery and targeted validator step (docs/spec/AU_AUVAL_STEP.md).

Stdlib only. Every subprocess uses an absolute tool path, stdin=DEVNULL, a new
session and an explicit timeout; a timeout kills only the identity-checked
process group this step started and is never retried. The step performs no
installation, copy, registration, election, cache reset, app launch or plugin
repair: installation and repairs are out of scope (AGENTS.md). A blocked
receipt is a valid result.

Exit codes: 0 receipt written (any stage outcome), 1 internal or receipt-write
error, 2 unsupported platform.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import time
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[3]
HOST = Path(__file__).resolve().parent
LANE = HOST.parent
SCHEMA = "vu.au_auval_step.v1"
AUTHORITY = "R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13; S2 20261006-s2 TIN-5612"
DEFAULT_OUT = ROOT / "artifacts/s2/au_auval"
DEFAULT_PACKAGING_RECEIPT = ROOT / ".cache/au-packaging/receipt.json"
AU_SPIKE_RECEIPT = ROOT / ".cache/au-spike/receipt.json"
HARNESS_SOURCE = HOST / "RegisteredRender.swift"
HARNESS_RELATIVE = "native/au-spike/host/RegisteredRender.swift"
TARGETS = LANE / "packaging/targets.json"

TOOL_PATHS = {"sw_vers": "/usr/bin/sw_vers", "uname": "/usr/bin/uname",
              "pluginkit": "/usr/bin/pluginkit", "auval": "/usr/bin/auval",
              "xcrun": "/usr/bin/xcrun"}
TIMEOUTS = {"sw_vers": 10, "uname": 10, "pluginkit": 30, "auval_list": 60,
            "swift_typecheck": 180, "auval_validate": 120, "swift_compile": 180,
            "render_run": 180}

DISCOVERY_VALUES = ("blocked_not_installed", "passed", "ambiguous_duplicates",
                    "ambiguous_partial", "error")
STATUS_VALUES = ("blocked_not_installed", "discovery_ambiguous", "discovery_error",
                 "validated", "validation_failed", "unsupported")
STAGE5_VALUES = ("not_performed", "passed", "failed", "timeout", "failed_artifact_mismatch")
BINDING_VALUES = ("matched", "mismatch", "unknown_no_packaging_receipt",
                  "unknown_path_not_reported")
TYPECHECK_VALUES = ("passed", "failed", "skipped")
NEXT_DECISION = ("operator-approved stage-1 installation (AU_HOST_ACCEPTANCE_LANE.md); "
                 "not requested by this lane")
CONTRACT_AMENDMENTS = [
    "A1: swiftc invocations add -module-cache-path <out>/swift-module-cache so compiler "
    "module-cache writes stay inside the out dir instead of a per-user default cache."]

RULE = re.compile(r"^-{10,}\s*$")
LISTING_TARGET = re.compile(r"^\s*aufx\s+vuGn\s+Jess\b")
LISTING_ROW = re.compile(r"^\s{0,4}[A-Za-z0-9]{4}\s+\S.{0,3}\s+\S.{0,3}\s+-\s+\S")
APPEX_PATH = re.compile(r"(/[^\t\n]*?\.appex)/?\s*$")


class CommandResult(NamedTuple):
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    seconds: float


def run_command(argv, timeout, cwd=None):
    """Run one bounded command; on timeout kill only the group this call made."""
    started = time.monotonic()
    process = subprocess.Popen([str(value) for value in argv], cwd=str(cwd or ROOT),
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, errors="replace",
                               start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return CommandResult(process.returncode, stdout, stderr, False,
                             round(time.monotonic() - started, 3))
    except subprocess.TimeoutExpired:
        if process.poll() is None:
            try:
                if os.getpgid(process.pid) == process.pid:
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
        stdout, stderr = process.communicate()
        return CommandResult(None, stdout or "", stderr or "", True,
                             round(time.monotonic() - started, 3))


def default_which(name):
    """Resolve a fixed absolute tool path without invoking anything."""
    path = TOOL_PATHS.get(name)
    if path and os.path.isfile(path) and os.access(path, os.X_OK):
        return path
    return None


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_target(path=TARGETS):
    targets = json.loads(Path(path).read_text())
    component = targets["component"]
    return {"bundle_id": targets["extension"]["identifier"],
            "extension_executable": targets["extension"]["executable"],
            "component": {"type": component["type"], "subtype": component["subtype"],
                          "manufacturer": component["manufacturer"]}}


def pluginkit_argv(bundle_id, pluginkit=TOOL_PATHS["pluginkit"]):
    # Stage-2 match form only: -m (match) with -A/-D/-v. No registry-changing flag.
    return [pluginkit, "-m", "-A", "-D", "-v", "-i", bundle_id]


# ---------------------------------------------------------------------------
# Pure parsers
# ---------------------------------------------------------------------------

def parse_pluginkit(text, bundle_id):
    """Match lines naming exactly `bundle_id`, and any .appex path they report."""
    pattern = re.compile(r"(?<![\w.-])" + re.escape(bundle_id) + r"(?![\w.-])")
    lines = [line.rstrip() for line in text.splitlines() if pattern.search(line)]
    paths = []
    for line in lines:
        match = APPEX_PATH.search(line)
        paths.append(match.group(1) if match else None)
    return {"match_lines": lines, "match_count": len(lines), "paths": paths}


def parse_auval_listing(text):
    """Rows matching exactly aufx/vuGn/Jess, and the total component row count."""
    lines = text.splitlines()
    targets = [line.rstrip() for line in lines if LISTING_TARGET.match(line)]
    rows = [line for line in lines if LISTING_ROW.match(line)]
    return {"target_lines": targets, "target_count": len(targets), "total_rows": len(rows)}


def _section_result(lines):
    stripped = [line.strip() for line in lines]
    failed = any("* * FAIL" in line or line.startswith(("FAIL", "ERROR:", "FATAL ERROR"))
                 for line in stripped)
    if failed:
        return "fail"
    if any("* * PASS" in line for line in stripped):
        return "pass"
    return "no_verdict"


def _is_summary(lines):
    """The closing chunk that carries the overall AU VALIDATION verdict."""
    return any(re.search(r"AU VALIDATION (SUCCEEDED|FAILED)", line) for line in lines)


def parse_auval_transcript(text):
    """Parse an `auval -v` transcript into per-section verdicts.

    Chunks are split on dashed rule lines. Text before the first rule is a
    preamble, the chunk carrying the overall AU VALIDATION verdict is a summary, and a
    chunk holding only a title line is merged as the title of the next chunk.
    Unknown and no-verdict results are never upgraded to a pass.
    """
    lines = text.splitlines()
    chunks, current, start, seen_rule = [], [], 1, False
    for number, line in enumerate(lines, start=1):
        if RULE.match(line):
            if seen_rule:
                chunks.append((start, number - 1, current))
            seen_rule, current, start = True, [], number + 1
        else:
            current.append(line)
    if seen_rule:
        chunks.append((start, len(lines), current))
    sections, pending_title = [], None
    for first, last, chunk in chunks:
        content = [(first + index, line) for index, line in enumerate(chunk) if line.strip()]
        if not content or _is_summary(chunk):
            continue
        if len(content) == 1 and _section_result(chunk) == "no_verdict" and pending_title is None:
            pending_title = (content[0][0], content[0][1].strip())
            continue
        title = pending_title[1] if pending_title else content[0][1].strip()
        span_start = pending_title[0] if pending_title else content[0][0]
        pending_title = None
        sections.append({"title": title, "result": _section_result(chunk),
                         "warnings": sum(1 for line in chunk if line.strip().startswith("WARNING")),
                         "line_span": [span_start, content[-1][0]]})
    if pending_title is not None:
        sections.append({"title": pending_title[1], "result": "no_verdict", "warnings": 0,
                         "line_span": [pending_title[0], pending_title[0]]})
    fatal = next((line.strip() for line in lines if "FATAL ERROR" in line), None)
    if fatal is not None:
        overall = "fatal"
    elif any("AU VALIDATION FAILED" in line for line in lines):
        overall = "failed"
    elif any("AU VALIDATION SUCCEEDED" in line for line in lines):
        overall = "passed"
    else:
        overall = "unknown"
    return {"overall": overall, "sections": sections, "section_count": len(sections),
            "pass_count": sum(section["result"] == "pass" for section in sections),
            "fail_count": sum(section["result"] == "fail" for section in sections),
            "no_verdict_count": sum(section["result"] == "no_verdict" for section in sections),
            "fatal_message": fatal,
            "transcript_sha256": sha256_bytes(text.encode("utf-8"))}


def decide_discovery(pluginkit_count, triple_count):
    if pluginkit_count >= 2 or triple_count >= 2:
        return "ambiguous_duplicates"
    if pluginkit_count == 0 and triple_count == 0:
        return "blocked_not_installed"
    if pluginkit_count == 1 and triple_count == 1:
        return "passed"
    return "ambiguous_partial"


# ---------------------------------------------------------------------------
# Step
# ---------------------------------------------------------------------------

class Step:
    def __init__(self, out_dir, packaging_receipt, runner, which, stamp):
        self.out = Path(out_dir).resolve()
        self.packaging_receipt = Path(packaging_receipt)
        self.runner = runner
        self.which = which
        self.stamp = stamp
        self.commands = []
        self.written = []

    def call(self, argv, timeout):
        argv = [str(value) for value in argv]
        result = self.runner(argv, timeout)
        self.commands.append({"argv": argv, "timeout_s": timeout, "exit_code": result.exit_code,
                              "timed_out": result.timed_out, "seconds": result.seconds})
        return result

    def save_raw(self, name, text):
        path = self.out / "raw" / f"{self.stamp}-{name}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        self.written.append(path)
        return path

    def query_summary(self, result, raw_name):
        raw = self.save_raw(raw_name, result.stdout)
        return {"exit_code": result.exit_code, "timed_out": result.timed_out,
                "stdout_sha256": sha256_bytes(result.stdout.encode("utf-8")),
                "stdout_line_count": len(result.stdout.splitlines()),
                "raw_output_path": str(raw.relative_to(self.out)),
                "stderr_tail": result.stderr[-400:] if result.exit_code or result.timed_out else ""}

    def typecheck(self):
        xcrun = self.which("xcrun")
        if xcrun is None:
            return {"status": "skipped", "reason": "xcrun not found at /usr/bin/xcrun; swiftc unresolved",
                    "seconds": 0.0}
        result = self.call([xcrun, "swiftc", "-typecheck", "-swift-version", "6",
                            "-module-cache-path", self.out / "swift-module-cache", HARNESS_RELATIVE],
                           TIMEOUTS["swift_typecheck"])
        self.written.append(self.out / "swift-module-cache")
        if result.timed_out:
            return {"status": "failed", "reason": "timeout after 180 s", "seconds": result.seconds}
        if result.exit_code != 0 and "unable to find utility" in result.stderr:
            return {"status": "skipped", "reason": "xcrun could not resolve swiftc",
                    "seconds": result.seconds}
        if result.exit_code != 0:
            return {"status": "failed", "reason": result.stderr[-800:], "seconds": result.seconds}
        return {"status": "passed", "reason": None, "seconds": result.seconds}

    def bind_artifact(self, appex_path, executable):
        """Hash the registered extension executable and compare to packaging."""
        if not appex_path:
            return "unknown_path_not_reported", None, None
        binary = Path(appex_path) / "Contents/MacOS" / executable
        try:
            observed = sha256_file(binary)
        except OSError as error:
            return "unknown_path_not_reported", None, f"unreadable: {error.strerror}"
        if not self.packaging_receipt.is_file():
            return "unknown_no_packaging_receipt", observed, None
        try:
            expected = json.loads(self.packaging_receipt.read_text())["binaries"]["extension"]["sha256"]
        except (OSError, ValueError, KeyError, TypeError):
            return "unknown_no_packaging_receipt", observed, "packaging receipt lacks extension sha256"
        return ("matched" if observed == expected else "mismatch"), observed, None

    def validate(self, binding, artifact_sha256):
        auval = self.which("auval")
        result = self.call([auval, "-v", "aufx", "vuGn", "Jess"], TIMEOUTS["auval_validate"])
        raw = self.save_raw("auval-validate", result.stdout + ("\n" + result.stderr if result.stderr else ""))
        parsed = parse_auval_transcript(result.stdout)
        if result.timed_out:
            status = "timeout"
        elif binding == "mismatch":
            status = "failed_artifact_mismatch"
        elif result.exit_code == 0 and parsed["overall"] == "passed":
            status = "passed"
        else:
            status = "failed"
        return {"status": status, "artifact_binding": binding, "artifact_sha256": artifact_sha256,
                "exit_code": result.exit_code, "timed_out": result.timed_out, "attempts": 1,
                "raw_transcript_path": str(raw.relative_to(self.out)), "parsed": parsed}

    def render(self):
        xcrun = self.which("xcrun")
        if xcrun is None:
            return {"status": "skipped", "reason": "xcrun/swiftc unavailable"}
        binary = self.out / "registered-render"
        compiled = self.call([xcrun, "swiftc", "-O", "-swift-version", "6", "-module-cache-path",
                              self.out / "swift-module-cache", HARNESS_RELATIVE, "-o", binary],
                             TIMEOUTS["swift_compile"])
        self.written.append(binary)
        if compiled.timed_out or compiled.exit_code != 0:
            return {"status": "compile_failed", "timed_out": compiled.timed_out,
                    "reason": compiled.stderr[-800:]}
        ran = self.call([binary], TIMEOUTS["render_run"])
        if ran.timed_out:
            return {"status": "timeout", "exit_code": None}
        try:
            harness = json.loads(ran.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return {"status": "failed", "exit_code": ran.exit_code, "reason": "no harness JSON"}
        harness["exit_code"] = ran.exit_code
        if ran.exit_code != 0 and harness.get("status") == "passed":
            harness["status"] = "failed"
        return harness

    def execute(self, system_name, now):
        target = load_target()
        receipt = base_receipt(target, now)
        if system_name != "Darwin":
            receipt["status"] = "unsupported"
            receipt["stage_2_discovery"] = "error"
            receipt["unsupported_reason"] = f"Darwin required; platform is {system_name}"
            return receipt
        self.out.mkdir(parents=True, exist_ok=True)
        os_version = self.call([self.which("sw_vers") or TOOL_PATHS["sw_vers"]], TIMEOUTS["sw_vers"])
        arch = self.call([self.which("uname") or TOOL_PATHS["uname"], "-m"], TIMEOUTS["uname"])
        fields = dict(re.findall(r"(?m)^(\w+):\s*(.+?)\s*$", os_version.stdout))
        receipt["host"] = {
            "os_version": (f"{fields.get('ProductVersion', 'unknown')} ({fields.get('BuildVersion', 'unknown')})"
                           if os_version.exit_code == 0 else "unknown"),
            "architecture": arch.stdout.strip() if arch.exit_code == 0 and arch.stdout.strip() else "unknown"}

        pluginkit_tool, auval_tool = self.which("pluginkit"), self.which("auval")
        discovery = {"pluginkit": None, "auval_list": None, "error": None}
        if pluginkit_tool is None or auval_tool is None:
            discovery["error"] = {"reason": "pluginkit or auval not found at fixed /usr/bin path"}
            decision = "error"
            pk = None
        else:
            pk_result = self.call(pluginkit_argv(target["bundle_id"], pluginkit_tool), TIMEOUTS["pluginkit"])
            pk = parse_pluginkit(pk_result.stdout, target["bundle_id"])
            discovery["pluginkit"] = {**self.query_summary(pk_result, "pluginkit"),
                                      "matching_lines": pk["match_lines"], "match_count": pk["match_count"],
                                      "reported_paths": pk["paths"]}
            list_result = self.call([auval_tool, "-a"], TIMEOUTS["auval_list"])
            listing = parse_auval_listing(list_result.stdout)
            discovery["auval_list"] = {**self.query_summary(list_result, "auval-list"),
                                       "matching_lines": listing["target_lines"],
                                       "target_count": listing["target_count"],
                                       "total_rows": listing["total_rows"]}
            failed = [(name, result) for name, result in (("pluginkit", pk_result), ("auval_list", list_result))
                      if result.timed_out or result.exit_code != 0]
            if failed:
                name, result = failed[0]
                decision = "error"
                discovery["error"] = {"command": name, "exit_code": result.exit_code,
                                      "timed_out": result.timed_out, "stderr_tail": result.stderr[-400:]}
            else:
                decision = decide_discovery(pk["match_count"], listing["target_count"])
        receipt["discovery"] = discovery
        receipt["stage_2_discovery"] = decision
        receipt["swift_typecheck"] = self.typecheck()

        if decision == "passed":
            binding, artifact_sha256, binding_note = self.bind_artifact(pk["paths"][0],
                                                                       target["extension_executable"])
            receipt["artifact_binding_note"] = binding_note
            receipt["stage_5_auval"] = self.validate(binding, artifact_sha256)
            receipt["stage_3_registered_render"] = self.render()
            mode = receipt["stage_3_registered_render"].get("observed_instantiation_mode")
            receipt["observed_instantiation_mode"] = mode if mode in ("in_process", "out_of_process") else "unknown"
            validated = (receipt["stage_5_auval"]["status"] == "passed" and binding == "matched"
                         and receipt["stage_3_registered_render"].get("status") == "passed")
            receipt["status"] = "validated" if validated else "validation_failed"
        else:
            receipt["status"] = {"blocked_not_installed": "blocked_not_installed",
                                 "error": "discovery_error"}.get(decision, "discovery_ambiguous")
            if decision == "blocked_not_installed":
                receipt["next_required_decision"] = NEXT_DECISION
        return receipt

    def finish(self, receipt):
        receipt["commands"] = self.commands
        outside = sorted(str(path) for path in self.written
                         if not Path(path).resolve().is_relative_to(self.out))
        receipt["mutations"]["writes_outside_out_dir"] = outside
        self.out.mkdir(parents=True, exist_ok=True)
        text = json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n"
        paths = [self.out / f"auval-step-{self.stamp}.json", self.out / "receipt.json"]
        for path in paths:
            pending = path.with_name("." + path.name + ".pending")
            pending.write_text(text)
            pending.replace(path)
        return paths


def base_receipt(target, now):
    stage0 = AU_SPIKE_RECEIPT.is_file()
    blocked = {"status": "not_performed", "blocked_by": "stage_2_discovery"}
    return {
        "schema": SCHEMA,
        "created_at": now.isoformat(),
        "authority": AUTHORITY,
        "host": {"os_version": "unknown", "architecture": "unknown"},
        "tool_paths": dict(TOOL_PATHS),
        "source_sha256": {str(path.relative_to(ROOT)): sha256_file(path)
                          for path in (Path(__file__).resolve(), HARNESS_SOURCE, TARGETS)},
        "target": {"bundle_id": target["bundle_id"], "component": target["component"]},
        "stage_0_local_checks": "see au-spike-check receipt" if stage0 else "unknown",
        "stage_0_receipt_sha256": sha256_file(AU_SPIKE_RECEIPT) if stage0 else "unknown",
        "stage_1_installation": "out_of_scope",
        "installation": "out_of_scope",
        "stage_2_discovery": "error",
        "discovery": None,
        "swift_typecheck": {"status": "skipped", "reason": "not reached", "seconds": 0.0},
        "stage_3_registered_render": dict(blocked),
        "observed_instantiation_mode": "unknown",
        "stage_4_parameters_state": "not_performed",
        "stage_5_auval": {**blocked, "artifact_binding": None, "artifact_sha256": None, "parsed": None},
        "logic_host_acceptance": "not_performed",
        "realtime_deadline": "unknown",
        "bypass": "not_performed",
        "state_recall": "not_performed",
        "listening": "not_performed",
        "audio_device_opened": False,
        "packaging_artifact_freshness": "stale_unknown",
        "os_managed_side_effects": "unknown",
        "mutations": {"files_copied": [], "registry_writes": [], "writes_outside_out_dir": []},
        "claim_classes": {"host": "H", "discovery": "H", "swift_typecheck": "M",
                          "stage_5_auval": "M when performed, else NP",
                          "stage_3_registered_render": "M when performed, else NP",
                          "realtime_deadline": "U", "observed_instantiation_mode": "U unless API-reported",
                          "logic_host_acceptance": "NP", "installation": "NP"},
        "contract_amendments": list(CONTRACT_AMENDMENTS),
        "commands": [],
        "status": "discovery_error",
    }


def run_step(out_dir=DEFAULT_OUT, packaging_receipt=DEFAULT_PACKAGING_RECEIPT, runner=run_command,
             which=default_which, system_name=None, now=None):
    """Run the step and write its receipt. Returns (receipt, exit_code, paths)."""
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    step = Step(out_dir, packaging_receipt, runner, which, stamp)
    receipt = step.execute(system_name or platform.system(), now)
    receipt.setdefault("commands", [])
    paths = step.finish(receipt)
    return receipt, (2 if receipt["status"] == "unsupported" else 0), paths


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--packaging-receipt", type=Path, default=DEFAULT_PACKAGING_RECEIPT)
    arguments = parser.parse_args(argv)
    try:
        receipt, code, paths = run_step(arguments.out, arguments.packaging_receipt)
    except Exception as error:  # noqa: BLE001 - report any internal failure as exit 1
        print(json.dumps({"status": "internal_error", "error": f"{type(error).__name__}: {error}"}),
              file=sys.stderr)
        return 1
    print(json.dumps({"status": receipt["status"], "stage_2_discovery": receipt["stage_2_discovery"],
                      "receipt": [str(path) for path in paths]}, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
