import contextlib
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import random
import statistics
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("phrase_timing", ROOT / "scripts/phrase_timing.py")
phrase_timing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(phrase_timing)
rhythm = phrase_timing.rhythm

RATE = rhythm.RATE
TUNING_MIDI = (24, 29, 34, 39, 46, 51, 56, 60, 65)
PERIODS = (.6757, 60 / 150, 60 / 185)
FORBIDDEN_TOKENS = ("missed", "extra_note", "wrong_note", "mistake", "error_verdict")
SEALED_DIR = ROOT / "artifacts" / "s2" / "rhythm_clicks" / "sealed"
SOURCE_SHA = "f" * 64


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


def phrase_fixture(period, deltas, rng, *, lead_beats=2, phrase_beats=8, gap_beats=4, jitter=.003):
    """16 kHz clicks plus, per phrase, 8 click-aligned distorted attacks at click+delta+N(0, jitter).

    Each phrase also carries 4 off-click subdivision attacks (P/3 or P/2 after a click) and one
    click-aligned attack boosted 1.6x so that it masks its coincident click in the transient
    envelopes. Truth is the median of the sample-rounded generated offsets of the 8 aligned attacks.
    """
    total_beats = lead_beats + len(deltas) * (phrase_beats + gap_beats)
    phase = .3
    length = round((phase + total_beats * period + .6) * RATE)
    samples = [0.0] * length
    noise = random.Random(rng.random())
    colored = 0.0
    for index in range(length):
        white = noise.uniform(-1, 1)
        colored = .7 * colored + .3 * white
        samples[index] = .004 * (.5 * white + .5 * colored)
    click_amplitude = rng.uniform(.06, .10)
    wave = [click_amplitude * math.exp(-(j / RATE) / .0018) * math.sin(2 * math.pi * 3500 * j / RATE) for j in range(round(.009 * RATE))]
    click_samples = [round((phase + beat * period) * RATE) for beat in range(total_beats)]
    for sample in click_samples:
        for j, value in enumerate(wave):
            samples[sample + j] += value
    attacks, phrases, truths = [], [], []
    for number, delta in enumerate(deltas):
        first_beat = lead_beats + number * (phrase_beats + gap_beats)
        masked = rng.randrange(phrase_beats)
        offsets = []
        for step in range(phrase_beats):
            click = click_samples[first_beat + step]
            onset = round(click + (delta + rng.gauss(0, jitter)) * RATE)
            offsets.append((onset - click) / RATE)
            attacks.append((onset, 1.6 if step == masked else 1.0))
        divisor = rng.choice((3, 2))
        for step in sorted(rng.sample(range(phrase_beats), 4)):
            attacks.append((round(click_samples[first_beat + step] + period / divisor * RATE), 1.0))
        phrases.append({"phrase_id": f"phrase-{number}", "label": f"generated phrase {number}",
                        "label_basis": "synthetic_fixture_span",
                        "span_source_seconds": [click_samples[first_beat] / RATE - period / 2,
                                                click_samples[first_beat + phrase_beats - 1] / RATE + period / 2]})
        truths.append(statistics.median(offsets))
    attacks.sort()
    for index, (onset, boost) in enumerate(attacks):
        following = attacks[index + 1][0] if index + 1 < len(attacks) else length
        extent = min(following - onset, round(.5 * RATE), length - onset)
        midi = rng.choice(TUNING_MIDI)
        frequency = 440 * 2 ** ((midi - 69) / 12)
        drive, decay = rng.uniform(2.6, 4.6), rng.uniform(.015, .040)
        gain = .17 * rng.uniform(.65, 1.0) * boost
        sustained = rng.random() < .5
        for j in range(extent):
            age = j / RATE
            envelope = min(1.0, age / .0015, (extent - j) / (.006 * RATE))
            envelope *= (.35 + .65 * math.exp(-age / decay)) * math.exp(-age / .6) if sustained else math.exp(-age / decay)
            samples[onset + j] += gain * envelope * math.tanh(drive * math.sin(2 * math.pi * frequency * age))
    return samples, phrases, truths


def measure_fixture(period, deltas, rng):
    samples, phrases, truths = phrase_fixture(period, deltas, rng)
    analysis = rhythm.analyze(samples)
    analysis["source"] = {"sha256": SOURCE_SHA}
    result = phrase_timing.measure(analysis, phrases, phrase_basis="synthetic_fixture_span", run_kind="synthetic_fixture")
    return result, truths


def errors(result, truths, field):
    values = []
    for entry, truth in zip(result["phrases"], truths):
        estimate = entry[field]
        values.append(math.inf if entry["status"] != "measured" or estimate is None else abs(estimate - truth * 1000))
    return values


