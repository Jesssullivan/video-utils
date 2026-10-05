import csv
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

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

    def selected_fixture(self, directory):
        flags = self.fixture(directory)
        relative = "comparisons/revision-1/comparison.json"
        selected = directory / relative
        selected.parent.mkdir(parents=True)
        selected.write_text(json.dumps({"status": "within_take_comparison_hypotheses",
                                       "flags": [flags["flags"][0]]}))
        digest = markers.sha256(selected)
        flags["evidence_artifacts"] = {"comparisons": {"selector": relative, "sha256": digest}}
        flags["flags"][0].update(selected_evidence_slot="comparisons", selected_artifact=relative,
                                  selected_artifact_sha256=digest, performance_issue_confirmed=False)
        (directory / "flags.json").write_text(json.dumps(flags))
        graph = {"source_sha256": "a" * 64, "flags_sha256": markers.sha256(directory / "flags.json"),
                 "artifact_hashes": {relative: digest},
                 "selected_evidence": {"comparisons": {"status": "verified", "selector": relative,
                     "artifact_sha256": digest, "upstream_hashes": {}, "external_context_hashes": {}}},
                 "external_context_hashes": {}}
        (directory / "dag.json").write_text(json.dumps(graph))
        return flags, graph, selected

    def test_nested_selected_graph_exports_only_flags_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            flags, graph, _ = self.selected_fixture(directory)
            flags["flags"].append(dict(flags["flags"][0]))
            (directory / "flags.json").write_text(json.dumps(flags))
            graph["flags_sha256"] = markers.sha256(directory / "flags.json")
            (directory / "dag.json").write_text(json.dumps(graph))
            result, encoded = markers.build(directory)
            self.assertEqual(len(result["markers"]), 1)
            self.assertEqual(len(list(csv.DictReader(io.StringIO(encoded)))), 1)
            self.assertEqual(result["evidence_artifacts"], flags["evidence_artifacts"])
            self.assertEqual(result["markers"][0]["selected_artifact"], "comparisons/revision-1/comparison.json")
            self.assertEqual(result["markers"][0]["status"], "needs_review")

    def test_nested_selected_artifact_change_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            _, _, selected = self.selected_fixture(directory)
            selected.write_text("changed comparative evidence")
            with self.assertRaisesRegex(ValueError, "upstream artifact is stale"):
                markers.build(directory)

    def test_absolute_and_lexically_escaped_paths_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.fixture(directory)
            for relative in (str(directory / "manifest.json"), "nested/../manifest.json",
                             "./manifest.json", "nested//manifest.json", "nested\\manifest.json",
                             "file:manifest.json"):
                with self.subTest(path=relative):
                    graph = {"source_sha256": "a" * 64, "flags_sha256": markers.sha256(directory / "flags.json"),
                             "artifact_hashes": {relative: markers.sha256(directory / "manifest.json")}}
                    (directory / "dag.json").write_text(json.dumps(graph))
                    with self.assertRaisesRegex(ValueError, "local filename"):
                        markers.build(directory)

    def test_selected_artifact_leaf_and_parent_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            directory, external = Path(temporary), Path(outside)
            _, graph, selected = self.selected_fixture(directory)
            contents = selected.read_bytes()
            selected.unlink()
            external_file = external / "comparison.json"
            external_file.write_bytes(contents)
            selected.symlink_to(external_file)
            with self.assertRaisesRegex(ValueError, "symbolic-link"):
                markers.build(directory)
            selected.unlink()
            selected.parent.rmdir()
            selected.parent.symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symbolic-link"):
                markers.build(directory)

    def test_selected_flags_cannot_use_rejected_or_mismatched_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            flags, graph, _ = self.selected_fixture(directory)
            graph["selected_evidence"]["comparisons"]["status"] = "rejected_source_mismatch"
            (directory / "dag.json").write_text(json.dumps(graph))
            with self.assertRaisesRegex(ValueError, "unverified selection"):
                markers.build(directory)
            graph["selected_evidence"]["comparisons"]["status"] = "verified"
            flags["flags"][0]["selected_artifact_sha256"] = "f" * 64
            (directory / "flags.json").write_text(json.dumps(flags))
            graph["flags_sha256"] = markers.sha256(directory / "flags.json")
            (directory / "dag.json").write_text(json.dumps(graph))
            with self.assertRaisesRegex(ValueError, "does not match"):
                markers.build(directory)

    def test_selected_flags_cannot_promote_hypotheses_to_confirmed_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            flags, graph, _ = self.selected_fixture(directory)
            flags["flags"][0]["performance_issue_confirmed"] = True
            (directory / "flags.json").write_text(json.dumps(flags))
            graph["flags_sha256"] = markers.sha256(directory / "flags.json")
            (directory / "dag.json").write_text(json.dumps(graph))
            with self.assertRaisesRegex(ValueError, "unconfirmed review hypotheses"):
                markers.build(directory)

    def test_external_registry_is_verified_and_arbitrary_external_paths_rejected(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as repository:
            directory, root = Path(temporary), Path(repository)
            _, graph, _ = self.selected_fixture(directory)
            registry = root / "program/instrument.json"
            registry.parent.mkdir()
            registry.write_text('{"tuning":"operator stated"}')
            digest = markers.sha256(registry)
            graph["external_context_hashes"] = {"program/instrument.json": digest}
            graph["selected_evidence"]["comparisons"]["external_context_hashes"] = dict(graph["external_context_hashes"])
            (directory / "dag.json").write_text(json.dumps(graph))
            with patch.object(markers, "ROOT", root):
                markers.build(directory)
                registry.write_text('{"tuning":"changed"}')
                with self.assertRaisesRegex(ValueError, "upstream artifact is stale"):
                    markers.build(directory)
                graph["external_context_hashes"] = {"other/secret.json": digest}
                (directory / "dag.json").write_text(json.dumps(graph))
                with self.assertRaisesRegex(ValueError, "instrument registry"):
                    markers.build(directory)

    def test_selected_parent_replaced_after_validation_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            directory, external = Path(temporary), Path(outside)
            _, _, selected = self.selected_fixture(directory)
            original_writer = csv.DictWriter

            def replace_parent(*arguments, **keywords):
                (external / selected.name).write_bytes(selected.read_bytes())
                selected.unlink()
                selected.parent.rmdir()
                selected.parent.symlink_to(external, target_is_directory=True)
                return original_writer(*arguments, **keywords)

            with patch.object(markers.csv, "DictWriter", side_effect=replace_parent):
                with self.assertRaisesRegex(ValueError, "symbolic-link"):
                    markers.build(directory)

    def test_source_metadata_symlink_and_unbound_selected_flag_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            flags = self.fixture(directory)
            flags["flags"][0]["selected_evidence_slot"] = "comparisons"
            (directory / "flags.json").write_text(json.dumps(flags))
            with self.assertRaisesRegex(ValueError, "verified DAG"):
                markers.build(directory)
            actual = directory / "real-manifest.json"
            (directory / "manifest.json").rename(actual)
            (directory / "manifest.json").symlink_to(actual)
            with self.assertRaisesRegex(ValueError, "symbolic-link"):
                markers.build(directory)


if __name__ == "__main__":
    unittest.main()
