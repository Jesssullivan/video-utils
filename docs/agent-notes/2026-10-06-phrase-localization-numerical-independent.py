#!/usr/bin/env python3
"""Saved JSON consistency audit of the fixed 617/719 experiment; no DSP imports."""
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'artifacts/experiments/phrase-localization/fresh-run-schema-repair-617-719-20261006T0408'
BANK = ROOT/'artifacts/experiments/phrase-localization/fresh-bank-617-719-20261006T0332'
PINS = {'run.json': '3187e03a542eb6458b307edbff414a71c26fc871a405c00a3d3f919dc0ddb13a',
        'evaluation.json': '5fafd1d3db2a2f74db3c439f9b40eebce04935e364b58b01cd6c6f27842f3003',
        'predictions-frozen.json': '2e7a9792d4277c72a06405508f27eb82a74cdc259f6bb79b856b9d0fb153b575'}
BANK_SHA = '9b62a3498f8ed5c508cca68c904f4d868c3861280c2f707f1972f098d4f39e67'
ARMS = ('Araw', 'Border', 'L1')
NEGATIVES = ('low32-sustain', 'missing-f0-sustain', 'ordered-click-noise-only', 'fan-envelope-only')
READ = {}


def load(path, sha):
    assert path.suffix == '.json' and path.is_relative_to(ROOT) and '..' not in path.parts
    assert not any(p.is_symlink() for p in (path, *path.parents)) and path.stat().st_size <= 2_000_000
    raw = path.read_bytes(); actual = hashlib.sha256(raw).hexdigest()
    assert actual == sha, str(path)
    READ[path] = actual
    assert sum(p.stat().st_size for p in READ) <= 10_000_000
    return json.loads(raw, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def same(a, b):
    if isinstance(a, dict):
        assert set(a) == set(b), (set(a), set(b))
        for key in a: same(a[key], b[key])
    elif isinstance(a, list):
        assert len(a) == len(b), (a, b)
        for x, y in zip(a, b): same(x, y)
    elif isinstance(a, float):
        assert type(b) in (float, int) and math.isfinite(a) and math.isclose(a, b, rel_tol=0, abs_tol=1e-12), (a, b)
    else:
        assert type(a) is type(b) and a == b, (a, b)


def spans(pair):
    value = ([pair['first_span_seconds'], pair['second_span_seconds']] if 'first_span_seconds' in pair else
             [[pair['first_start_seconds'], pair['first_end_seconds']],
              [pair['second_start_seconds'], pair['second_end_seconds']]])
    assert all(all(math.isfinite(t) for t in s) and 0 <= s[0] < s[1] <= 8 for s in value)
    return value


def counts(ref, pred, matches, boundary=False):
    tp = len(matches); noun = 'endpoint' if boundary else 'pair'
    return {'reference_'+noun+'_count': ref, 'estimate_'+noun+'_count': pred,
            'tp': tp, 'fp': pred-tp, 'fn': ref-tp,
            'precision': tp/pred if pred else None, 'recall': tp/ref if ref else None,
            'f1': 2*tp/(ref+pred) if ref+pred else None}


def iou(a, b):
    return max(0, min(a[1], b[1])-max(a[0], b[0]))/(max(a[1], b[1])-min(a[0], b[0]))


def score(reference, estimates):
    # Zero or one reference per case: exhaustive independent matching is sufficient.
    assert len(reference) <= 1 and len(estimates) <= 60
    refs = [spans(r) for r in reference]; preds = [spans(p) for p in estimates]
    output = {'candidate_count': len(preds), 'iou': [], 'boundary': []}
    for threshold in (.5, .75):
        eligible = []
        if refs:
            for index, prediction in enumerate(preds):
                overlaps = [iou(refs[0][k], prediction[k]) for k in (0, 1)]
                if min(overlaps)+1e-12 >= threshold: eligible.append((statistics.mean(overlaps), index))
        matches = []
        if eligible:
            _, index = max(eligible, key=lambda p: (p[0], -p[1]))
            matches = [{'reference_index': 0, 'estimate_index': index, 'reference_id': reference[0]['id'],
                        'signed_endpoint_offsets_seconds': [preds[index][k][v]-refs[0][k][v] for k in (0, 1) for v in (0, 1)]}]
        output['iou'].append({**counts(len(refs), len(preds), matches), 'kind': 'iou', 'threshold': threshold, 'matches': matches})
    for threshold in (.02, .05, .1):
        matches = []
        if refs:
            for k, prefix in enumerate(('first', 'second')):
                for v, edge in enumerate(('start', 'end')):
                    eligible = [(abs(p[k][v]-refs[0][k][v]), i) for i, p in enumerate(preds) if abs(p[k][v]-refs[0][k][v]) <= threshold+1e-12]
                    if eligible:
                        _, index = min(eligible)
                        matches.append({'reference_index': 0, 'estimate_index': index, 'endpoint_key': prefix+'_'+edge,
                                        'signed_offset_seconds': preds[index][k][v]-refs[0][k][v]})
        output['boundary'].append({**counts(4*len(refs), 4*len(preds), matches, True),
                                   'kind': 'typed_boundary', 'threshold': threshold, 'matches': matches})
    return output


def main():
    run, evaluation, seal = [load(BASE/name, PINS[name]) for name in ('run.json', 'evaluation.json', 'predictions-frozen.json')]
    bank = load(BANK/'fixtures.json', BANK_SHA)
    assert run['evaluation_sha256'] == PINS['evaluation.json'] and run['prediction_seal_sha256'] == PINS['predictions-frozen.json']
    assert run['bank_sha256'] == seal['bank_sha256'] == BANK_SHA and seal['truth_opened'] is False
    assert len(run['cases']) == len(bank['cases']) == len(evaluation['cases']) == seal['case_count'] == 12
    assert seal['case_prediction_sha256'] == [r['prediction_sha256'] for r in run['cases']]
    rows = []
    for case, receipt, saved in zip(bank['cases'], run['cases'], evaluation['cases']):
        assert case['id'] == receipt['id'] == saved['id']
        assert receipt['prediction_sha256'] == seal['artifact_sha256'][receipt['prediction_path']] == saved['prediction_sha256']
        prediction = load(BASE/receipt['prediction_path'], receipt['prediction_sha256'])
        truth = load(BANK/case['truth']['path'], case['truth']['sha256'])
        assert saved['truth_sha256'] == case['truth']['sha256']
        assert prediction['source_sha256'] == truth['source']['sha256'] == saved['source_sha256'] == receipt['source_sha256']
        assert prediction['performance_issue_confirmed'] is False and prediction['discovery_reference_labels_supplied'] is False
        assert prediction['raw_fallback_credited_L1'] is False and set(prediction['arms']) == set(ARMS)
        assert len(prediction['arms']['Border']) <= 10 and len(prediction['arms']['L1']) <= 10
        reference = truth['recurrence_pairs']; scores = {a: score(reference, prediction['arms'][a]) for a in ARMS}
        same(scores, saved['scores'])
        assert saved['reference_pair_count'] == len(reference) and saved['all_references_in_denominator'] is True
        same(prediction['failure_taxonomy'], saved['discovery_failure_taxonomy'])
        assert len(prediction['arms']['L1']) == prediction['localized_count'] == saved['localization_coverage']['localized_count']
        assert len(prediction['arms']['Border'])-len(prediction['arms']['L1']) == prediction['abstained_count'] == saved['localization_coverage']['abstained_count']
        common = []
        for index, threshold in enumerate((.5, .75)):
            maps = {a: {m['reference_index']: m['signed_endpoint_offsets_seconds'] for m in scores[a]['iou'][index]['matches']} for a in ('Border', 'L1')}
            left, right = maps['Border'], maps['L1']; shared = sorted(set(left)&set(right))
            offsets = {a: [v for i in shared for v in maps[a][i]] for a in maps}
            common.append({'iou_threshold': threshold, 'reference_count': len(reference), 'common_pair_count': len(shared), 'endpoint_count': 4*len(shared),
                'common_reference_ids': [reference[i]['id'] for i in shared],
                'lost_reference_ids': [reference[i]['id'] for i in sorted(set(left)-set(right))],
                'gained_reference_ids': [reference[i]['id'] for i in sorted(set(right)-set(left))],
                'signed_offsets_seconds': offsets, 'mean_absolute_error_seconds': {a: statistics.mean(abs(v) for v in values) if values else None for a, values in offsets.items()}})
        same(common, saved['common_reference_endpoints'])
        rows.append({'id': case['id'], 'seed': case['seed'], 'cohort': case['cohort'], 'reference_count': len(reference), 'scores': scores, 'common': common})
    scopes = {'all': rows, **{f'seed{s}': [r for r in rows if r['seed'] == s] for s in (617, 719)},
              **{c: [r for r in rows if r['cohort'] == c] for c in {r['cohort'] for r in rows}}}
    aggregate = {}
    for name, subset in scopes.items():
        out = {}
        for arm in ARMS:
            out[arm] = {}
            for kind, thresholds in [('iou', (.5, .75)), ('boundary', (.02, .05, .1))]:
                values = []
                for index, threshold in enumerate(thresholds):
                    noun = 'endpoint' if kind == 'boundary' else 'pair'
                    refs = sum(r['scores'][arm][kind][index]['reference_'+noun+'_count'] for r in subset)
                    preds = sum(r['scores'][arm][kind][index]['estimate_'+noun+'_count'] for r in subset)
                    tp = sum(r['scores'][arm][kind][index]['tp'] for r in subset)
                    values.append({**counts(refs, preds, [None]*tp, kind == 'boundary'), 'threshold': threshold})
                out[arm][kind] = values
            out[arm]['negative_false_candidates_by_cohort'] = {c: sum(r['scores'][arm]['candidate_count'] for r in subset if r['cohort'] == c and not r['reference_count']) for c in NEGATIVES}
        common = []
        for index, threshold in enumerate((.5, .75)):
            selected = [r['common'][index] for r in subset]; n = sum(r['endpoint_count'] for r in selected)
            common.append({'iou_threshold': threshold, 'endpoint_count': n, 'reference_pair_count': sum(r['reference_count'] for r in subset),
                'lost_reference_ids': [v for r in selected for v in r['lost_reference_ids']], 'gained_reference_ids': [v for r in selected for v in r['gained_reference_ids']],
                'mean_absolute_error_seconds': {a: sum(abs(v) for r in selected for v in r['signed_offsets_seconds'][a])/n if n else None for a in ('Border', 'L1')}})
        out['common_reference_endpoints'] = common; aggregate[name] = out
    same(aggregate, evaluation['aggregate'])
    gates = {}
    for seed in (617, 719):
        row = aggregate[f'seed{seed}']; baseline, treatment = [row[a]['iou'][0] for a in ('Border', 'L1')]
        gates[f'seed{seed}'] = {'all_reference_recall_not_lower': treatment['recall'] >= baseline['recall'],
            'negative_false_candidates_not_higher': sum(row['L1']['negative_false_candidates_by_cohort'].values()) <= sum(row['Border']['negative_false_candidates_by_cohort'].values()),
            'qualification': 'relative_generated_experiment_only; absolute navigation and musician acceptance remain unknown'}
    same(gates, evaluation['relative_research_criteria'])
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == sha for p, sha in READ.items())
    return {'status': 'independent_saved_json_consistency_verified', 'aggregate': aggregate, 'gates': gates,
        'per_case_pair_counts': [{'id': r['id'], **{a: [r['scores'][a]['iou'][0][k] for k in ('tp', 'fp', 'fn')] for a in ARMS}} for r in rows],
        'input_json_count': len(READ), 'input_hashes_unchanged': True,
        'predictions_sealed_before_evaluation_mtime': all((BASE/r['prediction_path']).stat().st_mtime_ns < (BASE/'predictions-frozen.json').stat().st_mtime_ns < (BASE/'evaluation.json').stat().st_mtime_ns for r in run['cases']),
        'media_or_feature_cache_bytes_read': False, 'inference_executed': False, 'default_adoption': False,
        'input_hashes': {str(p.relative_to(ROOT)): sha for p, sha in READ.items()}}


if __name__ == '__main__':
    print(json.dumps(main(), indent=2, allow_nan=False))
