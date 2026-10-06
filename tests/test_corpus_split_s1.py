"""Generated metadata-only leakage/refusal properties; no recording or model reads."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import corpus_split_s1 as split
try:
    import annotation_v2
except ImportError:
    annotation_v2 = None


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def record(name="original", family="take1", source=None, partition="train"):
    return {"id": name, "take_family_id": family, "split": partition,
            "origin": "synthetic_fixture", "source_sha256": source or digest(family),
            "artifact_sha256": digest(name), "parent_ids": [], "augmentation_group_ids": [],
            "manifest": None, "annotation_refs": []}


class CorpusSplitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.manifest = self.root / "split.json"
        self.data = {"schema_id": split.SCHEMA, "schema_version": 1, "corpus_id": "fixture-only",
                     "revision": 1, "coverage": "sparse_or_unknown_no_negative_inference",
                     "approval_state": "unreviewed", "records": [record()], "context_refs": []}

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def validate(self, summary=False):
        self.write("split.json", self.data)
        return split.validate_split(self.manifest, self.root, summary=summary)

    def reject(self, code):
        with self.assertRaisesRegex(split.corpus.CorpusError, code):
            self.validate()

    def annotation_fixture(self):
        row = self.data["records"][0]
        manifest = {"source": {"sha256": row["source_sha256"]},
                    "timeline": {"audio_start_seconds": 2, "format_start_seconds": 1},
                    "pcm": {"duration_seconds": 8}}
        mh = self.write("run/manifest.json", manifest)
        annotation = {"id": "11111111-2222-4333-8444-555555555555",
                      "source_start_seconds": 3, "source_end_seconds": 4,
                      "category": "phrase", "status": "needs_review", "candidate_id": None,
                      "note": "Synthetic uncertain boundary — Mgła / 音; no review occurred.",
                      "created_at": "2026-10-06T06:00:00Z",
                      "updated_at": "2026-10-06T06:00:00Z",
                      "created_with": {"manifest_sha256": mh, "candidate_artifact_sha256": None},
                      "updated_with": {"manifest_sha256": mh, "candidate_artifact_sha256": None}}
        store = {"schema_version": 1, "source_sha256": row["source_sha256"], "revision": 1,
                 "annotations": [annotation], "listening_acceptance": "not_established"}
        sh = self.write("run/review-annotations.json", store)
        row["manifest"] = {"path": "run/manifest.json", "sha256": mh}
        row["annotation_refs"] = [{"store": {"path": "run/review-annotations.json", "sha256": sh},
                                   "schema_version": 1, "revision": 1,
                                   "selected_ids": [annotation["id"]]}]
        return store

    def annotation_v2_fixture(self, with_candidate=False):
        row = self.data["records"][0]
        self.write("run/manifest.json", {
            "source": {"sha256": row["source_sha256"], "path": "unavailable-fixture.mov"},
            "timeline": {"audio_start_seconds": 2, "format_start_seconds": 1},
            "pcm": {"duration_seconds": 8}})
        if with_candidate:
            self.write("run/markers.json", {"source_sha256": row["source_sha256"],
                                           "markers": [{"source_time_seconds": 3, "end_seconds": 3,
                                                        "name": "uncertain_phrase"}]})
        spec = importlib.util.spec_from_file_location(
            "corpus_s1_v2_review_fixture", Path(annotation_v2.__file__).with_name("review_server.py"))
        review = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(review)
        session = review.Session(self.root / "run", open_media=False)
        self.addCleanup(session.close)
        store = annotation_v2.AnnotationStore(session)
        request = {"schema_version": 2, "expected_revision": 0,
                   "idempotency_key": "example-00000001", "source_sha256": session.source_hash,
                   "manifest_sha256": session.manifest_hash,
                   "annotation": {"kind": "phrase_duration", "basis": "operator_assertion",
                                  "status": "accepted_observation",
                                  "source_span": {"start_seconds": 3, "end_seconds": 3, "extent_known": False},
                                  "reported_by": {"actor": "operator", "via": "agent"},
                                  "operator_certainty": "confirmed", "operator_quote": "Fictional test assertion 音.",
                                  "note": "Unknown duration, not a verified musical mistake."}}
        if with_candidate:
            request["annotation"]["candidate_id"] = session.markers[0]["id"]
        saved = store.write(request)
        row["manifest"] = {"path": "run/manifest.json", "sha256": session.manifest_hash}
        row["annotation_refs"] = [{"store": {"path": "run/review-annotations-v2.json",
                                             "sha256": hashlib.sha256(store.path.read_bytes()).hexdigest()},
                                   "schema_version": 2, "revision": 1,
                                   "selected_ids": [saved["annotations"][0]["id"]]}]
        return saved, store

    def refresh_store(self, store):
        self.data["records"][0]["annotation_refs"][0]["store"]["sha256"] = self.write(
            "run/review-annotations.json", store)

    def test_empty_labels_unknown_and_no_audio(self):
        result = self.validate()
        self.assertEqual(result["absence_denominator"], 0)
        self.assertEqual(result["unique_selected_annotation_count"], 0)
        self.assertEqual(result["unlabelled_intervals"], "unknown_not_negative")
        self.assertFalse(result["ground_truth_established"])
        self.assertFalse(result["source_audio_read"])
        self.assertFalse(result["training_performed"])

    def test_unknown_split_is_not_assigned_or_negative(self):
        self.data["records"][0]["split"] = "unassigned"
        result = self.validate(True)
        self.assertIsNone(result["groups"][0]["assigned_split"])
        self.assertEqual(result["record_split_counts"]["unassigned"], 1)
        self.assertEqual(result["absence_denominator"], 0)

    def test_derivative_and_unassigned_member_share_family(self):
        other = record("denoised", partition="unassigned")
        other["parent_ids"] = ["original"]
        self.data["records"].append(other)
        result = self.validate()
        self.assertEqual(result["group_count"], 1)
        self.assertEqual(result["groups"][0]["unassigned_record_count"], 1)
        self.assertEqual(result["groups"][0]["assigned_split"], "train")

    def test_same_family_cannot_cross_split(self):
        self.data["records"].append(record("alternate", source=digest("different"), partition="test"))
        self.reject("cross_split_family_leakage")

    def test_forged_family_does_not_hide_shared_source(self):
        self.data["records"].append(record("alternate", family="forged", source=digest("take1"), partition="test"))
        self.reject("cross_split_family_leakage")

    def test_same_artifact_cannot_cross_split_with_forged_source(self):
        other = record("other", "other", partition="test")
        other["artifact_sha256"] = self.data["records"][0]["artifact_sha256"]
        self.data["records"].append(other)
        self.reject("cross_split_family_leakage")

    def test_forged_parent_source_refused(self):
        other = record("other", "other")
        other["parent_ids"] = ["original"]
        self.data["records"].append(other)
        self.reject("parent_source_mismatch")

    def test_shared_augmentation_cannot_cross_split(self):
        first = self.data["records"][0]
        first["augmentation_group_ids"] = ["augmentation-42"]
        other = record("other", "other", partition="test")
        other["augmentation_group_ids"] = ["augmentation-42"]
        self.data["records"].append(other)
        self.reject("cross_split_family_leakage")

    def test_parent_chain_transitive_leak(self):
        for i in range(1, 30):
            row = record("child" + str(i), partition="train" if i < 29 else "test")
            row["parent_ids"] = ["original" if i == 1 else "child" + str(i - 1)]
            self.data["records"].append(row)
        self.reject("cross_split_family_leakage")

    def test_missing_parent_self_parent_and_cycle(self):
        self.data["records"][0]["parent_ids"] = ["missing"]
        self.reject("missing_parent")
        self.data["records"][0]["parent_ids"] = ["original"]
        self.reject("self_parent")
        self.data["records"][0]["parent_ids"] = ["child"]
        other = record("child")
        other["parent_ids"] = ["original"]
        self.data["records"].append(other)
        self.reject("parent_cycle")

    def test_same_source_conflicting_families_refused_even_same_split(self):
        self.data["records"].append(record("other", "forged", source=digest("take1")))
        self.reject("conflicting_take_family_identity")

    def test_shared_artifact_conflicting_source_refused_same_split(self):
        other = record("other", source=digest("forged-source"))
        other["artifact_sha256"] = self.data["records"][0]["artifact_sha256"]
        self.data["records"].append(other)
        self.reject("conflicting_artifact_source")

    def test_family_origins_cannot_be_promoted(self):
        other = record("other")
        other["origin"] = "real_recording"
        self.data["records"].append(other)
        self.reject("conflicting_family_origin")

    def test_group_key_stable_under_order_and_split_rename(self):
        other = record("child")
        other["parent_ids"] = ["original"]
        self.data["records"].append(other)
        first = self.validate()["groups"][0]["group_sha256"]
        self.data["records"].reverse()
        for row in self.data["records"]:
            row["split"] = "test"
        second = self.validate()["groups"][0]["group_sha256"]
        self.assertEqual(first, second)
        self.data["records"][0]["artifact_sha256"] = digest("changed-content")
        self.assertNotEqual(second, self.validate()["groups"][0]["group_sha256"])

    def test_property_generated_240_leak_and_order_cases(self):
        for seed in (712, 941, 1381, 2718):
            rng = random.Random(seed)
            for trial in range(60):
                with self.subTest(seed=seed, trial=trial):
                    count = rng.randint(2, 20)
                    self.data["records"] = [record("r" + str(i)) for i in range(count)]
                    for i in range(1, count):
                        self.data["records"][i]["parent_ids"] = ["r" + str(rng.randrange(i))]
                    before = self.validate()["groups"]
                    rng.shuffle(self.data["records"])
                    self.assertEqual(before, self.validate()["groups"])
                    self.data["records"][rng.randrange(count)]["split"] = "test"
                    self.reject("cross_split_family_leakage")

    def test_disjoint_families_valid_independent_splits(self):
        self.data["records"].append(record("other", "other", partition="test"))
        result = self.validate()
        self.assertEqual(result["group_count"], 2)
        self.assertEqual(result["record_split_counts"]["test"], 1)

    def test_owner_v1_validator_preserves_unicode_and_review_state(self):
        store = self.annotation_fixture()
        result = self.validate()
        preserved = result["records"][0]["validated_annotation_refs"][0]["selected_annotations"][0]
        self.assertEqual(preserved, store["annotations"][0])
        self.assertEqual(result["unique_selected_annotation_count"], 1)
        summary = self.validate(True)
        self.assertNotIn("Synthetic uncertain", json.dumps(summary))
        self.assertNotIn("records", summary)
        self.assertEqual(summary["unique_selected_annotation_count"], 1)
        self.assertEqual(summary["absence_denominator"], 0)

    def test_annotation_reference_dedup_counts_distinct_from_unique(self):
        self.annotation_fixture()
        other = copy.deepcopy(self.data["records"][0])
        other.update(id="derivative", artifact_sha256=digest("derivative"), parent_ids=["original"])
        self.data["records"].append(other)
        result = self.validate()
        self.assertEqual(result["selected_annotation_reference_count"], 2)
        self.assertEqual(result["unique_selected_annotation_count"], 1)
        self.assertEqual(result["group_count"], 1)

    @unittest.skipIf(annotation_v2 is None, "S1 annotation-owner module not yet integrated")
    def test_actual_owner_v2_store_preserves_authorship_extent_and_verdict(self):
        saved, store = self.annotation_v2_fixture()
        before = store.path.read_bytes()
        result = self.validate()
        item = result["records"][0]["validated_annotation_refs"][0]["selected_annotations"][0]
        self.assertEqual(item, saved["annotations"][0])
        self.assertEqual(item["claim_label"], "USER REPORTED")
        self.assertEqual(item["musical_verdict"], "not_established")
        self.assertEqual(item["operator_certainty"], "confirmed")
        self.assertFalse(item["source_span"]["extent_known"])
        self.assertEqual(store.path.read_bytes(), before)
        self.assertEqual(self.validate(True)["absence_denominator"], 0)

    @unittest.skipIf(annotation_v2 is None, "S1 annotation-owner module not yet integrated")
    def test_actual_owner_v2_refuses_forged_verdict_manifest_and_missing_replay(self):
        _, store = self.annotation_v2_fixture()
        baseline = json.loads(store.path.read_bytes())
        for mutate, error in ((lambda value: value["annotations"][0].update(musical_verdict="confirmed_error"),
                                "annotation_v2_rejected"),
                               (lambda value: value.update(manifest_sha256=digest("wrong")),
                                "annotation_v2_rejected"),
                               (lambda value: value.pop("replay_receipts"), "annotation_v2_rejected")):
            payload = copy.deepcopy(baseline)
            mutate(payload)
            sha = self.write("run/review-annotations-v2.json", payload)
            self.data["records"][0]["annotation_refs"][0]["store"]["sha256"] = sha
            self.reject(error)

    @unittest.skipIf(annotation_v2 is None, "S1 annotation-owner module not yet integrated")
    def test_actual_owner_v2_candidate_bytes_source_and_event_identity_are_current(self):
        saved, store = self.annotation_v2_fixture(with_candidate=True)
        self.assertEqual(self.validate(True)["unique_selected_annotation_count"], 1)
        original_store = json.loads(store.path.read_bytes())
        self.write("run/markers.json", {"source_sha256": digest("foreign"), "markers": []})
        self.reject("stale_candidate_artifact")
        changed_hash = hashlib.sha256((self.root / "run/markers.json").read_bytes()).hexdigest()
        forged = copy.deepcopy(original_store)
        forged["annotations"][0]["updated_with"]["candidate_artifact_sha256"] = changed_hash
        sha = self.write("run/review-annotations-v2.json", forged)
        self.data["records"][0]["annotation_refs"][0]["store"]["sha256"] = sha
        self.reject("candidate_source_mismatch")
        self.write("run/markers.json", {"source_sha256": self.data["records"][0]["source_sha256"],
                                       "markers": [{"source_time_seconds": 7, "name": "different"}]})
        forged["annotations"][0]["updated_with"]["candidate_artifact_sha256"] = hashlib.sha256(
            (self.root / "run/markers.json").read_bytes()).hexdigest()
        sha = self.write("run/review-annotations-v2.json", forged)
        self.data["records"][0]["annotation_refs"][0]["store"]["sha256"] = sha
        self.reject("candidate_id_not_in_receipt")

    def test_annotation_stale_revision_hash_span_or_manifest_rejected(self):
        store = self.annotation_fixture()
        ref = self.data["records"][0]["annotation_refs"][0]
        ref["revision"] = 2
        self.reject("stale_annotation_revision")
        ref["revision"] = 1
        store["annotations"][0]["source_end_seconds"] = 12
        self.refresh_store(store)
        self.reject("annotation_span_out_of_bounds")
        store["annotations"][0]["source_end_seconds"] = 4
        store["annotations"][0]["updated_with"]["manifest_sha256"] = digest("stale")
        self.refresh_store(store)
        self.reject("stale_annotation_manifest")

    def test_missing_selected_annotation_and_duplicate_refs(self):
        self.annotation_fixture()
        refs = self.data["records"][0]["annotation_refs"]
        refs[0]["selected_ids"] = ["missing"]
        self.reject("selected_annotation_not_found")
        refs[0]["selected_ids"] = []
        refs.append(copy.deepcopy(refs[0]))
        self.reject("duplicate_annotation_reference")

    def test_annotation_schema_bool_and_listening_claim_rejected(self):
        store = self.annotation_fixture()
        ref = self.data["records"][0]["annotation_refs"][0]
        ref["schema_version"] = True
        self.reject("unsupported_annotation_schema")
        ref["schema_version"] = 1
        store["listening_acceptance"] = "accepted"
        self.refresh_store(store)
        self.reject("invalid_acceptance_claim")

    def test_context_is_hash_bound_operator_intent_not_labels(self):
        source = self.data["records"][0]["source_sha256"]
        context = {"source_sha256": source, "sections": ["four intended phrases"], "expected_clicks": 404}
        sha = self.write("意図/context.json", context)
        self.data["context_refs"] = [{"metadata": {"path": "意図/context.json", "sha256": sha},
                                     "source_sha256": source, "basis": "operator_context"}]
        result = self.validate()
        self.assertFalse(result["contexts"][0]["detected_ground_truth"])
        self.assertEqual(result["unique_selected_annotation_count"], 0)
        self.data["context_refs"][0]["basis"] = "ground_truth"
        self.reject("context_is_not_detected_ground_truth")

    def test_context_wrong_source_or_bytes_rejected(self):
        source = self.data["records"][0]["source_sha256"]
        sha = self.write("context.json", {"source_sha256": digest("wrong")})
        self.data["context_refs"] = [{"metadata": {"path": "context.json", "sha256": sha},
                                     "source_sha256": source, "basis": "operator_context"}]
        self.reject("context_source_mismatch")
        self.data["context_refs"][0]["metadata"]["sha256"] = digest("wrong-byte-hash")
        self.reject("metadata_hash_mismatch")

    def test_closed_fields_approval_coverage_and_boolean_version(self):
        baseline = copy.deepcopy(self.data)
        for key, value, code in (("extra", True, "invalid_split_manifest_fields"),
                                 ("schema_version", True, "unsupported_split_schema"),
                                 ("approval_state", "reviewed", "unsupported_approval_state"),
                                 ("coverage", "all_correct", "invalid_coverage"),
                                 ("revision", True, "invalid_revision")):
            with self.subTest(key=key):
                self.data = copy.deepcopy(baseline)
                self.data[key] = value
                self.reject(code)

    def test_identifier_limits_and_forged_unknown_split(self):
        baseline = copy.deepcopy(self.data)
        for key, value, code in (("take_family_id", "x" * 81, "invalid_identifier"),
                                 ("split", "heldout", "invalid_split"),
                                 ("source_sha256", "A" * 64, "invalid_sha256"),
                                 ("id", "\u200bhidden", "invalid_identifier"),
                                 ("origin", None, "invalid_origin")):
            with self.subTest(key=key):
                self.data = copy.deepcopy(baseline)
                self.data["records"][0][key] = value
                self.reject(code)

    def test_record_count_graph_lists_and_duplicate_ids_bounded(self):
        self.data["records"] = [record("r" + str(i), "f" + str(i)) for i in range(501)]
        self.reject("record_count_limit")
        self.data["records"] = [record(), record()]
        self.reject("duplicate_record_id")
        self.data["records"] = [record()]
        self.data["records"][0]["parent_ids"] = ["p" + str(i) for i in range(33)]
        self.reject("parent_ids")

    def test_500_record_chain_no_recursive_graph_walk(self):
        self.data["records"] = [record("r" + str(i)) for i in range(500)]
        for i in range(1, 500):
            self.data["records"][i]["parent_ids"] = ["r" + str(i - 1)]
        result = self.validate(True)
        self.assertEqual(result["record_count"], 500)
        self.assertEqual(result["group_count"], 1)

    def test_duplicate_json_keys_nonfinite_and_invalid_utf8(self):
        for raw in (b'{"schema_version":1,"schema_version":1}', b'{"value":NaN}', b'\xff'):
            self.manifest.write_bytes(raw)
            with self.assertRaises(split.corpus.CorpusError):
                split.validate_split(self.manifest, self.root)

    def test_file_limit_and_fifo_nonblocking(self):
        self.manifest.write_bytes(b" " * (split.corpus.MAX_FILE + 1))
        with self.assertRaisesRegex(split.corpus.CorpusError, "metadata_file_limit"):
            split.validate_split(self.manifest, self.root)
        if hasattr(os, "mkfifo"):
            self.manifest.unlink()
            os.mkfifo(self.manifest)
            with self.assertRaisesRegex(split.corpus.CorpusError, "metadata_not_regular_file"):
                split.validate_split(self.manifest, self.root)

    def test_total_referenced_metadata_limit(self):
        source = self.data["records"][0]["source_sha256"]
        for index in range(17):
            path = "context" + str(index) + ".json"
            sha = self.write(path, {"source_sha256": source, "context_id": index,
                                    "operator_text": "x" * 994000})
            self.data["context_refs"].append({"metadata": {"path": path, "sha256": sha},
                                              "source_sha256": source, "basis": "operator_context"})
        self.reject("metadata_total_limit")

    def test_full_output_limit_is_explicit_summary_still_validates_all_labels(self):
        store = self.annotation_fixture()
        template = store["annotations"][0]
        store["annotations"] = [{**template, "id": str(uuid.UUID(int=i + 1)), "note": "x" * 3900}
                                for i in range(200)]
        self.refresh_store(store)
        self.data["records"][0]["annotation_refs"][0]["selected_ids"] = [
            item["id"] for item in store["annotations"]]
        for index in range(1, 3):
            row = copy.deepcopy(self.data["records"][0])
            row.update(id="child" + str(index), artifact_sha256=digest("child" + str(index)),
                       parent_ids=["original"])
            self.data["records"].append(row)
        self.reject("result_output_limit")
        summary = self.validate(True)
        self.assertEqual(summary["selected_annotation_reference_count"], 600)
        self.assertEqual(summary["unique_selected_annotation_count"], 200)
        self.assertLess(len(json.dumps(summary).encode()), 5000)

    def test_symlink_traversal_and_external_manifest_refused(self):
        self.validate()
        alias = self.root / "alias.json"
        alias.symlink_to(self.manifest)
        with self.assertRaises(split.corpus.CorpusError):
            split.validate_split(alias, self.root)
        with self.assertRaisesRegex(split.corpus.CorpusError, "unsafe_metadata_path"):
            split.validate_split(self.root / "sub/../split.json", self.root)
        with self.assertRaisesRegex(split.corpus.CorpusError, "manifest_outside_corpus_root"):
            split.validate_split(self.root.parent / "outside.json", self.root)

    def test_summary_and_full_refusals_same_and_inputs_unchanged(self):
        self.annotation_fixture()
        self.validate()
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*.json")}
        for summary in (False, True):
            result = split.validate_split(self.manifest, self.root, summary)
            self.assertEqual(result["unique_selected_annotation_count"], 1)
        after = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*.json")}
        self.assertEqual(before, after)
        (self.root / "run/review-annotations.json").write_text("{}")
        for summary in (False, True):
            with self.assertRaisesRegex(split.corpus.CorpusError, "metadata_hash_mismatch"):
                split.validate_split(self.manifest, self.root, summary)

    def test_cli_summary_and_error_json_nonzero(self):
        self.validate()
        command = [sys.executable, str(ROOT / "scripts/corpus_split_s1.py"), "validate",
                   str(self.manifest), "--root", str(self.root), "--summary"]
        good = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertEqual(json.loads(good.stdout)["status"], "split_metadata_validated")
        self.manifest.write_text("{}")
        bad = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(bad.stdout, "")
        self.assertEqual(json.loads(bad.stderr)["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
