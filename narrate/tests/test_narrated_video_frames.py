"""The frame gates (docs/spec/NARRATED_VIDEO.md, "Frame gates", narrate/video/frames.py, Linear TIN-7788): a planted
fault refuses before any voice spend, and the same fault fails deliver_check on the composed video.

Every picture is an FFmpeg test source or a colour field with a drawn block; the voice is the fake engine's sine and
the avatar the kitpip stub. No real demo, slide, recording or render is read.
"""

import copy
import hashlib
import json
import shutil
import subprocess

import pytest
from test_narrated_video_compose import Bench, node_dir
from test_narrated_video_intake import add_asset, no_whisper, set_manifest, set_script, ws  # noqa: F401  (fixtures)
from test_narrated_video_intake import intake as run_intake
from test_narrated_video_intake import manifest as read_manifest
from test_narrated_video_render_stage import COMMIT, ENV, gpu_request, refused, request

from narrate.video import admit, bundle, cli, compose, deliver, frames, keys, render_stage, store, subject
from narrate.video.common import Env
from narrate.video.job import DEFAULTS, JobError, check_shape, load_records

W, H = 1280, 720  # the Contingency profile the Bench jobs use
BOX = frames.guarded_box(DEFAULTS["avatar"], W, H)
IN_BOX = f"drawbox=x={BOX['x'] + 40}:y={BOX['y'] + 40}:w=120:h=30:color=black:t=fill"
OUT_OF_BOX = "drawbox=x=60:y=60:w=500:h=300:color=black:t=fill"


def picture(path, *filters, size=f"{W}x{H}", source="color=white"):
    """A one-frame PNG: a white field, or another lavfi source, with drawn blocks."""
    chain = ",".join(filters) or "null"
    command = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"{source}:s={size}", "-vf", chain]
    subprocess.run([*command, "-frames:v", "1", str(path)], check=True)
    return path


def clip(path, *filters, seconds=3):
    """A white H.264 clip at 30 frames per second, with drawn blocks."""
    chain = ",".join(filters) or "null"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=white:s={W}x{H}:r=30:d={seconds}", "-vf", chain,
         "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )  # fmt: skip
    return path


def pages(*digests, seconds=2):
    return [
        {"id": f"p{n}", "startS": n * seconds, "endS": (n + 1) * seconds, "show": {"slide": {"sha256": digest}}}
        for n, digest in enumerate(digests)
    ]


def full(ws_, job_id, *digests, **edits):
    """A Full slide job with the avatar on every page, on a grey card at the Contingency profile."""
    job = ws_.slides_job(job_id, **edits)
    job["slides"] = copy.deepcopy(DEFAULTS["slides"]) | {"pages": pages(*digests)}
    job["avatar"]["avatarOff"] = edits.get("avatar.avatarOff", [])
    return job


@pytest.fixture
def bench(tmp_path, ffmpeg):
    return Bench(tmp_path)


def source(bench, tmp_path, name, *filters, **kw):
    return bench.add_source(picture(tmp_path / name, *filters, **kw))


def codes(report):
    return [f["code"] for f in report["findings"]]


# Pure parts ------------------------------------------------------------------------------------------------------
def test_the_guarded_box_is_the_box_the_hand_check_used():
    """The default avatar at 1080p: x 1466 and y 626, 422 px square, plus 16 px (TIN-7788 fcc8ded6)."""
    assert frames.guarded_box(DEFAULTS["avatar"], 1920, 1080) == {"x": 1450, "y": 610, "w": 454, "h": 454}


def test_the_guard_is_clamped_to_the_frame():
    box = frames.guarded_box(DEFAULTS["avatar"] | {"marginPx": 4}, 1920, 1080)
    assert box["x"] + box["w"] == 1920 and box["y"] + box["h"] == 1080


def test_off_mask_counts_a_pixel_once_and_reads_every_channel():
    rgb = bytes([255, 255, 255, 200, 255, 255, 255, 200, 255, 200, 200, 200])
    assert list(frames.off_mask(rgb, (255, 255, 255), 8)) == [0, 1, 1, 1]
    assert frames.off_mask(rgb, (255, 255, 255), 55).count(1) == 0  # at the tolerance is within it


def test_a_picture_with_no_dominant_colour_has_no_background():
    assert frames.flat_colour(bytes([250, 250, 250]) * 60 + bytes([0, 0, 0]) * 40) == (250, 250, 250)
    assert frames.flat_colour(bytes(v for n in range(100) for v in (n * 2, 255 - n * 2, n))) is None


def test_extent_reports_frame_pixels():
    mask = bytearray(30)
    mask[7] = mask[23] = 1  # row 1 column 2, and row 4 column 3, in a 5 by 6 mask
    assert frames.extent(bytes(mask), 5, 100, 200) == {"x0": 102, "y0": 201, "x1": 103, "y1": 204}
    assert frames.extent(bytes(30), 5) is None


def test_the_alpha_mask_lands_at_its_offset_and_cuts_what_runs_outside():
    alpha = bytes([0, 9, 9, 0])  # 2 by 2
    assert list(frames.alpha_mask(alpha, 2, 1, 1, 4, 4)) == [0] * 4 + [0, 0, 1, 0] + [0, 1, 0, 0] + [0] * 4
    assert list(frames.alpha_mask(alpha, 2, -1, 0, 2, 2)) == [1, 0, 0, 0]


