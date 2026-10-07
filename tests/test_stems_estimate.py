"""stems_estimate worker, refusal ladder, fake-separator runtime path, low-end accounting, SRC round trip,
timeline, drafts and the s3-stems-1 harness (contract docs/spec/sprints/STEMS_S3.md section 10).

No network, no torch, no weights. FFmpeg is needed only for M7a (FFMPEG env var or PATH).
"""
from __future__ import annotations

import array
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.request
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import stems_estimate as se  # noqa: E402

HEAVY = ('torch', 'torchaudio', 'demucs', 'numpy')
HEAVY_AT_IMPORT = {m for m in HEAVY if m in sys.modules}
RUN = 'artifacts/runs/20260101T000000Z-stems'
C1, C4 = 32.70, 261.6
# Contract section 7 top-level keys and 7.1 values, written out independently of the module.
CONTRACT_KEYS = {'schema_version', 'status', 'tool', 'model_identity', 'runtime_identity', 'input_identity', 'excerpt',
                 'analysed_input', 'stems', 'low_end_check', 'mixture_consistency', 'resource_receipt', 'privacy',
                 'limitations', 'estimate_from_mono_mixture', 'recovered_original_stem', 'stem_semantics',
                 'instrument_presence_claim', 'separation_accuracy', 'low_end_preservation_verdict', 'listening_accepted',
                 'bleed_artifact_review', 'default_adoption', 'cleanup_default', 'master_eligible', 'in_room_tone_recreated',
                 'note_correctness', 'performance_issue', 'expected_rhythm_reference', 'claim_class', 'redistribution_permitted'}
CONTRACT_UNKNOWN = {'estimate_from_mono_mixture': True, 'recovered_original_stem': False,
                    'stem_semantics': 'model_target_allocation_not_instrument_identity', 'instrument_presence_claim': 'none',
                    'separation_accuracy': 'unknown', 'low_end_preservation_verdict': None, 'listening_accepted': False,
                    'bleed_artifact_review': 'not_performed', 'default_adoption': False, 'cleanup_default': False,
                    'master_eligible': False, 'in_room_tone_recreated': False, 'note_correctness': None,
                    'performance_issue': None, 'expected_rhythm_reference': None, 'claim_class': 'model_output_measurement',
                    'redistribution_permitted': False}
REFUSAL_KEYS = {'schema_version', 'status', 'refusal_code', 'message', 'runtime_reason', 'model_id', 'network_used',
                'model_acquired', 'default_adoption', 'recovered_original_stem'}


def _no_network(*args, **kwargs):
    raise AssertionError('network access attempted in an offline test')


def tones(rate: int, seconds: float, parts=((C1, .3), (C4, .2))) -> list[float]:
    n = int(round(rate * seconds))
    return [math.fsum(a * math.sin(2 * math.pi * f * i / rate) for f, a in parts) for i in range(n)]


