#!/usr/bin/env python3
"""Experimental L1 fixed-diagonal support localization from immutable caches."""
from __future__ import annotations

import argparse
import ast
import bisect
import copy
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import stat
import struct
import sys
import zipfile
import zlib

ROOT=Path(__file__).resolve().parents[1]
PARSER_SHA256='a91ce8e9386cc7c63c5a5d53b8233f2c46a1f42fdd06ab1ae0eea3dc83405805'
PLAN_SHA256='230022f9a0d059036e8fadb62315b1abcd7108166df81b73ffb72a7828584273'
if hashlib.sha256((ROOT/'scripts/pitch_evaluate.py').read_bytes()).hexdigest()!=PARSER_SHA256:
    raise ValueError('Frozen parser dependency changed')
spec=importlib.util.spec_from_file_location('phrase_localize_json',ROOT/'scripts/pitch_evaluate.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
require=base.require
HOP=.016
SETTINGS={'arm':'L1_fixed_diagonal_cache_only','roi_margin_seconds':.256,'cosine_threshold':.8,
    'minimum_support_seconds':.5,'maximum_nonpositive_gap_seconds':.128,'different_extent_tie_epsilon':1e-12,
    'active_dimension_std_threshold':1e-5,'z_clip':4.,'internal_change_rms_threshold':.25,
    'minimum_internal_changes':2,'internal_change_spacing_seconds':.128,'endpoint_guard_seconds':.128,
    'maximum_frames':512,'maximum_dimensions':26,'maximum_proposals':60,'maximum_retained':10,
    'maximum_tile_rows':256,'maximum_tile_columns':256,'maximum_cells':2_000_000,
    'numerical_threads':2,'warp_steps':False,'competitor_order_margin_preserved_not_recomputed':.10}


def number(value):
    require(type(value) in (int,float) and math.isfinite(value),'finite_nonboolean_number_required')
    return float(value)


def path(value):
    value=Path(value)
    require('..' not in value.parts,'path_traversal')
    if not value.is_absolute():value=ROOT/value
    allowed=ROOT/'artifacts'
    require(value.is_relative_to(allowed) and value!=allowed,'path_outside_artifacts')
    current=ROOT
    for part in value.relative_to(ROOT).parts:
        current=current/part;require(not current.is_symlink(),'symlink_path')
    return value


def read(value,limit,expected):
    value=path(value);flags=os.O_RDONLY|os.O_NOFOLLOW
    directory=os.open(ROOT/'artifacts',flags|os.O_DIRECTORY);fds=[directory]
    try:
        parts=value.relative_to(ROOT/'artifacts').parts
        for part in parts[:-1]:
            directory=os.open(part,flags|os.O_DIRECTORY,dir_fd=directory);fds.append(directory)
        fd=os.open(parts[-1],flags,dir_fd=directory);fds.append(fd);before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size<=limit,'regular_file_bound')
        with os.fdopen(os.dup(fd),'rb') as handle:raw=handle.read(limit+1)
        after=os.fstat(fd)
        require(len(raw)==before.st_size==after.st_size<=limit and before.st_mtime_ns==after.st_mtime_ns,
                'file_changed_or_oversized')
    finally:
        for fd in reversed(fds):os.close(fd)
    digest=hashlib.sha256(raw).hexdigest()
    require(digest==base.fingerprint(expected),'sha256_mismatch')
    return raw


def json_receipt(value,expected):
    raw=read(value,5_000_000,expected);base.check_json_depth(raw)
    value=json.loads(raw,object_pairs_hook=base.unique_object,parse_constant=base.reject_constant,
        parse_float=base.finite_float,parse_int=base.bounded_int)
    require(isinstance(value,dict),'json_object_required');return value


