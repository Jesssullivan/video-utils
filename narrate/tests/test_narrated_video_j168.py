"""The shipped private-terms defaults under J168 and SPR-339 (TIN-7125, docs/spec/NARRATED_VIDEO.md, "Private terms").

test_narrated_video_private_terms.py keeps the rules J168 stops, for the November 30, 2026 audit. This module does not
use its audit_rules fixture, so it reads what a release does. Every bundle and denylist here is synthetic.
"""

import json

import pytest
from test_narrated_video_private_terms import (
    ENTRIES,
    NAME,
    declare,
    intake,
    no_whisper,  # noqa: F401
    refused,
    write_denylist,
    ws,  # noqa: F401
)
from test_narrated_video_visible_text import add_text_source, text_json

from narrate.video import bundle, cli, deliver, private_terms
from narrate.video.job import JobError, load_records

NAME_ROW = {"id": "name-a", "class": "name", "literal": NAME}
GEOMETRY = {"id": "g", "class": "geometry", "regex": r"chamfer\s+angle"}


def test_the_shipped_defaults_are_the_j168_defaults():
    assert private_terms.MATCHED == ("name",) and private_terms.SCRIPT_MATCHES is False
    assert private_terms.NEEDS == {"never_name": {"name"}}


def test_an_ip_private_bundle_needs_no_denylist(ws):  # noqa: F811
    declare(ws["bundle"], None, ip_private=True, never_name=False)
    report = bundle.claims_only(ws["bundle"])["private_terms"]
    assert report["status"] == "not_declared" and report["ip_private"] is True


def test_an_ip_private_bundle_needs_no_number_or_geometry_entry(ws):  # noqa: F811
    declare(ws["bundle"], write_denylist(ws["denylist"], [NAME_ROW]), ip_private=True, never_name=False)
    assert bundle.claims_only(ws["bundle"], ws["denylist"])["private_terms"]["status"] == "passed"


@pytest.mark.parametrize(
    "text", ["it is 3.1416 wide", "three point one four one six", "the chamfer angle", "hеllo", "Zօrblax"]
)
def test_a_number_geometry_or_script_text_no_longer_matches(ws, text):  # noqa: F811
    entries = private_terms.parse(write_denylist_bytes(ws))
    assert private_terms.scan(entries, [("beat#1", "voiced", text)]) == []


def test_a_name_still_matches(ws):  # noqa: F811
    entries = private_terms.parse(write_denylist_bytes(ws))
    assert [m["class"] for m in private_terms.scan(entries, [("beat#1", "voiced", f"from {NAME}")])] == ["name"]


def test_never_name_still_needs_its_denylist_and_a_name_entry(ws):  # noqa: F811
    declare(ws["bundle"], None, ip_private=False, never_name=True)
    refused("denylist_missing", bundle.claims_only, ws["bundle"])
    declare(ws["bundle"], write_denylist(ws["denylist"], [GEOMETRY]), ip_private=False, never_name=True)
    refused("denylist_invalid", bundle.claims_only, ws["bundle"], ws["denylist"])


@pytest.mark.parametrize(
    "spelled",
    ["Quillfeather Labꜱ", "Quillfeather Lօbs", "Quillfꓰather Labs"],
    ids=["latin_small_capital", "armenian", "lisu"],
)
def test_a_listed_name_outside_the_confusables_floor_no_longer_refuses(ws, spelled, monkeypatch):  # noqa: F811
    entries = private_terms.parse(write_denylist_bytes(ws))
    assert private_terms.scan(entries, [("beat#1", "voiced", spelled)]) == []
    monkeypatch.setattr(private_terms, "SCRIPT_MATCHES", True)  # what the November 30, 2026 audit would restore
    assert [m["class"] for m in private_terms.scan(entries, [("beat#1", "voiced", spelled)])] == ["script"]


def never_name_bundle(ws):  # noqa: F811
    declare(ws["bundle"], write_denylist(ws["denylist"], [NAME_ROW]), ip_private=False, never_name=True)


def test_a_name_in_a_slide_still_refuses_at_intake(ws, tmp_path):  # noqa: F811
    never_name_bundle(ws)
    add_text_source(ws["bundle"], "slide-a", "slide-a.json", text_json(f"Built with {NAME}"))
    error = refused("private_term", intake, ws, tmp_path / "out", denylist=ws["denylist"])
    assert [(m["segment"], m["source"], m["class"]) for m in error.report["matches"]] == [
        ("asset#1", "visible", "name")
    ]
    assert not (tmp_path / "out").exists()


def marker_path(out):
    return out / "records" / private_terms.MARKER


