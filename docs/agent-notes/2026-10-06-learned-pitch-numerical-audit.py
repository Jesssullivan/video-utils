"""Independent saved-array readback; never import/call either evaluator or model."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "artifacts/benchmarks/learned-numerical-pilot-20261006T0131"
EVAL = ROOT / "artifacts/benchmarks/learned-numerical-evaluation-20261006T0133/learned-pitch-calibration.json"
observed = {}


def read(path, expected=None):
    path = Path(path)
    assert path.is_file() and not path.is_symlink(), path
    raw = path.read_bytes()
    assert len(raw) <= 100 * 1024**2
    digest = hashlib.sha256(raw).hexdigest()
    if expected:
        assert digest == expected, (path, digest, expected)
    observed[str(path.relative_to(ROOT))] = digest
    return raw


def js(path, expected=None):
    return json.loads(read(path, expected))


def model_time(i):
    return i * 256 / 22050 - (i // 172) * ((172 * 256 - 43844) / 22050 + .0018)


def references(truth):
    result = []
    for kind, field in (("fixed", "pitch_regions"), ("glide", "pitch_trajectories")):
        for region in truth[field]:
            result.append({**region, "kind": kind})
    for a, b in truth["guitar_absent_intervals_seconds"]:
        result.append({"kind": "absent", "start_seconds": a, "end_seconds": b,
                       "start_native_sample": round(a * 48000), "end_native_sample": round(b * 48000)})
    return sorted(result, key=lambda r: r["start_native_sample"])


def truth_at(region, sample):
    if region["kind"] == "absent":
        return []
    if region["kind"] == "fixed":
        return region["frequencies_hz"]
    fraction = (sample / 48000 - region["start_seconds"]) / (region["end_seconds"] - region["start_seconds"])
    return [region["start_frequency_hz"] * (region["end_frequency_hz"] / region["start_frequency_hz"]) ** fraction]


def tally(arrays, segments, seconds, native):
    contexts = Counter()
    scores = Counter()
    top = np.argmax(arrays["note"], axis=1)  # first maximum = lowest MIDI
    maximum = arrays["note"][np.arange(len(top)), top]
    pitches = 440 * np.exp2((top + 21 - 69) / 12)
    histogram = Counter()
    for i, t in enumerate(seconds):
        sample = round(float(t) * 48000)
        region = next((r for r in segments if r["start_native_sample"] <= sample < r["end_native_sample"]), None)
        hz = truth_at(region, sample) if region else []
        first = (i // 142) * 36164 - 3840
        last = first + 43844
        padded = first < 0 or last > len(seconds) / 86 * 22050
        if native and padded:
            context = "input_padding"
        elif region is None:
            context = "reference_unknown"
        elif len(hz) > 1:
            context = "polyphonic"
        elif hz and not 27.5 <= hz[0] <= 440 * 2**((108 - 69) / 12):
            context = "out_of_range"
        elif native and (first / 22050 < region["start_seconds"] - 1 / 160000
                         or last / 22050 > region["end_seconds"] + 1 / 160000):
            context = "transition_crossing"
        else:
            context = "stable_monophonic" if hz else "stable_unvoiced"
        contexts[context] += 1
        voiced = float(maximum[i]) >= .3
        scores["abstentions"] += not voiced
        if context == "stable_monophonic":
            scores["monophonic_n"] += 1
            if voiced:
                error = float(1200 * np.log2(pitches[i] / hz[0]))
                scores["voiced_reference"] += 1
                scores["raw_pitch_correct"] += abs(error) <= 50
                scores["raw_chroma_correct"] += abs((error + 600) % 1200 - 600) <= 50
                scores["octave_errors"] += round(error / 1200) != 0 and abs(error - round(error / 1200) * 1200) <= 50
                histogram[int(top[i]) + 21] += 1
        elif context == "stable_unvoiced":
            scores["absence_n"] += 1
            scores["false_voiced_absence"] += voiced
    return {"contexts": dict(contexts), "counts": dict(scores), "eligible_top_midi_histogram": dict(sorted(histogram.items())),
            "maximum_activation_mean_all_rows": float(np.mean(maximum)),
            "maximum_activation_min_max_all_rows": [float(np.min(maximum)), float(np.max(maximum))]}


def assert_tally(actual, reported):
    assert actual["contexts"] == reported["counts"]["contexts"]
    c = actual["counts"]
    m = reported["stable_monophonic_metrics"]
    for key, metric, denominator in (("raw_pitch_correct", "raw_pitch_accuracy", "monophonic_n"),
                                   ("raw_chroma_correct", "raw_chroma_accuracy", "monophonic_n"),
                                   ("octave_errors", "octave_error_fraction", "monophonic_n"),
                                   ("false_voiced_absence", "voicing_false_alarm", "absence_n")):
        assert (c.get(key, 0), c.get(denominator, 0)) == (m[metric]["numerator"], m[metric]["denominator"]), (key, c, m)
        assert m[metric]["value"] == (c.get(key, 0) / c[denominator] if c.get(denominator, 0) else None)


def maximum_cardinality_onsets(truth, events, duration):
    refs = [(event["onset_source_seconds"], hz) for event in truth["generated_score"]["events"]
            if event["onset_source_seconds"] < duration for hz in event["frequencies_hz"]]
    edges = [[j for j, event in enumerate(events)
              if abs(start - event["model_start_seconds"]) <= .05
              and abs(1200 * np.log2((440 * 2**((event["midi_candidate"] - 69) / 12)) / hz)) <= 50]
             for start, hz in refs]
    assigned = {}
    def augment(i, seen):
        for j in edges[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in assigned or augment(assigned[j], seen):
                assigned[j] = i
                return True
        return False
    tp = sum(augment(i, set()) for i in range(len(refs)))
    return {"tp": tp, "fp": len(events) - tp, "fn": len(refs) - tp, "reference_n": len(refs)}


index = js(PILOT / "learned-pilot-index.json", "e565bb13847bb7f29c64a571f17d200f12dc21853154a39400516e52657bcf5f")
evaluation = js(EVAL, "655819f1dbe5150b0de6f6e8f05cdbd11d95c6dab9f062b65c77dcd45d8790c7")
assert evaluation["evaluator_sha256"] == "1fb883026b842857f72a70c8bf2fb757330b9ac705be36914f7a4c50cb8f7374"
assert evaluation["ground_truth_scope"] == "generator_only_not_musician"
assert not evaluation["real_performance_grading"] and not evaluation["listening_accepted"]
assert evaluation["unsupported_claim_count"] == 0
frozen = js(PILOT / "predictions-frozen.json", index["predictions_frozen_sha256"])
assert frozen["truth_content_read"] is False
prereg = js(ROOT / "docs/agent-notes/2026-10-06-learned-pitch-bank-preregistration.json", frozen["preregistration_sha256"])
js(ROOT / prereg["bank_index"], index["bank_index_sha256"])
js(ROOT / prereg["pyin_pilot_index"], evaluation["pyin_pilot_index_sha256"])
read(ROOT / "program/instrument.json", index["instrument_registry_sha256"])
read(ROOT / "scripts/basic_pitch_compare.py", index["adapter_sha256"])
read(ROOT / "artifacts/model-runtime-env/onnx-1.30.0-cp314/wheel-manifest-before-install.json", index["runtime_manifest_sha256"])
cases = []
raw_bytes = 0
total_windows = 0
event_totals = Counter()
for job, sealed, planned, reported in zip(index["jobs"], frozen["jobs"], prereg["jobs"], evaluation["cases"], strict=True):
    assert job["case_id"] == planned["evaluation_case_id"] == reported["case_id"]
    for key in ("comparison_path", "comparison_sha256", "activations_path", "activations_sha256"):
        assert job[key] == sealed[key]
    read(job["input_path"], job["input_sha256"])
    read(ROOT / planned["source_component_path"], job["input_sha256"])
    truth = js(job["truth_path"], job["truth_sha256"])
    assert truth["ground_truth_scope"] == "generator_only_not_musician"
    receipt = js(job["comparison_path"], job["comparison_sha256"])
    for key, expected in (("analysis_input_sha256", job["input_sha256"]), ("raw_activations_sha256", job["activations_sha256"]),
                          ("worker_sha256", index["adapter_sha256"]), ("model_sha256", index["model_sha256"]),
                          ("wheel_manifest_sha256", index["runtime_manifest_sha256"]), ("tuning_registry_sha256", index["instrument_registry_sha256"])):
        assert receipt[key] == expected
    archive_bytes = read(job["activations_path"], job["activations_sha256"])
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        assert len(archive.infolist()) == 8
        assert sum(m.file_size for m in archive.infolist()) < 20 * 1024**2
    with np.load(io.BytesIO(archive_bytes), allow_pickle=False) as archive:
        arrays = {key.removeprefix("excerpt_0_"): archive[key] for key in archive.files}
    n = planned["expected_frames"]
    assert set(arrays) == {"note", "onset", "contour", "model_times_seconds", "nominal_times_seconds",
                           "input_window_projection_seconds", "window_index", "window_frame_index"}
    for name, width in (("note", 88), ("onset", 88), ("contour", 264)):
        assert arrays[name].shape == (n, width) and np.isfinite(arrays[name]).all()
        assert ((arrays[name] >= 0) & (arrays[name] <= 1)).all()
    rows = np.arange(n)
    expected_model = rows * 256 / 22050 - (rows // 172) * ((172 * 256 - 43844) / 22050 + .0018)
    clocks = {"model_times_seconds": expected_model, "nominal_times_seconds": rows * 256 / 22050,
              "input_window_projection_seconds": ((rows // 142) * 36164 - 3840 + (rows % 142 + 15) * 256) / 22050}
    residuals = {name: float(np.max(np.abs(arrays[name] - expected))) for name, expected in clocks.items()}
    assert max(residuals.values()) < 1e-10
    assert np.array_equal(arrays["window_index"], rows // 142)
    assert np.array_equal(arrays["window_frame_index"], rows % 142 + 15)
    excerpt = receipt["excerpts"][0]
    assert excerpt["sample_count"] == round(planned["requested_budget_seconds"] * 22050)
    for w, window in enumerate(excerpt["model_input_windows"]):
        first = w * 36164 - 3840
        assert window["leading_zero_samples"] == max(0, -first)
        assert window["trailing_zero_samples"] == max(0, first + 43844 - excerpt["sample_count"])
        assert window["input_context_start_seconds_in_excerpt"] == max(0, first) / 22050
        assert window["input_context_end_seconds_in_excerpt"] == min(excerpt["sample_count"], first + 43844) / 22050
    segments = references(truth)
    native = tally(arrays, segments, arrays["model_times_seconds"], True)
    point = tally(arrays, segments, arrays["model_times_seconds"], False)
    assert_tally(native, reported["native_model_input_context"])
    assert_tally(point, reported["model_clock_pointwise"])
    alternatives = {}
    for clock in ("nominal_times_seconds", "input_window_projection_seconds"):
        alternatives[clock] = tally(arrays, segments, arrays[clock], False)
        assert_tally(alternatives[clock], reported["clock_sensitivity_pointwise"][clock])
    events_readback = []
    for variant, metrics in zip(excerpt["variants"], reported["event_presets"], strict=True):
        floor = variant["minimum_note_length_ms"]
        predicted = []
        for pitch in range(88):
            beginning = None
            for i in range(n + 1):
                active = i < n and float(arrays["note"][i, pitch]) >= .3
                split = active and beginning is not None and i > beginning and 0 < i < n - 1 and float(arrays["onset"][i, pitch]) >= .5 and arrays["onset"][i, pitch] > arrays["onset"][i - 1, pitch] and arrays["onset"][i, pitch] > arrays["onset"][i + 1, pitch]
                if beginning is not None and (not active or split):
                    if model_time(i) - model_time(beginning) >= floor / 1000:
                        predicted.append((beginning, i, pitch + 21))
                    beginning = i if split else None
                if active and beginning is None:
                    beginning = i
        events = variant["events"]
        assert sorted(predicted) == sorted((e["start_frame"], e["end_frame_exclusive"], e["midi_candidate"]) for e in events)
        for event in events:
            a, b, pitch = event["start_frame"], event["end_frame_exclusive"], event["midi_candidate"] - 21
            assert abs(event["mean_note_activation"] - float(np.mean(arrays["note"][a:b, pitch], dtype=np.float64))) <= 1e-7
            assert abs(event["maximum_onset_activation"] - float(np.max(arrays["onset"][a:b, pitch]))) <= 1e-7
            assert abs(event["model_start_seconds"] - model_time(a)) < 1e-10
            assert abs(event["model_end_seconds"] - model_time(b)) < 1e-10
        counts = maximum_cardinality_onsets(truth, events, planned["requested_budget_seconds"])
        assert all(counts[k] == metrics["onset_only"][k] for k in ("tp", "fp", "fn"))
        events_readback.append({"floor_ms": floor, "event_count": len(events), **counts})
        event_totals[str(floor)] += len(events)
    raw_bytes += sum(array.nbytes for array in arrays.values())
    total_windows += len(excerpt["model_input_windows"])
    cases.append({"case_id": job["case_id"], "native": native, "pointwise": point, "clock_sensitivity": alternatives,
                  "clock_max_abs_residual_seconds": residuals, "events": events_readback,
                  "c1_bin_activation_mean_all_rows": float(np.mean(arrays["note"][:, 24 - 21], dtype=np.float64))})
for path, digest in observed.items():
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
assert raw_bytes == 4623360 and total_windows == 19
assert "onnxruntime" not in sys.modules
print(json.dumps({"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                  "status": "independent_saved_array_checks_passed", "numpy_version": np.__version__,
                  "audit_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "evaluated_source_sha256": evaluation["evaluator_sha256"], "input_hashes_unchanged": observed,
                  "raw_numeric_bytes": raw_bytes, "model_windows": total_windows, "event_counts": dict(event_totals),
                  "cases": cases, "inference_invoked": False, "evaluator_invoked": False, "pcm_decoded": False,
                  "model_or_runtime_changed": False, "onnxruntime_imported": False,
                  "ground_truth_scope": "generator_only_not_musician", "real_note_correctness": None}, indent=2, allow_nan=False))
