"""Run only the final join and encode of a talk.toml whose parts are rendered: python final_only.py <worktree> <toml>"""
import json
import sys
import time

sys.path.insert(0, sys.argv[1])
from condense import render  # noqa: E402
from condense.config import Config  # noqa: E402

cfg = Config(sys.argv[2])
t = time.monotonic()
render.final(cfg, json.loads(cfg.f("edl", "json").read_text()))
print(json.dumps(dict(preset=cfg.encode["preset"], wall_s=round(time.monotonic() - t, 1), bytes=cfg.out.stat().st_size)))
