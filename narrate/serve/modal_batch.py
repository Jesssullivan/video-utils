#!/usr/bin/env python3
"""Phase B of a RentedAudioCppBatch render on Modal: a sealed app around audiocpp_batch.py. DRAFT.

Nothing here has been deployed, run or billed. A run needs its own spend go (TIN-7125 `4f75ce59`), a consent record
with `hostedAllowed` (`af4ceb3b`, `e385617a`) and an `audiocpp_cli` that runs in this image. Which audio.cpp build
that is stays unknown (docs/spec/NARRATE.md, "Rented batch on Modal"), so the record's binary digest is a placeholder
that `prerender.check_engine` refuses.

Importing this file creates nothing and needs no credential. Without the `modal` package it defines no app, and the
dry run and every check below still work, so a host with no Modal SDK can test the draft.

The container side follows the Modal burst lessons on TIN-7856 `9e90b4fe`:

- no network and no Modal API access, proved again at start: assert_sealed needs a name and a literal address to fail;
- retries 0 and min_containers 0, one container at a time, used once;
- inputs by sha256 from the Volume, outputs back to it as they finish, because a preempted container keeps no disk.
  `modal run` discards a return value, so the reply is one printed line of counts and digests.

The host side, run_plan, is the only upload path. It holds these steps together, so no step is left to a person:

    preflight   the plan's engine is rented and offsite, its consent allows that, the run states it holds no SP-4
                health row, and the pins are the record's. It reads no network, and runs before any byte leaves.
    stage_in    `modal volume put` of requests/ and refs/, what the engine needs
    run         `modal run`, one call per requests file, stopping at the first that fails
    stage_back  `modal volume get` into an empty directory, the reply's digest checked, every take checked, then merged
    wipe        `modal volume rm -r`, only once the takes are home, then read back. Consent keeps nothing on a rented
                disk after a run. A failed get leaves the run on the Volume; `abandon` removes it by name.

The Volume holds three trees:

    bin/<sha256>/audiocpp_cli            the pinned binary
    weights/<sha256>/voxcpm2-bf16.gguf   the pinned public weights
    runs/<run_id>/                       a plan's requests/ and refs/, then wav/, receipts/ and logs/

    modal_batch.py dry-run                          the whole phase with a fake `modal` client and fake audiocpp_cli
    modal_batch.py engine-record [--binary-sha256 SHA]   the record for the private engines.json
    modal_batch.py preflight PLAN --binary-sha256 SHA --model-sha256 SHA --health-class none
    modal_batch.py run PLAN --run-id RUN --binary-sha256 SHA --model-sha256 SHA --health-class none [--modal CLIENT]
    modal_batch.py runs [--modal CLIENT]            the run ids on the Volume
    modal_batch.py abandon RUN [--modal CLIENT]     remove a run whose takes will not come home
"""

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path, PurePosixPath

APP_NAME = "narrate-rented-batch"
VOLUME_NAME = "narrate-rented-batch"
VOL = "/vol"
IMAGE_DIR = "/opt/narrate"
HERE = Path(__file__).resolve().parent

ENGINE_ID = "voxcpm2-batch-modal"
BINARY_NAME = "audiocpp_cli"
WEIGHTS_NAME = "voxcpm2-bf16.gguf"
# The digest the on-prem VoxCPM2 record pins for this public file, audio-cpp/audio.cpp-gguf at HF_REVISION.
WEIGHTS_SHA256 = "dc48028ebf08b9fd2456cbf5fa1ab52568d16660e34d0fa418c35e251ca1ecab"
HF_REPO = "audio-cpp/audio.cpp-gguf"
HF_REVISION = "ef1ab2598f6d4d101486e4c5b9e605c687f20642"
BINARY_PLACEHOLDER = "<binary sha256 of the audiocpp_cli this image runs>"

