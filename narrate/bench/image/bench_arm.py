#!/usr/bin/env python3
"""Run narrate bench arms from JSON job files and write WAVs plus a receipt per arm.

The GPU-host bench image's entrypoint (deploy/narrate-bench/README.md). The preregistration is
docs/agent-notes/2026-10-22-narrate-bench-plan.md; this file implements its window steps 3 and 4 for one pod:
an idle VRAM baseline, a 10 Hz sysfs sampler, then per arm: load, a one-chunk smoke, and the seeds in order,
one synthesis process at a time, under the per-arm budget, the 120 s stall rule and the window deadline.

  bench_arm.py run JOB.json [JOB.json ...]   hash-check every model file against sources.json, then run the
                                             arms in order and write <out_root>/<run_id>/...
  bench_arm.py check JOB.json [...]          validate jobs and their inputs; run nothing
  bench_arm.py versions                      print runtime binaries, their sha256 and the Vulkan devices
  bench_arm.py verify --root DIR             hash-check DIR/hf/<repo>/<revision>/ against sources.json
  bench_arm.py layout --weights W --dest D   CPU host: build the upload tree (hf/ and inputs/) for the volume
  bench_arm.py receive --root DIR            staging pod: wait for the upload marker, verify, receipt

The chunk list is the shared one (narrate/bench/chunks-v1.json, from narrate/bench/prepare.py), so the pod
and the host-process bench render the same chunks.

Runtimes: "qwentts" (qwentts.cpp tts-server on loopback: one load, then one HTTP request per chunk) and
"audiocpp" (audio.cpp CLI with --request-sequence: one load, then every request in one session).
Measured values are wall clock and WAV headers; nothing here scores audio. The receipt carries hashes, never
reference audio or its transcript.
"""

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

JOB_SCHEMA = "narrate-bench-job/1"
RECEIPT_SCHEMA = "narrate-bench-arm-receipt/1"
CHUNKS_SCHEMA = "narrate-bench-chunks/1"
MAX_THREADS = 8
DEFAULT_WINDOW_S = 25 * 60  # no arm runs past this; the pod deadline (30 min) leaves 5 min for collection
DEFAULT_BUDGET_S = 8 * 60
DEFAULT_STALL_S = 120
VRAM_SYSFS = "/sys/class/drm/renderD128/device/mem_info_vram_used"
ICD_ENV = {"radv": "NARRATE_ICD_RADV", "lavapipe": "NARRATE_ICD_LAVAPIPE"}
STOP_PATTERNS = (  # runtime log text that names a stop rule (plan, "Stop rules")
    ("device_lost", re.compile(r"VK_ERROR_DEVICE_LOST|ErrorDeviceLost|device lost|ring .* timeout", re.I)),
    ("oom", re.compile(r"ErrorOutOfDeviceMemory|VK_ERROR_OUT_OF_DEVICE_MEMORY|out of memory|failed to allocate", re.I)),
)


class JobError(Exception):
    pass


def utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def wav_info(path):
    """Sample rate, channels, bits and duration from a RIFF/WAVE header (PCM, float or extensible)."""
    with open(path, "rb") as f:
        head = f.read(12)
        if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            raise ValueError(f"{path}: not a RIFF/WAVE file")
        rate = channels = bits = None
        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            cid, size = hdr[:4], struct.unpack("<I", hdr[4:])[0]
            if cid == b"fmt ":
                fmt = f.read(size)
                _, channels, rate, _, _, bits = struct.unpack("<HHIIHH", fmt[:16])
            elif cid == b"data":
                if not (rate and channels and bits):
                    raise ValueError(f"{path}: data chunk before fmt chunk")
                if size in (0, 0xFFFFFFFF):  # streamed header: size the data from the file
                    size = os.path.getsize(path) - f.tell()
                frames = size // (channels * bits // 8)
                return {"sample_rate": rate, "channels": channels, "bits": bits, "duration_s": frames / rate}
            else:
                f.seek(size + (size & 1), 1)
    raise ValueError(f"{path}: no data chunk")


def dumps_canonical(doc):
    return json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------------------------- job checks

def _need(doc, key, kind, where):
    if key not in doc or not isinstance(doc[key], kind):
        raise JobError(f"{where}: '{key}' is required ({kind.__name__ if isinstance(kind, type) else kind})")
    return doc[key]


def _hash_matches(path, declared, label):
    if not re.fullmatch(r"[0-9a-f]{64}", str(declared or "")):
        raise JobError(f"{label}: a declared sha256 (64 lowercase hex) is required")
    if not Path(path).is_file():
        raise JobError(f"{label}: file not found")
    got = sha256_file(path)
    if got != declared:
        raise JobError(f"{label}: sha256 {got} does not match the declared {declared}")
    return got


