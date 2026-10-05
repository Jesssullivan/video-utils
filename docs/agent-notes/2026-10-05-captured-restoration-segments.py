#!/usr/bin/env python3
"""Bounded low-band power/coherence in fixed actual-recording intervals."""
import argparse
import importlib.util
import json
from pathlib import Path

worker=Path(__file__).with_name('2026-10-05-captured-restoration-comparison.py')
spec=importlib.util.spec_from_file_location('restoration_comparison',worker)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
np=module.np
from scipy.signal import coherence,welch

INTERVALS=[(10,20,'active_candidate'),(40,50,'active_candidate'),
           (90,100,'active_candidate'),(130,140,'active_candidate'),
           (4,5,'quiet_candidate'),(149,150,'quiet_candidate')]
BANDS=[(20,45),(45,120)]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    parser.add_argument('--comparison',required=True);args=parser.parse_args()
    evidence=json.loads(Path(args.comparison).read_text()); result={
      'schema_version':1,'worker_sha256':module.sha(Path(__file__)),
      'comparison_worker_sha256':module.sha(worker),
      'comparison_path':args.comparison,'comparison_sha256':module.sha(Path(args.comparison)),
      'source_sha256':evidence['source_sha256'],
      'method':{'sample_rate':44100,'threads':2,'nperseg':16384,'noverlap':8192,
       'window':'hann','detrend':False,'band_power':'sum lower-inclusive upper-exclusive PSD bins * df',
       'coherence':'magnitude-squared coherence; both mean bins and source-PSD-weighted mean'},
      'limitations':['Activity/quiet labels are amplitude/context candidates, not isolated musical/noise references.',
       'High source/output coherence can coexist with attenuation and correlated noise removal; it is not preservation proof.',
       'One-second windows have only four overlapped segments; coherence is descriptive and statistically limited.',
       'Band power includes fan, guitar and other sounds; no specific C1-note identification.'],
      'candidates':[]}
    source_path=Path(evidence['candidates'][0]['artifacts']['source']['path'])
    assert module.sha(source_path)==evidence['decoded_source_wav_sha256']
    rate,source=module.load(source_path);source=source[:,0]
    for candidate in evidence['candidates']:
      artifact=candidate['artifacts']['denoised'];path=Path(artifact['path'])
      assert module.sha(path)==artifact['sha256']
      rr,output=module.load(path);assert rr==rate and len(output)==len(source)
      output=output[:,0];rows=[]
      for start,end,label in INTERVALS:
        a=round(start*rate);b=round(end*rate);x=source[a:b];y=output[a:b]
        controls=dict(fs=rate,nperseg=16384,noverlap=8192,window='hann',detrend=False)
        f,p=welch(x,scaling='density',**controls);_,q=welch(y,scaling='density',**controls)
        _,c=coherence(x,y,**controls);df=float(f[1]-f[0]);bands={}
        for lo,hi in BANDS:
          mask=(f>=lo)&(f<hi);px=float(p[mask].sum()*df);py=float(q[mask].sum()*df)
          bands[f'{lo}-{hi}']={'source_power_dbfs':module.db(px),'denoised_power_dbfs':module.db(py),
             'delta_db':module.db(py)-module.db(px),'bin_count':int(mask.sum()),
             'coherence_mean':float(c[mask].mean()),
             'coherence_source_power_weighted':float(np.sum(c[mask]*p[mask])/np.sum(p[mask]))}
        rows.append({'start_seconds':start,'end_seconds':end,'label':label,
          'sample_frames':len(x),'welch_segment_count':1+(len(x)-16384)//8192,
          'frequency_bin_hz':df,'source_rms_dbfs':module.db(np.mean(x*x)),
          'denoised_rms_dbfs':module.db(np.mean(y*y)),'bands':bands})
      result['candidates'].append({'profile':candidate['profile']['name'],
       'run_id':candidate['run_id'],'denoised_sha256':artifact['sha256'],'intervals':rows})
    dest=Path(args.output)
    with dest.open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
    print(dest)

if __name__=='__main__':main()
