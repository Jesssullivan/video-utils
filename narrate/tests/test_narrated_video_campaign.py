"""The Campaign edition, its machine verdict and the look external (narrate/video/campaign.py, narrate/video/look.py,
docs/spec/NARRATED_VIDEO.md "Campaign verdict" and "Look external", Linear TIN-7788, rulings TIN-7125 52ca88bf,
0690fe88).

The bars: public stays false for client and internal jobs. A Campaign job reads true only with every gate and the
signed record's id. Listening and lip sync stay required for client and internal jobs. Everything is generated: the fake
engine's sine voice, a transparent ProRes clip and invented ids and digests. No engine, GPU or real look is used.
Nothing uploads.
"""

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from test_narrated_video_intake import intake
from test_narrated_video_simple import Workspace

from narrate.video import (
    accept,
    admit,
    avatar_manifest,
    campaign,
    cli,
    deliver,
    findings,
    fixture,
    graph,
    look,
    render_stage,
    rerun,
    run,
)
from narrate.video.job import CLIENT_EDITIONS, EDITIONS, JobError, init_job

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "narrated-video"
LOOK_ID = "look-fixture"
GRANT_ID = "consent-fixture-campaign"
CAMPAIGN_ID = "campaign-fixture"
PERSONA = "fixture-persona"
RENDER_SIZE = 64
ANCHORS = [hashlib.sha256(b"anchor-b").hexdigest(), hashlib.sha256(b"anchor-a").hexdigest()]
RECORD_SHA256 = hashlib.sha256(b"a signed campaign record").hexdigest()
DECISION = "sp:dec:01H00000000000000000000000"
OTHER_EDITIONS = [e for e in EDITIONS if e != "Campaign"]


def load_rig():
    spec = importlib.util.spec_from_file_location("vrm_rig_fixture", FIXTURES / "vrm_rig_fixture.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rig = load_rig()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture(autouse=True)
def no_whisper(monkeypatch, tmp_path):
    monkeypatch.setenv("NARRATE_WHISPER_MODEL", str(tmp_path / "no-whisper-model.bin"))


def grant_row(**edit):
    return rig.likeness_consent(GRANT_ID) | {"scopes": ["Likeness", "CampaignStandingRule"]} | edit


def put_rows(ws, name, rows):
    path = ws.paths["records"] / name
    held = json.loads(path.read_text()) if path.exists() else []
    ids = {r["id"] for r in rows}
    path.write_text(json.dumps([r for r in held if r["id"] not in ids] + rows, indent=1))
    ws.reload()


def look_record(clips=None, **edit):
    return {
        "id": LOOK_ID,
        "kind": "look",
        "anchors": ANCHORS,
        "likenessConsent": {"id": GRANT_ID, "ruling": "SP-R13"},
        "renderer": {"name": "fixture-clip", "version": "0"},
        "clips": clips or {},
    } | edit


def add_look(ws, clips=None, **edit):
    put_rows(ws, "consents.json", [grant_row()])
    put_rows(ws, "avatars.json", [look_record(clips, **edit)])


def campaign_job(ws, job_id="nv-campaign"):
    job = init_job(
        job_id,
        fixture.NARRATE_JOB,
        sha(ws.paths["script"]),
        edition="Campaign",
        avatar=True,
        persona=PERSONA,
        look=LOOK_ID,
    )
    job["avatar"]["renderSize"] = RENDER_SIZE
    return job


def run_job(ws, job, replace=False, **kwargs):
    s = ws.store(job, replace=replace)
    rc = run.RunContext(job, ws.records, s, ws.ctx(), ws.env)
    result, g = run.run(rc, **kwargs)
    return s, result, g


def make_clip(path, frames_count, size=RENDER_SIZE, rate="30/1", pix_fmt="yuva444p10le", codec="prores_ks"):
    """A transparent clip: what a look lane would hand the graph, with no face in it."""
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y", "-f", "lavfi",
            "-i", f"color=c=black@0.0:s={size}x{size}:r={rate},format={pix_fmt}",
            "-frames:v", str(frames_count), "-c:v", codec, "-profile:v", "4444", "-pix_fmt", pix_fmt, str(path),
        ],
        check=True,
    )  # fmt: skip


def voice_take(s):
    return s.manifest("voice/seg-1")["measurements"]["narrate_content_sha256"]


def take_frames(s):
    from narrate.video import face, kitpip

    run_dir = s.dir / s.entry("voice/seg-1")["dir"] / "narration"
    manifest, _, _ = kitpip.narration(run_dir)
    return face.from_narration(run_dir, manifest, {"num": 30, "den": 1})["frames"]


def add_clip(ws, s, base, **make):
    path = base / "look-clip.mov"
    make_clip(path, take_frames(s), **make)
    digest = ws.add_source(path)
    return {voice_take(s): {"sha256": digest, "bytes": path.stat().st_size}}


