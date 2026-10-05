"""Cross-tool contract checks independent of proposed extension implementation."""
import json
import hashlib
import os
import shutil
import uuid
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import tool_api
import mcp_server


class ToolContractTests(unittest.TestCase):
    def test_schema_errors_never_launch_a_worker(self):
        for descriptor in tool_api.descriptors():
            name = descriptor['name']
            for arguments in [None, [], True, {'shell': 'anything'}, {'timeout_seconds': True}]:
                with self.subTest(tool=name, arguments=arguments), patch.object(tool_api, 'run_worker') as worker:
                    with self.assertRaises(tool_api.ValidationError):
                        tool_api.execute(name, arguments)
                    worker.assert_not_called()


    def test_extreme_integer_number_is_rejected_without_crashing_server(self):
        with patch.object(tool_api, 'run_worker') as worker:
            with self.assertRaises(tool_api.ValidationError):
                tool_api.execute('rhythm', {'input': '/nonexistent.wav', 'run_dir': '/tmp/no-write', 'bpm': 10**400})
            worker.assert_not_called()
        server = mcp_server.Server()
        server.initialized = server.ready = True
        reply = server.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                               'params': {'name': 'rhythm', 'arguments': {
                                   'input': '/nonexistent.wav', 'run_dir': '/tmp/no-write', 'bpm': 10**400}}})
        self.assertEqual(reply['error']['code'], -32602)

    def test_unknown_tools_never_launch_a_worker(self):
        for name in ['not_registered', '../scripts/media.py', 'run_shell', 'download_model']:
            with self.subTest(name=name), patch.object(tool_api, 'run_worker') as worker:
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.execute(name, {})
                worker.assert_not_called()

    def test_nonfinite_or_double_worker_json_is_a_tool_failure(self):
        for output in ['{"confidence": NaN}', '{"offset": Infinity}', '{"offset": -Infinity}', '{"overflow": 1e400}', '{}\n{}']:
            with self.subTest(output=output), tempfile.TemporaryDirectory() as temporary:
                script = Path(temporary) / 'fixture_worker.py'
                script.write_text('import sys\nsys.stdout.write(' + repr(output) + ')\n')
                with self.assertRaises(tool_api.ToolError):
                    tool_api.run_worker([sys.executable, str(script)], 2)


    def test_excessive_json_nesting_is_a_parse_error_not_a_server_crash(self):
        import subprocess
        payload = '[' * 10000 + '0' + ']' * 10000
        with self.assertRaises(ValueError):
            tool_api.strict_json(payload)
        child = subprocess.run([sys.executable, str(ROOT / 'scripts/mcp_server.py')],
                               input=payload + '\n', capture_output=True, text=True, timeout=5)
        self.assertEqual(child.returncode, 0)
        self.assertEqual(json.loads(child.stdout)['error']['code'], -32700)


    def test_json_nesting_limit_is_explicit_and_ignores_quoted_punctuation(self):
        limit = tool_api.MAX_JSON_NESTING
        accepted = '[' * limit + '0' + ']' * limit
        rejected = '[' * (limit + 1) + '0' + ']' * (limit + 1)
        self.assertIsInstance(tool_api.strict_json(accepted), list)
        with self.assertRaisesRegex(ValueError, 'nesting'):
            tool_api.strict_json(rejected)
        value = {'note': '[{' * 10000 + 'quoted \" braces } ] and literal backslash \\',
                 'nested': [{'quoted_key{': 'escaped \" quote and more [{ punctuation'}]}
        self.assertEqual(tool_api.strict_json(json.dumps(value)), value)

    def test_timeout_cleans_only_recorded_descendants_and_returns_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            late_output = directory / 'escaped-worker-output.txt'
            child = directory / 'child.py'
            child.write_text('import time\nfrom pathlib import Path\ntime.sleep(.5)\nPath(' +
                             repr(str(late_output)) + ').write_text("escaped")\n')
            parent = directory / 'parent.py'
            parent.write_text('import subprocess, sys, time\nsubprocess.Popen([sys.executable, ' +
                              repr(str(child)) + '])\ntime.sleep(20)\n')
            with self.assertRaises(tool_api.ToolError) as caught:
                tool_api.run_worker([sys.executable, str(parent)], .15)
            receipt = caught.exception.receipt
            self.assertEqual(receipt['actor'], 'video-utils/tool_api')
            target = receipt['target_ownership']
            self.assertTrue(target['created_by_invocation'])
            self.assertEqual(target['observed_pgid'], target['pid'])
            self.assertEqual(receipt['result']['signal_target'], 'owned_process_group')
            self.assertIn('R-N11', receipt['ruling'])
            time.sleep(.6)
            self.assertFalse(late_output.exists(), 'worker descendant outlived its owned process-group deadline')

    def test_nested_evidence_and_unknowns_survive_the_tool_wrapper(self):
        result = {'source': {'sha256': 'a' * 64, 'kind': 'processed_input'},
                  'lineage': {'original_source_sha256': 'b' * 64, 'status': 'hash_verified'},
                  'timeline': {'audio_start_seconds': 3.25},
                  'interpretation': {'tonic': None, 'mode': None, 'performance_issue': None},
                  'confidence': {'kind': 'heuristic_not_probability', 'score': .42},
                  'flags': [{'source_start_seconds': 4, 'source_end_seconds': 5,
                             'status': 'needs_review', 'performance_issue_confirmed': False}]}
        with tempfile.NamedTemporaryFile() as source, patch.object(tool_api, 'run_worker', return_value=result):
            envelope = tool_api.execute('probe', {'input': source.name})
        self.assertEqual(envelope['result'], result)
        self.assertIsNone(envelope['result']['interpretation']['tonic'])
        self.assertFalse(envelope['result']['flags'][0]['performance_issue_confirmed'])
        self.assertNotEqual(envelope['status'], 'accepted')
        self.assertEqual(json.loads(json.dumps(envelope, allow_nan=False))['result'], result)

    def test_mcp_validation_failure_and_worker_failure_are_distinct(self):
        server = mcp_server.Server()
        server.handle({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                       'params': {'protocolVersion': '2025-11-25', 'capabilities': {},
                                  'clientInfo': {'name': 'contract-test', 'version': '1'}}})
        server.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        invalid = server.handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                                 'params': {'name': 'probe', 'arguments': {'input': 3}}})
        self.assertEqual(invalid['error']['code'], -32602)
        failed = server.handle({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                                'params': {'name': 'probe', 'arguments': {'input': '/nonexistent/private-take.wav'}}})
        self.assertNotIn('error', failed)
        self.assertTrue(failed['result']['isError'])


    def test_extension_knob_errors_do_not_launch_workers(self):
        bad = [
            ('clicks', {'input': 'x', 'run_dir': 'x', 'attenuate': True}),
            ('clicks', {'input': 'x', 'run_dir': 'x', 'template_start': 0}),
            ('clicks', {'input': 'x', 'run_dir': 'x', 'template_start': 0, 'template_end': .5}),
            ('clicks', {'input': 'x', 'run_dir': 'x', 'template_start': 0, 'template_end': .01,
                        'attenuate': True, 'template_click_only': False}),
            ('clicks', {'input': 'x', 'run_dir': 'x', 'strength': .51}),
            ('pitch', {'input': 'x', 'run_dir': 'x', 'max_analysis_seconds': 31}),
            ('pitch', {'input': 'x', 'run_dir': 'x', 'start_seconds': -1}),
            ('pitch', {'input': 'x', 'run_dir': 'x', 'backend': 'install-a-model'}),
            ('meter', {'run_dir': 'x', 'time_signature': '4/4'}),
            ('tonal', {'run_dir': 'x', 'max_regions': 257}),
            ('tonal', {'run_dir': 'x', 'max_recurrences': True}),
            ('tonal', {'run_dir': 'x', 'tonic': 'C'}),
            ('phrase_compare', {'run_dir': 'x', 'band_fraction': 0}),
            ('phrase_compare', {'run_dir': 'x', 'band_fraction': float('inf')}),
            ('phrase_compare', {'run_dir': 'x', 'max_pairs': True}),
            ('benchmark', {'operation': 'fixtures', 'output': 'x', 'profile': 'bypass'}),
            ('benchmark', {'output': 'x', 'phrase_backend': 'install-anything'}),
            ('review', {'run_dir': 'x', 'operation': 'write'}),
            ('review', {'run_dir': 'x', 'operation': 'read', 'input': 'x'}),
            ('review', {'run_dir': 'x', 'operation': 'serve'}),
        ]
        for name, arguments in bad:
            with self.subTest(name=name, arguments=arguments), patch.object(tool_api, 'run_worker') as worker:
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.execute(name, arguments)
                worker.assert_not_called()

    def test_click_worker_uses_only_explicit_analysis_python_and_literal_args(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            source = directory / 'take $(shell); with spaces.wav'
            source.write_bytes(b'fixture')
            arguments = {'input': str(source), 'run_dir': str(directory), 'bpm': 178,
                         'template_start': .1, 'template_end': .11, 'attenuate': True,
                         'template_click_only': True, 'strength': .25}
            with patch.dict(os.environ, {'VIDEO_UTILS_ANALYSIS_PYTHON': '/explicit/analysis/python'}):
                command = tool_api.worker_command('clicks', arguments)
            self.assertEqual(command[0], '/explicit/analysis/python')
            self.assertEqual(command[1:3], [str(ROOT / 'scripts/clicks.py'), str(source)])
            self.assertIn('--attenuate', command)
            self.assertIn('--template-click-only', command)
            self.assertIn('178', command)
            self.assertNotIn('serve', tool_api.worker_command('review', {'run_dir': str(directory)}))


    def test_pitch_dispatch_keeps_budget_and_explicit_interpreter(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            source = directory / 'C1 fixture.wav'; source.write_bytes(b'fixture')
            with patch.dict(os.environ, {'VIDEO_UTILS_ANALYSIS_PYTHON': '/explicit/analysis/python'}):
                command = tool_api.worker_command('pitch', {'input': str(source), 'run_dir': str(directory),
                                                           'max_analysis_seconds': 1, 'start_seconds': 2.5})
            self.assertEqual(command[0], '/explicit/analysis/python')
            self.assertEqual(command[1:3], [str(ROOT / 'scripts/pitch.py'), str(source)])
            self.assertEqual(command[-4:], ['--max-analysis-seconds', '1', '--start-seconds', '2.5'])
            self.assertNotIn('--backend', command)


    def test_real_meter_hook_keeps_notation_unknown_and_rejects_stale_input(self):
        from test_meter import MeterTests
        from test_mcp import exchange, initialization, request
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source, _ = MeterTests().make_run(temporary)
            replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'meter', 'arguments': {'run_dir': temporary}})])
            self.assertEqual(stderr, '')
            self.assertFalse(replies[1]['result']['isError'])
            result = replies[1]['result']['structuredContent']['result']
            artifact = Path(result['output'])
            self.assertTrue(artifact.is_relative_to(directory.resolve()))
            self.assertEqual(hashlib.sha256(artifact.read_bytes()).hexdigest(), result['sha256'])
            meter = json.loads(artifact.read_text())
            self.assertIsNone(meter['time_signature'])
            self.assertTrue(meter['provenance']['no_media_changes'])
            source.write_bytes(b'changed provenance fixture')
            with self.assertRaisesRegex(tool_api.ToolError, 'Analyzed media hash differs'):
                tool_api.execute('meter', {'run_dir': temporary})
            self.assertEqual(len(list((directory / 'meter').glob('*/meter.json'))), 1)


    def test_pitch_real_c1_mcp_summary_and_sparse_coverage(self):
        import importlib.util
        import math
        import statistics
        import struct
        import wave
        from test_mcp import exchange, initialization, request
        interpreter = os.environ.get('VIDEO_UTILS_ANALYSIS_PYTHON')
        if not interpreter:
            if not (importlib.util.find_spec('numpy') and importlib.util.find_spec('librosa')):
                self.skipTest('explicit installed librosa analysis environment is required')
            interpreter = sys.executable
        if not (shutil.which(os.environ.get('FFMPEG', 'ffmpeg')) and
                shutil.which(os.environ.get('FFPROBE', 'ffprobe'))):
            self.skipTest('FFmpeg/FFprobe are required for the optional actual pitch hook')
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / 'known-C1.wav'
            rate, frequency = 16000, 440 * 2 ** ((24 - 69) / 12)
            values = [round(.4 * 32767 * math.tanh(3 * math.sin(2 * math.pi * frequency * i / rate)))
                      for i in range(rate * 2)]
            with wave.open(str(source), 'wb') as stream:
                stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(rate)
                stream.writeframes(struct.pack('<' + 'h' * len(values), *values))
            with patch.dict(os.environ, {'VIDEO_UTILS_ANALYSIS_PYTHON': interpreter}):
                replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                    request(2, 'tools/call', {'name': 'pitch', 'arguments': {
                        'input': str(source), 'run_dir': str(directory), 'max_analysis_seconds': 1,
                        'start_seconds': .25, 'timeout_seconds': 90}})], timeout=120)
            self.assertEqual(stderr, '')
            self.assertFalse(replies[1]['result']['isError'])
            summary = replies[1]['result']['structuredContent']['result']
            self.assertLess(len(json.dumps(summary)), 50000)
            self.assertNotIn('observations', summary)
            self.assertAlmostEqual(summary['analysis']['coverage_fraction'], .5)
            self.assertEqual(summary['analysis']['sampling'], 'explicit_contiguous_excerpt')
            artifact = json.loads(Path(summary['pitch_json']).read_text())
            self.assertIsNone(artifact['interpretation']['intended_notes'])
            self.assertEqual(artifact['interpretation']['performance_grade'], 'not_graded')
            branches = artifact['observations']['analyzed_excerpts'][0]['branches']
            low = next(branch for branch in branches if branch['minimum_hz'] == 28)
            candidates = [frame['frequency_hz'] for frame in low['frames'] if frame['frequency_hz'] is not None]
            self.assertTrue(candidates)
            self.assertAlmostEqual(statistics.median(candidates), frequency, delta=1)
            self.assertTrue(all(frame['note_mapping']['identified_string'] is None
                                for frame in low['frames'] if frame['frequency_hz'] is not None))


    def test_real_tonal_hook_preserves_null_tonic_mode_and_provenance(self):
        from test_tonal import fixture
        from test_mcp import exchange, initialization, request
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            fixture(directory)
            source = directory / 'denoised.wav'
            original = source.read_bytes()
            replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'tonal', 'arguments': {
                    'run_dir': temporary, 'max_regions': 1, 'max_recurrences': 1}})])
            self.assertEqual(stderr, '')
            self.assertFalse(replies[1]['result']['isError'])
            summary = replies[1]['result']['structuredContent']['result']
            self.assertIsNone(summary['tonic'])
            self.assertIsNone(summary['mode'])
            artifact = Path(summary['tonal_json'])
            self.assertTrue(artifact.is_relative_to(directory.resolve() / 'tonal'))
            tonal = json.loads(artifact.read_text())
            self.assertEqual(tonal['performance_grade'], 'not_graded')
            self.assertFalse(tonal['requires_expected_score'])
            self.assertFalse(tonal['instrument_context']['used_as_tonic_prior'])
            for comparison in tonal['recurrence_context_comparisons']:
                self.assertIsNone(comparison['tonal_change'])
                self.assertIsNone(comparison['performance_issue'])
            self.assertEqual(source.read_bytes(), original)
            source.write_bytes(b'mismatched derivative')
            with self.assertRaises(tool_api.ToolError):
                tool_api.execute('tonal', {'run_dir': temporary})
            self.assertEqual(len(list((directory / 'tonal').glob('*/tonal.json'))), 1)

    def test_real_review_read_write_revision_and_source_binding(self):
        from test_mcp import exchange, initialization, request
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest_path = directory / 'manifest.json'
            manifest = {'source': {'sha256': 'a' * 64},
                        'timeline': {'audio_start_seconds': 2.5},
                        'pcm': {'duration_seconds': 10}}
            manifest_path.write_text(json.dumps(manifest))
            write = directory / 'annotation.json'
            write.write_text(json.dumps({'expected_revision': 0, 'annotation': {
                'source_start_seconds': 3, 'source_end_seconds': 4, 'category': 'phrase',
                'status': 'needs_review', 'note': 'Synthetic review candidate; acceptance remains unknown.'}}))
            messages = [initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'review', 'arguments': {'run_dir': temporary}}),
                request(3, 'tools/call', {'name': 'review', 'arguments': {
                    'run_dir': temporary, 'operation': 'write', 'input': str(write)}}),
                request(4, 'tools/call', {'name': 'review', 'arguments': {
                    'run_dir': temporary, 'operation': 'write', 'input': str(write)}})]
            replies, stderr = exchange(messages)
            self.assertEqual(stderr, '')
            self.assertEqual(replies[1]['result']['structuredContent']['result']['revision'], 0)
            saved = replies[2]['result']['structuredContent']['result']
            self.assertEqual(saved['revision'], 1)
            self.assertEqual(saved['listening_acceptance'], 'not_established')
            self.assertEqual(saved['annotations'][0]['source_start_seconds'], 3)
            self.assertTrue(replies[3]['result']['isError'])
            self.assertIn('stale_annotation_revision', replies[3]['result']['content'][0]['text'])
            stored = directory / 'review-annotations.json'
            prior = hashlib.sha256(stored.read_bytes()).hexdigest()
            manifest['source']['sha256'] = 'b' * 64
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(tool_api.ToolError, 'annotation_source_mismatch'):
                tool_api.execute('review', {'run_dir': temporary})
            self.assertEqual(hashlib.sha256(stored.read_bytes()).hexdigest(), prior)

    def test_real_phrase_compare_keeps_missing_features_unknown_and_rejects_lineage(self):
        from test_mcp import exchange, initialization, request
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'manifest.json').write_text(json.dumps({'source': {'sha256': 'a' * 64}}))
            (directory / 'analysis.json').write_text(json.dumps({'source': {'sha256': 'a' * 64}}))
            phrases = {'source': {'sha256': 'a' * 64}, 'observations': {'recurrence_candidates': []}}
            phrases_path = directory / 'phrases.json'; phrases_path.write_text(json.dumps(phrases))
            replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'phrase_compare', 'arguments': {'run_dir': temporary}})])
            self.assertEqual(stderr, '')
            self.assertFalse(replies[1]['result']['isError'])
            self.assertEqual(replies[1]['result']['structuredContent']['result']['status'], 'feature_alignment_unavailable')
            artifact = directory / 'phrase-comparisons.json'
            result = json.loads(artifact.read_text())
            self.assertFalse(result['requires_expected_intent'])
            self.assertEqual(result['flags'], [])
            prior = hashlib.sha256(artifact.read_bytes()).hexdigest()
            phrases['source']['sha256'] = 'b' * 64; phrases_path.write_text(json.dumps(phrases))
            with self.assertRaisesRegex(tool_api.ToolError, 'matching analysis-input identity'):
                tool_api.execute('phrase_compare', {'run_dir': temporary})
            self.assertEqual(hashlib.sha256(artifact.read_bytes()).hexdigest(), prior)

    def test_real_benchmark_fixtures_and_output_root_rejection(self):
        from test_mcp import exchange, initialization, request
        output = ROOT / 'artifacts/benchmarks' / ('contract-' + uuid.uuid4().hex)
        try:
            replies, stderr = exchange([initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                request(2, 'tools/call', {'name': 'benchmark', 'arguments': {
                    'operation': 'fixtures', 'output': str(output), 'timeout_seconds': 90}})], timeout=120)
            self.assertEqual(stderr, '')
            self.assertFalse(replies[1]['result']['isError'])
            result = replies[1]['result']['structuredContent']['result']
            self.assertEqual(result['status'], 'fixtures_created')
            self.assertEqual(result['case_count'], 3)
            self.assertTrue((output / 'fixtures.json').is_file())
            with self.assertRaisesRegex(tool_api.ToolError, 'must not already exist'):
                tool_api.execute('benchmark', {'operation': 'fixtures', 'output': str(output)})
        finally:
            if output.exists():
                shutil.rmtree(output)  # Only this unique test-owned ignored artifact tree.
        with tempfile.TemporaryDirectory() as temporary:
            outside = Path(temporary) / 'must-not-create'
            with self.assertRaisesRegex(tool_api.ToolError, 'beneath artifacts/benchmarks'):
                tool_api.execute('benchmark', {'operation': 'fixtures', 'output': str(outside)})
            self.assertFalse(outside.exists())


if __name__ == '__main__':
    unittest.main()
