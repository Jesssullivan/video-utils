import json
from types import SimpleNamespace

import pytest

from condense import audio, edl
from condense.config import Config
from condense.edl import Timeline


@pytest.fixture(scope="module")
def built(talk):
    return json.loads(talk.f("edl", "json").read_text())


def at(built, t):
    return next(s for s in built["clips"][0]["segments"] if s["inp"] <= t < s["out"])


def test_segments_cover_the_clip_without_gaps(built):
    segs = built["clips"][0]["segments"]
    assert segs[0]["inp"] == 0 and segs[-1]["out"] == 24.0
    assert all(a["out"] == b["inp"] for a, b in zip(segs, segs[1:], strict=False))


def test_each_kind_gets_its_speed(built):
    assert (at(built, 2.0)["kind"], at(built, 2.0)["speed"]) == ("speech", 1.0)  # the welcome
    assert (at(built, 7.0)["kind"], at(built, 7.0)["speed"]) == ("speech", 2.0)
    assert (at(built, 9.4)["kind"], at(built, 9.4)["speed"]) == ("pause", 4.0)  # 0.8 s of silence
    assert (at(built, 10.0)["kind"], at(built, 10.0)["speed"]) == ("filler", 8.0)  # the um
    assert (at(built, 16.3)["kind"], at(built, 16.3)["speed"]) == ("filler", 8.0)  # the unworded burst
    assert at(built, 9.4)["gain"] == 0.4 and at(built, 7.0)["gain"] == 1.0


def test_a_long_pause_is_cut_to_nine_frames(built):
    cut = at(built, 5.0)  # the 2.5 s silence from 4.0 s
    assert cut["kind"] == "cut" and cut["out_dur"] == pytest.approx(0.3)
    (a0, a1), (b0, b1) = cut["keep"]
    assert a1 - a0 == pytest.approx(5 / 30, abs=1e-5) and b1 - b0 == pytest.approx(4 / 30, abs=1e-5)
    assert 4.0 < a1 < b0 < 6.5  # only silence is dropped


def test_no_cut_drops_a_sound(talk, built):
    rms = audio.read_rms(talk.f("talk", "rms.txt"))
    for s in built["clips"][0]["segments"]:
        if s["kind"] == "cut":
            dropped = range(round(s["keep"][0][1] * 10) + 1, int(s["keep"][1][0] * 10))
            assert all(rms[f] < -60 for f in dropped)


def test_the_time_map_is_monotonic_and_applies_the_speeds(built):
    tl = Timeline(built)
    outs = [tl.to_out("talk", i / 100) for i in range(2400)]
    kept = [t for t in outs if t is not None]
    assert kept == sorted(kept) and kept[0] == 0 and kept[-1] < tl.total
    assert tl.total == pytest.approx(built["expected_total_s"], abs=1e-3)
    assert tl.to_out("talk", 3.0) - tl.to_out("talk", 2.0) == pytest.approx(1.0)  # welcome, 1x
    # a sped segment lasts a whole number of frames, so its real speed sits within a frame of the rule
    assert tl.to_out("talk", 8.0) - tl.to_out("talk", 7.0) == pytest.approx(0.5, abs=0.02)  # speech, 2x
    um = at(built, 10.0)  # filler, 8x
    assert um["out_dur"] == pytest.approx((um["out"] - um["inp"]) / 8, abs=1 / 30)
    assert tl.to_out("talk", um["out"]) - tl.to_out("talk", um["inp"]) == pytest.approx(um["out_dur"])


def test_dropped_time_maps_to_nothing_or_snaps_to_the_join(built):
    tl = Timeline(built)
    cut = at(built, 5.0)
    assert tl.to_out("talk", 5.0) is None
    assert tl.to_out("talk", 5.0, snap=True) == pytest.approx(tl.to_out("talk", cut["keep"][1][0]))
    assert tl.to_out("talk", 24.0) is None


def test_output_times_map_back_to_their_source(built):
    tl = Timeline(built)
    for t in (2.0, 7.3, 9.4, 10.0, 12.5, 20.0):
        src, seg = tl.to_src(tl.to_out("talk", t))
        assert src == pytest.approx(t) and seg is at(built, t)
    assert tl.to_src(tl.total) is None


def test_every_segment_is_whole_frames_and_the_rounding_never_builds_up(built):
    ideal = done = 0.0
    for s in built["clips"][0]["segments"]:
        assert s["frames"] >= 1 and s["out_dur"] == pytest.approx(s["frames"] / 30, abs=1e-5)
        ideal, done = ideal + edl.seg_dur(s) * 30, done + s["frames"]
        assert abs(done - ideal) <= 0.5 + 1e-6


def test_a_segment_too_short_for_a_frame_joins_a_neighbour():
    def seg(inp, out, speed, kind):
        return dict(src="x", inp=inp, out=out, speed=speed, kind=kind)

    cut = seg(2.1, 4.0, 1.0, "cut") | dict(keep=[[2.1, 2.2], [3.9, 4.0]])
    blip = seg(2.0, 2.1, 8.0, "filler")  # 3 source frames at 8x: under half a frame
    segs = edl.quantise([seg(0.0, 2.0, 2.0, "speech"), blip, cut, seg(4.0, 6.0, 2.0, "speech")], 30)
    assert [(s["kind"], s["inp"], s["out"], s["frames"]) for s in segs] == [
        ("speech", 0.0, 2.1, 31),  # the blip plays as speech
        ("cut", 2.1, 4.0, 6),
        ("speech", 4.0, 6.0, 30),
    ]
    lone = edl.quantise([cut | dict(inp=0.0, out=1.9), dict(blip, inp=1.9, out=2.0), dict(cut)], 30)
    assert [s["frames"] for s in lone] == [6, 1, 6]  # between two cuts it keeps one frame


def test_a_card_is_one_segment_of_the_whole_clip(talk):
    card = json.loads(talk.f("edl", "json").read_text())["clips"][1]["segments"]
    assert len(card) == 1 and card[0]["kind"] == "card" and card[0]["frames"] == 60
    assert card[0]["speed"] == pytest.approx(12.0, rel=0.01) and card[0]["gain"] == 0.15


def test_speech_speeds_up_to_the_cap_when_the_clip_runs_over(talk):
    fast = Config(talk.work.parent / "fast.toml")
    segs, info = edl.build_clip(fast, fast.clips[0])
    assert info["speed"] == 2.5
    assert {s["speed"] for s in segs if s["kind"] == "speech"} == {1.0, 2.5}  # the welcome stays at 1x


def test_whisper_tags_are_no_proof_of_speech_and_a_hum_is():
    c = SimpleNamespace(asr={"1.000-2.000": "[BLANK_AUDIO]", "3.000-4.000": "Mmm.", "5.000-6.000": " um (coughs)"})
    assert [edl.heard(c, a, a + 1) for a in (1.0, 3.0, 5.0)] == [False, True, False]
