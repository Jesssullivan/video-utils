"""Write tests/fixtures/edl-golden-v1.json from the frozen talk-condense oracle.

Every case is synthetic and seeded, so the file is reproducible:
    python3 condense/tests/frozen/make_edl_golden.py          # rewrite the fixture
    python3 condense/tests/frozen/make_edl_golden.py --check  # exit 1 when it differs
src/timeline.rs must reproduce each answer bit for bit.
"""

import importlib.util
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "edl-golden-v1.json"
SEED = 20261015

spec = importlib.util.spec_from_file_location("edl_oracle", HERE / "edl_timeline_bf5b9dc.py")
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)


def seg(src, inp, out, speed, kind, **extra):
    return dict(src=src, inp=inp, out=out, speed=speed, kind=kind, **extra)


def test_edl_cases():
    """The two quantise cases of talk-condense tests/test_edl.py."""
    cut = seg("x", 2.1, 4.0, 1.0, "cut", keep=[[2.1, 2.2], [3.9, 4.0]])
    blip = seg("x", 2.0, 2.1, 8.0, "filler")
    first = [seg("x", 0.0, 2.0, 2.0, "speech"), blip, cut, seg("x", 4.0, 6.0, 2.0, "speech")]
    lone = [cut | dict(inp=0.0, out=1.9), dict(blip, inp=1.9, out=2.0), dict(cut)]
    return [dict(fps=30, segments=first), dict(fps=30, segments=lone)]


def raw_clip(rng, name, fps, total_frames):
    """Contiguous segments on the frame grid, shaped like edl.event_segments output."""

    def snap(t):
        return round(round(t * fps) / fps, 6)

    segs, f = [], 0
    while f < total_frames:
        kind = rng.choices(["speech", "pause", "filler", "cut"], [5, 2, 2, 2])[0]
        if kind == "cut":
            n = rng.randint(12, 90)
        elif kind == "speech":
            n = rng.randint(1, 120)
        else:
            n = rng.randint(1, 24)
        n = min(n, total_frames - f)
        if kind == "cut" and n < 12:
            kind = "speech"
        x, y = snap(f / fps), snap((f + n) / fps)
        if kind == "cut":
            a, b = snap((f + 5) / fps), snap((f + n - 4) / fps)
            segs.append(seg(name, x, y, 1.0, "cut", keep=[[x, a], [b, y]]))
        elif kind == "speech":
            segs.append(seg(name, x, y, rng.choice([1.0, 2.0, 2.0, 2.5]), "speech"))
        elif kind == "pause":
            segs.append(seg(name, x, y, 4.0, "pause"))
        else:
            segs.append(seg(name, x, y, 8.0, "filler"))
        f += n
    return segs


def finish_clip(name, fps, segs, total, shift, speed, welcome):
    for s in segs:
        if s["kind"] != "card":
            s["out_dur"] = round(s["frames"] / fps, 6)
            s["gain"] = 0.4 if s["speed"] >= 4.0 else 1.0
    kinds = {}
    for s in segs:
        kinds[s["kind"]] = round(kinds.get(s["kind"], 0) + s["out_dur"], 2)
    expected = round(sum(s["out_dur"] for s in segs), 3)
    return dict(
        name=name,
        duration=total,
        shift=shift,
        speed=speed,
        welcome=welcome,
        expected_s=expected,
        out_s_by_kind=kinds,
        segments=segs,
    )


def card_clip(name, fps, total, card_s):
    frames = round(card_s * fps)
    speed = round(total * fps / frames, 4)
    card = seg(name, 0.0, total, speed, "card", frames=frames, out_dur=frames / fps, gain=0.15)
    return finish_clip(name, fps, [card], total, 0.0, speed, None)


def build_edl(rng, index):
    fps = rng.choice([24, 25, 30, 30, 30, 50, 60])
    clips = []
    for c in range(rng.randint(1, 3)):
        name = f"clip{index}_{c}"
        if rng.random() < 0.2:
            clips.append(card_clip(name, fps, round(rng.uniform(5.0, 40.0), 3), rng.choice([1.5, 2.0, 3.0])))
            continue
        total_frames = rng.randint(60, 900)
        segs = oracle.quantise(oracle.coalesce(raw_clip(rng, name, fps, total_frames)), fps)
        total = total_frames / fps
        welcome = None if rng.random() < 0.5 else [0.0, round(total / 4, 3)]
        shift = rng.choice([0.0, 1 / fps, 3 / fps])
        clips.append(finish_clip(name, fps, segs, total, shift, rng.choice([2.0, 2.5]), welcome))
    rules = {"cut_over_s": 1.0, "filler_speed": 8.0, "short_pause_speed": 4.0, "xfade_frames": 2}
    total_s = round(sum(c["expected_s"] for c in clips), 3)
    return dict(fps=fps, rules=rules, clips=clips, expected_total_s=total_s)


