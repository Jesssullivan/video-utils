#!/usr/bin/env python3
"""A fake `modal` client for tests and the dry run. It keeps the behaviour of client 1.6.1 that the host steps rest on,
read from that client's source, and one directory stands for the Volume (FAKE_MODAL_VOL):

  volume put   makes parents; refuses a file that exists without --force (cli/volume.py)
  volume get   writes under the destination relative to the REMOTE PATH'S PARENT, so runs/RUN lands in DEST/RUN/;
               refuses a path that exists; with a destination that is not a directory every entry lands on that one
               path (cli/_download.py)
  volume ls    --json: rows with the key `filename`; a missing path exits 1
  volume rm -r exits 1 on a missing path
  run          a function's stdout reaches the client and its return value is dropped (cli/run.py); a raised error
               exits 1

`run` calls modal_batch.deployed in this process. It holds the run off the Volume until the probe fires, so anything
that reads the Volume before the probe finds no run. FAKE_MODAL_RUNNER_ENV is JSON for the runner's environment.
"""

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path, PurePosixPath

SERVE = Path(__file__).resolve().parents[1] / "serve"


def fail(message):
    print(message, file=sys.stderr)
    return 1


def volume(argv):
    verb, *rest = argv
    flags = [a for a in rest if a.startswith("-")]
    name, *paths = [a for a in rest if not a.startswith("-")]
    vol = Path(os.environ["FAKE_MODAL_VOL"])
    if verb == "put":
        local, remote = Path(paths[0]), vol / paths[1]
        files = (
            [(p, remote / p.relative_to(local)) for p in local.rglob("*") if p.is_file()]
            if local.is_dir()
            else [(local, remote)]
        )
        for source, target in files:
            if target.exists() and "--force" not in flags:
                return fail(f"{target.name} exists")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        return 0
    if verb == "get":
        remote, destination = paths[0], Path(paths[1])
        top = vol / remote
        if not top.exists():
            return fail("not found")
        start = vol / PurePosixPath(remote).parent
        for entry in sorted(top.rglob("*")):
            output = destination / entry.relative_to(start) if destination.is_dir() else destination
            if output.exists():
                return fail(f"Output path '{output}' already exists. Use --force to overwrite the output directory")
            if entry.is_file():
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(entry, output)
            else:
                output.mkdir(parents=True, exist_ok=True)
        return 0
    if verb == "ls":
        top = vol / paths[0].lstrip("/")
        if not top.is_dir():
            return fail("not found")
        print(
            json.dumps(
                [
                    {"filename": p.relative_to(vol).as_posix(), "type": "dir" if p.is_dir() else "file"}
                    for p in sorted(top.iterdir())
                    if not p.name.startswith(".")
                ]
            )
        )
        return 0
    if verb == "rm":
        top = vol / paths[0]
        if not top.exists():
            return fail("not found")
        shutil.rmtree(top)
        return 0
    return fail(f"fake modal: no volume verb {verb}")


def load_app():
    sys.modules["modal"] = None
    spec = importlib.util.spec_from_file_location("narrate_modal_batch", SERVE / "modal_batch.py")
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    return app


def run(argv):
    options = {"only_missing": "--only-missing" in argv}
    for flag in ("--run-id", "--name", "--binary-sha256", "--model-sha256"):
        options[flag[2:].replace("-", "_")] = argv[argv.index(flag) + 1]
    vol, run_id = Path(os.environ["FAKE_MODAL_VOL"]), options["run_id"]
    live, held = vol / "runs" / run_id, vol / f".held-{run_id}"
    live.rename(held)

    def probe():
        held.rename(live)

    app = load_app()
    try:
        app.deployed(
            run_id,
            options["name"],
            options["binary_sha256"],
            options["model_sha256"],
            options["only_missing"],
            vol=vol,
            runner=SERVE / "audiocpp_batch.py",
            work_root=os.environ["FAKE_MODAL_WORK"],
            probe=probe,
            extra_env=json.loads(os.environ.get("FAKE_MODAL_RUNNER_ENV") or "{}"),
        )
    except app.Refused as refused:
        return fail(str(refused))
    finally:
        if held.exists():
            held.rename(live)
    return 0


def main(argv):
    if argv[0] == "volume":
        return volume(argv[1:])
    if argv[0] == "run":
        return run(argv[1:])
    return fail(f"fake modal: no command {argv[0]}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
