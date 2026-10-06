#!/usr/bin/env python3
"""One preregistered generated A/V qualification; execution needs an exact release."""
from __future__ import annotations
import argparse
import array
from contextlib import contextmanager
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import re
import signal
import struct
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT/'docs/agent-notes/2026-10-06-capture-application-native-qualification-plan.md'
PLAN_SHA = 'f2aa237b4d7c0a34e93e5065e7436639a20311c7a81945de196c39c985ecd683'
BASE = ROOT/'artifacts/experiments/capture-application-native-qualification'
PINS = {
 'application':'790ac58f1924db2607087c6ab1cdae5d813ba24eda610af1f396d77e93d06584',
 'author':'7d2820878826c87aabf2ab60b73c997b9d406b7f3ff8943d6012ed967444c355',
 'media':'91443154251888c9e74670790766b289a2618f85f3be806d60ca26882faa9d94'}
FILES = {'application':ROOT/'scripts/apply_capture_profile.py',
         'author':ROOT/'scripts/capture_profile.py','media':ROOT/'scripts/media.py'}
FACTS = {'sample_rate':44100,'channels':2,'sample_count':352800,
 'picture_nominal_frames':204,'picture_decoded_frames':175,'picture_rate':'24/1',
 'picture_origin_seconds':'1/1','audio_origin_seconds':'3/2',
 'picture_end_seconds':'19/2','relative_audio_video_seconds':'1/2',
 'capture_samples':[11025,44100],'capture_seconds':[.25,1.],
 'capture_media_span_seconds':[1.75,2.5],'capture_preroll_samples':37485,
 'denoise_delay_samples':1102,'seed':20261006,'audio_seconds':8.,'picture_seconds':8.5}
CONTROLS = {'reduction_db':3.,'noise_floor_db':-40.,'adaptivity':0.,'gain_smooth':0,
            'integrated_lufs':-18.,'true_peak_dbtp':-1.5}
THREADS = ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS')
MAX_JSON = 1024*1024


def support_facts():
    kept=[n for n in range(204) if n%7!=3]
    return {'picture_indices':kept,'picture_frames':len(kept),
      'last_picture_extent_seconds':str(Fraction(1)+Fraction(kept[-1]+1,24)),
      'capture_training_samples':44100-11025,'capture_guard_samples':4410,
      'filter_trim_samples':[37485+1102,37485+1102+352800]}


def require(value, reason):
    if not value: raise ValueError(reason)


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'


def read_json(path):
    path=Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path,*path.parents)),'Regular nonsymlink metadata required')
    require(path.stat().st_size<=MAX_JSON,'Metadata byte bound exceeded')
    def pairs(rows):
        out={}
        for key,value in rows:
            require(key not in out,'Duplicate metadata key');out[key]=value
        return out
    def reject(_):raise ValueError('Nonfinite metadata')
    value=json.loads(path.read_bytes(),object_pairs_hook=pairs,parse_constant=reject)
    require(isinstance(value,dict),'Metadata object required');encoded(value)
    return value


def write_new(path,value):
    raw=encoded(value);require(len(raw)<=MAX_JSON,'Receipt byte bound exceeded')
    with Path(path).open('xb') as f:f.write(raw)


def verify_pins():
    require(digest(PLAN)==PLAN_SHA,'Qualification plan changed')
    for key,file in FILES.items():require(digest(file)==PINS[key],f'Frozen {key} source changed')


