"""ffprobe and ffmpeg measurements: durations, frame counts, silences and the RMS track."""

import json
import math
import re

from .config import FF, run

# Pad the audio from time 0, so sample n sits at n / rate seconds on the video's clock. Samples are then
# counted from the start of the file and never from a seek point.
FROM_ZERO = "aresample=async=1:first_pts=0"


def duration(path, stream="a:0"):
    out = run(
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        stream,
        "-show_entries",
        "stream=duration:format=duration",
        "-of",
        "json",
        path,
    ).stdout
    d = json.loads(out)
    return float((d["streams"] and d["streams"][0].get("duration")) or d["format"]["duration"])


def size(path):
    """(width, height) of the first video stream."""
    out = run(
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0",
        path,
    )
    return tuple(int(x) for x in out.stdout.strip().strip(",").split(",")[:2])


def frames(path):
    out = run(
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-count_packets",
        "-show_entries",
        "stream=nb_read_packets",
        "-of",
        "csv=p=0",
        path,
    ).stdout
    return int(out.strip().strip(","))


def shift(path, fps):
    """Seconds from analysis time to source time: the audio stream's start after the video's, rounded up to frames.

    The analysis wav starts at the first audio sample. One recording's audio started 0.087 s after its video,
    so analysis time t was source time t + 0.087 s. At 30 fps the shift is 3 frames, 0.1 s: cuts stay on the
    frame grid and land 0.013 s late, the same for picture and sound.
    """
    out = run("ffprobe", "-v", "error", "-show_entries", "stream=codec_type,start_time", "-of", "json", path).stdout
    start = {"video": 0.0, "audio": 0.0}
    for s in reversed(json.loads(out)["streams"]):  # the first stream of each type wins
        if s.get("start_time", "N/A") != "N/A":
            start[s["codec_type"]] = float(s["start_time"])
    return max(0, math.ceil((start["audio"] - start["video"]) * fps - 1e-6)) / fps


def extract(cfg, clip):
    """16 kHz mono wav for analysis. Return the wav whisper reads: the levelled copy when the clip asks for one."""
    wav, norm = cfg.f(clip, "16k.wav"), cfg.f(clip, "16k.norm.wav")
    base = (*FF, "-v", "error", "-i", clip["file"], "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000")
    base += ("-c:a", "pcm_s16le")
    run(*base, wav)
    if not clip["normalize"]:
        return wav
    run(*base, "-af", "highpass=f=80,dynaudnorm=f=250:g=15:m=20", norm)
    return norm


def silences(path, db, min_s, log=None):
    """[(start, end)] from silencedetect. The raw log goes to `log` when given."""
    err = run(*FF, "-i", path, "-vn", "-af", f"silencedetect=noise={db}dB:d={min_s}", "-f", "null", "-").stderr
    if log:
        log.write_text(err)
    out, start = [], None
    for line in err.splitlines():
        if m := re.search(r"silence_start: (-?[\d.]+)", line):
            start = max(float(m[1]), 0.0)
        if (m := re.search(r"silence_end: ([\d.]+)", line)) and start is not None:
            out.append((start, float(m[1])))
            start = None
    return out


def write_rms(wav, txt):
    """RMS level of every 100 ms frame, as ffmpeg metadata text."""
    af = "asetnsamples=n=1600:p=0,astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file="
    run(*FF, "-v", "error", "-i", wav, "-af", af + txt.name, "-f", "null", "-", cwd=txt.parent)


def read_rms(txt):
    """{frame index: dB}; frame f covers [f / 10, (f + 1) / 10) seconds."""
    pairs = re.findall(r"pts_time:([\d.]+)\n.*RMS_level=(-?[\d.]+|-inf)", txt.read_text())
    return {round(float(t) * 10): float(r) if r != "-inf" else -99.0 for t, r in pairs}
