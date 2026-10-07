"""Independent source-bound intent windows, marker admission and overlay labels."""
import copy
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

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import arrangement_markers as adapter
import arrangement_reference as assessment_tool
import marked_video as preview


class ArrangementMarkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.run = self.root / 'artifacts/runs/candidate'
        self.run.mkdir(parents=True)
        (self.root / 'program').mkdir()
        self.reference = json.loads((REPO / 'program/demo-arrangement.json').read_text())
        self.reference['source_sha256'] = 'a' * 64
        self.reference['sections'] = [{'id': 'verse1_open', 'label': 'Verse intent',
            'kind': 'phrase', 'phrase_count': 1, 'clicks_per_phrase': 16}]
        self.reference_path = self.root / 'program/demo-arrangement.json'
        self.reference_path.write_text(json.dumps(self.reference))
        (self.run / 'denoised.wav').write_bytes(b'metadata test placeholder, no audio processing')
        input_hash = adapter.digest(self.run / 'denoised.wav')
        manifest = {'schema_version': 1, 'source': {'sha256': 'a' * 64},
            'output_sha256': {'denoised.wav': input_hash},
            'timeline': {'audio_start_seconds': 0, 'no_time_stretch': True},
            'pcm': {'sample_rate': 44100, 'sample_count': 6657385, 'channels': 1}}
        for name, payload in [('manifest', manifest), ('analysis', {}), ('phrases', {})]:
            (self.run / (name + '.json')).write_text(json.dumps(payload))
        self.binding = {name: {'path': str(self.run / (name + '.json')),
            'sha256': adapter.digest(self.run / (name + '.json'))} for name in ('manifest', 'analysis', 'phrases')}
        self.binding['reference'] = {'path': str(self.reference_path), 'sha256': adapter.digest(self.reference_path)}
        self.binding['analyzed_input_sha256'] = input_hash
        self.binding['input_hashes'] = {name: adapter.digest(self.run / name) for name in
                                      ('manifest.json', 'analysis.json', 'phrases.json', 'denoised.wav')}
        self.observations = {'schema_version': 1, 'source_sha256': 'a' * 64,
            'analyzed_input_sha256': input_hash,
            'timeline': {'source_start_seconds': 0, 'duration_seconds': 6657385 / 44100,
                         'native_pcm': manifest['pcm']},
            'boundaries': []}
        handle = patch.object(adapter, 'ROOT', self.root)
        handle.start()
        self.addCleanup(handle.stop)
        self.write_assessment()

    def write_assessment(self, observations=None):
        assessment = assessment_tool.align_arrangement(self.reference, observations or self.observations)
        assessment['binding'] = copy.deepcopy(self.binding)
        assessment['reference'].update(self.binding['reference'])
        (self.run / 'assessment.json').write_text(json.dumps(assessment))
        return assessment

    def test_intent_core_retains_anchor_uncertainty_without_selecting_phase(self):
        payload, _ = adapter.build(self.run, 'assessment.json')
        intent = next(row for row in payload['markers'] if row['name'] == 'arrangement_intended_unit')
        self.assertEqual(intent['source_time_seconds'], 11)
        self.assertAlmostEqual(intent['end_seconds'], 10 + 16 * 60 / 178)
        self.assertEqual(intent['label_basis'], 'operator_intent_clock_window_core_not_observed_section')
        self.assertEqual(intent['evidence']['start_window'], [10, 11])
        self.assertIn('INTENT/time estimate', intent['display_label'])
        boundaries = [r for r in payload['markers'] if r['name'] == 'arrangement_boundary_review']
        self.assertEqual((boundaries[0]['source_time_seconds'], boundaries[0]['end_seconds']), (10, 11))
        self.assertTrue(all(r['performance_issue_confirmed'] is False for r in payload['markers']))

    def test_observed_alignment_is_separate_from_intended_section_label(self):
        obs = copy.deepcopy(self.observations)
        obs['boundaries'] = [{'id': 'a', 'source_seconds': 10.2, 'confidence': 'unvalidated', 'evidence': 'toy boundary'},
                            {'id': 'b', 'source_seconds': 15.6, 'confidence': 'unvalidated', 'evidence': 'toy boundary'}]
        self.write_assessment(obs)
        payload, _ = adapter.build(self.run, 'assessment.json')
        aligned = next(r for r in payload['markers'] if r['name'] == 'arrangement_aligned_unit_review')
        self.assertEqual((aligned['source_time_seconds'], aligned['end_seconds']), (10.2, 15.6))
        self.assertIn('ALIGNMENT CANDIDATE', aligned['display_label'])
        self.assertIsNone(aligned['evidence']['observed']['observed_click_count'])

    def test_mutated_marker_or_reference_or_cached_input_is_rejected(self):
        payload, _ = adapter.build(self.run, 'assessment.json')
        marker = self.run / 'alternate.json'
        marker.write_text(json.dumps(payload))
        self.assertEqual(adapter.load_validated(self.run, 'alternate.json')[0], payload)
        changed = copy.deepcopy(payload)
        changed['markers'][0]['display_label'] = 'Confirmed mistake'
        marker.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, 'stale or edited'):
            adapter.load_validated(self.run, 'alternate.json')
        (self.run / 'analysis.json').write_text('{}\n')
        with self.assertRaisesRegex(ValueError, 'cached binding mismatch'):
            adapter.build(self.run, 'assessment.json')

    def test_repo_relative_reference_identity_is_exact_and_supported(self):
        assessment = json.loads((self.run / 'assessment.json').read_text())
        for row in (assessment['reference'], assessment['binding']['reference']):
            row['path'] = 'program/demo-arrangement.json'
        (self.run / 'assessment.json').write_text(json.dumps(assessment))
        self.assertEqual(adapter.build(self.run, 'assessment.json')[0]['reference']['selector'],
                         'program/demo-arrangement.json')
        assessment['binding']['reference']['path'] = '../program/demo-arrangement.json'
        (self.run / 'assessment.json').write_text(json.dumps(assessment))
        with self.assertRaisesRegex(ValueError, 'reference binding'):
            adapter.build(self.run, 'assessment.json')

    def test_wrong_source_input_count_extent_or_confirmed_claim_fails(self):
        baseline = json.loads((self.run / 'assessment.json').read_text())
        for key, value in [('source_sha256', 'b' * 64), ('analyzed_input_sha256', 'c' * 64),
                           ('observed_click_count', 404), ('performance_issue_confirmed', True)]:
            with self.subTest(key=key):
                changed = copy.deepcopy(baseline)
                changed[key] = value
                (self.run / 'assessment.json').write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    adapter.build(self.run, 'assessment.json')
        changed = copy.deepcopy(baseline)
        changed['timeline']['duration_seconds'] += 1
        (self.run / 'assessment.json').write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, 'native source extent'):
            adapter.build(self.run, 'assessment.json')

    def test_forged_intended_label_or_exact_phase_fails(self):
        baseline = json.loads((self.run / 'assessment.json').read_text())
        for mutation in ('label', 'phase'):
            changed = copy.deepcopy(baseline)
            if mutation == 'label':
                changed['units'][0]['expected']['label'] = 'Wrong intended section'
            else:
                changed['review_candidates'][0]['source_time_seconds'] = 10.5
                changed['review_candidates'][0]['end_seconds'] = 10.5
            (self.run / 'assessment.json').write_text(json.dumps(changed))
            with self.assertRaises(ValueError):
                adapter.build(self.run, 'assessment.json')

    def test_path_bounds_symlink_duplicate_and_nonfinite_rejected(self):
        for name in ('../assessment.json', '/assessment.json', '.private/a.json', 'a//b', 'x:y', 'a\\b'):
            with self.assertRaises(ValueError):
                adapter.selector(self.run, name)
        (self.run / 'alias.json').symlink_to(self.run / 'assessment.json')
        with self.assertRaises(ValueError):
            adapter.selector(self.run, 'alias.json')
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}', '{"a":' + '[' * 25 + '0' + ']' * 25 + '}'):
            (self.run / 'bad.json').write_text(raw)
            with self.assertRaises(ValueError):
                adapter.read_json(self.run / 'bad.json')

    def test_renderer_custom_labels_only_in_explicit_validated_alternate_mode(self):
        payload, _ = adapter.build(self.run, 'assessment.json')
        selected, _ = preview.select_markers(payload['markers'], 'all-review', 0, 0, 150.9, arrangement_labels=True)
        self.assertTrue(any('Expected' in r['label'] for r in selected))
        self.assertTrue(any('INTENT' in r['full_display_label'] for r in selected))
        self.assertTrue(all('label_basis' in r for r in selected))
        canonical, _ = preview.select_markers(payload['markers'], 'all-review', 0, 0, 150.9)
        self.assertTrue(all(r['label'] == 'Review candidate' for r in canonical))
        with patch.object(preview, 'local_directory', side_effect=lambda value, **kw: value):
            with self.assertRaisesRegex(ValueError, 'explicit all-review'):
                preview.render(self.run, self.run / 'out', arrangement_markers='alternate.json')

    def test_compact_same_phrase_labels_preserve_visible_ids_and_accounting(self):
        rows = []
        for kind, text in [('arrangement_aligned_unit_review', 'ALIGNMENT CANDIDATE'),
                           ('arrangement_boundary_review', 'REVIEW boundary estimate')]:
            rows.append({'name': kind, 'source_time_seconds': 1, 'end_seconds': 2,
                'display_label': text + ': Chorus 2 (presumed repeat) phrase 2',
                'label_basis': 'unvalidated_reference_conditioned', 'evidence': {}})
        selected, _ = preview.select_markers(rows, 'all-review', 0, 0, 3, arrangement_labels=True)
        full, full_coverage = preview.compose_callouts(selected, 0)
        compact, compact_coverage = preview.compose_callouts(selected, 0, arrangement_labels=True)
        self.assertEqual(compact[0]['labels'], ['Chorus 2 · phrase 2 | Timing review'])
        self.assertEqual(compact[0]['visible_marker_ids'], full[0]['visible_marker_ids'])
        self.assertEqual(compact_coverage, full_coverage)
        self.assertEqual(len(compact[0]['visible_marker_ids']), 2)
        self.assertTrue(all('(presumed repeat)' in row['full_display_label'] for row in selected))
        ass = preview.subtitles(compact, 1620, 1080, reference_bpm=178)
        self.assertIn('~178 BPM · expected arrangement', ass)
        self.assertNotIn('SOURCE ', ass)
        other = copy.deepcopy(selected[1])
        other['marker_id'] += '-different'; other['arrangement_phrase_label'] = 'Chorus 2 · phrase 3'
        different, _ = preview.compose_callouts([selected[0], other], 0, arrangement_labels=True)
        self.assertEqual(len(different[0]['labels']), 2)

    def test_compact_breakdown_badge_preserves_user_attribution(self):
        marker = {'name': 'arrangement_aligned_unit_review',
                  'display_label': 'ALIGNMENT CANDIDATE: Breakdown 1 [USER: length?]'}
        row = preview.arrangement_display(marker)
        self.assertIn('Check breakdown length (user)', row['label'])
        self.assertIn('Timing review', row['label'])
        self.assertIn('[USER: length?]', row['full_display_label'])


