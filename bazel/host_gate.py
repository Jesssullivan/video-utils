#!/usr/bin/env python3
"""Host load gate before a heavy Bazel step (S3 bazel_full lane, contract section 6.4).

    python3 bazel/host_gate.py --step NAME --log GATE.jsonl [--max-load 24] [--wait-max-s 5400] [--interval-s 60]

Reads the 1-minute load average; while it exceeds --max-load, waits --interval-s
and reads it again, for at most --wait-max-s. Every reading is appended to the
JSON-lines log with UTC time, value, threshold and step. Run it as a background
job: it is the wait, so no foreground sleep is needed by the caller.

Exit status: 0 when the load is at or below the threshold, 3 when the step is
`blocked_on_host` (still above it after --wait-max-s), 2 for bad usage.
Stdlib only; starts no process.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

EXIT_OPEN = 0
EXIT_BLOCKED = 3


def reading(step: str, threshold: float, clock=time.time, load=os.getloadavg) -> dict:
    value = load()[0]
    return {
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(clock())),
        "step": step,
        "load1": round(value, 2),
        "threshold": threshold,
        "open": value <= threshold,
    }


def gate(step: str, log: Path, threshold: float, wait_max_s: float, interval_s: float,
         clock=time.time, load=os.getloadavg, pause=time.sleep) -> int:
    started = clock()
    while True:
        entry = reading(step, threshold, clock, load)
        entry["waited_s"] = round(clock() - started, 1)
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        if entry["open"]:
            return EXIT_OPEN
        if clock() - started + interval_s > wait_max_s:
            with log.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"step": step, "outcome": "blocked_on_host",
                                         "waited_s": round(clock() - started, 1)}, sort_keys=True) + "\n")
            return EXIT_BLOCKED
        pause(interval_s)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--step", required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--max-load", type=float, default=24.0)
    parser.add_argument("--wait-max-s", type=float, default=5400.0)
    parser.add_argument("--interval-s", type=float, default=60.0)
    arguments = parser.parse_args(argv)
    if arguments.max_load <= 0 or arguments.wait_max_s < 0 or arguments.interval_s <= 0:
        print("host_gate.py: thresholds must be positive", file=sys.stderr)
        return 2
    return gate(arguments.step, arguments.log, arguments.max_load, arguments.wait_max_s, arguments.interval_s)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
