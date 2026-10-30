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
from narrate.video import accept, cli, deliver, graph, keys
from narrate.video.job import ID, JobError

GO = "sp:dec:01JD00000000000000000000F1"
GO_2 = "sp:dec:01JD00000000000000000000F2"
GO_3 = "sp:dec:01JD0000000000000000000ZZZ"
NOW = "2026-10-30T12:00:00Z"


def gates_for(job, visible=None):
    """deliver_check's gate table for job, with visible_text from the intake's summary as deliver.py reads it."""
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
        "visible_text": deliver.visible_gate(visible)[0],
    }


def fields_for(node_id, partial, key, job, visible=None):
    if node_id == "base":
        return {"measurements": {"fps": FPS}}
    if node_id == "compose":
        (partial / "video.mp4").write_bytes(b"synthetic cut " + key.encode())
    if node_id == "deliver_check":
        return {"measurements": {"gates": gates_for(job, visible)}}
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
            s.commit(node_id, key, document, fields_for(node_id, partial, key, job, recs.get("visible_text")))
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
        ("visible_text", "gate_intake_bound"),
        ("visible_text_unread", "gate_unknown"),
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
        accept.accept(s, gate, GO, video_of(s), now=clock)
    assert caught.value.code == code
    assert not (s.dir / accept.ACCEPTANCE).exists()


def test_every_deliver_check_gate_is_classified():
    """A gate deliver_check reports must be acceptable, unruled, automated or record bound; nothing else."""
    reported = set(gates_for(example("nv-fixture-avatar"))) | {"vrm_badge_decision"}
    assert reported == set(accept.GATES)


# Recording ---------------------------------------------------------------------------------------------------
def test_listening_and_lip_sync_are_recorded_with_the_decision_time_gate_and_render(avatar_job):
    job, _, s = avatar_job
    first = accept.accept(s, "listening", GO, video_of(s), now=clock)
    assert first["recorded"] and first["operator_states_open"] == ["lip_sync"]
    second = accept.accept(s, "lip_sync", GO, video_of(s), now=clock)
    assert second["recorded"] and second["operator_states_open"] == []
    record = json.loads((s.dir / accept.ACCEPTANCE).read_text())
    assert record["kind"] == "nv_acceptance" and record["job_id"] == job["id"]
    entry = s.entry("deliver_check")
    for row, gate in zip(record["acceptances"], ("listening", "lip_sync"), strict=True):
        assert row == {
            "gate": gate,
            "decision": GO,
            "resolution": "form_only",
            "accepted_utc": NOW,
            "job_sha256": keys.digest(job),
            "deliver_check": {"stage_key": entry["key"], "content_sha256": entry["content_sha256"]},
            "video_sha256": video_of(s),
        }


def test_job_json_and_every_stage_stay_as_they_were(avatar_job):
    job, _, s = avatar_job
    before = s.job_file.read_bytes(), json.dumps(s.current(), sort_keys=True)
    accept.accept(s, "listening", GO, video_of(s), now=clock)
    assert (s.job_file.read_bytes(), json.dumps(s.current(), sort_keys=True)) == before
    assert s.read_job() == job and not any(s.verify().values())


def test_the_same_gate_and_decision_again_is_a_no_op(avatar_job):
    _, _, s = avatar_job
    accept.accept(s, "listening", GO, video_of(s), now=clock)
    before = (s.dir / accept.ACCEPTANCE).read_bytes()
    again = accept.accept(s, "listening", GO, video_of(s), now=lambda: "2026-10-31T00:00:00Z")
    assert not again["recorded"] and again["accepted_utc"] == NOW
    assert (s.dir / accept.ACCEPTANCE).read_bytes() == before


def test_a_second_decision_for_an_accepted_gate_refuses(avatar_job):
    _, _, s = avatar_job
    accept.accept(s, "listening", GO, video_of(s), now=clock)
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO_2, video_of(s), now=clock)
    assert caught.value.code == "gate_already_accepted"
    assert len(accept.read(s)["acceptances"]) == 1


def test_lip_sync_without_an_overlay_refuses(card_job):
    _, _, s = card_job
    with pytest.raises(JobError) as caught:
        accept.accept(s, "lip_sync", GO, video_of(s), now=clock)
    assert caught.value.code == "gate_not_applicable"
    assert accept.accept(s, "listening", GO, video_of(s), now=clock)["operator_states_open"] == []


def test_a_decision_about_another_cut_refuses(avatar_job):
    _, _, s = avatar_job
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, video_sha256="0" * 64, now=clock)
    assert caught.value.code == "video_mismatch"
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, video_sha256="not-a-digest", now=clock)
    assert caught.value.code == "video_sha256_invalid"
    assert not (s.dir / accept.ACCEPTANCE).exists()


@pytest.mark.parametrize("value", [None, "", "  "])
def test_no_video_sha256_refuses(avatar_job, value):
    """The decision must name the cut it saw; without one it could close the gates of any later render."""
    _, _, s = avatar_job
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, value, now=clock)
    assert caught.value.code == "video_sha256_missing"
    assert not (s.dir / accept.ACCEPTANCE).exists()


