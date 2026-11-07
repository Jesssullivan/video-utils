"""The campaign look, the third avatar external (docs/spec/NARRATED_VIDEO.md, "Look external", Linear TIN-7788, rulings
TIN-7125 0690fe88, 52ca88bf).

A job selects it with avatar.external "look". avatar.rig names a look record in the private avatars.json. The record
holds the look's anchor digests, the likeness consent it goes through, the renderer that drew its clips and one clip per
voice take, keyed by the narrate run's content digest:

  {id, kind: "look", anchors: [sha256], likenessConsent: {id, ruling}, renderer: {name, version},
   clips: {<narrate content sha256>: {sha256, bytes}}}

This stage draws nothing and calls no engine. The clips come from outside the graph as ProRes 4444 overlays in the
private store. The stage binds the clip of this voice take by digest, checks its codec, alpha, size, rate and frame
count against the take, and writes it with an avatar.manifest/v1. A new take has no clip until its record names one, so
the stage refuses look_clip_missing and never shows a clip over another take's voice.

The record's id and anchors are what a campaign record names, and narrate/video/campaign.py compares them with the
overlay each cut used. Only the Campaign edition takes this external (look_edition_unruled), because the signed campaign
rule approves a look for one campaign and no other job has a campaign go.

Listening and lip sync are lifted for a Campaign job by its signed record, so no person reads what this stage binds.
Whether the look's face moves in time with the voice is not measured here, and the identity check against the anchors is
Cade's (src/campaign-checks.ts)."""

import re
import shutil
from fractions import Fraction

from ..ir import sha256_file
from . import avatar_manifest, face, keys, labels
from .common import StageRefused, ffprobe, upstream, write_json
from .vrm import likeness_problem

EXTERNAL = "look"
EDITIONS = ("Campaign",)
TOOL = {"name": "look-clip", "version": "1", "binary_sha256": None}
# The resolution graph.py reads in place of a binary pin: nothing here spawns or downloads anything.
RESOLUTION = {"state": "resolved", "binary": None, "tool": TOOL, "detail": None}
NARRATION = "narration"
CLIP = "overlay.mov"
CODEC = "prores"
ALPHA_FORMATS = ("yuva444p10le", "yuva444p12le")
HEX64 = re.compile(r"[0-9a-f]{64}")


class LookRefused(StageRefused):
    """The look external refused. verdict as StageRefused."""


def anchors_digest(record):
    """The digest of a look's anchors, whatever order the record lists them in."""
    return keys.digest(sorted(record["anchors"]))


def digest(value):
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def record_problems(record):
    """Shape problems of one avatars.json look record (an empty list when it reads)."""
    problems = []
    anchors = record.get("anchors")
    if not isinstance(anchors, list) or not anchors or not all(digest(a) for a in anchors):
        problems.append("anchors is a non-empty list of 64-hex digests")
    elif len(set(anchors)) != len(anchors):
        problems.append("anchors repeat")
    if not isinstance(record.get("likenessConsent"), dict):
        problems.append("likenessConsent is {id, ruling}")
    renderer = record.get("renderer")
    if not (isinstance(renderer, dict) and all(avatar_manifest.text(renderer.get(k)) for k in ("name", "version"))):
        problems.append("renderer needs a name and a version")
    clips = record.get("clips")
    if not isinstance(clips, dict) or not all(
        digest(take)
        and isinstance(clip, dict)
        and digest(clip.get("sha256"))
        and avatar_manifest.natural(clip.get("bytes"))
        for take, clip in clips.items()
    ):
        problems.append("clips is {narrate content sha256: {sha256, bytes}}")
    return problems


def gates(job, records):
    """[(code, detail)] the look path refuses at admit for this job; empty when every gate holds."""
    out = []
    if job["edition"] not in EDITIONS:
        out.append(("look_edition_unruled", f"a campaign look is ruled only for {', '.join(EDITIONS)}"))
    look_id = job["avatar"].get("rig")
    record = (records.get("avatars") or {}).get(look_id) if look_id else None
    if record is None or record.get("kind") != EXTERNAL:
        out.append(("look_missing", "avatar.rig names no look record in avatars.json"))
        return out
    problems = record_problems(record)
    if problems:
        out.append(("look_invalid", f"look {look_id}: " + "; ".join(problems)))
        return out
    if job["avatar"].get("rigRevisionSha256") not in (None, anchors_digest(record)):
        out.append(("look_digest_mismatch", "avatar.rigRevisionSha256 is not the digest of the look's anchors"))
    code, detail = likeness_problem(record["likenessConsent"], records)
    if code is not None:
        out.append((code.replace("vrm_", "look_"), detail))
    return out


