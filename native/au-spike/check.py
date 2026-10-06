#!/usr/bin/env python3
"""Bounded local ABI/kernel/Swift checks (gain and biquad C ABIs); no plugin installation or registration."""
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
                or "GLOBAL__N_16renderE" in name
                or "VUGainKernel gainValueObserver]_block_invoke" in name
                or "VUGainKernel gainValueProvider]_block_invoke" in name}
    if len(selected) != 4:
        raise RuntimeError("compiled render audit could not locate render/helper/parameter bodies")
    forbidden = ("_objc_", "_Block_", "_malloc", "_calloc", "_realloc", "__Zn", "pthread_mutex", "dispatch_", "_printf", "_fopen")
    references = [line.strip() for body in selected.values() for line in body
                  if any(token in line for token in forbidden)]
    if references:
        raise RuntimeError("Forbidden runtime enters rendering: " + "; ".join(references))
    return {"status": "passed", "symbols_checked": sorted(selected),
            "objc_block_runtime_references": references,
            "scope": "direct callback/helper; not arbitrary host callbacks or every callee"}


def inspect_support_object(path, tokens):
    assembly = run(["xcrun", "llvm-objdump", "--macho", "--disassemble", "--symbolize-operands", str(path)])
    bodies, name = {}, None
    for line in assembly.splitlines():
        if line.endswith(":") and line and not line[0].isspace():
            name = line[:-1]
            bodies[name] = []
        elif name:
            bodies[name].append(line)
    selected = {name: lines for name, lines in bodies.items() if any(token in name for token in tokens)}
    if any(not any(token in name for name in selected) for token in tokens):
        raise RuntimeError("support audit missing required symbol")
    forbidden = ("_objc_", "_Block_", "_malloc", "_calloc", "_realloc", "__Zn", "pthread_mutex", "dispatch_", "_printf", "_fopen")
    hits = [line.strip() for lines in selected.values() for line in lines if any(token in line for token in forbidden)]
    if hits:
        raise RuntimeError("support processing runtime audit failed: " + "; ".join(hits))
    return {"symbols_checked": sorted(selected), "forbidden_direct_references": hits,
            "scope": "named direct native helpers; atomics not qualified wait-free; not arbitrary hosts/all callees"}


BIQUAD_FORBIDDEN = ("_malloc", "_calloc", "_realloc", "__rust_alloc", "__rust_dealloc",
                    "pthread_mutex", "dispatch_", "_printf", "_write", "_objc_")
BIQUAD_FFI_TESTS = ("ffi_matches_rust_biquad_bit_for_bit", "refusals_are_atomic",
                    "render_calls_do_not_allocate", "set_keeps_delay_line_and_reset_zeroes_it",
                    "zero_count_with_null_samples_is_ok_and_keeps_state")


def disassemble_symbol(library, symbol):
    """Direct body of one symbol in the release staticlib, with relocations."""
    text = run(["xcrun", "llvm-objdump", "--disassemble", "--reloc",
                "--disassemble-symbols=" + symbol, str(library)])
    lines, inside = [], False
    for line in text.splitlines():
        if line.rstrip().endswith("<" + symbol + ">:"):
            inside = True
            continue
        if inside and (not line.strip() or "file format" in line):
            break
        if inside:
            lines.append(line.strip())
    if not lines:
        raise RuntimeError("biquad audit could not locate " + symbol)
    return lines