def test_a_rect_mask_may_run_outside_and_minus_removes_it():
    rect = frames.rect_mask((-1, 1, 2, 9), 3, 3)
    assert list(rect) == [0, 0, 0, 1, 0, 0, 1, 0, 0]
    assert list(frames.minus(bytes([1, 1, 0, 1, 0, 0, 1, 0, 1]), rect)) == [1, 1, 0, 0, 0, 0, 0, 0, 1]


def test_a_short_board_image_leaves_a_strip_and_a_16_by_9_slide_does_not():
    """The size of the fault in TIN-7788 8c47686a: 1904 by 1064 leaves a dark strip at 1080p."""
    assert frames.strip_px(1904, 1064, 1920, 1080) > frames.STRIP_PX
    assert frames.strip_px(320, 180, 1920, 1080) == 0
    assert frames.strip_px(1920, 1080, 1920, 1080) == 0


def test_visible_pages_drop_an_avatar_off_page_and_a_hidden_segment():
    job = {
        "avatar": {"avatarOff": ["b"]},
        "segments": [{"id": "a", "avatar": True}, {"id": "c", "avatar": False}],
        "slides": {"pages": [{"id": "a"}, {"id": "b"}, {"id": "c"}]},
    }
    assert [p["id"] for p in frames.visible_pages(job)] == ["a"]
    assert frames.visible_pages(job | {"avatar": None}) == []
    assert [p["id"] for p in frames.visible_pages(job | {"slides": None})] == [None]


def test_a_job_written_before_box_exempt_stays_valid_with_its_digest(bench):
    job = bench.slides_job("nv-old")
    del job["avatar"]["boxExempt"]
    before = keys.digest(job)
    assert check_shape(job) is job and keys.digest(job) == before and frames.box_exempt(job) == set()
    with pytest.raises(JobError) as caught:
        check_shape(job | {"avatar": job["avatar"] | {"boxExempt": "p0"}})
    assert caught.value.code == "job_invalid"


# Before any voice spend ------------------------------------------------------------------------------------------
def test_preflight_passes_slides_that_keep_out_of_the_box(bench, tmp_path):
    digest = source(bench, tmp_path, "clean.png", OUT_OF_BOX)
    report = frames.preflight(full(bench, "nv-clean", digest), bench.env)
    assert report["ok"] and report["kind"] == frames.KIND
    assert report["avatar_box"]["state"] == "passed" and report["avatar_box"]["checked"] == ["p0"]
    assert report["slide_match"]["state"] == "passed"
    assert report["job_sha256"] == keys.digest(full(bench, "nv-clean", digest))


def test_preflight_refuses_a_slide_with_content_in_the_box(bench, tmp_path):
    clean = source(bench, tmp_path, "clean.png")
    digest = source(bench, tmp_path, "planted.png", IN_BOX)
    report = frames.preflight(full(bench, "nv-planted", clean, digest), bench.env)
    assert not report["ok"] and codes(report) == ["avatar_box_occupied"]
    finding = report["findings"][0]
    assert finding["page"] == "p1" and finding["source"] == "layer" and finding["pixels"] >= 120 * 30
    assert finding["extent"]["x0"] >= BOX["x"] and finding["extent"]["y1"] < BOX["y"] + BOX["h"]


def test_light_content_counts_on_a_lossless_picture(bench, tmp_path):
    """23 levels off white is inside the H.264 margin and outside the lossless one, and 5 levels is inside both."""
    block = f"drawbox=x={BOX['x'] + 40}:y={BOX['y'] + 40}:w=120:h=30:t=fill:color=0x"
    light = source(bench, tmp_path, "light.png", block + "E8E8E8")
    assert codes(frames.preflight(full(bench, "nv-light", light), bench.env)) == ["avatar_box_occupied"]
    faint = source(bench, tmp_path, "faint.png", block + "FAFAFA")
    assert frames.preflight(full(bench, "nv-faint", faint), bench.env)["ok"]


def test_the_guard_ring_counts_as_the_box(bench, tmp_path):
    ring = f"drawbox=x={BOX['x'] + 2}:y={BOX['y'] + 2}:w=4:h=40:color=black:t=fill"
    digest = source(bench, tmp_path, "ring.png", ring)
    assert codes(frames.preflight(full(bench, "nv-ring", digest), bench.env)) == ["avatar_box_occupied"]


def test_a_page_with_the_avatar_off_is_not_read(bench, tmp_path):
    digest = source(bench, tmp_path, "planted.png", IN_BOX)
    job = full(bench, "nv-off", digest)
    job["avatar"]["avatarOff"] = ["p0"]
    report = frames.preflight(job, bench.env)
    assert report["ok"] and report["avatar_box"]["state"] == "not_applicable"


def test_an_exempt_page_is_listed_not_read_and_not_counted_clear(bench, tmp_path):
    digest = source(bench, tmp_path, "render.png", IN_BOX)
    job = full(bench, "nv-exempt", digest)
    job["avatar"]["boxExempt"] = ["p0"]
    report = frames.preflight(job, bench.env)
    assert report["ok"] and report["avatar_box"]["exempt"] == ["p0"]
    assert report["avatar_box"]["checked"] == [] and report["avatar_box"]["state"] == "not_applicable"


def test_a_picture_with_no_flat_background_is_unchecked_never_clear(bench, tmp_path):
    digest = source(bench, tmp_path, "photo.png", source="testsrc2=r=1")
    report = frames.preflight(full(bench, "nv-photo", digest), bench.env)
    assert report["ok"] and report["avatar_box"]["unchecked"] == ["p0"]
    assert report["avatar_box"]["checked"] == [] and report["avatar_box"]["state"] == "not_applicable"


