"""The compose stage of lane L6: picture, overlays, slides, captions and the delivery encode (NARRATED_VIDEO.md,
"Compose").

compose reads the conformed base, the placements, the mix and, per segment, the avatar overlay. It writes:

- video.mp4: H.264 and AAC at the delivery profile (PROFILES), with the captions as a soft mov_text track when
  captions.soft is set, and video.upload.mp4, the same picture and sound without the caption track;
- captions.srt and captions.vtt (as captions.srt and captions.vtt ask), each narrate run's cues shifted to its
  segment's start on the base clock. labels.personaCue, when a job sets one, opens the first cue (KP-15: no visible
  label is required, so none is added otherwise);
- description.txt from a fixed template, with labels.extraNotice as its last line when set, and chapters.json;
- compose.json: the profile, the layer plan (overlay boxes, slide runs, avatar-off spans) and the encode settings.

Layers, bottom to top: the base scaled to the profile, the slide layers, the avatar overlays, and nothing burned in.
captions.burn refuses captions_burn_unsupported in v1 (the design keeps burn off, N5).

Slides (docs/spec/NARRATED_VIDEO.md, "Slides"). Adjacent slide pages form a run. A run fades in over fadeS, crossfades
in place at each page change (the incoming slide fades in over fadeS centred on the change, above the outgoing one,
which stays opaque until the incoming one is), and fades out over fadeS before the run ends. layout Full shows each
slide over the whole frame, and eases each of its fades against what is under it (eased_fade): the frame's mean luma
moves by the same ratio on every frame, so a light slide over a dark base passes the flash gate at the default fadeS.
CardLowerLeft shows it as a card cardWidth of the frame wide (narrower when a tall slide would not fit the frame
height less two margins), marginPx from the left and bottom edges, with linear fades. Under the card the base
frame at the run's end (the next clip's first frame) is held, fading in with the card, and a black layer dims it to
dimTo of its brightness, lifting as the card fades out. A Hold page shows no card and holds the base frame at its
start at full brightness. On a card or still base the picture does not change, so
nothing is held there. This layout was built from the deck seat's description of its slide card (design Addendum B);
no deck code or asset was read or copied.

The avatar overlays (ProRes 4444, straight alpha) are scaled to avatar.width of the frame and placed at their corner,
each from its segment's start. A page listed in avatar.avatarOff hides them for its whole span: they fade out over
avatar.fadeS before it, stay at alpha 0 through it (from its first frame when it starts the program) and fade back in
over fadeS after it. An avatarOff id that names no slide page refuses page_unknown.

Every refusal here is a verdict for the stage key except an FFmpeg failure: slides_exceed_program, page_unknown,
captions_missing, captions_burn_unsupported, overlay_exceeds_base and label_chain_broken.
"""

import json
import math
import re
from fractions import Fraction

from . import labels
from .common import RATE_HZ, StageRefused, ffmpeg, ffprobe, upstream, work_dir, write_json
from .graph import base_kind, selection, slide_sources
from .place import parse_rate, timeline
from .speech import RUN

# The delivery profiles. The deck project's own profiles port in phase 2 (design section 5.2); these are this
# lane's: H.264 High in yuv420p with AAC-LC at 48 kHz. Talk keeps the base's frame rate.
PROFILES = {
    "Web1080p30": {"size": {"w": 1920, "h": 1080}, "fps": {"num": 30, "den": 1}, "crf": 18, "preset": "fast",
                   "audio_kbps": 192},
    "Talk": {"size": {"w": 1920, "h": 1080}, "fps": None, "crf": 16, "preset": "fast", "audio_kbps": 256},
    "Contingency": {"size": {"w": 1280, "h": 720}, "fps": {"num": 30, "den": 1}, "crf": 23, "preset": "veryfast",
                    "audio_kbps": 128},
}  # fmt: skip
VIDEO_CODEC = "h264"
PIX_FMT = "yuv420p"
AUDIO_CODEC = "aac"
EPSILON_S = 1e-3  # two pages are adjacent when one ends within a millisecond of the next one's start
BLACK = "0x000000"
# The flash gate (deliver_check): the largest adjacent-frame mean-luma jump at a slide change, relative to the darker
# frame with video black (Y 16) as the floor, is at most FLASH_MAX. Full slide fades are eased against it.
FLASH_MAX = 0.30
FLASH_FLOOR_Y = 16.0
YAVG = re.compile(r"lavfi\.signalstats\.YAVG=([0-9.]+)")


