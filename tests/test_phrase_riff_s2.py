"""Preregistration, release, seal-before-score, aggregation and V2-wrapper tests.

Stdlib by default; numpy synthesis/R1 cases run only under the locked analysis
interpreter and otherwise skip with a stated reason. No held-out seed audio is
generated here: synthesis cases use throwaway seeds outside every registered set.
"""
import copy
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("phrase_riff_s2_under_test", ROOT / "scripts/phrase_riff_s2.py")
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)
try:
    import numpy as np
except ImportError:
    np = None
THROWAWAY_SEEDS = range(90101, 90103)


def calibrated():
    return mock.patch.multiple(rs, R1_THETA=.65, DEV_RECEIPT_SHA256="ab" * 32)


class LaneArea:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.area = Path(self.tmp.name).resolve() / "artifacts" / "s2" / "phrase_anchor_riff"
        self.area.mkdir(parents=True)
        self.patch = mock.patch.object(rs, "LANE_AREA", self.area)
        self.patch.start()
        return self

    def __exit__(self, *exc):
        self.patch.stop()
        self.tmp.cleanup()


def pair(first, second):
    return {"first_span_seconds": list(first), "second_span_seconds": list(second)}


class PreregistrationTests(unittest.TestCase):
    def test_13_deterministic_metadata_seeds_geometry_and_gaps(self):
        with self.assertRaisesRegex(ValueError, "theta_not_calibrated"):
            rs.metadata()
        with calibrated():
            first, second = rs.metadata(), rs.metadata()
            self.assertEqual(first, second)
            self.assertEqual(hashlib.sha256(rs.encoded(first)).hexdigest(), hashlib.sha256(rs.encoded(second)).hexdigest())
        self.assertEqual(first["seeds"], [1511, 1613])
        self.assertFalse(set(first["seeds"]) & (set(rs.CONSUMED_SEEDS) | {rs.DEV_SEED}))
        self.assertNotIn(rs.DEV_SEED, rs.CONSUMED_SEEDS)
        self.assertEqual((first["case_count"], first["audio_seconds"]), (16, 128))
        self.assertEqual(first["r1_settings"]["theta"], .65)
        self.assertEqual(first["scoring"]["reference_totals"], {"positive_pairs": 12, "typed_endpoints": 48, "negative_cases": 4})
        self.assertEqual(first["arms"].keys(), {"Araw", "S1_support", "R1_lag"})
        self.assertEqual(first["discarded_before_sealing"], ["S2_multiscale"])
        self.assertFalse(first["discovery_truth_input"])
        self.assertTrue(first["predictions_global_seal_before_truth_read"])
        self.assertEqual(first["continuous_riff_accuracy_scope"], "generated_only")
        self.assertFalse(first["default_adoption"])
        positives = negatives = 0
        for seed, cohorts in first["generator_geometry"].items():
            self.assertEqual(list(cohorts), list(rs.COHORTS))
            for cohort, item in cohorts.items():
                self.assertTrue(rs.validate_geometry(item))
                if cohort in rs.NEGATIVE_COHORTS:
                    negatives += 1
                    self.assertEqual(item["truth_pairs"], [])
                    continue
                positives += len(item["truth_pairs"])
                self.assertTrue(all(0 <= g <= .10 * rs.RATE for g in item["gap_samples"]))
                motif = item["motif_samples"] / rs.RATE
                low, high = (1.30, 1.70) if cohort == "aba-transition" else (1.40, 1.90)
                self.assertTrue(low <= motif <= high)
                truth = item["truth_pairs"][0]
                self.assertEqual(truth["first_span_samples"][1] - truth["first_span_samples"][0], item["motif_samples"])
                self.assertTrue(all(type(v) is int for v in truth["first_span_samples"] + truth["second_span_samples"]))
                self.assertEqual(truth["first_span_seconds"][0], truth["first_span_samples"][0] / rs.RATE)
                notes = [row[1] for row in item["notes"]]
                self.assertTrue(all(24 <= midi <= 77 for midi in notes))
        self.assertEqual((positives, 4 * positives, negatives), (12, 48, 4))

    def test_13b_distinctness_and_no_repeated_ngram_in_through_composed(self):
        self.assertTrue(rs.differs_enough([1, 2, 3, 4], [1, 2, 9, 9]))
        self.assertFalse(rs.differs_enough([1, 2, 3, 9], [1, 2, 3, 4]))
        for seed in (rs.DEV_SEED, *THROWAWAY_SEEDS):
            notes = [row[1] for row in rs.geometry(seed, "through-composed")["notes"]]
            grams = [tuple(notes[i:i + 4]) for i in range(len(notes) - 3)]
            self.assertEqual(len(grams), len(set(grams)))
            sustain = rs.geometry(seed, "sustain32-fan-click")["notes"]
            self.assertEqual([row[1:3] for row in sustain], [[24, "sustain"]])  # C1 ~32.7 Hz, never filtered


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.ffmpeg = base / "ffmpeg"
        self.ffmpeg.write_bytes(b"pinned-fixture")
        self.patches = [calibrated(), mock.patch.object(rs, "FFMPEG_PIN", {"path": str(self.ffmpeg),
                                                                          "sha256": hashlib.sha256(b"pinned-fixture").hexdigest()})]
        for item in self.patches:
            item.start()
        self.plan = base / "plan.json"
        self.plan.write_bytes(rs.encoded(rs.metadata()))
        self.plan_hash = hashlib.sha256(self.plan.read_bytes()).hexdigest()
        self.release = base / "release.json"

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def write_release(self, **changes):
        value = {"actor": "root_workflow", "suite": rs.SUITE, "authorized_phases": ["generate", "discover", "score"],
                 "plan_sha256": self.plan_hash, "worker_sha256": rs.digest(rs.__file__), "dependency_sha256": rs.PINS,
                 "budgets": rs.BUDGETS, "prereg_commit": "a" * 40, "authorization_quote": "workflow phase authorization"}
        value.update(changes)
        self.release.write_bytes(rs.encoded(value))
        return hashlib.sha256(self.release.read_bytes()).hexdigest()

    def git(self, committed=True, ancestor=True):
        blob = (lambda revision, path: self.plan_hash) if committed else (lambda revision, path: None)
        return mock.patch.multiple(rs, git_blob_sha256=blob, git_is_ancestor=lambda commit: ancestor)

    def test_14_refuses_unreleased_uncommitted_changed_or_mismatched(self):
        good = self.write_release()
        with self.git():
            self.assertEqual(rs.authorize(self.plan, self.plan_hash, self.release, good, "generate")["plan_sha256"], self.plan_hash)
            with self.assertRaisesRegex(ValueError, "release_required"):
                rs.authorize(self.plan, self.plan_hash, None, None, "generate")
            with self.assertRaisesRegex(ValueError, "release_required"):
                rs.authorize(self.plan, self.plan_hash, self.release, self.write_release(actor="lane"), "generate")
            with self.assertRaisesRegex(ValueError, "release_required"):
                rs.authorize(self.plan, self.plan_hash, self.release, self.write_release(authorized_phases=["score"]), "generate")
            with self.assertRaisesRegex(ValueError, "release_required"):
                rs.authorize(self.plan, self.plan_hash, self.release, self.write_release(authorization_quote=" "), "generate")
            for change in ({"worker_sha256": "0" * 64}, {"plan_sha256": "1" * 64}, {"budgets": {}},
                           {"dependency_sha256": {}}):
                with self.assertRaisesRegex(ValueError, "release_binding_changed"):
                    rs.authorize(self.plan, self.plan_hash, self.release, self.write_release(**change), "generate")
            with self.assertRaisesRegex(ValueError, "release_binding_changed"):
                rs.authorize(self.plan, self.plan_hash, self.release, "f" * 64, "generate")
        with self.git(ancestor=False), self.assertRaisesRegex(ValueError, "release_binding_changed"):
            rs.authorize(self.plan, self.plan_hash, self.release, self.write_release(), "discover")
        with self.git(committed=False), self.assertRaisesRegex(ValueError, "preregistration_uncommitted"):
            rs.authorize(self.plan, self.plan_hash, self.release, self.write_release(), "generate")
        changed = rs.metadata()
        changed["seeds"] = [1511, 1999]
        self.plan.write_bytes(rs.encoded(changed))
        new_hash = hashlib.sha256(self.plan.read_bytes()).hexdigest()
        with self.git(), self.assertRaisesRegex(ValueError, "preregistration_changed"):
            rs.authorize(self.plan, new_hash, self.release, self.write_release(plan_sha256=new_hash), "generate")
        with self.git(), self.assertRaisesRegex(ValueError, "preregistration_changed"):
            rs.authorize(self.plan, self.plan_hash, self.release, self.write_release(), "generate")

    def test_14b_git_helpers_on_a_real_temporary_repository(self):
        repo = Path(self.tmp.name) / "repo"
        relative = Path(rs.PREREG_RECEIPT)
        (repo / relative.parent).mkdir(parents=True)
        (repo / relative).write_bytes(b"{}\n")
        env = ["-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false"]
        subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=30)
        with mock.patch.object(rs, "REPO", repo):
            self.assertIsNone(rs.git_blob_sha256("HEAD", rs.PREREG_RECEIPT))
            subprocess.run(["git", "-C", str(repo), *env, "add", "."], check=True, timeout=30)
            subprocess.run(["git", "-C", str(repo), *env, "commit", "-q", "-m", "prereg"], check=True, timeout=30)
            head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                                  check=True, timeout=30).stdout.strip()
            self.assertEqual(rs.git_blob_sha256("HEAD", rs.PREREG_RECEIPT), hashlib.sha256(b"{}\n").hexdigest())
            self.assertTrue(rs.git_is_ancestor(head))
            self.assertFalse(rs.git_is_ancestor("0" * 40))
            self.assertFalse(rs.git_is_ancestor("not-a-commit; rm"))


