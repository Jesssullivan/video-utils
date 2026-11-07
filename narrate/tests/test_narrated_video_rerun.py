"""Reruns of one job root: the compose-only proof, the FIX counter, mixed takes and the spend cap
(narrate/video/rerun.py, docs/spec/RENDER_STAGE.md "Reruns", Linear TIN-7788, ruling TIN-7125 3672cb05).

The first half uses the fake stage runner of test_narrated_video_render_stage.py. The second half runs the synthetic
demo bundle through the real stages with the fake engine's sine voice, so a re-intake into one job root is proved on
real stage keys. No model and no GPU runs, and every digest, decision id and run id is made up.
"""

import copy
import json
import os
from unittest import mock

import pytest
from test_narrated_video_graph import example, new_store, plain_ctx, records
from test_narrated_video_intake import (  # noqa: F401  (fixtures)
    ENGINE,
    TEMPLATE,
    VOICE,
    manifest,
    no_whisper,
    set_manifest,
    set_script,
    ws,
)
from test_narrated_video_render_stage import (
    ENV,
    RUN,
    adopted_request,
    fields_for,
    gpu_request,
    refused,
    request,
    settle,
    settled,
    sha,
)

from narrate.video import accept, bundle, cli, findings, fixture, graph, keys, render_stage, rerun, run, store

DECISIONS = [f"sp:dec:01J0000000000000000000000{n}" for n in range(6)]
JOB = "demo-fixture"


@pytest.fixture
def card(tmp_path):
    return settled(tmp_path)


def event(job, number, **changes):
    return adopted_request(job) | {"run_id": f"hatchet-run-{number:02d}"} | changes


def video_of(s):
    return s.manifest("compose")["outputs"]["video.mp4"]


def edited(job, s, edit, recs=None):
    """Write an edited job to the store and run it through the fake runner, as a rerun event would."""
    job = copy.deepcopy(job)
    edit(job)
    s.write_job(job, replace=True)
    settle(job, records() if recs is None else recs, s, plain_ctx())
    return job


def burn(job, flag="burn"):
    """A compose knob, standing in for a slide change on a job with no slides. A later round flips another flag, so
    each round makes a cut no round made before."""
    job["captions"][flag] = not job["captions"][flag]


def new_script(job, recs):
    job["segments"][0]["scriptSha256"] = sha("another script")
    recs["jobs"][job["segments"][0]["narrateJob"]]["inputSha256"] = job["segments"][0]["scriptSha256"]


def ledger(s):
    return json.loads((s.dir / rerun.LEDGER).read_text())


# The commit counter ---------------------------------------------------------------------------------------------
def test_every_commit_takes_the_next_seq(card):
    _, s = card
    current = s.current()
    seqs = sorted(row["seq"] for row in current["stages"].values())
    assert seqs == list(range(1, current["seq"] + 1))


def test_a_seq_that_is_not_an_integer_is_store_invalid(card):
    _, s = card
    value = json.loads(s.current_file.read_text())
    value["seq"] = "7"
    s.current_file.write_text(json.dumps(value))
    assert refused(s.current) == "store_invalid"


# The compose-only proof -----------------------------------------------------------------------------------------
def test_a_first_render_is_recorded_and_a_retry_of_its_event_is_a_no_op(card):
    job, s = card
    first = render_stage.result(event(job, 1), s, ENV)
    assert first["rerun"]["previous"] is None and first["rerun"]["compose_only"] is False
    assert first["rerun"]["ran"][-1] == "deliver_check"
    written = (s.dir / rerun.LEDGER).read_bytes()
    assert render_stage.result(event(job, 1), s, ENV)["rerun"] == first["rerun"]
    assert (s.dir / rerun.LEDGER).read_bytes() == written


def test_a_compose_change_on_the_same_root_runs_only_compose_and_deliver_check(card):
    job, s = card
    render_stage.result(event(job, 1), s, ENV)
    held = {n: r["key"] for n, r in s.current()["stages"].items()}
    job = edited(job, s, burn)
    value = render_stage.result(event(job, 2, rerun={"scope": "compose_only"}), s, ENV)
    shown = value["rerun"]
    assert shown["ran"] == ["compose", "deliver_check"]
    assert shown["changed_keys"] == ["compose", "deliver_check"]
    assert shown["repeated"] == []
    assert shown["compose_only"] is True
    assert shown["unchanged_nodes"] == len(held) - 2
    assert shown["previous"]["run_id"] == "hatchet-run-01"


def test_a_voice_change_refuses_the_compose_only_scope_and_records_nothing(card):
    job, s = card
    render_stage.result(event(job, 1), s, ENV)
    written = (s.dir / rerun.LEDGER).read_bytes()
    recs = records()
    job = edited(job, s, lambda j: new_script(j, recs), recs)
    assert refused(render_stage.result, event(job, 2, rerun={"scope": "compose_only"}), s, ENV) == (
        "rerun_not_compose_only"
    )
    assert (s.dir / rerun.LEDGER).read_bytes() == written
    shown = render_stage.result(event(job, 3, rerun={"scope": "any"}), s, ENV)["rerun"]
    assert "voice/seg-1" in shown["ran"] and shown["compose_only"] is False
    assert "base" not in shown["ran"] and "music" not in shown["ran"]


def test_a_forced_rerun_of_an_unchanged_key_shows_as_repeated(card):
    job, s = card
    render_stage.result(event(job, 1), s, ENV)
    run.force(s, job, {"base"})
    settle(job, records(), s, plain_ctx())
    shown = render_stage.result(event(job, 2), s, ENV)["rerun"]
    assert shown["ran"] == ["base"] and shown["repeated"] == ["base"] and shown["changed_keys"] == []
    assert shown["compose_only"] is False


def test_a_compose_only_rerun_needs_a_render_and_a_stage_that_ran(card):
    job, s = card
    scoped = event(job, 1, rerun={"scope": "compose_only"})
    assert refused(render_stage.result, scoped, s, ENV) == "rerun_no_previous"
    assert not (s.dir / rerun.LEDGER).exists()
    render_stage.result(event(job, 1), s, ENV)
    assert refused(render_stage.result, event(job, 2, rerun={"scope": "compose_only"}), s, ENV) == "rerun_no_change"


def test_a_resume_is_a_new_event_and_runs_only_what_is_left(tmp_path):
    job, recs = example("nv-fixture-card"), records()
    s = new_store(tmp_path, job)
    g = graph.plan(job, recs, s, plain_ctx())
    node = g["runnable"][0]
    document = g["_documents"][node]
    key = keys.stage_key(document)
    partial = s.begin(node, key)
    s.commit(node, key, document, fields_for(node, partial, key, job))
    before = s.entry(node)
    settle(job, recs, s, plain_ctx())  # the new event picks up what the first one left
    assert s.entry(node) == before
    assert s.entry(node)["seq"] == 1
    shown = render_stage.result(event(job, 2, rerun={"scope": "any"}), s, ENV)["rerun"]
    assert shown["previous"] is None and shown["ran"][0] == node  # with no render recorded, ran reaches back to seq 1


def test_an_event_holds_one_render(card):
    job, s = card
    render_stage.result(event(job, 1), s, ENV)
    job = edited(job, s, burn)
    assert refused(render_stage.result, event(job, 1), s, ENV) == "rerun_event_reused"


@pytest.mark.parametrize("changes", [{"packet_id": "another-packet"}, {"rerun": {"scope": "compose_only"}}])
def test_a_reused_event_with_another_request_refuses_before_any_scope_check(card, changes):
    job, s = card
    render_stage.result(event(job, 1), s, ENV)
    written = (s.dir / rerun.LEDGER).read_bytes()
    assert refused(render_stage.result, event(job, 1, **changes), s, ENV) == "rerun_event_reused"
    assert (s.dir / rerun.LEDGER).read_bytes() == written


