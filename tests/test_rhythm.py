import importlib.util
import contextlib
import hashlib
import io
import json
import math
import os
import statistics
import time
import random
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("rhythm", Path(__file__).resolve().parents[1] / "scripts/rhythm.py")
rhythm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rhythm)


def clicks(bpm=90, seconds=14, phase=.2):
    samples = [0.0] * round(seconds * rhythm.RATE)
    time = phase
    while time < seconds - .02:
        start = round(time * rhythm.RATE)
        for j in range(120):
            samples[start + j] += .5 * math.sin(2 * math.pi * 3500 * j / rhythm.RATE) * math.exp(-j / 25)
        time += 60 / bpm
    return samples


class RhythmTests(unittest.TestCase):
    def test_known_click_grid_and_timeline(self):
        result = rhythm.analyze(clicks(), source_start=12.5)
        grid = result["click_grid"]
        self.assertIsNotNone(grid)
        self.assertAlmostEqual(grid["bpm"], 90, delta=.5)
        self.assertLess(grid["median_absolute_residual_ms"], 5)
        for event in result["events"]:
            self.assertAlmostEqual(event["source_timeline_seconds"], event["audio_relative_seconds"] + 12.5)
        self.assertEqual(result["performance"]["status"], "not_graded")
        self.assertIsNone(result["meter"]["time_signature"])

    def test_silence_abstains(self):
        result = rhythm.analyze([0.0] * rhythm.RATE * 3)
        self.assertEqual(result["tempo_candidates"], [])
        self.assertIsNone(result["click_grid"])
        self.assertEqual(result["events"], [])

    def test_steady_tone_has_no_confirmed_click(self):
        samples = [math.sin(2 * math.pi * 500 * i / rhythm.RATE) * .1 for i in range(rhythm.RATE * 3)]
        result = rhythm.analyze(samples)
        self.assertIsNone(result["click_grid"])

    def test_half_double_ambiguity_retained(self):
        result = rhythm.analyze(clicks(bpm=180))
        bpms = [x["bpm"] for x in result["tempo_candidates"]]
        self.assertTrue(any(abs(x - 180) < 2 for x in bpms))
        self.assertTrue(any(abs(x - 90) < 2 for x in bpms))

    def test_offset_signs(self):
        grid = {"phase_seconds_audio_relative": .1, "period_seconds": .5}
        self.assertAlmostEqual(rhythm.grid_offset(1.08, grid)[1], -20)
        self.assertAlmostEqual(rhythm.grid_offset(1.12, grid)[1], 20)

    def test_noise_without_periodicity_abstains(self):
        generator = random.Random(204)
        samples = [generator.uniform(-.02, .02) for _ in range(rhythm.RATE * 4)]
        result = rhythm.analyze(samples)
        self.assertIsNone(result["click_grid"])
        self.assertEqual(result["performance"]["status"], "not_graded")

    def test_missing_click_is_not_performance_error(self):
        samples = clicks()
        center = round((.2 + 4 * (60 / 90)) * rhythm.RATE)
        samples[center:center + 120] = [0.0] * 120
        result = rhythm.analyze(samples)
        self.assertAlmostEqual(result["click_grid"]["bpm"], 90, delta=.5)
        self.assertLess(result["click_grid"]["candidate_coverage"], 1)
        self.assertEqual(result["performance"]["status"], "not_graded")

    def test_declared_178_kept_separate_from_audio_periodicity(self):
        result = rhythm.analyze(clicks(bpm=178), bpm=178)
        self.assertEqual(result["declared_tempo"]["bpm"], 178)
        self.assertEqual(result["declared_tempo"]["precision"], "approximate")
        self.assertEqual(result["click_grid"]["tempo_seed_bpm"], 178)
        self.assertAlmostEqual(result["click_grid"]["bpm"], 178, delta=1)
        self.assertEqual(result["performance"]["status"], "not_graded")

    def test_failed_approximate_double_seed_falls_back_without_overwriting_declaration(self):
        # A long 90 BPM train makes the approximate doubled 178 seed drift through
        # different phase neighborhoods; its fit abstains, while the real 90 train fits.
        result = rhythm.analyze(clicks(bpm=90, seconds=40), bpm=178)
        self.assertEqual(result["declared_tempo"]["bpm"], 178)
        self.assertEqual(result["grid_fit_attempts"][0]["status"], "no_stable_observed_fit")
        self.assertEqual(result["grid_fit_attempts"][0]["seed_bpm"], 178)
        self.assertEqual(result["grid_fit_attempts"][1]["status"], "observed_fit")
        self.assertAlmostEqual(result["click_grid"]["bpm"], 90, delta=.5)
        self.assertEqual(result["click_grid"]["selection"], "audio_periodicity_fallback_after_declared_seed_fit_abstention")
        doubled = next(item for item in result["metrical_interpretations"] if item["pulse_multiplier"] == 2)
        self.assertAlmostEqual(doubled["bpm"], 180, delta=1)
        self.assertEqual(doubled["basis"], "observed_fitted_grid")
        self.assertEqual(result["subdivisions"]["status"], "automatic_candidates")

    def test_automatic_triplet_candidates_without_expected_pattern(self):
        grid = {"phase_seconds_audio_relative": .1, "period_seconds": .6}
        times = [.1 + i * .2 for i in range(60)]
        result = rhythm.subdivision_candidates(times, grid)
        self.assertEqual(result["status"], "automatic_candidates")
        triple = next(c for c in result["candidates"] if c["subdivisions_per_declared_or_fitted_pulse"] == 3)
        quarter = next(c for c in result["candidates"] if c["subdivisions_per_declared_or_fitted_pulse"] == 1)
        self.assertGreater(triple["within_tolerance_fraction"], quarter["within_tolerance_fraction"])
        self.assertEqual(triple["status"], "candidate_not_intended_rhythm")

    def test_optional_onset_timestamps_have_correct_sample_axis(self):
        optional = {"onsets": {"superflux": {"frames": [30], "audio_relative_seconds": [.15]}}, "features": {}}
        with patch.object(rhythm, "librosa_analysis", return_value=optional):
            result = rhythm.analyze(clicks(seconds=3), source_start=12.5, backend="librosa")
        event = next(event for event in result["events"] if event["kind"] == "superflux_attack_candidate")
        self.assertEqual(event["analysis_sample_position"], 2400)
        self.assertEqual(event["source_timeline_seconds"], 12.65)
        self.assertEqual(event["timestamp_convention"], "librosa_frame_time_center_compensated")

    @unittest.skipUnless(importlib.util.find_spec("librosa"), "optional librosa dependency absent")
    def test_actual_librosa_backend_has_two_onset_methods_and_features(self):
        result = rhythm.librosa_analysis(clicks(seconds=3))
        self.assertEqual(set(result["onsets"]), {"spectral_flux", "superflux"})
        self.assertTrue(result["onsets"]["superflux"]["frames"])
        self.assertEqual(len(result["features"]["mfcc"]), 13)
        self.assertEqual(len(result["features"]["chroma"]), 12)
        self.assertEqual(result["features"]["hop_samples"], 800)


class TimelineLineageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.run_dir = Path(self.directory.name)
        self.source = self.run_dir / "denoised.wav"
        self.source.write_bytes(b"test derivative content; decoding is mocked")
        self.input_hash = rhythm.file_hash(self.source)
        self.metadata = {"audio": {"start_time": "0", "codec_name": "pcm_f32le", "sample_rate": "16000",
                                   "channels": 1, "duration_ts": 48000, "time_base": "1/16000"}, "format": {}}
        self.manifest = {"run_id": "fixture", "source": {"sha256": "a" * 64, "path": "/original/take.mov"},
                         "output_sha256": {"denoised.wav": self.input_hash},
                         "timeline": {"audio_start_seconds": 12.75, "no_time_stretch": True},
                         "pcm": {"sample_rate": 16000, "channels": 1, "sample_count": 48000}}
        self.write_manifest()

    def write_manifest(self):
        (self.run_dir / "manifest.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_hash_bound_pcm_restores_nonzero_original_origin(self):
        start, lineage = rhythm.input_timeline(self.source, self.input_hash, self.metadata, self.run_dir)
        self.assertEqual(start, 12.75)
        self.assertEqual(lineage["analyzed_input_sha256"], self.input_hash)
        self.assertEqual(lineage["original_source_sha256"], "a" * 64)
        self.assertTrue(lineage["timeline_rebased"])
        self.assertEqual(lineage["sample_mapping"]["original_samples_per_analysis_frame"], "80")

    def test_hash_mismatch_rejected_without_rebase(self):
        with self.assertRaisesRegex(ValueError, "hash does not match"):
            rhythm.input_timeline(self.source, "b" * 64, self.metadata, self.run_dir)

    def test_extent_mismatch_and_stretch_rejected(self):
        self.manifest["pcm"]["sample_count"] += 1
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "count differs"):
            rhythm.input_timeline(self.source, self.input_hash, self.metadata, self.run_dir)
        self.manifest["pcm"]["sample_count"] -= 1
        self.manifest["timeline"]["no_time_stretch"] = False
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "unchanged time scale"):
            rhythm.input_timeline(self.source, self.input_hash, self.metadata, self.run_dir)

    def test_unrelated_input_keeps_its_origin_explicitly(self):
        unrelated = self.run_dir / "other.mov"
        start, lineage = rhythm.input_timeline(unrelated, "c" * 64, self.metadata, self.run_dir)
        self.assertEqual(start, 0)
        self.assertEqual(lineage["status"], "input_not_manifest_derivative")
        self.assertFalse(lineage["timeline_rebased"])

    def test_cli_publishes_actual_input_identity_and_original_event_axis(self):
        with patch.object(rhythm, "probe", return_value=self.metadata), \
                patch.object(rhythm, "decode", return_value=clicks(seconds=3)), \
                patch("sys.argv", ["rhythm.py", str(self.source), "--run-dir", str(self.run_dir)]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rhythm.main(), 0)
        result = json.loads((self.run_dir / "analysis.json").read_text())
        self.assertEqual(result["source"]["sha256"], self.input_hash)
        self.assertEqual(result["source"]["path"], str(self.source.resolve()))
        self.assertEqual(result["timeline"]["audio_stream_start_seconds"], 12.75)
        self.assertTrue(result["events"])
        for event in result["events"]:
            self.assertAlmostEqual(event["source_timeline_seconds"], event["audio_relative_seconds"] + 12.75)


