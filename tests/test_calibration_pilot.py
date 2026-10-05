"""Generated-bank orchestration contracts; toy outputs are not DSP calibration."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('calibration_pilot_tests', REPO / 'scripts/calibration_pilot.py')
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)
SECRET = 'TRUTH_SECRET_WARP_SCORE_98765'


class CalibrationPilotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.bank_dir = self.root / 'artifacts/benchmarks/bank'
        self.bank_dir.mkdir(parents=True)
        (self.root / 'program').mkdir()
        registry = self.root / 'program/instrument.json'
        registry.write_bytes((REPO / 'program/instrument.json').read_bytes())
        self.registry_hash = pilot.digest(registry)
        (self.root / 'scripts').mkdir()
        for name in pilot.SOURCES:
            (self.root / 'scripts' / name).write_text('# bounded toy worker ' + name + '\n')
        cases = []
        for position, (case_id, duration) in enumerate(zip(pilot.CASE_IDS, pilot.DURATIONS)):
            directory = self.bank_dir / case_id
            directory.mkdir()
            audio = directory / 'mix.wav'
            with wave.open(str(audio), 'wb') as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(48000)
                handle.writeframes((position + 1).to_bytes(2, 'little') * (duration * 48000))
            artifact = {'path': audio.relative_to(self.bank_dir).as_posix(),
                        'sha256': pilot.digest(audio), 'bytes': audio.stat().st_size}
            truth = {'schema_version': 2, 'id': case_id, 'instrument_registry_sha256': self.registry_hash,
                     'source': {**artifact, 'sample_rate': 48000, 'channels': 1, 'sample_count': duration*48000,
                                'duration_seconds': duration, 'audio_start_seconds': 0,
                                'origin_evidence': 'synthetic_generator_sample_zero'},
                     'artifacts': {'mix': artifact, 'clean': artifact},
                     'score': {'canary': SECRET, 'warp': [999, -500]}}
            truth_path = directory / 'truth.json'
            truth_path.write_text(json.dumps(truth))
            cases.append({'id': case_id, 'duration_seconds': duration,
                          'truth': truth_path.relative_to(self.bank_dir).as_posix(),
                          'truth_sha256': pilot.digest(truth_path)})
        self.index = self.bank_dir / 'fixtures.json'
        self.index.write_text(json.dumps({'schema_version': 2, 'suite': 'technical-v2', 'case_count': 12,
                                         'total_duration_seconds': 120, 'instrument_registry_sha256': self.registry_hash,
                                         'cases': cases}))
        self.output = self.root / 'artifacts/benchmarks/pilot'
        for module in (pilot, pilot.workflow):
            handle = patch.object(module, 'ROOT', self.root)
            handle.start()
            self.addCleanup(handle.stop)
        self.calls = []
        self.failed_script = None
        self.wrong_path = False
        self.hard_fail = False
        self.mutate_alias = False

    def fake_invoke(self, script, arguments, timeout=1200, interpreter=None, execution=None):
        self.calls.append((script, list(arguments), dict(os.environ), timeout, interpreter))
        execution.update(command=[interpreter or sys.executable, str(self.root/'scripts'/script), *arguments],
                         worker_sha256=pilot.digest(self.root/'scripts'/script), elapsed_seconds=.01, status='completed')
        if self.failed_script == script:
            self.failed_script = None
            raise pilot.workflow.StageError('deliberate fixture failure', dict(execution, status='failed'))
        if script.endswith('_evaluate.py'):
            directory = Path(arguments[arguments.index('--output')+1])
            directory.mkdir()
            path = directory / ('phrase-evaluation.json' if script == 'phrase_evaluate.py' else 'pitch-calibration.json')
            index = Path(arguments[arguments.index('--pilot-index')+1])
            result = {'status': 'generated_fixture_calibration' if not self.hard_fail else 'generated_fixture_calibration_failed_hard_gates',
                      'hard_gates_passed': not self.hard_fail, 'bank_index_sha256': pilot.digest(self.index),
                      'pilot_index_sha256': pilot.digest(index)}
            path.write_text(json.dumps(result))
            if self.hard_fail:
                raise pilot.workflow.StageError('hard gates failed', dict(execution, status='failed', exit_code=1))
            return {'evaluation_json': str(path), **result}
        directory = Path(arguments[arguments.index('--run-dir')+1]) if '--run-dir' in arguments else Path(arguments[0])
        manifest = json.loads((directory/'manifest.json').read_text())
        source_hash = manifest['source']['sha256']
        payload = {'source': manifest['source'], 'analysis': {}, 'settings': {'mock': True}}
        if script == 'rhythm.py':
            path = directory/'analysis.json'
            path.write_text(json.dumps(payload))
            if self.wrong_path:
                return {'analysis_json': str(self.index)}
            return {'analysis_json': str(path)}
        if script == 'guitar_features.py':
            (directory/'phrases.json').write_text(json.dumps(payload))
            return payload
        if script == 'phrase_compare.py':
            payload.update(analysis_input_sha256=source_hash, source_sha256=source_hash)
            path = directory/'phrase-comparisons.json'
            path.write_text(json.dumps(payload))
            return {'comparisons_json': str(path)}
        if script == 'pitch.py':
            budget = float(arguments[arguments.index('--max-analysis-seconds')+1])
            payload.update(provenance={'worker_sha256': execution['worker_sha256'], 'python_version': sys.version.split()[0]},
                           analysis={'coverage_spans_audio_relative': [{'start_seconds': 0., 'end_seconds': budget}]},
                           observations={'analyzed_excerpts': [{'versions': {'librosa': 'toy', 'numpy': 'toy'}}]})
            path = directory/'pitch.json'
            path.write_text(json.dumps(payload))
            if self.mutate_alias:
                Path(manifest['source']['path']).write_bytes(b'changed by faulty worker')
            return {'pitch_json': str(path)}
        self.fail('Unexpected script ' + script)

    def run_mock(self):
        with patch.object(pilot.workflow, 'invoke', side_effect=self.fake_invoke), patch.dict(os.environ, {SECRET: SECRET}):
            return pilot.run_pilot(self.index, self.output, sys.executable)

    def test_complete_order_exact_indexes_truth_isolation_and_preservation(self):
        result = self.run_mock()
        self.assertEqual(result['status'], 'completed_generated_calibration_pilot')
        self.assertTrue(result['original_input_hashes_preserved'])
        self.assertTrue(result['discovery_alias_hashes_preserved'])
        self.assertEqual([row[0] for row in self.calls[:36]], ['rhythm.py', 'guitar_features.py', 'phrase_compare.py']*12)
        self.assertEqual([row[0] for row in self.calls[36:]], ['pitch.py']*4+['phrase_evaluate.py','pitch_evaluate.py'])
        self.assertTrue(all(0 < row[3] <= 240 for row in self.calls))
        for script, argv, environment, _, _ in self.calls[:40]:
            self.assertNotIn('--bpm', argv)
            self.assertNotIn('--fixture-index', argv)
            self.assertNotIn(SECRET, environment)
            self.assertFalse(any(case_id in arg for arg in argv for case_id in pilot.CASE_IDS))
            self.assertNotIn(SECRET, json.dumps(argv))
        for manifest in (self.output/'discovery').glob('*/manifest.json'):
            self.assertNotIn(SECRET, manifest.read_text())
            self.assertNotIn('score', manifest.read_text())
        jobs = json.loads((self.output/'pitch-pilot-index.json').read_text())['jobs']
        self.assertEqual([(j['case_id'],j['component'],j['requested_budget_seconds']) for j in jobs], list(pilot.PITCH_PLAN))
        self.assertEqual(sum(j['requested_budget_seconds'] for j in jobs),30)
        self.assertEqual(len(json.loads((self.output/'phrase-pilot-index.json').read_text())['cases']),12)
        self.assertFalse((self.root/'artifacts/latest').exists())
        for row in result['evaluations'].values():
            self.assertEqual(pilot.digest(self.output/row['artifact']['path']),row['artifact']['sha256'])

    def test_failed_dependency_skips_incomplete_phrase_evaluation_retains_receipts(self):
        self.failed_script = 'rhythm.py'
        result = self.run_mock()
        self.assertEqual(result['status'],'partial_calibration_pilot')
        self.assertEqual(result['cases'][0]['stages']['rhythm']['status'],'failed')
        self.assertNotIn('phrases',result['cases'][0]['stages'])
        self.assertEqual(result['evaluations']['phrases']['status'],'skipped_incomplete_discovery')
        self.assertFalse(any(row[0]=='phrase_evaluate.py' for row in self.calls))
        self.assertEqual(len(result['pitch_jobs']),4)
        self.assertTrue((self.output/'pilot.json').exists())

    def test_comparison_failure_is_nullable_and_not_promoted(self):
        self.failed_script = 'phrase_compare.py'
        result = self.run_mock()
        cases=json.loads((self.output/'phrase-pilot-index.json').read_text())['cases']
        self.assertIsNone(cases[0]['comparisons'])
        self.assertEqual(result['status'],'partial_calibration_pilot')
        self.assertEqual(result['evaluations']['phrases']['status'],'completed_generated_reference_evaluation')

    def test_hard_gate_failure_keeps_exact_evaluator_receipt(self):
        self.hard_fail=True
        result=self.run_mock()
        self.assertEqual(result['status'],'partial_calibration_pilot')
        for row in result['evaluations'].values():
            self.assertEqual(row['status'],'failed')
            self.assertFalse(row['artifact']['hard_gates_passed'])
            self.assertEqual(pilot.digest(self.output/row['artifact']['path']),row['artifact']['sha256'])

    def test_wrong_explicit_receipt_is_rejected_without_scanning(self):
        self.wrong_path=True
        result=self.run_mock()
        self.assertEqual(result['status'],'partial_calibration_pilot')
        self.assertEqual(len(json.loads((self.output/'phrase-pilot-index.json').read_text())['cases']),0)
        self.assertFalse(any(row[0]=='guitar_features.py' for row in self.calls))

    def test_tampered_bank_fails_before_output_or_discovery(self):
        audio=self.bank_dir/pilot.CASE_IDS[0]/'mix.wav'
        with audio.open('ab') as handle:
            handle.write(b'bad')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):
            self.run_mock()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.calls)

    def test_existing_output_and_symlink_are_rejected(self):
        self.output.mkdir()
        sentinel=self.output/'keep'
        sentinel.write_bytes(b'preserve')
        with self.assertRaisesRegex(ValueError,'Output must be new'):
            self.run_mock()
        self.assertEqual(sentinel.read_bytes(),b'preserve')
        alias=self.bank_dir/'alias.json'
        alias.symlink_to(self.index)
        with self.assertRaisesRegex(ValueError,'symlink'):
            pilot.local_path(alias)
        with self.assertRaises(ValueError):
            pilot.local_path('../outside.json',self.bank_dir)

    def test_modified_alias_is_explicit_failure(self):
        self.mutate_alias=True
        result=self.run_mock()
        self.assertEqual(result['status'],'partial_calibration_pilot')
        self.assertFalse(result['discovery_alias_hashes_preserved'])
        self.assertTrue(result['original_input_hashes_preserved'])

    def test_deadline_retains_skipped_jobs_without_invoking_worker(self):
        with patch.object(pilot.time,'monotonic',side_effect=[0]+[1000]*1000):
            result=self.run_mock()
        self.assertEqual(result['status'],'partial_calibration_pilot')
        self.assertFalse(self.calls)
        self.assertEqual(len(result['cases']),12)
        self.assertEqual(len(result['pitch_jobs']),4)

    def test_real_bounded_child_receives_only_operational_environment(self):
        worker=self.root/'scripts/rhythm.py'
        worker.write_text('import json,os\nprint(json.dumps({"keys":sorted(os.environ),"threads":os.environ.get("OPENBLAS_NUM_THREADS")}))\n')
        execution={}
        with patch.dict(os.environ,{SECRET:SECRET}):
            with pilot.operational_environment():
                result=pilot.workflow.invoke('rhythm.py',[],5,sys.executable,execution)
            self.assertEqual(os.environ[SECRET],SECRET)
        self.assertNotIn(SECRET,result['keys'])
        self.assertEqual(result['threads'],'2')
        self.assertEqual(execution['worker_sha256'],pilot.digest(worker))
        self.assertLessEqual(execution['stdout_bytes'],2*1024*1024)


if __name__=='__main__':
    unittest.main()