class FakeBank:
    """Opaque fake sources (bytes only), truths, predictions and a global seal; no audio synthesis."""

    def __init__(self, area, seeds=(rs.DEV_SEED,), arms=rs.ARMS):
        self.area, self.seeds, self.arms = area, seeds, arms
        self.bank_dir = area / "bank"
        self.bank_dir.mkdir()
        self.auth = {"worker_sha256": rs.digest(rs.__file__), "plan_sha256": None}
        cases = []
        for index, (seed, cohort) in enumerate(rs.expected_cases(seeds)):
            folder = self.bank_dir / f"case{index:02d}"
            folder.mkdir()
            (folder / "mix.wav").write_bytes(f"opaque-{seed}-{cohort}".encode())
            source = {"path": f"case{index:02d}/mix.wav", "sha256": rs.digest(folder / "mix.wav")}
            refs = [] if cohort in rs.NEGATIVE_COHORTS else [pair((1., 2.6), (2.65, 4.25))]
            truth = {"source_sha256": source["sha256"], "ground_truth_scope": "generator_only_not_musician",
                     "recurrence_pairs": refs}
            (folder / "truth.json").write_bytes(rs.encoded(truth))
            cases.append({"id": f"case{index:02d}", "seed": seed, "cohort": cohort, "source": source,
                          "truth": {"path": f"case{index:02d}/truth.json", "sha256": rs.digest(folder / "truth.json")}})
        (self.bank_dir / "bank.json").write_bytes(rs.encoded({"suite": rs.SUITE, "cases": cases, "authorization": self.auth}))
        self.bank = self.bank_dir / "bank.json"
        self.bank_hash = rs.digest(self.bank)
        self.cases = cases

    def predictions(self, run="run", mode="dev", status="all_predictions_sealed_truth_unopened"):
        folder = self.area / run
        folder.mkdir()
        rows = []
        for index, case in enumerate(self.cases):
            arms = {arm: [pair((1.02, 2.62), (2.66, 4.26))] if case["cohort"] in rs.POSITIVE_COHORTS else [] for arm in self.arms}
            path = folder / f"prediction{index:02d}.json"
            path.write_bytes(rs.encoded({"source_sha256": case["source"]["sha256"], "arms": arms, "discovery_truth_input": False}))
            rows.append({"path": path.name, "sha256": rs.digest(path), "source_sha256": case["source"]["sha256"]})
        seal = folder / "predictions-sealed.json"
        seal.write_bytes(rs.encoded({"suite": rs.SUITE, "mode": mode, "status": status, "bank_sha256": self.bank_hash,
                                     "predictions": rows}))
        return seal


