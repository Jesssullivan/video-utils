"""What a render voices, and nothing else (`python -m narrate spoken`, TIN-7097).

The input goes through the same adapter a render uses (narrate/adapters.py) to the script IR, and only the IR's
segment text is printed: the written text the lexical pass checks, before spoken normalisation. Front matter,
headings, lines wholly in [brackets] (`[at 0:12: ...]`, `[clip: ...]`, `[pause]`), HTML comments, inline markup,
everything from a `Sources:` line on, cue numbers and timings, speaker labels and WebVTT tags never reach it.
A prose checker such as `xoxd-lexical check --register narration -` then sees spoken text only.

`python -m narrate.spoken lexical [CONFIG]` prints the release directory a render pins (NARRATE_LEXICAL_DIR,
else `lexical` in CONFIG, default narrate.toml) and the release string that release reports, one per line, for
`just narrate-lexical-check`. It exits 3 with no output when neither names a directory.

- lines: one voiced paragraph per line, a blank line between paragraphs, so a checker reads each cue, turn or
  slide paragraph as its own paragraph and never runs a sentence across two of them.
- json: [{id, text}] per segment, with start_s and dur_s for a timed segment, speaker for a named one and
  origin (such as "line 4" or "lines 6-20") where the segment came from in the input.
- srt: one cue per segment; only an input with cue times (SRT, WebVTT, condense words.json) has them.
"""

import json
import os
import re
import sys
import tomllib
from pathlib import Path

from .adapters import InputError
from .config import LEXICAL_ENV

FORMATS = ("lines", "json", "srt")
SUFFIX_KINDS = {
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".srt": "Srt",
    ".vtt": "Vtt",
    ".json": "CondenseWords",
}


def kind_for(path):
    """The adapter an input's file name implies. Dialog is never inferred: name it with --adapter."""
    return SUFFIX_KINDS.get(path.suffix.lower(), "PlainText")


def lines(script):
    paragraphs = [p.strip() for segment in script.segments for p in segment.paragraphs()]
    return "\n\n".join(paragraphs) + "\n"


def records(script):
    out = []
    for segment in script.segments:
        record = {"id": segment.id, "text": segment.text}
        if segment.target_start is not None:
            record["start_s"] = segment.target_start
        if segment.target_dur is not None and segment.target_start is not None:
            record["dur_s"] = segment.target_dur
        if segment.speaker is not None:
            record["speaker"] = segment.speaker
        if segment.origin:
            record["origin"] = segment.origin
        out.append(record)
    return out


def timestamp(seconds):
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def srt(script):
    untimed = [s.id for s in script.segments if s.target_start is None or s.target_dur is None]
    if untimed:
        raise InputError(
            f"srt needs cue times; {script.kind} segment {untimed[0]} has none (use --format lines or json)"
        )
    cues = []
    for number, segment in enumerate(script.segments, 1):
        start, end = segment.target_start, segment.target_start + segment.target_dur
        text = "\n".join(p.strip() for p in segment.paragraphs())
        cues.append(f"{number}\n{timestamp(start)} --> {timestamp(end)}\n{text}\n")
    return "\n".join(cues)


def render(script, form):
    if form == "lines":
        return lines(script)
    if form == "json":
        return json.dumps(records(script), indent=1, ensure_ascii=False) + "\n"
    if form == "srt":
        return srt(script)
    raise InputError(f"format {form!r}: one of {', '.join(FORMATS)}")


def lexical_dir(config="narrate.toml"):
    """The release directory a render reads: NARRATE_LEXICAL_DIR, else `lexical` in the config; else None."""
    if os.environ.get(LEXICAL_ENV):
        return Path(os.environ[LEXICAL_ENV]).resolve()
    path = Path(config)
    if not path.is_file():
        return None
    value = tomllib.loads(path.read_text(encoding="utf-8")).get("lexical", "")
    return (path.resolve().parent / value).resolve() if value else None


def release_string(directory):
    """The string `xoxd-lexical version` prints for this release directory, read the way the CLI reads it."""
    directory = Path(directory)
    full = directory / "estate-lexicon-full.json"
    source = full if full.is_file() else directory / "estate-lexicon.json"
    release = "xoxd-lexical@" + str(json.loads(source.read_text(encoding="utf-8"))["version"])
    digests = directory / "DIGESTS"
    if digests.is_file():
        match = re.search(r"^release\s+(\S+)", digests.read_text(encoding="utf-8"), re.M)
        if match:
            release = match.group(1)
    return release


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] != "lexical" or len(argv) > 2:
        print("usage: python -m narrate.spoken lexical [CONFIG]", file=sys.stderr)
        return 2
    directory = lexical_dir(*argv[1:])
    if directory is None:
        return 3
    print(directory)
    print(release_string(directory) if (directory / "estate-lexicon.json").is_file() else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
