"""The sealed Modal app for a rented VoxCPM2 batch (narrate/serve/modal_batch.py), with no Modal, GPU, network or spend.

A stand-in `modal` module records what the app asks for. The host steps run through the real subprocess path against
tests/fake_modal.py, which keeps client 1.6.1's Volume and `modal run` behaviour on one local directory. The batch runs
through the real audiocpp_batch.py against the fake audiocpp_cli. Every voice, script and clip is synthetic.
"""

# ruff: noqa: F811

import importlib.util
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
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
RUNNER = PACKAGE / "serve" / "audiocpp_batch.py"
TEST_MODE = {"NARRATE_AUDIOCPP_BATCH_TEST_MODE": "1"}


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


def test_the_image_holds_the_runner_and_the_file_it_loads():
    recorder = Recorder()
    app = load_app(recorder.module)
    added = {Path(c[1][1]) for c in recorder.image_calls if c[0] == "add_local_file"}
    assert added == {Path(app.IMAGE_DIR) / "audiocpp_batch.py", Path(app.IMAGE_DIR) / "finalize.py"}


def test_importing_without_the_sdk_defines_no_app(app):
    assert app.modal is None and not hasattr(app, "app")


def test_this_file_states_what_narrate_states(app):
    assert app.PLAN_SCHEMA == prerender.PLAN_SCHEMA and app.RECEIPT_SCHEMA == prerender.RECEIPT_SCHEMA
    assert (
        app.RENTED_BACKEND in prerender.BACKENDS and app.RENTED_BACKEND in policy.PROFILE_BACKENDS[app.RENTED_PROFILE]
    )
    assert app.PLACEMENT == prerender.RENTED


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


class Open:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@pytest.mark.parametrize(
    "answers, sealed",
    [
        ({"name", "address"}, False),
        ({"address"}, False),
        ({"name"}, False),
        (set(), True),
    ],
    ids=["open", "blocked-dns-open-routes", "address-blocked-only", "sealed"],
)
def test_assert_sealed_needs_the_name_and_the_address_to_fail(app, answers, sealed):
    (name, _), (address, _) = app.NETWORK_PROBES
    targets = {name: "name", address: "address"}
    tried = []

    def connect(target, timeout):
        tried.append(target[0])
        if targets[target[0]] in answers:
            return Open()
        if targets[target[0]] == "name":
            raise socket.gaierror("no name resolution")
        raise OSError("network is unreachable")

    if sealed:
        app.assert_sealed(connect)
        assert tried == [name, address]
    else:
        with pytest.raises(app.Refused) as refused:
            app.assert_sealed(connect)
        assert refused.value.code == "not_sealed"


def test_the_probes_name_a_real_host_and_a_public_address(app):
    (name, name_port), (address, address_port) = app.NETWORK_PROBES
    assert name == "huggingface.co" and name_port == 443
    assert ipaddress.ip_address(address).is_global and address_port == 443


def use_rented(app, workspace, kit):
    use_batch(workspace, kit, id=app.ENGINE_ID, profile="RentedOpen", backend="RentedAudioCppBatch")
    workspace.job["engine"] = app.ENGINE_ID
    for voice in workspace.voices:
        voice["allowedEngines"].append(app.ENGINE_ID)


def rented_job(app, workspace, kit, tmp_path, takes=1, allowed=True):
    """A job on the rented record: (config, plan directory)."""
    use_rented(app, workspace, kit)
    workspace.consents[0]["hostedAllowed"] = allowed
    cfg = Config(workspace.write(SLIDE))
    path, _ = render.plan(cfg, tmp_path / "plan", takes=takes)
    return cfg, path.parent


def on_prem_job(workspace, kit, tmp_path):
    """A job on a GpuDirect record, with consent that allows no rented host."""
    use_batch(workspace, kit)
    assert workspace.consents[0]["hostedAllowed"] is False
    cfg = Config(workspace.write(SLIDE))
    path, _ = render.plan(cfg, tmp_path / "plan", takes=1)
    return cfg, path.parent


def pins(app, vol, kit_):
    """The fake Volume with kit's binary and weights pinned."""
    for tree, name, path, sha in (
        ("bin", app.BINARY_NAME, kit_.binary, kit_.binary_sha),
        ("weights", app.WEIGHTS_NAME, kit_.model, kit_.model_sha),
    ):
        target = vol / tree / sha / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    return kit_.binary_sha, kit_.model_sha


def put_run(app, vol, run_id, plan):
    """A plan on the fake Volume, as stage_in leaves it, for tests of the container side."""
    for sub in app.UPLOADED:
        app.copy_tree(plan / sub, vol / "runs" / run_id / sub)


def live(workspace):
    """The consents file the workspace wrote, which is what modal_batch reads at upload."""
    return workspace.base / "consents.json"


def volume_files(vol):
    return sorted(p.relative_to(vol).as_posix() for p in vol.rglob("*") if p.is_file())


def batch_name(plan):
    return json.loads((plan / "plan.json").read_text())["batches"][0]["file"].split("/")[1].removesuffix(".json")


def driver(app, tmp_path, kit, runner_env=None):
    """(client, binary pin, weights pin) on a fake Volume with the pins in place."""
    binary, model = pins(app, tmp_path / "vol", kit)
    return app.fake_client(tmp_path, {**TEST_MODE, **(runner_env or {})}), binary, model


def test_the_probe_runs_before_the_first_volume_read(app, workspace, kit, tmp_path):
    """The run is off the Volume until the probe fires, so any read before the probe finds nothing and refuses."""
    _, plan = rented_job(app, workspace, kit, tmp_path)
    vol = tmp_path / "vol"
    binary, model = pins(app, vol, kit)
    put_run(app, tmp_path / "away", "run-0", plan)
    (vol / "runs").mkdir()

    def probe():
        (tmp_path / "away" / "runs" / "run-0").rename(vol / "runs" / "run-0")

    reply = app.run_batch(
        vol,
        "run-0",
        batch_name(plan),
        binary,
        model,
        runner=RUNNER,
        work_root=tmp_path,
        probe=probe,
        extra_env=TEST_MODE,
    )
    assert reply["exit_code"] == 0


