"""Every input adapter on synthetic text: the IR shape, stable ids, directions, cue timing, dialog turns and the
condense words.json mapping through an EDL."""

import json

import pytest
from conftest import SLIDE

from condense.edl import Timeline
from narrate import adapters
from narrate.adapters import InputError


def load(tmp_path, kind, text, name="input.txt", **options):
    path = tmp_path / name
    path.write_text(text if isinstance(text, str) else json.dumps(text))
    return adapters.load(kind, path, options)


def test_plain_text_is_one_segment_per_paragraph(tmp_path):
    script = load(tmp_path, "PlainText", "First line\ncontinues here.\n\n\nSecond paragraph.\n")
    assert [s.id for s in script.segments] == ["p0001", "p0002"]
    assert script.segments[0].text == "First line continues here."
    assert script.segments[1].origin == "line 5"
    assert (
        script.digest() == load(tmp_path, "PlainText", "First line\ncontinues here.\n\n\nSecond paragraph.\n").digest()
    )


def test_plain_text_refuses_an_empty_file(tmp_path):
    with pytest.raises(InputError):
        load(tmp_path, "PlainText", "\n \n")


def test_markdown_front_matter_sources_directions_and_markup(tmp_path):
    script = load(tmp_path, "Markdown", SLIDE, name="03-gates.md")
    (segment,) = script.segments
    assert segment.id == "slide-3"
    assert segment.target_dur == 30.0 and segment.target_start is None
    assert segment.paragraphs() == [
        "Narrate reads this slide with the fake engine. Version 2 of the gate allows 8% of stretch.",
        "The MCP tool lists every voice and its consent state.",
    ]
    assert "Sources" not in segment.text and "Gate numbers" not in segment.text
    (pause,) = segment.directions
    assert (pause.kind, pause.pause_ms, pause.paragraph) == ("pause", 400, 1)
    assert script.meta["sources_line"] == 14


def test_markdown_inline_markup_and_note_directions(tmp_path):
    text = (
        "Read **this** and _that_ with `code`, a [link](https://example.invalid/x) and <!-- hidden -->text.\n\n"
        "[slow down here]\n[pause for the diagram]\n[pause 1.5s]\n\nEnd.\n"
    )
    (segment,) = load(tmp_path, "Markdown", text, name="slide.md").segments
    assert segment.paragraphs()[0] == "Read this and that with code, a link and text."
    kinds = [(d.kind, d.pause_ms, d.paragraph) for d in segment.directions]
    assert kinds == [("note", None, 1), ("pause", None, 1), ("pause", 1500, 1)]
    assert segment.id == "slide-slide" and segment.target_dur is None


def test_markdown_refusals(tmp_path):
    with pytest.raises(InputError, match="never closed"):
        load(tmp_path, "Markdown", "---\nslide: 1\n", name="a.md")
    with pytest.raises(InputError, match="only `key: value`"):
        load(tmp_path, "Markdown", "---\nslide: 1\nText.\n---\n", name="a2.md")
    with pytest.raises(InputError, match="target_seconds"):
        load(tmp_path, "Markdown", "---\ntarget_seconds: soon\n---\nText.\n", name="b.md")
    with pytest.raises(InputError, match="no narration"):
        load(tmp_path, "Markdown", "[pause]\nSources: x\nText after sources.\n", name="c.md")


SRT = """1
00:00:01,000 --> 00:00:03,500
<i>First</i> cue,
two lines.

2
00:00:04,000 --> 00:00:05,250
Second cue.

3
00:00:06,000 --> 00:00:06,500

"""


def test_srt_cues_become_timed_segments(tmp_path):
    script = load(tmp_path, "Srt", SRT, name="c.srt")
    assert [(s.id, s.text, s.target_start, s.target_dur) for s in script.segments] == [
        ("cue-0001", "First cue, two lines.", 1.0, 2.5),
        ("cue-0002", "Second cue.", 4.0, 1.25),
    ]


def test_srt_refuses_overlap_and_reversed_cues(tmp_path):
    with pytest.raises(InputError, match="before the previous"):
        load(tmp_path, "Srt", "1\n00:00:01,000 --> 00:00:03,000\nA\n\n2\n00:00:02,000 --> 00:00:04,000\nB\n")
    with pytest.raises(InputError, match="ends at or before"):
        load(tmp_path, "Srt", "1\n00:00:03,000 --> 00:00:03,000\nA\n")


