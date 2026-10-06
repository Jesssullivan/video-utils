"""Typed application-only integration, separate from inert supervisor proofs."""
import hashlib
import copy
import inspect
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import tool_api
from capture_application_adapter import AdapterError

class ApplicationToolTests(unittest.TestCase):
    def paths(self,root):
        original=root/'literal $(data); take.wav';original.write_bytes(b'fixture-metadata-not-audio')
        author=root/'artifacts/runs/fixture/capture-profiles/one';author.mkdir(parents=True)
        for name in ('profile.json','receipt.json'):(author/name).write_text('{}')
        return {'input':str(original),'authoring_dir':str(author),'receipt_sha256':'a'*64}

    def test_original27_descriptors_and_runner_source_preserved(self):
        records=tool_api.load_registry()['tools']
        self.assertGreaterEqual(len(records),28)
        previous=copy.deepcopy(records[:27])
        marked=next(row for row in previous if row['name']=='marked_video')
        extension=marked['inputSchema']['properties'].pop('arrangement_markers',None)
        self.assertEqual(extension,{'type':'string','minLength':1,'maxLength':1024,'description':'Optional exact same-run-relative source-bound arrangement marker JSON; requires explicit selection all-review. Renderer revalidates assessment/reference/current artifact hashes; no confirmed-mistake labels.'})
        self.assertEqual(hashlib.sha256(json.dumps(previous,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'f6d10ecf160c0b71eab9fc9f5bf21ef5756393898b2c6f6525056a5a8e358e8a')
        self.assertEqual(hashlib.sha256(inspect.getsource(tool_api.run_worker).encode()).hexdigest(),'acd72926a70c33cc92bd056f055fb83f348ad2e7c9a3576e7bfcd6d20e9bd3af')

    def test_closed_schema_prevents_override_and_unsafe_paths_before_launch(self):
        args={'input':'source.mov','authoring_dir':'artifacts/runs/run/capture-profiles/id','receipt_sha256':'a'*64}
        invalid=[{'timeout_seconds':True},{'timeout_seconds':11},{'timeout_seconds':601},{'receipt_sha256':'Z'*64},{'output':'new'},{'filter':'x'},{'runtime':'/bin/python'},{'input':'nul\x00path'},{'input':'../outside'},{'authoring_dir':'https://remote/id'},{'authoring_dir':'artifacts/runs/.stage/id'}]
        for extra in invalid:
            with self.subTest(extra=extra),patch('capture_application_adapter.ApplicationAdapter.run') as launch,patch.object(tool_api,'run_worker') as old:
                with self.assertRaises(tool_api.ValidationError):tool_api.execute('apply_capture_profile',dict(args,**extra))
                launch.assert_not_called();old.assert_not_called()

    def test_dispatch_uses_application_supervisor_only_and_literal_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();args=self.paths(root)
            result={'status':'rendered_unreviewed','listening_accepted':False,'master_adopted':False}
            with patch.object(tool_api,'ROOT',root),patch('capture_application_adapter.ApplicationAdapter.run',return_value=result) as adapter,patch.object(tool_api,'run_worker') as old:
                envelope=tool_api.execute('apply_capture_profile',args)
            old.assert_not_called();self.assertEqual(adapter.call_args.args[0],args)
            self.assertEqual(envelope['result'],result);self.assertEqual(envelope['evidence_kind'],'source_bound_capture_profile_application')

    def test_preflight_missing_symlink_wrong_boundary_and_oversize_refuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();args=self.paths(root)
            original=Path(args['input']);linked=root/'linked.wav';linked.symlink_to(original)
            with patch.object(tool_api,'ROOT',root),patch('capture_application_adapter.ApplicationAdapter.run') as adapter:
                for extra in ({'input':str(linked)},{'input':str(root/'missing')},{'authoring_dir':str(root) }):
                    with self.subTest(extra=extra),self.assertRaises(tool_api.ToolError):tool_api.execute('apply_capture_profile',dict(args,**extra))
                (Path(args['authoring_dir'])/'profile.json').write_bytes(b'x'*16385)
                with self.assertRaises(tool_api.ToolError):tool_api.execute('apply_capture_profile',args)
                adapter.assert_not_called()

    def test_unknown_supervision_and_worker_recovery_remain_structured(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();args=self.paths(root)
            diagnostic={'status':'publication_outcome_unknown','committed_candidate':None,'possible_candidate':{'run_dir':'prepared-only'}}
            error=AdapterError('unverified outcome',receipt={'path':'exact-receipt','sha256':'b'*64},diagnostic=diagnostic,finalized=True)
            with patch.object(tool_api,'ROOT',root),patch('capture_application_adapter.ApplicationAdapter.run',side_effect=error):
                with self.assertRaises(tool_api.ToolError) as caught:tool_api.execute('apply_capture_profile',args)
            self.assertEqual(caught.exception.receipt['worker_diagnostic'],diagnostic)
            self.assertEqual(caught.exception.receipt['publication_outcome'],'inspect_exact_durable_receipts')
            self.assertFalse(caught.exception.receipt['worker_diagnostic_omitted'])
            error.diagnostic={'large':'x'*16350}
            with patch.object(tool_api,'ROOT',root),patch('capture_application_adapter.ApplicationAdapter.run',side_effect=error):
                with self.assertRaises(tool_api.ToolError) as large:tool_api.execute('apply_capture_profile',args)
            self.assertTrue(large.exception.receipt['worker_diagnostic_omitted'])
            self.assertIsNone(large.exception.receipt['worker_diagnostic'])
            self.assertEqual(large.exception.receipt['application_supervision'],error.receipt)

    def test_real_initialized_mcp_wrong_pin_fails_before_media(self):
        from test_mcp import exchange,initialization,request
        root=ROOT/'artifacts/runs'/('contract-apply-negative-'+uuid.uuid4().hex)
        root.mkdir(parents=True);self.addCleanup(shutil.rmtree,root,ignore_errors=True)
        args=self.paths(root)
        # Authoring path belongs to a real repository run, metadata intentionally invalid.
        author=root/'capture-profiles/id';author.mkdir(parents=True)
        for name in ('profile.json','receipt.json'):(author/name).write_text('{}')
        args['authoring_dir']=str(author)
        replies,stderr=exchange([initialization(),{'jsonrpc':'2.0','method':'notifications/initialized'},request(2,'tools/call',{'name':'apply_capture_profile','arguments':args})],timeout=20)
        self.assertEqual(stderr,'');self.assertTrue(replies[1]['result']['isError'])
        error=json.loads(replies[1]['result']['content'][0]['text'])
        ref=error['receipt']['application_supervision'];receipt=json.loads(Path(ref['path']).read_text())
        self.assertEqual(receipt['status'],'worker_error');self.assertEqual(receipt['events'],[])
        self.assertIsNotNone(error['receipt']['worker_diagnostic'])

    def test_actual_prompt_and_schema_readback(self):
        from test_mcp import exchange,initialization,request
        replies,stderr=exchange([initialization(),{'jsonrpc':'2.0','method':'notifications/initialized'},request(2,'tools/list'),request(3,'prompts/get',{'name':'guitar-apply-capture-profile'})])
        self.assertEqual(stderr,'');self.assertEqual(len(replies[1]['result']['tools']),len(tool_api.descriptors()))
        tool=next(row for row in replies[1]['result']['tools'] if row['name']=='apply_capture_profile')
        self.assertEqual(set(tool['inputSchema']['properties']),{'input','authoring_dir','receipt_sha256','timeout_seconds'})
        self.assertEqual(replies[2]['result']['messages'][0]['content']['text'],(ROOT/'.agents/skills/guitar-apply-capture-profile/SKILL.md').read_text())

if __name__=='__main__':unittest.main()