@pytest.fixture(scope="module")
def settled(tmp_path_factory, ffmpeg):
    """One Campaign job run end to end once on a transparent clip; tests copy it before changing it."""
    with pytest.MonkeyPatch.context() as mp:
        base = tmp_path_factory.mktemp("campaign")
        for name in (
            "WHISPER_MODEL",
            "NARRATE_STORE",
            "NARRATE_LEXICAL_DIR",
            "NARRATE_SIM_MODEL",
            "NARRATE_SIM_PYTHON",
        ):
            mp.delenv(name, raising=False)
        mp.setenv("NARRATE_SCORER_LOCK", str(base / "scorer.lock"))
        mp.setenv("NARRATE_WHISPER_MODEL", str(base / "no-whisper-model.bin"))
        ws = Workspace(base)
        add_look(ws)
        job = campaign_job(ws)
        s, _, _ = run_job(ws, job, stages=["script", "voice"])
        add_look(ws, add_clip(ws, s, base))
        s, result, _ = run_job(ws, job, replace=True)
        assert result["ok"], result
        rerun.bind_campaign(s, CAMPAIGN_ID)
    return {"ws": ws, "job": job, "store": s, "result": result}


@pytest.fixture
def copied(settled, tmp_path):
    shutil.copytree(settled["ws"].base, tmp_path / "copy")
    ws = Workspace.__new__(Workspace)
    ws.base = tmp_path / "copy"
    ws.paths = {k: tmp_path / "copy" / Path(v).relative_to(settled["ws"].base) for k, v in settled["ws"].paths.items()}
    ws.reload()
    s = ws.store(settled["job"], replace=True)
    return ws, s


def evidence_for(s, **edit):
    job = s.read_job()
    value = {
        "kind": campaign.EVIDENCE_KIND,
        "schema_version": 1,
        "campaign": CAMPAIGN_ID,
        "record_sha256": RECORD_SHA256,
        "consent_record": GRANT_ID,
        "look": {"anchors": list(ANCHORS)},
        "job_sha256": accept.keys.digest(job),
        "video_sha256": accept.render_of(s, job)[0]["video_sha256"],
        "checks": dict.fromkeys(campaign.CHECKS, "passed"),
    }
    return value | edit


def codes(verdict):
    return sorted(row["code"] for row in verdict["refusals"])


# The bar: a Campaign job reads true only with every gate and the record id -------------------------------------------
def test_a_campaign_cut_with_every_gate_and_the_record_id_reads_public(copied):
    ws, s = copied
    verdict = campaign.verdict(s, ws.records, evidence_for(s))
    assert verdict["refusals"] == []
    assert verdict["public_upload_allowed"] is True
    assert verdict["manifest"] == {
        "synthetic": True,
        "campaign": CAMPAIGN_ID,
        "consent_record": GRANT_ID,
        "video_sha256": verdict["video_sha256"],
    }
    assert verdict["record_sha256"] == RECORD_SHA256
    assert verdict["resolution"] == "caller_checked"
    assert verdict["lifted"] == ["listening", "lip_sync"]
    assert json.loads((s.dir / campaign.FILE).read_text()) == verdict
    assert campaign.held_rows(s, verdict["job_sha256"], verdict["video_sha256"]) == []


def test_no_evidence_means_no_record_id_and_not_public(copied):
    ws, s = copied
    verdict = campaign.verdict(s, ws.records)
    assert verdict["public_upload_allowed"] is False
    assert codes(verdict) == ["campaign_evidence_missing"]
    assert verdict["manifest"] is None


@pytest.mark.parametrize("name", sorted(campaign.CHECKS))
def test_every_required_check_refuses_when_failed_or_absent(copied, name):
    ws, s = copied
    failed = evidence_for(s)
    failed["checks"][name] = "failed"
    verdict = campaign.verdict(s, ws.records, failed)
    want = campaign.STOP_CHECKS.get(name, "campaign_check_failed")
    assert verdict["public_upload_allowed"] is False
    assert codes(verdict) == [want]
    absent = evidence_for(s)
    del absent["checks"][name]
    verdict = campaign.verdict(s, ws.records, absent)
    assert verdict["public_upload_allowed"] is False
    assert codes(verdict) == ["campaign_check_missing"]


@pytest.mark.parametrize("state", ["pending", "unknown", "Passed", "", "true"])
def test_only_passed_passes(copied, state):
    ws, s = copied
    value = evidence_for(s)
    value["checks"]["confidentiality"] = state
    assert campaign.verdict(s, ws.records, value)["public_upload_allowed"] is False


@pytest.mark.parametrize(
    "edit, code",
    [
        ({"campaign": "campaign-other"}, "campaign_record_mismatch"),
        ({"job_sha256": "a" * 64}, "campaign_evidence_stale"),
        ({"video_sha256": "b" * 64}, "campaign_evidence_stale"),
        ({"consent_record": "consent-unknown"}, "campaign_consent_missing"),
        ({"look": {"anchors": ["c" * 64]}}, "campaign_look_mismatch"),
        ({"look": {"anchors": ANCHORS[:1]}}, "campaign_look_mismatch"),
    ],
)
def test_evidence_of_another_record_cut_or_look_refuses(copied, edit, code):
    ws, s = copied
    verdict = campaign.verdict(s, ws.records, evidence_for(s, **edit))
    assert verdict["public_upload_allowed"] is False
    assert codes(verdict) == [code]


