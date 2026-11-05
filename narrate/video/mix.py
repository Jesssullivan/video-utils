"""The mix stage of lane L4: voice, kept clip sound and the ducked bed, through one limiter (NARRATED_VIDEO.md, "Mix").

Levels (NV-2, the deck project's ruling 58):

1. The placed voice is re-measured (EBU R128). It must already sit at the delivery's target: a voice further than
   driftLu from targetLufs refuses foreground_not_normalised. Nothing loudness-normalises the voice or the mix.
2. The bed is tiled from its cycle to the program's length and set bedBelowVoiceLu under the measured voice, from the
   cycle's integrated loudness (music stage): un-ducked, it sits 20 LU under the voice by default.
3. A duck envelope lowers the bed by duckDb under the foreground. Sidechain keys it on the foreground itself (voice
   plus kept clip sound, power per 10 ms block above SIDECHAIN_THRESHOLD_DBFS). EdlEnvelope keys it on the placed
   segments' spans. The gain moves at duckDb per attackMs going down and duckDb per releaseMs coming back.
4. Fades: fadeInS from the program's start and fadeOutS to its end. On a card or still base with a bed, the program
   runs to the last narration's end plus the music tailS (at least the placed length), rounded up to a whole frame,
   so the fade-out follows the voice. A video base keeps its own length.
5. One limiter (FFmpeg alimiter, latency compensated, no auto level) at LIMITER_HEADROOM_DB under truePeakDbtp.
6. The mix is measured. Integrated loudness further than driftLu from targetLufs refuses loudness_drift; a true peak
   above truePeakDbtp refuses true_peak_exceeded. Both are verdicts for the stage key.

Mono is the default delivery (NV-2). Stereo writes the same mix on both channels at -3.01 dB each, so the measured
integrated loudness stays at the target. Outputs: mix.wav, bed-ducked.wav (the bed after level, duck and fades, before
the limiter) and mix.json. The applied duck depth is the median envelope depth over the blocks where the duck is
keyed on; it is a measurement of the gain the stage applied, not a listening result.
"""

import array
import json
import math
import statistics

from .. import audio
from . import labels
from .common import (
    BITEXACT,
    LIMITER_HEADROOM_DB,
    RATE_HZ,
    StageRefused,
    ffmpeg,
    loudness,
    upstream,
    work_dir,
    write_json,
)
from .place import frames_for, samples_for, timeline

BLOCK_MS = 10
BLOCK = RATE_HZ * BLOCK_MS // 1000
ENV_RATE_HZ = 1000  # the duck envelope is written at 1 kHz and resampled to 48 kHz by FFmpeg
SIDECHAIN_THRESHOLD_DBFS = -45.0
DUCK_WARN_DB = (6.0, 8.0)  # NV-2: 6 to 8 dB under the foreground
DUCK_MIN_DB = 3.0  # the deck playbook's gate: a duck of at least 3 dB
STEREO = "pan=stereo|c0=0.707107*c0|c1=0.707107*c0"  # -3.01 dB on each channel keeps the integrated loudness


# Pure parts: tested alone ----------------------------------------------------------------------------------------
def block_power(samples, block=BLOCK):
    """Mean square per block (full scale 1.0), the last partial block included."""
    out = []
    for i in range(0, len(samples), block):
        seg = samples[i : i + block]
        out.append(math.sumprod(seg, seg) / (len(seg) * 32768.0 * 32768.0))
    return out


def sidechain_keys(powers, threshold_dbfs=SIDECHAIN_THRESHOLD_DBFS):
    floor = 10 ** (threshold_dbfs / 10)
    return [p >= floor for p in powers]


