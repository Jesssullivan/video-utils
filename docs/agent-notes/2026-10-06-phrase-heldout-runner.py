#!/usr/bin/env python3
"""Bounded isolated held-out execution; frozen arms, opaque inputs, truth read last."""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import wave

ROOT=Path(__file__).resolve().parents[2]
ARMS_SHA="78ca89de9cea327cc4ec1096a83522781a08bc161819699b69797ca273e2fb6c"
SETTINGS_SHA="f50e31ee6eba0966580f78c9124938b4cdf116a6242eed2b0e7b2bb147f32edd"
FRONTEND_SHA="2ed031e8000cbcda92b504db10c98de03f456c90573cbff815cbb940c9ac86fe"
RHYTHM_SHA="264b723ca29e4731da0a12d5dce221e7826a38b67f848ce9f4ffcf8bfe4b35b9"
sys.path.insert(0,str(ROOT/"scripts"))
from phrase_evaluate import guarded_json,recurrence_metrics,pair_spans,digest

def write(path,payload):
    temporary=path.with_name(path.name+".pending")
    temporary.write_text(json.dumps(payload,indent=2,allow_nan=False)+"\n")
    os.chmod(temporary,0o600);temporary.replace(path)

def read(path,expected=None):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>20_000_000:
        raise ValueError("Invalid bounded JSON artifact")
    before=digest(path)
    if expected and before!=expected:raise ValueError("JSON hash mismatch")
    value=guarded_json(path.read_text())
    if digest(path)!=before:raise ValueError("Unstable JSON artifact")
    return value

def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def child(source,target,identity):
    import numpy as np
    if digest(source)!=identity:raise ValueError("Opaque input hash mismatch")
    sources=target.parent.parent/"sources"
    rhythm=module(sources/"rhythm.py","heldout_rhythm")
    features=module(sources/"guitar_features.cache_worker.py","heldout_features")
    arms_path=ROOT/"docs/agent-notes/2026-10-05-phrase-guarded-arms.py"
    if digest(arms_path)!=ARMS_SHA:raise ValueError("Frozen arm harness changed")
    arms=module(arms_path,"heldout_arms")
    if arms.settings_hash()!=SETTINGS_SHA:raise ValueError("Frozen settings changed")
    # One canonical16k FFmpeg decode feeds both unchanged analysis primitives.
    samples=rhythm.decode(source)
    if len(samples)!=160_000:raise ValueError("Held-out input must decode to exactly10seconds")
    analysis=rhythm.analyze(samples,source_start=0.,bpm=None,backend="librosa")
    analysis["source"]={"path":str(source),"sha256":identity}
    grid=analysis.get("click_grid") or {}
    bpm=grid.get("bpm") or (analysis.get("selected_periodicity") or {}).get("bpm")
    write(target/"analysis.json",analysis)
    if bpm is None:
        write(target/"result.json",{"status":"unseeded_pulse_unavailable","source_sha256":identity,
            "source_read":True,"source_audio_decoded":True,"arms":{key:[] for key in "ABCD"},
            "performance_issue_confirmed":False,"requires_expected_intent":False})
        return
    period=60/bpm;origin=max(0,float(grid.get("phase_seconds_audio_relative",0))%period)
    original=features.phrases_librosa(samples,bpm,origin)
    cache=features._ablation_cache
    cache_path=target/"features.npz";np.savez_compressed(cache_path,**cache)
    result=arms.build(cache,period,origin,10.)
    result.update(source_sha256=identity,cache_sha256=digest(cache_path),source_read=True,source_audio_decoded=True,
        decoded_sample_count=len(samples),decoded_sample_rate=16000,decode_shared_by_primitives=True,
        pulse_provenance="same_source_unseeded_analysis_not_generator_bpm",original_four_pulse_candidate_count=len(original["observations"]["recurrence_candidates"]))
    write(target/"result.json",result)
    if digest(source)!=identity or digest(arms_path)!=ARMS_SHA:raise ValueError("Input or frozen harness changed")

