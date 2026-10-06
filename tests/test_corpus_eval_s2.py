"""Coverage-first corpus evaluation on synthetic and real metadata; no audio."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import annotation_v2  # noqa: E402
import corpus  # noqa: E402
import corpus_eval_s2 as evaluator  # noqa: E402
import corpus_split_s1  # noqa: E402
from test_annotation_markers import NAMESPACE, SOURCE, artifact_base, spec, write_run  # noqa: E402

EXAMPLE = "docs/spec/examples/corpus-split/operator-review-corpus.json"
REAL_FLAGS = "artifacts/runs/20261006T034521Z-a0def0c43eac/flags.json"
REAL_FLAGS_SHA = "95a0106c84a338ddc756f3c17879e5eccf8966b4344fe6326b71da7872e8a732"
STAGED = ("artifacts/experiments/s1-demo-context-20261006T0627/manifest.json",
          "artifacts/experiments/s1-demo-context-20261006T0627/review-annotations-v2.json",
          "program/demo-arrangement.json")


def ident(name):
    return str(uuid.uuid5(NAMESPACE, name))


def proposal(kind, start, end=None):
    return {"kind": kind, "source_time_seconds": start, "end_seconds": start if end is None else end,
            "confidence": 0.9, "status": "needs_review", "evidence": {"kind": kind}}


def stage_real_root(base, target):
    """Copy the example manifest and its three metadata files byte-identically; no audio."""
    for relative in STAGED:
        (target / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(base / relative, target / relative)
    (target / EXAMPLE).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / EXAMPLE, target / EXAMPLE)
    for relative in STAGED:
        assert (hashlib.sha256((target / relative).read_bytes()).digest()
                == hashlib.sha256((base / relative).read_bytes()).digest())


class CorpusEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.proposal_dir = self.root / "proposal-run"
        self.proposal_dir.mkdir()

    def corpus(self, items, *, duration=20.0, source=SOURCE, selected=None):
        _, store_sha = write_run(self.root / "run", items, duration=duration, source=source)
        manifest_sha = hashlib.sha256((self.root / "run" / "manifest.json").read_bytes()).hexdigest()
        split = {"schema_id": corpus_split_s1.SCHEMA, "schema_version": 1, "corpus_id": "synthetic-eval",
                 "revision": 1, "coverage": "sparse_or_unknown_no_negative_inference",
                 "approval_state": "unreviewed", "context_refs": [],
                 "records": [{"id": "take", "take_family_id": "fam", "split": "unassigned",
                              "origin": "synthetic_fixture", "source_sha256": source, "artifact_sha256": source,
                              "parent_ids": [], "augmentation_group_ids": [],
                              "manifest": {"path": "run/manifest.json", "sha256": manifest_sha},
                              "annotation_refs": [{"store": {"path": "run/review-annotations-v2.json",
                                                             "sha256": store_sha},
                                                   "schema_version": 2, "revision": len(items),
                                                   "selected_ids": selected if selected is not None else
                                                   [ident(item["name"]) for item in items]}]}]}
        (self.root / "split.json").write_text(json.dumps(split))
        return self.root / "split.json"

    def proposals(self, flags, *, source=SOURCE, axis="original_source_stream_timestamps_seconds"):
        path = self.proposal_dir / "flags.json"
        path.write_text(json.dumps({"source_sha256": source, "timeline": {"audio_start_seconds": 0.0, "axis": axis},
                                    "flags": flags}))
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def evaluate(self, items, flags, **kwargs):
        split = self.corpus(items, **{k: v for k, v in kwargs.items() if k in ("duration", "selected")})
        path, digest = self.proposals(flags, **{k: v for k, v in kwargs.items() if k in ("source", "axis")})
        return evaluator.evaluate(split, local_root=self.root, proposals_path=path, proposals_sha256=digest)

    def test_coverage_union_arithmetic(self):
        items = [spec("a", basis="operator_context", quote=None, start=0, end=4),
                 spec("b", start=2, end=6), spec("c", basis="reference_comparison", quote=None, start=10, end=12),
                 spec("point", start=15, extent=False),
                 spec("det", basis="detector_hypothesis", quote=None, start=16, end=20)]
        record = self.evaluate(items, [])["records"][0]
        coverage = record["coverage"]
        self.assertEqual((coverage["covered_seconds"], coverage["total_seconds"]), (8.0, 20.0))
        self.assertAlmostEqual(coverage["coverage_fraction"], 0.4)
        self.assertEqual(coverage["covered_intervals"], [[0.0, 6.0], [10.0, 12.0]])
        self.assertEqual(coverage["meaning"], "reviewer_attended_region_not_reviewed_absence")

    def test_below_threshold_nulls_precision_and_recall(self):
        result = self.evaluate([spec("a", start=1, end=3)], [proposal("spectral_texture_region_candidate", 1.5)])
        metrics = result["records"][0]["metrics"]
        self.assertEqual((metrics["precision"], metrics["recall"]), (None, None))
        self.assertEqual(metrics["reason"], "coverage_below_threshold")
        self.assertEqual(metrics["precision_reason"], "false_positive_requires_reviewed_absence_label")
        for key in ("negatives", "true_negatives", "false_positives"):
            self.assertIsNone(metrics[key])
        self.assertEqual((result["negatives_inferred"], result["unlabelled_intervals"],
                          result["ground_truth_established"], result["source_audio_read"]),
                         (0, "unknown_not_negative", False, False))

    def test_recall_with_numerator_denominator_and_precision_null(self):
        items = [spec("ctx", basis="operator_context", quote=None, start=0, end=12),
                 spec("p1", start=1, end=2), spec("p2", start=4, end=5), spec("p3", start=8, end=9),
                 spec("unsure", status="needs_review", start=10, end=11)]
        flags = [proposal("automatic_recurrence_review_candidate", 1.5, 3.0),
                 proposal("spectral_texture_region_candidate", 8.5), proposal("some_kind", 10.5)]
        metrics = self.evaluate(items, flags)["records"][0]["metrics"]
        self.assertEqual((metrics["recall_numerator"], metrics["recall_denominator"]), (2, 3))
        self.assertAlmostEqual(metrics["recall"], 2 / 3)
        self.assertIsNone(metrics["precision"])
        self.assertEqual(metrics["labelled_positive_count"], 3)
        self.assertEqual([m["annotation_id"] for m in metrics["matches"]], [ident("p1"), ident("p3")])

    def test_unlabelled_uncovered_proposals_change_no_number(self):
        items = [spec("ctx", basis="operator_context", quote=None, start=0, end=12), spec("p1", start=1, end=2),
                 spec("p2", start=4, end=5)]
        base = [proposal("automatic_recurrence_review_candidate", 1.5)]
        first = self.evaluate(items, base)["records"][0]
        extra = base + [proposal("spectral_texture_region_candidate", t, t + 1) for t in (13.0, 15.0, 18.0)]
        second = self.evaluate(items, extra)["records"][0]
        for key in ("coverage", "metrics", "error_axes", "articulation_axes", "articulation_unspecified",
                    "not_scored_kinds", "clock_alignment_status"):
            self.assertEqual(first[key], second[key], key)
        self.assertEqual(second["proposals"]["eligible_count"], 4)

    def test_axes_are_separate_and_articulation_is_not_spread(self):
        items = [spec("ctx", basis="operator_context", quote=None, start=0, end=15),
                 spec("t1", kind="rhythm_timing", start=1, end=2), spec("t2", kind="rhythm_pattern", start=3, end=4),
                 spec("om", kind="phrase_omission", start=5, end=6), spec("pi", kind="melodic_pitch", start=7, end=8),
                 spec("ar", kind="articulation", start=9, end=10), spec("re", kind="rest_execution", start=11, end=12),
                 spec("tone", kind="tone", start=13, end=14)]
        record = self.evaluate(items, [proposal("x", 1.5), proposal("y", 9.5)])["records"][0]
        errors, articulation = record["error_axes"], record["articulation_axes"]
        self.assertEqual({k: v["labelled_positive_count"] for k, v in errors.items()},
                         {"timing": 2, "omission": 1, "duration": 0, "pitch": 1})
        self.assertEqual((errors["timing"]["recall_numerator"], errors["timing"]["recall_denominator"]), (1, 2))
        self.assertEqual(errors["duration"]["reason"], "no_labelled_positives")
        self.assertIs(errors["pitch"]["reference_required"], True)
        self.assertEqual(errors["pitch"]["note_correctness"], "not_established")
        self.assertEqual(articulation["rest"]["labelled_positive_count"], 1)
        for axis in ("palm_mute", "legato", "tapping", "sweep", "chord"):
            self.assertEqual((articulation[axis]["status"], articulation[axis]["reason"],
                              articulation[axis]["detector_for_axis"], articulation[axis]["labelled_positive_count"]),
                             ("unknown", "no_subtype_in_v2_schema", "none", 0))
        unspecified = record["articulation_unspecified"]
        self.assertEqual((unspecified["labelled_positive_count"], unspecified["recall_numerator"],
                          unspecified["spread_to_articulation_axes"]), (1, 1, False))
        self.assertEqual(record["not_scored_kinds"]["tone"]["selected_count"], 1)
        self.assertEqual(set(errors) | set(articulation), {"timing", "omission", "duration", "pitch", "palm_mute",
                                                           "legato", "tapping", "sweep", "rest", "chord"})

    def test_context_detector_dismissed_and_unaccepted_are_not_positives(self):
        items = [spec("ctx", basis="operator_context", quote=None, start=0, end=15),
                 spec("det", basis="detector_hypothesis", quote=None, start=1, end=2),
                 spec("ref", basis="reference_comparison", quote=None, start=3, end=4),
                 spec("dis", status="dismissed_candidate", start=5, end=6),
                 spec("pending", status="needs_review", start=7, end=8)]
        metrics = self.evaluate(items, [proposal("x", t) for t in (1.5, 3.5, 5.5, 7.5)])["records"][0]["metrics"]
        self.assertEqual((metrics["labelled_positive_count"], metrics["recall"], metrics["reason"]),
                         (0, None, "no_labelled_positives"))

    def test_clock_statuses_null_all_metrics(self):
        items = [spec("ctx", basis="operator_context", quote=None, start=0, end=15), spec("p", start=1, end=2)]
        flags = [proposal("x", 1.5)]
        mismatch = self.evaluate(items, flags, source="e" * 64)["records"][0]
        self.assertEqual(mismatch["clock_alignment_status"], "source_mismatch")
        unknown = self.evaluate(items, flags, axis="audio_relative_seconds")["records"][0]
        self.assertEqual(unknown["clock_alignment_status"], "clock_unknown")
        aligned = self.evaluate(items, flags)["records"][0]
        self.assertEqual(aligned["clock_alignment_status"], "same_source_original_clock_declared")
        self.assertEqual(aligned["metrics"]["recall"], 1.0)
        for record, reason in ((mismatch, "source_mismatch"), (unknown, "clock_unknown")):
            self.assertEqual((record["metrics"]["recall"], record["metrics"]["reason"]), (None, reason))
            self.assertTrue(all(axis["recall"] is None for axis in record["error_axes"].values()))
            self.assertEqual(record["detector_latency"], "uncalibrated")
        self.assertIsNone(aligned["proposal_lineage_differs_from_annotation_manifest"])
        (self.proposal_dir / "manifest.json").write_text("{}")
        lineage = self.evaluate(items, flags)["records"][0]
        self.assertIs(lineage["proposal_lineage_differs_from_annotation_manifest"], True)

    def test_point_matching_tolerance_and_one_to_one(self):
        items = [spec("ctx", basis="operator_context", quote=None, start=0, end=15),
                 spec("pt", start=10.0, extent=False), spec("pt2", start=10.1, extent=False)]
        near = self.evaluate(items, [proposal("x", 10.2)])["records"][0]["metrics"]
        self.assertEqual((near["recall_numerator"], near["recall_denominator"]), (1, 2))
        far = self.evaluate(items, [proposal("x", 10.7)])["records"][0]["metrics"]
        self.assertEqual(far["recall_numerator"], 0)

    def test_proposals_untouched_navigation_counted_and_stale_refused(self):
        items = [spec("ctx", basis="operator_context", quote=None, start=0, end=15), spec("p", start=1, end=2)]
        flags = [proposal("x", 1.5), {"kind": "four_pulse_group_review_candidate", "source_time_seconds": 1.0,
                                      "end_seconds": 3.0, "confidence": "navigation_proxy_not_confirmed_bar"}]
        split = self.corpus(items)
        path, digest = self.proposals(flags)
        raw = path.read_bytes()
        result = evaluator.evaluate(split, local_root=self.root, proposals_path=path, proposals_sha256=digest)
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual((result["navigation_excluded"], result["eligible_proposal_count"],
                          result["proposals_modified"]), (1, 1, False))
        with self.assertRaisesRegex(corpus.CorpusError, "stale_proposals"):
            evaluator.evaluate(split, local_root=self.root, proposals_path=path, proposals_sha256="0" * 64)

    def test_split_refusals_propagate_unchanged(self):
        split = self.corpus([spec("p", start=1, end=2)])
        data = json.loads(split.read_text())
        data["records"][0]["annotation_refs"][0]["store"]["sha256"] = "0" * 64
        split.write_text(json.dumps(data))
        path, digest = self.proposals([])
        with self.assertRaisesRegex(corpus.CorpusError, "metadata_hash_mismatch"):
            evaluator.evaluate(split, local_root=self.root, proposals_path=path, proposals_sha256=digest)

    def test_cli_refuses_output_beside_proposals(self):
        split = self.corpus([spec("p", start=1, end=2)])
        path, digest = self.proposals([])
        inside = self.proposal_dir / "eval.json"
        argv = ["evaluate", str(split), "--root", str(self.root), "--proposals", str(path),
                "--proposals-sha256", digest, "--output"]
        self.assertEqual(evaluator.main(argv + [str(inside)]), 1)
        self.assertFalse(inside.exists())
        self.assertEqual(evaluator.main(argv + [str(self.root / "out" / "eval.json")]), 0)

    def test_real_take_null_result(self):
        base = artifact_base(REAL_FLAGS)
        if base is None or artifact_base(STAGED[1]) is None:
            self.skipTest("real-take metadata is not present on this host")
        staged = self.root / "staged"
        stage_real_root(base, staged)
        flags = base / REAL_FLAGS
        before = flags.read_bytes()
        result = evaluator.evaluate(staged / EXAMPLE, local_root=staged, proposals_path=flags,
                                    proposals_sha256=REAL_FLAGS_SHA)
        self.assertEqual(flags.read_bytes(), before)
        record = result["records"][0]
        self.assertEqual(record["coverage"]["covered_seconds"], 5.0)
        self.assertAlmostEqual(record["coverage"]["total_seconds"], 150.961111)
        self.assertLess(record["coverage"]["coverage_fraction"], evaluator.COVERAGE_THRESHOLD)
        self.assertEqual((record["metrics"]["precision"], record["metrics"]["recall"], record["metrics"]["reason"]),
                         (None, None, "coverage_below_threshold"))
        self.assertEqual(record["clock_alignment_status"], "same_source_original_clock_declared")
        self.assertIs(record["proposal_lineage_differs_from_annotation_manifest"], True)
        axes = {**record["error_axes"], **record["articulation_axes"]}
        self.assertTrue(all(axis["labelled_positive_count"] == 0 for axis in axes.values()))
        self.assertEqual((result["proposal_count"], result["navigation_excluded"]), (171, 112))

    def test_v3_receipt_equals_fresh_summary(self):
        base = artifact_base(STAGED[1])
        if base is None:
            self.skipTest("S1 demo context metadata is not present on this host")
        staged = self.root / "staged"
        stage_real_root(base, staged)
        fresh = corpus_split_s1.validate_split(staged / EXAMPLE, staged, summary=True)
        receipt = json.loads((ROOT / "docs/agent-notes/peers/xoruby/V3-corpus-split-receipt.json").read_text())
        self.assertEqual(receipt, fresh)
        self.assertEqual((receipt["result_mode"], receipt["source_audio_read"], receipt["negative_examples_inferred"]),
                         ("summary", False, 0))
        self.assertNotIn("records", receipt)

    def test_v5_mapping_and_vocabulary_documents(self):
        v5 = (ROOT / "docs/agent-notes/peers/xoruby/V5-vocabulary-mapping.md").read_text()
        for phrase in ("observation with literal reviewer assertion -> labelled record", "ambiguous -> unknown",
                       "unlabelled -> unknown never absent"):
            self.assertIn(phrase, v5)
        vocabulary = (ROOT / "docs/spec/ANNOTATION_V2_VOCABULARY.md").read_text()
        for token in sorted(annotation_v2.KINDS | annotation_v2.BASES | annotation_v2.STATES):
            self.assertIn("`" + token + "`", vocabulary)
        for label in annotation_v2.LABELS.values():
            self.assertIn(label, vocabulary)
        self.assertIn("132", vocabulary)


if __name__ == "__main__":
    unittest.main()
