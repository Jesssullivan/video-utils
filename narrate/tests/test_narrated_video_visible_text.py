"""The visible text of slide and plot assets in the private-terms guard, and the metadata strip at compose
(docs/spec/NARRATED_VIDEO.md, "Private terms" and "Compose and delivery", TIN-7788).

Every bundle, slide, text source and denylist here is synthetic: fixture.write_bundle's bundle, generated SVG and
JSON text sources, PNGs built in the test and the invented party name "Quillfeather Labs". No real slide, plot,
denylist, name or number is used.
"""

import hashlib
import json
import struct
import subprocess
import zlib

import pytest
from test_narrated_video_private_terms import (
    ENGINE,
    NAME,
    TEMPLATE,
    VOICE,
    leaks,
    private_bundle,
    refused,
    store_listing,
    write_denylist,
)

from narrate.video import bundle, cli, fixture, handoff, private_terms, strip, visible_text
from narrate.video.common import StageRefused


@pytest.fixture(autouse=True)
def no_whisper(monkeypatch, tmp_path):
    monkeypatch.setenv("NARRATE_WHISPER_MODEL", str(tmp_path / "no-whisper-model.bin"))
    monkeypatch.delenv(cli.DENYLIST_ENV, raising=False)


@pytest.fixture
def ws(tmp_path):
    paths = fixture.write(tmp_path / "ws")
    paths["bundle"] = fixture.write_bundle(tmp_path / "bundles")
    paths["denylist"] = tmp_path / "private" / "denylist.json"
    return paths


def intake(ws, out, **kw):
    args = {"template": TEMPLATE, "voice": VOICE, "engine": ENGINE} | kw
    return bundle.intake(ws["bundle"], out, ws["records"], store=ws["store"], **args)


def plot_svg(*labels, extra=""):
    """A synthetic plot drawn as SVG: a title, two axis labels and the given tick or legend labels."""
    ticks = "".join(f'<text x="{10 * n}" y="170">{label}</text>' for n, label in enumerate(labels))
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="320" height="180">'
        '<title>Fixture build time</title><g><text x="4" y="12">Build time</text>'
        f'<text x="4" y="176">runs</text>{ticks}</g>{extra}</svg>'
    ).encode()


def add_text_source(b, asset_id, name, data):
    """Bind a text source to an asset of bundle b by digest; returns its sha256."""
    (b / "assets" / name).write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    m = json.loads((b / "manifest.json").read_text())
    for asset in m["assets"]:
        if asset["id"] == asset_id:
            asset["text"] = {"path": f"assets/{name}", "sha256": digest}
    (b / "manifest.json").write_text(json.dumps(m, indent=1))
    return digest


def text_json(*texts):
    return json.dumps({"kind": "nv_asset_text", "schema_version": 1, "texts": list(texts)}).encode()


# Extraction ------------------------------------------------------------------------------------------------------
def test_svg_text_reads_text_tspans_comments_and_labels_but_not_metadata_or_style():
    data = (
        b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
        b"<metadata><creator>Tooling 9.9.9</creator></metadata><style>.t { font: 10px sans-serif }</style>"
        b'<!-- Quill --><g aria-label="axis"><text>Quill<tspan>feather</tspan> tail</text>'
        b'<a xlink:title="link label"><text>&#x4C;abs</text></a></g><script>var x = 1;</script></svg>'
    )
    assert visible_text.svg_texts(data) == ["Quill", "axis", "Quill", "feather", "tail", "link label", "Labs"]


@pytest.mark.parametrize(
    "data",
    [
        b'<!DOCTYPE svg [<!ENTITY t "Quillfeather">]><svg xmlns="http://www.w3.org/2000/svg"><text>&t;</text></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><text>unclosed</svg>',
        b'<html xmlns="http://www.w3.org/1999/xhtml"><p>not svg</p></html>',
        b'<svg xmlns="http://example.invalid/other"><text>other namespace</text></svg>',
    ],
)
def test_a_malformed_or_entity_svg_refuses(data):
    with pytest.raises(visible_text.TextSourceError) as caught:
        visible_text.svg_texts(data)
    assert "Quillfeather" not in str(caught.value)


