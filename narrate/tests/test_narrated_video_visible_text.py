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

from narrate.video import bundle, cli, deliver, fixture, handoff, private_terms, store, strip, visible_text
from narrate.video.common import StageRefused, to_mono
from narrate.video.job import JobError, load_records


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
        # an entity in UTF-16, with and without its byte-order mark: the raw bytes never spell <!ENTITY
        '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE svg [<!ENTITY a "Quill">]>'
        '<svg xmlns="http://www.w3.org/2000/svg"><text>&a;feather</text></svg>'.encode("utf-16"),
        '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE svg [<!ENTITY a "Quill">]>'
        '<svg xmlns="http://www.w3.org/2000/svg"><text>&a;feather</text></svg>'.encode("utf-16-le"),
        # a document type after more than 4096 bytes of leading comment
        b"<!--" + b"x" * 5000 + b'--><!DOCTYPE svg [<!ENTITY a "Quill">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg"><text>&a;feather</text></svg>',
        # ASCII bytes that declare another encoding
        b'<?xml version="1.0" encoding="ISO-8859-1"?><svg xmlns="http://www.w3.org/2000/svg"><text>a</text></svg>',
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
    assert m["visible_text"] == {"read": ["asset#1", "asset#2"], "unread": [], "opaque": []}
    assert m["states"]["visible_text"] == "passed" and m["states"]["producer_review"] == "pending_operator"
    rows = {s["segment"]: s["asset"]["text"] for s in m["segments"]}
    assert rows == {"intro": {"kind": "svg", "sha256": svg}, "result": {"kind": "json", "sha256": js}}
    # the text source is bound, not copied: the store holds the pictures and scripts only
    assert svg not in " ".join(store_listing(ws["store"])) and js not in " ".join(store_listing(ws["store"]))


def test_a_shown_asset_without_a_text_source_is_listed_unread(ws, tmp_path):
    private_bundle(ws)
    add_text_source(ws["bundle"], "slide-a", "slide-a.svg", plot_svg("0"))
    m = intake(ws, tmp_path / "out", persona="fixture-persona", denylist=ws["denylist"])
    assert m["visible_text"] == {"read": ["asset#1"], "unread": ["asset#2"], "opaque": []}
    assert m["states"]["visible_text"] == "partial"
    marker = json.loads((tmp_path / "out" / "records" / private_terms.MARKER).read_text())
    assert marker["visible_text"] == {"state": "partial", "unread": ["asset#2"], "opaque": []}
    assert load_records(tmp_path / "out" / "records")["visible_text"] == marker["visible_text"]


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


# Opaque SVG text sources: text drawn as an image or as outlines -----------------------------------------------------
PIXEL = "data:image/png;base64,iVBORw0KGgo="


@pytest.mark.parametrize(
    "extra",
    [
        f'<image href="{PIXEL}" width="10" height="10"/>',  # an embedded raster
        '<image xlink:href="slide-raster.png" width="10" height="10"/>',  # a raster in another file
        '<filter id="f"><feImage href="slide-raster.png"/></filter>',
        '<foreignObject width="10" height="10"><p xmlns="http://www.w3.org/1999/xhtml">x</p></foreignObject>',
        '<use href="labels.svg#title"/>',  # another file's drawing
        '<rect width="4" height="4" style="fill: url(other.svg#pattern)"/>',
        "<style>rect { fill: url('other.svg#pattern') }</style>",
        '<style>@import "other.css";</style>',  # an import needs no url()
        "<style>rect { fill: u\\72l(other.svg#pattern) }</style>",  # a CSS escape spells url
        '<rect width="4" height="4" style="fill: u\\72l(other.svg#p)"/>',
        '<script>document.querySelector("g").append("x")</script>',  # script may draw text
        '<rect width="4" height="4" onload="this.after(1)"/>',
    ],
)
def test_an_svg_that_draws_an_image_or_another_file_is_opaque(extra):
    read = visible_text.svg_read(plot_svg("0", extra=extra))
    assert read.opaque is True and "Build time" in read.texts


@pytest.mark.parametrize(
    "extra",
    [
        '<use href="#axis"/>',
        '<rect fill="url(#gradient)"/>',
        "<rect style=\"fill:url( '#g' )\"/>",
        '<a href="https://example.invalid/"><text>link</text></a>',
    ],
)
def test_an_svg_that_refers_only_to_itself_is_not_opaque(extra):
    assert visible_text.svg_read(plot_svg("0", extra=extra)).opaque is False