def test_vtt_voice_spans_notes_and_short_timestamps(tmp_path):
    text = (
        "WEBVTT\n\nNOTE a note block\nwith two lines\n\nintro\n00:01.000 --> 00:02.500 align:start\n"
        "<v Ana>Hello there.</v>\n\n01:00:00.000 --> 01:00:01.000\n<v.loud Ben>Late cue.\n"
    )
    script = load(tmp_path, "Vtt", text, name="c.vtt")
    assert [(s.speaker, s.text, s.target_start, s.target_dur) for s in script.segments] == [
        ("Ana", "Hello there.", 1.0, 1.5),
        ("Ben", "Late cue.", 3600.0, 1.0),
    ]
    with pytest.raises(InputError, match="WEBVTT"):
        load(tmp_path, "Vtt", "00:01.000 --> 00:02.000\nx\n", name="d.vtt")


def test_dialog_turns_and_continuations(tmp_path):
    text = "ANA: Hello and welcome.\nIt is a short one.\n\nBEN: Thanks, Ana.\nANA: Bye.\n"
    script = load(tmp_path, "Dialog", text)
    assert [(s.id, s.speaker, s.text) for s in script.segments] == [
        ("turn-0001", "ANA", "Hello and welcome. It is a short one."),
        ("turn-0002", "BEN", "Thanks, Ana."),
        ("turn-0003", "ANA", "Bye."),
    ]
    assert script.meta["speakers"] == ["ANA", "BEN"]
    with pytest.raises(InputError, match="outside any SPEAKER"):
        load(tmp_path, "Dialog", "no speaker here\n")


EDL = {
    "fps": 30,
    "clips": [
        {
            "name": "talk",
            "shift": 0.0,
            "segments": [
                {"kind": "speech", "inp": 0.0, "out": 2.0, "speed": 1.0, "frames": 60},
                {"kind": "cut", "inp": 2.0, "out": 5.0, "speed": 1.0, "frames": 6, "keep": [[2.0, 2.1], [4.9, 5.0]]},
                {"kind": "speech", "inp": 5.0, "out": 9.0, "speed": 2.0, "frames": 60},
            ],
        }
    ],
}
WORDS = [
    {"start": 0.2, "end": 0.5, "word": "Hello"},
    {"start": 0.6, "end": 1.0, "word": "there."},
    {"start": 5.5, "end": 6.0, "word": "After"},
    {"start": 6.1, "end": 7.0, "word": "the"},
    {"start": 7.1, "end": 8.0, "word": "cut"},
]


def test_condense_words_map_through_the_edl(tmp_path):
    (tmp_path / "edl.json").write_text(json.dumps(EDL))
    script = load(tmp_path, "CondenseWords", WORDS, name="talk.words.json", edl=str(tmp_path / "edl.json"), clip="talk")
    timeline = Timeline(EDL)
    first, second = script.segments
    assert (first.text, second.text) == ("Hello there.", "After the cut")
    assert first.target_start == pytest.approx(0.2) and first.target_dur == pytest.approx(0.8)
    assert second.target_start == pytest.approx(timeline.to_out("talk", 5.5), abs=1e-3)
    assert second.target_start == pytest.approx(2.2 + 0.5 / 2, abs=1e-3)  # 66 frames in, then 2x speech
    end = timeline.to_out("talk", 8.0)
    assert second.target_start + second.target_dur == pytest.approx(end, abs=2e-3)
    assert script.meta["mapping"] == "condense_edl" and len(script.meta["edl_sha256"]) == 64


def test_condense_words_without_an_edl_stay_on_the_source_clock(tmp_path):
    script = load(tmp_path, "CondenseWords", WORDS, name="w.json", sentence_gap_s=1.0)
    assert [s.target_start for s in script.segments] == [0.2, 5.5]
    assert script.meta["mapping"] == "source_clock"


def test_condense_words_refusals(tmp_path):
    (tmp_path / "edl.json").write_text(json.dumps(EDL))
    with pytest.raises(InputError, match="clip"):
        load(tmp_path, "CondenseWords", WORDS, name="w.json", edl=str(tmp_path / "edl.json"), clip="other")
    with pytest.raises(InputError, match="words.json"):
        load(tmp_path, "CondenseWords", {"words": []}, name="x.json")


def test_unknown_kind(tmp_path):
    with pytest.raises(InputError, match="input kind"):
        load(tmp_path, "Docx", "x")
