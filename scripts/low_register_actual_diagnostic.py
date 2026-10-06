#!/usr/bin/env python3
"""Prepare, or explicitly release, a bounded source-native mixture diagnostic.

`plan` reads metadata only. `execute` requires a root-owned release receipt and
positive independent audit, and never writes media/master/default artifacts.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts'/'experiments'/'low-register-actual-diagnostic'
WORKER=ROOT/'scripts'/'low_register_denoise_probe.py'
WORKER_SHA='384a99bca9e72212b5d9631e9b425424ea7b08fc41ce6eb4dde4d647b3ba3bc6'
SOURCE_SHA='a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6'
PCM_SHA='d68e49688293b1fb8c7c2566e2ecd6e31df9972af013dd23454e15864654bd2a'
MANIFEST=ROOT/'artifacts'/'runs'/'20261005T232627Z-eb7bead2ae74'/'manifest.json'
COMPARISON=ROOT/'docs'/'agent-notes'/'2026-10-05-captured-restoration-comparison.json'
COMPARISON_SHA='16a333af8d6068aabb4215cf183fa2d18b6726d38affcbe439c29d55cf004e0f'


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def read_json(path):
    p=Path(path)
    if not p.is_file() or p.is_symlink() or p.stat().st_size>1_000_000:raise ValueError('Bounded regular metadata required')
    def pairs(rows):
        obj={}
        for k,v in rows:
            if k in obj:raise ValueError('Duplicate metadata key')
            obj[k]=v
        return obj
    def reject(value):raise ValueError('Nonfinite metadata')
    value=json.loads(p.read_bytes(),object_pairs_hook=pairs,parse_constant=reject)
    canonical(value)
    return value


def new_output(path):
    p=Path(path).absolute()
    if ('..' in p.parts or not p.is_relative_to(BASE) or p==BASE or p.exists()
            or any(q.is_symlink() for q in (p,*p.parents))):
        raise ValueError('New output must be beneath the diagnostic artifact root')
    return p


def write_new(path,value):
    with Path(path).open('xb') as f:f.write(canonical(value)+b'\n')


def declaration():
    # No PCM/source payload is opened by this preparation operation.
    if digest(WORKER)!=WORKER_SHA or digest(COMPARISON)!=COMPARISON_SHA:raise ValueError('Frozen worker/evidence differs')
    m=read_json(MANIFEST);comparison=read_json(COMPARISON)
    source=m['source'];probe=source['probe']['audio']
    row=next(r for r in comparison['candidates'] if r['run_id']=='20261005T232627Z-eb7bead2ae74')
    pcm=row['artifacts']['source']
    if source['sha256']!=SOURCE_SHA or pcm['sha256']!=PCM_SHA or pcm['sample_rate']!=44100 or pcm['channels']!=1 or pcm['sample_frames']!=6657385:
        raise ValueError('Source identity/native metadata changed')
    if probe['sample_rate']!=44100 or probe['channels']!=1 or m['timeline']['audio_origin_receipt']['seconds']!=0:
        raise ValueError('Decoded origin metadata differs')
    rate=44100;length=8192;hop=2048;a=20*rate;b=30*rate;ca=180810;cb=218295
    cap_first=((ca+hop-1)//hop)*hop
    guard=length-1
    return {'schema_version':1,'kind':'preregistered_actual_mixture_diagnostic','status':'preparation_only',
      'worker_sha256':WORKER_SHA,'harness_sha256':digest(Path(__file__)),
      'source':{'path':source['path'],'sha256':SOURCE_SHA,'decoded_pcm_path':pcm['path'],'decoded_pcm_sha256':PCM_SHA,
        'manifest_path':str(MANIFEST),'manifest_sha256':digest(MANIFEST),'comparison_sha256':COMPARISON_SHA,
        'sample_rate':rate,'channels':1,'sample_frames':6657385,'decoded_origin_media_seconds':0.},
      'diagnostic':{'start_sample':a,'end_sample':b,'sample_frames':b-a,'seconds':10.,
        'selection':'neutral fixed interval 20–30 seconds, not chosen after diagnostic results',
        'source_relative_time_origin':'decoded source audio sample zero','synthetic_alignment_prefix_samples':a%hop,
        'frame_global_anchor_sample':0,'frame_samples':length,'hop_samples':hop,
        'metric_start_sample':a+guard,'metric_end_sample':b-guard,'metric_sample_frames':b-a-2*guard,
        'edge_policy':'retain exact10s array; descriptive metrics only conservative complete-OLA-support interior',
        'outside_interval_context_samples_read':0},
      'capture':{'reviewed_start_sample':ca,'reviewed_end_sample':cb,'reviewed_seconds':.85,
        'first_global_grid_start_sample':cap_first,'fit_end_sample':cb,
        'full_frame_count':(cb-cap_first-length)//hop+1,
        'status':'previously reviewed, music contamination unresolved, not verified fan-only',
        'capture_reuse':'read existing decoded PCM, no new media decode'},
      'settings':[{'low_ceiling_db':low,'noise_density_scale':scale,'broadband_ceiling_db':8.}
        for low in (0.,.5) for scale in (.5,1.)],
      'metrics':{'bands_hz':[[20,45],[45,120],[140,8000]],'welch_frame_samples':8192,'welch_hop_samples':2048,
        'window':'periodic Hann','detrend':False,'phase_alignment':'sourceglobal grid, no fitted shift',
        'welch_first_native_start_sample':((a+guard+hop-1)//hop)*hop,
        'coherence':'source-power-weighted mean of per-bin magnitude-squared coherence',
        'purpose':'mixture energy/coherence and residue descriptors; no isolated fan/music truth'},
      'bounds':{'diagnostic_pcm_seconds':10.,'existing_capture_pcm_seconds':.85,'total_selected_pcm_seconds':10.85,
        'additional_context_seconds':0.,'new_ffmpeg_decode_seconds':0.,'threads':2,'deadline_seconds':120},
      'prohibited':{'normalization':True,'eq':True,'compression':True,'media_export':True,
        'master_or_latest_replacement':True,'isolated_stem_claim':True,'note_correctness':True},
      'release_required':{'root_explicit_release':True,'positive_independent_mask_metric_audit':True,
        'elapsed_time_is_not_release':True},'actual_audio_read':False,'listening_accepted':False,'default_adoption':False}


def validate_release(plan_path,release_path):
    plan=read_json(plan_path);release=read_json(release_path)
    if (release.get('action')!='execute_actual_low_register_diagnostic'
            or release.get('root_explicit_release') is not True
            or release.get('plan_sha256')!=digest(plan_path)
            or release.get('worker_sha256')!=WORKER_SHA
            or release.get('audit_verdict')!='positive_independent_mask_metric_audit'):
        raise ValueError('Exact root release and positive audit required')
    audit=Path(release['audit_path'])
    if not audit.is_file() or audit.is_symlink() or digest(audit)!=release['audit_sha256']:
        raise ValueError('Independent audit receipt binding mismatch')
    if canonical(plan)!=canonical(declaration()):raise ValueError('Preregistered source/settings/harness changed')
    return plan,release


def execute(plan_path,release_path,output):
    plan,release=validate_release(plan_path,release_path)
    dest=new_output(output);started=time.monotonic();deadline=started+120
    spec=importlib.util.spec_from_file_location('frozen_low_register_diagnostic_worker',WORKER)
    worker=importlib.util.module_from_spec(spec);sys.modules[spec.name]=worker;spec.loader.exec_module(worker)
    np=worker.np;wavfile=worker.wavfile;s=plan['source'];d=plan['diagnostic'];c=plan['capture']
    original=Path(s['path']);wav=Path(s['decoded_pcm_path'])
    if digest(original)!=s['sha256'] or digest(wav)!=s['decoded_pcm_sha256']:raise ValueError('Original/decoded input hash differs')
    rate,data=wavfile.read(wav,mmap=True)
    if data.dtype!=np.float32 or rate!=44100 or data.shape!=(s['sample_frames'],):raise ValueError('Canonical native WAV header differs')
    # Only these selected spans become numeric PCM arrays. Outside context is zero.
    excerpt=np.array(data[d['start_sample']:d['end_sample']],dtype=np.float64)[:,None]
    capture=np.array(data[c['reviewed_start_sample']:c['reviewed_end_sample']],dtype=np.float64)[:,None]
    prefix=d['synthetic_alignment_prefix_samples'];extended=np.pad(excerpt,((prefix,0),(0,0)))
    cap_offset=c['first_global_grid_start_sample']-c['reviewed_start_sample']
    cap_fit=capture[cap_offset:]
    metric_a=d['metric_start_sample']-d['start_sample'];metric_b=d['metric_end_sample']-d['start_sample']
    stage=dest.parent/('.'+dest.name+'-stage-'+uuid.uuid4().hex);stage.mkdir(parents=True,exist_ok=False)
    try:
        jobs=[]
        for setting in plan['settings']:
            worker.deadline_check(deadline);config=worker.MaskConfig(rate,**setting)
            frames=worker.analyze_native(extended,config=config)
            density=worker.fit_capture_density(cap_fit,config=config,source_sha256=s['sha256'],
              decoded_start_sample=c['first_global_grid_start_sample'],decoded_end_sample=c['fit_end_sample'])
            gain=worker.derive_gain(frames,density,config=config)
            processed=worker.apply_frozen_gain(extended,gain,config=config)[prefix:prefix+len(excerpt)]
            residue=excerpt-processed
            global_starts=frames.native_starts+d['start_sample']-prefix
            full_support=(global_starts>=d['start_sample'])&(global_starts+8192<=d['end_sample'])
            name=f"p{setting['low_ceiling_db']:g}-n{setting['noise_density_scale']:g}";folder=stage/name;folder.mkdir()
            for key,array in [('mask',gain.gains),('density',density.density),('processed',processed),('residue',residue)]:
                np.save(folder/(key+'.npy'),array,allow_pickle=False)
            hashes={key:worker.digest(folder/(key+'.npy')) for key in ('mask','density','processed','residue')}
            before=excerpt[metric_a:metric_b];after=processed[metric_a:metric_b]
            first_welch=plan['metrics']['welch_first_native_start_sample']-d['metric_start_sample']
            w=worker.window(config);starts=range(first_welch,len(before)-8192+1,2048)
            xb=np.stack([before[i:i+8192].T for i in starts]);yb=np.stack([after[i:i+8192].T for i in starts])
            x=np.fft.rfft(xb*w,axis=-1);y=np.fft.rfft(yb*w,axis=-1)
            pxx=np.mean(abs(x)**2,axis=0)[0];pyy=np.mean(abs(y)**2,axis=0)[0];pxy=np.mean(x*np.conj(y),axis=0)[0]
            coherence=np.divide(abs(pxy)**2,pxx*pyy,out=np.zeros_like(pxx),where=pxx*pyy>0)
            frequencies=np.fft.rfftfreq(8192,1/rate);bands={}
            for low,high in plan['metrics']['bands_hz']:
                selected=(frequencies>=low)&(frequencies<high);weights=pxx[selected]
                bands[f'{low}-{high}']={'mixture_power_change':worker.db_ratio(worker.band_power(after,rate,low,high),worker.band_power(before,rate,low,high)),
                  'source_weighted_coherence':float(np.sum(weights*coherence[selected])/np.sum(weights)) if np.sum(weights)>0 else None,
                  'welch_bin_count':int(np.sum(selected)),'welch_full_frame_count':len(x),
                  'welch_first_native_start_sample':plan['metrics']['welch_first_native_start_sample'],
                  'isolated_fan_reduction':None,'musical_component_gain':None}
            job={'variant':name,'settings':setting,'hashes':hashes,'sample_frames':len(processed),'native_start_sample':d['start_sample'],
              'frame_native_starts':global_starts.tolist(),'frame_native_centers':(global_starts+4096).tolist(),
              'frame_full_original_support':full_support.tolist(),'metric_start_sample':d['metric_start_sample'],
              'metric_end_sample':d['metric_end_sample'],'band_descriptors':bands,
              'mixture_rms_change':worker.db_ratio(float(np.mean(after**2)),float(np.mean(before**2))),
              'residue_rms':float(np.sqrt(np.mean(residue[metric_a:metric_b]**2))),
              'claim_scope':'descriptive actual mixture changes, unresolved source separability',
              'noise_only_capture_verified':False,'listening_accepted':False,'default_adoption':False}
            write_new(folder/'diagnostic.json',job);jobs.append(job)
        if digest(original)!=s['sha256'] or digest(wav)!=s['decoded_pcm_sha256'] or digest(WORKER)!=WORKER_SHA:
            raise ValueError('Source or frozen worker changed')
        worker.deadline_check(deadline)
        result={'schema_version':1,'status':'bounded_actual_mixture_diagnostics_complete','plan_sha256':digest(plan_path),
          'release_sha256':digest(release_path),'positive_audit_sha256':release['audit_sha256'],'worker_sha256':WORKER_SHA,
          'source_sha256':s['sha256'],'decoded_pcm_sha256':s['decoded_pcm_sha256'],'source_hashes_preserved':True,
          'diagnostic_source_seconds':10.,'reused_capture_seconds':.85,'outside_context_samples_read':0,
          'elapsed_seconds':time.monotonic()-started,'jobs':jobs,'media_exported':False,'master_replaced':False,
          'isolated_sources_identified':False,'listening_accepted':False,'default_adoption':False}
        write_new(stage/'results.json',result);stage.rename(dest);return result
    except Exception as exc:
        write_new(stage/'failure.json',{'status':'failed','reason':str(exc),'actual_master_modified':False})
        raise RuntimeError(f'{exc}; retained failed stage {stage}') from exc


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='operation',required=True)
    p=sub.add_parser('plan');p.add_argument('--output',required=True)
    e=sub.add_parser('execute');e.add_argument('--plan',required=True);e.add_argument('--release-receipt',required=True);e.add_argument('--output',required=True)
    args=parser.parse_args()
    if args.operation=='plan':
        path=new_output(args.output);path.parent.mkdir(parents=True,exist_ok=True);write_new(path,declaration())
        result={'status':'preparation_only','plan_path':str(path),'plan_sha256':digest(path),'actual_audio_read':False}
    else:
        r=execute(args.plan,args.release_receipt,args.output);result={k:v for k,v in r.items() if k!='jobs'}
    print(json.dumps(result,sort_keys=True,allow_nan=False))


if __name__=='__main__':main()
