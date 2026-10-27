#!/usr/bin/env python3
"""A synthetic stand-in for the kitpip binary (docs/spec/NARRATED_VIDEO.md, lane L3). Standard library and FFmpeg.

It speaks kitpip's command shape as video-utils consumes it: `analyze RUN --fps N/D --out DIR`, `render PROSODY
--rig ID [--size PX] --out DIR`, `verify DIR` and `--version`. Every command prints one JSON line on stdout: a
result (exit 0), {"refused": code, "detail": ...} (exit 1) or {"error": ...} (exit 2). KITPIP_STUB_REFUSE=code
makes any command refuse with that code, so a test can draw each refusal on request.

It draws no character and holds no kitpip art. `render` writes a ProRes 4444 overlay (prores_ks, yuva444p10le) of
an opaque centred square on a fully transparent field, so every corner pixel is transparent, plus a
kitpip.manifest/v0 manifest. The pin for this file is narrate/tests/fixtures/narrated-video/kitpip-externals.json.
"""

import hashlib
import json
import math
import os
import platform
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

VERSION = "0.0.0-stub"
COMMIT = "0" * 40
RIGS = {"kitpip-stub-rig": {"revision": 0, "sha256": hashlib.sha256(b"kitpip-stub-rig").hexdigest()}}
CODES = (
    "no_consent",
    "not_synthetic",
    "digest_mismatch",
    "contract_invalid",
    "unsupported_audio",
    "inside_narration_run",
    "would_overwrite_input",
    "unlisted_file",
    "unknown_rig",
    "ffmpeg_missing",
)
DEFAULT_SIZE = 512


class Refused(Exception):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code, self.detail = code, detail


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def out_dir(path, inputs):
    out = Path(path).resolve()
    for source in inputs:
        source = Path(source).resolve()
        if out == source or source in out.parents:
            raise Refused(
                "inside_narration_run" if source.is_dir() else "would_overwrite_input",
                "the output directory is inside an input",
            )
    if out.exists() and any(out.iterdir()):
        raise Refused("would_overwrite_input", "the output directory is not empty")
    out.mkdir(parents=True, exist_ok=True)
    return out


def parse_fps(text):
    try:
        num, den = (int(x) for x in text.split("/"))
    except ValueError:
        raise Refused("contract_invalid", "fps is N/D") from None
    if num < 1 or den < 1:
        raise Refused("contract_invalid", "fps is positive")
    return {"num": num, "den": den}


def analyze(args):
    run = Path(args["input"]).resolve()
    out = out_dir(args["out"], [run])
    try:
        manifest = json.loads((run / "manifest.json").read_text())
    except (OSError, json.JSONDecodeError):
        raise Refused("contract_invalid", "no narrate manifest") from None
    if manifest.get("synthetic") is not True:
        raise Refused("not_synthetic", "the narration manifest is not synthetic")
    consent_ids = sorted({v["consent_id"] for v in manifest.get("voices", []) if v.get("consent_id")})
    if not consent_ids:
        raise Refused("no_consent", "the narration names no consent")
    wav = run / "narration.wav"
    if not wav.is_file() or sha_file(wav) != manifest.get("output_sha256", {}).get("narration.wav"):
        raise Refused("digest_mismatch", "narration.wav is not the manifest's")
    fps = parse_fps(args["fps"])
    try:
        with wave.open(str(wav), "rb") as stream:
            if stream.getsampwidth() != 2 or stream.getnchannels() != 1:
                raise Refused("unsupported_audio", "the stub reads 16-bit mono PCM")
            rate, pcm = stream.getframerate(), stream.readframes(stream.getnframes())
    except wave.Error:
        raise Refused("unsupported_audio", "narration.wav is not PCM WAV") from None
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    frames = max(1, math.floor(len(samples) * fps["num"] / (rate * fps["den"])))
    step = len(samples) / frames
    envelope = []
    for k in range(frames):
        chunk = samples[int(k * step) : int((k + 1) * step)] or (0,)
        envelope.append(round(math.sqrt(sum(s * s for s in chunk) / len(chunk)) / 32768, 4))
    prosody = {
        "schema": "kitpip.prosody/v0-stub",
        "fps": fps,
        "frames": frames,
        "narration_sha256": sha_file(wav),
        "run_id": manifest.get("run_id"),
        "content_sha256": manifest.get("content_sha256"),
        "consent_ids": consent_ids,
        "voice_ids": sorted({v["voice"] for v in manifest.get("voices", [])}),
        "envelope": envelope,
    }
    (out / "prosody.json").write_text(json.dumps(prosody, sort_keys=True) + "\n")
    return {"prosody": "prosody.json", "frames": frames}


