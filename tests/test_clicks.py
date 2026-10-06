import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("clicks", Path(__file__).resolve().parents[1] / "scripts/clicks.py")
clicks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(clicks)

HAS_ANALYSIS = bool(importlib.util.find_spec("numpy") and importlib.util.find_spec("scipy"))


def fixture(rate=16000, seconds=6, low_amplitude=0, collide=False, separate_attack=False):
    import numpy as np
    times = np.arange(round(seconds * rate)) / rate
    guitar = low_amplitude * np.sin(2 * np.pi * 32 * times)
    click_track = np.zeros(len(times))
    pulse_times = [.2 + i * .5 for i in range(int((seconds - .3) / .5) + 1)]
    size = round(.025 * rate)
    t = np.arange(size) / rate
    pulse = .4 * np.sin(2 * np.pi * 3000 * t) * np.exp(-t / .003)
    for event in pulse_times:
        begin = round(event * rate)
        click_track[begin:begin + size] += pulse
    attack_start = None
    if collide or separate_attack:
        event = pulse_times[4] if collide else pulse_times[4] + .25
        attack_start = round(event * rate)
        length = round(.10 * rate)
        t = np.arange(length) / rate
        attack = .25 * np.tanh(8 * np.sin(2 * np.pi * 185 * t)) * np.exp(-t / .02)
        guitar[attack_start:attack_start + length] += attack
    return (guitar + click_track).astype(np.float32), guitar, click_track, pulse_times, attack_start


