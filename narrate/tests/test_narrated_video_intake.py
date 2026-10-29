"""Demo bundle intake and the spoken-number claims gate (docs/spec/NARRATED_VIDEO.md, "Demo bundle intake", TIN-7735).

Every bundle here is synthetic: fixture.write_bundle's generated slide pictures and 1x1 GIF, an FFmpeg test pattern
for the MP4 cases, fixture receipts and fixture text. No real demo, client text, recording or receipt is used.
"""

import hashlib
import json
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from narrate.video import bundle, claims, cli, fixture, store
from narrate.video.admit import admit
from narrate.video.job import check_shape, load_records

TEMPLATE, VOICE, ENGINE = fixture.NARRATE_JOB, "voice-fixture-sine", "fake-sine"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture(autouse=True)
def no_whisper(monkeypatch, tmp_path):
    monkeypatch.setenv("NARRATE_WHISPER_MODEL", str(tmp_path / "no-whisper-model.bin"))


@pytest.fixture
def ws(tmp_path):
    paths = fixture.write(tmp_path / "ws")
    paths["bundle"] = fixture.write_bundle(tmp_path / "bundles")
    return paths


def intake(ws, out, **kw):
    args = {"template": TEMPLATE, "voice": VOICE, "engine": ENGINE} | kw
    return bundle.intake(ws["bundle"], out, ws["records"], store=ws["store"], **args)


def manifest(b):
    return json.loads((b / "manifest.json").read_text())


def set_manifest(b, value):
    (b / "manifest.json").write_text(json.dumps(value, indent=1))


def set_claims(b, edit):
    rows = json.loads((b / "claims.json").read_text())
    edit(rows)
    (b / "claims.json").write_text(json.dumps(rows, indent=1))


def set_script(b, old, new):
    text = (b / "script.md").read_text()
    assert old in text
    (b / "script.md").write_text(text.replace(old, new))


def refused(code, fn, *args, **kw):
    with pytest.raises(bundle.BundleError) as caught:
        fn(*args, **kw)
    assert caught.value.code == code, caught.value.detail
    return caught.value


def add_asset(b, asset_id, name, kind, data):
    (b / "assets" / name).write_bytes(data)
    m = manifest(b)
    m["assets"].append(
        {
            "id": asset_id,
            "path": f"assets/{name}",
            "sha256": hashlib.sha256(data).hexdigest(),
            "kind": kind,
            "receipt": f"fixture-receipt-{asset_id}",
        }
    )
    set_manifest(b, m)


def make_mp4(path, seconds=20):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
         f"testsrc2=s=320x180:r=30:d={seconds}", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
         str(path)],
        check=True,
    )  # fmt: skip
    return Path(path).read_bytes()


# Happy path ------------------------------------------------------------------------------------------------------
def test_happy_path_writes_the_existing_shapes(ws, tmp_path):
    out = tmp_path / "out"
    m = intake(ws, out, persona=None)
    job = json.loads((out / "narrated-video.json").read_text())
    assert check_shape(job) == job
    assert job["edition"] == "Internal" and job["avatar"] is None and job["music"] is None
    assert "card" in job["base"]
    assert [s["id"] for s in job["segments"]] == ["intro", "result"]
    assert [s["anchor"] for s in job["segments"]] == [{"atSeconds": 0}, {"atSeconds": 8}]
    pages = job["slides"]["pages"]
    slides = {a["id"]: a["sha256"] for a in manifest(ws["bundle"])["assets"]}
    assert [(p["id"], p["startS"], p["endS"]) for p in pages] == [("intro", 0, 8), ("result", 8, 16.5)]
    assert [p["show"]["slide"]["sha256"] for p in pages] == [slides["slide-a"], slides["slide-b"]]

    records = load_records(out / "records")
    for segment in job["segments"]:
        narrate_job = records["jobs"][segment["narrateJob"]]
        assert narrate_job["input"] == "Markdown"
        assert narrate_job["confidential"] is True and narrate_job["allowHosted"] is False
        assert narrate_job["voice"] == VOICE and narrate_job["engine"] == ENGINE and narrate_job["speakers"] == []
        assert narrate_job["inputSha256"] == segment["scriptSha256"]
        script = ws["store"] / f"{segment['scriptSha256']}.md"
        assert sha(script) == segment["scriptSha256"]
        template = records["jobs"][TEMPLATE]
        assert narrate_job["lexical"] == template["lexical"] and narrate_job["gates"] == template["gates"]
    for digest in slides.values():
        if digest != slides["loop-a"]:
            assert (ws["store"] / f"{digest}.png").is_file()
    assert not (ws["store"] / f"{slides['loop-a']}.gif").exists()
    assert admit(job, records)["verdict"] == "Admitted"

    written = json.loads((out / "intake.json").read_text())
    assert written == m
    assert m["kind"] == "nv_bundle_intake" and m["unused_assets"] == ["loop-a"]
    assert [s["claims"]["status"] for s in m["segments"]] == ["passed", "passed"]
    matched = [(r["number"], r["unit"], r["claim"]) for s in m["segments"] for r in s["claims"]["mentions"]]
    assert matched == [("17.877", "ms", "build-ms"), ("42", "percent", "cache-rate"), ("400", "", "files")]
    assert m["outputs"]["narrated-video.json"] == sha(out / "narrated-video.json")
    assert str(tmp_path) not in json.dumps(m)  # the manifest names the slug and digests, never a path


