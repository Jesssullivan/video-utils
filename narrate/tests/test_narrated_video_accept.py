"""Operator acceptance by Softproxy decision id (docs/spec/NARRATED_VIDEO.md, "Operator acceptance", Linear TIN-7788).

Every stage runs through a fake runner that writes one small output per node, a synthetic video.mp4 for compose and a
deliver_check gate table shaped like narrate/video/deliver.py's, so no FFmpeg runs. The decision ids are made-up ULIDs
in Softproxy's form; none names a real decision.
"""

import json
import subprocess
import sys

import pytest
from test_narrated_video_graph import FPS, example, new_store, plain_ctx, records, stub_ctx

from narrate.config import ROOT
from narrate.video import accept, cli, graph, keys
from narrate.video.job import JobError

GO = "sp:dec:01JD00000000000000000000F1"
GO_2 = "sp:dec:01JD00000000000000000000F2"
GO_3 = "sp:dec:01JD0000000000000000000ZZZ"
NOW = "2026-10-30T12:00:00Z"


def gates_for(job):
    overlay = job["avatar"] is not None and any(s["avatar"] for s in job["segments"])
    return {
        "profile": "passed",
        "loudness": "passed",
        "flash": "not_applicable",
        "captions": "passed",
        "listening": "pending_operator",
        "lip_sync": "pending_operator" if overlay else "not_applicable",
        "bed_licence_pdf": "not_applicable",
        "bed_content_id": "not_applicable",
    }


def fields_for(node_id, partial, key, job):
    if node_id == "base":
        return {"measurements": {"fps": FPS}}
    if node_id == "compose":
        (partial / "video.mp4").write_bytes(b"synthetic cut " + key.encode())
    if node_id == "deliver_check":
        return {"measurements": {"gates": gates_for(job)}}
    return {}


def settle(job, recs, s, ctx):
    for _ in range(30):
        g = graph.plan(job, recs, s, ctx)
        if not g["runnable"]:
            return g
        for node_id in g["runnable"]:
            document = g["_documents"][node_id]
            key = keys.stage_key(document)
            partial = s.begin(node_id, key)
            (partial / "out.json").write_text(json.dumps({"node": node_id, "key": key}))
            s.commit(node_id, key, document, fields_for(node_id, partial, key, job))
    raise AssertionError("the graph did not settle")


@pytest.fixture
def avatar_job(tmp_path):
    job, recs = example("nv-fixture-avatar"), records()
    s = new_store(tmp_path, job)
    settle(job, recs, s, stub_ctx())
    s.write_graph(graph.public(graph.plan(job, recs, s, stub_ctx())))
    return job, recs, s


@pytest.fixture
def card_job(tmp_path):
    job, recs = example("nv-fixture-card"), records()
    s = new_store(tmp_path, job)
    settle(job, recs, s, plain_ctx())
    return job, recs, s


def clock():
    return NOW


def video_of(s):
    return s.manifest("compose")["outputs"]["video.mp4"]


# The decision id ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("value", [GO, "sp:dec:7ZZZZZZZZZZZZZZZZZZZZZZZZZ", "sp:dec:00000000000000000000000000"])
def test_a_softproxy_decision_id_is_taken(value):
    assert accept.check_decision(value) == value


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (None, "decision_missing"),
        ("", "decision_missing"),
        ("   ", "decision_missing"),
        ("GO", "decision_free_text"),
        ("GO demo nv-fixture-avatar pkt-1", "decision_free_text"),
        ("yes", "decision_free_text"),
        ("lgtm", "decision_free_text"),
        ("approved by the operator", "decision_free_text"),
        ("sp:prp:01JD00000000000000000000F1", "decision_free_text"),  # a proposal id is not a decision
        ("SP:DEC:01JD00000000000000000000F1", "decision_free_text"),
        (" " + GO, "decision_free_text"),
        ("sp:dec:", "decision_invalid"),
        ("sp:dec:1", "decision_invalid"),
        ("sp:dec:01jd00000000000000000000f1", "decision_invalid"),  # lower case
        ("sp:dec:01JD00000000000000000000F", "decision_invalid"),  # 25 characters
        ("sp:dec:01JD00000000000000000000F11", "decision_invalid"),  # 27 characters
        ("sp:dec:01JD0000000000000000000IL1", "decision_invalid"),  # I and L are not Crockford base32
        ("sp:dec:01JD0000000000000000000OU1", "decision_invalid"),  # nor O and U
        ("sp:dec:81JD00000000000000000000F1", "decision_invalid"),  # past 48 bits of time
        (GO + "\n", "decision_invalid"),
        (GO + " lgtm", "decision_invalid"),
        ("sp:dec:01JD00000000000000000000F1:GO", "decision_invalid"),
    ],
)
def test_free_text_an_empty_value_and_a_malformed_id_refuse(value, code):
    with pytest.raises(JobError) as caught:
        accept.check_decision(value)
    assert caught.value.code == code
    if value and len(value.strip()) > len("sp:dec:<ulid>"):
        assert value.strip() not in caught.value.detail  # a refusal never echoes the value