def render(args):
    prosody_path = Path(args["input"]).resolve()
    out = out_dir(args["out"], [prosody_path])
    rig = args.get("rig") or "kitpip-stub-rig"
    if rig not in RIGS:
        raise Refused("unknown_rig", f"rig {rig} is not in the stub's catalogue")
    ffmpeg = shutil.which(os.environ.get("FFMPEG", "ffmpeg"))
    if ffmpeg is None:
        raise Refused("ffmpeg_missing", "no ffmpeg on PATH")
    prosody = json.loads(prosody_path.read_text())
    size = int(args.get("size") or DEFAULT_SIZE)
    if not 16 <= size <= 2048 or size % 4:
        raise Refused("contract_invalid", "size is 16 to 2048 and a multiple of 4")
    fps, frames = prosody["fps"], prosody["frames"]
    box = size // 2
    graph = (
        f"color=c=black@0.0:s={size}x{size}:r={fps['num']}/{fps['den']},format=yuva444p10le,"
        f"drawbox=x={size // 4}:y={size // 4}:w={box}:h={box}:color=0x40C0FF@1.0:t=fill:replace=1"
    )
    overlay = out / "overlay.mov"
    done = subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            graph,
            "-frames:v",
            str(frames),
            "-c:v",
            "prores_ks",
            "-profile:v",
            "4444",
            "-pix_fmt",
            "yuva444p10le",
            "-fflags",
            "+bitexact",
            "-flags:v",
            "+bitexact",
            "-an",
            str(overlay),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise Refused("contract_invalid", "ffmpeg could not write the overlay")
    shutil.copyfile(prosody_path, out / "prosody.json")
    frames_sha = hashlib.sha256(json.dumps([size, prosody["envelope"]]).encode()).hexdigest()
    (out / "frames.sha256").write_text(frames_sha + "\n")
    outputs = [
        {
            "file": name,
            "sha256": sha_file(out / name),
            "bytes": (out / name).stat().st_size,
            "codec": "prores_ks" if name == "overlay.mov" else None,
            "pix_fmt": "yuva444p10le" if name == "overlay.mov" else None,
        }
        for name in ("overlay.mov", "frames.sha256", "prosody.json")
    ]
    manifest = {
        "schema": "kitpip.manifest/v0",
        "kind": "avatar_overlay",
        "synthetic": True,
        "label": "AI persona",
        "consent_ids": prosody["consent_ids"],
        "voice_ids": prosody["voice_ids"],
        "voice_tempo": None,
        "status": "private_unaccepted",
        "lip_sync_acceptance": "pending_operator",
        "rig": {"id": rig} | RIGS[rig],
        "renderer": {"name": "kitpip-stub", "version": VERSION, "pipeline": "lavfi", "arch": platform.machine()},
        "rate": fps,
        "size": {"w": size, "h": size},
        "frames": frames,
        "frames_sha256": frames_sha,
        "inputs": [{"role": "narration", "sha256": prosody["narration_sha256"]}],
        "outputs": outputs,
        "timeline": {
            "mapping": "avatar_overlay_v1",
            "no_time_stretch": False,
            "clock": "narration_output",
            "base_sha256": None,
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return {"manifest": "manifest.json", "frames": frames}


def verify(args):
    directory = Path(args["input"])
    try:
        manifest = json.loads((directory / "manifest.json").read_text())
    except (OSError, json.JSONDecodeError):
        raise Refused("contract_invalid", "no kitpip manifest") from None
    if manifest.get("schema") != "kitpip.manifest/v0":
        raise Refused("contract_invalid", "not a kitpip.manifest/v0")
    listed = {o["file"]: o["sha256"] for o in manifest.get("outputs", [])}
    present = {p.name for p in directory.iterdir() if p.name != "manifest.json"}
    if present - set(listed):
        raise Refused("unlisted_file", ", ".join(sorted(present - set(listed))))
    for name, digest in listed.items():
        if not (directory / name).is_file() or sha_file(directory / name) != digest:
            raise Refused("digest_mismatch", f"{name} is not the manifest's")
    labelled = (
        manifest.get("synthetic") is True
        and manifest.get("label") == "AI persona"
        and bool(manifest.get("consent_ids"))
    )
    return {"labelled": labelled}


def parse(argv):
    if argv[:1] == ["--version"]:
        return "version", {}
    if not argv or argv[0] not in ("analyze", "render", "verify"):
        raise ValueError(
            "usage: kitpip_stub.py {analyze,render,verify} INPUT [--fps N/D] [--rig ID] [--size PX] "
            "[--out DIR] | --version"
        )
    command, rest = argv[0], argv[1:]
    args = {}
    while rest:
        head = rest.pop(0)
        if head.startswith("--"):
            if head in ("--allow-unlabelled-test", "--pipe"):
                raise ValueError(f"{head}: not supported by the stub")
            if not rest:
                raise ValueError(f"{head} needs a value")
            args[head[2:]] = rest.pop(0)
        elif "input" not in args:
            args["input"] = head
        else:
            raise ValueError(f"unexpected argument {head}")
    needs_out = command != "verify" and "out" not in args
    if "input" not in args or needs_out or (command == "analyze" and "fps" not in args):
        raise ValueError(f"{command}: missing INPUT, --out or --fps")
    return command, args


def main(argv):
    try:
        command, args = parse(argv)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    try:
        requested = os.environ.get("KITPIP_STUB_REFUSE")
        if requested:
            raise Refused(requested if requested in CODES else "contract_invalid", "refusal requested")
        if command == "version":
            result = {"version": VERSION, "commit": COMMIT}
        else:
            result = {"analyze": analyze, "render": render, "verify": verify}[command](args)
    except Refused as exc:
        print(json.dumps({"refused": exc.code, "detail": exc.detail}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
