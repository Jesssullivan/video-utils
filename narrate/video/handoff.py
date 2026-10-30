"""The handoff stage of lane L6: pre-VFX layers and edit.json (docs/spec/NARRATED_VIDEO.md, "Handoff").

handoff is optional (delivery.handoff). It writes the parts of a narrated video an editor or a VFX pass rebuilds it
from, each on the base clock, beside the composed cut:

  layers/base.mp4                    the base at the delivery profile: no overlay, no slide, no captions, no sound
  layers/avatar-<segment>.mov        each avatar overlay as its external (kitpip or vrm) wrote it (ProRes 4444,
                                     straight alpha)
  layers/avatar-<segment>.manifest.json
                                     that overlay's manifest (kitpip.manifest/v0 or avatar.manifest/v1), so its
                                     renderer, frames identity and, for vrm, the open badge decision and the
                                     likeness consent id travel with the layer
  layers/slide-<page>.png            each slide picture the job's pages show, with its metadata stripped: a PNG
                                     keeps its pixel bytes and colour chunks and loses its text, EXIF, ICC and
                                     time chunks (strip.strip_png); any other picture is decoded to a PNG first
  layers/voice.wav, layers/clips.wav the placed stems (clips only when the base kept its sound)
  layers/bed-ducked.wav              the bed after level, duck and fades, before the limiter (with a bed)
  layers/captions.srt, .vtt          the composed captions
  edit.json                          placements, overlay boxes and starts (each with its layer, manifest file and
                                     digest, renderer kind and frames identity), slide runs, avatar-off spans, the
                                     mix gains and the stage keys of every input

FCPXML and OTIO export is phase 2 (design section 5.2). Until an editor imports one, it stays unverified in an
application, as AGENTS.md rules for markers.
"""

import hashlib
import json
import shutil

from . import avatar_manifest, labels, strip
from .common import StageRefused, ffmpeg, upstream, write_json
from .compose import PIX_FMT, conform, profile_for
from .graph import selection, slide_sources
from .place import timeline


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def slide_layer(source, target, partial):
    """Write a slide picture as a PNG with no metadata chunk; returns the chunk types dropped. A picture that is not
    a PNG is decoded to one first (bit-exact, no metadata)."""
    data = source.read_bytes()
    stripped = strip.strip_png(data)
    if stripped is None:
        decoded = partial / f".{target.stem}.decoded.png"
        ffmpeg("-i", str(source), "-frames:v", "1", "-map_metadata", "-1", "-fflags", "+bitexact",
               "-flags:v", "+bitexact", "-c:v", "png", "-f", "image2", str(decoded))  # fmt: skip
        stripped = strip.strip_png(decoded.read_bytes())
        decoded.unlink()
        if stripped is None:
            raise StageRefused("ffmpeg_failed", f"{target.name} did not decode to a PNG", verdict=False)
    data, dropped = stripped
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return dropped


