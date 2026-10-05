import importlib.util
import json
import math
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
SPEC = importlib.util.spec_from_file_location("phrase_comparison",Path(__file__).resolve().parents[1]/"scripts/phrase_compare.py")
compare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compare)


def vector(time):
    return [math.sin((k+1)*time*1.3) for k in range(12)] + [max(0,math.cos(time*2+k)) for k in range(12)]


def fixture(rate=1.,shift=0.,omitted=False,**changes):
    first_times = [i*.05 for i in range(40)]
    second_times = [3+i*.05 for i in range(round(40*rate))]
    times = first_times+second_times
    vectors = [vector(time) for time in first_times]+[vector(max(0,min(2,(time-3-shift)/rate))) for time in second_times]
    onsets = [.2,.6,1.,1.4,1.8]
    second_onsets = [time*rate+shift for time in onsets if not (omitted and time==1.)]
    pair = {"first_start_seconds":0.,"first_end_seconds":2.,"second_start_seconds":3.,"second_end_seconds":3+2*rate,
            "first_onset_offsets_seconds":onsets,"second_onset_offsets_seconds":second_onsets,
            "pulse_period_seconds":.5,"similarity":.95,"onset_detector":"synthetic_known_attacks",
            "detector_confidence":.95,"first_boundary_confidence":.9,"second_boundary_confidence":.9,**changes}
    return pair,times,vectors


