#!/usr/bin/env python3
"""Bounded, non-adopting MP4 sharing export; fixed controls and owned children."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import signal
import tempfile
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('_share_owned_application', ROOT / 'scripts/apply_capture_profile.py')
app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(app)
MAX_SOURCE_BYTES = 3 * 1024**3
MAX_OUTPUT_BYTES = 3 * 1024**3
MAX_RESULT_BYTES = 16 * 1024
MAX_RECEIPT_BYTES = 64 * 1024
MAX_PACKETS = 100000
MAX_PEAK_ATTENUATION_DB = 3.0
TARGET_TRUE_PEAK_DBTP = -1.5
LAST_STATE = None

class ShareError(ValueError):
    def __init__(self, message, code='validation_failed'):
        super().__init__(message)
        self.code = code

class Deadline:
    def __init__(self, seconds):
        self.ends = time.monotonic() + seconds
    def check(self):
        if time.monotonic() >= self.ends:
            raise ShareError('sharing export operation deadline exceeded', 'deadline_exceeded')
    def remaining(self):
        self.check()
        return max(.001, self.ends - time.monotonic())

def require(condition, message):
    if not condition:
        raise ShareError(message)

def bounded_int(value, low, high, name):
    require(type(value) is int and low <= value <= high, f'{name} must be an integer in {low}..{high}')
    return value

def settings(height=720, crf=27, audio_kbps=96, codec='h264', timeout_seconds=900):
    bounded_int(height,240,1080,'height')
    require(height % 2 == 0, 'height must be even')
    bounded_int(crf,18,32,'crf')
    bounded_int(audio_kbps,64,192,'audio_kbps')
    bounded_int(timeout_seconds,30,900,'timeout_seconds')
    require(type(codec) is str and codec in ('hevc','h264','copy'), 'unsupported codec')
    return dict(height=height, crf=crf, audio_kbps=audio_kbps, codec=codec,
                timeout_seconds=timeout_seconds, operation_seconds=timeout_seconds-10,
                cleanup_grace_seconds=5, reporting_headroom_seconds=5, threads=2,
                target_true_peak_dbtp=TARGET_TRUE_PEAK_DBTP, audio_attempts_max=2,
                attenuation_db_max=MAX_PEAK_ATTENUATION_DB)

def geometry(width, height, requested):
    bounded_int(requested,240,1080,'requested height')
    require(requested % 2 == 0, 'requested height must be even')
    bounded_int(width,2,8192,'source width')
    bounded_int(height,2,8192,'source height')
    target = min(height, requested)
    target -= target % 2
    out_width = max(2, int(width * target / height) // 2 * 2)
    return out_width, target

def local_path(value):
    require(isinstance(value,(str,Path)) and 1 <= len(str(value)) <= 4096, 'path must contain 1..4096 characters')
    try:
        p = Path(value).expanduser()
        require(not p.is_symlink(), 'symlink input/output is unsupported')
        return p.resolve()
    except (OSError,RuntimeError,ValueError) as exc:
        raise ShareError('invalid local path') from exc

def digest(path, deadline, limit=MAX_SOURCE_BYTES):
    require(path.is_file() and 0 < path.stat().st_size <= limit, 'file absent, empty or above byte limit')
    h=hashlib.sha256()
    with path.open('rb') as f:
        while True:
            deadline.check()
            b=f.read(1024*1024)
            if not b: break
            h.update(b)
    return h.hexdigest()

def encoded(value, limit):
    raw=(json.dumps(value,sort_keys=True,allow_nan=False,separators=(',',':'))+'\n').encode()
    require(len(raw)<=limit,'JSON exceeds byte limit')
    return raw

def write_json(path, value, limit=MAX_RECEIPT_BYTES):
    with path.open('xb') as f:
        f.write(encoded(value,limit)); f.flush(); os.fsync(f.fileno())

def executable(name):
    p=shutil.which(os.environ.get(name.upper(),name))
    require(p is not None, f'{name} executable unavailable')
    return p

def command(args):
    return [executable('ffmpeg'),'-hide_banner','-nostdin','-v','info','-threads','2',
            '-filter_threads','2','-filter_complex_threads','2','-n',*args]

def run(args, state):
    state['deadline'].check()
    index = state.setdefault('stage_count', 0) + 1
    state['stage_count'] = index
    logs = []
    def retained_buffer():
        handle = tempfile.NamedTemporaryFile(prefix=f'stage-{index:02d}-', suffix='.log',
                                            dir=state['staging'], delete=False)
        logs.append(Path(handle.name))
        return handle
    command_args = list(args)
    if Path(command_args[0]).name == 'ffmpeg':
        progress = state['staging'] / f'stage-{index:02d}-progress.txt'
        command_args[1:1] = ['-progress', str(progress), '-stats_period', '5']
    # Replace only the privately loaded module's tempfile reference. Its
    # qualified runner still bounds/polls/reaps; its two buffers now survive
    # success or failure for local inspection.
    prior = app.tempfile
    app.tempfile = SimpleNamespace(TemporaryFile=retained_buffer)
    try:
        return app.run_owned(command_args, deadline=state['deadline'],
                             timeout=state['deadline'].remaining(), events=state['events'])
    finally:
        app.tempfile = prior
        truncated=[]
        for file in logs:
            try:
                if file.stat().st_size>app.MAX_PROCESS_LOG_BYTES:
                    with file.open('r+b') as handle:
                        handle.seek(-app.MAX_PROCESS_LOG_BYTES,os.SEEK_END)
                        tail=handle.read(app.MAX_PROCESS_LOG_BYTES)
                        handle.seek(0);handle.write(tail);handle.truncate()
                    truncated.append(file.name)
            except OSError: pass  # The process error remains authoritative.
        state.setdefault('stage_logs', []).append(dict(stage=index,
            stdout=logs[0].name if logs else None, stderr=logs[1].name if len(logs)>1 else None,
            retained_tail_truncated=truncated))

def probe(path,state):
    r=run([executable('ffprobe'),'-v','error','-show_format','-show_streams','-of','json',str(path)],state)
    try: data=json.loads(r.stdout)
    except ValueError as exc: raise ShareError('invalid ffprobe JSON') from exc
    streams=data.get('streams',[])
    a=next((s for s in streams if s.get('codec_type')=='audio'),None)
    v=next((s for s in streams if s.get('codec_type')=='video' and not s.get('disposition',{}).get('attached_pic')),None)
    return dict(format=data.get('format',{}),audio=a,video=v)

def packets(path,stream,state):
    r=run([executable('ffprobe'),'-v','error','-select_streams',str(stream),'-show_packets',
           '-show_entries','packet=pts,dts,duration,flags,data_hash','-show_data_hash','sha256','-of','json',str(path)],state)
    p=json.loads(r.stdout).get('packets',[])
    require(0<len(p)<=MAX_PACKETS,'packet count unavailable or above limit')
    return p

DISCARD_FLAG='D'  # ffprobe AV_PKT_FLAG_DISCARD: decode-only, outside the edit list

def presentation_split(ps,name):
    """Split packets into presented and decode-only (edit-list discarded) rows.

    MOV/MP4 edit lists can start the presentation after a keyframe; the
    demuxer then flags the pre-roll packets 'D'. A decoder still consumes them
    but never presents them, so a re-encode correctly emits no frame for them.
    Absent flags (older probes, unit records) mean presented: strict default.
    """
    require(isinstance(ps,list) and all(isinstance(p,dict) for p in ps),f'{name} video packets must be arrays of records')
    require(all(p.get('flags') is None or (type(p['flags']) is str and len(p['flags'])<=16) for p in ps),f'{name} video packet flags must be short strings')
    shown=[p for p in ps if DISCARD_FLAG not in (p.get('flags') or '')]
    return shown,len(ps)-len(shown)

def count_refusal(kind,src_shown,src_discard,out_shown,out_discard):
    return ShareError(f'video packet count changed ({kind}): source {src_shown} presented + {src_discard} decode-only '
                      f'edit-list packets, output {out_shown} presented + {out_discard} decode-only. A picture may have been '
                      'dropped, duplicated or lost, or pre-roll was not flagged consistently, so the export was '
                      'refused to avoid a desynchronized file. '
                      'Edit-list pre-roll alone is accepted and is not this case; inspect the retained staging '
                      'media and source, and do not bypass this check.','validation_failed')

def verify_packets(source_packets, output_packets, source_timebase, output_timebase, copy=False):
    require(isinstance(source_packets,list) and isinstance(output_packets,list),'video packets must be arrays')
    require(0<len(source_packets)<=MAX_PACKETS and 0<len(output_packets)<=MAX_PACKETS,'video packet count unavailable or above limit')
    src_shown,src_discard=presentation_split(source_packets,'source')
    out_shown,out_discard=presentation_split(output_packets,'output')
    if copy:
        # Stream copy must keep every coded packet, including decode-only
        # pre-roll, with identical presentation/discard state.
        if len(source_packets)!=len(output_packets) or src_discard!=out_discard:
            raise count_refusal('coded copy',len(src_shown),src_discard,len(out_shown),out_discard)
        compare_source,compare_output=source_packets,output_packets
    else:
        # A decoder never presents discarded packets; compare presented frames.
        # The re-encode path never legitimately writes decode-only packets.
        if out_discard or not (0<len(src_shown)==len(out_shown)):
            raise count_refusal('presented re-encode',len(src_shown),src_discard,len(out_shown),out_discard)
        compare_source,compare_output=src_shown,out_shown
    require(type(source_timebase) in (str,Fraction) and type(output_timebase) in (str,Fraction),'video time bases must be rational strings or Fractions')
    try:
        st,ot=Fraction(source_timebase),Fraction(output_timebase)
        require(st>0 and ot>0,'nonpositive video time base')
        def rows(ps,tick):
            require(isinstance(ps,list) and all(isinstance(p,dict) and type(p.get('pts')) is int and type(p.get('duration')) is int and p['duration']>0 for p in ps),'video packet timestamps/durations must be positive-duration integer records')
            return sorted([(p['pts']*tick,p['duration']*tick,p) for p in ps],key=lambda r:r[0])
        a,b=rows(compare_source,st),rows(compare_output,ot)
    except (ValueError,KeyError,TypeError,ZeroDivisionError) as exc:
        raise ShareError('video packet timestamps/durations unavailable') from exc
    tol=max(st,ot)
    require(all(a[i][0]<a[i+1][0] for i in range(len(a)-1)),'source presentation timestamps not unique')
    require(all(b[i][0]<b[i+1][0] for i in range(len(b)-1)),'output presentation timestamps not unique')
    pts=max(abs(x[0]-y[0]) for x,y in zip(a,b))
    extent=abs((a[-1][0]+a[-1][1])-(b[-1][0]+b[-1][1]))
    require(pts<=tol and extent<=tol,'video presentation timestamp or tail extent changed')
    duration_delta=max(abs(x[1]-y[1]) for x,y in zip(a,b))
    payload=False
    if copy:
        require(all((DISCARD_FLAG in (x[2].get('flags') or ''))==(DISCARD_FLAG in (y[2].get('flags') or '')) for x,y in zip(a,b)),'copied video decode-only (edit-list) state changed')
        require(duration_delta<=tol,'copied video packet duration changed')
        require(all(x[2].get('data_hash') and x[2]['data_hash']==y[2].get('data_hash') for x,y in zip(a,b)), 'copied video payload changed')
        require(all(type(x.get('dts')) is int and type(y.get('dts')) is int and abs(x['dts']*st-y['dts']*ot)<=tol for x,y in zip(source_packets,output_packets)), 'copied video decode timestamp changed')
        payload=True
    shown_a=[r for r in a if DISCARD_FLAG not in (r[2].get('flags') or '')] if copy else a
    require(shown_a,'source has no presented video packets')
    return dict(method='sorted_packet_presentation_timestamps_rational',packet_count=len(a),
                comparison_scope='all_coded_packets' if copy else 'presented_packets_excluding_edit_list_discard',
                source_packet_count_total=len(source_packets),output_packet_count_total=len(output_packets),
                source_presented_packet_count=len(src_shown),output_presented_packet_count=len(out_shown),
                source_decode_only_packets=src_discard,output_decode_only_packets=out_discard,
                maximum_pts_delta_seconds=float(pts),maximum_pts_delta_rational=str(pts),
                tail_extent_delta_seconds=float(extent),tail_extent_delta_rational=str(extent),
                source_time_base=str(st),output_time_base=str(ot),
                intermediate_packet_duration_delta_seconds=float(duration_delta),
                intermediate_packet_duration_identity_required=copy,
                tolerance_seconds=float(tol),copied_payload_verified=payload,
                source_full_frame_decode_verified=False,physical_capture_sync_verified=False,
                source_start_seconds=float(shown_a[0][0]),source_end_seconds=float(shown_a[-1][0]+shown_a[-1][1]))

def audio_frames(path,stream,rate,state):
    r=run([executable('ffprobe'),'-v','error','-select_streams',str(stream),'-show_frames',
           '-show_entries','frame=best_effort_timestamp,nb_samples','-of','json',str(path)],state)
    f=json.loads(r.stdout).get('frames',[])
    require(0<len(f)<=MAX_PACKETS,'decoded audio frames absent or above limit')
    tick=Fraction(probe(path,state)['audio']['time_base'])
    try:
        rows=[(int(x['best_effort_timestamp'])*tick,int(x['nb_samples'])) for x in f]
    except (ValueError,KeyError,TypeError) as exc: raise ShareError('audio frame clock unavailable') from exc
    require(all(type(x.get('best_effort_timestamp')) is int and type(x.get('nb_samples')) is int for x in f),'audio frame clock/samples must be integers')
    require(all(n>0 for t,n in rows),'invalid audio frame samples')
    require(all(rows[i][0]<rows[i+1][0] for i in range(len(rows)-1)),'audio frame timestamps not monotonic')
    return dict(start_seconds=float(rows[0][0]),end_seconds=float(rows[-1][0]+Fraction(rows[-1][1],rate)),
                decoded_samples=sum(n for t,n in rows),frame_count=len(rows),time_base=str(tick))

def loudness(path,state):
    r=run(command(['-i',str(path),'-map','0:a:0','-af','loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json','-f','null','-']),state)
    try: data=app.media.loudnorm_json(r)
    except Exception as exc: raise ShareError('encoded AAC loudness measurement unavailable') from exc
    peak=float(data['input_tp'])
    require(math.isfinite(peak) or peak==-math.inf,'invalid measured true peak')
    return dict(integrated_lufs=None if data['input_i']=='-inf' else float(data['input_i']),
                true_peak_dbtp=None if peak==-math.inf else peak, silence=peak==-math.inf,
                method='ffmpeg_loudnorm_decoded_audio_measurement')

def verify_audio(source_metadata, output_metadata, before, after):
    a,b=source_metadata['audio'],output_metadata['audio']
    require(b and b.get('codec_name')=='aac','output audio is not AAC')
    require(int(a['sample_rate'])==int(b['sample_rate']) and int(a['channels'])==int(b['channels']),'native audio rate/channels changed')
    tol=1024/int(a['sample_rate'])+max(float(Fraction(before['time_base'])),float(Fraction(after['time_base'])))
    require(abs(before['start_seconds']-after['start_seconds'])<=tol and abs(before['end_seconds']-after['end_seconds'])<=tol,'audio origin or tail exceeds AAC frame allowance')
    require(abs(before['decoded_samples']-after['decoded_samples'])<=2048,'audio decoded sample extent changed beyond AAC padding allowance')
    return dict(method='decoded_audio_frame_timestamps_and_samples',source=before,output=after,
                sample_rate=int(a['sample_rate']),channels=int(a['channels']),
                priming_padding_allowance_seconds=tol,exact_pcm_sample_identity=False,audio_reencoded=True)

def publish_no_clobber(staged,output):
    os.link(staged,output)  # Same-filesystem staging; atomic create, never replaces.

def progress_summary(state):
    summaries=[]
    for file in sorted(state['staging'].glob('stage-*-progress.txt')):
        try:
            require(file.stat().st_size<=1024*1024,'progress log exceeds byte bound')
            text=file.read_text()[-8192:]
            values={}
            for line in text.splitlines():
                k,sep,v=line.partition('=')
                if sep and k in ('frame','fps','out_time_us','out_time','speed','progress'):
                    values[k]=v[:100]
            summaries.append(dict(path=file.name,last_report=values))
        except (OSError,ValueError): summaries.append(dict(path=file.name,status='unavailable_or_above_bound'))
    return summaries

def failure(state,exc):
    signal.setitimer(signal.ITIMER_REAL,0) if app.CLI_ALARM_HANDLER is not None else None
    published=state.get('published',False)
    # Link may have committed before a reporting/observation exception.
    possible=None
    if state.get('prepared') and not published and state.get('publish_attempted'):
        try:
            current=state['output'].stat()
            published=(current.st_dev,current.st_ino)==state['prepared_identity']
            if not published:
                try:
                    staged=state['final_stage'].stat()
                    if (staged.st_dev,staged.st_ino)!=state['prepared_identity']: possible=state['prepared']
                except OSError: possible=state['prepared']
        except FileNotFoundError:
            try:
                staged=state['final_stage'].stat()
                if (staged.st_dev,staged.st_ino)!=state['prepared_identity']:
                    possible=state['prepared']
            except OSError: possible=state['prepared']
        except OSError: possible=state['prepared']
    state['published']=published
    recovery=state.get('prepared') if published else None
    status='exported_unreviewed_reporting_interrupted' if published else ('publication_outcome_unknown' if possible else 'failed_no_export_published')
    receipt=dict(schema_version=1,status=status,error=str(exc)[:2000],code=getattr(exc,'code','export_failed'),
        output=recovery,possible_output=possible,staging_dir=str(state['staging']),
        process_events=state['events'],stage_logs=state.get('stage_logs',[]),stage_progress=progress_summary(state),master_adopted=False,listening_accepted=False)
    p=state['staging']/'failure-receipt.json'
    try: write_json(p,receipt); receipt_hash=hashlib.sha256(p.read_bytes()).hexdigest()
    except (OSError,ValueError): p=None;receipt_hash=None
    return dict(status=status,error=str(exc)[:1000],code=getattr(exc,'code','export_failed'),
        output=recovery,possible_output=possible,staging_dir=str(state['staging']),
        failure_receipt_path=str(p) if p else None,failure_receipt_sha256=receipt_hash,stage_progress=progress_summary(state),
        master_adopted=False,listening_accepted=False)

def share_export(source,output,*,height=720,crf=27,audio_kbps=96,codec='h264',timeout_seconds=900):
    global LAST_STATE
    LAST_STATE=None
    cfg=settings(height,crf,audio_kbps,codec,timeout_seconds)
    src,out=local_path(source),local_path(output)
    sidecar=out.with_name(out.name+'.receipt.json')
    require(src.is_file(),'source must be a regular local file')
    require(out.suffix.lower()=='.mp4' and out.parent.is_dir(),'output must be .mp4 in an existing directory')
    require(src!=out and not out.exists() and not sidecar.exists(),'output or receipt exists or aliases source')
    require(0<src.stat().st_size<=MAX_SOURCE_BYTES,'source exceeds 3GiB or is empty')
    stage=Path(tempfile.mkdtemp(prefix='.share-export-',dir=out.parent))
    state=dict(source=src,output=out,receipt=sidecar,staging=stage,events=[],deadline=Deadline(cfg['operation_seconds']),published=False)
    LAST_STATE=state
    try:
        original=digest(src,state['deadline'])
        meta=probe(src,state)
        a,v=meta['audio'],meta['video']
        require(a is not None and v is not None,'source needs audio and video')
        duration=float(meta['format'].get('duration',0))
        require(math.isfinite(duration) and 0<duration<=300,'source duration must be finite in (0,300] seconds')
        rate,channels=int(a.get('sample_rate',0)),int(a.get('channels',0))
        require(8000<=rate<=192000 and 1<=channels<=8,'unsupported native audio rate/channel count')
        width,target_height=geometry(int(v['width']),int(v['height']),height)
        require(v.get('sample_aspect_ratio','1:1') in ('1:1','N/A'),'non-square pixels unsupported')
        require(not v.get('side_data_list'),'rotated or side-data video requires explicit upstream export')
        require(codec!='copy' or (int(v['height'])<=height and v.get('codec_name') in ('h264','hevc')),'copy requires H.264/HEVC video already within height bound')
        before_packets=packets(src,v['index'],state)
        before_audio=audio_frames(src,a['index'],rate,state)
        video=stage/'video.mp4'
        args=['-copyts','-i',str(src),'-map',f"0:{v['index']}",'-an','-map_metadata','-1']
        if codec=='copy': args+=['-c:v','copy','-copytb','1']
        else:
            args+=['-vf',f'scale={width}:{target_height}:flags=lanczos','-c:v','libx265' if codec=='hevc' else 'libx264',
                   '-preset','veryfast','-crf',str(crf),'-pix_fmt','yuv420p','-threads:v','2',
                   '-fps_mode','passthrough','-enc_time_base:v','demux']
            if codec=='hevc': args+=['-x265-params','pools=none:frame-threads=2:log-level=error']
        if codec=='hevc' or (codec=='copy' and v['codec_name']=='hevc'): args+=['-tag:v','hvc1']
        args+=['-avoid_negative_ts','disabled','-movie_timescale','1000000','-movflags','+faststart',str(video)]
        run(command(args),state)
        gain=0.0; attempts=[]; audio=None
        for index in range(2):
            audio=stage/f'audio-{index+1}.m4a'
            args=['-copyts','-i',str(src),'-map',f"0:{a['index']}",'-vn','-map_metadata','-1',
                  '-c:a','aac','-b:a',f'{audio_kbps}k','-ar',str(rate),'-ac',str(channels)]
            if gain: args+=['-af',f'volume={gain:.6f}dB']
            args+=['-avoid_negative_ts','disabled','-movie_timescale','1000000',str(audio)]
            run(command(args),state)
            measured=loudness(audio,state)
            attempts.append(dict(attempt=index+1,gain_db=gain,measurement=measured,path=audio.name))
            if measured['silence'] or measured['true_peak_dbtp']<=TARGET_TRUE_PEAK_DBTP: break
            gain-=measured['true_peak_dbtp']-TARGET_TRUE_PEAK_DBTP+.10
            require(index==0 and gain>=-MAX_PEAK_ATTENUATION_DB,'AAC peak limit cannot be met within two attempts/3dB attenuation')
        final=stage/'export.mp4'
        run(command(['-copyts','-i',str(video),'-i',str(audio),'-map','0:v:0','-map','1:a:0',
                     '-map_metadata','-1','-c','copy','-avoid_negative_ts','disabled',
                     '-movie_timescale','1000000','-movflags','+faststart',str(final)]),state)
        final_meta=probe(final,state)
        fv=final_meta['video']
        require(fv and int(fv['height'])<=height,'export height above bound')
        if codec!='copy':
            require((int(fv['width']),int(fv['height']))==(width,target_height) and fv.get('pix_fmt')=='yuv420p','export dimensions/pixel format changed')
            require(fv.get('codec_name')==codec,'export codec changed')
        video_proof=verify_packets(before_packets,packets(final,fv['index'],state),v['time_base'],fv['time_base'],codec=='copy')
        after_audio=audio_frames(final,final_meta['audio']['index'],rate,state)
        audio_proof=verify_audio(meta,final_meta,before_audio,after_audio)
        # Decode the bounded delivery output, not the high-resolution original.
        decoded=run(command(['-xerror','-err_detect','explode','-i',str(final),'-map','0:v:0','-map','0:a:0','-f','null','-']),state)
        require(not any(x in decoded.stderr.lower() for x in ('error while decoding','corrupt decoded frame')),'delivery decode error')
        final_measure=loudness(final,state)
        require(final_measure['silence'] or final_measure['true_peak_dbtp']<=TARGET_TRUE_PEAK_DBTP,'final mux AAC peak exceeds target')
        require(digest(src,state['deadline'])==original,'source changed during export')
        output_hash=digest(final,state['deadline'],MAX_OUTPUT_BYTES)
        size=final.stat().st_size
        result=dict(schema_version=1,status='exported_unreviewed',source=dict(path=str(src),sha256=original,bytes=src.stat().st_size),
                    output=dict(path=str(out),sha256=output_hash,bytes=size,receipt_path=str(sidecar)),
                    byte_reduction_fraction=1-size/src.stat().st_size,settings=cfg,
                    codecs=dict(video=fv['codec_name'],audio='aac'),dimensions=dict(width=int(fv['width']),height=int(fv['height'])),
                    video_encode_count=0 if codec=='copy' else 1,audio_attempts=attempts,
                    video_proof=video_proof,audio_proof=audio_proof,loudness=final_measure,
                    output_decode_errors_checked=True,master_adopted=False,listening_accepted=False,
                    uncertainty=['Lossy video/AAC sharing export; original/master untouched.','Packet timestamps do not prove source decoded-frame identity or physical capture sync.','AAC priming/padding permits up to one AAC frame plus mux tick at each endpoint.','File-size reduction depends on the input; CRF does not guarantee a byte limit.'])
        encoded(result,MAX_RESULT_BYTES)
        receipt=dict(result,process_events=state['events'],stage_logs=state.get('stage_logs',[]),stage_progress=progress_summary(state),staging_dir=str(stage),
                     producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                     runner_sha256=hashlib.sha256((ROOT/'scripts/apply_capture_profile.py').read_bytes()).hexdigest())
        staged_receipt=stage/'receipt.json';write_json(staged_receipt,receipt)
        result['output']['receipt_sha256']=hashlib.sha256(staged_receipt.read_bytes()).hexdigest()
        encoded(result,MAX_RESULT_BYTES)
        state['prepared']=dict(result['output']);state['final_stage']=final
        identity=final.stat();state['prepared_identity']=(identity.st_dev,identity.st_ino)
        state['deadline'].check()
        state['publish_attempted']=True
        publish_no_clobber(final,out)
        state['published']=True
        if app.CLI_ALARM_HANDLER is not None: signal.setitimer(signal.ITIMER_REAL,0)
        publish_no_clobber(staged_receipt,sidecar)
        return result
    except BaseException as exc:
        exc.share_failure=failure(state,exc)
        raise

def bounded_diagnostic(diagnostic):
    # The complete recovery details stay in the durable receipt. Project only
    # redundant fields if a pathological long local path exceeds transport cap.
    omitted=[]
    try:
        encoded(diagnostic,MAX_RESULT_BYTES)
        return diagnostic
    except ShareError:
        diagnostic=dict(diagnostic)
    if 'stage_progress' in diagnostic:
        diagnostic['stage_progress']=[];omitted.append('stage_progress')
    for field in ('output','possible_output'):
        if diagnostic.get(field):
            projected=dict(diagnostic[field])
            if projected.get('receipt_path'):
                projected['receipt_name']=Path(projected.pop('receipt_path')).name
                omitted.append(field+'.receipt_path')
            diagnostic[field]=projected
    diagnostic['diagnostic_fields_omitted']=omitted
    try:
        encoded(diagnostic,MAX_RESULT_BYTES)
        return diagnostic
    except ShareError:
        diagnostic.pop('staging_dir',None)
        omitted.append('staging_dir')
        diagnostic['error']=diagnostic.get('error','')[:200]
        encoded(diagnostic,MAX_RESULT_BYTES)
        return diagnostic

def main(argv=None):
    global LAST_STATE
    LAST_STATE=None
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source');p.add_argument('output')
    p.add_argument('--height',type=int,default=720);p.add_argument('--crf',type=int,default=27)
    p.add_argument('--audio-kbps',type=int,default=96);p.add_argument('--codec',choices=['hevc','h264','copy'],default='h264')
    p.add_argument('--timeout-seconds',type=int,default=900)
    p.add_argument('--tool-envelope',action='store_true',help='return domain-status JSON with exit zero for the typed local hook')
    args=p.parse_args(argv)
    prior_handler=signal.getsignal(signal.SIGALRM);prior_timer=signal.getitimer(signal.ITIMER_REAL)
    prior_app_handler=app.CLI_ALARM_HANDLER
    try:
        cfg=settings(args.height,args.crf,args.audio_kbps,args.codec,args.timeout_seconds)
        require(prior_timer[0]==0,'CLI cannot replace an existing caller timer')
        def expired(signum,frame): raise ShareError('sharing export operation deadline exceeded','deadline_exceeded')
        signal.signal(signal.SIGALRM,expired);app.CLI_ALARM_HANDLER=expired
        signal.setitimer(signal.ITIMER_REAL,cfg['operation_seconds'])
        result=share_export(args.source,args.output,height=args.height,crf=args.crf,audio_kbps=args.audio_kbps,codec=args.codec,timeout_seconds=args.timeout_seconds)
        signal.setitimer(signal.ITIMER_REAL,0)
        print(encoded(result,MAX_RESULT_BYTES).decode(),end='')
        return 0
    except Exception as exc:
        signal.setitimer(signal.ITIMER_REAL,0)
        diagnostic=getattr(exc,'share_failure',None)
        if diagnostic is None and LAST_STATE is not None: diagnostic=failure(LAST_STATE,exc)
        if diagnostic is None: diagnostic=dict(status='rejected',error=str(exc)[:1000],code=getattr(exc,'code','validation_failed'))
        diagnostic=bounded_diagnostic(diagnostic)
        print(encoded(diagnostic,MAX_RESULT_BYTES).decode(),end='')
        print(str(exc)[:1000],file=__import__('sys').stderr)
        return 0 if args.tool_envelope else 2
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,prior_handler)
        app.CLI_ALARM_HANDLER=prior_app_handler
        if prior_timer[0]: signal.setitimer(signal.ITIMER_REAL,*prior_timer)

if __name__=='__main__': raise SystemExit(main())
