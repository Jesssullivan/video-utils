#!/usr/bin/env python3
"""Run one narrate bench arm as a host process on the GPU host, and record what it did.

Standard library only, Python 3.9 or later: the GPU host runs this file on its own interpreter and never imports
narrate. run-bench.sh calls it once per arm inside the window's systemd scope; nothing here takes a Lease, and
nothing here opens a device node. Plan: docs/agent-notes/2026-10-22-narrate-bench-plan.md.

    host_run.py verify JOB --cache FILE [--arm A ...]      hash every input the arms read; no GPU use
    host_run.py run JOB --arm A --out DIR --cache FILE [--deadline EPOCH]
    host_run.py vram [--json]                              one reading of the amdgpu card's VRAM in use
    host_run.py summarize --out DIR ...                    the window receipt, DIR/receipt.json (run-bench.sh)

The JOB file (narrate/bench/host-job.json) names the chunk list, the private voice registry file and, per arm, the
runtime, its binary and model files and their sha256 values. `${NAME}` in any string is read from the environment
(`${NAME:-x}` falls back to x), so the tracked job carries no host path and no voice; a variable without a value or
default is refused. The voice registry (voices_file, hash-bound like every input) maps voice ids to a reference
clip and its verified transcript; it never enters git. Every input must declare a sha256; a missing or different
value is refused before any process starts. The verify cache keys each file by size, mtime, ctime and inode, and a
file whose key changed is hashed again.

An arm's optional reference policy (`reference`: cut, max_seconds, min_seconds, encoder) is checked by verify, before
any engine starts: `cut` names a time-aligned sub-clip of the voice's clip in the voices file (voices.<id>.cuts.<cut>,
wav and text hash-bound like the clip, source_sha256 the clip's sha256; narrate/bench/ref_cut.py makes them), and
the reference's duration from its WAV header and its encoder input (the clip resampled to encoder.rate, rounded up,
then padded to a multiple of encoder.pad_samples) must fit the policy. A misfit refuses the inputs (exit 2). An
audiocpp variant with prompt_audio also sends the reference as the request's `audio`, the continuation prompt that
its reference_text transcribes (VoxCPM2's ultimate clone). At audio.cpp 47c2756e VoxCPM2 builds the model's text as
prompt_text + target_text with no separator, so a prompt_audio variant's reference_text ends with one space; each
pass writes model-text.json beside requests.json, the text that reaches the model per request (prompt text plus the
chunk text with whitespace runs collapsed, as the pin's normalize_wrapper_text does, before any runtime text
chunking). Ming at the same pin tokenizes reference_text and the trimmed chunk text as separate pieces with no
separator; its model-text.json records that text and `reference_ends_bare`, true when the transcript ends on a
letter or digit. The request is left as it is, so a matched-cut arm keeps its native arm's variants. The run
receipt's `reference` names the conditioning reference (label, wav and text sha256, and the voice clip's sha256) so
a scorer can tell arms conditioned on different clips apart.

A matched-cut arm (`matched_cut_of`: another arm of the job) is that arm's control on a cut: load_job refuses it unless
its reference policy names a cut, the arm it names clones from the full clip, and the two have the same runtime,
inputs, settings and variants (decoys, budget and the about text may differ). Its receipt records `matched_cut_of`, so
a scorer can set the two side by side.

An arm runs, one synthesis process at a time: a one-chunk smoke per conditioning variant until one passes (exit
0, at least smoke_min_ratio of the chunk's expected duration, which catches a truncated take, and VRAM in use
rising at least vram.min_rise_bytes above the idle baseline, which catches a CPU fallback), the arm's decoy
renders, the full chunk list with seed 1, then seeds 2 and 3 while the arm's budget allows another pass of seed
1's length. Runtimes:

- qwentts: `qwen-tts --stream-by-line -o -` on an explicit --device; the model stays loaded, every stdin line is
  one chunk, and stdout carries one WAV per line, split here on qwen-tts's fixed 44-byte stream header.
- audiocpp: `audiocpp_cli --request-sequence`; one model load, <out-dir>/<id>.wav per chunk.
- command: an argv template run once per chunk ({binary} {text} {text_file} {out} {seed} {voice_wav}
  {voice_text_file}), for decoys and tests.

Engines run in their own process group with PR_SET_PDEATHSIG(SIGKILL), VK_DRIVER_FILES naming the RADV ICD only,
and never under root. Stop rules: the arm's wall budget (capped by --deadline), stall_s without output progress, a
non-zero exit, VRAM in use above vram.limit_bytes (at most 12,000,000,000; sampled every vram.poll_s from the
amdgpu card's sysfs mem_info_vram_used), an unreadable VRAM sample, any process of the scope holding a
/dev/dri/cardN node open, SIGTERM, SIGHUP or SIGINT. A stopped process group gets SIGTERM, then SIGKILL, and must
then be gone. After the arm, `journalctl -k -o cat` since its start is searched for an amdgpu reset or ring
timeout. Exit codes: 0 seed 1 completed; 10 the arm stopped (budget, stall, crash, no passing smoke, no GPU use,
unreadable VRAM); 20 the window must stop (VRAM over the limit, a card node open, a process group that survived its
kill, a GPU reset in the kernel log, or a signal); 2 refused (job, inputs or an existing output).

Outputs under DIR/<arm>/: one directory per pass with a WAV per chunk and, for a complete full pass, full.wav
(chunks joined with gap_s of silence); vram-trace.csv; receipt.json. Receipts name inputs by basename and sha256;
stderr tails have the home and bench directories replaced, but the outputs stay private (outside git).

Test mode (NARRATE_BENCH_TEST_MODE=1, recorded in every receipt) is the only way to point the sysfs root
(NARRATE_BENCH_DRM_ROOT) and the forbidden device prefix (NARRATE_BENCH_FORBIDDEN_DEV) somewhere else, or to lower
the minimum VRAM rise.
"""

import argparse
import ctypes
import datetime
import hashlib
import json
import os
import re
import signal
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

SCHEMA = "narrate-bench-host-job/1"
CHUNKS_SCHEMA = "narrate-bench-chunks/1"
EXIT_OK, EXIT_REFUSED, EXIT_ARM_STOP, EXIT_WINDOW_STOP = 0, 2, 10, 20
TEST_MODE = os.environ.get("NARRATE_BENCH_TEST_MODE") == "1"
DRM_ROOT = (TEST_MODE and os.environ.get("NARRATE_BENCH_DRM_ROOT")) or "/sys/class/drm"
FORBIDDEN_DEV = (TEST_MODE and os.environ.get("NARRATE_BENCH_FORBIDDEN_DEV")) or "/dev/dri/card"
VRAM_LIMIT_MAX = 12_000_000_000  # operator ruling 2026-10-23: peak VRAM under 12 GB
MIN_RISE_FLOOR = 64 << 20
VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
SHA256 = re.compile(r"[0-9a-f]{64}")
CARD = re.compile(r"card\d+")
GPU_RESET = re.compile(r"amdgpu.*(gpu reset|reset begin|ring \S+ timeout|gpu_recover|device lost|vram lost)", re.I)
QWENTTS_HEADER_MAGIC = (b"RIFF", b"WAVEfmt ")
RUNTIMES = ("qwentts", "audiocpp", "command")
WINDOW_RULES = ("vram", "card_open", "terminated", "group_survived", "gpu_reset")
TICK_S = 0.05
TERM_GRACE_S = 5.0
GONE_WAIT_S = 3.0
STDERR_TAIL = 4000
PR_SET_PDEATHSIG = 1

TERMINATED = threading.Event()
TRACKED_PGIDS = set()

try:
    _PRCTL = ctypes.CDLL(None, use_errno=True).prctl
