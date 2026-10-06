"""S2 tone_ab: closed schema, identity gates, match logic, band calibration and renders.

Synthetic fixtures are stdlib-generated 22050 Hz mono 55 s WAVs in temporary
directories with fake manifest/analysis JSON. They verify mechanics only and are
never used to select parameters (docs/spec/sprints/TONE_S2.md preregistration).
FFmpeg-dependent tests skip with a reason when FFMPEG/FFPROBE do not resolve.
"""
import array
import contextlib
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import media  # noqa: E402
import tone_ab  # noqa: E402

RATE = 22050
SECONDS = 55
FRAMES = RATE * SECONDS


def ffmpeg_available():
    try:
        media.executable("ffmpeg")
        media.executable("ffprobe")
        return True
    except media.MediaError:
        return False


HAVE_FFMPEG = ffmpeg_available()
SKIP_REASON = "FFmpeg/FFprobe unavailable; export FFMPEG and FFPROBE"


def write_f32(path, samples, rate=RATE, channels=1):
    data = array.array("f", samples)
    if sys.byteorder == "big":
        data.byteswap()
    payload = data.tobytes()
    fmt = struct.pack("<HHIIHHH", 3, channels, rate, rate * channels * 4, channels * 4, 32, 0)
    body = (b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
            + b"fact" + struct.pack("<II", 4, len(data) // channels)
            + b"data" + struct.pack("<I", len(payload)) + payload)
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)


def write_s24_extensible(path, samples, rate=RATE, channels=1):
    payload = bytearray()
    for value in samples:
        clipped = max(-8388608, min(8388607, round(value * 8388608)))
        payload += clipped.to_bytes(3, "little", signed=True)
    if len(payload) & 1:
        pad = b"\x00"
    else:
        pad = b""
    guid = bytes.fromhex("0100000000001000800000aa00389b71")
    fmt = struct.pack("<HHIIHHHHI", 0xFFFE, channels, rate, rate * channels * 3, channels * 3, 24, 22, 24, 4) + guid
    body = (b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
            + b"data" + struct.pack("<I", len(payload)) + bytes(payload) + pad)
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def click_seconds():
    return [0.5 * k for k in range(1, 110)] + [54.995]


def build_signals():
    rng = random.Random(7)
    w32, w1k = 2 * math.pi * 32.703195663 / RATE, 2 * math.pi * 1000.0 / RATE
    low = [math.sin(w32 * n) for n in range(FRAMES)]
    mid = [math.sin(w1k * n) for n in range(FRAMES)]
    burst = [0.0] * FRAMES
    w3k = 2 * math.pi * 3000.0 / RATE
    for t in click_seconds():
        start = round(t * RATE)
        for i in range(min(300, FRAMES - start)):
            burst[start + i] += 0.3 * math.exp(-i / 60.0) * math.sin(w3k * i)
    noise = [rng.gauss(0.0, 0.01) for _ in range(FRAMES)]
    return {
        "source.wav": [0.30 * a + 0.20 * b + c + d for a, b, c, d in zip(low, mid, burst, noise)],
        "denoised.wav": [0.27 * a + 0.20 * b + c for a, b, c in zip(low, mid, burst)],
        "processed.wav": [0.30 * a + 0.15 * b + 0.8 * c for a, b, c in zip(low, mid, burst)],
        "cleaned.wav": [0.40 * a + 0.20 * b + 1.0 * c for a, b, c in zip(low, mid, burst)],
    }


SIGNALS = None