def preregister(trial_id,ffmpeg,ffprobe):
    verify_pins()
    require(isinstance(trial_id,str) and re.fullmatch(r'native-[A-Za-z0-9-]{1,64}',trial_id),'Invalid fixed trial ID')
    binaries={}
    for name,value in [('ffmpeg',ffmpeg),('ffprobe',ffprobe)]:
        path=Path(value).resolve(strict=True)
        require(path.is_file() and os.access(path,os.X_OK),'Existing executable required')
        binaries[name]={'path':str(path),'sha256':digest(path),'expected_version':'8.1.2'}
    return {'schema_version':1,'kind':'generated_capture_application_native_qualification',
      'status':'preregistered_not_executed','plan_sha256':PLAN_SHA,'harness_sha256':digest(__file__),
      'worker_sha256':PINS,'binaries':binaries,'facts':FACTS,'controls':CONTROLS,
      'support':support_facts(),'bypass_profile_sha256':digest(ROOT/'profiles/bypass.json'),
      'trial_id':trial_id,'output':str(BASE/trial_id),'timeout_seconds':600,'threads':2,
      'generation':'one8s_stereo_s16_pcm_plus8.5s_175frame_VFR_Mov_nonzero_origins',
      'review':'generator_inspected_interval; identities_not_authenticated; listening_not_claimed',
      'gates':['exact_native_headers_and_counts','finite_audio_origin_1.5','exact_capture_samples',
       'measured_delay1102_remaining0','source_minus_denoised_residue_error<=2^-22',
       '175decoded_frames_copied_video_payloads_rational_clock_translation-1',
       'AAC_padding_separate_nativeextent_strict_peak<=-1.5','source_parent_latest_unchanged'],
      'actual_media_generated':False,'dsp_performed':False,'listening_accepted':False,'master_adopted':False}


def validate_release(prereg_path,release_path):
    p=read_json(prereg_path);r=read_json(release_path)
    required={'schema_version','action','root_explicit_release','preregistration_sha256',
              'harness_sha256','plan_sha256','worker_sha256','output','authorization_reference'}
    require(set(r)==required,'Release fields differ from the closed contract')
    require(type(r['schema_version']) is int and r['schema_version']==1 and r['root_explicit_release'] is True,'Explicit root release required')
    require(r['action']=='execute_capture_application_native_qualification','Unsupported release action')
    require(r['preregistration_sha256']==digest(prereg_path) and r['harness_sha256']==digest(__file__)
            and r['plan_sha256']==PLAN_SHA and r['worker_sha256']==PINS,'Release identities differ')
    require(isinstance(r['authorization_reference'],str) and 1<=len(r['authorization_reference'])<=512,'Meaningful release reference required')
    require(set(p.get('binaries',{}))=={'ffmpeg','ffprobe'},'Exact two media binaries required')
    expected=preregister(p.get('trial_id'),p['binaries']['ffmpeg']['path'],p['binaries']['ffprobe']['path'])
    require(encoded(p)==encoded(expected) and r['output']==p['output'],'Preregistered source/environment/settings changed')
    dest=Path(p['output'])
    require(dest.parent==BASE and not dest.exists() and not any(q.is_symlink() for q in (dest,*dest.parents)),'Fresh nonsymlink trial required')
    return p,r


def load_application():
    spec=importlib.util.spec_from_file_location('qualification_application',FILES['application'])
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@contextmanager
def bounded_environment(app,prereg,deadline,events):
    keys=(*THREADS,'FFMPEG','FFPROBE');prior={k:os.environ.get(k) for k in keys}
    old_handler=signal.getsignal(signal.SIGALRM);old_timer=signal.getitimer(signal.ITIMER_REAL)
    require(old_timer==(0.,0.),'Existing alarm is outside this harness ownership')
    def expired(_signum,_frame):raise app.ApplyError('Native qualification whole-job deadline exceeded','deadline_exceeded')
    old_app_handler=app.CLI_ALARM_HANDLER
    try:
        for key in THREADS:os.environ[key]='2'
        for name in ('ffmpeg','ffprobe'):os.environ[name.upper()]=prereg['binaries'][name]['path']
        signal.signal(signal.SIGALRM,expired);app.CLI_ALARM_HANDLER=expired
        signal.setitimer(signal.ITIMER_REAL,deadline.remaining())
        with app.private_media(ROOT,deadline,events):yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_handler)
        app.CLI_ALARM_HANDLER=old_app_handler
        for key,value in prior.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value


