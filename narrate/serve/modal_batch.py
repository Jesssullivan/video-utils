#!/usr/bin/env python3
"""Phase B of a RentedAudioCppBatch render on Modal: a sealed app around audiocpp_batch.py. DRAFT.

Nothing here has been deployed, run or billed. A run needs its own spend go (TIN-7125 `4f75ce59`), a consent record
with `hostedAllowed` (`af4ceb3b`, `e385617a`) and an `audiocpp_cli` that runs in this image. Which audio.cpp build
that is stays unknown (docs/spec/NARRATE.md, "Rented batch on Modal"), so the record's binary digest is a placeholder
that `prerender.check_engine` refuses.

Importing this file creates nothing and needs no credential. Without the `modal` package it defines no app, and the
dry run and every check below still work, so a host with no Modal SDK can test the draft.

The seal follows the Modal burst lessons on TIN-7856 `9e90b4fe`:

- no network and no Modal API access in the container, proved again at start by assert_sealed;
- retries 0 and min_containers 0, one container at a time, used once;
- inputs by sha256 from the Volume, outputs back to the Volume. A reply over 8 KiB failed under restrict_modal_access,
  so run_batch returns counts and digests only.

The Volume holds three trees:

    bin/<sha256>/audiocpp_cli            the pinned binary
    weights/<sha256>/voxcpm2-bf16.gguf   the pinned public weights
    runs/<run_id>/                       a plan's requests/ and refs/, then wav/, receipts/ and logs/

stage_in copies only requests/ and refs/, what the engine needs. run_batch works on the container's own disk, copies
outputs to the Volume and removes the work directory. wipe removes runs/<run_id>/ once the takes are home, because the
consent record keeps nothing on a rented disk after a run. stage_in, stage_back and wipe stand for `modal volume put`,
`modal volume get` and `modal volume rm` in the spec's order of steps; the dry run plays them on a local directory.

    modal_batch.py dry-run                          the whole phase on a fake Volume with the fake audiocpp_cli
    modal_batch.py engine-record [--binary-sha256 SHA]   the record for the private engines.json
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

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
# The runner stops first, so its finished takes reach the Volume before Modal's timeout kills the container.
DEADLINE_S = 1620
UID = GID = 10001
UPLOADED = ("requests", "refs")
RETURNED = ("wav", "receipts", "logs", "requests")
REPLY_MAX_BYTES = 8 << 10
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
NETWORK_PROBE = ("huggingface.co", 443)

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


def assert_sealed(connect=socket.create_connection):
    """Stop if the network answers, so an unsealed container never reads a reference clip or a script."""
    try:
        with connect(NETWORK_PROBE, timeout=3):
            pass
    except OSError:
        return
    raise Refused("not_sealed", "the network is reachable, so this container is not sealed")


def copy_tree(source, target):
    """Copy every regular file under source to target through a .part name. A symlink stops the copy."""
    copied = 0
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise Refused("input_symlink", f"{path.name} is a symlink")
        if not path.is_file():
            continue
        out = target / path.relative_to(source)
        out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        part = out.with_name(out.name + ".part")
        shutil.copyfile(path, part)
        os.replace(part, out)
        copied += 1
    return copied


def run_dir(vol, run_id):
    if not RUN_ID.match(run_id):
        raise Refused("run_id_invalid", "a plain name of at most 128 characters")
    return Path(vol) / "runs" / run_id


def stage_in(plan_dir, vol, run_id):
    """Put a plan directory's requests and references on the Volume: `modal volume put` in a real run."""
    target = run_dir(vol, run_id)
    if target.exists():
        raise Refused("run_exists", f"{run_id} is on the Volume; every run gets a new id")
    return sum(copy_tree(Path(plan_dir) / sub, target / sub) for sub in UPLOADED)


def stage_back(vol, run_id, plan_dir):
    """Bring a run's outputs home into its plan directory: `modal volume get` in a real run."""
    source = run_dir(vol, run_id)
    return sum(copy_tree(source / sub, Path(plan_dir) / sub) for sub in RETURNED if (source / sub).is_dir())


def wipe(vol, run_id):
    """Remove a run from the Volume once its takes are home: `modal volume rm -r`. The pins stay: they hold public
    weights and a binary, and no clip, script or take. Returns what stayed under runs/, which must be nothing."""
    target = run_dir(vol, run_id)
    if target.exists():
        shutil.rmtree(target)
    return sorted(p.name for p in (Path(vol) / "runs").glob(f"{run_id}*"))


