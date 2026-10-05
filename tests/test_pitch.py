import importlib.util
import math
from pathlib import Path
import statistics
import unittest
from unittest import mock
import subprocess

SPEC = importlib.util.spec_from_file_location("pitch", Path(__file__).resolve().parents[1] / "scripts/pitch.py")
pitch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pitch)
HAS_ANALYSIS = importlib.util.find_spec("numpy") and importlib.util.find_spec("librosa")


def signal(frequency, seconds=1, distorted=False):
    count = round(seconds*pitch.RATE)
    values = [math.sin(2*math.pi*frequency*i/pitch.RATE) for i in range(count)]
    return [.4*math.tanh(5*x) if distorted else .4*x for x in values]


class PitchContractTests(unittest.TestCase):
    def test_distributed_coverage_is_bounded_and_includes_ending(self):
        spans = pitch.schedule_excerpts(150, 20)
        self.assertEqual(len(spans), 4)
        self.assertEqual(spans[0]["start_seconds"], 0)
        self.assertEqual(spans[-1]["end_seconds"], 150)
        self.assertAlmostEqual(sum(s["end_seconds"]-s["start_seconds"] for s in spans), 20)
        self.assertTrue(all(a["end_seconds"] < b["start_seconds"] for a,b in zip(spans, spans[1:])))

    def test_explicit_excerpt_and_short_clip(self):
        self.assertEqual(pitch.schedule_excerpts(3, 20), [{"start_seconds": 0.0, "end_seconds": 3}])
        self.assertEqual(pitch.schedule_excerpts(150, 20, 145), [{"start_seconds": 145, "end_seconds": 150}])
        with self.assertRaises(ValueError):
            pitch.schedule_excerpts(150, 31)
        with self.assertRaises(ValueError):
            pitch.schedule_excerpts(150, 20, 150)

    def test_c1_and_detuning_map_to_nonunique_theoretical_string_hypotheses(self):
        context = pitch.features.instrument_context()
        c1 = 440*2**((24-69)/12)
        mapped = pitch.note_mapping(c1*2**(.25/12), context)
        self.assertEqual(mapped["note"], "C1")
        self.assertAlmostEqual(mapped["cents_from_equal_tempered_note"], 25, places=6)
        self.assertEqual(mapped["possible_string_mappings"][0]["string_number"], 9)
        self.assertEqual(mapped["possible_string_mappings"][0]["semitones_above_open"], 0)
        self.assertIsNone(mapped["identified_string"])
        high = pitch.note_mapping(349.228231433, context)
        self.assertEqual(high["note"], "F4")
        self.assertEqual(len(high["possible_string_mappings"]), 9)
        self.assertTrue(all(s["qualification"] == "hypothetical_not_identified_string_or_fret" for s in high["possible_string_mappings"]))

    def test_harmonic_support_retains_absent_fundamental_uncertainty(self):
        power = [0.0]*2049
        frequency = pitch.RATE/4096*8
        power[16] = 10
        power[24] = 5
        evidence = pitch.harmonic_evidence(power, frequency, 4096)
        self.assertEqual(evidence["harmonics"][0]["energy_fraction"], 0)
        self.assertEqual(evidence["union_energy_fraction"], 1)
        self.assertEqual(evidence["interpretation"], "spectral_support_not_probability_or_played_fundamental_identity")

    def test_assemble_preserves_window_extent_offset_and_octave_alternatives(self):
        frame = {"center_seconds_in_excerpt": .2, "window_start_seconds_in_excerpt": .072,
                 "window_end_seconds_in_excerpt": .328, "edge_context_complete": True,
                 "frequency_hz": 32.703195663, "octave_alternatives": [{"frequency_hz": 65.406391326}]}
        raw = {"excerpts": [{"start_seconds": 10, "end_seconds": 11,
                             "branches": [{"name": "low_register", "frames": [frame]}]}]}
        excerpts, summary = pitch.assemble(raw, pitch.features.instrument_context(), source_start=7)
        result = excerpts[0]["branches"][0]["frames"][0]
        self.assertAlmostEqual(result["source_timeline_seconds"], 17.2)
        self.assertAlmostEqual(result["window_start_seconds_source_timeline"], 17.072)
        self.assertEqual(result["octave_alternatives"][0]["note_mapping"]["note"], "C2")
        self.assertEqual(summary["voiced_candidate_count"], 1)
        self.assertEqual(summary["interpretation"], "overlapping_branch_hypotheses_not_unique_notes")

    def test_subprocess_analysis_has_wall_time_bound(self):
        with mock.patch.object(pitch.subprocess, "run", side_effect=subprocess.TimeoutExpired("pyin", 180)) as run:
            with self.assertRaises(subprocess.TimeoutExpired):
                pitch.bounded_extract([])
        self.assertEqual(run.call_args.kwargs["timeout"], 180)


