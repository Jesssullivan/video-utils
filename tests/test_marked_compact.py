"""marked_compact: exact copy-only composition of a verified audio run and arrangement preview.

Generated tiny movies only; no listening, visual or musical claim. Spec:
docs/spec/sprints/FULLER_S2.md section 4.3 and section 6.
"""
import contextlib
import copy
from fractions import Fraction
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import arrangement_markers as adapter  # noqa: E402
import arrangement_reference as assessment_tool  # noqa: E402
import marked_compact as compact  # noqa: E402
import marked_video as preview  # noqa: E402

SECTION5 = ('capture_noise_only_verified', 'capture_music_status', 'capture_click_status',
            'physical_audio_video_sync_verified', 'fundamental_32hz_restoration_claimed',
            'per_passage_level_matched', 'composite_visual_review_performed', 'composite_listening_review',
            'markers_are_analysis_of_audio_branch', 'performance_issue_confirmed', 'note_correctness_assessed',
            'master_adopted', 'latest_promoted', 'default_profile_changed_by_lane',
            'native_editor_import_verified', 'listening_acceptance', 'accepted_audio_identity',
            'tone_suitability_other_takes')
ACCEPTED_RUN = Path('/Users/jess/git/video-utils/artifacts/runs/20261006T041633Z-990aa1bd6737')


def accepted_stub():
    """Manifest fragment built only from the embedded accepted constants."""
    a = compact.ACCEPTED
    commands = [['ffmpeg', '-i', 'latency.wav', '-af', a['L'], 'latency.f32'],
                ['ffmpeg', '-i', 'source.wav', '-filter_complex', a['C'], '-map', '[out]', 'denoised.wav'],
                ['ffmpeg', '-i', 'denoised.wav', '-af', a['P'], 'processed.wav']]
    commands += [['ffmpeg', '-i', 'x.wav', '-af', a['N'] + ':print_format=json', '-f', 'null', '-']] * 6
    return {'source': {'sha256': a['source_sha256']}, 'pcm': dict(a['pcm'], codec='pcm_f32le'),
            'noise_capture': {'selected_samples': list(a['capture_samples']),
                              'filter_delay_samples_removed': a['delay_samples']},
            'tools': {'ffmpeg': a['ffmpeg_version']}, 'commands': commands}


def gate_inputs():
    sha = 'a' * 64
    pcm = {'sample_rate': 48000, 'channels': 1, 'sample_count': 96000}
    timeline = {'audio_start_seconds': 0.0, 'format_start_seconds': 0.0, 'no_time_stretch': True}
    run_manifest = {'source': {'sha256': sha}, 'pcm': dict(pcm), 'timeline': dict(timeline)}
    export = {'source_sha256': sha, 'verification': dict({key: True for key in compact.EXPORT_TRUE},
              video_packet_expected_translation_seconds=0.0, physical_audio_video_sync_verified=False)}
    bindings = {key: None for key in compact.BINDING_KEYS}
    bindings['source_sha256'] = sha
    outcome = {'status': 'marked_review_preview_verified_unreviewed', 'marker_mode': 'arrangement_reference_review',
               'arrangement_marker_selector': 'arrangement-markers.json', 'source_sha256': sha,
               'source_container_start_seconds': 0.0, 'arrangement_marker_bindings': bindings,
               'verification': dict({key: True for key in compact.PREVIEW_TRUE},
                                    physical_audio_video_sync_verified=False, decoded_video_frame_count=21,
                                    decoded_video_first_pts_seconds=0.0, decoded_video_last_extent_seconds=2.0)}
    preview_manifest = {'source': {'sha256': sha}, 'pcm': dict(pcm), 'timeline': dict(timeline)}
    return run_manifest, export, outcome, preview_manifest


