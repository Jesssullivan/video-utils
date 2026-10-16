import json
from types import SimpleNamespace

import pytest

from condense import audio, captions, edl
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


def test_a_drop_joins_the_cut_it_starts_in_and_trims_the_speech_it_ends_in():
    c = SimpleNamespace(
        name="x", fps=30, r=dict(keep_head_frames=5, keep_tail_frames=4), snap=lambda t: round(round(t * 30) / 30, 6)
    )

    def seg(inp, out, speed, kind, **extra):
        return dict(src="x", inp=inp, out=out, speed=speed, kind=kind, **extra)

    segs = [
        seg(0.0, 2.0, 2.0, "speech"),
        seg(2.0, 4.0, 1.0, "cut", keep=[[2.0, 2.166667], [3.866667, 4.0]]),
        seg(4.0, 6.0, 2.0, "speech"),
        seg(6.0, 6.5, 8.0, "filler"),
        seg(6.5, 10.0, 2.0, "speech"),
    ]
    out = edl.drop(c, segs, [[3.0, 7.0]])
    assert [(s["inp"], s["out"], s["kind"]) for s in out] == [
        (0.0, 2.0, "speech"),
        (2.0, 7.0, "cut"),
        (7.0, 10.0, "speech"),
    ]
    assert out[1]["keep"] == [[2.0, 2.166667], [6.866667, 7.0]]  # the cut's own head stays, 4 frames before 7 s
    both = edl.drop(c, segs, [[0.5, 1.5], [8.0, 9.0]])
    assert [(s["inp"], s["out"], s["kind"]) for s in both] == [
        (0.0, 0.5, "speech"),
        (0.5, 1.5, "cut"),
        (1.5, 2.0, "speech"),
        *[(s["inp"], s["out"], s["kind"]) for s in segs[1:4]],
        (6.5, 8.0, "speech"),
        (8.0, 9.0, "cut"),
        (9.0, 10.0, "speech"),
    ]
    assert edl.drop(c, segs, []) == segs


@pytest.fixture(scope="module")
def dropped(talk):
    """The synthetic talk with 6.5-14.0 s dropped: the first point, the um and the queue sentence."""
    text = (
        (talk.work.parent / "talk.toml").read_text().replace("speed = 2.0\n", "speed = 2.0\ndrop = [[6.5, 14.0]]\n", 1)
    )
    (talk.work.parent / "drop.toml").write_text(text)
    cfg = Config(talk.work.parent / "drop.toml")
    segs, info = edl.build_clip(cfg, cfg.clips[0])
    return cfg, dict(fps=30, rules=cfg.rules, clips=[dict(name="talk", shift=info["shift"], segments=segs)])


def test_a_drop_span_is_one_cut_and_its_words_leave_the_captions(talk, built, dropped):
    cfg, plan = dropped
    segs = plan["clips"][0]["segments"]
    assert all(a["out"] == b["inp"] for a, b in zip(segs, segs[1:], strict=False))
    cut = next(s for s in segs if s["inp"] <= 6.5 and s["out"] >= 14.0)
    assert cut["kind"] == "cut" and cut["frames"] == 9
    (a0, a1), (b0, b1) = cut["keep"]
    assert (a0, b1) == (cut["inp"], cut["out"]) and round((a1 - a0) * 30) == 5 and round((b1 - b0) * 30) == 4
    tl = Timeline(plan)
    assert all(tl.to_out("talk", t) is None for t in (7.0, 10.0, 12.5))
    full = sum(s["frames"] for s in built["clips"][0]["segments"])
    assert sum(s["frames"] for s in segs) < full - 3 * 30  # 7.5 s of source, about 4 s of output, is gone
    said = [w for _, _, w in captions.output_words(cfg, tl)]
    assert "Hello" in said and "watching" in said and not {"first", "queue", "um"} & set(said)


def test_a_drop_past_the_end_of_the_clip_is_refused(talk):
    text = (
        (talk.work.parent / "talk.toml").read_text().replace("speed = 2.0\n", "speed = 2.0\ndrop = [[20.0, 30.0]]\n", 1)
    )
    (talk.work.parent / "late.toml").write_text(text)
    cfg = Config(talk.work.parent / "late.toml")
    with pytest.raises(ValueError, match="ends after the clip's 24.000 s"):
        edl.build_clip(cfg, cfg.clips[0])


def test_a_drop_that_ends_inside_a_pause_cut_ends_where_that_cut_ends():
    # A drop's end edge at 141.067 s fell inside a pause cut that ran on to 141.233 s: the drop takes the
    # whole cut and keeps 4 frames before the cut's end, not before 141.067 s.
    c = SimpleNamespace(
        name="x", fps=30, r=dict(keep_head_frames=5, keep_tail_frames=4), snap=lambda t: round(round(t * 30) / 30, 6)
    )
    segs = [
        dict(src="x", inp=0.0, out=2.0, speed=2.0, kind="speech"),
        dict(src="x", inp=2.0, out=4.0, speed=2.0, kind="speech"),
        dict(src="x", inp=4.0, out=6.0, speed=1.0, kind="cut", keep=[[4.0, 4.4], [5.866667, 6.0]]),
        dict(src="x", inp=6.0, out=8.0, speed=2.0, kind="speech"),
    ]
    out = edl.drop(c, segs, [[1.0, 5.0]])
    assert [(s["inp"], s["out"], s["kind"]) for s in out] == [
        (0.0, 1.0, "speech"),
        (1.0, 6.0, "cut"),
        (6.0, 8.0, "speech"),
    ]
    # 5 head frames from the drop's start, 4 tail frames before the pause cut's own end
    assert out[1]["keep"] == [[1.0, 1.166667], [5.866667, 6.0]]


