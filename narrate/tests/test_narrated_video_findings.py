"""The typed finding record (narrate/video/findings.py, docs/spec/NARRATED_VIDEO.md "Findings", Linear TIN-7788, ruling
TIN-7125 0690fe88). A planted fault per code returns that code, a read with several faults returns them all, and a
gate's exit code and first code stay as they were. Synthetic bundles and pictures only.
"""

import copy
import hashlib
import json
import re
from decimal import Decimal

import pytest
from test_narrated_video_compose import Bench, node_dir
from test_narrated_video_frames import IN_BOX, H, W, full, source
from test_narrated_video_intake import (  # noqa: F401  (fixtures)
    ENGINE,
    TEMPLATE,
    VOICE,
    add_asset,
    add_pronunciation,
    edit_records,
    intake,
    manifest,
    no_whisper,
    set_consent,
    set_engine,
    set_manifest,
    set_script,
    set_template,
    ws,
)

from narrate.config import ROOT
from narrate.video import bundle, claims, cli, deliver, findings, frames, graph, speech
from narrate.video.job import JobError


@pytest.fixture
def bench(tmp_path, ffmpeg):
    return Bench(tmp_path)


def codes(rows):
    return [row["code"] for row in rows]


def refusal_of(fn, *args, **kw):
    with pytest.raises(bundle.BundleError) as caught:
        fn(*args, **kw)
    return caught.value


def edit_manifest(w, edit):
    value = manifest(w["bundle"])
    edit(value)
    set_manifest(w["bundle"], value)


def edit_claims(w, edit):
    path = w["bundle"] / "claims.json"
    rows = json.loads(path.read_text())
    edit(rows)
    path.write_text(json.dumps(rows))


# The record ------------------------------------------------------------------------------------------------------
def test_a_row_has_the_fields_of_the_record_and_a_known_code_takes_its_table_row():
    row = findings.finding("slide_letterbox", gate="other", stage="voice", page="p1", strip_px=12)
    assert set(row) == findings.FIELDS
    assert (row["gate"], row["stage"], row["blocking"]) == ("slide_match", "compose", True)
    assert (row["page"], row["segment"], row["detail"]) == ("p1", None, {"strip_px": 12})


def test_an_unlisted_code_takes_what_its_caller_names():
    row = findings.finding("bed_invalid", gate="music", stage="music", segment="seg-1")
    assert (row["gate"], row["stage"], row["blocking"], row["segment"]) == ("music", "music", True, "seg-1")
    assert findings.finding("nothing_known")["gate"] == "unknown"


@pytest.mark.parametrize(
    "text",
    ["a sentence with spaces", "/" + "x" * 80, "line\nbreak", "étude"],
)
def test_a_record_holds_no_text(text):
    row = findings.finding("slide_letterbox", page=text, segment=text, said=text, rows=[{"said": text}])
    assert row["page"] is None and row["segment"] is None
    assert row["detail"] == {"said": findings.WITHHELD, "rows": [{"said": findings.WITHHELD}]}


def test_a_lexical_finding_alone_does_not_block():
    shown = findings.report([findings.finding("lexical_finding", segment="seg-1", rule="XL-FIX-001")])
    assert shown["ok"] is True and shown["count"] == 1 and shown["blocking"] == 0
    both = findings.report(shown["findings"] + [findings.finding("flash_jump")])
    assert both["ok"] is False and both["blocking"] == 1
    assert both["codes"] == {"lexical_finding": 1, "flash_jump": 1}


