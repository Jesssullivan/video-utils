"""`narrate video stage JOB voice --from-run RUN_DIR` (TIN-7564): adopt a narrate run rendered elsewhere, such as an
AudioCppBatch engine's `narrate render --prerendered`, as a job's voice node instead of voicing it again.

Every input is synthetic: the fixture workspace (narrate/video/fixture.py), the fake engine's sine voice and the
committed example script. The "batch" run is a narrate run the fake engine rendered for a source job; the tests copy
it out of that job's store, so it stands where `artifacts/narrate/<run_id>/` would. Whisper is pointed at a model that
does not exist, so WER stays not_measured.
"""

import json
import shutil
from pathlib import Path

import pytest

from narrate import __main__ as narrate_cli
from narrate import render, verify
from narrate.video import cli, fixture, run, speech, store
from narrate.video.common import Env
from narrate.video.job import init_job, load_records


@pytest.fixture(autouse=True)
def no_whisper(monkeypatch, tmp_path):
    monkeypatch.setenv("NARRATE_WHISPER_MODEL", str(tmp_path / "no-whisper-model.bin"))


def sha(path):
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def rendered(tmp_path_factory, ffmpeg):
    """A fixture workspace and one narrate run the fake engine rendered for job nv-src, copied out of its store."""
    with pytest.MonkeyPatch.context() as mp:
        base = tmp_path_factory.mktemp("adopt")
        for name in ("WHISPER_MODEL", "NARRATE_STORE", "NARRATE_LEXICAL_DIR", "NARRATE_SIM_MODEL"):
            mp.delenv(name, raising=False)
        mp.delenv("NARRATE_SIM_PYTHON", raising=False)
        mp.setenv("NARRATE_SCORER_LOCK", str(base / "scorer.lock"))
        mp.setenv("NARRATE_WHISPER_MODEL", str(base / "no-whisper-model.bin"))
        paths = fixture.write(base / "ws")
        records = load_records(paths["records"])
        env = Env(paths["records"], records, paths["store"], paths["lexical"])
        job = init_job("nv-src", fixture.NARRATE_JOB, sha(paths["script"]), avatar=False)
        s = store.JobStore(base / "narrated", job["id"])
        s.write_job(job)
        ctx = {"pin": None, "kitpip": None, "ffmpeg": cli.ffmpeg_identity(), "sources": set(env.index)}
        result, _ = run.run(run.RunContext(job, records, s, ctx, env), until="voice")
        assert result["ok"], result
        narration = s.dir / s.entry("voice/seg-1")["dir"] / speech.RUN
        manifest = json.loads((narration / "manifest.json").read_text())
        batch = base / "batch" / manifest["run_id"]
        shutil.copytree(narration, batch)
    return {"base": base, "paths": paths, "batch": batch, "manifest": manifest}


@pytest.fixture
def ws(rendered, tmp_path, monkeypatch):
    """A private copy of the workspace and the batch run, and a CLI that targets it."""
    shutil.copytree(rendered["base"] / "ws", tmp_path / "ws")
    batch = tmp_path / "batch" / rendered["batch"].name
    shutil.copytree(rendered["batch"], batch)
    paths = {k: tmp_path / "ws" / Path(v).relative_to(rendered["base"] / "ws") for k, v in rendered["paths"].items()}
    root = tmp_path / "narrated"
    for name, value in (
        ("NARRATED_VIDEO_ROOT", root),
        ("NARRATED_VIDEO_RECORDS", paths["records"]),
        ("NARRATE_STORE", paths["store"]),
        ("NARRATE_LEXICAL_DIR", paths["lexical"]),
    ):
        monkeypatch.setenv(name, str(value))
    monkeypatch.delenv("NARRATED_VIDEO_EXTERNALS", raising=False)
    monkeypatch.delenv("KITPIP_BIN", raising=False)
    return {"paths": paths, "batch": batch, "root": root, "manifest": rendered["manifest"]}


def nv(capsys, *argv):
    code = cli.main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def init(capsys, w, job_id="nv-adopt"):
    code, _, err = nv(
        capsys,
        "init",
        "--job",
        job_id,
        "--narrate-job",
        fixture.NARRATE_JOB,
        "--script",
        str(w["paths"]["script"]),
        "--no-avatar",
        "--json",
    )
    assert code == 0, err
    code, _, err = nv(capsys, "run", job_id, "--stages", "script", "--json")
    assert code == 0, err
    return store.JobStore(w["root"], job_id)