@pytest.mark.parametrize(
    ("gate", "code"),
    [
        ("profile", "gate_automated"),
        ("loudness", "gate_automated"),
        ("flash", "gate_automated"),
        ("captions", "gate_automated"),
        ("bed_licence_pdf", "gate_record_bound"),
        ("bed_content_id", "gate_record_bound"),
        ("vrm_badge_decision", "vrm_badge_undecided"),
        ("listening_acceptance", "gate_unknown"),
        ("upload", "gate_unknown"),
        ("", "gate_unknown"),
        (None, "gate_unknown"),
    ],
)
def test_a_machine_gate_a_record_gate_an_unruled_gate_and_an_unknown_gate_refuse(avatar_job, gate, code):
    _, _, s = avatar_job
    with pytest.raises(JobError) as caught:
        accept.accept(s, gate, GO, now=clock)
    assert caught.value.code == code
    assert not (s.dir / accept.ACCEPTANCE).exists()


def test_every_deliver_check_gate_is_classified():
    """A gate deliver_check reports must be acceptable, unruled, automated or record bound; nothing else."""
    reported = set(gates_for(example("nv-fixture-avatar"))) | {"vrm_badge_decision"}
    assert reported == set(accept.GATES)


# Recording ---------------------------------------------------------------------------------------------------
def test_listening_and_lip_sync_are_recorded_with_the_decision_time_gate_and_render(avatar_job):
    job, _, s = avatar_job
    first = accept.accept(s, "listening", GO, now=clock)
    assert first["recorded"] and first["operator_states_open"] == ["lip_sync"]
    second = accept.accept(s, "lip_sync", GO, video_sha256=video_of(s), now=clock)
    assert second["recorded"] and second["operator_states_open"] == []
    record = json.loads((s.dir / accept.ACCEPTANCE).read_text())
    assert record["kind"] == "nv_acceptance" and record["job_id"] == job["id"]
    entry = s.entry("deliver_check")
    for row, gate in zip(record["acceptances"], ("listening", "lip_sync"), strict=True):
        assert row == {
            "gate": gate,
            "decision": GO,
            "accepted_utc": NOW,
            "job_sha256": keys.digest(job),
            "deliver_check": {"stage_key": entry["key"], "content_sha256": entry["content_sha256"]},
            "video_sha256": video_of(s),
        }


def test_job_json_and_every_stage_stay_as_they_were(avatar_job):
    job, _, s = avatar_job
    before = s.job_file.read_bytes(), json.dumps(s.current(), sort_keys=True)
    accept.accept(s, "listening", GO, now=clock)
    assert (s.job_file.read_bytes(), json.dumps(s.current(), sort_keys=True)) == before
    assert s.read_job() == job and not any(s.verify().values())


def test_the_same_gate_and_decision_again_is_a_no_op(avatar_job):
    _, _, s = avatar_job
    accept.accept(s, "listening", GO, now=clock)
    before = (s.dir / accept.ACCEPTANCE).read_bytes()
    again = accept.accept(s, "listening", GO, now=lambda: "2026-10-31T00:00:00Z")
    assert not again["recorded"] and again["accepted_utc"] == NOW
    assert (s.dir / accept.ACCEPTANCE).read_bytes() == before