@pytest.mark.parametrize(
    "edit",
    [
        lambda v: v.update(extra=1),
        lambda v: v.pop("record_sha256"),
        lambda v: v.update(kind="other"),
        lambda v: v.update(record_sha256="short"),
        lambda v: v.update(consent_record=""),
        lambda v: v.update(campaign="Not An Id"),
        lambda v: v.update(look={"id": LOOK_ID, "anchors": list(ANCHORS)}),
        lambda v: v["checks"].update(not_a_check="passed"),
    ],
)
def test_a_misshapen_evidence_file_refuses(copied, edit):
    ws, s = copied
    value = evidence_for(s)
    edit(value)
    with pytest.raises(JobError) as exc:
        campaign.verdict(s, ws.records, value)
    assert exc.value.code == "campaign_evidence_invalid"
    assert not (s.dir / campaign.FILE).exists()


def test_an_unbound_root_refuses(copied):
    ws, s = copied
    ledger = rerun.read(s)
    ledger.pop("campaign")
    (s.dir / rerun.LEDGER).write_text(json.dumps(ledger))
    verdict = campaign.verdict(s, ws.records, evidence_for(s))
    assert verdict["public_upload_allowed"] is False
    assert "campaign_unbound" in codes(verdict)


def test_a_withdrawn_consent_stops_every_later_cut(copied):
    ws, s = copied
    value = evidence_for(s)
    put_rows(ws, "consents.json", [grant_row(revokedAt="2026-11-08")])
    verdict = campaign.verdict(s, ws.records, value)
    assert verdict["public_upload_allowed"] is False
    assert "campaign_consent_revoked" in codes(verdict)


def test_a_likeness_only_consent_is_no_campaign_grant(copied):
    ws, s = copied
    value = evidence_for(s)
    put_rows(ws, "consents.json", [grant_row(scopes=["Likeness"])])
    verdict = campaign.verdict(s, ws.records, value)
    assert codes(verdict) == ["campaign_consent_missing"]


def test_a_parked_root_and_a_cut_sent_back_refuse(copied):
    ws, s = copied
    value = evidence_for(s)
    ledger = rerun.read(s)
    held = dict(ledger)
    video = value["video_sha256"]
    ledger["fixes"] = [
        {
            "round": 1,
            "decision": None,
            "resolution": rerun.MACHINE,
            "campaign": CAMPAIGN_ID,
            "findings_sha256": "d" * 64,
            "codes": {},
            "reach": [],
            "seq": 0,
            "job_sha256": value["job_sha256"],
            "video_sha256": video,
            "deliver_check": None,
            "recorded_utc": "2026-11-07T00:00:00Z",
        }
    ]
    (s.dir / rerun.LEDGER).write_text(json.dumps(ledger))
    verdict = campaign.verdict(s, ws.records, value)
    assert "campaign_cut_sent_back" in codes(verdict) and verdict["public_upload_allowed"] is False
    held["parked"] = {
        "round": 3,
        "findings_sha256": "d" * 64,
        "codes": {},
        "video_sha256": video,
        "job_sha256": value["job_sha256"],
        "recorded_utc": "2026-11-07T00:00:00Z",
    }
    (s.dir / rerun.LEDGER).write_text(json.dumps(held))
    verdict = campaign.verdict(s, ws.records, value)
    assert "campaign_parked" in codes(verdict) and verdict["public_upload_allowed"] is False


def perfect_report():
    return {
        "gates": {g: "passed" for g in deliver.MACHINE_GATES}
        | {"listening": "not_applicable", "lip_sync": "not_applicable", "visible_text": "passed"},
        "avatar_box": {"unchecked": [], "exempt": [], "checked": ["p1"], "held": [], "findings": [], "state": "passed"},
        "labels": {"synthetic": True},
        "edition": {"verdict": "Admitted"},
    }


PERFECT_GATE = {"machine_gates_passed": True, "upload_gates_closed": True, "operator_states_open": []}


def job_shape(**edit):
    job = init_job("nv-shape", fixture.NARRATE_JOB, "e" * 64, edition="Campaign", avatar=False)
    return copy.deepcopy(job) | edit


def test_a_perfect_report_leaves_nothing_open():
    assert campaign.cut_refusals(job_shape(), perfect_report(), PERFECT_GATE) == []


@pytest.mark.parametrize("gate", deliver.MACHINE_GATES)
@pytest.mark.parametrize("state", ["failed", "pending_operator", None])
def test_any_machine_gate_short_of_passed_refuses(gate, state):
    report = perfect_report()
    report["gates"][gate] = state
    assert [r["gate"] for r in campaign.cut_refusals(job_shape(), report, PERFECT_GATE)] == [gate]


@pytest.mark.parametrize("gate", deliver.MACHINE_GATES)
def test_only_a_gate_with_nothing_to_read_may_not_apply(gate):
    report = perfect_report()
    report["gates"][gate] = "not_applicable"
    found = campaign.cut_refusals(job_shape(), report, PERFECT_GATE)
    assert bool(found) == (gate in campaign.MUST_PASS)


