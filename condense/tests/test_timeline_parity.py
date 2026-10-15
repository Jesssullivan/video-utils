"""The in-process time map and quantisation in edl.py give the same answers as the Rust timeline.

The synthetic talk's EDL is queried on a dense grid of source and output times. Seeded random segment lists
go through both quantisers. Every float must match exactly.
"""

import json
import random

from condense import edl, timeline
from condense.edl import Timeline


def grid(stop, step):
    return [round(i * step, 6) for i in range(int(stop / step) + 2)]


def test_the_edl_stage_output_passes_the_rust_validator(talk):
    path = talk.f("edl", "json")
    built = json.loads(path.read_text())
    receipt = timeline.validate(path)
    assert receipt["status"] == "ok"
    assert receipt["total_frames"] == sum(s["frames"] for c in built["clips"] for s in c["segments"])
    assert receipt["max_drift_frames"] <= 0.5 + 1e-9


def test_the_time_map_matches_rust_on_every_query(talk):
    path = talk.f("edl", "json")
    built = json.loads(path.read_text())
    tl = Timeline(built)
    queries, expected = [], []
    for c in built["clips"]:
        for t in grid(c["duration"], 0.01):
            for snap in (False, True):
                queries.append(dict(op="to_out", clip=c["name"], source_s=t, snap=snap))
                expected.append(tl.to_out(c["name"], t, snap))
            queries.append(dict(op="row", clip=c["name"], source_s=t))
            row = tl.row(c["name"], t)
            expected.append(None if row is None else (row[0], c["segments"].index(row[2])))
    for t in grid(tl.total, 0.005):
        queries.append(dict(op="to_src", output_s=t))
        hit = tl.to_src(t)
        expected.append(None if hit is None else hit[0])
    got = []
    for q, r in zip(queries, timeline.answer(path, queries), strict=True):
        if r is None or q["op"] == "to_out":
            got.append(r)
        elif q["op"] == "row":
            got.append((r["start_s"], r["segment_index"]))
        else:
            got.append(r["source_s"])
    assert len(queries) > 5000
    assert got == expected


def random_segments(rng, fps):
    """Contiguous speech, pause, filler and cut segments with frame-grid edges."""
    segs, t = [], 0.0
    for _ in range(rng.randint(3, 40)):
        n = rng.randint(1, 90)
        kind = rng.choice(["speech", "speech", "pause", "filler", "cut"])
        a, b = t, round(t + n / fps, 6)
        if kind == "cut" and n >= 12:
            segs.append(dict(src="x", inp=a, out=b, speed=1.0, kind="cut", keep=[[a, a + 5 / fps], [b - 4 / fps, b]]))
        else:
            speed = {"speech": rng.choice([1.25, 2.0, 2.35]), "pause": 4.0, "filler": 8.0, "cut": 2.0}[kind]
            segs.append(dict(src="x", inp=a, out=b, speed=speed, kind="speech" if kind == "cut" else kind))
        t = b
    return segs


def test_quantise_matches_rust_on_seeded_segment_lists():
    rng = random.Random(20261015)
    keys = ("kind", "frames", "inp", "out", "speed")
    for case in range(60):
        fps = rng.choice([24, 25, 30])
        segs = random_segments(rng, fps)
        ours = [tuple(s[k] for k in keys) for s in edl.quantise(segs, fps)]
        theirs = [tuple(s[k] for k in keys) for s in timeline.quantise(segs, fps)]
        assert ours == theirs, f"case {case}"
