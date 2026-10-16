"""Checks on the rendered edit. Each gate measures, prints, and passes or fails.

silence:  no silence of 1 s or more at -35 dB is left. Each hit prints with the source time it came from.
loud:     integrated loudness within 1 LU of the target, true peak under 0 dBTP.
sync:     avsync.py. Every output frame of a coded stand-in, the delivered file at 1x speech (median per
          clip), and the delivered file against its lossless parts (median per third) must sit within 20 ms.
bounds:   whisper reads 6 s of the edit around cuts and clip joins, and the same span of the source.
          Printed side by side for a human: a cut must not eat a word. It never fails on its own.
captions: a measurement, not a gate. At sampled cues that follow a quiet lead-in, the cue start against the
          speech onset in the delivered sound. Positive means the caption appears after the speech starts.

`check` writes work/check.json: per gate its limits, its measured values and whether it passed, bound to the
sha256 of the delivered file and of edl.json. publish copies it into the run. Text stays in the printed report;
check.json holds names, times and numbers only.
"""

import difflib
import json

import numpy as np

from . import audio, avsync, captions, transcribe
from .config import FF, run
from .edl import Timeline
from .events import norm
from .publish import CHECK_REPORT, sha256
from .render import SR

GATES = ("silence", "loud", "sync", "bounds")


def measure_silence(cfg, tl):
    c = cfg.check
    hits = audio.silences(cfg.out, c["silence_db"], c["silence_s"])
    print(f"silence: {len(hits)} hits at {c['silence_db']} dB over {c['silence_s']} s")
    found = []
    for a, b in hits:
        src = tl.to_src(a + 0.01)
        where = f"{src[1]['src']} {src[0]:.2f} s ({src[1]['kind']} at {src[1]['speed']}x)" if src else "past the end"
        print(f"  {a:8.2f}-{b:8.2f} s  from {where}")
        hit = {"start_s": round(a, 3), "end_s": round(b, 3)}
        if src:
            hit |= {"clip": src[1]["src"], "source_s": round(src[0], 3), "kind": src[1]["kind"]}
        found.append(hit)
    limits = {"silence_db": c["silence_db"], "silence_s": c["silence_s"], "hits_max": 0}
    return {"limits": limits, "measured": {"hits": len(hits), "spans": found}, "passed": not hits}


def ebur128(path):
    """Integrated loudness (LUFS), loudness range (LU) and true peak (dBTP) of the file's sound."""
    log = run(*FF, "-nostats", "-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-").stderr
    summary = log[log.rindex("Summary:") :].split()
    return tuple(float(summary[summary.index(key) + 1]) for key in ("I:", "LRA:", "Peak:"))


def measure_loud(cfg, tl):
    i, lra, peak = ebur128(cfg.out)
    print(f"loud: {i} LUFS (target {cfg.encode['loudness']}), true peak {peak} dBTP, range {lra} LU")
    limits = {
        "target_lufs": cfg.encode["loudness"],
        "loudness_lu": cfg.check["loudness_lu"],
        "true_peak_below_dbtp": 0.0,
        "render_true_peak_dbtp": cfg.encode["true_peak"],
    }
    measured = {"integrated_lufs": i, "deviation_lu": round(i - cfg.encode["loudness"], 2), "true_peak_dbtp": peak}
    measured["loudness_range_lu"] = lra
    passed = abs(i - cfg.encode["loudness"]) <= cfg.check["loudness_lu"] and peak < 0
    return {"limits": limits, "measured": measured, "passed": passed}


def measure_sync(cfg, tl):
    edl = json.loads(cfg.f("edl", "json").read_text())
    limit = cfg.check["sync_ms"]
    probe, real = avsync.measure_probe(cfg, edl, limit), avsync.measure_real(cfg, tl, edl, limit)
    joined = avsync.measure_joined(cfg, edl, limit)
    measured = {"probe": probe, "real": real, "joined": joined}
    passed = probe["passed"] and real["passed"] and joined["passed"]
    return {"limits": {"sync_ms": limit}, "measured": measured, "passed": passed}


def measure_bounds(cfg, tl):
    """Two cuts per clip (a quarter and three quarters through) and every clip join."""
    picks, found = [], []
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
        found.append({"at": name, "t_s": round(t, 3), "match": round(same.ratio(), 3)})
    return {"limits": None, "measured": {"spots": found}, "passed": True, "review": "a person reads the printed text"}


