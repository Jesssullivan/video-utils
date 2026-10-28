#!/usr/bin/env python3
"""Run records for narrate GPU runs, and the finalize path that stops one by hand (J130, TIN-7564).

Standard library only, Python 3.9 or later, Linux /proc: the GPU host runs this file beside audiocpp_batch.py and
never imports narrate. J130(a) lets narration runs hold the GPU Lease unattended; J130(b) says a ringing live call
preempts them. Until TIN-7564's machine preempt lands, a waiting call relies on the run's time cap or on an operator
finalizing the run with this file. It takes no Lease and reads no Lease: the lease helper that started the run
releases the Lease in its own `finally` once the run's command exits.

Run record. Each narrate GPU run (audiocpp_batch.py run, a run-bench.sh window) writes
RUNS/<run_id>.json when it starts and rewrites it when it ends. RUNS is NARRATE_RUNS_DIR, else
$XDG_RUNTIME_DIR/narrate-runs, else ~/.local/state/narrate/runs (mode 0700); never a path in git. The record holds
the run id, its kind, the Lease holder, the runner's pid, process group and start time (clock ticks after boot, so
a reused pid is told apart), the boot id, the engine's process group and the run's cgroup when known, the run's
own receipt directory, the state (running, then ended) and the runner's exit status.

    finalize.py list                                        every record: id, kind, holder, state, live
    finalize.py holder                                      a new Lease holder: narrate-bench-YYYYMMDD-sHHMMSS
    finalize.py finalize RUN|latest --reason operator       stop one run by hand
    finalize.py finalize --holder H --reason preempted [--call-id ID]   the hook a preempt watcher calls

finalize, in order:

1. refuses an unknown or malformed run id, a run already finalized, a record from another boot, and a record whose
   runner pid is gone or now names another process (start time or owner differ) while the record says running.
   `latest` is the newest record not yet finalized; `--holder H` the newest one naming that Lease holder. A
   holder must have the one form the GPU Lease guard admits, narrate-bench-YYYYMMDD-sHHMMSS (UTC), and so must
   the holder a runner records;
2. a run that already ended gets no signal (reason `finished` asks for exactly this, and is refused on a live run);
3. otherwise sends SIGTERM to the runner: to its process group when it leads that group, else to its pid alone, so
   a caller sharing the group (the lease helper) is never signalled. The runner's own handler stops the engine
   (SIGTERM, then SIGKILL, then waits for it to be gone), writes its GPU-free evidence and receipt, and exits;
4. waits --grace-s (60) for the runner to exit. If it has not, it stops every process it saw under the runner, the
   engine group and the cgroup (SIGTERM, --kill-wait-s, then SIGKILL) and only then sends SIGKILL to the runner,
   so the runner's exit, which lets the lease helper release, comes after the engine is gone;
5. checks that every engine process it saw is gone (SIGTERM, then SIGKILL, for any left);
6. waits --lease-wait-s (60) for the lease helper to exit when it runs on this host (an ancestor of the runner whose
   argv names a script ending in _gpu_lease.py, the estate's lease helper). Its exit means its `finally` ran the
   release; its own receipt says how the release went. A helper on another host (the run started over ssh) is
   recorded as not_local: confirm the release there with the helper's receipt or its `show`;
7. writes a values-free receipt, RUNS/<run_id>.finalize.json and a copy in the run's receipt directory: the reason
   (preempted with an optional call id, operator, or finished), the times, each signal sent, the runner's exit
   status and whether the engine and the lease helper are gone. No path, command line, environment or text.

Exit codes: 0 finalized; 1 something survived (the runner, an engine process, or a local lease helper still
running at the end of its wait); 2 refused.
"""

import argparse
import datetime
import json
import os
import re
import signal
import sys
import time
from pathlib import Path

