#!/usr/bin/env python3
"""Bounded saved-WAV comparison of a root-authorized fuller-tone audition."""
from pathlib import Path
import hashlib, importlib.util, json, os, signal, time
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'artifacts/experiments/fuller-v1-20261006T041415Z'
NR8=ROOT/'artifacts/runs/20261006T030345Z-af60acfd29dd'
FULL=ROOT/'artifacts/runs/20261006T041633Z-990aa1bd6737'
PINS={ROOT/'docs/agent-notes/2026-10-06-nr8-nr10-comparison.py':'dbcb63463e3c820510d01aa836b1814a1c4333f598be0f620bf56c783fd11cc3',ROOT/'docs/agent-notes/2026-10-05-captured-restoration-comparison.py':'e62498f5e00325e37da2b7d6463ae813c98ae3ae0a27d5bfafd5c3d47cf5efef',ROOT/'scripts/apply_capture_profile.py':'790ac58f1924db2607087c6ab1cdae5d813ba24eda610af1f396d77e93d06584',WORK/'artifact-readback.json':'3e2a594f09fc27754c448e2e501e12a0e01e1e0c938ebec47a2d5c099b65b54f'}
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def loadmod(p,name):
 spec=importlib.util.spec_from_file_location(name,p); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
 started=time.monotonic();out={'schema_version':1,'status':'incomplete','whole_job_seconds_max':120,'threads':2,'owned_subprocesses':[],'candidates':[],'listening_accepted':False,'master_adopted':False,'fan_only_gain':None,'music_only_gain':None,'protected_after_verified':False,'method':'Exact pinned existing native-WAV Welch/local-panel equations; FULLER versus NR8 tone package, not single-bell attribution. Capture music/fan contamination unknown.'}
 class Budget:
  ends=started+115
  def remaining(self):
   v=self.ends-time.monotonic()
   if v<=0:raise TimeoutError('fuller readback processing deadline')
   return v
  def check(self):self.remaining()
 budget=Budget();prior=signal.getsignal(signal.SIGALRM);assert signal.getitimer(signal.ITIMER_REAL)==(0.,0.)
 def alarm(s,f):raise TimeoutError('fuller readback processing deadline')
 signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,budget.remaining())
 try:
  assert not (WORK/'tone-readback-complete.json').exists()
  for p,h in PINS.items():assert sha(p)==h,(str(p),'pin differs')
  for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS'):os.environ[k]='2'
  comp=loadmod(ROOT/'docs/agent-notes/2026-10-06-nr8-nr10-comparison.py','_fuller_comparison');helper=loadmod(comp.HELPER,'_fuller_helper');owned=loadmod(comp.APPLICATION,'_fuller_owned');owned.CLI_ALARM_HANDLER=alarm
  readback=json.loads((WORK/'artifact-readback.json').read_text());protected=readback['protected_after'];assert all(sha(r['path'])==r['sha256'] for r in protected)
  m8=json.loads((NR8/'manifest.json').read_text());mf=json.loads((FULL/'manifest.json').read_text());exp=json.loads((FULL/'export/outcome.json').read_text());app=json.loads((FULL/'application-receipt.json').read_text())
  assert sha(FULL/'manifest.json')==readback['manifest_sha256'];assert sha(FULL/'application-receipt.json')==readback['application_receipt_sha256'];assert sha(FULL/'export/outcome.json')==readback['export_outcome_sha256']
  assert app['producer']['application_worker_sha256']==comp.APPLICATION_SHA
  assert mf['profile']['peaking_eq']==[{'frequency_hz':160.,'gain_db':2.,'q':.7},{'frequency_hz':300.,'gain_db':1.,'q':.8}]
  assert {k:v for k,v in m8['profile'].items() if k not in {'name','description','peaking_eq'}}=={k:v for k,v in mf['profile'].items() if k not in {'name','description','peaking_eq'}}
  for role in ('source','denoised','residue'):assert sha(FULL/(role+'.wav'))==mf['output_sha256'][role+'.wav']==m8['output_sha256'][role+'.wav']
  rate,x=helper.load(NR8/'processed.wav');assert rate==44100 and x.shape==(6657385,1)
  import csv
  with comp.EVENTS.open(newline='') as f:anchors=comp.attack_panels(list(csv.DictReader(f)))
  out.update({'worker_sha256':sha(Path(__file__)),'pinned_sources':[{ 'path':str(p),'sha256':h} for p,h in PINS.items()],'pure_nr8_denoised_byte_identity':True,'pure_nr8_residue_byte_identity':True,'source_native_origin_seconds':0,'attack_panel_seconds':anchors,'attack_reference':'unvalidated historical NR8 broadband candidates; not confirmed picked notes','protected_before':protected,'worker_pcm_meter':mf['loudness']['cleaned']['output'],'worker_aac_meter':exp['final_audio_loudness'],'fuller_timeline':exp['verification']})
  for label,run,m in [('nr8',NR8,m8),('fuller_nr8',FULL,mf)]:
   row={'label':label,'run_dir':str(run),'artifacts':{}};out['candidates'].append(row)
   for role in ('processed','cleaned'):
    assert sha(run/(role+'.wav'))==m['output_sha256'][role+'.wav'];r,y=helper.load(run/(role+'.wav'));assert r==rate and y.shape==x.shape and helper.np.max(helper.np.abs(y))<1
    a={'sha256':m['output_sha256'][role+'.wav'],**helper.describe(rate,y),'local_panels':[],'attack_tail_windows':comp.short_panels(helper,y,anchors,rate)};row['artifacts'][role]=a
    for lo,hi in comp.INTERVALS:a['local_panels'].append(comp.local_stats(helper,x,y,rate,lo,hi));budget.check()
  aa,bb=out['candidates'];out['fuller_minus_nr8_same_stage']={role:{'rms_db':bb['artifacts'][role]['rms_dbfs']-aa['artifacts'][role]['rms_dbfs'],'whole_band_db':{k:bb['artifacts'][role]['band_power_dbfs'][k]-v for k,v in aa['artifacts'][role]['band_power_dbfs'].items()},'local_band_db':[{'seconds':q['seconds'],'bands':{k:q['bands'][k]['output_power_dbfs']-p['bands'][k]['output_power_dbfs'] for k in p['bands']}} for p,q in zip(aa['artifacts'][role]['local_panels'],bb['artifacts'][role]['local_panels'])]} for role in ('processed','cleaned')}
  out['independent_fuller_aac_meter']=comp.meter(owned,Path(exp['commands'][0][0]),FULL/'export/cleaned-video.mov',budget,out['owned_subprocesses']);out['delivery']=comp.delivery(out['independent_fuller_aac_meter'],True)
  assert all(sha(r['path'])==r['sha256'] for r in protected);assert all(sha(p)==h for p,h in PINS.items());assert sha(FULL/'manifest.json')==readback['manifest_sha256'];assert sha(FULL/'export/outcome.json')==readback['export_outcome_sha256']
  out['protected_after_verified']=True;out['status']='complete_fuller_comparison_unreviewed'
 except Exception as exc:out['error']={'type':type(exc).__name__,'message':str(exc)}
 finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,prior)
 out['elapsed_wall_seconds']=time.monotonic()-started
 with (WORK/'tone-readback-complete.json').open('x') as f:json.dump(out,f,indent=2,allow_nan=False);f.write('\n')
 print(json.dumps({'status':out['status'],'elapsed_wall_seconds':out['elapsed_wall_seconds'],'path':str(WORK/'tone-readback-complete.json'),'sha256':sha(WORK/'tone-readback-complete.json')}))
 return 0 if out['status']=='complete_fuller_comparison_unreviewed' else 1
if __name__=='__main__':raise SystemExit(main())