def generated_samples():
    rng=random.Random(FACTS['seed']);values=array.array('h')
    for i in range(FACTS['sample_count']):
        t=i/44100;noise=.002*rng.uniform(-1,1)
        envelope=0. if t<1.5 else .04*(1 if t<7.5 else math.exp(-(t-7.5)*2))
        clicks=sum(.07*math.exp(-(t-at)/.002)*math.cos(2*math.pi*2100*(t-at))
                   for at in (3.,4.5,7.25,7.99) if 0<=t-at<.008)
        for x in (noise+envelope*math.sin(2*math.pi*32*t)+clicks,
                  -.8*noise+.8*envelope*(math.sin(2*math.pi*65*t)+.2*math.sin(2*math.pi*32*t))+.7*clicks):
            require(math.isfinite(x) and abs(x)<1,'Generated PCM escaped amplitude bound')
            values.append(round(x*32767))
    if sys.byteorder!='little':values.byteswap()
    return values


def mux_arguments(reference,original):
    return ['-copyts','-f','lavfi','-i','testsrc2=size=160x90:rate=24:duration=8.5',
      '-itsoffset','0.5','-i',str(reference),'-map','0:v:0','-map','1:a:0',
      '-vf',r'select=not(eq(mod(n\,7)\,3))','-fps_mode','passthrough',
      '-c:v','mpeg4','-threads','2','-q:v','4','-enc_time_base','1:24000','-video_track_timescale','24000',
      '-c:a','pcm_s16le','-avoid_negative_ts','disabled','-output_ts_offset','1',str(original)]


def picture_frames(media,file,index):
    result=media.run([media.executable('ffprobe'),'-v','error','-threads','2','-select_streams',str(index),
     '-show_frames','-show_entries','frame=best_effort_timestamp,pkt_duration,duration','-of','json',str(file)],60)
    rows=json.loads(result.stdout)['frames'];require(len(rows)==175,'Decoded picture count differs')
    return rows


def picture_gate(media,file,probe):
    rows=picture_frames(media,file,probe['video']['index']);tick=Fraction(probe['video']['time_base'])
    expected=[Fraction(1)+Fraction(n,24) for n in range(204) if n%7!=3]
    starts=[int(row['best_effort_timestamp'])*tick for row in rows]
    require(starts==expected,'Generated VFR decoded PTS differs from preregistered grid')
    duration=int(rows[-1].get('duration',rows[-1].get('pkt_duration',0)))*tick
    require(duration>0 and starts[-1]+duration==Fraction(19,2),'Generated final picture extent differs')
    require(Fraction(str(probe['format']['start_time']))==1
      and Fraction(str(probe['video']['start_time']))==1
      and Fraction(str(probe['audio']['start_time']))==Fraction(3,2),'Generated mux origins differ')
    return {'decoded_frames':175,'time_base':str(tick),'pts_sha256':hashlib.sha256(encoded([str(x) for x in starts])).hexdigest(),
            'last_extent_seconds':'19/2','source_frames':rows}


def current_protection(app,deadline):
    latest=ROOT/'artifacts/latest.json';paths=[latest]
    if latest.exists():
        value=read_json(latest);run=Path(value['run_dir']);require(run.parent==ROOT/'artifacts/runs','Current latest points outside run root')
        manifest=read_json(run/'manifest.json');paths += [run/'manifest.json',Path(manifest['source']['path']),run/'cleaned.wav']
        for key in ('report','video','marked_video','demo_receipt'):
            if value.get(key):paths.append(Path(value[key]))
        for relative in ('export/outcome.json','marked-preview/outcome.json'):
            if (run/relative).exists():paths.append(run/relative)
    result={}
    for file in paths:
        require(file.is_file() and not file.is_symlink(),'Protected current artifact unavailable')
        result[str(file)]=app.digest(file,deadline,3*1024**3,'protected current artifact')
    return result


