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


# Review fixes (TIN-7564): policy at adoption, the used-voice binding, gates, the engine record, --replace, the no-op
# re-check and verify --result-line on an unreadable run.
def edit_records(w, name, edit):
    path = w["paths"]["records"] / name
    rows = json.loads(path.read_text())
    edit(rows)
    path.write_text(json.dumps(rows, indent=1))


def drop_consent_evidence(w):
    (consent,) = json.loads((w["paths"]["records"] / "consents.json").read_text())
    (path,) = [p for p in w["paths"]["store"].rglob("*") if p.is_file() and sha(p) == consent["evidenceSha256"]]
    path.unlink()


def hosted_engine(rows):
    rows[0].update(profile="Hosted", backend="Hosted", hosted=True)


@pytest.mark.parametrize(
    "drift, code",
    [
        (lambda w: edit_records(w, "consents.json", lambda r: r[0].update(scopes=["Other"])), "consent_scope"),
        (drop_consent_evidence, "consent_missing"),
        (lambda w: edit_records(w, "voices.json", lambda r: r[0].update(allowedEngines=[])), "engine_not_allowed"),
        (lambda w: edit_records(w, "engines.json", hosted_engine), "hosted_not_allowed"),
    ],
    ids=["consent-scope", "evidence-missing", "engine-not-allowed", "hosted-not-allowed"],
)
def test_adoption_admits_the_job_against_its_own_records_and_store_first(ws, capsys, drift, code):
    s = init(capsys, ws)
    drift(ws)
    code_, result, _ = adopt(capsys, "nv-adopt", ws["batch"])
    assert code_ == 1 and result["refused"] == code and result["recorded"] is False
    assert s.entry("voice/seg-1") is None
    assert not (s.node_dir("voice/seg-1").exists() and any(s.node_dir("voice/seg-1").iterdir()))


@pytest.mark.parametrize(
    "edit, field",
    [
        (lambda m: m["job"]["gates"].update(maxChunkWer=1.0, minSim=-1, maxTakes=99), "job.gates"),
        (lambda m: m["engine"]["knobs"].update(fit_speed_max=1.9), "engine.knobs"),
        (lambda m: m["engine"].update(model="other-model"), "engine.model"),
        (lambda m: m["engine"].update(sampleRateHz=8000), "engine.sampleRateHz"),
        (lambda m: m["engine"].update(backend="Fake2"), "engine.backend"),
        (lambda m: m["engine"].update(files=[{"path": "x", "sha256": "0" * 64}]), "engine.files"),
        (lambda m: m["voices"][0].update(speaker="Alice"), "voices: the run's {speaker: voice} map"),
        (lambda m: m["voices"].append(dict(m["voices"][0], speaker="Alice")), "voices: the run's {speaker: voice} map"),
        (lambda m: m["voices"][0].update(ref_text_sha256="0" * 64), "voices.voice-fixture-sine"),
        (lambda m: m["voices"][0].update(tempo=1.1), "voices.voice-fixture-sine"),
    ],
    ids=["gates", "knobs", "model", "rate", "backend", "files", "speaker", "extra-speaker", "ref-text", "tempo"],
)
def test_the_engine_record_gates_and_speaker_map_are_bound(ws, capsys, edit, field):
    init(capsys, ws)
    rewrite_manifest(ws["batch"], edit)
    code, result, _ = adopt(capsys, "nv-adopt", ws["batch"])
    assert code == 1 and result["refused"] == "voice_run_mismatch"
    assert f"key at {field}" in result["detail"]


def test_a_pinned_file_path_is_private_to_its_host_and_never_binds(ws, capsys):
    """Engine files bind by digest; the batch host's path for the same file does not refuse."""
    pinned = [{"path": "/elsewhere/audiocpp_cli", "sha256": "1" * 64}]
    edit_records(ws, "engines.json", lambda r: r[0].update(files=[{"path": "audiocpp_cli", "sha256": "1" * 64}]))
    init(capsys, ws)
    rewrite_manifest(ws["batch"], lambda m: m["engine"].update(files=pinned))
    code, result, err = adopt(capsys, "nv-adopt", ws["batch"])
    assert code == 0, (result, err)


def source_run(capsys, w, job_id):
    """Voice a source job through the stage's own render and copy its narrate run out of the store."""
    s = init(capsys, w, job_id)
    code, _, err = nv(capsys, "stage", job_id, "voice", "--segment", "seg-1", "--json")
    assert code == 0, err
    narration = s.dir / s.entry("voice/seg-1")["dir"] / speech.RUN
    target = w["batch"].parent / f"{job_id}-run"
    shutil.copytree(narration, target)
    return target, json.loads((narration / "manifest.json").read_text())


