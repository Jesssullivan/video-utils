#!/usr/bin/env python3
"""Bounded Bazel launcher behind just/bazel.just.

    python3 tools/bazel/run.py [--timeout SECONDS] [--keep-server] <bazel arguments...>

- uses `bazelisk` when it is on PATH, otherwise `bazel` (the version comes from
  .bazelversion either way);
- refuses remote cache, remote executor and build-event-service flags: this
  repository builds locally and never requires GloriousFlywheel;
- bounds the invocation with a wall-clock timeout (default 1800 s, or
  VIDEO_UTILS_BAZEL_TIMEOUT_S) and terminates the whole process group on expiry;
- shuts the per-workspace Bazel server down afterwards unless --keep-server or
  VIDEO_UTILS_BAZEL_KEEP_SERVER=1, so no helper process outlives the recipe.

Stdlib only. Exit status: Bazel's own, 124 on timeout, 127 when neither launcher
is installed, 2 for a refused flag or bad usage.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TIMEOUT_S = 1800
SHUTDOWN_TIMEOUT_S = 60
REFUSED_PREFIXES = ("--remote_cache", "--remote_executor", "--bes_backend", "--experimental_remote_downloader")
EXIT_TIMEOUT = 124
EXIT_MISSING = 127
EXIT_USAGE = 2


def refused_flags(arguments: list[str]) -> list[str]:
    """Returns the arguments that would attach a remote backend."""
    return [a for a in arguments if a.startswith(REFUSED_PREFIXES) and not a.endswith("=")]


def launcher() -> str | None:
    return shutil.which("bazelisk") or shutil.which("bazel")


def parse(argv: list[str]) -> tuple[int, bool, list[str]]:
    timeout = int(os.environ.get("VIDEO_UTILS_BAZEL_TIMEOUT_S", DEFAULT_TIMEOUT_S))
    keep = os.environ.get("VIDEO_UTILS_BAZEL_KEEP_SERVER") == "1"
    rest = list(argv)
    while rest and rest[0] in ("--timeout", "--keep-server"):
        flag = rest.pop(0)
        if flag == "--keep-server":
            keep = True
        elif not rest:
            raise ValueError("--timeout needs a value in seconds")
        else:
            timeout = int(rest.pop(0))
    if timeout <= 0:
        raise ValueError("timeout must be a positive number of seconds")
    if not rest:
        raise ValueError("no Bazel command given")
    return timeout, keep, rest


def run_bounded(command: list[str], timeout: int) -> int:
    process = subprocess.Popen(command, cwd=ROOT, start_new_session=True)
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"run.py: {command[1]} exceeded {timeout} s; terminating", file=sys.stderr)
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                break
            try:
                process.wait(timeout=15)
                break
            except subprocess.TimeoutExpired:
                continue
        return EXIT_TIMEOUT
    except KeyboardInterrupt:
        try:
            os.killpg(process.pid, signal.SIGINT)
        except ProcessLookupError:
            pass
        process.wait(timeout=30)
        return 130


def main(argv: list[str]) -> int:
    try:
        timeout, keep, arguments = parse(argv)
    except ValueError as error:
        print(f"run.py: {error}", file=sys.stderr)
        return EXIT_USAGE
    refused = refused_flags(arguments)
    if refused:
        print(f"run.py: refused {refused}: this repository builds locally, without a remote backend",
              file=sys.stderr)
        return EXIT_USAGE
    binary = launcher()
    if binary is None:
        print("run.py: neither bazelisk nor bazel is on PATH", file=sys.stderr)
        return EXIT_MISSING
    status = run_bounded([binary, *arguments], timeout)
    if not keep and arguments[0] != "shutdown":
        try:
            subprocess.run([binary, "shutdown"], cwd=ROOT, timeout=SHUTDOWN_TIMEOUT_S, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            print("run.py: bazel shutdown did not finish in time", file=sys.stderr)
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
