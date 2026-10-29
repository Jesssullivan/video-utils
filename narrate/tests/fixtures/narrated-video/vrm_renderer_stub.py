#!/usr/bin/env python3
"""A synthetic stand-in for the VRM offline renderer (docs/spec/NARRATED_VIDEO.md, "VRM external"). Standard library
only: no browser, no three.js, no GPU and no real .vrm.

It speaks the renderer's command shape as narrate/video/vrm.py consumes it:

  --version                                    one JSON line on stdout: {version, commit}
  render --vrm FILE --face FILE --size WxH     raw RGBA8 frames on stdout (straight alpha, rows top-down), one per
                                               face.json frame; the last stderr line is one JSON report, or
                                               {"refused": code, "detail": ...} with exit 1

It checks that the model is a binary glTF carrying VRMC_vrm or VRM, and that face.json is a face.timeline/v1 on the
narration_output clock. Each frame is a transparent field with an opaque square, two eye marks that close when the
frame's blink passes 0.5 and a mouth bar as tall as the frame's mouth weight. It draws no character and holds no model
art. Test knobs: VRM_STUB_REFUSE=code refuses with that code; VRM_STUB_EXTRA_FRAMES=n writes n frames too many;
VRM_STUB_NO_GPU=1 leaves the GPU out of the report. The pin for this file is
narrate/tests/fixtures/narrated-video/vrm-externals.json.
"""

import json
import os
import struct
import sys
from pathlib import Path

VERSION = "0.0.0-stub"
COMMIT = "0" * 40
CODES = ("vrm_invalid", "face_invalid", "contract_invalid", "unsupported_size")
CLEAR = bytes(4)
SKIN = bytes((0x40, 0xC0, 0xFF, 0xFF))
INK = bytes((0x10, 0x18, 0x20, 0xFF))


class Refused(Exception):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code, self.detail = code, detail


def check_model(path):
    try:
        data = Path(path).read_bytes()
    except OSError:
        raise Refused("vrm_invalid", "the model is not readable") from None
    if len(data) < 20 or data[:4] != b"glTF":
        raise Refused("vrm_invalid", "the model is not a binary glTF")
    _, _, _, length, kind = struct.unpack("<4sIIII", data[:20])
    if kind != 0x4E4F534A:
        raise Refused("vrm_invalid", "the model has no JSON chunk")
    try:
        document = json.loads(data[20 : 20 + length])
    except ValueError:
        raise Refused("vrm_invalid", "the model's JSON chunk does not parse") from None
    extensions = document.get("extensions") or {}
    if "VRMC_vrm" not in extensions and "VRM" not in extensions:
        raise Refused("vrm_invalid", "the model carries neither VRMC_vrm nor VRM")


def read_face(path):
    try:
        face = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Refused("face_invalid", "face.json does not parse") from None
    if face.get("schema") != "face.timeline/v1" or face.get("clock") != "narration_output":
        raise Refused("face_invalid", "face.json is not a face.timeline/v1 on the narration_output clock")
    if not isinstance(face.get("track"), list) or not face["track"]:
        raise Refused("face_invalid", "face.json has no frames")
    return face


def parse_size(text):
    try:
        w, h = (int(x) for x in text.split("x"))
    except ValueError:
        raise Refused("contract_invalid", "size is WxH") from None
    if w != h or not 16 <= w <= 2048 or w % 4:
        raise Refused("unsupported_size", "the stub draws squares 16 to 2048 px, a multiple of 4")
    return w


def draw(size, frame):
    """One RGBA frame: a transparent field, a square, two eye marks and a mouth bar."""
    lo, hi = size // 4, size - size // 4
    eye = max(1, size // 16)
    eyes_open = max(frame["blink"]) <= 0.5
    mouth_h = round(frame["mouth"]["weight"] * size // 8)
    mouth_top = hi - size // 8 - mouth_h
    rows = []
    for y in range(size):
        if not lo <= y < hi:
            rows.append(CLEAR * size)
            continue
        row = [CLEAR] * lo + [SKIN] * (hi - lo) + [CLEAR] * (size - hi)
        if eyes_open and lo + size // 8 <= y < lo + size // 8 + eye:
            for x in (lo + size // 8, hi - size // 8 - eye):
                row[x : x + eye] = [INK] * eye
        if mouth_h and mouth_top <= y < mouth_top + mouth_h:
            row[lo + size // 8 : hi - size // 8] = [INK] * (hi - lo - size // 4)
        rows.append(b"".join(row))
    return b"".join(rows)


def render(args):
    check_model(args["vrm"])
    face = read_face(args["face"])
    size = parse_size(args["size"])
    track = face["track"] + face["track"][-1:] * int(os.environ.get("VRM_STUB_EXTRA_FRAMES", "0") or 0)
    out = sys.stdout.buffer
    for frame in track:
        out.write(draw(size, frame))
    out.flush()
    report = {
        "frames": len(face["track"]),
        "step": "vrm.update(1/fps) per frame (stub: no model is stepped)",
        "renderer": {"name": "vrm-renderer-stub", "version": VERSION, "engine": {"kind": "stub"}},
    }
    if not os.environ.get("VRM_STUB_NO_GPU"):
        report["gpu"] = {"vendor": "none", "renderer": "stub-cpu", "driver": "none"}
    return report


def parse(argv):
    if argv[:1] == ["--version"]:
        return "version", {}
    if not argv or argv[0] != "render":
        raise ValueError("usage: vrm_renderer_stub.py render --vrm FILE --face FILE --size WxH | --version")
    args, rest = {}, argv[1:]
    while rest:
        head = rest.pop(0)
        if head in ("--badge", "--realtime"):
            raise ValueError(f"{head}: not supported by the stub")
        if not head.startswith("--") or not rest:
            raise ValueError(f"unexpected argument {head}")
        args[head[2:]] = rest.pop(0)
    if set(args) != {"vrm", "face", "size"}:
        raise ValueError("render needs --vrm, --face and --size")
    return "render", args


def main(argv):
    try:
        command, args = parse(argv)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    try:
        requested = os.environ.get("VRM_STUB_REFUSE")
        if requested:
            raise Refused(requested if requested in CODES else "contract_invalid", "refusal requested")
        if command == "version":
            print(json.dumps({"version": VERSION, "commit": COMMIT}, sort_keys=True))
            return 0
        report = render(args)
    except Refused as exc:
        print(json.dumps({"refused": exc.code, "detail": exc.detail}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
