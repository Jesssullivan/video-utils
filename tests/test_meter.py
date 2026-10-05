from pathlib import Path
import hashlib
import json
import math
import random
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from meter import analyze_run, infer, rank_accents


def feature_analysis(pattern, pulses=120, period=.5):
    times = [i*.05 for i in range(round(pulses*period/.05))]
    energy = [pattern[int((time+1e-8)/period) % len(pattern)] for time in times]
    return {"click_grid": {"period_seconds": period, "phase_seconds_audio_relative": 0.},
            "timeline": {"audio_stream_start_seconds": 12.},
            "librosa": {"features": {"matrix_layout": "feature_by_frame",
                "frame_times_audio_relative_seconds": times, "mfcc": [energy]+[[0.]*len(times) for _ in range(12)]}}}


class MeterTests(unittest.TestCase):
    def test_distinct_accent_patterns_rank_primitive_cycles(self):
        for pattern in ([1., .2, .4], [1., .2, .5, .2], [1., .2, .4, .15, .6, .25, .3]):
            with self.subTest(pattern=pattern):
                result = rank_accents(list(pattern)*24)
                self.assertEqual(result["status"], "accent_cycle_hypothesis")
                self.assertEqual(result["selected"]["cycle_pulses"], len(pattern))
                self.assertEqual(result["selected"]["score_kind"], "heuristic_not_probability")

    def test_uniform_click_and_continuous_legato_abstain(self):
        for value in (0., .5, 80.):
            self.assertIsNone(rank_accents([value]*120)["selected"])

    def test_seven_equal_subdivisions_do_not_prove_seven_meter(self):
        # Seven equal attacks per four-pulse bar have equal aggregate pulse energy.
        data = feature_analysis([1.]*4)
        data["events"] = [{"kind": "guitar_attack", "audio_relative_seconds": n*2/7} for n in range(210)]
        result = infer(data)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["time_signature"])
        self.assertTrue(all(alias["selected"] is None for alias in result["aliases"]))

    def test_random_accents_and_a_slow_ramp_abstain(self):
        rng = random.Random(7401)
        for values in ([rng.random() for _ in range(240)], [i/240 for i in range(240)]):
            self.assertIsNone(rank_accents(values)["selected"])

    def test_too_few_cycles_abstain(self):
        self.assertIsNone(rank_accents([1., .2, .5]*3)["selected"])

    def test_aliases_and_source_time_do_not_fix_notation(self):
        result = infer(feature_analysis([1., .2, .5, .2]))
        self.assertIsNone(result["time_signature"])
        self.assertEqual([item["pulse_bpm"] for item in result["aliases"]], [240., 120., 60.])
        central = result["aliases"][1]
        self.assertEqual(central["selected"]["cycle_pulses"], 4)
        self.assertEqual(central["selected"]["notation_hypothesis"], "4/4")
        self.assertEqual(central["accent_cycle_start_source_seconds"], 12.)
        self.assertIsNone(central["selected"]["additive_grouping"])

    def test_missing_backend_features_abstains(self):
        self.assertEqual(infer({})["reason"], "missing_comparative_features_or_pulse_grid")

    def test_nonfinite_malformed_and_unbounded_inputs_rejected(self):
        for value in (float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                rank_accents([value]*20)
        with self.assertRaises(ValueError):
            rank_accents([1.]*14401)
        data = feature_analysis([1., .2, .5])
        data["librosa"]["features"]["frame_times_audio_relative_seconds"][1] = 0.
        with self.assertRaises(ValueError):
            infer(data)

    def make_run(self, directory):
        directory = Path(directory)
        source = directory / "denoised.wav"
        source.write_bytes(b"synthetic provenance fixture; meter never decodes this")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        original = "a"*64
        manifest = {"source": {"sha256": original}, "output_sha256": {source.name: digest},
                    "timeline": {"audio_start_seconds": 12., "no_time_stretch": True}}
        manifest_path = directory / "manifest.json"
        manifest_path.write_text(json.dumps(manifest))
        analysis = feature_analysis([1., .2, .5, .2])
        analysis["source"] = {"path": str(source), "sha256": digest}
        analysis["source_lineage"] = {"status": "hash_bound_run_derivative",
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "original_source_sha256": original, "analyzed_input_sha256": digest,
            "original_audio_start_seconds": 12., "sample_mapping": {"no_time_stretch": True}}
        (directory / "analysis.json").write_text(json.dumps(analysis))
        return source, analysis

    def test_source_provenance_verified_and_inputs_unmodified(self):
        with tempfile.TemporaryDirectory() as temp:
            source, _ = self.make_run(temp)
            before = source.read_bytes()
            result = analyze_run(Path(temp))
            self.assertEqual(result["provenance"]["original_source_sha256"], "a"*64)
            self.assertTrue(result["provenance"]["no_media_changes"])
            self.assertEqual(source.read_bytes(), before)

    def test_media_or_lineage_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            source, _ = self.make_run(temp)
            source.write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "media hash"):
                analyze_run(Path(temp))
        with tempfile.TemporaryDirectory() as temp:
            _, analysis = self.make_run(temp)
            analysis["source_lineage"]["original_source_sha256"] = "b"*64
            (Path(temp)/"analysis.json").write_text(json.dumps(analysis))
            with self.assertRaisesRegex(ValueError, "lineage"):
                analyze_run(Path(temp))

    def test_mixed_local_cycles_are_not_confirmed_meter(self):
        data = feature_analysis([1., .2, .5], pulses=336)
        features = data["librosa"]["features"]
        for i, time in enumerate(features["frame_times_audio_relative_seconds"]):
            if time >= 84:
                features["mfcc"][0][i] = [1., .2, .5, .2][int((time+1e-8)/.5)%4]
        result = infer(data)
        self.assertEqual(result["local_structure"], "mixed_or_nonstationary_accent_evidence")
        self.assertIsNone(result["time_signature"])

    def test_source_time_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            _, analysis = self.make_run(temp)
            analysis["timeline"]["audio_stream_start_seconds"] = 13.
            (Path(temp)/"analysis.json").write_text(json.dumps(analysis))
            with self.assertRaisesRegex(ValueError, "timeline"):
                analyze_run(Path(temp))


if __name__ == "__main__":
    unittest.main()