def check_hashes(app,hashes,deadline):
    for name,sha in hashes.items():require(app.digest(Path(name),deadline,3*1024**3,'immutable input')==sha,'Protected input changed')


def f32_samples(file):
    require(file.stat().st_size<=4*1024**2,'Generated diagnostic WAV byte bound exceeded')
    with file.open('rb') as f:
        header=f.read(12);require(header[:4]==b'RIFF' and header[8:]==b'WAVE','RIFF float PCM required')
        fmt=None;data=None
        for _ in range(128):
            chunk=f.read(8)
            if not chunk:break
            require(len(chunk)==8,'Truncated PCM chunk');kind,size=struct.unpack('<4sI',chunk)
            require(size<=4*1024**2,'PCM chunk byte bound exceeded');payload=f.read(size)
            require(len(payload)==size,'Truncated PCM payload')
            if kind==b'fmt ':fmt=payload
            if kind==b'data':data=payload
            if size%2:f.read(1)
        require(fmt is not None and data is not None,'Missing PCM format/data')
        code,channels,rate,_,_,bits=struct.unpack('<HHIIHH',fmt[:16])
        if code==0xfffe:code=struct.unpack('<I',fmt[24:28])[0]
        require((code,channels,rate,bits)==(3,2,44100,32),'Expected stereo native float32')
        out=array.array('f');out.frombytes(data)
        if sys.byteorder!='little':out.byteswap()
        require(len(out)==705600 and all(math.isfinite(v) for v in out),'Float PCM count/nonfinite failure')
        return out


def s16_to_f32(samples):
    return array.array('f',(value/32768 for value in samples))


def reference_f32(file):
    with wave.open(str(file),'rb') as f:
        require((f.getnchannels(),f.getframerate(),f.getnframes(),f.getsampwidth())==(2,44100,352800,2),
                'Generated reference native header differs')
        samples=array.array('h');samples.frombytes(f.readframes(352800))
    require(len(samples)==705600,'Generated reference sample count differs')
    if sys.byteorder!='little':samples.byteswap()
    return s16_to_f32(samples)


def resume_qualification_alarm(app,deadline,events):
    """Application publication ended its timer; this larger transaction continues.

    Keep committed recovery state intact. Re-arm after every postcommit probe,
    whose existing cleanup legitimately suspends the completed app's timer.
    """
    deadline.check()
    owned_handler=app.CLI_ALARM_HANDLER
    def arm():
        require(signal.getsignal(signal.SIGALRM) is owned_handler,'Qualification alarm ownership changed')
        remaining=deadline.ends-time.monotonic()
        if remaining>0:signal.setitimer(signal.ITIMER_REAL,remaining)
    arm()
    def postcommit_run(command,timeout=600):
        try:return app.run_owned(command,deadline=deadline,timeout=timeout,events=events)
        finally:arm()
    # bounded_environment's private_media finally restores the prior run helper.
    # No application DSP is modified; only following qualification probes use it.
    app.media.run=postcommit_run


