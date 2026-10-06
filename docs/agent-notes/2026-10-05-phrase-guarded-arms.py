#!/usr/bin/env python3
"""Frozen experimental A/B/C/D phrase arms; cache-only, no labels or waveform reads."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
import zipfile
import tempfile

for variable in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS"):
    os.environ[variable]="2"
ROOT=Path(__file__).resolve().parents[2]
CANONICAL_SHA="2ed031e8000cbcda92b504db10c98de03f456c90573cbff815cbb940c9ac86fe"
SETTINGS={"arms":["A","B","C","D"],"search_pulses":[2,4,8,16],"minimum_cosine":.8,
    "proposal_cap":60,"contrast_minimum":.10,"ranked_cap":10,
    "competitor_baseline":"mean_of_two_anchor_medians_excluding_self_overlap_and_selected_partner",
    "endpoint_context_seconds":.2,"endpoint_radius":"one_inferred_pulse_capped_at_.75_seconds",
    "endpoint_cap_seconds":.75,"novelty_threshold":"max(.25,q75,median+.5MAD)",
    "novelty_peak":"score>=left_and_score>right","endpoint_tie":"highest_score_then_nearest_raw_then_earliest",
    "ambiguous_or_invalid_refinement":"keep_all_raw_endpoints_never_drop_candidate",
    "maximum_aggregation_frames":256,"maximum_native_feature_frames":1000,"numerical_threads":2,
    "inference_reference_labels_supplied":False,"waveform_decoding":False}

def digest(path):
    with Path(path).open("rb") as handle:return hashlib.file_digest(handle,"sha256").hexdigest()

def settings_hash():
    return hashlib.sha256(json.dumps(SETTINGS,sort_keys=True,allow_nan=False).encode()).hexdigest()

def check_cache_archive(path):
    with zipfile.ZipFile(path) as archive:
        members=archive.infolist()
        if len(members)!=4 or {item.filename for item in members}!={"features.npy","times.npy","centroid.npy","onsets.npy"} or sum(item.file_size for item in members)>1_000_000:
            raise ValueError("Feature cache archive expansion/member budget exceeded")

def array(value,name):
    import numpy as np
    result=np.asarray(value,dtype=float)
    if not np.isfinite(result).all():raise ValueError(f"Nonfinite {name}")
    return result

def validate(cache,period,origin,duration):
    import numpy as np
    features=array(cache["features"],"features");times=array(cache["times"],"times")
    centroids=array(cache["centroid"],"centroid");onsets=array(cache["onsets"],"onsets")
    if features.ndim!=2 or not 2<=features.shape[0]<=64 or times.ndim!=1 or not 4<=len(times)<=1000 or features.shape[1]!=len(times):
        raise ValueError("Feature matrix budget/layout invalid")
    if centroids.shape!=times.shape or np.any(np.diff(times)<=0) or times[0]<0 or times[-1]>duration+.05:
        raise ValueError("Feature timestamp/centroid axes invalid")
    if onsets.ndim!=1 or len(onsets)>2000 or np.any(onsets<0) or np.any(onsets>=duration) or np.any(np.diff(onsets)<0):
        raise ValueError("Onset source extent invalid")
    if not np.isfinite([period,origin,duration]).all() or not .1<=period<=3 or not 0<=origin<duration<=12:
        raise ValueError("Experimental period/origin/duration bounds invalid")
    return {"features":features,"times":times,"centroid":centroids,"onsets":onsets}

def aggregate(cache,period,origin,duration):
    import numpy as np
    values,centroids=[],[]
    for low,high in zip(np.arange(origin,duration+period,period),np.arange(origin,duration+period,period)[1:]):
        mask=(cache["times"]>=low)&(cache["times"]<min(high,duration))
        if mask.any():
            values.append(np.median(cache["features"][:,mask],axis=1))
            centroids.append(float(np.median(cache["centroid"][mask])))
    if len(values)>256:raise ValueError("Aggregation frame budget exceeded")
    return array(values,"aggregate"),centroids

def standardized(matrix):
    import numpy as np
    scale=np.std(matrix,axis=0);active=scale>1e-5
    if not active.any():return np.zeros((len(matrix),0))
    return np.clip((matrix[:,active]-np.mean(matrix[:,active],axis=0))/scale[active],-4,4)

def load_search():
    source=ROOT/"scripts/guitar_features.py"
    if digest(source)!=CANONICAL_SHA:raise ValueError("Canonical frontend/search changed after arm preregistration")
    text=source.read_text();tree=ast.parse(text)
    node=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="discover_phrase_features")
    body=ast.get_source_segment(text,node)
    if body.count("for length in (4, 8, 16):")!=1:raise ValueError("Unrecognized frozen window definition")
    body=body.replace("for length in (4, 8, 16):","for length in (2, 4, 8, 16):")
    namespace={};exec(compile(body,"<frozen_short_search>","exec"),namespace)
    return namespace["discover_phrase_features"],hashlib.sha256(body.encode()).hexdigest()

def contrast(candidate,z,period,origin):
    import numpy as np
    length=candidate["pulse_count"]
    first=round((candidate["first_start_seconds"]-origin)/period)
    second=round((candidate["second_start_seconds"]-origin)/period)
    if length not in (2,4,8,16) or not 0<=first<second or second+length>len(z) or z.shape[1]==0:
        raise ValueError("Candidate search-grid identity invalid")
    vectors=np.stack([z[index:index+length].ravel() for index in range(len(z)-length+1)])
    norms=np.linalg.norm(vectors,axis=1);normalized=vectors/np.maximum(norms[:,None],1e-10)
    score=float(np.clip(normalized[first]@normalized[second],-1,1))
    baselines=[];counts=[]
    for anchor,partner in ((first,second),(second,first)):
        competitors=[index for index in range(len(vectors)) if abs(index-anchor)>=length and index!=partner and norms[index]>=1e-6]
        counts.append(len(competitors))
        baselines.append(float(np.median(normalized[competitors]@normalized[anchor])) if competitors else None)
    background=sum(baselines)/2 if all(value is not None for value in baselines) else None
    return {"match_cosine":score,"anchor_competitor_medians":baselines,"anchor_competitor_counts":counts,
        "baseline_cosine":background,"contrast":score-background if background is not None else None,
        "qualification":"heuristic_distinctiveness_not_probability"}

def rank(candidates,z,period,origin):
    scored=[];audit=[]
    for index,candidate in enumerate(candidates):
        evidence=contrast(candidate,z,period,origin)
        eligible=evidence["contrast"] is not None and evidence["contrast"]>=.10-1e-12
        audit.append({"candidate_index":index,**evidence,"status":"eligible" if eligible else
                      "insufficient_competitor_background" if evidence["contrast"] is None else "below_contrast_threshold"})
        if eligible:scored.append((index,candidate,evidence))
    scored.sort(key=lambda row:(-row[2]["contrast"],-row[2]["match_cosine"],
        row[1]["first_start_seconds"],row[1]["second_start_seconds"],row[1]["pulse_count"],row[0]))
    for index,_,_ in scored[10:]:audit[index]["status"]="ranked_cap_excluded"
    kept=[{**candidate,"contrast_evidence":evidence,"original_candidate_index":index} for index,candidate,evidence in scored[:10]]
    return kept,audit

def novelty(cache):
    import numpy as np
    z=standardized(cache["features"].T);times=cache["times"]
    values=np.zeros(len(times));valid=np.zeros(len(times),dtype=bool)
    for index,time in enumerate(times):
        before=(times>=time-.1-1e-12)&(times<time)
        after=(times>=time)&(times<time+.1-1e-12)
        if time<.1 or time+.1>times[-1] or not before.any() or not after.any() or not z.shape[1]:continue
        values[index]=float(np.sqrt(np.mean((z[before].mean(axis=0)-z[after].mean(axis=0))**2)));valid[index]=True
    usable=values[valid]
    if not len(usable):return values,valid,None
    median=float(np.median(usable));mad=float(np.median(np.abs(usable-median)))
    return values,valid,max(.25,float(np.quantile(usable,.75)),median+.5*mad)

def refine(candidate,cache,period,duration,curve=None):
    values,valid,threshold=curve or novelty(cache)
    times=cache["times"];margin=min(period,.75)
    keys=("first_start_seconds","first_end_seconds","second_start_seconds","second_end_seconds")
    original={key:float(candidate[key]) for key in keys};proposed=dict(original);audit={}
    for key,raw in original.items():
        if raw==0 or raw==duration:
            audit[key]={"status":"recording_extent_retained","raw_seconds":raw,"refined_seconds":raw};continue
        anchors=[index for index in range(1,len(times)-1) if valid[index] and threshold is not None and
            abs(float(times[index])-raw)<=margin+1e-12 and values[index]>=threshold and
            values[index]>=values[index-1] and values[index]>values[index+1]]
        if not anchors:
            audit[key]={"status":"no_clear_novelty_anchor_raw_retained","raw_seconds":raw,"refined_seconds":raw};continue
        best=min(anchors,key=lambda index:(-float(values[index]),abs(float(times[index])-raw),float(times[index])))
        proposed[key]=float(times[best]);audit[key]={"status":"novelty_refined_hypothesis","raw_seconds":raw,
            "refined_seconds":proposed[key],"novelty":float(values[best]),"threshold":threshold}
    valid_span=0<=proposed[keys[0]]<proposed[keys[1]]<=proposed[keys[2]]<proposed[keys[3]]<=duration
    if not valid_span:
        proposed=original
        for key in keys:audit[key]["status"]="invalid_refinement_all_raw_endpoints_retained";audit[key]["refined_seconds"]=original[key]
    result={**candidate,**proposed,"raw_endpoints":original,"endpoint_refinement":audit,
        "search_pulse_count":candidate["pulse_count"],"refinement_confidence":None,
        "refinement_qualification":"unvalidated_acoustic_novelty_not_semantic_phrase_or_note_boundary"}
    for prefix in ("first","second"):
        start,end=result[prefix+"_start_seconds"],result[prefix+"_end_seconds"]
        result[prefix+"_onset_offsets_seconds"]=[float(time)-start for time in cache["onsets"] if start<=time<end]
    return result

def build(cache,period,origin,duration):
    cache=validate(cache,period,origin,duration);features,centroids=aggregate(cache,period,origin,duration)
    search,search_sha=load_search()
    proposals=search(features,period,duration,cache["onsets"],origin,centroids)["recurrence_candidates"]
    for item in proposals:
        item.update(detector_confidence=None,first_boundary_confidence=None,second_boundary_confidence=None,
            articulation_hint=None,performance_issue_confirmed=False)
    selected,audit=rank(proposals,standardized(features),period,origin) if proposals else ([],[])
    curve=novelty(cache)
    return {"schema_version":1,"status":"isolated_guarded_arm_hypotheses","settings":SETTINGS,"settings_sha256":settings_hash(),
        "harness_sha256":digest(Path(__file__)),"canonical_worker_sha256":CANONICAL_SHA,"short_search_sha256":search_sha,
        "inferred_pulse_period_seconds":period,"observed_pulse_origin_seconds":origin,"duration_seconds":duration,
        "proposal_count":len(proposals),"contrast_audit":audit,"novelty_threshold":curve[2],
        "arms":{"A":proposals,"B":selected,"C":[refine(item,cache,period,duration,curve) for item in proposals],
                "D":[refine(item,cache,period,duration,curve) for item in selected]},
        "requires_expected_intent":False,"performance_issue_confirmed":False,"detector_confidence":None,
        "boundary_confidence":None,"source_audio_decoded":False,"inference_reference_labels_supplied":False}

class StructuralTests(unittest.TestCase):
    def test_contrast_background_formula_and_homogeneity(self):
        import numpy as np
        candidate={"pulse_count":2,"first_start_seconds":0.,"second_start_seconds":4.}
        z=np.asarray([[1.,0.],[0.,1.],[-1.,0.],[0.,-1.],[1.,0.],[0.,1.],[-1.,0.],[0.,-1.]])
        evidence=contrast(candidate,z,1.,0.)
        self.assertAlmostEqual(evidence["match_cosine"],1.)
        self.assertEqual(evidence["anchor_competitor_counts"],[4,3])
        # Independently calculated: first[-1,0,0,-1], second[0,-1,-1].
        self.assertAlmostEqual(evidence["baseline_cosine"],-.75)
        self.assertAlmostEqual(evidence["contrast"],1.75)
        flat=contrast(candidate,np.ones((8,2)),1.,0.)
        self.assertAlmostEqual(flat["contrast"],0.)
        self.assertEqual(rank([candidate],np.ones((8,2)),1.,0.)[0],[])

    def test_refinement_ambiguous_and_invalid_keep_candidates(self):
        import numpy as np
        cache={"times":np.arange(0,4.01,.05),"features":np.ones((2,81)),"onsets":np.array([.25,1.25,2.25,3.25])}
        candidate={"first_start_seconds":.3,"first_end_seconds":1.3,"second_start_seconds":2.3,"second_end_seconds":3.3,"pulse_count":2}
        unchanged=refine(candidate,cache,.5,4.)
        self.assertEqual(unchanged["raw_endpoints"],{key:candidate[key] for key in unchanged["raw_endpoints"]})
        self.assertTrue(all(item["status"]=="no_clear_novelty_anchor_raw_retained" for item in unchanged["endpoint_refinement"].values()))
        values=np.zeros(81);values[20]=1.;valid=np.ones(81,dtype=bool)
        invalid={**candidate,"first_start_seconds":.8,"first_end_seconds":1.2}
        result=refine(invalid,cache,.5,4.,(values,valid,.25))
        self.assertEqual(result["first_start_seconds"],.8);self.assertEqual(result["first_end_seconds"],1.2)
        self.assertTrue(all(item["status"]=="invalid_refinement_all_raw_endpoints_retained" for item in result["endpoint_refinement"].values()))

    def test_refinement_uses_source_curve_not_truth_and_rebases_onsets(self):
        import numpy as np
        cache={"times":np.arange(0,4.01,.05),"features":np.ones((2,81)),"onsets":np.array([.25,1.25,2.25,3.25])}
        values=np.zeros(81);values[[5,25,45,65]]=1.;valid=np.ones(81,dtype=bool)
        candidate={"first_start_seconds":.3,"first_end_seconds":1.3,"second_start_seconds":2.3,"second_end_seconds":3.3,"pulse_count":2}
        result=refine(candidate,cache,.5,4.,(values,valid,.25))
        self.assertAlmostEqual(result["first_start_seconds"],.25)
        self.assertEqual(result["first_onset_offsets_seconds"],[0.])
        self.assertEqual(result["second_onset_offsets_seconds"],[0.])
        self.assertIsNone(result["refinement_confidence"])

    def test_limits_finite_and_unchanged_source(self):
        import numpy as np
        cache={"features":np.zeros((2,20)),"times":np.arange(20)*.05,"centroid":np.ones(20),"onsets":[]}
        validate(cache,.5,0.,1.)
        with self.assertRaises(ValueError):validate(cache,.5,0.,20.)
        cache["features"][0,0]=float("nan")
        with self.assertRaises(ValueError):validate(cache,.5,0.,1.)
        _,source_sha=load_search();self.assertEqual(len(source_sha),64)

    def test_cap_ties_and_independent_arm_counts(self):
        import numpy as np
        z=np.asarray([[1.,0.],[0.,1.],[-1.,0.],[0.,-1.],[1.,0.],[0.,1.],[-1.,0.],[0.,-1.]])
        items=[{"pulse_count":2,"first_start_seconds":0.,"second_start_seconds":4.,"ordinal":i} for i in range(12)]
        kept,audit=rank(items,z,1.,0.)
        self.assertEqual([item["ordinal"] for item in kept],list(range(10)))
        self.assertEqual([item["status"] for item in audit[-2:]],["ranked_cap_excluded"]*2)
        times=np.arange(0,8,.05)
        cache={"features":np.vstack((np.sin(times*6),np.cos(times*6))),"times":times,
            "centroid":np.ones(len(times)),"onsets":np.arange(.25,8,.5)}
        result=build(cache,.5,0.,8.)
        self.assertGreater(len(result["arms"]["A"]),0)
        self.assertEqual(len(result["arms"]["C"]),len(result["arms"]["A"]))
        self.assertEqual(len(result["arms"]["D"]),len(result["arms"]["B"]))
        self.assertLessEqual(len(result["arms"]["B"]),10)
        self.assertTrue(all(not item["performance_issue_confirmed"] for arm in result["arms"].values() for item in arm))

    def test_cache_archive_expansion_and_member_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"cache.npz"
            with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("features.npy",b"0"*1_000_001)
                for name in ("times.npy","centroid.npy","onsets.npy"):archive.writestr(name,b"0")
            with self.assertRaises(ValueError):check_cache_archive(path)
            with zipfile.ZipFile(path,"w") as archive:archive.writestr("unexpected.npy",b"0")
            with self.assertRaises(ValueError):check_cache_archive(path)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--cache-index",type=Path)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if args.self_test:
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(StructuralTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    if not args.cache_index or not args.output:parser.error("cache-index/output required")
    import numpy as np
    sys.path.insert(0,str(ROOT/"scripts"));from phrase_evaluate import guarded_json
    index_path=args.cache_index.resolve()
    if index_path.stat().st_size>64_000:raise ValueError("Cache metadata budget exceeded")
    index_identity=digest(index_path)
    index=guarded_json(index_path.read_text())
    if not 1<=len(index["cases"])<=12:raise ValueError("Case budget exceeded")
    if sum(item["duration_seconds"] for item in index["cases"])>120+1e-9:raise ValueError("Aggregate duration budget exceeded")
    output=args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT/"artifacts/experiments/phrase-window-ablation"):
        raise ValueError("Choose new isolated output")
    output.mkdir(parents=True);rows=[]
    for ordinal,item in enumerate(index["cases"]):
        path=(index_path.parent/item["cache"]).resolve()
        if not path.is_relative_to(ROOT/"artifacts/experiments") or path.is_symlink() or path.stat().st_size>20_000_000 or digest(path)!=item["cache_sha256"]:
            raise ValueError("Unbound feature cache")
        check_cache_archive(path)
        with np.load(path,allow_pickle=False) as value:cache={key:value[key] for key in value.files}
        result=build(cache,item["inferred_pulse_period_seconds"],item["observed_pulse_origin_seconds"],item["duration_seconds"])
        if digest(path)!=item["cache_sha256"]:raise ValueError("Feature cache changed during arm computation")
        result["source_sha256"]=item["source_sha256"];result["cache_sha256"]=item["cache_sha256"]
        artifact=output/f"case-{ordinal+1:02d}.json";artifact.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
        rows.append({"id":item["id"],"path":artifact.name,"sha256":digest(artifact),"counts":{key:len(value) for key,value in result["arms"].items()}})
    if digest(index_path)!=index_identity:raise ValueError("Cache index changed during arm computation")
    receipt={"schema_version":1,"status":"saved_label_free_cache_arm_predictions","settings_sha256":settings_hash(),
        "cache_index_sha256":digest(index_path),"harness_sha256":digest(Path(__file__)),"cases":rows,
        "heldout_waveforms_read":False,"reference_labels_read":False,"source_audio_decoded":False}
    (output/"arm-index.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps(receipt));return 0

if __name__=="__main__":raise SystemExit(main())
