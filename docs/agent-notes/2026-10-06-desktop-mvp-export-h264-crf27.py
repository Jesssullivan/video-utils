#!/usr/bin/env python3
"""Bounded, non-overwriting optimized Desktop derivative of accepted composition."""
from datetime import datetime,timezone
from fractions import Fraction
import hashlib,importlib.util,json,os,signal,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
INPUT=ROOT/'artifacts/experiments/accepted-fuller-compact-20261006T0441/accepted-marked-video.mov'
INPUT_SHA='4538573ae6dd487874613efe3e30fe0e14ccda8e00a80b148ad2d4ce7f13e7e2'
RUNNER_SHA='790ac58f1924db2607087c6ab1cdae5d813ba24eda610af1f396d77e93d06584'
ASSEMBLY_SHA='095fa1e694fb97cc9a53f1d12e04c86cac7fbd637a7d574c6295102ecd44a533'
STAGE=ROOT/'artifacts/experiments/desktop-mvp-h264-crf27-20261006T0513'
DESKTOP=Path('/Users/jess/Desktop/video_util_mvp_demo_1.mp4')
BIN='/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/'
def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def save(p,r):
 data=json.dumps(r,sort_keys=True,indent=2,allow_nan=False)+'\n';require(len(data.encode())<=4*1024*1024,'Receipt exceeds 4MiB')
 with p.open('x') as f:f.write(data)
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def frame_gate(expected,frames,tick,tolerance):
 require(len(expected)==len(frames)==3621,'Decoded frame count changed')
 pts=[int(f['best_effort_timestamp'])*tick for f in frames]
 require(all(a<b for a,b in zip(pts,pts[1:])),'Decoded frame clock not strictly increasing')
 delta=max(abs(a-b) for a,b in zip(expected,pts));require(delta<=tolerance,'Decoded VFR timestamp changed')
 tail=int(frames[-1].get('duration',0))*tick;require(tail>0,'Final decoded frame duration unavailable')
 end=pts[-1]+tail;require(abs(end-Fraction('150.885'))<=tolerance,'Final picture extent changed')
 return {'frame_count':len(pts),'max_timestamp_delta_seconds':str(delta),'first_pts_seconds':str(pts[0]),'last_extent_seconds':str(end),'mux_clock_tolerance_seconds':str(tolerance),'variable_intervals_preserved':len(set(b-a for a,b in zip(pts,pts[1:])))>1}
