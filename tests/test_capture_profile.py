"""Source-bound capture authoring fixtures; no decoded or processed audio is created."""
import array
import contextlib
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import shutil
import signal
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import wave

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("capture_profile_worker", REPO / "scripts" / "capture_profile.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, allow_nan=True), encoding="utf-8")


class CaptureProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.root_patch = patch.object(capture, "ROOT", self.root)
        self.root_patch.start()
        (self.root / "program").mkdir()
        for name in ("instrument.json", "capture-context.json"):
            shutil.copyfile(REPO / "program" / name, self.root / "program" / name)
        self.run = self.root / "artifacts" / "runs" / "baseline-fixture"
        self.run.mkdir(parents=True)
        self.source = self.root / "recorded mixed guitar and fan.wav"
        self.rate, self.count = 16000, 32000
        values = array.array("h", (int(1500 * math.sin(2 * math.pi * 32 * i / self.rate)
                                       + 200 * math.sin(2 * math.pi * 103 * i / self.rate))
                                  for i in range(self.count)))
        with wave.open(str(self.source), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(self.rate)
            handle.writeframes(values.tobytes())
        self.pcm = self.run / "source.wav"
        shutil.copyfile(self.source, self.pcm)
        self.manifest_path = self.run / "manifest.json"
        self.manifest = {
            "schema_version": 1,
            "source": {"path": str(self.source), "sha256": sha(self.source)},
            "pcm": {"sample_rate": self.rate, "channels": 1, "sample_count": self.count},
            "outputs": {"source": "source.wav"},
            "output_sha256": {"source.wav": sha(self.pcm)},
            "timeline": {"audio_start_seconds": 7.125, "no_time_stretch": True},
        }
        dump(self.manifest_path, self.manifest)
        self.review_path = self.run / "capture-review.json"
        self.review = {
            "schema_version": 1,
            "source_sha256": sha(self.source),
            "source_run_manifest_sha256": sha(self.manifest_path),
            "source_pcm_sha256": sha(self.pcm),
            "start_seconds": 0.125,
            "end_seconds": 0.625,
            "time_axis": "decoded_source_audio_samples",
            "selected_by": "fixture selector",
            "reviewed_by": "fixture reviewer",
            "review_status": "reviewed_possible_contamination",
            "authorization_scope": "experimental_capture_render",
            "authorization_reference": "Test fixture scope; metadata authoring only in this test.",
            "music_status": "suspected",
            "click_status": "unknown",
            "ambient_music_status": "not_reported",
            "note": "Known generated mixture includes 32 Hz music; uncertainty must be retained.",
        }
        dump(self.review_path, self.review)
        self.controls = {
            "capture_start_seconds": 0.125,
            "capture_end_seconds": 0.625,
            "reduction_db": 8,
            "noise_floor_db": -40,
            "adaptivity": 0,
            "gain_smooth": 0,
            "integrated_lufs": -18,
            "true_peak_dbtp": -1.5,
        }

    def tearDown(self):
        self.root_patch.stop()
        self.temp.cleanup()

    def author(self, **changes):
        return capture.author(str(self.source), str(self.run), str(self.review_path),
                              **dict(self.controls, **changes))

    def cli_args(self, *extra):
        return [str(self.source), "--run-dir", str(self.run), "--review", str(self.review_path),
                "--capture-start", "0.125", "--capture-end", "0.625",
                "--reduction-db", "8", "--noise-floor-db", "-40",
                "--adaptivity", "0", "--gain-smooth", "0",
                "--integrated-lufs", "-18", "--true-peak-dbtp", "-1.5", *extra]

    def reviewed(self, **changes):
        self.review.update(changes)
        dump(self.review_path, self.review)

    def rebound_manifest(self, **changes):
        self.manifest.update(changes)
        dump(self.manifest_path, self.manifest)
        self.reviewed(source_run_manifest_sha256=sha(self.manifest_path))

    def replace_native_fixture(self, rate, channels, count):
        values = array.array("h", [0]) * (channels * count)
        for index in range(count):
            for channel in range(channels):
                values[index * channels + channel] = int(
                    1500 * math.sin(2 * math.pi * (32 + channel) * index / rate))
        with wave.open(str(self.source), "wb") as handle:
            handle.setnchannels(channels)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(values.tobytes())
        shutil.copyfile(self.source, self.pcm)
        self.manifest["source"]["sha256"] = sha(self.source)
        self.rebound_manifest(pcm={"sample_rate": rate, "channels": channels, "sample_count": count},
                              output_sha256={"source.wav": sha(self.pcm)})
        self.reviewed(source_sha256=sha(self.source), source_pcm_sha256=sha(self.pcm))

    def assert_no_published_profile(self):
        self.assertEqual(list(self.run.glob("capture-profiles/*/profile.json")), [])

    def test_authored_profile_is_source_bound_and_no_dsp_or_acceptance(self):
        before = {p: sha(p) for p in (self.source, self.pcm, self.manifest_path, self.review_path)}
        result = self.author()
        self.assertEqual(result["status"], "authored_unrendered")
        self.assertFalse(result["dsp_performed"])
        self.assertFalse(result["listening_accepted"])
        self.assertEqual(result["source_sha256"], sha(self.source))
        profile_path = Path(result["profile_path"])
        receipt_path = Path(result["receipt_path"])
        self.assertTrue(profile_path.is_relative_to(self.run / "capture-profiles"))
        self.assertEqual(sha(profile_path), result["profile_sha256"])
        self.assertEqual(sha(receipt_path), result["receipt_sha256"])
        profile = json.loads(profile_path.read_text())
        self.assertEqual(profile["noise_capture_source_sha256"], sha(self.source))
        self.assertTrue(profile["noise_capture_authorized"])
        self.assertEqual(profile["noise_capture_seconds"], [0.125, 0.625])
        self.assertEqual(profile["preserve_low_fundamental_hz"], 32)
        self.assertNotIn("peaking_eq", profile)
        self.assertNotIn("compressor", profile)
        receipt_text = receipt_path.read_text()
        self.assertIn("reviewed_possible_contamination", receipt_text)
        self.assertIn("suspected", receipt_text)
        for path, identity in before.items():
            self.assertEqual(sha(path), identity)
        self.assertEqual(list(self.run.rglob("*.wav")), [self.pcm])

    def test_repeated_authoring_retains_both_immutable_artifact_sets(self):
        first = self.author()
        first_profile = Path(first["profile_path"]).read_bytes()
        first_receipt = Path(first["receipt_path"]).read_bytes()
        second = self.author(reduction_db=12)
        self.assertNotEqual(first["output_dir"], second["output_dir"])
        self.assertEqual(Path(first["profile_path"]).read_bytes(), first_profile)
        self.assertEqual(Path(first["receipt_path"]).read_bytes(), first_receipt)
        self.assertEqual(len(list(self.run.glob("capture-profiles/*/profile.json"))), 2)

    def test_native_rounding_and_nonzero_media_origin(self):
        self.reviewed(start_seconds=0.125001, end_seconds=0.625001)
        result = self.author()
        self.assertEqual(result["capture"]["native_samples"], [2000, 10000])
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        # The original clock must retain its measured nonzero origin, while
        # the profile's capture remains decoded-audio relative.
        receipt_text = json.dumps(receipt)
        self.assertIn("7.125", receipt_text)
        self.assertIn("7.25", receipt_text)
        self.assertIn("7.75", receipt_text)

    def test_unverified_media_origin_remains_unknown(self):
        self.rebound_manifest(timeline={"audio_start_seconds": None, "no_time_stretch": True})
        result = self.author()
        receipt_text = Path(result["receipt_path"]).read_text()
        self.assertIn("null", receipt_text)
        self.assertEqual(result["capture"]["native_samples"], [2000, 10000])

    def test_profile_authoring_scope_cannot_escalate_to_render_authority(self):
        self.reviewed(authorization_scope="profile_authoring")
        result = self.author()
        self.assertEqual(result["status"], "draft_authorization_incomplete")
        self.assertIsNone(result["profile_path"])
        self.assertIsNone(result["profile_sha256"])
        self.assert_no_published_profile()
        proposals = list(self.run.glob("capture-profiles/*/proposal.json"))
        self.assertEqual(len(proposals), 1)
        self.assertFalse(json.loads(proposals[0].read_text()).get("noise_capture_authorized", False))

    def test_confirmed_capture_contamination_requires_reselection(self):
        cases = [{"review_status": "rejected_contaminated"},
                 {"music_status": "reviewed_present"},
                 {"click_status": "reviewed_present"}]
        for update in cases:
            with self.subTest(update=update):
                previous = dict(self.review)
                self.reviewed(**update)
                result = self.author()
                self.assertEqual(result["status"], "needs_reselection")
                self.assertIsNone(result["profile_path"])
                self.assert_no_published_profile()
                self.review = previous
                dump(self.review_path, self.review)

    def test_source_hash_transplant_and_stale_review_bindings_rejected(self):
        for field in ("source_sha256", "source_run_manifest_sha256", "source_pcm_sha256"):
            with self.subTest(field=field):
                original = self.review[field]
                self.reviewed(**{field: "f" * 64})
                with self.assertRaises(capture.CaptureError):
                    self.author()
                self.assert_no_published_profile()
                self.reviewed(**{field: original})
        self.manifest["source"]["sha256"] = "a" * 64
        self.rebound_manifest()
        with self.assertRaises(capture.CaptureError):
            self.author()
        self.assert_no_published_profile()

    def test_baseline_original_path_cannot_be_replaced_by_same_content_alias(self):
        alias = self.root / "same bytes different recording.wav"
        shutil.copyfile(self.source, alias)
        self.manifest["source"]["path"] = str(alias)
        self.rebound_manifest()
        with self.assertRaises(capture.CaptureError):
            self.author()
        self.assert_no_published_profile()

    def test_review_interval_and_time_axis_must_match_native_source(self):
        for change in ({"start_seconds": 0.126}, {"time_axis": "video_time"},
                       {"schema_version": True}, {"unknown_filter": "highpass=80"},
                       {"authorization_reference": " "}, {"note": ""}):
            with self.subTest(change=change):
                previous = dict(self.review)
                self.reviewed(**change)
                with self.assertRaises(capture.CaptureError):
                    self.author()
                self.assert_no_published_profile()
                self.review = previous
                dump(self.review_path, self.review)

    def test_manifest_extent_rate_channel_and_no_stretch_truth_checked(self):
        cases = [dict(self.manifest["pcm"], sample_count=self.count + 1),
                 dict(self.manifest["pcm"], sample_rate=48000),
                 dict(self.manifest["pcm"], channels=2),
                 dict(self.manifest["pcm"], sample_count=True)]
        original_pcm = dict(self.manifest["pcm"])
        for pcm in cases:
            with self.subTest(pcm=pcm):
                self.rebound_manifest(pcm=pcm)
                with self.assertRaises(capture.CaptureError):
                    self.author()
                self.assert_no_published_profile()
        self.rebound_manifest(pcm=original_pcm,
                              timeline={"audio_start_seconds": 7.125, "no_time_stretch": False})
        with self.assertRaises(capture.CaptureError):
            self.author()

    def test_manifest_binding_sections_must_be_objects_without_partial_publication(self):
        for field in ("source", "timeline", "pcm", "outputs", "output_sha256"):
            original = self.manifest[field]
            for invalid in ([], None, "not an object"):
                with self.subTest(field=field, value=invalid):
                    self.rebound_manifest(**{field: invalid})
                    with self.assertRaises(capture.CaptureError):
                        self.author()
                    self.assert_no_published_profile()
            self.rebound_manifest(**{field: original})

    def test_numeric_and_interval_controls_reject_bool_nonfinite_and_out_of_bound(self):
        cases = [("reduction_db", True), ("reduction_db", 12.01), ("reduction_db", 0),
                 ("noise_floor_db", -81), ("noise_floor_db", float("nan")),
                 ("adaptivity", -0.01), ("adaptivity", float("inf")),
                 ("gain_smooth", 1.0), ("gain_smooth", False), ("gain_smooth", 51),
                 ("integrated_lufs", -4.9), ("true_peak_dbtp", 0.1),
                 ("capture_start_seconds", -0.1), ("capture_end_seconds", 0.15),
                 ("capture_end_seconds", 2.1), ("timeout_seconds", 61),
                 ("timeout_seconds", True)]
        for key, value in cases:
            with self.subTest(key=key, value=value), self.assertRaises(capture.CaptureError):
                self.author(**{key: value})
        self.assert_no_published_profile()

    def test_closed_eq_and_compressor_controls(self):
        eq = [{"frequency_hz": 300, "gain_db": -2, "q": 0.7}]
        comp = {"threshold_db": -18, "ratio": 2, "attack_ms": 15,
                "release_ms": 100, "knee_db": 3}
        result = self.author(peaking_eq=eq, compressor=comp)
        profile = json.loads(Path(result["profile_path"]).read_text())
        self.assertEqual(profile["peaking_eq"], eq)
        self.assertEqual(profile["compressor"], comp)
        cases = [{"peaking_eq": [{"frequency_hz": 32, "gain_db": -2, "q": 0.7}]},
                 {"peaking_eq": [dict(eq[0], filter="highpass=80")]},
                 {"peaking_eq": [dict(eq[0], gain_db=True)]},
                 {"peaking_eq": [dict(eq[0], gain_db=3.1)]},
                 {"peaking_eq": [dict(eq[0], q=0.49)]},
                 {"peaking_eq": eq * 4},
                 {"compressor": dict(comp, ratio=3.1)},
                 {"compressor": dict(comp, attack_ms=7)},
                 {"compressor": dict(comp, release_ms=201)},
                 {"compressor": dict(comp, threshold_db=-37)},
                 {"compressor": dict(comp, knee_db=float("nan"))},
                 {"compressor": {"ratio": 2}},
                 {"compressor": dict(comp, makeup_db=3)}]
        for controls in cases:
            with self.subTest(controls=controls), self.assertRaises(capture.CaptureError):
                self.author(**controls)

    def test_duplicate_json_keys_and_oversize_review_rejected(self):
        text = self.review_path.read_text()
        self.review_path.write_text(text[:-1] + ',"schema_version":1}')
        with self.assertRaises(capture.CaptureError):
            self.author()
        self.reviewed(note="x" * 17000)
        with self.assertRaises(capture.CaptureError):
            self.author()
        self.assert_no_published_profile()

    def test_symlink_source_review_and_run_rejected(self):
        alias = self.root / "source-link.wav"
        alias.symlink_to(self.source)
        with self.assertRaises(capture.CaptureError):
            capture.author(str(alias), str(self.run), str(self.review_path), **self.controls)
        review_alias = self.run / "review-link.json"
        review_alias.symlink_to(self.review_path)
        with self.assertRaises(capture.CaptureError):
            capture.author(str(self.source), str(self.run), str(review_alias), **self.controls)
        run_alias = self.root / "artifacts" / "runs" / "run-link"
        run_alias.symlink_to(self.run, target_is_directory=True)
        with self.assertRaises(capture.CaptureError):
            capture.author(str(self.source), str(run_alias), str(self.review_path), **self.controls)
        self.assert_no_published_profile()

    def test_pcm_path_traversal_and_external_review_rejected(self):
        self.rebound_manifest(outputs={"source": "../source.wav"})
        with self.assertRaises(capture.CaptureError):
            self.author()
        self.rebound_manifest(outputs={"source": "source.wav"})
        external = self.root / "external-review.json"
        shutil.copyfile(self.review_path, external)
        with self.assertRaises(capture.CaptureError):
            capture.author(str(self.source), str(self.run), str(external), **self.controls)
        self.assert_no_published_profile()

    def test_changed_pcm_and_changed_manifest_are_not_silently_rebased(self):
        original_pcm = self.pcm.read_bytes()
        with self.pcm.open("ab") as handle:
            handle.write(b"changed")
        with self.assertRaises(capture.CaptureError):
            self.author()
        self.pcm.write_bytes(original_pcm)
        self.manifest["extra_observation"] = "changed since review"
        dump(self.manifest_path, self.manifest)
        with self.assertRaises(capture.CaptureError):
            self.author()
        self.assert_no_published_profile()

    def test_finite_range_endpoints_are_accepted_without_optional_processing(self):
        for controls in (
                dict(reduction_db=0.01, noise_floor_db=-80, adaptivity=0,
                     gain_smooth=0, integrated_lufs=-70, true_peak_dbtp=-9),
                dict(reduction_db=12, noise_floor_db=-20, adaptivity=1,
                     gain_smooth=50, integrated_lufs=-5, true_peak_dbtp=0)):
            with self.subTest(controls=controls):
                result = self.author(**controls)
                self.assertEqual(result["status"], "authored_unrendered")
                profile = json.loads(Path(result["profile_path"]).read_text())
                for key, value in controls.items():
                    self.assertEqual(profile[key], value)

    def test_stereo_48k_non_frame_multiple_preserves_native_sample_mapping(self):
        self.replace_native_fixture(48000, 2, 96007)
        identity = sha(self.pcm)
        result = self.author()
        self.assertEqual(result["capture"]["native_samples"], [6000, 30000])
        self.assertEqual(sha(self.pcm), identity)
        self.assertFalse(result["dsp_performed"])

    def test_eq_nyquist_boundary_uses_actual_native_sample_rate(self):
        self.replace_native_fixture(8000, 1, 16000)
        for frequency in (4000, 6000):
            with self.subTest(frequency=frequency), self.assertRaises(capture.CaptureError):
                self.author(peaking_eq=[{"frequency_hz": frequency, "gain_db": 1, "q": 1}])
        result = self.author(peaking_eq=[{"frequency_hz": 3999, "gain_db": 1, "q": 1}])
        self.assertEqual(result["status"], "authored_unrendered")

    def test_float_pcm_baseline_header_is_supported_without_decoding(self):
        data = array.array("f", (0.05 * math.sin(2 * math.pi * 32 * i / self.rate)
                                  for i in range(self.count))).tobytes()
        fmt = struct.pack("<HHIIHH", 3, 1, self.rate, self.rate * 4, 4, 32)
        body = b"WAVEfmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
        self.pcm.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
        self.rebound_manifest(output_sha256={"source.wav": sha(self.pcm)})
        self.reviewed(source_pcm_sha256=sha(self.pcm))
        result = self.author()
        self.assertEqual(result["capture"]["native_samples"], [2000, 10000])
        self.assertFalse(result["dsp_performed"])

    def test_hash_bound_malformed_native_header_does_not_establish_pcm_truth(self):
        valid = self.pcm.read_bytes()
        # Wave headers store block alignment at byte 32. Hashes alone cannot
        # validate a malformed header claiming 4-byte mono PCM16 frames.
        invalid = bytearray(valid)
        invalid[32:34] = struct.pack("<H", 4)
        self.pcm.write_bytes(invalid)
        self.rebound_manifest(output_sha256={"source.wav": sha(self.pcm)})
        self.reviewed(source_pcm_sha256=sha(self.pcm))
        with self.assertRaises(capture.CaptureError):
            self.author()
        self.assert_no_published_profile()

    def test_hash_bound_truncated_and_duplicate_wave_chunks_are_rejected(self):
        valid = self.pcm.read_bytes()
        cases = []
        oversized_fmt = bytearray(valid)
        oversized_fmt[16:20] = struct.pack("<I", len(valid) + 100)
        cases.append(oversized_fmt)
        oversized_data = bytearray(valid)
        oversized_data[40:44] = struct.pack("<I", len(valid) + 100)
        cases.append(oversized_data)
        truncated = bytearray(valid[:-7])
        truncated[4:8] = struct.pack("<I", len(truncated) - 8)
        cases.append(truncated)
        duplicate = bytearray(valid + b"data" + struct.pack("<I", 0))
        duplicate[4:8] = struct.pack("<I", len(duplicate) - 8)
        cases.append(duplicate)
        invalid_rate = bytearray(valid)
        invalid_rate[24:28] = struct.pack("<I", 1)
        cases.append(invalid_rate)
        unsupported_encoding = bytearray(valid)
        unsupported_encoding[20:22] = struct.pack("<H", 6)
        cases.append(unsupported_encoding)
        for index, raw in enumerate(cases):
            with self.subTest(case=index):
                self.pcm.write_bytes(raw)
                self.rebound_manifest(output_sha256={"source.wav": sha(self.pcm)})
                self.reviewed(source_pcm_sha256=sha(self.pcm))
                with self.assertRaises(capture.CaptureError):
                    self.author()
                self.assert_no_published_profile()

    def test_invalid_instrument_and_artist_registry_shapes_are_rejected(self):
        for name, field, bad in (("instrument.json", "string_count", 8),
                                 ("capture-context.json", "tone_reference_artists", [])):
            path = self.root / "program" / name
            original = path.read_bytes()
            data = json.loads(original)
            data[field] = bad
            dump(path, data)
            with self.subTest(name=name), self.assertRaises(capture.CaptureError):
                self.author()
            self.assert_no_published_profile()
            path.write_bytes(original)

    def test_context_change_between_verification_and_publication_is_rejected(self):
        context_path = self.root / "program" / "instrument.json"
        original_hash = capture.hash_file
        count = 0

        def mutate_on_recheck(path, *args, **kwargs):
            nonlocal count
            if Path(path) == context_path:
                count += 1
                if count == 2:
                    with context_path.open("ab") as handle:
                        handle.write(b"\n ")
            return original_hash(path, *args, **kwargs)

        with patch.object(capture, "hash_file", side_effect=mutate_on_recheck):
            with self.assertRaises(capture.CaptureError):
                self.author()
        self.assertGreaterEqual(count, 2)
        self.assert_no_published_profile()

    def test_deadline_expiry_cannot_publish_partial_profile(self):
        with patch.object(capture.Deadline, "check", side_effect=capture.CaptureError("fixture deadline")):
            with self.assertRaises(capture.CaptureError):
                self.author()
        self.assert_no_published_profile()

    def test_source_change_between_verification_and_publication_is_rejected(self):
        original_hash = capture.hash_file
        count = 0

        def mutate_on_recheck(path, *args, **kwargs):
            nonlocal count
            if Path(path) == self.source:
                count += 1
                if count == 2:
                    with self.source.open("ab") as handle:
                        handle.write(b"changed during authoring")
            return original_hash(path, *args, **kwargs)

        with patch.object(capture, "hash_file", side_effect=mutate_on_recheck):
            with self.assertRaises(capture.CaptureError):
                self.author()
        self.assertGreaterEqual(count, 2, "source identity must be rechecked before publication")
        self.assert_no_published_profile()

    def test_publication_failure_leaves_no_runnable_profile(self):
        with patch.object(capture, "publish_directory", side_effect=capture.CaptureError("fixture publish failure")):
            with self.assertRaises(capture.CaptureError):
                self.author()
        self.assert_no_published_profile()

    def test_oversized_original_is_rejected_before_hashing(self):
        with self.source.open("r+b") as handle:
            handle.truncate(3 * 1024 ** 3 + 1)
        original_open = capture.os.open

        def prohibit_oversize_read(path, *args, **kwargs):
            if Path(path) == self.source:
                raise AssertionError("oversized original must be rejected before reading")
            return original_open(path, *args, **kwargs)

        with patch.object(capture.os, "open", side_effect=prohibit_oversize_read):
            with self.assertRaises(capture.CaptureError):
                self.author()
        self.assert_no_published_profile()

    def test_cli_emits_compact_json_without_audio_processing(self):
        argv = [str(REPO / "scripts" / "capture_profile.py"), str(self.source),
                "--run-dir", str(self.run), "--review", str(self.review_path),
                "--capture-start", "0.125", "--capture-end", "0.625",
                "--reduction-db", "8", "--noise-floor-db", "-40",
                "--adaptivity", "0", "--gain-smooth", "0",
                "--integrated-lufs", "-18", "--true-peak-dbtp", "-1.5"]
        stdout = io.StringIO()
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout):
            returned = capture.main()
        self.assertIn(returned, (None, 0))
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["status"], "authored_unrendered")
        self.assertFalse(result["dsp_performed"])
        self.assertEqual(list(self.run.rglob("*.wav")), [self.pcm])

    def test_cli_hard_deadline_interrupts_blocked_author_and_restores_signal_state(self):
        previous_timer = signal.getitimer(signal.ITIMER_REAL)
        previous_handler = signal.getsignal(signal.SIGALRM)
        if previous_timer != (0.0, 0.0):
            self.skipTest("another owner already has a process timer")

        def blocked_author(*args, **kwargs):
            time.sleep(3)
            return {}

        stdout = io.StringIO()
        started = time.monotonic()
        with patch.object(capture, "author", side_effect=blocked_author), contextlib.redirect_stdout(stdout):
            returned = capture.main(self.cli_args("--timeout-seconds", "1"))
        elapsed = time.monotonic() - started
        result = json.loads(stdout.getvalue())
        self.assertEqual(returned, 2)
        self.assertEqual(result["error"]["code"], "deadline_exceeded")
        self.assertFalse(result["dsp_performed"])
        self.assertGreaterEqual(elapsed, 0.8)
        self.assertLess(elapsed, 2.5, "deadline must interrupt blocking work rather than wait for it")
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), previous_timer)
        self.assertEqual(signal.getsignal(signal.SIGALRM), previous_handler)
        self.assert_no_published_profile()

    def test_cli_refuses_existing_timer_without_modifying_signal_or_calling_author(self):
        stdout = io.StringIO()
        with patch.object(signal, "getitimer", return_value=(4.0, 0.5)), \
                patch.object(signal, "setitimer") as set_timer, \
                patch.object(signal, "signal") as set_handler, \
                patch.object(capture, "author") as author, contextlib.redirect_stdout(stdout):
            returned = capture.main(self.cli_args("--timeout-seconds", "1"))
        result = json.loads(stdout.getvalue())
        self.assertEqual(returned, 2)
        self.assertEqual(result["error"]["code"], "validation_failed")
        set_timer.assert_not_called()
        set_handler.assert_not_called()
        author.assert_not_called()
        self.assert_no_published_profile()

    def test_author_reads_headers_without_subprocess_and_retains_context_hashes(self):
        import subprocess
        with patch.object(subprocess, "run", side_effect=AssertionError("author must not invoke media workers")):
            result = self.author()
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertFalse(receipt["audio_decoded"])
        self.assertFalse(receipt["learned_band_shape"])
        for name in ("instrument.json", "capture-context.json"):
            self.assertEqual(receipt["context"][name]["sha256"], sha(self.root / "program" / name))
        self.assertEqual(receipt["context"]["instrument.json"]["snapshot"]["string_count"], 9)


if __name__ == "__main__":
    unittest.main()