RECORD_SCHEMA = "narrate-gpu-run-record/1"
RECEIPT_SCHEMA = "narrate-gpu-run-finalize-receipt/1"
RULING = "J130; R-HOOK-CONVERGENCE-20261004 R-N13"
TICKET = "TIN-7564"
REASONS = ("preempted", "operator", "finished")
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,200}$")
# The only Lease holder form the GPU Lease guard admits for narrate (TIN-7564 ec74214b): UTC date and time of day,
# made by `just narrate-holder` or narrate-bench-$(date -u +%Y%m%d-s%H%M%S).
HOLDER = re.compile(r"^narrate-bench-[0-9]{8}-s[0-9]{6}$")
HOLDER_FORM = "narrate-bench-YYYYMMDD-sHHMMSS (just narrate-holder)"
CALL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
HELPER_SUFFIX = "_gpu_lease.py"  # the lease helper script; no host name in git
EXIT_OK, EXIT_SURVIVED, EXIT_REFUSED = 0, 1, 2
TICK_S = 0.1
ANCESTORS = 16


class Refusal(Exception):
    pass


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def runs_dir(env=None):
    env = os.environ if env is None else env
    if env.get("NARRATE_RUNS_DIR"):
        return Path(env["NARRATE_RUNS_DIR"])
    if env.get("XDG_RUNTIME_DIR"):
        return Path(env["XDG_RUNTIME_DIR"]) / "narrate-runs"
    return Path.home() / ".local" / "state" / "narrate" / "runs"


def boot_id():
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return None


def proc_stat(pid):
    """{state, ppid, pgid, starttime} of a pid from /proc/<pid>/stat, or None when it is gone."""
    try:
        text = Path(f"/proc/{int(pid)}/stat").read_text()
    except (OSError, ValueError):
        return None
    fields = text[text.rindex(")") + 2 :].split()  # the name may hold spaces or parentheses
    return {"state": fields[0], "ppid": int(fields[1]), "pgid": int(fields[2]), "starttime": int(fields[19])}


def proc_uid(pid):
    try:
        return os.stat(f"/proc/{int(pid)}").st_uid
    except (OSError, ValueError):
        return None


def alive(pid, starttime):
    """True while pid is the process that started at starttime and is not a zombie."""
    st = proc_stat(pid)
    return st is not None and st["starttime"] == starttime and st["state"] not in ("Z", "X")


def all_stats():
    out = {}
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            st = proc_stat(entry)
            if st is not None:
                out[int(entry)] = st
    return out


def write_json(path, value):
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(value, indent=1, sort_keys=True) + "\n")
    os.replace(tmp, path)


def check_holder(holder):
    """None, or a Lease holder in the one form the Lease guard admits; else Refusal."""
    if holder is not None and not HOLDER.match(holder):
        raise Refusal(f"Lease holder {holder!r} is not of the form {HOLDER_FORM}")
    return holder


def new_holder(at=None):
    """A Lease holder for a run starting now (UTC), the form the Lease guard admits."""
    at = at or datetime.datetime.now(datetime.timezone.utc)
    return at.strftime("narrate-bench-%Y%m%d-s%H%M%S")


# ---- the runner side --------------------------------------------------------------------------------------------


class Record:
    """One run's record. The runner opens it at start, may add the engine group, and closes it at exit."""

    def __init__(self, path, data):
        self.path, self.data = path, data

    def update(self, **fields):
        self.data.update(fields)
        write_json(self.path, self.data)

    def close(self, exit_status):
        self.update(state="ended", ended_utc=now(), exit_status=exit_status)


def open_record(kind, run_id, lease_holder=None, receipt_dir=None, directory=None, test_mode=False):
    """Write RUNS/<run_id>.json for this process (the runner) and return its Record."""
    if not RUN_ID.match(run_id):
        raise Refusal(f"run id {run_id!r} is not a plain name")
    check_holder(lease_holder)
    directory = Path(directory) if directory else runs_dir()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / f"{run_id}.json"
    if path.exists():
        raise Refusal(f"a run record for {run_id} exists; every run gets a new id")
    me = proc_stat(os.getpid()) or {"pgid": os.getpgid(0), "starttime": None}  # no /proc: finalize refuses it
    data = {
        "schema": RECORD_SCHEMA,
        "run_id": run_id,
        "kind": kind,
        "lease_holder": lease_holder,
        "runner": {"pid": os.getpid(), "pgid": me["pgid"], "starttime": me["starttime"], "uid": os.getuid()},
        "boot_id": boot_id(),
        "engine_pgid": None,
        "cgroup": None,
        "receipt_dir": str(Path(receipt_dir).resolve()) if receipt_dir else None,
        "started_utc": now(),
        "state": "running",
        "ended_utc": None,
        "exit_status": None,
        "test_mode": bool(test_mode),
    }
    write_json(path, data)
    return Record(path, data)