@pytest.mark.parametrize(
    "data",
    [
        b"not json",
        json.dumps({"kind": "nv_asset_text", "schema_version": 1}).encode(),
        json.dumps({"kind": "other", "schema_version": 1, "texts": []}).encode(),
        json.dumps({"kind": "nv_asset_text", "schema_version": 2, "texts": []}).encode(),
        json.dumps({"kind": "nv_asset_text", "schema_version": 1, "texts": ["a", 3]}).encode(),
        json.dumps({"kind": "nv_asset_text", "schema_version": 1, "texts": ["x" * 5000]}).encode(),
        b'{"kind": "nv_asset_text", "kind": "nv_asset_text", "schema_version": 1, "texts": []}',
    ],
)
def test_a_malformed_text_json_refuses(data):
    with pytest.raises(visible_text.TextSourceError):
        visible_text.json_texts(data)


# The guard reads the visible text ----------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "name, data",
    [
        ("slide-a.svg", plot_svg("0", "10", NAME)),
        ("slide-a.svg", plot_svg("Quill", extra="<text>feather Labs</text>")),  # split across two labels
        ("slide-a.svg", plot_svg(extra=f"<!-- {NAME} -->")),  # a label drawn as paths, named in a comment
        ("slide-a.svg", plot_svg("Quill&#x66;eather Labs")),  # a character reference
        ("slide-a.json", text_json("Build time", "runs", NAME.upper())),
    ],
)
def test_a_denylisted_term_on_a_slide_refuses_intake(ws, tmp_path, name, data):
    private_bundle(ws)
    add_text_source(ws["bundle"], "slide-a", name, data)
    before = store_listing(ws["store"])
    error = refused("private_term", intake, ws, tmp_path / "out", denylist=ws["denylist"])
    assert error.report["matches"] == [{"segment": "asset#1", "source": "visible", "entry": 0, "class": "name"}]
    assert not leaks(error.detail, error.report)
    assert not (tmp_path / "out").exists() and store_listing(ws["store"]) == before


def test_a_private_number_on_a_plot_axis_refuses(ws, tmp_path):
    private_bundle(ws)
    add_text_source(ws["bundle"], "slide-b", "slide-b.svg", plot_svg("0", "3.1416", "6"))
    error = refused("private_term", intake, ws, tmp_path / "out", denylist=ws["denylist"])
    assert error.report["matches"] == [{"segment": "asset#2", "source": "visible", "entry": 2, "class": "number"}]
    assert not leaks(error.detail, error.report)


def test_a_non_ascii_label_refuses_as_script(ws, tmp_path):
    private_bundle(ws)
    add_text_source(ws["bundle"], "slide-a", "slide-a.json", text_json("Zorbօax"))
    error = refused("private_term", intake, ws, tmp_path / "out", denylist=ws["denylist"])
    assert error.report["matches"][0] == {"segment": "asset#1", "source": "visible", "entry": None, "class": "script"}


def test_a_term_in_svg_metadata_is_not_visible_and_passes(ws, tmp_path):
    private_bundle(ws)
    add_text_source(ws["bundle"], "slide-a", "slide-a.svg", plot_svg(extra=f"<metadata>{NAME}</metadata>"))
    m = intake(ws, tmp_path / "out", persona="fixture-persona", denylist=ws["denylist"])
    assert m["private_terms"]["status"] == "passed" and m["private_terms"]["checked"]["visible"] == 1


def test_clean_text_sources_pass_and_intake_records_them(ws, tmp_path):
    private_bundle(ws)
    svg = add_text_source(ws["bundle"], "slide-a", "slide-a.svg", plot_svg("0", "10", "20"))
    js = add_text_source(ws["bundle"], "slide-b", "slide-b.json", text_json("Cache rate", "forty two percent"))
    m = intake(ws, tmp_path / "out", persona="fixture-persona", denylist=ws["denylist"])
    assert m["private_terms"]["checked"]["visible"] == 2
    assert m["visible_text"] == {"read": ["asset#1", "asset#2"], "unread": []}
    assert m["states"]["visible_text"] == "passed" and m["states"]["producer_review"] == "pending_operator"
    rows = {s["segment"]: s["asset"]["text"] for s in m["segments"]}
    assert rows == {"intro": {"kind": "svg", "sha256": svg}, "result": {"kind": "json", "sha256": js}}
    # the text source is bound, not copied: the store holds the pictures and scripts only
    assert svg not in " ".join(store_listing(ws["store"])) and js not in " ".join(store_listing(ws["store"]))


