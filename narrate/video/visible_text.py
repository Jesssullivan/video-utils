"""The visible text of a demo bundle's slide and plot assets (docs/spec/NARRATED_VIDEO.md, "Private terms", TIN-7788).

A PNG slide or plot, or an MP4 clip, shows text the script never says: a title, axis labels, a legend, tick values.
The private-terms guard reads no pixels, and this repository has no OCR dependency. So a bundle names the text an
asset shows in a text source beside it, bound by digest in the manifest (`text: {path, sha256}`):

  .svg   the vector the picture was drawn from. Every run of character data and every comment counts (a plotting
         library that draws glyphs as paths writes each label as a comment beside them), and so do the aria-label
         and xlink:title attributes. The metadata, style and script elements are skipped: none of them is drawn.
  .json  {"kind": "nv_asset_text", "schema_version": 1, "texts": ["...", ...]}: the strings the producer drew.

texts() returns the strings and whether the source is opaque; the guard reads the strings joined, one text per
asset, so a term split across two labels still matches. An SVG is opaque when it may draw text no string names: it
holds an image (image, feImage, foreignObject or another embedding element), refers to another file (an href that is
not a #fragment, or url() that is not one), or gives no string at all (text outlined to paths). The intake lists an
opaque asset, so its visible-text state is partial, not passed.

An SVG that is not UTF-8 (a byte-order mark other than UTF-8's, a NUL, or an XML declaration naming another
encoding) refuses, and so does one with a document type or entity declaration anywhere: the decoded text is searched
and the parser refuses one too. A malformed file refuses. Errors name the field or the rule, never a text from the
file.

Standard library only.
"""

import json
import re
import xml.etree.ElementTree as ET
from decimal import Decimal
from typing import NamedTuple
from xml.parsers import expat

KIND, SCHEMA_VERSION = "nv_asset_text", 1
SUFFIXES = (".svg", ".json")
MAX_BYTES = 4 * 1024 * 1024
MAX_TEXTS = 10_000
MAX_TEXT = 4096
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
SKIPPED = {"metadata", "style", "script"}  # never drawn
LABEL_ATTRIBUTES = {"aria-label", f"{{{XLINK_NS}}}title"}
# Elements that draw a picture, a document or another file's content, whose text no string here names.
OPAQUE_ELEMENTS = {"image", "feImage", "foreignObject", "video", "canvas", "iframe", "object", "embed"}
HREF_ATTRIBUTES = {"href", f"{{{XLINK_NS}}}href"}
URL = re.compile(r"url\(([^)]*)", re.IGNORECASE)
ENCODING = re.compile(r"^<\?xml\s[^>]*?\bencoding\s*=\s*[\"']([^\"']*)[\"']")


class Read(NamedTuple):
    """A text source's strings, and opaque: True when the source may draw text no string names."""

    texts: list
    opaque: bool


class TextSourceError(ValueError):
    """A text source that cannot be read. The message names a rule, never the file's text."""


def kind_of(path):
    """svg or json from a text source's path, or None."""
    lower = str(path).lower()
    return next((s[1:] for s in SUFFIXES if lower.endswith(s)), None)


def local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else None


def external_url(value):
    """True when value holds a CSS url(...) that is not a #fragment of this document."""
    return any(not m.group(1).strip().strip("'\"").strip().startswith("#") for m in URL.finditer(value))


def utf8_prolog(data):
    """Refuse an SVG that is not UTF-8 or holds a document type or entity declaration, before any parser reads it."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise TextSourceError("an SVG text source is not UTF-8") from None
    if "\x00" in text:
        raise TextSourceError("an SVG text source is not UTF-8")
    declared = ENCODING.match(text.removeprefix("\ufeff"))
    if declared and declared.group(1).strip().lower() not in ("utf-8", "utf8"):
        raise TextSourceError("an SVG text source declares an encoding other than UTF-8")
    lower = text.lower()
    if "<!doctype" in lower or "<!entity" in lower:
        raise TextSourceError("an SVG text source holds a document type or entity declaration")


def no_declarations(data):
    """Refuse a document type or entity declaration as the XML parser meets one, whatever the encoding."""

    def deny(*_):
        raise TextSourceError("an SVG text source holds a document type or entity declaration")

    parser = expat.ParserCreate()
    parser.StartDoctypeDeclHandler = deny
    parser.EntityDeclHandler = deny
    parser.UnparsedEntityDeclHandler = deny
    try:
        parser.Parse(data, True)
    except expat.ExpatError:
        raise TextSourceError("the SVG text source is not well-formed XML") from None


def svg_read(data):
    """Read(strings an SVG draws or labels in document order, opaque)."""
    utf8_prolog(data)
    no_declarations(data)
    try:
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
        parser.feed(data)
        root = parser.close()
    except ET.ParseError:
        raise TextSourceError("the SVG text source is not well-formed XML") from None
    if local(root.tag) != "svg" or not root.tag.startswith((f"{{{SVG_NS}}}", "svg")):
        raise TextSourceError("the SVG text source's root element is not svg")
    out, opaque = [], []

    def add(text):
        if isinstance(text, str) and text.strip():
            out.append(text.strip())

    def walk(element):
        comment = element.tag is ET.Comment
        name = None if comment else local(element.tag)
        if name == "style" and external_url(element.text or ""):
            opaque.append(name)
        if not comment and name in SKIPPED:
            return
        if name in OPAQUE_ELEMENTS:
            opaque.append(name)
        add(element.text)
        if not comment:
            for key in sorted(element.attrib):
                value = element.attrib[key]
                if key in LABEL_ATTRIBUTES:
                    add(value)
                elif key in HREF_ATTRIBUTES and name != "a" and not value.strip().startswith("#"):
                    opaque.append(name)
                elif external_url(value):
                    opaque.append(name)
            for child in element:
                walk(child)
                add(child.tail)

    walk(root)
    return Read(out, bool(opaque) or not out)


def svg_texts(data):
    """The strings an SVG draws or labels, in document order."""
    return svg_read(data).texts


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
    """Read(the strings a text source at path shows, opaque). kind is svg or json (default: from the suffix). A JSON
    source lists what its producer drew, so it is never opaque, even when its list is empty."""
    kind = kind or kind_of(path)
    with open(path, "rb") as f:
        data = f.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise TextSourceError(f"the text source is larger than {MAX_BYTES} bytes")
    if kind == "svg":
        return svg_read(data)
    if kind == "json":
        return Read(json_texts(data), False)
    raise TextSourceError("a text source ends in .svg or .json")