def test_no_deliver_check_run_refuses(tmp_path):
    job = example("nv-fixture-card")
    s = new_store(tmp_path, job)
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, "0" * 64, now=clock)
    assert caught.value.code == "deliver_check_missing"


def test_a_corrupt_deliver_check_or_a_recomposed_cut_refuses(avatar_job):
    _, _, s = avatar_job
    video = video_of(s)
    out = s.dir / s.entry("deliver_check")["dir"] / "out.json"
    saved = out.read_text()
    out.write_text("{}")
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, video_of(s), now=clock)
    assert caught.value.code == "deliver_check_corrupt"
    out.write_text(saved)
    s.archive("compose")
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, video, now=clock)
    assert caught.value.code == "deliver_check_stale"


def test_a_cut_composed_after_deliver_check_refuses(avatar_job):
    job, recs, s = avatar_job
    g = graph.plan(recaption(job), recs, s, stub_ctx())
    document = g["_documents"]["compose"]
    key = keys.stage_key(document)
    partial = s.begin("compose", key)
    s.commit("compose", key, document, fields_for("compose", partial, key, job))
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, video_of(s), now=clock)
    assert caught.value.code == "deliver_check_stale"


def test_a_malformed_acceptance_record_refuses(avatar_job):
    _, _, s = avatar_job
    (s.dir / accept.ACCEPTANCE).write_text(json.dumps({"kind": "nv_acceptance", "job_id": "x", "acceptances": []}))
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, video_of(s), now=clock)
    assert caught.value.code == "store_invalid"


# Forged rows: reading acceptance.json re-checks what accept would refuse -------------------------------------------
def forge(row):
    """A copy of row changed by one forgery."""
    return lambda r: r | row


FORGERIES = {
    "a machine gate": forge({"gate": "loudness"}),
    "the unruled badge": forge({"gate": "vrm_badge_decision"}),
    "an admit gate name": forge({"gate": "listening_acceptance"}),
    "a deliver_check string": forge({"deliver_check": "x"}),
    "a deliver_check list": forge({"deliver_check": []}),
    "a deliver_check without its content digest": lambda r: r | {"deliver_check": {"stage_key": "a" * 64}},
    "a short stage key": lambda r: r | {"deliver_check": r["deliver_check"] | {"stage_key": "abc"}},
    "a numeric content digest": lambda r: r | {"deliver_check": r["deliver_check"] | {"content_sha256": 7}},
    "a malformed video digest": forge({"video_sha256": "x"}),
    "an upper-case job digest": lambda r: r | {"job_sha256": r["job_sha256"].upper()},
    "a lower-case decision": lambda r: r | {"decision": r["decision"].lower()},
    "a resolved claim": forge({"resolution": "resolved"}),
    "no resolution": lambda r: {k: v for k, v in r.items() if k != "resolution"},
    "a free-text time": forge({"accepted_utc": "yesterday"}),
    "an extra field": forge({"note": "lgtm"}),
}


@pytest.mark.parametrize("name", sorted(FORGERIES))
def test_a_forged_row_is_store_invalid_everywhere(avatar_job, capsys, name):
    job, recs, s = avatar_job
    accept.accept(s, "listening", GO, video_of(s), now=clock)
    path = s.dir / accept.ACCEPTANCE
    record = json.loads(path.read_text())
    record["acceptances"] = [FORGERIES[name](dict(record["acceptances"][0]))]  # one row, so only the forgery is wrong
    path.write_text(json.dumps(record))
    for call_ in (
        lambda: accept.read(s),
        lambda: graph.plan(job, recs, s, stub_ctx()),
        lambda: accept.accept(s, "lip_sync", GO, video_of(s), now=clock),
    ):
        with pytest.raises(JobError) as caught:
            call_()
        assert caught.value.code == "store_invalid"
    argv = ["accept", s.job_id, "--root", str(s.root), "--gate", "lip_sync", "--decision", GO]
    status, out, err = call(capsys, [*argv, "--video-sha256", video_of(s)])
    assert status == 1 and out == "" and json.loads(err)["refused"] == "store_invalid"


OTHER_CHECK = {"stage_key": "a" * 64, "content_sha256": "b" * 64}


@pytest.mark.parametrize(
    "rows",
    [
        "two decisions for one gate of one render",
        "one decision on two cuts of one render",
        "one decision on two cuts of two renders",
        "one render with two cuts",
    ],
)
def test_an_inconsistent_record_is_store_invalid(avatar_job, rows):
    _, _, s = avatar_job
    accept.accept(s, "listening", GO, video_of(s), now=clock)
    path = s.dir / accept.ACCEPTANCE
    record = json.loads(path.read_text())
    first = record["acceptances"][0]
    added = {
        "two decisions for one gate of one render": {"decision": GO_2},
        "one decision on two cuts of one render": {"gate": "lip_sync", "video_sha256": "f" * 64},
        "one decision on two cuts of two renders": {"deliver_check": OTHER_CHECK, "video_sha256": "f" * 64},
        "one render with two cuts": {"gate": "lip_sync", "decision": GO_2, "video_sha256": "f" * 64},
    }[rows]
    record["acceptances"].append(first | added)
    path.write_text(json.dumps(record))
    with pytest.raises(JobError) as caught:
        accept.read(s)
    assert caught.value.code == "store_invalid"