def test_reading_a_report_rebuilds_each_row_so_a_caller_cannot_move_a_known_code():
    row = findings.finding("voice_qa_failed", segment="seg-1", metric="wer")
    forged = row | {"stage": "compose", "blocking": False, "gate": "lexical", "page": "a b", "detail": {"code": "x y"}}
    read = findings.check(findings.report([forged]))["findings"][0]
    assert (read["stage"], read["blocking"], read["gate"], read["page"]) == ("script", True, "voice_qa", None)
    assert read["detail"] == {"code": findings.WITHHELD}


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"kind": findings.KIND, "schema_version": 1},
        {"kind": "other", "schema_version": 1, "findings": []},
        {"kind": findings.KIND, "schema_version": 2, "findings": []},
        {"kind": findings.KIND, "schema_version": 1, "findings": [{"code": "flash_jump"}]},
        {"kind": findings.KIND, "schema_version": 1, "findings": ["flash_jump"]},
        findings.report([findings.finding("flash_jump") | {"detail": "words"}]),
        findings.report([findings.finding("flash_jump") | {"stage": 7}]),
        findings.report([findings.finding("flash_jump") | {"stage": "a sentence with spaces"}]),
        findings.report([findings.finding("flash_jump") | {"gate": "a sentence with spaces"}]),
        findings.report([findings.finding("flash_jump") | {"code": "a sentence with spaces"}]),
        findings.report([findings.finding("flash_jump") | {"code": ""}]),
    ],
)
def test_a_report_that_is_not_one_refuses(value):
    with pytest.raises(JobError) as caught:
        findings.check(value)
    assert caught.value.code == "findings_invalid"


def test_the_table_holds_every_code_the_gates_write():
    def source_of(name):
        return (ROOT / "narrate" / "video" / name).read_text(encoding="utf-8")

    written = set(re.findall(r'BundleError\(\s*"([a-z_]+)"', source_of("bundle.py")))
    written |= set(re.findall(r'bad\(number, .*?"([a-z_]+)"\)$', source_of("bundle.py"), re.M))
    written |= set(re.findall(r'"code": "([a-z_]+)"', source_of("frames.py")))
    written |= set(re.findall(r'row \|= \{"status": "refused", "code": "([a-z_]+)"', source_of("claims.py")))
    assert written - set(findings.CODES) == set()
    assert set(deliver.CAPTION_CODES.values()) <= set(findings.CODES)


# bundle.py: a planted fault per code -----------------------------------------------------------------------------
def plant_script(old, new):
    return lambda w, tmp: set_script(w["bundle"], old, new)


def plant_asset(**fields):
    return lambda w, tmp: edit_manifest(w, lambda value: value["assets"][0].update(fields))


def plant_text_source(w, tmp):
    (w["bundle"] / "assets" / "bad.json").write_bytes(b"not json")
    digest = hashlib.sha256(b"not json").hexdigest()
    edit_manifest(w, lambda value: value["assets"][0].update(text={"path": "assets/bad.json", "sha256": digest}))


def plant_two_videos(w, tmp):
    add_asset(w["bundle"], "clip-a", "clip-a.mp4", "mp4", b"\x00\x00\x00\x18ftypisom" + bytes(12))
    add_asset(w["bundle"], "clip-b", "clip-b.mp4", "mp4", b"\x00\x00\x00\x18ftypisom" + bytes(13))
    set_script(w["bundle"], "- asset_id: slide-a", "- asset_id: clip-a")
    set_script(w["bundle"], "- asset_id: slide-b", "- asset_id: clip-b")


def plant_no_voiced(w, tmp):
    path = w["bundle"] / "script.md"
    path.write_text(re.sub(r"```voiced\nThis synthetic.*?```\n", "", path.read_text(), flags=re.S))


def plant_voice_scope(w, tmp):
    edit_records(w, "voices.json", lambda rows: rows[0].update(scope="another-scope"))


def plant_no_engines(w, tmp):
    edit_records(w, "voices.json", lambda rows: rows[0].update(allowedEngines=[]))


def plant_rented(w, tmp):
    set_engine(w, profile="RentedOpen", backend="RentedOpen", endpoint="https://gpu.example.invalid")


def plant_held_job(w, tmp):
    def add(rows):
        template = next(r for r in rows if r["id"] == TEMPLATE)
        rows.append(template | {"id": f"{w['bundle'].name}-intro", "seed": 9999})

    edit_records(w, "jobs.json", add)


