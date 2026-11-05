"""`narrate spoken` prints only what a render voices (TIN-7097): synthetic manuscript, SRT and dialog inputs."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from narrate import adapters, lexical, spoken
from narrate.__main__ import main

PAGE = """---
slide: 17
target_seconds: 38
---

# Tide windows

<!-- build 1 -->
[at 0:00: open on the tide table]

Each row of the table is one high tide. A two-hour window opens before each row.

[clip: tide-pan.mp4]
<!--
build 2: the moon phase appears
-->

[at 0:19: the moon phase]
The moon phase sits in the last column,
and a full moon means a wider window.

Sources: Fixture tide log 2026, https://example.invalid/tides, data/tides.csv
Nothing after Sources is spoken.
"""

PAGE_LINES = [
    "Each row of the table is one high tide. A two-hour window opens before each row.",
    "The moon phase sits in the last column, and a full moon means a wider window.",
]

CAPTIONS = """1
00:00:01,000 --> 00:00:03,500
<i>First</i> caption line
continues here.

2
00:00:04,000 --> 00:00:06,250
Second caption.

3
00:01:02,125 --> 00:01:05,000
Third, a minute in.
"""

DIALOG = """HOST: Welcome to the fixture show.
It runs on synthetic text only.

GUEST: Thanks. The **demo** starts now.
HOST: Then let us start.
"""


def run(capsys, *argv):
    code = main(["spoken", *map(str, argv)])
    out, err = capsys.readouterr()
    return code, out, err


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_manuscript_page_yields_exactly_the_spoken_lines(tmp_path, capsys):
    page = write(tmp_path, "17-tides.md", PAGE)
    code, out, err = run(capsys, page)
    assert code == 0 and err == ""
    assert out == "\n\n".join(PAGE_LINES) + "\n"
    assert [line for line in out.splitlines() if line] == PAGE_LINES
    for unspoken in ("slide", "target_seconds", "---", "Tide windows", "build", "[at", "clip:", "Sources", "csv"):
        assert unspoken not in out


def test_spoken_text_is_the_text_the_render_reads(tmp_path):
    page = write(tmp_path, "17-tides.md", PAGE)
    script = adapters.load("Markdown", page)
    assert spoken.lines(script).rstrip("\n").split("\n\n") == script.segments[0].paragraphs() == PAGE_LINES
    (beat_a, clip, beat_b) = script.segments[0].directions
    assert (beat_a.text, beat_a.paragraph) == ("at 0:00: open on the tide table", 0)
    assert (clip.text, clip.paragraph) == ("clip: tide-pan.mp4", 1)
    assert (beat_b.text, beat_b.paragraph) == ("at 0:19: the moon phase", 1)


def test_spoken_lines_are_the_text_the_render_hands_vale(tmp_path, monkeypatch):
    """lexical.vale, which a render calls with the script's segments, writes exactly what `narrate spoken` prints."""
    register = write(tmp_path, "narration.ini", "BasedOnStyles = XoxdLexical\n")
    release = SimpleNamespace(dir=tmp_path, vale_register_path=register)
    seen = []

    def fake_run(argv, **_):
        seen.append(Path(argv[-1]).read_text(encoding="utf-8"))
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(lexical.shutil, "which", lambda name: "/fixture/vale")
    monkeypatch.setattr(lexical.subprocess, "run", fake_run)
    inputs = [("Markdown", "17-tides.md", PAGE), ("Srt", "talk.srt", CAPTIONS), ("Dialog", "show.txt", DIALOG)]
    for kind, name, text in inputs:
        script = adapters.load(kind, write(tmp_path, name, text))
        assert lexical.vale(release, script.segments)["status"] == "measured"
        assert seen[-1] + "\n" == spoken.lines(script)
    assert len(seen) == len(inputs)


def test_manuscript_json_carries_the_slide_id_and_no_times(tmp_path, capsys):
    page = write(tmp_path, "17-tides.md", PAGE)
    code, out, _ = run(capsys, page, "--format", "json")
    assert code == 0
    assert json.loads(out) == [{"id": "slide-17", "text": "\n\n".join(PAGE_LINES), "origin": "lines 5-21"}]


