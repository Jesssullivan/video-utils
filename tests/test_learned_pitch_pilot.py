"""Controller oracles use fabricated receipts; never model inference."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('learned_controller',ROOT/'scripts/learned_pitch_pilot.py')
pilot=importlib.util.module_from_spec(spec);spec.loader.exec_module(pilot)


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def put(path,value):path.write_text(json.dumps(value));return digest(path)


def fixture(directory):
    directory.mkdir(parents=True)
    jobs=[];old=[]
    for n,(case,component,budget) in enumerate(pilot.PLAN,1):
        count=(8 if n<=2 else 10)*48000
        source=directory/f'input-{n}.wav'
        with wave.open(str(source),'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(48000);wav.writeframes(b'\0\0'*count)
        sha=digest(source)
        jobs.append({'evaluation_case_id':case,'component':component,'opaque_discovery_id':f'job-{n:02}',
            'source_component_path':str(source),'input_sha256':sha,'native_bytes':source.stat().st_size,
            'native_sample_count':count,'native_channels':1,'native_sample_rate':48000,
            'requested_budget_seconds':budget,'requested_start_seconds':0,'expected_frames':budget*86,
            'expected_raw_numeric_bytes':budget*86*1792,
            'expected_model_windows':4 if budget==6 else 5,'truth_path':str(directory/f'truth-{n}.json'),
            'truth_sha256':'2'*64,'existing_pyin_pitch_sha256':'3'*64})
        old.append({'case_id':case,'component':component,'input_sha256':sha,
            'truth_sha256':'2'*64,'pitch_sha256':'3'*64})
    bank=directory/'fixtures.json';bank_sha=put(bank,{'schema_version':2,'suite':'technical-v2','case_count':12,'total_duration_seconds':120})
    pyin=directory/'pyin.json';pyin_sha=put(pyin,{'budget_seconds':30,'bank_index_sha256':bank_sha,'jobs':old})
    plan={'schema_version':1,'budget_seconds':30,'discovery_receives_truth':False,
        'expected_total_frames':2580,'expected_total_model_windows':19,'bank_index':str(bank),'bank_index_sha256':bank_sha,
        'pyin_pilot_index':str(pyin),'pyin_pilot_index_sha256':pyin_sha,
        'model_sha256':'1'*64,'runtime_manifest_sha256':'4'*64,'jobs':jobs,
        'settings':{'onset_threshold':.5,'frame_threshold':.3,'minimum_note_length_ms_presets':[127.7,25.],
            'worker_deadline_seconds':600,'controller_deadline_seconds':900,'root_inference_release_required':True,
            'controller_math_threads':2,'max_rss_bytes':1024**3,'max_model_windows':24,
            'max_raw_numeric_bytes':20*1024**2,'max_events_per_preset':5000}}
    for key,file in [('adapter_sha256','scripts/basic_pitch_compare.py'),('evaluator_sha256','scripts/learned_pitch_evaluate.py'),
                     ('instrument_registry_sha256','program/instrument.json'),('model_registry_sha256','program/models.json')]:
        plan[key]=digest(ROOT/file)
    path=directory/'plan.json';put(path,plan)
    return path,plan


class ControllerTests(unittest.TestCase):
    def setUp(self):
        pilot.base.ALLOWED.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='learned-controller-tests-',dir=pilot.base.ALLOWED)
        self.directory=Path(self.temp.name);self.path,self.plan=fixture(self.directory/'source')
    def tearDown(self):self.temp.cleanup()
    def prepare(self):return pilot.prepare(self.path,self.directory/'prepared')
    def release(self,prepared):
        path=self.directory/'release.json';put(path,{'inference_authorized':True,
            'preregistration_sha256':prepared['preregistration_sha256'],'controller_sha256':prepared['controller_sha256']})
        return path
    def fake(self,argv,directory,deadline):
        n=int(directory.name[-2:]);job=self.plan['jobs'][n-1]
        # Deliberately fabricated bounded receipt: no activation/model evaluation.
        self.assertNotIn(job['evaluation_case_id'],' '.join(argv));self.assertNotIn('truth',' '.join(argv))
        self.assertFalse((directory.parents[1]/'predictions-frozen.json').exists())
        raw=directory/'activations.npz';raw.write_bytes(b'constructed mock archive')
        path=directory/'comparison.json';put(path,{'raw_activations_sha256':digest(raw),
            'analysis_input_sha256':job['input_sha256'],'worker_sha256':self.plan['adapter_sha256'],
            'model_sha256':self.plan['model_sha256'],'wheel_manifest_sha256':self.plan['runtime_manifest_sha256'],
            'coverage_seconds':job['requested_budget_seconds'],'model_windows':job['expected_model_windows'],
            'raw_array_bytes':job['expected_raw_numeric_bytes'],'peak_rss_bytes':200_000_000,
            'excerpts':[{'retained_frames':job['expected_frames'],'variants':[
                {'minimum_note_length_ms':m,'event_count':0,'events':[]} for m in (127.7,25.)]}]})
        return {'comparison_json':str(path)}
    def test_prepare_preserves_bytes_and_withholds_truth_and_subprocess(self):
        before={p:digest(p) for p in (self.directory/'source').iterdir() if p.is_file()}
        with patch.object(pilot.subprocess,'Popen',side_effect=AssertionError('no subprocess permitted')):
            plan,receipt,output=self.prepare()
        self.assertFalse(receipt['inference_invoked']);self.assertFalse(receipt['truth_content_read'])
        for opaque,job in zip(receipt['jobs'],plan['jobs']):
            directory=Path(opaque['run_dir']);manifest=json.loads((directory/'manifest.json').read_text())
            self.assertEqual(digest(directory/'denoised.wav'),job['input_sha256'])
            self.assertEqual(manifest['source']['sha256'],job['input_sha256'])
            self.assertFalse(manifest['provenance']['denoising_performed'])
            self.assertEqual(manifest['timeline']['audio_start_seconds'],0)
            self.assertNotIn(job['evaluation_case_id'],json.dumps(manifest))
            self.assertNotIn('truth',json.dumps(manifest))
        self.assertEqual(before,{p:digest(p) for p in before})
    def test_default_cli_cannot_infer(self):
        result=subprocess.run([sys.executable,str(ROOT/'scripts/learned_pitch_pilot.py'),'--preregistration',str(self.path),
            '--output',str(self.directory/'cli'),'--summary'],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'],'prepared_no_inference')
    def test_execute_requires_exact_release(self):
        plan,receipt,output=self.prepare();release=self.release(receipt)
        value=json.loads(release.read_text());value['controller_sha256']='0'*64;put(release,value)
        with self.assertRaisesRegex(pilot.base.EvaluationError,'bound_inference_release'):
            pilot.execute(plan,receipt,output,release,runner=lambda *a:self.fail('must not launch'))
    def test_hash_freeze_precedes_truth_index_and_no_score_invocation(self):
        plan,receipt,output=self.prepare()
        identities=pilot.identities
        with patch.object(pilot,'identities',side_effect=lambda p,runtime=False:identities(p,False)):
            result=pilot.execute(plan,receipt,output,self.release(receipt),runner=self.fake)
        frozen=json.loads((output/'predictions-frozen.json').read_text())
        index=json.loads((output/'learned-pilot-index.json').read_text())
        self.assertEqual(index['predictions_frozen_sha256'],digest(output/'predictions-frozen.json'))
        self.assertFalse(frozen['truth_content_read']);self.assertEqual(len(index['jobs']),4)
        self.assertFalse(any(output.glob('*evaluation*')));self.assertEqual(result['coverage_seconds'],30)
    def test_failure_retains_prior_predictions_no_complete_index(self):
        plan,receipt,output=self.prepare();calls=[];identities=pilot.identities
        def runner(*args):
            calls.append(1)
            if len(calls)==2:raise pilot.base.EvaluationError('mock_failure')
            return self.fake(*args)
        with patch.object(pilot,'identities',side_effect=lambda p,runtime=False:identities(p,False)):
            with self.assertRaisesRegex(pilot.base.EvaluationError,'mock_failure'):
                pilot.execute(plan,receipt,output,self.release(receipt),runner=runner)
        self.assertTrue((output/'prediction-job-01.json').exists())
        self.assertFalse((output/'predictions-frozen.json').exists());self.assertFalse((output/'learned-pilot-index.json').exists())
    def test_altered_source_and_symlink_rejected(self):
        source=Path(self.plan['jobs'][0]['source_component_path']);source.write_bytes(source.read_bytes()+b'x')
        with self.assertRaisesRegex(pilot.base.EvaluationError,'sha256_mismatch'):self.prepare()
        other=self.directory/'alias.json';other.symlink_to(self.path)
        with self.assertRaisesRegex(pilot.base.EvaluationError,'symlink_path'):pilot.repo_json(other)
    def test_fixed_settings_and_nonfinite_metadata_rejected(self):
        self.plan['settings']['frame_threshold']=.2;put(self.path,self.plan)
        with self.assertRaisesRegex(pilot.base.EvaluationError,'fixed_settings'):self.prepare()
        self.path.write_text('{"x":1e400}')
        with self.assertRaises(ValueError):pilot.repo_json(self.path)
        self.path.write_text('{"x":'+('['*129)+'0'+(']'*129)+'}')
        with self.assertRaisesRegex(pilot.base.EvaluationError,'json_depth_bound'):pilot.repo_json(self.path)
    def test_owned_timeout_reaps_only_spawned_child(self):
        directory=self.directory/'child';directory.mkdir()
        with self.assertRaisesRegex(TimeoutError,'controller_deadline'):
            pilot.run_owned([sys.executable,'-c','import time;time.sleep(5)'],directory,time.monotonic()+.1)
        receipt=json.loads((directory/'signal-receipt.json').read_text())
        self.assertEqual(receipt['result'],'signalled and reaped')
    def test_failed_leader_cleans_owned_live_descendant(self):
        directory=self.directory/'orphan';directory.mkdir()
        script='import subprocess,sys;subprocess.Popen([sys.executable,"-c","import time;time.sleep(10)"]);sys.exit(4)'
        with self.assertRaisesRegex(pilot.base.EvaluationError,'discovery_worker_failed'):
            pilot.run_owned([sys.executable,'-c',script],directory,time.monotonic()+5)
        receipt=json.loads((directory/'signal-receipt.json').read_text())
        self.assertEqual(receipt['result'],'signalled and reaped')
    def test_plan_drift_blocks_discovery(self):
        plan,receipt,output=self.prepare();release=self.release(receipt)
        self.path.write_text(self.path.read_text()+' ')
        with self.assertRaisesRegex(pilot.base.EvaluationError,'sha256_mismatch'):
            pilot.execute(plan,receipt,output,release,runner=lambda *a:self.fail('must not launch'))
    def test_partial_preparation_retains_failure_without_inference(self):
        source=Path(self.plan['jobs'][1]['source_component_path']);source.write_bytes(b'bad')
        with self.assertRaisesRegex(pilot.base.EvaluationError,'sha256_mismatch'):self.prepare()
        path=self.directory/'prepared'/'preparation-failure.json'
        self.assertFalse(json.loads(path.read_text())['inference_invoked'])
        self.assertTrue((self.directory/'prepared'/'discovery'/'job-01'/'manifest.json').exists())
    def test_insufficient_global_budget_does_not_launch(self):
        plan,receipt,output=self.prepare();identities=pilot.identities
        with patch.object(pilot,'identities',side_effect=lambda p,runtime=False:identities(p,False)):
            with self.assertRaisesRegex(pilot.base.EvaluationError,'insufficient_remaining'):
                pilot.execute(plan,receipt,output,self.release(receipt),runner=lambda *a:self.fail('must not launch'),
                              deadline=time.monotonic()+10)
    def test_oversized_prediction_resource_rejected_before_freeze(self):
        plan,receipt,output=self.prepare();identities=pilot.identities
        def invalid(*args):
            result=self.fake(*args);path=Path(result['comparison_json']);value=json.loads(path.read_text())
            value['raw_array_bytes']=20*1024**2+1;put(path,value);return result
        with patch.object(pilot,'identities',side_effect=lambda p,runtime=False:identities(p,False)):
            with self.assertRaisesRegex(pilot.base.EvaluationError,'prediction_resource_bound'):
                pilot.execute(plan,receipt,output,self.release(receipt),runner=invalid)
        self.assertFalse((output/'predictions-frozen.json').exists())
    def test_existing_output_is_preserved(self):
        directory=self.directory/'prepared';directory.mkdir();sentinel=directory/'keep';sentinel.write_text('owned elsewhere')
        with self.assertRaisesRegex(pilot.base.EvaluationError,'fresh_output'):self.prepare()
        self.assertEqual(sentinel.read_text(),'owned elsewhere')


if __name__=='__main__':unittest.main()