def load_job(path):
    """Read and validate one job; return (job, resolved inputs). Raises JobError with the first problem."""
    raw = Path(path).read_bytes()
    try:
        job = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JobError(f"{path}: not JSON: {exc}") from None
    where = Path(path).name
    if job.get("schema") != JOB_SCHEMA:
        raise JobError(f"{where}: schema must be {JOB_SCHEMA}")
    arm = _need(job, "arm", str, where)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", arm):
        raise JobError(f"{where}: arm must be a short id")
    runtime = _need(job, "runtime", str, where)
    if runtime not in ("qwentts", "audiocpp"):
        raise JobError(f"{where}: runtime must be qwentts or audiocpp")
    threads = job.get("threads", MAX_THREADS)
    if not isinstance(threads, int) or not 1 <= threads <= MAX_THREADS:
        raise JobError(f"{where}: threads must be 1 to {MAX_THREADS}")
    backend = job.get("backend", "vulkan")
    if backend not in ("vulkan", "cpu"):
        raise JobError(f"{where}: backend must be vulkan or cpu")
    icd = job.get("vulkan_icd", "radv")
    if icd not in ("radv", "lavapipe", "system"):
        raise JobError(f"{where}: vulkan_icd must be radv, lavapipe or system")
    seeds = job.get("seeds", [1, 2, 3])
    if not seeds or not all(isinstance(s, int) and s >= 0 for s in seeds):
        raise JobError(f"{where}: seeds must be a non-empty list of non-negative integers")
    model = _need(job, "model", dict, where)
    files = ("talker", "codec") if runtime == "qwentts" else ("path",)
    for key in files:
        if not Path(_need(model, key, str, f"{where}: model")).exists():
            raise JobError(f"{where}: model.{key} not found")
    if runtime == "audiocpp":
        _need(model, "family", str, f"{where}: model")
    task = model.get("task", "clon")
    preset = job.get("preset_voice")
    reference = job.get("reference")
    inputs = {"job_sha256": hashlib.sha256(raw).hexdigest()}
    if preset is None:
        # Consent stop: a cloned render needs a reference with a consent id, both files hash-checked.
        if not isinstance(reference, dict):
            raise JobError(f"{where}: a cloned arm needs a reference (or preset_voice for the decoy)")
        for key in ("voice_id", "consent_id"):
            if not str(reference.get(key, "")).strip():
                raise JobError(f"{where}: reference.{key} is required (consent stop)")
        inputs["reference_wav"] = _hash_matches(_need(reference, "wav", str, where), reference.get("wav_sha256"),
                                                f"{where}: reference.wav")
        inputs["reference_text"] = _hash_matches(_need(reference, "text", str, where),
                                                 reference.get("text_sha256"), f"{where}: reference.text")
    elif runtime != "audiocpp" or not isinstance(preset, str) or task != "tts":
        raise JobError(f"{where}: preset_voice is an audio.cpp decoy and needs model.task 'tts'")
    chunks_path = _need(job, "chunks", str, where)
    inputs["chunks_sha256"] = _hash_matches(chunks_path, job.get("chunks_sha256"), f"{where}: chunks")
    doc = json.loads(Path(chunks_path).read_text(encoding="utf-8"))
    if doc.get("schema") != CHUNKS_SCHEMA or not doc.get("chunks"):
        raise JobError(f"{where}: chunks file is not a {CHUNKS_SCHEMA} list")
    chunks = doc["chunks"]
    limit = job.get("limit_chunks")
    if limit is not None:
        if not isinstance(limit, int) or limit < 1:
            raise JobError(f"{where}: limit_chunks must be a positive integer")
        chunks = chunks[:limit]
    inputs["chunks"] = chunks
    inputs["text_sha256"] = doc.get("text_sha256")
    for key in ("budget_s", "stall_s"):
        if key in job and (not isinstance(job[key], (int, float)) or job[key] <= 0):
            raise JobError(f"{where}: {key} must be a positive number of seconds")
    _need(job, "out_root", str, where)
    return job, inputs


# ---------------------------------------------------------------------------------------------- VRAM sampler

class VramSampler:
    """Polls the card's sysfs VRAM counter (ROCm tools are not in the image) and keeps every sample."""

    def __init__(self, path, hz=10.0):
        self.path, self.period = Path(path), 1.0 / hz
        self.samples, self._stop, self._thread, self.t0 = [], threading.Event(), None, time.monotonic()
        self.baseline_bytes = None

    @property
    def available(self):
        return self.path.is_file()

    def read(self):
        try:
            return int(self.path.read_text().strip())
        except (OSError, ValueError):
            return None

    def baseline(self, seconds=1.0):
        values = []
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            v = self.read()
            if v is not None:
                values.append(v)
            time.sleep(self.period)
        return sorted(values)[len(values) // 2] if values else None

    def _run(self):
        while not self._stop.is_set():
            v = self.read()
            if v is not None:
                self.samples.append((round(time.monotonic() - self.t0, 3), v))
            self._stop.wait(self.period)

    def start(self):
        if self.available:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self, csv_path):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        with open(csv_path, "w") as f:
            f.write("t_s,vram_used_bytes\n")
            f.writelines(f"{t},{v}\n" for t, v in self.samples)

    def peak_since(self, t_mark):
        values = [v for t, v in self.samples if t >= t_mark]
        return max(values) if values else None


# ---------------------------------------------------------------------------------------------- runtimes

