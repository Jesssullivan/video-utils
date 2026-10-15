import json

import pytest

from condense import captions
from condense.edl import Timeline


@pytest.fixture(scope="module")
def tl(talk):
    return Timeline(json.loads(talk.f("edl", "json").read_text()))


def test_words_land_at_their_mapped_times(talk, tl):
    words = captions.output_words(talk, tl)
    assert [w for _, _, w in words[:4]] == ["Hello", "and", "welcome", "everyone."]
    assert words[0][0] == pytest.approx(tl.to_out("talk", 1.2), abs=0.02)
    first = next(w for w in words if w[2] == "first")  # said from 8.0 s to 8.4 s at 2x
    assert first[0] == pytest.approx(tl.to_out("talk", 8.0), abs=0.01)
    assert first[1] - first[0] == pytest.approx(0.2, abs=0.02)
    assert [a for a, _, _ in words] == sorted(a for a, _, _ in words) and words[-1][1] <= tl.total


def test_fillers_and_cut_words_are_dropped(talk, tl):
    assert "um" not in [w for _, _, w in captions.output_words(talk, tl)]
    assert captions.spoken(tl, "talk", dict(start=4.8, end=5.2, word="ghost")) is None  # inside the cut
    assert captions.spoken(tl, "talk", dict(start=10.0, end=10.2, word="actually")) is None  # in a filler span
    late = captions.spoken(tl, "talk", dict(start=6.0, end=6.9, word="This"))  # DTW start early, in the cut
    assert late[0] == pytest.approx(tl.to_out("talk", 6.0, snap=True))


def test_captions_fit_two_lines_of_42_characters(talk, tl):
    found = captions.cues(captions.output_words(talk, tl))
    assert [" ".join(t) for _, _, t in found][:2] == ["Hello and welcome everyone.", "This is the first point."]
    long = [(i * 0.3, i * 0.3 + 0.25, "word") for i in range(60)]
    for a, b, lines in found + captions.cues(long):
        assert a < b and len(lines) <= 2 and all(len(line) <= 42 for line in lines)
    assert all(a[1] <= b[0] for a, b in zip(found, found[1:], strict=False))


def test_a_gap_starts_a_new_caption():
    found = captions.cues([(0.0, 0.3, "one"), (0.4, 0.7, "two"), (2.0, 2.3, "three")])
    assert [(a, t) for a, _, t in found] == [(0.0, ["one two"]), (2.0, ["three"])]
    assert found[0][1] == 1.0 and found[1][1] == 3.0  # held for a second


def test_srt_and_vtt_formats():
    found = [[1.5, 3.25, ["Hello and", "welcome."]], [3661.001, 3662.0, ["Bye."]]]
    assert captions.srt(found) == (
        "1\n00:00:01,500 --> 00:00:03,250\nHello and\nwelcome.\n\n2\n01:01:01,001 --> 01:01:02,000\nBye.\n"
    )
    assert captions.vtt(found).startswith(
        "WEBVTT\n\n00:00:01.500 --> 00:00:03.250\nHello and\nwelcome.\n\n01:01:01.001"
    )
