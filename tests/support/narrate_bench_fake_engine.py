#!/usr/bin/env python3
"""A fake TTS binary for tests/test_narrate_bench_host.py: it speaks qwen-tts's and audiocpp_cli's command lines
closely enough for narrate/bench/host_run.py, and writes silent 16-bit mono WAVs. No model, GPU or network.

Behaviour comes from FAKE_* environment variables:
  FAKE_WORD_S     seconds of audio per word (default 0.01)
  FAKE_SLEEP_S    sleep before each chunk (default 0)
  FAKE_STALL_AT   1-based chunk index at which it stops producing output and sleeps (default: never)
  FAKE_VRAM_FILE  a fake sysfs mem_info_vram_used it writes FAKE_VRAM_BYTES into on start and FAKE_VRAM_IDLE into
                  on a normal exit
  FAKE_FORK       when "1", forks a helper that sleeps in the same process group (its pid goes to FAKE_LOG)
  FAKE_OPEN       a path it opens and holds (stands in for a card node in the device guard test)
  FAKE_EXIT       exit code after all chunks (default 0)
  FAKE_SHORT_REF_TEXT  when "1", a request with a reference transcript yields 0.05 s of audio (a truncated take)
  FAKE_LOG        a file every invocation appends its argv to, as one JSON line
"""

import json
import os
import struct
import sys
import time

RATE = 24000


def header(data_size=0x7FFFFFFF):
    fmt = struct.pack("<HHIIHH", 1, 1, RATE, RATE * 2, 2, 16)
    return (
        b"RIFF"
        + struct.pack("<I", 0x7FFFFFFF)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<I", 16)
        + fmt
        + b"data"
        + struct.pack("<I", data_size)
    )


def samples(text, short):
    seconds = 0.05 if short else max(0.05, len(text.split()) * float(os.environ.get("FAKE_WORD_S", "0.01")))
    return b"\x01\x00" * round(seconds * RATE)


def wav(pcm):
    return header(len(pcm))[:4] + struct.pack("<I", 36 + len(pcm)) + header(len(pcm))[8:] + pcm


def pace(index):
    stall = int(os.environ.get("FAKE_STALL_AT", "0") or 0)
    if stall and index >= stall:
        time.sleep(3600)
    time.sleep(float(os.environ.get("FAKE_SLEEP_S", "0")))


def arg(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None


def log(record):
    if os.environ.get("FAKE_LOG"):
        with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


def vram(value):
    """Replace the fake sysfs value atomically, as the kernel's attribute reads are."""
    if os.environ.get("FAKE_VRAM_FILE") and value:
        tmp = f"{os.environ['FAKE_VRAM_FILE']}.{os.getpid()}.tmp"
        with open(tmp, "w") as f:
            f.write(value + "\n")
        os.replace(tmp, os.environ["FAKE_VRAM_FILE"])


def main(argv):
    log({"argv": argv, "pid": os.getpid(), "pgid": os.getpgid(0), "env_vk": os.environ.get("VK_DRIVER_FILES")})
    vram(os.environ.get("FAKE_VRAM_BYTES", ""))
    time.sleep(float(os.environ.get("FAKE_HOLD_S", "0.2")))  # long enough for the VRAM sampler to see it
    if os.environ.get("FAKE_FORK") == "1":
        helper = os.fork()
        if helper == 0:
            time.sleep(3600)
            os._exit(0)
        log({"helper": helper})
    held = open(os.environ["FAKE_OPEN"], "rb") if os.environ.get("FAKE_OPEN") else None  # noqa: SIM115
    code = speak(argv)
    vram(os.environ.get("FAKE_VRAM_IDLE", ""))
    if held:
        held.close()
    return code


def speak(argv):
    short_ref = os.environ.get("FAKE_SHORT_REF_TEXT") == "1"
    if "--stream-by-line" in argv:  # qwen-tts
        out = sys.stdout.buffer
        out.write(header())
        out.flush()
        lines = [line.rstrip("\n") for line in sys.stdin if line.strip()]
        for i, line in enumerate(lines, 1):
            pace(i)
            if i > 1:
                out.write(header())
            pcm = samples(line, short_ref and "--ref-text" in argv)
            for start in range(0, len(pcm), 4800):
                out.write(pcm[start : start + 4800])
                out.flush()
        sys.stderr.write(f"[Pipeline] Streamed {len(lines)} lines to <stdout>\n")
    elif "--request-sequence" in argv:  # audiocpp_cli
        with open(arg(argv, "--request-sequence"), encoding="utf-8") as f:
            requests = json.load(f)["requests"]
        out_dir = arg(argv, "--out-dir")
        print(f"family={arg(argv, '--family')}\ntask={arg(argv, '--task')}", flush=True)
        for i, request in enumerate(requests, 1):
            t0 = time.monotonic()
            pace(i)
            pcm = samples(request["text"], short_ref and bool(request.get("reference_text")))
            tmp = os.path.join(out_dir, request["id"] + ".part")
            with open(tmp, "wb") as f:
                f.write(wav(pcm))
            os.replace(tmp, os.path.join(out_dir, request["id"] + ".wav"))
            wall_ms = (time.monotonic() - t0) * 1000
            print(f"request_id={request['id']}\n[TIMING] request.{request['id']}.wall_ms {wall_ms:.3f}", flush=True)
    else:  # command runtime: fake -w OUT -f TEXT_FILE
        with open(arg(argv, "-f"), encoding="utf-8") as f:
            text = f.read()
        pace(1)
        with open(arg(argv, "-w"), "wb") as f:
            f.write(wav(samples(text, False)))
    return int(os.environ.get("FAKE_EXIT", "0"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
