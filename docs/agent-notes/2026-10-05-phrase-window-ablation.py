#!/usr/bin/env python3
"""Reproducible isolated six-case window ablation; references only after discovery."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
for name in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS"):
    os.environ[name]="2"
sys.path.insert(0,str(ROOT/"scripts"))
import phrase_evaluate as evaluator

IDS=("low32-sustain","palm-muted-recurrence","legato-recurrence","c1-missing-fundamental","timing-reference","timing-errors")
VARIANTS=("baseline","short_pulse","pulse_alternatives","seconds_domain")

def digest(path):
    return evaluator.digest(path)

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+".pending")
    temporary.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n")
    temporary.replace(path)

def checked(path,expected=None):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>20_000_000:
        raise ValueError("Invalid artifact")
    if expected and digest(path)!=expected:
        raise ValueError("Artifact hash mismatch")
    return evaluator.guarded_json(path.read_text())

def union_candidates(groups):
    result=[]
    for item in sorted([item for group in groups for item in group],key=lambda item:item["similarity"],reverse=True):
        if any(all(abs(item[key]-prior[key])<.05 for key in (
            "first_start_seconds","first_end_seconds","second_start_seconds","second_end_seconds")) for prior in result):
            continue
        result.append(item)
        if len(result)==60:break
    return result

def aggregate(cache,period,origin,duration):
    import numpy as np
    edges=np.arange(origin,duration+period,period)
    features,centroids=[],[]
    for low,high in zip(edges,edges[1:]):
        selected=(cache["times"]>=low)&(cache["times"]<min(high,duration))
        if selected.any():
            features.append(np.median(cache["features"][:,selected],axis=1))
            centroids.append(float(np.median(cache["centroid"][selected])))
    if len(features)>256:raise ValueError("Aggregation frame budget exceeded")
    return features,centroids

def discover(output,bank_index,pilot_index,cache_from=None):
    import numpy as np
    started=time.monotonic()
    bank=checked(bank_index)
    pilot=checked(pilot_index)
    if pilot["bank_index_sha256"]!=digest(bank_index):raise ValueError("Wrong frozen bank")
    if output.exists():raise ValueError("Output must be new")
    output.mkdir(parents=True)
    sources=output/"sources";sources.mkdir()
    original=ROOT/"scripts/guitar_features.py"
    frozen=sources/"guitar_features.frozen.py"
    shutil.copyfile(original,frozen)
    text=original.read_text()
    needle="    observations = discover_phrase_features(pulse_features, period, duration, onset_times, start, pulse_centroids)"
    if text.count(needle)!=1:raise ValueError("Unknown worker frontend")
    text=text.replace(needle,"    global _ablation_cache\n    _ablation_cache = {\"features\":frame_features,\"times\":frame_times,\"centroid\":centroid,\"onsets\":onset_times}\n"+needle)
    copied=sources/"guitar_features.cache_worker.py";copied.write_text(text)
    spec=importlib.util.spec_from_file_location("ablation_worker",copied)
    worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
    function=inspect.getsource(worker.discover_phrase_features)
    short_source=function.replace("for length in (4, 8, 16):","for length in (2, 4, 8, 16):")
    seconds_source=function.replace("for length in (4, 8, 16):","for length in (10, 15, 20, 30, 40, 60):")
    for name,value in (("short",short_source),("seconds",seconds_source)):
        (sources/f"search-{name}.py").write_text(value)
    functions={}
    for name,value in (("short",short_source),("seconds",seconds_source)):
        namespace=dict(worker.__dict__);exec(compile(value,str(sources/f"search-{name}.py"),"exec"),namespace)
        functions[name]=namespace["discover_phrase_features"]
    # Phase one consumes raw aliases plus already-unseeded observed pulse metadata.
    # No truth file, reference duration, score, boundary or warp is opened here.
    rows=[]
    for index,identifier in enumerate(IDS):
        case_started=time.monotonic()
        job=next(item for item in pilot["cases"] if item["id"]==identifier)
        prior=checked(pilot_index.parent/job["phrases"]["path"],job["phrases"]["sha256"])
        analysis=checked(pilot_index.parent/job["analysis"]["path"],job["analysis"]["sha256"])
        source=Path(prior["source"]["path"])
        identity=prior["source"]["sha256"]
        if digest(source)!=identity or analysis["source"]["sha256"]!=identity:raise ValueError("Changed discovery input")
        alias=output/"inputs"/f"audio-{index+1:02d}.wav";alias.parent.mkdir(exist_ok=True)
        shutil.copyfile(source,alias)
        if digest(alias)!=identity:raise ValueError("Alias changed")
        for variable,key in (("FFMPEG","decode_command"),("FFPROBE","probe_command")):
            executable=Path(prior["provenance"][key][0])
            if not executable.is_absolute() or not executable.is_file() or executable.name not in ("ffmpeg","ffprobe"):
                raise ValueError("Frozen media executable is unavailable")
            os.environ[variable]=str(executable)
        bpm=prior["phrase_backend"]["bpm"]
        origin=prior["phrase_backend"]["pulse_origin_seconds"]
        period=60/bpm
        reuse=cache_from/"cache"/f"case-{index+1:02d}.npz" if cache_from else None
        if reuse and reuse.is_file():
            if digest(cache_from/"inputs"/f"audio-{index+1:02d}.wav")!=identity:
                raise ValueError("Cached source changed")
            with np.load(reuse,allow_pickle=False) as cached:
                cache={key:cached[key] for key in cached.files}
            duration=float(prior["analysis"]["duration_seconds"])
            pulse_features,centroids=aggregate(cache,period,origin,duration)
            baseline={"observations":worker.discover_phrase_features(pulse_features,period,duration,cache["onsets"],origin,centroids)}
            for item in baseline["observations"]["recurrence_candidates"]:
                item.update({"onset_detector":"librosa.onset.onset_detect_spectral_flux","articulation_hint":None,
                    "detector_confidence":None,"first_boundary_confidence":None,"second_boundary_confidence":None})
        else:
            samples,_=worker.load(alias)
            duration=len(samples)/worker.RATE
            baseline=worker.phrases_librosa(samples,bpm,origin)
            cache=worker._ablation_cache
        cachepath=output/"cache"/f"case-{index+1:02d}.npz";cachepath.parent.mkdir(exist_ok=True)
        np.savez_compressed(cachepath,**cache)
        observed=baseline["observations"]["recurrence_candidates"]
        old=[{key:value for key,value in item.items() if "_source_" not in key}
            for item in prior["observations"]["recurrence_candidates"]]
        if observed!=old:raise ValueError("Baseline recurrence differs from frozen pilot")
        pulse_features,centroids=aggregate(cache,period,origin,duration)
        short=functions["short"](pulse_features,period,duration,cache["onsets"],origin,centroids)
        alternatives=[]
        for multiplier in (.5,1.,2.):
            features,centroids=aggregate(cache,period*multiplier,origin,duration)
            result=functions["short"](features,period*multiplier,duration,cache["onsets"],origin,centroids)
            for item in result["recurrence_candidates"]:item["pulse_multiplier"]=multiplier
            alternatives.append(result["recurrence_candidates"])
        features,centroids=aggregate(cache,.05,0.,duration)
        seconds=functions["seconds"](features,.05,duration,cache["onsets"],0.,centroids)
        variants={"baseline":baseline["observations"],"short_pulse":short,
            "pulse_alternatives":{"recurrence_candidates":union_candidates(alternatives)},"seconds_domain":seconds}
        path=output/"predictions"/f"case-{index+1:02d}.json"
        write(path,{"schema_version":1,"source_sha256":identity,"source_read":True,"source_audio_decoded":True,
            "requires_expected_intent":False,"inferred_pulse_period_seconds":period,"observed_pulse_origin_seconds":origin,
            "reference_grid_supplied":False,"baseline_equivalent":True,"cache_sha256":digest(cachepath),
            "variants":variants,"confidence":"unvalidated_similarity_not_probability",
            "detector_confidence":None,"boundary_confidence":None,"performance_issue_confirmed":False})
        rows.append({"id":identifier,"prediction":str(path.relative_to(output)),"prediction_sha256":digest(path),
            "source_sha256":identity,"duration_seconds":duration,"seconds":time.monotonic()-case_started})
        write(output/"progress.json",{"cases":rows,"status":"discovery_only_references_not_opened"})
        print(json.dumps({"case":index+1,"baseline_equivalent":True,"candidate_counts":{key:len(value["recurrence_candidates"]) for key,value in variants.items()}}),flush=True)
        if time.monotonic()-case_started>120 or time.monotonic()-started>600:raise ValueError("Experiment deadline exceeded")
    if sum(row["duration_seconds"] for row in rows)>56.001:raise ValueError("Audio budget exceeded")
    if digest(original)!=digest(frozen):raise ValueError("Canonical worker changed during experiment")
    # Phase two attaches generator truth only after every prediction is durable.
    evaluated=[]
    for row in rows:
        case=next(item for item in bank["cases"] if item["id"]==row["id"])
        truth=checked(bank_index.parent/case["truth"],case["truth_sha256"])
        if truth["source"]["sha256"]!=row["source_sha256"]:raise ValueError("Evaluation source mismatch")
        prediction=checked(output/row["prediction"],row["prediction_sha256"])
        scores={}
        for key,value in prediction["variants"].items():
            metrics=[evaluator.recurrence_metrics(truth["recurrence_pairs"],value["recurrence_candidates"],row["duration_seconds"],threshold) for threshold in (.5,.75)]
            scores[key]={"candidate_count":len(value["recurrence_candidates"]),"pair_metrics":metrics}
        evaluated.append({**row,"truth_sha256":case["truth_sha256"],"scores":scores})
    aggregates={}
    for variant in VARIANTS:
        aggregates[variant]=[]
        for k,threshold in enumerate((.5,.75)):
            metrics=[row["scores"][variant]["pair_metrics"][k] for row in evaluated]
            tp,fp,fn=(sum(metric[key] for metric in metrics) for key in ("tp","fp","fn"))
            aggregates[variant].append({"iou_threshold":threshold,"tp":tp,"fp":fp,"fn":fn,
                "precision":tp/(tp+fp) if tp+fp else 0.,"recall":tp/(tp+fn) if tp+fn else 0.,
                "f1":2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None})
    result={"schema_version":1,"status":"completed_isolated_development_bank_ablation","cases":evaluated,"aggregate":aggregates,
        "seconds":time.monotonic()-started,"unique_audio_seconds":sum(row["duration_seconds"] for row in rows),
        "bank_index_sha256":digest(bank_index),"pilot_index_sha256":digest(pilot_index),
        "canonical_worker_sha256":digest(frozen),"copied_worker_sha256":digest(copied),"harness_sha256":digest(Path(__file__)),
        "numerical_threads":2,"ground_truth_scope":"generator_only_not_musician","listening_accepted":False,
        "inference_reference_labels_supplied":False,"canonical_files_modified":False,"baseline_equivalent_all_cases":True}
    write(output/"results.json",result)
    print(json.dumps({"results":str(output/"results.json"),"aggregate":aggregates,"seconds":result["seconds"]}))

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--cache-from",type=Path)
    args=parser.parse_args()
    output=args.output.resolve()
    if not output.is_relative_to(ROOT/"artifacts/experiments/phrase-window-ablation"):
        raise SystemExit("Output must be isolated phrase-window-ablation subdirectory")
    discover(output,ROOT/"artifacts/benchmarks/root-calibration-bank-20261005T2255/fixtures.json",
        ROOT/"artifacts/benchmarks/root-calibration-pilot-20261005T2300/phrase-pilot-index.json",args.cache_from.resolve() if args.cache_from else None)