# Pure parts: tested alone ----------------------------------------------------------------------------------------
def profile_for(name, base_fps):
    """The resolved profile: {name, size, fps, crf, preset, audio_kbps}. Talk takes the base's rate."""
    p = PROFILES[name]
    return p | {"name": name, "fps": p["fps"] or base_fps}


def even(value):
    return max(2, int(round(value / 2)) * 2)


def avatar_box(corner, width, margin, w, h):
    """(x, y, side) of the square avatar box: width of the frame wide, margin pixels from its corner's edges."""
    side = even(width * w)
    x = margin if corner in ("BL", "TL") else w - margin - side
    y = margin if corner in ("TL", "TR") else h - margin - side
    return x, y, side


def card_box(card_width, margin, w, h, slide_w, slide_h):
    """(x, y, cw, ch) of a lower-left slide card at the slide's aspect ratio: cardWidth of the frame wide, or less
    when a tall slide would not fit in the frame height less a margin above and below."""
    cw = even(card_width * w)
    ch = even(cw * slide_h / slide_w)
    room = h - 2 * margin
    if ch > room:
        ch = room - room % 2
        cw = even(ch * slide_w / slide_h)
    return margin, h - margin - ch, cw, ch


def page_kind(page):
    show = page["show"]
    return "slide" if isinstance(show, dict) else show.lower()


def slide_runs(pages):
    """Runs of adjacent slide pages: [{start, end, pages}] in time order."""
    runs = []
    for page in pages:
        if page_kind(page) != "slide":
            continue
        if runs and abs(runs[-1]["end"] - page["startS"]) <= EPSILON_S:
            runs[-1]["pages"].append(page)
            runs[-1]["end"] = page["endS"]
        else:
            runs.append({"start": page["startS"], "end": page["endS"], "pages": [page]})
    return runs


def slide_layers(run, fade):
    """One layer per page of a run: {page, sha256, start, end, fade_in, fade_out}, fades as (start, length) in the
    layer's own seconds. The first page fades in from the run's start and the last fades out to its end. At each
    change inside the run the incoming page starts fade/2 early and fades in over fade above the outgoing page, which
    stays opaque until fade/2 after the change: a crossfade in place."""
    layers, last = [], len(run["pages"]) - 1
    for i, page in enumerate(run["pages"]):
        start = page["startS"] - (fade / 2 if i else 0)
        end = page["endS"] + (fade / 2 if i < last else 0)
        length = end - start
        layers.append(
            {
                "page": page["id"],
                "sha256": page["show"]["slide"]["sha256"],
                "start": round(start, 6),
                "end": round(end, 6),
                "fade_in": (0.0, fade),
                "fade_out": (round(length - fade, 6), fade) if i == last else None,
            }
        )
    return layers


def eased_fade(direction, start, length, y_under, y_over):
    """An alpha fade (direction "in" or "out", over [start, start + length] in the layer's seconds) whose curve moves
    the frame's mean luma geometrically from y_under to y_over, so every frame of the fade changes it by the same
    ratio. A linear alpha ramp puts the whole step on its first frames when the slide is much brighter or darker than
    what is under it. Equal lumas give the linear fade."""
    ratio = max(y_over, FLASH_FLOOR_Y) / max(y_under, FLASH_FLOOR_Y)
    if abs(ratio - 1) < 0.01:
        return f"fade=t={direction}:st={start:.6f}:d={length:.6f}:alpha=1"
    elapsed = f"(T-{start:.6f})" if direction == "in" else f"({start + length:.6f}-T)"
    curve = f"(pow({ratio:.6f},{elapsed}/{length:.6f})-1)/({ratio:.6f}-1)"
    return (
        f"geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':a='alpha(X,Y)*clip({curve},0,1)':"
        f"enable='between(t,{start:.6f},{start + length:.6f})'"
    )


