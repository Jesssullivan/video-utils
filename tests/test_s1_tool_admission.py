"""Exercise new S1 tools through real initialized MCP and exact-path refusal."""
import copy
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import tool_api
from test_mcp import exchange, initialization, request


class SprintToolAdmissionTests(unittest.TestCase):
    def call(self, name, arguments):
        replies, stderr = exchange([initialization(),
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            request(2, 'tools/call', {'name': name, 'arguments': arguments})])
        self.assertEqual(stderr, '')
        return replies[1]['result']

    def test_original_thirty_descriptors_preserved(self):
        tools = tool_api.descriptors()
        self.assertEqual(len(tools), 38)
        original = json.dumps(tools[:30], sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
        self.assertEqual(hashlib.sha256(original).hexdigest(),
                         '85fa376c6d6a64e8d2c7c332deb27cf14b4b490fb6f7f1c9ed51efb5ee3a06c7')

    def test_closed_schemas_refuse_before_worker(self):
        invalid = [('annotation_v2', {'run_dir': '/unopened', 'operation': 'write'}),
                   ('annotation_v2', {'run_dir': '/unopened', 'input': '/unopened.json'}),
                   ('annotation_v2', {'run_dir': '/unopened', 'runtime_python': '/bin/python'}),
                   ('corpus_split', {'manifest': '../leak.json'}),
                   ('corpus_split', {'manifest': 'fixture.json', 'train': True})]
        for name, arguments in invalid:
            with self.subTest(name=name, arguments=arguments), patch.object(tool_api, 'run_worker') as worker:
                with self.assertRaises(tool_api.ValidationError):
                    tool_api.execute(name, arguments)
                worker.assert_not_called()

    def test_new_tools_refuse_ancestor_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary).resolve()
            real = root / 'actual'; real.mkdir()
            run = real / 'run'; run.mkdir()
            manifest = real / 'split.json'; manifest.write_text('{}')
            alias = root / 'alias'; alias.symlink_to(real, target_is_directory=True)
            for name, arguments in [('annotation_v2', {'run_dir': str(alias / 'run')}),
                                    ('corpus_split', {'manifest': str(alias / 'split.json'), 'local_root': str(alias)}),
                                    ('corpus_split', {'manifest': str(manifest), 'local_root': str(alias)})]:
                with self.subTest(name=name, arguments=arguments), patch.object(tool_api, 'run_worker') as worker:
                    with self.assertRaises(tool_api.ToolError):
                        tool_api.execute(name, arguments)
                    worker.assert_not_called()

    def test_real_mcp_annotation_replay_and_refusal_preserve_store(self):
        with tempfile.TemporaryDirectory(prefix='s1 音 ') as temporary:
            root = pathlib.Path(temporary).resolve()
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps({'source': {'sha256': 'a' * 64, 'path': 'unavailable.mov'},
                'timeline': {'audio_start_seconds': 2, 'format_start_seconds': 1},
                'pcm': {'duration_seconds': 8}}))
            body = {'schema_version': 2, 'expected_revision': 0, 'idempotency_key': 'example-00000001',
                'source_sha256': 'a' * 64, 'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
                'annotation': {'kind': 'noise', 'basis': 'operator_context', 'status': 'needs_review',
                    'source_span': {'start_seconds': 2, 'end_seconds': 3, 'extent_known': True},
                    'reported_by': {'actor': 'operator', 'via': 'agent'}, 'operator_certainty': None,
                    'operator_quote': None, 'note': 'Fictional setup context 音; unknown purity.'}}
            selected = root / 'request $(literal);.json'; selected.write_text(json.dumps(body))
            args = {'run_dir': str(root), 'operation': 'write', 'input': str(selected)}
            first = self.call('annotation_v2', args)
            self.assertFalse(first.get('isError', False), first)
            path = root / 'review-annotations-v2.json'; before = path.read_bytes()
            replay = self.call('annotation_v2', args)
            self.assertFalse(replay.get('isError', False), replay)
            self.assertEqual(path.read_bytes(), before)
            for changes in ({'source_sha256': 'b' * 64}, {'idempotency_key': 'example-00000002'}):
                invalid = copy.deepcopy(body); invalid.update(changes)
                selected.write_text(json.dumps(invalid))
                result = self.call('annotation_v2', args)
                self.assertTrue(result['isError'])
                self.assertEqual(path.read_bytes(), before)
            readback = self.call('annotation_v2', {'run_dir': str(root)})
            self.assertFalse(readback.get('isError', False), readback)

    def test_real_mcp_corpus_split_and_leakage_refusal(self):
        from test_corpus_split_s1 import record
        with tempfile.TemporaryDirectory(prefix='s1 split 音 ') as temporary:
            root = pathlib.Path(temporary).resolve(); path = root / 'split $(literal);.json'
            body = {'schema_id': 'video-utils.corpus-split.s1', 'schema_version': 1,
                'corpus_id': 'synthetic-admission', 'revision': 1,
                'coverage': 'sparse_or_unknown_no_negative_inference', 'approval_state': 'unreviewed',
                'records': [record()], 'context_refs': []}
            path.write_text(json.dumps(body)); before = path.read_bytes()
            args = {'manifest': str(path), 'local_root': str(root)}
            result = self.call('corpus_split', args)
            self.assertFalse(result.get('isError', False), result)
            self.assertEqual(path.read_bytes(), before)
            body['records'].append(record('derivative', partition='test'))
            path.write_text(json.dumps(body)); before = path.read_bytes()
            refusal = self.call('corpus_split', args)
            self.assertTrue(refusal['isError'])
            self.assertEqual(path.read_bytes(), before)
