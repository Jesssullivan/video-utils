"""The VRM offline renderer, the second avatar external (docs/spec/NARRATED_VIDEO.md, "VRM external", SPR-128).

The public registration holds no pin value. The avatar.manifest/v1 schema reads kitpip.manifest/v0 as renderer kind
kitpip, so kitpip overlays keep working. A VRM overlay is drawn from a face.timeline/v1 on the narration clock by a
pinned renderer that writes raw RGBA to a pipe; its manifest records the model digest, its VRM meta licence fields,
the renderer, the GPU and driver, and frames_identity per_host. The VRM path refuses without its likeness consent
(SP-R13) and appearance approval (TIN-7130) and leaves the burned-in badge decision open.

Every input is generated: a synthetic GLB with VRM meta and no mesh, the fake engine's sine narration and a stub
renderer with no browser. No real .vrm, three.js, Chromium or GPU is used.
"""

import copy
import hashlib
import importlib.util
import json
import re
import shutil
from pathlib import Path

import pytest
from test_narrated_video_simple import Workspace, node_dir, ran

from narrate.video import admit, avatar_manifest, cli, face, graph, kitpip, run, vrm
from narrate.video.job import JobError, init_job

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "narrated-video"
STUB = FIXTURES / "vrm_renderer_stub.py"
EXTERNALS = FIXTURES / "vrm-externals.json"
KITPIP_EXTERNALS = FIXTURES / "kitpip-externals.json"
AVATAR = ("avatar/seg-1", "avatar_check/seg-1")
COMMIT = "c1" * 20


