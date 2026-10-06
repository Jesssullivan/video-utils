#!/usr/bin/env python3
"""Execute the exact root-released NR10 resource retry once; retain CLI error JSON."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
RELEASE = ROOT/'docs/agent-notes/2026-10-06-root-actual-nr10-resource-retry-release.json'
RELEASE_SHA = '24ba4717093779c7afbb7d8ade6cba493353ed6d93a0b447f48f3336023392f9'
OUT = ROOT/'artifacts/experiments/actual-nr10-resource-retry-20261006T0345'
MAX_LOG = 4*1024*1024

def now(): return datetime.now(timezone.utc).isoformat()
def require(condition, message):
    if not condition: raise ValueError(message)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
    return h.hexdigest()
def write(path, value):
    raw=json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n'
    require(len(raw.encode())<=1024*1024,'Receipt exceeds bound')
    with Path(path).open('x') as f:f.write(raw)
def verify(expected):
    for file,digest in expected.items():require(sha(file)==digest,'Protected identity changed: '+file)

def main():
    require(sha(RELEASE)==RELEASE_SHA,'Exact root release changed')
    r=json.loads(RELEASE.read_text());require(r['action']=='render_single_source_bound_actual_nr10_after_resource_repair','Release action differs')
    worker={str(ROOT/'scripts/apply_capture_profile.py'):r['application_sha256'],str(ROOT/'scripts/capture_profile.py'):r['author_sha256'],str(ROOT/'scripts/media.py'):r['media_sha256']}
    verify(worker);protected=dict(r['protected_sha256'])
    for c in r['candidates']:
        require(c['label']=='NR10' and c['attempts']==1 and c['timeout_seconds']==600,'Candidate execution bounds differ')
        d=Path(c['authoring_dir']);protected[str(d/'profile.json')]=c['profile_sha256'];protected[str(d/'receipt.json')]=c['authoring_receipt_sha256']
        for file in sorted(d.iterdir()):
            require(not file.is_symlink(),'Symlink authoring input');
            if file.is_file():protected[str(file)]=sha(file)
    require([c['label'] for c in r['candidates']]==['NR10'],'Exact single NR10 required')
    for file in ('program/instrument.json','profiles/bypass.json','scripts/tool_api.py'):
        protected[str(ROOT/file)]=sha(ROOT/file)
    verify(protected);require(not OUT.exists() and not any(p.is_symlink() for p in (OUT,*OUT.parents)),'Fresh regular output required')
    OUT.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('matched_pair_owned_cleanup',ROOT/'scripts/apply_capture_profile.py');app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
    env=dict(os.environ)
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS'):env[name]='2'
    binary='/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/'
    env.update(FFMPEG=binary+'ffmpeg',FFPROBE=binary+'ffprobe')
    events=[];results=[];ends=time.monotonic()+665
    state={'schema_version':1,'actor':'/root/media_latency','created_utc':now(),'root_release_sha256':RELEASE_SHA,'controller_sha256':sha(__file__),'worker_sha256':worker,'protected_sha256':protected,'attempts_per_candidate':1,'threads':2,'overall_budget_seconds':665,'listening_accepted':False,'master_adopted':False,'latest_promoted':False}
    write(OUT/'start.json',state)
    try:
        for c in r['candidates']:
            verify(protected);verify(worker)
            label=c['label'];command=[sys.executable,str(ROOT/'scripts/apply_capture_profile.py'),c['input'],'--authoring-dir',c['authoring_dir'],'--receipt-sha256',c['authoring_receipt_sha256'],'--timeout-seconds','600']
            started=time.monotonic();stage_end=min(ends-5,started+610)
            stdout_path=OUT/(label+'-stdout.json');stderr_path=OUT/(label+'-stderr.log')
            with stdout_path.open('xb') as stdout,stderr_path.open('xb') as stderr:
                process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,env=env,start_new_session=True,close_fds=True)
                write(OUT/(label+'-start.json'),{'actor':'/root/media_latency','created_utc':now(),'label':label,'pid':process.pid,'session_id':process.pid,'pgid':process.pid,'ruling':'R-N11/R-N13','command':command,'ownership':'Exact process launched by this controller; live session/group checked before any cleanup signals','timeout_seconds':600,'outer_stage_seconds':610})
                reason='stage_finished'
                try:
                    if process.poll() is None:require(os.getpgid(process.pid)==process.pid and os.getsid(process.pid)==process.pid,'Child session ownership differs')
                    while process.poll() is None:
                        if time.monotonic()>=stage_end:reason='stage_deadline_exceeded';raise RuntimeError('Bounded CLI deadline exceeded')
                        if any(os.fstat(f.fileno()).st_size>MAX_LOG for f in (stdout,stderr)):reason='stage_log_limit_exceeded';raise RuntimeError('Bounded CLI output exceeded')
                        time.sleep(.025)
                except BaseException:
                    if reason=='stage_finished':reason='stage_interrupted'
                    raise
                finally:app.cleanup_owned_group(process,process.pid,reason,events)
            require(stdout_path.stat().st_size<=MAX_LOG and stderr_path.stat().st_size<=MAX_LOG,'Terminal output exceeds bound')
            result=json.loads(stdout_path.read_text());row={'label':label,'exit_code':process.returncode,'elapsed_seconds':time.monotonic()-started,'stdout_sha256':sha(stdout_path),'stderr_sha256':sha(stderr_path),'result':result};write(OUT/(label+'-summary.json'),row);results.append(row)
            # Error JSON is retained verbatim even when the CLI reports an unknown
            # or committed publication outcome. Never infer candidate absence.
            require(process.returncode==0 and result['status']=='rendered_unreviewed','Application returned a retained failed outcome; no retry')
            require(result['listening_accepted'] is False and result['master_adopted'] is False,'Acceptance promoted')
            run=Path(result['run_dir']);manifest=json.loads((run/'manifest.json').read_text());outcome=json.loads(Path(result['export']['outcome_path']).read_text())
            require(manifest['pcm']['sample_rate']==44100 and manifest['pcm']['channels']==1 and manifest['pcm']['sample_count']==6657385,'Native facts differ')
            require(sha(run/'manifest.json')==result['manifest_sha256'] and sha(result['receipt_path'])==result['receipt_sha256'] and sha(result['export']['outcome_path'])==result['export']['outcome_sha256'],'Returned receipt identity differs')
            row['native']=manifest['pcm'];row['timeline']=manifest['timeline'];row['export_verification']=outcome['verification'];row['final_audio_loudness']=outcome['final_audio_loudness'];row['aac_headroom']=outcome['aac_headroom']
            write(OUT/(label+'-verified-summary.json'),row);verify(protected);verify(worker);require(sha(RELEASE)==RELEASE_SHA,'Root release changed')
            print(json.dumps({'label':label,'status':result['status'],'run_dir':result['run_dir'],'manifest_sha256':result['manifest_sha256'],'receipt_sha256':result['receipt_sha256'],'elapsed_seconds':row['elapsed_seconds']}),flush=True)
        require(time.monotonic()<ends,'Overall budget exceeded');verify(protected);verify(worker)
        state.update(status='single_actual_nr10_resource_retry_rendered_unreviewed',protected_unchanged=True,results=results,owned_process_events=events)
        write(OUT/'receipt.json',state);print(json.dumps({'status':state['status'],'receipt':str(OUT/'receipt.json'),'sha256':sha(OUT/'receipt.json')}),flush=True);return 0
    except BaseException as exc:
        state.update(status='single_nr10_resource_retry_failed_no_adoption',error=str(exc)[:2000],results=results,owned_process_events=events,candidate_absence_asserted=False,protected_unchanged=None)
        try:verify(protected);state['protected_unchanged']=True
        except (OSError,ValueError):pass
        write(OUT/'failure.json',state);print(json.dumps({'status':state['status'],'failure':str(OUT/'failure.json'),'error':str(exc)[:2000]}),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