def pcm16_bytes(samples: list[float], rate: int, channels: int = 1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        frames = array.array('h', (max(-32768, min(32767, int(round(v * 32767)))) for v in samples for _ in range(channels)))
        writer.writeframes(frames.tobytes())
    return buffer.getvalue()


def zeros(n: int) -> list[float]:
    return [0.0] * n


def six(guitar=None, bass=None, other=None, n: int = 0) -> dict:
    out = {name: [zeros(n), zeros(n)] for name in se.SOURCES}
    for name, value in (('guitar', guitar), ('bass', bass), ('other', other)):
        if value is not None:
            out[name] = [list(value), list(value)]
    return out


class IdentitySeparator:
    """guitar := input; every other target silent."""
    def __call__(self, stereo, model, workdir):
        return six(guitar=stereo[0], n=len(stereo[0]))


class ScaleSeparator:
    """guitar := input x 0.5 (-6.02 dB); other := the rest."""
    def __call__(self, stereo, model, workdir):
        half = [v * .5 for v in stereo[0]]
        return six(guitar=half, other=half, n=len(stereo[0]))


class LowToBassSeparator:
    """Stdlib 45 Hz biquad split: guitar := 12 cascaded RBJ high-pass biquads (Q 0.7071) at 45 Hz; bass := input - guitar."""
    def __call__(self, stereo, model, workdir):
        high = stereo[0]
        for _ in range(12):
            high = se.biquad(high, se.biquad_coefficients('highpass', 45.0, 0.7071, se.MODEL_RATE))
        low = [x - h for x, h in zip(stereo[0], high)]
        return six(guitar=high, bass=low, n=len(stereo[0]))


def fake_runtime(root):
    return {'kind': 'injected_fake', 'python': 'injected-fake', 'torch': None, 'demucs': None, 'platform': 'test-fake'}


class Offline(unittest.TestCase):
    def setUp(self):
        for target in ('socket.socket', 'socket.create_connection', 'urllib.request.urlopen'):
            patcher = patch(target, side_effect=_no_network)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(os.path.realpath(self.tmp.name))

    def assertHeavyAbsent(self):
        for module in HEAVY:
            if module not in HEAVY_AT_IMPORT:
                self.assertNotIn(module, sys.modules)

    # registry ------------------------------------------------------------
    def registry(self, entry: dict | None = None, model_bytes: bytes | None = None, drop: tuple = ()):
        (self.root / 'program').mkdir(exist_ok=True)
        (self.root / 'models').mkdir(exist_ok=True)
        model_bytes = os.urandom(512) if model_bytes is None else model_bytes
        (self.root / 'models' / f'{se.MODEL_ID}.bin').write_bytes(model_bytes)
        base = {'url': 'https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/5c90dfd2-34c22ccb.th',
                'sha256': hashlib.sha256(model_bytes).hexdigest(), 'max_bytes': 4096,
                'license': 'personal/research only (maintainer statements)', 'license_verdict': 'admissible_private_comparator',
                'operator_terms_acknowledgement': 'docs/agent-notes/test-ack.json'}
        base.update(entry or {})
        for key in drop:
            base.pop(key, None)
        (self.root / 'program' / 'models.json').write_text(json.dumps({'schema_version': 1, 'models': {se.MODEL_ID: base}}))

    # run-shaped inputs ---------------------------------------------------
    def run_dir(self, audio: bytes | None = None, origin=0.0, synthetic=False, rel: str = RUN, source_sha='b' * 64,
                bind: bytes | None = None) -> Path:
        run = self.root / rel
        run.mkdir(parents=True)
        audio = pcm16_bytes(tones(44100, 2.0), 44100) if audio is None else audio
        (run / 'denoised.wav').write_bytes(audio)
        (run / 'source.wav').write_bytes(audio)
        digest = hashlib.sha256(bind if bind is not None else audio).hexdigest()
        manifest = {'output_sha256': {'denoised.wav': digest, 'source.wav': digest},
                    'timeline': {'audio_start_seconds': origin}, 'source': {'sha256': source_sha}}
        if origin is None:
            del manifest['timeline']['audio_start_seconds']
        if source_sha is None:
            del manifest['source']['sha256']
        if synthetic:
            manifest['source'].update(kind='generated_fixture', generator='test', seed=1)
        (run / 'manifest.json').write_text(json.dumps(manifest))
        return run

    def request(self, **overrides) -> dict:
        req = {'run_dir': RUN, 'excerpt_start_seconds': 0.0, 'excerpt_end_seconds': 2.0}
        req.update(overrides)
        return {k: v for k, v in req.items() if v is not ...}

    def call(self, request=None, separator=None, runtime=fake_runtime):
        return se.run_estimate(self.request() if request is None else request, self.root,
                               separator=separator or IdentitySeparator(), runtime_resolver=runtime)

    def tree(self) -> set:
        return {str(p.relative_to(self.root)) for p in self.root.rglob('*')}


# ============================================================================ M1 / M3 / M4 refusal coverage

class RefusalCodes(Offline):
    def assertRefused(self, code, request=None, runtime=fake_runtime, reason=None):
        before = self.tree()
        doc, workdir = self.call(request, runtime=runtime)
        self.assertEqual(doc['status'], 'refused', doc)
        self.assertEqual(doc['refusal_code'], code, doc['message'])
        self.assertEqual(set(doc), REFUSAL_KEYS)
        self.assertFalse(doc['network_used'] or doc['model_acquired'] or doc['default_adoption'] or doc['recovered_original_stem'])
        self.assertEqual(doc['runtime_reason'], reason)
        self.assertIsNone(workdir)
        self.assertEqual(self.tree(), before, 'a refusal wrote files')
        self.assertHeavyAbsent()
        return doc

    def test_01_request_invalid(self):
        bad = [[], {'run_dir': RUN}, self.request(extra=1), self.request(run_dir=''), self.request(run_dir=7),
               self.request(input_role='processed'), self.request(excerpt_start_seconds=True),
               self.request(excerpt_start_seconds=float('nan')), self.request(excerpt_end_seconds=float('inf')),
               self.request(excerpt_start_seconds=-1.0), self.request(excerpt_end_seconds=0.0),
               self.request(excerpt_start_seconds=2.0, excerpt_end_seconds=2.0), self.request(excerpt_end_seconds=0.99),
               self.request(timeout_seconds=0), self.request(timeout_seconds=901), self.request(timeout_seconds=60.0),
               self.request(timeout_seconds=True), self.request(excerpt_end_seconds='2'), self.request(run_dir='artifacts/runs/a\0b')]
        for request in bad:
            with self.subTest(request=request):
                self.assertRefused('request_invalid', request)

    def test_02_excerpt_too_long(self):
        self.assertRefused('excerpt_too_long', self.request(excerpt_end_seconds=30.01))
        self.assertRefused('excerpt_too_long', self.request(excerpt_start_seconds=10, excerpt_end_seconds=40.5))

    def test_03_model_not_registered(self):
        self.assertRefused('model_not_registered')  # absent
        (self.root / 'program').mkdir()
        registry = self.root / 'program' / 'models.json'
        for text in ('{', '[]', '{"schema_version": 2, "models": {}}', '{"schema_version": 1, "models": []}',
                     '{"schema_version": 1, "models": {"other": {}}}', '{"schema_version": 1, "models": {"x": NaN}}'):
            with self.subTest(text=text):
                registry.write_text(text)
                self.assertRefused('model_not_registered')
        registry.write_text(' ' * (1024**2 + 1))
        self.assertRefused('model_not_registered')
        registry.unlink()
        real = self.root / 'real.json'
        real.write_text(json.dumps({'schema_version': 1, 'models': {}}))
        registry.symlink_to(real)
        self.assertRefused('model_not_registered')

    def test_04_model_hash_not_registered(self):
        for digest in (None, 'A' * 64, 'abc', 0):
            with self.subTest(digest=digest):
                self.registry({'sha256': digest})
                self.assertRefused('model_hash_not_registered')

    def test_05_model_registry_entry_invalid(self):
        for entry in ({'url': 'http://dl.fbaipublicfiles.com/x.th'}, {'url': 'https://user:pw@host/x'}, {'url': 'https:///x'},
                      {'url': None}, {'license': ' '}, {'license': None}, {'max_bytes': 0}, {'max_bytes': True},
                      {'max_bytes': 2 * 1024**3 + 1}, {'max_bytes': 10.0}):
            with self.subTest(entry=entry):
                self.registry(entry)
                self.assertRefused('model_registry_entry_invalid')

    def test_06_model_terms_not_acknowledged(self):
        for entry in ({'operator_terms_acknowledgement': None}, {'operator_terms_acknowledgement': ''},
                      {'operator_terms_acknowledgement': 1}):
            with self.subTest(entry=entry):
                self.registry(entry)
                self.assertRefused('model_terms_not_acknowledged')
        self.registry(drop=('operator_terms_acknowledgement',))
        self.assertRefused('model_terms_not_acknowledged')

    def test_07_model_file_missing(self):
        self.registry()
        model = self.root / 'models' / f'{se.MODEL_ID}.bin'
        data = model.read_bytes()
        model.unlink()
        self.assertRefused('model_file_missing')
        real = self.root / 'elsewhere.bin'
        real.write_bytes(data)
        model.symlink_to(real)
        self.assertRefused('model_file_missing')
        model.unlink()
        self.registry({'max_bytes': 100})  # 512 random bytes > 100
        self.assertRefused('model_file_missing')

    def test_08_model_hash_mismatch(self):
        self.registry({'sha256': 'c' * 64})
        self.assertRefused('model_hash_mismatch')

    def test_09_runtime_unavailable_with_default_resolver(self):
        self.registry()
        self.run_dir()
        doc = self.assertRefused('runtime_unavailable', runtime=lambda root: se.default_runtime_resolver(root, environ={}),
                                 reason='not_configured')
        self.assertIn(se.RUNTIME_ENV_VAR, doc['message'])

    def test_10_input_not_admitted(self):
        self.registry()
        rate = 44100
        cases = {
            'stereo': dict(audio=pcm16_bytes(tones(rate, 2.0), rate, channels=2)),
            'hash_mismatch': dict(bind=b'other bytes'),
            'origin_missing': dict(origin=None),
            'origin_non_finite': dict(origin='1.0'),
            'source_sha_missing': dict(source_sha=None),
            'source_sha_upper': dict(source_sha='B' * 64),
            'over_300_s': dict(audio=pcm16_bytes(zeros(1000 * 301), 1000)),
            'not_wav': dict(audio=b'not a wav file at all'),
        }
        for name, kwargs in cases.items():
            with self.subTest(name=name):
                run = self.run_dir(**kwargs)
                self.assertRefused('input_not_admitted')
                shutil.rmtree(run)
        # 8-bit PCM is unsupported
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as writer:
            writer.setnchannels(1)
            writer.setsampwidth(1)
            writer.setframerate(8000)
            writer.writeframes(b'\x80' * 16000)
        run = self.run_dir(audio=buffer.getvalue())
        self.assertRefused('input_not_admitted')
        shutil.rmtree(run)
        # excerpt end beyond duration; missing role file; missing manifest
        run = self.run_dir()
        self.assertRefused('input_not_admitted', self.request(excerpt_start_seconds=1.5, excerpt_end_seconds=2.6))
        (run / 'source.wav').unlink()
        self.assertRefused('input_not_admitted', self.request(input_role='source'))
        (run / 'manifest.json').unlink()
        self.assertRefused('input_not_admitted')
        shutil.rmtree(run)

    def test_10_input_containment(self):
        self.registry()
        self.run_dir()
        for run_dir in ('artifacts/runs/../runs/20260101T000000Z-stems', 'artifacts/runs', 'artifacts/other/x',
                        '/etc', 'artifacts\\runs\\x', 'artifacts/runs/does-not-exist'):
            with self.subTest(run_dir=run_dir):
                self.assertRefused('input_not_admitted', self.request(run_dir=run_dir))
        link = self.root / 'artifacts/runs/linked'
        link.symlink_to(self.root / RUN)
        self.assertRefused('input_not_admitted', self.request(run_dir='artifacts/runs/linked'))
        wav = self.root / RUN / 'denoised.wav'
        data = wav.read_bytes()
        wav.unlink()
        (self.root / 'real.wav').write_bytes(data)
        wav.symlink_to(self.root / 'real.wav')
        self.assertRefused('input_not_admitted')


class RuntimeResolver(Offline):
    def env_python(self, symlink=False) -> Path:
        path = self.root / se.RUNTIME_REL / 'bin' / 'python'
        path.parent.mkdir(parents=True)
        if symlink:
            path.symlink_to(sys.executable)
        else:
            path.write_text('#!/bin/sh\nexit 0\n')
            path.chmod(0o700)
        return path

    def resolve(self, environ, system='linux', probe=None):
        with self.assertRaises(se.Refused) as caught:
            se.default_runtime_resolver(self.root, environ=environ, system=system, probe=probe)
        self.assertEqual(caught.exception.code, 'runtime_unavailable')
        return caught.exception.runtime_reason

    def test_reasons_in_order(self):
        self.assertEqual(self.resolve({}), 'not_configured')
        self.assertEqual(self.resolve({se.RUNTIME_ENV_VAR: '/x'}, system='darwin'), 'platform_unsupported')
        self.assertEqual(self.resolve({se.RUNTIME_ENV_VAR: sys.executable}), 'path_rejected')
        self.assertEqual(self.resolve({se.RUNTIME_ENV_VAR: 'artifacts/model-runtime-env/bin/python'}), 'path_rejected')
        python = self.env_python()
        self.assertEqual(self.resolve({se.RUNTIME_ENV_VAR: str(python.parent / '..' / 'bin' / 'python')}), 'path_rejected')
        self.assertEqual(self.resolve({se.RUNTIME_ENV_VAR: str(python)}), 'not_pinned')  # pins are None today
        with patch.object(se, 'DEMUCS_PIN', '4.0.1'), patch.object(se, 'TORCH_PIN', '2.5.1'):
            def broken(path):
                raise subprocess.TimeoutExpired('probe', 60)
            self.assertEqual(self.resolve({se.RUNTIME_ENV_VAR: str(python)}, probe=broken), 'identity_failed')
            other = lambda path: {'torch': '2.5.1', 'demucs': '4.0.0', 'python': '3.12', 'machine': 'x86_64', 'system': 'linux'}
            self.assertEqual(self.resolve({se.RUNTIME_ENV_VAR: str(python)}, probe=other), 'not_pinned')
            good = lambda path: {'torch': '2.5.1', 'demucs': '4.0.1', 'python': '3.12.1', 'machine': 'x86_64', 'system': 'linux'}
            runtime = se.default_runtime_resolver(self.root, environ={se.RUNTIME_ENV_VAR: str(python)}, system='linux', probe=good)
        self.assertEqual(runtime['kind'], 'isolated_child')
        self.assertEqual(runtime['python'], 'artifacts/model-runtime-env/bin/python')
        self.assertEqual(runtime['platform'], 'linux-x86_64')

    def test_symlinked_interpreter_rejected(self):
        python = self.env_python(symlink=True)
        self.assertEqual(self.resolve({se.RUNTIME_ENV_VAR: str(python)}), 'path_rejected')


# ============================================================================ M2 precedence (adjacent pairs)

class Precedence(Offline):
    def code(self, request=None, runtime=fake_runtime):
        doc, _ = self.call(request, runtime=runtime)
        return doc['refusal_code']

    def test_pairs(self):
        no_runtime = lambda root: se.default_runtime_resolver(root, environ={})
        # (1,2) extra key and too long -> request_invalid
        self.assertEqual(self.code(self.request(extra=1, excerpt_end_seconds=40.0)), 'request_invalid')
        # (2,3) too long and no registry -> excerpt_too_long
        self.assertEqual(self.code(self.request(excerpt_end_seconds=40.0)), 'excerpt_too_long')
        # (3,4) wrong registry schema and a null digest -> model_not_registered
        self.registry({'sha256': None})
        registry = self.root / 'program' / 'models.json'
        data = json.loads(registry.read_text())
        data['schema_version'] = 2
        registry.write_text(json.dumps(data))
        self.assertEqual(self.code(), 'model_not_registered')
        # (4,5) null digest and bad url -> model_hash_not_registered
        self.registry({'sha256': None, 'url': 'http://x/y'})
        self.assertEqual(self.code(), 'model_hash_not_registered')
        # (5,6) bad url and no acknowledgement -> model_registry_entry_invalid
        self.registry({'url': 'http://x/y', 'operator_terms_acknowledgement': None})
        self.assertEqual(self.code(), 'model_registry_entry_invalid')
        # (6,7) no acknowledgement and model file missing -> model_terms_not_acknowledged
        self.registry({'operator_terms_acknowledgement': None})
        (self.root / 'models' / f'{se.MODEL_ID}.bin').unlink()
        self.assertEqual(self.code(), 'model_terms_not_acknowledged')
        # (7,8) oversized file that also mismatches -> model_file_missing
        self.registry({'max_bytes': 10, 'sha256': 'd' * 64})
        self.assertEqual(self.code(), 'model_file_missing')
        # (8,9) hash mismatch and runtime unavailable -> model_hash_mismatch
        self.registry({'sha256': 'd' * 64})
        self.assertEqual(self.code(runtime=no_runtime), 'model_hash_mismatch')
        # (9,10) runtime unavailable and inadmissible input (no run dir) -> runtime_unavailable
        self.registry()
        self.assertEqual(self.code(runtime=no_runtime), 'runtime_unavailable')
        self.assertEqual(self.code(), 'input_not_admitted')


# ============================================================================ M3 / M4 today behaviour and import hygiene

class TodayAndHygiene(unittest.TestCase):
    REQUEST = {'run_dir': 'artifacts/runs/20261006T041633Z-990aa1bd6737', 'input_role': 'denoised',
               'excerpt_start_seconds': 30.0, 'excerpt_end_seconds': 60.0}

    def estimates_listing(self):
        base = ROOT / se.ESTIMATES_REL
        return sorted(p.name for p in base.iterdir()) if base.is_dir() else None

    def test_m3_committed_registry_refuses_model_not_registered_and_writes_nothing(self):
        before = self.estimates_listing()
        committed = json.loads((ROOT / 'program' / 'models.json').read_text())
        if se.MODEL_ID in committed['models']:
            self.skipTest('root has registered the entry; M3 describes the pre-registration state')
        expected = 'model_not_registered'
        script = str(ROOT / 'scripts' / 'stems_estimate.py')
        env = {k: v for k, v in os.environ.items() if k != se.RUNTIME_ENV_VAR}
        for argv, stdin in ((['--request-json', json.dumps(self.REQUEST)], None), (['--request', '-'], json.dumps(self.REQUEST))):
            with self.subTest(argv=argv[0]):
                completed = subprocess.run([sys.executable, script, 'estimate', *argv], input=stdin, capture_output=True,
                                           text=True, timeout=60, cwd=ROOT, env=env)
                self.assertEqual(completed.returncode, 2, completed.stderr)
                doc = json.loads(completed.stdout)
                self.assertEqual(doc['refusal_code'], expected)
                self.assertEqual(set(doc), REFUSAL_KEYS)
        self.assertEqual(self.estimates_listing(), before)

    def test_m4_fresh_interpreter_import_and_refusals_leave_heavy_modules_absent(self):
        probe = (
            'import json, socket, sys, urllib.request\n'
            'calls = []\n'
            'def trap(name):\n'
            '    def f(*a, **k):\n'
            '        calls.append(name); raise RuntimeError(name)\n'
            '    return f\n'
            'socket.socket = trap("socket.socket"); urllib.request.urlopen = trap("urlopen")\n'
            f'sys.path.insert(0, {str(ROOT / "scripts")!r})\n'
            'import stems_estimate as se\n'
            'after_import = sorted(m for m in ("torch","torchaudio","demucs","numpy") if m in sys.modules)\n'
            f'codes = [se.estimate(r)["refusal_code"] for r in ({{}}, {self.REQUEST!r})]\n'
            'after = sorted(m for m in ("torch","torchaudio","demucs","numpy") if m in sys.modules)\n'
            'print(json.dumps({"import": after_import, "after": after, "codes": codes, "calls": calls}))\n')
        env = {k: v for k, v in os.environ.items() if k != se.RUNTIME_ENV_VAR}
        completed = subprocess.run([sys.executable, '-I', '-c', probe], capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report, {'import': [], 'after': [], 'codes': ['request_invalid', 'model_not_registered'], 'calls': []})

    def test_cli_unreadable_request_is_typed(self):
        completed = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'stems_estimate.py'), 'estimate', '--request-json', '{nan'],
                                   capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)['refusal_code'], 'request_invalid')


