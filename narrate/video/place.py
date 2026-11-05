"""The base and place stages of lane L4 (docs/spec/NARRATED_VIDEO.md, "Base and place").

base conforms the picture and writes base.json:

- Card: one frame of the colour at the job's size, `base.png`. Still: the still from the private store, scaled to fit
  the job's size and padded, `base.png`. Neither has a length: place extends it to the narration plus tailS.
- Video: the video from the private store, re-encoded at its own size and rate to constant-rate H.264 `base.mp4`, with
  its length in frames. With keepBaseAudio its sound becomes `clips.wav` (48 kHz mono) on the base clock.
- Deck: imported by digest in lane L8 (the deck seam). Until then base refuses base_deck_pending, unrecorded.

place lays each segment's narration on the base clock (48 kHz) and writes `voice.wav`, `clips.wav` when the base kept
its sound, and `placements.json`. Anchors: Auto starts where the previous segment ends (0 for the first), AtSeconds
starts at that second; Page needs a deck base. Segments never overlap (placement_overlap). A video base must hold every
segment (base_too_short); a card or still is extended to the last segment's end plus tailS, rounded up to a whole
frame. Each narration is resampled from its engine's rate to 48 kHz and placed sample-exact; nothing is time-stretched.
Place runs Edition.check at its point over the leaves it sees: the voice manifests' synthetic labels and the job.
"""

import array
import json
import math
import shutil
from fractions import Fraction

from .. import audio
from ..ir import sha256_file
from . import admit, labels
from .common import RATE_HZ, StageRefused, ffmpeg, ffprobe, to_mono, upstream, work_dir, write_json
from .speech import narration_wav

MAPPING = "narrated_video_v1"
OUTPUT_AXIS = "base frame index / fps, and sample index / sample_rate on the same base clock"
SOURCE_AXIS = (
    "none: narration, overlays and the bed are new tracks laid on the base clock; no source media is time-stretched"
)


def rate(fps):
    return Fraction(fps["num"], fps["den"])


def frames_for(samples, fps):
    """Whole frames that hold samples at RATE_HZ."""
    return math.ceil(Fraction(samples) * rate(fps) / RATE_HZ)


def samples_for(frames, fps):
    return round(Fraction(frames) * RATE_HZ / rate(fps))


def parse_rate(*texts):
    """The first positive frame rate among ffprobe's rate strings ("30/1", "30000/1001"; "0/0" is none)."""
    for text in texts:
        num, _, den = str(text or "").partition("/")
        try:
            value = Fraction(int(num), int(den or 1))
        except (ValueError, ZeroDivisionError):
            continue
        if value > 0:
            return {"num": value.numerator, "den": value.denominator}
    raise StageRefused("base_invalid", "the video has no frame rate")