def test_one_decision_on_two_renders_of_one_cut_is_consistent(avatar_job):
    """A bed record update reruns deliver_check over the same cut, and the operator's decision stays that cut's."""
    _, _, s = avatar_job
    accept.accept(s, "listening", GO, video_of(s), now=clock)
    path = s.dir / accept.ACCEPTANCE
    record = json.loads(path.read_text())
    record["acceptances"].append(record["acceptances"][0] | {"deliver_check": OTHER_CHECK})
    path.write_text(json.dumps(record))
    assert len(accept.read(s)["acceptances"]) == 2


def test_a_row_for_another_cut_closes_nothing_and_blocks_accept(avatar_job):
    """A well-formed row that binds the current deliver_check but names a video that is not the current cut."""
    job, recs, s = avatar_job
    entry = s.entry("deliver_check")
    row = {
        "gate": "lip_sync",
        "decision": GO_2,
        "resolution": "form_only",
        "accepted_utc": NOW,
        "job_sha256": keys.digest(job),
        "deliver_check": {"stage_key": entry["key"], "content_sha256": entry["content_sha256"]},
        "video_sha256": "f" * 64,
    }
    (s.dir / accept.ACCEPTANCE).write_text(json.dumps(accept.empty(s.job_id) | {"acceptances": [row]}))
    assert len(accept.read(s)["acceptances"]) == 1
    g = graph.plan(job, recs, s, stub_ctx())
    assert g["accepted"] == []
    assert {"listening_acceptance", "lip_sync_acceptance"} <= {p["gate"] for p in g["pending_operator"]}
    before = (s.dir / accept.ACCEPTANCE).read_bytes()
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, video_of(s), now=clock)
    assert caught.value.code == "store_invalid"
    assert (s.dir / accept.ACCEPTANCE).read_bytes() == before


def test_an_acceptance_record_that_is_a_directory_refuses_everywhere(avatar_job, card_job, capsys):
    job, recs, s = avatar_job
    _, _, other = card_job
    (s.dir / accept.ACCEPTANCE).mkdir()
    for call_ in (
        lambda: accept.read(s),
        lambda: graph.plan(job, recs, s, stub_ctx()),
        lambda: accept.accept(s, "listening", GO, video_of(s), now=clock),
        lambda: accept.accept(other, "listening", GO, video_of(other), now=clock),  # it may hold the decision
    ):
        with pytest.raises(JobError) as caught:
            call_()
        assert caught.value.code == "store_invalid"
    status, out, err = call(capsys, ["status", s.job_id, "--root", str(s.root), "--json"])
    assert status == 1 and out == "" and json.loads(err)["refused"] == "store_invalid"
    assert not (other.dir / accept.ACCEPTANCE).exists()


def test_a_dangling_acceptance_symlink_refuses_the_plan(avatar_job):
    job, recs, s = avatar_job
    (s.dir / accept.ACCEPTANCE).symlink_to(s.dir / "nowhere.json")
    with pytest.raises(JobError) as caught:
        graph.plan(job, recs, s, stub_ctx())
    assert caught.value.code == "stage_symlink"


def test_the_plan_view_closes_only_the_gates_accept_may_close():
    """The plan's view closes only listening and lip sync, whatever a row names."""
    assert "vrm_badge_decision" not in accept.ADMIT_GATES.values()
    assert set(accept.ADMIT_GATES.values()) == set(accept.ACCEPTABLE)


def test_plan_shows_each_acceptance_is_checked_by_form_only(avatar_job):
    job, recs, s = avatar_job
    accept.accept(s, "listening", GO, video_of(s), now=clock)
    (row,) = graph.plan(job, recs, s, stub_ctx())["accepted"]
    assert row["resolution"] == "form_only"
    assert s.read_graph()["accepted"][0]["resolution"] == "form_only"


# A new render ------------------------------------------------------------------------------------------------
def recaption(job):
    """The job with the other VTT setting: a compose knob, so compose and deliver_check rerun into a new cut."""
    changed = dict(job)
    changed["captions"] = dict(job["captions"]) | {"vtt": not job["captions"]["vtt"]}
    return changed


