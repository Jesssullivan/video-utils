"""The deliver_check stage of lane L6: per-gate states and the delivery gate (docs/spec/NARRATED_VIDEO.md, "Deliver
check").

deliver_check reads the composed video and reports each gate as passed, failed, pending_operator or not_applicable in
deliver_check.json. A failed machine gate is a state, not a refusal: the node is fresh and delivery_gate says what the
cut may be used for. deliver_check refuses only what the spec rules out: an edition refusal at the DeliverCheck point
and a broken label chain.

Machine gates:

- profile: the video is H.264 yuv420p and AAC at 48 kHz, at the profile's size and rate, with the delivery's channel
  count, the frame count compose planned and, with captions.soft, one caption track;
- loudness: the delivered sound (after the AAC encode) is within driftLu of targetLufs, its true peak at or under
  truePeakDbtp. Nothing loudness-normalises it here either;
- flash: at every slide change (a slide run's start and end, each page change inside a run, a hold's start and end)
  the largest jump in mean luma (Y, 8-bit) between adjacent frames, within fadeS plus one frame of the change, is at
  most FLASH_MAX (30%). A jump is |Y1 - Y0| / max(min(Y0, Y1), FLASH_FLOOR_Y): relative to the darker frame, with
  video black (16) as the floor. The 30% limit is the deck seat's gate (design Addendum B); this formula is this
  lane's reading of "the largest mean-luma jump between adjacent frames", not a port of the deck's code;
- captions: the files captions asks for exist, a soft track when soft is set, the personaCue opens the first cue and
  extraNotice ends description.txt when the job sets them.

Operator gates stay pending_operator here and never pass: listening, lip sync (with an avatar), the burned-in badge
decision (vrm_badge_decision, with a VRM overlay: not ruled, SPR-128), and with upload and a bed, the licence PDF
digest and a clear Content ID result. delivery_gate.upload_gates_closed says the machine gates pass, upload is set
and every bed gate is closed (a client edition also needs voiceOnlyListen).
delivery_gate.public_upload_allowed also needs every operator state closed: verified is not accepted (NV-2: internal
until a first listening receipt; an overlay without lip-sync acceptance stays private). deliver_check never closes
listening itself, so it never reports a public upload as allowed.
"""

from ..config import FF, run
from . import admit, labels
from .common import StageRefused, ffprobe, loudness, upstream, work_dir, write_json
from .compose import FLASH_FLOOR_Y, FLASH_MAX, YAVG, page_kind, parse_cues, profile_for, slide_runs
from .graph import selection
from .job import CLIENT_EDITIONS


# Pure parts ------------------------------------------------------------------------------------------------------
def slide_changes(pages):
    """Seconds at which the picture changes because of a slide or a hold: run edges, page changes, hold edges."""
    times = set()
    for span in slide_runs(pages):
        times.update((span["start"], span["end"]))
        times.update(p["startS"] for p in span["pages"][1:])
    for page in pages:
        if page_kind(page) == "hold":
            times.update((page["startS"], page["endS"]))
    return sorted(times)


def jump(y0, y1):
    return abs(y1 - y0) / max(min(y0, y1), FLASH_FLOOR_Y)


def flash_report(yavg, changes, fps, window_s):
    """[{at_s, max_jump, frame}] per change: the largest adjacent-frame jump within window_s of it."""
    rate = fps["num"] / fps["den"]
    out = []
    for at in changes:
        first = max(0, int((at - window_s) * rate) - 1)
        last = min(len(yavg) - 1, int((at + window_s) * rate) + 1)
        best, frame = 0.0, None
        for n in range(first, last):
            value = jump(yavg[n], yavg[n + 1])
            if value > best:
                best, frame = value, n + 1
        out.append({"at_s": round(at, 6), "max_jump": round(best, 4), "frame": frame})
    return out


def state(ok):
    return "passed" if ok else "failed"


def profile_gate(probe, profile, channels, frames, soft):
    """(state, findings) of the delivered file against its profile."""
    v = next((s for s in probe["streams"] if s.get("codec_type") == "video"), {})
    a = next((s for s in probe["streams"] if s.get("codec_type") == "audio"), {})
    subtitles = sum(1 for s in probe["streams"] if s.get("codec_type") == "subtitle")
    rate = v.get("avg_frame_rate") or v.get("r_frame_rate")
    want = {
        "video_codec": ("h264", v.get("codec_name")),
        "pix_fmt": ("yuv420p", v.get("pix_fmt")),
        "size": (f"{profile['size']['w']}x{profile['size']['h']}", f"{v.get('width')}x{v.get('height')}"),
        "fps": (f"{profile['fps']['num']}/{profile['fps']['den']}", rate),
        "frames": (frames, int(v.get("nb_frames") or 0)),
        "audio_codec": ("aac", a.get("codec_name")),
        "audio_rate_hz": (48000, int(a.get("sample_rate") or 0)),
        "audio_channels": ({"Mono": 1, "Stereo": 2}[channels], int(a.get("channels") or 0)),
        "subtitle_tracks": (1 if soft else 0, subtitles),
    }
    findings = {k: {"want": w, "got": g} for k, (w, g) in want.items() if w != g}
    return state(not findings), findings


