#!/usr/bin/env python3
"""Run one narrate request batch through audio.cpp's audiocpp_cli, and write the receipt narrate binds takes to.

Phase B of an AudioCppBatch render (narrate/prerender.py, docs/spec/NARRATE.md "Out-of-process batch engines").
Standard library only, Python 3.9 or later: the GPU host runs this file on its own interpreter and never imports
narrate. It takes no lease, opens no device node and sets no resource limit: the caller runs it inside the window's
bounded unit, with VK_DRIVER_FILES naming the RADV ICD, and watches VRAM.

    audiocpp_batch.py run DIR --requests requests/NAME.json --binary PATH --binary-sha256 SHA \\
        --model PATH --model-sha256 SHA [--family voxcpm2] [--backend vulkan] [--device 0] \\
        [--audiocpp-commit REV] [--deadline-s N] [--stall-s N] [--only-missing] [--lease-holder H]
    audiocpp_batch.py check DIR --requests requests/NAME.json     the request and reference checks alone

DIR is a `narrate plan` directory (copied to the GPU host): requests/, refs/ and plan.json. `run`:

1. reads the requests file and refuses (exit 2) a request whose id is not the digest of its content (the id rule
   of narrate/prerender.py), a key audiocpp_cli is not given by narrate, or a reference that is not
   refs/<sha256>.wav with that sha256;
2. hashes the binary and the weights and refuses a sha256 that differs from the one given;
3. writes the request sequence again with absolute reference paths under DIR/.run-NAME/, runs one
   `audiocpp_cli --task clon --family F --model M --backend B --device D --request-sequence R --out-dir O
   --out-format pcm16 --metrics` in its own process group, with stdout and stderr in DIR/logs/NAME.log;
4. stops the process group (SIGTERM, then SIGKILL after 10 s) at --deadline-s, after --stall-s seconds (default
   120, 0 for none) in which neither the log nor the output directory grew, or on SIGTERM, SIGHUP or SIGINT;
5. moves each finished, complete WAV to DIR/wav/<id>.wav. The pin prints `[TIMING] request.<id>.wall_ms` before it
   writes the WAV, then `audio_out=<path>` and `metrics[<id>].*` after it, so only an `audio_out` line naming the
   file or a `metrics[<id>]` line marks a request finished. After a clean exit every complete WAV counts; after a
   stop, only the finished ones. A WAV counts as complete when its RIFF size, its chunk sizes and a data chunk
   account for the file's length exactly, so a WAV cut short is dropped;
6. keeps a run record (narrate/serve/finalize.py, J130) from just before the runtime starts until it exits: this
   process's pid, process group and start time, the engine's process group and the Lease holder (--lease-holder,
   else NARRATE_LEASE_HOLDER). finalize.py must sit beside this file; `finalize.py finalize RUN --reason ...` sends
   this process SIGTERM, which stops the runtime as in step 4;
7. writes DIR/receipts/NAME.json: schema narrate-audiocpp-batch-receipt/1, the requests file and its sha256, each
   reference's sha256, runtime, commit, binary and weights sha256, family, task, backend, device, VK_DRIVER_FILES,
   exit code, stop rule, times, and every output's file and sha256. Missing outputs are listed, never invented.
   The pin prints no model load time, so the receipt records none.

--only-missing runs only the requests whose WAV is not yet in DIR/wav/ from an earlier receipt: it writes the subset
as requests/NAME.partK.json and its receipt as receipts/NAME.partK.json, so a window that stopped early can be
finished in the next one. Exit codes: 0 every request has its WAV; 1 some WAVs are missing; 2 refused before the
runtime started; 20 the runtime was stopped (deadline or signal).
"""

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

