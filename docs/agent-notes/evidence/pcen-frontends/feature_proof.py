import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS'):os.environ[k]='2'
import argparse,hashlib,json,math,time
from pathlib import Path
import numpy as np
import librosa
from scipy.io import wavfile
from scipy.signal import resample_poly

SETTINGS=[('power-default',2,2**31,.98,.4),('magnitude-default',1,2**31,.98,.4),('magnitude-unit-gain05',1,1,.5,.4),('magnitude-unit-gain05-slow',1,1,.5,1.)]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def cosine(a,b):
 denominator=np.linalg.norm(a)*np.linalg.norm(b)
 return float(a@b/denominator) if denominator>0 else None
def frontend(y,nfft):
 result={};nframes=None
 for kind in (1,2):
  mel=librosa.feature.melspectrogram(y=y,sr=16000,n_fft=nfft,hop_length=80,n_mels=128,fmin=20,fmax=8000,power=kind,center=True)
  nframes=mel.shape[1]
  log=(librosa.amplitude_to_db if kind==1 else librosa.power_to_db)(mel,ref=np.max)
  result['magnitude-log' if kind==1 else 'power-log']=librosa.onset.onset_strength(S=log,sr=16000,hop_length=80,lag=1,max_size=1)
  for name,representation,scale,gain,tc in SETTINGS:
   if representation!=kind:continue
   kwargs={'sr':16000,'hop_length':80,'gain':gain,'time_constant':tc,'bias':2,'power':.5,'eps':1e-6,'max_size':1}
   conditioned=mel.astype(np.float64)*scale
   smoothing=(math.sqrt(1+4*(tc*200)**2)-1)/(2*(tc*200)**2)
   initial=(1-smoothing)*conditioned[:,:1]
   full=librosa.pcen(conditioned,zi=initial,**kwargs)
   blocks=[];state=initial.copy()
   for begin in range(0,nframes,37):
    block,state=librosa.pcen(conditioned[:,begin:begin+37],zi=state,return_zf=True,**kwargs)
    blocks.append(block)
   difference=float(abs(full-np.concatenate(blocks,axis=-1)).max())
   assert np.isfinite(full).all() and difference<1e-9
   result[name]={'flux':librosa.onset.onset_strength(S=full,sr=16000,hop_length=80,lag=1,max_size=1),'block_batch_max_absolute_difference':difference,'minimum':float(full.min()),'maximum':float(full.max())}
 return result,nframes

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--inputs',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 assert not args.output.exists()
 selected=json.loads(args.inputs.read_text());assert len(selected['pairs'])==3
 started=time.monotonic();records=[];inputs=[]
 for number,pair in enumerate(selected['pairs']):
  decoded=[]
  for condition in ('clean','mix'):
   path=Path(pair[condition]['path']);before=sha(path);assert before==pair[condition]['sha256']
   rate,audio=wavfile.read(path);assert rate==48000 and audio.ndim==1 and audio.dtype==np.int16
   cropped=audio[:4*rate];assert len(cropped)==4*rate
   y=resample_poly(cropped.astype(np.float64)/32768,1,3)
   decoded.append(y.astype(np.float32));inputs.append({'pair_index':number,'condition':condition,'path':str(path),'sha256':before,'native_excerpt_samples':[0,192000],'excerpt_pcm16_sha256':hashlib.sha256(cropped.astype('<i2').tobytes()).hexdigest()})
  for nfft in (1024,4096):
   a,frames=frontend(decoded[0],nfft);b,bframes=frontend(decoded[1],nfft);assert frames==bframes
   rows=[]
   for name in ('power-log','magnitude-log',*(x[0] for x in SETTINGS)):
    af=a[name]['flux'] if isinstance(a[name],dict) else a[name]
    bf=b[name]['flux'] if isinstance(b[name],dict) else b[name]
    row={'policy':name,'whole_excerpt_flux_cosine':cosine(af,bf),'after_one_second_flux_cosine':cosine(af[200:],bf[200:])}
    if not name.endswith('-log'):
     row['pcen_checks']={condition:{key:value for key,value in front[name].items() if key!='flux'} for condition,front in (('clean',a),('mix',b))}
    rows.append(row)
   records.append({'pair_index':number,'fft_samples':nfft,'window_ms':nfft/16,'fft_bin_spacing_hz':16000/nfft,'C1_cycles_per_window':32.703195663*nfft/16000,'frame_count':frames,'centered_frame_time_extent_seconds':[0,(frames-1)*80/16000],'complete_support_center_seconds':[nfft/32000,4-nfft/32000],'low_band_centers_hz':[float(hz) for hz in librosa.mel_frequencies(n_mels=130,fmin=20,fmax=8000)[1:-1] if hz<=90],'metric_padding_scope':'Both cosine metrics retain centered padding at final excerpt edge; whole metric also retains initial edge.','rows':rows})
 for item in inputs:assert sha(Path(item['path']))==item['sha256']
 settings=[{'id':name,'spectral_exponent':kind,'scale':scale,'gain':gain,'time_constant_seconds':tc,'smoothing_coefficient':(math.sqrt(1+4*(tc*200)**2)-1)/(2*(tc*200)**2)} for name,kind,scale,gain,tc in SETTINGS]
 receipt={'schema_version':1,'kind':'preregistered_feature_only_holdout_probe','input_selection_sha256':sha(args.inputs),'plan_sha256':selected['plan_sha256'],'admitted_index_sha256':selected['admitted_index_sha256'],'inputs':inputs,'settings':settings,'common':{'sr':16000,'hop_samples':80,'n_mels':128,'fmin':20,'fmax':8000,'center':True,'window':'periodic Hann','filter_bank':'librosa Slaney area norm','bias':2,'compression_power':.5,'epsilon':1e-6,'startup':'explicit zi=(1-b)*conditioned_first_frame; M0=E0','warmup_seconds':1,'max_size':1},'results':records,'versions':{'librosa':librosa.__version__,'numpy':np.__version__},'numeric_threads':2,'elapsed_seconds':time.monotonic()-started,'worker_sha256':sha(Path(__file__)),'labels_used':False,'input_hashes_unchanged':True,'scope':'24 aggregate cropped audio-seconds; generated feature invariance only; no onset or phrase grading; no production changes'}
 assert receipt['elapsed_seconds']<90
 args.output.write_text(json.dumps(receipt,indent=2,allow_nan=False));print(json.dumps({'elapsed_seconds':receipt['elapsed_seconds'],'result_count':len(records)}))
if __name__=='__main__':main()
