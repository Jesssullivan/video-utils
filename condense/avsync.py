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
"""

import subprocess
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .config import FF, TIMEOUT_S, run
from .render import SR, joined, parts, render_part, video_filter

BITS, CELL, RAMP = 20, 4, 4000.0
CODED = ("-c:v", "ffv1", "-g", "1", "-c:a", "pcm_f64le")


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


def check_probe(cfg, edl, limit_ms):
    """True when every readable output frame of every clip is within the limit."""
    ok = True
    for clip in (c for c in edl["clips"] if c["segments"][0]["kind"] != "card"):
        off, good = probe(cfg, edl, clip)
        t = np.arange(len(off)) / edl["fps"]
        fast = np.repeat(
            [s["kind"] != "cut" and s["speed"] != 1.0 for s in clip["segments"]],
            [s["frames"] for s in clip["segments"]],
        )
        print(f"sync probe: {clip['name']}: {int((~good).sum())} crossfade or padded frames set aside")
        for name, mask in (("first 60 s", t < 60), ("1x", ~fast), ("sped", fast), ("all", t >= 0)):
            print(f"  {name:10s} {stats(off[good & mask])}")
        ok &= bool(good.any() and np.abs(off[good]).max() <= limit_ms)
    return ok


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


def real_at(cfg, s, shift, t0, j):
    """(audio - video in ms, correlation, sharpness) at output frame j of 1x segment s, which starts at t0."""
    fps = cfg.fps
    mezz, want = cfg.f(s["src"], "mezz.mkv"), s["inp"] + shift + j / fps - t0  # the source time the EDL puts there
    k0 = max(0, round(want * fps) - 12)
    edit, source = gray(cfg.out, j, 5, fps), gray(mezz, k0, 29, fps, video_filter(cfg) + ",")
    miss = [((edit - source[k : k + 5]) ** 2).mean() for k in range(len(source) - 4)]
    seen = (k0 + int(np.argmin(miss))) / fps
    x = pcm(cfg.out, j * SR // fps, 19200)
    c0 = max(0, round(want * SR) - 12000)
    y = pcm(mezz, c0, len(x) + 24000)
    corr = match(y, x - x.mean())
    heard = (c0 + int(np.argmax(corr))) / SR
    return (heard - seen) * 1000, corr.max(), np.sort(miss)[1] / (min(miss) + 1e-9)


def check_real(cfg, tl, edl, limit_ms, points=8):
    """True when the median offset of every clip with 1x speech is within the limit."""
    ok = True
    for clip in edl["clips"]:
        rows = [r for r in tl.by_clip[clip["name"]][1] if r[2]["kind"] == "speech" and r[1] - r[0] >= 0.8]
        rows = [r for r in rows if r[2]["frames"] == round((r[2]["out"] - r[2]["inp"]) * cfg.fps)]
        spots = [(r, t) for r in rows for t in np.arange(r[0] + 0.2, r[1] - 0.45, 0.5)]
        found = []
        for (t0, _, s), t in spots[:: max(1, len(spots) // points)]:
            gap, corr, sharp = real_at(cfg, s, clip["shift"], t0, round(t * cfg.fps))
            if corr >= 0.5 and sharp >= 1.15:  # else the sound or the picture has no clear match there
                found.append(gap)
                print(f"sync real: {clip['name']} at {t:8.2f} s: {gap:+6.1f} ms (correlation {corr:.2f})")
        if found:
            ok &= abs(float(np.median(found))) <= limit_ms
            print(f"sync real: {clip['name']} median {np.median(found):+.1f} ms over {len(found)} spots")
        else:
            print(f"sync real: {clip['name']} has no clear 1x speech to measure")
    return ok