BACKEND = "vulkan"
AUDIOCPP_COMMIT = "47c2756e"
ICD = "/etc/vulkan/icd.d/nvidia_icd.json"
GPU = "L4"
GPU_CPU = 4.0
MEMORY_MIB = 16384
STARTUP_S = 300
TIMEOUT_S = 1800
# The clock starts at the function's start, so the weights copy spends it. The 180 seconds left cover the runner's
# weights hash, its stop (STOP_WAIT_S) and the last copy of takes, before Modal's timeout kills the container.
DEADLINE_S = 1620
STOP_WAIT_S = 20
CHECKPOINT_S = 15.0
COPY_EVERY_S = 15.0
UID = GID = 10001
UPLOADED = ("requests", "refs")
# A plan with receipts at home is a resume: its takes go back up, so the runner keeps them and voices only the rest.
RESUMED = ("wav", "receipts")
RETURNED = ("wav", "receipts", "logs", "requests")
REPLY_MAX_BYTES = 8 << 10
REPLY_KEY = "narrate_reply"
RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
SHA256 = re.compile(r"[0-9a-f]{64}")
TAKE = re.compile(r"wav/[0-9a-f]{32}\.wav")
# A blocked resolver with open routes fails the name and answers the address, so a seal needs both to fail.
NETWORK_PROBES = (("huggingface.co", 443), ("1.1.1.1", 443))

PLAN_SCHEMA = "narrate-prerender-plan/1"
RECEIPT_SCHEMA = "narrate-audiocpp-batch-receipt/1"
RENTED_PROFILE = "RentedOpen"
RENTED_BACKEND = "RentedAudioCppBatch"
PLACEMENT = "rented"
# No job field carries the SP-4 class, so the run states it. Only this value uploads (TIN-7125 `af4ceb3b`).
HEALTH_NONE = "none"
EXIT_DONE, EXIT_PARTIAL, EXIT_REFUSED, EXIT_RUN_STAYS = 0, 1, 2, 3

SEALED = {
    "gpu": GPU,
    "cpu": (GPU_CPU, GPU_CPU),
    "memory": (MEMORY_MIB, MEMORY_MIB),
    "timeout": TIMEOUT_S,
    "startup_timeout": STARTUP_S,
    "retries": 0,
    "min_containers": 0,
    "max_containers": 1,
    "scaledown_window": 2,
    "single_use_containers": True,
    "block_network": True,
    "restrict_modal_access": True,
}


class Refused(RuntimeError):
    """A run the sealed function will not start. code is the typed refusal."""

    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def engine_record(binary_sha256=BINARY_PLACEHOLDER):
    """The record for the private engines.json. Its id is what a voice's allowedEngines names. The location lives in
    profile and backend, so a run on this engine never reads as the on-prem one."""
    return {
        "id": ENGINE_ID,
        "profile": "RentedOpen",
        "backend": "RentedAudioCppBatch",
        "endpoint": "audiocpp://voxcpm2",
        "model": "voxcpm2-bf16",
        "hfRepo": HF_REPO,
        "hfRevision": HF_REVISION,
        "files": [
            {"path": BINARY_NAME, "sha256": binary_sha256},
            {"path": WEIGHTS_NAME, "sha256": WEIGHTS_SHA256},
        ],
        "licence": "Apache-2.0 (VoxCPM2 GGUF); MIT (audio.cpp)",
        "licenceNotice": None,
        "vramGiB": 8.0,
        "sampleRateHz": 48000,
        "hosted": False,
        "estateControlled": False,
        "confidentialAllowed": False,
    }


def assert_sealed(connect=None):
    """Stop if the network answers, so an unsealed container never reads a reference clip or a script. One target is a
    name and one a literal address, and an answer from either stops the run."""
    connect = connect or socket.create_connection
    for target in NETWORK_PROBES:
        try:
            with connect(target, timeout=3):
                pass
        except OSError:
            continue
        raise Refused("not_sealed", f"{target[0]} answered, so this container is not sealed")


def copy_tree(source, target, keep_existing=False):
    """Copy every regular file under source to target through a .part name. A symlink stops the copy, and a .part left
    by a killed copy is skipped. keep_existing skips a file already there: a take never changes once it has its name."""
    copied = 0
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise Refused("input_symlink", f"{path.name} is a symlink")
        if not path.is_file() or path.name.endswith(".part"):
            continue
        out = target / path.relative_to(source)
        if keep_existing and out.exists():
            continue
        out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        part = out.with_name(out.name + ".part")
        shutil.copyfile(path, part)
        os.replace(part, out)
        copied += 1
    return copied


def run_path(run_id):
    if not RUN_ID.fullmatch(run_id):
        raise Refused("run_id_invalid", "a plain name of at most 128 characters")
    return f"runs/{run_id}"


def run_dir(vol, run_id):
    return Path(vol) / run_path(run_id)


