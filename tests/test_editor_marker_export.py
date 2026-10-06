"""Tests for scripts/editor_marker_export.py (S2 editor_export lane, TIN-5606).

Fixtures are synthetic, in memory or in tempfile directories; no test reads
~/Documents or artifacts/runs. Structural XML/JSON checks are not editor import
evidence: application_import stays not_performed throughout.
"""
import contextlib
from fractions import Fraction
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("editor_marker_export", ROOT / "scripts/editor_marker_export.py")
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)
planner = exporter.planner

SOURCE = "a" * 64
NAME = 'recurrence, "uncertain" & <riff> ♫'
TAKE_PATH = "/Users/jess/Documents/Movie on 10-5-26 at 3.38 PM.mov"
TAKE_URL = "file:///Users/jess/Documents/Movie%20on%2010-5-26%20at%203.38%E2%80%AFPM.mov"
TIME = re.compile(r"-?[0-9]+(/[0-9]+)?s")
DESCRIPTOR = ROOT / "docs/agent-notes/sprints/20261006-s2/editor_export-tool-descriptor.json"
SKILL = ROOT / ".agents/skills/editor-marker-export/SKILL.md"


def uniform_pts(count=240, time_base="1/24", start=0, duration=1):
    return {"source_sha256": SOURCE, "time_base": time_base, "clock": "original_source_stream_timestamps_seconds",
            "frames": [{"best_effort_timestamp": start + i * duration, "duration": duration} for i in range(count)]}


def vfr_pts():
    """Real-take-shaped cadence: 1/600 ticks with 24/25/26-tick steps."""
    frames, tick = [], 0
    for i in range(240):
        step = (24, 25, 25, 26, 25)[i % 5]
        frames.append({"best_effort_timestamp": tick, "duration": 25})
        tick += step
    return {"source_sha256": SOURCE, "time_base": "1/600", "clock": "original_source_stream_timestamps_seconds",
            "frames": frames}


def export_profile(fmt="fcpxml", drop=False, origin="00:00:00:00", url=TAKE_URL):
    profile = {"schema_version": 1, "format": "editor_marker_export_profile", "plan_profile": "editor-profile.json",
               "plan_profile_sha256": "0" * 64, "timecode": {"drop_frame": drop, "origin_label": origin}}
    if fmt == "fcpxml":
        profile["fcpxml"] = {"event_name": "video-utils review", "asset_name": "take", "media_src_url": url,
                             "width": 1920, "height": 1080}
    return profile


class Fixture:
    def __init__(self, points=((1, 1),), target="final_cut_pro", pts="uniform", name=NAME):
        self.generic = {"source_sha256": SOURCE, "markers": [
            {"source_time_seconds": start, "end_seconds": end, "name": name,
             "confidence": "unvalidated_feature_not_probability", "status": "needs_review",
             "evidence": {"warning": "legato or intentional variation"}} for start, end in points],
            "frame_rate": {"average_rational": "24/1", "nominal_rational": "24/1"}}
        self.selection = {"source_sha256": SOURCE, "selected_markers": [
            {"marker_index": i, "marker_id": planner.marker_id(i, row)} for i, row in enumerate(self.generic["markers"])]}
        self.profile = {"source_sha256": SOURCE, "target": target, "source_origin": 0, "asset_origin": 0,
                        "clip_in": 0, "clip_out": 10, "parent_offset": 0,
                        "fixture_grid": {"frame_duration": "1/24", "origin": 0, "frame_id_origin": 0}}
        self.pts = uniform_pts() if pts == "uniform" else pts
        self.fmt = "fcpxml" if target == "final_cut_pro" else "resolve_ops"
        self.export = export_profile(self.fmt)

    def run(self):
        plan = planner.make_plan(self.generic, self.selection, self.profile, self.pts)
        result, files = exporter.export_plan(plan, self.generic, self.profile, self.export, self.pts, self.fmt)
        return plan, result, files


def tree(directory):
    return {str(p.relative_to(directory)): (p.read_bytes() if p.is_file() else None)
            for p in sorted(Path(directory).rglob("*"))}


