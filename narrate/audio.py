"""Mono 16-bit PCM WAV in and out, silence, and the FFmpeg steps: canonical form, atempo, a voice's time stretch,
two-pass loudnorm, EBU R128 measurement and FLAC.

Chunk audio stays at the engine's native rate. Only a reply that is not mono 16-bit PCM at that rate passes
through FFmpeg to become so; the conversion is recorded by the caller.
"""

import array
import io
import json
import math
import re
import shutil
import sys
import wave
from pathlib import Path

from .config import FF, run


class Pcm:
    """Mono 16-bit samples at a rate."""

    def __init__(self, rate, samples=None):
        self.rate = int(rate)
        self.samples = samples if samples is not None else array.array("h")

    @property
    def seconds(self):
        return len(self.samples) / self.rate

    def extend(self, other):
        if other.rate != self.rate:
            raise ValueError(f"rate {other.rate} differs from {self.rate}")
        self.samples.extend(other.samples)

    def silence(self, seconds):
        self.samples.extend(array.array("h", bytes(2 * max(0, round(seconds * self.rate)))))

    def wav(self):
        values = array.array("h", self.samples)
        if sys.byteorder != "little":
            values.byteswap()
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(self.rate)
            out.writeframes(values.tobytes())
        return buffer.getvalue()

    def write(self, path):
        Path(path).write_bytes(self.wav())
        return path


def parse(data):
    """A Pcm from WAV bytes, or None when they are not mono 16-bit PCM."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getcomptype() != "NONE":
                return None
            values = array.array("h", w.readframes(w.getnframes()))
            rate = w.getframerate()
    except (wave.Error, EOFError):
        return None
    if sys.byteorder != "little":
        values.byteswap()
    return Pcm(rate, values)


def read(path):
    pcm = parse(Path(path).read_bytes())
    if pcm is None:
        raise ValueError(f"{path} is not mono 16-bit PCM WAV")
    return pcm


def canonical(data, rate, work):
    """(Pcm at rate, converted) from any WAV an engine sent. rate None keeps the reply's own rate."""
    pcm = parse(data)
    if pcm is not None and (rate is None or pcm.rate == rate):
        return pcm, False
    source, target = Path(work) / "reply.wav", Path(work) / "reply.s16.wav"
    source.write_bytes(data)
    args = ["-ac", "1", "-c:a", "pcm_s16le"] + (["-ar", str(rate)] if rate else [])
    run(*FF, "-v", "error", "-i", source, *args, target)
    return read(target), True


def atempo(pcm, factor, work):
    """pcm played factor times faster, pitch kept (FFmpeg atempo), at the same rate."""
    source, target = Path(work) / "fit.in.wav", Path(work) / "fit.out.wav"
    pcm.write(source)
    run(
        *FF,
        "-v",
        "error",
        "-i",
        source,
        "-af",
        f"atempo={factor:.6f}",
        "-ac",
        "1",
        "-ar",
        str(pcm.rate),
        "-c:a",
        "pcm_s16le",
        target,
    )
    return read(target)


TEMPO_RANGE = (0.5, 2.0)  # one FFmpeg atempo filter; no chain of filters reaches past it
PCM_CODECS = {1: "pcm_u8", 2: "pcm_s16le", 3: "pcm_s24le", 4: "pcm_s32le"}


def wav_format(path):
    """(channels, sample width in bytes, rate, frames) of a PCM WAV file. Raises ValueError for anything else."""
    try:
        with wave.open(str(path)) as w:
            if w.getcomptype() != "NONE" or w.getsampwidth() not in PCM_CODECS:
                raise ValueError(f"{path} is not PCM WAV")
            return w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
    except (wave.Error, EOFError) as error:
        raise ValueError(f"{path} is not PCM WAV: {error}") from None


def time_stretch(path_in, path_out, factor):
    """path_in played factor times faster into path_out, pitch kept (one FFmpeg atempo), at the input's sample rate,
    channels and sample width. A factor of None or 1.0 copies the bytes and calls no FFmpeg. Returns path_out's
    duration in seconds. Raises ValueError for a factor outside TEMPO_RANGE or an input that is not PCM WAV.
    Measured on 2 s tones: atempo drops about 9 ms of the input's tail at 0.5 and about 4 ms at 0.9, and about none
    at 1.1, 1.25 and 2.0."""
    low, high = TEMPO_RANGE
    if factor is not None and (
        isinstance(factor, bool) or not isinstance(factor, (int, float)) or not low <= factor <= high
    ):
        raise ValueError(f"tempo {factor!r} is outside {low} to {high}")
    channels, width, rate, frames = wav_format(path_in)
    if factor is None or factor == 1.0:
        if Path(path_in).resolve() != Path(path_out).resolve():
            shutil.copyfile(path_in, path_out)
        return frames / rate
    run(
        *FF,
        "-v",
        "error",
        "-i",
        path_in,
        "-af",
        f"atempo={factor:.6f}",
        "-ac",
        str(channels),
        "-ar",
        str(rate),
        "-c:a",
        PCM_CODECS[width],
        "-fflags",
        "+bitexact",
        "-flags:a",
        "+bitexact",
        path_out,
    )
    _, _, out_rate, out_frames = wav_format(path_out)
    return out_frames / out_rate


