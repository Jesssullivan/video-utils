from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import tonal


def vectors_for(classes, duration=8, transposition=0):
    times = [i*.05 for i in range(round(duration/.05))]
    vectors = []
    for i in range(len(times)):
        row = [0.] * 12
        row[(classes[i % len(classes)]+transposition) % 12] = 1
        vectors.append(row)
    return times, vectors


def fixture(directory: Path):
    derivative = directory/'denoised.wav'
    derivative.write_bytes(b'fixture opaque derivative; tonal worker does not decode media')
    identity = tonal.sha256(derivative)
    manifest = {'source': {'sha256': 'a'*64}, 'output_sha256': {'denoised.wav': identity},
                'timeline': {'audio_start_seconds': 2.5, 'no_time_stretch': True}}
    (directory/'manifest.json').write_text(json.dumps(manifest))
    times, vectors = vectors_for([0, 4, 7])
    analysis = {'source': {'sha256': identity}, 'source_lineage': {'original_source_sha256': 'a'*64,
        'analyzed_input_sha256': identity, 'manifest_sha256': tonal.sha256(directory/'manifest.json')},
        'analysis': {'duration_seconds': 8, 'sample_rate': 16000}, 'librosa': {'features': {
            'matrix_layout': 'feature_by_frame', 'chroma_fft_samples': 4096,
            'frame_times_audio_relative_seconds': times, 'chroma': [list(row) for row in zip(*vectors)]}}}
    (directory/'analysis.json').write_text(json.dumps(analysis))
    phrases = {'source': {'sha256': identity}, 'observations': {'segment_candidates': [
        {'start_seconds': 0, 'end_seconds': 4, 'label': 'automatic-region'}], 'recurrence_candidates': [
        {'first_start_seconds': 0, 'first_end_seconds': 4, 'second_start_seconds': 4, 'second_end_seconds': 8}]}}
    (directory/'phrases.json').write_text(json.dumps(phrases))
    return analysis


class TonalMathTests(unittest.TestCase):
    def test_triad_transposition_all_roots(self):
        for shift in range(12):
            times, vectors = vectors_for([0, 4, 7], transposition=shift)
            result = tonal.context(times, vectors, 0, 8)
            self.assertIsNone(result['tonic'])
            for family in tonal.PROFILES:
                winner = result['profile_families'][family]['ranked_hypotheses'][0]
                self.assertEqual((winner['tonic_candidate'], winner['mode_candidate']), (tonal.NOTES[shift], 'major'))

    def test_modal_collection_preserves_all_seven_rotations(self):
        times, vectors = vectors_for([0, 2, 3, 5, 7, 9, 10])
        result = tonal.context(times, vectors, 0, 8)
        top = result['scale_collection_hypotheses'][0]
        self.assertAlmostEqual(top['in_collection_mass'], 1)
        self.assertIn({'tonic_candidate': 'C', 'mode_candidate': 'dorian'}, top['compatible_rotations'])
        self.assertEqual(len(top['compatible_rotations']), 7)
        self.assertIsNone(result['mode'])

    def test_power_chord_and_single_pitch_abstain(self):
        for pitches in ([0], [0, 7]):
            times, vectors = vectors_for(pitches)
            result = tonal.context(times, vectors, 0, 8)
            self.assertEqual(result['status'], 'abstained')
            self.assertIn('single_pitch_or_power_chord_ambiguity', result['abstention_reasons'])

    def test_chromatic_riff_abstains(self):
        times, vectors = vectors_for(list(range(12)))
        result = tonal.context(times, vectors, 0, 8)
        self.assertIn('near_uniform_or_chromatic_distribution', result['abstention_reasons'])

    def test_uniform_noise_and_silence_abstain(self):
        times = [i*.05 for i in range(160)]
        for row in ([1/12]*12, [0]*12):
            result = tonal.context(times, [row]*160, 0, 8)
            self.assertEqual(result['status'], 'abstained')
            self.assertTrue(all(item['top_hypothesis_screen'] == 'ambiguous_or_weak_candidate'
                                for item in result['profile_families'].values()))

    def test_short_clear_riff_abstains(self):
        times, vectors = vectors_for([0, 4, 7], duration=1)
        self.assertIn('insufficient_context', tonal.context(times, vectors, 0, 1)['abstention_reasons'])

    def test_changed_context_reports_ranking_instability(self):
        times, first = vectors_for([0, 4, 7], duration=4)
        _, second = vectors_for([0, 4, 7], duration=4, transposition=6)
        result = tonal.context([i*.05 for i in range(160)], first+second, 0, 8)
        self.assertTrue(all(item['local_top_ranking_agreement'] <= .5
                            for item in result['profile_families'].values()))

    def test_frequent_pitch_is_not_chosen_as_tonic(self):
        # G is most salient, yet these independently known C-major triad weights
        # still rank C-major with K-K; no tonic is promoted from the rank.
        vector = tonal.normalize([.7, 0, 0, 0, .7, 0, 0, 1., 0, 0, 0, 0])
        self.assertEqual(tonal.profile_rank(vector, 'krumhansl_kessler')[0]['tonic_candidate'], 'C')

    def test_feature_validation_rejects_nonfinite_negative_and_bad_times(self):
        base = {'matrix_layout': 'feature_by_frame', 'frame_times_audio_relative_seconds': [0, .1, .2, .3],
                'chroma': [[1.]*4 for _ in range(12)]}
        for value in (float('nan'), float('inf'), -1, True):
            altered = json.loads(json.dumps(base)); altered['chroma'][0][0] = value
            with self.assertRaises(ValueError):
                tonal.validate_features(altered, 1)
        base['frame_times_audio_relative_seconds'] = [0, .1, .1, .3]
        with self.assertRaises(ValueError):
            tonal.validate_features(base, 1)


class TonalProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.analysis = fixture(self.directory)

    def tearDown(self):
        self.temporary.cleanup()

    def test_source_axis_and_recurrence_affinity(self):
        result = tonal.build(self.directory)
        self.assertEqual(result['regions'][0]['source_start_seconds'], 2.5)
        self.assertEqual(result['regions'][0]['source_end_seconds'], 6.5)
        self.assertGreater(result['recurrence_context_comparisons'][0]['pitch_distribution_affinity'], .999)
        self.assertEqual(result['feature_context']['fft_bin_spacing_hz'], 3.90625)
        self.assertFalse(result['instrument_context']['used_as_tonic_prior'])

    def test_tampered_derivative_rejected(self):
        (self.directory/'denoised.wav').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'hash-verified'):
            tonal.build(self.directory)

    def test_stale_manifest_rejected(self):
        with (self.directory/'manifest.json').open('a') as handle:
            handle.write(' ')
        with self.assertRaisesRegex(ValueError, 'stale'):
            tonal.build(self.directory)

    def test_wrong_phrase_source_rejected(self):
        phrases = json.loads((self.directory/'phrases.json').read_text())
        phrases['source']['sha256'] = 'f'*64
        (self.directory/'phrases.json').write_text(json.dumps(phrases))
        with self.assertRaisesRegex(ValueError, 'Phrase source'):
            tonal.build(self.directory)

    def test_features_missing_returns_unavailable(self):
        self.analysis['librosa'] = None
        (self.directory/'analysis.json').write_text(json.dumps(self.analysis))
        self.assertEqual(tonal.build(self.directory)['status'], 'tonal_features_unavailable')

    def test_outside_phrase_span_rejected(self):
        phrases = json.loads((self.directory/'phrases.json').read_text())
        phrases['observations']['segment_candidates'][0]['end_seconds'] = 9
        (self.directory/'phrases.json').write_text(json.dumps(phrases))
        with self.assertRaisesRegex(ValueError, 'within analysis'):
            tonal.build(self.directory)

    def test_publication_is_independent_immutable_and_private(self):
        before = {p.name: p.read_bytes() for p in self.directory.iterdir()}
        result = tonal.build(self.directory)
        first, second = tonal.publish(self.directory, result), tonal.publish(self.directory, result)
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(first.stat().st_mode & 0o777, 0o600)
        self.assertEqual({name: (self.directory/name).read_bytes() for name in before}, before)

    def test_sparse_pitch_receipt_not_pooled_as_notes(self):
        (self.directory/'pitch.json').write_text(json.dumps({'source': self.analysis['source'], 'analysis': {'coverage_fraction': .1}}))
        result = tonal.build(self.directory)
        self.assertFalse(result['pitch_context']['combined_into_tonal_histogram'])
        self.assertEqual(result['pitch_context']['coverage_fraction'], .1)

    def test_region_limits_are_strict(self):
        for regions, pairs in ((True, 30), (0, 30), (257, 30), (128, 61), (128, 0)):
            with self.assertRaises(ValueError):
                tonal.build(self.directory, regions, pairs)

    def test_unbounded_duration_rejected_before_local_window_scan(self):
        self.analysis['analysis']['duration_seconds'] = 1e100
        (self.directory/'analysis.json').write_text(json.dumps(self.analysis))
        with self.assertRaisesRegex(ValueError, '<=1800'):
            tonal.build(self.directory)

    def test_registry_mutation_rejected_and_read_hash_are_same_bytes(self):
        program = self.directory/'program'
        program.mkdir()
        registry = program/'instrument.json'
        registry.write_text(json.dumps({'tuning': 'before'}))
        original_context = tonal.context
        def mutate_during_context(*args, **kwargs):
            registry.write_text(json.dumps({'tuning': 'after'}))
            return original_context(*args, **kwargs)
        with patch.object(tonal, 'ROOT', self.directory), patch.object(tonal, 'context', side_effect=mutate_during_context):
            with self.assertRaisesRegex(ValueError, 'Input changed'):
                tonal.build(self.directory)
        registry.write_text(json.dumps({'tuning': 'stable'}))
        with patch.object(tonal, 'ROOT', self.directory):
            result = tonal.build(self.directory)
        self.assertEqual(result['instrument_context']['tuning_metadata']['tuning'], 'stable')
        self.assertEqual(result['instrument_context']['tuning_metadata_sha256'], tonal.sha256(registry))


@unittest.skipUnless(importlib.util.find_spec('librosa') and importlib.util.find_spec('numpy'), 'Explicit optional analysis environment required')
class TonalHarmonicFixtureTests(unittest.TestCase):
    def test_missing_c1_fundamental_is_not_a_confirmed_triad_or_key(self):
        import librosa
        import numpy as np
        rate, fundamental = 16000, 440*2**((24-69)/12)
        times = np.arange(rate*3)/rate
        signal = sum(amplitude*np.sin(2*np.pi*fundamental*partial*times)
                     for partial, amplitude in ((2, 1.), (3, .8), (5, .6)))
        chroma = librosa.feature.chroma_stft(y=signal, sr=rate, n_fft=4096, hop_length=800, tuning=0)
        features = {'matrix_layout': 'feature_by_frame', 'chroma': chroma.tolist(),
                    'frame_times_audio_relative_seconds': (np.arange(chroma.shape[1])*800/rate).tolist()}
        frame_times, vectors = tonal.validate_features(features, 3)
        result = tonal.context(frame_times, vectors, 0, 3)
        self.assertIsNone(result['tonic'])
        self.assertIsNone(result['mode'])
        self.assertTrue(any('missing fundamental' in text for text in tonal.LIMITATIONS))
        self.assertTrue(result['profile_families'])


if __name__ == '__main__':
    unittest.main()
