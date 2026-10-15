#!/usr/bin/env python3
"""Copy qualified compact review picture and accepted FULLER AAC into a new MOV."""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
COMPACT=ROOT/'artifacts/runs/20261006T034521Z-a0def0c43eac/reference-marked-preview-compact'
FULLER=ROOT/'artifacts/runs/20261006T041633Z-990aa1bd6737'
SOURCE_SHA='a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6'
APP_SHA='790ac58f1924db2607087c6ab1cdae5d813ba24eda610af1f396d77e93d06584'
MEDIA_SHA='91443154251888c9e74670790766b289a2618f85f3be806d60ca26882faa9d94'
FULLER_MANIFEST_SHA='61c9b3930c36d050818901138eb1820d5dc940e3603d38f019bde793da750a5f'
FULLER_VIDEO_SHA='91b2f436abebf9dd8403791b18dd9b51410e25d25648c71febc27ed269a04a82'
ASSESSMENT_SHA='834e9420ef10310c2e1df42f243af01f645de06a498e544f06ec1593cdd07028'
ANALYSIS_INPUT_SHA='cb8a3fa559424810f206c94191a149156423770bbf91a13724a2ba28a44e879e'
MAX_JSON=4*1024*1024
BINARY='/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/'

def require(condition,message):
    if not condition:raise ValueError(message)
def sha(file):
    h=hashlib.sha256()
    with Path(file).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def read(file):
    p=Path(file);require(p.is_file() and not any(q.is_symlink() for q in (p,*p.parents)) and p.stat().st_size<=MAX_JSON,'Bounded nonsymlink JSON required')
    def pairs(rows):
        out={}
        for k,v in rows:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    def reject(value):raise ValueError('Nonfinite JSON')
    value=json.loads(p.read_bytes(),object_pairs_hook=pairs,parse_constant=reject)
    json.dumps(value,allow_nan=False);return value
def write(file,value):
    raw=json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n';require(len(raw.encode())<=MAX_JSON,'Receipt exceeds bound')
    with Path(file).open('x') as f:f.write(raw)
def verify(rows):
    for file,expected in rows.items():
        require(Path(file).is_file() and not any(p.is_symlink() for p in (Path(file),*Path(file).parents)) and sha(file)==expected,'Input changed: '+str(file))

def branch_gate(compact,manifest,export):
    require(compact['status']=='marked_review_preview_verified_unreviewed','Compact parent is not verified terminal')
    require(compact['source_sha256']==manifest['source']['sha256']==export['source_sha256']==SOURCE_SHA,'Common original source differs')
    require(compact['source_container_start_seconds']==0 and manifest['timeline']['audio_start_seconds']==0
            and manifest['timeline']['format_start_seconds']==0 and manifest['timeline']['no_time_stretch'] is True,'Source-zero/no-stretch mapping missing')
    require({k:manifest['pcm'][k] for k in ('sample_rate','channels','sample_count')}=={'sample_rate':44100,'channels':1,'sample_count':6657385},'Accepted parent native facts differ')
    require(compact['marker_mode']=='arrangement_reference_review','Expected compact arrangement branch')
    binding=compact['arrangement_marker_bindings']
    require(binding['analyzed_input_sha256']==ANALYSIS_INPUT_SHA and binding['assessment']['sha256']==ASSESSMENT_SHA,'Marker analysis/assessment branch differs')
    proof=compact['verification']
    for key in ('decoded_video_frame_pts_preserved','decoded_video_last_extent_preserved','picture_geometry_preserved'):
        require(proof[key] is True,'Compact frame-clock proof missing')
    require(proof['decoded_video_frame_count']==3621 and proof['decoded_video_first_pts_seconds']==0
            and Fraction(str(proof['decoded_video_last_extent_seconds']))==Fraction('150.885'),'Compact picture extent differs')
    ev=export['verification']
    for key in ('source_hash_verified','video_frame_count_preserved','relative_audio_video_start_verified','dsp_latency_compensation_recorded','final_true_peak_within_target'):
        require(ev[key] is True,'Accepted parent export proof missing')
    require(ev['video_packet_expected_translation_seconds']==0 and ev['physical_audio_video_sync_verified'] is False,'Accepted branch clock/scope differs')

