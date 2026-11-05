"""Diagnostic: which file's seek misreads? Compare seek-read frames with decode-order frames, file by file."""
import json, sys
from pathlib import Path
import numpy as np
from condense.avsync import raw, gray, video_filter, parts
from condense.config import Config
r = Path(sys.argv[1]); cfg = Config(r / "talk.toml"); fps = cfg.fps
edl = json.loads(cfg.f("edl", "json").read_text())
names = [(cfg.f(n, "mezz.mkv"), sum(s["frames"] for s in segs)) for n, _, segs in parts(edl)]
starts = np.cumsum([0] + [n for _, n in names])
def seq(path, first, count, chain=""):
    sel = f"select='between(n\\,{first}\\,{first + count - 1})',{chain}scale=64:36,format=gray"
    return raw(np.uint8, "-i", path, "-an", "-vf", sel, "-fps_mode", "passthrough", "-frames:v", count, "-f", "rawvideo").reshape(-1, 36, 64).astype(float)
def shift(a, b):
    m = {d: ((a[2:7] - b[2 + d:7 + d]) ** 2).mean() for d in (-2, -1, 0, 1, 2)}
    return min(m, key=m.get)
for t in map(float, sys.argv[2:]):
    j = round(t * fps); p = int(np.searchsorted(starts, j, side="right")) - 1
    part, n = names[p]; local = j - int(starts[p])
    out = shift(seq(cfg.out, j - 2, 9), gray(cfg.out, j - 2, 9, fps))
    prt = shift(seq(part, local - 2, 9, video_filter(cfg) + ","), gray(part, local - 2, 9, fps, video_filter(cfg) + ","))
    print(f"{t:8.2f}: delivered seek vs decode {out:+d} fr, part seek vs decode {prt:+d} fr")
