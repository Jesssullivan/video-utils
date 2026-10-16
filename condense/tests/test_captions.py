import copy
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


V5 = dict(fill="chars", split="balanced", max_s=6, sentence_chars=0, clear_s=0.02, squeeze_s=0.3)  # a [captions]


def styled(cfg, **captions):
    """A copy of the talk's config with some [captions] keys changed."""
    out = copy.copy(cfg)
    out.captions = cfg.captions | captions
    return out


def test_the_default_style_is_the_original_one(talk, tl):
    assert talk.captions["words"] == "spoken" and not talk.captions["fillers"] and not talk.captions["cards"]
    assert captions.build(talk) == captions.cues(captions.output_words(talk, tl))


def test_start_words_keep_pause_words_and_drop_words_that_start_in_a_cut(tl):
    said = dict(start=9.2, end=9.5, word="so")  # inside the short pause at 9.067-9.667 s
    assert captions.spoken(tl, "talk", said) is None
    assert captions.started(tl, "talk", said)[0] == pytest.approx(tl.to_out("talk", 9.2))
    edge = dict(start=3.95, end=4.3, word="on")  # in the cut's kept head
    assert captions.spoken(tl, "talk", edge) is not None and captions.started(tl, "talk", edge) is None
    late = captions.started(tl, "talk", dict(start=13.8, end=14.5, word="here"))  # its end is cut
    assert late[1] - late[0] == pytest.approx(0.25)


def test_fillers_true_captions_a_filler_said_at_speech_speed(tl):
    um = dict(start=12.0, end=12.2, word="um")  # inside speech
    for words in (captions.spoken, captions.started):
        assert words(tl, "talk", um) is None and words(tl, "talk", um, fillers=True) is not None
        assert words(tl, "talk", dict(start=9.8, end=10.2, word="um"), fillers=True) is None  # a filler span


def test_start_words_are_the_spoken_words_here(talk, tl):
    start = captions.output_words(styled(talk, words="start", fillers=True), tl)
    assert [w for _, _, w in start] == [w for _, _, w in captions.output_words(talk, tl)]
    assert start == sorted(start)


def test_a_chars_fill_counts_characters_not_wrapped_lines():
    words = [(i * 0.1, i * 0.1 + 0.05, chr(97 + i) * 22) for i in range(6)]  # 22 characters: one per line
    assert [len(t) for _, _, t in captions.cues(words)] == [2, 2, 2]
    found = captions.cues(words, fill="chars", split="balanced")  # 3 words are 68 characters, under 2 x 42
    assert [len(" ".join(t).split()) for _, _, t in found] == [3, 3] and all(len(t) == 2 for _, _, t in found)


def test_a_balanced_split_breaks_near_the_middle():
    text = "a" * 30 + " bbbbb " + "c" * 20
    assert captions.split_lines(text, 42) == ["a" * 30 + " bbbbb", "c" * 20]
    assert captions.split_lines(text, 42, "balanced") == ["a" * 30, "bbbbb " + "c" * 20]
    assert captions.split_lines("short one", 42, "balanced") == ["short one"]
    assert captions.split_lines("x" * 50, 42, "balanced") == ["x" * 50]


def test_max_s_and_every_sentence_end_close_a_cue():
    words = [(i * 0.5, i * 0.5 + 0.4, "word") for i in range(10)]
    assert len(captions.cues(words)) == 1
    assert [len(t[0].split()) for _, _, t in captions.cues(words, max_s=2)] == [4, 4, 2]
    said = [(0.0, 0.2, "Hi."), (0.3, 0.5, "Yes.")]
    assert [t for _, _, t in captions.cues(said)] == [["Hi. Yes."]]  # under half a line: no break
    assert [t for _, _, t in captions.cues(said, sentence_chars=0)] == [["Hi."], ["Yes."]]


def test_a_cue_too_close_to_the_next_holds_and_pushes_it():
    said = [(0.0, 0.1, "A."), (0.2, 0.3, "B."), (1.0, 1.1, "C.")]
    original = captions.cues(said, sentence_chars=0)
    assert [(a, b) for a, b, _ in original] == [(0.0, 0.2), (0.2, 1.0), (1.0, 2.0)]
    held = captions.cues(said, min_s=0.6, sentence_chars=0, clear_s=0.02, squeeze_s=0.3)
    assert [(a, b) for a, b, _ in held] == pytest.approx([(0.0, 0.6), (0.6, 0.98), (1.0, 1.6)])


def test_a_card_caption_sits_over_the_card(talk, tl):
    lines = ["[This part was lost:", "the disk was full]"]
    found = captions.build(styled(talk, cards={"lost": lines}, **V5))
    card = tl.by_clip["lost"][1][0]
    assert found[-1][:2] == pytest.approx([card[0] + 0.5, card[1] - 0.5]) and found[-1][2] == lines
    assert all(a < b for a, b, _ in found) and all(x[1] <= y[0] for x, y in zip(found, found[1:], strict=False))
    assert "lost" not in " ".join(" ".join(t) for _, _, t in captions.build(talk))