def runner(bank_index,output):
    bank_index=bank_index.resolve();bank=read(bank_index)
    bank_hash=digest(bank_index)
    if bank.get("schema_version")!=2 or bank.get("case_count")!=12 or bank.get("total_duration_seconds")!=120 or len(bank.get("cases",[]))!=12:
        raise ValueError("Requires admitted12-case120-second held-out bank")
    if output.exists() or not output.resolve().is_relative_to(ROOT/"artifacts/experiments/phrase-window-ablation"):
        raise ValueError("Choose new isolated experiment output")
    if digest(ROOT/"scripts/guitar_features.py")!=FRONTEND_SHA or digest(ROOT/"scripts/rhythm.py")!=RHYTHM_SHA or digest(ROOT/"docs/agent-notes/2026-10-05-phrase-guarded-arms.py")!=ARMS_SHA:
        raise ValueError("Frozen inference sources changed")
    output.mkdir(parents=True);sources=output/"sources";sources.mkdir();(output/"inputs").mkdir();(output/"discovery").mkdir()
    for name in ("rhythm.py","guitar_features.py"):shutil.copyfile(ROOT/"scripts"/name,sources/name)
    shutil.copyfile(ROOT/"docs/agent-notes/2026-10-05-phrase-guarded-arms.py",sources/"arms.harness.py")
    shutil.copyfile(Path(__file__),sources/"runner.frozen.py")
    text=(sources/"guitar_features.py").read_text()
    needle="    observations = discover_phrase_features(pulse_features, period, duration, onset_times, start, pulse_centroids)"
    if text.count(needle)!=1:raise ValueError("Unknown frozen frontend")
    text=text.replace(needle,"    global _ablation_cache\n    _ablation_cache = {\"features\":frame_features,\"times\":frame_times,\"centroid\":centroid,\"onsets\":onset_times}\n"+needle)
    (sources/"guitar_features.cache_worker.py").write_text(text)
    prior=ROOT/"artifacts/benchmarks/root-calibration-pilot-20261005T2300"
    old_index=read(prior/"phrase-pilot-index.json");old=read(prior/old_index["cases"][0]["phrases"]["path"])
    environment={key:os.environ[key] for key in ("PATH","HOME","TMPDIR","LANG","LC_ALL") if key in os.environ}
    environment.update({key:"2" for key in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS")})
    environment.update(FFMPEG=old["provenance"]["decode_command"][0],FFPROBE=old["provenance"]["probe_command"][0])
    receipt={"schema_version":1,"status":"discovery_running_truth_unopened","bank_index_sha256":bank_hash,
        "harness_sha256":ARMS_SHA,"settings_sha256":SETTINGS_SHA,"runner_sha256":digest(Path(__file__)),
        "rhythm_sha256":RHYTHM_SHA,"frontend_sha256":FRONTEND_SHA,"cases":[],"failures":[],
        "numerical_threads":2,"unique_audio_seconds":120,"reference_labels_supplied":False,
        "authority":"operator_parallel_goal/R-HOOK-CONVERGENCE-20261004/R-N13"}
    started=time.monotonic()
    for ordinal,case in enumerate(bank["cases"]):
        source=bank_index.parent/case["source"]["path"];identity=case["source"]["sha256"]
        if digest(source)!=identity:raise ValueError("Held-out mixture source changed")
        with wave.open(str(source),"rb") as handle:
            if (handle.getframerate(),handle.getnchannels(),handle.getnframes())!=(48000,1,480000):raise ValueError("Held-out native extent invalid")
        alias=output/"inputs"/f"audio-{ordinal+1:02d}.wav";shutil.copyfile(source,alias)
        target=output/"discovery"/f"case-{ordinal+1:02d}";target.mkdir()
        argv=[sys.executable,str(Path(__file__).resolve()),"--child","--input",str(alias),"--target",str(target),"--identity",identity]
        with (target/"worker.stdout").open("wb") as stdout,(target/"worker.stderr").open("wb") as stderr:
            process=subprocess.Popen(argv,stdout=stdout,stderr=stderr,env=environment)
            receipt["cases"].append({"id":case["id"],"ordinal":ordinal+1,"pid":process.pid,"argv":argv,"source_sha256":identity,"status":"running"})
            write(output/"run.json",receipt)
            remaining=min(120,max(.1,600-(time.monotonic()-started)))
            try:code=process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
                code=-1
                receipt["signal_receipt"]={"actor":"phrase_dag","target":process.pid,"ownership":"just_spawned_case_worker",
                    "reason":"bounded_case_or_run_deadline","ruling":"R-N11","prior_state":"poll_running","result":"terminated"}
        row=receipt["cases"][-1];row["exit_code"]=code;row["status"]="completed" if code==0 else "failed"
        if code!=0:
            receipt["failures"].append({"ordinal":ordinal+1,"exit_code":code});receipt["status"]="partial_discovery_failed_truth_unopened"
            write(output/"run.json",receipt);return 1
        row["result"]=str((target/"result.json").relative_to(output));row["result_sha256"]=digest(target/"result.json")
        write(output/"run.json",receipt)
        print(json.dumps({"ordinal":ordinal+1,"status":"completed","elapsed_seconds":time.monotonic()-started}),flush=True)
    receipt["status"]="all_predictions_saved_and_hashed_truth_unopened";write(output/"run.json",receipt)
    # Only now open generated references. No post-reference inference follows.
    evaluated=[]
    for case,row in zip(bank["cases"],receipt["cases"]):
        truth_receipt=case["truth"];truth=read(bank_index.parent/truth_receipt["path"],truth_receipt["sha256"])
        prediction=read(output/row["result"],row["result_sha256"])
        if truth["source"]["sha256"]!=row["source_sha256"]:raise ValueError("Held-out evaluation source mismatch")
        scores={}
        for arm,candidates in prediction["arms"].items():
            metrics=[recurrence_metrics(truth["recurrence_pairs"],candidates,10.,threshold) for threshold in (.5,.75)]
            endpoint=[]
            for match in metrics[0]["matches"]:
                ref=pair_spans(truth["recurrence_pairs"][match["reference_index"]],10.)
                candidate=pair_spans(candidates[match["estimate_index"]],10.)
                endpoint.extend(candidate[k][j]-ref[k][j] for k in (0,1) for j in (0,1))
            scores[arm]={"pair_metrics":metrics,"matched_endpoint_offsets_seconds":endpoint,"matched_endpoint_count":len(endpoint),
                "candidate_count":len(candidates),"negative_reference":not truth["recurrence_pairs"]}
        evaluated.append({"id":case["id"],"seed":case["seed"],"cohort":case["cohort"],"source_sha256":row["source_sha256"],
            "truth_sha256":truth_receipt["sha256"],"scores":scores,"prediction_status":prediction["status"]})
    aggregate={}
    for scope,selected in (("all",evaluated),("seed211",[row for row in evaluated if row["seed"]==211]),("seed307",[row for row in evaluated if row["seed"]==307])):
        aggregate[scope]={}
        for arm in "ABCD":
            aggregate[scope][arm]=[]
            for k,threshold in enumerate((.5,.75)):
                values=[row["scores"][arm]["pair_metrics"][k] for row in selected]
                tp,fp,fn=(sum(value[key] for value in values) for key in ("tp","fp","fn"))
                offsets=[abs(value) for row in selected for value in row["scores"][arm]["matched_endpoint_offsets_seconds"]]
                aggregate[scope][arm].append({"iou_threshold":threshold,"tp":tp,"fp":fp,"fn":fn,
                    "precision":tp/(tp+fp) if tp+fp else 0.,"recall":tp/(tp+fn) if tp+fn else 0.,
                    "f1":2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,"matched_endpoint_count_at_primary_iou":len(offsets),
                    "mean_absolute_endpoint_error_at_primary_iou_seconds":sum(offsets)/len(offsets) if offsets else None,
                    "negative_false_candidates":sum(row["scores"][arm]["candidate_count"] for row in selected if row["scores"][arm]["negative_reference"])})
    result={"schema_version":1,"status":"completed_frozen_heldout_measurements","bank_index_sha256":bank_hash,
        "harness_sha256":ARMS_SHA,"settings_sha256":SETTINGS_SHA,"cases":evaluated,"aggregate":aggregate,
        "elapsed_seconds":time.monotonic()-started,"fixture_count":12,"unique_audio_seconds":120,
        "all_predictions_saved_before_truth_read":True,"settings_retuned":False,"ground_truth_scope":"generator_only_not_musician",
        "performance_issue_confirmed":False,"listening_accepted":False,"canonical_defaults_activated":False}
    if digest(bank_index)!=bank_hash or digest(ROOT/"docs/agent-notes/2026-10-05-phrase-guarded-arms.py")!=ARMS_SHA:
        raise ValueError("Frozen input/source changed")
    write(output/"heldout-evaluation.json",result);receipt["status"]="completed_frozen_heldout_measurements"
    receipt["evaluation_sha256"]=digest(output/"heldout-evaluation.json");write(output/"run.json",receipt)
    print(json.dumps({"output":str(output/"heldout-evaluation.json"),"sha256":receipt["evaluation_sha256"],"aggregate":aggregate,"elapsed_seconds":result["elapsed_seconds"]}));return 0

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank-index",type=Path);parser.add_argument("--output",type=Path)
    parser.add_argument("--child",action="store_true");parser.add_argument("--input",type=Path);parser.add_argument("--target",type=Path);parser.add_argument("--identity")
    args=parser.parse_args()
    try:
        if args.child:child(args.input,args.target,args.identity);return 0
        if not args.bank_index or not args.output:parser.error("bank-index and output required")
        return runner(args.bank_index,args.output.resolve())
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as exc:
        if args.output and args.output.is_dir():write(args.output/"failure.json",{"status":"partial_or_rejected_no_adoption","reason":str(exc)})
        print(f"held-out runner: {exc}",file=sys.stderr);return 1

if __name__=="__main__":raise SystemExit(main())