FLAT, BUSY = "color=c=white:", "testsrc2="


def joined(path, *parts):
    """A clip of (lavfi source, seconds) parts, one after the other."""
    inputs = [arg for name, s in parts for arg in ("-f", "lavfi", "-i", f"{name}s={W}x{H}:r=30:d={s}")]
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", "[0:v][1:v]concat=n=2:v=1[o]", "-map", "[o]",
         "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )  # fmt: skip
    return path


def video_job(bench, job_id, digest):
    job = bench.slides_job(job_id)
    job["base"] = {"video": {"sha256": digest, "keepBaseAudio": False}}
    job["slides"] = None
    return job


def test_one_flat_sample_leaves_a_busy_video_unchecked(bench, tmp_path):
    """A base that opens on a title card and turns busy: one flat sample in 20 must not clear the page."""
    digest = bench.add_source(joined(tmp_path / "title.mp4", (FLAT, 0.6), (BUSY, 9.4)))
    report = frames.preflight(video_job(bench, "nv-title", digest), bench.env)
    assert report["avatar_box"]["checked"] == [] and report["avatar_box"]["unchecked"] == ["program"]
    assert report["avatar_box"]["state"] == "not_applicable"


def test_a_finding_in_a_flat_sample_counts_on_an_unchecked_page(bench, tmp_path):
    path = tmp_path / "planted-title.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(joined(tmp_path / "t.mp4", (FLAT, 1), (BUSY, 4))), "-vf", IN_BOX,
         "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )  # fmt: skip
    report = frames.preflight(video_job(bench, "nv-planted-title", bench.add_source(path)), bench.env)
    assert report["avatar_box"]["unchecked"] == ["program"] and codes(report) == ["avatar_box_occupied"]


def test_a_page_with_no_samples_stays_unchecked(bench, tmp_path):
    digest = bench.add_source(clip(tmp_path / "white.mp4"))
    job = video_job(bench, "nv-past-end", digest)
    job["slides"] = copy.deepcopy(DEFAULTS["slides"]) | {
        "pages": [{"id": "late", "startS": 50, "endS": 60, "show": "Base"}]
    }
    assert frames.avatar_box_gate(job, bench.env, W, H)["unchecked"] == ["late"]


@pytest.mark.parametrize("page", ["only", None])
def test_a_flat_composed_frame_does_not_clear_a_busy_base(bench, tmp_path, page):
    """The frame at a page's midpoint is one sample. The clip ends flat, so that frame is flat and the base is not.
    A job with no pages reads its frames under segment ids, and they must not stand in for its program page."""
    path = joined(tmp_path / "ends-flat.mp4", (BUSY, 1), (FLAT, 9))
    job = video_job(bench, "nv-ends-flat", bench.add_source(path))
    job["avatar"]["avatarOff"] = []
    if page:
        job["slides"] = copy.deepcopy(DEFAULTS["slides"]) | {
            "pages": [{"id": page, "startS": 0, "endS": 10, "show": "Base"}]
        }
    s, result, _ = bench.run(job)
    assert result["ok"], result
    box = report_of(s)["avatar_box"]
    assert box["checked"] == [] and box["unchecked"] == [page or "program"] and box["state"] == "not_applicable"


def test_a_hold_page_reads_the_frame_it_holds(bench, tmp_path):
    """The fault appears after 1.2 seconds, so a hold at 2 seconds shows it and the first frame does not."""
    planted = bench.add_source(clip(tmp_path / "late.mp4", IN_BOX + ":enable='gte(t,1.2)'"))
    job = video_job(bench, "nv-hold", planted)
    job["slides"] = copy.deepcopy(DEFAULTS["slides"]) | {
        "pages": [{"id": "held", "startS": 2, "endS": 3, "show": "Hold"}]
    }
    report = frames.preflight(job, bench.env)
    assert codes(report) == ["avatar_box_occupied"] and report["findings"][0]["page"] == "held"


def test_a_base_video_is_sampled_across_its_page(bench, tmp_path):
    """The fault appears only after the first second, so one frame at the start would miss it."""
    planted = bench.add_source(clip(tmp_path / "late.mp4", IN_BOX + ":enable='gte(t,1.2)'"))
    job = bench.slides_job("nv-video")
    job["base"] = {"video": {"sha256": planted, "keepBaseAudio": False}}
    job["slides"] = None
    report = frames.preflight(job, bench.env)
    assert codes(report) == ["avatar_box_occupied"] and report["findings"][0]["pixels"] >= 120 * 30
    clean = bench.add_source(clip(tmp_path / "white.mp4"))
    job["base"] = {"video": {"sha256": clean, "keepBaseAudio": False}}
    assert frames.preflight(job, bench.env)["ok"]


def test_a_colour_card_base_counts_as_clear_and_a_deck_as_unchecked(bench):
    job = bench.slides_job("nv-card")
    job["slides"] = None
    assert frames.avatar_box_gate(job, bench.env, W, H)["checked"] == ["program"]
    job["base"] = {"deck": {"producer": "fixture", "videoSha256": "a" * 64, "timelineSha256": "b" * 64,
                            "stemsSha256": "c" * 64, "tightenEditsSha256": None}}  # fmt: skip
    assert frames.avatar_box_gate(job, bench.env, W, H)["unchecked"] == ["program"]


