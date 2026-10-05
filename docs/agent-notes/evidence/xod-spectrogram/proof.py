import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS'):os.environ[k]='2'
import json,hashlib,subprocess,time
from pathlib import Path
import numpy as np
import librosa
from scipy.signal import resample_poly
from scipy.io import wavfile
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
XOD=BASE.parent/'xoxd-spectrogram'
started=time.monotonic()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
cfg={'sampleRate':16000,'frameLength':400,'nFft':512,'hop':160,'nMels':40,'fmin':20,'fmax':7600,'floor':1e-10}
params={'timeConstant':.4,'gain':.98,'bias':2,'power':.5,'eps':1e-6,'inputScale':2**31}
def xmel(y):
 edges=700*(10**(np.linspace(2595*np.log10(1+20/700),2595*np.log10(1+7600/700),42)/2595)-1)
 hz=np.arange(257)*16000/512
 weights=np.maximum(0,np.minimum((hz[None,:]-edges[:-2,None])/(edges[1:-1,None]-edges[:-2,None]),(edges[2:,None]-hz[None,:])/(edges[2:,None]-edges[1:-1,None])))
 weights/=weights.sum(axis=1,keepdims=True)
 frames=np.lib.stride_tricks.sliding_window_view(y,400)[::160]
 window=.5-.5*np.cos(2*np.pi*np.arange(400)/400)
 power=abs(np.fft.rfft(frames*window,n=512))**2/window.sum()**2
 return (power@weights.T),edges
def read(p):
 rate,y=wavfile.read(p)
 assert y.ndim==1 and y.dtype==np.int16
 return resample_poly(y.astype(np.float64)/32768,16000,rate)
inputs=[];case_payload=[];features={}
reference=XOD/'test/fixtures/reference-16000.wav'
y=read(reference);rows,edges=xmel(y)
gold=json.loads((XOD/'test/fixtures/ruby/logmel-reference16k.json').read_text())['spectrogram']
goldmel=np.array(gold['values']).T
mel_delta=float(abs(10*np.log10(np.maximum(rows,1e-10))-goldmel).max())
case_payload.append({'id':'ruby-golden','rows':rows.tolist(),'cfg':cfg,'params':params})
bank=ROOT/'artifacts/benchmarks/root-calibration-bank-20261005T2255'
for case in ('low32-sustain','palm-muted-recurrence','legato-recurrence'):
 for kind in ('clean','mix'):
  p=bank/case/(kind+'.wav');y=read(p);id=case+'/'+kind
  m=librosa.feature.melspectrogram(y=y.astype(np.float32),sr=16000,n_fft=1024,hop_length=80,n_mels=128,fmin=27.5)
  log=librosa.power_to_db(m,ref=np.max)
  features[id]={'log_flux':librosa.onset.onset_strength(S=log,sr=16000,hop_length=80,lag=1,max_size=1),'signal':y}
  case_payload.append({'id':id+'/paired-current-power','rows':m.T.tolist(),'cfg':{**cfg,'hop':80},'params':params})
  rows,_=xmel(y);case_payload.append({'id':id+'/xoxd-default','rows':rows.tolist(),'cfg':cfg,'params':params})
  inputs.append({'id':id,'path':str(p.relative_to(ROOT)),'sha256':sha(p),'seconds':len(y)/16000})
source=ROOT/'artifacts/runs/20261005T211103Z-c6d0bac2fcd2/source.wav'
if not source.exists():source=ROOT/'artifacts/runs/20261005T211103Z-c6d0bac2fcd2/original.wav'
assert source.exists(), source
ffmpeg='/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffmpeg'
raw=subprocess.run([ffmpeg,'-v','error','-nostdin','-threads','1','-i',str(source),'-t','12','-ac','1','-ar','16000','-f','f32le','pipe:1'],capture_output=True,timeout=40,check=True).stdout
y=np.frombuffer(raw,dtype='<f4').astype(np.float64);assert len(y)<=192000
m=librosa.feature.melspectrogram(y=y.astype(np.float32),sr=16000,n_fft=1024,hop_length=80,n_mels=128,fmin=27.5)
log=librosa.power_to_db(m,ref=np.max)
features['actual-opening']={'log_flux':librosa.onset.onset_strength(S=log,sr=16000,hop_length=80,lag=1,max_size=1),'signal':y}
case_payload.append({'id':'actual-opening/paired-current-power','rows':m.T.tolist(),'cfg':{**cfg,'hop':80},'params':params})
rows,_=xmel(y);case_payload.append({'id':'actual-opening/xoxd-default','rows':rows.tolist(),'cfg':cfg,'params':params})
inputs.append({'id':'actual-opening','path':str(source.relative_to(ROOT)),'sha256':sha(source),'decoded_excerpt_f32le_sha256':hashlib.sha256(raw).hexdigest(),'excerpt_seconds':[0,12]})
for id,f in features.items():
 m=librosa.feature.melspectrogram(y=f['signal'].astype(np.float32),sr=16000,n_fft=1024,hop_length=80,n_mels=128,fmin=27.5,power=1)
 f['magnitude_log_flux']=librosa.onset.onset_strength(S=librosa.amplitude_to_db(m,ref=np.max),sr=16000,hop_length=80,lag=1,max_size=1)
 case_payload.append({'id':id+'/doc-magnitude','rows':m.T.tolist(),'cfg':{**cfg,'hop':80},'params':params})
