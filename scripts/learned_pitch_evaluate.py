#!/usr/bin/env python3
"""Bounded generated-reference learned-pitch artifact evaluation; no inference."""
from __future__ import annotations

import argparse
import ast
from collections import Counter, deque, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import struct
import sys
import time
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("published_pitch_evaluator", ROOT/"scripts/pitch_evaluate.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
require, number = base.require, base.number
RATE, HOP, WINDOW, STEP = 22050, 256, 43844, 36164
MODEL = "2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec"
DECODER = "project_threshold_active_runs_with_local_model_onset_splits"
NAMES = {"note":88,"onset":88,"contour":264,"model_times_seconds":None,
         "nominal_times_seconds":None,"input_window_projection_seconds":None,
         "window_index":None,"window_frame_index":None}
MAX_RAW = 20*1024**2
MAX_EVENTS = 5000


def model_time(index):
    return index*HOP/RATE-math.floor(index/172)*(HOP/RATE*(172-WINDOW/HOP)+.0018)


def projection_time(index):
    return ((index//142)*STEP-3840+(index%142+15)*HOP)/RATE


def unsupported_claims(receipt):
    flags={item["path"]:item for item in base.unsupported_claims(receipt)}
    pending=[("",receipt)]
    while pending:
        path,value=pending.pop()
        if isinstance(value,dict):
            for key,item in value.items():
                here=f"{path}/{key}"
                if key in ("intended_note","performance_issue","identified_fret") and item is not None:
                    flags[here]={"path":here,"kind":"unsupported_real_note_or_performance_claim"}
                if isinstance(item,(dict,list)):pending.append((here,item))
        elif isinstance(value,list):
            pending.extend((f"{path}/{i}",item) for i,item in enumerate(value) if isinstance(item,(dict,list)))
    return list(flags.values())


def read_npy(raw):
    require(raw.startswith(b"\x93NUMPY") and len(raw)>=10, "invalid_npy_magic")
    version = tuple(raw[6:8])
    require(version in ((1,0),(2,0)), "unsupported_npy_version")
    size = 2 if version==(1,0) else 4
    header_size = int.from_bytes(raw[8:8+size],"little")
    require(0<header_size<=4096 and len(raw)>=8+size+header_size, "npy_header_bound")
    header_raw = raw[8+size:8+size+header_size]
    # Dtypes/shapes are literal scalar/tuple metadata, never executable objects.
    require(header_raw.count(b"(")<=4 and header_raw.count(b"[")<=4, "npy_header_depth")
    try:
        header = ast.literal_eval(header_raw.decode("latin1").strip())
    except (ValueError,SyntaxError,RecursionError) as exc:
        raise base.EvaluationError("invalid_npy_header") from exc
    require(isinstance(header,dict) and set(header)=={"descr","fortran_order","shape"}
            and header["fortran_order"] is False, "npy_header_schema")
    dtype = header["descr"]
    formats = {"<f4":("f",4),"<f8":("d",8),"<i4":("i",4),"<i8":("q",8)}
    require(isinstance(dtype,str) and dtype in formats, "npy_dtype_not_allowed")
    shape = header["shape"]
    require(isinstance(shape,tuple) and 1<=len(shape)<=2
            and all(type(n) is int and 0<n<=3000 for n in shape), "npy_shape_bound")
    count = math.prod(shape)
    fmt,width = formats[dtype]
    payload = raw[8+size+header_size:]
    require(len(payload)==count*width and len(payload)<=MAX_RAW, "npy_payload_extent")
    values = [item[0] for item in struct.iter_unpack("<"+fmt,payload)]
    require(all(math.isfinite(x) for x in values), "nonfinite_array")
    return {"shape":shape,"dtype":dtype,"values":values,"bytes":len(payload)}


def read_npz(path, expected_hash, frames):
    raw,digest = base.read_bytes(path,100*1024**2,expected_hash)
    expected = {f"excerpt_0_{name}.npy" for name in NAMES}
    arrays,total = {},0
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            require(len(members)==8 and {m.filename for m in members}==expected,
                    "npz_members_required")
            require(len({m.filename for m in members})==len(members), "npz_duplicate_member")
            require(sum(m.file_size for m in members)<=MAX_RAW+8*4096, "npz_uncompressed_bound")
            for member in members:
                require(member.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED)
                        and not member.flag_bits&1 and member.file_size<=MAX_RAW+4096
                        and not ((member.external_attr>>16)&0o170000)==0o120000, "unsafe_npz_member")
                with archive.open(member) as handle:
                    unpacked = handle.read(member.file_size+1)
                require(len(unpacked)==member.file_size, "npz_member_extent")
                name = member.filename[len("excerpt_0_"):-4]
                item = read_npy(unpacked)
                expected_shape = (frames,NAMES[name]) if NAMES[name] else (frames,)
                require(item["shape"]==expected_shape, "array_shape_mismatch")
                require(item["dtype"] in (("<i4","<i8") if name in ("window_index","window_frame_index")
                                         else ("<f4","<f8")), "array_dtype_mismatch")
                if NAMES[name]:
                    require(all(0<=value<=1 for value in item["values"]), "activation_outside_unit_interval")
                arrays[name] = item
                total += item["bytes"]
    except (zipfile.BadZipFile,RuntimeError,EOFError,zlib.error) as exc:
        raise base.EvaluationError("invalid_npz_archive") from exc
    require(total<=MAX_RAW, "npz_raw_array_bound")
    return arrays,digest,total


def row(arrays,name,index):
    width = NAMES[name]
    values = arrays[name]["values"]
    return values[index*width:(index+1)*width] if width else values[index]


def validate_clocks(arrays,excerpt):
    n = excerpt["retained_frames"]
    windows = excerpt["model_input_windows"]
    count = math.ceil((excerpt["sample_count"]+3840)/STEP)
    require(isinstance(windows,list) and len(windows)==count<=24, "model_window_count")
    for index,window in enumerate(windows):
        first=index*STEP-3840
        expected={"window_index":index,"padded_start_sample":index*STEP,"unpadded_start_sample":first,
            "leading_zero_samples":max(0,-first),"trailing_zero_samples":max(0,first+WINDOW-excerpt["sample_count"]),
            "output_frames_before_crop":172,"cropped_frames_each_side":15,"retained_frames":142}
        require(all(window.get(k)==v for k,v in expected.items()), "window_mapping_mismatch")
        require(abs(number(window["input_context_start_seconds_in_excerpt"])-max(0,first)/RATE)<1e-10
                and abs(number(window["input_context_end_seconds_in_excerpt"])-min(excerpt["sample_count"],first+WINDOW)/RATE)<1e-10,
                "window_context_extent_mismatch")
    for i in range(n):
        require(abs(row(arrays,"nominal_times_seconds",i)-i*HOP/RATE)<1e-10
                and abs(row(arrays,"model_times_seconds",i)-model_time(i))<1e-10
                and abs(row(arrays,"input_window_projection_seconds",i)-projection_time(i))<1e-10,
                "array_clock_mismatch")
        require(row(arrays,"window_index",i)==i//142 and row(arrays,"window_frame_index",i)==i%142+15,
                "array_window_index_mismatch")
    return windows


def validate_comparison(receipt,index,job,duration,arrays):
    require(receipt.get("schema_version")==1 and receipt.get("status")=="experimental_official_model_project_decoder",
            "unsupported_comparison_schema")
    bindings={"analysis_input_sha256":job["input_sha256"],"model_sha256":index["model_sha256"],
              "worker_sha256":index["adapter_sha256"],"wheel_manifest_sha256":index["runtime_manifest_sha256"],
              "tuning_registry_sha256":index["instrument_registry_sha256"],"raw_activations_sha256":job["activations_sha256"]}
    require(all(receipt.get(k)==v for k,v in bindings.items()), "learned_receipt_binding_mismatch")
    require(receipt.get("providers")==["CPUExecutionProvider"] and receipt.get("upstream_decoder_parity") is False,
            "learned_provider_or_parity_mismatch")
    settings=receipt["settings"]
    require(settings.get("decoder")==DECODER and settings.get("minimum_note_length_ms_presets")==[127.7,25.]
            and settings.get("frame_threshold")==.3 and settings.get("onset_threshold")==.5,
            "fixed_learned_settings_required")
    require(settings.get("start_seconds")==0 and settings.get("max_analysis_seconds")==duration, "learned_requested_coverage")
    require(number(receipt.get("coverage_seconds"))==duration, "learned_coverage_seconds")
    excerpts=receipt["excerpts"]
    require(isinstance(excerpts,list) and len(excerpts)==1, "learned_exact_excerpt_required")
    e=excerpts[0]
    require(e.get("start_seconds")==0 and e.get("end_seconds")==duration and e.get("sample_rate")==RATE
            and e.get("sample_count")==round(duration*RATE) and e.get("retained_frames")==math.floor(duration*86),
            "learned_excerpt_extent_mismatch")
    validate_clocks(arrays,e)
    require(receipt.get("model_windows")==len(e["model_input_windows"]), "learned_total_windows")
    number(receipt.get("peak_rss_bytes"),1,1024**3)
    number(receipt.get("elapsed_seconds"),0,600)
    require(receipt.get("raw_array_bytes")==sum(a["bytes"] for a in arrays.values()), "learned_raw_byte_count")
    variants=e["variants"]
    require(isinstance(variants,list) and len(variants)==2 and {v["minimum_note_length_ms"] for v in variants}=={127.7,25.},
            "learned_presets_required")
    for variant in variants:
        events=variant["events"]
        require(isinstance(events,list) and len(events)==variant["event_count"]<=MAX_EVENTS, "learned_event_bound")
        for event in events:
            a,b=event["start_frame"],event["end_frame_exclusive"]
            require(type(a) is int and type(b) is int and 0<=a<b<=e["retained_frames"], "event_frame_extent")
            require(type(event["midi_candidate"]) is int and 21<=event["midi_candidate"]<=108, "event_pitch_range")
            require(type(event.get("touches_excerpt_boundary")) is bool
                    and event["touches_excerpt_boundary"]==(a==0 or b==e["retained_frames"]), "event_boundary_flag")
            for name,value in (("model_start_seconds",model_time(a)),("model_end_seconds",model_time(b)),
                               ("nominal_start_seconds",a*HOP/RATE),("nominal_end_seconds",b*HOP/RATE),
                               ("input_window_projection_start_seconds",projection_time(a)),
                               ("input_window_projection_end_seconds",projection_time(b) if b<e["retained_frames"] else projection_time(b-1)+HOP/RATE)):
                require(abs(number(event[name])-value)<1e-10, "event_clock_mismatch")
            require(model_time(b)-model_time(a)>=variant["minimum_note_length_ms"]/1000, "event_below_project_duration_floor")
            clipped_end=min(duration,model_time(b))
            require(abs(number(event["audio_relative_start_seconds"])-model_time(a))<1e-10
                    and abs(number(event["audio_relative_end_seconds"])-clipped_end)<1e-10
                    and abs(number(event["source_start_seconds"])-model_time(a))<1e-10
                    and abs(number(event["source_end_seconds"])-clipped_end)<1e-10, "event_source_axis_mismatch")
            for name in ("mean_note_activation","maximum_onset_activation"):
                number(event[name],0,1)
        # Validate the supplied project event list against the immutable arrays.
        expected=[]
        for pitch in range(88):
            beginning=None
            for i in range(e["retained_frames"]+1):
                active=i<e["retained_frames"] and row(arrays,"note",i)[pitch]>=.3
                split=(active and beginning is not None and i>beginning and 0<i<e["retained_frames"]-1
                       and row(arrays,"onset",i)[pitch]>=.5
                       and row(arrays,"onset",i)[pitch]>row(arrays,"onset",i-1)[pitch]
                       and row(arrays,"onset",i)[pitch]>row(arrays,"onset",i+1)[pitch])
                if beginning is not None and (not active or split):
                    if model_time(i)-model_time(beginning)>=variant["minimum_note_length_ms"]/1000:
                        expected.append((beginning,i,pitch+21))
                    beginning=i if split else None
                if active and beginning is None:beginning=i
        actual=[(v["start_frame"],v["end_frame_exclusive"],v["midi_candidate"]) for v in events]
        require(sorted(actual)==sorted(expected), "event_decoder_array_mismatch")
        for event in events:
            a,b=event["start_frame"],event["end_frame_exclusive"]
            pitch=event["midi_candidate"]-21
            note_values=arrays["note"]["values"][a*88+pitch:b*88+pitch:88]
            onset_values=arrays["onset"]["values"][a*88+pitch:b*88+pitch:88]
            require(abs(event["mean_note_activation"]-sum(note_values)/(b-a))<=1e-7
                    and abs(event["maximum_onset_activation"]-max(onset_values))<=1e-7,
                    "event_activation_array_mismatch")
    return e


def best_matching(left,right,eligible,cost):
    """Min-cost maximum bipartite matching, stable insertion order for ties."""
    n,m=len(left),len(right)
    graph=[[] for _ in range(n+m+2)]
    source,target=n+m,n+m+1
    def add(a,b,value):
        graph[a].append([b,len(graph[b]),1,value])
        graph[b].append([a,len(graph[a])-1,0,-value])
    for i in range(n):add(source,i,0.)
    for j in range(m):add(n+j,target,0.)
    for i,a in enumerate(left):
        for j,b in enumerate(right):
            if eligible(a,b):add(i,n+j,cost(a,b))
    while True:
        distance=[float("inf")]*len(graph);distance[source]=0.;previous=[None]*len(graph)
        queue=deque([source]);queued={source}
        while queue:
            u=queue.popleft();queued.remove(u)
            for k,edge in enumerate(graph[u]):
                v,_,capacity,value=edge
                if capacity and distance[u]+value<distance[v]-1e-12:
                    distance[v]=distance[u]+value;previous[v]=(u,k)
                    if v not in queued:queue.append(v);queued.add(v)
        if previous[target] is None:break
        v=target
        while v!=source:
            u,k=previous[v];edge=graph[u][k];edge[2]=0;graph[v][edge[1]][2]=1;v=u
    return [(i,edge[0]-n) for i in range(n) for edge in graph[i] if n<=edge[0]<n+m and edge[2]==0]


def metric_rows(arrays,e,segments,clock="model_times_seconds",native=True):
    rows=[]
    for i in range(e["retained_frames"]):
        t=row(arrays,clock,i);values=row(arrays,"note",i)
        best=max(range(88),key=lambda k:(values[k],-k));voiced=values[best]>=.3
        window=e["model_input_windows"][i//142]
        frame={"audio_relative_seconds":t,"frequency_hz":440*2**((best+21-69)/12) if voiced else None,"voiced":voiced,
            "edge_context_complete":not native or not (window["leading_zero_samples"] or window["trailing_zero_samples"]),
            "window_start_seconds_audio_relative":window["input_context_start_seconds_in_excerpt"] if native else t,
            "window_end_seconds_audio_relative":window["input_context_end_seconds_in_excerpt"] if native else t}
        item=base.classify_frame(frame,{"minimum_hz":27.5,"maximum_hz":440*2**((108-69)/12)},segments,48000)
        if native and not frame["edge_context_complete"]:item["context"]="input_padding"
        rows.append({"frame_index":i,"clock":clock,"audio_relative_seconds":t,"estimated_frequency_hz":frame["frequency_hz"],
                     "maximum_note_activation":values[best],"voicing_probability":None,**item})
    return rows


def polyphonic_counts(arrays,e,segments,clock="model_times_seconds"):
    counts=Counter()
    for i in range(e["retained_frames"]):
        t=row(arrays,clock,i);sample=round(t*48000)
        segment=next((s for s in segments if s["start_native_sample"]<=sample<s["end_native_sample"]),None)
        if segment is None:continue
        reference=base.frequencies_at(segment,sample,48000)
        estimates=[440*2**((k+21-69)/12) for k,value in enumerate(row(arrays,"note",i)) if value>=.3]
        pairs=best_matching(reference,estimates,lambda a,b:abs(base.cents(b,a))<=50,lambda a,b:abs(base.cents(b,a)))
        cohort="polyphonic" if len(reference)>1 else "guitar_absent" if not reference else "monophonic"
        counts[cohort+"_frames"]+=1
        for key,value in (("tp",len(pairs)),("fp",len(estimates)-len(pairs)),("fn",len(reference)-len(pairs)),
                          ("absolute_cardinality_error",abs(len(reference)-len(estimates)))):
            counts[cohort+"_"+key]+=value
    return dict(counts)


def reference_events(truth,duration):
    score=truth.get("generated_score")
    require(isinstance(score,dict) and isinstance(score.get("events"),list) and len(score["events"])<=512,
            "generated_score_events_required")
    result=[]
    seen=set()
    for event in score["events"]:
        require(isinstance(event.get("id"),str) and event["id"] not in seen, "score_event_id")
        seen.add(event["id"])
        start=number(event["onset_source_seconds"],0)
        sample=event["onset_native_sample"];length=event["duration_samples"]
        require(type(sample) is int and type(length) is int and length>0 and sample==round(start*48000), "score_native_time")
        end=start+length/48000
        require(end<=truth["source"]["duration_seconds"]+1/48000, "score_extent")
        pitches=event["frequencies_hz"]
        require(isinstance(pitches,list) and 1<=len(pitches)<=9, "score_pitch_set")
        for voice,hz in enumerate(pitches):
            hz=number(hz,1,24000)
            if start<duration:
                result.append({"id":event["id"]+f"/voice-{voice}","start":start,"end":min(end,duration),"frequency":hz,
                    "unclipped_end":end,"boundary_truncated":end>duration,"articulation":event.get("articulation","unknown")})
    return result


def event_metrics(reference,events,offsets=False):
    boundary_count=sum(r["boundary_truncated"] for r in reference)
    excluded_ref=excluded_est=0
    if offsets:
        excluded_ref=sum(r["boundary_truncated"] for r in reference)
        reference=[r for r in reference if not r["boundary_truncated"]]
        excluded_est=sum(bool(e.get("touches_excerpt_boundary")) for e in events)
    predicted=[{"start":e["model_start_seconds"],"end":e["model_end_seconds"],"original_index":i,
                "touches_boundary":bool(e.get("touches_excerpt_boundary")),
                "frequency":440*2**((e["midi_candidate"]-69)/12)} for i,e in enumerate(events)
               if not offsets or not e.get("touches_excerpt_boundary")]
    def eligible(a,b):
        return abs(a["start"]-b["start"])<=.05 and abs(base.cents(b["frequency"],a["frequency"]))<=50 and (
            not offsets or abs(a["end"]-b["end"])<=max(.05,.2*(a["end"]-a["start"])))
    pairs=best_matching(reference,predicted,eligible,lambda a,b:abs(a["start"]-b["start"]))
    tp=len(pairs);fp=len(predicted)-tp;fn=len(reference)-tp
    return {"tp":tp,"fp":fp,"fn":fn,"precision":base.rate(tp,tp+fp),"recall":base.rate(tp,tp+fn),
            "f1":base.rate(2*tp,2*tp+fp+fn),"onset_residual_seconds":base.error_summary([predicted[j]["start"]-reference[i]["start"] for i,j in pairs]),
            "offset_residual_seconds":base.error_summary([predicted[j]["end"]-reference[i]["end"] for i,j in pairs
                if not reference[i]["boundary_truncated"] and not predicted[j]["touches_boundary"]]),
            "boundary_truncated_reference_count":boundary_count,"offset_excluded_reference_count":excluded_ref,
            "offset_excluded_estimate_count":excluded_est,
            "matched_reference_ids":[reference[i]["id"] for i,j in pairs],
            "matches":[{"reference_id":reference[i]["id"],"estimated_event_index":predicted[j]["original_index"],
                "reference_start_seconds":reference[i]["start"],"reference_end_seconds":reference[i]["end"],
                "estimated_start_seconds":predicted[j]["start"],"estimated_end_seconds":predicted[j]["end"],
                "onset_residual_seconds":predicted[j]["start"]-reference[i]["start"],
                "offset_residual_seconds":None if reference[i]["boundary_truncated"] or predicted[j]["touches_boundary"]
                                          else predicted[j]["end"]-reference[i]["end"],
                "boundary_truncated":reference[i]["boundary_truncated"],
                "estimated_touches_excerpt_boundary":predicted[j]["touches_boundary"]} for i,j in pairs],
            "unmatched_reference_ids":[r["id"] for i,r in enumerate(reference) if i not in {a for a,b in pairs}],
            "unmatched_estimated_indices":[predicted[j]["original_index"] for j in range(len(predicted)) if j not in {b for a,b in pairs}]}


def paired_rows(native_rows,pyin_branches):
    result=[]
    clocks=[row["audio_relative_seconds"] for row in native_rows]
    import bisect
    for branch in pyin_branches:
        pairs=[];unavailable=0
        for frame in branch["frames"]:
            t=frame["audio_relative_seconds"];position=bisect.bisect_left(clocks,t)
            options=[i for i in (position-1,position) if 0<=i<len(clocks)]
            selected=min(options,key=lambda i:(abs(clocks[i]-t),i)) if options else None
            if selected is None or abs(clocks[selected]-t)>HOP/RATE/2:
                unavailable+=1;continue
            rows=native_rows[selected]
            # Same timestamp pairing does not establish equivalent model support.
            pairs.append({"pyin_seconds":t,"learned_seconds":clocks[selected],
                          "learned_frame_index":selected,"learned_context":rows["context"],
                          "pyin_edge_context_complete":frame["edge_context_complete"],
                          "pyin_frequency_hz":frame["frequency_hz"],"learned_frequency_hz":rows["estimated_frequency_hz"]})
        both=[p for p in pairs if p["pyin_frequency_hz"] is not None and p["learned_frequency_hz"] is not None]
        result.append({"branch":branch["name"],"paired_count":len(pairs),"unavailable_count":unavailable,
                       "both_estimated_count":len(both),"estimator_cents_difference":base.error_summary([base.cents(p["learned_frequency_hz"],p["pyin_frequency_hz"]) for p in both]),
                       "complete_pyin_window_pairs":sum(p["pyin_edge_context_complete"] for p in pairs),
                       "complete_learned_input_pairs":sum(p["learned_context"]!="input_padding" for p in pairs),
                       "meaning":"timestamp_pairing_not_equal_resolution_or_note_correctness"})
    return result


def evaluate(fixture_index,pyin_index,learned_index):
    # Resolve repository-relative indices before using their parent directories
    # as the base for artifact references. Keep every existing path guard.
    fixture_index=base.safe_path(fixture_index)
    pyin_index=base.safe_path(pyin_index)
    learned_index=base.safe_path(learned_index)
    # Full published pYIN validator independently enforces bank/source/grid/truth contracts.
    pyin_result,_,_=base.evaluate(fixture_index,pyin_index)
    bank,bank_hash=base.read_json(base.safe_path(fixture_index))
    pyin,pyin_hash=base.read_json(base.safe_path(pyin_index))
    learned,learned_hash=base.read_json(base.safe_path(learned_index))
    identity={"bank_index_sha256":bank_hash,"instrument_registry_sha256":bank["instrument_registry_sha256"]}
    require(learned.get("schema_version")==1 and learned.get("budget_seconds")==30
            and all(learned.get(k)==v for k,v in identity.items()), "learned_index_binding_mismatch")
    for name in ("model_sha256","adapter_sha256","runtime_manifest_sha256"):base.fingerprint(learned[name])
    require(learned["model_sha256"]==MODEL, "unqualified_model_identity")
    jobs=learned["jobs"]
    require(isinstance(jobs,list) and len(jobs)==4 and {j["case_id"] for j in jobs}==set(base.PILOT), "fixed_learned_jobs_required")
    case_by_id={c["id"]:c for c in bank["cases"]};pyin_by_id={j["case_id"]:j for j in pyin["jobs"]}
    results=[];full_rows=[];total_windows=0;total_events=Counter();unsupported=[]
    for job in jobs:
        component,duration=base.PILOT[job["case_id"]]
        require(job.get("status")=="completed_measurements" and job.get("component")==component, "learned_job_status_or_component")
        pyin_job=pyin_by_id[job["case_id"]]
        require(job["input_sha256"]==pyin_job["input_sha256"] and job["truth_sha256"]==pyin_job["truth_sha256"], "switched_learned_input_or_truth")
        truth,truth_hash=base.read_json(base.safe_path(job["truth_path"],Path(learned_index).parent),expected_hash=job["truth_sha256"])
        source=base.validate_truth(truth,case_by_id[job["case_id"]])
        base.verify_wave(base.safe_path(job["input_path"],Path(learned_index).parent),job["input_sha256"],source)
        receipt,receipt_hash=base.read_json(base.safe_path(job["comparison_path"],Path(learned_index).parent),base.MAX_PITCH_JSON,job["comparison_sha256"])
        arrays,raw_hash,raw_bytes=read_npz(base.safe_path(job["activations_path"],Path(learned_index).parent),job["activations_sha256"],math.floor(duration*86))
        excerpt=validate_comparison(receipt,learned,job,duration,arrays)
        segments=base.reference_segments(truth)
        native=metric_rows(arrays,excerpt,segments)
        point=metric_rows(arrays,excerpt,segments,native=False)
        pyin_payload,_=base.read_json(base.safe_path(pyin_job["pitch_path"],Path(pyin_index).parent),base.MAX_PITCH_JSON,pyin_job["pitch_sha256"])
        references=reference_events(truth,duration)
        variants=[]
        for variant in excerpt["variants"]:
            events=variant["events"];minimum=variant["minimum_note_length_ms"]
            total_events[minimum]+=len(events)
            require(total_events[minimum]<=MAX_EVENTS, "global_learned_event_bound")
            onset_metrics=event_metrics(references,events)
            matched=set(onset_metrics["matched_reference_ids"])
            variants.append({"minimum_note_length_ms":minimum,"onset_only":onset_metrics,
                "onset_and_offset":event_metrics(references,events,True),
                "by_articulation_recall":{a:base.rate(sum(r["id"] in matched for r in references if r["articulation"]==a),
                    sum(r["articulation"]==a for r in references)) for a in sorted({r["articulation"] for r in references})},
                "event_count":len(events)})
        unsupported.extend({"case_id":job["case_id"],**flag} for flag in unsupported_claims(receipt))
        total_windows+=len(excerpt["model_input_windows"])
        views={clock:base.summarize_frames(metric_rows(arrays,excerpt,segments,clock,False))
               for clock in ("nominal_times_seconds","input_window_projection_seconds")}
        result={"case_id":job["case_id"],"component":component,"coverage_seconds":duration,
                "native_model_input_context":base.summarize_frames(native),"model_clock_pointwise":base.summarize_frames(point),
                "clock_sensitivity_pointwise":views,"polyphonic_set_pointwise_counts":polyphonic_counts(arrays,excerpt,segments),
                "paired_timestamps":paired_rows(native,pyin_payload["observations"]["analyzed_excerpts"][0]["branches"]),
                "event_presets":variants,"provenance":{"truth_sha256":truth_hash,"input_sha256":job["input_sha256"],
                    "comparison_sha256":receipt_hash,"activations_sha256":raw_hash,"raw_numeric_bytes":raw_bytes}}
        results.append(result)
        full_rows.extend({"case_id":job["case_id"],"component":component,"view":"native",**r} for r in native)
        full_rows.extend({"case_id":job["case_id"],"component":component,"view":"model_clock_pointwise",**r} for r in point)
    require(total_windows<=24 and all(n<=MAX_EVENTS for n in total_events.values()), "global_learned_resource_bound")
    failure_count=len(unsupported)+pyin_result["unsupported_claim_count"]
    alerts=[]
    for result in results:
        for view in ("native_model_input_context","model_clock_pointwise"):
            metrics=result[view]["stable_monophonic_metrics"]
            if metrics["raw_pitch_accuracy"]["denominator"]>=20 and metrics["raw_pitch_accuracy"]["value"]<.9:
                alerts.append({"case_id":result["case_id"],"view":view,"kind":"low_raw_pitch_accuracy",
                    "value":metrics["raw_pitch_accuracy"]["value"],"n":metrics["raw_pitch_accuracy"]["denominator"]})
            if metrics["voicing_false_alarm"]["numerator"]:
                alerts.append({"case_id":result["case_id"],"view":view,"kind":"guitar_absence_false_voicing",
                    "count":metrics["voicing_false_alarm"]["numerator"]})
    summary={"schema_version":1,"suite":"learned-pitch-calibration-v1",
        "status":"generated_fixture_calibration_failed_hard_gates" if failure_count else "completed_with_regression_alerts" if alerts else "completed_experimental_baseline",
        "hard_gates_passed":failure_count==0,"unsupported_claim_count":failure_count,"unsupported_claims":unsupported,
        "ground_truth_scope":"generator_only_not_musician","real_performance_grading":False,"listening_accepted":False,
        "source_audio_bytes_read":True,"source_audio_decoded":False,"raw_array_bytes_read":True,"inference_invoked":False,
        "bank_index_sha256":bank_hash,"pyin_pilot_index_sha256":pyin_hash,"learned_pilot_index_sha256":learned_hash,
        "instrument_registry_sha256":learned["instrument_registry_sha256"],"model_sha256":MODEL,
        "adapter_sha256":learned["adapter_sha256"],"runtime_manifest_sha256":learned["runtime_manifest_sha256"],
        "evaluator_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"created_at":datetime.now(timezone.utc).isoformat(),
        "case_count":4,"coverage_seconds":30,"model_windows":total_windows,"event_count_by_preset":dict(total_events),"cases":results,
        "quality_alerts":alerts,"event_decoder_recomputed":True,
        "aggregate_views":{view:base.summarize_frames([r for r in full_rows if r["view"]==view])
                           for view in ("native","model_clock_pointwise")},
        "pyin_baseline":{"frame_count":pyin_result["frame_count"],"cases":pyin_result["cases"],
            "aggregate_branches":pyin_result["aggregate_branches"],"quality_alerts":pyin_result["quality_alerts"]},
        "metric_policy":{"frame_threshold":.3,"pitch_tolerance_cents":50,"onset_tolerance_seconds":.05,
            "clock_selection_by_truth":False,"primary_clock":"upstream_empirical_model_clock_unqualified_physical_latency",
            "native_context":"whole_model_input_without_padding_inside_one_reference_region",
            "pointwise_context":"truth_at_audited_timestamp_not_whole_receptive_field_acceptance"},
        "limitations":["Generated labels are hash-bound supplied generator evidence, not measured real guitar notes.",
            "No automatic replacement or winner between pYIN and learned outputs is selected.",
            "Physical timing, musician correctness and model activation calibration remain unqualified."]}
    return summary,full_rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-index",required=True)
    parser.add_argument("--pyin-pilot-index",required=True)
    parser.add_argument("--learned-pilot-index",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--summary",action="store_true")
    args=parser.parse_args();started=time.monotonic()
    try:
        output=base.safe_path(args.output)
        require(output!=base.ALLOWED and not output.exists(),"new_output_directory_required")
        output.parent.mkdir(parents=True,exist_ok=True);output.mkdir(mode=0o700)
    except (base.EvaluationError,OSError) as exc:
        print(f"learned pitch evaluation: {exc}",file=sys.stderr);return 2
    code=0
    try:
        result,rows=evaluate(args.fixture_index,args.pyin_pilot_index,args.learned_pilot_index)
        code=0 if result["hard_gates_passed"] else 1
    except (base.EvaluationError,OSError,KeyError,TypeError,ValueError,AttributeError,struct.error) as exc:
        result={"schema_version":1,"suite":"learned-pitch-calibration-v1","status":"failed_structural","error":str(exc),
            "hard_gates_passed":False,"real_performance_grading":False,"listening_accepted":False,
            "source_audio_bytes_read":None,"source_audio_decoded":False,"raw_array_bytes_read":None,"inference_invoked":False}
        rows=[];code=1
    result["elapsed_seconds"]=time.monotonic()-started
    paths={"evaluation_json":str(output/"learned-pitch-calibration.json"),"frame_errors_csv":str(output/"learned-pitch-frame-errors.csv"),
           "event_errors_csv":str(output/"learned-pitch-event-errors.csv")}
    base.write_atomic(Path(paths["evaluation_json"]),json.dumps(result,indent=2,allow_nan=False)+"\n")
    base.write_csv(Path(paths["frame_errors_csv"]),rows,["case_id","component","view","frame_index","clock","audio_relative_seconds",
        "context","condition","reference_frequency_hz","estimated_frequency_hz","estimated_voiced","signed_cents","octave_error","maximum_note_activation"])
    event_rows=[]
    for case in result.get("cases",[]):
        for variant in case["event_presets"]:
            for name in ("onset_only","onset_and_offset"):
                metrics=variant[name]
                prefix={"case_id":case["case_id"],"minimum_note_length_ms":variant["minimum_note_length_ms"],"match_policy":name}
                event_rows.extend({**prefix,"status":"matched",**match} for match in metrics["matches"])
                event_rows.extend({**prefix,"status":"unmatched_reference","reference_id":id} for id in metrics["unmatched_reference_ids"])
                event_rows.extend({**prefix,"status":"unmatched_estimate","estimated_event_index":i} for i in metrics["unmatched_estimated_indices"])
    base.write_csv(Path(paths["event_errors_csv"]),event_rows,["case_id","minimum_note_length_ms","match_policy","status",
        "reference_id","estimated_event_index","reference_start_seconds","reference_end_seconds","estimated_start_seconds",
        "estimated_end_seconds","onset_residual_seconds","offset_residual_seconds","boundary_truncated","estimated_touches_excerpt_boundary"])
    compact={**paths,**{k:result.get(k) for k in ("status","hard_gates_passed","unsupported_claim_count","ground_truth_scope",
        "case_count","coverage_seconds","model_windows","event_count_by_preset","source_audio_bytes_read","source_audio_decoded",
        "raw_array_bytes_read","inference_invoked","real_performance_grading","listening_accepted","quality_alerts","error")}}
    print(json.dumps(compact if args.summary else {**result,**paths},allow_nan=False))
    if code:print(f"learned pitch evaluation: {result.get('error') or 'unsupported_confirmed_claims'}; retained {paths['evaluation_json']}",file=sys.stderr)
    return code


if __name__=="__main__":
    raise SystemExit(main())
