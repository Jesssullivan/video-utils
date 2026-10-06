from __future__ import annotations
import array
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import basic_pitch_compare as bp


def matrices(n=30):
    return [[0.]*88 for _ in range(n)],[[0.]*88 for _ in range(n)]


class DecoderTests(unittest.TestCase):
    def test_polyphonic_bins_and_no_intended_grade(self):
        note,onset=matrices()
        for row in note:
            row[3]=.8;row[15]=.7
        events=bp.decode(note,onset,127.7,bp.settings())
        self.assertEqual([e['midi_candidate'] for e in events],[24,36])
        self.assertTrue(all(e['performance_issue'] is None and e['identified_string'] is None for e in events))

    def test_onset_splits_same_pitch(self):
        note,onset=matrices(40)
        for row in note:row[3]=.8
        onset[20][3]=.8
        self.assertEqual([(e['start_frame'],e['end_frame_exclusive']) for e in bp.decode(note,onset,127.7,bp.settings())],[(0,20),(20,40)])

    def test_one_frame_gap_is_not_bridged(self):
        note,onset=matrices(40)
        for row in note:row[3]=.8
        note[20][3]=0
        self.assertEqual([(e['start_frame'],e['end_frame_exclusive']) for e in bp.decode(note,onset,127.7,bp.settings())],[(0,20),(21,40)])

    def test_project_floor_127_7_accepts_11_hops(self):
        note,onset=matrices(12)
        for row in note[:11]:row[3]=.8
        self.assertEqual(len(bp.decode(note,onset,127.7,bp.settings())),1)
        self.assertEqual(len(bp.decode(note,onset,128,bp.settings())),0)

    def test_25_ms_requires_three_hops(self):
        for n,expected in [(2,0),(3,1)]:
            note,onset=matrices(n)
            for row in note:row[3]=.8
            self.assertEqual(len(bp.decode(note,onset,25,bp.settings())),expected)

    def test_empirical_clock_step_changes_duration_gate(self):
        note,onset=matrices(174)
        for row in note[170:173]:row[3]=.8
        self.assertLess(bp.frame_time(173)-bp.frame_time(170),.025)
        self.assertEqual(bp.decode(note,onset,25,bp.settings()),[])

    def test_rejects_invalid_values_and_shapes(self):
        for value in [float('nan'),float('inf'),-1.,1.1,True]:
            note,onset=matrices();note[0][0]=value
            with self.assertRaises(ValueError):bp.decode(note,onset,25,bp.settings())
        with self.assertRaises(ValueError):bp.decode([],[],25,bp.settings())
        with self.assertRaises(ValueError):bp.decode([[0.]*87],[[0.]*87],25,bp.settings())

    def test_silence_stays_empty(self):
        self.assertEqual(bp.decode(*matrices(),25,bp.settings()),[])