# ---- S2 rhythm_clicks additions (contract docs/spec/sprints/RHYTHM_S2.md) ----

TUNING_MIDI = (24, 29, 34, 39, 46, 51, 56, 60, 65)
OLD_EVENT_KEYS = ("kind", "analysis_frame", "beat_index", "audio_relative_seconds", "grid_offset_ms",
                  "source_timeline_seconds", "analysis_sample_position", "timestamp_convention", "confidence_label")
FORBIDDEN_TOKENS = ("missed", "extra_note", "wrong_note", "mistake", "error_verdict")
SEALED_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "s2" / "rhythm_clicks" / "sealed"


def scan_tokens(value, path="$"):
    """Recursive key and string-value scan for forbidden verdict tokens."""
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


def event_digest(result):
    rows = [[event.get(key) for key in OLD_EVENT_KEYS] for event in result["events"]]
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(), len(rows)


def drift_clicks(bpm, drift_fraction, *, seconds=10, phase=.3, click_amplitude=.09, noise_amplitude=.012,
                 noise_coefficient=.7, note_index=0, noise_seed=1):
    """16 kHz holdout-law click train IOI=(60/BPM)*(1+f*t/10) over noise and sustained distorted tuning notes."""
    rate = rhythm.RATE
    count = round(seconds * rate)
    samples = [0.0] * count
    generator = random.Random(noise_seed)
    colored = 0.0
    for index in range(count):
        white = generator.uniform(-1, 1)
        colored = noise_coefficient * colored + (1 - noise_coefficient) * white
        samples[index] = noise_amplitude * (.5 * white + .5 * colored)
    for order, start in enumerate((.9, 3.4, 5.9, 8.4)):
        if start >= seconds:
            break
        midi = TUNING_MIDI[(note_index + order) % len(TUNING_MIDI)]
        frequency = 440 * 2 ** ((midi - 69) / 12)
        first = round(start * rate)
        for j in range(min(round(1.6 * rate), count - first)):
            age = j / rate
            samples[first + j] += .12 * min(1, age / .0015) * math.exp(-age / .8) * math.tanh(3 * math.sin(2 * math.pi * frequency * age))
    period = 60 / bpm
    time_point, onsets = phase, []
    while time_point + .009 < seconds:
        first = round(time_point * rate)
        onsets.append(first / rate)
        for j in range(round(.009 * rate)):
            age = j / rate
            samples[first + j] += click_amplitude * math.exp(-age / .0018) * math.sin(2 * math.pi * 3500 * age)
        time_point += period * (1 + drift_fraction * time_point / 10)
    return samples, period * drift_fraction / 10, onsets