def load_fixture_module():
    spec = importlib.util.spec_from_file_location("vrm_rig_fixture", FIXTURES / "vrm_rig_fixture.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rig = load_fixture_module()


@pytest.fixture(autouse=True)
def no_whisper(monkeypatch, tmp_path):
    monkeypatch.setenv("NARRATE_WHISPER_MODEL", str(tmp_path / "no-whisper-model.bin"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fixture_record():
    return json.loads(EXTERNALS.read_text())


def write_record(tmp_path, record, name="vrm-externals.json"):
    path = tmp_path / name
    path.write_text(json.dumps(record))
    return path


def vrm_ctx(ws, binary=STUB, record=EXTERNALS):
    pin = vrm.load_pin(record)
    return ws.ctx() | {"vrm_pin": pin, "vrm": vrm.resolve(pin, {vrm.BIN_ENV: str(binary)})}


def add_model(ws, spec="1.0", edit=None):
    """Put a synthetic model in the store and its record in avatars.json. edit(record) changes the record."""
    data = rig.model(spec)
    (ws.paths["store"] / "fixture.vrm").write_bytes(data)
    record = rig.record(data)
    if edit is not None:
        edit(record)
    (ws.paths["records"] / "avatars.json").write_text(json.dumps([record], indent=1))
    ws.reload()
    return record


def vrm_job(ws, job_id="nv-vrm", persona="fixture-persona"):
    job = init_job(job_id, "job-fixture-fake", sha(ws.paths["script"]), avatar=True, persona=persona)
    job["avatar"].update(external="vrm", rig=rig.FIXTURE_ID, renderSize=64)
    return job


def run_job(ws, job, ctx, replace=False, **kwargs):
    s = ws.store(job, replace=replace)
    rc = run.RunContext(job, ws.records, s, ctx, ws.env)
    result, g = run.run(rc, **kwargs)
    return s, result, g


def plan(ws, job, ctx):
    return graph.plan(job, ws.records, ws.store(job, replace=True), ctx)


@pytest.fixture(scope="module")
def settled(tmp_path_factory, ffmpeg):
    """One VRM job run end to end once on the stub renderer; tests copy it before changing it."""
    with pytest.MonkeyPatch.context() as mp:
        base = tmp_path_factory.mktemp("vrm")
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
        add_model(ws)
        job = vrm_job(ws)
        s, result, g = run_job(ws, job, vrm_ctx(ws))
    return {"ws": ws, "job": job, "result": result, "store": s, "graph": g}


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


def pinned_script(tmp_path, body):
    """A wrapper script around the stub and a test-only record that pins it."""
    binary = tmp_path / "vrm-wrapper"
    binary.write_text(body)
    binary.chmod(0o755)
    record = fixture_record()
    record["externals"]["vrm"]["binaries"]["vrm-renderer"]["any"] = {
        "sha256": sha(binary),
        "bytes": binary.stat().st_size,
    }
    return binary, write_record(tmp_path, record, "wrapped.json")


# The registration and the pin -----------------------------------------------------------------------------------
def test_the_public_registration_holds_no_pin_values():
    entry = vrm.load_registry()
    assert entry["pin"] == "private_record" and entry["record_env"] == vrm.EXTERNALS_ENV
    assert (entry["manifest_schema"], entry["timeline_mapping"], entry["face_schema"]) == (
        "avatar.manifest/v1",
        "avatar_overlay_v1",
        "face.timeline/v1",
    )
    assert entry["flake_input"] is False and entry["vendored"] is False and entry["fetch"] == "explicit"
    assert "vrm.update(1/fps)" in entry["engine"]["primary"] and "Blender" in entry["engine"]["fallback"]
    assert "per_host" in entry["frames_identity"]
    assert set(entry["gates"]) == {"likeness_consent", "appearance_approval", "edition", "badge"}
    text = vrm.REGISTRY.read_text()
    assert "://" not in text and not re.search(r"\b[0-9a-f]{40}\b", text)
    kitpip_entry = kitpip.load_registry()
    assert kitpip_entry["manifest_schemas"] == ["kitpip.manifest/v0", "avatar.manifest/v1"]


@pytest.mark.parametrize("leak", ["source_commit", "binaries", "version", "engine_lock_sha256"])
def test_a_registration_that_holds_a_pin_value_refuses(tmp_path, leak):
    record = json.loads(vrm.REGISTRY.read_text())
    record["externals"]["vrm"][leak] = "x"
    with pytest.raises(JobError) as caught:
        vrm.load_registry(write_record(tmp_path, record, "registry.json"))
    assert caught.value.code == "externals_invalid"


def test_the_fixture_pin_names_the_stub_and_resolves_it():
    pin = vrm.load_pin(EXTERNALS)
    want = pin["binaries"]["vrm-renderer"]["any"]
    assert (want["sha256"], want["bytes"]) == (sha(STUB), STUB.stat().st_size)
    assert vrm.resolve(pin, {vrm.BIN_ENV: str(STUB)})["state"] == "resolved"
    assert vrm.pin_check(pin, {vrm.BIN_ENV: str(STUB)})["ok"] is True
    assert vrm.load_pin(KITPIP_EXTERNALS) is None  # a record that pins only kitpip pins no vrm renderer
    assert kitpip.load_pin(EXTERNALS, required=False) is None


def pending_record():
    record = fixture_record()
    record["externals"]["vrm"].update(
        visibility="private",
        version="0.0.0",
        source_commit=COMMIT,
        gate_state=vrm.PENDING,
        engine={"kind": "three-vrm-chromium", "lock_sha256": "d" * 64},
        binaries={"vrm-renderer": {}},
    )
    return record


def mutated(edit):
    record = pending_record()
    edit(record["externals"]["vrm"])
    return record


@pytest.mark.parametrize(
    "edit",
    [
        lambda p: p.update(source_commit=COMMIT[:8]),
        lambda p: p.update(gate_state="registered_hash_bound_not_accepted"),
        lambda p: p.update(visibility="public"),
        lambda p: p.update(renderer_kind="kitpip"),
        lambda p: p.update(manifest_schema="kitpip.manifest/v0"),
        lambda p: p.update(face_schema="face.timeline/v0"),
        lambda p: p.update(engine={"kind": "unity", "lock_sha256": "d" * 64}),
        lambda p: p.update(engine={"kind": "three-vrm-chromium", "lock_sha256": None}),
        lambda p: p.update(engine={"kind": "stub", "lock_sha256": "d" * 64}),
        lambda p: p.update(fetch="https://" + "example.org/renderer"),
        lambda p: p.update(resolve={"env": ["VRM_RENDERER_BIN"], "store": "/opt/renderer"}),
        lambda p: p["binaries"]["vrm-renderer"].update({"x86_64-linux": {"sha256": "a" * 64, "bytes": 0}}),
        lambda p: p.pop("engine"),
    ],
)
def test_a_misshapen_pin_refuses(tmp_path, edit):
    with pytest.raises(JobError) as caught:
        vrm.load_pin(write_record(tmp_path, mutated(edit)))
    assert caught.value.code == "externals_invalid"


def test_a_pending_pin_names_the_commit(tmp_path):
    pin = vrm.load_pin(write_record(tmp_path, pending_record()))
    resolution = vrm.resolve(pin, {vrm.BIN_ENV: str(STUB)})
    assert resolution["state"] == "pending" and COMMIT[:12] in resolution["detail"]
    check = vrm.pin_check(pin, {vrm.BIN_ENV: str(STUB)})
    assert check["ok"] is False and check["pin"]["engine"]["kind"] == "three-vrm-chromium"


def test_cli_pin_check_takes_the_vrm_external(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv(vrm.BIN_ENV, str(STUB))
    assert cli.main(["pin-check", "--external", "vrm", "--externals", str(EXTERNALS)]) == 0
    assert json.loads(capsys.readouterr().out)["pin"]["visibility"] == "test_fixture"
    pending = write_record(tmp_path, pending_record())
    assert cli.main(["pin-check", "--external", "vrm", "--externals", str(pending)]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "vrm_pin_pending"
    assert cli.main(["pin-check", "--external", "vrm", "--externals", str(KITPIP_EXTERNALS)]) == 1
    assert json.loads(capsys.readouterr().err)["refused"] == "vrm_pin_missing"


# avatar.manifest/v1 and kitpip.manifest/v0 ----------------------------------------------------------------------
def kitpip_v0():
    return {
        "schema": "kitpip.manifest/v0",
        "kind": "avatar_overlay",
        "synthetic": True,
        "consent_ids": ["c"],
        "voice_ids": ["v"],
        "rig": {"id": "kitpip-stub-rig", "revision": 0, "sha256": "c" * 64},
        "rate": {"num": 30, "den": 1},
        "size": {"w": 64, "h": 64},
        "frames": 3,
        "frames_sha256": "f" * 64,
        "outputs": [],
    }


def vrm_v1():
    return {
        "schema": "avatar.manifest/v1",
        "kind": "avatar_overlay",
        "synthetic": True,
        "show_badge": False,
        "badge": {"burned_in": False, "decision": "open"},
        "consent_ids": ["c"],
        "voice_ids": ["v"],
        "likeness_consent_id": "likeness-fixture",
        "approval": {"ref": "TIN-7130", "evidence_sha256": "e" * 64},
        "rig": {"id": "m", "sha256": "a" * 64},
        "vrm": {"sha256": "a" * 64, "bytes": 10, "spec_version": "1.0", "meta": {"licenseUrl": "x"}},
        "renderer": {
            "kind": "vrm",
            "name": "r",
            "version": "1",
            "engine": {"kind": "stub"},
            "gpu": {"vendor": "v", "renderer": "r", "driver": "d"},
        },
        "rate": {"num": 30, "den": 1},
        "size": {"w": 64, "h": 64},
        "frames": 3,
        "frames_sha256": "f" * 64,
        "frames_identity": "per_host",
        "face": {"schema": "face.timeline/v1", "sha256": "b" * 64, "clock": "narration_output"},
        "outputs": [],
        "timeline": {"mapping": "avatar_overlay_v1", "no_time_stretch": False, "clock": "narration_output"},
    }


def test_v0_reads_as_a_kitpip_overlay_and_v1_names_its_renderer():
    seen = avatar_manifest.view(kitpip_v0(), "kitpip")
    assert seen["renderer_kind"] == "kitpip" and seen["frames_identity"] == "unstated"
    v1_kitpip = kitpip_v0() | {
        "schema": "avatar.manifest/v1",
        "renderer": {"kind": "kitpip", "name": "kitpip", "version": "0.2.0"},
        "frames_identity": "bit_exact",
        "timeline": {"mapping": "avatar_overlay_v1", "no_time_stretch": False, "clock": "narration_output"},
    }
    assert avatar_manifest.view(v1_kitpip, "kitpip")["frames_identity"] == "bit_exact"
    assert avatar_manifest.view(vrm_v1(), "vrm")["renderer"]["gpu"]["driver"] == "d"
    with pytest.raises(JobError) as caught:
        avatar_manifest.view(vrm_v1(), "kitpip")
    assert caught.value.code == "avatar_manifest_invalid"


@pytest.mark.parametrize(
    "edit",
    [
        lambda m: m.update(schema="avatar.manifest/v2"),
        lambda m: m["renderer"].update(kind="unity"),
        lambda m: m["renderer"].pop("gpu"),
        lambda m: m["renderer"]["gpu"].update(driver=""),
        lambda m: m.update(frames_identity="bit_exact"),
        lambda m: m["vrm"].update(sha256="9" * 64),
        lambda m: m["vrm"].pop("meta"),
        lambda m: m["face"].update(clock="base"),
        lambda m: m.pop("likeness_consent_id"),
        lambda m: m["approval"].pop("evidence_sha256"),
        lambda m: m.update(badge={"burned_in": True, "decision": "ruled"}),
        lambda m: m.update(show_badge=True),
        lambda m: m["timeline"].update(no_time_stretch=True),
        lambda m: m.update(frames=0),
    ],
)
def test_a_vrm_manifest_missing_a_required_record_refuses(edit):
    manifest = vrm_v1()
    edit(manifest)
    with pytest.raises(JobError) as caught:
        avatar_manifest.view(manifest, "vrm")
    assert caught.value.code == "avatar_manifest_invalid"


# The face timeline ----------------------------------------------------------------------------------------------
def tiny_face(frames=3):
    track = [face.neutral(i) for i in range(frames)]
    narration = {"run_id": "r", "content_sha256": "0" * 64, "narration_sha256": "1" * 64}
    return {
        "schema": face.SCHEMA,
        "clock": face.CLOCK,
        "fps": {"num": 30, "den": 1},
        "frames": frames,
        "source": "loudness_envelope",
        "narration": narration,
        "track": track,
    }


@pytest.mark.parametrize(
    "edit",
    [
        lambda f: f.update(clock="base"),
        lambda f: f.update(fps={"num": 25, "den": 1}),
        lambda f: f.update(frames=4),
        lambda f: f["track"][1].update(i=2),
        lambda f: f["track"][0]["mouth"].update(viseme="mbp"),
        lambda f: f["track"][0]["mouth"].update(weight=1.5),
        lambda f: f["track"][0].update(blink=[0.0]),
        lambda f: f["track"][0]["mood"].update(smug=0.5),
        lambda f: f["track"][0].update(head=[0, 0, 200]),
        lambda f: f["narration"].update(run_id="other"),
        lambda f: f.update(source="aligner"),
    ],
)
def test_a_malformed_face_timeline_refuses(edit):
    doc = tiny_face()
    face.validate(copy.deepcopy(doc), {"num": 30, "den": 1}, {"run_id": "r", "content_sha256": "0" * 64})
    edit(doc)
    with pytest.raises(JobError) as caught:
        face.validate(doc, {"num": 30, "den": 1}, {"run_id": "r", "content_sha256": "0" * 64})
    assert caught.value.code == "face_timeline_invalid"


def test_the_blink_schedule_is_fixed_by_frame_index():
    fps = {"num": 30, "den": 1}
    closures = [face.blink_closure(i, fps) for i in range(300)]
    assert closures[:39] == [0] * 39 and closures[39:42] == [0.6, 1.0, 0.6]
    assert closures == [face.blink_closure(i, fps) for i in range(300)]


# The model file -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("spec", ["1.0", "0.x"])
def test_the_vrm_meta_licence_fields_are_read_from_the_model(tmp_path, spec):
    path = tmp_path / "m.vrm"
    path.write_bytes(rig.model(spec))
    read = vrm.read_meta(path)
    assert read["spec_version"] == spec and set(read["meta"]) == set(vrm.LICENCE_FIELDS[spec])
    if spec == "1.0":
        assert read["meta"]["avatarPermission"] == "onlyAuthor" and read["meta"]["otherLicenseUrl"] is None
    else:
        assert read["meta"]["licenseName"] == "Redistribution_Prohibited"
    assert "authors" not in read["meta"] and "name" not in read["meta"]


def test_a_model_without_vrm_meta_or_not_a_glb_refuses(tmp_path):
    path = tmp_path / "m.vrm"
    path.write_bytes(rig.model("1.0", meta={"name": "x"}))
    with pytest.raises(vrm.VrmRefused) as caught:
        vrm.read_meta(path)
    assert caught.value.code == "vrm_meta_missing"
    path.write_bytes(b"not a model at all, just bytes")
    with pytest.raises(vrm.VrmRefused) as caught:
        vrm.read_meta(path)
    assert caught.value.code == "vrm_invalid"


# The gates ------------------------------------------------------------------------------------------------------
GATES = {
    "vrm_consent_missing": lambda r: r["likenessConsent"].update(scopes=["Avatar"]),
    "vrm_consent_revoked": lambda r: r["likenessConsent"].update(revokedAt="2026-10-30T00:00:00Z"),
    "vrm_approval_missing": lambda r: r["approval"].update(state="pending"),
    "vrm_badge_undecided": lambda r: r["badge"].update(burnedIn=False),
}


@pytest.mark.parametrize("code", sorted(GATES))
def test_the_vrm_path_refuses_without_its_consent_and_approval(tmp_path, code):
    ws = Workspace(tmp_path)
    add_model(ws, edit=GATES[code])
    g = plan(ws, vrm_job(ws, "nv-gate"), vrm_ctx(ws))
    assert [r["code"] for r in g["admit"]["refusals"]] == [code]
    assert {n["id"]: n["state"] for n in g["nodes"]}["avatar/seg-1"] == "blocked"


@pytest.mark.parametrize(
    "edit, code",
    [
        (lambda r: r["approval"].update(vrmSha256="0" * 64), "vrm_approval_missing"),
        (lambda r: r["approval"].update(decidedBy="Agent"), "vrm_approval_missing"),
        (lambda r: r["approval"].update(ref="TIN-0000"), "vrm_approval_missing"),
        (lambda r: r["likenessConsent"].pop("evidenceSha256"), "vrm_consent_missing"),
        (lambda r: r.update(kind="kitpip"), "vrm_model_invalid"),
    ],
)
def test_each_gate_field_is_checked(tmp_path, edit, code):
    ws = Workspace(tmp_path)
    add_model(ws, edit=edit)
    gate = admit.admit(vrm_job(ws, "nv-gate"), ws.records, "resolved")
    assert [r["code"] for r in gate["refusals"]] == [code]


def test_the_job_must_name_its_model_digest_and_a_ruled_edition(tmp_path):
    ws = Workspace(tmp_path)
    add_model(ws)
    job = vrm_job(ws, "nv-gate")
    assert admit.admit(job, ws.records, "resolved")["verdict"] == "Admitted"
    job["avatar"]["rigRevisionSha256"] = "0" * 64
    assert [r["code"] for r in admit.admit(job, ws.records, "resolved")["refusals"]] == ["vrm_digest_mismatch"]
    job["avatar"]["rigRevisionSha256"], job["avatar"]["rig"] = None, "no-such-model"
    assert [r["code"] for r in admit.admit(job, ws.records, "resolved")["refusals"]] == ["vrm_model_missing"]
    job["avatar"]["rig"], job["edition"] = rig.FIXTURE_ID, "OwnContent"
    assert [r["code"] for r in admit.admit(job, ws.records, "resolved")["refusals"]] == ["vrm_edition_unruled"]
    job["edition"], job["avatar"]["external"] = "Internal", "unity"
    assert [r["code"] for r in admit.admit(job, ws.records, "resolved")["refusals"]] == ["avatar_external_unknown"]
    job["avatar"]["external"] = "vrm"
    assert [r["code"] for r in admit.admit(job, ws.records, "mismatch")["refusals"]] == ["vrm_pin_mismatch"]


def test_a_pending_or_missing_renderer_blocks_only_the_avatar_stages(tmp_path):
    ws = Workspace(tmp_path)
    add_model(ws)
    job = vrm_job(ws, "nv-pending")
    g = plan(ws, job, vrm_ctx(ws, record=write_record(tmp_path, pending_record())))
    rows = {n["id"]: n for n in g["nodes"]}
    assert {(rows[n]["state"], rows[n]["reason"]) for n in AVATAR} == {("blocked", "vrm_pin_pending")}
    assert g["admit"]["verdict"] == "Admitted" and rows["voice/seg-1"]["state"] == "stale"
    g = plan(ws, job, vrm_ctx(ws, binary=tmp_path / "absent"))
    assert {n["reason"] for n in g["nodes"] if n["id"] in AVATAR} == {"vrm_renderer_missing"}
    # A kitpip pin alone does not run a vrm job.
    g = plan(ws, job, ws.ctx() | {"pin": kitpip.load_pin(KITPIP_EXTERNALS)})
    assert {n["reason"] for n in g["nodes"] if n["id"] in AVATAR} == {"vrm_renderer_missing"}


def test_kitpip_avatar_keys_do_not_change_with_a_vrm_pin_in_the_context(tmp_path):
    ws = Workspace(tmp_path)
    job = init_job("nv-kitpip", "job-fixture-fake", sha(ws.paths["script"]), avatar=True, persona="fixture-persona")
    pin = kitpip.load_pin(KITPIP_EXTERNALS)
    knobs = graph.knobs_for("avatar", job["segments"][0], job, ws.records, pin)
    assert "external" not in knobs and set(knobs) == {"rig", "rigRevisionSha256", "renderSize", "persona"}
    assert graph.knobs_for("avatar_check", job["segments"][0], job, ws.records, pin) == {"persona": "fixture-persona"}


# The renderer protocol ------------------------------------------------------------------------------------------
def test_a_renderer_changed_after_resolve_refuses_before_spawn(tmp_path):
    sentinel = tmp_path / "spawned"
    binary, record = pinned_script(tmp_path, f"#!/bin/sh\ntouch {sentinel}\n")
    pin = vrm.load_pin(record)
    resolution = vrm.resolve(pin, {vrm.BIN_ENV: str(binary)})
    assert resolution["state"] == "resolved"
    binary.write_text(binary.read_text() + "# changed\n")
    with pytest.raises(vrm.VrmRefused) as caught:
        vrm.call_version(resolution, pin)
    assert caught.value.code == "vrm_pin_mismatch" and not sentinel.exists()


def stub_render(tmp_path, binary=STUB, record=EXTERNALS, frames=4, size=32):
    pin = vrm.load_pin(record)
    resolution = vrm.resolve(pin, {vrm.BIN_ENV: str(binary)})
    model = tmp_path / "m.vrm"
    model.write_bytes(rig.model())
    face_path = tmp_path / "face.json"
    face_path.write_text(json.dumps(tiny_face(frames)))
    out = tmp_path / "overlay.mov"
    return vrm.render(resolution, pin, model, face_path, size, {"num": 30, "den": 1}, frames, out, 120), out


def test_the_stub_streams_rgba_frames_into_a_prores_overlay(tmp_path, ffmpeg):
    (report, digest), out = stub_render(tmp_path)
    assert report["frames"] == 4 and report["gpu"] == {"vendor": "none", "renderer": "stub-cpu", "driver": "none"}
    assert out.is_file() and re.fullmatch(r"[0-9a-f]{64}", digest)
    again = tmp_path / "again"
    again.mkdir()
    (_, digest_again), _ = stub_render(again)
    assert digest_again == digest  # the stub is deterministic; a GPU renderer holds this per host only


@pytest.mark.parametrize(
    "env, code",
    [
        ("VRM_STUB_EXTRA_FRAMES=2", "vrm_frames_mismatch"),
        ("VRM_STUB_NO_GPU=1", "vrm_report_invalid"),
        ("VRM_STUB_REFUSE=vrm_invalid", "vrm_invalid"),
        ("VRM_STUB_REFUSE=face_invalid", "face_invalid"),
    ],
)
def test_renderer_faults_and_refusals_are_typed(tmp_path, ffmpeg, env, code):
    binary, record = pinned_script(tmp_path, f'#!/bin/sh\n{env} exec python3 "{STUB}" "$@"\n')
    with pytest.raises(vrm.VrmRefused) as caught:
        stub_render(tmp_path, binary, record)
    assert caught.value.code == code


# The executor ---------------------------------------------------------------------------------------------------
def test_run_renders_and_checks_a_vrm_overlay(settled):
    result, s = settled["result"], settled["store"]
    assert set(AVATAR) <= set(ran(result)) and {result["states"][n] for n in AVATAR} == {"fresh"}
    assert "compose" in ran(result) and "deliver_check" in ran(result)
    assert all(problems == [] for problems in s.verify().values())
    avatar = s.manifest("avatar/seg-1")
    measured = avatar["measurements"]
    assert measured["frames_identity"] == "per_host" and measured["show_badge"] is False
    assert measured["renderer"]["kind"] == "vrm" and measured["gpu"]["renderer"] == "stub-cpu"
    assert (
        measured["vrm"]["spec_version"] == "1.0" and measured["vrm"]["meta"]["commercialUsage"] == "personalNonProfit"
    )
    assert measured["rig"]["sha256"] == avatar["knobs"]["rigRevisionSha256"]
    assert avatar["knobs"]["external"] == "vrm" and avatar["knobs"]["approval"]["ref"] == "TIN-7130"
    assert avatar["timeline"]["mapping"] == "avatar_overlay_v1" and avatar["timeline"]["no_time_stretch"] is False
    assert avatar["states"]["lip_sync"] == "pending_operator" and avatar["states"]["badge_decision"] == "open"
    assert avatar["states"]["render"] == "stub"
    assert "likeness-fixture" in avatar["labels"]["consent_ids"] and avatar["labels"]["persona"] == "fixture-persona"
    overlay = node_dir(s, "avatar/seg-1") / "overlay"
    seen, problems = avatar_manifest.verify_dir(overlay, "vrm")
    assert problems == [] and seen["schema"] == "avatar.manifest/v1"
    written = json.loads((overlay / "manifest.json").read_text())
    assert written["vrm"]["sha256"] == measured["rig"]["sha256"] and written["face"]["clock"] == "narration_output"
    assert written["badge"] == {"burned_in": False, "decision": "open"}
    face_doc = json.loads((overlay / "face.json").read_text())
    assert face_doc["frames"] == measured["frames"] and face_doc["fps"] == measured["fps"]
    assert face_doc["narration"]["run_id"] == avatar["timeline"]["narration"]["run_id"]
    check = json.loads((node_dir(s, "avatar_check/seg-1") / "check.json").read_text())
    assert check["frames_sha256"] == measured["frames_sha256"] and check["renderer_kind"] == "vrm"
    voice_run = node_dir(s, "voice/seg-1") / "narration"
    assert not (voice_run / "overlay").exists() and not (voice_run / "face.json").exists()


def test_the_open_badge_decision_holds_delivery_at_the_operator(settled):
    g = settled["graph"]
    gates = {p["gate"] for p in g["pending_operator"]}
    assert {"vrm_badge_decision", "lip_sync_acceptance"} <= gates
    assert {n["id"]: n["state"] for n in g["nodes"]}["deliver_check"] == "pending_operator"


def test_a_second_run_runs_nothing(settled):
    ws, job = settled["ws"], settled["job"]
    _, result, _ = run_job(ws, job, vrm_ctx(ws), replace=True)
    assert result["ran"] == [] and result["ok"] is True


def test_a_new_model_revision_needs_a_new_approval_and_reruns_the_avatar(copied):
    ws, job = copied
    data = rig.model("0.x")
    (ws.paths["store"] / "fixture.vrm").write_bytes(data)
    record = rig.record(data)
    record["approval"]["vrmSha256"] = "0" * 64  # the old approval does not cover the new digest
    (ws.paths["records"] / "avatars.json").write_text(json.dumps([record]))
    ws.reload()
    _, result, _ = run_job(ws, job, vrm_ctx(ws), replace=True)
    assert result["refused"] == "vrm_approval_missing" and result["ran"] == []
    record["approval"]["vrmSha256"] = record["sha256"]
    (ws.paths["records"] / "avatars.json").write_text(json.dumps([record]))
    ws.reload()
    s, result, _ = run_job(ws, job, vrm_ctx(ws), replace=True)
    assert set(ran(result)) == {*AVATAR, "compose", "deliver_check"}
    assert s.manifest("avatar/seg-1")["measurements"]["vrm"]["spec_version"] == "0.x"


def test_avatar_check_refuses_an_overlay_changed_after_render(copied):
    ws, job = copied
    s = ws.store(job, replace=True)
    overlay = node_dir(s, "avatar/seg-1") / "overlay"
    s.archive("avatar_check/seg-1")
    rc = run.RunContext(job, ws.records, s, vrm_ctx(ws), ws.env)
    (overlay / "face.json").write_text("{}\n")
    with pytest.raises(vrm.VrmRefused) as caught:
        vrm.run_avatar_check(rc, {"segment": "seg-1"}, s.dir / "unused")
    assert caught.value.code == "digest_mismatch"


def test_a_persona_change_reruns_the_vrm_overlay(copied):
    ws, job = copied
    job["labels"]["persona"] = "fixture-persona-b"
    s, result, _ = run_job(ws, job, vrm_ctx(ws), replace=True)
    assert set(AVATAR) <= set(ran(result)) and "voice/seg-1" not in ran(result)
    assert s.manifest("avatar_check/seg-1")["labels"]["persona"] == "fixture-persona-b"
