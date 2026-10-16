"""A/V sync instrument. Offsets are in ms of output time. Positive means the sound leads the picture.

probe: measures every output frame, before the encode. Each clip gets a stand-in mezzanine of coded content:
       video frame k shows k as 20 luma bits, and every audio sample holds its own source time / 4000.
       The clip's real part graphs run on it and are joined as the final step joins them. Each output
       frame then says which source frame it shows, and its audio says which source time it plays.
       A plain resample stands in for atempo, which would scramble the coded audio.
real:  measures the delivered file at speech that plays at 1x. The picture is matched against the mezzanine
       frames around the EDL's answer (5 frames, 25 candidates). 0.4 s of sound is cross-correlated against
       the mezzanine audio 0.25 s to each side. This is the check that sees the source's own clocks,
       atempo, the encode and the mp4 timestamps.
joined: measures the delivered file at any speed, at points spread over the whole edit, against the
       lossless parts in work/ that the final step joined. The same picture and sound match, so it sees the
       join, the delivery filters, the encode and the mp4 timestamps, also where speech is sped up. Only
       atempo's own timing inside a sped segment is measured by none of the three.

A spot is clear when its sound correlates at CLEAR_CORR or more at a lag inside the search window and its
picture match is CLEAR_SHARP times better than the next frame. The same picture and sound matched on the
real talk at 0.835 to 0.988; leads of 0.5 to 8 s, beyond the 0.25 s window, gave spurious peaks at 0.57 or
less on the synthetic talk. A median needs MIN_CLEAR clear spots: fewer, where at least MIN_CLEAR were
tried, fails (a gross offset leaves nothing clear), and fewer tried is not measured. No measure passes
without evidence: each one's verdict is passed, failed or not_measured, and only passed passes.
"""

import subprocess
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .config import FF, TIMEOUT_S, run
from .render import SR, joined, parts, render_part, video_filter

BITS, CELL, RAMP = 20, 4, 4000.0
CODED = ("-c:v", "ffv1", "-g", "1", "-c:a", "pcm_f64le")
CLEAR_CORR, CLEAR_SHARP = 0.75, 1.15
MIN_CLEAR = 4  # clear spots behind a median: per clip (real) and per third of the edit (joined)


def overall(verdicts):
    """failed when any failed, else not_measured when any was not measured or there were none, else passed."""
    verdicts = list(verdicts)
    if "failed" in verdicts:
        return "failed"
    return "passed" if verdicts and all(v == "passed" for v in verdicts) else "not_measured"


def judged(offsets, tried, limit_ms):
    """(verdict, median ms or None) of the clear spots' offsets at `tried` spots."""
    median = round(float(np.median(offsets)), 2) if len(offsets) else None
    if len(offsets) >= MIN_CLEAR:
        return ("passed" if abs(median) <= limit_ms else "failed"), median
    return ("failed" if tried >= MIN_CLEAR else "not_measured"), median


def coded_mezzanine(cfg, clip):
    """work/<clip>.probe.mkv: as long as the real mezzanine, with frame numbers for video and a ramp for audio."""
    lum = f"255*mod(floor(N/pow(2,floor(X/{CELL}))),2)"
    picture = f"nullsrc=s={BITS * CELL}x8:r={cfg.fps},format=gray,geq=lum='{lum}'"
    ramp = f"aevalsrc='t/{RAMP}':s={SR}"
    span = ("-t", clip["duration"] + clip["shift"])
    run(
        *FF,
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        picture,
        "-f",
        "lavfi",
        "-i",
        ramp,
        *span,
        *CODED,
        cfg.f(clip, "probe.mkv"),
    )