def record_of(job, records):
    return records["avatars"][job["avatar"]["rig"]]


def knobs(job, records):
    """The avatar stage's knobs. The clips key by digest, so a record that adds a take moves this key and no voice's."""
    record = record_of(job, records)
    return {
        "external": EXTERNAL,
        "rig": record["id"],
        "rigRevisionSha256": anchors_digest(record),
        "renderSize": job["avatar"]["renderSize"],
        "persona": job["labels"]["persona"],
        "likenessConsentId": record["likenessConsent"]["id"],
        "renderer": record["renderer"],
        "clipsSha256": keys.digest(record["clips"]),
    }


def recheck_gates(job, records):
    for code, detail in gates(job, records):
        raise LookRefused(code, detail)


def clip_problems(probe, size, fps, frames):
    """What is wrong with a clip as this take's overlay. The stream must be ProRes with alpha at the job's render size
    and the base's rate, one frame per frame of the take, so compose never holds or cuts a face against its voice."""
    video = next((s for s in probe["streams"] if s.get("codec_type") == "video"), {})
    rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"
    problems = []
    if video.get("codec_name") != CODEC or video.get("pix_fmt") not in ALPHA_FORMATS:
        problems.append("the clip is not ProRes 4444 with alpha")
    if (video.get("width"), video.get("height")) != (size, size):
        problems.append(f"the clip is not {size}x{size}")
    if rate == "0/0" or Fraction(rate) != Fraction(fps["num"], fps["den"]):
        problems.append("the clip's rate is not the base's")
    if int(video.get("nb_frames") or 0) != frames:
        problems.append(f"the clip does not hold the take's {frames} frames")
    return problems


def overlay_manifest(record, clip_sha256, frames, fps, size, outputs, consent_ids, voice_ids):
    return {
        "schema": avatar_manifest.SCHEMA_V1,
        "kind": "avatar_overlay",
        "renderer": {"kind": EXTERNAL} | record["renderer"],
        "synthetic": True,
        "consent_ids": consent_ids,
        "voice_ids": voice_ids,
        "rig": {"id": record["id"], "sha256": anchors_digest(record)},
        "rate": fps,
        "size": {"w": size, "h": size},
        "frames": frames,
        "frames_sha256": clip_sha256,
        "frames_identity": "bit_exact",
        "outputs": outputs,
        "timeline": {"mapping": avatar_manifest.MAPPING, "no_time_stretch": False, "clock": avatar_manifest.CLOCK},
        "look": {
            "id": record["id"],
            "anchors": sorted(record["anchors"]),
            "likeness_consent_id": record["likenessConsent"]["id"],
            "clip_sha256": clip_sha256,
        },
    }


