"""The host placement rule (docs/spec/NARRATE.md, "Host placement and memory") as the code enforces it: the
qwentts.cpp script builds and serves only on a host whose machine id is in the user's private allow file, serves only
a stamped, current build with hashed weights, and never on the CPU device; heavy recipes run through
narrate/bounded.sh, which takes a one-at-a-time lock, waits on memory pressure and opens a MemoryMax scope at nice
19; whisper never gets more than 4 threads. Fake systemd-run, systemctl, git and tts-server binaries stand in for
the real ones; nothing heavy runs."""

import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from narrate import qa

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parent
BOUNDED = PACKAGE / "bounded.sh"
QWENTTS = PACKAGE / "serve" / "qwentts.sh"
PATCHES = [PACKAGE / "serve" / "qwentts-threads.patch", PACKAGE / "serve" / "qwentts-loopback.patch"]
PLACEMENT_ENV = (
    "NARRATE_BOUNDED",
    "NARRATE_BOUNDED_PID",
    "NARRATE_MEMORY_MAX",
    "NARRATE_PSI_MAX",
    "NARRATE_PSI_WAIT_S",
    "NARRATE_PSI_FILE",
    "NARRATE_LOCK_WAIT_S",
    "NARRATE_HEAVY_LOCK",
    "NARRATE_TTS_HOST_ALLOWED",
    "NARRATE_QWENTTS_DEVICE",
    "NARRATE_QWENTTS_BUILD",
    "NARRATE_WEIGHTS_DIR",
    "XDG_CONFIG_HOME",
)
# The fake systemd-run prints its argv and the thread knob, then runs the command the way the real one does.
FAKE_SYSTEMD_RUN = """echo "systemd-run $* threads=${QWENTTS_CPU_THREADS:-unset}"
while [ $# -gt 0 ]; do case "$1" in -p) shift 2 ;; -*) shift ;; *) break ;; esac; done
exec "$@"
"""


def env(tmp_path, **extra):
    """The caller's environment without any placement knob, a calm pressure file, a private lock file, an empty
    private config directory and fake systemd tools first on PATH (systemctl succeeds unless a test says
    otherwise)."""
    base = {k: v for k, v in os.environ.items() if k not in PLACEMENT_ENV}
    calm = tmp_path / "calm"
    calm.write_text("some avg10=0.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n")
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    tool(fake / "systemd-run", FAKE_SYSTEMD_RUN)
    tool(fake / "systemctl", "exit 0")
    (tmp_path / "config").mkdir(exist_ok=True)
    return (
        base
        | {
            "PATH": f"{fake}{os.pathsep}{base['PATH']}",
            "NARRATE_PSI_FILE": str(calm),
            "NARRATE_HEAVY_LOCK": str(tmp_path / "heavy.lock"),
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
        }
        | extra
    )


def tool(path, body):
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)


def run(cmd, environ):
    return subprocess.run(cmd, env=environ, capture_output=True, text=True, timeout=60)


def test_bounded_opens_a_6g_scope_at_nice_19(tmp_path):
    out = run([str(BOUNDED), "echo", "hi"], env(tmp_path))
    assert out.returncode == 0, out.stderr
    first, second = out.stdout.splitlines()
    words = first.split()
    assert words[:5] == ["systemd-run", "--user", "--scope", "--quiet", "--collect"]
    assert re.fullmatch(r"--unit=narrate-bounded-\d+", words[5])
    assert words[6:8] == ["-p", "MemoryMax=6G"]
    assert words[8:11] == ["nice", "-n", "19"]
    assert words[-3:-1] == ["echo", "hi"]
    assert second == "hi"


def test_bounded_takes_another_ceiling(tmp_path):
    out = run([str(BOUNDED), "true"], env(tmp_path, NARRATE_MEMORY_MAX="14G"))
    assert "MemoryMax=14G" in out.stdout.split()
    refused = run([str(BOUNDED), "true"], env(tmp_path, NARRATE_MEMORY_MAX="lots"))
    assert refused.returncode == 2 and "NARRATE_MEMORY_MAX" in refused.stderr


def test_without_user_systemd_it_still_runs_at_nice_19(tmp_path):
    environ = env(tmp_path)
    tool(tmp_path / "bin" / "systemctl", "exit 1")
    out = run([str(BOUNDED), "sh", "-c", 'nice; [ "$NARRATE_BOUNDED_PID" = "$$" ] && echo own-pid'], environ)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["19", "own-pid"]
    assert "without a memory ceiling" in out.stderr


