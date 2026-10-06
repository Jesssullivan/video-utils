#!/usr/bin/env python3
"""Bind arrangement intent/alignment to separate source-time review markers."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
MAX_JSON = 4_000_000
MAX_MARKERS = 512
REFERENCE = 'program/demo-arrangement.json'
SHORT_SECTIONS = {
    'verse1': 'Verse 1', 'verse1_open': 'Verse 1 open', 'verse1_palm_muted': 'Verse 1 palm-muted',
    'breakdown1': 'Breakdown 1', 'chorus1': 'Chorus 1',
    'verse2_open': 'Verse 2 open', 'verse2_palm_muted': 'Verse 2 palm-muted',
    'breakdown2': 'Breakdown 2', 'chorus2': 'Chorus 2 (presumed repeat)',
    'chorus_rest': 'Post-chorus rest', 'outro_tapping': 'Outro tapping',
    'outro_two_hand_tapping': 'Outro two-hand tapping', 'outro_sweep': 'Outro sweeps',
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            value.update(block)
    return value.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def number(value, name):
    require(type(value) in (int, float) and math.isfinite(value), 'Invalid ' + name)
    return float(value)


def fingerprint(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'Invalid SHA-256')
    return value


def selector(run_dir, value, *, fresh=False):
    require(isinstance(value, str) and 1 <= len(value) <= 1024, 'Run-relative selector bound')
    require('\\' not in value and ':' not in value and '\0' not in value and not Path(value).is_absolute()
            and all(p not in ('', '.', '..') and not p.startswith('.') for p in value.split('/')),
            'Expected safe run-relative selector')
    path = Path(run_dir)
    require(path.is_dir() and not any(p.is_symlink() for p in (path, *path.parents)), 'Run directory missing or symlink')
    for part in value.split('/'):
        path /= part
        require(not path.is_symlink(), 'Symlink selector prohibited')
    require(not path.exists() if fresh else path.is_file(), 'Output must be fresh' if fresh else 'Selector file missing')
    return path


def read_json(path, limit=MAX_JSON):
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), 'JSON symlink/type prohibited')
    require(path.stat().st_size <= limit, 'JSON byte bound')
    raw = path.read_bytes()
    require(len(raw) <= limit, 'JSON grew beyond byte bound')
    depth, quoted, escaped = 0, False, False
    for character in raw.decode('utf-8'):
        if escaped:
            escaped = False
        elif quoted and character == '\\':
            escaped = True
        elif character == '"':
            quoted = not quoted
        elif not quoted and character in '[{':
            depth += 1
            require(depth <= 24, 'JSON nesting bound')
        elif not quoted and character in ']}':
            depth -= 1
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    def reject(value):
        raise ValueError('Nonfinite JSON')
    payload = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)
    canonical(payload)  # Also rejects numeric overflow to infinity.
    require(isinstance(payload, dict), 'Expected JSON object')
    return payload, hashlib.sha256(raw).hexdigest()


def label(unit):
    section = unit['section_id']
    name = SHORT_SECTIONS.get(section, str(unit['label']))
    if section == 'breakdown1':
        name += ' [USER: length?]'
    suffix = (' phrase ' + str(unit['section_unit_index'])) if unit['kind'] == 'phrase' else ''
    return (name + suffix)[:120]


def build(run_dir, assessment_selector):
    """Revalidate all identities; intent-only regions never select a clock phase."""
    run_dir = Path(run_dir).absolute()
    manifest_path = selector(run_dir, 'manifest.json')
    assessment_path = selector(run_dir, assessment_selector)
    manifest, manifest_hash = read_json(manifest_path)
    assessment, assessment_hash = read_json(assessment_path)
    reference_path = ROOT / REFERENCE
    reference, reference_hash = read_json(reference_path, 64_000)
    import arrangement_reference as reference_tool
    source_hash = fingerprint(manifest['source']['sha256'])
    expanded = reference_tool.validate_reference(reference, source_hash)
    expected_units = expanded['units']
    reference_identity = assessment.get('reference', {})
    require(reference_identity.get('path') in (REFERENCE, str(reference_path.absolute()))
            and reference_identity.get('sha256') == reference_hash, 'Arrangement reference identity mismatch')
    require(assessment.get('schema_version') == 1 and assessment.get('tool') == 'arrangement_reference'
            and assessment.get('source_sha256') == source_hash, 'Assessment source/schema mismatch')
    denoised_path = selector(run_dir, 'denoised.wav')
    input_hash = fingerprint(manifest['output_sha256']['denoised.wav'])
    require(digest(denoised_path) == input_hash == assessment.get('analyzed_input_sha256'),
            'Assessment must match current pure-denoised input')
    binding = assessment.get('binding', {})
    require(binding.get('analyzed_input_sha256') == input_hash, 'Analyzed input binding mismatch')
    input_hashes = binding.get('input_hashes')
    require(isinstance(input_hashes, dict) and set(input_hashes) ==
            {'manifest.json', 'analysis.json', 'phrases.json', 'denoised.wav'}, 'Exact cached input hash bindings required')
    tracked = {manifest_path: manifest_hash, assessment_path: assessment_hash,
               reference_path: reference_hash, denoised_path: input_hash, Path(__file__): digest(__file__)}
    validator_path = Path(reference_tool.__file__)
    tracked[validator_path] = digest(validator_path)
    for name in ('manifest', 'analysis', 'phrases'):
        row = binding.get(name, {})
        path = selector(run_dir, name + '.json')
        require(Path(row.get('path', '')).absolute() == path.absolute() and digest(path) == row.get('sha256'),
                'Assessment cached binding mismatch: ' + name)
        tracked[path] = row['sha256']
    for name, expected in input_hashes.items():
        path = selector(run_dir, name)
        require(digest(path) == fingerprint(expected), 'Cached input hash mismatch: ' + name)
        tracked[path] = expected
    bound_reference = binding.get('reference', {})
    require(isinstance(bound_reference, dict) and set(bound_reference) == {'path', 'sha256'}
            and bound_reference.get('path') in (REFERENCE, str(reference_path.absolute()))
            and bound_reference.get('sha256') == reference_hash,
            'Assessment reference binding mismatch')
    origin = number(manifest['timeline']['audio_start_seconds'], 'source origin')
    require(manifest['timeline'].get('no_time_stretch') is True, 'Unchanged source time scale required')
    pcm = manifest['pcm']
    duration = number(pcm['sample_count'], 'sample count') / number(pcm['sample_rate'], 'sample rate')
    require(0 < duration <= 600 and pcm['sample_rate'] > 0, 'Source duration bound')
    end = origin + duration
    timeline = assessment['timeline']
    require(isinstance(timeline.get('native_pcm'), dict) and all(timeline['native_pcm'].get(key) == pcm.get(key)
            for key in ('sample_rate', 'sample_count', 'channels')), 'Assessment native PCM binding mismatch')
    require(abs(number(timeline['source_start_seconds'], 'assessment origin') - origin) < 1e-9
            and abs(number(timeline['duration_seconds'], 'assessment duration') - duration) < 1e-6,
            'Assessment native source extent mismatch')
    require(assessment.get('performance_issue_confirmed') is False and assessment.get('observed_click_count') is None,
            'Arrangement assessment cannot confirm performance or count')
    units = assessment.get('units')
    boundaries = assessment.get('boundaries')
    require(isinstance(units, list) and len(units) == len(expected_units)
            and isinstance(boundaries, list) and len(boundaries) == len(units) + 1, 'Arrangement unit/boundary extent mismatch')
    for row, expected in zip(boundaries, expanded['boundaries']):
        require(isinstance(row, dict) and row.get('performance_issue_confirmed') is False
                and isinstance(row.get('expected'), dict)
                and all(row['expected'].get(k) == v for k, v in expected.items()), 'Boundary intent differs from reference')
        observed = row.get('observed')
        if observed is not None:
            require(row.get('status') == 'matched_boundary_candidate'
                    and row.get('unmatched_alignment_possible') is False
                    and row.get('candidate_observation_count') == 1,
                    'Ambiguous boundary cannot become a selected observation')
            require(isinstance(observed, dict) and origin <= number(observed['source_seconds'], 'observed boundary') <= end,
                    'Observed boundary outside source extent')
    markers, represented_candidates = [], []
    def add(kind, low, high, display, basis, evidence, confidence='reference_conditioned_uncalibrated'):
        low, high = number(low, 'marker start'), number(high, 'marker end')
        require(origin <= low <= high <= end, 'Arrangement marker outside source extent')
        markers.append({'name': kind, 'source_time_seconds': low, 'end_seconds': high,
                        'display_label': display[:200], 'label_basis': basis, 'status': 'needs_review',
                        'confidence': confidence, 'evidence': evidence, 'performance_issue_confirmed': False})
    for index, (row, expected) in enumerate(zip(units, expected_units)):
        require(row.get('performance_issue_confirmed') is False and isinstance(row.get('expected'), dict),
                'Unit must be an unconfirmed expected arrangement')
        require(all(row['expected'].get(k) == v for k, v in expected.items()), 'Intended unit differs from reference')
        left, right = expanded['boundaries'][index:index + 2]
        low, high = max(origin, left['source_seconds_range'][1]), min(end, right['source_seconds_range'][0])
        if high > low:
            add('arrangement_intended_unit', low, high, 'INTENT/time estimate: ' + label(expected),
                'operator_intent_clock_window_core_not_observed_section',
                {'unit_id': expected['id'], 'expected': row['expected'],
                 'start_window': left['source_seconds_range'], 'end_window': right['source_seconds_range'],
                 'span_policy': 'core_common_to_all_supplied_anchor_phases; approximate_tempo_conditional'})
        observed = row.get('observed')
        if observed is not None:
            require(isinstance(observed, dict) and observed.get('observed_click_count') is None,
                    'Detected click count cannot be asserted')
            lo, hi = number(observed['start_seconds'], 'observed start'), number(observed['end_seconds'], 'observed end')
            require(origin <= lo < hi <= end, 'Observed unit bounds')
            left_observed, right_observed = boundaries[index].get('observed'), boundaries[index + 1].get('observed')
            require(left_observed is not None and right_observed is not None
                    and lo == left_observed['source_seconds'] and hi == right_observed['source_seconds'],
                    'Unit span must match its two selected boundary candidates')
            add('arrangement_aligned_unit_review', lo, hi, 'ALIGNMENT CANDIDATE: ' + label(expected),
                'operator_section_label_on_estimated_audio_boundaries',
                {'unit_id': expected['id'], 'expected': row['expected'], 'observed': observed,
                 'deviation': row.get('deviation'), 'warning': 'Assigned boundaries do not establish correct notes or played technique.'})
    candidates = assessment.get('review_candidates')
    require(isinstance(candidates, list) and len(candidates) <= MAX_MARKERS, 'Review candidate bound')
    for index, row in enumerate(candidates):
        require(isinstance(row, dict) and row.get('status') == 'needs_review'
                and row.get('performance_issue_confirmed') is False, 'Only unconfirmed arrangement review candidates allowed')
        expected = row.get('expected', {})
        if row.get('kind') == 'arrangement_unit_review_candidate':
            unit_index = next((i for i, unit in enumerate(expected_units) if unit['id'] == expected.get('id')), None)
            require(unit_index is not None and all(expected.get(k) == v for k, v in expected_units[unit_index].items())
                    and expected.get('source_start_seconds_range') == expanded['boundaries'][unit_index]['source_seconds_range']
                    and expected.get('source_end_seconds_range') == expanded['boundaries'][unit_index + 1]['source_seconds_range']
                    and row.get('observed') == units[unit_index].get('observed'), 'Unit review differs from bound arrangement')
            require(origin <= number(row['source_time_seconds'], 'unit review start') <=
                    number(row['end_seconds'], 'unit review end') <= end, 'Unit review outside source extent')
            represented_candidates.append({'assessment_candidate_index': index,
                'reason': 'represented_by_unit_intent_and_separate_alignment_markers', 'candidate': row})
            continue
        require(row.get('kind') == 'arrangement_boundary_review_candidate', 'Unsupported arrangement candidate kind')
        require(isinstance(expected, dict) and isinstance(expected.get('boundary_id'), str), 'Boundary expected identity missing')
        boundary_index = next((i for i, b in enumerate(expanded['boundaries']) if b['id'] == expected['boundary_id']), None)
        require(boundary_index is not None, 'Unknown expected boundary')
        unit = expected_units[min(boundary_index, len(expected_units) - 1)]
        require(expected.get('section_id') == unit['section_id'] and expected.get('label') == unit['label'],
                'Boundary intended label mismatch')
        require(all(expected.get(k) == v for k, v in expanded['boundaries'][boundary_index].items()),
                'Boundary timing window differs from intent')
        observed = row.get('observed')
        require(observed == boundaries[boundary_index].get('observed'), 'Boundary candidate observation mismatch')
        window = expanded['boundaries'][boundary_index]['source_seconds_range']
        low = observed['source_seconds'] if observed is not None else max(origin, window[0])
        high = low if observed is not None else min(end, window[1])
        require(row['source_time_seconds'] == low and row['end_seconds'] == high,
                'Boundary presentation must retain observed point or full intended interval')
        prefix = 'REVIEW boundary estimate: ' if observed is not None else 'EXPECTED boundary window: '
        basis = 'estimated_audio_boundary_assignment' if observed is not None else 'operator_intent_boundary_window'
        add('arrangement_boundary_review', row['source_time_seconds'], row['end_seconds'],
            prefix + label(unit), basis, {'assessment_candidate_index': index, 'candidate': row}, row.get('confidence', 'unknown'))
    require(0 < len(markers) <= MAX_MARKERS, 'No supported arrangement markers or marker bound exceeded')
    markers.sort(key=lambda row: (row['source_time_seconds'], row['name']))
    payload = {'schema_version': 1, 'format': 'arrangement_reference_review_markers_seconds',
               'source_sha256': source_hash, 'analyzed_input_sha256': input_hash, 'manifest_sha256': manifest_hash,
               'assessment': {'selector': assessment_selector, 'sha256': assessment_hash},
               'reference': {'selector': REFERENCE, 'sha256': reference_hash},
               'producer_sha256': digest(__file__), 'reference_validator_sha256': tracked[validator_path],
               'tempo': {'bpm': expanded['tempo']['bpm'], 'precision': expanded['tempo']['precision'],
                         'basis': 'operator_supplied_reference_not_measured_tempo'},
               'timeline': {'source_start_seconds': origin, 'duration_seconds': duration},
               'markers': markers, 'represented_review_candidates': represented_candidates,
               'performance_issue_confirmed': False, 'listening_accepted': False,
               'limitations': ['Intent labels do not identify performed sections or techniques.',
                   'Clock-window cores are conditional on supplied approximate tempo and anchor, not detected boundaries.',
                   'Estimated alignment and suspected breakdown issues remain unconfirmed; no isolated notes or detected click counts.',
                   'Presentation overlaps can suppress labels; source-bound metadata retains every marker.']}
    canonical(payload)
    require(len(canonical(payload).encode()) <= MAX_JSON, 'Arrangement marker byte bound')
    for path, expected in tracked.items():
        require(digest(path) == expected, 'Arrangement input changed during conversion')
    return payload, tracked


def load_validated(run_dir, marker_selector):
    """Reconstruct expected markers; reject stale or edited overlay claims."""
    path = selector(run_dir, marker_selector)
    saved, saved_hash = read_json(path)
    require(saved.get('format') == 'arrangement_reference_review_markers_seconds', 'Wrong alternate marker format')
    expected, tracked = build(run_dir, saved['assessment']['selector'])
    require(saved == expected, 'Arrangement markers stale or edited; rebuild them')
    tracked[path] = saved_hash
    return saved, tracked


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', type=Path)
    parser.add_argument('--assessment', required=True, help='Exact same-run-relative assessment JSON')
    parser.add_argument('--output', required=True, help='Fresh same-run-relative marker JSON')
    args = parser.parse_args(argv)
    try:
        directory = args.run_dir.absolute()
        payload, tracked = build(directory, args.assessment)
        output = selector(directory, args.output, fresh=True)
        require(output.parent.is_dir(), 'Output parent must already exist')
        with output.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(payload, indent=2, allow_nan=False) + '\n')
        for path, expected in tracked.items():
            require(digest(path) == expected, 'Input changed during publication')
        print(json.dumps({'status': 'arrangement_markers_bound_unreviewed', 'markers': str(output),
                          'sha256': digest(output), 'marker_count': len(payload['markers']),
                          'performance_issue_confirmed': False, 'media_rendered': False}))
        return 0
    except (ValueError, KeyError, OSError, TypeError, RecursionError) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
