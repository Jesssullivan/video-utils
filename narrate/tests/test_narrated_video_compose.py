"""The narrated-video compose and delivery lane (L6, docs/spec/NARRATED_VIDEO.md): compose, deliver_check and handoff
run for real on synthetic fixtures, with the alpha, caption, label, profile, slide and flash checks.

Every input is generated or a committed synthetic fixture: the fake engine's sine voice, the generated E-major bed
loops, the two generated slide pictures (narrate/dhall/check.py), colour cards, an FFmpeg test pattern and the kitpip
stub, which draws an opaque square on a transparent ProRes 4444 field and holds no kitpip art. Nothing is a recording
or deck material.

The avatar and avatar_check stages run through lane L5's runners (narrate/video/kitpip.py) on the stub.
"""

import copy
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from test_narrated_video_simple import FIXTURES, Workspace, ran

from narrate.video import admit, cli, compose, deliver, graph, kitpip, labels, run
from narrate.video.common import RATE_HZ, StageRefused
from narrate.video.job import DEFAULTS, load_records
from narrate.video.speech import RUN

STUB = FIXTURES / "kitpip_stub.py"
EXTERNALS = FIXTURES / "kitpip-externals.json"
EXAMPLES = Path(__file__).resolve().parents[1] / "dhall" / "examples"
GREY = "#808080"
STUB_SQUARE = (0x40, 0xC0, 0xFF)
CUE = "Narrated by a synthetic voice"
HOST_ENV = ("WHISPER_MODEL", "NARRATE_STORE", "NARRATE_LEXICAL_DIR", "NARRATE_SIM_MODEL", "NARRATE_SIM_PYTHON")


def slides_example():
    rows = json.loads((EXAMPLES / "narrated-videos.json").read_text())
    return copy.deepcopy(next(j for j in rows if j["id"] == "nv-fixture-slides"))


@pytest.fixture(autouse=True)
def no_whisper(monkeypatch, tmp_path):
    monkeypatch.setenv("NARRATE_WHISPER_MODEL", str(tmp_path / "no-whisper-model.bin"))


class Bench(Workspace):
    """A fixture workspace whose ctx resolves the kitpip stub."""

    def ctx(self):
        pin = kitpip.load_pin(EXTERNALS)
        return super().ctx() | {"pin": pin, "kitpip": kitpip.resolve(pin, {kitpip.BIN_ENV: str(STUB)})}

    def slides_job(self, job_id, **edits):
        job = self.job(job_id, bed=None)
        example = slides_example()
        job["avatar"] = copy.deepcopy(example["avatar"]) | {"renderSize": 128}
        job["labels"]["persona"] = "fixture-persona"
        job["slides"] = copy.deepcopy(example["slides"])
        job["delivery"]["profile"] = "Contingency"
        job["base"]["card"]["colour"] = GREY
        for path, value in edits.items():
            node = job
            *parents, last = path.split(".")
            for part in parents:
                node = node[part]
            node[last] = value
        return job


def node_dir(s, node):
    return s.dir / s.entry(node)["dir"]


def frame_rgb(video, at_s, size):
    """The RGB pixels of the frame at at_s, as bytes, and a pixel reader."""
    w, h = size["w"], size["h"]
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{at_s:.3f}", "-i", str(video), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    ).stdout  # fmt: skip
    assert len(raw) == w * h * 3

    def pixel(x, y):
        i = (y * w + x) * 3
        return tuple(raw[i : i + 3])

    return pixel


def close(a, b, tolerance):
    return all(abs(x - y) <= tolerance for x, y in zip(a, b, strict=True))


def luma(rgb):
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b


# The simple job: compose, deliver_check, captions and description -------------------------------------------------
@pytest.fixture(scope="module")
def simple(tmp_path_factory, ffmpeg):
    with pytest.MonkeyPatch.context() as mp:
        base = tmp_path_factory.mktemp("simple")
        for name in HOST_ENV:
            mp.delenv(name, raising=False)
        mp.setenv("NARRATE_WHISPER_MODEL", str(base / "no-whisper-model.bin"))
        ws = Bench(base)
        job = ws.job("nv-compose")
        job["delivery"]["profile"] = "Contingency"
        job["labels"] = {"persona": None, "personaCue": CUE, "extraNotice": "Fixture notice."}
        s, result, _ = ws.run(job)
    return {"ws": ws, "job": job, "store": s, "result": result}