def runtime_env(job):
    env = dict(os.environ)
    icd = job.get("vulkan_icd", "radv")
    if icd in ICD_ENV:
        files = os.environ.get(ICD_ENV[icd])
        if files:
            env["VK_DRIVER_FILES"] = files
            env.pop("VK_ICD_FILENAMES", None)
    if icd == "lavapipe":
        # ggml-vulkan skips CPU-type devices unless they are listed; lavapipe is the only device loaded.
        env["GGML_VK_VISIBLE_DEVICES"] = "0"
    threads = str(job.get("threads", MAX_THREADS))
    env.update({"OMP_NUM_THREADS": threads, "QWENTTS_CPU_THREADS": threads, "LP_NUM_THREADS": threads})
    env.setdefault("MESA_SHADER_CACHE_DIR", str(Path(job["out_root"]) / ".mesa-shader-cache"))
    return env


def binary(name):
    path = shutil.which(name)
    if not path:
        raise JobError(f"{name} is not on PATH")
    return path


def log_stop_reason(log_path):
    try:
        text = Path(log_path).read_text(errors="replace")
    except OSError:
        return None
    for reason, pattern in STOP_PATTERNS:
        m = pattern.search(text)
        if m:
            return reason, m.group(0)
    return None


def _terminate(proc, grace=10):
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def _record_chunk(arm_dir, wav, seed, chunk_id, wall_s, wall_source):
    info = wav_info(wav)
    return {"seed": seed, "id": chunk_id, "wav": str(Path(wav).relative_to(arm_dir)), "sha256": sha256_file(wav),
            "sample_rate": info["sample_rate"], "channels": info["channels"], "bits": info["bits"],
            "audio_s": round(info["duration_s"], 4), "wall_s": round(wall_s, 4) if wall_s is not None else None,
            "wall_source": wall_source,
            "rtf": round(wall_s / info["duration_s"], 4) if wall_s and info["duration_s"] > 0 else None}


def plan_requests(job, inputs):
    """(seed, id, text) in run order: the one-chunk smoke first, then every chunk for each seed."""
    chunks, seeds = inputs["chunks"], job.get("seeds", [1, 2, 3])
    order = []
    if job.get("smoke", True):
        order.append((seeds[0], "smoke", chunks[0]["text"]))
    for seed in seeds:
        order.extend((seed, c["id"], c["text"]) for c in chunks)
    return order


def run_qwentts(job, inputs, arm_dir, deadline, stall_s, log_path):
    model, port = job["model"], int(job.get("port", 18089))
    base = f"http://127.0.0.1:{port}"
    cmd = [binary("tts-server"), "--model", model["talker"], "--codec", model["codec"], "--host", "127.0.0.1",
           "--port", str(port), "--lang", job.get("language", "English"), "--alias", job["arm"]]
    if job.get("backend", "vulkan") == "vulkan":
        cmd += ["--device", job.get("device", "Vulkan0")]
    else:
        cmd += ["--device", "CPU"]
    result = {"command": cmd, "chunks": [], "stop": None}
    t_start = time.monotonic()
    with open(log_path, "ab") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=runtime_env(job))
    try:
        while True:  # load: until /health answers
            if proc.poll() is not None:
                result["stop"] = {"reason": "crash", "detail": f"tts-server exited {proc.returncode} during load"}
                return result
            if time.monotonic() > deadline:
                result["stop"] = {"reason": "budget", "detail": "load did not finish inside the budget"}
                return result
            try:
                with urllib.request.urlopen(base + "/health", timeout=2) as r:
                    if r.status == 200:
                        break
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(0.25)
        result["load_s"] = round(time.monotonic() - t_start, 3)
        result["t_loaded"] = time.monotonic()

        def post(path, body, timeout):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()

        voice = None
        if job.get("reference"):
            ref = job["reference"]
            voice = ref["voice_id"]
            body = {"name": voice, "wav_b64": base64.b64encode(Path(ref["wav"]).read_bytes()).decode()}
            if job.get("use_ref_text", True):
                body["ref_text"] = Path(ref["text"]).read_text(encoding="utf-8").strip()
            t0 = time.monotonic()
            post("/v1/audio/voices", body, timeout=min(stall_s, max(1, deadline - time.monotonic())))
            result["voice_register_s"] = round(time.monotonic() - t0, 3)
        for seed, chunk_id, text in plan_requests(job, inputs):
            remaining = deadline - time.monotonic()
            if remaining <= 1:
                result["stop"] = {"reason": "budget", "detail": f"stopped before seed {seed} {chunk_id}"}
                break
            body = {"input": text, "language": job.get("language", "English"), "response_format": "wav",
                    "seed": seed, **job.get("options", {})}
            if voice:
                body["voice"] = voice
            out = arm_dir / (f"seed{seed}" if chunk_id != "smoke" else ".") / f"{chunk_id}.wav"
            out.parent.mkdir(parents=True, exist_ok=True)
            t0 = time.monotonic()
            try:
                audio = post("/v1/audio/speech", body, timeout=min(stall_s, remaining))
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                hit = log_stop_reason(log_path)
                reason = hit[0] if hit else ("budget" if time.monotonic() >= deadline - 1 else
                                             "crash" if proc.poll() is not None else "stall")
                result["stop"] = {"reason": reason, "detail": f"seed {seed} {chunk_id}: {exc}"[:500]}
                break
            wall = time.monotonic() - t0
            out.write_bytes(audio)
            result["chunks"].append(_record_chunk(arm_dir, out, seed, chunk_id, wall, "http_request"))
    finally:
        _terminate(proc)
    return result