# base -----------------------------------------------------------------------------------------------------------
def run_base(rc, row, partial):
    kind, body = next(iter(rc.job["base"].items()))
    if kind == "deck":
        raise StageRefused("base_deck_pending", "a deck base is imported in lane L8 (the deck seam)", verdict=False)
    if kind in ("card", "still"):
        size, fps = body["size"], body["fps"]
        w, h = size["w"], size["h"]
        if kind == "card":
            colour = body["colour"].lstrip("#")
            source = ["-f", "lavfi", "-i", f"color=c=0x{colour}:s={w}x{h}:r={fps['num']}/{fps['den']}"]
            chain = "format=rgb24"
        else:
            still = rc.env.source(body["sha256"], "the still")
            info = ffprobe(still)
            if not any(s.get("codec_type") == "video" for s in info.get("streams", [])):
                raise StageRefused("base_invalid", "the still holds no picture")
            source = ["-i", str(still)]
            chain = (
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,format=rgb24"
            )
        ffmpeg(
            *source,
            "-frames:v",
            "1",
            "-vf",
            chain,
            "-fflags",
            "+bitexact",
            "-flags:v",
            "+bitexact",
            str(partial / "base.png"),
        )
        record = {
            "kind": kind,
            "picture": "base.png",
            "size": {"w": w, "h": h},
            "fps": fps,
            "frames": None,
            "length_samples": None,
            "extendable": True,
            "clip_sound": False,
        }
    else:
        video = rc.env.source(body["sha256"], "the base video")
        info = ffprobe(video)
        stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
        if stream is None:
            raise StageRefused("base_invalid", "the base video holds no picture")
        fps = parse_rate(stream.get("avg_frame_rate"), stream.get("r_frame_rate"))
        target = partial / "base.mp4"
        ffmpeg(
            "-i", str(video), "-map", "0:v:0", "-an",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1,format=yuv420p",
            "-fps_mode", "cfr", "-r", f"{fps['num']}/{fps['den']}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-threads", "2",
            "-fflags", "+bitexact", "-flags:v", "+bitexact", "-map_metadata", "-1", str(target),
        )  # fmt: skip
        out = next(s for s in ffprobe(target)["streams"] if s.get("codec_type") == "video")
        frames = int(out.get("nb_frames") or 0)
        if frames <= 0:
            raise StageRefused("base_invalid", "the conformed base video has no frames")
        length = samples_for(frames, fps)
        clip_sound = False
        if body["keepBaseAudio"] and any(s.get("codec_type") == "audio" for s in info.get("streams", [])):
            to_mono(video, partial / "clips.wav", chain=f"apad=whole_len={length},atrim=end_sample={length}")
            clip_sound = True
        record = {
            "kind": kind,
            "picture": "base.mp4",
            "size": {"w": int(out["width"]), "h": int(out["height"])},
            "fps": fps,
            "frames": frames,
            "length_samples": length,
            "extendable": False,
            "clip_sound": clip_sound,
        }
    write_json(partial / "base.json", record | {"sample_rate": RATE_HZ})
    length_s = None if record["length_samples"] is None else round(record["length_samples"] / RATE_HZ, 6)
    return {
        "measurements": {
            "fps": record["fps"],
            "size": record["size"],
            "frames": record["frames"],
            "length_s": length_s,
            "extendable": record["extendable"],
            "clip_sound": record["clip_sound"],
        },
        "states": {"source_checks": "passed", "render": "local"},
    }


# place ----------------------------------------------------------------------------------------------------------
def layout(segments, fps, base, tail_s):
    """Sample-exact placement on the base clock. segments: [{id, anchor, samples}] in job order; base: {extendable,
    length_samples}. Returns {segments: [{id, start_sample, end_sample}], total_samples, frames}."""
    placed, previous_end = [], 0
    for segment in segments:
        anchor = segment["anchor"]
        if anchor == "Auto":
            start = previous_end
        elif isinstance(anchor, dict) and "atSeconds" in anchor:
            if anchor["atSeconds"] < 0:
                raise StageRefused("anchor_invalid", f"segment {segment['id']} starts before the base")
            start = round(anchor["atSeconds"] * RATE_HZ)
        else:
            raise StageRefused("anchor_needs_deck", f"segment {segment['id']} names a page; only a deck base has pages")
        end = start + segment["samples"]
        placed.append({"id": segment["id"], "start_sample": start, "end_sample": end})
        previous_end = end
    ordered = sorted(placed, key=lambda p: (p["start_sample"], p["end_sample"]))
    for a, b in zip(ordered, ordered[1:], strict=False):
        if b["start_sample"] < a["end_sample"]:
            raise StageRefused("placement_overlap", f"segments {a['id']} and {b['id']} overlap on the base clock")
    last = max((p["end_sample"] for p in placed), default=0)
    if base["extendable"]:
        frames = max(1, frames_for(last + round(tail_s * RATE_HZ), fps))
        total = samples_for(frames, fps)
    else:
        total = base["length_samples"]
        frames = base["frames"]
        if last > total:
            raise StageRefused(
                "base_too_short", f"the narration ends {(last - total) / RATE_HZ:.3f} s after the base video"
            )
    return {"segments": placed, "total_samples": total, "frames": frames}


def edition_at_place(job, records, voice_manifests):
    """Edition.check at Place: the job's leaves, with syntheticVoice also read from the placed stems' manifests."""
    check = admit.port()
    bed = records["music_beds"].get(job["music"]["bed"]) if job["music"] else None
    leaves = check.plan_leaves(job, bed)
    leaves["syntheticVoice"] = leaves["syntheticVoice"] or any(m.get("synthetic") is True for m in voice_manifests)
    verdict = check.edition_check("Place", job["edition"], leaves)
    codes = [check.EDITION_REFUSALS[c] for c in verdict.get("codes", [])]
    if codes:
        raise StageRefused(codes[0], f"edition {job['edition']} at Place: {', '.join(codes)}")
    return verdict


