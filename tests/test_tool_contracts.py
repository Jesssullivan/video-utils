"""Cross-tool contract checks independent of proposed extension implementation."""
import json
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


if __name__ == '__main__':
    unittest.main()
