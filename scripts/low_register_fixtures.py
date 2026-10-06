#!/usr/bin/env python3
"""Declare then generate a separate source-known low-register fixture bank.

No denoiser, real recording or public tool registration is invoked. Generated
components are evaluation oracles, never inputs to future mask estimation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'artifacts' / 'benchmarks'
SCHEMA = 'low-register-separability-v1'
MAX_JSON = 1_000_000
FLOAT32_ADD_TOL = 2e-7
MISSING_F0_TOL = 5e-5
MASK_ADD_TOL = 1e-10


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def frequency(midi):
    return 440 * 2 ** ((midi - 69) / 12)


def declaration():
    cases = [
        ('clean-sentinels',44100,1,{'sentinel_hz':32.0,'fundamental_hz':frequency(24),
          'spans':[[1,3.2],[4,7.4]],'gain':.12,'harmonics':[[1,1],[2,.25],[3,.15],[4,.1]]}),
        ('fan-only',48000,1,{'fan_line_hz':frequency(24),'fan_line_gain':.025,'noise_rms':.006}),
        ('exact-collision',48000,2,{'fundamental_hz':frequency(24),'guitar_gain':.12,
          'fan_line_hz':frequency(24),'fan_line_gain':.04,'fan_phases_radians':[0,math.pi/2],
          'alternative_transfer_gain':.02,'noise_rms':0.0}),
        ('separated-line',44100,1,{'fundamental_hz':frequency(24),'guitar_gain':.12,
          'fan_line_hz':113.0,'fan_line_gain':.04,'noise_rms':.006}),
        ('walking-saturated',48000,1,{'midi':[24,29,34,39],'starts_seconds':[1,2.5,4,5.5],
          'note_seconds':1.2,'guitar_gain':.11,'drive':3.8,
          'fan_line_hz':175.0,'fan_line_gain':.025,'noise_rms':.006}),
        ('palm-legato-saturated',44100,2,{'midi':[24,29,24,34,24,39],
          'starts_seconds':[1,1.5,2,2.75,3.5,4],'note_seconds':.4,'decay_seconds':.09,
          'legato_span_seconds':[5,7.35],'legato_midi':[24,29,34,39],
          'drive':3.8,'guitar_gain':.10,'quiet_legato_gain':.20,
          'fan_line_hz':frequency(24),'fan_line_gain':.018,'noise_rms':.006}),
        ('missing-f0',48000,1,{'fundamental_hz':frequency(24),'span_seconds':[1,7.5],
          'harmonics':[[2,.10],[3,.065],[4,.035],[5,.020],[7,.012]],
          'fan_line_hz':frequency(24),'fan_line_gain':.035,'noise_rms':.004,
          'fit_span_seconds':[2,6]}),
        ('varying-fan-shared-gain',44100,2,{'fundamental_hz':frequency(24),'guitar_gain':.12,
          'fan_line_hz':frequency(39),'fan_line_gain':.025,'noise_rms':.006,
          'breakpoints_seconds':[0,2,4,6,8],'fan_levels':[1,1.75,.45,1.25,1],
          'shared_gain':[.7,1.2,.6,1,.8]}),
    ]
    rows = [{'alias':f'lr{i+1:02d}','kind':kind,'sample_rate':rate,'channels':ch,
             'duration_seconds':8,'sample_frames':8*rate,'seed':2026100600+i,
             'parameters':p,'capture_samples':[0,round(.8*rate)]}
            for i,(kind,rate,ch,p) in enumerate(cases)]
    design = {'suite':SCHEMA,'cases':rows,'total_source_seconds':64,
      'construction':{'sample_origin':0,'time':'n/native_rate','attack_seconds':.005,
        'release_seconds':.10,'harmonic_phase_radians':0,'fan_phase_default':.3,
        'colored_noise':'PCG64 Gaussian -> one-pole a=.92; normalize base RMS',
        'storage':'float32 little-endian WAV; round components then sum in float64 and round mixture',
        'stereo':'same guitar per channel; fan differs by declared phase/noise stream',
        'saturation':'tanh applied to guitar only before additive mixing',
        'known_noise_only_capture':'clean is exactly zero during first .8 seconds; clean-only case is silent'},
      'oracle_tolerances':{'float32_additivity_abs':FLOAT32_ADD_TOL,
        'missing_f0_joint_fit_amplitude':MISSING_F0_TOL,'same_mask_float64_additivity_abs':MASK_ADD_TOL},
      'future_preservation_gates':{'fundamental_loss_db':.5,'attack_first_ms':20,
        'attack_energy_loss_db':1,'attack_energy_boost_db':.5,'attack_centroid_shift_ms':2,
        'tail_interval_ms':[50,250],'tail_energy_loss_db':1,'tail_energy_boost_db':.5,
        'status':'predeclared_future_measurements_not_executed',
        'collision_applicability':'no contradictory perfect separation and preservation requirement'},
      'bounds':{'cases':8,'case_seconds':8,'total_source_seconds':64,'math_threads':2,
        'generation_deadline_seconds':120,'max_metadata_bytes':MAX_JSON,'max_audio_bytes':80_000_000}}
    return {'schema_version':1,'kind':'frozen_source_known_fixture_declaration','design':design,
       'design_sha256':hashlib.sha256(canonical(design)).hexdigest(),
       'generator_sha256':digest(Path(__file__)),
       'instrument_sha256':digest(ROOT/'program'/'instrument.json'),
       'actual_recording_or_profile_used':False,'truth_scope':'generated_components_only',
       'truth_supplied_to_discovery':False,'attenuation_executed':False,'listening_acceptance':False}


def local_path(value):
    path = Path(value).expanduser().absolute()
    if '..' in path.parts or not path.is_relative_to(ARTIFACTS) or path == ARTIFACTS:
        raise ValueError('Output/plan must be beneath artifacts/benchmarks')
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('Symlink components are rejected')
    return path


def write_new(path,value):
    raw = canonical(value)+b'\n'
    if len(raw)>MAX_JSON:
        raise ValueError('Metadata limit exceeded')
    with Path(path).open('xb') as f:
        f.write(raw)


def read_plan(path):
    path = local_path(path)
    if not path.is_file() or path.stat().st_size>MAX_JSON:
        raise ValueError('Plan must be a bounded regular file')
    def pairs(rows):
        result={}
        for key,value in rows:
            if key in result: raise ValueError('Duplicate plan key')
            result[key]=value
        return result
    with path.open('rb') as stream:
        raw=stream.read(MAX_JSON+1)
    if len(raw)>MAX_JSON:raise ValueError('Plan metadata limit exceeded')
    value=json.loads(raw,object_pairs_hook=pairs,
      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite plan')))
    if canonical(value)!=canonical(declaration()):
        raise ValueError('Frozen declaration, generator or instrument changed')
    return value,hashlib.sha256(raw).hexdigest()


def numeric():
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        os.environ[name]='2'
    import numpy as np
    from scipy.io import wavfile
    from scipy.signal import lfilter
    return np,wavfile,lfilter


def components(case):
    np,_,lfilter=numeric()
    rate=case['sample_rate'];ch=case['channels'];n=case['sample_frames']
    p=case['parameters'];t=np.arange(n,dtype=np.float64)/rate
    s=np.zeros(n);events=[]
    def envelope(start,end,decay=None):
        age=t-start
        e=np.maximum(0,np.minimum(np.minimum(age/.005,(end-t)/.10),1))
        if decay is not None:e*=np.exp(-np.maximum(age,0)/decay)
        return e
    def tone(f,start,end,gain,harmonics=((1,1),(2,.25),(3,.15)),decay=None):
        return gain*envelope(start,end,decay)*sum(a*np.sin(2*np.pi*k*f*t) for k,a in harmonics)
    def event(start,end,f,kind):
        events.append({'start_sample':round(start*rate),'end_sample':round(end*rate),
                      'frequency_hz':f,'kind':kind})
    kind=case['kind']
    if kind=='clean-sentinels':
        for f,(start,end) in zip((p['sentinel_hz'],p['fundamental_hz']),p['spans']):
            s+=tone(f,start,end,p['gain'],p['harmonics']);event(start,end,f,'sustain')
    elif kind in ('exact-collision','separated-line','varying-fan-shared-gain'):
        s=tone(p['fundamental_hz'],1,7.5,p['guitar_gain'])
        event(1,7.5,p['fundamental_hz'],'sustain')
    elif kind=='walking-saturated':
        for midi,start in zip(p['midi'],p['starts_seconds']):
            f=frequency(midi);s+=tone(f,start,start+p['note_seconds'],1)
            event(start,start+p['note_seconds'],f,'picked_sustain')
        s=p['guitar_gain']*np.tanh(p['drive']*s)
    elif kind=='palm-legato-saturated':
        for midi,start in zip(p['midi'],p['starts_seconds']):
            f=frequency(midi);s+=tone(f,start,start+p['note_seconds'],1,decay=p['decay_seconds'])
            event(start,start+p['note_seconds'],f,'palm_mute')
        a,b=p['legato_span_seconds'];edges=np.linspace(a,b,len(p['legato_midi']))
        frequencies=np.exp(np.interp(t,edges,np.log([frequency(m) for m in p['legato_midi']])))
        phase=2*np.pi*np.r_[0,np.cumsum(frequencies[:-1])]/rate
        s+=p['quiet_legato_gain']*envelope(a,b)*(np.sin(phase)+.25*np.sin(2*phase))
        event(a,b,None,'connected_legato_no_internal_pick_attacks')
        s=p['guitar_gain']*np.tanh(p['drive']*s)
    elif kind=='missing-f0':
        a,b=p['span_seconds'];s=tone(p['fundamental_hz'],a,b,1,p['harmonics'])
        event(a,b,p['fundamental_hz'],'linear_harmonic_proxy_missing_fundamental')
    elif kind!='fan-only':
        raise ValueError('Unregistered case')
    clean=np.repeat(s[:,None],ch,axis=1);fan=np.zeros_like(clean)
    rng=np.random.Generator(np.random.PCG64(case['seed']))
    for channel in range(ch):
        if kind=='clean-sentinels':continue
        phases=p.get('fan_phases_radians',[.3]*ch)
        fan[:,channel]=p['fan_line_gain']*np.sin(2*np.pi*p['fan_line_hz']*t+phases[channel])
        if p['noise_rms']:
            noise=lfilter([1],[1,-.92],rng.standard_normal(n))
            fan[:,channel]+=noise*(p['noise_rms']/np.sqrt(np.mean(noise*noise)))
    extras={}
    if kind=='varying-fan-shared-gain':
        fan*=np.interp(t,p['breakpoints_seconds'],p['fan_levels'])[:,None]
        extras={'base_clean':clean.copy(),'base_fan':fan.copy()}
        gain=np.interp(t,p['breakpoints_seconds'],p['shared_gain'])[:,None]
        extras['shared_gain']=np.repeat(gain,ch,axis=1)
        clean*=gain;fan*=gain
    clean=clean.astype('<f4');fan=fan.astype('<f4')
    mixture=(clean.astype(np.float64)+fan.astype(np.float64)).astype('<f4')
    arrays={'clean':clean,'fan':fan,'mixture':mixture,
            **{key:value.astype('<f4') for key,value in extras.items()}}
    truth={'schema_version':1,'case':case,'events':events,
      'source_origin_sample':0,'capture_clean_verified_zero':bool(np.all(clean[:round(.8*rate)]==0)),
      'non_identifiable':kind=='exact-collision',
      'fundamental_gain_applicable':kind not in ('fan-only','exact-collision','missing-f0'),
      'no_intended_score_or_real_notes':True,'truth_for_evaluation_only':True}
    return arrays,truth


def verify_oracles(arrays,case):
    np,_,_=numeric()
    n,ch=case['sample_frames'],case['channels']
    for key,x in arrays.items():
        if x.shape!=(n,ch) or not np.isfinite(x).all():raise ValueError('Invalid native extent/finite values')
        if key!='shared_gain' and np.max(np.abs(x))>=1:raise ValueError('Fixture clipping')
    clean=arrays['clean'].astype(np.float64);fan=arrays['fan'].astype(np.float64)
    mixture=arrays['mixture'].astype(np.float64)
    error=float(np.max(np.abs(clean+fan-mixture)))
    if error>FLOAT32_ADD_TOL:raise ValueError('Component additivity failed')
    result={'float32_additivity_max_abs':error,'capture_clean_zero':bool(np.all(clean[:round(.8*case['sample_rate'])]==0))}
    if not result['capture_clean_zero']:raise ValueError('Noise capture contains generated clean content')
    if case['kind']=='clean-sentinels' and np.any(fan):raise ValueError('Clean-only control has noise')
    if case['kind']=='fan-only' and np.any(clean):raise ValueError('Fan-only control has fabricated guitar')
    if case['kind']=='missing-f0':
        p=case['parameters'];rate=case['sample_rate'];a,b=[round(v*rate) for v in p['fit_span_seconds']]
        t=np.arange(a,b)/rate;harmonics=[1]+[h[0] for h in p['harmonics']]
        basis=np.column_stack([fun(2*np.pi*h*p['fundamental_hz']*t) for h in harmonics for fun in (np.sin,np.cos)])
        fit=np.linalg.lstsq(basis,clean[a:b,0],rcond=None)[0]
        f0=float(np.hypot(fit[0],fit[1]));result['missing_f0_joint_fit_amplitude']=f0
        if f0>MISSING_F0_TOL:raise ValueError('Missing F0 control contains fabricated fundamental')
        result['joint_fit_harmonic_amplitudes']=[float(np.hypot(fit[i],fit[i+1])) for i in range(2,len(fit),2)]
    if case['kind']=='exact-collision':
        rate=case['sample_rate'];p=case['parameters'];t=np.arange(n)/rate
        u=p['alternative_transfer_gain']*np.sin(2*np.pi*p['fundamental_hz']*t)
        u[:round(rate)]=0;u[round(7.5*rate):]=0;u=np.repeat(u[:,None],ch,axis=1)
        alternative_error=float(np.max(np.abs((clean+u)+(fan-u)-(clean+fan))))
        if alternative_error>MASK_ADD_TOL:raise ValueError('Collision alternative accounting failed')
        result.update(alternative_decomposition_error=alternative_error,
          alternative_components_differ=True,separation_identifiable=False)
    if case['kind']=='varying-fan-shared-gain':
        gain=arrays['shared_gain'].astype(np.float64)
        errors=[float(np.max(np.abs(arrays['base_'+role].astype(np.float64)*gain-arrays[role]))) for role in ('clean','fan')]
        if max(errors)>FLOAT32_ADD_TOL:raise ValueError('Shared gain references differ')
        result['effective_component_gain_max_abs']=errors
    return result


def verify_same_mask(clean_coefficients,fan_coefficients,mixture_coefficients,mask):
    """Oracle arithmetic only: accepts a frozen externally estimated mask."""
    np,_,_=numeric()
    arrays=[np.asarray(v) for v in (clean_coefficients,fan_coefficients,mixture_coefficients,mask)]
    if len({v.shape for v in arrays})!=1 or not all(np.isfinite(v).all() for v in arrays):
        raise ValueError('Invalid coefficient or mask shapes/values')
    s,n,x,g=arrays
    error=float(np.max(np.abs(s*g+n*g-x*g)))
    if error>MASK_ADD_TOL:raise ValueError('Same-mask conditional component accounting failed')
    return error


def generate(plan_path,output):
    plan,plan_hash=read_plan(plan_path);dest=local_path(output)
    dest.mkdir(exist_ok=False)
    np,wavfile,_=numeric();deadline=time.monotonic()+120;cases=[];discovery=[]
    for case in plan['design']['cases']:
        if time.monotonic()>deadline:raise TimeoutError('Fixture generation deadline')
        arrays,truth=components(case);oracle=verify_oracles(arrays,case)
        folder=dest/case['alias'];folder.mkdir();refs={}
        for key,data in arrays.items():
            path=folder/(key+'.wav');wavfile.write(path,case['sample_rate'],data[:,0] if case['channels']==1 else data)
            rate,rendered=wavfile.read(path);rendered=rendered[:,None] if rendered.ndim==1 else rendered
            if rate!=case['sample_rate'] or not np.array_equal(data,rendered):raise ValueError('Rendered reference differs')
            refs[key]={'path':str(path.relative_to(dest)),'sha256':digest(path)}
        truth.update(components=refs,oracles=oracle);write_new(folder/'truth.json',truth)
        cases.append({'alias':case['alias'],'truth':str((folder/'truth.json').relative_to(dest)),
                      'truth_sha256':digest(folder/'truth.json'),'components':refs,'oracles':oracle})
        discovery.append({'alias':case['alias'],'mixture':refs['mixture'],
          'sample_rate':case['sample_rate'],'channels':case['channels'],'sample_frames':case['sample_frames'],
          'capture_samples':case['capture_samples']})
    if sum(p.stat().st_size for p in dest.rglob('*.wav'))>80_000_000:raise ValueError('Audio byte bound exceeded')
    if read_plan(plan_path)[1]!=plan_hash:raise ValueError('Plan changed during generation')
    write_new(dest/'discovery.json',{'schema_version':1,'cases':discovery,'truth_supplied':False})
    receipt={'schema_version':1,'suite':SCHEMA,'status':'generated_oracles_verified',
      'plan_sha256':plan_hash,'design_sha256':plan['design_sha256'],
      'generator_sha256':plan['generator_sha256'],'instrument_sha256':plan['instrument_sha256'],
      'numpy_version':np.__version__,'case_count':8,'source_seconds':64,'cases':cases,
      'discovery_sha256':digest(dest/'discovery.json'),'attenuation_executed':False,
      'no_real_recording_used':True,'listening_acceptance':False}
    write_new(dest/'fixtures.json',receipt)
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='operation',required=True)
    declare=sub.add_parser('declare');declare.add_argument('--output',required=True)
    render=sub.add_parser('generate');render.add_argument('--plan',required=True);render.add_argument('--output',required=True)
    args=parser.parse_args()
    if args.operation=='declare':
        path=local_path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
        write_new(path,declaration());result={'status':'declaration_only','path':str(path),'sha256':digest(path)}
    else:result=generate(args.plan,args.output)
    print(json.dumps(result,sort_keys=True,allow_nan=False))


if __name__=='__main__':main()
