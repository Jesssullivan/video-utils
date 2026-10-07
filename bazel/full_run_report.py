#!/usr/bin/env python3
"""Per-target and per-module record of one `bazel test //...` run (S3 bazel_full lane).

    python3 bazel/full_run_report.py --bep BEP.json --targets TARGETS.txt \
        [--testlogs DIR] --out REPORT.json

Inputs:
- the newline-delimited Build Event Protocol file written by
  `--build_event_json_file` (per-target overall status and attempt durations);
- the verbatim output of `bazel query 'tests(//...)'` (the denominator T);
- optionally the directory holding copies of each target's `test.log`
  (`<package>/<name>/test.log`), parsed for the stdlib unittest counts.

Every target in the denominator gets exactly one status. A target with no
test summary in the BEP file is reported `NO_STATUS` with the abort reason the
BEP file gives, never inferred as a pass. Unittest counts come only from a
parsed `Ran N tests` line; a log without one is `unparsed`.

Stdlib only; reads files, starts no process.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA = "vu.bazel_full.full_run_report.v1"
STATUSES = ("PASSED", "FAILED", "TIMEOUT", "FLAKY", "NO_STATUS", "SKIPPED", "INCOMPLETE", "REMOTE_FAILURE",
            "FAILED_TO_BUILD", "TOOL_HALTED_BEFORE_TESTING")
CASE_HEADER = re.compile(r"^(?P<method>\w+) \((?P<case>[\w.]+)\)")
RESULT = re.compile(r" \.\.\. (?P<result>ok|FAIL|ERROR|skipped(?: (?P<reason>.*))?|expected failure|unexpected success)$")
DETAIL = re.compile(r"^(?P<kind>ERROR|FAIL): (?P<method>\w+) \((?P<case>[\w.]+)\)")
RAN = re.compile(r"^Ran (\d+) tests? in ([0-9.]+)s$")
VERDICT = re.compile(r"^(OK|FAILED)(?: \((.*)\))?$")
SEPARATOR = re.compile(r"^(=+|-+)$")


def read_bep(path: Path) -> list[dict]:
    events = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{number}: not JSON: {error}") from error
    return events


def bep_statuses(events: list[dict]) -> dict[str, dict]:
    """label -> {status, attempts, duration_ms, aborted}; only labels the BEP file mentions."""
    found: dict[str, dict] = {}
    for event in events:
        identifier = event.get("id", {})
        if "testSummary" in identifier:
            label = identifier["testSummary"].get("label")
            summary = event.get("testSummary", {})
            entry = found.setdefault(label, {})
            entry["status"] = summary.get("overallStatus", "NO_STATUS")
            entry["attempts"] = summary.get("attemptCount", summary.get("totalRunCount"))
            entry["duration_ms"] = int(summary["totalRunDurationMillis"]) if "totalRunDurationMillis" in summary else None
        elif "testResult" in identifier:
            label = identifier["testResult"].get("label")
            result = event.get("testResult", {})
            entry = found.setdefault(label, {})
            entry.setdefault("results", []).append(result.get("status", "NO_STATUS"))
            if result.get("cachedLocally"):
                entry["cached"] = True
        elif "targetCompleted" in identifier and "aborted" in event:
            label = identifier["targetCompleted"].get("label")
            found.setdefault(label, {})["aborted"] = event["aborted"].get("reason", "UNKNOWN")
        elif "targetConfigured" in identifier and "aborted" in event:
            label = identifier["targetConfigured"].get("label")
            aborted = event["aborted"]
            found.setdefault(label, {})["aborted"] = f"{aborted.get('reason', 'UNKNOWN')}: {aborted.get('description', '')}".strip(": ")
        elif "targetCompleted" in identifier and event.get("completed", {}).get("success") is False:
            label = identifier["targetCompleted"].get("label")
            found.setdefault(label, {})["build_failed"] = True
    return found


def bep_summary(events: list[dict]) -> dict:
    summary = {"exit_code": None, "exit_name": None, "wall_ms": None, "command": None}
    for event in events:
        identifier = event.get("id", {})
        if "buildFinished" in identifier:
            finished = event.get("finished", {})
            summary["exit_code"] = finished.get("exitCode", {}).get("code", 0)
            summary["exit_name"] = finished.get("exitCode", {}).get("name")
        elif "buildMetrics" in identifier:
            timing = event.get("buildMetrics", {}).get("timingMetrics", {})
            if "wallTimeInMs" in timing:
                summary["wall_ms"] = int(timing["wallTimeInMs"])
        elif "started" in identifier:
            started = event.get("started", {})
            summary["command"] = started.get("command")
    return summary


def parse_unittest_log(text: str) -> dict:
    """Counts and failing cases from `python -m unittest -v` output (Python 3.12 format)."""
    cases: dict[str, str] = {}
    skip_reasons: dict[str, int] = {}
    pending: str | None = None
    for line in text.splitlines():
        header = CASE_HEADER.match(line)
        if header and not DETAIL.match(line):
            pending = f"{header.group('case')}"
        result = RESULT.search(line)
        if result and pending:
            outcome = result.group("result")
            if outcome.startswith("skipped"):
                reason = (result.group("reason") or "").strip()
                if len(reason) >= 2 and reason[0] == reason[-1] and reason[0] in "'\"":
                    reason = reason[1:-1]
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
                outcome = "skipped"
            cases[pending] = outcome
            pending = None
    details = parse_details(text)
    ran = verdict = None
    for line in text.splitlines():
        match = RAN.match(line.strip())
        if match:
            ran = int(match.group(1))
        match = VERDICT.match(line.strip())
        if match and ran is not None:
            verdict = {"verdict": match.group(1), "detail": match.group(2) or ""}
    counts = {key: 0 for key in ("failures", "errors", "skipped", "expected_failures", "unexpected_successes")}
    if verdict:
        for part in verdict["detail"].split(","):
            key, _, value = part.strip().partition("=")
            if key in counts and value.isdigit():
                counts[key] = int(value)
    return {
        "parsed": ran is not None and verdict is not None,
        "ran": ran,
        "verdict": verdict["verdict"] if verdict else None,
        **counts,
        "skip_reasons": dict(sorted(skip_reasons.items())),
        "failing_cases": details,
        "case_outcomes_seen": len(cases),
    }


def parse_details(text: str) -> list[dict]:
    """The `ERROR:`/`FAIL:` blocks: case id, kind and the last traceback line (verbatim)."""
    lines = text.splitlines()
    found = []
    index = 0
    while index < len(lines):
        match = DETAIL.match(lines[index])
        if not match:
            index += 1
            continue
        body = []
        index += 1
        while index < len(lines) and not DETAIL.match(lines[index]) and not RAN.match(lines[index].strip()):
            if not SEPARATOR.match(lines[index].strip()):
                body.append(lines[index])
            elif body and lines[index].startswith("="):
                break
            index += 1
        meaningful = [line for line in body if line.strip()]
        found.append({
            "case": match.group("case"),
            "kind": match.group("kind"),
            "first_error_line": first_error_line(meaningful),
        })
    return found


def first_error_line(body: list[str]) -> str:
    """The exception line of a traceback: the first unindented line after the last `Traceback` frame."""
    last_traceback = max((i for i, line in enumerate(body) if line.startswith("Traceback")), default=-1)
    for line in body[last_traceback + 1:]:
        if not line.startswith(" "):
            return line.strip()
    return body[-1].strip() if body else ""


def build_report(bep: Path, targets_file: Path, testlogs: Path | None) -> dict:
    events = read_bep(bep)
    statuses = bep_statuses(events)
    targets = [line.strip() for line in targets_file.read_text(encoding="utf-8").splitlines()
               if line.strip().startswith("//")]
    rows = []
    for label in targets:
        entry = statuses.get(label, {})
        status = entry.get("status", "NO_STATUS")
        row = {
            "target": label,
            "status": status,
            "attempts": entry.get("attempts"),
            "duration_ms": entry.get("duration_ms"),
            "cached": bool(entry.get("cached", False)),
        }
        if status == "NO_STATUS":
            row["reason"] = entry.get("aborted") or ("build failed" if entry.get("build_failed") else
                                                     "no test summary in the BEP file")
        if testlogs is not None and label.startswith("//"):
            package, _, name = label[2:].partition(":")
            log = testlogs / package / name / "test.log"
            if log.is_file():
                text = log.read_text(encoding="utf-8", errors="replace")
                if re.search(r"^Ran \d+ tests? in", text, re.MULTILINE):
                    row["unittest"] = parse_unittest_log(text)
                else:
                    row["unittest"] = {"parsed": False, "reason": "no unittest summary line (not a Python unittest log)"}
            else:
                row["unittest"] = {"parsed": False, "reason": "no test.log copied"}
        rows.append(row)
    counts = {status: 0 for status in STATUSES}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "schema": SCHEMA,
        "denominator_targets": len(targets),
        "status_counts": {key: value for key, value in counts.items() if value or key in STATUSES[:6]},
        "bep": bep_summary(events),
        "unlisted_bep_labels": sorted(label for label in statuses if label not in set(targets)
                                      and "status" in statuses[label]),
        "targets": rows,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bep", type=Path, required=True)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--testlogs", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args(argv)
    report = build_report(arguments.bep, arguments.targets, arguments.testlogs)
    arguments.out.write_text(json.dumps(report, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    print(json.dumps(report["status_counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
