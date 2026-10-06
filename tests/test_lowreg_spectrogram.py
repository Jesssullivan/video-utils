"""Low-register spectrogram v1 (V4) reference tests: golden, parity, geometry, refusals.

Contract: docs/spec/sprints/LOWREG_SPEC_S2.md (metrics M1-M11). One stdlib render
of the generated fixture is shared by the module; tests never write the golden.
"""
import array
import contextlib
import io
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('lowreg_spectrogram', ROOT / 'scripts/lowreg_spectrogram.py')
L = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(L)

GOLDEN = ROOT / 'tests/fixtures/lowreg-golden-v1.json'
MACHINE_SPEC = ROOT / 'program/spectrogram-lowreg-v1.json'
HAS_NUMPY = importlib.util.find_spec('numpy') is not None

STATE = {}


def setUpModule():
    tmp = Path(tempfile.mkdtemp(prefix='lowreg-test-'))
    STATE['tmp'] = tmp
    wav = tmp / 'fixture.wav'
    STATE['fixture_record'] = L.write_fixture(wav)
    STATE['wav'] = wav
    STATE['sha_before'] = L.sha256_file(wav)
    keep = {}
    STATE['payload'] = L.render(wav, tmp / 'render', keep=keep)
    STATE['sha_after'] = L.sha256_file(wav)
    STATE['result'] = keep
    pcm, clipped = L.fixture_pcm()
    STATE['pcm'] = pcm
    STATE['regenerated'] = L.assemble_golden(keep, pcm, clipped, L.load_spec())
    STATE['golden'] = json.loads(GOLDEN.read_text())


def tearDownModule():
    shutil.rmtree(STATE['tmp'], ignore_errors=True)


def write_wav(path, rate=8000, width=2, channels=1, frames=5000):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(bytes(width * channels * frames))
    return path


class SpecTests(unittest.TestCase):
    def test_m3_spec_identity_machine_spec_and_golden(self):
        spec = json.loads(MACHINE_SPEC.read_text())
        recomputed = L.spec_hash(spec)
        self.assertEqual(recomputed, spec['spec_sha256'])
        self.assertEqual(recomputed, STATE['golden']['spec_sha256'])
        self.assertEqual(L.load_spec()['spec_sha256'], recomputed)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(L.main(['spec', '--sha']), 0)
        self.assertEqual(out.getvalue().strip(), recomputed)

    def test_machine_spec_carries_frozen_values(self):
        p = json.loads(MACHINE_SPEC.read_text())['parameters']
        self.assertEqual((p['analysis_rate_hz'], p['n_fft'], p['hop_samples']), (8000, 4096, 160))
        self.assertEqual((p['fmin_hz'], p['fmax_hz'], p['bins_per_octave'], p['n_bands']), (20.0, 2000.0, 24, 160))
        self.assertEqual((p['temporal_support_seconds'], p['hop_seconds'], p['fft_bin_spacing_hz']), (0.512, 0.02, 1.953125))
        self.assertEqual(p['spectrum_policy'], 'power')
        self.assertFalse(p['one_sided_doubling'])
        self.assertIn('not_part_of_v1', p['magnitude_filterbank'])
        pc = p['pcen']
        self.assertEqual((pc['gain'], pc['bias'], pc['power'], pc['time_constant_seconds'], pc['eps']),
                         (0.98, 2.0, 0.5, 0.4, 1e-6))
        self.assertEqual(pc['input_scale'], 2.0 ** 31)
        self.assertFalse(pc['reset_on_block_boundary'])
        self.assertAlmostEqual(pc['smoother_coefficient'], 0.0487656, places=7)
        spec = json.loads(MACHINE_SPEC.read_text())
        self.assertEqual(spec['pitch_resolution_claim'], 'none')
        self.assertEqual(spec['adoption'], 'none')

    def test_m6_geometry(self):
        centres = L.band_centres()
        self.assertEqual(len(centres), 160)
        for k, fk in enumerate(centres):
            self.assertEqual(fk, 20 * 2 ** (k / 24))
        self.assertEqual(centres[0], 20.0)  # no 80 Hz or 400 Hz floor
        self.assertLessEqual(centres[-1], 2000.0)
        self.assertGreater(20 * 2 ** (160 / 24), 2000.0)
        self.assertAlmostEqual(centres[-1], 1974.03, places=2)
        bank = L.filterbank()
        self.assertEqual(len(bank), 160)
        nonempty = sum(1 for _, w in bank if w and any(v > 0 for v in w))
        unit = sum(1 for _, w in bank if abs(math.fsum(w) - 1) <= 1e-12)
        self.assertEqual((nonempty, unit), (160, 160))
        # Below the interpolation threshold a filter touches at most two FFT bins.
        threshold = min(L.INTERPOLATED_BELOW_LEFT_HZ, L.INTERPOLATED_BELOW_RIGHT_HZ)
        low = [w for fk, (_, w) in zip(centres, bank) if fk < threshold]
        self.assertTrue(low)
        self.assertTrue(all(sum(1 for v in w if v > 0) <= 2 for w in low))
        self.assertAlmostEqual(L.INTERPOLATED_BELOW_LEFT_HZ, 68.61, places=2)
        self.assertAlmostEqual(L.INTERPOLATED_BELOW_RIGHT_HZ, 66.65, places=2)
        self.assertEqual(L.frame_count(19200), 95)
        self.assertEqual(L.frame_count(4096), 1)
        self.assertEqual(L.frame_centre_seconds(0), 0.256)
        self.assertAlmostEqual(L.frame_centre_seconds(17), 0.596, places=12)
        hann = L.periodic_hann()
        self.assertEqual(len(hann), 4096)
        self.assertAlmostEqual(math.fsum(hann), L.WINDOW_SUM, places=9)
        self.assertEqual(hann[0], 0.0)