# ---- the finalize side ------------------------------------------------------------------------------------------


def receipt_path(directory, run_id):
    return directory / f"{run_id}.finalize.json"


def load_records(directory):
    records = []
    if not directory.is_dir():
        return records
    for path in directory.glob("*.json"):
        if path.name.endswith(".finalize.json") or path.name.startswith("."):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("schema") == RECORD_SCHEMA and data.get("run_id") == path.stem:
            records.append(data)
    records.sort(key=lambda r: (str(r.get("started_utc")), r["runner"].get("starttime", 0)))
    return records


def runner_live(record):
    """'live', 'ended', or why the record is stale."""
    if record.get("state") == "ended":
        return "ended"
    if record.get("boot_id") and record.get("boot_id") != boot_id():
        return "stale: the record is from another boot"
    runner = record.get("runner") or {}
    pid, start = runner.get("pid"), runner.get("starttime")
    if not isinstance(pid, int) or not isinstance(start, int) or pid <= 1:
        return "stale: the record names no runner pid"
    st = proc_stat(pid)
    if st is None or st["state"] in ("Z", "X"):
        return "stale: the runner pid is gone and the record never ended"
    if st["starttime"] != start:
        return "stale: the runner pid now names another process (start time differs)"
    if proc_uid(pid) != os.getuid() or runner.get("uid", os.getuid()) != os.getuid():
        return "stale: the runner pid is not this user's process"
    return "live"


def select(directory, run=None, holder=None):
    if holder is not None:
        check_holder(holder)
        found = [r for r in load_records(directory) if r.get("lease_holder") == holder]
        found = [r for r in found if not receipt_path(directory, r["run_id"]).exists()]
        if not found:
            raise Refusal(f"no unfinalized run record names Lease holder {holder}")
        return found[-1]
    if run in (None, "latest"):
        found = [r for r in load_records(directory) if not receipt_path(directory, r["run_id"]).exists()]
        if not found:
            raise Refusal("no unfinalized run record")
        return found[-1]
    if not RUN_ID.match(run):
        raise Refusal(f"run id {run!r} is not a plain name")
    for record in load_records(directory):
        if record["run_id"] == run:
            if receipt_path(directory, run).exists():
                raise Refusal(f"{run} is already finalized")
            return record
    raise Refusal(f"unknown run id {run}")


def descendants(root_pid, stats):
    children = {}
    for pid, st in stats.items():
        children.setdefault(st["ppid"], []).append(pid)
    out, todo = set(), [root_pid]
    while todo:
        for child in children.get(todo.pop(), ()):
            if child not in out:
                out.add(child)
                todo.append(child)
    return out


def cgroup_pids(cgroup):
    if not cgroup:
        return set()
    try:
        text = (Path("/sys/fs/cgroup") / cgroup.lstrip("/") / "cgroup.procs").read_text()
    except OSError:
        return set()
    return {int(line) for line in text.split() if line.isdigit()}


def engine_watch(record, seen):
    """Add to seen {pid: starttime} every process under the runner, in the engine group or in the run's cgroup."""
    stats = all_stats()
    runner = record["runner"]["pid"]
    pids = descendants(runner, stats) | cgroup_pids(record.get("cgroup"))
    pgid = record.get("engine_pgid")
    if isinstance(pgid, int) and pgid > 1:
        pids |= {pid for pid, st in stats.items() if st["pgid"] == pgid}
    for pid in pids - {runner, os.getpid()}:
        st = stats.get(pid)
        if st is not None and st["state"] not in ("Z", "X") and proc_uid(pid) == os.getuid():
            seen.setdefault(pid, st["starttime"])
    return seen


def remaining(seen):
    return {pid: start for pid, start in seen.items() if alive(pid, start)}