@pytest.mark.parametrize("where", ["unchecked", "exempt"])
def test_a_page_no_frame_gate_read_refuses_and_gives_a_row(where):
    """TIN-7788 item 2.6: passed speaks only for the checked pages, and no person reads the others on this path."""
    report = perfect_report()
    report["avatar_box"][where] = ["p2"]
    found = campaign.cut_refusals(job_shape(), report, PERFECT_GATE)
    assert [(r["code"], r["page"]) for r in found] == [("frame_unread", "p2")]
    rows = deliver.campaign_rows(report, job_shape())
    assert [(r["code"], r["page"], r["stage"], r["blocking"]) for r in rows] == [("frame_unread", "p2", "base", True)]


def test_a_shown_asset_no_guard_read_refuses():
    report = perfect_report()
    report["gates"]["visible_text"] = "not_applicable"
    assert campaign.cut_refusals(job_shape(), report, PERFECT_GATE) == []  # a plain card shows no asset
    shown = job_shape(base={"still": {"sha256": "f" * 64}})
    assert [r["code"] for r in campaign.cut_refusals(shown, report, PERFECT_GATE)] == ["visible_text_unread"]
    report["gates"]["visible_text"] = "pending_operator"
    gate = PERFECT_GATE | {"operator_states_open": ["visible_text"]}
    assert [r["code"] for r in campaign.cut_refusals(job_shape(), report, gate)] == ["visible_text_unread"]


@pytest.mark.parametrize("state", ["bed_licence_pdf", "bed_content_id", "vrm_badge_decision"])
def test_every_other_operator_state_stays_open(state):
    gate = PERFECT_GATE | {"operator_states_open": [state]}
    found = campaign.cut_refusals(job_shape(), perfect_report(), gate)
    assert [(r["code"], r["gate"]) for r in found] == [("campaign_operator_state_open", state)]


def test_upload_off_and_open_upload_gates_refuse():
    off = job_shape()
    off["delivery"] = off["delivery"] | {"upload": False}
    assert [r["code"] for r in campaign.cut_refusals(off, perfect_report(), PERFECT_GATE)] == ["campaign_upload_off"]
    gate = PERFECT_GATE | {"upload_gates_closed": False}
    assert [r["code"] for r in campaign.cut_refusals(job_shape(), perfect_report(), gate)] == [
        "campaign_upload_gates_open"
    ]


def test_a_cut_not_labelled_synthetic_refuses():
    report = perfect_report()
    report["labels"] = {"synthetic": False}
    assert [r["code"] for r in campaign.cut_refusals(job_shape(), report, PERFECT_GATE)] == ["campaign_not_synthetic"]


def test_a_campaign_deliver_check_lifts_listening_and_says_not_public(copied):
    ws, s = copied
    measured = s.manifest("deliver_check")["measurements"]
    assert measured["gates"]["listening"] == "not_applicable"
    assert measured["gates"]["lip_sync"] == "not_applicable"
    gate = measured["delivery_gate"]
    assert gate["public_upload_allowed"] is False
    assert gate["upload_gates_closed"] is True
    assert gate["lifted"] == ["listening", "lip_sync"]
    assert "campaign.py" in gate["note"]


@pytest.mark.parametrize("gate", ["listening", "lip_sync"])
def test_accept_has_nothing_to_close_on_a_campaign_cut(copied, gate):
    ws, s = copied
    video = accept.current_video(s)
    with pytest.raises(JobError) as exc:
        accept.accept(s, gate, DECISION, video)
    assert exc.value.code == "gate_not_applicable"


# The bar: public stays false for client and internal, and their gates stay -------------------------------------------
@pytest.mark.parametrize("edition", OTHER_EDITIONS)
def test_public_stays_false_on_every_other_edition_with_every_check_passed(copied, edition):
    ws, s = copied
    value = evidence_for(s)
    job = s.read_job() | {"edition": edition}
    (s.dir / "job.json").write_text(json.dumps(job))
    verdict = campaign.verdict(s, ws.records, value)
    assert verdict["public_upload_allowed"] is False
    assert codes(verdict) == ["campaign_edition_required"]
    assert verdict["manifest"] is None
    assert verdict["refusals"][0]["code"] == "campaign_edition_required"


@pytest.mark.parametrize("edition", OTHER_EDITIONS)
def test_another_edition_writes_no_verdict_and_gives_no_row(copied, edition):
    ws, s = copied
    job = s.read_job() | {"edition": edition}
    (s.dir / "job.json").write_text(json.dumps(job))
    campaign.verdict(s, ws.records)
    assert not (s.dir / campaign.FILE).exists()
    assert deliver.campaign_rows({"avatar_box": {"unchecked": ["p"], "exempt": []}, "gates": {}}, job) == []