def test_a_reused_event_with_another_deliver_check_refuses(card):
    job, s = card
    render_stage.result(event(job, 1), s, ENV)
    value = ledger(s)
    value["renders"][0]["deliver_check"]["content_sha256"] = sha("another report")
    (s.dir / rerun.LEDGER).write_text(json.dumps(value))
    assert refused(render_stage.result, event(job, 1), s, ENV) == "rerun_event_reused"


def test_a_retry_of_a_later_event_reads_the_same_previous_render(card):
    job, s = card
    render_stage.result(event(job, 1), s, ENV)
    job = edited(job, s, burn)
    render_stage.result(event(job, 2), s, ENV)
    job = edited(job, s, lambda j: burn(j, "srt"))
    first = render_stage.result(event(job, 3), s, ENV)["rerun"]
    assert first["previous"]["run_id"] == "hatchet-run-02" and first["ran"] == ["compose", "deliver_check"]
    assert render_stage.result(event(job, 3), s, ENV)["rerun"] == first


@pytest.mark.parametrize("stage", ["place", "mix"])
def test_place_or_mix_alone_refuses_the_compose_only_scope(card, stage):
    job, s = card
    render_stage.result(event(job, 1), s, ENV)
    run.force(s, job, {stage})
    settle(job, records(), s, plain_ctx())
    assert refused(render_stage.result, event(job, 2, rerun={"scope": "compose_only"}), s, ENV) == (
        "rerun_not_compose_only"
    )
    shown = render_stage.result(event(job, 3), s, ENV)["rerun"]
    assert shown["ran"] == [stage] and shown["compose_only"] is False


def test_compose_only_needs_a_node_that_ran_and_takes_handoff():
    before = {"run_id": "run", "video_sha256": "0" * 64, "seq": 2, "keys": {"compose": "k"}}
    assert rerun.proof(before, {"compose": {"key": "k", "seq": 2}})["compose_only"] is False
    stages = {"compose": {"key": "new", "seq": 3}, "handoff": {"key": "h", "seq": 4}}
    assert rerun.proof(before, stages)["compose_only"] is True


def test_a_rerun_request_form(card):
    job, _ = card
    assert refused(render_stage.check_request, event(job, 2, rerun={"scope": "all"})) == "rerun_invalid"
    assert refused(render_stage.check_request, event(job, 2, rerun=None)) == "rerun_invalid"
    assert refused(render_stage.check_request, event(job, 2, rerun={"scope": "any", "x": 1})) == "rerun_invalid"
    window = gpu_request(max_seconds=600) | {"rerun": {"scope": "compose_only"}}
    assert refused(render_stage.check_request, window, gpu_draft=True) == "rerun_scope_conflict"


def test_a_rerun_re_intakes_and_compose_only_skips_voice_adopt(card):
    job, _ = card
    plain = render_stage.plan(event(job, 1))
    resume = render_stage.plan(event(job, 2, rerun={"scope": "any"}))
    scoped = render_stage.plan(event(job, 2, rerun={"scope": "compose_only"}))
    assert "--replace" not in next(p for p in plain["phases"] if p["id"] == "intake")["runs"]
    assert "--replace" in next(p for p in resume["phases"] if p["id"] == "intake")["runs"]
    assert "voice_adopt" in [p["id"] for p in resume["phases"]]
    assert [p["id"] for p in scoped["phases"]] == [
        "verify_inputs",
        "claims_gate",
        "intake",
        "preflight",
        "compose",
        "collect",
    ]


def test_a_malformed_ledger_refuses_store_invalid(card):
    job, s = card
    render_stage.result(event(job, 1), s, ENV)
    value = ledger(s)
    value["renders"][0]["extra"] = 1
    (s.dir / rerun.LEDGER).write_text(json.dumps(value))
    assert refused(rerun.read, s) == "store_invalid"
    (s.dir / rerun.LEDGER).write_text("not json")
    assert refused(rerun.read, s) == "store_invalid"
    (s.dir / rerun.LEDGER).unlink()
    (s.dir / rerun.LEDGER).symlink_to(s.dir / "job.json")
    assert refused(rerun.read, s) == "stage_symlink"


# The FIX counter ------------------------------------------------------------------------------------------------
def round_trip(job, s, number):
    """One FIX of the current cut, then a new cut from a new event."""
    out = rerun.fix(s, DECISIONS[number - 1], video_of(s))
    job = edited(job, s, lambda j: burn(j, ("burn", "srt", "vtt")[number - 1]))
    return job, out


def test_a_ledger_of_another_job_or_with_rounds_out_of_order_is_store_invalid(card):
    job, s = card
    for number in (1, 2):
        job, _ = round_trip(job, s, number)
    value = ledger(s)
    (s.dir / rerun.LEDGER).write_text(json.dumps(value | {"fixes": value["fixes"][::-1]}))
    assert refused(rerun.read, s) == "store_invalid"
    (s.dir / rerun.LEDGER).write_text(json.dumps(value | {"job_id": "nv-other"}))
    assert refused(rerun.read, s) == "store_invalid"


def test_three_rounds_then_the_fourth_stops_and_records_nothing(card):
    job, s = card
    render_stage.result(event(job, 1), s, ENV)
    for number in (1, 2, 3):
        job, out = round_trip(job, s, number)
        assert out["round"] == number and out["fix"]["left"] == 3 - number and out["recorded"] is True
        assert out["resolution"] == "form_only"
        value = render_stage.result(event(job, number + 1), s, ENV)
        assert value["rerun"]["fix"] == {"rounds": number, "cap": 3, "left": 3 - number, "answers_round": number}
    written = (s.dir / rerun.LEDGER).read_bytes()
    assert refused(rerun.fix, s, DECISIONS[3], video_of(s)) == "fix_cap_reached"
    assert (s.dir / rerun.LEDGER).read_bytes() == written


def test_replaying_a_round_at_the_cap_is_a_no_op(card):
    job, s = card
    for number in (1, 2):
        job, _ = round_trip(job, s, number)
    video = video_of(s)
    assert rerun.fix(s, DECISIONS[2], video)["recorded"] is True
    again = rerun.fix(s, DECISIONS[2], video)
    assert again["recorded"] is False and again["round"] == 3


def test_a_round_binds_one_cut_and_one_decision(card):
    job, s = card
    first = video_of(s)
    rerun.fix(s, DECISIONS[0], first)
    assert refused(rerun.fix, s, DECISIONS[1], first) == "fix_already_recorded"
    job = edited(job, s, burn)
    assert refused(rerun.fix, s, DECISIONS[1], first) == "video_mismatch"
    assert refused(rerun.fix, s, DECISIONS[0], video_of(s)) == "decision_bound_elsewhere"


@pytest.mark.parametrize(
    ("decision", "video", "code"),
    [
        ("FIX the second slide", "0" * 64, "decision_free_text"),
        ("", "0" * 64, "decision_missing"),
        ("sp:dec:short", "0" * 64, "decision_invalid"),
        (DECISIONS[0], None, "video_sha256_missing"),
        (DECISIONS[0], "abc", "video_sha256_invalid"),
    ],
)
def test_a_fix_takes_the_forms_accept_takes(card, decision, video, code):
    _, s = card
    assert refused(rerun.fix, s, decision, video) == code
    assert not (s.dir / rerun.LEDGER).exists()


def test_a_fix_refuses_an_accepted_cut_and_a_go_decision(card):
    _, s = card
    video = video_of(s)
    accept.accept(s, "listening", DECISIONS[0], video)
    assert refused(rerun.fix, s, DECISIONS[0], video) == "decision_bound_elsewhere"
    assert refused(rerun.fix, s, DECISIONS[1], video) == "cut_accepted"


def two_jobs(tmp_path):
    job_a, s_a = settled(tmp_path)
    other = store.JobStore(s_a.root, "nv-other")
    job_b = copy.deepcopy(job_a) | {"id": "nv-other"}
    other.write_job(job_b)
    settle(job_b, records(), other, plain_ctx())
    return s_a, other