def test_a_slide_card_that_reaches_the_box_refuses(bench, tmp_path):
    digest = source(bench, tmp_path, "card.png")
    job = bench.slides_job("nv-cardslide")
    job["slides"]["pages"] = pages(digest)
    job["avatar"]["avatarOff"] = []
    job["avatar"]["corner"] = "BL"
    assert codes(frames.preflight(job, bench.env)) == ["card_in_avatar_box"]
    job["avatar"]["corner"] = "BR"
    assert frames.preflight(job, bench.env)["ok"]


def test_a_letterboxed_full_slide_refuses(bench, tmp_path):
    digest = source(bench, tmp_path, "short.png", size=f"{W}x{H - 12}")
    assert codes(frames.preflight(full(bench, "nv-strip", digest), bench.env)) == ["slide_letterbox"]


def test_a_slide_changed_after_the_index_was_built_refuses(bench, tmp_path):
    """A run's Env outlives the slide: its index still names the file, and the re-hash catches the change."""
    digest = source(bench, tmp_path, "changed.png")
    (bench.paths["store"] / "changed.png").write_bytes(b"not the slide")
    report = frames.preflight(full(bench, "nv-hash", digest), bench.env)
    assert report["slide_match"]["state"] == "failed" and codes(report) == ["slide_digest_mismatch"]
    assert report["avatar_box"]["unchecked"] == ["p0"]


def test_admit_refuses_a_box_exempt_page_the_job_does_not_define(bench, tmp_path):
    job = full(bench, "nv-unknown", source(bench, tmp_path, "a.png"))
    job["avatar"]["boxExempt"] = ["no-such-page"]
    verdict = admit.admit(job, bench.records)
    assert verdict["verdict"] == "Refused" and verdict["refusals"][0]["code"] == "page_unknown"


def test_a_long_span_samples_slowly_enough_to_stay_bounded(bench, tmp_path):
    path = clip(tmp_path / "white.mp4", seconds=2)
    box = {"x": 0, "y": 0, "w": 8, "h": 8}
    assert len(frames.box_samples(path, W, H, box, span=(0, 2))) in (4, 5)
    assert len(frames.box_samples(path, W, H, box, span=(0, 2 * frames.MAX_SAMPLES))) <= 2


def test_a_report_holds_no_path(bench, tmp_path):
    digest = source(bench, tmp_path, "planted.png", IN_BOX)
    text = json.dumps(frames.preflight(full(bench, "nv-paths", digest), bench.env))
    assert str(tmp_path) not in text and "planted.png" not in text


def test_the_preflight_command_exits_1_and_writes_nothing(bench, tmp_path, capsys):
    digest = source(bench, tmp_path, "planted.png", IN_BOX)
    job = full(bench, "nv-cli", digest)
    s = bench.store(job)
    before = sorted(p.name for p in s.dir.iterdir())
    args = ["--root", str(s.root), "--records", str(bench.paths["records"]), "--store", str(bench.paths["store"])]
    assert cli.main(["preflight", "nv-cli", *args]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out)["ok"] is False and "avatar_box_occupied" in captured.err
    assert sorted(p.name for p in s.dir.iterdir()) == before


# On the composed video -------------------------------------------------------------------------------------------
def report_of(s):
    return json.loads((node_dir(s, "deliver_check") / "deliver_check.json").read_text())


def test_a_clean_cut_passes_both_gates_on_the_real_stages(bench, tmp_path):
    a, b = source(bench, tmp_path, "a.png", OUT_OF_BOX), source(bench, tmp_path, "b.png")
    s, result, _ = bench.run(full(bench, "nv-final", a, b))
    assert result["ok"], result
    report = report_of(s)
    assert report["gates"]["avatar_box"] == "passed" and report["avatar_box"]["checked"] == ["p0", "p1"]
    assert report["gates"]["slide_match"] == "passed" and list(report["slide_match"]["frames_read"]) == ["p0", "p1"]
    assert report["delivery_gate"]["machine_gates_passed"] is True


def test_a_planted_fault_fails_the_cut_and_the_cut_never_reaches_the_operator(bench, tmp_path):
    """The r5 failure: every machine gate passed with a frame finding open. Now deliver_check reports it as failed,
    and a failed cut refuses machine_gates_failed."""
    digest = source(bench, tmp_path, "planted.png", IN_BOX)
    job = full(bench, "nv-final-bad", digest)
    s, result, _ = bench.run(job)
    assert result["ok"], result
    report = report_of(s)
    assert report["gates"]["avatar_box"] == "failed"
    assert {f["source"] for f in report["avatar_box"]["findings"]} == {"layer", "frame"}
    assert report["delivery_gate"]["internal_review_allowed"] is False
    with pytest.raises(JobError) as caught:
        subject.cut(s, job)
    assert caught.value.code == "machine_gates_failed" and "avatar_box" in caught.value.detail


def test_the_slide_card_layout_passes_both_gates_on_its_own_box(bench):
    """The example card job on a flat grey base: the card is compared at its box and the composed frame is read."""
    s, result, _ = bench.run(bench.slides_job("nv-card-final"))
    assert result["ok"], result
    report = report_of(s)
    assert report["gates"]["slide_match"] == "passed" and report["gates"]["avatar_box"] == "passed"
    assert report["slide_match"]["frames_read"] and report["avatar_box"]["unchecked"] == []


