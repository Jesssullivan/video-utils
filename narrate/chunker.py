"""Split each segment into engine-sized chunks (docs/spec/NARRATE.md, "Dataflow" step 4).

A chunk never crosses a paragraph. Inside a paragraph, sentences pack into chunks of at most `limit`
codepoints. A longer sentence splits at the last clause mark (, ; : and dashes) that fits, then at the last
space that fits. No split lands inside a protected span (a number with its unit, a version, an identifier, a
link or a path, as lexical.PROTECTED reads them) or inside a range or dollar amount that spoken normalisation says
in words ("$5 to $10", amounts.find). A single span longer than the limit stays whole and its chunk
is flagged oversize rather than split.
"""

import re
from dataclasses import dataclass

from . import amounts
from .lexical import PROTECTED

ABBREVIATIONS = {"e.g.", "i.e.", "etc.", "vs.", "dr.", "mr.", "mrs.", "ms.", "st.", "no.", "fig.", "approx."}
SENTENCE_END = re.compile(r"[.!?…][\"'”’)\]]*\s+")
CLAUSE = re.compile(r"[,;:—–]\s+|\s-\s")


@dataclass(frozen=True)
class Chunk:
    id: str
    segment: str
    paragraph: int
    text: str
    last_in_paragraph: bool
    oversize: bool = False


def blocked(text):
    """Positions where a split would cut a protected span."""
    inside = set()
    for match in PROTECTED.finditer(text):
        inside.update(range(match.start() + 1, match.end()))
    try:
        spans = [(e.start, e.end) for e in amounts.find(text)]
    except amounts.AmountError:  # spoken normalisation refuses this text with its own error
        spans = []
    for start, end in spans:
        inside.update(range(start + 1, end))
    return inside


def sentences(paragraph):
    """Sentence strings of one paragraph. An abbreviation, an initial or a decimal never ends a sentence."""
    out, start = [], 0
    for match in SENTENCE_END.finditer(paragraph):
        end = match.end()
        head = paragraph[start : match.start() + 1].split()
        word = head[-1].lower() if head else ""
        if word in ABBREVIATIONS or re.fullmatch(r"[a-z]\.", word):
            continue
        out.append(paragraph[start:end].strip())
        start = end
    if paragraph[start:].strip():
        out.append(paragraph[start:].strip())
    return out


def split_long(sentence, limit):
    """[(piece, oversize)] of one sentence longer than limit."""
    pieces = []
    rest = sentence
    while len(rest) > limit:
        cut_forbidden = blocked(rest)
        cut = None
        for regex in (CLAUSE, re.compile(r"\s+")):
            ends = [
                m.end()
                for m in regex.finditer(rest)
                if m.end() <= limit and m.start() not in cut_forbidden and m.start() > 0
            ]
            if ends:
                cut = ends[-1]
                break
        if cut is None:  # no allowed cut fits: the first allowed space after the limit, else the whole rest
            later = [m.end() for m in re.finditer(r"\s+", rest) if m.start() not in cut_forbidden and m.start() > 0]
            if not later:
                break
            cut = later[0]
            pieces.append((rest[:cut].strip(), True))
            rest = rest[cut:]
            continue
        pieces.append((rest[:cut].strip(), False))
        rest = rest[cut:]
    if rest.strip():
        pieces.append((rest.strip(), len(rest.strip()) > limit))
    return pieces


def pack_words(text, fits):
    """[(piece, oversize)]: words joined greedily while fits(piece) holds. Words never split a protected span; a
    single word that does not fit stands alone, flagged oversize."""
    forbidden, words, start = blocked(text), [], 0
    for match in re.finditer(r"\s+", text):
        if match.start() not in forbidden:
            words.append(text[start : match.start()])
            start = match.end()
    words.append(text[start:])
    pieces, current = [], ""
    for word in (w for w in words if w):
        candidate = f"{current} {word}" if current else word
        if current and not fits(candidate):
            pieces.append(current)
            current = word
        else:
            current = candidate
    if current:
        pieces.append(current)
    return [(piece, not fits(piece)) for piece in pieces]


def chunk_segment(segment, limit):
    if limit < 20:
        raise ValueError(f"chunkMaxCodepoints = {limit}: at least 20")
    chunks = []
    paragraphs = segment.paragraphs()
    for p_index, paragraph in enumerate(paragraphs):
        packed, current = [], ""
        for sentence in sentences(" ".join(paragraph.split())):
            if len(sentence) > limit:
                if current:
                    packed.append((current, False))
                    current = ""
                packed += split_long(sentence, limit)
            elif not current:
                current = sentence
            elif len(current) + 1 + len(sentence) <= limit:
                current += " " + sentence
            else:
                packed.append((current, False))
                current = sentence
        if current:
            packed.append((current, False))
        for i, (text, oversize) in enumerate(packed):
            chunks.append(
                Chunk(
                    id=f"{segment.id}.c{len(chunks) + 1:02d}",
                    segment=segment.id,
                    paragraph=p_index,
                    text=text,
                    last_in_paragraph=i == len(packed) - 1,
                    oversize=oversize,
                )
            )
    return chunks


def chunk_script(script, limit):
    return [c for s in script.segments for c in chunk_segment(s, limit)]
