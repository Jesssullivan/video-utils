import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("guitar_dag", Path(__file__).resolve().parents[1] / "scripts/dag.py")
dag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dag)
SOURCE = "a" * 64


def reference(**changes):
    return dag.validate_reference({"schema_version": 1, "approved": True, "bpm": 120,
        "subdivision": 1, "expected_onsets_seconds": [1., 2., 3., 4.],
        "onset_latency_seconds": 0., "match_window_seconds": .15, **changes}, SOURCE)


def events(times):
    return [{"kind": "broadband_attack_candidate", "audio_relative_seconds": time} for time in times]


def write(directory, name, value):
    (directory / name).write_text(json.dumps(value))


def fixture(directory):
    (directory / "cleaned.wav").write_bytes(b"test-cleaned")
    (directory / "denoised.wav").write_bytes(b"test-denoised")
    write(directory, "manifest.json", {"source": {"sha256": SOURCE}, "profile": {"name": "conservative3"},
        "timeline": {"audio_start_seconds": 12.5}, "output_sha256": {
        "cleaned.wav": dag.sha256(directory / "cleaned.wav"), "denoised.wav": dag.sha256(directory / "denoised.wav")}})


class ReferenceTests(unittest.TestCase):
    def test_missing_early_late_and_source_axis(self):
        result = dag.compare_reference(events([.94, 2.08, 4.]), reference(), 12.5)
        kinds = {flag["kind"] for flag in result["flags"]}
        self.assertIn("early_attack_candidate", kinds)
        self.assertIn("late_attack_candidate", kinds)
        self.assertIn("expected_attack_not_detected_candidate", kinds)
        early = next(flag for flag in result["flags"] if flag["kind"] == "early_attack_candidate")
        self.assertAlmostEqual(early["source_time_seconds"], 13.44)
        self.assertAlmostEqual(early["evidence"]["offset_seconds"], -.06)
        self.assertFalse(early["performance_issue_confirmed"])

    def test_explicit_latency_removed_before_alignment(self):
        result = dag.compare_reference(events([1.08, 2.08, 3.08, 4.08]), reference(onset_latency_seconds=.08), 7.)
        self.assertEqual(result["flags"], [])
        self.assertEqual(len(result["matches"]), 4)
        self.assertAlmostEqual(result["matches"][0]["observed_raw_seconds"], 1.08)

    def test_uncalibrated_offset_does_not_label_early_or_late(self):
        result = dag.compare_reference(events([1.08, 2.08, 3.08, 4.08]), reference(onset_latency_seconds=None))
        self.assertEqual({flag["kind"] for flag in result["flags"]}, {"uncalibrated_offset_review"})
        self.assertEqual(result["status"], "reference_comparison_uncalibrated")

    def test_unapproved_reference_does_not_grade(self):
        value = reference(approved=False)
        self.assertEqual(dag.compare_reference(events([1.4]), value)["flags"], [])

    def test_chord_deduplication_and_one_to_one(self):
        result = dag.compare_reference(events([1., 1., 2., 3., 4.]), reference())
        self.assertEqual(len(result["matches"]), 4)
        self.assertEqual(result["flags"], [])

    def test_matching_maximizes_count_in_dense_phrase(self):
        pairs, missing, extra = dag.match_onsets([1., 1.1], [1.09, 1.19], .1)
        self.assertEqual(pairs, [(0, 0), (1, 1)])
        self.assertEqual(missing, [])
        self.assertEqual(extra, [])

    def test_matching_minimizes_error_for_same_cardinality(self):
        pairs, _, extra = dag.match_onsets([1., 2.], [.92, 1.01, 2.], .15)
        self.assertEqual(pairs, [(0, 1), (1, 2)])
        self.assertEqual(extra, [0])

    def test_phrase_boundary_attack_flag_does_not_claim_release(self):
        ref = reference(phrase_spans=[{"start_seconds": 1., "end_seconds": 4.5, "name": "riff A"}])
        result = dag.compare_reference(events([.94, 2., 3., 4.08]), ref)
        kinds = {flag["kind"] for flag in result["flags"]}
        self.assertIn("phrase_start_alignment_candidate", kinds)
        self.assertIn("phrase_last_attack_alignment_candidate", kinds)

    def test_unmatched_before_reference_range_is_ignored(self):
        result = dag.compare_reference(events([.1, 1., 1.5, 2., 3., 4., 7.]), reference())
        unmatched = [flag for flag in result["flags"] if flag["kind"] == "unmatched_attack_candidate"]
        self.assertEqual(len(unmatched), 1)
        self.assertEqual(unmatched[0]["audio_relative_seconds"], 1.5)

    def test_click_candidates_do_not_count_as_guitar_attacks(self):
        result = dag.compare_reference([{"kind": "periodic_high_frequency_candidate", "audio_relative_seconds": 1.}], reference())
        self.assertEqual(len(result["matches"]), 0)

    def test_reference_source_binding_and_invalid_numbers(self):
        with self.assertRaises(ValueError):
            reference(source_sha256="b" * 64)
        for changes in ({"bpm": float("nan")}, {"expected_onsets_seconds": [1., 1.]},
                        {"subdivision": True}, {"match_window_seconds": .01},
                        {"phrase_spans": [{"start_seconds": 2, "end_seconds": 1}]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                reference(**changes)


class GraphTests(unittest.TestCase):
    def test_missing_analysis_no_reference_abstains(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixture(directory)
            graph, flags = dag.build(directory)
            self.assertEqual(flags["status"], "not_graded_no_approved_reference")
            self.assertEqual(flags["flags"][0]["kind"], "tempo_context_unresolved_review")
            self.assertIsNone(flags["musical_context"]["tonic"])
            self.assertFalse(graph["listening_accepted"])

    def test_raw_and_processed_lineage_are_distinct(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixture(directory)
            write(directory, "analysis.json", {"source": {"sha256": SOURCE}, "events": [], "click_grid": {"bpm": 120}})
            _, flags = dag.build(directory)
            self.assertEqual(flags["analysis_lineage"], "preliminary_raw_source")
            processed = dag.sha256(directory / "denoised.wav")
            write(directory, "analysis.json", {"source": {"sha256": processed}, "events": []})
            graph, flags = dag.build(directory)
            self.assertEqual(flags["analysis_lineage"], "post_denoise")
            row = next(row for row in graph["stages"] if row["id"] == "bpm")
            self.assertEqual(row["analysis_input_sha256"], processed)
            self.assertEqual(row["source_sha256"], SOURCE)
            (directory / "denoised.wav").write_bytes(b"tampered")
            _, flags = dag.build(directory)
            self.assertEqual(flags["analysis_lineage"], "rejected_unverified_processed_artifact")

    def test_mismatched_artifacts_cannot_be_compared(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixture(directory)
            write(directory, "analysis.json", {"source": {"sha256": "b" * 64}, "events": events([1, 2, 3, 4])})
            write(directory, "reference.json", reference())
            _, flags = dag.build(directory, directory / "reference.json")
            self.assertEqual(flags["analysis_lineage"], "rejected_source_mismatch")
            self.assertEqual(flags["matches"], [])

    def test_no_reference_uses_uncertain_phrase_spans_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixture(directory)
            write(directory, "phrases.json", {"source": {"sha256": SOURCE}, "observations": {
                "proposed_review_spans": [{"start_seconds": 2., "end_seconds": 8., "kind": "recurrence_review_candidate"}]}})
            graph, flags = dag.build(directory)
            span = next(item for item in flags["flags"] if item["kind"] == "recurrence_review_candidate")
            self.assertEqual(span["source_time_seconds"], 14.5)
            self.assertEqual(span["end_seconds"], 20.5)
            self.assertFalse(span["performance_issue_confirmed"])
            encoded = json.dumps(flags, indent=2, allow_nan=False) + "\n"
            self.assertEqual(graph["flags_sha256"], hashlib.sha256(encoded.encode()).hexdigest())
            self.assertEqual(graph["artifact_hashes"]["flags.json"], graph["flags_sha256"])
            for row in graph["stages"]:
                self.assertEqual(len(row["settings_sha256"]), 64)

    def test_rebuild_does_not_consume_old_flags_as_source_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixture(directory)
            (directory / "flags.json").write_text("stale interrupted output")
            graph, flags = dag.build(directory)
            self.assertEqual(flags["status"], "not_graded_no_approved_reference")
            self.assertEqual(graph["artifact_hashes"]["flags.json"], graph["flags_sha256"])

    def test_report_snapshot_does_not_create_hash_self_reference(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixture(directory)
            (directory / "report.html").write_text("<html>old report</html>")
            graph, _ = dag.build(directory)
            self.assertNotIn("report.html", graph["artifact_hashes"])
            row = next(row for row in graph["stages"] if row["id"] == "report")
            self.assertEqual(row["artifact_sha256"], dag.sha256(directory / "report.html"))
            self.assertEqual(row["status"], "prior_report_snapshot_unreviewed")


if __name__ == "__main__":
    unittest.main()