RECEIPT_SCHEMA = "narrate-audiocpp-batch-receipt/1"
ID_LENGTH = 32
SHA256 = re.compile(r"^[0-9a-f]{64}$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
KEYS = {"id", "text", "seed", "voice_ref", "audio", "reference_text"}
TASKS = {"voxcpm2": "clon"}
EXIT_OK, EXIT_PARTIAL, EXIT_REFUSED, EXIT_STOPPED = 0, 1, 2, 20
KILL_AFTER_S = 10
STALL_S = 120.0
FINISHED = (
    re.compile(r"^audio_out=(.+)$", re.M),  # the file's path; its stem is the request id
    re.compile(r"^metrics\[([^\]\s]+)\]\.", re.M),
)
WALL = (
    re.compile(r"request\.(\S+?)\.wall_ms[ =]([\d.]+)"),
    re.compile(r"^metrics\[([^\]\s]+)\]\.wall_ms=([\d.]+)", re.M),
)
STOP = {"signal": None}


class Refusal(Exception):
    pass


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    """narrate/ir.py canonical: sorted keys, no spaces, UTF-8."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def request_id(body):
    """narrate/prerender.py request_id: the digest of the request's content without its id."""
    content = {k: v for k, v in body.items() if k != "id"}
    return hashlib.sha256(canonical(content).encode("utf-8")).hexdigest()[:ID_LENGTH]


def inside(root, relative):
    if not isinstance(relative, str) or not relative or relative.startswith("/") or "\\" in relative:
        return None
    parts = relative.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return None
    return root.joinpath(*parts)


def load_batch(root, relative):
    """(requests, requests sha256, {ref path: sha256}) after every request and reference check."""
    path = inside(root, relative)
    if path is None or not relative.startswith("requests/") or not relative.endswith(".json"):
        raise Refusal(f"--requests {relative!r}: a requests/<name>.json inside the plan directory")
    if path.is_symlink() or not path.is_file():
        raise Refusal(f"{relative}: not a regular file")
    data = path.read_bytes()
    try:
        requests = json.loads(data)["requests"]
    except (ValueError, KeyError, TypeError):
        raise Refusal(f'{relative}: not a {{"requests": [...]}} file') from None
    if not isinstance(requests, list) or not requests:
        raise Refusal(f"{relative}: no requests")
    refs, seen = {}, set()
    for body in requests:
        if not isinstance(body, dict) or set(body) - KEYS or not {"id", "text", "seed"} <= set(body):
            raise Refusal(f"{relative}: a request has keys outside {sorted(KEYS)} or lacks id, text or seed")
        if body["id"] != request_id(body):
            raise Refusal(f"{relative}: request {body['id']!r} is not the digest of its content")
        if body["id"] in seen:
            raise Refusal(f"{relative}: request {body['id']} appears twice")
        seen.add(body["id"])
        for key in ("voice_ref", "audio"):
            if key not in body:
                continue
            ref = body[key]
            match = re.fullmatch(r"refs/([0-9a-f]{64})\.wav", str(ref))
            target = inside(root, ref)
            if not match or target is None or target.is_symlink() or not target.is_file():
                raise Refusal(f"{relative}: request {body['id']} {key} is not a stored refs/<sha256>.wav")
            if ref not in refs:
                digest = sha256_file(target)
                if digest != match.group(1):
                    raise Refusal(f"{ref}: sha256 is {digest}, not the one its name says")
                refs[ref] = digest
    return requests, hashlib.sha256(data).hexdigest(), refs


def check_pin(path, want, what):
    if not SHA256.match(want or ""):
        raise Refusal(f"--{what}-sha256 must be 64 lowercase hex digits")
    path = Path(path)
    if not path.is_file():
        raise Refusal(f"{what} missing: {path.name}")
    got = sha256_file(path)
    if got != want:
        raise Refusal(f"{what} {path.name}: sha256 {got}, want {want}")


def done_ids(root):
    """Request ids an earlier receipt in DIR/receipts/ holds a WAV for that is still there with its sha256."""
    out = {}
    for receipt in sorted((root / "receipts").glob("*.json")):
        try:
            outputs = json.loads(receipt.read_text(encoding="utf-8")).get("outputs") or {}
        except (OSError, ValueError):
            continue
        for rid, entry in outputs.items():
            path = root / "wav" / f"{rid}.wav"
            if isinstance(entry, dict) and path.is_file() and sha256_file(path) == entry.get("sha256"):
                out[rid] = entry
    return out


def part_name(root, name):
    k = 1
    while any((root / sub / f"{name}.part{k}.json").exists() for sub in ("receipts", "requests")):
        k += 1
    return f"{name}.part{k}"


def wav_complete(data):
    """True when a RIFF/WAVE file's sizes account for every byte: the RIFF size is the length less 8, each chunk
    (padded to an even size) ends inside the file, the last ends at its end, and fmt and data chunks exist. A WAV
    whose header was written for the whole take but whose samples stop short fails."""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return False
    if int.from_bytes(data[4:8], "little") != len(data) - 8:
        return False
    at, seen = 12, set()
    while at < len(data):
        if at + 8 > len(data):
            return False
        size = int.from_bytes(data[at + 4 : at + 8], "little")
        seen.add(data[at : at + 4])
        at += 8 + size + (size & 1)
        if at > len(data) + (size & 1):
            return False
    return {b"fmt ", b"data"} <= seen


def wav_ok(path):
    return wav_complete(path.read_bytes())


def finished_ids(text):
    """Request ids the runtime reported finished: an `audio_out=` path's stem, or a `metrics[<id>]` line."""
    done = {Path(m.group(1).strip()).stem for m in FINISHED[0].finditer(text)}
    return done | {m.group(1) for m in FINISHED[1].finditer(text)}


def progress(log, out_dir):
    """What grows while the runtime works: the log's size and the output directory's bytes."""
    try:
        size = log.stat().st_size
        return size, sum(p.stat().st_size for p in out_dir.iterdir())
    except OSError:
        return None


def on_signal(signum, _frame):
    STOP["signal"] = signal.Signals(signum).name


def stop_group(proc):
    for sig, wait in ((signal.SIGTERM, KILL_AFTER_S), (signal.SIGKILL, 5)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return True
        try:
            proc.wait(timeout=wait)
            return True
        except subprocess.TimeoutExpired:
            continue
    return proc.poll() is not None


def run_records():
    """finalize.py from beside this file: the run record a manual or preempting finalize reads (J130)."""
    path = Path(__file__).resolve().with_name("finalize.py")
    if not path.is_file():
        raise Refusal("finalize.py is not beside audiocpp_batch.py; copy both to the GPU host (the run record, J130)")
    spec = importlib.util.spec_from_file_location("narrate_finalize", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path, value):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def run(a):
    root = Path(a.dir).resolve()
    if os.geteuid() == 0:
        raise Refusal("never run as root")
    if a.family not in TASKS:
        raise Refusal(f"--family {a.family!r}: one of {sorted(TASKS)}")
    requests, batch_sha, refs = load_batch(root, a.requests)
    name = Path(a.requests).stem
    if not NAME.match(name):
        raise Refusal(f"requests file name {name!r} is not a plain name")
    check_pin(a.binary, a.binary_sha256, "binary")
    check_pin(a.model, a.model_sha256, "model")
    holder = a.lease_holder or os.environ.get("NARRATE_LEASE_HOLDER") or None
    records = run_records()
    if holder is not None and not records.RUN_ID.match(holder):
        raise Refusal(f"Lease holder {holder!r} is not a plain name")
    for sub in ("wav", "receipts", "logs"):
        (root / sub).mkdir(mode=0o700, exist_ok=True)
    relative = a.requests
    if a.only_missing:
        done = done_ids(root)
        requests = [r for r in requests if r["id"] not in done]
        if not requests:
            print(json.dumps({"ok": True, "nothing_to_do": True, "done": len(done)}))
            return EXIT_OK
        name = part_name(root, name)
        relative = f"requests/{name}.json"
        data = (json.dumps({"requests": requests}, indent=1, ensure_ascii=False) + "\n").encode("utf-8")
        (root / relative).write_bytes(data)
        batch_sha = hashlib.sha256(data).hexdigest()
        refs = {k: v for k, v in refs.items() if any(k in (r.get("voice_ref"), r.get("audio")) for r in requests)}
    receipt_path = root / "receipts" / f"{name}.json"
    if receipt_path.exists():
        raise Refusal(f"receipts/{name}.json exists; a batch runs once (use --only-missing to finish it)")
    run_id = f"audiocpp-{name}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{os.getpid()}"
    try:
        record = records.open_record(
            "audiocpp-batch",
            run_id,
            lease_holder=holder,
            receipt_dir=root / "receipts",
            test_mode=os.environ.get("NARRATE_AUDIOCPP_BATCH_TEST_MODE") == "1",
        )
    except (records.Refusal, OSError) as error:
        raise Refusal(f"no run record: {error}") from None
    result = None
    try:
        result = batch(a, root, name, relative, requests, batch_sha, refs, receipt_path, record)
        return result
    finally:
        try:
            record.close(result)
        except OSError as error:
            print(json.dumps({"run_record": "not closed", "error": str(error)}), file=sys.stderr)


def batch(a, root, name, relative, requests, batch_sha, refs, receipt_path, record):
    work = root / f".run-{name}"
    work.mkdir(mode=0o700)
    absolute = []
    for body in requests:
        copy = dict(body)
        for key in ("voice_ref", "audio"):
            if key in copy:
                copy[key] = str(root / copy[key])
        absolute.append(copy)
    sequence = work / "requests.json"
    sequence.write_text(json.dumps({"requests": absolute}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    out_dir = work / "out"
    out_dir.mkdir()
    task = TASKS[a.family]
    argv = [str(Path(a.binary).resolve()), "--task", task, "--family", a.family]
    argv += ["--model", str(Path(a.model).resolve()), "--backend", a.backend, "--device", str(a.device)]
    argv += ["--request-sequence", str(sequence)]
    argv += ["--out-dir", str(out_dir), "--out-format", "pcm16", "--metrics"]
    log = root / "logs" / f"{name}.log"
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(sig, on_signal)
    started, started_utc = time.monotonic(), now()
    deadline = started + a.deadline_s if a.deadline_s else None
    rule, gone = "exit", True
    with open(log, "wb") as out:
        proc = subprocess.Popen(argv, cwd=work, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
        record.update(engine_pgid=proc.pid)
        seen, moved = None, time.monotonic()
        while proc.poll() is None:
            current = progress(log, out_dir)
            if current != seen:
                seen, moved = current, time.monotonic()
            if STOP["signal"]:
                rule = f"signal {STOP['signal']}"
            elif deadline and time.monotonic() > deadline:
                rule = f"deadline {a.deadline_s:g} s"
            elif a.stall_s and time.monotonic() - moved > a.stall_s:
                rule = f"stall {a.stall_s:g} s"
            if rule != "exit":
                gone = stop_group(proc)
                break
            time.sleep(0.2)
    code = proc.returncode
    ended = time.monotonic()
    text = log.read_text(encoding="utf-8", errors="replace")
    walls = {m.group(1): float(m.group(2)) for pattern in WALL for m in pattern.finditer(text)}
    finished = finished_ids(text)
    clean = rule == "exit" and code == 0
    outputs, missing = {}, []
    for body in requests:
        rid = body["id"]
        source = out_dir / f"{rid}.wav"
        if source.is_file() and not source.is_symlink() and (clean or rid in finished) and wav_ok(source):
            target = root / "wav" / f"{rid}.wav"
            source.replace(target)
            outputs[rid] = {"file": f"wav/{rid}.wav", "sha256": sha256_file(target), "bytes": target.stat().st_size}
            if rid in walls:
                outputs[rid]["wall_ms"] = walls[rid]
        else:
            missing.append(rid)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "requests_file": relative,
        "requests_sha256": batch_sha,
        "requests": len(requests),
        "refs": refs,
        "runtime": "audio.cpp audiocpp_cli",
        "audiocpp_commit": a.audiocpp_commit,
        "binary_sha256": a.binary_sha256,
        "model_sha256": a.model_sha256,
        "model_file": Path(a.model).name,
        "family": a.family,
        "task": task,
        "backend": a.backend,
        "device": str(a.device),
        "out_format": "pcm16",
        "vk_driver_files": os.environ.get("VK_DRIVER_FILES"),
        "exit_code": code,
        "stop_rule": rule,
        "process_group_gone": gone,
        "started_utc": started_utc,
        "ended_utc": now(),
        "wall_s": round(ended - started, 3),
        "log": {"file": f"logs/{name}.log", "sha256": sha256_file(log)},
        "test_mode": os.environ.get("NARRATE_AUDIOCPP_BATCH_TEST_MODE") == "1",
        "run_id": record.data["run_id"],
        "lease_holder": record.data["lease_holder"],
        "outputs": outputs,
        "missing": missing,
    }
    write_json(receipt_path, receipt)
    for leftover in out_dir.iterdir():
        leftover.unlink()
    out_dir.rmdir()
    print(
        json.dumps(
            {
                "receipt": str(receipt_path),
                "outputs": len(outputs),
                "missing": len(missing),
                "exit_code": code,
                "stop_rule": rule,
                "wall_s": receipt["wall_s"],
            }
        )
    )
    if rule != "exit" or not gone:
        return EXIT_STOPPED
    return EXIT_OK if not missing else EXIT_PARTIAL


def main(argv=None):
    p = argparse.ArgumentParser(prog="audiocpp_batch.py", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    for command in ("run", "check"):
        c = sub.add_parser(command)
        c.add_argument("dir")
        c.add_argument("--requests", required=True)
        if command == "run":
            c.add_argument("--binary", required=True)
            c.add_argument("--binary-sha256", required=True)
            c.add_argument("--model", required=True)
            c.add_argument("--model-sha256", required=True)
            c.add_argument("--family", default="voxcpm2")
            c.add_argument("--backend", default="vulkan")
            c.add_argument("--device", default="0")
            c.add_argument("--audiocpp-commit", default=None)
            c.add_argument("--deadline-s", type=float, default=0.0)
            c.add_argument("--stall-s", type=float, default=STALL_S)
            c.add_argument("--only-missing", action="store_true")
            c.add_argument("--lease-holder", default=None, help="the Lease holder id, for the run record")
    a = p.parse_args(argv)
    try:
        if a.command == "check":
            requests, digest, refs = load_batch(Path(a.dir).resolve(), a.requests)
            print(json.dumps({"ok": True, "requests": len(requests), "requests_sha256": digest, "refs": refs}))
            return EXIT_OK
        return run(a)
    except Refusal as error:
        print(json.dumps({"ok": False, "refused": str(error)}), file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
