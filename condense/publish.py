"""Publish one condensed talk as a hash-bound run under artifacts/condense/<run_id>/.

The manifest's timeline mapping is edl_v1 (docs/spec/TIMELINE_CONTRACT.md): output time maps to source time
through edl.json, so `no_time_stretch` is false and no guitar tool accepts the run. The run is staged, renamed
into place, then checked by `video-utils verify-run --timeline edl_v1`. A run that verify-run refuses is
renamed to .failed-<run_id> and the stage exits 1. The binary is found before anything is staged; a verify-run
that cannot start, crashes or runs over the time limit refuses nothing, so the run keeps its name, a file
.unverified-<run_id> beside it says why, and the stage exits 1.

When the check stage wrote work/check.json for this very edit (its delivery and edl.json sha256 equal the
outputs'), the run carries it as check.json and the manifest records its sha256, status and summary. A
check.json of another edit, or one that is not a check report, is refused; without one the manifest says the
check was not run. A partial check (work/check.partial.json) is never published, and one of the same edit
that is newer than check.json and says failed or not_measured refuses the publish: check.json is stale.
"""

import hashlib
import json
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

from . import audio, timeline
from .config import TIMEOUT_S, run

ARTIFACTS = timeline.ROOT / "artifacts" / "condense"
CHECK_REPORT = ("check", "json")  # work/check.json, written by the check stage when all four gates ran
PARTIAL_REPORT = ("check", "partial.json")  # work/check.partial.json, when only some ran; never published
STATUSES = ("passed", "partial", "not_measured", "failed")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def outputs(cfg):
    """Published name -> local file: the edit, its EDL and whichever captions and corrected copy exist."""
    found = {"talk.mp4": cfg.out, "edl.json": cfg.f("edl", "json")}
    for name, path in (
        ("talk.srt", cfg.out.with_suffix(".srt")),
        ("talk.vtt", cfg.out.with_suffix(".vtt")),
        ("talk.corrected.mp4", cfg.out.with_suffix(".corrected.mp4")),
    ):
        if path.is_file():
            found[name] = path
    for name in ("talk.mp4", "edl.json"):
        if not found[name].is_file():
            raise FileNotFoundError(f"{found[name]}: run the render stage first")
    report = cfg.f(*CHECK_REPORT)
    if report.is_file():
        bound = read_report(report)
        if (bound["delivery"].get("sha256"), bound.get("edl_sha256")) != (
            sha256(found["talk.mp4"]),
            sha256(found["edl.json"]),
        ):
            raise RuntimeError(f"{report} checked another edit: run the check stage again")
        later = cfg.f(*PARTIAL_REPORT)
        if later.is_file() and later.stat().st_mtime_ns > report.stat().st_mtime_ns:
            partial = read_report(later)
            same = (partial["delivery"].get("sha256"), partial.get("edl_sha256")) == (
                bound["delivery"].get("sha256"),
                bound.get("edl_sha256"),
            )
            if same and partial.get("status") in ("failed", "not_measured"):
                raise RuntimeError(
                    f"{later}, newer than {report.name}, says {partial['status']} for this edit: run the check "
                    "stage with all four gates again"
                )
        found["check.json"] = report
    return found


def read_report(path):
    """The check report at path, or a RuntimeError saying it is not one."""
    try:
        bound = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise RuntimeError(f"{path} is not a readable check report ({error}): run the check stage again") from None
    shape = isinstance(bound, dict) and bound.get("kind") == "condense_check"
    shape = shape and isinstance(bound.get("delivery"), dict) and isinstance(bound.get("gates"), dict)
    shape = shape and all(isinstance(gate, dict) for gate in bound["gates"].values())
    shape = shape and all(isinstance(bound.get(k), bool) for k in ("passed", "complete"))
    if not shape or bound.get("status", "passed") not in STATUSES:
        raise RuntimeError(f"{path} is not a condense check report: run the check stage again")
    return bound