def drift_truth_ppm(bpm, rate, reference_time):
    return 1e6 * rate / (60 / bpm + rate * reference_time)


def decimate_48k(samples):
    """3-sample centered boxcar mean, then every third sample (about 0.94 gain at 3.5 kHz)."""
    out = []
    for index in range(0, len(samples), 3):
        window = samples[max(0, index - 1):index + 2]
        out.append(sum(window) / len(window))
    return out


def sealed_unit(seed, knob):
    return int.from_bytes(hashlib.sha256(f"rhythm-s2-drift-eval:{seed}:{knob}".encode()).digest()[:8], "big") / 2**64


class DriftModelTests(unittest.TestCase):
    def assert_null_estimates(self, drift):
        for field in rhythm.DRIFT_ESTIMATE_FIELDS:
            self.assertIsNone(drift[field], field)
        self.assertEqual(drift["confidence_label"], "not_estimated")

    def test_d1_constant_grids_report_no_material_drift(self):
        for bpm, seconds in ((90, 14), (178, 14), (88.8, 60)):
            with self.subTest(bpm=bpm, seconds=seconds):
                result = rhythm.analyze(clicks(bpm=bpm, seconds=seconds))
                drift = result["click_grid_drift"]
                self.assertEqual(drift["status"], "fitted")
                self.assertLessEqual(abs(drift["drift_ppm"]), 250)
                self.assertLessEqual(abs(drift["period_change_per_second"]), 2e-4)
                self.assertEqual(drift["model"], "linear_period")
                self.assertIs(result["click_grid"]["drift"], drift)
                self.assertEqual(drift["confidence_kind"], "heuristic_not_probability")
                self.assertEqual(drift["identity"], "periodic_high_frequency_transients_not_verified_metronome")
                # The selected pulse is the generated click period, whichever divisor of the seed reached it.
                self.assertAlmostEqual(drift["period_at_reference_seconds"], 60 / bpm, delta=.002)

    def test_d2_dev_drift_grid_recovered_within_ten_percent(self):
        for fraction in (.04, .08, .12):
            for bpm in (150, 185, 220):
                with self.subTest(fraction=fraction, bpm=bpm):
                    samples, rate, _ = drift_clicks(bpm, fraction, note_index=bpm % 9, noise_seed=bpm)
                    drift = rhythm.analyze(samples)["click_grid_drift"]
                    self.assertEqual(drift["status"], "fitted")
                    truth = drift_truth_ppm(bpm, rate, drift["reference_time_seconds_audio_relative"])
                    self.assertLessEqual(abs(drift["drift_ppm"] - truth), .10 * abs(truth))
                    self.assertGreater(drift["constant_period_residual_ms_rms"], drift["residual_ms_rms"])
                    self.assertIn(drift["confidence_label"], ("strong_drift_evidence", "limited_drift_evidence"))

    def test_d4_five_clicks_and_silence_abstain_with_null_estimates(self):
        drift = rhythm.analyze(clicks(bpm=90, seconds=.2 + 4 * 60 / 90 + .1), bpm=90)["click_grid_drift"]
        self.assertEqual(drift["status"], "insufficient_events")
        self.assertLess(drift["retained_event_count"], 6)
        self.assert_null_estimates(drift)
        silent = rhythm.analyze([0.0] * rhythm.RATE * 3)
        self.assertEqual(silent["click_grid_drift"]["status"], "no_periodic_seed")
        self.assert_null_estimates(silent["click_grid_drift"])
        self.assertIsNone(silent["click_grid"])

    def test_drift_model_positions_follow_holdout_law_and_invert(self):
        parameters = {"anchor_click_seconds_audio_relative": .3, "ioi_intercept_seconds_at_audio_time_zero": .4,
                      "period_change_per_second": .004}
        time_point, expected = .3, []
        for _ in range(20):
            expected.append(time_point)
            time_point += .4 + .004 * time_point
        for beat, value in enumerate(expected):
            self.assertAlmostEqual(rhythm.drift_click_time(parameters, beat), value, places=9)
            self.assertAlmostEqual(rhythm.drift_beat_position(parameters, value), beat, places=6)
        parameters["period_change_per_second"] = 0.0
        self.assertAlmostEqual(rhythm.drift_click_time(parameters, 5), .3 + 5 * .4)

    def test_holdout_render_path_with_fabricated_dev_parameters(self):
        """Exercise render_timing_case plumbing without the withheld seed211/seed307 parameters."""
        holdout = load_holdout()
        parameters = {"first_motif_start_seconds": .7, "motif_duration_seconds": 1.2, "motif_gap_seconds": 2.2,
                      "guitar_gain": .8, "distortion_drive": 3.2, "noise_amplitude": .01, "noise_lowpass_coefficient": .7,
                      "click_amplitude": .09, "click_bpm": 170.0, "click_phase_seconds": .3, "click_drift_fraction": .06,
                      "motif_subdivision_denominator": 5, "noise_stream_seed": 123456789}
        drift, truth = holdout_drift({"id": "dev-fabricated-timing-reference", "cohort": "timing-reference",
                                      "duration_seconds": 10, "parameters": parameters}, holdout)
        self.assertEqual(drift["status"], "fitted")
        self.assertLessEqual(abs(drift["drift_ppm"] - truth), .10 * abs(truth))

    @unittest.skipUnless(os.environ.get("RHYTHM_S2_SEALED_EVAL") == "1", "sealed D3 evaluation runs once after the eval receipt")
    def test_d3_sealed_holdout_drift_eval(self):
        holdout = load_holdout()
        rows = []
        for seed in (211, 307):
            case = {"id": f"seed{seed}-timing-reference", "cohort": "timing-reference", "duration_seconds": 10,
                    "parameters": holdout.parameters(seed, "timing-reference")}
            drift, truth = holdout_drift(case, holdout)
            rows.append(sealed_row(f"holdout-seed{seed}", drift, truth, case["parameters"]["click_bpm"],
                                   case["parameters"]["click_drift_fraction"]))
        for seed in range(9101, 9109):
            fraction = .04 + .08 * sealed_unit(seed, "f")
            bpm = 80 + 140 * sealed_unit(seed, "bpm")
            samples, rate, _ = drift_clicks(
                bpm, fraction, phase=.2 + .3 * sealed_unit(seed, "phase"),
                click_amplitude=.06 + .06 * sealed_unit(seed, "click_amplitude"),
                noise_amplitude=.008 + .008 * sealed_unit(seed, "noise_amplitude"),
                noise_coefficient=.55 + .30 * sealed_unit(seed, "noise_color"),
                note_index=int(9 * sealed_unit(seed, "note")) % 9,
                noise_seed=int.from_bytes(hashlib.sha256(f"rhythm-s2-drift-eval:{seed}:noise_stream".encode()).digest()[:8], "big"))
            drift = rhythm.analyze(samples)["click_grid_drift"]
            truth = drift_truth_ppm(bpm, rate, drift["reference_time_seconds_audio_relative"]) if drift["status"] == "fitted" else None
            rows.append(sealed_row(f"generated-seed{seed}", drift, truth, bpm, fraction))
        passed = sum(row["within_10_percent"] for row in rows)
        report = {"metric": "D3", "denominator": len(rows), "within_10_percent_count": passed, "rows": rows,
                  "rhythm_sha256": rhythm.file_hash(Path(rhythm.__file__)), "claim_class": "M-syn"}
        SEALED_DIR.mkdir(parents=True, exist_ok=True)
        (SEALED_DIR / f"d3-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json").write_text(json.dumps(report, indent=2))
        print(json.dumps({key: report[key] for key in ("metric", "denominator", "within_10_percent_count")}))
        self.assertEqual(len(rows), 10)
        self.assertEqual(passed, 10, "D3 failure is reported, not retuned")


