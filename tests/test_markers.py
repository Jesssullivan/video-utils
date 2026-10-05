import csv
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
SPEC = importlib.util.spec_from_file_location("guitar_markers", Path(__file__).resolve().parents[1] / "scripts/markers.py")
markers = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(markers)


class MarkerTests(unittest.TestCase):
    def fixture(self, directory):
        (directory / "manifest.json").write_text(json.dumps({"source": {"sha256": "a" * 64,
            "probe": {"video": {"avg_frame_rate": "30000/1001", "r_frame_rate": "30/1"}}}}))
        payload = {"source_sha256": "a" * 64, "timeline": {"audio_start_seconds": 12.5},
                   "flags": [{"source_time_seconds": 14., "end_seconds": 14.5,
                              "kind": 'riff, "unclear"\nreview', "status": "needs_review", "confidence": "unknown",
                              "evidence": {"warning": 'quote "this", then\nlisten'}}]}
        (directory / "flags.json").write_text(json.dumps(payload))
        return payload

    def test_csv_round_trips_quotes_unicode_and_newlines(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            value = self.fixture(directory)
            payload, encoded = markers.build(directory)
            rows = list(csv.DictReader(io.StringIO(encoded)))
            self.assertEqual(rows[0]["name"], value["flags"][0]["kind"])
            self.assertEqual(json.loads(rows[0]["evidence"]), value["flags"][0]["evidence"])
            self.assertEqual(float(rows[0]["source_time_seconds"]), 14.)
            self.assertIsNone(payload["frame_rate"]["frame_indices"])
            self.assertTrue(payload["editor_import"]["final_cut_pro"].startswith("unsupported"))

    def test_source_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            value = self.fixture(directory)
            value["source_sha256"] = "b" * 64
            (directory / "flags.json").write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                markers.build(directory)

    def test_stale_dag_hash_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.fixture(directory)
            (directory / "dag.json").write_text(json.dumps({"source_sha256": "a" * 64, "flags_sha256": "b" * 64}))
            with self.assertRaises(ValueError):
                markers.build(directory)

    def test_changed_upstream_rejected_even_when_flags_hash_matches(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.fixture(directory)
            (directory / "analysis.json").write_text(json.dumps({"version": "first analysis"}))
            graph = {"source_sha256": "a" * 64, "flags_sha256": markers.sha256(directory / "flags.json"),
                     "artifact_hashes": {"analysis.json": markers.sha256(directory / "analysis.json")}}
            (directory / "dag.json").write_text(json.dumps(graph))
            markers.build(directory)
            (directory / "analysis.json").write_text(json.dumps({"version": "changed analysis"}))
            with self.assertRaisesRegex(ValueError, "upstream artifact is stale"):
                markers.build(directory)

    def test_graph_cannot_read_paths_outside_run_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.fixture(directory)
            graph = {"source_sha256": "a" * 64, "flags_sha256": markers.sha256(directory / "flags.json"),
                     "artifact_hashes": {"../analysis.json": "b" * 64}}
            (directory / "dag.json").write_text(json.dumps(graph))
            with self.assertRaisesRegex(ValueError, "local filename"):
                markers.build(directory)

    def test_invalid_end_rejected_and_negative_stream_start_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            value = self.fixture(directory)
            value["flags"][0].update(source_time_seconds=-.2, end_seconds=0.)
            (directory / "flags.json").write_text(json.dumps(value))
            result, _ = markers.build(directory)
            self.assertEqual(result["markers"][0]["source_time_seconds"], -.2)
            value["flags"][0]["end_seconds"] = -.3
            (directory / "flags.json").write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                markers.build(directory)


if __name__ == "__main__":
    unittest.main()