def make_run(directory: Path, *, analysis=True, source_sha="ab" * 32):
    global SIGNALS
    if SIGNALS is None:
        SIGNALS = build_signals()
    directory.mkdir(parents=True)
    for name, samples in SIGNALS.items():
        if name == "cleaned.wav":
            write_s24_extensible(directory / name, samples)
        else:
            write_f32(directory / name, samples)
    hashes = {name: sha(directory / name) for name in SIGNALS}
    manifest = {"schema_version": 1, "run_id": directory.name, "status": "rendered_unreviewed",
                "pcm": {"sample_rate": RATE, "channels": 1, "sample_count": FRAMES,
                        "duration_seconds": SECONDS, "codec": "pcm_f32le"},
                "outputs": {"source": "source.wav", "denoised": "denoised.wav",
                            "processed": "processed.wav", "cleaned": "cleaned.wav"},
                "output_sha256": hashes, "source": {"sha256": source_sha, "path": "synthetic"},
                "loudness": {"cleaned": {"mode": "two_pass_linear_requested"}}}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=1))
    if analysis:
        (directory / "analysis.json").write_text(json.dumps(analysis_record(hashes["denoised.wav"])))
    return manifest


def analysis_record(denoised_sha):
    clicks = [{"audio_relative_seconds": t, "beat_index": i} for i, t in enumerate(click_seconds())]
    events = ([{"kind": "superflux_attack_candidate", "audio_relative_seconds": t} for t in (2.0, 10.0, 20.25, 40.0)]
              + [{"kind": "broadband_attack_candidate", "audio_relative_seconds": 11.0}])
    return {"analysis": {"hop_seconds": 0.005, "frame_timestamp": "frame_midpoint",
                         "onset_detector_delay_seconds": None, "onset_detector_delay_status": "uncalibrated"},
            "click_grid": {"identity": "periodic_high_frequency_transients_not_verified_metronome",
                           "observed_events": clicks},
            "events": events,
            "source_lineage": {"analyzed_input_sha256": denoised_sha,
                               "sample_mapping": {"original_pcm_sample_rate": RATE,
                                                  "original_pcm_sample_count": FRAMES}}}


def args(run_dir, **extra):
    return dict({"run_dir": str(run_dir), "common_region_start": 5.0, "common_region_end": 55.0,
                 "timeout_seconds": 600}, **extra)


class FixtureBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="tone-ab-test-")
        cls.base = Path(cls.temp.name)
        cls.template = cls.base / "template-run"
        make_run(cls.template)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def fresh_run(self, name):
        target = self.base / name
        shutil.copytree(self.template, target)
        return target


class SchemaTests(unittest.TestCase):
    def test_schema_rejects_unknown_fields_bool_nonfinite(self):
        good = {"run_dir": "/x", "common_region_start": 5.0, "common_region_end": 60.0}
        self.assertEqual(tone_ab.validate_arguments(good)["timeout_seconds"], 1200)
        bad = [dict(good, output="/tmp/x"), dict(good, filter="lowshelf"),
               dict(good, common_region_start=True), dict(good, common_region_end=False),
               dict(good, common_region_start=float("nan")), dict(good, common_region_end=float("inf")),
               dict(good, common_region_start="5"), dict(good, run_dir=""), dict(good, run_dir=7),
               dict(good, run_dir="https://host/run"), dict(good, candidate_run_dir=3),
               {"run_dir": "/x", "common_region_start": 5.0}, "not-an-object"]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(tone_ab.ToneABError) as caught:
                tone_ab.validate_arguments(value)
            self.assertIn(caught.exception.code, {"invalid_arguments", "timeout_out_of_bounds"})

    def test_region_bounds_refusal(self):
        for start, end in ((4.999, 60.0), (0.0, 60.0), (60.0, 60.0), (70.0, 60.0), (5.0, 49.999)):
            with self.subTest(start=start, end=end), self.assertRaises(tone_ab.ToneABError) as caught:
                tone_ab.validate_arguments({"run_dir": "/x", "common_region_start": start,
                                            "common_region_end": end})
            self.assertEqual(caught.exception.code, "region_out_of_bounds")
        pcm = {"sample_rate": RATE, "channels": 1, "sample_count": FRAMES}
        with self.assertRaises(tone_ab.ToneABError) as caught:
            tone_ab.region_samples(5.0, 55.01, pcm)
        self.assertEqual(caught.exception.code, "region_out_of_bounds")
        region = tone_ab.region_samples(5.0, 55.0, pcm)
        self.assertEqual((region["start_sample"], region["end_sample_exclusive"]), (110250, FRAMES))
        self.assertEqual(region["frames"], FRAMES - 110250)

    def test_timeout_bounds(self):
        base = {"run_dir": "/x", "common_region_start": 5.0, "common_region_end": 60.0}
        for value in (0, 1801, -1, 1.5, 600.0, True, "60"):
            with self.subTest(value=value), self.assertRaises(tone_ab.ToneABError) as caught:
                tone_ab.validate_arguments(dict(base, timeout_seconds=value))
            self.assertEqual(caught.exception.code, "timeout_out_of_bounds")
        for value in (1, 1800):
            self.assertEqual(tone_ab.validate_arguments(dict(base, timeout_seconds=value))["timeout_seconds"], value)

    def test_descriptor_draft_closed_schema(self):
        schema = tone_ab.DESCRIPTOR_DRAFT["inputSchema"]
        self.assertEqual(set(schema["properties"]), {"run_dir", "candidate_run_dir", "common_region_start",
                                                     "common_region_end", "timeout_seconds"})
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(schema["required"], ["run_dir", "common_region_start", "common_region_end"])
        timeout = schema["properties"]["timeout_seconds"]
        self.assertEqual((timeout["minimum"], timeout["maximum"], timeout["default"]), (1, 1800, 1200))
        self.assertEqual(schema["properties"]["common_region_start"]["minimum"], 5)
        import tool_api  # root-owned registry validator; read-only use
        tool_api.validate_schema(schema)
        self.assertEqual(tone_ab.DESCRIPTOR_DRAFT["skill"], ".agents/skills/guitar-tone-ab/SKILL.md")
        self.assertTrue((ROOT / tone_ab.DESCRIPTOR_DRAFT["skill"]).is_file())
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(tone_ab.main(["describe"]), 0)
        self.assertEqual(json.loads(buffer.getvalue()), tone_ab.DESCRIPTOR_DRAFT)