(BASE/'input.json').write_text(json.dumps({'cases':case_payload}))
subprocess.run(['bun',str(BASE/'pcen.ts'),str(BASE/'input.json'),str(BASE/'output.json')],check=True,timeout=45)
out=json.loads((BASE/'output.json').read_text());results={x['id']:x for x in out['results']}
goldpcen=np.array(json.loads((XOD/'test/fixtures/ruby/pcen-reference16k.json').read_text())['sets'][0]['pcen'])
pcen_delta=float(abs(np.array(results['ruby-golden']['rows'])-goldpcen).max())
def events(env,hop):
 return librosa.frames_to_time(librosa.onset.onset_detect(onset_envelope=env,sr=16000,hop_length=hop,units='frames'),sr=16000,hop_length=hop).tolist()
actual={};synthetic={};similarity=[]
for id,f in features.items():
 p=np.array(results[id+'/paired-current-power']['rows']).T
 env=librosa.onset.onset_strength(S=p,sr=16000,hop_length=80,lag=1,max_size=1)
 f['pcen_flux']=env
 magnitude=np.array(results[id+'/doc-magnitude']['rows']).T
 menv=librosa.onset.onset_strength(S=magnitude,sr=16000,hop_length=80,lag=1,max_size=1)
 f['magnitude_pcen_flux']=menv
 x=np.array(results[id+'/xoxd-default']['rows']).T
 xenv=librosa.onset.onset_strength(S=x,sr=16000,hop_length=160,lag=1,max_size=1)
 item={'log_flux_event_candidates_seconds':events(f['log_flux'],80),'paired_power_pcen_event_candidates_seconds':events(env,80),'doc_magnitude_pcen_event_candidates_seconds':events(menv,80),'xoxd_default_pcen_frame_relative_candidates_seconds':events(xenv,160),'paired_flux_correlation':float(np.corrcoef(f['log_flux'],env)[0,1])}
 if id=='actual-opening':actual=item
 else:synthetic[id]=item
for case in ('low32-sustain','palm-muted-recurrence','legato-recurrence'):
 a,b=features[case+'/clean'],features[case+'/mix']
 similarity.append({'case':case,'clean_mix_flux_cosine':{k:float(np.dot(a[k],b[k])/(np.linalg.norm(a[k])*np.linalg.norm(b[k]))) for k in ('log_flux','pcen_flux','magnitude_log_flux','magnitude_pcen_flux')}})
receipt={'schema_version':1,'kind':'bounded_feature_compatibility_not_restoration_or_accuracy_acceptance','source_repo':'xoxd-ai/xoxd-spectrogram','source_revision':'8264a38651c785aa0dd9c02e3569b2d979747d80','runtime':{'bun':out['runtime'],'librosa':librosa.__version__,'numpy':np.__version__},'inputs':inputs,'bank_index_sha256':sha(bank/'fixtures.json'),'workers':{'numeric_threads':2,'max_actual_seconds':12},'golden':{'ruby_logmel_max_absolute_db_difference':mel_delta,'ruby_pcen_max_absolute_difference':pcen_delta,'stream_batch_max_absolute_difference':max(x['streaming_batch_max_absolute_difference'] for x in results.values())},'parameters':{'xoxd_default':cfg,'pcen':params,'paired_current_input':'librosa power mel float [-1,1] audio, inputScale 2**31, 128 Slaney bands, fmin27.5, centered1024 FFT, 80hop@16k'},'synthetic_features':synthetic,'synthetic_mixture_similarity':similarity,'actual_unlabelled_features':actual,'scope':['Exact imported TypeScript PCEN core was run; NumPy reconstructed xoxd STFT/mel matched committed Ruby golden.','Paired-current-power isolates compression choice but input scaling must be separately calibrated; no automatic adoption.','xoxd default event timestamps are frame-relative start convention in this prototype, plus12.5ms center; do not import as source markers.','No labelled onset scoring, phrase discovery, restoration, guitar note or market accuracy qualification.'],'elapsed_seconds':time.monotonic()-started,'worker_sha256':{'proof.py':sha(Path(__file__)),'pcen.ts':sha(BASE/'pcen.ts')},'input_hashes_unchanged':all(sha(ROOT/i['path'])==i['sha256'] for i in inputs)}
assert mel_delta<1e-7 and pcen_delta<1e-8 and receipt['input_hashes_unchanged']
(BASE/'receipt.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps({'golden':receipt['golden'],'similarity':similarity,'actual_counts':{k:len(v) for k,v in actual.items() if isinstance(v,list)},'seconds':receipt['elapsed_seconds']}))
