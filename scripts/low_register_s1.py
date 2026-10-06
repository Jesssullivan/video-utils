#!/usr/bin/env python3
"""Unregistered bounded S1 known-component/counterfactual restoration experiment."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'artifacts' / 'benchmarks'
MAX_JSON = 2_000_000
MAX_AUDIO_BYTES = 768 * 1024 * 1024
ARMS = ('bypass', 'captured_nr8', 'captured_nr10', 'protected_mask')
GATES = {'fundamental_db': [-.5, .1], 'attack_tail_legato_db': [-1., .5],
         'attack_centroid_ms': 2., 'noise_broadband_attenuation_db': 3.,
         'conditional_additivity_max_abs': 4e-7}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def numeric():
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        os.environ[name] = '2'
    import numpy as np
    from scipy.io import wavfile
    import low_register_fixtures as fixtures
    import low_register_denoise_probe as probe
    return np, wavfile, fixtures, probe


def declaration():
    # Importing this fixture module does not import numerical dependencies.
    import low_register_fixtures as fixtures
    cases = copy.deepcopy(fixtures.declaration()['design']['cases'])
    near = copy.deepcopy(cases[3])
    near.update(alias='lr09', kind='separated-line', seed=2026100608)
    near['parameters']['fan_line_hz'] = fixtures.frequency(24) + .75
    near['s1_collision_scope'] = 'near_collision_not_unique_separation'
    cases.append(near)
    return {'schema_version': 1, 'kind': 's1_low_register_frozen_plan', 'cases': cases,
            'arms': list(ARMS), 'afftdn': {'noise_floor_db': -40, 'adaptivity': 0,
            'gain_smooth': 0, 'track_noise': 0, 'capture_seconds': [0, .8]},
            'experimental_mask': {'low_ceiling_db': 0, 'broadband_ceiling_db': 8,
                                 'noise_density_scale': 1},
            'gates': GATES, 'deadline_seconds': 180, 'threads': 2,
            'max_audio_bytes': MAX_AUDIO_BYTES, 'source_seconds': 72,
            'truth_scope': 'generated_only; afftdn paired counterfactual, mask conditional',
            'hashes': {str(p.relative_to(ROOT)): digest(p) for p in
                       [Path(__file__), ROOT/'scripts/low_register_fixtures.py',
                        ROOT/'scripts/low_register_denoise_probe.py', ROOT/'program/instrument.json']}}


def artifact_path(value, *, fresh=False):
    p = Path(value).expanduser().absolute()
    if '..' in p.parts or p == ARTIFACTS or not p.is_relative_to(ARTIFACTS):
        raise ValueError('Expected path beneath artifacts/benchmarks')
    if any(q.is_symlink() for q in (p, *p.parents)):
        raise ValueError('Symlink components refused')
    if fresh and p.exists():
        raise ValueError('Destination already exists')
    return p


def write_json(path, value):
    raw = canonical(value) + b'\n'
    if len(raw) > MAX_JSON:
        raise ValueError('JSON byte bound exceeded')
    with Path(path).open('xb') as stream:
        stream.write(raw)


def read_plan(path):
    p = artifact_path(path)
    if not p.is_file() or p.stat().st_size > MAX_JSON:
        raise ValueError('Expected bounded plan file')
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError('Duplicate plan key')
            out[key] = value
        return out
    value = json.loads(p.read_bytes(), object_pairs_hook=pairs,
                       parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite plan')))
    if canonical(value) != canonical(declaration()):
        raise ValueError('Plan/helper/dependencies changed')
    return value, digest(p)


def check_deadline(deadline):
    if time.monotonic() >= deadline:
        raise TimeoutError('Overall experiment deadline exceeded')


def run_ffmpeg(ffmpeg, args, deadline, log):
    check_deadline(deadline)
    # subprocess.run kills and waits only its own child on timeout.
    result = subprocess.run([ffmpeg, '-hide_banner', '-nostdin', '-threads', '2',
                             '-filter_complex_threads', '2', '-y', *args],
                            capture_output=True, timeout=min(20, deadline-time.monotonic()))
    if len(result.stdout) + len(result.stderr) > 1_000_000:
        raise ValueError('FFmpeg output byte bound exceeded')
    Path(log).write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError('FFmpeg failed; inspect retained log')
    return result.stderr.decode('utf-8', errors='replace')


def calibration(ffmpeg, rate, nr, folder, deadline):
    np, wavfile, _, _ = numeric()
    x = np.zeros((rate, 1), dtype=np.float32)
    positions = [rate//4, rate*3//5]
    x[positions] = .75
    src, out = folder/f'cal-{rate}-{nr}.wav', folder/f'cal-{rate}-{nr}.out.wav'
    wavfile.write(src, rate, x[:, 0])
    run_ffmpeg(ffmpeg, ['-i', str(src), '-af', f'afftdn=nr={nr}:nf=-40:tn=0:gs=0:ad=0',
               '-c:a', 'pcm_f32le', str(out)], deadline, out.with_suffix('.log'))
    r, y = wavfile.read(out)
    expected = 2*(rate//80)
    offsets = []
    for pos in positions:
        a, b = pos-expected, pos+2*expected+1
        peak = a + int(np.argmax(np.abs(y[a:b])))
        if abs(y[peak]) < .1:
            raise ValueError('Calibration impulse not observable')
        offsets.append(peak-pos)
    if r != rate or len(y) != len(x) or offsets != [expected, expected]:
        raise ValueError('Unqualified afftdn insertion delay')
    return {'sample_rate': rate, 'nr': nr, 'delay_samples': expected,
            'measured_impulse_offsets': offsets}


def afftdn(ffmpeg, body_path, capture_path, rate, channels, count, nr, out, deadline):
    np, wavfile, _, _ = numeric()
    cap, guard, delay = round(.8*rate), math.ceil(.1*rate), 2*(rate//80)
    prefix = cap + guard
    graph = (f'[0:a]atrim=start_sample=0:end_sample={cap},asetpts=N/SR/TB,'
             f'apad=pad_len={guard}[training];[1:a]asetpts=N/SR/TB[body];'
             f'[training][body]concat=n=2:v=0:a=1,apad=pad_len={delay},'
             "asendcmd=c='0 afftdn sn start;0.8 afftdn sn stop',"
             f'afftdn=nr={nr}:nf=-40:tn=0:gs=0:ad=0,'
             f'atrim=start_sample={prefix+delay}:end_sample={prefix+delay+count},'
             'asetpts=N/SR/TB[out]')
    log = run_ffmpeg(ffmpeg, ['-i', str(capture_path), '-i', str(body_path),
                    '-filter_complex', graph, '-map', '[out]', '-c:a', 'pcm_f32le', str(out)],
                    deadline, out.with_suffix('.log'))
    bands = [line.split('bn=', 1)[1].split() for line in log.splitlines() if 'bn=' in line]
    if len(bands) != channels or any(len(v) != 15 for v in bands):
        raise ValueError('Captured profile not confirmed for each channel')
    r, y = wavfile.read(out)
    y = y[:, None] if y.ndim == 1 else y
    if r != rate or y.shape != (count, channels) or not np.isfinite(y).all():
        raise ValueError('Afftdn native extent/finite output differs')
    return y.astype(np.float64), [[float(v) for v in row] for row in bands]


def ratio(after, before):
    if before == 0:
        return {'value_db': None, 'status': 'zero_reference'}
    if after == 0:
        return {'value_db': None, 'status': 'complete_attenuation'}
    return {'value_db': 10*math.log10(after/before), 'status': 'measured'}


def score(clean, noise, mixture, output, guitar_response, noise_control, clean_control, truth, arm):
    np, _, _, probe = numeric()
    rate = truth['case']['sample_rate']
    events = truth['events']
    temporal = []
    fits = []
    legato = []
    for event in events:
        if event['kind'] == 'palm_mute':
            item = probe.temporal_metrics(clean, guitar_response, event, rate)
            item['kind'] = event['kind']
            temporal.append(item)
        if event['kind'] == 'connected_legato_no_internal_pick_attacks':
            a, b = event['start_sample']+round(.25*rate), event['end_sample']-round(.1*rate)
            legato.append({'start_sample': a, 'end_sample': b,
                          **ratio(float(np.sum(guitar_response[a:b]**2)), float(np.sum(clean[a:b]**2)))})
        if event['frequency_hz'] is not None:
            a, b = event['start_sample']+round(.1*rate), event['end_sample']-round(.1*rate)
            if b-a >= rate:
                harmonics = [int(h[0]) for h in truth['case']['parameters'].get('harmonics', [[1,1],[2,.25],[3,.15],[4,.1]])]
                fits.append(probe.harmonic_gain(clean, guitar_response, rate, a, b, event['frequency_hz'], harmonics))
    interaction = output-clean_control-noise_control
    guitar_energy = float(np.sum(clean**2))
    near = truth['case'].get('s1_collision_scope') is not None
    exact = truth['non_identifiable']
    fundamental_eligible = bool(truth['fundamental_gain_applicable'] and not near and not exact)
    fundamental = [h for fit in fits for h in fit.get('rows', []) if h['harmonic']==1]
    eligible = [h for h in fundamental if fundamental_eligible and h['status'] in ('measured','complete_attenuation')]
    alerts = []
    for h in eligible:
        if h['status']=='complete_attenuation' or not GATES['fundamental_db'][0] <= h['value_db'] <= GATES['fundamental_db'][1]:
            alerts.append('fundamental_preservation')
    for event in temporal:
        for label in ('attack_energy', 'tail_energy'):
            v = event[label]['value_db']
            if event[label]['status']=='complete_attenuation' or (v is not None and not -1 <= v <= .5):
                alerts.append(label)
        v = event['centroid_shift_ms']
        if v is not None and abs(v)>2:
            alerts.append('attack_centroid')
    for item in legato:
        if item['status']=='complete_attenuation' or (item['value_db'] is not None and not -1 <= item['value_db'] <= .5):
            alerts.append('legato_energy')
    noise_bands = {f'{lo}-{hi}': ratio(probe.band_power(noise_control,rate,lo,hi),
                                      probe.band_power(noise,rate,lo,hi))
                   for lo,hi in ((20,45),(45,120),(140,8000))}
    noise_eligible = truth['case']['parameters'].get('noise_rms', 0)>0
    broadband = noise_bands['140-8000']['value_db']
    if noise_eligible and broadband is not None and broadband > -3:
        alerts.append('noise_control_broadband')
    active = np.zeros(len(clean),dtype=bool)
    for event in events:
        active[event['start_sample']:event['end_sample']] = True
    return {'arm': arm, 'alias': truth['case']['alias'], 'kind': truth['case']['kind'],
        'metric_scope': 'conditional_known_components' if arm in ('bypass','protected_mask') else 'paired_counterfactual_not_stems',
        'guitar_response_energy': ratio(float(np.sum(guitar_response**2)), guitar_energy),
        'guitar_response_active_energy': ratio(float(np.sum(guitar_response[active]**2)),float(np.sum(clean[active]**2))),
        'active_sample_frame_denominator': int(np.count_nonzero(active)),
        'guitar_response_low_band': ratio(probe.band_power(guitar_response,rate,20,45),probe.band_power(clean,rate,20,45)),
        'guitar_response_relative_error': ratio(float(np.sum((guitar_response-clean)**2)),guitar_energy),
        'processed_mixture_relative_error': ratio(float(np.sum((output-clean)**2)),guitar_energy),
        'interaction_relative_energy': ratio(float(np.sum(interaction**2)),guitar_energy),
        'conditional_additivity_max_abs': float(np.max(np.abs(interaction))) if arm in ('bypass','protected_mask') else None,
        'noise_control_energy': ratio(float(np.sum(noise_control**2)),float(np.sum(noise**2))),
        'noise_control_band_power_change': noise_bands,
        'noise_control_is_mixture_residual': arm in ('bypass','protected_mask'),
        'harmonic_fits': fits, 'fundamental_gain_rows': fundamental,
        'palm_attack_tail': temporal, 'legato_sustain': legato,
        'processed_peak_abs': float(np.max(np.abs(output))),
        'clipped_sample_values': int(np.count_nonzero(np.abs(output)>=1)),
        'sample_value_denominator': int(output.size),
        'fundamental_gate_eligible': fundamental_eligible,
        'fundamental_eligible_channel_event_denominator': len(eligible),
        'fundamental_exclusion': 'collision_not_identifiable' if exact or near else
            ('missing_f0_or_no_guitar' if not fundamental_eligible else None),
        'palm_event_denominator': len(temporal), 'legato_event_denominator': len(legato),
        'broadband_noise_gate_eligible': noise_eligible,
        'quality_alerts': sorted(set(alerts)), 'exact_collision': exact, 'near_collision': near,
        'missing_f0_recovered': False, 'real_stem_recovered': False}


def run(plan_path, output, ffmpeg):
    started = time.monotonic()
    plan, plan_hash = read_plan(plan_path)
    dest = artifact_path(output, fresh=True)
    dest.mkdir(parents=True, exist_ok=False)
    deadline = started+plan['deadline_seconds']
    np, wavfile, fixtures, probe = numeric()
    completed = []
    try:
        version = subprocess.run([ffmpeg, '-version'], capture_output=True, timeout=5, check=True)
        ffmpeg_sha = digest(ffmpeg)
        write_json(dest/'plan.json',plan)
        jobs = []
        calibrations = []
        for rate in (44100,48000):
            for nr in (8,10):
                calibrations.append(calibration(ffmpeg,rate,nr,dest,deadline))
        # Generation is separately persisted. Denoiser inputs below are only mixtures/captures.
        for case in plan['cases']:
            check_deadline(deadline)
            folder = dest/case['alias']; folder.mkdir()
            arrays, truth = fixtures.components(case)
            oracle = fixtures.verify_oracles(arrays,case)
            for role in ('clean','fan','mixture'):
                wavfile.write(folder/(role+'.wav'),case['sample_rate'], arrays[role][:,0] if case['channels']==1 else arrays[role])
            write_json(folder/'truth.json',{**truth,'oracles':oracle})
        # Freeze all mixture-only outputs before reading oracle component WAVs.
        for case in plan['cases']:
            check_deadline(deadline)
            folder = dest/case['alias']
            rate,pcm = wavfile.read(folder/'mixture.wav')
            pcm=pcm[:,None] if pcm.ndim==1 else pcm
            pcm=pcm.astype(np.float64)
            config=probe.MaskConfig(rate,low_ceiling_db=0,noise_density_scale=1)
            frames=probe.analyze_native(pcm,config=config)
            capture=probe.fit_capture_density(pcm[:round(.8*rate)],config=config,
                    source_sha256=digest(folder/'mixture.wav'),decoded_start_sample=0,decoded_end_sample=round(.8*rate))
            gain=probe.derive_gain(frames,capture,config=config)
            np.save(folder/'mask.npy',gain.gains,allow_pickle=False)
            np.save(folder/'protected_mask-mixture.npy',probe.apply_frozen_gain(pcm,gain,config=config),allow_pickle=False)
            np.save(folder/'bypass-mixture.npy',pcm,allow_pickle=False)
            bands={}
            for nr in (8,10):
                arm=f'captured_nr{nr}'
                y,bands[arm]=afftdn(ffmpeg,folder/'mixture.wav',folder/'mixture.wav',rate,case['channels'],len(pcm),nr,folder/(arm+'-mixture.wav'),deadline)
                np.save(folder/(arm+'-mixture.npy'),y,allow_pickle=False)
            jobs.append({'alias':case['alias'],'mixture_sha256':digest(folder/'mixture.wav'),
                'captured_bands':bands,'sealed_hashes':{p.name:digest(p) for p in folder.glob('*.npy')}})
        write_json(dest/'sealed-mixtures.json',{'jobs':jobs,'all_mixture_outputs_saved_before_component_evaluation':True})
        sealed_hash=digest(dest/'sealed-mixtures.json')
        for case in plan['cases']:
            check_deadline(deadline)
            folder=dest/case['alias'];truth=json.loads((folder/'truth.json').read_text())
            components={}
            for role in ('clean','fan','mixture'):
                r,data=wavfile.read(folder/(role+'.wav'))
                data=data[:,None] if data.ndim==1 else data
                if r!=case['sample_rate'] or data.shape!=(case['sample_frames'],case['channels']):
                    raise ValueError('Component native extent mismatch')
                components[role]=data.astype(np.float64)
            clean,noise,mix=(components[k] for k in ('clean','fan','mixture'))
            for arm in ARMS:
                check_deadline(deadline)
                y=np.load(folder/(arm+'-mixture.npy'),allow_pickle=False)
                if arm=='bypass':
                    g,n,s=clean,noise,clean
                elif arm=='protected_mask':
                    config=probe.MaskConfig(case['sample_rate'],low_ceiling_db=0,noise_density_scale=1)
                    gains=np.load(folder/'mask.npy',allow_pickle=False)
                    frozen=probe.FrozenGain(gains,len(clean),case['channels'],probe.grid(config),config)
                    g=probe.apply_frozen_gain(clean,frozen,config=config)
                    n=probe.apply_frozen_gain(noise,frozen,config=config);s=g
                else:
                    nr=8 if arm=='captured_nr8' else 10
                    n,_=afftdn(ffmpeg,folder/'fan.wav',folder/'mixture.wav',case['sample_rate'],case['channels'],len(clean),nr,folder/(arm+'-fan-control.wav'),deadline)
                    s,_=afftdn(ffmpeg,folder/'clean.wav',folder/'mixture.wav',case['sample_rate'],case['channels'],len(clean),nr,folder/(arm+'-clean-control.wav'),deadline)
                    g=y-n
                for role,data in (('guitar-response',g),('noise-control',n),('clean-control',s)):
                    np.save(folder/(arm+'-'+role+'.npy'),data,allow_pickle=False)
                metric=score(clean,noise,mix,y,g,n,s,truth,arm)
                if metric['conditional_additivity_max_abs'] is not None and metric['conditional_additivity_max_abs']>GATES['conditional_additivity_max_abs']:
                    raise ValueError('Conditional component additivity failed')
                write_json(folder/(arm+'-metrics.json'),metric);completed.append(metric)
        if digest(dest/'sealed-mixtures.json')!=sealed_hash or read_plan(plan_path)[1]!=plan_hash:
            raise ValueError('Seal/source/plan changed')
        for job in jobs:
            folder=dest/job['alias']
            if digest(folder/'mixture.wav')!=job['mixture_sha256'] or any(digest(folder/name)!=sha for name,sha in job['sealed_hashes'].items()):
                raise ValueError('Sealed input/output changed')
        audio_bytes=sum(p.stat().st_size for p in dest.rglob('*') if p.suffix in ('.wav','.npy'))
        if audio_bytes>MAX_AUDIO_BYTES:
            raise ValueError('Audio artifact byte bound exceeded')
        check_deadline(deadline)
        result={'schema_version':1,'status':'synthetic_comparison_complete','plan_sha256':plan_hash,
                'helper_sha256':digest(__file__),'sealed_mixtures_sha256':sealed_hash,'calibrations':calibrations,
                'ffmpeg_sha256':ffmpeg_sha,'ffmpeg_version':version.stdout.decode().splitlines()[0],
                'case_count':9,'arm_count':4,'row_count':len(completed),'unique_source_seconds':72,
                'elapsed_seconds':time.monotonic()-started,'deadline_seconds':180,'audio_artifact_bytes':audio_bytes,
                'gates':GATES,'results':completed,'summary':summarize(completed),
                'actual_audio_processed':False,'master_changed':False,'default_adoption':False,
                'listening_acceptance':False,'truth_scope':plan['truth_scope']}
        write_json(dest/'results.json',result)
        return result
    except Exception as exc:
        write_json(dest/'failure.json',{'status':'failed','reason':str(exc),'completed_rows':len(completed),
                    'elapsed_seconds':time.monotonic()-started,'actual_audio_processed':False})
        raise


def summarize(rows):
    result={}
    for arm in ARMS:
        values=[r for r in rows if r['arm']==arm]
        result[arm]={'rows':len(values),'alert_rows':sum(bool(r['quality_alerts']) for r in values),
            'clipped_sample_values':sum(r['clipped_sample_values'] for r in values),
            'sample_value_denominator':sum(r['sample_value_denominator'] for r in values),
            'fundamental_eligible_channel_event_denominator':sum(r['fundamental_eligible_channel_event_denominator'] for r in values),
            'palm_event_denominator':sum(r['palm_event_denominator'] for r in values),
            'legato_event_denominator':sum(r['legato_event_denominator'] for r in values),
            'broadband_noise_case_denominator':sum(r['broadband_noise_gate_eligible'] for r in values),
            'collision_case_count':sum(r['near_collision'] or r['exact_collision'] for r in values)}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='operation',required=True)
    p=sub.add_parser('declare');p.add_argument('--output',required=True)
    p=sub.add_parser('run');p.add_argument('--plan',required=True);p.add_argument('--output',required=True)
    p.add_argument('--ffmpeg',default=os.environ.get('FFMPEG','ffmpeg'))
    args=parser.parse_args()
    if args.operation=='declare':
        p=artifact_path(args.output,fresh=True);p.parent.mkdir(parents=True,exist_ok=True)
        write_json(p,declaration());result={'status':'declaration_only','path':str(p),'sha256':digest(p)}
    else:
        result=run(args.plan,args.output,args.ffmpeg)
        result={k:v for k,v in result.items() if k!='results'}
    print(json.dumps(result,sort_keys=True,allow_nan=False))


if __name__=='__main__':main()
