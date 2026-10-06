"""Evidence-only wrapper: save every frozen frontend output before comparisons.

No feature settings or extraction function are changed. The frozen worker is
loaded verbatim; returned spectral-flux vectors are persisted before callers
can compute clean/mix metrics. No labels are read.
"""
import hashlib,importlib.util,json,sys
from pathlib import Path

BASE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
worker=BASE/'feature_proof.py'
assert sha(worker)=='a87586af40aab7aa22e983efbd5a35acdd9f149197cd9861ff33ee57e1e67117'
spec=importlib.util.spec_from_file_location('frozen_pcen_probe',worker)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
extract=module.frontend
snapshots=BASE/'features';assert not snapshots.exists();snapshots.mkdir()
records=[]
def capture(signal,fft_samples):
 result,frames=extract(signal,fft_samples)
 path=snapshots/f'opaque-call-{len(records):02d}-features.npz'
 arrays={name:values['flux'] if isinstance(values,dict) else values for name,values in result.items()}
 module.np.savez(path,**arrays)
 records.append({'call_index':len(records),'fft_samples':fft_samples,'frames':frames,'path':str(path),'sha256':sha(path),'policies':list(arrays),'status':'saved_before_component_pair_comparison'})
 (snapshots/'index.json').write_text(json.dumps({'schema_version':1,'records':records},indent=2))
 return result,frames
module.frontend=capture
sys.argv=[str(worker),'--inputs',str(BASE/'selected-inputs.json'),'--output',str(BASE/'receipt.json')]
module.main()
(BASE/'invocation.json').write_text(json.dumps({'schema_version':1,'worker_sha256':sha(worker),'evidence_wrapper_sha256':sha(Path(__file__)),'feature_index_sha256':sha(snapshots/'index.json'),'receipt_sha256':sha(BASE/'receipt.json'),'feature_calls':len(records),'settings_changed':False,'labels_read':False},indent=2))