class BoundTests(unittest.TestCase):
    def test_settings_reject_nonfinite_or_out_of_bounds(self):
        for value in [0,31,float('nan'),float('inf'),True]:
            with self.assertRaises(ValueError):bp.settings(value)
        for value in [0,.96,float('nan')]:
            with self.assertRaises(ValueError):bp.settings(onset=value)
        with self.assertRaises(ValueError):bp.settings(start=-1)

    def test_default_schedule_includes_first_and_ending(self):
        plan=bp.schedule(150.961111,bp.settings())
        self.assertEqual(len(plan),4)
        self.assertEqual(plan[0]['start_seconds'],0)
        self.assertAlmostEqual(plan[-1]['end_seconds'],150.961111)
        self.assertAlmostEqual(sum(e['end_seconds']-e['start_seconds'] for e in plan),20)

    def test_short_and_explicit_schedule(self):
        self.assertEqual(bp.schedule(8,bp.settings()),[{'start_seconds':0.,'end_seconds':8.}])
        self.assertEqual(bp.schedule(8,bp.settings(30,start=7)),[{'start_seconds':7.,'end_seconds':8.}])
        with self.assertRaises(ValueError):bp.schedule(8,bp.settings(start=8))
        with self.assertRaises(ValueError):bp.schedule(301,bp.settings())

    def test_max_schedule_model_window_bound(self):
        plan=bp.schedule(200,bp.settings(30))
        self.assertLessEqual(sum(math.ceil((round((e['end_seconds']-e['start_seconds'])*bp.RATE)+3840)/bp.STEP) for e in plan),24)

    def test_deadline_reaps_only_own_child(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)
            with self.assertRaisesRegex(ValueError,'deadline'):
                bp.bounded_child([sys.executable,'-c','import time;time.sleep(10)'],output,time.monotonic()+.1)
            receipt=json.loads((output/'worker-resource.json').read_text())
            self.assertEqual(receipt['owner_pid'],os.getpid())
            self.assertEqual(receipt['ruling'],'R-N11')
            self.assertIsNotNone(receipt['returncode'])

    def test_monitor_exception_reaps_child(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(bp.subprocess,'run',side_effect=OSError('injected ps failure')):
                with self.assertRaisesRegex(ValueError,'injected ps failure'):
                    bp.bounded_child([sys.executable,'-c','import time;time.sleep(10)'],Path(temp),time.monotonic()+10)
            self.assertIsNotNone(json.loads((Path(temp)/'worker-resource.json').read_text())['returncode'])

    def test_model_change_fails_before_media_decode(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);(path/'denoised.wav').write_bytes(b'fixture')
            (path/'manifest.json').write_text(json.dumps({'source':{'sha256':'a'*64},'output_sha256':{'denoised.wav':bp.sha256(path/'denoised.wav')},'timeline':{'no_time_stretch':True,'audio_start_seconds':0.}}))
            model=path/'bad.onnx';model.write_bytes(b'wrong')
            (path/'program').mkdir();(path/'program/models.json').write_text(json.dumps({'models':{bp.MODEL_ID:{'sha256':bp.MODEL_HASH,'max_bytes':230444}}}))
            with patch.object(bp,'ROOT',path),patch.object(bp,'LOCAL_MODEL',model):
                with self.assertRaisesRegex(ValueError,'prequalified model'):
                    bp.build(path,bp.settings())

    def test_missing_model_has_actionable_prefetch_error_without_inference(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);(path/'denoised.wav').write_bytes(b'fixture')
            (path/'manifest.json').write_text(json.dumps({'source':{'sha256':'a'*64},'output_sha256':{'denoised.wav':bp.sha256(path/'denoised.wav')},'timeline':{'no_time_stretch':True,'audio_start_seconds':0.}}))
            (path/'program').mkdir();(path/'program/models.json').write_text(json.dumps({'models':{bp.MODEL_ID:{'sha256':bp.MODEL_HASH,'max_bytes':230444}}}))
            with patch.object(bp,'ROOT',path),patch.object(bp,'LOCAL_MODEL',path/'absent.onnx'),patch.object(bp.subprocess,'run') as media:
                with self.assertRaisesRegex(ValueError,'explicitly run just model-prefetch '+bp.MODEL_ID):bp.build(path,bp.settings())
                media.assert_not_called()
            self.assertFalse((path/'learned-pitch').exists())

    def test_unknown_or_nonfinite_origin_fails_before_processing(self):
        for origin in ('absent',None,True,float('nan'),float('inf')):
            with self.subTest(origin=origin),tempfile.TemporaryDirectory() as temp:
                path=Path(temp);timeline={'no_time_stretch':True}
                if origin!='absent':timeline['audio_start_seconds']=origin
                (path/'manifest.json').write_text(json.dumps({'timeline':timeline}))
                with patch.object(bp.subprocess,'run') as media:
                    with self.assertRaisesRegex(ValueError,'audio_start_seconds'):
                        bp.build(path,bp.settings())
                    media.assert_not_called()
                self.assertFalse((path/'learned-pitch').exists())

    def test_three_clocks_are_distinct_at_seams(self):
        nominal=142*256/bp.RATE
        projection=(bp.STEP-3840+15*256)/bp.RATE
        self.assertAlmostEqual(projection-nominal,-.008526077097505746)
        self.assertAlmostEqual(bp.frame_time(142),nominal)
        self.assertNotEqual(bp.frame_time(172),172*256/bp.RATE)


@unittest.skipUnless(os.environ.get('BASIC_PITCH_RUNTIME_TEST')=='1','optional qualified runtime integration; no implicit install')
class QualifiedRuntimeTests(unittest.TestCase):
    def test_generated_low_missing_f0_sweep_tapping(self):
        output=Path(os.environ['BASIC_PITCH_PILOT_OUTPUT']).absolute();output.mkdir(mode=0o700,parents=True)
        excerpts=[];truth=[]
        for case in ('low_c1','missing_fundamental','legato_sweep','polyphonic_tapping'):
            values=array.array('f');notes=[]
            for i in range(3*bp.RATE):
                t=i/bp.RATE
                if case in ('low_c1','missing_fundamental'):
                    midi=[24];fundamental=440*2**((24-69)/12)
                    harmonics=range(1 if case=='low_c1' else 2,9)
                    value=sum(math.sin(2*math.pi*fundamental*h*t)/h for h in harmonics)*.22
                else:
                    step=min(15,int(t/.1875));midi=[60+[0,3,7,12,15,19,24,19,15,12,7,3,0,7,12,19][step]]
                    if case=='polyphonic_tapping':midi.append(48)
                    value=sum(sum(math.sin(2*math.pi*440*2**((n-69)/12)*h*t)/h for h in range(1,5)) for n in midi)*.14
                edge=min(1,t/.02,(3-t)/.02)
                # Missing-F0 must remain linear: tanh intermodulation can regenerate C1.
                shaped=value if case=='missing_fundamental' else math.tanh(value*1.8)
                values.append(shaped*max(0,edge))
                if i%256==0:notes.append({'audio_relative_seconds':t,'midi_truth':midi})
            if sys.byteorder!='little':values.byteswap()
            path=output/(case+'.f32');path.write_bytes(values.tobytes())
            excerpts.append({'start_seconds':0.,'end_seconds':3.,'pcm_path':str(path),'pcm_sha256':bp.sha256(path),'sample_count':3*bp.RATE,'case_id':case})
            truth.append({'case_id':case,'generated_truth_points':notes,'labels_role':'evaluation_only_no_model_input','articulation_scope':'stepped phase-discontinuous harmonic proxy; not physical legato/sweep/tap validation'})
        task={'model_path':str(bp.LOCAL_MODEL),'output_dir':str(output),'source_audio_start_seconds':0.,'excerpts':excerpts,
              'setting_arguments':{'budget':12.,'start':None,'onset':.5,'frame':.3},'wheel_manifest_sha256':bp.sha256(bp.WHEEL_MANIFEST)}
        path=output/'task.json';path.write_text(json.dumps(task))
        bp.bounded_child([str(bp.RUNTIME.absolute()),str(ROOT/'scripts/basic_pitch_compare.py'),'--infer-task',str(path)],output,time.monotonic()+600)
        result=json.loads((output/'inference.json').read_text())
        self.assertEqual(result['model_windows'],8)
        self.assertLess(result['peak_rss_bytes'],1024**3)
        self.assertEqual(len(result['excerpts']),4)
        self.assertEqual(result['providers'],['CPUExecutionProvider'])
        (output/'generated-truth.json').write_text(json.dumps(truth,indent=2)+'\n')
        self.assertTrue(all(e['retained_frames']==258 for e in result['excerpts']))
        self.assertTrue(all(len(e['model_input_windows'])==2 for e in result['excerpts']))
        self.assertTrue(all(v['minimum_note_length_ms'] in (25.,127.7) for e in result['excerpts'] for v in e['variants']))
        diagnostic_code = """
from pathlib import Path
import json,sys,numpy as np
p=Path(sys.argv[1]);r=json.loads((p/'inference.json').read_text());truth=json.loads((p/'generated-truth.json').read_text());arrays=np.load(p/'activations.npz',allow_pickle=False);cases=[]
for i,e in enumerate(r['excerpts']):
    note=arrays[f'excerpt_{i}_note'];clock=arrays[f'excerpt_{i}_model_times_seconds'];top=note.argmax(axis=1)+21;active=note.max(axis=1)>=.3;labels=truth[i]['generated_truth_points'];hits=voiced=0;hist={}
    for t,n,v in zip(clock,top,active):
        k=min(len(labels)-1,max(0,int(round(t*22050/256))));hits+=bool(v and n in labels[k]['midi_truth']);voiced+=bool(v)
        if v:hist[str(n)]=hist.get(str(n),0)+1
    cases.append({'case_id':e['case_id'],'frames':len(note),'threshold_active_top_one_frames':voiced,'truth_membership_hits_all_frames':hits,'all_frame_truth_membership_fraction':hits/len(note),'active_top_one_midi_histogram':hist,'event_counts_by_floor_ms':{str(v['minimum_note_length_ms']):v['event_count'] for v in e['variants']}})
receipt={'schema_version':1,'cases':cases,'coverage_seconds':12,'model_windows':r['model_windows'],'peak_rss_bytes':r['peak_rss_bytes'],'top_one_rule':'highest note activation, lowest MIDI tie, threshold0.3; labels consulted after raw arrays persist','acceptance':'descriptive all-frame diagnostics, not native-context eligible musical accuracy','limitations':['Stepped phase-discontinuous harmonic proxies do not validate physical guitar articulation.','Missing-F0 input excludes fundamental and nonlinear distortion to avoid regenerating C1.','Full model support approximately2seconds; no pYIN eligibility reuse.']}
(p/'diagnostics.json').write_text(json.dumps(receipt,indent=2)+'\\n')
"""
        subprocess.run([str(bp.RUNTIME.absolute()),'-c',diagnostic_code,str(output)],check=True,timeout=30)
        diagnostics=json.loads((output/'diagnostics.json').read_text())
        self.assertEqual(len(diagnostics['cases']),4)
        self.assertTrue(all(c['frames']==258 and 0<=c['all_frame_truth_membership_fraction']<=1 for c in diagnostics['cases']))


if __name__=='__main__':unittest.main()
