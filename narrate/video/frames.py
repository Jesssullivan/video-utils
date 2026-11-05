"""The frame gates of a narrated video (docs/spec/NARRATED_VIDEO.md, "Frame gates", Linear TIN-7788).

deliver_check's first four machine gates read sound, captions, the profile and flash. None looks at what a frame
shows, so a cut passed them with its frame findings open (TIN-7788 eecee03c, 845695a5). This module reads frames, in
two places:

- preflight, before any voice spend: the pictures a job will show, from the private store;
- deliver_check, on the composed video: the same reading plus the frames of the final artifact.

avatar_box. A flat picture keeps everything out of the avatar's box plus BOX_GUARD_PX on each side. Each page the
avatar is on reads its slide (tolerance LAYER_TOL) or its base (one still, or a video sampled at BASE_SAMPLE_FPS). In
deliver_check, the frame at each such page's midpoint also counts pixels off its background outside the overlay's own
alpha, dilated by ALPHA_DILATE_PX for scaling and chroma bleed (tolerance FRAME_TOL, the H.264 margin).

A picture is flat when at least FLAT_SHARE of it sits within LAYER_TOL of its modal colour. A picture that is not
flat has no background to measure against, so a page is checked only when every sample of it was flat: one unflat
sample leaves the page unchecked, and a finding in its flat samples still counts. The composed frame adds to that
reading and never replaces it, except on a card page, whose held base is one frozen frame that a single midpoint reads.

An unchecked page does not fail the gate, and a gate with no checked page reads not_applicable, so passed speaks only
for the checked pages. A page in avatar.boxExempt (a bundle asset that declares avatar_box exempt) is listed as exempt
and not read: a render whose model edge reaches the box, with no text there. A job with no pages holds its segment ids
there, and its one program page is exempt when every segment the avatar is on is. deliver_check's measurements repeat
both lists as frame_review, which nv cut and the render stage result print, so a person reads those pages before a GO.

slide_match. The cut shows the slides the bundle binds. Before any voice spend, the store still holds a file that
hashes to each slide's digest, a Full slide fills the frame (a strip wider than STRIP_PX refuses slide_letterbox), and
the job's pages agree with the rows of the intake that wrote it. A slide that changed or left the store is
slide_digest_mismatch whichever way it went: a store's index is keyed by content, so a changed file is one the index
no longer finds. In deliver_check, compose's layers must be the job's pages, and at each slide page's midpoint the
composed frame must match the slide: at most SLIDE_MISMATCH_MAX of its pixels may differ by more than SLIDE_TOL in a
channel, with the overlay's square left out while the avatar covers it.

Whether a slide draws the numbers its beat speaks stays with the producer (its shown record and demo check). This
module compares pixels with pixels and reads no claim. A report holds page ids, counts and digests, never a path or a
text.
"""

from collections import Counter

from ..config import FF, run
from ..ir import sha256_file
from . import keys
from .common import StageRefused, ffprobe, upstream
from .compose import PROFILES, avatar_box, card_box, conform, page_kind
from .graph import base_kind, slide_sources

KIND = "nv_preflight"
SCHEMA_VERSION = 1
BOX_GUARD_PX = 16
LAYER_TOL = 8  # per RGB channel, on a lossless picture
FRAME_TOL = 32  # per RGB channel, on an H.264 frame
ALPHA_DILATE_PX = 4
FLAT_SHARE = 0.5
BASE_SAMPLE_FPS = 2
MAX_SAMPLES = 400  # a longer span samples more slowly, so a long base holds no more than this many crops in memory
VIEW_W, VIEW_H = 160, 90  # the small view that gives a picture's background
SLIDE_TOL = 32
SLIDE_MISMATCH_MAX = 0.005
STRIP_PX = 2
TOOL_TIMEOUT_S = 300
PROGRAM = "program"  # the label of the one page of a job with no pages