class PacketIdentityTests(unittest.TestCase):
    def rows(self):
        return [{'pts': index * 600, 'dts': index * 600, 'duration': 600, 'data_hash': f'SHA256:{index}',
                 'side_data_list': [{'side_data_type': 'Skip Samples', 'skip_samples': 1024 if index == 0 else 0,
                                     'discard_padding': 0}]} for index in range(3)]

    def test_equal_rational_times_in_different_time_bases_are_accepted(self):
        before = self.rows()
        after = [dict(row, pts=row['pts'] * 150, dts=row['dts'] * 150, duration=row['duration'] * 150)
                 for row in before]
        self.assertEqual(compact.exact_packets(before, after, '1/600', '1/90000', audio=True), 3)

    def test_shift_payload_and_padding_changes_are_rejected(self):
        before = self.rows()
        mutations = [lambda rows: rows[1].update(pts=rows[1]['pts'] + 1),
                     lambda rows: rows[2].update(data_hash='SHA256:other'),
                     lambda rows: rows[0]['side_data_list'][0].update(skip_samples=0),
                     lambda rows: rows[2]['side_data_list'][0].update(discard_padding=17),
                     lambda rows: rows.pop()]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                after = copy.deepcopy(before)
                mutate(after)
                with self.assertRaises(compact.CompactError) as caught:
                    compact.exact_packets(before, after, '1/600', '1/600', audio=True)
                self.assertEqual(caught.exception.code, 'packet_identity_failed')


class BranchGateTests(unittest.TestCase):
    def test_valid_generalized_gate_reads_extent_from_preview(self):
        result = compact.branch_gate(*gate_inputs(), 'arrangement-markers.json')
        self.assertEqual(result['picture_extent'], Fraction(2))
        self.assertEqual(result['native_pcm']['sample_count'], 96000)

    def test_each_branch_refusal_has_its_typed_reason(self):
        cases = {
            'source_mismatch': lambda r, e, o, p: e.update(source_sha256='b' * 64),
            'native_pcm_mismatch': lambda r, e, o, p: p['pcm'].update(sample_count=95999),
            'nonzero_origin_unsupported': lambda r, e, o, p: r['timeline'].update(audio_start_seconds=2.0),
            'export_unverified': lambda r, e, o, p: e['verification'].update(final_true_peak_within_target=None),
            'preview_unverified': lambda r, e, o, p: o.update(status='failed_preview_preserving_inputs'),
            'arrangement_markers_mismatch': lambda r, e, o, p: o.update(arrangement_marker_selector='other.json'),
        }
        extra = {'nonzero_origin_unsupported': [lambda r, e, o, p: o.update(source_container_start_seconds=2.0),
                                                lambda r, e, o, p: p['timeline'].pop('no_time_stretch')],
                 'export_unverified': [lambda r, e, o, p: e['verification'].update(
                     video_packet_expected_translation_seconds=-2.0),
                     lambda r, e, o, p: e['verification'].update(physical_audio_video_sync_verified=True)],
                 'preview_unverified': [lambda r, e, o, p: o.update(marker_mode=None),
                                        lambda r, e, o, p: o['verification'].update(decoded_video_frame_pts_preserved=False)]}
        for reason, mutate in cases.items():
            for index, change in enumerate([mutate, *extra.get(reason, [])]):
                with self.subTest(reason=reason, variant=index):
                    inputs = gate_inputs()
                    change(*inputs)
                    with self.assertRaises(compact.CompactError) as caught:
                        compact.branch_gate(*inputs, 'arrangement-markers.json')
                    self.assertEqual(caught.exception.code, reason)


class OutputPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        handle = patch.object(compact, 'ROOT', self.root)
        handle.start()
        self.addCleanup(handle.stop)
        self.parent = self.root / 'artifacts/experiments/parent-run'
        self.parent.mkdir(parents=True)

    def assert_invalid(self, value):
        with self.assertRaises(compact.CompactError) as caught:
            compact.output_directory(value, (self.parent,))
        self.assertEqual(caught.exception.code, 'output_invalid')

    def test_fresh_artifacts_child_is_accepted(self):
        self.assertEqual(compact.output_directory('artifacts/s2/out', (self.parent,)), self.root / 'artifacts/s2/out')
        self.assertTrue(compact.default_output().is_relative_to(self.root / 'artifacts/experiments'))

    def test_existing_symlinked_inside_parent_and_runs_targets_rejected(self):
        existing = self.root / 'artifacts/experiments/existing'
        existing.mkdir()
        self.assert_invalid(existing)
        real = self.root / 'artifacts/real'
        real.mkdir()
        (self.root / 'artifacts/alias').symlink_to(real)
        self.assert_invalid(self.root / 'artifacts/alias/out')
        self.assert_invalid(self.parent / 'nested-output')
        self.assert_invalid(self.root / 'artifacts/runs/new-output')
        self.assert_invalid(self.root / 'elsewhere/out')
        self.assert_invalid('artifacts/../outside')
        self.assert_invalid(self.root / 'artifacts')

    def test_cli_reports_typed_reason_json(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = compact.main([str(self.parent), '--picture-preview', str(self.parent),
                                 '--arrangement-markers', 'a.json', '--output', 'artifacts/runs/x'])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(err.getvalue())['reason'], 'output_invalid')
        self.assertFalse((self.root / 'artifacts/runs/x').exists())