@pytest.mark.parametrize("never_name", [True, False])
def test_the_marker_holds_never_name_so_a_load_needs_no_intake_json(ws, tmp_path, never_name):  # noqa: F811
    declare(ws["bundle"], write_denylist(ws["denylist"], [NAME_ROW]), ip_private=False, never_name=never_name)
    out = tmp_path / "out"
    intake(ws, out, denylist=ws["denylist"])
    assert load_records(out / "records")["never_name"] is never_name
    (out / "intake.json").unlink()
    assert load_records(out / "records")["never_name"] is never_name


def test_a_marker_older_than_the_flag_loads_with_no_flag(ws, tmp_path):  # noqa: F811
    never_name_bundle(ws)
    out = tmp_path / "out"
    intake(ws, out, denylist=ws["denylist"])
    marker = json.loads(marker_path(out).read_text())
    del marker["never_name"]
    marker_path(out).write_text(json.dumps(marker))
    assert load_records(out / "records")["never_name"] is None


@pytest.mark.parametrize("value", [False, "true", None, 1])
def test_a_marker_flag_that_disagrees_with_intake_json_or_is_no_boolean_refuses(ws, tmp_path, value):  # noqa: F811
    never_name_bundle(ws)
    out = tmp_path / "out"
    intake(ws, out, denylist=ws["denylist"])
    marker = json.loads(marker_path(out).read_text())
    marker_path(out).write_text(json.dumps(marker | {"never_name": value}))
    with pytest.raises(JobError) as caught:
        load_records(out / "records")
    assert caught.value.code == "private_terms_stale"
    (out / "intake.json").write_text("not json")
    marker_path(out).write_text(json.dumps(marker))
    with pytest.raises(JobError):
        load_records(out / "records")


def ip_private_only(ws, out):  # noqa: F811
    declare(ws["bundle"], None, ip_private=True, never_name=False)
    add_text_source(ws["bundle"], "slide-a", "slide-a.json", text_json("Cache rate"))
    return intake(ws, out)


def test_an_ip_private_bundle_with_no_denylist_keeps_the_unread_asset_hold(ws, tmp_path):  # noqa: F811
    out = tmp_path / "out"
    m = ip_private_only(ws, out)
    assert m["private_terms"]["status"] == "not_declared" and m["states"]["private_terms"] == "not_declared"
    assert m["states"]["visible_text"] == "partial" and "visible_text_unread" in m["admit"]["pending_operator"]
    summary = load_records(out / "records")["visible_text"]
    assert {k: summary[k] for k in ("state", "unread", "opaque")} == {
        "state": "partial",
        "unread": ["asset#2"],
        "opaque": [],
    }
    assert deliver.visible_gate(summary)[0] == "pending_operator"
    # The bundle is guarded, so it stores its shown text and both records bind the digest.
    assert summary["source_sha256"] == m["visible_text"]["source_sha256"]
    assert (ws["store"] / f"{summary['source_sha256']}.json").is_file()
    assert load_records(out / "records")["never_name"] is False


def test_an_ip_private_bundle_passes_the_gate_once_every_shown_asset_has_a_source(ws, tmp_path):  # noqa: F811
    add_text_source(ws["bundle"], "slide-b", "slide-b.json", text_json("Build time"))
    m = ip_private_only(ws, tmp_path / "out")
    assert m["states"]["visible_text"] == "passed"


def test_a_deleted_marker_beside_an_ip_private_intake_refuses(ws, tmp_path):  # noqa: F811
    out = tmp_path / "out"
    ip_private_only(ws, out)
    marker_path(out).unlink()
    with pytest.raises(JobError) as caught:
        load_records(out / "records")
    assert caught.value.code == "private_terms_stale"


def test_nv_subject_on_an_ip_private_marker_prints_the_fact_and_does_not_refuse(ws, tmp_path, capsys):  # noqa: F811
    out = tmp_path / "out"
    ip_private_only(ws, out)
    common = ["--root", str(tmp_path / "narrated"), "--records", str(out / "records"), "--store", str(ws["store"]),
              "--lexical", str(ws["lexical"])]  # fmt: skip
    assert cli.main(["init", "--job", "demo-fixture", "--from", str(out / "narrated-video.json"), *common]) == 0
    capsys.readouterr()
    assert cli.main(["subject", "demo-fixture", *common]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["shown_unread"] == ["slide"]
    assert [t["text"] for t in printed["texts"] if t["field"] == "visible_text"] == ["Cache rate"]


def write_denylist_bytes(ws):  # noqa: F811
    write_denylist(ws["denylist"], ENTRIES)
    return ws["denylist"].read_bytes()