# ============================================================================ M5-M9 runtime path with fakes

class FakeRuntimePath(Offline):
    def setUp(self):
        super().setUp()
        self.registry()

    def completed(self, separator=None, request=None):
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.root / 'artifacts' / 'runs').rglob('*') if p.is_file()}
        tree = self.tree()
        doc, workdir = self.call(request, separator=separator)
        self.assertEqual(doc['status'], 'completed', doc)
        after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.root / 'artifacts' / 'runs').rglob('*') if p.is_file()}
        self.assertEqual(after, before, 'M9: the run directory changed')
        new = self.tree() - tree
        lane = str(se.LANE_REL)
        self.assertTrue(new and all(p == lane or p.startswith(lane + '/') or lane.startswith(p + '/') for p in new), new)
        self.assertTrue(workdir.is_relative_to(self.root / se.ESTIMATES_REL))
        self.assertHeavyAbsent()
        return doc, workdir

    def read_stem(self, workdir, name):
        channels, rate = se.read_wav(workdir / 'stems' / f'{name}.wav')
        self.assertEqual(len(channels), 1)
        return channels[0], rate

    def test_m5_schema_unknown_fields_and_six_stems(self):
        self.run_dir()
        doc, workdir = self.completed()
        self.assertEqual(set(doc), CONTRACT_KEYS)
        self.assertEqual(set(doc), set(se.RESULT_KEYS))
        for key, value in CONTRACT_UNKNOWN.items():
            self.assertIs(type(doc[key]), type(value), key)
            self.assertEqual(doc[key], value, key)
        self.assertEqual(len(CONTRACT_UNKNOWN), 17)
        self.assertEqual([s['name'] for s in doc['stems']], ['drums', 'bass', 'other', 'vocals', 'guitar', 'piano'])
        for stem in doc['stems']:
            path = workdir / stem['path']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), stem['sha256'])
            header = se.wav_header(path)
            self.assertEqual((header['rate'], header['channels'], header['frames'], header['format']), (44100, 1, 88200, 'float'))
            self.assertEqual((stem['rate'], stem['channels'], stem['frames'], stem['estimate']), (44100, 1, 88200, True))
        self.assertEqual(set(doc['model_identity']), {'model_id', 'sha256', 'registry_sha256', 'source_url', 'license_verdict',
                                                      'terms_acknowledgement', 'checkpoint_load'})
        self.assertEqual(doc['model_identity']['checkpoint_load'], 'not_loaded_injected_fake')
        runtime = doc['runtime_identity']
        self.assertEqual((runtime['kind'], runtime['threads'], runtime['seed']), ('injected_fake', 2, 20261007))
        self.assertEqual(runtime['apply_settings'], {'shifts': 1, 'overlap': 0.25, 'split': True, 'segment': None})
        identity = doc['input_identity']
        self.assertEqual(identity['signal_version'], 'sha256:' + identity['input_sha256'])
        self.assertEqual((identity['source_channels'], identity['real_take'], identity['path_role']), (1, True, 'run_denoised_wav'))
        self.assertEqual(doc['privacy'], 'V6_private_real_take_derived')
        analysed = doc['analysed_input']
        self.assertEqual(analysed['sha256'], hashlib.sha256((workdir / 'model_input.wav').read_bytes()).hexdigest())
        self.assertEqual((analysed['rate'], analysed['channels'], analysed['frames']), (44100, 2, 88200))
        self.assertEqual(analysed['channel_conversion'], {'to_model': 'mono_duplicated_to_stereo', 'from_model': 'stereo_mean_to_mono'})
        self.assertEqual(doc['resource_receipt']['deadline_seconds'], 600)
        self.assertEqual(doc['resource_receipt']['rss_ceiling_bytes'], 3 * 1024**3)
        self.assertIsNone(doc['resource_receipt']['max_rss_bytes'])
        text = ' '.join(doc['limitations'])
        for phrase in ('not recovered original stems', 'listening review', 'bass', 'drums', 'MUSDB18-HQ', 'personal/research',
                       'V6', 'never a cleanup'):
            self.assertIn(phrase, text)
        stored = json.loads((workdir / 'stems_estimate.json').read_text())
        self.assertEqual(stored, doc)
        self.assertFalse((workdir / 'scratch').exists())
        self.assertEqual(se.summary_of(doc, workdir, self.root)['output_dir'], str(workdir.relative_to(self.root)))

    def test_m6_identity_low_end(self):
        self.run_dir()
        doc, _ = self.completed(IdentitySeparator())
        low = doc['low_end_check']
        self.assertEqual(low['status'], 'measured')
        self.assertEqual((low['band_hz'], low['reference_band_hz'], low['filter']), ([20, 45], [45, 120], 'rbj_butterworth4_bandpass_cascade'))
        self.assertEqual(low['settle_excluded_seconds'], 0.25)
        self.assertLess(abs(low['guitar_vs_input_band_db']), 0.2)
        self.assertLess(abs(low['guitar_plus_bass_vs_input_band_db']), 0.2)
        self.assertGreater(low['input']['band_energy'], 0)
        self.assertIsNone(low['per_stem']['bass']['band_ratio_to_input_db'])
        self.assertEqual(low['per_stem']['bass']['band_ratio_to_input_db_reason'], 'zero_stem_band_energy')
        self.assertAlmostEqual(low['per_stem']['guitar']['band_share_of_stem_sum'], 1.0)
        mixture = doc['mixture_consistency']
        self.assertIsNone(mixture['residual_vs_input_full_db'])
        self.assertEqual(mixture['residual_vs_input_full_db_reason'], 'zero_residual_energy')

    def test_m6_low_to_bass(self):
        self.run_dir()
        doc, _ = self.completed(LowToBassSeparator())
        low = doc['low_end_check']
        self.assertLessEqual(low['guitar_vs_input_band_db'], -40.0)
        self.assertGreaterEqual(low['per_stem']['bass']['band_share_of_stem_sum'], 0.99)
        self.assertLess(abs(low['guitar_plus_bass_vs_input_band_db']), 0.2)

    def test_m6_minus_6_db_guitar(self):
        self.run_dir()
        doc, _ = self.completed(ScaleSeparator())
        low = doc['low_end_check']
        self.assertLess(abs(low['guitar_vs_input_band_db'] - (-6.0206)), 0.2)
        self.assertIsNone(doc['mixture_consistency']['residual_vs_input_band_db'])  # 0.5 + 0.5 sums back exactly

    def test_zero_reference_input(self):
        self.run_dir(audio=pcm16_bytes(zeros(88200), 44100))
        doc, _ = self.completed()
        low = doc['low_end_check']
        self.assertEqual(low['status'], 'zero_reference')
        self.assertIsNone(low['guitar_vs_input_band_db'])
        self.assertEqual(low['guitar_vs_input_band_db_reason'], 'zero_input_band_energy')

    def test_m7a_48k_round_trip_through_ffmpeg(self):
        selected = os.environ.get('FFMPEG', 'ffmpeg')
        if not shutil.which(selected):
            self.skipTest('FFmpeg unavailable: M7a NOT MET (contract section 10)')
        rate = 48000
        source = tones(rate, 2.0, ((C1, .3), (C4, .2), (1000.0, .1)))
        audio = se.wav_float_bytes([source], rate)
        self.run_dir(audio=audio)
        doc, workdir = self.completed()
        conversion = doc['analysed_input']['sample_rate_conversion']
        self.assertEqual(conversion, {'input_rate': 48000, 'model_rate': 44100, 'applied': True,
                                      'forward_filter': 'aresample=44100:resampler=swr',
                                      'return_filter': 'aresample=48000:resampler=swr', 'length_adjust_frames': conversion['length_adjust_frames']})
        self.assertLessEqual(abs(conversion['length_adjust_frames']), 2)
        self.assertEqual(doc['analysed_input']['frames'], 88200)
        guitar, stem_rate = self.read_stem(workdir, 'guitar')
        self.assertEqual((stem_rate, len(guitar), doc['excerpt']['frame_count']), (48000, 96000, 96000))
        excerpt = array.array('d', array.array('f', source))
        lo, hi = 2000, len(excerpt) - 2000
        corr = {lag: math.fsum(excerpt[i] * guitar[i + lag] for i in range(lo, hi)) for lag in range(-4, 5)}
        self.assertLessEqual(abs(max(corr, key=corr.get)), 1)
        self.assertLess(abs(doc['low_end_check']['guitar_vs_input_band_db']), 0.2)
        skip = 12000
        kilo = 10 * math.log10(se.mean_square(se.bandpass(guitar, rate, 800, 1250), skip)
                               / se.mean_square(se.bandpass(excerpt, rate, 800, 1250), skip))
        self.assertLess(abs(kilo), 0.2)

    def test_m7b_44k1_passthrough_is_bit_exact(self):
        source = tones(44100, 2.0)
        audio = se.wav_float_bytes([source], 44100)
        self.run_dir(audio=audio)
        doc, workdir = self.completed()
        conversion = doc['analysed_input']['sample_rate_conversion']
        self.assertEqual((conversion['applied'], conversion['forward_filter'], conversion['return_filter'],
                          conversion['length_adjust_frames']), (False, None, None, 0))
        payload = lambda path: path.read_bytes()[se.wav_header(path)['data_offset']:]  # noqa: E731
        self.assertEqual(payload(workdir / 'stems' / 'guitar.wav'), payload(self.root / RUN / 'denoised.wav'))

    def test_m8_source_timeline(self):
        source = tones(44100, 2.0)
        for origin in (0.0, 1.25):
            with self.subTest(origin=origin):
                run = self.run_dir(audio=pcm16_bytes(source, 44100), origin=origin)
                doc, workdir = self.completed(request=self.request(excerpt_start_seconds=0.5, excerpt_end_seconds=1.75))
                excerpt = doc['excerpt']
                self.assertEqual((excerpt['start_frame'], excerpt['frame_count'], excerpt['rate']), (22050, 55125, 44100))
                self.assertEqual(excerpt['source_timeline_origin_seconds'], origin)
                self.assertEqual(excerpt['source_start_seconds'], origin + 0.5)
                self.assertEqual(excerpt['source_end_seconds'], origin + 1.75)
                for stem in doc['stems']:
                    self.assertEqual((stem['source_start_seconds'], stem['source_end_seconds']), (origin + 0.5, origin + 1.75))
                guitar, _ = self.read_stem(workdir, 'guitar')
                (expected,), _ = se.read_wav(run / 'denoised.wav', 22050, 55125)
                self.assertEqual(list(guitar), list(expected))
                shutil.rmtree(run)

    def test_input_role_source_and_generated_fixture_privacy(self):
        self.run_dir(synthetic=True)
        doc, _ = self.completed(request=self.request(input_role='source'))
        self.assertEqual(doc['input_identity']['input_role'], 'source')
        self.assertEqual(doc['input_identity']['path_role'], 'run_source_wav')
        self.assertFalse(doc['input_identity']['real_take'])
        self.assertEqual(doc['privacy'], 'generated_fixture')

    def test_separator_faults_are_failures_not_refusals(self):
        self.run_dir()

        class Wrong:
            def __call__(self, stereo, model, workdir):
                out = six(n=len(stereo[0]))
                del out['piano']
                return out

        class Short:
            def __call__(self, stereo, model, workdir):
                return six(n=len(stereo[0]) - 1)

        class NonFinite:
            def __call__(self, stereo, model, workdir):
                out = six(n=len(stereo[0]))
                out['drums'][0][5] = float('nan')
                return out

        class Raises:
            def __call__(self, stereo, model, workdir):
                raise MemoryError('boom')

        for separator, code in ((Wrong(), 'separator_output_invalid'), (Short(), 'separator_output_invalid'),
                                (NonFinite(), 'separator_output_invalid'), (Raises(), 'inference_failed')):
            with self.subTest(code=code, separator=type(separator).__name__):
                doc, workdir = self.call(separator=separator)
                self.assertEqual((doc['status'], doc['failure_code']), ('failed', code))
                self.assertFalse(doc['recovered_original_stem'])
                self.assertTrue((workdir / 'failure.json').is_file())

    def test_input_changed_during_inference_fails(self):
        run = self.run_dir()

        class Mutates(IdentitySeparator):
            def __call__(self, stereo, model, workdir):
                with (run / 'denoised.wav').open('ab') as handle:
                    handle.write(b'\0\0')
                return super().__call__(stereo, model, workdir)

        doc, _ = self.call(separator=Mutates())
        self.assertEqual(doc['failure_code'], 'input_or_model_changed')