def inspect_biquad_process(library):
    """Forbidden-reference audit of the compiled `_vu_biquad_process` body.

    Scope is the direct body plus, as a supplementary record, the direct
    `video_utils` callees it branches to; it is not an audit of every callee.
    """
    body = disassemble_symbol(library, "_vu_biquad_process")
    hits = [line for line in body if any(token in line for token in BIQUAD_FORBIDDEN)]
    callees = sorted({line.split()[-1] for line in body if "ARM64_RELOC_BRANCH26" in line})
    callee_hits = {}
    for callee in callees:
        if callee.startswith("__ZN11video_utils"):
            callee_body = disassemble_symbol(library, callee)
            callee_hits[callee] = [line for line in callee_body
                                   if any(token in line for token in BIQUAD_FORBIDDEN)]
    if hits:
        raise RuntimeError("Forbidden runtime enters vu_biquad_process: " + "; ".join(hits))
    return {"status": "passed", "symbol": "_vu_biquad_process", "body_lines_with_relocations": len(body),
            "forbidden_tokens": list(BIQUAD_FORBIDDEN), "forbidden_direct_references": hits,
            "direct_callees": callees,
            "supplementary_video_utils_callee_forbidden_references": callee_hits,
            "scope": "direct body of the release staticlib symbol; supplementary direct video_utils callees; not every callee"}


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
                                 and path.suffix in {".rs", ".c", ".h", ".cpp", ".hpp", ".mm", ".swift", ".py", ".toml", ".lock"}}}
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
        missing = [name for name in BIQUAD_FFI_TESTS if f"test {name} ... ok" not in test]
        if missing:
            raise RuntimeError("biquad FFI tests missing or failed: " + ", ".join(missing))
        receipt["biquad_ffi_tests"] = {"status": "passed", "tests": list(BIQUAD_FFI_TESTS),
                                       "denominators": {"parity_cases": 150, "refusal_cases": 20,
                                                        "allocation_calls": 2048}}
        run(["xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror", "-ffp-contract=off",
             *includes, str(LANE / "tests/biquad_abi_harness.c"), str(library),
             "-o", str(BUILD / "biquad-abi-harness")])
        receipt["c_biquad_abi"] = json.loads(run([str(BUILD / "biquad-abi-harness")]))
        if receipt["c_biquad_abi"].get("c_biquad_abi") != "passed":
            raise RuntimeError("biquad C harness did not pass")
        receipt["biquad_process_runtime_audit"] = inspect_biquad_process(library)
        native = ["xcrun", "clang++", "-std=c++17", "-fobjc-arc", "-fblocks",
                  "-Wall", "-Wextra", "-isysroot", sdk, *includes]
        kernel = BUILD / "GainKernel.o"
        run([*native, "-c", str(LANE / "apple/GainKernel.mm"), "-o", str(kernel)])
        receipt["compiled_render_runtime_audit"] = inspect_render_object(kernel)
        supporting = []
        receipt["support_runtime_audits"] = {}
        support_tokens = {"GainAutomation": ["6Engine7process", "6Engine5begin", "6Engine7advance"],
                          "AppleEvents": ["12convertApple"], "ParameterState": ["7Session"],
                          "ControlIngress": ["14ControlIngress"]}
        for relative in ["automation/GainAutomation.cpp", "automation/AppleEvents.mm", "state/ParameterState.cpp", "integration/ControlIngress.cpp"]:
            path = BUILD / (Path(relative).stem + ".o")
            run([*native, "-c", str(LANE / relative), "-o", str(path)])
            supporting.append(str(path))
            receipt["support_runtime_audits"][Path(relative).stem] = inspect_support_object(path,support_tokens[Path(relative).stem])
        run([*native, str(LANE / "tests/kernel_harness.mm"), str(kernel), *supporting, str(library),
             *frameworks, "-o", str(BUILD / "kernel-harness")])
        receipt["native_kernel"] = json.loads(run([str(BUILD / "kernel-harness")]))
        integrated_sources = [str(LANE / "integration/parameter_state_harness.mm"), str(kernel), *supporting, str(library)]
        run([*native, *integrated_sources, *frameworks, "-o", str(BUILD / "parameter-state-harness")])
        receipt["parameter_state_release"] = json.loads(run([str(BUILD / "parameter-state-harness")]))
        # Instrument the owned native sources and harness; the unchanged Rust ABI
        # remains separately qualified by its tests/allocation receipt.
        sanitized_sources = [str(LANE / "integration/parameter_state_harness.mm"),
                             str(LANE / "apple/GainKernel.mm"),
                             *[str(LANE / relative) for relative in ["automation/GainAutomation.cpp", "automation/AppleEvents.mm", "state/ParameterState.cpp", "integration/ControlIngress.cpp"]], str(library)]
        run([*native, "-O1", "-fsanitize=address,undefined", "-fno-omit-frame-pointer", *sanitized_sources,
             *frameworks, "-o", str(BUILD / "parameter-state-sanitized")])
        receipt["parameter_state_asan_ubsan"] = json.loads(run([str(BUILD / "parameter-state-sanitized")]))
        swift = ["xcrun", "swiftc", "-j1", "-swift-version", "6", "-sdk", sdk,
                 "-module-cache-path", str(BUILD / "swift-module-cache"),
                 "-import-objc-header", str(LANE / "apple/GainKernel.h"),
                 str(LANE / "apple/GuitarGainAudioUnit.swift"), str(kernel), *supporting, str(library),
                 "-lc++", *frameworks]
        run([*swift, "-emit-library", "-emit-module", "-module-name", "VideoUtilsAUSpike",
             "-emit-module-path", str(BUILD / "VideoUtilsAUSpike.swiftmodule"),
             "-o", str(BUILD / "libVideoUtilsAUSpike.dylib")])
        run([*swift, str(LANE / "tests/main.swift"), "-o", str(BUILD / "swift-lifecycle")])
        receipt["swift_lifecycle"] = json.loads(run([str(BUILD / "swift-lifecycle")]))
        run([*swift, str(LANE / "integration/state_harness.swift"), "-o", str(BUILD / "swift-state")])
        receipt["swift_parameter_state"] = json.loads(run([str(BUILD / "swift-state")]))
        if any(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected
               for relative, expected in receipt["source_sha256"].items()):
            raise RuntimeError("source changed during check; rerun against stable source")
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
