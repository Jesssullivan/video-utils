#!/usr/bin/env python3
"""Preregister local holdout metadata; full-bank execution needs root admission."""
from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import os
from pathlib import Path
import random
import stat
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "benchmarks"
SEEDS = (211, 307)
COHORTS = ("low32-sustain", "palm-muted-recurrence", "legato-recurrence",
           "c1-missing-fundamental", "timing-reference", "timing-errors")
RECIPE = "holdout-sha256-v1"
MAX_JSON = 1_000_000
ADMITTED_PLAN_SHA256 = "495ad2f3f553b0bd7030ac797b6e8589f37748df657219c075d0fc4ce7491e74"
DEPENDENCIES = ("scripts/benchmark.py", "scripts/benchmark_bank.py", "program/benchmarks.json",
                "program/benchmarks-v2.json", "program/instrument.json")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def knob_bytes(seed, cohort, knob):
    if seed not in SEEDS or cohort not in (*COHORTS, "timing-pair"):
        raise ValueError("Unregistered holdout seed or cohort")
    return hashlib.sha256(f"{RECIPE}:{seed}:{cohort}:{knob}".encode()).digest()


def parameters(seed, cohort):
    basis = "timing-pair" if cohort in ("timing-reference", "timing-errors") else cohort
    def integer(name):
        return int.from_bytes(knob_bytes(seed,basis,name)[:4],"big")
    def unit(name):
        return integer(name)/4294967296
    return {"first_motif_start_seconds":.6+.3*unit("phrase_phase"),
            "motif_duration_seconds":.8+1.2*unit("motif_duration"),
            "motif_gap_seconds":2.0+.8*unit("phrase_gap"),
            "guitar_gain":.65+.35*unit("guitar_gain"),
            "distortion_drive":2.6+2.0*unit("distortion_drive"),
            "noise_amplitude":.008+.008*unit("noise_amplitude"),
            "noise_lowpass_coefficient":.55+.30*unit("noise_color"),
            "click_amplitude":.06+.06*unit("click_amplitude"),
            "click_bpm":150+70*unit("click_bpm"),
            "click_phase_seconds":.2+.3*unit("click_phase"),
            "click_drift_fraction":.04+.08*unit("click_drift"),
            "motif_subdivision_denominator":(3,4,5,7)[integer("subdivision")%4],
            "noise_stream_seed":int.from_bytes(knob_bytes(seed,basis,"noise_stream")[:8],"big")}