@unittest.skipUnless(HAS_ANALYSIS, "optional locked analysis dependencies absent")
class ClickExperimentTests(unittest.TestCase):
    def experiment(self, pcm, rate=16000, **kwargs):
        return clicks.experiment(pcm, rate, template_window=(.2, .225), bpm=120, **kwargs)

    def test_isolated_clicks_are_candidates_and_default_has_no_audio(self):
        pcm, _, _, pulses, _ = fixture()
        result, processed, estimate = self.experiment(pcm)
        self.assertIsNone(processed)
        self.assertIsNone(estimate)
        self.assertEqual(result["identity_status"], "unverified")
        self.assertEqual(result["summary"]["accepted_fit_count"], len(pulses))
        self.assertEqual(result["summary"]["attenuated_count"], 0)

    def test_opt_in_reduces_known_click_component_and_preserves_32_hz(self):
        import numpy as np
        pcm, _, _, _, _ = fixture(low_amplitude=.01)
        original = pcm.copy()
        result, processed, estimate = self.experiment(pcm, attenuate=True, template_click_only=True)
        self.assertGreaterEqual(result["summary"]["attenuated_count"], 3)
        self.assertTrue(np.array_equal(pcm, original))
        self.assertEqual(processed.shape, (len(pcm), 1))
        frequency = np.fft.rfftfreq(len(pcm), 1 / 16000)
        low = int(np.argmin(np.abs(frequency - 32)))
        high = int(np.argmin(np.abs(frequency - 3000)))
        before, after = np.fft.rfft(pcm), np.fft.rfft(processed[:, 0])
        self.assertLess(abs(after[low] - before[low]) / abs(before[low]), 1e-5)
        self.assertLess(abs(after[high]) / abs(before[high]), .65)
        self.assertGreater(abs(after[high]) / abs(before[high]), .35)
        self.assertLess(result["frequency_preservation"]["32_hz_complex_bin_relative_delta"], 1e-5)

    def test_coincident_independent_guitar_attack_abstains(self):
        import numpy as np
        pcm, _, _, _, start = fixture(collide=True)
        result, processed, _ = self.experiment(pcm, attenuate=True, template_click_only=True)
        overlaps = [event for event in result["events"] if abs(event["aligned_window_start_sample"] - start) < 80]
        self.assertTrue(overlaps, "Overlap should be detected and explicitly reviewed, not silently removed")
        self.assertTrue(all(event["decision"] == "abstained" for event in overlaps))
        self.assertTrue(any("overlap_or_non_template_energy" in event["reason"] for event in overlaps))
        # Only filtering tails from other accepted clicks may reach this abstained window.
        interval = slice(start, start + 1600)
        relative_error = np.linalg.norm(processed[interval, 0] - pcm[interval]) / np.linalg.norm(pcm[interval])
        self.assertLess(relative_error, .01)

    def test_nonoverlap_pick_attack_preserved_in_known_fixture(self):
        import numpy as np
        pcm, guitar, _, _, start = fixture(separate_attack=True)
        result, processed, _ = self.experiment(pcm, attenuate=True, template_click_only=True)
        self.assertGreater(result["summary"]["attenuated_count"], 0)
        interval = slice(start, start + 1600)
        relative_error = np.linalg.norm(processed[interval, 0] - guitar[interval]) / np.linalg.norm(guitar[interval])
        self.assertLess(relative_error, .01)

    def test_no_click_or_low_register_template_is_not_removed(self):
        import numpy as np
        t = np.arange(16000 * 3) / 16000
        pcm = (.1 * np.sin(2 * np.pi * 32 * t)).astype(np.float32)
        result, processed, _ = self.experiment(pcm, attenuate=True, template_click_only=True)
        self.assertEqual(result["summary"]["attenuated_count"], 0)
        self.assertTrue(np.array_equal(processed[:, 0], pcm))

    def test_noise_template_does_not_create_recurring_click_identity(self):
        import numpy as np
        pcm = np.random.default_rng(204).normal(0, .004, 16000 * 4).astype(np.float32)
        result, processed, _ = self.experiment(pcm, attenuate=True, template_click_only=True)
        self.assertEqual(result["summary"]["attenuated_count"], 0)
        self.assertTrue(np.array_equal(processed[:, 0], pcm))

    def test_zero_strength_is_a_bypass_not_a_claimed_attenuation(self):
        import numpy as np
        pcm, _, _, _, _ = fixture()
        result, processed, _ = self.experiment(pcm, attenuate=True, template_click_only=True, strength=0)
        self.assertEqual(result["summary"]["attenuated_count"], 0)
        self.assertGreater(result["summary"]["accepted_fit_count"], 0)
        self.assertTrue(np.array_equal(processed[:, 0], pcm))

    def test_unconfirmed_or_missing_template_cannot_attenuate(self):
        pcm, _, _, _, _ = fixture()
        with self.assertRaisesRegex(ValueError, "explicit click-only"):
            self.experiment(pcm, attenuate=True)
        with self.assertRaisesRegex(ValueError, "supplied template"):
            clicks.experiment(pcm, 16000, attenuate=True, template_click_only=True)
        with self.assertRaisesRegex(ValueError, "Strength"):
            self.experiment(pcm, attenuate=True, template_click_only=True, strength=.8)

    def test_native_stereo_extent_and_nonzero_media_axis(self):
        import numpy as np
        pcm, _, _, _, _ = fixture(rate=48000)
        stereo = np.column_stack((pcm, pcm * .8))
        result, processed, _ = self.experiment(stereo, rate=48000, attenuate=True, template_click_only=True, source_start=9.75)
        self.assertEqual(result["pcm"]["sample_rate"], 48000)
        self.assertEqual(result["pcm"]["channels"], 2)
        self.assertEqual(processed.shape, stereo.shape)
        for event in result["events"]:
            self.assertAlmostEqual(event["source_timeline_seconds"], event["native_sample"] / 48000 + 9.75)

    def test_no_template_path_passes_through_drift_and_delay_calibration(self):
        pcm, _, _, _, _ = fixture()
        result, processed, estimate = clicks.experiment(pcm, 16000, bpm=120)
        self.assertIsNone(processed)
        self.assertIsNone(estimate)
        drift = result["click_grid_drift"]
        self.assertEqual(drift["model"], "linear_period")
        self.assertIn(drift["status"], ("fitted", "insufficient_events", "no_periodic_seed", "fit_residual_exceeds_bound"))
        if drift["status"] == "fitted":
            self.assertLessEqual(abs(drift["period_change_per_second"]), 2e-4)
        calibration = result["onset_detector_delay_calibration"]
        self.assertEqual(calibration["status"], "measured_on_synthetic_impulses_not_physical_av_offset")
        self.assertIsNone(calibration["compensation_table"]["superflux_attack_candidate"])
        self.assertEqual(result["summary"]["attenuated_count"], 0)
        for event in result["events"]:
            self.assertEqual(event["decision"], "analyze_only")

    def test_cli_detection_artifacts_are_immutable_and_emit_no_wav(self):
        pcm, _, _, _, _ = fixture()
        metadata = {"audio": {"start_time": "0", "duration": "6", "sample_rate": "16000", "channels": 1}, "format": {}}
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            source = run_dir / "input.wav"
            source.write_bytes(b"hash-bound input fixture; decoder mocked")
            original_hash = clicks.rhythm.file_hash(source)
            for _ in range(2):
                with patch.object(clicks.rhythm, "probe", return_value=metadata), \
                        patch.object(clicks, "decode_native", return_value=(pcm[:, None], 16000)), \
                        patch("sys.argv", ["clicks.py", str(source), "--run-dir", str(run_dir), "--bpm", "120"]), \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(clicks.main(), 0)
            receipts = list((run_dir / "clicks").glob("*/clicks.json"))
            self.assertEqual(len(receipts), 2)
            self.assertFalse(list((run_dir / "clicks").rglob("*.wav")))
            for receipt in receipts:
                result = json.loads(receipt.read_text())
                self.assertEqual(result["source"]["sha256"], original_hash)
                self.assertTrue(receipt.with_name("click-events.csv").exists())
            self.assertEqual(clicks.rhythm.file_hash(source), original_hash)

    def test_cli_optin_wav_outputs_verify_samples_extent_and_hashes(self):
        import numpy as np
        from scipy.io import wavfile
        pcm, _, _, _, _ = fixture(rate=48000)
        stereo = np.column_stack((pcm, pcm * .8))
        metadata = {"audio": {"start_time": "5.25", "duration": "6", "sample_rate": "48000", "channels": 2}, "format": {}}
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            source = run_dir / "input.wav"
            source.write_bytes(b"native stereo source fixture; decoder mocked")
            original_hash = clicks.rhythm.file_hash(source)
            with patch.object(clicks.rhythm, "probe", return_value=metadata), \
                    patch.object(clicks, "decode_native", return_value=(stereo, 48000)), \
                    patch("sys.argv", ["clicks.py", str(source), "--run-dir", str(run_dir), "--bpm", "120",
                                       "--template-start", ".2", "--template-end", ".225", "--attenuate", "--template-click-only"]), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(clicks.main(), 0)
            receipt = next((run_dir / "clicks").glob("*/clicks.json"))
            result = json.loads(receipt.read_text())
            self.assertEqual(result["summary"]["attenuated_count"], 12)
            for name in ("click-attenuated.wav", "click-estimate.wav"):
                path = receipt.with_name(name)
                rate, data = wavfile.read(path)
                self.assertEqual(rate, 48000)
                self.assertEqual(data.shape, stereo.shape)
                self.assertEqual(data.dtype, np.float32)
                self.assertEqual(clicks.rhythm.file_hash(path), result["output_sha256"][name])
            self.assertEqual(clicks.rhythm.file_hash(source), original_hash)


if __name__ == "__main__":
    unittest.main()