class ChainIdentityTests(unittest.TestCase):
    def test_identical_chain_with_byte_identical_audio_carries_accepted_label(self):
        result = compact.chain_identity(accepted_stub(), compact.ACCEPTED['cleaned_sha256'],
                                        compact.ACCEPTED['export_video_sha256'])
        self.assertEqual(result['chain_class'], 'identical_accepted_fuller_v1')
        self.assertEqual(result['listening_acceptance'], compact.ACCEPTED_LABEL)
        self.assertEqual(result['accepted_audio_identity'], 'byte_identical')

    def test_identical_chain_with_different_audio_is_not_performed(self):
        result = compact.chain_identity(accepted_stub(), 'c' * 64)
        self.assertEqual(result['chain_class'], 'identical_accepted_fuller_v1')
        self.assertEqual(result['listening_acceptance'], 'not_performed')
        self.assertEqual(result['listening_acceptance_reason'], 'chain_identical_audio_differs')
        self.assertEqual(result['accepted_audio_identity'], 'differs')
        export = compact.chain_identity(accepted_stub(), compact.ACCEPTED['cleaned_sha256'], 'd' * 64)
        self.assertEqual((export['listening_acceptance'], export['listening_acceptance_reason']),
                         ('not_performed', 'chain_identical_export_differs'))
        unknown = compact.chain_identity(accepted_stub())
        self.assertEqual((unknown['listening_acceptance'], unknown['accepted_audio_identity']),
                         ('not_performed', 'not_compared'))

    def test_other_interval_is_template_binding_without_acceptance(self):
        stub = accepted_stub()
        stub['noise_capture']['selected_samples'] = [8820, 46305]
        stub['commands'][1][4] = compact.capture_template(8820, 46305, 6657385, 44100, 1102)
        result = compact.chain_identity(stub, compact.ACCEPTED['cleaned_sha256'])
        self.assertEqual(result['chain_class'], 'fuller_v1_template_other_binding')
        self.assertEqual(result['listening_acceptance'], 'not_performed')
        self.assertEqual(result['accepted_audio_identity'], 'not_compared')

    def test_changed_eq_is_not_fuller_v1(self):
        stub = accepted_stub()
        stub['commands'][2][4] = stub['commands'][2][4].replace('g=2:', 'g=3:')
        result = compact.chain_identity(stub, compact.ACCEPTED['cleaned_sha256'])
        self.assertEqual(result['chain_class'], 'not_fuller_v1')
        self.assertEqual(result['listening_acceptance'], 'not_performed')
        empty = compact.chain_identity({})
        self.assertEqual(empty['chain_class'], 'not_fuller_v1')

    def test_actual_accepted_manifest_is_identical_when_present(self):
        manifest = ACCEPTED_RUN / 'manifest.json'
        if not manifest.is_file():
            self.skipTest('accepted run not present on this host (read-only check)')
        before = compact.sha256(manifest)
        payload, _ = compact.read_json(manifest, 'run_dir_invalid')
        result = compact.chain_identity(payload, payload['output_sha256']['cleaned.wav'])
        self.assertEqual(result['chain_class'], 'identical_accepted_fuller_v1')
        self.assertEqual(result['listening_acceptance'], compact.ACCEPTED_LABEL)
        self.assertEqual(compact.sha256(manifest), before)

    def test_claim_fields_never_omit_unknowns(self):
        fields = compact.claim_fields()
        self.assertTrue(set(SECTION5) <= set(fields))
        self.assertIsNone(fields['markers_are_analysis_of_audio_branch'])
        self.assertIn('markers_are_analysis_of_audio_branch_reason', fields)
        self.assertEqual(fields['listening_acceptance'], 'not_performed')


