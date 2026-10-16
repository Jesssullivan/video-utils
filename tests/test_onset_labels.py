"""Operator onset labels (D6, TIN-5491): store kinds, label import, one-to-one scorer, report table.

Synthetic data only. Detections are never moved toward labels; every property
below checks the scorer against an independently known construction.
"""
import contextlib
import hashlib
import importlib.util
import io
import itertools
import json
import os
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))
import annotation_v2 as annotations  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


review = load("review_server_onset_tests", SCRIPTS / "review_server.py")
benchmark = load("onset_benchmark_tests", SCRIPTS / "onset_benchmark.py")
event_benchmark = load("benchmark_event_tests", SCRIPTS / "benchmark.py")
TOLERANCES = (.010, .025, .050)
RSCRIPT = shutil.which("Rscript")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def onset(seconds, certainty="uncertain", status="needs_review", actor="operator", basis="operator_assertion"):
    return {"kind": "onset", "basis": basis, "status": status,
            "source_span": {"start_seconds": seconds, "end_seconds": seconds, "extent_known": False},
            "reported_by": {"actor": actor, "via": "cli"},
            "operator_certainty": certainty if basis == "operator_assertion" else None,
            "operator_quote": "onset" if basis == "operator_assertion" else None, "note": "synthetic"}


def segment(start, end):
    return {"kind": "onset_segment", "basis": "operator_assertion", "status": "accepted_observation",
            "source_span": {"start_seconds": start, "end_seconds": end, "extent_known": True},
            "reported_by": {"actor": "operator", "via": "cli"}, "operator_certainty": "confirmed",
            "operator_quote": "every onset in this span is marked", "note": "synthetic"}


def store_of(*items):
    return {"annotations": list(items)}


def analysis_of(times, kind="broadband_attack_candidate", compensated=None):
    events = [{"kind": kind, "source_timeline_seconds": value,
               "delay_compensated_source_timeline_seconds": None if compensated is None else value - compensated}
              for value in times]
    events.append({"kind": "periodic_high_frequency_candidate", "source_timeline_seconds": 0.5,
                   "delay_compensated_source_timeline_seconds": None})
    return {"events": events}


def separated_times(rng, count, start=1.0, gap=(0.15, 0.4)):
    """Onset times far enough apart (>= 150 ms) that 50 ms windows never overlap."""
    times, current = [], start
    for _ in range(count):
        current += rng.uniform(*gap)
        times.append(round(current, 6))
    return times


def brute_force(first, second, tolerance, priority=None):
    """Maximum prioritised count, then maximum count, then minimum total offset, over all matchings."""
    weight = priority or [False] * len(first)
    best = (0, 0, 0.0)
    edges = [(i, j) for i in range(len(first)) for j in range(len(second)) if abs(first[i] - second[j]) <= tolerance]
    for size in range(len(edges), 0, -1):
        for chosen in itertools.combinations(edges, size):
            if len({i for i, _ in chosen}) < size or len({j for _, j in chosen}) < size:
                continue
            preferred = sum(weight[i] for i, _ in chosen)
            cost = sum(abs(first[i] - second[j]) for i, j in chosen)
            if (preferred, size) > best[:2] or ((preferred, size) == best[:2] and cost < best[2] - 1e-12):
                best = (preferred, size, cost)
    return best


class OnsetKindValidationTests(unittest.TestCase):
    def check(self, item):
        return annotations.validate_annotation(item, source_min_seconds=0, source_max_seconds=100)

    def refused(self, item, code):
        with self.assertRaises(annotations.AnnotationError) as caught:
            self.check(item)
        self.assertEqual(caught.exception.code, code)

    def test_onset_kinds_are_new_and_issue_kinds_unchanged(self):
        self.assertEqual(annotations.KINDS - annotations.ISSUE_KINDS, {"onset", "onset_segment"})
        self.assertEqual(len(annotations.ISSUE_KINDS), 11)
        self.assertIn("onset", annotations.request_schema()["properties"]["annotation"]["properties"]["kind"]["enum"])

    def test_onset_point_and_segment_span_accepted_for_operator_bases(self):
        self.check(onset(3.5))
        self.check(onset(3.5, basis="operator_context"))
        self.check(segment(2, 4))

    def test_onset_extent_rules(self):
        item = onset(3.5)
        item["source_span"] = {"start_seconds": 3.5, "end_seconds": 3.6, "extent_known": True}
        self.refused(item, "onset_label_requires_point_timestamp")
        item = segment(4, 4)
        item["source_span"]["extent_known"] = False
        self.refused(item, "onset_segment_requires_known_span")
        self.refused(segment(4, 4), "onset_segment_requires_known_span")

    def test_detector_or_reference_cannot_author_an_onset_label(self):
        item = onset(3.5, actor="detector", basis="detector_hypothesis")
        self.refused(item, "onset_label_requires_operator_basis")
        item = onset(3.5, actor="agent", basis="reference_comparison")
        item["reference_sha256"] = "c" * 64
        self.refused(item, "onset_label_requires_operator_basis")


class LabelImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        with wave.open(str(self.root / "source.wav"), "wb") as stream:
            stream.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
            stream.writeframes(struct.pack("<h", 0) * 8000 * 12)
        self.manifest = {"source": {"sha256": "a" * 64}, "output_sha256": {"source.wav": sha((self.root / "source.wav").read_bytes())},
                         "timeline": {"audio_start_seconds": 0.25, "format_start_seconds": 0, "no_time_stretch": True},
                         "pcm": {"duration_seconds": 12}}
        (self.root / "manifest.json").write_text(json.dumps(self.manifest))
        self.session = review.Session(self.root, open_media=False)
        self.addCleanup(self.session.close)
        self.store = annotations.AnnotationStore(self.session)
        self.labels = self.root / "labels.txt"

    def write_labels(self, text):
        self.labels.write_text(text)

    def test_points_and_region_import_on_source_clock_and_replay(self):
        self.write_labels("1.000000\t1.000000\tpick\n\n\\\t100.0\t2000.0\n2.500000\t2.500000\t\n3.0\t8.0\tall onsets\n")
        result = annotations.import_labels(self.store, self.labels, "source.wav", quote="onset")
        self.assertEqual((result["saved"], result["replayed"], result["ignored_frequency_rows"]), (3, 0, 1))
        self.assertEqual(result["by_kind"], {"onset": 2, "onset_segment": 1})
        saved = self.store.read()["annotations"]
        spans = [(item["kind"], item["source_span"]["start_seconds"], item["source_span"]["end_seconds"]) for item in saved]
        self.assertEqual(spans, [("onset", 1.25, 1.25), ("onset", 2.75, 2.75), ("onset_segment", 3.25, 8.25)])
        self.assertEqual([item["operator_quote"] for item in saved], ["pick", "onset", "all onsets"])
        self.assertTrue(all(item["reported_by"] == {"actor": "operator", "via": "cli"} for item in saved))
        self.assertTrue(all(item["musical_verdict"] == "not_established" for item in saved))
        again = annotations.import_labels(self.store, self.labels, "source.wav", quote="onset")
        self.assertEqual((again["saved"], again["replayed"], again["count"]), (0, 3, 3))

    def test_boundary_points_import_as_phrase_duration(self):
        self.write_labels("1.0\t1.0\tboundary\n2.0\t2.0\tboundary\n")
        result = annotations.import_labels(self.store, self.labels, "source.wav", point_kind="phrase_duration")
        self.assertEqual(result["by_kind"], {"phrase_duration": 2})
        self.write_labels("1.0\t2.0\tregion\n")
        with self.assertRaises(annotations.AnnotationError) as caught:
            annotations.import_labels(self.store, self.labels, "source.wav", point_kind="phrase_duration")
        self.assertEqual(caught.exception.code, "region_label_only_declares_an_onset_segment")

    def test_refusals_happen_before_any_write(self):
        cases = [("1.0\t1.0\t\n", {}, "label_text_or_quote_required"),
                 ("1.0\t0.5\tx\n", {}, "label_row_time_invalid"),
                 ("nan\tnan\tx\n", {}, "label_row_time_invalid"),
                 ("1.0\n", {}, "label_row_requires_start_and_end"),
                 ("1.0\t1.0\tok\n20.0\t20.0\tpast end\n", {}, "source_span_out_of_bounds"),
                 ("\n\n", {}, "label_file_has_no_labels")]
        for text, options, code in cases:
            with self.subTest(code=code):
                self.write_labels(text)
                with self.assertRaises(annotations.AnnotationError) as caught:
                    annotations.import_labels(self.store, self.labels, "source.wav", **options)
                self.assertEqual(caught.exception.code, code)
                self.assertFalse(self.store.path.exists())
        self.write_labels("".join(f"{1 + index * 0.01:.2f}\t{1 + index * 0.01:.2f}\tx\n" for index in range(201)))
        with self.assertRaises(annotations.AnnotationError) as caught:
            annotations.import_labels(self.store, self.labels, "source.wav")
        self.assertEqual(caught.exception.code, "annotation_limit_reached")

    def test_labelled_audio_must_be_the_run_bound_file(self):
        self.write_labels("1.0\t1.0\tx\n")
        with self.assertRaises(annotations.AnnotationError) as caught:
            annotations.import_labels(self.store, self.labels, "denoised.wav")
        self.assertEqual(caught.exception.code, "labelled_audio_not_run_bound")
        data = bytearray((self.root / "source.wav").read_bytes())
        data[-1] ^= 1
        (self.root / "source.wav").write_bytes(bytes(data))
        with self.assertRaises(annotations.AnnotationError) as caught:
            annotations.import_labels(self.store, self.labels, "source.wav")
        self.assertEqual(caught.exception.code, "labelled_audio_not_run_bound")
        self.assertFalse(self.store.path.exists())

    def test_labelled_audio_requires_a_no_time_stretch_timeline(self):
        self.write_labels("1.0\t1.0\tx\n")
        for timeline in ({"audio_start_seconds": 0.25, "format_start_seconds": 0},
                         {"audio_start_seconds": 0.25, "format_start_seconds": 0, "no_time_stretch": False}):
            with self.subTest(timeline=timeline):
                (self.root / "manifest.json").write_text(json.dumps({**self.manifest, "timeline": timeline}))
                session = review.Session(self.root, open_media=False)
                self.addCleanup(session.close)
                with self.assertRaises(annotations.AnnotationError) as caught:
                    annotations.import_labels(annotations.AnnotationStore(session), self.labels, "source.wav")
                self.assertEqual(caught.exception.code, "labelled_audio_requires_no_time_stretch_timeline")
                self.assertFalse(self.store.path.exists())

    def test_cli_import_and_argument_contract(self):
        self.write_labels("1.0\t1.0\tx\n")
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            code = annotations.main(["import-labels", str(self.root), "--labels", str(self.labels), "--audio", "source.wav"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stream.getvalue())["saved"], 1)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            annotations.main(["import-labels", str(self.root), "--labels", str(self.labels)])


