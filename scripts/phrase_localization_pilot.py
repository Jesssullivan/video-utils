#!/usr/bin/env python3
"""Fresh, preregistered phrase-localization experiment; numerical phases require release."""
from __future__ import annotations

import argparse
from array import array
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import signal
import shutil
import struct
import subprocess
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
AREA = ROOT/'artifacts/experiments/phrase-localization'
SUITE = 'phrase-localization-fresh-617-719-v1'
COHORTS = ('low32-sustain', 'missing-f0-sustain', 'ordered-click-noise-only',
           'fan-envelope-only', 'palm-recurrence', 'legato-recurrence')
PINS = {
    'docs/spec/PHRASE_LOCALIZATION_LANE.md':'71ab8f5b6641c33ac0bdf4bae4f4ba521c7fb22938d6547e4bc18a8c2639332b',
    'scripts/phrase_localize.py':'a64ff3acc5f18931e9975e96d1c6e80a1d454272fbf9dd4925b8b835b8c509de',
    'scripts/pitch_evaluate.py':'a91ce8e9386cc7c63c5a5d53b8233f2c46a1f42fdd06ab1ae0eea3dc83405805',
    'scripts/phrase_evaluate.py':'3e503de277b2fd233fe802595a09a655c89669b0eb820f228e677c1b94b828a5',
    'scripts/rhythm.py':'264b723ca29e4731da0a12d5dce221e7826a38b67f848ce9f4ffcf8bfe4b35b9',
    'scripts/guitar_features.py':'2ed031e8000cbcda92b504db10c98de03f456c90573cbff815cbb940c9ac86fe',
    'scripts/benchmark_bank.py':'087a67c009bb48abeac78259fc2719c02886e81b956ef8a9c62a22e6ee3913d5',
    'docs/agent-notes/2026-10-06-phrase-order-null.py':'5582a5cf2b415b07a434b59f407da8c6e63fa9101001267dbba03f0cabe9f066',
    'docs/agent-notes/2026-10-05-phrase-guarded-arms.py':'78ca89de9cea327cc4ec1096a83522781a08bc161819699b69797ca273e2fb6c',
    'docs/agent-notes/2026-10-06-phrase-order-null-settings.json':'232f7503f58e9ebcb2b59b220b97755b7001683eccd80893634d8f6b777079a3',
    'program/instrument.json':'bd381207d6615814ebee694148357c00719739ec900aa69c96d71b20779707b0',
}
# Byte-identical frozen copies; PINS keys stay the recorded logical names (sealed receipts compare PINS).
FROZEN = {'scripts/rhythm.py':'scripts/frozen/rhythm_264b723c.py'}
MEDIA = {
    'ffmpeg': {'path':'/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffmpeg',
               'sha256':'3a315207e67de78e48c3bbb6b3346663f6a27c02e034d65ac72a12fee74c534a',
               'version_prefix':'ffmpeg version 8.1.2'},
    'ffprobe': {'path':'/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffprobe',
                'sha256':'5fb21f955aad27bc59615906801ce4b5b9f1466e99450b714b6d989f836c8850',
                'version_prefix':'ffprobe version 8.1.2'},
}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def unit(seed, knob):
    return int.from_bytes(hashlib.sha256(f'{SUITE}:{seed}:{knob}'.encode()).digest()[:8], 'big')/2**64


def draw(seed, knob, low, high):
    return low+(high-low)*unit(seed, knob)


def geometry(seconds):
    native = round(seconds*48000)
    return {'requested_seconds':seconds, 'native_sample':native, 'seconds':native/48000}


def metadata():
    """Pure metadata only. No signal construction or discovery is performed."""
    seeds = []
    for seed in (617,719):
        first = geometry(draw(seed,'motif:first',.853,1.107))
        second = geometry(draw(seed,'motif:second',4.173,4.481))
        length = geometry(draw(seed,'motif:length',1.673,1.897))
        period = draw(seed,'nuisance:pulse_period',.337,.393)
        phase = draw(seed,'nuisance:pulse_phase',.101,.167)
        ordered_start = draw(seed,'nuisance:ordered_start',.311,.437)
        ordered_second = draw(seed,'nuisance:ordered_second',4.617,4.831)
        clicks = [{'seconds':phase+k*period, 'hz':3500.,'amplitude':.033,'type':'regular_pulse'}
                  for k in range(24) if phase+k*period<8]
        offsets = [0.,.173,.367,.581,.809,1.013,1.227,1.451]
        pitches = [2200.,5100.,1600.,3700.,5100.,2200.,3700.,1600.]
        amplitudes = [.058,.083,.047,.071,.061,.089,.053,.076]
        for start in (ordered_start,ordered_second):
            clicks.extend({'seconds':start+offset,'hz':hz,'amplitude':amplitude,'type':'ordered_texture'}
                          for offset,hz,amplitude in zip(offsets,pitches,amplitudes))
        clicks.sort(key=lambda event:event['seconds'])
        seeds.append({'seed':seed,'motif':{'first_start':first,'second_start':second,'duration':length,
                         'internal_rest_fraction_spans':[[.305,.351],[.657,.703]],
                         'position_fractions':[0.,.083,.167,.253,.365,.443,.527,.611,.717,.803,.889,.961],
                         'midi':[24,29,34,29,24,39,46,34,24,51,39,29]},
                      'nuisance':{'noise_rng_seed':int.from_bytes(hashlib.sha256(f'{SUITE}:{seed}:noise'.encode()).digest()[:8],'big'),
                         'fan_phase':draw(seed,'nuisance:fan_phase',0,2*math.pi),
                         'noise_phase':draw(seed,'nuisance:noise_phase',0,2*math.pi),
                         'pulse_period_seconds':period,'pulse_phase_seconds':phase,
                         'ordered_starts_seconds':[ordered_start,ordered_second],'clicks':clicks}})
    return {'schema_version':1,'suite':SUITE,'seeds':[617,719],'cohorts':list(COHORTS),
        'case_count':12,'case_duration_seconds':8,'total_audio_seconds':96,
        'native_pcm':{'sample_rate':48000,'channels':1,'sample_width_bytes':2,'sample_count_per_case':384000},
        'analysis_pcm':{'sample_rate':16000,'sample_count_per_case':128000,'source_audio_start_seconds':0},
        'feature_clock':{'hop_samples':256,'fft_samples':4096,'centered':True,'expected_frames':501},
        'parameter_recipe':'SHA256 suite:seed:knob, first8bytes unsigned big-endian / 2^64; nearest native sample for motif geometry',
        'parameters':seeds,
        'signal':{'common_gain':1.,'sustain_span_seconds':[.5,7.5],'sustain_attack_seconds':.02,'sustain_release_seconds':.02,
            'low32_frequency_hz':32.,'low32_amplitude':.17,'c1_frequency_hz':440*2**((24-69)/12),
            'missing_f0_harmonics':[[2,.1],[3,.065],[4,.035],[5,.02],[7,.012]],
            'missing_f0_nonlinearity_after_synthesis':False,'missing_f0_fit_seconds':[2.,6.],
            'missing_f0_fit_amplitude_bound':5e-5,
            'fan_hz':[47.,71.],'fan_amplitudes':[.009,.006],'fan_envelope_hz':.61,'fan_envelope_depth':.45,
            'noise_amplitude':.006,'noise_envelope_hz':.43,'noise_envelope_depth':.4,
            'noise_color':'uniform white; fixed RNG reseeded once per component per seed',
            'click_support_seconds':.012,'click_decay_seconds':.0024,
            'guitar_gain':.16,'guitar_drive':2.2,'guitar_harmonic_coefficients':[1.,.5,.25],
            'palm_support_seconds':.055,'palm_decay_seconds':.018,'palm_attack_seconds':.0015,
            'legato_attack_seconds':.008,'legato_release_seconds':.008,'legato_glide_seconds':.024,
            'safety_peak_upper_bound':.5,'component_sum_pcm_error_bound':2/32768},
        'sharing':{'fan_noise':'byte-identical across all six cohorts within each seed',
            'click':'byte-identical across five cohorts; fan-envelope-only intentionally click-free',
            'source_gain':'fixed common gain1; no per-case normalization or guitar-dependent nuisance',
            'motif_nuisance_independent_knob_namespaces':True},
        'truth':{'scope':'generator_only_not_musician','negative_cohorts':list(COHORTS[:4]),
            'positive_cohorts':list(COHORTS[4:]),'reference_pairs_per_positive':1,
            'reference_definition':'full generated identical motif spans including internal rests; no acoustic-repetition claim for negative sustain',
            'string_identity_inferred':False,'physical_articulation_accepted':False},
        'discovery':{'arms':['Araw','Border','L1'],'Bcontrol_retained_as_context':True,
            'BPM':'same-source unseeded rhythm analysis; absent pulse => no cache and all arms empty',
            'truth_supplied':False,'proposal_cap':60,'Border_cap':10,'L1_raw_candidate_ids_endpoints_unchanged':True},
        'scoring':{'iou_thresholds':[.5,.75],'primary_pair_iou':'both span IoUs meet threshold; compatible with frozen prior evaluator',
            'iou_assignment':'maximum cardinality then maximum mean IoU; frozen prior optimal_matching',
            'boundary_tolerances_seconds':[.02,.05,.1],
            'boundary_matching':'maximum-cardinality one-to-one independently typed first_start/first_end/second_start/second_end endpoints',
            'full_same_reference_sets':True,'common_endpoints_per_iou_threshold':True,
            'raw_fallback_credited_L1':False,'abstention_in_full_reference_denominator':True,
            'aggregation':'sum TP FP FN and endpoint sums/counts; no averaging per-case rates'},
        'budgets':{'numerical_threads':2,'case_deadline_seconds':120,'overall_deadline_seconds':600,
            'generation_case_deadline_seconds':120,'generation_overall_deadline_seconds':600,
            'frames_per_case':512,'roi_tile_cells':65536,'localization_cells_per_case':2000000,
            'json_bytes':20000000,'audio_bytes_per_file':1000000,'cache_expansion_bytes':1000000},
        'pins':dict(PINS),'media_executables':MEDIA,'settings_retuned':False,
        'canonical_defaults_activated':False,'musical_performance_graded':False}


