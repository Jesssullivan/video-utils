"""Demo workflow order, exact receipt selection and bounded process ownership."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('demo_worker', REPO / 'scripts/run_demo.py')
demo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(demo)


class DemoWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.directory = self.root / 'artifacts/runs/take'
        self.directory.mkdir(parents=True)
        self.source = self.root / 'original.mov'
        self.source.write_bytes(b'original private source')
        for name in ('denoised.wav', 'cleaned.wav'):
            (self.directory / name).write_bytes(name.encode())
        self.manifest = {'schema_version': 1, 'run_dir': str(self.directory),
                         'source': {'path': str(self.source), 'sha256': demo.sha256(self.source)},
                         'output_sha256': {name: demo.sha256(self.directory / name) for name in ('denoised.wav', 'cleaned.wav')},
                         'pcm': {'sample_rate': 44100, 'channels': 1, 'sample_count': 100}}
        (self.directory / 'manifest.json').write_text(json.dumps(self.manifest))
        self.root_patch = patch.object(demo, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.calls = []
        self.fail = set()
        self.mutate = None
        self.reject_slot = None

    def fake_invoke(self, script, arguments, timeout=1200, interpreter=None, execution=None):
        name = script.removesuffix('.py')
        if name == 'media':
            name = 'media' if arguments[0] == 'clean' else 'export'
        if name == 'guitar_features':
            name = arguments[0]
        if name == 'phrase_compare':
            name = 'comparisons'
        self.calls.append((name, arguments, interpreter))
        if execution is not None:
            execution.update(status='completed', mocked_execution=True)
        if name in self.fail:
            raise demo.StageError(f'{name} fixture failure', {'status': 'failed', 'fixture': True})
        if self.mutate and name == self.mutate:
            (self.directory / 'denoised.wav').write_bytes(b'modified by faulty worker')
        if name == 'media':
            return self.manifest
        if name == 'export':
            return {'video': None}
        if name == 'dag':
            rows = {}
            for slot in demo.OPTIONAL_OUTPUTS:
                flag = '--' + slot + '-artifact'
                selected = arguments[arguments.index(flag)+1] if flag in arguments else None
                rows[slot] = ({'status': 'verified', 'selector': selected,
                               'artifact_sha256': demo.sha256(self.directory / selected)} if selected else
                              {'status': 'not_selected', 'selector': None, 'artifact_sha256': None})
            if self.reject_slot is not None:
                rows[self.reject_slot]['status'] = 'rejected_fixture_provenance'
            path = self.directory / 'dag.json'
            path.write_text(json.dumps({'selected_evidence': rows}))
            return {'dag_json': str(path)}
        if name in demo.OPTIONAL_OUTPUTS:
            key, _ = demo.OPTIONAL_OUTPUTS[name]
            relative = {'clicks': 'clicks/explicit-older/clicks.json', 'pitch': 'pitch.json',
                        'meter': 'meter/explicit-older/meter.json', 'tonal': 'tonal/tonal.json',
                        'comparisons': 'phrase-comparisons.json'}[name]
            path = self.directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({'tool': name, 'tonic': None, 'performance_grade': 'not_graded'}))
            return {key: str(path), 'sha256': demo.sha256(path)}
        return {'status': 'unreviewed', 'tonic': None}

    def run_workflow(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(demo, 'invoke', side_effect=self.fake_invoke), patch.object(demo, 'verify_pcm'), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = demo.main(arguments)
        return status, json.loads(stdout.getvalue()) if stdout.getvalue() else None, stderr.getvalue()

    def test_default_input_mode_remains_base_and_preserves_failed_analysis_receipt(self):
        self.fail.add('notes')
        status, result, _ = self.run_workflow([str(self.source)])
        self.assertEqual(status, 0)  # Existing default behavior: optional candidate failure is retained.
        self.assertEqual([row[0] for row in self.calls],
                         ['media', 'export', 'rhythm', 'noise', 'tone', 'notes', 'phrases', 'dag', 'markers', 'report'])
        receipt = json.loads(Path(result['demo_receipt']).read_text())
        self.assertEqual(receipt['analysis_settings']['features'], 'base')
        self.assertEqual(receipt['stages']['notes']['status'], 'failed')
        self.assertTrue(receipt['stages']['notes']['execution']['fixture'])
        self.assertEqual(receipt['selected_evidence'], {})
        self.assertFalse(receipt['listening_accepted'])
        self.assertEqual(demo.sha256(self.directory / 'cleaned.wav'), self.manifest['output_sha256']['cleaned.wav'])

    def test_extended_existing_order_exact_receipts_and_explicit_interpreter(self):
        # Newer-looking artifacts must not be discovered or substituted.
        wrong = self.directory / 'clicks/newest/clicks.json'
        wrong.parent.mkdir(parents=True)
        wrong.write_text('{"wrong":true}')
        (self.directory / 'demo.json').write_text('{"status":"prior_unreviewed"}')
        status, result, _ = self.run_workflow(['--existing-run', str(self.directory), '--features', 'extended',
                                             '--backend', 'librosa', '--bpm', '178',
                                             '--analysis-python', '/explicit/analysis-python', '--pitch-seconds', '3'])
        self.assertEqual(status, 0)
        self.assertEqual([row[0] for row in self.calls],
                         ['rhythm', 'noise', 'tone', 'notes', 'phrases', 'clicks', 'pitch', 'meter', 'tonal', 'comparisons', 'dag', 'markers', 'report'])
        self.assertEqual(result['selected_evidence']['clicks']['selector'], 'clicks/explicit-older/clicks.json')
        self.assertEqual(result['selected_evidence']['meter']['selector'], 'meter/explicit-older/meter.json')
        dag_args = next(row[1] for row in self.calls if row[0] == 'dag')
        for slot, evidence in result['selected_evidence'].items():
            self.assertIn('--' + slot + '-artifact', dag_args)
            self.assertIn(evidence['selector'], dag_args)
        for name, args, interpreter in self.calls:
            if name in {'rhythm', 'phrases', 'clicks', 'pitch'}:
                self.assertEqual(interpreter, '/explicit/analysis-python')
            if name == 'pitch':
                self.assertIn('3.0', args)
        receipt_path = Path(result['demo_receipt'])
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt['mode'], 'existing_run')
        self.assertFalse(receipt['stages']['media']['media_rerendered'])
        self.assertEqual(json.loads((receipt_path.parent / 'prior-demo.json').read_text())['status'], 'prior_unreviewed')
        self.assertIsNone(receipt['stages']['tonal']['result'].get('tonic'))

    def test_failed_current_pitch_omits_selector_and_skips_old_pitch_tonal_use(self):
        (self.directory / 'pitch.json').write_text('{"old_pitch":true}')
        self.fail.add('pitch')
        status, result, _ = self.run_workflow(['--existing-run', str(self.directory), '--features', 'extended'])
        self.assertEqual(status, 1)
        self.assertNotIn('pitch', result['selected_evidence'])
        self.assertNotIn('tonal', result['selected_evidence'])
        self.assertNotIn('tonal', [row[0] for row in self.calls])
        self.assertEqual(result['stage_status']['tonal'], 'skipped_dependency_failed')
        dag_args = next(row[1] for row in self.calls if row[0] == 'dag')
        self.assertNotIn('--pitch-artifact', dag_args)
        self.assertNotIn('--tonal-artifact', dag_args)
        self.assertFalse((self.directory / 'pitch.json').exists())
        receipt = json.loads(Path(result['demo_receipt']).read_text())
        history = self.directory / receipt['prior_artifact_snapshot']['path']
        self.assertEqual((history / 'pitch.json').read_text(), '{"old_pitch":true}')

    def test_snapshot_preserves_prior_analysis_and_pitch_before_successful_overwrite(self):
        before = {'analysis.json': b'{"old_analysis":true}', 'pitch.json': b'{"old_pitch":true}',
                  'report.html': b'previous report', 'dag.json': b'{"old_graph":true}'}
        for name, content in before.items():
            (self.directory / name).write_bytes(content)
        status, result, _ = self.run_workflow(['--existing-run', str(self.directory), '--features', 'extended'])
        self.assertEqual(status, 0)
        receipt = json.loads(Path(result['demo_receipt']).read_text())
        history = self.directory / receipt['prior_artifact_snapshot']['path']
        for name, content in before.items():
            self.assertEqual((history / name).read_bytes(), content)
        self.assertFalse(receipt['prior_artifact_snapshot']['media_copied'])
        self.assertFalse((history / 'denoised.wav').exists())
        self.assertNotEqual((self.directory / 'pitch.json').read_bytes(), before['pitch.json'])

    def test_snapshot_cap_and_symlink_fail_without_mutating_existing_run(self):
        prior = self.directory / 'demo.json'
        prior.write_bytes(b'{"prior":true}')
        pitch = self.directory / 'pitch.json'
        pitch.write_bytes(b'xxxxxxxxx')
        with patch.object(demo, 'MAX_HISTORY_FILE_BYTES', 8):
            status, _, error = self.run_workflow(['--existing-run', str(self.directory)])
        self.assertEqual(status, 1)
        self.assertEqual(self.calls, [])
        self.assertIn('snapshot', error)
        self.assertEqual(prior.read_bytes(), b'{"prior":true}')
        pitch.unlink()
        pitch.symlink_to(self.source)
        status, _, error = self.run_workflow(['--existing-run', str(self.directory)])
        self.assertEqual(status, 1)
        self.assertEqual(self.calls, [])
        self.assertIn('symlink', error)
        self.assertEqual(prior.read_bytes(), b'{"prior":true}')

    def test_failed_rhythm_does_not_reuse_old_graph_for_new_markers(self):
        self.fail.add('rhythm')
        status, result, _ = self.run_workflow(['--existing-run', str(self.directory), '--features', 'extended'])
        self.assertEqual(status, 1)
        self.assertNotIn('dag', [row[0] for row in self.calls])
        self.assertNotIn('markers', [row[0] for row in self.calls])
        self.assertEqual(result['stage_status']['dag'], 'skipped_dependency_failed')
        self.assertIn('report', [row[0] for row in self.calls])

    def test_rejected_current_graph_evidence_is_not_reported_as_complete_workflow(self):
        self.reject_slot = 'pitch'
        status, result, _ = self.run_workflow(['--existing-run', str(self.directory), '--features', 'extended'])
        self.assertEqual(status, 1)
        self.assertEqual(result['stage_status']['dag'], 'failed')
        self.assertEqual(result['stage_status']['markers'], 'skipped_dependency_failed')
        receipt = json.loads(Path(result['demo_receipt']).read_text())
        self.assertIn('current exact pitch receipt', receipt['stages']['dag']['reason'])

    def test_tampered_existing_media_rejected_before_worker_and_prior_receipt_preserved(self):
        (self.directory / 'demo.json').write_text('{"prior":true}')
        (self.directory / 'denoised.wav').write_bytes(b'tampered')
        status, result, error = self.run_workflow(['--existing-run', str(self.directory), '--features', 'extended'])
        self.assertEqual(status, 1)
        self.assertIsNone(result)
        self.assertEqual(self.calls, [])
        self.assertIn('hash', error)
        self.assertEqual((self.directory / 'demo.json').read_text(), '{"prior":true}')

    def test_worker_media_modification_fails_final_identity_check(self):
        self.mutate = 'report'
        status, result, error = self.run_workflow(['--existing-run', str(self.directory)])
        self.assertEqual(status, 1)
        self.assertIsNone(result)
        self.assertIn('hash', error)
        receipt = json.loads((self.directory / 'demo.json').read_text())
        self.assertEqual(receipt['status'], 'failed_preserving_media')
        self.assertFalse((self.root / 'artifacts/latest.json').exists())

    def test_no_latest_preserves_operator_pointer(self):
        pointer = self.root / 'artifacts/latest.json'
        pointer.write_bytes(b'{"run_dir":"operator-demo"}')
        status, _, _ = self.run_workflow(['--existing-run', str(self.directory), '--no-latest'])
        self.assertEqual(status, 0)
        self.assertEqual(pointer.read_bytes(), b'{"run_dir":"operator-demo"}')

    def test_existing_delivery_is_hash_verified_and_returned_without_encoding(self):
        export = self.directory / 'export'
        export.mkdir()
        video = export / 'cleaned-video.mov'
        video.write_bytes(b'existing encoded delivery fixture')
        outcome = {'video': str(video), 'source_sha256': self.manifest['source']['sha256'],
                   'output_sha256': {'cleaned-video.mov': demo.sha256(video)},
                   'verification': {'final_true_peak_within_target': True}}
        (export / 'outcome.json').write_text(json.dumps(outcome))
        status, result, _ = self.run_workflow(['--existing-run', str(self.directory)])
        self.assertEqual(status, 0)
        self.assertEqual(result['video'], str(video))
        self.assertNotIn('export', [row[0] for row in self.calls])
        self.assertEqual(video.read_bytes(), b'existing encoded delivery fixture')

    def test_selector_rejects_external_traversal_and_symlink_receipts(self):
        outside = self.root / 'external.json'
        outside.write_text('{}')
        alias = self.directory / 'alias.json'
        alias.symlink_to(outside)
        for returned in (str(outside), str(alias), str(self.directory / 'a/../pitch.json'), 'pitch.json'):
            with self.subTest(returned=returned), self.assertRaises(ValueError):
                demo.exact_selector(self.directory, returned)


class BoundedInvocationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        (self.root / 'scripts').mkdir()
        self.root_patch = patch.object(demo, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def worker(self, text, timeout=2):
        (self.root / 'scripts/fixture.py').write_text(text)
        return demo.invoke('fixture.py', [], timeout)

    def test_finite_single_object_and_bad_worker_results(self):
        self.assertEqual(self.worker('print(\'{"mode":null}\')'), {'mode': None})
        for code in ["print('[]')", "print('{\"value\":NaN}')", "print('{\"value\":1e999}')", "print('debug');print('{}')"]:
            with self.subTest(code=code), self.assertRaises(demo.StageError):
                self.worker(code)

    def test_output_limit_actively_stops_worker(self):
        with self.assertRaises(demo.StageError) as caught:
            self.worker("import sys,time\nsys.stdout.write('x'*(3*1024*1024));sys.stdout.flush();time.sleep(30)")
        receipt = caught.exception.receipt
        self.assertLessEqual(receipt['stdout_bytes'], demo.MAX_OUTPUT_BYTES)
        self.assertEqual(receipt['process_escape_hatch']['result']['signal_target'], 'owned_process_group')
        self.assertIn('R-N11', receipt['process_escape_hatch']['ruling'])

    def test_deadline_stops_recorded_descendant_group_even_after_leader_exits(self):
        late = self.root / 'late.txt'
        child = self.root / 'scripts/child.py'
        child.write_text('import time\nfrom pathlib import Path\ntime.sleep(.6)\nPath(' + repr(str(late)) + ').write_text("escaped")\n')
        with self.assertRaises(demo.StageError) as caught:
            self.worker('import subprocess,sys\nsubprocess.Popen([sys.executable,' + repr(str(child)) + '])\n', .15)
        escape = caught.exception.receipt['process_escape_hatch']
        self.assertTrue(escape['target_ownership']['created_by_invocation'])
        self.assertEqual(escape['target_ownership']['observed_pgid'], escape['target_ownership']['pid'])
        time.sleep(.7)
        self.assertFalse(late.exists())


if __name__ == '__main__':
    unittest.main()
