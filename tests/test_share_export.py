"""Share-delivery metadata, bounded controls and synthetic VFR/AAC qualification."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import random
import shutil
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("share_export_test_worker", REPO / "scripts/share_export.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
QUALIFIED_BIN = Path("/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin")
QUALIFIED_SHA = {
    "ffmpeg": "3a315207e67de78e48c3bbb6b3346663f6a27c02e034d65ac72a12fee74c534a",
    "ffprobe": "5fb21f955aad27bc59615906801ce4b5b9f1466e99450b714b6d989f836c8850",
}


def packets(*, multiplier=1, encoded=False):
    # Deliberately nonconstant picture durations. Packet input order models
    # encoder reorder; comparison must use presentation order, not DTS order.
    return [{"pts": value * multiplier, "dts": (value - 80) * multiplier, "duration": duration * multiplier,
             "data_hash": "SHA256:" + hashlib.sha256(f"{'encoded' if encoded else 'source'}:{index}".encode()).hexdigest()}
            for index, (value, duration) in enumerate(((0, 40), (40, 80), (120, 40), (160, 80)))]


class ShareExportHelpers(unittest.TestCase):
    def test_default_settings_are_explicit_without_mutable_shared_state(self):
        first = worker.settings()
        self.assertIsInstance(first, dict)
        self.assertEqual((first["height"], first["crf"], first["audio_kbps"], first["codec"]), (720, 27, 96, "h264"))
        self.assertEqual(first["operation_seconds"], 890)
        self.assertEqual(first["cleanup_grace_seconds"] + first["reporting_headroom_seconds"], 10)
        second = worker.settings()
        first["synthetic_mutation"] = True
        self.assertNotIn("synthetic_mutation", second)

    def test_boolean_nonfinite_and_noninteger_controls_are_rejected(self):
        base = [720, 26, 96, "hevc", 900]
        for index in (0, 1, 2, 4):
            for invalid in (True, False, math.nan, math.inf, -math.inf, None, "720", 720.5, -(10 ** 100), 10 ** 100):
                with self.subTest(index=index, invalid=repr(invalid)):
                    values = list(base)
                    values[index] = invalid
                    with self.assertRaises(ValueError):
                        worker.settings(*values)
        for invalid in (None, True, "", "vp9", "HEVC", "libx265"):
            with self.subTest(codec=invalid), self.assertRaises(ValueError):
                worker.settings(720, 26, 96, invalid, 900)

    def test_geometry_is_even_bounded_and_never_upscales(self):
        self.assertEqual(worker.geometry(1920, 1080, 720), (1280, 720))
        self.assertEqual(worker.geometry(320, 240, 720), (320, 240))
        rng = random.Random(6100609)
        for case in range(100):
            width, height = rng.randint(160, 4096), rng.randint(160, 4096)
            requested = rng.choice((360, 480, 720, 1080))
            with self.subTest(seed=6100609, case=case, geometry=(width, height, requested)):
                out_width, out_height = worker.geometry(width, height, requested)
                self.assertEqual(out_width % 2, 0)
                self.assertEqual(out_height % 2, 0)
                self.assertTrue(0 < out_width <= width)
                self.assertTrue(0 < out_height <= min(height, requested))
                factor = (min(height, requested) // 2 * 2) / height
                self.assertLessEqual(abs(out_width - width * factor), 2)
                self.assertEqual(out_height, min(height, requested) // 2 * 2)

    def test_reencoded_vfr_packets_compare_sorted_pts_across_rational_timebases(self):
        source = packets()
        output = list(reversed(packets(multiplier=2, encoded=True)))
        before = copy.deepcopy((source, output))
        proof = worker.verify_packets(source, output, "1/1000", "1/2000", copy=False)
        self.assertIsInstance(proof, dict)
        self.assertEqual((source, output), before)

    def test_packet_copy_requires_payload_identity_not_only_equal_timing(self):
        source = packets()
        output = packets(multiplier=2)
        self.assertIsInstance(worker.verify_packets(source, output, "1/1000", "1/2000", copy=True), dict)
        output[2]["data_hash"] = "SHA256:" + "f" * 64
        with self.assertRaises(ValueError):
            worker.verify_packets(source, output, "1/1000", "1/2000", copy=True)

    def test_missing_extra_or_shifted_packets_cannot_pass_timeline_proof(self):
        source = packets()
        variants = [packets()[:-1], packets() + [dict(packets()[-1], pts=240)], packets()]
        variants[-1][2]["pts"] += 1000
        for index, output in enumerate(variants):
            with self.subTest(case=index), self.assertRaises(ValueError):
                worker.verify_packets(source, output, "1/1000", "1/1000", copy=False)

    def test_final_packet_extent_is_part_of_timing_proof(self):
        output = packets()
        output[-1]["duration"] += 1000
        with self.assertRaises(ValueError):
            worker.verify_packets(packets(), output, "1/1000", "1/1000", copy=False)

    def test_transcoded_nominal_packet_durations_may_differ_without_changing_vfr_pts(self):
        source, output = packets(), packets(encoded=True)
        output[0]["duration"] += 40
        output[1]["duration"] -= 40
        proof = worker.verify_packets(source, output, "1/1000", "1/1000", copy=False)
        self.assertEqual(proof["maximum_pts_delta_seconds"], 0.0)
        self.assertEqual(proof["tail_extent_delta_seconds"], 0.0)
        self.assertFalse(proof["copied_payload_verified"])
        copied = packets()
        copied[0]["duration"] += 40
        with self.assertRaises(worker.ShareError):
            worker.verify_packets(source, copied, "1/1000", "1/1000", copy=True)

    def test_unknown_packet_fields_or_clocks_do_not_create_a_false_proof(self):
        for field in ("pts", "duration", "data_hash"):
            incomplete = packets()
            del incomplete[1][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                worker.verify_packets(packets(), incomplete, "1/1000", "1/1000", copy=True)
        for timebase in ("0/1", "1/0", "bad", None):
            with self.subTest(timebase=timebase), self.assertRaises(ValueError):
                worker.verify_packets(packets(), packets(), timebase, "1/1000", copy=False)

    def test_geometry_requested_height_has_the_same_typed_bound_as_settings(self):
        for requested in (True, False, None, 0, -1, 239, 1082, 240.5, "720"):
            with self.subTest(requested=requested), self.assertRaises(worker.ShareError):
                worker.geometry(1920, 1080, requested)

    def test_packet_boolean_fractional_or_nonpositive_duration_cannot_prove_timing(self):
        for field, invalid in (("pts", False), ("pts", .1), ("duration", True),
                               ("duration", 0), ("duration", -1), ("duration", 40.5)):
            source, output = packets(), packets()
            output[0][field] = invalid
            with self.subTest(field=field, invalid=invalid), self.assertRaises(worker.ShareError):
                worker.verify_packets(source, output, "1/1000", "1/1000", copy=False)
        with self.assertRaises(worker.ShareError):
            worker.verify_packets(packets(), packets(), True, True, copy=False)


class ShareExportMockedStages(unittest.TestCase):
    """Dummy stage bytes test orchestration only; no media rendering occurs."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "original.mp4"
        self.source.write_bytes(b"synthetic source identity bytes, never decoded")
        self.original = self.source.read_bytes()
        self.output = self.root / "shared.mp4"
        self.metadata = {"format": {"duration": "2.0"},
                         "audio": {"index": 1, "codec_name": "aac", "sample_rate": "44100", "channels": 2},
                         "video": {"index": 0, "codec_name": "h264", "width": 320, "height": 240,
                                   "sample_aspect_ratio": "1:1", "time_base": "1/1000", "pix_fmt": "yuv420p"}}
        self.audio = {"start_seconds": 0.0, "end_seconds": 2.0, "decoded_samples": 88200,
                      "frame_count": 87, "time_base": "1/44100"}
        self.target_codec = "h264"
        self.copy_video = False
        self.commands = []
        self.stack = contextlib.ExitStack()
        self.stack.enter_context(patch.object(worker, "executable", side_effect=lambda name: "/synthetic/" + name))
        self.run = self.stack.enter_context(patch.object(worker, "run", side_effect=self.stage))
        self.probe = self.stack.enter_context(patch.object(worker, "probe", side_effect=self.probe_fixture))
        self.stack.enter_context(patch.object(worker, "packets", side_effect=lambda path, stream, state: packets(encoded=Path(path) != self.source and not self.copy_video)))
        self.frames = self.stack.enter_context(patch.object(worker, "audio_frames", side_effect=lambda *args: copy.deepcopy(self.audio)))
        self.measure = self.stack.enter_context(patch.object(worker, "loudness", return_value=self.measurement(-2.0)))

    def tearDown(self):
        self.stack.close()
        self.temp.cleanup()

    def measurement(self, peak):
        return {"integrated_lufs": -18.0, "true_peak_dbtp": peak, "silence": False,
                "method": "synthetic_measurement_fixture"}

    def probe_fixture(self, path, state):
        result = copy.deepcopy(self.metadata)
        if Path(path) != self.source and result["video"] is not None:
            result["video"]["codec_name"] = self.target_codec
        return result

    def stage(self, command, state):
        self.assertLessEqual(state["deadline"].remaining(), 110)
        self.assertEqual(command[command.index("-threads") + 1], "2")
        self.assertIn("-n", command)
        self.commands.append(list(command))
        target = Path(command[-1])
        if target.suffix in (".mp4", ".m4a") and target.parent == state["staging"]:
            target.write_bytes(b"synthetic stage bytes for " + target.name.encode())
        return subprocess.CompletedProcess(command, 0, "", "")

    def export(self, **changes):
        return worker.share_export(str(self.source), str(self.output), timeout_seconds=120, **changes)

    def assert_no_delivery(self):
        self.assertFalse(self.output.exists())
        self.assertFalse(self.output.with_name(self.output.name + ".receipt.json").exists())
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_verified_stages_publish_exact_hashes_and_unreviewed_sidecar(self):
        result = self.export()
        receipt_path = self.output.with_name(self.output.name + ".receipt.json")
        self.assertEqual(result["status"], "exported_unreviewed")
        self.assertEqual(result["source"]["sha256"], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(result["output"]["sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())
        self.assertEqual(result["output"]["receipt_sha256"], hashlib.sha256(receipt_path.read_bytes()).hexdigest())
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt["source"], result["source"])
        self.assertEqual(receipt["video_encode_count"], 1)
        self.assertTrue(receipt["audio_proof"]["audio_reencoded"])
        self.assertFalse(result["master_adopted"])
        self.assertFalse(result["listening_accepted"])
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_existing_output_or_sidecar_never_launches_or_overwrites(self):
        for collision in (self.output, self.output.with_name(self.output.name + ".receipt.json")):
            with self.subTest(collision=collision.name):
                collision.write_bytes(b"owner sentinel")
                with self.assertRaises(worker.ShareError):
                    self.export()
                self.assertEqual(collision.read_bytes(), b"owner sentinel")
                collision.unlink()
        self.run.assert_not_called()
        self.probe.assert_not_called()
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_invalid_native_metadata_rejects_before_encode(self):
        original = copy.deepcopy(self.metadata)
        variants = []
        for key in ("audio", "video"):
            variant = copy.deepcopy(original)
            variant[key] = None
            variants.append(variant)
        for duration in ("NaN", "0", "301"):
            variant = copy.deepcopy(original)
            variant["format"]["duration"] = duration
            variants.append(variant)
        for field, value in (("sample_rate", "7999"), ("channels", 9)):
            variant = copy.deepcopy(original)
            variant["audio"][field] = value
            variants.append(variant)
        for field, value in (("sample_aspect_ratio", "4:3"), ("side_data_list", [{"rotation": 90}])):
            variant = copy.deepcopy(original)
            variant["video"][field] = value
            variants.append(variant)
        for index, variant in enumerate(variants):
            with self.subTest(case=index):
                self.metadata = variant
                with self.assertRaises(worker.ShareError):
                    self.export()
                self.assert_no_delivery()
        self.run.assert_not_called()

    def test_copy_mode_preserves_video_payload_and_does_not_encode_video(self):
        self.target_codec, self.copy_video = "h264", True
        result = self.export(codec="copy")
        self.assertEqual(result["video_encode_count"], 0)
        self.assertTrue(result["video_proof"]["copied_payload_verified"])
        self.assertFalse(any("-vf" in command for command in self.commands))
        self.assertTrue(result["audio_proof"]["audio_reencoded"])

    def test_strict_aac_peak_retry_reuses_video_and_applies_only_bounded_attenuation(self):
        self.measure.side_effect = [self.measurement(-.5), self.measurement(-1.7), self.measurement(-1.7)]
        result = self.export()
        self.assertEqual(len(result["audio_attempts"]), 2)
        self.assertEqual(result["audio_attempts"][0]["gain_db"], 0.0)
        self.assertAlmostEqual(result["audio_attempts"][1]["gain_db"], -1.1)
        self.assertEqual(sum("-vf" in command for command in self.commands), 1)
        self.assertEqual(sum("-c:a" in command for command in self.commands), 2)
        audio_retry = [command for command in self.commands if "-c:a" in command][1]
        self.assertEqual(audio_retry[audio_retry.index("-af") + 1], "volume=-1.100000dB")
        self.assertLessEqual(result["loudness"]["true_peak_dbtp"], -1.5)

    def test_unmet_peak_or_stage_failure_retains_failure_evidence_without_delivery(self):
        self.measure.side_effect = [self.measurement(-.5), self.measurement(-.5)]
        with self.assertRaises(worker.ShareError) as caught:
            self.export()
        diagnostic = caught.exception.share_failure
        self.assertEqual(diagnostic["status"], "failed_no_export_published")
        failure = Path(diagnostic["failure_receipt_path"])
        self.assertEqual(hashlib.sha256(failure.read_bytes()).hexdigest(), diagnostic["failure_receipt_sha256"])
        self.assertEqual(sum("-c:a" in command for command in self.commands), 2)
        self.assert_no_delivery()

    def test_source_mutation_after_stages_abstains_before_publication(self):
        original_stage = self.stage

        def mutate(command, state):
            result = original_stage(command, state)
            if command[-1] == "-":
                self.source.write_bytes(b"synthetic independently changed source")
            return result

        self.run.side_effect = mutate
        with self.assertRaises(worker.ShareError) as caught:
            self.export()
        self.assertEqual(caught.exception.share_failure["status"], "failed_no_export_published")
        self.assertFalse(self.output.exists())
        self.assertFalse(self.output.with_name(self.output.name + ".receipt.json").exists())

    def test_last_moment_output_collision_does_not_replace_other_writer_bytes(self):
        original_publish = worker.publish_no_clobber

        def collide(staged, destination):
            if Path(destination) == self.output:
                self.output.write_bytes(b"independent owner won collision")
            return original_publish(staged, destination)

        with patch.object(worker, "publish_no_clobber", side_effect=collide), self.assertRaises(FileExistsError) as caught:
            self.export()
        self.assertEqual(caught.exception.share_failure["status"], "failed_no_export_published")
        self.assertEqual(self.output.read_bytes(), b"independent owner won collision")
        self.assertFalse(self.output.with_name(self.output.name + ".receipt.json").exists())
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_receipt_collision_reports_committed_media_instead_of_false_rollback(self):
        original_publish = worker.publish_no_clobber
        sidecar = self.output.with_name(self.output.name + ".receipt.json")

        def collide(staged, destination):
            if Path(destination) == sidecar:
                sidecar.write_bytes(b"independent receipt owner")
            return original_publish(staged, destination)

        with patch.object(worker, "publish_no_clobber", side_effect=collide), self.assertRaises(FileExistsError) as caught:
            self.export()
        diagnostic = caught.exception.share_failure
        self.assertEqual(diagnostic["status"], "exported_unreviewed_reporting_interrupted")
        self.assertEqual(diagnostic["output"]["sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())
        self.assertEqual(sidecar.read_bytes(), b"independent receipt owner")
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_failed_encode_retains_bounded_failure_receipt_without_publishing(self):
        self.run.side_effect = OSError("synthetic stage launch failure")
        with self.assertRaises(OSError) as caught:
            self.export()
        diagnostic = caught.exception.share_failure
        self.assertEqual(diagnostic["status"], "failed_no_export_published")
        receipt = Path(diagnostic["failure_receipt_path"])
        self.assertLessEqual(receipt.stat().st_size, worker.MAX_RECEIPT_BYTES)
        self.assertEqual(hashlib.sha256(receipt.read_bytes()).hexdigest(), diagnostic["failure_receipt_sha256"])
        self.assert_no_delivery()

    def test_exit_zero_with_explicit_delivery_decode_error_still_refuses_publication(self):
        original_stage = self.stage

        def decode_error(command, state):
            result = original_stage(command, state)
            if command[-1] == "-":
                result.stderr = "error while decoding synthetic delivery frame"
            return result

        self.run.side_effect = decode_error
        with self.assertRaises(worker.ShareError) as caught:
            self.export()
        self.assertEqual(caught.exception.share_failure["status"], "failed_no_export_published")
        self.assert_no_delivery()

    def test_cli_disarms_owned_timer_before_success_print_and_restores_signal_state(self):
        before_handler = signal.getsignal(signal.SIGALRM)
        before_timer = signal.getitimer(signal.ITIMER_REAL)
        if before_timer != (0.0, 0.0):
            self.skipTest("another owner already has a timer")
        printed = []

        def observe_print(value, *args, **kwargs):
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
            printed.append(json.loads(value))

        argv = [str(self.source), str(self.output), "--timeout-seconds", "120"]
        with patch("builtins.print", side_effect=observe_print):
            code = worker.main(argv)
        self.assertEqual(code, 0)
        self.assertEqual(printed[0]["status"], "exported_unreviewed")
        self.assertEqual(signal.getsignal(signal.SIGALRM), before_handler)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), before_timer)

    def test_rejected_cli_after_success_cannot_report_previous_export_as_current(self):
        previous = self.export()
        output_before = self.output.read_bytes()
        stdout = io.StringIO()
        argv = [str(self.source), str(self.root / "next.mp4"), "--height", "239"]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            code = worker.main(argv)
        diagnostic = json.loads(stdout.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(diagnostic["status"], "rejected")
        self.assertNotIn("output", diagnostic)
        self.assertIsNone(worker.LAST_STATE)
        self.assertEqual(self.output.read_bytes(), output_before)
        self.assertEqual(previous["output"]["sha256"], hashlib.sha256(output_before).hexdigest())

    def test_tool_envelope_preserves_rejection_json_with_exit_zero_only_for_hook(self):
        argv = [str(self.root / "missing-source.mp4"), str(self.output), "--timeout-seconds", "120"]
        diagnostics = []
        for envelope, expected_code in ((False, 2), (True, 0)):
            stdout = io.StringIO()
            with self.subTest(tool_envelope=envelope), contextlib.redirect_stdout(stdout), \
                    contextlib.redirect_stderr(io.StringIO()):
                code = worker.main(argv + (["--tool-envelope"] if envelope else []))
                self.assertEqual(code, expected_code)
            diagnostic = json.loads(stdout.getvalue())
            self.assertEqual(diagnostic["status"], "rejected")
            self.assertNotIn("output", diagnostic)
            diagnostics.append(diagnostic)
        self.assertEqual(diagnostics[0], diagnostics[1])
        self.assertIsNone(worker.LAST_STATE)
        self.run.assert_not_called()
        self.probe.assert_not_called()
        self.assert_no_delivery()


class ShareExportSyntheticIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Qualification selects the existing binaries by exact content hash;
        # never discover/download a replacement when these are unavailable.
        for name, digest in QUALIFIED_SHA.items():
            path = QUALIFIED_BIN / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise unittest.SkipTest(f"qualified {name} binary unavailable or changed")
        parent = REPO / "artifacts/experiments"
        parent.mkdir(parents=True, exist_ok=True)
        cls.root = Path(tempfile.mkdtemp(prefix="share-vfr-test-", dir=parent)).resolve()
        cls.preserve = False
        cls.source = cls.root / "synthetic-vfr-aac.mp4"
        command = [str(QUALIFIED_BIN / "ffmpeg"), "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
                   "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24:duration=2",
                   "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=44100:duration=2",
                   "-vf", "select=not(eq(mod(n\\,7)\\,3))", "-fps_mode", "vfr",
                   "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-threads", "2",
                   "-c:a", "aac", "-ac", "2", "-b:a", "96k", "-movflags", "+faststart", str(cls.source)]
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=45)
        except BaseException:
            shutil.rmtree(cls.root)
            raise

    @classmethod
    def tearDownClass(cls):
        if not cls.preserve:
            shutil.rmtree(cls.root)

    def packet_probe(self, path, selector):
        command = [str(QUALIFIED_BIN / "ffprobe"), "-v", "error", "-select_streams", selector,
                   "-show_streams", "-show_packets", "-show_data_hash", "sha256", "-of", "json", str(path)]
        return json.loads(subprocess.run(command, check=True, capture_output=True, text=True, timeout=30).stdout)

    def assert_synthetic_export(self, codec=None):
        output = self.root / f"synthetic-shared-{codec or 'default-h264'}.mp4"
        source_before = self.source.read_bytes()
        environment = {"FFMPEG": str(QUALIFIED_BIN / "ffmpeg"), "FFPROBE": str(QUALIFIED_BIN / "ffprobe")}
        controls = {} if codec is None else {"codec": codec}
        try:
            with patch.dict(os.environ, environment):
                result = worker.share_export(str(self.source), str(output), timeout_seconds=120, **controls)
        except BaseException as exc:
            type(self).preserve = True
            exc.add_note(f"Retained synthetic fixture and stage evidence: {self.root}")
            raise
        self.assertIsInstance(result, dict)
        self.assertTrue(output.is_file())
        self.assertEqual(self.source.read_bytes(), source_before)
        source_video, target_video = self.packet_probe(self.source, "v:0"), self.packet_probe(output, "v:0")
        self.assertEqual(len(source_video["packets"]), 41)
        self.assertEqual(len(target_video["packets"]), 41)
        self.assertEqual(target_video["streams"][0]["codec_name"], "hevc" if codec == "hevc" else "h264")
        self.assertEqual((target_video["streams"][0]["width"], target_video["streams"][0]["height"]), (320, 240))
        worker.verify_packets(source_video["packets"], target_video["packets"],
                              source_video["streams"][0]["time_base"], target_video["streams"][0]["time_base"], copy=codec == "copy")
        self.assertEqual(result["video_encode_count"], 0 if codec == "copy" else 1)
        self.assertEqual(result["video_proof"]["copied_payload_verified"], codec == "copy")
        source_audio, target_audio = self.packet_probe(self.source, "a:0"), self.packet_probe(output, "a:0")
        self.assertEqual(target_audio["streams"][0]["codec_name"], "aac")
        self.assertEqual(target_audio["streams"][0]["sample_rate"], "44100")
        self.assertEqual(target_audio["streams"][0]["channels"], 2)
        self.assertTrue(result["audio_proof"]["audio_reencoded"])
        self.assertFalse(result["audio_proof"]["exact_pcm_sample_identity"])
        self.assertLessEqual(abs(result["audio_proof"]["source"]["decoded_samples"]
                                 - result["audio_proof"]["output"]["decoded_samples"]), 2048)
        self.assertFalse(result["video_proof"]["physical_capture_sync_verified"])
        self.assertFalse(result["video_proof"]["source_full_frame_decode_verified"])
        receipt_path = Path(result["output"]["receipt_path"])
        self.assertEqual(receipt_path, output.with_name(output.name + ".receipt.json"))
        self.assertEqual(hashlib.sha256(receipt_path.read_bytes()).hexdigest(), result["output"]["receipt_sha256"])
        self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), result["output"]["sha256"])
        self.assertFalse(result["master_adopted"])
        self.assertFalse(result["listening_accepted"])
        self.assertTrue(result["loudness"]["silence"] or result["loudness"]["true_peak_dbtp"] <= -1.5)
        before = output.read_bytes()
        with patch.dict(os.environ, environment), self.assertRaises(ValueError):
            worker.share_export(str(self.source), str(output), timeout_seconds=120, **controls)
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(self.source.read_bytes(), source_before)

    def test_generated_two_second_vfr_aac_default_h264_delivery_clocks(self):
        self.assert_synthetic_export()

    def test_generated_two_second_vfr_aac_explicit_hevc_delivery_clocks(self):
        self.assert_synthetic_export("hevc")

    def test_generated_two_second_vfr_video_copy_preserves_payload_and_clocks(self):
        self.assert_synthetic_export("copy")


if __name__ == "__main__":
    unittest.main()
