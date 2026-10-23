"""narrate/bench/host_run.py, run-bench.sh and prepare.py: the GPU-host bench runner against a fake TTS binary.

No GPU, model, voice or network: tests/support/narrate_bench_fake_engine.py speaks qwen-tts's --stream-by-line
and audiocpp_cli's --request-sequence closely enough, a fake sysfs tree stands in for the amdgpu card's
mem_info_vram_used, a temporary file stands in for a card node, and the voice registry is a synthetic fixture.
Covered: the committed chunk list and the tracked job (no voice in it), input hash refusal before any process
starts, the qwentts stream split, the audiocpp variant fallback and decoy, the budget, stall, VRAM, unreadable
VRAM, card-node, no-GPU-use and kernel-log stops, SIGHUP, SIGTERM and SIGKILL of the runner with a forking engine
(no process left), and run-bench.sh's holder, bench.env, runner-hash, scope and signal handling.
"""

import hashlib
import importlib.util
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "narrate" / "bench"
FAKE = ROOT / "tests" / "support" / "narrate_bench_fake_engine.py"
GiB = 1 << 30


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


host_run = load("narrate_bench_host_run", BENCH / "host_run.py")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def chunk_doc(texts):
    chunks = [
        {"id": f"s1.c{i:02d}", "section": "s1", "text": t, "words": len(t.split()), "expected_s": 0.1 * len(t.split())}
        for i, t in enumerate(texts, 1)
    ]
    digest = hashlib.sha256(host_run.canonical(chunks).encode("utf-8")).hexdigest()
    return {"schema": "narrate-bench-chunks/1", "chunks_sha256": digest, "chunks": chunks}


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:  # a zombie nobody has reaped yet counts as gone
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