def test_a_shown_asset_without_a_text_source_is_listed_unread(ws, tmp_path):
    private_bundle(ws)
    add_text_source(ws["bundle"], "slide-a", "slide-a.svg", plot_svg("0"))
    m = intake(ws, tmp_path / "out", persona="fixture-persona", denylist=ws["denylist"])
    assert m["visible_text"] == {"read": ["asset#1"], "unread": ["asset#2"]}
    assert m["states"]["visible_text"] == "partial"


def test_an_undeclared_bundle_records_visible_text_not_declared(ws, tmp_path):
    add_text_source(ws["bundle"], "slide-a", "slide-a.svg", plot_svg(NAME))
    m = intake(ws, tmp_path / "out", persona="fixture-persona")
    assert m["states"]["visible_text"] == "not_declared" and m["visible_text"]["read"] == ["asset#1"]


def test_a_denylist_given_to_an_undeclared_bundle_still_reads_the_slides(ws, tmp_path):
    write_denylist(ws["denylist"])
    add_text_source(ws["bundle"], "slide-a", "slide-a.svg", plot_svg(NAME))
    refused("private_term", intake, ws, tmp_path / "out", denylist=ws["denylist"])


def test_a_text_source_path_is_a_record_text(ws, tmp_path):
    private_bundle(ws)
    add_text_source(ws["bundle"], "slide-a", "quillfeather-labs.svg", plot_svg("0"))
    error = refused("private_term", intake, ws, tmp_path / "out", denylist=ws["denylist"])
    assert error.report["matches"][0]["source"] == "record" and error.report["matches"][0]["segment"] == "asset#1"
    assert not leaks(error.detail, error.report)


@pytest.mark.parametrize(
    "edit, code",
    [
        (lambda t: t.update(sha256="0" * 64), "asset_digest_mismatch"),
        (lambda t: t.update(path="assets/../x.svg"), "bundle_invalid"),
        (lambda t: t.update(path="assets/slide-a.txt"), "asset_kind_mismatch"),
        (lambda t: t.update(path="assets/absent.svg"), "asset_missing"),
        (lambda t: t.update(note="x"), "bundle_invalid"),
        (lambda t: t.pop("sha256"), "bundle_invalid"),
    ],
)
def test_a_bad_text_source_refuses(ws, tmp_path, edit, code):
    add_text_source(ws["bundle"], "slide-a", "slide-a.svg", plot_svg("0"))
    m = json.loads((ws["bundle"] / "manifest.json").read_text())
    edit(m["assets"][0]["text"])
    (ws["bundle"] / "manifest.json").write_text(json.dumps(m))
    refused(code, intake, ws, tmp_path / "out")


def test_a_malformed_text_source_refuses_asset_text_invalid(ws, tmp_path):
    private_bundle(ws)
    entity = b'<!DOCTYPE svg [<!ENTITY t "Quillfeather Labs">]><svg xmlns="http://www.w3.org/2000/svg"></svg>'
    add_text_source(ws["bundle"], "slide-a", "slide-a.svg", entity)
    error = refused("asset_text_invalid", intake, ws, tmp_path / "out", denylist=ws["denylist"])
    assert not leaks(error.detail)


def test_a_text_source_on_a_gif_refuses(ws, tmp_path):
    add_text_source(ws["bundle"], "loop-a", "loop-a.svg", plot_svg("0"))
    refused("bundle_invalid", intake, ws, tmp_path / "out")


def test_the_visible_source_is_a_guard_source():
    assert "visible" in private_terms.SOURCES