def logic_analysis(*, onsets=(), clicks=(), grid=True, drift=None, duration=60.0, delays=(.0023, .0002)):
    """Hand-built analysis dict for rule tests (constant grid period 0.5 s, phase 1.0 s)."""
    events = [{"kind": "broadband_attack_candidate", "audio_relative_seconds": value} for value in onsets]
    events += [{"kind": "periodic_high_frequency_candidate", "audio_relative_seconds": value} for value in clicks]
    table = {"broadband_attack_candidate": {"delay_seconds": delays[0]},
             "periodic_high_frequency_candidate": {"delay_seconds": delays[1]}}
    return {"source": {"sha256": SOURCE_SHA}, "timeline": {"audio_stream_start_seconds": 0.0},
            "analysis": {"duration_seconds": duration, "onset_detector_delay_calibration": {"compensation_table": table}},
            "click_grid": {"period_seconds": .5, "phase_seconds_audio_relative": 1.0,
                           "observed_events": [{"beat_index": 0}, {"beat_index": 100}]} if grid else None,
            "click_grid_drift": drift or {"status": "no_periodic_seed"}, "events": events}


class PhraseTimingRuleTests(unittest.TestCase):
    def test_sign_convention_nearest_counts_and_off_click(self):
        onsets = [2.0 - .010, 2.5 - .012, 3.0 - .008, 3.5 - .011, 3.5 + .020, 3.5 + .25]
        analysis = logic_analysis(onsets=onsets, clicks=[2.0, 2.5, 3.0, 3.5])
        phrase = {"phrase_id": "p", "label": "x", "label_basis": "test", "span_source_seconds": [1.75, 3.9]}
        entry = phrase_timing.measure(analysis, [phrase], phrase_basis="test", run_kind="synthetic_fixture")["phrases"][0]
        self.assertEqual(entry["status"], "measured")
        self.assertEqual(entry["click_proximal_onset_count"], 4)
        self.assertEqual(entry["additional_onsets_in_window_count"], 1)
        self.assertEqual(entry["off_click_onset_count"], 1)
        self.assertAlmostEqual(entry["median_offset_ms"], -10.5, places=6)
        self.assertAlmostEqual(entry["median_offset_ms_delay_compensated"], -10.5 - 2.3 + .2, places=6)
        self.assertAlmostEqual(entry["observed_click_basis_median_offset_ms"], -10.5, places=6)
        self.assertEqual(entry["tendency_label"], "ahead_of_click")
        self.assertEqual(entry["iqr_ms"][0] <= entry["median_offset_ms"] <= entry["iqr_ms"][1], True)

    def test_p3_three_click_proximal_onsets_abstain(self):
        analysis = logic_analysis(onsets=[2.0 + .01, 2.5 + .01, 3.0 + .01, 3.25])
        phrase = {"phrase_id": "p", "label": None, "label_basis": "test", "span_source_seconds": [1.75, 3.4]}
        result = phrase_timing.measure(analysis, [phrase], phrase_basis="test", run_kind="synthetic_fixture")
        entry = result["phrases"][0]
        self.assertEqual(entry["status"], "abstained")
        self.assertEqual(entry["abstain_reason"], "fewer_than_4_click_proximal_onsets")
        self.assertEqual(entry["click_proximal_onset_count"], 3)
        self.assertIsNone(entry["median_offset_ms"])
        self.assertIsNone(entry["tendency_label"])
        self.assertEqual(result["summary"]["abstain_reason_counts"]["fewer_than_4_click_proximal_onsets"], 1)

    def test_p3_no_grid_and_outside_span_abstain(self):
        onsets = [2.0, 2.5, 3.0, 3.5, 4.0]
        phrase = {"phrase_id": "p", "label": None, "label_basis": "test", "span_source_seconds": [1.75, 4.2]}
        result = phrase_timing.measure(logic_analysis(onsets=onsets, grid=False), [phrase, dict(phrase, phrase_id="q")],
                                       phrase_basis="test", run_kind="synthetic_fixture")
        self.assertEqual([entry["abstain_reason"] for entry in result["phrases"]], ["no_click_grid", "no_click_grid"])
        self.assertIsNone(result["click_reference"]["basis"])
        self.assertEqual(result["summary"]["measured_count"], 0)
        outside = dict(phrase, span_source_seconds=[70.0, 75.0])
        entry = phrase_timing.measure(logic_analysis(onsets=onsets), [outside], phrase_basis="test",
                                      run_kind="synthetic_fixture")["phrases"][0]
        self.assertEqual(entry["abstain_reason"], "span_outside_analysis")

    def test_drift_reference_preferred_over_constant_grid(self):
        parameters = {"anchor_click_seconds_audio_relative": 1.0, "ioi_intercept_seconds_at_audio_time_zero": .49,
                      "period_change_per_second": .01, "retained_beat_index_range": [0, 40]}
        drift = {"status": "fitted", "model_parameters": parameters, "confidence_label": "strong_drift_evidence"}
        predicted = [rhythm.drift_click_time(parameters, beat) for beat in range(10, 16)]
        analysis = logic_analysis(onsets=[time + .015 for time in predicted], drift=drift)
        phrase = {"phrase_id": "p", "label": None, "label_basis": "test", "span_source_seconds": [predicted[0] - .2, predicted[-1] + .2]}
        result = phrase_timing.measure(analysis, [phrase], phrase_basis="test", run_kind="real_take")
        entry = result["phrases"][0]
        self.assertEqual(result["click_reference"]["basis"], "linear_period_drift_model")
        self.assertAlmostEqual(entry["median_offset_ms"], 15, places=6)
        self.assertFalse(entry["click_reference_extrapolated"])
        self.assertEqual(entry["tendency_label"], "behind_click")
        self.assertEqual(result["real_take_status"], "unvalidated_until_operator_spot_check")

    def test_fixed_unknown_fields_and_no_verdict_tokens(self):
        result = phrase_timing.measure(logic_analysis(onsets=[2.0, 2.5, 3.0, 3.5]),
                                       [{"phrase_id": "p", "label": None, "label_basis": "test", "span_source_seconds": [1.75, 3.7]}],
                                       phrase_basis="test", run_kind="synthetic_fixture")
        for key, value in {"click_identity": "unverified", "physical_capture_latency": "uncalibrated",
                           "listening_ab": "not_performed", "performance_grading": "not_performed",
                           "expected_rhythm_reference": None, "real_take_status": "synthetic_fixture"}.items():
            self.assertIn(key, result)
            self.assertEqual(result[key], value)
        self.assertEqual(scan_tokens(result), [])


class PhraseTimingFileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.analysis = self.root / "analysis.json"
        self.analysis.write_text(json.dumps(logic_analysis(onsets=[2.0, 2.5, 3.0, 3.5, 4.0])))

    def markers(self, bound):
        return {"format": "arrangement_reference_review_markers_seconds", "analyzed_input_sha256": bound,
                "markers": [{"name": "arrangement_aligned_unit_review", "source_time_seconds": 1.75, "end_seconds": 4.2,
                             "display_label": "ALIGNMENT CANDIDATE: Verse 1 phrase 1", "label_basis": "estimated"},
                            {"name": "arrangement_boundary_review", "source_time_seconds": 1.75, "end_seconds": 1.75}]}

    def test_hash_binding_refusal(self):
        path = self.root / "markers.json"
        path.write_text(json.dumps(self.markers("0" * 64)))
        with self.assertRaisesRegex(ValueError, "not bound"):
            phrase_timing.run(self.analysis, path, self.root / "out")
        self.assertFalse((self.root / "out").exists())

    def test_refuses_accepted_run_output(self):
        path = self.root / "markers.json"
        path.write_text(json.dumps(self.markers(SOURCE_SHA)))
        with self.assertRaisesRegex(ValueError, "accepted run"):
            phrase_timing.run(self.analysis, path, self.root / "artifacts" / "runs" / "x")

    def test_markers_and_review_spans_cli(self):
        markers = self.root / "markers.json"
        markers.write_text(json.dumps(self.markers(SOURCE_SHA)))
        spans = self.root / "phrases.json"
        spans.write_text(json.dumps({"lineage": {"input_sha256": SOURCE_SHA}, "observations": {"proposed_review_spans": [
            {"start_seconds": 1.75, "end_seconds": 4.2, "label": "riff_region_1", "source_start_seconds": 1.75, "source_end_seconds": 4.2}]}}))
        for path, basis, count in ((markers, "reference_conditioned_alignment_candidate", 1), (spans, "automatic_review_span", 1)):
            with patch("sys.argv", ["phrase_timing.py", "--analysis", str(self.analysis), "--phrases", str(path),
                                    "--output-root", str(self.root / "out")]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(phrase_timing.main(), 0)
            written = sorted((self.root / "out").glob("*/phrase-timing.json"), key=lambda item: item.stat().st_mtime)[-1]
            result = json.loads(written.read_text())
            self.assertEqual(result["phrase_basis"], basis)
            self.assertEqual(result["summary"]["phrase_count"], count)
            self.assertEqual(result["real_take_status"], "unvalidated_until_operator_spot_check")
            self.assertEqual(result["inputs"]["analysis_file_sha256"], rhythm.file_hash(self.analysis))
            self.assertEqual(result["inputs"]["phrase_binding_sha256"], SOURCE_SHA)
            self.assertEqual(scan_tokens(result), [])
        self.assertEqual(json.loads(written.read_text())["inputs"]["phrase_input"]["excluded_marker_count"], 0)


class PhraseTimingFixtureTests(unittest.TestCase):
    def test_p1_dev_arms_within_5_ms(self):
        arms = {"on_time": [0, 0, 0, 0], "rushing": [-.008, -.015, -.025, -.015], "dragging": [.008, .015, .025, .015]}
        for position, (arm, deltas) in enumerate(arms.items()):
            with self.subTest(arm=arm):
                result, truths = measure_fixture(PERIODS[position], deltas, random.Random(f"phrase-timing-dev:{arm}"))
                compensated = errors(result, truths, "median_offset_ms_delay_compensated")
                raw = errors(result, truths, "median_offset_ms")
                self.assertLessEqual(statistics.median(compensated), 5.0, (compensated, raw))
                self.assertEqual(result["summary"]["measured_count"], 4)
                self.assertIn(result["click_reference"]["basis"], ("linear_period_drift_model", "constant_click_grid"))
                self.assertEqual(scan_tokens(result), [])
                if arm != "on_time":
                    expected = "ahead_of_click" if arm == "rushing" else "behind_click"
                    self.assertGreaterEqual(sum(entry["tendency_label"] == expected for entry in result["phrases"]), 3)

    @unittest.skipUnless(os.environ.get("PHRASE_TIMING_S2_SEALED_EVAL") == "1", "sealed P2 evaluation runs once after the eval receipt")
    def test_p2_sealed_phrase_timing_eval(self):
        def unit(seed, arm, phrase, knob):
            digest = hashlib.sha256(f"rhythm-s2-phrase-eval:{seed}:{arm}:{phrase}:{knob}".encode()).digest()
            return int.from_bytes(digest[:8], "big") / 2**64
        ranges = {"on_time": (0.0, 0.0), "rushing": (-.030, -.006), "dragging": (.006, .030)}
        report = {"metric": "P2", "arms": {}, "rows": []}
        for arm, (low, high) in ranges.items():
            primary, secondary, within, sign_correct = [], [], 0, 0
            for seed in range(7301, 7305):
                deltas = [low + (high - low) * unit(seed, arm, phrase, "delta") for phrase in range(4)]
                period = PERIODS[int(3 * unit(seed, arm, "all", "period")) % 3]
                rng = random.Random(f"rhythm-s2-phrase-eval:{seed}:{arm}:all:rng")
                result, truths = measure_fixture(period, deltas, rng)
                comp = errors(result, truths, "median_offset_ms_delay_compensated")
                raw = errors(result, truths, "median_offset_ms")
                primary += comp
                secondary += raw
                for entry, truth, error, delta in zip(result["phrases"], truths, comp, deltas):
                    within += error <= 5.0
                    estimate = entry["median_offset_ms_delay_compensated"]
                    correct = estimate is not None and (abs(estimate) <= 5.0 if arm == "on_time" else (estimate < 0) == (delta < 0))
                    sign_correct += bool(correct)
                    report["rows"].append({"seed": seed, "arm": arm, "phrase_id": entry["phrase_id"], "period": period,
                                           "delta_ms": delta * 1000, "truth_ms": truth * 1000, "status": entry["status"],
                                           "estimate_compensated_ms": estimate, "estimate_raw_ms": entry["median_offset_ms"],
                                           "abs_error_compensated_ms": None if math.isinf(error) else error,
                                           "click_reference": result["click_reference"]["basis"]})
            report["arms"][arm] = {"denominator": len(primary),
                                   "median_abs_error_ms_compensated": statistics.median(primary),
                                   "median_abs_error_ms_raw": statistics.median(secondary),
                                   "phrases_within_5_ms": within, "sign_correct_count": sign_correct}
        report["rhythm_sha256"] = rhythm.file_hash(ROOT / "scripts/rhythm.py")
        report["phrase_timing_sha256"] = rhythm.file_hash(ROOT / "scripts/phrase_timing.py")
        SEALED_DIR.mkdir(parents=True, exist_ok=True)
        (SEALED_DIR / f"p2-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report["arms"]))
        for arm in ("rushing", "dragging"):
            self.assertLessEqual(report["arms"][arm]["median_abs_error_ms_compensated"], 5.0, arm)


if __name__ == "__main__":
    unittest.main()
