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

    def test_spectral_backend_stream_is_selected_without_double_counting(self):
        mixed = events([1.01, 2.01, 3.01, 4.01]) + [{"kind": "superflux_attack_candidate",
            "audio_relative_seconds": time} for time in [1., 2., 3., 4.]]
        result = dag.compare_reference(mixed, reference())
        self.assertEqual(result["attack_detector"], "superflux_attack_candidate")
        self.assertEqual(result["flags"], [])
        self.assertEqual(len(result["matches"]), 4)

    def test_reference_source_binding_and_invalid_numbers(self):
        with self.assertRaises(ValueError):
            reference(source_sha256="b" * 64)
        for changes in ({"bpm": float("nan")}, {"expected_onsets_seconds": [1., 1.]},
                        {"subdivision": True}, {"match_window_seconds": .01, "tolerance_seconds": .03},
                        {"phrase_spans": [{"start_seconds": 2, "end_seconds": 1}]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                reference(**changes)

    def test_virtuoso_high_subdivision_defaults_remain_valid(self):
        value = dag.validate_reference({"schema_version": 1, "approved": True, "bpm": 178,
            "subdivision": 32, "expected_onsets_seconds": [1., 2.]}, SOURCE)
        self.assertLessEqual(value["tolerance_seconds"], value["match_window_seconds"])


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


class AutomaticPhraseTests(unittest.TestCase):
    def phrase(self, **changes):
        return {"observations": {"segment_candidates": [{"start_seconds": 0., "end_seconds": 2.,
            "kind": "breakdown_texture_candidate", "label": "breakdown?", "confidence": .8}],
            "recurrence_candidates": [{"first_start_seconds": 0., "first_end_seconds": 2.,
            "second_start_seconds": 3., "second_end_seconds": 5., "pulse_period_seconds": .5,
            "similarity": .92, "first_onset_offsets_seconds": [.2, .7, 1.2, 1.7],
            "second_onset_offsets_seconds": [.2, .7, 1.2, 1.7], **changes}]}}

    def test_automatic_segments_and_recurrences_need_no_expected_intent(self):
        flags = dag.automatic_phrase_flags(self.phrase(), 12.5)
        kinds = {item["kind"] for item in flags}
        self.assertIn("breakdown_texture_candidate", kinds)
        self.assertIn("automatic_recurrence_review_candidate", kinds)
        self.assertFalse(any("difference" in kind for kind in kinds))
        for item in flags:
            self.assertFalse(item["requires_expected_intent"])
            self.assertFalse(item["performance_issue_confirmed"])

    def test_relative_duration_difference_is_hypothesis_not_skipped_beat(self):
        flags = dag.automatic_phrase_flags(self.phrase(second_end_seconds=5.3), 10.)
        item = next(item for item in flags if item["kind"] == "recurrence_duration_difference_review")
        self.assertAlmostEqual(item["evidence"]["duration_difference_pulses"], .6)
        self.assertEqual(item["source_time_seconds"], 13.)
        self.assertEqual(item["end_seconds"], 15.3)
        self.assertFalse(item["performance_issue_confirmed"])

    def test_motif_offset_comparison_unknown_absolute_latency(self):
        flags = dag.automatic_phrase_flags(self.phrase(second_onset_offsets_seconds=[.3, .8, 1.3, 1.8]), 0.)
        changed = [item for item in flags if item["kind"] == "recurrence_motif_timing_difference_review"]
        self.assertEqual(len(changed), 4)
        self.assertAlmostEqual(changed[0]["evidence"]["relative_difference_seconds"], .1)
        self.assertIn("constant_offset_cancels", changed[0]["evidence"]["recording_latency"])

    def test_legato_attack_density_difference_does_not_infer_missing_notes(self):
        flags = dag.automatic_phrase_flags(self.phrase(second_onset_offsets_seconds=[.2, 1.2]), 0.)
        item = next(item for item in flags if item["kind"] == "recurrence_attack_density_difference_review")
        self.assertIn("legato", item["evidence"]["warning"].lower())
        self.assertFalse(any("missing" in item["kind"] or "extra" in item["kind"] for item in flags))

    def test_overlapping_spans_and_outside_motif_rejected(self):
        for changes in ({"second_start_seconds": 1.}, {"second_onset_offsets_seconds": [3.]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                dag.automatic_phrase_flags(self.phrase(**changes), 0.)

    def test_graph_automatic_review_status_and_persisted_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixture(directory)
            write(directory, "phrases.json", {**self.phrase(), "source": {"sha256": SOURCE}})
            graph, flags = dag.build(directory)
            self.assertEqual(flags["status"], "automatic_phrase_review_candidates")
            self.assertEqual(flags["reference"]["status"], "not_supplied")
            self.assertEqual(flags["performance_grade"], "not_graded_human_review_required")
            row = next(row for row in graph["stages"] if row["id"] == "flags")
            self.assertEqual(row["settings"]["automatic_review"], flags["automatic_review_settings"])

    def test_bar_proxy_is_not_time_signature_or_downbeat_proof(self):
        phrase = self.phrase()
        phrase["observations"]["bar_proxy_candidates"] = [{"start_seconds": 0, "end_seconds": 2, "time_signature": "4/4"}]
        flags = dag.automatic_phrase_flags(phrase, 0.)
        bar = next(item for item in flags if item["kind"] == "four_pulse_group_review_candidate")
        self.assertIsNone(bar["evidence"]["time_signature"])
        self.assertEqual(bar["confidence"], "navigation_proxy_not_confirmed_bar")


if __name__ == "__main__":
    unittest.main()