def loudness_gate(measured, delivery):
    drift = round(measured["integrated_lufs"] - delivery["targetLufs"], 3)
    ok = abs(drift) <= delivery["driftLu"] and measured["true_peak_dbtp"] <= delivery["truePeakDbtp"]
    return state(ok), {"drift_lu": drift} | measured


def captions_gate(job, files, cues, description, subtitles):
    findings = []
    want = job["captions"]
    for name, flag in (("captions.srt", "srt"), ("captions.vtt", "vtt")):
        if want[flag] and name not in files:
            findings.append(f"{name} is missing")
    if want["soft"] and subtitles != 1:
        findings.append("the video holds no soft caption track")
    cue = job["labels"]["personaCue"]
    if cue and not (cues and cues[0][2].split("\n", 1)[0] == cue):
        findings.append("the persona cue does not open the captions")
    notice = job["labels"]["extraNotice"]
    if notice and description.rstrip("\n").rsplit("\n", 1)[-1] != notice:
        findings.append("extraNotice does not end description.txt")
    return state(not findings), findings


def delivery_gate(job, bed, machine, operator):
    machine_ok = all(v == "passed" for v in machine.values() if v != "not_applicable")
    bed_closed = bed is None or (
        bed["licence"]["certifiedPdfSha256"] is not None
        and isinstance(bed["licence"]["contentIdCheck"], dict)
        and "clear" in bed["licence"]["contentIdCheck"]
    )
    listen_ok = bed is None or job["edition"] not in CLIENT_EDITIONS or job["delivery"]["voiceOnlyListen"] is not None
    upload_closed = bool(job["delivery"]["upload"] and machine_ok and bed_closed and listen_ok)
    open_states = sorted(k for k, v in operator.items() if v == "pending_operator")
    return {
        "machine_gates_passed": machine_ok,
        "internal_review_allowed": machine_ok,
        "upload_gates_closed": upload_closed,
        "public_upload_allowed": upload_closed and not open_states,
        "operator_states_open": open_states,
        "note": "public upload, sending and Content ID stay operator actions (the deck playbook's ship step)",
    }


# The stage ------------------------------------------------------------------------------------------------------
def luma_series(video, work):
    """Mean luma (Y, 8-bit) of every frame of video, by FFmpeg signalstats."""
    stats = work / "yavg.txt"
    try:
        run(
            *FF, "-v", "error", "-i", str(video), "-map", "0:v:0",
            "-vf", f"signalstats,metadata=print:key=lavfi.signalstats.YAVG:file={stats.name}", "-f", "null", "-",
            cwd=work,
        )  # fmt: skip
    except RuntimeError as exc:
        raise StageRefused("ffmpeg_failed", str(exc).splitlines()[0][:200], verdict=False) from None
    return [float(m.group(1)) for m in YAVG.finditer(stats.read_text(encoding="utf-8"))]


def leaves_labels(rc):
    """The label set re-derived from the leaves: every segment's voice manifest and every selected avatar's."""
    job, parents = rc.job, []
    for segment in job["segments"]:
        parents.append(upstream(rc.store, f"voice/{segment['id']}")[0])
        if selection("avatar", segment, job)[0]:
            parents.append(upstream(rc.store, f"avatar/{segment['id']}")[0])
    return labels.grow(parents, job["labels"]["persona"]), parents


def edition_at_deliver(job, bed, derived, overlays):
    check = admit.port()
    leaves = {
        "syntheticVoice": derived["synthetic"],
        "avatar": bool(overlays),
        "pip": False,
        "bed": job["music"] is not None,
        "bedCleared": bed is not None
        and check.bed_licence_cleared(bed)
        and job["delivery"]["voiceOnlyListen"] is not None,
    }
    verdict = check.edition_check("DeliverCheck", job["edition"], leaves)
    codes = [check.EDITION_REFUSALS[c] for c in verdict.get("codes", [])]
    if codes:
        raise StageRefused(codes[0], f"edition {job['edition']} at DeliverCheck: {', '.join(codes)}")
    return verdict | {"leaves": leaves}


