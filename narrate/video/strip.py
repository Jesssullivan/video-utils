"""Metadata stripping and its check for composed outputs (docs/spec/NARRATED_VIDEO.md, "Compose and delivery",
TIN-7788).

compose encodes with -map_metadata -1, -map_chapters -1 and the bit-exact flags, so no title, comment, creator,
creation time, chapter or encoder version passes from an input to video.mp4 or video.upload.mp4. Then it checks
what the files hold, and refuses metadata_present when:

- a container or stream tag is outside MEDIA_TAGS (the brand fields, a three-letter language, the muxer's default
  handler names and FFmpeg's bit-exact encoder name), or a chapter remains;
- the file's bytes hold an XMP packet, an EXIF block or a local path (the job store, the private store, the records
  directory or the home directory);
- a text output (compose.json, chapters.json, description.txt, captions) holds a local path.

handoff writes each slide layer through strip_png: a PNG keeps its critical chunks and the colour chunks in
PNG_KEEP, and loses every text, EXIF, ICC profile, time and unknown chunk. Its pixels and their bytes stay the same.

A refusal names the file and the tag key or the kind of finding, never a tag value or a path.
"""

import json
import re
import struct
import zlib
from pathlib import Path

from .common import StageRefused, run

FORMAT_TAGS = {
    "major_brand": re.compile(r"^[a-z0-9 ]{4}$"),
    "minor_version": re.compile(r"^[0-9]{1,10}$"),
    "compatible_brands": re.compile(r"^[a-z0-9 ]{4,64}$"),
}
STREAM_TAGS = {
    "language": re.compile(r"^[a-z]{3}$"),
    "handler_name": re.compile(r"^(?:VideoHandler|SoundHandler|SubtitleHandler)$"),
    "vendor_id": re.compile(r"^\[0\]\[0\]\[0\]\[0\]$"),
    "encoder": re.compile(r"^Lavc(?: [a-z0-9_]{1,32})?$"),  # bit-exact: no version
}
# Byte markers of embedded metadata blocks: an XMP packet and an EXIF header.
MARKERS = {"xmp": (b"<x:xmpmeta", b"http://ns.adobe.com/xap/1.0/"), "exif": (b"Exif\x00\x00",)}
CHUNK = 1 << 20
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PNG_CRITICAL = {b"IHDR", b"PLTE", b"IDAT", b"IEND"}
PNG_KEEP = {b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"sBIT", b"pHYs", b"bKGD"}


def refuse(name, what):
    raise StageRefused("metadata_present", f"{name} {what}")


def local_roots(*paths):
    """The local paths an output must not say: each given directory that exists and the home directory, as text."""
    roots = {str(Path(p).resolve()) for p in paths if p is not None}
    home = Path.home()
    if home != Path("/") and home.is_dir():
        roots.add(str(home.resolve()))
    return sorted(r for r in roots if len(r) > 1)


def probe_tags(path):
    """(format tags, [stream tags], chapter count) as ffprobe reads them."""
    try:
        done = run(
            "ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", "-show_chapters",
            str(path), timeout=120,
        )  # fmt: skip
        doc = json.loads(done.stdout)
    except (RuntimeError, ValueError) as exc:
        raise StageRefused("ffprobe_failed", str(exc).splitlines()[0][:200], verdict=False) from None
    streams = [s.get("tags") or {} for s in doc.get("streams") or []]
    return (doc.get("format") or {}).get("tags") or {}, streams, len(doc.get("chapters") or [])


def scan_bytes(path, needles):
    """The kinds of needle ({kind: [bytes]}) that occur in path's bytes, read in chunks with an overlap."""
    longest = max((len(n) for ns in needles.values() for n in ns), default=1)
    found, tail = set(), b""
    with open(path, "rb") as f:
        while block := f.read(CHUNK):
            window = tail + block
            for kind, ns in needles.items():
                if kind not in found and any(n in window for n in ns):
                    found.add(kind)
            tail = window[-(longest - 1) :] if longest > 1 else b""
    return found


def check_media(path, roots):
    """A metadata report for one composed MP4: {format_tags, stream_tags, chapters}, each tag by key. Refuses
    metadata_present on a tag outside the allowlist, a chapter, an XMP or EXIF block, or a local path."""
    name = Path(path).name
    format_tags, streams, chapters = probe_tags(path)
    for key, value in format_tags.items():
        allowed = FORMAT_TAGS.get(key)
        if allowed is None or not allowed.match(str(value)):
            refuse(name, f"keeps the container tag {key}")
    for n, tags in enumerate(streams):
        for key, value in tags.items():
            allowed = STREAM_TAGS.get(key)
            if allowed is None or not allowed.match(str(value)):
                refuse(name, f"keeps the tag {key} on stream {n}")
    if chapters:
        refuse(name, f"keeps {chapters} chapters")
    needles = dict(MARKERS) | {"path": tuple(r.encode() for r in roots)}
    found = scan_bytes(path, needles)
    if found:
        refuse(name, "holds " + " and ".join(f"an embedded {k} block" if k != "path" else "a local path"
                                             for k in sorted(found)))  # fmt: skip
    return {
        "format_tags": sorted(format_tags),
        "stream_tags": [sorted(t) for t in streams],
        "chapters": 0,
    }


def check_text(path, roots):
    """Refuse metadata_present when a text output holds a local path."""
    if any(root in Path(path).read_text(encoding="utf-8", errors="replace") for root in roots):
        refuse(Path(path).name, "holds a local path")


def png_chunks(data):
    """[(type, body)] of a PNG's chunks, or None when data is not a well-formed PNG."""
    if not data.startswith(PNG_MAGIC):
        return None
    out, at = [], len(PNG_MAGIC)
    while at + 12 <= len(data):
        (length,) = struct.unpack(">I", data[at : at + 4])
        kind = data[at + 4 : at + 8]
        end = at + 12 + length
        if end > len(data):
            return None
        body = data[at + 8 : at + 8 + length]
        if struct.unpack(">I", data[at + 8 + length : end])[0] != zlib.crc32(kind + body):
            return None
        out.append((kind, body))
        at = end
        if kind == b"IEND":
            return out  # bytes after IEND are dropped with the rest
    return None


def strip_png(data):
    """(the PNG bytes with only its critical chunks and PNG_KEEP, [dropped chunk types]), or None when data is not
    a well-formed PNG."""
    chunks = png_chunks(data)
    if chunks is None or not chunks or chunks[0][0] != b"IHDR" or chunks[-1][0] != b"IEND":
        return None
    kept, dropped = [PNG_MAGIC], []
    for kind, body in chunks:
        if kind in PNG_CRITICAL or kind in PNG_KEEP:
            kept.append(struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body)))
        else:
            dropped.append(kind.decode("latin-1"))
    return b"".join(kept), sorted(set(dropped))