def test_a_new_render_reopens_the_gates_and_a_decision_never_moves_to_it(avatar_job):
    job, recs, s = avatar_job
    accept.accept(s, "listening", GO, video_of(s), now=clock)
    accept.accept(s, "lip_sync", GO, video_of(s), now=clock)
    old_video = video_of(s)
    job = recaption(job)
    s.write_job(job, replace=True)
    settle(job, recs, s, stub_ctx())
    assert video_of(s) != old_video
    g = graph.plan(job, recs, s, stub_ctx())
    assert g["accepted"] == []
    assert {p["gate"] for p in g["pending_operator"]} >= {"listening_acceptance", "lip_sync_acceptance"}
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, video_of(s), now=clock)
    assert caught.value.code == "decision_bound_elsewhere"
    result = accept.accept(s, "listening", GO_3, video_of(s), now=clock)
    assert result["recorded"] and result["operator_states_open"] == ["lip_sync"]
    assert [r["decision"] for r in accept.read(s)["acceptances"]] == [GO, GO, GO_3]  # append-only


def test_a_decision_about_render_one_refuses_after_a_re_render(avatar_job):
    """The operator said GO on render 1, and a re-render landed before accept ran: the GO never closes render 2."""
    job, recs, s = avatar_job
    seen = video_of(s)
    job = recaption(job)
    s.write_job(job, replace=True)
    settle(job, recs, s, stub_ctx())
    assert video_of(s) != seen
    for gate in ("listening", "lip_sync"):
        with pytest.raises(JobError) as caught:
            accept.accept(s, gate, GO, seen, now=clock)
        assert caught.value.code == "video_mismatch"
    assert not (s.dir / accept.ACCEPTANCE).exists()
    assert graph.plan(job, recs, s, stub_ctx())["accepted"] == []


def clear_content_id(recs):
    """The bed record with a Content ID result: a deliver_check knob only, so compose and its video stay."""
    recs["music_beds"]["bed-fixture-emaj"]["licence"]["contentIdCheck"] = {"clear": "fixture-check-1"}
    return recs


def test_a_bed_record_update_keeps_the_decision_for_the_same_cut(avatar_job):
    """SPR-258: one GO closes listening and lip sync for a render version. Recording a Content ID result reruns only
    deliver_check over the same video, so the same GO is recorded again for the new render, not a second decision."""
    job, recs, s = avatar_job
    accept.accept(s, "listening", GO, video_of(s), now=clock)
    accept.accept(s, "lip_sync", GO, video_of(s), now=clock)
    video, check = video_of(s), s.entry("deliver_check")["key"]
    recs = clear_content_id(recs)
    settle(job, recs, s, stub_ctx())
    assert video_of(s) == video and s.entry("deliver_check")["key"] != check
    g = graph.plan(job, recs, s, stub_ctx())
    assert g["accepted"] == []
    assert {"listening_acceptance", "lip_sync_acceptance"} <= {p["gate"] for p in g["pending_operator"]}
    s.write_graph(graph.public(g))
    first = accept.accept(s, "listening", GO, video, now=clock)
    assert first["recorded"] and first["operator_states_open"] == ["lip_sync"]
    second = accept.accept(s, "lip_sync", GO, video, now=clock)
    assert second["recorded"] and second["operator_states_open"] == []
    g = graph.plan(job, recs, s, stub_ctx())
    assert [r["gate"] for r in g["accepted"]] == ["listening", "lip_sync"]
    assert not {"listening_acceptance", "lip_sync_acceptance"} & {p["gate"] for p in g["pending_operator"]}
    assert s.read_graph()["accepted"] == g["accepted"]
    assert [r["decision"] for r in accept.read(s)["acceptances"]] == [GO] * 4  # append-only
    with pytest.raises(JobError) as caught:  # the gate still holds one decision per render
        accept.accept(s, "listening", GO_2, video, now=clock)
    assert caught.value.code == "gate_already_accepted"


def test_a_decision_never_moves_to_a_new_cut_after_a_bed_record_update(avatar_job):
    """The same-cut reuse ends where the video changes."""
    job, recs, s = avatar_job
    accept.accept(s, "listening", GO, video_of(s), now=clock)
    recs = clear_content_id(recs)
    settle(job, recs, s, stub_ctx())
    accept.accept(s, "listening", GO, video_of(s), now=clock)
    job = recaption(job)
    s.write_job(job, replace=True)
    settle(job, recs, s, stub_ctx())
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, video_of(s), now=clock)
    assert caught.value.code == "decision_bound_elsewhere"


def test_one_decision_never_closes_a_second_job(avatar_job, card_job):
    _, _, a = avatar_job
    _, _, b = card_job
    assert a.root == b.root and a.job_id != b.job_id
    assert accept.accept(a, "listening", GO, video_of(a), now=clock)["recorded"]
    with pytest.raises(JobError) as caught:
        accept.accept(b, "listening", GO, video_of(b), now=clock)
    assert caught.value.code == "decision_bound_elsewhere"
    assert not (b.dir / accept.ACCEPTANCE).exists()
    assert accept.accept(b, "listening", GO_2, video_of(b), now=clock)["recorded"]
    # and the first job takes the second job's decision no more than the other way round
    with pytest.raises(JobError) as caught:
        accept.accept(a, "lip_sync", GO_2, video_of(a), now=clock)
    assert caught.value.code == "decision_bound_elsewhere"