def test_a_dense_correct_slide_stays_under_the_mismatch_limit(bench, tmp_path):
    digest = source(bench, tmp_path, "dense.png", source="testsrc2=r=1")
    s, result, _ = bench.run(full(bench, "nv-dense", digest))
    assert result["ok"], result
    report = report_of(s)
    assert report["gates"]["slide_match"] == "passed"
    assert report["slide_match"]["frames_read"]["p0"] <= frames.SLIDE_MISMATCH_MAX
    assert report["avatar_box"]["unchecked"] == ["p0"]


@pytest.fixture
def composed(bench, tmp_path):
    a = source(bench, tmp_path, "a.png")
    job = full(bench, "nv-pixels", a)
    s, result, _ = bench.run(job)
    assert result["ok"], result
    return job, s, s.manifest("compose")["measurements"], node_dir(s, "compose") / "video.mp4"


def test_a_cut_that_shows_another_slide_fails_slide_match(bench, tmp_path, composed):
    job, s, measured, video = composed
    other = source(bench, tmp_path, "other.png", OUT_OF_BOX)
    claimed = copy.deepcopy(job)
    claimed["slides"]["pages"][0]["show"]["slide"]["sha256"] = other
    faked = copy.deepcopy(measured)
    faked["slides"]["runs"][0]["layers"][0]["sha256"] = other
    overlays = []
    findings, read = frames.slide_frames(claimed, bench.env, faked, overlays, video, W, H)
    assert list(read) == ["p0"] and [f["code"] for f in findings] == ["slide_not_shown"]
    assert findings[0]["share"] > frames.SLIDE_MISMATCH_MAX


def test_a_layer_that_is_not_the_jobs_page_fails_slide_match(bench, tmp_path, composed):
    job, s, measured, video = composed
    other = copy.deepcopy(job)
    other["slides"]["pages"][0]["show"]["slide"]["sha256"] = "f" * 64
    findings, _ = frames.slide_frames(other, bench.env, measured, [], video, W, H)
    assert [f["code"] for f in findings] == ["slide_layer_mismatch"]
    empty = copy.deepcopy(measured)
    empty["slides"]["runs"] = []
    assert [f["code"] for f in frames.slide_frames(job, bench.env, empty, [], video, W, H)[0]] == [
        "slide_layer_missing"
    ]


def test_the_frame_check_leaves_out_the_avatars_alpha_only(bench, tmp_path, composed):
    """The stub draws an opaque square in the middle of a transparent field: a block under it is the avatar's, and a
    block beside it in the box is a finding."""
    job, s, measured, video = composed
    rc_like = type("RC", (), {"store": s})
    overlay = frames.overlay_rows(rc_like, measured)[0]
    placed = overlay["box"]
    middle = (placed["x"] + placed["w"] // 2 - 10, placed["y"] + placed["h"] // 2 - 10)
    under = clip(tmp_path / "under.mp4", f"drawbox=x={middle[0]}:y={middle[1]}:w=20:h=20:color=black:t=fill")
    assert frames.frame_off_alpha(under, overlay, 1.0, BOX) == (True, None)
    beside = clip(
        tmp_path / "beside.mp4", f"drawbox=x={placed['x'] + 2}:y={placed['y'] + 2}:w=12:h=12:color=black:t=fill"
    )
    flat, worst = frames.frame_off_alpha(beside, overlay, 1.0, BOX)
    assert flat and worst["pixels"] >= 100


def test_the_alpha_is_dilated_for_scaling_and_chroma_bleed(bench, tmp_path, composed):
    """A faint band 3 px beyond the alpha's edge is scaling bleed, inside the 4 px dilation. At 8 px it is content."""
    job, s, measured, _ = composed
    rc_like = type("RC", (), {"store": s})
    overlay = frames.overlay_rows(rc_like, measured)[0]
    placed = overlay["box"]
    side = placed["w"]
    alpha = frames.raw(
        ["-ss", "1", "-i", str(overlay["directory"] / "overlay" / "overlay.mov")],
        f"scale={side}:{side},format=rgba,alphaextract",
        limit=1,
        pixel="gray",
    )
    drawn = frames.extent(bytes(1 if v else 0 for v in alpha), side, placed["x"], placed["y"])

    def band(name, gap, width):
        drawbox = f"drawbox=x={drawn['x1'] + gap}:y={drawn['y0']}:w={width}:h=40:color=0xB8B8B8:t=fill"
        return clip(tmp_path / name, drawbox)

    assert frames.frame_off_alpha(band("near.mp4", 1, 3), overlay, 1.0, BOX) == (True, None)
    assert frames.frame_off_alpha(band("far.mp4", 8, 6), overlay, 1.0, BOX)[1]["pixels"] >= 100


def test_a_composed_frame_with_no_flat_background_is_not_read(bench, tmp_path, composed):
    job, s, measured, _ = composed
    rc_like = type("RC", (), {"store": s})
    overlay = frames.overlay_rows(rc_like, measured)[0]
    noisy = tmp_path / "noisy.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s={W}x{H}:r=30:d=2", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", str(noisy)],
        check=True,
    )  # fmt: skip
    assert frames.frame_off_alpha(noisy, overlay, 1.0, BOX) == (False, None)