METRIC_LINE = re.compile(r"^metrics\[(?P<id>[^\]]+)\]\.(?P<key>wall_ms|audio_duration_ms|rtf)=(?P<val>\S+)$")


def run_audiocpp(job, inputs, arm_dir, deadline, stall_s, log_path):
    model = job["model"]
    wav_dir = arm_dir / "wav"
    wav_dir.mkdir(parents=True, exist_ok=True)
    order = plan_requests(job, inputs)
    ref = job.get("reference")
    ref_text = Path(ref["text"]).read_text(encoding="utf-8").strip() if ref else None
    requests, ids = [], {}
    for seed, chunk_id, text in order:
        rid = "smoke" if chunk_id == "smoke" else f"seed{seed}__{chunk_id}"
        options = {"seed": str(seed), "raw_text": "true", **{k: str(v) for k, v in job.get("options", {}).items()}}
        item = {"id": rid, "text": text, "language": job.get("language", "en"), "options": options}
        if ref:
            item["voice_ref"] = str(Path(ref["wav"]).resolve())
            if job.get("use_ref_text", True):
                options["reference_text"] = ref_text
        else:  # decoy 2: a built-in preset voice through Ming's `ip` template, no cloning
            options.update({"template_name": "ip", "voice_id": job["preset_voice"]})
        requests.append(item)
        ids[rid] = (seed, chunk_id)
    seq = arm_dir / "requests.json"
    # The request list holds the reference transcript; it stays in the private run directory.
    seq.write_text(json.dumps({"requests": requests}, ensure_ascii=False, indent=1))
    cmd = [binary("audiocpp_cli"), "--task", model.get("task", "clon"), "--family", model["family"],
           "--model", model["path"], "--backend", job.get("backend", "vulkan"), "--threads",
           str(job.get("threads", MAX_THREADS)), "--request-sequence", str(seq), "--out-dir", str(wav_dir),
           "--metrics", "--log"]
    if job.get("backend", "vulkan") == "vulkan":
        cmd += ["--device", str(job.get("device_index", 0))]
    stdbuf = shutil.which("stdbuf")
    if stdbuf:
        cmd = [stdbuf, "-oL", "-eL", *cmd]
    result = {"command": cmd, "chunks": [], "stop": None}
    t_start = time.monotonic()
    seen, appeared = set(), {}
    with open(log_path, "ab") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=runtime_env(job))
    last_progress = t_start
    try:
        while proc.poll() is None:
            now = time.monotonic()
            for p in wav_dir.glob("*.wav"):
                if p.name not in seen:
                    seen.add(p.name)
                    appeared[p.stem] = now
                    last_progress = now
            if now >= deadline:
                result["stop"] = {"reason": "budget", "detail": f"{len(seen)} of {len(order)} requests written"}
                break
            if now - last_progress > stall_s + (0 if seen else stall_s):  # the first output also covers load
                result["stop"] = {"reason": "stall", "detail": f"no new output for {stall_s} s"}
                break
            time.sleep(0.2)
    finally:
        _terminate(proc)
    for p in wav_dir.glob("*.wav"):
        appeared.setdefault(p.stem, time.monotonic())
    if result["stop"] is None and proc.returncode != 0:
        hit = log_stop_reason(log_path)
        result["stop"] = {"reason": hit[0] if hit else "crash",
                          "detail": (hit[1] if hit else f"audiocpp_cli exited {proc.returncode}")[:500]}
    metrics = {}
    for line in Path(log_path).read_text(errors="replace").splitlines():
        m = METRIC_LINE.match(line.strip())
        if m:
            metrics.setdefault(m.group("id"), {})[m.group("key")] = float(m.group("val"))
    previous = t_start
    for rid in [r["id"] for r in requests]:
        if rid not in appeared:
            continue
        wall, source = None, "runtime_metrics"
        if "wall_ms" in metrics.get(rid, {}):
            wall = metrics[rid]["wall_ms"] / 1000.0
        else:
            wall, source = appeared[rid] - previous, "output_appearance_delta"
        previous = appeared[rid]
        seed, chunk_id = ids[rid]
        result["chunks"].append(_record_chunk(arm_dir, wav_dir / f"{rid}.wav", seed, chunk_id, wall, source))
    smoke = metrics.get("smoke", {}).get("wall_ms")
    if "smoke" in appeared:
        first = appeared["smoke"] - t_start
        result["load_s"] = round(first - smoke / 1000.0, 3) if smoke else None
        result["load_s_method"] = "first output time minus the smoke request's own wall time"
        result["t_loaded"] = t_start + (result["load_s"] or 0)
    return result


# ---------------------------------------------------------------------------------------------- arms

