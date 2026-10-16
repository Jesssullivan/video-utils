"""SSIM of each encode against the lossless parts through the same delivery filter: ssim.py <worktree> <toml> <mp4>..."""
import json
import re
import sys

sys.path.insert(0, sys.argv[1])
from condense import render  # noqa: E402
from condense.config import FF, Config, run  # noqa: E402

cfg = Config(sys.argv[2])
edl = json.loads(cfg.f("edl", "json").read_text())
for mp4 in sys.argv[3:]:
    inputs, graph = render.joined(cfg, [n for n, _, _ in render.parts(edl)])
    k = len(inputs) // 2
    graph += f";[a0]anullsink;[v]{render.video_filter(cfg)}[ref];[{k}:v]setpts=N/({cfg.fps}*TB)[enc];[enc][ref]ssim"
    log = run(*FF, *inputs, "-i", mp4, "-filter_complex", graph, "-f", "null", "-", cwd=cfg.work).stderr
    print(json.dumps(dict(file=mp4.rsplit("/", 1)[-1], ssim=re.findall(r"SSIM .*All:([\d.]+) \(([\d.]+)\)", log)[-1])))
