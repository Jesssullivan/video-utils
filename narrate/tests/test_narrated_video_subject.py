"""The guard subject and the current cut (docs/spec/NARRATED_VIDEO.md, "Guard subject and cut", Linear TIN-7788).

Every input is synthetic: the fixture workspace (narrate/video/fixture.py) and its committed example script, and the
accept tests' fake-runner job, whose compose writes a synthetic video.mp4. The decision id is a made-up ULID.
"""

import json

import pytest
import test_narrated_video_accept as accept_tests
from test_narrated_video_accept import GO, avatar_job, video_of  # noqa: F401  (pytest fixture)
from test_narrated_video_graph import example, new_store, records, stub_ctx

from narrate import adapters, spoken
from narrate.video import accept, cli, fixture, store, subject
from narrate.video.common import Env
from narrate.video.job import JobError, init_job, load_records


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """A fixture workspace, one simple job written into a store, and a CLI environment that targets them."""
    paths = fixture.write(tmp_path / "ws")
    records = load_records(paths["records"])
    env = Env(paths["records"], records, paths["store"], paths["lexical"])
    job = init_job("nv-subject", fixture.NARRATE_JOB, fixture.sha(paths["script"]), avatar=False)
    s = store.JobStore(tmp_path / "narrated", job["id"])
    s.write_job(job)
    for name, value in (
        ("NARRATED_VIDEO_ROOT", tmp_path / "narrated"),
        ("NARRATED_VIDEO_RECORDS", paths["records"]),
        ("NARRATE_STORE", paths["store"]),
        ("NARRATE_LEXICAL_DIR", paths["lexical"]),
    ):
        monkeypatch.setenv(name, str(value))
    monkeypatch.delenv("NARRATED_VIDEO_EXTERNALS", raising=False)
    return {"paths": paths, "records": records, "env": env, "job": job, "store": s}


def expected_narration(ws):
    kind = ws["records"]["jobs"][fixture.NARRATE_JOB]["input"]
    return spoken.lines(adapters.load(kind, ws["paths"]["script"]))


def test_the_subject_lists_the_voiced_text_then_the_ids_and_no_unset_label(ws):
    got = subject.subject(ws["job"], ws["records"], ws["env"], ws["store"])
    assert got["ok"] and got["job_id"] == "nv-subject"
    segment = ws["job"]["segments"][0]["id"]
    assert got["texts"] == [
        {"field": "narration", "text": expected_narration(ws)},
        {"field": "title", "text": "nv-subject"},
        {"field": "title", "text": segment},
    ]


def test_each_set_label_joins_the_subject_in_a_fixed_order(ws):
    job = ws["job"]
    job["labels"] = {"persona": "Synthetic narrator", "personaCue": "A synthetic voice", "extraNotice": "Fixture only"}
    fields = [(t["field"], t["text"]) for t in subject.texts(job, ws["records"], ws["env"], ws["store"])][3:]
    want = [("caption", "A synthetic voice"), ("description", "Fixture only"), ("label", "Synthetic narrator")]
    assert fields == want


def test_slide_page_ids_are_titles(ws):
    job = ws["job"]
    job["slides"] = {**(job["slides"] or {}), "pages": [{"id": "page-a", "startS": 0}, {"id": "page-b", "startS": 4}]}
    titles = [t["text"] for t in subject.texts(job, ws["records"], ws["env"], ws["store"]) if t["field"] == "title"]
    assert titles[-2:] == ["page-a", "page-b"]


def test_the_subject_leaves_no_scratch_in_the_job_directory(ws):
    before = sorted(p.name for p in ws["store"].dir.iterdir())
    subject.texts(ws["job"], ws["records"], ws["env"], ws["store"])
    assert sorted(p.name for p in ws["store"].dir.iterdir()) == before


def test_a_segment_with_an_unknown_narrate_job_refuses(ws):
    job = ws["job"]
    job["segments"][0]["narrateJob"] = "job-none"
    with pytest.raises(JobError) as exc:
        subject.texts(job, ws["records"], ws["env"], ws["store"])
    assert exc.value.code == "records_invalid"