def wait_for(predicate, seconds=10.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


class Workspace(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="narrate-bench-host-"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        d = self.dir
        (d / "bin").mkdir()
        self.fake = d / "bin" / "fake-tts"
        shutil.copy(FAKE, self.fake)
        self.fake.chmod(self.fake.stat().st_mode | stat.S_IXUSR)
        card = d / "drm" / "card0" / "device"
        card.mkdir(parents=True)
        (d / "drivers" / "amdgpu").mkdir(parents=True)
        os.symlink(d / "drivers" / "amdgpu", card / "driver")
        self.vram = card / "mem_info_vram_used"
        self.vram.write_text("1000000\n")
        (card / "mem_info_vram_total").write_text("17095983104\n")
        os.symlink(d / "drivers" / "amdgpu", d / "drm" / "card0-DP-1")  # a connector, never a card
        self.icd = d / "radv_icd.json"
        self.icd.write_text("{}\n")
        self.forbidden = d / "forbidden-card"
        (d / "forbidden-card1").write_text("a stand-in for a card node\n")
        (d / "w").mkdir()
        (d / "w" / "talker.gguf").write_bytes(b"talker" * 100)
        (d / "w" / "codec.gguf").write_bytes(b"codec" * 100)
        (d / "v").mkdir()
        (d / "v" / "ref.wav").write_bytes(b"RIFF synthetic reference")
        (d / "v" / "ref.txt").write_text("A synthetic reference transcript.\n")
        self.voices = d / "v" / "voices.json"
        self.voices.write_text(
            json.dumps(
                {
                    "voices": {
                        "fixture-voice": {
                            "wav": {"path": "ref.wav", "sha256": sha(d / "v" / "ref.wav")},
                            "text": {"path": "ref.txt", "sha256": sha(d / "v" / "ref.txt")},
                        }
                    }
                }
            )
        )
        self.chunks = d / "chunks.json"
        texts = ["One two three four five six.", "Seven eight nine ten eleven.", "Twelve thirteen fourteen."]
        self.chunks.write_text(json.dumps(chunk_doc(texts)))
        self.log = d / "fake.log"
        self.env = {
            "NARRATE_BENCH_TEST_MODE": "1",
            "NARRATE_BENCH_DRM_ROOT": str(d / "drm"),
            "NARRATE_BENCH_FORBIDDEN_DEV": str(self.forbidden),
            "FAKE_WORD_S": "0.1",
            "FAKE_LOG": str(self.log),
            "FAKE_VRAM_FILE": str(self.vram),
            "FAKE_VRAM_BYTES": str(2 * GiB),
            "FAKE_VRAM_IDLE": "1000000",
        }
        for patcher in (
            mock.patch.dict(os.environ, self.env),
            mock.patch.object(host_run, "TEST_MODE", True),
            mock.patch.object(host_run, "DRM_ROOT", str(d / "drm")),
            mock.patch.object(host_run, "FORBIDDEN_DEV", str(self.forbidden)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        host_run.TERMINATED.clear()
        self.addCleanup(host_run.TERMINATED.clear)
        self.addCleanup(self.kill_leftovers)
        self.out = d / "out"
        self.cache = d / "inputs-verified.json"

    def kill_leftovers(self):
        for record in self.invocations():
            for key in ("pid", "helper"):
                if key in record and alive(record[key]):
                    os.kill(record[key], signal.SIGKILL)

    def spec(self, path):
        return {"path": str(path), "sha256": sha(path)}

    def job(self, **arms):
        job = {
            "schema": "narrate-bench-host-job/1",
            "chunks": self.spec(self.chunks),
            "voice": "fixture-voice",
            "voices_file": self.spec(self.voices),
            "vulkan_icd": str(self.icd),
            "seeds": [1, 2, 3],
            "stall_s": 30,
            "vram": {"poll_s": 0.02, "limit_bytes": 12_000_000_000, "min_rise_bytes": 256 << 20},
            "arms": arms or {"Q": self.qwentts_arm(), "M": self.audiocpp_arm()},
        }
        path = self.dir / "job.json"
        path.write_text(json.dumps(job))
        return path

    def qwentts_arm(self, **extra):
        d = self.dir
        arm = {
            "runtime": "qwentts",
            "budget_s": 60,
            "inputs": {
                "binary": self.spec(self.fake),
                "model": self.spec(d / "w" / "talker.gguf"),
                "codec": self.spec(d / "w" / "codec.gguf"),
            },
            "settings": {"device": "Vulkan0", "lang": "English"},
            "variants": [{"name": "icl"}],
        }
        arm.update(extra)
        return arm

    def audiocpp_arm(self, **extra):
        d = self.dir
        arm = {
            "runtime": "audiocpp",
            "budget_s": 60,
            "inputs": {"binary": self.spec(self.fake), "model": self.spec(d / "w" / "talker.gguf")},
            "settings": {"family": "ming3_tts", "task": "clon", "options": {"language": "en", "raw_text": "true"}},
            "variants": [{"name": "ref-text"}, {"name": "speaker-embedding", "reference_text": False}],
            "decoys": [{"id": "preset", "task": "tts", "chunks": ["s1.c02"], "options": {"voice_id": "UK_George"}}],
        }
        arm.update(extra)
        return arm

    def run_arm(self, arm, env=None):
        with mock.patch.dict(os.environ, env or {}):
            argv = ["run", str(self.job_path), "--arm", arm, "--out", str(self.out), "--cache", str(self.cache)]
            code = host_run.main(argv)
        receipt = json.loads((self.out / arm / "receipt.json").read_text())
        return code, receipt

    def invocations(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def engine_pids(self):
        return [r[k] for r in self.invocations() for k in ("pid", "helper") if k in r]


class ChunkList(unittest.TestCase):
    def test_committed_chunk_list_is_current_and_bounded(self):
        prepare = load("narrate_bench_prepare", BENCH / "prepare.py")
        doc = json.loads((BENCH / "chunks-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(prepare.render(prepare.build()), (BENCH / "chunks-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["text_sha256"], hashlib.sha256((BENCH / "text-v1.md").read_bytes()).hexdigest())
        self.assertEqual(sum(c["words"] for c in doc["chunks"]), 795)
        self.assertTrue(all(c["codepoints"] <= 300 and c["id"].startswith(c["section"]) for c in doc["chunks"]))
        self.assertEqual([c["section"] for c in doc["chunks"]], sorted(c["section"] for c in doc["chunks"]))
        host_run.load_chunks(BENCH / "chunks-v1.json")

    def test_tracked_job_binds_the_committed_chunks_and_pinned_weights_and_holds_no_voice(self):
        raw = (BENCH / "host-job.json").read_text(encoding="utf-8")
        job = json.loads(raw)
        self.assertEqual(job["chunks"]["sha256"], sha(BENCH / "chunks-v1.json"))
        self.assertEqual(list(job["arms"]), ["A2-gpu-alt", "A1-gpu", "A3-gpu"])
        self.assertNotIn("voices", job)  # the registry is a private file named by the environment
        self.assertEqual(job["voices_file"]["sha256"], "${NARRATE_BENCH_VOICES_SHA256}")
        self.assertNotIn("consent", raw)
        sources = json.loads((BENCH / "sources.json").read_text(encoding="utf-8"))
        declared = {f["sha256"] for s in sources["sources"] for f in s.get("files", []) if f.get("sha256")}
        for name, arm in job["arms"].items():
            for key, spec in arm["inputs"].items():
                if key != "binary":
                    self.assertIn(spec["sha256"], declared, f"{name}.{key}")
        self.assertNotRegex(raw, r'"/(home|srv|Users|root)/')  # every path comes from the environment

    def test_tracked_job_needs_an_explicit_qwen_device_and_the_voices_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            voices = Path(tmp) / "voices.json"
            voices.write_text('{"voices": {}}')
            icd = Path(tmp) / "icd.json"
            icd.write_text("{}")
            env = {
                "NARRATE_BENCH_ROOT": "/bench",
                "NARRATE_BENCH_JOB_DIR": "/bench/job",
                "NARRATE_BENCH_WEIGHTS": "/bench/weights/hf",
                "NARRATE_BENCH_VOICE": "fixture-voice",
                "NARRATE_BENCH_VOICES_FILE": str(voices),
                "NARRATE_BENCH_VOICES_SHA256": sha(voices),
                "NARRATE_BENCH_VK_ICD": str(icd),
                "NARRATE_BENCH_QWEN_TTS": "/bench/bin/qwen-tts",
                "NARRATE_BENCH_QWEN_TTS_SHA256": "0" * 64,
                "NARRATE_BENCH_QWEN_DEVICE": "Vulkan0",
                "NARRATE_BENCH_AUDIOCPP_CLI": "/bench/bin/audiocpp_cli",
                "NARRATE_BENCH_AUDIOCPP_CLI_SHA256": "1" * 64,
            }
            loaded = host_run.load_job(BENCH / "host-job.json", env)
            self.assertEqual(loaded["arms"]["A1-gpu"]["settings"]["device"], "0")
            self.assertEqual(loaded["vram"]["limit_bytes"], 12_000_000_000)
            self.assertTrue(loaded["vram"]["required"])
            with self.assertRaisesRegex(host_run.Refusal, "NARRATE_BENCH_QWEN_DEVICE"):
                host_run.load_job(BENCH / "host-job.json", {k: v for k, v in env.items() if "QWEN_DEVICE" not in k})
            with self.assertRaisesRegex(host_run.Refusal, "voices_file: voices.json sha256"):
                host_run.load_job(BENCH / "host-job.json", dict(env, NARRATE_BENCH_VOICES_SHA256="2" * 64))


class Runner(Workspace):
    def test_qwentts_stream_splits_into_chunks_with_all_seeds(self):
        self.job_path = self.job()
        code, receipt = self.run_arm("Q")
        self.assertEqual(code, host_run.EXIT_OK, receipt["stop"])
        self.assertTrue(receipt["seed1_complete"])
        self.assertTrue(receipt["test_mode"])
        self.assertEqual([p["name"] for p in receipt["passes"]], ["smoke-icl", "seed1", "seed2", "seed3"])
        seed1 = receipt["passes"][1]
        self.assertEqual([c["chunk"] for c in seed1["chunks"]], ["s1.c01", "s1.c02", "s1.c03"])
        self.assertEqual([c["audio_s"] for c in seed1["chunks"]], [0.6, 0.5, 0.3])
        self.assertTrue(all(c["wall_s"] is not None and c["rtf"] is not None for c in seed1["chunks"]))
        self.assertIsNotNone(seed1["load_s"])
        self.assertAlmostEqual(seed1["full"]["audio_s"], 0.6 + 0.5 + 0.3 + 2 * 0.25, places=3)
        self.assertEqual(host_run.wav_seconds(self.out / "Q" / "seed1" / "s1_c02.wav"), 0.5)
        first = self.invocations()[1]
        argv = first["argv"]
        self.assertEqual(argv[argv.index("--seed") + 1], "1")
        self.assertEqual(argv[argv.index("--device") + 1], "Vulkan0")
        self.assertEqual(argv[argv.index("--ref-text") + 1], str(self.dir / "v" / "ref.txt"))
        self.assertEqual(first["env_vk"], str(self.icd))
        self.assertEqual(receipt["vram"]["card"], "card0")
        self.assertEqual(receipt["vram"]["peak_bytes"], 2 * GiB)
        self.assertGreaterEqual(receipt["smoke_vram_rise_bytes"], 256 << 20)
        self.assertNotIn(str(self.dir), json.dumps(receipt["inputs"]))
        self.assertEqual(receipt["runner_sha256"], sha(BENCH / "host_run.py"))

    def test_audiocpp_falls_back_to_the_next_variant_on_a_truncated_smoke_and_renders_the_decoy(self):
        self.job_path = self.job()
        code, receipt = self.run_arm("M", {"FAKE_SHORT_REF_TEXT": "1"})
        self.assertEqual(code, host_run.EXIT_OK, receipt["stop"])
        names = [p["name"] for p in receipt["passes"]]
        self.assertEqual(names[:3], ["smoke-ref-text", "smoke-speaker-embedding", "decoy-preset"])
        self.assertFalse(receipt["passes"][0]["plausible"])
        self.assertEqual(receipt["variant"], "speaker-embedding")
        requests = json.loads((self.out / "M" / "seed1" / "requests.json").read_text())["requests"]
        self.assertTrue(all("reference_text" not in r and r["voice_ref"] for r in requests))
        decoy = json.loads((self.out / "M" / "decoy-preset" / "requests.json").read_text())["requests"]
        expected = {
            "id": "s1_c02",
            "text": "Seven eight nine ten eleven.",
            "seed": 1,
            "options": {"voice_id": "UK_George"},
        }
        self.assertEqual(decoy, [expected])
        decoy_argv = next(i["argv"] for i in self.invocations() if "decoy-preset" in " ".join(i.get("argv", [])))
        self.assertEqual(decoy_argv[decoy_argv.index("--task") + 1], "tts")
        seed1 = next(p for p in receipt["passes"] if p["name"] == "seed1")
        self.assertTrue(seed1["complete"])
        self.assertEqual(seed1["chunks"][0]["wall_source"], "runtime")

    def test_a_changed_input_is_refused_before_any_process_starts(self):
        self.job_path = self.job()
        (self.dir / "w" / "talker.gguf").write_bytes(b"tampered")
        argv = ["run", str(self.job_path), "--arm", "Q", "--out", str(self.out), "--cache", str(self.cache)]
        self.assertEqual(host_run.main(argv), host_run.EXIT_REFUSED)
        self.assertEqual(self.invocations(), [])
        self.assertFalse((self.out / "Q").exists())

    def test_a_missing_hash_is_refused(self):
        arm = self.qwentts_arm()
        arm["inputs"]["binary"] = {"path": str(self.fake), "sha256": ""}
        self.job_path = self.job(Q=arm)
        with self.assertRaisesRegex(host_run.Refusal, "Q.binary: no declared sha256"):
            host_run.verify(host_run.load_job(self.job_path), ["Q"], self.cache)

    def test_the_verify_cache_rehashes_a_replaced_file(self):
        self.job_path = self.job()
        job = host_run.load_job(self.job_path)
        self.assertTrue(host_run.verify(job, ["Q"], self.cache)["Q.model"]["rehashed"])
        self.assertFalse(host_run.verify(job, ["Q"], self.cache)["Q.model"]["rehashed"])
        model = self.dir / "w" / "talker.gguf"
        data, st = model.read_bytes(), model.stat()
        model.unlink()
        model.write_bytes(data)  # same bytes, size and (below) mtime; a new inode and ctime
        os.utime(model, ns=(st.st_atime_ns, st.st_mtime_ns))
        self.assertTrue(host_run.verify(job, ["Q"], self.cache)["Q.model"]["rehashed"])

    def test_an_existing_arm_output_is_refused(self):
        self.job_path = self.job()
        self.run_arm("Q")
        argv = ["run", str(self.job_path), "--arm", "Q", "--out", str(self.out), "--cache", str(self.cache)]
        self.assertEqual(host_run.main(argv), host_run.EXIT_REFUSED)

    def test_qwentts_without_an_explicit_device_is_refused(self):
        arm = self.qwentts_arm()
        arm["settings"]["device"] = ""
        self.job_path = self.job(Q=arm)
        with self.assertRaisesRegex(host_run.Refusal, "explicit --device"):
            host_run.load_job(self.job_path)

    def test_budget_stop_kills_the_whole_process_group(self):
        self.job_path = self.job(Q=self.qwentts_arm(budget_s=1.5))
        code, receipt = self.run_arm("Q", {"FAKE_SLEEP_S": "5", "FAKE_FORK": "1"})
        self.assertEqual(code, host_run.EXIT_ARM_STOP)
        self.assertEqual(receipt["stop"]["rule"], "budget")
        self.assertTrue(all(p["group_gone"] for p in receipt["passes"]))
        self.assertTrue(any("helper" in r for r in self.invocations()))
        self.assertFalse(any(alive(pid) for pid in self.engine_pids()))

    def test_stall_stop(self):
        self.job_path = self.job(Q=self.qwentts_arm(stall_s=1.0))
        code, receipt = self.run_arm("Q", {"FAKE_STALL_AT": "2"})
        self.assertEqual(code, host_run.EXIT_ARM_STOP)
        self.assertEqual(receipt["stop"]["rule"], "stall")
        seed1 = next(p for p in receipt["passes"] if p["name"] == "seed1")
        self.assertEqual(seed1["outcome"], "stall")
        # qwen-tts writes a chunk's header only when the next line starts, so a stream cut before the next header
        # cannot show the last chunk was whole; it is not kept.
        self.assertEqual(seed1["chunks"], [])
        self.assertFalse(any(alive(pid) for pid in self.engine_pids()))

    def test_vram_over_the_limit_stops_the_window(self):
        self.job_path = self.job()
        code, receipt = self.run_arm("Q", {"FAKE_VRAM_BYTES": "12500000000", "FAKE_SLEEP_S": "2"})
        self.assertEqual(code, host_run.EXIT_WINDOW_STOP)
        self.assertEqual(receipt["stop"]["rule"], "vram")
        self.assertTrue(receipt["vram"]["over_limit"])
        self.assertEqual(receipt["vram"]["peak_bytes"], 12500000000)
        self.assertFalse(any(alive(pid) for pid in self.engine_pids()))

    def test_an_unreadable_vram_sample_stops_the_arm(self):
        self.job_path = self.job()
        code, receipt = self.run_arm("Q", {"FAKE_VRAM_BYTES": "unreadable", "FAKE_SLEEP_S": "2"})
        self.assertEqual(code, host_run.EXIT_ARM_STOP)
        self.assertEqual(receipt["stop"]["rule"], "vram_unreadable")
        self.assertGreater(receipt["vram"]["read_errors"], 0)

    def test_an_open_card_node_stops_the_window(self):
        self.job_path = self.job()
        env = {"FAKE_OPEN": str(self.dir / "forbidden-card1"), "FAKE_SLEEP_S": "2"}
        code, receipt = self.run_arm("Q", env)
        self.assertEqual(code, host_run.EXIT_WINDOW_STOP)
        self.assertEqual(receipt["stop"]["rule"], "card_open")
        self.assertEqual(receipt["vram"]["card_node_open"][0]["node"], str(self.dir / "forbidden-card1"))

    def test_no_vram_rise_means_no_gpu_use(self):
        self.job_path = self.job()
        code, receipt = self.run_arm("Q", {"FAKE_VRAM_BYTES": ""})
        self.assertEqual(code, host_run.EXIT_ARM_STOP)
        self.assertEqual(receipt["stop"]["rule"], "no_gpu_use")
        self.assertEqual([p["name"] for p in receipt["passes"]], ["smoke-icl"])

    def test_a_gpu_reset_in_the_kernel_log_stops_the_window(self):
        tools = self.dir / "tools"
        tools.mkdir()
        journal = tools / "journalctl"
        journal.write_text(
            "#!/bin/sh\n"
            'case " $* " in *" -o cat "*) ;; *) echo "host names must not be read" >&2; exit 1 ;; esac\n'
            'case " $* " in *" --since "*) echo "amdgpu 0000:03:00.0: amdgpu: GPU reset begin!" ;; esac\n'
        )
        journal.chmod(0o755)
        self.job_path = self.job()
        code, receipt = self.run_arm("Q", {"PATH": f"{tools}{os.pathsep}{os.environ['PATH']}"})
        self.assertEqual(code, host_run.EXIT_WINDOW_STOP)
        self.assertEqual(receipt["stop"]["rule"], "gpu_reset")
        self.assertEqual(receipt["kernel_log_probe"], {"status": "readable"})

    def test_card_selection_reads_amdgpu_cards_only(self):
        card, path = host_run.find_card(self.dir / "drm")
        self.assertEqual((card, Path(path).name), ("card0", "mem_info_vram_used"))
        os.unlink(self.dir / "drm" / "card0" / "device" / "driver")
        os.makedirs(self.dir / "drivers" / "i915")
        os.symlink(self.dir / "drivers" / "i915", self.dir / "drm" / "card0" / "device" / "driver")
        self.assertEqual(host_run.find_card(self.dir / "drm"), (None, None))


class Signals(Workspace):
    """The runner as its own process: a signal or its death leaves no engine behind."""

    def start(self, extra_env):
        self.job_path = self.job(Q=self.qwentts_arm(budget_s=120))
        env = dict(os.environ, FAKE_SLEEP_S="30", FAKE_FORK="1", **extra_env)
        argv = [sys.executable, str(BENCH / "host_run.py"), "run", str(self.job_path), "--arm", "Q"]
        argv += ["--out", str(self.out), "--cache", str(self.cache)]
        proc = subprocess.Popen(argv, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        self.assertTrue(wait_for(lambda: any("helper" in r for r in self.invocations()), 20), "engine never forked")
        return proc

    def check_signal(self, sig):
        proc = self.start({})
        proc.send_signal(sig)
        self.assertEqual(proc.wait(timeout=30), host_run.EXIT_WINDOW_STOP)
        receipt = json.loads((self.out / "Q" / "receipt.json").read_text())
        self.assertEqual(receipt["stop"]["rule"], "terminated")
        self.assertTrue(wait_for(lambda: not any(alive(pid) for pid in self.engine_pids()), 5))

    def test_sighup_stops_the_arm_and_its_whole_engine_group(self):
        self.check_signal(signal.SIGHUP)

    def test_sigterm_stops_the_arm_and_its_whole_engine_group(self):
        self.check_signal(signal.SIGTERM)

    def test_a_killed_runner_takes_its_engine_with_it(self):
        proc = self.start({})
        engine = next(r["pid"] for r in self.invocations() if "pid" in r)
        proc.kill()
        proc.wait(timeout=10)
        self.assertTrue(wait_for(lambda: not alive(engine), 5), "PR_SET_PDEATHSIG did not stop the engine")


class Window(Workspace):
    """run-bench.sh in test mode; its scope is either skipped (NO_SCOPE) or faked by a systemd-run on PATH."""

    def setUp(self):
        super().setUp()
        if not shutil.which("ionice") or not shutil.which("bash") or not shutil.which("sha256sum"):
            self.skipTest("run-bench.sh needs bash, ionice and sha256sum")
        self.bench = self.dir / "bench"
        (self.bench / "job").mkdir(parents=True)
        shutil.copy(BENCH / "run-bench.sh", self.bench / "run-bench.sh")
        shutil.copy(BENCH / "host_run.py", self.bench / "job" / "host_run.py")
        self.job_path = self.job(Q=self.qwentts_arm(), M=self.audiocpp_arm(), Q2=self.qwentts_arm())
        shutil.copy(self.job_path, self.bench / "job" / "host-job.json")
        self.base_env = dict(
            os.environ,
            NARRATE_BENCH_NO_SCOPE="1",
            NARRATE_BENCH_ARMS="Q M Q2",
            NARRATE_BENCH_PYTHON=sys.executable,
            NARRATE_BENCH_EXPECT_RUN_BENCH=sha(self.bench / "run-bench.sh"),
            NARRATE_BENCH_EXPECT_HOST_RUN=sha(self.bench / "job" / "host_run.py"),
            NARRATE_BENCH_EXPECT_JOB=sha(self.bench / "job" / "host-job.json"),
        )

    def window(self, *args, env=None, **popen):
        argv = ["bash", str(self.bench / "run-bench.sh"), *args]
        return subprocess.run(argv, env=env or self.base_env, capture_output=True, text=True, timeout=120, **popen)

    def receipt(self, holder):
        return json.loads((self.bench / "runs" / holder / "receipt.json").read_text())

    def test_arms_run_in_order_then_a_window_stop_ends_the_window(self):
        done = self.window("h1")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("NARRATE-BENCH-DONE rc=0", done.stdout)
        receipt = self.receipt("h1")
        self.assertEqual([(a["arm"], a["result"]) for a in receipt["arms"]], [("Q", "0"), ("M", "0"), ("Q2", "0")])
        self.assertIsNone(receipt["stop"])
        self.assertTrue(receipt["test_mode"])
        self.assertEqual(receipt["scope"], {"test_mode_no_scope": True})
        self.assertEqual(receipt["runner"]["host_run.py"]["measured"], sha(BENCH / "host_run.py"))

        env = dict(self.base_env, FAKE_VRAM_BYTES="12500000000", FAKE_SLEEP_S="1")
        done = self.window("h2", env=env)
        self.assertEqual(done.returncode, 20, done.stderr)
        self.assertEqual([(a["arm"], a["result"]) for a in self.receipt("h2")["arms"]], [("Q", "20")])
        self.assertEqual(self.receipt("h2")["stop"], "window_stop_from_Q")

    def test_changed_inputs_refuse_the_window_with_a_receipt(self):
        (self.dir / "w" / "codec.gguf").write_bytes(b"changed")
        done = self.window("h3")
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("NARRATE-BENCH-DONE rc=2", done.stdout)
        self.assertEqual((self.receipt("h3")["stop"], self.receipt("h3")["arms"]), ("inputs_refused", []))

    def test_holder_bench_env_and_runner_hash_refusals_print_done(self):
        done = self.window()
        self.assertEqual(done.returncode, 2)
        self.assertIn("usage: run-bench.sh HOLDER", done.stderr)
        self.assertIn("NARRATE-BENCH-DONE rc=2", done.stdout)
        self.assertEqual(self.window("bad holder").returncode, 2)

        (self.bench / "bench.env").write_text("NARRATE_BENCH_TEST_MODE=1\n")
        done = self.window("h4")
        self.assertEqual(done.returncode, 2)
        self.assertIn("not an allowed key", done.stderr)
        (self.bench / "bench.env").write_text("export NARRATE_BENCH_QWEN_DEVICE=Vulkan0\n")

        env = dict(self.base_env, NARRATE_BENCH_EXPECT_HOST_RUN="0" * 64)
        done = self.window("h5", env=env)
        self.assertEqual(done.returncode, 2)
        self.assertIn("NARRATE_BENCH_EXPECT_", done.stderr)
        self.assertFalse((self.bench / "runs" / "h5").exists())

        self.assertEqual(self.window("h6").returncode, 0)
        done = self.window("h6")
        self.assertEqual(done.returncode, 2)
        self.assertIn("already exists", done.stderr)

    def fake_systemd_run(self, body):
        tools = self.dir / "tools"
        tools.mkdir(exist_ok=True)
        script = tools / "systemd-run"
        script.write_text("#!/bin/sh\n" + body)
        script.chmod(0o755)
        return dict(self.base_env, PATH=f"{tools}{os.pathsep}{os.environ['PATH']}")

    def test_test_settings_are_ignored_without_test_mode_and_a_failed_scope_still_reports(self):
        env = self.fake_systemd_run('echo "$*" > "$(dirname "$0")/called"; exit 1\n')
        del env["NARRATE_BENCH_TEST_MODE"]  # NO_SCOPE alone must not skip the scope
        done = self.window("h7", env=env)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("NARRATE-BENCH-DONE rc=2", done.stdout)
        called = (self.dir / "tools" / "called").read_text()
        for prop in ("MemoryMax=14G", "MemorySwapMax=0", "CPUQuota=200%", "RuntimeMaxSec=1680"):
            self.assertIn(prop, called)
        receipt = self.receipt("h7")
        self.assertEqual((receipt["stop"], receipt["exit_code"], receipt["test_mode"]), ("scope_failed", 2, False))

    def test_a_process_outside_the_requested_scope_is_refused(self):
        # A systemd-run that drops the properties and runs the command in place: the cgroup is not the unit's.
        env = self.fake_systemd_run('while [ "$1" != nice ]; do shift; done\nexec "$@"\n')
        del env["NARRATE_BENCH_NO_SCOPE"]
        done = self.window("h8", env=env)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertEqual(self.receipt("h8")["stop"], "scope_unverified")
        self.assertEqual(self.receipt("h8")["arms"], [])

    def test_sighup_to_the_window_stops_it_and_leaves_nothing(self):
        env = dict(self.base_env, FAKE_SLEEP_S="30", FAKE_FORK="1")
        argv = ["bash", str(self.bench / "run-bench.sh"), "h9"]
        proc = subprocess.Popen(
            argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True
        )
        self.addCleanup(lambda: proc.poll() is None and os.killpg(proc.pid, signal.SIGKILL))
        self.assertTrue(wait_for(lambda: any("helper" in r for r in self.invocations()), 30), "engine never forked")
        os.killpg(proc.pid, signal.SIGHUP)  # a hangup reaches the whole foreground group
        out, err = proc.communicate(timeout=60)
        self.assertEqual(proc.returncode, 20, err)
        self.assertIn("NARRATE-BENCH-DONE rc=20", out)
        self.assertEqual(self.receipt("h9")["stop"], "terminated")
        self.assertTrue(wait_for(lambda: not any(alive(pid) for pid in self.engine_pids()), 5))


class Wav(unittest.TestCase):
    def test_stream_split_ignores_a_header_lookalike_off_the_sample_grid(self):
        fake = load("narrate_bench_fake_engine", FAKE)
        header = fake.header()
        lookalike = b"\x01" + header  # odd offset inside 16-bit PCM: not a boundary
        data = header + b"\x02\x00" * 10 + lookalike + b"\x00" + header + b"\x03\x00" * 4
        markers = [(len(data), time.monotonic())]
        _fmt, _t, segments = host_run.split_stream(data, markers)
        self.assertEqual(len(segments), 2)
        self.assertEqual(len(segments[1][0]), 8)


class Score(unittest.TestCase):
    def test_score_refuses_a_destination_inside_a_git_work_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".git").mkdir()
            done = subprocess.run(
                [sys.executable, str(BENCH / "score.py"), str(Path(tmp) / "runs" / "never-created")],
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(done.returncode, 2, done.stderr)
            self.assertIn("inside a git work tree", done.stderr)
            self.assertFalse((Path(tmp) / "runs").exists())


if __name__ == "__main__":
    unittest.main()