def test_an_unreadable_record_of_another_job_refuses(avatar_job, card_job):
    """Another job's record may hold the decision, so accept refuses rather than skip it."""
    _, _, a = avatar_job
    _, _, b = card_job
    (b.dir / accept.ACCEPTANCE).write_text("{not json")
    with pytest.raises(JobError) as caught:
        accept.accept(a, "listening", GO, video_of(a), now=clock)
    assert caught.value.code == "store_invalid"
    assert not (a.dir / accept.ACCEPTANCE).exists()


def test_the_root_lock_is_never_a_job_directory(avatar_job):
    _, _, s = avatar_job
    accept.accept(s, "listening", GO, video_of(s), now=clock)
    assert (s.root / accept.LOCK).is_file() and not (s.dir / accept.LOCK).exists()
    assert ID.match(accept.LOCK) is None


def test_a_changed_job_plans_the_accepted_render_stale_and_shows_no_acceptance(avatar_job):
    job, recs, s = avatar_job
    accept.accept(s, "listening", GO, video_of(s), now=clock)
    g = graph.plan(recaption(job), recs, s, stub_ctx())
    assert {n["id"]: n["state"] for n in g["nodes"]}["deliver_check"] == "stale"
    assert g["accepted"] == []


# The plan, the recorded graph and the CLI ----------------------------------------------------------------------
def test_plan_and_the_recorded_graph_list_the_acceptance_and_close_its_gates(avatar_job):
    job, recs, s = avatar_job
    open_before = {p["gate"] for p in s.read_graph()["pending_operator"]}
    assert {"listening_acceptance", "lip_sync_acceptance"} <= open_before
    accept.accept(s, "listening", GO, video_of(s), now=clock)
    recorded = s.read_graph()
    assert [r["gate"] for r in recorded["accepted"]] == ["listening"]
    assert recorded["accepted"][0]["decision"] == GO
    assert {p["gate"] for p in recorded["pending_operator"]} == open_before - {"listening_acceptance"}
    planned = graph.plan(job, recs, s, stub_ctx())
    assert planned["accepted"] == recorded["accepted"]
    assert planned["pending_operator"] == recorded["pending_operator"]
    accept.accept(s, "lip_sync", GO, video_of(s), now=clock)
    assert {p["gate"] for p in s.read_graph()["pending_operator"]} == open_before - {
        "listening_acceptance",
        "lip_sync_acceptance",
    }


def test_admit_is_unchanged_by_an_acceptance(avatar_job):
    """admit lists the operator gates from the job alone; only the plan's view folds acceptances in."""
    job, recs, s = avatar_job
    accept.accept(s, "listening", GO, video_of(s), now=clock)
    gate = graph.admit_stage.admit(job, recs, "resolved")
    assert any(p["gate"] == "listening_acceptance" for p in gate["pending_operator"])


# The visible-text gate beside the acceptances (TIN-7788) -------------------------------------------------------
PARTIAL = {"state": "partial", "unread": ["asset#2"], "opaque": []}
READ_ALL = {"state": "passed", "unread": [], "opaque": []}


def open_gates(g):
    return {p["gate"] for p in g["pending_operator"]}