def native_gate(app,manifest,candidate):
    expected={'sample_rate':44100,'channels':2,'sample_count':352800}
    for key,value in expected.items():require(manifest['pcm'][key]==value,'Native manifest extent differs')
    for name in ('source.wav','denoised.wav','residue.wav','baseline.wav','cleaned.wav'):
        actual=app.capture.native_pcm(candidate/name,app.capture.Deadline(60))
        require(all(actual[k]==v for k,v in expected.items()),'Native output header differs')
        require(actual['codec']==('pcm_s24le' if name in ('baseline.wav','cleaned.wav') else 'pcm_f32le'),'Unexpected native PCM encoding')
        require(digest(candidate/name)==manifest['output_sha256'][name],'Native output hash differs')
    require(not (candidate/'processed.wav').exists(),'Unexpected post-processing stage')
    capture=manifest['noise_capture'];latency=manifest['dsp_latency']['denoise']
    require(capture['selected_samples']==[11025,44100] and capture['source_media_span_seconds']==[1.75,2.5]
      and capture['guard_samples']==4410 and capture['preroll_samples_removed']==37485,'Capture preroll mapping differs')
    require(latency['status']=='measured_and_compensated' and latency['delay_samples']==1102
      and latency['remaining_bulk_delay_samples']==0 and latency['measured_impulse_offsets_samples']==[1102]*4,'Denoiser calibration differs')
    require(manifest['timeline']['audio_start_seconds']==1.5 and manifest['timeline']['no_time_stretch'] is True,'Native origin changed')
    source=f32_samples(candidate/'source.wav');denoised=f32_samples(candidate/'denoised.wav');residue=f32_samples(candidate/'residue.wav')
    error=max(abs(s-d-r) for s,d,r in zip(source,denoised,residue));require(error<=2**-22,'Residue arithmetic differs')
    return {'native':expected,'residue_max_abs_error':error,'first_boundary_error':max(abs(source[i]-denoised[i]-residue[i]) for i in range(2048)),
       'last_boundary_error':max(abs(source[i]-denoised[i]-residue[i]) for i in range(len(source)-2048,len(source))),
       'tail_source_rms':math.sqrt(sum(v*v for v in source[-2048:])/2048),
       'tail_denoised_rms':math.sqrt(sum(v*v for v in denoised[-2048:])/2048),'quality_accepted':False}


def delivery_audio_evidence(media,video,index):
    packets=media.run([media.executable('ffprobe'),'-v','error','-select_streams',str(index),
      '-show_packets','-show_entries','packet=pts,dts,duration,side_data_list','-of','json',str(video)],60)
    frames=media.run([media.executable('ffprobe'),'-v','error','-threads','2','-select_streams',str(index),
      '-show_frames','-show_entries','frame=best_effort_timestamp,nb_samples','-of','json',str(video)],60)
    packet_rows=json.loads(packets.stdout)['packets'];frame_rows=json.loads(frames.stdout)['frames']
    require(0<len(packet_rows)<=1000 and 0<len(frame_rows)<=1000,'Generated AAC timing table exceeded bound')
    require(all(isinstance(row.get('nb_samples'),int) and row['nb_samples']>0 for row in frame_rows),'AAC decoded sample extent unavailable')
    return {'packets':packet_rows,'frames':frame_rows,
      'raw_decoded_sample_count':sum(row['nb_samples'] for row in frame_rows),
      'scope':'AAC priming/padding/edit-list evidence; raw decoded count is not native master count'}


def audio_origin_gate(evidence,audio_time_base,picture_start):
    tick=Fraction(audio_time_base);rows=evidence['frames']
    require(rows and type(rows[0].get('best_effort_timestamp')) is int
      and type(rows[-1].get('best_effort_timestamp')) is int,'Decoded AAC timestamps unavailable')
    first=rows[0]['best_effort_timestamp']*tick
    last=rows[-1]['best_effort_timestamp']*tick+Fraction(rows[-1]['nb_samples'],44100)
    tolerance=Fraction(1024,44100)+Fraction(2,1000)
    offset=first-picture_start
    require(abs(offset-Fraction(1,2))<=tolerance,'Independent decoded AAC/video origin differs')
    return {'time_base':str(tick),'first_decoded_seconds':str(first),'last_raw_decoded_extent_seconds':str(last),
      'relative_decoded_audio_video_seconds':str(offset),'relative_offset_error_seconds':str(offset-Fraction(1,2)),
      'existing_AAC_tolerance_seconds':str(tolerance),'physical_sync_verified':False}


