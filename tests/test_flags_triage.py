"""Synthetic and real-metadata flags triage invariants; JSON only, no media."""
import copy
import hashlib
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import flags_triage as triage_tool  # noqa: E402
import marked_video  # noqa: E402
from test_annotation_markers import artifact_base  # noqa: E402

SOURCE = hashlib.sha256(b"synthetic-triage-source").hexdigest()
PERIOD = 0.5  # 16 periods -> 8 s windows
PHASE = 0.25
REAL_RUN = "artifacts/runs/20261006T034521Z-a0def0c43eac"
REAL_FLAGS_SHA = "95a0106c84a338ddc756f3c17879e5eccf8966b4344fe6326b71da7872e8a732"
KINDS = sorted(marked_video.COMPARISON_KINDS) + ["automatic_recurrence_review_candidate",
                                                "low_register_riff_or_breakdown_candidate",
                                                "bright_ending_texture_candidate", "spectral_texture_region_candidate",
                                                "some_future_kind"]


def flag(kind, start, end=None, confidence="unvalidated_automatic_phrase_candidate", **extra):
    return {"kind": kind, "source_time_seconds": start, "end_seconds": start if end is None else end,
            "confidence": confidence, "status": "needs_review", "evidence": {"kind": kind},
            "performance_issue_confirmed": False, **extra}


def proxy(start):
    return {"kind": "four_pulse_group_review_candidate", "source_time_seconds": start, "end_seconds": start + 2,
            "confidence": "navigation_proxy_not_confirmed_bar", "status": "needs_review",
            "evidence": {"kind": "four_pulse_bar_proxy", "warning": "navigation proxy"}}


class TriageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name).resolve() / "run"
        self.run.mkdir()
        (self.run / "manifest.json").write_text(json.dumps({
            "source": {"sha256": SOURCE}, "timeline": {"audio_start_seconds": 0.0, "format_start_seconds": 0.0},
            "pcm": {"duration_seconds": 64.0}}))
        self.clicks = {"click_grid": {"period_seconds": PERIOD, "phase_seconds_audio_relative": PHASE, "bpm": 120.0}}
        self.comparison = {"comparisons": "synthetic"}

    def write(self, flags, *, clicks=True, comparisons=True, timeline=None):
        bindings = {}
        if clicks:
            path = self.run / "clicks" / "x" / "clicks.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.clicks))
            bindings["clicks"] = {"selector": "clicks/x/clicks.json",
                                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        if comparisons:
            path = self.run / "phrase-comparisons.json"
            path.write_text(json.dumps(self.comparison))
            bindings["comparisons"] = {"selector": "phrase-comparisons.json",
                                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        payload = {"schema_version": 1, "source_sha256": SOURCE, "evidence_artifacts": bindings,
                   "timeline": timeline or {"audio_start_seconds": 0.0,
                                            "axis": "original_source_stream_timestamps_seconds"},
                   "flags": flags}
        (self.run / "flags.json").write_text(json.dumps(payload))
        return payload

    def bound(self, item):
        binding = json.loads((self.run / "flags.json").read_text())["evidence_artifacts"]["comparisons"]
        return {**item, "selected_evidence_slot": "comparisons", "selected_artifact": binding["selector"],
                "selected_artifact_sha256": binding["sha256"]}

    def refuse(self, code):
        with self.assertRaises(triage_tool.TriageError) as caught:
            triage_tool.triage(self.run)
        self.assertEqual(caught.exception.code, code)

    def assert_invariants(self, result, flags):
        d = result["denominators"]
        self.assertEqual(d["shown"] + d["suppressed_lower_priority"] + d["navigation_hidden"], d["total_flags"])
        self.assertEqual(d["total_flags"], len(flags))
        windows = [item["window_id"] for item in result["shown"]]
        self.assertEqual(len(windows), len(set(windows)))
        indices = ([i["flag_index"] for i in result["shown"]] + [i["flag_index"] for i in result["suppressed"]]
                   + [i["flag_index"] for i in result["hidden_navigation"]])
        self.assertEqual(sorted(indices), list(range(len(flags))))
        for group in ("shown", "suppressed", "hidden_navigation"):
            for item in result[group]:
                self.assertEqual(item["flag"], flags[item["flag_index"]])
                self.assertEqual(item["flag_id"], triage_tool.flag_id(item["flag_index"], flags[item["flag_index"]]))
        self.assertFalse(any(triage_tool.is_navigation_proxy(item["flag"]) for item in result["shown"]))
        self.assertTrue(all(triage_tool.is_navigation_proxy(item["flag"]) for item in result["hidden_navigation"]))
        self.assertEqual(result["new_flag_kinds"], [])
        self.assertLessEqual({item["flag"].get("kind") for group in ("shown", "suppressed", "hidden_navigation")
                              for item in result[group]}, {item.get("kind") for item in flags})
        for item in result["suppressed"]:
            self.assertEqual(item["reason"], "lower_priority_in_window")
            winner = next(row for row in result["shown"] if row["flag_id"] == item["winner_flag_id"])
            self.assertEqual(winner["window_id"], item["window_id"])

    def test_navigation_proxies_hidden_by_default_and_retained(self):
        flags = [proxy(0.0), proxy(2.0), flag("spectral_texture_region_candidate", 3.0, 5.0),
                 {**flag("other_kind", 4.0), "confidence": "navigation_proxy_not_confirmed_bar"},
                 {**flag("other_kind", 20.0), "evidence": {"kind": "four_pulse_bar_proxy"}}]
        self.write(flags)
        result = triage_tool.triage(self.run)
        self.assertEqual([item["flag_index"] for item in result["hidden_navigation"]], [0, 1, 3, 4])
        self.assertEqual(result["denominators"]["shown"], 1)
        self.assert_invariants(result, flags)

    def test_priority_rule_tiers_and_tiebreaks(self):
        self.write([])
        flags = [flag("spectral_texture_region_candidate", 1.0, 3.0),          # T4 earliest
                 flag("recurrence_motif_timing_difference_review", 6.0),       # T1 unbound
                 self.bound(flag("recurrence_relative_rate_difference_review", 7.0, 7.5)),  # T1 bound, later
                 flag("some_future_kind", 9.0),                                # window 2: T5 only
                 flag("automatic_recurrence_review_candidate", 17.0, 18.0),    # window 3: T2 vs T3
                 flag("low_register_riff_or_breakdown_candidate", 16.5, 20.0),
                 flag("bright_ending_texture_candidate", 26.0),                # window 4: same tier/time,
                 flag("low_register_riff_or_breakdown_candidate", 26.0)]       # kind lexical order decides
        self.write(flags)
        result = triage_tool.triage(self.run)
        shown = {item["window_id"]: (item["flag_index"], item["tier"]) for item in result["shown"]}
        self.assertEqual(shown, {"grid_+00": (2, "T1"), "grid_+01": (3, "T5"), "grid_+02": (4, "T2"),
                                 "grid_+03": (6, "T3")})
        self.assertTrue(next(i for i in result["shown"] if i["flag_index"] == 2)["selected_evidence_hash_bound"])
        self.assertEqual(result["priority_rule"]["id"], "flags-triage-priority-v1")
        self.assertIs(result["priority_rule"]["numeric_confidence_used"], False)
        self.assertEqual(result["window_basis"]["kind"], "click_grid_16_period_navigation_windows")
        self.assertIs(result["window_basis"]["bar_or_downbeat_identified"], False)
        self.assert_invariants(result, flags)
        # Changed evidence bytes break the hash binding; the bound flag loses its precedence.
        self.write(flags)
        (self.run / "phrase-comparisons.json").write_text('{"comparisons": "changed"}')
        result = triage_tool.triage(self.run)
        self.assertEqual(next(i for i in result["shown"] if i["window_id"] == "grid_+00")["flag_index"], 1)

    def test_one_per_window_property_and_confidence_permutation(self):
        rng = random.Random(20261006)
        for case in range(200):
            flags = []
            for index in range(rng.randint(0, 40)):
                start = round(rng.uniform(-1.0, 70.0), 3)
                if rng.random() < .4:
                    flags.append(proxy(start))
                    continue
                item = flag(rng.choice(KINDS), start, round(start + rng.choice((0, rng.uniform(0, 12))), 3),
                            confidence=rng.choice((rng.random(), "unvalidated_automatic_phrase_candidate", None)))
                flags.append(item)
            self.write(flags)
            result = triage_tool.triage(self.run)
            self.assert_invariants(result, flags)
            for item in result["shown"] + result["suppressed"]:
                expected = triage_tool.grid_id(int((item["flag"]["source_time_seconds"] - PHASE) // (16 * PERIOD)))
                self.assertEqual(item["window_id"], expected)
            permuted = copy.deepcopy(flags)
            pool = [item["confidence"] for item in permuted if not triage_tool.is_navigation_proxy(item)]
            rng.shuffle(pool)
            iterator = iter(pool)
            for item in permuted:
                if not triage_tool.is_navigation_proxy(item):
                    item["confidence"] = next(iterator)
            self.write(permuted)
            again = triage_tool.triage(self.run)
            self.assertEqual([i["flag_index"] for i in again["shown"]], [i["flag_index"] for i in result["shown"]],
                             f"case {case}")

    def test_phrase_span_basis_with_unspanned_residual(self):
        flags = [flag("spectral_texture_region_candidate", 1.0, 12.0), flag("automatic_recurrence_review_candidate", 2.0),
                 flag("spectral_texture_region_candidate", 15.0), flag("bright_ending_texture_candidate", 40.0)]
        self.write(flags, clicks=False)
        phrases = {"interpretation": {"semantic_phrases": [
            {"source_start_seconds": 0.0, "source_end_seconds": 10.0},
            {"source_start_seconds": 10.0, "source_end_seconds": 20.0}]}}
        (self.run / "phrases.json").write_text(json.dumps(phrases))
        result = triage_tool.triage(self.run)
        self.assertEqual(result["window_basis"]["kind"], "phrase_spans")
        shown = {item["window_id"]: item["flag_index"] for item in result["shown"]}
        self.assertEqual(shown, {"phrase-000": 1, "phrase-001": 2, "unspanned": 3})
        crossing = next(i for i in result["suppressed"] if i["flag_index"] == 0)
        self.assertIs(crossing["crosses_window_boundary"], True)
        self.assert_invariants(result, flags)
        # A DAG that does not bind the current phrases.json bytes refuses rather than guessing.
        (self.run / "dag.json").write_text(json.dumps({"artifact_hashes": {"phrases.json": "0" * 64}}))
        self.refuse("stale_phrase_spans")

    def test_feature_segments_and_scalar_phrases_do_not_define_windows(self):
        flags = [flag("spectral_texture_region_candidate", 1.0)]
        self.write(flags, clicks=False)
        (self.run / "phrases.json").write_text(json.dumps({
            "interpretation": {"semantic_phrases": "automatic_feature_hypotheses_no_score_required"},
            "observations": {"segment_candidates": [{"source_start_seconds": 0, "source_end_seconds": 5}]}}))
        self.refuse("triage_window_basis_unavailable")

    def test_refusals(self):
        self.write([flag("spectral_texture_region_candidate", 1.0)])
        (self.run / "clicks" / "x" / "clicks.json").write_text(json.dumps({"click_grid": {"period_seconds": 0.6}}))
        self.refuse("stale_click_grid")
        payload = self.write([flag("spectral_texture_region_candidate", 1.0)])
        payload["source_sha256"] = "f" * 64
        (self.run / "flags.json").write_text(json.dumps(payload))
        self.refuse("flags_source_mismatch")
        self.write([flag("spectral_texture_region_candidate", 5.0, 4.0)])
        self.refuse("invalid_flag_interval")
        self.write([{"kind": "x", "source_time_seconds": "1.0"}])
        self.refuse("invalid_flag_interval")
        self.clicks = {"click_grid": {"period_seconds": 0, "phase_seconds_audio_relative": 0}}
        self.write([flag("spectral_texture_region_candidate", 1.0)])
        self.refuse("triage_window_basis_unavailable")

    def test_generated_strings_carry_no_verdict_vocabulary(self):
        flags = [flag(kind, 3.0 + index) for index, kind in enumerate(KINDS)] + [proxy(1.0)]
        flags[0]["evidence"]["warning"] = "detector error possible; not a confirmed mistake"
        self.write(flags)
        result = triage_tool.triage(self.run)
        for text in triage_tool.generated_strings(result):
            for word in triage_tool.GENERATED_FORBIDDEN_WORDS:
                self.assertNotIn(word, text.lower(), text)
        self.assertEqual((result["view"], result["performance_grade"], result["musical_verdict"]),
                         ("default_review_ordering_not_verdict", "not_assigned", "not_established"))
        copied = next(i for g in ("shown", "suppressed") for i in result[g] if i["flag_index"] == 0)
        self.assertIn("confirmed mistake", copied["flag"]["evidence"]["warning"])

    def test_cli_refuses_output_inside_run_dir(self):
        self.write([flag("spectral_texture_region_candidate", 1.0)])
        inside = self.run / "flags-triage.json"
        self.assertEqual(triage_tool.main([str(self.run), "--output", str(inside)]), 1)
        self.assertFalse(inside.exists())
        outside = self.run.parent / "out" / "flags-triage.json"
        self.assertEqual(triage_tool.main([str(self.run), "--output", str(outside)]), 0)
        self.assertEqual(json.loads(outside.read_text())["schema_id"], "video-utils.flags-triage.s2")

    def test_real_take_triage_invariants(self):
        base = artifact_base(REAL_RUN + "/flags.json")
        if base is None:
            self.skipTest("real-take run artifacts are not present on this host")
        run = base / REAL_RUN
        before = hashlib.sha256((run / "flags.json").read_bytes()).hexdigest()
        self.assertEqual(before, REAL_FLAGS_SHA)
        result = triage_tool.triage(run)
        flags = json.loads((run / "flags.json").read_text())["flags"]
        self.assert_invariants(result, flags)
        d = result["denominators"]
        self.assertEqual(d["total_flags"], 171)
        self.assertEqual(d["navigation_hidden"],
                         sum(1 for item in flags if item.get("kind") == "four_pulse_group_review_candidate"))
        self.assertLessEqual(d["shown"], 30)
        self.assertLessEqual(d["shown"], d["window_count"])
        self.assertEqual(result["flags_sha256"], REAL_FLAGS_SHA)
        self.assertEqual(result["window_basis"]["kind"], "click_grid_16_period_navigation_windows")
        self.assertEqual(hashlib.sha256((run / "flags.json").read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()
