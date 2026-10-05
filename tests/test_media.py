"""Meaningful integration fixtures for source fidelity and export timelines."""
import array
import importlib.util
import json
import math
import random
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("media_worker", REPO / "scripts" / "media.py")
media = importlib.util.module_from_spec(spec)
spec.loader.exec_module(media)


class ProfileTests(unittest.TestCase):
    def test_captured_presets_bind_reviewed_source_and_keep_typed_stages(self):
        original = "a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6"
        for name in ("captured8", "captured12", "captured8-clarity"):
            with self.subTest(name=name):
                profile = media.load_profile(REPO / "profiles" / f"{name}.json")
                self.assertEqual(profile["noise_capture_source_sha256"], original)
                self.assertEqual(profile["noise_capture_seconds"], [4.1, 4.95])
                self.assertIn("Root reviewed", profile["noise_capture_review"])
                self.assertIn("not an operator-exact", profile["noise_capture_review"])
                self.assertEqual(profile["noise_floor_db"], -40)
                self.assertEqual(profile["adaptivity"], 0)
                self.assertEqual(profile["gain_smooth"], 0)
                self.assertEqual(len(media.post_denoise_filters(profile, 44100)), 3 if name.endswith("clarity") else 0)

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
            with self.assertRaises(media.MediaError):
                media.load_profile(path)
            profile["noise_capture_source_sha256"] = "a" * 64
            path.write_text(json.dumps(profile))
            self.assertEqual(media.load_profile(path)["noise_capture_seconds"], [0, 0.5])

    def test_strict_numeric_restoration_controls_reject_injection_and_nonfinite(self):
        base = json.loads((REPO / "profiles" / "conservative3.json").read_text())
        invalid = [{"filter": "highpass=f=80"}, {"gain_smooth": 2.5},
                   {"compressor": {"ratio": 2}},
                   {"peaking_eq": [{"frequency_hz": "300,highpass=80", "gain_db": 1, "q": 1}]},
                   {"peaking_eq": [{"frequency_hz": 300, "gain_db": True, "q": 1}]},
                   {"peaking_eq": [{"frequency_hz": 32, "gain_db": -3, "q": 1}]},
                   {"peaking_eq": [{"frequency_hz": 300, "gain_db": 4, "q": 1}]},
                   {"peaking_eq": [{"frequency_hz": 300, "gain_db": float("nan"), "q": 1}]}]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profile.json"
            for update in invalid:
                with self.subTest(update=update):
                    path.write_text(json.dumps(dict(base, **update)))
                    with self.assertRaises(media.MediaError):
                        media.load_profile(path)
        compressor = {"threshold_db": -18, "ratio": 2, "attack_ms": 15,
                      "release_ms": 100, "knee_db": 3}
        for key, bad in [("ratio", 4), ("attack_ms", 0), ("release_ms", 9000),
                         ("threshold_db", -90), ("knee_db", float("inf"))]:
            with self.subTest(key=key), self.assertRaises(media.MediaError):
                media.post_denoise_filters({"compressor": dict(compressor, **{key: bad})}, 48000)
        with self.assertRaises(media.MediaError):
            media.post_denoise_filters({"peaking_eq": [{"frequency_hz": 6000, "gain_db": 1, "q": 1}]}, 8000)


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

    def test_wav_without_stream_start_uses_measured_decoded_origin(self):
        source = self.directory / "32 Hz recording.wav"
        self.tone(source)
        metadata = media.probe(source)
        self.assertIsNone(metadata["audio"]["start_time"])
        original_hash = media.sha256(source)
        manifest = media.clean(source, self.profile("bypass"))
        self.assertEqual(manifest["timeline"]["audio_start_seconds"], 0.0)
        origin = manifest["timeline"]["audio_origin_receipt"]
        self.assertEqual(origin["basis"], "first_decoded_frame_timestamp")
        self.assertIsNone(manifest["source"]["probe"]["audio"]["start_time"])
        self.assertEqual(media.sha256(source), original_hash)
        import subprocess
        run_dir = Path(manifest["run_dir"])
        result = subprocess.run([__import__("sys").executable, str(REPO / "scripts" / "rhythm.py"),
                                 str(run_dir / "denoised.wav"), "--run-dir", str(run_dir)],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        analysis = json.loads((run_dir / "analysis.json").read_text())
        self.assertEqual(analysis["source_lineage"]["original_audio_start_seconds"], 0.0)

    def test_compensated_attack_alignment_and_tail_at_44100_and_48000(self):
        for rate in (44100, 48000):
            with self.subTest(rate=rate):
                # Include a non-hop-multiple extent and a final attack inside
                # the last 25 ms; trimming an old delayed WAV loses that attack.
                count = rate * 4 + 137
                positions = (rate // 3, rate * 2 + 17, count - 100)
                values = array.array("h", [0]) * count
                for index in range(rate // 2, count):
                    values[index] = int(3000 * math.sin(2 * math.pi * 32 * index / rate))
                for position in positions:
                    values[position] += 24000
                source = self.directory / f"attacks-{rate}.wav"
                with wave.open(str(source), "wb") as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(2)
                    handle.setframerate(rate)
                    handle.writeframes(values.tobytes())
                manifest = media.clean(source, self.profile("conservative3"))
                directory = Path(manifest["run_dir"])
                latency = manifest["dsp_latency"]["denoise"]
                self.assertEqual(latency["delay_samples"], 2 * (rate // 80))
                self.assertEqual(latency["measured_impulse_offsets_samples"], [2 * (rate // 80)] * 2)
                self.assertFalse(manifest["dsp_latency"]["physical_audio_video_sync_verified"])
                for name in ("denoised.wav", "baseline.wav", "cleaned.wav"):
                    samples = self.raw_samples(directory / name)
                    self.assertEqual(len(samples), count)
                    for position in positions:
                        hit = max(range(max(0, position - 20), min(count, position + 21)),
                                  key=lambda i: abs(samples[i]))
                        self.assertEqual(hit, position, f"{name} displaced the attack")
                        self.assertGreater(abs(samples[position]), 0.1, f"{name} lost the source tail")
                self.assertEqual(manifest["loudness"]["cleaned"]["render"]["normalization_type"], "dynamic")
                # Prove this fixture detects the original bug: uncorrected
                # filtering displaces both interior attacks by two FFT hops.
                control = self.directory / f"uncompensated-{rate}.wav"
                media.ffmpeg(["-i", str(source), "-af", "afftdn=nr=3:nf=-40:tn=0:gs=5",
                              "-c:a", "pcm_f32le", str(control)])
                damaged = self.raw_samples(control)
                for position in positions[:2]:
                    search = range(position, position + latency["delay_samples"] + 30)
                    hit = max(search, key=lambda i: abs(damaged[i]))
                    self.assertEqual(hit - position, latency["delay_samples"])
                self.assertLess(abs(damaged[positions[-1]]), 0.15)

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

    def peak_fixture(self):
        source = self.directory / "aac-overshoot.mov"
        media.ffmpeg(["-f", "lavfi", "-i", "color=c=black:s=64x64:r=10:d=2",
                      "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=2",
                      "-map", "0:v:0", "-map", "1:a:0", "-c:v", "mpeg4",
                      "-c:a", "pcm_s16le", str(source)])
        manifest = media.clean(source, self.profile("bypass"))
        directory = Path(manifest["run_dir"])
        # Construct a source-bound test master at the exact -1.50 dBTP ceiling.
        # This demonstrates lossy delivery overshoot independently of mastering.
        replacement = self.directory / "peak-master.wav"
        gain = 8 * 10 ** (-1.5 / 20)
        media.ffmpeg(["-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=2",
                      "-af", f"volume={gain}", "-c:a", "pcm_s24le", str(replacement)])
        replacement.replace(directory / "cleaned.wav")
        manifest["output_sha256"]["cleaned.wav"] = media.sha256(directory / "cleaned.wav")
        media.json_write(directory / "manifest.json", manifest)
        return manifest, directory

    def test_actual_aac_overshoot_retry_preserves_master_and_picture(self):
        manifest, directory = self.peak_fixture()
        master_hash = media.sha256(directory / "cleaned.wav")
        outcome = media.export(directory)
        headroom = outcome["aac_headroom"]
        self.assertGreater(len(headroom["attempts"]), 1)
        self.assertLessEqual(len(headroom["attempts"]), 3)
        self.assertFalse(headroom["attempts"][0]["true_peak_within_target"])
        self.assertGreater(headroom["attempts"][0]["decoded_true_peak_dbtp"], -1.5)
        self.assertTrue(headroom["attempts"][-1]["true_peak_within_target"])
        self.assertGreaterEqual(headroom["feed_gain_db"], -1.0)
        self.assertLess(headroom["feed_gain_db"], 0)
        self.assertEqual(media.sha256(directory / "cleaned.wav"), master_hash)
        self.assertEqual(headroom["target_true_peak_dbtp"], -1.5)
        self.assertTrue(outcome["verification"]["final_true_peak_within_target"])
        self.assertTrue(outcome["verification"]["video_packet_payload_hashes_preserved"])
        self.assertTrue(outcome["verification"]["video_packet_timeline_preserved"])

    def test_aac_headroom_failure_is_bounded_and_retains_receipt_master(self):
        manifest, directory = self.peak_fixture()
        master_hash = media.sha256(directory / "cleaned.wav")
        # A stubborn measurement exercises retry exhaustion without weakening
        # the ceiling; the actual encoder still executes for each bounded try.
        with patch.object(media, "loudness", return_value={"input_tp": "-1.40", "input_i": "-18.0"}):
            with self.assertRaisesRegex(media.MediaError, "bounded headroom retries exhausted"):
                media.export(directory)
        self.assertEqual(media.sha256(directory / "cleaned.wav"), master_hash)
        self.assertFalse((directory / "export").exists())
        receipts = list((directory / "export-failures").glob("*.json"))
        self.assertEqual(len(receipts), 1)
        receipt = json.loads(receipts[0].read_text())
        self.assertEqual(receipt["status"], "export_failed_master_retained")
        self.assertEqual(len(receipt["aac_attempts"]), 3)
        self.assertTrue(all(not attempt["true_peak_within_target"] for attempt in receipt["aac_attempts"]))
        self.assertEqual(receipt["master_sha256"], master_hash)
        self.assertFalse(list(directory.glob(".export-staging-*")))

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
        profile.update(noise_capture_seconds=[0, 0.2], noise_capture_authorized=True,
                       noise_capture_source_sha256=media.sha256(source))
        profile_path = self.directory / "profile.json"
        profile_path.write_text(json.dumps(profile))
        manifest = media.clean(source, profile_path)
        self.assertTrue(manifest["noise_capture"]["applies_to_original_start"])
        self.assertEqual(manifest["noise_capture"]["authorization"], "authorized_source_bound_noise_interval")
        self.assertEqual(manifest["noise_capture"]["source_sha256"], media.sha256(source))
        profile["noise_capture_source_sha256"] = "f" * 64
        profile_path.write_text(json.dumps(profile))
        with self.assertRaises(media.MediaError):
            media.clean(source, profile_path)
        profile["noise_capture_source_sha256"] = media.sha256(source)
        profile["noise_capture_seconds"] = [0, 20]
        profile_path.write_text(json.dumps(profile))
        with self.assertRaises(media.MediaError):
            media.clean(source, profile_path)
        self.assertFalse(list((self.directory / "artifacts" / "runs").glob(".staging-*")))

    def fixture_wav(self, name, rate, channels, values):
        path = self.directory / name
        raw = array.array("h", (round(max(-.99, min(.99, value)) * 32767) for value in values))
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(channels)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(raw.tobytes())
        return path

    def test_each_forward_stage_preserves_support_stereo_rate_and_tail(self):
        stages = [{"peaking_eq": [{"frequency_hz": 300, "gain_db": -1.5, "q": .8},
                                   {"frequency_hz": 2200, "gain_db": 1, "q": .8}]},
                  {"compressor": {"threshold_db": -18, "ratio": 2, "attack_ms": 15,
                                  "release_ms": 100, "knee_db": 3}}]
        for rate in (44100, 48000):
            count, channels = rate + 137, 2
            positions = (rate // 4, count - 100)
            values = [0.] * (count * channels)
            for position in positions:
                values[position * channels] = .8
                values[position * channels + 1] = -.4
            source = self.fixture_wav(f"support-{rate}.wav", rate, channels, values)
            reference = media.pcm_info(source)
            for index, controls in enumerate(stages):
                with self.subTest(rate=rate, stage=index):
                    output = self.directory / f"stage-{rate}-{index}.wav"
                    receipt = media.render_post_denoise(source, output, controls, reference)
                    samples = self.raw_samples(output)
                    for position in positions:
                        self.assertGreater(samples[position * 2], .6)
                        self.assertLess(samples[position * 2 + 1], -.3)
                        self.assertLess(max(abs(x) for x in samples[(position-30)*2:position*2]), 1e-7)
                    self.assertFalse(receipt[0]["timing"]["acoustic_alignment_verified"])
                    self.assertEqual(len(samples), count * 2)

    def test_eq_low_sustain_and_compressor_level_dependence(self):
        rate = 48000
        compressor = {"compressor": {"threshold_db": -18, "ratio": 2,
                                     "attack_ms": 15, "release_ms": 100, "knee_db": 3}}
        eq = {"peaking_eq": [{"frequency_hz": 300, "gain_db": -1.5, "q": .8},
                             {"frequency_hz": 2200, "gain_db": 1, "q": .8}]}
        for level in (.02, .7):
            source = self.fixture_wav(f"sustain-{level}.wav", rate, 1,
                                      [level * math.sin(2*math.pi*32*i/rate) for i in range(rate * 2)])
            before = self.raw_samples(source)
            for name, controls in (("eq", eq), ("compressor", compressor)):
                output = self.directory / f"sustain-{level}-{name}.wav"
                media.render_post_denoise(source, output, controls, media.pcm_info(source))
                after = self.raw_samples(output)
                start, end = rate, rate * 2
                ratio = math.sqrt(sum(x*x for x in after[start:end]) / sum(x*x for x in before[start:end]))
                if name == "eq":
                    self.assertGreater(ratio, .97)
                    self.assertLess(ratio, 1.03)
                elif level < .1:
                    self.assertAlmostEqual(ratio, 1, places=4)
                else:
                    self.assertLess(ratio, .95)
                    self.assertGreaterEqual(ratio, .75)
                    # Gain control changes amplitude; it does not move the
                    # established waveform zero crossings/sample support.
                    crossings = lambda xs: [i for i in range(start+1,end) if xs[i-1] < 0 <= xs[i]]
                    self.assertEqual(crossings(before), crossings(after))

    def test_capture_preroll_reduces_initial_fan_and_preserves_32hz_attacks(self):
        for rate, channels, reduction_db in ((44100, 1, 8), (48000, 2, 12)):
            with self.subTest(rate=rate, channels=channels, reduction_db=reduction_db):
                rng = random.Random(914)
                count = rate * 3 + 137
                values = []
                attack = rate * 2 + 17
                for i in range(count):
                    fan = .008 * rng.uniform(-1, 1) + .003 * math.sin(2*math.pi*240*i/rate)
                    guitar = (.22 * math.sin(2*math.pi*32*i/rate)
                              + .06 * math.sin(2*math.pi*160*i/rate)) if i >= rate else 0
                    # A damped5ms pick burst has musical transient energy.
                    # One-sample impulses are tested separately for sample
                    # support, not promoted into an attack-fidelity guarantee.
                    pick = 0.
                    for position in (attack, count-round(.007*rate)):
                        offset = i-position
                        if 0 <= offset < round(.005*rate):
                            pick += .6 * math.exp(-offset/(.002*rate)) * math.cos(2*math.pi*2100*offset/rate)
                    sample = fan + guitar + pick
                    values.extend(sample * (1 if channel == 0 else .75) for channel in range(channels))
                source = self.fixture_wav(f"fan-{rate}.wav", rate, channels, values)
                profile = json.loads(self.profile("conservative3").read_text())
                profile.update(reduction_db=reduction_db, adaptivity=0, gain_smooth=0, noise_capture_seconds=[.2,.6],
                               noise_capture_authorized=True,
                               noise_capture_source_sha256=media.sha256(source))
                path = self.directory / f"capture-{rate}.json"
                path.write_text(json.dumps(profile))
                manifest = media.clean(source, path)
                before = self.raw_samples(source)[::channels]
                after = self.raw_samples(Path(manifest["run_dir"]) / "denoised.wav")[::channels]
                self.assertEqual(len(after), count)
                window = slice(round(.05*rate), round(.15*rate))
                reduction = 10*math.log10(sum(x*x for x in after[window]) / sum(x*x for x in before[window]))
                self.assertLess(reduction, -3, f"opening fan change {reduction:.2f} dB")
                # Compare the independently generated guitar's coherent32Hz
                # component, rather than mistaking lower noise for fidelity.
                component = lambda xs: 2/rate * abs(sum(xs[i]*complex(math.cos(2*math.pi*32*i/rate),
                                                                     -math.sin(2*math.pi*32*i/rate))
                                                          for i in range(rate*2,rate*3)))
                self.assertGreater(component(after), .22*.9)
                for position in (attack, count-round(.007*rate)):
                    extent = round(.005*rate)
                    before_peak = max(abs(x) for x in before[position:position+extent])
                    after_peak = max(abs(x) for x in after[position:position+extent])
                    self.assertGreater(after_peak, 10**(-1.5/20) * before_peak)
                    # Leading-sample amplitude can differ more than the burst
                    # peak; keep this separate3dB envelope budget explicit.
                    self.assertGreater(abs(after[position]), 10**(-3/20) * abs(before[position]))
                self.assertEqual(manifest["noise_capture"]["preroll_samples_removed"], round(.4*rate)+math.ceil(rate/10))
                self.assertEqual(manifest["dsp_latency"]["denoise"]["remaining_bulk_delay_samples"], 0)

    def test_strong_capture_delta_amplitude_damage_is_not_transparency(self):
        rate, count = 48000, 48000 * 2
        rng = random.Random(914)
        values = [.008*rng.uniform(-1,1) for _ in range(count)]
        position = rate + 17
        values[position] += .6
        source = self.fixture_wav("single-sample-damage.wav", rate, 1, values)
        profile = json.loads(self.profile("conservative3").read_text())
        profile.update(reduction_db=12, adaptivity=0, gain_smooth=0,
                       noise_capture_seconds=[.2,.6], noise_capture_authorized=True,
                       noise_capture_source_sha256=media.sha256(source))
        path = self.directory / "delta-capture.json"
        path.write_text(json.dumps(profile))
        manifest = media.clean(source, path)
        before = self.raw_samples(source)
        after = self.raw_samples(Path(manifest["run_dir"]) / "denoised.wav")
        peak = max(range(position-2,position+3), key=lambda i: abs(after[i]))
        self.assertEqual(peak, position)
        self.assertLess(abs(after[peak])/abs(before[position]), .85)
        self.assertFalse(manifest["frequency_preservation"]["music_preservation_listening_verified"])

    def test_clarity_clean_contract_keeps_denoise_residue_separate(self):
        rate = 44100
        source = self.fixture_wav("clarity.wav", rate, 2,
                                 [channel * .7 * math.sin(2*math.pi*32*i/rate)
                                  for i in range(rate*2+137) for channel in (1, .5)])
        profile = json.loads(self.profile("bypass").read_text())
        profile.update(peaking_eq=[{"frequency_hz": 300, "gain_db": -1.5, "q": .8},
                                   {"frequency_hz": 2200, "gain_db": 1, "q": .8}],
                       compressor={"threshold_db": -18, "ratio": 2, "attack_ms": 15,
                                   "release_ms": 100, "knee_db": 3})
        path = self.directory / "clarity.json"
        path.write_text(json.dumps(profile))
        manifest = media.clean(source, path)
        directory = Path(manifest["run_dir"])
        self.assertEqual(manifest["outputs"]["processed"], "processed.wav")
        self.assertEqual(manifest["restoration_stages"][-1]["input"], "processed.wav")
        self.assertEqual([stage["stage"] for stage in manifest["restoration_stages"]],
                         ["denoise_bypass", "peaking_eq_1", "peaking_eq_2", "rms_compressor",
                          "measured_loudness_normalization"])
        self.assertEqual(self.raw_samples(directory/"source.wav"), self.raw_samples(directory/"denoised.wav"))
        self.assertLess(max(abs(value) for value in self.raw_samples(directory/"residue.wav")), 1e-7)
        self.assertNotEqual(media.sha256(directory/"processed.wav"), media.sha256(directory/"denoised.wav"))
        self.assertEqual(media.sha256(directory/"processed.wav"), manifest["output_sha256"]["processed.wav"])
        for filename in manifest["outputs"].values():
            media.ensure_pcm_matches(directory/filename, manifest["pcm"])
        self.assertFalse(manifest["dsp_latency"]["post_denoise"]["complete_acoustic_alignment_verified"])


if __name__ == "__main__":
    unittest.main()