def test_a_simple_job_composes_a_profiled_cut_with_captions_and_a_description(simple):
    result, s = simple["result"], simple["store"]
    assert result["ok"] is True and {"compose", "deliver_check"} <= set(ran(result))
    m = s.manifest("compose")
    out = node_dir(s, "compose")
    assert sorted(m["outputs"]) == [
        "captions.srt", "captions.vtt", "chapters.json", "compose.json", "description.txt", "video.mp4",
        "video.upload.mp4",
    ]  # fmt: skip
    mix = s.manifest("mix")["measurements"]
    measured = m["measurements"]
    assert measured["size"] == {"w": 1280, "h": 720} and measured["fps"] == {"num": 30, "den": 1}
    assert measured["frames"] == round(mix["total_samples"] * 30 / RATE_HZ)
    assert (measured["video_codec"], measured["pix_fmt"], measured["audio_codec"]) == ("h264", "yuv420p", "aac")
    assert measured["subtitle_tracks"] == 1 and measured["overlays"] == [] and measured["slides"] is None
    probe = json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(out / "video.upload.mp4")],
            capture_output=True,
            check=True,
        ).stdout
    )
    assert sorted(st["codec_type"] for st in probe["streams"]) == ["audio", "video"]
    # Captions: the narrate run's cues on the base clock, the persona cue on its own line above the first one.
    narrated = (node_dir(s, "voice/seg-1") / RUN / "narration.srt").read_text()
    cues = compose.parse_cues((out / "captions.srt").read_text())
    source = compose.parse_cues(narrated)
    assert [(a, b) for a, b, _ in cues] == [(a, b) for a, b, _ in source]
    assert cues[0][2] == f"{CUE}\n{source[0][2]}"
    assert compose.parse_cues((out / "captions.vtt").read_text()) == cues
    text = (out / "description.txt").read_text()
    assert text.startswith("nv-compose\n") and text.rstrip("\n").endswith("Fixture notice.")
    assert "00:00 seg-1" in text
    assert m["timeline"]["mapping"] == "narrated_video_v1" and m["timeline"]["no_time_stretch"] is False
    assert m["labels"] == s.manifest("mix")["labels"] and m["synthetic"] is True
    assert m["states"]["listening"] == "pending_operator" and "lip_sync" not in m["states"]


def test_deliver_check_reports_every_gate_and_keeps_upload_closed(simple):
    s, job = simple["store"], simple["job"]
    report = json.loads((node_dir(s, "deliver_check") / "deliver_check.json").read_text())
    assert report["gates"] == {
        "profile": "passed", "loudness": "passed", "flash": "not_applicable", "captions": "passed",
        "listening": "pending_operator", "lip_sync": "not_applicable", "bed_licence_pdf": "not_applicable",
        "bed_content_id": "not_applicable",
    }  # fmt: skip
    assert report["profile"]["findings"] == {} and abs(report["loudness"]["drift_lu"]) <= job["delivery"]["driftLu"]
    assert report["loudness"]["true_peak_dbtp"] <= -1.5
    assert report["delivery_gate"]["internal_review_allowed"] is True
    assert report["delivery_gate"]["upload_gates_closed"] is False  # upload is off
    assert report["delivery_gate"]["public_upload_allowed"] is False
    assert report["edition"]["verdict"] == "Admitted" and report["edition"]["leaves"]["syntheticVoice"] is True


def test_upload_with_an_unlicensed_bed_leaves_deliver_check_pending_operator(simple, tmp_path):
    ws = simple["ws"]
    job = copy.deepcopy(simple["job"])
    job["delivery"]["upload"] = True
    s = ws.store(job, replace=True)
    rc = run.RunContext(job, ws.records, s, ws.ctx(), ws.env)
    result, g = run.run(rc)
    states = {n["id"]: n["state"] for n in g["nodes"]}
    assert ran(result) == ["deliver_check"] and states["deliver_check"] == "pending_operator"
    report = json.loads((node_dir(s, "deliver_check") / "deliver_check.json").read_text())
    assert report["gates"]["bed_licence_pdf"] == report["gates"]["bed_content_id"] == "pending_operator"
    assert report["delivery_gate"]["public_upload_allowed"] is False
    # Recording the operator's licence digest and a clear Content ID result reruns deliver_check only.
    ws.edit_records("music-beds.json", lambda rows: rows[0]["licence"].update(
        certifiedPdfSha256="f" * 64, contentIdCheck={"clear": "fixture-check-1"}))  # fmt: skip
    rc = run.RunContext(job, ws.records, s, ws.ctx(), ws.env)
    result, g = run.run(rc)
    assert ran(result) == ["deliver_check"]
    report = json.loads((node_dir(s, "deliver_check") / "deliver_check.json").read_text())
    assert report["delivery_gate"]["upload_gates_closed"] is True
    # Verified is not accepted: listening stays an operator state, so public upload stays closed (NV-2).
    assert report["delivery_gate"]["operator_states_open"] == ["listening"]
    assert report["delivery_gate"]["public_upload_allowed"] is False
    ws.edit_records("music-beds.json", lambda rows: rows[0]["licence"].update(
        certifiedPdfSha256=None, contentIdCheck="NotRun"))  # fmt: skip