def summarise(chunks, seeds, total):
    per_seed = {}
    for seed in seeds:
        rows = [c for c in chunks if c["seed"] == seed and c["id"] != "smoke"]
        wall = sum(c["wall_s"] or 0 for c in rows)
        audio = sum(c["audio_s"] for c in rows)
        per_seed[str(seed)] = {"chunks_done": len(rows), "chunks_total": total, "complete": len(rows) == total,
                               "wall_s": round(wall, 3), "audio_s": round(audio, 3),
                               "rtf": round(wall / audio, 4) if audio > 0 else None}
    return per_seed


def run_arm(job_path, run_dir, window_deadline, sampler):
    started = utc()
    try:
        job, inputs = load_job(job_path)
    except (JobError, OSError, ValueError) as exc:
        return {"schema": RECEIPT_SCHEMA, "job": str(job_path), "state": "refused", "error": str(exc),
                "started_utc": started, "ended_utc": utc()}
    arm_dir = run_dir / job["arm"]
    arm_dir.mkdir(parents=True, exist_ok=True)
    log_path = arm_dir / "runtime.log"
    budget = float(job.get("budget_s", DEFAULT_BUDGET_S))
    stall = float(job.get("stall_s", DEFAULT_STALL_S))
    t_arm = time.monotonic()
    deadline = min(t_arm + budget, window_deadline)
    exe = "tts-server" if job["runtime"] == "qwentts" else "audiocpp_cli"
    receipt = {"schema": RECEIPT_SCHEMA, "arm": job["arm"], "runtime": job["runtime"], "started_utc": started,
               "job": {"file": Path(job_path).name, "sha256": inputs["job_sha256"]},
               "image_digest": os.environ.get("NARRATE_IMAGE_DIGEST"),
               "binary": {"name": exe}, "backend": job.get("backend", "vulkan"),
               "vulkan_icd": job.get("vulkan_icd", "radv"), "threads": job.get("threads", MAX_THREADS),
               "model": {k: (Path(v).name if k in ("talker", "codec", "path") else v)
                         for k, v in job["model"].items()},
               "chunks": {"sha256": inputs["chunks_sha256"], "text_sha256": inputs["text_sha256"],
                          "count": len(inputs["chunks"])},
               "seeds": job.get("seeds", [1, 2, 3]), "budget_s": budget, "stall_s": stall}
    if job.get("reference"):
        ref = job["reference"]
        receipt["reference"] = {"voice_id": ref["voice_id"], "consent_id": ref["consent_id"],
                                "wav_sha256": inputs["reference_wav"], "text_sha256": inputs["reference_text"],
                                "ref_text_used": job.get("use_ref_text", True)}
    else:
        receipt["preset_voice"] = job["preset_voice"]
    try:
        path = binary(exe)
        receipt["binary"].update({"sha256": sha256_file(path)})
        vram_mark = time.monotonic() - sampler.t0
        runner = run_qwentts if job["runtime"] == "qwentts" else run_audiocpp
        result = runner(job, inputs, arm_dir, deadline, stall, log_path)
    except (JobError, OSError, ValueError) as exc:
        result = {"chunks": [], "stop": {"reason": "error", "detail": str(exc)[:500]}}
        vram_mark = None
    smoke = [c for c in result["chunks"] if c["id"] == "smoke"]
    receipt.update({
        "load_s": result.get("load_s"), "load_s_method": result.get("load_s_method", "until /health answered"),
        "voice_register_s": result.get("voice_register_s"),
        "smoke": smoke[0] if smoke else None,
        "per_seed": summarise(result["chunks"], receipt["seeds"], len(inputs["chunks"])),
        "chunk_results": [c for c in result["chunks"] if c["id"] != "smoke"],
        "stop": result.get("stop"), "ended_utc": utc(),
        "arm_wall_s": round(time.monotonic() - t_arm, 3),
    })
    if sampler.available and vram_mark is not None:
        peak = sampler.peak_since(vram_mark)
        receipt["vram"] = {"peak_bytes": peak, "peak_above_baseline_bytes":
                           (peak - sampler.baseline_bytes) if peak is not None and sampler.baseline_bytes is not None
                           else None}
    complete = all(s["complete"] for s in receipt["per_seed"].values())
    receipt["state"] = "complete" if complete and not receipt["stop"] else ("partial" if result["chunks"] else "failed")
    (arm_dir / "receipt.json").write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n")
    return receipt


