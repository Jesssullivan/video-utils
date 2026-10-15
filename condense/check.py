"""Checks on the rendered edit. Each returns True when it passes.

silence: no silence of 1 s or more at -35 dB is left. Each hit prints with the source time it came from.
loud:    integrated loudness within 1 LU of the target, true peak under 0 dBTP.
sync:    avsync.py. Every output frame of a coded stand-in, and the delivered file at 1x speech, must sit
         within 20 ms.
bounds:  whisper reads 6 s of the edit around cuts and clip joins, and the same span of the source.
         Printed side by side for a human: a cut must not eat a word.
"""

import difflib
import json

from . import audio, avsync, transcribe
from .config import FF, run
from .edl import Timeline
from .events import norm


def silence(cfg, tl):
    c = cfg.check
    hits = audio.silences(cfg.out, c["silence_db"], c["silence_s"])
    print(f"silence: {len(hits)} hits at {c['silence_db']} dB over {c['silence_s']} s")
    for a, b in hits:
        src = tl.to_src(a + 0.01)
        where = f"{src[1]['src']} {src[0]:.2f} s ({src[1]['kind']} at {src[1]['speed']}x)" if src else "past the end"
        print(f"  {a:8.2f}-{b:8.2f} s  from {where}")
    return not hits


def loud(cfg, tl):
    log = run(*FF, "-nostats", "-i", cfg.out, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-").stderr
    summary = log[log.rindex("Summary:") :].split()
    i, peak = float(summary[summary.index("I:") + 1]), float(summary[summary.index("Peak:") + 1])
    print(f"loud: {i} LUFS (target {cfg.encode['loudness']}), true peak {peak} dBTP")
    return abs(i - cfg.encode["loudness"]) <= cfg.check["loudness_lu"] and peak < 0


def sync(cfg, tl):
    edl = json.loads(cfg.f("edl", "json").read_text())
    limit = cfg.check["sync_ms"]
    return avsync.check_probe(cfg, edl, limit) & avsync.check_real(cfg, tl, edl, limit)


def bounds(cfg, tl):
    """Two cuts per clip (a quarter and three quarters through) and every clip join."""
    picks = []
    for clip in cfg.clips:
        rows = tl.by_clip[clip["name"]][1]
        cuts = [
            (b[0] + b[1]) / 2
            for a, b, c in zip(rows, rows[1:], rows[2:], strict=False)
            if (a[2]["kind"], b[2]["kind"], c[2]["kind"]) == ("speech", "cut", "speech")
            and min(a[2]["out"] - a[2]["inp"], c[2]["out"] - c[2]["inp"]) > 1
        ]
        picks += [(f"{clip['name']} cut", cuts[len(cuts) * q // 4]) for q in (1, 3) if cuts]
        if rows[0][0] > 0:
            picks.append((f"join before {clip['name']}", rows[0][0]))
    for name, t in sorted(picks, key=lambda p: p[1]):
        lo, hi = max(0.0, t - 3), min(tl.total, t + 3)
        (a, sa), (b, sb) = tl.to_src(lo + 0.02), tl.to_src(hi - 0.02)
        shift_a, shift_b = tl.shift[sa["src"]], tl.shift[sb["src"]]  # the mezzanines are on the source's clock
        edit = transcribe.read(cfg, cfg.out, lo, hi)
        wav_a, wav_b = cfg.f(sa["src"], "mezz.mkv"), cfg.f(sb["src"], "mezz.mkv")
        if sa["src"] == sb["src"]:
            source = transcribe.read(cfg, wav_a, a + shift_a, b + shift_a)
        else:
            end = tl.by_clip[sa["src"]][1][-1][2]["out"]
            source = transcribe.read(cfg, wav_a, a + shift_a, end + shift_a) + " | "
            source += transcribe.read(cfg, wav_b, shift_b, b + shift_b)
        same = difflib.SequenceMatcher(None, [norm(w) for w in source.split()], [norm(w) for w in edit.split()])
        span = f"{sa['src']} {a:.2f} s to {sb['src']} {b:.2f} s"
        print(f"bounds: {name} at {t:.2f} s (source {span}), match {same.ratio():.2f}")
        print(f"  edit:   {edit}\n  source: {source}")
    return True


CHECKS = {"silence": silence, "loud": loud, "sync": sync, "bounds": bounds}


def check(cfg, names):
    tl = Timeline.load(cfg)
    failed = [name for name in names or CHECKS if not CHECKS[name](cfg, tl)]
    print("check:", f"FAILED {failed}" if failed else "ok")
    return not failed