def test_a_nested_call_stays_inside_the_outer_step(tmp_path):
    """The inner call opens no second scope and does not wait for the lock its own parent holds."""
    inner = f"{BOUNDED} sh -c 'echo inner; nice'"
    out = run([str(BOUNDED), "sh", "-c", inner], env(tmp_path, NARRATE_LOCK_WAIT_S="0"))
    assert out.returncode == 0, out.stderr
    lines = out.stdout.splitlines()
    assert sum(line.startswith("systemd-run") for line in lines) == 1
    assert lines[1:] == ["inner", "19"]


@pytest.mark.parametrize(
    "leaked", [{"NARRATE_BOUNDED": "1"}, {"NARRATE_BOUNDED_PID": "1"}, {"NARRATE_BOUNDED_PID": "4194301"}]
)
def test_a_leaked_marker_does_not_drop_the_bounds(tmp_path, leaked):
    out = run([str(BOUNDED), "sh", "-c", "nice"], env(tmp_path, **leaked))
    assert out.returncode == 0, out.stderr
    assert "MemoryMax=6G" in out.stdout.split() and out.stdout.split()[-1] == "19"


needs_flock = pytest.mark.skipif(shutil.which("flock") is None, reason="flock(1) is not on PATH")


def hold(lock):
    handle = open(lock, "a")  # noqa: SIM115 - held across the call under test
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return handle


@needs_flock
def test_a_second_step_waits_for_the_first_then_gives_up_with_75(tmp_path):
    environ = env(tmp_path, NARRATE_LOCK_WAIT_S="0")
    marker = tmp_path / "ran"
    with hold(environ["NARRATE_HEAVY_LOCK"]):
        out = run([str(BOUNDED), "touch", str(marker)], environ)
    assert out.returncode == 75
    assert "holds" in out.stderr and "not starting" in out.stderr
    assert not marker.exists()
    after = run([str(BOUNDED), "touch", str(marker)], environ)
    assert after.returncode == 0 and marker.exists()


@needs_flock
def test_the_lock_is_held_while_the_step_runs(tmp_path):
    environ = env(tmp_path, NARRATE_LOCK_WAIT_S="0")
    probe = f"{BOUNDED} true; echo inner=$?"
    # The inner call here is a fresh step (its marker is cleared), so it must find the lock taken.
    out = run([str(BOUNDED), "sh", "-c", f"NARRATE_BOUNDED_PID= {probe}"], environ)
    assert out.stdout.splitlines()[-1] == "inner=75", out.stderr


def test_no_lock_is_for_a_server(tmp_path):
    environ = env(tmp_path, NARRATE_LOCK_WAIT_S="0")
    with hold(environ["NARRATE_HEAVY_LOCK"]):
        out = run([str(BOUNDED), "--no-lock", "echo", "served"], environ)
    assert out.returncode == 0 and out.stdout.splitlines()[-1] == "served"


def test_high_memory_pressure_holds_the_step_back(tmp_path):
    hot = tmp_path / "hot"
    hot.write_text("some avg10=40.00 avg60=1 avg300=1 total=1\nfull avg10=31.50 avg60=1 avg300=1 total=1\n")
    marker = tmp_path / "ran"
    out = run([str(BOUNDED), "touch", str(marker)], env(tmp_path, NARRATE_PSI_FILE=str(hot), NARRATE_PSI_WAIT_S="0"))
    assert out.returncode == 75
    assert "full avg10=31.50" in out.stderr
    assert not marker.exists()


def test_a_missing_pressure_file_does_not_wait(tmp_path):
    out = run([str(BOUNDED), "true"], env(tmp_path, NARRATE_PSI_FILE=str(tmp_path / "absent")))
    assert out.returncode == 0, out.stderr


