"""narrate/serve/finalize.py (J130, TIN-7564): run records and the manual or preempting finalize path.

Every runner, engine and lease helper here is a fake Python process: no GPU, no Lease, no model. The fake runner
keeps a run record through finalize.open_record, starts a fake engine in its own session, and on SIGTERM stops the
engine group (SIGTERM, then SIGKILL) and closes its record with exit 20, as audiocpp_batch.py does. The fake lease
helper is a file named fixture_gpu_lease.py that runs the runner and exits when it does, as the real helper's
`finally` releases the Lease when its command exits.
"""

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time

import pytest
from conftest import PACKAGE

FINALIZE = PACKAGE / "serve" / "finalize.py"
HOLDER = "narrate-bench-20261028-s200000"

RUNNER = """
import importlib.util, os, signal, subprocess, sys, time
spec = importlib.util.spec_from_file_location("narrate_finalize", sys.argv[1])
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
run_id, holder, out = sys.argv[2], sys.argv[3], sys.argv[4]
stop = []
if os.environ.get("FAKE_RUNNER_MODE") == "ignore_term":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
else:
    signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
record = f.open_record("fake", run_id, lease_holder=holder, receipt_dir=out, test_mode=True)
engine = subprocess.Popen([sys.executable, "-c", "import time\\nwhile True: time.sleep(0.05)"], start_new_session=True)
record.update(engine_pgid=engine.pid)
with open(os.path.join(out, "engine.pid"), "w") as pid_file:
    pid_file.write(str(engine.pid))
end = time.monotonic() + float(os.environ.get("FAKE_RUNNER_S", "60"))
while not stop and time.monotonic() < end:
    time.sleep(0.05)
for sig in (signal.SIGTERM, signal.SIGKILL):
    try:
        os.killpg(engine.pid, sig)
    except ProcessLookupError:
        break
    try:
        engine.wait(timeout=2)
        break
    except subprocess.TimeoutExpired:
        pass
code = 20 if stop else 0
record.close(code)
sys.exit(code)
"""

HELPER = """
import subprocess, sys
child = subprocess.Popen(sys.argv[2:], start_new_session=True)
rc = child.wait()
with open(sys.argv[1], "w") as marker:
    marker.write(f"released after exit {rc}\\n")
"""