def loudnorm_json(stderr):
    block = stderr[stderr.rindex("{") : stderr.rindex("}") + 1]
    return json.loads(block)


LIMIT_ATTEMPTS = 4


def measure_loudnorm(source, chain, lufs, tp, lra):
    first = f"{chain}loudnorm=I={lufs}:TP={tp}:LRA={lra}:print_format=json"
    return loudnorm_json(run(*FF, "-nostats", "-i", source, "-af", first, "-f", "null", "-").stderr)


def loudnorm(source, target, rate, lufs, tp, lra=11.0, headroom_db=0.5):
    """Two-pass FFmpeg loudnorm of source into target at rate, linear. When the one linear gain would carry a
    peak past the ceiling, a limiter (alimiter, latency compensated) first holds the source's peaks to where the
    gain lands them headroom_db under it, as condense's delivery chain does; the source is measured again through
    it. Returns both passes' measured values and the limiter, if any."""
    measured = measure_loudnorm(source, "", lufs, tp, lra)
    chain, limiter, limit_db = "", None, None
    for attempt in range(1, LIMIT_ATTEMPTS + 1):
        over = float(measured["input_tp"]) + lufs - float(measured["input_i"]) - (tp - 0.1)
        if over <= 0:
            break
        # first: the source peak the gain lands headroom_db under the ceiling; then lower it by what is still over
        if limit_db is None:
            limit_db = tp - headroom_db - (lufs - float(measured["input_i"]))
        else:
            limit_db -= over + headroom_db / 2
        level = min(1.0, max(0.0625, 10 ** (limit_db / 20)))
        chain = f"alimiter=limit={level:.6f}:attack=5:release=50:level=false:latency=1,"
        limiter = {
            "limit_dbfs": round(20 * math.log10(level), 2),
            "attempts": attempt,
            "reason": "one linear gain would carry a peak over the ceiling",
        }
        measured = measure_loudnorm(source, chain, lufs, tp, lra)
    second = (
        f"{chain}loudnorm=I={lufs}:TP={tp}:LRA={lra}:measured_I={measured['input_i']}:"
        f"measured_TP={measured['input_tp']}:measured_LRA={measured['input_lra']}:"
        f"measured_thresh={measured['input_thresh']}:offset={measured['target_offset']}:linear=true:"
        "print_format=json"
    )
    applied = loudnorm_json(
        run(
            *FF,
            "-nostats",
            "-i",
            source,
            "-af",
            second,
            "-ar",
            str(rate),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            "-fflags",
            "+bitexact",
            "-flags:a",
            "+bitexact",
            target,
        ).stderr
    )
    keep = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    return {
        "first_pass": {k: float(measured[k]) for k in keep},
        "second_pass": {k: float(applied[k]) for k in (*keep, "output_i", "output_tp", "output_lra")},
        "normalization_type": applied.get("normalization_type"),
        "limiter": limiter,
    }


PEAK_TOLERANCE_DB = 0.1  # a true peak this far over the ceiling still passes (meter and resampler spread)


def loudness_verdict(integrated, peak, post, normalization_type=None):
    """(passed, flags) for one delivered file, shared by render and evaluate: integrated loudness within the
    job's tolerance, true peak at most PEAK_TOLERANCE_DB over the ceiling, and a linear loudnorm when its type is
    known. Each failure names its own flag."""
    flags = []
    if not abs(integrated - post["loudnessLufs"]) <= post["loudnessToleranceLu"]:
        flags.append("loudness_out_of_tolerance")
    if not peak <= post["truePeakDbtp"] + PEAK_TOLERANCE_DB:
        flags.append("true_peak_over_ceiling")
    if normalization_type is not None and normalization_type != "linear":
        flags.append("loudnorm_dynamic")
    return not flags, flags


def ebur128(path):
    """(integrated LUFS, loudness range LU, true peak dBTP) of a file's sound."""
    log = run(*FF, "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-").stderr
    summary = log[log.rindex("Summary:") :].split()
    values = []
    for key in ("I:", "LRA:", "Peak:"):
        token = summary[summary.index(key) + 1]
        values.append(float("-inf") if re.fullmatch(r"-?inf", token) else float(token))
    return tuple(values)


def flac(source, target):
    run(*FF, "-v", "error", "-i", source, "-c:a", "flac", "-compression_level", "8", target)
