import importlib.util
import contextlib
import io
import json
import math
import random
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("rhythm", Path(__file__).resolve().parents[1] / "scripts/rhythm.py")
rhythm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rhythm)


def clicks(bpm=90, seconds=14, phase=.2):
    samples = [0.0] * round(seconds * rhythm.RATE)
    time = phase
    while time < seconds - .02:
        start = round(time * rhythm.RATE)
        for j in range(120):
            samples[start + j] += .5 * math.sin(2 * math.pi * 3500 * j / rhythm.RATE) * math.exp(-j / 25)
        time += 60 / bpm
    return samples


class RhythmTests(unittest.TestCase):
    def test_known_click_grid_and_timeline(self):
        result = rhythm.analyze(clicks(), source_start=12.5)
        grid = result["click_grid"]
        self.assertIsNotNone(grid)
        self.assertAlmostEqual(grid["bpm"], 90, delta=.5)
        self.assertLess(grid["median_absolute_residual_ms"], 5)
        for event in result["events"]:
            self.assertAlmostEqual(event["source_timeline_seconds"], event["audio_relative_seconds"] + 12.5)
        self.assertEqual(result["performance"]["status"], "not_graded")
        self.assertIsNone(result["meter"]["time_signature"])

    def test_silence_abstains(self):
        result = rhythm.analyze([0.0] * rhythm.RATE * 3)
        self.assertEqual(result["tempo_candidates"], [])
        self.assertIsNone(result["click_grid"])
        self.assertEqual(result["events"], [])

    def test_steady_tone_has_no_confirmed_click(self):
        samples = [math.sin(2 * math.pi * 500 * i / rhythm.RATE) * .1 for i in range(rhythm.RATE * 3)]
        result = rhythm.analyze(samples)
        self.assertIsNone(result["click_grid"])

    def test_half_double_ambiguity_retained(self):
        result = rhythm.analyze(clicks(bpm=180))
        bpms = [x["bpm"] for x in result["tempo_candidates"]]
        self.assertTrue(any(abs(x - 180) < 2 for x in bpms))
        self.assertTrue(any(abs(x - 90) < 2 for x in bpms))

    def test_offset_signs(self):
        grid = {"phase_seconds_audio_relative": .1, "period_seconds": .5}
        self.assertAlmostEqual(rhythm.grid_offset(1.08, grid)[1], -20)
        self.assertAlmostEqual(rhythm.grid_offset(1.12, grid)[1], 20)

    def test_noise_without_periodicity_abstains(self):
        generator = random.Random(204)
        samples = [generator.uniform(-.02, .02) for _ in range(rhythm.RATE * 4)]
        result = rhythm.analyze(samples)
        self.assertIsNone(result["click_grid"])
        self.assertEqual(result["performance"]["status"], "not_graded")

    def test_missing_click_is_not_performance_error(self):
        samples = clicks()
        center = round((.2 + 4 * (60 / 90)) * rhythm.RATE)
        samples[center:center + 120] = [0.0] * 120
        result = rhythm.analyze(samples)
        self.assertAlmostEqual(result["click_grid"]["bpm"], 90, delta=.5)
        self.assertLess(result["click_grid"]["candidate_coverage"], 1)
        self.assertEqual(result["performance"]["status"], "not_graded")


class TimelineLineageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.run_dir = Path(self.directory.name)
        self.source = self.run_dir / "denoised.wav"
        self.source.write_bytes(b"test derivative content; decoding is mocked")
        self.input_hash = rhythm.file_hash(self.source)
        self.metadata = {"audio": {"start_time": "0", "codec_name": "pcm_f32le", "sample_rate": "16000",
                                   "channels": 1, "duration_ts": 48000, "time_base": "1/16000"}, "format": {}}
        self.manifest = {"run_id": "fixture", "source": {"sha256": "a" * 64, "path": "/original/take.mov"},
                         "output_sha256": {"denoised.wav": self.input_hash},
                         "timeline": {"audio_start_seconds": 12.75, "no_time_stretch": True},
                         "pcm": {"sample_rate": 16000, "channels": 1, "sample_count": 48000}}
        self.write_manifest()

    def write_manifest(self):
        (self.run_dir / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_hash_bound_pcm_restores_nonzero_original_origin(self):
        start, lineage = rhythm.input_timeline(self.source, self.input_hash, self.metadata, self.run_dir)
        self.assertEqual(start, 12.75)
        self.assertEqual(lineage["analyzed_input_sha256"], self.input_hash)
        self.assertEqual(lineage["original_source_sha256"], "a" * 64)
        self.assertTrue(lineage["timeline_rebased"])
        self.assertEqual(lineage["sample_mapping"]["original_samples_per_analysis_frame"], "80")

    def test_hash_mismatch_rejected_without_rebase(self):
        with self.assertRaisesRegex(ValueError, "hash does not match"):
            rhythm.input_timeline(self.source, "b" * 64, self.metadata, self.run_dir)

    def test_extent_mismatch_and_stretch_rejected(self):
        self.manifest["pcm"]["sample_count"] += 1
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "count differs"):
            rhythm.input_timeline(self.source, self.input_hash, self.metadata, self.run_dir)
        self.manifest["pcm"]["sample_count"] -= 1
        self.manifest["timeline"]["no_time_stretch"] = False
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "unchanged time scale"):
            rhythm.input_timeline(self.source, self.input_hash, self.metadata, self.run_dir)

    def test_unrelated_input_keeps_its_origin_explicitly(self):
        unrelated = self.run_dir / "other.mov"
        start, lineage = rhythm.input_timeline(unrelated, "c" * 64, self.metadata, self.run_dir)
        self.assertEqual(start, 0)
        self.assertEqual(lineage["status"], "input_not_manifest_derivative")
        self.assertFalse(lineage["timeline_rebased"])

    def test_cli_publishes_actual_input_identity_and_original_event_axis(self):
        with patch.object(rhythm, "probe", return_value=self.metadata), \
                patch.object(rhythm, "decode", return_value=clicks(seconds=3)), \
                patch("sys.argv", ["rhythm.py", str(self.source), "--run-dir", str(self.run_dir)]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rhythm.main(), 0)
        result = json.loads((self.run_dir / "analysis.json").read_text())
        self.assertEqual(result["source"]["sha256"], self.input_hash)
        self.assertEqual(result["source"]["path"], str(self.source.resolve()))
        self.assertEqual(result["timeline"]["audio_stream_start_seconds"], 12.75)
        self.assertTrue(result["events"])
        for event in result["events"]:
            self.assertAlmostEqual(event["source_timeline_seconds"], event["audio_relative_seconds"] + 12.75)


if __name__ == "__main__":
    unittest.main()
