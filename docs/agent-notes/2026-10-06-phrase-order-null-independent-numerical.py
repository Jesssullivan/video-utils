#!/usr/bin/env python3
"""Independent saved-JSON arithmetic only; no project evaluator or audio imports."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'artifacts/experiments/phrase-window-ablation/order-null-predictions-20261006T0152'
BANK = ROOT / 'artifacts/experiments/phrase-window-ablation/order-null-bank-20261006T0145'
PINNED = {
    BASE/'run.json': 'cc3a66cd5bd12ec10a081b25248bf06bcd487a9036248578d0c881c481ea21c1',
    BASE/'evaluation.json': 'cc3e28ce269439a9a74c3c07035668198537135624b67d8873dd67651d1a2654',
    BASE/'result-disposition-audit.json': 'cbdd8d886b7845f85491e54add31fe477f3459e61ab502a26e00af705be0acb7',
    BANK/'fixtures.json': '42ff7501ea734378c22010c4765b58e66ed766627bbaedf81babddd4e69c8fa8',
}
READ = {}
ARMS = ('Bcontrol', 'Border')
COHORTS = ('low32-sustain', 'missing-f0-sustain', 'click-noise-only')


def load(path, expected):
    path = Path(path)
    assert path.suffix == '.json' and path.is_relative_to(ROOT)
    assert '..' not in path.parts and not any(p.is_symlink() for p in (path, *path.parents))
    assert path.stat().st_size <= 2_000_000
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    assert sha == expected, str(path)
    READ[path] = sha
    assert sum(p.stat().st_size for p in READ) <= 10_000_000
    return json.loads(raw, parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))


def equal(a, b):
    if isinstance(a, dict):
        assert set(a) == set(b), (set(a), set(b))
        for k in a: equal(a[k], b[k])
    elif isinstance(a, list):
        assert len(a) == len(b), (a, b)
        for x, y in zip(a, b): equal(x, y)
    elif isinstance(a, float):
        assert isinstance(b, (float, int)) and math.isfinite(a) and math.isclose(a, b, rel_tol=0, abs_tol=1e-12), (a, b)
    else:
        assert type(a) is type(b) and a == b, (a, b)


def spans(pair):
    result = ([pair['first_span_seconds'], pair['second_span_seconds']]
              if 'first_span_seconds' in pair else
              [[pair['first_start_seconds'], pair['first_end_seconds']],
               [pair['second_start_seconds'], pair['second_end_seconds']]])
    assert all(all(math.isfinite(v) for v in s) and 0 <= s[0] < s[1] <= 8 for s in result)
    return result


def overlap(a, b):
    return max(0, min(a[1], b[1])-max(a[0], b[0]))/(max(a[1], b[1])-min(a[0], b[0]))


def metrics(reference, candidates, threshold):
    # The generated bank has at most one reference per case; exhaustive selection
    # independently replaces the project's general min-cost-flow matching.
    assert len(reference) <= 1 and len(candidates) <= 10
    options = []
    if reference:
        ref = spans(reference[0])
        for i, candidate in enumerate(candidates):
            estimate = spans(candidate)
            ious = [overlap(ref[k], estimate[k]) for k in (0, 1)]
            if min(ious)+1e-12 >= threshold:
                options.append((statistics.mean(ious), i))
    matches = []
    if options:
        score, index = max(options, key=lambda p: (p[0], -p[1]))
        matches = [{'reference_index': 0, 'estimate_index': index, 'mean_iou': score}]
    tp = len(matches); refs = len(reference); estimates = len(candidates)
    empty = refs == estimates == 0
    return {'tp': tp, 'fp': estimates-tp, 'fn': refs-tp,
            'precision': None if empty else tp/estimates if estimates else 0.,
            'recall': None if empty else tp/refs if refs else 0.,
            'f1': None if empty else 2*tp/(refs+estimates), 'iou_threshold': threshold,
            'status': 'not_applicable_empty_reference_and_estimate' if empty else
            'empty_reference_false_positives_visible' if not refs else 'evaluated',
            'matches': matches}


def selection(prediction):
    proposals = prediction['proposal_universe']; audit = prediction['audit']
    assert len(proposals) == len(audit) <= 60
    control = []; order = []
    for index, row in enumerate(audit):
        assert row['candidate_index'] == index
        evidence = row['contrast_evidence']; null = row['order_evidence']
        baseline = evidence['baseline_cosine']
        medians = evidence['anchor_competitor_medians']
        if baseline is not None:
            equal(float(baseline), sum(medians)/2)
            equal(float(evidence['contrast']), evidence['match_cosine']-baseline)
        qualified = evidence['contrast'] is not None and evidence['contrast'] >= .10-1e-12
        if null['margin'] is not None:
            assert null['first_window_rotated'] is False
            assert null['rotation_offsets'] == list(range(1, proposals[index]['pulse_count']))
            equal(float(null['null_median']), statistics.median(null['rotated_cosines']))
            equal(float(null['margin']), null['true_cosine']-null['null_median'])
        ordered = qualified and null['margin'] is not None and null['margin'] >= .10-1e-12
        if qualified: control.append(index)
        if ordered: order.append(index)
    def ranking(i):
        proposal = proposals[i]; evidence = audit[i]['contrast_evidence']
        return (-evidence['contrast'], -evidence['match_cosine'], proposal['first_start_seconds'],
                proposal['second_start_seconds'], proposal['pulse_count'], i)
    full = {'Bcontrol': sorted(control, key=ranking), 'Border': sorted(order, key=ranking)}
    for arm in ARMS:
        assert [p['original_candidate_index'] for p in prediction['arms'][arm]] == full[arm][:10]
        for candidate in prediction['arms'][arm]:
            for key, value in proposals[candidate['original_candidate_index']].items(): equal(value, candidate[key])
    for index, row in enumerate(audit):
        control_status = ('eligible' if index in full['Bcontrol'][:10] else
                          'ranked_cap_excluded' if index in control else 'contrast_excluded')
        order_status = ('eligible' if index in full['Border'][:10] else
                        'ranked_cap_excluded' if index in order else
                        'contrast_excluded' if index not in control else 'order_margin_excluded')
        assert row['control_status'] == control_status and row['order_status'] == order_status
    return {arm: dict(Counter(r['control_status' if arm == 'Bcontrol' else 'order_status'] for r in audit)) for arm in ARMS}


def main():
    run = load(BASE/'run.json', PINNED[BASE/'run.json'])
    evaluation = load(BASE/'evaluation.json', PINNED[BASE/'evaluation.json'])
    owner = load(BASE/'result-disposition-audit.json', PINNED[BASE/'result-disposition-audit.json'])
    bank = load(BANK/'fixtures.json', PINNED[BANK/'fixtures.json'])
    assert len(run['cases']) == len(evaluation['cases']) == len(bank['cases']) == len(owner['rows']) == 10
    assert run['evaluation_sha256'] == PINNED[BASE/'evaluation.json']
    assert run['bank_index_sha256'] == PINNED[BANK/'fixtures.json']
    rows = []; common = []; dispositions = {arm: Counter() for arm in ARMS}
    for case, receipt, saved, auditrow in zip(bank['cases'], run['cases'], evaluation['cases'], owner['rows']):
        assert case['id'] == receipt['id'] == saved['id'] == auditrow['id']
        prediction = load(BASE/receipt['result'], receipt['result_sha256'])
        truth = load(BANK/case['truth']['path'], case['truth']['sha256'])
        assert prediction['source_sha256'] == truth['source']['sha256'] == receipt['source_sha256']
        assert prediction['performance_issue_confirmed'] is False
        assert saved['truth_sha256'] == case['truth']['sha256'] and saved['result_sha256'] == receipt['result_sha256']
        assert saved['reference_pair_count'] == len(truth['recurrence_pairs'])
        counts = selection(prediction)
        left_indices = {p['original_candidate_index'] for p in prediction['arms']['Bcontrol']}
        right_indices = {p['original_candidate_index'] for p in prediction['arms']['Border']}
        equal(sorted(left_indices & right_indices), auditrow['postcap_shared_proposal_indices'])
        equal(sorted(left_indices-right_indices), auditrow['postcap_control_only_indices'])
        equal(sorted(right_indices-left_indices), auditrow['postcap_order_only_indices'])
        for arm in ARMS:
            dispositions[arm].update(counts[arm])
            equal(counts[arm], auditrow['control_dispositions' if arm == 'Bcontrol' else 'order_dispositions'])
        maps = {}; scores = {}
        for arm in ARMS:
            candidates = prediction['arms'][arm]
            assert all(c['performance_issue_confirmed'] is False for c in candidates)
            measured = [metrics(truth['recurrence_pairs'], candidates, t) for t in (.5, .75)]
            maps[arm] = {}; offsets = []
            for match in measured[0]['matches']:
                reference = spans(truth['recurrence_pairs'][match['reference_index']])
                estimate = spans(candidates[match['estimate_index']])
                values = [estimate[i][j]-reference[i][j] for i in (0, 1) for j in (0, 1)]
                maps[arm][match['reference_index']] = values; offsets.extend(values)
            scores[arm] = {'pair_metrics': measured, 'candidate_count': len(candidates),
                           'negative_reference': not truth['recurrence_pairs'],
                           'matched_endpoint_offsets_at_primary_iou_seconds': offsets,
                           'unmatched_reference_ids_at_primary_iou': [p['id'] for i, p in enumerate(truth['recurrence_pairs']) if i not in maps[arm]]}
            equal(scores[arm], saved['scores'][arm]); equal(scores[arm], auditrow['scores'][arm])
        left, right = maps['Bcontrol'], maps['Border']; shared = sorted(set(left)&set(right))
        current = {'id': case['id'], 'seed': case['seed'], 'common_reference_indices': shared,
                   'lost_reference_indices': sorted(set(left)-set(right)), 'gained_reference_indices': sorted(set(right)-set(left)),
                   'endpoint_count': 4*len(shared)}
        for arm, label, mapping in [('Bcontrol', 'control', left), ('Border', 'order', right)]:
            values = [v for i in shared for v in mapping[i]]
            current[label+'_signed_offsets_seconds'] = values
            current[label+'_mean_absolute_error_seconds'] = statistics.mean(abs(v) for v in values) if values else None
        equal(current, evaluation['common_reference_endpoints'][len(rows)])
        owner_common = owner['common_reference_endpoints'][len(rows)]
        equal(current, {k: owner_common[k] for k in current})
        for key, indices in [('common', shared), ('lost', current['lost_reference_indices']), ('gained', current['gained_reference_indices'])]:
            equal([truth['recurrence_pairs'][i]['id'] for i in indices], owner_common[key+'_reference_ids'])
        common.append(current); rows.append({'id': case['id'], 'seed': case['seed'], 'cohort': case['cohort'], 'scores': scores})
    aggregate = {}
    for name, subset in [('all', rows)]+[(f'seed{s}', [r for r in rows if r['seed'] == s]) for s in (419, 523)]:
        aggregate[name] = {}
        for arm in ARMS:
            aggregate[name][arm] = []
            for n, threshold in enumerate((.5, .75)):
                tp, fp, fn = [sum(r['scores'][arm]['pair_metrics'][n][k] for r in subset) for k in ('tp', 'fp', 'fn')]
                aggregate[name][arm].append({'iou_threshold': threshold, 'tp': tp, 'fp': fp, 'fn': fn,
                    'precision': tp/(tp+fp) if tp+fp else None, 'recall': tp/(tp+fn) if tp+fn else None,
                    'f1': 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
                    'negative_false_candidates_by_cohort': {c: sum(r['scores'][arm]['candidate_count'] for r in subset if r['cohort'] == c) for c in COHORTS}})
    equal(aggregate, evaluation['aggregate'])
    gates = {}
    for seed in (419, 523):
        control, order = [aggregate[f'seed{seed}'][a][0] for a in ARMS]
        gates[f'seed{seed}'] = {'negative_false_candidates_strictly_lower': sum(order['negative_false_candidates_by_cohort'].values()) < sum(control['negative_false_candidates_by_cohort'].values()),
            'primary_recall_not_lower': order['recall'] is not None and control['recall'] is not None and order['recall'] >= control['recall'],
            'qualification': 'relative_research_criterion_only_not_absolute_accuracy_or_acceptance'}
    equal(gates, evaluation['relative_research_criteria'])
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == sha for p, sha in READ.items())
    return {'status': 'independent_saved_json_arithmetic_verified', 'aggregate': aggregate,
            'per_case_counts': [{k: r[k] for k in ('id', 'seed', 'cohort')} | {a: [[m[k] for k in ('tp', 'fp', 'fn')] for m in r['scores'][a]['pair_metrics']] for a in ARMS} for r in rows],
            'dispositions': {a: dict(v) for a, v in dispositions.items()}, 'common_reference_endpoints': [r for r in common if r['endpoint_count']],
            'relative_gates': gates, 'input_json_count': len(READ), 'input_hashes_unchanged': True,
            'all_predictions_older_than_evaluation': all((BASE/r['result']).stat().st_mtime_ns < (BASE/'evaluation.json').stat().st_mtime_ns for r in run['cases']),
            'media_or_cache_bytes_read': False, 'inference_reexecuted': False,
            'default_adoption': False, 'input_hashes': {str(p.relative_to(ROOT)): sha for p, sha in READ.items()}}


if __name__ == '__main__':
    print(json.dumps(main(), indent=2, allow_nan=False))