# Metadata strip ----------------------------------------------------------------------------------------------------
def chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def png_with(*extra):
    """A 2x1 RGB PNG with extra chunks after IHDR."""
    ihdr = struct.pack(">IIBBBBB", 2, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(b"\x00\xff\x00\x00\x00\x00\xff")
    return strip.PNG_MAGIC + chunk(b"IHDR", ihdr) + b"".join(extra) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")


def test_strip_png_drops_text_exif_icc_and_time_and_keeps_pixels_and_colour():
    clean = png_with(chunk(b"gAMA", struct.pack(">I", 45455)))
    dirty = png_with(
        chunk(b"gAMA", struct.pack(">I", 45455)),
        chunk(b"tEXt", b"Author\x00" + NAME.encode()),
        chunk(b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00<x:xmpmeta>/srv/slides/deck-a</x:xmpmeta>"),
        chunk(b"zTXt", b"Comment\x00\x00" + zlib.compress(b"/private/path")),
        chunk(b"eXIf", b"MM\x00*\x00\x00\x00\x08"),
        chunk(b"iCCP", b"profile\x00\x00" + zlib.compress(b"icc")),
        chunk(b"tIME", b"\x07\xea\x0a\x1e\x00\x00\x00"),
        chunk(b"prVt", b"private"),
    )
    data, dropped = strip.strip_png(dirty)
    assert data == clean and dropped == sorted(["iCCP", "iTXt", "eXIf", "prVt", "tEXt", "tIME", "zTXt"])
    assert strip.strip_png(clean) == (clean, [])
    assert strip.strip_png(b"not a png") is None
    assert strip.strip_png(dirty[:-5]) is None  # a broken IEND


def test_handoff_writes_a_slide_layer_without_metadata(tmp_path, ffmpeg):
    source = tmp_path / "slide.png"
    source.write_bytes(png_with(chunk(b"tEXt", b"Author\x00" + NAME.encode())))
    target = tmp_path / "layers" / "slide-p.png"
    assert handoff.slide_layer(source, target, tmp_path) == ["tEXt"]
    assert NAME.encode() not in target.read_bytes() and target.read_bytes() == png_with()
    bmp = tmp_path / "slide.bmp"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=8x8:d=1", "-frames:v", "1",
                    "-metadata", f"title={NAME}", str(bmp)], check=True)  # fmt: skip
    other = tmp_path / "layers" / "slide-q.png"
    handoff.slide_layer(bmp, other, tmp_path)
    assert other.read_bytes().startswith(strip.PNG_MAGIC) and NAME.encode() not in other.read_bytes()
    assert not list(tmp_path.glob(".*.decoded.png"))


def encode(path, *args):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=64x36:r=10:d=1", "-f", "lavfi", "-i",
         "sine=d=1", *args, "-c:v", "libx264", "-c:a", "aac", "-shortest", str(path)],
        check=True,
    )  # fmt: skip
    return path


def with_chapter(tmp_path, source):
    meta = tmp_path / "chapters.txt"
    meta.write_text(f";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=500\ntitle={NAME}\n")
    out = tmp_path / "chaptered.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source), "-i", str(meta), "-map", "0",
                    "-map_metadata", "0", "-map_chapters", "1", "-c", "copy", str(out)], check=True)  # fmt: skip
    return out


def test_check_media_refuses_tags_chapters_and_paths(tmp_path, ffmpeg):
    tagged = encode(tmp_path / "tagged.mp4", "-metadata", f"title={NAME}", "-metadata", "comment=creator")
    with pytest.raises(StageRefused) as caught:
        strip.check_media(tagged, [])
    assert caught.value.code == "metadata_present" and "title" in caught.value.detail
    assert NAME not in caught.value.detail
    chaptered = with_chapter(tmp_path, encode(tmp_path / "plain.mp4"))
    # the compose flags drop tags and chapters, and the check passes
    clean = tmp_path / "clean.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(chaptered), "-map", "0:v", "-map", "0:a", "-c", "copy",
                    "-map_metadata", "-1", "-map_chapters", "-1", "-fflags", "+bitexact", str(clean)],
                   check=True)  # fmt: skip
    report = strip.check_media(clean, [str(tmp_path)])
    assert report["chapters"] == 0 and set(report["format_tags"]) <= set(strip.FORMAT_TAGS)
    # without -map_chapters -1 a chapter survives -map_metadata -1, and the check refuses it
    kept = tmp_path / "kept.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(chaptered), "-map", "0:v", "-map", "0:a", "-c", "copy",
                    "-map_metadata", "-1", "-fflags", "+bitexact", str(kept)], check=True)  # fmt: skip
    with pytest.raises(StageRefused) as caught:
        strip.check_media(kept, [])
    assert "chapter" in caught.value.detail
    # bytes that say a local path refuse, named only as a local path (the brand bytes stand in for one here)
    with pytest.raises(StageRefused) as caught:
        strip.check_media(clean, ["isom"])
    assert caught.value.detail.endswith("a local path")


def test_check_text_refuses_a_local_path(tmp_path):
    out = tmp_path / "description.txt"
    out.write_text(f"job nv-1\nsource {tmp_path}/store/slide.png\n")
    with pytest.raises(StageRefused) as caught:
        strip.check_text(out, [str(tmp_path)])
    assert caught.value.code == "metadata_present" and str(tmp_path) not in caught.value.detail
    out.write_text("job nv-1\n")
    strip.check_text(out, [str(tmp_path)])
