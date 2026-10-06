"""Synthetic phone / Photo Booth fixtures through the full demo pipeline (S2 robustness, TIN-5609).

Contract: docs/spec/sprints/ROBUSTNESS_S2.md §4-§7. Fixtures are synthetic; nothing here
is a real-take, device-capture, listening or note-correctness claim. run_demo.py runs as a
subprocess inside an isolated temporary ROOT (copies of scripts/, profiles/, program/)
under the gitignored artifacts/s2/robustness/, with --no-latest; the repository's
artifacts/runs is never written and the real take is never opened. Heavy pipeline runs
execute sequentially, each under a 600 s subprocess timeout.
"""
from fractions import Fraction
import functools
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
LANE_ARTIFACTS = REPO / 'artifacts' / 's2' / 'robustness'
RESULTS_PATH = LANE_ARTIFACTS / 'fixture-run-results.json'
QUALIFIED_BIN = Path('/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin')
QUALIFIED_SHA = {
    'ffmpeg': '3a315207e67de78e48c3bbb6b3346663f6a27c02e034d65ac72a12fee74c534a',
    'ffprobe': '5fb21f955aad27bc59615906801ce4b5b9f1466e99450b714b6d989f836c8850',
}
PIPELINE_TIMEOUT = 600
CAPTURE_REVIEW = 'synthetic fixture lead-in: pink noise only by construction (seed 5609)'
REAL_TAKE = '/Users/jess/Documents/Movie on 10-5-26 at 3.38 PM.mov'
VERDICT_KEYS = {'performance_issue_confirmed', 'note_correctness_confirmed', 'missed_notes_confirmed',
                'extra_notes_confirmed', 'musical_error_confirmed', 'note_correctness', 'missed_or_extra_notes'}