# ============================================================================ child process bounds (no torch)

class ChildBounds(Offline):
    def test_bounded_child_deadline_kills_process_group(self):
        workdir = self.root / 'w'
        workdir.mkdir()
        started = time.monotonic()
        with self.assertRaises(se.Failed) as caught:
            se.bounded_child([sys.executable, '-c', 'import time; time.sleep(30)'], workdir, {'PATH': '/usr/bin:/bin'}, 0.5)
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(caught.exception.code, 'inference_failed')
        receipt = json.loads((workdir / 'worker-resource.json').read_text())
        self.assertEqual(receipt['termination_reason'], 'deadline')
        self.assertEqual(receipt['ruling'], 'R-N11')

    def test_infer_refuses_changed_identity_before_any_heavy_import(self):
        model = self.root / 'm.bin'
        model.write_bytes(b'weights')
        wav = self.root / 'in.wav'
        wav.write_bytes(se.wav_float_bytes([[0.0] * 10, [0.0] * 10], 44100))
        task = self.root / 'task.json'
        task.write_text(json.dumps({'model_path': str(model), 'model_sha256': 'e' * 64, 'input_path': str(wav),
                                    'input_sha256': hashlib.sha256(wav.read_bytes()).hexdigest()}))
        with self.assertRaises(ValueError):
            se.infer_task(task)
        self.assertHeavyAbsent()

    def test_child_separator_rechecks_model_before_launch(self):
        workdir = self.root / 'w'
        workdir.mkdir()
        se.write_wav_float(workdir / 'model_input.wav', [[0.0] * 8, [0.0] * 8], 44100)
        model = self.root / 'm.bin'
        model.write_bytes(b'weights')
        separator = se.ChildSeparator(self.root, {'interpreter': sys.executable})
        with self.assertRaises(se.Failed) as caught:
            separator([[0.0] * 8, [0.0] * 8], {'path': str(model), 'sha256': 'f' * 64}, workdir)
        self.assertEqual(caught.exception.code, 'model_changed')
        self.assertFalse((workdir / 'task.json').exists())


