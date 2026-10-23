"""Input adapters: plain text, a markdown manuscript, SRT, WebVTT, condense words.json and SPEAKER: dialog.

Each returns an ir.Script. None of them changes its input; a condense run is read, never written.

- PlainText: one segment per paragraph (blank-line separated); lines of a paragraph join with a space.
- Markdown: one slide manuscript per file and one segment per file. Front matter `slide` and `target_seconds`
  are read (a small `key: value` subset of YAML). Only text before a `Sources:` line is spoken. A line wholly
  in [brackets] is a direction, never spoken; `[pause]`, `[pause 2s]`, `[pause 800ms]` or `[pause for ...]`
  add a pause. Headings, HTML comments and inline markup are not spoken; a link reads as its text.
- Srt / Vtt: one segment per cue, with target_start and target_dur. A WebVTT `<v Name>` span names the
  speaker. Tags are dropped.
- CondenseWords: a condense `<clip>.words.json` ([{start, end, word}] on the clip's analysis clock) grouped into
  sentences; each sentence's times map through the condense edl.json to the edit's output clock.
- Dialog: `NAME: text` lines (NAME in capitals); following lines continue the turn until a blank line.
"""

import json
import re
from pathlib import Path

from .ir import Direction, Script, Segment

KINDS = ("PlainText", "Markdown", "Srt", "Vtt", "CondenseWords", "Dialog")
DIRECTION = re.compile(r"^\s*\[([^\[\]]+)\]\s*$")
PAUSE = re.compile(r"^pause\b(?:\s+(\d+(?:\.\d+)?)\s*(ms|s)\b)?", re.IGNORECASE)
SOURCES = re.compile(r"^\s*(?:\*\*|__)?Sources?\s*:", re.IGNORECASE)
SPEAKER = re.compile(r"^([A-Z][A-Z0-9_ .'-]{0,31}):\s+(.*\S)\s*$")
TIME = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[,.](\d{3})")
CUE_TIMES = re.compile(rf"^\s*({TIME.pattern})\s+-->\s+({TIME.pattern})")


class InputError(ValueError):
    """The input cannot become a script. The message names the line or cue."""


def load(kind, path, options=None):
    """The script for one input file of a job's input kind."""
    options = options or {}
    path = Path(path)
    if kind not in KINDS:
        raise InputError(f"input kind {kind!r}: one of {', '.join(KINDS)}")
    if kind == "CondenseWords":
        return condense_words(
            path, options.get("edl") or None, options.get("clip") or None, float(options.get("sentence_gap_s", 1.0))
        )
    text = path.read_text(encoding="utf-8")
    return {"PlainText": plain_text, "Markdown": markdown, "Srt": srt, "Vtt": vtt, "Dialog": dialog}[kind](
        text, name=path.stem
    )


def spoken(line):
    """One line's speakable text: inline markup, links and HTML tags dropped, whitespace collapsed."""
    line = re.sub(r"<!--.*?-->", " ", line)
    line = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", line)  # an image reads as its alt text
    line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
    line = re.sub(r"`([^`]*)`", r"\1", line)
    line = re.sub(r"(\*\*|__)(.+?)\1", r"\2", line)
    line = re.sub(r"(?<![\w*])([*_])(?!\s)(.+?)(?<!\s)\1(?![\w*])", r"\2", line)
    line = re.sub(r"<[^>]+>", " ", line)
    return " ".join(line.split())


def direction(text, paragraph):
    match = PAUSE.match(text.strip())
    if not match:
        return Direction(text=text.strip(), paragraph=paragraph)
    ms = None
    if match.group(1):
        ms = round(float(match.group(1)) * (1 if match.group(2).lower() == "ms" else 1000))
    return Direction(text=text.strip(), paragraph=paragraph, kind="pause", pause_ms=ms)


def plain_text(text, name="input"):
    segments, block, start = [], [], 0
    lines = text.splitlines() + [""]
    for number, line in enumerate(lines, 1):
        if line.strip():
            if not block:
                start = number
            block.append(line.strip())
        elif block:
            segments.append(Segment(id=f"p{len(segments) + 1:04d}", text=" ".join(block), origin=f"line {start}"))
            block = []
    if not segments:
        raise InputError(f"{name}: no paragraph to speak")
    return Script(kind="PlainText", segments=tuple(segments), meta={"paragraphs": len(segments)})