class LogicTests(unittest.TestCase):
    def test_gain_iteration_converges_with_fake_meter(self):
        base = {"a": -21.0, "b": -18.0, "c": -16.5}
        calls = []

        def meter(label, gain):  # under-responds to gain so the first pass misses
            calls.append((label, gain))
            return base[label] if gain is None else base[label] + 0.8 * gain
        result = tone_ab.match_gains(list(base), meter)
        self.assertEqual(result["match_status"], "matched")
        self.assertLessEqual(result["match_lu_delta"], 0.3)
        self.assertEqual(result["target_lufs"], -21.0)
        for label, arm in result["per_arm"].items():
            self.assertLessEqual(arm["gain_db"], 0.0)
            self.assertLessEqual(arm["corrections"], 3)
            self.assertTrue(all(step["gain_db"] <= 0.0 for step in arm["iterations"]))
        self.assertGreater(result["per_arm"]["c"]["corrections"], 0)

        stuck = tone_ab.match_gains(["a", "b"], lambda label, gain: base[label] if gain is None
                                    else base[label] + 0.0 * gain)
        self.assertEqual(stuck["match_status"], "unmatched")
        self.assertIn("exceeds", stuck["reason"])
        self.assertEqual(stuck["per_arm"]["b"]["corrections"], 3)
        undefined = tone_ab.match_gains(["a", "b"], lambda label, gain: None if label == "b" else -20.0)
        self.assertEqual(undefined["match_status"], "unmatched")
        self.assertIsNone(undefined["match_lu_delta"])

    def test_rfft_power_matches_direct_dft(self):
        rng = random.Random(3)
        x = [rng.uniform(-1, 1) for _ in range(64)]
        power = tone_ab.rfft_power(x)
        for k in (0, 1, 5, 31, 32):
            direct = sum(v * complex(math.cos(2 * math.pi * k * i / 64), -math.sin(2 * math.pi * k * i / 64))
                         for i, v in enumerate(x))
            self.assertAlmostEqual(power[k], abs(direct) ** 2, places=8)

    def test_band_energy_sine_calibration(self):
        n = 4 * tone_ab.WELCH_N
        low = array.array("f", (0.5 * math.sin(2 * math.pi * 32.703 * i / RATE) for i in range(n)))
        result = tone_ab.band_energies(low, 1, RATE)
        levels = {b["band"]: b["level_dbfs_raw"] for b in result["bands"]}
        self.assertAlmostEqual(levels["20-45"], 10 * math.log10(0.125), delta=0.2)
        self.assertLessEqual(levels["400-2000"], levels["20-45"] - 30)
        self.assertEqual(result["frame_count"], 4)
        self.assertTrue(all(b["frame_count"] == 4 and b["bin_count"] > 0 for b in result["bands"]))
        high = array.array("f", (0.5 * math.sin(2 * math.pi * 1000 * i / RATE) for i in range(n)))
        bands = tone_ab.band_energies(high, 1, RATE)["bands"]
        loudest = max(bands, key=lambda b: b["level_dbfs_raw"] or -999)
        self.assertEqual(loudest["band"], "400-2000")
        self.assertGreater(loudest["share_db"], -0.1)
        nyq = tone_ab.band_energies(array.array("f", [0.0] * 4 * 16384), 1, 16000)["bands"]
        self.assertEqual(nyq[-1]["status"], "above_nyquist")
        self.assertIsNone(nyq[-1]["level_dbfs_raw"])

    def test_attack_analysis_hash_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            pcm = {"sample_rate": RATE, "channels": 1, "sample_count": FRAMES}
            (run_dir / "analysis.json").write_text(json.dumps(analysis_record("0" * 64)))
            unbound = tone_ab.find_attack_analysis(run_dir, {}, "f" * 64, pcm)
            self.assertEqual(unbound["status"], "no_hash_bound_attack_analysis")
            self.assertEqual(unbound["tried"][0]["status"], "analyzed_input_sha256_mismatch")
            self.assertIsNone(unbound["data"])
            # Parent-run fallback via capture_profile_application.authoring_dir.
            parent = run_dir / "parent"
            (parent / "capture-profiles" / "p1").mkdir(parents=True)
            (parent / "analysis.json").write_text(json.dumps(analysis_record("f" * 64)))
            manifest = {"capture_profile_application": {"authoring_dir": str(parent / "capture-profiles" / "p1")}}
            bound = tone_ab.find_attack_analysis(run_dir, manifest, "f" * 64, pcm)
            self.assertEqual(bound["status"], "hash_bound")
            self.assertEqual(bound["basis"], "parent_run_from_capture_profile_authoring_dir")
            wrong_extent = tone_ab.find_attack_analysis(run_dir, manifest, "f" * 64, dict(pcm, sample_count=FRAMES + 1))
            self.assertEqual(wrong_extent["status"], "no_hash_bound_attack_analysis")
        panels = tone_ab.attack_panels(analysis_record("f" * 64))
        self.assertEqual(len(panels["primary"]["seconds"]), 110)
        self.assertEqual(len(panels["secondary"]["seconds"]), 4)
        region = {"start_sample": 110250, "end_sample_exclusive": FRAMES}
        samples = array.array("f", [0.1] * (FRAMES - 110250))
        rows = tone_ab.attack_metrics(samples, 1, RATE, region, [110250 - 1, 110250, FRAMES - 441, FRAMES - 440])
        self.assertIsNone(rows[0])
        self.assertIsNotNone(rows[1])
        self.assertIsNotNone(rows[2])  # window [FRAMES-441, FRAMES) is exactly inside
        self.assertIsNone(rows[3])
        self.assertAlmostEqual(rows[1]["energy_dbfs_raw"], 20 * math.log10(0.1), places=4)

    def test_centroid_gain_invariant_and_unknown_fields_present(self):
        rng = random.Random(11)
        signal = [math.sin(2 * math.pi * 2500 * i / RATE) * 0.4 + rng.gauss(0, 0.05) for i in range(RATE)]
        region = {"start_sample": 0, "end_sample_exclusive": RATE}
        loud = tone_ab.attack_metrics(array.array("f", signal), 1, RATE, region, [1000, 5000])
        quiet = tone_ab.attack_metrics(array.array("f", (0.5 * v for v in signal)), 1, RATE, region, [1000, 5000])
        for a, b in zip(loud, quiet):
            self.assertAlmostEqual(a["centroid_hz"], b["centroid_hz"], places=3)
            self.assertAlmostEqual(a["energy_dbfs_raw"] - b["energy_dbfs_raw"], -20 * math.log10(0.5), places=3)
        self.assertTrue(1500 < loud[0]["centroid_hz"] < 6000)
        silent = tone_ab.attack_metrics(array.array("f", [0.0] * RATE), 1, RATE, region, [1000])
        self.assertIsNone(silent[0]["centroid_hz"])
        self.assertIsNone(silent[0]["energy_dbfs_raw"])
        required = {"operator_preference": None, "listening_accepted": False, "room_response_recovered": False,
                    "perceived_fullness": None, "nasal_quality": None, "fan_only_gain": None,
                    "music_only_gain": None, "fundamental_32hz_presence": None, "capture_chain_response": None,
                    "monitoring_device": None, "attack_identity": "unverified", "true_peak_dbtp": None,
                    "stage_separation_eq_vs_compressor": "not_separable_combined_stage",
                    "default_adopted": False, "master_changed": False}
        self.assertEqual({k: v for k, (v, _) in tone_ab.UNKNOWN_FIELDS.items()}, required)
        self.assertTrue(all(reason for _, reason in tone_ab.UNKNOWN_FIELDS.values()))

    def test_excerpt_window_rule_and_seeded_labels(self):
        region = tone_ab.region_samples(5.0, 150.0, {"sample_rate": 44100, "channels": 1, "sample_count": 6657385})
        windows = tone_ab.excerpt_windows(region, 44100)
        self.assertEqual([w["frames"] for w in windows], [661500] * 3)
        for i, window in enumerate(windows):
            center = 5.0 + 145.0 * (2 * i + 1) / 6
            self.assertAlmostEqual(window["center_seconds"], center)
            self.assertEqual(window["start_sample"], round((center - 7.5) * 44100))
            swap = random.Random(20261006 + i).random() < 0.5
            self.assertEqual(window["key"]["X"], "delivery_master" if swap else "source")
            self.assertEqual(sorted(window["key"].values()), ["delivery_master", "source"])
        self.assertLess(windows[0]["end_sample_exclusive"], windows[1]["start_sample"])