def npy(raw):
    require(raw.startswith(b'\x93NUMPY') and len(raw)>=10,'invalid_npy')
    version=tuple(raw[6:8]);require(version in ((1,0),(2,0)),'unsupported_npy_version')
    width=2 if version==(1,0) else 4;size=int.from_bytes(raw[8:8+width],'little')
    require(0<size<=4096 and len(raw)>=8+width+size,'npy_header_bound')
    try:header=ast.literal_eval(raw[8+width:8+width+size].decode('latin1').strip())
    except (ValueError,SyntaxError,RecursionError) as exc:raise base.EvaluationError('invalid_npy_header') from exc
    require(isinstance(header,dict) and set(header)=={'descr','fortran_order','shape'}
        and header['fortran_order'] is False and header['descr'] in ('<f4','<f8'),'npy_numeric_c_order_required')
    shape=header['shape'];require(isinstance(shape,tuple) and 1<=len(shape)<=2
        and all(type(n) is int and 0<=n<=512 for n in shape),'npy_shape_bound')
    fmt,size=('f',4) if header['descr']=='<f4' else ('d',8);body=raw[8+width+int.from_bytes(raw[8:8+width],'little'):]
    require(len(body)==math.prod(shape)*size,'npy_payload_extent')
    values=[v[0] for v in struct.iter_unpack('<'+fmt,body)]
    require(all(math.isfinite(v) and abs(v)<=1e12 for v in values),'invalid_feature_value')
    if len(shape)==2:return [values[i*shape[1]:(i+1)*shape[1]] for i in range(shape[0])]
    return values


def cache_receipt(value,expected):
    raw=read(value,10*1024**2,expected);result={}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries=archive.infolist();names={'features.npy','times.npy','centroid.npy','onsets.npy'}
            require(len(entries)==4 and {e.filename for e in entries}==names,'cache_members_required')
            require(sum(e.file_size for e in entries)<=1024**2,'cache_expansion_bound')
            for entry in entries:
                require(entry.compress_type in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED) and not entry.flag_bits&1
                    and not ((entry.external_attr>>16)&0o170000)==0o120000,'unsafe_cache_member')
                with archive.open(entry) as handle:decoded=handle.read(entry.file_size+1)
                require(len(decoded)==entry.file_size,'cache_member_extent')
                result[entry.filename[:-4]]=npy(decoded)
    except (zipfile.BadZipFile,zlib.error,RuntimeError,EOFError) as exc:
        raise base.EvaluationError('invalid_cache_archive') from exc
    return result


def standardized(features):
    count=len(features[0]);active=[]
    for row in features:
        mean=math.fsum(row)/count
        scale=math.sqrt(math.fsum((v-mean)**2 for v in row)/count)
        if scale>1e-5:active.append([max(-4.,min(4.,(v-mean)/scale)) for v in row])
    return [[row[i] for row in active] for i in range(count)],len(active)


def cosine(a,b):
    first=math.fsum(v*v for v in a);second=math.fsum(v*v for v in b)
    if not first or not second:return None
    return max(-1.,min(1.,math.fsum(x*y for x,y in zip(a,b))/math.sqrt(first*second)))


def unknown(reason,cells=0):
    return {'status':'localization_unknown','reason':reason,'confidence':None,'localized_support':None,'cells_visited':cells}


def extent(times,start,end,indices,duration,origin):
    a,b=times[start],times[end]
    left=max(0.,a-HOP/2);right=min(duration,b+HOP/2)
    return {'first_frame_index':indices[start],'last_frame_index':indices[end],
        'first_center_audio_relative_seconds':a,'last_center_audio_relative_seconds':b,
        'first_center_source_seconds':origin+a,'last_center_source_seconds':origin+b,
        'center_extent_seconds':b-a,'cell_start_audio_relative_seconds':left,'cell_end_audio_relative_seconds':right,
        'source_start_seconds':origin+left,'source_end_seconds':origin+right,
        'fft_support_start_audio_relative_seconds':max(0.,a-.128),
        'fft_support_end_audio_relative_seconds':min(duration,b+.128),
        'fft_support_start_source_seconds':origin+max(0.,a-.128),
        'fft_support_end_source_seconds':origin+min(duration,b+.128),
        'fft_padding_before_seconds':max(0.,.128-a),'fft_padding_after_seconds':max(0.,b+.128-duration),
        'fft_support_uncertainty_seconds':.256}


def internal_changes(times,z,start,end,span):
    eligible=[]
    for i in range(start+1,end+1):
        t=times[i]
        if (t-span['cell_start_audio_relative_seconds']<=.128+1e-12
                or span['cell_end_audio_relative_seconds']-t<=.128+1e-12):continue
        rms=math.sqrt(math.fsum((a-b)**2 for a,b in zip(z[i],z[i-1]))/len(z[i]))
        if rms>=.25:eligible.append({'audio_relative_seconds':t,'dimension_normalized_rms_z_change':rms})
    chosen=[]
    for row in eligible:
        if not chosen or row['audio_relative_seconds']-chosen[-1]['audio_relative_seconds']>=.128-1e-12:
            chosen.append(row)
    return chosen


