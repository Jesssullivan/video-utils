"""SRT and WebVTT captions on the output clock.

Each word's source times go through the EDL. A word is dropped when it is a filler, when it sits in a span
that plays as a filler, or when the edit plays none of it at speech speed. Captions hold at most 2 lines of
42 characters. A caption ends at a sentence end, at a gap of 1 s, or when it is full.
"""

import json
import textwrap

from .edl import Timeline
from .events import is_filler


def spoken(tl, clip, word):
    """Output (start, end) of a word, or None when the edit drops it."""

    def kept(t):
        row = tl.row(clip, t)
        return row is not None and row[2]["kind"] in ("speech", "cut") and tl.to_out(clip, t) is not None

    row = tl.row(clip, word["start"])
    end = max(word["start"], word["end"] - 0.01)
    # DTW starts can run early, so a word that starts in a pause and ends in speech is still said
    if is_filler(word["word"]) or row is None or row[2]["kind"] == "filler" or not (kept(word["start"]) or kept(end)):
        return None
    a = tl.to_out(clip, word["start"], snap=True)
    return a, max(tl.to_out(clip, end, snap=True) or a, a + 0.05)


def output_words(cfg, tl):
    """[(start, end, word)] of every kept word, in output order."""
    out = []
    for clip in (c for c in cfg.clips if not c["card"]):
        for word in json.loads(cfg.f(clip, "words.json").read_text()):
            if span := spoken(tl, clip["name"], word):
                start = max(span[0], out[-1][0] if out else 0.0)
                out.append((start, max(span[1], start + 0.05), word["word"]))
    return out


def cues(words, width=42, lines=2, gap=1.0, min_s=1.0):
    """Group (start, end, word) into [start, end, [lines]] captions."""
    out, cur = [], []

    def flush():
        if cur:
            out.append([cur[0][0], cur[-1][1], textwrap.wrap(" ".join(w for _, _, w in cur), width)])
            cur.clear()

    for a, b, w in words:
        text = " ".join([x[2] for x in cur] + [w])
        if cur and (a - cur[-1][1] > gap or len(textwrap.wrap(text, width)) > lines):
            flush()
            text = w
        cur.append((a, b, w))
        if w[-1] in ".?!" and len(text) >= width // 2:
            flush()
    flush()
    for cue, nxt in zip(out, out[1:] + [None], strict=True):  # hold short captions, never into the next one
        cue[1] = max(cue[1], cue[0] + min_s)
        if nxt:
            cue[1] = min(cue[1], nxt[0])
    return out


def stamp(t, sep):
    ms = round(t * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d}{sep}{ms % 1000:03d}"


def srt(cues):
    blocks = [f"{i}\n{stamp(a, ',')} --> {stamp(b, ',')}\n" + "\n".join(t) for i, (a, b, t) in enumerate(cues, 1)]
    return "\n\n".join(blocks) + "\n"


def vtt(cues):
    return (
        "WEBVTT\n\n" + "\n\n".join(f"{stamp(a, '.')} --> {stamp(b, '.')}\n" + "\n".join(t) for a, b, t in cues) + "\n"
    )


def write(cfg):
    r = cfg.rules
    found = cues(output_words(cfg, Timeline.load(cfg)), r["caption_chars"], r["caption_lines"])
    cfg.out.parent.mkdir(parents=True, exist_ok=True)
    cfg.out.with_suffix(".srt").write_text(srt(found))
    cfg.out.with_suffix(".vtt").write_text(vtt(found))
    print(f"{len(found)} captions -> {cfg.out.with_suffix('.srt')} and .vtt")