def test_srt_needs_cue_times(tmp_path, capsys):
    page = write(tmp_path, "17-tides.md", PAGE)
    code, out, err = run(capsys, page, "--format", "srt")
    assert code == 1 and out == ""
    refusal = json.loads(err)
    assert refusal["refused"] == "input_invalid" and "slide-17" in refusal["detail"]


def test_srt_lines_drop_numbers_timings_and_tags(tmp_path, capsys):
    captions = write(tmp_path, "talk.srt", CAPTIONS)
    code, out, _ = run(capsys, captions)
    assert code == 0
    assert out == "First caption line continues here.\n\nSecond caption.\n\nThird, a minute in.\n"


def test_srt_round_trips_through_the_srt_adapter(tmp_path, capsys):
    captions = write(tmp_path, "talk.srt", CAPTIONS)
    code, out, _ = run(capsys, captions, "--format", "srt")
    assert code == 0
    again = write(tmp_path, "again.srt", out)
    before, after = adapters.load("Srt", captions), adapters.load("Srt", again)
    fields = [(s.id, s.text, s.target_start, s.target_dur) for s in before.segments]
    assert fields == [(s.id, s.text, s.target_start, s.target_dur) for s in after.segments]
    assert "00:01:02,125 --> 00:01:05,000" in out
    assert run(capsys, again, "--format", "srt")[1] == out  # a second pass prints the same cues


def test_json_carries_cue_ids_and_times(tmp_path, capsys):
    captions = write(tmp_path, "talk.srt", CAPTIONS)
    code, out, _ = run(capsys, captions, "--format", "json")
    assert code == 0
    first = {"origin": "line 1"}  # origin points a checker finding back at the input's lines
    assert json.loads(out) == [
        {"id": "cue-0001", "start_s": 1.0, "dur_s": 2.5, "text": "First caption line continues here."} | first,
        {"id": "cue-0002", "start_s": 4.0, "dur_s": 2.25, "text": "Second caption.", "origin": "line 6"},
        {"id": "cue-0003", "start_s": 62.125, "dur_s": 2.875, "text": "Third, a minute in.", "origin": "line 10"},
    ]


def test_vtt_speaker_spans_are_not_spoken(tmp_path, capsys):
    vtt = write(tmp_path, "talk.vtt", "WEBVTT\n\nNOTE not spoken\n\n00:00.500 --> 00:02.000\n<v Host>Hello there.\n")
    code, out, _ = run(capsys, vtt, "--format", "json")
    assert code == 0
    assert json.loads(out) == [
        {"id": "cue-0001", "start_s": 0.5, "dur_s": 1.5, "speaker": "Host", "text": "Hello there.", "origin": "line 5"}
    ]


def test_dialog_lines_drop_speaker_labels(tmp_path, capsys):
    dialog = write(tmp_path, "show.txt", DIALOG)
    code, out, _ = run(capsys, dialog, "--adapter", "Dialog")
    assert code == 0
    assert out.split("\n\n") == [
        "Welcome to the fixture show. It runs on synthetic text only.",
        "Thanks. The demo starts now.",
        "Then let us start.\n",
    ]
    assert "HOST" not in out and "GUEST" not in out


def test_dialog_round_trips_through_the_dialog_adapter(tmp_path, capsys):
    dialog = write(tmp_path, "show.txt", DIALOG)
    code, out, _ = run(capsys, dialog, "--adapter", "Dialog", "--format", "json")
    assert code == 0
    turns = json.loads(out)
    assert [t["id"] for t in turns] == ["turn-0001", "turn-0002", "turn-0003"]
    rebuilt = write(tmp_path, "rebuilt.txt", "\n\n".join(f"{t['speaker']}: {t['text']}" for t in turns) + "\n")
    before, after = adapters.load("Dialog", dialog), adapters.load("Dialog", rebuilt)
    assert [(s.id, s.speaker, s.text) for s in before.segments] == [(s.id, s.speaker, s.text) for s in after.segments]