def sha_ok(value):
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def pinned_copy(vol, tree, sha256, name, work):
    """Copy a pinned file to the container's disk under the name the receipt must carry. audiocpp_batch.py hashes the
    copy against the pin, so a wrong file refuses there, before the runtime starts."""
    if not sha_ok(sha256):
        raise Refused("pin_invalid", f"{tree}: the pin is not 64 lowercase hex digits")
    source = Path(vol) / tree / sha256 / name
    if source.is_symlink() or not source.is_file():
        raise Refused("pin_missing", f"{tree}/{sha256[:12]} holds no {name}")
    target = work / name
    shutil.copyfile(source, target)
    target.chmod(0o500)
    return target


def child_settings(work, extra_env):
    """The runner's environment and its unprivileged user. audiocpp_batch.py refuses root and a Modal container runs as
    root, so root hands the work tree to UID and drops to it. No token reaches the runner: the environment is built
    here, never inherited."""
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(work),
        "NARRATE_RUNS_DIR": str(work / ".runs"),
        "VK_DRIVER_FILES": ICD,
        **(extra_env or {}),
    }
    if os.geteuid() != 0:
        return env, {}
    for path in [work, *work.rglob("*")]:
        os.chown(path, UID, GID)
    return env, {"user": UID, "group": GID, "extra_groups": []}


def sync_outputs(plan, source):
    """Copy what the runner has so far to the Volume. The receipts are read first and written last, so a receipt on
    the Volume never lists a take that is not there, whenever the container dies."""
    receipts = {p.name: p.read_bytes() for p in sorted((plan / "receipts").glob("*.json"))}
    copied = copy_tree(plan / "wav", source / "wav", keep_existing=True) if (plan / "wav").is_dir() else 0
    copied += sum(copy_tree(plan / sub, source / sub) for sub in ("logs", "requests") if (plan / sub).is_dir())
    target = source / "receipts"
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name, data in receipts.items():
        part = target / f"{name}.part"
        part.write_bytes(data)
        os.replace(part, target / name)
    os.sync()
    return copied + len(receipts)