def dependency_receipts():
    receipts = {}
    for name in DEPENDENCIES:
        path = ROOT/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_JSON:
            raise ValueError("Published holdout dependency is missing, unsafe or oversized")
        with path.open("rb") as stream:
            before=os.fstat(stream.fileno());raw=stream.read(MAX_JSON+1);after=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or len(raw)>MAX_JSON or (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
            raise ValueError("Published dependency changed or exceeded its byte bound")
        receipts[name] = sha(raw)
    return receipts


def make_plan():
    cases = [{"id":f"seed{seed}-{cohort}","seed":seed,"cohort":cohort,"duration_seconds":10,
              "parameters":parameters(seed,cohort),
              "reference_role":"generated_negative_no_declared_recurrence" if cohort in ("low32-sustain","c1-missing-fundamental") else "generated_positive_pair"}
             for seed in SEEDS for cohort in COHORTS]
    design = {"recipe_id":RECIPE,"seeds":list(SEEDS),"cohorts":list(COHORTS),"cases":cases,
              "comparison_arms":{"A":{"pulse_windows":[2,4,8,16],"cosine_threshold":.8,"candidate_cap":60},
                                 "B":{"contrast_minimum":.10,"ranked_pair_cap":10},
                                 "C":{"novelty_context_seconds":.2,"endpoint_search_cap_seconds":.75},
                                 "D":{"combines":["B","C"]}}}
    return {"schema_version":1,"kind":"preregistered_generated_holdout_plan","suite":"technical-holdout-v1",
            "role":"both_seeds_withheld_from_setting_selection","admission_status":"pending_root_admission",
            "ground_truth_scope":"generator_only_not_musician","design":design,"recipe_sha256":sha(canonical(design)),
            "sample_rate":48000,"channels":1,"sample_format":"pcm16","case_count":12,"total_duration_seconds":120,
            "bounds":{"max_case_seconds":10,"max_cases":12,"max_source_seconds":120,"math_threads":2,
                      "max_metadata_bytes":MAX_JSON,"proof_case_count":1,"proof_deadline_seconds":60},
            "published_dependencies":dependency_receipts(),"truth_supplied_to_discovery":False,
            "setting_selection_source":"previous_development_bank_only","full_generation_admitted":False,
            "listening_acceptance":"not_established","real_recording_labels":False}


def local_path(value, existing=False):
    path = Path(value).expanduser().absolute()
    if ".." in path.parts or not path.is_relative_to(ARTIFACTS) or path==ARTIFACTS:
        raise ValueError("Holdout artifacts must be children of artifacts/benchmarks")
    for parent in (path,*path.parents):
        if parent.is_symlink():
            raise ValueError("Holdout symlink components are rejected")
    if existing and (not path.is_file() or path.stat().st_size>MAX_JSON):
        raise ValueError("Holdout metadata must be a bounded regular file")
    return path


def object_pairs(pairs):
    value = {}
    for key,item in pairs:
        if key in value:
            raise ValueError("Duplicate holdout JSON key")
        value[key] = item
    return value


def validate_plan(path):
    path = local_path(path,True)
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        raw = stream.read(MAX_JSON+1)
        after = os.fstat(stream.fileno())
    if len(raw)>MAX_JSON or (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
        raise ValueError("Holdout metadata changed or exceeded its byte bound")
    value = json.loads(raw,object_pairs_hook=object_pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite holdout JSON")))
    if canonical(value) != canonical(make_plan()):
        raise ValueError("Holdout parameters, roles, bounds or dependencies differ from the preregistered recipe")
    return value,sha(raw)


def write_new(path,value):
    raw = canonical(value)+b"\n"
    if len(raw)>MAX_JSON:
        raise ValueError("Holdout metadata byte limit exceeded")
    path = local_path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as stream:
        stream.write(raw)
    return sha(raw)


def render_timing_case(case, deadline):
    """One generated score; no discovery, score selection or model calls."""
    cohort=case["cohort"]
    if cohort not in ("timing-errors","timing-reference","palm-muted-recurrence","legato-recurrence") or case["duration_seconds"] != 10:
        raise ValueError("Unregistered ten-second positive holdout case")
    rate, length = 48000, 480000
    p = case["parameters"]
    clean, click, noise = ([0.0]*length for _ in range(3))
    events, regions, click_events = [], [], []
    d = p["motif_subdivision_denominator"]
    positions = [0,d,2*d,3*d,3*d+1,3*d+2]
    starts = [p["first_motif_start_seconds"],p["first_motif_start_seconds"]+p["motif_duration_seconds"]+p["motif_gap_seconds"]]
    spans = []
    def check_deadline():
        if time.monotonic()>deadline:
            raise ValueError("Single-case proof deadline exceeded")
    def add_event(identity, ideal, actual, midi, edit=None, beat=None, phrase_end=None, support_end=None, articulation="picked_attack"):
        ideal_sample = round(ideal*rate)
        onset = None if actual is None else round(actual*rate)
        extent = round(.040*rate)
        if support_end is not None:
            extent=round(support_end*rate)-(ideal_sample if onset is None else onset)
        if phrase_end is not None:
            extent=min(extent,round(phrase_end*rate)-(ideal_sample if onset is None else onset))
        if extent<=0:
            raise ValueError("Generated attack has no support inside its declared phrase")
        row = {"id":identity,"ideal_onset_native_sample":ideal_sample,"ideal_onset_seconds":ideal_sample/rate,
               "ideal_analytic_onset_seconds":ideal,"onset_native_sample":onset,
               "onset_source_seconds":None if onset is None else onset/rate,"duration_samples":extent,
               "midi_notes":[midi],"frequencies_hz":[440*2**((midi-69)/12)],"articulation":articulation,
               "injected_edit":edit,"beat_position":beat}
        events.append(row)
        if onset is None:
            return
        if not 0<=onset<onset+extent<=length:
            raise ValueError("Generated attack escaped the native source extent")
        row["injected_offset_seconds"]=(onset-ideal_sample)/rate
        frequency = row["frequencies_hz"][0]
        for j in range(extent):
            age=j/rate
            envelope=min(1,j/((.008 if cohort=="legato-recurrence" else .0015)*rate),(extent-j)/(.006*rate))
            if cohort!="legato-recurrence":
                envelope*=math.exp(-age/.023)
            clean[onset+j]+=.17*p["guitar_gain"]*max(0,envelope)*math.tanh(p["distortion_drive"]*math.sin(2*math.pi*frequency*age))
        regions.append({"start_seconds":onset/rate,"end_seconds":(onset+extent)/rate,
                        "start_native_sample":onset,"end_native_sample":onset+extent,
                        "frequencies_hz":[frequency],"midi_notes":[midi],"monophonic":True,
                        "condition":"tanh_distorted","articulation":"legato_segment" if cohort=="legato-recurrence" else "palm_mute"})
    for group,start in enumerate(starts):
        spans.append([round(start*rate)/rate,round((start+p["motif_duration_seconds"])*rate)/rate])
        for step,slot in enumerate(positions):
            ideal=start+p["motif_duration_seconds"]*slot/(4*d)
            edit=None
            actual=ideal
            if group==1 and cohort=="timing-errors":
                if step==4:
                    edit,actual="omitted_attack",None
                elif step in (0,1,2,3):
                    actual+= (.025,-.025,.060,-.060)[step]
                    edit="injected_timing_shift"
            following=start+p["motif_duration_seconds"]*(positions[step+1]/(4*d) if step+1<len(positions) else 1)
            add_event(f"motif-{group}-{step}",ideal,actual,(24,29,34,29,24,39)[step],edit,
                      {"numerator":slot,"denominator":d},start+p["motif_duration_seconds"],
                      support_end=following if cohort=="legato-recurrence" else None,
                      articulation="pitch_transition" if cohort=="legato-recurrence" and step>0 else "picked_attack")
        if group==1 and cohort=="timing-errors":
            ideal=start+p["motif_duration_seconds"]*((positions[-1]/(4*d)+1)/2)
            add_event("extra-generated-attack",ideal,ideal,29,"extra_attack",phrase_end=start+p["motif_duration_seconds"])
        check_deadline()
    rng=random.Random(p["noise_stream_seed"])
    colored=0.0
    for index in range(length):
        white=rng.uniform(-1,1)
        colored=p["noise_lowpass_coefficient"]*colored+(1-p["noise_lowpass_coefficient"])*white
        noise[index]=p["noise_amplitude"]*(.5*white+.5*colored)
        if index%48000==0:
            check_deadline()
    at=p["click_phase_seconds"]
    while at+.009<10:
        native=round(at*rate)
        click_events.append({"id":f"click-{len(click_events)}","native_sample":native,"source_seconds":native/rate,
                             "analytic_seconds":at,"template_id":"independent-3500-exp"})
        for j in range(round(.009*rate)):
            age=j/rate
            click[native+j]+=p["click_amplitude"]*math.exp(-age/.0018)*math.sin(2*math.pi*3500*age)
        at+=60/p["click_bpm"]*(1+p["click_drift_fraction"]*at/10)
    mixed=[a+b+c for a,b,c in zip(clean,click,noise)]
    if max(abs(x) for x in mixed)>=.999:
        raise ValueError("Generated proof would clip; normalization is forbidden")
    a,b=spans
    truth={"schema_version":2,"kind":"synthetic_generated_signal_and_score_truth","ground_truth_scope":"generator_only_not_musician",
           "id":case["id"],"sample_rate":rate,"sample_count":length,"audio_start_seconds":0.0,
           "generated_score":{"events":events,"rounding":"nearest_native_sample","status":"complete_generated_score","attack_reference_known":True},
           "pitch_regions":regions,"pitch_trajectories":[],"phrase_spans_seconds":spans,
           "boundaries_seconds":sorted(t for span in spans for t in span),
           "recurrence_pairs":[{"id":"generated-repeat-1","first_span_seconds":a,"second_span_seconds":b,
             "warp_reference":{"source_times_seconds":a,"target_times_seconds":b,"source_offsets_seconds":[0,a[1]-a[0]],
                               "target_offsets_seconds":[0,b[1]-b[0]],"mapping_kind":"affine"}}],
           "guitar_onsets_seconds":sorted(row["onset_source_seconds"] for row in events if row["onset_source_seconds"] is not None and row["articulation"]=="picked_attack"),
           "click_events":click_events,"click_times_seconds":[row["source_seconds"] for row in click_events],
           "bpm":None,"pulse_reference_role":"independent_generated_click_not_motif_tempo",
           "intentional_subdivision_denominator":d,"parameters":p,"real_recording_labels":False,"listening_accepted":False}
    verify_timestamps(truth)
    check_deadline()
    return {"clean":clean,"click":click,"noise":noise,"mix":mixed},truth


def nuisance_components(p,deadline):
    rate,length=48000,480000
    click,noise=[0.0]*length,[0.0]*length
    rng=random.Random(p["noise_stream_seed"])
    colored=0.0
    for index in range(length):
        white=rng.uniform(-1,1)
        colored=p["noise_lowpass_coefficient"]*colored+(1-p["noise_lowpass_coefficient"])*white
        noise[index]=p["noise_amplitude"]*(.5*white+.5*colored)
        if index%48000==0 and time.monotonic()>deadline:
            raise ValueError("Holdout generation deadline exceeded")
    at=p["click_phase_seconds"]
    click_events=[]
    while at+.009<10:
        native=round(at*rate)
        click_events.append({"id":f"click-{len(click_events)}","native_sample":native,"source_seconds":native/rate,
                             "analytic_seconds":at,"template_id":"independent-3500-exp"})
        for j in range(round(.009*rate)):
            age=j/rate
            click[native+j]+=p["click_amplitude"]*math.exp(-age/.0018)*math.sin(2*math.pi*3500*age)
        at+=60/p["click_bpm"]*(1+p["click_drift_fraction"]*at/10)
    return click,noise,click_events


def render_negative_case(case,deadline):
    cohort=case["cohort"]
    if cohort not in ("low32-sustain","c1-missing-fundamental") or case["duration_seconds"]!=10:
        raise ValueError("Unregistered ten-second negative holdout case")
    p=case["parameters"]
    rate,length=48000,480000
    clean=[0.0]*length
    f0=32.0 if cohort=="low32-sustain" else 440*2**((24-69)/12)
    drive=p["distortion_drive"]/3.8
    harmonics=[{"index":k,"amplitude":a*p["guitar_gain"]*factor,"phase_radians":0.0}
               for k,a,factor in ((2,.13,1),(3,.08,drive),(4,.05,math.sqrt(drive)),(5,.04,1),(7,.02,1))]
    for native in range(24000,446400):
        age=(native-24000)/rate
        envelope=max(0,min(1,age/.01,(446400-native)/rate/.02))
        value=.19*p["guitar_gain"]*math.sin(2*math.pi*32*age) if cohort=="low32-sustain" else sum(h["amplitude"]*math.sin(2*math.pi*h["index"]*f0*age) for h in harmonics)
        clean[native]=envelope*value
        if native%48000==0 and time.monotonic()>deadline:
            raise ValueError("Holdout generation deadline exceeded")
    events=[]
    for n,at in enumerate((.4,9.45)):
        native=round(at*rate)
        for j in range(1920):
            age=j/rate
            clean[native+j]+=.02*p["guitar_gain"]*math.exp(-age/.003)*math.sin(2*math.pi*3500*age)
        events.append({"id":f"guitar-nuisance-{n}","ideal_onset_native_sample":native,"ideal_onset_seconds":native/rate,
                       "ideal_analytic_onset_seconds":at,"onset_native_sample":native,"onset_source_seconds":native/rate,
                       "duration_samples":1920,"midi_notes":[],"frequencies_hz":[3500],"articulation":"guitar_nuisance_transient",
                       "injected_edit":None,"beat_position":None,"injected_offset_seconds":0.0})
    click,noise,click_events=nuisance_components(p,deadline)
    mixed=[a+b+c for a,b,c in zip(clean,click,noise)]
    if max(abs(x) for x in mixed)>=.999:
        raise ValueError("Generated negative would clip; normalization is forbidden")
    truth={"schema_version":2,"kind":"synthetic_generated_signal_and_score_truth","ground_truth_scope":"generator_only_not_musician",
           "id":case["id"],"sample_rate":rate,"sample_count":length,"audio_start_seconds":0.0,"parameters":p,
           "generated_score":{"events":events,"rounding":"nearest_native_sample","status":"complete_generated_score","attack_reference_known":True},
           "pitch_regions":[{"start_seconds":.5,"end_seconds":9.3,"start_native_sample":24000,"end_native_sample":446400,
               "frequencies_hz":[f0],"midi_notes":[24] if cohort!="low32-sustain" else [],"monophonic":True,
               "condition":"pure_32hz_sine" if cohort=="low32-sustain" else "missing_fundamental_harmonic_proxy","articulation":"sustain"}],
           "pitch_trajectories":[],"phrase_spans_seconds":[],"boundaries_seconds":[],"recurrence_pairs":[],
           "recurrence_reference_role":"generated_negative_no_declared_recurrence","guitar_onsets_seconds":[],
           "click_events":click_events,"click_times_seconds":[row["source_seconds"] for row in click_events],"bpm":None,
           "pulse_reference_role":"independent_generated_click_not_motif_tempo","real_recording_labels":False,"listening_accepted":False}
    if cohort=="c1-missing-fundamental":
        truth["missing_fundamental"]={"frequency_hz":f0,"fundamental_coefficient":0.0,"harmonics":harmonics,
                                      "steady_interval_seconds":[1,7],"nonlinearity_after_synthesis":False}
    else:
        truth["low32_construction"]={"frequency_hz":32.0,"amplitude":.19*p["guitar_gain"],"steady_interval_seconds":[1,7],"distortion_applied":False}
    verify_timestamps(truth)
    return {"clean":clean,"click":click,"noise":noise,"mix":mixed},truth


def render_case(case,deadline):
    if case["cohort"] in ("low32-sustain","c1-missing-fundamental"):
        return render_negative_case(case,deadline)
    return render_timing_case(case,deadline)


def verify_timestamps(truth):
    rate,length=truth["sample_rate"],truth["sample_count"]
    if type(rate) is not int or rate!=48000 or type(length) is not int or length!=480000 or type(truth["audio_start_seconds"]) is not float or truth["audio_start_seconds"]!=0.0:
        raise ValueError("Proof native extent or generator sample-zero origin differs")
    ids=set()
    for row in truth["generated_score"]["events"]:
        if row["id"] in ids:
            raise ValueError("Duplicate generated event identity")
        ids.add(row["id"])
        if type(row["duration_samples"]) is not int or not 0<row["duration_samples"]<=96000:
            raise ValueError("Generated event duration exceeds two-second motif support")
        for key,seconds in (("ideal_onset_native_sample","ideal_onset_seconds"),("onset_native_sample","onset_source_seconds")):
            native=row[key]
            if native is None:
                if key!="onset_native_sample" or row[seconds] is not None or row["injected_edit"]!="omitted_attack":
                    raise ValueError("Null timestamp must denote an explicitly omitted attack")
            elif type(native) is not int or not 0<=native<length or type(row[seconds]) is not float or row[seconds]!=native/rate:
                raise ValueError("Generated native/source timestamp mismatch")
        if row["onset_native_sample"] is not None and row["onset_native_sample"]+row["duration_samples"]>length:
            raise ValueError("Generated event tail escaped source extent")
        if "ideal_analytic_onset_seconds" in row and round(row["ideal_analytic_onset_seconds"]*rate)!=row["ideal_onset_native_sample"]:
            raise ValueError("Generated analytic/native ideal onset differs")
        if row["onset_native_sample"] is not None and "injected_offset_seconds" in row and row["injected_offset_seconds"]!=(row["onset_native_sample"]-row["ideal_onset_native_sample"])/rate:
            raise ValueError("Injected offset differs from actual versus ideal native samples")
    previous=-1
    click_ids=set()
    for row in truth["click_events"]:
        if type(row["native_sample"]) is not int or not 0<=row["native_sample"]<length or type(row["source_seconds"]) is not float or row["source_seconds"]!=row["native_sample"]/rate:
            raise ValueError("Generated click/native timestamp mismatch")
        if row["native_sample"]<=previous or row["id"] in click_ids:
            raise ValueError("Generated clicks must have unique ordered native times and IDs")
        previous=row["native_sample"];click_ids.add(row["id"])
    for row in truth.get("pitch_regions",[]):
        first,last=row["start_native_sample"],row["end_native_sample"]
        if type(first) is not int or type(last) is not int or not 0<=first<last<=length or row["start_seconds"]!=first/rate or row["end_seconds"]!=last/rate:
            raise ValueError("Generated pitch region native/source extent differs")
    for start,end in truth["phrase_spans_seconds"]:
        if not 0<=start<end<=length/rate:
            raise ValueError("Generated phrase span escaped source extent")


def write_pcm(path,samples):
    if len(samples)!=480000 or any(not math.isfinite(x) or not -1<=x<1 for x in samples):
        raise ValueError("Proof PCM extent or amplitude invalid")
    data=array.array("h",(round(x*32768) for x in samples))
    if sys.byteorder!="little":
        data.byteswap()
    path=local_path(path)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as output:
        with wave.open(output,"wb") as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(48000)
            stream.writeframes(data.tobytes())


def verify_components(folder,truth):
    if truth["source"]!={**truth["components"]["mix"],"audio_start_seconds":0.0,
                         "origin_evidence":{"status":"known_generated_native_sample_zero","scope":"generated_file_only"}}:
        raise ValueError("Proof source receipt or generated origin is inconsistent with mixture")
    components={}
    for name,receipt in truth["components"].items():
        path=folder/receipt["path"]
        if Path(receipt["path"]).name!=receipt["path"]:
            raise ValueError("Proof component paths must be relative filenames")
        if (receipt["sample_rate"],receipt["channels"],receipt["sample_count"],receipt["duration_seconds"])!=(48000,1,480000,10):
            raise ValueError("Component receipt native extent differs")
        if path.is_symlink() or path.parent!=folder or not path.is_file() or path.stat().st_size!=960044 or sha(path.read_bytes())!=receipt["sha256"]:
            raise ValueError("Proof component path/hash mismatch")
        with wave.open(str(path),"rb") as stream:
            if (stream.getframerate(),stream.getnchannels(),stream.getsampwidth(),stream.getnframes())!=(48000,1,2,480000):
                raise ValueError("Proof component native header mismatch")
            data=array.array("h"); data.frombytes(stream.readframes(480000))
        if sys.byteorder!="little":
            data.byteswap()
        components[name]=data
    if set(components)!={"clean","click","noise","mix"}:
        raise ValueError("Proof requires all four components")
    error=max(abs(m-a-b-c) for m,a,b,c in zip(components["mix"],components["clean"],components["click"],components["noise"]))
    if error>2:
        raise ValueError("Rendered mixture differs from components beyond two PCM16 LSB")
    verify_timestamps(truth)
    return {"component_count":4,"native_frames_each":480000,"max_mix_error_pcm16_lsb":error,
            "component_hashes_verified":True,"native_timestamps_verified":True}


def rendered_construction_checks(folder,truth,dependencies):
    if "missing_fundamental" not in truth and "low32_construction" not in truth:
        return {}
    with wave.open(str(folder/"clean.wav"),"rb") as stream:
        data=array.array("h");data.frombytes(stream.readframes(480000))
    if sys.byteorder!="little":
        data.byteswap()
    if "missing_fundamental" in truth:
        path=ROOT/"scripts/benchmark_bank.py"
        raw=path.read_bytes()
        if sha(raw)!=dependencies["scripts/benchmark_bank.py"]:
            raise ValueError("Frozen independent harmonic verifier changed")
        namespace={"__file__":str(path),"__name__":"_holdout_frozen_harmonic_verifier"}
        exec(compile(raw,str(path),"exec"),namespace)
        result=namespace["verify_missing_render"]([x/32768 for x in data],48000,truth)
        return {"rendered_missing_fundamental_verification":result}
    specification=truth["low32_construction"]
    first,last=48000,336000
    coefficient=2*sum((data[i]/32768)*math.sin(2*math.pi*32*i/48000) for i in range(first,last))/(last-first)
    if abs(coefficient-specification["amplitude"])>5e-5:
        raise ValueError("Rendered generated 32Hz construction coefficient differs")
    return {"rendered_low32_verification":{"status":"verified_generated_clean_32hz_coefficient","measured_amplitude":coefficient,
                "absolute_tolerance":5e-5,"scope":"generated_clean_component_only","nonlinearity_applied":False}}


def generation_budget(plan,timeout_seconds):
    if type(timeout_seconds) is not int or not 0<timeout_seconds<=600:
        raise ValueError("Holdout generation timeout must be an integer in1..600seconds")
    cases=plan["design"]["cases"]
    expected=[f"seed{seed}-{cohort}" for seed in SEEDS for cohort in COHORTS]
    if len(cases)!=12 or [row["id"] for row in cases]!=expected or any(type(row["duration_seconds"]) is not int or row["duration_seconds"]!=10 for row in cases):
        raise ValueError("Holdout generation requires exactly twelve registered ten-second cases")
    if sum(row["duration_seconds"] for row in cases)!=120 or plan["sample_rate"]!=48000 or plan["channels"]!=1:
        raise ValueError("Holdout native extent or total source budget differs")
    return time.monotonic()+timeout_seconds


def save_case(output,case,signals,truth,plan,plan_hash,dependencies,worker_hash,deadline):
    if truth["id"]!=case["id"] or truth["ground_truth_scope"]!="generator_only_not_musician" or set(signals)!={"clean","click","noise","mix"}:
        raise ValueError("Rendered case identity, scope or components differ")
    directory=local_path(output/case["id"])
    directory.mkdir(mode=0o700)
    receipts={}
    for name,samples in signals.items():
        if time.monotonic()>deadline:
            raise ValueError("Holdout generation deadline exceeded")
        path=directory/f"{name}.wav"
        write_pcm(path,samples)
        receipts[name]={"path":path.name,"sha256":sha(path.read_bytes()),"bytes":path.stat().st_size,
                        "sample_rate":48000,"channels":1,"sample_count":480000,"duration_seconds":10}
    truth.update(components=receipts,source=dict(receipts["mix"],audio_start_seconds=0.0,
                  origin_evidence={"status":"known_generated_native_sample_zero","scope":"generated_file_only"}),
                 provenance={"plan_sha256":plan_hash,"recipe_sha256":plan["recipe_sha256"],"generator_sha256":worker_hash,
                             "published_dependencies":dependencies,"truth_supplied_to_discovery":False})
    checks=verify_components(directory,truth)
    truth.update(rendered_construction_checks(directory,truth,dependencies))
    # Per-case truth and aggregate receipts share the bank-index-relative basis.
    receipts={name:dict(receipt,path=f"{case['id']}/{receipt['path']}") for name,receipt in receipts.items()}
    truth["components"]=receipts
    truth["source"]=dict(receipts["mix"],audio_start_seconds=0.0,
                         origin_evidence={"status":"known_generated_native_sample_zero","scope":"generated_file_only"})
    truth_hash=write_new(directory/"truth.json",truth)
    if time.monotonic()>deadline:
        raise ValueError("Holdout generation deadline exceeded")
    return {"id":case["id"],"seed":case["seed"],"cohort":case["cohort"],"duration_seconds":10,
            "source":truth["source"],"components":receipts,"truth":{"path":f"{case['id']}/truth.json","sha256":truth_hash},
            "construction_checks":checks}


def aggregate_index(plan,plan_hash,worker_hash,cases,elapsed_seconds):
    generation_budget(plan,600)
    expected=[row["id"] for row in plan["design"]["cases"]]
    if [row["id"] for row in cases]!=expected or sum(row["duration_seconds"] for row in cases)!=120:
        raise ValueError("Incomplete or reordered holdout cases cannot produce a successful index")
    if any(set(row["components"])!={"clean","click","noise","mix"} for row in cases):
        raise ValueError("Aggregate index requires all48components")
    for definition,row in zip(plan["design"]["cases"],cases):
        if type(row["duration_seconds"]) is not int or row["duration_seconds"]!=10 or row["seed"]!=definition["seed"] or row["cohort"]!=definition["cohort"]:
            raise ValueError("Aggregate case source extent or recipe identity differs")
        if row["source"]!={**row["components"]["mix"],"audio_start_seconds":0.0,
                           "origin_evidence":{"status":"known_generated_native_sample_zero","scope":"generated_file_only"}}:
            raise ValueError("Aggregate source receipt or generator origin differs")
        for name,receipt in row["components"].items():
            if receipt["path"]!=f"{row['id']}/{name}.wav" or any(type(receipt[key]) is not int or receipt[key]!=value for key,value in (("bytes",960044),("sample_rate",48000),("channels",1),("sample_count",480000),("duration_seconds",10))):
                raise ValueError("Aggregate component path or native receipt differs")
            if not valid_digest(receipt["sha256"]):
                raise ValueError("Aggregate component hash is malformed")
        if row["truth"]["path"]!=f"{row['id']}/truth.json" or not valid_digest(row["truth"]["sha256"]):
            raise ValueError("Aggregate truth receipt path or hash differs")
    if not math.isfinite(elapsed_seconds) or not 0<=elapsed_seconds<=600:
        raise ValueError("Aggregate elapsed work exceeded its ceiling")
    return {"schema_version":2,"suite":"technical-holdout-v1","role":plan["role"],"plan_sha256":plan_hash,
            "recipe_sha256":plan["recipe_sha256"],"generator_sha256":worker_hash,"published_dependencies":plan["published_dependencies"],
            "instrument_registry_sha256":plan["published_dependencies"]["program/instrument.json"],
            "ground_truth_scope":"generator_only_not_musician","case_count":12,"total_duration_seconds":120,"cases":cases,
            "sample_rate":48000,"channels":1,"sample_format":"pcm16","wave_component_count":48,
            "max_wave_bytes":48*960044,"math_threads":1,"math_threads_ceiling":2,"elapsed_seconds":elapsed_seconds,
            "status":"passed_generated_construction_checks","inference_executed":False,"truth_supplied_to_discovery":False,
            "quality_metrics":"not_evaluated","listening_accepted":False,"real_recording_labels":False}


def valid_digest(value):
    return isinstance(value,str) and len(value)==64 and all(character in "0123456789abcdef" for character in value)


def generate(plan_path,output,timeout_seconds=600):
    started=time.monotonic()
    plan,plan_hash=validate_plan(plan_path)
    if plan_hash!=ADMITTED_PLAN_SHA256:
        raise ValueError("Generation requires the exact root-admitted metadata byte hash")
    deadline=generation_budget(plan,timeout_seconds)
    folder=local_path(output)
    if folder.exists():
        raise ValueError("Holdout generation output must be a new directory")
    dependencies=dependency_receipts()
    worker_hash=sha(Path(__file__).read_bytes())
    folder.mkdir(parents=True,mode=0o700)
    completed=[]
    try:
        for case in plan["design"]["cases"]:
            if time.monotonic()>deadline:
                raise ValueError("Holdout generation deadline exceeded")
            if dependencies!=dependency_receipts() or worker_hash!=sha(Path(__file__).read_bytes()):
                raise ValueError("Renderer or frozen dependencies changed during generation")
            signals,truth=render_case(case,deadline)
            row=save_case(folder,case,signals,truth,plan,plan_hash,dependencies,worker_hash,deadline)
            if dependencies!=dependency_receipts() or worker_hash!=sha(Path(__file__).read_bytes()):
                raise ValueError("Renderer or frozen dependencies changed during generation")
            completed.append(row)
            del signals,truth
        index=aggregate_index(plan,plan_hash,worker_hash,completed,time.monotonic()-started)
        index_hash=write_new(folder/"fixtures.json",index)
        return {"status":index["status"],"fixtures":str(folder/"fixtures.json"),"fixtures_sha256":index_hash,
                "plan_sha256":plan_hash,"recipe_sha256":plan["recipe_sha256"],"case_count":12,"total_duration_seconds":120,
                "wave_component_count":48,"elapsed_seconds":index["elapsed_seconds"],"inference_executed":False,"quality_metrics":"not_evaluated"}
    except Exception as exc:
        failure={"schema_version":1,"status":"failed_structural_generation","plan_sha256":plan_hash,"recipe_sha256":plan["recipe_sha256"],
                 "generator_sha256":worker_hash,"completed_case_count":len(completed),"completed_source_seconds":10*len(completed),
                 "completed_cases":[{"id":row["id"],"truth":row["truth"]} for row in completed],"error":str(exc)[:2000],
                 "inference_executed":False,"quality_metrics":"not_evaluated","successful_aggregate_index":False}
        write_new(folder/"failure.json",failure)
        raise


def proof(plan_path,case_id,output):
    plan,plan_hash=validate_plan(plan_path)
    if plan_hash!=ADMITTED_PLAN_SHA256:
        raise ValueError("Proof requires the exact root-admitted metadata byte hash")
    case=next((row for row in plan["design"]["cases"] if row["id"]==case_id),None)
    if case is None or case["cohort"]!="timing-errors":
        raise ValueError("Only a registered timing-errors proof is admitted")
    folder=local_path(output)
    if folder.exists():
        raise ValueError("Proof output must be a new directory")
    dependencies=dependency_receipts()
    worker_hash=sha(Path(__file__).read_bytes())
    deadline=time.monotonic()+60
    signals,truth=render_timing_case(case,deadline)
    folder.mkdir(parents=True,mode=0o700)
    receipts={}
    for name,samples in signals.items():
        if time.monotonic()>deadline:
            raise ValueError("Single-case proof deadline exceeded")
        path=folder/f"{name}.wav"
        write_pcm(path,samples)
        receipts[name]={"path":path.name,"sha256":sha(path.read_bytes()),"sample_rate":48000,"channels":1,"sample_count":480000,"duration_seconds":10}
    truth.update(components=receipts,source=dict(receipts["mix"],audio_start_seconds=0.0,
                  origin_evidence={"status":"known_generated_native_sample_zero","scope":"generated_file_only"}),
                 provenance={"plan_sha256":plan_hash,"recipe_sha256":plan["recipe_sha256"],"generator_sha256":worker_hash,
                             "published_dependencies":dependencies,"truth_supplied_to_discovery":False})
    checks=verify_components(folder,truth)
    if time.monotonic()>deadline:
        raise ValueError("Single-case proof deadline exceeded")
    truth_hash=write_new(folder/"truth.json",truth)
    if dependencies!=dependency_receipts() or worker_hash!=sha(Path(__file__).read_bytes()):
        raise ValueError("Generator or published dependencies changed during proof")
    index={"schema_version":2,"suite":"technical-holdout-v1","role":"single_case_construction_proof_not_inference",
           "plan_sha256":plan_hash,"recipe_sha256":plan["recipe_sha256"],"case_count":1,"total_duration_seconds":10,
           "cases":[{"id":case_id,"source":truth["source"],"components":receipts,"truth":{"path":"truth.json","sha256":truth_hash}}],
           "checks":checks,"status":"passed_generated_construction_checks","quality_metrics":"not_evaluated",
           "full_generation_admitted":False,"truth_supplied_to_discovery":False,"inference_executed":False}
    index_hash=write_new(folder/"fixtures.json",index)
    return {"status":index["status"],"fixtures":str(folder/"fixtures.json"),"fixtures_sha256":index_hash,
            "truth_sha256":truth_hash,"plan_sha256":plan_hash,"recipe_sha256":plan["recipe_sha256"],"case_id":case_id,
            "case_count":1,"total_duration_seconds":10,"checks":checks,"inference_executed":False,"full_generation_admitted":False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation",required=True)
    plan = sub.add_parser("plan",help="Print or save preregistered metadata only; never generate audio")
    plan.add_argument("--output",type=Path)
    validate = sub.add_parser("validate",help="Check metadata against the frozen recipe and dependencies")
    validate.add_argument("plan",type=Path)
    single=sub.add_parser("proof",help="Generate one admitted timing-errors construction proof; never run inference")
    single.add_argument("--plan",required=True,type=Path)
    single.add_argument("--case",required=True,choices=("seed211-timing-errors","seed307-timing-errors"))
    single.add_argument("--output",required=True,type=Path)
    full=sub.add_parser("generate",help="Generate the preregistered twelve-case bank only; never run inference")
    full.add_argument("--plan",required=True,type=Path)
    full.add_argument("--output",required=True,type=Path)
    full.add_argument("--timeout-seconds",type=int,default=600)
    args = parser.parse_args()
    try:
        if args.operation=="plan":
            value = make_plan()
            if args.output:
                digest = write_new(args.output,value)
                result = {"status":"metadata_plan_saved","path":str(args.output),"plan_sha256":digest,
                          "recipe_sha256":value["recipe_sha256"],"case_count":12,"total_duration_seconds":120,
                          "admission_status":"pending_root_admission","audio_generated":False}
            else:
                result = value
        elif args.operation=="validate":
            value,digest = validate_plan(args.plan)
            result = {"status":"metadata_plan_validated","plan_sha256":digest,"recipe_sha256":value["recipe_sha256"],
                      "case_count":12,"total_duration_seconds":120,"admission_status":"pending_root_admission",
                      "audio_generated":False,"full_generation_admitted":False}
        elif args.operation=="proof":
            result=proof(args.plan,args.case,args.output)
        else:
            result=generate(args.plan,args.output,args.timeout_seconds)
        print(json.dumps(result,indent=2,allow_nan=False))
        return 0
    except (OSError,ValueError,TypeError,KeyError,RecursionError) as exc:
        print(json.dumps({"status":"rejected","error":str(exc)}),file=sys.stderr)
        return 1


if __name__=="__main__":
    sys.exit(main())