def test_init_from_the_intake_and_plan(ws, tmp_path, capsys):
    out = tmp_path / "out"
    intake(ws, out)
    root = tmp_path / "narrated"
    common = ["--root", str(root), "--records", str(out / "records"), "--store", str(ws["store"])]
    assert cli.main(["init", "--job", "demo-fixture", "--from", str(out / "narrated-video.json"), *common]) == 0
    capsys.readouterr()
    assert cli.main(["plan", "demo-fixture", "--json", *common]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["admit"]["verdict"] == "Admitted"
    states = {n["id"]: n["state"] for n in plan["nodes"]}
    assert states["script/intro"] == states["script/result"] == "stale"
    assert not [n for n in plan["nodes"] if n["state"] == "blocked"]


def test_intake_runs_end_to_end_through_deliver_check(ws, tmp_path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg is not on PATH")
    out = tmp_path / "out"
    intake(ws, out)
    root = tmp_path / "narrated"
    common = ["--root", str(root), "--records", str(out / "records"), "--store", str(ws["store"]),
              "--lexical", str(ws["lexical"])]  # fmt: skip
    assert cli.main(["init", "--job", "demo-fixture", "--from", str(out / "narrated-video.json"), *common]) == 0
    assert cli.main(["run", "demo-fixture", *common]) == 0
    s = store.JobStore(root, "demo-fixture")
    current = json.loads((s.dir / "current.json").read_text())["stages"]
    place = json.loads((s.dir / current["place"]["dir"] / "manifest.json").read_text())["measurements"]
    assert [(p["id"], p["start_s"]) for p in place["segments"]] == [("intro", 0.0), ("result", 8.0)]
    deliver = json.loads((s.dir / current["deliver_check"]["dir"] / "manifest.json").read_text())["measurements"]
    assert deliver["delivery_gate"]["internal_review_allowed"] is True
    assert deliver["gates"]["listening"] == "pending_operator"
    assert deliver["delivery_gate"]["public_upload_allowed"] is False


def test_persona_turns_the_avatar_on(ws, tmp_path):
    intake(ws, tmp_path / "out", persona="fixture-persona")
    job = json.loads((tmp_path / "out" / "narrated-video.json").read_text())
    assert job["avatar"]["external"] == "kitpip" and job["labels"]["persona"] == "fixture-persona"


def test_cli_intake_needs_a_persona_or_no_avatar(ws, tmp_path, capsys):
    argv = ["intake", str(ws["bundle"]), "--out", str(tmp_path / "out"), "--records", str(ws["records"]),
            "--narrate-template", TEMPLATE, "--voice", VOICE, "--engine", ENGINE]  # fmt: skip
    assert cli.main(argv) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "persona_label_missing"
    assert cli.main([*argv, "--no-avatar", "--store", str(ws["store"])]) == 0
    assert json.loads(capsys.readouterr().out)["job_id"] == "demo-fixture"


def test_mp4_becomes_the_base_video_and_a_base_page(ws, tmp_path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg is not on PATH")
    b = ws["bundle"]
    data = make_mp4(tmp_path / "clip.mp4")
    add_asset(b, "clip", "clip.mp4", "mp4", data)
    set_script(b, "- asset_id: slide-b", "- asset_id: clip")
    intake(ws, tmp_path / "out")
    job = json.loads((tmp_path / "out" / "narrated-video.json").read_text())
    assert job["base"] == {"video": {"sha256": hashlib.sha256(data).hexdigest(), "keepBaseAudio": False}}
    assert [p["show"] for p in job["slides"]["pages"]][1] == "Base"
    assert (ws["store"] / f"{hashlib.sha256(data).hexdigest()}.mp4").is_file()


def test_only_mp4_beats_have_no_slides(ws, tmp_path):
    b = ws["bundle"]
    fake = b"\x00\x00\x00\x18ftypisom" + bytes(12)  # parse-level only: an ftyp box, never rendered here
    add_asset(b, "clip", "clip.mp4", "mp4", fake)
    set_script(b, "- asset_id: slide-a", "- asset_id: clip")
    set_script(b, "- asset_id: slide-b", "- asset_id: clip")
    job, _ = bundle.convert(
        bundle.read(b), load_records(ws["records"]), job_id="demo-fixture", template=TEMPLATE, voice=VOICE,
        engine=ENGINE,
    )  # fmt: skip
    assert job["slides"] is None and "video" in job["base"]


# Refusals: the bundle --------------------------------------------------------------------------------------------
def test_sha_mismatch_refuses(ws, tmp_path):
    (ws["bundle"] / "assets" / "slide-a.png").write_bytes(fixture.port().fixtures()["slide-b.png"])
    refused("asset_digest_mismatch", intake, ws, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_unknown_asset_refuses(ws, tmp_path):
    set_script(ws["bundle"], "- asset_id: slide-b", "- asset_id: slide-z")
    refused("asset_unknown", intake, ws, tmp_path / "out")


def test_missing_asset_file_refuses(ws, tmp_path):
    (ws["bundle"] / "assets" / "slide-a.png").unlink()
    refused("asset_missing", intake, ws, tmp_path / "out")


def test_symlinked_asset_refuses(ws, tmp_path):
    path = ws["bundle"] / "assets" / "slide-a.png"
    real = tmp_path / "elsewhere.png"
    shutil.move(path, real)
    path.symlink_to(real)
    refused("asset_missing", intake, ws, tmp_path / "out")


@pytest.mark.parametrize("path", ["../slide-a.png", "/etc/slide-a.png", "assets/./slide-a.png", "assets\\a.png"])
def test_asset_path_outside_the_bundle_refuses(ws, tmp_path, path):
    m = manifest(ws["bundle"])
    m["assets"][0]["path"] = path
    set_manifest(ws["bundle"], m)
    refused("bundle_invalid", intake, ws, tmp_path / "out")


def test_asset_bytes_must_be_their_kind(ws, tmp_path):
    b = ws["bundle"]
    add_asset(b, "slide-c", "slide-c.png", "png", fixture.GIF_1X1)
    refused("asset_kind_mismatch", bundle.read, b)


def test_png_size_must_match_the_manifest(ws):
    m = manifest(ws["bundle"])
    m["assets"][0]["size"] = {"w": 640, "h": 360}
    set_manifest(ws["bundle"], m)
    refused("asset_kind_mismatch", bundle.read, ws["bundle"])


def test_asset_without_a_receipt_refuses(ws):
    m = manifest(ws["bundle"])
    m["assets"][1]["receipt"] = " "
    set_manifest(ws["bundle"], m)
    refused("asset_unreceipted", bundle.read, ws["bundle"])


def test_unknown_manifest_field_refuses(ws):
    m = manifest(ws["bundle"])
    m["assets"][0]["note"] = "x"
    set_manifest(ws["bundle"], m)
    refused("bundle_invalid", bundle.read, ws["bundle"])


def test_gif_asset_refuses_with_a_conversion_message(ws, tmp_path):
    set_script(ws["bundle"], "- asset_id: slide-b", "- asset_id: loop-a")
    error = refused("asset_needs_conversion", intake, ws, tmp_path / "out")
    assert "convert it to a PNG still or an MP4 clip" in error.detail


def test_two_different_videos_refuse(ws):
    b = ws["bundle"]
    add_asset(b, "clip-a", "clip-a.mp4", "mp4", b"\x00\x00\x00\x18ftypisom" + bytes(12))
    add_asset(b, "clip-b", "clip-b.mp4", "mp4", b"\x00\x00\x00\x18ftypisom" + bytes(13))
    set_script(b, "- asset_id: slide-a", "- asset_id: clip-a")
    set_script(b, "- asset_id: slide-b", "- asset_id: clip-b")
    refused("asset_video_multiple", bundle.read, b)


# Refusals: the script --------------------------------------------------------------------------------------------
def test_missing_voiced_block_refuses(ws, tmp_path):
    text = (ws["bundle"] / "script.md").read_text()
    start = text.index("```voiced", text.index("## result"))
    (ws["bundle"] / "script.md").write_text(text[:start])
    refused("beat_voiced_missing", intake, ws, tmp_path / "out")


def test_empty_voiced_block_refuses(ws):
    text = (ws["bundle"] / "script.md").read_text()
    start = text.index("```voiced", text.index("## result"))
    (ws["bundle"] / "script.md").write_text(text[:start] + "```voiced\n\n```\n")
    refused("beat_voiced_missing", bundle.read, ws["bundle"])


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("## intro\n\n- target_s: 4\n- asset_id: slide-a\n\n```voiced\nHello.\n```\n", "beat_invalid"),  # no claims
        ("## intro\n- target_s: 0\n- asset_id: slide-a\n- claims:\n```voiced\nHello.\n```\n", "beat_invalid"),
        ("## intro\n- target_s: four\n- asset_id: slide-a\n- claims:\n```voiced\nHello.\n```\n", "beat_invalid"),
        ("## Intro\n- target_s: 4\n- asset_id: slide-a\n- claims:\n```voiced\nHello.\n```\n", "beat_invalid"),
        ("## a\n- target_s: 4\n- asset_id: x\n- claims:\n```voiced\nA.\n```\n## a\n", "beat_invalid"),
        ("## a\n- target_s: 4\n- target_s: 5\n", "beat_invalid"),
        ("## a\n- target_s: 4\n- asset_id: x\n- claims:\nStray prose.\n", "script_invalid"),
        ("Stray prose before a beat.\n", "script_invalid"),
        ("## a\n- target_s: 4\n- asset_id: x\n- claims:\n```voiced\nNever closed.\n", "script_invalid"),
        ("## a\n- target_s: 4\n- asset_id: x\n- claims:\n```text\nA.\n```\n", "script_invalid"),
        ("# Only a title\n", "script_invalid"),
        ("## a\n- target_s: 4\n- asset_id: x\n- claims: c, c\n```voiced\nA.\n```\n", "beat_invalid"),
    ],
)
def test_script_parser_refusals(text, code):
    refused(code, bundle.parse_script, text)


def test_script_reads_notes_titles_and_claim_lists():
    beats = bundle.parse_script(
        "# Title\n\n> a note\n\n## one\n\n> another note\n- target_s: 2.25\n- asset_id: a\n- claims: x, y\n\n"
        "```voiced\nFirst paragraph.\n\nSecond paragraph.\n```\n"
    )
    assert beats == [
        {
            "id": "one",
            "line": 5,
            "target_s": Decimal("2.25"),
            "asset_id": "a",
            "claims": ["x", "y"],
            "voiced": "First paragraph.\n\nSecond paragraph.",
        }
    ]


def test_voiced_text_must_be_spoken_verbatim(ws, tmp_path):
    set_script(ws["bundle"], "It did so across", "It did so *across*")
    refused("voiced_not_verbatim", intake, ws, tmp_path / "out")


def test_voiced_direction_line_is_not_verbatim(ws, tmp_path):
    set_script(ws["bundle"], "It did so across", "[pause]\n\nIt did so across")
    refused("voiced_not_verbatim", intake, ws, tmp_path / "out")


def test_unknown_claim_reference_refuses(ws, tmp_path):
    set_script(ws["bundle"], "- claims: build-ms", "- claims: build-ms, nowhere")
    refused("claim_unknown", intake, ws, tmp_path / "out")


# Refusals: the claims gate ---------------------------------------------------------------------------------------
def test_unmatched_number_refuses_the_segment(ws, tmp_path):
    set_script(ws["bundle"], "four hundred generated files", "four hundred and one generated files")
    error = refused("number_unclaimed", intake, ws, tmp_path / "out")
    rows = {r["segment"]: r for r in error.report}
    assert rows["intro"]["status"] == "passed"
    assert rows["result"]["status"] == "refused" and rows["result"]["codes"] == ["number_unclaimed"]
    assert [m["number"] for m in rows["result"]["mentions"] if m["status"] == "refused"] == ["401"]
    assert not (tmp_path / "out").exists()


def test_number_cited_by_another_beat_only_refuses(ws):
    set_script(ws["bundle"], "- claims: cache-rate, files", "- claims: cache-rate")
    result = bundle.claims_only(ws["bundle"])
    assert not result["ok"]
    assert result["segments"][1]["codes"] == ["number_unclaimed"]


def test_spelled_out_decimal_matches_its_claim(ws):
    result = bundle.claims_only(ws["bundle"])
    row = result["segments"][0]["mentions"][0]
    assert (row["text"], row["number"], row["unit"], row["claim"]) == (
        "seventeen point eight seven seven milliseconds", "17.877", "ms", "build-ms",
    )  # fmt: skip


def test_spelled_out_decimal_with_another_digit_refuses(ws):
    set_script(ws["bundle"], "point eight seven seven", "point eight seven eight")
    result = bundle.claims_only(ws["bundle"])
    assert result["segments"][0]["codes"] == ["number_unclaimed"]


@pytest.mark.parametrize("said", ["forty two percent", "forty two per cent", "42%", "42 percent", "forty-two %"])
def test_percentage_forms_match_a_percent_claim(ws, said):
    set_script(ws["bundle"], "forty two percent", said)
    assert bundle.claims_only(ws["bundle"])["ok"], said


def test_percentage_without_the_unit_does_not_match(ws):
    set_script(ws["bundle"], "forty two percent of its requests", "forty two of its requests")
    assert bundle.claims_only(ws["bundle"])["segments"][1]["codes"] == ["number_unclaimed"]


@pytest.mark.parametrize("receipt", ["", "   ", None])
def test_receipt_less_claim_refuses(ws, tmp_path, receipt):
    set_claims(ws["bundle"], lambda rows: rows[0].__setitem__("receipt", receipt))
    error = refused("claim_unreceipted", intake, ws, tmp_path / "out")
    assert error.report[0]["mentions"][0]["claims"] == ["build-ms"]


def test_two_cited_claims_with_one_value_are_ambiguous(ws):
    def twin(rows):
        rows.append(dict(rows[2], id="files-again", receipt="fixture-receipt-other"))

    set_claims(ws["bundle"], twin)
    set_script(ws["bundle"], "- claims: cache-rate, files", "- claims: cache-rate, files, files-again")
    assert bundle.claims_only(ws["bundle"])["segments"][1]["codes"] == ["claim_ambiguous"]


def test_ambiguous_number_refuses(ws):
    set_script(ws["bundle"], "four hundred generated files", "nineteen eighty four generated files")
    row = bundle.claims_only(ws["bundle"])["segments"][1]
    assert row["codes"] == ["number_ambiguous"] and row["unused_claims"] == ["files"]
    assert any(m.get("reason") == "adjacent_numbers" for m in row["mentions"])


def test_claim_spoken_text_must_read_as_its_value(ws):
    set_claims(ws["bundle"], lambda rows: rows[1]["value"].__setitem__("spoken", "forty three percent"))
    refused("claim_invalid", bundle.claims_only, ws["bundle"])


@pytest.mark.parametrize("unit", ["furlongs", "%", None])
def test_claim_unit_must_be_known(ws, unit):
    set_claims(ws["bundle"], lambda rows: rows[1]["value"].__setitem__("unit", unit))
    refused("claim_invalid", bundle.claims_only, ws["bundle"])


def test_claim_number_must_be_a_number(ws):
    set_claims(ws["bundle"], lambda rows: rows[1]["value"].__setitem__("number", "42"))
    refused("claim_invalid", bundle.claims_only, ws["bundle"])


def test_unused_claims_are_reported(ws):
    set_script(ws["bundle"], "- claims: build-ms", "- claims: build-ms, files")
    row = bundle.claims_only(ws["bundle"])["segments"][0]
    assert row["status"] == "passed" and row["unused_claims"] == ["files"]


def test_cli_claims_prints_the_report_and_refuses(ws, capsys):
    assert cli.main(["claims", str(ws["bundle"])]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    set_script(ws["bundle"], "forty two percent", "forty one percent")
    assert cli.main(["claims", str(ws["bundle"])]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out)["segments"][1]["status"] == "refused"
    assert json.loads(captured.err)["refused"] == "number_unclaimed"


# Refusals: records and output ------------------------------------------------------------------------------------
def test_out_must_be_new_or_empty(ws, tmp_path):
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "x").write_text("x")
    refused("out_exists", intake, ws, tmp_path / "out")


def test_engine_must_allow_a_confidential_job(ws, tmp_path):
    path = ws["records"] / "engines.json"
    rows = json.loads(path.read_text())
    rows[0]["confidentialAllowed"] = False
    path.write_text(json.dumps(rows))
    refused("confidential_engine_refused", intake, ws, tmp_path / "out")


def test_unknown_template_voice_and_engine_refuse(ws, tmp_path):
    refused("narrate_job_missing", intake, ws, tmp_path / "a", template="job-none")
    refused("voice_unknown", intake, ws, tmp_path / "b", voice="voice-none")
    refused("engine_unknown", intake, ws, tmp_path / "c", engine="engine-none")


def test_admit_refusal_stops_the_intake(ws, tmp_path):
    set_script(ws["bundle"], "- target_s: 8\n", "- target_s: 0.5\n")
    error = refused("slides_invalid", intake, ws, tmp_path / "out", tail_s=1)
    assert error.detail.startswith("admit:")
    assert not (tmp_path / "out").exists()


# The extractor ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "readings"),
    [
        ("seventeen point eight seven seven milliseconds", [("17.877", "ms")]),
        ("zero point five", [("0.5", "")]),
        ("one hundred and five users", [("105", "")]),
        ("one thousand two hundred thirty four", [("1234", "")]),
        ("two million three hundred thousand", [("2300000", "")]),
        ("a hundred files", [("100", "")]),
        ("twenty-one files", [("21", "")]),
        ("twenty first run", [("21", "ordinal")]),
        ("the 3rd beat", [("3", "ordinal")]),
        ("first, we start", [("1", "ordinal")]),
        ("one second later", [("1", "s")]),
        ("three point five seconds", [("3.5", "s")]),
        ("3.5 million users", [("3500000", "")]),
        ("12ms and 1,024 bytes at 30 frames per second", [("12", "ms"), ("1024", "B"), ("30", "fps")]),
        ("five metres per second", [("5", "m/s")]),
        ("minus five volts and minus 5 V", [("-5", "V"), ("-5", "V")]),
        ("five and six", [("5", ""), ("6", "")]),
        ("seven point, then more", [("7", "")]),
        ("five hundred six", [("506", "")]),
        ("Version 2 allows 8% of stretch.", [("2", ""), ("8", "percent")]),
        ("a dog, someone, once, no one else", [("1", "")]),
        ("forty two decibels and 6 dBFS", [("42", "dB"), ("6", "dBFS")]),
        ("five\u2011hundred generated files", [("500", "")]),
        ("twenty\u2010one files", [("21", "")]),
        ("five's company", [("5", "")]),
        ("seven\u2019s turn", [("7", "")]),
        ("twelve ms and nine dB", [("12", "ms"), ("9", "dB")]),
        ("5 m/s and five km/h", [("5", "m/s"), ("5", "km/h")]),
        ("12 MB, 5 mW and 3 m", [("12", "MB"), ("5", "mW"), ("3", "m")]),
        ("2 MCP servers and 12 PRs", [("2", ""), ("12", "")]),
        ("a manifold, a fold", []),
        ("12s and 1.5s", [("12", "s"), ("1.5", "s")]),
    ],
)
def test_extract_reads_numbers(text, readings):
    got = [(claims.fmt(m["number"]), m["unit"]) for m in claims.extract(text) if not m["ambiguous"]]
    assert got == readings
    assert not [m for m in claims.extract(text) if m["ambiguous"]]


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("nineteen eighty four", "adjacent_numbers"),
        ("one two three", "adjacent_numbers"),
        ("twenty twenty six", "adjacent_numbers"),
        ("one million thousand", "adjacent_numbers"),
        ("5 6", "adjacent_numbers"),
        ("two thirds of it", "fraction_or_vague_quantity"),
        ("one third", "fraction_or_vague_quantity"),
        ("a half", "fraction_or_vague_quantity"),
        ("a dozen", "fraction_or_vague_quantity"),
        ("twice as fast", "fraction_or_vague_quantity"),
        ("point five", "point_without_whole_part"),
        ("twenty second", "second_ordinal_or_unit"),
        ("one hundred second", "second_ordinal_or_unit"),
        ("version 1.2.3", "digits_not_one_number"),
        ("at 10:30", "digits_not_one_number"),
        ("1/2", "digits_not_one_number"),
        ("2026-10-29", "digits_not_one_number"),
        ("an MP4 file", "digits_not_one_number"),
        ("1,23", "digits_not_one_number"),
        ("4K", "digits_not_one_number"),
        # A scale word with no count, plural scales, -fold words and other vague quantities (TIN-7735 review).
        ("hundred files", "scale_without_count"),
        ("thousand users", "scale_without_count"),
        ("millions of rows", "fraction_or_vague_quantity"),
        ("thousands of users", "fraction_or_vague_quantity"),
        ("hundreds of files", "fraction_or_vague_quantity"),
        ("tenfold", "fraction_or_vague_quantity"),
        ("threefold", "fraction_or_vague_quantity"),
        ("ten-fold", "fraction_or_vague_quantity"),
        ("10 fold", "fraction_or_vague_quantity"),
        ("nil errors", "fraction_or_vague_quantity"),
        ("nought errors", "fraction_or_vague_quantity"),
        ("since the nineties", "fraction_or_vague_quantity"),
        ("a third of it", "fraction_or_vague_quantity"),
        ("an eighth of it", "fraction_or_vague_quantity"),
        # Non-ASCII numerals, Roman numerals, dashes and decades.
        ("\u00bd of it", "digits_not_one_number"),
        ("\u00bc of it", "digits_not_one_number"),
        ("\u0663 items", "digits_not_one_number"),
        ("5\u00b2 tiles", "digits_not_one_number"),
        ("World War II", "roman_numeral"),
        ("Phase IV", "roman_numeral"),
        ("five\u2013hundred files", "dash_between_numbers"),
        ("five\u2014six", "dash_between_numbers"),
        ("the 90s", "decade_or_seconds"),
        ("the 1990s", "decade_or_seconds"),
        # Scale abbreviations and units the gate does not read.
        ("17 K users", "unknown_scale_or_unit"),
        ("17 k users", "unknown_scale_or_unit"),
        ("17 bn", "unknown_scale_or_unit"),
        ("3 B rows", "unknown_scale_or_unit"),
        ("17 M users", "unknown_scale_or_unit"),
        ("two lakh", "unknown_scale_or_unit"),
        ("1.5 GiB", "unknown_scale_or_unit"),
        ("5 kph", "unknown_scale_or_unit"),
        ("5 Mbps", "unknown_scale_or_unit"),
        ("12 Mb", "unknown_scale_or_unit"),
        ("5 MW", "unknown_scale_or_unit"),
        ("3 kWh", "unknown_scale_or_unit"),
        ("5M users", "digits_not_one_number"),
        ("5 m/furlong", "unit_not_read"),
    ],
)
def test_extract_fails_closed_on_ambiguity(text, reason):
    found = [m for m in claims.extract(text) if m["ambiguous"]]
    assert [m["ambiguous"] for m in found] == [reason]
    assert all(m["number"] is None for m in found)


