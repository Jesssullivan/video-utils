"""The sealed Modal app for a rented VoxCPM2 batch (narrate/serve/modal_batch.py), with no Modal, GPU, network or spend.

A stand-in `modal` module records what the app asks for. The batch runs through the real audiocpp_batch.py against the
fake audiocpp_cli, on a fake Volume that is one local directory. Every voice, script and clip is synthetic.
"""

import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import types
from pathlib import Path

import pytest
from conftest import SLIDE
from test_prerender import batch_engine, kit, run_batch, use_batch  # noqa: F401

from narrate import policy, prerender, render, verify
from narrate.config import Config
from narrate.video import graph

PACKAGE = Path(__file__).resolve().parents[1]
APP = PACKAGE / "serve" / "modal_batch.py"
SPEC = PACKAGE.parent / "docs" / "spec" / "NARRATE.md"


def load_app(fake_modal=None):
    """The app module under a private name, with the given `modal` module, or with none importable."""
    previous = sys.modules.get("modal")
    sys.modules["modal"] = fake_modal
    try:
        spec = importlib.util.spec_from_file_location("narrate_modal_batch", APP)
        module = importlib.util.module_from_spec(spec)
        sys.modules["narrate_modal_batch"] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop("narrate_modal_batch", None)
        if previous is None:
            sys.modules.pop("modal", None)
        else:
            sys.modules["modal"] = previous


@pytest.fixture
def app():
    return load_app()


class Recorder:
    """A stand-in for the Modal SDK: it records each call and starts nothing."""

    def __init__(self):
        self.functions, self.image_calls, self.volumes = {}, [], []
        recorder = self

        class App:
            def __init__(self, name):
                self.name = name

            def function(self, **kwargs):
                def wrap(fn):
                    assert "<locals>" not in fn.__qualname__, "Modal refuses a function outside global scope"
                    recorder.functions[fn.__name__] = kwargs
                    return fn

                return wrap

        class Volume:
            @staticmethod
            def from_name(name, create_if_missing=True):
                recorder.volumes.append((name, create_if_missing))
                return f"volume:{name}"

        class Image:
            @staticmethod
            def debian_slim(python_version):
                return Image()

            def __getattr__(self, name):
                def call(*args, **kwargs):
                    recorder.image_calls.append((name, args, kwargs))
                    return self

                return call

        self.module = types.SimpleNamespace(App=App, Volume=Volume, Image=Image)


def test_the_app_is_sealed_as_the_burst_lessons_ask():
    recorder = Recorder()
    load_app(recorder.module)
    assert set(recorder.functions) == {"run_requests"}
    asked = recorder.functions["run_requests"]
    assert asked["block_network"] is True and asked["restrict_modal_access"] is True
    assert asked["retries"] == 0 and asked["min_containers"] == 0 and asked["max_containers"] == 1
    assert asked["single_use_containers"] is True
    assert asked["cpu"][0] == asked["cpu"][1] and asked["memory"][0] == asked["memory"][1]
    assert not asked.get("secrets"), "a sealed run holds no secret"
    assert list(asked["volumes"]) == ["/vol"]
    assert recorder.volumes == [("narrate-rented-batch", False)], "the app never creates a Volume"


def test_importing_without_the_sdk_defines_no_app(app):
    assert app.modal is None and not hasattr(app, "app")


def test_the_runner_stops_before_the_function_timeout(app):
    assert app.DEADLINE_S < app.TIMEOUT_S


def test_the_engine_record_is_a_consistent_rented_batch_and_offsite(app):
    record = app.engine_record("1" * 64)
    assert policy.consistent(record) and policy.is_offsite(record) and prerender.is_batch(record)
    assert not policy.is_hosted(record), "a rented batch needs no job allowHosted, as for any RentedOpen engine"
    prerender.check_engine(record, {})


def test_the_placeholder_binary_is_refused_until_a_real_digest_exists(app):
    with pytest.raises(prerender.PrerenderError) as refused:
        prerender.check_engine(app.engine_record(), {})
    assert refused.value.code == "engine_unpinned"


