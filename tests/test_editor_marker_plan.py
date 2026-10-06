import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
SPEC = importlib.util.spec_from_file_location("editor_marker_plan", Path(__file__).resolve().parents[1] / "scripts/editor_marker_plan.py")
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)


class EditorMarkerPlanTests(unittest.TestCase):
    def inputs(self, points=((1, 1),), target="davinci_resolve"):
        generic = {"source_sha256": "a" * 64, "markers": [
            {"source_time_seconds": start, "end_seconds": end, "name": "recurrence, \"uncertain\" & <riff> ♫",
             "confidence": "unvalidated_feature_not_probability", "status": "needs_review",
             "evidence": {"warning": "legato or intentional variation"}} for start, end in points]}
        selection = {"source_sha256": "a" * 64, "selected_markers": [
            {"marker_index": i, "marker_id": planner.marker_id(i, row)} for i, row in enumerate(generic["markers"])]}
        profile = {"source_sha256": "a" * 64, "target": target,
                   "source_origin": 0, "asset_origin": 0, "clip_in": 0, "clip_out": 10,
                   "parent_offset": 3600, "fixture_grid": {"frame_duration": "1/24", "origin": 0, "frame_id_origin": 0}}
        pts = {"source_sha256": "a" * 64, "time_base": "1/24", "clock": "original_source_stream_timestamps_seconds",
               "frames": [{"best_effort_timestamp": i, "duration": 1} for i in range(240)]}
        return generic, selection, profile, pts

    def test_nonzero_negative_origin_and_parent_are_independent(self):
        generic, selection, profile, pts = self.inputs(((-.2, -.2),))
        profile.update(source_origin=-.5, parent_offset=3600)
        pts["frames"] = [{"best_effort_timestamp": i, "duration": 1} for i in range(-12, 240)]
        row = planner.make_plan(generic, selection, profile, pts)["markers"][0]
        self.assertEqual(row["asset_local_start"], "3/10")
        self.assertEqual(row["parent_time"], "36003/10")
        self.assertIsNone(row["host_frame_id"])

    def test_trimmed_local_origin_apple_example(self):
        generic, selection, profile, pts = self.inputs(((3, 3),))
        profile.update(asset_origin=5, clip_in=5, clip_out=15, parent_offset=10)
        row = planner.make_plan(generic, selection, profile, pts)["markers"][0]
        self.assertEqual(row["asset_local_start"], "8/1")
        self.assertEqual(row["parent_time"], "13/1")

    def test_rational_grid_tie_and_outward_span(self):
        generic, selection, profile, pts = self.inputs((("1/48", "1/48"), (1.01, 1.02)))
        result = planner.make_plan(generic, selection, profile, pts)
        self.assertEqual(result["markers"][0]["fixture_positions"]["start_frame"], 1)
        self.assertEqual(result["markers"][0]["fixture_positions"]["start_error_seconds"], "1/48")
        span = result["markers"][1]["fixture_positions"]
        self.assertEqual((span["start_frame"], span["end_frame"], span["duration_frames"]), (24, 25, 1))
        profile["fixture_grid"]["frame_duration"] = "1001/24000"
        alternate = planner.make_plan(generic, selection, profile, pts)
        self.assertNotEqual(result["markers"][0]["fixture_positions"], alternate["markers"][0]["fixture_positions"])

    def test_vfr_containing_frame_not_nearest_grid(self):
        generic, selection, profile, _ = self.inputs((("48/600", "48/600"),))
        pts = {"source_sha256": "a" * 64, "time_base": "1/600", "clock": "original_source_stream_timestamps_seconds", "frames": [
            {"best_effort_timestamp": 0, "duration": 25}, {"best_effort_timestamp": 25, "duration": 24},
            {"best_effort_timestamp": 49, "duration": 26}, {"best_effort_timestamp": 75, "duration": 25}]}
        row = planner.make_plan(generic, selection, profile, pts)["markers"][0]
        self.assertEqual(row["preview_frame_index"], 1)
        self.assertEqual(row["fixture_positions"]["start_frame"], 2)
        self.assertIsNone(row["host_frame_id"])

    def test_gap_duplicate_pts_and_unknown_duration(self):
        generic, selection, profile, _ = self.inputs((("30/600", "30/600"),))
        pts = {"source_sha256": "a" * 64, "time_base": "1/600", "clock": "original_source_stream_timestamps_seconds", "frames": [
            {"best_effort_timestamp": 0, "duration": 25}, {"best_effort_timestamp": 49, "duration": 25}]}
        result = planner.make_plan(generic, selection, profile, pts)
        self.assertIsNone(result["markers"][0]["preview_frame_index"])
        self.assertEqual(result["markers"][0]["disposition"], "outside_video_coverage")
        self.assertEqual(result["actions"], [])
        pts["frames"][1]["best_effort_timestamp"] = 0
        with self.assertRaisesRegex(ValueError, "Duplicate or nonmonotonic"):
            planner.make_plan(generic, selection, profile, pts)
        pts["frames"][1] = {"best_effort_timestamp": 49}
        with self.assertRaisesRegex(ValueError, "durations must be integers"):
            planner.make_plan(generic, selection, profile, pts)

    def test_span_crossing_gap_and_audio_only_tail_abstain(self):
        generic, selection, profile, _ = self.inputs(((.01, .12), (150.90, 150.954059)))
        profile["clip_out"] = 151
        pts = {"source_sha256": "a" * 64, "time_base": "1/600", "clock": "original_source_stream_timestamps_seconds", "frames": [
            {"best_effort_timestamp": 0, "duration": 25}, {"best_effort_timestamp": 49, "duration": 25},
            {"best_effort_timestamp": 90506, "duration": 25}]}
        result = planner.make_plan(generic, selection, profile, pts)
        self.assertEqual([row["disposition"] for row in result["markers"]], ["outside_video_coverage"] * 2)
        self.assertEqual(result["actions"], [])
        self.assertEqual(result["markers"][1]["source_end"], "150954059/1000000")

    def test_missing_origins_and_pts_do_not_default_from_average_rate(self):
        generic, selection, profile, _ = self.inputs()
        generic["frame_rate"] = {"average_rational": "108930/4549", "nominal_rational": "24/1"}
        profile.pop("source_origin")
        profile.pop("fixture_grid")
        result = planner.make_plan(generic, selection, profile)
        self.assertEqual(result["plan_status"], "calibration_required")
        self.assertIsNone(result["markers"][0]["asset_local_start"])
        self.assertIsNone(result["markers"][0]["preview_frame_index"])
        self.assertEqual(result["actions"], [])

    def test_fcp_span_pair_and_existing_collision_preserved(self):
        generic, selection, profile, pts = self.inputs(((1.01, 1.02), (1.03, 1.03)), "final_cut_pro")
        profile["existing_markers"] = [{"fixture_frame_id": 24, "name": "user annotation"}]
        result = planner.make_plan(generic, selection, profile, pts)
        self.assertEqual([a["role"] for a in result["actions"]], ["START", "END", "POINT"])
        self.assertEqual(result["actions"][0]["collision"], "preserve_existing_marker")
        self.assertEqual(result["actions"][1]["collision"], "planned_same_frame_conflict")
        self.assertEqual(result["actions"][2]["collision"], "planned_same_frame_conflict")
        self.assertTrue(all(a["executable"] is False for a in result["actions"]))
        self.assertEqual(profile["existing_markers"][0]["name"], "user annotation")

    def test_fcp_exclusive_end_at_clip_out_not_shifted(self):
        generic, selection, profile, pts = self.inputs(((9, 10),), "final_cut_pro")
        result = planner.make_plan(generic, selection, profile, pts)
        self.assertEqual(result["markers"][0]["disposition"], "exclusive_end_boundary_unrepresentable")
        self.assertEqual(result["actions"], [])

    def test_overlapping_duration_cannot_bridge_later_gap(self):
        generic, selection, profile, _ = self.inputs(((0, 3),))
        pts = {"source_sha256": "a" * 64, "time_base": "1/1", "clock": "original_source_stream_timestamps_seconds",
               "frames": [{"best_effort_timestamp": 0, "duration": 100},
                          {"best_effort_timestamp": 1, "duration": 1},
                          {"best_effort_timestamp": 4, "duration": 1}]}
        result = planner.make_plan(generic, selection, profile, pts)
        self.assertEqual(result["markers"][0]["disposition"], "outside_video_coverage")
        self.assertEqual(result["actions"], [])

    def test_unicode_uncertainty_round_trip_no_confidence_promotion(self):
        inputs = self.inputs()
        result = planner.make_plan(*inputs)
        restored = json.loads(json.dumps(result, ensure_ascii=False, allow_nan=False))
        row = restored["markers"][0]
        self.assertIn('"uncertain" & <riff> ♫', row["notes"])
        self.assertEqual(row["confidence"], "unvalidated_feature_not_probability")
        self.assertEqual(row["evidence"]["warning"], "legato or intentional variation")
        self.assertEqual(restored["native_contract_status"], "native_contract_unverified")

    def test_source_json_decimal_lexeme_survives_float_precision_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.json"
            path.write_text('{"time":0.100000000000000001}')
            value, _, _ = planner.read_json(path)
            generic, selection, profile, pts = self.inputs(((value["time"], value["time"]),))
            result = planner.make_plan(generic, selection, profile, pts)
            self.assertEqual(result["markers"][0]["source_start"], "100000000000000001/1000000000000000000")
            self.assertEqual(result["selected_ids"][0], planner.marker_id(0, generic["markers"][0]))
            json.dumps(result, allow_nan=False)

    def test_stale_selection_source_invalid_span_and_mistake_promotion(self):
        for kind in ("source", "id", "span", "promotion", "retiming"):
            generic, selection, profile, pts = self.inputs()
            if kind == "source": profile["source_sha256"] = "b" * 64
            if kind == "id": selection["selected_markers"][0]["marker_id"] = "stale"
            if kind == "span": generic["markers"][0]["end_seconds"] = 0
            if kind == "promotion": generic["markers"][0]["performance_issue_confirmed"] = True
            if kind == "retiming": profile["mapping_kind"] = "reverse"
            if kind in ("span", "promotion"):
                selection["selected_markers"][0]["marker_id"] = planner.marker_id(0, generic["markers"][0])
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                planner.make_plan(generic, selection, profile, pts)

    def test_limit_requires_selection_without_truncated_actions(self):
        generic, selection, profile, pts = self.inputs(((1, 2),), "final_cut_pro")
        with patch.object(planner, "MAX_ACTIONS", 1):
            result = planner.make_plan(generic, selection, profile, pts)
        self.assertEqual(result["plan_status"], "selection_required")
        self.assertEqual(result["selected_count"], 1)
        self.assertEqual(result["actions"], [])

    def disk_fixture(self, directory):
        generic, selection, profile, pts = self.inputs()
        manifest = {"source": {"sha256": "a" * 64}}
        flags = {"source_sha256": "a" * 64, "flags": [{"source_time_seconds": 1, "end_seconds": 1,
            "kind": "review_candidate", "status": "needs_review", "evidence": {}}]}
        for name, value in (("manifest.json", manifest), ("flags.json", flags)):
            (directory / name).write_text(json.dumps(value))
        generic, _ = planner.markers.build(directory)
        selection = {"source_sha256": "a" * 64, "selected_markers": [{"marker_index": 0,
                     "marker_id": planner.marker_id(0, generic["markers"][0])}]}
        for name, value in (("markers.json", generic), ("selection.json", selection), ("pts.json", pts)):
            (directory / name).write_text(json.dumps(value))
        profile["pts_artifact"] = "pts.json"
        profile["input_sha256"] = {name: planner.markers.sha256(directory / name)
            for name in ("markers.json", "selection.json", "manifest.json", "pts.json")}
        (directory / "profile.json").write_text(json.dumps(profile))
        return profile

    def test_real_entrypoint_is_stdout_only_and_checks_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.disk_fixture(directory)
            before = {p.name: p.read_bytes() for p in directory.iterdir()}
            with patch.object(sys, "argv", ["planner", str(directory), "selection.json", "profile.json"]), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(planner.main(), 0)
            value = json.loads(output.getvalue())
            self.assertEqual(value["selected_count"], 1)
            self.assertFalse(value["executable"])
            self.assertEqual(before, {p.name: p.read_bytes() for p in directory.iterdir()})
            (directory / "pts.json").write_text('{}')
            with self.assertRaises(ValueError): planner.build(directory, "selection.json", "profile.json")

    def test_duplicate_nonfinite_json_and_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.disk_fixture(directory)
            good = (directory / "profile.json").read_bytes()
            for invalid in ('{"target":1,"target":2}', '{"x":NaN}', '{"x":1e999}'):
                (directory / "profile.json").write_text(invalid)
                with self.assertRaises(ValueError): planner.build(directory, "selection.json", "profile.json")
            (directory / "profile.json").write_bytes(good)
            (directory / "linked.json").symlink_to(directory / "profile.json")
            for name in ("linked.json", "../profile.json"):
                with self.assertRaises(ValueError): planner.build(directory, "selection.json", name)


if __name__ == "__main__":
    unittest.main()