def source_times(rng, clip, fps):
    times = [-0.25, 0.0, clip["duration"], clip["duration"] + 0.5]
    for s in clip["segments"]:
        times += [s["inp"], s["out"], (s["inp"] + s["out"]) / 2, s["out"] - 1e-9]
        if s["kind"] == "cut":
            (a0, a1), (b0, b1) = s["keep"]
            times += [a1, b0, (a1 + b0) / 2, a1 - 1e-9, b0 - 1e-9]
    times += [rng.uniform(-0.1, clip["duration"] + 0.1) for _ in range(16)]
    rng.shuffle(times)
    return times[:64]


def answer_row(tl, row):
    if row is None:
        return None
    index = next(i for i, r in enumerate(tl.rows) if r is row)
    return dict(row=index, start_s=row[0], end_s=row[1])


def timeline_case(rng, edl):
    tl = oracle.Timeline(edl)
    seg_index = {id(r[2]): i for i, r in enumerate(tl.rows)}
    queries = []
    for clip in edl["clips"]:
        for t in source_times(rng, clip, edl["fps"]):
            for snap in (False, True):
                queries.append(
                    dict(
                        op="to_out",
                        clip=clip["name"],
                        source_s=t,
                        snap=snap,
                        expect=tl.to_out(clip["name"], t, snap=snap),
                    )
                )
            queries.append(
                dict(op="row", clip=clip["name"], source_s=t, expect=answer_row(tl, tl.row(clip["name"], t)))
            )
    outs = [0.0, tl.total, tl.total + 1.0, -0.5] + [r[0] for r in tl.rows] + [r[1] - 1e-9 for r in tl.rows]
    outs += [rng.uniform(-0.1, tl.total + 0.1) for _ in range(24)]
    rng.shuffle(outs)
    for t in outs[:96]:
        hit = tl.to_src(t)
        expect = None if hit is None else dict(source_s=hit[0], row=seg_index[id(hit[1])])
        queries.append(dict(op="to_src", output_s=t, expect=expect))
    return dict(edl=edl, total_s=tl.total, rows=len(tl.rows), queries=queries)


def golden():
    rng = random.Random(SEED)
    quantise_cases = test_edl_cases()
    for _ in range(10):
        fps = rng.choice([24, 25, 30, 60])
        quantise_cases.append(dict(fps=fps, segments=raw_clip(rng, "q", fps, rng.randint(30, 600))))
    for case in quantise_cases:
        case["expect"] = oracle.quantise(case["segments"], case["fps"])
    timeline_cases = [timeline_case(rng, build_edl(rng, i)) for i in range(8)]
    return dict(
        schema_version=1,
        source="talk-condense bf5b9dc talk_condense/edl.py, frozen in condense/tests/frozen/edl_timeline_bf5b9dc.py",
        generator="condense/tests/frozen/make_edl_golden.py",
        seed=SEED,
        quantise_cases=quantise_cases,
        timeline_cases=timeline_cases,
    )


def dump(value, level=0):
    """JSON with one segment or one query per line, so the fixture diffs line by line."""
    pad = " " * (level + 1)
    if isinstance(value, dict) and ("op" in value or "kind" in value):
        return json.dumps(value, separators=(",", ":"))
    if isinstance(value, dict) and value:
        items = [f"{pad}{json.dumps(k)}: {dump(v, level + 1)}" for k, v in value.items()]
        return "{\n" + ",\n".join(items) + "\n" + " " * level + "}"
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return "[\n" + ",\n".join(pad + dump(v, level + 1) for v in value) + "\n" + " " * level + "]"
    return json.dumps(value, separators=(",", ":"))


def main():
    text = dump(golden()) + "\n"
    if sys.argv[1:] == ["--check"]:
        same = FIXTURE.read_text() == text
        print("edl golden up to date" if same else "edl golden differs; rerun make_edl_golden.py")
        return 0 if same else 1
    FIXTURE.write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