class EditorMarkerExportTests(unittest.TestCase):
    # ----- disk helpers -------------------------------------------------
    def disk_fixture(self, directory, rows=((1.0, 1.0), (2.01, 2.5)), target="final_cut_pro", pts=None,
                     with_pts=True, video=None, export=None, profile_updates=None):
        directory = Path(directory)
        source = {"sha256": SOURCE}
        if video is not None:
            source["probe"] = {"video": video}
        flags = {"source_sha256": SOURCE, "flags": [
            {"source_time_seconds": s, "end_seconds": e, "kind": NAME, "status": "needs_review",
             "confidence": "unvalidated_feature_not_probability", "evidence": {"warning": "tapping or legato"}}
            for s, e in rows]}
        (directory / "manifest.json").write_text(json.dumps({"source": source}))
        (directory / "flags.json").write_text(json.dumps(flags))
        generic, _ = planner.markers.build(directory)
        selection = {"source_sha256": SOURCE, "selected_markers": [
            {"marker_index": i, "marker_id": planner.marker_id(i, m)} for i, m in enumerate(generic["markers"])]}
        (directory / "markers.json").write_text(json.dumps(generic))
        (directory / "selection.json").write_text(json.dumps(selection))
        names = ["markers.json", "selection.json", "manifest.json"]
        profile = {"source_sha256": SOURCE, "target": target, "source_origin": 0, "asset_origin": 0,
                   "clip_in": 0, "clip_out": 10, "parent_offset": 0,
                   "fixture_grid": {"frame_duration": "1/24", "origin": 0, "frame_id_origin": 0}}
        profile.update(profile_updates or {})
        if with_pts:
            (directory / "pts.json").write_text(json.dumps(pts or uniform_pts()))
            profile["pts_artifact"] = "pts.json"
            names.append("pts.json")
        profile["input_sha256"] = {n: planner.markers.sha256(directory / n) for n in names}
        (directory / "editor-profile.json").write_text(json.dumps(profile))
        fmt = "fcpxml" if target == "final_cut_pro" else "resolve_ops"
        export = export or export_profile(fmt)
        export["plan_profile_sha256"] = planner.markers.sha256(directory / "editor-profile.json")
        (directory / "export-profile.json").write_text(json.dumps(export))
        return fmt

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = exporter.main([str(a) for a in argv])
        return code, out.getvalue(), err.getvalue()

    def run_cli(self, run, fmt, out, *extra):
        return self.cli(run, "selection.json", "export-profile.json", "--format", fmt, "--output-dir", out, *extra)

    # ----- FCPXML structure ----------------------------------------------
    def test_uniform_fcpxml_version_doctype_rational_one_frame_markers(self):
        _, result, files = Fixture(((1, 1), (2.01, 2.5), ("1/48", "1/48"))).run()
        self.assertEqual(result["native_export_status"], "written_unverified")
        self.assertEqual((result["reasons"], result["cadence"]), ([], "uniform"))
        data = files[exporter.FCPXML_NAME]
        self.assertTrue(data.startswith(b'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n'))
        root = ET.fromstring(data)
        self.assertEqual((root.tag, root.get("version")), ("fcpxml", "1.10"))
        fmt = root.find("resources/format")
        self.assertEqual(fmt.get("frameDuration"), "1/24s")
        asset = root.find("resources/asset")
        self.assertEqual((asset.get("start"), asset.get("duration")), ("0s", "10s"))
        self.assertEqual(asset.find("media-rep").get("kind"), "original-media")
        clip = root.find("library/event/asset-clip")
        self.assertEqual((clip.get("start"), clip.get("duration"), clip.get("offset"), clip.get("tcFormat")),
                         ("0s", "10s", "0s", "NDF"))
        marks = clip.findall("marker")
        self.assertEqual(len(marks), 4)
        for element in root.iter():
            for key in ("start", "duration", "offset", "frameDuration"):
                if element.get(key) is not None:
                    self.assertRegex(element.get(key), TIME)
                    value = Fraction(element.get(key)[:-1])
                    self.assertEqual(exporter.fcp_time(value), element.get(key))  # reduced form
        self.assertTrue(all(m.get("duration") == fmt.get("frameDuration") for m in marks))
        self.assertIn("1/24s", [m.get("start") for m in marks])  # tie at 1/48 rounds to the later frame
        self.assertEqual(result["application_import"], "not_performed")
        self.assertIsNone(result["host_frame_id"])
        self.assertEqual(result["dtd_validation"], "not_performed")

    def test_no_completed_attribute_and_only_ordinary_markers(self):
        _, _, files = Fixture(((1, 1), (2.01, 2.5))).run()
        root = ET.fromstring(files[exporter.FCPXML_NAME])
        tags = {element.tag for element in root.iter()}
        self.assertEqual(tags, {"fcpxml", "resources", "format", "asset", "media-rep", "library", "event",
                                "asset-clip", "marker"})
        self.assertFalse(any("completed" in element.attrib for element in root.iter()))
        self.assertNotIn(b"completed=", files[exporter.FCPXML_NAME])
        self.assertNotIn(b"chapter-marker", files[exporter.FCPXML_NAME])

    def test_span_becomes_start_end_pair_and_point_single_marker(self):
        plan, result, files = Fixture(((1, 1), (2.01, 2.5))).run()
        marks = ET.fromstring(files[exporter.FCPXML_NAME]).findall("library/event/asset-clip/marker")
        point_id, span_id = plan["markers"][0]["marker_id"], plan["markers"][1]["marker_id"]
        point = [m for m in marks if f"marker_id={point_id}" in m.get("note")]
        span = [m for m in marks if f"marker_id={span_id}" in m.get("note")]
        self.assertEqual(len(point), 1)
        self.assertTrue(point[0].get("value").startswith("POINT · "))
        self.assertEqual([m.get("value").split(" · ")[0] for m in span], ["START", "END"])
        self.assertEqual([m.get("start") for m in span], ["2s", "5/2s"])  # floor(2.01*24)=48 -> 2s, ceil(2.5*24)=60 -> 5/2s
        self.assertTrue(all("not a confirmed musical mistake" in m.get("note") for m in marks))
        self.assertEqual(result["markers"][1]["native_roles"], ["START", "END"])

    # ----- Resolve preview ---------------------------------------------
    def test_resolve_operations_int_frame_ids_and_unverified_contract(self):
        plan, result, files = Fixture(((1, 1), (2.01, 2.5)), target="davinci_resolve").run()
        document = json.loads(files[exporter.RESOLVE_NAME])
        self.assertEqual(document["format"], "resolve_marker_operations_preview")
        self.assertIs(document["executable"], False)
        self.assertEqual((document["api_contract"], document["application_import"]), ("unverified", "not_performed"))
        self.assertIsNone(document["resolve_version"])
        self.assertEqual(len(document["operations"]), 2)
        for operation in document["operations"]:
            self.assertIs(type(operation["frameId"]), int)
            self.assertIs(type(operation["duration_frames"]), int)
            self.assertGreaterEqual(operation["duration_frames"], 1)
            self.assertIs(operation["executable"], False)
            self.assertEqual(operation["api_contract"], "unverified")
            self.assertIsNone(operation["host_frame_id"])
            self.assertIsNone(operation["color"])
            self.assertEqual(operation["receiver"], "explicit_original_MediaPoolItem")
            self.assertEqual(operation["custom_data"], operation["marker_id"])
        self.assertEqual([(o["frameId"], o["duration_frames"]) for o in document["operations"]], [(24, 1), (48, 12)])
        self.assertNotIn(exporter.FCPXML_NAME, files)

    # ----- Sidecar ------------------------------------------------------
    def test_sidecar_keeps_decimal_lexeme_rationals_errors_and_display_labels(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "times.json"
            path.write_text('{"t":0.100000000000000001,"s":2.01,"e":2.5}')
            value, _, _ = planner.read_json(path)
        fixture = Fixture(((value["t"], value["t"]), (value["s"], value["e"])))
        fixture.export["timecode"]["origin_label"] = "01:00:00:00"
        plan, result, _ = fixture.run()
        first, second = result["markers"]
        self.assertEqual(first["original_start_decimal"], "0.100000000000000001")
        self.assertEqual(first["source_start"], "100000000000000001/1000000000000000000")
        self.assertEqual((second["original_start_decimal"], second["original_end_decimal"]), ("2.01", "2.5"))
        planned = plan["markers"][0]["fixture_positions"]
        self.assertEqual(first["start_quantization_error_seconds"]["exact_seconds"], planned["start_error_seconds"])
        self.assertAlmostEqual(first["start_quantization_error_seconds"]["display_ms"],
                               float(Fraction(planned["start_error_seconds"])) * 1000, places=6)
        self.assertEqual((first["fixture_start_frame"], first["display_timecode_start"]), (2, "01:00:00:02"))
        self.assertEqual((second["display_timecode_start"], second["display_timecode_end"]), ("01:00:02:00", "01:00:02:12"))
        self.assertEqual(result["display_timecode_basis"], exporter.DISPLAY_TIMECODE_BASIS)
        required = {"marker_id", "marker_index", "original_start_decimal", "original_end_decimal", "source_start",
                    "source_end", "asset_local_start", "asset_local_end", "fixture_start_frame", "fixture_end_frame",
                    "start_quantization_error_seconds", "end_quantization_error_seconds", "display_timecode_start",
                    "display_timecode_end", "collisions", "disposition", "exported", "exclusion_reason", "host_frame_id"}
        for row in result["markers"]:
            self.assertLessEqual(required, set(row))
            self.assertIsNone(row["host_frame_id"])
            self.assertEqual(row["status"], "needs_review")

    def test_collisions_excluded_atomically_per_marker_and_not_shifted(self):
        fixture = Fixture(((1.01, 1.02), (1.03, 1.03), (3, 3)))
        fixture.profile["existing_markers"] = [{"fixture_frame_id": 24, "name": "user annotation"}]
        plan, result, files = fixture.run()
        self.assertEqual([a["collision"] for a in plan["actions"]],
                         ["preserve_existing_marker", "planned_same_frame_conflict", "planned_same_frame_conflict", "none"])
        marks = ET.fromstring(files[exporter.FCPXML_NAME]).findall("library/event/asset-clip/marker")
        self.assertEqual([m.get("start") for m in marks], ["3s"])
        rows = result["markers"]
        self.assertEqual([r["exported"] for r in rows], [False, False, True])
        self.assertEqual([r["exclusion_reason"] for r in rows],
                         ["preserve_existing_marker", "planned_same_frame_conflict", None])
        self.assertEqual((rows[0]["fixture_start_frame"], rows[0]["fixture_end_frame"]), (24, 25))
        self.assertEqual([c["role"] for c in rows[0]["collisions"]], ["START", "END"])
        self.assertEqual(fixture.profile["existing_markers"][0]["name"], "user annotation")
        self.assertEqual(result["counts"]["exported_marker_count"], 1)

    def test_nothing_exportable_when_every_action_collides(self):
        fixture = Fixture(((1, 1),))
        fixture.profile["existing_markers"] = [{"fixture_frame_id": 24}]
        _, result, files = fixture.run()
        self.assertEqual((result["native_export_status"], files), ("nothing_exportable", {}))
        self.assertEqual(result["markers"][0]["exclusion_reason"], "preserve_existing_marker")

    # ----- Abstention arms --------------------------------------------------
    def test_real_take_shaped_vfr_writes_no_file_or_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "run"
            run.mkdir()
            for fmt, target in (("fcpxml", "final_cut_pro"), ("resolve_ops", "davinci_resolve")):
                for child in run.iterdir():
                    child.unlink()
                self.disk_fixture(run, target=target, pts=vfr_pts(),
                                  video={"avg_frame_rate": "108930/4549", "r_frame_rate": "24/1"})
                before, parent_before = tree(run), tree(temporary)
                out = Path(temporary) / f"out-{fmt}"
                code, stdout, stderr = self.run_cli(run, fmt, out)
                self.assertEqual((code, stderr), (0, ""))
                value = json.loads(stdout)
                self.assertEqual(value["native_export_status"], "calibration_required")
                self.assertEqual((value["cadence"], value["reasons"]), ("variable", ["cadence_variable"]))
                steps = value["cadence_evidence"]["step_histogram"]["ticks"]
                self.assertEqual(set(steps), {"24", "25", "26"})
                hint = value["metadata_cadence_hint"]
                self.assertEqual((hint["average_rational"], hint["nominal_rational"]), ("108930/4549", "24/1"))
                self.assertIs(hint["used_for_decisions"], False)
                self.assertEqual((value["application_import"], value["files_written"]), ("not_performed", 0))
                self.assertIsNone(value["host_frame_id"])
                self.assertFalse(out.exists())
                self.assertEqual(tree(temporary), parent_before)
                self.assertEqual(tree(run), before)

    def test_no_pts_unknown_cadence_and_no_grid_propagate_with_zero_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "run"
            run.mkdir()
            self.disk_fixture(run, with_pts=False)
            out = Path(temporary) / "out"
            code, stdout, _ = self.run_cli(run, "fcpxml", out, "--summary")
            value = json.loads(stdout)
            self.assertEqual(code, 0)
            self.assertEqual((value["native_export_status"], value["cadence"]), ("calibration_required", "unknown"))
            self.assertIn("cadence_unknown_no_pts", value["reasons"])
            self.assertNotIn("markers", value)
            self.assertFalse(out.exists())
            self.assertEqual(sorted(p.name for p in Path(temporary).iterdir()), ["run"])
        fixture = Fixture()
        fixture.profile.pop("fixture_grid")
        plan, result, files = fixture.run()
        self.assertEqual(plan["plan_status"], "calibration_required")
        self.assertEqual((result["native_export_status"], files), ("calibration_required", {}))
        self.assertEqual(result["reasons"][0], "plan_calibration_required")

    def test_period_mismatch_and_misaligned_grid_origin(self):
        fixture = Fixture(pts=uniform_pts(250, "1/25"))
        _, result, files = fixture.run()
        self.assertEqual((result["reasons"], files), (["grid_pts_period_mismatch"], {}))
        self.assertEqual(result["cadence"], "uniform")
        fixture = Fixture()
        fixture.profile["fixture_grid"]["origin"] = "1/48"
        _, result, files = fixture.run()
        self.assertEqual((result["reasons"], files), (["grid_origin_misaligned"], {}))

    def test_drop_frame_refused_at_24_and_written_at_2997(self):
        fixture = Fixture()
        fixture.export["timecode"] = {"drop_frame": True, "origin_label": "00:00:00;00"}
        _, result, files = fixture.run()
        self.assertEqual((result["reasons"], files), (["drop_frame_rate_unsupported"], {}))
        period = Fraction(1001, 30000)
        fixture = Fixture(((ratio := planner.ratio(1800 * period), ratio), (1, 1)), pts=uniform_pts(2000, "1001/30000"))
        fixture.profile.update(clip_out=planner.ratio(2000 * period))
        fixture.profile["fixture_grid"]["frame_duration"] = "1001/30000"
        fixture.export["timecode"] = {"drop_frame": True, "origin_label": "00:00:00;00"}
        _, result, files = fixture.run()
        self.assertEqual(result["native_export_status"], "written_unverified")
        clip = ET.fromstring(files[exporter.FCPXML_NAME]).find("library/event/asset-clip")
        self.assertEqual(clip.get("tcFormat"), "DF")
        self.assertEqual(ET.fromstring(files[exporter.FCPXML_NAME]).find("resources/format").get("frameDuration"),
                         "1001/30000s")
        labels = {row["fixture_start_frame"]: row["display_timecode_start"] for row in result["markers"]}
        self.assertEqual(labels[1800], "00:01:00;02")
        self.assertEqual(labels[30], "00:00:01;00")
        self.assertEqual(result["timecode"]["tc_format"], "DF")

    def test_rate_unsupported_for_timecode_negative_time_and_missing_media(self):
        fixture = Fixture(pts=uniform_pts(235, "2/47"))
        fixture.profile["fixture_grid"]["frame_duration"] = "2/47"
        _, result, files = fixture.run()
        self.assertEqual((result["reasons"], files), (["rate_unsupported_for_timecode"], {}))
        fixture = Fixture()
        fixture.profile["parent_offset"] = -1
        fixture.export["fcpxml"]["media_src_url"] = None
        _, result, files = fixture.run()
        self.assertEqual(result["reasons"], ["media_reference_missing", "negative_native_time_unverified"])
        self.assertEqual(files, {})

    def test_clip_bounds_off_grid_and_outside_asset_extent_abstain_for_fcpxml(self):
        fixture = Fixture()
        fixture.profile["clip_out"] = "9.99"
        _, result, files = fixture.run()
        self.assertEqual((result["reasons"], files), (["clip_bounds_off_grid"], {}))
        fixture = Fixture()
        fixture.profile["clip_out"] = 11
        _, result, files = fixture.run()
        self.assertEqual((result["reasons"], files), (["clip_outside_asset_extent"], {}))

    def test_over_one_thousand_actions_requires_selection_without_truncation(self):
        points = [(planner.ratio(Fraction(9 * i, 1001)),) * 2 for i in range(1001)]
        fixture = Fixture(points, target="davinci_resolve")
        plan, result, files = fixture.run()
        self.assertEqual((plan["plan_status"], plan["actions"]), ("selection_required", []))
        self.assertEqual((result["native_export_status"], files), ("selection_required", {}))
        self.assertEqual(result["reasons"], ["plan_selection_required"])
        self.assertEqual(len(result["markers"]), 1001)

    def test_audio_only_tail_stays_in_sidecar_outside_video_coverage(self):
        fixture = Fixture(((5, 5), (10.5, 10.5)), target="davinci_resolve")
        fixture.profile["clip_out"] = 11
        _, result, files = fixture.run()
        self.assertEqual(result["native_export_status"], "written_unverified")
        tail = result["markers"][1]
        self.assertEqual((tail["disposition"], tail["exported"], tail["exclusion_reason"]),
                         ("outside_video_coverage", False, "outside_video_coverage"))
        self.assertEqual(len(json.loads(files[exporter.RESOLVE_NAME])["operations"]), 1)

    # ----- Serialization safety ------------------------------------------------
    def test_xml_escaping_round_trip_and_percent_encoded_media_url(self):
        tricky = 'riff & <tap> "sweep" \'legato\'\nline two\ttab ♫ C1 32.7 Hz'
        _, _, files = Fixture(((1, 1),), name=tricky).run()
        root = ET.fromstring(files[exporter.FCPXML_NAME])
        note = root.find("library/event/asset-clip/marker").get("note")
        self.assertIn(f"candidate={tricky};", note)
        self.assertEqual(root.find("resources/asset/media-rep").get("src"), TAKE_URL)
        self.assertEqual(exporter.file_url_from_path(TAKE_PATH), TAKE_URL)
        for bad in ("file:///Users/jess/Movie on.mov", "file:///Users/jess/3.38 PM.mov", "/Users/jess/a.mov",
                    "file://host/a.mov", "https://example.com/a.mov", "file:///a.mov?x=1", "file:///a%2.mov"):
            profile = export_profile(url=bad)
            with self.subTest(url=bad), self.assertRaises(ValueError):
                exporter.validate_export_profile(profile, "fcpxml")
        with self.assertRaises(ValueError):
            Fixture(((1, 1),), name="bell\x07").run()

    def test_closed_export_profile_rejections(self):
        cases = {"unknown": lambda p: p.update(command="never run"),
                 "bool_version": lambda p: p.update(schema_version=True),
                 "format": lambda p: p.update(format="edl"),
                 "timecode_extra": lambda p: p["timecode"].update(rate="24/1"),
                 "drop_type": lambda p: p["timecode"].update(drop_frame=1),
                 "fcpxml_extra": lambda p: p["fcpxml"].update(completed=1),
                 "event_oversized": lambda p: p["fcpxml"].update(event_name="x" * 257),
                 "width_bool": lambda p: p["fcpxml"].update(width=True),
                 "plan_abs": lambda p: p.update(plan_profile="/etc/profile.json")}
        for name, mutate in cases.items():
            profile = export_profile()
            mutate(profile)
            with self.subTest(name=name), self.assertRaises(ValueError):
                exporter.validate_export_profile(profile, "fcpxml")
        with self.assertRaises(ValueError):
            exporter.validate_export_profile(export_profile("fcpxml"), "resolve_ops")  # fcpxml block refused
        with self.assertRaises(ValueError):
            exporter.validate_export_profile(export_profile("resolve_ops"), "fcpxml")  # fcpxml block required
        with self.assertRaises(ValueError):
            exporter.validate_export_profile(export_profile("resolve_ops"), "edl")
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "run"
            run.mkdir()
            self.disk_fixture(run)
            stale = json.loads((run / "export-profile.json").read_text())
            stale["plan_profile_sha256"] = "f" * 64
            (run / "export-profile.json").write_text(json.dumps(stale))
            out = Path(temporary) / "out"
            code, stdout, stderr = self.run_cli(run, "fcpxml", out)
            self.assertEqual((code, stdout), (1, ""))
            self.assertIn("Stale plan_profile_sha256", stderr)
            self.assertFalse(out.exists())
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as caught:
                exporter.main([str(run), "selection.json", "export-profile.json", "--format", "edl",
                               "--output-dir", str(out), "--bogus=" + "♫" * 100_000])
            self.assertEqual(caught.exception.code, 2)
            self.assertLessEqual(len(err.getvalue().encode()), exporter.MAX_ERROR_BYTES)
            self.assertFalse(out.exists())

    def test_target_format_mismatch_and_invalid_origin_label_are_errors(self):
        fixture = Fixture()
        fixture.fmt = "resolve_ops"
        fixture.export = export_profile("resolve_ops")
        with self.assertRaisesRegex(ValueError, "does not match the planner target"):
            fixture.run()
        fixture = Fixture()
        fixture.export["timecode"]["origin_label"] = "00:00:00;00"
        with self.assertRaisesRegex(ValueError, "separator_mode_mismatch"):
            fixture.run()

    # ----- CLI, determinism and immutability ---------------------------------
    def test_cli_determinism_byte_identical_and_hashes_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "run"
            run.mkdir()
            self.disk_fixture(run, rows=((1.0, 1.0), (2.01, 2.5), (3.0, 3.0)))
            before = tree(run)
            outputs = []
            for label in ("a", "b"):
                out = Path(temporary) / f"export-{label}"
                code, stdout, stderr = self.run_cli(run, "fcpxml", out, "--summary")
                self.assertEqual((code, stderr), (0, ""))
                value = json.loads(stdout)
                self.assertLessEqual(len(stdout.encode()), exporter.MAX_SUMMARY_BYTES)
                self.assertEqual(value["native_export_status"], "written_unverified")
                self.assertEqual(sorted(value["output_sha256"]), [exporter.SIDECAR_NAME, exporter.FCPXML_NAME])
                for name, digest in value["output_sha256"].items():
                    self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), digest)
                self.assertEqual(value["files_written"], 2)
                outputs.append(tree(out))
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(tree(run), before)
            self.assertEqual(sorted(p.name for p in Path(temporary).iterdir()), ["export-a", "export-b", "run"])
            sidecar = json.loads(outputs[0][exporter.SIDECAR_NAME])
            self.assertEqual(sidecar["format"], "editor_marker_export_sidecar")
            self.assertEqual(sidecar["payload_sha256"][exporter.FCPXML_NAME],
                             hashlib.sha256(outputs[0][exporter.FCPXML_NAME]).hexdigest())
            for key, value in exporter.FIXED_UNKNOWN_FIELDS.items():
                self.assertEqual(sidecar[key], value)
            self.assertNotIn("output_dir", sidecar)
            self.assertEqual(len(sidecar["markers"]), 3)
            self.assertIn("export-profile.json", sidecar["input_sha256"])
            self.assertIn("editor-profile.json", sidecar["input_sha256"])

    def test_existing_output_dir_refused_unmodified_and_inputs_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "run"
            run.mkdir()
            self.disk_fixture(run, target="davinci_resolve")
            out = Path(temporary) / "out"
            out.mkdir()
            (out / "keep.txt").write_text("user file")
            before_run, before_out = tree(run), tree(out)
            code, stdout, stderr = self.run_cli(run, "resolve_ops", out)
            self.assertEqual((code, stdout), (1, ""))
            self.assertIn("refusing to overwrite", stderr)
            self.assertEqual((tree(run), tree(out)), (before_run, before_out))
            # Staging race: path appears after the pre-check; staging is removed, nothing replaced.
            out2 = Path(temporary) / "out2"
            original = exporter.build

            def appear(*args, **kwargs):
                out2.mkdir()
                return original(*args, **kwargs)
            with patch.object(exporter, "build", side_effect=appear):
                code, _, stderr = self.run_cli(run, "resolve_ops", out2)
            self.assertEqual(code, 1)
            self.assertEqual(tree(out2), {})
            self.assertEqual(sorted(p.name for p in Path(temporary).iterdir()), ["out", "out2", "run"])
            code, stdout, _ = self.run_cli(run, "resolve_ops", Path(temporary) / "fresh")
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout)["native_export_status"], "written_unverified")
            self.assertEqual(tree(run), before_run)

    def test_input_change_during_export_aborts_before_publish(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "run"
            run.mkdir()
            self.disk_fixture(run)
            out = Path(temporary) / "out"
            original = exporter.write_exclusive

            def tamper(*args, **kwargs):
                (run / "selection.json").write_text((run / "selection.json").read_text() + " ")
                return original(*args, **kwargs)
            with patch.object(exporter, "write_exclusive", side_effect=tamper):
                code, stdout, stderr = self.run_cli(run, "fcpxml", out)
            self.assertEqual((code, stdout), (1, ""))
            self.assertIn("Input changed during export", stderr)
            self.assertEqual(sorted(p.name for p in Path(temporary).iterdir()), ["run"])

    def test_dtd_validation_not_performed_passed_failed_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            temporary = Path(temporary)
            run = temporary / "run"
            run.mkdir()
            self.disk_fixture(run)
            code, stdout, _ = self.run_cli(run, "fcpxml", temporary / "plain", "--summary")
            self.assertEqual(json.loads(stdout)["dtd_validation"], "not_performed")
            dtd = temporary / "synthetic.dtd"
            dtd.write_text(SYNTHETIC_DTD)
            with patch.object(exporter, "XMLLINT", str(temporary / "missing-xmllint")):
                code, stdout, _ = self.run_cli(run, "fcpxml", temporary / "missing", "--dtd", dtd, "--summary")
            value = json.loads(stdout)
            self.assertEqual((code, value["dtd_validation"]), (0, "unavailable"))
            self.assertEqual(value["dtd_validator"]["diagnostics_tail"], "validator_missing")
            if not os.access(exporter.XMLLINT, os.X_OK):
                self.skipTest("LABELLED SKIP: /usr/bin/xmllint unavailable; passed/failed arms not exercised")
            code, stdout, _ = self.run_cli(run, "fcpxml", temporary / "checked", "--dtd", dtd, "--summary")
            value = json.loads(stdout)
            self.assertEqual((code, value["dtd_validation"]), (0, "passed"))
            self.assertEqual(value["dtd_validator"]["dtd_sha256"], hashlib.sha256(dtd.read_bytes()).hexdigest())
            self.assertIn("does not establish FCPXML 1.10 conformance", value["dtd_validator"]["scope"])
            sidecar = json.loads((temporary / "checked" / exporter.SIDECAR_NAME).read_text())
            self.assertEqual(sidecar["dtd_validation"], "passed")
            mutated = temporary / "mutated.fcpxml"
            mutated.write_bytes((temporary / "checked" / exporter.FCPXML_NAME).read_bytes()
                                .replace(b"</asset-clip>", b"<bogus/></asset-clip>"))
            status, validator = exporter.dtd_validate(mutated, dtd.resolve(), "0" * 64)
            self.assertEqual(status, "failed")
            self.assertNotEqual(validator["returncode"], 0)
            link = temporary / "link.dtd"
            link.symlink_to(dtd)
            code, _, _ = self.run_cli(run, "fcpxml", temporary / "linked", "--dtd", link)
            self.assertEqual(code, 1)
            self.assertFalse((temporary / "linked").exists())

    def test_descriptor_draft_closed_schema_and_skill_draft(self):
        descriptor = json.loads(DESCRIPTOR.read_text())
        schema = descriptor["inputSchema"]
        self.assertEqual(descriptor["name"], "editor_marker_export")
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(set(schema["properties"]), {"run_dir", "selection", "profile", "format", "timeout_seconds"})
        self.assertEqual(schema["properties"]["format"]["enum"], ["fcpxml", "resolve_ops"])
        timeout = schema["properties"]["timeout_seconds"]
        self.assertEqual((timeout["type"], timeout["minimum"]), ("integer", 1))
        self.assertLessEqual(timeout["maximum"], 120)
        self.assertEqual(set(schema["required"]), {"run_dir", "selection", "profile", "format"})
        self.assertEqual(descriptor["skill"], ".agents/skills/editor-marker-export/SKILL.md")
        text = SKILL.read_text()
        self.assertTrue(text.startswith("---\nname: editor-marker-export\n"))
        for phrase in ("calibration_required", "not_performed", "host_frame_id", "needs_review"):
            self.assertIn(phrase, text)


SYNTHETIC_DTD = """<!-- Synthetic test DTD covering only the elements this exporter writes. Not Apple's FCPXML 1.10 DTD. -->
<!ELEMENT fcpxml (resources, library)>
<!ATTLIST fcpxml version CDATA #REQUIRED>
<!ELEMENT resources (format, asset)>
<!ELEMENT format EMPTY>
<!ATTLIST format id ID #REQUIRED frameDuration CDATA #IMPLIED width CDATA #IMPLIED height CDATA #IMPLIED>
<!ELEMENT asset (media-rep)>
<!ATTLIST asset id ID #REQUIRED name CDATA #IMPLIED start CDATA #IMPLIED duration CDATA #IMPLIED
                hasVideo (0|1) "0" format IDREF #IMPLIED>
<!ELEMENT media-rep EMPTY>
<!ATTLIST media-rep kind (original-media|proxy-media) "original-media" src CDATA #REQUIRED>
<!ELEMENT library (event*)>
<!ELEMENT event (asset-clip*)>
<!ATTLIST event name CDATA #IMPLIED>
<!ELEMENT asset-clip (marker*)>
<!ATTLIST asset-clip ref IDREF #REQUIRED name CDATA #IMPLIED offset CDATA #IMPLIED start CDATA #IMPLIED
                     duration CDATA #REQUIRED format IDREF #IMPLIED tcFormat (DF|NDF) #IMPLIED>
<!ELEMENT marker EMPTY>
<!ATTLIST marker start CDATA #REQUIRED duration CDATA #IMPLIED value CDATA #REQUIRED note CDATA #IMPLIED>
"""

if __name__ == "__main__":
    unittest.main()
