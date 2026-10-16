"""The defaults are bounded, and every tool call has a timeout."""

import sys

import pytest

from condense import config


def test_default_parallelism_is_bounded():
    assert config.ENCODE["jobs"] == 2
    assert config.WHISPER["threads"] == 4


def test_a_tool_that_overruns_its_timeout_raises():
    with pytest.raises(RuntimeError, match="ran over 0.2 s"):
        config.run(sys.executable, "-c", "import time; time.sleep(5)", timeout=0.2)


def test_a_failing_tool_raises_with_its_stderr():
    with pytest.raises(RuntimeError, match="boom"):
        config.run(sys.executable, "-c", "import sys; sys.exit('boom')")


def talk_toml(tmp_path, clip="", encode="", out="out/talk.mp4"):
    """A one-clip talk.toml whose recording exists, for the config checks."""
    (tmp_path / "a.mov").write_bytes(b"")
    path = tmp_path / "talk.toml"
    path.write_text(f'out = "{out}"\n[encode]\n{encode}\n[[clip]]\nname = "a"\nfile = "a.mov"\n{clip}\n')
    return path


def test_drop_spans_are_source_seconds_in_order(tmp_path):
    cfg = config.Config(talk_toml(tmp_path, "drop = [[1.0, 3.0], [5, 9.5]]"))
    assert cfg.clips[0]["drop"] == [[1.0, 3.0], [5, 9.5]]
    assert config.Config(talk_toml(tmp_path)).clips[0]["drop"] == []


@pytest.mark.parametrize(
    ("drop", "message"),
    [
        ("[[1.0, 4.0], [3.0, 6.0]]", "overlaps or precedes"),
        ("[[5.0, 9.0], [1.0, 3.0]]", "overlaps or precedes"),
        ("[[1.0, 3.0], [3.0, 5.0]]", "touches"),
        ("[[3.0, 1.0]]", "0 <= start < end"),
        ("[[-1.0, 2.0]]", "0 <= start < end"),
        ("[[1.0, 2.0, 3.0]]", "must be \\[start, end\\]"),
        ('[["1", "2"]]', "must be \\[start, end\\]"),
        ("[1.0, 2.0]", "must be \\[start, end\\]"),
        ("[[1.0, 1.2]]", "under 10 frames \\(0.333 s\\); a cut keeps 9"),
        ("[[1.0, 1.3]]", "under 10 frames"),
    ],
)
def test_a_bad_drop_span_is_refused(tmp_path, drop, message):
    with pytest.raises(ValueError, match=message):
        config.Config(talk_toml(tmp_path, f"drop = {drop}"))


def test_a_card_clip_takes_no_drop(tmp_path):
    with pytest.raises(ValueError, match="a card clip plays whole"):
        config.Config(talk_toml(tmp_path, 'card = ["lost"]\ndrop = [[1.0, 3.0]]'))


def test_the_preset_and_the_upload_copy_are_checked(tmp_path):
    cfg = config.Config(talk_toml(tmp_path))
    assert (cfg.encode["preset"], cfg.encode["upload"]) == ("slow", "")  # the defaults stay
    cfg = config.Config(talk_toml(tmp_path, encode='preset = "medium"\nupload = "h264"'))
    assert (cfg.encode["preset"], cfg.encode["upload"]) == ("medium", "h264")
    assert cfg.out.with_suffix(".corrected.upload.mp4") in cfg.outputs()
    with pytest.raises(ValueError, match="encode.preset = 'fastest'"):
        config.Config(talk_toml(tmp_path, encode='preset = "fastest"'))
    with pytest.raises(ValueError, match="encode.upload = 'hevc'"):
        config.Config(talk_toml(tmp_path, encode='upload = "hevc"'))
    assert config.Config(talk_toml(tmp_path, encode="upload_crf = 23")).encode["upload_crf"] == 23
    for crf in ("52", "-1", "18.5", '"18"', "true"):
        with pytest.raises(ValueError, match="encode.upload_crf = .*: a whole number from 0 to 51"):
            config.Config(talk_toml(tmp_path, encode=f"upload_crf = {crf}"))


def test_a_drop_of_exactly_one_frame_more_than_a_cut_keeps_is_accepted(tmp_path):
    assert config.Config(talk_toml(tmp_path, "drop = [[3.0, 3.3333334]]")).clips[0]["drop"] == [[3.0, 3.3333334]]


def test_no_output_may_overwrite_a_recording(tmp_path):
    with pytest.raises(ValueError, match="is a clip file"):
        config.Config(talk_toml(tmp_path, out="a.mov"))
    (tmp_path / "a.upload.mp4").write_bytes(b"")
    clip = 'name = "b"\nfile = "a.upload.mp4"'
    config.Config(talk_toml(tmp_path, f"[[clip]]\n{clip}", out="a.mp4"))  # no upload copy, no clash
    with pytest.raises(ValueError, match="a.upload.mp4 is a clip file"):
        config.Config(talk_toml(tmp_path, f"[[clip]]\n{clip}", encode='upload = "h264"', out="a.mp4"))
