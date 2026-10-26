#!/usr/bin/env python3
"""A fake audiocpp_cli for the tests: no model, no GPU. It reads --request-sequence and writes one 48 kHz mono
16-bit WAV per request (a tone whose pitch follows the seed and text, whose length follows the text) to --out-dir,
and prints the runtime's metric lines. FAKE_AUDIOCPP_LOG appends each argv as JSON; FAKE_AUDIOCPP_FAIL_AFTER=N
writes N WAVs and exits 1; FAKE_AUDIOCPP_HANG_AFTER=N writes N WAVs and sleeps until it is stopped."""

import hashlib
import json
import math
import os
import struct
import sys
import time
import wave
from pathlib import Path

RATE = 48000


def arg(argv, name):
    return argv[argv.index(name) + 1]


def tone(path, text, seed):
    pitch = 140 + int.from_bytes(hashlib.sha256(f"{seed}\0{text}".encode()).digest()[:2], "big") % 160
    count = round(max(0.4, 0.065 * len(text)) * RATE)
    step = 2 * math.pi * pitch / RATE
    frames = b"".join(
        struct.pack("<h", round(9000 * min(1.0, n / 480, (count - 1 - n) / 480) * math.sin(step * n)))
        for n in range(count)
    )
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames)


def main(argv):
    if os.environ.get("FAKE_AUDIOCPP_LOG"):
        with open(os.environ["FAKE_AUDIOCPP_LOG"], "a") as f:
            f.write(json.dumps(argv) + "\n")
    requests = json.loads(Path(arg(argv, "--request-sequence")).read_text())["requests"]
    out = Path(arg(argv, "--out-dir"))
    fail = int(os.environ.get("FAKE_AUDIOCPP_FAIL_AFTER", "-1"))
    hang = int(os.environ.get("FAKE_AUDIOCPP_HANG_AFTER", "-1"))
    print("model.load_ms=12.5", flush=True)
    for n, request in enumerate(requests):
        if n == fail:
            print("fake: failing", file=sys.stderr)
            return 1
        if n == hang:
            time.sleep(3600)
        for key in ("voice_ref", "audio"):
            if key in request and not Path(request[key]).is_file():
                print(f"fake: {key} missing", file=sys.stderr)
                return 1
        tone(out / f"{request['id']}.wav", request["text"], request["seed"])
        print(f"request.{request['id']}.wall_ms=7.0", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
