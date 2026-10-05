#!/usr/bin/env python3
"""Bounded private-state codec/lifecycle checks; no AU preset or host changes."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess

ROOT = Path(__file__).resolve().parents[3]
LANE = ROOT / "native/au-spike/state"
BUILD = ROOT / ".cache/au-state"
COMMANDS = []

def run(command):
    COMMANDS.append([str(part) for part in command])
    process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True,
                               env={**os.environ, "CARGO_BUILD_JOBS": "1"})
    try:
        out, err = process.communicate(timeout=120)
    except subprocess.TimeoutExpired:
        if process.poll() is None:
            try:
                if os.getpgid(process.pid) == process.pid:
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
        process.communicate()
        raise
    if process.returncode:
        raise RuntimeError(f"{command[0]} exit {process.returncode}: {out[-3000:]}\n{err[-3000:]}")
    return out.strip()

def audit(path, required):
    assembly = run(["xcrun", "llvm-objdump", "--macho", "--disassemble", "--symbolize-operands", str(path)])
    bodies = {}
    name = None
    for line in assembly.splitlines():
        if line.endswith(":") and line and not line[0].isspace():
            name = line[:-1]
            bodies[name] = []
        elif name:
            bodies[name].append(line)
    selected = {name: lines for name, lines in bodies.items() if any(token in name for token in required)}
    if any(not any(token in name for name in selected) for token in required):
        raise RuntimeError("audit missing required render-side symbol")
    forbidden = ("_objc_", "_Block_", "_malloc", "_calloc", "_realloc", "__Zn", "pthread_mutex", "dispatch_")
    hits = [line.strip() for lines in selected.values() for line in lines if any(token in line for token in forbidden)]
    if hits:
        raise RuntimeError("render runtime audit failed: " + "; ".join(hits))
    return {"symbols": sorted(selected), "forbidden_direct_references": hits,
            "scope": "direct unoptimized processing functions; not every callee or host callback"}

def main():
    if platform.system() != "Darwin":
        print(json.dumps({"status": "unsupported", "reason": "Installed Apple development tools required"}))
        return 2
    BUILD.mkdir(parents=True, exist_ok=True)
    sources = list(LANE.iterdir()) + [ROOT / name for name in [
        "src/lib.rs", "Cargo.toml", "Cargo.lock", "native/au-spike/Cargo.toml",
        "native/au-spike/Cargo.lock", "native/au-spike/src/lib.rs", "native/au-spike/include/video_utils_gain.h",
        "native/au-spike/automation/GainAutomation.hpp", "native/au-spike/automation/GainAutomation.cpp"]]
    receipt = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
               "au_fullState_implemented": False, "au_packaged": False, "auval": "not_performed",
               "logic_host_loaded": False, "audio_device_opened": False,
               "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted(sources) if p.is_file()},
               "authority": "Operator ten-hour goal; GRAPH_INTEGRATION_LANE; R-HOOK-CONVERGENCE-20261004/R-N11/R-N12/R-N13"}
    try:
        receipt["rustc"] = run(["rustc", "--version"])
        receipt["clang"] = run(["xcrun", "clang++", "--version"])
        sdk = run(["xcrun", "--show-sdk-path"])
        receipt["sdk"] = sdk
        run(["cargo", "build", "--release", "--offline", "--locked", "--jobs", "1",
             "--manifest-path", str(LANE.parent / "Cargo.toml"), "--target-dir", str(BUILD / "rust")])
        library = BUILD / "rust/release/libvideo_utils_gain_ffi.a"
        common = ["xcrun", "clang++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-isysroot", sdk]
        object_path = BUILD / "ParameterState.audit.o"
        run([*common, "-O0", "-c", str(LANE / "ParameterState.cpp"), "-o", str(object_path)])
        receipt["session_render_audit"] = audit(object_path,["7Session7process"])
        gain_object = BUILD / "GainAutomation.audit.o"
        run([*common, "-O0", "-c", str(LANE.parent / "automation/GainAutomation.cpp"), "-o", str(gain_object)])
        receipt["gain_render_audit"] = audit(gain_object,["6Engine7process", "6Engine5begin", "6Engine7advance"])
        sources_compile = [str(LANE / "ParameterState.cpp"), str(LANE / "tests.cpp"),
                           str(LANE.parent / "automation/GainAutomation.cpp"), str(library)]
        executable = BUILD / "state-tests"
        run([*common, "-O2", *sources_compile, "-o", str(executable)])
        receipt["release_behavior"] = json.loads(run([str(executable)]))
        sanitized = BUILD / "state-sanitized"
        run([*common, "-O1", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
             *sources_compile, "-o", str(sanitized)])
        receipt["asan_ubsan_behavior"] = json.loads(run([str(sanitized)]))
        if any(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected
               for relative, expected in receipt["source_sha256"].items()):
            raise RuntimeError("source changed during check; rerun against stable source")
        receipt["status"] = "isolated_state_passed_not_au_host_qualified"
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as error:
        receipt["status"] = "failed"
        receipt["error"] = str(error)
    receipt["commands"] = COMMANDS
    pending = BUILD / ".receipt.json.pending"
    pending.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
    pending.replace(BUILD / "receipt.json")
    print(json.dumps(receipt, indent=2, allow_nan=False))
    return 0 if receipt["status"] == "isolated_state_passed_not_au_host_qualified" else 1

if __name__ == "__main__":
    raise SystemExit(main())