def test_ambiguous_mentions_never_match():
    cited = {"c": {"id": "c", "value": {"spoken": "", "number": Decimal(1984), "unit": ""}, "receipt": "r"}}
    result = claims.check_segment("It was nineteen eighty four.", ["c"], cited)
    assert result["codes"] == ["number_ambiguous"]


def test_units_are_canonical():
    assert all(claims.unit_valid(u) for u in ("", "ordinal", "ms", "percent", "m/s", "Hz"))
    assert not any(claims.unit_valid(u) for u in ("%", "furlong", "m/s/s", "ms/"))


def test_tens_of_thousands_is_two_vague_quantities():
    found = claims.extract("tens of thousands of users")
    assert [m["ambiguous"] for m in found] == ["fraction_or_vague_quantity"] * 2


def test_a_hyphen_variant_cannot_change_the_value(ws):
    # Written with U+2011, "five-hundred" is 500: a claim of 5 must not back it.
    set_script(ws["bundle"], "four hundred generated", "five\u2011hundred generated")
    set_claims(ws["bundle"], lambda rows: rows[2]["value"].update(spoken="five", number=5))
    result = bundle.claims_only(ws["bundle"])
    assert not result["ok"]
    rows = [m for s in result["segments"] for m in s["mentions"] if m["status"] == "refused"]
    assert [(r["number"], r["code"]) for r in rows] == [("500", "number_unclaimed")]


