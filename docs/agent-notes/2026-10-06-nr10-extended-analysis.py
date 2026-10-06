#!/usr/bin/env python3
"""Root-released no-latest NR10 analysis with one shared 900-second budget."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'artifacts/runs/20261006T034521Z-a0def0c43eac'
OUT=ROOT/'artifacts/experiments/nr10-extended-analysis-20261006T0400'
ARGS=['--existing-run',str(RUN),'--features','extended','--backend','librosa',
      '--analysis-python',str(ROOT/'.venv/bin/python'),'--pitch-seconds','20','--bpm','178','--no-latest']
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()
def write(path,value):
    with Path(path).open('x') as f:f.write(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n')
def verify(rows):
    for file,expected in rows.items():
        if sha(file)!=expected:raise ValueError('Protected input changed: '+file)

def main():
    if signal.getitimer(signal.ITIMER_REAL)!=(0.,0.):raise ValueError('Another timer is active')
    source=ROOT/'scripts/run_demo.py'
    if sha(source)!='3c03bd68b9bdb77f13e3721db44430aff51c1315e8cfaa09b68a0baea278f23c':raise ValueError('Selected demo workflow source changed')
    release=json.loads((ROOT/'docs/agent-notes/2026-10-06-root-actual-nr10-resource-retry-release.json').read_text())
    protected=dict(release['protected_sha256'])
    for name in ('manifest.json','restoration-manifest.json','application-receipt.json','source.wav','denoised.wav','residue.wav','processed.wav','cleaned.wav','export/outcome.json','export/cleaned-video.mov'):
        p=RUN/name;protected[str(p)]=sha(p)
    verify(protected)
    workers={str(ROOT/'scripts'/s):sha(ROOT/'scripts'/s) for s in ('run_demo.py','rhythm.py','guitar_features.py','clicks.py','pitch.py','meter.py','tonal.py','phrase_compare.py','dag.py','markers.py','report.py')}
    for name in ('program/instrument.json','program/models.json'):workers[str(ROOT/name)]=sha(ROOT/name)
    if OUT.exists() or any(p.is_symlink() for p in (OUT,*OUT.parents)):raise ValueError('Fresh regular output required')
    OUT.mkdir(parents=True,exist_ok=False)
    if os.getsid(0)!=os.getpid():os.setsid()
    state={'schema_version':1,'actor':'/root/media_latency','created_utc':datetime.now(timezone.utc).isoformat(),
      'authority':'Root explicit fresh NR10 extended/no-latest analysis; R-HOOK-CONVERGENCE-20261004/R-N11/R-N13',
      'status':'running','command':[sys.executable,str(source),*ARGS],'controller_sha256':sha(__file__),
      'controller_pid':os.getpid(),'controller_pgid':os.getpgrp(),'controller_sid':os.getsid(0),
      'timeout_seconds':900,'threads':2,'protected_sha256':protected,'worker_sha256':workers,
      'input_restoration_manifest_sha256':sha(RUN/'restoration-manifest.json'),
      'operator_bpm_prior':178,'expected_score_supplied':False,'latest_promotion':False,
      'listening_accepted':False,'master_adopted':False}
    write(OUT/'start.json',state)
    binary='/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/'
    os.environ.update(FFMPEG=binary+'ffmpeg',FFPROBE=binary+'ffprobe')
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS'):os.environ[name]='2'
    spec=importlib.util.spec_from_file_location('bounded_nr10_demo',source);demo=importlib.util.module_from_spec(spec);spec.loader.exec_module(demo)
    started=time.monotonic();ends=started+900;original=demo.invoke;limits=[]
    def bounded_invoke(script,arguments,timeout=1200,interpreter=None,execution=None):
        remaining=ends-time.monotonic()-5
        if remaining<=.1:raise demo.StageError('Shared analysis900s budget exhausted before stage')
        allocated=min(float(timeout),remaining);limits.append({'worker':script,'allocated_seconds':allocated,'remaining_whole_job_seconds':remaining+5})
        return original(script,arguments,allocated,interpreter,execution)
    demo.invoke=bounded_invoke
    old=signal.getsignal(signal.SIGALRM)
    def expired(signum,frame):raise demo.StageError('Shared analysis900s absolute deadline exceeded')
    signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,900)
    code=1;issue=None
    try:
        code=demo.main(ARGS)
        verify(protected);verify(workers)
        if time.monotonic()>=ends:raise ValueError('Shared analysis deadline exceeded')
    except BaseException as exc:issue=str(exc)[:2000]
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
    state.update(status='analysis_completed_unreviewed' if code==0 and issue is None else 'analysis_failed_preserving_media',
      elapsed_seconds=time.monotonic()-started,workflow_exit_code=code,error=issue,stage_allocations=limits,
      protected_unchanged=None,workers_unchanged=None)
    try:verify(protected);state['protected_unchanged']=True
    except (OSError,ValueError):pass
    try:verify(workers);state['workers_unchanged']=True
    except (OSError,ValueError):pass
    if (RUN/'demo.json').is_file():state['demo_receipt']={'path':str(RUN/'demo.json'),'sha256':sha(RUN/'demo.json')}
    write(OUT/'receipt.json',state)
    print(json.dumps({'status':state['status'],'receipt':str(OUT/'receipt.json'),'sha256':sha(OUT/'receipt.json'),'error':issue}),flush=True)
    return 0 if state['status']=='analysis_completed_unreviewed' else 1

if __name__=='__main__':raise SystemExit(main())