def front_matter(lines):
    """({key: value}, index of the first body line). Only `key: value` lines; a number reads as a number."""
    if not lines or lines[0].strip() != "---":
        return {}, 0
    meta = {}
    for index, line in enumerate(lines[1:], 1):
        if line.strip() in ("---", "..."):
            return meta, index + 1
        key, sep, value = line.partition(":")
        if not sep or not key.strip() or key.startswith((" ", "\t", "#")):
            if line.strip() and not line.lstrip().startswith("#"):
                raise InputError(f"front matter line {index + 1}: only `key: value` is read")
            continue
        value = value.strip().strip("\"'")
        try:
            meta[key.strip()] = float(value) if re.fullmatch(r"-?\d+(?:\.\d+)?", value) else value
        except ValueError:
            meta[key.strip()] = value
    raise InputError("front matter opened with --- is never closed")


def markdown(text, name="slide"):
    lines = text.splitlines()
    meta, first = front_matter(lines)
    target = meta.get("target_seconds")
    if target is not None and (not isinstance(target, float) or target <= 0):
        raise InputError(f"{name}: target_seconds = {target!r}: a number of seconds above 0")
    slide = str(meta.get("slide", name))
    if isinstance(meta.get("slide"), float) and meta["slide"].is_integer():
        slide = str(int(meta["slide"]))
    paragraphs, directions, block, ended, in_comment = [], [], [], None, False
    for number, line in enumerate(lines[first:], first + 1):
        if in_comment:
            in_comment = "-->" not in line
            continue
        if line.strip().startswith("<!--") and "-->" not in line:
            in_comment = True
            continue
        if SOURCES.match(line):
            ended = number
            break
        if not line.strip():
            if block:
                paragraphs.append(" ".join(block))
                block = []
            continue
        if line.lstrip().startswith("#"):
            continue  # a heading titles the slide; it is not narration
        found = DIRECTION.match(line)
        if found:
            if block:
                paragraphs.append(" ".join(block))
                block = []
            directions.append(direction(found.group(1), len(paragraphs)))
            continue
        said = spoken(line)
        if said:
            block.append(said)
    if block:
        paragraphs.append(" ".join(block))
    if not paragraphs:
        raise InputError(f"{name}: no narration before Sources:")
    segment = Segment(
        id=f"slide-{slide}",
        text="\n\n".join(paragraphs),
        target_dur=target,
        directions=tuple(directions),
        origin=f"lines {first + 1}-{(ended or len(lines) + 1) - 1}",
    )
    info = {"slide": slide, "target_seconds": target, "sources_line": ended, "paragraphs": len(paragraphs)}
    return Script(kind="Markdown", segments=(segment,), meta=info)


def seconds(match_groups):
    hours, minutes, secs, millis = match_groups
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(secs) + int(millis) / 1000


def cue_blocks(text):
    """[(first line number, [lines])] separated by blank lines."""
    blocks, block, start = [], [], 0
    for number, line in enumerate(text.splitlines() + [""], 1):
        if line.strip():
            if not block:
                start = number
            block.append(line.rstrip())
        elif block:
            blocks.append((start, block))
            block = []
    return blocks


def cues(blocks, kind, name):
    segments, last_end = [], 0.0
    for start, block in blocks:
        timing = next((i for i, line in enumerate(block) if "-->" in line), None)
        if timing is None:
            raise InputError(f"{name}: line {start}: a cue without a --> timing line")
        found = CUE_TIMES.match(block[timing])
        if not found:
            raise InputError(f"{name}: line {start + timing}: unreadable cue timing {block[timing]!r}")
        groups = found.groups()
        a, b = seconds(groups[1:5]), seconds(groups[6:10])
        if b <= a:
            raise InputError(f"{name}: line {start + timing}: the cue ends at or before its start")
        if a < last_end - 1e-9:
            raise InputError(f"{name}: line {start + timing}: the cue starts before the previous cue ends")
        last_end = b
        speaker, words = None, []
        for line in block[timing + 1 :]:
            voice = re.search(r"<v(?:\.[\w.-]+)?\s+([^>]+)>", line)
            if voice:
                speaker = voice.group(1).strip()
            said = spoken(line)
            if said:
                words.append(said)
        if not words:
            continue  # an empty cue is a gap, not a segment
        segments.append(
            Segment(
                id=f"cue-{len(segments) + 1:04d}",
                text=" ".join(words),
                speaker=speaker,
                target_start=round(a, 3),
                target_dur=round(b - a, 3),
                origin=f"line {start}",
            )
        )
    if not segments:
        raise InputError(f"{name}: no cue with text")
    return Script(kind=kind, segments=tuple(segments), meta={"cues": len(segments)})