@pytest.mark.parametrize(
    "said",
    ["hundred", "thousands of", "tenfold more", "\u00bd of the", "five's", "the 90s of", "17 K"],
)
def test_review_cases_refuse_without_a_claim(ws, said):
    set_script(ws["bundle"], "four hundred generated", f"{said} generated")
    set_claims(ws["bundle"], lambda rows: rows.pop(2))
    set_script(ws["bundle"], "- claims: cache-rate, files", "- claims: cache-rate")
    assert not bundle.claims_only(ws["bundle"])["ok"]


# Atomic writes -----------------------------------------------------------------------------------------------------
def store_listing(store_dir):
    return sorted((p.name, sha(p)) for p in Path(store_dir).iterdir()) if Path(store_dir).exists() else []


def test_store_conflict_refuses_before_writing(ws, tmp_path):
    digest = {a["id"]: a["sha256"] for a in manifest(ws["bundle"])["assets"]}["slide-a"]
    ws["store"].mkdir(parents=True, exist_ok=True)
    (ws["store"] / f"{digest}.png").write_bytes(b"not the slide")
    before = store_listing(ws["store"])
    refused("store_conflict", intake, ws, tmp_path / "out")
    assert not (tmp_path / "out").exists()
    assert store_listing(ws["store"]) == before
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".out.intake-")]


