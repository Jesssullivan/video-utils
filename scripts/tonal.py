#!/usr/bin/env python3
"""Bounded tonal-context hypotheses from verified restored comparative chroma."""
from __future__ import annotations

import argparse
import bisect
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import statistics
import sys

from dag import load, number, sha256

ROOT = Path(__file__).resolve().parents[1]
NOTES = ('C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B')
PROFILES = {
    'krumhansl_kessler': {
        'major': [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
        'minor': [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]},
    'temperley_2002': {
        'major': [5, 2, 3.5, 2, 4.5, 4, 2, 4.5, 2, 3.5, 1.5, 4],
        'minor': [5, 2, 3.5, 4.5, 2, 4, 2, 4.5, 3.5, 2, 1.5, 4]}}
MODES = {
    'ionian': [0, 2, 4, 5, 7, 9, 11], 'dorian': [0, 2, 3, 5, 7, 9, 10],
    'phrygian': [0, 1, 3, 5, 7, 8, 10], 'lydian': [0, 2, 4, 6, 7, 9, 11],
    'mixolydian': [0, 2, 4, 5, 7, 9, 10], 'aeolian': [0, 2, 3, 5, 7, 8, 10],
    'locrian': [0, 1, 3, 5, 6, 8, 10]}
LIMITS = {'maximum_frames': 36_001, 'maximum_regions': 256, 'maximum_recurrences': 60,
          'maximum_duration_seconds': 1800}
SETTINGS = {'minimum_context_seconds': 2., 'local_window_seconds': 4.,
            'pitch_presence_fraction': .12, 'active_class_fraction': .06,
            'maximum_entropy': .96, 'minimum_profile_margin': .08,
            'minimum_profile_correlation': .60, 'minimum_local_agreement': .60}
LIMITATIONS = [
    'Profile correlation, margins, entropy and stability are diagnostics, not calibrated probabilities.',
    'Octave-folded distortion harmonics, clicks and noise are not recovered fundamentals or played notes.',
    'A triad-shaped spectrum may be partials 2, 3 and 5 of one missing fundamental.',
    'Diatonic modes sharing the same pitch collection cannot be distinguished by inventory alone.',
    'Western major/minor profiles can poorly describe chromatic, modal, power-chord or technical riffs.',
    'Open-string tuning does not establish tonic, mode, intended notes or identified strings.',
    'Source-time contexts inherit feature window/resampling and unqualified physical synchronization uncertainty.']


def correlation(first: list[float], second: list[float]) -> float:
    a, b = statistics.mean(first), statistics.mean(second)
    x, y = [v-a for v in first], [v-b for v in second]
    denominator = math.sqrt(sum(v*v for v in x)*sum(v*v for v in y))
    return sum(v*w for v, w in zip(x, y))/denominator if denominator > 1e-12 else 0.


def normalize(vector: list[float]) -> list[float]:
    total = sum(vector)
    return [v/total for v in vector] if total > 1e-12 else [0.] * 12


def profile_rank(vector: list[float], family: str) -> list[dict]:
    candidates = []
    for mode, profile in PROFILES[family].items():
        for tonic in range(12):
            shifted = [profile[(pc-tonic) % 12] for pc in range(12)]
            candidates.append({'tonic_candidate': NOTES[tonic], 'mode_candidate': mode,
                               'profile_correlation': correlation(vector, shifted)})
    return sorted(candidates, key=lambda item: (-item['profile_correlation'], item['tonic_candidate'], item['mode_candidate']))


def collection_rank(vector: list[float]) -> list[dict]:
    # Equal inventories are grouped: no lexical tie-break becomes a modal verdict.
    collections = {}
    for mode, intervals in MODES.items():
        for tonic in range(12):
            classes = tuple(sorted((tonic+offset) % 12 for offset in intervals))
            record = collections.setdefault(classes, {'pitch_classes': [NOTES[i] for i in classes],
                'in_collection_mass': sum(vector[i] for i in classes), 'compatible_rotations': []})
            record['compatible_rotations'].append({'tonic_candidate': NOTES[tonic], 'mode_candidate': mode})
    return sorted(collections.values(), key=lambda item: (-item['in_collection_mass'], item['pitch_classes']))


def validate_features(features: dict, duration: float) -> tuple[list[float], list[list[float]]]:
    if features.get('matrix_layout') != 'feature_by_frame':
        raise ValueError('Expected feature_by_frame chroma')
    times, rows = features.get('frame_times_audio_relative_seconds'), features.get('chroma')
    if not isinstance(times, list) or not 4 <= len(times) <= LIMITS['maximum_frames']:
        raise ValueError('Need 4..36001 feature timestamps')
    times = [number(value, 'feature timestamp', 0) for value in times]
    if any(a >= b for a, b in zip(times, times[1:])) or times[-1] > duration + .001:
        raise ValueError('Feature timestamps must increase and lie within analysis duration')
    if not isinstance(rows, list) or len(rows) != 12 or any(not isinstance(row, list) or len(row) != len(times) for row in rows):
        raise ValueError('Need twelve chroma rows matching timestamps')
    rows = [[number(value, 'chroma value', 0) for value in row] for row in rows]
    return times, [normalize(list(vector)) for vector in zip(*rows)]


def context(times: list[float], vectors: list[list[float]], start: float, end: float) -> dict:
    start, end = number(start, 'context start', 0), number(end, 'context end', 0)
    if end <= start:
        raise ValueError('Context must have positive extent')
    lower, upper = bisect.bisect_left(times, start), bisect.bisect_left(times, end)
    frames = vectors[lower:upper]
    nonzero = [row for row in frames if sum(row) > 0]
    mean = normalize([statistics.mean(row[i] for row in nonzero) if nonzero else 0. for i in range(12)])
    presence = normalize([sum(row[i] >= SETTINGS['pitch_presence_fraction'] for row in nonzero) for i in range(12)])
    entropy = -sum(v*math.log(v) for v in mean if v > 0)/math.log(12)
    active = sum(value >= SETTINGS['active_class_fraction'] for value in mean)
    reasons = []
    if end-start < SETTINGS['minimum_context_seconds'] or len(nonzero) < 4:
        reasons.append('insufficient_context')
    if not nonzero:
        reasons.append('no_chroma_energy')
    if active < 3:
        reasons.append('single_pitch_or_power_chord_ambiguity')
    if entropy >= SETTINGS['maximum_entropy']:
        reasons.append('near_uniform_or_chromatic_distribution')
    families = {}
    for family in PROFILES:
        ranked = profile_rank(mean, family)
        winner = ranked[0]
        margin = winner['profile_correlation']-ranked[1]['profile_correlation']
        local_winners = []
        cursor = start
        while cursor < end:
            window_end = min(end, cursor+SETTINGS['local_window_seconds'])
            a, b = bisect.bisect_left(times, cursor), bisect.bisect_left(times, window_end)
            chunk = [row for row in vectors[a:b] if sum(row) > 0]
            if window_end-cursor >= SETTINGS['minimum_context_seconds'] and len(chunk) >= 4:
                chunk_mean = [statistics.mean(row[i] for row in chunk) for i in range(12)]
                top = profile_rank(chunk_mean, family)[0]
                local_winners.append((top['tonic_candidate'], top['mode_candidate']))
            cursor = window_end
        key = winner['tonic_candidate'], winner['mode_candidate']
        agreement = sum(value == key for value in local_winners)/len(local_winners) if local_winners else None
        supported = (not reasons and margin >= SETTINGS['minimum_profile_margin']
                     and winner['profile_correlation'] >= SETTINGS['minimum_profile_correlation']
                     and agreement is not None and agreement >= SETTINGS['minimum_local_agreement'])
        families[family] = {'ranked_hypotheses': ranked[:8], 'top_score_margin': margin,
            'local_top_ranking_agreement': agreement, 'local_context_count': len(local_winners),
            'top_hypothesis_screen': 'passes_heuristic_candidate_screen' if supported else 'ambiguous_or_weak_candidate',
            'presence_vector_ranked_hypotheses': profile_rank(presence, family)[:4]}
    return {'audio_start_seconds': start, 'audio_end_seconds': end, 'feature_frames': len(frames),
            'nonzero_feature_frames': len(nonzero), 'pitch_class_distribution': dict(zip(NOTES, mean)),
            'pitch_presence_distribution': dict(zip(NOTES, presence)), 'normalized_pitch_class_entropy': entropy,
            'active_pitch_class_count': active, 'status': 'abstained' if reasons else 'ranked_hypotheses_only',
            'abstention_reasons': reasons, 'tonic': None, 'mode': None, 'profile_families': families,
            'scale_collection_hypotheses': collection_rank(mean)[:4] if not reasons else [],
            'confidence_kind': 'uncalibrated_diagnostics_not_probability'}


def validate_hash(value, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError(f'{name} must be a SHA256 digest')
    return value


def build(directory: Path, max_regions: int = 128, max_recurrences: int = 30) -> dict:
    if isinstance(max_regions, bool) or not isinstance(max_regions, int) or not 1 <= max_regions <= 256:
        raise ValueError('max_regions must be an integer in 1..256')
    if isinstance(max_recurrences, bool) or not isinstance(max_recurrences, int) or not 1 <= max_recurrences <= 60:
        raise ValueError('max_recurrences must be an integer in 1..60')
    paths = {name: directory/f'{name}.json' for name in ('manifest', 'analysis')}
    if (directory/'phrases.json').exists():
        paths['phrases'] = directory/'phrases.json'
    if (directory/'pitch.json').exists():
        paths['pitch'] = directory/'pitch.json'
    hashes = {path.name: sha256(path) for path in paths.values()}
    payloads = {name: load(path) for name, path in paths.items()}
    manifest, analysis = payloads['manifest'], payloads['analysis']
    original = validate_hash(manifest.get('source', {}).get('sha256'), 'original source')
    identity = validate_hash(analysis.get('source', {}).get('sha256'), 'analysis input')
    derivative_names = [name for name in ('denoised.wav', 'cleaned.wav') if manifest.get('output_sha256', {}).get(name) == identity]
    if not derivative_names or any(sha256(directory/name) != identity for name in derivative_names):
        raise ValueError('Tonal analysis requires a hash-verified restored derivative')
    if manifest.get('timeline', {}).get('no_time_stretch') is not True:
        raise ValueError('Original source-time mapping requires manifest no_time_stretch')
    lineage = analysis.get('source_lineage', {})
    if (lineage.get('original_source_sha256') != original or lineage.get('analyzed_input_sha256') != identity
            or lineage.get('manifest_sha256') != hashes['manifest.json']):
        raise ValueError('Analysis source lineage or manifest hash is stale')
    source_start = number(manifest.get('timeline', {}).get('audio_start_seconds', 0), 'source start')
    duration = number(analysis.get('analysis', {}).get('duration_seconds'), 'duration', .000001)
    if duration > LIMITS['maximum_duration_seconds']:
        raise ValueError('Analysis duration must be <=1800 seconds')
    settings = {**SETTINGS, 'max_regions': max_regions, 'max_recurrences': max_recurrences, 'limits': LIMITS}
    result = {'schema_version': 1, 'tool': 'tonal', 'status': 'tonal_context_hypotheses',
        'original_source_sha256': original, 'analysis_input_sha256': identity, 'analysis_lineage': 'verified_post_denoise',
        'artifact_hashes': hashes, 'settings': settings,
        'settings_sha256': hashlib.sha256(json.dumps(settings, sort_keys=True, allow_nan=False).encode()).hexdigest(),
        'requires_expected_score': False, 'tonic': None, 'mode': None, 'performance_grade': 'not_graded',
        'regions': [], 'recurrence_context_comparisons': [], 'limitations': LIMITATIONS}
    registry = ROOT/'program/instrument.json'
    if registry.stat().st_size > 64_000:
        raise ValueError('Instrument registry must be <=64000 bytes')
    registry_bytes = registry.read_bytes()
    if len(registry_bytes) > 64_000:
        raise ValueError('Instrument registry changed size while reading')
    registry_data = json.loads(registry_bytes)
    if not isinstance(registry_data, dict):
        raise ValueError('Instrument registry must be an object')
    registry_hash = hashlib.sha256(registry_bytes).hexdigest()
    result['instrument_context'] = {'tuning_metadata': registry_data, 'tuning_metadata_sha256': registry_hash,
                                    'used_as_tonic_prior': False}
    pitch = payloads.get('pitch')
    if pitch is not None:
        if pitch.get('source', {}).get('sha256') != identity:
            raise ValueError('Optional pitch context differs from tonal feature source')
        fraction = number(pitch.get('analysis', {}).get('coverage_fraction'), 'pitch coverage', 0)
        if fraction > 1:
            raise ValueError('Pitch coverage fraction must be <=1')
        result['pitch_context'] = {'status': 'separate_sparse_ambiguous_pitch_evidence', 'coverage_fraction': fraction,
            'artifact_sha256': hashes['pitch.json'], 'combined_into_tonal_histogram': False,
            'reason': 'Low/high branches and octave alternatives are dependent unresolved hypotheses, not independent note votes.'}
    features = (analysis.get('librosa') or {}).get('features')
    if not isinstance(features, dict):
        result.update(status='tonal_features_unavailable', reason='No existing comparative chroma; no implicit analysis rerun')
    else:
        times, vectors = validate_features(features, duration)
        rate = number(analysis['analysis'].get('sample_rate'), 'analysis sample rate', 1)
        fft = number(features.get('chroma_fft_samples'), 'chroma FFT samples', 1)
        result['feature_context'] = {'analysis_sample_rate': rate, 'chroma_fft_samples': fft, 'fft_bin_spacing_hz': rate/fft,
            'frame_timestamps': 'existing_audio_relative_centers', 'source_start_seconds': source_start,
            'octave_weighting': 'upstream_librosa_chroma_stft_defaults_not_reestimated',
            'low_register_pitch_resolution': 'not_qualified_for_C1_semitone_resolution'}
        result['whole_take'] = context(times, vectors, 0, duration)
        phrases = payloads.get('phrases', {})
        if phrases and phrases.get('source', {}).get('sha256') != identity:
            raise ValueError('Phrase source differs from tonal feature source')
        observations = phrases.get('observations', {})
        regions, pairs = observations.get('segment_candidates', []), observations.get('recurrence_candidates', [])
        if not isinstance(regions, list) or len(regions) > 5000 or not isinstance(pairs, list) or len(pairs) > 5000:
            raise ValueError('Phrase regions/recurrences must be bounded lists')
        def region(a, b):
            a, b = number(a, 'region start', 0), number(b, 'region end', 0)
            if b > duration+.001 or b <= a:
                raise ValueError('Region must lie within analysis duration')
            record = context(times, vectors, a, b)
            return {**record, 'source_start_seconds': source_start+a, 'source_end_seconds': source_start+b}
        for item in regions[:max_regions]:
            result['regions'].append({**region(item['start_seconds'], item['end_seconds']), 'discovered_label': item.get('label')})
        for item in pairs[:max_recurrences]:
            first = region(item['first_start_seconds'], item['first_end_seconds'])
            second = region(item['second_start_seconds'], item['second_end_seconds'])
            a, b = list(first['pitch_class_distribution'].values()), list(second['pitch_class_distribution'].values())
            affinity = sum(math.sqrt(x*y) for x, y in zip(a, b)) if sum(a) and sum(b) else None
            result['recurrence_context_comparisons'].append({'first_context': first, 'second_context': second,
                'pitch_distribution_affinity': affinity, 'interpretation': 'distribution_similarity_not_tonal_or_note_equivalence',
                'tonal_change': None, 'performance_issue': None})
        result['resource_status'] = {'regions_available': len(regions), 'recurrences_available': len(pairs),
            'regions_truncated': len(regions)>max_regions, 'recurrences_truncated': len(pairs)>max_recurrences}
    if (sha256(registry) != registry_hash or any(sha256(path) != hashes[path.name] for path in paths.values())
            or any(sha256(directory/name) != identity for name in derivative_names)):
        raise ValueError('Input changed during tonal analysis')
    return result


def publish(directory: Path, result: dict) -> Path:
    parent = directory/'tonal'
    if parent.is_symlink():
        raise ValueError('Tonal output directory must not be a symbolic link')
    parent.mkdir(mode=0o700, exist_ok=True)
    target = parent/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(6))
    target.mkdir(mode=0o700)
    output, staging = target/'tonal.json', target/'tonal.partial'
    with staging.open('x', encoding='utf-8') as handle:
        staging.chmod(0o600)
        handle.write(json.dumps(result, indent=2, allow_nan=False)+'\n')
        handle.flush()
        os.fsync(handle.fileno())
    staging.rename(output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', type=Path)
    parser.add_argument('--max-regions', type=int, default=128)
    parser.add_argument('--max-recurrences', type=int, default=30)
    args = parser.parse_args()
    try:
        directory = args.run_dir.expanduser().resolve(strict=True)
        result = build(directory, args.max_regions, args.max_recurrences)
        output = publish(directory, result)
        print(json.dumps({'tonal_json': str(output), 'status': result['status'], 'region_count': len(result['regions']),
                          'recurrence_count': len(result['recurrence_context_comparisons']), 'tonic': None, 'mode': None}))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'tonal: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