def test_a_named_speaker_the_script_leaves_out_does_not_refuse(ws, capsys):
    """The run lists the voices the script uses; a job that also names an unused speaker still adopts."""

    def second_voice(rows):
        rows.append(dict(rows[0], id="voice-fixture-two"))

    def speakers(rows):
        rows[0]["speakers"] = [{"speaker": "Guest", "voice": "voice-fixture-two"}]

    edit_records(ws, "voices.json", second_voice)
    edit_records(ws, "jobs.json", speakers)
    run_dir, manifest = source_run(capsys, ws, "nv-src2")
    assert [(v["speaker"], v["voice"]) for v in manifest["voices"]] == [(None, "voice-fixture-sine")]
    init(capsys, ws)
    code, result, err = adopt(capsys, "nv-adopt", run_dir)
    assert code == 0, (result, err)
    assert result["adopted"]["content_sha256"] == manifest["content_sha256"]


def test_voice_qa_scores_against_the_job_gates_never_the_run_gates(ws, capsys, monkeypatch, tmp_path):
    from narrate import evaluate

    seen = []

    def scored(run_dir, manifest, metrics, cfg, reference_voice, scorer):
        seen.append(manifest["job"]["gates"])
        return {}

    monkeypatch.setattr(evaluate, "scored", scored)
    monkeypatch.setenv("NARRATE_SCORER_LOCK", str(tmp_path / "scorer.lock"))
    s = init(capsys, ws)
    assert adopt(capsys, "nv-adopt", ws["batch"])[0] == 0
    # gates are outside the voice key: the voice node stays fresh and voice_qa reruns with the records' gates
    edit_records(ws, "jobs.json", lambda r: r[0]["gates"].update(maxChunkWer=0.05, minSim=0.5))
    code, _, err = nv(capsys, "stage", "nv-adopt", "voice_qa", "--segment", "seg-1", "--json")
    assert code == 0, err
    assert seen and seen[-1]["maxChunkWer"] == 0.05 and seen[-1]["minSim"] == 0.5
    qa_json = json.loads((s.dir / s.entry("voice_qa/seg-1")["dir"] / "qa.json").read_text())
    assert qa_json["gates"] == seen[-1]


def test_replace_checks_the_run_before_it_archives_the_held_node(ws, capsys):
    s = init(capsys, ws)
    assert adopt(capsys, "nv-adopt", ws["batch"])[0] == 0
    held = s.entry("voice/seg-1")
    empty = ws["batch"].parent / "empty-run"
    empty.mkdir()
    code, _, err = adopt(capsys, "nv-adopt", empty, "--replace")
    assert code == 1 and json.loads(err)["refused"] == "voice_run_manifest_missing"
    drifted = ws["batch"].parent / "drifted"
    shutil.copytree(ws["batch"], drifted)
    rewrite_manifest(drifted, lambda m: m["job"].update(seed=99))
    code, _, err = adopt(capsys, "nv-adopt", drifted, "--replace")
    assert code == 1 and json.loads(err)["refused"] == "voice_run_mismatch"
    assert s.entry("voice/seg-1") == held
    assert store.verify_stage_dir(s.dir / held["dir"]) == []


def test_adopting_the_held_run_again_re_checks_run_dir(ws, capsys):
    s = init(capsys, ws)
    assert adopt(capsys, "nv-adopt", ws["batch"])[0] == 0
    held = s.entry("voice/seg-1")
    take = next((ws["batch"] / "chunks").iterdir())
    take.write_bytes(take.read_bytes()[:-2] + b"\x00\x01")
    (ws["batch"] / "narration.wav").write_bytes(b"RIFF")
    code, _, err = adopt(capsys, "nv-adopt", ws["batch"])
    assert code == 1 and json.loads(err)["refused"] == "voice_run_unverified"
    assert s.entry("voice/seg-1") == held  # the node is unharmed


@pytest.mark.parametrize("manifest", [None, "[1, 2]", "{not json"], ids=["missing", "not-an-object", "unreadable"])
def test_verify_result_line_on_an_unreadable_manifest(tmp_path, capsys, manifest):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    if manifest is not None:
        (run_dir / "manifest.json").write_text(manifest)
    assert narrate_cli.main(["verify", str(run_dir), "--result-line"]) == 1
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    line = json.loads(out)
    assert line == {"ok": False, "run_id": None, "content_sha256": None, "reason": line["reason"]}
    assert line["reason"].startswith("manifest")