def plant_out(w, tmp):
    (tmp / "out").mkdir()
    (tmp / "out" / "held").write_text("held")


def plant_earlier_intake(w, tmp):
    intake(w, tmp / "out", job_id="an-earlier-job")


def plant_store_file(w, tmp):
    digest = manifest(w["bundle"])["assets"][0]["sha256"]
    w["store"].mkdir(parents=True, exist_ok=True)
    (w["store"] / f"{digest}.png").write_bytes(b"not the slide")


def plant_refused_saying(w, tmp):
    set_script(w["bundle"], "It did so across", "The Widget did so across")
    add_pronunciation(w, "Widget", "Widget 7")


# code: (plant the fault, intake arguments).
PLANTED = {
    "asset_digest_mismatch": (plant_asset(sha256="0" * 64), {}),
    "asset_kind_mismatch": (plant_asset(kind="mp4"), {}),
    "asset_missing": (lambda w, tmp: (w["bundle"] / "assets" / "slide-a.png").unlink(), {}),
    "asset_needs_conversion": (plant_script("- asset_id: slide-a", "- asset_id: loop-a"), {}),
    "asset_text_invalid": (plant_text_source, {}),
    "asset_unknown": (plant_script("- asset_id: slide-a", "- asset_id: nothing"), {}),
    "asset_unreceipted": (plant_asset(receipt=""), {}),
    "asset_video_multiple": (plant_two_videos, {}),
    "beat_invalid": (plant_script("- target_s: 8\n", "- target_s: soon\n"), {}),
    "beat_voiced_missing": (plant_no_voiced, {}),
    "bundle_invalid": (plant_asset(kind="bmp"), {}),
    "claim_invalid": (lambda w, tmp: edit_claims(w, lambda rows: rows[0]["value"].update(number=18)), {}),
    "claim_unknown": (plant_script("- claims: build-ms", "- claims: nothing"), {}),
    "consent_scope": (plant_voice_scope, {}),
    "engine_inconsistent": (lambda w, tmp: set_engine(w, profile="GpuDirect", backend="Fake"), {}),
    "engine_not_allowed": (plant_no_engines, {}),
    "engine_unknown": (lambda w, tmp: None, {"engine": "engine-none"}),
    "hosted_not_allowed": (plant_rented, {}),
    "job_invalid": (lambda w, tmp: None, {"job_id": "not an id"}),
    "job_mismatch": (plant_earlier_intake, {"replace": True}),
    "narrate_job_exists": (plant_held_job, {}),
    "narrate_job_missing": (lambda w, tmp: None, {"template": "job-none"}),
    "out_exists": (plant_out, {}),
    "pronunciation_adds_number": (lambda w, tmp: add_pronunciation(w, "synthetic", "forty two"), {}),
    "pronunciation_refused": (plant_refused_saying, {}),
    "pronunciation_unknown": (lambda w, tmp: set_template(w, pronunciation="table-none"), {}),
    "records_invalid": (lambda w, tmp: set_template(w, extra=1), {}),
    "script_invalid": (plant_script("# Demo fixture\n", "A stray line.\n"), {}),
    "store_conflict": (plant_store_file, {}),
    "voice_unknown": (lambda w, tmp: None, {"voice": "voice-none"}),
    "voiced_not_verbatim": (plant_script("It did so across", "It did so *across*"), {}),
}


def test_every_intake_code_has_a_planted_fault():
    assert set(PLANTED) == set(findings.INTAKE_CODES)


@pytest.mark.parametrize("code", sorted(PLANTED))
def test_a_planted_bundle_fault_refuses_with_its_code_and_a_typed_row(ws, tmp_path, code):  # noqa: F811
    plant, arguments = PLANTED[code]
    plant(ws, tmp_path)
    error = refusal_of(intake, ws, tmp_path / "out", **arguments)
    assert error.code == code, error.detail
    assert code in codes(error.findings)
    row = next(row for row in error.findings if row["code"] == code)
    assert set(row) == findings.FIELDS and row["gate"] == findings.INTAKE and row["stage"] is None and row["blocking"]