def min_fade_s(y_a, y_b, fps):
    """The shortest fade (whole frames) whose eased curve keeps each frame's luma step at or under FLASH_MAX."""
    ratio = max(y_a, FLASH_FLOOR_Y) / max(y_b, FLASH_FLOOR_Y)
    frames = math.ceil(abs(math.log(ratio)) / math.log(1 + FLASH_MAX))
    return round(frames * fps["den"] / fps["num"], 6)


def avatar_off_spans(pages, off, total_s):
    """Merged [start, end] spans of the pages avatarOff lists, clipped to the program. An id that names no page of
    the job's slides refuses page_unknown: compose never drops one without a word."""
    unknown = sorted(set(off) - {p["id"] for p in pages})
    if unknown:
        raise StageRefused("page_unknown", f"avatar.avatarOff names no slide page: {', '.join(unknown)}")
    spans = sorted((p["startS"], min(p["endS"], total_s)) for p in pages if p["id"] in set(off))
    merged = []
    for start, end in spans:
        if merged and start <= merged[-1][1] + EPSILON_S:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(round(s, 6), round(e, 6)) for s, e in merged if e > s]


def avatar_off_filters(spans, fade, total_s):
    """FFmpeg alpha filters per span: a fade out over the time before the span (up to fade), alpha 0 for the whole
    span, and a fade in over fade after it. A span from the program start has no fade out: its first frame is
    already hidden."""
    out = []
    for start, end in spans:
        if start > 0:
            fade_at = max(0.0, start - fade)
            span = f"between(t,{fade_at:.6f},{start:.6f})"
            out.append(f"fade=t=out:st={fade_at:.6f}:d={start - fade_at:.6f}:alpha=1:enable='{span}'")
        out.append(f"lut=a=0:enable='between(t,{start:.6f},{end:.6f})'")
        if end < total_s:
            out.append(f"fade=t=in:st={end:.6f}:d={fade:.6f}:alpha=1:enable='between(t,{end:.6f},{end + fade:.6f})'")
    return out