def run_avatar_stage(rc, row, partial):
    """The executor's avatar runner for a look: bind this take's clip, inside the job store."""
    from . import kitpip

    recheck_gates(rc.job, rc.records)
    record = record_of(rc.job, rc.records)
    segment = next(s for s in rc.job["segments"] if s["id"] == row["segment"])
    voice, voice_dir = upstream(rc.store, f"voice/{segment['id']}")
    base, _ = upstream(rc.store, "base")
    fps, size = base["measurements"]["fps"], rc.job["avatar"]["renderSize"]
    narrate_run = (voice_dir / NARRATION).resolve()
    kitpip.guard_partial(rc.store, partial, narrate_run)
    manifest, consent_ids, voice_ids = kitpip.narration(narrate_run)
    frames = face.from_narration(narrate_run, manifest, fps)["frames"]
    clip = record["clips"].get(voice["measurements"].get("narrate_content_sha256"))
    if clip is None:
        raise LookRefused("look_clip_missing", f"look {record['id']} holds no clip for this voice take")
    path = rc.env.source(clip["sha256"], "the look clip")
    if path.stat().st_size != clip["bytes"] or sha256_file(path) != clip["sha256"]:
        raise LookRefused("look_clip_mismatch", "the stored clip is not its record's", verdict=False)
    problems = clip_problems(ffprobe(path), size, fps, frames)
    if problems:
        raise LookRefused("look_clip_invalid", "; ".join(problems))
    overlay = partial / "overlay"
    overlay.mkdir(parents=True)
    shutil.copyfile(path, overlay / CLIP)
    outputs = [{"file": CLIP, "sha256": clip["sha256"], "bytes": clip["bytes"]}]
    written = overlay_manifest(record, clip["sha256"], frames, fps, size, outputs, consent_ids, voice_ids)
    write_json(overlay / "manifest.json", written)
    seen, problems = avatar_manifest.verify_dir(overlay, EXTERNAL)
    if problems:
        raise LookRefused("avatar_manifest_invalid", "; ".join(problems))
    likeness = record["likenessConsent"]["id"]
    return {
        "measurements": {
            "frames": frames,
            "frames_sha256": clip["sha256"],
            "frames_identity": "bit_exact",
            "fps": fps,
            "size": {"w": size, "h": size},
            "rig": {"id": record["id"], "sha256": anchors_digest(record)},
            "show_badge": False,
            "renderer": {"kind": EXTERNAL, "name": seen["renderer"]["name"], "version": seen["renderer"]["version"]},
        },
        "labels": {
            "synthetic": True,
            "consent_ids": sorted(set(consent_ids) | {likeness}),
            "voice_ids": voice_ids,
            "persona": rc.job["labels"]["persona"],
        },
        "synthetic": True,
        "timeline": {
            "mapping": avatar_manifest.MAPPING,
            "no_time_stretch": False,
            "stretch_applied": False,
            "fps": fps,
            "total_frames": frames,
            "narration": {"run_id": manifest["run_id"], "content_sha256": manifest["content_sha256"]},
            "output_axis": "overlay frame index / fps on its segment's narration clock; compose places frame 0 "
            "at the segment anchor",
            "source_axis": "none: the clip was drawn outside the graph for this take; no source media is stretched",
        },
        "states": {"source_checks": "passed", "render": "prerendered", "lip_sync": "lifted_by_campaign"},
    }


def run_avatar_check(rc, row, partial):
    """The executor's avatar_check runner for a look: re-hash the overlay under its manifest, keep the clip digest the
    avatar stage bound and the narration's consent ids, and grow the labels."""
    recheck_gates(rc.job, rc.records)
    segment = row["segment"]
    voice, _ = upstream(rc.store, f"voice/{segment}")
    avatar, avatar_dir = upstream(rc.store, f"avatar/{segment}")
    seen, problems = avatar_manifest.verify_dir(avatar_dir / "overlay", EXTERNAL)
    if seen is None or problems:
        raise LookRefused("digest_mismatch", "; ".join(problems))
    if not (seen["synthetic"] and seen["consent_ids"]):
        raise LookRefused("look_unlabelled", "the overlay manifest is not synthetic with consent ids")
    frames_sha256 = avatar["measurements"].get("frames_sha256")
    if seen["frames_sha256"] != frames_sha256:
        raise LookRefused("label_chain_broken", "the stored overlay is not the clip the avatar stage bound")
    if seen["consent_ids"] != labels.of(voice)["consent_ids"]:
        raise LookRefused("label_chain_broken", "the overlay's consent ids are not the narration's")
    persona = rc.job["labels"]["persona"]
    grown = labels.grow([voice, avatar], persona)
    labels.check(grown, [voice, avatar], persona)
    write_json(
        partial / "check.json",
        {
            "verified": True,
            "labelled": True,
            "renderer_kind": EXTERNAL,
            "frames_sha256": frames_sha256,
            "frames_identity": "bit_exact",
            "consent_ids": grown["consent_ids"],
            "likeness_consent_id": record_of(rc.job, rc.records)["likenessConsent"]["id"],
            "avatar_content_sha256": avatar["content_sha256"],
        },
    )
    return {
        "synthetic": True,
        "measurements": {"labelled": True, "frames_sha256": frames_sha256, "frames_identity": "bit_exact"},
        "labels": grown,
        "states": {"source_checks": "passed", "lip_sync": "lifted_by_campaign"},
    }
