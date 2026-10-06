"""Synthetic-grid tests for anchor-click arrangement projection and its scorer.

Stdlib only; no media, models or detector runs. Fixtures are in-test grids,
the repository arrangement, mark files and temporary output areas.
"""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("phrase_anchor_under_test", ROOT / "scripts/phrase_anchor.py")
pa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pa)

ARRANGEMENT = json.loads((ROOT / "program/demo-arrangement.json").read_text())
SOURCE = ARRANGEMENT["source_sha256"]
ANALYZED = "cd" * 32
MANIFEST = "ef" * 32
REAL_GRID = Path("/Users/jess/git/video-utils/artifacts/runs/20261006T034521Z-a0def0c43eac/clicks/"
                 "20261006T040944Z-a98ce2dc1f72/clicks.json")
REAL_GRID_SHA = "cee9a506d70f3bebb95d054ae6a4bb5f8c880133d31327a8b7c0a19950497937"


def expected_positions():
    cursor, positions = 0, []
    for section in ARRANGEMENT["sections"]:
        for _ in range(section["phrase_count"]):
            positions.append(cursor)
            cursor += section["clicks_per_phrase"]
    return positions + [cursor]


def grid_value(period=.6, phase=.2, start=0., duration=400., offset_ms=2., drop=(), offsets=None):
    beats = int((duration - phase) / period) + 1
    events = []
    for j in range(beats):
        if j in drop:
            continue
        value = (offsets or {}).get(j, offset_ms)
        events.append({"analysis_frame": j, "beat_index": j, "audio_relative_seconds": phase + j * period + value / 1000,
                       "grid_offset_ms": value})
    return {"schema_version": 1, "pcm": {"duration_seconds": duration, "sample_rate": 44100},
            "timeline": {"audio_stream_start_seconds": start},
            "click_grid": {"period_seconds": period, "phase_seconds_audio_relative": phase, "bpm": 60 / period,
                           "identity": "synthetic_fixture_grid", "median_absolute_residual_ms": abs(offset_ms),
                           "candidate_coverage": 1., "observed_events": events},
            "source": {"sha256": ANALYZED},
            "source_lineage": {"analyzed_input_sha256": ANALYZED, "original_source_sha256": SOURCE,
                               "sample_mapping": {"no_time_stretch": True}}}


def run_project(grid=None, r=2, k=None, seconds=None, **kwargs):
    grid = pa.parse_grid(grid or grid_value())
    if k is None and seconds is None:
        k = 0
    return pa.project(grid, copy.deepcopy(ARRANGEMENT), r, lattice_index=k, anchor_seconds=seconds, **kwargs)