spec = importlib.util.spec_from_file_location('robustness_phone_fixtures', REPO / 'tests/support/phone_fixtures.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


def file_identity(path: Path) -> tuple:
    stat = path.stat()
    return fixtures.sha256(path), stat.st_size, stat.st_mtime_ns


def qualified_environment() -> dict:
    for name, digest in QUALIFIED_SHA.items():
        path = QUALIFIED_BIN / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise unittest.SkipTest(f'qualified {name} binary unavailable or changed at {path}')
    return {'FFMPEG': str(QUALIFIED_BIN / 'ffmpeg'), 'FFPROBE': str(QUALIFIED_BIN / 'ffprobe')}


def load_module(root: Path, name: str):
    """Import a worker module from the isolated ROOT copy (sibling imports resolved there)."""
    scripts = str(root / 'scripts')
    module_spec = importlib.util.spec_from_file_location(f'robustness_{name}', root / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(module_spec)
    sys.path.insert(0, scripts)
    try:
        module_spec.loader.exec_module(module)
    finally:
        sys.path.remove(scripts)
    return module


def verdicts(value, path='') -> list:
    """Every note/performance verdict key carrying an affirmative value."""
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in VERDICT_KEYS and child is True:
                found.append(f'{path}/{key}')
            found += verdicts(child, f'{path}/{key}')
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found += verdicts(child, f'{path}[{index}]')
    return found


def decimal(value: Fraction) -> str:
    return f'{float(value):.6f}'


def retain_on_failure(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except unittest.SkipTest:
            raise
        except BaseException as exc:
            type(self).preserve = True
            exc.add_note(f'Retained synthetic fixture root and stage evidence: {type(self).base}')
            raise
    return wrapper


class PhoneFixturePipelineTests(unittest.TestCase):
    results: list = []

    @classmethod
    def setUpClass(cls):
        cls.environment = qualified_environment()
        cls.patcher = patch.dict(os.environ, cls.environment)
        cls.patcher.start()
        LANE_ARTIFACTS.mkdir(parents=True, exist_ok=True)
        cls.base = Path(tempfile.mkdtemp(prefix='phone-fixtures-', dir=LANE_ARTIFACTS)).resolve()
        cls.preserve = False
        cls.fixture_dir = cls.base / 'fixtures'
        cls.root = cls.base / 'root'
        try:
            for name in ('scripts', 'profiles', 'program'):
                shutil.copytree(REPO / name, cls.root / name, ignore=shutil.ignore_patterns('__pycache__'))
            cls.hevc = fixtures.has_encoder('libx265')
            cls.fixtures, cls.build_seconds = {}, {}
            for kind in ('phone', 'photo_booth', 'photo_booth_preroll') + (('phone_hevc',) if cls.hevc else ()):
                started = time.monotonic()
                cls.fixtures[kind] = fixtures.build_fixture(kind, cls.fixture_dir)
                cls.build_seconds[kind] = time.monotonic() - started
            cls.identities = {kind: file_identity(Path(receipt['path'])) for kind, receipt in cls.fixtures.items()}
            cls.media = load_module(cls.root, 'media')
            cls.planner = load_module(cls.root, 'editor_marker_plan')
        except BaseException:
            cls.patcher.stop()
            cls.preserve = True
            raise

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
        payload = {'schema_version': 1, 'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                   'retained_root': str(cls.base) if cls.preserve else None,
                   'hevc': 'run' if cls.hevc else 'skipped_encoder_absent',
                   'fixtures': {kind: {key: receipt[key] for key in ('kind', 'sha256', 'size_bytes', 'expected', 'measured', 'unknown', 'commands')}
                                for kind, receipt in cls.fixtures.items()},
                   'fixture_build_seconds': cls.build_seconds, 'pipeline_runs': cls.results,
                   'real_take_opened': False}
        RESULTS_PATH.write_text(json.dumps(payload, indent=2, default=str) + '\n')
        if not cls.preserve:
            shutil.rmtree(cls.base, ignore_errors=True)

    # ------------------------------------------------------------------ helpers
    def run_demo(self, *arguments):
        return subprocess.run([sys.executable, str(self.root / 'scripts/run_demo.py'), *arguments],
                              cwd=self.root, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              timeout=PIPELINE_TIMEOUT, env={**os.environ, **self.environment})

    def published_runs(self):
        runs = self.root / 'artifacts/runs'
        return sorted(path.name for path in runs.iterdir() if not path.name.startswith('.')) if runs.is_dir() else []

    def editor_tail(self, receipt: dict, directory: Path) -> dict:
        """P6: an audio-only tail point is outside video coverage; an in-video point is not."""
        source = Path(receipt['path'])
        time_base, frames = fixtures.video_frames(source)
        tick = Fraction(time_base)
        pts = {'source_sha256': receipt['sha256'], 'clock': 'original_source_stream_timestamps_seconds',
               'time_base': time_base, 'producer': 'robustness lane: ffprobe -show_frames of the fixture video',
               'frames': [{'best_effort_timestamp': int(frame['best_effort_timestamp']), 'duration': int(frame['duration'])}
                          for frame in frames]}
        first = int(frames[0]['best_effort_timestamp']) * tick
        video_end = (int(frames[-1]['best_effort_timestamp']) + int(frames[-1]['duration'])) * tick
        audio_end = Fraction(str(receipt['measured']['audio_end_seconds']))
        generic = json.loads((directory / 'markers.json').read_text())
        run_markers = len(generic['markers'])
        probe = {'status': 'needs_review', 'performance_issue_confirmed': False, 'confidence': 'synthetic_lane_probe',
                 'evidence': {'origin': 'ROBUSTNESS_S2 P6', 'scope': 'coordinate probe, not a musical observation'}}
        tail_time = (video_end + audio_end) / 2
        control_time = first + Fraction(1, 2)
        extended = dict(generic, markers=generic['markers'] + [
            dict(probe, name='robustness_lane_synthetic_audio_only_tail_point', source_time_seconds=decimal(tail_time)),
            dict(probe, name='robustness_lane_synthetic_in_video_control_point', source_time_seconds=decimal(control_time))])
        selection = {'source_sha256': receipt['sha256'], 'selected_markers': [
            {'marker_index': index, 'marker_id': self.planner.marker_id(index, item)}
            for index, item in enumerate(extended['markers'])]}
        profile = {'schema_version': 1, 'source_sha256': receipt['sha256'], 'target': 'final_cut_pro'}
        plan = self.planner.make_plan(extended, selection, profile, pts)
        rows = plan['markers']
        evidence = {'video_end_seconds': float(video_end), 'audio_end_seconds': float(audio_end),
                    'tail_point_seconds': float(tail_time), 'control_point_seconds': float(control_time),
                    'tail_disposition': rows[run_markers]['disposition'],
                    'control_disposition': rows[run_markers + 1]['disposition'],
                    'run_marker_dispositions': [row['disposition'] for row in rows[:run_markers]],
                    'all_rows_needs_review': all(row['status'] == 'needs_review' for row in rows),
                    'native_contract_status': plan['native_contract_status'], 'run_generic_markers': run_markers}
        if run_markers:
            names = {'pts': 'robustness-pts.json', 'selection': 'robustness-selection.json',
                     'profile': 'robustness-profile.json'}
            (directory / names['pts']).write_text(json.dumps(pts))
            run_selection = {'source_sha256': receipt['sha256'], 'selected_markers': [
                {'marker_index': index, 'marker_id': self.planner.marker_id(index, item)}
                for index, item in enumerate(generic['markers'])]}
            (directory / names['selection']).write_text(json.dumps(run_selection))
            digests = {name: fixtures.sha256(directory / name)
                       for name in ('markers.json', 'manifest.json', names['selection'], names['pts'])}
            (directory / names['profile']).write_text(json.dumps(dict(profile, pts_artifact=names['pts'], input_sha256=digests)))
            built = self.planner.build(directory, names['selection'], names['profile'])
            evidence['full_build'] = {'status': 'exercised', 'plan_status': built['plan_status'],
                                      'native_contract_status': built['native_contract_status'],
                                      'dispositions': [row['disposition'] for row in built['markers']],
                                      'all_rows_needs_review': all(row['status'] == 'needs_review' for row in built['markers'])}
        else:
            evidence['full_build'] = {'status': 'abstained_no_generic_markers'}
        return evidence

    def evaluate(self, kind: str, receipt: dict, directory: Path, demo_receipt: dict) -> dict:
        """Evaluate P1-P8 independently so every check has its own denominator."""
        checks = {}

        def check(name, function):
            try:
                ok, evidence = function()
            except Exception as exc:  # noqa: BLE001 - recorded as a failed check with its reason.
                ok, evidence = False, {'error': f'{type(exc).__name__}: {exc}'}
            checks[name] = {'passed': bool(ok), 'evidence': evidence}

        source = Path(receipt['path'])
        measured = receipt['measured']
        manifest = json.loads((directory / 'manifest.json').read_text())

        def p1():
            now = file_identity(source)
            return now == self.identities[kind], {'sha256': now[0], 'size': now[1], 'mtime_ns': now[2]}

        def p2():
            pcm = manifest['pcm']
            for name in ('denoised.wav', 'cleaned.wav'):
                self.media.ensure_pcm_matches(directory / name, pcm)
            ok = (pcm['sample_rate'] == measured['sample_rate'] and pcm['channels'] == measured['channels']
                  and pcm['sample_count'] == measured['decoded_audio_samples'])
            return ok, {'manifest_pcm': pcm, 'ffprobe_decoded_audio_samples': measured['decoded_audio_samples'],
                        'container_audio_duration_ts': measured.get('audio_stream_duration_ts'),
                        'denoised_and_cleaned_extent': 'ensure_pcm_matches passed'}

        def p3():
            timeline = manifest['timeline']
            ok = (abs(timeline['audio_start_seconds'] - measured['audio_start_seconds']) <= 1e-9
                  and timeline['no_time_stretch'] is True)
            return ok, {'manifest_audio_start_seconds': timeline['audio_start_seconds'],
                        'fixture_probed_audio_start_seconds': measured['audio_start_seconds']}

        def p4():
            outcome = json.loads((directory / 'export/outcome.json').read_text())
            verification = outcome['verification']
            evidence = {key: verification.get(key) for key in (
                'video_packet_timeline_preserved', 'video_packet_payload_hashes_preserved', 'video_frame_count_preserved',
                'relative_audio_video_start_verified', 'relative_audio_video_start_delta_seconds',
                'aac_timing_tolerance_seconds', 'source_video_packets', 'export_video_packets',
                'source_decoded_video_frames', 'export_decoded_video_frames', 'physical_audio_video_sync_verified')}
            ok = all(verification.get(key) is True for key in (
                'video_packet_timeline_preserved', 'video_packet_payload_hashes_preserved',
                'video_frame_count_preserved', 'relative_audio_video_start_verified'))
            ok = ok and abs(verification['relative_audio_video_start_delta_seconds']) <= verification['aac_timing_tolerance_seconds']
            exported = fixtures.measure(directory / 'export/cleaned-video.mov')
            evidence['exported_rotation'], evidence['source_rotation'] = exported['rotation'], measured['rotation']
            evidence['rotation_applied_to_pixels'] = False
            if kind.startswith('phone'):
                ok = ok and exported['rotation'] == measured['rotation'] == 90
            evidence['source_decode_only_packets'] = measured['decode_only_packets']
            evidence['export_decode_only_packets'] = exported['decode_only_packets']
            evidence['export_sample_rate'], evidence['export_channels'] = exported['sample_rate'], exported['channels']
            return ok, evidence

        def p5():
            lineage = json.loads((directory / 'analysis.json').read_text())['source_lineage']
            delay = lineage.get('sample_mapping', {}).get('filter_or_detector_delay', '')
            ok = (lineage['status'] == 'hash_bound_run_derivative' and lineage['timeline_rebased'] is True
                  and lineage['original_audio_start_seconds'] == manifest['timeline']['audio_start_seconds']
                  and delay.startswith('uncalibrated'))
            return ok, {key: lineage.get(key) for key in ('status', 'timeline_rebased', 'original_audio_start_seconds')} | {
                'filter_or_detector_delay': delay}

        def p6():
            evidence = self.editor_tail(receipt, directory)
            ok = (evidence['tail_disposition'] == 'outside_video_coverage'
                  and evidence['control_disposition'] != 'outside_video_coverage'
                  and evidence['all_rows_needs_review'] and evidence['native_contract_status'] == 'native_contract_unverified'
                  and (evidence['full_build']['status'] == 'abstained_no_generic_markers'
                       or (evidence['full_build']['native_contract_status'] == 'native_contract_unverified'
                           and evidence['full_build']['all_rows_needs_review'])))
            return ok, evidence

        def p7():
            report = directory / 'report.html'
            found = []
            for path in directory.rglob('*.json'):
                if path.stat().st_size <= 20_000_000:
                    found += [f'{path.relative_to(directory)}{key}' for key in verdicts(json.loads(path.read_text()))]
            ok = (demo_receipt['stages']['report']['status'] == 'completed' and report.stat().st_size > 0
                  and demo_receipt['listening_accepted'] is False and not found)
            return ok, {'report_bytes': report.stat().st_size, 'affirmative_note_or_performance_verdicts': found}

        def p8():
            outcome_path = directory / 'export/outcome.json'
            export_sync = (json.loads(outcome_path.read_text())['verification']['physical_audio_video_sync_verified']
                           if outcome_path.exists() else None)
            generic = json.loads((directory / 'markers.json').read_text())
            evidence = {'manifest_physical_audio_video_sync_verified': manifest['dsp_latency']['physical_audio_video_sync_verified'],
                        'export_physical_audio_video_sync_verified': export_sync,
                        'music_preservation_listening_verified': manifest['frequency_preservation']['music_preservation_listening_verified'],
                        'high_pass_applied': manifest['frequency_preservation']['high_pass_applied'],
                        'hum_notches_applied': manifest['frequency_preservation']['hum_notches_applied'],
                        'markers_needs_review': all(item.get('status') == 'needs_review' for item in generic['markers']),
                        'fixture_unknown': receipt['unknown'],
                        'receipt_memory_ceiling_status': demo_receipt['resource_limits']['memory_ceiling_status'],
                        'receipt_listening_accepted': demo_receipt['listening_accepted']}
            ok = (evidence['manifest_physical_audio_video_sync_verified'] is False and export_sync is False
                  and evidence['music_preservation_listening_verified'] is False
                  and evidence['high_pass_applied'] is False and evidence['hum_notches_applied'] is False
                  and evidence['markers_needs_review']
                  and receipt['unknown']['real_take_equivalence'] == 'not_established'
                  and receipt['unknown']['device_capture_equivalence'] == 'unknown'
                  and receipt['unknown']['rotation_applied_to_pixels'] is False
                  and receipt['unknown']['real_take_audio_tail_reconciled'] is False
                  and receipt['unknown']['capture_interval_noise_only'] == 'by_construction_synthetic'
                  and evidence['receipt_memory_ceiling_status'] == 'unknown_not_measured'
                  and demo_receipt['resource_limits']['memory_ceiling_bytes'] is None)
            return ok, evidence

        for name, function in (('P1_input_immutability', p1), ('P2_native_pcm', p2), ('P3_timeline', p3),
                               ('P4_export_packets', p4), ('P5_rhythm_rebase', p5), ('P6_editor_tail', p6),
                               ('P7_report', p7), ('P8_unknowns_preserved', p8)):
            check(name, function)
        return checks

    def pipeline(self, kind: str, profile: str):
        receipt = self.fixtures[kind]
        arguments = [receipt['path'], '--profile', profile, '--no-latest']
        if profile == 'fuller':
            arguments += ['--capture-interval', '0.2', '0.9', '--capture-review', CAPTURE_REVIEW]
        before_runs = self.published_runs()
        started = time.monotonic()
        completed = self.run_demo(*arguments)
        elapsed = time.monotonic() - started
        record = {'kind': kind, 'profile': profile, 'returncode': completed.returncode,
                  'wall_clock_seconds': elapsed, 'wall_clock_scope': 'measurement, not a bound',
                  'arguments': arguments[1:], 'stderr_tail': completed.stderr[-1500:]}
        type(self).results.append(record)
        self.assertEqual(completed.returncode, 0, completed.stderr[-3000:])
        result = json.loads(completed.stdout)
        directory = Path(result['run_dir'])
        demo_receipt = json.loads(Path(result['demo_receipt']).read_text())
        self.assertEqual(len(self.published_runs()) - len(before_runs), 1)
        self.assertTrue(str(directory).startswith(str(self.root / 'artifacts/runs')))
        record.update(run_dir=str(directory), invocation_id=demo_receipt['invocation_id'],
                      analysis_status=demo_receipt['status'],
                      stage_status={name: value['status'] for name, value in demo_receipt['stages'].items()})
        checks = self.evaluate(kind, receipt, directory, demo_receipt)
        record['checks'] = checks
        manifest = json.loads((directory / 'manifest.json').read_text())
        if profile == 'fuller':
            capture = manifest['noise_capture']
            record['noise_capture'] = {key: capture.get(key) for key in (
                'selected_seconds', 'selected_samples', 'noise_only_verified_by_worker', 'profile_update_status')}
            self.assertEqual(capture['selected_seconds'], [0.2, 0.9])
            self.assertIs(capture['noise_only_verified_by_worker'], False)
            self.assertEqual(capture['review'], CAPTURE_REVIEW)
        for name, value in checks.items():
            with self.subTest(check=name):
                self.assertTrue(value['passed'], json.dumps(value['evidence'], default=str)[:3000])
        return record

    # ------------------------------------------------------------------ fixture tests
    @retain_on_failure
    def test_builder_bounds_and_no_overwrite(self):
        for kwargs in ({'seconds': 10.5}, {'seconds': 0}, {'seconds': True}, {'timeout_seconds': 61},
                       {'timeout_seconds': 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(fixtures.FixtureError):
                fixtures.build_fixture('phone', self.base / 'bounds', **kwargs)
        with self.assertRaises(fixtures.FixtureError):
            fixtures.build_fixture('bogus', self.base / 'bounds')
        with self.assertRaises(fixtures.FixtureError):
            fixtures.run(['true'], 61)
        existing = Path(self.fixtures['phone']['path'])
        before = file_identity(existing)
        with self.assertRaises(fixtures.FixtureError):
            fixtures.build_fixture('phone', self.fixture_dir)
        self.assertEqual(file_identity(existing), before)
        for kind, receipt in self.fixtures.items():
            with self.subTest(kind=kind):
                for command in receipt['commands']:
                    self.assertEqual(command[0], self.environment['FFMPEG'])
                    for flag in ('-nostdin', '-n'):
                        self.assertIn(flag, command)
                    self.assertEqual(command[command.index('-threads') + 1], '2')
                self.assertEqual(receipt['binaries']['ffmpeg']['sha256'], QUALIFIED_SHA['ffmpeg'])
                self.assertEqual(receipt['binaries']['ffprobe']['sha256'], QUALIFIED_SHA['ffprobe'])
                self.assertLessEqual(receipt['measured']['audio_end_seconds'], fixtures.MAX_SECONDS + 1)
                self.assertNotEqual(Path(receipt['path']).resolve(), Path(REAL_TAKE))
        self.assertEqual(fixtures.MAX_TIMEOUT, 60)

    @retain_on_failure
    def test_phone_fixture_properties(self):
        measured = self.fixtures['phone']['measured']
        self.assertEqual(measured['rotation'], 90)  # Sign exactly as ffprobe reports the display matrix.
        self.assertEqual((measured['width'], measured['height'], measured['video_codec']), (360, 640, 'h264'))
        self.assertEqual((measured['channels'], measured['sample_rate'], measured['audio_codec']), (2, 48000, 'aac'))
        self.assertEqual(measured['video_time_base'], '1/30000')
        self.assertGreaterEqual(len(measured['frame_duration_ticks']), 2)
        self.assertLessEqual(abs(measured['audio_start_seconds'] - 0.25), 1024 / 48000 + 0.002)
        self.assertGreater(measured['audio_end_minus_video_end_seconds'], 0)
        self.assertEqual(self.fixtures['phone']['unknown']['rotation_applied_to_pixels'], False)

    @retain_on_failure
    def test_photo_booth_fixture_properties(self):
        measured = self.fixtures['photo_booth']['measured']
        self.assertEqual((measured['width'], measured['height'], measured['video_codec']), (1280, 720, 'h264'))
        self.assertEqual((measured['channels'], measured['sample_rate']), (1, 44100))
        self.assertEqual(measured['video_time_base'], '1/600')
        self.assertEqual(measured['frame_duration_ticks'], [24, 25, 26])
        self.assertLessEqual(abs(measured['audio_end_minus_video_end_seconds'] - 0.069), 1024 / 44100 + 0.002)
        self.assertIs(self.fixtures['photo_booth']['unknown']['real_take_audio_tail_reconciled'], False)

    @retain_on_failure
    def test_preroll_fixture_has_decode_only_packets(self):
        measured = self.fixtures['photo_booth_preroll']['measured']
        self.assertGreaterEqual(measured['decode_only_packets'], 1)
        self.assertEqual(measured['presented_frames'], measured['coded_video_packets'] - measured['decode_only_packets'])
        packets = fixtures.video_packets(Path(self.fixtures['photo_booth_preroll']['path']))
        self.assertTrue(all(int(packet['pts']) < 0 for packet in packets if 'D' in packet.get('flags', '')))
        self.assertEqual(measured['video_time_base'], '1/600')

    # ------------------------------------------------------------------ pipeline matrix (P1-P8)
    @retain_on_failure
    def test_phone_pipeline_conservative3(self):
        self.pipeline('phone', 'conservative3')

    @retain_on_failure
    def test_photo_booth_pipeline_conservative3(self):
        self.pipeline('photo_booth', 'conservative3')

    @retain_on_failure
    def test_preroll_pipeline_conservative3(self):
        self.pipeline('photo_booth_preroll', 'conservative3')

    @retain_on_failure
    def test_phone_pipeline_fuller_with_synthetic_capture_interval(self):
        self.pipeline('phone', 'fuller')

    @retain_on_failure
    def test_photo_booth_pipeline_fuller_with_synthetic_capture_interval(self):
        before_runs = self.published_runs()
        invocations = self.root / 'artifacts/demo-invocations'
        before_invocations = sorted(invocations.iterdir()) if invocations.is_dir() else []
        refused = self.run_demo(self.fixtures['photo_booth']['path'], '--profile', 'fuller', '--no-latest')
        self.assertEqual(refused.returncode, 1)
        self.assertEqual(json.loads(refused.stderr.strip().splitlines()[-1])['reason'], 'capture_interval_required')
        self.assertEqual(self.published_runs(), before_runs)
        self.assertEqual(sorted(invocations.iterdir()) if invocations.is_dir() else [], before_invocations)
        self.pipeline('photo_booth', 'fuller')

    @retain_on_failure
    def test_preroll_pipeline_fuller_with_synthetic_capture_interval(self):
        self.pipeline('photo_booth_preroll', 'fuller')

    @retain_on_failure
    def test_phone_hevc_pipeline_conservative3(self):
        if not self.hevc:
            type(self).results.append({'kind': 'phone_hevc', 'profile': 'conservative3', 'status': 'skipped_encoder_absent'})
            self.skipTest('libx265 encoder absent from the qualified ffmpeg')
        self.pipeline('phone_hevc', 'conservative3')


if __name__ == '__main__':
    unittest.main()
