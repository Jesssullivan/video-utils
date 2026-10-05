import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import wave


spec = importlib.util.spec_from_file_location("report", Path(__file__).parents[1] / "scripts" / "report.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def manifest(self, value):
        (self.root / "manifest.json").write_text(json.dumps(value), encoding="utf-8")

    def test_missing_analysis_is_explicit_and_atomic(self):
        self.manifest({"source": {"path": '/Users/jess/Documents/<script>alert("x")</script>.mov'}})
        result = report.write_report(self.root)
        text = (self.root / "report.html").read_text()
        self.assertFalse(result["analysis_available"])
        self.assertIn("Rhythm analysis unavailable", text)
        self.assertNotIn("/Users/jess/Documents", text)
        self.assertNotIn('<script>alert("x")</script>', text)
        self.assertEqual(list(self.root.glob(".report-*")), [])
        self.assertNotIn("autoplay", text)
        self.assertIn("not a Quarto-rendered report", text)

    def test_media_escape_and_unsafe_paths(self):
        safe = 'original & " take.wav'
        (self.root / safe).write_bytes(b"not a wave")
        self.manifest({"source": "guitar <take>.mov", "outputs": {"original_audio": safe, "clean_audio": "../../outside.wav", "processed_video": "https://example.com/private.mp4"}})
        report.write_report(self.root)
        text = (self.root / "report.html").read_text()
        self.assertIn("guitar &lt;take&gt;.mov", text)
        self.assertIn("original%20%26%20%22%20take.wav", text)
        self.assertNotIn("https://example.com", text)
        self.assertNotIn("../../outside", text)
        self.assertIn("Artifact unavailable", text)

    def test_symlink_outside_run_is_rejected(self):
        with tempfile.TemporaryDirectory() as external:
            target = Path(external) / "outside.wav"
            target.write_bytes(b"audio")
            (self.root / "original.wav").symlink_to(target)
            self.assertIsNone(report.artifact(self.root, "original.wav"))

    def test_waveform_events_and_metrics(self):
        with wave.open(str(self.root / "original.wav"), "wb") as output:
            output.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
            output.writeframes(struct.pack("<h", 16384) * 8000)
        self.manifest({"source": {"path": "take.mov", "sha256": "a" * 64}, "measurements": {"original": {"integrated_lufs": -21.24}}})
        (self.root / "analysis.json").write_text(json.dumps({"source": {"sha256": "a" * 64}, "tempo": {"bpm": 88.5}}))
        (self.root / "events.csv").write_text('time_s,kind\n0.25,click\n0.5,<script>\nnan,onset\n')
        result = report.write_report(self.root)
        text = (self.root / "report.html").read_text()
        self.assertTrue(result["analysis_available"])
        self.assertIn("-21.24 LUFS", text)
        self.assertIn("88.50 BPM", text)
        self.assertIn("&lt;script&gt; at 0.500s", text)
        self.assertNotIn('cx="nan', text)
        self.assertIn("Original PCM amplitude", text)
        self.assertAlmostEqual(report.waveform(self.root / "original.wav")[1], 1.0)

    def test_missing_manifest_does_not_replace_existing_report(self):
        path = self.root / "report.html"
        path.write_text("previous")
        with self.assertRaises(ValueError):
            report.write_report(self.root)
        self.assertEqual(path.read_text(), "previous")

    def test_peer_schemas_and_float_pcm(self):
        fmt = struct.pack("<HHIIHH", 3, 1, 8000, 32000, 4, 32)
        samples = struct.pack("<f", 0.25) * 8000
        payload = b"WAVEfmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(samples)) + samples
        (self.root / "source.wav").write_bytes(b"RIFF" + struct.pack("<I", len(payload)) + payload)
        for name in ("baseline.wav", "cleaned.wav", "residue.wav"):
            (self.root / name).write_bytes(b"fixture")
        self.manifest({"source": {"path": "/Users/jess/Documents/take.mov", "sha256": "a" * 64}, "outputs": {"source": "source.wav", "baseline": "baseline.wav", "cleaned": "cleaned.wav", "residue": "residue.wav"}, "loudness": {"cleaned": {"output": {"input_i": "-18.05", "input_tp": "-1.50"}}}})
        (self.root / "analysis.json").write_text(json.dumps({"source": {"sha256": "a" * 64}, "tempo_candidates": [{"bpm": 88.5}], "metrical_interpretations": [{"bpm": 44.25}, {"bpm": 88.5}, {"bpm": 177}], "click_grid": {"bpm": 88.8, "median_absolute_residual_ms": 8.5}}))
        (self.root / "events.csv").write_text("audio_relative_seconds,kind,grid_offset_ms\n0.3,periodic_high_frequency_candidate,1\n0.7,broadband_attack_candidate,-15\n")
        report.write_report(self.root)
        text = (self.root / "report.html").read_text()
        self.assertIn('src="baseline.wav"', text)
        self.assertIn('src="cleaned.wav"', text)
        self.assertIn('src="residue.wav"', text)
        self.assertIn("-18.05 LUFS", text)
        self.assertIn("-1.50 dBTP", text)
        self.assertIn("Candidate attack offset", text)
        self.assertIn("grid offset -15.00ms", text)
        self.assertIn("playback-level normalization", text)
        self.assertIn("44.25 / 88.50 / 177.00 BPM", text)
        self.assertIn("Derived half/double pulse ambiguity", text)
        peaks, duration = report.waveform(self.root / "source.wav")
        self.assertAlmostEqual(duration, 1)
        self.assertAlmostEqual(max(peaks), 0.25)

    def test_unrelated_analysis_rejected_and_events_not_plotted(self):
        self.manifest({"source": {"path": "take.mov", "sha256": "a" * 64}})
        (self.root / "analysis.json").write_text(json.dumps({"source": {"sha256": "b" * 64}, "tempo": {"bpm": 999}, "events": [{"time_s": 0.2, "kind": "unrelated_event"}]}))
        (self.root / "events.csv").write_text("time_s,kind\n0.1,stale_event\n")
        result = report.write_report(self.root)
        text = (self.root / "report.html").read_text()
        self.assertFalse(result["analysis_available"])
        self.assertEqual(result["event_count"], 0)
        self.assertIn("rejected_unrelated_or_modified_source", text)
        self.assertNotIn("999.00 BPM", text)
        self.assertNotIn("unrelated_event", text)
        self.assertNotIn("stale_event", text)

    def test_derivative_analysis_requires_current_artifact_hash(self):
        derived = self.root / "denoised.wav"
        derived.write_bytes(b"verified derivative")
        fingerprint = report.sha256(derived)
        self.manifest({"source": {"path": "take.mov", "sha256": "a" * 64}, "outputs": {"denoised": "denoised.wav"}, "output_sha256": {"denoised.wav": fingerprint}})
        (self.root / "analysis.json").write_text(json.dumps({"source": {"sha256": fingerprint}, "tempo": {"bpm": 88}}))
        result = report.write_report(self.root)
        self.assertTrue(result["analysis_available"])
        self.assertEqual(result["analysis_lineage"], "verified_run_derivative_hash_bound")
        derived.write_bytes(b"modified derivative")
        self.assertFalse(report.write_report(self.root)["analysis_available"])

    def test_actual_export_schema_discovers_video_and_verifies_hash(self):
        self.manifest({"source": {"path": "/Users/jess/Documents/take.mov", "sha256": "a" * 64}})
        export = self.root / "export"
        export.mkdir()
        video = export / "cleaned-video.mov"
        video.write_bytes(b"video fixture")
        outcome = {"source_sha256": "a" * 64, "video": str(video), "output_sha256": {video.name: report.sha256(video)}, "final_audio_loudness": {"input_i": "-18.12", "input_tp": "-1.40"}, "verification": {"video_frame_count_preserved": True, "final_true_peak_within_target": True}}
        (export / "outcome.json").write_text(json.dumps(outcome))
        result = report.write_report(self.root)
        text = (self.root / "report.html").read_text()
        self.assertIn('src="export/cleaned-video.mov"', text)
        self.assertNotIn(str(self.root), text)
        self.assertNotIn("/Users/jess/Documents", text)
        self.assertIn("-18.12 LUFS", text)
        self.assertIn("Video frame count preserved: passed", text)
        self.assertEqual(result["export_evidence"], "source_and_video_hash_verified")
        video.write_bytes(b"modified video")
        result = report.write_report(self.root)
        self.assertEqual(result["export_evidence"], "rejected_export_hash_mismatch")
        self.assertNotIn('src="export/cleaned-video.mov"', (self.root / "report.html").read_text())

    def test_review_flags_seek_times_and_stale_dag(self):
        self.manifest({"source": {"path": "take.mov", "sha256": "a" * 64}, "timeline": {"audio_start_seconds": 1.2, "format_start_seconds": 0.2}})
        flags = {"source_sha256": "a" * 64, "status": "reference_comparison_candidates", "flags": [{"kind": "phrase_<candidate>", "source_time_seconds": 3.2, "end_seconds": 4.2, "status": "needs_review", "confidence": "heuristic"}]}
        flag_path = self.root / "flags.json"
        flag_path.write_text(json.dumps(flags))
        graph = {"source_sha256": "a" * 64, "flags_sha256": report.sha256(flag_path), "stages": [{"id": "phrases", "status": "source_hash_bound"}]}
        (self.root / "dag.json").write_text(json.dumps(graph))
        (self.root / "markers.json").write_text(json.dumps({"source_sha256": "a" * 64, "flags_sha256": report.sha256(flag_path), "markers": [{"name": "candidate"}]}))
        report.write_report(self.root)
        text = (self.root / "report.html").read_text()
        self.assertIn("phrase_&lt;candidate&gt;", text)
        self.assertIn('data-media="audio" data-time="2.000000"', text)
        self.assertIn('data-media="video" data-time="3.000000"', text)
        self.assertIn("1 source-bound generic markers", text)
        self.assertNotIn(".play()", text)
        flags["flags"][0]["kind"] = "changed_candidate"
        flag_path.write_text(json.dumps(flags))
        result = report.write_report(self.root)
        self.assertEqual(result["auxiliary_evidence"]["dag"], "rejected_stale_flags_hash")
        self.assertNotIn("changed_candidate", (self.root / "report.html").read_text())

    def test_feature_exports_require_lineage_and_show_uncertainty(self):
        derived = self.root / "denoised.wav"
        derived.write_bytes(b"analysis input")
        fingerprint = report.sha256(derived)
        self.manifest({"source": {"path": "take.mov", "sha256": "a" * 64}, "output_sha256": {"denoised.wav": fingerprint}})
        tone = {"source": {"sha256": fingerprint}, "observations": {"sampled_band_energies": [{"low_hz": 32, "high_hz_exclusive": 80, "rms_dbfs": -40.852, "fraction_of_ac_energy": .01048}]}}
        noise = {"source": {"sha256": fingerprint}, "observations": {"quiet_candidate_windows": [{"start_seconds": 4, "end_seconds": 4.5, "rms_dbfs": -35.829}]}}
        notes = {"source": {"sha256": fingerprint}, "observations": {"sparse_analysis_frames": [{"start_seconds": 2, "periodicity_candidate": {"frequency_hz": 169.09, "normalized_autocorrelation_score": .696}}]}, "interpretation": {"tonic": None, "mode": None, "note_transcription": "unsupported"}}
        for name, value in [("tone", tone), ("noise", noise), ("notes", notes)]:
            (self.root / f"{name}.json").write_text(json.dumps(value))
        result = report.write_report(self.root)
        text = (self.root / "report.html").read_text()
        self.assertIn("32–80 Hz", text)
        self.assertIn("-40.85 dBFS", text)
        self.assertIn("169.09 Hz", text)
        self.assertIn("Tonic: unknown", text)
        self.assertIn("Mode: unknown", text)
        self.assertIn("4.000–4.500s", text)
        self.assertEqual(result["feature_evidence"]["tone"], "verified_run_derivative_hash_bound")
        derived.write_bytes(b"changed input")
        report.write_report(self.root)
        text = (self.root / "report.html").read_text()
        self.assertNotIn("-40.85 dBFS", text)
        self.assertNotIn("169.09 Hz", text)

    def test_declared_tempo_and_automatic_phrase_proposals(self):
        self.manifest({"source": {"path": "take.mov", "sha256": "a" * 64}, "timeline": {"audio_start_seconds": 10, "format_start_seconds": 9}})
        analysis = {"source": {"sha256": "a" * 64}, "declared_tempo": {"bpm": 178, "status": "operator_declared_not_audio_verified"}, "click_grid": {"bpm": 177.6}, "subdivisions": {"candidates": [{"subdivisions_per_declared_or_fitted_pulse": 4, "within_tolerance_fraction": .6, "tolerance_ms": 20, "median_absolute_offset_ms": 15}]}}
        (self.root / "analysis.json").write_text(json.dumps(analysis))
        phrases = {"source": {"sha256": "a" * 64, "audio_stream_start_seconds": 10}, "observations": {"proposed_review_spans": [{"start_seconds": 2, "end_seconds": 7, "source_start_seconds": 12, "source_end_seconds": 17, "kind": "low_register_riff_or_breakdown_candidate", "label": "riff_<region>", "confidence": .8, "evidence": "beat_synchronous_multifeature_segmentation"}, {"start_seconds": 8, "end_seconds": 12, "kind": "multifeature_recurrence_candidate", "reference_start_seconds": 2, "score": .91}], "bar_proxy_candidates": [{"start_seconds": 2, "end_seconds": 3.35, "time_signature": None}], "novelty_curve": [{"seconds": 0, "score": 0}, {"seconds": 2, "score": .8}, {"seconds": 7, "score": .2}]}}
        (self.root / "phrases.json").write_text(json.dumps(phrases))
        result = report.write_report(self.root)
        text = (self.root / "report.html").read_text()
        self.assertTrue(result["analysis_available"])
        self.assertIn("178 BPM", text)
        self.assertIn("177.60 BPM", text)
        self.assertIn("Operator-declared tempo", text)
        self.assertIn("4 per pulse", text)
        self.assertIn("riff_&lt;region&gt;", text)
        self.assertIn("12.000–17.000s", text)
        self.assertIn('data-media="video" data-time="3.000000"', text)
        self.assertIn("Compare recurrence", text)
        self.assertIn("Four-pulse bar hypotheses", text)
        self.assertIn("without an intended score", text)
        self.assertNotIn("confirmed verse", text.split("Automatic labels")[0])

    def selected_graph(self, payloads):
        self.manifest({"source": {"path": "/Users/jess/Documents/take.mov", "sha256": "a" * 64}, "timeline": {"audio_start_seconds": 10, "format_start_seconds": 9}})
        upstream = self.root / "analysis.json"
        upstream.write_text(json.dumps({"source": {"sha256": "a" * 64}}))
        hashes = {"analysis.json": report.sha256(upstream), "manifest.json": report.sha256(self.root / "manifest.json")}
        selections = {}
        for name, payload in payloads.items():
            path = self.root / "selected" / name / "result.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(payload))
            local = path.relative_to(self.root).as_posix()
            digest = report.sha256(path)
            hashes[local] = digest
            selections[name] = {"status": "verified", "selector": local, "artifact_sha256": digest, "upstream_hashes": {"analysis.json": hashes["analysis.json"]}, "payload_status": payload.get("status"), "timing_status": "bulk_dsp_delay_compensated_detector_and_physical_sync_unverified"}
        graph = {"source_sha256": "a" * 64, "artifact_hashes": hashes, "selected_evidence": selections}
        (self.root / "dag.json").write_text(json.dumps(graph))
        return graph

    def test_selected_features_retain_sparse_coverage_unknowns_and_abstention(self):
        self.selected_graph({
            "clicks": {"status": "candidate_analysis_only", "identity_status": "unverified", "summary": {"candidate_count": 7, "abstained_count": 5}, "events": [{"audio_relative_seconds": 2, "source_timeline_seconds": 12, "decision": "abstained", "reason": "overlap_<guitar>"}]},
            "pitch": {"status": "experimental_candidate_analysis", "analysis": {"coverage_fraction": .132484, "coverage_seconds": 20, "sampling": "distributed_excerpts_including_ending", "coverage_spans_source_timeline": [{"start_seconds": 10, "end_seconds": 15}]}, "summary": {"abstained_frame_count": 120}, "observations": {"analyzed_excerpts": [{"branches": [{"frames": [{"frequency_hz": 32.70, "audio_relative_seconds": 1, "source_timeline_seconds": 11, "window_start_seconds_source_timeline": 10.872, "window_end_seconds_source_timeline": 11.128, "note_mapping": {"note": "C1"}}]}]}]}},
            "meter": {"status": "unknown", "time_signature": None, "aliases": [{"pulse_bpm": 88.8, "status": "unknown", "selected": None, "reason": "uniform_or_continuous_energy"}]},
            "tonal": {"status": "tonal_context_hypotheses", "tonic": None, "mode": None, "whole_take": {"status": "abstained", "normalized_pitch_class_entropy": .976, "abstention_reasons": ["near_uniform"], "profile_families": {"family_<a>": {"ranked_hypotheses": [{"tonic_candidate": "C", "mode_candidate": "minor", "profile_correlation": .334}], "top_hypothesis_screen": "ambiguous_or_weak_candidate"}}}, "regions": [{"status": "abstained"}]},
            "comparisons": {"status": "within_take_comparison_hypotheses", "comparisons": [{"spans": {"first_start_seconds": 1, "first_end_seconds": 3, "second_start_seconds": 5, "second_end_seconds": 7}, "status": "aligned_hypothesis", "median_relative_offset_seconds": .05, "interior_rate_median": 1.08, "motif_comparison": {"status": "attack_edits_abstained"}}]}})
        result = report.write_report(self.root)
        text = (self.root / "report.html").read_text()
        self.assertEqual(set(result["selected_evidence"].values()), {"verified"})
        for fragment in ["13.25%", "20.00 seconds", "32.70 Hz · C1", "10.872–11.128s", "Notated time signature: <strong>unknown", "family_&lt;a&gt;", "Tonic: <strong>unknown", "Mode: <strong>unknown", "attack_edits_abstained", "overlap_&lt;guitar&gt;", 'data-time="3.000000"', 'href="selected/pitch/result.json"']:
            self.assertIn(fragment, text)
        self.assertNotIn("/Users/jess/Documents", text)
        self.assertNotIn("autoplay", text)

    def test_unselected_receipts_are_never_discovered(self):
        self.manifest({"source": {"sha256": "a" * 64}})
        (self.root / "pitch.json").write_text(json.dumps({"analysis": {"coverage_seconds": 999}}))
        result = report.write_report(self.root)
        self.assertEqual(result["selected_evidence"]["pitch"], "not_selected")
        self.assertNotIn("999.00 seconds", (self.root / "report.html").read_text())

    def test_changed_selected_or_upstream_receipt_excludes_evidence(self):
        graph = self.selected_graph({"clicks": {"summary": {"candidate_count": 913}}})
        report.write_report(self.root)
        self.assertIn("Candidates: 913", (self.root / "report.html").read_text())
        path = self.root / graph["selected_evidence"]["clicks"]["selector"]
        path.write_text(json.dumps({"summary": {"candidate_count": 914}}))
        result = report.write_report(self.root)
        self.assertTrue(result["selected_evidence"]["clicks"].startswith("rejected"))
        self.assertNotIn("Candidates: 914", (self.root / "report.html").read_text())
        path.write_text(json.dumps({"summary": {"candidate_count": 913}}))
        (self.root / "analysis.json").write_text(json.dumps({"source": {"sha256": "a" * 64}, "changed": True}))
        self.assertTrue(report.write_report(self.root)["selected_evidence"]["clicks"].startswith("rejected"))
        self.assertNotIn("Candidates: 913", (self.root / "report.html").read_text())

    def test_selected_symlink_rejected_even_inside_run(self):
        graph = self.selected_graph({"clicks": {"summary": {"candidate_count": 913}}})
        path = self.root / graph["selected_evidence"]["clicks"]["selector"]
        target = path.with_name("actual.json")
        path.rename(target)
        path.symlink_to(target.name)
        result = report.write_report(self.root)
        self.assertTrue(result["selected_evidence"]["clicks"].startswith("rejected"))
        self.assertNotIn("Candidates: 913", (self.root / "report.html").read_text())

    def test_external_tuning_change_rejects_selected_and_flags(self):
        graph = self.selected_graph({"meter": {"time_signature": "bad_meter"}})
        graph["external_context_hashes"] = {"program/instrument.json": "f" * 64}
        (self.root / "dag.json").write_text(json.dumps(graph))
        (self.root / "flags.json").write_text(json.dumps({"source_sha256": "a" * 64, "flags": [{"kind": "stale_tuning_flag", "source_time_seconds": 11}]}))
        result = report.write_report(self.root)
        text = (self.root / "report.html").read_text()
        self.assertEqual(result["auxiliary_evidence"]["dag"], "rejected_stale_external_context")
        self.assertNotIn("bad_meter", text)
        self.assertNotIn("stale_tuning_flag", text)

    def test_selected_output_strings_are_bounded_and_escaped(self):
        self.selected_graph({"clicks": {"events": [{"reason": "<script>" + "x" * 100000, "decision": "<bad>"}]}})
        report.write_report(self.root)
        text = (self.root / "report.html").read_text()
        self.assertIn("&lt;script&gt;", text)
        self.assertNotIn("x" * 601, text)
        self.assertLess(len(text), 50000)

    def test_rejected_selection_does_not_open_malformed_receipt(self):
        graph = self.selected_graph({"clicks": {"summary": {"candidate_count": 123}}})
        receipt = self.root / graph["selected_evidence"]["clicks"]["selector"]
        receipt.write_text("not JSON")
        graph["selected_evidence"]["clicks"]["status"] = "rejected_settings_hash_mismatch"
        graph["artifact_hashes"].pop(graph["selected_evidence"]["clicks"]["selector"])
        (self.root / "dag.json").write_text(json.dumps(graph))
        result = report.write_report(self.root)
        self.assertEqual(result["selected_evidence"]["clicks"], "rejected_settings_hash_mismatch")
        self.assertNotIn("Candidates: 123", (self.root / "report.html").read_text())

    def test_selected_candidate_numeric_booleans_remain_unknown(self):
        self.selected_graph({"pitch": {"analysis": {"coverage_fraction": True, "coverage_seconds": False}}})
        report.write_report(self.root)
        self.assertIn("Pitch excerpt coverage: unknown · unknown seconds", (self.root / "report.html").read_text())


if __name__ == "__main__":
    unittest.main()