def test_unread_pages_reach_the_cut_and_the_deliver_check_report(bench, tmp_path):
    """A gradient behind a block in the box has no background to read, so the gate cannot fail it. The person who
    decides sees the page id in nv cut."""
    photo = source(bench, tmp_path, "photo.png", source="testsrc2=r=1")
    render = source(bench, tmp_path, "render.png", IN_BOX)
    job = full(bench, "nv-review", photo, render)
    job["avatar"]["boxExempt"] = ["p1"]
    s, result, _ = bench.run(job)
    assert result["ok"], result
    report = report_of(s)
    assert report["gates"]["avatar_box"] == "not_applicable"
    assert report["delivery_gate"]["machine_gates_passed"] is True
    assert subject.cut(s, job)["frame_review"] == {"unchecked": ["p0"], "exempt": ["p1"]}


def test_a_job_without_pages_reads_each_overlays_midpoint():
    overlays = [{"segment": "a", "start_s": 0.0, "end_s": 4.0}, {"segment": "b", "start_s": 4.0, "end_s": 6.0}]
    job = {"avatar": {"avatarOff": []}, "segments": [{"id": "a", "avatar": True}], "slides": None}
    assert [(m[0], m[1]) for m in frames.moments(job, overlays)] == [("a", 2.0), ("b", 5.0)]


def test_deliver_check_keys_on_box_exempt_and_leaves_compose_alone(bench, tmp_path):
    from narrate.video import graph

    digest = source(bench, tmp_path, "planted.png", IN_BOX)
    job = full(bench, "nv-rekey", digest)
    s, result, _ = bench.run(job)
    assert report_of(s)["gates"]["avatar_box"] == "failed"
    freed = copy.deepcopy(job)
    freed["avatar"]["boxExempt"] = ["p0"]
    s, result, _ = bench.run(freed, replace=True)
    assert [row["node"] for row in result["ran"]] == ["deliver_check"], result["ran"]
    assert report_of(s)["gates"]["avatar_box"] == "not_applicable"
    assert report_of(s)["delivery_gate"]["internal_review_allowed"] is True
    assert graph.IMPL["compose"] == 2


# Through the render stage ----------------------------------------------------------------------------------------
def intake_job(ws_, tmp_path, *, persona="fixture-persona"):
    root = tmp_path / "narrated"
    out = root / "demo-fixture" / "intake"
    run_intake(ws_, out, persona=persona)
    common = ["--root", str(root), "--records", str(out / "records"), "--store", str(ws_["store"])]
    assert cli.main(["init", "--job", "demo-fixture", "--from", str(out / "narrated-video.json"), *common]) == 0
    s = store.JobStore(root, "demo-fixture")
    records = load_records(out / "records")
    media = Env(out / "records", records, ws_["store"], ws_["lexical"])
    return s, media


def bound_request(ws_, **changes):
    value = request(job_id="demo-fixture", **changes)
    value["inputs"] |= {
        "bundle_manifest_sha256": render_stage.sha256_file(ws_["bundle"] / "manifest.json"),
        "records_sha256": render_stage.tree_sha256(ws_["records"]),
    }
    return value


