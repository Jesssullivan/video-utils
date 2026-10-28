"""narrate/bench/host_run.py, run-bench.sh and prepare.py: the GPU-host bench runner against a fake TTS binary.

No GPU, model, voice or network: tests/support/narrate_bench_fake_engine.py speaks qwen-tts's --stream-by-line
and audiocpp_cli's --request-sequence closely enough, a fake sysfs tree stands in for the amdgpu card's
mem_info_vram_used, a temporary file stands in for a card node, and the voice registry is a synthetic fixture.
Covered: the committed chunk list and the tracked job (no voice in it), input hash refusal before any process
starts, the qwentts stream split, the audiocpp variant fallback and decoy, the budget, stall, VRAM, unreadable
VRAM, card-node, no-GPU-use and kernel-log stops, SIGHUP, SIGTERM and SIGKILL of the runner with a forking engine
(no process left), run-bench.sh's holder, voice argument, bench.env, runner-hash, scope and signal handling, the
matched-cut arms (cut reference for the control, full clip for its native arm, identity enforced), and the scorer's
matched-cut comparison and multi-window combine.
"""

import hashlib
import importlib.util
import json
import math
import os
import shutil
import signal
import stat
import struct
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
ref_cut = load("narrate_bench_ref_cut", BENCH / "ref_cut.py")
score = load("narrate_bench_score", BENCH / "score.py")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def chunk_doc(texts):
    chunks = [
        {"id": f"s1.c{i:02d}", "section": "s1", "text": t, "words": len(t.split()), "expected_s": 0.1 * len(t.split())}
        for i, t in enumerate(texts, 1)
    ]
    digest = hashlib.sha256(host_run.canonical(chunks).encode("utf-8")).hexdigest()
    return {"schema": "narrate-bench-chunks/1", "chunks_sha256": digest, "chunks": chunks}