def adopt(capsys, job_id, run_dir, *extra):
    code, out, err = nv(capsys, "stage", job_id, "voice", "--from-run", str(run_dir), "--json", *extra)
    return code, (json.loads(out) if out.strip() else None), err


def rewrite_manifest(run_dir, edit):
    """Edit a run's manifest and re-seal content_sha256, so only the edited field can refuse it."""
    path = Path(run_dir) / "manifest.json"
    manifest = json.loads(path.read_text())
    edit(manifest)
    manifest["content_sha256"] = render.content_digest(manifest)
    path.write_text(json.dumps(manifest, indent=1))
    return manifest


def test_an_adopted_run_becomes_the_fresh_voice_node_and_voice_qa_runs_on_it(ws, capsys):
    s = init(capsys, ws)
    code, result, err = adopt(capsys, "nv-adopt", ws["batch"])
    assert code == 0, (result, err)
    assert [r["node"] for r in result["ran"]] == ["voice/seg-1"]
    assert result["states"]["voice/seg-1"] == "fresh"
    content = ws["manifest"]["content_sha256"]
    assert result["adopted"] == {
        "node": "voice/seg-1",
        "run_id": ws["manifest"]["run_id"],
        "content_sha256": content,
        "state": "adopted",
    }
    manifest = s.manifest("voice/seg-1")
    assert manifest["states"]["render"] == "adopted" and manifest["synthetic"] is True
    assert manifest["measurements"]["narrate_content_sha256"] == content
    assert manifest["measurements"]["adopted"] == {"run_id": ws["manifest"]["run_id"], "content_sha256": content}
    assert manifest["timeline"]["no_time_stretch"] is False and manifest["timeline"]["mapping"] == "narration_v1"
    assert manifest["labels"]["synthetic"] is True and manifest["labels"]["persona"] is None
    # the adopted copy carries no path of the source run in the stage manifest
    assert str(ws["batch"]) not in json.dumps(manifest)
    assert store.verify_stage_dir(s.dir / s.entry("voice/seg-1")["dir"]) == []
    assert verify.verify(s.dir / s.entry("voice/seg-1")["dir"] / speech.RUN)["ok"]
    code, _, err = nv(capsys, "stage", "nv-adopt", "voice_qa", "--segment", "seg-1", "--json")
    assert code == 0, err
    assert s.manifest("voice_qa/seg-1")["measurements"]["verified"] is True


def test_adopting_the_same_run_again_is_a_no_op_and_another_run_needs_replace(ws, capsys):
    init(capsys, ws)
    assert adopt(capsys, "nv-adopt", ws["batch"])[0] == 0
    code, result, _ = adopt(capsys, "nv-adopt", ws["batch"])
    assert code == 0 and result["ran"] == [] and result["adopted"]["state"] == "adopted"
    other = ws["batch"].parent / "other-run"
    shutil.copytree(ws["batch"], other)
    rewrite_manifest(other, lambda m: m.update(run_id="other-run"))  # run_id is volatile: the content is the same
    code, result, _ = adopt(capsys, "nv-adopt", other)
    assert code == 0 and result["ran"] == []
    flagged = ws["batch"].parent / "flagged"
    shutil.copytree(ws["batch"], flagged)
    rewrite_manifest(flagged, lambda m: m["flags"].append("loudness_off_target"))
    code, _, err = adopt(capsys, "nv-adopt", flagged)
    assert code == 1 and json.loads(err)["refused"] == "voice_already_fresh"
    code, result, err = adopt(capsys, "nv-adopt", flagged, "--replace")
    assert code == 0, err
    assert result["ran"][0]["node"] == "voice/seg-1"
    flags = store.JobStore(ws["root"], "nv-adopt").manifest("voice/seg-1")["measurements"]["flags"]
    assert "loudness_off_target" in flags


def test_a_tampered_take_refuses_voice_run_unverified_and_leaves_the_node_stale(ws, capsys):
    s = init(capsys, ws)
    take = next((ws["batch"] / "chunks").iterdir())
    take.write_bytes(take.read_bytes()[:-2] + b"\x00\x01")
    code, result, _ = adopt(capsys, "nv-adopt", ws["batch"])
    assert code == 1 and result["refused"] == "voice_run_unverified"
    assert result["recorded"] is False and "outputs" in result["detail"]
    assert result["states"]["voice/seg-1"] == "stale"
    assert s.entry("voice/seg-1") is None
    assert not list(s.node_dir("voice/seg-1").glob("*.partial"))


