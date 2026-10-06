#!/usr/bin/env python3
"""Prepare opaque generated-audio jobs; execute only against a bound release.

Discovery never receives fixture labels or truth. Evaluation is a separate CLI
after all four predictions have been hash-frozen. No dependency installation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('learned_pilot_base', ROOT/'scripts/pitch_evaluate.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
require = base.require
PLAN = (('c1-missing-fundamental','clean',8),('tuning-ladder','clean',8),
        ('legato-transition','mix',6),('sweep-and-polyphony','mix',8))
RUNTIME_MANIFEST = ROOT/'artifacts/model-runtime-env/onnx-1.30.0-cp314/wheel-manifest-before-install.json'
AUTHORITY = 'AGENTS.md; R-HOOK-CONVERGENCE-20261004; R-N11 owned child; R-N13 durable receipt'
OWNED_OUTPUTS = set()


def repo_bytes(value, limit=5_000_000, expected=None):
    path = Path(value)
    if not path.is_absolute(): path = ROOT/path
    require('..' not in path.parts and path.is_relative_to(ROOT), 'path_outside_repository')
    current = ROOT
    for part in path.relative_to(ROOT).parts:
        current = current/part
        require(not current.is_symlink(), 'symlink_path')
    fd = os.open(path, os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size<=limit, 'file_bound_or_type')
        with os.fdopen(os.dup(fd),'rb') as handle: raw = handle.read(limit+1)
        after = os.fstat(fd)
        require(len(raw)==after.st_size<=limit and before.st_mtime_ns==after.st_mtime_ns,
                'file_changed_or_oversized')
    finally: os.close(fd)
    digest = hashlib.sha256(raw).hexdigest()
    if expected is not None: require(digest==base.fingerprint(expected), 'sha256_mismatch')
    return raw,digest


def repo_json(value, expected=None):
    raw,digest = repo_bytes(value, expected=expected)
    base.check_json_depth(raw)
    value = json.loads(raw, object_pairs_hook=base.unique_object, parse_constant=base.reject_constant,
                       parse_float=base.finite_float, parse_int=base.bounded_int)
    require(isinstance(value,dict), 'json_object_required')
    return value,digest


def put(path, value):
    raw = (json.dumps(value,indent=2,allow_nan=False)+'\n').encode()
    fd = os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as handle:
        handle.write(raw);handle.flush();os.fsync(handle.fileno())
    return hashlib.sha256(raw).hexdigest()


def identities(plan, runtime=False):
    files = {'adapter_sha256':ROOT/'scripts/basic_pitch_compare.py',
             'evaluator_sha256':ROOT/'scripts/learned_pitch_evaluate.py',
             'instrument_registry_sha256':ROOT/'program/instrument.json',
             'model_registry_sha256':ROOT/'program/models.json'}
    if runtime: files['runtime_manifest_sha256'] = RUNTIME_MANIFEST
    for key,path in files.items(): repo_bytes(path,expected=plan[key])


def validate_plan(plan):
    require(plan.get('schema_version')==1 and plan.get('budget_seconds')==30
            and plan.get('discovery_receives_truth') is False, 'unsupported_preregistration')
    require(plan.get('expected_total_frames')==2580 and plan.get('expected_total_model_windows')==19,
            'fixed_coverage_required')
    settings = plan['settings']
    require(settings.get('onset_threshold')==.5 and settings.get('frame_threshold')==.3
            and settings.get('minimum_note_length_ms_presets')==[127.7,25.]
            and settings.get('worker_deadline_seconds')==600
            and settings.get('controller_deadline_seconds')==900
            and settings.get('root_inference_release_required') is True,'fixed_settings_required')
    require(settings.get('controller_math_threads')==2 and settings.get('max_rss_bytes')==1024**3
            and settings.get('max_model_windows')==24 and settings.get('max_raw_numeric_bytes')==20*1024**2
            and settings.get('max_events_per_preset')==5000,'fixed_resource_bounds_required')
    jobs = plan['jobs']
    require(isinstance(jobs,list) and len(jobs)==4,'fixed_four_jobs_required')
    for n,(job,(case,component,budget)) in enumerate(zip(jobs,PLAN),1):
        require((job['evaluation_case_id'],job['component'],job['requested_budget_seconds'])==(case,component,budget)
                and job['opaque_discovery_id']==f'job-{n:02}' and job['requested_start_seconds']==0,
                'fixed_job_plan_required')
        require(job['native_sample_rate']==48000 and job['native_channels']==1
                and job['native_sample_count']==(8 if n<=2 else 10)*48000, 'native_identity_required')
        require(job['expected_frames']==budget*86 and job['expected_model_windows']==(4 if budget==6 else 5),
                'expected_job_coverage_required')
        require(job.get('expected_raw_numeric_bytes')==budget*86*1792,'expected_raw_array_extent_required')


def _prepare(preregistration, output):
    plan,plan_hash = repo_json(preregistration)
    validate_plan(plan);identities(plan)
    bank,bank_hash = base.read_json(base.safe_path(plan['bank_index']),expected_hash=plan['bank_index_sha256'])
    pyin,pyin_hash = base.read_json(base.safe_path(plan['pyin_pilot_index']),expected_hash=plan['pyin_pilot_index_sha256'])
    require(bank.get('schema_version')==2 and bank.get('suite')=='technical-v2'
            and bank.get('case_count')==12 and bank.get('total_duration_seconds')==120,'bound_bank_required')
    require(pyin.get('budget_seconds')==30 and pyin.get('bank_index_sha256')==bank_hash
            and len(pyin.get('jobs',[]))==4,'bound_pyin_required')
    output = base.safe_path(output)
    require(output!=base.ALLOWED and not output.exists(),'fresh_output_required')
    output.mkdir(mode=0o700,parents=True)
    OWNED_OUTPUTS.add(output)
    prepared=[]
    for job,old in zip(plan['jobs'],pyin['jobs']):
        require(old.get('case_id')==job['evaluation_case_id'] and old.get('component')==job['component']
                and old.get('input_sha256')==job['input_sha256']
                and old.get('truth_sha256')==job['truth_sha256']
                and old.get('pitch_sha256')==job['existing_pyin_pitch_sha256'],'pyin_job_binding_mismatch')
        source = base.safe_path(job['source_component_path'])
        identity = {'sample_rate':48000,'channels':1,'sample_count':job['native_sample_count']}
        _,size = base.verify_wave(source,job['input_sha256'],identity)
        require(size==job['native_bytes'],'source_byte_extent_mismatch')
        raw,_ = base.read_bytes(source,3_000_000,job['input_sha256'])
        directory = output/'discovery'/job['opaque_discovery_id'];directory.mkdir(mode=0o700,parents=True)
        alias = directory/'denoised.wav'
        with alias.open('xb') as handle: handle.write(raw)
        alias.chmod(0o600)
        manifest = {'schema_version':1,'source':{'sha256':job['input_sha256']},
            'output_sha256':{'denoised.wav':job['input_sha256']},
            'timeline':{'audio_start_seconds':0.,'no_time_stretch':True},'pcm':identity,
            'provenance':{'input_role':'unprocessed_component_alias','denoising_performed':False,
                'gain_changed':False,'origin_evidence':'synthetic_generator_sample_zero'}}
        manifest_hash = put(directory/'manifest.json',manifest)
        prepared.append({'opaque_id':job['opaque_discovery_id'],'run_dir':str(directory),
                         'manifest_sha256':manifest_hash,'input_sha256':job['input_sha256']})
    receipt = {'schema_version':1,'status':'prepared_no_inference','authority':AUTHORITY,
        'preregistration_sha256':plan_hash,'bank_index_sha256':bank_hash,'pyin_pilot_index_sha256':pyin_hash,
        'preregistration_path':str(Path(preregistration).absolute()),
        'controller_sha256':repo_bytes(Path(__file__))[1],'jobs':prepared,
        'source_audio_bytes_read':True,'source_audio_decoded':False,'inference_invoked':False,
        'truth_content_read':False,'real_performance_grading':False,'created_at':datetime.now(timezone.utc).isoformat()}
    put(output/'preparation.json',receipt)
    return plan,receipt,output


def prepare(preregistration, output):
    output = base.safe_path(output)
    require(output not in OWNED_OUTPUTS and not output.exists(),'fresh_output_required')
    try: return _prepare(preregistration,output)
    except Exception as exc:
        if output in OWNED_OUTPUTS:
            put(output/'preparation-failure.json',{'status':'partial_preparation_no_inference',
                'reason':str(exc),'inference_invoked':False,'evaluation_invoked':False})
        raise


def command(directory, budget):
    return [sys.executable,str(ROOT/'scripts/basic_pitch_compare.py'),str(directory),
            '--start-seconds','0','--max-analysis-seconds',str(budget),
            '--onset-threshold','0.5','--frame-threshold','0.3']


def group_live(pgid):
    result = subprocess.run(['ps','-axo','pid=,pgid=,stat='],capture_output=True,text=True,timeout=3,check=True)
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields)==3 and fields[1].isdigit() and int(fields[1])==pgid and not fields[2].startswith('Z'):
            return True
    return False


def run_owned(argv, directory, deadline):
    """Launch an owned isolated process group; never signal an unrelated session."""
    env = dict(os.environ)
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS'):
        env[key] = '2'
    with (directory/'controller.stdout').open('xb') as out,(directory/'controller.stderr').open('xb') as err:
        child = subprocess.Popen(argv,stdout=out,stderr=err,env=env,start_new_session=True,cwd=ROOT)
        signalled = False
        try:
            while child.poll() is None:
                require((directory/'controller.stdout').stat().st_size<=5_000_000
                        and (directory/'controller.stderr').stat().st_size<=5_000_000,'child_log_bound')
                if time.monotonic()>=deadline: raise TimeoutError('controller_deadline')
                time.sleep(.05)
            require(child.returncode==0,'discovery_worker_failed')
        except BaseException:
            # Unreaped Popen identity and PGID==PID establish ownership of this
            # session. A group may retain grandchildren after its leader exits.
            # The new-session process group remains owned when its leader has
            # exited but descendants are still live. Group ID cannot be reused
            # while those members remain. Probe that exact group before signal.
            if group_live(child.pid):
                if child.poll() is None:
                    require(os.getpgid(child.pid)==child.pid,'owned_group_identity_changed')
                os.killpg(child.pid,signal.SIGTERM);signalled=True
                try: child.wait(timeout=3)
                except subprocess.TimeoutExpired: pass
                if group_live(child.pid):
                    try: os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError: pass
                child.wait(timeout=3)
            put(directory/'signal-receipt.json',{'actor':'learned_pitch_pilot','pid':child.pid,
                'target_ownership':'Popen child in new session; live PGID equals PID before signal',
                'reason':'timeout or log bound','ruling':'R-N11','prior_state':'owned running child',
                'result':'signalled and reaped' if signalled else 'already exited'})
            raise
    result,_ = base.read_json(directory/'controller.stdout')
    return result


def execute(plan, prepared, output, release_path, runner=run_owned, deadline=None):
    repo_bytes(prepared['preregistration_path'],expected=prepared['preregistration_sha256'])
    repo_bytes(Path(__file__),expected=prepared['controller_sha256'])
    release,_ = repo_json(release_path)
    require(release.get('inference_authorized') is True
            and release.get('preregistration_sha256')==prepared['preregistration_sha256']
            and release.get('controller_sha256')==prepared['controller_sha256'],'bound_inference_release_required')
    identities(plan,runtime=True)
    deadline = deadline if deadline is not None else time.monotonic()+900
    predictions=[]
    total_raw=0;event_counts={127.7:0,25.:0}
    for job,opaque in zip(plan['jobs'],prepared['jobs']):
        require(deadline-time.monotonic()>=610,'insufficient_remaining_worker_budget')
        directory = base.safe_path(opaque['run_dir'])
        base.read_bytes(directory/'manifest.json',5_000_000,opaque['manifest_sha256'])
        base.read_bytes(directory/'denoised.wav',3_000_000,job['input_sha256'])
        result = runner(command(directory,job['requested_budget_seconds']),directory,deadline)
        path = base.safe_path(result['comparison_json'])
        require(path.is_relative_to(directory),'comparison_outside_owned_job')
        comparison,comparison_hash = base.read_json(path,limit=64_000_000)
        raw = path.parent/'activations.npz'
        _,raw_hash = base.read_bytes(raw,100*1024**2,comparison['raw_activations_sha256'])
        require(comparison.get('analysis_input_sha256')==job['input_sha256']
                and comparison.get('worker_sha256')==plan['adapter_sha256']
                and comparison.get('model_sha256')==plan['model_sha256']
                and comparison.get('wheel_manifest_sha256')==plan['runtime_manifest_sha256']
                and comparison.get('coverage_seconds')==job['requested_budget_seconds']
                and comparison.get('model_windows')==job['expected_model_windows'],'prediction_binding_mismatch')
        require(comparison.get('raw_array_bytes')==job['expected_raw_numeric_bytes']
                and isinstance(comparison.get('peak_rss_bytes'),(float,int))
                and 0<comparison['peak_rss_bytes']<=1024**3,'prediction_resource_bound')
        total_raw += comparison['raw_array_bytes']
        require(total_raw<=20*1024**2,'aggregate_raw_array_bound')
        require(len(comparison.get('excerpts',[]))==1
                and comparison['excerpts'][0].get('retained_frames')==job['expected_frames'], 'prediction_coverage_mismatch')
        variants = comparison['excerpts'][0].get('variants')
        require(isinstance(variants,list) and len(variants)==2
                and [v.get('minimum_note_length_ms') for v in variants]==[127.7,25.],'prediction_presets_required')
        for variant in variants:
            count = variant.get('event_count')
            require(type(count) is int and count==len(variant.get('events',[])) and count>=0,'event_extent_required')
            event_counts[variant['minimum_note_length_ms']] += count
            require(event_counts[variant['minimum_note_length_ms']]<=5000,'aggregate_event_bound')
        predictions.append({'opaque_id':opaque['opaque_id'],'comparison_path':str(path),
            'comparison_sha256':comparison_hash,'activations_path':str(raw),'activations_sha256':raw_hash})
        put(output/f'prediction-{opaque["opaque_id"]}.json',predictions[-1])
    identities(plan,runtime=True)
    repo_bytes(prepared['preregistration_path'],expected=prepared['preregistration_sha256'])
    repo_bytes(Path(__file__),expected=prepared['controller_sha256'])
    base.read_bytes(base.safe_path(plan['bank_index']),5_000_000,prepared['bank_index_sha256'])
    base.read_bytes(base.safe_path(plan['pyin_pilot_index']),5_000_000,prepared['pyin_pilot_index_sha256'])
    for job,pred,opaque in zip(plan['jobs'],predictions,prepared['jobs']):
        base.read_bytes(base.safe_path(job['source_component_path']),3_000_000,job['input_sha256'])
        base.read_bytes(base.safe_path(Path(opaque['run_dir'])/'denoised.wav'),3_000_000,job['input_sha256'])
        base.read_bytes(base.safe_path(Path(opaque['run_dir'])/'manifest.json'),5_000_000,opaque['manifest_sha256'])
        base.read_bytes(base.safe_path(pred['comparison_path']),64_000_000,pred['comparison_sha256'])
        base.read_bytes(base.safe_path(pred['activations_path']),100*1024**2,pred['activations_sha256'])
    require(time.monotonic()<deadline,'controller_deadline_before_freeze')
    freeze_hash = put(output/'predictions-frozen.json',{'status':'four_predictions_hash_frozen',
        'truth_content_read':False,'preregistration_sha256':prepared['preregistration_sha256'],'jobs':predictions})
    jobs=[]
    for job,pred,opaque in zip(plan['jobs'],predictions,prepared['jobs']):
        jobs.append({**{k:v for k,v in pred.items() if k!='opaque_id'},
            'case_id':job['evaluation_case_id'],'component':job['component'],'status':'completed_measurements',
            'input_path':str(Path(opaque['run_dir'])/'denoised.wav'),'input_sha256':job['input_sha256'],
            'truth_path':str(base.safe_path(job['truth_path'])),'truth_sha256':job['truth_sha256']})
    index = {'schema_version':1,'bank_index_sha256':prepared['bank_index_sha256'],
        'instrument_registry_sha256':plan['instrument_registry_sha256'],'model_sha256':plan['model_sha256'],
        'adapter_sha256':plan['adapter_sha256'],'runtime_manifest_sha256':plan['runtime_manifest_sha256'],
        'budget_seconds':30,'predictions_frozen_sha256':freeze_hash,'jobs':jobs}
    index_hash = put(output/'learned-pilot-index.json',index)
    require(time.monotonic()<deadline,'controller_deadline_after_index')
    return {'status':'predictions_frozen_ready_for_separate_evaluation','inference_invoked':True,
        'truth_content_read':False,'model_windows':19,'coverage_seconds':30,
        'learned_pilot_index':str(output/'learned-pilot-index.json'),'learned_pilot_index_sha256':index_hash,
        'predictions_frozen_sha256':freeze_hash,'real_performance_grading':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preregistration',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--release',type=Path)
    parser.add_argument('--summary',action='store_true')
    args=parser.parse_args();output=None
    deadline=time.monotonic()+900
    try:
        require(not args.execute or args.release is not None,'execute_requires_bound_release')
        plan,prepared,output = prepare(args.preregistration,args.output)
        result = execute(plan,prepared,output,args.release,deadline=deadline) if args.execute else prepared
        put(output/'controller-result.json',result)
        print(json.dumps(result if not args.summary else {k:v for k,v in result.items() if k!='jobs'},allow_nan=False))
        return 0
    except (ValueError,OSError,KeyError,TypeError,TimeoutError,subprocess.SubprocessError) as exc:
        diagnostic = {'status':'partial_or_failed_no_evaluation','reason':str(exc),
                      'real_performance_grading':False,'evaluation_invoked':False}
        if output is not None: put(output/'controller-failure.json',diagnostic)
        print(json.dumps(diagnostic));print(str(exc),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
