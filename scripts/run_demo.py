#!/usr/bin/env python3
"""Render a private demo, then add independently qualified analysis and report."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def invoke(script: str, arguments: list[str], timeout: int = 1200,
           interpreter: str | None = None) -> dict:
    result = subprocess.run([interpreter or sys.executable, str(ROOT / "scripts" / script), *arguments],
                            stdin=subprocess.DEVNULL, capture_output=True, text=True,
                            timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(f"{script}: {result.stderr[-3000:]}")
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--profile", default="conservative3")
    parser.add_argument("--bpm", type=float, help="Approximate operator pulse; not an intended score")
    parser.add_argument("--backend", choices=("stdlib", "librosa"), default="stdlib")
    args = parser.parse_args()
    if args.bpm is not None and (not math.isfinite(args.bpm) or not 20 <= args.bpm <= 400):
        parser.error("--bpm must be finite and between 20 and 400")
    analysis_python = os.environ.get("VIDEO_UTILS_ANALYSIS_PYTHON", sys.executable)
    analysis_options = ["--backend", args.backend]
    if args.bpm is not None:
        analysis_options += ["--bpm", str(args.bpm)]
    try:
        print("Rendering conservative audio and synchronized video…", file=sys.stderr)
        media = invoke("media.py", ["demo", args.input, "--profile", args.profile])
        directory = Path(media["run_dir"])
        processing_input = str(directory / "denoised.wav")
        stages = {"media": {"status": "rendered_unreviewed"}}
        for name, script, arguments in [
            ("rhythm", "rhythm.py", [processing_input, "--run-dir", str(directory), *analysis_options]),
            ("noise", "guitar_features.py", ["noise", processing_input, "--run-dir", str(directory)]),
            ("tone", "guitar_features.py", ["tone", processing_input, "--run-dir", str(directory)]),
            ("notes", "guitar_features.py", ["notes", processing_input, "--run-dir", str(directory)]),
            ("phrases", "guitar_features.py", ["phrases", processing_input, "--run-dir", str(directory), *analysis_options]),
        ]:
            if not (ROOT / "scripts" / script).is_file():
                stages[name] = {"status": "unavailable", "reason": "Worker not implemented"}
                continue
            print(f"Measuring {name} candidates…", file=sys.stderr)
            try:
                data = invoke(script, arguments, 600,
                              analysis_python if name in {"rhythm", "phrases"} and args.backend == "librosa" else None)
                stages[name] = {"status": "measured_candidates", "result": data}
            except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
                # A failed experimental analysis must not discard a completed render.
                stages[name] = {"status": "failed", "reason": str(exc)}
        for name, script in [("dag", "dag.py"), ("markers", "markers.py")]:
            if (ROOT / "scripts" / script).is_file():
                try:
                    stages[name] = {"status": "completed", "result": invoke(script, [str(directory)], 180)}
                except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
                    stages[name] = {"status": "failed", "reason": str(exc)}
        report = invoke("report.py", [str(directory)], 180)
        receipt = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                   "analysis_settings": {"backend": args.backend, "operator_bpm": args.bpm},
                   "run_dir": str(directory), "stages": stages, "report": report,
                   "listening_accepted": False, "instrument": {"strings": 9, "low_fundamental_hz": 32},
                   "authority": "Operator approved implementation; R-HOOK-CONVERGENCE-20261004/R-N13"}
        temporary = directory / ".demo.json.pending"
        temporary.write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
        os.chmod(temporary, 0o600)
        temporary.replace(directory / "demo.json")
        latest = ROOT / "artifacts" / "latest.json"
        latest.write_text(json.dumps({"run_dir": str(directory), "report": str(directory / "report.html")}, indent=2) + "\n")
        os.chmod(latest, 0o600)
        print(json.dumps({"status": "rendered_unreviewed", "run_dir": str(directory),
                          "cleaned_wav": str(directory / "cleaned.wav"),
                          "video": media.get("export", {}).get("video"),
                          "report": str(directory / "report.html"),
                          "stage_status": {k: v["status"] for k, v in stages.items()}}, indent=2))
        return 0
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