def load_holdout():
    spec = importlib.util.spec_from_file_location("s2_holdout", Path(__file__).resolve().parents[1] / "scripts/benchmark_holdout.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def holdout_drift(case, holdout):
    signals, truth = holdout.render_timing_case(case, time.monotonic() + 120)
    samples = decimate_48k(signals["mix"])
    drift = rhythm.analyze(samples)["click_grid_drift"]
    parameters = case["parameters"]
    rate = (60 / parameters["click_bpm"]) * parameters["click_drift_fraction"] / 10
    expected = drift_truth_ppm(parameters["click_bpm"], rate, drift["reference_time_seconds_audio_relative"]) if drift["status"] == "fitted" else None
    return drift, expected


def sealed_row(case_id, drift, truth, bpm, fraction):
    fitted = drift["status"] == "fitted" and truth is not None
    relative = abs(drift["drift_ppm"] - truth) / abs(truth) if fitted else None
    return {"case": case_id, "bpm": bpm, "drift_fraction": fraction, "status": drift["status"],
            "drift_ppm": drift["drift_ppm"], "truth_drift_ppm": truth, "relative_error": relative,
            "within_10_percent": bool(fitted and relative <= .10), "pulse_divisor": drift["pulse_divisor"],
            "residual_ms_rms": drift["residual_ms_rms"], "confidence_label": drift["confidence_label"],
            "retained_event_count": drift["retained_event_count"]}


class DetectorDelayTests(unittest.TestCase):
    def test_c1_calibration_deterministic_and_complete(self):
        first = rhythm._calibrate_detector_delay()
        second = rhythm._calibrate_detector_delay()
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(rhythm.onset_detector_delay_calibration(), rhythm.onset_detector_delay_calibration())
        self.assertEqual(set(first["results"]), {"high_frequency_novelty", "broadband_rms_novelty"})
        for path, probes in first["results"].items():
            self.assertEqual(set(probes), {"unit_impulse", "click_3500hz_exp", "distorted_c1_attack"})
            for cell in probes.values():
                self.assertEqual(cell["probe_count"], 16)
                self.assertEqual(cell["detected_count"] + cell["undetected_count"], 16)
        self.assertEqual(first["sub_hop_offsets_samples"], list(range(0, 80, 5)))
        table = first["compensation_table"]
        self.assertIsNone(table["superflux_attack_candidate"])
        self.assertIsNone(table["spectral_flux_attack_candidate"])
        self.assertEqual(table["broadband_attack_candidate"]["probe"], "distorted_c1_attack")
        self.assertEqual(table["periodic_high_frequency_candidate"]["probe"], "click_3500hz_exp")

    def test_analysis_records_measured_delay_without_shifting_events(self):
        result = rhythm.analyze(clicks(), source_start=12.5)
        analysis = result["analysis"]
        self.assertEqual(analysis["onset_detector_delay_status"], "measured_on_synthetic_impulses_not_physical_av_offset")
        self.assertIs(analysis["onset_detector_delay_compensated"], False)
        self.assertEqual(analysis["physical_capture_latency"], "uncalibrated")
        cell = analysis["onset_detector_delay_calibration"]["results"]["broadband_rms_novelty"]["distorted_c1_attack"]
        self.assertGreaterEqual(cell["detected_count"], 12)
        self.assertEqual(analysis["onset_detector_delay_seconds"], cell["median_seconds"])
        table = analysis["onset_detector_delay_calibration"]["compensation_table"]
        for event in result["events"]:
            self.assertAlmostEqual(event["source_timeline_seconds"], event["audio_relative_seconds"] + 12.5)
            delay = table[event["kind"]]["delay_seconds"]
            self.assertAlmostEqual(event["delay_compensated_source_timeline_seconds"], event["source_timeline_seconds"] - delay)
            self.assertEqual(event["delay_compensation"], "synthetic_probe_median_subtracted")

    def test_librosa_kinds_stay_uncalibrated(self):
        optional = {"onsets": {"superflux": {"frames": [30], "audio_relative_seconds": [.15]}}, "features": {}}
        with patch.object(rhythm, "librosa_analysis", return_value=optional):
            result = rhythm.analyze(clicks(seconds=3), backend="librosa")
        event = next(event for event in result["events"] if event["kind"] == "superflux_attack_candidate")
        self.assertIsNone(event["delay_compensated_source_timeline_seconds"])
        self.assertEqual(event["delay_compensation"], "uncalibrated_path")
        self.assertEqual(event["source_timeline_seconds"], .15)

    def test_c2_existing_fixture_event_timestamps_unchanged(self):
        # Digests of all pre-change event fields, computed on commit 2d9eaa5 before any S2 edit.
        expected = {
            "default_90_start12.5": ("886f14bae583fb23da6c980a6406bcd6f4a97a0f43e491ddd2a4ef99f512144f", 42),
            "bpm180": ("c25db167ffe619c427350290c0817c8cadb78b7dbe82f470bf2abeefd208888b", 56),
            "bpm178_declared": ("90e41faff694767d56dbb03fcdb7436f01ed91282009dd4b47c621cf7e3c6b78", 82),
            "bpm90_40s_declared178": ("f28858bc9d6168fe8f7b72e0d2d4bbacf11bdabe49b17d63c41684301aedd226", 120),
            "missing_click": ("85ed2bb2c3605b51c0e274d0f92674de8dc2729d3ef1ca5cf60b1c50c1487417", 40)}
        missing = clicks()
        center = round((.2 + 4 * (60 / 90)) * rhythm.RATE)
        missing[center:center + 120] = [0.0] * 120
        cases = {"default_90_start12.5": (clicks(), {"source_start": 12.5}),
                 "bpm180": (clicks(bpm=180), {}),
                 "bpm178_declared": (clicks(bpm=178), {"bpm": 178}),
                 "bpm90_40s_declared178": (clicks(bpm=90, seconds=40), {"bpm": 178}),
                 "missing_click": (missing, {})}
        for name, (samples, options) in cases.items():
            with self.subTest(name=name):
                self.assertEqual(event_digest(rhythm.analyze(samples, **options)), expected[name])

    def test_c3_compensated_click_times_match_independent_fixture_onsets(self):
        result = rhythm.analyze(clicks(bpm=90, seconds=14, phase=.2))
        onsets, time_point = [], .2
        while time_point < 14 - .02:
            onsets.append(round(time_point * rhythm.RATE) / rhythm.RATE)
            time_point += 60 / 90
        raw, compensated = [], []
        for event in result["events"]:
            if event["kind"] != "periodic_high_frequency_candidate":
                continue
            nearest = min(onsets, key=lambda onset: abs(onset - event["audio_relative_seconds"]))
            raw.append(abs(event["source_timeline_seconds"] - nearest))
            compensated.append(abs(event["delay_compensated_source_timeline_seconds"] - nearest))
        self.assertGreaterEqual(len(compensated), 18)
        self.assertLessEqual(statistics.median(compensated), .0025)
        self.assertLessEqual(statistics.median(raw), .005)

    def test_new_outputs_have_no_verdict_tokens(self):
        result = rhythm.analyze(clicks())
        self.assertEqual(scan_tokens(result["click_grid_drift"]), [])
        self.assertEqual(scan_tokens(result["analysis"]), [])
        self.assertEqual(scan_tokens(result["events"]), [])


if __name__ == "__main__":
    unittest.main()
