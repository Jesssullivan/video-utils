"""timing_calibration lane tests (contract docs/spec/sprints/TIMING_CALIBRATION_S3.md, sections 5-7).

All fixtures are generated in-process from the deterministic dev namespace; no media file, real-take
derivative or accepted run is read. Only the CLI analyze test decodes through FFmpeg (skipped when
FFMPEG is unset). The sealed evaluation runs only with TIMING_CALIBRATION_S3_SEALED_EVAL=1.
"""
import array
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import statistics
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("timing_calibration", ROOT / "scripts/timing_calibration.py")
tc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tc)
RATE = tc.RATE
FORBIDDEN_TOKENS = ("missed", "extra_note", "wrong_note", "mistake", "error_verdict")
SEALED_OUTPUT = ROOT / "artifacts" / "s2" / "timing_calibration" / "sealed"

_SESSIONS: dict = {}
_RECORDS: dict = {}


def session(seed, **overrides):
    key = (seed, tuple(sorted(overrides.items())))
    if key not in _SESSIONS:
        params = tc.case_params(tc.DEV_NAMESPACE, seed)
        _SESSIONS[key] = (params, *tc.synthetic_session(params, **overrides))
    return _SESSIONS[key]


def true_distance_map(params):
    return {"mic_to_metronome": params["d_mic_metronome"], "mic_to_amp": params["d_mic_amp"]}


def measured_record(seed, **overrides):
    key = (seed, tuple(sorted(overrides.items())))
    if key not in _RECORDS:
        params, samples, segments, _ = session(seed, **overrides)
        _RECORDS[key] = tc.analyze_samples(samples, segments, distances=true_distance_map(params),
                                           distance_method="measured", room_temp_c=21.0, setup_id="dev-setup")
    return _RECORDS[key]


