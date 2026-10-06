"""Inert harness contract tests; no fixture PCM, FFmpeg or DSP execution."""
import importlib.util
import array
from contextlib import nullcontext
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location('native_qualification_harness',HERE/'2026-10-06-capture-application-native-qualification.py')
h=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(h)


class NativeQualificationHarnessTests(unittest.TestCase):
    def test_preregistered_native_support_arithmetic(self):
        facts=h.support_facts()
        self.assertEqual(facts['picture_frames'],175)
        self.assertEqual(facts['last_picture_extent_seconds'],'19/2')
        self.assertEqual(facts['capture_training_samples'],33075)
        self.assertEqual(facts['capture_guard_samples'],4410)
        self.assertEqual(facts['filter_trim_samples'],[38587,391387])
        self.assertEqual(391387-38587,352800)

    def test_s16_reference_mapping_preserves_signed_channel_transport_exactly(self):
        # Pure integer constants, not a generated audio fixture or a decode.
        interleaved=array.array('h',[-32768,32767,0,1,-1,8192])
        expected=array.array('f',[-1,32767/32768,0,1/32768,-1/32768,.25])
        self.assertEqual(h.s16_to_f32(interleaved),expected)

    def test_decoded_aac_origin_is_independent_of_priming_packet_and_native_count(self):
        evidence={'packets':[{'pts':21026,'side_data_list':[{'skip_samples':1024}]}],
                  'frames':[{'best_effort_timestamp':22050,'nb_samples':1024},
                            {'best_effort_timestamp':373282,'nb_samples':1024}],
                  'raw_decoded_sample_count':353280}
        gate=h.audio_origin_gate(evidence,'1/44100',h.Fraction(0))
        self.assertEqual(gate['relative_decoded_audio_video_seconds'],'1/2')
        self.assertFalse(gate['physical_sync_verified'])
        self.assertEqual(evidence['raw_decoded_sample_count'],353280)
        evidence['frames'][0]['best_effort_timestamp']=0
        with self.assertRaisesRegex(ValueError,'origin differs'):
            h.audio_origin_gate(evidence,'1/44100',h.Fraction(0))

    def test_qualification_alarm_rearms_after_multiple_committed_application_probes(self):
        # Simulate the qualified cleanup's deliberate timer suspension. No alarm
        # is actually armed and no subprocess is started in this inert fixture.
        handler=object();app=h.load_application();media=app.media;committed={'run_dir':'/kept/recovery'}
        def suspended_runner(*args,**kwargs):
            with app.protect_owned_cleanup():pass
            return 'inert-probe-result'
        app.CLI_ALARM_HANDLER=handler;app.LAST_COMMITTED=committed;app.run_owned=suspended_runner
        deadline=SimpleNamespace(check=lambda:None,ends=103.)
        with patch.object(h.signal,'getsignal',return_value=handler),patch.object(h.signal,'setitimer') as timer,\
             patch.object(h.signal,'getitimer',return_value=(3.,0.)),\
             patch.object(h.time,'monotonic',return_value=100.):
            h.resume_qualification_alarm(app,deadline,[])
            for _ in range(2):
                self.assertEqual(media.run(['/inert/probe'],30),'inert-probe-result')
                self.assertEqual(timer.call_args.args,(h.signal.ITIMER_REAL,3.))
        self.assertIs(app.LAST_COMMITTED,committed)

    def test_existing_alarm_ownership_rejects_before_environment_or_timer_mutation(self):
        before=dict(h.os.environ)
        for timer_state in ((1.,0.),(0.,.1)):
            with self.subTest(timer=timer_state),patch.object(h.signal,'getsignal',return_value=object()),\
                 patch.object(h.signal,'getitimer',return_value=timer_state),patch.object(h.signal,'setitimer') as timer:
                with self.assertRaisesRegex(ValueError,'outside this harness ownership'):
                    with h.bounded_environment(SimpleNamespace(),{},None,[]):pass
                timer.assert_not_called()
        self.assertEqual(dict(h.os.environ),before)

    def test_mux_keeps_nonzero_origins_and_vfr_without_shortest(self):
        argv=h.mux_arguments(Path('/fixed/reference.wav'),Path('/fixed/original.mov'))
        self.assertEqual(argv[argv.index('-itsoffset')+1],'0.5')
        self.assertEqual(argv[argv.index('-output_ts_offset')+1],'1')
        self.assertEqual(argv[argv.index('-fps_mode')+1],'passthrough')
        self.assertEqual(argv[argv.index('-c:a')+1],'pcm_s16le')
        self.assertNotIn('-shortest',argv)
        self.assertNotIn('asetpts',str(argv))

    def inert_prereg(self,folder):
        bins={}
        for name in ('ffmpeg','ffprobe'):
            file=folder/name;file.write_text('inert executable, never run');file.chmod(0o700)
            bins[name]=file
        with patch.object(h,'verify_pins'),patch.object(h,'ROOT',folder):
            (folder/'profiles').mkdir();(folder/'profiles/bypass.json').write_text('{}')
            p=h.preregister('native-inert-contract',bins['ffmpeg'],bins['ffprobe'])
        return p

    def released(self,p,plan_path):
        return {'schema_version':1,'action':'execute_capture_application_native_qualification',
          'root_explicit_release':True,'preregistration_sha256':h.digest(plan_path),
          'harness_sha256':h.digest(h.__file__),'plan_sha256':h.PLAN_SHA,'worker_sha256':h.PINS,
          'output':p['output'],'authorization_reference':'inert test contract; not a numerical release'}

    def test_release_requires_every_exact_identity_before_any_application_import(self):
        for key,replacement in [('root_explicit_release',False),('plan_sha256','0'*64),
          ('worker_sha256',{}),('harness_sha256','0'*64),('action','anything'),('schema_version',True)]:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as name:
                folder=Path(name).resolve();p=self.inert_prereg(folder);pp=folder/'p.json';h.write_new(pp,p)
                r=self.released(p,pp);r[key]=replacement;rp=folder/'r.json';h.write_new(rp,r)
                with patch.object(h,'load_application') as load,self.assertRaises(ValueError):
                    h.execute(pp,rp)
                load.assert_not_called()
                self.assertFalse(Path(p['output']).exists())

    def test_changed_preregistered_settings_are_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name).resolve();p=self.inert_prereg(folder);p['controls']={**p['controls'],'reduction_db':8}
            pp=folder/'p.json';h.write_new(pp,p);r=self.released(p,pp);rp=folder/'r.json';h.write_new(rp,r)
            expected={**p,'controls':h.CONTROLS}
            with patch.object(h,'preregister',return_value=expected),self.assertRaisesRegex(ValueError,'Preregistered'):
                h.validate_release(pp,rp)

    def test_exact_release_validation_is_metadata_only(self):
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name).resolve();p=self.inert_prereg(folder);p['output']=str(folder/'native-inert-contract')
            pp=folder/'p.json';h.write_new(pp,p);rp=folder/'r.json';h.write_new(rp,self.released(p,pp))
            with patch.object(h,'BASE',folder),patch.object(h,'preregister',return_value=p),patch.object(h,'load_application') as load:
                actual,_=h.validate_release(pp,rp)
            self.assertEqual(actual,p);load.assert_not_called();self.assertFalse(Path(p['output']).exists())

    def test_trial_output_collision_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name).resolve();p=self.inert_prereg(folder);p['output']=str(folder/'native-inert-contract')
            pp=folder/'p.json';h.write_new(pp,p);rp=folder/'r.json';h.write_new(rp,self.released(p,pp))
            dest=Path(p['output']);dest.mkdir()
            with patch.object(h,'BASE',folder),patch.object(h,'preregister',return_value=p),self.assertRaisesRegex(ValueError,'Fresh'):
                h.validate_release(pp,rp)
            dest.rmdir();dest.symlink_to(folder,target_is_directory=True)
            with patch.object(h,'BASE',folder),patch.object(h,'preregister',return_value=p),self.assertRaisesRegex(ValueError,'Fresh'):
                h.validate_release(pp,rp)

    def test_bounded_duplicate_nonfinite_metadata_and_closed_release(self):
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name).resolve();file=folder/'bad.json'
            for raw in ('{"x":1,"x":2}','{"x":NaN}','{"x":1e999}'):
                file.write_text(raw)
                with self.assertRaises(ValueError):h.read_json(file)
            file.write_bytes(b' '* (h.MAX_JSON+1))
            with self.assertRaises(ValueError):h.read_json(file)
            p=self.inert_prereg(folder);pp=folder/'p.json';h.write_new(pp,p)
            r=self.released(p,pp);r['extra_dsp_filter']='unsafe';rp=folder/'r.json';h.write_new(rp,r)
            with self.assertRaisesRegex(ValueError,'closed'):h.validate_release(pp,rp)

    def test_failed_picture_timing_gate_keeps_measured_expected_separate(self):
        class FakeMedia:pass
        probe={'video':{'index':0,'time_base':'1/24','start_time':1},'audio':{'start_time':1.5},'format':{'start_time':1}}
        rows=[{'best_effort_timestamp':24+n,'duration':1} for n in h.support_facts()['picture_indices']]
        with patch.object(h,'picture_frames',return_value=rows):
            result=h.picture_gate(FakeMedia(),Path('/not-read.mov'),probe)
        self.assertEqual(result['decoded_frames'],175)
        bad=[dict(row) for row in rows];bad[4]['best_effort_timestamp']+=1
        with patch.object(h,'picture_frames',return_value=bad),self.assertRaisesRegex(ValueError,'PTS differs'):
            h.picture_gate(FakeMedia(),Path('/not-read.mov'),probe)
        probe['audio']['start_time']=0
        with patch.object(h,'picture_frames',return_value=rows),self.assertRaisesRegex(ValueError,'origins differ'):
            h.picture_gate(FakeMedia(),Path('/not-read.mov'),probe)

    def test_failure_receipt_retains_published_recovery_without_false_absence(self):
        class RecoveredError(ValueError):pass
        exc=RecoveredError('injected publication interruption')
        exc.committed_candidate={'run_dir':'/explicit/recovery-only','status':'published_unreviewed'}
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name).resolve();pp=folder/'p.json';rp=folder/'r.json'
            h.write_new(pp,{'inert':True});h.write_new(rp,{'inert':True})
            p={'output':str(folder/'native-failure')};app=SimpleNamespace(Deadline=lambda _:SimpleNamespace(ends=0))
            with patch.object(h,'validate_release',return_value=(p,{})),patch.object(h,'load_application',return_value=app),\
                 patch.object(h,'bounded_environment',return_value=nullcontext()),patch.object(h,'current_protection',side_effect=exc),\
                 patch.object(h,'generated_samples') as generate,self.assertRaisesRegex(RuntimeError,'retained'):
                h.execute(pp,rp)
            generate.assert_not_called()
            receipt=h.read_json(Path(p['output'])/'failure.json')
            self.assertFalse(receipt['candidate_absence_asserted'])
            self.assertEqual(receipt['application_published_candidate_recovery'],exc.committed_candidate)
            self.assertIsNone(receipt['protected_unchanged'])
            self.assertIsNone(receipt['parent_unchanged'])

    def test_unknown_publication_possible_selectors_never_become_confirmed_commit(self):
        class UnknownPublication(ValueError):pass
        exc=UnknownPublication('injected rename observation failure')
        exc.committed_candidate=None;exc.possible_candidate={'run_dir':'/possible/unverified','receipt_sha256':'b'*64}
        # Actual exception carries possible_candidate without an outcome field.
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name).resolve();pp=folder/'p.json';rp=folder/'r.json'
            h.write_new(pp,{'inert':True});h.write_new(rp,{'inert':True})
            p={'output':str(folder/'native-unknown')};app=SimpleNamespace(Deadline=lambda _:SimpleNamespace(ends=0),LAST_COMMITTED=None)
            with patch.object(h,'validate_release',return_value=(p,{})),patch.object(h,'load_application',return_value=app),\
                 patch.object(h,'bounded_environment',return_value=nullcontext()),patch.object(h,'current_protection',side_effect=exc),\
                 patch.object(h,'generated_samples') as generate,self.assertRaises(RuntimeError):
                h.execute(pp,rp)
            generate.assert_not_called();receipt=h.read_json(Path(p['output'])/'failure.json')
            self.assertFalse(receipt['candidate_absence_asserted'])
            self.assertEqual(receipt['application_possible_candidate_recovery'],exc.possible_candidate)
            self.assertEqual(receipt['application_publication_outcome'],'unknown_after_publish_attempt')
            self.assertNotIn('application_published_candidate_recovery',receipt)


if __name__=='__main__':unittest.main()