class GateTests(FixtureBase):
    def test_wav_header_parser_reads_float_and_extensible_s24(self):
        source = tone_ab.read_wav_header(self.template / "source.wav")
        self.assertEqual((source["format_tag"], source["bits_per_sample"], source["frames"]), (3, 32, FRAMES))
        cleaned = tone_ab.read_wav_header(self.template / "cleaned.wav")
        self.assertEqual((cleaned["format_tag"], cleaned["container_format_tag"], cleaned["bits_per_sample"],
                          cleaned["frames"], cleaned["sample_rate"]), (1, 0xFFFE, 24, FRAMES, RATE))

    def test_stage_hash_mismatch_refusal(self):
        run_dir = self.fresh_run("hash-mismatch")
        path = run_dir / "denoised.wav"
        data = bytearray(path.read_bytes())
        data[-5] ^= 0x01
        path.write_bytes(bytes(data))
        out = self.base / "out-hash"
        with self.assertRaises(tone_ab.ToneABError) as caught:
            tone_ab.run(args(run_dir), out)
        self.assertEqual(caught.exception.code, "stage_hash_mismatch")
        self.assertFalse(out.exists())
        self.assertFalse(any(p.name.startswith(".out-hash") or p.name.startswith("out-hash")
                             for p in self.base.iterdir()))

    def test_native_extent_mismatch_refusal(self):
        run_dir = self.fresh_run("extent-mismatch")
        manifest = json.loads((run_dir / "manifest.json").read_text())
        manifest["pcm"]["sample_count"] = FRAMES + 1
        (run_dir / "manifest.json").write_text(json.dumps(manifest))
        out = self.base / "out-extent"
        with self.assertRaises(tone_ab.ToneABError) as caught:
            tone_ab.run(args(run_dir), out)
        self.assertEqual(caught.exception.code, "native_extent_mismatch")
        self.assertFalse(out.exists())

    def test_region_end_beyond_run_duration_refused(self):
        with self.assertRaises(tone_ab.ToneABError) as caught:
            tone_ab.run(args(self.template, common_region_end=55.5), self.base / "out-duration")
        self.assertEqual(caught.exception.code, "region_out_of_bounds")

    def test_fresh_output_dir_required(self):
        existing = self.base / "existing-out"
        existing.mkdir()
        with self.assertRaises(tone_ab.ToneABError) as caught:
            tone_ab.run(args(self.template), existing)
        self.assertEqual(caught.exception.code, "output_dir_exists")
        self.assertEqual(list(existing.iterdir()), [])

    def test_output_inside_protected_dirs_refused(self):
        for target in (self.template / "tone-ab", self.template,
                       self.base / "artifacts" / "runs" / "other" / "x", self.base / "artifacts" / "runs" / "new"):
            with self.subTest(target=target), self.assertRaises(tone_ab.ToneABError) as caught:
                tone_ab.run(args(self.template), target)
            self.assertIn(caught.exception.code, {"output_dir_protected", "output_dir_exists"})
        self.assertFalse((self.template / "tone-ab").exists())
        self.assertFalse((self.base / "artifacts").exists())

    def test_candidate_source_mismatch_refusal(self):
        candidate = self.base / "candidate-other-source"
        make_run(candidate, analysis=False, source_sha="cd" * 32)
        with self.assertRaises(tone_ab.ToneABError) as caught:
            tone_ab.run(args(self.template, candidate_run_dir=str(candidate)), self.base / "out-cand")
        self.assertEqual(caught.exception.code, "candidate_source_mismatch")
        with self.assertRaises(tone_ab.ToneABError) as caught:
            tone_ab.run(args(self.template, candidate_run_dir=str(self.template)), self.base / "out-same")
        self.assertEqual(caught.exception.code, "invalid_arguments")

    def test_failure_keeps_only_failed_record(self):
        out = self.base / "out-failure"
        before = tone_ab.snapshot(self.template)
        with patch.object(tone_ab, "render_trial",
                          side_effect=tone_ab.ToneABError("ffmpeg_failed", "simulated")):
            with self.assertRaises(tone_ab.ToneABError):
                tone_ab.run(args(self.template), out)
        self.assertFalse(out.exists())
        failed = self.base / "out-failure.failed"
        self.assertEqual([p.name for p in failed.iterdir()], ["tone-ab.failed.json"])
        record = json.loads((failed / "tone-ab.failed.json").read_text())
        self.assertEqual((record["status"], record["code"], record["master_changed"]), ("failed", "ffmpeg_failed", False))
        self.assertEqual(tone_ab.snapshot(self.template), before)

    def test_cli_refusal_exit_code(self):
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer):
            code = tone_ab.main(["run", "--run-dir", str(self.template), "--common-region-start", "4",
                                 "--common-region-end", "55"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(buffer.getvalue())["code"], "region_out_of_bounds")


@unittest.skipUnless(HAVE_FFMPEG, SKIP_REASON)
class FFmpegRunTests(FixtureBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.run_dir = cls.template
        cls.before = tone_ab.snapshot(cls.run_dir)
        cls.out = cls.base / "s2" / "tone_ab" / "fixture-run"
        cls.record = tone_ab.run(args(cls.run_dir), cls.out)
        cls.saved = json.loads((cls.out / "tone-ab.json").read_text())

    def test_no_master_overwrite_and_protected_readback(self):
        self.assertEqual(tone_ab.snapshot(self.run_dir), self.before)
        readback = self.saved["protected_readback"]
        self.assertEqual(readback["status"], "unchanged")
        self.assertEqual(readback["directories"]["run_dir"]["changed"], [])
        self.assertEqual(readback["directories"]["run_dir"]["files_checked"], len(self.before))
        self.assertIs(self.saved["master_changed"], False)
        self.assertIs(self.saved["default_adopted"], False)
        self.assertFalse(any(p.name.startswith(("trial", "excerpt", "tone-ab")) for p in self.run_dir.iterdir()))
        self.assertTrue((self.out / "trial-lowshelf.wav").is_file())
        self.assertEqual(self.saved["status"], "completed")

    def test_two_tone_match_convergence_ffmpeg(self):
        self.assertEqual(self.saved["loudness_match"]["match_status"], "matched")
        self.assertLessEqual(self.saved["loudness_match"]["match_lu_delta"], 0.3)
        gains = {k: v["gain_db"] for k, v in self.saved["loudness_match"]["per_arm"].items()}
        self.assertEqual(set(gains), {"source", "pure_denoise", "tone_dynamics_pre_gain",
                                      "delivery_master", "trial_lowshelf"})
        self.assertTrue(all(g <= 0 for g in gains.values()))
        # Direct two-arm check: different 32.7 Hz / 1 kHz mixes and levels.
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            n = RATE * 20
            w32, w1k = 2 * math.pi * 32.703 / RATE, 2 * math.pi * 1000 / RATE
            write_f32(temp / "a.wav", [0.5 * math.sin(w32 * i) + 0.05 * math.sin(w1k * i) for i in range(n)])
            write_f32(temp / "b.wav", [0.05 * math.sin(w32 * i) + 0.3 * math.sin(w1k * i) for i in range(n)])
            runner = tone_ab.Runner(tone_ab.time.monotonic() + 300)
            region = {"start_sample": RATE, "end_sample_exclusive": n - RATE}
            paths = {"a": temp / "a.wav", "b": temp / "b.wav"}
            result = tone_ab.match_gains(["a", "b"], lambda label, gain: tone_ab.measure_lufs(
                runner, paths[label], region, gain))
            self.assertEqual(result["match_status"], "matched")
            self.assertLessEqual(result["match_lu_delta"], 0.3)
            self.assertGreater(abs(result["per_arm"]["a"]["lufs_before"] - result["per_arm"]["b"]["lufs_before"]), 1.0)

    def test_band_cells_and_stage_deltas(self):
        bands = self.saved["bands"]
        cells = [b for arm in bands.values() for b in arm["bands"]]
        self.assertEqual(len(cells), 30)
        self.assertTrue(all(c["level_dbfs_raw"] is not None and c["level_dbfs_matched"] is not None for c in cells))
        for arm, record in bands.items():
            gain = self.saved["loudness_match"]["per_arm"][arm]["gain_db"]
            for band in record["bands"]:
                self.assertAlmostEqual(band["level_dbfs_matched"], band["level_dbfs_raw"] + gain, places=9)
        deltas = self.saved["stage_deltas"]
        self.assertEqual(set(deltas), {"denoise_stage", "tone_dynamics_stage_combined", "delivery_normalization",
                                       "end_to_end", "trial"})
        self.assertIsNone(deltas["end_to_end"]["fan_only_gain"])
        # cleaned has 0.40 vs source 0.30 at 32.7 Hz: about +2.5 dB raw mixture energy.
        self.assertAlmostEqual(deltas["end_to_end"]["bands"]["20-45"]["raw_db"], 20 * math.log10(0.4 / 0.3), delta=0.3)

    def test_excerpt_extent_preservation_ffmpeg(self):
        excerpts = self.saved["excerpts"]
        self.assertEqual(len(excerpts["pairs"]), 3)
        self.assertEqual(excerpts["frames_per_file"], round(15 * RATE))
        gains = {k: v["gain_db"] for k, v in self.saved["loudness_match"]["per_arm"].items()}
        for i, pair in enumerate(excerpts["pairs"]):
            center = 5.0 + 50.0 * (2 * i + 1) / 6
            self.assertEqual(pair["start_sample"], round((center - 7.5) * RATE))
            key = excerpts["blind_key"][i]
            swap = random.Random(20261006 + i).random() < 0.5
            self.assertEqual(key["X"], "delivery_master" if swap else "source")
            for blind in ("X", "Y"):
                record = pair["files"][blind]
                header = tone_ab.read_wav_header(self.out / record["file"])
                self.assertEqual((header["frames"], header["sample_rate"], header["channels"], header["format_tag"]),
                                 (round(15 * RATE), RATE, 1, 3))
                self.assertEqual(record["sha256"], sha(self.out / record["file"]))
                self.assertEqual(record["static_gain_db"], gains[key[blind]])
                self.assertIsNone(record["true_peak_dbtp"])
        self.assertIsNone(excerpts["operator_preference"])

    def test_attack_denominators_from_bound_analysis(self):
        attacks = self.saved["attacks"]
        self.assertEqual(attacks["status"], "hash_bound")
        primary = attacks["panels"]["primary"]["denominators"]
        self.assertEqual(primary, {"events_in_analysis": 110, "invalid_timestamps": 0, "in_region": 101, "used": 100})
        secondary = attacks["panels"]["secondary"]["denominators"]
        self.assertEqual((secondary["events_in_analysis"], secondary["in_region"], secondary["used"]), (4, 3, 3))
        self.assertEqual(attacks["window"]["samples"], 441)
        self.assertEqual(attacks["attack_identity"], "unverified")
        per_arm = attacks["panels"]["primary"]["per_arm"]
        self.assertEqual(per_arm["source"]["count_with_energy"], 100)
        self.assertEqual(per_arm["trial_lowshelf"]["paired_median_deltas"]["vs_delivery_master"]["pairs"], 100)

    def test_trial_arm_fields_and_reversibility_ffmpeg(self):
        saved = self.saved
        trial_arms = [a for a in saved["arms"] if a["label"] == "trial_lowshelf"]
        self.assertEqual(len(trial_arms), 1)
        experiment = saved["experiment"]
        self.assertEqual(experiment["status"], "rejected_or_unreviewed_trial")
        self.assertEqual(experiment["filter"], "lowshelf=f=100:t=q:w=0.7:g=1.5:r=f64")
        self.assertIs(experiment["adopted"], False)
        self.assertIs(experiment["forwarded_to_profile"], False)
        self.assertIsNone(saved["operator_preference"])
        self.assertIs(saved["room_response_recovered"], False)
        floor = saved["eq_floor_change_proposed"]
        self.assertEqual(floor["measured_delta_20_45_db"], experiment["delta_20_45_db"])
        self.assertIs(floor["adopted"], False)
        self.assertEqual((floor["current_schema_min_hz"], floor["trial_shelf_hz"]), (160, 100.0))
        self.assertGreater(experiment["delta_20_45_db"]["raw"], 1.0)
        self.assertLess(experiment["delta_20_45_db"]["raw"], 1.6)
        self.assertEqual(trial_arms[0]["path"], str(self.out / "trial-lowshelf.wav"))
        self.assertEqual(saved["claims"]["listening"], [])
        for field in tone_ab.UNKNOWN_FIELDS:
            self.assertIn(field, saved)
            self.assertTrue(saved["unknown_field_reasons"][field])
        # g=0 shelf is a near-null identity.
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "identity.wav"
            runner = tone_ab.Runner(tone_ab.time.monotonic() + 300)
            pcm = {"sample_rate": RATE, "channels": 1, "sample_count": FRAMES}
            tone_ab.render_trial(runner, self.run_dir / "cleaned.wav", out, pcm, gain_db=0.0)
            original, _ = tone_ab.read_wav_samples(self.run_dir / "cleaned.wav")
            rendered, _ = tone_ab.read_wav_samples(out)
            self.assertEqual(len(original), len(rendered))
            rms = math.sqrt(sum((a - b) ** 2 for a, b in zip(original, rendered)) / len(original))
            self.assertLess(rms, 1e-4)


if __name__ == "__main__":
    unittest.main()