# Profiles ------------------------------------------------------------------------------------------------------
def test_each_profile_sets_size_rate_and_codecs(tmp_path, ffmpeg):
    ws = Bench(tmp_path)
    video = tmp_path / "base-25.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=8", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", "-threads", "2", str(video)],
        check=True,
    )  # fmt: skip
    digest = ws.add_source(video)
    want = {
        "Web1080p30": ((1920, 1080), (30, 1)),
        "Talk": ((1920, 1080), (25, 1)),
        "Contingency": ((1280, 720), (30, 1)),
    }
    for name, (size, rate) in want.items():
        job = ws.job(f"nv-{name.lower()}", bed=None)
        job["base"] = {"video": {"sha256": digest, "keepBaseAudio": False}}
        job["delivery"]["profile"] = name
        s, result, _ = ws.run(job)
        assert result["ok"], result
        m = s.manifest("compose")["measurements"]
        assert (m["size"]["w"], m["size"]["h"]) == size and (m["fps"]["num"], m["fps"]["den"]) == rate
        assert m["frames"] == 8 * rate[0] and m["length_s"] == 8
        report = json.loads((node_dir(s, "deliver_check") / "deliver_check.json").read_text())
        assert report["gates"]["profile"] == "passed", report["profile"]
    assert compose.profile_for("Talk", {"num": 24000, "den": 1001})["fps"] == {"num": 24000, "den": 1001}


def test_the_profile_gate_names_each_field_off_its_profile():
    probe = {"streams": [
        {"codec_type": "video", "codec_name": "hevc", "pix_fmt": "yuv444p", "width": 1280, "height": 720,
         "avg_frame_rate": "25/1", "nb_frames": "10"},
        {"codec_type": "audio", "codec_name": "aac", "sample_rate": "44100", "channels": 2},
    ]}  # fmt: skip
    profile = compose.profile_for("Web1080p30", {"num": 30, "den": 1})
    state, findings = deliver.profile_gate(probe, profile, "Mono", 300, True)
    assert state == "failed"
    assert set(findings) == {"video_codec", "pix_fmt", "size", "fps", "frames", "audio_rate_hz", "audio_channels",
                             "subtitle_tracks"}  # fmt: skip


# Alpha, avatar default and avatarOff ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def slides(tmp_path_factory, ffmpeg):
    """The slides example (two generated slides as a lower-left card, a base page, a 0.4 s hold, the avatar off on
    the second slide) on a grey card at the Contingency profile, with the kitpip stub as the avatar."""
    with pytest.MonkeyPatch.context() as mp:
        base = tmp_path_factory.mktemp("slides")
        for name in HOST_ENV:
            mp.delenv(name, raising=False)
        mp.setenv("NARRATE_WHISPER_MODEL", str(base / "no-whisper-model.bin"))
        ws = Bench(base)
        job = ws.slides_job("nv-slides", **{"delivery.handoff": True})
        s, result, _ = ws.run(job)
    return {"ws": ws, "job": job, "store": s, "result": result}


def test_the_slides_job_runs_every_stage_to_handoff(slides):
    result = slides["result"]
    assert result["ok"], result
    assert {n: st for n, st in result["states"].items() if st != "fresh"} == {"music": "not_selected"}
    m = slides["store"].manifest("compose")
    assert m["states"]["lip_sync"] == "pending_operator"
    assert m["labels"]["persona"] == "fixture-persona" and m["labels"]["consent_ids"] == ["consent-fixture-sine"]


