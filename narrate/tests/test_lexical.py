"""The pinned lexical release (fixture lexicon), advisory findings, Vale's absence and the RewriteCheck."""

import json
import shutil

import pytest
from conftest import LEXICAL, fixture_pin, narration_fixture, sha

from narrate import lexical
from narrate.ir import Script, Segment
from narrate.lexical import LexicalError


def segs(*texts):
    return tuple(Segment(id=f"p{i}", text=t) for i, t in enumerate(texts, 1))


def test_release_verifies_every_pinned_digest():
    release = lexical.Release(LEXICAL, fixture_pin())
    assert release.record()["lexicon_sha256"] == fixture_pin()["lexiconSha256"]
    assert release.prompt_digest().startswith("# xoxd-lexical fixture")


@pytest.mark.parametrize("key", ["lexiconSha256", "promptDigestSha256", "valeRegisterSha256"])
def test_release_refuses_a_digest_mismatch(key):
    with pytest.raises(LexicalError) as caught:
        lexical.Release(LEXICAL, fixture_pin() | {key: "0" * 64})
    assert caught.value.code == "lexical_digest_mismatch"


def test_release_refuses_a_missing_directory_file_or_version(tmp_path):
    with pytest.raises(LexicalError, match="lexical_missing"):
        lexical.Release(None, fixture_pin())
    with pytest.raises(LexicalError, match="lexical_missing"):
        lexical.Release(tmp_path, fixture_pin())
    with pytest.raises(LexicalError, match="version"):
        lexical.Release(LEXICAL, fixture_pin() | {"release": "xoxd-lexical@0.2.0"})
    with pytest.raises(LexicalError, match="lexical_missing"):
        lexical.Release(LEXICAL, fixture_pin() | {"valeRegister": "doc"})


def test_findings_are_advisory_and_register_bound():
    release = lexical.Release(LEXICAL, fixture_pin())
    record = lexical.findings(release, segs("Let us delve into it.", "He was kind enough to come."))
    assert record["advisory"] is True
    assert [(f["rule"], f["segment"], f["match"]) for f in record["findings"]] == [("XL-FIX-001", "p1", "delve")]
    assert [s["rule"] for s in record["skipped_rules"]] == ["XL-FIX-003"]  # a pattern Python cannot compile