def test_an_asset_changed_after_reading_refuses(ws, tmp_path, monkeypatch):
    original = bundle.read

    def read_then_change(path):
        b = original(path)
        (Path(path) / "assets" / "slide-a.png").write_bytes(b"\x89PNG\r\n\x1a\nchanged after the read")
        return b

    monkeypatch.setattr(bundle, "read", read_then_change)
    before = store_listing(ws["store"])
    error = refused("asset_digest_mismatch", intake, ws, tmp_path / "out")
    assert "slide-a" in error.detail
    assert not (tmp_path / "out").exists()
    assert store_listing(ws["store"]) == before
    assert not [p for p in ws["store"].iterdir() if p.name.endswith(".part")]


def test_an_asset_swapped_for_a_symlink_after_reading_refuses(ws, tmp_path, monkeypatch):
    original = bundle.read
    elsewhere = tmp_path / "elsewhere.png"

    def read_then_swap(path):
        b = original(path)
        slide = Path(path) / "assets" / "slide-a.png"
        elsewhere.write_bytes(slide.read_bytes())
        slide.unlink()
        slide.symlink_to(elsewhere)
        return b

    monkeypatch.setattr(bundle, "read", read_then_swap)
    before = store_listing(ws["store"])
    refused("asset_missing", intake, ws, tmp_path / "out")
    assert not (tmp_path / "out").exists()
    assert store_listing(ws["store"]) == before


