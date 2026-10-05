"""Read-only toolchain diagnostics. Never prints environment secrets."""

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys


def tool_version(name, arguments):
    override = os.environ.get(name.upper()) if name in {"ffmpeg", "ffprobe"} else None
    executable = override or shutil.which(name)
    if not executable:
        return {"available": False}
    try:
        process = subprocess.run(
            [executable, *arguments], capture_output=True, text=True, timeout=10,
            check=False,
        )
        lines = (process.stdout or process.stderr).splitlines()
        return {
            "available": process.returncode == 0,
            "executable": executable,
            "version": lines[0][:240] if lines else "unknown",
            "exit_code": process.returncode,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "error": type(exc).__name__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-media", action="store_true")
    arguments = parser.parse_args()
    # Rust is optional for today's Python pipeline. Do not invoke guarded compiler
    # launchers or realize a Nix development environment during diagnostics.
    tools = {
        "ffmpeg": tool_version("ffmpeg", ["-version"]),
        "ffprobe": tool_version("ffprobe", ["-version"]),
        "just": tool_version("just", ["--version"]),
        "quarto": tool_version("quarto", ["--version"]),
        "R": tool_version("R", ["--version"]),
        "python": {"available": True, "executable": sys.executable, "version": sys.version.split()[0]},
        "cargo": {"available": shutil.which("cargo") is not None, "version": "not queried (optional compiler)"},
        "nix": {"available": shutil.which("nix") is not None, "version": "not queried (no realization)"},
    }
    optional = {name: importlib.util.find_spec(name) is not None for name in ("numpy", "scipy", "librosa", "soundfile", "torch")}
    print(json.dumps({"schema_version": 1, "tools": tools, "optional_python": optional, "model_downloads": "explicit hash-bound prefetch only"}, indent=2))
    return int(arguments.require_media and not all(tools[name]["available"] for name in ("ffmpeg", "ffprobe")))


if __name__ == "__main__":
    raise SystemExit(main())