@pytest.mark.parametrize("edition", OTHER_EDITIONS)
def test_delivery_gate_keeps_public_false_with_listening_open(edition):
    job = init_job("nv-other", fixture.NARRATE_JOB, "e" * 64, edition="Internal", avatar=False) | {"edition": edition}
    job["delivery"] = job["delivery"] | {"upload": True}
    machine = dict.fromkeys(deliver.MACHINE_GATES, "passed")
    gate = deliver.delivery_gate(job, None, machine, {"listening": "pending_operator", "lip_sync": "pending_operator"})
    assert gate["public_upload_allowed"] is False
    assert gate["operator_states_open"] == ["lip_sync", "listening"]
    assert "lifted" not in gate


def test_a_campaign_gate_is_not_public_at_the_stage_even_with_every_state_closed():
    job = job_shape()
    machine = dict.fromkeys(deliver.MACHINE_GATES, "passed")
    gate = deliver.delivery_gate(job, None, machine, {"listening": "not_applicable", "lip_sync": "not_applicable"})
    assert gate["upload_gates_closed"] is True and gate["public_upload_allowed"] is False


@pytest.mark.parametrize("edition", OTHER_EDITIONS)
def test_deliver_check_keeps_listening_and_lip_sync_open_on_every_other_edition(edition):
    job = {"edition": edition}
    assert deliver.listen_gates(job, ["overlay"]) == {"listening": "pending_operator", "lip_sync": "pending_operator"}
    assert deliver.listen_gates(job, []) == {"listening": "pending_operator", "lip_sync": "not_applicable"}
    lifted = {"listening": "not_applicable", "lip_sync": "not_applicable"}
    assert deliver.listen_gates({"edition": "Campaign"}, ["overlay"]) == lifted


@pytest.mark.parametrize("edition", OTHER_EDITIONS)
def test_listening_and_lip_sync_stay_required_for_every_other_edition(edition):
    job = init_job("nv-other", fixture.NARRATE_JOB, "e" * 64, avatar=True, persona=PERSONA) | {"edition": edition}
    gates = {p["gate"] for p in admit.pending_operator(job, None)}
    assert {"listening_acceptance", "lip_sync_acceptance"} <= gates
    assert "listening_acceptance" not in {
        p["gate"] for p in admit.pending_operator(job | {"edition": "Campaign"}, None)
    }
    assert "lip_sync_acceptance" not in {p["gate"] for p in admit.pending_operator(job | {"edition": "Campaign"}, None)}


def test_an_internal_job_keeps_its_report_and_accept(tmp_path, ffmpeg):
    """A job bound to a campaign but not of the Campaign edition still needs its decision, and stays not public."""
    ws = Workspace(tmp_path)
    job = init_job("nv-internal", fixture.NARRATE_JOB, sha(ws.paths["script"]), avatar=False)
    s, result, _ = run_job(ws, job)
    assert result["ok"], result
    measured = s.manifest("deliver_check")["measurements"]
    assert measured["gates"]["listening"] == "pending_operator"
    assert measured["delivery_gate"]["public_upload_allowed"] is False
    assert "lifted" not in measured["delivery_gate"]
    rerun.bind_campaign(s, CAMPAIGN_ID)
    verdict = campaign.verdict(s, ws.records)
    assert verdict["public_upload_allowed"] is False and codes(verdict) == ["campaign_edition_required"]
    assert accept.accept(s, "listening", DECISION, accept.current_video(s))["recorded"] is True
    assert campaign.verdict(s, ws.records)["public_upload_allowed"] is False
    assert render_stage.job_findings(s)["blocking"] == 0


def test_an_internal_cut_cannot_read_public_by_a_new_edition_in_job_json(tmp_path, ffmpeg):
    """deliver_check keys on the job's digest, so an edition edited after the render has no current cut to read."""
    ws = Workspace(tmp_path)
    add_look(ws)
    job = init_job("nv-internal", fixture.NARRATE_JOB, sha(ws.paths["script"]), avatar=False)
    s, result, _ = run_job(ws, job)
    assert result["ok"], result
    rerun.bind_campaign(s, CAMPAIGN_ID)
    value = evidence_for(s)
    (s.dir / "job.json").write_text(json.dumps(job | {"edition": "Campaign"}))
    verdict = campaign.verdict(s, ws.records, value)
    assert verdict["public_upload_allowed"] is False
    assert "deliver_check_stale" in codes(verdict)


# Admit ----------------------------------------------------------------------------------------------------------------
def refusal_codes(ws, job):
    return [r["code"] for r in admit.admit(job, ws.records, "resolved")["refusals"]]


def test_a_campaign_overlay_is_a_look_and_no_other_external(tmp_path):
    ws = Workspace(tmp_path)
    add_look(ws)
    assert refusal_codes(ws, campaign_job(ws)) == []
    kitpip_job = campaign_job(ws)
    kitpip_job["avatar"]["external"] = "kitpip"
    assert refusal_codes(ws, kitpip_job) == ["campaign_look_required"]
    vrm_job = campaign_job(ws)
    vrm_job["avatar"]["external"] = "vrm"
    assert "campaign_look_required" in refusal_codes(ws, vrm_job)
    assert "vrm_edition_unruled" in refusal_codes(ws, vrm_job)