def test_a_fault_in_each_asset_returns_them_all_and_the_first_code_stays(ws, tmp_path):  # noqa: F811
    def edit(value):
        value["assets"][0]["receipt"] = ""
        value["assets"][1]["sha256"] = "0" * 64
        value["assets"][2]["kind"] = "bmp"

    edit_manifest(ws, edit)
    error = refusal_of(intake, ws, tmp_path / "out")
    assert error.code == "asset_unreceipted" and "slide-a" in error.detail
    assert codes(error.findings) == ["asset_unreceipted", "asset_digest_mismatch", "bundle_invalid"]
    assert [row["page"] for row in error.findings] == ["slide-a", "slide-b", "loop-a"]
    assert [row["detail"]["position"] for row in error.findings] == [0, 1, 2]


def test_a_fault_in_each_beat_and_claim_returns_them_all(ws, tmp_path):  # noqa: F811
    set_script(ws["bundle"], "- target_s: 8\n", "- target_s: soon\n")
    set_script(ws["bundle"], "- target_s: 8.5\n", "- target_s: 9000\n")
    set_script(ws["bundle"], "# Demo fixture\n", "A stray line.\n")

    def edit(rows):
        rows[0]["value"]["number"] = 18
        rows[2]["value"]["unit"] = "furlong"

    edit_claims(ws, edit)
    error = refusal_of(intake, ws, tmp_path / "out")
    assert error.code == "script_invalid"
    assert codes(error.findings) == ["script_invalid", "beat_invalid", "beat_invalid", "claim_invalid", "claim_invalid"]
    assert [row["page"] for row in error.findings[1:3]] == ["intro", "result"]
    assert [row["detail"]["claim"] for row in error.findings[3:]] == ["build-ms", "files"]


def test_a_refused_heading_adds_no_finding_of_its_own_lines(ws, tmp_path):  # noqa: F811
    set_script(ws["bundle"], "## result\n", "## intro\n")
    error = refusal_of(intake, ws, tmp_path / "out")
    assert error.code == "beat_invalid" and codes(error.findings) == ["beat_invalid"]
    assert error.findings[0]["detail"]["line"] > 0


def test_an_unclosed_voiced_block_is_one_finding(ws, tmp_path):  # noqa: F811
    path = ws["bundle"] / "script.md"
    path.write_text(path.read_text().rstrip().removesuffix("```"))
    error = refusal_of(intake, ws, tmp_path / "out")
    assert error.code == "script_invalid" and codes(error.findings) == ["script_invalid"]


def test_a_fault_in_each_beats_asset_returns_them_all(ws, tmp_path):  # noqa: F811
    set_script(ws["bundle"], "- asset_id: slide-a", "- asset_id: nothing")
    set_script(ws["bundle"], "- asset_id: slide-b", "- asset_id: loop-a")
    error = refusal_of(intake, ws, tmp_path / "out")
    assert error.code == "asset_unknown"
    assert codes(error.findings) == ["asset_unknown", "asset_needs_conversion"]
    assert [row["page"] for row in error.findings] == ["intro", "result"]


def test_an_asset_fault_also_carries_the_spoken_numbers_intake_would_refuse_next(ws, tmp_path):  # noqa: F811
    set_script(ws["bundle"], "forty two percent", "forty three percent")
    edit_manifest(ws, lambda value: value["assets"][0].update(receipt=""))
    error = refusal_of(intake, ws, tmp_path / "out")
    assert error.code == "asset_unreceipted"
    assert codes(error.findings) == ["asset_unreceipted", "number_unclaimed"]
    assert error.findings[1]["segment"] == "result" and error.findings[1]["stage"] == "script"


