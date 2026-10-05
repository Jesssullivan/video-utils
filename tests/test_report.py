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


if __name__ == "__main__":
    unittest.main()