def test_an_svg_with_an_xml_stylesheet_instruction_is_opaque():
    data = plot_svg("0").replace(b"\n<svg", b'\n<?xml-stylesheet href="other.css" type="text/css"?><svg', 1)
    assert b"xml-stylesheet" in data
    read = visible_text.svg_read(data)
    assert read.opaque is True and "Build time" in read.texts


def test_outlined_text_beside_one_string_is_not_opaque():
    """The guard cannot compare an SVG with its picture: paths beside a title stay the producer's review."""
    data = b'<svg xmlns="http://www.w3.org/2000/svg"><title>Chart</title><path d="M0 0h10v10z"/></svg>'
    assert visible_text.svg_read(data) == visible_text.Read(["Chart"], False)


def test_an_svg_with_no_string_is_opaque_and_a_json_list_is_not():
    outlined = b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h10v10z"/></svg>'  # text outlined to paths
    assert visible_text.svg_read(outlined) == visible_text.Read([], True)
    assert visible_text.svg_texts(outlined) == []


def test_an_opaque_slide_makes_the_intake_partial(ws, tmp_path):
    private_bundle(ws)
    add_text_source(ws["bundle"], "slide-a", "slide-a.svg", plot_svg("0", extra=f'<image href="{PIXEL}"/>'))
    add_text_source(ws["bundle"], "slide-b", "slide-b.svg",
                    b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h1"/></svg>')  # fmt: skip
    m = intake(ws, tmp_path / "out", persona="fixture-persona", denylist=ws["denylist"])
    assert m["visible_text"] == {"read": ["asset#1", "asset#2"], "unread": [], "opaque": ["asset#1", "asset#2"]}
    assert m["states"]["visible_text"] == "partial" and m["private_terms"]["checked"]["visible"] == 1
    marker = json.loads((tmp_path / "out" / "records" / private_terms.MARKER).read_text())
    assert marker["visible_text"]["opaque"] == ["asset#1", "asset#2"]


def test_an_opaque_slide_still_has_its_strings_guarded(ws, tmp_path):
    private_bundle(ws)
    add_text_source(ws["bundle"], "slide-a", "slide-a.svg", plot_svg(NAME, extra=f'<image href="{PIXEL}"/>'))
    error = refused("private_term", intake, ws, tmp_path / "out", denylist=ws["denylist"])
    assert error.report["matches"][0]["source"] == "visible"


# The visible-text state reaches deliver_check ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "summary, gate",
    [
        (None, "not_applicable"),
        ({"state": "passed", "unread": [], "opaque": []}, "passed"),
        ({"state": "partial", "unread": ["asset#2"], "opaque": []}, "pending_operator"),
        ({"state": "partial", "unread": [], "opaque": ["asset#1"]}, "pending_operator"),
        ({"state": "not_recorded", "unread": [], "opaque": []}, "pending_operator"),
    ],
)
def test_the_visible_text_gate(summary, gate):
    assert deliver.visible_gate(summary) == (gate, summary)
    operator = {"listening": "passed", "visible_text": gate}
    job = {"delivery": {"upload": True}, "edition": "Internal"}
    closed = deliver.delivery_gate(job, None, {"profile": "passed"}, operator)
    assert closed["public_upload_allowed"] is (gate != "pending_operator")
    assert ("visible_text" in closed["operator_states_open"]) is (gate == "pending_operator")


@pytest.mark.parametrize(
    "value",
    [
        {"state": "maybe", "unread": [], "opaque": []},
        {"state": "passed", "unread": ["slide-a"], "opaque": []},  # an id, not a position
        {"state": "passed", "unread": []},
        "partial",
        # a guarded intake never writes not_declared: a denylist ran, so the gate must not become not_applicable
        {"state": "not_declared", "unread": ["asset#2"], "opaque": []},
        {"state": "not_declared", "unread": [], "opaque": []},
        # passed holds exactly when no asset is unread or opaque
        {"state": "passed", "unread": ["asset#2"], "opaque": ["asset#3"]},
        {"state": "passed", "unread": [], "opaque": ["asset#1"]},
        {"state": "partial", "unread": [], "opaque": []},
    ],
)
def test_a_marker_with_a_bad_visible_text_refuses(ws, tmp_path, value):
    private_bundle(ws)
    intake(ws, tmp_path / "out", persona="fixture-persona", denylist=ws["denylist"])
    path = tmp_path / "out" / "records" / private_terms.MARKER
    marker = json.loads(path.read_text())
    path.write_text(json.dumps(marker | {"visible_text": value}))
    with pytest.raises(JobError) as caught:
        load_records(tmp_path / "out" / "records")
    assert caught.value.code == "private_terms_stale"
    path.write_text(json.dumps({k: v for k, v in marker.items() if k != "visible_text"}))
    assert load_records(tmp_path / "out" / "records")["visible_text"]["state"] == "not_recorded"