def test_an_open_container_reads_nothing_on_the_volume(app, workspace, kit, tmp_path, monkeypatch):
    """The run exists, so only the probe can refuse this."""
    _, plan = rented_job(app, workspace, kit, tmp_path)
    vol = tmp_path / "vol"
    binary, model = pins(app, vol, kit)
    put_run(app, vol, "run-0", plan)
    copies = []
    monkeypatch.setattr(app, "copy_tree", lambda *args, **kw: copies.append(args))
    monkeypatch.setattr(app, "assert_sealed", lambda: (_ for _ in ()).throw(app.Refused("not_sealed", "open")))
    with pytest.raises(app.Refused) as refused:
        app.run_batch(vol, "run-0", batch_name(plan), binary, model, work_root=tmp_path)
    assert refused.value.code == "not_sealed"
    assert not copies and not list(tmp_path.glob("narrate-batch-*"))


class Deployed:
    """The deployed run_requests under a stand-in SDK, with the real runner and every spawn recorded."""

    def __init__(self, tmp_path, monkeypatch, kit_):
        self.module = load_app(Recorder().module)
        self.vol, self.calls = tmp_path / "vol", []
        self.binary, self.model = pins(self.module, self.vol, kit_)
        monkeypatch.setattr(self.module, "VOL", str(self.vol))
        monkeypatch.setattr(self.module, "IMAGE_DIR", str(RUNNER.parent))
        monkeypatch.setattr(self.module.tempfile, "tempdir", str(tmp_path))
        monkeypatch.setattr(self.module.socket, "create_connection", self.sealed)
        real = subprocess.Popen

        def recorded(argv, **kwargs):
            self.calls.append((argv, kwargs))
            return real(argv, **{k: v for k, v in kwargs.items() if k not in ("user", "group", "extra_groups")})

        monkeypatch.setattr(self.module.subprocess, "Popen", recorded)

    @staticmethod
    def sealed(target, timeout):
        raise OSError("sealed")

    def run(self, run_id, name, **kwargs):
        return self.module.run_requests(run_id, name, self.binary, self.model, **kwargs)

    def flag(self, name):
        argv = self.calls[-1][0]
        return argv[argv.index(name) + 1]


@pytest.fixture
def deployed(tmp_path, monkeypatch, kit):
    return Deployed(tmp_path, monkeypatch, kit)


def reply_of(text):
    lines = [json.loads(line) for line in text.splitlines()]
    assert len(lines) == 1, "the app log holds the reply and nothing else"
    return lines[0]["narrate_reply"]


def test_run_requests_prints_the_reply_and_keeps_the_runner_out_of_the_log(
    app,
    deployed,
    workspace,
    kit,
    tmp_path,
    capfd,
):
    _, plan = rented_job(app, workspace, kit, tmp_path)
    put_run(app, deployed.vol, "run-1", plan)
    name = batch_name(plan)
    assert deployed.run("run-1", name) is None, "the reply is printed, because `modal run` drops a return value"
    out, err = capfd.readouterr()
    reply = reply_of(out)
    assert reply["exit_code"] == 0 and reply["missing"] == 0 and not err
    assert app.read_reply(f"12:00:01 {out}") == reply
    assert len(out.encode()) <= app.REPLY_MAX_BYTES
    held = app.sha256_file(deployed.vol / "runs" / "run-1" / "receipts" / f"{name}.json")
    assert reply["receipt_sha256"] == held


def test_run_requests_asks_the_runner_for_the_sealed_settings(app, deployed, workspace, kit, tmp_path):
    _, plan = rented_job(app, workspace, kit, tmp_path)
    put_run(app, deployed.vol, "run-1", plan)
    deployed.run("run-1", batch_name(plan))
    argv, _ = deployed.calls[-1]
    assert argv[:3] == [sys.executable, "-I", str(RUNNER)]
    assert deployed.flag("--backend") == "vulkan" and deployed.flag("--family") == "voxcpm2"
    assert deployed.flag("--device") == "0" and deployed.flag("--audiocpp-commit") == app.AUDIOCPP_COMMIT
    assert deployed.flag("--placement") == "rented" and float(deployed.flag("--checkpoint-s")) > 0
    assert 0 < float(deployed.flag("--deadline-s")) <= app.DEADLINE_S
    assert "--only-missing" not in argv


def test_run_requests_passes_only_missing_and_fails_a_batch_that_is_not_whole(
    app,
    deployed,
    workspace,
    kit,
    tmp_path,
    capfd,
    monkeypatch,
):
    _, plan = rented_job(app, workspace, kit, tmp_path, takes=3)
    put_run(app, deployed.vol, "run-1", plan)
    name = batch_name(plan)
    real = app.child_settings

    def partial(module_settings):
        def settings(work, extra_env):
            return module_settings(work, {"FAKE_AUDIOCPP_FAIL_AFTER": "1"})

        return settings

    monkeypatch.setattr(deployed.module, "child_settings", partial(deployed.module.child_settings))
    with pytest.raises(deployed.module.Refused) as refused:
        deployed.run("run-1", name)
    assert refused.value.code == "batch_incomplete"
    assert reply_of(capfd.readouterr().out)["exit_code"] == 1
    monkeypatch.setattr(deployed.module, "child_settings", real)
    deployed.run("run-1", name, only_missing=True)
    assert "--only-missing" in deployed.calls[-1][0]
    assert reply_of(capfd.readouterr().out)["exit_code"] == 0


