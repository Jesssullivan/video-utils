import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS'):os.environ[key]='2'
import hashlib,importlib.util,json,time
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
plan=json.loads((BASE/'plan.json').read_text())
assert sha(BASE/'plan.json')=='a5c95ac0b418828e6290b6d6df1952f04b4ece847e75d4f83a2b5d263fb9a6b3'
frozen=ROOT/plan['frozen_frontend_worker']
assert sha(frozen)==plan['frozen_frontend_worker_sha256']
spec=importlib.util.spec_from_file_location('fixed_frontend',frozen)
frontend=importlib.util.module_from_spec(spec);spec.loader.exec_module(frontend)
input_path=ROOT/plan['input'];manifest_path=input_path.parent/'manifest.json'
assert sha(input_path)==plan['input_sha256'] and sha(manifest_path)==plan['producer_manifest_sha256']
manifest=json.loads(manifest_path.read_text());original=Path(manifest['source']['path'])
assert sha(original)==plan['source_sha256']
latest=ROOT/'artifacts/latest.json';latest_before=sha(latest)
started=time.monotonic()
rate,audio=wavfile.read(input_path)
assert rate==44100 and audio.ndim==1 and audio.dtype==np.float32 and np.isfinite(audio).all()
features_dir=BASE/'features';assert not features_dir.exists();features_dir.mkdir()
all_outputs=[];snapshots=[];excerpts=[]
for excerpt in plan['excerpts']:
 start,end=[int(second*rate) for second in excerpt['seconds']]
 cropped=audio[start:end];assert len(cropped)==4*rate
 signal=resample_poly(cropped.astype(np.float64),160,441).astype(np.float32)
 assert len(signal)==64000 and np.isfinite(signal).all()
 excerpts.append({'id':excerpt['id'],'native_samples':[start,end],'native_f32le_sha256':hashlib.sha256(cropped.astype('<f4').tobytes()).hexdigest(),'analysis_sample_count':len(signal),'analysis_f32le_sha256':hashlib.sha256(signal.astype('<f4').tobytes()).hexdigest()})
 for nfft in plan['fft_samples']:
  output,frames=frontend.frontend(signal,nfft)
  arrays={name:values['flux'] if isinstance(values,dict) else values for name,values in output.items()}
  assert all(value.shape==(801,) and np.isfinite(value).all() for value in arrays.values())
  path=features_dir/f"{excerpt['id']}-{nfft}.npz";np.savez(path,**arrays)
  record={'excerpt_id':excerpt['id'],'fft_samples':nfft,'frames':frames,'path':str(path.relative_to(ROOT)),'sha256':sha(path),'policies':list(arrays),'status':'saved_before_any_cross_policy_comparison'}
  snapshots.append(record);all_outputs.append((record,output))
(features_dir/'index.json').write_text(json.dumps({'schema_version':1,'snapshots':snapshots},indent=2))
# All prediction/features are now saved and hash-bound; begin characterization.
results=[]
for record,outputs in all_outputs:
 rows=[]
 for policy,value in outputs.items():
  flux=value['flux'] if isinstance(value,dict) else value
  baseline_name='power-log' if policy.startswith('power-') else 'magnitude-log'
  baseline=outputs[baseline_name]
  row={'policy':policy,'paired_log_reference':baseline_name,'paired_log_whole_flux_cosine':frontend.cosine(flux,baseline),'paired_log_after_one_second_flux_cosine':frontend.cosine(flux[200:],baseline[200:]),'envelope_quantiles_native_feature_units':np.quantile(flux,[.5,.95,1]).tolist()}
  if isinstance(value,dict):row['pcen_checks']={key:item for key,item in value.items() if key!='flux'}
  rows.append(row)
 results.append({'excerpt_id':record['excerpt_id'],'fft_samples':record['fft_samples'],'frame_count':record['frames'],'rows':rows})
assert sha(input_path)==plan['input_sha256'] and sha(manifest_path)==plan['producer_manifest_sha256'] and sha(original)==plan['source_sha256']
assert sha(latest)==latest_before
for snapshot in snapshots:assert sha(ROOT/snapshot['path'])==snapshot['sha256']
receipt={'schema_version':1,'kind':'fixed_actual_feature_characterization_not_acceptance','plan_sha256':sha(BASE/'plan.json'),'worker_sha256':sha(Path(__file__)),'frozen_frontend_worker_sha256':sha(frozen),'input_sha256':sha(input_path),'manifest_sha256':sha(manifest_path),'original_source_sha256':sha(original),'latest_sha256_before_and_after':latest_before,'feature_index_sha256':sha(features_dir/'index.json'),'excerpts':excerpts,'results':results,'elapsed_seconds':time.monotonic()-started,'numeric_threads':2,'versions':{'numpy':np.__version__,'librosa':frontend.librosa.__version__},'input_and_source_and_latest_unchanged':True,'features_saved_before_comparisons':True,'interpretation':['No clean reference, articulation labels, intended score, onset grading, pitch/phrase accuracy or audible preservation acceptance.','Cross-policy cosine describes agreement with a log feature transform, not better musical detection.','Both cosine metrics retain centered final-edge padding; whole metric also retains initial padding.','Four policies and first-frame M0=E0 state unchanged from frozen generated probe;64/256ms supports remain separate.','Feature quantiles have policy-dependent units; absolute levels cannot be ranked as noise reduction.']}
assert receipt['elapsed_seconds']<90
assert not (BASE/'receipt.json').exists()
(BASE/'receipt.json').write_text(json.dumps(receipt,indent=2,allow_nan=False))
print(json.dumps({'elapsed_seconds':receipt['elapsed_seconds'],'feature_snapshot_count':len(snapshots),'results':len(results)}))