class SealBeforeScoreTests(unittest.TestCase):
    def test_15_score_refuses_without_seal_or_on_changed_prediction_and_reads_truth_last(self):
        with LaneArea() as lane:
            fake = FakeBank(lane.area)
            unsealed = fake.predictions(run="unsealed", status="partial")
            with self.assertRaisesRegex(ValueError, "global_complete_prediction_seal_required"):
                rs.score(fake.bank, fake.bank_hash, unsealed, rs.digest(unsealed), lane.area / "x.json", fake.auth,
                         seeds=fake.seeds, mode="dev")
            seal = fake.predictions()
            tampered = seal.parent / "prediction03.json"
            original = tampered.read_bytes()
            tampered.write_bytes(original.replace(b"1.02", b"1.03"))
            opened = []
            with mock.patch.object(rs, "read_truth", side_effect=lambda *a: opened.append(a) or {}):
                with self.assertRaisesRegex(ValueError, "sealed_prediction_changed"):
                    rs.score(fake.bank, fake.bank_hash, seal, rs.digest(seal), lane.area / "y.json", fake.auth,
                             seeds=fake.seeds, mode="dev")
            self.assertEqual(opened, [])
            tampered.write_bytes(original)
            order = []
            real = rs.strict_read

            def tracking(path, expected=None):
                order.append(Path(path).name)
                return real(path, expected)

            with mock.patch.object(rs, "strict_read", side_effect=tracking):
                path, document = rs.score(fake.bank, fake.bank_hash, seal, rs.digest(seal), lane.area / "score.json",
                                          fake.auth, seeds=fake.seeds, mode="dev")
            first_truth = order.index("truth.json")
            predictions = [i for i, name in enumerate(order) if name.startswith("prediction") and name[10:12].isdigit()]
            self.assertEqual(len(predictions), 8)
            self.assertLess(max(predictions), first_truth)
            self.assertTrue(document["truth_read_after_global_seal"])
            self.assertEqual(document["aggregate"]["arms"]["R1_lag"]["pair_iou"][0]["tp"], 6)
            self.assertEqual(document["continuous_riff_accuracy_scope"], "generated_only")
            self.assertFalse(document["default_adoption"])
            self.assertIsNone(document["candidate_confidence"])
            with self.assertRaisesRegex(ValueError, "global_complete_prediction_seal_required"):
                rs.score(fake.bank, fake.bank_hash, seal, rs.digest(seal), lane.area / "z.json", fake.auth,
                         seeds=fake.seeds, mode="heldout")

    def test_16_discovery_child_accepts_no_truth_or_reference(self):
        self.assertEqual(list(inspect.signature(rs.source_child).parameters),
                         ["source", "source_sha256", "output", "worker_sha256", "mode"])
        with mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            rs.main(["_source", "a", "b", "c", "d", "dev", "--truth", "t.json"])
        with LaneArea() as lane:
            fake = FakeBank(lane.area)
            calls = []

            def child(argv, **kwargs):
                calls.append(argv)
                Path(argv[5]).write_bytes(rs.encoded({"elapsed_seconds": .1, "source_sha256": argv[4]}))
                return subprocess.CompletedProcess(argv, 0, "", "")

            with mock.patch.object(rs.subprocess, "run", side_effect=child), \
                    mock.patch.object(rs, "read_truth", side_effect=AssertionError("truth opened")), \
                    mock.patch("builtins.print"):
                seal = rs.discover(fake.bank, fake.bank_hash, lane.area / "run", fake.auth, seeds=fake.seeds, mode="dev")
            self.assertEqual(len(calls), 8)
            for argv, case in zip(calls, fake.cases):
                self.assertEqual(argv[2:], ["_source", str(fake.bank_dir / case["source"]["path"]), case["source"]["sha256"],
                                            argv[5], fake.auth["worker_sha256"], "dev"])
                self.assertFalse(any("truth" in str(item) or case["cohort"] in str(item) for item in argv))
            sealed = rs.strict_read(seal)
            self.assertEqual(sealed["status"], "all_predictions_sealed_truth_unopened")
            self.assertEqual(len(sealed["predictions"]), 8)