def test_a_second_decision_for_an_accepted_gate_refuses(avatar_job):
    _, _, s = avatar_job
    accept.accept(s, "listening", GO, now=clock)
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO_2, now=clock)
    assert caught.value.code == "gate_already_accepted"
    assert len(accept.read(s)["acceptances"]) == 1


def test_lip_sync_without_an_overlay_refuses(card_job):
    _, _, s = card_job
    with pytest.raises(JobError) as caught:
        accept.accept(s, "lip_sync", GO, now=clock)
    assert caught.value.code == "gate_not_applicable"
    assert accept.accept(s, "listening", GO, now=clock)["operator_states_open"] == []


def test_a_decision_about_another_cut_refuses(avatar_job):
    _, _, s = avatar_job
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, video_sha256="0" * 64, now=clock)
    assert caught.value.code == "video_mismatch"
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, video_sha256="not-a-digest", now=clock)
    assert caught.value.code == "video_sha256_invalid"
    assert not (s.dir / accept.ACCEPTANCE).exists()


def test_no_deliver_check_run_refuses(tmp_path):
    job = example("nv-fixture-card")
    s = new_store(tmp_path, job)
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, now=clock)
    assert caught.value.code == "deliver_check_missing"


def test_a_corrupt_deliver_check_or_a_recomposed_cut_refuses(avatar_job):
    _, _, s = avatar_job
    out = s.dir / s.entry("deliver_check")["dir"] / "out.json"
    saved = out.read_text()
    out.write_text("{}")
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, now=clock)
    assert caught.value.code == "deliver_check_corrupt"
    out.write_text(saved)
    s.archive("compose")
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, now=clock)
    assert caught.value.code == "deliver_check_stale"


def test_a_cut_composed_after_deliver_check_refuses(avatar_job):
    job, recs, s = avatar_job
    g = graph.plan(recaption(job), recs, s, stub_ctx())
    document = g["_documents"]["compose"]
    key = keys.stage_key(document)
    partial = s.begin("compose", key)
    s.commit("compose", key, document, fields_for("compose", partial, key, job))
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, now=clock)
    assert caught.value.code == "deliver_check_stale"


def test_a_malformed_acceptance_record_refuses(avatar_job):
    _, _, s = avatar_job
    (s.dir / accept.ACCEPTANCE).write_text(json.dumps({"kind": "nv_acceptance", "job_id": "x", "acceptances": []}))
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, now=clock)
    assert caught.value.code == "store_invalid"


# A new render ------------------------------------------------------------------------------------------------
def recaption(job):
    """The job with the other VTT setting: a compose knob, so compose and deliver_check rerun into a new cut."""
    changed = dict(job)
    changed["captions"] = dict(job["captions"]) | {"vtt": not job["captions"]["vtt"]}
    return changed


def test_a_new_render_reopens_the_gates_and_a_decision_never_moves_to_it(avatar_job):
    job, recs, s = avatar_job
    accept.accept(s, "listening", GO, now=clock)
    accept.accept(s, "lip_sync", GO, now=clock)
    old_video = video_of(s)
    job = recaption(job)
    s.write_job(job, replace=True)
    settle(job, recs, s, stub_ctx())
    assert video_of(s) != old_video
    g = graph.plan(job, recs, s, stub_ctx())
    assert g["accepted"] == []
    assert {p["gate"] for p in g["pending_operator"]} >= {"listening_acceptance", "lip_sync_acceptance"}
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, now=clock)
    assert caught.value.code == "decision_bound_elsewhere"
    result = accept.accept(s, "listening", GO_3, now=clock)
    assert result["recorded"] and result["operator_states_open"] == ["lip_sync"]
    assert [r["decision"] for r in accept.read(s)["acceptances"]] == [GO, GO, GO_3]  # append-only


def test_a_changed_job_plans_the_accepted_render_stale_and_shows_no_acceptance(avatar_job):
    job, recs, s = avatar_job
    accept.accept(s, "listening", GO, now=clock)
    g = graph.plan(recaption(job), recs, s, stub_ctx())
    assert {n["id"]: n["state"] for n in g["nodes"]}["deliver_check"] == "stale"
    assert g["accepted"] == []


