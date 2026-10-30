"""The private-terms guard of a demo bundle (docs/spec/NARRATED_VIDEO.md, "Private terms", TIN-7735, SPR-220).

Every bundle and denylist here is synthetic: fixture.write_bundle's bundle, an invented party name ("Quillfeather
Labs"), invented geometry wording and the fixture's own claim values. No real denylist, name or number is used.
"""

import hashlib
import json
from pathlib import Path

import pytest

from narrate.video import bundle, cli, fixture, private_terms

TEMPLATE, VOICE, ENGINE = fixture.NARRATE_JOB, "voice-fixture-sine", "fake-sine"
NAME = "Quillfeather Labs"
SALT = "3a9f0c71e6b28d45" * 2  # a fixed synthetic salt; a real denylist holds random bytes
ENTRIES = [
    {"id": "name-a", "class": "name", "literal": NAME},
    {"id": "geom-a", "class": "geometry", "regex": r"chamfer\s+angle"},
    {"id": "num-a", "class": "number", "number": 3.1416, "unit": None},
]


@pytest.fixture(autouse=True)
def no_whisper(monkeypatch, tmp_path):
    monkeypatch.setenv("NARRATE_WHISPER_MODEL", str(tmp_path / "no-whisper-model.bin"))
    monkeypatch.delenv(cli.DENYLIST_ENV, raising=False)


@pytest.fixture
def ws(tmp_path):
    paths = fixture.write(tmp_path / "ws")
    paths["bundle"] = fixture.write_bundle(tmp_path / "bundles")
    paths["denylist"] = tmp_path / "private" / "denylist.json"  # outside the bundle, as a real one is
    return paths


def write_denylist(path, entries=ENTRIES, raw=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (
        raw
        if raw is not None
        else json.dumps({"kind": "nv_denylist", "schema_version": 1, "salt": SALT, "entries": entries})
    )
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def declare(b, digest=None, ip_private=True, never_name=True, **extra):
    m = json.loads((b / "manifest.json").read_text())
    privacy = {"ip_private": ip_private, "never_name": never_name} | extra
    if digest is not None:
        privacy["denylist_sha256"] = digest
    m["privacy"] = privacy
    (b / "manifest.json").write_text(json.dumps(m, indent=1))


def private_bundle(ws, entries=ENTRIES):
    declare(ws["bundle"], write_denylist(ws["denylist"], entries))
    return ws["bundle"]


def set_script(b, old, new):
    text = (b / "script.md").read_text()
    assert old in text
    (b / "script.md").write_text(text.replace(old, new))


def refused(code, fn, *args, **kw):
    with pytest.raises(bundle.BundleError) as caught:
        fn(*args, **kw)
    assert caught.value.code == code, caught.value.detail
    return caught.value


def intake(ws, out, **kw):
    args = {"template": TEMPLATE, "voice": VOICE, "engine": ENGINE} | kw
    return bundle.intake(ws["bundle"], out, ws["records"], store=ws["store"], **args)


def store_listing(store_dir):
    return sorted(p.name for p in Path(store_dir).iterdir()) if Path(store_dir).exists() else []


def leaks(*values):
    """True when any value, dumped as JSON, holds a denylist term."""
    text = " ".join(json.dumps(v, default=str) for v in values).casefold()
    return "quillfeather" in text or "chamfer" in text or "3.1416" in text


# No declaration ----------------------------------------------------------------------------------------------------
def test_an_undeclared_bundle_needs_no_denylist(ws, tmp_path):
    result = bundle.claims_only(ws["bundle"])
    assert result["ok"] is True and result["private_terms"]["status"] == "not_declared"
    m = intake(ws, tmp_path / "out")
    assert m["private_terms"]["status"] == "not_declared" and m["states"]["private_terms"] == "not_declared"


def test_a_denylist_given_to_an_undeclared_bundle_still_runs(ws):
    write_denylist(ws["denylist"])
    set_script(ws["bundle"], "stands in for a demo", f"stands in for {NAME}")
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert error.report["status"] == "refused" and error.report["ip_private"] is False


# The declaration needs its denylist ------------------------------------------------------------------------------
def test_a_declared_bundle_without_a_denylist_refuses(ws, tmp_path):
    private_bundle(ws)
    refused("denylist_missing", bundle.claims_only, ws["bundle"])
    before = store_listing(ws["store"])
    refused("denylist_missing", intake, ws, tmp_path / "out")
    assert not (tmp_path / "out").exists() and store_listing(ws["store"]) == before


def test_a_missing_denylist_file_refuses(ws, tmp_path):
    private_bundle(ws)
    refused("denylist_missing", bundle.claims_only, ws["bundle"], tmp_path / "absent.json")


def test_a_symlinked_denylist_refuses(ws, tmp_path):
    private_bundle(ws)
    link = tmp_path / "link.json"
    link.symlink_to(ws["denylist"])
    refused("denylist_missing", bundle.claims_only, ws["bundle"], link)


def test_a_declaration_without_a_digest_refuses(ws):
    write_denylist(ws["denylist"])
    declare(ws["bundle"], None)
    refused("denylist_missing", bundle.claims_only, ws["bundle"], ws["denylist"])


def test_a_denylist_with_other_bytes_refuses(ws):
    private_bundle(ws)
    write_denylist(ws["denylist"], ENTRIES + [{"id": "name-b", "class": "name", "literal": "Other Party"}])
    refused("denylist_digest_mismatch", bundle.claims_only, ws["bundle"], ws["denylist"])


@pytest.mark.parametrize(
    "privacy",
    [
        {"ip_private": True},
        {"ip_private": "yes", "never_name": True},
        {"ip_private": True, "never_name": True, "denylist_sha256": "ABC"},
        {"ip_private": True, "never_name": True, "denylist_path": "x"},
        [],
    ],
)
def test_a_malformed_privacy_declaration_refuses(ws, privacy):
    m = json.loads((ws["bundle"] / "manifest.json").read_text())
    m["privacy"] = privacy
    (ws["bundle"] / "manifest.json").write_text(json.dumps(m))
    refused("bundle_invalid", bundle.claims_only, ws["bundle"])


# A malformed denylist ------------------------------------------------------------------------------------------
NAME_ROW = {"id": "name-a", "class": "name", "literal": NAME}


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        b"\xff\xfe",
        json.dumps({"kind": "nv_denylist", "schema_version": 1, "salt": SALT, "entries": [NAME_ROW], "extra": 1}),
        json.dumps({"kind": "nv_denylist", "schema_version": 1, "entries": [NAME_ROW]}),  # no salt
        json.dumps({"kind": "nv_denylist", "schema_version": 1, "salt": "0f" * 8, "entries": [NAME_ROW]}),
        json.dumps({"kind": "nv_denylist", "schema_version": 1, "salt": "ZZ" * 16, "entries": [NAME_ROW]}),
        json.dumps({"kind": "other", "schema_version": 1, "salt": SALT, "entries": [NAME_ROW]}),
        json.dumps({"kind": "nv_denylist", "schema_version": 2, "salt": SALT, "entries": [NAME_ROW]}),
        json.dumps({"kind": "nv_denylist", "schema_version": 1, "salt": SALT, "entries": []}),
        '{"kind": "nv_denylist", "kind": "nv_denylist", "schema_version": 1, "entries": []}',
        json.dumps(
            {"kind": "nv_denylist", "schema_version": 1, "salt": SALT, "entries": [{"id": "x", "class": "name"}]}
        ),
    ],
)
def test_a_malformed_denylist_file_refuses(ws, raw):
    declare(ws["bundle"], write_denylist(ws["denylist"], raw=raw))
    refused("denylist_invalid", bundle.claims_only, ws["bundle"], ws["denylist"])