class FixtureTests(unittest.TestCase):
    def test_m2_fixture_identity(self):
        fixture = STATE['golden']['fixture']
        record = STATE['fixture_record']
        self.assertEqual(record['wav_sha256'], fixture['wav_sha256'])
        self.assertEqual(record['pcm_sha256'], fixture['pcm_sha256'])
        self.assertEqual(record['n_samples'], 19200)
        self.assertEqual(record['clipped_samples'], 0)
        self.assertEqual(record['bytes'], 44 + 2 * 19200)

    def test_m11_input_invariance(self):
        self.assertEqual(STATE['sha_before'], STATE['sha_after'])
        inp = STATE['payload']['input']
        self.assertTrue(inp['unchanged'])
        self.assertEqual(inp['sha256'], STATE['sha_before'])
        self.assertEqual(inp['signal_version'], 'sha256:' + STATE['sha_before'])

    def test_fixture_refuses_existing_path(self):
        before = L.sha256_file(STATE['wav'])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(L.main(['fixture', '--out', str(STATE['wav'])]), 2)
        self.assertEqual(L.sha256_file(STATE['wav']), before)

    def test_render_outputs_and_declared_unknowns(self):
        out = STATE['tmp'] / 'render'
        written = json.loads((out / 'render.json').read_text())
        self.assertEqual(written, json.loads(json.dumps(STATE['payload'])))
        for name in L.MATRICES:
            raw = (out / f'{name}.f64le').read_bytes()
            self.assertEqual(L.sha256_bytes(raw), written['files'][name]['sha256'])
            data = array.array('d')
            data.frombytes(raw)
            if __import__('sys').byteorder == 'big':
                data.byteswap()
            self.assertEqual(len(data), 95 * 160)
            self.assertEqual(list(data), [v for row in STATE['result'][name] for v in row])
        self.assertEqual(written['spec_version'], 'lowreg-spectrogram-v1')
        self.assertEqual(written['pitch_resolution_claim'], 'none')
        for key in ('note_identity', 'intended_note_reference', 'tonic', 'mode', 'onset_timing',
                    'resampler', 'resampler_group_delay_samples'):
            self.assertIn(key, written)
            self.assertIsNone(written[key])
            self.assertTrue(written['null_reasons'][key] if key != 'resampler' else True)
        self.assertIn('attack branch', written['null_reasons']['onset_timing'])
        self.assertEqual((written['temporal_support_seconds'], written['hop_seconds']), (0.512, 0.02))
        self.assertIn('84.27', written['temporal_caveat'])
        self.assertEqual(written['coverage']['head_partial_support_seconds'], [0.0, 0.256])
        self.assertEqual(written['coverage']['tail_partial_support_seconds'], [2.136, 2.4])
        self.assertEqual(written['coverage']['unanalysed_tail_samples'], 64)
        self.assertEqual(written['calibration']['scale'], 'uncalibrated_digital_scale')
        self.assertEqual(written['calibration']['microphone_response'], 'unknown')
        self.assertEqual(written['denoise_or_profile_applied'], 'unknown')
        self.assertEqual(written['pcen_status'], 'experimental_fixed_knobs_not_tuned')
        self.assertEqual(written['baseline'], 'log-power (log-mel remains project baseline)')
        self.assertEqual(written['listening_acceptance'], 'not_assessed')
        self.assertEqual(written['adoption'], 'none')
        self.assertEqual((written['input']['sample_rate'], written['input']['channels'], written['input']['downmix']),
                         (8000, 1, 'none_mono'))