# The plan, the recorded graph and the CLI ----------------------------------------------------------------------
def test_plan_and_the_recorded_graph_list_the_acceptance_and_close_its_gates(avatar_job):
    job, recs, s = avatar_job
    open_before = {p["gate"] for p in s.read_graph()["pending_operator"]}
    assert {"listening_acceptance", "lip_sync_acceptance"} <= open_before
    accept.accept(s, "listening", GO, now=clock)
    recorded = s.read_graph()
    assert [r["gate"] for r in recorded["accepted"]] == ["listening"]
    assert recorded["accepted"][0]["decision"] == GO
    assert {p["gate"] for p in recorded["pending_operator"]} == open_before - {"listening_acceptance"}
    planned = graph.plan(job, recs, s, stub_ctx())
    assert planned["accepted"] == recorded["accepted"]
    assert planned["pending_operator"] == recorded["pending_operator"]
    accept.accept(s, "lip_sync", GO, now=clock)
    assert {p["gate"] for p in s.read_graph()["pending_operator"]} == open_before - {
        "listening_acceptance",
        "lip_sync_acceptance",
    }


def test_admit_is_unchanged_by_an_acceptance(avatar_job):
    """admit lists the operator gates from the job alone; only the plan's view folds acceptances in."""
    job, recs, s = avatar_job
    accept.accept(s, "listening", GO, now=clock)
    gate = graph.admit_stage.admit(job, recs, "resolved")
    assert any(p["gate"] == "listening_acceptance" for p in gate["pending_operator"])


@pytest.fixture
def cli_root(avatar_job):
    _, _, s = avatar_job
    return s, ["--root", str(s.root)]


def call(capsys, argv):
    code = cli.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def test_cli_accept_records_and_prints_json(cli_root, capsys):
    s, root = cli_root
    code, out, _ = call(capsys, ["accept", s.job_id, *root, "--gate", "listening", "--decision", GO])
    assert code == 0
    result = json.loads(out)
    assert result["ok"] and result["recorded"] and result["decision"] == GO and result["gate"] == "listening"
    code, out, _ = call(capsys, ["accept", s.job_id, *root, "--gate", "listening", "--decision", GO, "--json"])
    assert code == 0 and json.loads(out)["recorded"] is False


@pytest.mark.parametrize(
    ("argv", "code"),
    [
        (["--gate", "listening"], "decision_missing"),
        (["--gate", "listening", "--decision", ""], "decision_missing"),
        (["--gate", "listening", "--decision", "GO"], "decision_free_text"),
        (["--gate", "listening", "--decision", "sp:dec:nope"], "decision_invalid"),
        (["--gate", "loudness", "--decision", GO], "gate_automated"),
        (["--gate", "listen", "--decision", GO], "gate_unknown"),
        (["--decision", GO], "gate_unknown"),
    ],
)
def test_cli_accept_refusals_are_typed_and_write_nothing(cli_root, capsys, argv, code):
    s, root = cli_root
    graph_before = s.graph_file.read_bytes()
    status, out, err = call(capsys, ["accept", s.job_id, *root, *argv])
    assert status == 1 and out == ""
    refusal = json.loads(err)
    assert refusal == {"ok": False, "refused": code, "detail": refusal["detail"]}
    assert not (s.dir / accept.ACCEPTANCE).exists() and s.graph_file.read_bytes() == graph_before


def test_cli_accept_an_unknown_job_refuses(tmp_path, capsys):
    status, _, err = call(
        capsys, ["accept", "nv-nothing", "--root", str(tmp_path / "narrated"), "--gate", "listening", "--decision", GO]
    )
    assert status == 1 and json.loads(err)["refused"] == "job_missing"


def test_the_module_entry_point_runs_accept(cli_root):
    s, root = cli_root
    done = subprocess.run(
        [sys.executable, "-m", "narrate", "video", "accept", s.job_id, *root, "--gate", "lip_sync", "--decision", GO],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["operator_states_open"] == ["listening"]