def module():
    spec = importlib.util.spec_from_file_location("narrate_finalize", FINALIZE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


fin = module()


def alive(pid):
    st = fin.proc_stat(pid)
    return st is not None and st["state"] not in ("Z", "X")


def wait_for(predicate, seconds=15.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


@pytest.fixture
def lab(tmp_path):
    """A runs directory, the fake runner and lease helper, and every process started, killed at the end."""
    procs = []

    class Lab:
        runs = tmp_path / "narrate-runs"
        out = tmp_path / "out"
        runner = tmp_path / "runner.py"
        helper = tmp_path / "lease" / "fixture_gpu_lease.py"
        released = tmp_path / "released"

        def start(self, run_id, holder=HOLDER, *, via_helper=False, env=None, argv=None):
            cmd = argv or [sys.executable, str(self.runner), str(FINALIZE), run_id, holder, str(self.out)]
            if via_helper:
                cmd = [sys.executable, str(self.helper), str(self.released), *cmd]
            proc = subprocess.Popen(cmd, env={**os.environ, **(env or {})}, start_new_session=True)
            procs.append(proc)
            assert wait_for(lambda: self.record(run_id).get("engine_pgid")), "the runner never wrote its record"
            return proc

        def record(self, run_id):
            try:
                return json.loads((self.runs / f"{run_id}.json").read_text())
            except (OSError, ValueError):
                return {}

        def engine_pid(self):
            return int((self.out / "engine.pid").read_text())

    lab = Lab()
    lab.out.mkdir()
    lab.runner.write_text(RUNNER)
    lab.helper.parent.mkdir()
    lab.helper.write_text(HELPER)
    yield lab
    for proc in procs:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
    if (lab.out / "engine.pid").exists() and alive(lab.engine_pid()):
        os.kill(lab.engine_pid(), signal.SIGKILL)


def strings(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)
    elif isinstance(value, str):
        yield value


def test_operator_finalize_stops_the_runner_and_its_engine_and_writes_a_values_free_receipt(lab, tmp_path):
    proc = lab.start("run-a")
    engine = lab.engine_pid()
    code, receipt = fin.finalize("run-a", reason="operator", directory=lab.runs)
    assert code == 0, receipt
    assert proc.wait(timeout=5) == 20
    assert not alive(engine)
    assert [(s["signal"], s["target"]) for s in receipt["signals"]] == [("SIGTERM", "process_group")]
    assert receipt["reason"] == "operator" and receipt["call_id"] is None
    assert (receipt["runner_exit_status"], receipt["runner_closed_record"]) == (20, True)
    assert (receipt["engine_gone"], receipt["lease_helper"], receipt["outcome"]) == (True, "not_local", "stopped")
    assert receipt["lease_holder"] == HOLDER and receipt["ruling"].startswith("J130")
    assert receipt["requested_utc"] <= receipt["runner_gone_utc"] <= receipt["finished_utc"]
    assert json.loads((lab.runs / "run-a.finalize.json").read_text()) == receipt
    assert json.loads((lab.out / "run-a.finalize.json").read_text()) == receipt  # the run's own receipt dir
    assert not any("/" in s for s in strings({k: v for k, v in receipt.items() if k != "schema"}))  # no path


def test_the_preempt_hook_selects_by_holder_and_waits_for_the_local_lease_helper(lab):
    proc = lab.start("run-b", "narrate-bench-20261028-s203000", via_helper=True)
    cli = subprocess.run(
        [
            sys.executable,
            str(FINALIZE),
            "--runs-dir",
            str(lab.runs),
            "finalize",
            "--holder",
            "narrate-bench-20261028-s203000",
        ]
        + ["--reason", "preempted", "--call-id", "call-42"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert cli.returncode == 0, cli.stderr
    receipt = json.loads(cli.stdout)
    assert (receipt["run_id"], receipt["reason"], receipt["call_id"]) == ("run-b", "preempted", "call-42")
    assert receipt["lease_helper"] == "exited" and receipt["lease_helper_gone_utc"]
    assert lab.released.read_text() == "released after exit 20\n"  # the helper saw the runner's exit, then left
    proc.wait(timeout=5)


def test_a_runner_that_ignores_sigterm_is_killed_only_after_its_engine(lab):
    proc = lab.start("run-c", env={"FAKE_RUNNER_MODE": "ignore_term"})
    engine = lab.engine_pid()
    code, receipt = fin.finalize("run-c", reason="operator", directory=lab.runs, grace_s=1.0, kill_wait_s=2.0)
    assert code == 0, receipt
    assert proc.wait(timeout=5) == -signal.SIGKILL
    assert not alive(engine)
    order = [(s["signal"], s["target"]) for s in receipt["signals"]]
    assert order[0] == ("SIGTERM", "process_group") and order[-1] == ("SIGKILL", "process_group")
    assert ("SIGTERM", "engine") in order[1:-1]  # the engine is stopped before the runner's exit frees the Lease
    assert receipt["engine_processes_seen"] >= 1 and receipt["engine_gone"] is True
    assert (receipt["runner_closed_record"], receipt["runner_exit_status"]) == (False, None)


def test_a_runner_that_does_not_lead_its_group_is_signalled_alone(lab):
    # The group leader is a sleep standing in for a lease helper that shares the runner's group.
    argv = [sys.executable, str(lab.runner), str(FINALIZE), "run-d", HOLDER, str(lab.out)]
    cmd = " ".join(f"'{a}'" for a in argv)
    leader = lab.start("run-d", argv=["sh", "-c", f"{cmd} & exec sleep 60"])
    code, receipt = fin.finalize("run-d", reason="operator", directory=lab.runs)
    assert code == 0, receipt
    assert receipt["signals"][0]["target"] == "process"
    assert leader.poll() is None  # the group mate got no signal


def test_unknown_malformed_and_already_finalized_runs_are_refused(lab):
    with pytest.raises(fin.Refusal, match="unknown run id"):
        fin.finalize("no-such-run", reason="operator", directory=lab.runs)
    with pytest.raises(fin.Refusal, match="not a plain name"):
        fin.finalize("../escape", reason="operator", directory=lab.runs)
    with pytest.raises(fin.Refusal, match="no unfinalized run record"):
        fin.finalize("latest", reason="operator", directory=lab.runs)
    with pytest.raises(fin.Refusal, match="--call-id goes with --reason preempted"):
        fin.finalize("latest", reason="operator", call_id="c1", directory=lab.runs)
    lab.start("run-e")
    assert fin.finalize("run-e", reason="operator", directory=lab.runs)[0] == 0
    with pytest.raises(fin.Refusal, match="already finalized"):
        fin.finalize("run-e", reason="operator", directory=lab.runs)
    cli = subprocess.run(
        [sys.executable, str(FINALIZE), "--runs-dir", str(lab.runs), "finalize", "nope", "--reason", "operator"],
        capture_output=True,
        text=True,
    )
    assert cli.returncode == 2 and "unknown run id" in cli.stderr


def write_record(lab, run_id, **runner):
    lab.runs.mkdir(exist_ok=True)
    base = {"pid": 0, "pgid": 0, "starttime": 0, "uid": os.getuid()}
    record = {
        "schema": fin.RECORD_SCHEMA,
        "run_id": run_id,
        "kind": "fake",
        "lease_holder": HOLDER,
        "runner": {**base, **runner},
        "boot_id": fin.boot_id(),
        "engine_pgid": None,
        "cgroup": None,
        "receipt_dir": None,
        "started_utc": fin.now(),
        "state": "running",
        "ended_utc": None,
        "exit_status": None,
        "test_mode": True,
    }
    (lab.runs / f"{run_id}.json").write_text(json.dumps(record))
    return record


def test_stale_records_are_refused_and_signal_nothing(lab):
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    write_record(lab, "gone", pid=gone.pid, pgid=gone.pid, starttime=1)
    with pytest.raises(fin.Refusal, match="pid is gone"):
        fin.finalize("gone", reason="operator", directory=lab.runs)

    bystander = subprocess.Popen(["sleep", "60"], start_new_session=True)
    try:
        st = fin.proc_stat(bystander.pid)
        write_record(lab, "reused", pid=bystander.pid, pgid=st["pgid"], starttime=st["starttime"] + 1)
        with pytest.raises(fin.Refusal, match="another process"):
            fin.finalize("reused", reason="operator", directory=lab.runs)
        record = write_record(lab, "reboot", pid=bystander.pid, pgid=st["pgid"], starttime=st["starttime"])
        record["boot_id"] = "another-boot"
        (lab.runs / "reboot.json").write_text(json.dumps(record))
        with pytest.raises(fin.Refusal, match="another boot"):
            fin.finalize("reboot", reason="operator", directory=lab.runs)
        assert bystander.poll() is None  # never signalled
        assert not list(lab.runs.glob("*.finalize.json"))
        assert {r["run_id"]: r["state"].split(":")[0] for r in fin.listing(lab.runs)} == {
            "gone": "stale",
            "reused": "stale",
            "reboot": "stale",
        }
    finally:
        bystander.kill()
        bystander.wait()


def test_finished_closes_an_ended_run_without_a_signal_and_is_refused_on_a_live_one(lab):
    proc = lab.start("run-f")
    with pytest.raises(fin.Refusal, match="still running"):
        fin.finalize("run-f", reason="finished", directory=lab.runs)
    proc.send_signal(signal.SIGTERM)  # the run ends on its own path
    assert proc.wait(timeout=5) == 20
    code, receipt = fin.finalize("latest", reason="finished", directory=lab.runs)
    assert code == 0
    assert (receipt["signals"], receipt["outcome"], receipt["runner_exit_status"]) == ([], "already_ended", 20)


def test_latest_is_the_newest_unfinalized_record(lab):
    lab.start("run-g1", "narrate-bench-20261028-s201000")
    lab.start("run-g2", "narrate-bench-20261028-s202000")
    assert fin.finalize("latest", reason="operator", directory=lab.runs)[1]["run_id"] == "run-g2"
    assert fin.finalize("latest", reason="operator", directory=lab.runs)[1]["run_id"] == "run-g1"


def test_a_run_record_is_written_once_per_id(lab):
    lab.runs.mkdir()
    fin.open_record("fake", "once", directory=lab.runs)
    with pytest.raises(fin.Refusal, match="exists"):
        fin.open_record("fake", "once", directory=lab.runs)
    with pytest.raises(fin.Refusal, match="plain name"):
        fin.open_record("fake", "a/b", directory=lab.runs)


def test_only_the_lease_guard_holder_form_is_accepted(lab):
    """TIN-7564 ec74214b: the GPU Lease guard admits narrate holders matching narrate-bench-YYYYMMDD-sHHMMSS."""
    lab.runs.mkdir()
    for bad in ("holder-1", "narrate-bench-20261023-s1526140", "narrate-bench-20261028-s20000", "x/narrate-bench"):
        with pytest.raises(fin.Refusal, match="narrate-bench-YYYYMMDD-sHHMMSS"):
            fin.open_record("fake", "bad-holder", lease_holder=bad, directory=lab.runs)
        with pytest.raises(fin.Refusal, match="narrate-bench-YYYYMMDD-sHHMMSS"):
            fin.finalize(holder=bad, reason="preempted", directory=lab.runs)
    assert not list(lab.runs.iterdir())
    fin.open_record("fake", "no-holder", lease_holder=None, directory=lab.runs)  # a run without a Lease
    made = fin.new_holder()
    assert fin.HOLDER.match(made) and fin.check_holder(made) == made
    cli = subprocess.run([sys.executable, str(FINALIZE), "holder"], capture_output=True, text=True, check=True)
    assert fin.HOLDER.match(cli.stdout.strip())
    assert fin.new_holder(fin.datetime.datetime(2026, 10, 23, 15, 26, 14)) == "narrate-bench-20261023-s152614"