def exact_packets(before,after,before_tick,after_tick,*,audio=False):
    require(len(before)==len(after) and len(before)>0,'Copied packet count differs')
    bt,at=Fraction(before_tick),Fraction(after_tick)
    for old,new in zip(before,after):
        require(old.get('data_hash') is not None and old['data_hash']==new.get('data_hash'),'Copied packet payload differs')
        if audio:require(old.get('side_data_list')==new.get('side_data_list'),'AAC priming/padding differs')
        for key in ('pts','dts','duration'):
            require(key in old and key in new and int(old[key])*bt==int(new[key])*at,'Copied rational packet '+key+' differs')

def fresh_output(value):
    p=Path(value).absolute();base=ROOT/'artifacts/experiments'
    require(p.parent==base and p.name.startswith('accepted-fuller-compact-') and not p.exists()
            and not any(q.is_symlink() for q in (p,*p.parents)),'Fresh fixed experiment child required')
    return p

def assemble(compact_sha,output):
    require(sha(ROOT/'scripts/apply_capture_profile.py')==APP_SHA and sha(ROOT/'scripts/media.py')==MEDIA_SHA,'Frozen runner/media source differs')
    require(sha(COMPACT/'outcome.json')==compact_sha,'Compact receipt differs from owner qualification')
    require(sha(FULLER/'manifest.json')==FULLER_MANIFEST_SHA,'Accepted manifest changed')
    compact=read(COMPACT/'outcome.json');manifest=read(FULLER/'manifest.json');export=read(FULLER/'export/outcome.json');branch_gate(compact,manifest,export)
    picture=COMPACT/'marked-video.mov';audio=FULLER/'export/cleaned-video.mov'
    require(export['video']==str(audio) and sha(audio)==export['output_sha256']['cleaned-video.mov']==FULLER_VIDEO_SHA,'Accepted audio delivery identity differs')
    protected=dict(compact['input_sha256'])
    protected.update({str(COMPACT/'outcome.json'):compact_sha,str(picture):compact['output_sha256']['marked-video.mov'],
      str(COMPACT/'selection.json'):compact['output_sha256']['selection.json'],str(COMPACT/'callouts.ass'):compact['output_sha256']['callouts.ass']})
    for name in ('manifest.json','application-receipt.json','applied-profile.json','export/outcome.json','export/cleaned-video.mov','cleaned.wav'):
        p=FULLER/name;protected[str(p)]=sha(p)
    latest=ROOT/'artifacts/latest.json'
    if latest.exists():protected[str(latest)]=sha(latest)
    verify(protected);output=fresh_output(output)
    spec=importlib.util.spec_from_file_location('assembly_owned_runner',ROOT/'scripts/apply_capture_profile.py');app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
    deadline=app.Deadline(600);events=[];started=time.monotonic();output.mkdir(parents=True,mode=0o700)
    state={'schema_version':1,'actor':'/root/media_latency','created_utc':datetime.now(timezone.utc).isoformat(),'status':'running',
      'authority':'Root explicit accepted FULLER+compact picture composition; R-HOOK-CONVERGENCE-20261004/R-N11/R-N13',
      'controller_sha256':sha(__file__),'runner_sha256':APP_SHA,'media_sha256':MEDIA_SHA,'timeout_seconds':600,'threads':2,
      'source_sha256':SOURCE_SHA,'input_sha256':protected,'picture_marker_branch':{'run_dir':str(COMPACT.parent),'compact_outcome_sha256':compact_sha,'selection_sha256':compact['output_sha256']['selection.json'],'arrangement_bindings':compact['arrangement_marker_bindings']},
      'accepted_audio_branch':{'run_dir':str(FULLER),'export_sha256':sha(FULLER/'export/outcome.json'),'video_sha256':FULLER_VIDEO_SHA,'listening_accepted':True,'acceptance_quote':'sounds excellent!  great work!','acceptance_authority':'Root reports explicit operator acceptance in active session'},
      'new_audio_DSP':False,'picture_reencoded_by_assembly':False,'markers_are_analysis_of_FULLER':False,'master_adopted':False,'latest_promoted':False,'physical_audio_video_sync_verified':False}
    write(output/'start.json',state)
    def run(command,timeout=120):
        # Existing metadata helpers do not always state decoder threads.
        if Path(command[0]).name=='ffprobe' and '-threads' not in command:
            command=[command[0],'-threads','2',*command[1:]]
        if Path(command[0]).name=='ffprobe' and '-show_streams' in command and '-show_data_hash' not in command:
            command=[*command[:-1],'-show_data_hash','sha256',command[-1]]
        return app.run_owned(command,deadline=deadline,timeout=min(timeout,deadline.remaining()),events=events)
    def packets(file,index,audio=False):
        fields='packet=pts,dts,duration,data_hash'
        if audio:fields+=',side_data_list:packet_side_data=side_data_type,skip_samples,discard_padding'
        rows=json.loads(run([BINARY+'ffprobe','-v','error','-threads','2','-select_streams',str(index),'-show_packets','-show_entries',fields,'-show_data_hash','sha256','-of','json',str(file)]).stdout)['packets']
        require(0<len(rows)<=60000,'Packet table exceeds bound');return rows
    def pcmhash(file):
        value=run([BINARY+'ffmpeg','-hide_banner','-nostdin','-loglevel','error','-threads','2','-i',str(file),'-map','0:a:0','-vn','-c:a','pcm_f32le','-f','hash','-hash','sha256','-']).stdout.strip()
        require(value.startswith('SHA256=') and len(value)==71,'Decoded AAC identity missing');return value
    prior_runner=app.media.run;prior_ffmpeg=os.environ.get('FFMPEG');prior_ffprobe=os.environ.get('FFPROBE')
    app.media.run=lambda command,timeout=600:run(command,timeout)
    os.environ.update(FFMPEG=BINARY+'ffmpeg',FFPROBE=BINARY+'ffprobe')
    old_handler=signal.getsignal(signal.SIGALRM);require(signal.getitimer(signal.ITIMER_REAL)==(0.,0.),'Another alarm is active')
    def expired(signum,frame):raise app.ApplyError('Assembly600s deadline exceeded','deadline_exceeded')
    signal.signal(signal.SIGALRM,expired);app.CLI_ALARM_HANDLER=expired;signal.setitimer(signal.ITIMER_REAL,600)
    try:
        before_picture=app.media.probe(picture);before_audio=app.media.probe(audio)
        pv,pa=before_picture['video'],before_audio['audio']
        require(pv['codec_type']=='video' and pa['codec_name']=='aac' and pa['sample_rate']==44100 and pa['channels']==1,'Parent stream format differs')
        require(Fraction(str(pv['start_time']))==0 and Fraction(str(pa['start_time']))==0,'Parent stream origins differ')
        picture_end=Fraction(str(compact['verification']['decoded_video_last_extent_seconds']))
        accepted_audio_end=Fraction(str(pa['duration']))
        require(accepted_audio_end>=picture_end,'Accepted audio does not cover complete compact picture clock')
        tick=Fraction(pv['time_base']);require(tick.numerator==1,'Reciprocal picture clock required')
        vp=app.media.video_packets(picture,pv['index']);ap=packets(audio,pa['index'],True);parent_pcm=pcmhash(audio)
        write(output/'parent-video-packets.json',{'time_base':pv['time_base'],'packets':vp});write(output/'parent-audio-packets.json',{'time_base':pa['time_base'],'packets':ap})
        destination=output/'accepted-marked-video.mov'
        command=[BINARY+'ffmpeg','-hide_banner','-nostdin','-loglevel','warning','-threads','2','-n','-copyts','-i',str(picture),'-i',str(audio),'-map','0:v:0','-map','1:a:0','-map_metadata','0','-map_chapters','-1','-c:v','copy','-c:a','copy','-video_track_timescale',str(tick.denominator),'-avoid_negative_ts','disabled','-movflags','+faststart',str(destination)]
        run(command,120);after=app.media.probe(destination);nv,na=after['video'],after['audio']
        ov=app.media.video_packets(destination,nv['index']);oa=packets(destination,na['index'],True)
        video_proof=app.media.compare_video_packets(vp,ov,pv['time_base'],nv['time_base'],Fraction(0));exact_packets(vp,ov,pv['time_base'],nv['time_base']);exact_packets(ap,oa,pa['time_base'],na['time_base'],audio=True)
        require(pcmhash(destination)==parent_pcm,'Accepted decoded AAC PCM changed')
        for key in ('width','height','sample_aspect_ratio','codec_name','extradata_size','profile','level','pix_fmt',
                    'field_order','color_range','color_space','color_transfer','color_primaries','chroma_location','side_data_list'):
            require(pv.get(key)==nv.get(key),'Picture format differs: '+key)
        for key in ('sample_rate','channels','codec_name','extradata_size'):require(pa.get(key)==na.get(key),'AAC format differs')
        require(pv.get('extradata_hash') is not None and pv['extradata_hash']==nv.get('extradata_hash'),'Picture decoder configuration differs')
        require(pa.get('extradata_hash') is not None and pa['extradata_hash']==na.get('extradata_hash'),'AAC decoder configuration differs')
        require(Fraction(str(nv['start_time']))==0 and Fraction(str(na['start_time']))==0,'Composed origins differ')
        require(Fraction(str(na['duration']))==accepted_audio_end,'Accepted AAC header extent changed')
        verify(protected);require(sha(__file__)==state['controller_sha256'],'Assembly source changed');deadline.check()
        write(output/'output-video-packets.json',{'time_base':nv['time_base'],'packets':ov});write(output/'output-audio-packets.json',{'time_base':na['time_base'],'packets':oa})
        state.update(status='accepted_audio_compact_marked_composition_verified',elapsed_seconds=time.monotonic()-started,
          output=str(destination),output_sha256=sha(destination),output_bytes=destination.stat().st_size,input_hashes_preserved=True,
          command=command,owned_subprocesses=events,video_packet_verification=video_proof,
          exact_video_packet_payload_and_rational_clock_identity=True,exact_AAC_packet_payload_clock_padding_identity=True,
          picture_and_AAC_decoder_configuration_identity=True,
          accepted_decoded_AAC_pcm_sha256=parent_pcm,decoded_AAC_identity_preserved=True,
          clock_overlap={'decoded_picture_start_seconds':'0','decoded_picture_end_seconds':str(picture_end),
             'accepted_AAC_stream_start_seconds':'0','accepted_AAC_stream_end_seconds':str(accepted_audio_end),
             'complete_picture_clock_covered':True,'native_PCM_extent_samples':6657385,
             'AAC_padding_is_separate_from_native_PCM_extent':True},
          inherited_picture_frame_proof=compact['verification'],frame_proof_scope='Transitive: parent verified decoded VFR frame table + exact coded packet/clock/geometry identity; no new HD frame decode',
          inherited_audio_loudness=export['final_audio_loudness'],audio_loudness_scope='Accepted parent measurement transferred by exact AAC packet and decoded PCM identity; no fresh normalization',
          composed_probe=after,composite_visual_review_performed=False)
        write(output/'receipt.json',state);return state
    except BaseException as exc:
        state.update(status='assembly_failed_preserving_parents',error=str(exc)[:2000],owned_subprocesses=events,elapsed_seconds=time.monotonic()-started,input_hashes_preserved=None)
        try:verify(protected);state['input_hashes_preserved']=True
        except (OSError,ValueError):pass
        write(output/'failure.json',state);raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_handler);app.CLI_ALARM_HANDLER=None;app.media.run=prior_runner
        for key,value in (('FFMPEG',prior_ffmpeg),('FFPROBE',prior_ffprobe)):
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compact-outcome-sha256',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    try:
        r=assemble(a.compact_outcome_sha256,a.output);print(json.dumps({k:r[k] for k in ('status','output','output_sha256','elapsed_seconds')}));return 0
    except (OSError,ValueError,RuntimeError) as exc:print(json.dumps({'status':'error','error':str(exc)[:2000]}));return 1

if __name__=='__main__':raise SystemExit(main())
