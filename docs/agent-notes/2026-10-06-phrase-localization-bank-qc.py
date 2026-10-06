#!/usr/bin/env python3
"""Read-only, exact-selector native bank construction QC. No discovery/regen."""
from array import array
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import time
import wave

ROOT=Path(__file__).resolve().parents[2]
BANK=ROOT/'artifacts/experiments/phrase-localization/fresh-bank-617-719-20261006T0332'
INDEX_SHA='9b62a3498f8ed5c508cca68c904f4d868c3861280c2f707f1972f098d4f39e67'
GENERATION_SHA='98b373e301b91e5d3ed29c34a03b9282b5749375e57904293067b041fc2c8230'
WORKER_SHA='8eae0110995619d128a022e8f0882a522b6213c5899cfd41216128b9847abd6c'
PLAN_PATH=ROOT/'docs/agent-notes/2026-10-06-phrase-localization-fresh-preregistration.json'
PLAN_SHA='8b0e7969f702d0685e2d7176c4ee96c19b1325b2e9b3d848685e093405c4c000'
COHORTS=('low32-sustain','missing-f0-sustain','ordered-click-noise-only','fan-envelope-only','palm-recurrence','legato-recurrence')
STARTED=time.monotonic()
FILES={}


def require(value,reason):
    if not value:raise ValueError(reason)


def read_exact(path,expected,limit):
    path=Path(path)
    require(path.is_relative_to(ROOT) and '..' not in path.parts,'root_local_path')
    require(not any(p.is_symlink() for p in (path,*path.parents)),'symlink_rejected')
    before=path.stat();require(path.is_file() and before.st_size<=limit,'file_extent_bound')
    raw=path.read_bytes();after=path.stat()
    require((before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns),'changed_during_read')
    actual=hashlib.sha256(raw).hexdigest();require(actual==expected,'sha256_mismatch:'+str(path.relative_to(ROOT)))
    FILES[str(path.relative_to(ROOT))]=actual
    return raw


def joint_fit(values,frequencies):
    """Independent pivoted least squares, DC plus sine/cosine; stride24 at48k.

    Measurement interval is frozen2..6s. Effective sample rate2000Hz safely
    exceeds twice the highest generated harmonic (~229Hz). No FFT/frontend.
    """
    samples=range(96000,288000,24)
    basis=[[1.]+[fun(2*math.pi*hz*i/48000) for hz in frequencies for fun in (math.sin,math.cos)] for i in samples]
    width=len(basis[0])
    matrix=[[math.fsum(row[a]*row[b] for row in basis) for b in range(width)]+
            [math.fsum(row[a]*values[i]/32768 for row,i in zip(basis,samples))] for a in range(width)]
    for pivot in range(width):
        best=max(range(pivot,width),key=lambda r:abs(matrix[r][pivot]))
        matrix[pivot],matrix[best]=matrix[best],matrix[pivot]
        scale=matrix[pivot][pivot];require(abs(scale)>1e-12,'singular_measurement_basis')
        matrix[pivot]=[x/scale for x in matrix[pivot]]
        for row in range(width):
            if row==pivot:continue
            factor=matrix[row][pivot]
            matrix[row]=[x-factor*y for x,y in zip(matrix[row],matrix[pivot])]
    return [row[-1] for row in matrix]


