"""narrate/bench/image/bench_arm.py: the GPU-host bench entrypoint, driven end to end with fake runtimes.

No GPU, weights, voice or network beyond loopback: a fake `tts-server` (qwentts.cpp's HTTP shape) and a fake
`audiocpp_cli` (its --request-sequence and metrics lines) write synthetic WAVs. The fakes stand in for the
runtimes so the job checks, stop rules, timing and receipt fields can be exercised; they say nothing about the
real engines. The weights are synthetic files under a synthetic sources.json, in the GPU host's volume layout
(hf/<repo>/<revision>/<path>). The deploy manifests are rendered and checked against the GPU-host owner's pod
contract (deploy/narrate-bench/README.md), and checked by the owner's own validator when
NARRATE_BENCH_WINDOW_VALIDATOR names it and PyYAML is importable.
"""

import hashlib
import importlib.util
import json
import os
import re
import socket
import stat
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("narrate_bench_arm", ROOT / "narrate" / "bench" / "image" / "bench_arm.py")
bench = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bench)
sys.path.insert(0, str(ROOT / "tests" / "support"))
import mini_yaml  # noqa: E402

REV = "0123456789abcdef0123456789abcdef01234567"
CHUNKS = {"schema": "narrate-bench-chunks/1", "text_sha256": "0" * 64, "chunks": [
    {"id": f"s1.c0{i}", "section": "s1", "text": f"Synthetic sentence number {i} for the fake runtimes."}
    for i in range(1, 5)]}


def synthetic_sources(root):
    """Write a weight tree and its sources.json; return the sources path and the model file paths."""
    files = {"talker.gguf": b"synthetic talker " * 64, "codec.gguf": b"synthetic codec " * 64,
             "sub/model.gguf": b"synthetic model " * 64}
    readme = b"synthetic card\n"
    base = Path(root) / "models" / "hf" / "example" / "synthetic" / REV
    entries, sums = [], []
    for name, data in files.items():
        (base / name).parent.mkdir(parents=True, exist_ok=True)
        (base / name).write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        entries.append({"path": name, "bytes": len(data), "sha256": digest})
        sums.append(f"{digest}  {name}\n")
    (base / "README.md").write_bytes(readme)
    entries.append({"path": "README.md", "bytes": len(readme), "sha256": None,
                    "git_blob_sha1": hashlib.sha1(b"blob %d\0" % len(readme) + readme).hexdigest()})
    sums.append(f"{hashlib.sha256(readme).hexdigest()}  README.md\n")
    (base / "SHA256SUMS").write_text("".join(sorted(sums)))
    sources = Path(root) / "sources.json"
    sources.write_text(json.dumps({"schema_version": 1, "sources": [
        {"id": "synthetic-gguf", "kind": "hf", "repo": "example/synthetic", "revision": REV, "arms": ["A9-gpu"],
         "licence": "MIT", "files": entries}]}))
    return sources, {k: str(base / k) for k in files}

FAKE_WAV = r'''
import struct
def wav(seconds, rate=24000):
    n = int(seconds * rate)
    data = b"\x00\x00" * n
    return (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate,
            rate * 2, 2, 16) + b"data" + struct.pack("<I", len(data)) + data)
'''

FAKE_TTS_SERVER = FAKE_WAV + r'''
import json, os, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer
args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
mode = os.environ.get("FAKE_MODE", "ok")
time.sleep(0.2)  # load
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json"):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        self._send(200, b'{"status":"ok"}')
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/v1/audio/voices":
            assert body["wav_b64"] and body["name"]
            print("voice", body["name"], "ref_text" in body, flush=True)
            return self._send(200, b'{"ok":true}')
        if mode == "hang" and body["input"] != "":
            time.sleep(30)
        print("speech", body.get("voice"), body["seed"], flush=True)
        self._send(200, wav(len(body["input"]) * 0.05), "audio/wav")
HTTPServer(("127.0.0.1", int(args["--port"])), H).serve_forever()
'''