class AggregateTests(unittest.TestCase):
    def test_17_sums_mae_denominators_common_null_and_negatives(self):
        s1 = rs.s1_module()
        ref = pair((1., 2.6), (2.65, 4.25))
        good = pair((1.02, 2.62), (2.66, 4.26))
        results = []
        for index, cohort in enumerate(rs.COHORTS):
            positive = cohort in rs.POSITIVE_COHORTS
            refs = [ref] if positive else []
            arms = {"A": [good] if positive else [good, good],
                    "B": ([good] if index < 2 else []) if positive else [],
                    "C": [pair((5., 6.), (6.1, 7.1))] if positive else [good]}
            results.append({"id": f"case{index}", "seed": 1, "cohort": cohort, "reference_pair_count": len(refs),
                            "scores": {arm: rs.score_case(s1, refs, ests) for arm, ests in arms.items()}})
        summary = rs.aggregate(results, ("A", "B", "C"))
        a, b, c = (summary["arms"][k] for k in "ABC")
        self.assertEqual((a["pair_iou"][0]["tp"], a["pair_iou"][0]["reference_count"], a["pair_iou"][0]["fp"]), (6, 6, 4))
        self.assertEqual(a["pair_iou"][0]["mae_denominator"], 24)
        self.assertAlmostEqual(a["pair_iou"][0]["matched_endpoint_mae_seconds"], (.02 + .02 + .01 + .01) / 4)
        self.assertEqual((b["pair_iou"][0]["tp"], b["pair_iou"][0]["mae_denominator"], b["pair_iou"][0]["fn"]), (2, 8, 4))
        self.assertEqual((c["pair_iou"][0]["tp"], c["pair_iou"][0]["mae_denominator"]), (0, 0))
        self.assertIsNone(c["pair_iou"][0]["matched_endpoint_mae_seconds"])
        self.assertEqual((a["typed_endpoints"][0]["reference_count"], a["typed_endpoints"][1]["tp"]), (24, 24))
        self.assertEqual(a["typed_endpoints"][0]["tp"], 24)  # all offsets <= 20 ms
        self.assertEqual(a["negative_false_candidates"], {"through-composed": {"false_candidates": 2, "case_count": 1},
                                                          "sustain32-fan-click": {"false_candidates": 2, "case_count": 1}})
        self.assertEqual((a["negative_false_candidates_total"], b["negative_false_candidates_total"],
                          c["negative_false_candidates_total"]), (4, 0, 2))
        self.assertEqual(b["per_positive_cohort_tp"]["b2b-picked"], {"tp_iou_0.5": 1, "tp_iou_0.75": 1, "reference_count": 1})
        self.assertEqual(b["per_positive_cohort_tp"]["tapping-run"]["tp_iou_0.5"], 0)
        common = summary["common_reference_mae"]
        self.assertEqual((common["denominator"], common["reason"]), (0, "no_reference_matched_by_all_arms"))
        self.assertEqual(common["mae_seconds"], {"A": None, "B": None, "C": None})
        two = rs.aggregate(results, ("A", "B"))["common_reference_mae"]
        self.assertEqual((two["denominator"], two["reason"]), (8, None))
        self.assertAlmostEqual(two["mae_seconds"]["B"], .015)
        theta, rows = rs.choose_theta({"arms": {f"R1_lag@{t:.2f}": {"pair_iou": [{"tp": tp}], "negative_false_candidates_total": fp}
                                                for t, tp, fp in ((.55, 6, 4), (.65, 4, 2), (.75, 3, 1))}})
        self.assertEqual(theta, .75)  # 2, 2, 2 -> tie broken toward larger theta
        self.assertEqual([row["objective"] for row in rows], [2, 2, 2])


