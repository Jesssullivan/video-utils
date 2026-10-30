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
    data = raw if raw is not None else json.dumps({"kind": "nv_denylist", "schema_version": 1, "entries": entries})
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
        json.dumps({"kind": "nv_denylist", "schema_version": 1, "entries": [NAME_ROW], "extra": 1}),
        json.dumps({"kind": "other", "schema_version": 1, "entries": [NAME_ROW]}),
        json.dumps({"kind": "nv_denylist", "schema_version": 2, "entries": [NAME_ROW]}),
        json.dumps({"kind": "nv_denylist", "schema_version": 1, "entries": []}),
        '{"kind": "nv_denylist", "kind": "nv_denylist", "schema_version": 1, "entries": []}',
        json.dumps({"kind": "nv_denylist", "schema_version": 1, "entries": [{"id": "x", "class": "name"}]}),
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
    assert private["checked"] == {"record": 19, "voiced": 2, "spoken": 0, "claim": 3, "label": 0}
    m = intake(ws, tmp_path / "out", persona="fixture-persona", denylist=ws["denylist"])
    assert m["private_terms"]["status"] == "passed" and m["states"]["private_terms"] == "passed"
    assert m["private_terms"]["checked"] == {"record": 21, "voiced": 2, "spoken": 4, "claim": 3, "label": 1}
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
    assert error.report["matches"] == [{"segment": "intro", "source": "voiced", "entry": "name-a", "class": "name"}]
    assert not leaks(error.detail, error.report)


def test_a_name_inside_a_longer_word_does_not_match(ws):
    private_bundle(ws)
    set_script(ws["bundle"], "stands in for a demo", "stands in for Quillfeather Labsworth")
    assert bundle.claims_only(ws["bundle"], ws["denylist"])["private_terms"]["status"] == "passed"


def test_a_geometry_pattern_refuses(ws):
    private_bundle(ws)
    set_script(ws["bundle"], "stands in for a demo", "shows its Chamfer   angle")
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert error.report["matches"][0]["entry"] == "geom-a"


@pytest.mark.parametrize("said", ["3.1416", "three point one four one six", "three point one four one six metres"])
def test_a_private_number_refuses_in_digits_or_words(ws, said):
    private_bundle(ws)
    set_script(ws["bundle"], "stands in for a demo", f"stands in for {said}")
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert error.report["matches"][0] == {"segment": "intro", "source": "voiced", "entry": "num-a", "class": "number"}


def test_a_number_entry_with_a_unit_matches_only_that_unit(ws):
    rows = [NAME_ROW, {"id": "num-b", "class": "number", "number": 42, "unit": "ms"}]
    private_bundle(ws, rows)
    assert bundle.claims_only(ws["bundle"], ws["denylist"])["ok"] is True  # the fixture says 42 percent
    rows = [NAME_ROW, {"id": "num-b", "class": "number", "number": 42, "unit": "percent"}]
    private_bundle(ws, rows)
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
    assert error.report["matches"] == [{"segment": "labels", "source": "label", "entry": "name-a", "class": "name"}]
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
    assert error.report["matches"] == [{"segment": "beat#2", "source": "record", "entry": "name-a", "class": "name"}]
    assert not leaks(error.detail, error.report)


def test_a_private_claim_receipt_refuses(ws):
    private_bundle(ws)
    edit_json(ws["bundle"] / "claims.json", lambda rows: rows[0].update(receipt=f"measured at {NAME}"))
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    assert error.report["matches"][0] == {"segment": "claim#1", "source": "record", "entry": "name-a", "class": "name"}
    assert not leaks(error.detail, error.report)


@pytest.mark.parametrize("key", ["receipt", "path", "id"])
def test_a_private_asset_text_refuses_before_any_asset_check(ws, key):
    private_bundle(ws)
    value = {"receipt": "the chamfer angle run", "path": "assets/chamfer-angle.png", "id": "chamfer-angle"}[key]
    edit_json(ws["bundle"] / "manifest.json", lambda m: m["assets"][0].update({key: value}))
    error = refused("private_term", bundle.claims_only, ws["bundle"], ws["denylist"])
    match = {"segment": "asset#1", "source": "record", "entry": "geom-a", "class": "geometry"}
    assert error.report["matches"][0] == match
    assert not leaks(error.detail, error.report)


def test_a_private_job_id_refuses_at_intake(ws, tmp_path):
    private_bundle(ws)
    error = refused("private_term", intake, ws, tmp_path / "out", job_id="quillfeather-labs", denylist=ws["denylist"])
    assert error.report["matches"] == [{"segment": "job", "source": "record", "entry": "name-a", "class": "name"}]
    assert not (tmp_path / "out").exists()


def test_a_private_bundle_directory_name_refuses_at_intake(ws, tmp_path):
    private_bundle(ws)
    renamed = ws["bundle"].with_name("quillfeather-labs")
    ws["bundle"].rename(renamed)
    ws["bundle"] = renamed  # the fixture manifest has no slug, so only the directory's name says the term
    error = refused("private_term", intake, ws, tmp_path / "out", job_id="demo", denylist=ws["denylist"])
    assert error.report["matches"] == [{"segment": "slug", "source": "record", "entry": "name-a", "class": "name"}]


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
    assert json.loads(captured.out)["private_terms"]["matches"][0]["entry"] == "name-a"
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
