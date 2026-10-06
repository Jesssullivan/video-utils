#!/usr/bin/env python3
"""One root-authorized generated8s typed stdio trial; no operator recording."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
FIXTURE=ROOT/'artifacts/experiments/capture-application-native-qualification/native-resource-20261006T0340'
PINS={'application':'790ac58f1924db2607087c6ab1cdae5d813ba24eda610af1f396d77e93d06584','supervisor':'ea2d27400b98a2c7285f068501100c222fbb969a56d53d497a3b141b1c70f5a8'}
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,data):path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
def run():
    assert sha(ROOT/'scripts/apply_capture_profile.py')==PINS['application']
    assert sha(ROOT/'scripts/capture_application_adapter.py')==PINS['supervisor']
    authored=json.loads((FIXTURE/'authoring-summary.json').read_text())
    source=FIXTURE/'original.mov';author=Path(authored['output_dir'])
    assert sha(source)==authored['source_sha256']=='9304f783e0b4b82973c98fff2cda457013abe1a3716bf57285647f2d62bb283e'
    assert sha(author/'receipt.json')==authored['receipt_sha256']
    protected=[source,author/'receipt.json',author/'profile.json',Path(authored['run_dir'])/'manifest.json',Path(authored['run_dir'])/'source.wav']
    before={str(p.relative_to(ROOT)):sha(p) for p in protected}
    destination=ROOT/'artifacts/experiments/application-mcp-qualification'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination.mkdir(parents=True)
    arguments={'input':str(source),'authoring_dir':str(author),'receipt_sha256':authored['receipt_sha256'],'timeout_seconds':600}
    plan={'schema_version':1,'actor':'/root/tool_hooks','authority':'Root tool28 API/native generated qualification release; R-HOOK-CONVERGENCE-20261004/R-N11/R-N13','source_class':'generated8s_not_operator_take','arguments':arguments,'worker_pins':PINS,'protected_before':before,'client_timeout_seconds':620,'tool_outer_seconds':600,'inner_seconds':590,'actual_recording_processed':False}
    save(destination/'plan.json',plan)
    messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'generated8s-application-proof','version':'1'}}},{'jsonrpc':'2.0','method':'notifications/initialized'},{'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'apply_capture_profile','arguments':arguments}}]
    env=dict(os.environ)
    env['FFMPEG']='/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffmpeg'
    env['FFPROBE']='/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffprobe'
    began=time.monotonic()
    completed=subprocess.run([sys.executable,str(ROOT/'scripts/mcp_server.py')],cwd=ROOT,env=env,input=''.join(json.dumps(x)+'\n' for x in messages),capture_output=True,text=True,timeout=620)
    (destination/'stdio.jsonl').write_text(completed.stdout);(destination/'stderr.txt').write_text(completed.stderr)
    result={'schema_version':1,'status':'pending','elapsed_seconds':time.monotonic()-began,'exit_code':completed.returncode,'stderr_empty':completed.stderr=='','actual_recording_processed':False,'listening_accepted':False,'master_adopted':False,'worker_pins':PINS,'proof_dir':str(destination)}
    try:
        assert completed.returncode==0 and completed.stderr==''
        replies=[json.loads(line) for line in completed.stdout.splitlines()];assert len(replies)==2
        call=replies[1]['result'];assert not call.get('isError'),call
        envelope=call.get('structuredContent') or json.loads(call['content'][0]['text']);summary=envelope['result']
        assert summary['status']=='rendered_unreviewed' and summary['dsp_performed'] is True
        assert summary['listening_accepted'] is False and summary['master_adopted'] is False
        for field,digest_field in (('manifest_path','manifest_sha256'),('receipt_path','receipt_sha256')):assert sha(summary[field])==summary[digest_field]
        after={str(p.relative_to(ROOT)):sha(p) for p in protected};assert after==before
        manifest=json.loads(Path(summary['manifest_path']).read_text());assert {k:manifest['pcm'][k] for k in ('sample_rate','channels','sample_count')}=={'sample_rate':44100,'channels':2,'sample_count':352800}
        supervision=json.loads(Path(summary['supervision']['receipt']['path']).read_text())
        assert supervision['inner_seconds']==590 and supervision['outer_seconds']==600
        assert supervision['descendant_cleanup']=='no_runnable_recorded_members'
        result.update(status='typed_generated_native_passed',summary=summary,protected_after=after,native=manifest['pcm'],supervision_status=supervision['status'])
    except BaseException as exc:
        result.update(status='typed_generated_native_failed',error=str(exc)[:3000])
        save(destination/'result.json',result);print(json.dumps({'status':result['status'],'result_json':str(destination/'result.json'),'error':result['error']}));raise
    save(destination/'result.json',result)
    save(ROOT/'docs/agent-notes/2026-10-06-apply-capture-profile-mcp-result.json',result)
    print(json.dumps({'status':result['status'],'elapsed_seconds':result['elapsed_seconds'],'result_json':str(destination/'result.json'),'run_dir':result['summary']['run_dir']}))
if __name__=='__main__':run()