class RealMarkedCompactTests(unittest.TestCase):
    """Real tiny VFR movie: arrangement preview + separate same-source audio run."""

    def setUp(self):
        self.ffmpeg = os.environ.get('FFMPEG') or shutil.which('ffmpeg')
        self.ffprobe = os.environ.get('FFPROBE') or shutil.which('ffprobe')
        if not self.ffmpeg or not self.ffprobe:
            self.skipTest('Explicit FFmpeg/FFprobe required for generated composition proof')
        spec = importlib.util.spec_from_file_location('marked_compact_tiny_fixture', REPO / 'tests/test_marked_video.py')
        self.fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.fixture)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for module, name in ((preview, 'ROOT'), (preview.marker_tool, 'ROOT'), (adapter, 'ROOT'),
                             (compact, 'ROOT')):
            handle = patch.object(module, name, self.root)
            handle.start()
            self.addCleanup(handle.stop)
        handle = patch.dict(os.environ, {'FFMPEG': self.ffmpeg, 'FFPROBE': self.ffprobe})
        handle.start()
        self.addCleanup(handle.stop)
        self.preview_run, self.preview_dir = self.build_preview()

    def ff(self, *arguments):
        subprocess.run([self.ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'error', '-threads', '2', *arguments],
                       check=True, capture_output=True, timeout=60)

    def build_preview(self):
        """Arrangement pattern of test_arrangement_markers at source origin 0."""
        run = self.root / 'artifacts/runs/candidate'
        (self.root / 'program').mkdir(parents=True)
        self.fixture.create_verified_fixture(run, self.ffmpeg, self.ffprobe, origin=0., vfr=True)
        shutil.copyfile(run / 'cleaned.wav', run / 'denoised.wav')
        stream = json.loads(subprocess.run([self.ffprobe, '-v', 'error', '-show_streams', '-of', 'json',
                                            str(run / 'denoised.wav')], check=True, capture_output=True,
                                           timeout=20).stdout)['streams'][0]
        rate = int(stream['sample_rate'])
        pcm = {'sample_rate': rate, 'sample_count': int(stream['duration_ts']), 'channels': 1}
        manifest = json.loads((run / 'manifest.json').read_text())
        manifest['output_sha256']['denoised.wav'] = adapter.digest(run / 'denoised.wav')
        manifest['pcm'] = pcm
        manifest['timeline']['no_time_stretch'] = True
        (run / 'manifest.json').write_text(json.dumps(manifest))
        graph = json.loads((run / 'dag.json').read_text())
        graph['artifact_hashes']['manifest.json'] = adapter.digest(run / 'manifest.json')
        (run / 'dag.json').write_text(json.dumps(graph))
        canonical, _ = preview.marker_tool.build(run)
        (run / 'markers.json').write_text(json.dumps(canonical))
        for name in ('analysis.json', 'phrases.json'):
            (run / name).write_text('{}')
        reference = json.loads((REPO / 'program/demo-arrangement.json').read_text())
        reference['source_sha256'] = manifest['source']['sha256']
        reference['anchors']['first_phrase_source_seconds'] = [0.2, 0.3]
        reference['sections'] = [{'id': 'outro_tapping', 'label': 'Toy intended tapping',
                                  'kind': 'phrase', 'phrase_count': 1, 'clicks_per_phrase': 4}]
        reference_path = self.root / 'program/demo-arrangement.json'
        reference_path.write_text(json.dumps(reference))
        input_hash = adapter.digest(run / 'denoised.wav')
        observations = {'schema_version': 1, 'source_sha256': reference['source_sha256'],
                        'analyzed_input_sha256': input_hash,
                        'timeline': {'source_start_seconds': 0., 'duration_seconds': pcm['sample_count'] / rate,
                                     'native_pcm': pcm}, 'boundaries': []}
        assessment = assessment_tool.align_arrangement(reference, observations)
        binding = {name: {'path': str(run / (name + '.json')), 'sha256': adapter.digest(run / (name + '.json'))}
                   for name in ('manifest', 'analysis', 'phrases')}
        binding['reference'] = {'path': str(reference_path), 'sha256': adapter.digest(reference_path)}
        binding['analyzed_input_sha256'] = input_hash
        binding['input_hashes'] = {name: adapter.digest(run / name) for name in
                                   ('manifest.json', 'analysis.json', 'phrases.json', 'denoised.wav')}
        assessment['binding'] = binding
        assessment['reference'].update(binding['reference'])
        (run / 'arrangement').mkdir()
        (run / 'arrangement/assessment.json').write_text(json.dumps(assessment))
        marker, _ = adapter.build(run, 'arrangement/assessment.json')
        (run / 'arrangement/arrangement-markers.json').write_text(json.dumps(marker))
        output = run / 'reference-marked-preview-compact'
        result = preview.render(run, output, selection='all-review',
                                arrangement_markers='arrangement/arrangement-markers.json')
        self.assertEqual(result['status'], 'marked_review_preview_verified_unreviewed')
        return run, output

    def build_audio_run(self, name='audio', duration=None):
        """Second same-source run whose AAC differs (volume re-encode of the original)."""
        run = self.root / 'artifacts/runs' / name
        (run / 'export').mkdir(parents=True)
        original = self.preview_run / 'original.mov'
        video = run / 'export/cleaned-video.mov'
        self.ff('-i', str(original), '-map', '0:v:0', '-map', '0:a:0', '-c:v', 'copy', '-af', 'volume=0.5',
                '-c:a', 'aac', '-b:a', '128k', *(['-t', str(duration)] if duration else []), str(video))
        cleaned = run / 'cleaned.wav'
        self.ff('-i', str(video), '-map', '0:a:0', '-c:a', 'pcm_s24le', str(cleaned))
        shutil.copyfile(cleaned, run / 'denoised.wav')
        preview_manifest = json.loads((self.preview_run / 'manifest.json').read_text())
        source = preview_manifest['source']['sha256']
        manifest = {'schema_version': 1, 'run_dir': str(run), 'source': {'path': str(original), 'sha256': source},
                    'pcm': dict(preview_manifest['pcm']),
                    'timeline': {'format_start_seconds': 0.0, 'audio_start_seconds': 0.0, 'no_time_stretch': True},
                    'output_sha256': {'cleaned.wav': adapter.digest(cleaned),
                                      'denoised.wav': adapter.digest(run / 'denoised.wav')},
                    'commands': [], 'tools': {'ffmpeg': 'fixture'}, 'noise_capture': None}
        (run / 'manifest.json').write_text(json.dumps(manifest))
        verification = {key: True for key in compact.EXPORT_TRUE}
        verification.update(video_packet_expected_translation_seconds=0.0, physical_audio_video_sync_verified=False)
        export = {'source_sha256': source, 'video': str(video), 'audio_master': str(cleaned),
                  'output_sha256': {'cleaned-video.mov': adapter.digest(video)}, 'verification': verification,
                  'final_audio_loudness': {'input_i': 'fixture_not_acceptance'}}
        (run / 'export/outcome.json').write_text(json.dumps(export))
        return run

    def tree_hashes(self):
        base = self.root / 'artifacts/runs'
        return {path: adapter.digest(path) for path in base.rglob('*') if path.is_file()}

    def pcm_hash(self, path):
        return subprocess.run([self.ffmpeg, '-hide_banner', '-nostdin', '-loglevel', 'error', '-threads', '2',
                               '-i', str(path), '-map', '0:a:0', '-vn', '-c:a', 'pcm_f32le', '-f', 'hash',
                               '-hash', 'sha256', '-'], check=True, capture_output=True, timeout=60).stdout.strip()

    def packet_count(self, path, selector):
        rows = json.loads(subprocess.run([self.ffprobe, '-v', 'error', '-select_streams', selector, '-show_packets',
                                          '-show_entries', 'packet=pts', '-of', 'json', str(path)], check=True,
                                         capture_output=True, timeout=60).stdout)['packets']
        return len(rows)

    def compose(self, audio_run, output_name='out'):
        return compact.compose(audio_run, self.preview_dir, 'arrangement/arrangement-markers.json',
                               self.root / 'artifacts/experiments' / output_name, 120)

    def assert_failure(self, audio_run, reason, output_name='out'):
        output = self.root / 'artifacts/experiments' / output_name
        with self.assertRaises(compact.CompactError) as caught:
            self.compose(audio_run, output_name)
        self.assertEqual(caught.exception.code, reason)
        failure = json.loads((output / 'failure.json').read_text())
        self.assertEqual(failure['status'], compact.STATUS_FAILED)
        self.assertEqual(failure['reason'], reason)
        self.assertFalse((output / 'receipt.json').exists())
        for key in SECTION5:
            self.assertIn(key, failure)
        self.assertEqual(failure['listening_acceptance'], 'not_performed')
        return failure

    def test_compose_copies_picture_and_audio_branch_exactly(self):
        audio_run = self.build_audio_run()
        before = self.tree_hashes()
        receipt = self.compose(audio_run)
        self.assertEqual(receipt['status'], compact.STATUS_OK)
        output = Path(receipt['output'])
        picture = self.preview_dir / 'marked-video.mov'
        audio = audio_run / 'export/cleaned-video.mov'
        k, m = self.packet_count(picture, 'v:0'), self.packet_count(audio, 'a:0')
        self.assertEqual(receipt['video_packets_identical'], f'{k}/{k}')
        self.assertEqual(receipt['aac_packets_identical'], f'{m}/{m}')
        self.assertEqual(self.packet_count(output, 'v:0'), k)
        self.assertEqual(self.pcm_hash(output), self.pcm_hash(audio))
        self.assertEqual(receipt['decoded_aac_pcm_sha256'], self.pcm_hash(audio).decode())
        self.assertNotEqual(self.pcm_hash(output), self.pcm_hash(picture))
        self.assertEqual(compact.sha256(output), receipt['output_sha256'])
        self.assertEqual(self.tree_hashes(), before)
        self.assertTrue(receipt['input_hashes_preserved'])
        for key in SECTION5:
            self.assertIn(key, receipt)
        self.assertEqual(receipt['listening_acceptance'], 'not_performed')
        self.assertEqual(receipt['accepted_audio_identity'], 'not_compared')
        self.assertEqual(receipt['chain_identity']['chain_class'], 'not_fuller_v1')
        self.assertIs(receipt['markers_are_analysis_of_audio_branch'], False)
        self.assertEqual(receipt['composite_listening_review'], 'not_performed')
        self.assertIs(receipt['new_audio_dsp'], False)
        self.assertEqual(oct((output.parent).stat().st_mode & 0o777), '0o700')
        for name in ('start.json', 'parent-video-packets.json', 'parent-audio-packets.json',
                     'output-video-packets.json', 'output-audio-packets.json', 'receipt.json'):
            self.assertTrue((output.parent / name).is_file(), name)
        self.assertFalse((output.parent / 'failure.json').exists())
        with self.assertRaises(compact.CompactError) as caught:
            self.compose(audio_run)
        self.assertEqual(caught.exception.code, 'output_invalid')

    def test_edited_arrangement_markers_refuse(self):
        audio_run = self.build_audio_run()
        markers = self.preview_run / 'arrangement/arrangement-markers.json'
        payload = json.loads(markers.read_text())
        payload['markers'][0]['display_label'] = 'Confirmed mistake'
        markers.write_text(json.dumps(payload))
        self.assert_failure(audio_run, 'arrangement_markers_mismatch')

    def test_audio_shorter_than_picture_refuses(self):
        audio_run = self.build_audio_run('short', duration=1.5)
        failure = self.assert_failure(audio_run, 'audio_does_not_cover_picture')
        self.assertTrue(failure['input_hashes_preserved'])

    def test_input_mutated_mid_run_refuses(self):
        audio_run = self.build_audio_run()
        selection = self.preview_dir / 'selection.json'
        original = compact.decoded_pcm_hash
        calls = []

        def mutate_after_compose(session, path):
            calls.append(path)
            if len(calls) == 2:
                with selection.open('a') as handle:
                    handle.write('\n')
            return original(session, path)

        with patch.object(compact, 'decoded_pcm_hash', mutate_after_compose):
            failure = self.assert_failure(audio_run, 'input_changed')
        self.assertIs(failure['input_hashes_preserved'], False)


if __name__ == '__main__':
    unittest.main()
