"""Diagnostic: split the joined offset into picture (frames from expected) and sound (ms from expected)."""
import json, sys
from pathlib import Path
import numpy as np
from condense import avsync
from condense.avsync import gray, pcm, match, SR, video_filter, parts
from condense.config import Config
r = Path(sys.argv[1]); cfg = Config(r / "talk.toml"); fps = cfg.fps
if len(sys.argv) > 2: cfg.out = Path(sys.argv[2])
edl = json.loads(cfg.f("edl", "json").read_text())
names = [(cfg.f(n, "mezz.mkv"), sum(s["frames"] for s in segs)) for n, _, segs in parts(edl)]
starts = np.cumsum([0] + [n for _, n in names]); total = int(starts[-1])
for i in range(12):
    j = int(total * (i + 0.5) / 12); p = int(np.searchsorted(starts, j, side="right")) - 1
    part, n = names[p]; local = min(max(j - int(starts[p]), 15), n - 45); j = int(starts[p]) + local
    k0 = local - 12
    edit, source = gray(cfg.out, j, 5, fps), gray(part, k0, 29, fps, video_filter(cfg) + ",")
    miss = np.array([((edit - source[k:k+5]) ** 2).mean() for k in range(len(source) - 4)])
    order = np.argsort(miss)
    x = pcm(cfg.out, j * SR // fps, 19200); c0 = local * SR // fps - 12000
    y = pcm(part, c0, len(x) + 24000); corr = match(y, x - x.mean())
    heard = (c0 + int(np.argmax(corr))) / SR
    print(f"{j/fps:8.2f} part {p:2d} local {local:5d}: picture {order[0]+k0-local:+d} fr (next {order[1]+k0-local:+d}, ratio {miss[order[1]]/(miss[order[0]]+1e-9):.2f}), sound {(heard-local/fps)*1000:+.1f} ms")
