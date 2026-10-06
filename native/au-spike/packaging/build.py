#!/usr/bin/env python3
"""Compile and inspect owned AUv3 bundles without launch or registration."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
LANE = ROOT / "native/au-spike/packaging"
BUILD = ROOT / ".cache/au-packaging"
NATIVE = "native/au-spike/"
FROZEN = ["Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "LICENSE", "src/lib.rs", "src/main.rs"] + [
    NATIVE + relative for relative in [
        "Cargo.toml", "Cargo.lock", "src/lib.rs", "include/video_utils_gain.h",
        "apple/GainKernel.h", "apple/GainKernel.mm", "apple/GuitarGainAudioUnit.swift",
        "automation/GainAutomation.hpp", "automation/GainAutomation.cpp",
        "automation/AppleEvents.hpp", "automation/AppleEvents.mm",
        "state/ParameterState.hpp", "state/ParameterState.cpp",
        "integration/ControlIngress.hpp", "integration/ControlIngress.cpp"]]
SUPPORT = ["automation/GainAutomation.cpp", "automation/AppleEvents.mm",
           "state/ParameterState.cpp", "integration/ControlIngress.cpp"]
ENTITLEMENTS = {"com.apple.security.app-sandbox": True}


def validate_targets(value):
    """The prototype's identity is fixed; drift needs a new reviewed plan."""
    if type(value) is not dict or value.get("schema_version") != 1:
        raise ValueError("unsupported target schema")
    if value.get("architecture") != "arm64" or value.get("deployment_target") != "26.0":
        raise ValueError("only the reviewed native arm64/macOS26 prototype is supported")
    expected = {
        "container": {"bundle": "VideoUtilsGainPrototype.app",
                      "identifier": "org.video-utils.gain.prototype", "executable": "VideoUtilsGainPrototype"},
        "extension": {"bundle": "VideoUtilsGain.appex", "identifier": "org.video-utils.gain.prototype.audio-unit",
                      "executable": "VideoUtilsGain", "principal_class": "VideoUtilsGainFactory",
                      "point": "com.apple.AudioUnit"}}
    for key, target in expected.items():
        if value.get(key) != target:
            raise ValueError(f"unreviewed {key} identity or layout")
    component = value.get("component")
    if type(component) is not dict:
        raise ValueError("missing component")
    for key, code in {"type": "aufx", "subtype": "vuGn", "manufacturer": "Jess"}.items():
        if component.get(key) != code or re.fullmatch(r"[A-Za-z0-9]{4}", component[key]) is None:
            raise ValueError("unreviewed four-character component identity")
    if type(component.get("version")) is not int or component["version"] != 65536:
        raise ValueError("unreviewed component version")
    if component.get("sandboxSafe") is not True or component.get("tags") != ["Effects", "Guitar"]:
        raise ValueError("unreviewed component sandbox metadata")
    if set(component) != {"type", "subtype", "manufacturer", "version", "name", "description", "sandboxSafe", "tags"}:
        raise ValueError("unexpected component metadata")
    if any(type(component.get(key)) is not str or not 1 <= len(component[key]) <= 160
           for key in ("name", "description")):
        raise ValueError("invalid component display text")
    if set(value) != {"schema_version", "architecture", "deployment_target", "container", "extension", "component"}:
        raise ValueError("unexpected target metadata")
    return value


def metadata(targets):
    common = {"CFBundleInfoDictionaryVersion": "6.0", "CFBundleVersion": "1",
              "CFBundleShortVersionString": "0.1.0", "LSMinimumSystemVersion": targets["deployment_target"]}
    app = {**common, "CFBundleIdentifier": targets["container"]["identifier"],
           "CFBundleExecutable": targets["container"]["executable"], "CFBundlePackageType": "APPL",
           "CFBundleName": "Guitar Gain Prototype", "NSPrincipalClass": "NSApplication"}
    extension = {**common, "CFBundleIdentifier": targets["extension"]["identifier"],
                 "CFBundleExecutable": targets["extension"]["executable"], "CFBundlePackageType": "XPC!",
                 "CFBundleName": "Guitar Gain",
                 "NSExtension": {"NSExtensionPointIdentifier": targets["extension"]["point"],
                                 "NSExtensionPrincipalClass": targets["extension"]["principal_class"],
                                 "NSExtensionAttributes": {"AudioComponents": [targets["component"]]}}}
    return app, extension