def run_handoff(rc, row, partial):
    job = rc.job
    base_manifest, base_dir = upstream(rc.store, "base")
    place_manifest, place_dir = upstream(rc.store, "place")
    mix_manifest, mix_dir = upstream(rc.store, "mix")
    compose_manifest, compose_dir = upstream(rc.store, "compose")
    base = json.loads((base_dir / "base.json").read_text(encoding="utf-8"))
    placements = json.loads((place_dir / "placements.json").read_text(encoding="utf-8"))
    composed = compose_manifest["measurements"]
    profile = profile_for(job["delivery"]["profile"], base["fps"])
    fps, size = profile["fps"], profile["size"]
    layers = partial / "layers"
    layers.mkdir()
    picture = base_dir / base["picture"]
    loop = ["-loop", "1", "-framerate", f"{fps['num']}/{fps['den']}"] if base["picture"] == "base.png" else []
    pad = "" if loop else ",tpad=stop_mode=clone:stop_duration=1"
    ffmpeg(
        *loop, "-i", str(picture), "-an",
        "-vf", f"{conform(size['w'], size['h'])},fps={fps['num']}/{fps['den']}{pad},format={PIX_FMT}",
        "-frames:v", str(composed["frames"]), "-c:v", "libx264", "-preset", profile["preset"],
        "-crf", str(profile["crf"]), "-pix_fmt", PIX_FMT, "-threads", "2", "-map_metadata", "-1", "-map_chapters", "-1",
        "-fflags", "+bitexact", "-flags:v", "+bitexact", str(layers / "base.mp4"),
    )  # fmt: skip
    strip.check_media(layers / "base.mp4", strip.local_roots(rc.store.root, rc.env.store_dir, rc.env.records_dir))
    copy(place_dir / "voice.wav", layers / "voice.wav")
    if placements["clips"]:
        copy(place_dir / "clips.wav", layers / "clips.wav")
    if (mix_dir / "bed-ducked.wav").is_file():
        copy(mix_dir / "bed-ducked.wav", layers / "bed-ducked.wav")
    for name in ("captions.srt", "captions.vtt"):
        if (compose_dir / name).is_file():
            copy(compose_dir / name, layers / name)
    parents = [base_manifest, place_manifest, mix_manifest, compose_manifest]
    keys = {node: rc.store.entry(node)["key"] for node in ("base", "place", "mix", "compose")}
    if job["music"] is not None:
        keys["music"] = rc.store.entry("music")["key"]
    overlays = []
    for segment in job["segments"]:
        if not selection("avatar", segment, job)[0]:
            continue
        node = f"avatar/{segment['id']}"
        manifest, directory = upstream(rc.store, node)
        parents.append(manifest)
        keys[node] = rc.store.entry(node)["key"]
        copy(directory / "overlay" / "overlay.mov", layers / f"avatar-{segment['id']}.mov")
        manifest_file = layers / f"avatar-{segment['id']}.manifest.json"
        copy(directory / "overlay" / "manifest.json", manifest_file)
        seen = avatar_manifest.view(json.loads(manifest_file.read_text(encoding="utf-8")))
        overlays.append(
            {
                "file": f"layers/avatar-{segment['id']}.mov",
                "manifest": f"layers/{manifest_file.name}",
                "manifest_sha256": hashlib.sha256(manifest_file.read_bytes()).hexdigest(),
                "renderer_kind": seen["renderer_kind"],
                "frames_identity": seen["frames_identity"],
            }
        )
    slides = []
    for page, digest in slide_sources(job):
        source = rc.env.source(digest, f"slide {page}")
        target = layers / f"slide-{page}.png"
        dropped = slide_layer(source, target, partial)
        layer_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
        slides.append(
            {"page": page, "file": f"layers/{target.name}", "sha256": digest, "layer_sha256": layer_sha256,
             "stripped": dropped}
        )  # fmt: skip
    mix = mix_manifest["measurements"]
    edit = {
        "kind": "nv_edit",
        "schema_version": 1,
        "clock": placements["clock"],
        "profile": {"name": profile["name"], "size": size, "fps": fps, "frames": composed["frames"]},
        "segments": placements["segments"],
        "overlays": [o | layer for o, layer in zip(composed["overlays"], overlays, strict=True)],
        "slides": composed["slides"],
        "slide_files": slides,
        "avatar_off": composed["avatar_off"],
        "mix": {
            k: mix.get(k)
            for k in (
                "voice_integrated_lufs",
                "bed_gain_db",
                "bed_below_voice_lu",
                "duck_mode",
                "duck_db_target",
                "duck_depth_db",
                "attack_ms",
                "release_ms",
                "fade_in_s",
                "fade_out_s",
                "limiter_dbtp",
                "channels",
            )
        },  # fmt: skip
        "stage_keys": keys,
        "export": {"fcpxml": "phase 2", "otio": "phase 2", "application_import": "unverified"},
    }
    write_json(partial / "edit.json", edit)
    persona = job["labels"]["persona"]
    grown = labels.grow(parents, persona)
    labels.check(grown, parents, persona)
    return {
        "synthetic": grown["synthetic"],
        "labels": grown,
        "measurements": {"layers": sorted(f"layers/{p.name}" for p in layers.iterdir()), "frames": composed["frames"]},
        "timeline": timeline(base["fps"], place_manifest["outputs"]["placements.json"]),
        "states": {"source_checks": "passed", "render": "local", "application_import": "unverified"},
    }
