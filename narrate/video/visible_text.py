"""The visible text of a demo bundle's slide and plot assets (docs/spec/NARRATED_VIDEO.md, "Private terms", TIN-7788).

A PNG slide or plot, or an MP4 clip, shows text the script never says: a title, axis labels, a legend, tick values.
The private-terms guard reads no pixels, and this repository has no OCR dependency. So a bundle names the text an
asset shows in a text source beside it, bound by digest in the manifest (`text: {path, sha256}`):

  .svg   the vector the picture was drawn from. Every run of character data and every comment counts (a plotting
         library that draws glyphs as paths writes each label as a comment beside them), and so do the aria-label
         and xlink:title attributes. The metadata, style and script elements are skipped: none of them is drawn.
  .json  {"kind": "nv_asset_text", "schema_version": 1, "texts": ["...", ...]}: the strings the producer drew.

texts() returns the strings; the guard reads them joined, one text per asset, so a term split across two labels
still matches. An SVG with a document type declaration (and so any entity definition) refuses, as does a malformed
file. Errors name the field or the rule, never a text from the file.

Standard library only.
"""

import json
import xml.etree.ElementTree as ET
from decimal import Decimal

KIND, SCHEMA_VERSION = "nv_asset_text", 1
SUFFIXES = (".svg", ".json")
MAX_BYTES = 4 * 1024 * 1024
MAX_TEXTS = 10_000
MAX_TEXT = 4096
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
SKIPPED = {"metadata", "style", "script"}  # never drawn
LABEL_ATTRIBUTES = {"aria-label", f"{{{XLINK_NS}}}title"}


class TextSourceError(ValueError):
    """A text source that cannot be read. The message names a rule, never the file's text."""


def kind_of(path):
    """svg or json from a text source's path, or None."""
    lower = str(path).lower()
    return next((s[1:] for s in SUFFIXES if lower.endswith(s)), None)


def local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else None


def svg_texts(data):
    """The strings an SVG draws or labels, in document order."""
    head = data[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in data.lower():
        raise TextSourceError("an SVG text source holds a document type or entity declaration")
    try:
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
        parser.feed(data)
        root = parser.close()
    except ET.ParseError:
        raise TextSourceError("the SVG text source is not well-formed XML") from None
    if local(root.tag) != "svg" or not root.tag.startswith((f"{{{SVG_NS}}}", "svg")):
        raise TextSourceError("the SVG text source's root element is not svg")
    out = []

    def add(text):
        if isinstance(text, str) and text.strip():
            out.append(text.strip())

    def walk(element):
        comment = element.tag is ET.Comment
        if not comment and local(element.tag) in SKIPPED:
            return
        add(element.text)
        if not comment:
            for name in sorted(element.attrib):
                if name in LABEL_ATTRIBUTES:
                    add(element.attrib[name])
            for child in element:
                walk(child)
                add(child.tail)

    walk(root)
    return out


def no_duplicates(pairs):
    keys = [k for k, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("a key repeats in one object")
    return dict(pairs)


def json_texts(data):
    """The strings an nv_asset_text file lists."""
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=no_duplicates, parse_float=Decimal)
    except (UnicodeDecodeError, ValueError):
        raise TextSourceError("the JSON text source is not UTF-8 JSON with distinct keys") from None
    if not isinstance(value, dict) or set(value) != {"kind", "schema_version", "texts"}:
        raise TextSourceError("the JSON text source is not {kind, schema_version, texts}")
    if value["kind"] != KIND or value["schema_version"] != SCHEMA_VERSION:
        raise TextSourceError(f"the JSON text source is not {KIND} schema {SCHEMA_VERSION}")
    texts = value["texts"]
    if not isinstance(texts, list) or len(texts) > MAX_TEXTS:
        raise TextSourceError(f"texts is not a list of at most {MAX_TEXTS} strings")
    if not all(isinstance(t, str) and len(t) <= MAX_TEXT for t in texts):
        raise TextSourceError(f"texts holds an entry that is not a string of at most {MAX_TEXT} characters")
    return [t.strip() for t in texts if t.strip()]


def texts(path, kind=None):
    """The strings a text source at path shows. kind is svg or json (default: from the suffix)."""
    kind = kind or kind_of(path)
    with open(path, "rb") as f:
        data = f.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise TextSourceError(f"the text source is larger than {MAX_BYTES} bytes")
    if kind == "svg":
        return svg_texts(data)
    if kind == "json":
        return json_texts(data)
    raise TextSourceError("a text source ends in .svg or .json")
