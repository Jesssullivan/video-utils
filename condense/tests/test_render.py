"""One real render of the synthetic talk, then the checks, the captions and the overlay pass on it."""

import copy
import json
import subprocess
from pathlib import Path

import pytest

from condense import audio, captions, check, overlay, render
from condense.edl import Timeline


def probe(path, stream, entry):
    cmd = ["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", f"stream={entry}", "-of", "csv=p=0"]
    return subprocess.run([*cmd, path], capture_output=True, text=True, check=True).stdout.strip()


def audio_md5(path):
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-map", "0:a", "-c", "copy", "-f", "md5", "-"]
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def test_the_edit_is_hevc_and_exactly_the_frames_of_its_edl(rendered):
    edl = json.loads(rendered.f("edl", "json").read_text())
    names = [name for name, _, _ in render.parts(edl)]
    assert len(names) > 2 and all(
        rendered.f(name, "mezz.mkv").exists() for name in names
    )  # parallel parts and the card
    frames = sum(s["frames"] for c in edl["clips"] for s in c["segments"])
    assert audio.frames(rendered.out) == frames and edl["expected_total_s"] == pytest.approx(frames / 30, abs=1e-3)
    assert float(probe(rendered.out, "a:0", "duration")) == pytest.approx(frames / 30, abs=0.03)
    assert probe(rendered.out, "v:0", "codec_name,codec_tag_string") == "hevc,hvc1"
    assert probe(rendered.out, "a:0", "codec_name,channels") == "aac,1"


def test_the_silence_gate_passes_the_edit_and_fails_the_source(rendered):
    tl = Timeline.load(rendered)
    assert check.silence(rendered, tl)
    source = copy.copy(rendered)
    source.out = Path(rendered.clips[0]["file"])
    assert not check.silence(source, tl)


def test_loudness_meets_the_target(rendered):
    assert check.loud(rendered, Timeline.load(rendered))


def test_audio_and_video_stay_in_sync(rendered):
    assert check.sync(rendered, Timeline.load(rendered))


def test_corrections_map_through_the_edl(rendered):
    tl = Timeline.load(rendered)
    first, second = overlay.placements(rendered.corrections, tl)
    assert first == (
        pytest.approx(tl.to_out("talk", 12.0), abs=1e-3),
        pytest.approx(first[0] + 3),
        "*the queue holds 64 items",
    )
    join = tl.to_out("talk", 15.0, snap=True)  # 15.0 s is inside a cut
    assert tl.to_out("talk", 15.0) is None and second[0] == pytest.approx(max(join, first[1]), abs=1e-3)
    assert second[1] <= tl.total and second[2] == "*said during a pause that is cut"


def test_overlapping_corrections_queue_up():
    class Flat:
        total = 100.0

        def to_out(self, clip, t, snap=False):
            return None if t < 0 else t / 2

    notes = [dict(clip="a", source_s=s, text="x") for s in (20.0, 22.0, -1.0, 60.0)]
    assert overlay.placements(notes, Flat()) == [(10.0, 13.0, "*x"), (13.0, 16.0, "*x"), (30.0, 33.0, "*x")]


def test_the_overlay_pass_draws_on_the_video_and_copies_the_audio(rendered):
    overlay.burn(rendered)
    out = rendered.out.with_suffix(".corrected.mp4")
    assert audio_md5(out) == audio_md5(rendered.out)
    assert audio.frames(out) == audio.frames(rendered.out)
    start = overlay.placements(rendered.corrections, Timeline.load(rendered))[0][0]

    def corner(path, t):  # mean luma of the top right corner, where the note sits on a dark box
        cut = ["-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-vf", "crop=iw/4:ih/8:iw*3/4-10:10,format=gray"]
        raw = subprocess.run(["ffmpeg", "-v", "error", *cut, "-f", "rawvideo", "-"], capture_output=True, check=True)
        return sum(raw.stdout) / len(raw.stdout)

    assert abs(corner(out, start + 1) - corner(rendered.out, start + 1)) > 10
    assert abs(corner(out, start - 1) - corner(rendered.out, start - 1)) < 3


def test_captions_are_written_beside_the_edit(rendered):
    captions.write(rendered)
    srt = rendered.out.with_suffix(".srt").read_text()
    assert srt.startswith("1\n00:00:00,") and "Hello and welcome everyone." in srt and "um" not in srt.split()
    assert rendered.out.with_suffix(".vtt").read_text().startswith("WEBVTT\n\n00:00:00.")


def packets(path):
    """[(pts, dts, flags)] of the video stream, in file order."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "packet=pts,dts,flags",
        "-of",
        "csv=p=0",
    ]
    out = subprocess.run([*cmd, path], capture_output=True, text=True, check=True).stdout.split()
    return [(int(p), int(d), f) for p, d, f in (line.split(",")[:3] for line in out)]


def assert_upload(path, edit):
    """H.264 with no B-frame, so no packet's pts runs ahead of its dts, from pts 0, a keyframe every 2 s."""
    assert probe(path, "v:0", "codec_name,has_b_frames") == "h264,0"
    found = packets(path)
    assert found[0][0] == 0 and all(p == d for p, d, _ in found)
    assert [i for i, (_, _, f) in enumerate(found) if "K" in f] == list(range(0, len(found), 60))
    assert len(found) == audio.frames(edit) and audio_md5(path) == audio_md5(edit)


def test_the_upload_copy_is_h264_without_b_frames_with_the_edits_frames_and_sound(rendered, monkeypatch, capsys):
    edl = json.loads(rendered.f("edl", "json").read_text())
    out = render.upload(rendered, edl)
    assert out == rendered.out.with_suffix(".upload.mp4")
    assert_upload(out, rendered.out)
    monkeypatch.setattr(render, "parts", lambda edl: [("gone", "talk", [])])  # the parts were cleaned up
    assert_upload(render.upload(rendered, edl, suffix=".from-edit"), rendered.out)
    assert "a second generation of loss" in capsys.readouterr().out


def test_render_writes_the_upload_copy_when_asked_and_only_then(rendered, monkeypatch, capsys):
    # The parts and talk.mp4 are already rendered; stub those steps so only the upload decision runs again.
    monkeypatch.setattr(render, "mezzanine", lambda cfg, clip, total: None)
    monkeypatch.setattr(render, "render_part", lambda cfg, edl, name, *rest: name)
    monkeypatch.setattr(render, "final", lambda cfg, edl: None)
    copy_path = rendered.out.with_suffix(".upload.mp4")
    copy_path.unlink(missing_ok=True)
    render.render(rendered)  # upload unset: no copy
    assert not copy_path.exists()
    cfg = copy.copy(rendered)
    cfg.encode = rendered.encode | {"upload": "h264"}
    render.render(cfg)
    assert_upload(copy_path, rendered.out)
    assert "warning" not in capsys.readouterr().out  # from the lossless parts, not a re-encode of talk.mp4


def test_the_overlay_pass_writes_a_corrected_upload_copy_when_asked(rendered):
    cfg = copy.copy(rendered)
    cfg.encode = rendered.encode | {"upload": "h264"}
    overlay.burn(cfg)
    assert_upload(rendered.out.with_suffix(".corrected.upload.mp4"), rendered.out)