def test_a_transparent_overlay_pixel_equals_the_base_pixel_after_compose(slides):
    s = slides["store"]
    m = s.manifest("compose")["measurements"]
    box = m["overlays"][0]["box"]
    assert m["overlays"][0]["corner"] == "BR" and box["w"] == compose.even(0.22 * 1280)
    assert (box["x"], box["y"]) == (1280 - 32 - box["w"], 720 - 32 - box["w"])
    pixel = frame_rgb(node_dir(s, "compose") / "video.mp4", 4.6, m["size"])  # the body page: no slide, avatar on
    base = pixel(400, 200)
    assert close(base, (128, 128, 128), 4)
    assert close(pixel(box["x"] + 8, box["y"] + 8), base, 4)  # the stub's transparent corner
    assert close(pixel(box["x"] + box["w"] - 9, box["y"] + box["w"] - 9), base, 4)
    assert close(pixel(box["x"] + box["w"] // 2, box["y"] + box["w"] // 2), STUB_SQUARE, 14)  # its opaque square


def test_the_avatar_is_off_for_the_whole_span_of_an_avatar_off_page_with_fades(slides):
    s = slides["store"]
    m = s.manifest("compose")["measurements"]
    assert m["avatar_off"] == [{"start_s": 2.0, "end_s": 4.0, "fade_s": 0.35}]
    box = m["overlays"][0]["box"]
    centre = (box["x"] + box["w"] // 2, box["y"] + box["w"] // 2)
    video = node_dir(s, "compose") / "video.mp4"

    def centre_vs_around(at):
        pixel = frame_rgb(video, at, m["size"])
        return pixel(*centre), pixel(box["x"] - 20, box["y"] + box["w"] // 2)

    on, _ = centre_vs_around(1.0)
    assert close(on, STUB_SQUARE, 14)
    for at in (2.05, 3.0, 3.95):  # inside the off page: the box shows what is under it
        here, around = centre_vs_around(at)
        assert close(here, around, 4), at
    half, around = centre_vs_around(1.82)  # halfway through the fade out before the page
    assert not close(half, STUB_SQUARE, 14) and not close(half, around, 4)
    after, _ = centre_vs_around(4.5)
    assert close(after, STUB_SQUARE, 14)


# Slides --------------------------------------------------------------------------------------------------------
def test_the_slide_card_sits_lower_left_dims_the_held_frame_and_crossfades_in_place(slides):
    s = slides["store"]
    m = s.manifest("compose")["measurements"]
    run_plan = m["slides"]["runs"]
    assert m["slides"]["layout"] == "CardLowerLeft" and len(run_plan) == 1
    assert run_plan[0]["pages"] == ["slide-a", "slide-b"] and run_plan[0]["dim_to"] == 0.5
    card = run_plan[0]["layers"][0]["box"]
    assert card["w"] == compose.even(0.42 * 1280) and card["h"] == compose.even(card["w"] * 180 / 320)
    assert (card["x"], card["y"] + card["h"]) == (64, 720 - 64)
    video = node_dir(s, "compose") / "video.mp4"
    inside = (card["x"] + card["w"] // 2, card["y"] + card["h"] - 20)  # the slide's light field
    outside = (700, 120)
    one = frame_rgb(video, 1.0, m["size"])
    assert close(one(*inside), (232, 228, 216), 8)
    after = frame_rgb(video, 4.6, m["size"])
    assert close(after(*inside), (128, 128, 128), 4)
    # The background dims to half its brightness while the card shows, and lifts after it.
    ratio = luma(one(*outside)) / luma(after(*outside))  # full-range RGB: 0 is black
    assert 0.45 <= ratio <= 0.55, ratio
    # At the page change the incoming slide is half in: the average of the two slides' fields.
    mid = frame_rgb(video, 2.0, m["size"])(*inside)
    a, b = (232, 228, 216), (214, 228, 240)
    assert close(mid, tuple((x + y) / 2 for x, y in zip(a, b, strict=True)), 6), mid
    two = frame_rgb(video, 3.0, m["size"])
    assert close(two(*inside), b, 8)


def test_the_flash_gate_passes_the_card_and_fails_a_hard_full_frame_cut(slides, tmp_path):
    s = slides["store"]
    report = json.loads((node_dir(s, "deliver_check") / "deliver_check.json").read_text())
    assert report["gates"]["flash"] == "passed" and report["flash"]["max"] == 0.30
    assert report["flash"]["worst"] <= 0.30
    assert [c["at_s"] for c in report["flash"]["changes"]] == [0.0, 2.0, 4.0, 5.0, 5.4]
    ws = Bench(tmp_path)
    hard = ws.slides_job("nv-hard", **{"base.card.colour": "#101820"})
    hard["slides"] |= {"layout": "Full", "fadeS": 0.04}
    hard["slides"]["pages"] = [
        {"id": "dark", "startS": 0, "endS": 1, "show": "Base"},
        {"id": "bright", "startS": 1, "endS": 3, "show": hard["slides"]["pages"][0]["show"]},
    ]
    hard["avatar"]["avatarOff"] = []
    s2, result, _ = ws.run(hard)
    assert result["ok"], result
    report = json.loads((node_dir(s2, "deliver_check") / "deliver_check.json").read_text())
    assert report["gates"]["flash"] == "failed" and report["flash"]["worst"] > 0.30
    assert report["delivery_gate"]["internal_review_allowed"] is False


def test_a_full_slide_at_the_default_fade_passes_the_flash_gate_on_the_default_card(tmp_path, ffmpeg):
    """The defaults: layout Full, fadeS 0.35 and the #101820 card under a light fixture slide. A linear alpha ramp
    jumps about 40% on its first frame here; the eased fade keeps every frame under 30%."""
    ws = Bench(tmp_path)
    job = ws.slides_job("nv-full", **{"base.card.colour": DEFAULTS["colour"]})
    job["slides"] = copy.deepcopy(DEFAULTS["slides"]) | {"pages": [
        {"id": "open", "startS": 0, "endS": 1, "show": "Base"},
        {"id": "bright", "startS": 1, "endS": 3, "show": job["slides"]["pages"][0]["show"]},
        {"id": "close", "startS": 3, "endS": 4, "show": "Base"},
    ]}  # fmt: skip
    assert (job["slides"]["layout"], job["slides"]["fadeS"]) == ("Full", 0.35)
    job["avatar"] = None
    job["labels"]["persona"] = None
    s, result, _ = ws.run(job)
    assert result["ok"], result
    layer = s.manifest("compose")["measurements"]["slides"]["runs"][0]["layers"][0]
    ease = layer["ease"]
    assert ease["in"]["under_y"] == ease["out"]["under_y"] and ease["in"]["under_y"] < 40
    assert ease["in"]["over_y"] > 180 and ease["in"]["min_fade_s"] <= 0.35
    report = json.loads((node_dir(s, "deliver_check") / "deliver_check.json").read_text())
    assert report["gates"]["flash"] == "passed" and report["flash"]["worst"] <= 0.30, report["flash"]
    assert [c["at_s"] for c in report["flash"]["changes"]] == [1, 3]
    assert report["delivery_gate"]["internal_review_allowed"] is True


def test_the_card_on_a_video_base_holds_the_next_clip_frame_dimmed_and_hands_over_without_a_step(tmp_path, ffmpeg):
    ws = Bench(tmp_path)
    video = tmp_path / "base.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=8", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", "-threads", "2", str(video)],
        check=True,
    )  # fmt: skip
    job = ws.slides_job("nv-held")
    job["base"] = {"video": {"sha256": ws.add_source(video), "keepBaseAudio": False}}
    slide = job["slides"]["pages"][0]["show"]
    job["slides"]["pages"] = [{"id": "open", "startS": 0, "endS": 1, "show": "Base"},
                              {"id": "card", "startS": 1, "endS": 3, "show": slide}]  # fmt: skip
    job["avatar"] = None
    job["labels"]["persona"] = None
    s, result, _ = ws.run(job)
    assert result["ok"], result
    m = s.manifest("compose")["measurements"]
    run_plan = m["slides"]["runs"][0]
    assert run_plan["held"] == "base frame at the run's end" and run_plan["dim_to"] == 0.5
    out = node_dir(s, "compose") / "video.mp4"
    points = [(700, 100), (900, 300), (1100, 500), (1200, 150), (800, 650)]  # all outside the card

    def lumas(at):
        pixel = frame_rgb(out, at, m["size"])
        return [luma(pixel(*p)) for p in points], pixel

    early, early_px = lumas(1.6)  # the card is in: the held frame, dimmed
    late, late_px = lumas(2.4)
    after, after_px = lumas(3.0)  # the live base at the run's end: the frame that was held
    edge, _ = lumas(2.96)  # the last frame of the run
    assert all(close(early_px(*p), late_px(*p), 4) for p in points)  # held: nothing moves under the card
    assert 0.45 <= sum(early) / sum(after) <= 0.55, (early, after)  # dimmed to dimTo of the next clip's frame
    assert sum(edge) / sum(after) >= 0.9, (edge, after)  # the dim has lifted: the handover has no step
    live, _ = lumas(0.5)
    assert live != after  # the base moves outside the run
    report = json.loads((node_dir(s, "deliver_check") / "deliver_check.json").read_text())
    assert report["gates"]["flash"] == "passed", report["flash"]


def test_a_hold_page_on_a_video_base_holds_the_frame_at_its_start(tmp_path, ffmpeg):
    ws = Bench(tmp_path)
    video = tmp_path / "base.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=8", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", "-threads", "2", str(video)],
        check=True,
    )  # fmt: skip
    job = ws.slides_job("nv-hold")
    job["base"] = {"video": {"sha256": ws.add_source(video), "keepBaseAudio": False}}
    job["slides"]["pages"] = [{"id": "run", "startS": 0, "endS": 6, "show": "Base"},
                              {"id": "end", "startS": 6, "endS": 7, "show": "Hold"}]  # fmt: skip
    job["avatar"] = None
    job["labels"]["persona"] = None
    s, result, _ = ws.run(job)
    assert result["ok"], result
    m = s.manifest("compose")["measurements"]
    assert m["slides"]["holds"] == [{"page": "end", "start_s": 6, "end_s": 7}]
    out = node_dir(s, "compose") / "video.mp4"
    frames = [frame_rgb(out, t, m["size"]) for t in (6.0, 6.5, 6.9)]
    points = [(40, 40), (640, 360), (1000, 600)]
    assert all(close(f(*p), frames[0](*p), 3) for f in frames[1:] for p in points)
    moving = frame_rgb(out, 7.5, m["size"])
    assert not all(close(moving(*p), frames[0](*p), 3) for p in points)


def test_slide_runs_layers_and_avatar_off_spans_are_planned_exactly():
    page = lambda i, a, b, show: {"id": i, "startS": a, "endS": b, "show": show}  # noqa: E731
    slide = {"slide": {"sha256": "1" * 64}}
    pages = [page("a", 0, 2, slide), page("b", 2, 4, slide), page("c", 4, 5, "Base"), page("d", 5, 6, slide),
             page("e", 6, 6.4, "Hold")]  # fmt: skip
    runs = compose.slide_runs(pages)
    assert [(r["start"], r["end"], [p["id"] for p in r["pages"]]) for r in runs] == [(0, 4, ["a", "b"]), (5, 6, ["d"])]
    layers = compose.slide_layers(runs[0], 0.4)
    assert [(x["start"], x["end"], x["fade_in"], x["fade_out"]) for x in layers] == [
        (0, 2.2, (0.0, 0.4), None),
        (1.8, 4, (0.0, 0.4), (1.8, 0.4)),
    ]
    assert compose.slide_layers(runs[1], 0.4)[0]["fade_out"] == (0.6, 0.4)
    assert deliver.slide_changes(pages) == [0, 2, 4, 5, 6, 6.4]
    assert compose.avatar_off_spans(pages, ["b", "a", "e"], 6.2) == [(0, 4), (6, 6.2)]
    with pytest.raises(StageRefused) as caught:
        compose.avatar_off_spans(pages, ["b", "deck-06"], 6.2)  # an id compose has no span for
    assert caught.value.code == "page_unknown" and caught.value.verdict is True
    filters = compose.avatar_off_filters([(0, 4), (6, 6.2)], 0.35, 6.2)
    assert filters == [
        "lut=a=0:enable='between(t,0.000000,4.000000)'",  # from the first frame: no fade out before the start
        "fade=t=in:st=4.000000:d=0.350000:alpha=1:enable='between(t,4.000000,4.350000)'",
        "fade=t=out:st=5.650000:d=0.350000:alpha=1:enable='between(t,5.650000,6.000000)'",
        "lut=a=0:enable='between(t,6.000000,6.200000)'",
    ]


def test_an_avatar_off_page_at_the_program_start_hides_the_first_frame(tmp_path, ffmpeg):
    filters = ",".join(compose.avatar_off_filters([(0, 1)], 0.35, 2))
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=white:s=16x16:r=30:d=2",
         "-vf", f"format=yuva420p,{filters},alphaextract", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, check=True,
    ).stdout  # fmt: skip
    alpha = [raw[i * 256] for i in range(len(raw) // 256)]
    assert len(alpha) == 60
    assert alpha[:31] == [0] * 31  # frames 0 to 30 (t = 0 to 1 s): hidden from the first frame
    assert 0 < alpha[36] < 255 and alpha[45:] == [255] * 15  # fading back in, then opaque


def test_the_card_fits_a_tall_slide_inside_the_frame():
    assert compose.card_box(0.42, 64, 1920, 1080, 320, 180) == (64, 1080 - 64 - 454, 806, 454)
    x, y, cw, ch = compose.card_box(0.42, 64, 1920, 1080, 180, 320)  # portrait
    assert (x, y, ch) == (64, 64, 952) and cw == compose.even(952 * 180 / 320)
    x, y, cw, ch = compose.card_box(0.42, 64, 1280, 720, 1000, 1001)  # just taller than wide
    assert y >= 64 and y + ch == 720 - 64 and cw <= compose.even(0.42 * 1280)


def test_eased_fades_step_the_mean_luma_by_one_ratio():
    assert compose.eased_fade("in", 0.0, 0.35, 100, 100) == "fade=t=in:st=0.000000:d=0.350000:alpha=1"
    eased = compose.eased_fade("out", 1.65, 0.35, 35, 189)
    assert eased.startswith("geq=") and "between(t,1.650000,2.000000)" in eased and "(2.000000-T)" in eased
    # The curve: alpha a(t) = (r^t - 1) / (r - 1) puts Y = under + a (over - under) on under * r^t.
    under, over, frames = 35.0, 189.0, 10
    r = over / under
    ys = [under + (r ** (n / frames) - 1) / (r - 1) * (over - under) for n in range(frames + 1)]
    worst = max(deliver.jump(a, b) for a, b in zip(ys, ys[1:], strict=False))
    linear = deliver.jump(under, under + (over - under) / frames)
    assert worst == pytest.approx(r ** (1 / frames) - 1) and worst < 0.30 < linear
    assert compose.min_fade_s(35, 189, {"num": 30, "den": 1}) == round(7 / 30, 6)
    assert compose.min_fade_s(16, 235, {"num": 30, "den": 1}) == round(11 / 30, 6)  # black to white: over 0.35 s


def test_the_flash_measure_is_relative_to_the_darker_frame_with_a_black_floor():
    assert deliver.jump(100, 130) == 0.3 and deliver.jump(130, 100) == 0.3
    assert deliver.jump(16, 70) == pytest.approx(3.375) and deliver.jump(4, 8) == 0.25
    yavg = [20] * 30 + [88] * 30
    report = deliver.flash_report(yavg, [1.0, 1.5], {"num": 30, "den": 1}, 0.1)
    assert report[0] == {"at_s": 1.0, "max_jump": 3.4, "frame": 30} and report[1]["max_jump"] == 0


# Labels, captions and refusals ---------------------------------------------------------------------------------
def test_the_captions_gate_finds_a_missing_cue_notice_or_file():
    job = {"captions": dict(DEFAULTS["captions"]), "labels": {"persona": None, "personaCue": "Cue",
                                                               "extraNotice": "Notice"}}  # fmt: skip
    cues = [(0, 1, "Cue\nHello")]
    assert deliver.captions_gate(job, {"captions.srt", "captions.vtt"}, cues, "x\nNotice\n", 1) == ("passed", [])
    state, findings = deliver.captions_gate(job, {"captions.srt"}, [(0, 1, "Hello")], "x\n", 0)
    assert state == "failed" and len(findings) == 4


def test_a_dropped_leaf_label_breaks_the_chain_at_deliver_check(simple, monkeypatch):
    ws = simple["ws"]
    job = copy.deepcopy(simple["job"])
    s = ws.store(job, replace=True)
    rc = run.RunContext(job, ws.records, s, ws.ctx(), ws.env)
    real = deliver.leaves_labels

    def extra_leaf(rc):
        derived, parents = real(rc)
        leaf = copy.deepcopy(parents[0])
        leaf["labels"]["consent_ids"] = leaf["labels"]["consent_ids"] + ["consent-the-compose-dropped"]
        return derived, parents + [leaf]

    monkeypatch.setattr(deliver, "leaves_labels", extra_leaf)
    result, g = run.run(rc, forced=["deliver_check"])
    assert result["refused"] == "label_chain_broken" and result["node"] == "deliver_check" and result["recorded"]
    monkeypatch.setattr(deliver, "leaves_labels", real)
    result, _ = run.run(rc, forced=["deliver_check"])
    assert result["ok"] and ran(result) == ["deliver_check"]


def test_compose_refuses_a_broken_label_chain(simple, monkeypatch):
    ws = simple["ws"]
    job = copy.deepcopy(simple["job"])
    s = ws.store(job, replace=True)
    real = labels.grow
    monkeypatch.setattr(labels, "grow", lambda parents, persona: real(parents, persona) | {"consent_ids": []})
    rc = run.RunContext(job, ws.records, s, ws.ctx(), ws.env)
    result, _ = run.run(rc, forced=["compose"])
    assert result["refused"] == "label_chain_broken" and result["node"] == "compose"
    monkeypatch.setattr(labels, "grow", real)
    result, _ = run.run(rc, forced=["compose"])
    assert result["ok"] and set(ran(result)) >= {"compose"}


def test_edition_at_deliver_check_refuses_an_overlay_in_a_voice_only_cut():
    job = {"edition": "ClientVoiceOnly", "music": None, "delivery": {"voiceOnlyListen": None}}
    with pytest.raises(StageRefused) as caught:
        deliver.edition_at_deliver(job, None, {"synthetic": False}, [{"segment": "seg-1"}])
    assert caught.value.code == "edition_pip_refused"
    with pytest.raises(StageRefused) as caught:
        deliver.edition_at_deliver(job, None, {"synthetic": True}, [])
    assert caught.value.code == "edition_voice_refused"
    narrated = job | {"edition": "ClientNarrated"}
    assert deliver.edition_at_deliver(narrated, None, {"synthetic": True}, [{}])["verdict"] == "Admitted"


@pytest.mark.parametrize(
    "edit, code",
    [
        (lambda j: j["captions"].update(burn=True), "captions_burn_unsupported"),
        (lambda j: j["slides"]["pages"].append({"id": "late", "startS": 5.4, "endS": 60, "show": "Base"}),
         "slides_exceed_program"),
    ],
)  # fmt: skip
def test_compose_verdicts_are_recorded_for_their_key(tmp_path, ffmpeg, edit, code):
    ws = Bench(tmp_path)
    job = ws.slides_job("nv-refuse")
    edit(job)
    s, result, g = ws.run(job)
    assert result["refused"] == code and result["node"] == "compose" and result["recorded"] is True
    assert {n["id"]: n["state"] for n in g["nodes"]}["compose"] == "refused"


@pytest.mark.parametrize(
    "edit, code",
    [
        (lambda j: j["slides"]["pages"][1].update(startS=1.0), "slides_invalid"),
        (lambda j: j["slides"].update(cardWidth=0.9), "knob_out_of_bounds"),
        (lambda j: j["avatar"].update(avatarOff=["no-such-page"]), "page_unknown"),
        (lambda j: j["avatar"].update(fadeS=5), "knob_out_of_bounds"),
        (lambda j: j["slides"]["pages"][0].update(endS=0.3), "slides_invalid"),
    ],
)
def test_admit_refuses_slides_that_break_the_rules(edit, code):
    recs = load_records(EXAMPLES)
    job = slides_example()
    assert admit.admit(job, recs)["verdict"] == "Admitted"
    edit(job)
    assert code in [r["code"] for r in admit.admit(job, recs)["refusals"]]


# Handoff -------------------------------------------------------------------------------------------------------
def test_handoff_writes_the_pre_vfx_layers_and_edit_json(slides):
    s = slides["store"]
    out = node_dir(s, "handoff")
    m = s.manifest("handoff")
    assert m["measurements"]["layers"] == sorted([
        "layers/avatar-seg-1.manifest.json", "layers/avatar-seg-1.mov", "layers/base.mp4", "layers/captions.srt",
        "layers/captions.vtt", "layers/slide-slide-a.png", "layers/slide-slide-b.png", "layers/voice.wav",
    ])  # fmt: skip
    edit = json.loads((out / "edit.json").read_text())
    assert edit["kind"] == "nv_edit" and edit["profile"]["frames"] == s.manifest("compose")["measurements"]["frames"]
    assert edit["overlays"][0]["file"] == "layers/avatar-seg-1.mov"
    assert edit["overlays"][0]["manifest"] == "layers/avatar-seg-1.manifest.json"
    assert edit["overlays"][0]["renderer_kind"] == "kitpip"
    assert set(edit["stage_keys"]) == {"base", "place", "mix", "compose", "avatar/seg-1"}
    assert edit["stage_keys"]["compose"] == s.entry("compose")["key"]
    assert edit["export"]["application_import"] == "unverified"
    slide_a = hashlib.sha256((out / "layers" / "slide-slide-a.png").read_bytes()).hexdigest()
    assert slide_a == slides["job"]["slides"]["pages"][0]["show"]["slide"]["sha256"]
    mov = hashlib.sha256((out / "layers" / "avatar-seg-1.mov").read_bytes()).hexdigest()
    assert mov == s.manifest("avatar/seg-1")["outputs"]["overlay/overlay.mov"]
    probe = json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(out / "layers" / "base.mp4")],
            capture_output=True,
            check=True,
        ).stdout
    )
    assert [st["codec_type"] for st in probe["streams"]] == ["video"]
    assert int(probe["streams"][0]["nb_frames"]) == edit["profile"]["frames"]
    assert m["timeline"]["mapping"] == "narrated_video_v1" and m["states"]["application_import"] == "unverified"


def test_a_layout_or_avatar_off_change_reruns_compose_and_what_follows_only(slides, tmp_path):
    shutil.copytree(slides["ws"].base, tmp_path / "copy")
    ws = Bench.__new__(Bench)
    ws.base = tmp_path / "copy"
    ws.paths = {name: ws.base / "ws" / name for name in ("records", "store", "lexical")}
    ws.paths["script"] = ws.paths["store"] / "script.md"
    ws.reload()
    job = copy.deepcopy(slides["job"])
    job["avatar"]["avatarOff"] = []
    s, result, _ = ws.run(job, replace=True)
    assert sorted(ran(result)) == ["compose", "deliver_check", "handoff"]
    job["slides"]["layout"] = "Full"
    s, result, _ = ws.run(job, replace=True)
    assert sorted(ran(result)) == ["compose", "deliver_check", "handoff"]
    assert s.manifest("compose")["measurements"]["avatar_off"] == []


def test_cli_init_keeps_the_avatar_on_by_default_and_run_waits_for_the_kitpip_binary(tmp_path, capsys, ffmpeg):
    code = cli.main(["fixture", "--out", str(tmp_path / "ws")])
    paths = json.loads(capsys.readouterr().out)
    common = ["--root", str(tmp_path / "narrated"), "--records", paths["records"]]
    argv = ["init", "--job", "nv-default", "--narrate-job", paths["narrate_job"], "--script", paths["script"]]
    code = cli.main(argv + ["--persona", "fixture-persona"] + common)
    capsys.readouterr()
    assert code == 0
    run_args = common + ["--store", paths["store"], "--lexical", paths["lexical"], "--json"]
    code = cli.main(["run", "nv-default"] + run_args)
    result = json.loads(capsys.readouterr().out)
    # No kitpip binary is named: the avatar blocks, and compose waits for it instead of composing without it.
    assert code == 1 and result["states"]["avatar/seg-1"] == "blocked" and result["states"]["mix"] == "fresh"
    assert result["states"]["compose"] == "blocked" and result["refused"] == "kitpip_missing"
    assert result["waiting_on_lane"] == {}
    plan = graph.public(graph.plan(*plan_args(tmp_path, paths)))
    assert {n["id"]: n["reason"] for n in plan["nodes"]}["avatar/seg-1"] == "kitpip_missing"


def plan_args(tmp_path, paths):
    from narrate.video import store

    s = store.JobStore(tmp_path / "narrated", "nv-default")
    ctx = {"pin": None, "kitpip": kitpip.resolve(None), "ffmpeg": cli.ffmpeg_identity(), "sources": None}
    return s.read_job(), load_records(paths["records"]), s, ctx