def cmd_run(args):
    window_s = float(os.environ.get("NARRATE_WINDOW_S", DEFAULT_WINDOW_S))
    t0 = time.monotonic()
    window_deadline = t0 + window_s
    jobs = [Path(j) for j in args.jobs]
    try:
        first, _ = load_job(jobs[0])
    except JobError as exc:
        print(f"bench: {exc}", file=sys.stderr)
        return 2
    run_id = os.environ.get("NARRATE_RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(first["out_root"]) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    # The weights' sha256 at the start, once per file, against sources.json (the volume is read-only, so
    # this binds the bytes the arms load). An arm whose weights fail is refused; the others still run.
    t_verify = time.monotonic()
    fetch, doc, sources_path = load_sources(args.sources)
    verified, weight_errors = {}, {}
    for job in jobs:
        try:
            j, _ = load_job(job)
        except JobError:
            continue  # run_arm records the refusal
        try:
            for f in job_model_files(j):
                if f not in verified:
                    source, entry = pinned_entry(doc, f)
                    verified[f] = verify_file(fetch, f, source, entry)
        except (JobError, OSError, ValueError) as exc:
            weight_errors[job] = str(exc)
    weights = {"sources_sha256": sha256_file(sources_path), "files": list(verified.values()),
               "errors": {p.name: e for p, e in weight_errors.items()},
               "verify_s": round(time.monotonic() - t_verify, 3)}
    print(json.dumps({"weights_verified": len(verified), "errors": weights["errors"],
                      "verify_s": weights["verify_s"]}), flush=True)
    sampler = VramSampler(os.environ.get("NARRATE_VRAM_SYSFS", VRAM_SYSFS))
    sampler.baseline_bytes = sampler.baseline(1.0) if sampler.available else None
    sampler.start()
    window = {"schema": "narrate-bench-window/1", "run_id": run_id, "started_utc": utc(), "window_s": window_s,
              "image_digest": os.environ.get("NARRATE_IMAGE_DIGEST"),
              "vram": {"sysfs": str(sampler.path), "available": sampler.available, "hz": 10,
                       "idle_baseline_bytes": sampler.baseline_bytes},
              "weights": weights, "arms": []}
    bench_stop = None
    for job in jobs:
        if job in weight_errors:
            window["arms"].append({"job": job.name, "state": "refused", "reason": "weights",
                                   "error": weight_errors[job]})
            continue
        if bench_stop:
            window["arms"].append({"job": job.name, "state": "skipped", "reason": bench_stop})
            continue
        if time.monotonic() >= window_deadline:
            window["arms"].append({"job": job.name, "state": "skipped", "reason": "window deadline"})
            continue
        receipt = run_arm(job, run_dir, window_deadline, sampler)
        print(json.dumps({k: receipt.get(k) for k in ("arm", "state", "load_s", "stop", "per_seed", "vram")}),
              flush=True)
        window["arms"].append({"job": job.name, "arm": receipt.get("arm"), "state": receipt["state"],
                               "stop": receipt.get("stop"), "error": receipt.get("error")})
        if (receipt.get("stop") or {}).get("reason") == "device_lost":
            bench_stop = "bench stop: device lost or ring timeout in the previous arm"
    sampler.stop(run_dir / "vram.csv")
    peak = max((v for _, v in sampler.samples), default=None)
    window["vram"].update({"samples": len(sampler.samples), "peak_bytes": peak,
                           "end_bytes": sampler.read() if sampler.available else None})
    window.update({"ended_utc": utc(), "wall_s": round(time.monotonic() - t0, 3), "bench_stop": bench_stop})
    (run_dir / "window.json").write_text(json.dumps(window, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"run_dir": str(run_dir), "arms": window["arms"]}), flush=True)
    return 0 if all(a["state"] == "complete" for a in window["arms"]) else 1


def cmd_check(args):
    ok = True
    for job in args.jobs:
        try:
            j, inputs = load_job(job)
            exe = "tts-server" if j["runtime"] == "qwentts" else "audiocpp_cli"
            print(json.dumps({"job": Path(job).name, "arm": j["arm"], "ok": True, "chunks": len(inputs["chunks"]),
                              "requests": len(plan_requests(j, inputs)), "binary_on_path": bool(shutil.which(exe))}))
        except (JobError, OSError, ValueError) as exc:
            ok = False
            print(json.dumps({"job": Path(job).name, "ok": False, "error": str(exc)}))
    return 0 if ok else 2


def cmd_versions(_args):
    out = {}
    for exe in ("audiocpp_cli", "tts-server", "qwen-tts"):
        path = shutil.which(exe)
        out[exe] = {"sha256": sha256_file(path)} if path else None
    vk = shutil.which("vulkaninfo")
    for icd in ("radv", "lavapipe"):
        files = os.environ.get(ICD_ENV[icd])
        if vk and files:
            env = dict(os.environ, VK_DRIVER_FILES=files)
            r = subprocess.run([vk, "--summary"], capture_output=True, text=True, env=env, timeout=60, check=False)
            names = re.findall(r"deviceName\s*=\s*(.+)", r.stdout)
            out[f"vulkan_{icd}"] = {"exit": r.returncode, "devices": [n.strip() for n in names]}
    print(json.dumps(out, indent=1))
    return 0


def _load_fetch():
    """narrate/bench/fetch.py: beside this file in the image, one directory up in the repository."""
    here = Path(__file__).resolve().parent
    for candidate in (here / "fetch.py", here.parent / "fetch.py"):
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location("narrate_bench_fetch", candidate)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module, candidate.parent / "sources.json"
    raise JobError("fetch.py not found beside the bench entrypoint")


# ---------------------------------------------------------------------------------------------- weights
# The GPU host's volume layout (its owner's pod contract): <root>/hf/<repo>/<revision>/<path>, with a
# SHA256SUMS file in each <revision> directory. The bench root in the window pod is /models/bench/narrate.