@unittest.skipUnless(HAS_ANALYSIS, "optional locked analysis environment")
class PitchAnalysisTests(unittest.TestCase):
    def test_distorted_low_c1_is_recovered_with_octave_ambiguity(self):
        c1 = 440*2**((24-69)/12)
        result = pitch.extract_branches(signal(c1, distorted=True))
        frames = result["branches"][0]["frames"]
        candidates = [f for f in frames if f["frequency_hz"] is not None and f["edge_context_complete"]]
        self.assertGreater(len(candidates), 20)
        self.assertAlmostEqual(statistics.median(f["frequency_hz"] for f in candidates), c1, delta=.6)
        self.assertTrue(all(f["octave_alternatives"] for f in candidates))
        self.assertTrue(all("not_calibrated" in f["confidence_kind"] for f in candidates))

    def test_legato_glide_has_pitch_candidates_without_attack_reference(self):
        samples = []
        phase = 0.0
        count = pitch.RATE
        for i in range(count):
            frequency = 300*2**(i/count)
            phase += 2*math.pi*frequency/pitch.RATE
            samples.append(.3*math.sin(phase))
        branch = pitch.extract_branches(samples)["branches"][1]
        frames = [f for f in branch["frames"] if f["frequency_hz"] is not None and f["edge_context_complete"]]
        self.assertGreater(len(frames), 30)
        errors = [abs(1200*math.log2(f["frequency_hz"]/(300*2**f["center_seconds_in_excerpt"]))) for f in frames]
        self.assertLess(statistics.median(errors), 35)

    def test_missing_low_fundamental_keeps_periodicity_and_source_ambiguity(self):
        c1 = 440*2**((24-69)/12)
        samples = [.25*math.sin(2*math.pi*2*c1*i/pitch.RATE)
                   +.2*math.sin(2*math.pi*3*c1*i/pitch.RATE) for i in range(pitch.RATE)]
        frames = pitch.extract_branches(samples)["branches"][0]["frames"]
        candidates = [f for f in frames if f["frequency_hz"] is not None and f["edge_context_complete"]]
        self.assertGreater(len(candidates), 20)
        self.assertAlmostEqual(statistics.median(f["frequency_hz"] for f in candidates), c1, delta=.6)
        self.assertLess(statistics.median(f["harmonic_evidence"]["harmonics"][0]["energy_fraction"] for f in candidates), .01)
        self.assertTrue(all(f["octave_alternatives"] for f in candidates))

    def test_stepwise_sweep_retains_high_register_note_changes(self):
        samples = []
        phase = 0.0
        step_seconds = .16
        frequencies = [300*2**(step/12) for step in range(8)]
        for frequency in frequencies:
            for _ in range(round(step_seconds*pitch.RATE)):
                phase += 2*math.pi*frequency/pitch.RATE
                samples.append(.3*math.sin(phase))
        frames = pitch.extract_branches(samples)["branches"][1]["frames"]
        for step, frequency in enumerate(frequencies):
            center = (step+.5)*step_seconds
            local = [f["frequency_hz"] for f in frames if f["frequency_hz"] is not None
                     and abs(f["center_seconds_in_excerpt"]-center) < .03]
            self.assertTrue(local)
            self.assertLess(abs(1200*math.log2(statistics.median(local)/frequency)), 35)

    def test_silence_abstains(self):
        result = pitch.extract_branches([0.0]*pitch.RATE)
        self.assertTrue(all(f["frequency_hz"] is None for b in result["branches"] for f in b["frames"]))


if __name__ == "__main__":
    unittest.main()