class GoldenTests(unittest.TestCase):
    def test_m1_golden_regeneration(self):
        report = L.compare_golden(STATE['golden'], STATE['regenerated'])
        self.assertEqual((report['values_matched'], report['values_total']), (1910, 1910))
        self.assertEqual(STATE['golden']['stored_value_count'], 1910)
        self.assertIsNone(STATE['golden']['reduction'])
        self.assertEqual((report['aggregates_matched'], report['shape_matched']), (6, 2))
        self.assertTrue(all(report['identities'].values()))
        self.assertTrue(report['ok'])
        self.assertEqual(STATE['golden']['shape'], {'frames': 95, 'bands': 160})
        self.assertEqual(STATE['golden']['backend'], 'stdlib')
        self.assertEqual(STATE['golden']['tolerance']['abs'], 1e-9)
        self.assertEqual(STATE['golden']['tolerance']['rel'], 1e-9)

    def test_m7_low_register_retained(self):
        d = STATE['result']['log_power_db']
        self.assertGreaterEqual(d[94][17] - d[0][17], 20.0)

    def test_m8_steady_tone_separation_not_a_note_claim(self):
        d = STATE['result']['log_power_db']
        self.assertGreaterEqual(d[94][17] - d[94][28], 10.0)
        self.assertEqual(STATE['golden']['pitch_resolution_claim'], 'none')
        self.assertIsNone(STATE['golden']['note_identity'])

    def test_m10_golden_size(self):
        self.assertLessEqual(GOLDEN.stat().st_size, 50_000)

    def test_golden_declares_unknowns_and_indices(self):
        g = STATE['golden']
        self.assertEqual(g['schema'], 'lowreg-golden-v1')
        self.assertEqual(g['stored_frames'], [0, 17, 94])
        self.assertEqual(g['stored_bins'], [0, 17, 28, 41, 150])
        self.assertEqual(g['stored_frame_centre_seconds'], [0.256, 0.596, 2.136])
        self.assertEqual([round(f, 2) for f in g['stored_bin_centre_hz']], [20.0, 32.68, 44.9, 65.36, 1522.19])
        for key in ('note_identity', 'intended_note_reference', 'tonic', 'mode', 'onset_timing'):
            self.assertIsNone(g[key])
        self.assertEqual(g['listening_acceptance'], 'not_assessed')
        self.assertEqual(g['adoption'], 'none')
        self.assertEqual(g['generator']['role'], 'provenance_only_not_a_test_gate')

    def test_golden_write_refuses_existing(self):
        before = L.sha256_file(GOLDEN)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(L.main(['golden', '--write', str(GOLDEN)]), 2)
        self.assertEqual(L.sha256_file(GOLDEN), before)


class StreamingTests(unittest.TestCase):
    def test_m5_streamed_equals_batch_exactly(self):
        energy = STATE['result']['band_energy']
        batch = STATE['result']['pcen']
        self.assertEqual(L.pcen(energy), batch)
        for size in (1, 7, 95):
            state = L.PcenState()
            out = []
            for start in range(0, len(energy), size):
                out.extend(state.process(energy[start:start + size]))
            equal = sum(a == b for ra, rb in zip(out, batch) for a, b in zip(ra, rb))
            self.assertEqual((equal, len(out)), (15200, 95), size)
            self.assertEqual(state.frames, 95)

    def test_reset_per_block_would_differ(self):
        energy = STATE['result']['band_energy']
        reset = []
        for start in range(0, len(energy), 7):
            reset.extend(L.PcenState().process(energy[start:start + 7]))
        self.assertNotEqual(reset, STATE['result']['pcen'])


class RefusalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='lowreg-refusal-'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def refused(self, wav, out_dir=None, extra=()):
        out_dir = out_dir or self.tmp / 'out'
        before = L.sha256_file(wav) if Path(wav).exists() else None
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = L.main(['render', '--wav', str(wav), '--out-dir', str(out_dir), *extra])
        self.assertIn('refused:', err.getvalue())
        self.assertEqual(code, 2)
        if before is not None:
            self.assertEqual(L.sha256_file(wav), before)
        return out_dir

    def test_m9_refusals(self):
        count = 0
        out = self.refused(write_wav(self.tmp / 'r16k.wav', rate=16000))
        self.assertFalse(out.exists())
        count += 1
        out = self.refused(write_wav(self.tmp / 'u8.wav', width=1))
        self.refused(write_wav(self.tmp / 's24.wav', width=3))
        float_wav = self.tmp / 'float.wav'
        raw = bytearray((self.tmp / 'u8.wav').read_bytes())
        raw[20:22] = (3).to_bytes(2, 'little')  # WAVE_FORMAT_IEEE_FLOAT
        float_wav.write_bytes(bytes(raw))
        self.refused(float_wav)
        self.assertFalse(out.exists())
        count += 1
        out = self.refused(write_wav(self.tmp / 'short.wav', frames=4095))
        self.assertFalse(out.exists())
        count += 1
        out_dir = self.tmp / 'existing'
        out_dir.mkdir()
        (out_dir / 'render.json').write_text('keep')
        self.refused(STATE['wav'], out_dir)
        self.assertEqual((out_dir / 'render.json').read_text(), 'keep')
        self.assertEqual(sorted(p.name for p in out_dir.iterdir()), ['render.json'])
        count += 1
        link = self.tmp / 'link.wav'
        os.symlink(STATE['wav'], link)
        out = self.refused(link)
        self.assertFalse(out.exists())
        empty = self.tmp / 'empty'
        empty.mkdir()
        link_dir = self.tmp / 'link-out'
        os.symlink(empty, link_dir)
        self.refused(STATE['wav'], link_dir)
        self.assertEqual(list(empty.iterdir()), [])
        count += 1
        for bad in (float('nan'), float('inf')):
            samples = [0.0] * 4096
            samples[100] = bad
            with self.assertRaises(L.Refusal):
                L.render_samples(samples)
        with self.assertRaises(L.Refusal):
            L.PcenState().process([[float('nan')] * 160])
        count += 1
        spec = json.loads(MACHINE_SPEC.read_text())
        tampered = dict(spec, parameters=dict(spec['parameters'], fmin_hz=80.0))
        bad_hash = self.tmp / 'bad-hash.json'
        bad_hash.write_text(json.dumps(tampered))
        out = self.refused(STATE['wav'], extra=('--spec', str(bad_hash)))
        rehashed = dict(tampered)
        rehashed['spec_sha256'] = L.spec_hash(rehashed)
        bad_params = self.tmp / 'bad-params.json'
        bad_params.write_text(json.dumps(rehashed))
        self.refused(STATE['wav'], extra=('--spec', str(bad_params)))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(L.main(['spec', '--sha', '--spec', str(bad_hash)]), 1)
        self.assertFalse(out.exists())
        count += 1
        self.assertEqual(count, 7)

    def test_resampler_record_binding(self):
        record = self.tmp / 'resample.json'
        record.write_text(json.dumps({'command': 'ffmpeg -ar 8000', 'tool_version': '8.1.2', 'output_sha256': 'ab'}))
        with self.assertRaises(L.Refusal):
            L._load_resampler_record(record, 'cd')
        bound = L._load_resampler_record(record, 'ab')
        self.assertEqual(bound['evidence'], 'caller_supplied')
        fields = L.declared_fields({}, bound, L.load_spec())
        self.assertIsNone(fields['resampler_group_delay_samples'])
        self.assertIn('unmeasured', fields['null_reasons']['resampler_group_delay_samples'])

    def test_multichannel_mean_downmix(self):
        path = self.tmp / 'stereo.wav'
        left = array.array('h', [1000] * 4096)
        right = array.array('h', [-3000] * 4096)
        inter = array.array('h', [v for pair in zip(left, right) for v in pair])
        if __import__('sys').byteorder == 'big':
            inter.byteswap()
        with wave.open(str(path), 'wb') as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(8000)
            w.writeframes(inter.tobytes())
        samples, meta = L.read_wav(path)
        self.assertEqual(meta['downmix'], 'arithmetic_mean_of_channels_float64')
        self.assertEqual(samples[0], (1000 / 32768.0 + -3000 / 32768.0) / 2)


@unittest.skipUnless(HAS_NUMPY, 'numpy not importable')
class NumpyParityTests(unittest.TestCase):
    def test_m4_numpy_matches_stdlib_full_matrix(self):
        samples = [v / 32768.0 for v in STATE['pcm']]
        result = L.render_samples(samples, 'numpy')
        cells = matched = 0
        for name in L.MATRICES:
            for ra, rb in zip(result[name], STATE['result'][name]):
                for a, b in zip(ra, rb):
                    cells += 1
                    matched += math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
        self.assertEqual((matched, cells), (30400, 30400))
        regenerated = L.assemble_golden(result, STATE['pcm'], 0, L.load_spec())
        self.assertTrue(L.compare_golden(STATE['golden'], regenerated)['ok'])


if __name__ == '__main__':
    unittest.main()