def validate_linkage(output):
    dependencies = []
    for line in output.splitlines()[1:]:
        dependency = line.strip().split(" (", 1)[0]
        if not dependency.startswith(("/System/Library/", "/usr/lib/")):
            raise ValueError("non-system dynamic dependency: " + dependency)
        dependencies.append(dependency)
    if not dependencies:
        raise ValueError("missing dynamic-linkage inspection")
    return dependencies


def validate_macho(headers, commands, deployment, sdk):
    # A thin image has exactly one Mach header. Do not accept a universal
    # image merely because one of its slices happens to contain ARM64.
    image_headers = [line.split() for line in headers.splitlines() if line.startswith("MH_")]
    if len(image_headers) != 1 or len(image_headers[0]) < 5:
        raise ValueError("expected one thin Mach-O executable")
    image = image_headers[0]
    if image[0] != "MH_MAGIC_64" or image[1] != "ARM64" or image[4] != "EXECUTE":
        raise ValueError("unexpected executable architecture/type")
    blocks = re.split(r"(?m)^Load command \d+\s*$", commands)
    versions = [block for block in blocks if re.search(r"(?m)^\s*cmd LC_BUILD_VERSION\s*$", block)]
    if len(versions) != 1:
        raise ValueError("expected one build-version command")
    def field(name):
        match = re.search(r"(?m)^\s*" + name + r"\s+(\S+)\s*$", versions[0])
        return match.group(1) if match else None
    if field("platform") not in {"1", "MACOS"} or field("minos") != deployment or field("sdk") != sdk:
        raise ValueError("unexpected build-version platform, deployment or SDK")
    mains = [block for block in blocks if re.search(r"(?m)^\s*cmd LC_MAIN\s*$", block)]
    if len(mains) != 1:
        raise ValueError("expected one executable entrypoint")
    return {"architecture": "arm64", "image_type": "EXECUTE", "deployment_target": deployment,
            "sdk_version": sdk, "slices": 1, "entrypoint_command_count": 1}


def hash_sources():
    files = [ROOT / relative for relative in FROZEN]
    files += sorted(path for path in LANE.iterdir() if path.is_file()
                    and path.suffix in {".py", ".swift", ".json", ".md"})
    result = {}
    for path in files:
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(ROOT):
            raise ValueError("unsafe source path")
        result[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    # Keep the frozen state boundary explicit in every packaging receipt.
    swift = (ROOT / NATIVE / "apple/GuitarGainAudioUnit.swift").read_text()
    if "fullStateSetterQualified = false" not in swift or "lastStateRestoreStatus = -100" not in swift:
        raise ValueError("frozen AU generic-state qualification boundary changed")
    return result


def safe_cache():
    if BUILD.is_symlink() or not BUILD.resolve().is_relative_to(ROOT):
        raise ValueError("cache path escapes repository")
    if BUILD.exists() and any(path.is_symlink() for path in BUILD.rglob("*")):
        raise ValueError("unexpected symlink in owned cache")


def run(command, receipt, timeout=120):
    command = [str(item) for item in command]
    receipt["commands"].append(command)
    process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
        env={**os.environ, "CARGO_BUILD_JOBS": "1"})
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # Only this invocation's still-live, identity-checked compiler group.
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
        raise RuntimeError(f"{command[0]} exited {process.returncode}: {stdout[-3000:]}\n{stderr[-3000:]}")
    return stdout, stderr