def onset(x, at, lead=0.3, frame=0.005, rise_db=10.0, contrast_db=20.0):
    """Seconds into x of the sound onset nearest `at` (seconds into x) within `lead`, or None.

    x is 48 kHz mono sound. An onset is a 5 ms level rise_db over the floor (the window's 10th percentile)
    after 50 ms below it. The nearest one is taken, so a filler the captions leave out does not stand in for
    the cue's own first word. A window whose loud part is not contrast_db over its floor has no clear onset.
    """
    n = int(frame * SR)
    level = 10 * np.log10(np.maximum((x[: len(x) // n * n].reshape(-1, n) ** 2).mean(axis=1), 1e-9))
    floor = np.percentile(level, 10)
    if np.percentile(level, 95) - floor < contrast_db:
        return None
    above, quiet = level > floor + rise_db, int(0.05 / frame)
    lo, hi = max(quiet, int((at - lead) / frame)), min(len(level), int((at + lead) / frame) + 1)
    rises = [i * frame for i in range(lo, hi) if above[i] and not above[i - quiet : i].any()]
    return min(rises, key=lambda t: abs(t - at)) if rises else None


def measure_captions(cfg, tl, samples=24, pad=0.6):
    """Cue start minus speech onset, at up to `samples` cues that follow at least 0.3 s with no cue."""
    try:
        words = captions.output_words(cfg, tl)
    except FileNotFoundError as missing:
        print(f"captions: not measured: {missing}")
        return {"limits": None, "measured": None, "passed": True, "gated": False}
    r = cfg.rules
    found = captions.cues(words, r["caption_chars"], r["caption_lines"])
    lead_in = [c[0] for i, c in enumerate(found) if c[0] - (found[i - 1][1] if i else 0.0) >= 0.3 and c[0] >= pad]
    picked = lead_in[:: max(1, len(lead_in) // samples)][:samples]
    offsets = []
    for start in picked:
        first = round((start - pad) * SR)
        at = onset(avsync.pcm(cfg.out, first, round(2 * pad * SR)), start - first / SR)
        if at is not None:
            offsets.append(round((start - (first / SR + at)) * 1000, 1))
    measured = {"cues": len(found), "with_lead_in": len(lead_in), "sampled": len(picked), "offsets_ms": offsets}
    if offsets:
        o = np.array(offsets)
        measured |= {"median_ms": round(float(np.median(o)), 1), "max_abs_ms": round(float(np.abs(o).max()), 1)}
        measured["p90_abs_ms"] = round(float(np.percentile(np.abs(o), 90)), 1)
        print(f"captions: {len(offsets)} of {len(picked)} sampled cues, median {measured['median_ms']:+.1f} ms")
    else:
        print(f"captions: {len(picked)} sampled cues, no clear speech onset")
    return {"limits": None, "measured": measured, "passed": True, "gated": False}


CHECKS = {
    "silence": measure_silence,
    "loud": measure_loud,
    "sync": measure_sync,
    "bounds": measure_bounds,
    "captions": measure_captions,
}


def silence(cfg, tl):
    return measure_silence(cfg, tl)["passed"]


def loud(cfg, tl):
    return measure_loud(cfg, tl)["passed"]


def sync(cfg, tl):
    return measure_sync(cfg, tl)["passed"]


def bounds(cfg, tl):
    return measure_bounds(cfg, tl)["passed"]


def summary(gates):
    """The few numbers publish records in the manifest."""

    def get(name, *keys):
        value = gates.get(name, {}).get("measured")
        for key in keys:
            value = value.get(key) if isinstance(value, dict) else None
        return value

    probe = get("sync", "probe", "clips") or []
    worst = [w["max_abs_ms"] for c in probe if (w := c["windows"]["all"])]
    real = get("sync", "real", "thirds") or {}
    joined = get("sync", "joined", "thirds") or {}
    return {
        "silence_hits": get("silence", "hits"),
        "integrated_lufs": get("loud", "integrated_lufs"),
        "true_peak_dbtp": get("loud", "true_peak_dbtp"),
        "sync_probe_max_abs_ms": max(worst) if worst else None,
        "sync_real_median_ms": {k: (v or {}).get("median_ms") for k, v in real.items()} or None,
        "sync_joined_median_ms": {k: (v or {}).get("median_ms") for k, v in joined.items()} or None,
        "caption_offset_median_ms": get("captions", "median_ms"),
    }


def check(cfg, names, report=None):
    """Run the named checks (default all), print them, write check.json, and return True when no gate failed."""
    unknown = [name for name in names if name not in CHECKS]
    if unknown:
        raise ValueError(f"unknown checks {unknown}; choose from {list(CHECKS)}")
    tl = Timeline.load(cfg)
    gates = {name: CHECKS[name](cfg, tl) for name in names or CHECKS}
    failed = [name for name, gate in gates.items() if not gate["passed"]]
    print("check:", f"FAILED {failed}" if failed else "ok")
    version = run(*FF, "-version").stdout.splitlines()[0]
    record = {
        "schema_version": 1,
        "kind": "condense_check",
        "delivery": {"file": cfg.out.name, "sha256": sha256(cfg.out), "video_frames": audio.frames(cfg.out)},
        "edl_sha256": sha256(cfg.f("edl", "json")),
        "ran": list(gates),
        "complete": all(name in gates for name in GATES),
        "passed": not failed,
        "failed": failed,
        "summary": summary(gates),
        "gates": gates,
        "tools": {"ffmpeg": version},
    }
    path = report or cfg.f(*CHECK_REPORT)
    path.write_text(json.dumps(record, indent=2) + "\n")
    print(f"check: wrote {path}")
    return not failed
