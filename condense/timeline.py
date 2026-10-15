"""The Rust timeline (`video-utils timeline`, src/timeline.rs) is the authority on every EDL.

The edl stage validates each edl.json it writes. `Timeline` in edl.py answers the per-word time map in
process; tests/test_timeline_parity.py proves its answers equal the Rust ones.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

from .config import TIMEOUT_S

ROOT = Path(__file__).resolve().parents[1]


def binary():
    """VIDEO_UTILS_BIN, then this checkout's release or debug build, then PATH."""
    builds = (ROOT / "target/release/video-utils", ROOT / "target/debug/video-utils")
    for path in (os.environ.get("VIDEO_UTILS_BIN"), *builds):
        if path and Path(path).is_file():
            return str(path)
    found = shutil.which("video-utils")
    if not found:
        raise RuntimeError("no video-utils binary: run `just cli`, or set VIDEO_UTILS_BIN")
    return found


def call(*args, stdin=None):
    """Run one `video-utils timeline` command. Return its receipt, or raise with its typed reason."""
    p = subprocess.run(
        [binary(), "timeline", *map(str, args)], input=stdin, capture_output=True, text=True, timeout=TIMEOUT_S
    )
    if p.returncode not in (0, 1):
        raise RuntimeError(f"video-utils timeline {args[0]}: {p.stderr.strip()}")
    receipt = json.loads(p.stdout)
    if p.returncode:
        raise ValueError(f"edl rejected: {receipt['reason']}: {receipt['detail']}")
    return receipt


def validate(path):
    """The validate receipt: fps, clips, segments, total frames and seconds, the largest drift, the sha256."""
    return call("validate", path)


def answer(path, queries):
    """One batch of to_out, to_src and row queries against an edl.json."""
    return call("map", path, "-", stdin=json.dumps({"queries": queries}))["results"]


def quantise(segs, fps):
    """The Rust frame quantisation of one clip's segments."""
    return call("quantise", "--fps", fps, "-", stdin=json.dumps({"segments": segs}))["segments"]