def build(targets, hashes, receipt):
    safe_cache()
    BUILD.mkdir(parents=True, exist_ok=True)
    snapshot = BUILD / "snapshot"
    for relative, expected in hashes.items():
        source = ROOT / relative
        content = source.read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("source changed before snapshot")
        destination = snapshot / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    lane = snapshot / NATIVE
    package = lane / "packaging"
    receipt["toolchains"] = {
        "rust": run(["rustc", "--version"], receipt)[0].strip(),
        "swift": run(["xcrun", "swiftc", "--version"], receipt)[0].strip(),
        "sdk_version": run(["xcrun", "--show-sdk-version"], receipt)[0].strip()}
    sdk = run(["xcrun", "--show-sdk-path"], receipt)[0].strip()
    receipt["sdk"] = sdk
    cargo_target = BUILD / "rust"
    run(["cargo", "build", "--offline", "--locked", "--release", "--jobs", "1",
         "--manifest-path", lane / "Cargo.toml", "--target-dir", cargo_target], receipt)
    library = cargo_target / "release/libvideo_utils_gain_ffi.a"
    receipt["rust_static_library_sha256"] = hashlib.sha256(library.read_bytes()).hexdigest()
    triple = "arm64-apple-macosx" + targets["deployment_target"]
    objects = []
    for relative in ["apple/GainKernel.mm", *SUPPORT]:
        obj = BUILD / (Path(relative).stem + ".o")
        run(["xcrun", "clang++", "-target", triple, "-std=c++17", "-fobjc-arc", "-fblocks",
             "-fapplication-extension", "-Wall", "-Wextra", "-isysroot", sdk,
             "-I", lane / "include", "-I", lane / "apple", "-c", lane / relative, "-o", obj], receipt)
        objects.append(obj)
    app = BUILD / targets["container"]["bundle"]
    extension = app / "Contents/PlugIns" / targets["extension"]["bundle"]
    app_metadata, extension_metadata = metadata(targets)
    for bundle, info in ((app, app_metadata), (extension, extension_metadata)):
        (bundle / "Contents/MacOS").mkdir(parents=True, exist_ok=True)
        (bundle / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
        (bundle / "Contents/Resources").mkdir(parents=True, exist_ok=True)
        (bundle / "Contents/Resources/LICENSE").write_bytes((snapshot / "LICENSE").read_bytes())
    entitlements = BUILD / "sandbox.entitlements"
    entitlements.write_bytes(plistlib.dumps(ENTITLEMENTS))
    module_cache = BUILD / "swift-module-cache"
    common = ["xcrun", "swiftc", "-j1", "-swift-version", "6", "-sdk", sdk,
              "-target", triple, "-module-cache-path", module_cache]
    extension_exe = extension / "Contents/MacOS" / targets["extension"]["executable"]
    app_exe = app / "Contents/MacOS" / targets["container"]["executable"]
    run([*common, "-application-extension", "-module-name", "VideoUtilsGainExtension",
         "-import-objc-header", lane / "apple/GainKernel.h",
         lane / "apple/GuitarGainAudioUnit.swift", package / "AudioUnitFactory.swift",
         *objects, library, "-lc++", "-framework", "Foundation", "-framework", "AudioToolbox",
         "-framework", "AVFAudio", "-Xlinker", "-e", "-Xlinker", "_NSExtensionMain",
         "-o", extension_exe], receipt)
    run([*common, "-parse-as-library", "-module-name", "VideoUtilsGainContainer",
         package / "ContainerApp.swift", "-framework", "AppKit", "-o", app_exe], receipt)
    receipt["signing"] = {"identity": "ad-hoc", "distribution_qualified": False, "targets": {}}
    for bundle in (extension, app):
        run(["codesign", "--force", "--sign", "-", "--entitlements", entitlements, bundle], receipt)
    run(["codesign", "--verify", "--strict", "--deep", app], receipt)
    receipt["binaries"] = {}
    for name, bundle, binary, expected_info in (("extension", extension, extension_exe, extension_metadata),
                                                ("container", app, app_exe, app_metadata)):
        run(["plutil", "-lint", bundle / "Contents/Info.plist"], receipt)
        if plistlib.loads((bundle / "Contents/Info.plist").read_bytes()) != expected_info:
            raise ValueError("bundle metadata changed")
        _, signing = run(["codesign", "--display", "--verbose=4", bundle], receipt)
        if "Signature=adhoc" not in signing or "Identifier=" + expected_info["CFBundleIdentifier"] not in signing:
            raise ValueError("unexpected signing identity")
        ent_text, _ = run(["codesign", "--display", "--entitlements", ":-", bundle], receipt)
        if plistlib.loads(ent_text.encode()) != ENTITLEMENTS:
            raise ValueError("unexpected signed entitlement")
        linkage = validate_linkage(run(["xcrun", "otool", "-L", binary], receipt)[0])
        headers = run(["xcrun", "otool", "-hv", binary], receipt)[0]
        load_commands = run(["xcrun", "otool", "-l", binary], receipt)[0]
        macho = validate_macho(headers, load_commands, targets["deployment_target"],
                               receipt["toolchains"]["sdk_version"])
        receipt["binaries"][name] = {"relative_path": str(binary.relative_to(BUILD)),
            "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "dynamic_dependencies": linkage,
            "mach_o_header": headers.strip(), "validated_mach_o": macho, "signed_entitlements": ENTITLEMENTS}
        receipt["signing"]["targets"][name] = signing.strip()
    symbols = run(["xcrun", "nm", "-g", extension_exe], receipt)[0]
    required = ["_OBJC_CLASS_$_VideoUtilsGainFactory", "_OBJC_CLASS_$_GuitarGainAudioUnit", "_vu_gain_process"]
    if any(not any(line.endswith(" " + symbol) and " U " not in line for line in symbols.splitlines())
           for symbol in required):
        raise ValueError("extension misses a defined factory, AU or Rust gain ABI symbol")
    if "_NSExtensionMain" not in symbols:
        raise ValueError("extension entrypoint does not reference Apple's extension main")
    receipt["extension_symbols"] = {"defined_required": required, "entry_reference": "_NSExtensionMain",
                                     "factory_executed": False}
    expected_files = {"Contents/Info.plist", "Contents/MacOS/VideoUtilsGainPrototype",
        "Contents/Resources/LICENSE", "Contents/_CodeSignature/CodeResources",
        "Contents/PlugIns/VideoUtilsGain.appex/Contents/Info.plist",
        "Contents/PlugIns/VideoUtilsGain.appex/Contents/MacOS/VideoUtilsGain",
        "Contents/PlugIns/VideoUtilsGain.appex/Contents/Resources/LICENSE",
        "Contents/PlugIns/VideoUtilsGain.appex/Contents/_CodeSignature/CodeResources"}
    files = {str(path.relative_to(app)) for path in app.rglob("*") if path.is_file()}
    if files != expected_files or any(path.is_symlink() for path in app.rglob("*")):
        raise ValueError("unexpected bundle inventory or symlink")
    receipt["bundle_inventory"] = sorted(files)
    if hash_sources() != hashes:
        raise ValueError("source changed during packaging; do not accept artifact")
    receipt["status"] = "bundle_compiled_signed_inspected_not_activated"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--dry-run", action="store_true")
    choice.add_argument("--build", action="store_true")
    args = parser.parse_args()
    receipt = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "authority": "Operator-approved packaging lane; R-HOOK-CONVERGENCE-20261004/R-N12/R-N13",
        "architecture": platform.machine(), "commands": [],
        "app_launched": False, "window_display_verified": False, "extension_loaded": False,
        "registration_requested": False, "auval_performed": False, "logic_host_acceptance": "unverified",
        "audio_device_opened": False, "full_state_setter_qualified": False,
        "licensing": "MIT repository source; Apple SDK/frameworks under existing Xcode license; no third-party source",
        "claim_scope": "owned compiler/signature/inspection actions; not a sampled global plugin registry"}
    try:
        targets = validate_targets(json.loads((LANE / "targets.json").read_text()))
        hashes = hash_sources()
        receipt.update(targets=targets, source_sha256=hashes)
        if args.dry_run:
            receipt["status"] = "design_manifest_only_no_commands_invoked"
        else:
            if platform.system() != "Darwin" or platform.machine() != "arm64":
                raise ValueError("existing native Apple arm64 toolchain required; nothing installed")
            build(targets, hashes, receipt)
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        receipt["status"] = "failed"
        receipt["error"] = str(error)
    if args.build:
        safe_cache()
        BUILD.mkdir(parents=True, exist_ok=True)
        pending = BUILD / ".receipt.json.pending"
        pending.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
        pending.replace(BUILD / "receipt.json")
    print(json.dumps(receipt, indent=2, allow_nan=False))
    return 1 if receipt["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