def vrm_overlays(rc):
    """The segments whose composed overlay a VRM renderer drew (the avatar stage's measured renderer kind)."""
    found = []
    for segment in rc.job["segments"]:
        if selection("avatar", segment, rc.job)[0]:
            measured = upstream(rc.store, f"avatar/{segment['id']}")[0].get("measurements") or {}
            if (measured.get("renderer") or {}).get("kind") == "vrm":
                found.append(segment["id"])
    return found


def run_deliver_check(rc, row, partial):
    job = rc.job
    compose_manifest, compose_dir = upstream(rc.store, "compose")
    composed = compose_manifest["measurements"]
    bed = rc.records["music_beds"].get(job["music"]["bed"]) if job["music"] else None
    derived, leaves = leaves_labels(rc)
    labels.check(compose_manifest["labels"], leaves, job["labels"]["persona"])
    edition = edition_at_deliver(job, bed, derived, composed["overlays"])
    video = compose_dir / "video.mp4"
    probe = ffprobe(video)
    base_fps = upstream(rc.store, "base")[0]["measurements"]["fps"]
    profile = profile_for(job["delivery"]["profile"], base_fps)
    frames = round(composed["length_s"] * profile["fps"]["num"] / profile["fps"]["den"])
    profile_state, profile_findings = profile_gate(
        probe, profile, job["delivery"]["channels"], frames, job["captions"]["soft"]
    )
    loud_state, loud = loudness_gate(loudness(video), job["delivery"])
    pages = (job["slides"] or {}).get("pages") or []
    changes = slide_changes(pages)
    flash = {"max": FLASH_MAX, "changes": []}
    if changes:
        with work_dir(rc.store) as work:
            yavg = luma_series(video, work)
        window = job["slides"]["fadeS"] + profile["fps"]["den"] / profile["fps"]["num"]
        flash["changes"] = flash_report(yavg, changes, profile["fps"], window)
        flash["worst"] = max(c["max_jump"] for c in flash["changes"])
        flash_state = state(flash["worst"] <= FLASH_MAX)
    else:
        flash_state = "not_applicable"
    files = set(compose_manifest["outputs"])
    srt = compose_dir / "captions.srt"
    cues = parse_cues(srt.read_text(encoding="utf-8")) if srt.is_file() else []
    description = (compose_dir / "description.txt").read_text(encoding="utf-8")
    subtitles = sum(1 for s in probe["streams"] if s.get("codec_type") == "subtitle")
    captions_state, caption_findings = captions_gate(job, files, cues, description, subtitles)
    machine = {"profile": profile_state, "loudness": loud_state, "flash": flash_state, "captions": captions_state}
    operator = {
        "listening": "pending_operator",
        "lip_sync": "pending_operator" if composed["overlays"] else "not_applicable",
        "bed_licence_pdf": "not_applicable",
        "bed_content_id": "not_applicable",
    }
    if vrm_overlays(rc):
        operator["vrm_badge_decision"] = "pending_operator"
    if job["delivery"]["upload"] and bed is not None:
        licence = bed["licence"]
        operator["bed_licence_pdf"] = "passed" if licence["certifiedPdfSha256"] else "pending_operator"
        clear = isinstance(licence["contentIdCheck"], dict) and "clear" in licence["contentIdCheck"]
        operator["bed_content_id"] = "passed" if clear else "pending_operator"
    gate = delivery_gate(job, bed, machine, operator)
    report = {
        "kind": "nv_deliver_check",
        "schema_version": 1,
        "gates": machine | operator,
        "profile": {"name": profile["name"], "findings": profile_findings},
        "loudness": loud,
        "flash": flash,
        "captions": {"findings": caption_findings, "cues": len(cues)},
        "edition": edition,
        "labels": derived,
        "delivery_gate": gate,
    }
    write_json(partial / "deliver_check.json", report)
    return {
        "synthetic": derived["synthetic"],
        "labels": compose_manifest["labels"],
        "measurements": {
            "gates": report["gates"],
            "delivery_gate": gate,
            "integrated_lufs": loud["integrated_lufs"],
            "true_peak_dbtp": loud["true_peak_dbtp"],
            "drift_lu": loud["drift_lu"],
            "flash_worst": flash.get("worst"),
        },
        "states": {"source_checks": "passed"} | {k: v for k, v in operator.items() if v != "not_applicable"},
    }
