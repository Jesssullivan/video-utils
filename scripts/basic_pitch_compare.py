#!/usr/bin/env python3
"""Bounded official Basic Pitch ONNX activations with project note hypotheses."""
from __future__ import annotations

import argparse
import array
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import re
import secrets
import subprocess
import sys
import time
import zipfile

from dag import load, number, sha256

ROOT = Path(__file__).resolve().parents[1]
RATE, WINDOW, OVERLAP, STEP = 22050, 43844, 7680, 36164
MODEL_ID = 'spotify-basic-pitch-0.4.0-onnx'
MODEL_HASH = '2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec'
LOCAL_MODEL = ROOT/'artifacts/model-qualification/20261005T230424Z-33788bf0000a/nmp.onnx'
RUNTIME = ROOT/'artifacts/model-runtime-env/onnx-1.30.0-cp314/python/bin/python'
WHEEL_MANIFEST = ROOT/'artifacts/model-runtime-env/onnx-1.30.0-cp314/wheel-manifest-before-install.json'
LIMITS = {'audio_seconds': 30, 'model_windows': 24, 'rss_bytes': 1024**3,
          'deadline_seconds': 600, 'raw_array_bytes': 20*1024**2, 'events_per_preset': 5000,
          'maximum_input_seconds': 300}
OUTPUT_NAMES = ['StatefulPartitionedCall:1', 'StatefulPartitionedCall:2', 'StatefulPartitionedCall:0']
DECODER = 'project_threshold_active_runs_with_local_model_onset_splits'


def settings(budget=20., start=None, onset=.5, frame=.3):
    budget = number(budget, 'max_analysis_seconds', 1)
    if budget > 30:
        raise ValueError('max_analysis_seconds must be <=30')
    onset, frame = number(onset, 'onset_threshold'), number(frame, 'frame_threshold')
    if not .05 <= onset <= .95 or not .05 <= frame <= .95:
        raise ValueError('Activation thresholds must be in .05..0.95')
    if start is not None:
        start = number(start, 'start_seconds', 0)
    return {'max_analysis_seconds': budget, 'start_seconds': start,
            'onset_threshold': onset, 'frame_threshold': frame,
            'minimum_note_length_ms_presets': [127.7, 25.], 'decoder': DECODER,
            'upstream_decoder_parity': False, 'limits': LIMITS}


