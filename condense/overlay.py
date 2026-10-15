"""Burn "*correction" notes into the top right corner.

Each note sits at a source time: the moment the speaker says the wrong thing. The EDL maps it to the output
clock, and it shows for 3 s. A note that lands in a cut moves to the join. Notes never overlap: a later one
waits for the one before it.

This is its own pass, so the main render is not repeated. The video is encoded once more from the lossless
parts when they are still in the work directory, else from the finished file. The audio is copied.
"""

import json
import textwrap

from .config import FF, run
from .edl import Timeline
from .render import joined, parts, video_codec, video_filter


def placements(corrections, tl, hold=3.0):
    """[(start, end, text)] on the output clock, in order."""
    at = [(tl.to_out(c["clip"], c["source_s"], snap=True), c["text"]) for c in corrections]
    out, free = [], 0.0
    for t, text in sorted(x for x in at if x[0] is not None):
        start = max(t, free)
        free = start + hold
        out.append((round(start, 3), min(round(free, 3), tl.total), text if text.startswith("*") else "*" + text))
    return out


def drawtext(cfg, i, start, end, text):
    notes = cfg.work / "overlay"
    notes.mkdir(exist_ok=True)
    (notes / f"{i}.txt").write_text("\n".join(textwrap.wrap(text, 40)))
    font = f"fontfile={cfg.font}:" if cfg.font else ""
    return (
        f"drawtext={font}textfile=overlay/{i}.txt:expansion=none:fontsize=h/24:fontcolor=white:line_spacing=6"
        f":box=1:boxcolor=black@0.65:boxborderw=14:x=w-text_w-h/18:y=h/18:enable='between(t,{start},{end})'"
    )


def burn(cfg):
    edl = json.loads(cfg.f("edl", "json").read_text())
    notes = placements(cfg.corrections, Timeline.load(cfg), cfg.rules["overlay_s"])
    if not notes:
        print("no corrections to burn in")
        return
    draw = ",".join(drawtext(cfg, i, *n) for i, n in enumerate(notes))
    names = [name for name, _, _ in parts(edl)]
    if all(cfg.f(name, "mezz.mkv").exists() for name in names):
        inputs, graph = joined(cfg, names)
        graph += f";[a0]anullsink;[v]{video_filter(cfg)},{draw}[vo]"
    else:
        inputs, graph = ["-i", cfg.out], f"[0:v]{draw}[vo]"
    out = cfg.out.with_suffix(".corrected.mp4")
    maps = ("-map", "[vo]", "-map", f"{len(inputs) // 2}:a", "-map_metadata", "-1", "-c:a", "copy")
    graph_file = cfg.f("overlay", "filter")
    graph_file.write_text(graph)
    run(
        *FF,
        "-v",
        "error",
        *inputs,
        "-i",
        cfg.out,
        "-/filter_complex",
        graph_file,
        *maps,
        *video_codec(cfg),
        "-movflags",
        "+faststart+negative_cts_offsets",
        out,
        cwd=cfg.work,
    )
    for start, end, text in notes:
        print(f"  {start:8.2f}-{end:8.2f} s  {text}")
    print(f"{len(notes)} corrections -> {out}")