def pinned_copy(vol, tree, sha256, name, work):
    """Copy a pinned file to the container's disk under the name the receipt must carry. audiocpp_batch.py hashes the
    copy against the pin, so a wrong file refuses there, before the runtime starts."""
    if not SHA256.match(sha256):
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
    probe=assert_sealed,
    extra_env=None,
):
    """One requests file through audiocpp_batch.py, on the container's disk. Returns counts and digests only: no text,
    no path and no take leaves by the reply. Exit codes are the runner's: 0, 1 partial, 2 refused, 20 stopped."""
    probe()
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
        binary = pinned_copy(vol, "bin", binary_sha256, BINARY_NAME, work)
        model = pinned_copy(vol, "weights", model_sha256, WEIGHTS_NAME, work)
        env, user = child_settings(work, extra_env)
        argv = [sys.executable, "-I", str(runner), "run", str(plan), "--requests", requests]
        argv += ["--binary", str(binary), "--binary-sha256", binary_sha256]
        argv += ["--model", str(model), "--model-sha256", model_sha256]
        argv += ["--family", "voxcpm2", "--backend", backend, "--device", "0"]
        argv += ["--audiocpp-commit", AUDIOCPP_COMMIT, "--deadline-s", str(DEADLINE_S)]
        argv += ["--only-missing"] if only_missing else []
        done = subprocess.run(argv, env=env, cwd=work, capture_output=True, text=True, **user)
        logs = plan / "logs"
        logs.mkdir(exist_ok=True)
        # The app log is the provider's. The runner's own words stay on the Volume with the run.
        (logs / f"{name}.runner.log").write_text(done.stdout + done.stderr, encoding="utf-8")
        lines = [line for line in done.stdout.splitlines() if line.startswith("{")]
        summary = json.loads(lines[-1]) if lines else {}
        receipt = Path(str(summary.get("receipt", ""))).name
        receipt_path = plan / "receipts" / receipt
        copied = sum(copy_tree(plan / sub, source / sub) for sub in RETURNED if (plan / sub).is_dir())
        os.sync()
        return {
            "run_id": run_id,
            "requests": name,
            "exit_code": done.returncode,
            "stop_rule": summary.get("stop_rule"),
            "outputs": summary.get("outputs"),
            "missing": summary.get("missing"),
            "receipt": receipt or None,
            "receipt_sha256": sha256_file(receipt_path) if receipt and receipt_path.is_file() else None,
            "files_copied": copied,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


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


def fixture_plan(plan):
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
    (plan / "requests" / "fixture.json").write_text(json.dumps({"requests": requests}), encoding="utf-8")
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


def dry_run(fake_cli=None):
    """The whole phase on a fake Volume with the fake audiocpp_cli: no Modal, no GPU, no network and no spend. Returns
    the report; ok is true only when every check holds."""
    fake_cli = fake_cli or HERE.parent / "tests" / "fake_audiocpp.py"
    with tempfile.TemporaryDirectory(prefix="narrate-modal-dry-") as tmp:
        tmp = Path(tmp)
        vol, plan, run_id = tmp / "vol", tmp / "plan", "dry-run-1"
        texts = fixture_plan(plan)
        binary_sha, model_sha = seed_pins(vol, fake_cli)
        probes = []
        stage_in(plan, vol, run_id)
        reply = run_batch(
            vol,
            run_id,
            "fixture",
            binary_sha,
            model_sha,
            runner=HERE / "audiocpp_batch.py",
            work_root=tmp,
            probe=lambda: probes.append("sealed"),
            extra_env={"NARRATE_AUDIOCPP_BATCH_TEST_MODE": "1"},
        )
        stage_back(vol, run_id, plan)
        receipt = json.loads((plan / "receipts" / "fixture.json").read_text(encoding="utf-8"))
        takes = [plan / entry["file"] for entry in receipt["outputs"].values()]
        reply_text = json.dumps(reply)
        left = wipe(vol, run_id)
        checks = {
            "sealed_probe_ran_first": probes == ["sealed"],
            "runner_exit_0": reply["exit_code"] == 0,
            "every_request_has_a_take": reply["outputs"] == len(texts) and reply["missing"] == 0,
            "takes_match_the_receipt": all(
                sha256_file(t) == e["sha256"] for t, e in zip(takes, receipt["outputs"].values(), strict=True)
            ),
            "receipt_digest_in_reply": reply["receipt_sha256"] == sha256_file(plan / "receipts" / "fixture.json"),
            "no_lease_recorded": receipt["lease_holder"] is None,
            "marked_test_mode": receipt["test_mode"] is True,
            "reply_under_8_kib": len(reply_text.encode()) <= REPLY_MAX_BYTES,
            "reply_holds_no_text": not any(text in reply_text for text in texts),
            "no_run_left_on_the_volume": not left and not (vol / "runs" / run_id).exists(),
            "work_dir_removed": not list(tmp.glob("narrate-batch-*")),
            "pins_stay": (vol / "bin" / binary_sha).is_dir() and (vol / "weights" / model_sha).is_dir(),
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
    def run_requests(run_id: str, name: str, binary_sha256: str, model_sha256: str, only_missing: bool = False) -> dict:
        """One requests file. A rerun with only_missing finishes a stopped batch from the takes on the Volume."""
        return run_batch(VOL, run_id, name, binary_sha256, model_sha256, only_missing=only_missing)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="modal_batch.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("dry-run")
    record = sub.add_parser("engine-record")
    record.add_argument("--binary-sha256", default=BINARY_PLACEHOLDER)
    args = parser.parse_args(argv)
    if args.command == "engine-record":
        print(json.dumps(engine_record(args.binary_sha256), indent=1))
        return 0
    report = dry_run()
    print(json.dumps(report, indent=1))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