def diagonal_support(times_a,times_b,z_a,z_b,*,indices_a=None,indices_b=None,duration=None,source_origin=0.):
    n,m=len(times_a),len(times_b);cells=n*m
    require(n<=512 and m<=512 and len(z_a)==n and len(z_b)==m,'roi_frame_bound')
    require(all(type(t) in (float,int) and math.isfinite(t) for t in times_a+times_b),'invalid_roi_clock')
    require(all(b>a for times in (times_a,times_b) for a,b in zip(times,times[1:])),'roi_clock_order')
    if not n or not m:return unknown('insufficient_roi_frames')
    if not z_a[0] or not z_b[0]:return unknown('stationary_or_insufficient_internal_change')
    require(all(len(v)==len(z_a[0]) and all(math.isfinite(x) for x in v) for v in z_a+z_b),'roi_vector_shape')
    indices_a=indices_a if indices_a is not None else list(range(n));indices_b=indices_b if indices_b is not None else list(range(m))
    require(len(indices_a)==n and len(indices_b)==m,'roi_index_extent')
    duration=duration if duration is not None else max(times_a[-1],times_b[-1])+HOP/2
    previous=[None]*m;best=None;ties=set();tiles=[]
    for block in range(0,n,256):
        for col in range(0,m,256):tiles.append([min(256,n-block),min(256,m-col)])
        for i in range(block,min(n,block+256)):
            current=[None]*m
            for col in range(0,m,256):
                for j in range(col,min(m,col+256)):
                    if times_a[i]>=times_b[j]:continue
                    value=cosine(z_a[i],z_b[j]);reward=(value-.8) if value is not None else -.8
                    prev=previous[j-1] if i and j else None
                    if prev and (abs(times_a[i]-times_a[i-1]-HOP)>1e-10
                            or abs(times_b[j]-times_b[j-1]-HOP)>1e-10):prev=None
                    gap=(prev[3]+HOP if prev and reward<=0 else HOP if reward<=0 else 0.)
                    if gap>.128+1e-12:prev=None
                    score=max(0.,(prev[0] if prev else 0.)+reward)
                    if score<=0:continue
                    state=(score,prev[1] if prev else i,prev[2] if prev else j,gap)
                    current[j]=state
                    if reward<=0:continue
                    a,b=state[1],state[2]
                    first=extent(times_a,a,i,indices_a,duration,source_origin)
                    second=extent(times_b,b,j,indices_b,duration,source_origin)
                    lengths=[s['cell_end_audio_relative_seconds']-s['cell_start_audio_relative_seconds'] for s in (first,second)]
                    if min(lengths)<.5-1e-12 or first['cell_end_audio_relative_seconds']>second['cell_start_audio_relative_seconds']+1e-12:continue
                    key=(a,i,b,j)
                    if best is None or score>best[0]+1e-12:best=(score,key);ties={key}
                    elif abs(score-best[0])<=1e-12:ties.add(key)
            previous=current
    if best is None:return unknown('no_ordered_support_of_minimum_duration',cells)
    if len(ties)>1:return unknown('nonunique_maximum_support',cells)
    score,(a,i,b,j)=best;first=extent(times_a,a,i,indices_a,duration,source_origin);second=extent(times_b,b,j,indices_b,duration,source_origin)
    changes=[internal_changes(t,z,left,right,span) for t,z,left,right,span in
             [(times_a,z_a,a,i,first),(times_b,z_b,b,j,second)]]
    if any(len(rows)<2 for rows in changes):return unknown('stationary_or_insufficient_internal_change',cells)
    positive=unsupported=0;positive_durations={'first':0.,'second':0.};unsupported_durations={'first':0.,'second':0.}
    for x,y in zip(range(a,i+1),range(b,j+1)):
        c=cosine(z_a[x],z_b[y])
        matched=c is not None and c>.8
        if matched:positive+=1
        else:unsupported+=1
        durations=positive_durations if matched else unsupported_durations
        for axis,t in [('first',times_a[x]),('second',times_b[y])]:
            durations[axis]+=min(duration,t+HOP/2)-max(0.,t-HOP/2)
    return {'status':'localized_support_candidate','reason':None,'confidence':None,'cells_visited':cells,
        'localized_support':{'first':first,'second':second,'total_reward':score,
            'support_duration_seconds':{'first':first['cell_end_audio_relative_seconds']-first['cell_start_audio_relative_seconds'],
                                        'second':second['cell_end_audio_relative_seconds']-second['cell_start_audio_relative_seconds']},
            'positive_support_cell_count':positive,'unsupported_cell_count':unsupported,
            'positive_support_duration_seconds':positive_durations,'unsupported_duration_seconds':unsupported_durations,
            'path_frame_pairs':[[indices_a[x],indices_b[y]] for x,y in zip(range(a,i+1),range(b,j+1))],
            'internal_change_evidence':{'first':changes[0],'second':changes[1]},'tile_shapes':tiles}}