def test_dialog_is_never_inferred(tmp_path, capsys):
    dialog = write(tmp_path, "show.txt", DIALOG)
    code, out, _ = run(capsys, dialog)
    assert code == 0
    assert out.startswith("HOST: Welcome")  # plain text reads the labels: name the Dialog adapter


def test_kind_follows_the_suffix(tmp_path):
    names = {"a.md": "Markdown", "a.MARKDOWN": "Markdown", "a.srt": "Srt", "a.vtt": "Vtt", "a.json": "CondenseWords"}
    for name, kind in names.items():
        assert spoken.kind_for(tmp_path / name) == kind
    assert spoken.kind_for(tmp_path / "a.txt") == "PlainText"


def test_missing_input_and_unspoken_page_are_refused(tmp_path, capsys):
    code, out, err = run(capsys, tmp_path / "absent.md")
    assert (code, out) == (1, "") and json.loads(err)["refused"] == "input_invalid"
    only_directions = write(tmp_path, "empty.md", "---\nslide: 9\n---\n[at 0:00: silence]\n\nSources: none\n")
    code, out, err = run(capsys, only_directions)
    assert (code, out) == (1, "") and "no narration" in json.loads(err)["detail"]


def test_undecodable_input_is_refused_not_raised(tmp_path, capsys):
    for name, data in (("words.json", b"{not json"), ("page.md", b"\xff\xfe not utf-8")):
        path = tmp_path / name
        path.write_bytes(data)
        code, out, err = run(capsys, path)
        assert (code, out) == (1, "") and json.loads(err)["refused"] == "input_invalid"


def test_lexical_dir_is_the_release_a_render_reads(tmp_path, monkeypatch):
    monkeypatch.delenv("NARRATE_LEXICAL_DIR", raising=False)
    assert spoken.lexical_dir(tmp_path / "absent.toml") is None
    config = write(tmp_path, "narrate.toml", 'lexical = "pins/release"\n')
    assert spoken.lexical_dir(config) == (tmp_path / "pins" / "release").resolve()
    assert spoken.lexical_dir(write(tmp_path, "bare.toml", "")) is None
    monkeypatch.setenv("NARRATE_LEXICAL_DIR", str(tmp_path / "env-release"))
    assert spoken.lexical_dir(config) == (tmp_path / "env-release").resolve()


def test_release_string_reads_the_release_like_the_check_cli(tmp_path, capsys, monkeypatch):
    release = tmp_path / "release-a"  # any name: the recipe links it as dist/ in a XOXD_LEXICAL_HOME
    release.mkdir()
    write(release, "estate-lexicon.json", json.dumps({"version": "0.1.0"}))
    assert spoken.release_string(release) == "xoxd-lexical@0.1.0"
    write(release, "estate-lexicon-full.json", json.dumps({"version": "0.2.0"}))
    assert spoken.release_string(release) == "xoxd-lexical@0.2.0"
    write(release, "DIGESTS", "# fixture\nrelease  xoxd-lexical@0.2.0+sha256:00ff\n")
    assert spoken.release_string(release) == "xoxd-lexical@0.2.0+sha256:00ff"
    monkeypatch.setenv("NARRATE_LEXICAL_DIR", str(release))
    assert spoken.main(["lexical"]) == 0
    assert capsys.readouterr().out == f"{release.resolve()}\nxoxd-lexical@0.2.0+sha256:00ff\n"
    monkeypatch.setenv("NARRATE_LEXICAL_DIR", str(tmp_path / "empty"))
    assert spoken.main(["lexical"]) == 0
    assert capsys.readouterr().out.endswith("empty\n\n")  # no lexicon: the recipe says so and skips the check
    monkeypatch.delenv("NARRATE_LEXICAL_DIR")
    assert spoken.main(["lexical", str(tmp_path / "absent.toml")]) == 3
    assert capsys.readouterr().out == ""