# ============================================================================ M10-M12 drafts and skill

class Drafts(unittest.TestCase):
    def test_m10_descriptor_draft(self):
        import tool_api
        draft = json.loads((ROOT / 'program' / 'tool-drafts' / 'stems_estimate.json').read_text())
        descriptor = draft['descriptor']
        tool_api.validate_schema(descriptor['inputSchema'])
        admitted = json.loads((ROOT / 'program' / 'tools.json').read_text())['tools']
        reference = next(t for t in admitted if t['name'] == 'beat_this_compare')
        self.assertEqual(set(descriptor), set(reference))
        self.assertEqual(len(descriptor), 12)
        schema = descriptor['inputSchema']
        self.assertIs(schema['additionalProperties'], False)
        self.assertEqual(set(schema['properties']), se.REQUEST_KEYS)
        self.assertEqual(set(schema['required']), se.REQUIRED_REQUEST_KEYS)
        self.assertEqual(schema['properties']['input_role']['enum'], ['denoised', 'source'])
        self.assertEqual((descriptor['name'], descriptor['implementation_status'], descriptor['evidence_kind']),
                         ('stems_estimate', 'experimental', 'uncalibrated_model_stem_estimates_from_mono_mixture'))
        self.assertTrue((ROOT / descriptor['skill']).is_file())
        # Admitted unchanged by root_admission_g (tests/test_s3g_tool_admission.py).
        self.assertEqual(next(t for t in admitted if t['name'] == 'stems_estimate'), descriptor)

    def test_m11_registry_draft(self):
        draft = json.loads((ROOT / 'program' / 'model-drafts' / 'htdemucs_6s.json').read_text())
        self.assertEqual((draft['schema_version'], draft['draft_for'], draft['model_id']), (1, 'program/models.json', se.MODEL_ID))
        entry = draft['entry']
        self.assertEqual(set(entry), {'url', 'sha256', 'max_bytes', 'expected_bytes_source', 'upstream_sha256_prefix_cross_check',
                                      'format', 'license', 'license_verdict', 'license_conditions',
                                      'operator_terms_acknowledgement', 'source_commit', 'sources', 'model_rate_hz',
                                      'model_channels', 'gate_state'})
        self.assertEqual(len(entry), 15)
        self.assertIsNone(entry['sha256'])
        self.assertIsNone(entry['operator_terms_acknowledgement'])
        self.assertEqual(entry['max_bytes'], 54996327)
        self.assertEqual(entry['gate_state'], 'registered_pending_fetch')
        self.assertEqual(entry['license_verdict'], 'admissible_private_comparator')
        self.assertEqual(entry['url'], 'https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/5c90dfd2-34c22ccb.th')
        self.assertEqual(entry['upstream_sha256_prefix_cross_check'], '34c22ccb')
        self.assertEqual(tuple(entry['sources']), se.SOURCES)
        self.assertEqual((entry['model_rate_hz'], entry['model_channels']), (se.MODEL_RATE, se.MODEL_CHANNELS))
        self.assertEqual(len(entry['license_conditions']), 5)

    def test_m11_draft_entry_refuses_hash_not_registered(self):
        draft = json.loads((ROOT / 'program' / 'model-drafts' / 'htdemucs_6s.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(os.path.realpath(tmp))
            (root / 'program').mkdir()
            (root / 'program' / 'models.json').write_text(json.dumps({'schema_version': 1, 'models': {se.MODEL_ID: draft['entry']}}))
            doc = se.estimate({'run_dir': RUN, 'excerpt_start_seconds': 0, 'excerpt_end_seconds': 2}, root)
        self.assertEqual(doc['refusal_code'], 'model_hash_not_registered')

    def test_m12_skill_sections(self):
        text = (ROOT / '.agents' / 'skills' / 'stems-estimate' / 'SKILL.md').read_text()
        self.assertTrue(text.startswith('---\nname: stems-estimate\n'))
        headings = [line[3:].strip().lower() for line in text.splitlines() if line.startswith('## ')]
        for section in ('intent', 'knobs', 'dependencies', 'research', 'iteration', 'evidence', 'refusals'):
            self.assertTrue(any(h.startswith(section) for h in headings), section)
        self.assertIn('docs/research/2026-10-07-stems-weights-licence.md', text)
        self.assertIn('docs/spec/sprints/STEMS_S3.md', text)


# ============================================================================ M13 fixtures, separation, seal; scorer

class FixtureHarness(Offline):
    def test_m13_generator_determinism(self):
        first = se.generate_fixture('k1-c1-chug', 4001, duration=2.0)
        second = se.generate_fixture('k1-c1-chug', 4001, duration=2.0)
        for part in ('mixture', 'guitar', 'fan', 'click'):
            a = hashlib.sha256(se.wav_float_bytes([first[part]], 44100)).hexdigest()
            b = hashlib.sha256(se.wav_float_bytes([second[part]], 44100)).hexdigest()
            self.assertEqual(a, b, part)
        self.assertEqual(len(first['mixture']), 88200)
        other = se.generate_fixture('k1-c1-chug', 4002, duration=2.0)
        self.assertNotEqual(first['fan'], other['fan'])
        negative = se.generate_fixture('k4-negative', 4001, duration=2.0)
        self.assertTrue(negative['truth']['guitar_is_digital_silence'])
        self.assertEqual(max(abs(v) for v in negative['guitar']), 0.0)
        fan_rms = math.sqrt(math.fsum(v * v for v in first['fan']) / len(first['fan']))
        self.assertAlmostEqual(20 * math.log10(fan_rms), -42.0, places=6)
        self.assertAlmostEqual(max(abs(v) for v in first['guitar']), 10 ** (-6 / 20), places=9)

    def test_seed_and_role_rules(self):
        with self.assertRaises(ValueError):
            se.generate_suite(self.root, 'x', 'dev', [4103])
        with self.assertRaises(ValueError):
            se.generate_suite(self.root, 'x', 'heldout', [3101, 3203])
        with self.assertRaises(ValueError):
            se.generate_suite(self.root, 'x', 'heldout', [4103])
        with self.assertRaises(ValueError):
            se.generate_suite(self.root, '../x', 'dev', [4001])

    def test_heldout_generation_blocked_until_a1_runnable(self):
        with self.assertRaises(se.Refused) as caught:
            se.generate_suite(self.root, 's3-stems-1', 'heldout', [4103, 4211])
        self.assertEqual(caught.exception.code, 'model_not_registered')
        self.assertFalse((self.root / se.FIXTURES_REL).exists())

    def test_m13_truth_prediction_separation_and_seal(self):
        self.registry()
        suite = se.generate_suite(self.root, 's3-stems-dev', 'dev', [4001], duration=2.0, cohorts=('k1-c1-chug', 'k4-negative'))
        manifest = json.loads((suite / 'manifest.json').read_text())
        self.assertFalse(manifest['complete_preregistered_suite'])
        for info in manifest['cases'].values():
            for relative in info['truth_files']:
                self.assertEqual((suite / relative).stat().st_mode & 0o777, 0o400)
            case_manifest = json.loads((suite / info['case_dir'] / 'manifest.json').read_text())
            self.assertEqual(case_manifest['source']['kind'], 'generated_fixture')
            self.assertEqual(case_manifest['timeline']['audio_start_seconds'], 0.0)
        real_open = io.open

        def guarded(file, *args, **kwargs):
            if '/truth/' in str(file) or str(file).endswith('/truth'):
                raise AssertionError(f'prediction code opened truth: {file}')
            return real_open(file, *args, **kwargs)

        a1 = lambda request: se.run_estimate(request, self.root, separator=IdentitySeparator(), runtime_resolver=fake_runtime)
        with patch('io.open', guarded), patch('builtins.open', guarded):
            se.predict(self.root, suite, 'A0')
            se.predict(self.root, suite, 'A1', a1=a1)
        for case in manifest['cases']:
            record = json.loads((suite / 'predictions' / 'A1' / case / 'record.json').read_text())
            self.assertEqual(record['estimate'], 'htdemucs_6s_guitar')
            self.assertEqual(set(record['files']), {'guitar.wav', 'bass.wav'})
        se.seal(self.root, suite)
        with self.assertRaises(ValueError):
            se.predict(self.root, suite, 'A0')
        with self.assertRaisesRegex(ValueError, 'dev suites are never scored'):
            se.score(self.root, suite)
        target = suite / 'predictions' / 'A0' / 'k1-c1-chug-s4001' / 'guitar.wav'
        with target.open('ab') as handle:
            handle.write(b'\0\0\0\0')
        with self.assertRaisesRegex(ValueError, 'sealed prediction changed'):
            se.score(self.root, suite)
        extra = suite / 'predictions' / 'A0' / 'k1-c1-chug-s4001' / 'extra.wav'
        extra.write_bytes(b'x')
        with self.assertRaisesRegex(ValueError, 'differ from the sealed set'):
            se.score(self.root, suite)

    def test_score_refuses_without_seal(self):
        suite = se.generate_suite(self.root, 's3-stems-dev', 'dev', [4001], duration=1.0, cohorts=('k4-negative',))
        with self.assertRaisesRegex(ValueError, 'seal.json missing'):
            se.score(self.root, suite)


class Scorer(unittest.TestCase):
    RATE = 8000

    def parts(self, seconds=1.0):
        n = int(self.RATE * seconds)
        rng = random.Random(7)
        guitar = tones(self.RATE, seconds, ((C1, .3), (130.8, .2)))
        fan = [0.01 * (rng.random() - .5) for _ in range(n)]
        click = [0.0] * n
        for k in range(0, n, 2000):
            click[k] = 0.1
        mixture = [g + f + c for g, f, c in zip(guitar, fan, click)]
        return guitar, fan, click, mixture

    def test_metrics_on_constructed_estimates(self):
        g, f, k, m = self.parts()
        row = se.score_case('k1-c1-chug', self.RATE, m, g, f, k, {'A0': m, 'A1': g})
        a0, a1 = row['readouts']['A0'], row['readouts']['A1']
        self.assertEqual(a1['S2_si_sdr_db'], {'value': None, 'reason': 'plus_infinity_zero_error_energy'})
        self.assertAlmostEqual(a1['S1_low_band_retention_db']['value'], 0.0, places=9)
        self.assertAlmostEqual(a1['S1_band_correlation']['value'], 1.0, places=9)
        leak = a1['S3_fan_leakage_full_db']
        self.assertTrue(leak['reason'] == 'minus_infinity_zero_numerator_energy' or leak['value'] < -100, leak)
        self.assertAlmostEqual(a0['S3_fan_leakage_full_db']['value'], 0.0, places=6)
        self.assertGreater(a0['S2_si_sdr_db']['value'], 5.0)
        negative = se.score_case('k4-negative', self.RATE, f, [0.0] * len(f), f, k, {'A0': f, 'A1': [0.0] * len(f)})
        self.assertAlmostEqual(negative['readouts']['A0']['S4_false_allocation_full_db']['value'], 0.0, places=9)
        self.assertEqual(negative['readouts']['A1']['S4_false_allocation_full_db']['reason'], 'minus_infinity_zero_numerator_energy')

    def test_si_sdr_and_projection(self):
        g = tones(self.RATE, .5, ((200.0, 1.0),))
        noise = tones(self.RATE, .5, ((900.0, .1),))
        e = [a + b for a, b in zip(g, noise)]
        self.assertAlmostEqual(se.si_sdr(e, g), 20.0, delta=0.05)
        self.assertIsNone(se.si_sdr(e, [0.0] * len(g)))
        coeffs = se.projection_coefficients([2 * a - 0.5 * b for a, b in zip(g, noise)], [g, noise])
        self.assertAlmostEqual(coeffs[0], 2.0, places=6)
        self.assertAlmostEqual(coeffs[1], -0.5, places=6)
        self.assertIsNone(se.projection_coefficients(g, [g, g]))

    def test_decision_rule_outcomes(self):
        g, f, k, m = self.parts()
        neg_mix = [a + b for a, b in zip(f, k)]
        silent = [0.0] * len(g)

        def run(a1_guitar, a1_negative, gb=None):
            per_case = {
                'k1-c1-chug-s1': se.score_case('k1-c1-chug', self.RATE, m, g, f, k,
                                                {'A0': m, 'A1': a1_guitar, 'A1-gb': gb or a1_guitar}),
                'k4-negative-s1': se.score_case('k4-negative', self.RATE, neg_mix, silent, f, k, {'A0': neg_mix, 'A1': a1_negative}),
            }
            return se.decide(se.aggregate(per_case)), se.aggregate(per_case)

        decision, summary = run(g, silent)
        self.assertEqual(decision['outcome'], 'A1 separates without low-band loss on generated fixtures')
        self.assertFalse(decision['low_band_loss_observed'])
        self.assertFalse(decision['default_adoption'])
        self.assertEqual(summary['A0']['S2_si_sdr_db']['n_cases'], 1)
        decision, _ = run(m, neg_mix)
        self.assertEqual(decision['outcome'], 'no separation benefit shown on generated fixtures')
        high = g
        for _ in range(4):
            high = se.biquad(high, se.biquad_coefficients('highpass', 60.0, 0.7071, self.RATE))
        decision, _ = run(list(high), silent, gb=g)
        self.assertTrue(decision['low_band_loss_observed'])
        self.assertFalse(decision['low_band_loss_observed_A1_gb'])
        self.assertEqual(decision['outcome'], 'no separation benefit shown on generated fixtures')


if __name__ == '__main__':
    unittest.main()