class Area:
    """Temporary lane output area plus input directory."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.area = base / "artifacts" / "s2" / "phrase_anchor_riff"
        self.inputs = base / "inputs"
        self.inputs.mkdir()
        self.patch = mock.patch.object(pa, "OUTPUT_AREA", self.area)
        self.patch.start()
        return self

    def __exit__(self, *exc):
        self.patch.stop()
        self.tmp.cleanup()

    def put(self, name, value):
        path = self.inputs / name
        path.write_text(json.dumps(value))
        return path

    def run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = pa.main([str(item) for item in argv])
        return code, (json.loads(out.getvalue()) if out.getvalue() else None), err.getvalue()


def spans_doc(area, grid=None, k=0, r=2, name="spans.json"):
    clicks = area.put("clicks.json", grid or grid_value())
    arrangement = area.put("arrangement.json", ARRANGEMENT)
    code, result, err = area.run(["spans", "--clicks", clicks, "--arrangement", arrangement,
                                  "--clicks-per-grid-period", r, "--anchor-lattice-index", k,
                                  "--anchor-source", "synthetic", "--output", area.area / name])
    assert code == 0, err
    return area.area / name, json.loads((area.area / name).read_text())


def annotation(start, end=None, *, actor="operator", basis="operator_assertion", status="needs_review",
               kind="phrase_duration"):
    end = start if end is None else end
    who = {"actor": actor, "via": "browser" if actor == "operator" else "agent"}
    operator = basis == "operator_assertion"
    return {"kind": kind, "basis": basis, "status": status,
            "source_span": {"start_seconds": start, "end_seconds": end, "extent_known": end != start},
            "reported_by": who, "operator_certainty": "uncertain" if operator else None,
            "operator_quote": "phrase starts here" if operator else None, "note": "synthetic fixture mark",
            "id": str(uuid.uuid4()), "candidate_id": None, "reference_sha256": None,
            "created_at": "2026-10-06T10:00:00+00:00", "updated_at": "2026-10-06T10:00:00+00:00",
            "created_with": {"manifest_sha256": MANIFEST, "candidate_artifact_sha256": None},
            "updated_with": {"manifest_sha256": MANIFEST, "candidate_artifact_sha256": None},
            "claim_label": pa.load_module("labels", "scripts/annotation_v2.py").LABELS[basis],
            "musical_verdict": "not_established"}


def store(items, source=SOURCE):
    receipts = [{"key": f"fixture-key-{i:04d}", "request_sha256": "aa" * 32, "annotation_id": item["id"],
                 "committed_revision": i + 1} for i, item in enumerate(items)]
    return {"schema_version": 2, "source_sha256": source, "manifest_sha256": MANIFEST, "revision": len(items),
            "annotations": items, "listening_acceptance": "not_established", "replay_receipts": receipts}


class ExpansionArithmeticTests(unittest.TestCase):
    def test_01_expansion_27_units_28_boundaries_404_clicks(self):
        result = run_project()
        self.assertEqual(len(result["units"]), 27)
        self.assertEqual(len(result["boundaries"]), 28)
        self.assertEqual(result["expanded"]["totals"]["intended_click_count"], 404)
        self.assertEqual([row["click_index"] for row in result["boundaries"]], expected_positions())
        self.assertEqual([row["id"] for row in result["boundaries"]], [f"boundary:{i}" for i in range(28)])
        kinds = [row["kind"] for row in result["units"]]
        self.assertEqual((kinds.count("phrase"), kinds.count("breakdown"), kinds.count("rest")), (24, 2, 1))
        self.assertEqual(sum(row["click_count"] for row in result["units"]), 404)
        for unit, start, end in zip(result["units"], expected_positions(), expected_positions()[1:]):
            self.assertEqual((unit["start_click_index"], unit["end_click_index"]), (start, end))

    def test_02_exact_anchor_arithmetic_on_synthetic_grid(self):
        s0, phi, period, r, k0 = 1.5, .2, .6, 2, 7
        result = run_project(grid_value(start=s0, phase=phi, period=period), r=r, k=k0)
        for row in result["boundaries"]:
            self.assertEqual(row["lattice_index"], k0 + row["click_index"])
            self.assertAlmostEqual(row["source_seconds"], s0 + phi + (k0 + row["click_index"]) * period / r, places=12)
        for unit in result["units"]:
            self.assertAlmostEqual(unit["start_source_seconds"], s0 + phi + (k0 + unit["start_click_index"]) * .3, places=12)
            self.assertAlmostEqual(unit["end_source_seconds"], s0 + phi + (k0 + unit["end_click_index"]) * .3, places=12)
        r1 = run_project(grid_value(start=s0, phase=phi, period=period), r=1, k=k0)
        self.assertAlmostEqual(r1["boundaries"][1]["source_seconds"], s0 + phi + (k0 + 16) * period, places=12)

    def test_03_anchor_seconds_snapping_residual_and_refusals(self):
        grid = grid_value(period=.6, phase=.2)
        target = .2 + 10 * .3
        result = run_project(grid, r=2, seconds=target + .05)
        self.assertEqual(result["anchor"]["k0"], 10)
        self.assertAlmostEqual(result["anchor"]["snap_residual_seconds"], .05, places=12)
        self.assertAlmostEqual(run_project(grid, r=2, seconds=target - .07)["anchor"]["snap_residual_seconds"], -.07, places=12)
        with self.assertRaisesRegex(pa.DomainError, "anchor_snap_residual_exceeds_quarter_click"):
            run_project(grid, r=2, seconds=target + .08)  # p/4 = .075
        with self.assertRaisesRegex(pa.DomainError, "anchor_before_grid_origin"):
            run_project(grid, r=2, seconds=-1.)
        for bad in (None, 3, 0, True, 2.0):
            with self.assertRaisesRegex(pa.DomainError, "clicks_per_grid_period_must_be_1_or_2"):
                run_project(grid, r=bad, k=1)
        with self.assertRaisesRegex(pa.DomainError, "exactly_one_anchor_required"):
            pa.project(pa.parse_grid(grid), ARRANGEMENT, 2, lattice_index=1, anchor_seconds=3.)
        with Area() as area, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                area.run(["spans", "--clicks", area.put("c.json", grid), "--arrangement", area.put("a.json", ARRANGEMENT),
                          "--clicks-per-grid-period", 3, "--anchor-lattice-index", 1, "--anchor-source", "x",
                          "--output", area.area / "x.json"])
            with self.assertRaises(SystemExit):  # r is required, never inferred
                area.run(["spans", "--clicks", area.put("c2.json", grid), "--arrangement", area.put("a2.json", ARRANGEMENT),
                          "--anchor-lattice-index", 1, "--anchor-source", "x", "--output", area.area / "y.json"])

    def test_04_half_period_parity_flagging(self):
        odd = run_project(r=2, k=29)
        self.assertTrue(all(row["grid"]["on_interpolated_half_period"] for row in odd["boundaries"]))
        self.assertTrue(all(row["grid_beat_index"] is None for row in odd["boundaries"]))
        even = run_project(r=2, k=30)
        self.assertFalse(any(row["grid"]["on_interpolated_half_period"] for row in even["boundaries"]))
        self.assertEqual([row["grid_beat_index"] for row in even["boundaries"]],
                         [(30 + c) // 2 for c in expected_positions()])
        single = run_project(r=1, k=29)
        self.assertFalse(any(row["grid"]["on_interpolated_half_period"] for row in single["boundaries"]))
        self.assertEqual(single["boundaries"][0]["grid_beat_index"], 29)
        self.assertEqual(odd["counts"]["interpolated_half_period_boundaries"], 28)
        hypothesis = next(h for h in odd["hypotheses"] if h["shift_clicks"] == 1)
        self.assertFalse(hypothesis["downstream_boundaries"][0]["on_interpolated_half_period"])  # 29+133+1 is even


class UncertaintyTests(unittest.TestCase):
    def test_05_uncertain_joins_flagged_not_forced(self):
        grid = grid_value(offsets={j: 25. for j in range(0, 600, 3)})
        result = run_project(grid, r=2, k=30)
        rows = result["boundaries"]
        upstream = [int(row["id"].split(":")[1]) for row in rows if "uncertain_upstream_breakdown" in row["structural_status"]]
        self.assertEqual(upstream, list(range(7, 28)))
        self.assertEqual(len(upstream), 21)
        self.assertEqual([int(r["id"].split(":")[1]) for r in rows if "breakdown_execution_uncertain" in r["structural_status"]],
                         [6, 7, 15, 16])
        self.assertEqual([int(r["id"].split(":")[1]) for r in rows if "presumed_repeat_section" in r["structural_status"]],
                         [16, 17, 18, 19, 20])
        self.assertEqual(rows[7]["upstream_uncertain_breakdown_units"], ["breakdown1:1"])
        self.assertEqual(rows[20]["upstream_uncertain_breakdown_units"], ["breakdown1:1", "breakdown2:1"])
        self.assertEqual(rows[0]["structural_status"], ["nominal"])
        for row in rows:
            self.assertEqual(len(row["structural_status"]), len(set(row["structural_status"])))
            if row["structural_status"] != ["nominal"]:
                self.assertIn(row["join_confidence"], ("uncertain", "unsupported"))
            self.assertFalse(row["moved_to_fit_observation"])
            self.assertAlmostEqual(row["source_seconds"], .2 + (30 + row["click_index"]) * .3, places=12)
        self.assertEqual(result["counts"]["structural_status"]["uncertain_upstream_breakdown"], 21)

    def test_06_grid_support_labels_from_removed_and_offset_events(self):
        # r=1, P=.6: boundary:3 at lattice 48 -> window +-4 beats = beats 44..52 (9 expected).
        base = run_project(grid_value(), r=1, k=0)["boundaries"][3]
        self.assertEqual((base["grid"]["expected_grid_beats"], base["grid"]["grid_label"]), (9, "grid_supported"))
        self.assertEqual(base["join_confidence"], "supported")
        self.assertEqual(base["confidence_kind"], "heuristic_not_probability")
        gone = run_project(grid_value(drop=range(44, 53)), r=1, k=0)["boundaries"][3]
        self.assertEqual((gone["grid"]["observed_grid_beats"], gone["grid"]["support_fraction"]), (0, 0.))
        self.assertIsNone(gone["grid"]["median_abs_grid_offset_ms"])
        self.assertEqual((gone["grid"]["grid_label"], gone["join_confidence"]), ("grid_unsupported", "unsupported"))
        half = run_project(grid_value(drop=range(44, 49)), r=1, k=0)["boundaries"][3]
        self.assertAlmostEqual(half["grid"]["support_fraction"], 4 / 9)
        self.assertEqual((half["grid"]["grid_label"], half["join_confidence"]), ("grid_weak", "weak"))
        late = run_project(grid_value(offsets={j: -40. for j in range(40, 60)}), r=1, k=0)["boundaries"][3]
        self.assertEqual(late["grid"]["support_fraction"], 1.)
        self.assertEqual(late["grid"]["median_abs_grid_offset_ms"], 40.)
        self.assertEqual(late["grid"]["grid_label"], "grid_weak")
        self.assertEqual(late["source_seconds"], base["source_seconds"])  # measured offsets never move a join

    def test_07_outside_source_units_and_boundaries_retained(self):
        result = run_project(grid_value(duration=60.), r=2, k=0)
        self.assertEqual((len(result["units"]), len(result["boundaries"])), (27, 28))
        outside = [row for row in result["boundaries"] if row["coverage"] == "outside_source"]
        self.assertTrue(outside)
        for row in outside:
            self.assertGreater(row["source_seconds"], 60.)
            self.assertIn("outside_source", row["structural_status"])
            self.assertEqual(row["join_confidence"], "unsupported")
            self.assertTrue(math.isfinite(row["source_seconds"]))
        coverage = [row["coverage"] for row in result["units"]]
        self.assertIn("partially_outside_source", coverage)
        self.assertIn("outside_source", coverage)
        self.assertEqual(result["counts"]["outside_source_boundaries"], len(outside))


class ProvenanceTests(unittest.TestCase):
    def test_08_provenance_hashes_unknowns_and_output_confinement(self):
        with Area() as area:
            path, document = spans_doc(area, k=30)
            clicks = area.inputs / "clicks.json"
            self.assertEqual(document["provenance"]["grid_sha256"], hashlib.sha256(clicks.read_bytes()).hexdigest())
            self.assertEqual(document["provenance"]["arrangement_sha256"],
                             hashlib.sha256((area.inputs / "arrangement.json").read_bytes()).hexdigest())
            self.assertEqual(document["provenance"]["worker_sha256"],
                             hashlib.sha256((ROOT / "scripts/phrase_anchor.py").read_bytes()).hexdigest())
            self.assertEqual(document["provenance"]["grid_analyzed_input_sha256"], ANALYZED)
            self.assertEqual(document["provenance"]["original_source_sha256"], SOURCE)
            self.assertEqual(document["provenance"]["clicks_per_grid_period"],
                             {"value": 2, "mapping_basis": "operator_supplied_not_inferred"})
            anchor = document["provenance"]["anchor"]
            self.assertEqual((anchor["k0"], anchor["method"], anchor["status"], anchor["adopted"]),
                             (30, "lattice_index", "review_candidate_not_confirmed_downbeat", False))
            for key, value in pa.UNKNOWNS.items():
                self.assertEqual(document[key], value)
            self.assertEqual(document["real_take_phrase_correctness"], "unknown_until_operator_marks_boundaries")
            self.assertEqual((document["tool"], document["status"]), ("phrase_anchor", "intent_projection_not_detection"))
            self.assertFalse(document["default_adoption"])
            code, _, err = area.run(["spans", "--clicks", clicks, "--arrangement", area.inputs / "arrangement.json",
                                     "--clicks-per-grid-period", 2, "--anchor-lattice-index", 30,
                                     "--anchor-source", "x", "--output", path])
            self.assertEqual((code, json.loads(err)["reason"]), (2, "output_exists"))
            code, _, err = area.run(["spans", "--clicks", clicks, "--arrangement", area.inputs / "arrangement.json",
                                     "--clicks-per-grid-period", 2, "--anchor-lattice-index", 30,
                                     "--anchor-source", "x", "--output", area.inputs / "escape.json"])
            self.assertEqual((code, json.loads(err)["reason"]), (2, "output_outside_lane_area"))
            dup = area.inputs / "dup.json"
            dup.write_text('{"schema_version": 1, "schema_version": 1}')
            code, _, err = area.run(["spans", "--clicks", dup, "--arrangement", area.inputs / "arrangement.json",
                                     "--clicks-per-grid-period", 2, "--anchor-lattice-index", 30,
                                     "--anchor-source", "x", "--output", area.area / "dup-out.json"])
            self.assertEqual((code, json.loads(err)["reason"]), (2, "duplicate_json_key"))
            item = pa.Input(clicks)
            clicks.write_text(json.dumps(grid_value(offset_ms=3.)))
            with self.assertRaisesRegex(pa.DomainError, "input_changed_after_read"):
                pa.recheck([item])

    def test_08b_anchor_evidence_binding_and_operator_mark(self):
        with Area() as area:
            grid = pa.parse_grid(grid_value())
            t30 = .2 + 30 * .3
            candidates = pa.Input(area.put("cand.json", {"source_sha256": SOURCE, "analyzed_input_sha256": "11" * 32,
                                                         "first_phrase_candidates": [{"candidate_source_seconds": t30 - .02,
                                                                                      "status": "review_candidate_not_confirmed_downbeat"}]}))
            result = pa.project(grid, ARRANGEMENT, 2, anchor_seconds=t30 - .02, evidence=candidates)
            self.assertEqual(result["anchor"]["status"], "review_candidate_not_confirmed_downbeat")
            self.assertEqual(result["anchor"]["evidence_analyzed_input_sha256"], "11" * 32)
            self.assertAlmostEqual(result["anchor"]["matched_evidence_candidate"]["candidate_source_seconds"], t30 - .02)
            marks = pa.Input(area.put("op.json", {"schema_version": "phrase-boundaries-v1", "source_sha256": SOURCE,
                                                  "marks": [{"source_seconds": t30, "author": "operator",
                                                             "basis": "operator_assertion", "note": "first phrase"}]}))
            marked = pa.project(grid, ARRANGEMENT, 2, lattice_index=30, evidence=marks)
            self.assertEqual(marked["anchor"]["status"], pa.ANCHOR_OPERATOR)
            wrong = pa.Input(area.put("wrong.json", {"source_sha256": "99" * 32}))
            with self.assertRaisesRegex(pa.DomainError, "anchor_evidence_source_mismatch"):
                pa.project(grid, ARRANGEMENT, 2, lattice_index=30, evidence=wrong)
            other = copy.deepcopy(ARRANGEMENT)
            other["source_sha256"] = "98" * 32
            with self.assertRaisesRegex(pa.DomainError, "arrangement_source_mismatch"):
                pa.project(grid, other, 2, lattice_index=30)


class ScorerTests(unittest.TestCase):
    def score(self, area, spans_path, marks, fmt="boundaries"):
        marks_path = area.put(f"marks-{uuid.uuid4().hex}.json", marks)
        out = area.area / f"score-{uuid.uuid4().hex}.json"
        flag = "--boundaries" if fmt == "boundaries" else "--annotation-store"
        code, _, err = area.run(["score", "--spans", spans_path, flag, marks_path, "--output", out])
        self.assertEqual(code, 0, err)
        return json.loads(out.read_text())

    def test_09_null_below_ten_marks_excluding_detector_and_dismissed(self):
        with Area() as area:
            spans_path, document = spans_doc(area, k=30)
            times = [row["source_seconds"] for row in document["boundaries"]]
            items = [annotation(t) for t in times[:9]]
            items += [annotation(times[9], actor="detector", basis="detector_hypothesis"),
                      annotation(times[10], status="dismissed_candidate"),
                      annotation(times[11], kind="rhythm_timing"),
                      annotation(times[12], actor="agent", basis="reference_comparison")]
            items[-1]["reference_sha256"] = "ab" * 32
            result = self.score(area, spans_path, store(items), "annotation_store")
            self.assertIsNone(result["result"])
            self.assertEqual((result["reason"], result["accepted_mark_count"], result["required"]),
                             ("insufficient_operator_boundaries", 9, 10))
            self.assertEqual(result["excluded_mark_counts"],
                             {"non_operator_actor": 2, "dismissed_candidate": 1, "kind_not_phrase_duration": 1})
            self.assertEqual(result["real_take_phrase_correctness"], "unknown_until_operator_marks_boundaries")
            self.assertFalse(result["detector_hypotheses_counted"])
            lane = {"schema_version": "phrase-boundaries-v1", "source_sha256": SOURCE,
                    "marks": [{"source_seconds": t, "author": "operator" if i < 9 else "agent", "basis": "operator_assertion",
                               "note": "n"} for i, t in enumerate(times[:14])]}
            result = self.score(area, spans_path, lane)
            self.assertEqual((result["result"], result["accepted_mark_count"]), (None, 9))
            self.assertEqual(result["excluded_mark_counts"], {"non_operator_author": 5})
            # A span with known extent contributes both endpoints.
            spanned = [annotation(times[i], times[i + 1], basis="operator_context") for i in range(0, 10, 2)]
            result = self.score(area, spans_path, store(spanned), "annotation_store")
            self.assertEqual(result["accepted_mark_count"], 10)
            self.assertIsNotNone(result["result"])

    def test_10_hits_at_100ms_and_one_click_one_to_one_with_mae_denominator(self):
        with Area() as area:
            spans_path, document = spans_doc(area, k=30)
            times = [row["source_seconds"] for row in document["boundaries"]]
            offsets = [.0, .05, -.08, .02, .15, -.2, .29, .04, -.03, .06]
            marks = [{"source_seconds": times[i] + d, "author": "operator", "basis": "operator_assertion", "note": "n"}
                     for i, d in enumerate(offsets)]
            marks.append({"source_seconds": times[0] + .01, "author": "operator", "basis": "operator_assertion", "note": "dup"})
            marks.append({"source_seconds": times[-1] + 5., "author": "operator", "basis": "operator_assertion", "note": "far"})
            result = self.score(area, spans_path, {"schema_version": "phrase-boundaries-v1", "source_sha256": SOURCE,
                                                   "marks": marks})
            self.assertEqual(result["accepted_mark_count"], 12)
            ms = result["result"]["hits_at_100ms"]
            self.assertEqual(ms["hits"], 7)  # offsets within .1, boundary:0 used once
            self.assertEqual(ms["accepted_marks"], 12)
            self.assertEqual(ms["mae_denominator"], 7)
            within = [abs(d) for d in offsets if abs(d) <= .1]
            self.assertAlmostEqual(ms["mae_seconds"], sum(within) / len(within), places=9)
            self.assertEqual(len({row["boundary_id"] for row in ms["matches"]}), ms["hits"])
            self.assertEqual(ms["unmatched_predicted_boundaries_role"], "not_reviewed_not_false_positive")
            self.assertEqual(len(ms["not_reviewed_boundary_ids"]), 28 - 7)
            click = result["result"]["hits_at_one_click"]
            self.assertAlmostEqual(click["tolerance_seconds"], .3)
            self.assertEqual(click["hits"], 10)  # .15/.2/.29 within one .3 s click; duplicate still unmatched
            for row in click["matches"]:
                self.assertAlmostEqual(row["signed_offset_seconds"], row["predicted_source_seconds"] - row["mark_source_seconds"])
                self.assertIn("structural_status", row)
            self.assertEqual(result["result"]["marks_outside_predicted_extent"], [11])
            self.assertIsNone(result["precision"])
            for diagnostic in result["result"]["post_hoc_breakdown_hypothesis_diagnostics"]:
                self.assertFalse(diagnostic["selected"])

    def test_11_source_binding_mismatch_and_no_stretch_derivative(self):
        with Area() as area:
            spans_path, document = spans_doc(area, k=30)
            times = [row["source_seconds"] for row in document["boundaries"]][:12]
            marks = [{"source_seconds": t, "author": "operator", "basis": "operator_assertion", "note": "n"} for t in times]
            wrong = self.score(area, spans_path, {"schema_version": "phrase-boundaries-v1", "source_sha256": "77" * 32,
                                                  "marks": marks})
            self.assertEqual((wrong["result"], wrong["reason"], wrong["source_binding"]), (None, "source_binding_mismatch", None))
            derived = self.score(area, spans_path, {"schema_version": "phrase-boundaries-v1", "source_sha256": ANALYZED,
                                                    "marks": marks})
            self.assertEqual(derived["source_binding"], "run_derivative_no_stretch_timeline")
            self.assertEqual(derived["result"]["hits_at_100ms"]["hits"], 12)
            stretched = grid_value()
            stretched["source_lineage"]["sample_mapping"]["no_time_stretch"] = False
            spans2, _ = spans_doc(area, grid=stretched, k=30, name="spans2.json")
            refused = self.score(area, spans2, {"schema_version": "phrase-boundaries-v1", "source_sha256": ANALYZED,
                                                "marks": marks})
            self.assertEqual(refused["reason"], "source_binding_mismatch")
            store_wrong = self.score(area, spans_path, store([annotation(t) for t in times], source="66" * 32), "annotation_store")
            self.assertEqual(store_wrong["reason"], "source_binding_mismatch")

    def test_12_breakdown_shift_hypotheses_not_adopted(self):
        result = run_project(r=2, k=30)
        hypotheses = result["hypotheses"]
        self.assertEqual([(h["breakdown_unit_id"], h["shift_clicks"]) for h in hypotheses],
                         [(u, s) for u in ("breakdown1:1", "breakdown2:1") for s in (-2, -1, 1, 2)])
        positions = expected_positions()
        for h in hypotheses:
            self.assertEqual(h["status"], "hypothesis_not_adopted")
            start = 7 if h["breakdown_unit_id"] == "breakdown1:1" else 16
            self.assertEqual([row["id"] for row in h["downstream_boundaries"]], [f"boundary:{b}" for b in range(start, 28)])
            for row, b in zip(h["downstream_boundaries"], range(start, 28)):
                self.assertEqual(row["click_index"], positions[b] + h["shift_clicks"])
                self.assertAlmostEqual(row["source_seconds"], .2 + (30 + positions[b] + h["shift_clicks"]) * .3, places=12)
        self.assertEqual(hypotheses[0]["basis"], "operator_reported_possible_rush_or_skip")
        self.assertEqual(hypotheses[0]["hypothesized_breakdown_clicks"], 6)
        for row, c in zip(result["boundaries"], positions):  # primary expansion keeps the intended eight clicks
            self.assertAlmostEqual(row["source_seconds"], .2 + (30 + c) * .3, places=12)


@unittest.skipUnless(REAL_GRID.is_file(), "real-take grid artifact is local-only and absent in CI")
class RealGridReadOnlyTests(unittest.TestCase):
    def test_real_grid_three_cached_candidates_map_to_lattice_29_30_31(self):
        grid_input = pa.Input(REAL_GRID)
        if grid_input.sha256 != REAL_GRID_SHA:
            self.skipTest("real-take grid changed from the frozen hash")
        grid = pa.parse_grid(grid_input.value)
        for seconds, k in ((10.2775, 29), (10.6275, 30), (10.9775, 31)):
            result = pa.project(grid, ARRANGEMENT, 2, anchor_seconds=seconds)
            self.assertEqual(result["anchor"]["k0"], k)
            self.assertEqual(len(result["boundaries"]), 28)
            self.assertEqual(result["anchor"]["status"], "review_candidate_not_confirmed_downbeat")


if __name__ == "__main__":
    unittest.main()
