"""Load talk.toml, name the files the stages share and run the tools."""

import os
import subprocess
import tomllib
from pathlib import Path

RULES = {
    "silence_s": 0.6,  # silencedetect minimum length
    "word_gap_s": 0.7,  # a longer gap between two words is a pause
    "merge_s": 0.3,  # events closer than this become one span
    "margin_s": 0.15,  # kept at speech speed on each side of a span
    "min_event_s": 0.2,  # shorter spans stay speech
    "cut_over_s": 1.0,  # a longer pause is cut
    "keep_head_frames": 5,  # frames kept at 1x before a cut
    "keep_tail_frames": 4,  # frames kept at 1x after a cut
    "xfade_frames": 2,  # audio crossfade over a cut
    "short_pause_speed": 4.0,
    "filler_speed": 8.0,
    "loud_speed": 4.0,  # anything this fast or faster is turned down
    "loud_gain": 0.4,
    "card_gain": 0.15,  # the sound under a card
    "chunk_segs": 220,  # segments per render part
    "overlay_s": 3.0,
    "caption_chars": 42,
    "caption_lines": 2,
}
ENCODE = {
    "width": 1280,
    "height": 720,
    "fps": 30,
    "crf": 35,
    "preset": "slow",
    "audio_bitrate": "64k",
    "denoise": "hqdn3d=2:1.5:4:3",
    "loudness": -16.0,  # LUFS
    "true_peak": -1.5,  # dBTP
    "pre_gain_db": 9.5,  # gain into the limiter, so loudnorm can stay linear
    "limit": 0.32,  # limiter ceiling, -9.9 dBFS
    "jobs": 2,  # part renders and whisper chunks in parallel
}
WHISPER = {
    "model": "models/ggerganov-whisper-cpp-ggml-small.en.bin",
    "dtw": "small.en",
    "language": "en",
    "threads": 4,  # per whisper run
    "chunk_s": 800,
    "pass1": True,
    "prompt": "Um, uh, so, okay, you know, I mean, er, hmm. So, um, let's see.",  # seeds whisper to write fillers
}
CLIP = {
    "speed": 2.0,
    "zones": [],
    "silence_db": -32,
    "voiced_db": -35,
    "evidence": "energy",
    "keep_repeats": ["that", "had", "very", "really", "no", "yeah", "ha"],  # doubled for emphasis, not a restart
    "normalize": False,
    "tonemap": False,
    "detect": "room",  # room | phone (events.detect)
    "pass1_fillers": False,
    "whisper_args": [],
    "card": [],  # text lines: the whole clip plays in card_s seconds, blurred, under them
    "card_s": 20,
}
CHECK = {"silence_db": -35, "silence_s": 1.0, "loudness_lu": 1.0, "sync_ms": 20}
FF = ("ffmpeg", "-hide_banner", "-nostdin", "-y")
# Every tool call is bounded. A long talk's mezzanine or untrunc pass takes minutes, not hours.
TIMEOUT_S = float(os.environ.get("CONDENSE_TOOL_TIMEOUT_S", 7200))


class Config:
    def __init__(self, path):
        raw = tomllib.loads(Path(path).read_text())
        base = Path(path).resolve().parent
        self.work = base / raw.get("work", "work")
        self.out = base / raw.get("out", "out/talk.mp4")
        self.rules = RULES | raw.get("rules", {})
        self.encode = ENCODE | raw.get("encode", {})
        self.whisper = WHISPER | raw.get("whisper", {})
        self.check = CHECK | raw.get("check", {})
        clips = {c["name"]: CLIP | c | {"file": str(base / c["file"])} for c in raw["clip"]}
        self.clips = [clips[name] for name in raw.get("order", clips)]
        self.corrections = raw.get("correction", [])
        self.model = os.environ.get("WHISPER_MODEL") or str(base / self.whisper["model"])
        self.font = raw.get("font") or os.environ.get("TALK_FONT", "")
        self.fps = self.encode["fps"]
        if 48000 % self.fps:
            raise ValueError(f"encode.fps = {self.fps}: a frame must be a whole number of 48 kHz samples")
        self.work.mkdir(parents=True, exist_ok=True)

    def clip(self, name):
        return next(c for c in self.clips if c["name"] == name)

    def f(self, clip, ext):
        """work/<clip>.<ext>"""
        return self.work / f"{clip if isinstance(clip, str) else clip['name']}.{ext}"


def run(*args, cwd=None, timeout=None):
    """Run a tool. Return the finished process, or raise with the end of its stderr or on timeout."""
    timeout = TIMEOUT_S if timeout is None else timeout
    try:
        p = subprocess.run(
            [str(a) for a in args], capture_output=True, text=True, errors="replace", cwd=cwd, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{args[0]} ran over {timeout:g} s (CONDENSE_TOOL_TIMEOUT_S)") from None
    if p.returncode:
        raise RuntimeError(f"{args[0]} failed ({p.returncode}):\n{p.stderr[-2000:]}")
    return p
