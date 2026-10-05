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

    def test_declared_178_kept_separate_from_audio_periodicity(self):
        result = rhythm.analyze(clicks(bpm=178), bpm=178)
        self.assertEqual(result["declared_tempo"]["bpm"], 178)
        self.assertEqual(result["declared_tempo"]["precision"], "approximate")
        self.assertEqual(result["click_grid"]["tempo_seed_bpm"], 178)
        self.assertAlmostEqual(result["click_grid"]["bpm"], 178, delta=1)
        self.assertEqual(result["performance"]["status"], "not_graded")

    def test_failed_approximate_double_seed_falls_back_without_overwriting_declaration(self):
        # A long 90 BPM train makes the approximate doubled 178 seed drift through
        # different phase neighborhoods; its fit abstains, while the real 90 train fits.
        result = rhythm.analyze(clicks(bpm=90, seconds=40), bpm=178)
        self.assertEqual(result["declared_tempo"]["bpm"], 178)
        self.assertEqual(result["grid_fit_attempts"][0]["status"], "no_stable_observed_fit")
        self.assertEqual(result["grid_fit_attempts"][0]["seed_bpm"], 178)
        self.assertEqual(result["grid_fit_attempts"][1]["status"], "observed_fit")
        self.assertAlmostEqual(result["click_grid"]["bpm"], 90, delta=.5)
        self.assertEqual(result["click_grid"]["selection"], "audio_periodicity_fallback_after_declared_seed_fit_abstention")
        doubled = next(item for item in result["metrical_interpretations"] if item["pulse_multiplier"] == 2)
        self.assertAlmostEqual(doubled["bpm"], 180, delta=1)
        self.assertEqual(doubled["basis"], "observed_fitted_grid")
        self.assertEqual(result["subdivisions"]["status"], "automatic_candidates")

    def test_automatic_triplet_candidates_without_expected_pattern(self):
        grid = {"phase_seconds_audio_relative": .1, "period_seconds": .6}
        times = [.1 + i * .2 for i in range(60)]
        result = rhythm.subdivision_candidates(times, grid)
        self.assertEqual(result["status"], "automatic_candidates")
        triple = next(c for c in result["candidates"] if c["subdivisions_per_declared_or_fitted_pulse"] == 3)
        quarter = next(c for c in result["candidates"] if c["subdivisions_per_declared_or_fitted_pulse"] == 1)
        self.assertGreater(triple["within_tolerance_fraction"], quarter["within_tolerance_fraction"])
        self.assertEqual(triple["status"], "candidate_not_intended_rhythm")

    def test_optional_onset_timestamps_have_correct_sample_axis(self):
        optional = {"onsets": {"superflux": {"frames": [30], "audio_relative_seconds": [.15]}}, "features": {}}
        with patch.object(rhythm, "librosa_analysis", return_value=optional):
            result = rhythm.analyze(clicks(seconds=3), source_start=12.5, backend="librosa")
        event = next(event for event in result["events"] if event["kind"] == "superflux_attack_candidate")
        self.assertEqual(event["analysis_sample_position"], 2400)
        self.assertEqual(event["source_timeline_seconds"], 12.65)
        self.assertEqual(event["timestamp_convention"], "librosa_frame_time_center_compensated")

    @unittest.skipUnless(importlib.util.find_spec("librosa"), "optional librosa dependency absent")
    def test_actual_librosa_backend_has_two_onset_methods_and_features(self):
        result = rhythm.librosa_analysis(clicks(seconds=3))
        self.assertEqual(set(result["onsets"]), {"spectral_flux", "superflux"})
        self.assertTrue(result["onsets"]["superflux"]["frames"])
        self.assertEqual(len(result["features"]["mfcc"]), 13)
        self.assertEqual(len(result["features"]["chroma"]), 12)
        self.assertEqual(result["features"]["hop_samples"], 800)


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