@pytest.mark.parametrize("edition", OTHER_EDITIONS)
def test_a_look_is_ruled_only_for_the_campaign_edition(tmp_path, edition):
    ws = Workspace(tmp_path)
    add_look(ws)
    job = campaign_job(ws) | {"edition": edition}
    assert "look_edition_unruled" in refusal_codes(ws, job)


def test_a_campaign_voice_under_a_client_consent_refuses(tmp_path):
    ws = Workspace(tmp_path)
    add_look(ws)
    job = campaign_job(ws)
    assert "campaign_client_consent" not in refusal_codes(ws, job)
    voice = ws.records["voices"][ws.records["jobs"][fixture.NARRATE_JOB]["voice"]]
    consent = dict(ws.records["consents"][voice["consentId"]])
    put_rows(ws, "consents.json", [consent | {"scopes": [*consent["scopes"], "ClientDisclosed"]}])
    assert "campaign_client_consent" in refusal_codes(ws, job)


@pytest.mark.parametrize(
    "edit, code",
    [
        ({"kind": "vrm"}, "look_missing"),
        ({"anchors": []}, "look_invalid"),
        ({"anchors": ["short"]}, "look_invalid"),
        ({"anchors": ["a" * 64, "a" * 64]}, "look_invalid"),
        ({"renderer": {"name": "x"}}, "look_invalid"),
        ({"clips": {"short": {"sha256": "a" * 64, "bytes": 1}}}, "look_invalid"),
        ({"likenessConsent": {"id": "nobody", "ruling": "SP-R13"}}, "look_consent_missing"),
        ({"likenessConsent": {"id": GRANT_ID, "ruling": "other"}}, "look_consent_missing"),
    ],
)
def test_each_look_gate_refuses(tmp_path, edit, code):
    ws = Workspace(tmp_path)
    add_look(ws, **edit)
    assert code in refusal_codes(ws, campaign_job(ws))


def test_a_revoked_likeness_and_a_wrong_digest_refuse(tmp_path):
    ws = Workspace(tmp_path)
    add_look(ws)
    job = campaign_job(ws)
    job["avatar"]["rigRevisionSha256"] = "a" * 64
    assert refusal_codes(ws, job) == ["look_digest_mismatch"]
    job["avatar"]["rigRevisionSha256"] = look.anchors_digest(look_record())
    assert refusal_codes(ws, job) == []
    put_rows(ws, "consents.json", [grant_row(revokedAt="2026-11-08")])
    assert refusal_codes(ws, job) == ["look_consent_revoked"]


def test_a_look_resolves_with_no_pin_and_a_job_with_no_avatar_resolves_nothing(tmp_path):
    ws = Workspace(tmp_path)
    job = init_job("nv-plain", fixture.NARRATE_JOB, sha(ws.paths["script"]), avatar=False)
    assert graph.avatar_resolution(job, ws.ctx()) is None
    assert graph.avatar_resolution(campaign_job(ws), {}) == look.RESOLUTION


# The look route ------------------------------------------------------------------------------------------------------
def test_the_look_reaches_the_cut_by_digest_with_its_labels(copied):
    ws, s = copied
    record = ws.records["avatars"][LOOK_ID]
    overlay = s.dir / s.entry("avatar/seg-1")["dir"] / "overlay"
    seen, problems = avatar_manifest.verify_dir(overlay, "look")
    assert problems == []
    clip = record["clips"][voice_take(s)]
    assert sha(overlay / "overlay.mov") == clip["sha256"]
    assert seen["renderer_kind"] == "look" and seen["frames_identity"] == "bit_exact"
    assert seen["rig"] == {"id": LOOK_ID, "sha256": look.anchors_digest(record)}
    assert seen["look"]["anchors"] == sorted(ANCHORS)
    manifest = s.manifest("avatar/seg-1")
    assert GRANT_ID in manifest["labels"]["consent_ids"] and manifest["synthetic"] is True
    assert s.manifest("compose")["measurements"]["overlays"], "compose drew no overlay"
    check = json.loads((s.dir / s.entry("avatar_check/seg-1")["dir"] / "check.json").read_text())
    assert check["likeness_consent_id"] == GRANT_ID and check["frames_sha256"] == clip["sha256"]


def test_a_new_voice_take_has_no_clip_until_its_record_names_one(tmp_path, ffmpeg):
    ws = Workspace(tmp_path)
    add_look(ws, {"a" * 64: {"sha256": "b" * 64, "bytes": 1}})
    s, result, _ = run_job(ws, campaign_job(ws))
    assert result["ok"] is False
    assert s.current()["refusals"]["avatar/seg-1"]["code"] == "look_clip_missing"


@pytest.mark.parametrize(
    "make, why",
    [
        ({"size": RENDER_SIZE * 2}, "is not"),
        ({"rate": "25/1"}, "rate"),
        ({"pix_fmt": "yuv422p10le"}, "alpha"),
    ],
)
def test_a_clip_that_does_not_fit_the_take_refuses(tmp_path, ffmpeg, make, why):
    ws = Workspace(tmp_path)
    add_look(ws)
    job = campaign_job(ws)
    s, _, _ = run_job(ws, job, stages=["script", "voice"])
    add_look(ws, add_clip(ws, s, tmp_path, **make))
    s, result, _ = run_job(ws, job, replace=True)
    refusal = s.current()["refusals"]["avatar/seg-1"]
    assert result["ok"] is False and refusal["code"] == "look_clip_invalid" and why in refusal["detail"]