def validate(cache,proposals,clock):
    require(clock.get('schema_version')==1,'clock_schema_required')
    require(not base.unsupported_claims(proposals) and not base.unsupported_claims(clock),'unsupported_confirmed_claim')
    require(proposals.get('source_sha256')==clock.get('source_sha256') and proposals.get('cache_sha256')==clock.get('cache_sha256'),'cache_source_binding_mismatch')
    base.fingerprint(clock['source_sha256']);base.fingerprint(clock['cache_sha256'])
    duration=number(clock['duration_seconds']);origin=number(clock['audio_start_seconds'])
    require(0<duration<=8.192 and origin>=0 and number(proposals['duration_seconds'])==duration,'duration_origin_binding')
    native,analysis,feature=clock['native_pcm'],clock['analysis_pcm'],clock['feature_clock']
    require(native.get('sample_rate')==48000 and native.get('channels')==1 and analysis.get('sample_rate')==16000
            and type(native.get('sample_count')) is int and type(analysis.get('sample_count')) is int
            and native['sample_count']==analysis['sample_count']*3
            and abs(native['sample_count']/48000-duration)<1e-10,'native_analysis_extent_mismatch')
    require(feature.get('hop_samples')==256 and feature.get('fft_samples')==4096
            and type(feature.get('centered')) is bool and feature.get('timestamp_convention')=='frame_centers_audio_relative','unsupported_feature_clock')
    times=cache['times'];features=cache['features'];indices=feature['frame_indices']
    require(isinstance(times,list) and 1<=len(times)<=512 and len(indices)==len(times)
        and all(type(i) is int and i>=0 for i in indices) and all(b>a for a,b in zip(indices,indices[1:])),'frame_index_bound_or_order')
    offset=0. if feature['centered'] else .128
    require(all(abs(number(t)-(i*HOP+offset))<1e-10 and 0<=t<=duration+1e-10 for i,t in zip(indices,times)),'frame_center_clock_mismatch')
    require(isinstance(features,list) and 1<=len(features)<=26 and all(isinstance(row,list) and len(row)==len(times)
            and all(math.isfinite(number(v)) and abs(v)<=1e12 for v in row) for row in features),'feature_matrix_extent')
    require(len(cache['centroid'])==len(times) and all(number(v)>=0 for v in cache['centroid'])
            and isinstance(cache['onsets'],list) and len(cache['onsets'])<=512
            and all(0<=number(v)<=duration for v in cache['onsets']),'auxiliary_cache_extent')
    universe=proposals.get('proposal_universe');rows=proposals.get('arms',{}).get('Border')
    require(isinstance(universe,list) and len(universe)<=60 and isinstance(rows,list) and len(rows)<=10,'proposal_count_bound')
    ids=[]
    for row in rows:
        candidate=row['original_candidate_index'];require(type(candidate) is int and 0<=candidate<len(universe),'candidate_identity_bound')
        ids.append(candidate)
        a,b,c,d=[number(row[k]) for k in ('first_start_seconds','first_end_seconds','second_start_seconds','second_end_seconds')]
        require(0<=a<b<=c<d<=duration,'candidate_span_order')
        require(all(row[k]==universe[candidate].get(k) for k in ('first_start_seconds','first_end_seconds','second_start_seconds','second_end_seconds')),'candidate_raw_window_mismatch')
    require(len(set(ids))==len(ids),'duplicate_candidate_identity')
    return duration,origin,indices