def scan_tokens(value, path="$"):
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if any(token in str(key).lower() for token in FORBIDDEN_TOKENS):
                found.append(f"{path}.{key}")
            found.extend(scan_tokens(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(scan_tokens(item, f"{path}[{index}]"))
    elif isinstance(value, str) and any(token in value.lower() for token in FORBIDDEN_TOKENS):
        found.append(f"{path}={value[:60]}")
    return found


def phrase_timing_doc(rhythm_sha=None, schema_version=2):
    """Hand-built phrase_timing schema-2 document shaped like phrase_timing.run() output."""
    measured = {"phrase_id": "p0", "label": "x", "label_basis": "test", "span_source_seconds": [10.25, 14.5],
                "span_audio_relative_seconds": [10.25, 14.5], "onset_count_in_span": 9,
                "click_proximal_onset_count": 8, "off_click_onset_count": 1, "additional_onsets_in_window_count": 0,
                "median_offset_ms": 31.0, "iqr_ms": [29.0, 33.0], "iqr_width_ms": 4.0,
                "median_offset_ms_delay_compensated": 29.0, "iqr_ms_delay_compensated": [27.0, 31.0],
                "observed_click_basis_median_offset_ms": 30.0, "observed_click_basis_count": 6,
                "click_reference_extrapolated": False, "offset_summary_basis": "median_offset_ms_delay_compensated",
                "direction": None, "direction_status": "withheld_uncalibrated", "direction_basis": None,
                "status": "measured", "abstain_reason": None}
    near = dict(measured, phrase_id="p1", span_source_seconds=[20.0, 24.0], median_offset_ms=9.0)
    abstained = dict(measured, phrase_id="p2", span_source_seconds=[30.0, 34.0], median_offset_ms=None,
                     iqr_ms=None, iqr_width_ms=None, click_proximal_onset_count=2, status="abstained",
                     abstain_reason="fewer_than_4_click_proximal_onsets", direction_status=None)
    return {"schema_version": schema_version, "tool": "phrase_timing", "status": "experimental_unvalidated_measurement",
            "run_kind": "real_take", "real_take_status": "unvalidated_until_operator_spot_check",
            "phrases": [measured, near, abstained],
            "inputs": {"analyzed_input_sha256": "a" * 64},
            "producer": {"phrase_timing_sha256": "b" * 64,
                         "rhythm_sha256": rhythm_sha or tc.rhythm.file_hash(ROOT / "scripts/rhythm.py")}}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class AcousticPathTests(unittest.TestCase):
    """T1: 4 geometry cases; estimate within 0.01 ms of analytic; truth inside the interval."""

    def test_geometry_cases(self):
        cases = [  # (declared met, declared amp, method, declared T, true met, true amp, true T)
            ("equal", 1.2, 1.2, "measured", 21.0, 1.2, 1.2, 19.5),
            ("amp_farther", .5, 2.5, "measured", 21.0, .5, 2.5, 22.5),
            ("metronome_farther", 2.6, .4, "measured", 21.0, 2.6, .4, 20.0),
            ("estimated", 1.0, 2.0, "estimated", None, 1.25, 1.75, 24.0),
        ]
        inside = 0
        for name, met, amp, method, temp, true_met, true_amp, true_temp in cases:
            with self.subTest(name):
                component, block = tc.acoustic_path_component({"mic_to_metronome": met, "mic_to_amp": amp}, method, temp)
                c_mid = tc.speed_of_sound(temp if temp is not None else 22.5)
                self.assertLessEqual(abs(component["estimate_ms"] - (amp - met) / c_mid * 1000), .01)
                truth = (true_amp - true_met) / tc.speed_of_sound(true_temp) * 1000
                lo, hi = component["interval_ms"]
                self.assertLessEqual(lo, truth)
                self.assertLessEqual(truth, hi)
                inside += 1
                self.assertEqual(block["per_distance_half_width_m"], tc.DISTANCE_HALF_WIDTH_M[method])
                self.assertGreater(component["standard_uncertainty_ms"], 0)
        self.assertEqual(inside, 4)

    def test_about_2_9_ms_per_metre(self):
        component, _ = tc.acoustic_path_component({"mic_to_metronome": 1.0, "mic_to_amp": 2.0}, "measured", 20.0)
        self.assertAlmostEqual(component["estimate_ms"], 2.914, places=2)

    def test_distance_parsing_and_bounds(self):
        self.assertEqual(tc.parse_distances("mic_to_metronome=1.5,mic_to_amp=0.7"),
                         {"mic_to_metronome": 1.5, "mic_to_amp": .7})
        for bad in ("mic_to_amp=1", "mic_to_metronome=1,mic_to_amp=x", "mic_to_metronome=1,mic_to_amp=1,ear_to_amp=1",
                    "mic_to_metronome=1,mic_to_amp=1,foo=2", ""):
            with self.subTest(bad), self.assertRaises(tc.Refusal) as caught:
                tc.parse_distances(bad)
            self.assertEqual(caught.exception.code, "distances_invalid")


class DetectorBiasTests(unittest.TestCase):
    """T2: 3 dev seeds x 3 classes within 1.0 ms of generator truth; T4: C1-only open attacks detected."""

    def test_t2_bias_recovery(self):
        within = 0
        for seed in tc.DEV_SEEDS:
            params, samples, segments, truth = session(seed)
            measured = tc.measure_session(samples, tc.normalize_segments(segments))
            record = measured_record(seed)
            for klass, key in (("click", "clicks"), ("palm_muted_pick_attack", "palm_muted_pick_attack"),
                               ("open_pick_attack", "open_pick_attack")):
                with self.subTest(seed=seed, klass=klass):
                    valid = [row for row in measured["classes"][klass] if row["valid"]]
                    true_bias = statistics.median(row["det"] - min(truth[key], key=lambda t: abs(t - row["det"]))
                                                  for row in valid) * 1000
                    estimate = record["components"]["detector_bias"]["classes"][klass]["bias_estimate_ms"]
                    self.assertIsNotNone(estimate)
                    self.assertLessEqual(abs(estimate - true_bias), 1.0)
                    within += 1
        self.assertEqual(within, 9)

    def test_t4_low_register_open_attacks_detected_without_high_pass(self):
        for seed in tc.DEV_SEEDS:
            params, samples, segments, truth = session(seed, open_midis=(24,))
            before = tc.samples_sha256(samples)
            measured = tc.measure_session(samples, tc.normalize_segments(segments))
            detected = sum(any(-.010 <= row["det"] - onset <= .040 for row in measured["classes"]["open_pick_attack"])
                           for onset in truth["open_pick_attack"])
            with self.subTest(seed=seed):
                self.assertEqual(len(truth["open_pick_attack"]), 16)
                self.assertGreaterEqual(detected, tc.rhythm.DELAY_MINIMUM_DETECTIONS)
                self.assertEqual(tc.samples_sha256(samples), before)
                # The fixture carries 32.70 Hz content (Goertzel power vs a 47 Hz control) and nothing filters it.
                span = next(s for s in segments["segments"] if s["kind"] == "offbeat_open")
                block = samples[round(span["start_seconds"] * RATE):round(span["end_seconds"] * RATE)]
                self.assertGreater(goertzel(block, 32.70), 4 * goertzel(block, 47.0))

    def test_fine_probe_table_is_fixed_and_noise_free(self):
        table = tc.fine_estimator_bias_table()
        self.assertEqual(set(table["classes"]), {"click", "palm_muted_pick_attack", "open_pick_attack"})
        for probe, row in table["probes"].items():
            self.assertEqual(row["valid_count"], 16, probe)
        self.assertEqual(table, tc.fine_estimator_bias_table())


def goertzel(block, frequency):
    coefficient = 2 * math.cos(2 * math.pi * frequency / RATE)
    s1 = s2 = 0.0
    for value in block:
        s1, s2 = value + coefficient * s1 - s2, s1
    return s1 * s1 + s2 * s2 - coefficient * s1 * s2


class EndToEndDevTests(unittest.TestCase):
    """T3: 3 dev seeds x 6 phrases, arm E1: median |calibrated - truth| <= 3.0 ms (withheld phrases count as inf)."""

    def test_t3_end_to_end(self):
        errors, rows = [], []
        for seed in tc.DEV_SEEDS:
            case = tc.run_seed(tc.case_params(tc.DEV_NAMESPACE, seed), arms=("E1",))["E1"]
            self.assertEqual(case["record_status"], "calibrated")
            rows.extend(case["phrases"])
            errors.extend(math.inf if row["abs_error_ms"] is None else row["abs_error_ms"] for row in case["phrases"])
        self.assertEqual(len(errors), 18)
        self.assertLessEqual(statistics.median(errors), 3.0)
        emitted = [row for row in rows if row["direction"] in ("ahead_of_click", "behind_click")]
        self.assertTrue(all((row["direction"] == "ahead_of_click") == (row["truth_ms"] < 0) for row in emitted))
        self.assertFalse(any(row["direction"] in ("ahead_of_click", "behind_click")
                             for row in rows if abs(row["truth_ms"]) <= 2.0))


class AbstentionTests(unittest.TestCase):
    """A1: 4/4 abstain with the expected reason and null numeric estimates."""

    def assert_abstained(self, record, expected):
        self.assertEqual(record["status"], "abstained")
        self.assertTrue(set(record["abstain_reasons"]) & set(expected), record["abstain_reasons"])
        offset = record["offset_correction_ms"]
        self.assertIsNone(offset["estimate"])
        self.assertIsNone(offset["expanded_uncertainty_ms"])
        self.assertIsNone(offset["interval_ms"])

    def test_a_too_few_click_events(self):
        params, samples, segments, _ = session(11)
        trimmed = copy.deepcopy(segments)
        clicks = [s for s in trimmed["segments"] if s["kind"] == "click_only"]
        clicks[0]["end_seconds"] = clicks[0]["start_seconds"] + 12 * params["period"]
        trimmed["segments"] = [s for s in trimmed["segments"] if s is not clicks[1]]
        record = tc.analyze_samples(samples, trimmed, distances=true_distance_map(params), distance_method="measured",
                                    room_temp_c=21.0, setup_id="dev-setup")
        self.assert_abstained(record, {"insufficient_click_events"})
        self.assertLess(record["components"]["detector_bias"]["classes"]["click"]["valid_fine_onset_count"], 16)

    def test_b_estimated_distances_unknown_amp_chain(self):
        params, samples, segments, _ = session(11)
        record = tc.analyze_samples(samples, segments, distances=true_distance_map(params), distance_method="estimated",
                                    amp_chain="unknown", setup_id="dev-setup")
        self.assert_abstained(record, {"expanded_uncertainty_exceeds_decision_margin"})
        self.assertGreaterEqual(record["offset_correction_ms"]["attempted_expanded_uncertainty_ms"], 5.77)

    def test_c_click_masked_by_fan_noise(self):
        params, samples, segments, truth = session(11, noise_amplitude=.12, noise_ar=.55)
        self.assertLessEqual(truth["click_snr_db"], -6.0)
        record = tc.analyze_samples(samples, segments, distances=true_distance_map(params), distance_method="measured",
                                    room_temp_c=21.0, setup_id="dev-setup")
        self.assert_abstained(record, {"click_grid_not_fitted", "insufficient_click_events"})

    def test_d_on_click_segment_played_offbeat(self):
        params = tc.case_params(tc.DEV_NAMESPACE, 11)
        record = measured_record(11, on_click_shift_s=params["period"] / 2)
        self.assert_abstained(record, {"played_on_click_consistency_failed"})
        check = record["consistency_check"]["played_on_click"]
        self.assertEqual(check["status"], "failed")
        self.assertGreater(abs(check["calibrated_median_ms"]), 100)

    def test_missing_segment_and_distance_bounds(self):
        params, samples, segments, _ = session(11)
        partial = {"schema_version": 1, "segments": [s for s in segments["segments"] if s["kind"] != "offbeat_open"]}
        record = tc.analyze_samples(samples, partial, distances={"mic_to_metronome": 1.0, "mic_to_amp": 25.0},
                                    distance_method="measured", setup_id="dev-setup")
        self.assertIn("segment_missing:offbeat_open", record["abstain_reasons"])
        self.assertIn("distance_out_of_bounds", record["abstain_reasons"])
        self.assertIsNone(record["offset_correction_ms"]["estimate"])

    def test_on_click_segment_never_sets_the_offset(self):
        record = measured_record(11)
        params = tc.case_params(tc.DEV_NAMESPACE, 11)
        shifted = measured_record(11, on_click_shift_s=.010)
        self.assertEqual(record["status"], "calibrated")
        self.assertFalse(record["consistency_check"]["played_on_click"]["used_in_offset_estimate"])
        # Moving the played-on-click attacks changes the check but not how the offset is formed.
        self.assertEqual(shifted["consistency_check"]["played_on_click"]["status"], "passed")
        self.assertNotEqual(shifted["consistency_check"]["played_on_click"]["calibrated_median_ms"],
                            record["consistency_check"]["played_on_click"]["calibrated_median_ms"])
        self.assertIsNotNone(params)


class ApplyRefusalTests(unittest.TestCase):
    """R1: 6/6 typed refusals through the CLI; no file written."""

    def run_apply(self, record, timing, setup_id="dev-setup", output_under_runs=False, write_record=True):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            timing_path = base / "phrase-timing.json"
            timing_path.write_text(json.dumps(timing))
            record_path = base / "calibration-record.json"
            if write_record:
                record_path.write_text(json.dumps(record))
            output = base / ("artifacts/runs/x" if output_under_runs else "out")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
                code = tc.main(["apply", "--phrase-timing", str(timing_path), "--calibration", str(record_path),
                                "--setup-id", setup_id, "--output-root", str(output)])
            written = [p for p in output.rglob("*") if p.is_file()] if output.exists() else []
            refusal = json.loads(stderr.getvalue()).get("refusal") if stderr.getvalue().startswith("{") else None
            return code, refusal, written

    def test_r1_refusals(self):
        calibrated = measured_record(11)
        params, samples, segments, _ = session(11)
        abstained = tc.analyze_samples(samples, segments, distances=true_distance_map(params),
                                       distance_method="estimated", amp_chain="unknown", setup_id="dev-setup")
        cases = {
            "calibration_record_required": dict(record=calibrated, timing=phrase_timing_doc(), write_record=False),
            "calibration_abstained": dict(record=abstained, timing=phrase_timing_doc()),
            "detector_identity_mismatch": dict(record=calibrated, timing=phrase_timing_doc(rhythm_sha="0" * 64)),
            "setup_id_mismatch": dict(record=calibrated, timing=phrase_timing_doc(), setup_id="other-room"),
            "phrase_timing_schema_unsupported": dict(record=calibrated, timing=phrase_timing_doc(schema_version=1)),
            "output_under_accepted_runs": dict(record=calibrated, timing=phrase_timing_doc(), output_under_runs=True),
        }
        refused = 0
        for expected, kwargs in cases.items():
            with self.subTest(expected):
                code, refusal, written = self.run_apply(**kwargs)
                self.assertEqual(code, 2)
                self.assertEqual(refusal, expected)
                self.assertEqual(written, [])
                refused += 1
        self.assertEqual(refused, 6)

    def test_pure_refusals_and_invalid_record(self):
        record = measured_record(11)
        with self.assertRaises(tc.Refusal) as caught:
            tc.apply_view(phrase_timing_doc(), None, "dev-setup")
        self.assertEqual(caught.exception.code, "calibration_record_required")
        tampered = dict(record, unexpected_key=1)
        with self.assertRaises(tc.Refusal) as caught:
            tc.apply_view(phrase_timing_doc(), tampered, "dev-setup")
        self.assertEqual(caught.exception.code, "calibration_record_invalid")
        widened = copy.deepcopy(record)
        widened["offset_correction_ms"]["expanded_uncertainty_ms"] = 9.0
        with self.assertRaises(tc.Refusal) as caught:
            tc.apply_view(phrase_timing_doc(), widened, "dev-setup")
        self.assertEqual(caught.exception.code, "calibration_record_invalid")


class PreservationTests(unittest.TestCase):
    """P1 (input unchanged, source entries verbatim) and P2 (analysis only)."""

    def test_p1_cli_apply_preserves_input(self):
        record = measured_record(11)
        timing = phrase_timing_doc()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            timing_path, record_path = base / "phrase-timing.json", base / "calibration-record.json"
            timing_path.write_text(json.dumps(timing, indent=1))
            record_path.write_text(json.dumps(record))
            before = sha(timing_path), sha(record_path)
            with contextlib.redirect_stdout(io.StringIO()):
                code = tc.main(["apply", "--phrase-timing", str(timing_path), "--calibration", str(record_path),
                                "--setup-id", "dev-setup", "--output-root", str(base / "out")])
            self.assertEqual(code, 0)
            self.assertEqual((sha(timing_path), sha(record_path)), before)
            [view_path] = list((base / "out").rglob("phrase-timing-calibrated.json"))
            view = json.loads(view_path.read_text())
            self.assertEqual(view["inputs"]["phrase_timing_sha256"], before[0])
            self.assertEqual(view["inputs"]["calibration_record_sha256"], before[1])
            self.assertTrue(view["source_phrase_timing_unmodified"])
            self.assertEqual([p["source_entry"] for p in view["phrases"]], timing["phrases"])
            for phrase, source in zip(view["phrases"], timing["phrases"]):
                self.assertEqual(phrase["source_entry"]["span_source_seconds"], source["span_source_seconds"])
            self.assertEqual(sorted(p.name for p in (base / "out").rglob("*") if p.is_file()),
                             ["phrase-timing-calibrated.json"])

    def test_p1_direction_rule(self):
        record = measured_record(11)
        correction = record["offset_correction_ms"]["estimate"]
        expanded = record["offset_correction_ms"]["expanded_uncertainty_ms"]
        timing = phrase_timing_doc()
        timing["phrases"][0]["median_offset_ms"] = correction + 20.0
        timing["phrases"][1]["median_offset_ms"] = correction + 1.0
        snapshot = copy.deepcopy(timing)
        view = tc.apply_view(timing, record, "dev-setup")
        self.assertEqual(timing, snapshot)
        first, second, third = (p["calibrated"] for p in view["phrases"])
        u_median = tc.PHRASE_MEDIAN_FACTOR * 4.0 / math.sqrt(8)
        self.assertAlmostEqual(first["combined_uncertainty_ms"], math.hypot(expanded, u_median))
        self.assertEqual(first["direction"], "behind_click")
        self.assertEqual(first["direction_status"], "calibrated_direction")
        self.assertEqual(second["direction"], "within_uncertainty")
        self.assertGreaterEqual(second["direction_threshold_ms"], tc.DECISION_MARGIN_MS)
        self.assertIsNone(third["direction"])
        self.assertEqual(third["direction_status"], "phrase_abstained")
        self.assertEqual(first["basis_field"], "median_offset_ms")

    def test_click_coincidence_guard(self):
        record = measured_record(11)
        self_offset = record["click_grid"]["click_broadband_self_offset"]
        self.assertEqual(self_offset["status"], "measured")
        timing = phrase_timing_doc()
        timing["phrases"][0]["median_offset_ms"] = self_offset["median_ms"] + 1.0
        view = tc.apply_view(timing, record, "dev-setup")
        guarded = view["phrases"][0]["calibrated"]
        self.assertIsNone(guarded["direction"])
        self.assertEqual(guarded["withheld_basis"], "onset_median_coincides_with_click_self_detection")

    def test_p2_analysis_only_in_memory(self):
        params, samples, segments, _ = session(11)
        before = tc.samples_sha256(samples)
        record = measured_record(11)
        self.assertEqual(tc.samples_sha256(samples), before)
        self.assertIs(record["audio_written"], False)
        self.assertEqual(record["filters_applied"], [])

    @unittest.skipUnless(os.environ.get("FFMPEG") and os.environ.get("FFPROBE"), "FFMPEG/FFPROBE not exported")
    def test_p2_cli_analyze_on_wav(self):
        params, samples, segments, _ = session(12)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            wav = base / "calibration.wav"
            pcm = array.array("h", (max(-32767, min(32767, round(v * 32767))) for v in samples))
            with wave.open(str(wav), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(RATE)
                handle.writeframes(pcm.tobytes())
            seg_path = base / "segments.json"
            seg_path.write_text(json.dumps(segments))
            before = sha(wav)
            distances = f"mic_to_metronome={params['d_mic_metronome']},mic_to_amp={params['d_mic_amp']}"
            with contextlib.redirect_stdout(io.StringIO()):
                code = tc.main(["analyze", str(wav), "--segments", str(seg_path), "--distances", distances,
                                "--distance-method", "measured", "--room-temp-c", "21", "--amp-chain", "analog",
                                "--setup-id", "dev-setup", "--output-root", str(base / "out")])
            self.assertEqual(code, 0)
            self.assertEqual(sha(wav), before)
            outputs = [p for p in (base / "out").rglob("*") if p.is_file()]
            self.assertEqual([p.name for p in outputs], ["calibration-record.json"])
            record = json.loads(outputs[0].read_text())
            self.assertEqual(record["input"]["sha256"], before)
            self.assertEqual(record["input"]["signal_chain"], "source_audio")
            self.assertIs(record["audio_written"], False)
            self.assertEqual(record["filters_applied"], [])
            self.assertEqual(set(record), tc.RECORD_KEYS)
            self.assertEqual(record["status"], measured_record(12)["status"])


class SchemaAndTokenTests(unittest.TestCase):
    """P3: exact key sets, fixed unknowns present, no verdict tokens."""

    def test_record_schema(self):
        records = [measured_record(11), measured_record(11, on_click_shift_s=tc.case_params(tc.DEV_NAMESPACE, 11)["period"] / 2)]
        for record in records:
            self.assertEqual(set(record), tc.RECORD_KEYS)
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["tool"], "timing_calibration")
            self.assertEqual(record["kind"], "capture_latency_calibration_record")
            for key, value in tc.FIXED_UNKNOWNS.items():
                self.assertEqual(record[key], value)
            self.assertEqual(set(record["components"]), set(tc.COMPONENT_NAMES))
            for name in tc.COMPONENT_NAMES:
                self.assertTrue(tc.COMPONENT_KEYS <= set(record["components"][name]), name)
            classes = record["components"]["detector_bias"]["classes"]
            self.assertEqual(classes["legato_tapping_sweep"], {"status": "uncalibrated"})
            for klass in ("click", "palm_muted_pick_attack", "open_pick_attack"):
                self.assertEqual(set(classes[klass]), tc.CLASS_KEYS)
            self.assertEqual(set(record["offset_correction_ms"]), tc.OFFSET_KEYS)
            self.assertEqual(set(record["consistency_check"]["played_on_click"]), tc.CONSISTENCY_KEYS)
            self.assertEqual(record["consistency_check"]["played_on_click"]["role"], "consistency_check_not_ground_truth")
            self.assertEqual(record["decision_margin_ms"], 5.0)
            self.assertEqual(record["reference_definition"], "source_emission")
            self.assertEqual(record["claims"]["listening"], [])
            self.assertTrue(all(r in tc.ABSTAIN_REASONS for r in record["abstain_reasons"]))
            self.assertEqual(scan_tokens(record), [])
            tc.validate_record(record)

    def test_view_schema(self):
        view = tc.apply_view(phrase_timing_doc(), measured_record(11), "dev-setup")
        self.assertEqual(set(view), tc.VIEW_KEYS)
        self.assertEqual(view["kind"], "calibrated_phrase_timing_view")
        for key, value in tc.FIXED_UNKNOWNS.items():
            self.assertEqual(view[key], value)
        self.assertEqual(view["click_identity"], "unverified")
        self.assertEqual(view["real_take_status"], "unvalidated_until_operator_spot_check")
        self.assertEqual(view["direction_meaning"], tc.DIRECTION_MEANING)
        for phrase in view["phrases"]:
            self.assertEqual(set(phrase), {"source_entry", "calibrated"})
            self.assertEqual(set(phrase["calibrated"]), tc.CALIBRATED_KEYS)
            self.assertIn(phrase["calibrated"]["direction"], ("ahead_of_click", "behind_click", "within_uncertainty", None))
        self.assertEqual(view["claims"]["listening"], [])
        self.assertEqual(scan_tokens({k: v for k, v in view.items() if k != "phrases"}), [])
        self.assertEqual(scan_tokens([p["calibrated"] for p in view["phrases"]]), [])

    def test_listener_view_is_arithmetic_only(self):
        params, samples, segments, _ = session(11)
        distances = dict(true_distance_map(params), ear_to_metronome=1.0, ear_to_amp=2.0)
        record = tc.analyze_samples(samples, segments, distances=distances, distance_method="measured",
                                    room_temp_c=21.0, setup_id="dev-setup")
        self.assertEqual(record["listener_view"]["status"], "computed")
        self.assertIs(record["listener_view"]["direction_bearing"], False)
        view = tc.apply_view(phrase_timing_doc(), record, "dev-setup")
        first = view["phrases"][0]["calibrated"]
        self.assertAlmostEqual(first["listener_view_offset_ms"],
                               first["calibrated_median_offset_ms"] + record["listener_view"]["estimate_ms"])

    def test_segments_closed_schema(self):
        for bad in ({"schema_version": 1, "segments": [{"kind": "click_only", "start_seconds": 0, "end_seconds": 5}]},
                    {"schema_version": 1, "segments": [{"kind": "tapping", "start_seconds": 0, "end_seconds": 5,
                                                        "review_text": "x"}]},
                    {"schema_version": 1, "segments": [], "extra": True},
                    {"schema_version": 1, "segments": [{"kind": "click_only", "start_seconds": 5, "end_seconds": 1,
                                                        "review_text": "x"}]}):
            with self.subTest(bad=bad), self.assertRaises(tc.Refusal) as caught:
                tc.normalize_segments(bad)
            self.assertEqual(caught.exception.code, "segments_invalid")


@unittest.skipUnless(os.environ.get("TIMING_CALIBRATION_S3_SEALED_EVAL") == "1", "sealed evaluation runs once, on request")
class SealedEvaluationTests(unittest.TestCase):
    """S1-S4 on sealed seeds 5501-5508; results are recorded, acceptance is reported in the receipt."""

    def test_sealed_evaluation(self):
        result = tc.sealed_evaluation()
        result["producer"] = tc.producer_hashes()
        SEALED_OUTPUT.mkdir(parents=True, exist_ok=True)
        tc.rhythm.atomic_write(SEALED_OUTPUT / "results.json", json.dumps(result, indent=2, allow_nan=False, default=str) + "\n")
        for arm in ("E1", "E2", "E3"):
            summary = result["summary"][arm]
            self.assertEqual(summary["case_count"], 8)
            self.assertEqual(summary["phrase_count"], 48)


if __name__ == "__main__":
    unittest.main()
