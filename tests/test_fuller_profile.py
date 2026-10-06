"""FULLER-v1 profile template: exact accepted controls, filter-graph identity and refusals.

Fixture renders are synthetic measurements only. They prove the accepted chain
text and native-extent behaviour through scripts/media.py; they are not a
listening, real-take or tone claim. Spec: docs/spec/sprints/FULLER_S2.md.
"""
import array
import contextlib
import copy
import importlib.util
import io
import json
import math
import random
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("fuller_media_worker", REPO / "scripts" / "media.py")
media = importlib.util.module_from_spec(spec)
spec.loader.exec_module(media)
sys.path.insert(0, str(REPO / "scripts"))
import marked_compact as compact  # noqa: E402

PROFILE = REPO / "profiles" / "fuller.json"
FREEZE = REPO / "docs/agent-notes/sprints/20261006-s2/fuller_profile-phase1-freeze.json"
CONSERVATIVE3_SHA256 = "28bd2cf6aa9307776003d01b750860555659934261bcdaa9013eeb130d70fbbd"
CAPTURE_KEYS = ("noise_capture_seconds", "noise_capture_authorized", "noise_capture_review",
                "noise_capture_source_sha256")
FORBIDDEN = ("highpass", "lowpass", "bandreject", "bandpass", "notch", "anequalizer", "lowshelf",
             "bass=", "allpass", "firequalizer")
FIXTURE_RATE = 44100
FIXTURE_COUNT = 3 * FIXTURE_RATE + 137
FIXTURE_INTERVAL = (0.2, 1.05)
C1_HZ = 32.703
REVIEW = "Synthetic fixture interval [0.2, 1.05) s contains generated fan only; not a real-take review."


def rq_m1_merged():
    """Root's RQ-M1 adds MediaError.code and per-take capture binding."""
    return hasattr(media.MediaError("probe"), "code") and hasattr(media, "bind_capture")


def template():
    return json.loads(PROFILE.read_text())


def bind(profile, interval, review, source_sha256):
    """Pre-merge materialization: remove the requirement, add the four capture keys."""
    bound = copy.deepcopy(profile)
    bound.pop("noise_capture_required")
    bound.update(noise_capture_seconds=list(interval), noise_capture_authorized=True,
                 noise_capture_review=review, noise_capture_source_sha256=source_sha256)
    return bound