def load_sources(path=None):
    fetch, default = _load_fetch()
    path = Path(path) if path else default
    return fetch, fetch.load_sources(path), path


def weight_dir(root, source):
    return Path(root) / "hf" / source["repo"] / source["revision"]


IMAGE_SOURCES = ("qwen3-tts-1.7b-base-qwentts", "ming3-0.5b-gguf", "voxcpm2-gguf")  # A2-gpu-alt, A1-gpu, A3-gpu


def gpu_sources(doc, only=()):
    only = tuple(only) or IMAGE_SOURCES
    chosen = [s for s in doc["sources"] if s["kind"] == "hf" and s["id"] in only]
    missing = sorted(set(only) - {s["id"] for s in chosen})
    if missing:
        raise JobError(f"unknown or non-hf source ids: {', '.join(missing)}")
    return chosen


def job_model_files(job):
    model = job["model"]
    return [model[k] for k in (("talker", "codec") if job["runtime"] == "qwentts" else ("path",))]


def pinned_entry(doc, path):
    """The sources.json source and file a model path names, by the <repo>/<revision>/<path> layout."""
    text = str(path)
    for source in doc["sources"]:
        if source["kind"] != "hf":
            continue
        marker = f"/hf/{source['repo']}/{source['revision']}/"
        if marker in text:
            rel = text.split(marker, 1)[1]
            for entry in source["files"]:
                if entry["path"] == rel:
                    return source, entry
    raise JobError(f"{Path(path).name}: not a pinned file under hf/<repo>/<revision>/ in sources.json")


def verify_file(fetch, path, source, entry):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise JobError(f"{source['id']}/{entry['path']}: missing or not a regular file")
    if path.stat().st_size != entry["bytes"]:
        raise JobError(f"{source['id']}/{entry['path']}: {path.stat().st_size} bytes, declared {entry['bytes']}")
    t = time.monotonic()
    digest, blob = fetch.hash_file(path, entry["bytes"])
    check = fetch.verify(f"{source['id']}/{entry['path']}", entry, digest, blob)
    return {"id": source["id"], "repo": source["repo"], "revision": source["revision"], "path": entry["path"],
            "bytes": entry["bytes"], "sha256": digest, "check": check, "hash_s": round(time.monotonic() - t, 3)}


def verify_tree(root, only=(), sources=None):
    """Every pinned file of the selected sources, against sources.json and the directory's SHA256SUMS."""
    fetch, doc, _ = load_sources(sources)
    records = []
    for source in gpu_sources(doc, only):
        base = weight_dir(root, source)
        sums = fetch.read_sums(base / "SHA256SUMS")
        for entry in source["files"]:
            record = verify_file(fetch, base / entry["path"], source, entry)
            if sums.get(entry["path"]) != record["sha256"]:
                raise JobError(f"{source['id']}/{entry['path']}: SHA256SUMS does not record {record['sha256']}")
            records.append(record)
    return records


def cmd_verify(args):
    records = verify_tree(args.root, args.only or (), args.sources)
    print(json.dumps({"root": str(args.root), "files": records}, indent=1))
    return 0


def _fill(template, values):
    if isinstance(template, dict):
        return {k: _fill(v, values) for k, v in template.items()}
    if isinstance(template, list):
        return [_fill(v, values) for v in template]
    if isinstance(template, str):
        for key, value in values.items():
            template = template.replace(key, value)
    return template


def cmd_layout(args):
    """On the CPU host: build the upload tree for the GPU host's volume, outside the repository.

    hf/<repo>/<revision>/<path> are symlinks to narrate-fetch's hash-checked copies (<weights>/hf/<id>/<path>),
    with SHA256SUMS from fetch's measured values; inputs/ holds the chunk list, the consented reference clip
    and its transcript (symlinks), and the job files filled from the templates with their sha256 values. The
    tree is streamed with `tar -h`, so the symlinks arrive as files."""
    fetch, doc, _ = load_sources(args.sources)
    dest = Path(args.dest)
    fetch.resolve_dest(dest)  # refuses a destination inside a repository checkout
    weights = Path(args.weights)
    for source in gpu_sources(doc, args.only or ()):
        have = fetch.read_sums(fetch.hf_base(weights, source) / "SHA256SUMS")
        out = weight_dir(dest, source)
        out.mkdir(parents=True, exist_ok=True)
        lines = []
        for entry in source["files"]:
            src = fetch.hf_base(weights, source) / entry["path"]
            if not src.is_file() or src.stat().st_size != entry["bytes"]:
                raise JobError(f"{source['id']}/{entry['path']}: not fetched (run just narrate-fetch --apply)")
            digest = have.get(entry["path"])
            if digest is None or (entry["sha256"] is not None and digest != entry["sha256"]):
                raise JobError(f"{source['id']}/{entry['path']}: fetch's SHA256SUMS lacks the declared sha256")
            link = out / entry["path"]
            link.parent.mkdir(parents=True, exist_ok=True)
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(src.resolve())
            lines.append(f"{digest}  {entry['path']}\n")
        (out / "SHA256SUMS").write_text("".join(sorted(lines)), encoding="utf-8")
    if args.jobs:
        if not all((args.voice_id, args.consent_id, args.ref_wav, args.ref_text, args.chunks)):
            raise JobError("--jobs needs --voice-id, --consent-id, --ref-wav, --ref-text and --chunks")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", args.voice_id):
            raise JobError("--voice-id must be a short lowercase id")
        inputs = dest / "inputs"
        (inputs / "voices").mkdir(parents=True, exist_ok=True)
        (inputs / "jobs").mkdir(parents=True, exist_ok=True)
        links = {inputs / "chunks-v1.json": args.chunks, inputs / "voices" / f"{args.voice_id}.wav": args.ref_wav,
                 inputs / "voices" / f"{args.voice_id}.txt": args.ref_text}
        for link, target in links.items():
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(Path(target).resolve())
        values = {"CHUNKS_SHA256": sha256_file(args.chunks), "REFERENCE_WAV_SHA256": sha256_file(args.ref_wav),
                  "REFERENCE_TEXT_SHA256": sha256_file(args.ref_text), "CONSENT_ID": args.consent_id,
                  "VOICE_ID": args.voice_id}
        for template in args.jobs:
            job = _fill(json.loads(Path(template).read_text(encoding="utf-8")), values)
            (inputs / "jobs" / Path(template).name).write_text(dumps_canonical(job), encoding="utf-8")
    print(json.dumps({"dest": str(dest), "upload": f"tar -C {dest} -chf - hf inputs"}))
    return 0