def test_a_decision_from_another_job_refuses(tmp_path):
    s_a, other = two_jobs(tmp_path)
    accept.accept(s_a, "listening", DECISIONS[0], video_of(s_a))
    assert refused(rerun.fix, other, DECISIONS[0], video_of(other)) == "decision_bound_elsewhere"


def test_a_fix_decision_binds_one_cut_of_one_job(tmp_path):
    s_a, other = two_jobs(tmp_path)
    rerun.fix(s_a, DECISIONS[0], video_of(s_a))
    assert refused(rerun.fix, other, DECISIONS[0], video_of(other)) == "decision_bound_elsewhere"
    assert refused(accept.accept, other, "listening", DECISIONS[0], video_of(other)) == "decision_bound_elsewhere"
    assert not (other.dir / rerun.LEDGER).exists() and not (other.dir / accept.ACCEPTANCE).exists()


def test_an_unreadable_ledger_of_another_job_refuses(tmp_path):
    s_a, other = two_jobs(tmp_path)
    (other.dir / rerun.LEDGER).write_text("not json")
    assert refused(accept.accept, s_a, "listening", DECISIONS[0], video_of(s_a)) == "store_invalid"
    assert refused(rerun.fix, s_a, DECISIONS[0], video_of(s_a)) == "store_invalid"


def test_a_cut_sent_back_closes_no_gate(card):
    _, s = card
    video = video_of(s)
    rerun.fix(s, DECISIONS[0], video)
    assert refused(accept.accept, s, "listening", DECISIONS[0], video) == "decision_bound_elsewhere"
    assert refused(accept.accept, s, "listening", DECISIONS[1], video) == "cut_sent_back"
    assert not (s.dir / accept.ACCEPTANCE).exists()


def test_a_fix_decision_accepts_no_later_cut_and_a_new_decision_does(card):
    job, s = card
    rerun.fix(s, DECISIONS[0], video_of(s))
    edited(job, s, burn)
    assert refused(accept.accept, s, "listening", DECISIONS[0], video_of(s)) == "decision_bound_elsewhere"
    assert accept.accept(s, "listening", DECISIONS[1], video_of(s))["recorded"] is True


def test_a_cut_sent_back_must_change(card):
    job, s = card
    render_stage.result(event(job, 1), s, ENV)
    rerun.fix(s, DECISIONS[0], video_of(s))
    assert refused(render_stage.result, event(job, 2), s, ENV) == "fix_unchanged_cut"
    assert render_stage.result(event(job, 1), s, ENV)["rerun"]["fix"]["answers_round"] is None
    job = edited(job, s, burn)
    assert render_stage.result(event(job, 2), s, ENV)["rerun"]["fix"]["answers_round"] == 1


def test_a_cut_any_round_sent_back_cannot_return(card):
    job, s = card
    render_stage.result(event(job, 1), s, ENV)
    first = video_of(s)
    rerun.fix(s, DECISIONS[0], first)
    job = edited(job, s, burn)
    render_stage.result(event(job, 2), s, ENV)
    rerun.fix(s, DECISIONS[1], video_of(s))
    job = edited(job, s, burn)
    assert video_of(s) == first
    written = (s.dir / rerun.LEDGER).read_bytes()
    assert refused(render_stage.result, event(job, 3), s, ENV) == "fix_unchanged_cut"
    assert refused(accept.accept, s, "listening", DECISIONS[2], first) == "cut_sent_back"
    assert (s.dir / rerun.LEDGER).read_bytes() == written


def test_a_fix_with_no_render_row_binds_its_cut_and_the_next_render_answers_it(card):
    job, s = card
    rerun.fix(s, DECISIONS[0], video_of(s))
    assert refused(render_stage.result, event(job, 1), s, ENV) == "fix_unchanged_cut"
    job = edited(job, s, burn)
    assert render_stage.result(event(job, 1), s, ENV)["rerun"]["fix"]["answers_round"] == 1
    job = edited(job, s, lambda j: burn(j, "srt"))
    assert render_stage.result(event(job, 2), s, ENV)["rerun"]["fix"]["answers_round"] is None


def test_more_rounds_than_the_cap_in_the_ledger_is_store_invalid(card):
    job, s = card
    for number in (1, 2, 3):
        job, _ = round_trip(job, s, number)
    value = ledger(s)
    value["fixes"].append(value["fixes"][-1] | {"round": 4})
    (s.dir / rerun.LEDGER).write_text(json.dumps(value))
    assert refused(rerun.fix, s, DECISIONS[3], video_of(s)) == "store_invalid"