def probe(cfg, edl, clip):
    """(offset in ms, readable) per output frame of one clip of the EDL."""
    fps, per, segs = edl["fps"], SR // edl["fps"], clip["segments"]
    coded_mezzanine(cfg, clip)
    mine = [p for p in parts(edl) if p[1] == clip["name"]]
    with ThreadPoolExecutor(cfg.encode["jobs"]) as pool:
        names = list(pool.map(lambda p: render_part(cfg, edl, *p, "probe", CODED), mine))
    inputs, graph = joined(cfg, names, "probe")
    v, a = cfg.f(clip, "probe.gray"), cfg.f(clip, "probe.f64")
    video = ("-map", "[vo]", "-f", "rawvideo", v)
    run(
        *FF,
        "-v",
        "error",
        *inputs,
        "-filter_complex",
        graph + ";[v]format=gray[vo]",
        *video,
        "-map",
        "[a0]",
        "-f",
        "f64le",
        a,
    )
    bits = np.fromfile(v, np.uint8).reshape(-1, 8, BITS * CELL)[:, 4, CELL // 2 :: CELL] > 127
    shown = (bits * (1 << np.arange(BITS))).sum(axis=1) / fps  # source time of the frame each output frame shows
    ramp = np.fromfile(a, np.float64) * RAMP  # source time of the sound in each output sample
    v.unlink(), a.unlink()
    seg = np.repeat(np.arange(len(segs)), [s["frames"] for s in segs])
    assert len(shown) == len(seg) and len(ramp) == len(seg) * per, (len(shown), len(ramp), len(seg))
    speed = np.array([1.0 if s["kind"] == "cut" else (s["out"] - s["inp"]) * fps / s["frames"] for s in segs])[seg]
    mid = np.arange(len(seg)) * per + per // 2
    heard = ramp[mid] - speed / (2 * fps)  # the sound at the start of each frame
    # A cut's crossfade blends two source times, and padding holds none. Both show as a wrong slope.
    slope = (ramp[mid + per // 4] - ramp[mid - per // 4]) * SR / (per // 2)
    return (heard - shown) / speed * 1000, np.abs(slope / speed - 1) < 0.5


def stats(x):
    if not len(x):
        return "no frames"
    lo, mid, hi = np.percentile(x, [0, 50, 100])
    return f"{len(x)} frames, min {lo:+.1f}, median {mid:+.1f}, max {hi:+.1f} ms"


def summary(x):
    """Frames, min, median, max and the largest |offset| in ms, or None when no frame was measured."""
    if not len(x):
        return None
    lo, mid, hi = (round(float(v), 2) for v in np.percentile(x, [0, 50, 100]))
    return {"frames": len(x), "min_ms": lo, "median_ms": mid, "max_ms": hi, "max_abs_ms": max(-lo, hi)}


def thirds(t, total):
    """Masks for the start, middle and end third of an output timeline `total` seconds long."""
    return {name: (t >= total * i / 3) & (t < total * (i + 1) / 3) for i, name in enumerate(("start", "middle", "end"))}


def measure_probe(cfg, edl, limit_ms):
    """Per clip: set-aside frames, offset summaries by window and by third, and whether every frame is in limit."""
    clips = []
    for clip in (c for c in edl["clips"] if c["segments"][0]["kind"] != "card"):
        off, good = probe(cfg, edl, clip)
        t = np.arange(len(off)) / edl["fps"]
        fast = np.repeat(
            [s["kind"] != "cut" and s["speed"] != 1.0 for s in clip["segments"]],
            [s["frames"] for s in clip["segments"]],
        )
        print(f"sync probe: {clip['name']}: {int((~good).sum())} crossfade or padded frames set aside")
        windows = {}
        for name, mask in (("first 60 s", t < 60), ("1x", ~fast), ("sped", fast), ("all", t >= 0)):
            print(f"  {name:10s} {stats(off[good & mask])}")
            windows[name] = summary(off[good & mask])
        passed = bool(good.any() and np.abs(off[good]).max() <= limit_ms)
        clips.append(
            {
                "clip": clip["name"],
                "frames": len(off),
                "set_aside_frames": int((~good).sum()),
                "windows": windows,
                "thirds": {k: summary(off[good & m]) for k, m in thirds(t, len(off) / edl["fps"]).items()},
                "verdict": "passed" if passed else "failed",
                "passed": passed,
            }
        )
    verdict = overall(c["verdict"] for c in clips)  # an edit of cards only has nothing to probe
    return {"limit_ms": limit_ms, "verdict": verdict, "passed": verdict == "passed", "clips": clips}


def check_probe(cfg, edl, limit_ms):
    """True when every readable output frame of every probed clip is within the limit."""
    return measure_probe(cfg, edl, limit_ms)["passed"]


def raw(dtype, *args):
    out = subprocess.run(
        [*FF, "-v", "error", *map(str, args), "-"], capture_output=True, check=True, timeout=TIMEOUT_S
    ).stdout
    return np.frombuffer(out, dtype)


def gray(path, first, count, fps, chain=""):
    """Frames [first, first + count) as 64x36 gray. The seek sits half a frame early, so frame `first` is kept."""
    cut = ("-ss", f"{max(0, first - 0.5) / fps:.6f}", "-i", path, "-an", "-frames:v", count)
    return (
        raw(np.uint8, *cut, "-vf", f"{chain}scale=64:36,format=gray", "-f", "rawvideo")
        .reshape(-1, 36, 64)
        .astype(float)
    )


def pcm(path, first, count):
    """Samples [first, first + count) at 48 kHz mono."""
    cut = ("-ss", f"{first / SR:.6f}", "-i", path, "-vn", "-ac", 1, "-ar", SR, "-af", f"atrim=end_sample={count}")
    return raw(np.float32, *cut, "-f", "f32le").astype(float)


def match(y, x):
    """Normalised correlation of x against y at every lag where x fits inside y."""
    size = 1 << (len(y) - 1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(y, size) * np.conj(np.fft.rfft(x, size)), size)[: len(y) - len(x) + 1]
    power = np.concatenate([[0.0], np.cumsum(y * y)])
    return corr / (np.sqrt((power[len(x) :] - power[: -len(x)]) * (x * x).sum()) + 1e-9)


def offset_at(cfg, ref, j, want):
    """(audio - video in ms, correlation, sharpness) at output frame j, against `ref` near its time `want` s.

    The picture is matched against 25 frames of ref around `want` (through the delivery filters), and 0.4 s of
    sound is cross-correlated against ref's sound 0.25 s to each side. A sound peak on the window's edge says
    the match lies outside it, so its correlation is reported as 0.
    """
    fps = cfg.fps
    k0 = max(0, round(want * fps) - 12)
    edit, source = gray(cfg.out, j, 5, fps), gray(ref, k0, 29, fps, video_filter(cfg) + ",")
    miss = [((edit - source[k : k + 5]) ** 2).mean() for k in range(len(source) - 4)]
    seen = (k0 + int(np.argmin(miss))) / fps
    x = pcm(cfg.out, j * SR // fps, 19200)
    c0 = max(0, round(want * SR) - 12000)
    y = pcm(ref, c0, len(x) + 24000)
    corr = match(y, x - x.mean())
    lag = int(np.argmax(corr))
    heard = (c0 + lag) / SR
    inside = 0 < lag < len(corr) - 1
    return (heard - seen) * 1000, float(corr[lag]) if inside else 0.0, np.sort(miss)[1] / (min(miss) + 1e-9)


def clear(corr, sharp):
    """The sound and the picture both have a clear match there."""
    return corr >= CLEAR_CORR and sharp >= CLEAR_SHARP


def real_at(cfg, s, shift, t0, j):
    """(audio - video in ms, correlation, sharpness) at output frame j of 1x segment s, which starts at t0."""
    want = s["inp"] + shift + j / cfg.fps - t0  # the source time the EDL puts there
    return offset_at(cfg, cfg.f(s["src"], "mezz.mkv"), j, want)


def by_thirds(found, total):
    """Clear spots and their median per third of an output timeline `total` seconds long."""
    t = np.array([f["t_s"] for f in found])
    off = np.array([f["offset_ms"] for f in found])
    return {
        name: {"spots": int(mask.sum()), "median_ms": round(float(np.median(off[mask])), 2) if mask.any() else None}
        for name, mask in thirds(t, total).items()
    }


def measure_real(cfg, tl, edl, limit_ms, points=8):
    """Per clip: every measured spot, its median and verdict. Then the spots of all clips by third of the edit.

    A clip with no 1x speech, or too little to try MIN_CLEAR spots, is not measured and does not count. The
    measure passes when no clip failed and at least one passed.
    """
    clips, every = [], []
    for clip in edl["clips"]:
        rows = [r for r in tl.by_clip[clip["name"]][1] if r[2]["kind"] == "speech" and r[1] - r[0] >= 0.8]
        rows = [r for r in rows if r[2]["frames"] == round((r[2]["out"] - r[2]["inp"]) * cfg.fps)]
        spots = [(r, t) for r in rows for t in np.arange(r[0] + 0.2, r[1] - 0.45, 0.5)]
        tried = spots[:: max(1, len(spots) // points)]
        found = []
        for (t0, _, s), t in tried:
            gap, corr, sharp = real_at(cfg, s, clip["shift"], t0, round(t * cfg.fps))
            if clear(corr, sharp):  # else the sound or the picture has no clear match there
                found.append(
                    {"t_s": round(float(t), 3), "offset_ms": round(float(gap), 2), "correlation": round(corr, 3)}
                )
                print(f"sync real: {clip['name']} at {t:8.2f} s: {gap:+6.1f} ms (correlation {corr:.2f})")
        verdict, median = judged([f["offset_ms"] for f in found], len(tried), limit_ms)
        if not tried:
            verdict = "no_1x_speech"
            if clip["segments"][0]["kind"] != "card":
                print(f"sync real: {clip['name']} has no 1x speech to measure")
        else:
            at = f"median {median:+.1f} ms" if median is not None else "no median"
            print(f"sync real: {clip['name']} {at} over {len(found)} of {len(tried)} spots clear: {verdict}")
        clips.append(
            {
                "clip": clip["name"],
                "spots": found,
                "tried_spots": len(tried),
                "unclear_spots": len(tried) - len(found),
                "median_ms": median,
                "verdict": verdict,
            }
        )
        every += found
    verdict = overall(c["verdict"] for c in clips if c["verdict"] in ("passed", "failed"))
    return {
        "limit_ms": limit_ms,
        "min_clear_spots": MIN_CLEAR,
        "verdict": verdict,
        "passed": verdict == "passed",
        "clips": clips,
        "thirds": by_thirds(every, tl.total),
    }


def check_real(cfg, tl, edl, limit_ms, points=8):
    """True when no clip's 1x speech failed and at least one clip's was measured within the limit."""
    return measure_real(cfg, tl, edl, limit_ms, points)["passed"]


def measure_joined(cfg, edl, limit_ms, points=24):
    """Up to points // 3 distinct spots spread evenly over each third's usable frames, each against its lossless
    part. Each third with usable frames needs MIN_CLEAR clear spots and a median within the limit; a third with
    none (only cards or parts too short) is recorded as nothing_to_measure. Not measured, so not passed, when
    the parts are no longer in work/ or no third can be measured."""
    fps = cfg.fps
    every = parts(edl)
    names = [(cfg.f(name, "mezz.mkv"), sum(s["frames"] for s in segs)) for name, _, segs in every]
    starts = np.cumsum([0] + [n for _, n in names])
    total = int(starts[-1])
    # Frames whose 29-frame and 0.9 s windows stay inside their part. Parts under 60 frames have none, and
    # neither has a card, whose picture and sound are not speech.
    usable = [
        np.arange(a + 15, a + n - 44)
        for a, (_, n), (_, _, segs) in zip(starts[:-1], names, every, strict=True)
        if n >= 60 and segs[0]["kind"] != "card"
    ]
    usable = np.concatenate(usable) if usable else np.array([], int)
    empty = {"spots": [], "tried_spots": 0, "unclear_spots": 0, "thirds": None}
    if not all(path.is_file() for path, _ in names):
        print("sync joined: the parts are not in work/: not measured")
        return {"limit_ms": limit_ms, "verdict": "not_measured", "passed": False, "measured": False, **empty}
    if not len(usable):
        print("sync joined: no part is long enough to measure: not measured")
        return {"limit_ms": limit_ms, "verdict": "not_measured", "passed": False, "measured": False, **empty}
    tried = []  # points // 3 distinct frames spread evenly over each third's usable frames, or all of them
    for mask in thirds(usable / fps, total / fps).values():
        pool = usable[mask]
        k = min(len(pool), points // 3)
        tried += [int(pool[int(len(pool) * (i + 0.5) / k)]) for i in range(k)]
    found, offsets = [], np.full(len(tried), np.nan)
    for i, j in enumerate(tried):
        p = int(np.searchsorted(starts, j, side="right")) - 1
        gap, corr, sharp = offset_at(cfg, names[p][0], j, (j - int(starts[p])) / fps)
        if clear(corr, sharp):
            offsets[i] = round(float(gap), 2)
            found.append({"t_s": round(j / fps, 3), "offset_ms": float(offsets[i]), "correlation": round(corr, 3)})
            print(f"sync joined: at {j / fps:8.2f} s: {gap:+6.1f} ms (correlation {corr:.2f})")
    by_third = {}
    for third, mask in thirds(np.array(tried) / fps, total / fps).items():
        mine = offsets[mask & ~np.isnan(offsets)]
        verdict, median = judged(mine, int(mask.sum()), limit_ms)
        if not mask.any():
            verdict = "nothing_to_measure"  # no part there is long enough, or it is a card
        by_third[third] = {"spots": len(mine), "tried": int(mask.sum()), "median_ms": median, "verdict": verdict}
    verdict = overall(v["verdict"] for v in by_third.values() if v["verdict"] != "nothing_to_measure")
    print(
        f"sync joined: {len(found)} of {len(tried)} spots clear, "
        + ", ".join(
            f"{k} {v['median_ms']:+.1f} ms ({v['spots']} of {v['tried']}, {v['verdict']})"
            if v["median_ms"] is not None
            else f"{k} no clear spot of {v['tried']} ({v['verdict']})"
            for k, v in by_third.items()
        )
    )
    return {
        "limit_ms": limit_ms,
        "min_clear_spots": MIN_CLEAR,
        "verdict": verdict,
        "passed": verdict == "passed",
        "measured": True,
        "spots": found,
        "tried_spots": len(tried),
        "unclear_spots": len(tried) - len(found),
        "thirds": by_third,
    }