def schedule(duration: float, config: dict) -> list[dict]:
    duration = number(duration, 'input duration', .000001)
    if duration > LIMITS['maximum_input_seconds']:
        raise ValueError('Input duration must be <=300 seconds')
    budget, start = config['max_analysis_seconds'], config['start_seconds']
    if start is not None:
        if start >= duration:
            raise ValueError('start_seconds must be inside input')
        spans = [(start, min(duration, start+budget))]
    elif duration <= budget:
        spans = [(0., duration)]
    else:
        count = min(6, max(2, math.ceil(budget/5)))
        width = budget/count
        spans = [(i*(duration-width)/(count-1), i*(duration-width)/(count-1)+width) for i in range(count)]
    result = [{'start_seconds': a, 'end_seconds': b} for a, b in spans]
    windows = sum(math.ceil((round((b-a)*RATE)+OVERLAP//2)/STEP) for a,b in spans)
    if windows > LIMITS['model_windows']:
        raise ValueError('Planned model windows exceed24')
    return result


def frame_time(index: int) -> float:
    # Exact upstream model_frames_to_time formula; this is not latency calibration.
    offset = (256/RATE)*(172-WINDOW/256)+.0018
    return index*256/RATE-offset*math.floor(index/172)


def decode(note, onset, minimum_ms: float, config: dict) -> list[dict]:
    if len(note) != len(onset) or not note or any(len(row) != 88 for row in note+onset):
        raise ValueError('Decoder needs matching time-by88 note/onset arrays')
    minimum_ms = number(minimum_ms, 'minimum note length', .001)
    if len(note)>30*86 or any(not isinstance(x,(int,float)) or isinstance(x,bool) or not math.isfinite(x) or not 0<=x<=1 for row in note+onset for x in row):
        raise ValueError('Invalid activation values/frame budget')
    count = len(note)
    result = []
    for pitch in range(88):
        beginning = None
        for index in range(count+1):
            active = index < count and note[index][pitch] >= config['frame_threshold']
            split = (active and beginning is not None and index > beginning and 0 < index < count-1
                and onset[index][pitch] >= config['onset_threshold']
                and onset[index][pitch] > onset[index-1][pitch] and onset[index][pitch] > onset[index+1][pitch])
            if beginning is not None and (not active or split):
                a, b = frame_time(beginning), frame_time(index)
                if b-a >= minimum_ms/1000:
                    result.append({'start_frame': beginning, 'end_frame_exclusive': index,
                        'model_start_seconds': a, 'model_end_seconds': b,
                        'midi_candidate': pitch+21, 'mean_note_activation': sum(row[pitch] for row in note[beginning:index])/(index-beginning),
                        'maximum_onset_activation': max(row[pitch] for row in onset[beginning:index]),
                        'touches_excerpt_boundary': beginning == 0 or index == count,
                        'confidence_kind': 'uncalibrated_model_activation', 'identified_string': None,
                        'intended_note': None, 'performance_issue': None})
                    if len(result) > LIMITS['events_per_preset']:
                        raise ValueError('Decoded event budget exceeded')
                beginning = index if split else None
            if active and beginning is None:
                beginning = index
    return sorted(result, key=lambda item: (item['model_start_seconds'], item['midi_candidate']))


def infer_task(task_path: Path) -> int:
    # This branch is invoked only by the fixed isolated interpreter, never on import.
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[key] = '2'
    import numpy as np
    import onnxruntime as ort
    task = load(task_path)
    if len(task.get('excerpts',[])) not in range(1,7) or sum(e['sample_count'] for e in task['excerpts']) > 30*RATE:
        raise ValueError('Excerpt count/total sample budget exceeded')
    if any(not isinstance(e['sample_count'],int) or isinstance(e['sample_count'],bool) or e['sample_count']<=0 for e in task['excerpts']):
        raise ValueError('Invalid excerpt sample count')
    wheel_manifest=load(WHEEL_MANIFEST)
    if sha256(WHEEL_MANIFEST)!=task['wheel_manifest_sha256'] or Path(sys.prefix).absolute()!=RUNTIME.parent.parent.absolute():
        raise ValueError('Isolated runtime identity mismatch')
    import importlib.metadata
    site=Path(ort.__file__).parents[1]
    for package in wheel_manifest['packages']:
        if importlib.metadata.version(package['name']) != package['version']:
            raise ValueError('Runtime package version mismatch')
        wheel=WHEEL_MANIFEST.parent/'wheels'/package['filename']
        if sha256(wheel)!=package['sha256'] or wheel.stat().st_size!=package['bytes']:
            raise ValueError('Runtime wheel integrity mismatch')
        with zipfile.ZipFile(wheel) as archive:
            for member in archive.infolist():
                if member.is_dir() or member.filename.endswith('.dist-info/RECORD'):
                    continue
                installed=site/member.filename
                expected=hashlib.sha256(archive.read(member)).hexdigest()
                if not installed.is_file() or sha256(installed)!=expected:
                    raise ValueError('Runtime installed bytes mismatch: '+member.filename)
    model = Path(task['model_path'])
    if model.stat().st_size != 230444 or sha256(model) != MODEL_HASH:
        raise ValueError('Qualified model failed checksum')
    options = ort.SessionOptions()
    options.intra_op_num_threads, options.inter_op_num_threads = 2, 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    session = ort.InferenceSession(str(model), sess_options=options, providers=['CPUExecutionProvider'])
    inputs = session.get_inputs()
    if len(inputs) != 1 or inputs[0].name != 'serving_default_input_2:0' or inputs[0].shape[1:] != [WINDOW,1] or inputs[0].type != 'tensor(float)':
        raise ValueError('Unexpected model input contract')
    if session.get_providers() != ['CPUExecutionProvider']:
        raise ValueError('Only CPU provider is qualified')
    config = settings(**task['setting_arguments'])
    excerpts, arrays = [], {}
    windows_used, array_bytes = 0, 0
    total_events={127.7:0,25.:0}
    deadline = time.monotonic()+LIMITS['deadline_seconds']
    for excerpt_index, excerpt in enumerate(task['excerpts']):
        path = Path(excerpt['pcm_path'])
        if path.stat().st_size != excerpt['sample_count']*4 or sha256(path) != excerpt['pcm_sha256']:
            raise ValueError('Excerpt PCM hash/extent mismatch')
        signal = np.fromfile(path, dtype='<f4')
        if not np.isfinite(signal).all() or len(signal) > 30*RATE:
            raise ValueError('Invalid or oversized analysis waveform')
        padded = np.concatenate((np.zeros(OVERLAP//2,dtype=np.float32),signal))
        outputs = [[],[],[]]
        window_receipts=[]
        for position in range(0,len(padded),STEP):
            if time.monotonic() > deadline or windows_used >= LIMITS['model_windows']:
                raise ValueError('Inference deadline/window bound exceeded')
            window = padded[position:position+WINDOW]
            window = np.pad(window,(0,WINDOW-len(window))).reshape(1,WINDOW,1)
            result = session.run(OUTPUT_NAMES, {'serving_default_input_2:0':window})
            for k, value in enumerate(result):
                expected = (1,172,264 if k==2 else 88)
                if value.shape != expected or not np.isfinite(value).all() or float(value.min()) < 0 or float(value.max()) > 1:
                    raise ValueError('Invalid model output shape/value')
                outputs[k].append(value[0,15:-15,:])
            first=position-OVERLAP//2
            window_receipts.append({'window_index':len(window_receipts),'padded_start_sample':position,
                'unpadded_start_sample':first,'input_context_start_seconds_in_excerpt':max(0,first)/RATE,
                'input_context_end_seconds_in_excerpt':min(len(signal),first+WINDOW)/RATE,
                'leading_zero_samples':max(0,-first),'trailing_zero_samples':max(0,first+WINDOW-len(signal)),
                'output_frames_before_crop':172,'cropped_frames_each_side':15,'retained_frames':142})
            windows_used += 1
        retained = int(math.floor(len(signal)*(86/RATE)))
        joined = [np.concatenate(rows,axis=0)[:retained] for rows in outputs]
        note, onset, contour = joined
        if retained < 2:
            raise ValueError('Too few retained model frames')
        clock = np.array([frame_time(i) for i in range(retained)],dtype=np.float64)
        nominal=np.arange(retained,dtype=np.float64)*256/RATE
        window_index=np.arange(retained,dtype=np.int32)//142
        window_frame=np.arange(retained,dtype=np.int32)%142+15
        input_projection=(window_index.astype(np.float64)*STEP-OVERLAP//2+window_frame*256)/RATE
        for name, value in zip(('note','onset','contour','model_times_seconds','nominal_times_seconds',
            'input_window_projection_seconds','window_index','window_frame_index'),
            [*joined,clock,nominal,input_projection,window_index,window_frame]):
            arrays[f'excerpt_{excerpt_index}_{name}'] = value
            array_bytes += value.nbytes
        if array_bytes > LIMITS['raw_array_bytes']:
            raise ValueError('Raw activation byte budget exceeded')
        variants = []
        for minimum in (127.7,25.):
            events = decode(note.tolist(),onset.tolist(),minimum,config)
            total_events[minimum]+=len(events)
            if total_events[minimum]>LIMITS['events_per_preset']:
                raise ValueError('Total run event budget exceeded')
            for event in events:
                a,b=event['start_frame'],event['end_frame_exclusive']
                event['nominal_start_seconds']=a*256/RATE
                event['nominal_end_seconds']=b*256/RATE
                event['input_window_projection_start_seconds']=float(input_projection[a])
                event['input_window_projection_end_seconds']=float(input_projection[b]) if b<retained else float(input_projection[-1]+256/RATE)
                event['audio_relative_start_seconds'] = excerpt['start_seconds']+event['model_start_seconds']
                event['audio_relative_end_seconds'] = min(excerpt['end_seconds'],excerpt['start_seconds']+event['model_end_seconds'])
                event['source_start_seconds'] = task['source_audio_start_seconds']+event['audio_relative_start_seconds']
                event['source_end_seconds'] = task['source_audio_start_seconds']+event['audio_relative_end_seconds']
                event['window_context'] = 'approximately2second_model_context_with_overlap_cropping; not pYIN64/256ms eligibility'
            variants.append({'minimum_note_length_ms':minimum,'event_count':len(events),'events':events})
        excerpts.append({**excerpt,'sample_rate':RATE,'retained_frames':retained,'variants':variants,
            'model_input_windows':window_receipts,
            'arrays_prefix':f'excerpt_{excerpt_index}_', 'clock':{'formula':'frame*256/22050 - floor(frame/172)*((256/22050)*(172-43844/256)+0.0018)',
                'source_axis':'manifest_source_audio_start + excerpt_audio_start + model_time',
                'leading_padding_samples':3840,'overlap_samples':7680,'input_window_samples':43844,
                'window_step_samples':36164,'cropped_output_frames_each_side':15,
                'retained_frame_rule':'floor(excerpt_samples *86/22050)','physical_latency':'unqualified'}})
    output = Path(task['output_dir'])
    np.savez_compressed(output/'activations.npz', **arrays)
    result = {'schema_version':1,'status':'experimental_official_model_project_decoder','excerpts':excerpts,
        'model_windows':windows_used,'raw_array_bytes':array_bytes,'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        'runtime_versions':{name:importlib.metadata.version(name) for name in ('onnxruntime','numpy','flatbuffers','packaging','protobuf')},
        'runtime_python':sys.version.split()[0],'providers':session.get_providers(),
        'model_io':{'inputs':[{'name':i.name,'shape':i.shape,'type':i.type} for i in inputs],
                    'outputs':[{'name':i.name,'shape':i.shape,'type':i.type} for i in session.get_outputs()]}}
    (output/'inference.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    return 0


def bounded_child(command: list[str], output: Path, deadline: float) -> dict:
    peak,stopped,monitor_error=0,None,None
    with (output/'worker.stdout.log').open('xb') as stdout, (output/'worker.stderr.log').open('xb') as stderr:
        process = subprocess.Popen(command,stdout=stdout,stderr=stderr,
            env={**os.environ,'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2','MKL_NUM_THREADS':'2'})
        try:
            while process.poll() is None:
                snapshot=subprocess.run(['ps','-p',str(process.pid),'-o','ppid=,rss='],capture_output=True,text=True,timeout=5).stdout.split()
                if len(snapshot)==2:
                    if int(snapshot[0])!=os.getpid():raise ValueError('Inference worker ownership mismatch')
                    peak=max(peak,int(snapshot[1])*1024)
                if peak>LIMITS['rss_bytes'] or time.monotonic()>=deadline:
                    stopped='rss_bound' if peak>LIMITS['rss_bytes'] else 'deadline'
                    break
                if stdout.tell()+stderr.tell()>10*1024**2:
                    stopped='log_byte_bound';break
                time.sleep(.1)
        except Exception as exc:
            stopped='monitor_error';monitor_error=exc
        finally:
            # Popen keeps ownership of this unreaped direct child even if ps fails.
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
            else:process.wait(timeout=3)
    receipt={'pid':process.pid,'owner_pid':os.getpid(),'ownership':'direct child checked by PPID',
             'ruling':'R-N11','termination_reason':stopped,'returncode':process.returncode,'observed_peak_rss_bytes':peak}
    (output/'worker-resource.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if stopped or process.returncode:
        message=(output/'worker.stderr.log').read_text(errors='replace')[-1000:]
        raise ValueError('Bounded inference failed: '+str(monitor_error or stopped or message))
    return receipt


def build(directory: Path, config: dict, runtime_python: Path = RUNTIME) -> tuple[Path,dict]:
    start_clock=time.monotonic();deadline=start_clock+LIMITS['deadline_seconds']
    manifest_path=directory/'manifest.json'
    manifest_hash=sha256(manifest_path);manifest=load(manifest_path)
    timeline=manifest.get('timeline')
    if not isinstance(timeline,dict) or 'audio_start_seconds' not in timeline:
        raise ValueError('Need explicit manifest timeline.audio_start_seconds; unknown source origin cannot default to zero')
    source_origin=number(timeline['audio_start_seconds'],'manifest timeline.audio_start_seconds')
    source=directory/'denoised.wav'
    identity=sha256(source)
    if manifest.get('output_sha256',{}).get('denoised.wav')!=identity or manifest.get('timeline',{}).get('no_time_stretch') is not True:
        raise ValueError('Need verified denoised derivative and no-time-stretch source mapping')
    if not re.fullmatch('[0-9a-f]{64}',manifest.get('source',{}).get('sha256','')):
        raise ValueError('Need original source SHA256 lineage')
    registry_path=ROOT/'program/models.json';registry_hash=sha256(registry_path);registry=load(registry_path)
    entry=registry.get('models',{}).get(MODEL_ID)
    if not isinstance(entry,dict) or entry.get('sha256')!=MODEL_HASH or entry.get('max_bytes')!=230444:
        raise ValueError('Qualified Basic Pitch model must be explicitly registered')
    cached_model=ROOT/'models'/f'{MODEL_ID}.bin'
    selected_model=cached_model if cached_model.exists() else LOCAL_MODEL
    if not selected_model.is_file():
        raise ValueError('Qualified Basic Pitch model missing; explicitly run just model-prefetch '+MODEL_ID+' before comparison; no automatic download')
    if selected_model.is_symlink() or selected_model.stat().st_size!=230444 or sha256(selected_model)!=MODEL_HASH:
        raise ValueError('Local prequalified model missing/changed; no implicit prefetch')
    interpreter=runtime_python.expanduser().absolute()
    if interpreter!=RUNTIME.absolute() or not interpreter.is_file():
        raise ValueError('Only the qualified isolated venv launcher is accepted')
    runtime_manifest_hash=sha256(WHEEL_MANIFEST)
    worker_hash=sha256(Path(__file__))
    tuning_path=ROOT/'program/instrument.json';tuning_hash=sha256(tuning_path)
    ffprobe=os.environ.get('FFPROBE','ffprobe');ffmpeg=os.environ.get('FFMPEG','ffmpeg')
    probe=subprocess.run([ffprobe,'-v','error','-show_format','-show_streams','-of','json',str(source)],capture_output=True,timeout=30,check=True)
    audio=next(s for s in json.loads(probe.stdout)['streams'] if s['codec_type']=='audio')
    pcm=manifest.get('pcm',{})
    if (int(audio['sample_rate'])!=pcm.get('sample_rate') or int(audio['channels'])!=pcm.get('channels')
        or audio.get('time_base')!=f"1/{pcm.get('sample_rate')}" or int(audio['duration_ts'])!=pcm.get('sample_count')):
        raise ValueError('Native derivative extent/rate/channels differ from manifest PCM')
    duration=number(float(audio['duration']),'duration',.000001)
    excerpts=schedule(duration,config)
    parent=directory/'learned-pitch'
    if parent.is_symlink():raise ValueError('Learned pitch output parent must not be a symlink')
    parent.mkdir(exist_ok=True)
    output=parent/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(6))
    output.mkdir(mode=0o700)
    try:
        for index,excerpt in enumerate(excerpts):
            command=[ffmpeg,'-hide_banner','-loglevel','error','-nostdin','-threads','2','-ss',str(excerpt['start_seconds']),'-i',str(source),'-t',str(excerpt['end_seconds']-excerpt['start_seconds']),'-vn','-map','0:a:0','-ac','1','-ar',str(RATE),'-filter_threads','2','-f','f32le','pipe:1']
            decoded=subprocess.run(command,capture_output=True,check=True,timeout=min(60,max(.001,deadline-time.monotonic()))).stdout
            if len(decoded)>30*RATE*4 or len(decoded)%4:raise ValueError('Unexpected decoded PCM extent')
            pcm=output/f'excerpt-{index}.f32';pcm.write_bytes(decoded);pcm.chmod(0o600)
            excerpt.update(pcm_path=str(pcm),pcm_sha256=sha256(pcm),sample_count=len(decoded)//4,decode_command=command)
        if sum(e['sample_count'] for e in excerpts)>30*RATE:raise ValueError('Total decoded duration exceeds30 seconds')
        arguments={'budget':config['max_analysis_seconds'],'start':config['start_seconds'],'onset':config['onset_threshold'],'frame':config['frame_threshold']}
        task={'model_path':str(selected_model),'output_dir':str(output),'source_audio_start_seconds':source_origin,
              'excerpts':excerpts,'setting_arguments':arguments,'wheel_manifest_sha256':runtime_manifest_hash}
        task_path=output/'task.json';task_path.write_text(json.dumps(task,indent=2)+'\n')
        resource_receipt=bounded_child([str(interpreter),str(Path(__file__).resolve()),'--infer-task',str(task_path)],output,deadline)
        result=load(output/'inference.json')
        if result['peak_rss_bytes']>LIMITS['rss_bytes']:raise ValueError('Measured runtime RSS exceeds bound')
        if (sha256(source)!=identity or sha256(manifest_path)!=manifest_hash or sha256(tuning_path)!=tuning_hash
            or sha256(registry_path)!=registry_hash or sha256(WHEEL_MANIFEST)!=runtime_manifest_hash
            or sha256(selected_model)!=MODEL_HASH or sha256(Path(__file__))!=worker_hash):
            raise ValueError('Source or dependency/context artifacts changed during inference')
        result.update(settings=config,original_source_sha256=manifest['source']['sha256'],analysis_input_sha256=identity,
            manifest_sha256=manifest_hash,model_sha256=MODEL_HASH,model_id=MODEL_ID,model_registry_sha256=registry_hash,
            wheel_manifest_sha256=runtime_manifest_hash,tuning_registry_sha256=tuning_hash,worker_sha256=worker_hash,
            runtime_python_path=str(interpreter),model_path=str(selected_model),elapsed_seconds=time.monotonic()-start_clock,
            coverage_seconds=sum(e['sample_count']/RATE for e in excerpts),coverage_fraction=sum(e['sample_count']/RATE for e in excerpts)/duration,
            raw_activations_sha256=sha256(output/'activations.npz'),worker_resources=resource_receipt,
            performance_grade='not_graded',upstream_decoder_parity=False,
            limitations=['Official polyphonic model activations are not identified strings, played fundamentals or intended notes.',
                        'Project threshold decoder differs from the upstream Melodia/postprocessing implementation.',
                        'Raw activations, model clock adjustment, excerpt edges and approximately2second context are not latency calibration.',
                        'Sparse excerpts cannot recover every sweep/tap/legato note or grade the full recording.'])
        result_path=output/'comparison.json';result_path.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        return result_path,result
    except Exception as exc:
        (output/'failure.json').write_text(json.dumps({'status':'failure','error':str(exc),'source_sha256':identity,'settings':config})+'\n')
        raise


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir',type=Path,nargs='?')
    parser.add_argument('--max-analysis-seconds',type=float,default=20)
    parser.add_argument('--start-seconds',type=float)
    parser.add_argument('--onset-threshold',type=float,default=.5)
    parser.add_argument('--frame-threshold',type=float,default=.3)
    parser.add_argument('--runtime-python',type=Path,default=RUNTIME)
    parser.add_argument('--infer-task',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args()
    try:
        if args.infer_task:return infer_task(args.infer_task)
        if args.run_dir is None:raise ValueError('run_dir required')
        config=settings(args.max_analysis_seconds,args.start_seconds,args.onset_threshold,args.frame_threshold)
        output,result=build(args.run_dir.expanduser().resolve(strict=True),config,args.runtime_python)
        print(json.dumps({'comparison_json':str(output),'status':result['status'],'coverage_seconds':result['coverage_seconds'],
            'model_windows':result['model_windows'],'excerpt_count':len(result['excerpts']),
            'event_counts_by_minimum_ms':{str(ms):sum(v['event_count'] for e in result['excerpts'] for v in e['variants'] if v['minimum_note_length_ms']==ms) for ms in (127.7,25.)},
            'performance_grade':'not_graded'}))
        return 0
    except (OSError,ValueError,KeyError,TypeError,StopIteration,subprocess.SubprocessError) as exc:
        print('basic pitch comparator: '+str(exc),file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
