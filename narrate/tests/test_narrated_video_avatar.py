"""The kitpip pin and the avatar stages (lane L5, docs/spec/NARRATED_VIDEO.md, "kitpip pin and the stub").

The public registration (program/externals.json) holds no pin values (NV-1). A private pin record names a commit and,
once a release binary exists, its digest; a pin whose digest is pending blocks the avatar stages. The executor runs
avatar and avatar_check through the kitpip wrapper on the synthetic stub, with the command shape of kitpip at the
pinned commit. Every input is generated or a committed synthetic fixture; no kitpip art or release binary is read.
"""

import copy
import hashlib
import json
import re
import shutil
import stat
from pathlib import Path

import pytest
from test_narrated_video_simple import Workspace, node_dir, ran

from narrate.video import cli, graph, kitpip, run, store
from narrate.video.job import JobError, init_job

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "narrated-video"
STUB = FIXTURES / "kitpip_stub.py"
EXTERNALS = FIXTURES / "kitpip-externals.json"
COMMIT = "c0" * 20  # a synthetic commit: the real pin is private (NV-1)
AVATAR = ("avatar/seg-1", "avatar_check/seg-1")


@pytest.fixture(autouse=True)
def no_whisper(monkeypatch, tmp_path):
    monkeypatch.setenv("NARRATE_WHISPER_MODEL", str(tmp_path / "no-whisper-model.bin"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fixture_record():
    return json.loads(EXTERNALS.read_text())


def write_record(tmp_path, record, name="externals.json"):
    path = tmp_path / name
    path.write_text(json.dumps(record))
    return path


def pending_record():
    """A private pin as L5 writes it before kitpip has a release binary: the commit, no digest."""
    record = fixture_record()
    pin = record["externals"]["kitpip"]
    pin.update(
        visibility="private",
        version="0.0.0",
        source_commit=COMMIT,
        gate_state=kitpip.PENDING,
        binaries={"kitpip": {}},
        default_rig={"id": "kitpip-v1", "revision": 2, "sha256": "e" * 64},
    )
    return record


def stub_ctx(ws, binary=STUB, record=EXTERNALS):
    pin = kitpip.load_pin(record)
    return ws.ctx() | {"pin": pin, "kitpip": kitpip.resolve(pin, {kitpip.BIN_ENV: str(binary)})}


def avatar_job(ws, job_id="nv-avatar", persona="fixture-persona"):
    job = init_job(job_id, "job-fixture-fake", sha(ws.paths["script"]), avatar=True, persona=persona)
    job["avatar"]["renderSize"] = 64
    return job


def run_job(ws, job, ctx, replace=False, **kwargs):
    s = ws.store(job, replace=replace)
    rc = run.RunContext(job, ws.records, s, ctx, ws.env)
    result, g = run.run(rc, **kwargs)
    return s, result, g


@pytest.fixture(scope="module")
def settled(tmp_path_factory, ffmpeg):
    """One avatar job run end to end once on the stub; tests copy it before changing it."""
    with pytest.MonkeyPatch.context() as mp:
        base = tmp_path_factory.mktemp("avatar")
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
        job = avatar_job(ws)
        s, result, g = run_job(ws, job, stub_ctx(ws))
    return {"ws": ws, "job": job, "result": result, "store": s}


# The public registration and the private pin --------------------------------------------------------------------
def test_the_public_registration_holds_no_pin_values():
    entry = kitpip.load_registry()
    assert entry["pin"] == "private_record" and entry["record_env"] == kitpip.EXTERNALS_ENV
    assert (entry["manifest_schema"], entry["timeline_mapping"]) == (kitpip.MANIFEST_SCHEMA, kitpip.MAPPING)
    assert entry["flake_input"] is False and entry["vendored"] is False
    assert not set(entry) & {"source_commit", "binaries", "default_rig", "version"}
    text = kitpip.REGISTRY.read_text()
    assert "://" not in text and not re.search(r"\b[0-9a-f]{40}\b", text)


@pytest.mark.parametrize("leak", ["source_commit", "binaries", "default_rig", "version"])
def test_a_registration_that_holds_a_pin_value_refuses(tmp_path, leak):
    record = json.loads(kitpip.REGISTRY.read_text())
    record["externals"]["kitpip"][leak] = "x"
    with pytest.raises(JobError) as caught:
        kitpip.load_registry(write_record(tmp_path, record))
    assert caught.value.code == "externals_invalid"


def test_a_pending_pin_names_the_commit_and_blocks_the_avatar_stages(tmp_path):
    pin = kitpip.load_pin(write_record(tmp_path, pending_record()))
    resolution = kitpip.resolve(pin, {kitpip.BIN_ENV: str(STUB)})
    assert resolution["state"] == "pending" and COMMIT[:12] in resolution["detail"]
    assert resolution["tool"]["binary_sha256"] is None
    check = kitpip.pin_check(pin, {kitpip.BIN_ENV: str(STUB)})
    assert check["ok"] is False and check["state"] == "pending"
    assert check["pin"]["source_commit"] == COMMIT and check["pin"]["gate_state"] == kitpip.PENDING


def mutated(edit):
    record = pending_record()
    edit(record["externals"]["kitpip"])
    return record


@pytest.mark.parametrize(
    "edit",
    [
        lambda p: p.update(source_commit=COMMIT[:8]),
        lambda p: p.update(source_commit=COMMIT.upper()),
        lambda p: p.update(gate_state="registered_hash_bound_not_accepted"),
        lambda p: p.update(visibility="public"),
        lambda p: p.update(fetch="https://" + "example.org/kitpip"),
        lambda p: p.update(resolve={"env": ["KITPIP_BIN"], "store": "/opt/kitpip/bin"}),
        lambda p: p.update(default_rig={"id": "kitpip-v1", "revision": 2}),
        lambda p: p["binaries"]["kitpip"].update({"x86_64-linux": {"sha256": "pending", "bytes": 1}}),
        lambda p: p["binaries"]["kitpip"].update({"x86_64-linux": {"sha256": "a" * 64, "bytes": 0}}),
        lambda p: p.pop("gate_state"),
    ],
)
def test_a_misshapen_pin_refuses(tmp_path, edit):
    with pytest.raises(JobError) as caught:
        kitpip.load_pin(write_record(tmp_path, mutated(edit)))
    assert caught.value.code == "externals_invalid"


def test_a_pin_with_a_release_digest_resolves_only_its_own_binary(tmp_path):
    record = pending_record()
    pin = record["externals"]["kitpip"]
    pin["gate_state"] = "registered_hash_bound_not_accepted"
    pin["binaries"]["kitpip"][kitpip.system()] = {"sha256": sha(STUB), "bytes": STUB.stat().st_size}
    loaded = kitpip.load_pin(write_record(tmp_path, record))
    assert kitpip.pin_check(loaded, {kitpip.BIN_ENV: str(STUB)})["state"] == "resolved"
    other = tmp_path / "other"
    other.write_bytes(STUB.read_bytes() + b"\n")
    assert kitpip.pin_check(loaded, {kitpip.BIN_ENV: str(other)})["state"] == "mismatch"
    assert kitpip.pin_check(None)["state"] == "unregistered"


def test_cli_pin_check_refuses_pending_and_passes_the_stub(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv(kitpip.BIN_ENV, str(STUB))
    pending = write_record(tmp_path, pending_record())
    assert cli.main(["pin-check", "--externals", str(pending)]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "kitpip_pin_pending"
    assert cli.main(["pin-check", "--externals", str(EXTERNALS)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True and out["pin"]["visibility"] == "test_fixture"
    monkeypatch.delenv(kitpip.EXTERNALS_ENV, raising=False)
    assert cli.main(["pin-check"]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "kitpip_pin_missing"


def test_plan_blocks_the_avatar_on_a_pending_pin_and_runs_the_rest(tmp_path, ffmpeg):
    ws = Workspace(tmp_path)
    job = avatar_job(ws, "nv-pending")
    ctx = stub_ctx(ws, record=write_record(tmp_path, pending_record()))
    s, result, g = run_job(ws, job, ctx)
    rows = {n["id"]: n for n in g["nodes"]}
    assert {(rows[n]["state"], rows[n]["reason"]) for n in AVATAR} == {("blocked", "kitpip_pin_pending")}
    assert rows["mix"]["state"] == "fresh" and g["admit"]["verdict"] == "Admitted"
    assert result["ok"] is False and result["refused"] == "kitpip_pin_pending"


# The executor's avatar stages -----------------------------------------------------------------------------------
def test_run_renders_and_checks_the_avatar_per_segment(settled):
    result, s = settled["result"], settled["store"]
    assert result["ok"] is True and "refused" not in result
    assert set(AVATAR) <= set(ran(result))
    assert {n: result["states"][n] for n in AVATAR} == {n: "fresh" for n in AVATAR}
    assert result["waiting_on_lane"] == {"compose": "L6", "deliver_check": "L6"}
    assert all(problems == [] for problems in s.verify().values())
    avatar = s.manifest("avatar/seg-1")
    assert avatar["knobs"]["persona"] == "fixture-persona" and avatar["knobs"]["renderSize"] == 64
    assert avatar["labels"] == {
        "synthetic": True,
        "consent_ids": ["consent-fixture-sine"],
        "voice_ids": s.manifest("voice/seg-1")["labels"]["voice_ids"],
        "persona": "fixture-persona",
    }
    assert avatar["timeline"]["mapping"] == "avatar_overlay_v1" and avatar["timeline"]["no_time_stretch"] is False
    assert avatar["measurements"]["fps"] == s.manifest("base")["measurements"]["fps"]
    assert avatar["measurements"]["size"] == {"w": 64, "h": 64} and avatar["measurements"]["show_badge"] is False
    assert avatar["states"] == {"source_checks": "passed", "render": "stub", "lip_sync": "pending_operator"}
    voice_run = node_dir(s, "voice/seg-1") / "narration"
    assert not (voice_run / "analyze").exists() and not (voice_run / "overlay").exists()
    checked = s.manifest("avatar_check/seg-1")
    receipt = json.loads((node_dir(s, "avatar_check/seg-1") / "check.json").read_text())
    assert receipt["labelled"] is True and receipt["frames_sha256"] == avatar["measurements"]["frames_sha256"]
    assert receipt["avatar_content_sha256"] == avatar["content_sha256"]
    assert checked["labels"] == avatar["labels"] and checked["states"]["lip_sync"] == "pending_operator"


def test_a_second_run_runs_nothing(settled):
    ws, job = settled["ws"], settled["job"]
    _, result, _ = run_job(ws, job, stub_ctx(ws), replace=True)
    assert result["ran"] == [] and result["ok"] is True


@pytest.fixture
def copied(settled, tmp_path):
    shutil.copytree(settled["ws"].base, tmp_path / "copy")
    ws = Workspace.__new__(Workspace)
    ws.base = tmp_path / "copy"
    ws.paths = {
        "records": ws.base / "ws" / "records",
        "store": ws.base / "ws" / "store",
        "lexical": ws.base / "ws" / "lexical",
        "script": ws.base / "ws" / "store" / "script.md",
    }
    ws.reload()
    return ws, copy.deepcopy(settled["job"])


def test_a_persona_change_reruns_the_avatar_and_the_chain_holds(copied):
    ws, job = copied
    job["labels"]["persona"] = "fixture-persona-b"
    s, result, _ = run_job(ws, job, stub_ctx(ws), replace=True)
    assert set(ran(result)) == {"place", "mix", *AVATAR}
    assert s.manifest("avatar/seg-1")["labels"]["persona"] == "fixture-persona-b"
    assert s.manifest("avatar_check/seg-1")["labels"]["persona"] == "fixture-persona-b"


def test_a_compose_knob_reruns_no_avatar(copied):
    ws, job = copied
    job["avatar"]["width"] = 0.18
    _, result, g = run_job(ws, job, stub_ctx(ws), replace=True)
    assert result["ran"] == [] and {n["id"]: n["state"] for n in g["nodes"]}["avatar/seg-1"] == "fresh"


def test_a_segment_switched_off_selects_no_avatar(copied):
    ws, job = copied
    job["segments"][0]["avatar"] = False
    _, result, _ = run_job(ws, job, stub_ctx(ws), replace=True)
    assert {result["states"][n] for n in AVATAR} == {"not_selected"}


def logging_wrapper(tmp_path):
    """A pinned wrapper that logs each argv to a file and then runs the stub."""
    log = tmp_path / "argv.jsonl"
    binary = tmp_path / "kitpip-logged"
    binary.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{log}'\nexec '{STUB}' \"$@\"\n")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    record = fixture_record()
    record["externals"]["kitpip"]["binaries"]["kitpip"]["any"] = {"sha256": sha(binary), "bytes": binary.stat().st_size}
    return binary, write_record(tmp_path, record, "logged.json"), log


def test_the_wrapper_speaks_kitpips_command_shape(tmp_path, ffmpeg):
    ws = Workspace(tmp_path / "w")
    binary, record, log = logging_wrapper(tmp_path)
    _, result, _ = run_job(ws, avatar_job(ws, "nv-argv"), stub_ctx(ws, binary, record))
    assert result["ok"] is True
    lines = log.read_text().splitlines()
    analyze, render, verify, check = (line.split() for line in lines)
    assert analyze[0] == "analyze" and analyze[analyze.index("--rig") + 1] == "kitpip-stub-rig"
    assert analyze[analyze.index("--fps") + 1] == "30/1"
    assert render[0] == "render" and render[render.index("--size") + 1] == "64x64"
    assert render[render.index("--encode") + 1] == "mov"
    assert verify[0] == check[0] == "verify" and check[1].endswith("/overlay")
    assert not any(flag in line for line in lines for flag in kitpip.FORBIDDEN_FLAGS)


def test_avatar_check_refuses_an_overlay_whose_frames_or_labels_changed(copied, monkeypatch):
    ws, job = copied
    real = kitpip.call

    def lying(resolution, pin, args, timeout_s=kitpip.TIMEOUT_S):
        out = real(resolution, pin, args, timeout_s)
        return out | {"frames_sha256": "0" * 64} if args[0] == "verify" else out

    s = ws.store(job, replace=True)
    s.archive("avatar_check/seg-1")
    monkeypatch.setattr(kitpip, "call", lying)
    _, result, g = run_job(ws, job, stub_ctx(ws), replace=True)
    assert result["refused"] == "label_chain_broken" and result["node"] == "avatar_check/seg-1"
    assert result["recorded"] is True
    assert {n["id"]: n["state"] for n in g["nodes"]}["avatar_check/seg-1"] == "refused"

    def unlabelled(resolution, pin, args, timeout_s=kitpip.TIMEOUT_S):
        out = real(resolution, pin, args, timeout_s)
        return out | {"labelled": False} if args[0] == "verify" else out

    monkeypatch.setattr(kitpip, "call", unlabelled)
    s.clear_refusal("avatar_check/seg-1")
    _, result, _ = run_job(ws, job, stub_ctx(ws), replace=True)
    assert result["refused"] == "kitpip_unlabelled"


def test_a_missing_kitpip_binary_blocks_only_the_avatar(tmp_path, ffmpeg):
    ws = Workspace(tmp_path)
    job = avatar_job(ws, "nv-nobin")
    _, result, g = run_job(ws, job, stub_ctx(ws, binary=tmp_path / "absent"))
    rows = {n["id"]: n for n in g["nodes"]}
    assert {(rows[n]["state"], rows[n]["reason"]) for n in AVATAR} == {("blocked", "kitpip_missing")}
    assert rows["mix"]["state"] == "fresh"


def test_the_stage_command_runs_one_avatar_node(copied):
    ws, job = copied
    s = ws.store(job, replace=True)
    s.archive("avatar/seg-1")
    rc = run.RunContext(job, ws.records, s, stub_ctx(ws), ws.env)
    result, _ = run.run(rc, only="avatar/seg-1")
    assert ran(result) == ["avatar/seg-1"] and result["states"]["avatar/seg-1"] == "fresh"
    assert store.verify_stage_dir(node_dir(s, "avatar/seg-1")) == []
    assert graph.BY_ID["avatar"].mapping == kitpip.MAPPING