def test_a_clip_with_the_wrong_frame_count_refuses():
    probe = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "prores",
                "pix_fmt": "yuva444p10le",
                "width": 8,
                "height": 8,
                "avg_frame_rate": "30/1",
                "nb_frames": "9",
            }
        ]
    }
    assert look.clip_problems(probe, 8, {"num": 30, "den": 1}, 9) == []
    assert "frames" in look.clip_problems(probe, 8, {"num": 30, "den": 1}, 10)[0]


def test_the_stored_clip_must_be_its_records(tmp_path, ffmpeg):
    ws = Workspace(tmp_path)
    add_look(ws)
    job = campaign_job(ws)
    s, _, _ = run_job(ws, job, stages=["script", "voice"])
    clips = add_clip(ws, s, tmp_path)
    clips[voice_take(s)]["bytes"] += 1
    add_look(ws, clips)
    s, result, _ = run_job(ws, job, replace=True)
    assert result["ok"] is False


def good_look_manifest():
    digest = "a" * 64
    return {
        "schema": avatar_manifest.SCHEMA_V1,
        "kind": "avatar_overlay",
        "renderer": {"kind": "look", "name": "n", "version": "1"},
        "synthetic": True,
        "consent_ids": ["c"],
        "voice_ids": ["v"],
        "rig": {"id": LOOK_ID, "sha256": digest},
        "rate": {"num": 30, "den": 1},
        "size": {"w": 8, "h": 8},
        "frames": 3,
        "frames_sha256": digest,
        "frames_identity": "bit_exact",
        "outputs": [],
        "timeline": {"mapping": avatar_manifest.MAPPING, "no_time_stretch": False, "clock": avatar_manifest.CLOCK},
        "look": {"id": LOOK_ID, "anchors": [digest], "likeness_consent_id": "c", "clip_sha256": digest},
    }


@pytest.mark.parametrize(
    "edit",
    [
        lambda m: m["look"].update(id="other"),
        lambda m: m["look"].update(anchors=[]),
        lambda m: m["look"].update(likeness_consent_id=""),
        lambda m: m["look"].update(clip_sha256="b" * 64),
        lambda m: m.update(frames_identity="per_host"),
        lambda m: m.update(show_badge=True),
        lambda m: m.pop("look"),
    ],
)
def test_a_look_manifest_missing_a_record_refuses(edit):
    assert avatar_manifest.view(good_look_manifest(), "look")["renderer_kind"] == "look"
    manifest = good_look_manifest()
    edit(manifest)
    with pytest.raises(JobError) as exc:
        avatar_manifest.view(manifest, "look")
    assert exc.value.code == "avatar_manifest_invalid"


@pytest.fixture
def bundle_ws(tmp_path):
    paths = fixture.write(tmp_path / "ws")
    paths["bundle"] = fixture.write_bundle(tmp_path / "bundles")
    return paths


def test_intake_writes_a_campaign_job_only_when_a_look_is_named(bundle_ws, tmp_path):
    records = bundle_ws["records"]
    (records / "avatars.json").write_text(json.dumps([look_record()]))
    held = json.loads((records / "consents.json").read_text())
    (records / "consents.json").write_text(json.dumps([*held, grant_row()]))
    plain = intake(bundle_ws, tmp_path / "plain", persona=PERSONA)
    assert plain["edition"] == "Internal"
    held = json.loads((tmp_path / "plain" / "narrated-video.json").read_text())
    assert held["avatar"]["external"] == "kitpip" and held["delivery"]["upload"] is False
    named = intake(bundle_ws, tmp_path / "named", persona=PERSONA, look=LOOK_ID)
    assert named["edition"] == "Campaign"
    written = json.loads((tmp_path / "named" / "narrated-video.json").read_text())
    assert written["avatar"]["external"] == "look" and written["avatar"]["rig"] == LOOK_ID
    assert written["delivery"]["upload"] is True


# The manifest the checks read ----------------------------------------------------------------------------------------
def test_the_manifest_the_checks_read_is_the_verdicts_on_this_cut(copied, capsys):
    ws, s = copied
    printed = campaign.manifest(s, CAMPAIGN_ID, GRANT_ID)
    verdict = campaign.verdict(s, ws.records, evidence_for(s))
    assert {k: printed[k] for k in verdict["manifest"]} == verdict["manifest"]
    assert printed["job_sha256"] == verdict["job_sha256"]
    root = ["--root", str(ws.base / "narrated")]
    assert (
        cli.main(["campaign-manifest", s.job_id, "--campaign", CAMPAIGN_ID, "--consent-record", GRANT_ID, *root]) == 0
    )
    assert json.loads(capsys.readouterr().out)["video_sha256"] == verdict["video_sha256"]


