"""Meaningful integration fixtures for source fidelity and export timelines."""
import array
import importlib.util
import json
import math
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("media_worker", REPO / "scripts" / "media.py")
media = importlib.util.module_from_spec(spec)
spec.loader.exec_module(media)


class ProfileTests(unittest.TestCase):
    def test_packet_timing_rejects_shift_and_picture_payload_changes(self):
        packets = [{"pts": index * 20, "dts": index * 20 - 20, "duration": 20,
                    "data_hash": f"SHA256:picture-{index}"} for index in range(3)]
        translated = [dict(packet, pts=packet["pts"] - 500, dts=packet["dts"] - 500)
                      for packet in packets]
        verified = media.compare_video_packets(packets, translated, "1/1000", "1/1000", Fraction(-1, 2))
        self.assertTrue(verified["video_packet_payload_hashes_preserved"])
        shifted = [dict(packet, pts=packet["pts"] + 20) for packet in translated]
        with self.assertRaises(media.MediaError):
            media.compare_video_packets(packets, shifted, "1/1000", "1/1000", Fraction(-1, 2))
        changed = [dict(packet) for packet in translated]
        changed[1]["data_hash"] = "SHA256:different-picture"
        with self.assertRaises(media.MediaError):
            media.compare_video_packets(packets, changed, "1/1000", "1/1000", Fraction(-1, 2))

    def test_noise_capture_needs_explicit_authorization(self):
        profile = json.loads((REPO / "profiles" / "conservative3.json").read_text())
        profile["noise_capture_seconds"] = [0, 0.5]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profile.json"
            path.write_text(json.dumps(profile))
            with self.assertRaises(media.MediaError):
                media.load_profile(path)
            profile["noise_capture_authorized"] = True
            path.write_text(json.dumps(profile))
            self.assertEqual(media.load_profile(path)["noise_capture_seconds"], [0, 0.5])


class MediaIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            media.executable("ffmpeg")
            media.executable("ffprobe")
        except media.MediaError as exc:
            raise unittest.SkipTest(str(exc))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.original_root = media.ROOT
        media.ROOT = self.directory

    def tearDown(self):
        media.ROOT = self.original_root
        self.temp.cleanup()

    def profile(self, name):
        return REPO / "profiles" / f"{name}.json"

    def tone(self, path, rate=48000):
        media.ffmpeg(["-f", "lavfi", "-i", f"sine=frequency=32:sample_rate={rate}:duration=2",
                      "-ac", "2", "-c:a", "pcm_s24le", str(path)])

    def raw_samples(self, path):
        import subprocess
        result = subprocess.run([media.executable("ffmpeg"), "-v", "error", "-nostdin", "-i", str(path),
                                 "-map", "0:a:0", "-c:a", "pcm_f32le", "-f", "f32le", "-"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=30)
        samples = array.array("f")
        samples.frombytes(result.stdout)
        return samples

    def test_32hz_preservation_native_pcm_and_source_immutability(self):
        # Spaces and shell syntax in input name must remain ordinary path data.
        source = self.directory / "low 32Hz ; $(touch unexpected).wav"
        self.tone(source)
        original_hash = media.sha256(source)
        manifest = media.clean(source, self.profile("conservative3"))
        self.assertEqual(media.sha256(source), original_hash)
        self.assertFalse((self.directory / "unexpected").exists())
        self.assertEqual(manifest["pcm"]["sample_count"], 96000)
        self.assertEqual(manifest["pcm"]["channels"], 2)
        self.assertEqual(manifest["pcm"]["sample_rate"], 48000)
        run_dir = Path(manifest["run_dir"])
        self.assertEqual(media.pcm_info(run_dir / "cleaned.wav")["codec"], "pcm_s24le")
        before = self.raw_samples(run_dir / "source.wav")
        after = self.raw_samples(run_dir / "denoised.wav")
        # Ignore filter boundary warmup; measure coherent 32Hz energy, not total RMS.
        def amplitude(samples):
            sequence = samples[4800 * 2:-4800 * 2:2]
            sine = sum(sample * math.sin(2 * math.pi * 32 * (index + 4800) / 48000)
                       for index, sample in enumerate(sequence))
            cosine = sum(sample * math.cos(2 * math.pi * 32 * (index + 4800) / 48000)
                         for index, sample in enumerate(sequence))
            return 2 * math.hypot(sine, cosine) / len(sequence)
        attenuation_db = 20 * math.log10(amplitude(after) / amplitude(before))
        self.assertGreater(attenuation_db, -0.25, "denoising damages intentional 32Hz fundamental")
        # A deliberately damaging rumble filter proves the LF check catches the
        # actual nine-string failure mode instead of merely checking metadata.
        damaged = self.directory / "highpass-damage-control.wav"
        media.ffmpeg(["-i", str(source), "-af", "highpass=f=80", "-c:a", "pcm_f32le", str(damaged)])
        damage_db = 20 * math.log10(amplitude(self.raw_samples(damaged)) / amplitude(before))
        self.assertLess(damage_db, -12)
        self.assertFalse(manifest["frequency_preservation"]["high_pass_applied"])
        outcome = media.export(run_dir)
        self.assertIsNone(outcome["video"])
        self.assertFalse(outcome["listening_accepted"])
        self.assertFalse(list((self.directory / "artifacts" / "runs").glob(".staging-*")))

    def test_bypass_residue_and_nondefault_rate(self):
        source = self.directory / "bypass.wav"
        self.tone(source, rate=44100)
        manifest = media.clean(source, self.profile("bypass"))
        run_dir = Path(manifest["run_dir"])
        self.assertEqual(manifest["pcm"]["sample_rate"], 44100)
        self.assertEqual(manifest["pcm"]["sample_count"], 88200)
        self.assertEqual(max(abs(value) for value in self.raw_samples(run_dir / "residue.wav")), 0)
        self.assertEqual(media.sha256(run_dir / "baseline.wav"), media.sha256(run_dir / "cleaned.wav"))

    def test_video_outlasts_audio_and_original_offset_is_preserved(self):
        source = self.directory / "offset.mov"
        media.ffmpeg(["-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=4",
                      "-itsoffset", "0.5", "-f", "lavfi", "-i",
                      "sine=frequency=220:sample_rate=48000:duration=2",
                      "-map", "0:v:0", "-map", "1:a:0", "-c:v", "mpeg4",
                      "-c:a", "pcm_s16le", "-avoid_negative_ts", "disabled", str(source)])
        manifest = media.clean(source, self.profile("bypass"))
        # Synthetic container-header diagnostic: an edit-list style duration
        # discrepancy must not overrule unchanged ordered packet timestamps.
        manifest["source"]["probe"]["video"]["duration"] = "4.020000"
        media.json_write(Path(manifest["run_dir"]) / "manifest.json", manifest)
        outcome = media.export(manifest["run_dir"])
        source_probe, output_probe = manifest["source"]["probe"], outcome["video_probe"]
        self.assertEqual(source_probe["video"]["nb_frames"], output_probe["video"]["nb_frames"])
        self.assertAlmostEqual(float(output_probe["video"]["duration"]), 4.0, places=2)
        self.assertAlmostEqual(output_probe["audio"]["start_time"], 0.5, delta=0.03)
        self.assertTrue(outcome["verification"]["relative_audio_video_start_verified"])
        self.assertTrue(outcome["verification"]["video_frame_count_preserved"])
        self.assertTrue(outcome["verification"]["video_packet_timeline_preserved"])
        self.assertTrue(outcome["verification"]["video_packet_payload_hashes_preserved"])
        self.assertAlmostEqual(outcome["verification"]["video_duration_delta_seconds"], -0.02, places=6)
        self.assertEqual(outcome["verification"]["source_decoded_video_frames"], 40)
        self.assertIn("input_tp", outcome["final_audio_loudness"])
        self.assertEqual(media.export(manifest["run_dir"]), outcome)
        with Path(outcome["video"]).open("ab") as handle:
            handle.write(b"tampered")
        with self.assertRaises(media.MediaError):
            media.export(manifest["run_dir"])

    def test_export_rejects_changed_source(self):
        source = self.directory / "changed.wav"
        self.tone(source)
        manifest = media.clean(source, self.profile("bypass"))
        with source.open("ab") as handle:
            handle.write(b"changed")
        with self.assertRaises(media.MediaError):
            media.export(manifest["run_dir"])
        self.assertFalse((Path(manifest["run_dir"]) / "export").exists())

    def test_explicit_noise_capture_and_failed_stage_cleanup(self):
        source = self.directory / "capture.wav"
        self.tone(source)
        profile = json.loads(self.profile("conservative3").read_text())
        profile.update(noise_capture_seconds=[0, 0.2], noise_capture_authorized=True)
        profile_path = self.directory / "profile.json"
        profile_path.write_text(json.dumps(profile))
        manifest = media.clean(source, profile_path)
        self.assertTrue(any("after the selected interval" in text for text in manifest["assumptions"]))
        profile["noise_capture_seconds"] = [0, 20]
        profile_path.write_text(json.dumps(profile))
        with self.assertRaises(media.MediaError):
            media.clean(source, profile_path)
        self.assertFalse(list((self.directory / "artifacts" / "runs").glob(".staging-*")))


if __name__ == "__main__":
    unittest.main()
