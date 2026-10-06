"""Independent intent/observation and source-clock oracles; no audio inference."""
from __future__ import annotations
import copy
import contextlib
import hashlib
import importlib.util
import json
import io
import math
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('arrangement_audit_worker', ROOT / 'scripts/arrangement_reference.py')
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
SOURCE = 'a' * 64
INPUT = 'b' * 64
MANIFEST = 'c' * 64


def reference(anchor=(10, 10), counts=(4, 4), kinds=None):
    kinds = kinds or ['phrase'] * len(counts)
    return {'schema_version': 1, 'source_sha256': SOURCE,
            'provenance': {'status': 'operator_supplied_expected_arrangement',
                           'authority_reference': 'independent_constructed_operator_reference', 'assumptions': []},
            'tempo': {'bpm': 60, 'precision': 'approximate'},
            'anchors': {'first_phrase_source_seconds': list(anchor), 'click_start_approx_seconds': 5},
            'sections': [{'id': f'unit{i}', 'label': 'same riff' if kind == 'phrase' else kind,
                          'kind': kind, 'phrase_count': 1, 'clicks_per_phrase': count}
                         for i, (count, kind) in enumerate(zip(counts, kinds))]}


def observations(times=(), start=0, duration=40, confidence='unvalidated', uncertainty=0):
    return {'schema_version': 1, 'source_sha256': SOURCE,
            'timeline': {'source_start_seconds': start, 'duration_seconds': duration},
            'boundaries': [{'id': f'observed{i}', 'source_seconds': t, 'confidence': confidence,
                            'uncertainty_seconds': uncertainty, 'evidence': 'independent feature change'}
                           for i, t in enumerate(times)]}


def adapter_fixture(duration=8, relative_end=8):
    manifest = {'source': {'sha256': SOURCE}, 'timeline': {'audio_start_seconds': 7.25, 'no_time_stretch': True},
                'pcm': {'sample_rate': 48000, 'sample_count': int(duration * 48000), 'channels': 1},
                'output_sha256': {'denoised.wav': INPUT}}
    analysis = {'source': {'sha256': INPUT},
                'source_lineage': {'original_source_sha256': SOURCE, 'timeline_rebased': True, 'manifest_sha256': MANIFEST},
                'timeline': {'audio_stream_start_seconds': 7.25},
                'analysis': {'duration_seconds': duration},
                'click_grid': {'bpm': 89, 'period_seconds': 60 / 89}}
    phrases = {'source': {'sha256': INPUT, 'audio_stream_start_seconds': 7.25},
               'analysis': {'duration_seconds': duration},
               'lineage': {'original_source_sha256': SOURCE, 'status': 'verified_canonical_derivative'},
               'observations': {'segment_candidates': [{'start_seconds': 0, 'end_seconds': relative_end,
                                                        'source_start_seconds': 7.25,
                                                        'source_end_seconds': 7.25 + relative_end}]}}
    return manifest, analysis, phrases