def leaves(value, prefix=""):
    if isinstance(value, dict):
        for key in sorted(value):
            yield from leaves(value[key], f"{prefix}.{key}" if prefix else key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from leaves(item, f"{prefix}[{index}]")
    else:
        yield prefix, value


def post_text(profile):
    return ",".join(stage["filter"] for stage in media.post_denoise_filters(profile, FIXTURE_RATE))


class FullerProfileContractTests(unittest.TestCase):
    """Static measurements; no FFmpeg."""

    def setUp(self):
        self.profile = template()
        self.freeze = json.loads(FREEZE.read_text())["accepted_truth"]

    def test_nineteen_accepted_controls_equal_by_value_and_type(self):
        expected = dict(leaves(self.freeze["profile_controls"]))
        self.assertEqual(len(expected), 19)
        actual = dict(leaves({key: self.profile[key] for key in self.freeze["profile_controls"]}))
        self.assertEqual(set(actual), set(expected))
        matched = 0
        for key, value in expected.items():
            with self.subTest(control=key):
                self.assertEqual(actual[key], value)
                self.assertIs(type(actual[key]), type(value))
                matched += 1
        self.assertEqual(matched, 19)

    def test_capture_interval_is_required_and_never_baked_in(self):
        self.assertIs(self.profile["noise_capture_required"], True)
        for key in CAPTURE_KEYS:
            self.assertNotIn(key, self.profile)
        self.assertEqual(self.profile["name"], "fuller")
        self.assertLessEqual(len(self.profile["description"]), 2000)
        for phrase in ("not_performed", "not verified noise-only", "180810, 218295"):
            self.assertIn(phrase, self.profile["description"])

    def test_post_denoise_graph_is_exactly_the_accepted_p(self):
        self.assertEqual(post_text(self.profile), compact.ACCEPTED["P"])
        self.assertEqual(post_text(self.profile), self.freeze["filters"]["P_post"])
        media.validate_post_controls(self.profile)

    def test_latency_and_normalization_text_follow_json_types(self):
        # Formulae copied from media.clean/media.loudness; the fixture render
        # below proves the same strings from the worker itself.
        p = self.profile
        latency = (f"afftdn=nr={p['reduction_db']}:nf={p['noise_floor_db']}:tn=0:gs={p['gain_smooth']}"
                   f":ad={float(p['adaptivity']):.9g}")
        self.assertEqual(latency, self.freeze["filters"]["L_latency"])
        self.assertEqual(f"loudnorm=I={p['integrated_lufs']}:TP={p['true_peak_dbtp']}:LRA=50",
                         self.freeze["filters"]["N_prefix"])

    def test_no_forbidden_low_cut_or_notch_stage(self):
        self.assertEqual(self.profile["preserve_low_fundamental_hz"], 32)
        graph = ";".join([compact.ACCEPTED["L"], compact.ACCEPTED["C"], post_text(self.profile),
                          compact.ACCEPTED["N"]]).lower()
        for name in FORBIDDEN:
            self.assertNotIn(name, graph)
        self.assertEqual([stage["stage"] for stage in media.post_denoise_filters(self.profile, FIXTURE_RATE)],
                         ["peaking_eq_1", "peaking_eq_2", "rms_compressor"])
        self.assertTrue(all(band["gain_db"] > 0 for band in self.profile["peaking_eq"]))
        self.assertNotIn(2200.0, [band["frequency_hz"] for band in self.profile["peaking_eq"]])

    def test_template_at_accepted_binding_reproduces_c_byte_for_byte(self):
        built = compact.capture_template(180810, 218295, 6657385, 44100, 1102)
        self.assertEqual(built, self.freeze["filters"]["C_capture"])
        self.assertEqual(built.encode(), compact.ACCEPTED["C"].encode())
        self.assertEqual(compact.ACCEPTED["L"], self.freeze["filters"]["L_latency"])
        self.assertEqual(compact.ACCEPTED["N"], self.freeze["filters"]["N_prefix"])
        self.assertNotEqual(compact.capture_template(180810, 218296, 6657385, 44100, 1102), built)

    def test_conservative3_unchanged_loadable_and_fuller_is_default(self):
        path = REPO / "profiles" / "conservative3.json"
        self.assertEqual(media.sha256(path), CONSERVATIVE3_SHA256)
        self.assertEqual(media.load_profile(path)["name"], "conservative3")
        with patch.object(media, "clean", return_value={"status": "mock"}) as clean, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(media.main(["clean", "unused-input.wav"]), 0)
        self.assertEqual(clean.call_args.args[1], "fuller")
        with patch.object(media, "clean", return_value={"run_dir": "unused"}) as clean, \
                patch.object(media, "export", return_value={"status": "mock"}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(media.main(["demo", "unused-input.wav"]), 0)
        self.assertEqual(clean.call_args.args[1], "fuller")
        # conservative3 remains available when selected explicitly.
        with patch.object(media, "clean", return_value={"status": "mock"}) as clean, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(media.main(["clean", "unused-input.wav", "conservative3"]), 0)
        self.assertEqual(clean.call_args.args[1:], ("conservative3", None, None))
        with patch.object(media, "clean", return_value={"run_dir": "unused"}) as clean, \
                patch.object(media, "export", return_value={"status": "mock"}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(media.main(["demo", "unused-input.wav", "--profile", "conservative3"]), 0)
        self.assertEqual(clean.call_args.args[1], "conservative3")

    def test_raw_template_fails_closed_or_requires_interval(self):
        if rq_m1_merged():
            loaded = media.load_profile(PROFILE)
            self.assertIs(loaded["noise_capture_required"], True)
        else:
            with self.assertRaisesRegex(media.MediaError, "unsupported fields"):
                media.load_profile(PROFILE)


def fixture_values():
    """Frozen fixture (FULLER_S2.md section 6): fan throughout; C1 guitar from 1.2 s."""
    rate, rng = FIXTURE_RATE, random.Random(914)
    guitar_start, attack, burst = round(1.2 * rate), 2 * rate, round(.005 * rate)
    values = []
    for i in range(FIXTURE_COUNT):
        sample = .008 * rng.uniform(-1, 1) + .003 * math.sin(2 * math.pi * 240 * i / rate)
        if i >= guitar_start:
            sample += .22 * math.sin(2 * math.pi * C1_HZ * i / rate) + .06 * math.sin(2 * math.pi * 160 * i / rate)
        offset = i - attack
        if 0 <= offset < burst:
            sample += .6 * math.exp(-offset / (.002 * rate)) * math.cos(2 * math.pi * 2100 * offset / rate)
        values.append(sample)
    return values


class FixtureMixin:
    def setUp(self):
        try:
            media.executable("ffmpeg")
            media.executable("ffprobe")
        except media.MediaError as exc:
            self.skipTest(f"FFMPEG/FFPROBE required for fixture render: {exc}")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()
        handle = patch.object(media, "ROOT", self.directory)
        handle.start()
        self.addCleanup(handle.stop)
        self.source = self.directory / "fuller-fixture.wav"
        raw = array.array("h", (round(max(-.99, min(.99, value)) * 32767) for value in fixture_values()))
        with wave.open(str(self.source), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(FIXTURE_RATE)
            handle.writeframes(raw.tobytes())
        self.source_sha = media.sha256(self.source)

    def bound_path(self, interval=FIXTURE_INTERVAL, source_sha=None, name="bound.json"):
        path = self.directory / name
        path.write_text(json.dumps(bind(template(), interval, REVIEW, source_sha or self.source_sha)))
        return path

    def runs(self):
        root = self.directory / "artifacts" / "runs"
        return sorted(root.iterdir()) if root.is_dir() else []

    def samples(self, path):
        result = subprocess.run([media.executable("ffmpeg"), "-v", "error", "-nostdin", "-i", str(path),
                                 "-map", "0:a:0", "-c:a", "pcm_f32le", "-f", "f32le", "-"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=60)
        values = array.array("f")
        values.frombytes(result.stdout)
        if sys.byteorder != "little":
            values.byteswap()
        return values


class FullerFixtureRenderTests(FixtureMixin, unittest.TestCase):
    def test_bound_template_renders_accepted_chain_modulo_interval(self):
        manifest = media.clean(self.source, self.bound_path())
        chain = compact.extract_chain(manifest)
        # M2: L, P, N byte-equal with no substitution.
        self.assertEqual(chain["L"], compact.ACCEPTED["L"])
        self.assertEqual(chain["P"], compact.ACCEPTED["P"])
        self.assertEqual(chain["N_prefixes"], [compact.ACCEPTED["N"]])
        self.assertEqual(chain["N_count"], 6)
        capture = manifest["noise_capture"]
        self.assertEqual(capture["selected_samples"], [8820, 46305])
        self.assertEqual(capture["guard_samples"], 4410)
        self.assertEqual(capture["capture_stop_filter_seconds"], .85)
        delay = capture["filter_delay_samples_removed"]
        self.assertEqual(delay, 1102)
        self.assertEqual(manifest["dsp_latency"]["denoise"]["delay_samples"], 1102)
        self.assertEqual(manifest["dsp_latency"]["denoise"]["remaining_bulk_delay_samples"], 0)
        self.assertEqual(chain["C"], compact.capture_template(8820, 46305, FIXTURE_COUNT, FIXTURE_RATE, delay))
        # Measured afftdn band update for 1 of 1 channel.
        self.assertEqual(capture["profile_update_status"], "observed_ffmpeg_afftdn_band_profile_update")
        self.assertEqual(len(capture["captured_band_shape_db_per_channel"]), 1)
        self.assertEqual(len(capture["captured_band_shape_db_per_channel"][0]), 15)
        self.assertIs(capture["noise_only_verified_by_worker"], False)
        reference = {"sample_rate": FIXTURE_RATE, "channels": 1, "sample_count": FIXTURE_COUNT}
        self.assertEqual({key: manifest["pcm"][key] for key in reference}, reference)
        run = Path(manifest["run_dir"])
        self.assertEqual(set(manifest["outputs"].values()),
                         {"source.wav", "denoised.wav", "baseline.wav", "cleaned.wav", "residue.wav", "processed.wav"})
        for name in manifest["outputs"].values():
            with self.subTest(output=name):
                media.ensure_pcm_matches(run / name, reference)
        self.assertIs(manifest["frequency_preservation"]["high_pass_applied"], False)
        self.assertIs(manifest["frequency_preservation"]["hum_notches_applied"], False)
        # M4 synthetic measurement only: coherent C1 component in denoised.wav.
        denoised = self.samples(run / "denoised.wav")
        window = range(2 * FIXTURE_RATE, 3 * FIXTURE_RATE)
        component = 2 / FIXTURE_RATE * abs(sum(
            denoised[i] * complex(math.cos(2 * math.pi * C1_HZ * i / FIXTURE_RATE),
                                  -math.sin(2 * math.pi * C1_HZ * i / FIXTURE_RATE)) for i in window))
        self.assertGreaterEqual(component, .9 * .22, f"C1 component {component:.4f}")
        self.assertEqual(media.sha256(self.source), self.source_sha)
        identity = compact.chain_identity(manifest, manifest["output_sha256"]["cleaned.wav"])
        self.assertEqual(identity["chain_class"], "fuller_v1_template_other_binding")
        self.assertEqual(identity["listening_acceptance"], "not_performed")
        self.assertEqual(identity["accepted_audio_identity"], "not_compared")

    def test_pre_merge_refusal_classes_leave_no_run_or_staging(self):
        with self.assertRaisesRegex(media.MediaError, "beyond decoded audio|outside decoded audio"):
            media.clean(self.source, self.bound_path((2.5, 3.4), name="outside.json"))
        self.assertEqual(self.runs(), [])
        with self.assertRaisesRegex(media.MediaError, "source SHA-256 differs"):
            media.clean(self.source, self.bound_path(source_sha="f" * 64, name="wrong-source.json"))
        self.assertEqual(self.runs(), [])
        unbound = bind(template(), FIXTURE_INTERVAL, REVIEW, self.source_sha)
        unbound.pop("noise_capture_seconds")
        path = self.directory / "metadata-only.json"
        path.write_text(json.dumps(unbound))
        with self.assertRaisesRegex(media.MediaError, "requires an interval"):
            media.load_profile(path)
        with self.assertRaises(media.MediaError):
            media.clean(self.source, path)
        self.assertEqual(self.runs(), [])
        if rq_m1_merged():
            with self.assertRaises(media.MediaError) as caught:
                media.clean(self.source, PROFILE)
            self.assertEqual(caught.exception.code, "capture_interval_required")
        else:
            with self.assertRaisesRegex(media.MediaError, "unsupported fields"):
                media.clean(self.source, PROFILE)
        self.assertEqual(self.runs(), [])
        self.assertEqual(media.sha256(self.source), self.source_sha)


class FullerTypedRefusalTests(FixtureMixin, unittest.TestCase):
    """RQ-M1 (root-applied). Skips only while MediaError lacks ``code``."""

    def setUp(self):
        if not rq_m1_merged():
            self.skipTest("requires root RQ-M1")
        super().setUp()

    def cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = media.main(argv)
        return code, out.getvalue(), err.getvalue()

    def argv(self, command, profile, extra=()):
        if command == "clean":
            return ["clean", str(self.source), str(profile), *extra]
        return ["demo", str(self.source), "--profile", str(profile), *extra]

    def test_eight_cli_refusals_carry_typed_reason_and_leave_no_run(self):
        wrong = self.bound_path(source_sha="e" * 64, name="wrong-source.json")
        cases = {"capture_interval_required": (PROFILE, ()),
                 "capture_review_required": (PROFILE, ("--capture-interval", "0.2", "1.05")),
                 "capture_interval_outside_source": (PROFILE, ("--capture-interval", "2.5", "3.4",
                                                               "--capture-review", REVIEW)),
                 "capture_source_mismatch": (wrong, ())}
        observed = 0
        for command in ("clean", "demo"):
            for reason, (profile, extra) in cases.items():
                with self.subTest(command=command, reason=reason):
                    code, _, err = self.cli(self.argv(command, profile, extra))
                    self.assertEqual(code, 1)
                    payload = json.loads(err)
                    self.assertEqual(payload["status"], "error")
                    self.assertEqual(payload["reason"], reason)
                    self.assertEqual(self.runs(), [])
                    observed += 1
        self.assertEqual(observed, 8)
        self.assertEqual(media.sha256(self.source), self.source_sha)

    def test_default_profile_refuses_without_interval_with_actionable_reason(self):
        profiles = self.directory / "profiles"
        profiles.mkdir(exist_ok=True)
        (profiles / "fuller.json").write_bytes(PROFILE.read_bytes())
        for argv in (["clean", str(self.source)], ["demo", str(self.source)]):
            with self.subTest(command=argv[0]):
                code, out, err = self.cli(argv)
                payload = json.loads(err)
                self.assertEqual((code, out, payload["reason"]), (1, "", "capture_interval_required"))
                self.assertIn("--capture-interval START END", payload["error"])
                self.assertIn("conservative3", payload["error"])
                self.assertEqual(self.runs(), [])
        self.assertEqual(media.sha256(self.source), self.source_sha)

    def test_invalid_and_conflicting_intervals_refuse_before_decode(self):
        for extra, reason in ((("--capture-interval", "1.0", "1.05", "--capture-review", REVIEW), "capture_interval_invalid"),
                              (("--capture-interval", "-0.1", "0.5", "--capture-review", REVIEW), "capture_interval_invalid"),
                              (("--capture-interval", "nan", "0.5", "--capture-review", REVIEW), "capture_interval_invalid")):
            with self.subTest(extra=extra):
                code, _, err = self.cli(self.argv("clean", PROFILE, extra))
                self.assertEqual((code, json.loads(err)["reason"]), (1, reason))
        bound = self.bound_path()
        code, _, err = self.cli(self.argv("clean", bound, ("--capture-interval", "0.2", "1.05",
                                                          "--capture-review", REVIEW)))
        self.assertEqual((code, json.loads(err)["reason"]), (1, "capture_interval_conflict"))
        self.assertEqual(self.runs(), [])

    def test_cli_binding_renders_the_same_capture_graph_as_materialized_profile(self):
        materialized = media.clean(self.source, self.bound_path())
        code, out, _ = self.cli(self.argv("clean", PROFILE, ("--capture-interval", "0.2", "1.05",
                                                             "--capture-review", REVIEW)))
        self.assertEqual(code, 0)
        cli = json.loads(out)
        self.assertEqual(compact.extract_chain(cli)["C"], compact.extract_chain(materialized)["C"])
        self.assertEqual(compact.extract_chain(cli)["C"],
                         compact.capture_template(8820, 46305, FIXTURE_COUNT, FIXTURE_RATE, 1102))
        self.assertEqual(cli["noise_capture"]["source_sha256"], self.source_sha)
        self.assertEqual(cli["profile"]["noise_capture_review"], REVIEW)
        self.assertNotIn("noise_capture_required", cli["profile"])
        self.assertEqual(cli["output_sha256"]["denoised.wav"], materialized["output_sha256"]["denoised.wav"])


if __name__ == "__main__":
    unittest.main()