def test_accept_never_closes_visible_text_and_a_partial_read_keeps_deliver_check_at_the_operator(tmp_path):
    """A guarded intake left asset#2's on-screen text unread. Listening and lip sync are accepted by one GO, yet
    visible_text stays open: accept refuses it, admit still lists visible_text_unread, and deliver_check plans
    pending_operator. Only a re-intake that reads every shown asset closes it. That reruns deliver_check over the same
    cut, so the same GO is recorded again for the new render and no operator gate stays open."""
    job, recs = example("nv-fixture-avatar"), records()
    recs["visible_text"] = dict(PARTIAL)
    s = new_store(tmp_path, job)
    settle(job, recs, s, stub_ctx())
    s.write_graph(graph.public(graph.plan(job, recs, s, stub_ctx())))
    gates = s.manifest("deliver_check")["measurements"]["gates"]
    assert (gates["listening"], gates["lip_sync"], gates["visible_text"]) == ("pending_operator",) * 3
    before = open_gates(s.read_graph())
    assert {"listening_acceptance", "lip_sync_acceptance", "visible_text_unread"} <= before

    with pytest.raises(JobError) as caught:
        accept.accept(s, "visible_text", GO, video_of(s), now=clock)
    assert caught.value.code == "gate_intake_bound"
    assert not (s.dir / accept.ACCEPTANCE).exists()

    first = accept.accept(s, "listening", GO, video_of(s), now=clock)
    assert first["recorded"] and first["operator_states_open"] == ["lip_sync", "visible_text"]
    second = accept.accept(s, "lip_sync", GO, video_of(s), now=clock)
    assert second["recorded"] and second["operator_states_open"] == ["visible_text"]

    for g in (graph.plan(job, recs, s, stub_ctx()), s.read_graph()):
        assert [r["gate"] for r in g["accepted"]] == ["listening", "lip_sync"]
        assert open_gates(g) == before - {"listening_acceptance", "lip_sync_acceptance"}
        (held,) = [p for p in g["pending_operator"] if p["gate"] == "visible_text_unread"]
        assert held["stage"] == "deliver_check" and held["detail"].endswith(": asset#2")
        assert {n["id"]: n["state"] for n in g["nodes"]}["deliver_check"] == "pending_operator"
    with pytest.raises(JobError) as caught:  # still no decision closes it, after both acceptances
        accept.accept(s, "visible_text", GO, video_of(s), now=clock)
    assert caught.value.code == "gate_intake_bound"
    assert [r["gate"] for r in accept.read(s)["acceptances"]] == ["listening", "lip_sync"]

    # A re-intake reads asset#2: the summary is a deliver_check knob, so deliver_check reruns over the same cut.
    video, check = video_of(s), s.entry("deliver_check")["key"]
    recs["visible_text"] = dict(READ_ALL)
    settle(job, recs, s, stub_ctx())
    assert video_of(s) == video and s.entry("deliver_check")["key"] != check
    assert s.manifest("deliver_check")["measurements"]["gates"]["visible_text"] == "passed"
    g = graph.plan(job, recs, s, stub_ctx())
    assert g["accepted"] == [] and "visible_text_unread" not in open_gates(g)
    assert {"listening_acceptance", "lip_sync_acceptance"} <= open_gates(g)
    s.write_graph(graph.public(g))
    assert accept.accept(s, "listening", GO, video, now=clock)["operator_states_open"] == ["lip_sync"]
    assert accept.accept(s, "lip_sync", GO, video, now=clock)["operator_states_open"] == []
    g = graph.plan(job, recs, s, stub_ctx())
    assert [r["gate"] for r in g["accepted"]] == ["listening", "lip_sync"]
    assert not {"listening_acceptance", "lip_sync_acceptance", "visible_text_unread"} & open_gates(g)
    # visible_text passed and both acceptances recorded: deliver_check is fresh again, in the plan, the recorded
    # graph and status alike
    for shown_graph in (g, s.read_graph(), accept.check_recorded(s, s.read_graph())):
        assert {n["id"]: n["state"] for n in shown_graph["nodes"]}["deliver_check"] == "fresh"
        assert not any(p["stage"] == "deliver_check" for p in shown_graph["pending_operator"])


def test_admit_lists_visible_text_unread_beside_the_acceptance_gates():
    """admit's operator gates are the union: listening and lip sync from #76's acceptance model, visible_text_unread
    from the guarded intake, and the acceptance view drops only the first two."""
    job, recs = example("nv-fixture-avatar"), records()
    recs["visible_text"] = dict(PARTIAL)
    gate = graph.admit_stage.admit(job, recs, "resolved")
    assert {"listening_acceptance", "lip_sync_acceptance", "visible_text_unread"} <= {
        p["gate"] for p in gate["pending_operator"]
    }
    assert "visible_text_unread" not in accept.ADMIT_GATES
    rows = [
        {"gate": g, "decision": GO, "resolution": "form_only", "accepted_utc": NOW, "video_sha256": "0" * 64}
        for g in accept.ACCEPTABLE
    ]
    shown = accept.apply({"pending_operator": list(gate["pending_operator"])}, rows)
    assert "visible_text_unread" in open_gates(shown)
    assert not {"listening_acceptance", "lip_sync_acceptance"} & open_gates(shown)


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
    video = ["--video-sha256", video_of(s)]
    code, out, _ = call(capsys, ["accept", s.job_id, *root, "--gate", "listening", "--decision", GO, *video])
    assert code == 0
    result = json.loads(out)
    assert result["ok"] and result["recorded"] and result["decision"] == GO and result["gate"] == "listening"
    assert result["resolution"] == "form_only"
    code, out, _ = call(capsys, ["accept", s.job_id, *root, "--gate", "listening", "--decision", GO, *video, "--json"])
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
        (["--gate", "listening", "--decision", GO], "video_sha256_missing"),
        (["--gate", "listening", "--decision", GO, "--video-sha256", ""], "video_sha256_missing"),
        (["--gate", "listening", "--decision", GO, "--video-sha256", "ABC"], "video_sha256_invalid"),
        (["--gate", "listening", "--decision", GO, "--video-sha256", "0" * 64], "video_mismatch"),
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
        capsys,
        [
            "accept",
            "nv-nothing",
            *("--root", str(tmp_path / "narrated"), "--gate", "listening", "--decision", GO),
            *("--video-sha256", "0" * 64),
        ],
    )
    assert status == 1 and json.loads(err)["refused"] == "job_missing"


def status_of(capsys, s):
    return call(capsys, ["status", s.job_id, "--root", str(s.root), "--json"])