def test_the_cli_records_a_round_and_refuses_on_stderr(card, capsys):
    job, s = card
    root = str(s.dir.parent)
    argv = ["fix", job["id"], "--root", root, "--decision", DECISIONS[0], "--video-sha256", video_of(s)]
    assert cli.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["round"] == 1
    assert cli.main(["fix", job["id"], "--root", root, "--decision", "again", "--video-sha256", video_of(s)]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "decision_free_text"


# The spend cap --------------------------------------------------------------------------------------------------
def spending(**changes):
    value = gpu_request(max_seconds=1800)
    value["spend"] = value["spend"] | changes
    return value


def test_a_window_needs_a_spend_cap_and_an_adopted_voice_names_none(card):
    job, _ = card
    bare = gpu_request()
    del bare["spend"]
    assert refused(render_stage.check_request, bare, gpu_draft=True) == "spend_cap_missing"
    named = event(job, 1, spend={"window_cap_usd_cents": 100, "rate_usd_cents_per_hour": 0})
    assert refused(render_stage.check_request, named) == "spend_unneeded"


@pytest.mark.parametrize(
    "spend",
    [
        {"window_cap_usd_cents": 0, "rate_usd_cents_per_hour": 0},
        {"window_cap_usd_cents": True, "rate_usd_cents_per_hour": 0},
        {"window_cap_usd_cents": 10.5, "rate_usd_cents_per_hour": 0},
        {"window_cap_usd_cents": 100, "rate_usd_cents_per_hour": -1},
        {"window_cap_usd_cents": 100},
        {"window_cap_usd_cents": 100, "rate_usd_cents_per_hour": 0, "extra": 1},
        "100",
    ],
)
def test_the_spend_cap_is_a_count_of_cents(spend):
    value = gpu_request() | {"spend": spend}
    assert refused(render_stage.check_request, value, gpu_draft=True) == "spend_invalid"


def test_the_cap_refuses_a_window_whose_ceiling_is_over_it():
    # 30 minutes at 201 cents an hour reaches 101 cents, rounded up
    assert refused(
        render_stage.check_request, spending(window_cap_usd_cents=100, rate_usd_cents_per_hour=201), gpu_draft=True
    ) == ("spend_cap_exceeded")
    out = render_stage.plan(spending(window_cap_usd_cents=101, rate_usd_cents_per_hour=201), gpu_draft=True)
    held = next(p for p in out["phases"] if p["id"] == "voice_gpu")
    assert held["spend"]["ceiling_usd_cents"] == 101


# Mixed takes ----------------------------------------------------------------------------------------------------
def mixed(runs):
    value = gpu_request()
    value["voice"] = {"mode": "mixed", "runs": runs}
    return value


def test_v1_refuses_a_mixed_window_outside_the_draft_plan(card):
    job, s = card
    value = mixed({"seg-1": RUN, "seg-2": None})
    assert refused(render_stage.check_request, value) == "gpu_window_not_v1"
    value["job_id"] = job["id"]
    assert refused(render_stage.result, value, s, ENV) == "gpu_window_not_v1"


def test_a_mixed_plan_voices_only_the_beats_it_names():
    out = render_stage.plan(mixed({"seg-1": RUN, "seg-2": None, "seg-3": None}), gpu_draft=True)
    assert out["gpu"] is True and out["draft"] is True
    assert [p["id"] for p in out["phases"]] == [
        "verify_inputs",
        "claims_gate",
        "intake",
        "preflight",
        "voice_takes",
        "voice_plan",
        "voice_gpu",
        "voice_render",
        "voice_adopt",
        "voice_ready",
        "compose",
        "collect",
    ]
    for phase in ("voice_plan", "voice_gpu", "voice_render"):
        assert next(p for p in out["phases"] if p["id"] == phase)["segments"] == ["seg-2", "seg-3"]
    assert [p["id"] for p in out["phases"] if p["gpu"]] == ["voice_gpu"]
    assert next(p for p in out["phases"] if p["id"] == "voice_ready")["runs"].endswith("--after-window")


@pytest.mark.parametrize(
    ("runs", "code"),
    [
        ({}, "voice_runs_missing"),
        (None, "voice_runs_missing"),
        ({"seg-1": "abc", "seg-2": None}, "voice_runs_invalid"),
        ({"Not An Id": RUN, "seg-2": None}, "voice_runs_invalid"),
        ({"seg-1": RUN, "seg-2": RUN}, "voice_mixed_invalid"),
        ({"seg-1": None, "seg-2": None}, "voice_mixed_invalid"),
    ],
)
def test_a_mixed_request_names_every_take_or_null(runs, code):
    assert refused(render_stage.check_request, mixed(runs), gpu_draft=True) == code


def test_a_mixed_window_needs_its_lease():
    value = mixed({"seg-1": RUN, "seg-2": None}) | {"lease": None}
    assert refused(render_stage.check_request, value, gpu_draft=True) == "lease_missing"


def two_beats(s_root):
    """The card job with a second beat, run by the fake runner."""
    job, recs = example("nv-fixture-card"), records()
    second = copy.deepcopy(recs["jobs"]["job-fixture-fake"])
    second["id"] = "job-fixture-fake-2"
    second["inputSha256"] = sha("second synthetic segment")
    recs["jobs"][second["id"]] = second
    job["segments"].append(
        job["segments"][0]
        | {
            "id": "seg-2",
            "narrateJob": second["id"],
            "scriptSha256": second["inputSha256"],
            "anchor": {"atSeconds": 12.5},
        }
    )
    s = new_store(s_root, job)
    settle(job, recs, s, plain_ctx())
    return job, recs, s


def takes_of(request_value, job, recs, s, after=False):
    g = graph.plan(job, recs, s, plain_ctx())
    return render_stage.takes(request_value | {"job_id": job["id"]}, g, s, job, gpu_draft=True, after=after)


def change_beat(job, recs, index):
    """A new script on one beat of two_beats, so its voice node plans stale."""
    segment = job["segments"][index]
    segment["scriptSha256"] = sha(f"a changed beat {index}")
    recs["jobs"][segment["narrateJob"]]["inputSha256"] = segment["scriptSha256"]


def test_takes_keeps_a_held_take_and_voices_only_the_changed_beat(tmp_path):
    job, recs, s = two_beats(tmp_path)
    render_stage.result(event(job, 1) | {"voice": {"mode": "from_run", "runs": {"seg-1": RUN, "seg-2": RUN}}}, s, ENV)
    change_beat(job, recs, 1)
    s.write_job(job, replace=True)
    value = mixed({"seg-1": RUN, "seg-2": None})
    out = takes_of(value, job, recs, s)
    assert out["takes"] == {"seg-1": "keep", "seg-2": "revoice"}
    assert out["revoice"] == ["seg-2"] and out["ready"] is False
    settle(job, recs, s, plain_ctx())  # the fake runner stands in for the window and voice_adopt
    out = takes_of(value, job, recs, s, after=True)
    assert out["takes"] == {"seg-1": "keep", "seg-2": "revoiced"} and out["ready"] is True


def test_takes_refuses_a_window_on_a_beat_that_needs_no_take(tmp_path):
    job, recs, s = two_beats(tmp_path)
    render_stage.result(event(job, 1) | {"voice": {"mode": "from_run", "runs": {"seg-1": RUN, "seg-2": RUN}}}, s, ENV)
    assert refused(takes_of, mixed({"seg-1": RUN, "seg-2": None}), job, recs, s) == "revoice_unneeded"


def test_before_a_window_a_fresh_beat_refuses_on_a_root_with_no_render(tmp_path):
    job, recs, s = two_beats(tmp_path)
    assert refused(takes_of, mixed({"seg-1": RUN, "seg-2": None}), job, recs, s) == "revoice_unneeded"


def test_before_a_window_a_beat_committed_since_the_last_render_still_refuses(tmp_path):
    job, recs, s = two_beats(tmp_path)
    render_stage.result(event(job, 1) | {"voice": {"mode": "from_run", "runs": {"seg-1": RUN, "seg-2": RUN}}}, s, ENV)
    change_beat(job, recs, 1)
    s.write_job(job, replace=True)
    settle(job, recs, s, plain_ctx())  # a resume finds the take already in
    value = mixed({"seg-1": RUN, "seg-2": None})
    assert refused(takes_of, value, job, recs, s) == "revoice_unneeded"
    assert takes_of(value, job, recs, s, after=True)["takes"]["seg-2"] == "revoiced"


def test_after_a_window_an_unchanged_beat_still_refuses(tmp_path):
    job, recs, s = two_beats(tmp_path)
    render_stage.result(event(job, 1) | {"voice": {"mode": "from_run", "runs": {"seg-1": RUN, "seg-2": RUN}}}, s, ENV)
    assert refused(takes_of, mixed({"seg-1": RUN, "seg-2": None}), job, recs, s, after=True) == "revoice_unneeded"


def test_a_gpu_window_voices_every_beat_so_a_fresh_one_refuses(tmp_path):
    job, recs, s = two_beats(tmp_path)
    change_beat(job, recs, 0)
    s.write_job(job, replace=True)
    assert refused(takes_of, gpu_request(), job, recs, s) == "revoice_unneeded"


def test_a_changed_beat_named_with_its_old_take_refuses_before_any_spend(tmp_path):
    job, recs, s = two_beats(tmp_path)
    change_beat(job, recs, 0)
    change_beat(job, recs, 1)
    s.write_job(job, replace=True)
    assert refused(takes_of, mixed({"seg-1": RUN, "seg-2": None}), job, recs, s) == "voice_run_mismatch"
    out = takes_of(mixed({"seg-1": "e" * 64, "seg-2": None}), job, recs, s)
    assert out["takes"] == {"seg-1": "adopt", "seg-2": "revoice"}  # another take is checked at voice_adopt


def test_takes_adopts_on_a_new_root_and_refuses_another_run(tmp_path):
    job, recs, s = two_beats(tmp_path)
    assert refused(takes_of, mixed({"seg-1": "e" * 64, "seg-2": None}), job, recs, s) == "voice_run_mismatch"
    fresh = store.JobStore(tmp_path / "other", job["id"])
    fresh.write_job(job)
    out = takes_of(mixed({"seg-1": RUN, "seg-2": None}), job, recs, fresh)
    assert out["takes"] == {"seg-1": "adopt", "seg-2": "revoice"}


def test_takes_names_every_segment_and_the_right_job(tmp_path):
    job, recs, s = two_beats(tmp_path)
    assert refused(takes_of, mixed({"seg-1": RUN, "seg-9": None}), job, recs, s) == "voice_runs_invalid"
    g = graph.plan(job, recs, s, plain_ctx())
    other = mixed({"seg-1": RUN, "seg-2": None})
    assert refused(render_stage.takes, other | {"job_id": "nv-other"}, g, s, job, gpu_draft=True) == "job_mismatch"
    assert refused(render_stage.takes, other, g, s, job) == "gpu_window_not_v1"


@pytest.mark.parametrize("state", ["blocked", "refused"])
def test_takes_refuses_a_blocked_or_refused_voice_node(tmp_path, state):
    job, recs, s = two_beats(tmp_path)
    g = graph.plan(job, recs, s, plain_ctx())
    row = next(n for n in g["nodes"] if n["id"] == "voice/seg-2")
    row |= {"state": state, "reason": "source_missing"}
    value = mixed({"seg-1": RUN, "seg-2": None}) | {"job_id": job["id"]}
    assert refused(render_stage.takes, value, g, s, job, gpu_draft=True) == "voice_blocked"


# The extension: one round per decision, each recorded (TIN-7125 11296de3) ---------------------------------------
def at_the_cap(job, s):
    for number in (1, 2, 3):
        job, _ = round_trip(job, s, number)
    return job


def test_a_decision_at_the_cap_extends_the_root_by_the_one_round_it_takes(card):
    job, s = card
    job = at_the_cap(job, s)
    video = video_of(s)
    assert refused(rerun.fix, s, DECISIONS[3], video) == "fix_cap_reached"
    out = rerun.fix(s, DECISIONS[3], video, extend=True)
    assert out["round"] == 4 and out["recorded"] is True and out["fix"] == {
        "rounds": 4, "cap": 4, "left": 0, "answers_round": None,
    }  # fmt: skip
    assert ledger(s)["fixes"][-1]["extended"] is True and ledger(s)["fixes"][-1]["decision"] == DECISIONS[3]
    assert rerun.read(s)["fixes"][3]["round"] == 4
    assert rerun.fix(s, DECISIONS[3], video, extend=True)["recorded"] is False

    job = edited(job, s, lambda j: burn(j, "soft"))
    value = render_stage.result(event(job, 5), s, ENV)
    assert value["rerun"]["fix"] == {"rounds": 4, "cap": 4, "left": 0, "answers_round": 4}
    assert refused(rerun.fix, s, DECISIONS[4], video_of(s)) == "fix_cap_reached"
    assert rerun.fix(s, DECISIONS[4], video_of(s), extend=True)["round"] == 5


def test_a_decision_with_rounds_left_extends_nothing(card):
    _, s = card
    assert refused(rerun.fix, s, DECISIONS[0], video_of(s), extend=True) == "fix_extend_unneeded"
    assert not (s.dir / rerun.LEDGER).exists()


def test_an_extension_binds_its_decision_like_any_fix(card):
    job, s = card
    job = at_the_cap(job, s)
    assert refused(rerun.fix, s, DECISIONS[0], video_of(s), extend=True) == "decision_bound_elsewhere"
    assert refused(rerun.fix, s, "one more round please", video_of(s), extend=True) == "decision_free_text"
    assert len(ledger(s)["fixes"]) == 3


def test_a_round_marked_extended_inside_the_cap_is_store_invalid(card):
    job, s = card
    round_trip(job, s, 1)
    value = ledger(s)
    value["fixes"][0]["extended"] = True
    (s.dir / rerun.LEDGER).write_text(json.dumps(value))
    assert refused(rerun.read, s) == "store_invalid"
    value["fixes"][0]["extended"] = False
    (s.dir / rerun.LEDGER).write_text(json.dumps(value))
    assert refused(rerun.read, s) == "store_invalid"


# Machine-started rounds ------------------------------------------------------------------------------------------
CAMPAIGN = "campaign-fixture"


def report_of(*codes, page="p1"):
    return findings.report([findings.finding(code, page=page) for code in codes])


def bound(job, s):
    assert rerun.bind_campaign(s, CAMPAIGN)["recorded"] is True
    return job, s


def machine_trip(job, s, number, *codes):
    """One round on the current cut, then a new cut from a new event."""
    out = rerun.machine_round(s, report_of(*(codes or ("slide_not_shown",))), video_of(s))
    job = edited(job, s, lambda j: burn(j, ("burn", "srt", "vtt", "soft")[number - 1]))
    return job, out


def test_a_campaign_round_needs_no_softproxy_decision(card):
    job, s = bound(*card)
    video = video_of(s)
    out = rerun.machine_round(s, report_of("slide_not_shown", "slide_not_shown"), video)
    assert out["ok"] is True and out["result"] == "round" and out["round"] == 1 and out["recorded"] is True
    assert out["campaign"] == CAMPAIGN and out["fix"]["left"] == 2
    row = ledger(s)["fixes"][0]
    assert row["decision"] is None and row["resolution"] == rerun.MACHINE and row["codes"] == {"slide_not_shown": 2}
    assert row["video_sha256"] == video and row["job_sha256"] == keys.digest(job)
    assert row["reach"] == ["compose", "deliver_check", "handoff"]
    assert rerun.read(s)["fixes"][0] == row


def test_a_campaign_round_binds_its_cut_as_a_fix_does(card):
    job, s = bound(*card)
    video = video_of(s)
    rerun.machine_round(s, report_of("slide_not_shown"), video)
    assert refused(accept.accept, s, "listening", DECISIONS[0], video) == "cut_sent_back"
    assert refused(rerun.fix, s, DECISIONS[0], video) == "fix_already_recorded"
    assert refused(render_stage.result, event(job, 1), s, ENV) == "fix_unchanged_cut"
    job = edited(job, s, burn)
    value = render_stage.result(event(job, 2), s, ENV)
    assert value["rerun"]["fix"]["answers_round"] == 1


def test_the_same_findings_on_the_same_cut_are_a_no_op_and_others_refuse(card):
    job, s = bound(*card)
    video = video_of(s)
    rerun.machine_round(s, report_of("slide_not_shown"), video)
    written = (s.dir / rerun.LEDGER).read_bytes()
    again = rerun.machine_round(s, report_of("slide_not_shown"), video)
    assert again["recorded"] is False and again["round"] == 1
    assert refused(rerun.machine_round, s, report_of("slide_letterbox"), video) == "fix_already_recorded"
    assert (s.dir / rerun.LEDGER).read_bytes() == written


def test_a_round_read_before_any_render_binds_no_cut_and_a_first_render_answers_it(tmp_path):
    job, recs = example("nv-fixture-card"), records()
    s = new_store(tmp_path, job)
    rerun.bind_campaign(s, CAMPAIGN)
    out = rerun.machine_round(s, report_of("avatar_box_occupied"))
    assert out["round"] == 1 and ledger(s)["fixes"][0]["video_sha256"] is None
    assert ledger(s)["fixes"][0]["deliver_check"] is None
    assert rerun.machine_round(s, report_of("avatar_box_occupied"))["recorded"] is False
    assert refused(rerun.machine_round, s, report_of("slide_letterbox")) == "fix_already_recorded"
    settle(job, recs, s, plain_ctx())
    value = render_stage.result(event(job, 1), s, ENV)
    assert value["rerun"]["fix"]["answers_round"] == 1


@pytest.mark.parametrize("edition", ["ClientNarrated", "ClientVoiceOnly"])
def test_a_client_job_cannot_be_bound_and_still_needs_its_decision(card, edition):
    job, s = card
    client = copy.deepcopy(job) | {"edition": edition}
    s.write_job(client, replace=True)
    assert refused(rerun.bind_campaign, s, CAMPAIGN) == "campaign_client_job"
    assert refused(rerun.machine_round, s, report_of("slide_not_shown")) == "round_needs_decision"
    assert not (s.dir / rerun.LEDGER).exists()


def test_a_client_cut_takes_a_round_only_with_its_softproxy_id(card):
    job, s = card
    edited(job, s, lambda j: j.update(edition="ClientNarrated", music=None))
    video = video_of(s)
    assert refused(rerun.machine_round, s, report_of("slide_not_shown"), video) == "round_needs_decision"
    assert refused(rerun.fix, s, None, video) == "decision_missing"
    assert not (s.dir / rerun.LEDGER).exists()
    assert rerun.fix(s, DECISIONS[0], video)["round"] == 1
    assert ledger(s)["fixes"][0]["decision"] == DECISIONS[0]


def test_a_client_edition_written_after_a_binding_still_needs_its_decision(card):
    job, s = bound(*card)
    s.write_job(copy.deepcopy(job) | {"edition": "ClientNarrated"}, replace=True)
    written = (s.dir / rerun.LEDGER).read_bytes()
    assert refused(rerun.machine_round, s, report_of("slide_not_shown")) == "round_needs_decision"
    assert (s.dir / rerun.LEDGER).read_bytes() == written


def test_a_job_with_no_binding_needs_its_decision_whatever_its_edition(card):
    job, s = card
    assert job["edition"] == "Internal"
    assert refused(rerun.machine_round, s, report_of("slide_not_shown"), video_of(s)) == "round_needs_decision"
    assert not (s.dir / rerun.LEDGER).exists()
    assert rerun.fix(s, DECISIONS[0], video_of(s))["round"] == 1


@pytest.mark.parametrize("decision", ["", "FIX it", "machine", None])
def test_a_person_on_a_bound_job_still_answers_with_a_softproxy_id(card, decision):
    job, s = bound(*card)
    code = refused(rerun.fix, s, decision, video_of(s))
    assert code in ("decision_missing", "decision_free_text", "decision_invalid")
    assert ledger(s)["fixes"] == []


def test_a_root_on_the_operators_path_stays_there(card):
    job, s = card
    rerun.fix(s, DECISIONS[0], video_of(s))
    assert refused(rerun.bind_campaign, s, CAMPAIGN) == "campaign_after_decision"
    assert refused(rerun.machine_round, s, report_of("slide_not_shown")) == "round_needs_decision"


def test_an_accepted_root_stays_on_the_operators_path(card):
    job, s = card
    accept.accept(s, "listening", DECISIONS[0], video_of(s))
    assert refused(rerun.bind_campaign, s, CAMPAIGN) == "campaign_after_decision"


def test_a_binding_holds_one_campaign_and_one_id_form(card):
    job, s = bound(*card)
    assert rerun.bind_campaign(s, CAMPAIGN)["recorded"] is False
    assert refused(rerun.bind_campaign, s, "another-campaign") == "campaign_bound"
    for value in ("", "two words", "../up", "trailing\n", None):
        assert refused(rerun.bind_campaign, s, value) == "campaign_id_invalid"


def test_the_cap_parks_the_root_and_asks_nobody(card):
    job, s = bound(*card)
    render_stage.result(event(job, 1), s, ENV)
    for number in (1, 2, 3):
        job, out = machine_trip(job, s, number)
        assert out["round"] == number and out["result"] == "round"
        render_stage.result(event(job, number + 1), s, ENV)
    video = video_of(s)
    out = rerun.machine_round(s, report_of("slide_not_shown", "flash_jump"), video)
    assert out["ok"] is True and out["result"] == "parked" and out["recorded"] is True
    assert out["campaign"] == CAMPAIGN and out["codes"] == {"flash_jump": 1, "slide_not_shown": 1}
    assert out["fix"] == {"rounds": 3, "cap": 3, "left": 0, "answers_round": None}
    held = ledger(s)
    assert len(held["fixes"]) == 3 and held["parked"]["video_sha256"] == video and held["parked"]["round"] == 3
    assert rerun.read(s)["parked"] == held["parked"]
    written = (s.dir / rerun.LEDGER).read_bytes()
    again = rerun.machine_round(s, report_of("slide_letterbox"), video)
    assert again["result"] == "parked" and again["recorded"] is False
    assert (s.dir / rerun.LEDGER).read_bytes() == written


def test_a_person_may_still_extend_a_parked_root_and_it_stays_parked(card):
    job, s = bound(*card)
    for number in (1, 2, 3):
        job, _ = machine_trip(job, s, number)
    assert rerun.machine_round(s, report_of("slide_not_shown"), video_of(s))["result"] == "parked"
    assert rerun.fix(s, DECISIONS[0], video_of(s), extend=True)["round"] == 4
    job = edited(job, s, lambda j: burn(j, "soft"))
    assert rerun.machine_round(s, report_of("slide_not_shown"), video_of(s))["result"] == "parked"


def test_a_machine_round_past_the_cap_is_store_invalid(card):
    job, s = bound(*card)
    for number in (1, 2, 3):
        job, _ = machine_trip(job, s, number)
    value = ledger(s)
    value["fixes"].append(value["fixes"][-1] | {"round": 4})
    (s.dir / rerun.LEDGER).write_text(json.dumps(value))
    assert refused(rerun.read, s) == "store_invalid"


@pytest.mark.parametrize(
    "edit",
    [
        lambda v: v | {"campaign": {"id": "two words", "resolution": "form_only", "recorded_utc": "x"}},
        lambda v: v | {"campaign": {"id": CAMPAIGN}},
        lambda v: v | {"parked": {"round": 3}},
        lambda v: v | {"fixes": [v["fixes"][0] | {"decision": DECISIONS[0]}]},
        lambda v: v | {"fixes": [v["fixes"][0] | {"deliver_check": 5}]},
        lambda v: v | {"fixes": [v["fixes"][0] | {"findings_sha256": "short"}]},
    ],
)
def test_a_forged_campaign_parked_or_round_row_is_store_invalid(card, edit):
    job, s = bound(*card)
    rerun.machine_round(s, report_of("slide_not_shown"), video_of(s))
    (s.dir / rerun.LEDGER).write_text(json.dumps(edit(ledger(s))))
    assert refused(rerun.read, s) == "store_invalid"


def test_a_ledger_written_before_campaigns_still_reads_and_starts_no_round(card):
    job, s = card
    rerun.fix(s, DECISIONS[0], video_of(s))
    value = ledger(s)
    assert "campaign" not in value and "parked" not in value and set(value["fixes"][0]) == rerun.FIX_FIELDS
    assert refused(rerun.machine_round, s, report_of("slide_not_shown")) == "round_needs_decision"


@pytest.mark.parametrize(
    ("report", "video", "code"),
    [
        ({"kind": "other"}, None, "findings_invalid"),
        (findings.report([]), None, "round_no_findings"),
        (findings.report([findings.finding("lexical_finding", rule="XL-FIX-001")]), None, "round_no_findings"),
        (report_of("flash_jump"), None, "round_video_missing"),
        (report_of("slide_not_shown"), None, "round_video_missing"),
        (report_of("slide_layer_missing"), None, "round_video_missing"),
        (report_of("slide_layer_mismatch"), None, "round_video_missing"),
        (report_of("slide_letterbox", "slide_not_shown"), None, "round_video_missing"),
        (report_of("slide_not_shown"), "abc", "video_sha256_invalid"),
        (report_of("slide_not_shown"), "0" * 64, "video_mismatch"),
    ],
)
def test_a_round_refuses_with_nothing_recorded(card, report, video, code):
    job, s = bound(*card)
    written = (s.dir / rerun.LEDGER).read_bytes()
    assert refused(rerun.machine_round, s, report, video) == code
    assert (s.dir / rerun.LEDGER).read_bytes() == written


def test_an_accepted_cut_takes_no_round(card):
    job, s = bound(*card)
    accept.accept(s, "listening", DECISIONS[0], video_of(s))
    assert refused(rerun.machine_round, s, report_of("slide_not_shown"), video_of(s)) == "cut_accepted"


def test_a_caller_cannot_widen_or_narrow_a_known_codes_reach(card):
    job, s = bound(*card)
    row = findings.finding("voice_qa_failed", segment="seg-1") | {"stage": "compose"}
    out = rerun.machine_round(s, findings.report([row]), video_of(s))
    assert "voice" in out["reach"]


# A round's reach: what its fix may run ---------------------------------------------------------------------------
def test_the_reach_of_a_slide_fix_holds_no_voice_stage():
    assert graph.reach(["compose"]) == list(rerun.COMPOSE_STAGES)
    assert not {"script", "voice", "voice_qa"} & set(graph.reach(["base"]))
    assert graph.reach(["mix"]) == ["mix", "compose", "deliver_check", "handoff"]


def test_the_reach_of_a_script_fix_holds_the_voice_and_what_reads_it():
    assert {"script", "voice", "voice_qa", "place", "compose"} <= set(graph.reach(["script"]))
    assert "base" not in graph.reach(["script"])


@pytest.mark.parametrize("entries", [[None], ["no-such-stage"], ["compose", None]])
def test_an_entry_that_bounds_nothing_reaches_the_whole_graph(entries):
    assert graph.reach(entries) == graph.ORDER


def test_every_finding_stage_is_a_stage_of_the_graph():
    assert {stage for _, stage in findings.CODES.values()} - set(graph.BY_ID) == {None}
    assert not {"voice", "voice_qa"} & set(graph.reach([findings.CODES["slide_letterbox"][1]]))


def test_a_render_that_re_voices_on_a_slide_round_refuses_and_records_nothing(card):
    job, s = bound(*card)
    render_stage.result(event(job, 1), s, ENV)
    rerun.machine_round(s, report_of("slide_letterbox"), video_of(s))
    recs = records()
    job = edited(job, s, lambda j: new_script(j, recs), recs)
    before = ledger(s)
    assert refused(render_stage.result, event(job, 2), s, ENV) == "round_out_of_reach"
    assert ledger(s) == before


def test_a_round_whose_fix_may_re_voice_takes_that_render(card):
    job, s = bound(*card)
    render_stage.result(event(job, 1), s, ENV)
    rerun.machine_round(s, report_of("voice_qa_failed"), video_of(s))
    recs = records()
    job = edited(job, s, lambda j: new_script(j, recs), recs)
    value = render_stage.result(event(job, 2), s, ENV)
    assert value["rerun"]["fix"]["answers_round"] == 1
    assert "voice/" + job["segments"][0]["id"] in value["rerun"]["ran"]


# The commands ----------------------------------------------------------------------------------------------------
def test_the_round_commands_bind_record_park_and_print_findings(card, tmp_path, capsys):
    job, s = card
    root = ["--root", str(s.root)]
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report_of("slide_not_shown")))

    assert cli.main(["round", job["id"], "--findings", str(path), *root]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "round_needs_decision"
    assert cli.main(["campaign-bind", job["id"], "--campaign", CAMPAIGN, *root]) == 0
    assert json.loads(capsys.readouterr().out)["recorded"] is True
    for number, flag in enumerate(("burn", "srt", "vtt"), 1):
        assert cli.main(["round", job["id"], "--findings", str(path), "--video-sha256", video_of(s), *root]) == 0
        assert json.loads(capsys.readouterr().out)["round"] == number
        job = edited(job, s, lambda j, flag=flag: burn(j, flag))
    assert cli.main(["round", job["id"], "--findings", str(path), "--video-sha256", video_of(s), *root]) == 0
    assert json.loads(capsys.readouterr().out)["result"] == "parked"
    # This fake runner's deliver_check.json is a stub. The real stages' report is read in the job root test below.
    assert cli.main(["findings", job["id"], *root]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "store_invalid"
    path.write_text("not json")
    assert cli.main(["round", job["id"], "--findings", str(path), *root]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "findings_invalid"


def test_the_fix_command_takes_extend(card, capsys):
    job, s = card
    job = at_the_cap(job, s)
    capsys.readouterr()
    argv = ["fix", job["id"], "--root", str(s.root), "--decision", DECISIONS[3], "--video-sha256", video_of(s)]
    assert cli.main(argv) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "fix_cap_reached"
    assert cli.main([*argv, "--extend"]) == 0
    assert json.loads(capsys.readouterr().out)["round"] == 4


# One job root through the real stages ---------------------------------------------------------------------------
@pytest.fixture
def root(ws, tmp_path, ffmpeg):  # noqa: F811
    return Root(ws, tmp_path)


class Root:
    """The synthetic demo bundle through the real commands, on one job root."""

    def __init__(self, w, base):
        self.w, self.root, self.out = w, base / "narrated", base / "narrated" / JOB / "intake"
        self.common = ["--root", str(self.root), "--records", str(self.out / "records"), "--store", str(w["store"])]
        self.common += ["--lexical", str(w["lexical"])]

    def intake(self, *extra):
        w = self.w
        argv = ["intake", str(w["bundle"]), "--out", str(self.out), "--records", str(w["records"]),
                "--store", str(w["store"]), "--narrate-template", TEMPLATE, "--voice", VOICE, "--engine", ENGINE,
                "--no-avatar", "--json", *extra]  # fmt: skip
        return cli.main(argv)

    def init(self, *extra):
        source = str(self.out / "narrated-video.json")
        argv = ["init", "--job", JOB, "--from", source, *self.common[:4], "--store", str(self.w["store"]), *extra]
        return cli.main(argv)

    def run(self, capsys, until="deliver_check"):
        capsys.readouterr()
        assert cli.main(["run", JOB, "--until", until, *self.common, "--json"]) == 0
        return json.loads(capsys.readouterr().out)

    def event(self, number, **changes):
        s = store.JobStore(self.root, JOB)
        runs = {seg["id"]: render_stage.voice_runs(s, s.read_job())[seg["id"]] for seg in s.read_job()["segments"]}
        value = request(job_id=JOB, run_id=f"hatchet-run-{number:02d}", voice={"mode": "from_run", "runs": runs})
        value["inputs"] |= {
            "bundle_manifest_sha256": render_stage.sha256_file(self.w["bundle"] / "manifest.json"),
            "records_sha256": render_stage.tree_sha256(self.w["records"]),
        }
        return value | changes

    def preflight(self, number, **changes):
        path = self.root / f"request-{number}.json"
        path.write_text(json.dumps(self.event(number, **changes)))
        with mock.patch.dict(os.environ, ENV):
            return cli.main(["render-stage", "preflight", JOB, "--request", str(path), *self.common])

    def result(self, number, **changes):
        assert self.preflight(number, **changes) == 0
        return render_stage.result(self.event(number, **changes), store.JobStore(self.root, JOB), ENV)


def swap_slide(w):
    """Give slide-a another picture of the same size, as a producer's fix does."""
    b = w["bundle"]
    data = fixture.port().fixtures()["slide-b.png"]
    (b / "assets" / "slide-a.png").write_bytes(data)
    m = manifest(b)
    m["assets"][0]["sha256"] = render_stage.hashlib.sha256(data).hexdigest()
    set_manifest(b, m)


def ran(result):
    return [row["node"] for row in result["ran"]]


def test_one_slide_rerun_on_the_same_root_runs_only_compose_and_deliver_check(root, capsys):
    assert root.intake() == 0 and root.init() == 0
    first = root.run(capsys)
    assert "voice/intro" in ran(first) and "voice/result" in ran(first)
    render = root.result(1)
    cut = render["outputs"]["video_sha256"]

    s = store.JobStore(root.root, JOB)
    assert rerun.fix(s, DECISIONS[0], cut)["round"] == 1
    swap_slide(root.w)
    assert root.intake("--replace") == 0 and root.init("--replace") == 0
    second = root.run(capsys)
    assert ran(second) == ["compose", "deliver_check"]

    # The replaced intake took its preflight to history, so a rerun's new intake must run preflight again.
    assert not (root.out / "preflight.json").exists()
    assert refused(render_stage.result, root.event(2, rerun={"scope": "compose_only"}), s, ENV) == "intake_missing"

    value = root.result(2, rerun={"scope": "compose_only"})
    shown = value["rerun"]
    assert shown["ran"] == ["compose", "deliver_check"] and shown["compose_only"] is True
    assert shown["changed_keys"] == ["compose", "deliver_check"]
    assert shown["fix"]["answers_round"] == 1
    assert value["outputs"]["video_sha256"] != cut
    assert sorted(p.name.partition("--")[0] for p in (s.dir / "history").iterdir()) == ["intake"]


def test_a_campaign_round_on_a_slide_fix_does_not_re_voice(root, capsys):
    """No Softproxy id, and the proof runs through the real stages with the fake engine's sine voice."""
    assert root.intake() == 0 and root.init() == 0
    root.run(capsys)
    render = root.result(1)
    s = store.JobStore(root.root, JOB)
    voices = {seg["id"]: s.manifest(f"voice/{seg['id']}") for seg in s.read_job()["segments"]}

    assert cli.main(["campaign-bind", JOB, "--campaign", CAMPAIGN, "--root", str(root.root)]) == 0
    capsys.readouterr()
    assert cli.main(["findings", JOB, "--root", str(root.root)]) == 0
    assert json.loads(capsys.readouterr().out)["video_sha256"] == render["outputs"]["video_sha256"]
    cut = render["outputs"]["video_sha256"]
    out = rerun.machine_round(s, report_of("slide_not_shown", page="intro"), cut)
    assert out["round"] == 1 and ledger(s)["fixes"][0]["decision"] is None

    swap_slide(root.w)
    assert root.intake("--replace") == 0 and root.init("--replace") == 0
    second = root.run(capsys)
    assert ran(second) == ["compose", "deliver_check"]
    value = root.result(2, rerun={"scope": "compose_only"})
    assert value["rerun"]["ran"] == ["compose", "deliver_check"] and value["rerun"]["fix"]["answers_round"] == 1
    assert value["outputs"]["video_sha256"] != cut
    assert {seg: s.manifest(f"voice/{seg}") for seg in voices} == voices


def test_the_findings_of_a_real_root_are_typed_and_hold_a_real_lexical_finding(root, capsys):
    set_script(root.w["bundle"], "It did so across", "It did delve across")
    assert root.intake() == 0 and root.init() == 0
    root.run(capsys)
    root.result(1)
    shown = render_stage.job_findings(store.JobStore(root.root, JOB))
    assert findings.check(json.loads(json.dumps(shown)))["codes"] == shown["codes"]
    lexical = [row for row in shown["findings"] if row["code"] == "lexical_finding"]
    assert lexical and all(row["blocking"] is False and row["segment"] for row in lexical)
    assert "delve" not in json.dumps(shown)


def test_a_changed_beat_re_voices_alone_and_the_held_take_stays(root, capsys):
    assert root.intake() == 0 and root.init() == 0
    root.run(capsys)
    root.result(1)
    s = store.JobStore(root.root, JOB)
    intro = s.manifest("voice/intro")
    set_script(
        root.w["bundle"], "It did so across four hundred generated files.", "It read four hundred generated files."
    )
    assert root.intake("--replace") == 0 and root.init("--replace") == 0

    job = s.read_job()
    records_now = cli.load_records(root.out / "records")
    ctx = plain_ctx() | {"ffmpeg": cli.ffmpeg_identity()}
    value = mixed({"intro": intro["measurements"]["narrate_content_sha256"], "result": None}) | {"job_id": JOB}
    out = render_stage.takes(value, graph.plan(job, records_now, s, ctx), s, job, gpu_draft=True)
    assert out["takes"] == {"intro": "keep", "result": "revoice"} and out["revoice"] == ["result"]

    voiced = root.run(capsys, until="voice_qa")  # the fake engine stands in for the window
    assert ran(voiced) == ["script/result", "voice/result", "voice_qa/result"]
    planned = graph.plan(job, records_now, s, ctx)
    out = render_stage.takes(value, planned, s, job, gpu_draft=True, after=True)
    assert out["ready"] is True and out["takes"] == {"intro": "keep", "result": "revoiced"}

    root.run(capsys)
    shown = root.result(2, rerun={"scope": "any"})["rerun"]
    assert "voice/result" in shown["ran"] and "voice/intro" not in shown["ran"]
    assert s.manifest("voice/intro") == intro


def test_a_refused_re_intake_keeps_the_earlier_one(root):
    assert root.intake() == 0
    before = (root.out / "intake.json").read_bytes()
    set_script(root.w["bundle"], "forty two percent", "forty three percent")
    assert root.intake("--replace") == 1
    assert (root.out / "intake.json").read_bytes() == before


def test_replace_binds_the_same_job(root):
    assert root.intake() == 0
    before = (root.out / "intake.json").read_bytes()
    assert root.intake("--replace", "--job", "some-other-job") == 1
    assert (root.out / "intake.json").read_bytes() == before
    assert not (root.out.parent / "history").exists()


@pytest.mark.parametrize("fault", [OSError, KeyboardInterrupt])
def test_a_failed_swap_brings_the_earlier_intake_back(root, monkeypatch, fault):
    assert root.intake() == 0
    before = (root.out / "intake.json").read_bytes()
    real = bundle.os.rename

    def failing(source, target):
        if ".intake-" in str(source):
            raise fault("the swap failed")
        return real(source, target)

    with monkeypatch.context() as patch:
        patch.setattr(bundle.os, "rename", failing)
        if fault is OSError:
            assert root.intake("--replace") == 1
        else:
            with pytest.raises(KeyboardInterrupt):
                root.intake("--replace")
    assert (root.out / "intake.json").read_bytes() == before
    assert list((root.out.parent / "history").iterdir()) == []
    assert not list(root.out.parent.glob(".intake.intake-*"))


def test_replace_refuses_a_symlinked_intake_json(ws, tmp_path):  # noqa: F811
    out = tmp_path / "out"
    out.mkdir()
    (out / "elsewhere.json").write_text("{}")
    (out / "intake.json").symlink_to(out / "elsewhere.json")
    args = {"template": TEMPLATE, "voice": VOICE, "engine": ENGINE, "store": ws["store"], "replace": True}
    with pytest.raises(bundle.BundleError) as caught:
        bundle.intake(ws["bundle"], out, ws["records"], **args)
    assert caught.value.code == "out_exists"


def test_replace_takes_only_an_earlier_intake(ws, tmp_path):  # noqa: F811
    out = tmp_path / "out"
    out.mkdir()
    (out / "a-file").write_text("not an intake")
    args = {"template": TEMPLATE, "voice": VOICE, "engine": ENGINE, "store": ws["store"], "replace": True}
    with pytest.raises(bundle.BundleError) as caught:
        bundle.intake(ws["bundle"], out, ws["records"], **args)
    assert caught.value.code == "out_exists"
    assert sorted(p.name for p in out.iterdir()) == ["a-file"]
    assert not (tmp_path / "history").exists()


def test_a_re_intake_with_no_replace_still_refuses(root):
    assert root.intake() == 0
    assert root.intake() == 1


def test_the_cli_takes_path(root, capsys):
    assert root.intake() == 0 and root.init() == 0
    root.run(capsys)
    s = store.JobStore(root.root, JOB)
    held = s.manifest("voice/intro")["measurements"]["narrate_content_sha256"]
    path = root.root.parent / "request.json"
    path.write_text(json.dumps(mixed({"intro": held, "result": None}) | {"job_id": JOB}))
    argv = ["render-stage", "takes", JOB, "--request", str(path), *root.common[:6]]
    capsys.readouterr()
    assert cli.main([*argv, "--gpu-draft", "--after-window"]) == 0
    assert json.loads(capsys.readouterr().out)["takes"]["result"] == "revoiced"
    root.result(1)
    capsys.readouterr()
    assert cli.main(argv) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "gpu_window_not_v1"
    assert cli.main([*argv, "--gpu-draft"]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "revoice_unneeded"
    assert cli.main(["render-stage", "takes", "--request", str(path)]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "usage"
    assert cli.main([*argv, "--inputs", str(root.root)]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "usage"
    assert cli.main(["render-stage", "check", "--request", str(path), "--after-window"]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "usage"