def test_every_refused_number_of_every_beat_is_returned_with_no_spoken_text(ws, tmp_path):  # noqa: F811
    set_script(ws["bundle"], "seventeen point eight seven seven", "eighteen")
    set_script(ws["bundle"], "forty two percent", "forty three percent")
    set_script(ws["bundle"], "four hundred generated", "nineteen eighty four generated")
    error = refusal_of(intake, ws, tmp_path / "out")
    assert error.code == "number_unclaimed"
    assert codes(error.findings) == ["number_unclaimed", "number_unclaimed", "number_ambiguous"]
    assert [row["segment"] for row in error.findings] == ["intro", "result", "result"]
    assert error.findings[2]["detail"]["reason"] == "adjacent_numbers"
    said = json.dumps(error.findings)
    assert "eighteen" not in said and "forty" not in said and "nineteen" not in said


def test_admit_returns_every_refusal(ws, tmp_path, monkeypatch):  # noqa: F811
    rows = [{"code": "first_one", "detail": "a"}, {"code": "next_one", "detail": "b"}]
    verdict = {"verdict": "Refused", "refusals": rows}
    monkeypatch.setattr(bundle, "admit", lambda *a: verdict)
    error = refusal_of(intake, ws, tmp_path / "out")
    assert error.code == "first_one" and codes(error.findings) == ["first_one", "next_one"]


def test_a_row_that_may_say_a_private_term_keeps_its_code_alone():
    row = findings.finding("asset_unknown", page="intro", segment="intro", line=4)
    assert bundle.withheld_row(None, row) == row
    assert bundle.withheld_row(False, row) == row | {"page": None, "segment": None, "detail": {}}
    with pytest.raises(bundle.BundleError) as caught, bundle.withheld({"entries": False}):
        raise bundle.BundleError("asset_unknown", "beat intro: nothing", rows=[row])
    assert caught.value.findings == [row | {"page": None, "segment": None, "detail": {}}]
    assert "intro" not in caught.value.detail


def test_the_intake_command_keeps_exit_1_and_its_first_code_and_prints_every_finding(ws, tmp_path, capsys):  # noqa: F811
    edit_manifest(ws, lambda value: (value["assets"][0].update(receipt=""), value["assets"][1].update(receipt="")))
    argv = ["intake", str(ws["bundle"]), "--out", str(tmp_path / "out"), "--records", str(ws["records"]),
            "--store", str(ws["store"]), "--narrate-template", TEMPLATE, "--voice", VOICE, "--engine", ENGINE,
            "--no-avatar", "--json"]  # fmt: skip
    assert cli.main(argv) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.err)["refused"] == "asset_unreceipted"
    assert json.loads(captured.out)["findings"]["codes"] == {"asset_unreceipted": 2}


def test_the_claims_command_keeps_exit_1_and_its_first_code_and_prints_every_finding(ws, capsys):  # noqa: F811
    set_script(ws["bundle"], "seventeen point eight seven seven", "eighteen")
    set_script(ws["bundle"], "forty two percent", "forty three percent")
    assert cli.main(["claims", str(ws["bundle"])]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.err)["refused"] == "number_unclaimed"
    shown = json.loads(captured.out)
    assert shown["findings"]["codes"] == {"number_unclaimed": 2} and shown["ok"] is False


# claims.py -------------------------------------------------------------------------------------------------------
def test_a_planted_fault_per_claims_code():
    def claim(ident, number, unit="", receipt="fixture-receipt"):
        return {"id": ident, "value": {"spoken": "x", "number": Decimal(number), "unit": unit}, "receipt": receipt}

    table = {"a": claim("a", "7"), "b": claim("b", "7"), "c": claim("c", "9", receipt=" ")}
    report = [
        {"segment": "one"} | claims.check_segment("seven and eleven.", ["a", "b"], table),
        {"segment": "two"} | claims.check_segment("nine, and nineteen eighty four.", ["c"], table),
    ]
    rows = claims.typed_rows(report)
    assert codes(rows) == ["claim_ambiguous", "number_unclaimed", "claim_unreceipted", "number_ambiguous"]
    assert [row["segment"] for row in rows] == ["one", "one", "two", "two"]
    assert {row["gate"] for row in rows} == {"claims"} and {row["stage"] for row in rows} == {"script"}
    assert [row["detail"]["mention"] for row in rows] == [0, 1, 0, 1]
    assert claims.typed_rows([{"segment": "three"} | claims.check_segment("Nothing here.", [], table)]) == []