def test_status_shows_an_acceptance_acceptance_json_holds(cli_root, capsys):
    s, _ = cli_root
    accept.accept(s, "listening", GO, video_of(s), now=clock)
    status, out, _ = status_of(capsys, s)
    assert status == 0 and [r["gate"] for r in json.loads(out)["accepted"]] == ["listening"]


@pytest.mark.parametrize("change", ["acceptance.json deleted", "a hand-written graph row", "acceptance.json corrupt"])
def test_status_re_checks_acceptance_json(cli_root, capsys, change):
    """status never shows a gate closed that acceptance.json does not hold for the recorded render and cut."""
    s, _ = cli_root
    if change == "a hand-written graph row":
        document = s.read_graph()
        document["accepted"] = [
            {"gate": "lip_sync", "decision": GO, "resolution": "form_only", "accepted_utc": NOW}
            | {"video_sha256": video_of(s)}
        ]
        s.write_graph(document)
        code = "graph_stale"
    else:
        accept.accept(s, "listening", GO, video_of(s), now=clock)
        if change == "acceptance.json deleted":
            (s.dir / accept.ACCEPTANCE).unlink()
            code = "graph_stale"
        else:
            (s.dir / accept.ACCEPTANCE).write_text("{not json")
            code = "store_invalid"
    status, out, err = status_of(capsys, s)
    assert status == 1 and out == "" and json.loads(err)["refused"] == code


def test_status_refuses_an_acceptance_of_an_earlier_cut(avatar_job, capsys):
    """compose ran again after the graph was recorded: its accepted row names a cut that is no longer current."""
    job, recs, s = avatar_job
    accept.accept(s, "listening", GO, video_of(s), now=clock)
    g = graph.plan(recaption(job), recs, s, stub_ctx())
    document = g["_documents"]["compose"]
    key = keys.stage_key(document)
    partial = s.begin("compose", key)
    s.commit("compose", key, document, fields_for("compose", partial, key, job))
    status, _, err = status_of(capsys, s)
    assert status == 1 and json.loads(err)["refused"] == "graph_stale"


def drop_gate(name):
    def edit(document):
        document["pending_operator"] = [p for p in document["pending_operator"] if p["gate"] != name]

    return edit


def drop_admitted_gate(name):
    def edit(document):
        drop_gate(name)(document)
        document["admit"]["pending_operator"] = [p for p in document["admit"]["pending_operator"] if p["gate"] != name]

    return edit


def other_job_digest(document):
    document["job_sha256"] = "0" * 64


def another_deliver_check_key(document):
    (node,) = [n for n in document["nodes"] if n["id"] == "deliver_check"]
    node["key"] = "0" * 64


@pytest.mark.parametrize(
    "edit",
    [
        drop_gate("listening_acceptance"),
        drop_admitted_gate("listening_acceptance"),
        drop_admitted_gate("lip_sync_acceptance"),
        other_job_digest,
        another_deliver_check_key,
    ],
    ids=["pending", "admit and pending", "lip sync from both", "job digest", "deliver_check key"],
)
def test_status_recomputes_the_operator_view_and_refuses_a_hand_edit(cli_root, capsys, edit):
    """status trusts no operator view in graph.json: hiding a gate, in pending_operator or in admit too, refuses."""
    s, _ = cli_root
    document = s.read_graph()
    assert accept.check_recorded(s, document) is document
    edit(document)
    s.write_graph(document)
    status, out, err = status_of(capsys, s)
    assert status == 1 and out == "" and json.loads(err)["refused"] == "graph_stale"


@pytest.fixture
def partial_job(tmp_path):
    """The avatar fixture after a guarded intake that left asset#2 unread: deliver_check plans pending_operator."""
    job, recs = example("nv-fixture-avatar"), records()
    recs["visible_text"] = dict(PARTIAL)
    s = new_store(tmp_path, job)
    settle(job, recs, s, stub_ctx())
    s.write_graph(graph.public(graph.plan(job, recs, s, stub_ctx())))
    return job, recs, s


def mark_deliver_check_fresh(document):
    (node,) = [n for n in document["nodes"] if n["id"] == "deliver_check"]
    node["state"], node["reason"] = "fresh", None


def mark_deliver_check_stale(document):
    (node,) = [n for n in document["nodes"] if n["id"] == "deliver_check"]
    node["state"], node["reason"] = "stale", "key_changed"


def remove_deliver_check_node(document):
    document["nodes"] = [n for n in document["nodes"] if n["id"] != "deliver_check"]


@pytest.mark.parametrize(
    "edits",
    [
        (drop_gate("visible_text_unread"),),
        (drop_admitted_gate("visible_text_unread"),),
        (mark_deliver_check_fresh,),
        (drop_admitted_gate("visible_text_unread"), mark_deliver_check_fresh),
        (drop_admitted_gate("visible_text_unread"), mark_deliver_check_stale),
    ],
    ids=["pending", "admit and pending", "node fresh", "all three", "node stale"],
)
def test_status_never_hides_the_visible_text_gate(partial_job, capsys, edits):
    """The deliver_check render reports visible_text pending_operator, so admit must list it and the node must hold."""
    _, _, s = partial_job
    accept.accept(s, "listening", GO, video_of(s), now=clock)
    document = s.read_graph()
    assert accept.check_recorded(s, document) is document
    for edit in edits:
        edit(document)
    s.write_graph(document)
    status, out, err = status_of(capsys, s)
    assert status == 1 and out == "" and json.loads(err)["refused"] == "graph_stale"


