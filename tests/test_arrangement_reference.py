"""Fixed-seed randomized arrangement properties; no models, media DSP or installs."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import random
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("arrangement_property_worker", REPO / "scripts/arrangement_reference.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
SOURCE_SHA = "ab" * 32


def reference(sections=None, *, bpm=178, anchor=(10.0, 10.05)):
    return {
        "schema_version": 1, "source_sha256": SOURCE_SHA,
        "provenance": {"status": "operator_supplied_expected_arrangement",
                       "authority_reference": "synthetic arrangement property fixture",
                       "assumptions": ["Intent and clock fixtures are supplied assertions, not detected music."]},
        "tempo": {"bpm": bpm, "precision": "approximate"},
        "anchors": {"first_phrase_source_seconds": list(anchor), "click_start_approx_seconds": 5.0},
        "sections": sections or [
            {"id": "verse", "label": "Verse", "kind": "phrase", "phrase_count": 2, "clicks_per_phrase": 16},
            {"id": "breakdown", "label": "Breakdown", "kind": "breakdown", "phrase_count": 1, "clicks_per_phrase": 8},
            {"id": "rest", "label": "Rest", "kind": "rest", "phrase_count": 1, "clicks_per_phrase": 4}],
    }


def observations(ref, boundaries=None, *, start=0.0, duration=None):
    expanded = worker.validate_reference(ref)
    if duration is None:
        duration = expanded["boundaries"][-1]["source_seconds_range"][1] + 2.0
    if boundaries is None:
        boundaries = [{"id": f"obs:{index}", "source_seconds": sum(row["source_seconds_range"]) / 2,
                       "confidence": "unvalidated", "evidence": "synthetic independently supplied boundary"}
                      for index, row in enumerate(expanded["boundaries"])]
    return {"schema_version": 1, "source_sha256": ref["source_sha256"],
            "timeline": {"source_start_seconds": start, "duration_seconds": duration},
            "boundaries": boundaries}


def random_case(rng):
    sections = [{"id": f"section:{index}", "label": f"Synthetic section {index}",
                 "kind": rng.choice(("phrase", "breakdown", "rest")),
                 "phrase_count": rng.randint(1, 3), "clicks_per_phrase": rng.choice((4, 8, 12, 16))}
                for index in range(rng.randint(1, 4))]
    ref = reference(sections, bpm=rng.uniform(80, 240), anchor=(10.0, 10.1))
    period = 60 / ref["tempo"]["bpm"]
    obs = observations(ref)
    supplied = []
    for row in obs["boundaries"]:
        if rng.random() < .2:
            continue
        row["source_seconds"] += rng.uniform(-.12, .12) * period
        row["uncertainty_seconds"] = rng.uniform(0, .06) * period
        row["confidence"] = rng.choice(("unvalidated", "operator_reviewed", "ambiguous"))
        supplied.append(row)
        if rng.random() < .15:
            duplicate = copy.deepcopy(row)
            duplicate["id"] += ":alternative"
            duplicate["source_seconds"] += .01 * period
            supplied.append(duplicate)
    rng.shuffle(supplied)
    obs["boundaries"] = supplied
    return ref, obs


class ArrangementReferenceProperties(unittest.TestCase):
    def align_unchanged(self, ref, obs):
        before_ref, before_obs = copy.deepcopy(ref), copy.deepcopy(obs)
        result = worker.align_arrangement(ref, obs)
        self.assertEqual(ref, before_ref)
        self.assertEqual(obs, before_obs)
        return result

    def assert_unknown_performance(self, result):
        self.assertFalse(result["performance_issue_confirmed"])
        self.assertIsNone(result["observed_click_count"])
        self.assertIsNone(result["meter"])
        for key in ("boundaries", "units", "review_candidates"):
            for row in result[key]:
                self.assertFalse(row["performance_issue_confirmed"])
        for row in result["units"]:
            if row["observed"] is not None:
                self.assertIsNone(row["observed"]["observed_click_count"])
                self.assertIn("not_detected_clicks", row["observed"]["click_count_basis"])

    def assert_same_alignment(self, left, right):
        self.assertEqual(left["observed_boundary_count"], right["observed_boundary_count"])
        self.assertEqual(left["unassigned_observation_ids"], right["unassigned_observation_ids"])
        self.assertEqual(left["reference"]["totals"], right["reference"]["totals"])
        self.assertAlmostEqual(left["alignment"]["cost"], right["alignment"]["cost"], places=8)
        for a, b in zip(left["boundaries"], right["boundaries"]):
            for key in ("status", "coverage", "candidate_observation_ids", "candidate_observation_count",
                        "unmatched_alignment_possible", "confidence"):
                self.assertEqual(a[key], b[key])
            self.assertEqual(None if a["observed"] is None else a["observed"]["id"],
                             None if b["observed"] is None else b["observed"]["id"])

    def test_supplied_demo_expands_to_404_intended_clicks_without_observed_counts(self):
        ref = json.loads((REPO / "program/demo-arrangement.json").read_text())
        before = copy.deepcopy(ref)
        expanded = worker.validate_reference(ref, ref["source_sha256"])
        self.assertEqual(expanded["totals"], {"intended_click_count": 404, "musical_phrase_count": 24,
                                            "breakdown_group_count": 2, "rest_click_count": 4})
        self.assertEqual([row["click_count"] for row in expanded["units"] if row["kind"] == "breakdown"], [8, 8])
        self.assertEqual(expanded["boundaries"][-1]["click_index"], 404)
        self.assertEqual(ref, before)
        self.assertEqual(len(expanded["boundaries"]), len(expanded["units"]) + 1)

    def test_randomized_reference_expansion_uses_an_independent_integer_cursor(self):
        rng = random.Random(6100601)
        for case in range(50):
            with self.subTest(seed=6100601, case=case):
                ref, unused = random_case(rng)
                before = copy.deepcopy(ref)
                expanded = worker.validate_reference(ref)
                cursor, indices, unit_ids = 0, [0], set()
                counts = {"phrase": 0, "breakdown": 0, "rest": 0}
                units = iter(expanded["units"])
                for section in ref["sections"]:
                    for index in range(section["phrase_count"]):
                        row = next(units)
                        self.assertEqual(row["section_id"], section["id"])
                        self.assertEqual(row["section_unit_index"], index + 1)
                        self.assertEqual(row["start_click_index"], cursor)
                        cursor += section["clicks_per_phrase"]
                        self.assertEqual(row["end_click_index"], cursor)
                        self.assertEqual(row["click_count"], section["clicks_per_phrase"])
                        self.assertNotIn(row["id"], unit_ids)
                        unit_ids.add(row["id"])
                        indices.append(cursor)
                    counts[section["kind"]] += (section["phrase_count"] * section["clicks_per_phrase"]
                                                if section["kind"] == "rest" else section["phrase_count"])
                self.assertEqual([row["click_index"] for row in expanded["boundaries"]], indices)
                self.assertEqual(expanded["totals"], {"intended_click_count": cursor,
                    "musical_phrase_count": counts["phrase"], "breakdown_group_count": counts["breakdown"],
                    "rest_click_count": counts["rest"]})
                self.assertEqual(ref, before)

    def test_randomized_source_time_translation_preserves_alignment_and_duration(self):
        rng = random.Random(6100602)
        for case in range(35):
            with self.subTest(seed=6100602, case=case):
                ref, obs = random_case(rng)
                original = self.align_unchanged(ref, obs)
                delta = rng.uniform(-100, 100)
                moved_ref, moved_obs = copy.deepcopy(ref), copy.deepcopy(obs)
                moved_ref["anchors"]["first_phrase_source_seconds"] = [value + delta for value in ref["anchors"]["first_phrase_source_seconds"]]
                moved_ref["anchors"]["click_start_approx_seconds"] += delta
                moved_obs["timeline"]["source_start_seconds"] += delta
                for row in moved_obs["boundaries"]:
                    row["source_seconds"] += delta
                moved = self.align_unchanged(moved_ref, moved_obs)
                self.assert_same_alignment(original, moved)
                for a, b in zip(original["boundaries"], moved["boundaries"]):
                    for x, y in zip(a["expected"]["source_seconds_range"], b["expected"]["source_seconds_range"]):
                        self.assertAlmostEqual(y, x + delta)
                    if a["deviation"] is not None:
                        for x, y in zip(a["deviation"]["seconds_range"], b["deviation"]["seconds_range"]):
                            self.assertAlmostEqual(x, y)
                for a, b in zip(original["units"], moved["units"]):
                    if a["observed"] is not None:
                        self.assertAlmostEqual(a["observed"]["duration_seconds"], b["observed"]["duration_seconds"])
                self.assert_unknown_performance(moved)

    def test_randomized_tempo_and_time_scaling_preserves_reference_equivalent_counts(self):
        rng = random.Random(6100603)
        for case in range(35):
            with self.subTest(seed=6100603, case=case):
                ref, obs = random_case(rng)
                original = self.align_unchanged(ref, obs)
                factor = rng.uniform(.65, 1.4)
                scaled_ref, scaled_obs = copy.deepcopy(ref), copy.deepcopy(obs)
                scaled_ref["tempo"]["bpm"] /= factor
                scaled_ref["anchors"]["first_phrase_source_seconds"] = [value * factor for value in ref["anchors"]["first_phrase_source_seconds"]]
                scaled_ref["anchors"]["click_start_approx_seconds"] *= factor
                for key in ("source_start_seconds", "duration_seconds"):
                    scaled_obs["timeline"][key] *= factor
                for row in scaled_obs["boundaries"]:
                    row["source_seconds"] *= factor
                    row["uncertainty_seconds"] *= factor
                scaled = self.align_unchanged(scaled_ref, scaled_obs)
                self.assert_same_alignment(original, scaled)
                for a, b in zip(original["units"], scaled["units"]):
                    self.assertAlmostEqual(b["expected"]["duration_seconds"], a["expected"]["duration_seconds"] * factor)
                    if a["observed"] is not None:
                        self.assertAlmostEqual(b["observed"]["duration_seconds"], a["observed"]["duration_seconds"] * factor)
                        self.assertAlmostEqual(a["observed"]["reference_equivalent_clicks"], b["observed"]["reference_equivalent_clicks"])
                self.assert_unknown_performance(scaled)

    def test_randomized_unsorted_observations_are_canonical_without_input_mutation(self):
        rng = random.Random(6100604)
        for case in range(35):
            with self.subTest(seed=6100604, case=case):
                ref, obs = random_case(rng)
                result = self.align_unchanged(ref, obs)
                shuffled = copy.deepcopy(obs)
                rng.shuffle(shuffled["boundaries"])
                self.assertEqual(result, self.align_unchanged(ref, shuffled))
                keys = [(row["source_seconds"], row["id"]) for row in result["observations"]]
                self.assertEqual(keys, sorted(keys))

    def test_randomized_alignment_never_fabricates_or_reuses_an_observation(self):
        rng = random.Random(6100605)
        for case in range(60):
            with self.subTest(seed=6100605, case=case):
                ref, obs = random_case(rng)
                result = self.align_unchanged(ref, obs)
                supplied = {row["id"]: row for row in obs["boundaries"]}
                assigned = []
                for row in result["boundaries"]:
                    self.assertTrue(set(row["candidate_observation_ids"]) <= set(supplied))
                    self.assertLessEqual(len(row["candidate_observation_ids"]), row["candidate_observation_count"])
                    chosen = row["observed"]
                    if chosen is None:
                        self.assertIsNone(row["deviation"])
                    else:
                        assigned.append(chosen["id"])
                        self.assertEqual(chosen["source_seconds"], supplied[chosen["id"]]["source_seconds"])
                        self.assertEqual(chosen["evidence"], supplied[chosen["id"]]["evidence"])
                        self.assertIn(chosen["id"], row["candidate_observation_ids"])
                        self.assertFalse(row["unmatched_alignment_possible"])
                self.assertEqual(len(assigned), len(set(assigned)))
                self.assertEqual(set(assigned) | set(result["unassigned_observation_ids"]), set(supplied))
                self.assertTrue(set(assigned).isdisjoint(result["unassigned_observation_ids"]))
                self.assert_unknown_performance(result)

    def test_empty_evidence_retains_intent_without_detecting_any_boundary_or_click(self):
        ref = reference()
        result = self.align_unchanged(ref, observations(ref, []))
        self.assertEqual(result["observed_boundary_count"], 0)
        self.assertTrue(all(row["observed"] is None for row in result["boundaries"]))
        self.assertTrue(all(row["status"] == "unobserved_boundary" for row in result["boundaries"]))
        self.assertTrue(all(row["observed"] is None for row in result["units"]))
        self.assertEqual(result["observations"], [])
        self.assert_unknown_performance(result)

    def test_randomized_dense_windows_keep_global_matches_unique_and_monotonic(self):
        rng = random.Random(6100608)
        matched_count, ambiguous_count = 0, 0
        for case in range(45):
            with self.subTest(seed=6100608, case=case):
                # Wide anchor uncertainty and short units make neighboring
                # expected windows compete for the same supplied candidates.
                sections = [{"id": f"dense:{index}", "label": "Dense synthetic unit",
                             "kind": rng.choice(("phrase", "breakdown", "rest")),
                             "phrase_count": rng.randint(1, 4), "clicks_per_phrase": rng.randint(1, 4)}
                            for index in range(2)]
                ref = reference(sections, bpm=rng.uniform(120, 240), anchor=(10, 10 + rng.uniform(.5, 2)))
                obs = observations(ref)
                period = 60 / ref["tempo"]["bpm"]
                supplied = []
                for row in obs["boundaries"]:
                    if rng.random() < .1:
                        continue
                    row["source_seconds"] += rng.uniform(-.25, .25) * period
                    supplied.append(row)
                    if rng.random() < .5:
                        duplicate = copy.deepcopy(row)
                        duplicate["id"] += ":repeat"
                        supplied.append(duplicate)
                rng.shuffle(supplied)
                obs["boundaries"] = supplied
                result = self.align_unchanged(ref, obs)
                ids, times = [], []
                for row in result["boundaries"]:
                    if row["observed"] is not None:
                        ids.append(row["observed"]["id"])
                        times.append(row["observed"]["source_seconds"])
                    if row["status"] == "ambiguous_boundary_alignment":
                        ambiguous_count += 1
                self.assertEqual(len(ids), len(set(ids)))
                self.assertEqual(times, sorted(times))
                self.assertTrue(set(ids) <= {row["id"] for row in supplied})
                matched_count += len(ids)
                self.assert_unknown_performance(result)
        self.assertGreater(matched_count, 0, "fixture must exercise actual assignments")
        self.assertGreater(ambiguous_count, 0, "fixture must exercise competing assignments")

    def test_repeated_identical_candidates_remain_ambiguous(self):
        ref = reference()
        obs = observations(ref)
        duplicate = copy.deepcopy(obs["boundaries"][1])
        duplicate["id"] = "repeated_candidate"
        obs["boundaries"].append(duplicate)
        result = self.align_unchanged(ref, obs)
        row = result["boundaries"][1]
        self.assertEqual(row["status"], "ambiguous_boundary_alignment")
        self.assertIsNone(row["observed"])
        self.assertEqual(set(row["candidate_observation_ids"]), {"obs:1", "repeated_candidate"})
        self.assertEqual(row["candidate_observation_count"], 2)
        self.assertIsNone(result["units"][0]["observed"])
        self.assert_unknown_performance(result)

    def test_explicit_ambiguous_confidence_cannot_become_a_unique_accepted_boundary(self):
        ref = reference()
        obs = observations(ref)
        obs["boundaries"][1]["confidence"] = "ambiguous"
        result = self.align_unchanged(ref, obs)
        row = result["boundaries"][1]
        self.assertEqual(row["candidate_observation_ids"], ["obs:1"])
        self.assertIsNone(row["observed"])
        self.assertEqual(row["status"], "ambiguous_boundary_alignment")
        self.assert_unknown_performance(result)

    def test_randomized_partial_tails_keep_censoring_and_markers_within_source(self):
        rng = random.Random(6100606)
        for case in range(35):
            with self.subTest(seed=6100606, case=case):
                ref, obs = random_case(rng)
                expanded = worker.validate_reference(ref)
                end = rng.uniform(10.01, expanded["boundaries"][-1]["source_seconds_range"][0] - .01)
                start = rng.uniform(0, min(10.0, end - .01))
                obs["timeline"].update(source_start_seconds=start, duration_seconds=end - start)
                obs["boundaries"] = [row for row in obs["boundaries"] if start <= row["source_seconds"] <= end]
                result = self.align_unchanged(ref, obs)
                for row in result["boundaries"]:
                    lo, hi = row["expected"]["source_seconds_range"]
                    expected_coverage = ("within_source" if start <= lo <= hi <= end else
                                         "right_censored" if lo > end else
                                         "left_censored" if hi < start else "partially_censored")
                    self.assertEqual(row["coverage"], expected_coverage)
                    if expected_coverage == "right_censored":
                        self.assertIsNone(row["observed"])
                        self.assertEqual(row["status"], "right_censored")
                for flag in result["review_candidates"]:
                    self.assertLessEqual(start, flag["source_time_seconds"])
                    self.assertLessEqual(flag["source_time_seconds"], flag["end_seconds"])
                    self.assertLessEqual(flag["end_seconds"], end)
                self.assert_unknown_performance(result)

    def test_randomized_out_of_source_boundaries_are_rejected(self):
        rng = random.Random(6100607)
        for case in range(25):
            with self.subTest(seed=6100607, case=case):
                ref, obs = random_case(rng)
                start = obs["timeline"]["source_start_seconds"]
                end = start + obs["timeline"]["duration_seconds"]
                invalid = {"id": "outside", "source_seconds": start - rng.uniform(.001, 3),
                           "confidence": "unvalidated", "evidence": "synthetic out-of-source observation"}
                obs["boundaries"] = [invalid]
                with self.assertRaises(ValueError):
                    worker.align_arrangement(ref, obs)
                invalid["source_seconds"] = end + rng.uniform(.001, 3)
                with self.assertRaises(ValueError):
                    worker.align_arrangement(ref, obs)

    def test_constructed_short_breakdown_measures_duration_without_confirming_rush(self):
        ref = reference([
            {"id": "verse", "label": "Verse", "kind": "phrase", "phrase_count": 1, "clicks_per_phrase": 16},
            {"id": "breakdown", "label": "Breakdown", "kind": "breakdown", "phrase_count": 1, "clicks_per_phrase": 8},
            {"id": "rest", "label": "Rest", "kind": "rest", "phrase_count": 1, "clicks_per_phrase": 4},
        ], anchor=(10.0, 10.0))
        obs = observations(ref)
        period = 60 / ref["tempo"]["bpm"]
        obs["boundaries"][2]["source_seconds"] -= period
        result = self.align_unchanged(ref, obs)
        breakdown = result["units"][1]
        self.assertEqual(breakdown["expected"]["click_count"], 8)
        self.assertAlmostEqual(breakdown["observed"]["reference_equivalent_clicks"], 7)
        self.assertAlmostEqual(breakdown["deviation"]["reference_equivalent_clicks_delta"], -1)
        self.assertAlmostEqual(breakdown["deviation"]["duration_seconds_delta"], -period)
        self.assertEqual(breakdown["status"], "duration_review_candidate")
        self.assert_unknown_performance(result)
        self.assertEqual(result["timeline"]["boundary_latency_status"], "uncalibrated")

    def test_missing_breakdown_boundary_stays_unknown_without_missed_grade(self):
        ref = reference()
        obs = observations(ref)
        # Units 0/1 are verse; unit 2 is breakdown, ended by boundary 3.
        obs["boundaries"] = [row for row in obs["boundaries"] if row["id"] != "obs:3"]
        result = self.align_unchanged(ref, obs)
        self.assertIsNone(result["boundaries"][3]["observed"])
        self.assertEqual(result["boundaries"][3]["status"], "unobserved_boundary")
        self.assertIsNone(result["units"][2]["observed"])
        self.assertEqual(result["units"][2]["status"], "boundary_support_unavailable")
        self.assert_unknown_performance(result)

    def test_rest_is_intended_context_even_with_duration_support(self):
        ref = reference()
        result = self.align_unchanged(ref, observations(ref))
        rest = result["units"][-1]
        self.assertEqual(rest["expected"]["kind"], "rest")
        self.assertEqual(rest["expected"]["click_count"], 4)
        self.assertAlmostEqual(rest["observed"]["reference_equivalent_clicks"], 4)
        self.assert_unknown_performance(result)

    def test_source_hash_binding_rejects_other_intent_or_observation_source(self):
        ref = reference()
        with self.assertRaises(ValueError):
            worker.validate_reference(ref, "cd" * 32)
        obs = observations(ref)
        obs["source_sha256"] = "cd" * 32
        with self.assertRaises(ValueError):
            worker.align_arrangement(ref, obs)

    def test_cli_writes_hash_bound_fresh_artifacts_without_dsp_or_overwrite(self):
        ref = reference()
        obs = observations(ref)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            ref_path, obs_path, output = root / "reference.json", root / "observations.json", root / "result"
            ref_path.write_text(json.dumps(ref))
            obs_path.write_text(json.dumps(obs))
            argv = [str(ref_path), "--observations", str(obs_path), "--output", str(output)]
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = worker.main(argv)
            summary = json.loads(stdout.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(summary["source_sha256"], SOURCE_SHA)
            self.assertIsNone(summary["observed_click_count"])
            receipt_path = output / "receipt.json"
            receipt = json.loads(receipt_path.read_text())
            self.assertFalse(receipt["dsp_performed"])
            self.assertFalse(receipt["performance_issue_confirmed"])
            for name, expected in receipt["output_sha256"].items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), expected)
            before = {path.name: path.read_bytes() for path in output.iterdir()}
            with contextlib.redirect_stdout(io.StringIO()):
                repeated = worker.main(argv)
            self.assertEqual(repeated, 2)
            self.assertEqual({path.name: path.read_bytes() for path in output.iterdir()}, before)


if __name__ == "__main__":
    unittest.main()