def test_the_manifest_refuses_another_campaign_an_unbound_root_and_another_edition(copied):
    ws, s = copied
    with pytest.raises(JobError) as exc:
        campaign.manifest(s, "campaign-other", GRANT_ID)
    assert exc.value.code == "campaign_record_mismatch"
    with pytest.raises(JobError) as exc:
        campaign.manifest(s, CAMPAIGN_ID, "")
    assert exc.value.code == "campaign_consent_missing"
    ledger = rerun.read(s)
    ledger.pop("campaign")
    (s.dir / rerun.LEDGER).write_text(json.dumps(ledger))
    with pytest.raises(JobError) as exc:
        campaign.manifest(s, CAMPAIGN_ID, GRANT_ID)
    assert exc.value.code == "campaign_unbound"
    (s.dir / "job.json").write_text(json.dumps(s.read_job() | {"edition": "Internal"}))
    with pytest.raises(JobError) as exc:
        campaign.manifest(s, CAMPAIGN_ID, GRANT_ID)
    assert exc.value.code == "campaign_edition_required"


# The loop -------------------------------------------------------------------------------------------------------------
def test_a_failed_check_routes_through_findings_to_a_round_and_a_new_cut_clears_it(copied):
    ws, s = copied
    value = evidence_for(s)
    value["checks"]["ai_disclosure"] = "failed"
    assert campaign.verdict(s, ws.records, value)["public_upload_allowed"] is False
    report = render_stage.job_findings(s)
    rows = [r for r in report["findings"] if r["code"] == "campaign_check_failed"]
    assert [(r["gate"], r["stage"], r["blocking"]) for r in rows] == [("ai_disclosure", "compose", True)]
    shown = rerun.machine_round(s, report, report["video_sha256"])
    assert shown["result"] == "round" and shown["campaign"] == CAMPAIGN_ID
    assert not any(stage.startswith("voice") for stage in shown["reach"])
    assert campaign.held_rows(s, value["job_sha256"], "f" * 64) == []
    assert campaign.held_rows(s, "f" * 64, value["video_sha256"]) == []


@pytest.mark.parametrize("code", ["campaign_check_failed", "frame_unread"])
def test_a_round_on_a_verdict_row_names_the_cut_it_read(code):
    """Only a composed cut can show these, so a round on one binds that cut and the same cut cannot answer it."""
    assert findings.reads_cut(findings.finding(code, gate="campaign"))


@pytest.mark.parametrize(
    "plant, code",
    [
        ({"brand_public_gate": "failed"}, "campaign_brand_gate_closed"),
        ({"claims_allowlist": None}, "campaign_check_missing"),
    ],
)
def test_a_fault_no_job_edit_repairs_gives_a_stop_row(copied, plant, code):
    ws, s = copied
    value = evidence_for(s)
    for name, state in plant.items():
        if state is None:
            del value["checks"][name]
        else:
            value["checks"][name] = state
    campaign.verdict(s, ws.records, value)
    rows = [r for r in render_stage.job_findings(s)["findings"] if r["code"] == code]
    assert len(rows) == 1 and rows[0]["stage"] is None


def test_a_held_verdict_holds_no_path_or_text(copied):
    ws, s = copied
    value = evidence_for(s)
    value["checks"]["claims_allowlist"] = "failed"
    campaign.verdict(s, ws.records, value)
    held = (s.dir / campaign.FILE).read_text()
    assert str(s.dir) not in held and "narration" not in held and "/" not in held.replace("nv_campaign", "")


# The command and the render stage -------------------------------------------------------------------------------------
def test_the_command_prints_the_verdict_and_refuses_bad_evidence(copied, tmp_path, capsys):
    ws, s = copied
    base = ["--root", str(ws.base / "narrated"), "--records", str(ws.paths["records"])]
    good = tmp_path / "evidence.json"
    good.write_text(json.dumps(evidence_for(s)))
    assert cli.main(["campaign-verdict", s.job_id, "--evidence", str(good), *base]) == 0
    assert json.loads(capsys.readouterr().out)["public_upload_allowed"] is True
    assert cli.main(["campaign-verdict", s.job_id, *base]) == 0
    assert json.loads(capsys.readouterr().out)["public_upload_allowed"] is False
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    assert cli.main(["campaign-verdict", s.job_id, "--evidence", str(bad), *base]) == 1
    assert "campaign_evidence_invalid" in capsys.readouterr().err


def test_the_render_stage_admits_campaign_and_no_client_edition():
    assert "Campaign" in render_stage.EDITIONS_V1
    assert not set(CLIENT_EDITIONS) & set(render_stage.EDITIONS_V1)


def test_a_campaign_cut_plans_fresh_and_reads_no_open_gate(copied, capsys):
    ws, s = copied
    root = ["--root", str(ws.base / "narrated")]
    records = ["--records", str(ws.paths["records"]), "--store", str(ws.paths["store"])]
    assert cli.main(["plan", s.job_id, "--record", "--json", *root, *records]) == 0
    capsys.readouterr()
    assert cli.main(["status", s.job_id, "--json", *root, *records]) == 0
    capsys.readouterr()
    assert cli.main(["cut", s.job_id, "--json", *root]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["pending_operator"] == [] and shown["internal_review_allowed"] is True
