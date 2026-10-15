"""Old/new parity: run two condense tool roots on one talk.toml and compare what they write, by sha256.

    python3 -m condense.tools.parity OLD_ROOT NEW_ROOT talk.toml RUN_DIR [--stages transcribe,events,edl]

A tool root holds `talk_condense/` (the retired tool) or `condense/` (this repository). Each side runs in its
own RUN_DIR/<side>/ with a copy of talk.toml and hard links to the same recordings, so both read identical
inputs and the same `[encode] jobs` and `[whisper] threads` bounds. The sides run one after the other.
`publish` runs only where the tool has it, and its `verify-run` refuses a symlinked recording.

The receipt (RUN_DIR/parity.json, and stdout) holds hashes, counts, durations, stage exit codes and tool
versions. It names no path, host or transcript text: files appear by their name inside work/ or out/.
A mismatch is reported, never tuned away. The exit code is 0 when every compared file matches.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

SIDES = ("old", "new")
STAGES = ("transcribe", "events", "edl", "render", "captions", "overlay", "publish")
DEFAULT_STAGES = ("transcribe", "events", "edl")
MEDIA = (".mp4", ".mkv", ".mov")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def package(root):
    """The importable package of a tool root: condense (this repository) or talk_condense (the retired tool)."""
    for name in ("condense", "talk_condense"):
        if (Path(root) / name / "__main__.py").is_file():
            return name
    raise FileNotFoundError("a tool root holds condense/__main__.py or talk_condense/__main__.py")


def stage_supported(root, stage):
    """publish exists only in this repository's condense."""
    return (Path(root) / package(root) / f"{stage}.py").is_file()


def stage_config(config, side_dir):
    """Copy talk.toml into side_dir and link every recording it names, so relative paths resolve the same."""
    config = Path(config).resolve()
    raw = tomllib.loads(config.read_text())
    for key in ("work", "out"):
        value = Path(raw.get(key, "work" if key == "work" else "out/talk.mp4"))
        if value.is_absolute() or ".." in value.parts:
            raise ValueError(f"talk.toml {key} must be a relative path inside its directory, so the sides stay apart")
    side_dir.mkdir(parents=True, exist_ok=True)
    for clip in raw["clip"]:
        rel = Path(clip["file"])
        if rel.is_absolute():
            continue
        link = side_dir / rel
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink() or link.exists():
            link.unlink()
        target = (config.parent / rel).resolve()
        try:  # verify-run refuses a symlinked source, so publish needs a regular file: a hard link
            os.link(target, link)
        except OSError:  # another filesystem: the stages up to overlay still run on a symlink
            link.symlink_to(target)
    shutil.copyfile(config, side_dir / "talk.toml")
    return side_dir / "talk.toml"