def cmd_receive(args):
    """In the staging pod: wait for the operator's upload-complete marker, then verify the weights and the
    jobs, write a dated receipt beside them, and print NARRATE-STAGE-DONE rc=N."""
    root = Path(args.root)
    marker = root / ".upload-complete"
    deadline = time.monotonic() + args.wait_s
    print(json.dumps({"waiting_for": str(marker), "wait_s": args.wait_s}), flush=True)
    while not marker.exists():
        if time.monotonic() >= deadline:
            print("NARRATE-STAGE-DONE rc=3 (no upload-complete marker)", flush=True)
            return 3
        time.sleep(5)
    receipt = {"schema": "narrate-bench-stage/1", "started_utc": utc(), "root": str(root)}
    rc = 0
    try:
        receipt["weights"] = verify_tree(root, args.only or (), args.sources)
        jobs = sorted((root / "inputs" / "jobs").glob("*.json"))
        receipt["jobs"] = []
        for job in jobs:
            j, inputs = load_job(job)
            receipt["jobs"].append({"job": job.name, "arm": j["arm"], "sha256": inputs["job_sha256"],
                                    "chunks": len(inputs["chunks"])})
    except (JobError, OSError, ValueError) as exc:
        receipt["error"] = str(exc)
        rc = 2
    receipt["ended_utc"] = utc()
    out = root / "receipts" / f"stage-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"receipt": str(out), "files": len(receipt.get("weights", [])), "error": receipt.get("error")}))
    print(f"NARRATE-STAGE-DONE rc={rc}", flush=True)
    return rc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="verify the weights, then run arms in order")
    p.add_argument("--sources", help="pinned sources file (default: the one beside fetch.py)")
    p.add_argument("jobs", nargs="+")
    p.set_defaults(func=cmd_run)
    p = sub.add_parser("check", help="validate jobs and inputs")
    p.add_argument("jobs", nargs="+")
    p.set_defaults(func=cmd_check)
    p = sub.add_parser("versions", help="binaries and Vulkan devices")
    p.set_defaults(func=cmd_versions)
    p = sub.add_parser("verify", help="hash-check the weight tree <root>/hf/<repo>/<revision>/")
    p.add_argument("--root", required=True)
    p.add_argument("--only", action="append", help="source id (repeatable; default: the three image arms' sources)")
    p.add_argument("--sources")
    p.set_defaults(func=cmd_verify)
    p = sub.add_parser("layout", help="CPU host: build the upload tree from narrate-fetch's weights")
    p.add_argument("--weights", required=True, help="narrate-fetch's destination (NARRATE_WEIGHTS_DIR)")
    p.add_argument("--dest", required=True, help="upload tree, outside any checkout")
    p.add_argument("--only", action="append")
    p.add_argument("--sources")
    p.add_argument("--jobs", nargs="*", default=[], help="job templates to fill into inputs/jobs/")
    p.add_argument("--chunks", help="the shared chunk list (narrate/bench/chunks-v1.json)")
    p.add_argument("--voice-id")
    p.add_argument("--consent-id")
    p.add_argument("--ref-wav")
    p.add_argument("--ref-text")
    p.set_defaults(func=cmd_layout)
    p = sub.add_parser("receive", help="staging pod: wait for the upload, verify, write a receipt")
    p.add_argument("--root", required=True)
    p.add_argument("--wait-s", type=float, default=3300)
    p.add_argument("--only", action="append")
    p.add_argument("--sources")
    p.set_defaults(func=cmd_receive)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (JobError, ValueError, OSError) as exc:  # fetch.FetchError is a ValueError
        print(f"bench: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