def plant(ws_, tmp_path, asset_id="slide-a"):
    """Replace a bundle slide with one that holds content in the avatar's box at the bundle's 1080p delivery."""
    box = frames.guarded_box(DEFAULTS["avatar"], 1920, 1080)
    planted = f"drawbox=x={box['x'] + 40}:y={box['y'] + 40}:w=200:h=60:color=black:t=fill"
    path = picture(tmp_path / "planted.png", planted, size="1920x1080")
    manifest = json.loads((ws_["bundle"] / "manifest.json").read_text())
    asset = next(a for a in manifest["assets"] if a["id"] == asset_id)
    shutil.copyfile(path, ws_["bundle"] / asset["path"])
    asset["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    asset["size"] = {"w": 1920, "h": 1080}
    set_manifest(ws_["bundle"], manifest)
    return asset


def test_a_clean_bundle_passes_preflight_and_the_report_lies_beside_the_intake(ws, tmp_path, ffmpeg):  # noqa: F811
    s, media = intake_job(ws, tmp_path)
    report = render_stage.preflight(bound_request(ws), s, media, ENV)
    assert report["ok"] and report["claims"] == "passed"
    assert report["avatar_box"]["checked"] == ["intro", "result"]
    assert report["slide_match"]["checked"] == ["intro", "result"]
    written = s.dir / "intake" / render_stage.PREFLIGHT_FILE
    assert report["preflight_sha256"] == render_stage.sha256_file(written)


def test_a_planted_box_fault_refuses_at_preflight_with_its_report_written(ws, tmp_path, ffmpeg):  # noqa: F811
    plant(ws, tmp_path)
    s, media = intake_job(ws, tmp_path)
    assert refused(render_stage.preflight, bound_request(ws), s, media, ENV) == "avatar_box_occupied"
    report = json.loads((s.dir / "intake" / render_stage.PREFLIGHT_FILE).read_text())
    assert report["ok"] is False and report["findings"][0]["page"] == "intro"


def test_a_planted_fault_refuses_a_gpu_request_too_before_its_window(ws, tmp_path, ffmpeg):  # noqa: F811
    """A gpu_window request stops here, not at gpu_window_not_v1: this phase runs before any window would."""
    plant(ws, tmp_path)
    s, media = intake_job(ws, tmp_path)
    value = gpu_request()
    value |= {"job_id": "demo-fixture", "inputs": bound_request(ws)["inputs"]}
    assert refused(render_stage.preflight, value, s, media, ENV) == "avatar_box_occupied"


def test_a_planted_number_refuses_at_intake_and_no_job_or_report_exists(ws, tmp_path, ffmpeg):  # noqa: F811
    set_script(ws["bundle"], "forty two percent", "forty three percent")
    with pytest.raises(bundle.BundleError) as caught:
        intake_job(ws, tmp_path)
    assert caught.value.code == "number_unclaimed"
    assert not (tmp_path / "narrated" / "demo-fixture" / "intake" / "intake.json").exists()


def test_a_declared_exemption_reaches_the_job_and_clears_preflight(ws, tmp_path, ffmpeg):  # noqa: F811
    asset = plant(ws, tmp_path)
    manifest = json.loads((ws["bundle"] / "manifest.json").read_text())
    next(a for a in manifest["assets"] if a["id"] == asset["id"])["avatar_box"] = "exempt"
    set_manifest(ws["bundle"], manifest)
    s, media = intake_job(ws, tmp_path)
    assert s.read_job()["avatar"]["boxExempt"] == ["intro"]
    report = render_stage.preflight(bound_request(ws), s, media, ENV)
    assert report["ok"] and report["avatar_box"]["exempt"] == ["intro"]


def only_mp4_bundle(workspace, tmp_path, *filters, exempt=True):
    """Both beats of the fixture bundle show one MP4, so the job has a video base and no slides."""
    data = clip(tmp_path / "beats.mp4", *filters, seconds=20).read_bytes()
    add_asset(workspace["bundle"], "beats", "beats.mp4", "mp4", data)
    set_script(workspace["bundle"], "asset_id: slide-a", "asset_id: beats")
    set_script(workspace["bundle"], "asset_id: slide-b", "asset_id: beats")
    manifest = read_manifest(workspace["bundle"])
    if exempt:
        next(a for a in manifest["assets"] if a["id"] == "beats")["avatar_box"] = "exempt"
    set_manifest(workspace["bundle"], manifest)


def test_an_exempt_mp4_only_bundle_passes_intake_and_covers_its_program_page(ws, tmp_path, ffmpeg):  # noqa: F811
    """The beats are the job's segments here, because a job with no slide has no pages."""
    only_mp4_bundle(ws, tmp_path, IN_BOX)
    s, media = intake_job(ws, tmp_path)
    job = s.read_job()
    assert job["slides"] is None and job["avatar"]["boxExempt"] == ["intro", "result"]
    report = render_stage.preflight(bound_request(ws), s, media, ENV)
    assert report["ok"] and report["avatar_box"]["exempt"] == ["program"]
    assert report["avatar_box"]["checked"] == [] and report["avatar_box"]["unchecked"] == []


def test_an_undeclared_mp4_only_bundle_is_still_read(ws, tmp_path, ffmpeg):  # noqa: F811
    only_mp4_bundle(ws, tmp_path, IN_BOX, exempt=False)
    s, media = intake_job(ws, tmp_path)
    assert s.read_job()["avatar"]["boxExempt"] == []
    assert refused(render_stage.preflight, bound_request(ws), s, media, ENV) == "avatar_box_occupied"


def test_a_partly_exempt_job_with_no_pages_is_read():
    job = {"avatar": {"boxExempt": ["a"]}, "segments": [{"id": "a", "avatar": True}, {"id": "b", "avatar": True}]}
    assert frames.page_exempt(job, frames.PROGRAM) is False
    job["segments"][1]["avatar"] = False
    assert frames.page_exempt(job, frames.PROGRAM) is True


def test_a_segment_is_exemptable_only_in_a_job_with_no_slides(bench, tmp_path):
    job = full(bench, "nv-segment", source(bench, tmp_path, "a.png"))
    job["avatar"]["boxExempt"] = [job["segments"][0]["id"]]
    assert admit.admit(job, bench.records)["refusals"][0]["code"] == "page_unknown"
    job["slides"] = None
    assert not [r for r in admit.admit(job, bench.records)["refusals"] if r["code"] == "page_unknown"]
    job["avatar"]["boxExempt"] = ["no-such-segment"]
    assert admit.admit(job, bench.records)["refusals"][0]["code"] == "page_unknown"


def test_a_slide_changed_in_the_store_refuses_at_the_command(ws, tmp_path, ffmpeg, monkeypatch, capsys):  # noqa: F811
    """Every copy of a slide changes before the process starts, so a fresh index has no file for its digest. The code
    is the verdict, not source_missing, and the report records it."""
    s, _ = intake_job(ws, tmp_path)
    digest = s.read_job()["slides"]["pages"][0]["show"]["slide"]["sha256"]
    copies = [p for p in ws["store"].rglob("*") if p.is_file() and render_stage.sha256_file(p) == digest]
    assert copies
    for path in copies:
        path.write_bytes(b"not the slide")
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(bound_request(ws)))
    monkeypatch.setenv("VIDEO_UTILS_COMMIT", COMMIT)
    out = s.dir / "intake"
    args = ["--root", str(s.root), "--records", str(out / "records"), "--store", str(ws["store"])]
    capsys.readouterr()
    assert cli.main(["render-stage", "preflight", "demo-fixture", "--request", str(request_path), *args]) == 1
    assert "slide_digest_mismatch" in capsys.readouterr().err
    assert json.loads((out / render_stage.PREFLIGHT_FILE).read_text())["slide_match"]["state"] == "failed"


def edit_intake(s, change):
    path = s.dir / "intake" / "intake.json"
    value = json.loads(path.read_text())
    change(value)
    path.write_text(json.dumps(value))


