#!/usr/bin/env python3
"""Bounded synthetic restoration benchmarks; no real-media quality acceptance."""
from __future__ import annotations

import argparse
import array
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import signal
import statistics
import subprocess
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "program" / "benchmarks.json"


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def read_json(path: Path, limit=5_000_000):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Missing, symlinked or oversized benchmark JSON")
    return json.loads(path.read_text())


def write_json(path: Path, value):
    temporary = path.with_name(path.name + ".pending")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def configuration():
    config = read_json(CONFIG)
    if config.get("schema_version") != 1 or config.get("suite") != "technical-v1":
        raise ValueError("Unsupported benchmark suite")
    rate, duration = config.get("sample_rate"), config.get("duration_seconds")
    if rate != 48000 or duration != 8 or len(config.get("fixtures", [])) != 3:
        raise ValueError("technical-v1 requires three bounded 48 kHz eight-second fixtures")
    limits={"worker_timeout_seconds":120,"overall_timeout_seconds":600,"max_json_bytes":5_000_000,
            "max_worker_output_bytes":8_000_000,"max_decoded_bytes":2_000_000}
    for key,maximum in limits.items():
        value=config.get("bounds",{}).get(key)
        if isinstance(value,bool) or not isinstance(value,int) or not 0<value<=maximum:
            raise ValueError("Benchmark resource bounds exceed the supported ceiling")
    if not 20<=config.get("bpm",0)<=400:
        raise ValueError("Invalid fixture tempo")
    identifiers=set()
    for fixture in config["fixtures"]:
        identifier=fixture.get("id","")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}",identifier) or identifier in identifiers:
            raise ValueError("Invalid or duplicate fixture identifier")
        identifiers.add(identifier)
        if fixture.get("kind") not in ("sustain","palm_mute","legato") or not 20<=fixture.get("fundamental_hz",0)<=500:
            raise ValueError("Invalid fixture signal definition")
    return config


def destination(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    permitted = ROOT / "artifacts" / "benchmarks"
    if (ROOT/"artifacts").is_symlink() or permitted.is_symlink():
        raise ValueError("Benchmark artifact roots must not be symlinks")
    if not path.is_relative_to(permitted) or path == permitted:
        raise ValueError("Choose a new directory beneath artifacts/benchmarks/")
    if path.exists():
        raise ValueError("Benchmark output must not already exist")
    path.mkdir(parents=True, mode=0o700)
    return path


def pcm16(path: Path, samples, rate: int):
    frames = array.array("h", (round(max(-1.0, min(1 - 1/32768, x)) * 32768) for x in samples))
    if sys.byteorder != "little":
        frames.byteswap()
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames.tobytes())
    os.chmod(path, 0o600)


