#!/usr/bin/env python3
"""Isolated preregistered order-null generator/runner. Numerical release is separate."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import wave

ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = ROOT / 'docs/agent-notes/2026-10-06-phrase-order-null-settings.json'
ARMS_PATH = ROOT / 'docs/agent-notes/2026-10-05-phrase-guarded-arms.py'
ARMS_SHA = '78ca89de9cea327cc4ec1096a83522781a08bc161819699b69797ca273e2fb6c'
FRONTEND_SHA = '2ed031e8000cbcda92b504db10c98de03f456c90573cbff815cbb940c9ac86fe'
RHYTHM_SHA = '264b723ca29e4731da0a12d5dce221e7826a38b67f848ce9f4ffcf8bfe4b35b9'
SETTINGS_SHA = '232f7503f58e9ebcb2b59b220b97755b7001683eccd80893634d8f6b777079a3'
EVALUATOR_SHA = '3e503de277b2fd233fe802595a09a655c89669b0eb820f228e677c1b94b828a5'
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS'):
    os.environ[name] = '2'
sys.path.insert(0, str(ROOT / 'scripts'))
if hashlib.sha256((ROOT/'scripts/phrase_evaluate.py').read_bytes()).hexdigest()!=EVALUATOR_SHA:
    raise ValueError('Frozen evaluation/JSON parser source changed before import')
from phrase_evaluate import guarded_json, recurrence_metrics, pair_spans


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def safe(path, root, existing=False):
    path = Path(path).absolute()
    if '..' in path.parts or not path.is_relative_to(root) or path == root:
        raise ValueError('Artifact path must stay beneath the assigned root')
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError('Symlink artifact components rejected')
    if existing and (not path.is_file() or path.stat().st_size > 20_000_000):
        raise ValueError('Missing or oversized artifact')
    return path


def read(path, expected=None, opened=None):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 20_000_000:
        raise ValueError('Missing or oversized JSON')
    if opened is not None:
        with path.open('rb'):
            opened()  # An actual successful truth-file open, before digest/content reads.
    before = digest(path)
    if expected is not None and before != expected:
        raise ValueError('JSON receipt hash changed')
    value = guarded_json(path.read_text())
    if digest(path) != before:
        raise ValueError('JSON changed while read')
    return value


def write(path, value, new=False):
    raw = json.dumps(value, indent=2, allow_nan=False).encode() + b'\n'
    if len(raw) > 20_000_000 or (new and path.exists()):
        raise ValueError('Metadata bound or immutable output violated')
    temporary = path.with_name(path.name + '.pending')
    with temporary.open('xb') as handle:
        handle.write(raw)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def settings():
    if SETTINGS_SHA is not None and digest(SETTINGS_PATH) != SETTINGS_SHA:
        raise ValueError('Closed preregistered settings changed')
    return read(SETTINGS_PATH)


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def frozen_arms():
    if digest(ARMS_PATH) != ARMS_SHA:
        raise ValueError('Original A/B/C/D source changed')
    return module(ARMS_PATH, 'order_null_frozen_arms')


def parameters(seed):
    s = settings()
    if seed not in s['seeds']:
        raise ValueError('Unregistered fresh seed')
    def unit(knob):
        raw = hashlib.sha256(f'phrase-order-null-v1:{seed}:{knob}'.encode()).digest()
        return int.from_bytes(raw[:8], 'big') / 2**64
    return {name: low + (high-low)*unit(name) for name, (low, high) in s['ranges'].items()}


def plan():
    s = settings()
    return {'schema_version': 1, 'kind': 'phrase_order_null_preregistration',
            'settings_sha256': digest(SETTINGS_PATH), 'runner_sha256': digest(__file__),
            'original_arms_sha256': ARMS_SHA, 'frontend_sha256': FRONTEND_SHA,
            'rhythm_sha256': RHYTHM_SHA, 'evaluator_sha256':EVALUATOR_SHA, 'instrument_sha256': digest(ROOT/'program/instrument.json'),
            'case_count': 10, 'total_duration_seconds': 80, 'truth_scope': 'generator_only_not_musician',
            'cases': [{'id': f'seed{seed}-{cohort}', 'seed': seed, 'cohort': cohort,
                       'duration_seconds': 8, 'parameters': parameters(seed)}
                      for seed in s['seeds'] for cohort in s['cohorts']],
            'generation_admitted': False, 'inference_admitted': False,
            'discovery_reference_labels_supplied': False, 'canonical_defaults_activated': False}


def checked_plan(path):
    value = read(safe(path, ROOT/'artifacts/experiments/phrase-window-ablation', True))
    if value != plan():
        raise ValueError('Plan source/settings/context differ from freeze')
    return value


def order_evidence(candidate, z, period, origin):
    import numpy as np
    length = candidate['pulse_count']
    i = round((candidate['first_start_seconds']-origin)/period)
    j = round((candidate['second_start_seconds']-origin)/period)
    if length not in (2, 4, 8, 16) or not 0 <= i < j or j+length > len(z) or z.shape[1] == 0:
        raise ValueError('Order-null proposal grid invalid')
    first, second = z[i:i+length], z[j:j+length]
    norm = float(np.linalg.norm(first) * np.linalg.norm(second))
    if norm < 1e-12:
        return {'status': 'zero_norm_abstention', 'margin': None, 'rotated_cosines': []}
    score = float(np.clip(np.sum(first*second)/norm, -1, 1))
    rotated = [float(np.clip(np.sum(first*np.roll(second, offset, axis=0))/norm, -1, 1))
               for offset in range(1, length)]
    baseline = float(np.median(rotated))
    return {'status': 'heuristic_order_distinctiveness_not_probability', 'true_cosine': score,
            'rotated_cosines': rotated, 'rotation_offsets': list(range(1, length)),
            'null_median': baseline, 'margin': score-baseline, 'first_window_rotated': False}


def select(proposals, z, period, origin, arms=None):
    arms = arms or frozen_arms()
    if len(proposals) > 60:
        raise ValueError('Initial proposal cap exceeded')
    rows, audit = [], []
    for index, candidate in enumerate(proposals):
        contrast = arms.contrast(candidate, z, period, origin)
        order = order_evidence(candidate, z, period, origin)
        eligible = contrast['contrast'] is not None and contrast['contrast'] >= .10-1e-12
        order_ok = order['margin'] is not None and order['margin'] >= .10-1e-12
        rows.append((index, candidate, contrast, order, eligible, order_ok))
        audit.append({'candidate_index': index, 'contrast_evidence': contrast, 'order_evidence': order,
                      'control_status': 'eligible' if eligible else 'contrast_excluded',
                      'order_status': 'eligible' if eligible and order_ok else
                      'contrast_excluded' if not eligible else 'order_margin_excluded'})
    def ranking(row):
        return (-row[2]['contrast'], -row[2]['match_cosine'], row[1]['first_start_seconds'],
                row[1]['second_start_seconds'], row[1]['pulse_count'], row[0])
    result = {}
    for name, predicate, key in (('Bcontrol', lambda row: row[4], 'control_status'),
                                 ('Border', lambda row: row[4] and row[5], 'order_status')):
        eligible = sorted((row for row in rows if predicate(row)), key=ranking)
        for row in eligible[10:]:
            audit[row[0]][key] = 'ranked_cap_excluded'
        result[name] = [{**row[1], 'original_candidate_index': row[0],
                         'contrast_evidence': row[2], 'order_evidence': row[3]} for row in eligible[:10]]
    return result, audit


def build(cache, period, origin, duration):
    arms = frozen_arms()
    cache = arms.validate(cache, period, origin, duration)
    values, centroids = arms.aggregate(cache, period, origin, duration)
    search, search_sha = arms.load_search()
    proposals = search(values, period, duration, cache['onsets'], origin, centroids)['recurrence_candidates']
    for candidate in proposals:
        candidate.update(performance_issue_confirmed=False, detector_confidence=None,
                         first_boundary_confidence=None, second_boundary_confidence=None)
    selected, audit = select(proposals, arms.standardized(values), period, origin, arms) if proposals else ({'Bcontrol': [], 'Border': []}, [])
    return {'schema_version': 1, 'status': 'isolated_order_null_hypotheses',
            'settings_sha256': digest(SETTINGS_PATH), 'runner_sha256': digest(__file__),
            'short_search_sha256': search_sha, 'proposal_universe': proposals, 'arms': selected,
            'audit': audit, 'duration_seconds': duration, 'inferred_period_seconds': period,
            'observed_origin_seconds': origin, 'performance_issue_confirmed': False,
            'detector_confidence': None, 'boundary_confidence': None,
            'inference_reference_labels_supplied': False, 'canonical_defaults_activated': False}


def render(case, rate=48000):
    """Pure generator; only source tests use tiny low-rate arrays before admission."""
    import numpy as np
    s = settings(); p = case['parameters']; cohort = case['cohort']; seed = case['seed']
    if cohort not in s['cohorts'] or seed not in s['seeds']:
        raise ValueError('Unregistered construction')
    t = np.arange(8*rate)/rate; clean = np.zeros(len(t)); events = []; spans = []
    noise_seed = int.from_bytes(hashlib.sha256(f'phrase-order-null-v1:{seed}:noise'.encode()).digest()[:8], 'big')
    rng = random.Random(noise_seed); white = np.fromiter((rng.uniform(-1, 1) for _ in t), float, len(t))
    from scipy.signal import lfilter
    colored = lfilter([1-p['noise_lowpass_coefficient']], [1, -p['noise_lowpass_coefficient']], white)
    levels = np.interp(t, s['noise_envelope_times_seconds'], s['noise_envelope_levels'])
    noise = levels*(p['noise_amplitude']*(.5*white+.5*colored)+p['fan_gain']*np.sin(2*np.pi*p['fan_hz']*t+.3))
    click = np.zeros(len(t)); click_times = []; at = p['click_phase_seconds']
    while at+.009 < 8:
        start = round(at*rate); extent = round(.009*rate); age = np.arange(extent)/rate
        click[start:start+extent] += p['click_gain']*np.exp(-age/.0018)*np.sin(2*np.pi*3500*age)
        click_times.append(start/rate); at += 60/p['click_bpm']*(1+p['click_drift']*at/8)
    def envelope(start, end, attack=.0015, release=.006):
        return np.maximum(0, np.minimum(1, np.minimum((t-start)/attack, (end-t)/release)))
    f0 = s['guitar_fundamental_hz']
    if cohort in ('low32-sustain', 'missing-f0-sustain'):
        env = envelope(.5, 7.5, .015, .05)
        if cohort == 'low32-sustain':
            clean = p['guitar_gain']*env*np.tanh(p['drive']*np.sin(2*np.pi*f0*t))
        else:
            # No saturation: a nonlinear harmonic sum recreates the omitted fundamental.
            clean = env*sum(gain*np.sin(2*np.pi*multiple*f0*t) for multiple, gain in s['missing_f0_harmonics'])
    elif cohort in ('palm-recurrence', 'legato-recurrence'):
        for group, start in enumerate((p['first_start_seconds'], p['second_start_seconds'])):
            end = start+p['motif_duration_seconds']; spans.append([round(start*rate)/rate, round(end*rate)/rate])
            for index, (fraction, midi) in enumerate(zip(s['motif_position_fractions'], s['motif_midi'])):
                onset = round((start+fraction*p['motif_duration_seconds'])*rate)/rate
                following = start+(s['motif_position_fractions'][index+1] if index<5 else 1)*p['motif_duration_seconds']
                finish = following if cohort == 'legato-recurrence' else min(end, onset+.04)
                age = np.maximum(0, t-onset); env = envelope(onset, finish, .008 if cohort == 'legato-recurrence' else .0015)
                if cohort == 'palm-recurrence': env *= np.exp(-age/.023)
                hz = 440*2**((midi-69)/12)
                clean += p['guitar_gain']*env*np.tanh(p['drive']*np.sin(2*np.pi*hz*age))
                events.append({'id': f'motif-{group}-{index}', 'onset_native_sample': round(onset*rate),
                               'onset_source_seconds': onset, 'duration_samples': max(1, round(finish*rate)-round(onset*rate)),
                               'midi_notes': [midi], 'articulation': 'pitch_transition' if cohort=='legato-recurrence' and index else 'picked_attack'})
    mixture = clean+click+noise
    if np.max(np.abs(mixture)) >= .999:
        raise ValueError('Unnormalized construction clips')
    pcm = {key: np.rint(value*32767).astype('<i2') for key, value in
           {'clean': clean, 'click': click, 'noise': noise, 'mix': mixture}.items()}
    pairs = [] if not spans else [{'id': 'generated-repeat-1', 'first_span_seconds': spans[0], 'second_span_seconds': spans[1]}]
    truth = {'schema_version': 2, 'kind': 'synthetic_generated_signal_and_score_truth',
             'ground_truth_scope': 'generator_only_not_musician', 'id': case['id'],
             'phrase_spans_seconds': spans, 'boundaries_seconds': sorted(x for span in spans for x in span),
             'recurrence_pairs': pairs, 'click_times_seconds': click_times,
             'generated_score': {'events': events, 'status': 'complete_generated_score', 'attack_reference_known': True},
             'bpm': None, 'audio_start_seconds': 0., 'real_recording_labels': False,
             'observed_articulation_context': [], 'expected_abstention_reasons': ['detector_and_boundary_confidence_unknown'],
             'construction_parameters': p, 'listening_accepted': False}
    return pcm, truth


def missing_f0_fit(samples, rate=48000):
    import numpy as np
    s = settings(); low, high = s['missing_f0_fit_seconds']; t = np.arange(round(low*rate), round(high*rate))/rate
    f0 = s['guitar_fundamental_hz']; columns = [np.ones(len(t))]
    for harmonic in range(1, 8):
        columns.extend([np.sin(2*np.pi*f0*harmonic*t), np.cos(2*np.pi*f0*harmonic*t)])
    coefficients = np.linalg.lstsq(np.column_stack(columns), samples[round(low*rate):round(high*rate)]/32767., rcond=None)[0]
    amplitude = float(np.hypot(coefficients[1], coefficients[2]))
    if amplitude > s['missing_f0_fit_amplitude_bound']:
        raise ValueError('Rendered missing-F0 fixture contains excess fundamental')
    return {'method': 'joint_sin_cos_DC_harmonics_1_through_7_on_rendered_clean_PCM',
            'fundamental_amplitude': amplitude, 'bound': s['missing_f0_fit_amplitude_bound'], 'span_seconds': [low, high]}


def generate(plan_path, output):
    admitted = checked_plan(plan_path)
    output = safe(output, ROOT/'artifacts/experiments/phrase-window-ablation')
    if output.exists(): raise ValueError('Choose new isolated generator output')
    output.mkdir(parents=True); rows = []; started = time.monotonic()
    try:
        for case in admitted['cases']:
            if time.monotonic()-started > 120: raise ValueError('Generator deadline exceeded')
            pcm, truth = render(case); folder = output/case['id']; folder.mkdir(); components = {}
            for name, samples in pcm.items():
                path = folder/f'{name}.wav'
                with wave.open(str(path), 'wb') as handle:
                    handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(48000); handle.writeframes(samples.tobytes())
                components[name] = {'path': str(path.relative_to(output)), 'sha256': digest(path), 'bytes': path.stat().st_size,
                                    'sample_rate': 48000, 'channels': 1, 'sample_count': 384000,
                                    'duration_seconds': 8., 'audio_start_seconds': 0., 'origin_evidence': 'synthetic_generator_sample_zero'}
            import numpy as np
            saved={}
            for name in components:
                with wave.open(str(folder/f'{name}.wav'),'rb') as handle:
                    if (handle.getframerate(),handle.getnchannels(),handle.getsampwidth(),handle.getnframes())!=(48000,1,2,384000):
                        raise ValueError('Saved generated native extent differs')
                    saved[name]=np.frombuffer(handle.readframes(handle.getnframes()),dtype='<i2').astype(np.int32)
            # Three independently rounded PCM components have a mathematical two-LSB bound.
            error=int(np.max(np.abs(saved['mix']-saved['clean']-saved['click']-saved['noise'])))
            if error>2:raise ValueError('Saved PCM component sum exceeds quantization bound')
            truth['component_sum_check']={'maximum_error_lsb':error,'bound_lsb':2}
            # Reopen the saved clean PCM for the linear missing-F0 proof.
            if case['cohort']=='missing-f0-sustain':
                import numpy as np
                with wave.open(str(folder/'clean.wav'), 'rb') as handle: actual=np.frombuffer(handle.readframes(handle.getnframes()), dtype='<i2')
                truth['missing_f0_construction_check'] = missing_f0_fit(actual)
            truth['source'] = components['mix']; truth['artifacts'] = components
            path = folder/'truth.json'; write(path, truth, True)
            rows.append({**{key: case[key] for key in ('id','seed','cohort','duration_seconds')}, 'source': components['mix'],
                         'components': components, 'truth': {'path': str(path.relative_to(output)), 'sha256': digest(path)}})
            if time.monotonic()-started>120:raise ValueError('Generator deadline exceeded')
        index = {'schema_version': 2, 'suite': 'phrase-order-null-v1', 'case_count': 10,
                 'total_duration_seconds': 80, 'cases': rows, 'plan_sha256': digest(plan_path),
                 'settings_sha256': digest(SETTINGS_PATH), 'runner_sha256': digest(__file__),
                 'instrument_registry_sha256': admitted['instrument_sha256'], 'truth_supplied_to_discovery': False}
        write(output/'fixtures.json', index, True)
        return {'path': str(output/'fixtures.json'), 'sha256': digest(output/'fixtures.json')}
    except Exception as exc:
        write(output/'generation-failure.json', {'status': 'partial_generator_no_inference', 'reason': str(exc), 'completed_cases': rows})
        raise


def child(source, target, identity):
    import numpy as np
    if digest(source)!=identity: raise ValueError('Opaque audio identity mismatch')
    sources=target.parent.parent/'sources'
    rhythm=module(sources/'rhythm.py','order_rhythm')
    frontend=module(sources/'guitar_features.cache_worker.py','order_frontend')
    samples=rhythm.decode(source)
    if len(samples)!=128000: raise ValueError('Expected exactly eight seconds analysis PCM')
    analysis=rhythm.analyze(samples,source_start=0.,bpm=None,backend='librosa')
    analysis['source']={'path':str(source),'sha256':identity}; write(target/'analysis.json',analysis)
    grid=analysis.get('click_grid') or {}
    bpm=grid.get('bpm') or (analysis.get('selected_periodicity') or {}).get('bpm')
    if bpm is None:
        result={'status':'unseeded_pulse_unavailable','source_sha256':identity,
                'arms':{'Bcontrol':[],'Border':[]},'proposal_universe':[],'audit':[],
                'performance_issue_confirmed':False,'inference_reference_labels_supplied':False}
    else:
        period=60/bpm;origin=max(0,float(grid.get('phase_seconds_audio_relative',0))%period)
        frontend.phrases_librosa(samples,bpm,origin)
        cache=frontend._ablation_cache; path=target/'features.npz';np.savez_compressed(path,**cache)
        frozen_arms().check_cache_archive(path)
        result=build(cache,period,origin,8.)
        result.update(cache_sha256=digest(path),source_sha256=identity)
    result.update(source_read=True,source_audio_decoded=True,decoded_sample_count=len(samples),
                  settings_sha256=digest(SETTINGS_PATH),runner_sha256=digest(__file__),
                  decoded_sample_rate=16000,decode_shared_by_primitives=True,
                  pulse_provenance='same_source_unseeded_analysis_not_generator_bpm')
    write(target/'result.json',result)
    if digest(source)!=identity:raise ValueError('Opaque source changed during inference')


def deadline(started, phase):
    remaining=600-(time.monotonic()-started)
    if remaining<=0:raise ValueError(f'Overall deadline exceeded during {phase}')
    return remaining


def owned_group_live(pgid):
    try:os.killpg(pgid,0);return True
    except ProcessLookupError:return False


def cleanup_owned_group(process, receipts, reason):
    """Only PGID created by this Popen(start_new_session=True), even after leader exit."""
    pgid=process.pid
    if not owned_group_live(pgid):return
    receipt={'actor':'phrase_dag','target_pgid':pgid,'leader_pid':process.pid,
             'ownership':'just_spawned_start_new_session_group','reason':reason,
             'ruling':'R-N11','prior_state':{'leader_poll':process.poll(),'owned_group_live':True}}
    os.killpg(pgid,signal.SIGTERM)
    until=time.monotonic()+2
    while owned_group_live(pgid) and time.monotonic()<until:time.sleep(.02)
    if owned_group_live(pgid):os.killpg(pgid,signal.SIGKILL)
    try:process.wait(timeout=2)
    except subprocess.TimeoutExpired:receipt['result']='group_cleanup_unverified';receipts.append(receipt);raise ValueError('Owned group cleanup unverified')
    until=time.monotonic()+2
    while owned_group_live(pgid) and time.monotonic()<until:time.sleep(.02)
    receipt['result']='group_signalled_and_leader_reaped' if not owned_group_live(pgid) else 'group_cleanup_unverified'
    receipts.append(receipt)
    if receipt['result']=='group_cleanup_unverified':raise ValueError('Owned descendants remain after group cleanup')


def executable_preflight(environment, started, signals=None):
    s=settings();receipts={};signals=[] if signals is None else signals
    for name,receipt in s['media_executables'].items():
        path=Path(receipt['path'])
        if not path.is_absolute() or not path.is_file() or not os.access(path,os.X_OK) or digest(path)!=receipt['sha256']:
            raise ValueError('Pinned media executable missing, nonexecutable, or changed')
        with tempfile.TemporaryFile() as stdout,tempfile.TemporaryFile() as stderr:
            process=subprocess.Popen([str(path),'-version'],stdout=stdout,stderr=stderr,env=environment,start_new_session=True)
            try:code=process.wait(timeout=min(5,deadline(started,'executable_preflight')))
            except subprocess.TimeoutExpired:
                cleanup_owned_group(process,signals,'executable_preflight_deadline');raise ValueError('Media executable preflight deadline exceeded')
            cleanup_owned_group(process,signals,'preflight_exited_leader_descendants')
            if stdout.tell()>65536 or stderr.tell()>65536:raise ValueError('Media version output byte cap exceeded')
            stdout.seek(0);raw=stdout.read(65537);line=raw.decode('utf-8',errors='strict').splitlines()[0] if raw else ''
            if code!=0 or not line.startswith(receipt['version_prefix']):raise ValueError('Pinned media executable version disagrees')
            receipts[name]={**receipt,'version_first_line':line,'version_stdout_sha256':hashlib.sha256(raw).hexdigest(),'exit_code':code}
    return receipts,signals


def verify_snapshot(bank_path, bank_sha, output, receipt, originals):
    expected={ROOT/'scripts/rhythm.py':RHYTHM_SHA,ROOT/'scripts/guitar_features.py':FRONTEND_SHA,
              ROOT/'scripts/phrase_evaluate.py':EVALUATOR_SHA,ARMS_PATH:ARMS_SHA,SETTINGS_PATH:SETTINGS_SHA,
              ROOT/'program/instrument.json':receipt['instrument_registry_sha256'],
              Path(__file__):receipt['runner_sha256'],bank_path:bank_sha}
    expected.update({output/name:sha for name,sha in receipt['copied_source_hashes'].items()})
    expected.update({path:sha for path,sha in originals})
    for row in receipt['cases']:
        expected[output/row['result']]=row['result_sha256']
        expected[output/'inputs'/f"audio-{row['ordinal']:02d}.wav"]=row['source_sha256']
        expected.update({output/name:sha for name,sha in row['artifact_hashes'].items()})
    if any(digest(path)!=sha for path,sha in expected.items()):raise ValueError('Frozen source, settings, cache receipt, prediction, or audio changed')
    for name,executable in receipt['media_preflight'].items():
        if digest(executable['path'])!=executable['sha256']:raise ValueError('Media executable changed after preflight')


def evaluate(bank, bank_dir, output, rows, on_truth_open=None):
    """Called only after every prediction has been saved and hash-bound."""
    evaluated=[]; common=[]
    for case,row in zip(bank['cases'],rows):
        truth=read(safe(bank_dir/case['truth']['path'],bank_dir,True),case['truth']['sha256'],opened=on_truth_open)
        prediction=read(output/row['result'],row['result_sha256'])
        if truth['source']['sha256']!=row['source_sha256']:raise ValueError('Truth/source binding changed')
        if len(truth['recurrence_pairs'])>1:raise ValueError('Preregistered one-reference-pair bound exceeded')
        if prediction.get('performance_issue_confirmed') is not False or set(prediction['arms'])!={'Bcontrol','Border'}:
            raise ValueError('Unsupported confirmed claim or changed arm set')
        if any(len(candidates)>10 or any(candidate.get('performance_issue_confirmed',False) is not False for candidate in candidates) for candidates in prediction['arms'].values()):
            raise ValueError('Unsupported candidate claim or pair cap violated')
        scores={}; maps={}
        for arm,candidates in prediction['arms'].items():
            metrics=[recurrence_metrics(truth['recurrence_pairs'],candidates,8.,threshold) for threshold in (.5,.75)]
            maps[arm]={};offsets=[]
            for match in metrics[0]['matches']:
                ref=pair_spans(truth['recurrence_pairs'][match['reference_index']],8.)
                estimate=pair_spans(candidates[match['estimate_index']],8.)
                value=[estimate[i][j]-ref[i][j] for i in (0,1) for j in (0,1)]
                maps[arm][match['reference_index']]=value;offsets.extend(value)
            scores[arm]={'pair_metrics':metrics,'candidate_count':len(candidates),'negative_reference':not truth['recurrence_pairs'],
                         'matched_endpoint_offsets_at_primary_iou_seconds':offsets,
                         'unmatched_reference_ids_at_primary_iou':[ref.get('id',str(i)) for i,ref in enumerate(truth['recurrence_pairs']) if i not in maps[arm]]}
        control,order=maps['Bcontrol'],maps['Border'];shared=sorted(control.keys()&order.keys())
        common.append({'id':case['id'],'seed':case['seed'],'common_reference_indices':shared,
                       'lost_reference_indices':sorted(control.keys()-order.keys()),'gained_reference_indices':sorted(order.keys()-control.keys()),
                       'endpoint_count':4*len(shared),'control_signed_offsets_seconds':[v for i in shared for v in control[i]],
                       'order_signed_offsets_seconds':[v for i in shared for v in order[i]],
                       'control_mean_absolute_error_seconds':sum(abs(v) for i in shared for v in control[i])/(4*len(shared)) if shared else None,
                       'order_mean_absolute_error_seconds':sum(abs(v) for i in shared for v in order[i])/(4*len(shared)) if shared else None})
        evaluated.append({'id':case['id'],'seed':case['seed'],'cohort':case['cohort'],'scores':scores,
                          'truth_sha256':case['truth']['sha256'],'result_sha256':row['result_sha256'],
                          'reference_pair_count':len(truth['recurrence_pairs'])})
    aggregate={}
    for scope,selected in [('all',evaluated)]+[(f'seed{seed}',[r for r in evaluated if r['seed']==seed]) for seed in (419,523)]:
        aggregate[scope]={}
        for arm in ('Bcontrol','Border'):
            aggregate[scope][arm]=[]
            for index,threshold in enumerate((.5,.75)):
                tp,fp,fn=[sum(r['scores'][arm]['pair_metrics'][index][key] for r in selected) for key in ('tp','fp','fn')]
                aggregate[scope][arm].append({'iou_threshold':threshold,'tp':tp,'fp':fp,'fn':fn,
                    'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,
                    'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
                    'negative_false_candidates_by_cohort':{cohort:sum(r['scores'][arm]['candidate_count'] for r in selected if r['cohort']==cohort)
                        for cohort in ('low32-sustain','missing-f0-sustain','click-noise-only')}})
    gates={}
    for seed in (419,523):
        baseline=aggregate[f'seed{seed}']['Bcontrol'][0];order=aggregate[f'seed{seed}']['Border'][0]
        negative_control=sum(baseline['negative_false_candidates_by_cohort'].values())
        negative_order=sum(order['negative_false_candidates_by_cohort'].values())
        gates[f'seed{seed}']={'negative_false_candidates_strictly_lower':negative_order<negative_control,
            'primary_recall_not_lower':order['recall'] is not None and baseline['recall'] is not None and order['recall']>=baseline['recall'],
            'qualification':'relative_research_criterion_only_not_absolute_accuracy_or_acceptance'}
    return {'schema_version':1,'status':'completed_isolated_order_null_measurements','cases':evaluated,
            'aggregate':aggregate,'common_reference_endpoints':common,'settings_retuned':False,
            'relative_research_criteria':gates,
            'all_predictions_saved_before_truth_read':True,'ground_truth_scope':'generator_only_not_musician',
            'performance_issue_confirmed':False,'listening_accepted':False,'canonical_defaults_activated':False}


def runner(bank_path, bank_sha, output):
    started=time.monotonic()
    bank_path=safe(bank_path,ROOT/'artifacts/experiments/phrase-window-ablation',True)
    bank=read(bank_path,bank_sha);s=settings()
    expected=[(seed,cohort) for seed in s['seeds'] for cohort in s['cohorts']]
    if bank.get('suite')!=s['suite'] or bank.get('settings_sha256')!=digest(SETTINGS_PATH) or bank.get('runner_sha256')!=digest(__file__) or bank.get('case_count')!=10 or bank.get('total_duration_seconds')!=80:
        raise ValueError('Frozen new bank metadata mismatch')
    if [(r['seed'],r['cohort']) for r in bank['cases']]!=expected:raise ValueError('Case set/order changed')
    if bank.get('instrument_registry_sha256')!=digest(ROOT/'program/instrument.json'):raise ValueError('Instrument context changed')
    if digest(ROOT/'scripts/rhythm.py')!=RHYTHM_SHA or digest(ROOT/'scripts/guitar_features.py')!=FRONTEND_SHA:
        raise ValueError('Canonical primitive changed after preregistration')
    frozen_arms();output=safe(output,ROOT/'artifacts/experiments/phrase-window-ablation')
    if output.exists():raise ValueError('Choose new immutable experiment directory')
    # Validate all source receipts and native headers before output allocation.
    sources_to_read=[]
    for case in bank['cases']:
        deadline(started,'native_source_prevalidation')
        source=safe(bank_path.parent/case['source']['path'],bank_path.parent,True)
        if source.stat().st_size>1_000_000 or digest(source)!=case['source']['sha256']:raise ValueError('Source hash/size invalid')
        with wave.open(str(source),'rb') as handle:
            if (handle.getframerate(),handle.getnchannels(),handle.getsampwidth(),handle.getnframes())!=(48000,1,2,384000):raise ValueError('Native PCM extent invalid')
        sources_to_read.append(source)
    output.mkdir(parents=True);sources=output/'sources';sources.mkdir();(output/'inputs').mkdir();(output/'discovery').mkdir()
    for name in ('rhythm.py','guitar_features.py'):shutil.copyfile(ROOT/'scripts'/name,sources/name)
    shutil.copyfile(__file__,sources/'runner.frozen.py');shutil.copyfile(SETTINGS_PATH,sources/'settings.frozen.json')
    shutil.copyfile(ARMS_PATH,sources/'original-arms.frozen.py')
    text=(sources/'guitar_features.py').read_text();needle='    observations = discover_phrase_features(pulse_features, period, duration, onset_times, start, pulse_centroids)'
    if text.count(needle)!=1:raise ValueError('Unrecognized pinned frontend cache hook')
    text=text.replace(needle,'    global _ablation_cache\n    _ablation_cache = {"features":frame_features,"times":frame_times,"centroid":centroid,"onsets":onset_times}\n'+needle)
    (sources/'guitar_features.cache_worker.py').write_text(text)
    # Exact builder executables are closed settings, not mutable historical strings.
    env={key:os.environ[key] for key in ('PATH','HOME','TMPDIR','LANG','LC_ALL') if key in os.environ}
    env.update({key:'2' for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS')})
    env.update(FFMPEG=s['media_executables']['ffmpeg']['path'],FFPROBE=s['media_executables']['ffprobe']['path'])
    receipt={'schema_version':1,'status':'discovery_running_truth_unopened','cases':[],
             'bank_index_sha256':bank_sha,'settings_sha256':digest(SETTINGS_PATH),'runner_sha256':digest(__file__),
             'unique_audio_seconds':80,'numerical_threads':2,'reference_labels_supplied':False,
             'truth_opened':False,'evaluator_sha256':EVALUATOR_SHA,'signal_receipts':[],
             'instrument_registry_sha256':bank['instrument_registry_sha256'],
             'copied_source_hashes':{str(path.relative_to(output)):digest(path) for path in sources.iterdir()}}
    write(output/'run.json',receipt)
    try:
        preflight,_=executable_preflight(env,started,receipt['signal_receipts'])
    except Exception:
        receipt['status']='preflight_failed_truth_unopened';write(output/'run.json',receipt);raise
    receipt['media_preflight']=preflight;write(output/'run.json',receipt)
    for ordinal,(case,source) in enumerate(zip(bank['cases'],sources_to_read),1):
        if time.monotonic()-started>=600:raise ValueError('Overall deadline exceeded before next child')
        alias=output/'inputs'/f'audio-{ordinal:02d}.wav';shutil.copyfile(source,alias)
        target=output/'discovery'/f'case-{ordinal:02d}';target.mkdir()
        argv=[sys.executable,str(Path(__file__).resolve()),'--child','--input',str(alias),'--target',str(target),'--identity',case['source']['sha256']]
        with (target/'worker.stdout').open('wb') as stdout,(target/'worker.stderr').open('wb') as stderr:
            process=subprocess.Popen(argv,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
            row={'id':case['id'],'ordinal':ordinal,'pid':process.pid,'owned_pgid':process.pid,'start_new_session':True,
                 'argv':argv,'source_sha256':case['source']['sha256'],'status':'running'}
            receipt['cases'].append(row);write(output/'run.json',receipt)
            try:code=process.wait(timeout=min(120,max(.1,600-(time.monotonic()-started))))
            except subprocess.TimeoutExpired:
                code=-1
            finally:
                try:cleanup_owned_group(process,receipt['signal_receipts'],'worker_timeout_or_exited_leader_descendants')
                except Exception:
                    receipt['status']='owned_cleanup_failed_truth_unopened';write(output/'run.json',receipt);raise
        row.update(exit_code=code,status='completed' if code==0 else 'failed')
        if code!=0:
            receipt['status']='partial_discovery_failed_truth_unopened';write(output/'run.json',receipt);return 1
        row.update(result=str((target/'result.json').relative_to(output)),result_sha256=digest(target/'result.json'))
        row['artifact_hashes']={str(path.relative_to(output)):digest(path) for path in (target/'analysis.json',target/'features.npz') if path.exists()}
        prediction=read(target/'result.json',row['result_sha256'])
        if (target/'features.npz').exists() and prediction.get('cache_sha256')!=digest(target/'features.npz'):
            raise ValueError('Prediction/cache binding mismatch')
        write(output/'run.json',receipt)
    receipt['status']='all_predictions_saved_and_hashed_truth_unopened';write(output/'run.json',receipt)
    deadline(started,'pretruth_verification')
    originals=[(source,case['source']['sha256']) for case,source in zip(bank['cases'],sources_to_read)]
    verify_snapshot(bank_path,bank_sha,output,receipt,originals)
    deadline(started,'before_truth_open')
    receipt['status']='evaluation_starting_truth_unopened';write(output/'run.json',receipt)
    def on_truth_open():
        if not receipt['truth_opened']:
            receipt['truth_opened']=True;receipt['status']='evaluation_running_truth_opened';write(output/'run.json',receipt)
        deadline(started,'actual_truth_open')
    result=evaluate(bank,bank_path.parent,output,receipt['cases'],on_truth_open)
    deadline(started,'post_evaluation')
    verify_snapshot(bank_path,bank_sha,output,receipt,originals)
    write(output/'evaluation.json',result,True)
    deadline(started,'evaluation_sealing')
    receipt.update(status=result['status'],evaluation_sha256=digest(output/'evaluation.json'),elapsed_seconds=time.monotonic()-started)
    write(output/'run.json',receipt);deadline(started,'final_receipt_sealing')
    print(json.dumps({'output':str(output/'evaluation.json'),'sha256':receipt['evaluation_sha256'],'aggregate':result['aggregate']}));return 0


class SourceTests(unittest.TestCase):
    def test_fixed_first_rotation_oracle_and_bad_both_rotation(self):
        import numpy as np
        candidate={'pulse_count':4,'first_start_seconds':0.,'second_start_seconds':4.}
        motif=np.array([[1.,0.],[0.,1.],[-1.,0.],[0.,-1.]])
        evidence=order_evidence(candidate,np.vstack([motif,motif]),1.,0.)
        self.assertEqual(evidence['rotation_offsets'],[1,2,3]);self.assertAlmostEqual(evidence['true_cosine'],1)
        self.assertEqual(evidence['rotated_cosines'],[0.,-1.,0.]);self.assertAlmostEqual(evidence['margin'],1)
        self.assertAlmostEqual(float(np.sum(np.roll(motif,1,axis=0)**2)/np.sum(motif**2)),1)
        flat=order_evidence(candidate,np.ones((8,2)),1.,0.);self.assertAlmostEqual(flat['margin'],0)

    def test_cap_ranking_equal_and_order_filter_before_cap(self):
        import numpy as np
        class Background:
            def contrast(self,*_):return {'contrast':.5,'match_cosine':1.}
        z=np.tile([[1.,0.],[0.,1.],[-1.,0.],[0.,-1.]],(20,1))
        proposals=[{'pulse_count':4,'first_start_seconds':float(i*4),'second_start_seconds':float(i*4+4)} for i in range(12)]
        selected,audit=select(proposals,z,1.,0.,Background())
        self.assertEqual([r['original_candidate_index'] for r in selected['Bcontrol']],list(range(10)))
        self.assertEqual([r['original_candidate_index'] for r in selected['Border']],list(range(10)))
        self.assertEqual(sum(r['order_status']=='ranked_cap_excluded' for r in audit),2)
        selected,audit=select(proposals,np.ones((80,2)),1.,0.,Background())
        self.assertEqual(len(selected['Bcontrol']),10);self.assertEqual(selected['Border'],[])
        self.assertTrue(all(r['order_status']=='order_margin_excluded' for r in audit))

    def test_metadata_fresh_and_nuisance_shared(self):
        value=plan();self.assertEqual(value['case_count'],10);self.assertEqual(value['total_duration_seconds'],80)
        self.assertEqual({row['seed'] for row in value['cases']},{419,523})
        self.assertEqual(len([r for r in value['cases'] if 'recurrence' not in r['cohort']]),6)
        for seed in (419,523):
            self.assertTrue(all(r['parameters']==parameters(seed) for r in value['cases'] if r['seed']==seed))

    def test_tiny_source_render_linear_missing_f0_and_no_labels_in_build(self):
        import numpy as np
        # Low-rate algebraic source test only: no 48k waveform, bank, inference, or saved audio.
        row=next(r for r in plan()['cases'] if r['cohort']=='missing-f0-sustain')
        pcm,truth=render(row,rate=1000)
        fit=missing_f0_fit(pcm['clean'],rate=1000);self.assertLess(fit['fundamental_amplitude'],5e-5)
        self.assertEqual(truth['recurrence_pairs'],[])
        row={**row,'cohort':'click-noise-only'};only,_=render(row,rate=1000)
        self.assertTrue(np.all(only['clean']==0));self.assertTrue(np.array_equal(only['noise'],pcm['noise']))
        self.assertTrue(np.array_equal(only['click'],pcm['click']))

    def test_paths_and_finite_cache_guard(self):
        import numpy as np
        with self.assertRaises(ValueError):safe(ROOT/'artifacts/experiments/phrase-window-ablation/../escape',ROOT/'artifacts/experiments/phrase-window-ablation')
        with self.assertRaises(ValueError):read(SETTINGS_PATH,expected='0'*64)
        with self.assertRaises(ValueError):guarded_json('{"x":1e400}')
        arms=frozen_arms();cache={'features':np.zeros((2,20)),'times':np.arange(20)*.05,'centroid':np.ones(20),'onsets':[]}
        cache['features'][0,0]=float('nan')
        with self.assertRaises(ValueError):arms.validate(cache,.5,0.,1.)

    def test_evaluation_full_reference_and_common_intersection(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();pair={'id':'repeat','first_span_seconds':[1.,2.],'second_span_seconds':[4.,5.]}
            source_sha='a'*64;truth={'source':{'sha256':source_sha},'recurrence_pairs':[pair]}
            write(root/'truth.json',truth,True)
            prediction={'performance_issue_confirmed':False,'arms':{'Bcontrol':[pair],'Border':[]}}
            write(root/'result.json',prediction,True)
            case={'id':'synthetic','seed':419,'cohort':'palm-recurrence','truth':{'path':'truth.json','sha256':digest(root/'truth.json')}}
            result=evaluate({'cases':[case]},root,root,[{'source_sha256':source_sha,'result':'result.json','result_sha256':digest(root/'result.json')}])
            self.assertEqual(result['aggregate']['all']['Border'][0]['fn'],1)
            common=result['common_reference_endpoints'][0];self.assertEqual(common['lost_reference_indices'],[0])
            self.assertEqual(common['endpoint_count'],0);self.assertEqual(common['order_signed_offsets_seconds'],[])
            self.assertIsNone(common['control_mean_absolute_error_seconds'])
            prediction['performance_issue_confirmed']=True;write(root/'result.json',prediction)
            with self.assertRaises(ValueError):evaluate({'cases':[case]},root,root,[{'source_sha256':source_sha,'result':'result.json','result_sha256':digest(root/'result.json')}])

    def test_control_is_exact_original_B_and_source_pins(self):
        import numpy as np
        arms=frozen_arms();z=np.tile([[1.,0.],[0.,1.],[-1.,0.],[0.,-1.]],(5,1))
        proposals=[{'pulse_count':2,'first_start_seconds':float(i),'second_start_seconds':float(i+8)} for i in range(5)]
        original,_=arms.rank(proposals,z,1.,0.)
        selected,_=select(proposals,z,1.,0.,arms)
        def without_order(rows):return [{k:v for k,v in row.items() if k!='order_evidence'} for row in rows]
        self.assertEqual(without_order(selected['Bcontrol']),original)
        self.assertEqual(digest(ROOT/'scripts/guitar_features.py'),FRONTEND_SHA)
        self.assertEqual(digest(ROOT/'scripts/rhythm.py'),RHYTHM_SHA)

    def test_source_event_axes_and_negative_scope(self):
        value=plan()
        for row in [r for r in value['cases'] if r['seed']==419 and 'recurrence' in r['cohort']]:
            _,truth=render(row,rate=1000)
            self.assertEqual(len(truth['recurrence_pairs']),1);self.assertEqual(len(truth['generated_score']['events']),12)
            for event in truth['generated_score']['events']:
                self.assertEqual(event['onset_native_sample']/1000,event['onset_source_seconds'])
                self.assertGreater(event['duration_samples'],0)
                self.assertLessEqual(event['onset_native_sample']+event['duration_samples'],8000)
            if row['cohort']=='legato-recurrence':
                self.assertEqual(sum(e['articulation']=='picked_attack' for e in truth['generated_score']['events']),2)

    def test_exited_leader_owned_descendant_cleanup_and_deadline(self):
        from unittest.mock import patch
        class Owned:
            pid=999999
            def poll(self):return 0
            def wait(self,timeout):return 0
        receipts=[]
        with patch(__name__+'.owned_group_live',side_effect=[True,False,False,False,False]),patch('os.killpg') as signalled:
            cleanup_owned_group(Owned(),receipts,'source_test_exited_leader')
            signalled.assert_called_once_with(999999,signal.SIGTERM)
        self.assertEqual(receipts[0]['prior_state']['leader_poll'],0)
        self.assertEqual(receipts[0]['result'],'group_signalled_and_leader_reaped')
        with patch('time.monotonic',return_value=601):
            with self.assertRaises(ValueError):deadline(0,'source_test_evaluation')

    def test_evaluator_closed_executable_and_snapshot_pins(self):
        self.assertEqual(digest(ROOT/'scripts/phrase_evaluate.py'),EVALUATOR_SHA)
        for name,receipt in settings()['media_executables'].items():
            self.assertEqual(Path(receipt['path']).name,name);self.assertEqual(digest(receipt['path']),receipt['sha256'])
            self.assertTrue(os.access(receipt['path'],os.X_OK))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();path=root/'case.json';write(path,{'ok':True},True)
            receipt={'runner_sha256':digest(__file__),'copied_source_hashes':{'case.json':digest(path)},'cases':[],
                     'media_preflight':settings()['media_executables'],'instrument_registry_sha256':digest(ROOT/'program/instrument.json')}
            verify_snapshot(SETTINGS_PATH,SETTINGS_SHA,root,receipt,[])
            write(path,{'ok':False})
            with self.assertRaises(ValueError):verify_snapshot(SETTINGS_PATH,SETTINGS_SHA,root,receipt,[])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path);parser.add_argument('--generate',action='store_true')
    parser.add_argument('--bank-index',type=Path);parser.add_argument('--bank-sha256');parser.add_argument('--output',type=Path)
    parser.add_argument('--child',action='store_true');parser.add_argument('--input',type=Path);parser.add_argument('--target',type=Path);parser.add_argument('--identity')
    parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    try:
        if args.self_test:return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SourceTests)).wasSuccessful() else 1
        if args.child:child(args.input,args.target,args.identity);return 0
        if args.generate:
            if not args.plan or not args.output:parser.error('generate requires plan/output')
            print(json.dumps(generate(args.plan,args.output)));return 0
        if args.bank_index:
            if not args.bank_sha256 or not args.output:parser.error('run requires exact bank-sha256 and new output')
            return runner(args.bank_index,args.bank_sha256,args.output)
        if args.plan:
            path=safe(args.plan,ROOT/'artifacts/experiments/phrase-window-ablation');path.parent.mkdir(parents=True,exist_ok=True)
            write(path,plan(),True);print(json.dumps({'plan':str(path),'sha256':digest(path)}));return 0
        parser.error('choose plan, generate, bank-index, or self-test')
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as exc:
        if args.output and args.output.is_dir():
            previous=read(args.output/'run.json') if (args.output/'run.json').is_file() else {}
            opened=previous.get('truth_opened',False)
            failure={'status':'failed_after_truth_open_no_adoption' if opened else 'failed_truth_unopened_no_adoption',
                     'reason':str(exc),'truth_opened':opened,'signal_receipts':previous.get('signal_receipts',[])}
            write(args.output/'failure.json',failure)
            if previous:
                previous['status']=failure['status'];write(args.output/'run.json',previous)
        print(f'order-null experiment: {exc}',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