@pytest.mark.parametrize(
    "edit",
    [
        # partial edited to passed, as a well-formed summary
        {"state": "passed", "unread": [], "opaque": []},
        # the unread position moved
        {"state": "partial", "unread": ["asset#3"], "opaque": []},
        {"state": "partial", "unread": ["asset#2"], "opaque": ["asset#1"]},
    ],
)
def test_a_marker_summary_that_disagrees_with_intake_json_refuses(ws, tmp_path, edit):
    private_bundle(ws)
    add_text_source(ws["bundle"], "slide-a", "slide-a.svg", plot_svg("0"))
    out = tmp_path / "out"
    m = intake(ws, out, denylist=ws["denylist"])
    assert m["states"]["visible_text"] == "partial" and m["visible_text"]["unread"] == ["asset#2"]
    path = out / "records" / private_terms.MARKER
    marker = json.loads(path.read_text())
    assert load_records(out / "records")["visible_text"] == marker["visible_text"]
    path.write_text(json.dumps(marker | {"visible_text": edit}))
    with pytest.raises(JobError) as caught:
        load_records(out / "records")
    assert caught.value.code == "private_terms_stale" and "intake.json" in caught.value.detail
    # an intake.json edited the other way disagrees too
    path.write_text(json.dumps(marker))
    manifest = json.loads((out / "intake.json").read_text())
    manifest["states"]["visible_text"] = "passed"
    (out / "intake.json").write_text(json.dumps(manifest))
    with pytest.raises(JobError):
        load_records(out / "records")
    (out / "intake.json").write_text("not json")
    with pytest.raises(JobError):
        load_records(out / "records")


def test_an_unread_slide_on_a_private_lane_holds_the_upload_at_the_operator(ws, tmp_path, ffmpeg, capsys):
    private_bundle(ws)
    add_text_source(ws["bundle"], "slide-a", "slide-a.svg", plot_svg("0"))
    out = tmp_path / "out"
    intake(ws, out, denylist=ws["denylist"])
    root = tmp_path / "narrated"
    common = ["--root", str(root), "--records", str(out / "records"), "--store", str(ws["store"]),
              "--lexical", str(ws["lexical"])]  # fmt: skip
    assert cli.main(["init", "--job", "demo-fixture", "--from", str(out / "narrated-video.json"), *common]) == 0
    assert cli.main(["run", "demo-fixture", *common]) == 0
    s = store.JobStore(root, "demo-fixture")
    current = json.loads((s.dir / "current.json").read_text())["stages"]
    report = json.loads((s.dir / current["deliver_check"]["dir"] / "deliver_check.json").read_text())
    assert report["gates"]["visible_text"] == "pending_operator"
    assert report["visible_text"] == {"state": "partial", "unread": ["asset#2"], "opaque": []}
    assert "visible_text" in report["delivery_gate"]["operator_states_open"]
    assert report["delivery_gate"]["public_upload_allowed"] is False
    # nv plan shows the hold too: admit lists the gate, so a fresh deliver_check stays pending_operator
    capsys.readouterr()
    assert cli.main(["plan", "demo-fixture", "--json", *common]) == 0
    g = json.loads(capsys.readouterr().out)
    held = [p for p in g["pending_operator"] if p["gate"] == "visible_text_unread"]
    assert held and held[0]["stage"] == "deliver_check" and held[0]["detail"].endswith(": asset#2")
    assert {n["id"]: n["state"] for n in g["nodes"]}["deliver_check"] == "pending_operator"


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


# Handoff layers: tags from the base clip, and a byte check of every layer ------------------------------------------
def wav_chunks(path):
    return [c.decode() for c in strip.wav_chunks(path)]


def test_to_mono_drops_the_source_tags(tmp_path, ffmpeg):
    tagged = encode(tmp_path / "tagged.mp4", "-metadata", f"title={NAME}", "-metadata", f"comment={tmp_path}/deck")
    target = to_mono(tagged, tmp_path / "clips.wav")
    assert wav_chunks(target) == ["fmt ", "data"]
    assert NAME.encode() not in target.read_bytes() and str(tmp_path).encode() not in target.read_bytes()
    strip.check_layer(target, [str(tmp_path)])


