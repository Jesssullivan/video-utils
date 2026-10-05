import importlib.util
import math
import json
import tempfile
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("guitar_features", Path(__file__).resolve().parents[1] / "scripts/guitar_features.py")
guitar = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guitar)


def sine(frequency, count=guitar.FRAME, amplitude=.3):
    return [amplitude * math.sin(2 * math.pi * frequency * i / guitar.RATE) for i in range(count)]


class GuitarFeatureTests(unittest.TestCase):
    def test_32hz_is_measured_in_protected_band(self):
        result = guitar.spectrum(sine(32))
        self.assertGreater(result["bands"][0]["mean_square"], .04)
        self.assertEqual(result["bands"][0]["low_hz"], 28)
        self.assertLess(result["bands"][1]["mean_square"], .00001)

    def test_32hz_periodicity_with_strong_distortion_harmonics(self):
        samples = [math.tanh(5*x) for x in sine(32)]
        result = guitar.periodicity(samples)
        self.assertAlmostEqual(result["frequency_hz"], 32, delta=.2)
        self.assertGreater(result["normalized_autocorrelation_score"], .9)
        self.assertTrue(result["harmonic_octave_ambiguity"])

    def test_known_220hz_periodicity_does_not_choose_octave(self):
        self.assertAlmostEqual(guitar.periodicity(sine(220))["frequency_hz"], 220, delta=1)

    def test_silence_abstains_and_emits_finite_json_values(self):
        samples = [0.0] * guitar.RATE
        self.assertIsNone(guitar.periodicity(samples[:guitar.FRAME])["frequency_hz"])
        self.assertIsNone(guitar.noise(samples)["observations"]["whole_signal_rms_dbfs"])
        self.assertIsNone(guitar.tone(samples)["observations"]["sampled_band_energies"][0]["fraction_of_ac_energy"])
        self.assertEqual(guitar.phrases(samples)["observations"]["similar_envelope_region_candidates"], [])

    def test_quiet_guitar_is_not_declared_noise(self):
        result = guitar.noise(sine(32, guitar.RATE, amplitude=.0001))
        self.assertEqual(result["interpretation"]["background_noise_identity"], "unknown")
        self.assertIsNone(result["interpretation"]["noise_only_profile"])
        self.assertTrue(result["observations"]["quiet_candidate_windows"])

    def test_short_note_frame_abstains(self):
        self.assertEqual(guitar.periodicity(sine(32, 1000))["reason"], "less_than_250ms")

    def test_phrase_gap_proposal_is_not_a_mistake(self):
        active = sine(90, guitar.RATE * 2)
        result = guitar.phrases(active + [0.0] * guitar.RATE * 2 + active)
        gaps = result["observations"]["low_energy_gap_candidates"]
        self.assertEqual(gaps[0]["start_seconds"], 2)
        self.assertEqual(gaps[0]["end_seconds"], 4)
        self.assertEqual(result["interpretation"]["phrase_mistakes"], "not_graded")

    def test_manifest_hash_verified_timeline_inheritance(self):
        result = {"source": {"sha256": "verified-denoised-hash", "audio_stream_start_seconds": 0,
                              "sample_rate": 44100, "channels": 1},
                  "analysis": {"duration_seconds": 1}}
        manifest = {"output_sha256": {"denoised.wav": "verified-denoised-hash"},
                    "source": {"sha256": "original-container-hash"},
                    "timeline": {"audio_start_seconds": 12.5, "no_time_stretch": True},
                    "pcm": {"sample_rate": 44100, "channels": 1, "sample_count": 44100}}
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "manifest.json").write_text(json.dumps(manifest))
            guitar.inherit_manifest_lineage(result, run_dir)
        self.assertEqual(result["source"]["audio_stream_start_seconds"], 12.5)
        self.assertEqual(result["source"]["probed_input_audio_start_seconds"], 0)
        self.assertEqual(result["lineage"]["original_source_sha256"], "original-container-hash")
        self.assertEqual(result["lineage"]["matched_artifact_names"], ["denoised.wav"])
        self.assertEqual(result["lineage"]["status"], "verified_canonical_derivative")

    def test_manifest_mismatch_never_guesses_rebase(self):
        result = {"source": {"sha256": "different-recording", "audio_stream_start_seconds": .3,
                              "sample_rate": 44100, "channels": 1},
                  "analysis": {"duration_seconds": 1}}
        manifest = {"output_sha256": {"denoised.wav": "canonical-denoised"},
                    "source": {"sha256": "original-container-hash"},
                    "timeline": {"audio_start_seconds": 12.5, "no_time_stretch": True},
                    "pcm": {"sample_rate": 44100, "channels": 1, "sample_count": 44100}}
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "manifest.json").write_text(json.dumps(manifest))
            guitar.inherit_manifest_lineage(result, run_dir)
        self.assertEqual(result["source"]["audio_stream_start_seconds"], .3)
        self.assertEqual(result["lineage"]["manifest_status"], "rejected")
        self.assertEqual(result["lineage"]["manifest_rejection_reason"], "input_hash_not_canonical_derivative")
        self.assertIsNone(result["lineage"]["original_source_sha256"])

    def test_matching_hash_with_changed_pcm_abstains(self):
        result = {"source": {"sha256": "verified-hash", "audio_stream_start_seconds": 0,
                              "sample_rate": 44100, "channels": 1},
                  "analysis": {"duration_seconds": .9}}
        manifest = {"output_sha256": {"source.wav": "verified-hash"},
                    "source": {"sha256": "original-hash"},
                    "timeline": {"audio_start_seconds": 12.5, "no_time_stretch": True},
                    "pcm": {"sample_rate": 44100, "channels": 1, "sample_count": 44100}}
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "manifest.json").write_text(json.dumps(manifest))
            guitar.inherit_manifest_lineage(result, run_dir)
        self.assertEqual(result["source"]["audio_stream_start_seconds"], 0)
        self.assertEqual(result["lineage"]["manifest_rejection_reason"], "canonical_decoded_length_mismatch")

    def test_phrase_context_rejects_other_recording_and_preserves_offsets(self):
        samples = sine(90, guitar.RATE * 2) + [0.0] * guitar.RATE * 2 + sine(90, guitar.RATE * 2)
        result = {"source": {"sha256": "recording-A", "audio_stream_start_seconds": 7}, **guitar.phrases(samples)}
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "analysis.json").write_text(json.dumps({"source": {"sha256": "recording-B"}, "click_grid": {"bpm": 100}}))
            guitar.phrase_context(result, run_dir)
        self.assertEqual(result["dag_context"]["analysis"]["status"], "rejected_source_mismatch")
        self.assertEqual(result["dag_context"]["notes"]["status"], "not_available")
        span = result["observations"]["proposed_review_spans"][0]
        self.assertEqual(span["source_start_seconds"], 9)
        self.assertEqual(span["source_end_seconds"], 11)
        self.assertIsNone(span["performance_issue"])

    def test_same_source_context_does_not_establish_intent(self):
        result = {"source": {"sha256": "recording-A", "audio_stream_start_seconds": 0}, **guitar.phrases([0.0] * guitar.RATE)}
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "analysis.json").write_text(json.dumps({"source": {"sha256": "recording-A"}, "click_grid": {"bpm": 90}}))
            guitar.phrase_context(result, run_dir)
        self.assertEqual(result["dag_context"]["analysis"]["bpm_candidate"], 90)
        self.assertFalse(result["dag_context"]["analysis"]["reference_approved"])
        self.assertEqual(result["observations"]["proposed_review_spans"], [])

    def test_repeated_dynamic_envelope_is_candidate_only(self):
        envelope = [.1, .2, .4, .3, .8, .5, .2, .4, .9, .6, .4, .2, .7, .3, .6, .2]
        samples = []
        for gain in envelope * 2:
            samples.extend(sine(120, guitar.RATE // 2, gain))
        result = guitar.phrases(samples)
        repeated = result["observations"]["similar_envelope_region_candidates"]
        self.assertTrue(repeated)
        self.assertAlmostEqual(repeated[0]["envelope_similarity"], 1)
        self.assertEqual(result["interpretation"]["semantic_phrases"], "unknown")


if __name__ == "__main__":
    unittest.main()