def test_a_script_missing_from_the_store_refuses(ws):
    job = ws["job"]
    job["segments"][0]["scriptSha256"] = "0" * 64
    with pytest.raises(JobError) as exc:
        subject.texts(job, ws["records"], ws["env"], ws["store"])
    assert exc.value.code == "source_missing"


def test_a_script_that_does_not_load_refuses_without_quoting_it(ws):
    # adapters.py quotes the unreadable timing line, so run_script's detail would carry the script's own words here.
    script = ws["paths"]["store"] / "unreadable.srt"
    script.write_text("1\nsynthetic private words --> more of them\nhello\n", encoding="utf-8")
    digest = fixture.sha(script)
    ws["env"].index[digest] = script
    ws["records"]["jobs"][fixture.NARRATE_JOB]["input"] = "Srt"
    ws["job"]["segments"][0]["scriptSha256"] = digest
    with pytest.raises(JobError) as exc:
        subject.texts(ws["job"], ws["records"], ws["env"], ws["store"])
    assert exc.value.code == "input_invalid" and "synthetic private words" not in exc.value.detail


def test_a_subject_the_guard_would_refuse_as_too_large_refuses_first(ws, monkeypatch):
    monkeypatch.setattr(subject, "MAX_TEXT", 4)
    with pytest.raises(JobError) as exc:
        subject.texts(ws["job"], ws["records"], ws["env"], ws["store"])
    assert exc.value.code == "subject_too_large"


def call(capsys, argv):
    code = cli.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def test_cli_subject_prints_the_subject(ws, capsys):
    code, out, err = call(capsys, ["subject", "nv-subject", "--json"])
    assert code == 0 and err == ""
    assert json.loads(out) == subject.subject(ws["job"], ws["records"], ws["env"], ws["store"])


def test_cli_subject_without_a_store_refuses_typed(ws, capsys, monkeypatch):
    monkeypatch.delenv("NARRATE_STORE")
    code, out, err = call(capsys, ["subject", "nv-subject", "--json"])
    assert code == 1 and out == "" and json.loads(err)["refused"] == "store_missing"