def check():
    source_before=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    plan=json.loads(read_exact(PLAN_PATH,PLAN_SHA,20_000_000))
    index=json.loads(read_exact(BANK/'fixtures.json',INDEX_SHA,20_000_000))
    generation=json.loads(read_exact(BANK/'generation.json',GENERATION_SHA,20_000_000))
    require(generation['status']=='generated_native_bank_sealed_no_discovery','generation_terminal_status')
    require(generation['bank_sha256']==INDEX_SHA,'generation_bank_identity')
    require(index['case_count']==12 and index['total_duration_seconds']==96,'bank_case_extent')
    require([(c['seed'],c['cohort']) for c in index['cases']]==[(s,c) for s in (617,719) for c in COHORTS],'fixed_bank_order')
    require(index['worker_sha256']==WORKER_SHA and index['plan_sha256']==PLAN_SHA,'source_plan_identity')
    for name,sha in plan['pins'].items():read_exact(ROOT/name,sha,20_000_000)
    read_exact(ROOT/'scripts/phrase_localization_pilot.py',WORKER_SHA,20_000_000)
    authority=index['authorization']
    release=json.loads(read_exact(ROOT/authority['path'],authority['sha256'],20_000_000))
    require(release['actor']=='root' and release['authorized_phases']==['generate'],'generation_phase_only')
    require(release['worker_sha256']==WORKER_SHA and release['plan_sha256']==PLAN_SHA,'root_source_plan_binding')
    require(release['dependency_sha256']==plan['pins'] and release['budgets']==plan['budgets'],'root_dependency_budget_binding')
    read_exact(ROOT/authority['source_audit_path'],authority['source_audit_sha256'],20_000_000)
    results=[];shared={};wav_count=0;positive=negative=0
    for case in index['cases']:
        require(time.monotonic()-STARTED<180,'construction_qc_deadline')
        assets=case['artifacts'];require(set(assets)=={'clean','fan','noise','click','mix'},'five_components')
        truth=json.loads(read_exact(BANK/case['truth']['path'],case['truth']['sha256'],20_000_000))
        require(truth['ground_truth_scope']=='generator_only_not_musician' and truth['native_rate']==48000
                and truth['native_sample_count']==384000 and truth['source_audio_start_seconds']==0,'native_truth_extent')
        require(truth['seed']==case['seed'] and truth['cohort']==case['cohort'] and truth['source']==case['source'],'truth_source_binding')
        require(truth['artifacts']==assets,'truth_component_binding')
        parts={};peaks={}
        for name,receipt in assets.items():
            path=BANK/receipt['path'];raw=read_exact(path,receipt['sha256'],1_000_000)
            require(len(raw)==receipt['bytes']==768044,'native_wave_file_extent')
            with wave.open(io.BytesIO(raw),'rb') as handle:
                require((handle.getframerate(),handle.getnchannels(),handle.getsampwidth(),handle.getnframes(),handle.getcomptype())
                        ==(48000,1,2,384000,'NONE'),'native_wave_header')
                pcm=handle.readframes(384000)
                require(not handle.readframes(1),'native_wave_extra_frames')
            require(len(pcm)==768000 and hashlib.sha256(pcm).hexdigest()==receipt['pcm_sha256'],'native_pcm_sha_extent')
            data=array('h');data.frombytes(pcm)
            if sys.byteorder!='little':data.byteswap()
            require(len(data)==384000,'unpacked_sample_extent');parts[name]=data
            peaks[name]=max(abs(v) for v in data)/32768
            require(peaks[name]<.5,'pcm_peak_bound')
            wav_count+=1
            if name in ('fan','noise','click'):
                if name=='click' and case['cohort']=='fan-envelope-only':require(not any(data),'fan_case_click_free')
                else:
                    key=f"{case['seed']}:{name}";require(key not in shared or shared[key]==receipt['sha256'],'shared_component_bytes')
                    shared[key]=receipt['sha256']
        require(case['source']=={**assets['mix'],'sample_rate':48000,'channels':1,'sample_count':384000,
                'audio_start_seconds':0,'origin_evidence':'generated_sample_zero'},'source_native_receipt')
        max_sum=max(abs(m-a-b-c-d) for a,b,c,d,m in zip(parts['clean'],parts['fan'],parts['noise'],parts['click'],parts['mix']))
        require(max_sum<=2,'component_sum_two_lsb')
        require(truth['rendered_component_sum_verification']['maximum_integer_sample_residual']==max_sum,'saved_sum_receipt_matches')
        row={'id':case['id'],'seed':case['seed'],'cohort':case['cohort'],'headers_verified':5,
             'maximum_component_sum_error_lsb':max_sum,'component_peaks':peaks,'low_register_measurement':None}
        if case['cohort']=='low32-sustain':
            coefficients=joint_fit(parts['clean'],[32.]);amp=math.hypot(coefficients[1],coefficients[2])
            require(abs(amp-.17)<=5e-5,'low32_rendered_amplitude')
            row['low_register_measurement']={'kind':'32hz_joint_dc_sine_cosine','amplitude':amp,'expected_amplitude':.17,'tolerance':5e-5}
        if case['cohort']=='missing-f0-sustain':
            fundamental=plan['signal']['c1_frequency_hz'];harmonics=[1]+[k for k,a in plan['signal']['missing_f0_harmonics']]
            coefficients=joint_fit(parts['clean'],[fundamental*k for k in harmonics])
            amplitudes=[math.hypot(coefficients[1+2*i],coefficients[2+2*i]) for i in range(len(harmonics))]
            require(amplitudes[0]<=5e-5,'missing_fundamental_fit')
            expected=[a for k,a in plan['signal']['missing_f0_harmonics']]
            require(all(abs(a-b)<=5e-5 for a,b in zip(amplitudes[1:],expected)),'generated_harmonic_coefficients')
            row['low_register_measurement']={'kind':'missing_f0_joint_dc_sine_cosine','f0_hz':fundamental,'fundamental_amplitude':amplitudes[0],
                    'harmonics':harmonics,'amplitudes':amplitudes,'harmonic_expected_amplitudes':expected,'tolerance':5e-5}
        parameter=next(x for x in plan['parameters'] if x['seed']==case['seed'])
        require(truth['motif_parameters']==parameter['motif'] and truth['nuisance_parameters']==parameter['nuisance'],'preregistered_parameters_unchanged')
        if case['cohort'] in COHORTS[4:]:
            positive+=1;require(len(truth['recurrence_pairs'])==1,'generated_positive_reference_count')
            motif=parameter['motif'];length=motif['duration']['native_sample']
            first,second=[motif[k]['native_sample'] for k in ('first_start','second_start')]
            require(parts['clean'][first:first+length]==parts['clean'][second:second+length],'saved_identical_motif_copies')
            row['saved_motif_copies_equal']=True
        else:
            negative+=1;require(truth['recurrence_pairs']==[] and truth['negative_riff_reference'] is True,'generated_negative_reference')
            require(truth['no_acoustic_repetition_claim'] is True,'negative_acoustic_scope')
        results.append(row)
    require(wav_count==60 and positive==4 and negative==8 and shared==index['shared_component_sha256'],'complete_bank_construction_counts')
    # Read back every previously verified artifact after all measurements.
    before=dict(FILES)
    for name,sha in before.items():read_exact(ROOT/name,sha,20_000_000)
    require(hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==source_before,'auditor_source_changed')
    report={'schema_version':1,'status':'verified_generated_bank_construction_only','actor':'phrase_dag','authority':'root_BANKQC/R-HOOK-CONVERGENCE-20261004/R-N13',
        'time_utc':datetime.now(timezone.utc).isoformat(),'bank_index':str((BANK/'fixtures.json').relative_to(ROOT)),
        'bank_index_sha256':INDEX_SHA,'generation_sha256':GENERATION_SHA,'worker_sha256_before':WORKER_SHA,'worker_sha256_after':WORKER_SHA,
        'plan_sha256':PLAN_SHA,'auditor_sha256':source_before,'wav_headers_verified':60,'positive_cases':4,'negative_cases':8,
        'native_seconds':96,'sample_rate':48000,'channels':1,'samples_per_case':384000,'maximum_sum_error_lsb':max(r['maximum_component_sum_error_lsb'] for r in results),
        'shared_component_sha256':shared,'cases':results,'verified_file_sha256':before,'verified_files_count':len(before),'all_hashes_rechecked_unchanged':True,
        'source_audio_bytes_read':True,'native_pcm_unpacked':True,'truth_construction_metadata_read':True,'waveform_regenerated':False,
        'feature_discovery_invoked':False,'model_inference_invoked':False,'phrase_accuracy_scored':False,'settings_retuned':False,
        'musical_performance_accepted':False,'canonical_defaults_activated':False,'numerical_threads':1,'elapsed_seconds':time.monotonic()-STARTED,
        'measurement_protocol':{'interval_seconds':[2,6],'stride_native_samples':24,'effective_measurement_rate':2000,
            'method':'independent_joint_dc_sine_cosine_pivoted_least_squares','no_frontend_or_fft':True}}
    target=ROOT/'docs/agent-notes/2026-10-06-phrase-localization-bank-qc.json'
    with target.open('x') as handle:json.dump(report,handle,indent=2,allow_nan=False);handle.write('\n')
    print(json.dumps({k:report[k] for k in ('status','wav_headers_verified','verified_files_count','positive_cases','negative_cases','maximum_sum_error_lsb','elapsed_seconds')}))
    print(json.dumps({'result':str(target.relative_to(ROOT)),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}))


if __name__=='__main__':check()