def wait_until(predicate, seconds):
    end = time.monotonic() + seconds
    while not predicate():
        if time.monotonic() >= end:
            return predicate()
        time.sleep(TICK_S)
    return True


def stop_seen(seen, kill_wait_s, sent):
    """SIGTERM, wait, then SIGKILL every seen process still alive; True when all are gone."""
    for sig, wait in ((signal.SIGTERM, kill_wait_s), (signal.SIGKILL, max(kill_wait_s / 2, 1.0))):
        left = remaining(seen)
        if not left:
            return True
        for pid in left:
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, PermissionError):
                pass
        sent.append({"signal": sig.name, "target": "engine", "count": len(left), "sent_utc": now()})
        if wait_until(lambda: not remaining(seen), wait):
            return True
    return not remaining(seen)


def signal_runner(record, sig):
    runner = record["runner"]
    if runner["pgid"] == runner["pid"]:
        os.killpg(runner["pid"], sig)
        return "process_group"
    os.kill(runner["pid"], sig)
    return "process"


def find_helper(pid, helper_suffix=HELPER_SUFFIX):
    """The nearest ancestor of pid whose argv names the lease helper (a basename ending in helper_suffix), as
    (pid, starttime), or None."""
    for _ in range(ANCESTORS):
        st = proc_stat(pid)
        if st is None or st["ppid"] <= 1:
            return None
        pid = st["ppid"]
        try:
            argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        except OSError:
            return None
        if any(os.path.basename(a.decode("utf-8", "replace")).endswith(helper_suffix) for a in argv):
            parent = proc_stat(pid)
            return (pid, parent["starttime"]) if parent else None
    return None


