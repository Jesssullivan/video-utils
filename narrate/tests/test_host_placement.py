"""The host placement rule (docs/spec/NARRATE.md, "Host placement and memory") as the code enforces it: the
qwentts.cpp serve script refuses a host that has not opted in, heavy recipes run through narrate/bounded.sh, which
waits on memory pressure and opens a MemoryMax scope at nice 19, and whisper never gets more than 4 threads. Fake
systemd-run and systemctl binaries stand in for the real ones; nothing heavy runs."""

import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from narrate import qa

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parent
BOUNDED = PACKAGE / "bounded.sh"
QWENTTS = PACKAGE / "serve" / "qwentts.sh"
PLACEMENT_ENV = (
    "NARRATE_BOUNDED",
    "NARRATE_MEMORY_MAX",
    "NARRATE_PSI_MAX",
    "NARRATE_PSI_WAIT_S",
    "NARRATE_PSI_FILE",
    "NARRATE_TTS_HOST_ALLOWED",
    "NARRATE_QWENTTS_DEVICE",
    "NARRATE_WEIGHTS_DIR",
)


def env(tmp_path, **extra):
    """The caller's environment without any placement knob, a calm pressure file, and fake systemd tools first on
    PATH (systemctl succeeds unless extra says otherwise)."""
    base = {k: v for k, v in os.environ.items() if k not in PLACEMENT_ENV}
    calm = tmp_path / "calm"
    calm.write_text("some avg10=0.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n")
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    tool(fake / "systemd-run", 'echo "systemd-run $*"')
    tool(fake / "systemctl", "exit 0")
    return base | {"PATH": f"{fake}{os.pathsep}{base['PATH']}", "NARRATE_PSI_FILE": str(calm)} | extra


def tool(path, body):
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)


def run(cmd, environ):
    return subprocess.run(cmd, env=environ, capture_output=True, text=True, timeout=60)


def test_bounded_opens_a_6g_scope_at_nice_19(tmp_path):
    out = run([str(BOUNDED), "echo", "hi"], env(tmp_path))
    assert out.returncode == 0, out.stderr
    words = out.stdout.split()
    assert words[:6] == ["systemd-run", "--user", "--scope", "--quiet", "--collect", "-p"]
    assert words[6] == "MemoryMax=6G"
    assert words[7:10] == ["nice", "-n", "19"]
    assert words[-2:] == ["echo", "hi"]


def test_bounded_takes_another_ceiling(tmp_path):
    out = run([str(BOUNDED), "true"], env(tmp_path, NARRATE_MEMORY_MAX="14G"))
    assert "MemoryMax=14G" in out.stdout.split()
    refused = run([str(BOUNDED), "true"], env(tmp_path, NARRATE_MEMORY_MAX="lots"))
    assert refused.returncode == 2 and "NARRATE_MEMORY_MAX" in refused.stderr


def test_without_user_systemd_it_still_runs_at_nice_19(tmp_path):
    environ = env(tmp_path)
    tool(tmp_path / "bin" / "systemctl", "exit 1")
    out = run([str(BOUNDED), "sh", "-c", "nice; echo bounded=$NARRATE_BOUNDED"], environ)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["19", "bounded=1"]
    assert "without a memory ceiling" in out.stderr


def test_a_nested_call_runs_the_command_directly(tmp_path):
    out = run([str(BOUNDED), "sh", "-c", "echo direct"], env(tmp_path, NARRATE_BOUNDED="1"))
    assert out.stdout.strip() == "direct"


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


def test_serve_refuses_a_host_that_has_not_opted_in(tmp_path):
    out = run([str(QWENTTS), "serve"], env(tmp_path, NARRATE_QWENTTS_DEVICE="Vulkan0"))
    assert out.returncode == 2
    assert "refused" in out.stderr and "Host placement and memory" in out.stderr


@pytest.mark.parametrize(
    ("device", "message"),
    [(None, "set NARRATE_QWENTTS_DEVICE"), ("CUDA0", "must be Vulkan0..9, MTL0..9 or CPU")],
)
def test_serve_needs_a_named_device(tmp_path, device, message):
    extra = {"NARRATE_TTS_HOST_ALLOWED": "1"} | ({"NARRATE_QWENTTS_DEVICE": device} if device else {})
    out = run([str(QWENTTS), "serve"], env(tmp_path, **extra))
    assert out.returncode == 2 and message in out.stderr


def test_serve_needs_the_private_weights(tmp_path):
    extra = {"NARRATE_TTS_HOST_ALLOWED": "1", "NARRATE_QWENTTS_DEVICE": "Vulkan0"}
    out = run([str(QWENTTS), "serve"], env(tmp_path, **extra))
    assert out.returncode == 2 and "NARRATE_WEIGHTS_DIR" in out.stderr


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