def test_intake_fills_an_empty_out_and_a_default_store(ws, tmp_path):
    out = tmp_path / "nested" / "out"
    out.mkdir(parents=True)
    m = bundle.intake(ws["bundle"], out, ws["records"], template=TEMPLATE, voice=VOICE, engine=ENGINE)
    assert (out / "intake.json").is_file() and (out / "records" / "jobs.json").is_file()
    assert sorted(m["sources"]) == sorted(p.name.split(".")[0] for p in (out / "store").iterdir())
    assert "store/" not in json.dumps(m["outputs"])
    assert out.stat().st_mode & 0o777 == bundle.umask_mode(0o777)  # not mkdtemp's 0700
    assert not [p for p in out.parent.iterdir() if p.name.startswith(".out.intake-")]


def test_a_default_store_refusal_leaves_no_out(ws, tmp_path, monkeypatch):
    original = bundle.read

    def read_then_change(path):
        b = original(path)
        (Path(path) / "assets" / "slide-b.png").write_bytes(b"changed")
        return b

    monkeypatch.setattr(bundle, "read", read_then_change)
    out = tmp_path / "new" / "out"
    refused(
        "asset_digest_mismatch",
        bundle.intake,
        ws["bundle"],
        out,
        ws["records"],
        template=TEMPLATE,
        voice=VOICE,
        engine=ENGINE,
    )
    assert not (tmp_path / "new").exists()