FAKE_AUDIOCPP = FAKE_WAV + r'''
import json, os, sys, time
args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
mode = os.environ.get("FAKE_MODE", "ok")
seq = json.load(open(args["--request-sequence"]))["requests"]
out = args["--out-dir"]
time.sleep(0.2)  # load
for i, r in enumerate(seq):
    if mode == "oom" and i == 2:
        print("ggml_vulkan: Device memory allocation failed: ErrorOutOfDeviceMemory", flush=True)
        sys.exit(1)
    open(os.path.join(out, r["id"] + ".wav"), "wb").write(wav(len(r["text"]) * 0.05, 44100))
    print(f"metrics[{r['id']}].wall_ms=12.5", flush=True)
    print(f"metrics[{r['id']}].options={json.dumps(r['options'], sort_keys=True)}", flush=True)
'''


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class BenchImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.bin = self.dir / "bin"
        self.bin.mkdir()
        for name, body in (("tts-server", FAKE_TTS_SERVER), ("audiocpp_cli", FAKE_AUDIOCPP)):
            p = self.bin / name
            p.write_text(f"#!{sys.executable}\n{body}")
            p.chmod(p.stat().st_mode | stat.S_IXUSR)
        self.env = {k: os.environ.get(k) for k in ("PATH", "FAKE_MODE", "NARRATE_RUN_ID", "NARRATE_VRAM_SYSFS",
                                                   "NARRATE_WINDOW_S")}
        os.environ["PATH"] = f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}"
        os.environ["NARRATE_VRAM_SYSFS"] = str(self.dir / "vram_used")
        (self.dir / "vram_used").write_text("1000\n")
        os.environ["NARRATE_RUN_ID"] = "test-run"
        self.chunks = self.dir / "chunks.json"
        self.chunks.write_text(bench.dumps_canonical(CHUNKS))
        (self.dir / "ref.wav").write_bytes(b"RIFF synthetic reference")
        (self.dir / "ref.txt").write_text("A synthetic reference transcript.\n")
        self.sources, self.models = synthetic_sources(self.dir)

    def tearDown(self):
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def sha(self, name):
        return hashlib.sha256((self.dir / name).read_bytes()).hexdigest()

    def job(self, name, **over):
        doc = {"schema": bench.JOB_SCHEMA, "arm": "A2-gpu-alt", "runtime": "qwentts", "threads": 2,
               "port": free_port(), "model": {"talker": self.models["talker.gguf"],
                                              "codec": self.models["codec.gguf"]},
               "reference": {"voice_id": "synthetic-voice", "consent_id": "consent-synthetic",
                             "wav": str(self.dir / "ref.wav"), "wav_sha256": self.sha("ref.wav"),
                             "text": str(self.dir / "ref.txt"), "text_sha256": self.sha("ref.txt")},
               "chunks": str(self.chunks), "chunks_sha256": self.sha("chunks.json"), "limit_chunks": 3,
               "seeds": [1, 2], "out_root": str(self.dir / "runs"), "stall_s": 5, "budget_s": 60}
        doc.update(over)
        path = self.dir / name
        path.write_text(json.dumps(doc))
        return path

    def run_bench(self, *jobs):
        return bench.main(["run", "--sources", str(self.sources), *map(str, jobs)])

    def receipt(self, arm):
        return json.loads((self.dir / "runs" / "test-run" / arm / "receipt.json").read_text())

    # -- job refusals -----------------------------------------------------------------------------

    def test_cloned_arm_without_consent_is_refused(self):
        job = self.job("j.json")
        doc = json.loads(job.read_text())
        doc["reference"]["consent_id"] = ""
        job.write_text(json.dumps(doc))
        with self.assertRaisesRegex(bench.JobError, "consent stop"):
            bench.load_job(job)

    def test_reference_hash_mismatch_is_refused(self):
        job = self.job("j.json")
        doc = json.loads(job.read_text())
        doc["reference"]["wav_sha256"] = "0" * 64
        job.write_text(json.dumps(doc))
        with self.assertRaisesRegex(bench.JobError, "does not match"):
            bench.load_job(job)

    def test_threads_above_the_bound_are_refused(self):
        with self.assertRaisesRegex(bench.JobError, "threads"):
            bench.load_job(self.job("j.json", threads=16))

    def test_preset_voice_needs_audiocpp_tts(self):
        job = self.job("j.json", reference=None, preset_voice="UK_George")
        with self.assertRaisesRegex(bench.JobError, "preset_voice"):
            bench.load_job(job)

    # -- end to end with fake runtimes ------------------------------------------------------------

    def test_qwentts_arm_writes_wavs_and_a_receipt(self):
        self.assertEqual(self.run_bench(self.job("a2.json")), 0)
        r = self.receipt("A2-gpu-alt")
        self.assertEqual(r["state"], "complete")
        self.assertIsNone(r["stop"])
        self.assertGreater(r["load_s"], 0)
        self.assertEqual(r["reference"]["consent_id"], "consent-synthetic")
        self.assertNotIn("synthetic reference transcript", json.dumps(r))
        self.assertEqual(r["per_seed"]["1"]["chunks_done"], 3)  # limit_chunks
        self.assertTrue(r["per_seed"]["2"]["complete"])
        self.assertIsNotNone(r["smoke"])
        for c in r["chunk_results"]:
            self.assertEqual(c["sample_rate"], 24000)
            self.assertAlmostEqual(c["rtf"], c["wall_s"] / c["audio_s"], places=3)
            self.assertTrue((self.dir / "runs" / "test-run" / "A2-gpu-alt" / c["wav"]).is_file())
        self.assertEqual(r["vram"]["peak_above_baseline_bytes"], 0)
        window = json.loads((self.dir / "runs" / "test-run" / "window.json").read_text())
        self.assertEqual(window["vram"]["idle_baseline_bytes"], 1000)
        self.assertEqual(sorted(f["path"] for f in window["weights"]["files"]), ["codec.gguf", "talker.gguf"])
        self.assertTrue(all(f["check"] == "matched_declared_sha256" for f in window["weights"]["files"]))
        self.assertGreater(window["vram"]["samples"], 0)

    def test_qwentts_stall_stops_the_arm(self):
        os.environ["FAKE_MODE"] = "hang"
        self.assertEqual(self.run_bench(self.job("a2.json", stall_s=1)), 1)
        r = self.receipt("A2-gpu-alt")
        self.assertEqual(r["stop"]["reason"], "stall")
        self.assertEqual(r["state"], "failed")

    def test_audiocpp_arms_run_in_order_with_runtime_metrics(self):
        model = {"family": "ming3_tts", "task": "clon", "path": self.models["sub/model.gguf"]}
        a1 = self.job("a1.json", arm="A1-gpu", runtime="audiocpp", model=model, seeds=[1])
        d2 = self.job("d2.json", arm="D2-preset", runtime="audiocpp", reference=None, preset_voice="UK_George",
                      model=dict(model, task="tts"), seeds=[1], smoke=False, limit_chunks=2)
        self.assertEqual(self.run_bench(a1, d2), 0)
        r = self.receipt("A1-gpu")
        self.assertEqual(r["state"], "complete")
        self.assertTrue(all(c["wall_source"] == "runtime_metrics" and c["wall_s"] == 0.0125
                            for c in r["chunk_results"]))
        self.assertEqual(r["chunk_results"][0]["sample_rate"], 44100)
        log = (self.dir / "runs" / "test-run" / "A1-gpu" / "runtime.log").read_text()
        self.assertIn('"raw_text": "true"', log)
        self.assertIn('"reference_text": "A synthetic reference transcript."', log)
        d = self.receipt("D2-preset")
        self.assertEqual(d["preset_voice"], "UK_George")
        self.assertEqual(d["per_seed"]["1"]["chunks_done"], 2)
        dlog = (self.dir / "runs" / "test-run" / "D2-preset" / "runtime.log").read_text()
        self.assertIn('"template_name": "ip"', dlog)
        self.assertIn('"voice_id": "UK_George"', dlog)

    def test_audiocpp_oom_is_named_and_the_next_arm_still_runs(self):
        os.environ["FAKE_MODE"] = "oom"
        model = {"family": "voxcpm2", "task": "clon", "path": self.models["sub/model.gguf"]}
        a3 = self.job("a3.json", arm="A3-gpu", runtime="audiocpp", model=model)
        a2 = self.job("a2.json")
        self.assertEqual(self.run_bench(a3, a2), 1)
        r = self.receipt("A3-gpu")
        self.assertEqual(r["stop"]["reason"], "oom")
        self.assertEqual(r["state"], "partial")
        self.assertEqual(self.receipt("A2-gpu-alt")["state"], "complete")

    def test_window_deadline_skips_later_arms(self):
        os.environ["NARRATE_WINDOW_S"] = "0"
        self.assertEqual(self.run_bench(self.job("a2.json")), 1)
        window = json.loads((self.dir / "runs" / "test-run" / "window.json").read_text())
        self.assertEqual(window["arms"][0]["state"], "skipped")

    def test_tampered_weights_refuse_that_arm_and_the_next_arm_runs(self):
        path = Path(self.models["sub/model.gguf"])
        path.write_bytes(b"X" + path.read_bytes()[1:])  # same size, different bytes
        model = {"family": "voxcpm2", "task": "clon", "path": str(path)}
        a3 = self.job("a3.json", arm="A3-gpu", runtime="audiocpp", model=model)
        self.assertEqual(self.run_bench(a3, self.job("a2.json")), 1)
        window = json.loads((self.dir / "runs" / "test-run" / "window.json").read_text())
        self.assertEqual(window["arms"][0]["state"], "refused")
        self.assertIn("does not match the declared", window["arms"][0]["error"])
        self.assertEqual(window["arms"][1]["state"], "complete")
        self.assertFalse((self.dir / "runs" / "test-run" / "A3-gpu").exists())

    def test_unpinned_weights_are_refused(self):
        stray = self.dir / "stray.gguf"
        stray.write_bytes(b"synthetic")
        job = self.job("a2.json", model={"talker": str(stray), "codec": self.models["codec.gguf"]})
        self.assertEqual(self.run_bench(job), 1)
        window = json.loads((self.dir / "runs" / "test-run" / "window.json").read_text())
        self.assertIn("not a pinned file", window["arms"][0]["error"])

    def test_wav_info_reads_float_and_streamed_headers(self):
        rate, n = 48000, 480
        data = b"\x00" * (n * 4)
        header = (b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 3, 1, rate,
                  rate * 4, 4, 32) + b"data" + struct.pack("<I", 0xFFFFFFFF))
        p = self.dir / "f.wav"
        p.write_bytes(header + data)
        info = bench.wav_info(p)
        self.assertEqual((info["sample_rate"], info["bits"]), (48000, 32))
        self.assertAlmostEqual(info["duration_s"], 0.01)