def test_a_manifest_whose_content_digest_differs_refuses(ws, capsys):
    init(capsys, ws)
    path = ws["batch"] / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["job"]["seed"] = 7  # not re-sealed
    path.write_text(json.dumps(manifest, indent=1))
    code, result, _ = adopt(capsys, "nv-adopt", ws["batch"])
    assert code == 1 and result["refused"] == "voice_run_unverified" and "content" in result["detail"]


@pytest.mark.parametrize(
    "edit, check",
    [
        (lambda m: m.update(synthetic=False), "manifest"),
        (lambda m: m["timeline"].update(no_time_stretch=True), "timeline"),
        (lambda m: m["timeline"].update(mapping="identity"), "timeline"),
        (lambda m: m.update(kind="condense_render"), "manifest"),
    ],
    ids=["synthetic-false", "no-time-stretch-true", "not-narration-v1", "wrong-kind"],
)
def test_wrong_manifest_flags_refuse_voice_run_unverified(ws, capsys, edit, check):
    init(capsys, ws)
    rewrite_manifest(ws["batch"], edit)
    code, result, _ = adopt(capsys, "nv-adopt", ws["batch"])
    assert code == 1 and result["refused"] == "voice_run_unverified"
    assert result["detail"].startswith(f"the narrate run does not verify: {check}")


def test_a_missing_manifest_refuses_before_anything_is_copied(ws, capsys):
    s = init(capsys, ws)
    (ws["batch"] / "manifest.json").unlink()
    code, result, _ = adopt(capsys, "nv-adopt", ws["batch"])
    assert code == 1 and result["refused"] == "voice_run_manifest_missing"
    code, result, _ = adopt(capsys, "nv-adopt", ws["batch"].parent / "no-such-run")
    assert code == 1 and result["refused"] == "voice_run_missing"
    assert s.entry("voice/seg-1") is None


def test_a_symlink_in_the_run_refuses_voice_run_invalid(ws, capsys):
    init(capsys, ws)
    (ws["batch"] / "extra.wav").symlink_to(ws["batch"] / "narration.wav")
    code, result, _ = adopt(capsys, "nv-adopt", ws["batch"])
    assert code == 1 and result["refused"] == "voice_run_invalid"


def test_a_run_under_the_guitar_runs_or_missing_a_recorded_field_refuses(ws, capsys, monkeypatch):
    from narrate import config

    init(capsys, ws)
    with monkeypatch.context() as mp:
        mp.setattr(config, "GUITAR_RUNS", ws["batch"].parent)
        code, result, _ = adopt(capsys, "nv-adopt", ws["batch"])
    assert code == 1 and result["refused"] == "voice_run_in_guitar_runs"
    rewrite_manifest(ws["batch"], lambda m: m.pop("loudness"))
    code, result, _ = adopt(capsys, "nv-adopt", ws["batch"])
    assert code == 1 and result["refused"] == "voice_run_invalid" and "loudness" in result["detail"]


@pytest.mark.parametrize(
    "edit",
    [
        lambda m: m["flags"].append("prerendered_test_mode"),
        lambda m: m["engine"].update(synthesis={"mode": "out_of_process_batch", "test_mode": True}),
    ],
    ids=["flag", "synthesis-record"],
)
def test_a_test_mode_batch_refuses_voice_run_test_mode(ws, capsys, edit):
    init(capsys, ws)
    rewrite_manifest(ws["batch"], lambda m: (edit(m), m["flags"].sort()))
    code, result, _ = adopt(capsys, "nv-adopt", ws["batch"])
    assert code == 1 and result["refused"] == "voice_run_test_mode"


