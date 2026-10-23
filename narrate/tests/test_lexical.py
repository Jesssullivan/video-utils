"""The pinned lexical release (fixture lexicon), advisory findings, Vale's absence and the RewriteCheck."""

import shutil

import pytest
from conftest import LEXICAL, fixture_pin

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
