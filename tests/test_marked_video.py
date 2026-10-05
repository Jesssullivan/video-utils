"""Source-time selection and preservation of a real, tiny marked-video render."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('marked_video_tests',REPO/'scripts/marked_video.py')
preview=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preview)


def create_verified_fixture(run_dir, ffmpeg, ffprobe, origin=0, vfr=True):
    """Two-second generated media and hash-bound toy review evidence, not musical truth."""
    run_dir.mkdir(parents=True)
    (run_dir/'export').mkdir()
    original=run_dir/'original.mov'
    command=[ffmpeg,'-hide_banner','-nostdin','-loglevel','error','-threads','2','-filter_threads','2',
             '-f','lavfi','-i','testsrc2=size=480x270:rate=12:duration=2',
             '-f','lavfi','-i','sine=frequency=220:sample_rate=48000:duration=2',
             '-c:v','libx264','-preset','ultrafast','-threads','2','-c:a','aac',
             *(['-vf','select=not(eq(n\\,3)+eq(n\\,7)+eq(n\\,16))','-fps_mode:v','passthrough'] if vfr else []),
             '-output_ts_offset',str(origin),str(original)]
    subprocess.run(command,check=True,capture_output=True,timeout=20)
    video=run_dir/'export/cleaned-video.mov'
    subprocess.run([ffmpeg,'-hide_banner','-nostdin','-loglevel','error','-threads','2','-copyts','-i',str(original),
                    '-map','0:v:0','-map','0:a:0','-c','copy','-output_ts_offset',str(-origin),
                    '-avoid_negative_ts','disabled',str(video)],check=True,capture_output=True,timeout=20)
    master=run_dir/'cleaned.wav'
    subprocess.run([ffmpeg,'-hide_banner','-nostdin','-loglevel','error','-threads','2','-i',str(video),
                    '-map','0:a:0','-c:a','pcm_s24le',str(master)],check=True,capture_output=True,timeout=20)
    identity=preview.workflow.sha256(original)
    manifest={'schema_version':1,'source':{'path':str(original),'sha256':identity},
              'timeline':{'format_start_seconds':origin,'audio_start_seconds':origin},
              'output_sha256':{'cleaned.wav':preview.workflow.sha256(master)}}
    (run_dir/'manifest.json').write_text(json.dumps(manifest))
    outcome={'source_sha256':identity,'video':str(video),'audio_master':str(master),
             'output_sha256':{'cleaned-video.mov':preview.workflow.sha256(video)},
             'verification':{key:True for key in ('source_hash_verified','video_frame_count_preserved',
                                  'video_packet_timeline_preserved','final_true_peak_within_target')},
             'final_audio_loudness':{'input_i':'fixture_not_master_acceptance'}}
    outcome['verification']['video_packet_expected_translation_seconds']=-origin
    (run_dir/'export/outcome.json').write_text(json.dumps(outcome))
    flags={'source_sha256':identity,'timeline':{'axis':'original_source_stream_timestamps_seconds','audio_start_seconds':origin},
           'flags':[{'kind':'automatic_recurrence_review_candidate','source_time_seconds':origin+.25,
                     'end_seconds':origin+1.5,'status':'needs_review','confidence':'unvalidated_fixture',
                     'performance_issue_confirmed':False,'evidence':{'warning':'Toy review hypothesis, not musician truth'}}]}
    (run_dir/'flags.json').write_text(json.dumps(flags))
    graph={'source_sha256':identity,'flags_sha256':preview.workflow.sha256(run_dir/'flags.json'),
           'artifact_hashes':{'manifest.json':preview.workflow.sha256(run_dir/'manifest.json')},
           'external_context_hashes':{},'selected_evidence':{}}
    (run_dir/'dag.json').write_text(json.dumps(graph))
    marker,_=preview.marker_tool.build(run_dir)
    (run_dir/'markers.json').write_text(json.dumps(marker))
    (run_dir/'report.html').write_text('Existing report remains unchanged')
    return original,video


class MarkedVideoTests(unittest.TestCase):
    def row(self,name,start,end):
        return {'name':name,'source_time_seconds':start,'end_seconds':end,'status':'needs_review','evidence':{}}

    def test_default_qualifies_phrase_and_comparison_without_navigation_proxies(self):
        rows=[self.row(name,1,2) for name in preview.LABELS]
        selected,excluded=preview.select_markers(rows,'phrase-review',0,0,3)
        self.assertEqual({row['name'] for row in selected},preview.DEFAULT_KINDS)
        self.assertEqual(len(excluded),2)
        recurrence,_=preview.select_markers(rows,'recurrences',0,0,3)
        self.assertEqual(len(recurrence),5)
        all_rows,_=preview.select_markers(rows,'all-review',0,0,3)
        self.assertEqual(len(all_rows),8)

    def test_nonzero_source_container_origin_and_picture_clipping(self):
        rows=[self.row('automatic_recurrence_review_candidate',12.25,13.5),
              self.row('automatic_recurrence_review_candidate',10,12.1)]
        selected,_=preview.select_markers(rows,'recurrences',12,0,2)
        self.assertEqual((selected[0]['video_start_seconds'],selected[0]['video_end_seconds']),(.25,1.5))
        self.assertEqual(selected[1]['video_start_seconds'],0)
        callouts,_=preview.compose_callouts(selected,12)
        self.assertEqual(callouts[0]['source_start_seconds'],12)
        self.assertIn('SOURCE 0:00:12.25',preview.subtitles(callouts,480,270))

    def test_overlap_records_visible_and_suppressed_marker_coverage(self):
        rows=[self.row('automatic_recurrence_review_candidate',0,2),
              self.row('recurrence_motif_timing_difference_review',.5,1.5),
              self.row('recurrence_relative_rate_difference_review',.5,1.5)]
        selected,_=preview.select_markers(rows,'recurrences',0,0,3)
        callouts,coverage=preview.compose_callouts(selected,0)
        middle=next(row for row in callouts if row['video_start_seconds']==.5)
        self.assertEqual(len(middle['visible_marker_ids']),2)
        self.assertEqual(middle['suppressed_marker_ids'],[selected[0]['marker_id']])
        self.assertEqual(coverage[selected[0]['marker_id']],{'visible_seconds':1.,'suppressed_seconds':1.})
        ass=preview.subtitles(callouts,1620,1080)
        self.assertTrue(all(line.count('\\N')==1 for line in ass.splitlines() if line.startswith('Dialogue:')))
        self.assertNotIn('MISTAKE',ass)

    def test_escaping_and_centisecond_carry(self):
        self.assertEqual(preview.timestamp(59.999),'0:01:00.00')
        self.assertEqual(preview.safe_text('{\\pos(0,0)}\nMISTAKE'),'( /pos(0,0)) MISTAKE'.replace('( /','(/'))
        selected,_=preview.select_markers([self.row('{\\evil}',.2,.5)],'all-review',0,0,1)
        self.assertEqual(selected[0]['label'],'Review candidate')

    def test_point_dwell_and_invalid_interval(self):
        selected,_=preview.select_markers([self.row('automatic_recurrence_review_candidate',.2,.2)],'recurrences',0,0,2)
        self.assertTrue(selected[0]['presentation_dwell_extended'])
        self.assertEqual(selected[0]['source_end_seconds'],.2)
        self.assertEqual(selected[0]['video_end_seconds'],1.2)
        with self.assertRaises(ValueError):
            preview.select_markers([self.row('automatic_recurrence_review_candidate',2,1)],'recurrences',0,0,3)

    def test_frame_pts_and_audio_payload_mismatch_fail_verification(self):
        from fractions import Fraction
        base={'frame_pts':[Fraction(0),Fraction(1,12)],'frame_start':0.,'frame_end':1.,'pcm_hash':'SHA256=test',
              'video':{'width':480,'height':270},
              'audio':{'sample_rate':'48000','channels':1,'codec_name':'aac','time_base':'1/48000'},
              'packets':[{'pts':0,'dts':0,'duration':1024,'data_hash':'SHA256=test'}]}
        wrong=json.loads(json.dumps({k:v for k,v in base.items() if k!='frame_pts'}))
        wrong['frame_pts']=[Fraction(0),Fraction(1,10)]
        with self.assertRaisesRegex(ValueError,'frame PTS'):
            preview.verify_render(base,wrong)
        wrong['frame_pts']=base['frame_pts']
        wrong['packets'][0]['data_hash']='bad'
        with self.assertRaisesRegex(ValueError,'payload'):
            preview.verify_render(base,wrong)

    def test_bounded_owned_child_output_and_timeout_receipts(self):
        executions=[]
        with self.assertRaisesRegex(ValueError,'byte bound'):
            preview.command_run([sys.executable,'-c','import os;os.write(1,b"x"*3000000)'],executions,5)
        self.assertEqual(executions[0]['status'],'failed')
        self.assertLessEqual(executions[0]['stdout_bytes'],preview.MAX_PROCESS_BYTES)
        executions=[]
        with self.assertRaisesRegex(ValueError,'deadline'):
            preview.command_run([sys.executable,'-c','import time;time.sleep(5)'],executions,.05)
        cleanup=executions[0]['process_escape_hatch']
        self.assertEqual(cleanup['result']['signal_target'],'owned_worker_only')
        self.assertFalse(cleanup['target_ownership']['new_session_requested'])

    def test_freshness_symlink_and_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve()
            run=root/'artifacts/runs/test'
            run.mkdir(parents=True)
            with patch.object(preview,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'fresh'):
                    preview.local_directory(run,True)
                alias=run.parent/'alias'
                alias.symlink_to(run)
                with self.assertRaisesRegex(ValueError,'Symlink'):
                    preview.local_directory(alias)
                with self.assertRaises(ValueError):
                    preview.local_directory(run/'..'/'other',True)

    def test_repository_artifact_boundary_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve()
            real=root/'real-runs'
            (real/'test').mkdir(parents=True)
            (root/'artifacts').mkdir()
            (root/'artifacts/runs').symlink_to(real)
            with patch.object(preview,'ROOT',root):
                with self.assertRaisesRegex(ValueError,'boundary'):
                    preview.local_directory(real/'test')


class RealMarkedVideoTests(unittest.TestCase):
    def setUp(self):
        self.ffmpeg=os.environ.get('FFMPEG') or shutil.which('ffmpeg')
        self.ffprobe=os.environ.get('FFPROBE') or shutil.which('ffprobe')
        if not self.ffmpeg or not self.ffprobe:
            self.skipTest('Explicit FFmpeg/FFprobe or PATH required for real render proof')
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        for module in (preview,preview.marker_tool):
            handle=patch.object(module,'ROOT',self.root)
            handle.start()
            self.addCleanup(handle.stop)
        handle=patch.dict(os.environ,{'FFMPEG':self.ffmpeg,'FFPROBE':self.ffprobe})
        handle.start()
        self.addCleanup(handle.stop)
        self.run_dir=self.root/'artifacts/runs/tiny'
        self.output=self.root/'artifacts/runs/tiny-marked'
        create_verified_fixture(self.run_dir,self.ffmpeg,self.ffprobe,origin=2.)

    def test_real_nonzero_origin_render_preserves_picture_pts_and_audio(self):
        before={path:preview.workflow.sha256(path) for path in self.run_dir.rglob('*') if path.is_file()}
        result=preview.render(self.run_dir,self.output)
        outcome=json.loads(Path(result['outcome_json']).read_text())
        self.assertEqual(result['status'],'marked_review_preview_verified_unreviewed')
        self.assertTrue(outcome['verification']['aac_packet_payloads_timing_and_padding_preserved'])
        self.assertTrue(outcome['verification']['decoded_audio_pcm_sha256_preserved'])
        self.assertTrue(outcome['verification']['decoded_video_frame_pts_preserved'])
        self.assertTrue(outcome['verification']['decoded_video_variable_frame_intervals_observed'])
        self.assertTrue(outcome['input_hashes_preserved'])
        self.assertEqual(outcome['verification']['decoded_video_frame_count'],21)
        self.assertFalse(outcome['listening_accepted'])
        selection=json.loads(Path(result['selection_json']).read_text())
        self.assertEqual(selection['selected_markers'][0]['source_start_seconds'],2.25)
        self.assertEqual(selection['selected_markers'][0]['video_start_seconds'],.25)
        self.assertEqual(len(selection['selected_markers'][0]['flags']),1)
        for path,identity in before.items():
            self.assertEqual(preview.workflow.sha256(path),identity)

    def test_stale_markers_and_source_fail_before_render(self):
        markers=self.run_dir/'markers.json'
        payload=json.loads(markers.read_text())
        payload['markers'][0]['source_time_seconds']=9
        markers.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError,'markers differ'):
            preview.render(self.run_dir,self.output)
        self.assertFalse(self.output.exists())

    def test_original_source_hash_change_fails_before_render(self):
        with (self.run_dir/'original.mov').open('ab') as handle:
            handle.write(b'changed fixture')
        with self.assertRaisesRegex(ValueError,'source hash mismatch'):
            preview.render(self.run_dir,self.output)
        self.assertFalse(self.output.exists())

    def test_failed_verification_preserves_diagnostic_preview_and_existing_inputs(self):
        before=preview.workflow.sha256(self.run_dir/'export/cleaned-video.mov')
        with patch.object(preview,'verify_render',side_effect=ValueError('deliberate verification rejection')):
            with self.assertRaisesRegex(ValueError,'verification rejection'):
                preview.render(self.run_dir,self.output)
        outcome=json.loads((self.output/'outcome.json').read_text())
        self.assertEqual(outcome['status'],'failed_preview_preserving_inputs')
        self.assertTrue((self.output/'marked-video.mov').exists())
        self.assertEqual(preview.workflow.sha256(self.run_dir/'export/cleaned-video.mov'),before)


if __name__=='__main__':
    unittest.main()