class V2WrapperTests(unittest.TestCase):
    def test_18_v2_refuses_changed_generator_or_plan_confines_output_and_literals(self):
        self.assertEqual(rs.V2_LICENCE, "pending operator confirmation (repository MIT; proposed CC BY 4.0 for cross-repo use)")
        self.assertEqual(rs.V2_TRAINING_STATEMENT, "training use of this bank voids video-utils held-out evaluation on it")
        self.assertEqual(rs.V2_RESERVED_SEEDS, [2101, 2199])
        self.assertEqual(rs.V2_GENERATOR_SHA256, "051d8689364564513c34a1ab00a2c23560407e474da12c2bf25e7513dbc81709")
        with LaneArea() as lane:
            with mock.patch.object(rs, "V2_GENERATOR_SHA256", "0" * 64), \
                    self.assertRaisesRegex(ValueError, "holdout_generator_changed"):
                rs.v2_bank(lane.area / "v2-bank-a", None)
            with mock.patch.object(rs, "V2_PLAN_SHA256", "1" * 64), \
                    self.assertRaisesRegex(ValueError, "holdout_plan_changed"):
                rs.v2_bank(lane.area / "v2-bank-b", None)
            self.assertFalse((lane.area / "v2-bank-b" / "bank").exists())  # refused before generation
            with self.assertRaisesRegex(ValueError, "lane_artifacts_required"):
                rs.v2_bank(Path(lane.tmp.name).resolve() / "elsewhere" / "v2-bank-c", None)
            with self.assertRaisesRegex(ValueError, "v2_output_name_required"):
                rs.v2_bank(lane.area / "bank-d", None)
            module = rs.load_holdout()
            self.assertEqual(module.ARTIFACTS, lane.area)
            with self.assertRaises(ValueError):
                module.local_path(Path(lane.tmp.name).resolve() / "artifacts" / "benchmarks" / "x")


