"""Meaningful finite-feature and evidence tests; no heldout audio or inference."""
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("phrase_proposal_s1", ROOT/"scripts/phrase_proposal_s1.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
try:
    import numpy as np
except ImportError:
    np = None


def pair(first=(1., 2.8), second=(4.3, 6.1)):
    return {"first_span_seconds": list(first), "second_span_seconds": list(second)}


@unittest.skipIf(np is None, "locked numerical environment is optional in baseline CI")
class FeatureContractTests(unittest.TestCase):
    def features(self, internal_gap=True):
        times = np.arange(0, 8.001, .02)
        centers = np.array([32., 65., 110., 220., 440., 880., 2200., 4500.])
        x = np.ones((len(times), len(centers)))
        for start in (1., 4.3):
            for i, time in enumerate(times):
                age = time-start
                if 0 <= age < 1.8:
                    if internal_gap and .6 <= age < .72:  # Internal acoustic gap remains within motif.
                        continue
                    x[i, int(age/.15) % 6] += 100
        return x, times, centers

    def test_spectral_sequence_recurrence_without_reference_input(self):
        x, times, centers = self.features()
        result = p.propose(x, times, centers, 8.)
        self.assertEqual(len(result["candidates"]), 1)
        row = result["candidates"][0]
        self.assertAlmostEqual(row["first_span_seconds"][0], .99)
        self.assertAlmostEqual(row["first_span_seconds"][1], 2.79)
        self.assertGreater(row["similarity"], .95)
        self.assertFalse(row["performance_issue_confirmed"])
        self.assertIsNone(row["confidence"])
        self.assertFalse(result["truth_supplied"])
        with self.assertRaises(TypeError):
            p.propose(x, times, centers, 8., ground_truth=[pair()])

    def test_multiscale_duplicates_do_not_multiply_identical_pair(self):
        x, times, centers = self.features(internal_gap=False)
        result = p.propose(x, times, centers, 8., multiscale=True)
        self.assertEqual(len(result["support_audits"]), 3)
        self.assertEqual(len(result["candidates"]), 1)
        self.assertGreaterEqual(result["candidate_count_before_deduplication"], 3)

    def test_constant_low_sustain_and_missing_f0_not_riff_identity(self):
        x, times, centers = self.features()
        for bins in ((0,), (1, 2, 3)):
            x[:] = 1
            for start in (1., 4.3):
                selected = (times >= start) & (times < start+1.8)
                x[np.ix_(selected, bins)] = 100
            self.assertEqual(p.propose(x, times, centers, 8.)["candidates"], [])

    def test_ordered_high_frequency_click_pattern_rejected_by_support_guard(self):
        x, times, centers = self.features()
        for row in x:
            row[6:] += row[:6].sum()
            row[:6] = 1
        self.assertEqual(p.propose(x, times, centers, 8., multiscale=True)["candidates"], [])

    def test_shape_and_clock_refusals(self):
        x, times, centers = self.features()
        bad = [(-x, times, centers), (x*np.nan, times, centers),
               (x.astype(bool), times, centers), (x, times[:-1], centers),
               (x, times[::-1], centers), (x, times, centers[::-1]),
               (x, times-1, centers), (x, times+1, centers),
               (x, times, centers*1e6)]
        for values in bad:
            with self.subTest(values=str([v.shape for v in values])):
                with self.assertRaises(ValueError):
                    p.propose(*values, 8.)
        with self.assertRaises(ValueError):
            p.propose(x, times, centers, True)
        with self.assertRaises(ValueError):
            p.propose(x, times, centers, float("inf"))
        with self.assertRaises(ValueError):
            p.propose(x, times, centers, 8., multiscale=1)

    def test_frame_and_dimension_budgets(self):
        with self.assertRaisesRegex(ValueError, "feature_shape_bound"):
            p.propose(np.ones((1025, 2)), np.linspace(0,8,1025), [32,65], 8.)
        with self.assertRaisesRegex(ValueError, "feature_shape_bound"):
            p.propose(np.ones((4, 65)), np.arange(4), np.linspace(32,6000,65), 8.)

    def test_quiet_constant_features_abstain(self):
        x, times, centers = self.features()
        self.assertEqual(p.propose(np.zeros_like(x), times, centers, 8.)["candidates"], [])
        self.assertEqual(p.propose(np.ones_like(x), times, centers, 8.)["candidates"], [])


class EvidenceTests(unittest.TestCase):
    def test_pair_requires_both_span_iou_and_best_assignment(self):
        measured = p.score_rows([pair()], [pair(), pair((1.,2.8),(4.3,7.9))])
        for score in measured["pair_iou"]:
            self.assertEqual((score["tp"],score["fp"],score["fn"]), (1,1,0))
            self.assertEqual(score["matches"][0]["estimate_index"], 0)
            self.assertEqual(score["endpoint_count"], 4)
            self.assertEqual(score["matched_endpoint_mae_seconds"], 0)
        measured = p.score_rows([pair()], [pair((1.,2.8),(4.3,7.9))])
        self.assertEqual(measured["pair_iou"][1]["tp"], 0)
        self.assertIsNone(measured["pair_iou"][1]["matched_endpoint_mae_seconds"])

    def test_typed_endpoints_and_abstention_denominators(self):
        measured = p.score_rows([pair()], [pair((1.01,2.81),(4.31,6.3))])
        self.assertEqual((measured["typed_endpoints"][0]["tp"],measured["typed_endpoints"][0]["fn"]), (3,1))
        empty = p.score_rows([pair()], [])
        self.assertEqual(empty["pair_iou"][0]["fn"], 1)
        self.assertEqual(empty["typed_endpoints"][0]["fn"], 4)
        self.assertIsNone(empty["pair_iou"][0]["matched_endpoint_mae_seconds"])
        negative = p.score_rows([], [pair()])
        self.assertEqual(negative["pair_iou"][0]["fp"], 1)
        self.assertEqual(negative["typed_endpoints"][0]["fp"], 4)

    def test_closed_heldout_metadata_and_unchanged_dependencies(self):
        value = p.metadata()
        self.assertEqual(value["seeds"], [1301,1423])
        self.assertEqual(value["case_count"], 12)
        self.assertEqual(value["audio_seconds"], 96)
        self.assertEqual(len(value["arms"]), 3)
        self.assertFalse(value["retune_after_heldout"])
        self.assertFalse(value["canonical_defaults_activated"])
        self.assertNotIn(617, value["seeds"])
        p.verify_pins()

    def test_no_product_catalog_or_default_mutation(self):
        catalog = json.loads((ROOT/"program/tools.json").read_text())
        self.assertNotIn("phrase_proposal_s1", json.dumps(catalog))
        self.assertNotIn("S1_support", json.dumps(catalog))

    def test_strict_reader_rejects_duplicates_nonfinite_symlink_and_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"value.json"
            for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}'):
                path.write_text(raw)
                with self.assertRaises(ValueError):
                    p.strict_read(path)
            path.write_text('{"a":1}')
            with self.assertRaises(ValueError):
                p.strict_read(path, "0"*64)
            link = Path(tmp)/"link.json"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                p.strict_read(link)

    def test_artifact_paths_refuse_escape_and_traversal(self):
        for path in ("/tmp/output.json", "artifacts/../output.json", "artifacts"):
            with self.assertRaises(ValueError):
                p.artifact_path(path)

    def test_fifo_metadata_refused_before_blocking_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"fifo"
            os.mkfifo(path)
            with self.assertRaisesRegex(ValueError, "json_regular_bound"):
                p.strict_read(path)

    def test_incomplete_seal_refused_before_any_truth_read(self):
        bank = {"suite": p.SUITE, "cases": [{}]*12}
        seal = {"suite": p.SUITE, "bank_sha256": "bank", "status": "all_predictions_sealed_truth_unopened", "predictions": [{}]*11}
        with patch.object(p, "artifact_path", side_effect=lambda x, **_: Path(x)), patch.object(p, "strict_read", side_effect=[bank,seal]) as read:
            with self.assertRaisesRegex(ValueError, "global_complete_prediction_seal_required"):
                p.score("bank.json", "bank", "seal.json", "seal", "result.json", {})
            self.assertEqual(read.call_count, 2)

    def test_all_predictions_verified_before_first_truth_read(self):
        predictions = [{"source_sha256": str(i), "arms": {arm:[] for arm in p.ARMS}, "discovery_truth_input": False} for i in range(12)]
        cases = [{"id": str(i), "seed":seed,"cohort":cohort, "source":{"path":f"source{i}","sha256":str(i)}, "truth":{"path":f"truth{i}","sha256":"truth"}}
                 for i,(seed,cohort) in enumerate((seed,cohort) for seed in p.SEEDS for cohort in p.COHORTS)]
        bank = {"suite":p.SUITE, "cases":cases}
        seal = {"suite":p.SUITE,"bank_sha256":"bank","status":"all_predictions_sealed_truth_unopened",
                "predictions":[{"path":f"prediction{i}","sha256":"prediction","source_sha256":str(i)} for i in range(12)]}
        calls = []
        def read(path, expected=None):
            calls.append(str(path))
            name = Path(path).name
            if name == "bank.json": return bank
            if name == "seal.json": return seal
            if name.startswith("prediction"): return predictions[int(name[10:])]
            if name.startswith("truth"):
                self.assertEqual(sum("prediction" in item for item in calls), 12)
                raise ValueError("first_truth_open_after_seal")
            self.fail(name)
        with patch.object(p,"artifact_path",side_effect=lambda x,**_:Path(x)), patch.object(p,"strict_read",side_effect=read), patch.object(p,"digest",side_effect=lambda x:Path(x).name[6:]):
            with self.assertRaisesRegex(ValueError,"first_truth_open_after_seal"):
                p.score("bank.json","bank","seal.json","seal","result.json",{})


if __name__ == "__main__":
    unittest.main()