def execute(prereg_path,release_path):
    prereg,release=validate_release(prereg_path,release_path);app=load_application()
    deadline=app.Deadline(600);events=[];dest=Path(prereg['output']);dest.mkdir(parents=True,exist_ok=False)
    state={'schema_version':1,'status':'running','preregistration_sha256':digest(prereg_path),
      'release_sha256':digest(release_path),'harness_sha256':digest(__file__),'worker_sha256':PINS,
      'listening_accepted':False,'master_adopted':False,'physical_audio_video_sync_verified':False}
    started=time.monotonic();protected={};parent_hashes={}
    try:
        with bounded_environment(app,prereg,deadline,events):
            protected=current_protection(app,deadline)
            versions={name:app.run_owned([entry['path'],'-version'],deadline=deadline,timeout=30,events=events).stdout.splitlines()[0]
                      for name,entry in prereg['binaries'].items()}
            require(all('version 8.1.2 ' in version for version in versions.values()),'Pinned media version differs')
            filters=app.run_owned([prereg['binaries']['ffmpeg']['path'],'-hide_banner','-filters'],deadline=deadline,timeout=30,events=events).stdout
            encoders=app.run_owned([prereg['binaries']['ffmpeg']['path'],'-hide_banner','-encoders'],deadline=deadline,timeout=30,events=events).stdout
            for name in ('afftdn','asendcmd','concat','loudnorm','select'):
                require(re.search(r'\s'+name+r'\s',filters) is not None,'Required installed filter unavailable')
            for name in ('mpeg4','aac','pcm_s16le','pcm_s24le','pcm_f32le'):
                require(re.search(r'\s'+name+r'\s',encoders) is not None,'Required installed encoder unavailable')
            write_new(dest/'capabilities.json',{'versions':versions,'filters_sha256':hashlib.sha256(filters.encode()).hexdigest(),
              'encoders_sha256':hashlib.sha256(encoders.encode()).hexdigest(),'required_filters':['afftdn','asendcmd','concat','loudnorm','select'],
              'required_encoders':['mpeg4','aac','pcm_s16le','pcm_s24le','pcm_f32le']})
            reference=dest/'reference.wav'
            with wave.open(str(reference),'wb') as f:
                f.setnchannels(2);f.setsampwidth(2);f.setframerate(44100);f.writeframes(generated_samples().tobytes())
            original=dest/'original.mov';app.media.ffmpeg(mux_arguments(reference,original))
            source_hash=digest(original);probe=app.media.probe(original)
            picture=picture_gate(app.media,original,probe);write_new(dest/'source-picture.json',picture)
            baseline=app.media.clean(original,ROOT/'profiles/bypass.json');parent=Path(baseline['run_dir'])
            require(baseline['pcm']['sample_count']==352800 and baseline['pcm']['sample_rate']==44100
              and baseline['pcm']['channels']==2 and baseline['timeline']['audio_start_seconds']==1.5,'Baseline native facts differ')
            require(reference_f32(reference)==f32_samples(parent/'source.wav'),
                    'Original mux/decode changed generated native samples or channel order')
            review={'schema_version':1,'source_sha256':source_hash,'source_run_manifest_sha256':digest(parent/'manifest.json'),
              'source_pcm_sha256':digest(parent/'source.wav'),'start_seconds':.25,'end_seconds':1.,
              'time_axis':'decoded_source_audio_samples','selected_by':'root-generated-fixture-plan',
              'reviewed_by':'generated-signal-structure-review','review_status':'reviewed_candidate',
              'authorization_scope':'experimental_capture_render','authorization_reference':release['authorization_reference'],
              'music_status':'unknown','click_status':'unknown','ambient_music_status':'not_reported',
              'note':'Declared generator noise opportunity before tone/click onset; structural review only, no operator listening or authenticated identity.'}
            review_file=parent/'native-qualification-review.json';write_new(review_file,review)
            authored=app.capture.author(original,parent,review_file,capture_start_seconds=.25,capture_end_seconds=1.,**CONTROLS,timeout_seconds=min(60,int(deadline.remaining())))
            require(authored['status']=='authored_unrendered' and authored['dsp_performed'] is False,'Authoring did not return runnable unrendered profile')
            write_new(dest/'authoring-summary.json',authored)
            parent_hashes={str(file):digest(file) for file in parent.rglob('*') if file.is_file()}
            parent_hashes[str(original)]=source_hash;parent_hashes[str(reference)]=digest(reference)
            # Application owns its internal native clean/export commands. Its separate
            # bounded runner joins the receipt; this outer deadline remains active.
            applied=app.apply(original,authored['output_dir'],authored['receipt_sha256'],timeout_seconds=min(600,int(deadline.remaining())))
            resume_qualification_alarm(app,deadline,events)
            require(applied['status']=='rendered_unreviewed' and applied['listening_accepted'] is False
              and applied['master_adopted'] is False,'Application promoted acceptance state')
            write_new(dest/'application-summary.json',applied);candidate=Path(applied['run_dir'])
            state['candidate_run_dir']=str(candidate)
            manifest=read_json(candidate/'manifest.json');outcome=read_json(Path(applied['export']['outcome_path']))
            native=native_gate(app,manifest,candidate)
            require(f32_samples(parent/'source.wav')==f32_samples(candidate/'source.wav'),'New decode changed original native samples')
            require(digest(Path(applied['receipt_path']))==applied['receipt_sha256']
              and digest(candidate/'manifest.json')==applied['manifest_sha256']
              and digest(Path(applied['export']['outcome_path']))==applied['export']['outcome_sha256'],'Application returned stale artifact identities')
            video=Path(outcome['video']);export_probe=app.media.probe(video);frames=picture_frames(app.media,video,export_probe['video']['index'])
            tick=Fraction(export_probe['video']['time_base']);source_tick=Fraction(probe['video']['time_base'])
            require([int(r['best_effort_timestamp'])*tick for r in frames]==
                    [int(r['best_effort_timestamp'])*source_tick-1 for r in picture['source_frames']],'Export decoded VFR PTS changed')
            def frame_duration(row,clock):
                duration=int(row.get('duration',row.get('pkt_duration',0)))*clock
                require(duration>0,'Decoded picture duration unavailable');return duration
            require([frame_duration(r,tick) for r in frames]==
              [frame_duration(r,source_tick) for r in picture['source_frames']],'Export decoded picture durations changed')
            require(int(frames[-1]['best_effort_timestamp'])*tick+frame_duration(frames[-1],tick)==Fraction(17,2),'Export final picture extent changed')
            for key in ('source_hash_verified','video_frame_count_preserved','relative_audio_video_start_verified',
                        'dsp_latency_compensation_recorded','final_true_peak_within_target',
                        'video_packet_timeline_preserved','video_packet_payload_hashes_preserved'):
                require(outcome['verification'][key] is True,'Required exporter proof missing')
            require(outcome['verification']['physical_audio_video_sync_verified'] is False,'Physical sync claim promoted')
            require(outcome['verification']['video_packet_expected_translation_seconds']==-1.,'Picture clock translation differs')
            require(float(outcome['final_audio_loudness']['input_tp'])<=-1.5,'Final AAC peak exceeds target')
            require(export_probe['audio']['sample_rate']==44100 and export_probe['audio']['channels']==2,'Delivery audio native channels/rate differ')
            audio_evidence=delivery_audio_evidence(app.media,video,export_probe['audio']['index'])
            audio_evidence['decoded_origin_gate']=audio_origin_gate(audio_evidence,export_probe['audio']['time_base'],
                int(frames[0]['best_effort_timestamp'])*tick)
            write_new(dest/'delivery-audio-timing.json',audio_evidence)
            check_hashes(app,parent_hashes,deadline);check_hashes(app,protected,deadline);verify_pins()
            require(digest(__file__)==state['harness_sha256'],'Qualification controller changed during execution')
            require(digest(ROOT/'profiles/bypass.json')==prereg['bypass_profile_sha256'],'Approved bypass profile changed')
            require(digest(prereg_path)==state['preregistration_sha256'] and digest(release_path)==state['release_sha256'],'Release or preregistration changed')
            state.update(status='native_generated_qualification_passed',elapsed_seconds=time.monotonic()-started,
              versions=versions,facts=FACTS,native_checks=native,export_verification=outcome['verification'],
              final_audio_loudness=outcome['final_audio_loudness'],aac_headroom=outcome['aac_headroom'],
              protected_sha256=protected,parent_sha256=parent_hashes,owned_subprocesses=events,
              original_sha256=source_hash,application_receipt_sha256=applied['receipt_sha256'],
              manifest_sha256=digest(candidate/'manifest.json'),export_outcome_sha256=digest(Path(applied['export']['outcome_path'])),
              generated_reference_transport_exact=True,candidate_source_samples_equal_parent=True,
              media_generated=True,dsp_performed=True,actual_recording_processed=False)
        deadline.check()
        write_new(dest/'receipt.json',state)
        return state
    except BaseException as exc:
        state.update(status='qualification_failed_no_adoption',error=str(exc)[:2000],elapsed_seconds=time.monotonic()-started,
                     owned_subprocesses=events,protected_unchanged=None,parent_unchanged=None)
        recovered=(getattr(exc,'committed_candidate',None) or getattr(exc,'published_candidate',None)
                   or getattr(app,'LAST_COMMITTED',None))
        if recovered is not None:state['application_published_candidate_recovery']=recovered
        possible=None if recovered is not None else (getattr(exc,'possible_candidate',None)
                    or getattr(app,'LAST_POSSIBLE_CANDIDATE',None))
        if possible is not None:state['application_possible_candidate_recovery']=possible
        outcome=('committed_unreviewed' if recovered is not None else
                 'unknown_after_publish_attempt' if possible is not None else
                 getattr(exc,'publication_outcome',None))
        if outcome is not None:state['application_publication_outcome']=outcome
        for name in ('failure_receipt_path','failure_receipt_sha256','failure_receipt_error'):
            if getattr(exc,name,None) is not None:state['application_'+name]=getattr(exc,name)
        state['candidate_absence_asserted']=False
        for name,hashes in [('protected_unchanged',protected),('parent_unchanged',parent_hashes)]:
            if not hashes:continue
            if deadline.ends<=time.monotonic():continue
            try:
                check_hashes(app,hashes,deadline);state[name]=True
            except (OSError,ValueError):state[name]=None
        write_new(dest/'failure.json',state)
        raise RuntimeError(f'Native qualification failed; retained {dest}/failure.json') from exc


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='operation',required=True)
    p=sub.add_parser('preregister');p.add_argument('--trial-id',required=True);p.add_argument('--ffmpeg',required=True);p.add_argument('--ffprobe',required=True);p.add_argument('--output',required=True)
    e=sub.add_parser('execute');e.add_argument('--preregistration',required=True);e.add_argument('--release-receipt',required=True)
    args=parser.parse_args()
    try:
        if args.operation=='preregister':
            output=Path(args.output).absolute();require(output.parent==ROOT/'docs/agent-notes' and not output.exists()
              and not any(q.is_symlink() for q in (output,*output.parents)),'Fresh dated-note preregistration required')
            write_new(output,preregister(args.trial_id,args.ffmpeg,args.ffprobe));result={'status':'preregistered_not_executed','path':str(output),'sha256':digest(output)}
        else:
            r=execute(args.preregistration,args.release_receipt);result={key:r[key] for key in ('status','candidate_run_dir','elapsed_seconds','listening_accepted','master_adopted')}
        print(json.dumps(result,allow_nan=False));return 0
    except (OSError,ValueError,RuntimeError) as exc:
        print(json.dumps({'status':'error','error':str(exc)[:2000]},allow_nan=False));return 1


if __name__=='__main__':raise SystemExit(main())