def test_check_layer_refuses_a_wav_info_chunk_xmp_exif_and_a_local_path(tmp_path, ffmpeg):
    tagged = encode(tmp_path / "tagged.mp4", "-metadata", f"comment={tmp_path}/deck")
    kept = tmp_path / "kept.wav"  # the old to_mono: no -map_metadata -1
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(tagged), "-ac", "1", "-c:a", "pcm_s16le", "-fflags",
                    "+bitexact", str(kept)], check=True)  # fmt: skip
    assert "LIST" in wav_chunks(kept)
    with pytest.raises(StageRefused) as caught:
        strip.check_layer(kept, [])
    assert caught.value.code == "metadata_present" and caught.value.detail == "kept.wav keeps the chunk LIST"
    for name, data, finding in [
        ("avatar-seg-1.mov", b"\x00\x00moov<x:xmpmeta>x</x:xmpmeta>", "an embedded xmp block"),
        ("avatar-seg-1.manifest.json", b'{"exif": "Exif\x00\x00MM"}', "an embedded exif block"),
        ("avatar-seg-1.manifest.json", f'{{"bin": "{tmp_path}/kitpip"}}'.encode(), "a local path"),
    ]:
        (tmp_path / name).write_bytes(data)
        with pytest.raises(StageRefused) as caught:
            strip.check_layer(tmp_path / name, [str(tmp_path)])
        assert caught.value.detail == f"{name} holds {finding}" and str(tmp_path) not in caught.value.detail
    (tmp_path / "plain.json").write_text('{"kind": "kitpip.manifest/v0"}')
    strip.check_layer(tmp_path / "plain.json", [str(tmp_path)])
    (tmp_path / "bad.wav").write_bytes(b"not a wav")
    with pytest.raises(StageRefused):
        strip.check_layer(tmp_path / "bad.wav", [])


def prores(path, *args):
    """A synthetic ProRes 4444 overlay, as an avatar external writes one."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red@0.5:s=32x32:r=10:d=0.3", "-c:v",
         "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-an", *args, str(path)],
        check=True,
    )  # fmt: skip
    return path


def test_check_layer_reads_an_overlay_s_tags_against_the_allowlist(tmp_path, ffmpeg):
    plain = prores(tmp_path / "avatar-seg-1.mov", "-fflags", "+bitexact", "-flags:v", "+bitexact")
    strip.check_layer(plain, [str(tmp_path)])  # vendor_id FFMP and the bit-exact encoder pass
    versioned = prores(tmp_path / "avatar-seg-2.mov")  # a library version names no person or file
    strip.check_layer(versioned, [str(tmp_path)])
    for n, args in enumerate([
        ["-metadata", f"title={NAME}"],
        ["-metadata", f"artist={NAME}"],
        ["-metadata", "comment=client session"],
        ["-metadata:s:v", f"handler_name={NAME}"],
    ]):  # fmt: skip
        tagged = prores(tmp_path / f"avatar-tag-{n}.mov", "-fflags", "+bitexact", *args)
        before = tagged.read_bytes()
        with pytest.raises(StageRefused) as caught:
            strip.check_layer(tagged, [str(tmp_path)])
        assert caught.value.code == "metadata_present" and NAME not in caught.value.detail
        assert tagged.read_bytes() == before  # read only: the bytes a manifest binds stay
    chaptered = with_chapter(tmp_path, encode(tmp_path / "plain.mp4", "-fflags", "+bitexact"))
    with pytest.raises(StageRefused) as caught:
        strip.check_layer(chaptered, [])
    assert caught.value.code == "metadata_present"


def test_handoff_from_a_tagged_base_clip_keeps_no_tag(tmp_path, ffmpeg):
    from test_narrated_video_simple import Workspace

    ws = Workspace(tmp_path)
    video = tmp_path / "tagged-base.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=160x90:r=25:d=12", "-f", "lavfi", "-i",
         "sine=f=220:d=12:sample_rate=48000", "-af", "volume=-40dB", "-metadata", f"title={NAME}",
         "-metadata", f"comment={ws.paths['store']}/deck-a.key", "-c:v", "libx264", "-preset", "ultrafast",
         "-c:a", "aac", "-shortest", str(video)],
        check=True,
    )  # fmt: skip
    job = ws.job("nv-tagged", bed=None, **{"delivery.handoff": True, "delivery.profile": "Contingency"})
    job["base"] = {"video": {"sha256": ws.add_source(video), "keepBaseAudio": True}}
    s, result, _ = ws.run(job)
    assert result["ok"], result
    layers = s.dir / s.entry("handoff")["dir"] / "layers"
    assert wav_chunks(layers / "clips.wav") == ["fmt ", "data"]
    for layer in layers.iterdir():
        assert NAME.encode() not in layer.read_bytes()
        assert str(ws.paths["store"].resolve()).encode() not in layer.read_bytes()
    edit = json.loads((layers.parent / "edit.json").read_text())
    assert "layers/clips.wav" in edit["metadata_checked"] and "layers/base.mp4" not in edit["metadata_checked"]
