#!/usr/bin/env python3
"""Bounded local ABI/kernel/Swift checks; no plugin installation or registration."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
LANE = ROOT / "native/au-spike"
BUILD = ROOT / ".cache/au-spike"
COMMANDS = []


def run(command, timeout=120):
    COMMANDS.append([str(value) for value in command])
    process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True,
                               env={**os.environ, "CARGO_BUILD_JOBS": "1"})
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # This invocation created the process group. Check its actual identity
        # and liveness before stopping only owned compiler/harness descendants.
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
        raise RuntimeError(f"{command[0]} failed ({process.returncode}):\n{stdout[-4000:]}\n{stderr[-4000:]}")
    return stdout.strip()


def inspect_render_object(path):
    """Catch ARC ownership inserted into the two direct render-side bodies.

    Getter/copy/dispose ownership is intentional and occurs outside rendering.
    This inspection complements, rather than replaces, behavioral counters and
    source review; it does not audit arbitrary host callbacks or all callees.
    """
    assembly = run(["xcrun", "llvm-objdump", "--macho", "--disassemble",
                    "--symbolize-operands", str(path)])
    bodies = {}
    name = None
    for line in assembly.splitlines():
        if line.endswith(":") and line and not line[0].isspace():
            name = line[:-1]
            bodies[name] = []
        elif name:
            bodies[name].append(line)
    selected = {name: body for name, body in bodies.items()
                if "VUGainKernel renderBlock]_block_invoke" in name
                or "GLOBAL__N_16renderE" in name}
    if len(selected) != 2:
        raise RuntimeError("compiled render audit could not locate callback and helper bodies")
    references = [line.strip() for body in selected.values() for line in body
                  if "_objc_" in line or "_Block_" in line]
    if references:
        raise RuntimeError("Objective-C/Block ownership runtime enters rendering: " + "; ".join(references))
    return {"status": "passed", "symbols_checked": sorted(selected),
            "objc_block_runtime_references": references,
            "scope": "direct callback/helper; not arbitrary host callbacks or every callee"}


def main():
    if platform.system() != "Darwin":
        print(json.dumps({"status": "unsupported", "reason": "Apple SDK required; no tools installed"}))
        return 2
    BUILD.mkdir(parents=True, exist_ok=True)
    receipt = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
               "architecture": platform.machine(), "au_extension_packaged": False,
               "component_registered": False, "auval": "not_performed",
               "logic_host_loaded": False, "audio_device_opened": False,
               "licensing": "MIT repository code plus Apple system frameworks; no third-party source",
               "authority": "Operator-approved native scaffold; R-HOOK-CONVERGENCE-20261004/R-N12/R-N13",
               "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in sorted(LANE.rglob("*")) if path.is_file()
                                 and path.suffix in {".rs", ".c", ".h", ".mm", ".swift", ".py", ".toml", ".lock"}}}
    receipt["source_sha256"]["src/lib.rs"] = hashlib.sha256((ROOT / "src/lib.rs").read_bytes()).hexdigest()
    try:
        receipt["toolchains"] = {"rust": run(["rustc", "--version"]),
                                 "swift": run(["swift", "--version"])}
        sdk = run(["xcrun", "--show-sdk-path"])
        receipt["sdk"] = sdk
        cargo = ["cargo", "--offline", "--locked"]
        manifest = ["--manifest-path", str(LANE / "Cargo.toml"),
                    "--target-dir", str(BUILD / "rust"), "--jobs", "1"]
        # Global Cargo flags belong after the subcommand on some Cargo versions.
        test = run([cargo[0], "test", *cargo[1:], *manifest, "--", "--test-threads=1"])
        receipt["rust_test_output"] = test
        run([cargo[0], "build", *cargo[1:], "--release", *manifest])
        library = BUILD / "rust/release/libvideo_utils_gain_ffi.a"
        frameworks = ["-framework", "Foundation", "-framework", "AudioToolbox", "-framework", "AVFAudio"]
        includes = ["-I", str(LANE / "include"), "-I", str(LANE / "apple")]
        run(["xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
             *includes, str(LANE / "tests/abi_harness.c"), str(library), "-o", str(BUILD / "abi-harness")])
        receipt["c_abi"] = json.loads(run([str(BUILD / "abi-harness")]))
        native = ["xcrun", "clang++", "-std=c++17", "-fobjc-arc", "-fblocks",
                  "-Wall", "-Wextra", "-isysroot", sdk, *includes]
        kernel = BUILD / "GainKernel.o"
        run([*native, "-c", str(LANE / "apple/GainKernel.mm"), "-o", str(kernel)])
        receipt["compiled_render_runtime_audit"] = inspect_render_object(kernel)
        run([*native, str(LANE / "tests/kernel_harness.mm"), str(kernel), str(library),
             *frameworks, "-o", str(BUILD / "kernel-harness")])
        receipt["native_kernel"] = json.loads(run([str(BUILD / "kernel-harness")]))
        swift = ["xcrun", "swiftc", "-j1", "-swift-version", "6", "-sdk", sdk,
                 "-module-cache-path", str(BUILD / "swift-module-cache"),
                 "-import-objc-header", str(LANE / "apple/GainKernel.h"),
                 str(LANE / "apple/GuitarGainAudioUnit.swift"), str(kernel), str(library),
                 "-lc++", *frameworks]
        run([*swift, "-emit-library", "-emit-module", "-module-name", "VideoUtilsAUSpike",
             "-emit-module-path", str(BUILD / "VideoUtilsAUSpike.swiftmodule"),
             "-o", str(BUILD / "libVideoUtilsAUSpike.dylib")])
        run([*swift, str(LANE / "tests/main.swift"), "-o", str(BUILD / "swift-lifecycle")])
        receipt["swift_lifecycle"] = json.loads(run([str(BUILD / "swift-lifecycle")]))
        receipt["status"] = "native_checks_passed_not_au_host_qualified"
    except (RuntimeError, OSError, subprocess.TimeoutExpired, ValueError) as error:
        receipt["status"] = "failed"
        receipt["error"] = str(error)
    receipt["commands"] = COMMANDS
    temporary = BUILD / ".receipt.json.pending"
    temporary.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
    temporary.replace(BUILD / "receipt.json")
    print(json.dumps(receipt, indent=2, allow_nan=False))
    return 0 if receipt["status"] == "native_checks_passed_not_au_host_qualified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