class ArrangementAudit(unittest.TestCase):
    def test_demo_arithmetic_and_articulation_provenance(self):
        ref = json.loads((ROOT / 'program/demo-arrangement.json').read_text())
        expanded = worker.validate_reference(ref, ref['source_sha256'])
        self.assertEqual(expanded['totals']['intended_click_count'], 404)
        self.assertEqual(expanded['totals']['musical_phrase_count'], 24)
        self.assertEqual(expanded['totals']['breakdown_group_count'], 2)
        self.assertEqual(expanded['totals']['rest_click_count'], 4)
        self.assertEqual(len(expanded['units']), 27)
        self.assertEqual(ref['sections'][0]['id'], 'verse1')
        self.assertNotIn('open', ref['sections'][0]['label'].lower())
        chorus2 = next(s for s in ref['sections'] if s['id'] == 'chorus2')
        self.assertEqual(chorus2['section_provenance'], 'presumed_repeat')
        chorus = next(s for s in ref['sections'] if s['id'] == 'chorus1')
        self.assertEqual(chorus['clicks_per_phrase'], 16)

    def test_half_open_counts_property(self):
        rng = random.Random(46021)
        for _ in range(40):
            counts = [rng.randint(1, 32) for _ in range(rng.randint(1, 8))]
            ref = reference(counts=counts)
            expanded = worker.validate_reference(ref)
            cursor = 0
            for unit, count in zip(expanded['units'], counts):
                self.assertEqual((unit['start_click_index'], unit['end_click_index']), (cursor, cursor + count))
                cursor += count
            self.assertEqual(expanded['totals']['intended_click_count'], sum(counts))
            self.assertEqual([r['click_index'] for r in expanded['boundaries']], [0] + list(__import__('itertools').accumulate(counts)))

    def test_range_anchor_not_midpoint(self):
        ref = reference(anchor=(10, 11))
        result = worker.align_arrangement(ref, observations([10.25, 14.25, 18.25]))
        self.assertEqual(result['boundaries'][1]['expected']['source_seconds_range'], [14, 15])
        self.assertEqual(result['boundaries'][1]['deviation']['seconds_range'], [-.75, .25])
        self.assertFalse(result['boundaries'][1]['deviation']['outside_expected_window'])

    def test_boundary_uncertainty_propagates_to_duration(self):
        obs = observations([10, 14, 18])
        obs['boundaries'][0]['uncertainty_seconds'] = .2
        obs['boundaries'][1]['uncertainty_seconds'] = .3
        result = worker.align_arrangement(reference(), obs)
        observed = result['units'][0]['observed']
        self.assertEqual(observed['duration_seconds'], 4)
        for actual, expected in zip(observed['duration_seconds_range'], [3.5, 4.5]):
            self.assertAlmostEqual(actual, expected, places=10)
        self.assertFalse(result['units'][0]['performance_issue_confirmed'])

    def test_correct_constructed_boundaries_no_detected_click_claim(self):
        result = worker.align_arrangement(reference(), observations([10, 14, 18]))
        self.assertEqual(result['observed_boundary_count'], 3)
        self.assertIsNone(result['observed_click_count'])
        self.assertIsNone(result['meter'])
        for unit in result['units']:
            self.assertEqual(unit['observed']['reference_equivalent_clicks'], 4)
            self.assertIsNone(unit['observed']['observed_click_count'])
            self.assertFalse(unit['performance_issue_confirmed'])
        self.assertFalse(result['performance_issue_confirmed'])

    def test_negative_duration_delta_is_hypothesis(self):
        result = worker.align_arrangement(reference(), observations([10, 13.5, 18]))
        self.assertEqual(result['units'][0]['deviation']['reference_equivalent_clicks_delta'], -.5)
        self.assertEqual(result['units'][0]['observed']['duration_seconds'], 3.5)
        self.assertFalse(result['units'][0]['performance_issue_confirmed'])
        self.assertTrue(all(x['status'] == 'needs_review' and not x['performance_issue_confirmed'] for x in result['review_candidates']))

    def test_no_boundaries_does_not_fabricate_phrase_observations(self):
        result = worker.align_arrangement(reference(), observations())
        self.assertEqual(result['observed_boundary_count'], 0)
        self.assertTrue(all(b['observed'] is None and b['deviation'] is None for b in result['boundaries']))
        self.assertTrue(all(u['observed'] is None and u['deviation'] is None for u in result['units']))
        self.assertEqual(result['observed_click_count'], None)

    def test_repeated_riff_join_without_novelty_stays_unknown(self):
        result = worker.align_arrangement(reference(), observations([10, 18]))
        join = result['boundaries'][1]
        self.assertIsNone(join['observed'])
        self.assertIsNone(join['deviation'])
        self.assertEqual(join['status'], 'unobserved_boundary')
        self.assertTrue(all(u['observed'] is None for u in result['units']))

    def test_same_observation_competing_joins_abstain(self):
        result = worker.align_arrangement(reference(anchor=(10, 11), counts=(1, 1)), observations([11]))
        self.assertTrue(all(b['observed'] is None for b in result['boundaries']))
        self.assertEqual(result['boundaries'][0]['candidate_observation_ids'], ['observed0'])
        self.assertEqual(result['boundaries'][1]['candidate_observation_ids'], ['observed0'])
        self.assertTrue(all(b['deviation'] is None for b in result['boundaries']))

    def test_ambiguous_observation_confidence_never_becomes_unique_support(self):
        result = worker.align_arrangement(reference(), observations([10, 14, 18], confidence='ambiguous'))
        self.assertTrue(all(x['observed'] is None for x in result['boundaries']))
        self.assertTrue(all(x['deviation'] is None for x in result['boundaries']))

    def test_extra_change_not_consumed_as_repeated_join(self):
        result = worker.align_arrangement(reference(), observations([10, 11.9, 14, 18]))
        used = [b['observed']['id'] for b in result['boundaries'] if b['observed']]
        self.assertEqual(len(used), len(set(used)))
        self.assertEqual(result['unassigned_observation_ids'], ['observed1'])

    def test_right_censored_tail_not_invented_observed_end(self):
        result = worker.align_arrangement(reference(), observations([10, 14], duration=15))
        self.assertEqual(result['boundaries'][-1]['coverage'], 'right_censored')
        self.assertIsNone(result['units'][-1]['observed'])
        self.assertTrue(all(x['end_seconds'] <= 15 for x in result['review_candidates']))

    def test_partial_anchor_tail_range_is_clipped_for_navigation(self):
        result = worker.align_arrangement(reference(anchor=(10, 11)), observations([10.5, 14.5], duration=18.5))
        self.assertEqual(result['boundaries'][-1]['coverage'], 'partially_censored')
        tail = result['review_candidates'][-1]
        self.assertEqual([tail['source_time_seconds'], tail['end_seconds']], [18, 18.5])
        self.assertEqual(tail['evidence']['time_basis'], 'intended_boundary_interval')
        self.assertIsNone(tail['observed'])

    def test_rest_is_context_not_missed_attack(self):
        result = worker.align_arrangement(reference(counts=(4, 4), kinds=['phrase', 'rest']), observations([10, 14, 18]))
        self.assertEqual(result['units'][1]['expected']['kind'], 'rest')
        self.assertFalse(result['units'][1]['performance_issue_confirmed'])
        self.assertEqual(result['reference']['totals']['musical_phrase_count'], 1)

    def test_source_origin_shift_property(self):
        for shift in [-17.25, -.125, 7.25, 91.125]:
            ref = reference(anchor=(10, 11))
            obs = observations([10.3, 14.2, 18.6])
            baseline = worker.align_arrangement(ref, obs)
            ref['anchors']['first_phrase_source_seconds'] = [x + shift for x in ref['anchors']['first_phrase_source_seconds']]
            ref['anchors']['click_start_approx_seconds'] += shift
            obs['timeline']['source_start_seconds'] += shift
            for row in obs['boundaries']:
                row['source_seconds'] += shift
            moved = worker.align_arrangement(ref, obs)
            self.assertEqual([b['status'] for b in moved['boundaries']], [b['status'] for b in baseline['boundaries']])
            for a, b in zip(moved['boundaries'], baseline['boundaries']):
                for left, right in zip(a['deviation']['seconds_range'], b['deviation']['seconds_range']):
                    self.assertAlmostEqual(left, right, places=10)

    def test_inputs_not_mutated_and_unsorted_observations_sort(self):
        ref = reference(); obs = observations([18, 10, 14]); before = copy.deepcopy((ref, obs))
        result = worker.align_arrangement(ref, obs)
        self.assertEqual((ref, obs), before)
        self.assertEqual([x['source_seconds'] for x in result['observations']], [10, 14, 18])

    def test_reference_source_binding_rejected(self):
        with self.assertRaises(ValueError): worker.validate_reference(reference(), 'f' * 64)
        obs = observations(); obs['source_sha256'] = 'd' * 64
        with self.assertRaises(ValueError): worker.align_arrangement(reference(), obs)

    def test_hostile_reference_values_rejected(self):
        mutations = [('tempo', 'bpm', True), ('tempo', 'bpm', math.nan), ('tempo', 'bpm', math.inf), ('tempo', 'bpm', 401)]
        for group, key, value in mutations:
            with self.subTest(value=value):
                ref = reference(); ref[group][key] = value
                with self.assertRaises(ValueError): worker.validate_reference(ref)
        for counts in [(True,), (0,), (129,)]:
            with self.assertRaises(ValueError): worker.validate_reference(reference(counts=counts))
        ref = reference(); ref['sections'][1]['id'] = ref['sections'][0]['id']
        with self.assertRaises(ValueError): worker.validate_reference(ref)
        ref = reference(); ref['sections'][0]['performance_issue_confirmed'] = True
        with self.assertRaises(ValueError): worker.validate_reference(ref)

    def test_hostile_observed_values_rejected(self):
        for value in [True, math.nan, math.inf, -1, 41]:
            obs = observations([value])
            with self.subTest(value=value), self.assertRaises(ValueError): worker.align_arrangement(reference(), obs)
        obs = observations([10, 14]); obs['boundaries'][1]['id'] = obs['boundaries'][0]['id']
        with self.assertRaises(ValueError): worker.align_arrangement(reference(), obs)
        obs = observations([10]); obs['boundaries'][0]['confidence'] = 'certain'
        with self.assertRaises(ValueError): worker.align_arrangement(reference(), obs)

    def test_boundary_and_unit_resource_limits(self):
        ref = reference(); ref['sections'][0]['phrase_count'] = 129
        with self.assertRaises(ValueError): worker.validate_reference(ref)
        with self.assertRaises(ValueError): worker.align_arrangement(reference(), observations([10] * 2049))
        with self.assertRaises(ValueError): worker.align_arrangement(reference(), observations(duration=301))

    def test_adapter_source_offset_once_and_unverified_pulse(self):
        fixture = adapter_fixture()
        result = worker.observations_from_run(*fixture, MANIFEST)
        self.assertEqual([b['source_seconds'] for b in result['boundaries']], [7.25, 15.25])
        self.assertEqual(result['pulse_candidates'][0]['bpm'], 89)
        self.assertIsNone(result['pulse_candidates'][0]['reference_click_unit_mapping'])
        self.assertEqual(result['timeline']['boundary_latency_status'], 'uncalibrated')

    def test_adapter_shared_edges_deduplicate(self):
        manifest, analysis, phrases = adapter_fixture()
        phrases['observations']['segment_candidates'] = [
            {'start_seconds': 0, 'end_seconds': 4, 'source_start_seconds': 7.25, 'source_end_seconds': 11.25},
            {'start_seconds': 4, 'end_seconds': 8, 'source_start_seconds': 11.25, 'source_end_seconds': 15.25}]
        result = worker.observations_from_run(manifest, analysis, phrases, MANIFEST)
        self.assertEqual([b['source_seconds'] for b in result['boundaries']], [7.25, 11.25, 15.25])

    def test_adapter_stale_manifest_or_wrong_axis_rejected(self):
        fixture = adapter_fixture()
        with self.assertRaises(ValueError): worker.observations_from_run(*fixture, 'e' * 64)
        manifest, analysis, phrases = adapter_fixture(); phrases['observations']['segment_candidates'][0]['source_end_seconds'] += 7.25
        with self.assertRaises(ValueError): worker.observations_from_run(manifest, analysis, phrases, MANIFEST)

    def test_reversed_cached_segment_rejected(self):
        manifest, analysis, phrases = adapter_fixture()
        phrases['observations']['segment_candidates'] = [{'start_seconds': 6, 'end_seconds': 2,
                                                         'source_start_seconds': 13.25, 'source_end_seconds': 9.25}]
        with self.assertRaises(ValueError): worker.observations_from_run(manifest, analysis, phrases, MANIFEST)

    def test_native_fractional_count_rejected(self):
        manifest, analysis, phrases = adapter_fixture()
        manifest['pcm']['sample_count'] += .5
        with self.assertRaises(ValueError): worker.observations_from_run(manifest, analysis, phrases, MANIFEST)

    def test_optional_metadata_nonfinite_or_claim_injection_rejected(self):
        obs = observations([10])
        obs['pulse_candidates'] = [{'bpm': math.inf, 'period_seconds': .5,
                                    'identity': 'unverified_periodic_candidate', 'reference_click_unit_mapping': None}]
        with self.assertRaises(ValueError): worker.align_arrangement(reference(), obs)
        obs = observations([10]); obs['boundaries'][0]['performance_issue_confirmed'] = True
        with self.assertRaises(ValueError): worker.align_arrangement(reference(), obs)

    def test_json_duplicate_nonfinite_and_depth_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            file = Path(td) / 'input.json'
            for raw in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":1e400}', '[' * 25 + '0' + ']' * 25]:
                file.write_text(raw)
                with self.subTest(raw=raw[:20]), self.assertRaises(ValueError): worker.read_json(file, 10000)

    def test_cached_resampling_tail_is_handled_without_extra_native_time(self):
        fixture = adapter_fixture(relative_end=8 + 1 / 16000)
        result = worker.observations_from_run(*fixture, MANIFEST)
        self.assertLessEqual(result['boundaries'][-1]['source_seconds'], 15.25)

    def test_candidate_pulse_aliases_do_not_change_arrangement_assignment(self):
        baseline = worker.align_arrangement(reference(), observations([10, 14, 18]))
        for bpm in [44.5, 89, 178, 356]:
            obs = observations([10, 14, 18])
            obs['pulse_candidates'] = [{'bpm': bpm, 'period_seconds': 60 / bpm,
                                        'identity': 'unverified_periodic_candidate',
                                        'reference_click_unit_mapping': None}]
            result = worker.align_arrangement(reference(), obs)
            self.assertEqual(result['units'], baseline['units'])
            self.assertEqual(result['boundaries'], baseline['boundaries'])
            self.assertEqual(result['pulse_candidates'][0]['bpm'], bpm)

    def test_missing_join_property_has_no_implicit_correctness(self):
        rng = random.Random(98410)
        for _ in range(25):
            counts = [rng.randint(4, 16) for _ in range(rng.randint(2, 6))]
            times = [10] + [10 + x for x in __import__('itertools').accumulate(counts)]
            removed = rng.randrange(1, len(times) - 1)
            result = worker.align_arrangement(reference(counts=counts), observations(times[:removed] + times[removed + 1:], duration=150))
            self.assertIsNone(result['boundaries'][removed]['observed'])
            self.assertIsNone(result['units'][removed - 1]['observed'])
            self.assertIsNone(result['units'][removed]['observed'])
            self.assertFalse(result['performance_issue_confirmed'])

    def test_fresh_cli_receipt_input_binding_and_output_collision(self):
        with tempfile.TemporaryDirectory() as td:
            parent = Path(td).resolve()
            ref_path, obs_path = parent / 'ref.json', parent / 'obs.json'
            ref_path.write_text(json.dumps(reference()))
            obs_path.write_text(json.dumps(observations([10, 14, 18])))
            before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in [ref_path, obs_path]}
            output = parent / 'result'
            argv = [str(ref_path), '--observations', str(obs_path), '--output', str(output)]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(worker.main(argv), 0)
            receipt = json.loads((output / 'receipt.json').read_text())
            self.assertFalse(receipt['dsp_performed'])
            self.assertFalse(receipt['performance_issue_confirmed'])
            for p, digest in before.items():
                self.assertEqual(receipt['input_sha256'][str(p)], digest)
                self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), digest)
            for name, digest in receipt['output_sha256'].items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)
            prior = (output / 'assessment.json').read_bytes()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertNotEqual(worker.main(argv), 0)
            self.assertEqual((output / 'assessment.json').read_bytes(), prior)


if __name__ == '__main__': unittest.main()