def load_module(path,name):
    specification=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(specification);specification.loader.exec_module(value);return value


def verify_pins():
    for name,expected in PINS.items():
        require(digest(ROOT/FROZEN.get(name,name))==expected,'pinned_dependency_changed:'+name)


def old_helper():
    verify_pins()
    return load_module(ROOT/'docs/agent-notes/2026-10-06-phrase-order-null.py','fresh_phrase_order')


def checked_plan(path,identity):
    helper=old_helper();value=helper.read(path,identity)
    require(value==metadata(),'preregistration_not_exact_fixed_metadata')
    return value


def write(path,value,new=False):
    raw=(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
    require(len(raw)<=20000000,'json_bound')
    path=Path(path)
    if new:
        with path.open('xb') as handle:handle.write(raw)
    else:
        pending=path.with_name(path.name+'.pending')
        with pending.open('wb') as handle:handle.write(raw)
        os.replace(pending,path)
    path.chmod(0o600)


def envelope(t,start,end,attack,release):
    return max(0.,min(1.,(t-start)/attack,(end-t)/release)) if start<=t<end else 0.


def construct_components(seed,cohort,rate=512):
    """Pure generated arrays; low-rate calls are algebra fixtures, never native evidence."""
    require(seed in (617,719) and cohort in COHORTS,'fixed_case_required')
    require(type(rate) is int and 256<=rate<=48000,'bounded_constructed_rate')
    plan=metadata();parameter=next(row for row in plan['parameters'] if row['seed']==seed)
    signal=plan['signal'];nuisance=parameter['nuisance'];count=8*rate
    clean=array('d',[0.])*count;fan=array('d');noise=array('d');click=array('d',[0.])*count
    rng=random.Random(nuisance['noise_rng_seed'])
    for i in range(count):
        t=i/rate
        level=1-signal['fan_envelope_depth']/2+signal['fan_envelope_depth']/2*math.sin(2*math.pi*.61*t+nuisance['fan_phase'])
        fan.append(level*sum(a*math.sin(2*math.pi*f*t+nuisance['fan_phase']) for f,a in zip(signal['fan_hz'],signal['fan_amplitudes'])))
        noise_level=1-signal['noise_envelope_depth']/2+signal['noise_envelope_depth']/2*math.sin(2*math.pi*.43*t+nuisance['noise_phase'])
        noise.append(signal['noise_amplitude']*noise_level*rng.uniform(-1,1))
    if cohort!='fan-envelope-only':
        for event in nuisance['clicks']:
            # Absolute deterministic nuisance clock; never related to guitar placement.
            first=math.ceil(event['seconds']*rate);last=min(count,math.ceil((event['seconds']+.012)*rate))
            for i in range(first,last):
                age=i/rate-event['seconds']
                click[i]+=event['amplitude']*math.exp(-age/.0024)*math.sin(2*math.pi*event['hz']*age)
    if cohort in ('low32-sustain','missing-f0-sustain'):
        for i in range(count):
            t=i/rate;level=envelope(t,.5,7.5,.02,.02)
            if cohort=='low32-sustain':clean[i]=level*.17*math.sin(2*math.pi*32*t)
            else:clean[i]=level*sum(a*math.sin(2*math.pi*k*signal['c1_frequency_hz']*t) for k,a in signal['missing_f0_harmonics'])
    motif=parameter['motif'];references=[]
    if cohort in COHORTS[4:]:
        seconds=motif['duration']['seconds'];length=round(seconds*rate);shape=array('d',[0.])*length
        positions=[round(f*motif['duration']['native_sample'])/48000 for f in motif['position_fractions']]
        frequencies=[440*2**((note-69)/12) for note in motif['midi']]
        rests=[[round(a*motif['duration']['native_sample'])/48000,round(b*motif['duration']['native_sample'])/48000]
               for a,b in motif['internal_rest_fraction_spans']]
        phase=0.;position=0
        for i in range(length):
            t=i/rate
            while position+1<len(positions) and t>=positions[position+1]:position+=1
            hz=frequencies[position];age=t-positions[position]
            if cohort=='palm-recurrence':
                level=envelope(age,0,.055,.0015,.004)*math.exp(-max(0,age)/.018)
                phase=2*math.pi*hz*age
            else:
                if position and age<.024:
                    hz=frequencies[position-1]*2**(math.log2(hz/frequencies[position-1])*max(0.,age)/.024)
                # One continuously integrated phase; rests mute amplitude, not phase.
                phase+=2*math.pi*hz/rate
                level=envelope(t,0,seconds,.008,.008)
            if any(a<=t<b for a,b in rests):level=0.
            harmonic=math.sin(phase)+.5*math.sin(2*phase)+.25*math.sin(3*phase)
            shape[i]=.16*level*math.tanh(2.2*harmonic)
        starts=[round(motif[k]['seconds']*rate) for k in ('first_start','second_start')]
        for first in starts:
            require(first+length<=count,'motif_extent')
            clean[first:first+length]=shape
        references=[{'id':f'seed{seed}-{cohort}-full-motif',
                     'first_span_seconds':[motif['first_start']['seconds'],motif['first_start']['seconds']+seconds],
                     'second_span_seconds':[motif['second_start']['seconds'],motif['second_start']['seconds']+seconds]}]
    mix=array('d',(a+b+c+d for a,b,c,d in zip(clean,fan,noise,click)))
    require(all(math.isfinite(v) and abs(v)<.5 for v in mix),'fixed_peak_bound_exceeded')
    truth={'schema_version':1,'suite':SUITE,'seed':seed,'cohort':cohort,'ground_truth_scope':'generator_only_not_musician',
           'duration_seconds':8.,'recurrence_pairs':references,'negative_riff_reference':not references,
           'no_acoustic_repetition_claim':True,'physical_articulation_accepted':False,
           'source_audio_start_seconds':0.,'native_rate':rate,'native_sample_count':count,
           'construction_scope':'native_generated_pcm' if rate==48000 else 'tiny_low_rate_algebra_fixture_only',
           'motif_parameters':motif,'nuisance_parameters':nuisance,'performance_issue_confirmed':False}
    if cohort=='missing-f0-sustain':
        truth['missing_fundamental']={'frequency_hz':signal['c1_frequency_hz'],'fundamental_coefficient':0.,
            'nonlinearity_after_synthesis':False,'steady_interval_seconds':[2.,6.],
            'harmonics':[{'index':k,'amplitude':a,'phase_radians':0.} for k,a in signal['missing_f0_harmonics']]}
    return {'clean':clean,'fan':fan,'noise':noise,'click':click,'mix':mix,'truth':truth}


def spans(pair,duration=8.):
    if 'first_span_seconds' in pair:values=[pair['first_span_seconds'],pair['second_span_seconds']]
    else:values=[[pair[k+'_start_seconds'],pair[k+'_end_seconds']] for k in ('first','second')]
    require(len(values)==2 and all(isinstance(a,(list,tuple)) and len(a)==2 for a in values),'pair_spans_required')
    require(all(type(v) in (int,float) and math.isfinite(v) for a in values for v in a),'finite_pair_required')
    require(0<=values[0][0]<values[0][1]<=values[1][0]<values[1][1]<=duration,'ordered_source_pair_required')
    return values


def maximum_matching(references,estimates,eligible):
    """Deterministic augmenting paths; cardinality first, no label-guided retuning."""
    adjacency=[[j for j,estimate in enumerate(estimates) if eligible(reference,estimate)] for reference in references]
    assigned={}
    def augment(i,seen):
        for j in adjacency[i]:
            if j in seen:continue
            seen.add(j)
            if j not in assigned or augment(assigned[j],seen):assigned[j]=i;return True
        return False
    for i in range(len(references)):augment(i,set())
    return sorted((i,j) for j,i in assigned.items())


def counts(reference_count,estimate_count,matches):
    tp=len(matches)
    return {'reference_pair_count':reference_count,'estimate_pair_count':estimate_count,
        'tp':tp,'fp':estimate_count-tp,'fn':reference_count-tp,
        'precision':tp/estimate_count if estimate_count else None,
        'recall':tp/reference_count if reference_count else None,
        'f1':2*tp/(reference_count+estimate_count) if reference_count+estimate_count else None}


def iou(a,b):
    return max(0.,min(a[1],b[1])-max(a[0],b[0]))/(max(a[1],b[1])-min(a[0],b[0]))


def pair_metrics(references,estimates,duration,kind,threshold):
    refs=[spans(pair,duration) for pair in references];preds=[spans(pair,duration) for pair in estimates]
    require(kind=='iou','pair_iou_kind_required')
    measured=old_helper().recurrence_metrics(references,estimates,duration,threshold)
    matched=[(row['reference_index'],row['estimate_index']) for row in measured['matches']]
    offsets={i:[preds[j][k][v]-refs[i][k][v] for k in (0,1) for v in (0,1)] for i,j in matched}
    return {**counts(len(refs),len(preds),matched),'kind':kind,'threshold':threshold,
        'matches':[{'reference_index':i,'estimate_index':j,'reference_id':references[i].get('id',str(i)),
                    'signed_endpoint_offsets_seconds':offsets[i]} for i,j in matched]}


def boundary_metrics(references,estimates,duration,threshold):
    refs=[spans(pair,duration) for pair in references];preds=[spans(pair,duration) for pair in estimates];matches=[]
    for k,prefix in enumerate(('first','second')):
        for v,edge in enumerate(('start','end')):
            a=[x[k][v] for x in refs];b=[x[k][v] for x in preds]
            matched=maximum_matching(a,b,lambda first,second:abs(first-second)<=threshold+1e-12)
            matches.extend({'reference_index':i,'estimate_index':j,'endpoint_key':prefix+'_'+edge,
                            'signed_offset_seconds':b[j]-a[i]} for i,j in matched)
    result=counts(4*len(refs),4*len(preds),matches)
    result['reference_endpoint_count']=result.pop('reference_pair_count')
    result['estimate_endpoint_count']=result.pop('estimate_pair_count')
    return {**result,'kind':'typed_boundary','threshold':threshold,'matches':matches}


def reject_claims(value):
    if isinstance(value,dict):
        for key,item in value.items():
            if key in ('performance_issue_confirmed','musical_error_confirmed','note_correctness_confirmed'):
                require(item is False,'unsupported_confirmed_claim')
            reject_claims(item)
    elif isinstance(value,list):
        for item in value:reject_claims(item)


def score_case(references,arms,duration=8.):
    require(set(arms)=={'Araw','Border','L1'},'fixed_score_arms_required');reject_claims(arms)
    require(len(references)<=1 and len(arms['Araw'])<=60 and len(arms['Border'])<=10 and len(arms['L1'])<=10,'score_caps')
    scores={arm:{'candidate_count':len(rows),'iou':[pair_metrics(references,rows,duration,'iou',threshold) for threshold in (.5,.75)],
                 'boundary':[boundary_metrics(references,rows,duration,threshold) for threshold in (.02,.05,.1)]}
            for arm,rows in arms.items()}
    common=[]
    for index,threshold in enumerate((.5,.75)):
        maps={arm:{row['reference_index']:row['signed_endpoint_offsets_seconds'] for row in scores[arm]['iou'][index]['matches']}
              for arm in ('Border','L1')}
        baseline,treatment=maps['Border'],maps['L1'];shared=sorted(baseline.keys()&treatment.keys())
        offsets={arm:[v for i in shared for v in maps[arm][i]] for arm in maps}
        common.append({'iou_threshold':threshold,'common_reference_ids':[references[i].get('id',str(i)) for i in shared],
            'lost_reference_ids':[references[i].get('id',str(i)) for i in sorted(baseline.keys()-treatment.keys())],
            'gained_reference_ids':[references[i].get('id',str(i)) for i in sorted(treatment.keys()-baseline.keys())],
            'reference_count':len(references),'common_pair_count':len(shared),'endpoint_count':4*len(shared),
            'signed_offsets_seconds':offsets,'mean_absolute_error_seconds':{
                arm:sum(abs(v) for v in values)/len(values) if values else None for arm,values in offsets.items()}})
    return {'reference_pair_count':len(references),'scores':scores,'common_reference_endpoints':common,
            'raw_fallback_credited_L1':False,'all_references_in_denominator':True}


def aggregate_cases(rows):
    scopes={'all':rows}
    scopes.update({f'seed{seed}':[r for r in rows if r['seed']==seed] for seed in (617,719)})
    scopes.update({cohort:[r for r in rows if r['cohort']==cohort] for cohort in COHORTS})
    output={}
    for scope,selected in scopes.items():
        value={}
        for arm in ('Araw','Border','L1'):
            value[arm]={}
            for kind,thresholds in (('iou',(.5,.75)),('boundary',(.02,.05,.1))):
                metrics=[]
                for index,threshold in enumerate(thresholds):
                    r=[row['scores'][arm][kind][index] for row in selected]
                    noun='pair' if kind=='iou' else 'endpoint'
                    reference_count=sum(x['reference_'+noun+'_count'] for x in r);estimate_count=sum(x['estimate_'+noun+'_count'] for x in r)
                    tp=sum(x['tp'] for x in r)
                    totals=counts(reference_count,estimate_count,[None]*tp)
                    if kind=='boundary':
                        totals['reference_endpoint_count']=totals.pop('reference_pair_count')
                        totals['estimate_endpoint_count']=totals.pop('estimate_pair_count')
                    metrics.append({**totals,'threshold':threshold})
                value[arm][kind]=metrics
            value[arm]['negative_false_candidates_by_cohort']={cohort:sum(r['scores'][arm]['candidate_count'] for r in selected
                    if r['cohort']==cohort and r['reference_pair_count']==0) for cohort in COHORTS[:4]}
        value['common_reference_endpoints']=[]
        for index,threshold in enumerate((.5,.75)):
            common=[r['common_reference_endpoints'][index] for r in selected]
            n=sum(r['endpoint_count'] for r in common)
            value['common_reference_endpoints'].append({'iou_threshold':threshold,'endpoint_count':n,
                'reference_pair_count':sum(r['reference_pair_count'] for r in selected),
                'lost_reference_ids':[x for r in common for x in r['lost_reference_ids']],
                'gained_reference_ids':[x for r in common for x in r['gained_reference_ids']],
                'mean_absolute_error_seconds':{arm:sum(abs(v) for r in common for v in r['signed_offsets_seconds'][arm])/n
                                                if n else None for arm in ('Border','L1')}})
        output[scope]=value
    return output


def artifact_path(value,existing=False):
    return old_helper().safe(Path(value),AREA,existing)


def authorized(plan_path,plan_sha,release_path,release_sha,phase):
    plan_path=old_helper().safe(plan_path,ROOT/'docs/agent-notes',True)
    plan=checked_plan(plan_path,plan_sha)
    release_path=old_helper().safe(release_path,ROOT/'docs/agent-notes',True)
    require(release_path.name.startswith('2026-10-06-root-phrase-localization-'),'root_release_filename_required')
    release=old_helper().read(release_path,release_sha)
    require(release.get('actor')=='root' and release.get('scope')==SUITE and phase in release.get('authorized_phases',[]),
            'exact_root_numerical_phase_not_authorized')
    require(release.get('plan_sha256')==plan_sha and release.get('worker_sha256')==digest(__file__),
            'release_source_or_plan_binding_changed')
    require(release.get('dependency_sha256')==PINS and release.get('budgets')==plan['budgets'],
            'release_dependencies_or_budgets_changed')
    audit=old_helper().safe(ROOT/release['source_audit_path'],ROOT/'docs/agent-notes',True)
    require(digest(audit)==release['source_audit_sha256'],'independent_audit_binding_changed')
    return plan,{'path':str(release_path.relative_to(ROOT)),'sha256':release_sha,
                 'plan_path':str(plan_path.relative_to(ROOT)),'plan_sha256':plan_sha,
                 'worker_sha256':digest(__file__),'source_audit_sha256':release['source_audit_sha256'],
                 'source_audit_path':str(audit.relative_to(ROOT)),
                 'bank_sha256':release.get('bank_sha256'),
                 'bank_generator_sha256':release.get('bank_generator_sha256',digest(__file__))}


def guard_deadline(started,phase,case_started=None):
    require(time.monotonic()-started<600,'overall_deadline:'+phase)
    if case_started is not None:require(time.monotonic()-case_started<120,'case_deadline:'+phase)


def live_owned_group(pgid):
    """Bounded readback excludes dead zombies; a reused/nonowned group is never targeted."""
    result=subprocess.run(['ps','-axo','pid=,pgid=,stat='],capture_output=True,text=True,timeout=2,check=True)
    require(len(result.stdout)<2000000,'owned_group_inspection_bound')
    rows=[]
    for line in result.stdout.splitlines():
        fields=line.split()
        if len(fields)==3 and fields[0].isdigit() and fields[1].isdigit() and int(fields[1])==pgid and not fields[2].startswith('Z'):
            rows.append({'pid':int(fields[0]),'pgid':pgid,'state':fields[2]})
    return rows


def cleanup_owned_group(process,receipts,reason):
    """Caller owns this just-created start_new_session Popen; inspect exact PGID before signal."""
    members=live_owned_group(process.pid)
    if not members:
        process.wait(timeout=2);return
    receipt={'actor':'guitar_features_fresh_localization','target_pgid':process.pid,'ownership':'just_created_Popen_start_new_session',
        'reason':reason,'ruling':'R-N11','prior_state':{'leader_poll':process.poll(),'live_group_members':members}}
    receipts.append(receipt)
    try:
        os.killpg(process.pid,signal.SIGTERM)
        until=time.monotonic()+1
        while live_owned_group(process.pid) and time.monotonic()<until:time.sleep(.02)
        if live_owned_group(process.pid):os.killpg(process.pid,signal.SIGKILL)
        process.wait(timeout=2)
        require(not live_owned_group(process.pid),'owned_live_descendants_remain')
        receipt['result']='owned_group_signalled_leader_reaped_no_live_members'
    except BaseException:
        receipt['result']='owned_group_cleanup_unverified';raise


def pcm16(values):
    require(all(math.isfinite(v) and abs(v)<.5 for v in values),'pcm_peak_or_finite_guard')
    encoded=array('h',(round(v*32768) for v in values))
    if sys.byteorder!='little':encoded.byteswap()
    return encoded.tobytes()


def write_wav(path,raw):
    require(not Path(path).exists() and len(raw)==768000,'native_pcm_payload_extent')
    with wave.open(str(path),'wb') as handle:
        handle.setparams((1,2,48000,384000,'NONE','not compressed'));handle.writeframes(raw)
    Path(path).chmod(0o600)


def decoded_ints(raw):
    result=array('h');result.frombytes(raw)
    if sys.byteorder!='little':result.byteswap()
    return result


def component_sum_proof(encoded):
    parts=[decoded_ints(encoded[name]) for name in ('clean','fan','noise','click')]
    mix=decoded_ints(encoded['mix'])
    error=max(abs(value-sum(row[i] for row in parts)) for i,value in enumerate(mix))
    require(error<=2,'rendered_component_sum_exceeds_two_lsb')
    return {'maximum_integer_sample_residual':error,'absolute_bound_lsb':2,
            'normalization_or_clip_performed':False,'components':['clean','fan','noise','click'],
            'method':'independently quantized PCM16 components vs independently quantized float sum'}


def verify_low32_render(raw,rate=48000):
    values=decoded_ints(raw);require(len(values)==8*rate,'low32_rendered_extent')
    a,b=2*rate,6*rate;count=b-a
    sine=2*math.fsum(values[i]/32768*math.sin(2*math.pi*32*i/rate) for i in range(a,b))/count
    cosine=2*math.fsum(values[i]/32768*math.cos(2*math.pi*32*i/rate) for i in range(a,b))/count
    amplitude=math.hypot(sine,cosine)
    require(abs(amplitude-.17)<5e-5,'rendered_low32_coefficient_mismatch')
    return {'status':'verified_rendered_pcm16_32hz_coefficient','frequency_hz':32.,'measured_amplitude':amplitude,
            'expected_amplitude':.17,'absolute_tolerance':5e-5,'steady_interval_seconds':[2.,6.],
            'method':'orthogonal sine/cosine projection over128 complete periods',
            'scope':'rendered_generated_clean_component_only'}


def generate(plan_path,plan_sha,release_path,release_sha,output):
    started=time.monotonic();plan,authorization=authorized(plan_path,plan_sha,release_path,release_sha,'generate')
    output=artifact_path(output);require(not output.exists(),'fresh_output_required')
    output.mkdir(parents=True,mode=0o700)
    receipt={'schema_version':1,'status':'generation_running','authorization':authorization,'cases':[],
             'audio_generated':True,'cache_generated':False,'model_inference_invoked':False,'musical_performance_graded':False}
    write(output/'generation.json',receipt)
    try:
        shared={};cases=[]
        verifier=load_module(ROOT/'scripts/benchmark_bank.py','fresh_render_verifier')
        for seed in plan['seeds']:
            for cohort in COHORTS:
                case_started=time.monotonic();guard_deadline(started,'before_case',case_started)
                components=construct_components(seed,cohort,48000)
                guard_deadline(started,'after_float_construction',case_started)
                encoded={name:pcm16(components[name]) for name in ('clean','fan','noise','click','mix')}
                proof=component_sum_proof(encoded);id=f'seed{seed}-{cohort}';directory=output/id;directory.mkdir(mode=0o700)
                artifacts={}
                for name,raw in encoded.items():
                    target=directory/(name+'.wav');write_wav(target,raw)
                    with wave.open(str(target),'rb') as handle:
                        require((handle.getframerate(),handle.getnchannels(),handle.getsampwidth(),handle.getnframes())==(48000,1,2,384000),'rendered_native_header')
                        require(handle.readframes(384000)==raw,'rendered_pcm_byte_mismatch')
                    artifacts[name]={'path':str(target.relative_to(output)),'sha256':digest(target),'bytes':target.stat().st_size,
                                     'pcm_sha256':hashlib.sha256(raw).hexdigest()}
                for name in ('fan','noise','click'):
                    if name=='click' and cohort=='fan-envelope-only':continue
                    key=(seed,name);actual=artifacts[name]['sha256']
                    require(key not in shared or shared[key]==actual,'shared_nuisance_component_not_byte_identical')
                    shared[key]=actual
                truth=components['truth'];truth['source']={**artifacts['mix'],'sample_rate':48000,'channels':1,
                    'sample_count':384000,'audio_start_seconds':0,'origin_evidence':'generated_sample_zero'}
                truth['artifacts']=artifacts;truth['rendered_component_sum_verification']=proof
                if cohort=='low32-sustain':truth['rendered_low32_verification']=verify_low32_render(encoded['clean'])
                if cohort=='missing-f0-sustain':
                    clean=[v/32768 for v in decoded_ints(encoded['clean'])]
                    truth['rendered_missing_fundamental_verification']=verifier.verify_missing_render(clean,48000,truth)
                write(directory/'truth.json',truth,new=True)
                case={'id':id,'seed':seed,'cohort':cohort,'source':truth['source'],
                      'truth':{'path':str((directory/'truth.json').relative_to(output)),'sha256':digest(directory/'truth.json')},
                      'artifacts':artifacts,'duration_seconds':8.}
                cases.append(case);receipt['cases'].append({'id':id,'elapsed_seconds':time.monotonic()-case_started,
                    'source_sha256':case['source']['sha256'],'truth_sha256':case['truth']['sha256']})
                guard_deadline(started,'case_sealing',case_started);write(output/'generation.json',receipt)
        verify_pins();require(digest(__file__)==authorization['worker_sha256'],'worker_changed_during_generation')
        checked_plan(ROOT/authorization['plan_path'],plan_sha)
        bank={'schema_version':1,'suite':SUITE,'case_count':12,'total_duration_seconds':96,'cases':cases,
              'plan_sha256':plan_sha,'worker_sha256':authorization['worker_sha256'],
              'ground_truth_scope':'generator_only_not_musician','instrument_registry_sha256':PINS['program/instrument.json'],
              'shared_component_sha256':{f'{seed}:{name}':sha for (seed,name),sha in shared.items()},
              'click_free_exception':'fan-envelope-only','authorization':authorization}
        write(output/'fixtures.json',bank,new=True);guard_deadline(started,'bank_seal')
        receipt.update(status='generated_native_bank_sealed_no_discovery',bank_sha256=digest(output/'fixtures.json'),elapsed_seconds=time.monotonic()-started)
        write(output/'generation.json',receipt);guard_deadline(started,'generation_receipt_seal')
        return output/'fixtures.json'
    except BaseException as exc:
        receipt.update(status='generation_failed_retained_partial',error=type(exc).__name__+': '+str(exc),elapsed_seconds=time.monotonic()-started)
        write(output/'generation.json',receipt);raise


def treatment_estimates(localization,proposal):
    """Only localized physical cells are scored; raw fallback is preserved separately."""
    reject_claims(localization);raw=proposal['arms']['Border']
    require(len(localization['candidates'])==len(raw),'L1_retained_count_changed')
    result=[]
    for original,row in zip(raw,localization['candidates']):
        require(row['candidate_id']==original['original_candidate_index'] and row['raw_candidate']==original,'L1_raw_identity_changed')
        if row['status']=='localized_support_candidate':
            support=row['localized_support']
            first=[support['first']['cell_start_audio_relative_seconds'],support['first']['cell_end_audio_relative_seconds']]
            second=[support['second']['cell_start_audio_relative_seconds'],support['second']['cell_end_audio_relative_seconds']]
            value={'original_candidate_index':original['original_candidate_index'],'first_span_seconds':first,
                   'second_span_seconds':second,'confidence':None,'performance_issue_confirmed':False}
            spans(value);result.append(value)
        else:require(row['localized_support'] is None,'abstention_has_support')
    return result


def child(task_path,task_sha):
    """Internal opaque discovery job: source and mechanical clocks only, no corpus labels."""
    helper=old_helper();task_path=artifact_path(task_path,True);task=helper.read(task_path,task_sha)
    require(set(task)=={'source','source_sha256','target','sources','controller_sha256','release_sha256','admission_sha256'},'opaque_task_fields')
    require(task['controller_sha256']==digest(__file__),'task_controller_changed')
    source=artifact_path(task['source'],True);target=artifact_path(task['target']);sources=artifact_path(task['sources'])
    require(task_path.parent==target and target.parent.name=='discovery' and sources.parent==target.parent.parent,'task_owned_layout')
    validate_child_admission(task,target)
    require(digest(source)==task['source_sha256'],'opaque_source_hash_mismatch')
    import numpy as np
    rhythm=load_module(sources/'rhythm.py','fresh_rhythm')
    frontend=load_module(sources/'guitar_features.cache_worker.py','fresh_cache_frontend')
    samples=rhythm.decode(source);require(len(samples)==128000,'analysis_pcm_extent')
    analysis=rhythm.analyze(samples,source_start=0.,bpm=None,backend='librosa')
    analysis['source']={'opaque_input':str(source),'sha256':task['source_sha256']};write(target/'analysis.json',analysis,new=True)
    pulse=pulse_settings(analysis)
    if pulse is None:
        proposal={'schema_version':1,'status':'unseeded_pulse_unavailable','source_sha256':task['source_sha256'],
                  'arms':{'Bcontrol':[],'Border':[]},'proposal_universe':[],'cache_sha256':None,
                  'duration_seconds':8.,'performance_issue_confirmed':False}
        localized={'schema_version':1,'status':'upstream_pulse_unavailable_no_cache','candidates':[],
                   'localized_count':0,'abstained_count':0,'cells_visited':0,'confidence':None}
    else:
        period,origin,pulse_provenance=pulse;bpm=60/period
        frontend.phrases_librosa(samples,bpm,origin);cache=frontend._ablation_cache
        np.savez_compressed(target/'features.npz',**cache);helper.frozen_arms().check_cache_archive(target/'features.npz')
        proposal=helper.build(cache,period,origin,8.)
        proposal.update(cache_sha256=digest(target/'features.npz'),source_sha256=task['source_sha256'],
                        pulse_input_provenance=pulse_provenance)
        clock={'schema_version':1,'source_sha256':task['source_sha256'],'cache_sha256':proposal['cache_sha256'],
            'audio_start_seconds':0.,'duration_seconds':8.,
            'native_pcm':{'sample_rate':48000,'channels':1,'sample_count':384000},
            'analysis_pcm':{'sample_rate':16000,'sample_count':128000},
            'feature_clock':{'hop_samples':256,'fft_samples':4096,'centered':True,
                'timestamp_convention':'frame_centers_audio_relative','frame_indices':list(range(len(cache['times'])))}}
        write(target/'clock.json',clock,new=True)
        localizer=load_module(ROOT/'scripts/phrase_localize.py','fresh_localizer')
        values={name:np.asarray(value).tolist() for name,value in cache.items()}
        localized=localizer.localize(values,proposal,clock)
        localized['provenance']={'worker_sha256':PINS['scripts/phrase_localize.py'],'parser_dependency_sha256':PINS['scripts/pitch_evaluate.py'],
            'cache_sha256':proposal['cache_sha256'],'clock_sha256':digest(target/'clock.json'),
            'source_time_basis':'generated_sample_zero_native48000_analysis16000'}
    proposal.update(source_audio_start_seconds=0.,analysis_sample_count=128000,analysis_shared=True,
                    generator_bpm_supplied=False,truth_supplied=False)
    write(target/'proposals.json',proposal,new=True);write(target/'localization.json',localized,new=True)
    estimates=treatment_estimates(localized,proposal)
    prediction={'schema_version':1,'source_sha256':task['source_sha256'],
        'arms':{'Araw':proposal['proposal_universe'],'Border':proposal['arms']['Border'],'L1':estimates},
        'Bcontrol_context':proposal['arms']['Bcontrol'],'status':localized['status'],
        'discovery_reference_labels_supplied':False,'performance_issue_confirmed':False,
        'raw_fallback_credited_L1':False,'localized_count':len(estimates),
        'abstained_count':len(proposal['arms']['Border'])-len(estimates),
        'failure_taxonomy':{
            'upstream_pulse_unavailable':pulse is None,'no_initial_proposals':not proposal['proposal_universe'],
            'initial_proposal_count':len(proposal['proposal_universe']),
            'contrast_excluded_count':sum(r['order_status']=='contrast_excluded' for r in proposal.get('audit',[])),
            'order_margin_excluded_count':sum(r['order_status']=='order_margin_excluded' for r in proposal.get('audit',[])),
            'Border_cap_excluded_count':sum(r['order_status']=='ranked_cap_excluded' for r in proposal.get('audit',[])),
            'localization_abstained_count':len(proposal['arms']['Border'])-len(estimates),
            'initial_cap_saturated_not_proof_of_extra_opportunity':len(proposal['proposal_universe'])==60},
        'candidate_failures':[{'candidate_id':r['candidate_id'],'reason':r['reason']} for r in localized['candidates'] if r['localized_support'] is None]}
    write(target/'prediction.json',prediction,new=True)
    require(digest(source)==task['source_sha256'],'source_changed_during_discovery');verify_pins()
    require(digest(__file__)==task['controller_sha256'],'controller_changed_during_discovery')
    return 0


def pulse_settings(analysis):
    """Consume the pinned rhythm.analyze schema; no generator tempo or score input."""
    require(isinstance(analysis,dict) and analysis.get('schema_version')==1
            and 'click_grid' in analysis and 'selected_periodicity' in analysis,'pinned_rhythm_return_schema_required')
    grid=analysis['click_grid'] or {};selected=analysis['selected_periodicity'] or {}
    bpm=grid.get('bpm') or selected.get('bpm')
    if bpm is None:return None
    require(type(bpm) in (int,float) and math.isfinite(bpm) and 20<=bpm<=600,'bounded_measured_bpm_required')
    period=60/bpm;phase=grid.get('phase_seconds_audio_relative')
    if phase is not None:require(type(phase) in (int,float) and math.isfinite(phase) and phase>=0,'bounded_measured_phase_required')
    origin=max(0.,phase or 0.)%period
    return period,origin,{'tempo_basis':'same_source_unseeded_rhythm_analysis',
        'tempo_field':'click_grid.bpm' if grid.get('bpm') else 'selected_periodicity.bpm',
        'phase_field':'click_grid.phase_seconds_audio_relative' if phase is not None else None,
        'phase_available':phase is not None,
        'origin_basis':'measured_grid_phase_modulo_period' if phase is not None else 'analysis_sample_zero_no_measured_grid_phase',
        'generator_bpm_supplied':False,'reference_labels_supplied':False}


def validate_child_admission(task,target):
    """Read root release and opaque mechanical admission, never bank/phrase/note labels."""
    helper=old_helper();run=target.parent.parent
    admission=helper.read(artifact_path(run/'run-admission.json',True),task['admission_sha256'])
    authorization=admission['authorization']
    require(authorization['sha256']==task['release_sha256'] and admission['controller_sha256']==task['controller_sha256'],
            'child_admission_controller_release_mismatch')
    release_path=helper.safe(ROOT/authorization['path'],ROOT/'docs/agent-notes',True)
    require(release_path.name.startswith('2026-10-06-root-phrase-localization-'),'root_release_filename_required')
    release=helper.read(release_path,authorization['sha256'])
    require(release.get('actor')=='root' and release.get('scope')==SUITE and 'run' in release.get('authorized_phases',[]),
            'child_run_phase_not_authorized')
    require(release.get('worker_sha256')==task['controller_sha256'] and release.get('bank_sha256')==admission['bank_sha256']
            and release.get('plan_sha256')==authorization['plan_sha256'] and release.get('dependency_sha256')==PINS
            and release.get('budgets')==metadata()['budgets'],'child_release_source_bank_plan_binding')
    plan_path=helper.safe(ROOT/authorization['plan_path'],ROOT/'docs/agent-notes',True)
    require(digest(plan_path)==authorization['plan_sha256'],'child_plan_hash_changed')
    audit=helper.safe(ROOT/release['source_audit_path'],ROOT/'docs/agent-notes',True)
    require(digest(audit)==release['source_audit_sha256']==authorization['source_audit_sha256'],'child_audit_binding_changed')
    require({'path':task['source'],'sha256':task['source_sha256']} in admission['opaque_sources'],'child_source_not_admitted')
    copied_rhythm=artifact_path(Path(task['sources'])/'rhythm.py',True)
    require(digest(copied_rhythm)==PINS['scripts/rhythm.py'],'copied_rhythm_changed')
    frontend=(ROOT/'scripts/guitar_features.py').read_text()
    needle='    observations = discover_phrase_features(pulse_features, period, duration, onset_times, start, pulse_centroids)'
    expected=frontend.replace(needle,'    global _ablation_cache\n    _ablation_cache = {"features":frame_features,"times":frame_times,"centroid":centroid,"onsets":onset_times}\n'+needle)
    cache_worker=artifact_path(Path(task['sources'])/'guitar_features.cache_worker.py',True)
    require(cache_worker.read_text()==expected,'copied_cache_hook_changed')
    for receipt in MEDIA.values():require(digest(receipt['path'])==receipt['sha256'],'child_media_binary_changed')


def validate_bank(path,sha,plan_sha,worker_sha,started,producer_sha=None):
    helper=old_helper();path=artifact_path(path,True);bank=helper.read(path,sha)
    require(bank.get('schema_version')==1 and bank.get('suite')==SUITE and bank.get('case_count')==12
            and bank.get('total_duration_seconds')==96 and bank.get('plan_sha256')==plan_sha
            and bank.get('worker_sha256')==(producer_sha or worker_sha)
            and bank.get('authorization',{}).get('worker_sha256')==(producer_sha or worker_sha)
            and bank.get('instrument_registry_sha256')==PINS['program/instrument.json'],
            'bank_preregistration_binding_changed')
    require([(row['seed'],row['cohort']) for row in bank['cases']]==[(s,c) for s in (617,719) for c in COHORTS],
            'bank_case_order_changed')
    sources=[];originals=[];shared={}
    for case in bank['cases']:
        guard_deadline(started,'bank_prevalidation');require(case['duration_seconds']==8.,'case_duration_changed')
        for name,receipt in case['artifacts'].items():
            require(name in ('clean','fan','noise','click','mix'),'unexpected_audio_component')
            asset=helper.safe(path.parent/receipt['path'],path.parent,True)
            require(asset.stat().st_size==receipt['bytes']<=1000000 and digest(asset)==receipt['sha256'],'component_hash_size_changed')
            with wave.open(str(asset),'rb') as handle:
                require((handle.getframerate(),handle.getnchannels(),handle.getsampwidth(),handle.getnframes())==(48000,1,2,384000),'native_header_mismatch')
            originals.append((asset,receipt['sha256']))
            if name in ('fan','noise','click') and not (name=='click' and case['cohort']=='fan-envelope-only'):
                key=f"{case['seed']}:{name}";require(key not in shared or shared[key]==receipt['sha256'],'shared_nuisance_changed')
                shared[key]=receipt['sha256']
        require(set(case['artifacts'])=={'clean','fan','noise','click','mix'},'component_set_changed')
        require(case['source']=={**case['artifacts']['mix'],'sample_rate':48000,'channels':1,'sample_count':384000,
                'audio_start_seconds':0,'origin_evidence':'generated_sample_zero'},'bank_source_identity_changed')
        sources.append(helper.safe(path.parent/case['source']['path'],path.parent,True))
        # Truth path structure is validated, but neither truth content nor truth bytes are read before sealing.
        helper.safe(path.parent/case['truth']['path'],path.parent,True)
    require(shared==bank['shared_component_sha256'],'shared_components_index_mismatch')
    return path,bank,sources,originals


def recheck_bindings(bank_path,bank_sha,authorization,output,artifacts,originals,started):
    guard_deadline(started,'integrity_recheck')
    require(digest(bank_path)==bank_sha,'bank_changed_after_predictions')
    verify_pins();require(digest(__file__)==authorization['worker_sha256'],'controller_changed_after_release')
    require(digest(ROOT/authorization['plan_path'])==authorization['plan_sha256'],'preregistration_changed')
    require(digest(ROOT/authorization['path'])==authorization['sha256'],'release_changed')
    require(digest(ROOT/authorization['source_audit_path'])==authorization['source_audit_sha256'],'source_audit_changed')
    for receipt in MEDIA.values():require(digest(receipt['path'])==receipt['sha256'],'media_binary_changed_after_inference')
    for path,sha in originals:
        guard_deadline(started,'original_recheck');require(digest(path)==sha,'original_component_changed')
    for name,sha in artifacts.items():
        guard_deadline(started,'prediction_recheck')
        path=artifact_path(output/name,True);require(digest(path)==sha,'prediction_or_source_snapshot_changed')


def score_sealed(bank,bank_path,output,rows,sealed_path,sealed_sha,on_truth_open=None,deadline_check=None):
    """The sole truth-opening path, reachable only after a complete prediction seal."""
    helper=old_helper();seal=helper.read(sealed_path,sealed_sha)
    require(seal['status']=='all_twelve_predictions_frozen_truth_unopened' and seal['case_count']==12
            and len(rows)==12 and len(bank['cases'])==12
            and [(case['seed'],case['cohort']) for case in bank['cases']]==[(s,c) for s in (617,719) for c in COHORTS]
            and seal['bank_sha256']==digest(bank_path)
            and seal['case_prediction_sha256']==[row['prediction_sha256'] for row in rows],
            'complete_prediction_seal_required')
    require(all(seal['artifact_sha256'].get(row['prediction_path'])==row['prediction_sha256'] for row in rows),
            'all_predictions_in_artifact_seal_required')
    for name,sha in seal['artifact_sha256'].items():
        if deadline_check:deadline_check('global_artifact_pretruth_validation')
        require(digest(artifact_path(output/name,True))==sha,'sealed_artifact_changed_before_truth')
    predictions=[]
    for case,row in zip(bank['cases'],rows):
        if deadline_check:deadline_check('global_predictions_pretruth_validation')
        prediction=helper.read(output/row['prediction_path'],row['prediction_sha256'])
        require(prediction['source_sha256']==case['source']['sha256'] and row['id']==case['id'],'case_source_binding_changed')
        reject_claims(prediction)
        predictions.append(prediction)
    evaluated=[]
    for case,row,prediction in zip(bank['cases'],rows,predictions):
        if deadline_check:deadline_check('before_truth_open')
        truth=helper.read(helper.safe(bank_path.parent/case['truth']['path'],bank_path.parent,True),case['truth']['sha256'],opened=on_truth_open)
        require(truth['suite']==SUITE and truth['seed']==case['seed'] and truth['cohort']==case['cohort']
                and truth['ground_truth_scope']=='generator_only_not_musician' and truth['source']==case['source'],
                'truth_provenance_mismatch')
        reject_claims(truth)
        expected=expected_reference(case['seed'],case['cohort'])
        require(truth['recurrence_pairs']==expected,'truth_not_fixed_preregistered_geometry')
        measured=score_case(expected,prediction['arms'])
        measured.update(id=case['id'],seed=case['seed'],cohort=case['cohort'],prediction_sha256=row['prediction_sha256'],
            truth_sha256=case['truth']['sha256'],source_sha256=case['source']['sha256'],
            localization_coverage={'status':prediction['status'],'retained_count':len(prediction['arms']['Border']),
                'localized_count':prediction['localized_count'],'abstained_count':prediction['abstained_count'],
                'failures':prediction['candidate_failures']})
        measured['discovery_failure_taxonomy']=prediction.get('failure_taxonomy',{'status':'not_supplied_in_inert_source_fixture'})
        measured['evaluation_only_roi_geometry']=roi_geometry(expected,prediction['arms']['Border'])
        evaluated.append(measured)
    aggregate=aggregate_cases(evaluated);criteria={}
    for seed in (617,719):
        arm=aggregate[f'seed{seed}'];baseline=arm['Border'];treatment=arm['L1']
        criteria[f'seed{seed}']={
            'negative_false_candidates_not_higher':sum(treatment['negative_false_candidates_by_cohort'].values())<=sum(baseline['negative_false_candidates_by_cohort'].values()),
            'all_reference_recall_not_lower':all(treatment['iou'][i]['recall'] is not None and baseline['iou'][i]['recall'] is not None
                and treatment['iou'][i]['recall']>=baseline['iou'][i]['recall'] for i in range(2)),
            'qualification':'relative_generated_experiment_only; absolute navigation and musician acceptance remain unknown'}
    return {'schema_version':1,'status':'completed_fresh_generated_phrase_localization_measurements',
        'cases':evaluated,'aggregate':aggregate,'relative_research_criteria':criteria,
        'all_predictions_frozen_before_truth_read':True,'prediction_seal_sha256':sealed_sha,
        'ground_truth_scope':'generator_only_not_musician','settings_retuned':False,
        'performance_issue_confirmed':False,'listening_accepted':False,'canonical_defaults_activated':False,
        'primary_causal_comparison':'same retained Border raw pairs vs L1 physical support; Araw is uncapped proposal context',
        'missing_proposals_not_recovered':True,'raw_fallback_credited_L1':False}


def expected_reference(seed,cohort):
    if cohort not in COHORTS[4:]:return []
    motif=next(row['motif'] for row in metadata()['parameters'] if row['seed']==seed)
    length=motif['duration']['seconds']
    return [{'id':f'seed{seed}-{cohort}-full-motif',
             'first_span_seconds':[motif['first_start']['seconds'],motif['first_start']['seconds']+length],
             'second_span_seconds':[motif['second_start']['seconds'],motif['second_start']['seconds']+length]}]


def roi_geometry(references,retained):
    """Evaluation-only geometric upper bounds on the fixed centered 16ms frame cells."""
    rows=[]
    for i,reference in enumerate(references):
        ref=spans(reference)
        for raw in retained:
            pair=spans(raw);ceilings=[];reachable=[]
            for target,estimate in zip(ref,pair):
                left=max(0.,estimate[0]-.256);right=min(8.,estimate[1]+.256)
                first=math.ceil(left/.016-1e-12);last=math.ceil(right/.016-1e-12)-1
                cell=[max(0.,first*.016-.008),min(8.,last*.016+.008)]
                overlap=max(0.,min(target[1],cell[1])-max(target[0],cell[0]))
                ceilings.append(overlap/(target[1]-target[0]))
                reachable.append(cell[0]<=target[0] and cell[1]>=target[1])
            rows.append({'reference_index':i,'candidate_id':raw['original_candidate_index'],
                'span_iou_upper_bounds':ceilings,'both_endpoints_geometrically_reachable':reachable,
                'primary_pair_iou_upper_bound':min(ceilings),
                'qualification':'fixed regular centered grid geometric bound only; no feature/path/internal-change feasibility or discovered repair'})
    return {'reference_pair_count':len(references),'retained_pair_count':len(retained),'rows':rows,
            'geometry_used_in_discovery':False,'no_retained_candidate_is_not_a_localization_recovery':True}


def runner(plan_path,plan_sha,release_path,release_sha,bank_path,bank_sha,output):
    started=time.monotonic();plan,authorization=authorized(plan_path,plan_sha,release_path,release_sha,'run')
    require(authorization['bank_sha256']==bank_sha,'exact_released_bank_hash_required')
    bank_path,bank,sources_to_read,originals=validate_bank(bank_path,bank_sha,plan_sha,authorization['worker_sha256'],started,
                                                       producer_sha=authorization.get('bank_generator_sha256'))
    output=artifact_path(output);require(not output.exists(),'fresh_output_required')
    output.mkdir(parents=True,mode=0o700)
    receipt={'schema_version':1,'status':'preparing_discovery_truth_unopened','authorization':authorization,
        'bank_sha256':bank_sha,'signal_receipts':[],'cases':[],'truth_opened':False,'total_audio_seconds':96,
        'numerical_threads':2,'reference_labels_supplied':False,'source_audio_start_seconds':0.,
        'no_dsp_or_gain_applied_to_aliases':True,'settings_retuned':False,'source_originals_immutable':True}
    write(output/'run.json',receipt)
    try:
        sources=output/'sources';sources.mkdir();(output/'inputs').mkdir();(output/'discovery').mkdir()
        for name in ('rhythm.py','guitar_features.py'):shutil.copyfile(ROOT/FROZEN.get('scripts/'+name,'scripts/'+name),sources/name)
        shutil.copyfile(__file__,sources/'runner.frozen.py')
        shutil.copyfile(plan_path,sources/'preregistration.frozen.json')
        text=(sources/'guitar_features.py').read_text()
        needle='    observations = discover_phrase_features(pulse_features, period, duration, onset_times, start, pulse_centroids)'
        require(text.count(needle)==1,'pinned_cache_hook_changed')
        text=text.replace(needle,'    global _ablation_cache\n    _ablation_cache = {"features":frame_features,"times":frame_times,"centroid":centroid,"onsets":onset_times}\n'+needle)
        (sources/'guitar_features.cache_worker.py').write_text(text)
        artifacts={str(path.relative_to(output)):digest(path) for path in sources.iterdir()}
        environment={k:os.environ[k] for k in ('PATH','HOME','TMPDIR','LANG','LC_ALL') if k in os.environ}
        environment.update({k:'2' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS')})
        environment.update(FFMPEG=MEDIA['ffmpeg']['path'],FFPROBE=MEDIA['ffprobe']['path'])
        helper=old_helper();receipt['media_preflight'],_=helper.executable_preflight(environment,started,receipt['signal_receipts'])
        receipt['environment']={k:environment[k] for k in ('FFMPEG','FFPROBE','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS')}
        admission={'schema_version':1,'authorization':authorization,'bank_sha256':bank_sha,
            'controller_sha256':authorization['worker_sha256'],
            'opaque_sources':[{'path':str(output/'inputs'/f'audio-{ordinal:02d}.wav'),'sha256':case['source']['sha256']}
                              for ordinal,case in enumerate(bank['cases'],1)]}
        write(output/'run-admission.json',admission,new=True)
        artifacts['run-admission.json']=digest(output/'run-admission.json')
        for ordinal,(case,source) in enumerate(zip(bank['cases'],sources_to_read),1):
            case_started=time.monotonic();guard_deadline(started,'before_child',case_started)
            alias=output/'inputs'/f'audio-{ordinal:02d}.wav';shutil.copyfile(source,alias)
            require(digest(alias)==case['source']['sha256'],'byte_identical_alias_mismatch')
            artifacts[str(alias.relative_to(output))]=digest(alias)
            target=output/'discovery'/f'job-{ordinal:02d}';target.mkdir(mode=0o700)
            task={'source':str(alias),'source_sha256':case['source']['sha256'],'target':str(target),
                  'sources':str(sources),'controller_sha256':authorization['worker_sha256'],'release_sha256':authorization['sha256'],
                  'admission_sha256':artifacts['run-admission.json']}
            write(target/'task.json',task,new=True)
            argv=[sys.executable,str(Path(__file__).absolute()),'--child-task',str(target/'task.json'),'--child-task-sha256',digest(target/'task.json')]
            row={'id':case['id'],'ordinal':ordinal,'source_sha256':case['source']['sha256'],'argv':argv,'status':'running'}
            receipt['cases'].append(row);write(output/'run.json',receipt)
            with (target/'worker.stdout').open('wb') as stdout,(target/'worker.stderr').open('wb') as stderr:
                process=subprocess.Popen(argv,env=environment,stdout=stdout,stderr=stderr,start_new_session=True)
                row.update(pid=process.pid,owned_pgid=process.pid,start_new_session=True);write(output/'run.json',receipt)
                code=-1
                try:
                    remaining=min(112.,600-(time.monotonic()-started)-8)
                    require(remaining>0,'deadline_cleanup_reserve_exhausted')
                    code=process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:row['failure_reason']='worker_deadline'
                finally:
                    cleanup_owned_group(process,receipt['signal_receipts'],'fresh_owned_child_or_exited_leader_descendants')
            guard_deadline(started,'after_owned_cleanup',case_started)
            row.update(exit_code=code,elapsed_seconds=time.monotonic()-case_started)
            if code!=0:
                receipt.update(status='partial_worker_failed_truth_unopened',elapsed_seconds=time.monotonic()-started)
                row['status']='failed';write(output/'run.json',receipt);return 1
            for path in target.iterdir():
                require(path.is_file() and not path.is_symlink() and path.stat().st_size<=20000000,'worker_artifact_bound')
                artifacts[str(path.relative_to(output))]=digest(path)
            prediction=helper.read(target/'prediction.json',digest(target/'prediction.json'));reject_claims(prediction)
            require(set(prediction['arms'])=={'Araw','Border','L1'} and prediction['source_sha256']==case['source']['sha256']
                    and prediction['discovery_reference_labels_supplied'] is False,'invalid_opaque_prediction')
            spans_list=[spans(value) for values in prediction['arms'].values() for value in values]
            require(len(spans_list)<=80,'candidate_artifact_cap')
            row.update(status='prediction_saved_truth_unopened',prediction_path=str((target/'prediction.json').relative_to(output)),
                       prediction_sha256=digest(target/'prediction.json'))
            write(output/'run.json',receipt);guard_deadline(started,'prediction_case_seal',case_started)
        recheck_bindings(bank_path,bank_sha,authorization,output,artifacts,originals,started)
        seal={'schema_version':1,'status':'all_twelve_predictions_frozen_truth_unopened','case_count':12,
              'bank_sha256':bank_sha,'plan_sha256':plan_sha,'worker_sha256':authorization['worker_sha256'],
              'case_prediction_sha256':[row['prediction_sha256'] for row in receipt['cases']],
              'artifact_sha256':artifacts,'total_audio_seconds':96,'elapsed_seconds':time.monotonic()-started,'truth_opened':False}
        write(output/'predictions-frozen.json',seal,new=True)
        guard_deadline(started,'prediction_freeze_seal');receipt['prediction_seal_sha256']=digest(output/'predictions-frozen.json')
        receipt['status']='all_predictions_frozen_truth_unopened';write(output/'run.json',receipt)
        def on_truth_open():
            guard_deadline(started,'actual_truth_open')
            if not receipt['truth_opened']:
                receipt.update(truth_opened=True,status='evaluation_running_truth_opened');write(output/'run.json',receipt)
        measured=score_sealed(bank,bank_path,output,receipt['cases'],output/'predictions-frozen.json',receipt['prediction_seal_sha256'],
                              on_truth_open=on_truth_open,deadline_check=lambda phase:guard_deadline(started,phase))
        recheck_bindings(bank_path,bank_sha,authorization,output,artifacts,originals,started)
        require(digest(output/'predictions-frozen.json')==receipt['prediction_seal_sha256'],'prediction_seal_changed')
        write(output/'evaluation.json',measured,new=True);guard_deadline(started,'evaluation_seal')
        receipt.update(status=measured['status'],evaluation_sha256=digest(output/'evaluation.json'),elapsed_seconds=time.monotonic()-started,
                       artifact_sha256=artifacts)
        write(output/'run.json',receipt);guard_deadline(started,'final_receipt_seal')
        print(json.dumps({'evaluation':str(output/'evaluation.json'),'sha256':receipt['evaluation_sha256'],'aggregate':measured['aggregate']}));return 0
    except BaseException as exc:
        receipt.update(status='failed_retained_partial_truth_opened' if receipt['truth_opened'] else 'failed_retained_partial_truth_unopened',
                       error=type(exc).__name__+': '+str(exc),elapsed_seconds=time.monotonic()-started)
        write(output/'run.json',receipt);raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generate',action='store_true');parser.add_argument('--run',action='store_true')
    parser.add_argument('--plan',type=Path);parser.add_argument('--plan-sha256')
    parser.add_argument('--release',type=Path);parser.add_argument('--release-sha256')
    parser.add_argument('--bank-index',type=Path);parser.add_argument('--bank-sha256');parser.add_argument('--output',type=Path)
    parser.add_argument('--child-task',type=Path);parser.add_argument('--child-task-sha256')
    args=parser.parse_args()
    try:
        if args.child_task:
            require(not args.generate and not args.run and args.child_task_sha256,'internal_child_arguments')
            return child(args.child_task,args.child_task_sha256)
        require(args.generate!=args.run,'choose_exactly_one_generate_or_run_phase')
        require(all((args.plan,args.plan_sha256,args.release,args.release_sha256,args.output)),'exact_plan_release_output_required')
        if args.generate:
            require(not args.bank_index and not args.bank_sha256,'generation_does_not_receive_bank')
            bank=generate(args.plan,args.plan_sha256,args.release,args.release_sha256,args.output)
            print(json.dumps({'status':'generated_native_bank_sealed_no_discovery','fixtures':str(bank),'sha256':digest(bank)}));return 0
        require(args.bank_index and args.bank_sha256,'run_requires_hash_bound_bank')
        return runner(args.plan,args.plan_sha256,args.release,args.release_sha256,args.bank_index,args.bank_sha256,args.output)
    except (ValueError,OSError,KeyError,TypeError,AttributeError) as exc:
        print(json.dumps({'status':'failed_structural_or_operational','error':str(exc),'musical_performance_graded':False}))
        print(str(exc),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