MACHINE_ID = "0123456789abcdef0123456789abcdef"
COMMIT = "a" * 40
URL = "https://example.invalid/qwentts.cpp"
TALKER, CODEC = "qwen-talker-1.7b-base-BF16.gguf", "qwen-tokenizer-12hz-F32.gguf"
VULKAN_FLAGS = "-DGGML_VULKAN=ON -DGGML_METAL=OFF -DGGML_CUDA=OFF"


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Host:
    """A fixture host for the sourced script: a machine id, the private allow file, a pinned sources file with
    small weights, a fetched weights directory, and a 0700 build tree with a fake stamped tts-server."""

    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.env = env(tmp_path)
        (tmp_path / "host" / "etc").mkdir(parents=True)
        (tmp_path / "host" / "etc" / "machine-id").write_text(MACHINE_ID + "\n")
        self.allow = tmp_path / "config" / "narrate" / "tts-host"
        self.allow.parent.mkdir(parents=True)
        self.allow.write_text(MACHINE_ID + "\n")
        self.allow.chmod(0o600)
        weights = {TALKER: b"talker fixture", CODEC: b"codec fixture"}
        self.weights = tmp_path / "weights" / "hf" / "qwen3-tts-1.7b-base-qwentts"
        self.weights.mkdir(parents=True)
        for name, data in weights.items():
            (self.weights / name).write_bytes(data)
        (self.weights / "SHA256SUMS").write_text("".join(f"{sha(d)}  {n}\n" for n, d in weights.items()))
        self.sources = tmp_path / "sources.json"
        files = [{"path": n, "bytes": len(d), "sha256": sha(d)} for n, d in weights.items()]
        self.sources.write_text(
            json.dumps(
                {
                    "sources": [
                        {"id": "qwentts.cpp", "url": URL, "commit": COMMIT},
                        {"id": "qwen3-tts-1.7b-base-qwentts", "files": files},
                    ]
                }
            )
        )
        self.build = tmp_path / "build"
        self.build.mkdir(mode=0o700)
        self.out = self.build / "qwentts.cpp" / "build-vulkan"
        self.out.mkdir(parents=True)
        self.server = self.out / "tts-server"
        tool(self.server, 'echo "tts-server $*"')
        self.stamp()
        tool(tmp_path / "bin" / "git", "echo git must not run >&2; exit 9")
        self.env |= {
            "NARRATE_QWENTTS_DEVICE": "Vulkan0",
            "NARRATE_QWENTTS_BUILD": str(self.build),
            "NARRATE_WEIGHTS_DIR": str(tmp_path / "weights"),
        }

    def stamp(self):
        first = " ".join([COMMIT, *(sha(p.read_bytes()) for p in PATCHES), VULKAN_FLAGS])
        (self.out / "narrate-stamp").write_text(f"{first}\n{sha(self.server.read_bytes())}\n")

    def run(self, command, **extra):
        script = 'source "$1"; host_root="$2"; sources="$3"; main "$4"'
        argv = ["bash", "-c", script, "qwentts", str(QWENTTS), str(self.tmp / "host"), str(self.sources), command]
        return run(argv, self.env | extra)


@pytest.fixture
def host(tmp_path):
    return Host(tmp_path)


def test_serve_starts_the_stamped_server_on_loopback_in_a_14g_scope(host):
    with hold(host.env["NARRATE_HEAVY_LOCK"]):  # serve takes no lock: a scorer may hold it
        out = host.run("serve", NARRATE_LOCK_WAIT_S="0")
    assert out.returncode == 0, out.stderr
    scope, server = out.stdout.splitlines()
    assert "MemoryMax=14G" in scope.split() and scope.endswith("threads=4")
    assert server.split() == [
        "tts-server",
        "--model",
        str(host.weights / TALKER),
        "--codec",
        str(host.weights / CODEC),
        "--device",
        "Vulkan0",
        "--alias",
        "qwen3-tts-1.7b-base-qwentts",
        "--host",
        "127.0.0.1",
        "--port",
        "18089",
        "--lang",
        "English",
    ]


def test_serve_refuses_a_host_without_an_allow_file(tmp_path):
    out = run([str(QWENTTS), "serve"], env(tmp_path, NARRATE_QWENTTS_DEVICE="Vulkan0"))
    assert out.returncode == 2
    assert "refused" in out.stderr and "Host placement and memory" in out.stderr


def test_the_old_environment_opt_in_opens_nothing(tmp_path):
    out = run([str(QWENTTS), "serve"], env(tmp_path, NARRATE_TTS_HOST_ALLOWED="1", NARRATE_QWENTTS_DEVICE="Vulkan0"))
    assert out.returncode == 2 and "refused" in out.stderr


@pytest.mark.parametrize("command", ["serve", "build"])
def test_an_allow_file_for_another_host_is_refused(host, command):
    host.allow.write_text("fedcba9876543210fedcba9876543210\n")
    out = host.run(command)
    assert out.returncode == 2 and "does not name this host" in out.stderr


def test_an_allow_file_others_can_write_is_refused(host):
    host.allow.chmod(0o620)
    out = host.run("serve")
    assert out.returncode == 2 and "writable by another user" in out.stderr