@pytest.mark.parametrize(
    "edit, words",
    [
        ("fail", "failed their measured gate"),
        (lambda m: m["qa"]["chunks"].update(passed=m["qa"]["chunks"]["passed"] + 1), "qa.chunks differs"),
        (lambda m: m["input"].update(chunks=m["input"]["chunks"] + 1), "input.chunks differs"),
        (lambda m: m["chunks"][0]["qa"].update(status="skipped"), "no listed take or QA status"),
    ],
    ids=["failed-chunk", "counts", "input-chunks", "unknown-status"],
)
def test_a_chunk_gate_that_does_not_hold_refuses_voice_chunk_gate_failed(ws, capsys, edit, words):
    init(capsys, ws)

    def failed(m):
        was = m["chunks"][0]["qa"]["status"]
        m["chunks"][0]["qa"]["status"] = "failed"
        m["qa"]["chunks"][was] -= 1
        m["qa"]["chunks"]["failed"] += 1

    rewrite_manifest(ws["batch"], failed if edit == "fail" else edit)
    code, result, _ = adopt(capsys, "nv-adopt", ws["batch"])
    assert code == 1 and result["refused"] == "voice_chunk_gate_failed"
    assert words in result["detail"]


@pytest.mark.parametrize(
    "edit, field",
    [
        (lambda m: m["job"].update(seed=99), "job.seed"),
        (lambda m: m["job"].update(overrides={"voice": "voice-other"}), "job.overrides"),
        (lambda m: m["job"].update(id="job-other"), "job.id"),
        (lambda m: m["input"].update(sha256="0" * 64), "input.sha256"),
        (lambda m: m["engine"].update(id="engine-other"), "engine.id"),
        (lambda m: m["voices"][0].update(consent_id="consent-other"), "voices."),
        (lambda m: m["lexical"].update(release="xoxd-lexical@9.9.9"), "lexical.release"),
        (lambda m: m["pronunciation"].update(sha256="0" * 64), "pronunciation"),
    ],
    ids=["seed", "overrides", "job-id", "script", "engine", "consent", "lexical", "pronunciation"],
)
def test_a_run_that_differs_from_the_voice_key_refuses_voice_run_mismatch(ws, capsys, edit, field):
    init(capsys, ws)
    rewrite_manifest(ws["batch"], edit)
    code, result, _ = adopt(capsys, "nv-adopt", ws["batch"])
    assert code == 1 and result["refused"] == "voice_run_mismatch"
    assert f"key at {field}" in result["detail"]


def test_a_script_that_is_not_fresh_refuses_stage_input_stale(ws, capsys):
    code, _, err = nv(
        capsys,
        "init",
        "--job",
        "nv-cold",
        "--narrate-job",
        fixture.NARRATE_JOB,
        "--script",
        str(ws["paths"]["script"]),
        "--no-avatar",
    )
    assert code == 0, err
    code, result, _ = adopt(capsys, "nv-cold", ws["batch"])
    assert code == 1 and result["refused"] == "stage_input_stale"


def test_wrong_cli_flags_refuse_usage(ws, capsys):
    init(capsys, ws)
    code, _, err = nv(capsys, "stage", "nv-adopt", "mix", "--from-run", str(ws["batch"]))
    assert code == 1 and json.loads(err)["refused"] == "usage"
    code, _, err = nv(capsys, "stage", "nv-adopt", "voice_qa", "--segment", "seg-1", "--from-run", str(ws["batch"]))
    assert code == 1 and json.loads(err)["refused"] == "usage"
    code, _, err = nv(capsys, "stage", "nv-adopt", "voice", "--segment", "seg-1", "--replace")
    assert code == 1 and json.loads(err)["refused"] == "usage"
    code, result, err = adopt(capsys, "nv-adopt", ws["batch"], "--segment", "seg-9")
    assert code == 1 and result is None and json.loads(err)["refused"] == "node_unknown"


def test_narrate_render_and_verify_print_one_result_line(ws, capsys):
    want = {"ok": True, "run_id": ws["manifest"]["run_id"], "content_sha256": ws["manifest"]["content_sha256"]}
    assert narrate_cli.main(["verify", str(ws["batch"]), "--result-line"]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and json.loads(out) == want
    assert narrate_cli.main(["verify", str(ws["batch"])]) == 0
    assert json.loads(capsys.readouterr().out)["content_sha256"] == want["content_sha256"]
    (ws["batch"] / "narration.wav").write_bytes(b"RIFF")
    assert narrate_cli.main(["verify", str(ws["batch"]), "--result-line"]) == 1
    line = json.loads(capsys.readouterr().out)
    assert line["ok"] is False and line["content_sha256"] is None and line["reason"].startswith("outputs")
