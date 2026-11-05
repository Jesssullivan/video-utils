"""Chunker edge cases and spoken normalisation."""

import json

import pytest
from conftest import EXAMPLES

from narrate import chunker
from narrate.ir import Segment
from narrate.normalise import NormaliseError, Normaliser
from narrate.render import chunk_spoken

TABLE = json.loads((EXAMPLES / "pronunciation.json").read_text())


def chunks(text, limit=300):
    return chunker.chunk_segment(Segment(id="s", text=text), limit)


def test_short_paragraphs_never_merge():
    out = chunks("One sentence here.\n\nAnother paragraph.")
    assert [(c.id, c.paragraph, c.text, c.last_in_paragraph) for c in out] == [
        ("s.c01", 0, "One sentence here.", True),
        ("s.c02", 1, "Another paragraph.", True),
    ]


def test_sentences_pack_up_to_the_limit():
    sentence = "This sentence has exactly forty chars.."
    out = chunks(" ".join([sentence] * 10), limit=100)
    assert all(len(c.text) <= 100 for c in out)
    assert " ".join(c.text for c in out) == " ".join([sentence] * 10)
    assert len(out) == 5


def test_abbreviations_initials_and_decimals_do_not_end_sentences():
    assert chunker.sentences("Use e.g. the 3.5 GiB model. J. Smith said so. Done!") == [
        "Use e.g. the 3.5 GiB model.",
        "J. Smith said so.",
        "Done!",
    ]


def test_a_long_sentence_splits_at_a_clause_then_at_a_space():
    text = (
        "The first clause runs on for a while, the second clause continues further along; "
        "and the third clause carries the remaining words of this long sentence onward"
    )
    out = chunks(text, limit=60)
    assert all(len(c.text) <= 60 for c in out)
    assert out[0].text.endswith(",")
    assert " ".join(c.text for c in out) == text


@pytest.mark.parametrize(
    "span", ["1,234,567.89 GiB", "fitMaxStretch_value_identifier", "v0.2.0-rc.1", "narrate/dhall/examples/jobs.json"]
)
def test_no_split_inside_a_number_or_identifier(span):
    text = ("word " * 9) + span + (" word" * 20)
    for limit in range(20, 80, 3):
        out = chunks(text, limit=limit)
        assert " ".join(c.text for c in out) == " ".join(text.split())
        assert any(span in c.text for c in out), (limit, [c.text for c in out])


def test_a_span_longer_than_the_limit_stays_whole_and_is_flagged():
    url = "https://example.invalid/" + "a" * 60
    out = chunks(f"See {url} now.", limit=30)
    holder = [c for c in out if url in c.text]
    assert holder and holder[0].oversize
    assert not any(c.oversize for c in out if url not in c.text)


def test_limit_floor():
    with pytest.raises(ValueError):
        chunks("x", limit=10)


def test_normaliser_expands_and_records():
    n = Normaliser(TABLE)
    said = n.say("The MCP gate allows 8% at -16 LUFS. MCPs stay.", "s1")
    assert said == "The M C P gate allows 8 percent at -16 loudness units relative to full scale. MCPs stay."
    record = n.record()
    assert record["table"] == "narrate-en-example" and len(record["sha256"]) == 64
    assert {(s["written"], s["count"]) for s in record["substitutions"]} == {("MCP", 1), ("8%", 1), ("LUFS", 1)}


def test_normaliser_refuses_an_entry_that_changes_digits():
    table = {
        **TABLE,
        "entries": [{"written": "v2", "spoken": "version two", "caseSensitive": True, "wholeWord": True, "note": None}],
    }
    with pytest.raises(NormaliseError, match="digits"):
        Normaliser(table).say("Use v2 now.", "s1")


def test_spoken_overflow_is_chunked_again():
    table = {
        **TABLE,
        "entries": [
            {
                "written": "LUFS",
                "spoken": "loudness units relative to full scale",
                "caseSensitive": True,
                "wholeWord": True,
                "note": None,
            }
        ],
    }
    text = " ".join(["LUFS"] * 14) + "."
    out = chunk_spoken(Segment(id="s", text=text), 100, Normaliser(table))
    assert len(out) > 1
    assert all(len(spoken) <= 100 for _, spoken in out)
    assert " ".join(c.text for c, _ in out) == text