def test_an_allow_file_symlink_is_refused(host):
    target = host.tmp / "elsewhere"
    target.write_text(MACHINE_ID)
    host.allow.unlink()
    host.allow.symlink_to(target)
    out = host.run("serve")
    assert out.returncode == 2 and "no allow file" in out.stderr


def test_serve_never_takes_the_cpu_device(host):
    out = host.run("serve", NARRATE_QWENTTS_DEVICE="CPU")
    assert out.returncode == 2 and "CPU is a build target only" in out.stderr


@pytest.mark.parametrize(
    ("device", "message"),
    [("", "set NARRATE_QWENTTS_DEVICE"), ("CUDA0", "must be Vulkan0..9, MTL0..9 or CPU")],
)
def test_serve_needs_a_named_device(host, device, message):
    out = host.run("serve", NARRATE_QWENTTS_DEVICE=device)
    assert out.returncode == 2 and message in out.stderr


def test_serve_needs_the_private_weights(host):
    out = host.run("serve", NARRATE_WEIGHTS_DIR="")
    assert out.returncode == 2 and "NARRATE_WEIGHTS_DIR" in out.stderr


def test_a_same_size_corrupt_weight_is_refused(host):
    (host.weights / TALKER).write_bytes(b"talker FIXTURE")
    out = host.run("serve")
    assert out.returncode != 0 and "sha256 differs from the pin" in out.stderr


def test_a_receipt_that_disagrees_with_the_pin_is_refused(host):
    (host.weights / "SHA256SUMS").write_text(f"{'0' * 64}  {TALKER}\n{sha(b'codec fixture')}  {CODEC}\n")
    out = host.run("serve")
    assert out.returncode != 0 and "fetch receipt" in out.stderr


@pytest.mark.parametrize("damage", ["no_stamp", "stale_stamp", "replaced_binary"])
def test_serve_never_builds_and_refuses_a_build_it_cannot_vouch_for(host, damage):
    if damage == "no_stamp":
        (host.out / "narrate-stamp").unlink()
    elif damage == "stale_stamp":
        (host.out / "narrate-stamp").write_text("b" * 40 + "\n" + sha(host.server.read_bytes()) + "\n")
    else:
        tool(host.server, 'echo "something else"')
    out = host.run("serve")
    assert out.returncode == 2 and "run just narrate-build-qwentts first" in out.stderr
    assert "git must not run" not in out.stderr


def test_a_current_build_is_not_rebuilt(host):
    out = host.run("build")
    assert out.returncode == 0, out.stderr
    assert "build is current" in out.stderr and "git must not run" not in out.stderr


def test_a_build_tree_open_to_others_is_refused(host):
    (host.out / "narrate-stamp").unlink()
    host.build.chmod(0o755)
    out = host.run("build")
    assert out.returncode == 2 and "must have mode 0700" in out.stderr
    assert "git must not run" not in out.stderr


def test_the_loopback_patch_drops_cors_and_refuses_browser_origins():
    patch = PATCHES[1].read_text()
    removed = [line for line in patch.splitlines() if line.startswith("-") and not line.startswith("---")]
    added = "\n".join(line for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
    assert any('"Access-Control-Allow-Origin", "*"' in line for line in removed)
    assert any("svr.Options" in line for line in removed)
    assert "Access-Control" not in added
    assert 'req.has_header("Origin")' in added and "127.0.0.1" in added and "HandlerResponse::Handled" in added


@pytest.mark.parametrize("knob", ["NARRATE_QWENTTS_THREADS", "NARRATE_QWENTTS_JOBS"])
def test_thread_and_job_knobs_stop_at_8(tmp_path, knob):
    out = run([str(QWENTTS), "build"], env(tmp_path, **{knob: "9", "NARRATE_QWENTTS_DEVICE": "CPU"}))
    assert out.returncode == 2 and knob in out.stderr


def test_whisper_recipes_run_bounded():
    recipes = (ROOT / "just" / "narrate.just").read_text()
    for name in ("narrate-render", "narrate-eval"):
        body = re.search(rf"^{name}\b.*:\n((?:    .*\n)+)", recipes, re.M).group(1)
        assert body.strip().startswith("narrate/bounded.sh python3 -m narrate"), name
    assert "narrate-serve-cpu" not in recipes


@pytest.mark.parametrize(("asked", "used"), [(16, 4), (4, 4), (2, 2), (0, 1)])
def test_whisper_gets_at_most_4_threads(asked, used):
    cfg = SimpleNamespace(whisper={"threads": asked, "language": "en"}, whisper_model="absent.bin")
    assert qa.Whisper(cfg).whisper["threads"] == used