def read_pcm16(path: Path):
    with wave.open(str(path), "rb") as handle:
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2 or handle.getnframes() > 384000:
            raise ValueError("Expected bounded mono PCM16 fixture")
        rate = handle.getframerate()
        samples = array.array("h")
        samples.frombytes(handle.readframes(handle.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()
    return [x/32768 for x in samples], rate


def fixture_signals(definition, config):
    rate, duration = config["sample_rate"], config["duration_seconds"]
    length, period = round(rate * duration), 60/config["bpm"]
    rng = random.Random(config["seed"] + sum(definition["id"].encode()))
    noise = [rng.uniform(-0.012, 0.012) for _ in range(length)]
    clean, clicks = [0.0]*length, [0.0]*length
    click_times = [0.3 + i*period for i in range(int((duration-0.3)/period)+1)]
    for event in click_times:
        origin = round(event*rate)
        for offset in range(round(0.009*rate)):
            if origin+offset < length:
                seconds = offset/rate
                clicks[origin+offset] += 0.10*math.exp(-seconds/0.0018)*math.sin(2*math.pi*3500*seconds)
    regions = [(2.0, 2.0+4*period), (4.0, 4.0+4*period)]
    onset_truth = []
    kind = definition["kind"]
    frequency = definition["fundamental_hz"]
    for index in range(length):
        t = index/rate
        if kind == "sustain":
            if 1.3 <= t < 7.5:
                envelope = min(1.0, (t-1.3)/0.01, (7.5-t)/0.05)
                clean[index] = .16*max(0.0, envelope)*math.sin(2*math.pi*frequency*(t-1.3))
            continue
        region = next(((start,end) for start,end in regions if start <= t < end), None)
        if region is None:
            continue
        local = t-region[0]
        if kind == "palm_mute":
            # Repeated sixteenth-note pattern includes a rest and a sustained hit.
            step = period/4
            position = min(15, int(local/step))
            pattern = [1,1,0,1,1,0,1,1,1,1,0,0,1,0,1,1]
            if not pattern[position]:
                continue
            age = local-position*step
            envelope = min(1, age/.0015)*math.exp(-age/.024)
            oscillator = math.sin(2*math.pi*frequency*age)
            clean[index] = .19*envelope*math.tanh(3.8*oscillator)
        else:
            upper = definition["upper_frequency_hz"]
            # Continuous phase with cyclic, smooth legato pitch motion.
            mean, depth = (frequency+upper)/2, (upper-frequency)/2
            phase = 2*math.pi*(mean*local + depth*(1-math.cos(2*math.pi*local/period))*period/(2*math.pi))
            envelope = min(1, local/.015, (region[1]-t)/.04)
            clean[index] = .13*max(0,envelope)*math.tanh(2.4*math.sin(phase))
    if kind == "palm_mute":
        pattern = [1,1,0,1,1,0,1,1,1,1,0,0,1,0,1,1]
        onset_truth = [start+i*period/4 for start,_ in regions for i,active in enumerate(pattern) if active]
        # Add one independently labelled coincident attack to challenge click detection.
        collision = click_times[round((6.2-0.3)/period)]
        onset_truth.append(collision)
        for offset in range(round(.08*rate)):
            index = round(collision*rate)+offset
            if index < length:
                age=offset/rate
                clean[index] += .18*min(1,age/.001)*math.exp(-age/.022)*math.tanh(3.8*math.sin(2*math.pi*frequency*age))
    elif kind == "legato":
        onset_truth = [start for start,_ in regions]
    else:
        onset_truth = [1.3]
    mixed = [a+b+c for a,b,c in zip(clean,clicks,noise)]
    truth = {
        "schema_version":1, "kind":"synthetic_generated_component_truth", "sample_rate":rate,
        "sample_count":length, "audio_start_seconds":0.0,"bpm":config["bpm"], "fundamental_hz":frequency,
        "click_times_seconds":click_times, "guitar_onsets_seconds":onset_truth,
        "noise_only_intervals_seconds":[[0,.25]], "lf_measurement_interval_seconds":[2,6],
        "repeated_regions_seconds":[] if kind=="sustain" else [list(span) for span in regions],
        "click_only_template_seconds":[.299,.311],
        "limitations":config["limitations"], "listening_accepted":False,
    }
    return {"clean":clean,"click":clicks,"noise":noise,"mix":mixed}, truth


def create_fixtures(output: Path, config):
    cases=[]
    for definition in config["fixtures"]:
        directory=output/definition["id"]
        directory.mkdir(mode=0o700)
        signals,truth=fixture_signals(definition,config)
        artifacts={}
        for name,samples in signals.items():
            path=directory/f"{name}.wav"
            pcm16(path,samples,config["sample_rate"])
            artifacts[name]={"path":str(path.relative_to(output)),"sha256":digest(path),"bytes":path.stat().st_size}
        truth.update(id=definition["id"], artifacts=artifacts, generator_sha256=digest(Path(__file__)),
                     configuration_sha256=digest(CONFIG), random_generator="random.Random.uniform; exact output hashes recorded")
        write_json(directory/"truth.json",truth)
        cases.append({"id":definition["id"],"truth":str((directory/"truth.json").relative_to(output)),"truth_sha256":digest(directory/"truth.json")})
    index={"schema_version":1,"suite":config["suite"],"case_count":len(cases),"cases":cases,
           "generated_at":datetime.now(timezone.utc).isoformat(),"configuration_sha256":digest(CONFIG)}
    write_json(output/"fixtures.json",index)
    return index


def amplitude(samples, rate, frequency, interval):
    start,end=(round(x*rate) for x in interval)
    window=samples[start:end]
    if not window:
        raise ValueError("Empty amplitude measurement interval")
    sine=sum(x*math.sin(2*math.pi*frequency*(i+start)/rate) for i,x in enumerate(window))
    cosine=sum(x*math.cos(2*math.pi*frequency*(i+start)/rate) for i,x in enumerate(window))
    return 2*math.hypot(sine,cosine)/len(window)


def signal_metrics(reference, before, after, rate, truth):
    if len(reference)!=len(before) or len(before)!=len(after) or not reference:
        raise ValueError("PCM sample extent mismatch")
    if any(not math.isfinite(x) for stream in (reference,before,after) for x in stream):
        raise ValueError("Non-finite decoded PCM")
    energy=sum(x*x for x in reference)
    if energy<=0:
        raise ValueError("Synthetic clean reference has no energy")
    def error_metrics(stream):
        gain=sum(x*y for x,y in zip(reference,stream))/energy
        if not math.isfinite(gain) or abs(gain)<1e-9:
            return {"fitted_gain":gain,"gain_adjusted_mse":None,"gain_adjusted_sdr_db":None}
        mse=sum((y/gain-x)**2 for x,y in zip(reference,stream))/len(stream)
        return {"fitted_gain":gain,"gain_adjusted_mse":mse,
                "gain_adjusted_sdr_db":None if mse==0 else 10*math.log10(energy/len(reference)/mse)}
    previous,current=error_metrics(before),error_metrics(after)
    baseline_amplitude=amplitude(before,rate,truth["fundamental_hz"],truth["lf_measurement_interval_seconds"])
    final_amplitude=amplitude(after,rate,truth["fundamental_hz"],truth["lf_measurement_interval_seconds"])
    lf_delta=None if baseline_amplitude<1e-7 or final_amplitude<=0 else 20*math.log10(final_amplitude/baseline_amplitude)
    quiet=[]
    for start,end in truth["noise_only_intervals_seconds"]:
        old,new=before[round(start*rate):round(end*rate)],after[round(start*rate):round(end*rate)]
        old_rms=math.sqrt(sum(x*x for x in old)/len(old))
        # Separate a uniform gain change from quiet-region noise improvement.
        fitted_gain=current["fitted_gain"]/previous["fitted_gain"] if previous["fitted_gain"] else None
        new_rms=math.sqrt(sum(x*x for x in new)/len(new))
        adjusted=None if fitted_gain is None or abs(fitted_gain)<1e-9 else new_rms/abs(fitted_gain)
        quiet.append({"interval_seconds":[start,end],"before_rms":old_rms,"after_rms":new_rms,
                      "raw_noise_change_db":None if not new_rms or not old_rms else 20*math.log10(new_rms/old_rms),
                      "gain_adjusted_noise_change_db":None if not adjusted or not old_rms else 20*math.log10(adjusted/old_rms)})
    return {"sample_rate":rate,"sample_count":len(reference),"before":previous,"after":current,
            "coherent_fundamental_gain_db":lf_delta,"quiet_regions":quiet,
            "alignment":"unaltered sample index; no fitted delay or time correction",
            "gain_adjustment_warning":"Least-squares gain and waveform error are phase-sensitive; uncalibrated processing/detector delay can bias them. Raw quiet-region RMS and coherent LF gain are separate measurements.",
            "interpretation":"synthetic measurements only; no listening acceptance"}


def event_metrics(expected, observed, tolerance=.02):
    if not math.isfinite(tolerance) or tolerance<=0:
        raise ValueError("Event tolerance must be positive")
    if any(not math.isfinite(x) for x in [*expected,*observed]):
        raise ValueError("Event times must be finite")
    pairs=sorted((abs(b-a),i,j,b-a) for i,a in enumerate(expected) for j,b in enumerate(observed) if abs(b-a)<=tolerance)
    used_expected,used_observed,offsets=set(),set(),[]
    for _,i,j,offset in pairs:
        if i not in used_expected and j not in used_observed:
            used_expected.add(i); used_observed.add(j); offsets.append(offset)
    count=len(offsets)
    nearest=[b-min(expected,key=lambda a:abs(a-b)) for b in observed] if expected else []
    nearest=[offset for offset in nearest if abs(offset)<=.1]
    return {"expected_count":len(expected),"observed_count":len(observed),"matched_count":count,
            "precision":None if not observed else count/len(observed),
            "recall":None if not expected else count/len(expected),"false_positive_count":len(observed)-count,
            "missed_count":len(expected)-count,"signed_offsets_seconds":offsets,"tolerance_seconds":tolerance,
            "latency_calibration":"none","nearest_truth_median_offset_seconds":statistics.median(nearest) if nearest else None,
            "nearest_offset_window_seconds":.1,"interpretation":"timestamp matching does not prove causal click identity"}


def interval_iou(first,second):
    if len(first)!=2 or len(second)!=2 or any(not math.isfinite(x) for x in [*first,*second]) or first[1]<=first[0] or second[1]<=second[0]:
        raise ValueError("Invalid interval")
    overlap=max(0,min(first[1],second[1])-max(first[0],second[0]))
    return overlap/(max(first[1],second[1])-min(first[0],second[0]))


def recurrence_metrics(expected_regions,candidates):
    if len(expected_regions)!=2:
        return {"status":"no_expected_recurrence","candidate_count":len(candidates),"best_pair_overlap":None}
    scores=[]
    for item in candidates:
        first=[item["first_start_seconds"],item.get("first_end_seconds",item["first_start_seconds"]+item.get("duration_seconds",0))]
        second=[item["second_start_seconds"],item.get("second_end_seconds",item["second_start_seconds"]+item.get("duration_seconds",0))]
        if first[1]<=first[0] or second[1]<=second[0]:
            continue
        scores.append(min(interval_iou(expected_regions[0],first),interval_iou(expected_regions[1],second)))
    return {"status":"measured_candidates" if scores else "no_recurrence_candidates",
            "candidate_count":len(candidates),"best_pair_overlap":max(scores) if scores else 0.0,
            "overlap_definition":"minimum interval IoU across the first and second generated motif"}


def invoke(command, directory, timeout, max_bytes, receipt):
    stdout_path,stderr_path=directory/"worker.stdout",directory/"worker.stderr"
    started=time.monotonic()
    receipt.update(command=command,timeout_seconds=timeout,max_output_bytes=max_bytes)
    with stdout_path.open("wb") as stdout,stderr_path.open("wb") as stderr:
        worker_environment=dict(os.environ,OMP_NUM_THREADS="2",OPENBLAS_NUM_THREADS="2",MKL_NUM_THREADS="2",NUMBA_NUM_THREADS="2")
        receipt["math_threads"]=2
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True,env=worker_environment)
        stop_reason=None
        try:
            while process.poll() is None:
                if time.monotonic()-started>=timeout:
                    stop_reason="bounded worker deadline"
                    break
                if any(path.stat().st_size>max_bytes for path in (stdout_path,stderr_path)):
                    stop_reason="bounded worker output exceeded"
                    break
                try:
                    process.wait(timeout=min(.1,max(.001,timeout-(time.monotonic()-started))))
                except subprocess.TimeoutExpired:
                    continue
            if stop_reason is not None:
                raise subprocess.TimeoutExpired(command,timeout)
            code=process.wait()
        except subprocess.TimeoutExpired:
            # This process group was created by this invocation; inspect live state
            # before signalling its owned workers. Never target other sessions.
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL)
                    process.wait(timeout=3)
            receipt.update(status="bounded_worker_stopped", seconds=time.monotonic()-started,
                           process_receipt={"actor":"benchmark", "pid":process.pid,"target_ownership":"own launched worker process group", "reason":stop_reason or "bounded worker deadline", "ruling":"R-HOOK-CONVERGENCE-20261004/R-N11", "prior_state":"live child confirmed by poll", "result":"terminated"})
            raise ValueError(stop_reason or "Benchmark worker exceeded deadline")
    receipt.update(command=command,seconds=time.monotonic()-started,exit_code=code)
    if any(path.stat().st_size>max_bytes for path in (stdout_path,stderr_path)):
        raise ValueError("Benchmark worker output exceeded bound")
    if code:
        raise ValueError(f"Worker {Path(command[1]).name if len(command)>1 else command[0]} failed with exit {code}; local logs retained")
    receipt["status"]="completed"
    return json.loads(stdout_path.read_text())


