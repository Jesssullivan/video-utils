"""SRT and WebVTT captions on the output clock.

Each word's source times go through the EDL. A word is dropped when it is a filler, when it sits in a span
that plays as a filler, or when the edit plays none of it at speech speed. Captions hold at most 2 lines of
42 characters. A caption ends at a sentence end, at a gap of 1 s, or when it is full.

That is the default style. The [captions] section of talk.toml (config.CAPTIONS) changes which words count,
when a cue is full or ends, how its lines break, how long it holds, and adds a caption over a card.
"""

import json
import textwrap

from .edl import Timeline
from .events import is_filler


def spoken(tl, clip, word, fillers=False):
    """Output (start, end) of a word, or None when the edit drops it. fillers: keep a filler word."""

    def kept(t):
        row = tl.row(clip, t)
        return row is not None and row[2]["kind"] in ("speech", "cut") and tl.to_out(clip, t) is not None

    row = tl.row(clip, word["start"])
    end = max(word["start"], word["end"] - 0.01)
    # DTW starts can run early, so a word that starts in a pause and ends in speech is still said
    if (not fillers and is_filler(word["word"])) or row is None or row[2]["kind"] == "filler":
        return None
    if not (kept(word["start"]) or kept(end)):
        return None
    a = tl.to_out(clip, word["start"], snap=True)
    return a, max(tl.to_out(clip, end, snap=True) or a, a + 0.05)


def started(tl, clip, word, fillers=False):
    """Output (start, end) of a word whose start plays in a speech or pause segment, else None.

    It ends where the edit plays its end less 0.02 s, or 0.25 s after its start when that is not played.
    """

    def heard(t):
        row = tl.row(clip, t)
        return None if row is None or row[2]["kind"] in ("cut", "filler") else tl.to_out(clip, t)

    if (not fillers and is_filler(word["word"])) or (a := heard(word["start"])) is None:
        return None
    b = heard(max(word["start"], word["end"] - 0.02))
    return a, b if b is not None and b > a else a + 0.25


def output_words(cfg, tl):
    """[(start, end, word)] of every kept word, in output order.

    captions.words = "spoken" (spoken()): starts never go backwards. "start" (started()): sorted by start,
    and a word with no text is left out.
    """
    style, out = cfg.captions, []
    for clip in (c for c in cfg.clips if not c["card"]):
        for word in json.loads(cfg.f(clip, "words.json").read_text()):
            if style["words"] == "start":
                if (text := word["word"].strip()) and (span := started(tl, clip["name"], word, style["fillers"])):
                    out.append((*span, text))
            elif span := spoken(tl, clip["name"], word, style["fillers"]):
                start = max(span[0], out[-1][0] if out else 0.0)
                out.append((start, max(span[1], start + 0.05), word["word"]))
    return sorted(out) if style["words"] == "start" else out


def split_lines(text, width, split="greedy"):
    """greedy: textwrap at width. balanced: one line up to width, else two, broken at the last space before
    the middle plus 8 characters."""
    if split == "greedy":
        return textwrap.wrap(text, width)
    if len(text) <= width:
        return [text]
    i = text.rfind(" ", 0, len(text) // 2 + 8)
    i = i if i > 0 else text.find(" ")
    return [text] if i < 0 else [text[:i], text[i + 1 :]]


def cues(words, width=42, lines=2, gap=1.0, min_s=1.0, **style):
    """Group (start, end, word) into [start, end, [lines]] captions.

    style holds the [captions] keys fill, split, max_s, sentence_chars, clear_s and squeeze_s (their defaults
    are the original style), and fixed: [start, end, [lines]] cues placed among the words' cues (cards).
    """
    fill, split = style.get("fill", "wrap"), style.get("split", "greedy")
    max_s, sentence = style.get("max_s", 0.0), style.get("sentence_chars", width // 2)
    clear, squeeze = style.get("clear_s", 0.0), style.get("squeeze_s", 0.0)
    out, cur = [], []

    def full(text):
        return len(text) > width * lines if fill == "chars" else len(textwrap.wrap(text, width)) > lines

    def flush():
        if cur:
            out.append([cur[0][0], cur[-1][1], split_lines(" ".join(w for _, _, w in cur), width, split)])
            cur.clear()

    for a, b, w in words:
        text = " ".join([x[2] for x in cur] + [w])
        if cur and (a - cur[-1][1] > gap or full(text) or (max_s and b - cur[0][0] > max_s)):
            flush()
            text = w
        cur.append((a, b, w))
        if w[-1] in ".?!" and len(text) >= sentence:
            flush()
    flush()
    if fixed := style.get("fixed"):
        out = sorted(out + [[a, b, list(t)] for a, b, t in fixed], key=lambda cue: (cue[0], cue[1]))
    prev = 0.0
    for cue, nxt in zip(out, out[1:] + [None], strict=True):  # hold short captions, never into the next one
        cue[0] = max(cue[0], prev)  # only a held cue (squeeze_s) moves the next one
        cue[1] = max(cue[1], cue[0] + min_s)
        if nxt and (not squeeze or nxt[0] > cue[0] + squeeze):
            cue[1] = min(cue[1], nxt[0] - clear)
        prev = cue[1]
    return out


def card_cues(cfg, tl):
    """[start, end, lines] over each card clip named in captions.cards, inset from the card's ends."""
    inset, out = cfg.captions["card_inset_s"], []
    for name, lines in cfg.captions["cards"].items():
        rows = tl.by_clip[name][1]
        out.append([rows[0][0] + inset, rows[-1][1] - inset, lines])
    return out


def build(cfg):
    """The captions of a talk: [start, end, [lines]] on the output clock."""
    r, c, tl = cfg.rules, cfg.captions, Timeline.load(cfg)
    style = {k: c[k] for k in ("fill", "split", "max_s", "sentence_chars", "clear_s", "squeeze_s")}
    words = output_words(cfg, tl)
    return cues(
        words, r["caption_chars"], r["caption_lines"], c["gap_s"], c["min_s"], fixed=card_cues(cfg, tl), **style
    )


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
    found = build(cfg)
    cfg.out.parent.mkdir(parents=True, exist_ok=True)
    cfg.out.with_suffix(".srt").write_text(srt(found))
    cfg.out.with_suffix(".vtt").write_text(vtt(found))
    print(f"{len(found)} captions -> {cfg.out.with_suffix('.srt')} and .vtt")
