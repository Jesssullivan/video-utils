import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import tool_api


class ToolsTests(unittest.TestCase):
    def test_catalog_has_intent_and_strict_schemas(self):
        catalog = tool_api.load_registry()
        self.assertGreaterEqual(len(catalog['tools']), 12)
        self.assertEqual(catalog['instrument_context']['lowest_intentional_fundamental_hz'], 32)
        for item in catalog['tools']:
            self.assertTrue(item['intent'])
            self.assertTrue(item['limitations'])
            self.assertFalse(item['inputSchema']['additionalProperties'])

    def test_unsupported_schema_is_rejected_instead_of_ignored(self):
        with self.assertRaises(ValueError):
            tool_api.validate_schema({'type': 'string', 'pattern': '.*'})

    def test_schema_rejects_injection_keys_wrong_types_and_bad_knobs(self):
        for name, arguments in [
            ('probe', {'input': 'x', 'command': 'rm -rf anything'}),
            ('denoise', {'input': 'x', 'profile': '../../../other'}),
            ('probe', {'input': 'x', 'timeout_seconds': True}),
            ('probe', {'input': 'x', 'timeout_seconds': 901}),
            ('rhythm', {'input': 'x', 'run_dir': 'x', 'bpm': float('nan')}),
            ('rhythm', {'input': 'x', 'run_dir': 'x', 'bpm': 0}),
            ('probe', {'input': 'x\x00anything'}),
            ('pipeline', {'run_dir': 'x', 'reference': 12}),
            ('pipeline', {'run_dir': 'x', 'execute_shell': 'anything'}),
            ('markers', {'run_dir': 'x', 'editor': 'final_cut_pro'}),
            ('phrases', {'input': 'x', 'run_dir': 'x', 'backend': 'unknown'}),
            ('phrases', {'input': 'x', 'run_dir': 'x', 'bpm': 401}),
            ('notes', {'input': 'x', 'run_dir': 'x', 'backend': 'librosa'}),
            ('probe', {}), ('nonexistent', {})]:
            with self.subTest(name=name, arguments=arguments), self.assertRaises(tool_api.ValidationError):
                tool_api.execute(name, arguments)

    def test_source_shell_characters_are_passed_literally(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'take $(touch surprise);`echo nope`.wav'
            source.write_bytes(b'fixture')
            command = tool_api.worker_command('probe', {'input': str(source)})
            self.assertEqual(command[-1], str(source.resolve()))
            self.assertEqual(command[2], 'probe')
            self.assertNotIn('shell', command)



    def test_phrase_backend_and_tempo_are_forwarded_with_explicit_python(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / 'take.wav'; source.write_bytes(b'fixture')
            with patch.dict(os.environ, {'VIDEO_UTILS_ANALYSIS_PYTHON': '/explicit/analysis/python'}):
                command = tool_api.worker_command('phrases', {'input': str(source), 'run_dir': str(root),
                                                              'backend': 'librosa', 'bpm': 178})
            self.assertEqual(command[0], '/explicit/analysis/python')
            self.assertEqual(command[-4:], ['--backend', 'librosa', '--bpm', '178'])
            command = tool_api.worker_command('phrases', {'input': str(source), 'run_dir': str(root)})
            self.assertEqual(command[-2:], ['--backend', 'stdlib'])
            self.assertNotIn('--bpm', command)

    def test_pipeline_reference_and_markers_dispatch_are_typed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            reference = root / 'approved reference.json'
            reference.write_text('{"schema_version":1,"approved":false}')
            command = tool_api.worker_command('pipeline', {'run_dir': str(root), 'reference': str(reference)})
            self.assertEqual(command[1:], [str(ROOT / 'scripts/dag.py'), str(root), '--reference', str(reference)])
            marker_command = tool_api.worker_command('markers', {'run_dir': str(root)})
            self.assertEqual(marker_command[1:], [str(ROOT / 'scripts/markers.py'), str(root)])
            with self.assertRaises(tool_api.ToolError):
                tool_api.worker_command('pipeline', {'run_dir': str(root), 'reference': str(root / 'missing.json')})

    def test_result_envelope_preserves_uncertainty(self):
        with tempfile.NamedTemporaryFile() as source:
            with patch.object(tool_api, 'run_worker', return_value={'performance': {'status': 'not_graded'}}):
                result = tool_api.execute('rhythm', {'input': source.name, 'run_dir': '/tmp/video-utils-test'})
            self.assertEqual(result['result']['performance']['status'], 'not_graded')
            self.assertEqual(result['implementation_status'], 'experimental')
            self.assertIn('expected-rhythm', result['limitations'][0])

    def worker(self, text, timeout=2):
        with tempfile.TemporaryDirectory() as temporary:
            script = Path(temporary) / 'worker.py'
            script.write_text(text)
            return tool_api.run_worker([sys.executable, str(script)], timeout)

    def test_worker_single_object_and_execution_errors(self):
        self.assertEqual(self.worker('print(\'{"status":"unknown"}\')'), {'status': 'unknown'})
        for text in ["print('[]')", "print('debug'); print('{}')", "print('{\"value\": NaN}')",
                     "import sys; print('failure', file=sys.stderr); sys.exit(7)"]:
            with self.subTest(text=text), self.assertRaises(tool_api.ToolError):
                self.worker(text)

    def test_timeout_stops_owned_worker(self):
        with self.assertRaisesRegex(tool_api.ToolError, 'deadline exceeded') as caught:
            self.worker('import time; time.sleep(30)', timeout=.1)
        self.assertTrue(caught.exception.receipt['target_ownership']['created_by_invocation'])
        self.assertIn('R-N11', caught.exception.receipt['ruling'])
        self.assertEqual(caught.exception.receipt['result']['signal_target'], 'owned_process_group')

    def test_worker_result_size_is_bounded(self):
        with self.assertRaisesRegex(tool_api.ToolError, 'result limit'):
            self.worker("print('x' * (2 * 1024 * 1024 + 1))")

    def test_cli_invalid_json_has_no_success_stdout(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/tool_api.py'), 'run', 'probe',
                                 '--arguments', '{invalid}'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertEqual(json.loads(result.stderr)['status'], 'error')


if __name__ == '__main__':
    unittest.main()