def run_place(rc, row, partial):
    job = rc.job
    _, base_dir = upstream(rc.store, "base")
    base = json.loads((base_dir / "base.json").read_text(encoding="utf-8"))
    voices, qas, rows = [], [], []
    with work_dir(rc.store) as work:
        pcms = {}
        for segment in job["segments"]:
            manifest, directory = upstream(rc.store, f"voice/{segment['id']}")
            qa_manifest, _ = upstream(rc.store, f"voice_qa/{segment['id']}")
            voices.append(manifest)
            qas.append(qa_manifest)
            resampled = to_mono(narration_wav(directory), work / f"{segment['id']}.wav")
            pcm = audio.read(resampled)
            pcms[segment["id"]] = pcm
            rows.append({"id": segment["id"], "anchor": segment["anchor"], "samples": len(pcm.samples)})
        edition_at_place(job, rc.records, voices)
        tail_s = next(iter(job["base"].values())).get("tailS") or 0
        placed = layout(rows, base["fps"], base, tail_s)
        track = array.array("h", bytes(2 * placed["total_samples"]))
        for p in placed["segments"]:
            track[p["start_sample"] : p["end_sample"]] = pcms[p["id"]].samples
        audio.Pcm(RATE_HZ, track).write(partial / "voice.wav")
    if base["clip_sound"]:
        shutil.copyfile(base_dir / "clips.wav", partial / "clips.wav")
    by_id = {s["id"]: s for s in job["segments"]}
    segments = []
    for p, manifest in zip(placed["segments"], voices, strict=True):
        m = manifest["measurements"]
        segments.append(
            {
                "id": p["id"],
                "anchor": by_id[p["id"]]["anchor"],
                "start_sample": p["start_sample"],
                "end_sample": p["end_sample"],
                "start_s": round(p["start_sample"] / RATE_HZ, 6),
                "end_s": round(p["end_sample"] / RATE_HZ, 6),
                "narration_sha256": m["narration_sha256"],
                "narrate_content_sha256": m["narrate_content_sha256"],
                "resampled": {"from_hz": m["sample_rate"], "to_hz": RATE_HZ},
            }
        )
    voice_end = max((p["end_sample"] for p in placed["segments"]), default=0)
    placements = {
        "kind": "nv_placements",
        "schema_version": 1,
        "clock": {
            "fps": base["fps"],
            "sample_rate": RATE_HZ,
            "frames": placed["frames"],
            "total_samples": placed["total_samples"],
            "length_s": round(placed["total_samples"] / RATE_HZ, 6),
        },
        "base": {"kind": base["kind"], "extendable": base["extendable"], "tail_s": tail_s},
        "segments": segments,
        "voice_end_sample": voice_end,
        "clips": base["clip_sound"],
    }
    write_json(partial / "placements.json", placements)
    grown = labels.grow(voices + qas, job["labels"]["persona"])
    labels.check(grown, voices + qas, job["labels"]["persona"])
    return {
        "synthetic": grown["synthetic"],
        "labels": grown,
        "measurements": {
            "fps": base["fps"],
            "frames": placed["frames"],
            "total_samples": placed["total_samples"],
            "length_s": placements["clock"]["length_s"],
            "voice_end_s": round(voice_end / RATE_HZ, 6),
            "extendable": base["extendable"],
            "clips": base["clip_sound"],
            "segments": [{"id": s["id"], "start_s": s["start_s"], "end_s": s["end_s"]} for s in segments],
        },
        "timeline": timeline(base["fps"], sha256_file(partial / "placements.json")),
        "states": {"source_checks": "passed", "render": "local"},
    }


def timeline(fps, placements_sha256):
    return {
        "mapping": MAPPING,
        "no_time_stretch": False,
        "stretch_applied": False,
        "clock": "base",
        "fps": fps,
        "sample_rate": RATE_HZ,
        "placements": {"file": "placements.json", "sha256": placements_sha256},
        "output_axis": OUTPUT_AXIS,
        "source_axis": SOURCE_AXIS,
    }