class RealArrangementVideoTests(unittest.TestCase):
    def test_alternate_intent_preview_preserves_vfr_and_aac_without_canonical_edits(self):
        ffmpeg = os.environ.get('FFMPEG') or shutil.which('ffmpeg')
        ffprobe = os.environ.get('FFPROBE') or shutil.which('ffprobe')
        if not ffmpeg or not ffprobe:
            self.skipTest('Explicit FFmpeg/FFprobe required for generated arrangement render proof')
        spec = importlib.util.spec_from_file_location('arrangement_tiny_fixture', REPO / 'tests/test_marked_video.py')
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            run = root / 'artifacts/runs/candidate'
            (root / 'program').mkdir(parents=True)
            with patch.object(preview, 'ROOT', root), patch.object(preview.marker_tool, 'ROOT', root), \
                    patch.object(adapter, 'ROOT', root), \
                    patch.dict(os.environ, {'FFMPEG': ffmpeg, 'FFPROBE': ffprobe}):
                fixture.create_verified_fixture(run, ffmpeg, ffprobe, origin=2., vfr=True)
                shutil.copyfile(run / 'cleaned.wav', run / 'denoised.wav')
                probe = json.loads(subprocess.run([ffprobe, '-v', 'error', '-show_streams', '-of', 'json',
                    str(run / 'denoised.wav')], check=True, capture_output=True, timeout=20).stdout)['streams'][0]
                rate = int(probe['sample_rate'])
                pcm = {'sample_rate': rate, 'sample_count': int(probe['duration_ts']), 'channels': 1}
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
                reference['anchors']['first_phrase_source_seconds'] = [2.2, 2.3]
                reference['sections'] = [{'id': 'outro_tapping', 'label': 'Toy intended tapping',
                    'kind': 'phrase', 'phrase_count': 1, 'clicks_per_phrase': 4}]
                rp = root / 'program/demo-arrangement.json'
                rp.write_text(json.dumps(reference))
                input_hash = adapter.digest(run / 'denoised.wav')
                obs = {'schema_version': 1, 'source_sha256': reference['source_sha256'],
                    'analyzed_input_sha256': input_hash,
                    'timeline': {'source_start_seconds': 2., 'duration_seconds': pcm['sample_count'] / rate,
                                 'native_pcm': pcm}, 'boundaries': []}
                assessment = assessment_tool.align_arrangement(reference, obs)
                binding = {name: {'path': str(run / (name + '.json')), 'sha256': adapter.digest(run / (name + '.json'))}
                           for name in ('manifest', 'analysis', 'phrases')}
                binding['reference'] = {'path': str(rp), 'sha256': adapter.digest(rp)}
                binding['analyzed_input_sha256'] = input_hash
                binding['input_hashes'] = {name: adapter.digest(run / name) for name in
                                          ('manifest.json', 'analysis.json', 'phrases.json', 'denoised.wav')}
                assessment['binding'] = binding
                assessment['reference'].update(binding['reference'])
                (run / 'assessment.json').write_text(json.dumps(assessment))
                marker, _ = adapter.build(run, 'assessment.json')
                (run / 'arrangement-markers.json').write_text(json.dumps(marker))
                before = {p: adapter.digest(p) for p in run.rglob('*') if p.is_file()}
                output = run / 'reference-marked-preview'
                result = preview.render(run, output, selection='all-review', arrangement_markers='arrangement-markers.json')
                outcome = json.loads(Path(result['outcome_json']).read_text())
                self.assertEqual(outcome['marker_mode'], 'arrangement_reference_review')
                for key in ('aac_packet_payloads_timing_and_padding_preserved', 'decoded_audio_pcm_sha256_preserved',
                            'decoded_video_frame_pts_preserved', 'decoded_video_variable_frame_intervals_observed'):
                    self.assertTrue(outcome['verification'][key], key)
                selection = json.loads(Path(result['selection_json']).read_text())
                self.assertTrue(any('Expected' in r['label'] for r in selection['selected_markers']))
                self.assertTrue(any('INTENT' in r['full_display_label'] for r in selection['selected_markers']))
                self.assertIn('~178 BPM · expected arrangement', Path(result['subtitles_ass']).read_text())
                self.assertTrue(all(r['flags'][0]['flag_origin'] == 'hash_bound_arrangement_assessment'
                                    for r in selection['selected_markers']))
                self.assertFalse(selection['performance_issue_confirmed'])
                self.assertTrue(outcome['input_hashes_preserved'])
                for path, identity in before.items():
                    self.assertEqual(adapter.digest(path), identity)