def decode(path: Path, directory: Path, rate, config):
    command=[os.environ.get("FFMPEG","ffmpeg"),"-v","error","-nostdin","-threads","2","-i",str(path),
             "-map","0:a:0","-t",str(config["duration_seconds"]+.01),"-ac","1","-ar",str(rate),"-f","f32le","pipe:1"]
    response=subprocess.run(command,capture_output=True,timeout=30,check=True)
    if len(response.stdout)>config["bounds"]["max_decoded_bytes"] or len(response.stdout)%4:
        raise ValueError("Decoded PCM exceeds benchmark bound")
    samples=array.array("f"); samples.frombytes(response.stdout)
    if sys.byteorder!="little": samples.byteswap()
    return samples


def audit_artifact(path: Path, expected_hash: str):
    if path.is_symlink() or not path.is_file() or digest(path)!=expected_hash:
        raise ValueError("Benchmark artifact hash mismatch")
    return {"path":str(path),"sha256":expected_hash,"bytes":path.stat().st_size,"verified":True}


def evaluate_case(case, fixture_root: Path, output: Path, config, profile, backend, deadline):
    truth=read_json(fixture_root/case["truth"])
    if digest(fixture_root/case["truth"])!=case["truth_sha256"]:
        raise ValueError("Fixture truth hash mismatch")
    for artifact in truth["artifacts"].values():
        audit_artifact(fixture_root/artifact["path"],artifact["sha256"])
    directory=output/case["id"]; directory.mkdir(mode=0o700)
    result={"id":case["id"],"status":"running","stages":{},"artifacts":{},"metrics":{},"quality_alerts":[]}
    source=fixture_root/truth["artifacts"]["mix"]["path"]
    python=os.environ.get("VIDEO_UTILS_ANALYSIS_PYTHON",sys.executable) if backend=="librosa" else sys.executable
    def worker(name,script,args):
        stage=directory/name; stage.mkdir(mode=0o700)
        receipt={}; result["stages"][name]=receipt
        remaining=deadline-time.monotonic()
        if remaining<=0: raise ValueError("Overall benchmark deadline reached")
        script_path=ROOT/"scripts"/script
        receipt["worker_sha256"]=digest(script_path)
        (stage/"worker-source.py").write_bytes(script_path.read_bytes())
        if digest(stage/"worker-source.py")!=receipt["worker_sha256"]:
            raise ValueError("Worker source changed while snapshotting")
        try:
            value=invoke([python,str(script_path),*map(str,args)],stage,
                         min(config["bounds"]["worker_timeout_seconds"],remaining),config["bounds"]["max_worker_output_bytes"],receipt)
            if digest(script_path)!=receipt["worker_sha256"]:
                raise ValueError("Worker source changed during benchmark stage")
            return value
        finally:
            write_json(directory/"case.json",result)
    media=worker("restoration","media.py",["clean",source,profile])
    run=Path(media["run_dir"]); manifest=read_json(run/"manifest.json")
    if manifest["source"]["sha256"]!=truth["artifacts"]["mix"]["sha256"] or digest(source)!=manifest["source"]["sha256"]:
        raise ValueError("Restoration source lineage mismatch")
    pcm=manifest["pcm"]
    if (pcm["sample_rate"],pcm["channels"],pcm["sample_count"])!=(config["sample_rate"],1,truth["sample_count"]):
        raise ValueError("Restoration changed native PCM extent")
    result["media_run_dir"]=str(run)
    result["tools"]=manifest["tools"]
    result["profile_sha256"]=digest(ROOT/"profiles"/f"{profile}.json")
    for name,sha in manifest["output_sha256"].items():
        if name in ("source.wav","denoised.wav","cleaned.wav"):
            result["artifacts"][name]=audit_artifact(run/name,sha)
    original,_=read_pcm16(source)
    clean,_=read_pcm16(fixture_root/truth["artifacts"]["clean"]["path"])
    processed=decode(run/"denoised.wav",directory,config["sample_rate"],config)
    result["metrics"]["restoration"]=signal_metrics(clean,original,processed,config["sample_rate"],truth)
    lf=result["metrics"]["restoration"]["coherent_fundamental_gain_db"]
    if truth["id"]=="low32-sustain" and lf is not None and lf<config["metric_policy"]["low_frequency_alert_below_db"]:
        result["quality_alerts"].append({"kind":"synthetic_low32_attenuation","gain_db":lf})
    analysis_dir=directory/"analysis"; analysis_dir.mkdir(mode=0o700)
    # WAV carries no declared stream PTS. Only this generated fixture has a
    # known sample-zero origin. Preserve the worker's original manifest and
    # write a separate, explicit synthetic-origin assertion for analysis.
    analysis_manifest=json.loads(json.dumps(manifest))
    analysis_manifest["timeline"].update(audio_start_seconds=truth["audio_start_seconds"],
                                         benchmark_origin_evidence="synthetic_generator_sample_zero",
                                         probed_audio_start_seconds=manifest["timeline"]["audio_start_seconds"])
    analysis_manifest["benchmark_parent_manifest"]={"path":str(run/"manifest.json"),"sha256":digest(run/"manifest.json"),
                                                    "fixture_truth_sha256":case["truth_sha256"]}
    write_json(analysis_dir/"manifest.json",analysis_manifest)
    result["analysis_origin"]={"seconds":0.0,"evidence":"synthetic_generator_sample_zero_only","original_manifest_unchanged":True}
    source_analysis=directory/"source-analysis"
    worker("source_rhythm","rhythm.py",[source,"--output",source_analysis,"--bpm",config["bpm"]])
    baseline_rhythm=read_json(source_analysis/"analysis.json")
    if baseline_rhythm.get("source",{}).get("sha256")!=truth["artifacts"]["mix"]["sha256"]:
        raise ValueError("Source rhythm lineage mismatch")
    baseline_events=[e["audio_relative_seconds"] for e in baseline_rhythm.get("events",[]) if e.get("kind")=="periodic_high_frequency_candidate"]
    result["metrics"]["source_click_timing"]={"status":"measured_unverified_rhythm_candidates",**event_metrics(truth["click_times_seconds"],baseline_events,config["metric_policy"]["click_tolerance_seconds"])}
    worker("rhythm","rhythm.py",[run/"denoised.wav","--run-dir",analysis_dir,"--bpm",config["bpm"]])
    analysis=read_json(analysis_dir/"analysis.json")
    if analysis.get("source",{}).get("sha256")!=manifest["output_sha256"]["denoised.wav"]:
        raise ValueError("Rhythm source lineage mismatch")
    events=[e["audio_relative_seconds"] for e in analysis.get("events",[]) if e.get("kind")=="periodic_high_frequency_candidate"]
    result["metrics"]["click_timing"]={"status":"measured_unverified_rhythm_candidates",**event_metrics(truth["click_times_seconds"],events,config["metric_policy"]["click_tolerance_seconds"])}
    before_offset=result["metrics"]["source_click_timing"]["nearest_truth_median_offset_seconds"]
    after_offset=result["metrics"]["click_timing"]["nearest_truth_median_offset_seconds"]
    result["metrics"]["candidate_processing_shift"]={"seconds":None if before_offset is None or after_offset is None else after_offset-before_offset,
                                                     "interpretation":"before/after detector-time difference; processing latency and changed detector response remain confounded","correction_applied":False}
    result["metrics"]["dedicated_clicks"]={"status":"not_requested_stdlib_suite","attenuation":False}
    if backend=="librosa" and (ROOT/"scripts"/"clicks.py").is_file():
        click_dir=directory/"dedicated-click-analysis"
        template=truth["click_only_template_seconds"]
        summary=worker("dedicated_clicks","clicks.py",[source,"--run-dir",click_dir,"--bpm",config["bpm"],
                                                       "--template-start",template[0],"--template-end",template[1],"--template-click-only"])
        clicks_path=Path(summary["clicks_json"])
        clicks=read_json(clicks_path)
        if clicks.get("source",{}).get("sha256")!=truth["artifacts"]["mix"]["sha256"]:
            raise ValueError("Dedicated click source lineage mismatch")
        click_times=[item["audio_relative_seconds"] for item in clicks.get("events",[])]
        result["metrics"]["dedicated_clicks"]={"status":"measured_synthetic_template_candidates","attenuation":False,
                                              "input":"unprocessed_generated_mixture","template_origin":"generated_click_only_interval",
                                              **event_metrics(truth["click_times_seconds"],click_times,config["metric_policy"]["click_tolerance_seconds"])}
        result["artifacts"]["clicks.json"]=audit_artifact(clicks_path,digest(clicks_path))
    worker("phrases","guitar_features.py",["phrases",run/"denoised.wav","--run-dir",analysis_dir,"--backend",backend,"--bpm",config["bpm"]])
    phrases=read_json(analysis_dir/"phrases.json")
    if phrases.get("source",{}).get("sha256")!=manifest["output_sha256"]["denoised.wav"]:
        raise ValueError("Phrase source lineage mismatch")
    observations=phrases.get("observations",{})
    candidates=observations.get("recurrence_candidates",observations.get("similar_envelope_region_candidates",[]))
    result["metrics"]["phrases"]={**recurrence_metrics(truth["repeated_regions_seconds"],candidates),
                                   "expected_regions_seconds":truth["repeated_regions_seconds"],"semantic_acceptance":"unverified"}
    for name in ("analysis.json","events.csv","phrases.json","manifest.json"):
        result["artifacts"][name]=audit_artifact(analysis_dir/name,digest(analysis_dir/name))
    result["artifacts"]["original_media_manifest"]=audit_artifact(run/"manifest.json",analysis_manifest["benchmark_parent_manifest"]["sha256"])
    result["artifacts"]["source_analysis.json"]=audit_artifact(source_analysis/"analysis.json",digest(source_analysis/"analysis.json"))
    result["source_immutable"]=digest(source)==truth["artifacts"]["mix"]["sha256"]
    result["status"]="completed_synthetic_measurements"
    write_json(directory/"case.json",result)
    return result