def test_run_requests_stops_an_open_container(app, deployed, workspace, kit, tmp_path, monkeypatch):
    _, plan = rented_job(app, workspace, kit, tmp_path)
    put_run(app, deployed.vol, "run-1", plan)
    monkeypatch.setattr(deployed.module.socket, "create_connection", lambda target, timeout: Open())
    with pytest.raises(deployed.module.Refused) as refused:
        deployed.run("run-1", batch_name(plan))
    assert refused.value.code == "not_sealed"
    assert not deployed.calls


def test_the_spawn_drops_root_and_gets_only_the_built_environment(
    app,
    deployed,
    workspace,
    kit,
    tmp_path,
    monkeypatch,
):
    """audiocpp_batch.py refuses root, and a Modal container runs as root."""
    _, plan = rented_job(app, workspace, kit, tmp_path)
    put_run(app, deployed.vol, "run-1", plan)
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "not-for-the-runner")
    monkeypatch.setenv("NARRATE_ENGINE_TOKEN", "not-for-the-runner")
    module = deployed.module
    owned = []
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    monkeypatch.setattr(module.os, "chown", lambda path, uid, gid: owned.append((uid, gid)))
    deployed.run("run-1", batch_name(plan))
    _, kwargs = deployed.calls[-1]
    assert (kwargs["user"], kwargs["group"], kwargs["extra_groups"]) == (module.UID, module.GID, [])
    assert set(owned) == {(module.UID, module.GID)}
    assert set(kwargs["env"]) == {"PATH", "HOME", "NARRATE_RUNS_DIR", "VK_DRIVER_FILES"}
    assert kwargs["env"]["VK_DRIVER_FILES"] == module.ICD


def test_the_margin_covers_the_stop_and_the_clock_counts_the_weights_copy(
    app,
    deployed,
    workspace,
    kit,
    tmp_path,
    monkeypatch,
):
    assert app.TIMEOUT_S - app.DEADLINE_S >= 180
    module = deployed.module
    _, plan = rented_job(app, workspace, kit, tmp_path)
    put_run(app, deployed.vol, "run-1", plan)
    now = {"t": 1000.0}
    copy = module.pinned_copy

    def slow(vol, tree, *args):
        now["t"] += 250.0
        return copy(vol, tree, *args)

    monkeypatch.setattr(module, "time", types.SimpleNamespace(monotonic=lambda: now["t"]))
    monkeypatch.setattr(module, "pinned_copy", slow)
    deployed.run("run-1", batch_name(plan))
    assert float(deployed.flag("--deadline-s")) == module.DEADLINE_S - 500
    now["t"] += 0
    monkeypatch.setattr(module, "pinned_copy", lambda *args: (now.update(t=now["t"] + 2000), copy(*args))[1])
    put_run(app, deployed.vol, "run-2", plan)
    with pytest.raises(module.Refused) as refused:
        deployed.run("run-2", batch_name(plan))
    assert refused.value.code == "deadline_spent"


def stand_in_wait(monkeypatch, app, wait):
    """Popen whose first plain wait() runs wait(proc) in place of the real one."""
    real = subprocess.Popen

    class Watched(real):
        waited = False

        def wait(self, timeout=None):
            if timeout is None and not Watched.waited and self.args[0] == sys.executable:
                Watched.waited = True
                return wait(self)
            return super().wait(timeout)

    monkeypatch.setattr(app.subprocess, "Popen", Watched)


def wait_for(ready, seconds=20):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if ready():
            return True
        time.sleep(0.02)
    raise AssertionError("never happened")


def outputs_on(source, name):
    path = source / "receipts" / f"{name}.json"
    return json.loads(path.read_text())["outputs"] if path.is_file() else {}


def test_a_preempted_container_keeps_its_finished_takes(app, workspace, kit, tmp_path, monkeypatch):
    """Preemption reaches the function as SIGINT, so it stops the runner and copies what finished before it dies."""
    _, plan = rented_job(app, workspace, kit, tmp_path, takes=3)
    vol = tmp_path / "vol"
    binary, model = pins(app, vol, kit)
    put_run(app, vol, "run-1", plan)
    name = batch_name(plan)

    def preempted(proc):
        logs = lambda: tmp_path.glob(f"narrate-batch-*/plan/logs/{name}.log")  # noqa: E731
        wait_for(lambda: any("audio_out=" in p.read_text() for p in logs()))
        raise KeyboardInterrupt

    stand_in_wait(monkeypatch, app, preempted)
    with pytest.raises(KeyboardInterrupt):
        app.run_batch(
            vol,
            "run-1",
            name,
            binary,
            model,
            runner=RUNNER,
            work_root=tmp_path,
            probe=lambda: None,
            extra_env={**TEST_MODE, "FAKE_AUDIOCPP_HANG_AFTER": "1"},
        )
    source = vol / "runs" / "run-1"
    outputs = outputs_on(source, name)
    assert len(outputs) >= 1 and json.loads((source / "receipts" / f"{name}.json").read_text())["exit_code"] != 0
    assert all((source / out["file"]).is_file() for out in outputs.values())
    assert not list(tmp_path.glob("narrate-batch-*"))


