"""Independent metadata fixtures; no actual take or human listening labels."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "corpus.py"
spec = importlib.util.spec_from_file_location("corpus", SCRIPT)
corpus = importlib.util.module_from_spec(spec)
spec.loader.exec_module(corpus)


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.run = self.root / "run"
        self.run.mkdir()
        self.source_hash = hashlib.sha256(b"fictional fixture source identity; no audio file").hexdigest()
        self.manifest = {"source": {"sha256": self.source_hash, "path": "unavailable-original.mov"},
                         "timeline": {"audio_start_seconds": 2, "format_start_seconds": 1},
                         "pcm": {"duration_seconds": 8}}
        mh = self.write("run/manifest.json", self.manifest)
        self.annotation = {"id": "11111111-2222-4333-8444-555555555555", "source_start_seconds": 3,
                           "source_end_seconds": 4, "category": "phrase", "status": "needs_review",
                           "note": "Fictional test observation: boundary is ambiguous.",
                           "candidate_id": None, "created_at": "2026-10-05T20:00:00+00:00",
                           "updated_at": "2026-10-05T20:00:00+00:00",
                           "created_with": {"manifest_sha256": mh, "candidate_artifact_sha256": None},
                           "updated_with": {"manifest_sha256": mh, "candidate_artifact_sha256": None}}
        self.store = {"schema_version": 1, "source_sha256": self.source_hash, "revision": 1,
                      "annotations": [self.annotation], "listening_acceptance": "not_established"}
        sh = self.write("run/review-annotations.json", self.store)
        self.label = {"annotation_id": self.annotation["id"], "reviewer_id": "fixture-reviewer",
                      "reviewed_at": "2026-10-05T20:01:00Z", "source_start_seconds": 3,
                      "source_end_seconds": 4, "label": "uncertain_phrase_boundary",
                      "certainty": "ambiguous", "alternatives": ["pick_attack", "phrase_boundary"]}
        self.entry = {"id": "synthetic-run", "origin": "synthetic_fixture", "source_sha256": self.source_hash,
                      "manifest": {"path": "run/manifest.json", "sha256": mh},
                      "annotations": {"path": "run/review-annotations.json", "sha256": sh, "revision": 1},
                      "labels": [self.label]}
        self.data = {"schema_version": 1, "corpus_id": "fixture-corpus", "revision": 1,
                     "units": "source_seconds", "coverage": "sparse_reviewed_spans",
                     "reviewers": [{"id": "fixture-reviewer", "identity": "Synthetic test identity; no human review claim"}],
                     "sources": [self.entry]}

    def write(self, name, value):
        raw = (json.dumps(value, allow_nan=False) + "\n").encode()
        (self.root / name).write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def validate(self):
        self.write("corpus.json", self.data)
        return corpus.validate(self.root / "corpus.json", self.root)

    def refresh_store(self):
        self.entry["annotations"]["sha256"] = self.write("run/review-annotations.json", self.store)

    def test_sparse_ambiguous_nonzero_timeline_never_establishes_ground_truth(self):
        before = {p.name: p.read_bytes() for p in self.run.iterdir()}
        result = self.validate()
        self.assertEqual(result["source_origin_counts"], {"real_recording": 0, "synthetic_fixture": 1})
        self.assertEqual(result["sources"][0]["source_bounds_seconds"], [1, 10])
        self.assertEqual(result["sources"][0]["selected_labels"][0]["alternatives"], self.label["alternatives"])
        self.assertFalse(result["ground_truth_established"])
        self.assertFalse(result["source_audio_read"])
        self.assertEqual(result["unlabelled_intervals"], "unknown_not_negative")
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.run.iterdir()})
        self.entry["labels"] = []
        self.assertEqual(self.validate()["label_count"], 0)

    def test_overlapping_reviewers_keep_disagreement_instead_of_voting(self):
        second = copy.deepcopy(self.annotation)
        second.update(id="22222222-3333-4444-8555-666666666666", source_start_seconds=3.5, source_end_seconds=4.5)
        self.store["annotations"].append(second)
        self.refresh_store()
        other = copy.deepcopy(self.label)
        other.update(annotation_id=second["id"], source_start_seconds=3.5, source_end_seconds=4.5,
                     label="possible_legato_transition")
        self.entry["labels"].append(other)
        result = self.validate()
        self.assertEqual(result["label_count"], 2)
        self.assertEqual(result["sources"][0]["selected_labels"][1]["label"], "possible_legato_transition")

    def test_span_and_units_cannot_silently_convert_audio_relative_or_milliseconds(self):
        self.label["source_start_seconds"] = 1
        with self.assertRaisesRegex(corpus.CorpusError, "label_span_mismatch"):
            self.validate()
        self.label["source_start_seconds"] = 3
        self.data["units"] = "milliseconds"
        with self.assertRaisesRegex(corpus.CorpusError, "source_seconds_units_required"):
            self.validate()
        self.data["units"] = "source_seconds"
        self.manifest["timeline"]["audio_start_seconds"] = None
        self.entry["manifest"]["sha256"] = self.write("run/manifest.json", self.manifest)
        with self.assertRaisesRegex(corpus.CorpusError, "invalid_source_seconds"):
            self.validate()

    def test_hash_revision_and_historical_manifest_receipts_reject_stale_labels(self):
        (self.run / "review-annotations.json").write_bytes(b"{}")
        with self.assertRaisesRegex(corpus.CorpusError, "metadata_hash_mismatch"):
            self.validate()
        self.refresh_store()
        self.entry["annotations"]["revision"] = 2
        with self.assertRaisesRegex(corpus.CorpusError, "stale_annotation_revision"):
            self.validate()
        self.entry["annotations"]["revision"] = 1
        self.manifest["profile"] = {"name": "new-render"}
        self.entry["manifest"]["sha256"] = self.write("run/manifest.json", self.manifest)
        with self.assertRaisesRegex(corpus.CorpusError, "stale_annotation_manifest"):
            self.validate()

    def test_candidate_receipt_source_and_content_are_checked(self):
        payload = {"source_sha256": self.source_hash, "markers": [{"source_time_seconds": 3, "end_seconds": 4, "name": "phrase"}]}
        ch = self.write("run/markers.json", payload)
        self.annotation["updated_with"]["candidate_artifact_sha256"] = ch
        identity = {"source_sha256": self.source_hash, "kind": "phrase", "start": 3.0, "end": 4.0}
        self.annotation["candidate_id"] = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        self.refresh_store()
        receipt = self.validate()["sources"][0]["selected_labels"][0]["candidate_artifact_receipt"]
        self.assertEqual(receipt["sha256"], ch)
        self.annotation["candidate_id"] = "e" * 64
        self.refresh_store()
        with self.assertRaisesRegex(corpus.CorpusError, "candidate_id_not_in_receipt"):
            self.validate()
        self.annotation["candidate_id"] = None
        payload["source_sha256"] = "b" * 64
        ch = self.write("run/markers.json", payload)
        self.annotation["updated_with"]["candidate_artifact_sha256"] = ch
        self.refresh_store()
        with self.assertRaisesRegex(corpus.CorpusError, "candidate_source_mismatch"):
            self.validate()
        self.write("run/markers.json", {"source_sha256": self.source_hash, "markers": ["changed"]})
        with self.assertRaisesRegex(corpus.CorpusError, "stale_candidate_artifact"):
            self.validate()

    def test_attribution_certainty_and_review_chronology_are_required(self):
        self.label["reviewer_id"] = "unlisted-person"
        with self.assertRaisesRegex(corpus.CorpusError, "reviewer_not_found"):
            self.validate()
        self.label["reviewer_id"] = "fixture-reviewer"
        self.label["certainty"] = "observation"
        with self.assertRaisesRegex(corpus.CorpusError, "observation_requires_accepted_review"):
            self.validate()
        self.annotation["status"] = "accepted_observation"
        self.refresh_store()
        self.label["alternatives"] = []
        self.assertFalse(self.validate()["ground_truth_established"])
        self.label["reviewed_at"] = "2026-10-05T19:00:00Z"
        with self.assertRaisesRegex(corpus.CorpusError, "review_predates_annotation"):
            self.validate()
        self.label["reviewed_at"] = "2026-10-05T20:01:00"
        with self.assertRaisesRegex(corpus.CorpusError, "review_timestamp_must_be_utc"):
            self.validate()

    def test_duplicate_labels_and_unverified_acceptance_claims_reject(self):
        self.entry["labels"].append(copy.deepcopy(self.label))
        with self.assertRaisesRegex(corpus.CorpusError, "duplicate_reviewer_label"):
            self.validate()
        self.entry["labels"].pop()
        self.store["listening_acceptance"] = "master_accepted"
        self.refresh_store()
        with self.assertRaisesRegex(corpus.CorpusError, "invalid_acceptance_claim"):
            self.validate()

    def test_real_and_synthetic_origins_are_separate_supplied_assertions(self):
        other = copy.deepcopy(self.entry)
        other.update(id="real-metadata-example", origin="real_recording", source_sha256="d" * 64, labels=[])
        (self.root / "other").mkdir()
        manifest = copy.deepcopy(self.manifest)
        manifest["source"]["sha256"] = "d" * 64
        store = copy.deepcopy(self.store)
        store.update(source_sha256="d" * 64, annotations=[])
        other["manifest"] = {"path": "other/manifest.json", "sha256": self.write("other/manifest.json", manifest)}
        other["annotations"] = {"path": "other/review-annotations.json", "sha256": self.write("other/review-annotations.json", store), "revision": 1}
        self.data["sources"].append(other)
        result = self.validate()
        self.assertEqual(result["source_origin_counts"], {"real_recording": 1, "synthetic_fixture": 1})
        self.assertIn("supplied_not_authenticated", result["assertion_boundary"])
        self.assertFalse(result["ground_truth_established"])

    def test_symlink_components_traversal_and_external_manifests_reject(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        external = Path(outside.name) / "external.json"
        external.write_text(json.dumps(self.store))
        (self.run / "review-annotations.json").unlink()
        (self.run / "review-annotations.json").symlink_to(external)
        with self.assertRaisesRegex(corpus.CorpusError, "metadata_unreadable_or_unsafe"):
            self.validate()
        self.entry["manifest"]["path"] = "../outside/manifest.json"
        with self.assertRaisesRegex(corpus.CorpusError, "unsafe_metadata_path"):
            self.validate()
        with self.assertRaisesRegex(corpus.CorpusError, "manifest_outside_corpus_root"):
            corpus.validate(external, self.root)
        self.entry["manifest"]["path"] = "linked/manifest.json"
        (self.root / "linked").symlink_to(self.run, target_is_directory=True)
        self.entry["annotations"]["path"] = "linked/review-annotations.json"
        with self.assertRaisesRegex(corpus.CorpusError, "metadata_unreadable_or_unsafe"):
            self.validate()

    def test_malformed_nonfinite_duplicate_and_oversized_metadata_reject(self):
        path = self.root / "corpus.json"
        for raw in (b'{"schema_version":1,"schema_version":2}', b'{"x":NaN}', b"{"):
            path.write_bytes(raw)
            with self.assertRaises(corpus.CorpusError):
                corpus.validate(path, self.root)
        path.write_bytes(b" " * (corpus.MAX_FILE + 1))
        with self.assertRaisesRegex(corpus.CorpusError, "metadata_file_limit"):
            corpus.validate(path, self.root)

    def test_total_metadata_budget_and_fifo_are_bounded_without_blocking(self):
        metadata = corpus.Metadata(self.root)
        metadata.total = corpus.MAX_TOTAL
        with self.assertRaisesRegex(corpus.CorpusError, "metadata_total_limit"):
            metadata.read("run/manifest.json")
        fifo = self.root / "pipe.json"
        import os
        os.mkfifo(fifo)
        with self.assertRaisesRegex(corpus.CorpusError, "metadata_not_regular_file"):
            corpus.Metadata(self.root).read("pipe.json")

    def test_cli_is_read_only_and_reports_rejection_without_processing(self):
        self.write("corpus.json", self.data)
        result = subprocess.run([sys.executable, str(SCRIPT), "validate", str(self.root / "corpus.json"),
                                 "--root", str(self.root)], capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "metadata_validated")
        self.label["source_end_seconds"] = 4.25
        self.write("corpus.json", self.data)
        result = subprocess.run([sys.executable, str(SCRIPT), "validate", str(self.root / "corpus.json"),
                                 "--root", str(self.root)], capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr)["error"], "label_span_mismatch")
        self.assertEqual(result.stdout, "")

    def test_existing_review_worker_store_is_accepted_without_schema_translation(self):
        # Mutate only isolated fictional metadata using the real review CLI.
        self.store.update(revision=0, annotations=[])
        self.refresh_store()
        request = {"expected_revision": 0, "annotation": {
            "source_start_seconds": 3, "source_end_seconds": 4, "category": "phrase",
            "status": "accepted_observation", "note": "Synthetic integration fixture; no take listened to."}}
        self.write("request.json", request)
        result = subprocess.run([sys.executable, str(SCRIPT.with_name("review_server.py")), "annotate",
                                 str(self.run), "--input", str(self.root / "request.json")],
                                capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = json.loads(result.stdout)
        self.label.update(annotation_id=saved["annotations"][0]["id"], certainty="observation",
                          alternatives=[], reviewed_at=saved["annotations"][0]["updated_at"])
        self.entry["annotations"]["revision"] = saved["revision"]
        self.entry["annotations"]["sha256"] = hashlib.sha256((self.run / "review-annotations.json").read_bytes()).hexdigest()
        result = self.validate()
        self.assertEqual(result["sources"][0]["selected_labels"][0]["review_status"], "accepted_observation")
        self.assertFalse(result["ground_truth_established"])

    def test_summary_retains_counts_receipts_limits_and_unchanged_bytes(self):
        self.write("corpus.json", self.data)
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*.json")}
        command = [sys.executable, str(SCRIPT), "validate", str(self.root / "corpus.json"),
                   "--root", str(self.root)]
        full = subprocess.run(command, capture_output=True, text=True, timeout=3)
        compact = subprocess.run(command + ["--summary"], capture_output=True, text=True, timeout=3)
        self.assertEqual((full.returncode, compact.returncode), (0, 0), compact.stderr)
        result, summary = json.loads(full.stdout), json.loads(compact.stdout)
        self.assertEqual(summary["result_mode"], "metadata_summary")
        self.assertEqual(summary["corpus_sha256"], result["corpus_sha256"])
        self.assertEqual(summary["source_origin_label_counts"], {"real_recording": 0, "synthetic_fixture": 1})
        self.assertEqual(summary["sources"][0]["certainty_counts"], {"observation": 0, "ambiguous": 1})
        self.assertEqual(summary["sources"][0]["review_status_counts"]["needs_review"], 1)
        self.assertEqual(summary["reviewer_count"], 1)
        self.assertNotIn("reviewers", summary)
        self.assertNotIn("selected_labels", summary["sources"][0])
        self.assertNotIn(str(self.root), compact.stdout)
        self.assertNotIn(self.label["label"], compact.stdout)
        self.assertFalse(summary["source_audio_read"])
        self.assertFalse(summary["ground_truth_established"])
        self.assertLess(len(compact.stdout.encode()), corpus.MAX_SUMMARY_BYTES)
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*.json")})

    def test_summary_runs_full_label_hash_and_unit_validation_with_same_errors(self):
        command = [sys.executable, str(SCRIPT), "validate", str(self.root / "corpus.json"),
                   "--root", str(self.root)]
        for failure in ("label_span_mismatch", "metadata_hash_mismatch", "source_seconds_units_required"):
            with self.subTest(failure=failure):
                if failure == "label_span_mismatch":
                    self.label["source_end_seconds"] = 4.25
                elif failure == "metadata_hash_mismatch":
                    self.label["source_end_seconds"] = 4
                    self.entry["annotations"]["sha256"] = "e" * 64
                else:
                    self.refresh_store()
                    self.data["units"] = "milliseconds"
                self.write("corpus.json", self.data)
                full = subprocess.run(command, capture_output=True, text=True, timeout=3)
                compact = subprocess.run(command + ["--summary"], capture_output=True, text=True, timeout=3)
                self.assertEqual((full.returncode, compact.returncode), (1, 1))
                self.assertEqual(full.stderr, compact.stderr)
                self.assertEqual(json.loads(compact.stderr)["error"], failure)
                self.assertEqual(compact.stdout, "")

    def test_summary_handles_valid_full_receipt_above_mcp_output_ceiling(self):
        # One valid sub-1MB corpus can repeat a long, verified candidate path
        # enough times that its full receipt exceeds the dispatcher's 2MiB cap.
        markers_hash = self.write("run/markers.json", {"source_sha256": self.source_hash, "markers": []})
        self.annotation["updated_with"]["candidate_artifact_sha256"] = markers_hash
        self.store["annotations"] = []
        self.entry["labels"] = []
        self.data["reviewers"] = [{"id": f"reviewer-{n}", "identity": "Fictional synthetic test reviewer"} for n in range(40)]
        for n in range(64):
            item = copy.deepcopy(self.annotation)
            item["id"] = f"{n:08x}-2222-4333-8444-555555555555"
            self.store["annotations"].append(item)
            for reviewer in self.data["reviewers"]:
                label = copy.deepcopy(self.label)
                label.update(annotation_id=item["id"], reviewer_id=reviewer["id"])
                self.entry["labels"].append(label)
        self.refresh_store()
        # Stay below macOS PATH_MAX while exercising repeated path expansion.
        deep = self.root.joinpath(*["d" * 120 + str(n) for n in range(6)])
        deep.mkdir(parents=True)
        self.run.rename(deep / "run")
        self.run = deep / "run"
        relative = self.run.relative_to(self.root).as_posix()
        self.entry["manifest"]["path"] = relative + "/manifest.json"
        self.entry["annotations"]["path"] = relative + "/review-annotations.json"
        result = self.validate()
        self.assertGreater(len(json.dumps(result).encode()), 2 * 1024 * 1024)
        summary = corpus.summarize(result)
        self.assertEqual(summary["label_count"], 2560)
        self.assertEqual(summary["sources"][0]["label_count"], 2560)
        self.assertEqual(len(summary["sources"]), 1)
        self.assertLess(len(json.dumps(summary).encode()), 5000)
        self.assertNotIn(relative, json.dumps(summary))
        compact = subprocess.run([sys.executable, str(SCRIPT), "validate", str(self.root / "corpus.json"),
                                  "--root", str(self.root), "--summary"],
                                 capture_output=True, text=True, timeout=5)
        self.assertEqual(compact.returncode, 0, compact.stderr)
        self.assertEqual(json.loads(compact.stdout)["label_count"], 2560)
        self.assertLess(len(compact.stdout.encode()), 5000)


if __name__ == "__main__":
    unittest.main()
