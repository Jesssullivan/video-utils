"""Rebuild a truncated .mov (no moov atom) with untrunc and a healthy reference recording.

The reference must be a long recording from the same device and app, so its encoder settings match.
A 41 MB reference rebuilt 27% of a 977 MB file. A 4.9 GB reference from the same session rebuilt all of it.
"""

import re
import subprocess
import sys
from pathlib import Path

from .config import TIMEOUT_S


def recover(ref, broken, fixed):
    # -n: never prompt. -s: step over unknown byte runs. untrunc exits 1 even on a full rebuild,
    # so the verdict comes from its "Found N packets" and "Duration" lines and from the output size.
    p = subprocess.run(
        ["untrunc", "-n", "-s", "-dst", fixed, ref, broken],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=TIMEOUT_S,
    )
    log = p.stdout + p.stderr
    Path(f"{fixed}.untrunc.log").write_text(log)
    found = re.search(r"Found (\d+) packets", log)
    for line in re.findall(r"Info: (Found .*|Duration of .*)", log):
        print(line)
    if not found or not Path(fixed).exists():
        sys.exit(f"untrunc rebuilt nothing (exit {p.returncode}); see {fixed}.untrunc.log")
    share = Path(fixed).stat().st_size / Path(broken).stat().st_size
    print(f"{fixed}: {share:.0%} of the broken file's bytes")
    if share < 0.9:
        sys.exit("most of the file did not match the reference: use a longer recording from the same device and app")
