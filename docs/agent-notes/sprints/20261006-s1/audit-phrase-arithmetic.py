#!/usr/bin/env python3
"""Independently score sealed phrase predictions without executing discovery."""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import math
import os
import sys
import wave

os.environ["OPENBLAS_NUM_THREADS"] = "2"
import numpy as np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def spans(pair):
    if "first_span_seconds" in pair:
        return [pair["first_span_seconds"], pair["second_span_seconds"]]
    return [[pair[prefix + "_start_seconds"], pair[prefix + "_end_seconds"]]
            for prefix in ("first", "second")]


def iou(left, right):
    union = max(left[1], right[1]) - min(left[0], right[0])
    intersection = max(0, min(left[1], right[1]) - max(left[0], right[0]))
    return intersection / union


def matching(references, estimates, score):
    # Independent exhaustive dynamic programming, rather than owner's min-cost flow.
    @lru_cache(None)
    def visit(index, used):
        if index == len(references):
            return (), 0.0
        best, best_score = visit(index + 1, used)
        for candidate, estimate in enumerate(estimates):
            if used & (1 << candidate):
                continue
            value = score(references[index], estimate)
            if value is None:
                continue
            rest, rest_score = visit(index + 1, used | (1 << candidate))
            proposed, proposed_score = ((index, candidate, value),) + rest, value + rest_score
            if (len(proposed), proposed_score) > (len(best), best_score):
                best, best_score = proposed, proposed_score
        return best, best_score
    return visit(0, 0)[0]


def qc_wave(path, receipt):
    assert sha(path) == receipt["sha256"]
    with wave.open(str(path), "rb") as stream:
        assert (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getnframes()) == (1, 2, 48000, 384000)
        raw = stream.readframes(384000)
    assert hashlib.sha256(raw).hexdigest() == receipt["pcm_sha256"]
    return np.frombuffer(raw, dtype="<i2").astype(np.int32)


