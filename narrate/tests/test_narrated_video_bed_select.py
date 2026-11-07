"""Bed selection for a campaign job (docs/spec/NARRATED_VIDEO.md, "Bed selection", ruling TIN-7125 e552e569).

The judge and the catalog are fakes, so nothing here reaches a vendor, spends a credit or downloads a sound. Every loop
is a generated sine WAV, and every id is synthetic.
"""

import copy
import hashlib
import json
import math
import shutil
import struct
import wave
from pathlib import Path

import pytest

from narrate.video import bed_select, bundle, cli, fixture, music, rerun, store
from narrate.video.admit import admit
from narrate.video.bed_select import CatalogError, FileJudge, pick, read_selection, select_bed
from narrate.video.common import Env, StageRefused
from narrate.video.job import DEFAULTS, JobError, check_shape, load_records

TEMPLATE, VOICE, ENGINE = fixture.NARRATE_JOB, "voice-fixture-sine", "fake-sine"
CAMPAIGN = "campaign-fixture"
BUDGET = 10
JOB = "demo-fixture"
PLAN = {"wanted": True, "reason": "a long stretch of narration over a still", "query": "soft pad in E major"}
NOT_WANTED = {"wanted": False, "reason": "the demo's own sound carries it"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sine_wav(path, period, seconds=1, rate=48000):
    """One generated loop: a whole number of periods at a low level, so a sum never clips."""
    frames = b"".join(
        struct.pack("<h", round(2000 * math.sin(2 * math.pi * n / period))) for n in range(rate * seconds)
    )
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(frames)
    return path


class FakeJudge:
    def __init__(self, decision):
        self.decision, self.briefs = decision, []

    def judge(self, brief):
        self.briefs.append(brief)
        return self.decision


class FakeCatalog:
    """Catalog rows in order, and generated files per asset. It counts every call, and no call leaves this process."""

    source = "Splice"
    terms_ref = "https://example.invalid/terms, last updated 2026-11-02"
    terms_read_on = "2026-11-07"

    def __init__(self, rows=None, fail_on=None):
        self.rows = rows if rows is not None else loops(3)
        self.searches, self.downloads, self.fail_on = [], [], fail_on

    def search(self, query, bpm_min, bpm_max):
        self.searches.append((query, bpm_min, bpm_max))
        return copy.deepcopy(self.rows)

    def download(self, asset_id, directory):
        self.downloads.append(asset_id)
        if asset_id == self.fail_on:
            raise CatalogError(f"the vendor said no about {asset_id}")
        period = 100 + sum(asset_id.encode())
        return sine_wav(Path(directory) / f"vendor-name-{asset_id}.wav", period)


def loops(count, **fields):
    return [
        {"asset_id": f"asset-{i}", "type": "loop", "bpm": 120, "key": "E major", "preview": False, "name": f"pad {i}"}
        | fields
        for i in range(count)
    ]


def clock(stamp):
    return lambda: stamp


@pytest.fixture
def ws(tmp_path):
    paths = fixture.write(tmp_path / "ws")
    paths["bundle"] = fixture.write_bundle(tmp_path / "bundles")
    paths["root"] = tmp_path / "narrated"
    return paths


def select(ws, decision=PLAN, catalog=None, budget=BUDGET, stamp="2026-11-07T12:00:00Z", **kw):
    catalog = FakeCatalog() if catalog is None else catalog
    return select_bed(
        {"job": JOB},
        FakeJudge(decision),
        catalog,
        campaign=kw.pop("campaign", CAMPAIGN),
        budget=budget,
        root=ws["root"],
        store_dir=ws["store"],
        job=JOB,
        now=clock(stamp),
        **kw,
    )


def saved(tmp_path, selection, name="selection.json"):
    path = tmp_path / name
    bed_select.write_selection(path, selection)
    return path


def run_intake(ws, out, selection_path, campaign=CAMPAIGN):
    return bundle.intake(
        ws["bundle"], out, ws["records"], template=TEMPLATE, voice=VOICE, engine=ENGINE, store=ws["store"],
        bed_selection=selection_path, campaign=campaign,
    )  # fmt: skip


def stage_manifest(s, stage):
    current = json.loads((s.dir / "current.json").read_text())["stages"][stage]
    return json.loads((s.dir / current["dir"] / "manifest.json").read_text())


def refused_code(fn, *args, **kw):
    with pytest.raises(JobError) as error:
        fn(*args, **kw)
    return error.value.code


def ledger_rows(ws):
    path = ws["root"] / bed_select.LEDGER
    return json.loads(path.read_text())["rows"] if path.exists() else []


def ledger_row(**fields):
    row = {"month": "2026-11", "asset_id": "asset-0", "credits": 1, "campaign": CAMPAIGN, "job": None,
           "recorded_utc": "2026-11-07T12:00:00Z", "sha256": None}  # fmt: skip
    return row | fields


def bed_job(edition="Internal", bed_id="bed-x"):
    """The shape admit needs: the fixture job's records with a bed named and one edition."""
    job = fixture_job()
    job["edition"] = edition
    job["music"] = copy.deepcopy(DEFAULTS["music"]) | {"bed": bed_id}
    return job


def fixture_job():
    return {
        "id": JOB,
        "edition": "Internal",
        "base": {
            "card": {"colour": "#101820", "size": {"w": 1920, "h": 1080}, "fps": {"num": 30, "den": 1}, "tailS": 1}
        },
        "segments": [],
        "avatar": None,
        "slides": None,
        "music": None,
        "tighten": copy.deepcopy(DEFAULTS["tighten"]),
        "captions": copy.deepcopy(DEFAULTS["captions"]),
        "labels": copy.deepcopy(DEFAULTS["labels"]),
        "delivery": copy.deepcopy(DEFAULTS["delivery"]),
    }


def bed_codes(bed, edition="Internal", campaign=CAMPAIGN):
    job = bed_job(edition, bed["id"])
    records = {"jobs": {}, "voices": {}, "consents": {}, "music_beds": {bed["id"]: bed}, "visible_text": None}
    return [r["code"] for r in admit(job, records, campaign=campaign)["refusals"]]


# Evidence 1: a bedless job still passes ---------------------------------------------------------------------------
def test_a_job_the_judge_wants_no_bed_for_spends_nothing(ws):
    catalog, judge = FakeCatalog(), FakeJudge(NOT_WANTED)
    selection = select_bed(
        {"job": JOB}, judge, catalog, campaign=CAMPAIGN, budget=None, root=ws["root"], store_dir=None, job=JOB
    )
    assert selection["outcome"] == "bedless" and selection["bedless_reason"] == "not_wanted"
    assert selection["bed"] is None and selection["credits"] is None
    assert judge.briefs == [{"job": JOB}]
    assert catalog.searches == [] and catalog.downloads == [] and ledger_rows(ws) == []


def test_a_bedless_selection_gives_a_job_that_passes_through_plan(ws, tmp_path, capsys):
    path = saved(tmp_path, select(ws, NOT_WANTED))
    out = tmp_path / "out"
    manifest = run_intake(ws, out, path)
    job = json.loads((out / "narrated-video.json").read_text())
    assert job["music"] is None and check_shape(job) == job
    assert manifest["bed_selection"]["outcome"] == "bedless" and manifest["bed_selection"]["bed"] is None
    assert manifest["bed_selection"]["selection_sha256"] == sha(path)
    common = ["--root", str(ws["root"]), "--records", str(out / "records"), "--store", str(ws["store"])]
    assert cli.main(["init", "--job", JOB, "--from", str(out / "narrated-video.json"), *common]) == 0
    capsys.readouterr()
    assert cli.main(["plan", JOB, "--json", *common]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["admit"]["verdict"] == "Admitted"
    assert {n["id"]: n["state"] for n in plan["nodes"]}["music"] == "not_selected"
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg is not on PATH")
    assert cli.main(["run", JOB, *common, "--lexical", str(ws["lexical"])]) == 0
    deliver = stage_manifest(store.JobStore(ws["root"], JOB), "deliver_check")["measurements"]
    assert deliver["delivery_gate"]["internal_review_allowed"] is True
    assert deliver["gates"]["bed_licence_pdf"] == "not_applicable"


def test_a_job_with_no_selection_is_what_it_was(ws, tmp_path):
    out = tmp_path / "out"
    manifest = bundle.intake(
        ws["bundle"], out, ws["records"], template=TEMPLATE, voice=VOICE, engine=ENGINE, store=ws["store"]
    )
    assert json.loads((out / "narrated-video.json").read_text())["music"] is None
    assert "bed_selection" not in manifest


def test_a_search_with_too_few_fitting_loops_is_bedless_with_no_spend(ws):
    catalog = FakeCatalog(loops(1))
    selection = select(ws, catalog=catalog)
    assert selection["outcome"] == "bedless" and selection["bedless_reason"] == "no_candidates"
    assert catalog.downloads == [] and ledger_rows(ws) == []


# Evidence 2: a selected bed binds by digest -------------------------------------------------------------------------
def test_a_selected_bed_binds_each_loop_by_digest_with_its_licence_record(ws):
    catalog = FakeCatalog()
    selection = select(ws, catalog=catalog)
    bed = selection["bed"]
    assert selection["outcome"] == "selected" and bed["id"] == bed_select.bound_id(bed)
    assert len(bed["layers"]) == 2 and catalog.downloads == ["asset-0", "asset-1"]
    for layer in bed["layers"]:
        held = next(Path(ws["store"]).glob(f"{layer['sha256']}.*"))
        assert sha(held) == layer["sha256"] and held.stat().st_size == layer["bytes"]
        assert layer["rateHz"] == 48000 and layer["channels"] == 1 and layer["source"] == "Splice"
    assert bed["licence"] == {
        "termsRef": FakeCatalog.terms_ref,
        "termsReadOn": "2026-11-07",
        "attributionRequired": False,
        "attributionText": None,
        "certifiedPdfSha256": None,
        "contentIdCheck": "NotRun",
    }
    assert bed["acquisition"] == {
        "acquiredBy": {"agent": CAMPAIGN},
        "date": "2026-11-07",
        "creditsSpent": 2,
        "rulingRef": bed_select.RULING,
    }
    assert selection["credits"] == {"month": "2026-11", "credits": 2, "spent_month": 2, "budget": BUDGET}


def test_a_later_licence_result_does_not_move_the_id_and_anything_else_does(ws):
    bed = select(ws)["bed"]
    held = bed["id"]
    later = copy.deepcopy(bed)
    later["licence"].update(certifiedPdfSha256="f" * 64, contentIdCheck={"clear": "probe"})
    assert bed_select.bound_id(later) == held
    for edit in (
        lambda b: b["layers"][0].update(sha256="0" * 64),
        lambda b: b["layers"][1].update(bytes=1),
        lambda b: b["licence"].update(termsRef="other terms"),
        lambda b: b["acquisition"].update(creditsSpent=0),
    ):
        changed = copy.deepcopy(bed)
        edit(changed)
        assert bed_select.bound_id(changed) != held


def test_intake_carries_the_bed_into_the_job_and_its_records(ws, tmp_path):
    selection = select(ws)
    path = saved(tmp_path, selection)
    out = tmp_path / "out"
    manifest = run_intake(ws, out, path)
    job = json.loads((out / "narrated-video.json").read_text())
    bed = selection["bed"]
    assert job["music"]["bed"] == bed["id"] and check_shape(job) == job
    assert load_records(out / "records")["music_beds"][bed["id"]] == bed
    assert manifest["bed_selection"] == {
        "campaign": CAMPAIGN,
        "outcome": "selected",
        "selection_sha256": sha(path),
        "bed": bed["id"],
        "layers": [layer["sha256"] for layer in bed["layers"]],
    }
    assert str(tmp_path) not in json.dumps(manifest)


@pytest.mark.parametrize(
    ("damage", "code"),
    [
        (lambda p: p.unlink(), "bed_loop_missing"),
        (lambda p: p.write_bytes(p.read_bytes() + b"\0"), "bed_digest_mismatch"),
    ],
)
def test_intake_refuses_a_loop_off_its_digest_and_writes_nothing(ws, tmp_path, damage, code):
    selection = select(ws)
    path = saved(tmp_path, selection)
    held = next(Path(ws["store"]).glob(f"{selection['bed']['layers'][0]['sha256']}.*"))
    damage(held)
    out = tmp_path / "out"
    assert refused_code(run_intake, ws, out, path) == code
    assert not out.exists()


def test_intake_refuses_a_hand_edited_or_foreign_selection(ws, tmp_path):
    selection = select(ws)
    edited = copy.deepcopy(selection)
    edited["bed"]["layers"][0]["sha256"] = "0" * 64
    assert (
        refused_code(run_intake, ws, tmp_path / "a", saved(tmp_path, edited, "edited.json")) == "bed_selection_invalid"
    )
    other = saved(tmp_path, selection, "other.json")
    assert refused_code(run_intake, ws, tmp_path / "b", other, "another-campaign") == "bed_selection_campaign"
    assert refused_code(read_selection, other, None) == "bed_selection_campaign"
    assert refused_code(run_intake, ws, tmp_path / "c", None, CAMPAIGN) == "bed_selection_invalid"
    path_like = copy.deepcopy(selection)
    path_like["bed"]["layers"][0]["sha256"] = "../../outside"
    path_like["bed"]["id"] = bed_select.bound_id(path_like["bed"])
    forged = saved(tmp_path, path_like, "forged.json")
    assert refused_code(run_intake, ws, tmp_path / "e", forged) == "bed_selection_invalid"
    junk = tmp_path / "junk.json"
    junk.write_text(json.dumps({"kind": "other"}))
    assert refused_code(run_intake, ws, tmp_path / "d", junk) == "bed_selection_invalid"


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is not on PATH")
def test_a_bound_campaign_job_runs_the_music_stage_on_the_selected_loops(ws, tmp_path, capsys):
    selection = select(ws)
    bed = selection["bed"]
    out = tmp_path / "out"
    run_intake(ws, out, saved(tmp_path, selection))
    common = ["--root", str(ws["root"]), "--records", str(out / "records"), "--store", str(ws["store"]),
              "--lexical", str(ws["lexical"])]  # fmt: skip
    from_file = ["--job", JOB, "--from", str(out / "narrated-video.json")]
    assert cli.main(["init", *from_file, "--campaign", CAMPAIGN, *common]) == 0
    capsys.readouterr()
    assert rerun.read(store.JobStore(ws["root"], JOB))["campaign"]["id"] == CAMPAIGN
    assert cli.main(["plan", JOB, "--json", *common]) == 0
    assert json.loads(capsys.readouterr().out)["admit"]["verdict"] == "Admitted"
    assert cli.main(["run", JOB, *common]) == 0
    s = store.JobStore(ws["root"], JOB)
    current = json.loads((s.dir / "current.json").read_text())["stages"]["music"]
    written = json.loads((s.dir / current["dir"] / "bed.json").read_text())
    assert written["bed"] == bed["id"]
    assert [r["sha256"] for r in written["layers"]] == [layer["sha256"] for layer in bed["layers"]]
    assert "asset-" not in json.dumps(written) and "vendor-name" not in json.dumps(written)
    deliver = stage_manifest(s, "deliver_check")["measurements"]
    assert deliver["delivery_gate"]["public_upload_allowed"] is False


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is not on PATH")
def test_a_damaged_loop_refuses_the_music_stage_of_a_bound_job(ws, tmp_path, capsys):
    selection = select(ws)
    out = tmp_path / "out"
    run_intake(ws, out, saved(tmp_path, selection))
    common = ["--root", str(ws["root"]), "--records", str(out / "records"), "--store", str(ws["store"]),
              "--lexical", str(ws["lexical"])]  # fmt: skip
    assert (
        cli.main(["init", "--job", JOB, "--from", str(out / "narrated-video.json"), "--campaign", CAMPAIGN, *common])
        == 0
    )
    capsys.readouterr()
    held = next(Path(ws["store"]).glob(f"{selection['bed']['layers'][0]['sha256']}.*"))
    held.write_bytes(held.read_bytes() + b"\0")
    assert cli.main(["stage", JOB, "music", *common]) != 0
    assert "source_missing" in capsys.readouterr().out


# Evidence 3: the guard refuses past the budget ----------------------------------------------------------------------
def test_the_guard_refuses_past_the_budget_before_any_download(ws):
    catalog = FakeCatalog()
    held = sorted(p.name for p in Path(ws["store"]).iterdir())
    assert refused_code(select, ws, catalog=catalog, budget=1) == "bed_credit_budget"
    assert catalog.searches and catalog.downloads == [] and ledger_rows(ws) == []
    assert sorted(p.name for p in Path(ws["store"]).iterdir()) == held


def test_the_guard_lets_the_exact_budget_through_and_counts_the_month(ws):
    first = FakeCatalog(loops(2))
    assert select(ws, catalog=first, budget=4)["credits"]["spent_month"] == 2
    second_rows = loops(2)
    for i, row in enumerate(second_rows):
        row["asset_id"] = f"asset-second-{i}"
    assert select(ws, catalog=FakeCatalog(second_rows), budget=4)["credits"]["spent_month"] == 4
    third_rows = loops(2)
    for i, row in enumerate(third_rows):
        row["asset_id"] = f"asset-third-{i}"
    third = FakeCatalog(third_rows)
    assert refused_code(select, ws, catalog=third, budget=4) == "bed_credit_budget"
    assert third.downloads == []
    assert sum(row["credits"] for row in ledger_rows(ws)) == 4


def test_a_new_month_starts_the_count_again(ws):
    select(ws, catalog=FakeCatalog(loops(2)), budget=2)
    rows = loops(2)
    for i, row in enumerate(rows):
        row["asset_id"] = f"asset-december-{i}"
    assert select(ws, catalog=FakeCatalog(rows), budget=2, stamp="2026-12-01T00:00:00Z")["credits"] == {
        "month": "2026-12",
        "credits": 2,
        "spent_month": 2,
        "budget": 2,
    }


def test_a_repeat_download_costs_nothing_even_at_the_budget(ws):
    select(ws, catalog=FakeCatalog(loops(2)), budget=2)
    again = select(ws, catalog=FakeCatalog(loops(2)), budget=2)
    assert again["outcome"] == "selected" and again["credits"]["credits"] == 0
    assert again["bed"]["acquisition"]["creditsSpent"] == 0
    assert len(ledger_rows(ws)) == 2


@pytest.mark.parametrize("budget", [None, 0, -1, True, "10"])
def test_a_wanted_bed_needs_a_budget_and_no_default_stands_in(ws, budget):
    catalog = FakeCatalog()
    assert refused_code(select, ws, catalog=catalog, budget=budget) == "bed_credit_budget_missing"
    assert catalog.searches == [] and catalog.downloads == []


def test_a_failed_download_stays_counted_and_its_text_stays_out(ws):
    catalog = FakeCatalog(fail_on="asset-1")
    with pytest.raises(JobError) as error:
        select(ws, catalog=catalog)
    assert error.value.code == "bed_catalog_failed" and "asset-1" not in str(error.value)
    assert [row["asset_id"] for row in ledger_rows(ws)] == ["asset-0", "asset-1"]
    assert [row["sha256"] is not None for row in ledger_rows(ws)] == [True, False]


def test_the_ledger_binds_each_sound_to_the_digest_it_arrived_as(ws):
    bed = select(ws)["bed"]
    assert [row["sha256"] for row in ledger_rows(ws)] == [layer["sha256"] for layer in bed["layers"]]
    assert [row["asset_id"] for row in ledger_rows(ws)] == ["asset-0", "asset-1"]


@pytest.mark.parametrize(
    "value",
    [
        {"kind": "other", "schema_version": 1, "rows": []},
        {"kind": bed_select.LEDGER_KIND, "schema_version": 1, "rows": [{"month": "2026-11"}]},
        {"kind": bed_select.LEDGER_KIND, "schema_version": 1, "rows": [ledger_row(month="not-a-month")]},
        {"kind": bed_select.LEDGER_KIND, "schema_version": 1, "rows": [ledger_row(month="2026-13")]},
        {"kind": bed_select.LEDGER_KIND, "schema_version": 1, "rows": [ledger_row(asset_id="")]},
        {"kind": bed_select.LEDGER_KIND, "schema_version": 2, "rows": []},
        [],
    ],
)
def test_a_damaged_ledger_refuses_instead_of_reading_as_empty(ws, value):
    ws["root"].mkdir(parents=True, exist_ok=True)
    (ws["root"] / bed_select.LEDGER).write_text(json.dumps(value))
    catalog = FakeCatalog()
    assert refused_code(select, ws, catalog=catalog) == "store_invalid"
    assert catalog.downloads == []


def test_after_a_budget_refusal_a_bedless_decision_still_gives_a_passing_job(ws, tmp_path):
    assert refused_code(select, ws, budget=1) == "bed_credit_budget"
    out = tmp_path / "out"
    run_intake(ws, out, saved(tmp_path, select(ws, NOT_WANTED, budget=1)))
    assert json.loads((out / "narrated-video.json").read_text())["music"] is None


# NV-3 stands off a campaign -------------------------------------------------------------------------------------
def agent_bed(ws):
    return select(ws)["bed"]


def test_an_agents_bed_is_admitted_only_on_its_campaigns_root(ws):
    bed = agent_bed(ws)
    assert bed_codes(bed) == []
    assert bed_codes(bed, campaign=None) == ["bed_acquisition_agent"]
    assert bed_codes(bed, campaign="another-campaign") == ["bed_acquisition_agent"]


@pytest.mark.parametrize("edition", ["ClientNarrated", "ClientVoiceOnly"])
def test_a_client_edition_refuses_an_agents_bed_even_when_cleared(ws, edition):
    bed = agent_bed(ws)
    bed["licence"].update(certifiedPdfSha256="f" * 64, contentIdCheck={"clear": "probe"})
    assert "bed_acquisition_agent" in bed_codes(bed, edition)


def test_an_agents_record_edited_after_selection_refuses(ws):
    bed = agent_bed(ws)
    bed["layers"][0]["sha256"] = "0" * 64
    assert bed_codes(bed) == ["bed_digest_mismatch"]


def test_an_agents_record_with_no_terms_refuses(ws):
    bed = agent_bed(ws)
    bed["licence"]["termsReadOn"] = None
    bed["id"] = bed_select.bound_id(bed)
    assert bed_codes(bed) == ["bed_licence_missing"]


@pytest.mark.parametrize("acquired", ["Agent", {"agent": ""}, {"agent": "two words"}, {"agent": 1}, {"other": "x"}])
def test_any_other_acquirer_still_refuses(ws, acquired):
    bed = agent_bed(ws)
    bed["acquisition"]["acquiredBy"] = acquired
    assert bed_codes(bed) == ["bed_acquisition_agent"]


def test_an_operators_bed_is_as_it_was(ws):
    bed = json.loads((ws["records"] / "music-beds.json").read_text())[0]
    assert bed_codes(bed, campaign=None) == []


def test_the_music_stage_refuses_an_agents_bed_on_an_unbound_root(ws, tmp_path, capsys):
    selection = select(ws)
    out = tmp_path / "out"
    run_intake(ws, out, saved(tmp_path, selection))
    common = ["--root", str(ws["root"]), "--records", str(out / "records"), "--store", str(ws["store"])]
    from_file = ["--job", JOB, "--from", str(out / "narrated-video.json")]
    assert cli.main(["init", *from_file, *common]) == 1  # admit refuses it, so no root is written
    assert "bed_acquisition_agent" in capsys.readouterr().err
    assert not (ws["root"] / JOB / "job.json").exists()

    s = store.JobStore(ws["root"], JOB)
    job = json.loads((out / "narrated-video.json").read_text())
    s.write_job(job)  # a job written around admit still meets the stage's own check
    records = load_records(out / "records")

    class Context:
        store = s
        env = Env(out / "records", records, ws["store"], None)

    Context.job, Context.records = job, records
    with pytest.raises(StageRefused) as error:
        music.run_music(Context, None, tmp_path)
    assert error.value.code == "bed_acquisition_agent"


def test_init_refuses_a_campaign_on_a_client_edition_before_it_writes(ws, tmp_path, capsys):
    script = tmp_path / "script.md"
    script.write_text("synthetic")
    common = ["--root", str(ws["root"]), "--records", str(ws["records"]), "--store", str(ws["store"])]
    code = cli.main(
        ["init", "--job", JOB, "--client", "--no-avatar", "--narrate-job", TEMPLATE, "--script", str(script),
         "--campaign", CAMPAIGN, *common]
    )  # fmt: skip
    assert code == 1
    assert "campaign_client_job" in capsys.readouterr().err
    assert not (ws["root"] / JOB / "job.json").exists()


# The rule -----------------------------------------------------------------------------------------------------------
def test_preview_audio_and_one_shots_are_never_picked(ws):
    rows = loops(4)
    rows[0]["preview"] = True
    rows[1]["type"] = "oneshot"
    catalog = FakeCatalog(rows)
    select(ws, catalog=catalog)
    assert catalog.downloads == ["asset-2", "asset-3"]


@pytest.mark.parametrize("mark", [1, "true", "false", None, "absent"])
def test_a_row_that_does_not_say_it_is_no_preview_is_not_picked(mark):
    rows = loops(2)
    for row in rows:
        row.pop("preview")
        if mark != "absent":
            row["preview"] = mark
    assert pick(rows, 2) is None


def test_the_pick_keeps_the_first_rows_key_and_the_tempo_bound():
    rows = loops(5)
    rows[1]["key"] = "A minor"
    rows[2]["bpm"] = 300  # 120 / 300 is under the 0.5 bound
    rows[3]["bpm"] = 90
    picked = pick(rows, 2)
    assert [r["asset_id"] for r in picked] == ["asset-0", "asset-3"]
    assert pick(rows[:3], 2) is None
    assert pick("not rows", 2) is None
    assert pick([rows[0], rows[0]], 2) is None


def test_the_tempo_factor_brings_a_layer_to_the_first_rows_tempo(ws):
    rows = loops(2)
    rows[1]["bpm"] = 100
    bed = select(ws, catalog=FakeCatalog(rows))["bed"]
    assert [layer["tempoFactor"] for layer in bed["layers"]] == [1.0, 1.2]
    assert [layer["gainDb"] for layer in bed["layers"]] == [0.0, bed_select.UPPER_LAYER_GAIN_DB]


def test_three_layers_on_request(ws):
    assert len(select(ws, PLAN | {"layers": 3})["bed"]["layers"]) == 3


@pytest.mark.parametrize(
    "decision",
    [
        None,
        {"wanted": "yes", "reason": "x", "query": "y"},
        {"wanted": True, "reason": "", "query": "y"},
        {"wanted": True, "reason": "x"},
        {"wanted": True, "reason": "x", "query": "y", "layers": 4},
        {"wanted": True, "reason": "x", "query": "y", "layers": True},
        {"wanted": True, "reason": "x", "query": "y", "bpm_min": "fast"},
        {"wanted": False},
        {"wanted": False, "reason": "x" * 201},
        {"wanted": False, "reason": "x", "url": "https://example.invalid/"},
    ],
)
def test_a_malformed_decision_refuses(ws, decision):
    catalog = FakeCatalog()
    assert refused_code(select, ws, decision, catalog) == "bed_decision_invalid"
    assert catalog.searches == []


@pytest.mark.parametrize("field", ["terms_read_on", "terms_ref", "source"])
def test_a_catalog_with_no_terms_refuses_before_any_search(ws, field):
    catalog = FakeCatalog()
    setattr(catalog, field, None)
    assert refused_code(select, ws, catalog=catalog) == "bed_licence_missing"
    assert catalog.searches == []


def test_two_rows_that_give_one_file_refuse(ws):
    catalog = FakeCatalog()
    catalog.download = lambda asset_id, directory: sine_wav(Path(directory) / "same.wav", 120)
    assert refused_code(select, ws, catalog=catalog) == "bed_layers_invalid"


def test_a_file_that_is_no_audio_refuses(ws):
    catalog = FakeCatalog()

    def not_audio(asset_id, directory):
        path = Path(directory) / "x.wav"
        path.write_bytes(b"not audio")
        return path

    catalog.download = not_audio
    assert refused_code(select, ws, catalog=catalog) == "bed_loop_unreadable"


def test_a_campaign_id_keeps_its_form(ws):
    assert refused_code(select, ws, campaign="two words") == "campaign_id_invalid"


@pytest.mark.parametrize("source", ["YoutubeAudioLibrary", "SelfMade", "Fixture"])
def test_a_catalog_off_the_ruling_refuses_before_any_search(ws, source):
    catalog = FakeCatalog()
    catalog.source = source
    assert refused_code(select, ws, catalog=catalog) == "bed_licence_missing"
    assert catalog.searches == []


@pytest.mark.parametrize("source", ["YoutubeAudioLibrary", "SelfMade", "Fixture", "scraped"])
def test_an_agents_record_naming_another_source_refuses(ws, source):
    bed = agent_bed(ws)
    bed["layers"][0]["source"] = source
    bed["id"] = bed_select.bound_id(bed)
    assert bed_codes(bed) == ["bed_acquisition_agent"]


# A record no one bought --------------------------------------------------------------------------------------------
def forged(ws, tmp_path):
    """A selection the stage never wrote: other files from the store under a recomputed id, with no credit counted."""
    bed = select(ws)["bed"]
    made = tmp_path / "made"
    made.mkdir()
    for i, layer in enumerate(bed["layers"]):
        loop = sine_wav(made / f"{i}.wav", 150 + 20 * i)
        layer.update(sha256=sha(loop), bytes=loop.stat().st_size)
        shutil.copy(loop, Path(ws["store"]) / f"{sha(loop)}.wav")
    bed["acquisition"]["creditsSpent"] = 0
    bed["id"] = bed_select.bound_id(bed)
    return {"kind": bed_select.KIND, "schema_version": 1, "campaign": CAMPAIGN, "outcome": "selected", "bed": bed}


def test_a_loop_the_ledger_never_counted_refuses_at_init_and_in_the_stage(ws, tmp_path, capsys):
    out = tmp_path / "out"
    run_intake(ws, out, saved(tmp_path, forged(ws, tmp_path)))  # intake has no root, so plan and the stage hold this
    common = ["--root", str(ws["root"]), "--records", str(out / "records"), "--store", str(ws["store"])]
    from_file = ["--job", JOB, "--from", str(out / "narrated-video.json"), "--campaign", CAMPAIGN]
    assert cli.main(["init", *from_file, *common]) == 1
    assert "bed_unledgered" in capsys.readouterr().err
    assert not (ws["root"] / JOB / "job.json").exists()

    s = store.JobStore(ws["root"], JOB)
    job = json.loads((out / "narrated-video.json").read_text())
    s.write_job(job)  # a job written around admit still meets the stage's own check
    rerun.bind_campaign(s, CAMPAIGN)
    records = load_records(out / "records")

    class Context:
        store = s
        env = Env(out / "records", records, ws["store"], None)

    Context.job, Context.records = job, records
    with pytest.raises(StageRefused) as error:
        music.run_music(Context, None, tmp_path)
    assert error.value.code == "bed_unledgered"


def test_a_bed_counted_under_another_root_refuses_on_this_one(ws, tmp_path, capsys):
    selection = select({**ws, "root": tmp_path / "other-root"})
    out = tmp_path / "out"
    run_intake(ws, out, saved(tmp_path, selection))
    common = ["--root", str(ws["root"]), "--records", str(out / "records"), "--store", str(ws["store"])]
    code = cli.main(["init", "--job", JOB, "--from", str(out / "narrated-video.json"), "--campaign", CAMPAIGN, *common])
    assert code == 1 and "bed_unledgered" in capsys.readouterr().err


def test_an_operators_bed_never_reads_the_ledger(ws, tmp_path):
    (ws["root"]).mkdir(parents=True, exist_ok=True)
    (ws["root"] / bed_select.LEDGER).write_text("not json")
    bed = json.loads((ws["records"] / "music-beds.json").read_text())[0]
    assert bed_select.acquisition_problems(bed, "Internal", None, ws["root"]) == []


@pytest.mark.parametrize(
    "gates",
    [
        {"certifiedPdfSha256": "f" * 64},
        {"contentIdCheck": {"clear": "probe"}},
        {"contentIdCheck": {"claimed": "probe"}},
    ],
)
def test_a_selection_that_arrives_with_a_gate_set_refuses(ws, tmp_path, gates):
    selection = select(ws)
    selection["bed"]["licence"].update(gates)
    out = tmp_path / "out"
    assert refused_code(run_intake, ws, out, saved(tmp_path, selection)) == "bed_selection_invalid"
    assert not out.exists()


@pytest.mark.parametrize("field", sorted(bed_select.LAYER_FIELDS - {"sha256", "bytes"}))
def test_a_selection_short_of_a_layer_field_refuses(ws, tmp_path, field):
    selection = select(ws)
    selection["bed"]["layers"][0].pop(field)
    selection["bed"]["id"] = bed_select.bound_id(selection["bed"])
    assert refused_code(run_intake, ws, tmp_path / "out", saved(tmp_path, selection)) == "bed_selection_invalid"


def records_with(ws, tmp_path, row):
    records = tmp_path / "records"
    shutil.copytree(ws["records"], records)
    rows = json.loads((records / "music-beds.json").read_text())
    (records / "music-beds.json").write_text(json.dumps(rows + [row]))
    return records


def intake_on(ws, out, records, path):
    return bundle.intake(
        ws["bundle"], out, records, template=TEMPLATE, voice=VOICE, engine=ENGINE, store=ws["store"],
        bed_selection=path, campaign=CAMPAIGN,
    )  # fmt: skip


def test_records_holding_another_bed_under_the_selections_id_refuse(ws, tmp_path):
    selection = select(ws)
    other = json.loads((ws["records"] / "music-beds.json").read_text())[0] | {"id": selection["bed"]["id"]}
    records = records_with(ws, tmp_path, other)
    out = tmp_path / "out"
    assert refused_code(intake_on, ws, out, records, saved(tmp_path, selection)) == "bed_selection_invalid"
    assert not out.exists()


def test_records_holding_this_bed_with_a_later_result_keep_it(ws, tmp_path):
    selection = select(ws)
    later = copy.deepcopy(selection["bed"])
    later["licence"]["contentIdCheck"] = {"claimed": "probe"}
    records = records_with(ws, tmp_path, later)
    out = tmp_path / "out"
    intake_on(ws, out, records, saved(tmp_path, selection))
    assert load_records(out / "records")["music_beds"][later["id"]] == later


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is not on PATH")
def test_a_record_cleared_by_hand_with_upload_set_still_allows_no_public_upload(ws, tmp_path, capsys):
    """The id leaves the licence results out, so an edit to them shows nowhere. Listening still holds public shut."""
    selection = select(ws)
    out = tmp_path / "out"
    run_intake(ws, out, saved(tmp_path, selection))
    beds = json.loads((out / "records" / "music-beds.json").read_text())
    for row in beds:
        if row["id"] == selection["bed"]["id"]:
            row["licence"].update(certifiedPdfSha256="f" * 64, contentIdCheck={"clear": "probe"})
    (out / "records" / "music-beds.json").write_text(json.dumps(beds))
    job = json.loads((out / "narrated-video.json").read_text())
    job["delivery"]["upload"] = True
    (out / "narrated-video.json").write_text(json.dumps(job))
    common = ["--root", str(ws["root"]), "--records", str(out / "records"), "--store", str(ws["store"]),
              "--lexical", str(ws["lexical"])]  # fmt: skip
    from_file = ["--job", JOB, "--from", str(out / "narrated-video.json"), "--campaign", CAMPAIGN]
    assert cli.main(["init", *from_file, *common]) == 0
    assert cli.main(["run", JOB, *common]) == 0
    deliver = stage_manifest(store.JobStore(ws["root"], JOB), "deliver_check")["measurements"]
    assert deliver["delivery_gate"]["upload_gates_closed"] is True  # the bed gates alone do not say public
    assert deliver["delivery_gate"]["public_upload_allowed"] is False
    assert "listening" in deliver["delivery_gate"]["operator_states_open"]


# The command --------------------------------------------------------------------------------------------------------
def decision_file(tmp_path, decision):
    path = tmp_path / "decision.json"
    path.write_text(json.dumps(decision))
    return path


def test_the_command_writes_a_bedless_selection_with_no_budget_or_store(ws, tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("NARRATE_STORE", raising=False)
    out = tmp_path / "selection.json"
    code = cli.main(["bed-select", "--campaign", CAMPAIGN, "--decision", str(decision_file(tmp_path, NOT_WANTED)),
                     "--out", str(out), "--root", str(ws["root"])])  # fmt: skip
    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["outcome"] == "bedless" and printed["layers"] == []
    assert NOT_WANTED["reason"] not in json.dumps(printed)
    assert read_selection(out, CAMPAIGN)[0]["decision"]["wanted"] is False


def test_the_command_ships_no_catalog_so_a_wanted_bed_refuses_and_spends_nothing(ws, tmp_path, capsys):
    out = tmp_path / "selection.json"
    code = cli.main(["bed-select", "--campaign", CAMPAIGN, "--decision", str(decision_file(tmp_path, PLAN)),
                     "--out", str(out), "--root", str(ws["root"]), "--monthly-credits", "10"])  # fmt: skip
    assert code == 1
    assert "bed_catalog_unconfigured" in capsys.readouterr().err
    assert not out.exists() and ledger_rows(ws) == []


def test_the_command_prints_no_vendor_id_and_the_selection_holds_none(ws, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "bed_catalog", lambda a: FakeCatalog())
    out = tmp_path / "selection.json"
    code = cli.main(["bed-select", "--campaign", CAMPAIGN, "--decision", str(decision_file(tmp_path, PLAN)),
                     "--out", str(out), "--root", str(ws["root"]), "--store", str(ws["store"]),
                     "--monthly-credits", "10", "--job", JOB])  # fmt: skip
    assert code == 0
    printed = capsys.readouterr().out
    for text in (printed, out.read_text()):
        assert "asset-" not in text and "vendor-name" not in text and "pad 0" not in text
    assert json.loads(printed)["credits"]["spent_month"] == 2


def test_the_command_reads_the_budget_from_the_environment_and_refuses_past_it(ws, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "bed_catalog", lambda a: FakeCatalog())
    monkeypatch.setenv(cli.BED_CREDITS_ENV, "1")
    code = cli.main(["bed-select", "--campaign", CAMPAIGN, "--decision", str(decision_file(tmp_path, PLAN)),
                     "--out", str(tmp_path / "s.json"), "--root", str(ws["root"]),
                     "--store", str(ws["store"])])  # fmt: skip
    assert code == 1
    assert "bed_credit_budget" in capsys.readouterr().err


def test_the_command_refuses_an_out_already_there_before_any_spend(ws, tmp_path, capsys, monkeypatch):
    catalog = FakeCatalog()
    monkeypatch.setattr(cli, "bed_catalog", lambda a: catalog)
    out = tmp_path / "selection.json"
    out.write_text("held")
    code = cli.main(["bed-select", "--campaign", CAMPAIGN, "--decision", str(decision_file(tmp_path, PLAN)),
                     "--out", str(out), "--root", str(ws["root"]), "--store", str(ws["store"]),
                     "--monthly-credits", "10"])  # fmt: skip
    assert code == 1 and "out_exists" in capsys.readouterr().err
    assert catalog.downloads == [] and ledger_rows(ws) == [] and out.read_text() == "held"


def test_the_command_refuses_an_out_with_no_directory_before_any_spend(ws, tmp_path, capsys, monkeypatch):
    catalog = FakeCatalog()
    monkeypatch.setattr(cli, "bed_catalog", lambda a: catalog)
    code = cli.main(["bed-select", "--campaign", CAMPAIGN, "--decision", str(decision_file(tmp_path, PLAN)),
                     "--out", str(tmp_path / "no" / "such" / "s.json"), "--root", str(ws["root"]),
                     "--store", str(ws["store"]), "--monthly-credits", "10"])  # fmt: skip
    assert code == 1 and "out_parent_missing" in capsys.readouterr().err
    assert catalog.searches == [] and catalog.downloads == [] and ledger_rows(ws) == []


@pytest.mark.parametrize(
    ("ceiling", "asked", "spent"),
    [("1", "1000", None), ("10", "1", None), ("10", "2", 2), ("2", "10", 2)],
)
def test_an_argument_lowers_the_workers_ceiling_and_never_raises_it(
    ws, tmp_path, capsys, monkeypatch, ceiling, asked, spent
):
    catalog = FakeCatalog()
    monkeypatch.setattr(cli, "bed_catalog", lambda a: catalog)
    monkeypatch.setenv(cli.BED_CREDITS_ENV, ceiling)
    code = cli.main(["bed-select", "--campaign", CAMPAIGN, "--decision", str(decision_file(tmp_path, PLAN)),
                     "--out", str(tmp_path / "s.json"), "--root", str(ws["root"]), "--store", str(ws["store"]),
                     "--monthly-credits", asked])  # fmt: skip
    if spent is None:
        assert code == 1 and "bed_credit_budget" in capsys.readouterr().err
        assert catalog.downloads == [] and ledger_rows(ws) == []
    else:
        assert code == 0 and json.loads(capsys.readouterr().out)["credits"]["spent_month"] == spent


def test_a_selection_file_is_written_once(ws, tmp_path):
    path = saved(tmp_path, select(ws, NOT_WANTED))
    assert refused_code(bed_select.write_selection, path, {}) == "out_exists"


def test_the_file_judge_reads_the_decision(tmp_path):
    assert FileJudge(decision_file(tmp_path, NOT_WANTED)).judge(None) == NOT_WANTED
