"""The fixed chunk list of the narrate engine bench, made once from text-v1 and committed.

Chunking (bench plan, "Arms"): the text splits at sentence boundaries and sentences pack greedily into chunks of
at most 300 codepoints, never across a section boundary. Each `## sN Title` section of text-v1.md is one narrate
script segment whose paragraphs are joined into one paragraph, so narrate's own chunker (narrate/chunker.py)
packs sentences across the section's paragraphs (the s3 dialog would otherwise become one tiny chunk per
line) and never across sections. Front matter, headings and HTML comments are not spoken.

`python3 narrate/bench/prepare.py` writes narrate/bench/chunks-v1.json; `--check` exits 1 when the committed file
differs from what the text and the chunker make now. The GPU host never imports narrate: host_run.py reads the
committed JSON and checks its sha256. Plan: docs/agent-notes/2026-10-22-narrate-bench-plan.md.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT = Path(__file__).resolve().parent / "text-v1.md"
OUT = Path(__file__).resolve().parent / "chunks-v1.json"
TEXT_SHA256 = "f7ff6923899b72ade8da6f84678ca9bff81bc3d8ee61b70bda908b95951a704d"  # the preregistered text-v1
LIMIT = 300
WPM = 150  # the bench's expected speaking rate for the "longer than twice expected" catastrophic rule
SECTION = re.compile(r"^##\s+(s\d+)\b.*$", re.MULTILINE)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sections(text):
    """[(section id, spoken text)] of text-v1: one paragraph per section, whitespace collapsed."""
    body = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.DOTALL)
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.DOTALL)
    marks = list(SECTION.finditer(body))
    out = []
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        out.append((mark.group(1), " ".join(body[mark.end() : end].split())))
    return out


def build(text_path=TEXT, limit=LIMIT):
    sys.path.insert(0, str(ROOT))
    from narrate.chunker import chunk_segment
    from narrate.ir import Segment

    raw = Path(text_path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != TEXT_SHA256:
        raise SystemExit(f"text-v1 sha256 {digest} is not the preregistered {TEXT_SHA256}: a new text is a new bench")
    chunks = []
    for section, spoken in sections(raw.decode("utf-8")):
        for chunk in chunk_segment(Segment(id=section, text=spoken), limit):
            if chunk.oversize:
                raise SystemExit(f"chunk {chunk.id} is longer than {limit} codepoints")
            words = len(chunk.text.split())
            chunks.append(
                {
                    "id": chunk.id,
                    "section": section,
                    "text": chunk.text,
                    "codepoints": len(chunk.text),
                    "words": words,
                    "expected_s": round(words * 60 / WPM, 2),
                }
            )
    return {
        "schema": "narrate-bench-chunks/1",
        "text": "narrate/bench/text-v1.md",
        "text_sha256": digest,
        "limit_codepoints": limit,
        "expected_wpm": WPM,
        "chunker": "narrate/chunker.py chunk_segment, one segment per ## section with its paragraphs joined",
        "chunks_sha256": hashlib.sha256(canonical(chunks).encode("utf-8")).hexdigest(),
        "chunks": chunks,
    }


def render(doc):
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 when the committed chunk list is stale")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    text = render(build())
    if args.check:
        current = args.out.read_text(encoding="utf-8") if args.out.is_file() else ""
        if current != text:
            print(f"{args.out} is stale: run python3 narrate/bench/prepare.py", file=sys.stderr)
            return 1
        print(f"{args.out.name} is current")
        return 0
    args.out.write_text(text, encoding="utf-8")
    doc = json.loads(text)
    print(f"{len(doc['chunks'])} chunks, chunks_sha256 {doc['chunks_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
