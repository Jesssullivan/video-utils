"""Independent method oracles; no actual recording or FFmpeg DSP is used."""
import importlib.util
import json
import math
import signal
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1]/'docs/agent-notes/2026-10-06-nr8-nr10-comparison.py'
spec = importlib.util.spec_from_file_location('nr_pair', FILE)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

try:
    import numpy as np
    import scipy
except ImportError:
    np = None


class MeterOracles(unittest.TestCase):
    def mocked_run_fixture(self,root):
        protected=[]
        for i in range(7):
            p=root/f'protected-{i}';p.write_text('owned-metadata')
            protected.append({'path':str(p),'sha256':worker.SOURCE_SHA if i==0 else worker.PCM_SHA if i==1 else f'{i:064x}'})
        events=root/'events.csv';events.write_text('kind,audio_relative_seconds\n')
        candidates=[]
        for label in ('nr8','nr10'):
            run=root/'artifacts/runs'/label;run.mkdir(parents=True)
            m=run/'manifest.json';m.write_text('{}')
            files={}
            for role in worker.ROLES:
                p=run/(role+'.wav');p.write_text('header-placeholder');files[role]=p
            video=run/'video.mov';video.write_text('placeholder')
            doc={'manifest_path':m,'application_receipt_path':m,'export_outcome_path':m,'label':label,'files':files,'video':video,
                 'manifest':{'source':{'path':protected[0]['path']},'profile':{'reduction_db':8 if label=='nr8' else 10},
                     'run_id':label,'output_sha256':{role+'.wav':'0'*64 for role in worker.ROLES}},
                 'application_receipt':{'producer':{'application_worker_sha256':worker.APPROVED_APPLICATION_PRODUCERS[label]}},
                 'export_outcome':{'output_sha256':{'cleaned-video.mov':'0'*64},'verification':{}}}
            candidates.append(doc)
        selectors=[{'label':d['label'],**{k:{'path':str(d[k+'_path']),'sha256':'0'*64}
                   for k in ('manifest','application_receipt','export_outcome')}} for d in candidates]
        release=root/'release.json';out=root/'artifacts/experiments/new'
        release.write_text(json.dumps({'schema_version':1,'authority':'root_nr8_nr10_measurement_release',
            'whole_job_seconds_max':worker.WHOLE_SECONDS,
            'approved_application_producers':worker.APPROVED_APPLICATION_PRODUCERS,
            'driver_sha256':'0'*64,'method_sha256':worker.METHOD_SHA,'output_dir':str(out),'ffmpeg':{'path':str(root/'ffmpeg'),'sha256':'0'*64},
            'candidates':selectors,'protected':protected}))
        class Array:
            shape=(6657385,1)
            def __len__(self):return 6657385
        helper=SimpleNamespace(load=lambda p:(44100,Array()),describe=lambda r,x:{'completed_stat':1},
                               np=SimpleNamespace(abs=lambda x:[.2],max=max))
        owned=SimpleNamespace(CLI_ALARM_HANDLER=None,capture=SimpleNamespace(native_pcm=lambda f,d:{'sample_rate':44100,'channels':1,'sample_count':6657385}))
        return release,out,events,candidates,helper,owned

    def candidate_fixture(self, root):
        run=root/'artifacts/runs/case';(run/'export').mkdir(parents=True)
        files={}
        for role in worker.ROLES:
            p=run/(role+'.wav');p.write_bytes(('metadata-fixture-'+role).encode());files[p.name]=worker.sha(p)
        video=run/'export/cleaned-video.mov';video.write_bytes(b'encoded-placeholder')
        profile=dict(reduction_db=8,noise_floor_db=-40,adaptivity=0,gain_smooth=0,integrated_lufs=-18,true_peak_dbtp=-1.75,
            preserve_low_fundamental_hz=32,denoise=True,noise_capture_authorized=True,noise_capture_source_sha256=worker.SOURCE_SHA,
            peaking_eq=worker.EXPECTED_EQ,compressor=worker.EXPECTED_COMP,schema_version=1,name='fixture',description='fixture',
            noise_capture_review='unknown',noise_capture_seconds=[4.1,4.95])
        native={'sample_rate':44100,'channels':1,'sample_count':6657385}
        manifest={'run_dir':str(run),'source':{'sha256':worker.SOURCE_SHA,'probe':{'video':{'time_base':'1/24000'}}},'pcm':native,
            'timeline':{'no_time_stretch':True,'audio_start_seconds':0},'profile':profile,
            'noise_capture':{'selected_samples':[180810,218295],'applies_to_original_start':True,
                             'source_axis_sample_count_preserved':True,'noise_only_verified_by_worker':False,'filter_delay_samples_removed':1102},
            'dsp_latency':{'denoise':{'status':'measured_and_compensated','remaining_bulk_delay_samples':0,'delay_samples':1102}},
            'outputs':{role:role+'.wav' for role in worker.ROLES},'output_sha256':files}
        flags={k:True for k in ('source_hash_verified','video_frame_count_preserved','relative_audio_video_start_verified',
            'dsp_latency_compensation_recorded','video_packet_timeline_preserved','video_packet_payload_hashes_preserved')}
        flags.update(physical_audio_video_sync_verified=False,source_video_packets=3631,export_video_packets=3631,
            source_decoded_video_frames=3631,export_decoded_video_frames=3631,video_packet_clock_tolerance_seconds=1/24000,
            video_packet_max_pts_delta_seconds=0,video_packet_max_dts_delta_seconds=0,video_packet_max_duration_delta_seconds=0,
            relative_audio_video_start_delta_seconds=-.023,aac_timing_tolerance_seconds=1024/44100+.002,
            audio_duration_delta_seconds=.023,video_duration_delta_seconds=-.02)
        outcome={'run_dir':str(run),'source_sha256':worker.SOURCE_SHA,'listening_accepted':False,'verification':flags,
                 'video_probe':{'video':{'time_base':'1/24000'}},
                 'video':str(video),'audio_master':str(run/'cleaned.wav'),'output_sha256':{video.name:worker.sha(video)}}
        app={'run_dir':str(run),'source':{'sha256':worker.SOURCE_SHA},'status':'rendered_unreviewed','listening_accepted':False,
             'master_adopted':False,'native_pcm':native,'producer':{'application_worker_sha256':worker.APPROVED_APPLICATION_PRODUCERS['nr8'],
             'authoring_worker_sha256':worker.AUTHORING_SHA,'media_worker_sha256':worker.MEDIA_SHA},
             'outputs':{'audio_sha256':files,'video_sha256':outcome['output_sha256']}}
        paths={'manifest':run/'manifest.json','application_receipt':run/'application-receipt.json','export_outcome':run/'export/outcome.json'}
        def save():
            for key,obj in [('manifest',manifest),('export_outcome',outcome)]:paths[key].write_text(json.dumps(obj))
            app['outputs'].update(manifest_sha256=worker.sha(paths['manifest']),export_outcome_sha256=worker.sha(paths['export_outcome']))
            paths['application_receipt'].write_text(json.dumps(app))
            return {'label':'nr8',**{k:{'path':str(p),'sha256':worker.sha(p)} for k,p in paths.items()}}
        return manifest,outcome,app,save,files['source.wav']

    def test_delivery_limits_are_inclusive_and_not_musical_acceptance(self):
        for loudness in (-18.3, -17.7):
            d = worker.delivery({'integrated_lufs': loudness, 'true_peak_dbtp': -1.75, 'loudness_range_lu': 3}, True)
            self.assertTrue(d['eligible_for_comparison_delivery'])
            self.assertFalse(d['musical_acceptance'])
            self.assertFalse(d['master_adopted'])
        for data in ({'integrated_lufs': -17.69, 'true_peak_dbtp': -2, 'loudness_range_lu': 3},
                     {'integrated_lufs': -18, 'true_peak_dbtp': -1.749, 'loudness_range_lu': 3}):
            self.assertFalse(worker.delivery(data, True)['eligible_for_comparison_delivery'])
        self.assertFalse(worker.delivery({'integrated_lufs': -18, 'true_peak_dbtp': -2, 'loudness_range_lu': 3}, False)['eligible_for_comparison_delivery'])

    def test_nonfinite_and_bool_meter_refuse(self):
        for value in (float('nan'), float('inf'), True, None):
            with self.assertRaises(worker.ComparisonError):
                worker.delivery({'integrated_lufs': value, 'true_peak_dbtp': -2, 'loudness_range_lu': 3}, True)

    def test_meter_uses_input_and_bounded_owned_runner(self):
        class Deadline:
            def remaining(self): return 7.5
        class Owned:
            @staticmethod
            def run_owned(command, *, deadline, timeout, events):
                assert timeout == 7.5 and '-f' in command and command[-1] == '-'
                assert command.count('2') == 3 and command[command.index('-map')+1] == '0:a:0'
                return type('Result', (), {'stderr': 'header\n'+json.dumps({'input_i': '-18.1', 'input_tp': '-1.82', 'input_lra': '3.4', 'output_i': '-17', 'output_tp': '-1.5'})})()
        result = worker.meter(Owned(), Path('/fixed/ffmpeg'), Path('/candidate.mov'), Deadline(), [])
        self.assertEqual(result['integrated_lufs'], -18.1)
        self.assertEqual(result['true_peak_dbtp'], -1.82)
        self.assertNotIn('normalization_type', result)

    def test_fixed_attack_panel_selection_and_spacing(self):
        times = [10.1999,10.2,10.3,10.6,10.95,19.51,40.21,40.8]
        rows = [{'kind': 'broadband_attack_candidate', 'audio_relative_seconds': str(t)} for t in reversed(times)]
        rows += [{'kind':'spectral_flux_attack_candidate', 'audio_relative_seconds':'11'}]
        self.assertEqual(worker.attack_panels(rows), [10.2,10.6,10.95,40.21,40.8])

    def test_json_rejects_duplicate_overflow_constants(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)/'input.json'
            for text in ('{"x":1,"x":2}', '{"x":1e400}', '{"x":NaN}'):
                p.write_text(text)
                with self.assertRaises(worker.ComparisonError): worker.strict_json(p)

    def test_invalid_release_does_not_write_existing_directory(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)/'release.json'; p.write_text('{}')
            out = Path(t)/'existing';out.mkdir();sentinel = out/'user.txt';sentinel.write_text('retain')
            result = worker.run(p, worker.sha(p), str(out))
            self.assertEqual(result['status'], 'incomplete')
            self.assertEqual(list(out.iterdir()), [sentinel])
            self.assertFalse(result['comparison_delivery_eligible'])

    def test_profile_one_knob_controls_and_extra_filter_refuse(self):
        p = dict(reduction_db=10, noise_floor_db=-40, adaptivity=0, gain_smooth=0,
                 integrated_lufs=-18, true_peak_dbtp=-1.75,preserve_low_fundamental_hz=32,
                 denoise=True, noise_capture_authorized=True, noise_capture_source_sha256=worker.SOURCE_SHA,
                 peaking_eq=worker.EXPECTED_EQ, compressor=worker.EXPECTED_COMP,
                 schema_version=1,name='test',description='test',noise_capture_review='unknown',
                 noise_capture_seconds=[4.1,4.95])
        worker.profile_controls(p,10)
        for k,v in [('true_peak_dbtp',-1.5),('adaptivity',.5),('gain_smooth',2),('reduction_db',8),('highpass_hz',80)]:
            with self.assertRaises(worker.ComparisonError):worker.profile_controls({**p,k:v},10)

    def test_pinned_helper_and_runner_sources_are_the_frozen_bytes(self):
        for p,h in [(worker.METHOD,worker.METHOD_SHA),(worker.HELPER,worker.HELPER_SHA),
                    (worker.SEGMENT,worker.SEGMENT_SHA),(worker.APPLICATION,worker.APPLICATION_SHA),
                    (worker.HISTORICAL_APPLICATION,worker.APPROVED_APPLICATION_PRODUCERS['nr8']),
                    (worker.RESOURCE_QUALIFICATION,worker.RESOURCE_QUALIFICATION_SHA)]:
            self.assertEqual(worker.sha(p),h)

    def test_inert_owned_subprocess_has_explicit_session_cleanup(self):
        owned = worker.load_module(worker.APPLICATION,'nr_test_owned')
        events=[]
        result=owned.run_owned([sys.executable,'-c','print("inert-oracle")'],
                              deadline=owned.Deadline(5),timeout=2,events=events)
        self.assertEqual(result.stdout.strip(),'inert-oracle')
        self.assertTrue(events)
        self.assertEqual(events[-1]['result'],'leader_reaped_no_runnable_same_session_group_members')

    def test_packet_timeline_not_twenty_ms_header_metadata_decides(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();m,e,a,save,pcm=self.candidate_fixture(root)
            deadline=type('Budget',(),{'check':lambda s:None})()
            with patch.object(worker,'ROOT',root),patch.object(worker,'PCM_SHA',pcm):
                worker.validate_candidate(save(),'nr8',deadline) # exact packets despite -20ms metadata
                e['verification']['video_packet_max_pts_delta_seconds']=.02
                with self.assertRaises(worker.ComparisonError):worker.validate_candidate(save(),'nr8',deadline)

    def test_coarse_actual_mov_clock_uses_exact_known_rational_tick(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();m,e,a,save,pcm=self.candidate_fixture(root)
            m['source']['probe']['video']['time_base']='1/600'
            e['video_probe']['video']['time_base']='1/19200'
            e['verification']['video_packet_clock_tolerance_seconds']=1/600
            deadline=type('Budget',(),{'check':lambda s:None})()
            with patch.object(worker,'ROOT',root),patch.object(worker,'PCM_SHA',pcm):
                worker.validate_candidate(save(),'nr8',deadline)
                e['verification']['video_packet_clock_tolerance_seconds']=.02
                with self.assertRaises(worker.ComparisonError):worker.validate_candidate(save(),'nr8',deadline)
                e['verification']['video_packet_clock_tolerance_seconds']=1/600
                e['verification']['video_packet_max_pts_delta_seconds']=.02
                with self.assertRaises(worker.ComparisonError):worker.validate_candidate(save(),'nr8',deadline)

    def test_native_capture_unknown_and_padding_refusals(self):
        changes=[('native',None),('capture',None),('aac_duration',None),('physical_sync',None)]
        for change,unused in changes:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as t:
                root=Path(t).resolve();m,e,a,save,pcm=self.candidate_fixture(root)
                if change=='native':a['native_pcm']={**a['native_pcm'],'sample_count':6657384}
                if change=='capture':m['noise_capture']['noise_only_verified_by_worker']=True
                if change=='aac_duration':e['verification']['audio_duration_delta_seconds']=.05
                if change=='physical_sync':e['verification']['physical_audio_video_sync_verified']=True
                with patch.object(worker,'ROOT',root),patch.object(worker,'PCM_SHA',pcm):
                    with self.assertRaises(worker.ComparisonError):worker.validate_candidate(save(),'nr8',type('Budget',(),{'check':lambda s:None})())

    def test_changed_media_bytes_refused_despite_frozen_manifest_flags(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();m,e,a,save,pcm=self.candidate_fixture(root);d=save()
            (root/'artifacts/runs/case/processed.wav').write_bytes(b'changed')
            with patch.object(worker,'ROOT',root),patch.object(worker,'PCM_SHA',pcm):
                with self.assertRaises(worker.ComparisonError):worker.validate_candidate(d,'nr8',type('Budget',(),{'check':lambda s:None})())

    def test_preflight_stall_is_timed_before_module_import_and_restores_handler(self):
        before=signal.getsignal(signal.SIGALRM)
        with patch.object(worker,'PROCESS_SECONDS',.08),patch.object(worker,'pinned',side_effect=lambda *a:time.sleep(.4)):
            result=worker.run('/unused','0'*64,'/unused-output')
        self.assertEqual(result['status'],'incomplete')
        self.assertIn('deadline',result['error']['message'])
        self.assertLess(result['elapsed_seconds'],.35)
        self.assertIs(signal.getsignal(signal.SIGALRM),before)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.))

    def test_import_stall_is_timed_and_partial_role_panels_are_retained(self):
        before=signal.getsignal(signal.SIGALRM)
        for stall in ('import','partial_panel'):
            with self.subTest(stall=stall),tempfile.TemporaryDirectory() as t:
                root=Path(t).resolve();release,out,events,candidates,helper,owned=self.mocked_run_fixture(root)
                loader=(lambda *args:time.sleep(.4)) if stall=='import' else (lambda p,n:helper if p==worker.HELPER else owned)
                with patch.object(worker,'ROOT',root),patch.object(worker,'EVENTS',events),\
                     patch.object(worker,'PROCESS_SECONDS',.08 if stall=='import' else 2),\
                     patch.object(worker,'pinned',side_effect=lambda p,h,d:Path(p).resolve()),\
                     patch.object(worker,'validate_candidate',side_effect=candidates),\
                     patch.object(worker,'load_module',side_effect=loader),\
                     patch.object(worker,'short_panels',return_value=[]),\
                     patch.object(worker,'local_stats',side_effect=[{'completed_panel':1},worker.ComparisonError('inert interrupted panel')]):
                    result=worker.run(release,'0'*64,str(out))
                saved=json.loads((out/'results.json').read_text())
                self.assertEqual(saved['status'],'incomplete')
                if stall=='partial_panel':
                    role=saved['candidates'][0]['artifacts']['denoised']
                    self.assertEqual(role['completed_stat'],1)
                    self.assertEqual(role['local_panels'],[{'completed_panel':1}])
                    self.assertFalse(saved['candidates'][0]['measurement_complete'])
                else:self.assertLess(result['elapsed_seconds'],.35)
        self.assertIs(signal.getsignal(signal.SIGALRM),before)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.))

    def test_closed_producer_map_accepts_only_the_exact_role_versions(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();m,e,a,save,pcm=self.candidate_fixture(root)
            deadline=type('Budget',(),{'check':lambda s:None})()
            with patch.object(worker,'ROOT',root),patch.object(worker,'PCM_SHA',pcm):
                worker.validate_candidate(save(),'nr8',deadline)
                m['profile']['reduction_db']=10
                d=save();d['label']='nr10'
                with self.assertRaises(worker.ComparisonError):worker.validate_candidate(d,'nr10',deadline)
                a['producer']['application_worker_sha256']=worker.APPROVED_APPLICATION_PRODUCERS['nr10']
                d=save();d['label']='nr10';worker.validate_candidate(d,'nr10',deadline)
                for bad in (worker.APPROVED_APPLICATION_PRODUCERS['nr8'],'f'*64):
                    a['producer']['application_worker_sha256']=bad;d=save();d['label']='nr10'
                    with self.assertRaises(worker.ComparisonError):worker.validate_candidate(d,'nr10',deadline)

    def test_release_cannot_broaden_or_swap_approved_producer_map(self):
        for bad in ({}, {**worker.APPROVED_APPLICATION_PRODUCERS,'extra':'f'*64},
                    {'nr8':worker.APPLICATION_SHA,'nr10':worker.APPROVED_APPLICATION_PRODUCERS['nr8']}):
            with self.subTest(bad=bad),tempfile.TemporaryDirectory() as t:
                root=Path(t).resolve();release,out,events,candidates,helper,owned=self.mocked_run_fixture(root)
                value=json.loads(release.read_text());value['approved_application_producers']=bad;release.write_text(json.dumps(value))
                result=worker.run(release,worker.sha(release),str(out))
                self.assertEqual(result['status'],'incomplete');self.assertIn('producer map',result['error']['message'])
                self.assertFalse(out.exists())

    def test_explicit_budget_refuses_old60_and_bool_values_before_inputs(self):
        self.assertEqual(worker.WHOLE_SECONDS,300)
        self.assertEqual(worker.PROCESS_SECONDS,295)
        for bad in (60,True,300.0):
            with self.subTest(bad=bad),tempfile.TemporaryDirectory() as t:
                root=Path(t).resolve();release,out,events,candidates,helper,owned=self.mocked_run_fixture(root)
                value=json.loads(release.read_text());value['whole_job_seconds_max']=bad;release.write_text(json.dumps(value))
                result=worker.run(release,worker.sha(release),str(out))
                self.assertEqual(result['status'],'incomplete');self.assertIn('budget',result['error']['message'])
                self.assertFalse(out.exists())

    def test_resource_revision_cannot_change_shared_authoring_or_media(self):
        for field in ('authoring_worker_sha256','media_worker_sha256'):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as t:
                root=Path(t).resolve();m,e,a,save,pcm=self.candidate_fixture(root)
                a['producer'][field]='f'*64
                with patch.object(worker,'ROOT',root),patch.object(worker,'PCM_SHA',pcm):
                    with self.assertRaises(worker.ComparisonError):worker.validate_candidate(save(),'nr8',type('Budget',(),{'check':lambda s:None})())

    def test_historical_driver_and_test_snapshots_preserve_exact_prior_bytes(self):
        snapshot=worker.ROOT/'docs/agent-notes/source-freezes'
        self.assertEqual(worker.sha(snapshot/'2026-10-06-nr8-nr10-comparison-7f46a701.py'),
                         '7f46a7010f42558bf8d39f8a94fc9b0a6f513a12242e61d6be553267d6e9b26e')
        self.assertEqual(worker.sha(snapshot/'2026-10-06-nr8-nr10-comparison-tests-cd819f20.py'),
                         'cd819f20f73a79ebae94f32c1275bb9635622de3bbae46b1ac9aabcb445fe47e')


@unittest.skipIf(np is None,'locked NumPy/SciPy optional; no implicit installation')
class NumericOracles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper=worker.load_module(worker.HELPER,'nr_test_helper')

    def test_coherence_one_can_coexist_with_six_db_low_band_loss(self):
        rate=44100;t=np.arange(rate*2)/rate
        x=(.2*np.sin(2*np.pi*32*t)+.05*np.sin(2*np.pi*113*t))[:,None]
        out=worker.local_stats(self.helper,x,x*.5,rate,0,2)
        low=out['bands']['20-45']
        self.assertAlmostEqual(low['delta_db'],-6.020599913279624,places=10)
        self.assertAlmostEqual(low['coherence_source_power_weighted'],1,places=12)
        self.assertEqual(out['native_samples'],[0,88200])
        self.assertEqual(out['welch_segment_count'],9)

    def test_short_windows_keep_native_index_and_do_not_fit_gain(self):
        x=np.ones((44100,1))*.25
        rows=worker.short_panels(self.helper,x,[.5],44100)
        self.assertEqual(rows[0]['native_sample'],22050)
        self.assertEqual(rows[0]['windows'][1]['native_samples'],[22050,22932])
        self.assertAlmostEqual(rows[0]['windows'][1]['rms_dbfs'],-12.041199826559248,places=10)
        with self.assertRaises(worker.ComparisonError):worker.short_panels(self.helper,x,[0],44100)

    def test_zero_power_has_null_coherence_and_no_nan_json(self):
        x=np.zeros((44100,1))
        with np.errstate(invalid='ignore',divide='ignore'):
            out=worker.local_stats(self.helper,x,x,44100,0,1)
        self.assertIsNone(out['bands']['20-45']['coherence_source_power_weighted'])
        json.dumps(out,allow_nan=False)


if __name__=='__main__':unittest.main()