def main():
 require(sha(INPUT)==INPUT_SHA,'Accepted input changed')
 require(sha(ROOT/'scripts/apply_capture_profile.py')==RUNNER_SHA,'Owned runner changed')
 ap=ROOT/'docs/agent-notes/2026-10-06-accepted-fuller-compact-assembly.py';require(sha(ap)==ASSEMBLY_SHA,'Packet validator changed')
 require(not STAGE.exists() and not DESKTOP.exists(),'Fresh stage and absent Desktop destination required')
 require(not any(p.is_symlink() for p in (INPUT,*INPUT.parents,STAGE,*STAGE.parents,DESKTOP,*DESKTOP.parents)),'Symlink path rejected')
 app=load('desktop_owned_runner',ROOT/'scripts/apply_capture_profile.py');helper=load('desktop_packet_validator',ap)
 deadline=app.Deadline(600);events=[];started=time.monotonic();STAGE.mkdir(mode=0o700)
 protected={str(INPUT):INPUT_SHA,str(INPUT.parent/'receipt.json'):sha(INPUT.parent/'receipt.json')}
 latest=ROOT/'artifacts/latest.json'
 if latest.exists():protected[str(latest)]=sha(latest)
 state={'schema_version':1,'actor':'/root/media_latency','authority':'Explicit operator optimized Desktop export; R-N11/R-N13','created_utc':datetime.now(timezone.utc).isoformat(),'controller_sha256':sha(Path(__file__)),'source_sha256':INPUT_SHA,'source':str(INPUT),'destination':str(DESKTOP),'timeout_seconds':600,'threads':2,'status':'running','new_audio_DSP':False,'current_master_or_latest_promoted':False,'input_sha256':protected}
 save(STAGE/'start.json',state)
 def run(argv,timeout=120):return app.run_owned(argv,deadline=deadline,timeout=min(timeout,deadline.remaining()),events=events)
 def probe(p):return json.loads(run([BIN+'ffprobe','-v','error','-threads','2','-show_streams','-show_format','-show_data_hash','sha256','-of','json',str(p)]).stdout)
 def streams(p):
  v=[s for s in p['streams'] if s['codec_type']=='video'];a=[s for s in p['streams'] if s['codec_type']=='audio'];require(len(v)==len(a)==1,'One audio/video stream required');return v[0],a[0]
 def packets(p,index):return json.loads(run([BIN+'ffprobe','-v','error','-threads','2','-select_streams',str(index),'-show_packets','-show_entries','packet=pts,dts,duration,data_hash,side_data_list:packet_side_data=side_data_type,skip_samples,discard_padding','-show_data_hash','sha256','-of','json',str(p)]).stdout)['packets']
 def pcm(p):
  r=run([BIN+'ffmpeg','-hide_banner','-nostdin','-v','error','-threads','2','-err_detect','explode','-i',str(p),'-map','0:a:0','-vn','-c:a','pcm_f32le','-f','hash','-hash','sha256','-']);require(not r.stderr.strip(),'AAC decoder errors');return r.stdout.strip()
 old=signal.getsignal(signal.SIGALRM);require(signal.getitimer(signal.ITIMER_REAL)==(0.,0.),'Other timer active')
 def alarm(*args):raise app.ApplyError('Desktop derivative 600s deadline','deadline_exceeded')
 signal.signal(signal.SIGALRM,alarm);app.CLI_ALARM_HANDLER=alarm;signal.setitimer(signal.ITIMER_REAL,600)
 try:
  encoders=run([BIN+'ffmpeg','-hide_banner','-encoders']).stdout;require(' libx264 ' in encoders,'H264 encoder unavailable');hevc=False
  before=probe(INPUT);v,a=streams(before);require(v['width']==1620 and v['height']==1080 and a['codec_name']=='aac' and int(a['sample_rate'])==44100 and a['channels']==1,'Source facts changed')
  require(Fraction(v['start_time'])==Fraction(a['start_time'])==0,'Nonzero source clock')
  source_v=packets(INPUT,v['index']);source_a=packets(INPUT,a['index']);source_pcm=pcm(INPUT)
  expected=sorted(int(p['pts'])*Fraction(v['time_base']) for p in source_v);require(len(expected)==3621 and len(set(expected))==3621,'Source picture packet clock ambiguity')
  output=STAGE/'video_util_mvp_demo_1.mp4';tick=Fraction(v['time_base']);require(tick.numerator==1,'Picture timebase unsupported')
  codec=['-c:v','libx265','-preset','medium','-crf','26','-x265-params','pools=none:frame-threads=2:wpp=0','-tag:v','hvc1'] if hevc else ['-c:v','libx264','-preset','veryfast','-crf','27','-threads','2']
  command=[BIN+'ffmpeg','-hide_banner','-nostdin','-loglevel','warning','-threads','2','-filter_threads','2','-n','-copyts','-i',str(INPUT),'-map','0:v:0','-map','0:a:0','-map_metadata','0','-map_chapters','-1','-vf','scale=1080:720:flags=lanczos','-pix_fmt','yuv420p',*codec,'-fps_mode','passthrough','-enc_time_base',v['time_base'],'-video_track_timescale',str(tick.denominator),'-c:a','copy','-avoid_negative_ts','disabled','-movflags','+faststart',str(output)]
  state.update(codec='libx265' if hevc else 'libx264',command=command);save(STAGE/'encode-plan.json',state);run(command,500)
  after=probe(output);nv,na=streams(after);require(nv['width']==1080 and nv['height']==720 and nv['pix_fmt']=='yuv420p','Output picture geometry differs')
  require(nv['codec_name']==('hevc' if hevc else 'h264') and (not hevc or nv['codec_tag_string']=='hvc1'),'Delivery codec/tag differs')
  for k in ('codec_name','sample_rate','channels','extradata_hash'):require(a.get(k)==na.get(k),'Copied AAC format/config differs')
  require(Fraction(nv['start_time'])==Fraction(na['start_time'])==0,'Output origins changed')
  out_a=packets(output,na['index']);helper.exact_packets(source_a,out_a,a['time_base'],na['time_base'],audio=True);require(pcm(output)==source_pcm,'Copied decoded AAC changed')
  decoded=run([BIN+'ffprobe','-v','error','-threads','2','-err_detect','explode','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp,duration','-of','json=compact=1',str(output)],240)
  require(not decoded.stderr.strip(),'Full video decode errors');frames=json.loads(decoded.stdout)['frames'];proof=frame_gate(expected,frames,Fraction(nv['time_base']),max(tick,Fraction(nv['time_base'])))
  require(output.stat().st_size<INPUT.stat().st_size,'Derivative is not smaller');helper.verify(protected);require(sha(Path(__file__))==state['controller_sha256'],'Controller changed')
  samples=[]
  for label,seek in [('widest-label',36.65),('breakdown',44.2),('chorus',96.8)]:
   p=STAGE/(label+'.png');run([BIN+'ffmpeg','-hide_banner','-nostdin','-v','error','-threads','2','-ss',str(seek),'-i',str(output),'-map','0:v:0','-an','-frames:v','1','-threads','2',str(p)],30);samples.append({'path':str(p),'sha256':sha(p),'seek_seconds':seek})
  deadline.check();hash_out=sha(output)
  with output.open('rb') as src,DESKTOP.open('xb') as dst:
   for block in iter(lambda:src.read(1048576),b''):dst.write(block)
   dst.flush();os.fsync(dst.fileno())
  require(sha(DESKTOP)==hash_out,'Desktop copy differs');helper.verify(protected);deadline.check()
  state.update(status='optimized_desktop_export_verified_unreviewed_visual',elapsed_seconds=time.monotonic()-started,desktop_sha256=hash_out,output_bytes=output.stat().st_size,source_bytes=INPUT.stat().st_size,reduction_fraction=1-output.stat().st_size/INPUT.stat().st_size,staged_path=str(output),video_verification=proof,audio_packet_count=len(out_a),audio_packet_payload_clock_padding_identity=True,decoded_audio_pcm_sha256=source_pcm,decoded_audio_identity=True,audio_sample_rate=44100,audio_channels=1,full_video_decode_errors=False,full_audio_decode_errors=False,protected_inputs_unchanged=True,frames=samples,owned_subprocesses=events,output_probe=after,visual_review_performed=False,new_audio_DSP=False)
  save(STAGE/'receipt.json',state);save(ROOT/'docs/agent-notes/2026-10-06-desktop-mvp-export.json',state);print(json.dumps({k:state[k] for k in ('status','destination','desktop_sha256','output_bytes','reduction_fraction','elapsed_seconds')}));return 0
 except BaseException as exc:
  state.update(status='optimized_export_failed_preserving_source',error=str(exc)[:3000],elapsed_seconds=time.monotonic()-started,owned_subprocesses=events,desktop_exists=DESKTOP.exists());save(STAGE/'failure.json',state);raise
 finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old);app.CLI_ALARM_HANDLER=None
if __name__=='__main__':raise SystemExit(main())
