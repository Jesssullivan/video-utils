#!/usr/bin/env python3
"""Read immutable restoration artifacts and emit independent comparison JSON.

Run from repo root with .venv/bin/python. The output is a new evidence file;
source/run artifacts and environment packages are never modified.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

for variable in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "2"
import numpy as np
import scipy
from scipy.io import wavfile
from scipy.signal import welch

BANDS = [(20,45),(28,80),(55,70),(190,225),(80,250),(250,2000),
         (2000,10000),(10000,22050)]
WINDOWS = [(0,1),(4,5),(4.1,4.95),(149,150)]

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def db(value): return float(10*np.log10(max(float(value),1e-300)))

def load(path):
    rate,x=wavfile.read(path)
    if np.issubdtype(x.dtype,np.integer):
        x=x.astype(np.float64)/max(abs(np.iinfo(x.dtype).min),np.iinfo(x.dtype).max)
    else: x=x.astype(np.float64)
    if x.ndim==1: x=x[:,None]
    assert np.isfinite(x).all(),path
    return int(rate),x

def describe(rate,x):
    rms=float(np.sqrt(np.mean(x*x))); peak=float(np.max(np.abs(x)))
    frames=(len(x)//rate)*rate
    one_second=np.mean(x[:frames].reshape(-1,rate,x.shape[1])**2,axis=(1,2))
    f,p=welch(x,fs=rate,nperseg=65536,noverlap=32768,
              window='hann',detrend=False,scaling='density',axis=0)
    density=np.mean(p,axis=1); df=float(f[1]-f[0])
    return {
        'sample_rate':rate,'channels':x.shape[1],'sample_frames':len(x),
        'duration_seconds':len(x)/rate,'rms_dbfs':20*math.log10(max(rms,1e-150)),
        'sample_peak_dbfs':20*math.log10(max(peak,1e-150)),
        'crest_db':20*math.log10(max(peak,1e-150)/max(rms,1e-150)),
        'one_second_rms_dbfs_percentiles':dict(zip(['p10','p50','p90'],
           [float(v) for v in np.percentile(10*np.log10(np.maximum(one_second,1e-300)),[10,50,90])])),
        'band_power_dbfs':{f'{lo}-{hi}':db(np.sum(density[(f>=lo)&(f<hi)])*df)
                            for lo,hi in BANDS},
        'windows':{f'{a:g}-{b:g}':{'rms_dbfs':db(np.mean(x[round(a*rate):round(b*rate)]**2)),
                         'sample_frames':round(b*rate)-round(a*rate)} for a,b in WINDOWS},
    }

def loudness(ffmpeg,path):
    cmd=[ffmpeg,'-hide_banner','-nostdin','-loglevel','info','-threads','2',
         '-filter_threads','2','-filter_complex_threads','2','-i',str(path),
         '-map','0:a:0','-af','loudnorm=I=-18:TP=-1.5:LRA=50:print_format=json',
         '-f','null','-']
    r=subprocess.run(cmd,capture_output=True,text=True,check=True)
    start=r.stderr.rfind('{'); end=r.stderr.rfind('}')
    data=json.loads(r.stderr[start:end+1])
    return {'command':cmd,'integrated_lufs':float(data['input_i']),
            'true_peak_dbtp':float(data['input_tp']),'loudness_range_lu':float(data['input_lra']),
            'threshold_lufs':float(data['input_thresh'])}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    parser.add_argument('--ffmpeg',required=True); args=parser.parse_args()
    receipts=[Path('artifacts/runs/20261005T211103Z-c6d0bac2fcd2/manifest.json'),
              Path('artifacts/root-captured8-render.json'),
              Path('artifacts/root-captured12-render.json'),
              Path('artifacts/root-captured8-clarity-render.json')]
    manifests=[json.loads(p.read_text()) for p in receipts]
    source_path=Path(manifests[0]['source']['path']); source_hash=sha(source_path)
    assert all(m['source']['sha256']==source_hash for m in manifests)
    output={'schema_version':1,'method':{'worker_sha256':sha(Path(__file__)),
      'python':sys.version,'numpy':np.__version__,'scipy':scipy.__version__,
      'threads':2,'welch':{'window':'hann','nperseg':65536,'noverlap':32768,
      'detrend':False,'scaling':'density','band_integration':'sum PSD bins * df; lower inclusive upper exclusive'},
      'window_sample_rounding':'Python round(seconds*sample_rate)',
      'levels':'full-scale-normalized native WAV; dB power relative 1; no level matching before denoise deltas',
      'dynamics':'crest and one-second RMS descriptive only; no musical quality score'},
      'source_sha256':source_hash,'worker_inputs':[], 'candidates':[],
      'limitations':['Selected quiet windows may contain guitar/metronome/room sound; changes are not fan-only SNR.',
       'Whole-take band energy mixes noise and music; no low-note or pick-preservation proof.',
       'Equal frame counts and calibrated bulk delay are not complete acoustic A/V alignment.',
       'No real listening acceptance, automated best tone or performance correctness claim.']}
    source_wav_hash=None; denoise8_hash=None; source_loudness=None
    for receipt,m in zip(receipts,manifests):
        name=m['profile']['name']; root=Path(m['run_dir'])
        output['worker_inputs'].append({'receipt':str(receipt),'sha256':sha(receipt)})
        cand={'profile':m['profile'],'run_id':m['run_id'],'run_dir':str(root),
              'capture':m.get('noise_capture'),'latency':m['dsp_latency'],
              'artifacts':{},'manifest_output_loudness':m['loudness'].get('cleaned',{}).get('output'),
              'normalization_render_type':m['loudness'].get('cleaned',{}).get('render',{}).get('normalization_type')}
        arrays={};rate0=None
        for key,rel in m['outputs'].items():
            path=root/rel; actual=sha(path); expected=m['output_sha256'][rel]
            assert actual==expected,(name,key,'hash mismatch')
            rate,x=load(path);rate0=rate if rate0 is None else rate0
            assert rate==rate0 and x.shape[1]==1,(name,key,rate,x.shape)
            if key=='source':
                assert source_wav_hash is None or source_wav_hash==actual
                source_wav_hash=actual
            arrays[key]=x
            cand['artifacts'][key]={'path':str(path),'sha256':actual,'hash_verified':True,**describe(rate,x)}
        assert len({a.shape for a in arrays.values()})==1,(name,'extent')
        residue_error=arrays['source']-arrays['denoised']-arrays['residue']
        cand['residue_equality']={'equation':'source - denoised - residue',
         'max_abs_full_scale':float(np.max(np.abs(residue_error))),
         'rms_dbfs':db(np.mean(residue_error**2))}
        assert cand['residue_equality']['max_abs_full_scale']<=1e-7,(name,'residue')
        for key in arrays:
            if key in ('source','residue','baseline'):continue
            stats=cand['artifacts'][key];reference=cand['artifacts']['source']
            stats['band_delta_vs_source_db']={band:value-reference['band_power_dbfs'][band]
                                            for band,value in stats['band_power_dbfs'].items()}
            stats['window_delta_vs_source_db']={window:value['rms_dbfs']-reference['windows'][window]['rms_dbfs']
                                             for window,value in stats['windows'].items()}
        if name=='captured8':denoise8_hash=cand['artifacts']['denoised']['sha256']
        if name=='captured8-clarity':
            cand['denoise_matches_captured8']=cand['artifacts']['denoised']['sha256']==denoise8_hash
            assert cand['denoise_matches_captured8']
            cand['residue_matches_captured8']=cand['artifacts']['residue']['sha256']==output['candidates'][1]['artifacts']['residue']['sha256']
            assert cand['residue_matches_captured8']
            gain=np.mean(arrays['processed']**2)/np.mean(arrays['denoised']**2)
            cand['processed_vs_denoised_rms_delta_db']=db(gain)
        if source_loudness is None:source_loudness=loudness(args.ffmpeg,root/m['outputs']['source'])
        cand['measured_master_loudness']=loudness(args.ffmpeg,root/m['outputs']['cleaned'])
        if 'processed' in m['outputs']:
            cand['measured_processed_loudness']=loudness(args.ffmpeg,root/m['outputs']['processed'])
        output['candidates'].append(cand)
        print(name,'verified',flush=True)
    old_master=output['candidates'][0]['artifacts']['cleaned']
    for cand in output['candidates']:
        master=cand['artifacts']['cleaned'];baseline=cand['artifacts']['baseline']
        master['window_delta_vs_conservative3_master_db']={w:stats['rms_dbfs']-old_master['windows'][w]['rms_dbfs']
                                                           for w,stats in master['windows'].items()}
        master['window_delta_vs_matched_baseline_db']={w:stats['rms_dbfs']-baseline['windows'][w]['rms_dbfs']
                                                     for w,stats in master['windows'].items()}
    assert sha(source_path)==source_hash
    output['source_unchanged_after_worker']=True
    output['decoded_source_wav_sha256']=source_wav_hash
    output['measured_source_loudness']=source_loudness
    dest=Path(args.output);dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open('x') as f:json.dump(output,f,indent=2,sort_keys=True);f.write('\n')
    print(dest,flush=True)

if __name__=='__main__':main()