class OnsetScorerTests(unittest.TestCase):
    def test_ordered_matching_equals_brute_force_optimum(self):
        rng = random.Random(5491)
        for _ in range(150):
            first = sorted(round(rng.uniform(0, 0.3), 4) for _ in range(rng.randint(0, 5)))
            second = sorted(round(rng.uniform(0, 0.3), 4) for _ in range(rng.randint(0, 5)))
            tolerance = rng.choice(TOLERANCES)
            pairs = benchmark.ordered_pairs(first, second, tolerance)
            self.assertEqual(len({i for i, _ in pairs}), len(pairs))
            self.assertEqual(len({j for _, j in pairs}), len(pairs))
            self.assertTrue(all(abs(first[i] - second[j]) <= tolerance for i, j in pairs))
            _, count, cost = brute_force(first, second, tolerance)
            self.assertEqual(len(pairs), count)
            self.assertAlmostEqual(sum(abs(first[i] - second[j]) for i, j in pairs), cost, places=9)

    def test_prioritised_matching_equals_brute_force_optimum(self):
        rng = random.Random(5492)
        for _ in range(150):
            first = sorted(round(rng.uniform(0, 0.3), 4) for _ in range(rng.randint(0, 5)))
            second = sorted(round(rng.uniform(0, 0.3), 4) for _ in range(rng.randint(0, 5)))
            priority = [rng.random() < 0.5 for _ in first]
            tolerance = rng.choice(TOLERANCES)
            pairs = benchmark.ordered_pairs(first, second, tolerance, priority=priority)
            self.assertEqual(len({i for i, _ in pairs}), len(pairs))
            self.assertEqual(len({j for _, j in pairs}), len(pairs))
            preferred, count, cost = brute_force(first, second, tolerance, priority)
            self.assertEqual((sum(priority[i] for i, _ in pairs), len(pairs)), (preferred, count))
            self.assertAlmostEqual(sum(abs(first[i] - second[j]) for i, j in pairs), cost, places=9)

    def test_matcher_agrees_with_frozen_event_metrics_v2(self):
        rng = random.Random(6)
        for _ in range(100):
            first = sorted(rng.uniform(0, 2) for _ in range(rng.randint(0, 30)))
            second = sorted(rng.uniform(0, 2) for _ in range(rng.randint(0, 30)))
            tolerance = rng.choice(TOLERANCES)
            frozen = event_benchmark.event_metrics_v2(first, second, tolerance)
            pairs = benchmark.ordered_pairs(first, second, tolerance)
            self.assertEqual(frozen["matched_count"], len(pairs))
            self.assertEqual(frozen["signed_offsets_seconds"], [second[j] - first[i] for i, j in pairs])

    def test_timing_jitter_matches_exactly_the_labels_within_tolerance(self):
        rng = random.Random(10)
        for _ in range(40):
            labels = separated_times(rng, rng.randint(10, 60))
            jitter = [rng.uniform(-0.06, 0.06) for _ in labels]
            detections = [label + offset for label, offset in zip(labels, jitter)]
            previous = -1
            for tolerance in TOLERANCES:
                result = benchmark.onset_agreement(labels, detections, tolerance)
                expected = sum(abs(offset) <= tolerance for offset in jitter)
                self.assertEqual(result["matched_count"], expected)
                self.assertAlmostEqual(result["recall"], expected / len(labels))
                self.assertGreaterEqual(result["matched_count"], previous)
                previous = result["matched_count"]
                self.assertIsNone(result["precision"])
                self.assertEqual(result["precision_reason"], "no_operator_declared_fully_labelled_segment")

    def test_constant_detector_lag_is_reported_not_corrected(self):
        labels = separated_times(random.Random(3), 20)
        result = benchmark.onset_agreement(labels, [value + 0.018 for value in labels], .025)
        self.assertAlmostEqual(result["median_signed_offset_seconds"], 0.018, places=9)
        self.assertEqual(benchmark.onset_agreement(labels, [value + 0.018 for value in labels], .010)["matched_count"], 0)

    def test_missing_and_extra_detections_inside_a_declared_segment(self):
        rng = random.Random(77)
        for _ in range(40):
            labels = separated_times(rng, rng.randint(12, 40))
            segments = [[labels[0] - 0.05, labels[-1] + 0.05]]
            missing = set(rng.sample(range(len(labels)), rng.randint(0, 5)))
            detections = [value + rng.uniform(-0.008, 0.008) for index, value in enumerate(labels) if index not in missing]
            gaps = [(a + b) / 2 for a, b in zip(labels, labels[1:]) if b - a > 0.2]
            extra = rng.sample(gaps, min(len(gaps), rng.randint(0, 4)))
            outside = [segments[0][1] + 1.0, segments[0][0] - 1.0]
            for tolerance in TOLERANCES:
                result = benchmark.onset_agreement(labels, detections + extra + outside, tolerance, segments)
                matched = len(labels) - len(missing)
                self.assertEqual(result["matched_count"], matched)
                self.assertEqual(result["missed_label_count"], len(missing))
                self.assertEqual(result["false_positive_count"], len(extra))
                self.assertAlmostEqual(result["precision"], matched / (matched + len(extra)))
                self.assertAlmostEqual(result["recall"], matched / len(labels))

    def test_ambiguous_close_labels_share_one_detection_one_to_one(self):
        labels = [1.000, 1.015]
        result = benchmark.onset_agreement(labels, [1.007], .025, [[0.9, 1.1]])
        self.assertEqual((result["matched_count"], result["missed_label_count"], result["false_positive_count"]), (1, 1, 0))
        self.assertEqual((result["contested_detection_count"], result["contested_label_count"]), (1, 0))
        result = benchmark.onset_agreement([1.0], [0.99, 1.012], .025, [[0.9, 1.1]])
        self.assertEqual((result["matched_count"], result["false_positive_count"], result["contested_label_count"]), (1, 1, 1))
        self.assertAlmostEqual(result["signed_offsets_seconds"][0], -0.01)

    def test_labels_outside_segments_are_not_scored_and_partial_coverage(self):
        labels = [1.0, 2.0, 3.0, 9.0]
        result = benchmark.onset_agreement(labels, [1.0, 2.0, 3.0, 9.0, 9.5], .01, [[0.5, 3.5]])
        self.assertEqual((result["operator_label_count"], result["matched_count"], result["false_positive_count"]), (3, 3, 0))
        self.assertEqual(result["detections_in_scope"], 3)

    def test_segment_edge_detection_matched_to_outside_label_is_not_a_false_positive(self):
        # A hand-drawn region starts 5 ms after the first heard attack; its detection lands inside.
        result = benchmark.onset_agreement([1.995, 2.5], [2.004, 2.5], .025, [[2.0, 3.0]])
        self.assertEqual((result["operator_label_count"], result["matched_count"], result["false_positive_count"]), (1, 1, 0))
        self.assertEqual((result["precision"], result["recall"], result["f1"]), (1.0, 1.0, 1.0))
        self.assertEqual(result["detections_in_scope_matched_to_unscored_labels"], 1)
        self.assertEqual(result["unscored_operator_label_count"], 1)
        # Symmetric case: a detection just outside the edge still matches a label inside it.
        result = benchmark.onset_agreement([2.004, 2.5], [1.995, 2.5], .025, [[2.0, 3.0]])
        self.assertEqual((result["operator_label_count"], result["matched_count"], result["false_positive_count"]), (2, 2, 0))
        self.assertEqual(result["detections_in_scope"], 1)
        # An in-segment detection near no label at all is still a false positive.
        result = benchmark.onset_agreement([1.995, 2.5], [2.004, 2.5, 2.75], .025, [[2.0, 3.0]])
        self.assertEqual((result["matched_count"], result["false_positive_count"]), (1, 1))
        self.assertAlmostEqual(result["precision"], 0.5)

    def test_contested_edge_detection_prefers_the_scored_label(self):
        # One detection between a label outside the segment and one inside it, equally far.
        result = benchmark.onset_agreement([1.99, 2.01], [2.0], .025, [[2.0, 3.0]])
        self.assertEqual((result["operator_label_count"], result["matched_count"], result["missed_label_count"]), (1, 1, 0))
        self.assertEqual((result["false_positive_count"], result["contested_detection_count"]), (0, 1))

    def test_edge_jitter_property_with_tight_hand_drawn_segments(self):
        rng = random.Random(91)
        for _ in range(60):
            labels = separated_times(rng, rng.randint(14, 40))
            inner = labels[2:-2]
            # Region edges dragged a few ms after the first and before the last scored attack.
            segments = [[inner[0] - rng.uniform(-0.004, 0.004), inner[-1] + rng.uniform(-0.004, 0.004)]]
            scored = [value for value in labels if segments[0][0] <= value <= segments[0][1]]
            detections = [value + rng.uniform(-0.009, 0.009) for value in labels]
            for tolerance in TOLERANCES:
                result = benchmark.onset_agreement(labels, detections, tolerance, segments)
                self.assertEqual(result["operator_label_count"], len(scored))
                self.assertEqual((result["matched_count"], result["false_positive_count"]), (len(scored), 0))
                self.assertEqual(result["precision"], 1.0)

    def test_offset_of_exactly_the_tolerance_matches_after_label_rounding(self):
        labels = [round(value, 6) for value in separated_times(random.Random(12), 12)]
        for tolerance in TOLERANCES:
            detections = [round(value + tolerance, 6) for value in labels]
            result = benchmark.onset_agreement(labels, detections, tolerance)
            self.assertEqual(result["recall"], 1.0, tolerance)
            late = benchmark.onset_agreement(labels, [round(value + tolerance + 0.000002, 6) for value in labels], tolerance)
            self.assertEqual(late["matched_count"], 0)

    def test_confirmed_only_matches_against_unconfirmed_labels_too(self):
        times = [1.0 + index * 0.3 for index in range(24)]
        items = [onset(value, certainty="confirmed" if index % 2 else "uncertain") for index, value in enumerate(times)]
        document = benchmark.onset_label_benchmark(store_of(segment(0.9, 9.0), *items), analysis_of(times))
        confirmed = document["detectors"][0]["subsets"]["confirmed_only"]["by_tolerance"][0]
        self.assertEqual((confirmed["operator_label_count"], confirmed["matched_count"]), (12, 12))
        self.assertEqual((confirmed["false_positive_count"], confirmed["precision"]), (0, 1.0))
        self.assertEqual(confirmed["detections_in_scope_matched_to_unscored_labels"], 12)

    def benchmark_for(self, items, analysis):
        return benchmark.onset_label_benchmark(store_of(*items), analysis)

    def test_empty_store_reports_no_labels_and_no_rates(self):
        document = self.benchmark_for([], analysis_of([1.0, 2.0]))
        self.assertEqual(document["status"], "no_operator_onset_labels")
        self.assertEqual(benchmark.onset_benchmark_rows(document), [])
        self.assertEqual(document["claims"]["note_correctness"], "not_assessed_no_approved_reference")
        self.assertEqual(document["detectors"][0]["subsets"]["all_operator_labels"]["by_tolerance"], None)

    def test_fewer_than_ten_labels_abstains(self):
        document = self.benchmark_for([onset(1.0 + index) for index in range(9)], analysis_of([1.0, 2.0]))
        self.assertEqual(document["status"], "insufficient_operator_onset_labels")
        self.assertEqual(benchmark.onset_benchmark_rows(document), [])

    def test_authorship_status_and_kind_filters_are_counted(self):
        items = [onset(1.0 + index * 0.3, certainty="confirmed" if index % 2 else "uncertain") for index in range(12)]
        items += [onset(9.0, status="dismissed_candidate"), onset(9.5, basis="operator_context"),
                  {**onset(9.7), "kind": "rhythm_timing"}]
        detector = onset(9.9, actor="detector", basis="detector_hypothesis")
        items.append(detector)
        document = self.benchmark_for(items, analysis_of([1.0 + index * 0.3 for index in range(12)]))
        labels = document["operator_labels"]
        self.assertEqual(labels["count"], 13)
        self.assertEqual(labels["excluded"], {"dismissed_candidate": 1, "non_operator_actor": 1})
        self.assertEqual(labels["by_certainty"], {"confirmed": 6, "not_applicable": 1, "uncertain": 6})
        self.assertEqual(document["status"], "measured_operator_label_agreement")
        detector_row = document["detectors"][0]
        self.assertEqual(detector_row["kind"], "broadband_attack_candidate")
        self.assertEqual(detector_row["subsets"]["confirmed_only"]["status"], "insufficient_operator_onset_labels")
        measured = detector_row["subsets"]["all_operator_labels"]["by_tolerance"]
        self.assertEqual([row["tolerance_seconds"] for row in measured], list(TOLERANCES))
        self.assertEqual(measured[0]["matched_count"], 12)

    def test_detector_kinds_and_axes_stay_separate_and_clicks_excluded(self):
        labels = [onset(1.0 + index * 0.3) for index in range(10)]
        times = [1.0 + index * 0.3 for index in range(10)]
        analysis = analysis_of(times, compensated=0.02)
        analysis["events"] += [{"kind": "superflux_attack_candidate", "source_timeline_seconds": value + 0.03,
                                "delay_compensated_source_timeline_seconds": None} for value in times]
        document = benchmark.onset_label_benchmark(store_of(segment(0.9, 4.0), *labels), analysis)
        keys = [(row["kind"], row["time_axis"]) for row in document["detectors"]]
        self.assertEqual(keys, [("broadband_attack_candidate", "uncompensated"),
                                ("broadband_attack_candidate", "synthetic_probe_delay_compensated"),
                                ("superflux_attack_candidate", "uncompensated")])
        rows = benchmark.onset_benchmark_rows(document)
        recall = {(row["detector_kind"], row["time_axis"], row["tolerance_ms"]): row["recall"]
                  for row in rows if row["label_subset"] == "all_operator_labels"}
        self.assertEqual(recall[("broadband_attack_candidate", "uncompensated", 10)], 1.0)
        self.assertEqual(recall[("broadband_attack_candidate", "synthetic_probe_delay_compensated", 10)], 0.0)
        self.assertEqual(recall[("superflux_attack_candidate", "uncompensated", 25)], 0.0)
        self.assertEqual(recall[("superflux_attack_candidate", "uncompensated", 50)], 1.0)
        self.assertEqual(document["scoring_mode"], "declared_segments_precision_and_recall")
        self.assertEqual(document["declared_segment_total_seconds"], 3.1)

    def test_missing_source_time_abstains_for_that_detector(self):
        analysis = {"events": [{"kind": "broadband_attack_candidate", "audio_relative_seconds": 1.0}]}
        document = self.benchmark_for([onset(1.0 + index) for index in range(10)], analysis)
        self.assertEqual(document["detectors"][0]["status"], "source_time_missing")
        self.assertEqual(document["status"], "no_detector_onsets")

    def test_overlapping_segments_merge(self):
        labels, segments, _ = benchmark.onset_operator_labels(store_of(segment(1, 3), segment(2, 4), segment(6, 7)))
        self.assertEqual((labels, segments), ([], [[1.0, 4.0], [6.0, 7.0]]))


class OnsetReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "run-onsets"
        self.root.mkdir()
        manifest = {"run_id": "synthetic-onset-run", "source": {"sha256": "a" * 64},
                    "timeline": {"audio_start_seconds": 0, "format_start_seconds": 0}, "pcm": {"duration_seconds": 30}}
        (self.root / "manifest.json").write_text(json.dumps(manifest))
        session = review.Session(self.root, open_media=False)
        self.addCleanup(session.close)
        store = annotations.AnnotationStore(session)
        self.times = [2.0 + index * 0.25 for index in range(12)]
        for index, value in enumerate([*self.times, None]):
            item = onset(value) if value is not None else segment(1.5, 5.5)
            store.write({"schema_version": 2, "expected_revision": index, "idempotency_key": f"receipt-key-{index:04d}",
                         "source_sha256": session.source_hash, "manifest_sha256": session.manifest_hash,
                         "annotation": item})

    def write_analysis(self, source_sha):
        events = [{"kind": "broadband_attack_candidate", "source_timeline_seconds": value + 0.004,
                   "delay_compensated_source_timeline_seconds": None} for value in self.times]
        events.append({"kind": "broadband_attack_candidate", "source_timeline_seconds": 3.125,
                       "delay_compensated_source_timeline_seconds": None})
        (self.root / "analysis.json").write_text(json.dumps({"source": {"sha256": source_sha}, "events": events}))

    def test_bound_receipt_scores_and_carries_no_paths(self):
        self.write_analysis("a" * 64)
        receipt = benchmark.onset_labels_receipt(self.root)
        self.assertEqual(receipt["status"], "measured_operator_label_agreement")
        self.assertEqual(receipt["inputs"]["analysis"]["status"], "original_source_hash_bound")
        self.assertEqual(receipt["inputs"]["annotation_store"]["revision"], 13)
        rows = benchmark.onset_benchmark_rows(receipt)
        ten = next(row for row in rows if row["tolerance_ms"] == 10 and row["label_subset"] == "all_operator_labels")
        self.assertEqual((ten["matched"], ten["false_positives"]), (12, 1))
        self.assertAlmostEqual(ten["precision"], 12 / 13, places=4)
        self.assertNotIn(str(self.root.parent), json.dumps(receipt))
        output = self.root / "out" / "onsets.json"
        with contextlib.redirect_stdout(io.StringIO()):
            digest = benchmark.write_new_json(output, receipt)
        self.assertEqual(digest, sha(output.read_bytes()))
        with self.assertRaises(ValueError):
            benchmark.write_new_json(output, receipt)

    def test_unbound_analysis_is_not_scored(self):
        self.write_analysis("f" * 64)
        receipt = benchmark.onset_labels_receipt(self.root)
        self.assertEqual(receipt["status"], "detector_analysis_unbound")
        self.assertEqual(receipt["detectors"], [])

    def test_analysis_declaring_another_original_source_is_not_scored(self):
        self.write_analysis("a" * 64)
        analysis = json.loads((self.root / "analysis.json").read_text())
        analysis["source_lineage"] = {"original_source_sha256": "e" * 64}
        (self.root / "analysis.json").write_text(json.dumps(analysis))
        receipt = benchmark.onset_labels_receipt(self.root)
        self.assertEqual(receipt["inputs"]["analysis"]["status"], "rejected_original_source_mismatch")
        self.assertEqual((receipt["status"], receipt["detectors"]), ("detector_analysis_unbound", []))
        analysis["source_lineage"] = {"original_source_sha256": "a" * 64}
        (self.root / "analysis.json").write_text(json.dumps(analysis))
        self.assertEqual(benchmark.onset_labels_receipt(self.root)["status"], "measured_operator_label_agreement")

    def test_store_bound_to_other_manifest_is_refused(self):
        self.write_analysis("a" * 64)
        store = json.loads((self.root / "review-annotations-v2.json").read_text())
        store["manifest_sha256"] = "9" * 64
        (self.root / "review-annotations-v2.json").write_text(json.dumps(store))
        with self.assertRaises(ValueError) as caught:
            benchmark.onset_labels_receipt(self.root)
        self.assertIn("annotation_manifest_mismatch", str(caught.exception))


class OnsetReportTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle_tests = load("report_bundle_tests_onsets", ROOT / "tests" / "test_report_bundle.py")

    def fixture(self):
        case = self.bundle_tests.BundleFixture("setUp")
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def table(self, output, name):
        return (output / "tables" / name).read_text().splitlines()

    def test_no_labels_yet_renders_as_status_without_rates(self):
        case = self.fixture()
        _, output = case.build()
        self.assertEqual(case.index(output)["run"]["onset_labels"]["status"], "no_operator_onset_labels")
        self.assertIn("status,no_operator_onset_labels", self.table(output, "onset_labels.csv"))
        self.assertEqual(len(self.table(output, "onset_benchmark.csv")), 1)
        status, _ = self.bundle_tests.rb.verify(output, check_origin=True)
        self.assertEqual(status, "verified")

    def test_bundle_without_a_store_is_the_no_labels_empty_state(self):
        case = self.fixture()
        case.store_path.unlink()
        _, output = case.build()
        run = case.index(output)["run"]["onset_labels"]
        self.assertEqual((run["status"], run["operator_label_count"], run["metric_rows"]), ("annotation_store_absent", 0, 0))
        summary = self.table(output, "onset_labels.csv")
        self.assertIn("operator_onset_labels,0", summary)
        self.assertIn("annotation_store_status,annotation_store_absent", summary)
        self.assertEqual(len(self.table(output, "onset_benchmark.csv")), 1)

    def test_labelled_store_produces_metric_rows_without_free_text(self):
        case = self.fixture()
        times = [10.0 + index * 0.3 for index in range(12)]
        analysis_path = case.parent / "analysis.json"
        analysis = json.loads(analysis_path.read_text())
        analysis["events"] = [{"kind": "broadband_attack_candidate", "audio_relative_seconds": value,
                               "source_timeline_seconds": value + 0.006} for value in times]
        case.write_parent_payloads()
        analysis_sha = self.bundle_tests.dump(analysis_path, analysis)
        dag = json.loads((case.parent / "dag.json").read_text())
        dag["artifact_hashes"]["analysis.json"] = analysis_sha
        self.bundle_tests.dump(case.parent / "dag.json", dag)
        store = json.loads(case.store_path.read_text())
        store["annotations"] += [dict(onset(value), operator_quote="PRIVATE-FREE-TEXT") for value in times]
        store["annotations"].append(dict(segment(9.5, 14.0), operator_quote="PRIVATE-FREE-TEXT"))
        self.bundle_tests.dump(case.store_path, store)
        _, output = case.build()
        run = case.index(output)["run"]["onset_labels"]
        self.assertEqual((run["status"], run["operator_label_count"], run["scoring_mode"]),
                         ("measured_operator_label_agreement", 12, "declared_segments_precision_and_recall"))
        rows = self.table(output, "onset_benchmark.csv")
        self.assertTrue(rows[0].startswith("detector_kind,time_axis,label_subset,tolerance_ms"))
        self.assertIn("broadband_attack_candidate,uncompensated,all_operator_labels,10,12,12,0,0,1.0,1.0,1.0,6.0", rows)
        for path in output.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"PRIVATE-FREE-TEXT", path.read_bytes())

    def onset_chunk_output(self, output):
        """Run the shipped section-7 R chunk and its table helpers against one bundle."""
        qmd = (ROOT / "reports" / "demo.qmd").read_text()
        helpers = re.search(r"^table_of <- function.*?^value_of <- function.*?^}$", qmd, re.S | re.M).group(0)
        chunk = re.search(r"^```\{r onsets\}\n(.*?)^```$", qmd, re.S | re.M).group(1)
        script = output.parent / f"onset-chunk-{output.name}.R"
        script.write_text(f"bundle_dir <- {json.dumps(str(output))}\nverified <- TRUE\n{helpers}\n{chunk}")
        result = subprocess.run([RSCRIPT, "--vanilla", str(script)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    @unittest.skipUnless(RSCRIPT, "Rscript (report shell) required to run the shipped report chunk")
    def test_report_chunk_renders_every_no_label_state_as_the_empty_state(self):
        bound = self.fixture()
        _, bound_output = bound.build()
        absent = self.fixture()
        absent.store_path.unlink()
        _, absent_output = absent.build()
        for output in (bound_output, absent_output):
            text = self.onset_chunk_output(output)
            self.assertIn("No operator onset labels yet.", text)
            self.assertNotIn("Scoring mode", text)
        self.assertIn("Annotation store: `annotation_store_absent`", self.onset_chunk_output(absent_output))

    def test_report_sources_render_empty_state_honestly(self):
        qmd = (ROOT / "reports" / "demo.qmd").read_text()
        plots = (ROOT / "reports" / "plots.R").read_text()
        self.assertIn("onset_labels.csv", qmd)
        self.assertIn("No operator onset labels yet.", qmd)
        self.assertIn("plot_onset_benchmark", qmd)
        self.assertIn("onset_benchmark.csv", plots)
        self.assertIn("No operator onset labels yet", plots)
        guide = (ROOT / "docs" / "spec" / "ONSET_LABELS.md").read_text()
        for phrase in ("just review", "onset-import", "onset-benchmark", "phrase-anchor-score", "10, 25 and 50 ms"):
            self.assertIn(phrase, guide)


NODE = shutil.which("node")


@unittest.skipUnless(NODE, "Node required for shipped JavaScript behaviour")
class OnsetReviewDisplayTests(unittest.TestCase):
    """Stored onset/onset_segment records through the shipped review UI display paths."""

    @classmethod
    def setUpClass(cls):
        cls.s1 = load("review_ui_s1_onsets", ROOT / "tests" / "test_review_ui_s1.py")

    def check_js(self, code):
        result = subprocess.run([NODE, "-e", self.s1.HARNESS + code, str(ROOT / "review" / "practice.js")],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_stored_onset_segment_and_onset_render_as_user_reported_span_and_point(self):
        records = [segment(4.0, 5.0), onset(4.5, certainty="confirmed")]
        value = self.check_js(f'''run("issueStore={{annotations:"+JSON.stringify({json.dumps(records)})+"}}");run("renderIssues()");
          run("renderCallouts(4.5)");
          emit({{issues:element("saved-issues").children.map(a=>[a.children[0].text,a.children[1].text,a.children[1].cls]),
                badges:element("review-callouts").children.map(b=>[b.children[0].text,b.children[1].text])}});''')
        self.assertEqual(value["issues"], [["4 → 5", "USER REPORTED · onset segment · user reports certainty", "issue-provenance"],
                                           ["4.5 · point", "USER REPORTED · onset · user reports certainty", "issue-provenance"]])
        self.assertEqual(value["badges"], [["USER REPORTED · onset segment", "4 → 5"],
                                           ["USER REPORTED · onset", "Point @ 4.5 · display cue only"]])

    def test_edit_form_offers_both_onset_kinds_for_a_stored_record(self):
        page = (ROOT / "review" / "index.html").read_text()
        select = re.search(r'<select id="issue-kind">(.*?)</select>', page, re.S).group(1)
        self.assertIn('<option value="onset">', select)
        self.assertIn('<option value="onset_segment">', select)


if __name__ == "__main__":
    unittest.main()