def test_status_refuses_a_graph_without_the_deliver_check_node(partial_job, capsys):
    """job.json gives the node set: removing deliver_check, with no acceptance recorded and visible_text_unread
    dropped from both lists, still refuses."""
    _, _, s = partial_job
    document = s.read_graph()
    assert accept.check_recorded(s, document) is document
    drop_admitted_gate("visible_text_unread")(document)
    remove_deliver_check_node(document)
    s.write_graph(document)
    status, out, err = status_of(capsys, s)
    assert status == 1 and out == "" and json.loads(err)["refused"] == "graph_stale"


def test_a_job_changed_after_deliver_check_refuses_until_it_reruns(avatar_job):
    """deliver_check keys on job.json's digest: after an edit (here only delivery.handoff, which no cut reads),
    accept refuses the old render, plan shows deliver_check stale, and the rerun takes the same decision for the
    same cut."""
    job, recs, s = avatar_job
    video = video_of(s)
    changed = json.loads(json.dumps(job))
    changed["delivery"]["handoff"] = not job["delivery"]["handoff"]
    s.write_job(changed, replace=True)
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, video, now=clock)
    assert caught.value.code == "deliver_check_stale"
    assert not (s.dir / accept.ACCEPTANCE).exists()
    assert {n["id"]: n["state"] for n in graph.plan(changed, recs, s, stub_ctx())["nodes"]}["deliver_check"] == "stale"
    settle(changed, recs, s, stub_ctx())
    assert video_of(s) == video
    s.write_graph(graph.public(graph.plan(changed, recs, s, stub_ctx())))
    row = accept.accept(s, "listening", GO, video, now=clock)
    assert row["recorded"] and accept.read(s)["acceptances"][0]["job_sha256"] == keys.digest(changed)


def malformed_nodes(s):
    document = s.read_graph()
    document["nodes"] = "deliver_check"
    s.write_graph(document)


def malformed_admit(s):
    document = s.read_graph()
    document["admit"]["pending_operator"] = [None]
    s.write_graph(document)


def malformed_segment(s):
    document = s.read_graph()
    document["admit"]["pending_operator"][0]["segment"] = ["x"]
    s.write_graph(document)


def graph_directory(s):
    s.graph_file.unlink()
    s.graph_file.mkdir()


def graph_symlink(s):
    s.graph_file.unlink()
    s.graph_file.symlink_to(s.dir / "job.json")


@pytest.mark.parametrize(
    ("damage", "code"),
    [
        (malformed_nodes, "store_invalid"),
        (malformed_admit, "store_invalid"),
        (malformed_segment, "store_invalid"),
        (graph_directory, "store_invalid"),
        (graph_symlink, "stage_symlink"),
    ],
)
def test_a_malformed_graph_refuses_accept_typed_before_anything_is_recorded(cli_root, capsys, damage, code):
    s, root = cli_root
    damage(s)
    with pytest.raises(JobError) as caught:
        accept.accept(s, "listening", GO, video_of(s), now=clock)
    assert caught.value.code == code
    assert not (s.dir / accept.ACCEPTANCE).exists()
    argv = ["accept", s.job_id, *root, "--gate", "listening", "--decision", GO, "--video-sha256", video_of(s)]
    status, out, err = call(capsys, argv)
    assert status == 1 and out == "" and json.loads(err)["refused"] == code
    assert not (s.dir / accept.ACCEPTANCE).exists()


@pytest.mark.parametrize("damage", [malformed_nodes, malformed_admit, malformed_segment])
def test_status_refuses_a_malformed_graph_typed(cli_root, capsys, damage):
    """A gate segment that is not a string or null refuses store_invalid, never an untyped crash."""
    s, _ = cli_root
    damage(s)
    status, out, err = status_of(capsys, s)
    assert status == 1 and out == "" and json.loads(err)["refused"] == "store_invalid"


def test_no_graph_json_still_records_and_writes_none(avatar_job):
    _, _, s = avatar_job
    s.graph_file.unlink()
    assert accept.accept(s, "listening", GO, video_of(s), now=clock)["recorded"]
    assert not s.graph_file.exists()


def test_the_module_entry_point_runs_accept(cli_root):
    s, root = cli_root
    done = subprocess.run(
        [
            *(sys.executable, "-m", "narrate", "video", "accept", s.job_id, *root),
            *("--gate", "lip_sync", "--decision", GO, "--video-sha256", video_of(s)),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["operator_states_open"] == ["listening"]
