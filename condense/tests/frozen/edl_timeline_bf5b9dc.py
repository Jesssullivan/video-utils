"""Frozen copy of the EDL quantisation and time map from talk-condense.

Source: talk-condense commit bf5b9dc29dc0171063c9adc580eaed0d7eccb9d9, talk_condense/edl.py
lines 187-246 (coalesce, seg_dur, quantise) and 340-386 (Timeline), copied unchanged.
This is the oracle for src/timeline.rs. make_edl_golden.py writes its answers to
tests/fixtures/edl-golden-v1.json. Do not edit the copied code.
"""

import bisect
import json


def coalesce(segs):
    """Drop empty segments and join neighbours of one kind and speed."""
    out = []
    for s in segs:
        if s["out"] - s["inp"] < 1e-6:
            continue
        last = out[-1] if out else None
        same = last and s["kind"] != "cut" and (last["speed"], last["kind"]) == (s["speed"], s["kind"])
        if same and abs(last["out"] - s["inp"]) < 1e-6:
            last["out"] = s["out"]
        else:
            out.append(dict(s))
    return out


def seg_dur(s):
    """Output seconds of one segment."""
    if s["kind"] == "cut":
        return sum(b - a for a, b in s["keep"])
    return (s["out"] - s["inp"]) / s["speed"]


def quantise(segs, fps):
    """Give every segment a whole number of output frames, diffusing the rounding error.

    Segment k ends on frame round(ideal running total * fps). A segment that would get no frame joins a
    neighbour and plays at its speed: the one before it, or the one after when a cut sits before it.
    Between two cuts it keeps one frame. A cut always keeps its own frames, so the next segment pays that back.
    """
    segs = [dict(s) for s in segs]

    def free(o):
        return o is not None and o["kind"] != "cut"

    while True:
        total, done = 0.0, 0
        for s in segs:
            total += seg_dur(s) * fps
            own = round(seg_dur(s) * fps) if s["kind"] == "cut" else 1 if s.get("min1") else 0
            s["frames"] = own if s["kind"] == "cut" else max(round(total - 1e-9) - done, own)
            done += s["frames"]
        zero = next((i for i, s in enumerate(segs) if s["frames"] == 0), None)
        if zero is None:
            return [{k: v for k, v in s.items() if k != "min1"} for s in segs]
        z = segs[zero]
        prev = segs[zero - 1] if zero else None
        nxt = segs[zero + 1] if zero + 1 < len(segs) else None

        def same(o, z=z):
            return free(o) and o["speed"] == z["speed"]

        if free(prev) and abs(prev["out"] - z["inp"]) < 1e-6 and (same(prev) or not same(nxt)):
            prev["out"] = z["out"]
        elif free(nxt) and abs(nxt["inp"] - z["out"]) < 1e-6:
            nxt["inp"] = z["inp"]
        else:
            z["min1"] = True
            continue
        del segs[zero]
        segs = coalesce(segs)


class Timeline:
    """Where every segment lands on the output clock, and the map between source and output times."""

    def __init__(self, edl):
        self.rows, self.by_clip, n, fps = [], {}, 0, edl["fps"]  # rows: (out_start, out_end, segment)
        for clip in edl["clips"]:
            first = len(self.rows)
            for s in clip["segments"]:
                self.rows.append((n / fps, (n + s["frames"]) / fps, s))
                n += s["frames"]
            self.by_clip[clip["name"]] = ([r[2]["inp"] for r in self.rows[first:]], self.rows[first:])
        self.total, self.starts = n / fps, [r[0] for r in self.rows]
        self.shift = {c["name"]: c["shift"] for c in edl["clips"]}

    @classmethod
    def load(cls, cfg):
        return cls(json.loads(cfg.f("edl", "json").read_text()))

    def row(self, clip, t):
        """The row whose segment holds source time t of a clip, or None."""
        inps, rows = self.by_clip[clip]
        i = bisect.bisect_right(inps, t) - 1
        return rows[i] if i >= 0 and t < rows[i][2]["out"] else None

    def to_out(self, clip, t, snap=False):
        """Output time of source time t. None inside a dropped span, unless snap moves it to the join."""
        row = self.row(clip, t)
        if row is None:
            return None
        t0, t1, s = row
        if s["kind"] != "cut":  # the segment's real speed is its source length over its whole frames
            return t0 + (t - s["inp"]) / (s["out"] - s["inp"]) * (t1 - t0)
        (a0, a1), (b0, _) = s["keep"]
        if a1 <= t < b0 and not snap:
            return None
        return t0 + (t - a0 if t < a1 else (a1 - a0) + max(0.0, t - b0))

    def to_src(self, t):
        """(source time, segment) under output time t, or None past the end."""
        i = bisect.bisect_right(self.starts, t) - 1
        if i < 0 or t >= self.rows[i][1]:
            return None
        t0, t1, s = self.rows[i]
        if s["kind"] != "cut":
            return s["inp"] + (t - t0) / (t1 - t0) * (s["out"] - s["inp"]), s
        (a0, a1), (b0, _) = s["keep"]
        return (a0 + t - t0 if t - t0 < a1 - a0 else b0 + t - t0 - (a1 - a0)), s