def test_an_intake_row_that_disagrees_with_the_job_refuses(ws, tmp_path, ffmpeg):  # noqa: F811
    """The job and the rows come from one convert, so this needs an intake.json edited afterward."""
    s, media = intake_job(ws, tmp_path)
    pages = s.read_job()["slides"]["pages"]

    def swap(value):
        row = next(r for r in value["segments"] if r["segment"] == pages[0]["id"])
        row["asset"]["sha256"] = pages[1]["show"]["slide"]["sha256"]

    edit_intake(s, swap)
    assert refused(render_stage.preflight, bound_request(ws), s, media, ENV) == "slide_page_mismatch"


def test_an_intake_whose_claims_did_not_pass_refuses_with_its_report(ws, tmp_path, ffmpeg):  # noqa: F811
    s, media = intake_job(ws, tmp_path)
    edit_intake(s, lambda value: value["states"].update(claims="partial"))
    assert refused(render_stage.preflight, bound_request(ws), s, media, ENV) == "claims_not_passed"
    report = json.loads((s.dir / "intake" / render_stage.PREFLIGHT_FILE).read_text())
    assert report["ok"] is False and report["claims"] == "partial"


def test_preflight_binds_the_request_before_it_reads_a_frame(ws, tmp_path, ffmpeg):  # noqa: F811
    s, media = intake_job(ws, tmp_path)
    good = bound_request(ws)
    assert refused(render_stage.preflight, good, s, media, {}) == "commit_unknown"
    assert refused(render_stage.preflight, good, s, media, {"VIDEO_UTILS_COMMIT": "f" * 40}) == "commit_mismatch"
    assert refused(render_stage.preflight, good | {"job_id": "another-job"}, s, media, ENV) == "job_mismatch"
    moved = copy.deepcopy(good)
    moved["inputs"]["bundle_manifest_sha256"] = "d" * 64
    assert refused(render_stage.preflight, moved, s, media, ENV) == "input_binding_mismatch"
    job = json.loads((s.dir / "job.json").read_text())
    (s.dir / "job.json").write_text(json.dumps(job | {"edition": "ClientNarrated"}))
    assert refused(render_stage.preflight, good, s, media, ENV) == "edition_mismatch"
    assert not (s.dir / "intake" / render_stage.PREFLIGHT_FILE).exists()


def test_a_preflight_that_crashes_leaves_no_earlier_pass(ws, tmp_path, ffmpeg, monkeypatch):  # noqa: F811
    s, media = intake_job(ws, tmp_path)
    render_stage.preflight(bound_request(ws), s, media, ENV)
    path = s.dir / "intake" / render_stage.PREFLIGHT_FILE
    assert path.exists()

    def crashes(*args):
        raise frames.StageRefused("ffmpeg_failed", "planted", verdict=False)

    monkeypatch.setattr(frames, "preflight", crashes)
    assert refused(render_stage.preflight, bound_request(ws), s, media, ENV) == "ffmpeg_failed"
    assert not path.exists()


def test_the_report_binds_the_intake_it_read(ws, tmp_path, ffmpeg):  # noqa: F811
    s, media = intake_job(ws, tmp_path)
    report = render_stage.preflight(bound_request(ws), s, media, ENV)
    assert report["intake_sha256"] == render_stage.sha256_file(s.dir / "intake" / "intake.json")


def test_a_manifest_avatar_box_value_other_than_exempt_refuses(ws, tmp_path):  # noqa: F811
    manifest = json.loads((ws["bundle"] / "manifest.json").read_text())
    manifest["assets"][0]["avatar_box"] = "clear"
    set_manifest(ws["bundle"], manifest)
    with pytest.raises(bundle.BundleError) as caught:
        run_intake(ws, tmp_path / "out")
    assert caught.value.code == "bundle_invalid"


def test_no_gpu_phase_comes_before_the_gates():
    phases = [p for p in render_stage.plan(gpu_request(), gpu_draft=True)["phases"]]
    ids = [p["id"] for p in phases]
    first_gpu = next(n for n, p in enumerate(phases) if p["gpu"])
    assert {"claims_gate", "intake", "preflight"} <= set(ids[:first_gpu])
    assert ids.index("claims_gate") < ids.index("intake") < ids.index("preflight") < ids.index("voice_plan")


def test_the_module_entry_point_runs_render_stage_preflight(ws, tmp_path, ffmpeg, monkeypatch, capsys):  # noqa: F811
    s, _ = intake_job(ws, tmp_path)
    path = tmp_path / "request.json"
    path.write_text(json.dumps(bound_request(ws)))
    monkeypatch.setenv("VIDEO_UTILS_COMMIT", COMMIT)
    capsys.readouterr()
    out = s.dir / "intake"
    args = ["--root", str(s.root), "--records", str(out / "records"), "--store", str(ws["store"])]
    assert cli.main(["render-stage", "preflight", "demo-fixture", "--request", str(path), *args]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert cli.main(["render-stage", "preflight", "--request", str(path), *args]) == 1
    assert "preflight names the job" in capsys.readouterr().err
    for flag in (["--gpu-draft"], ["--inputs", str(tmp_path)]):
        assert cli.main(["render-stage", "preflight", "demo-fixture", "--request", str(path), *flag, *args]) == 1
        assert "go with check" in capsys.readouterr().err


# deliver.py reads the same table the result does ------------------------------------------------------------------
def test_the_machine_gates_name_the_frame_gates():
    assert {"avatar_box", "slide_match"} <= set(render_stage.accept.AUTOMATED)
    assert compose.PROFILES and deliver.final_gates is frames.final_gates