# frames.py -------------------------------------------------------------------------------------------------------
def test_preflight_returns_every_code_and_page_not_the_first(bench, tmp_path):
    first = source(bench, tmp_path, "first.png", IN_BOX)
    second = source(bench, tmp_path, "second.png", IN_BOX)
    short = source(bench, tmp_path, "short.png", size=f"{W}x{H - 12}")
    gone = source(bench, tmp_path, "gone.png")
    (bench.paths["store"] / "gone.png").write_bytes(b"not the slide")
    job = full(bench, "nv-every", first, second, short, gone)
    intake_row = {"segments": [{"segment": "p0", "show": "slide", "asset": {"sha256": "f" * 64}}], "states": {}}
    report = frames.preflight(job, bench.env, intake_row)
    shown = report["typed"]
    assert report["ok"] is False and shown["ok"] is False and shown["kind"] == findings.KIND
    assert (
        codes(shown["findings"])
        == codes(report["findings"])
        == [
            "claims_not_passed",
            "avatar_box_occupied",
            "avatar_box_occupied",
            "slide_letterbox",
            "slide_digest_mismatch",
            "slide_page_mismatch",
        ]
    )
    assert [row["page"] for row in shown["findings"]] == [None, "p0", "p1", "p2", "p3", "p0"]
    assert shown["findings"][1]["detail"]["pixels"] >= 120 * 30 and shown["findings"][1]["detail"]["source"] == "layer"
    assert shown["findings"][3]["detail"]["strip_px"] > frames.STRIP_PX
    assert findings.check(json.loads(json.dumps(shown)))["codes"] == shown["codes"]


def test_a_planted_card_in_the_box(bench, tmp_path):
    job = bench.slides_job("nv-cardslide")
    job["slides"]["pages"] = [
        {"id": "p0", "startS": 0, "endS": 2, "show": {"slide": {"sha256": source(bench, tmp_path, "card.png")}}}
    ]
    job["avatar"]["avatarOff"] = []
    job["avatar"]["corner"] = "BL"
    assert codes(frames.preflight(job, bench.env)["typed"]["findings"]) == ["card_in_avatar_box"]


def test_the_preflight_command_keeps_exit_1_and_its_first_code(bench, tmp_path, capsys):
    from narrate.video.store import JobStore

    job = full(bench, "nv-cli", source(bench, tmp_path, "a.png", IN_BOX), source(bench, tmp_path, "b.png", IN_BOX))
    JobStore(tmp_path / "root", job["id"]).write_job(job)
    args = ["--root", str(tmp_path / "root"), "--records", str(bench.paths["records"])]
    args += ["--store", str(bench.paths["store"]), "--lexical", str(bench.paths["lexical"])]
    assert cli.main(["preflight", "nv-cli", *args]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.err)["refused"] == "avatar_box_occupied"
    assert json.loads(captured.out)["typed"]["codes"] == {"avatar_box_occupied": 2}