def test_a_kill_with_no_warning_keeps_what_the_last_pass_copied(
    app,
    workspace,
    kit,
    tmp_path,
    monkeypatch,
):
    """The Volume as it stood at the kill holds a checkpoint receipt and its takes, and a new call finishes from it."""
    cfg, plan = rented_job(app, workspace, kit, tmp_path, takes=3)
    vol = tmp_path / "vol"
    binary, model = pins(app, vol, kit)
    put_run(app, vol, "run-1", plan)
    name = batch_name(plan)
    monkeypatch.setattr(app, "COPY_EVERY_S", 0.05)
    monkeypatch.setattr(app, "CHECKPOINT_S", 0.05)
    source, killed = vol / "runs" / "run-1", vol / "runs" / "run-2"

    def killed_now(proc):
        wait_for(lambda: outputs_on(source, name))
        shutil.copytree(source, killed)
        proc.terminate()
        return subprocess.Popen.wait(proc, 15)

    stand_in_wait(monkeypatch, app, killed_now)
    common = {"runner": RUNNER, "work_root": tmp_path, "probe": lambda: None}
    env = {**TEST_MODE, "FAKE_AUDIOCPP_HANG_AFTER": "1"}
    app.run_batch(vol, "run-1", name, binary, model, extra_env=env, **common)
    receipt = json.loads((killed / "receipts" / f"{name}.json").read_text())
    assert receipt["stop_rule"] == "checkpoint" and receipt["exit_code"] is None
    assert receipt["placement"] == "rented" and receipt["missing"]
    assert all((killed / out["file"]).is_file() for out in receipt["outputs"].values())
    reply = app.run_batch(vol, "run-2", name, binary, model, only_missing=True, extra_env=TEST_MODE, **common)
    assert reply["exit_code"] == 0 and reply["missing"] == 0
    app.copy_tree(killed, plan)
    render.render(cfg, prerendered=plan)


def test_a_receipt_on_the_volume_never_lists_a_take_that_is_not_there(app, tmp_path, monkeypatch):
    """The take arrives between the receipt's read and the copy: the receipt on the Volume is still the older one."""
    plan, source = tmp_path / "plan", tmp_path / "vol"
    (plan / "wav").mkdir(parents=True)
    (plan / "receipts").mkdir()
    (plan / "receipts" / "voice.json").write_text('{"outputs": {}}')
    (plan / "wav" / "take.wav").write_bytes(b"take")
    copy = app.copy_tree
    order = []

    def spying(from_dir, to_dir, **kwargs):
        order.append(from_dir.name)
        if from_dir.name == "wav":
            assert not (source / "receipts" / "voice.json").exists(), "takes reach the Volume before their receipt"
        return copy(from_dir, to_dir, **kwargs)

    monkeypatch.setattr(app, "copy_tree", spying)
    app.sync_outputs(plan, source)
    assert order[0] == "wav" and (source / "receipts" / "voice.json").is_file()


def test_the_dry_run_passes_every_check(app, kit):
    report = app.dry_run()
    assert report["ok"], report["checks"]
    assert report["deployed"] is False and report["billed"] is False


