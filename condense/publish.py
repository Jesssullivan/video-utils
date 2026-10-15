"""Publish one condensed talk as a hash-bound run under artifacts/condense/<run_id>/.

The manifest's timeline mapping is edl_v1 (docs/spec/TIMELINE_CONTRACT.md): output time maps to source time
through edl.json, so `no_time_stretch` is false and no guitar tool accepts the run. The run is staged, renamed
into place, then checked by `video-utils verify-run --timeline edl_v1`. A run that fails the check is renamed
to .failed-<run_id> and the stage exits 1.
"""

import hashlib
import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from . import audio, timeline
from .config import run

ARTIFACTS = timeline.ROOT / "artifacts" / "condense"


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
    return found


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
        "tools": {"ffmpeg": version, "video_utils_timeline": checked["schema_version"]},
    }


def publish(cfg, root=None):
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
        run(timeline.binary(), "verify-run", "--timeline", "edl_v1", final)
    except RuntimeError as refused:
        final.rename(root / f".failed-{run_id}")
        raise RuntimeError(f"verify-run refused {run_id}; kept as .failed-{run_id}: {refused}") from None
    print(f"{final}: {len(files)} files, {record['timeline']['total_frames']} frames, verified")
    return final
