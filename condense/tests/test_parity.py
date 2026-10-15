"""The old/new parity receipt: per-file verdicts, media frame counts, staged configs and no private strings.

Two fake tool roots stand in for the retired talk_condense and this repository's condense. FFmpeg makes the
media. No whisper runs here.
"""

import json
import subprocess
import textwrap

import pytest

from condense.tools import parity

FAKE_MAIN = """
import json, os, sys, tomllib
from pathlib import Path
stage, config = sys.argv[1], Path(sys.argv[2])
raw = tomllib.loads(config.read_text())
work = config.parent / raw.get("work", "work")
work.mkdir(parents=True, exist_ok=True)
if stage == os.environ.get("FAKE_FAIL_STAGE"):
    sys.exit(3)
words = [{{"start": 0.5, "end": 0.9, "word": "hello"}}, {{"start": 1.0, "end": 1.4, "word": "{last}"}}]
size = Path(config.parent / raw["clip"][0]["file"]).stat().st_size
if stage != "publish":  # the real publish writes under artifacts/, not work/
    (work / f"talk.{{stage}}.json").write_text(json.dumps({{"stage": stage, "source_bytes": size, "words": words}}))
if stage == "edl":
    (work / "edl.json").write_text(json.dumps({{"clips": [{{"segments": [1, 2, 3]}}], "expected_total_s": 1.5}}))
"""


def fake_root(base, package, last="world", stages=("transcribe", "events", "edl")):
    pkg = base / package
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "__main__.py").write_text(FAKE_MAIN.format(last=last))
    for stage in stages:
        (pkg / f"{stage}.py").write_text("")
    return base