def test_vale_absent_is_not_run(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    release = lexical.Release(LEXICAL, fixture_pin())
    assert lexical.vale(release, segs("Text.")) == {
        "status": "not_run",
        "reason": "vale is not on PATH",
        "advisory": True,
    }


@pytest.mark.parametrize(
    "before,after",
    [
        ("We ship 3 tools in 2026.", "In 2026 we will ship 3 tools."),
        ("Gate v0.2.0 allows 8% at -16 LUFS.", "At -16 LUFS, gate v0.2.0 allows 8%."),
        ("Set fitMaxStretch in narrate/config.py.", "In narrate/config.py, set fitMaxStretch."),
    ],
)
def test_rewrite_that_keeps_spans_but_reorders_them_is_refused(before, after):
    assert lexical.rewrite_check(before, after)  # same spans, other order: XL-ACC-002 order


@pytest.mark.parametrize(
    "before,after",
    [
        ("We ship 3 tools in 2026.", "We now ship 3 tools in 2026."),
        ("Read TIN-7087 first, then narrate/config.py.", "First read TIN-7087, then narrate/config.py, please."),
        ("It runs at 24000 Hz.", "It runs at 24000 Hz, always."),
    ],
)
def test_rewrite_that_keeps_every_span_is_accepted(before, after):
    assert lexical.rewrite_check(before, after) == []


@pytest.mark.parametrize(
    "before,after,rule",
    [
        ("We ship 3 tools.", "We ship 4 tools.", "XL-ACC-001"),
        ("Set fitMaxStretch.", "Set fit_max_stretch.", "XL-ACC-001"),
        ("See the docs.", "See https://example.invalid/docs.", "XL-ACC-001"),
        ("It needs 16 GiB.", "It needs 16 GB.", "XL-ACC-001"),
        ("Pinned at v0.2.0 today.", "Pinned today.", "XL-ACC-002"),
        ("Ask @maintainer about TIN-7087.", "Ask about it.", "XL-ACC-002"),
    ],
)
def test_rewrite_that_changes_a_span_is_refused(before, after, rule):
    assert rule in {v["rule"] for v in lexical.rewrite_check(before, after)}


def test_check_rewrite_on_scripts():
    original = Script(kind="PlainText", segments=segs("We ship 3 tools.", "Then 2 more."))
    good = Script(kind="PlainText", segments=segs("We will ship 3 tools.", "Then 2 more after that."))
    assert lexical.check_rewrite(original, good)["status"] == "accepted"
    bad = Script(kind="PlainText", segments=segs("We ship 3 tools.", "Then 5 more."))
    with pytest.raises(LexicalError) as caught:
        lexical.check_rewrite(original, bad)
    assert caught.value.code == "rewrite_refused" and "p2" in caught.value.detail
    with pytest.raises(LexicalError, match="segment ids"):
        lexical.check_rewrite(original, Script(kind="PlainText", segments=segs("We ship 3 tools.")))


def narration_release(tmp_path, table=None):
    """Synthetic public fixture, never a vendored private lexical table."""
    return lexical.Release(tmp_path, narration_fixture(tmp_path, table))


def test_narration_uses_its_own_pinned_prompt_and_authenticated_table(tmp_path):
    release = narration_release(tmp_path)
    assert release.prompt_digest() == "# fixture narration-only prompt\n"
    assert release.upstream_pronunciation["entries"][0]["id"] == "fixture-1"
    assert lexical.Release(LEXICAL, fixture_pin()).upstream_pronunciation is None
    (tmp_path / "prompt-digest-narration.txt").unlink()
    with pytest.raises(LexicalError, match="lexical_missing"):
        lexical.Release(tmp_path, release.pin)


@pytest.mark.parametrize("change", ["missing", "empty", "duplicate", "flags", "blank-form"])
def test_narration_refuses_missing_or_malformed_authenticated_pronunciation(tmp_path, change):
    release = narration_release(tmp_path)
    path = tmp_path / "estate-lexicon.json"
    data = json.loads(path.read_text())
    if change == "missing":
        data.pop("pronunciation")
    elif change == "empty":
        data["pronunciation"]["entries"] = []
    elif change == "duplicate":
        data["pronunciation"]["entries"] *= 2
    elif change == "flags":
        data["pronunciation"]["entries"][0]["wholeWord"] = "yes"
    else:
        data["pronunciation"]["entries"][0]["spoken"] = " "
    path.write_text(json.dumps(data))
    with pytest.raises(LexicalError):
        lexical.Release(tmp_path, release.pin | {"lexiconSha256": sha(path.read_bytes())})


def test_narration_shared_layer_precedes_local_and_records_each_layer(tmp_path):
    from narrate.normalise import Normaliser

    release = narration_release(tmp_path)
    local = {
        "id": "fixture-local",
        "language": "en",
        "entries": [
            {"written": "A B C", "spoken": "local letters", "caseSensitive": True, "wholeWord": True, "note": None},
        ],
    }
    normaliser = Normaliser(local, upstream=release.upstream_pronunciation)
    assert normaliser.say("ABC 24000 Hz", "p1", record=False) == "local letters 24000 Hz"
    assert normaliser.record()["substitutions"] == []
    assert normaliser.record()["upstream"]["substitutions"] == []
    assert normaliser.say("ABC 24000 Hz", "p1") == "local letters 24000 Hz"
    record = normaliser.record()
    assert record["table"] == "fixture-local"
    assert record["upstream"]["table"] == "fixture-upstream"
    assert record["upstream"]["substitutions"][0]["written"] == "ABC"
    assert record["substitutions"][0]["written"] == "A B C"


def entry(written, spoken, case=True, whole=True, ident=None):
    return {"id": ident or written, "written": written, "spoken": spoken, "caseSensitive": case, "wholeWord": whole}


def test_longer_written_forms_apply_first_in_each_layer():
    """An overlapping prefix: the shorter entry must not consume the start of the longer one."""
    from narrate.normalise import Normaliser

    entries = [entry("xy", "ex why"), entry("xy-lexical", "ex why lexical")]
    upstream = {"id": "fixture-upstream", "language": "en", "entries": entries}
    local = {
        "id": "fixture-local",
        "language": "en",
        "entries": [entry("zq", "zed queue"), entry("zq-tool", "the tool")],
    }
    for order in (entries, entries[::-1]):
        normaliser = Normaliser(local, upstream=upstream | {"entries": order})
        assert normaliser.say("xy-lexical and xy, zq-tool and zq", "p1") == (
            "ex why lexical and ex why, the tool and zed queue"
        )


def test_case_sensitive_entries_match_case_and_insensitive_entries_do_not():
    from narrate.normalise import Normaliser

    upstream = {
        "id": "fixture-upstream",
        "language": "en",
        "entries": [entry("xy", "ex why", case=False), entry("SSOT", "S S O T", case=True)],
    }
    normaliser = Normaliser({"id": "fixture-local", "language": "en", "entries": []}, upstream=upstream)
    assert normaliser.say("XY, Xy and xy; SSOT not ssot", "p1") == "ex why, ex why and ex why; S S O T not ssot"


def test_a_local_entry_overrides_the_upstream_entry_with_its_written_form():
    from narrate.normalise import Normaliser

    upstream = {
        "id": "fixture-upstream",
        "language": "en",
        "entries": [entry("SSOT", "S S O T", ident="fixture-ssot"), entry("ABC", "A B C", ident="fixture-abc")],
    }
    local = {"id": "fixture-local", "language": "en", "entries": [entry("ssot", "single source of truth", case=False)]}
    normaliser = Normaliser(local, upstream=upstream)
    assert normaliser.say("The SSOT and ABC.", "p1") == "The single source of truth and A B C."
    record = normaliser.record()
    assert record["upstream"]["overridden_by_local"] == ["fixture-ssot"]
    assert [s["written"] for s in record["upstream"]["substitutions"]] == ["ABC"]
    assert [s["written"] for s in record["substitutions"]] == ["ssot"]
    assert (
        Normaliser(local, upstream=upstream | {"entries": upstream["entries"][1:]}).record()["upstream"][
            "overridden_by_local"
        ]
        == []
    )


def test_aliases_map_a_transcript_back_through_both_layers():
    from narrate import qa
    from narrate.normalise import Normaliser, recorded_aliases

    upstream = {"id": "fixture-upstream", "language": "en", "entries": [entry("ABC", "A B C")]}
    local = {"id": "fixture-local", "language": "en", "entries": [entry("A B C", "local letters")]}
    normaliser = Normaliser(local, upstream=upstream)
    text = "The ABC tool."
    spoken = normaliser.say(text, "p1")
    assert spoken == "The local letters tool."
    aliases = normaliser.aliases(text, "p1")
    assert aliases == [("local letters", "A B C"), ("A B C", "ABC")]
    assert recorded_aliases(normaliser.record(), "p1") == aliases
    assert recorded_aliases(normaliser.record(), "p2") == []
    for heard in ("The ABC tool.", "the local letters tool", "The A B C tool"):
        assert qa.chunk_wer(text, spoken, heard, aliases) == 0.0