@unittest.skipIf(np is None, "numpy synthesis/R1 checks run only under VIDEO_UTILS_ANALYSIS_PYTHON")
class NumericConstructionTests(unittest.TestCase):
    def test_construction_checks_on_throwaway_seeds(self):
        with self.assertRaisesRegex(ValueError, "registered_seed_required"):
            rs.construct(90101, "b2b-picked")
        for seed in THROWAWAY_SEEDS:
            for cohort in rs.COHORTS:
                components, truth = rs._construct(seed, cohort)
                raw = {key: np.frombuffer(rs.pcm16(components[key]), dtype="<i2").astype(int) for key in rs.COMPONENTS}
                self.assertLessEqual(int(np.abs(raw["mix"] - raw["clean"] - raw["fan"] - raw["noise"] - raw["click"]).max()), 2)
                self.assertLess(truth["peak_absolute_mix"], .5)
                cue = rs.silence_cue(rs.pcm16(components["clean"]), truth["geometry"])
                self.assertTrue(cue["passed"] if cue["applicable"] else True, (seed, cohort, cue))
                if cohort == "sustain32-fan-click":
                    x = components["clean"][48000:336000]
                    k = np.arange(48000, 336000)
                    amplitude = 2 * abs(np.sum(x * np.exp(-2j * np.pi * 32.7032 * k / 48000))) / len(x)
                    self.assertGreater(amplitude, .05)  # ~32.7 Hz fundamental present, never high-passed

    def test_r1_recovers_contiguous_repeat_without_gap(self):
        rng = np.random.default_rng(7)
        hop = rs.R1_SETTINGS["frame_hop_seconds"]
        frames = 500
        centers = np.geomspace(30, 1700, 20)
        x = rng.uniform(1, 2, (frames, 20))
        start, length, lag = 80, 100, 102  # motif 1.6 s, second copy after a 0.032 s gap
        x[start + lag:start + lag + length] = x[start:start + length]
        result = rs.r1_lag(x, centers, np.arange(frames) * hop, .75)
        top = result["candidates"][0]
        self.assertLess(abs(top["first_span_seconds"][0] - start * hop), .1)
        self.assertLess(abs(top["second_span_seconds"][0] - (start + lag) * hop), .1)
        self.assertIsNone(top["confidence"])
        self.assertFalse(result["truth_supplied"])
        with self.assertRaisesRegex(ValueError, "registered_theta_required"):
            rs.r1_lag(x, centers, np.arange(frames) * hop, .6)


if __name__ == "__main__":
    unittest.main()