@pytest.mark.parametrize(
    "rows",
    [
        [NAME_ROW, NAME_ROW],  # a repeated id
        [NAME_ROW, {"id": "Bad Id", "class": "name", "literal": "Other"}],
        [NAME_ROW, {"id": "g", "class": "shape", "literal": "chamfer angle"}],
        [NAME_ROW, {"id": "g", "class": "geometry", "literal": "x"}],  # under two letters or digits
        [NAME_ROW, {"id": "g", "class": "geometry", "literal": " - "}],
        [NAME_ROW, {"id": "g", "class": "geometry", "literal": "a" * 300}],
        [NAME_ROW, {"id": "g", "class": "geometry", "regex": "("}],
        [NAME_ROW, {"id": "g", "class": "geometry", "regex": "x*"}],  # matches empty text
        [NAME_ROW, {"id": "g", "class": "geometry", "regex": r"\s?"}],
        [NAME_ROW, {"id": "g", "class": "geometry", "regex": ""}],
        [NAME_ROW, {"id": "g", "class": "geometry", "literal": "chamfer", "regex": "chamfer"}],
        [NAME_ROW, {"id": "g", "class": "geometry", "literal": "chamfer", "note": "x"}],
        [NAME_ROW, {"id": "n", "class": "number", "number": 5}],  # no unit
        [NAME_ROW, {"id": "n", "class": "number", "number": "5", "unit": None}],
        [NAME_ROW, {"id": "n", "class": "number", "number": 5, "unit": "furlong"}],
        [NAME_ROW, {"id": "n", "class": "name", "number": 5, "unit": None}],
        [{"id": "g", "class": "geometry", "literal": "chamfer angle"}],  # never_name without a name entry
        [NAME_ROW],  # ip_private without a number or geometry entry
        [NAME_ROW, {"id": "chamfer-a", "class": "geometry", "literal": "chamfer"}],  # an id that says a term
    ],
)
def test_a_malformed_denylist_entry_refuses(ws, rows):
    declare(ws["bundle"], write_denylist(ws["denylist"], rows))
    error = refused("denylist_invalid", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert not leaks(error.detail)


def test_each_declaration_needs_only_its_own_class(ws):
    declare(ws["bundle"], write_denylist(ws["denylist"], [NAME_ROW]), ip_private=False, never_name=True)
    assert bundle.claims_only(ws["bundle"], ws["denylist"])["private_terms"]["status"] == "passed"
    rows = [{"id": "g", "class": "geometry", "regex": r"chamfer\s+angle"}]
    declare(ws["bundle"], write_denylist(ws["denylist"], rows), ip_private=True, never_name=False)
    assert bundle.claims_only(ws["bundle"], ws["denylist"])["private_terms"]["status"] == "passed"


# Passing and refusing ----------------------------------------------------------------------------------------------
def test_a_clean_bundle_passes_and_intake_records_the_guard(ws, tmp_path):
    digest = write_denylist(ws["denylist"])
    declare(ws["bundle"], digest)
    result = bundle.claims_only(ws["bundle"], ws["denylist"])
    assert result["ok"] is True
    private = result["private_terms"]
    assert private["status"] == "passed" and private["denylist_sha256"] == digest and private["entries"] == 3
    assert private["checked"] == {
        "record": 29,
        "voiced": 2,
        "spoken": 0,
        "claim": 3,
        "label": 0,
        "joined": 1,
        "visible": 0,
    }
    m = intake(ws, tmp_path / "out", persona="fixture-persona", denylist=ws["denylist"])
    assert m["private_terms"]["status"] == "passed" and m["states"]["private_terms"] == "passed"
    assert m["private_terms"]["checked"] == {
        "record": 31,
        "voiced": 2,
        "spoken": 4,
        "claim": 3,
        "label": 1,
        "joined": 4,
        "visible": 0,  # the fixture's slides name no text source (test_narrated_video_visible_text.py)
    }
    assert m["private_terms"]["denylist_sha256"] == digest
    assert not leaks(m) and str(ws["denylist"]) not in json.dumps(m)


@pytest.mark.parametrize(
    "said",
    [
        NAME,
        "quillfeather labs",
        "QUILLFEATHER LABS",
        "Quillfeather-Labs",
        "Quillfeather Labs's",
        "Quill​feather Labs",
        "Quill­feather  Labs",
        "Ｑｕｉｌｌｆｅａｔｈｅｒ Labs",  # fullwidth letters fold under NFKC
    ],
)
def test_a_name_in_voiced_text_refuses_in_any_spelling(ws, said):
    private_bundle(ws)
    set_script(ws["bundle"], "stands in for a demo", f"stands in for {said}")
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert error.report["matches"] == [{"segment": "intro", "source": "voiced", "entry": 0, "class": "name"}]
    assert not leaks(error.detail, error.report)


def test_a_name_inside_a_longer_word_matches_because_the_guard_fails_closed(ws):
    private_bundle(ws)
    set_script(ws["bundle"], "stands in for a demo", "stands in for Quillfeather Labsworth")
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert error.report["matches"][0]["entry"] == 0


def test_a_geometry_pattern_refuses(ws):
    private_bundle(ws)
    set_script(ws["bundle"], "stands in for a demo", "shows its Chamfer   angle")
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert error.report["matches"][0]["entry"] == 1


@pytest.mark.parametrize("said", ["3.1416", "three point one four one six", "three point one four one six metres"])
def test_a_private_number_refuses_in_digits_or_words(ws, said):
    private_bundle(ws)
    set_script(ws["bundle"], "stands in for a demo", f"stands in for {said}")
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert error.report["matches"][0] == {"segment": "intro", "source": "voiced", "entry": 2, "class": "number"}


@pytest.mark.parametrize("unit", ["ms", "percent", None])
def test_a_number_entry_matches_its_value_in_any_unit(ws, unit):
    rows = [NAME_ROW, {"id": "num-b", "class": "number", "number": 42, "unit": unit}]
    private_bundle(ws, rows)  # the fixture says 42 percent; a unit-bound entry no longer narrows the match
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    sources = {(m["segment"], m["source"]) for m in error.report["matches"]}
    assert sources == {("result", "voiced"), ("cache-rate", "claim")}


def test_a_claim_spoken_text_is_checked(ws):
    rows = [NAME_ROW, {"id": "num-b", "class": "number", "number": 400, "unit": ""}]
    private_bundle(ws, rows)
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert ("files", "claim") in {(m["segment"], m["source"]) for m in error.report["matches"]}


def test_a_persona_label_is_checked(ws, tmp_path):
    private_bundle(ws)
    error = refused("private_term", intake, ws, tmp_path / "out", persona=NAME, denylist=ws["denylist"])
    assert error.report["matches"] == [{"segment": "labels", "source": "label", "entry": 0, "class": "name"}]
    assert not (tmp_path / "out").exists()


def test_a_pronunciation_table_that_says_a_term_refuses_at_intake(ws, tmp_path):
    private_bundle(ws)
    path = ws["records"] / "pronunciation.json"
    table = json.loads(path.read_text())
    rows = table if isinstance(table, list) else [table]
    rows[0]["entries"].append(
        {"caseSensitive": True, "note": None, "spoken": "quillfeather labs", "wholeWord": True, "written": "synthetic"}
    )
    path.write_text(json.dumps(table, indent=1))
    assert bundle.claims_only(ws["bundle"], ws["denylist"])["ok"] is True  # claims reads no records
    before = store_listing(ws["store"])
    error = refused("private_term", intake, ws, tmp_path / "out", denylist=ws["denylist"])
    assert error.report["matches"][0]["source"] == "spoken" and error.report["matches"][0]["segment"] == "intro"
    assert not (tmp_path / "out").exists() and store_listing(ws["store"]) == before


# Record texts ------------------------------------------------------------------------------------------------
def edit_json(path, change):
    value = json.loads(path.read_text())
    change(value)
    path.write_text(json.dumps(value, indent=1))


def test_a_private_beat_id_refuses_by_position(ws):
    private_bundle(ws)
    set_script(ws["bundle"], "## result", "## quillfeather-labs-result")
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert error.report["matches"] == [{"segment": "beat#2", "source": "record", "entry": 0, "class": "name"}]
    assert not leaks(error.detail, error.report)


def test_a_private_claim_receipt_refuses(ws):
    private_bundle(ws)
    edit_json(ws["bundle"] / "claims.json", lambda rows: rows[0].update(receipt=f"measured at {NAME}"))
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert error.report["matches"][0] == {"segment": "claim#1", "source": "record", "entry": 0, "class": "name"}
    assert not leaks(error.detail, error.report)


@pytest.mark.parametrize("key", ["receipt", "path", "id"])
def test_a_private_asset_text_refuses_before_any_asset_check(ws, key):
    private_bundle(ws)
    value = {"receipt": "the chamfer angle run", "path": "assets/chamfer-angle.png", "id": "chamfer-angle"}[key]
    edit_json(ws["bundle"] / "manifest.json", lambda m: m["assets"][0].update({key: value}))
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    match = {"segment": "asset#1", "source": "record", "entry": 1, "class": "geometry"}
    assert error.report["matches"][0] == match
    assert not leaks(error.detail, error.report)


def test_a_private_job_id_refuses_at_intake(ws, tmp_path):
    private_bundle(ws)
    error = refused("private_term", intake, ws, tmp_path / "out", job_id="quillfeather-labs", denylist=ws["denylist"])
    assert error.report["matches"] == [{"segment": "job", "source": "record", "entry": 0, "class": "name"}]
    assert not (tmp_path / "out").exists()


def test_a_private_bundle_directory_name_refuses_at_intake(ws, tmp_path):
    private_bundle(ws)
    renamed = ws["bundle"].with_name("quillfeather-labs")
    ws["bundle"].rename(renamed)
    ws["bundle"] = renamed  # the fixture manifest has no slug, so only the directory's name says the term
    error = refused("private_term", intake, ws, tmp_path / "out", job_id="demo", denylist=ws["denylist"])
    assert error.report["matches"] == [{"segment": "slug", "source": "record", "entry": 0, "class": "name"}]


def test_intake_refuses_a_term_and_writes_nothing(ws, tmp_path):
    private_bundle(ws)
    set_script(ws["bundle"], "stands in for a demo", f"stands in for {NAME}")
    before = store_listing(ws["store"])
    refused("private_term", intake, ws, tmp_path / "out", denylist=ws["denylist"])
    assert not (tmp_path / "out").exists() and store_listing(ws["store"]) == before


# The CLI -------------------------------------------------------------------------------------------------------
def test_cli_claims_reads_the_denylist_flag_and_env(ws, capsys, monkeypatch):
    private_bundle(ws)
    assert cli.main(["claims", str(ws["bundle"])]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "denylist_missing"
    assert cli.main(["claims", str(ws["bundle"]), "--denylist", str(ws["denylist"])]) == 0
    assert json.loads(capsys.readouterr().out)["private_terms"]["status"] == "passed"
    monkeypatch.setenv(cli.DENYLIST_ENV, str(ws["denylist"]))
    assert cli.main(["claims", str(ws["bundle"])]) == 0
    capsys.readouterr()


def test_cli_claims_prints_no_term_when_it_refuses(ws, capsys):
    private_bundle(ws)
    set_script(ws["bundle"], "stands in for a demo", f"stands in for {NAME}")
    assert cli.main(["claims", str(ws["bundle"]), "--denylist", str(ws["denylist"])]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.err)["refused"] == "private_term"
    assert json.loads(captured.out)["private_terms"]["matches"][0]["entry"] == 0
    assert not leaks(captured.out, captured.err)


def test_cli_intake_takes_the_denylist(ws, tmp_path, capsys):
    private_bundle(ws)
    args = ["intake", str(ws["bundle"]), "--out", str(tmp_path / "out"), "--records", str(ws["records"]),
            "--store", str(ws["store"]), "--narrate-template", TEMPLATE, "--voice", VOICE, "--engine", ENGINE,
            "--no-avatar"]  # fmt: skip
    assert cli.main(args) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "denylist_missing"
    assert cli.main(args + ["--denylist", str(ws["denylist"])]) == 0
    assert json.loads((tmp_path / "out" / "intake.json").read_text())["states"]["private_terms"] == "passed"


def test_the_guard_reads_declarations_directly():
    assert not private_terms.required(private_terms.declaration(None))
    assert private_terms.required(private_terms.declaration({"ip_private": False, "never_name": True}))


# Review round 2 (TIN-7735 F3, F7 to F12) ---------------------------------------------------------------------------
CONFORMANCE = Path(__file__).parent / "fixtures" / "narrated-video" / "nv-denylist-conformance.json"


def test_the_shared_conformance_fixture_agrees_with_this_guard():
    """cade src/bs21-guard.ts reads the same file (tests/fixtures/nv-denylist-conformance.json) and must agree."""
    case = json.loads(CONFORMANCE.read_text())
    entries = private_terms.parse(case["denylist"].encode())
    missed = [t for t in case["refuse"] if not private_terms.scan(entries, [("x", "voiced", t)])]
    over = [t for t in case["pass"] if private_terms.scan(entries, [("x", "voiced", t)])]
    assert missed == [] and over == []
    for raw in case["invalid"]:
        with pytest.raises(private_terms.PrivateError) as caught:
            private_terms.parse(raw.encode())
        assert caught.value.code == "denylist_invalid"
    for raw in case["valid"]:
        private_terms.parse(raw.encode())


@pytest.mark.parametrize(
    "said",
    [
        "QuillfeatherLabs", "quillfeatherlabs.com", "#QuillfeatherLabs", "Quillfeather­Labs",
        "Quillfeather⁠Labs", "Quillfeather‍Labs", "Quіllfeather Labs", "Qui̱llfeather Labs",
        "Quillféather Labs", "Quillféather Labs", "Quillfeather Labses", "Quill-feather Labs",
    ],
)  # fmt: skip
def test_a_respelled_name_refuses(ws, said):
    private_bundle(ws)
    set_script(ws["bundle"], "stands in for a demo", f"stands in for {said}")
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert {m["class"] for m in error.report["matches"]} <= {"name", "script"}
    assert not leaks(error.detail, error.report)


@pytest.mark.parametrize("said", ["Chamfer​Angle", "chamferangle", "chamferAngle"])
def test_a_squeezed_geometry_phrase_refuses(ws, said):
    private_bundle(ws)
    set_script(ws["bundle"], "stands in for a demo", f"shows the {said}")
    assert refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"]).report["matches"]


def test_a_word_mixing_latin_and_cyrillic_refuses_as_script(ws):
    private_bundle(ws)
    set_script(ws["bundle"], "stands in for a demo", "stands in for a dеmo")
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert error.report["matches"][0] == {"segment": "intro", "source": "voiced", "entry": None, "class": "script"}


@pytest.mark.parametrize(
    "receipt",
    ["３.１４１６", "3,1416", "run 3.1416-b", "three point one four one six", "٣.١٤١٦"],
)  # fmt: skip
def test_a_private_number_in_a_record_text_refuses_in_any_form(ws, receipt):
    private_bundle(ws)
    edit_json(ws["bundle"] / "claims.json", lambda rows: rows[0].update(receipt=f"measured {receipt}"))
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert error.report["matches"][0]["segment"] == "claim#1"


@pytest.mark.parametrize("said", ["12,5", "12½", "twelve and a half", ".5 of 12.5", "12.5 deg", "12.5-degree"])
def test_number_forms_near_a_private_value_refuse(said):
    entries = private_terms.parse(json.dumps({"kind": "nv_denylist", "schema_version": 1, "salt": SALT, "entries": [
        {"id": "num-x", "class": "number", "number": 12.5, "unit": "deg"}]}).encode())  # fmt: skip
    assert private_terms.scan(entries, [("x", "record", f"value {said}")])


def test_a_number_entry_id_that_says_its_number_refuses_and_details_name_positions(ws):
    rows = [NAME_ROW, {"id": "angle-12.5", "class": "geometry", "number": 12.5, "unit": None}]
    declare(ws["bundle"], write_denylist(ws["denylist"], rows))
    error = refused("denylist_invalid", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert "12.5" not in error.detail
    private_bundle(ws)
    set_script(ws["bundle"], "stands in for a demo", f"stands in for {NAME}")
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert "name-a" not in error.detail and "entry #0" in error.detail


@pytest.mark.parametrize("salt", ["0" * 32, "0f" * 16, "01234560123456" + "0" * 18])
def test_a_low_entropy_salt_refuses(ws, salt):
    raw = json.dumps({"kind": "nv_denylist", "schema_version": 1, "salt": salt, "entries": ENTRIES})
    declare(ws["bundle"], write_denylist(ws["denylist"], raw=raw))
    refused("denylist_invalid", bundle.claims_only, ws["bundle"], ws["denylist"])


@pytest.mark.parametrize("pattern", [r"chamfer(?P<x>a)", r"\w+angle", r"(?=a)b", r"a\1", r"[[:alpha:]]", r"^chamfer$"])
def test_a_regex_outside_the_shared_subset_refuses(ws, pattern):
    rows = [NAME_ROW, {"id": "g", "class": "geometry", "regex": pattern}]
    declare(ws["bundle"], write_denylist(ws["denylist"], rows))
    refused("denylist_invalid", bundle.claims_only, ws["bundle"], ws["denylist"])


# F7: the operator's pin and the denylist's place -------------------------------------------------------------------
def test_a_pinned_lane_refuses_an_undeclared_bundle(ws, monkeypatch):
    digest = write_denylist(ws["denylist"])
    refused("privacy_undeclared", bundle.claims_only, ws["bundle"], ws["denylist"], digest)
    monkeypatch.setenv(private_terms.PIN_ENV, digest)
    refused("privacy_undeclared", bundle.claims_only, ws["bundle"], ws["denylist"])
    refused("denylist_missing", bundle.claims_only, ws["bundle"])  # a pin needs the file


def test_a_pin_outranks_the_manifest_digest(ws):
    digest = write_denylist(ws["denylist"])
    declare(ws["bundle"], digest)
    other = ws["denylist"].with_name("other.json")
    swapped = write_denylist(other, [NAME_ROW, {"id": "g", "class": "geometry", "regex": "nothing\\s+here"}])
    declare(ws["bundle"], swapped)  # a bundle edit that binds another list
    refused("denylist_digest_mismatch", bundle.claims_only, ws["bundle"], other, digest)
    declare(ws["bundle"], None)
    refused("denylist_digest_mismatch", bundle.claims_only, ws["bundle"], other, digest)
    declare(ws["bundle"], digest)
    assert bundle.claims_only(ws["bundle"], ws["denylist"], digest)["private_terms"]["pinned"] is True


def test_a_bad_pin_refuses(ws):
    private_bundle(ws)
    refused("denylist_pin_invalid", bundle.claims_only, ws["bundle"], ws["denylist"], "ABC")


def test_a_denylist_inside_the_bundle_or_a_work_tree_refuses(ws, tmp_path):
    inside = ws["bundle"] / "denylist.json"
    declare(ws["bundle"], write_denylist(inside))
    refused("denylist_misplaced", bundle.claims_only, ws["bundle"], inside)
    tree = tmp_path / "repo"
    (tree / ".git").mkdir(parents=True)
    in_tree = tree / "lists" / "denylist.json"
    declare(ws["bundle"], write_denylist(in_tree))
    refused("denylist_misplaced", bundle.claims_only, ws["bundle"], in_tree)


def test_cli_reads_the_pin_flag(ws, capsys):
    digest = write_denylist(ws["denylist"])
    assert cli.main(["claims", str(ws["bundle"]), "--denylist", str(ws["denylist"]), "--denylist-sha256", digest]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "privacy_undeclared"


# F8: a guarded intake binds its narrate jobs and their pronunciation tables --------------------------------------
def add_entry(row):
    return lambda table: (table if isinstance(table, list) else [table])[0]["entries"].append(row)


def test_a_guarded_intake_binds_the_pronunciation_table(ws, tmp_path):
    from narrate.video.job import JobError, load_records

    private_bundle(ws)
    out = tmp_path / "out"
    intake(ws, out, denylist=ws["denylist"])
    marker = json.loads((out / "records" / private_terms.MARKER).read_text())
    assert marker["status"] == "passed" and len(marker["jobs"]) == 2 and not leaks(marker)
    load_records(out / "records")
    row = {"caseSensitive": True, "note": None, "spoken": "quillfeather labs", "wholeWord": True, "written": "demo"}
    edit_json(out / "records" / "pronunciation.json", add_entry(row))
    with pytest.raises(JobError) as caught:
        load_records(out / "records")
    assert caught.value.code == "private_terms_stale" and not leaks(caught.value.detail)


def test_an_undeclared_intake_writes_no_marker(ws, tmp_path):
    intake(ws, tmp_path / "out")
    assert not (tmp_path / "out" / "records" / private_terms.MARKER).exists()


# F9: refusals before and around the guard withhold private text ----------------------------------------------------
def test_a_claim_refusal_that_reads_a_private_number_is_withheld(ws):
    private_bundle(ws)
    edit_json(ws["bundle"] / "claims.json", lambda rows: rows[0]["value"].update(spoken="3.1416 and 7"))
    error = refused("claim_invalid", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert "withheld" in error.detail and not leaks(error.detail)


def test_an_asset_refusal_that_names_a_private_path_is_withheld(ws, tmp_path):
    private_bundle(ws)
    m = json.loads((ws["bundle"] / "manifest.json").read_text())
    old = ws["bundle"] / m["assets"][0]["path"]
    new = old.with_name("quillfeather-labs-" + old.name)
    old.rename(new)
    m["assets"][0]["path"] = str(new.relative_to(ws["bundle"]))
    m["assets"][0]["receipt"] = "synthetic receipt"
    (ws["bundle"] / "manifest.json").write_text(json.dumps(m, indent=1))
    error = refused("private_term", intake, ws, tmp_path / "out", denylist=ws["denylist"])
    assert not leaks(error.detail, error.report)
    m["assets"][0]["sha256"] = "0" * 64
    (ws["bundle"] / "manifest.json").write_text(json.dumps(m, indent=1))
    error = refused("private_term", intake, ws, tmp_path / "out", denylist=ws["denylist"])
    assert not leaks(error.detail)


def test_a_refusal_while_the_given_denylist_is_unreadable_is_withheld(ws):
    ws["denylist"].parent.mkdir(parents=True, exist_ok=True)
    ws["denylist"].write_text("not json")
    edit_json(ws["bundle"] / "manifest.json", lambda m: m.update({NAME: 1}))  # refused before the guard is built
    error = refused("bundle_invalid", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert "withheld" in error.detail and not leaks(error.detail)


def test_a_redacted_detail_keeps_unrelated_refusals_readable(ws):
    private_bundle(ws)
    set_script(ws["bundle"], "## result", "## Bad Id")
    error = refused("beat_invalid", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert "withheld" not in error.detail and "line" in error.detail and "Bad Id" not in error.detail


# Review round 3 (TIN-7735): look-alike letters, number forms, the records marker and record numbers -----------------
@pytest.mark.parametrize(
    "said",
    [
        "QuiIlfeather Labs", "Qu1llfeather Labs", "Quil|feather Labs", "Qui!lfeather Labs", "Quillfeաther Labs",
        "ꓖuillfeather Labs", "ᴏᴜɪʟʟꜰᴇᴀᴛʜᴇʀ Labs",
        "QuilΙfeather Labs", "Quillfeather Lօbs",
    ],
)  # fmt: skip
def test_a_look_alike_name_refuses(ws, said):
    private_bundle(ws)
    set_script(ws["bundle"], "stands in for a demo", f"stands in for {said}")
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert {m["class"] for m in error.report["matches"]} <= {"name", "script"}
    assert not leaks(error.detail, error.report)


def test_a_letter_outside_ascii_refuses_as_script_and_an_accent_does_not(ws):
    private_bundle(ws)
    set_script(ws["bundle"], "stands in for a demo", "stands in for a dօmo")
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert error.report["matches"][0] == {"segment": "intro", "source": "voiced", "entry": None, "class": "script"}
    set_script(ws["bundle"], "stands in for a dօmo", "stands in for a démo of Straße")
    assert bundle.claims_only(ws["bundle"], ws["denylist"])["private_terms"]["status"] == "passed"


@pytest.mark.parametrize("said", ["QuiIlfeather Labs", "Quillfeաther Labs"])
def test_a_look_alike_persona_and_asset_receipt_refuse_at_intake(ws, tmp_path, said):
    private_bundle(ws)
    error = refused("private_term", intake, ws, tmp_path / "out", persona=said, denylist=ws["denylist"])
    assert error.report["matches"][0]["segment"] == "labels"
    edit_json(ws["bundle"] / "manifest.json", lambda m: m["assets"][0].update(receipt=f"run at {said}"))
    error = refused("private_term", intake, ws, tmp_path / "out", denylist=ws["denylist"])
    assert error.report["matches"][0]["segment"] == "asset#1"
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "receipt",
    ["12·5", "twelve dot five", "twelve comma five", "12٫5", "25/2", "12 1/2", "12 .5", "12 . 5"],
)  # fmt: skip
def test_a_private_number_in_a_receipt_refuses_in_more_forms(ws, receipt):
    rows = [NAME_ROW, {"id": "e1", "class": "number", "number": 12.5, "unit": None}]
    private_bundle(ws, rows)
    edit_json(ws["bundle"] / "claims.json", lambda rows: rows[0].update(receipt=f"measured {receipt}"))
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert error.report["matches"][0] == {"segment": "claim#1", "source": "record", "entry": 1, "class": "number"}


def test_a_grouped_integer_with_one_point_refuses():
    entries = private_terms.parse(json.dumps({"kind": "nv_denylist", "schema_version": 1, "salt": SALT, "entries": [
        {"id": "e0", "class": "number", "number": 3375, "unit": None}]}).encode())  # fmt: skip
    assert private_terms.scan(entries, [("x", "record", "a run of 3.375 parts")])
    assert not private_terms.scan(entries, [("x", "record", "a run of 3.38 parts and 12 1/3 cups")])


def test_an_entry_id_never_reaches_a_report(ws):
    rows = [NAME_ROW, {"id": "angle-12-5", "class": "geometry", "number": 12.5, "unit": None}]
    private_bundle(ws, rows)
    edit_json(ws["bundle"] / "claims.json", lambda rows: rows[0].update(receipt="measured 12.5"))
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert "angle" not in json.dumps(error.report) + error.detail
    assert error.report["matches"][0]["entry"] == 1


@pytest.mark.parametrize(("number", "segment"), [(8.5, "beat#2"), (16.5, "beat#2"), (320, "asset#1")])
def test_a_private_number_a_record_holds_refuses(ws, number, segment):
    private_bundle(ws, [NAME_ROW, {"id": "e1", "class": "number", "number": number, "unit": None}])
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert (segment, "record") in {(m["segment"], m["source"]) for m in error.report["matches"]}


def guarded_out(ws, tmp_path):
    private_bundle(ws)
    out = tmp_path / "out"
    intake(ws, out, persona="fixture-persona", denylist=ws["denylist"])
    return out


def init_args(ws, tmp_path, out, job_file):
    common = ["--root", str(tmp_path / "narrated"), "--records", str(out / "records"), "--store", str(ws["store"])]
    return ["init", "--job", "demo-fixture", "--from", str(job_file), *common]


def test_a_deleted_marker_refuses_beside_a_guarded_intake(ws, tmp_path, monkeypatch):
    from narrate.video.job import JobError, load_records

    out = guarded_out(ws, tmp_path)
    (out / "records" / private_terms.MARKER).unlink()
    row = {"caseSensitive": True, "note": None, "spoken": "quillfeather labs", "wholeWord": True, "written": "demo"}
    edit_json(out / "records" / "pronunciation.json", add_entry(row))
    with pytest.raises(JobError) as caught:
        load_records(out / "records")
    assert caught.value.code == "private_terms_stale"
    (out / "intake.json").unlink()
    load_records(out / "records")  # no intake.json and no private lane: nothing says the records were guarded
    monkeypatch.setenv(private_terms.DENYLIST_ENV, str(ws["denylist"]))
    with pytest.raises(JobError) as caught:
        load_records(out / "records")
    assert caught.value.code == "private_terms_stale"


def test_init_from_takes_only_the_record_a_guarded_intake_wrote(ws, tmp_path, capsys):
    out = guarded_out(ws, tmp_path)
    assert cli.main(init_args(ws, tmp_path, out, out / "narrated-video.json")) == 0
    common = ["--root", str(tmp_path / "narrated"), "--records", str(out / "records"), "--store", str(ws["store"])]
    assert cli.main(["plan", "demo-fixture", "--json", *common]) == 0  # the stored record still matches the marker
    capsys.readouterr()
    job = json.loads((out / "narrated-video.json").read_text())
    edits = {
        "persona": lambda j: j["labels"].update(persona=NAME),
        "segment": lambda j: j["segments"][0].update(narrateJob=TEMPLATE),
    }
    for name, change in edits.items():
        edited = json.loads(json.dumps(job))
        change(edited)
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(edited))
        args = init_args(ws, tmp_path, out, path) + ["--replace"]
        assert cli.main(args) == 1, name
        captured = capsys.readouterr()
        assert json.loads(captured.err)["refused"] == "private_terms_stale"
        assert not leaks(captured.out, captured.err)


def test_init_from_flags_refuses_on_guarded_records(ws, tmp_path, capsys):
    out = guarded_out(ws, tmp_path)
    script = tmp_path / "script.md"
    script.write_text("synthetic\n")
    narrate_job = sorted(json.loads((out / "records" / private_terms.MARKER).read_text())["jobs"])[0]
    args = ["init", "--job", "flags-job", "--narrate-job", narrate_job, "--script", str(script), "--no-avatar",
            "--root", str(tmp_path / "narrated"), "--records", str(out / "records")]  # fmt: skip
    assert cli.main(args) == 1
    assert json.loads(capsys.readouterr().err)["refused"] in {"private_terms_stale", "input_mismatch", "job_invalid"}


# Final review (TIN-7735 F-A to F-C): no detail echoes a bundle value, a pinned lane withholds, more number forms -----
HIDDEN = [f"Quill{ch}feather Labs" for ch in ("­", "​", "‍", "⁠")]


def says_nothing(detail):
    """True when a refusal detail holds no part of the synthetic name, no escape and no format character."""
    return (
        "quill" not in detail.casefold()
        and not private_terms.ESCAPE.search(detail)
        and not any(ch in detail for ch in "­​‍⁠")
    )


def unknown_manifest_key(b, term):
    edit_json(b / "manifest.json", lambda m: m.update({term: 1}))


def unknown_claims_key(b, term):
    edit_json(b / "claims.json", lambda rows: rows[0].update({term: 1}))


def asset_kind(b, term):
    edit_json(b / "manifest.json", lambda m: m["assets"][0].update(kind=term))


def claim_unit(b, term):
    edit_json(b / "claims.json", lambda rows: rows[0]["value"].update(unit=term))


def beat_heading(b, term):
    set_script(b, "## result", f"## {term}")


def beat_target(b, term):
    set_script(b, "- target_s: 8.5", f"- target_s: {term}")


def beat_asset(b, term):
    set_script(b, "- asset_id: slide-b", f"- asset_id: {term}")


@pytest.mark.parametrize(
    "edit", [unknown_manifest_key, unknown_claims_key, asset_kind, claim_unit, beat_heading, beat_target, beat_asset]
)
@pytest.mark.parametrize("term", HIDDEN)
def test_no_refusal_detail_echoes_a_bundle_value(ws, capsys, edit, term):
    private_bundle(ws)
    edit(ws["bundle"], term)
    with pytest.raises(bundle.BundleError) as caught:
        bundle.read(ws["bundle"], ws["denylist"])
    assert caught.value.code != "private_term" or not leaks(caught.value.detail, caught.value.report)
    assert says_nothing(caught.value.detail)
    cli.main(["claims", str(ws["bundle"]), "--denylist", str(ws["denylist"])])
    out = capsys.readouterr()
    assert says_nothing(out.err + out.out)


def test_a_private_number_with_a_format_character_in_target_s_is_not_echoed(ws):
    private_bundle(ws, ENTRIES + [{"id": "num-b", "class": "number", "number": 12.5, "unit": None}])
    beat_target(ws["bundle"], "12​.5")
    error = refused("beat_invalid", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert "12" not in error.detail and says_nothing(error.detail)


def test_redact_withholds_an_escaped_detail():
    entries = private_terms.parse(json.dumps({"kind": "nv_denylist", "schema_version": 1, "salt": SALT,
                                              "entries": ENTRIES}).encode())  # fmt: skip
    assert "withheld" in private_terms.redact(entries, "x", repr("Quill​feather Labs"))
    assert "withheld" in private_terms.redact(entries, "x", "id 'a\\xadb'")
    assert private_terms.redact(entries, "x", "a plain detail") == "a plain detail"


def test_a_pinned_lane_withholds_details_before_its_denylist_is_bound(ws, monkeypatch, capsys):
    digest = write_denylist(ws["denylist"])
    declare(ws["bundle"], digest)
    unknown_manifest_key(ws["bundle"], "Quillfeather Labs")
    monkeypatch.setenv(private_terms.PIN_ENV, digest)
    error = refused("bundle_invalid", bundle.claims_only, ws["bundle"])
    assert "withheld" in error.detail and not leaks(error.detail)
    assert cli.main(["claims", str(ws["bundle"])]) == 1
    assert not leaks(capsys.readouterr().err)
    monkeypatch.delenv(private_terms.PIN_ENV)
    error = refused("bundle_invalid", bundle.claims_only, ws["bundle"], None, digest)
    assert "withheld" in error.detail
    state = {"entries": None, "pinned": True}
    with pytest.raises(bundle.BundleError) as caught, bundle.withheld(state):
        raise bundle.BundleError("asset_missing", f"{NAME} is gone")
    assert "withheld" in caught.value.detail


def test_an_unpinned_undeclared_bundle_keeps_its_details(ws, monkeypatch):
    monkeypatch.delenv(private_terms.PIN_ENV, raising=False)
    edit_json(ws["bundle"] / "claims.json", lambda rows: rows[0]["value"].update(unit="furlongs"))
    error = refused("claim_invalid", bundle.claims_only, ws["bundle"])
    assert "value.unit" in error.detail and "withheld" not in error.detail


# The 12.5 and 3375 cases of the shared fixture's denylist, in forms cade does not read yet (TIN-7735 F-C). Each is
# video-utils only until the shared fixture adds it in step with cade.
NUMBER_ROWS = [NAME_ROW, {"id": "num-x", "class": "number", "number": 12.5, "unit": "deg"},
               {"id": "num-y", "class": "number", "number": 3375, "unit": None}]  # fmt: skip
GROUPED_REFUSE = [
    "3 375", "3 375", "3 375", "3 375", "3'375", "3’375", "3_375", "1.25e1", "125E-1",
    "twelve point fifty", "twelve point five zero", "thirty three seventy five", "12 and a half", "twelve and 1/2",
    "12 and 1/2", "one two point five", "three three seven five",
]  # fmt: skip
GROUPED_PASS = ["12 and 12", "beats 12 375 times", "1 2 3 4", "3 37 5", "12 375", "version 1.2.4", "1e5 runs"]


@pytest.mark.parametrize("said", GROUPED_REFUSE)
def test_a_grouped_exponent_or_spelled_number_refuses(said):
    entries = private_terms.parse(json.dumps({"kind": "nv_denylist", "schema_version": 1, "salt": SALT,
                                              "entries": NUMBER_ROWS}).encode())  # fmt: skip
    assert private_terms.scan(entries, [("x", "record", said)])


@pytest.mark.parametrize("said", GROUPED_PASS)
def test_nearby_number_forms_still_pass(said):
    entries = private_terms.parse(json.dumps({"kind": "nv_denylist", "schema_version": 1, "salt": SALT,
                                              "entries": NUMBER_ROWS}).encode())  # fmt: skip
    assert private_terms.scan(entries, [("x", "record", said)]) == []


@pytest.mark.parametrize("receipt", ["3 375", "3'375", "1.25e1"])
def test_a_grouped_or_exponent_number_in_a_receipt_refuses_at_intake(ws, tmp_path, receipt):
    private_bundle(ws, ENTRIES + NUMBER_ROWS[1:])
    edit_json(ws["bundle"] / "manifest.json", lambda m: m["assets"][0].update(receipt=f"run {receipt}"))
    error = refused("private_term", intake, ws, tmp_path / "out", denylist=ws["denylist"])
    assert error.report["matches"][0]["segment"] == "asset#1" and not (tmp_path / "out").exists()
    edit_json(ws["bundle"] / "manifest.json", lambda m: m["assets"][0].update(receipt="synthetic receipt"))
    edit_json(ws["bundle"] / "claims.json", lambda rows: rows[0].update(receipt=f"run {receipt}"))
    assert refused("private_term", intake, ws, tmp_path / "out", denylist=ws["denylist"]).report["matches"]


def test_a_term_split_across_two_beats_refuses_as_joined(ws):
    private_bundle(ws)
    set_script(ws["bundle"], "eight seven seven milliseconds.", "eight seven seven milliseconds. Quillfeather.")
    set_script(ws["bundle"], "The fixture cache then", "Labs. The fixture cache then")
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert error.report["matches"] == [{"segment": "intro+result", "source": "joined", "entry": 0, "class": "name"}]
    assert not leaks(error.detail, error.report)


def test_a_joined_text_does_not_repeat_a_part_match(ws):
    private_bundle(ws)
    set_script(ws["bundle"], "stands in for a demo", f"stands in for {NAME}")
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert [m["source"] for m in error.report["matches"]] == ["voiced"]
