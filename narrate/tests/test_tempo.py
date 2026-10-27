"""A voice's tempo (narrate/tempo.py): audio.time_stretch on synthetic tones, the refusals, and end to end with the
fake engine, where every take is shorter by the voice's factor before QA and the timing fit."""

import array
import json
import math
import wave

import pytest
from conftest import SLIDE
from test_render import SRT_FIT

from narrate import audio, render, tempo, verify
from narrate.config import Config
from narrate.policy import Refused

pytestmark = pytest.mark.usefixtures("ffmpeg")


def tone(path, seconds=2.0, rate=24000, channels=1, hz=220.0):
    frames = round(seconds * rate)
    values = array.array("h", (round(8000 * math.sin(2 * math.pi * hz * n / rate)) for n in range(frames)))
    interleaved = array.array("h", (v for v in values for _ in range(channels)))
    with wave.open(str(path), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(interleaved.tobytes())
    return path


@pytest.mark.parametrize(("rate", "channels"), [(24000, 1), (48000, 2)])
def test_a_two_second_tone_at_1_1_lasts_1_818_s_at_the_same_rate_and_channels(tmp_path, rate, channels):
    source, target = tone(tmp_path / "in.wav", rate=rate, channels=channels), tmp_path / "out.wav"
    seconds = audio.time_stretch(source, target, 1.1)
    assert seconds == pytest.approx(2.0 / 1.1, abs=0.010)
    with wave.open(str(target)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (rate, channels, 2)
        assert w.getnframes() / w.getframerate() == pytest.approx(seconds)


@pytest.mark.parametrize("factor", [1.0, None])
def test_tempo_one_or_none_copies_the_bytes_without_ffmpeg(tmp_path, monkeypatch, factor):
    def no_ffmpeg(*args, **kwargs):
        raise AssertionError("time_stretch called FFmpeg for an identity tempo")

    monkeypatch.setattr(audio, "run", no_ffmpeg)
    source, target = tone(tmp_path / "in.wav"), tmp_path / "out.wav"
    assert audio.time_stretch(source, target, factor) == pytest.approx(2.0)
    assert target.read_bytes() == source.read_bytes()
    pcm = audio.read(source)
    voice = {"id": "voice-fixture-sine", "tempo": factor}
    kept, facts = tempo.apply_tempo(pcm, voice, {"variant": "sine"}, tmp_path)
    assert kept is pcm and facts == {"variant": "sine", "tempo": 1.0, "pre_tempo_seconds": 2.0}


@pytest.mark.parametrize("factor", [0.4, 2.01, -1.0, True, "1.1"])
def test_a_tempo_outside_half_to_double_is_refused(tmp_path, factor):
    source = tone(tmp_path / "in.wav")
    with pytest.raises(ValueError, match="outside 0.5 to 2.0"):
        audio.time_stretch(source, tmp_path / "out.wav", factor)
    assert not (tmp_path / "out.wav").exists()
    with pytest.raises(Refused) as caught:
        tempo.voice_tempo({"id": "voice-x", "tempo": factor})
    assert caught.value.code == "voice_tempo_invalid"


def test_a_voice_tempo_out_of_range_is_refused_before_any_run_exists(workspace):
    workspace.voices[0]["tempo"] = 0.4
    cfg = Config(workspace.write(SLIDE))
    with pytest.raises(Refused) as caught:
        render.render(cfg)
    assert caught.value.code == "voice_tempo_invalid"
    assert workspace.runs() == []


def test_the_manifest_and_edl_record_the_voice_tempo(workspace):
    workspace.voices[0]["tempo"] = 1.1
    cfg = Config(workspace.write(SLIDE))
    final, manifest = render.render(cfg)
    assert verify.verify(final)["ok"]
    assert [v["tempo"] for v in manifest["voices"]] == [1.1]
    edl = json.loads((final / "narration.edl.json").read_text())
    assert [s["voice_tempo"] for s in edl["segments"]] == [1.1]
    for chunk in manifest["chunks"]:
        for take in chunk["qa"]["takes"]:
            assert take["tempo"] == 1.1
            assert take["seconds"] == pytest.approx(take["pre_tempo_seconds"] / 1.1, abs=0.010)
        assert chunk["qa"]["engine_facts"]["tempo"] == 1.1


def test_every_take_is_shorter_by_the_voice_tempo_before_the_fit(workspace):
    workspace.job["captions"] = ["Srt"]
    cfg = Config(workspace.write(SRT_FIT, "Srt"))
    _, plain = render.render(cfg)
    workspace.voices[0]["tempo"] = 1.25
    cfg = Config(workspace.write(SRT_FIT, "Srt"))
    final, fast = render.render(cfg)
    assert verify.verify(final)["ok"]
    assert [c["id"] for c in fast["chunks"]] == [c["id"] for c in plain["chunks"]]
    for a, b in zip(plain["chunks"], fast["chunks"], strict=True):
        assert b["qa"]["takes"][0]["tempo"] == 1.25
        # the kept take, before the fit's atempo: the pre-tempo take matches the plain render's at the same speed
        assert b["seconds"] == pytest.approx(b["qa"]["takes"][0]["pre_tempo_seconds"] / 1.25, abs=0.010)
        if a["qa"]["speed"] == b["qa"]["speed"]:
            assert b["seconds"] == pytest.approx(a["seconds"] / 1.25, abs=0.010)
        on_disk = audio.read(final / b["file"])
        assert on_disk.rate == 24000 and on_disk.seconds == pytest.approx(b["seconds"], abs=1e-3)
    edl = json.loads((final / "narration.edl.json").read_text())
    plain_edl = {
        s["id"]: s for s in json.loads((final.parent / plain["run_id"] / "narration.edl.json").read_text())["segments"]
    }
    for segment in edl["segments"]:
        assert segment["voice_tempo"] == 1.25 and plain_edl[segment["id"]]["voice_tempo"] == 1.0
        # the fit still runs on the faster take and stays within fitMaxStretch
        assert 1.0 <= segment["atempo"] <= 1.08 + 1e-6
    long = next(s for s in edl["segments"] if s["id"] == "cue-0002")
    assert long["natural_s"] < plain_edl["cue-0002"]["natural_s"]


def test_wer_hears_the_take_at_the_voice_tempo(workspace):
    """The transcriber gets the faster take: QA scores what the voice speaks, not the engine's reply."""
    workspace.voices[0]["tempo"] = 1.25
    heard = []

    def transcriber(pcm, text):
        heard.append(pcm.seconds)
        return text

    _, manifest = render.render(Config(workspace.write(SLIDE)), transcriber=transcriber)
    takes = [take for chunk in manifest["chunks"] for take in chunk["qa"]["takes"]]
    assert len(heard) == len(takes) > 0
    for seconds, take in zip(heard, takes, strict=True):
        assert take["tempo"] == 1.25
        assert seconds == pytest.approx(take["pre_tempo_seconds"] / 1.25, abs=0.010)
        assert seconds < take["pre_tempo_seconds"]