def localize(cache,proposals,clock):
    duration,origin,indices=validate(cache,proposals,clock)
    z,active=standardized(cache['features']);times=cache['times'];results=[];total=0
    for raw in proposals['arms']['Border']:
        spans=[];slices=[]
        for prefix in ('first','second'):
            left=max(0.,raw[prefix+'_start_seconds']-.256);right=min(duration,raw[prefix+'_end_seconds']+.256)
            spans.append([left,right]);slices.append((bisect.bisect_left(times,left),bisect.bisect_left(times,right)))
        (a,b),(c,d)=slices;cells=(b-a)*(d-c)
        if total+cells>2_000_000:result=unknown('total_cell_budget_exhausted')
        else:
            result=diagonal_support(times[a:b],times[c:d],z[a:b],z[c:d],indices_a=indices[a:b],indices_b=indices[c:d],
                duration=duration,source_origin=origin);total+=result['cells_visited']
        results.append({'candidate_id':raw['original_candidate_index'],'raw_candidate':copy.deepcopy(raw),
            'roi_audio_relative_seconds':{'first':spans[0],'second':spans[1]},'raw_fallback_available':True,**result})
    localized=sum(r['status']=='localized_support_candidate' for r in results)
    return {'schema_version':1,'status':'partial_cell_budget_coverage' if any(r['reason']=='total_cell_budget_exhausted' for r in results)
            else 'completed_experimental_cache_only','settings':copy.deepcopy(SETTINGS),
        'candidate_count_pre_selection':len(proposals['proposal_universe']),'retained_raw_count':len(results),
        'localized_count':localized,'abstained_count':len(results)-localized,'active_dimensions':active,
        'cells_visited':total,'source_sha256':clock['source_sha256'],'cache_sha256':clock['cache_sha256'],
        'clock':copy.deepcopy(clock),'candidates':results,'confidence':None,'audio_decoded':False,'inference_invoked':False,
        'localization_computed':True,'model_inference_invoked':False,'audio_feature_extraction_invoked':False,
        'truth_received':False,'musical_performance_graded':False,'physical_latency_calibrated':False,
        'limitations':['Acoustic support is not full intended phrases or identified guitar notes.',
            'Stationary guitar may abstain; variable fan/click textures can pass.',
            'Raw fallback is not successful localization and all references remain in future evaluation.',
            'L1 cannot recover missing palm proposals or exceed the523legato ROI geometric ceiling.',
            'FFT support and frame cells are separate; physical resampler/detector latency is unknown.']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('cache','proposals','clock'):
        parser.add_argument('--'+name,required=True,type=Path);parser.add_argument('--'+name+'-sha256',required=True)
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--summary',action='store_true')
    args=parser.parse_args();output=None
    try:
        worker_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        output=path(args.output);require(not output.exists(),'fresh_output_required')
        cache=cache_receipt(args.cache,args.cache_sha256);proposals=json_receipt(args.proposals,args.proposals_sha256)
        clock=json_receipt(args.clock,args.clock_sha256);require(clock['cache_sha256']==args.cache_sha256,'supplied_cache_hash_mismatch')
        result=localize(cache,proposals,clock)
        for name in ('cache','proposals','clock'):read(getattr(args,name),10*1024**2 if name=='cache' else 5_000_000,getattr(args,name+'_sha256'))
        require(hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==worker_hash
                and hashlib.sha256((ROOT/'scripts/pitch_evaluate.py').read_bytes()).hexdigest()==PARSER_SHA256,'worker_or_dependency_changed')
        result['provenance']={'worker_sha256':worker_hash,'parser_dependency_sha256':PARSER_SHA256,'admitted_plan_sha256':PLAN_SHA256,
            'cache_sha256':args.cache_sha256,'proposals_sha256':args.proposals_sha256,'clock_sha256':args.clock_sha256,
            'settings_sha256':hashlib.sha256(json.dumps(SETTINGS,sort_keys=True).encode()).hexdigest(),
            'feature_clock_sha256':hashlib.sha256(json.dumps(clock['feature_clock'],sort_keys=True).encode()).hexdigest(),
            'source_axis_sha256':hashlib.sha256(json.dumps({k:clock[k] for k in
                ('source_sha256','audio_start_seconds','duration_seconds','native_pcm','analysis_pcm')},sort_keys=True).encode()).hexdigest(),
            'source_waveform_bytes_read':False,'feature_cache_bytes_read':True,'source_time_basis':'supplied_hash_bound_clock_metadata'}
        output.parent.mkdir(parents=True,exist_ok=True);output.mkdir(mode=0o700)
        target=output/'phrase-localization.json'
        with target.open('x') as handle:json.dump(result,handle,indent=2,allow_nan=False);handle.write('\n')
        target.chmod(0o600)
        summary={k:result[k] for k in ('status','retained_raw_count','localized_count','abstained_count','cells_visited','audio_decoded','inference_invoked','truth_received')}
        print(json.dumps({**(summary if args.summary else result),'localization_json':str(target)},allow_nan=False));return 0
    except (ValueError,OSError,KeyError,TypeError,AttributeError) as exc:
        print(json.dumps({'status':'failed_structural','error':str(exc),'inference_invoked':False,'truth_received':False}));print(str(exc),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