# Pronunciation tables ----------------------------------------------------------------------------------------------
def add_pronunciation(ws, written, spoken):
    path = ws["records"] / "pronunciation.json"
    table = json.loads(path.read_text())
    rows = table if isinstance(table, list) else [table]
    rows[0]["entries"].append(
        {"caseSensitive": True, "note": None, "spoken": spoken, "wholeWord": True, "written": written}
    )
    path.write_text(json.dumps(table, indent=1))


def test_a_pronunciation_entry_that_adds_a_number_refuses(ws, tmp_path):
    add_pronunciation(ws, "synthetic", "forty two")
    before = store_listing(ws["store"])
    error = refused("pronunciation_adds_number", intake, ws, tmp_path / "out")
    assert "forty" in error.detail and "intro" in error.detail
    assert not (tmp_path / "out").exists()
    assert store_listing(ws["store"]) == before


def test_a_pronunciation_entry_that_spells_a_word_passes(ws, tmp_path):
    add_pronunciation(ws, "synthetic", "sin thetic")
    m = intake(ws, tmp_path / "out")
    assert m["narrate"]["pronunciation"] == "narrate-en-example"
    assert m["narrate"]["pronunciation_upstream"] is None
    assert m["states"]["pronunciation_numbers"] == "passed"


def test_a_narration_register_needs_its_release_to_check(ws, tmp_path, monkeypatch):
    monkeypatch.delenv("NARRATE_LEXICAL_DIR", raising=False)
    path = ws["records"] / "jobs.json"
    rows = json.loads(path.read_text())
    rows = rows if isinstance(rows, list) else [rows]
    for row in rows:
        if row["id"] == TEMPLATE:
            row["lexical"]["valeRegister"] = "narration"
    path.write_text(json.dumps(rows, indent=1))
    refused("lexical_missing", intake, ws, tmp_path / "out")
    assert not (tmp_path / "out").exists()