def stamp(seconds, sep):
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def parse_stamp(text):
    hms, _, ms = text.strip().replace(",", ".").partition(".")
    parts = [int(x) for x in hms.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return h * 3600 + m * 60 + s + int((ms or "0")[:3].ljust(3, "0")) / 1000


def parse_cues(text):
    """[(start_s, end_s, text)] from SRT or WebVTT text. NOTE blocks and the WEBVTT header are skipped."""
    cues = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        lines = [line for line in block.split("\n") if line.strip()]
        timing = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing is None:
            continue
        a, _, b = lines[timing].partition("-->")
        cues.append((parse_stamp(a), parse_stamp(b.split()[0]), "\n".join(lines[timing + 1 :])))
    return cues


def shift(cues, offset):
    return [(round(a + offset, 3), round(b + offset, 3), t) for a, b, t in cues]


def open_with_cue(cues, persona_cue):
    """The cues with labels.personaCue on its own line above the first cue's text, when the job sets one."""
    if not persona_cue or not cues:
        return cues
    a, b, text = cues[0]
    return [(a, b, f"{persona_cue}\n{text}")] + cues[1:]


def srt(cues):
    return "".join(f"{i}\n{stamp(a, ',')} --> {stamp(b, ',')}\n{t}\n\n" for i, (a, b, t) in enumerate(cues, 1))


def vtt(cues):
    return "WEBVTT\n\n" + "".join(f"{stamp(a, '.')} --> {stamp(b, '.')}\n{t}\n\n" for a, b, t in cues)


def clock(seconds):
    whole = int(seconds)
    h, rest = divmod(whole, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def chapters_for(job, placements):
    """[{start_s, title}]: one per page when the job has slide pages, else one per segment. Titles are ids."""
    pages = (job["slides"] or {}).get("pages") or []
    rows = [{"start_s": p["startS"], "title": p["id"]} for p in pages]
    if not rows:
        rows = [{"start_s": s["start_s"], "title": s["id"]} for s in placements["segments"]]
    if rows and rows[0]["start_s"] > 0:
        rows.insert(0, {"start_s": 0.0, "title": "start"})
    return rows


def description(job, length_s, chapters):
    """description.txt from a fixed template. KP-15: no synthetic label is required; extraNotice is kept when set."""
    lines = [job["id"], f"Length {clock(length_s)}. Narrated in {len(job['segments'])} segment(s).", "", "Chapters"]
    lines += [f"{clock(c['start_s'])} {c['title']}" for c in chapters]
    if job["labels"]["extraNotice"]:
        lines += ["", job["labels"]["extraNotice"]]
    return "\n".join(lines) + "\n"


# The stage ------------------------------------------------------------------------------------------------------
def captions(rc, placements, work):
    """The job's cues on the base clock, read from each segment's narrate run (narration.srt, else .vtt)."""
    cues = []
    for segment in placements["segments"]:
        _, voice_dir = upstream(rc.store, f"voice/{segment['id']}")
        run = voice_dir / RUN
        source = next((run / n for n in ("narration.srt", "narration.vtt") if (run / n).is_file()), None)
        if source is None:
            continue
        cues += shift(parse_cues(source.read_text(encoding="utf-8")), segment["start_s"])
    return open_with_cue(sorted(cues), rc.job["labels"]["personaCue"])


def conform(w, h):
    return f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"


def last_frame_s(base):
    return float((base["frames"] - 1) * Fraction(base["fps"]["den"], base["fps"]["num"]))


def held_frame(base_mp4, at_s, base, target):
    """One frame of the conformed base video at at_s (clamped to its last frame), as a PNG."""
    ffmpeg("-ss", f"{min(at_s, last_frame_s(base)):.6f}", "-i", str(base_mp4), "-frames:v", "1", "-update", "1",
           str(target))  # fmt: skip
    return target


def mean_luma(source, w, h, at_s=None):
    """Mean luma (Y, 8-bit) of one picture conformed to w x h in yuv420p: a still, or a video's frame at at_s."""
    seek = ["-ss", f"{at_s:.6f}"] if at_s is not None else []
    done = ffmpeg(
        *seek, "-i", str(source), "-frames:v", "1",
        "-vf", f"{conform(w, h)},format={PIX_FMT},signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
        "-f", "null", "-",
    )  # fmt: skip
    found = YAVG.search(done.stdout)
    if not found:
        raise StageRefused("ffmpeg_failed", f"no mean luma measured for {source.name}", verdict=False)
    return float(found.group(1))


def run_compose(rc, row, partial):
    job = rc.job
    base_manifest, base_dir = upstream(rc.store, "base")
    place_manifest, place_dir = upstream(rc.store, "place")
    mix_manifest, mix_dir = upstream(rc.store, "mix")
    base = json.loads((base_dir / "base.json").read_text(encoding="utf-8"))
    placements = json.loads((place_dir / "placements.json").read_text(encoding="utf-8"))
    total = mix_manifest["measurements"]["total_samples"]
    total_s = total / RATE_HZ
    profile = profile_for(job["delivery"]["profile"], base["fps"])
    w, h, fps = profile["size"]["w"], profile["size"]["h"], profile["fps"]
    rate = Fraction(fps["num"], fps["den"])
    frames = max(1, round(Fraction(total, RATE_HZ) * rate))
    frame_s = float(1 / rate)
    if job["captions"]["burn"]:
        raise StageRefused("captions_burn_unsupported", "v1 composes soft captions only; set captions.burn False")
    slides = job["slides"]
    pages = (slides or {}).get("pages") or []
    if pages and pages[-1]["endS"] > total_s + frame_s:
        raise StageRefused(
            "slides_exceed_program", f"the last page ends {pages[-1]['endS'] - total_s:.3f} s after the program"
        )
    avatar_nodes = [s for s in job["segments"] if selection("avatar", s, job)[0]]
    parents = [base_manifest, place_manifest, mix_manifest]
    inputs, chain = [], []

    def add_input(*args):
        inputs.extend(args)
        return sum(1 for a in inputs if a == "-i") - 1

    kind, _ = base_kind(job)
    picture = base_dir / base["picture"]
    if base["picture"] == "base.png":
        idx = add_input("-loop", "1", "-framerate", f"{fps['num']}/{fps['den']}", "-i", str(picture))
        chain.append(f"[{idx}:v]{conform(w, h)},fps={fps['num']}/{fps['den']},format={PIX_FMT}[v0]")
    else:
        idx = add_input("-i", str(picture))
        chain.append(
            f"[{idx}:v]{conform(w, h)},fps={fps['num']}/{fps['den']},"
            f"tpad=stop_mode=clone:stop_duration=1,format={PIX_FMT}[v0]"
        )
    layer = 0
    plan = {"slides": None, "overlays": [], "avatar_off": []}

    def overlay(source, x="0", y="0"):
        nonlocal layer
        chain.append(f"[v{layer}][{source}]overlay=x={x}:y={y}:eof_action=pass:repeatlast=0:format=auto[v{layer + 1}]")
        layer += 1

    def timed(label, start):
        return f"setpts=PTS-STARTPTS+{start:.6f}/TB[{label}]"

    with work_dir(rc.store) as work:
        moving = base["picture"] == "base.mp4"
        if slides is not None:
            fade = slides["fadeS"]
            card = slides["layout"] == "CardLowerLeft"
            runs = slide_runs(pages)
            sources = {page: rc.env.source(digest, f"slide {page}") for page, digest in slide_sources(job)}
            plan["slides"] = {"layout": slides["layout"], "runs": [], "holds": []}
            still_y = None if moving else mean_luma(picture, w, h)

            def base_y(at_s):
                return mean_luma(picture, w, h, min(at_s, last_frame_s(base))) if moving else still_y

            for k, page in enumerate(p for p in pages if page_kind(p) == "hold"):
                if not moving:
                    continue
                still = held_frame(picture, page["startS"], base, work / f"hold-{k}.png")
                length = page["endS"] - page["startS"]
                idx = add_input("-loop", "1", "-framerate", f"{fps['num']}/{fps['den']}", "-t", f"{length:.6f}",
                                "-i", str(still))  # fmt: skip
                chain.append(f"[{idx}:v]{conform(w, h)},format=yuva420p,{timed(f'h{k}', page['startS'])}")
                overlay(f"h{k}")
                plan["slides"]["holds"].append({"page": page["id"], "start_s": page["startS"], "end_s": page["endS"]})
            for r, run in enumerate(runs):
                length = run["end"] - run["start"]
                record = {"start_s": run["start"], "end_s": run["end"], "pages": [p["id"] for p in run["pages"]]}
                if card:
                    if moving:
                        still = held_frame(picture, run["end"], base, work / f"held-{r}.png")
                        idx = add_input("-loop", "1", "-framerate", f"{fps['num']}/{fps['den']}",
                                        "-t", f"{length:.6f}", "-i", str(still))  # fmt: skip
                        chain.append(
                            f"[{idx}:v]{conform(w, h)},format=yuva420p,fade=t=in:st=0:d={fade}:alpha=1,"
                            + timed(f"held{r}", run["start"])
                        )
                        overlay(f"held{r}")
                    chain.append(
                        f"color=c=black@{1 - slides['dimTo']:.4f}:s={w}x{h}:r={fps['num']}/{fps['den']}:"
                        f"d={length:.6f},format=yuva420p,fade=t=in:st=0:d={fade}:alpha=1,"
                        f"fade=t=out:st={length - fade:.6f}:d={fade}:alpha=1," + timed(f"dim{r}", run["start"])
                    )
                    overlay(f"dim{r}")
                    record["held"] = "base frame at the run's end" if moving else "static base"
                    record["dim_to"] = slides["dimTo"]
                record["layers"] = []
                under_y = None if card else base_y(run["start"])
                for j, spec in enumerate(slide_layers(run, fade)):
                    source = sources[spec["page"]]
                    info = next(s for s in ffprobe(source)["streams"] if s.get("codec_type") == "video")
                    length_j = spec["end"] - spec["start"]
                    idx = add_input("-loop", "1", "-framerate", f"{fps['num']}/{fps['den']}",
                                    "-t", f"{length_j:.6f}", "-i", str(source))  # fmt: skip
                    if card:
                        x, y, cw, ch = card_box(slides["cardWidth"], slides["marginPx"], w, h,
                                                int(info["width"]), int(info["height"]))  # fmt: skip
                        fit = f"scale={cw}:{ch},setsar=1"
                    else:
                        x, y, cw, ch = 0, 0, w, h
                        fit = conform(w, h)
                    if card:
                        fades = f"fade=t=in:st={spec['fade_in'][0]}:d={spec['fade_in'][1]}:alpha=1"
                        if spec["fade_out"]:
                            fades += f",fade=t=out:st={spec['fade_out'][0]:.6f}:d={spec['fade_out'][1]}:alpha=1"
                    else:
                        # Full: each fade is eased against what is under it (the base, or the outgoing slide).
                        over_y = mean_luma(source, w, h)
                        fades = eased_fade("in", *spec["fade_in"], under_y, over_y)
                        spec["ease"] = {"in": {"under_y": under_y, "over_y": over_y,
                                               "min_fade_s": min_fade_s(under_y, over_y, fps)}}  # fmt: skip
                        if spec["fade_out"]:
                            end_y = base_y(run["end"])
                            fades += "," + eased_fade("out", *spec["fade_out"], end_y, over_y)
                            spec["ease"]["out"] = {"under_y": end_y, "over_y": over_y,
                                                   "min_fade_s": min_fade_s(end_y, over_y, fps)}  # fmt: skip
                        under_y = over_y
                    label = f"s{r}_{j}"
                    chain.append(f"[{idx}:v]{fit},format=yuva420p,{fades},{timed(label, spec['start'])}")
                    overlay(label, str(x), str(y))
                    record["layers"].append(spec | {"box": {"x": x, "y": y, "w": cw, "h": ch}})
                plan["slides"]["runs"].append(record)
        spans = []
        if job["avatar"] is not None:
            avatar = job["avatar"]
            ax, ay, side = avatar_box(avatar["corner"], avatar["width"], avatar["marginPx"], w, h)
            spans = avatar_off_spans(pages, avatar["avatarOff"], total_s)
            plan["avatar_off"] = [{"start_s": s, "end_s": e, "fade_s": avatar["fadeS"]} for s, e in spans]
            offs = avatar_off_filters(spans, avatar["fadeS"], total_s)
            starts = {s["id"]: s["start_s"] for s in placements["segments"]}
            for segment in avatar_nodes:
                node = f"avatar/{segment['id']}"
                manifest, directory = upstream(rc.store, node)
                check_manifest, _ = upstream(rc.store, f"avatar_check/{segment['id']}")
                parents += [manifest, check_manifest]
                mov = directory / "overlay" / "overlay.mov"
                if not mov.is_file():
                    raise StageRefused("overlay_missing", f"{node} holds no overlay/overlay.mov", verdict=False)
                ov_frames = manifest["measurements"]["frames"]
                ov_fps = manifest["measurements"]["fps"]
                ov_end = starts[segment["id"]] + ov_frames * ov_fps["den"] / ov_fps["num"]
                if ov_end > total_s + frame_s:
                    raise StageRefused("overlay_exceeds_base", f"{node} ends {ov_end - total_s:.3f} s after the base")
                idx = add_input("-i", str(mov))
                label = f"a{segment['id'].replace('-', '_').replace('.', '_')}"
                filters = [f"fps={fps['num']}/{fps['den']}", f"scale={side}:{side}", "format=yuva420p"]
                chain.append(
                    f"[{idx}:v]" + ",".join(filters) + f",setpts=PTS-STARTPTS+{starts[segment['id']]:.6f}/TB"
                    + ("," + ",".join(offs) if offs else "") + f"[{label}]"
                )  # fmt: skip
                overlay(label, str(ax), str(ay))
                plan["overlays"].append(
                    {"segment": segment["id"], "start_s": starts[segment["id"]], "frames": ov_frames,
                     "box": {"x": ax, "y": ay, "w": side, "h": side}, "corner": avatar["corner"]}
                )  # fmt: skip
        chain.append(f"[v{layer}]format={PIX_FMT}[vout]")
        cues = captions(rc, placements, work)
        want = job["captions"]
        if (want["srt"] or want["vtt"] or want["soft"]) and not cues:
            raise StageRefused("captions_missing", "the narrate runs wrote no SRT or VTT captions")
        if want["srt"]:
            (partial / "captions.srt").write_text(srt(cues), encoding="utf-8")
        if want["vtt"]:
            (partial / "captions.vtt").write_text(vtt(cues), encoding="utf-8")
        audio_idx = add_input("-i", str(mix_dir / "mix.wav"))
        maps = ["-map", "[vout]", "-map", f"{audio_idx}:a"]
        subtitle = []
        if want["soft"]:
            soft = work / "soft.srt"
            soft.write_text(srt(cues), encoding="utf-8")
            sub_idx = add_input("-i", str(soft))
            maps += ["-map", f"{sub_idx}:s"]
            subtitle = ["-c:s", "mov_text", "-metadata:s:s:0", "language=und"]
        encode = [
            "-frames:v", str(frames), "-r", f"{fps['num']}/{fps['den']}",
            "-c:v", "libx264", "-preset", profile["preset"], "-crf", str(profile["crf"]), "-profile:v", "high",
            "-pix_fmt", PIX_FMT, "-threads", "2",
            "-c:a", AUDIO_CODEC, "-b:a", f"{profile['audio_kbps']}k", "-ar", str(RATE_HZ),
            *subtitle, "-movflags", "+faststart", "-map_metadata", "-1",
            "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
        ]  # fmt: skip
        graph = ";".join(chain)
        ffmpeg(*inputs, "-filter_complex", graph, *maps, *encode, str(partial / "video.mp4"))
    ffmpeg(
        "-i", str(partial / "video.mp4"), "-map", "0:v", "-map", "0:a", "-c", "copy", "-movflags", "+faststart",
        "-map_metadata", "-1", "-fflags", "+bitexact", str(partial / "video.upload.mp4"),
    )  # fmt: skip
    chapters = chapters_for(job, placements)
    write_json(partial / "chapters.json", {"chapters": chapters})
    (partial / "description.txt").write_text(description(job, total_s, chapters), encoding="utf-8")
    probe = ffprobe(partial / "video.mp4")
    v = next(s for s in probe["streams"] if s.get("codec_type") == "video")
    a = next(s for s in probe["streams"] if s.get("codec_type") == "audio")
    measured = {
        "profile": profile["name"],
        "size": {"w": int(v["width"]), "h": int(v["height"])},
        "fps": parse_rate(v.get("avg_frame_rate"), v.get("r_frame_rate")),
        "frames": int(v.get("nb_frames") or 0),
        "length_s": round(total_s, 6),
        "video_codec": v.get("codec_name"),
        "pix_fmt": v.get("pix_fmt"),
        "audio_codec": a.get("codec_name"),
        "audio_rate_hz": int(a.get("sample_rate") or 0),
        "audio_channels": int(a.get("channels") or 0),
        "subtitle_tracks": sum(1 for s in probe["streams"] if s.get("codec_type") == "subtitle"),
        "cues": len(cues),
        "overlays": plan["overlays"],
        "slides": plan["slides"],
        "avatar_off": plan["avatar_off"],
        "kind": kind,
    }
    write_json(partial / "compose.json", measured | {"filter": graph, "encode": encode})
    if measured["frames"] != frames:
        raise StageRefused("frames_mismatch", f"the encode holds {measured['frames']} frames, not {frames}")
    persona = job["labels"]["persona"]
    grown = labels.grow(parents, persona)
    labels.check(grown, parents, persona)
    states = {"source_checks": "passed", "render": "local", "listening": "pending_operator"}
    if plan["overlays"]:
        states["lip_sync"] = "pending_operator"
    return {
        "synthetic": grown["synthetic"],
        "labels": grown,
        "measurements": measured,
        "timeline": timeline(base["fps"], place_manifest["outputs"]["placements.json"]),
        "states": states,
    }
