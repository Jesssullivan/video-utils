"""The guard subject and the current cut (docs/spec/NARRATED_VIDEO.md, "Guard subject and cut", Linear TIN-7788).

Every input is synthetic: the fixture workspace (narrate/video/fixture.py) and its committed example script, and the
accept tests' fake-runner job, whose compose writes a synthetic video.mp4. The decision id is a made-up ULID.
"""

import json

import pytest
from test_narrated_video_accept import GO, avatar_job, video_of  # noqa: F401  (pytest fixture)

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


def test_the_cut_names_the_current_video_and_the_open_operator_gates(avatar_job):  # noqa: F811
    job, _, s = avatar_job
    got = subject.cut(s, job)
    render, _ = accept.render_of(s, job)
    pending = {"pending_operator": ["lip_sync", "listening"], "accepted": []}
    assert got == {"ok": True, "job_id": job["id"], **render, **pending}
    assert got["video_sha256"] == video_of(s)


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
    assert set(got) == {"ok", "job_id", "deliver_check", "video_sha256", "pending_operator", "accepted"}