def test_two_drops_that_meet_once_an_edge_moves_become_one_cut():
    # Each span is valid on its own and they are apart, but the first one's end moves out to 6.0 s, past the
    # start of the second, so the second starts inside the first's cut and the two become one cut.
    c = SimpleNamespace(
        name="x", fps=30, r=dict(keep_head_frames=5, keep_tail_frames=4), snap=lambda t: round(round(t * 30) / 30, 6)
    )
    segs = [
        dict(src="x", inp=0.0, out=4.0, speed=2.0, kind="speech"),
        dict(src="x", inp=4.0, out=6.0, speed=1.0, kind="cut", keep=[[4.0, 4.166667], [5.866667, 6.0]]),
        dict(src="x", inp=6.0, out=10.0, speed=2.0, kind="speech"),
    ]
    out = edl.drop(c, segs, [[1.0, 5.0], [5.5, 8.0]])
    assert [(s["inp"], s["out"], s["kind"]) for s in out] == [
        (0.0, 1.0, "speech"),
        (1.0, 8.0, "cut"),
        (8.0, 10.0, "speech"),
    ]
    assert out[1]["keep"] == [[1.0, 1.166667], [7.866667, 8.0]]


def test_a_drop_that_starts_or_ends_on_a_pause_cut_edge_joins_it():
    # A drop that meets a pause cut exactly at the cut's end (or start) would otherwise leave two cuts back to
    # back, each keeping its own head and tail frames, so 18 frames instead of 9 played at the seam.
    c = SimpleNamespace(
        name="x", fps=30, r=dict(keep_head_frames=5, keep_tail_frames=4), snap=lambda t: round(round(t * 30) / 30, 6)
    )
    segs = [
        dict(src="x", inp=0.0, out=2.0, speed=2.0, kind="speech"),
        dict(src="x", inp=2.0, out=4.0, speed=1.0, kind="cut", keep=[[2.0, 2.166667], [3.866667, 4.0]]),
        dict(src="x", inp=4.0, out=8.0, speed=2.0, kind="speech"),
        dict(src="x", inp=8.0, out=9.0, speed=1.0, kind="cut", keep=[[8.0, 8.166667], [8.866667, 9.0]]),
        dict(src="x", inp=9.0, out=10.0, speed=2.0, kind="speech"),
    ]
    out = edl.drop(c, segs, [[4.0, 6.0]])
    assert [(s["inp"], s["out"], s["kind"]) for s in out] == [
        (0.0, 2.0, "speech"),
        (2.0, 6.0, "cut"),
        (6.0, 8.0, "speech"),
        *[(s["inp"], s["out"], s["kind"]) for s in segs[3:]],
    ]
    out = edl.drop(c, segs, [[6.0, 8.0]])
    assert [(s["inp"], s["out"], s["kind"]) for s in out][2:4] == [(4.0, 6.0, "speech"), (6.0, 9.0, "cut")]
    assert out[3]["keep"] == [[6.0, 6.166667], [8.866667, 9.0]]


def test_whisper_never_reads_a_pause_span_inside_a_drop(talk, monkeypatch):
    """evidence = "asr" re-reads a pause span with a sound in it, unless a drop removes the span anyway."""
    base = talk.work.parent
    work = base / "asr-work"
    work.mkdir(exist_ok=True)
    for ext in ("16k.wav", "words.json", "rms.txt"):
        (work / f"talk.{ext}").write_bytes(talk.f("talk", ext).read_bytes())
    ev = json.loads(talk.f("talk", "events.json").read_text())
    ev["fillers"] = [f for f in ev["fillers"] if not 14.0 <= f[0] < 18.6]  # the burst now sits in a pause
    ev["pauses"] = [p for p in ev["pauses"] if not 14.0 <= p[0] < 18.6] + [[14.0, 18.6]]
    (work / "talk.events.json").write_text(json.dumps(ev))
    calls = []
    monkeypatch.setattr(edl.transcribe, "read", lambda cfg, wav, a, b: calls.append((a, b)) or "")

    def build(extra):
        text = (base / "talk.toml").read_text().replace("speed = 2.0\n", f'speed = 2.0\nevidence = "asr"\n{extra}', 1)
        (base / "asr.toml").write_text(f'work = "asr-work"\n{text}')
        (work / "talk.pause_asr.json").unlink(missing_ok=True)
        cfg = Config(base / "asr.toml")
        return edl.build_clip(cfg, cfg.clips[0])[0]

    build("")
    assert calls and all(14.0 <= a < b <= 18.6 for a, b in calls)  # the control: the burst's span is read
    calls.clear()
    segs = build("drop = [[13.5, 18.6]]\n")
    assert calls == []
    assert any(s["kind"] == "cut" and s["inp"] <= 13.5 and s["out"] >= 18.6 for s in segs)