def test_a_subject_text_counts_utf16_units_as_the_guard_does(ws, monkeypatch):
    # An astral code point is 1 Python character and 2 UTF-16 units, the length the Cade guard measures. The persona
    # below fits the limit in code points and exceeds it in units, so only a UTF-16 count refuses it.
    assert subject.utf16_units("\U0001f3b8") == 2 and subject.utf16_units("abc") == 3
    job = ws["job"]
    limit = max(subject.utf16_units(t["text"]) for t in subject.texts(job, ws["records"], ws["env"], ws["store"]))
    persona = "\U0001f3b8" * (limit // 2 + 1)
    assert len(persona) <= limit < subject.utf16_units(persona)
    job["labels"] = {**job["labels"], "persona": persona}
    monkeypatch.setattr(subject, "MAX_TEXT", limit)
    with pytest.raises(JobError) as exc:
        subject.texts(job, ws["records"], ws["env"], ws["store"])
    assert exc.value.code == "subject_too_large"


MACHINE_PASSED = {"profile": "passed", "loudness": "passed", "flash": "not_applicable", "captions": "passed"}


def test_the_cut_names_the_current_video_and_the_open_operator_gates(avatar_job):  # noqa: F811
    job, _, s = avatar_job
    got = subject.cut(s, job)
    render, _ = accept.render_of(s, job)
    pending = {"pending_operator": ["lip_sync", "listening"], "accepted": []}
    machine = {"machine_gates": MACHINE_PASSED, "internal_review_allowed": True}
    assert got == {"ok": True, "job_id": job["id"], **render, **machine, **pending}
    assert got["video_sha256"] == video_of(s)


def failed_job(tmp_path, monkeypatch, gate, value="failed"):
    """The avatar fixture job, settled with deliver_check reporting gate as value. deliver.delivery_gate computes the
    internal-review flag from the machine states, as the real stage does."""
    base = accept_tests.gates_for
    monkeypatch.setattr(accept_tests, "gates_for", lambda job, visible=None: base(job, visible) | {gate: value})
    job, recs = example("nv-fixture-avatar"), records()
    s = new_store(tmp_path, job)
    accept_tests.settle(job, recs, s, stub_ctx())
    return job, s


def swap_manifest(monkeypatch, s, manifest):
    """Serve manifest as the deliver_check manifest of s, and every other node's manifest from disk."""
    real = s.manifest
    monkeypatch.setattr(s, "manifest", lambda node: manifest if node == "deliver_check" else real(node))


@pytest.mark.parametrize("gate", ["flash", "loudness", "profile", "captions"])
def test_a_cut_whose_machine_gate_failed_refuses_and_names_the_gate(tmp_path, monkeypatch, gate):
    job, s = failed_job(tmp_path, monkeypatch, gate)
    delivery = s.manifest("deliver_check")["measurements"]["delivery_gate"]
    assert delivery["internal_review_allowed"] is False
    with pytest.raises(JobError) as exc:
        subject.cut(s, job)
    assert exc.value.code == "machine_gates_failed" and gate in exc.value.detail


def test_a_cut_refuses_when_deliver_check_withholds_internal_review(avatar_job, monkeypatch):  # noqa: F811
    # Every machine state passed, yet delivery_gate says no: the flag is deliver_check's own, so it wins.
    job, _, s = avatar_job
    manifest = s.manifest("deliver_check")
    manifest["measurements"]["delivery_gate"]["internal_review_allowed"] = False
    swap_manifest(monkeypatch, s, manifest)
    with pytest.raises(JobError) as exc:
        subject.cut(s, job)
    assert exc.value.code == "machine_gates_failed"


@pytest.mark.parametrize("drop", ["delivery_gate", "flash"])
def test_a_cut_without_its_machine_states_or_delivery_gate_refuses_invalid(avatar_job, monkeypatch, drop):  # noqa: F811
    job, _, s = avatar_job
    manifest = s.manifest("deliver_check")
    if drop == "delivery_gate":
        del manifest["measurements"]["delivery_gate"]
    else:
        del manifest["measurements"]["gates"]["flash"]
    swap_manifest(monkeypatch, s, manifest)
    with pytest.raises(JobError) as exc:
        subject.cut(s, job)
    assert exc.value.code == "deliver_check_invalid"


def test_cli_cut_of_a_failed_flash_gate_prints_only_the_refusal(tmp_path, monkeypatch, capsys):
    job, s = failed_job(tmp_path, monkeypatch, "flash")
    code, out, err = call(capsys, ["cut", job["id"], "--root", str(s.root)])
    assert code == 1 and out == ""
    refusal = json.loads(err)
    assert refusal["refused"] == "machine_gates_failed" and "flash" in refusal["detail"]


def test_an_acceptance_of_this_cut_closes_its_gate_in_the_cut(avatar_job):  # noqa: F811
    job, _, s = avatar_job
    accept.accept(s, "listening", GO, video_of(s))
    got = subject.cut(s, job)
    assert got["pending_operator"] == ["lip_sync"] and got["accepted"] == ["listening"]


def test_the_cut_of_a_job_with_no_deliver_check_refuses(ws):
    with pytest.raises(JobError) as exc:
        subject.cut(ws["store"], ws["job"])
    assert exc.value.code == "deliver_check_missing"


def test_cli_cut_prints_digests_and_gate_names_only(avatar_job, capsys):  # noqa: F811
    job, _, s = avatar_job
    code, out, _ = call(capsys, ["cut", job["id"], "--root", str(s.root)])
    got = json.loads(out)
    assert code == 0 and got == subject.cut(s, job)
    want = {"ok", "job_id", "deliver_check", "video_sha256", "machine_gates", "internal_review_allowed"}
    assert set(got) == want | {"pending_operator", "accepted"}
