"""Independent gaps in capture-profile qualification; authoring metadata only."""
import array
import importlib.util
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("capture_audit_fixtures", REPO / "tests/test_capture_profile.py")
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
worker = fixtures.capture


class CaptureProfileAuditTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CaptureProfileTests()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def test_exact_minimum_native_capture_survives_decimal_float_subtraction(self):
        f = self.fixture
        f.reviewed(start_seconds=0.2, end_seconds=0.3)
        result = f.author(capture_start_seconds=0.2, capture_end_seconds=0.3)
        self.assertEqual(result["status"], "authored_unrendered")
        self.assertEqual(result["capture"]["native_samples"], [3200, 4800])
        self.assertFalse(result["dsp_performed"])
        profile = worker.media.load_profile(result["profile_path"])
        self.assertEqual([round(value * f.rate) for value in profile["noise_capture_seconds"]], [3200, 4800])
        self.assertEqual(result["capture"]["requested_seconds"], [0.2, 0.3])

    def test_exact_maximum_native_capture_survives_decimal_float_subtraction(self):
        f = self.fixture
        f.replace_native_fixture(16000, 1, 320000)
        f.reviewed(start_seconds=8.1, end_seconds=18.1)
        result = f.author(capture_start_seconds=8.1, capture_end_seconds=18.1)
        self.assertEqual(result["capture"]["native_samples"], [129600, 289600])
        profile = worker.media.load_profile(result["profile_path"])
        self.assertEqual([round(value * 16000) for value in profile["noise_capture_seconds"]], [129600, 289600])
        self.assertEqual(result["capture"]["requested_seconds"], [8.1, 18.1])

    def test_oversized_numeric_integer_returns_domain_error_without_artifacts(self):
        f = self.fixture
        for key in ("reduction_db", "capture_start_seconds", "noise_floor_db"):
            with self.subTest(key=key), self.assertRaises(worker.CaptureError):
                f.author(**{key: 10 ** 400})
        f.assert_no_published_profile()

    def test_nested_oversized_numeric_controls_return_domain_error(self):
        f = self.fixture
        settings = [{"peaking_eq": [{"frequency_hz": 300, "gain_db": 10 ** 400, "q": 1}]},
                    {"compressor": {"threshold_db": -18, "ratio": 10 ** 400,
                                    "attack_ms": 15, "release_ms": 100, "knee_db": 3}}]
        for controls in settings:
            with self.subTest(stage=next(iter(controls))), self.assertRaises(worker.CaptureError):
                f.author(**controls)
        f.assert_no_published_profile()

    def test_unavailable_named_home_path_returns_domain_error(self):
        f = self.fixture
        with self.assertRaises(worker.CaptureError):
            worker.author("~__capture_audit_nonexistent_user__/missing.wav", str(f.run),
                          str(f.review_path), **f.controls)
        f.assert_no_published_profile()

    def test_missing_review_or_authority_field_cannot_author_a_profile(self):
        f = self.fixture
        review_bytes = f.review_path.read_bytes()
        f.review_path.unlink()
        with self.assertRaises(worker.CaptureError):
            f.author()
        f.assert_no_published_profile()
        f.review_path.write_bytes(review_bytes)
        del f.review["authorization_scope"]
        fixtures.dump(f.review_path, f.review)
        with self.assertRaises(worker.CaptureError):
            f.author()
        f.assert_no_published_profile()

    def test_authoring_only_proposal_is_rejected_by_frozen_media_profile_validator(self):
        f = self.fixture
        f.reviewed(authorization_scope="profile_authoring")
        result = f.author()
        self.assertEqual(result["status"], "draft_authorization_incomplete")
        self.assertIsNone(result["profile_path"])
        self.assertFalse(json.loads(Path(result["proposal_path"]).read_text())["noise_capture_authorized"])
        with self.assertRaises(worker.media.MediaError):
            worker.media.load_profile(result["proposal_path"])
        f.assert_no_published_profile()

    def test_unknown_capture_is_an_explicit_experiment_without_noise_only_proof(self):
        f = self.fixture
        for status in ("unknown", "suspected"):
            with self.subTest(status=status):
                f.reviewed(music_status=status, click_status=status)
                result = f.author()
                self.assertEqual(result["status"], "authored_unrendered")
                receipt = json.loads(Path(result["receipt_path"]).read_text())
                self.assertFalse(receipt["capture"]["noise_only_verified"])
                self.assertFalse(receipt["listening_accepted"])
                self.assertEqual(receipt["review"]["assertions"]["music_status"], status)
                self.assertEqual(receipt["review"]["assertions"]["click_status"], status)

    def test_whole_take_ambient_music_is_retained_without_separation_claim(self):
        f = self.fixture
        f.reviewed(ambient_music_status="reviewed_present")
        result = f.author()
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(result["status"], "authored_unrendered")
        self.assertEqual(receipt["review"]["assertions"]["ambient_music_status"], "reviewed_present")
        self.assertTrue(any("Ambient music" in message for message in receipt["warnings"]))
        self.assertFalse(receipt["audio_decoded"])
        self.assertFalse(receipt["learned_band_shape"])
        self.assertFalse(receipt["dsp_performed"])

    def test_review_change_between_hash_and_json_read_is_detected(self):
        f = self.fixture
        original_hash = worker.hash_file
        changed = False

        def mutate_after_hash(path, *args, **kwargs):
            nonlocal changed
            result = original_hash(path, *args, **kwargs)
            if Path(path) == f.review_path and not changed:
                changed = True
                f.reviewed(note="Changed authorization review between hashing and JSON read.")
            return result

        with patch.object(worker, "hash_file", side_effect=mutate_after_hash):
            with self.assertRaises(worker.CaptureError):
                f.author()
        self.assertTrue(changed)
        f.assert_no_published_profile()

    def test_pcm_byte_ceiling_is_checked_before_payload_read(self):
        f = self.fixture
        with f.pcm.open("r+b") as handle:
            handle.truncate(1024 ** 3 + 1)
        original_open = worker.os.open

        def no_oversize_payload_read(path, *args, **kwargs):
            if Path(path) == f.pcm:
                raise AssertionError("PCM ceiling must precede payload reading")
            return original_open(path, *args, **kwargs)

        with patch.object(worker.os, "open", side_effect=no_oversize_payload_read):
            with self.assertRaises(worker.CaptureError):
                f.author()
        f.assert_no_published_profile()

    def test_extensible_native_float_header_is_supported_but_unknown_subformat_rejects(self):
        f = self.fixture
        f.replace_native_fixture(48000, 2, 96007)
        data = array.array("f", [0.01]) * (96007 * 2)
        raw_data = data.tobytes()
        guid = bytes.fromhex("0300000000001000800000aa00389b71")
        fmt = struct.pack("<HHIIHHHHI", 0xFFFE, 2, 48000, 48000 * 8, 8, 32, 22, 32, 3) + guid

        def bind_fmt(raw_fmt):
            body = b"WAVEfmt " + struct.pack("<I", len(raw_fmt)) + raw_fmt + b"data" + struct.pack("<I", len(raw_data)) + raw_data
            f.pcm.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
            identity = fixtures.sha(f.pcm)
            f.rebound_manifest(output_sha256={"source.wav": identity})
            f.reviewed(source_pcm_sha256=identity)

        bind_fmt(fmt)
        result = f.author()
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["baseline"]["pcm"]["codec"], "pcm_f32le")
        self.assertEqual(result["capture"]["native_samples"], [6000, 30000])
        before = len(list(f.run.glob("capture-profiles/*/profile.json")))
        bind_fmt(fmt[:-1] + b"\0")
        with self.assertRaises(worker.CaptureError):
            f.author()
        self.assertEqual(len(list(f.run.glob("capture-profiles/*/profile.json"))), before)


if __name__ == "__main__":
    unittest.main()