def run_suite(output: Path,config,profile="conservative3",backend="stdlib"):
    started=time.monotonic(); deadline=started+config["bounds"]["overall_timeout_seconds"]
    fixtures=output/"fixtures"; fixtures.mkdir(mode=0o700)
    sources=output/"sources"; sources.mkdir(mode=0o700)
    for path in (CONFIG,Path(__file__),ROOT/"profiles"/f"{profile}.json",ROOT/"flake.lock",ROOT/"uv.lock",ROOT/"Cargo.lock"):
        (sources/path.name).write_bytes(path.read_bytes())
    index=create_fixtures(fixtures,config)
    receipt={"schema_version":1,"suite":config["suite"],"status":"running","cases":[],
             "created_at":datetime.now(timezone.utc).isoformat(),"profile":profile,"phrase_backend":backend,
             "configuration_sha256":digest(CONFIG),"runner_sha256":digest(Path(__file__)),
             "runtime":{"python":sys.version,"platform":sys.platform},
             "worker_sha256":{name:digest(ROOT/"scripts"/name) for name in ("media.py","rhythm.py","guitar_features.py","clicks.py") if (ROOT/"scripts"/name).is_file()},
             "lock_sha256":{name:digest(ROOT/name) for name in ("flake.lock","uv.lock","Cargo.lock")},
             "listening_accepted":False,"limitations":config["limitations"]}
    for case in index["cases"]:
        try:
            result=evaluate_case(case,fixtures,output,config,profile,backend,deadline)
        except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:
            case_path=output/case["id"]/"case.json"
            result=read_json(case_path) if case_path.is_file() else {"id":case["id"]}
            result.update(status="failed",reason=str(exc))
        receipt["cases"].append(result)
        write_json(output/"benchmark.json",receipt)
    revisions={}
    for case in receipt["cases"]:
        for stage in case.get("stages",{}).values():
            command=stage.get("command",[])
            if len(command)>1 and stage.get("worker_sha256"):
                revisions.setdefault(Path(command[1]).name,set()).add(stage["worker_sha256"])
    receipt["worker_revision_consistency"]={name:{"consistent":len(hashes)==1,"sha256":sorted(hashes)} for name,hashes in revisions.items()}
    receipt.update(status="completed_synthetic_measurements" if all(c["status"]=="completed_synthetic_measurements" for c in receipt["cases"]) else "failed",
                   seconds=time.monotonic()-started,quality_alert_count=sum(len(c.get("quality_alerts",[])) for c in receipt["cases"]))
    if any(len(hashes)!=1 for hashes in revisions.values()):
        receipt.update(status="failed",comparison_failure="Worker revisions changed between fixture cases; measurements retained but not a consistent suite comparison")
    write_json(output/"benchmark.json",receipt)
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest="command",required=True)
    for name in ("fixtures","run"):
        command=commands.add_parser(name); command.add_argument("--output",required=True,type=Path)
        if name=="run":
            command.add_argument("--profile",choices=("bypass","conservative3","mild6"),default="conservative3")
            command.add_argument("--phrase-backend",choices=("stdlib","librosa"),default="stdlib")
    args=parser.parse_args()
    try:
        config=configuration(); output=destination(args.output)
        result=create_fixtures(output,config) if args.command=="fixtures" else run_suite(output,config,args.profile,args.phrase_backend)
        print(json.dumps({"status":result.get("status","fixtures_created"),"output":str(output),"case_count":len(result["cases"]),"result":str(output/("fixtures.json" if args.command=="fixtures" else "benchmark.json"))}))
        return int(result.get("status")=="failed")
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        print(json.dumps({"status":"error","message":str(exc)}),file=sys.stderr); return 2


if __name__=="__main__":
    raise SystemExit(main())
