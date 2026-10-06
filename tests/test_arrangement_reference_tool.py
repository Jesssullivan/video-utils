"""Run-derived metadata MCP and additive marked-video selector contracts."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import uuid
import wave
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import tool_api

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):path.write_text(json.dumps(value,allow_nan=False)+'\n');return sha(path)

class ArrangementToolTests(unittest.TestCase):
    def metadata_paths(self,root):
        run=root/'artifacts/runs/selected';run.mkdir(parents=True)
        ref=root/'reference $(literal);.json';ref.write_text('{}')
        for name in ('manifest.json','analysis.json','phrases.json'):(run/name).write_text('{}')
        return {'run_dir':str(run),'reference':str(ref),'output':str(run/'fresh')}

    def test_closed_schema_and_fixed_literal_argv(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();args=self.metadata_paths(root)
            with patch.object(tool_api,'ROOT',root),patch.object(tool_api,'run_worker',return_value={'status':'reference_conditioned_review_candidates'}) as worker:
                envelope=tool_api.execute('arrangement_reference',args)
            command,timeout=worker.call_args.args
            self.assertEqual(command[1:],[str(root/'scripts/arrangement_reference.py'),args['reference'],'--run-dir',args['run_dir'],'--output',args['output']]);self.assertEqual(timeout,120)
            self.assertEqual(envelope['evidence_kind'],'reference_conditioned_review_candidates')
            for extra in ({'timeout_seconds':True},{'timeout_seconds':121},{'observations':'x.json'},{'model':'weights'},{'reference':'../outside.json'},{'output':'https://host/file'},{'run_dir':'dot\x00nul'}):
                with self.subTest(extra=extra),patch.object(tool_api,'run_worker') as launch:
                    with self.assertRaises(tool_api.ValidationError):tool_api.execute('arrangement_reference',dict(args,**extra))
                    launch.assert_not_called()

    def test_output_boundary_existing_symlink_and_byte_bounds_fail_prelaunch(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();args=self.metadata_paths(root);run=Path(args['run_dir'])
            link=root/'linked.json';link.symlink_to(Path(args['reference']))
            existing=run/'existing';existing.mkdir()
            with patch.object(tool_api,'ROOT',root),patch.object(tool_api,'run_worker') as launch:
                for extra in ({'output':str(root/'artifacts/runs/other')},{'output':str(existing)},{'reference':str(link)},{'reference':str(root/'missing.json')}):
                    with self.subTest(extra=extra),self.assertRaises(tool_api.ToolError):tool_api.execute('arrangement_reference',dict(args,**extra))
                (run/'phrases.json').write_bytes(b'x'*(4*1024**2+1))
                with self.assertRaises(tool_api.ToolError):tool_api.execute('arrangement_reference',args)
                launch.assert_not_called()

    def fixture(self):
        from test_arrangement_reference_audit import adapter_fixture,reference
        run=ROOT/'artifacts/runs'/('contract-arrangement-'+uuid.uuid4().hex);run.mkdir(parents=True)
        self.addCleanup(shutil.rmtree,run,ignore_errors=True)
        pcm=run/'denoised.wav'
        with wave.open(str(pcm),'wb') as stream:
            stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(48000);stream.writeframes(b'\0\0'*384000)
        manifest,analysis,phrases=adapter_fixture()
        native=sha(pcm);manifest['output_sha256']['denoised.wav']=native
        analysis['source']['sha256']=native;phrases['source']['sha256']=native
        edge=phrases['observations']['segment_candidates'][0]
        first=dict(edge,end_seconds=4,source_end_seconds=11.25)
        second=dict(edge,start_seconds=4,source_start_seconds=11.25)
        phrases['observations']['segment_candidates']=[first,second]
        manifest_hash=save(run/'manifest.json',manifest)
        analysis['source_lineage']['manifest_sha256']=manifest_hash
        save(run/'analysis.json',analysis);save(run/'phrases.json',phrases)
        ref=run/'reference.json';save(ref,reference(anchor=(7.25,7.25),counts=(4,4)))
        return run,{'run_dir':str(run),'reference':str(ref),'output':str(run/'assessment')}

    def call(self,args):
        from test_mcp import exchange,initialization,request
        with patch.dict(os.environ,{'FFMPEG':'/nonexistent/no-decode','FFPROBE':'/nonexistent/no-probe','VIDEO_UTILS_ANALYSIS_PYTHON':'/nonexistent/no-inference'}):
            replies,stderr=exchange([initialization(),{'jsonrpc':'2.0','method':'notifications/initialized'},request(2,'tools/call',{'name':'arrangement_reference','arguments':args})],timeout=20)
        self.assertEqual(stderr,'');return replies[1]['result']

    def test_real_stdio_assessment_preserves_intent_nulls_and_native_hashes(self):
        run,args=self.fixture();before={name:sha(run/name) for name in ('manifest.json','analysis.json','phrases.json','denoised.wav','reference.json')}
        reply=self.call(args);self.assertFalse(reply.get('isError'),reply)
        summary=reply['structuredContent']['result'];self.assertEqual(summary['intended_click_count'],8);self.assertIsNone(summary['observed_click_count'])
        receipt=json.loads((Path(args['output'])/'receipt.json').read_text());assessment=json.loads((Path(args['output'])/'assessment.json').read_text())
        self.assertFalse(receipt['audio_decoded']);self.assertFalse(receipt['dsp_performed']);self.assertTrue(receipt['canonical_pcm_read_for_hash'])
        self.assertFalse(assessment['performance_issue_confirmed']);self.assertIn('original encoded media not rehashed',assessment['binding']['source_identity_scope'])
        self.assertEqual(before,{name:sha(run/name) for name in before})
        for name,digest in summary['output_sha256'].items():self.assertEqual(sha(Path(args['output'])/name),digest)
        self.assertTrue(all(not row['performance_issue_confirmed'] for row in assessment['review_candidates']))

    def test_real_stdio_stale_lineage_and_changed_pcm_reject_without_output(self):
        run,args=self.fixture();analysis=json.loads((run/'analysis.json').read_text());analysis['source_lineage']['manifest_sha256']='f'*64;save(run/'analysis.json',analysis)
        reply=self.call(args);self.assertTrue(reply['isError']);self.assertIn('lineage stale',reply['content'][0]['text']);self.assertFalse(Path(args['output']).exists())
        analysis['source_lineage']['manifest_sha256']=sha(run/'manifest.json');save(run/'analysis.json',analysis)
        with (run/'denoised.wav').open('ab') as stream:stream.write(b'tampered')
        reply=self.call(args);self.assertTrue(reply['isError']);self.assertIn('PCM hash differs',reply['content'][0]['text']);self.assertFalse(Path(args['output']).exists())

    def test_marked_selector_forwarding_crossrule_and_no_absolute_paths(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name).resolve();args=self.metadata_paths(root);run=Path(args['run_dir']);marker=run/'arrangement markers.json';marker.write_text('{}')
            valid={'run_dir':str(run),'output':str(run/'preview'),'selection':'all-review','arrangement_markers':marker.name}
            with patch.object(tool_api,'ROOT',root),patch.object(tool_api,'run_worker',return_value={}) as launch:
                tool_api.execute('marked_video',valid)
            command,timeout=launch.call_args.args;self.assertEqual(command[-2:],['--arrangement-markers',marker.name]);self.assertEqual(timeout,600)
            for extra in ({'selection':'phrase-review'},{'arrangement_markers':str(marker)},{'arrangement_markers':'../markers.json'},{'arrangement_markers':'x'*1025}):
                with self.subTest(extra=extra),patch.object(tool_api,'run_worker') as worker:
                    with self.assertRaises(tool_api.ValidationError):tool_api.execute('marked_video',dict(valid,**extra))
                    worker.assert_not_called()

    def test_live29_prompt_exact_and_marked_optional_schema(self):
        from test_mcp import exchange,initialization,request
        replies,stderr=exchange([initialization(),{'jsonrpc':'2.0','method':'notifications/initialized'},request(2,'tools/list'),request(3,'prompts/get',{'name':'guitar-arrangement-reference'})])
        self.assertEqual(stderr,'');self.assertGreaterEqual(len(replies[1]['result']['tools']),29)
        self.assertEqual(replies[2]['result']['messages'][0]['content']['text'],(ROOT/'.agents/skills/guitar-arrangement-reference/SKILL.md').read_text())
        marked=next(row for row in replies[1]['result']['tools'] if row['name']=='marked_video');self.assertNotIn('arrangement_markers',marked['inputSchema']['required'])

if __name__=='__main__':unittest.main()