def media(path, frames, rate=30):
    args = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=64x36:r={rate}:d={frames / rate}"]
    args += ["-f", "lavfi", "-i", f"sine=f=440:r=48000:d={frames / rate}", "-c:v", "libx264", "-preset"]
    subprocess.run([*args, "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path], check=True)
    return path


@pytest.fixture
def talk(tmp_path):
    base = tmp_path / "talk"
    (base / "media").mkdir(parents=True)
    media(base / "media" / "intro.mp4", 15)
    toml = base / "talk.toml"
    toml.write_text(
        textwrap.dedent("""
        work = "work"
        out = "out/talk.mp4"
        [[clip]]
        name = "intro"
        file = "media/intro.mp4"
        """)
    )
    return toml


def side(tmp_path, name, files):
    d = tmp_path / name
    (d / "work").mkdir(parents=True)
    (d / "out").mkdir()
    (d / "talk.toml").write_text('work = "work"\nout = "out/talk.mp4"\n[[clip]]\nname = "a"\nfile = "a.mov"\n')
    for rel, content in files.items():
        if isinstance(content, int):
            media(d / rel, content)
        else:
            (d / rel).write_text(content)
    return d


def test_identical_sides_match_by_hash_and_frames(tmp_path):
    files = {"work/a.words.json": "[1, 2, 3]", "work/edl.json": '{"clips": []}', "out/talk.mp4": 12}
    old, new = side(tmp_path, "old", files), side(tmp_path, "new", files)
    # Encoders can differ run to run; copy the media so the two sides hold the same bytes.
    (new / "out/talk.mp4").write_bytes((old / "out/talk.mp4").read_bytes())
    c = parity.compare(old, new)
    assert c["identical"] and c["counts"] == {"match": 3}
    row = c["files"]["out/talk.mp4"]
    assert row["old"]["video_frames"] == 12 and row["frames_and_duration"] == "match"
    assert c["files"]["work/a.words.json"]["old"]["shape"] == {"items": 3}


def test_a_changed_word_list_differs_and_names_its_first_index(tmp_path):
    old = side(tmp_path, "old", {"work/a.words.json": json.dumps([{"w": "a"}, {"w": "b"}, {"w": "c"}])})
    new = side(tmp_path, "new", {"work/a.words.json": json.dumps([{"w": "a"}, {"w": "zebra"}, {"w": "c"}])})
    c = parity.compare(old, new)
    row = c["files"]["work/a.words.json"]
    assert not c["identical"] and row["verdict"] == "differ"
    assert row["first_diff"] == {"index": 1}
    assert "zebra" not in json.dumps(c), "the receipt carries counts, not transcript text"


def test_an_edl_difference_names_its_key_and_segment_counts(tmp_path):
    a = {"clips": [{"segments": [1, 2]}], "expected_total_s": 2.0}
    b = {"clips": [{"segments": [1, 2, 3]}], "expected_total_s": 2.5}
    old = side(tmp_path, "old", {"work/edl.json": json.dumps(a)})
    new = side(tmp_path, "new", {"work/edl.json": json.dumps(b)})
    row = parity.compare(old, new)["files"]["work/edl.json"]
    assert row["first_diff"] == {"key": "clips", "index": 0}
    assert (row["old"]["shape"]["segments"], row["new"]["shape"]["segments"]) == ([2], [3])
    assert (row["old"]["shape"]["expected_total_s"], row["new"]["shape"]["expected_total_s"]) == (2.0, 2.5)


def test_a_frame_count_difference_is_reported(tmp_path):
    old, new = side(tmp_path, "old", {"out/talk.mp4": 10}), side(tmp_path, "new", {"out/talk.mp4": 11})
    row = parity.compare(old, new)["files"]["out/talk.mp4"]
    assert row["verdict"] == "differ" and row["frames_and_duration"] == "differ"
    assert (row["old"]["video_frames"], row["new"]["video_frames"]) == (10, 11)


def test_a_truncated_render_is_recorded_not_raised(tmp_path):
    old, new = side(tmp_path, "old", {"out/talk.mp4": 30}), side(tmp_path, "new", {"out/talk.mp4": 30})
    full = (old / "out/talk.mp4").read_bytes()
    (new / "out/talk.mp4").write_bytes(full[: len(full) // 2])  # a render that died partway
    c = parity.compare(old, new)
    row = c["files"]["out/talk.mp4"]
    assert row["verdict"] == "differ" and row["frames_and_duration"] == "probe_failed" and not c["identical"]
    assert row["old"]["video_frames"] == 30 and row["new"]["probe"] == "failed"


def test_equal_unreadable_media_is_not_parity(tmp_path):
    old, new = side(tmp_path, "old", {"out/talk.mp4": "not a video"}), side(tmp_path, "new", {})
    (new / "out/talk.mp4").write_bytes((old / "out/talk.mp4").read_bytes())
    (new / "out/extra.mov").write_text("")
    c = parity.compare(old, new)
    assert c["files"]["out/talk.mp4"]["verdict"] == "differ" and not c["identical"]
    extra = c["files"]["out/extra.mov"]
    assert extra["verdict"] == "only_new" and extra["new"]["probe"] == "failed"


def test_a_file_on_one_side_only_is_not_a_match(tmp_path):
    old = side(tmp_path, "old", {"work/a.events.json": "{}", "work/a.pause_asr.json": "{}"})
    new = side(tmp_path, "new", {"work/a.events.json": "{}", "out/talk.srt": "1\n"})
    c = parity.compare(old, new)
    assert c["counts"] == {"match": 1, "only_old": 1, "only_new": 1} and not c["identical"]


def test_no_files_is_not_parity(tmp_path):
    assert not parity.compare(side(tmp_path, "old", {}), side(tmp_path, "new", {}))["identical"]


def test_the_staged_config_links_the_same_recording(talk, tmp_path):
    staged = parity.stage_config(talk, tmp_path / "run" / "old")
    assert staged.read_text() == talk.read_text()
    link = staged.parent / "media" / "intro.mp4"
    assert not link.is_symlink() and link.samefile(talk.parent / "media" / "intro.mp4")
    parity.stage_config(talk, tmp_path / "run" / "old")  # staging twice replaces the link


@pytest.mark.parametrize("line", ['work = "/abs/work"', 'work = "../shared"'])
def test_a_shared_work_dir_is_refused(talk, tmp_path, line):
    talk.write_text(line + "\n" + talk.read_text().replace('work = "work"\n', ""))
    with pytest.raises(ValueError, match="relative path"):
        parity.stage_config(talk, tmp_path / "run" / "old")


def test_both_pipelines_run_and_agree(talk, tmp_path):
    old = fake_root(tmp_path / "old_root", "talk_condense")
    new = fake_root(tmp_path / "new_root", "condense", stages=("transcribe", "events", "edl", "publish"))
    run = tmp_path / "run"
    code = parity.main([str(old), str(new), str(talk), str(run), "--stages", "transcribe,events,edl,publish"])
    receipt = json.loads((run / "parity.json").read_text())
    assert code == 0 and receipt["comparison"]["identical"]
    assert receipt["comparison"]["counts"] == {"match": 4}
    assert [s["status"] for s in receipt["runs"]["old"]] == ["ok", "ok", "ok", "unsupported"]
    assert [s["status"] for s in receipt["runs"]["new"]] == ["ok"] * 4
    assert receipt["versions"]["old_package"] == "talk_condense" and receipt["versions"]["new_package"] == "condense"
    assert set(receipt["sources_sha256"]) == {"intro"}
    assert str(tmp_path) not in (run / "parity.json").read_text()


def test_a_mismatch_exits_1_and_a_failed_stage_stops_its_side(talk, tmp_path, monkeypatch):
    old = fake_root(tmp_path / "old_root", "talk_condense")
    new = fake_root(tmp_path / "new_root", "condense", last="word")
    run = tmp_path / "run"
    assert parity.main([str(old), str(new), str(talk), str(run)]) == 1
    receipt = json.loads((run / "parity.json").read_text())
    assert receipt["comparison"]["files"]["work/talk.transcribe.json"]["first_diff"] == {"key": "words", "index": 1}
    assert receipt["comparison"]["files"]["work/edl.json"]["verdict"] == "match"
    monkeypatch.setenv("FAKE_FAIL_STAGE", "events")
    assert parity.main([str(old), str(old), str(talk), str(tmp_path / "run2"), "--sides", "new"]) == 1
    runs = json.loads((tmp_path / "run2" / "parity.json").read_text())["runs"]
    assert list(runs) == ["new"] and [s["status"] for s in runs["new"]] == ["ok", "failed"]


def test_a_receipt_with_a_private_string_is_refused():
    with pytest.raises(ValueError, match="private"):
        parity.scrub({"note": "under /private/dir"}, "/private/dir")
    assert parity.scrub({"sha256": "ab"}, "/private/dir", "") == {"sha256": "ab"}
