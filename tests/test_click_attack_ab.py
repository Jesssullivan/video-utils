import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HAS_ANALYSIS = bool(importlib.util.find_spec("numpy") and importlib.util.find_spec("scipy")
                    and importlib.util.find_spec("threadpoolctl"))
FORBIDDEN_TOKENS = ("missed", "extra_note", "wrong_note", "mistake", "error_verdict")
SEALED_DIR = ROOT / "artifacts" / "s2" / "rhythm_clicks" / "sealed"

if HAS_ANALYSIS:
    SPEC = importlib.util.spec_from_file_location("click_attack_ab", ROOT / "scripts/click_attack_ab.py")
    ab = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(ab)


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


@unittest.skipUnless(HAS_ANALYSIS, "optional locked analysis dependencies absent")
class ClickAttackFixtureTests(unittest.TestCase):
    def test_fixture_geometry_and_low_register_content(self):
        import numpy as np
        isolated = ab.render_arm("isolated", 1, ab.NAMESPACES["dev"])
        coincident = ab.render_arm("coincident", 1, ab.NAMESPACES["dev"])
        self.assertTrue(all(attack["nearest_click_distance_ms"] >= 150 for attack in isolated["attacks"]))
        self.assertEqual({attack["delta_ms"] for attack in coincident["attacks"]}, set(ab.DELTAS_MS))
        self.assertTrue(all(attack["nearest_click_distance_ms"] <= 10 for attack in coincident["attacks"]))
        for fixture in (isolated, coincident):
            self.assertEqual(len(fixture["attacks"]), ab.ATTACKS_PER_ARM)
            self.assertTrue({attack["midi"] for attack in fixture["attacks"]} <= set(ab.NOTES))
            start, end = fixture["template_window"]
            self.assertAlmostEqual(end - start, .020)
            first_onset = min(attack["onset_sample"] for attack in fixture["attacks"]) / ab.RATE
            self.assertGreater(first_onset - end, .5, "template click must be isolated from guitar")
        midi24 = [attack for attack in isolated["attacks"] + coincident["attacks"] if attack["midi"] == 24]
        self.assertTrue(midi24, "32.70 Hz notes are part of the fixture")
        spectrum = np.abs(np.fft.rfft(isolated["clean_guitar"]))
        frequencies = np.fft.rfftfreq(len(isolated["clean_guitar"]), 1 / ab.RATE)
        band = (frequencies >= 28) & (frequencies <= 40)
        self.assertGreater(float(np.max(spectrum[band])), 0)

    def test_dev_ab_seed_counts_denominators_and_preservation(self):
        runs = {arm: [ab.run_arm(arm, 1, ab.NAMESPACES["dev"])] for arm in ("isolated", "coincident")}
        summaries = {arm: ab.summarize_arm(items) for arm, items in runs.items()}
        for arm, summary in summaries.items():
            with self.subTest(arm=arm):
                total = sum(summary[key] for key in ("attenuated_count", "abstained_count", "analyze_only_count",
                                                     "unmatched_generated_click_count"))
                self.assertEqual(total, summary["generated_click_count"])
                self.assertEqual(summary["attack_window_count"], ab.ATTACKS_PER_ARM)
                self.assertEqual(summary["windows_with_abs_energy_delta_over_0_5_db"]["denominator"], ab.ATTACKS_PER_ARM)
                self.assertEqual(summary["analyze_only_count"], 0)
                preservation = summary["frequency_preservation_per_seed"][0]
                self.assertLess(preservation["32_hz_complex_bin_relative_delta"], 1e-5)
                self.assertLess(preservation["28_80_hz_max_complex_bin_relative_delta"], 1e-5)
                self.assertEqual(scan_tokens({key: value for key, value in summary.items() if key != "windows"}), [])
        # A1 dev: isolated attacks are not touched by attenuation of distant clicks.
        self.assertEqual(summaries["isolated"]["windows_with_abs_energy_delta_over_0_5_db"]["count"], 0)
        # A2 dev direction (reported, not a release gate): overlap guard abstains more on coincident clicks.
        self.assertLess(summaries["coincident"]["attenuated_fraction"], summaries["isolated"]["attenuated_fraction"])
        coincident_hosts = {attack["host_click_sample"] for attack in runs["coincident"][0]["fixture"]["attacks"]}
        decisions = runs["coincident"][0]["decisions"]["decisions"]
        clicks = runs["coincident"][0]["fixture"]["click_samples"]
        host_decisions = [decision for sample, decision in zip(clicks, decisions) if sample in coincident_hosts]
        self.assertNotIn("attenuated", host_decisions)
        self.assertEqual(summaries["isolated"]["attack_proximal_clicks"]["denominator"], 0)
        self.assertEqual(summaries["coincident"]["attack_proximal_clicks"]["denominator"], ab.ATTACKS_PER_ARM)
        self.assertEqual(summaries["coincident"]["attack_proximal_clicks"]["decision_counts"]["attenuated"], 0)

    def test_real_take_block_is_detection_only(self):
        import numpy as np
        fixture = ab.render_arm("isolated", 2, ab.NAMESPACES["dev"])
        pcm = fixture["mix"][:, None]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "denoised.wav"
            source.write_bytes(b"real-take stand-in; decoder mocked")
            digest = ab.clicks.rhythm.file_hash(source)
            onsets = [attack["onset_sample"] / ab.RATE for attack in fixture["attacks"]]
            first_click = fixture["click_samples"][2] / ab.RATE
            analysis = {"source": {"sha256": digest}, "declared_tempo": None,
                        "events": [{"kind": "broadband_attack_candidate", "audio_relative_seconds": value}
                                   for value in onsets + [first_click + .004]]}
            analysis_path = root / "analysis.json"
            analysis_path.write_text(json.dumps(analysis))
            metadata = {"audio": {"sample_rate": "48000", "channels": 1, "duration": str(len(pcm) / ab.RATE)}, "format": {}}
            with patch.object(ab.clicks.rhythm, "probe", return_value=metadata), \
                    patch.object(ab.clicks, "decode_native", return_value=(pcm, ab.RATE)):
                block = ab.real_take(source, analysis_path)
            self.assertEqual(block["attenuation_claim"], "none_detection_only")
            self.assertFalse(block["audio_written"])
            self.assertEqual(block["coincident_candidate_count"] + block["isolated_candidate_count"], block["candidate_count"])
            self.assertGreaterEqual(block["coincident_candidate_count"], 1)
            self.assertEqual(list(root.glob("*.wav")), [source])
            self.assertEqual(scan_tokens(block), [])
            analysis["source"]["sha256"] = "0" * 64
            analysis_path.write_text(json.dumps(analysis))
            with self.assertRaisesRegex(ValueError, "not bound"):
                ab.real_take(source, analysis_path)
        self.assertTrue(np.isfinite(pcm).all())

    def test_cli_refuses_unsealed_eval_and_accepted_run_output(self):
        with patch.dict(os.environ, {"CLICK_AB_S2_SEALED_EVAL": ""}), \
                patch("sys.argv", ["click_attack_ab.py", "--seed-set", "eval"]), \
                contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(ab.main(), 1)
        self.assertIn("CLICK_AB_S2_SEALED_EVAL", error.getvalue())
        with tempfile.TemporaryDirectory() as directory, \
                patch("sys.argv", ["click_attack_ab.py", "--skip-synthetic", "--output-root",
                                   str(Path(directory) / "artifacts" / "runs" / "x")]), \
                contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(ab.main(), 1)
        self.assertIn("accepted run", error.getvalue())

    def test_cli_output_fixed_fields(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("sys.argv", ["click_attack_ab.py", "--skip-synthetic", "--output-root", directory]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ab.main(), 0)
            result = json.loads(next(Path(directory).glob("*/click_attack_ab.json")).read_text())
        for key, value in {"click_identity": "unverified", "listening_ab": "not_performed",
                           "physical_capture_latency": "uncalibrated", "status": "experimental_synthetic_ab",
                           "tool": "click_attack_ab"}.items():
            self.assertEqual(result[key], value)
        self.assertEqual(result["real_take"], {"status": "not_requested"})
        self.assertEqual(scan_tokens(result), [])

    @unittest.skipUnless(os.environ.get("CLICK_AB_S2_SEALED_EVAL") == "1", "sealed A/B evaluation runs once after the eval receipt")
    def test_sealed_ab_eval(self):
        result = ab.synthetic("eval")
        report = {"metric": "A1-A3", "seeds": result["seeds"], "comparison": result["comparison"],
                  "arms": {arm: {key: value for key, value in data.items() if key != "windows"} for arm, data in result["arms"].items()},
                  "click_attack_ab_sha256": ab.clicks.rhythm.file_hash(ROOT / "scripts/click_attack_ab.py")}
        SEALED_DIR.mkdir(parents=True, exist_ok=True)
        (SEALED_DIR / f"ab-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report["comparison"]))
        for arm in ("isolated", "coincident"):
            data = result["arms"][arm]
            self.assertEqual(data["attack_window_count"], 4 * ab.ATTACKS_PER_ARM)
            self.assertEqual(sum(data[key] for key in ("attenuated_count", "abstained_count", "analyze_only_count",
                                                       "unmatched_generated_click_count")), data["generated_click_count"])


if __name__ == "__main__":
    unittest.main()