def span_keys(spans, blocks, block=BLOCK):
    """Blocks that overlap any [start, end) sample span."""
    keys = [False] * blocks
    for start, end in spans:
        for b in range(max(0, start // block), min(blocks, -(-end // block))):
            keys[b] = True
    return keys


def envelope(keys, duck_db, attack_ms, release_ms, block_ms=BLOCK_MS):
    """Gain in dB at the end of each block: toward -duck_db while keyed, toward 0 otherwise, at duck_db per attack_ms
    down and duck_db per release_ms up (an instant step when the time is 0)."""
    down = math.inf if attack_ms == 0 else duck_db * block_ms / attack_ms
    up = math.inf if release_ms == 0 else duck_db * block_ms / release_ms
    gain, out = 0.0, []
    for keyed in keys:
        target = -duck_db if keyed else 0.0
        gain = max(target, gain - down) if target < gain else min(target, gain + up)
        out.append(gain)
    return out


def duck_depth(env, keys):
    """The median applied depth (dB, positive) over keyed blocks; None when the duck never keys on."""
    depths = [-g for g, k in zip(env, keys, strict=True) if k]
    return round(statistics.median(depths), 3) if depths else None


def envelope_samples(env, block_ms=BLOCK_MS, rate=ENV_RATE_HZ):
    """Linear gain at rate, interpolated in dB from each block's start gain to its end gain."""
    per = rate * block_ms // 1000
    out, previous = array.array("h"), 0.0
    for gain in env:
        for k in range(1, per + 1):
            db = previous + (gain - previous) * k / per
            out.append(min(32767, round(32767 * 10 ** (db / 20))))
        previous = gain
    return out


def gates(voice_lufs, mix_lufs, mix_peak, delivery):
    """[(code, detail)] the levels refuse: the foreground off its target, drift and the true peak."""
    target, drift, ceiling = delivery["targetLufs"], delivery["driftLu"], delivery["truePeakDbtp"]
    out = []
    if voice_lufs is not None and not abs(voice_lufs - target) <= drift:
        out.append(("foreground_not_normalised", f"the voice measures {voice_lufs} LUFS, target {target}"))
    if mix_lufs is not None and not abs(mix_lufs - target) <= drift:
        out.append(("loudness_drift", f"the mix measures {mix_lufs} LUFS, {abs(mix_lufs - target):.2f} LU off"))
    if mix_peak is not None and not mix_peak <= ceiling:
        out.append(("true_peak_exceeded", f"the mix peaks at {mix_peak} dBTP, ceiling {ceiling}"))
    return out


def refuse_first(found):
    if found:
        code, detail = found[0]
        raise StageRefused(code, detail)


def program_samples(placed, music, extendable, fps):
    """The program length: the placed length, or on an extendable base with a bed, the last narration's end plus
    the music tail when that is longer, rounded up to a whole frame."""
    total = placed["clock"]["total_samples"]
    if music is None or not extendable:
        return total
    wanted = placed["voice_end_sample"] + round(music["tailS"] * RATE_HZ)
    return max(total, samples_for(frames_for(wanted, fps), fps))


# The stage ------------------------------------------------------------------------------------------------------
def run_mix(rc, row, partial):
    job = rc.job
    music, delivery = job["music"], job["delivery"]
    place_manifest, place_dir = upstream(rc.store, "place")
    placed = json.loads((place_dir / "placements.json").read_text(encoding="utf-8"))
    fps = placed["clock"]["fps"]
    voice_wav = place_dir / "voice.wav"
    clips_wav = place_dir / "clips.wav" if placed["clips"] else None
    voice = loudness(voice_wav)
    refuse_first(gates(voice["integrated_lufs"], None, None, delivery))
    total = program_samples(placed, music, placed["base"]["extendable"], fps)
    parents = [place_manifest]
    measured = {
        "voice_integrated_lufs": voice["integrated_lufs"],
        "target_lufs": delivery["targetLufs"],
        "total_samples": total,
        "frames": frames_for(total, fps),
        "length_s": round(total / RATE_HZ, 6),
        "channels": delivery["channels"],
        "limiter_dbtp": delivery["truePeakDbtp"] - LIMITER_HEADROOM_DB,
    }
    flags = []
    limit = 10 ** (measured["limiter_dbtp"] / 20)
    limiter = f"alimiter=limit={limit:.6f}:attack=5:release=50:level=false:latency=1"
    if delivery["channels"] == "Stereo":
        limiter += "," + STEREO
    with work_dir(rc.store) as work:
        inputs = ["-i", str(voice_wav)] + (["-i", str(clips_wav)] if clips_wav else [])
        labels_in = ["[0:a]"] + (["[1:a]"] if clips_wav else [])
        if music is not None:
            music_manifest, music_dir = upstream(rc.store, "music")
            parents.append(music_manifest)
            bed_lufs = music_manifest["measurements"]["integrated_lufs"]
            bed_gain = round(voice["integrated_lufs"] - music["bedBelowVoiceLu"] - bed_lufs, 4)
            voice_pcm = audio.read(voice_wav)
            powers = block_power(voice_pcm.samples)
            blocks = -(-total // BLOCK)
            powers += [0.0] * (blocks - len(powers))
            if clips_wav:
                clip_powers = block_power(audio.read(clips_wav).samples)
                clip_powers += [0.0] * (blocks - len(clip_powers))
                powers = [a + b for a, b in zip(powers, clip_powers, strict=False)]
            powers = powers[:blocks]
            if music["duckMode"] == "Sidechain":
                keys = sidechain_keys(powers)
            else:
                spans = [(s["start_sample"], s["end_sample"]) for s in placed["segments"]]
                keys = span_keys(spans, blocks)
            env = envelope(keys, music["duckDb"], music["attackMs"], music["releaseMs"])
            depth = duck_depth(env, keys)
            audio.Pcm(ENV_RATE_HZ, envelope_samples(env)).write(work / "envelope.wav")
            length_s = total / RATE_HZ
            fade_out_at = max(0.0, length_s - music["fadeOutS"])
            bed_chain = (
                f"[0:a]atrim=end_sample={total},asetpts=N/SR/TB,volume={bed_gain}dB,"
                f"afade=t=in:st=0:d={music['fadeInS']},afade=t=out:st={fade_out_at:.6f}:d={music['fadeOutS']}[b];"
                f"[1:a]aresample={RATE_HZ},apad=whole_len={total},atrim=end_sample={total}[e];"
                "[b][e]amultiply[out]"
            )
            ffmpeg(
                "-stream_loop", "-1", "-i", str(music_dir / "bed.wav"), "-i", str(work / "envelope.wav"),
                "-filter_complex", bed_chain, "-map", "[out]", "-ac", "1", "-ar", str(RATE_HZ),
                "-c:a", "pcm_s16le", *BITEXACT, str(partial / "bed-ducked.wav"),
            )  # fmt: skip
            inputs += ["-i", str(partial / "bed-ducked.wav")]
            labels_in.append(f"[{len(labels_in)}:a]")
            measured |= {
                "bed_integrated_lufs": bed_lufs,
                "bed_gain_db": bed_gain,
                "bed_below_voice_lu": music["bedBelowVoiceLu"],
                "duck_mode": music["duckMode"],
                "duck_db_target": music["duckDb"],
                "duck_depth_db": depth,
                "attack_ms": music["attackMs"],
                "release_ms": music["releaseMs"],
                "fade_in_s": music["fadeInS"],
                "fade_out_s": music["fadeOutS"],
                "sidechain_threshold_dbfs": SIDECHAIN_THRESHOLD_DBFS if music["duckMode"] == "Sidechain" else None,
                "gates": {"duck_min_3db": "passed" if depth is not None and depth >= DUCK_MIN_DB else "failed"},
            }
            if depth is None or not DUCK_WARN_DB[0] <= depth <= DUCK_WARN_DB[1]:
                flags.append("duck_outside_6_8_db")
        padded = "".join(f"{label}apad=whole_len={total}[i{k}];" for k, label in enumerate(labels_in))
        joined = "".join(f"[i{k}]" for k in range(len(labels_in)))
        mixer = f"amix=inputs={len(labels_in)}:normalize=0:duration=longest," if len(labels_in) > 1 else ""
        graph = f"{padded}{joined}{mixer}atrim=end_sample={total},{limiter}[m]"
        ffmpeg(
            *inputs, "-filter_complex", graph, "-map", "[m]", "-ar", str(RATE_HZ),
            "-c:a", "pcm_s16le", *BITEXACT, str(partial / "mix.wav"),
        )  # fmt: skip
    mix = loudness(partial / "mix.wav")
    measured |= {
        "integrated_lufs": mix["integrated_lufs"],
        "true_peak_dbtp": mix["true_peak_dbtp"],
        "loudness_range_lu": mix["loudness_range_lu"],
        "drift_lu": round(mix["integrated_lufs"] - delivery["targetLufs"], 3),
        "flags": flags,
    }
    write_json(partial / "mix.json", measured | {"filter": graph})
    refuse_first(gates(None, mix["integrated_lufs"], mix["true_peak_dbtp"], delivery))
    persona = job["labels"]["persona"]
    grown = labels.grow(parents, persona)
    labels.check(grown, parents, persona)
    return {
        "synthetic": grown["synthetic"],
        "labels": grown,
        "measurements": measured,
        "timeline": timeline(fps, place_manifest["outputs"]["placements.json"]),
        "states": {"source_checks": "passed", "render": "local", "listening": "pending_operator"},
    }