class CompareTests(unittest.TestCase):
    def result(self,**changes):
        pair,times,vectors=fixture(**changes)
        return compare.compare_pair(pair,times,vectors,compare.validate_settings(),source_start=12.5)

    def test_identical_motif_has_no_difference_flags(self):
        result=self.result()
        self.assertEqual(result["status"],"aligned_hypothesis")
        self.assertLess(result["mean_feature_cost"],1e-10)
        self.assertEqual(result["flags"],[])
        self.assertEqual(len(result["motif_comparison"]["matches"]),5)

    def test_shifted_motif_relative_time_mapping(self):
        result=self.result(shift=.1)
        self.assertEqual(result["status"],"aligned_hypothesis")
        self.assertAlmostEqual(result["median_relative_offset_seconds"],.1,delta=.03)
        self.assertIn("recurrence_relative_alignment_shift_review",{item["kind"] for item in result["flags"]})
        self.assertFalse(any("attack_detection_gap" in item["kind"] for item in result["flags"]))

    def test_compressed_rushed_motif_is_relative_rate_hypothesis(self):
        result=self.result(rate=.8)
        self.assertEqual(result["status"],"aligned_hypothesis")
        self.assertAlmostEqual(result["interior_rate_median"],.8,delta=.08)
        self.assertIn("recurrence_relative_rate_difference_review",{item["kind"] for item in result["flags"]})
        self.assertLessEqual(result["duration_rate"],1.)
        for flag in result["flags"]:
            self.assertFalse(flag["performance_issue_confirmed"])

    def test_omitted_motif_attack_with_qualified_synthetic_evidence(self):
        result=self.result(omitted=True)
        motif=result["motif_comparison"]
        self.assertEqual(motif["status"],"attack_edit_review_hypotheses")
        self.assertEqual(len(motif["unmatched_first"]),1)
        flags=[item for item in result["flags"] if item["kind"]=="recurrence_attack_detection_gap_review"]
        self.assertEqual(len(flags),1)
        self.assertAlmostEqual(flags[0]["source_time_seconds"],16.5)
        self.assertIn("not missed/extra notes",flags[0]["evidence"]["warning"])

    def test_legato_abstains_from_attack_edit_flags(self):
        result=self.result(omitted=True,articulation_hint="legato")
        self.assertEqual(result["motif_comparison"]["status"],"attack_edits_abstained")
        self.assertEqual(len(result["motif_comparison"]["unmatched_first"]),1)
        self.assertFalse(any("detection_gap" in item["kind"] for item in result["flags"]))

    def test_unknown_detector_and_boundary_confidence_abstains(self):
        result=self.result(omitted=True,detector_confidence=None,second_boundary_confidence=None)
        self.assertEqual(result["motif_comparison"]["status"],"attack_edits_abstained")
        self.assertFalse(any("detection_gap" in item["kind"] for item in result["flags"]))

    def test_chord_duplicate_detected_attack_does_not_add_edit(self):
        result=self.result(second_onset_offsets_seconds=[.2,.6,.6,1.,1.4,1.8])
        self.assertEqual(result["motif_comparison"]["second_attack_count"],5)
        self.assertEqual(result["flags"],[])

    def test_additional_attack_remains_detection_hypothesis(self):
        result=self.result(second_onset_offsets_seconds=[.2,.6,.8,1.,1.4,1.8])
        self.assertEqual(len(result["motif_comparison"]["unmatched_second"]),1)
        self.assertIn("recurrence_additional_detection_review",{item["kind"] for item in result["flags"]})

    def test_constant_texture_and_silence_abstain(self):
        pair,times,vectors=fixture()
        for constant in ([0.]*24,[1.]*24):
            result=compare.compare_pair(pair,times,[constant]*len(vectors),compare.validate_settings())
            self.assertEqual(result["status"],"constant_texture_alignment_ambiguous")
            self.assertEqual(result["flags"],[])

    def test_rate_bounds_and_cell_budget_enforced(self):
        pair,times,vectors=fixture(rate=.8)
        settings=compare.validate_settings(min_rate=.9,max_rate=1.1)
        result=compare.compare_pair(pair,times,vectors,settings)
        self.assertEqual(result["status"],"duration_rate_outside_bounds")
        pair,times,vectors=fixture()
        result=compare.compare_pair(pair,times,vectors,compare.validate_settings(),cell_budget=5)
        self.assertEqual(result["status"],"cell_budget_exhausted")
        self.assertEqual(result["cells_visited"],5)

    def test_local_step_bounds_can_yield_no_path(self):
        pair,times,vectors=fixture(rate=.95)
        result=compare.compare_pair(pair,times,vectors,compare.validate_settings(min_rate=.9,max_rate=1.1))
        self.assertEqual(result["status"],"no_valid_constrained_path")

    def test_window_frame_cap_and_invalid_spans(self):
        pair,times,vectors=fixture()
        times=[i*.001 for i in range(2000)]+[3+i*.001 for i in range(2000)]
        result=compare.compare_pair(pair,times,[vector(time) for time in times],compare.validate_settings())
        self.assertEqual(result["status"],"window_frame_limits")
        pair["second_start_seconds"]=1.
        with self.assertRaises(ValueError):
            compare.compare_pair(pair,times,vectors,compare.validate_settings())

    def test_feature_mismatch_rejects_alignment_flags(self):
        pair,times,vectors=fixture(shift=.4)
        settings=compare.validate_settings()
        settings["maximum_mean_feature_cost"]=.00001
        result=compare.compare_pair(pair,times,vectors,settings)
        self.assertEqual(result["status"],"feature_mismatch_alignment_unreliable")
        self.assertEqual(result["flags"],[])

    def test_settings_invalid_bounds(self):
        for changes in ({"max_pairs":61},{"band_fraction":0},{"min_rate":1.2},{"max_rate":.9},{"band_fraction":float("nan")}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                compare.validate_settings(**changes)


class ArtifactTests(unittest.TestCase):
    def write_fixture(self,directory):
        pair,times,vectors=fixture(omitted=True)
        identity="a"*64
        features={"matrix_layout":"feature_by_frame","frame_times_audio_relative_seconds":times,
                  "mfcc":[[0.]*len(times)]+[[row[k] for row in vectors] for k in range(12)],
                  "chroma":[[row[k] for row in vectors] for k in range(12,24)]}
        values={"manifest":{"source":{"sha256":identity},"timeline":{"audio_start_seconds":12.5}},
                "analysis":{"source":{"sha256":identity},"librosa":{"features":features}},
                "phrases":{"source":{"sha256":identity},"observations":{"recurrence_candidates":[pair]}}}
        for name,value in values.items():
            (directory/f"{name}.json").write_text(json.dumps(value))
        return values

    def test_hashes_source_axis_and_no_expected_intent(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            self.write_fixture(directory)
            result=compare.build(directory,compare.validate_settings())
            self.assertEqual(result["analysis_lineage"],"preliminary_raw_source")
            self.assertFalse(result["requires_expected_intent"])
            self.assertEqual(result["performance_grade"],"not_graded")
            self.assertEqual(len(result["settings_sha256"]),64)
            self.assertEqual(len(result["comparisons"]),1)
            for name,digest in result["artifact_hashes"].items():
                self.assertEqual(digest,compare.sha256(directory/name))

    def test_unrelated_phrase_and_tampered_restored_media_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            values=self.write_fixture(directory)
            values["phrases"]["source"]["sha256"]="b"*64
            (directory/"phrases.json").write_text(json.dumps(values["phrases"]))
            with self.assertRaises(ValueError):
                compare.build(directory,compare.validate_settings())
            values["phrases"]["source"]["sha256"]="a"*64
            values["manifest"]["source"]["sha256"]="c"*64
            values["manifest"]["output_sha256"]={"denoised.wav":"a"*64}
            (directory/"phrases.json").write_text(json.dumps(values["phrases"]))
            (directory/"manifest.json").write_text(json.dumps(values["manifest"]))
            (directory/"denoised.wav").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                compare.build(directory,compare.validate_settings())

    def test_missing_features_explicit_unavailable_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            values=self.write_fixture(directory)
            values["analysis"].pop("librosa")
            (directory/"analysis.json").write_text(json.dumps(values["analysis"]))
            result=compare.build(directory,compare.validate_settings())
            self.assertEqual(result["status"],"feature_alignment_unavailable")
            self.assertEqual(result["flags"],[])

    def test_bad_feature_shapes_and_nonfinite_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            values=self.write_fixture(Path(temporary))
            features=values["analysis"]["librosa"]["features"]
            features["mfcc"][1][0]=float("nan")
            with self.assertRaises(ValueError):
                compare.feature_vectors(features)
            features["mfcc"][1][0]=0.
            features["mfcc"][0][0]=float("nan")
            with self.assertRaises(ValueError):
                compare.feature_vectors(features)
            features["mfcc"][0][0]=0.
            features["chroma"][0].pop()
            with self.assertRaises(ValueError):
                compare.feature_vectors(features)

    def test_empty_recurrence_set_is_explicitly_unavailable_for_comparison(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            values=self.write_fixture(directory)
            values["phrases"]["observations"]["recurrence_candidates"]=[]
            (directory/"phrases.json").write_text(json.dumps(values["phrases"]))
            result=compare.build(directory,compare.validate_settings())
            self.assertEqual(result["status"],"no_recurrence_candidates")
            self.assertEqual(result["cells_visited"],0)

    def test_output_cannot_overwrite_original_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            values=self.write_fixture(directory)
            values["manifest"]["source"]["path"]=str(directory/"phrase-comparisons.json")
            (directory/"manifest.json").write_text(json.dumps(values["manifest"]))
            with self.assertRaisesRegex(ValueError,"overwrite original source"):
                compare.build(directory,compare.validate_settings())

    def test_actual_cli_writes_atomic_output_and_valid_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            self.write_fixture(directory)
            worker=Path(__file__).resolve().parents[1]/"scripts/phrase_compare.py"
            result=subprocess.run([sys.executable,str(worker),str(directory),"--max-pairs","2"],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            summary=json.loads(result.stdout)
            self.assertEqual(summary["comparison_count"],1)
            output=Path(summary["comparisons_json"])
            payload=json.loads(output.read_text())
            self.assertEqual(payload["source_sha256"],"a"*64)
            self.assertEqual(output.stat().st_mode & 0o777,0o600)


if __name__=="__main__":
    unittest.main()