def finalize(
    run=None,
    *,
    reason,
    call_id=None,
    holder=None,
    directory=None,
    grace_s=60.0,
    kill_wait_s=10.0,
    lease_wait_s=60.0,
    helper_suffix=HELPER_SUFFIX,
):
    """Stop one narrate GPU run and write its finalize receipt. Returns (exit code, receipt).

    The hook a preempt watcher calls: finalize(holder=H, reason="preempted", call_id=ID). Raises Refusal."""
    if reason not in REASONS:
        raise Refusal(f"--reason must be one of {', '.join(REASONS)}")
    if call_id is not None:
        if reason != "preempted":
            raise Refusal("--call-id goes with --reason preempted only")
        if not CALL_ID.match(call_id):
            raise Refusal(f"call id {call_id!r} is not a plain id")
    directory = Path(directory) if directory else runs_dir()
    record = select(directory, None if holder is not None and run == "latest" else run, holder)
    state = runner_live(record)
    if state.startswith("stale"):
        raise Refusal(f"{record['run_id']}: {state}; nothing signalled")
    if reason == "finished" and state == "live":
        raise Refusal(f"{record['run_id']} is still running; --reason finished is for a run that ended")

    started = time.monotonic()
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "ruling": RULING,
        "ticket": TICKET,
        "run_id": record["run_id"],
        "kind": record.get("kind"),
        "lease_holder": record.get("lease_holder"),
        "reason": reason,
        "call_id": call_id,
        "requested_utc": now(),
        "run_started_utc": record.get("started_utc"),
        "state_at_request": state,
        "signals": [],
        "test_mode": bool(record.get("test_mode")),
    }
    sent = receipt["signals"]
    seen = {}
    helper = None
    runner = record["runner"]
    if state == "live":
        helper = find_helper(runner["pid"], helper_suffix)
        engine_watch(record, seen)
        target = signal_runner(record, signal.SIGTERM)
        sent.append({"signal": "SIGTERM", "target": target, "sent_utc": now()})

        def exited():  # keep watching the runner's children while it stops them
            if alive(runner["pid"], runner["starttime"]):
                engine_watch(record, seen)
                return False
            return True

        if not wait_until(exited, grace_s):
            stop_seen(seen, kill_wait_s, sent)  # the engine first: the runner's exit lets the Lease go
            if alive(runner["pid"], runner["starttime"]):
                try:
                    target = signal_runner(record, signal.SIGKILL)
                    sent.append({"signal": "SIGKILL", "target": target, "sent_utc": now()})
                except ProcessLookupError:
                    pass
                wait_until(lambda: not alive(runner["pid"], runner["starttime"]), max(kill_wait_s, 1.0))
    runner_gone = not alive(runner["pid"], runner["starttime"])
    receipt["runner_gone"] = runner_gone
    receipt["runner_gone_utc"] = now() if runner_gone else None
    engine_gone = stop_seen(seen, kill_wait_s, sent)
    receipt["engine_processes_seen"] = len(seen)
    receipt["engine_gone"] = engine_gone

    try:
        closed = json.loads((directory / f"{record['run_id']}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        closed = record
    receipt["runner_closed_record"] = closed.get("state") == "ended"
    receipt["runner_exit_status"] = closed.get("exit_status") if closed.get("state") == "ended" else None

    if helper is None:
        receipt["lease_helper"] = "not_local"
        receipt["lease_helper_gone_utc"] = None
    elif wait_until(lambda: not alive(*helper), lease_wait_s):
        receipt["lease_helper"] = "exited"
        receipt["lease_helper_gone_utc"] = now()
    else:
        receipt["lease_helper"] = "still_running"
        receipt["lease_helper_gone_utc"] = None
    receipt["finished_utc"] = now()
    receipt["wall_s"] = round(time.monotonic() - started, 3)
    survived = not runner_gone or not engine_gone or receipt["lease_helper"] == "still_running"
    receipt["outcome"] = "survived" if survived else ("already_ended" if state == "ended" else "stopped")

    write_json(receipt_path(directory, record["run_id"]), receipt)
    own = record.get("receipt_dir")
    if own and Path(own).is_dir():
        try:
            write_json(Path(own) / f"{record['run_id']}.finalize.json", receipt)
        except OSError:
            pass
    return (EXIT_SURVIVED if survived else EXIT_OK), receipt


def listing(directory):
    rows = []
    for record in load_records(directory):
        rows.append(
            {
                "run_id": record["run_id"],
                "kind": record.get("kind"),
                "lease_holder": record.get("lease_holder"),
                "started_utc": record.get("started_utc"),
                "state": runner_live(record),
                "finalized": receipt_path(directory, record["run_id"]).exists(),
            }
        )
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(prog="finalize.py", description=__doc__.split("\n\n")[0])
    p.add_argument("--runs-dir", default=None, help="default: NARRATE_RUNS_DIR, else $XDG_RUNTIME_DIR/narrate-runs")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("holder", help="print a new Lease holder for a run starting now")
    f = sub.add_parser("finalize")
    f.add_argument("run", nargs="?", default=None, help="a run id or latest (default latest)")
    f.add_argument("--holder", default=None, help="the newest unfinalized run naming this Lease holder")
    f.add_argument("--reason", required=True, choices=REASONS)
    f.add_argument("--call-id", default=None, help="the live call that preempts the run (with --reason preempted)")
    f.add_argument("--grace-s", type=float, default=60.0)
    f.add_argument("--kill-wait-s", type=float, default=10.0)
    f.add_argument("--lease-wait-s", type=float, default=60.0)
    f.add_argument("--helper-suffix", default=HELPER_SUFFIX)
    a = p.parse_args(argv)
    directory = Path(a.runs_dir) if a.runs_dir else runs_dir()
    if a.command == "list":
        print(json.dumps(listing(directory), indent=1))
        return EXIT_OK
    if a.command == "holder":
        print(new_holder())
        return EXIT_OK
    if a.run not in (None, "latest") and a.holder is not None:
        print(json.dumps({"ok": False, "refused": "give a run id or --holder, not both"}), file=sys.stderr)
        return EXIT_REFUSED
    try:
        code, receipt = finalize(
            a.run,
            reason=a.reason,
            call_id=a.call_id,
            holder=a.holder,
            directory=directory,
            grace_s=a.grace_s,
            kill_wait_s=a.kill_wait_s,
            lease_wait_s=a.lease_wait_s,
            helper_suffix=a.helper_suffix,
        )
    except Refusal as error:
        print(json.dumps({"ok": False, "refused": str(error)}), file=sys.stderr)
        return EXIT_REFUSED
    print(json.dumps(receipt, indent=1, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
