"""Closed sharing-only MCP controls, provenance envelope and unchanged prior tools."""
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import tool_api


class ShareExportToolTests(unittest.TestCase):
    def paths(self, root):
        source = root / 'source $(literal);.mov'
        source.write_bytes(b'structural hook fixture, never decoded')
        return {'source': str(source), 'output': str(root / 'share $(literal);.mp4')}

    def test_prior29_descriptors_and_generic_runner_preserved(self):
        registry = tool_api.load_registry()
        digest = hashlib.sha256(json.dumps(registry['tools'][:29], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(digest, '5e92c39ff92759bf4f9c191d0b0d10e8494eff926a63415d8a60f3a8aee52b07')
        self.assertEqual(hashlib.sha256(inspect.getsource(tool_api.run_worker).encode()).hexdigest(), 'acd72926a70c33cc92bd056f055fb83f348ad2e7c9a3576e7bfcd6d20e9bd3af')

    def test_literal_fixed_argv_and_single_public_timeout(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve(); args = self.paths(root)
            result = {'status': 'exported_unreviewed', 'listening_accepted': False, 'master_adopted': False, 'source': {'path': args['source'], 'sha256': 'a'*64, 'bytes': 32}, 'output': {'path': args['output'], 'sha256': 'b'*64, 'bytes': 16, 'receipt_path': args['output']+'.receipt.json', 'receipt_sha256': 'c'*64}}
            with patch.object(tool_api, 'ROOT', root), patch.object(tool_api, 'run_worker', return_value=result) as worker:
                envelope = tool_api.execute('share_export', args)
                custom = dict(args, height=480, crf=30, audio_kbps=128, codec='h264', timeout_seconds=40)
                tool_api.execute('share_export', custom)
            first, second = worker.call_args_list
            command, timeout = first.args
            self.assertEqual(command[1:], [str(root/'scripts/share_export.py'), args['source'], args['output'], '--height', '720', '--crf', '27', '--audio-kbps', '96', '--codec', 'h264', '--timeout-seconds', '900', '--tool-envelope'])
            self.assertEqual(timeout, 900)
            self.assertEqual(second.args[1], 40); self.assertEqual(second.args[0][-3:], ['--timeout-seconds', '40', '--tool-envelope'])
            self.assertEqual(envelope['evidence_kind'], 'lossy_sharing_derivative')
            self.assertFalse(envelope['result']['listening_accepted'])

    def test_closed_finite_bounds_and_even_height_reject_before_worker(self):
        with tempfile.TemporaryDirectory() as name:
            args = self.paths(Path(name))
            for extra in ({'height': 721}, {'height': True}, {'height': 1082}, {'crf': 17}, {'audio_kbps': 193}, {'codec': 'shell'}, {'timeout_seconds': 29}, {'timeout_seconds': 901}, {'timeout_seconds': True}, {'crf': float('nan')}, {'filter': 'arbitrary'}, {'model': 'x'}, {'source': '../outside.mov'}, {'output': 'https://host/share.mp4'}, {'source': 'null\0.mov'}):
                with self.subTest(extra=extra), patch.object(tool_api, 'run_worker') as worker:
                    with self.assertRaises(tool_api.ValidationError):
                        tool_api.execute('share_export', dict(args, **extra))
                    worker.assert_not_called()

    def test_missing_symlink_existing_receipt_and_oversize_refuse_prelaunch(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve(); args = self.paths(root)
            link = root/'linked.mov'; link.symlink_to(args['source'])
            receipt = Path(args['output']+'.receipt.json'); receipt.write_text('{}')
            with patch.object(tool_api, 'ROOT', root), patch.object(tool_api, 'run_worker') as worker:
                for extra in ({}, {'source': str(link)}, {'source': str(root/'missing.mov')}, {'output': str(root/'missing-dir/share.mp4')}, {'output': args['source']}, {'output': str(root/'share.wav')}):
                    with self.subTest(extra=extra), self.assertRaises(tool_api.ToolError):
                        tool_api.execute('share_export', dict(args, **extra))
                receipt.unlink()
                with Path(args['source']).open('r+b') as stream: stream.truncate(3*1024**3+1)
                with self.assertRaises(tool_api.ToolError): tool_api.execute('share_export', args)
                worker.assert_not_called()
                self.assertFalse(Path(args['output']).exists())

    def test_real_initialized_preflight_and_exact_prompt(self):
        from test_mcp import exchange, initialization, request
        messages = [initialization(), {'jsonrpc': '2.0', 'method': 'notifications/initialized'}, request(2, 'tools/list'), request(3, 'prompts/get', {'name': 'media-share-export'}), request(4, 'tools/call', {'name': 'share_export', 'arguments': {'source': 'absent-source.mov', 'output': 'absent-parent/share.mp4'}}), request(5, 'tools/call', {'name': 'share_export', 'arguments': {'source': 'absent-source.mov', 'output': 'absent-parent/share.mp4', 'height': 721}})]
        replies, stderr = exchange(messages, timeout=20)
        self.assertEqual(stderr, '')
        self.assertEqual(len(replies[1]['result']['tools']), 39)
        schema = next(row['inputSchema'] for row in replies[1]['result']['tools'] if row['name']=='share_export')
        self.assertEqual(schema['required'], ['source', 'output']); self.assertFalse(schema['additionalProperties'])
        self.assertEqual(replies[2]['result']['messages'][0]['content']['text'], (ROOT/'.agents/skills/media-share-export/SKILL.md').read_text())
        self.assertTrue(replies[3]['result']['isError']); self.assertIn('unavailable', replies[3]['result']['content'][0]['text'])
        self.assertEqual(replies[4]['error']['code'], -32602)

    def test_domain_exit0_failure_is_error_with_exact_recovery(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();args=self.paths(root)
            recovery={'path':args['output'],'sha256':'a'*64,'bytes':12,
                      'receipt_path':args['output']+'.receipt.json','receipt_sha256':'b'*64}
            common={'error':'reporting interrupted','code':'export_failed','staging_dir':str(root/'staging'),
                    'failure_receipt_path':str(root/'staging/failure-receipt.json'),'failure_receipt_sha256':'c'*64,
                    'stage_progress':[],'master_adopted':False,'listening_accepted':False}
            for status,output,possible in (('failed_no_export_published',None,None),
                    ('exported_unreviewed_reporting_interrupted',recovery,None),
                    ('publication_outcome_unknown',None,recovery)):
                result=dict(common,status=status,output=output,possible_output=possible)
                with self.subTest(status=status),patch.object(tool_api,'ROOT',root),patch.object(tool_api,'run_worker',return_value=result):
                    with self.assertRaises(tool_api.ToolError) as caught:tool_api.execute('share_export',args)
                    self.assertEqual(caught.exception.receipt['share_export'],result)

    def test_truthful_bounded_projection_and_malformed_statuses(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();args=self.paths(root)
            result={'status':'publication_outcome_unknown','error':'unknown','code':'export_failed',
                    'output':None,'possible_output':{'path':args['output'],'sha256':'a'*64,'bytes':12,
                    'receipt_name':Path(args['output']+'.receipt.json').name,'receipt_sha256':'b'*64},
                    'failure_receipt_path':str(root/'failure-receipt.json'),'failure_receipt_sha256':'c'*64,
                    'stage_progress':[],'master_adopted':False,'listening_accepted':False,
                    'diagnostic_fields_omitted':['staging_dir','possible_output.receipt_path','stage_progress']}
            with self.assertRaises(tool_api.ToolError) as caught:tool_api.classify_share_export_result(result,args)
            self.assertEqual(caught.exception.receipt['share_export'],result)
            for bad in ({'status':[]},{'status':'completed'},{'status':'exported_unreviewed','master_adopted':True},
                        dict(result,diagnostic_fields_omitted=['arbitrary']),dict(result,stage_progress=[{}]),
                        dict(result,extra='unknown'),dict(result,error='x'*(16*1024))):
                with self.subTest(bad=bad),self.assertRaises(tool_api.ToolError) as failed:
                    tool_api.classify_share_export_result(bad,args)
                self.assertIsNone(failed.exception.receipt)

    def test_real_tool_envelope_failure_never_reports_completed(self):
        from test_mcp import exchange, initialization, request
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();args=self.paths(root)
            with patch.dict(os.environ,{'FFMPEG':'/nonexistent/no-encode','FFPROBE':'/nonexistent/no-probe'}):
                replies,stderr=exchange([initialization(),{'jsonrpc':'2.0','method':'notifications/initialized'},
                    request(2,'tools/call',{'name':'share_export','arguments':args})],timeout=20)
            self.assertEqual(stderr,'');self.assertTrue(replies[1]['result']['isError'])
            self.assertIn('failed_no_export_published',replies[1]['result']['content'][0]['text'])
            self.assertIn('failure_receipt_path',replies[1]['result']['content'][0]['text'])
            self.assertFalse(Path(args['output']).exists())


if __name__ == '__main__': unittest.main()
