"""Cue count and sha256 of the SRT and VTT a worktree's captions code builds for a run, without writing them.

usage: L11-captions-hash.py <run dir with talk.toml> <worktree>
Run once on main and once on the branch: equal lines mean the default style is byte-identical.
"""

import hashlib
import sys
from pathlib import Path

run, tree = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(tree))
from condense import captions  # noqa: E402
from condense.config import Config  # noqa: E402
from condense.edl import Timeline  # noqa: E402

cfg = Config(run / "talk.toml")
if hasattr(captions, "build"):
    found = captions.build(cfg)
else:  # main before TIN-6573
    r = cfg.rules
    found = captions.cues(captions.output_words(cfg, Timeline.load(cfg)), r["caption_chars"], r["caption_lines"])
srt, vtt = (hashlib.sha256(f(found).encode()).hexdigest() for f in (captions.srt, captions.vtt))
print(run.name, len(found), srt, vtt)