def main():
    root = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2])
    bank_path = root / "bank-1301-1423/bank.json"
    seal_path = root / "run-1301-1423/predictions-sealed.json"
    result_path = root / "evaluation-1301-1423.json"
    bank, seal, result = [json.loads(p.read_text()) for p in (bank_path, seal_path, result_path)]
    sources = [p for p in root.rglob("*") if p.is_file()]
    initial = {str(p.relative_to(root)): sha(p) for p in sources}
    assert result["bank_sha256"] == sha(bank_path) == seal["bank_sha256"]
    assert result["seal_sha256"] == sha(seal_path)
    assert len(bank["cases"]) == len(seal["predictions"]) == len(result["cases"]) == 12
    arms = ("Araw", "S1_support", "S2_multiscale")
    aggregate = {arm: {"pairs": [], "endpoints": [], "negative_false_candidates": {}}
                 for arm in arms}
    qc = []
    nuisance = {}
    for case, binding, scored in zip(bank["cases"], seal["predictions"], result["cases"]):
        prediction_path = seal_path.parent / binding["path"]
        assert sha(prediction_path) == binding["sha256"]
        prediction = json.loads(prediction_path.read_text())
        truth_path = bank_path.parent / case["truth"]["path"]
        assert sha(truth_path) == case["truth"]["sha256"]
        truth = json.loads(truth_path.read_text())
        assert prediction["source_sha256"] == binding["source_sha256"] == case["source"]["sha256"] == truth["source_sha256"]
        assert prediction["discovery_truth_input"] is False
        assert prediction["performance_issue_confirmed"] is False
        assert truth["ground_truth_scope"] == "generator_only_not_musician"
        components = {role: qc_wave(bank_path.parent / receipt["path"], receipt)
                      for role, receipt in case["assets"].items()}
        error = np.max(np.abs(sum(components[role] for role in ("clean", "fan", "noise", "click")) - components["mix"]))
        assert error <= 2 and error == truth["rendered_component_sum_maximum_lsb"]
        for role in ("fan", "noise", "click"):
            key = case["seed"], role
            if role == "click" and case["cohort"] == "fan-only":
                assert not np.any(components[role])
            elif key in nuisance:
                assert np.array_equal(components[role], nuisance[key])
            else:
                nuisance[key] = components[role]
        references = truth["recurrence_pairs"]
        assert len(references) == (1 if case["cohort"] in ("palm-recurrence", "legato-recurrence") else 0)
        for pair in references:
            first, second = spans(pair)
            a, b, c, d = [round(time * 48000) for time in (*first, *second)]
            assert np.array_equal(components["clean"][a:b], components["clean"][c:d])
        qc.append({"case": case["id"], "cohort": case["cohort"], "seed": case["seed"],
                   "sum_maximum_lsb": int(error), "reference_pairs": len(references),
                   "native_samples": len(components["mix"])})
        for arm in arms:
            estimates = prediction["arms"][arm]
            observed = scored["scores"][arm]
            assert observed["candidate_count"] == len(estimates)
            for threshold, metric in zip((.5, .75), observed["pair_iou"]):
                def score(left, right):
                    values = [iou(a, b) for a, b in zip(spans(left), spans(right))]
                    return sum(values) / 2 if min(values) + 1e-12 >= threshold else None
                matches = matching(references, estimates, score)
                offsets = [spans(estimates[j])[axis][endpoint] - spans(references[i])[axis][endpoint]
                           for i, j, _ in matches for axis in (0, 1) for endpoint in (0, 1)]
                expected = {"tp": len(matches), "fp": len(estimates) - len(matches),
                            "fn": len(references) - len(matches), "reference_count": len(references),
                            "estimate_count": len(estimates), "endpoint_count": len(offsets)}
                for key, value in expected.items():
                    assert metric[key] == value, (case["id"], arm, key, metric[key], value)
                mae = sum(abs(v) for v in offsets) / len(offsets) if offsets else None
                assert mae is None and metric["matched_endpoint_mae_seconds"] is None or mae is not None and math.isclose(mae, metric["matched_endpoint_mae_seconds"], abs_tol=1e-12)
                aggregate[arm]["pairs"].append({"threshold": threshold, **expected, "offsets": offsets})
            for tolerance, metric in zip((.02, .05, .1), observed["typed_endpoints"]):
                count = 0
                for axis in (0, 1):
                    for endpoint in (0, 1):
                        left = [spans(p)[axis][endpoint] for p in references]
                        right = [spans(p)[axis][endpoint] for p in estimates]
                        matched = matching(left, right, lambda a, b: 1 - abs(a-b) / tolerance if abs(a-b) <= tolerance + 1e-12 else None)
                        count += len(matched)
                expected = {"tp": count, "fp": 4 * len(estimates) - count, "fn": 4 * len(references) - count,
                            "reference_count": 4 * len(references), "estimate_count": 4 * len(estimates)}
                for key, value in expected.items():
                    assert metric[key] == value
                aggregate[arm]["endpoints"].append({"threshold": tolerance, **expected})
            if not references:
                cohort = case["cohort"]
                negative = aggregate[arm]["negative_false_candidates"]
                negative[cohort] = negative.get(cohort, 0) + len(estimates)
    recomputed = {}
    for arm in arms:
        pairs, endpoints = [], []
        for threshold, observed in zip((.5, .75), result["aggregate"][arm]["pair_iou"]):
            selected = [row for row in aggregate[arm]["pairs"] if row["threshold"] == threshold]
            totals = {key: sum(row[key] for row in selected)
                      for key in ("tp", "fp", "fn", "reference_count", "estimate_count", "endpoint_count")}
            offsets = [value for row in selected for value in row["offsets"]]
            totals.update(threshold=threshold, recall=totals["tp"] / totals["reference_count"] if totals["reference_count"] else None,
                          matched_endpoint_mae_seconds=sum(abs(value) for value in offsets) / len(offsets) if offsets else None)
            assert totals == observed
            pairs.append(totals)
        for tolerance, observed in zip((.02, .05, .1), result["aggregate"][arm]["typed_endpoints"]):
            selected = [row for row in aggregate[arm]["endpoints"] if row["threshold"] == tolerance]
            totals = {key: sum(row[key] for row in selected) for key in ("tp", "fp", "fn", "reference_count", "estimate_count")}
            totals["threshold"] = tolerance
            assert totals == observed
            endpoints.append(totals)
        negative = aggregate[arm]["negative_false_candidates"]
        assert negative == result["aggregate"][arm]["negative_false_candidates"]
        recomputed[arm] = {"pair_iou": pairs, "typed_endpoints": endpoints, "negative_false_candidates": negative}
    assert initial == {str(p.relative_to(root)): sha(p) for p in sources}
    receipt = {"status": "PASS", "auditor_sha256": sha(__file__), "bank_sha256": sha(bank_path),
               "seal_sha256": sha(seal_path), "results_sha256": sha(result_path), "all_checked_inputs_unchanged": True,
               "source_files_checked": len(initial), "cases": 12, "positive_cases": 4, "negative_cases": 8,
               "reference_pairs": 4, "reference_endpoints": 16, "native_component_qc": qc,
               "recomputed": recomputed, "discovery_or_inference_rerun": False, "actual_recording_read": False,
               "default_adoption": False, "scope": "New-seed same-recipe generated accounting; no real phrasing or musical correctness proof."}
    output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({key: value for key, value in receipt.items() if key != "native_component_qc"}, indent=2))


if __name__ == "__main__":
    main()