def srt(text, name="captions"):
    return cues(cue_blocks(text.lstrip("﻿")), "Srt", name)


def vtt(text, name="captions"):
    text = text.lstrip("﻿")
    if not text.startswith("WEBVTT"):
        raise InputError(f"{name}: a WebVTT file starts with WEBVTT")
    blocks = [b for b in cue_blocks(text)[1:] if not b[1][0].startswith(("NOTE", "STYLE", "REGION"))]
    return cues(blocks, "Vtt", name)


def dialog(text, name="dialog"):
    segments, turn, start = [], None, 0

    def close():
        if turn and turn[1]:
            segments.append(
                Segment(
                    id=f"turn-{len(segments) + 1:04d}", text=" ".join(turn[1]), speaker=turn[0], origin=f"line {start}"
                )
            )

    for number, line in enumerate(text.splitlines(), 1):
        found = SPEAKER.match(line)
        if found:
            close()
            turn, start = (found.group(1).strip(), [spoken(found.group(2))]), number
        elif not line.strip():
            close()
            turn = None
        elif turn is None:
            raise InputError(f"{name}: line {number}: a line outside any SPEAKER: turn")
        else:
            turn[1].append(spoken(line))
    close()
    if not segments:
        raise InputError(f"{name}: no SPEAKER: line")
    return Script(
        kind="Dialog",
        segments=tuple(segments),
        meta={"turns": len(segments), "speakers": sorted({s.speaker for s in segments})},
    )


def sentences(words, gap_s):
    """Runs of words, each ending at a sentence mark or before a gap longer than gap_s."""
    group = []
    for i, word in enumerate(words):
        group.append(word)
        last = i + 1 == len(words)
        gap = not last and words[i + 1]["start"] - word["end"] > gap_s
        if last or gap or re.search(r"[.!?][\"')\]]*$", word["word"].strip()):
            yield group
            group = []


def condense_words(path, edl_path, clip, gap_s):
    words = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(words, list) or not all(
        isinstance(w, dict) and {"start", "end", "word"} <= set(w) for w in words
    ):
        raise InputError(f"{path}: not a condense words.json ([{{start, end, word}}])")
    words = sorted((w for w in words if str(w["word"]).strip()), key=lambda w: w["start"])
    if not words:
        raise InputError(f"{path}: no words")
    timeline, mapping = None, "source_clock"
    if edl_path:
        from condense.edl import Timeline  # the condense time map; stdlib only

        edl = json.loads(Path(edl_path).read_text(encoding="utf-8"))
        timeline, mapping = Timeline(edl), "condense_edl"
        names = [c["name"] for c in edl["clips"]]
        clip = clip or (names[0] if len(names) == 1 else None)
        if clip not in names:
            raise InputError(f"{edl_path}: name the clip the words came from (input_options.clip): {names}")
    segments, index = [], 0
    for group in sentences(words, gap_s):
        a, b = group[0]["start"], group[-1]["end"]
        if timeline is not None:
            out_a, out_b = timeline.to_out(clip, a, snap=True), timeline.to_out(clip, b, snap=True)
            if out_a is None or out_b is None:
                raise InputError(f"{path}: words {index + 1}-{index + len(group)} fall outside the edit")
            a, b = out_a, out_b
        text = " ".join(str(w["word"]).strip() for w in group)
        segments.append(
            Segment(
                id=f"words-{len(segments) + 1:04d}",
                text=text,
                target_start=round(a, 3),
                target_dur=round(max(b - a, 0.05), 3),
                origin=f"words {index + 1}-{index + len(group)}",
            )
        )
        index += len(group)
    meta = {"mapping": mapping, "clip": clip, "words": len(words), "sentence_gap_s": gap_s}
    if edl_path:
        from .ir import sha256_file

        meta["edl_sha256"] = sha256_file(edl_path)
    return Script(kind="CondenseWords", segments=tuple(segments), meta=meta)