IMAGE = "ghcr.io/example/narrate-bench@sha256:" + "ab" * 32
RENDER = {"__WINDOW_ID__": "20261024t1500", "__GPU_NODE__": "gpu-node-1", "__MODELS_PVC__": "models-gpu",
          "__IMAGE__": IMAGE, "__IMAGE_DIGEST__": "sha256:" + "ab" * 32}


def render(text):
    for key, value in RENDER.items():
        text = text.replace(key, value)
    self_check = re.findall(r"__[A-Z_]+__", text)
    assert not self_check, self_check
    return text


def contract_problems(pod):
    """The GPU-host owner's pod contract (deploy/narrate-bench/README.md), checked independently here."""
    bad = []
    meta, spec = pod["metadata"], pod["spec"]
    want_labels = {"app.kubernetes.io/name": "narrate-bench", "app.kubernetes.io/part-of": "narrate",
                   "app.kubernetes.io/component": "bench", "app.kubernetes.io/managed-by": "narrate"}
    checks = [
        (pod["apiVersion"] == "v1" and pod["kind"] == "Pod", "a v1 Pod"),
        (meta.get("namespace") == "models", "namespace models"),
        (re.fullmatch(r"narrate-bench-[a-z0-9]([-a-z0-9]{0,40}[a-z0-9])?", meta["name"]) is not None, "name"),
        (all(meta["labels"].get(k) == v for k, v in want_labels.items()), "labels"),
        # The owner reserves its model-store and Lease-peer label prefixes; the pod carries only these four.
        (set(meta["labels"]) == set(want_labels), "no other labels"),
        (list(spec["nodeSelector"]) == ["kubernetes.io/hostname"], "nodeSelector"),
        (spec["restartPolicy"] == "Never", "restartPolicy"),
        (isinstance(spec["activeDeadlineSeconds"], int) and 60 <= spec["activeDeadlineSeconds"] <= 1800, "deadline"),
        (spec["automountServiceAccountToken"] is False, "no token"),
        (spec["priorityClassName"] == "gpu-exclusive", "priority class"),
        ({"name": "ghcr-pull"} in spec["imagePullSecrets"], "pull secret"),
        (spec["securityContext"]["runAsNonRoot"] is True and spec["securityContext"]["runAsUser"] == 10001,
         "non-root 10001"),
        (spec["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}, "seccomp"),
        (105 in spec["securityContext"]["supplementalGroups"], "render group 105"),
        (not spec.get("initContainers") and len(spec["containers"]) == 1, "one container"),
    ]
    c = spec["containers"][0]
    csc, res = c["securityContext"], c["resources"]
    volumes = {v["name"]: v for v in spec["volumes"]}
    mounts = {m["name"]: m for m in c["volumeMounts"]}
    pvcs = [n for n, v in volumes.items() if "persistentVolumeClaim" in v]
    checks += [
        (re.fullmatch(r"ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}", c["image"]) is not None, "image by digest"),
        (c["imagePullPolicy"] == "IfNotPresent", "pull policy"),
        (csc["allowPrivilegeEscalation"] is False and not csc.get("privileged"), "no escalation"),
        (csc["capabilities"] == {"drop": ["ALL"]}, "drop ALL"),
        (csc["readOnlyRootFilesystem"] is True, "read-only root"),
        (not c.get("ports"), "no ports"),
        (str(res["limits"]["devic.es/dri"]) == "1", "one GPU"),
        (res["requests"]["cpu"] in ("2", 2) or res["requests"]["cpu"].endswith("m"), "cpu request"),
        (res["requests"]["memory"] == res["limits"]["memory"] == "12Gi", "memory 12Gi"),
        (len(pvcs) == 1 and volumes[pvcs[0]]["persistentVolumeClaim"].get("readOnly") is True, "PVC read-only"),
        (pvcs and mounts[pvcs[0]] == {"name": pvcs[0], "mountPath": "/models", "readOnly": True}, "/models mount"),
        ("emptyDir" in volumes.get("out", {}) and mounts.get("out", {}).get("mountPath") == "/out", "out at /out"),
        (all(v["emptyDir"].get("sizeLimit") for v in volumes.values() if "emptyDir" in v), "emptyDir sizeLimit"),
        (all(set(v) - {"name"} <= {"persistentVolumeClaim", "emptyDir", "configMap"} for v in volumes.values()),
         "volume kinds"),
    ]
    return [what for ok, what in checks if not ok]


class DeployManifestTests(unittest.TestCase):
    """The rendered pod meets the owner's contract; the templates carry placeholders, not estate names."""

    def read(self, name):
        return (ROOT / "deploy" / "narrate-bench" / name).read_text()

    def test_rendered_bench_pod_meets_the_contract(self):
        docs = mini_yaml.load_all(render(self.read("bench-pod.yaml")))
        self.assertEqual(len(docs), 1, "the runner takes one Pod and writes its own NetworkPolicy")
        self.assertEqual(contract_problems(docs[0]), [])
        c = docs[0]["spec"]["containers"][0]
        self.assertEqual(c["command"], ["/bin/narrate-bench-window"])
        env = {e["name"]: e["value"] for e in c["env"]}
        self.assertEqual(env["NARRATE_RUN_ID"], RENDER["__WINDOW_ID__"])
        self.assertEqual(env["NARRATE_IMAGE_DIGEST"], RENDER["__IMAGE_DIGEST__"])
        self.assertLess(int(env["NARRATE_WINDOW_S"]), docs[0]["spec"]["activeDeadlineSeconds"])
        self.assertTrue(all(env[k].startswith("/tmp/") or env[k] == "/tmp"
                            for k in ("HOME", "XDG_CACHE_HOME", "MESA_SHADER_CACHE_DIR")))
        self.assertEqual(c["resources"]["requests"]["cpu"], "2")

    def test_contract_check_catches_a_broken_pod(self):
        pod = mini_yaml.load_all(render(self.read("bench-pod.yaml")))[0]
        pod["spec"]["securityContext"]["supplementalGroups"] = []
        pod["spec"]["volumes"][0]["persistentVolumeClaim"]["readOnly"] = False
        self.assertEqual(contract_problems(pod), ["render group 105", "PVC read-only"])

    def test_owner_validator_when_available(self):
        script = os.environ.get("NARRATE_BENCH_WINDOW_VALIDATOR")
        if not script:
            self.skipTest("NARRATE_BENCH_WINDOW_VALIDATOR is not set (the GPU-host owner's window runner)")
        spec = importlib.util.spec_from_file_location("narrate_bench_window", script)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except ImportError as exc:
            self.skipTest(f"the validator's imports are unavailable: {exc}")
        pod = mini_yaml.load_all(render(self.read("bench-pod.yaml")))[0]
        pod["spec"]["nodeSelector"] = {"kubernetes.io/hostname": module.NODE}
        pod["spec"]["volumes"][0]["persistentVolumeClaim"]["claimName"] = module.PVC
        self.assertEqual(module.validate_pod(pod, "narrate-bench-20261024t1500"), [])

    def test_templates_hold_placeholders_not_estate_values(self):
        for name in ("bench-pod.yaml", "stage-job.yaml"):
            spec = "\n".join(line for line in self.read(name).splitlines() if not line.lstrip().startswith("#"))
            for placeholder in ("__GPU_NODE__", "__MODELS_PVC__", "__IMAGE__"):
                self.assertIn(placeholder, spec)
            self.assertNotIn("hostPath", spec)
            self.assertNotIn("privileged: true", spec)

    def test_stage_job_has_no_gpu_and_no_network(self):
        docs = mini_yaml.load_all(render(self.read("stage-job.yaml")))
        policy, job = docs
        self.assertEqual(policy["spec"]["egress"], [])
        self.assertEqual(policy["spec"]["ingress"], [])
        self.assertEqual(policy["spec"]["policyTypes"], ["Ingress", "Egress"])
        pod = job["spec"]["template"]
        self.assertTrue(job["metadata"]["name"].startswith("models-stage-"))
        for key, value in policy["spec"]["podSelector"]["matchLabels"].items():
            self.assertEqual(pod["metadata"]["labels"][key], value)
        c = pod["spec"]["containers"][0]
        self.assertNotIn("devic.es/dri", json.dumps(c["resources"]))
        self.assertEqual(c["args"][:3], ["receive", "--root", "/models/bench/narrate"])
        self.assertEqual(c["securityContext"]["capabilities"], {"drop": ["ALL"]})
        self.assertTrue(c["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(pod["spec"]["imagePullSecrets"], [{"name": "ghcr-pull"}])
        self.assertLess(float(c["args"][4]), job["spec"]["activeDeadlineSeconds"])

    def test_pod_jobs_are_the_templates_and_use_the_volume_layout(self):
        pod = mini_yaml.load_all(render(self.read("bench-pod.yaml")))[0]
        args = pod["spec"]["containers"][0]["args"]
        doc = json.loads((ROOT / "narrate" / "bench" / "sources.json").read_text())
        budgets = 0
        for arg in args:
            name = Path(arg).name
            self.assertEqual(arg, f"/models/bench/narrate/inputs/jobs/{name}")
            job = json.loads((ROOT / "narrate" / "bench" / "image" / "jobs" / name).read_text())
            self.assertEqual(job["out_root"], "/out")
            self.assertEqual(job["chunks"], "/models/bench/narrate/inputs/chunks-v1.json")
            self.assertLessEqual(job["threads"], 4)
            for path in bench.job_model_files(job):
                source, entry = bench.pinned_entry(doc, path)
                self.assertIn(source["id"], bench.IMAGE_SOURCES)
                self.assertEqual(path, f"/models/bench/narrate/hf/{source['repo']}/{source['revision']}/{entry['path']}")
            budgets += job["budget_s"]
        self.assertEqual([json.loads((ROOT / "narrate" / "bench" / "image" / "jobs" / Path(a).name).read_text())["arm"]
                          for a in args], ["A2-gpu-alt", "D2-preset", "A1-gpu", "A3-gpu"])
        env = {e["name"]: e["value"] for e in pod["spec"]["containers"][0]["env"]}
        self.assertLessEqual(budgets, int(env["NARRATE_WINDOW_S"]))


class LayoutStageTests(unittest.TestCase):
    """`layout` (CPU host) builds the upload tree; `receive` (staging pod) verifies it after the marker."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.sources, _ = synthetic_sources(self.dir / "src")
        # narrate-fetch's layout: <weights>/hf/<id>/<path> with SHA256SUMS
        fetched = self.dir / "weights" / "hf" / "synthetic-gguf"
        tree = self.dir / "src" / "models" / "hf" / "example" / "synthetic" / REV
        for item in tree.rglob("*"):
            if item.is_file():
                target = fetched / item.relative_to(tree)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(item.read_bytes())
        self.voice = self.dir / "voice"
        self.voice.mkdir()
        (self.voice / "clip.wav").write_bytes(b"RIFF synthetic reference")
        (self.voice / "clip.txt").write_text("A synthetic reference transcript.\n")
        (self.dir / "chunks.json").write_text(bench.dumps_canonical(CHUNKS))
        self.upload = self.dir / "upload"
        self.volume = self.dir / "volume" / "bench" / "narrate"

    def tearDown(self):
        self.tmp.cleanup()

    def layout(self, template):
        return bench.main(["layout", "--weights", str(self.dir / "weights"), "--dest", str(self.upload),
                           "--only", "synthetic-gguf", "--sources", str(self.sources), "--jobs", str(template),
                           "--chunks", str(self.dir / "chunks.json"), "--voice-id", "synthetic-voice",
                           "--consent-id", "consent-synthetic", "--ref-wav", str(self.voice / "clip.wav"),
                           "--ref-text", str(self.voice / "clip.txt")])

    def upload_to_volume(self):
        import tarfile
        with tarfile.open(self.dir / "upload.tar", "w", dereference=True) as tar:
            tar.add(self.upload / "hf", arcname="hf")
            tar.add(self.upload / "inputs", arcname="inputs")
        self.volume.mkdir(parents=True)
        with tarfile.open(self.dir / "upload.tar") as tar:
            tar.extractall(self.volume, filter="data")

    def template(self):
        root = str(self.volume)
        job = {"schema": bench.JOB_SCHEMA, "arm": "A1-gpu", "runtime": "audiocpp", "threads": 4,
               "model": {"family": "ming3_tts", "task": "clon",
                         "path": f"{root}/hf/example/synthetic/{REV}/sub/model.gguf"},
               "reference": {"voice_id": "VOICE_ID", "consent_id": "CONSENT_ID",
                             "wav": f"{root}/inputs/voices/VOICE_ID.wav", "wav_sha256": "REFERENCE_WAV_SHA256",
                             "text": f"{root}/inputs/voices/VOICE_ID.txt", "text_sha256": "REFERENCE_TEXT_SHA256"},
               "chunks": f"{root}/inputs/chunks-v1.json", "chunks_sha256": "CHUNKS_SHA256", "out_root": "/out"}
        path = self.dir / "a1-gpu.json"
        path.write_text(json.dumps(job))
        return path

    def receive(self, wait="5"):
        return bench.main(["receive", "--root", str(self.volume), "--wait-s", wait, "--only", "synthetic-gguf",
                           "--sources", str(self.sources)])

    def test_layout_upload_and_receive_verify_everything(self):
        self.assertEqual(self.layout(self.template()), 0)
        sums = (self.upload / "hf" / "example" / "synthetic" / REV / "SHA256SUMS").read_text()
        self.assertEqual(len(sums.splitlines()), 4)
        job = json.loads((self.upload / "inputs" / "jobs" / "a1-gpu.json").read_text())
        self.assertEqual(job["reference"]["consent_id"], "consent-synthetic")
        self.assertEqual(job["reference"]["wav_sha256"], bench.sha256_file(self.voice / "clip.wav"))
        self.assertEqual(job["chunks_sha256"], bench.sha256_file(self.dir / "chunks.json"))
        self.upload_to_volume()
        self.assertFalse((self.volume / "inputs" / "voices" / "synthetic-voice.wav").is_symlink())
        (self.volume / ".upload-complete").touch()
        self.assertEqual(self.receive(), 0)
        receipt = json.loads(next((self.volume / "receipts").glob("stage-*.json")).read_text())
        self.assertEqual(len(receipt["weights"]), 4)
        self.assertEqual(receipt["jobs"][0]["arm"], "A1-gpu")
        self.assertNotIn("synthetic reference transcript", json.dumps(receipt))

    def test_receive_refuses_a_tampered_upload(self):
        self.assertEqual(self.layout(self.template()), 0)
        self.upload_to_volume()
        path = self.volume / "hf" / "example" / "synthetic" / REV / "talker.gguf"
        path.write_bytes(b"X" + path.read_bytes()[1:])
        (self.volume / ".upload-complete").touch()
        self.assertEqual(self.receive(), 2)

    def test_receive_without_the_marker_times_out(self):
        self.volume.mkdir(parents=True)
        self.assertEqual(self.receive(wait="0"), 3)

    def test_layout_refuses_missing_fetch_and_a_destination_in_the_checkout(self):
        (self.dir / "weights" / "hf" / "synthetic-gguf" / "talker.gguf").unlink()
        self.assertEqual(self.layout(self.template()), 2)
        code = bench.main(["layout", "--weights", str(self.dir / "weights"), "--dest", str(ROOT / "upload-tree"),
                           "--only", "synthetic-gguf", "--sources", str(self.sources)])
        self.assertEqual(code, 2)
        self.assertFalse((ROOT / "upload-tree").exists())


if __name__ == "__main__":
    unittest.main()