except (OSError, AttributeError):
    _PRCTL = None


class Refusal(ValueError):
    """The job or an input is not what it declares; nothing ran."""


def say(message):
    """stderr that survives a closed ssh pipe."""
    try:
        print(message, file=sys.stderr, flush=True)
    except (BrokenPipeError, OSError):
        pass


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def expand(value, env, missing):
    if isinstance(value, str):

        def one(match):
            name, default = match.group(1), match.group(2)
            if env.get(name):
                return env[name]
            if default is not None:
                return default
            missing.add(name)
            return match.group(0)

        return VAR.sub(one, value)
    if isinstance(value, list):
        return [expand(v, env, missing) for v in value]
    if isinstance(value, dict):
        return {k: v if k == "about" else expand(v, env, missing) for k, v in value.items()}
    return value


def check_spec(label, spec):
    if not isinstance(spec, dict) or not spec.get("path"):
        raise Refusal(f"{label}: needs a path and a sha256")
    if not SHA256.fullmatch(str(spec.get("sha256") or "").lower()):
        raise Refusal(f"{label}: no declared sha256 (64 hex digits), got {spec.get('sha256')!r}")


def load_voices(job, env):
    """job["voices"] from the private registry file job["voices_file"], after its sha256 matches."""
    spec = job.get("voices_file")
    if spec is None:
        job.setdefault("voices", {})
        return
    check_spec("voices_file", spec)
    path = Path(spec["path"])
    try:
        measured = sha256_file(path)
    except OSError as error:
        raise Refusal(f"voices_file: {path.name} cannot be read: {error.strerror}") from error
    if measured != spec["sha256"].lower():
        raise Refusal(f"voices_file: {path.name} sha256 {measured} is not the declared {spec['sha256']}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise Refusal(f"voices_file: {path.name} is not JSON") from error
    missing = set()
    voices = expand(doc.get("voices", {}), env, missing)
    if missing:
        raise Refusal("voices_file needs these environment variables: " + ", ".join(sorted(missing)))
    for voice in voices.values():
        cuts = voice.get("cuts") if isinstance(voice, dict) else None
        entries = [voice] + (list(cuts.values()) if isinstance(cuts, dict) else [])
        for entry in entries:
            for part in ("wav", "text"):
                spec = entry.get(part) if isinstance(entry, dict) else None
                if isinstance(spec, dict) and spec.get("path") and not Path(spec["path"]).is_absolute():
                    spec["path"] = str(path.parent / spec["path"])
    job["voices"] = voices


def load_job(path, env=None):
    env = os.environ if env is None else env
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Refusal(f"job {Path(path).name}: {error}") from error
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise Refusal(f"job {Path(path).name}: schema must be {SCHEMA}")
    missing = set()
    job = expand(raw, env, missing)
    if missing:
        raise Refusal("job needs these environment variables: " + ", ".join(sorted(missing)))
    for key in ("chunks", "arms"):
        if key not in job:
            raise Refusal(f"job has no {key}")
    for name, arm in job["arms"].items():
        if arm.get("runtime") not in RUNTIMES:
            raise Refusal(f"arm {name}: runtime must be one of {', '.join(RUNTIMES)}")
        if not isinstance(arm.get("inputs"), dict) or "binary" not in arm["inputs"]:
            raise Refusal(f"arm {name}: inputs must name a binary")
        if not arm.get("variants"):
            raise Refusal(f"arm {name}: at least one conditioning variant")
        if arm.get("decoys") and arm["runtime"] != "audiocpp":
            raise Refusal(f"arm {name}: decoy renders are defined for the audiocpp runtime only")
        if arm["runtime"] == "qwentts" and not str(arm.get("settings", {}).get("device") or "").strip():
            raise Refusal(f"arm {name}: qwen-tts needs an explicit --device (settings.device), never a fallback")
        for variant in arm["variants"]:
            if variant.get("prompt_audio") and (
                arm["runtime"] != "audiocpp"
                or not variant.get("voice", True)
                or not variant.get("reference_text", True)
            ):
                raise Refusal(
                    f"arm {name} variant {variant.get('name')}: prompt_audio is the audiocpp runtime's continuation"
                    " prompt and needs the voice and its reference_text"
                )
        check_policy(name, arm.get("reference"))
    for name, arm in job["arms"].items():
        check_matched(name, arm, job["arms"])
    job.setdefault("seeds", [1, 2, 3])
    job.setdefault("gap_s", 0.25)
    job.setdefault("stall_s", 120.0)
    job.setdefault("smoke_min_ratio", 0.5)
    vram = job.setdefault("vram", {})
    vram["limit_bytes"] = min(int(vram.get("limit_bytes", VRAM_LIMIT_MAX)), VRAM_LIMIT_MAX)
    vram["required"] = True
    vram.setdefault("poll_s", 0.2)
    vram.setdefault("card", "")
    rise = int(vram.get("min_rise_bytes", 256 << 20))
    vram["min_rise_bytes"] = rise if TEST_MODE else max(rise, MIN_RISE_FLOOR)
    icd = job.get("vulkan_icd")
    if icd is not None and not Path(icd).is_file():
        raise Refusal(f"vulkan_icd {Path(icd).name} is not a file")
    load_voices(job, env)
    return job


def check_policy(name, policy):
    """An arm's reference policy: {cut?, max_seconds?, min_seconds?, encoder?: {rate, capacity_samples,
    pad_samples}}. Refuses a malformed one."""
    if policy is None:
        return
    if not isinstance(policy, dict):
        raise Refusal(f"arm {name}: reference must be an object")
    if "cut" in policy and not (isinstance(policy["cut"], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,40}", policy["cut"])):
        raise Refusal(f"arm {name}: reference.cut must be a short name")
    for key in ("max_seconds", "min_seconds"):
        value = policy.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0):
            raise Refusal(f"arm {name}: reference.{key} must be a positive number")
    if policy.get("min_seconds") and policy.get("max_seconds") and policy["min_seconds"] > policy["max_seconds"]:
        raise Refusal(f"arm {name}: reference.min_seconds is above max_seconds")
    encoder = policy.get("encoder")
    if encoder is not None:
        keys = ("rate", "capacity_samples", "pad_samples")
        if not isinstance(encoder, dict) or not all(
            isinstance(encoder.get(k), int) and not isinstance(encoder.get(k), bool) and encoder[k] > 0 for k in keys
        ):
            raise Refusal(f"arm {name}: reference.encoder needs positive integers rate, capacity_samples, pad_samples")


MATCHED_KEYS = ("runtime", "inputs", "settings", "variants")


def check_matched(name, arm, arms):
    """A matched-cut arm: the control of arm `matched_cut_of` on a reference cut, identical in everything that
    conditions the render except the reference. Refuses anything else."""
    native = arm.get("matched_cut_of")
    if native is None:
        return
    if not isinstance(native, str) or native == name or native not in arms:
        raise Refusal(f"arm {name}: matched_cut_of must name another arm of the job, got {native!r}")
    if not (arm.get("reference") or {}).get("cut"):
        raise Refusal(f"arm {name}: a matched-cut arm needs a reference policy that names a cut")
    other = arms[native]
    if (other.get("reference") or {}).get("cut") or other.get("matched_cut_of"):
        raise Refusal(f"arm {name}: matched_cut_of names {native}, which does not clone from the full clip")
    differ = [k for k in MATCHED_KEYS if canonical(arm.get(k)) != canonical(other.get(k))]
    if differ:
        raise Refusal(f"arm {name}: differs from {native} in {', '.join(differ)}; only the reference may differ")


def voice_of(job):
    """(voice id, {"wav": input, "text": input}) of the job's cloning voice, or (None, None)."""
    vid = job.get("voice") or ""
    if not vid:
        return None, None
    voice = job.get("voices", {}).get(vid)
    if not voice or "wav" not in voice or "text" not in voice:
        raise Refusal("the selected voice is not in the voices file with a wav and a text")
    return vid, voice


def clones(arm):
    return any(v.get("voice", True) for v in arm["variants"])


def reference_of(job, arm_name):
    """(label prefix, {"wav", "text"}) of the reference an arm clones from: the voice's clip, or the cut its
    reference policy names (a time-aligned sub-clip of the same consented clip, private voices file)."""
    vid, voice = voice_of(job)
    if vid is None:
        raise Refusal("an arm clones a voice but the job names none (voice)")
    cut = (job["arms"][arm_name].get("reference") or {}).get("cut")
    if not cut:
        return "voice", voice
    entry = (voice.get("cuts") or {}).get(cut)
    if not isinstance(entry, dict) or "wav" not in entry or "text" not in entry:
        raise Refusal(f"arm {arm_name}: the selected voice has no reference cut {cut!r} in the voices file")
    source = str(entry.get("source_sha256") or "").lower()
    if source != str(voice["wav"].get("sha256") or "").lower():
        raise Refusal(f"arm {arm_name}: reference cut {cut!r} does not name the voice clip's sha256 as its source")
    return f"voice.{cut}", entry


def inputs_of(job, arms):
    """{label: {"path", "sha256"}} of everything the named arms read."""
    out = {"chunks": job["chunks"]}
    if job.get("voices_file"):
        out["voices_file"] = job["voices_file"]
    for arm in arms:
        if clones(job["arms"][arm]):
            prefix, ref = reference_of(job, arm)
            out[f"{prefix}.wav"], out[f"{prefix}.text"] = ref["wav"], ref["text"]
    for arm in arms:
        for key, spec in job["arms"][arm]["inputs"].items():
            out[f"{arm}.{key}"] = spec
    return out


def file_key(st):
    return {"bytes": st.st_size, "mtime_ns": st.st_mtime_ns, "ctime_ns": st.st_ctime_ns, "ino": st.st_ino}


def verify(job, arms, cache_path):
    """Check every input's sha256, hashing again any file whose size, mtime, ctime or inode changed since the
    cache recorded it. Returns the records."""
    cache_path = Path(cache_path)
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    records, problems = {}, []
    for label, spec in sorted(inputs_of(job, arms).items()):
        try:
            check_spec(label, spec)
        except Refusal as error:
            problems.append(str(error))
            continue
        declared = spec["sha256"].lower()
        path = Path(spec["path"])
        try:
            st = path.stat()
        except OSError:
            problems.append(f"{label}: {path.name} is missing")
            continue
        if not path.is_file():
            problems.append(f"{label}: {path.name} is not a file")
            continue
        key = file_key(st)
        seen = cache.get(str(path))
        if seen and all(seen.get(k) == v for k, v in key.items()):
            measured, rehashed = seen["sha256"], False
        else:
            measured, rehashed = sha256_file(path), True
        if measured != declared:
            problems.append(f"{label}: {path.name} sha256 {measured} is not the declared {declared}")
            continue
        cache[str(path)] = dict(key, sha256=measured)
        records[label] = {"file": path.name, "sha256": measured, "bytes": st.st_size, "rehashed": rehashed}
    if not problems:
        for arm in arms:
            policy = job["arms"][arm].get("reference")
            if policy and clones(job["arms"][arm]):
                check = check_reference(job, arm, policy)
                records[f"{arm}.reference"] = check
                problems += check.pop("problems")
    if problems:
        raise Refusal("inputs refused:\n  " + "\n  ".join(problems))
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_name(cache_path.name + ".tmp")
    tmp.write_text(json.dumps(cache, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(cache_path)
    return records


def check_reference(job, arm_name, policy):
    """The reference an arm clones from against its policy: duration from the WAV header, and the encoder's padded
    input length (the clip resampled to encoder.rate, rounded up as soxr's exact-length output is, then padded up
    to a multiple of encoder.pad_samples) against encoder.capacity_samples. Runs before any engine starts."""
    prefix, ref = reference_of(job, arm_name)
    path = Path(ref["wav"]["path"])
    out = {"reference": prefix, "file": path.name, "policy": policy, "problems": []}
    try:
        info = wav_info(path.read_bytes())
    except (OSError, ValueError) as error:
        out["problems"].append(f"{arm_name}: reference {path.name} is not a readable WAV ({error})")
        return out
    frames = info["data"][1] // info["block"]
    seconds = frames / info["rate"]
    out.update(rate=info["rate"], channels=info["channels"], frames=frames, seconds=round(seconds, 4))
    lasts = f"{arm_name}: reference {path.name} lasts {seconds:.2f} s"
    if policy.get("max_seconds") and seconds > policy["max_seconds"]:
        out["problems"].append(f"{lasts}, over the arm's max_seconds {policy['max_seconds']}")
    if policy.get("min_seconds") and seconds < policy["min_seconds"]:
        out["problems"].append(f"{lasts}, under the arm's min_seconds {policy['min_seconds']}")
    encoder = policy.get("encoder")
    if encoder:
        resampled = -(-frames * encoder["rate"] // info["rate"])
        padded = -(-resampled // encoder["pad_samples"]) * encoder["pad_samples"]
        out["encoder"] = {"resampled_samples": resampled, "padded_samples": padded, **encoder}
        if padded > encoder["capacity_samples"]:
            out["problems"].append(
                f"{arm_name}: reference {path.name} needs {padded} encoder samples at {encoder['rate']} Hz, over the"
                f" capacity {encoder['capacity_samples']}"
            )
    out["fits"] = not out["problems"]
    return out


def load_chunks(path):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("schema") != CHUNKS_SCHEMA or not doc.get("chunks"):
        raise Refusal(f"chunk list must be {CHUNKS_SCHEMA} with chunks")
    digest = hashlib.sha256(canonical(doc["chunks"]).encode("utf-8")).hexdigest()
    if digest != doc.get("chunks_sha256"):
        raise Refusal(f"chunk list content sha256 {digest} is not its declared chunks_sha256")
    for chunk in doc["chunks"]:
        if "\n" in chunk["text"] or not chunk["text"].strip():
            raise Refusal(f"chunk {chunk['id']}: one non-empty line of text")
    return doc


# --- WAV --------------------------------------------------------------------------------------------------------


def wav_info(data):
    """{"fmt": raw fmt chunk bytes, "channels", "rate", "bits", "block", "data": (offset, length)} of RIFF bytes.
    A streamed header's placeholder sizes are clipped to the bytes present."""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a RIFF WAVE file")
    pos, fmt, found = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos : pos + 4], struct.unpack("<I", data[pos + 4 : pos + 8])[0]
        body = pos + 8
        if cid == b"fmt ":
            fmt = data[body : body + size]
        elif cid == b"data":
            found = (body, min(size, len(data) - body))
            break
        pos = body + size + (size & 1)
    if fmt is None or found is None or len(fmt) < 16:
        raise ValueError("WAV without a fmt and a data chunk")
    _tag, channels, rate, _byte_rate, block, bits = struct.unpack("<HHIIHH", fmt[:16])
    if not channels or not rate or not block:
        raise ValueError("WAV fmt has a zero channel count, rate or block size")
    return {"fmt": fmt, "channels": channels, "rate": rate, "bits": bits, "block": block, "data": found}


def wav_seconds(path):
    info = wav_info(Path(path).read_bytes())
    return info["data"][1] // info["block"] / info["rate"]


def wav_bytes(fmt, pcm):
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + (b"\0" if len(fmt) & 1 else b"")
    body += b"data" + struct.pack("<I", len(pcm)) + pcm + (b"\0" if len(pcm) & 1 else b"")
    return b"RIFF" + struct.pack("<I", len(body)) + body


def concat_wavs(paths, out, gap_s):
    """Join chunk WAVs of one format with gap_s of silence between them. Returns seconds."""
    infos = [(p, wav_info(Path(p).read_bytes())) for p in paths]
    first = infos[0][1]
    for p, info in infos[1:]:
        if info["fmt"] != first["fmt"]:
            raise ValueError(f"{Path(p).name} has a different WAV format from {Path(infos[0][0]).name}")
    gap = b"\0" * (round(gap_s * first["rate"]) * first["block"])
    parts = []
    for i, (p, info) in enumerate(infos):
        start, length = info["data"]
        raw = Path(p).read_bytes()[start : start + length]
        parts.append(raw[: len(raw) - len(raw) % first["block"]])
        if i + 1 < len(infos):
            parts.append(gap)
    pcm = b"".join(parts)
    Path(out).write_bytes(wav_bytes(first["fmt"], pcm))
    return len(pcm) // first["block"] / first["rate"]


def split_stream(data, markers):
    """(fmt, first header time, [(pcm bytes, end time)]) of qwen-tts's --stream-by-line output. markers:
    [(cumulative bytes, time)] of each stdout read. A WAV begins at every copy of the stream's own first 44-byte
    header that lands on the sample grid (qwen-tts writes the same header before each line)."""
    if len(data) < 44 or data[:4] != QWENTTS_HEADER_MAGIC[0] or data[8:16] != QWENTTS_HEADER_MAGIC[1]:
        return None, None, []
    header = data[:44]
    fmt = header[20:36]
    block = struct.unpack("<H", fmt[12:14])[0] or 2
    starts, pos = [0], 44
    while True:
        found = data.find(header, pos)
        if found < 0:
            break
        if (found - starts[-1] - 44) % block == 0:
            starts.append(found)
        pos = found + 1

    def arrival(offset):
        for cumulative, t in markers:
            if cumulative >= offset:
                return t
        return markers[-1][1] if markers else None

    segments = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(data)
        pcm = data[start + 44 : end]
        pcm = pcm[: len(pcm) - len(pcm) % block]
        done = arrival(starts[i + 1] + 44) if i + 1 < len(starts) else (markers[-1][1] if markers else None)
        segments.append((pcm, done))
    return fmt, arrival(44), segments


# --- VRAM and the device-node guard -----------------------------------------------------------------------------


def find_card(root=None, name=""):
    """(card name, mem_info_vram_used path) of the amdgpu card with the most VRAM, read from sysfs only. A device
    node under /dev is never opened."""
    root = Path(root or DRM_ROOT)
    best = None
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return None, None
    for entry in entries:
        if not CARD.fullmatch(entry) or (name and entry != name):
            continue
        device = root / entry / "device"
        try:
            driver = os.path.basename(os.path.realpath(device / "driver"))
            used = device / "mem_info_vram_used"
            total = int((device / "mem_info_vram_total").read_text().strip())
        except (OSError, ValueError):
            continue
        if driver == "amdgpu" and used.is_file() and (best is None or total > best[0]):
            best = (total, entry, used)
    return (best[1], best[2]) if best else (None, None)


def read_vram(path):
    try:
        return int(Path(path).read_text().strip())
    except (OSError, ValueError):
        return None


def own_cgroup_procs():
    """The cgroup.procs file of this process's cgroup (the window scope in production)."""
    try:
        line = next(x for x in Path("/proc/self/cgroup").read_text().splitlines() if x.startswith("0::"))
    except (OSError, StopIteration):
        return None
    return Path("/sys/fs/cgroup" + line[3:]) / "cgroup.procs"


def descendants(pid):
    """pid and every process below it, from /proc/<pid>/task/<tid>/children."""
    out, todo = [], [pid]
    while todo:
        current = todo.pop()
        out.append(current)
        try:
            tasks = os.listdir(f"/proc/{current}/task")
        except OSError:
            continue
        for tid in tasks:
            try:
                todo += [int(c) for c in Path(f"/proc/{current}/task/{tid}/children").read_text().split()]
            except (OSError, ValueError):
                continue
    return out


def scope_pids():
    """Pids to guard: every process of the window scope in production; in test mode (no scope), the engines this
    runner started and everything below them."""
    if not TEST_MODE:
        procs = own_cgroup_procs()
        try:
            return [int(p) for p in procs.read_text().split()] if procs else []
        except OSError:
            return []
    return [pid for leader in list(TRACKED_PGIDS) for pid in descendants(leader)]


def card_holders():
    """[(pid, target)] of open file descriptors on a card node (FORBIDDEN_DEV followed by digits)."""
    pattern = re.compile(re.escape(FORBIDDEN_DEV) + r"\d+$")
    found = []
    for pid in scope_pids():
        fd_dir = f"/proc/{pid}/fd"
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(f"{fd_dir}/{fd}")
            except OSError:
                continue
            if pattern.match(target):
                found.append((pid, target))
    return found


class VramMonitor(threading.Thread):
    """Samples VRAM in use every poll_s and checks the scope for open card nodes. Sets over (above the limit),
    unreadable (a failed sample) or card_open."""

    def __init__(self, path, poll_s, limit_bytes):
        super().__init__(daemon=True)
        self.path, self.poll_s, self.limit = path, float(poll_s), int(limit_bytes)
        self.over, self.unreadable, self.card_open = threading.Event(), threading.Event(), threading.Event()
        self.halt = threading.Event()
        self.peak, self.pass_peak, self.samples, self.errors, self.over_value = None, None, 0, 0, None
        self.card_detail = None
        self.trace = []
        self.t0 = time.monotonic()

    def begin_pass(self):
        self.pass_peak = None

    def run(self):
        while not self.halt.is_set():
            value = read_vram(self.path)
            if value is None:
                self.errors += 1
                self.unreadable.set()
            else:
                self.samples += 1
                self.trace.append((round(time.monotonic() - self.t0, 3), value))
                self.peak = value if self.peak is None else max(self.peak, value)
                self.pass_peak = value if self.pass_peak is None else max(self.pass_peak, value)
                if value > self.limit and not self.over.is_set():
                    self.over_value = value
                    self.over.set()
            holders = card_holders()
            if holders and not self.card_open.is_set():
                self.card_detail = [{"pid": pid, "node": target} for pid, target in holders]
                self.card_open.set()
            self.halt.wait(self.poll_s)

    def stop(self):
        self.halt.set()
        self.join(timeout=5)


def baseline(path, seconds=1.0, poll_s=0.1):
    values = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = read_vram(path)
        if value is not None:
            values.append(value)
        time.sleep(poll_s)
    return min(values) if values else None


# --- processes --------------------------------------------------------------------------------------------------


def _child_setup():
    """In the engine, before exec: die with the runner (PR_SET_PDEATHSIG, SIGKILL)."""
    if _PRCTL is not None:
        _PRCTL(PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0)


def group_alive(pgid):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def reap_group(proc):
    """Stop the engine's whole process group (SIGTERM, then SIGKILL) and wait for it to be gone. True when no
    member is left."""
    pgid = proc.pid
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if proc.poll() is None or group_alive(pgid):
            try:
                os.killpg(pgid, sig)
            except ProcessLookupError:
                pass
        try:
            proc.wait(timeout=TERM_GRACE_S)
        except subprocess.TimeoutExpired:
            continue
        end = time.monotonic() + (TERM_GRACE_S if sig == signal.SIGTERM else GONE_WAIT_S)
        while group_alive(pgid) and time.monotonic() < end:
            time.sleep(TICK_S)
        if not group_alive(pgid):
            break
    gone = proc.poll() is not None and not group_alive(pgid)
    if gone:
        TRACKED_PGIDS.discard(pgid)
    return gone


def supervise(proc, progress, deadline, stall_s, monitor):
    """Wait for proc; stop it on the first rule that fires. Returns (rule, group gone) where rule is "exit",
    "terminated", "vram", "card_open", "vram_unreadable", "budget" or "stall". The process group is always
    reaped, whatever happens here."""
    rule = None
    try:
        last, last_t = progress(), time.monotonic()
        while True:
            if proc.poll() is not None:
                rule = "exit"
                break
            now = time.monotonic()
            if TERMINATED.is_set():
                rule = "terminated"
            elif monitor is not None and monitor.over.is_set():
                rule = "vram"
            elif monitor is not None and monitor.card_open.is_set():
                rule = "card_open"
            elif monitor is not None and monitor.unreadable.is_set():
                rule = "vram_unreadable"
            elif now >= deadline:
                rule = "budget"
            else:
                value = progress()
                if value != last:
                    last, last_t = value, now
                elif now - last_t >= stall_s:
                    rule = "stall"
            if rule:
                break
            time.sleep(TICK_S)
    finally:
        gone = reap_group(proc)
    if rule == "exit" and monitor is not None:
        for event, name in ((monitor.over, "vram"), (monitor.card_open, "card_open")):
            if event.is_set():
                rule = name
    return rule or "terminated", gone


def redact(text):
    for value, label in ((os.environ.get("NARRATE_BENCH_ROOT", ""), "<bench>"), (str(Path.home()), "~")):
        if value and len(value) > 1:
            text = text.replace(value, label)
    return text


def tail(path, limit=STDERR_TAIL):
    try:
        data = Path(path).read_bytes()
    except OSError:
        return ""
    return redact(data[-limit:].decode("utf-8", "replace"))


def engine_env(job):
    env = dict(os.environ)
    icd = job.get("vulkan_icd")
    if icd:
        env["VK_DRIVER_FILES"] = env["VK_ICD_FILENAMES"] = str(icd)
    return env


def popen(argv, pass_dir, env, stdin=None, stdout_file=None):
    err = open(pass_dir / "stderr.log", "wb")
    out = open(stdout_file, "wb") if stdout_file else subprocess.PIPE
    try:
        proc = subprocess.Popen(
            [str(a) for a in argv],
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            start_new_session=True,
            preexec_fn=_child_setup,
            cwd=str(pass_dir),
            env=env,
        )
    finally:
        err.close()
        if stdout_file:
            out.close()
    TRACKED_PGIDS.add(proc.pid)
    return proc


# --- runtimes ---------------------------------------------------------------------------------------------------


class Ctx:
    """What a pass needs: the job, the arm, resolved inputs, the voice and the stop machinery."""

    def __init__(self, job, arm_name, deadline, monitor):
        self.job, self.name, self.arm = job, arm_name, job["arms"][arm_name]
        self.deadline, self.monitor = deadline, monitor
        self.inputs = {k: v["path"] for k, v in self.arm["inputs"].items()}
        vid, voice = voice_of(job)
        self.voice_id = vid
        self.reference = None
        if voice is not None and clones(self.arm):
            clip_sha256 = str(voice["wav"].get("sha256") or "").lower()
            label, voice = reference_of(job, arm_name)
            self.reference = {
                "label": label,
                "wav_sha256": str(voice["wav"].get("sha256") or "").lower(),
                "text_sha256": str(voice["text"].get("sha256") or "").lower(),
                "voice_clip_sha256": clip_sha256,
            }
        self.voice_wav = voice["wav"]["path"] if voice else None
        self.voice_text_file = voice["text"]["path"] if voice else None
        self.voice_text = (
            " ".join(Path(self.voice_text_file).read_text(encoding="utf-8").split()) if self.voice_text_file else ""
        )
        self.settings = self.arm.get("settings", {})
        self.stall_s = float(self.arm.get("stall_s", job["stall_s"]))
        self.env = engine_env(job)


def file_id(chunk_id):
    return re.sub(r"[^A-Za-z0-9_-]", "_", chunk_id)


def run_qwentts(ctx, chunks, seed, variant, pass_dir):
    s = ctx.settings
    argv = [ctx.inputs["binary"], "--model", ctx.inputs["model"], "--codec", ctx.inputs["codec"]]
    argv += ["--device", s["device"], "--lang", s.get("lang", "English"), "--format", "wav16", "--seed", seed]
    argv += ["--stream-by-line", "-o", "-"]
    if variant.get("voice", True):
        argv += ["--ref-wav", ctx.voice_wav]
        if variant.get("reference_text", True):
            argv += ["--ref-text", ctx.voice_text_file]
    argv += list(s.get("extra_args", [])) + list(variant.get("extra_args", []))
    started = time.monotonic()
    proc = popen(argv, pass_dir, ctx.env, stdin=True)
    markers, total = [], [0]
    with open(pass_dir / "stream.raw", "wb") as stream:

        def pump():
            fd = proc.stdout.fileno()
            while True:
                try:
                    block = os.read(fd, 1 << 16)
                except OSError:
                    break
                if not block:
                    break
                stream.write(block)
                total[0] += len(block)
                markers.append((total[0], time.monotonic()))

        reader = threading.Thread(target=pump, daemon=True)
        reader.start()
        try:
            proc.stdin.write("".join(c["text"] + "\n" for c in chunks).encode("utf-8"))
            proc.stdin.close()
        except OSError:
            pass
        rule, gone = supervise(proc, lambda: total[0], ctx.deadline, ctx.stall_s, ctx.monitor)
        reader.join(timeout=5)
        proc.stdout.close()
    ended = time.monotonic()
    data = (pass_dir / "stream.raw").read_bytes()
    fmt, header_t, segments = split_stream(data, markers)
    results, previous = [], header_t
    clean = rule == "exit" and proc.returncode == 0
    for i, chunk in enumerate(chunks):
        if i >= len(segments):
            break
        pcm, done = segments[i]
        if i == len(segments) - 1 and not clean:
            break  # the stream was cut inside this chunk, or before the next header proved it whole
        path = pass_dir / f"{file_id(chunk['id'])}.wav"
        path.write_bytes(wav_bytes(fmt, pcm))
        results.append({"chunk": chunk, "file": path, "wall_s": (done - previous) if previous and done else None})
        previous = done
    (pass_dir / "stream.raw").unlink()
    load_s = (header_t - started) if header_t else None
    return rule, gone, proc.returncode, results, load_s, ended - started


MODEL_TEXT_RULES = {
    "voxcpm2": "audio.cpp 47c2756e VoxCPM2: prompt_text + normalize_wrapper_text(text) with prompt audio",
    "ming3_tts": (
        "audio.cpp 47c2756e Ming (src/models/ming3_tts/prompt.cpp:99,111): reference_text with a reference, then"
        " trim_ascii_whitespace(text); each is tokenized as its own piece, with no separator between them"
    ),
}


def wrapper_text(text):
    """audio.cpp 47c2756e VoxCPM2 normalize_wrapper_text: every run of C-locale whitespace becomes one space."""
    return re.sub(r"[ \t\n\v\f\r]+", " ", text)


def composed_text(family, request):
    """The text that reaches the model for one request at the pin; None when the family's rule is not known."""
    if family == "voxcpm2":
        prompt = request.get("reference_text", "") if "audio" in request else ""
        return prompt + wrapper_text(request["text"])
    if family == "ming3_tts":
        prompt = request.get("reference_text", "") if "voice_ref" in request else ""
        return prompt + request["text"].strip(" \t\n\v\f\r")
    return None


def run_audiocpp(ctx, chunks, seed, variant, pass_dir, decoy=None):
    s = ctx.settings
    task = (decoy or {}).get("task") or s.get("task", "clon")
    requests, model_text = [], {}
    for chunk in chunks:
        request = {"id": file_id(chunk["id"]), "text": chunk["text"], "seed": seed}
        options = dict(s.get("options", {}))
        options.update(variant.get("options", {}))
        if decoy is not None:
            options = dict(decoy.get("options", {}))
        elif variant.get("voice", True):
            request["voice_ref"] = str(ctx.voice_wav)
            if variant.get("reference_text", True):
                request["reference_text"] = ctx.voice_text
            if variant.get("prompt_audio"):
                request["audio"] = str(ctx.voice_wav)  # the continuation prompt the reference_text transcribes
                # the pin concatenates prompt_text + target_text with no separator: keep the last prompt word and
                # the chunk's first word apart
                request["reference_text"] = ctx.voice_text + " "
        if options:
            request["options"] = options
        requests.append(request)
        model_text[request["id"]] = composed_text(s["family"], request)
    (pass_dir / "requests.json").write_text(json.dumps({"requests": requests}, indent=1), encoding="utf-8")
    record = {"family": s["family"], "composed_as": MODEL_TEXT_RULES.get(s["family"]), "texts": model_text}
    if s["family"] == "ming3_tts":
        # a transcript that ends on a letter or digit runs straight into the chunk's first word
        ending = {r.get("reference_text", "")[-1:] for r in requests if r.get("reference_text")}
        record["reference_ends_bare"] = any(c.isalnum() for c in ending) if ending else None
    (pass_dir / "model-text.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    out_dir = pass_dir / "out"
    out_dir.mkdir(exist_ok=True)
    argv = [ctx.inputs["binary"], "--task", task, "--family", s["family"], "--model", ctx.inputs["model"]]
    argv += ["--backend", s.get("backend", "vulkan"), "--device", str(s.get("device", 0))]
    argv += ["--request-sequence", pass_dir / "requests.json", "--out-dir", out_dir, "--out-format", "pcm16"]
    argv += ["--metrics"] + list(s.get("extra_args", [])) + list(variant.get("extra_args", []))
    started = time.monotonic()
    proc = popen(argv, pass_dir, ctx.env, stdout_file=pass_dir / "stdout.log")
    appeared = {}

    def progress():
        for chunk in chunks:
            fid = file_id(chunk["id"])
            if fid not in appeared and (out_dir / f"{fid}.wav").is_file():
                appeared[fid] = time.monotonic()
        return len(appeared)

    rule, gone = supervise(proc, progress, ctx.deadline, ctx.stall_s, ctx.monitor)
    progress()
    ended = time.monotonic()
    stdout = (pass_dir / "stdout.log").read_text(encoding="utf-8", errors="replace")
    walls = {m.group(1): float(m.group(2)) / 1000 for m in re.finditer(r"request\.(\S+)\.wall_ms[ =]([\d.]+)", stdout)}
    results = []
    clean = rule == "exit" and proc.returncode == 0
    for i, chunk in enumerate(chunks):
        fid = file_id(chunk["id"])
        source = out_dir / f"{fid}.wav"
        if fid not in appeared:
            break
        if not clean and i == len(appeared) - 1 and fid not in walls:
            break  # possibly still being written when the process was stopped
        path = pass_dir / f"{fid}.wav"
        source.replace(path)
        results.append({"chunk": chunk, "file": path, "wall_s": walls.get(fid), "wall_source": "runtime"})
    load_s = None
    if results and results[0]["wall_s"] is not None:
        first = appeared[file_id(chunks[0]["id"])]
        load_s = max(0.0, first - started - results[0]["wall_s"])
    return rule, gone, proc.returncode, results, load_s, ended - started


def run_command(ctx, chunks, seed, variant, pass_dir):
    template = list(ctx.settings.get("argv", []))
    if not template:
        raise Refusal(f"arm {ctx.name}: the command runtime needs settings.argv")
    results, started, rule, gone, code = [], time.monotonic(), "exit", True, 0
    for chunk in chunks:
        if TERMINATED.is_set():
            rule = "terminated"
            break
        fid = file_id(chunk["id"])
        text_file = pass_dir / f"{fid}.txt"
        text_file.write_text(chunk["text"] + "\n", encoding="utf-8")
        out = pass_dir / f"{fid}.wav"
        values = {
            "binary": ctx.inputs["binary"],
            "text": chunk["text"],
            "text_file": text_file,
            "out": out,
            "seed": seed,
            "voice_wav": ctx.voice_wav or "",
            "voice_text_file": ctx.voice_text_file or "",
        }
        argv = [str(part).format(**values) for part in template]
        t0 = time.monotonic()
        proc = popen(argv, pass_dir, ctx.env, stdout_file=pass_dir / "stdout.log")

        def progress(out=out):
            sizes = [out, pass_dir / "stdout.log", pass_dir / "stderr.log"]
            return tuple(p.stat().st_size if p.exists() else -1 for p in sizes)

        rule, gone = supervise(proc, progress, ctx.deadline, ctx.stall_s, ctx.monitor)
        code = proc.returncode
        if rule != "exit" or code != 0 or not gone or not out.is_file():
            break
        results.append({"chunk": chunk, "file": out, "wall_s": time.monotonic() - t0, "wall_source": "process"})
    return rule, gone, code, results, None, time.monotonic() - started


RUNNERS = {"qwentts": run_qwentts, "audiocpp": run_audiocpp, "command": run_command}


def run_pass(ctx, name, chunks, seed, variant, out_root, decoy=None):
    record = {
        "name": name,
        "seed": seed,
        "variant": variant.get("name"),
        "chunks_total": len(chunks),
        "chunk_ids": [c["id"] for c in chunks],
        "started_utc": utc_now(),
    }
    if TERMINATED.is_set():
        record.update(outcome="terminated", exit_code=None, complete=False, chunks_done=0, chunks=[])
        record.update(group_gone=True, process_wall_s=0.0, load_s=None, stderr_tail="", ended_utc=utc_now())
        return record
    pass_dir = out_root / name
    pass_dir.mkdir(parents=True, exist_ok=False)
    if ctx.monitor is not None:
        ctx.monitor.begin_pass()
    runner = RUNNERS[ctx.arm["runtime"]]
    if decoy is not None:
        rule, gone, code, results, load_s, wall = runner(ctx, chunks, seed, variant, pass_dir, decoy=decoy)
    else:
        rule, gone, code, results, load_s, wall = runner(ctx, chunks, seed, variant, pass_dir)
    if not gone:
        rule = "group_survived"
    rows = []
    for r in results:
        chunk = r["chunk"]
        try:
            seconds = wav_seconds(r["file"])
        except (OSError, ValueError) as error:
            rows.append({"chunk": chunk["id"], "file": r["file"].name, "error": str(error)})
            continue
        wall_s = r["wall_s"]
        rows.append(
            {
                "chunk": chunk["id"],
                "file": r["file"].name,
                "sha256": sha256_file(r["file"]),
                "audio_s": round(seconds, 3),
                "expected_s": chunk.get("expected_s"),
                "wall_s": round(wall_s, 3) if wall_s is not None else None,
                "wall_source": r.get("wall_source", "stream"),
                "rtf": round(wall_s / seconds, 4) if wall_s is not None and seconds > 0 else None,
            }
        )
    complete = rule == "exit" and code == 0 and len(rows) == len(chunks) and all("audio_s" in r for r in rows)
    record.update(
        {
            "ended_utc": utc_now(),
            "outcome": rule,
            "exit_code": code,
            "group_gone": gone,
            "complete": complete,
            "chunks_done": len([r for r in rows if "audio_s" in r]),
            "process_wall_s": round(wall, 3),
            "load_s": round(load_s, 3) if load_s is not None else None,
            "vram_peak_bytes": ctx.monitor.pass_peak if ctx.monitor is not None else None,
            "stderr_tail": tail(pass_dir / "stderr.log"),
            "chunks": rows,
        }
    )
    timed = [r for r in rows if r.get("wall_s") is not None]
    if timed:
        synth = sum(r["wall_s"] for r in timed)
        audio = sum(r["audio_s"] for r in timed)
        record["synth_wall_s"], record["audio_s"] = round(synth, 3), round(audio, 3)
        record["rtf"] = round(synth / audio, 4) if audio > 0 else None
    if complete and decoy is None and len(rows) > 1:
        seconds = concat_wavs([pass_dir / r["file"] for r in rows], pass_dir / "full.wav", ctx.job["gap_s"])
        record["full"] = {"file": "full.wav", "sha256": sha256_file(pass_dir / "full.wav"), "audio_s": seconds}
    return record


def journal(args, timeout=30):
    return subprocess.run(
        ["journalctl", "-k", "-q", "--no-pager", "-o", "cat"] + args, capture_output=True, text=True, timeout=timeout
    )


def kernel_log_probe():
    """None when the kernel log is readable, else the not_measured record."""
    try:
        done = journal(["-n", "1"], timeout=15)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"status": "not_measured", "reason": f"journalctl: {error}"}
    if done.returncode != 0:
        return {"status": "not_measured", "reason": redact(done.stderr.strip()[-300:]) or "journalctl -k failed"}
    return None


def kernel_log(since_epoch):
    """Messages (no host name: -o cat) of the kernel log since since_epoch that read as an amdgpu reset or ring
    timeout."""
    probe = kernel_log_probe()
    if probe is not None:
        return probe
    try:
        done = journal(["--since", f"@{int(since_epoch)}"])
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"status": "not_measured", "reason": f"journalctl: {error}"}
    if done.returncode != 0:
        return {"status": "not_measured", "reason": redact(done.stderr.strip()[-300:]) or "journalctl -k failed"}
    hits = [redact(line) for line in done.stdout.splitlines() if GPU_RESET.search(line)]
    return {"status": "measured", "gpu_reset_lines": hits[-20:]}


def run_arm(job, arm_name, out_dir, deadline_epoch=None, verified=None):
    arm = job["arms"][arm_name]
    out_root = Path(out_dir) / arm_name
    out_root.mkdir(parents=True, exist_ok=False)
    start_epoch, start = time.time(), time.monotonic()
    budget = float(arm.get("budget_s", 480))
    deadline = start + budget
    capped = False
    if deadline_epoch is not None and start + (deadline_epoch - start_epoch) < deadline:
        deadline, capped = start + (deadline_epoch - start_epoch), True
    vram_cfg = job["vram"]
    card, used_path = find_card(name=vram_cfg.get("card") or "")
    receipt = {
        "schema": "narrate-bench-host-receipt/1",
        "arm": arm_name,
        "runtime": arm["runtime"],
        "settings": arm.get("settings", {}),
        "test_mode": TEST_MODE,
        "started_utc": utc_now(),
        "budget_s": budget,
        "budget_capped_by_window": capped,
        "python": sys.version.split()[0],
        "runner_sha256": sha256_file(__file__),
        "vulkan_icd": Path(job["vulkan_icd"]).name if job.get("vulkan_icd") else None,
        "inputs": verified or {},
        "voice_selected": bool(job.get("voice")),
        "matched_cut_of": arm.get("matched_cut_of"),
        "passes": [],
        "stop": None,
        "authority": "R-HOOK-CONVERGENCE-20261004",
    }
    chunk_doc = load_chunks(job["chunks"]["path"])
    chunks = chunk_doc["chunks"]
    receipt["chunk_list"] = {"chunks_sha256": chunk_doc["chunks_sha256"], "count": len(chunks)}
    probe = kernel_log_probe()
    receipt["kernel_log_probe"] = probe or {"status": "readable"}
    if used_path is None:
        receipt["vram"] = {"status": "not_measured", "reason": "no amdgpu card with mem_info_vram_used in sysfs"}
        receipt["stop"] = {"rule": "no_vram_reading", "detail": receipt["vram"]["reason"]}
        return finish(receipt, out_root, EXIT_WINDOW_STOP, start_epoch)
    base = baseline(used_path)
    monitor = VramMonitor(used_path, vram_cfg["poll_s"], vram_cfg["limit_bytes"])
    monitor.start()
    receipt["vram"] = {"card": card, "limit_bytes": vram_cfg["limit_bytes"], "poll_s": vram_cfg["poll_s"]}
    receipt["vram"].update(baseline_bytes=base, min_rise_bytes=vram_cfg["min_rise_bytes"])
    ctx = Ctx(job, arm_name, deadline, monitor)
    receipt["reference"] = ctx.reference
    code = EXIT_ARM_STOP
    try:
        code = arm_passes(ctx, chunks, out_root, receipt, base)
    finally:
        monitor.stop()
        v = receipt["vram"]
        v.update({"peak_bytes": monitor.peak, "samples": monitor.samples, "read_errors": monitor.errors})
        if monitor.peak is not None and base is not None:
            v["peak_above_baseline_bytes"] = monitor.peak - base
        v["over_limit"] = monitor.over.is_set()
        v["card_node_open"] = monitor.card_detail
        with open(out_root / "vram-trace.csv", "w", encoding="utf-8") as f:
            f.write("t_s,vram_used_bytes\n")
            f.writelines(f"{t},{b}\n" for t, b in monitor.trace)
        v["trace"] = "vram-trace.csv"
    return finish(receipt, out_root, code, start_epoch)


def stop_code(rule):
    return EXIT_WINDOW_STOP if rule in WINDOW_RULES else EXIT_ARM_STOP


def halted(receipt, record, where):
    """A stop code when record's outcome ends the arm before its full passes, else None."""
    if record["outcome"] in WINDOW_RULES + ("budget", "vram_unreadable"):
        receipt["stop"] = {"rule": record["outcome"], "detail": where}
        return stop_code(record["outcome"])
    return None


def arm_passes(ctx, chunks, out_root, receipt, base):
    job, arm = ctx.job, ctx.arm
    seeds = [int(s) for s in job["seeds"]]
    receipt["first_seed"] = seeds[0]
    chosen = None
    for variant in arm["variants"]:
        smoke = run_pass(ctx, f"smoke-{variant['name']}", chunks[:1], seeds[0], variant, out_root)
        receipt["passes"].append(smoke)
        code = halted(receipt, smoke, f"during smoke {variant['name']}")
        if code is not None:
            return code
        row = smoke["chunks"][0] if smoke["chunks"] else {}
        expected = chunks[0].get("expected_s") or 0
        plausible = smoke["complete"] and row.get("audio_s", 0) >= float(job["smoke_min_ratio"]) * expected
        smoke["plausible"] = plausible
        if plausible:
            chosen = variant
            break
    if chosen is None:
        receipt["stop"] = {"rule": "smoke", "detail": "no conditioning variant passed its one-chunk smoke"}
        return EXIT_ARM_STOP
    rise = (smoke.get("vram_peak_bytes") or 0) - (base or 0)
    receipt["smoke_vram_rise_bytes"] = rise
    if rise < job["vram"]["min_rise_bytes"]:
        receipt["stop"] = {
            "rule": "no_gpu_use",
            "detail": f"VRAM in use rose {rise} bytes during the smoke, under {job['vram']['min_rise_bytes']}",
        }
        return EXIT_ARM_STOP
    receipt["variant"] = chosen["name"]
    by_id = {c["id"]: c for c in chunks}
    for decoy in arm.get("decoys", []):
        picked = [by_id[i] for i in decoy.get("chunks", []) if i in by_id]
        record = run_pass(ctx, f"decoy-{decoy['id']}", picked, seeds[0], {"name": decoy["id"]}, out_root, decoy)
        record["decoy"] = decoy["id"]
        receipt["passes"].append(record)
        code = halted(receipt, record, f"during decoy {decoy['id']}")
        if code is not None:
            return code
    for n, seed in enumerate(seeds):
        if n > 0:
            first = next(p for p in receipt["passes"] if p["name"] == f"seed{seeds[0]}")
            need = first["process_wall_s"] * 1.1
            if ctx.deadline - time.monotonic() < need:
                receipt["seeds_skipped"] = {"from_seed": seed, "reason": f"less than {need:.0f} s of budget left"}
                break
        record = run_pass(ctx, f"seed{seed}", chunks, seed, chosen, out_root)
        receipt["passes"].append(record)
        if not record["complete"]:
            rule = record["outcome"] if record["outcome"] != "exit" else "crash"
            receipt["stop"] = {"rule": rule, "detail": f"seed {seed}, exit code {record['exit_code']}"}
            if n == 0 or rule in WINDOW_RULES:
                return stop_code(rule)
            return EXIT_OK
    return EXIT_OK


def finish(receipt, out_root, code, start_epoch):
    log = kernel_log(start_epoch)
    receipt["kernel_log"] = log
    if log.get("gpu_reset_lines"):
        receipt["stop"] = {"rule": "gpu_reset", "detail": "amdgpu reset or ring timeout in the kernel log"}
        code = EXIT_WINDOW_STOP
    first = receipt.get("first_seed")
    receipt["seed1_complete"] = any(p["name"] == f"seed{first}" and p["complete"] for p in receipt["passes"])
    receipt["ended_utc"] = utc_now()
    receipt["exit_code"] = code
    (out_root / "receipt.json").write_text(json.dumps(receipt, indent=1, default=str) + "\n", encoding="utf-8")
    return code


def epoch_utc(seconds):
    return datetime.datetime.fromtimestamp(float(seconds), datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def summarize(out_dir, holder, started, ended, stop, exit_code, arm_results):
    """DIR/receipt.json: the window's facts, the measured scope and runner hashes, and one line per arm."""
    out_dir = Path(out_dir)
    arms = []
    for item in arm_results:
        name, _, result = item.partition("=")
        receipt = read_json(out_dir / name / "receipt.json") or {}
        passes = [
            {k: p.get(k) for k in ("name", "variant", "outcome", "complete", "chunks_done", "load_s", "rtf", "audio_s")}
            for p in receipt.get("passes", [])
        ]
        vram = receipt.get("vram", {})
        arms.append(
            {
                "arm": name,
                "result": result,
                "variant": receipt.get("variant"),
                "reference": (receipt.get("reference") or {}).get("label"),
                "matched_cut_of": receipt.get("matched_cut_of"),
                "seed1_complete": receipt.get("seed1_complete", False),
                "stop": receipt.get("stop"),
                "peak_vram_bytes": vram.get("peak_bytes"),
                "peak_above_baseline_bytes": vram.get("peak_above_baseline_bytes"),
                "kernel_log": (receipt.get("kernel_log") or {}).get("status"),
                "passes": passes,
            }
        )
    doc = {
        "schema": "narrate-bench-window-receipt/1",
        "holder": holder,
        "test_mode": TEST_MODE,
        "started_utc": epoch_utc(started),
        "ended_utc": epoch_utc(ended),
        "duration_s": round(float(ended) - float(started), 1),
        "stop": stop or None,
        "exit_code": int(exit_code),
        "runner": read_json(out_dir / "runner.json"),
        "scope": read_json(out_dir / "scope.json"),
        "leftover_pids_killed": (read_json(out_dir / "leftovers.json") or {}).get("pids", []),
        "inputs": (read_json(out_dir / "inputs.json") or {}).get("verified"),
        "vram_start": read_json(out_dir / "vram-start.json"),
        "vram_end": read_json(out_dir / "vram-end.json"),
        "arms": arms,
        "authority": "R-HOOK-CONVERGENCE-20261004",
    }
    tmp = out_dir / "receipt.json.tmp"
    tmp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    tmp.replace(out_dir / "receipt.json")
    return doc


def on_term(signum, _frame):
    TERMINATED.set()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run one narrate bench arm on the GPU host.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_verify = sub.add_parser("verify", help="hash every input the arms read; no GPU use")
    p_verify.add_argument("job")
    p_verify.add_argument("--cache", required=True, help="the verify cache file (outside any run directory)")
    p_verify.add_argument("--arm", action="append", default=[])
    p_run = sub.add_parser("run", help="run one arm")
    p_run.add_argument("job")
    p_run.add_argument("--out", required=True)
    p_run.add_argument("--cache", required=True)
    p_run.add_argument("--arm", required=True)
    p_run.add_argument("--deadline", type=float, help="window deadline, Unix seconds; caps the arm budget")
    p_vram = sub.add_parser("vram", help="one sysfs reading of the amdgpu card's VRAM in use")
    p_vram.add_argument("--json", action="store_true")
    p_vram.add_argument("--card", default="")
    p_sum = sub.add_parser("summarize", help="write the window receipt DIR/receipt.json")
    p_sum.add_argument("--out", required=True)
    p_sum.add_argument("--holder", required=True)
    p_sum.add_argument("--started", type=float, required=True)
    p_sum.add_argument("--ended", type=float, required=True)
    p_sum.add_argument("--stop", default="")
    p_sum.add_argument("--exit", type=int, required=True)
    p_sum.add_argument("--arm-result", action="append", default=[], help="ARM=exit code or not_started")
    args = parser.parse_args(argv)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, on_term)
    if args.command == "summarize":
        summarize(args.out, args.holder, args.started, args.ended, args.stop, args.exit, args.arm_result)
        return 0
    if args.command == "vram":
        card, path = find_card(name=args.card)
        value = read_vram(path) if path else None
        try:
            if args.json:
                print(json.dumps({"card": card, "vram_used_bytes": value, "utc": utc_now()}))
            else:
                print(f"{card or 'no amdgpu card'} {value if value is not None else 'unreadable'}")
        except BrokenPipeError:
            pass
        return 0 if value is not None else 3
    if os.geteuid() == 0:
        say("host_run: refused: never run as root")
        return EXIT_REFUSED
    try:
        job = load_job(args.job)
        arms = args.arm if args.command == "verify" else [args.arm]
        arms = arms or list(job["arms"])
        unknown = [a for a in arms if a not in job["arms"]]
        if unknown:
            raise Refusal(f"unknown arm {', '.join(unknown)}; the job has {', '.join(job['arms'])}")
        if args.command == "run" and (Path(args.out) / args.arm).exists():
            raise Refusal(f"{args.arm} already has an output directory in this run")
        verified = verify(job, arms, args.cache)
        load_chunks(job["chunks"]["path"])
    except Refusal as error:
        say(f"host_run: refused: {error}")
        return EXIT_REFUSED
    if TERMINATED.is_set():
        say("host_run: signalled during verify")
        return EXIT_WINDOW_STOP
    if args.command == "verify":
        try:
            print(json.dumps({"verified": verified}, indent=1))
        except BrokenPipeError:
            pass
        return EXIT_OK
    code = run_arm(job, args.arm, args.out, args.deadline, verified)
    say(f"host_run: {args.arm} exit {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
