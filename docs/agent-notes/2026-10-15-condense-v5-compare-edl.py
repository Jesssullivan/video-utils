"""Compare a condense edl.json with the hand-run edl.v5.json: kept spans, speeds, output frames, totals.

usage: compare_edl.py <edl.v5.json> <condense edl.json>
A kept span is source time the edit plays: a speech/pause/filler/card segment, or one keep edge of a cut.
Adjacent kept spans of one speed and kind join, so a cut's edges join their neighbours when they play at 1x.
Prints JSON with counts and the largest edge differences in frames.
"""

import json
import sys

FPS = 30


def v5_clips(e):
    out = {}
    for p in e["parts"]:
        for g in p["edl"]:
            out.setdefault(g["src"], []).append(g)
    return out


def new_clips(e):
    return {c["name"]: c["segments"] for c in e["clips"]}


def frames(g):
    if "frames" in g:
        return g["frames"]
    return round(g["out_dur"] * FPS)


def kept(segs):
    """[(src_in, src_out, speed, out_frame_start, out_frame_end)] with a cut split into its two keep edges."""
    rows, n = [], 0
    for g in segs:
        f = frames(g)
        if g["kind"] == "cut":
            (a0, a1), (b0, b1) = g["keep"]
            k0 = round((a1 - a0) * FPS)
            rows += [(a0, a1, 1.0, "keep", n, n + k0), (b0, b1, 1.0, "keep", n + k0, n + f)]
        else:
            rows.append((g["inp"], g["out"], g["speed"], g["kind"], n, n + f))
        n += f
    return rows, n


def match(a, b):
    """Pair each span of a with its nearest span of b, in one forward pass over two lists sorted by source.

    For x in a: j skips every span of b that ends at or before x starts; the candidates are b[j-2 .. j+2]
    (at most 5 spans), and the pair is the candidate with the least |start diff| + |end diff|. A span of b
    may pair with more than one span of a; no window bounds the distance, the caller's 1-frame test does.
    """
    out, j = [], 0
    for x in a:
        while j < len(b) and b[j][1] <= x[0] + 1e-6:
            j += 1
        best = min(b[max(0, j - 2) : j + 3], key=lambda y: abs(y[0] - x[0]) + abs(y[1] - x[1]), default=None)
        out.append((x, best))
    return out


def main():
    v5, new = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
    a, b = v5_clips(v5), new_clips(new)
    report, total_a, total_b = {}, 0, 0
    for clip in a:
        ra, fa = kept(a[clip])
        rb, fb = kept(b[clip])
        total_a += fa
        total_b += fb
        pairs = match(ra, rb)
        within, worst, speed_diff, out_worst = 0, 0.0, 0, 0
        for x, y in pairs:
            d = max(abs(x[0] - y[0]), abs(x[1] - y[1])) * FPS if y else float("inf")
            worst = max(worst, d)
            if d <= 1 + 1e-6 and abs(x[2] - y[2]) <= 1e-3 * x[2]:
                within += 1
            if y and abs(x[2] - y[2]) > 1e-3 * x[2]:
                speed_diff += 1
            if y:
                out_worst = max(out_worst, abs(x[4] - y[4]))
        report[clip] = dict(
            v5_kept_spans=len(ra),
            new_kept_spans=len(rb),
            within_1_frame_same_speed=within,
            worst_edge_frames=round(worst, 3),
            speed_differs=speed_diff,
            v5_frames=fa,
            new_frames=fb,
            frame_diff=fb - fa,
            worst_output_start_shift_frames=out_worst,
            v5_segments=len(a[clip]),
            new_segments=len(b[clip]),
        )
    report["total"] = dict(v5_frames=total_a, new_frames=total_b, frame_diff=total_b - total_a)
    print(json.dumps(report, indent=1))


main()
