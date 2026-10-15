"""The sync instrument: every output frame of a coded stand-in, then the delivered file."""

import copy
import json
import re
import subprocess

import numpy as np
import pytest
from conftest import LATE, SHIFT

from condense import audio, avsync, edl
from condense.config import Config
from condense.edl import Timeline


def long_edl(rules, rounds=36, fps=30):
    """Rounds of speech at four speeds, a filler, a short pause and a cut: 151 s of source, 63 s of edit."""
    segs = []

    def add(frames, speed, kind):
        a = segs[-1]["out"] if segs else 0.0
        segs.append(dict(src="long", inp=a, out=round(a + frames / fps, 6), speed=speed, kind=kind, gain=1.0))
        return a, segs[-1]["out"]

    for i in range(rounds):
        add(57, (1.0, 2.0, 2.5, 1.25)[i % 4], "speech")
        add(9, 8.0, "filler")
        add(15, 4.0, "pause")
        a, b = add(45, 1.0, "cut")
        segs[-1]["keep"] = [[a, round(a + 5 / fps, 6)], [round(b - 4 / fps, 6), b]]
    clip = dict(name="long", duration=segs[-1]["out"], shift=SHIFT, segments=edl.quantise(segs, fps))
    return dict(fps=fps, rules=rules, clips=[clip])


def test_the_first_60_s_stay_within_20_ms(tmp_path):
    toml = '[encode]\njobs = 4\n[rules]\nchunk_segs = 40\n[[clip]]\nname = "long"\nfile = "none.mov"\n'
    (tmp_path / "long.toml").write_text(toml)
    cfg = Config(tmp_path / "long.toml")
    built = long_edl(cfg.rules)
    off, good = avsync.probe(cfg, built, built["clips"][0])
    t = np.arange(len(off)) / 30
    assert t[-1] > 60 and good.mean() > 0.9  # four parts, so the part joins are measured too
    assert (~good).sum() == 2 * 36  # only the two crossfade frames of each cut are set aside
    assert np.abs(off[good & (t < 60)]).max() <= 20
    assert np.abs(off[good]).max() <= 20 and abs(np.median(off[good])) <= 1


def test_the_shift_is_the_audio_start_rounded_up_to_frames(talk):
    assert audio.shift(talk.clips[0]["file"], 30) == pytest.approx(SHIFT)
    built = json.loads(talk.f("edl", "json").read_text())
    assert [c["shift"] for c in built["clips"]] == [pytest.approx(SHIFT), 0.0]


def test_the_mezzanine_keeps_the_source_clock(rendered):
    def onset(path):
        return np.argmax(np.abs(avsync.pcm(path, 0, 2 * 48000)) > 0.01) / 48000

    # the analysis wav starts at the first audio sample, the mezzanine at the first video frame
    assert onset(rendered.f("talk", "mezz.mkv")) - onset(rendered.f("talk", "16k.wav")) == pytest.approx(
        LATE, abs=0.002
    )


def test_a_late_soundtrack_is_caught(rendered, capsys):
    """The in-sync file passes in test_render. Here the same file has its sound moved 100 ms late."""
    tl, built = Timeline.load(rendered), json.loads(rendered.f("edl", "json").read_text())
    late = copy.copy(rendered)
    late.out = rendered.out.with_suffix(".late.mp4")
    remux = ["-i", rendered.out, "-itsoffset", "0.1", "-i", rendered.out, "-map", "0:v", "-map", "1:a", "-c", "copy"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", *remux, late.out], check=True)
    assert not avsync.check_real(late, tl, built, 20)
    median = re.search(r"talk median ([-+.\d]+) ms", capsys.readouterr().out)
    assert float(median[1]) == pytest.approx(-100, abs=2)  # the sound plays 100 ms after the picture
