"""guitar_noul TIN-5619 client tests with an injected mock transport (no sockets, no server)."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import guitar_noul_client as gn  # noqa: E402

SYNTH = 'artifacts/s2/model_lanes/fixtures/noul-synth'
REAL = 'artifacts/runs/20260101T000000Z-real'
GATEWAY = {gn.GATEWAY_ENV: 'https://models.xoxd.ai/v1/guitar_noul'}
IDENTITY = {'gguf_sha256': 'c' * 64, 'catalog_name': 'xoxd/rune-26b-a4b-v3-xoruby-noul1-20261010'}


def _no_network(*args, **kwargs):
    raise AssertionError('network access attempted in an offline test')


def tone_wav(seconds: float, rate: int = 44100) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(b''.join(((i * 37) % 2000 - 1000).to_bytes(2, 'little', signed=True) for i in range(int(seconds * rate))))
    return buffer.getvalue()


class MockTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, body, timeout):
        self.calls.append({'url': url, 'body': json.loads(body), 'timeout': timeout})
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        status, payload = item
        return status, payload if isinstance(payload, bytes) else json.dumps(payload).encode()


def ok_response(indices, override=None):
    override = override or {}
    windows = []
    for i in indices:
        item = {'index': i, 'label': 'riff_hypothesis_a', 'abstain': False, 'abstain_reason': None,
                'confidence_label': 'medium', 'model_identity': IDENTITY}
        item.update(override.get(i, {}))
        windows.append(item)
    return 200, {'contract': gn.CONTRACT, 'windows': windows}


class Base(unittest.TestCase):
    def setUp(self):
        for target in ('socket.socket', 'socket.create_connection', 'urllib.request.urlopen'):
            patcher = patch(target, side_effect=_no_network)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(os.path.realpath(self.tmp.name))
        self.make_run(SYNTH, synthetic=True)
        self.make_run(REAL, synthetic=False)

    def make_run(self, relative: str, synthetic: bool, seconds: float = 3.0):
        run = self.root / relative
        run.mkdir(parents=True)
        audio = tone_wav(seconds)
        (run / 'denoised.wav').write_bytes(audio)
        source = {'kind': 'generated_fixture', 'generator': 'test', 'seed': 7} if synthetic else {'path': '/private/take.mov', 'sha256': 'a' * 64}
        manifest = {'source': source, 'pcm': {'duration_seconds': seconds, 'sample_rate': 44100},
                    'timeline': {'audio_start_seconds': 0.0}, 'output_sha256': {'denoised.wav': hashlib.sha256(audio).hexdigest()}}
        (run / 'manifest.json').write_text(json.dumps(manifest))

    def request(self, run=SYNTH, windows=None, timeout=10, **extra):
        body = {'run_dir': run, 'windows': windows or [{'source_start_s': 0.0, 'source_end_s': 1.0},
                                                        {'source_start_s': 1.5, 'source_end_s': 2.5}], 'timeout_seconds': timeout}
        body.update(extra)
        return body

    def decide(self, request, env=None, transport=None):
        transport = transport or MockTransport(ok_response([0, 1]))
        return gn.decide(request, env=GATEWAY if env is None else env, transport=transport, root=self.root), transport

    def assertRefused(self, result, transport, code):
        self.assertEqual(result['status'], 'refused', result)
        self.assertEqual(result['refusal_code'], code, result)
        if code not in ('gateway_auth_refused', 'gateway_unreachable'):
            self.assertEqual(transport.calls, [])
            self.assertFalse(result['transport_invoked'])


class RefusalTests(Base):
    """M8: the seven refusal codes, with transport-call assertions."""

    def test_input_schema_invalid(self):
        for request in (self.request(extra_key=1), self.request(timeout=0), self.request(timeout=True),
                        self.request(timeout=121), self.request(run='artifacts/other'), self.request(run='artifacts/runs/../runs'),
                        {'run_dir': SYNTH, 'windows': []}):
            self.assertRefused(*self.decide(request), 'input_schema_invalid')

    def test_window_invalid(self):
        cases = ([{'source_start_s': 0.0, 'source_end_s': 1.0}, {'source_start_s': 0.5, 'source_end_s': 1.5}],
                 [{'source_start_s': 0.0, 'source_end_s': 0.2}],
                 [{'source_start_s': 2.5, 'source_end_s': 3.5}],
                 [{'source_start_s': 1.0, 'source_end_s': 0.5}],
                 [{'source_start_s': float('nan'), 'source_end_s': 1.0}],
                 [{'source_start_s': 0.0, 'source_end_s': 1.0, 'extra': 1}],
                 [{'source_start_s': i * 0.04, 'source_end_s': i * 0.04 + 0.3} for i in range(65)])
        for windows in cases:
            self.assertRefused(*self.decide(self.request(windows=windows)), 'window_invalid')

    def test_gateway_not_configured(self):
        self.assertRefused(*self.decide(self.request(), env={}), 'gateway_not_configured')
        self.assertRefused(*self.decide(self.request(), env={gn.GATEWAY_ENV: ''}), 'gateway_not_configured')

    def test_gateway_url_rejected(self):
        for url in ('http://models.xoxd.ai/x', 'https://user@models.xoxd.ai/x', 'https://models.xoxd.ai:8443/x',
                    'https://example.org/x', 'https://ts.net/x', 'https://evil-models.xoxd.ai.example/x'):
            self.assertRefused(*self.decide(self.request(), env={gn.GATEWAY_ENV: url}), 'gateway_url_rejected')
        result, _ = self.decide(self.request(), env={gn.GATEWAY_ENV: 'https://honey.tail1234.ts.net:443/noul'})
        self.assertEqual(result['status'], 'completed')

    def test_real_take_not_permitted(self):
        for env in (GATEWAY, {**GATEWAY, gn.ALLOW_ENV: 'yes'}, {**GATEWAY, gn.ALLOW_ENV: 'v6-private-operator-lab-host '}):
            self.assertRefused(*self.decide(self.request(run=REAL), env=env), 'real_take_not_permitted')

    def test_gateway_auth_refused(self):
        for status in (401, 403):
            transport = MockTransport((status, b'{}'))
            result, _ = self.decide(self.request(), transport=transport)
            self.assertRefused(result, transport, 'gateway_auth_refused')
            self.assertEqual(len(transport.calls), 1)
            self.assertTrue(result['transport_invoked'])

    def test_gateway_unreachable_retried_once(self):
        transport = MockTransport(gn.TransportUnreachable('down'))
        result, _ = self.decide(self.request(), transport=transport)
        self.assertRefused(result, transport, 'gateway_unreachable')
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(result['transport_receipt']['attempts'], 2)


class WindowOutcomeTests(Base):
    """M8 abstains and M9 hypothesis fields; no file written under run_dir."""

    def assertHypotheses(self, doc):
        for window in doc['windows']:
            self.assertEqual(window['claim_class'], 'detector_hypothesis')
            self.assertIs(window['is_label'], False)
            self.assertIs(window['user_reported'], False)
            self.assertEqual(window['authorship'], 'detector:guitar_noul')
            self.assertIsNone(window['note_correctness'])
            self.assertIsNone(window['performance_issue'])
            self.assertIs(window['label_vocabulary_ratified'], False)

    def test_valid_decisions_and_wire_request(self):
        before = sorted(p.name for p in (self.root / SYNTH).iterdir())
        doc, transport = self.decide(self.request())
        self.assertEqual(doc['status'], 'completed')
        self.assertFalse(doc['gateway_wire_schema_ratified'])
        self.assertEqual(doc['gateway'], {'url_host': 'models.xoxd.ai', 'configured': True})
        self.assertFalse(doc['real_take'])
        self.assertIsNone(doc['real_take_permission'])
        self.assertNotIn('privacy', doc)
        self.assertEqual([w['decision']['label'] for w in doc['windows']], ['riff_hypothesis_a'] * 2)
        self.assertEqual(doc['windows'][0]['model_identity'], IDENTITY)
        self.assertHypotheses(doc)
        body = transport.calls[0]['body']
        self.assertEqual(body['contract'], 'tin-5619-v0')
        self.assertEqual(len(body['windows']), 2)
        payload = base64.b64decode(body['windows'][0]['payload'])
        with wave.open(io.BytesIO(payload)) as reader:
            self.assertEqual((reader.getframerate(), reader.getnchannels(), reader.getsampwidth()), (16000, 1, 2))
            self.assertAlmostEqual(reader.getnframes() / 16000, 1.0, places=2)
        self.assertEqual(sorted(p.name for p in (self.root / SYNTH).iterdir()), before)

    def test_real_take_allowed_with_exact_v6_value(self):
        doc, transport = self.decide(self.request(run=REAL), env={**GATEWAY, gn.ALLOW_ENV: gn.ALLOW_VALUE})
        self.assertEqual(doc['status'], 'completed')
        self.assertTrue(doc['real_take'])
        self.assertEqual(doc['real_take_permission'], 'v6-private-operator-lab-host')
        self.assertEqual(doc['privacy'], 'V6_private_real_take_derived')
        self.assertEqual(transport.calls[0]['body']['source_sha256'], 'a' * 64)
        self.assertHypotheses(doc)

    def test_gateway_response_invalid(self):
        bad = {0: {'model_identity': {'gguf_sha256': 'XYZ', 'catalog_name': IDENTITY['catalog_name']}},
               1: {'label': 'ok', 'abstain': True, 'abstain_reason': 'x'}}
        doc, _ = self.decide(self.request(), transport=MockTransport(ok_response([0, 1], bad)))
        self.assertEqual([w['abstain_reason'] for w in doc['windows']], ['gateway_response_invalid'] * 2)
        self.assertTrue(all(w['abstain'] and w['decision']['label'] is None for w in doc['windows']))
        self.assertTrue(all(len(w['raw_response_sha256']) == 64 for w in doc['windows']))
        self.assertHypotheses(doc)
        doc, _ = self.decide(self.request(), transport=MockTransport((200, b'not json')))
        self.assertEqual({w['abstain_reason'] for w in doc['windows']}, {'gateway_response_invalid'})
        bad_catalog = {0: {'model_identity': {'gguf_sha256': 'c' * 64, 'catalog_name': 'xoxd/other-model-20261010'}}}
        doc, _ = self.decide(self.request(), transport=MockTransport(ok_response([0, 1], bad_catalog)))
        self.assertEqual(doc['windows'][0]['abstain_reason'], 'gateway_response_invalid')
        self.assertEqual(doc['windows'][1]['decision']['label'], 'riff_hypothesis_a')

    def test_timeout(self):
        doc, transport = self.decide(self.request(), transport=MockTransport(gn.TransportTimeout('slow')))
        self.assertEqual(doc['status'], 'completed')
        self.assertEqual([w['abstain_reason'] for w in doc['windows']], ['timeout', 'timeout'])
        self.assertEqual(len(transport.calls), 1)
        self.assertLessEqual(transport.calls[0]['timeout'], 10)
        self.assertHypotheses(doc)

    def test_missing_from_response(self):
        doc, _ = self.decide(self.request(), transport=MockTransport(ok_response([0])))
        self.assertEqual(doc['windows'][1]['abstain_reason'], 'missing_from_response')
        self.assertEqual(doc['windows'][0]['decision']['label'], 'riff_hypothesis_a')
        self.assertHypotheses(doc)

    def test_gateway_abstain_is_kept_distinct(self):
        abstain = {1: {'label': None, 'abstain': True, 'abstain_reason': 'low_signal', 'confidence_label': None}}
        doc, _ = self.decide(self.request(), transport=MockTransport(ok_response([0, 1], abstain)))
        self.assertEqual(doc['windows'][1]['abstain_reason'], 'gateway:low_signal')

    def test_output_never_inside_run_dir(self):
        doc, _ = self.decide(self.request())
        with self.assertRaises(gn.Refused):
            gn.write_output(doc, self.root / SYNTH / 'out.json', self.root / SYNTH, root=self.root)
        with self.assertRaises(gn.Refused):
            gn.write_output(doc, self.root / 'artifacts/runs/x.json', self.root / SYNTH, root=self.root)
        written = gn.write_output(doc, self.root / 'artifacts/s2/model_lanes/noul/out.json', self.root / SYNTH, root=self.root)
        self.assertTrue(written.is_file())


class CliTests(Base):
    def test_cli_refuses_without_gateway_and_never_raises(self):
        request = json.dumps(self.request())
        with patch.dict(os.environ, {}, clear=False), patch('builtins.print') as printed:
            os.environ.pop(gn.GATEWAY_ENV, None)
            code = gn.main(['--request-json', request])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(printed.call_args[0][0])['refusal_code'], 'input_schema_invalid')  # run_dir is relative to the real ROOT
        with patch('builtins.print') as printed:
            self.assertEqual(gn.main(['--request-json', '{not json']), 2)
        self.assertEqual(json.loads(printed.call_args[0][0])['refusal_code'], 'input_schema_invalid')


if __name__ == '__main__':
    unittest.main()