def run_side(root, config, stages, logs):
    """Run each stage with `python3 -m <package> <stage> talk.toml`. Stop at the first failure."""
    root = Path(root).resolve()
    env = os.environ | {"PYTHONPATH": str(root)}
    logs.mkdir(parents=True, exist_ok=True)
    done = []
    for stage in stages:
        if not stage_supported(root, stage):
            done.append(dict(stage=stage, status="unsupported"))
            continue
        start = time.monotonic()
        with open(logs / f"{stage}.log", "w") as log:
            p = subprocess.run(
                [sys.executable, "-m", package(root), stage, str(config)],
                cwd=root,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        done.append(dict(stage=stage, status="ok" if p.returncode == 0 else "failed", exit=p.returncode))
        done[-1]["wall_s"] = round(time.monotonic() - start, 1)
        if p.returncode:
            break
    return done


def probe(path):
    """Decoded video frames, the container duration and the audio stream duration of one media file."""
    args = ["ffprobe", "-v", "error", "-count_frames", "-show_entries"]
    args += ["stream=codec_type,nb_read_frames,duration:format=duration", "-of", "json", str(path)]
    d = json.loads(subprocess.run(args, capture_output=True, text=True, check=True).stdout)
    video = next((s for s in d["streams"] if s["codec_type"] == "video"), {})
    sound = next((s for s in d["streams"] if s["codec_type"] == "audio"), {})
    out = dict(duration_s=round(float(d["format"]["duration"]), 6))
    if "nb_read_frames" in video:
        out["video_frames"] = int(video["nb_read_frames"])
    if "duration" in sound:
        out["audio_duration_s"] = round(float(sound["duration"]), 6)
    return out


def shape(path):
    """Counts that say where two JSON files part: list lengths and the lengths of a dict's list values."""
    try:
        data = json.loads(Path(path).read_text(errors="replace"))
    except ValueError:
        return {}
    if isinstance(data, list):
        return {"items": len(data)}
    if not isinstance(data, dict):
        return {}
    out = {k: len(v) for k, v in data.items() if isinstance(v, list)}
    if isinstance(data.get("clips"), list):  # edl.json
        out["segments"] = [len(c.get("segments", [])) for c in data["clips"] if isinstance(c, dict)]
        out["expected_total_s"] = data.get("expected_total_s")
    return out


def first_diff(a, b):
    """The first index where two JSON lists, or one key's lists, differ. None when they agree."""
    try:
        x, y = json.loads(Path(a).read_text(errors="replace")), json.loads(Path(b).read_text(errors="replace"))
    except ValueError:
        return None
    if isinstance(x, dict) and isinstance(y, dict):
        for key in sorted(set(x) | set(y)):
            if x.get(key) != y.get(key):
                at = first_diff_list(x.get(key), y.get(key))
                return {"key": key} | ({"index": at} if at is not None else {})
        return None
    at = first_diff_list(x, y)
    return None if at is None else {"index": at}


def first_diff_list(x, y):
    if not (isinstance(x, list) and isinstance(y, list)):
        return None
    for i, (p, q) in enumerate(zip(x, y, strict=False)):
        if p != q:
            return i
    return min(len(x), len(y)) if len(x) != len(y) else None


def collect(side_dir):
    """name -> path for every file the receipt compares: work/*.json, work/*.rms.txt and every out/ file."""
    raw = tomllib.loads((side_dir / "talk.toml").read_text())
    work = side_dir / raw.get("work", "work")
    out = (side_dir / raw.get("out", "out/talk.mp4")).parent
    found = {}
    if work.is_dir():
        for p in sorted([*work.glob("*.json"), *work.glob("*.rms.txt")]):
            found[f"work/{p.name}"] = p
    if out.is_dir():
        for p in sorted(out.iterdir()):
            if p.is_file():
                found[f"out/{p.name}"] = p
    return found


def describe(path):
    d = dict(sha256=sha256(path), bytes=path.stat().st_size)
    if path.suffix in MEDIA:
        d |= probe(path)
    elif path.suffix == ".json":
        d |= {"shape": shape(path)}
    return d


def compare(old_dir, new_dir):
    """Per-file verdicts and a summary for two side directories."""
    a, b = collect(old_dir), collect(new_dir)
    files = {}
    for name in sorted(set(a) | set(b)):
        if name not in b:
            files[name] = dict(verdict="only_old", old=describe(a[name]))
            continue
        if name not in a:
            files[name] = dict(verdict="only_new", new=describe(b[name]))
            continue
        x, y = describe(a[name]), describe(b[name])
        row = dict(verdict="match" if x["sha256"] == y["sha256"] else "differ", old=x, new=y)
        if row["verdict"] == "differ" and name.endswith(".json"):
            row["first_diff"] = first_diff(a[name], b[name])
        if "video_frames" in x or "video_frames" in y:
            same = x.get("video_frames") == y.get("video_frames") and x.get("duration_s") == y.get("duration_s")
            row["frames_and_duration"] = "match" if same else "differ"
        files[name] = row
    counts = {}
    for row in files.values():
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    return dict(files=files, counts=counts, identical=bool(files) and set(counts) == {"match"})


def version(args, pattern, stream="stdout"):
    """The first match of pattern in a tool's output, or "unknown"."""
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    m = re.search(pattern, p.stdout + p.stderr if stream == "both" else getattr(p, stream))
    return m.group(1) if m else "unknown"


def commit(root):
    try:
        p = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return p.stdout.strip() or "unknown"


def versions(roots):
    model = os.environ.get("WHISPER_MODEL")
    out = dict(
        ffmpeg=version(["ffmpeg", "-version"], r"ffmpeg version (\S+)"),
        # whisper-cli has no --version; its backend line names the package it was built from.
        whisper_cpp=version(["whisper-cli", "--help"], r"whisper-cpp-(\d+(?:\.\d+)+)", "both"),
        python=".".join(map(str, sys.version_info[:3])),
        whisper_model_sha256=sha256(model) if model and Path(model).is_file() else "unknown",
    )
    out |= {f"{side}_commit": commit(root) for side, root in roots.items()}
    out |= {f"{side}_package": package(root) for side, root in roots.items()}
    return out


def sources(config):
    """clip name -> sha256 of its recording."""
    config = Path(config).resolve()
    raw = tomllib.loads(config.read_text())
    return {c["name"]: sha256(config.parent / c["file"]) for c in raw["clip"]}


def scrub(receipt, *private):
    """Refuse a receipt that carries any of the given strings (paths, host names)."""
    text = json.dumps(receipt)
    leaked = [p for p in private if p and p in text]
    if leaked:
        raise ValueError(f"the receipt carries {len(leaked)} private string(s); refusing to write it")
    return receipt


def main(argv=None):
    p = argparse.ArgumentParser(prog="condense.tools.parity", description=__doc__.split("\n")[0])
    p.add_argument("old_root")
    p.add_argument("new_root")
    p.add_argument("config", help="talk.toml; its recordings, work dir and outputs stay outside git")
    p.add_argument("run_dir", help="the sides run in RUN_DIR/old and RUN_DIR/new")
    p.add_argument("--stages", default=",".join(DEFAULT_STAGES), help=f"comma-separated, from {','.join(STAGES)}")
    p.add_argument("--sides", default="old,new", help="which sides to run; the comparison always reads both")
    p.add_argument("--compare-only", action="store_true", help="hash what the sides already wrote")
    a = p.parse_args(argv)
    stages = [s for s in a.stages.split(",") if s]
    unknown = set(stages) - set(STAGES)
    if unknown:
        p.error(f"unknown stages: {sorted(unknown)}")
    roots = {"old": Path(a.old_root).resolve(), "new": Path(a.new_root).resolve()}
    run_dir = Path(a.run_dir).resolve()
    runs = {}
    for side in SIDES:
        config = stage_config(a.config, run_dir / side)
        if not a.compare_only and side in a.sides.split(","):
            runs[side] = run_side(roots[side], config, stages, run_dir / side / "logs")
    receipt = dict(
        kind="condense_parity",
        stages=stages,
        versions=versions(roots),
        sources_sha256=sources(a.config),
        config_sha256=sha256(a.config),
        runs=runs,
        comparison=compare(run_dir / "old", run_dir / "new"),
    )
    private = [str(run_dir), *map(str, roots.values()), str(Path(a.config).resolve().parent), str(Path.home())]
    scrub(receipt, *private)
    text = json.dumps(receipt, indent=1, sort_keys=True)
    (run_dir / "parity.json").write_text(text + "\n")
    print(text)
    failed = any(s["status"] == "failed" for r in runs.values() for s in r)
    return 0 if receipt["comparison"]["identical"] and not failed else 1


if __name__ == "__main__":
    sys.exit(main())