class ReferenceResolutionTests(unittest.TestCase):
    """A second take binds its own arrangement reference; the demo keeps its repository selector."""

    def setUp(self):
        import arrangement_markers
        self.tool = arrangement_markers
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_demo_reference_keeps_repository_selector(self):
        demo = self.tool.ROOT / self.tool.REFERENCE
        for recorded in (self.tool.REFERENCE, str(demo.absolute())):
            path, selector = self.tool.resolve_reference(recorded)
            self.assertEqual(selector, self.tool.REFERENCE)
            self.assertEqual(path.absolute(), demo.absolute())

    def test_other_take_reference_is_used_as_recorded(self):
        other = self.tmp / 'take-two-arrangement.json'
        other.write_text('{}')
        path, selector = self.tool.resolve_reference(str(other))
        self.assertEqual(path, other)
        self.assertEqual(selector, str(other))

    def test_refusals(self):
        real = self.tmp / 'real.json'
        real.write_text('{}')
        link = self.tmp / 'link.json'
        link.symlink_to(real)
        for recorded in (None, '', 'a\x00b', str(link), str(self.tmp / 'missing.json'), str(self.tmp),
                         'program/../program/demo-arrangement.json'):
            with self.subTest(recorded=recorded):
                with self.assertRaises(ValueError):
                    self.tool.resolve_reference(recorded)


if __name__ == '__main__':
    unittest.main()