@pytest.fixture
def prerendered(ws, tmp_path, monkeypatch):
    """A real `narrate render --prerendered` run: the fixture records switched to an AudioCppBatch engine, narrate's
    plan, the batch through the fake audiocpp_cli (narrate/tests/fake_audiocpp.py) and the render that takes its
    WAVs. The fake binary runs only in the batch runner's test mode, so the run is then re-sealed as a non-test
    batch: the only edit is test_mode, which a real GPU window would have left false."""
    import stat
    import sys

    from test_prerender import FAKE, batch_engine, run_batch

    from narrate.config import Config
    from narrate.ir import sha256_file

    gpu = tmp_path / "gpu"
    gpu.mkdir()

    class Kit:
        binary, model = gpu / "audiocpp_cli", gpu / "voxcpm2-bf16.gguf"

    Kit.binary.write_text(f"#!{sys.executable}\n" + FAKE.read_text())
    Kit.binary.chmod(Kit.binary.stat().st_mode | stat.S_IXUSR)
    Kit.model.write_bytes(b"fake voxcpm2 weights; no model\n")
    Kit.binary_sha, Kit.model_sha = sha256_file(Kit.binary), sha256_file(Kit.model)
    engine = batch_engine(Kit)
    edit_records(ws, "engines.json", lambda rows: rows.append(engine))
    edit_records(ws, "voices.json", lambda rows: rows[0]["allowedEngines"].append(engine["id"]))
    edit_records(ws, "jobs.json", lambda rows: rows[0].update(engine=engine["id"]))
    records = ws["paths"]["records"]
    values = {
        "input": str(ws["paths"]["script"]),
        "job": str(records / "jobs.json"),
        "job_id": fixture.NARRATE_JOB,
        "engines": str(records / "engines.json"),
        "voices": str(records / "voices.json"),
        "consents": str(records / "consents.json"),
        "pronunciation": str(records / "pronunciation.json"),
        "store": str(ws["paths"]["store"]),
        "lexical": str(ws["paths"]["lexical"]),
        "out": str(tmp_path / "out"),
    }
    toml = tmp_path / "narrate.toml"
    toml.write_text("".join(f"{k} = {json.dumps(v)}\n" for k, v in values.items()))
    cfg = Config(toml)
    path, _ = render.plan(cfg, tmp_path / "plan", takes=1)
    monkeypatch.setenv("NARRATE_AUDIOCPP_BATCH_TEST_MODE", "1")
    monkeypatch.setenv("FAKE_AUDIOCPP_LOG", str(tmp_path / "argv.jsonl"))
    assert run_batch(Kit, path.parent) == [0]
    monkeypatch.delenv("NARRATE_AUDIOCPP_BATCH_TEST_MODE")
    final, manifest = render.render(cfg, prerendered=path.parent)
    assert manifest["engine"]["synthesis"]["mode"] == "out_of_process_batch"
    assert manifest["engine"]["knobs"] == {"fit_speed_max": 1.15, "audiocpp_clone": "ultimate"}

    def live(m):
        m["flags"].remove("prerendered_test_mode")
        m["engine"]["synthesis"]["test_mode"] = False
        for b in m["engine"]["synthesis"]["batches"]:
            b["test_mode"] = False

    batch = ws["batch"].parent / "prerendered"
    shutil.copytree(final, batch)
    return batch, rewrite_manifest(batch, live), final


def test_a_prerendered_audiocpp_batch_run_adopts_and_voice_qa_runs_on_it(ws, capsys, prerendered):
    batch, manifest, test_mode_run = prerendered
    s = init(capsys, ws)
    code, result, _ = adopt(capsys, "nv-adopt", test_mode_run)
    assert code == 1 and result["refused"] == "voice_run_test_mode"
    code, result, err = adopt(capsys, "nv-adopt", batch)
    assert code == 0, (result, err)
    assert result["adopted"]["content_sha256"] == manifest["content_sha256"]
    held = s.manifest("voice/seg-1")
    assert held["states"]["render"] == "adopted" and held["measurements"]["engine"] == manifest["engine"]["id"]
    code, _, err = nv(capsys, "stage", "nv-adopt", "voice_qa", "--segment", "seg-1", "--json")
    assert code == 0, err


@pytest.mark.parametrize(
    "edit, field",
    [
        (lambda m: m["engine"]["knobs"].update(audiocpp_clone="x"), "engine.knobs"),
        (lambda m: m["engine"].update(hfRevision="0" * 40), "engine.hfRevision"),
    ],
    ids=["clone-mode", "hf-revision"],
)
def test_a_prerendered_run_with_other_engine_settings_refuses(ws, capsys, prerendered, edit, field):
    batch, _, _ = prerendered
    init(capsys, ws)
    rewrite_manifest(batch, edit)
    code, result, _ = adopt(capsys, "nv-adopt", batch)
    assert code == 1 and result["refused"] == "voice_run_mismatch" and f"key at {field}" in result["detail"]