# Pure parts: tested alone ----------------------------------------------------------------------------------------
def guarded_box(avatar, w, h):
    """{x, y, w, h} of the avatar's box plus BOX_GUARD_PX, clamped to the frame."""
    x, y, side = avatar_box(avatar["corner"], avatar["width"], avatar["marginPx"], w, h)
    x0, y0 = max(0, x - BOX_GUARD_PX), max(0, y - BOX_GUARD_PX)
    x1, y1 = min(w, x + side + BOX_GUARD_PX), min(h, y + side + BOX_GUARD_PX)
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def modal(rgb):
    return Counter(zip(rgb[0::3], rgb[1::3], rgb[2::3], strict=True)).most_common(1)[0][0]


def off_mask(rgb, colour, tol):
    """One byte per pixel: 1 when any channel is more than tol from colour. Runs at C speed: a frame is 2 million
    pixels and deliver_check reads one per page."""
    merged = 0
    for channel, value in enumerate(colour):
        table = bytes(1 if abs(v - value) > tol else 0 for v in range(256))
        merged |= int.from_bytes(rgb[channel::3].translate(table), "big")
    return merged.to_bytes(len(rgb) // 3, "big")


def flat_colour(view):
    """The modal colour of a small view when the picture is flat, else None."""
    colour = modal(view)
    pixels = len(view) // 3
    return colour if pixels - off_mask(view, colour, LAYER_TOL).count(1) >= FLAT_SHARE * pixels else None


def extent(mask, width, x0=0, y0=0):
    """{x0, y0, x1, y1}, inclusive and in frame pixels, of the 1s of a width-wide mask, or None."""
    rows = [y for y in range(len(mask) // width) if 1 in mask[y * width : (y + 1) * width]]
    if not rows:
        return None
    left = min(mask.find(1, y * width, (y + 1) * width) - y * width for y in rows)
    right = max(mask.rfind(1, y * width, (y + 1) * width) - y * width for y in rows)
    return {"x0": x0 + left, "y0": y0 + rows[0], "x1": x0 + right, "y1": y0 + rows[-1]}


def worst_off(samples, box, tol):
    """(flat samples, {pixels, extent} of the worst one or None) over [(view, crop)]. A sample's own background
    counts, so a slide that changes colour is not read against another sample's."""
    flat, worst = 0, None
    for view, crop in samples:
        colour = flat_colour(view)
        if colour is None:
            continue
        flat += 1
        mask = off_mask(crop, colour, tol)
        pixels = mask.count(1)
        if pixels and (worst is None or pixels > worst["pixels"]):
            worst = {"pixels": pixels, "extent": extent(mask, box["w"], box["x"], box["y"])}
    return flat, worst


def alpha_mask(alpha, side, offset_x, offset_y, width, height):
    """A width by height mask holding the overlay's non-zero alpha, side pixels square, at the offset. Rows and
    columns outside the crop are cut."""
    table = bytes([0] + [1] * 255)
    solid = alpha.translate(table)
    out = bytearray(width * height)
    left, right = max(0, -offset_x), min(side, width - offset_x)
    for y in range(max(0, -offset_y), min(side, height - offset_y)):
        at = (y + offset_y) * width + offset_x
        out[at + left : at + right] = solid[y * side + left : y * side + right]
    return bytes(out)


def minus(mask, other):
    """The 1s of mask that other does not cover."""
    kept = int.from_bytes(mask, "big") & ~int.from_bytes(other, "big")
    return kept.to_bytes(len(mask), "big")


def rect_mask(rect, width, height):
    """A width by height mask of 1s over rect (x, y, w, h), which may run outside it."""
    x, y, w, h = rect
    x0, x1 = max(0, x), min(width, x + w)
    out = bytearray(width * height)
    for row in range(max(0, y), min(height, y + h)):
        out[row * width + x0 : row * width + x1] = b"\x01" * max(0, x1 - x0)
    return bytes(out)


def overlaps(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def strip_px(slide_w, slide_h, w, h):
    """The black strip, in frame pixels, a Full slide of this size leaves after the fit that compose uses."""
    scale = min(w / slide_w, h / slide_h)
    return max(w - round(slide_w * scale), h - round(slide_h * scale))


def state(checked, findings):
    if findings:
        return "failed"
    return "passed" if checked else "not_applicable"


def visible_pages(job):
    """The pages the avatar is on: every page but an avatarOff one or one whose segment hides it. A job with no pages
    is one page, id None, over its base. Empty without an avatar."""
    avatar = job["avatar"]
    if avatar is None or not any(s["avatar"] for s in job["segments"]):
        return []
    pages = (job["slides"] or {}).get("pages") or [{"id": None, "startS": None, "endS": None, "show": "Base"}]
    hidden = set(avatar["avatarOff"]) | {s["id"] for s in job["segments"] if not s["avatar"]}
    return [p for p in pages if p["id"] not in hidden]


def box_exempt(job):
    """The ids avatar.boxExempt lists. A job written before the field holds none."""
    return set((job["avatar"] or {}).get("boxExempt") or ())


def page_exempt(job, label):
    """True when avatar.boxExempt covers this page. A job with no pages lists segments, so its program page needs all
    of the segments the avatar is on."""
    if label != PROGRAM:
        return label in box_exempt(job)
    return all(s["id"] in box_exempt(job) for s in job["segments"] if s["avatar"])


# Decoding --------------------------------------------------------------------------------------------------------
def raw(inputs, filters, *, limit=None, pixel="rgb24"):
    """The decoded pictures of one FFmpeg call as bytes. A crash is a failure a retry may clear, not a verdict."""
    frames = ["-frames:v", str(limit)] if limit else []
    try:
        done = run(
            *FF, "-v", "error", *inputs, "-map", "0:v:0", "-vf", filters, *frames,
            "-f", "rawvideo", "-pix_fmt", pixel, "-", input=b"", timeout=TOOL_TIMEOUT_S,
        )  # fmt: skip
    except RuntimeError as exc:
        raise StageRefused("ffmpeg_failed", str(exc).splitlines()[0][:200], verdict=False) from None
    return done.stdout


def box_samples(source, w, h, box, *, at_s=None, span=None):
    """[(view, crop)] of a picture fitted to the frame as compose fits it: a small view for its background and the
    box at full size. at_s reads one frame. span (start, length) samples a video at BASE_SAMPLE_FPS, or slower when
    the span would pass MAX_SAMPLES. With neither, FFmpeg reads the one frame of a still."""
    inputs, pre, limit = [], "", 1
    if at_s is not None:
        inputs = ["-ss", f"{at_s:.6f}"]
    if span is not None:
        inputs, limit = ["-ss", f"{span[0]:.6f}", "-t", f"{span[1]:.6f}"], None
        pre = f"fps={min(BASE_SAMPLE_FPS, MAX_SAMPLES / span[1]):.6f},"
    inputs += ["-i", str(source)]
    fit = pre + conform(w, h)
    views = raw(inputs, f"{fit},scale={VIEW_W}:{VIEW_H}:flags=neighbor", limit=limit)
    crops = raw(inputs, f"{fit},crop={box['w']}:{box['h']}:{box['x']}:{box['y']}", limit=limit)
    view_size, crop_size = VIEW_W * VIEW_H * 3, box["w"] * box["h"] * 3
    count = min(len(views) // view_size, len(crops) // crop_size)
    return [
        (views[n * view_size : (n + 1) * view_size], crops[n * crop_size : (n + 1) * crop_size]) for n in range(count)
    ]


def picture_size(source):
    info = next(s for s in ffprobe(source)["streams"] if s.get("codec_type") == "video")
    return int(info["width"]), int(info["height"])


def slide_file(env, digest):
    """The store file that hashes to digest now, or None. env.index is keyed by content when Env is built, so a file
    changed before that is simply absent, and the re-hash catches one changed after it."""
    path = env.index.get(digest)
    return path if path is not None and sha256_file(path) == digest else None


# What a job will show --------------------------------------------------------------------------------------------
def base_samples(job, env, page, w, h, box):
    """(samples, lossless) of the base under a page, or None for a base this module cannot read before it is built.
    A colour card is uniform, so it has no samples and its page counts as clear."""
    kind, body = base_kind(job)
    if kind == "card":
        return [], True
    if kind == "still":
        return box_samples(env.source(body["sha256"], "the base still"), w, h, box), True
    if kind == "video":
        source = env.source(body["sha256"], "the base video")
        if page_kind(page) == "hold":
            return box_samples(source, w, h, box, at_s=page["startS"]), False
        start = page["startS"] or 0
        end = float(ffprobe(source)["format"]["duration"]) if page["endS"] is None else page["endS"]
        return box_samples(source, w, h, box, span=(start, end - start)), False
    return None


def avatar_box_gate(job, env, w, h):
    """The avatar_box report of the pictures a job shows, read from the private store."""
    avatar = job["avatar"]
    pages = visible_pages(job)
    if not pages:
        return {"state": "not_applicable", "checked": [], "exempt": [], "unchecked": [], "held": [], "findings": []}
    box = guarded_box(avatar, w, h)
    rect = (box["x"], box["y"], box["w"], box["h"])
    slides = job["slides"] or {}
    report = {"box": box, "checked": [], "exempt": [], "unchecked": [], "held": [], "findings": []}
    for page in pages:
        label = page["id"] or PROGRAM
        if page_exempt(job, label):
            report["exempt"].append(label)
            continue
        if page_kind(page) == "slide":
            source = slide_file(env, page["show"]["slide"]["sha256"])
            if source is None:  # slide_gate reports it
                report["unchecked"].append(label)
                continue
            if slides["layout"] == "CardLowerLeft":
                card = card_box(slides["cardWidth"], slides["marginPx"], w, h, *picture_size(source))
                if overlaps(card, rect):
                    report["findings"].append({"code": "card_in_avatar_box", "page": label})
                report["unchecked"].append(label)  # the held base under the card is not read until it is composed
                report["held"].append(label)
                continue
            samples, lossless = box_samples(source, w, h, box), True
        else:
            read = base_samples(job, env, page, w, h, box)
            if read is None:
                report["unchecked"].append(label)
                continue
            samples, lossless = read
        if not samples and base_kind(job)[0] == "card" and page_kind(page) != "slide":
            report["checked"].append(label)
            continue
        flat, worst = worst_off(samples, box, LAYER_TOL if lossless else FRAME_TOL)
        report["checked" if samples and flat == len(samples) else "unchecked"].append(label)
        if worst:
            report["findings"].append({"code": "avatar_box_occupied", "page": label, "source": "layer"} | worst)
    return report | {"state": state(report["checked"], report["findings"])}


def slide_gate(job, env, w, h, intake=None):
    """The slide_match report before anything renders: the store still holds each slide, a Full slide fills the frame
    and each page agrees with its row in the intake that wrote the job, when one did. That row and the page come from
    the same beats, so this catches an intake.json edited after it was written, not a wrong citation in a bundle."""
    slides = job["slides"]
    if slides is None:
        return {"state": "not_applicable", "checked": [], "findings": []}
    report = {"checked": [], "findings": []}
    for page_id, digest in slide_sources(job):
        source = slide_file(env, digest)
        if source is None:
            report["findings"].append({"code": "slide_digest_mismatch", "page": page_id})
            continue
        report["checked"].append(page_id)
        if slides["layout"] == "Full":
            strip = strip_px(*picture_size(source), w, h)
            if strip > STRIP_PX:
                report["findings"].append({"code": "slide_letterbox", "page": page_id, "strip_px": strip})
    if intake is not None:
        pages = {p["id"]: p for p in slides["pages"]}
        for row in intake["segments"]:
            page = pages.get(row["segment"])
            shown = page["show"]["slide"]["sha256"] if page and page_kind(page) == "slide" else None
            if shown != (row["asset"]["sha256"] if row["show"] == "slide" else None):
                report["findings"].append({"code": "slide_page_mismatch", "page": row["segment"]})
    return report | {"state": state(report["checked"], report["findings"])}


def preflight(job, env, intake=None):
    """The nv_preflight report: the frame gates a job can pass or fail before any voice spend, and the claims state
    of the intake that wrote it. No voice is read and nothing renders."""
    size = PROFILES[job["delivery"]["profile"]]["size"]
    w, h = size["w"], size["h"]
    avatar, slides = avatar_box_gate(job, env, w, h), slide_gate(job, env, w, h, intake)
    claims = None if intake is None else (intake.get("states") or {}).get("claims")
    findings = avatar["findings"] + slides["findings"]
    if intake is not None and claims != "passed":
        findings = [{"code": "claims_not_passed", "page": None}] + findings
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "job_id": job["id"],
        "job_sha256": keys.digest(job),
        "ok": not findings,
        "findings": findings,
        "claims": claims,
        "avatar_box": avatar,
        "slide_match": slides,
    }


# The final artifact ----------------------------------------------------------------------------------------------
def overlay_rows(rc, composed):
    """[{segment, box, start_s, end_s, directory}] of the overlays compose placed."""
    rows = []
    for overlay in composed["overlays"]:
        manifest, directory = upstream(rc.store, f"avatar/{overlay['segment']}")
        fps = manifest["measurements"]["fps"]
        length = overlay["frames"] * fps["den"] / fps["num"]
        end = overlay["start_s"] + length
        rows.append(overlay | {"end_s": end, "directory": directory})
    return rows


def covering(overlays, at_s):
    return next((o for o in overlays if o["start_s"] <= at_s < o["end_s"]), None)


def midpoint(page):
    return (page["startS"] + page["endS"]) / 2


def moments(job, overlays):
    """[(page id, seconds, overlay)]: where each visible page's frame is read. A job with no pages reads each
    overlay's midpoint under its segment id."""
    rows = []
    for page in visible_pages(job):
        if page["id"] is None:
            return [(o["segment"], (o["start_s"] + o["end_s"]) / 2, o) for o in overlays]
        overlay = covering(overlays, midpoint(page))
        if overlay is not None:
            rows.append((page["id"], midpoint(page), overlay))
    return rows


def frame_off_alpha(video, overlay, at_s, box):
    """(flat, {pixels, extent} or None): off-background pixels of the composed frame's box, outside the avatar."""
    inputs = ["-ss", f"{at_s:.6f}", "-i", str(video)]
    view = raw(inputs, f"scale={VIEW_W}:{VIEW_H}:flags=neighbor", limit=1)
    crop = raw(inputs, f"crop={box['w']}:{box['h']}:{box['x']}:{box['y']}", limit=1)
    colour = flat_colour(view) if view else None
    if colour is None:
        return False, None
    placed = overlay["box"]
    side = placed["w"]
    dilate = ",".join(["dilation"] * ALPHA_DILATE_PX)
    alpha = raw(
        ["-ss", f"{at_s - overlay['start_s']:.6f}", "-i", str(overlay["directory"] / "overlay" / "overlay.mov")],
        f"scale={side}:{side},format=rgba,alphaextract,{dilate}",
        limit=1,
        pixel="gray",
    )
    avatar = alpha_mask(alpha, side, placed["x"] - box["x"], placed["y"] - box["y"], box["w"], box["h"])
    mask = minus(off_mask(crop, colour, FRAME_TOL), avatar)
    pixels = mask.count(1)
    return True, ({"pixels": pixels, "extent": extent(mask, box["w"], box["x"], box["y"])} if pixels else None)


def difference(video, at_s, source, rect, fit):
    """The per-channel absolute difference of a composed frame's rect and a slide fitted to it, as RGB bytes."""
    x, y, w, h = rect
    graph = (
        f"[0:v]crop={w}:{h}:{x}:{y},format=gbrp[a];[1:v]{fit},format=gbrp[b];"
        "[a][b]blend=all_mode=difference,format=rgb24[d]"
    )
    try:
        return run(
            *FF, "-v", "error", "-ss", f"{at_s:.6f}", "-i", str(video), "-i", str(source), "-filter_complex", graph,
            "-map", "[d]", "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-", input=b"",
            timeout=TOOL_TIMEOUT_S,
        ).stdout  # fmt: skip
    except RuntimeError as exc:
        raise StageRefused("ffmpeg_failed", str(exc).splitlines()[0][:200], verdict=False) from None


def slide_frames(job, env, composed, overlays, video, w, h):
    """The findings of the composed video against its slides, and {page: share of pixels that differ} for each page
    it read, so a first real job can check SLIDE_MISMATCH_MAX against measured shares."""
    slides = job["slides"]
    if slides is None or composed["slides"] is None:
        return [], {}
    pages = {p["id"]: p for p in slides["pages"] if page_kind(p) == "slide"}
    layers = {layer["page"]: layer for run_ in composed["slides"]["runs"] for layer in run_["layers"]}
    findings, read = [], {}
    for page_id in sorted(set(pages) - set(layers)):
        findings.append({"code": "slide_layer_missing", "page": page_id})
    for page_id, page in pages.items():
        layer = layers.get(page_id)
        if layer is None:
            continue
        if layer["sha256"] != page["show"]["slide"]["sha256"]:
            findings.append({"code": "slide_layer_mismatch", "page": page_id})
            continue
        source = slide_file(env, layer["sha256"])
        if source is None:  # slide_gate reports it
            continue
        at = midpoint(page)
        box = layer["box"]
        rect = (box["x"], box["y"], box["w"], box["h"])
        fit = conform(w, h) if slides["layout"] == "Full" else f"scale={box['w']}:{box['h']},setsar=1"
        diff = difference(video, at, source, rect, fit)
        expected = box["w"] * box["h"] * 3
        if len(diff) < expected:
            findings.append({"code": "slide_not_shown", "page": page_id, "share": 1.0})
            continue
        mask = off_mask(diff[:expected], (0, 0, 0), SLIDE_TOL)
        overlay = covering(overlays, at) if page_id in {p["id"] for p in visible_pages(job)} else None
        if overlay is not None:
            placed = overlay["box"]
            square = (placed["x"] - box["x"], placed["y"] - box["y"], placed["w"], placed["h"])
            mask = minus(mask, rect_mask(square, box["w"], box["h"]))
        share = round(mask.count(1) / (box["w"] * box["h"]), 5)
        read[page_id] = share
        if share > SLIDE_MISMATCH_MAX:
            findings.append({"code": "slide_not_shown", "page": page_id, "share": share})
    return findings, read


def final_gates(rc, composed, video, w, h):
    """(avatar_box report, slide_match report) of the composed video: the pictures as preflight reads them, then the
    frames themselves. A failed gate is a state, as for the other machine gates."""
    job, env = rc.job, rc.env
    overlays = overlay_rows(rc, composed)
    avatar = avatar_box_gate(job, env, w, h)
    if overlays and avatar.get("box"):
        exempt = box_exempt(job)
        for page_id, at, overlay in moments(job, overlays):
            if page_id in exempt:
                continue
            flat, worst = frame_off_alpha(video, overlay, at, avatar["box"])
            if flat and page_id in avatar["held"]:
                avatar["checked"].append(page_id)
                avatar["unchecked"].remove(page_id)
            if worst:
                avatar["findings"].append({"code": "avatar_box_occupied", "page": page_id, "source": "frame"} | worst)
    avatar["state"] = state(avatar["checked"], avatar["findings"])
    slide = slide_gate(job, env, w, h)
    found, read = slide_frames(job, env, composed, overlays, video, w, h)
    slide["findings"] += found
    slide["frames_read"] = read
    slide["state"] = state(slide["checked"], slide["findings"])
    return avatar, slide


def frame_review(avatar):
    """The pages no gate read, for the view a person decides from: nv cut and the render stage result."""
    return {"unchecked": avatar["unchecked"], "exempt": avatar["exempt"]}