def test_a_planted_fault_per_composed_frame_code(bench, tmp_path):
    digest = source(bench, tmp_path, "a.png")
    other = source(bench, tmp_path, "other.png", "drawbox=x=60:y=60:w=500:h=300:color=black:t=fill")
    job = full(bench, "nv-pixels", digest)
    s, result, _ = bench.run(job)
    assert result["ok"], result
    measured, video = s.manifest("compose")["measurements"], node_dir(s, "compose") / "video.mp4"
    report = json.loads((node_dir(s, "deliver_check") / "deliver_check.json").read_text())
    assert deliver.typed_findings(report, job) == []

    claimed = copy.deepcopy(job)
    claimed["slides"]["pages"][0]["show"]["slide"]["sha256"] = other
    faked = copy.deepcopy(measured)
    faked["slides"]["runs"][0]["layers"][0]["sha256"] = other
    found, _ = frames.slide_frames(claimed, bench.env, faked, [], video, W, H)
    assert codes(frames.typed_rows(found)) == ["slide_not_shown"]
    moved = copy.deepcopy(job)
    moved["slides"]["pages"][0]["show"]["slide"]["sha256"] = "f" * 64
    found, _ = frames.slide_frames(moved, bench.env, measured, [], video, W, H)
    assert codes(frames.typed_rows(found)) == ["slide_layer_mismatch"]
    empty = copy.deepcopy(measured)
    empty["slides"]["runs"] = []
    found, _ = frames.slide_frames(job, bench.env, empty, [], video, W, H)
    rows = frames.typed_rows(found)
    assert codes(rows) == ["slide_layer_missing"] and rows[0]["page"] == "p0" and rows[0]["stage"] == "compose"


# deliver.py ------------------------------------------------------------------------------------------------------
JOB = {
    "slides": {"pages": [{"id": "p0", "startS": 0, "endS": 2}, {"id": "p1", "startS": 2, "endS": 4}]},
    "delivery": {"driftLu": 1, "truePeakDbtp": -1.5},
    "captions": {"srt": True, "vtt": True, "soft": True},
    "labels": {"personaCue": "A cue", "extraNotice": "A notice"},
}
PROFILE = {"size": {"w": W, "h": H}, "fps": {"num": 30, "den": 1}}


def clean_report():
    gates = dict.fromkeys(("profile", "loudness", "flash", "captions", "avatar_box", "slide_match"), "passed")
    return {
        "gates": gates,
        "profile": {"findings": {}},
        "loudness": {"drift_lu": 0.1, "integrated_lufs": -16.1, "true_peak_dbtp": -2.0},
        "flash": {"max": 0.3, "changes": [{"at_s": 2, "max_jump": 0.1, "frame": 60}]},
        "captions": {"findings": [], "cues": 1},
        "avatar_box": {"findings": []},
        "slide_match": {"findings": []},
    }


def test_a_passed_report_holds_no_finding():
    assert deliver.typed_findings(clean_report(), JOB) == []


def test_a_planted_fault_per_profile_field():
    state, found = deliver.profile_gate({"streams": []}, PROFILE, "Mono", 300, True)
    assert state == "failed" and set(found) == set(findings.PROFILE_FIELDS)
    report = clean_report() | {"profile": {"findings": found}}
    rows = deliver.typed_findings(report, JOB)
    assert sorted(codes(rows)) == sorted(f"profile_{name}" for name in findings.PROFILE_FIELDS)
    assert all(row["gate"] == "profile" and row["stage"] == "base" for row in rows)
    row = next(r for r in rows if r["code"] == "profile_video_codec")
    assert row["detail"] == {"want": "h264", "got": None}


def test_a_planted_fault_per_captions_code():
    state, found = deliver.captions_gate(JOB, set(), [(0, 1, "Hello")], "x\n", 0)
    assert state == "failed" and len(found) == 5
    rows = deliver.typed_findings(clean_report() | {"captions": {"findings": found, "cues": 1}}, JOB)
    assert codes(rows) == [
        "captions_srt_missing",
        "captions_vtt_missing",
        "captions_soft_missing",
        "captions_persona_cue",
        "captions_extra_notice",
    ]


