from pathlib import Path
import hashlib, json, math
import numpy as np
from scipy.io import wavfile
from scipy.signal import welch

ROOT=Path('/Users/jess/git/video-utils')
paths={
 'bypass':ROOT/'artifacts/runs/20261005T224706Z-2a72efe386ab',
 'conservative3':ROOT/'artifacts/runs/20261005T211103Z-c6d0bac2fcd2',
 'mild6':ROOT/'artifacts/runs/20261005T224733Z-0e920a701cf8',
}
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pcm(p):
 rate,a=wavfile.read(p)
 if np.issubdtype(a.dtype,np.integer): a=a.astype(np.float64)/float(2**(np.iinfo(a.dtype).bits-1))
 else:a=a.astype(np.float64)
 if a.ndim!=1 or not np.isfinite(a).all():raise ValueError('Expected finite mono PCM')
 return rate,a
def rms(a):return float(np.sqrt(np.mean(a*a)))
def db(a,b):return None if not a or not b else 20*math.log10(a/b)
bands=((20,45),(45,120),(120,500),(500,2000),(2000,8000),(8000,20000))
output={'schema_version':1,'kind':'actual_source_bound_profile_comparison','worker_sha256':sha(Path(__file__)),
 'method':{'spectral':'SciPy Welch density, Hann65536, overlap32768, mean, complete native mono take; integrated selected FFT-bin power ratios before presentation normalization',
 'band_intervals_hz':[list(b) for b in bands],'quiet_candidate_intervals_seconds':[[4,5],[149,150]],
 'qualifications':['Bands are mixture-energy measurements, not identified guitar fundamentals or SNR.',
 'Candidate quiet intervals are not confirmed noise-only.', 'No fitted time shift/gain or acoustic alignment assertion.',
 'Normalized candidates match integrated loudness within0.01LU; local dynamic gain may differ.',
 'No listening acceptance or best-profile selection.']},'profiles':[]}
source_sha=None
for label,root in paths.items():
 manifest_path=root/'manifest.json'; m=json.loads(manifest_path.read_text())
 input_file=Path(m['source']['path'])
 assert sha(input_file)==m['source']['sha256']
 if source_sha is None:source_sha=m['source']['sha256']
 assert m['source']['sha256']==source_sha
 for name,h in m['output_sha256'].items():assert sha(root/name)==h
 rate,source=pcm(root/'source.wav'); rate2,processed=pcm(root/'denoised.wav')
 assert rate==rate2==44100 and len(source)==len(processed)==6657385
 freq,power=welch(source,fs=rate,window='hann',nperseg=65536,noverlap=32768,scaling='density',average='mean')
 freq2,power2=welch(processed,fs=rate,window='hann',nperseg=65536,noverlap=32768,scaling='density',average='mean')
 assert np.array_equal(freq,freq2)
 ratios=[]
 for low,high in bands:
  selected=(freq>=low)&(freq<high)
  p=float(np.sum(power[selected]));q=float(np.sum(power2[selected]))
  ratios.append({'range_hz':[low,high],'power_change_db':None if not p or not q else 10*math.log10(q/p)})
 quiet=[]
 for start,end in ((4,5),(149,150)):
  old=rms(source[round(start*rate):round(end*rate)]);new=rms(processed[round(start*rate):round(end*rate)])
  quiet.append({'interval_seconds':[start,end],'input_rms':old,'denoised_rms':new,'change_db':db(new,old),'noise_only_confirmed':False})
 l=m['loudness']['cleaned']['output']
 row={'profile':label,'run_dir':str(root),'manifest_sha256':sha(manifest_path),'source_sha256':source_sha,
      'output_hashes':m['output_sha256'],'sample_rate':rate,'sample_count':len(source),'channels':1,
      'measured_master_integrated_lufs':float(l['input_i']),'measured_master_true_peak_dbtp':float(l['input_tp']),
      'pre_normalization_whole_take_rms_change_db':db(rms(processed),rms(source)),
      'pre_normalization_band_energy_changes':ratios,'quiet_candidates':quiet,'source_unchanged':True}
 if label=='bypass':
  row['source_denoised_hashes_identical']=m['output_sha256']['source.wav']==m['output_sha256']['denoised.wav']
  row['baseline_cleaned_hashes_identical']=m['output_sha256']['baseline.wav']==m['output_sha256']['cleaned.wav']
  assert row['source_denoised_hashes_identical'] and row['baseline_cleaned_hashes_identical']
 output['profiles'].append(row)
 for name,h in m['output_sha256'].items():assert sha(root/name)==h
 assert sha(input_file)==source_sha
output['source_sha256']=source_sha
assert max(x['measured_master_integrated_lufs'] for x in output['profiles'])-min(x['measured_master_integrated_lufs'] for x in output['profiles'])<=0.011
destination=ROOT/'artifacts/actual-restoration-comparison.json'
destination.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
print(json.dumps({'output':str(destination),'sha256':sha(destination),'profiles':[{'profile':x['profile'],'lufs':x['measured_master_integrated_lufs'],'true_peak':x['measured_master_true_peak_dbtp'],'low_band':x['pre_normalization_band_energy_changes'][0],'quiet_changes':[y['change_db'] for y in x['quiet_candidates']]} for x in output['profiles']]},indent=2))
