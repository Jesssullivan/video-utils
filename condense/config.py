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
    "preset": "slow",  # x265 preset of talk.mp4 and x264 preset of the upload copy (PRESETS)
    "audio_bitrate": "64k",
    "denoise": "hqdn3d=2:1.5:4:3",
    "loudness": -16.0,  # LUFS
    "true_peak": -1.5,  # dBTP
    "pre_gain_db": 9.5,  # gain into the limiter, so loudnorm can stay linear
    "limit": 0.32,  # limiter ceiling, -9.9 dBFS
    "jobs": 2,  # part renders and whisper chunks in parallel
    "upload": "",  # "h264": also write <out>.upload.mp4 for a video site (render.upload)
    "upload_crf": 18,  # x264 CRF of the upload copy: near-transparent, the site re-encodes it
}
PRESETS = ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow", "placebo")
UPLOADS = ("", "h264")
WHISPER = {
    "model": "models/ggerganov-whisper-cpp-ggml-small.en.bin",
    "dtw": "small.en",
    "language": "en",
    "threads": 4,  # per whisper run
    "chunk_s": 800,
    "pass1": True,
    "prompt": "Um, uh, so, okay, you know, I mean, er, hmm. So, um, let's see.",  # seeds whisper to write fillers
    "backend": "cli",  # cli: whisper-cli and the model; http: a loopback STT service (docs/spec/CONDENSE.md)
    "url": "",  # http backend only; its bearer token comes from CONDENSE_STT_TOKEN, never from a file
    "http_timeout_s": 3600,  # http backend: the longest wait on the service in one request
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
    "drop": [],  # [[start, end]] source seconds cut like a long pause, before the speed rules (edl.drop)
}
CAPTIONS = {  # [captions]: how words become cues (captions.py). The defaults are the original style.
    "words": "spoken",  # spoken | start: which words are captioned and on which times (captions.output_words)
    "fillers": False,  # true: caption filler words that play at speech speed, as words
    "fill": "wrap",  # wrap: a cue is full past caption_lines wrapped lines; chars: past lines x chars characters
    "split": "greedy",  # greedy: textwrap; balanced: two lines broken near the middle
    "gap_s": 1.0,  # a longer silence between two words starts a new cue
    "max_s": 0.0,  # a cue never spans more than this from its first word's start to its last's end; 0: no limit
    # "sentence_chars": a sentence end closes a cue that holds at least this many characters; caption_chars // 2
    "min_s": 1.0,  # a cue shows at least this long, never into the next one
    "clear_s": 0.0,  # a cue cut short by the next one ends this long before it
    "squeeze_s": 0.0,  # a cue the next would cut to this or less holds min_s and pushes the next; 0: always cut
    "cards": {},  # card clip name -> caption lines shown over the card
    "card_inset_s": 0.5,  # a card caption starts this long after the card and ends this long before its end
}
CAPTION_CHOICES = {"words": ("spoken", "start"), "fill": ("wrap", "chars"), "split": ("greedy", "balanced")}
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
        self.captions = CAPTIONS | raw.get("captions", {})
        self.captions.setdefault("sentence_chars", self.rules["caption_chars"] // 2)
        clips = {c["name"]: CLIP | c | {"file": str(base / c["file"])} for c in raw["clip"]}
        self.clips = [clips[name] for name in raw.get("order", clips)]
        self.corrections = raw.get("correction", [])
        self.model = os.environ.get("WHISPER_MODEL") or str(base / self.whisper["model"])
        self.font = raw.get("font") or os.environ.get("TALK_FONT", "")
        self.fps = self.encode["fps"]
        if 48000 % self.fps:
            raise ValueError(f"encode.fps = {self.fps}: a frame must be a whole number of 48 kHz samples")
        if self.encode["preset"] not in PRESETS:
            raise ValueError(f"encode.preset = {self.encode['preset']!r}: one of {', '.join(PRESETS)}")
        if self.encode["upload"] not in UPLOADS:
            raise ValueError(f'encode.upload = {self.encode["upload"]!r}: "h264", or leave it out')
        crf = self.encode["upload_crf"]
        if type(crf) is not int or not 0 <= crf <= 51:
            raise ValueError(f"encode.upload_crf = {crf!r}: a whole number from 0 to 51 (x264's 8-bit range)")
        check_captions(self.captions, self.clips, self.rules)
        for clip in self.clips:
            check_drops(clip, self.rules["keep_head_frames"] + self.rules["keep_tail_frames"], self.fps)
        for path in self.outputs():
            if any(path.resolve() == Path(c["file"]).resolve() for c in self.clips):
                raise ValueError(f"{path} is a clip file: an output may never overwrite a recording")
        self.work.mkdir(parents=True, exist_ok=True)

    def clip(self, name):
        return next(c for c in self.clips if c["name"] == name)

    def outputs(self):
        """Every file written beside out: the edit, its captions, the corrected copy and the upload copies."""
        suffixes = [".srt", ".vtt", ".corrected.mp4"]
        suffixes += [".upload.mp4", ".corrected.upload.mp4"] if self.encode["upload"] else []
        return [self.out, *(self.out.with_suffix(s) for s in suffixes)]

    def f(self, clip, ext):
        """work/<clip>.<ext>"""
        return self.work / f"{clip if isinstance(clip, str) else clip['name']}.{ext}"


def check_drops(clip, kept, fps):
    """Drop spans are [start, end] source seconds, in order, apart and at least kept + 1 frames long.

    kept is the frames a cut keeps (keep_head_frames + keep_tail_frames), so a drop always removes something.
    Whether a span ends inside the clip needs the clip's duration, so edl.build_clip checks that.
    """
    spans, name, shortest = clip["drop"], clip["name"], (kept + 1) / fps
    if spans and clip["card"]:
        raise ValueError(f"clip {name}: a card clip plays whole, so it takes no drop")
    end = None
    for span in spans:
        ok = isinstance(span, list) and len(span) == 2 and all(type(x) in (int, float) for x in span)
        if not ok or not 0 <= span[0] < span[1]:
            raise ValueError(f"clip {name}: drop {span!r} must be [start, end] with 0 <= start < end")
        if span[1] - span[0] < shortest:
            raise ValueError(
                f"clip {name}: drop {span!r} is under {kept + 1} frames ({shortest:.3f} s); a cut keeps {kept}"
            )
        if end is not None and span[0] <= end:
            raise ValueError(f"clip {name}: drop {span!r} touches, overlaps or precedes the one before it")
        end = span[1]


def check_captions(c, clips, rules):
    """Every [captions] key is known and in range, and every card caption names a card clip."""
    extra = sorted(set(c) - set(CAPTIONS) - {"sentence_chars"})
    if extra:
        raise ValueError(f"captions: unknown key {', '.join(extra)}; the keys are in condense/README.md")
    for key, choices in CAPTION_CHOICES.items():
        if c[key] not in choices:
            raise ValueError(f"captions.{key} = {c[key]!r}: one of {', '.join(choices)}")
    if type(c["fillers"]) is not bool:
        raise ValueError(f"captions.fillers = {c['fillers']!r}: true or false")
    for key in ("gap_s", "max_s", "min_s", "clear_s", "squeeze_s", "card_inset_s"):
        if type(c[key]) not in (int, float) or c[key] < 0 or (key == "gap_s" and not c[key]):
            raise ValueError(
                f"captions.{key} = {c[key]!r}: a number of seconds, {'over' if key == 'gap_s' else 'at least'} 0"
            )
    if type(c["sentence_chars"]) is not int or c["sentence_chars"] < 0:
        raise ValueError(f"captions.sentence_chars = {c['sentence_chars']!r}: a whole number, at least 0")
    if c["clear_s"] and c["clear_s"] >= c["squeeze_s"]:
        raise ValueError("captions.clear_s needs a larger squeeze_s, so a cut-short cue never ends before it starts")
    if c["fill"] == "chars" and c["split"] != "balanced":
        raise ValueError("captions.fill = 'chars' needs split = 'balanced': a greedy wrap could need a third line")
    if c["split"] == "balanced" and rules["caption_lines"] != 2:
        raise ValueError("captions.split = 'balanced' breaks a cue into two lines: it needs rules.caption_lines = 2")
    cards = {clip["name"]: clip for clip in clips if clip["card"]}
    if not isinstance(c["cards"], dict):
        raise ValueError("captions.cards: a table of card clip name = [caption lines]")
    for name, lines in c["cards"].items():
        if name not in cards:
            raise ValueError(f"captions.cards.{name}: not a card clip in order")
        if not (isinstance(lines, list) and lines and all(isinstance(x, str) and x.strip() for x in lines)):
            raise ValueError(f"captions.cards.{name} = {lines!r}: a list of non-empty lines")
        if 2 * c["card_inset_s"] >= cards[name]["card_s"]:
            raise ValueError(f"captions.card_inset_s = {c['card_inset_s']}: leaves no time on the {name} card")


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