def test_each_loudness_limit_a_cut_misses_is_its_own_finding():
    report = clean_report()
    report["gates"]["loudness"] = "failed"
    report["loudness"] = {"drift_lu": -3.2, "integrated_lufs": -19.2, "true_peak_dbtp": -0.5}
    rows = deliver.typed_findings(report, JOB)
    assert codes(rows) == ["loudness_drift", "loudness_true_peak"]
    assert {row["stage"] for row in rows} == {"mix"}
    assert rows[0]["detail"] == {"drift_lu": -3.2, "limit": 1}


def test_every_slide_change_over_the_flash_limit_is_a_finding_with_its_page():
    report = clean_report()
    report["flash"]["changes"] = [
        {"at_s": 0, "max_jump": 0.5, "frame": 1},
        {"at_s": 2, "max_jump": 0.1, "frame": 60},
        {"at_s": 4, "max_jump": 0.9, "frame": 120},
    ]
    rows = deliver.typed_findings(report, JOB)
    assert codes(rows) == ["flash_jump", "flash_jump"] and [row["page"] for row in rows] == ["p0", "p1"]
    assert rows[1]["detail"]["max_jump"] == 0.9


def test_a_report_with_a_fault_in_every_gate_returns_them_all():
    report = clean_report()
    report["gates"] |= {"loudness": "failed", "flash": "failed"}
    report["profile"]["findings"] = {"pix_fmt": {"want": "yuv420p", "got": "yuv444p"}}
    report["loudness"]["drift_lu"] = 5
    report["flash"]["changes"][0]["max_jump"] = 2
    report["captions"]["findings"] = ["captions.srt is missing"]
    report["avatar_box"]["findings"] = [{"code": "avatar_box_occupied", "page": "p0", "source": "frame", "pixels": 9}]
    report["slide_match"]["findings"] = [{"code": "slide_not_shown", "page": "p1", "share": 0.5}]
    rows = deliver.typed_findings(report, JOB)
    assert codes(rows) == [
        "profile_pix_fmt",
        "loudness_drift",
        "flash_jump",
        "captions_srt_missing",
        "avatar_box_occupied",
        "slide_not_shown",
    ]


# speech.py -------------------------------------------------------------------------------------------------------
def test_each_lexical_finding_is_a_row_and_stays_advisory_with_no_match():
    report = {
        "findings": {
            "findings": [
                {"rule": "XL-FIX-001", "severity": "Error", "segment": "p1", "start": 4, "match": "delve"},
                {"rule": "XL-FIX-002", "severity": "Warning", "segment": "p1", "start": 9, "match": "tapestry"},
            ],
            "skipped": [],
        }
    }
    rows = speech.lexical_rows(report, "seg-1")
    assert codes(rows) == ["lexical_finding", "lexical_finding"]
    assert [row["blocking"] for row in rows] == [False, False] and {row["stage"] for row in rows} == {"script"}
    assert rows[0]["detail"] == {"rule": "XL-FIX-001", "severity": "Error", "start": 4}
    assert "delve" not in json.dumps(rows)


def test_each_failed_measured_gate_is_a_row():
    refusal = {"key": "k", "code": "voice_qa_failed", "detail": f"{speech.QA_FAILED}similarity, wer"}
    rows = speech.qa_rows("seg-1", refusal)
    assert [row["detail"]["metric"] for row in rows] == ["similarity", "wer"]
    assert {row["stage"] for row in rows} == {"script"} and {row["segment"] for row in rows} == {"seg-1"}


def test_a_voice_the_run_cannot_verify_is_a_row():
    rows = speech.qa_rows("seg-1", {"key": "k", "code": "voice_unverified", "detail": "the narrate run is gone"})
    assert codes(rows) == ["voice_unverified"] and rows[0]["detail"] == {}
    assert "gone" not in json.dumps(rows)


def test_reading_findings_moves_no_stage_key():
    """A voice key reads the script stage's digest, so a typed record never joins a stage's bytes."""
    assert graph.IMPL["script"] == 1 and graph.IMPL["deliver_check"] == 3
