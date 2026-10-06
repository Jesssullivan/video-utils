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

    def fake_invoke(self, script, arguments, timeout=1200, interpreter=None, execution=None, on_started=None):
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
        # Explicit conservative3: the default fuller profile requires a reviewed capture interval.
        status, result, _ = self.run_workflow([str(self.source), '--profile', 'conservative3'])
        self.assertEqual(status, 0)  # Existing default behavior: optional candidate failure is retained.
        self.assertEqual([row[0] for row in self.calls],
                         ['media', 'export', 'rhythm', 'noise', 'tone', 'notes', 'phrases', 'dag', 'markers', 'report'])
        self.assertEqual(self.calls[0][1], ['clean', str(self.source), 'conservative3'])
        receipt = json.loads(Path(result['demo_receipt']).read_text())
        self.assertEqual(receipt['analysis_settings']['features'], 'base')
        self.assertEqual(receipt['stages']['notes']['status'], 'failed')
        self.assertTrue(receipt['stages']['notes']['execution']['fixture'])
        self.assertEqual(receipt['selected_evidence'], {})
        self.assertFalse(receipt['listening_accepted'])
        self.assertEqual(demo.sha256(self.directory / 'cleaned.wav'), self.manifest['output_sha256']['cleaned.wav'])

    def install_fuller_profile(self):
        (self.root / 'profiles').mkdir(exist_ok=True)
        shutil.copyfile(REPO / 'profiles/fuller.json', self.root / 'profiles/fuller.json')

    def test_default_fuller_without_interval_refuses_typed_before_any_stage_or_receipt(self):
        self.install_fuller_profile()
        self.assertEqual(demo.DEFAULT_PROFILE, 'fuller')
        before = sorted(path.relative_to(self.root) for path in self.root.rglob('*'))
        status, result, error = self.run_workflow([str(self.source)])
        self.assertEqual((status, result), (1, None))
        payload = json.loads(error)
        self.assertEqual((payload['status'], payload['reason']), ('error', 'capture_interval_required'))
        self.assertIn('--capture-interval START END', payload['message'])
        self.assertIn('--profile conservative3', payload['message'])
        self.assertEqual(self.calls, [])
        self.assertEqual(sorted(path.relative_to(self.root) for path in self.root.rglob('*')), before)

    def test_default_fuller_with_reviewed_interval_passes_binding_to_media(self):
        self.install_fuller_profile()
        status, _, _ = self.run_workflow([str(self.source), '--capture-interval', '4.1', '4.95',
                                          '--capture-review', 'operator reviewed opening interval'])
        self.assertEqual(status, 0)
        self.assertEqual(self.calls[0][1], ['clean', str(self.source), 'fuller', '--capture-interval', '4.1', '4.95',
                                            '--capture-review', 'operator reviewed opening interval'])

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



# --- S2 robustness lane (TIN-5609): --resume crash recovery. ---------------------------------
# Contract: docs/spec/sprints/ROBUSTNESS_S2.md §3 and §5 tests 1-12. Temporary roots live under
# the gitignored artifacts/s2/robustness/ and are retained (path attached) only on failure.

import functools
import signal
import subprocess

LANE_ARTIFACTS = REPO / 'artifacts' / 's2' / 'robustness'
STUB_WORKERS = ('media.py', 'rhythm.py', 'guitar_features.py', 'clicks.py', 'pitch.py', 'meter.py',
                'tonal.py', 'phrase_compare.py', 'dag.py', 'markers.py', 'report.py')
BASE_ORDER = ['media', 'export', 'rhythm', 'noise', 'tone', 'notes', 'phrases', 'dag', 'markers', 'report']


class SimulatedOrchestratorDeath(BaseException):
    """Not caught by run_demo.main: the in-flight stage stays recorded as running."""


def reaped_pid() -> int:
    """PID of a test-owned child that has already exited and been reaped."""
    child = subprocess.Popen([sys.executable, '-c', ''], stdin=subprocess.DEVNULL)
    child.wait(timeout=30)
    return child.pid


def tree(root: Path) -> dict:
    state = {}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            state[relative] = ('symlink', os.readlink(path))
        elif path.is_dir():
            state[relative] = ('dir',)
        else:
            state[relative] = ('file', demo.sha256(path), path.stat().st_mtime_ns)
    return state


