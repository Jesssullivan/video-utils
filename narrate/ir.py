"""The script IR every input adapter produces (docs/spec/NARRATE.md, "Dataflow" step 1).

A script is a list of segments. A segment is what one speaker says as one block: a paragraph of plain text,
a slide's manuscript, a caption cue, a sentence of a condensed talk or a dialog turn. Its text holds
paragraphs separated by a blank line. Directions are never spoken; each sits at a paragraph boundary and may
carry a pause. Ids are stable across runs of the same input: they come from the input's structure only.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Direction:
    text: str  # the direction without its brackets, such as "pause for the diagram"
    paragraph: int  # it sits before this paragraph index of the segment's text (len(paragraphs) = at the end)
    kind: str = "note"  # "pause" adds silence at its place; any other direction is recorded only
    pause_ms: int | None = None  # a pause's explicit length; None takes the job's paragraphPauseMs


@dataclass(frozen=True)
class Segment:
    id: str
    text: str
    speaker: str | None = None  # a dialog speaker name; None reads in the job's voice
    target_start: float | None = None  # seconds on the output clock
    target_dur: float | None = None  # seconds the segment should fill
    directions: tuple[Direction, ...] = field(default_factory=tuple)
    origin: str = ""  # where in the input it came from: "line 4", "cue 3", "words 10-24"

    def paragraphs(self):
        return [p for p in self.text.split("\n\n") if p.strip()]


@dataclass(frozen=True)
class Script:
    kind: str  # the job's Input: PlainText, Markdown, Srt, Vtt, CondenseWords or Dialog
    segments: tuple[Segment, ...]
    meta: dict = field(default_factory=dict)  # adapter facts: slide id, cue count, words mapping

    def to_json(self):
        return {"kind": self.kind, "meta": self.meta, "segments": [asdict(s) for s in self.segments]}

    def digest(self):
        return sha256_text(canonical(self.to_json()))


def canonical(value):
    """The bytes every digest of a JSON value is taken over: sorted keys, no spaces, UTF-8."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