def check_summary(files, digests):
    """The manifest's check entry: the report's sha256, which gates ran and passed, and its summary numbers."""
    if "check.json" not in files:
        return {"status": "not_run"}
    report = read_report(files["check.json"])
    status = report.get("status") or ("failed" if not report["passed"] else "passed")
    if status == "passed" and not report["complete"]:
        status = "partial"  # a report that ran some gates only never says passed
    return {
        "status": status,
        "file": "check.json",
        "sha256": digests["check.json"],
        "complete": report["complete"],
        "gates": {name: bool(gate.get("passed")) for name, gate in report["gates"].items()},
        "summary": report.get("summary"),
    }


def stream(path):
    """Sample rate and channels of the first audio stream."""
    out = run(
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=sample_rate,channels",
        "-of",
        "json",
        path,
    ).stdout
    s = json.loads(out)["streams"][0]
    return int(s["sample_rate"]), int(s["channels"])


def manifest(cfg, run_id, final, files, edl):
    checked = timeline.validate(files["edl.json"])
    rate, channels = stream(files["talk.mp4"])
    digests = {name: sha256(path) for name, path in files.items()}
    version = run("ffmpeg", "-hide_banner", "-version").stdout.splitlines()[0]
    return {
        "schema_version": 1,
        "kind": "condense_edit",
        "status": "rendered_unreviewed",
        "run_id": run_id,
        "run_dir": str(final),
        "sources": [{"clip": c["name"], "path": c["file"], "sha256": sha256(c["file"])} for c in cfg.clips],
        "output_sha256": digests,
        "timeline": {
            "mapping": "edl_v1",
            "no_time_stretch": False,
            "edl": {"file": "edl.json", "sha256": digests["edl.json"]},
            "fps": edl["fps"],
            "total_frames": checked["total_frames"],
            "source_axis": "per-clip analysis seconds from the first decoded audio sample; source = analysis + shift",
            "output_axis": "delivered frame index / fps",
            "clips": [{"name": c["name"], "shift_seconds": c["shift"]} for c in edl["clips"]],
        },
        "delivery": {
            "file": "talk.mp4",
            "audio_sample_rate": rate,
            "audio_channels": channels,
            "video_frames": audio.frames(files["talk.mp4"]),
        },
        "check": check_summary(files, digests),
        "tools": {"ffmpeg": version, "video_utils_timeline": checked["schema_version"]},
    }


def verify(verifier, run_dir):
    """(accepted, the end of its receipt): verify-run's verdict, 0 or 1. Raise when it gave none."""
    try:
        p = subprocess.run(
            [verifier, "verify-run", "--timeline", "edl_v1", str(run_dir)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"verify-run ran over {TIMEOUT_S:g} s (CONDENSE_TOOL_TIMEOUT_S)") from None
    except OSError as error:
        raise RuntimeError(f"verify-run could not start: {error}") from None
    if p.returncode not in (0, 1):  # 2 is a usage error; anything else is a crash, not a verdict
        raise RuntimeError(f"verify-run exited {p.returncode}: {p.stderr.strip()[-2000:]}")
    return p.returncode == 0, (p.stdout.strip() or p.stderr.strip())[-2000:]


def publish(cfg, root=None):
    verifier = timeline.binary()  # before any staging: no binary means no run at all
    root = Path(root or ARTIFACTS)
    root.mkdir(parents=True, exist_ok=True)
    files = outputs(cfg)
    edl = json.loads(files["edl.json"].read_text())
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:12]
    final, staging = root / run_id, root / f".staging-{run_id}"
    staging.mkdir()
    try:
        for name, path in files.items():
            shutil.copy2(path, staging / name)
        record = manifest(cfg, run_id, final.resolve(), {n: staging / n for n in files}, edl)
        (staging / "manifest.json").write_text(json.dumps(record, indent=2) + "\n")
        staging.rename(final)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    try:
        accepted, receipt = verify(verifier, final)
    except RuntimeError as error:
        marker = root / f".unverified-{run_id}"
        marker.write_text(f"{run_id}: verify-run gave no verdict: {error}\n")
        raise RuntimeError(f"{run_id} is unverified, not refused; it keeps its name ({marker.name}): {error}") from None
    if not accepted:
        final.rename(root / f".failed-{run_id}")
        raise RuntimeError(f"verify-run refused {run_id}; kept as .failed-{run_id}: {receipt}")
    check = record["check"]["status"]
    print(f"{final}: {len(files)} files, {record['timeline']['total_frames']} frames, check {check}, verified")
    return final