def test_the_dry_run_cli_prints_ok_with_no_sdk_and_no_network():
    done = subprocess.run([sys.executable, "-I", str(APP), "dry-run"], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["ok"] is True


def test_a_rented_job_runs_sealed_and_renders_with_nothing_left_behind(app, workspace, kit, tmp_path):
    """The path a real run takes: consent refuses first, then plan, run_plan and the render. Only the `modal` command,
    the Volume and the SDK are stand-ins."""
    use_rented(app, workspace, kit)
    cfg = Config(workspace.write(SLIDE))
    with pytest.raises(policy.Refused) as refused:
        render.plan(cfg, tmp_path / "refused", takes=1)
    assert refused.value.code == "hosted_not_allowed"

    workspace.consents[0]["hostedAllowed"] = True
    cfg = Config(workspace.write(SLIDE))
    path, _ = render.plan(cfg, tmp_path / "plan", takes=1)
    plan = path.parent
    client, binary, model = driver(app, tmp_path, kit)
    code, report = app.run_plan(plan, live(workspace), client, "run-1", binary, model, "none")
    assert code == 0 and report["wiped"] and report["missing"] == 0 and not report["failed_batch"]
    assert client.runs() == [], "the run is gone from the Volume"
    assert not [f for f in volume_files(tmp_path / "vol") if f.startswith("runs/")]
    assert not list(tmp_path.glob("narrate-batch-*")), "the container's work directory goes with the run"
    assert not list(plan.glob(".get-*")), "the get directory goes too"
    assert (plan / "receipts").is_dir() and (plan / "wav").is_dir(), "takes land where --prerendered reads them"

    final, manifest = render.render(cfg, prerendered=plan)
    assert verify.verify(final)["ok"]
    assert manifest["engine"]["id"] == app.ENGINE_ID and manifest["engine"]["profile"] == "RentedOpen"
    assert manifest["engine"]["synthesis"]["mode"] == "out_of_process_batch"
    assert manifest["engine"]["synthesis"]["placements"] == ["rented"]
    assert all(b["placement"] == "rented" for b in manifest["engine"]["synthesis"]["batches"])


def test_a_job_on_an_on_prem_record_never_leaves_the_host(app, workspace, kit, tmp_path):
    """The path a review reproduced: a GpuDirect job with no hosted consent, and the digests the on-prem record pins."""
    _, plan = on_prem_job(workspace, kit, tmp_path)
    client, binary, model = driver(app, tmp_path, kit)
    before = volume_files(tmp_path / "vol")
    with pytest.raises(app.Refused) as refused:
        app.run_plan(plan, live(workspace), client, "run-1", binary, model, "none")
    assert refused.value.code == "engine_not_rented"
    assert volume_files(tmp_path / "vol") == before, "no byte left the host"


def test_a_rented_receipt_under_an_on_prem_record_never_renders(app, workspace, kit, tmp_path):
    """Someone runs the sealed batch by hand on an on-prem plan: the receipt's placement stops the render."""
    cfg, plan = on_prem_job(workspace, kit, tmp_path)
    assert run_batch(kit, plan, None, "--placement", "rented") == [0]
    with pytest.raises(render.RenderError) as refused:
        render.render(cfg, prerendered=plan)
    assert refused.value.code == "prerendered_placement_mismatch"


def test_an_unknown_placement_is_refused(workspace, kit, tmp_path):
    _, plan = on_prem_job(workspace, kit, tmp_path)
    assert run_batch(kit, plan) == [0]
    path = next((plan / "receipts").glob("*.json"))
    receipt = json.loads(path.read_text())
    assert receipt["placement"] == "on-prem"
    path.write_text(json.dumps({**receipt, "placement": "moon"}))
    with pytest.raises(prerender.PrerenderError) as refused:
        prerender.Pool(plan, batch_engine(kit), {})
    assert refused.value.code == "prerendered_invalid"


def edit_plan(plan, change):
    path = plan / "plan.json"
    doc = json.loads(path.read_text())
    change(doc)
    path.write_text(json.dumps(doc))


@pytest.mark.parametrize(
    "change, code",
    [
        (lambda d: d["engine"].update(backend="AudioCppBatch"), "engine_not_rented"),
        (lambda d: d["engine"].update(profile="GpuDirect"), "engine_not_rented"),
        (lambda d: d.pop("engine"), "engine_not_rented"),
        (lambda d: d["consents"][0].update(hostedAllowed=False), "hosted_not_allowed"),
        (lambda d: d["consents"][0].update(hostedAllowed="true"), "hosted_not_allowed"),
        (lambda d: d.update(consents=[]), "hosted_not_allowed"),
        (lambda d: d.pop("consents"), "hosted_not_allowed"),
        (lambda d: d["engine"].update(files=[]), "pin_not_in_record"),
        (lambda d: d.update(schema="other"), "plan_invalid"),
        (lambda d: d.update(batches=[]), "plan_incomplete"),
    ],
    ids=[
        "backend",
        "profile",
        "no-engine",
        "no-consent",
        "only-true-grants",
        "no-consents",
        "consents-absent",
        "pins",
        "schema",
        "no-batches",
    ],
)
def test_preflight_refuses_a_plan_it_cannot_send(app, workspace, kit, tmp_path, change, code):
    _, plan = rented_job(app, workspace, kit, tmp_path)
    assert app.preflight(plan, live(workspace), kit.binary_sha, kit.model_sha, "none")["batches"] == [batch_name(plan)]
    edit_plan(plan, change)
    with pytest.raises(app.Refused) as refused:
        app.preflight(plan, live(workspace), kit.binary_sha, kit.model_sha, "none")
    assert refused.value.code == code


def test_a_consent_revoked_after_the_plan_uploads_nothing(app, workspace, kit, tmp_path):
    """plan.json still says hostedAllowed, and its snapshot has no revokedAt: only the live row can stop this."""
    _, plan = rented_job(app, workspace, kit, tmp_path)
    client, binary, model = driver(app, tmp_path, kit)
    app.preflight(plan, live(workspace), binary, model, "none")
    snapshot = (plan / "plan.json").read_bytes()
    before = volume_files(tmp_path / "vol")
    workspace.consents[0]["revokedAt"] = "2026-11-05T00:00:00Z"
    workspace.write(SLIDE)
    with pytest.raises(app.Refused) as refused:
        app.run_plan(plan, live(workspace), client, "run-1", binary, model, "none")
    assert refused.value.code == "consent_revoked"
    assert (plan / "plan.json").read_bytes() == snapshot, "the snapshot is the same, and it did not decide"
    assert volume_files(tmp_path / "vol") == before, "no byte left the host"
    assert client.runs() == []


def test_the_commands_need_the_live_consents_and_refuse_a_revoked_one(app, workspace, kit, tmp_path, capsys):
    _, plan = rented_job(app, workspace, kit, tmp_path)
    workspace.consents[0]["revokedAt"] = "2026-11-05T00:00:00Z"
    workspace.write(SLIDE)
    argv = ["preflight", str(plan), "--binary-sha256", kit.binary_sha, "--model-sha256", kit.model_sha]
    argv += ["--health-class", "none"]
    with pytest.raises(SystemExit):
        app.main(argv)
    capsys.readouterr()
    assert app.main([*argv, "--consents", str(live(workspace))]) == app.EXIT_REFUSED
    assert json.loads(capsys.readouterr().err)["refused"] == "consent_revoked"


@pytest.mark.parametrize(
    "write, code",
    [
        (lambda rows: rows[0].update(revokedAt="2026-11-05"), "consent_revoked"),
        (lambda rows: rows[0].update(revokedAt=""), "consent_revoked"),
        (lambda rows: rows[0].pop("revokedAt"), "consent_invalid"),
        (lambda rows: rows[0].update(hostedAllowed=False), "hosted_not_allowed"),
        (lambda rows: rows[0].update(hostedAllowed="true"), "hosted_not_allowed"),
        (lambda rows: rows[0].pop("hostedAllowed"), "hosted_not_allowed"),
        (lambda rows: rows[0].update(id="another-consent"), "consent_missing"),
        (lambda rows: rows.clear(), "consent_missing"),
        (lambda rows: rows.append(dict(rows[0], revokedAt="2026-11-05")), "consent_revoked"),
        (lambda rows: rows.append("a row that is no record"), "consent_invalid"),
    ],
    ids=[
        "revoked",
        "revoked-empty",
        "no-revoked-field",
        "no-longer-granted",
        "only-true-grants",
        "no-grant-field",
        "row-gone",
        "file-empty",
        "duplicate-revoked",
        "not-a-record",
    ],
)
def test_preflight_reads_the_live_row_of_every_consent(app, workspace, kit, tmp_path, write, code):
    _, plan = rented_job(app, workspace, kit, tmp_path)
    rows = json.loads(live(workspace).read_text())
    write(rows)
    live(workspace).write_text(json.dumps(rows))
    with pytest.raises(app.Refused) as refused:
        app.preflight(plan, live(workspace), kit.binary_sha, kit.model_sha, "none")
    assert refused.value.code == code


def test_preflight_refuses_a_live_file_it_cannot_read_and_takes_a_single_record(app, workspace, kit, tmp_path):
    _, plan = rented_job(app, workspace, kit, tmp_path)
    check = lambda path: app.preflight(plan, path, kit.binary_sha, kit.model_sha, "none")  # noqa: E731
    rows = json.loads(live(workspace).read_text())
    for path, text in ((tmp_path / "absent.json", None), (tmp_path / "broken.json", "not json")):
        if text:
            path.write_text(text)
        with pytest.raises(app.Refused) as refused:
            check(path)
        assert refused.value.code == "consent_invalid"
    single = tmp_path / "single.json"
    single.write_text(json.dumps(rows[0]))
    assert check(single)["batches"] == [batch_name(plan)]


def test_preflight_reads_every_consent_the_plan_lists(app, workspace, kit, tmp_path):
    _, plan = rented_job(app, workspace, kit, tmp_path)
    edit_plan(plan, lambda d: d["consents"].append({"id": "another-consent", "hostedAllowed": True}))
    with pytest.raises(app.Refused) as refused:
        app.preflight(plan, live(workspace), kit.binary_sha, kit.model_sha, "none")
    assert refused.value.code == "consent_missing"


@pytest.mark.parametrize("health_class", ["health", "unknown", "", "None"])
def test_preflight_keeps_sp4_rows_off_a_rented_host(app, workspace, kit, tmp_path, health_class):
    _, plan = rented_job(app, workspace, kit, tmp_path)
    with pytest.raises(app.Refused) as refused:
        app.preflight(plan, live(workspace), kit.binary_sha, kit.model_sha, health_class)
    assert refused.value.code == "sp4_health_row"


def test_preflight_binds_the_run_to_the_record_and_the_files(app, workspace, kit, tmp_path):
    _, plan = rented_job(app, workspace, kit, tmp_path)

    def check(binary=kit.binary_sha, model=kit.model_sha):
        return app.preflight(plan, live(workspace), binary, model, "none")

    for binary, model, code in (
        ("7" * 64, kit.model_sha, "pin_not_in_record"),
        (kit.binary_sha, "7" * 64, "pin_not_in_record"),
        (app.BINARY_PLACEHOLDER, kit.model_sha, "pin_invalid"),
        ("a" * 64 + "\n", kit.model_sha, "pin_invalid"),
    ):
        with pytest.raises(app.Refused) as refused:
            check(binary, model)
        assert refused.value.code == code
    (plan / "refs" / "extra.wav").write_bytes(b"not in the plan")
    with pytest.raises(app.Refused) as refused:
        check()
    assert refused.value.code == "plan_extra_file"
    (plan / "refs" / "extra.wav").unlink()
    request = next((plan / "requests").glob("*.json"))
    data = request.read_bytes()
    request.write_bytes(data + b" ")
    with pytest.raises(app.Refused) as refused:
        check()
    assert refused.value.code == "plan_digest_mismatch"
    request.write_bytes(data)
    moved = tmp_path / "refs-away"
    (plan / "refs").rename(moved)
    with pytest.raises(app.Refused) as refused:
        check()
    assert refused.value.code == "plan_incomplete"
    (plan / "refs").mkdir()
    for clip in moved.iterdir():
        (plan / "refs" / clip.name).symlink_to(clip)
    with pytest.raises(app.Refused) as refused:
        check()
    assert refused.value.code == "input_symlink"


def test_only_what_the_engine_needs_leaves_the_host(app, workspace, kit, tmp_path):
    _, plan = rented_job(app, workspace, kit, tmp_path)
    (plan / "extra").mkdir()
    (plan / "extra" / "note.txt").write_text("stays home")
    (plan / "wav").mkdir()
    (plan / "wav" / "stray.wav").write_bytes(b"stays home")
    client, binary, model = driver(app, tmp_path, kit)
    facts = app.preflight(plan, live(workspace), binary, model, "none")
    app.stage_in(plan, client, "run-1", facts)
    held = tmp_path / "vol" / "runs" / "run-1"
    assert {p.relative_to(held).parts[0] for p in held.rglob("*") if p.is_file()} == {"requests", "refs"}


def test_the_fake_get_lands_as_the_client_does(app, kit, tmp_path):
    """The layout stage_back rests on: DEST/RUN/ and not DEST/. The fake's docstring says where this comes from."""
    client, _, _ = driver(app, tmp_path, kit)
    run = tmp_path / "vol" / "runs" / "run-1" / "wav"
    run.mkdir(parents=True)
    (run / "take.wav").write_bytes(b"take")
    (tmp_path / "plan").mkdir()
    (tmp_path / "plan" / "run-1").mkdir()
    client.volume("get", app.VOLUME_NAME, "runs/run-1", str(tmp_path / "plan"))
    assert (tmp_path / "plan" / "run-1" / "wav" / "take.wav").is_file()
    with pytest.raises(app.Refused) as refused:
        client.volume("get", app.VOLUME_NAME, "runs/run-1", str(tmp_path / "plan"))
    assert refused.value.code == "client_failed"


class Tampering:
    """A client that changes the Volume after the sealed run, before the get."""

    def __init__(self, client, change):
        self.client, self.change = client, change

    def __getattr__(self, name):
        return getattr(self.client, name)

    def run(self, *args):
        answer = self.client.run(*args)
        self.change()
        return answer


@pytest.mark.parametrize("target", ["receipt", "take"])
def test_a_changed_volume_is_not_taken_home_and_the_run_stays(app, workspace, kit, tmp_path, target):
    """A run whose takes did not come home is not wiped. abandon is the one way to drop it."""
    _, plan = rented_job(app, workspace, kit, tmp_path)
    client, binary, model = driver(app, tmp_path, kit)
    run = tmp_path / "vol" / "runs" / "run-1"

    def change():
        receipt = run / "receipts" / f"{batch_name(plan)}.json"
        if target == "receipt":
            receipt.write_text(receipt.read_text() + " ")
        else:
            next((run / "wav").glob("*.wav")).write_bytes(b"another take")

    code, report = app.run_plan(plan, live(workspace), Tampering(client, change), "run-1", binary, model, "none")
    assert code == app.EXIT_RUN_STAYS and not report["takes_home"] and not report["wiped"]
    assert report["stopped"] == ("receipt_digest_mismatch" if target == "receipt" else "take_missing")
    assert client.runs() == ["run-1"] and not (plan / "receipts").exists()
    app.drop(client, "run-1")
    assert client.runs() == []


def test_a_failed_get_leaves_the_run_and_abandon_removes_it(app, workspace, kit, tmp_path):
    _, plan = rented_job(app, workspace, kit, tmp_path)
    client, binary, model = driver(app, tmp_path, kit)

    class NoGet:
        def __getattr__(self, name):
            return getattr(client, name)

        def volume(self, verb, *args):
            if verb == "get":
                raise app.Refused("client_failed", "`modal volume get` exited 1")
            return client.volume(verb, *args)

    code, report = app.run_plan(plan, live(workspace), NoGet(), "run-1", binary, model, "none")
    assert code == app.EXIT_RUN_STAYS and report["stopped"] == "client_failed"
    assert report["next"].endswith("abandon run-1") and client.runs() == ["run-1"]
    app.drop(client, "run-1")
    assert client.runs() == []


def test_a_batch_that_refuses_leaves_nothing_on_the_volume(app, workspace, kit, tmp_path):
    """The runtime never started, so no take exists: the run goes and the report names the batch."""
    _, plan = rented_job(app, workspace, kit, tmp_path)
    client, binary, model = driver(app, tmp_path, kit)
    (tmp_path / "vol" / "bin" / binary / app.BINARY_NAME).write_bytes(b"another binary")
    code, report = app.run_plan(plan, live(workspace), client, "run-1", binary, model, "none")
    assert code == app.EXIT_PARTIAL and report["wiped"] and report["failed_batch"] == batch_name(plan)
    assert report["takes"] == 0 and report["missing"] > 0
    assert report["replies"][0]["exit_code"] == 2 and report["replies"][0]["outputs"] is None
    assert client.runs() == []


def test_a_call_that_prints_no_reply_is_a_failed_batch(app, workspace, kit, tmp_path):
    _, plan = rented_job(app, workspace, kit, tmp_path)
    client, binary, model = driver(app, tmp_path, kit)

    class Silent:
        def __getattr__(self, name):
            return getattr(client, name)

        def run(self, *args):
            client.run(*args)
            return 0, None

    code, report = app.run_plan(plan, live(workspace), Silent(), "run-1", binary, model, "none")
    assert code == app.EXIT_PARTIAL and report["failed_batch"] == batch_name(plan)
    assert client.runs() == []


def test_a_stopped_batch_comes_home_and_a_new_run_finishes_it(app, workspace, kit, tmp_path):
    """A partial batch is wiped with its takes home. The same plan under a new id sends them back up and voices only
    the rest, and a render takes both receipts."""
    cfg, plan = rented_job(app, workspace, kit, tmp_path, takes=3)
    client, binary, model = driver(app, tmp_path, kit, {"FAKE_AUDIOCPP_FAIL_AFTER": "1"})
    code, report = app.run_plan(plan, live(workspace), client, "run-1", binary, model, "none")
    assert code == app.EXIT_PARTIAL and report["takes"] == 1 and report["missing"] > 0
    assert report["replies"][0]["exit_code"] == 1 and report["wiped"] and client.runs() == []
    left = report["missing"]

    client, _, _ = driver(app, tmp_path, kit)
    code, report = app.run_plan(plan, live(workspace), client, "run-2", binary, model, "none")
    assert code == 0 and report["missing"] == 0, report
    assert report["replies"][0]["outputs"] == left, "the takes went back up, so only the rest is voiced"
    assert (plan / "requests" / f"{batch_name(plan)}.part1.json").is_file()
    final, manifest = render.render(cfg, prerendered=plan)
    assert verify.verify(final)["ok"]
    assert len(manifest["engine"]["synthesis"]["batches"]) >= 1


def test_a_run_id_on_the_volume_is_refused_before_any_upload(app, workspace, kit, tmp_path):
    _, plan = rented_job(app, workspace, kit, tmp_path)
    client, binary, model = driver(app, tmp_path, kit)
    (tmp_path / "vol" / "runs" / "run-1").mkdir(parents=True)
    with pytest.raises(app.Refused) as refused:
        app.run_plan(plan, live(workspace), client, "run-1", binary, model, "none")
    assert refused.value.code == "run_exists"
    assert not list((tmp_path / "vol" / "runs" / "run-1").iterdir())


def test_a_failed_upload_takes_the_partial_run_with_it(app, workspace, kit, tmp_path):
    _, plan = rented_job(app, workspace, kit, tmp_path)
    client, binary, model = driver(app, tmp_path, kit)

    class FailsSecondPut:
        puts = 0

        def __getattr__(self, name):
            return getattr(client, name)

        def volume(self, verb, *args):
            if verb == "put":
                FailsSecondPut.puts += 1
                if FailsSecondPut.puts == 2:
                    raise app.Refused("client_failed", "`modal volume put` exited 1")
            return client.volume(verb, *args)

    with pytest.raises(app.Refused) as refused:
        app.run_plan(plan, live(workspace), FailsSecondPut(), "run-1", binary, model, "none")
    assert refused.value.code == "client_failed" and client.runs() == []


def test_wipe_removes_one_run_by_its_exact_name(app, workspace, kit, tmp_path):
    _, plan = rented_job(app, workspace, kit, tmp_path)
    client, binary, model = driver(app, tmp_path, kit)
    assert app.run_plan(plan, live(workspace), client, "run-2", binary, model, "none")[0] == 0
    for run in ("run-1", "run-10"):
        (tmp_path / "vol" / "runs" / run).mkdir(parents=True)
    app.wipe(plan, client, "run-1")
    assert client.runs() == ["run-10"], "run-1 is gone, and run-10 is not a false alarm"


def test_wipe_refuses_until_the_takes_are_home(app, kit, tmp_path):
    client, _, _ = driver(app, tmp_path, kit)
    (tmp_path / "vol" / "runs" / "run-1").mkdir(parents=True)
    (tmp_path / "plan").mkdir()
    with pytest.raises(app.Refused) as refused:
        app.wipe(tmp_path / "plan", client, "run-1")
    assert refused.value.code == "takes_not_home"
    assert client.runs() == ["run-1"]


def test_a_wipe_that_does_not_read_back_is_refused(app, kit, tmp_path):
    client, _, _ = driver(app, tmp_path, kit)
    (tmp_path / "vol" / "runs" / "run-1").mkdir(parents=True)

    class Stuck:
        def __getattr__(self, name):
            return getattr(client, name)

        def volume(self, verb, *args):
            return "" if verb == "rm" else client.volume(verb, *args)

    with pytest.raises(app.Refused) as refused:
        app.drop(Stuck(), "run-1")
    assert refused.value.code == "wipe_unconfirmed"


def test_a_wrong_pin_refuses_before_the_runtime_starts(app, workspace, kit, tmp_path):
    _, plan = rented_job(app, workspace, kit, tmp_path)
    vol = tmp_path / "vol"
    binary, model = pins(app, vol, kit)
    put_run(app, vol, "run-3", plan)
    (vol / "bin" / binary / app.BINARY_NAME).write_bytes(b"another binary")
    name = batch_name(plan)
    common = {"runner": RUNNER, "work_root": tmp_path, "probe": lambda: None}
    reply = app.run_batch(
        vol, "run-3", name, binary, model, extra_env={"FAKE_AUDIOCPP_LOG": str(tmp_path / "a")}, **common
    )
    assert reply["exit_code"] == 2 and reply["outputs"] is None
    assert not (tmp_path / "a").exists(), "the runtime never started"
    with pytest.raises(app.Refused) as refused:
        app.run_batch(vol, "run-3", name, "bad", model, **common)
    assert refused.value.code == "pin_invalid"


def test_a_symlink_never_stands_in_for_a_pin(app, kit, tmp_path):
    vol = tmp_path / "vol"
    binary, _ = pins(app, vol, kit)
    pin = vol / "bin" / binary / app.BINARY_NAME
    real = tmp_path / "elsewhere"
    pin.rename(real)
    pin.symlink_to(real)
    with pytest.raises(app.Refused) as refused:
        app.pinned_copy(vol, "bin", binary, app.BINARY_NAME, tmp_path)
    assert refused.value.code == "pin_missing"


@pytest.mark.parametrize("run_id", ["../escape", "run/two", "", "ok\n", ".hidden"])
def test_a_run_id_stays_inside_the_volume(app, tmp_path, run_id):
    with pytest.raises(app.Refused) as refused:
        app.run_dir(tmp_path, run_id)
    assert refused.value.code == "run_id_invalid"


def test_a_symlink_stops_a_copy_and_a_killed_copy_leaves_no_part(app, tmp_path):
    source, target = tmp_path / "a", tmp_path / "b"
    source.mkdir()
    (source / "take.wav").write_bytes(b"take")
    (source / "take2.wav.part").write_bytes(b"half")
    assert app.copy_tree(source, target) == 1 and sorted(p.name for p in target.iterdir()) == ["take.wav"]
    (source / "take.wav").write_bytes(b"changed")
    assert app.copy_tree(source, target, keep_existing=True) == 0
    assert (target / "take.wav").read_bytes() == b"take"
    (source / "link.wav").symlink_to(source / "take.wav")
    with pytest.raises(app.Refused) as refused:
        app.copy_tree(source, target)
    assert refused.value.code == "input_symlink"


def test_a_user_outside_root_keeps_its_own_identity(app, tmp_path):
    env, user = app.child_settings(tmp_path, None)
    assert set(env) == {"PATH", "HOME", "NARRATE_RUNS_DIR", "VK_DRIVER_FILES"}
    if os.geteuid() != 0:
        assert user == {}


def test_on_prem_takes_render_under_a_rented_record_only_when_it_pins_them(
    app,
    workspace,
    kit,
    tmp_path,
):
    """A request id holds no engine, so batches merge by content. The receipt check is the gate: a take from a binary
    the record does not pin refuses. With both binaries pinned the render passes, and the manifest says those takes are
    on-prem under this engine's name. Whether a run may do that is open."""
    other = "2" * 64
    use_rented(app, workspace, kit)
    workspace.engines[-1]["files"] = [
        {"path": app.BINARY_NAME, "sha256": other},
        {"path": app.BINARY_NAME, "sha256": kit.binary_sha},
        workspace.engines[-1]["files"][1],
    ]
    workspace.consents[0]["hostedAllowed"] = True
    cfg = Config(workspace.write(SLIDE))
    path, _ = render.plan(cfg, tmp_path / "plan", takes=1)
    assert run_batch(kit, path.parent) == [0]
    _, manifest = render.render(cfg, prerendered=path.parent)
    assert manifest["engine"]["id"] == app.ENGINE_ID
    assert manifest["engine"]["synthesis"]["placements"] == ["on-prem"]
    alone = dict(
        workspace.engines[-1], files=[{"path": app.BINARY_NAME, "sha256": other}, workspace.engines[-1]["files"][2]]
    )
    with pytest.raises(prerender.PrerenderError) as refused:
        prerender.Pool(path.parent, alone, {})
    assert refused.value.code == "prerendered_engine_mismatch"


def test_a_rented_engine_changes_the_voice_key_of_every_segment(app, kit):
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
