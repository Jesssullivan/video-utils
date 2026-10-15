"""A synthetic talk: 24 s of sound on a test pattern. Noisy tone bursts stand for speech. Digital silence sits between.

Its audio stream starts 0.087 s after its video, as one real recording's did. Every time below is counted from
the first audio sample, as the analysis counts. A second clip plays the same file as a card.
No whisper runs here. A fake whisper JSON carries one word per stretch of each burst.
"""

import json
import subprocess

import pytest

from condense import audio, edl, events, render
from condense.config import Config

TOTAL = 24.0
LATE = 0.087  # the audio stream's first sample, on the video's clock
SHIFT = 0.1  # LATE rounded up to whole frames
SPEECH = {  # burst (start, end): the words said in it
    (1.2, 4.0): "Hello and welcome everyone.",
    (6.5, 9.0): "This is the first point.",
    (9.8, 10.3): "um",
    (11.1, 14.0): "The queue is bounded here.",
    (18.6, 22.0): "Thanks for watching this talk.",
}
BURST = (16.0, 16.6)  # sound with no word
SILENCES = [(0.0, 1.2), (4.0, 6.5), (9.0, 9.8), (10.3, 11.1), (14.0, 16.0), (16.6, 18.6), (22.0, 24.0)]

TOML = """
out = "out/talk.mp4"
[encode]
width = 320
height = 180
preset = "ultrafast"
jobs = 4
[rules]
chunk_segs = 6
[[clip]]
name = "talk"
file = "talk.mkv"
welcome = [1.2, 4.0]
speed = 2.0
{extra}
[[clip]]
name = "lost"
file = "talk.mkv"
card = ["This part was lost.", "The disk was full."]
card_s = 2
[[correction]]
clip = "talk"
source_s = 12.0
text = "the queue holds 64 items"
[[correction]]
clip = "talk"
source_s = 15.0
text = "*said during a pause that is cut"
"""


def fake_words():
    """[{start, end, word}]: each burst's words spread evenly over it."""
    out = []
    for (a, b), text in SPEECH.items():
        step = (b - a) / len(text.split())
        out += [dict(start=a + i * step, end=a + (i + 1) * step - 0.1, word=w) for i, w in enumerate(text.split())]
    return out


def fake_whisper(words):
    """whisper.cpp full JSON for the words: one segment per word, offsets in ms, t_dtw in 1/100 s."""
    segs = []
    for w in words:
        off = {"from": round(w["start"] * 1000), "to": round(w["end"] * 1000)}
        token = {"text": " " + w["word"], "offsets": off, "t_dtw": round(w["start"] * 100)}
        segs.append({"text": " " + w["word"], "offsets": off, "tokens": [token]})
    return {"transcription": segs}


@pytest.fixture(scope="session")
def talk(tmp_path_factory):
    """Config for the synthetic talk, with the events and EDL stages already run."""
    base = tmp_path_factory.mktemp("talk")
    gate = "+".join(f"between(t,{a},{b})" for a, b in [*SPEECH, BURST])
    sound = (
        f"sine=f=220:r=48000:d={TOTAL}[s];anoisesrc=c=pink:r=48000:a=0.5:d={TOTAL}:seed=1[n];"
        f"[s][n]amix=inputs=2,volume='if({gate},1,0)':eval=frame"
    )
    ff = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi"]
    subprocess.run([*ff, "-i", sound, base / "late.wav"], check=True)
    picture = ["-i", f"testsrc2=s=320x180:r=30:d={TOTAL + SHIFT}", "-itsoffset", str(LATE), "-i", base / "late.wav"]
    codec = ["-c:v", "libx264", "-preset", "ultrafast", "-c:a", "pcm_s16le"]
    subprocess.run([*ff, *picture, *codec, base / "talk.mkv"], check=True)
    (base / "talk.toml").write_text(TOML.format(extra=""))
    (base / "fast.toml").write_text(TOML.format(extra="speed_max = 2.5\nmax_s = 5"))
    cfg = Config(base / "talk.toml")
    clip = cfg.clips[0]
    audio.extract(cfg, clip)
    cfg.f(clip, "dtw.json").write_text(json.dumps(fake_whisper(fake_words())))
    events.run(cfg, clip)
    edl.build(cfg)
    return cfg


@pytest.fixture(scope="session")
def rendered(talk):
    render.render(talk)
    return talk