def test_the_spec_shows_this_record(app):
    text = SPEC.read_text(encoding="utf-8")
    block = re.search(r'```json\n(\{"id": "voxcpm2-batch-modal".*?)\n```', text, re.S)
    assert block, "docs/spec/NARRATE.md shows the record"
    shown = json.loads(block.group(1))
    assert shown == app.engine_record("<binary sha256>")


@pytest.mark.parametrize("reachable", [True, False], ids=["open", "sealed"])
def test_assert_sealed_stops_an_open_container(app, reachable):
    class Open:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def connect(address, timeout):
        if reachable:
            return Open()
        raise socket.gaierror("no name resolution in a sealed container")

    if reachable:
        with pytest.raises(app.Refused) as refused:
            app.assert_sealed(connect)
        assert refused.value.code == "not_sealed"
    else:
        app.assert_sealed(connect)


def test_an_open_container_reads_nothing_on_the_volume(app, tmp_path):
    def refused_probe():
        raise app.Refused("not_sealed", "open")

    with pytest.raises(app.Refused):
        app.run_batch(tmp_path, "nothing-here", "x", "0" * 64, "0" * 64, probe=refused_probe)


def test_the_dry_run_passes_every_check(app, kit):  # noqa: F811
    report = app.dry_run()
    assert report["ok"], report["checks"]
    assert report["deployed"] is False and report["billed"] is False


