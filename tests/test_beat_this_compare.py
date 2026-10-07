"""Beat This comparator, runtime setup, scorer and fixture tests (stub model; no network, no FFmpeg, no torch)."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.request
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import beat_this_compare as btc  # noqa: E402
import beat_this_runtime_setup as setup  # noqa: E402

RUN = 'artifacts/runs/20260101T000000Z-test'


def _no_network(*args, **kwargs):
    raise AssertionError('network access attempted in an offline test')


def pcm16_wav(seconds: float, rate: int = 8000, channels: int = 1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(b'\x00\x00' * int(seconds * rate) * channels)
    return buffer.getvalue()


def float_wav(samples: list[float], rate: int) -> bytes:
    data = struct.pack(f'<{len(samples)}f', *samples)
    fmt = struct.pack('<HHIIHH', 3, 1, rate, rate * 4, 4, 32)
    body = b'WAVE' + b'fmt ' + struct.pack('<I', len(fmt)) + fmt + b'data' + struct.pack('<I', len(data)) + data
    return b'RIFF' + struct.pack('<I', len(body)) + body


class Offline(unittest.TestCase):
    def setUp(self):
        for target in ('socket.socket', 'urllib.request.urlopen', 'socket.create_connection'):
            patcher = patch(target, side_effect=_no_network)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(os.path.realpath(self.tmp.name))

    # helpers -------------------------------------------------------------
    def registry(self, entry: dict | None = None, model_bytes: bytes | None = b'stub-checkpoint-bytes' * 10):
        (self.root / 'program').mkdir(exist_ok=True)
        (self.root / 'models').mkdir(exist_ok=True)
        if model_bytes is not None:
            (self.root / 'models' / f'{btc.MODEL_ID}.bin').write_bytes(model_bytes)
        digest = hashlib.sha256(model_bytes or b'').hexdigest()
        base = {'url': 'https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt', 'sha256': digest,
                'max_bytes': 1000, 'format': 'pytorch-lightning-ckpt', 'license': 'MIT', 'source_commit': 'x'}
        if entry is not None:
            base.update(entry)
        models = {btc.MODEL_ID: {k: v for k, v in base.items() if v is not None}}
        (self.root / 'program' / 'models.json').write_text(json.dumps({'schema_version': 1, 'models': models}))

    def run_dir(self, seconds: float = 2.0, origin=1.5, synthetic: bool = False, audio: bytes | None = None) -> Path:
        run = self.root / RUN
        run.mkdir(parents=True)
        audio = audio if audio is not None else pcm16_wav(seconds)
        (run / 'denoised.wav').write_bytes(audio)
        manifest = {'output_sha256': {'denoised.wav': hashlib.sha256(audio).hexdigest()},
                    'timeline': {'audio_start_seconds': origin, 'no_time_stretch': True},
                    'pcm': {'duration_seconds': seconds}, 'source': {'sha256': 'a' * 64}}
        if origin is None:
            del manifest['timeline']['audio_start_seconds']
        if synthetic:
            manifest['source'] = {'kind': 'generated_fixture', 'generator': 'test', 'seed': 1}
        (run / 'manifest.json').write_text(json.dumps(manifest))
        return run


class StubRunner:
    def __init__(self, beats=None, downbeats=None):
        self.calls = []
        self.beats = beats if beats is not None else [0.1 + 0.5 * k for k in range(8)]
        self.downbeats = downbeats if downbeats is not None else self.beats[::4]

    def __call__(self, wav_path, model, workdir, runtime):
        self.calls.append(wav_path)
        return {'beats': self.beats, 'downbeats': self.downbeats, 'python': '3.14.7',
                'versions': {'torch': '2.12.0', 'beat-this': '1.1.0'}}


def runtime_ok(root):
    return {'lock_sha256': setup.lock_sha256(), 'python': '3.14.7', 'machine': 'x86_64', 'versions': {'torch': '2.12.0', 'beat-this': '1.1.0'}}


class RefusalOrderTests(Offline):
    """M3: every row of contract table 3.1, fail closed, runner never invoked."""

    def call(self, **kwargs):
        runner = StubRunner()
        options = {'runner': runner, 'runtime_checker': runtime_ok, 'system': 'linux', 'click_grid_provider': lambda i: 0.25}
        options.update(kwargs)
        result = btc.compare(self.root, **options)
        return result, runner

    def assertRefused(self, result, runner, code):
        self.assertEqual(result['status'], 'refused', result)
        self.assertEqual(result['refusal_code'], code, result)
        self.assertEqual(runner.calls, [])
        self.assertFalse(result['network_used'])

    def test_1_model_not_registered(self):
        result, runner = self.call(run_dir=RUN)
        self.assertRefused(result, runner, 'model_not_registered')
        (self.root / 'program').mkdir()
        (self.root / 'program' / 'models.json').write_text(json.dumps({'schema_version': 1, 'models': {}}))
        result, runner = self.call(run_dir=RUN)
        self.assertRefused(result, runner, 'model_not_registered')

    def test_2_placeholder_hash_not_registered(self):
        self.registry({'sha256': 'TO_BE_FILLED_BY_ROOT_HASH_BOUND_FETCH'})
        result, runner = self.call(run_dir=RUN)
        self.assertRefused(result, runner, 'model_hash_not_registered')
        self.registry({'sha256': 'A' * 64})
        self.assertRefused(*self.call(run_dir=RUN), 'model_hash_not_registered')

    def test_3_registry_entry_invalid(self):
        for broken in ({'license': None}, {'max_bytes': True}, {'max_bytes': 0}, {'url': 'http://example.org/x'}):
            self.registry(broken)
            self.assertRefused(*self.call(run_dir=RUN), 'model_registry_entry_invalid')

    def test_4_model_file_missing_symlink_or_oversized(self):
        self.registry(model_bytes=None)
        self.assertRefused(*self.call(run_dir=RUN), 'model_file_missing')
        self.registry({'max_bytes': 5})
        self.assertRefused(*self.call(run_dir=RUN), 'model_file_missing')
        self.registry()
        model = self.root / 'models' / f'{btc.MODEL_ID}.bin'
        real = self.root / 'elsewhere.bin'
        model.rename(real)
        model.symlink_to(real)
        self.assertRefused(*self.call(run_dir=RUN), 'model_file_missing')

    def test_5_model_hash_mismatch(self):
        self.registry({'sha256': 'b' * 64})
        self.assertRefused(*self.call(run_dir=RUN), 'model_hash_mismatch')

    def test_6_runtime_not_qualified_with_default_checker(self):
        self.registry()
        result, runner = self.call(run_dir=RUN, runtime_checker=None)
        self.assertRefused(result, runner, 'runtime_not_qualified')

    def test_7_platform_unsupported(self):
        self.registry()
        self.assertRefused(*self.call(run_dir=RUN, system='darwin'), 'platform_unsupported')

    def test_8_input_rejected(self):
        self.registry()
        self.assertRefused(*self.call(run_dir='artifacts/elsewhere'), 'input_rejected')
        self.assertRefused(*self.call(run_dir='artifacts/runs/../runs/x'), 'input_rejected')
        run = self.run_dir()
        (run / 'denoised.wav').write_bytes(pcm16_wav(1.0))  # changed after manifest
        self.assertRefused(*self.call(run_dir=RUN), 'input_rejected')

    def test_8_input_rejected_symlink_origin_and_duration(self):
        self.registry()
        self.run_dir(origin=None)
        self.assertRefused(*self.call(run_dir=RUN), 'input_rejected')
        link = self.root / 'artifacts' / 'runs' / 'linked'
        link.symlink_to(self.root / RUN)
        self.assertRefused(*self.call(run_dir='artifacts/runs/linked'), 'input_rejected')

    def test_8_input_over_300_seconds(self):
        self.registry()
        self.run_dir(seconds=301, audio=pcm16_wav(301, rate=200))
        self.assertRefused(*self.call(run_dir=RUN), 'input_rejected')

    def test_generated_truth_refused_for_real_take(self):
        self.registry()
        self.run_dir()
        self.assertRefused(*self.call(run_dir=RUN, generated_truth=self.root / 'x.json'), 'input_rejected')


class EndToEndStubTests(Offline):
    """M4: stub runner end-to-end schema with all unknown fields at exact values."""

    def test_real_take_shaped_run(self):
        self.registry()
        self.run_dir(origin=1.5)
        runner = StubRunner()
        doc = btc.compare(self.root, run_dir=RUN, runner=runner, runtime_checker=runtime_ok, system='linux',
                          click_grid_provider=lambda item: 0.25)
        self.assertEqual(doc['status'], 'completed')
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(len(btc.UNKNOWN_FIELDS), 15)
        for key, value in btc.UNKNOWN_FIELDS.items():
            self.assertIn(key, doc)
            self.assertEqual(doc[key], value, key)
            self.assertIs(type(doc[key]), type(value))
        self.assertEqual(doc['meter_claim'], 'none')
        self.assertIsNone(doc['generated_truth_scores'])
        self.assertEqual(doc['generated_truth_scores_reason'], 'no_generated_truth')
        self.assertEqual(doc['beat_count'], 8)
        self.assertEqual(doc['downbeat_count'], 2)
        self.assertAlmostEqual(doc['beats'][0]['source_timeline_seconds'], 1.6)
        self.assertAlmostEqual(doc['median_ibi_seconds'], 0.5)
        self.assertAlmostEqual(doc['ibi_tempo_bpm'], 120.0)
        ratio = doc['half_double_ratio_vs_click_grid']
        self.assertEqual((ratio['status'], ratio['nearest_relation']), ('measured', '1/2'))
        self.assertAlmostEqual(ratio['ratio'], 0.5)
        self.assertTrue(doc['real_take'])
        self.assertEqual(doc['privacy'], 'V6_private_real_take_derived')
        self.assertEqual(doc['input_identity']['analysis_rate'], 22050)
        self.assertEqual(doc['input_identity']['resampling'], 'soxr_in_upstream_preprocess')
        self.assertEqual(set(doc['model_identity']), {'model_id', 'sha256', 'checkpoint', 'source_url', 'license', 'registry_sha256'})
        self.assertEqual(set(doc['runtime_identity']), {'lock_sha256', 'python', 'torch', 'beat_this_version', 'platform', 'host_label'})
        text = ' '.join(doc['limitations'])
        for phrase in ('model hypotheses', 'does not establish meter', 'not an identification of intended tempo'):
            self.assertIn(phrase, text)
        written = self.root / doc['output_dir'] / 'beat_this_comparison.json'
        self.assertTrue(written.is_file())
        self.assertTrue(written.is_relative_to(self.root / 'artifacts/s2/model_lanes'))
        self.assertEqual(sorted(p.name for p in (self.root / RUN).iterdir()), ['denoised.wav', 'manifest.json'])

    def test_no_click_grid_and_dev_fixture_truth_scores(self):
        self.registry()
        suite = btc.generate_suite(self.root, 'dev-test', 'dev', [3001], duration=4.0, cohorts=('c1-chug178',))
        truth = json.loads((suite / 'truth' / 'c1-chug178-s3001.json').read_text())
        runner = StubRunner(beats=truth['beats'], downbeats=truth['downbeats'])
        doc = btc.compare(self.root, fixture_wav=suite / 'cases' / 'c1-chug178-s3001.wav',
                          generated_truth=suite / 'truth' / 'c1-chug178-s3001.json', runner=runner,
                          runtime_checker=runtime_ok, system='linux', click_grid_provider=lambda item: None)
        self.assertEqual(doc['status'], 'completed', doc)
        self.assertFalse(doc['real_take'])
        self.assertNotIn('privacy', doc)
        self.assertEqual(doc['half_double_ratio_vs_click_grid']['status'], 'no_click_grid')
        self.assertEqual(doc['half_double_ratio_vs_construction_click']['nearest_relation'], '1')
        self.assertEqual(doc['generated_truth_scores']['beat']['f_measure'], 1.0)
        self.assertEqual(doc['generated_truth_scores']['downbeat']['f_measure'], 1.0)


class F70Tests(unittest.TestCase):
    """M5: six hand cases at the 70 ms tolerance."""

    def test_perfect(self):
        self.assertEqual(btc.f70([1, 2, 3], [1, 2, 3])['f_measure'], 1.0)

    def test_69_ms_matches(self):
        r = btc.f70([1.0, 2.0], [1.069, 1.931])
        self.assertEqual((r['tp'], r['f_measure']), (2, 1.0))

    def test_71_ms_misses(self):
        r = btc.f70([1.0, 2.0], [1.071, 1.929])
        self.assertEqual((r['tp'], r['f_measure']), (0, 0.0))

    def test_duplicates_count_once(self):
        r = btc.f70([1.0], [0.99, 1.01])
        self.assertEqual((r['tp'], r['pred_count']), (1, 2))
        self.assertAlmostEqual(r['precision'], 0.5)
        self.assertAlmostEqual(r['recall'], 1.0)

    def test_empty_truth_is_null_with_reason(self):
        r = btc.f70([], [1.0])
        self.assertIsNone(r['recall'])
        self.assertIsNone(r['f_measure'])
        self.assertEqual(r['f_null_reason'], 'empty_truth')

    def test_empty_prediction_is_null_with_reason(self):
        r = btc.f70([1.0], [])
        self.assertIsNone(r['precision'])
        self.assertEqual(r['precision_null_reason'], 'no_predictions')
        self.assertIsNone(r['f_measure'])

    def test_pooled_sums_not_averaged_rates(self):
        p = btc.pooled([{'tp': 1, 'truth_count': 1, 'pred_count': 1}, {'tp': 0, 'truth_count': 9, 'pred_count': 9}])
        self.assertAlmostEqual(p['f_measure'], 0.1)


class HalfDoubleTests(unittest.TestCase):
    """M6: seven relations, the 4 % boundary, no grid."""

    def beats(self, ibi: float, n: int = 8):
        return [k * ibi for k in range(n)]

    def test_each_relation(self):
        for name, value in btc.RELATIONS:
            result = btc.half_double(0.5 * value, self.beats(0.5))
            self.assertEqual((result['status'], result['nearest_relation']), ('measured', name), name)

    def test_three_percent_is_related(self):
        self.assertEqual(btc.half_double(0.5 * 2 * 1.03, self.beats(0.5))['nearest_relation'], '2')

    def test_five_percent_is_unrelated(self):
        result = btc.half_double(0.5 * 2 * 1.05, self.beats(0.5))
        self.assertEqual(result['nearest_relation'], 'unrelated')
        self.assertAlmostEqual(result['relative_error'], 0.05)

    def test_no_grid_and_insufficient_beats(self):
        self.assertEqual(btc.half_double(None, self.beats(0.5))['status'], 'no_click_grid')
        self.assertIsNone(btc.half_double(None, self.beats(0.5))['ratio'])
        self.assertEqual(btc.half_double(0.5, self.beats(0.5, 3))['status'], 'insufficient_beats')


class RuntimeSetupTests(Offline):
    """M7: lock self-hash, non-Linux refusal, --check never downloads or installs."""

    def test_lock_self_hash(self):
        self.assertEqual(setup.lock_sha256(), setup.LOCK_SHA)
        setup.verified_lock()
        tampered = json.loads(json.dumps(setup.LOCK))
        tampered['packages'][0]['sha256'] = '0' * 64
        with self.assertRaises(setup.Refused) as ctx:
            setup.verified_lock(tampered)
        self.assertEqual(ctx.exception.code, 'lock_identity_mismatch')

    def test_non_linux_refuses(self):
        with self.assertRaises(setup.Refused) as ctx:
            setup.check(self.root, system='darwin')
        self.assertEqual(ctx.exception.code, 'platform_unsupported')
        with patch.object(setup.sys, 'platform', 'darwin'), patch('builtins.print') as printed:
            self.assertEqual(setup.main(['--check']), 2)
        self.assertEqual(json.loads(printed.call_args[0][0])['refusal_code'], 'platform_unsupported')

    def test_check_is_read_only(self):
        with patch.object(setup, 'fetch', side_effect=AssertionError('fetch during check')), \
             patch.object(setup, 'extract', side_effect=AssertionError('install during check')):
            with self.assertRaises(setup.Refused) as ctx:
                setup.check(self.root, system='linux', machine='x86_64')
        self.assertEqual(ctx.exception.code, 'runtime_missing')
        self.assertEqual(list(self.root.iterdir()), [])

    def test_lock_hosts_and_machines(self):
        for machine in ('x86_64', 'aarch64'):
            names = sorted(p['name'] for p in setup.selected_packages(setup.LOCK, machine))
            self.assertEqual(names, ['beat-this', 'einops', 'rotary-embedding-torch', 'soxr'])
        with self.assertRaises(setup.Refused):
            setup.selected_packages(setup.LOCK, 'riscv64')
        self.assertTrue(all(p['url'].startswith('https://files.pythonhosted.org/') for p in setup.LOCK['packages']))


class FixtureAndSealTests(Offline):
    def test_determinism_and_truth_separation(self):
        audio1, truth1 = btc.generate_fixture('c1-chug178', 3001, duration=4.0)
        audio2, truth2 = btc.generate_fixture('c1-chug178', 3001, duration=4.0)
        self.assertEqual(hashlib.sha256(audio1).hexdigest(), hashlib.sha256(audio2).hexdigest())
        self.assertEqual(truth1, truth2)
        with wave.open(io.BytesIO(audio1)) as reader:
            self.assertEqual((reader.getframerate(), reader.getnchannels(), reader.getsampwidth()), (48000, 1, 2))
        self.assertNotIn(b'beats', audio1)
        self.assertAlmostEqual(truth1['construction_click_period_seconds'], 60 / 178)
        self.assertEqual(len(truth1['downbeats']), len(truth1['beats'][::4]))

    def test_negative_cohort_has_empty_truth(self):
        _, truth = btc.generate_fixture('c8-negative', 3001, duration=1.0)
        self.assertEqual((truth['beats'], truth['downbeats'], truth['click_times']), ([], [], []))

    def test_seeds_are_sealed(self):
        with self.assertRaises(ValueError):
            btc.generate_suite(self.root, 'x', 'heldout', [3101, 1009], 1.0)
        with self.assertRaises(ValueError):
            btc.generate_suite(self.root, 'y', 'dev', [3101], 1.0)

    def test_predict_never_opens_truth_then_seal_then_score(self):
        suite = btc.generate_suite(self.root, 'heldout-test', 'heldout', [3101, 3203], duration=2.0, cohorts=('c1-chug178', 'c8-negative'))
        for path in (suite / 'truth').iterdir():
            path.chmod(0o000)
        a0 = lambda wav, duration: {'beats': [0.5, 1.0, 1.5], 'basis': 'click_grid', 'click_grid_period_seconds': 60 / 178}
        a1 = lambda wav: {'status': 'completed', 'beats': [{'model_seconds': t} for t in (0.6, 0.94, 1.28, 1.61)],
                          'downbeats': [{'model_seconds': 0.6}], 'model_identity': {}, 'runtime_identity': {}}
        real_open = open

        def guarded_open(file, *args, **kwargs):
            if '/truth/' in str(file):
                raise AssertionError('prediction step opened truth')
            return real_open(file, *args, **kwargs)

        with patch('builtins.open', guarded_open):
            btc.predict(self.root, suite, 'A0', a0=a0)
            btc.predict(self.root, suite, 'A1', a1=a1)
        with self.assertRaises(ValueError):
            btc.score(self.root, suite)  # no seal yet
        btc.seal(self.root, suite)
        with self.assertRaises(ValueError):
            btc.predict(self.root, suite, 'A0', a0=a0)  # sealed predictions are immutable
        for path in (suite / 'truth').iterdir():
            path.chmod(0o400)
        result = btc.score(self.root, suite)
        self.assertEqual(result['decision']['default_adoption'], False)
        self.assertIn(result['decision']['outcome'], ('A1 better on generated fixtures', 'no improvement shown'))
        self.assertIsNone(result['arms']['A0']['downbeat_f70_overall'])
        self.assertEqual(result['arms']['A0']['downbeat_null_reason'], 'arm_has_no_downbeats')
        self.assertEqual(result['arms']['A1']['c8_false_beats_per_minute']['predicted'], 8)
        self.assertEqual(result['arms']['A1']['half_double_relation_counts']['denominator_cases'], 2)
        (suite / 'scores.json').unlink()
        prediction = suite / 'predictions' / 'A1' / 'c1-chug178-s3101.json'
        prediction.write_text(prediction.read_text().replace('0.6', '0.7'))
        with self.assertRaises(ValueError):
            btc.score(self.root, suite)

    def test_dev_suite_is_never_scored(self):
        suite = btc.generate_suite(self.root, 'dev-only', 'dev', [3001], duration=1.0, cohorts=('c8-negative',))
        btc.predict(self.root, suite, 'A0', a0=lambda wav, d: {'beats': [], 'basis': 'none', 'click_grid_period_seconds': None})
        btc.seal(self.root, suite, ('A0',))
        with self.assertRaises(ValueError):
            btc.score(self.root, suite)


class WavReaderTests(Offline):
    def test_float_and_pcm_readers(self):
        path = self.root / 'f.wav'
        path.write_bytes(float_wav([0.0, 0.5, -0.5, 0.25], 4))
        samples, rate = btc.read_wav_mono(path)
        self.assertEqual((rate, samples), (4, [0.0, 0.5, -0.5, 0.25]))
        self.assertEqual(btc.wav_header(path)['format'], 'float')
        stereo = self.root / 's.wav'
        stereo.write_bytes(pcm16_wav(0.5, rate=100, channels=2))
        self.assertEqual(btc.wav_header(stereo)['channels'], 2)
        self.assertEqual(len(btc.read_wav_mono(stereo, 0.1, 0.3)[0]), 20)


if __name__ == '__main__':
    unittest.main()