def pcm_wav(path, samples, rate=16000, bits=16, extensible=False):
    """A mono integer PCM WAV of samples (floats in [-1, 1))."""
    peak = (1 << (bits - 1)) - 1
    ints = [max(-peak - 1, min(peak, round(v * peak))) for v in samples]
    pcm = b"".join(i.to_bytes(bits // 8, "little", signed=True) for i in ints)
    block = bits // 8
    fmt = struct.pack("<HHIIHH", 0xFFFE if extensible else 1, 1, rate, rate * block, block, bits)
    if extensible:  # cbSize, valid bits, channel mask, then the PCM sub-format GUID
        fmt += struct.pack("<HHI", 22, bits, 4) + bytes.fromhex("0100000000001000800000aa00389b71")
    Path(path).write_bytes(host_run.wav_bytes(fmt, pcm))
    return Path(path)


def silence_wav(path, seconds, rate=16000):
    return pcm_wav(path, [0.0] * round(seconds * rate), rate)


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
        silence_wav(d / "v" / "ref.wav", 1.0)  # a synthetic reference: one second of silence
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
            "NARRATE_RUNS_DIR": str(d / "run-records"),
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
        self.assertEqual(list(job["arms"]), ["A2-gpu-alt", "A1-gpu", "A3-gpu", "A2-gpu-alt-cut", "A1-gpu-cut"])
        self.assertEqual(job["seeds"], [1])  # window 2: seed 1 only (J83(a) addendum)
        run_bench = (BENCH / "run-bench.sh").read_text(encoding="utf-8")
        self.assertIn(f'DEFAULT_ARMS="{" ".join(job["arms"])}"', run_bench)  # the window runs the job's order
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

    def test_tracked_a3_arm_clones_from_a_cut_that_fits_the_voxcpm2_encoder(self):
        arm = json.loads((BENCH / "host-job.json").read_text(encoding="utf-8"))["arms"]["A3-gpu"]
        policy = arm["reference"]
        self.assertEqual(policy["cut"], "max14s")
        self.assertEqual(policy["encoder"], {"rate": 16000, "capacity_samples": 240000, "pad_samples": 2560})
        self.assertLessEqual(policy["max_seconds"], 238080 / 16000)  # the largest reference the encoder takes
        self.assertGreaterEqual(policy["min_seconds"], 5.0)  # the VoxCPM2 usage guide's practical minimum
        self.assertEqual([v["name"] for v in arm["variants"]], ["ultimate", "reference-only"])
        self.assertTrue(arm["variants"][0]["prompt_audio"] and arm["variants"][0]["reference_text"])
        self.assertFalse(arm["variants"][1]["reference_text"])
        host_run.check_policy("A3-gpu", policy)

    def test_tracked_cut_arms_are_their_native_arms_on_a3s_cut(self):
        arms = json.loads((BENCH / "host-job.json").read_text(encoding="utf-8"))["arms"]
        a3 = arms["A3-gpu"]["reference"]
        for cut, native in (("A2-gpu-alt-cut", "A2-gpu-alt"), ("A1-gpu-cut", "A1-gpu")):
            arm = arms[cut]
            self.assertEqual(arm["matched_cut_of"], native)
            for key in host_run.MATCHED_KEYS + ("budget_s",):
                self.assertEqual(arm[key], arms[native][key], f"{cut}.{key}")
            self.assertNotIn("reference", arms[native])  # the native arm keeps the full clip
            policy = arm["reference"]
            self.assertEqual(
                (policy["cut"], policy["max_seconds"], policy["min_seconds"]),
                (a3["cut"], a3["max_seconds"], a3["min_seconds"]),
            )
            self.assertNotIn("decoys", arm)  # decoy 2 renders once per window, inside A1-gpu
            host_run.check_matched(cut, arm, arms)
        self.assertTrue(arms["A1-gpu"]["decoys"])

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
            self.assertEqual(loaded["arms"]["A2-gpu-alt-cut"]["settings"]["device"], "Vulkan0")
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


class RefPolicy(Workspace):
    """An arm's reference policy: the cut it names, its duration and its encoder fit, all checked before any engine
    starts; prompt_audio sends the reference as the continuation prompt."""

    POLICY = {"max_seconds": 14.5, "min_seconds": 5.0, "encoder": {"rate": 16000, "capacity_samples": 240000,
                                                                    "pad_samples": 2560}}  # fmt: skip

    def setUp(self):
        super().setUp()
        d = self.dir
        silence_wav(d / "v" / "ref.wav", 20.0, rate=24000)  # the long consented clip
        silence_wav(d / "v" / "cut.wav", 12.0, rate=24000)
        (d / "v" / "cut.txt").write_text("A synthetic cut transcript.\n")
        self.write_voices()

    def write_voices(self, **cut):
        d = self.dir
        entry = {
            "wav": {"path": "cut.wav", "sha256": sha(d / "v" / "cut.wav")},
            "text": {"path": "cut.txt", "sha256": sha(d / "v" / "cut.txt")},
            "source_sha256": sha(d / "v" / "ref.wav"),
        }
        entry.update(cut)
        voice = {
            "wav": {"path": "ref.wav", "sha256": sha(d / "v" / "ref.wav")},
            "text": {"path": "ref.txt", "sha256": sha(d / "v" / "ref.txt")},
            "cuts": {"max14s": entry},
        }
        self.voices.write_text(json.dumps({"voices": {"fixture-voice": voice}}))

    def vox_arm(self, reference):
        arm = self.audiocpp_arm(reference=reference, decoys=[])
        arm["settings"] = {"family": "voxcpm2", "task": "clon", "options": {}}
        arm["variants"] = [
            {"name": "ultimate", "reference_text": True, "prompt_audio": True},
            {"name": "reference-only", "reference_text": False},
        ]
        return arm

    def verify(self, arms):
        job = host_run.load_job(self.job_path)
        return host_run.verify(job, arms, self.cache)

    def test_an_oversized_reference_is_refused_before_any_engine_starts(self):
        self.job_path = self.job(V=self.vox_arm(dict(self.POLICY)))  # no cut: the 20 s clip itself
        with self.assertRaises(host_run.Refusal) as caught:
            self.verify(["V"])
        message = str(caught.exception)
        self.assertIn("lasts 20.00 s, over the arm's max_seconds 14.5", message)
        self.assertIn("needs 320000 encoder samples at 16000 Hz, over the capacity 240000", message)
        argv = ["run", str(self.job_path), "--arm", "V", "--out", str(self.out), "--cache", str(self.cache)]
        self.assertEqual(host_run.main(argv), host_run.EXIT_REFUSED)
        self.assertEqual(self.invocations(), [])
        self.assertFalse((self.out / "V").exists())

    def test_the_named_cut_is_hashed_checked_and_sent_as_reference_and_prompt(self):
        # the cut's transcript ends on a bare word, as a cut ending mid-phrase does
        (self.dir / "v" / "cut.txt").write_text("A synthetic cut transcript  ending\non a bare word\n")
        self.write_voices()
        self.job_path = self.job(V=self.vox_arm(dict(self.POLICY, cut="max14s")))
        records = self.verify(["V"])
        self.assertEqual(records["voice.max14s.wav"]["file"], "cut.wav")
        self.assertNotIn("voice.wav", records)  # the arm never reads the long clip
        check = records["V.reference"]
        self.assertTrue(check["fits"])
        self.assertEqual((check["seconds"], check["rate"]), (12.0, 24000))
        self.assertEqual(check["encoder"]["resampled_samples"], 192000)
        self.assertEqual(check["encoder"]["padded_samples"], 192000)
        code, receipt = self.run_arm("V")
        self.assertEqual(code, host_run.EXIT_OK, receipt["stop"])
        self.assertEqual(receipt["variant"], "ultimate")
        self.assertEqual(
            receipt["reference"],
            {
                "label": "voice.max14s",
                "wav_sha256": sha(self.dir / "v" / "cut.wav"),
                "text_sha256": sha(self.dir / "v" / "cut.txt"),
                "voice_clip_sha256": sha(self.dir / "v" / "ref.wav"),
            },
        )
        self.assertTrue(receipt["inputs"]["V.reference"]["fits"])
        requests = json.loads((self.out / "V" / "seed1" / "requests.json").read_text())["requests"]
        cut = str(self.dir / "v" / "cut.wav")
        self.assertTrue(all(r["voice_ref"] == cut and r["audio"] == cut for r in requests))
        # the pin builds prompt_text + target_text with no separator: the prompt ends with one space
        prompt = "A synthetic cut transcript ending on a bare word "
        self.assertTrue(all(r["reference_text"] == prompt for r in requests))
        texts = json.loads((self.out / "V" / "seed1" / "model-text.json").read_text())["texts"]
        self.assertEqual(texts, {r["id"]: prompt + " ".join(r["text"].split()) for r in requests})
        self.assertTrue(all(" word " + r["text"].split()[0] in texts[r["id"]] for r in requests))

    def test_the_reference_only_variant_sends_no_prompt_and_no_transcript(self):
        arm = self.vox_arm(dict(self.POLICY, cut="max14s"))
        arm["variants"] = [arm["variants"][1]]
        self.job_path = self.job(V=arm)
        code, receipt = self.run_arm("V")
        self.assertEqual(code, host_run.EXIT_OK, receipt["stop"])
        requests = json.loads((self.out / "V" / "seed1" / "requests.json").read_text())["requests"]
        self.assertTrue(all("audio" not in r and "reference_text" not in r for r in requests))
        texts = json.loads((self.out / "V" / "seed1" / "model-text.json").read_text())["texts"]
        self.assertEqual(texts, {r["id"]: r["text"] for r in requests})

    def test_ming_model_text_records_the_transcript_running_into_the_chunk(self):
        # Ming tokenizes reference_text and the trimmed chunk text as two pieces with no separator; the request is
        # left as it is, and model-text.json records the joined text and whether the transcript ends bare
        self.job_path = self.job(M=self.audiocpp_arm(decoys=[]))
        code, receipt = self.run_arm("M")
        self.assertEqual(code, host_run.EXIT_OK, receipt["stop"])
        requests = json.loads((self.out / "M" / "seed1" / "requests.json").read_text())["requests"]
        transcript = "A synthetic reference transcript."
        self.assertTrue(all(r["reference_text"] == transcript and "audio" not in r for r in requests))
        record = json.loads((self.out / "M" / "seed1" / "model-text.json").read_text())
        self.assertEqual(record["family"], "ming3_tts")
        self.assertIn("no separator", record["composed_as"])
        self.assertIs(record["reference_ends_bare"], False)  # the fixture transcript ends with "."
        self.assertEqual(record["texts"], {r["id"]: transcript + r["text"].strip() for r in requests})
        bare = {"id": "x", "text": " Next words\n", "voice_ref": "r.wav", "reference_text": "ends on a word"}
        self.assertEqual(host_run.composed_text("ming3_tts", bare), "ends on a wordNext words")
        self.assertEqual(host_run.composed_text("ming3_tts", {"id": "x", "text": " Preset "}), "Preset")
        self.assertIsNone(host_run.composed_text("other", bare))

    def test_a_cut_must_exist_and_name_the_voice_clip_as_its_source(self):
        self.job_path = self.job(V=self.vox_arm(dict(self.POLICY, cut="other")))
        with self.assertRaisesRegex(host_run.Refusal, "no reference cut 'other'"):
            self.verify(["V"])
        self.write_voices(source_sha256="0" * 64)
        self.job_path = self.job(V=self.vox_arm(dict(self.POLICY, cut="max14s")))
        with self.assertRaisesRegex(host_run.Refusal, "does not name the voice clip's sha256 as its source"):
            self.verify(["V"])

    def test_encoder_capacity_is_checked_to_the_sample_and_a_short_cut_is_refused(self):
        policy = {"cut": "max14s", "max_seconds": 15.0, "encoder": dict(self.POLICY["encoder"])}
        for frames, fits in ((238080, True), (238081, False)):
            pcm_wav(self.dir / "v" / "cut.wav", [0.0] * frames, rate=16000)
            self.write_voices()
            self.job_path = self.job(V=self.vox_arm(policy))
            if fits:
                self.assertEqual(self.verify(["V"])["V.reference"]["encoder"]["padded_samples"], 238080)
            else:
                with self.assertRaisesRegex(host_run.Refusal, "needs 240640 encoder samples"):
                    self.verify(["V"])
        # 44.1 kHz: 656208 frames resample to exactly 238080 samples; one frame more rounds up to 238081, which
        # pads to 240640 (a floor would keep 238080 and wrongly pass)
        for frames, fits in ((656208, True), (656209, False)):
            pcm_wav(self.dir / "v" / "cut.wav", [0.0] * frames, rate=44100)
            self.write_voices()
            self.job_path = self.job(V=self.vox_arm(policy))
            if fits:
                encoder = self.verify(["V"])["V.reference"]["encoder"]
                self.assertEqual((encoder["resampled_samples"], encoder["padded_samples"]), (238080, 238080))
            else:
                with self.assertRaisesRegex(host_run.Refusal, "needs 240640 encoder samples"):
                    self.verify(["V"])
        silence_wav(self.dir / "v" / "cut.wav", 3.0)
        self.write_voices()
        self.job_path = self.job(V=self.vox_arm(dict(self.POLICY, cut="max14s")))
        with self.assertRaisesRegex(host_run.Refusal, "under the arm's min_seconds 5.0"):
            self.verify(["V"])

    def test_a_matched_cut_arm_clones_from_the_cut_and_its_native_arm_from_the_full_clip(self):
        cut_policy = {"cut": "max14s", "max_seconds": 14.5, "min_seconds": 5.0}
        self.job_path = self.job(Q=self.qwentts_arm(), Qc=self.qwentts_arm(matched_cut_of="Q", reference=cut_policy))
        records = self.verify(["Q", "Qc"])
        self.assertEqual(records["voice.wav"]["file"], "ref.wav")
        self.assertEqual(records["voice.max14s.wav"]["file"], "cut.wav")
        self.assertTrue(records["Qc.reference"]["fits"])
        self.assertNotIn("Q.reference", records)
        for arm, wav, text in (("Q", "ref.wav", "ref.txt"), ("Qc", "cut.wav", "cut.txt")):
            before = len(self.invocations())
            code, receipt = self.run_arm(arm)
            self.assertEqual(code, host_run.EXIT_OK, receipt["stop"])
            self.assertEqual(receipt["passes"][-1]["name"], "seed3")
            argv = self.invocations()[before]["argv"]
            self.assertEqual(argv[argv.index("--ref-wav") + 1], str(self.dir / "v" / wav))
            self.assertEqual(argv[argv.index("--ref-text") + 1], str(self.dir / "v" / text))
            self.assertEqual(receipt["reference"]["wav_sha256"], sha(self.dir / "v" / wav))
            self.assertEqual(receipt["reference"]["voice_clip_sha256"], sha(self.dir / "v" / "ref.wav"))
            self.assertEqual(receipt["matched_cut_of"], "Q" if arm == "Qc" else None)

    def test_a_matched_cut_arm_must_differ_from_its_native_arm_only_in_the_reference(self):
        cut_policy = {"cut": "max14s", "max_seconds": 14.5}
        other = [{"name": "x-vector", "reference_text": False}]
        bad = [
            ("must name another arm", dict(matched_cut_of="Nope", reference=cut_policy)),
            ("must name another arm", dict(matched_cut_of="Qc", reference=cut_policy)),
            ("policy that names a cut", dict(matched_cut_of="Q")),
            ("differs from Q in settings;", dict(matched_cut_of="Q", reference=cut_policy, settings={"device": "V1"})),
            ("differs from Q in variants;", dict(matched_cut_of="Q", reference=cut_policy, variants=other)),
        ]  # fmt: skip
        for message, extra in bad:
            self.job_path = self.job(Q=self.qwentts_arm(), Qc=self.qwentts_arm(**extra))
            with self.assertRaisesRegex(host_run.Refusal, message):
                host_run.load_job(self.job_path)
        self.job_path = self.job(
            Q=self.qwentts_arm(reference=cut_policy), Qc=self.qwentts_arm(matched_cut_of="Q", reference=cut_policy)
        )
        with self.assertRaisesRegex(host_run.Refusal, "does not clone from the full clip"):
            host_run.load_job(self.job_path)
        # budget, decoys and about text may differ
        native = self.audiocpp_arm()
        control = self.audiocpp_arm(matched_cut_of="M", reference=cut_policy, budget_s=30, about="control")
        del control["decoys"]
        self.job_path = self.job(M=native, Mc=control)
        host_run.load_job(self.job_path)

    def test_malformed_policies_and_prompt_audio_without_its_transcript_are_refused(self):
        for bad in ({"max_seconds": -1}, {"cut": "a/b"}, {"encoder": {"rate": 16000}}, "14s",
                    {"min_seconds": 9, "max_seconds": 8}):  # fmt: skip
            self.job_path = self.job(V=self.vox_arm(bad))
            with self.assertRaises(host_run.Refusal):
                host_run.load_job(self.job_path)
        arm = self.vox_arm(dict(self.POLICY, cut="max14s"))
        arm["variants"] = [{"name": "prompt-without-text", "reference_text": False, "prompt_audio": True}]
        self.job_path = self.job(V=arm)
        with self.assertRaisesRegex(host_run.Refusal, "prompt_audio"):
            host_run.load_job(self.job_path)
        self.job_path = self.job(Q=self.qwentts_arm(variants=[{"name": "icl", "prompt_audio": True}]))
        with self.assertRaisesRegex(host_run.Refusal, "prompt_audio"):
            host_run.load_job(self.job_path)


class RefCut(unittest.TestCase):
    """narrate/bench/ref_cut.py on a synthetic clip: tone-burst words, short gaps between words and long ones
    between sentences, and word timings standing in for whisper's."""

    RATE = 16000
    SENTENCES = [["alpha", "bravo", "charlie."], ["delta", "echo", "foxtrot", "golf."], ["hotel", "india."],
                 ["juliet", "kilo", "lima", "mike."]]  # fmt: skip

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="narrate-ref-cut-"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        samples, words, t = [], [], 0.0

        def add(seconds, tone):
            n = round(seconds * self.RATE)
            start = len(samples)
            samples.extend(
                (0.4 * math.sin(2 * math.pi * 220 * (start + k) / self.RATE)) if tone else 0.0005 * ((k % 7) - 3)
                for k in range(n)
            )
            return seconds

        t += add(0.5, False)
        for sentence in self.SENTENCES:
            for k, word in enumerate(sentence):
                words.append({"start": round(t + 0.01, 3), "end": round(t + 0.39, 3), "word": word.capitalize()})
                t += add(0.4, True)
                t += add(0.15 if k + 1 < len(sentence) else 0.6, False)
        self.tokens = [w for s in self.SENTENCES for w in s]
        self.clip = pcm_wav(self.dir / "clip.wav", samples, self.RATE, bits=24, extensible=True)
        self.text = self.dir / "clip.txt"
        self.text.write_text(" ".join(self.tokens) + "\n")
        self.words = self.dir / "clip.words.json"
        self.words.write_text(json.dumps({"clip_sha256": sha(self.clip), "words": words}))
        self.duration = t

    def cut(self, *extra, out=None):
        out = out or self.dir / "out"
        out.mkdir(exist_ok=True)
        argv = ["cut", str(self.clip), str(self.text), "--words", str(self.words), *extra]
        argv += [
            "--out-wav",
            str(out / "cut.wav"),
            "--out-text",
            str(out / "cut.txt"),
            "--record",
            str(out / "cut.json"),
        ]
        with mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            code = ref_cut.main(argv)
        record = json.loads((out / "cut.json").read_text()) if (out / "cut.json").exists() else None
        return code, record, out

    def test_the_longest_cut_between_sentence_boundaries_is_a_byte_identical_slice(self):
        code, record, out = self.cut("--max-s", "5.5", "--min-s", "2", "--capacity-samples", "240000",
                                     "--pad-samples", "2560")  # fmt: skip
        self.assertEqual(code, 0)
        cut = record["cut"]
        self.assertEqual((cut["start_boundary"], cut["end_boundary"]), ("sentence", "sentence"))
        self.assertLessEqual(cut["seconds"], 5.5)
        i, j = cut["word_range"]
        self.assertEqual((i, j), (0, 6))  # alpha .. golf.: the longest run of whole sentences under 5.5 s
        self.assertEqual((out / "cut.txt").read_text(), " ".join(self.tokens[i : j + 1]) + "\n")
        source, copy = ref_cut.read_wav(self.clip), ref_cut.read_wav(out / "cut.wav")
        a, b = cut["start_frame"] * source["block"], cut["end_frame"] * source["block"]
        self.assertEqual(copy["pcm"], source["pcm"][a:b])
        self.assertEqual(copy["fmt"], source["fmt"])  # 24-bit extensible kept as it was
        self.assertLessEqual(cut["start_dbfs"], cut["floor_dbfs"] + ref_cut.QUIET_DB)
        self.assertTrue(cut["encoder"]["fits"])
        self.assertEqual(record["outputs"]["wav"]["sha256"], sha(out / "cut.wav"))
        dumped = json.dumps(record).lower()
        self.assertFalse(any(word.strip(".") in dumped for word in self.tokens))  # no transcript in the record

    def test_without_a_whole_sentence_under_the_limit_it_cuts_at_word_gaps_and_refuses_the_impossible(self):
        code, record, _ = self.cut("--max-s", "1.2")
        self.assertEqual(code, 0)
        self.assertLessEqual(record["cut"]["seconds"], 1.2)
        self.assertEqual(record["cut"]["end_boundary"], "sentence")  # a sentence end still outranks a word gap
        code, record, out = self.cut("--max-s", "30", "--min-s", "20", "--force", out=self.dir / "fresh")
        self.assertEqual((code, record), (2, None))
        self.assertEqual(list(out.iterdir()), [])  # a refused cut writes nothing

    def test_a_cut_refused_after_writing_leaves_the_earlier_outputs_as_they_were(self):
        code, _, out = self.cut("--max-s", "1.2")
        self.assertEqual(code, 0)
        before = {p.name: p.read_bytes() for p in out.iterdir()}
        real = ref_cut.read_wav

        def tampered(path):
            info = real(path)
            if Path(path).name.endswith(".tmp"):
                info["pcm"] = info["pcm"][:-2]  # the read-back differs from what was cut
            return info

        with mock.patch.object(ref_cut, "read_wav", tampered):
            code, _, out = self.cut("--max-s", "5.5", "--min-s", "2", "--force")
        self.assertEqual(code, 2)
        self.assertEqual({p.name: p.read_bytes() for p in out.iterdir()}, before)  # no temporary file left either

    def test_a_cut_needs_whisper_to_have_heard_no_more_than_the_transcript_inside_it(self):
        info = ref_cut.read_wav(self.clip)
        words = json.loads(self.words.read_text())["words"]
        # whisper heard two words between "delta" and "echo" that the transcript lacks
        k = next(n for n, w in enumerate(words) if w["word"] == "Delta")
        gap = (words[k]["end"], words[k + 1]["start"])
        extra = [{"start": gap[0] + 0.01, "end": gap[0] + 0.05, "word": "um"},
                 {"start": gap[0] + 0.06, "end": gap[1] - 0.01, "word": "uh"}]  # fmt: skip
        heard = words[: k + 1] + extra + words[k + 1 :]
        chosen = ref_cut.plan(info, self.tokens, words, 5.5, 2)
        self.assertEqual(tuple(chosen["word_range"]), (0, 6))  # alpha .. golf. without the extra words
        for max_s in (2.5, 4.0, 5.5):
            chosen = ref_cut.plan(info, self.tokens, heard, max_s, 1.0)
            i, j = chosen["word_range"]
            self.assertTrue(j < 3 or i > 6, (max_s, i, j))  # no cut keeps sentence two
            self.assertEqual((chosen["matched_ratio"], chosen["heard_ratio"]), (1.0, 1.0))

    def test_encoder_fit_rounds_the_resampled_length_up_at_44100_hz(self):
        encoder = {"rate": 16000, "capacity_samples": 240000, "pad_samples": 2560}
        fit = ref_cut.encoder_fit(656208, 44100, encoder)
        self.assertEqual((fit["resampled_samples"], fit["padded_samples"], fit["fits"]), (238080, 238080, True))
        fit = ref_cut.encoder_fit(656209, 44100, encoder)
        self.assertEqual((fit["resampled_samples"], fit["padded_samples"], fit["fits"]), (238081, 240640, False))

    def test_no_cut_starts_or_ends_beside_a_word_whisper_did_not_hear(self):
        info = ref_cut.read_wav(self.clip)
        words = json.loads(self.words.read_text())["words"]
        missed = [w for w in words if w["word"] != "Delta"]  # whisper missed the first word of sentence two
        for max_s in (1.6, 2.2, 3.0, 4.5, 6.0):
            chosen = ref_cut.plan(info, self.tokens, missed, max_s, 0.5)
            i, j = chosen["word_range"]
            self.assertNotEqual(i, 4, max_s)  # "echo" follows the unheard word: its gap is not trusted
            self.assertNotEqual(j, 2, max_s)  # nor is the gap after "charlie."
        self.assertEqual(ref_cut.kind_after(["one,", "two;", "three.", "four"], 0), "clause")
        self.assertEqual([ref_cut.kind_after(["a,", "b?", "c"], k) for k in range(3)], ["clause", "sentence", "word"])

    def test_word_timings_from_another_clip_are_refused(self):
        self.words.write_text(json.dumps({"clip_sha256": "0" * 64, "words": []}))
        code, record, _ = self.cut("--max-s", "5")
        self.assertEqual((code, record), (2, None))

    def test_cgroup_limits_take_the_tightest_limit_over_the_cgroup_and_its_ancestors(self):
        root = self.dir / "cg"
        leaf = root / "user.slice" / "run-x.scope"
        leaf.mkdir(parents=True)
        (root / "user.slice" / "memory.max").write_text(f"{6 << 30}\n")
        (root / "user.slice" / "memory.swap.max").write_text("max\n")
        (leaf / "memory.max").write_text("max\n")
        (leaf / "memory.swap.max").write_text("0\n")
        proc = self.dir / "cgroup"
        proc.write_text("0::/user.slice/run-x.scope\n")
        self.assertEqual(ref_cut.cgroup_limits(root, proc), (6 << 30, 0))
        (root / "user.slice" / "memory.max").write_text("max\n")
        self.assertEqual(ref_cut.cgroup_limits(root, proc), (None, 0))
        self.assertEqual(ref_cut.cgroup_limits(root, self.dir / "missing"), (None, None))

    def test_24_bit_samples_decode_with_their_sign(self):
        path = pcm_wav(self.dir / "s24.wav", [-1.0, -0.5, 0.0, 0.5], 16000, bits=24, extensible=True)
        values = ref_cut.mono_samples(ref_cut.read_wav(path))
        self.assertEqual([round(v, 3) for v in values], [-1.0, -0.5, 0.0, 0.5])

    def test_words_runs_whisper_with_dtw_at_four_threads_at_most(self):
        bin_dir = self.dir / "bin"
        bin_dir.mkdir()
        (bin_dir / "ffmpeg").write_text('#!/bin/sh\nfor last; do :; done\ncp "$5" "$last"\n')
        full = {"transcription": [{"text": " Alpha bravo.", "offsets": {"from": 500, "to": 1300}, "tokens": [
            {"text": " Alpha", "offsets": {"from": 500, "to": 900}, "t_dtw": 51},
            {"text": " bravo", "offsets": {"from": 900, "to": 1250}, "t_dtw": 95},
            {"text": ".", "offsets": {"from": 1250, "to": 1300}, "t_dtw": 125}]}]}  # fmt: skip
        script = '#!/bin/sh\necho "$@" > "$FAKE_ARGS"\nwhile [ $# -gt 0 ]; do [ "$1" = -of ] && of=$2; shift; done\n'
        script += f"cat > \"$of.json\" <<'EOF'\n{json.dumps(full)}\nEOF\n"
        (bin_dir / "whisper-cli").write_text(script)
        for tool in ("ffmpeg", "whisper-cli"):
            (bin_dir / tool).chmod(0o755)
        model = self.dir / "model.bin"
        model.write_bytes(b"model")
        models = self.dir / "models.json"
        models.write_text(json.dumps({"models": {ref_cut.WHISPER_MODEL_ID: {"sha256": sha(model)}}}))
        out = self.dir / "w.json"
        env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_ARGS": str(self.dir / "args")}
        argv = ["words", str(self.clip), "--out", str(out), "--model", str(model), "--threads", "16"]
        scoped = mock.patch.object(ref_cut, "cgroup_limits", return_value=(6 << 30, 0))
        with mock.patch.dict(os.environ, env), mock.patch("sys.stdout"), mock.patch("sys.stderr"):
            with mock.patch.object(ref_cut, "MODELS", models), scoped:
                (self.dir / "other.bin").write_bytes(b"another model")
                other = ["words", str(self.clip), "--out", str(out), "--model", str(self.dir / "other.bin")]
                self.assertEqual(ref_cut.main(other), 2)  # not the registered small.en
            with mock.patch.object(ref_cut, "MODELS", models):
                for limits in ((None, None), (8 << 30, 0), (6 << 30, None)):
                    with mock.patch.object(ref_cut, "cgroup_limits", return_value=limits):
                        self.assertEqual(ref_cut.main(argv), 2, limits)  # no memory scope, too large, or swap on
            self.assertFalse((self.dir / "args").exists() or out.exists())  # whisper never started
            with mock.patch.object(ref_cut, "MODELS", models), scoped:
                self.assertEqual(ref_cut.main(argv), 0)
        doc = json.loads(out.read_text())
        self.assertEqual([w["word"] for w in doc["words"]], ["Alpha", "bravo."])
        self.assertEqual(doc["clip_sha256"], sha(self.clip))
        self.assertEqual(doc["whisper"]["threads"], 4)
        self.assertEqual(doc["whisper"]["model_sha256"], sha(model))
        self.assertEqual(doc["whisper"]["scope"], {"memory_max": 6 << 30, "memory_swap_max": 0})
        args = (self.dir / "args").read_text().split()
        self.assertEqual(args[args.index("-t") + 1], "4")
        self.assertEqual(args[args.index("-dtw") + 1], "small.en")


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
        record = json.loads((self.dir / "run-records" / "bench-h1.json").read_text())
        self.assertEqual((record["kind"], record["lease_holder"]), ("bench-window", "h1"))
        self.assertEqual((record["state"], record["exit_status"], record["test_mode"]), ("ended", 0, True))

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

    def test_preflight_refuses_an_oversized_reference_before_the_lease_and_writes_no_run(self):
        done = self.window("--preflight")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("NARRATE-BENCH-PREFLIGHT rc=0", done.stdout)
        self.assertFalse((self.bench / "runs").exists())
        # preflight keeps its own hash cache: the window's verify still hashes every input itself
        self.assertTrue((self.bench / "preflight-verified.json").is_file())
        self.assertFalse((self.bench / "inputs-verified.json").exists())
        arm = self.audiocpp_arm(reference={"max_seconds": 0.5})  # the 1 s fixture reference is too long
        job = self.job(Q=self.qwentts_arm(), M=arm, Q2=self.qwentts_arm())
        shutil.copy(job, self.bench / "job" / "host-job.json")
        env = dict(self.base_env, NARRATE_BENCH_EXPECT_JOB=sha(self.bench / "job" / "host-job.json"))
        done = self.window("--preflight", env=env)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("NARRATE-BENCH-PREFLIGHT rc=2", done.stdout)
        self.assertIn("over the arm's max_seconds 0.5", done.stderr)
        self.assertFalse((self.bench / "runs").exists())
        self.assertEqual(self.invocations(), [])
        done = self.window("--preflight", env=dict(env, NARRATE_BENCH_EXPECT_JOB="0" * 64))
        self.assertEqual(done.returncode, 2)
        self.assertIn("runner file's sha256", done.stderr)

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

    def test_the_voice_argument_names_the_window_voice(self):
        d = self.dir
        silence_wav(d / "v" / "other.wav", 1.5)
        (d / "v" / "other.txt").write_text("Another synthetic transcript.\n")
        voices = json.loads(self.voices.read_text())
        voices["voices"]["other-voice"] = {
            "wav": {"path": "other.wav", "sha256": sha(d / "v" / "other.wav")},
            "text": {"path": "other.txt", "sha256": sha(d / "v" / "other.txt")},
        }
        self.voices.write_text(json.dumps(voices))
        job = json.loads(self.job(Q=self.qwentts_arm()).read_text())
        job["voice"] = "${NARRATE_BENCH_VOICE}"
        job["voices_file"] = {"path": str(self.voices), "sha256": sha(self.voices)}
        (self.bench / "job" / "host-job.json").write_text(json.dumps(job))
        (self.bench / "bench.env").write_text("NARRATE_BENCH_VOICE=fixture-voice\n")
        expect = sha(self.bench / "job" / "host-job.json")
        env = dict(self.base_env, NARRATE_BENCH_ARMS="Q", NARRATE_BENCH_EXPECT_JOB=expect)

        def cloned_from(holder):
            arm = json.loads((self.bench / "runs" / holder / "Q" / "receipt.json").read_text())
            return arm["reference"]["wav_sha256"]

        done = self.window("h10", "other-voice", env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(cloned_from("h10"), sha(d / "v" / "other.wav"))  # the argument replaces bench.env's
        self.assertIn("voice other-voice", (self.bench / "runs" / "h10" / "window.log").read_text())
        self.assertEqual(self.window("h11", env=env).returncode, 0)
        self.assertEqual(cloned_from("h11"), sha(d / "v" / "ref.wav"))  # without it, bench.env's voice
        for args, message in ((("h12", "bad voice"), "voice must be"), (("h13", "a", "b"), "usage")):
            done = self.window(*args, env=env)
            self.assertEqual(done.returncode, 2)
            self.assertIn(message, done.stderr)
            self.assertFalse((self.bench / "runs" / args[0]).exists())
        done = self.window("--preflight", "other-voice", env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("other.wav", done.stdout)
        done = self.window("--preflight", "missing-voice", env=env)
        self.assertEqual(done.returncode, 2)
        self.assertIn("not in the voices file", done.stderr)

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

    def test_finalize_stops_a_window_through_its_run_record(self):
        """J130 (TIN-7564): finalize.py sends the inner stage SIGTERM; the window stops as on a hangup."""
        finalize = load("narrate_finalize", ROOT / "narrate" / "serve" / "finalize.py")
        runs = self.dir / "run-records"
        env = dict(self.base_env, FAKE_SLEEP_S="30", FAKE_FORK="1")
        argv = ["bash", str(self.bench / "run-bench.sh"), "h14"]
        proc = subprocess.Popen(
            argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True
        )
        self.addCleanup(lambda: proc.poll() is None and os.killpg(proc.pid, signal.SIGKILL))
        self.assertTrue(wait_for(lambda: any("helper" in r for r in self.invocations()), 30), "engine never forked")
        record = json.loads((runs / "bench-h14.json").read_text())
        self.assertEqual((record["lease_holder"], record["state"]), ("h14", "running"))
        code, receipt = finalize.finalize("bench-h14", reason="operator", directory=runs)
        out, err = proc.communicate(timeout=60)
        self.assertEqual(code, 0, receipt)
        self.assertEqual(proc.returncode, 20, err)
        self.assertIn("NARRATE-BENCH-DONE rc=20", out)
        # The inner stage shares the outer stage's group, so it alone gets the signal.
        self.assertEqual([(s["signal"], s["target"]) for s in receipt["signals"]], [("SIGTERM", "process")])
        self.assertEqual((receipt["runner_exit_status"], receipt["engine_gone"]), (20, True))
        self.assertEqual(self.receipt("h14")["stop"], "terminated")
        self.assertTrue((self.bench / "runs" / "h14" / "bench-h14.finalize.json").is_file())
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
    def test_arms_conditioned_on_different_references_are_flagged(self):
        clip, cut = "a" * 64, "c" * 64
        full = {"label": "voice", "wav_sha256": clip, "text_sha256": "b" * 64, "voice_clip_sha256": clip}
        part = {"label": "voice.max14s", "wav_sha256": cut, "text_sha256": "d" * 64, "voice_clip_sha256": clip}
        self.assertEqual(score.conditioning_of({"reference": full}), full)
        self.assertEqual(score.conditioning_of({"reference": "voice.max14s"})["label"], "voice.max14s")
        self.assertIsNone(score.conditioning_of({}))
        arms = [{"arm": "A1", "conditioning": full}, {"arm": "A2", "conditioning": dict(full)}]
        self.assertEqual(
            score.compare_conditioning(arms, clip),
            {
                "equal": True,
                "flags": [],
                "groups": [
                    {"label": "voice", "wav_sha256": clip, "arms": ["A1", "A2"], "variants": {"A1": None, "A2": None}}
                ],
            },
        )
        arms.append({"arm": "A3", "conditioning": part})
        result = score.compare_conditioning(arms, clip)
        self.assertFalse(result["equal"])
        self.assertIn("unequal conditioning: voice aaaaaaaa (A1, A2); voice.max14s cccccccc (A3)", result["flags"][0])
        self.assertIn("A3: conditioned on voice.max14s, SIM against the full clip", result["flags"])
        result = score.compare_conditioning(arms + [{"arm": "A0", "conditioning": None}], "e" * 64)
        self.assertIn("conditioning reference not recorded for A0", result["flags"])
        self.assertIn("A1: the SIM reference is not the voice clip its conditioning came from", result["flags"])
        doc = {
            "arms": [dict(a, passes=[]) for a in arms],
            "wer": {"status": "not_measured"},
            "sim": {"status": "not_measured"},
            "sim_reference": {"sha256": clip, "role": score.SIM_REFERENCE_ROLE},
            "conditioning": score.compare_conditioning(arms, clip),
        }
        text = score.table(doc)
        self.assertIn("SIM reference: aaaaaaaa, the one fixed SIM reference", text)
        self.assertIn("Conditioning: unequal conditioning", text)

    CLIP, CUT = "a" * 64, "c" * 64

    def arm(self, name, label, median, wer, variant="ref-text", matched=None, met=True):
        wav = self.CLIP if label == "voice" else self.CUT
        sim = {
            "status": "measured",
            "median": median,
            "wsim": {"min": median - 0.05, "mean": median - 0.01},
            "bars": {"all_met": met, "unmet": [] if met else ["wsim_ok"]},
        }
        seed = {"pass": "seed1", "complete": True, "wer_whole": wer, "catastrophic": 0, "rtf": 0.6, "load_s": 4.0}
        smoke = dict(seed, **{"pass": "smoke-ref-text", "wer_whole": 0.9})
        cond = {"label": label, "wav_sha256": wav, "text_sha256": "b" * 64, "voice_clip_sha256": self.CLIP}
        return {"arm": name, "variant": variant, "conditioning": cond, "matched_cut_of": matched, "sim": sim,
                "passes": [smoke, seed]}  # fmt: skip

    def window_arms(self):
        return [
            self.arm("A2-gpu-alt", "voice", 0.70, 0.04),
            self.arm("A1-gpu", "voice", 0.60, 0.05, variant="speaker-embedding", met=False),
            self.arm("A3-gpu", "voice.max14s", 0.65, 0.06, variant="ultimate"),
            self.arm("A2-gpu-alt-cut", "voice.max14s", 0.66, 0.05, matched="A2-gpu-alt"),
            self.arm("A1-gpu-cut", "voice.max14s", 0.62, 0.07, matched="A1-gpu"),
        ]

    def test_matched_cut_arms_sit_beside_their_native_arms_and_the_cut_group_is_like_for_like(self):
        arms = self.window_arms()
        rows = score.matched_comparisons(arms)
        self.assertEqual([(r["cut_arm"], r["native_arm"]) for r in rows],
                         [("A1-gpu-cut", "A1-gpu"), ("A2-gpu-alt-cut", "A2-gpu-alt")])  # fmt: skip
        a2 = rows[1]
        self.assertEqual((a2["full"]["sim_median"], a2["cut"]["sim_median"]), (0.70, 0.66))
        self.assertEqual(a2["cut_minus_full"]["sim_median"], -0.04)
        self.assertEqual(a2["cut_minus_full"]["wer_whole"], 0.01)
        self.assertEqual(a2["full"]["seed_pass"], "seed1")  # the seed pass, never the smoke
        self.assertEqual((a2["full"]["conditioning"], a2["cut"]["conditioning"]), ("voice", "voice.max14s"))
        self.assertNotIn("note", a2)
        self.assertIn("variant ref-text on the cut and speaker-embedding on the full clip", rows[0]["note"])
        cond = score.compare_conditioning(arms, self.CLIP)
        self.assertEqual(
            cond["groups"],
            [
                {
                    "label": "voice",
                    "wav_sha256": self.CLIP,
                    "arms": ["A1-gpu", "A2-gpu-alt"],
                    "variants": {"A1-gpu": "speaker-embedding", "A2-gpu-alt": "ref-text"},
                },
                {
                    "label": "voice.max14s",
                    "wav_sha256": self.CUT,
                    "arms": ["A1-gpu-cut", "A2-gpu-alt-cut", "A3-gpu"],
                    "variants": {"A1-gpu-cut": "ref-text", "A2-gpu-alt-cut": "ref-text", "A3-gpu": "ultimate"},
                },
            ],
        )
        lone = score.matched_comparisons([a for a in arms if a["arm"] != "A1-gpu"])
        self.assertEqual(lone[0]["note"], "A1-gpu was not scored in this window")
        doc = {
            "arms": [dict(a, passes=[], sim=None) for a in arms],  # per-pass and per-arm lines are covered elsewhere
            "wer": {"status": "measured"},
            "sim": {"status": "not_measured", "reason": "test"},
            "sim_reference": {"sha256": self.CLIP, "role": score.SIM_REFERENCE_ROLE},
            "conditioning": cond,
            "matched": rows,
        }
        text = score.table(doc)
        group = "on voice.max14s cccccccc: A1-gpu-cut (ref-text), A2-gpu-alt-cut (ref-text), A3-gpu (ultimate)"
        self.assertIn("Like for like " + group, text)
        self.assertIn("| A2-gpu-alt-cut minus A2-gpu-alt | | | -0.040 |", text)
        self.assertIn("| A2-gpu-alt | voice aaaaaaaa | ref-text | 0.700 |", text)

    def scored_dir(self, root, holder, voice, arms, model="m" * 64, chunks=None):
        d = Path(root) / holder
        d.mkdir(parents=True)
        doc = {
            "schema": "narrate-bench-scored/1",
            "chunks_sha256": chunks or "f" * 64,
            "window": {"holder": holder, "started_utc": "2026-10-26T00:00:00Z", "voice_clip_sha256": voice},
            "sim": {"status": "measured", "model_sha256": model, "bars": {"bar": 0.45},
                    "checks": {"1-reference-self-match": {"valid": True}, "2-wrong-speaker": {"valid": True}}},
            "sim_reference": {"sha256": voice},
            "conditioning": score.compare_conditioning(arms, voice),
            "matched": score.matched_comparisons(arms),
            "arms": arms,
        }  # fmt: skip
        (d / "scored.json").write_text(json.dumps(doc))
        return d

    def test_two_windows_combine_into_one_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.scored_dir(tmp, "w2-presenter", self.CLIP, self.window_arms())
            other = [
                dict(a, conditioning=dict(a["conditioning"], voice_clip_sha256="e" * 64)) for a in self.window_arms()
            ]
            other[1] = self.arm("A1-gpu", "voice", 0.61, 0.05, variant="speaker-embedding")
            second = self.scored_dir(tmp, "w2-read", "e" * 64, other)
            dest = Path(tmp) / "combined"
            argv = [str(dest), "--combine", str(first), "--combine", str(second)]
            self.assertEqual(score.main(argv), 0)
            out = json.loads((dest / "combined.json").read_text())
            self.assertEqual([w["window"] for w in out["windows"]], ["w2-presenter", "w2-read"])
            self.assertEqual(len(out["arms"]), 10)
            self.assertEqual(len(out["matched"]), 4)
            self.assertEqual(out["per_arm"]["A1-gpu"]["bars_unmet_in"], ["w2-presenter"])
            self.assertFalse(out["per_arm"]["A1-gpu"]["bars_met_in_every_window"])
            self.assertTrue(out["per_arm"]["A3-gpu"]["bars_met_in_every_window"])
            self.assertEqual(out["flags"], [])
            text = (dest / "combined.md").read_text()
            self.assertIn("| w2-read | eeeeeeee | A3-gpu | voice.max14s cccccccc | ultimate | 0.650 |", text)
            self.assertIn("| w2-presenter | A2-gpu-alt-cut minus A2-gpu-alt |", text)
            line = "Arm A1-gpu: in 2 window(s); SIM bars met in every window False (unmet in w2-presenter)"
            self.assertIn(line, text)

            # the same voice twice, or another SIM model, is flagged; another chunk list or no scored.json refuses
            again = self.scored_dir(tmp, "w2-again", self.CLIP, self.window_arms(), model="n" * 64)
            self.assertEqual(score.main([str(Path(tmp) / "c2"), "--combine", str(first), "--combine", str(again)]), 0)
            flags = json.loads((Path(tmp) / "c2" / "combined.json").read_text())["flags"]
            self.assertIn("windows w2-presenter and w2-again share the voice clip aaaaaaaa", flags)
            self.assertIn("the windows used different SIM models or bars, so SIM is not comparable across them", flags)
            # an arm that errored in one window, or never ran there, has not met its bars in every window
            broken = [a for a in other if a["arm"] != "A1-gpu-cut"]
            broken[2] = {"arm": "A3-gpu", "error": "no receipt"}
            third = self.scored_dir(tmp, "w2-third", "9" * 64, broken)
            argv = [str(Path(tmp) / "c5"), "--combine", str(first), "--combine", str(third)]
            self.assertEqual(score.main(argv), 0)
            per_arm = json.loads((Path(tmp) / "c5" / "combined.json").read_text())["per_arm"]
            a3, a1c = per_arm["A3-gpu"], per_arm["A1-gpu-cut"]
            self.assertEqual((a3["windows"], a3["not_scored_in"]), (["w2-presenter"], ["w2-third"]))
            self.assertEqual(a1c["absent_from"], ["w2-third"])
            self.assertFalse(a3["bars_met_in_every_window"] or a1c["bars_met_in_every_window"])
            self.assertTrue(per_arm["A2-gpu-alt"]["bars_met_in_every_window"])
            text = (Path(tmp) / "c5" / "combined.md").read_text()
            met = "in 1 window(s); SIM bars met in every window False"
            self.assertIn(f"Arm A1-gpu-cut: {met} (absent from w2-third)", text)
            self.assertIn(f"Arm A3-gpu: {met} (not scored in w2-third)", text)
            odd = self.scored_dir(tmp, "w2-odd", "d" * 64, self.window_arms(), chunks="0" * 64)
            self.assertEqual(score.main([str(Path(tmp) / "c3"), "--combine", str(first), "--combine", str(odd)]), 2)
            self.assertEqual(score.main([str(Path(tmp) / "c4"), "--combine", str(Path(tmp) / "absent")]), 2)
            self.assertFalse((Path(tmp) / "c3").exists() or (Path(tmp) / "c4").exists())

    def test_a_window_of_cut_arms_only_binds_sim_to_the_clip_its_receipts_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            cut = {"label": "voice.max14s", "wav_sha256": self.CUT, "text_sha256": "b" * 64}
            receipts = [{"reference": dict(cut, voice_clip_sha256=self.CLIP)}]
            self.assertEqual(score.window_voice_sha256(tmp, receipts), self.CLIP)
            receipts.append({"reference": dict(cut, voice_clip_sha256="e" * 64)})
            self.assertIsNone(score.window_voice_sha256(tmp, receipts))  # two clips: no binding is guessed
            (Path(tmp) / "inputs.json").write_text(json.dumps({"verified": {"voice.wav": {"sha256": "9" * 64}}}))
            self.assertEqual(score.window_voice_sha256(tmp, receipts), "9" * 64)  # the verified clip wins
            ident = score.window_identity(tmp, self.CLIP)
            self.assertEqual(ident, {"holder": Path(tmp).name, "started_utc": None, "voice_clip_sha256": self.CLIP})

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