def test_the_dry_run_cli_prints_ok_with_no_sdk_and_no_network():
    done = subprocess.run([sys.executable, "-I", str(APP), "dry-run"], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["ok"] is True


def stage(app, vol, run_id, plan, kit_):
    """The fake Volume with kit's binary and weights pinned, and a plan on it."""
    for tree, name, path, sha in (
        ("bin", app.BINARY_NAME, kit_.binary, kit_.binary_sha),
        ("weights", app.WEIGHTS_NAME, kit_.model, kit_.model_sha),
    ):
        target = vol / tree / sha / name
        target.parent.mkdir(parents=True)
        target.write_bytes(path.read_bytes())
    app.stage_in(plan, vol, run_id)


def test_a_rented_job_runs_sealed_and_renders_with_nothing_left_behind(app, workspace, kit, tmp_path):  # noqa: F811
    """The path a real run takes: consent refuses first, then plan, the sealed batch, the takes home, the wipe and the
    render. Only the Volume and the SDK are stand-ins."""
    use_batch(workspace, kit, id=app.ENGINE_ID, profile="RentedOpen", backend="RentedAudioCppBatch")
    workspace.job["engine"] = app.ENGINE_ID
    for voice in workspace.voices:
        voice["allowedEngines"].append(app.ENGINE_ID)
    cfg = Config(workspace.write(SLIDE))
    with pytest.raises(policy.Refused) as refused:
        render.plan(cfg, tmp_path / "refused", takes=1)
    assert refused.value.code == "hosted_not_allowed"

    workspace.consents[0]["hostedAllowed"] = True
    cfg = Config(workspace.write(SLIDE))
    path, plan_doc = render.plan(cfg, tmp_path / "plan", takes=1)
    vol, run_id, plan_dir = tmp_path / "vol", "run-1", path.parent
    stage(app, vol, run_id, plan_dir, kit)
    held = vol / "runs" / run_id
    uploaded = {p.relative_to(held).parts[0] for p in held.rglob("*") if p.is_file()}
    assert uploaded == {"requests", "refs"}, "only what the engine needs leaves the host"

    name = Path(plan_doc["batches"][0]["file"]).stem
    probes = []
    env = {"NARRATE_AUDIOCPP_BATCH_TEST_MODE": "1", "FAKE_AUDIOCPP_LOG": str(tmp_path / "argv.jsonl")}
    reply = app.run_batch(
        vol,
        run_id,
        name,
        kit.binary_sha,
        kit.model_sha,
        runner=PACKAGE / "serve" / "audiocpp_batch.py",
        work_root=tmp_path,
        probe=lambda: probes.append(1),
        extra_env=env,
    )
    assert reply["exit_code"] == 0 and reply["missing"] == 0 and probes == [1]
    assert len(json.dumps(reply).encode()) <= app.REPLY_MAX_BYTES

    app.stage_back(vol, run_id, plan_dir)
    assert app.wipe(vol, run_id) == [] and not (vol / "runs" / run_id).exists()
    assert not list(tmp_path.glob("narrate-batch-*")), "the container's work directory goes with the run"

    final, manifest = render.render(cfg, prerendered=plan_dir)
    assert verify.verify(final)["ok"]
    assert manifest["engine"]["id"] == app.ENGINE_ID and manifest["engine"]["profile"] == "RentedOpen"
    assert manifest["engine"]["synthesis"]["mode"] == "out_of_process_batch"


def test_a_stopped_rented_batch_finishes_from_the_volume(app, workspace, kit, tmp_path):  # noqa: F811
    """No retries: a second call with only_missing resumes from the takes the first call left on the Volume."""
    use_batch(workspace, kit, profile="RentedOpen", backend="RentedAudioCppBatch")
    workspace.consents[0]["hostedAllowed"] = True
    cfg = Config(workspace.write(SLIDE))
    path, plan_doc = render.plan(cfg, tmp_path / "plan", takes=3)
    vol, plan_dir = tmp_path / "vol", path.parent
    stage(app, vol, "run-2", plan_dir, kit)
    name = Path(plan_doc["batches"][0]["file"]).stem
    common = {
        "runner": PACKAGE / "serve" / "audiocpp_batch.py",
        "work_root": tmp_path,
        "probe": lambda: None,
    }
    first = app.run_batch(
        vol,
        "run-2",
        name,
        kit.binary_sha,
        kit.model_sha,
        extra_env={"NARRATE_AUDIOCPP_BATCH_TEST_MODE": "1", "FAKE_AUDIOCPP_FAIL_AFTER": "1"},
        **common,
    )
    assert first["exit_code"] == 1 and first["outputs"] == 1 and first["missing"] > 0
    second = app.run_batch(
        vol,
        "run-2",
        name,
        kit.binary_sha,
        kit.model_sha,
        only_missing=True,
        extra_env={"NARRATE_AUDIOCPP_BATCH_TEST_MODE": "1"},
        **common,
    )
    assert second["exit_code"] == 0 and second["missing"] == 0
    assert second["receipt"] != first["receipt"]


def test_a_wrong_pin_refuses_before_the_runtime_starts(app, workspace, kit, tmp_path):  # noqa: F811
    use_batch(workspace, kit, profile="RentedOpen", backend="RentedAudioCppBatch")
    workspace.consents[0]["hostedAllowed"] = True
    cfg = Config(workspace.write(SLIDE))
    path, plan_doc = render.plan(cfg, tmp_path / "plan", takes=1)
    vol = tmp_path / "vol"
    stage(app, vol, "run-3", path.parent, kit)
    (vol / "bin" / kit.binary_sha / app.BINARY_NAME).write_bytes(b"another binary")
    name = Path(plan_doc["batches"][0]["file"]).stem
    reply = app.run_batch(
        vol,
        "run-3",
        name,
        kit.binary_sha,
        kit.model_sha,
        runner=PACKAGE / "serve" / "audiocpp_batch.py",
        work_root=tmp_path,
        probe=lambda: None,
        extra_env={"FAKE_AUDIOCPP_LOG": str(tmp_path / "argv.jsonl")},
    )
    assert reply["exit_code"] == 2 and reply["outputs"] is None
    assert not (tmp_path / "argv.jsonl").exists(), "the runtime never started"
    with pytest.raises(app.Refused) as refused:
        app.run_batch(vol, "run-3", name, "bad", kit.model_sha, work_root=tmp_path, probe=lambda: None)
    assert refused.value.code == "pin_invalid"


@pytest.mark.parametrize(
    "run_id, code",
    [("../escape", "run_id_invalid"), ("run/two", "run_id_invalid"), ("", "run_id_invalid")],
)
def test_a_run_id_stays_inside_the_volume(app, tmp_path, run_id, code):
    with pytest.raises(app.Refused) as refused:
        app.run_dir(tmp_path, run_id)
    assert refused.value.code == code


def test_every_run_needs_a_new_id_and_a_symlink_stops_the_copy(app, tmp_path):
    plan = tmp_path / "plan"
    app.fixture_plan(plan)
    app.stage_in(plan, tmp_path / "vol", "again")
    with pytest.raises(app.Refused) as refused:
        app.stage_in(plan, tmp_path / "vol", "again")
    assert refused.value.code == "run_exists"
    (plan / "refs" / "link.wav").symlink_to(tmp_path / "plan" / "requests" / "fixture.json")
    with pytest.raises(app.Refused) as refused:
        app.stage_in(plan, tmp_path / "vol", "linked")
    assert refused.value.code == "input_symlink"


def test_root_hands_the_work_tree_to_an_unprivileged_user(app, tmp_path, monkeypatch):
    """audiocpp_batch.py refuses root, and a Modal container runs as root."""
    owned = []
    monkeypatch.setattr(app.os, "geteuid", lambda: 0)
    monkeypatch.setattr(app.os, "chown", lambda path, uid, gid: owned.append((Path(path), uid, gid)))
    (tmp_path / "plan").mkdir()
    env, user = app.child_settings(tmp_path, None)
    assert user == {"user": app.UID, "group": app.GID, "extra_groups": []}
    assert {p for p, _, _ in owned} == {tmp_path, tmp_path / "plan"}
    assert {(uid, gid) for _, uid, gid in owned} == {(app.UID, app.GID)}


def test_the_runner_gets_a_built_environment_and_no_token(app, tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATE_ENGINE_TOKEN", "not-for-the-runner")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "not-for-the-runner")
    env, user = app.child_settings(tmp_path, None)
    assert "not-for-the-runner" not in env.values()
    assert set(env) == {"PATH", "HOME", "NARRATE_RUNS_DIR", "VK_DRIVER_FILES"}
    if os.geteuid() != 0:
        assert user == {}


def test_takes_from_another_binary_join_only_when_the_record_pins_it(app, workspace, kit, tmp_path):  # noqa: F811
    """A request id holds no engine, so batches merge by content. The receipt check is the gate: a take from a binary
    the record does not pin refuses. Listing both binaries is a choice about the record, and the manifest's batches
    still name which binary made each take."""
    use_batch(workspace, kit)
    cfg = Config(workspace.write(SLIDE))
    path, _ = render.plan(cfg, tmp_path / "plan", takes=1)
    assert run_batch(kit, path.parent) == [0]
    other = "2" * 64
    rented = batch_engine(kit, profile="RentedOpen", backend="RentedAudioCppBatch")
    weights = rented["files"][1]
    alone = {**rented, "files": [{"path": app.BINARY_NAME, "sha256": other}, weights]}
    with pytest.raises(prerender.PrerenderError) as refused:
        prerender.Pool(path.parent, alone, {})
    assert refused.value.code == "prerendered_engine_mismatch"
    both = {**rented, "files": [{"path": app.BINARY_NAME, "sha256": other}, rented["files"][0], weights]}
    assert prerender.Pool(path.parent, both, {}).takes


def test_a_rented_engine_changes_the_voice_key_of_every_segment(app, kit):  # noqa: F811
    """engine_identity holds the id, the profile and the backend, so moving a job to a rented engine leaves no voice
    node fresh: unchanged segments render again unless the job keeps the engine that voiced them."""
    local = batch_engine(kit, id="voxcpm2-batch")
    rented = {
        **local,
        "id": app.ENGINE_ID,
        "profile": "RentedOpen",
        "backend": "RentedAudioCppBatch",
        "estateControlled": False,
        "confidentialAllowed": False,
    }
    records = {"engines": {"voxcpm2-batch": local, app.ENGINE_ID: rented}}
    identity = [graph.engine_identity(records, {"engine": e}) for e in ("voxcpm2-batch", app.ENGINE_ID)]
    assert identity[0] != identity[1]
    assert identity[0]["files"] == identity[1]["files"], "the same pinned files do not keep the key"