def supervise(argv, env, cwd, user, output, plan, source):
    """Run the runner while a thread copies takes to the Volume, so a kill with no warning loses only what no pass had
    copied. A preemption reaches this process as SIGINT: the runner gets SIGTERM, finishes its receipt, and one last
    pass copies it. Returns the runner's exit code."""
    stop = threading.Event()

    def copier():
        while not stop.wait(COPY_EVERY_S):
            try:
                sync_outputs(plan, source)
            except OSError:
                continue  # the next pass tries again, and the last pass reports it

    worker = threading.Thread(target=copier, daemon=True)
    with open(output, "ab") as out:
        proc = subprocess.Popen(argv, env=env, cwd=cwd, stdout=out, stderr=subprocess.STDOUT, **user)
    worker.start()
    try:
        return proc.wait()
    except BaseException:
        proc.terminate()
        try:
            proc.wait(STOP_WAIT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
        raise
    finally:
        stop.set()
        worker.join()
        sync_outputs(plan, source)


def run_batch(
    vol,
    run_id,
    name,
    binary_sha256,
    model_sha256,
    *,
    backend=BACKEND,
    only_missing=False,
    runner=None,
    work_root=None,
    probe=None,
    extra_env=None,
):
    """One requests file through audiocpp_batch.py, on the container's disk. Returns counts and digests only: no text,
    no path and no take leaves by the reply. Exit codes are the runner's: 0, 1 partial, 2 refused, 20 stopped."""
    started = time.monotonic()
    (probe or assert_sealed)()
    source = run_dir(vol, run_id)
    requests = f"requests/{name}.json"
    if not (source / requests).is_file():
        raise Refused("requests_missing", f"{run_id} holds no {requests}")
    runner = Path(runner) if runner else Path(IMAGE_DIR) / "audiocpp_batch.py"
    work = Path(tempfile.mkdtemp(prefix="narrate-batch-", dir=work_root))
    try:
        plan = work / "plan"
        copy_tree(source, plan)
        (work / ".runs").mkdir(mode=0o700)
        (plan / "logs").mkdir(mode=0o700, exist_ok=True)
        binary = pinned_copy(vol, "bin", binary_sha256, BINARY_NAME, work)
        model = pinned_copy(vol, "weights", model_sha256, WEIGHTS_NAME, work)
        env, user = child_settings(work, extra_env)
        left = DEADLINE_S - (time.monotonic() - started)
        if left <= 0:
            raise Refused("deadline_spent", "the pinned copies took the whole deadline")
        argv = [sys.executable, "-I", str(runner), "run", str(plan), "--requests", requests]
        argv += ["--binary", str(binary), "--binary-sha256", binary_sha256]
        argv += ["--model", str(model), "--model-sha256", model_sha256]
        argv += ["--family", "voxcpm2", "--backend", backend, "--device", "0"]
        argv += ["--audiocpp-commit", AUDIOCPP_COMMIT, "--deadline-s", f"{left:.0f}"]
        argv += ["--placement", PLACEMENT, "--checkpoint-s", f"{CHECKPOINT_S:g}"]
        argv += ["--only-missing"] if only_missing else []
        # The app log is the provider's. The runner's own words stay on the Volume with the run.
        output = plan / "logs" / f"{name}.runner.log"
        code = supervise(argv, env, work, user, output, plan, source)
        lines = [line for line in output.read_text(encoding="utf-8").splitlines() if line.startswith('{"receipt"')]
        summary = json.loads(lines[-1]) if lines else {}
        receipt = Path(str(summary.get("receipt", ""))).name
        receipt_path = plan / "receipts" / receipt
        return {
            "run_id": run_id,
            "requests": name,
            "exit_code": code,
            "stop_rule": summary.get("stop_rule"),
            "outputs": summary.get("outputs"),
            "missing": summary.get("missing"),
            "receipt": receipt or None,
            "receipt_sha256": sha256_file(receipt_path) if receipt and receipt_path.is_file() else None,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def deployed(run_id, name, binary_sha256, model_sha256, only_missing=False, *, vol=None, **batch):
    """What the deployed function does. `modal run` discards a return value (client 1.6.1, cli/run.py) and keeps a
    function's stdout, so the reply is one printed line, and a batch that is not whole fails the call."""
    reply = run_batch(vol or VOL, run_id, name, binary_sha256, model_sha256, only_missing=only_missing, **batch)
    print(json.dumps({REPLY_KEY: reply}, sort_keys=True), flush=True)
    if reply["exit_code"] != 0:
        raise Refused("batch_incomplete", f"runner exit {reply['exit_code']}, {reply['missing']} missing")


def read_reply(stdout):
    """The reply in a `modal run` transcript, or None. It can follow a timestamp or a client's prefix."""
    for line in reversed(stdout.splitlines()):
        at = line.find(f'{{"{REPLY_KEY}"')
        if at >= 0:
            try:
                return json.loads(line[at:])[REPLY_KEY]
            except ValueError:
                return None
    return None


class Client:
    """The `modal` command line. Every byte a run moves goes through here, and run_plan is its only caller that puts."""

    def __init__(self, command="modal", env=None):
        self.argv, self.env = shlex.split(command), env

    def call(self, *args):
        return subprocess.run([*self.argv, *args], env=self.env, capture_output=True, text=True)

    def volume(self, verb, *args):
        done = self.call("volume", verb, *args)
        if done.returncode != 0:
            raise Refused("client_failed", f"`modal volume {verb}` exited {done.returncode}")
        return done.stdout

    def names(self, path):
        rows = json.loads(self.volume("ls", VOLUME_NAME, path, "--json"))
        return [PurePosixPath(row["filename"]).name for row in rows]

    def runs(self):
        """The run ids on the Volume. `runs` itself is absent on a new Volume."""
        return self.names("runs") if "runs" in self.names("/") else []

    def run(self, run_id, name, binary_sha256, model_sha256, only_missing):
        """One sealed batch: (exit code of `modal run`, the reply or None)."""
        target = f"{Path(__file__).resolve()}::run_requests"
        args = ["run", target, "--run-id", run_id, "--name", name]
        args += ["--binary-sha256", binary_sha256, "--model-sha256", model_sha256]
        args += ["--only-missing"] if only_missing else []
        done = self.call(*args)
        return done.returncode, read_reply(done.stdout)


def listed_files(plan_dir, tree, listed, spare=None):
    """Refuse unless tree holds exactly the files the plan lists, each with its digest. spare admits a file the plan
    cannot list, a resume's requests part."""
    root = Path(plan_dir)
    held = (
        sorted(p for p in (root / tree).rglob("*") if p.is_symlink() or p.is_file()) if (root / tree).is_dir() else []
    )
    names = {p.relative_to(root).as_posix(): p for p in held}
    for path in held:
        if path.is_symlink():
            raise Refused("input_symlink", f"{path.name} is a symlink")
    for name, sha in listed.items():
        if name not in names:
            raise Refused("plan_incomplete", f"the plan lists {name}, which is not there")
        if sha256_file(names[name]) != sha:
            raise Refused("plan_digest_mismatch", f"{name} differs from the plan")
    extra = [n for n in names if n not in listed and not (spare and spare.fullmatch(n))]
    if extra:
        raise Refused("plan_extra_file", f"{tree}/ holds {len(extra)} file(s) the plan does not list")


def preflight(plan_dir, binary_sha256, model_sha256, health_class):
    """The gate before any byte leaves the host. A plan carries the record it was admitted under, so a plan on an
    on-prem engine stops here, whatever its digests. Returns the batches to run and the request ids they must yield."""
    plan_dir = Path(plan_dir)
    try:
        plan = json.loads((plan_dir / "plan.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Refused("plan_invalid", "the directory holds no readable plan.json") from None
    if not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA:
        raise Refused("plan_invalid", f"plan.json is not {PLAN_SCHEMA}")
    engine = plan.get("engine") or {}
    if engine.get("backend") != RENTED_BACKEND or engine.get("profile") != RENTED_PROFILE:
        raise Refused("engine_not_rented", f"the plan's engine is {engine.get('id')}, not a rented batch record")
    consents = plan.get("consents")
    if not consents or any(c.get("hostedAllowed") is not True for c in consents):
        raise Refused("hosted_not_allowed", "a consent in this plan does not allow rented engines")
    if health_class != HEALTH_NONE:
        raise Refused("sp4_health_row", f"--health-class {health_class}: SP-4 health rows stay off a rented host")
    pins = {f.get("sha256") for f in engine.get("files") or []}
    for what, sha in (("binary", binary_sha256), ("weights", model_sha256)):
        if not sha_ok(sha):
            raise Refused("pin_invalid", f"{what}: the pin is not 64 lowercase hex digits")
        if sha not in pins:
            raise Refused("pin_not_in_record", f"{what} {sha[:12]} is not a file {engine.get('id')} pins")
    batches = {b["file"]: b["sha256"] for b in plan.get("batches") or []}
    if not batches:
        raise Refused("plan_incomplete", "the plan lists no batch")
    stems = "|".join(re.escape(PurePosixPath(f).stem) for f in batches)
    listed_files(plan_dir, "requests", batches, re.compile(rf"requests/({stems})\.part[0-9]+\.json"))
    listed_files(plan_dir, "refs", {r["file"]: r["sha256"] for r in plan.get("refs") or []})
    wanted = set()
    for file in batches:
        wanted |= {r["id"] for r in json.loads((plan_dir / file).read_text(encoding="utf-8"))["requests"]}
    return {
        "engine": engine.get("id"),
        "batches": [PurePosixPath(f).stem for f in batches],
        "wanted": wanted,
        "only_missing": any((plan_dir / "receipts").glob("*.json")),
    }


def stage_in(plan_dir, client, run_id, facts):
    """Put the plan's requests and references on the Volume, and a resume's takes. facts is preflight's answer."""
    for sub in UPLOADED + (RESUMED if facts["only_missing"] else ()):
        client.volume("put", VOLUME_NAME, str(Path(plan_dir) / sub), f"{run_path(run_id)}/{sub}")


def takes_home(root, replies=()):
    """The takes a directory holds: every reply's receipt has the digest the sealed function printed, every receipt is
    a rented run's, and each listed take is there with its sha256. Refused otherwise."""
    root = Path(root)
    for reply in replies:
        if reply.get("receipt"):
            path = root / "receipts" / Path(reply["receipt"]).name
            if not path.is_file() or sha256_file(path) != reply.get("receipt_sha256"):
                raise Refused("receipt_digest_mismatch", f"{path.name} differs from the sealed function's reply")
    takes = set()
    for path in sorted((root / "receipts").glob("*.json")):
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            receipt = {}
        if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("placement") != PLACEMENT:
            raise Refused("receipt_not_rented", f"{path.name} is not a rented run's receipt")
        for rid, out in (receipt.get("outputs") or {}).items():
            take = root / str(out.get("file"))
            if not TAKE.fullmatch(str(out.get("file"))) or not take.is_file() or sha256_file(take) != out.get("sha256"):
                raise Refused("take_missing", f"{rid} is not there with its sha256")
            takes.add(rid)
    return takes


def stage_back(plan_dir, client, run_id, replies=()):
    """Bring a run home. `modal volume get` writes under the destination relative to the remote path's parent, refuses
    a path that exists, and needs a destination that exists (client 1.6.1, cli/_download.py). So it fills a new empty
    directory, and the trees move into the plan only after every check. Returns the request ids that came home."""
    plan_dir = Path(plan_dir)
    with tempfile.TemporaryDirectory(prefix=".get-", dir=plan_dir) as tmp:
        client.volume("get", VOLUME_NAME, run_path(run_id), tmp)
        fetched = Path(tmp) / run_id
        takes_home(fetched, replies)
        for sub in RETURNED:
            if (fetched / sub).is_dir():
                copy_tree(fetched / sub, plan_dir / sub)
    return takes_home(plan_dir, replies)


def drop(client, run_id):
    """Remove a run from the Volume by its exact name and read that back. Other runs stay, and so do the pins: they
    hold public weights and a binary, and no clip, script or take. Whether consent's "nothing stays on a rented disk"
    means run data only is an open question for Jess (docs/spec/NARRATE.md)."""
    if run_id in client.runs():
        client.volume("rm", "-r", VOLUME_NAME, run_path(run_id))
    if run_id in client.runs():
        raise Refused("wipe_unconfirmed", f"{run_id} is still on the Volume")


def wipe(plan_dir, client, run_id, replies=()):
    """Remove a run once its takes are home. `abandon` is the one path that drops a run without them."""
    if not takes_home(plan_dir, replies):
        raise Refused("takes_not_home", f"the plan holds no take of {run_id}")
    drop(client, run_id)


def run_plan(plan_dir, client, run_id, binary_sha256, model_sha256, health_class):
    """The whole of phase B from the host, and the only upload path. Returns (exit code, report): 0 every request has
    its take and the run is wiped; 1 takes are home and the run is wiped, and the same plan under a new run id voices
    the rest; 3 the run stays on the Volume, because its takes are not home or the wipe failed. Refused before an
    upload is exit 2 from main."""
    facts = preflight(plan_dir, binary_sha256, model_sha256, health_class)
    run_path(run_id)
    if run_id in client.runs():
        raise Refused("run_exists", f"{run_id} is on the Volume; every run gets a new id")
    try:
        stage_in(plan_dir, client, run_id, facts)
    except Refused:
        drop(client, run_id)
        raise
    replies, failed = [], None
    for name in facts["batches"]:
        code, reply = client.run(run_id, name, binary_sha256, model_sha256, facts["only_missing"])
        replies += [reply] if reply else []
        if code != 0 or reply is None:
            failed = name
            break
    report = {
        "run_id": run_id,
        "engine": facts["engine"],
        "health_class": health_class,
        "failed_batch": failed,
        "replies": replies,
        "takes_home": False,
        "wiped": False,
    }
    try:
        takes = stage_back(plan_dir, client, run_id, replies)
        report["takes_home"] = True
        report["takes"], report["missing"] = len(takes & facts["wanted"]), len(facts["wanted"] - takes)
        if takes:
            wipe(plan_dir, client, run_id, replies)
        else:
            drop(client, run_id)
    except Refused as refused:
        return EXIT_RUN_STAYS, {**report, "stopped": refused.code, "next": f"modal_batch.py abandon {run_id}"}
    report["wiped"] = True
    return (EXIT_DONE if not report["missing"] and not failed else EXIT_PARTIAL), report


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def request_id(body):
    """audiocpp_batch.py's request id, computed here so the dry run writes valid requests."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def fixture_clip():
    """A synthetic reference: six seconds of silence at 16 kHz, so no voice enters a dry run."""
    with tempfile.TemporaryFile() as raw:
        with wave.open(raw, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(struct.pack("<h", 0) * 16000 * 6)
        raw.seek(0)
        return raw.read()


def fixture_plan(plan, binary_sha, model_sha, **engine):
    """A `narrate plan` shaped directory with two synthetic requests. Returns the request texts."""
    clip = fixture_clip()
    sha = hashlib.sha256(clip).hexdigest()
    (plan / "refs").mkdir(parents=True)
    (plan / "requests").mkdir()
    (plan / "refs" / f"{sha}.wav").write_bytes(clip)
    texts = ["A synthetic line for the sealed dry run.", "A second synthetic line."]
    requests = []
    for seed, text in enumerate(texts, 1):
        body = {"text": text, "seed": seed, "voice_ref": f"refs/{sha}.wav"}
        requests.append({"id": request_id(body), **body})
    batch = json.dumps({"requests": requests}).encode()
    (plan / "requests" / "fixture.json").write_bytes(batch)
    doc = {
        "schema": PLAN_SCHEMA,
        "engine": {**engine_record(binary_sha), **engine},
        "consents": [{"id": "consent-fixture", "hostedAllowed": True}],
        "batches": [{"file": "requests/fixture.json", "sha256": hashlib.sha256(batch).hexdigest()}],
        "refs": [{"file": f"refs/{sha}.wav", "sha256": sha}],
    }
    doc["engine"]["files"] = [{"path": BINARY_NAME, "sha256": binary_sha}, {"path": WEIGHTS_NAME, "sha256": model_sha}]
    (plan / "plan.json").write_text(json.dumps(doc), encoding="utf-8")
    return texts


def seed_pins(vol, fake_cli):
    """A fake binary and fake weights on the fake Volume. Returns their digests."""
    source = Path(fake_cli).read_text(encoding="utf-8")
    binary = f"#!{sys.executable}\n{source}".encode()
    weights = b"fake voxcpm2 weights; no model\n"
    pins = []
    for tree, name, data in (("bin", BINARY_NAME, binary), ("weights", WEIGHTS_NAME, weights)):
        digest = hashlib.sha256(data).hexdigest()
        path = Path(vol) / tree / digest / name
        path.parent.mkdir(parents=True)
        path.write_bytes(data)
        pins.append(digest)
    return pins


def fake_client(tmp, runner_env=None):
    """run_plan's client: the real subprocess path, with tests/fake_modal.py for the `modal` command."""
    tests = HERE.parent / "tests"
    env = {
        **os.environ,
        "FAKE_MODAL_VOL": str(tmp / "vol"),
        "FAKE_MODAL_WORK": str(tmp),
        "FAKE_MODAL_RUNNER_ENV": json.dumps(runner_env or {}),
    }
    return Client(f"{shlex.quote(sys.executable)} -I {shlex.quote(str(tests / 'fake_modal.py'))}", env=env)


def dry_run(fake_cli=None):
    """The whole phase through run_plan with a fake `modal` command and the fake audiocpp_cli: no Modal, no GPU, no
    network and no spend. The fake holds a run off the Volume until the probe fires, so a read before the probe
    refuses. Returns the report; ok is true only when every check holds."""
    fake_cli = fake_cli or HERE.parent / "tests" / "fake_audiocpp.py"
    with tempfile.TemporaryDirectory(prefix="narrate-modal-dry-") as tmp:
        tmp = Path(tmp)
        vol, plan, run_id = tmp / "vol", tmp / "plan", "dry-run-1"
        binary_sha, model_sha = seed_pins(vol, fake_cli)
        texts = fixture_plan(plan, binary_sha, model_sha)
        client = fake_client(tmp, {"NARRATE_AUDIOCPP_BATCH_TEST_MODE": "1"})
        code, report = run_plan(plan, client, run_id, binary_sha, model_sha, HEALTH_NONE)
        reply = report["replies"][0] if report["replies"] else {}
        receipt_path = plan / "receipts" / "fixture.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else {"outputs": {}}
        reply_text = json.dumps(reply)
        on_prem = tmp / "on-prem"
        fixture_plan(on_prem, binary_sha, model_sha, profile="GpuDirect", backend="AudioCppBatch")
        try:
            run_plan(on_prem, client, "dry-run-2", binary_sha, model_sha, HEALTH_NONE)
            refusal = None
        except Refused as refused:
            refusal = refused.code
        checks = {
            "run_plan_exit_0": code == EXIT_DONE,
            "every_request_has_a_take": report.get("takes") == len(texts) and report.get("missing") == 0,
            "takes_match_the_receipt": bool(receipt["outputs"])
            and all(sha256_file(plan / e["file"]) == e["sha256"] for e in receipt["outputs"].values()),
            "receipt_digest_in_reply": receipt_path.is_file()
            and reply.get("receipt_sha256") == sha256_file(receipt_path),
            "placement_rented": receipt.get("placement") == PLACEMENT,
            "no_lease_recorded": receipt.get("lease_holder") is None,
            "marked_test_mode": receipt.get("test_mode") is True,
            "reply_under_8_kib": len(reply_text.encode()) <= REPLY_MAX_BYTES,
            "reply_holds_no_text": not any(text in reply_text for text in texts),
            "wiped_and_read_back": report.get("wiped") is True and not client.runs(),
            "work_dir_removed": not list(tmp.glob("narrate-batch-*")),
            "pins_stay": (vol / "bin" / binary_sha).is_dir() and (vol / "weights" / model_sha).is_dir(),
            "on_prem_plan_refused_before_upload": refusal == "engine_not_rented" and not client.runs(),
        }
    return {
        "ok": all(checks.values()),
        "dry_run": True,
        "deployed": False,
        "billed": False,
        "engine": ENGINE_ID,
        "app": APP_NAME,
        "sealed": {k: list(v) if isinstance(v, tuple) else v for k, v in SEALED.items()},
        "checks": checks,
    }


try:
    import modal
except ImportError:
    modal = None

if modal is not None:
    # Building these starts nothing; `modal run` would. Modal requires a function in global scope.
    app = modal.App(APP_NAME)
    volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=False)
    image = (
        modal.Image.debian_slim(python_version="3.12")
        .apt_install("libvulkan1", "libgomp1")
        .add_local_file(str(HERE / "audiocpp_batch.py"), f"{IMAGE_DIR}/audiocpp_batch.py", copy=True)
        .add_local_file(str(HERE / "finalize.py"), f"{IMAGE_DIR}/finalize.py", copy=True)
        .env({"DO_NOT_TRACK": "1"})
    )

    @app.function(image=image, volumes={VOL: volume}, **SEALED)
    def run_requests(run_id: str, name: str, binary_sha256: str, model_sha256: str, only_missing: bool = False) -> None:
        """One requests file. With only_missing it voices only what the takes on the Volume do not hold."""
        deployed(run_id, name, binary_sha256, model_sha256, only_missing)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="modal_batch.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("dry-run")
    record = sub.add_parser("engine-record")
    record.add_argument("--binary-sha256", default=BINARY_PLACEHOLDER)
    for command in ("preflight", "run"):
        host = sub.add_parser(command)
        host.add_argument("plan")
        host.add_argument("--binary-sha256", required=True)
        host.add_argument("--model-sha256", required=True)
        host.add_argument("--health-class", required=True, help="the SP-4 class of the script text: none uploads")
        if command == "run":
            host.add_argument("--run-id", required=True)
            host.add_argument("--modal", default="modal", help="the modal client command")
    sub.add_parser("runs").add_argument("--modal", default="modal")
    abandon = sub.add_parser("abandon")
    abandon.add_argument("run_id")
    abandon.add_argument("--modal", default="modal")
    args = parser.parse_args(argv)
    try:
        if args.command == "engine-record":
            print(json.dumps(engine_record(args.binary_sha256), indent=1))
            return 0
        if args.command == "preflight":
            facts = preflight(args.plan, args.binary_sha256, args.model_sha256, args.health_class)
            print(json.dumps({"ok": True, **{k: v for k, v in facts.items() if k != "wanted"}}))
            return 0
        if args.command == "run":
            client = Client(args.modal)
            code, report = run_plan(
                args.plan, client, args.run_id, args.binary_sha256, args.model_sha256, args.health_class
            )
            print(json.dumps(report, indent=1))
            return code
        if args.command == "runs":
            print(json.dumps(Client(args.modal).runs()))
            return 0
        if args.command == "abandon":
            run_path(args.run_id)
            drop(Client(args.modal), args.run_id)
            print(json.dumps({"ok": True, "wiped": args.run_id}))
            return 0
    except Refused as refused:
        print(json.dumps({"ok": False, "refused": refused.code, "detail": refused.detail}), file=sys.stderr)
        return EXIT_REFUSED
    report = dry_run()
    print(json.dumps(report, indent=1))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
