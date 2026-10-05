import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import mcp_server


def request(identifier, method, params=None):
    return {'jsonrpc': '2.0', 'id': identifier, 'method': method, 'params': params or {}}


def initialization(version='2025-11-25'):
    return request(1, 'initialize', {'protocolVersion': version, 'capabilities': {},
                                    'clientInfo': {'name': 'test-client', 'version': '1'}})


def exchange(messages):
    raw = ''.join((json.dumps(message) if isinstance(message, dict) else message) + '\n' for message in messages)
    process = subprocess.run([sys.executable, str(ROOT / 'scripts/mcp_server.py')], input=raw,
                             capture_output=True, text=True, timeout=30)
    if process.returncode:
        raise AssertionError(process.stderr)
    return [json.loads(line) for line in process.stdout.splitlines()], process.stderr


class MCPTests(unittest.TestCase):
    def test_stdio_lifecycle_catalog_ping_errors_and_eof(self):
        messages = [request(0, 'tools/list'), initialization(),
                    {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                    request(2, 'tools/list'), request(3, 'prompts/list'), request(4, 'ping'),
                    request(5, 'tools/call', {'name': 'probe', 'arguments': {}}),
                    request(6, 'tools/call', {'name': 'probe', 'arguments': {'input': '/nonexistent/video-utils.wav'}}),
                    request(7, 'not-a-method'), '{bad-json}',
                    {'jsonrpc': '2.0', 'method': 'unknown/notification'}]
        replies, stderr = exchange(messages)
        self.assertEqual(stderr, '')
        self.assertEqual(len(replies), 9)
        self.assertEqual(replies[0]['error']['code'], -32002)
        self.assertEqual(replies[1]['result']['protocolVersion'], '2025-11-25')
        tools = replies[2]['result']['tools']
        self.assertEqual(len(tools), len(mcp_server.Server().catalog['tools']))
        self.assertTrue(all('outputSchema' in tool for tool in tools))
        self.assertEqual(len(replies[3]['result']['prompts']), len(tools))
        self.assertEqual(replies[4]['result'], {})
        self.assertEqual(replies[5]['error']['code'], -32602)
        self.assertTrue(replies[6]['result']['isError'])
        self.assertNotIn('error', replies[6])
        self.assertEqual(replies[7]['error']['code'], -32601)
        self.assertEqual(replies[8]['error']['code'], -32700)

    def test_version_negotiation_supports_known_and_offers_latest(self):
        for version, expected in [('2025-06-18', '2025-06-18'), ('unknown-future-version', '2025-11-25')]:
            server = mcp_server.Server()
            self.assertEqual(server.handle(initialization(version))['result']['protocolVersion'], expected)

    def test_no_rpc_shutdown_or_response_to_notification(self):
        server = mcp_server.Server()
        self.assertIsNone(server.handle({'jsonrpc': '2.0', 'method': 'unknown/notification'}))
        self.assertIsNone(server.handle({'jsonrpc': '2.0', 'id': 4, 'result': {}}))
        self.assertEqual(server.handle(request(True, 'ping'))['error']['code'], -32600)
        self.assertEqual(server.handle([])['error']['code'], -32600)
        self.assertEqual(server.handle({})['error']['code'], -32600)

    def test_prompt_loads_actual_skill_and_context_as_data(self):
        skill = ROOT / '.agents/skills/guitar-denoise/SKILL.md'
        if not skill.is_file():
            self.skipTest('parallel skill lane has not landed')
        replies, _ = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            request(2, 'prompts/get', {'name': 'guitar-denoise', 'arguments': {'goal': 'Preserve 32 Hz guitar'}})])
        result = replies[1]['result']
        self.assertEqual(result['messages'][0]['content']['text'], skill.read_text())
        self.assertIn('Preserve 32 Hz guitar', result['messages'][1]['content']['text'])


    def test_every_advertised_tool_has_a_readable_skill_prompt(self):
        server = mcp_server.Server()
        prompts = server.prompts()
        self.assertEqual(len(prompts), 12)
        messages = [initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'}]
        messages.extend(request(index + 2, 'prompts/get', {'name': prompt['name']})
                        for index, prompt in enumerate(prompts))
        replies, stderr = exchange(messages)
        self.assertEqual(stderr, '')
        self.assertEqual(len(replies), 13)
        for prompt, reply in zip(prompts, replies[1:]):
            with self.subTest(prompt=prompt['name']):
                self.assertNotIn('error', reply)
                skill = ROOT / '.agents/skills' / prompt['name'] / 'SKILL.md'
                self.assertEqual(reply['result']['messages'][0]['content']['text'], skill.read_text())

    @unittest.skipUnless(shutil.which(os.environ.get('FFPROBE', 'ffprobe')), 'ffprobe unavailable')
    def test_real_tool_call_probe_returns_structured_media_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'take with spaces.wav'
            with wave.open(str(source), 'wb') as stream:
                stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(44100)
                stream.writeframes(struct.pack('<h', 0) * 4410)
            replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'probe', 'arguments': {'input': str(source)}})])
            self.assertEqual(stderr, '')
            call = replies[1]['result']
            self.assertFalse(call['isError'])
            result = call['structuredContent']
            self.assertEqual(result, json.loads(call['content'][0]['text']))
            self.assertEqual(result['result']['probe']['audio']['sample_rate'], 44100)
            self.assertEqual(result['instrument_context']['strings'], 9)
            self.assertEqual(result['evidence_kind'], 'measured')


    @unittest.skipUnless(shutil.which(os.environ.get('FFPROBE', 'ffprobe')) and
                         shutil.which(os.environ.get('FFMPEG', 'ffmpeg')),
                         'FFmpeg/FFprobe unavailable')
    def test_real_low_string_notes_hook_keeps_intended_notes_unknown(self):
        if not (ROOT / 'scripts/guitar_features.py').is_file():
            self.skipTest('parallel feature lane has not landed')
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / '32-hz-nine-string.wav'
            frames = [round(10000 * math.sin(2 * math.pi * 32 * i / 44100)) for i in range(44100)]
            with wave.open(str(source), 'wb') as stream:
                stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(44100)
                stream.writeframes(struct.pack('<' + 'h' * len(frames), *frames))
            replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'notes', 'arguments': {'input': str(source),
                                                                       'run_dir': str(Path(temporary) / 'analysis')}})])
            self.assertEqual(stderr, '')
            call = replies[1]['result']
            self.assertFalse(call['isError'])
            evidence = call['structuredContent']['result']
            interpretation = evidence['interpretation']
            self.assertIsNone(interpretation['intended_notes'])
            self.assertIsNone(interpretation['tonic'])
            self.assertIsNone(interpretation['mode'])
            self.assertEqual(interpretation['performance_grade'], 'not_graded')
            frame = evidence['observations']['sparse_analysis_frames'][0]
            self.assertAlmostEqual(frame['periodicity_candidate']['frequency_hz'], 32, delta=1)
            self.assertTrue((Path(temporary) / 'analysis/notes.json').is_file())


    def test_real_pipeline_and_markers_keep_reference_unknown(self):
        if not (ROOT / 'program/dags/guitar-take.json').is_file():
            self.skipTest('DAG registry has not landed')
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'manifest.json').write_text(json.dumps({
                'source': {'sha256': 'a' * 64},
                'timeline': {'audio_start_seconds': 2.5}}))
            replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'pipeline', 'arguments': {'run_dir': temporary}}),
                request(3, 'tools/call', {'name': 'markers', 'arguments': {'run_dir': temporary}})])
            self.assertEqual(stderr, '')
            self.assertFalse(replies[1]['result']['isError'])
            self.assertFalse(replies[2]['result']['isError'])
            flags = json.loads((directory / 'flags.json').read_text())
            self.assertEqual(flags['status'], 'not_graded_no_approved_reference')
            self.assertIsNone(flags['musical_context']['tonic'])
            self.assertIsNone(flags['musical_context']['mode'])
            graph = json.loads((directory / 'dag.json').read_text())
            self.assertEqual(graph['kind'], 'artifact_provenance_DAG_not_an_execution_engine')
            markers = json.loads((directory / 'markers.json').read_text())
            self.assertEqual(markers['markers'][0]['source_time_seconds'], 2.5)
            self.assertIn('unsupported', markers['editor_import']['final_cut_pro'])
            self.assertTrue((directory / 'markers.csv').is_file())


if __name__ == '__main__':
    unittest.main()