def retain_on_failure(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except unittest.SkipTest:
            raise
        except BaseException as exc:
            self.preserve_root = True
            exc.add_note(f'Retained robustness test root: {self.base}')
            raise
    return wrapper


class LaneRoot(unittest.TestCase):
    def setUp(self):
        LANE_ARTIFACTS.mkdir(parents=True, exist_ok=True)
        self.base = Path(tempfile.mkdtemp(prefix=f'{type(self).__name__}-', dir=LANE_ARTIFACTS)).resolve()
        self.preserve_root = False
        self.addCleanup(lambda: None if self.preserve_root else shutil.rmtree(self.base, ignore_errors=True))


class ResumeEnv:
    """Isolated ROOT with stub worker files, one pre-published run and a mocked invoke."""

    def __init__(self, root: Path, dead_pid: int):
        self.root = root
        self.dead_pid = dead_pid
        (root / 'scripts').mkdir(parents=True)
        for name in STUB_WORKERS:
            (root / 'scripts' / name).write_text(f'# stub worker {name}\n')
        self.directory = root / 'artifacts/runs/20200101T000000Z-aaaaaaaaaaaa'
        self.directory.mkdir(parents=True)
        self.source = root / 'original.mov'
        self.source.write_bytes(b'original private source')
        for name in ('denoised.wav', 'cleaned.wav'):
            (self.directory / name).write_bytes(name.encode())
        self.manifest = {'schema_version': 1, 'run_id': self.directory.name, 'run_dir': str(self.directory),
                         'source': {'path': str(self.source), 'sha256': demo.sha256(self.source)},
                         'output_sha256': {name: demo.sha256(self.directory / name) for name in ('denoised.wav', 'cleaned.wav')},
                         'pcm': {'sample_rate': 44100, 'channels': 1, 'sample_count': 100}}
        (self.directory / 'manifest.json').write_text(json.dumps(self.manifest))
        self.calls, self.timeouts = [], {}
        self.fail, self.crash_at = set(), None

    def fake_invoke(self, script, arguments, timeout=1200, interpreter=None, execution=None, on_started=None):
        name = script.removesuffix('.py')
        if name == 'media':
            name = 'media' if arguments[0] == 'clean' else 'export'
        if name == 'guitar_features':
            name = arguments[0]
        if name == 'phrase_compare':
            name = 'comparisons'
        self.calls.append(name)
        self.timeouts[name] = timeout
        if execution is not None:
            execution.update(command=[script, *arguments], worker_sha256=demo.sha256(self.root / 'scripts' / script),
                             timeout_seconds=timeout, status='starting', mocked_execution=True)
            if on_started is not None:
                on_started()
        if name == self.crash_at:
            if name not in ('media', 'export'):
                (self.directory / f'{name}.json').write_text('{"partial": true}')
            raise SimulatedOrchestratorDeath(name)
        if name in self.fail:
            raise demo.StageError(f'{name} fixture failure', {'status': 'failed', 'fixture': True})
        stamp = {'tool': name, 'call': len(self.calls), 'tonic': None}
        result = {'status': 'unreviewed', 'tonic': None}
        if name == 'media':
            result = self.manifest
        elif name == 'export':
            (self.directory / 'export').mkdir(exist_ok=True)
            (self.directory / 'export/outcome.json').write_text(json.dumps(
                {'video': None, 'source_sha256': self.manifest['source']['sha256'], 'output_sha256': {}}))
            result = {'video': None}
        elif name == 'rhythm':
            (self.directory / 'analysis.json').write_text(json.dumps(stamp))
            (self.directory / 'events.csv').write_text(f'time,call\n0,{len(self.calls)}\n')
        elif name in ('noise', 'tone', 'notes', 'phrases'):
            (self.directory / f'{name}.json').write_text(json.dumps(stamp))
        elif name in demo.OPTIONAL_OUTPUTS:
            key, _ = demo.OPTIONAL_OUTPUTS[name]
            relative = {'clicks': 'clicks/c1/clicks.json', 'pitch': 'pitch.json', 'meter': 'meter/m1/meter.json',
                        'tonal': 'tonal/tonal.json', 'comparisons': 'phrase-comparisons.json'}[name]
            path = self.directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(stamp))
            result = {key: str(path), 'sha256': demo.sha256(path)}
        elif name == 'dag':
            rows = {}
            for slot in demo.OPTIONAL_OUTPUTS:
                flag = '--' + slot + '-artifact'
                chosen = arguments[arguments.index(flag) + 1] if flag in arguments else None
                rows[slot] = ({'status': 'verified', 'selector': chosen,
                               'artifact_sha256': demo.sha256(self.directory / chosen)} if chosen else
                              {'status': 'not_selected', 'selector': None, 'artifact_sha256': None})
            (self.directory / 'dag.json').write_text(json.dumps({'selected_evidence': rows, 'call': len(self.calls)}))
            (self.directory / 'flags.json').write_text(json.dumps({'flags': [], 'call': len(self.calls)}))
            result = {'dag_json': str(self.directory / 'dag.json')}
        elif name == 'markers':
            (self.directory / 'markers.json').write_text(json.dumps({'markers': [], 'call': len(self.calls)}))
            (self.directory / 'markers.csv').write_text('time,status\n')
        elif name == 'report':
            (self.directory / 'report.html').write_text(f'<p>report call {len(self.calls)}</p>')
            result = {'report': 'report.html', 'listening_acceptance': 'pending'}
        if execution is not None:
            execution['status'] = 'completed'
        return result

    def main(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(demo, 'ROOT', self.root), patch.object(demo, 'invoke', side_effect=self.fake_invoke), \
                patch.object(demo, 'verify_pcm'), patch.object(demo, 'current_pid', return_value=self.dead_pid), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                status = demo.main(arguments)
            except SimulatedOrchestratorDeath:
                status = 'crashed'
        output = stdout.getvalue()
        return status, json.loads(output) if output else None, stderr.getvalue()

    def fresh(self, *extra):
        return self.main([str(self.source), '--profile', 'conservative3', *extra])

    def resume(self, invocation_id, *extra):
        self.calls = []
        return self.main(['--resume', invocation_id, *extra])

    def invocation_id(self):
        (entry,) = list((self.root / 'artifacts/demo-invocations').iterdir())
        return entry.name

    def receipt_path(self, invocation_id=None):
        invocation_id = invocation_id or self.invocation_id()
        bootstrap = self.root / 'artifacts/demo-invocations' / invocation_id / 'receipt.json'
        data = json.loads(bootstrap.read_text())
        return Path(data['receipt']) if set(data) == {'schema_version', 'invocation_id', 'run_dir', 'receipt'} else bootstrap

    def receipt(self, invocation_id=None):
        return json.loads(self.receipt_path(invocation_id).read_text())

    def edit_receipt(self, change):
        path = self.receipt_path()
        data = json.loads(path.read_text())
        change(data)
        path.write_text(json.dumps(data))

    def published_runs(self):
        return sorted(path.name for path in (self.root / 'artifacts/runs').iterdir() if not path.name.startswith('.'))


class DemoResumeTests(LaneRoot):
    def setUp(self):
        super().setUp()
        self.dead = reaped_pid()

    def env(self, label='root'):
        return ResumeEnv(self.base / label, self.dead)

    def sleeper(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'],
                                 stdin=subprocess.DEVNULL, start_new_session=True)

        def stop():  # Test-owned child only.
            if child.poll() is None:
                child.kill()
            child.wait(timeout=10)
        self.addCleanup(stop)
        return child

    def assert_refusal_writes_nothing(self, env, invocation_id, reason, *extra):
        receipt_path = None
        with contextlib.suppress(Exception):
            receipt_path = env.receipt_path(invocation_id)
        receipt_bytes = receipt_path.read_bytes() if receipt_path and receipt_path.exists() else None
        before = tree(env.root)
        status, result, error = env.resume(invocation_id, *extra)
        self.assertEqual(status, 1)
        self.assertIsNone(result)
        payload = json.loads(error.strip().splitlines()[-1])
        self.assertEqual((payload['status'], payload['reason']), ('error', reason), payload)
        self.assertEqual(env.calls, [])
        self.assertEqual(tree(env.root), before)
        if receipt_bytes is not None:
            self.assertEqual(receipt_path.read_bytes(), receipt_bytes)
        return payload

    @retain_on_failure
    def test_resume_after_orchestrator_crash_mid_stage_skips_verified_prefix(self):
        env = self.env()
        env.crash_at = 'tone'
        status, _, _ = env.fresh()
        self.assertEqual(status, 'crashed')
        invocation_id = env.invocation_id()
        crashed = env.receipt()
        self.assertEqual(crashed['stages']['tone']['status'], 'running')
        self.assertIn('resume_arguments', crashed)
        self.assertEqual(crashed['resume_arguments']['input_sha256'], demo.sha256(env.source))
        prefix = {name: demo.sha256(env.directory / name) for name in ('analysis.json', 'events.csv', 'noise.json')}
        env.crash_at = None
        status, result, _ = env.resume(invocation_id)
        self.assertEqual(status, 0)
        self.assertEqual(env.calls, ['tone', 'notes', 'phrases', 'dag', 'markers', 'report'])
        receipt = env.receipt(invocation_id)
        self.assertEqual(receipt['invocation_id'], invocation_id)
        self.assertEqual(receipt['run_dir'], crashed['run_dir'])
        self.assertEqual(result['run_dir'], crashed['run_dir'])
        self.assertEqual(receipt['status'], 'completed_unreviewed')
        self.assertEqual(receipt['final_media_identity_verification'],
                         'original_source_and_native_PCM_hashes_and_extents_verified')
        (history,) = receipt['resume_history']
        self.assertEqual(history['resume_index'], 1)
        self.assertEqual(history['skipped_stages'], ['media', 'export', 'rhythm', 'noise'])
        self.assertEqual(history['rerun_stages'], ['tone', 'notes', 'phrases', 'dag', 'markers', 'report'])
        self.assertEqual(history['lock'], {'status': 'acquired', 'prior_pid': None})
        self.assertEqual(history['verified']['source_sha256'], demo.sha256(env.source))
        self.assertIsNone(history['memory_ceiling_bytes'])
        self.assertEqual(history['memory_ceiling_status'], 'unknown_not_measured')
        self.assertFalse(receipt['listening_accepted'])
        self.assertEqual({name: demo.sha256(env.directory / name) for name in prefix}, prefix)
        self.assertEqual(env.published_runs(), [env.directory.name])
        self.assertEqual(json.loads((env.directory / 'demo.json').read_text()), receipt)
        self.assertFalse((env.receipt_path(invocation_id).parent / 'resume.lock').exists())
        for name in BASE_ORDER:
            self.assertIn(receipt['stages'][name]['status'], demo.SUCCESS_TERMINAL, name)

    @retain_on_failure
    def test_resume_reruns_failed_stage_and_downstream_only(self):
        env = self.env()
        env.fail.add('noise')
        status, result, _ = env.fresh()
        self.assertEqual(status, 0)
        invocation_id = env.invocation_id()
        self.assertEqual(env.receipt()['status'], 'completed_with_stage_failures')
        kept = {name: demo.sha256(env.directory / name) for name in ('analysis.json', 'tone.json', 'notes.json', 'phrases.json')}
        env.fail.clear()
        status, result, _ = env.resume(invocation_id)
        self.assertEqual(status, 0)
        self.assertEqual(env.calls, ['noise', 'dag', 'markers', 'report'])
        receipt = env.receipt(invocation_id)
        self.assertEqual(receipt['status'], 'completed_unreviewed')
        self.assertEqual(receipt['failed_stages'], [])
        self.assertEqual(receipt['resume_history'][0]['prior_status'], 'completed_with_stage_failures')
        self.assertEqual(receipt['resume_history'][0]['skipped_stages'],
                         ['media', 'export', 'rhythm', 'tone', 'notes', 'phrases'])
        self.assertEqual({name: demo.sha256(env.directory / name) for name in kept}, kept)
        self.assertEqual(env.published_runs(), [env.directory.name])

    @retain_on_failure
    def test_resume_displaces_unverified_outputs_without_deleting(self):
        env = self.env()
        env.fail.add('noise')
        env.fresh()
        invocation_id = env.invocation_id()
        receipts = {env.receipt_path(invocation_id), env.directory / 'demo.json'}
        before = {path: demo.sha256(path) for path in env.directory.rglob('*') if path.is_file() and path not in receipts}
        env.fail.clear()
        status, _, _ = env.resume(invocation_id)
        self.assertEqual(status, 0)
        receipt = env.receipt(invocation_id)
        displaced = receipt['resume_history'][0]['displaced_outputs']
        self.assertEqual(set(displaced), {'dag.json', 'flags.json', 'markers.json', 'markers.csv', 'report.html'})
        root = env.receipt_path(invocation_id).parent / 'resume-1' / 'displaced'
        for relative, digest in displaced.items():
            self.assertEqual(demo.sha256(root / relative), digest)
            self.assertEqual(before[env.directory / relative], digest)
        for path, digest in before.items():
            relative = path.relative_to(env.directory).as_posix()
            survived = path.is_file() and demo.sha256(path) == digest
            self.assertTrue(survived or displaced.get(relative) == digest, f'{relative} was lost')
        # A partially written output of the crashed stage is displaced too.
        crash = self.env('crash')
        crash.crash_at = 'tone'
        crash.fresh()
        crash_id = crash.invocation_id()
        partial = demo.sha256(crash.directory / 'tone.json')
        crash.crash_at = None
        self.assertEqual(crash.resume(crash_id)[0], 0)
        history = crash.receipt(crash_id)['resume_history'][0]
        self.assertEqual(history['displaced_outputs'], {'tone.json': partial})
        self.assertEqual(demo.sha256(crash.receipt_path(crash_id).parent / 'resume-1/displaced/tone.json'), partial)

    @retain_on_failure
    def test_resume_refusals_write_nothing(self):
        def crashed(label, at='tone', existing=False):
            env = self.env(label)
            env.crash_at = at
            if existing:
                (env.directory / 'analysis.json').write_text('{"prior": true}')
                status, _, _ = env.main(['--existing-run', str(env.directory)])
            else:
                status, _, _ = env.fresh()
            self.assertEqual(status, 'crashed')
            env.crash_at = None
            return env, env.invocation_id()

        def tamper(path, content=b'tampered'):
            path.write_bytes(content)

        scenarios = []
        env, _ = crashed('invalid')
        for value in ('../etc', '20261006T000000Z-abcdef12345', '20261006T000000Z-ABCDEF123456',
                      ' 20261006T000000Z-abcdef123456', '20261006T000000Z-abcdef123456/..'):
            scenarios.append(('invalid_invocation_id', env, value))
        env, _ = crashed('missing')
        scenarios.append(('receipt_not_found', env, '20261006T000000Z-abcdef123456'))
        env, _ = crashed('invalid-json')
        bogus = env.root / 'artifacts/demo-invocations/20261006T000000Z-0123456789ab'
        bogus.mkdir()
        (bogus / 'receipt.json').write_text('{"invocation_id": "20261006T000000Z-0123456789ab", "x": NaN}')
        scenarios.append(('receipt_invalid', env, bogus.name))
        env, invocation_id = crashed('pointer')
        pointer = env.root / 'artifacts/demo-invocations' / invocation_id / 'receipt.json'
        data = json.loads(pointer.read_text())
        data['receipt'] = str(env.root / 'elsewhere.json')
        pointer.write_text(json.dumps(data))
        scenarios.append(('receipt_invalid', env, invocation_id))
        env, invocation_id = crashed('legacy')
        env.edit_receipt(lambda receipt: receipt.pop('resume_arguments'))
        scenarios.append(('receipt_lacks_resume_arguments', env, invocation_id))
        env = self.env('terminal')
        self.assertEqual(env.fresh()[0], 0)
        scenarios.append(('invocation_already_terminal', env, env.invocation_id()))
        env, invocation_id = crashed('source')
        tamper(env.source)
        scenarios.append(('source_hash_drift', env, invocation_id))
        env, invocation_id = crashed('media')
        tamper(env.directory / 'denoised.wav')
        scenarios.append(('media_hash_drift', env, invocation_id))
        env, invocation_id = crashed('stage')
        tamper(env.directory / 'analysis.json', b'{"tampered": true}')
        scenarios.append(('stage_artifact_hash_drift', env, invocation_id))
        env, invocation_id = crashed('worker')
        tamper(env.root / 'scripts/rhythm.py', b'# changed worker\n')
        scenarios.append(('worker_hash_drift', env, invocation_id))
        env, invocation_id = crashed('snapshot', existing=True)
        snapshot = env.directory / env.receipt()['prior_artifact_snapshot']['path']
        tamper(snapshot / 'analysis.json', b'{"rewritten": true}')
        scenarios.append(('snapshot_hash_drift', env, invocation_id))
        for reason, env, invocation_id in scenarios:
            with self.subTest(reason=reason, invocation_id=invocation_id):
                payload = self.assert_refusal_writes_nothing(env, invocation_id, reason)
                self.assertTrue(payload['message'])
        self.assertEqual({reason for reason, _, _ in scenarios},
                         {'invalid_invocation_id', 'receipt_not_found', 'receipt_invalid',
                          'receipt_lacks_resume_arguments', 'invocation_already_terminal', 'source_hash_drift',
                          'media_hash_drift', 'stage_artifact_hash_drift', 'worker_hash_drift', 'snapshot_hash_drift'})

    @retain_on_failure
    def test_resume_refuses_live_orchestrator_and_live_worker_group_without_signalling(self):
        env = self.env()
        env.crash_at = 'tone'
        env.fresh()
        invocation_id = env.invocation_id()
        live = self.sleeper()
        env.edit_receipt(lambda receipt: receipt['orchestrator'].update(pid=live.pid))
        payload = self.assert_refusal_writes_nothing(env, invocation_id, 'orchestrator_may_be_alive')
        self.assertIn(str(live.pid), payload['message'])
        self.assertIsNone(live.poll())

        def worker_alive(receipt):
            receipt['orchestrator']['pid'] = self.dead
            receipt['stages']['tone']['execution']['pid'] = live.pid
        env.edit_receipt(worker_alive)
        payload = self.assert_refusal_writes_nothing(env, invocation_id, 'prior_worker_group_alive')
        self.assertIn('no signal', payload['message'])
        self.assertIsNone(live.poll())

    @retain_on_failure
    def test_resume_lock_held_and_stale_lock_takeover(self):
        env = self.env()
        env.crash_at = 'tone'
        env.fresh()
        invocation_id = env.invocation_id()
        env.crash_at = None
        lock = env.receipt_path(invocation_id).parent / 'resume.lock'
        live = self.sleeper()
        lock.write_text(json.dumps({'pid': live.pid}))
        self.assert_refusal_writes_nothing(env, invocation_id, 'resume_lock_held')
        self.assertIsNone(live.poll())
        stale = reaped_pid()
        lock.write_text(json.dumps({'pid': stale}))
        status, _, _ = env.resume(invocation_id)
        self.assertEqual(status, 0)
        history = env.receipt(invocation_id)['resume_history'][0]
        self.assertEqual(history['lock'], {'status': 'stale_taken_over', 'prior_pid': stale})
        self.assertFalse(lock.exists())

    @retain_on_failure
    def test_resume_media_incomplete_reruns_media_once_and_refuses_unrecorded_run_dir(self):
        env = self.env()
        env.crash_at = 'media'
        self.assertEqual(env.fresh()[0], 'crashed')
        invocation_id = env.invocation_id()
        bootstrap = env.root / 'artifacts/demo-invocations' / invocation_id / 'receipt.json'
        self.assertEqual(json.loads(bootstrap.read_text())['stages']['media']['status'], 'running')
        env.crash_at = None
        # A killed media.py can only leave staging; it is counted, never deleted.
        orphan = env.root / 'artifacts/runs/.staging-20990101T000000Z-cccccccccccc-x'
        orphan.mkdir()
        decoy = env.root / 'artifacts/runs/20990101T000000Z-bbbbbbbbbbbb'
        decoy.mkdir()
        (decoy / 'manifest.json').write_text(json.dumps({'run_id': decoy.name, 'source': {'sha256': demo.sha256(env.source)}}))
        payload = self.assert_refusal_writes_nothing(env, invocation_id, 'media_outcome_unrecorded_run_dir_exists')
        self.assertIn(str(decoy), payload['message'])
        shutil.rmtree(decoy)  # Test-owned decoy only.
        status, _, _ = env.resume(invocation_id)
        self.assertEqual(status, 0)
        self.assertEqual(env.calls.count('media'), 1)
        self.assertEqual(env.calls, BASE_ORDER)
        receipt = env.receipt(invocation_id)
        self.assertEqual(receipt['status'], 'completed_unreviewed')
        history = receipt['resume_history'][0]
        self.assertEqual(history['orphan_staging_dirs_observed'], 1)
        self.assertEqual(history['skipped_stages'], [])
        self.assertTrue(orphan.is_dir())
        self.assertEqual(env.published_runs(), [env.directory.name])
        self.assertEqual(json.loads(bootstrap.read_text())['receipt'], str(env.receipt_path(invocation_id)))

    @retain_on_failure
    def test_resume_existing_run_mode_verifies_snapshot_and_never_resnapshots(self):
        env = self.env()
        (env.directory / 'analysis.json').write_text('{"prior_analysis": true}')
        (env.directory / 'demo.json').write_text('{"status": "prior_unreviewed"}')
        env.crash_at = 'tone'
        self.assertEqual(env.main(['--existing-run', str(env.directory), '--no-latest'])[0], 'crashed')
        invocation_id = env.invocation_id()
        crashed = env.receipt(invocation_id)
        history_root = env.directory / 'demo-history'
        snapshots = tree(history_root)
        prior_demo = env.receipt_path(invocation_id).parent / 'prior-demo.json'
        prior_bytes = prior_demo.read_bytes()
        env.crash_at = None
        status, _, _ = env.resume(invocation_id)
        self.assertEqual(status, 0)
        self.assertEqual(env.calls, ['tone', 'notes', 'phrases', 'dag', 'markers', 'report'])
        receipt = env.receipt(invocation_id)
        self.assertEqual(receipt['prior_artifact_snapshot'], crashed['prior_artifact_snapshot'])
        self.assertEqual(tree(history_root), snapshots)
        self.assertEqual(prior_demo.read_bytes(), prior_bytes)
        self.assertEqual(json.loads(prior_bytes), {'status': 'prior_unreviewed'})
        self.assertEqual(receipt['resume_history'][0]['skipped_stages'], ['media', 'export', 'rhythm', 'noise'])
        self.assertEqual(receipt['stages']['media']['status'], 'existing_media_verified_unreviewed')
        self.assertEqual(receipt['resume_history'][0]['displaced_outputs'], {'tone.json': demo.sha256(
            env.receipt_path(invocation_id).parent / 'resume-1/displaced/tone.json')})
        self.assertFalse((env.root / 'artifacts/latest.json').exists())
        self.assertEqual(env.published_runs(), [env.directory.name])

    @retain_on_failure
    def test_resume_rejects_conflicting_arguments(self):
        env = self.env()
        invocation_id = '20261006T000000Z-abcdef123456'
        before = tree(env.root)
        for extra in (['input.mov'], ['--existing-run', str(env.directory)], ['--profile', 'conservative3'],
                      ['--capture-interval', '0.2', '0.9'], ['--capture-review', 'text'], ['--bpm', '120'],
                      ['--backend', 'stdlib'], ['--features', 'base'], ['--analysis-python', sys.executable],
                      ['--pitch-seconds', '5']):
            with self.subTest(extra=extra), self.assertRaises(SystemExit) as caught:
                env.main(['--resume', invocation_id, *extra])
            self.assertEqual(caught.exception.code, 2)
        self.assertEqual(env.calls, [])
        self.assertEqual(tree(env.root), before)

    @retain_on_failure
    def test_stage_timeouts_unchanged_and_recorded(self):
        def load(name):
            spec = importlib.util.spec_from_file_location(f'robustness_{name}', REPO / 'scripts' / f'{name}.py')
            module = importlib.util.module_from_spec(spec)
            sys.path.insert(0, str(REPO / 'scripts'))
            try:
                spec.loader.exec_module(module)
            finally:
                sys.path.remove(str(REPO / 'scripts'))
            return module
        expected = {'media': 1200, 'export': 1200, 'rhythm': 600, 'noise': 600, 'tone': 600, 'notes': 600,
                    'phrases': 600, 'clicks': 300, 'pitch': 300, 'meter': 300, 'tonal': 300, 'comparisons': 300,
                    'dag': 180, 'markers': 180, 'report': 180}
        self.assertEqual(demo.STAGE_TIMEOUTS, expected)
        self.assertEqual(demo.MAX_OUTPUT_BYTES, 2 * 1024 * 1024)
        media, rhythm, share = load('media'), load('rhythm'), load('share_export')
        self.assertEqual(media.TIMEOUT, 600)
        self.assertIn('timeout=60)', inspect_source(media.probe))
        self.assertEqual(inspect_default(rhythm.run, 'timeout'), 180)
        for value, accepted in ((29, False), (30, True), (900, True), (901, False)):
            with self.subTest(share_export_timeout=value):
                if accepted:
                    self.assertEqual(share.settings(timeout_seconds=value)['timeout_seconds'], value)
                else:
                    with self.assertRaises(Exception):
                        share.settings(timeout_seconds=value)
        env = self.env()
        status, _, _ = env.main([str(env.source), '--profile', 'conservative3', '--features', 'extended', '--bpm', '120'])
        self.assertEqual(status, 0)
        receipt = env.receipt()
        for name, timeout in expected.items():
            with self.subTest(stage=name):
                self.assertEqual(env.timeouts[name], timeout)
                self.assertEqual(receipt['stages'][name]['execution']['timeout_seconds'], timeout)
        limits = receipt['resource_limits']
        self.assertEqual(limits['stage_timeouts_seconds'], expected)
        self.assertEqual(limits['max_output_bytes_per_stream'], demo.MAX_OUTPUT_BYTES)
        self.assertIsNone(limits['memory_ceiling_bytes'])
        self.assertEqual(limits['memory_ceiling_status'], 'unknown_not_measured')


def inspect_source(function):
    import inspect
    return inspect.getsource(function)


def inspect_default(function, name):
    import inspect
    return inspect.signature(function).parameters[name].default


STUB_COMMON = r"""
import hashlib, json, os, signal, sys, wave
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def control(stage):
    # Test-owned fault injection: one-shot, consumed on use.
    path = ROOT / 'control' / stage
    if not path.exists():
        return
    action = path.read_text().strip()
    path.unlink()
    if action == 'kill-self':
        os.kill(os.getpid(), signal.SIGKILL)
    if action == 'kill-parent':
        # Ownership check: only the test-created orchestrator recorded for this invocation.
        recorded = set()
        for receipt in (ROOT / 'artifacts' / 'demo-invocations').glob('*/receipt.json'):
            data = json.loads(receipt.read_text())
            if 'receipt' in data:
                data = json.loads(Path(data['receipt']).read_text())
            recorded.add(data['orchestrator']['pid'])
        if os.getppid() in recorded:
            os.kill(os.getppid(), signal.SIGKILL)
        sys.exit(0)


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload))


def run_dir(arguments):
    return Path(arguments[arguments.index('--run-dir') + 1]) if '--run-dir' in arguments else Path(arguments[0])
"""

STUBS = {
    'media.py': STUB_COMMON + r"""
import tempfile, uuid
from datetime import datetime, timezone


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ensure_pcm_matches(path, reference):
    with wave.open(str(path), 'rb') as handle:
        info = {'sample_rate': handle.getframerate(), 'channels': handle.getnchannels(), 'sample_count': handle.getnframes()}
    for key in info:
        if info[key] != reference[key]:
            raise ValueError(f'{Path(path).name} changed {key}')
    return info


def clean(source, profile):
    source = Path(source).resolve()
    runs = ROOT / 'artifacts' / 'runs'
    runs.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:12]
    staging = Path(tempfile.mkdtemp(prefix='.staging-' + run_id + '-', dir=runs))
    for index, name in enumerate(('source.wav', 'denoised.wav', 'cleaned.wav')):
        with wave.open(str(staging / name), 'wb') as handle:
            handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(44100)
            handle.writeframes(bytes([index]) * 200)
    final = runs / run_id
    manifest = {'schema_version': 1, 'run_id': run_id, 'run_dir': str(final), 'profile': {'name': profile},
                'source': {'path': str(source), 'sha256': sha256(source)},
                'pcm': {'sample_rate': 44100, 'channels': 1, 'sample_count': 100},
                'timeline': {'audio_start_seconds': 0.0, 'no_time_stretch': True},
                'output_sha256': {name: sha256(staging / name) for name in ('source.wav', 'denoised.wav', 'cleaned.wav')}}
    write(staging / 'manifest.json', manifest)
    staging.rename(final)
    return manifest


def export(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    outcome = {'schema_version': 1, 'video': None, 'source_sha256': manifest['source']['sha256'], 'output_sha256': {}}
    write(directory / 'export' / 'outcome.json', outcome)
    return outcome


if __name__ == '__main__':
    command, *rest = sys.argv[1:]
    control('media' if command == 'clean' else 'export')
    print(json.dumps(clean(rest[0], rest[1]) if command == 'clean' else export(rest[0])))
""",
    'rhythm.py': STUB_COMMON + r"""
if __name__ == '__main__':
    directory = run_dir(sys.argv[1:])
    control('rhythm')
    write(directory / 'analysis.json', {'tool': 'rhythm', 'bpm': None})
    write(directory / 'events.csv', 'time\n')
    print(json.dumps({'status': 'stub'}))
""",
    'guitar_features.py': STUB_COMMON + r"""
if __name__ == '__main__':
    tool = sys.argv[1]
    directory = run_dir(sys.argv[2:])
    control(tool)
    write(directory / f'{tool}.json', {'tool': tool, 'tonic': None})
    print(json.dumps({'status': 'stub', 'tool': tool}))
""",
    'dag.py': STUB_COMMON + r"""
if __name__ == '__main__':
    directory = Path(sys.argv[1])
    control('dag')
    rows = {slot: {'status': 'not_selected', 'selector': None, 'artifact_sha256': None}
            for slot in ('clicks', 'pitch', 'meter', 'tonal', 'comparisons')}
    write(directory / 'dag.json', {'selected_evidence': rows})
    write(directory / 'flags.json', {'flags': []})
    print(json.dumps({'dag_json': str(directory / 'dag.json'), 'flags_json': str(directory / 'flags.json')}))
""",
    'markers.py': STUB_COMMON + r"""
if __name__ == '__main__':
    directory = Path(sys.argv[1])
    control('markers')
    write(directory / 'markers.json', {'markers': []})
    write(directory / 'markers.csv', 'time\n')
    print(json.dumps({'markers_json': str(directory / 'markers.json')}))
""",
    'report.py': STUB_COMMON + r"""
if __name__ == '__main__':
    directory = Path(sys.argv[1])
    control('report')
    write(directory / 'report.html', '<p>stub report</p>')
    print(json.dumps({'report': 'report.html', 'listening_acceptance': 'pending'}))
""",
}


class DemoResumeProcessTests(LaneRoot):
    """Real orchestrator and worker subprocesses with stub workers; no FFmpeg."""

    def setUp(self):
        super().setUp()
        self.root = self.base / 'root'
        (self.root / 'scripts').mkdir(parents=True)
        (self.root / 'control').mkdir()
        shutil.copyfile(REPO / 'scripts/run_demo.py', self.root / 'scripts/run_demo.py')
        for name, text in STUBS.items():
            (self.root / 'scripts' / name).write_text(text)
        self.source = self.root / 'take.bin'
        self.source.write_bytes(b'synthetic stub source bytes')

    def run_demo(self, *arguments):
        return subprocess.run([sys.executable, str(self.root / 'scripts/run_demo.py'), *arguments], cwd=self.root,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)

    def invocation(self):
        (entry,) = list((self.root / 'artifacts/demo-invocations').iterdir())
        pointer = json.loads((entry / 'receipt.json').read_text())
        return entry.name, Path(pointer['receipt'])

    def published_runs(self):
        return [path for path in (self.root / 'artifacts/runs').iterdir() if not path.name.startswith('.')]

    def wait_group_gone(self, pgid):
        deadline = time.monotonic() + 15
        while demo.group_alive(pgid) and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertFalse(demo.group_alive(pgid), 'stub worker group did not exit')

    @retain_on_failure
    def test_killed_worker_mid_stage_then_resume_completes(self):
        (self.root / 'control/noise').write_text('kill-self')
        first = self.run_demo(str(self.source), '--profile', 'conservative3', '--no-latest')
        self.assertEqual(first.returncode, 0, first.stderr)
        invocation_id, path = self.invocation()
        receipt = json.loads(path.read_text())
        self.assertEqual(receipt['stages']['noise']['status'], 'failed')
        self.assertEqual(receipt['stages']['noise']['execution']['returncode'], -signal.SIGKILL)
        self.assertEqual(receipt['status'], 'completed_with_stage_failures')
        second = self.run_demo('--resume', invocation_id)
        self.assertEqual(second.returncode, 0, second.stderr)
        resumed = json.loads(path.read_text())
        self.assertEqual(resumed['status'], 'completed_unreviewed')
        self.assertEqual((resumed['invocation_id'], resumed['run_dir']), (invocation_id, receipt['run_dir']))
        self.assertEqual(resumed['stages']['noise']['status'], 'measured_candidates')
        self.assertEqual(resumed['resume_history'][0]['rerun_stages'], ['noise', 'dag', 'markers', 'report'])
        self.assertEqual(len(self.published_runs()), 1)
        self.assertEqual(json.loads(second.stdout)['run_dir'], receipt['run_dir'])

    @retain_on_failure
    def test_orchestrator_sigkill_mid_stage_then_resume_completes(self):
        (self.root / 'control/tone').write_text('kill-parent')
        first = self.run_demo(str(self.source), '--profile', 'conservative3', '--no-latest')
        self.assertEqual(first.returncode, -signal.SIGKILL, first.stderr)
        invocation_id, path = self.invocation()
        receipt = json.loads(path.read_text())
        self.assertEqual(receipt['stages']['tone']['status'], 'running')
        self.assertNotIn('status', receipt)
        worker = receipt['stages']['tone']['execution']['pid']
        self.wait_group_gone(worker)
        second = self.run_demo('--resume', invocation_id)
        self.assertEqual(second.returncode, 0, second.stderr)
        resumed = json.loads(path.read_text())
        self.assertEqual(resumed['status'], 'completed_unreviewed')
        self.assertEqual((resumed['invocation_id'], resumed['run_dir']), (invocation_id, receipt['run_dir']))
        history = resumed['resume_history'][0]
        self.assertEqual(history['prior_orchestrator']['pid'], receipt['orchestrator']['pid'])
        self.assertEqual(history['skipped_stages'], ['media', 'export', 'rhythm', 'noise'])
        self.assertEqual(len(self.published_runs()), 1)
        self.assertEqual(resumed['final_media_identity_verification'],
                         'original_source_and_native_PCM_hashes_and_extents_verified')


if __name__ == '__main__':
    unittest.main()
