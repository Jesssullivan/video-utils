#!/usr/bin/env python3
"""Hash-bound generated-reference pitch metrics; no discovery or real-note grading."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import statistics
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = ROOT / "artifacts/benchmarks"
MAX_JSON = 5_000_000
MAX_PITCH_JSON = 64_000_000
MAX_AUDIO = 3_000_000
MAX_FRAMES = 4000
RATE = 16000
HOP = 256
EPS = 1 / (RATE*10)
BRANCHES = {"low_register": (4096, 28, 500), "high_register": (1024, 200, 2000)}
PILOT = {"c1-missing-fundamental": ("clean", 8), "tuning-ladder": ("clean", 8),
         "legato-transition": ("mix", 6), "sweep-and-polyphony": ("mix", 8)}
SHA = re.compile(r"[0-9a-f]{64}\Z")


class EvaluationError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise EvaluationError(code)


def number(value, minimum=None, maximum=None):
    require(type(value) in (float, int), "number_required")
    try:
        value = float(value)
    except OverflowError as exc:
        raise EvaluationError("nonfinite_number") from exc
    require(math.isfinite(value), "nonfinite_number")
    require(minimum is None or value >= minimum, "number_below_bound")
    require(maximum is None or value <= maximum, "number_above_bound")
    return value


def fingerprint(value):
    require(isinstance(value, str) and SHA.fullmatch(value), "invalid_sha256")
    return value


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "duplicate_json_key")
        value[key] = item
    return value


def reject_constant(value):
    raise EvaluationError("nonfinite_json_constant")


def finite_float(value):
    result = float(value)
    require(math.isfinite(result), "nonfinite_json_number")
    return result


def bounded_int(value):
    require(len(value.lstrip("-")) <= 20, "integer_bound")
    return int(value)


def check_json_depth(raw):
    depth, quoted, escaped = 0, False, False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91,123):
            depth += 1
            require(depth <= 128, "json_depth_bound")
        elif byte in (93,125):
            depth -= 1
            require(depth >= 0, "invalid_json_depth")


def safe_path(value, base=None):
    require(isinstance(value, (str, Path)), "path_required")
    path = Path(value).expanduser()
    require(".." not in path.parts, "path_traversal")
    if not path.is_absolute():
        path = (base or ROOT) / path
    try:
        path.relative_to(ALLOWED)
    except ValueError as exc:
        raise EvaluationError("path_outside_benchmark_root") from exc
    current = ALLOWED
    require(not current.is_symlink(), "symlink_benchmark_root")
    for part in path.relative_to(ALLOWED).parts:
        current = current / part
        require(not current.is_symlink(), "symlink_path")
    return path


def read_bytes(path, limit, expected_hash=None):
    path = safe_path(path)
    flags = os.O_RDONLY | os.O_NOFOLLOW
    directory = os.open(ALLOWED, flags | os.O_DIRECTORY)
    descriptors = [directory]
    try:
        parts = path.relative_to(ALLOWED).parts
        require(bool(parts), "regular_file_required")
        for part in parts[:-1]:
            directory = os.open(part, flags | os.O_DIRECTORY, dir_fd=directory)
            descriptors.append(directory)
        descriptor = os.open(parts[-1], flags, dir_fd=directory)
        descriptors.append(descriptor)
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= limit, "file_bound_or_type")
        with os.fdopen(os.dup(descriptor), "rb") as handle:
            data = handle.read(limit+1)
        after = os.fstat(descriptor)
        require(len(data) <= limit and before.st_size == after.st_size
                and before.st_mtime_ns == after.st_mtime_ns and len(data) == after.st_size,
                "file_changed_or_oversized")
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    actual = hashlib.sha256(data).hexdigest()
    if expected_hash is not None:
        require(actual == fingerprint(expected_hash), "sha256_mismatch")
    return data, actual


def read_json(path, limit=MAX_JSON, expected_hash=None):
    data, digest = read_bytes(path, limit, expected_hash)
    check_json_depth(data)
    try:
        value = json.loads(data, object_pairs_hook=unique_object, parse_constant=reject_constant,
                           parse_float=finite_float, parse_int=bounded_int)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationError("invalid_json") from exc
    require(isinstance(value, dict), "json_object_required")
    return value, digest


def rate(count, denominator, reason="no_applicable_frames"):
    return {"value": count/denominator if denominator else None, "numerator": count,
            "denominator": denominator, "reason": None if denominator else reason}


def error_summary(values):
    return {"n": len(values), "median_signed": statistics.median(values) if values else None,
            "median_absolute": statistics.median(abs(x) for x in values) if values else None,
            "absolute_p95": sorted(abs(x) for x in values)[math.ceil(.95*len(values))-1] if len(values) >= 20 else None,
            "p95_reason": None if len(values) >= 20 else "insufficient_samples"}


def cents(estimated, reference):
    return 1200*math.log2(estimated/reference)


def reference_segments(truth):
    source = truth["source"]
    native_rate, duration = source["sample_rate"], source["sample_count"]/source["sample_rate"]
    segments = []
    for kind, rows in (("region", truth.get("pitch_regions", [])), ("trajectory", truth.get("pitch_trajectories", []))):
        require(isinstance(rows, list) and len(rows) <= 512, "reference_region_bound")
        for index, row in enumerate(rows):
            require(isinstance(row, dict), "reference_region_required")
            start = number(row["start_seconds"], 0, duration)
            end = number(row["end_seconds"], 0, duration)
            require(start < end, "invalid_reference_extent")
            require(type(row["start_native_sample"]) is int and type(row["end_native_sample"]) is int,
                    "native_sample_required")
            require(row["start_native_sample"] == round(start*native_rate)
                    and row["end_native_sample"] == round(end*native_rate), "reference_sample_time_mismatch")
            require(type(row.get("monophonic")) is bool, "reference_monophonic_flag")
            if kind == "region":
                frequencies = row["frequencies_hz"]
                require(isinstance(frequencies, list) and 1 <= len(frequencies) <= 9, "pitch_set_required")
                frequencies = [number(hz, 1, native_rate/2) for hz in frequencies]
                require(row["monophonic"] == (len(frequencies) == 1), "pitch_set_monophonic_mismatch")
            else:
                require(row["monophonic"] and row["formula"] == "log_frequency_linear_time", "trajectory_formula")
                frequencies = [number(row["start_frequency_hz"], 1, native_rate/2),
                               number(row["end_frequency_hz"], 1, native_rate/2)]
            segments.append({**row, "start_seconds": start, "end_seconds": end, "frequencies": frequencies,
                             "kind": kind, "id": row.get("id", f"{kind}-{index}"),
                             "condition": row.get("condition", "unspecified"),
                             "articulation": row.get("articulation", "unspecified")})
    absent = truth.get("guitar_absent_intervals_seconds", [])
    require(isinstance(absent, list) and len(absent) <= 512, "absence_interval_bound")
    for index, span in enumerate(absent):
        require(isinstance(span, list) and len(span) == 2, "absence_interval_required")
        start, end = number(span[0], 0, duration), number(span[1], 0, duration)
        require(start < end, "absence_interval_extent")
        segments.append({"start_seconds": start, "end_seconds": end,
                         "start_native_sample": round(start*native_rate), "end_native_sample": round(end*native_rate),
                         "frequencies": [], "kind": "absent", "monophonic": False,
                         "condition": "guitar_absent", "articulation": "silence_or_nuisance_component", "id": f"absent-{index}"})
    segments.sort(key=lambda x: x["start_seconds"])
    require(all(a["end_native_sample"] <= b["start_native_sample"] for a,b in zip(segments, segments[1:])),
            "overlapping_reference_regions")
    return segments


def frequencies_at(segment, sample, native_rate):
    if segment["kind"] != "trajectory":
        return segment["frequencies"]
    fraction = (sample/native_rate-segment["start_seconds"])/(segment["end_seconds"]-segment["start_seconds"])
    a,b = segment["frequencies"]
    return [a*(b/a)**fraction]


def classify_frame(frame, branch, segments, native_rate):
    center = frame["audio_relative_seconds"]
    sample = round(center*native_rate)
    segment = next((s for s in segments if s["start_native_sample"] <= sample < s["end_native_sample"]), None)
    frequencies = frequencies_at(segment, sample, native_rate) if segment else []
    if not frame["edge_context_complete"]:
        context = "excerpt_edge"
    elif segment is None:
        context = "reference_unknown"
    elif segment["kind"] != "absent" and not segment["monophonic"]:
        context = "polyphonic"
    elif frequencies and not branch["minimum_hz"] <= frequencies[0] <= branch["maximum_hz"]:
        context = "out_of_range"
    elif (frame["window_start_seconds_audio_relative"] < segment["start_seconds"]-EPS
          or frame["window_end_seconds_audio_relative"] > segment["end_seconds"]+EPS):
        context = "transition_crossing"
    elif segment["kind"] == "absent":
        context = "stable_unvoiced"
    else:
        context = "stable_monophonic"
    estimated_voiced = frame["voiced"] is True and frame["frequency_hz"] is not None
    error = cents(frame["frequency_hz"], frequencies[0]) if context == "stable_monophonic" and estimated_voiced else None
    octave = (round(error/1200) != 0 and abs(error-1200*round(error/1200)) <= 50) if error is not None else False
    return {"native_reference_sample": sample, "reference_frequency_hz": frequencies[0] if len(frequencies) == 1 else None,
            "reference_frequencies_hz": frequencies, "context": context,
            "condition": segment["condition"] if segment else "unknown", "estimated_voiced": estimated_voiced,
            "signed_cents": error, "octave_error": bool(octave),
            "non_octave_pitch_error": error is not None and abs(error) > 50 and not octave}


def summarize_frames(rows):
    contexts = Counter(r["context"] for r in rows)
    mono = [r for r in rows if r["context"] == "stable_monophonic"]
    absent = [r for r in rows if r["context"] == "stable_unvoiced"]
    voiced = [r for r in mono if r["estimated_voiced"]]
    tp,fp = len(voiced), sum(r["estimated_voiced"] for r in absent)
    errors = [r["signed_cents"] for r in voiced]
    correct = sum(abs(error) <= 50 for error in errors)
    chroma_correct = sum(abs((error+600)%1200-600) <= 50 for error in errors)
    hist = Counter(str(round(error/100)) for error in errors if abs(error)>50 and not
                   (round(error/1200) != 0 and abs(error-1200*round(error/1200)) <= 50))
    probabilities = defaultdict(lambda: [0]*5)
    for row in rows:
        score = row.get("voicing_probability")
        if score is not None:
            probabilities[row["context"]][min(4, int(score*5))] += 1
    return {"counts": {"covered_frames": len(rows), "stable_true_voiced": len(mono), "stable_true_unvoiced": len(absent),
                       "estimated_voiced_true_voiced": tp, "estimated_voiced_true_unvoiced": fp,
                       "abstained_frames": sum(not r["estimated_voiced"] for r in rows), "contexts": dict(contexts)},
            "stable_monophonic_metrics": {"raw_pitch_accuracy": rate(correct,len(mono)),
                "raw_chroma_accuracy": rate(chroma_correct,len(mono)), "voicing_recall": rate(tp,len(mono)),
                "voicing_false_alarm": rate(fp,len(absent)), "voicing_precision": rate(tp,tp+fp),
                "octave_error_fraction": rate(sum(r["octave_error"] for r in voiced),len(mono)),
                "non_octave_pitch_error_fraction": rate(sum(r["non_octave_pitch_error"] for r in voiced),len(mono)),
                "cents_error": error_summary(errors), "signed_semitone_error_histogram": dict(hist)},
            "context_diagnostics": {"abstention": rate(sum(not r["estimated_voiced"] for r in rows),len(rows)),
                "per_context_abstention": {key: rate(sum(not r["estimated_voiced"] for r in rows if r["context"]==key), count)
                                            for key,count in contexts.items()},
                "algorithm_voicing_probability_histogram": dict(probabilities),
                "probability_bins": [[0,.2],[.2,.4],[.4,.6],[.6,.8],[.8,1]],
                "probability_meaning": "voicing_algorithm_output_not_note_correctness_confidence"}}


def transition_rows(frames, branch, segments, native_rate):
    rows = []
    for segment_index, segment in enumerate(segments):
        if segment["kind"] != "region" or not segment["monophonic"]:
            continue
        target = segment["frequencies"][0]
        previous = segments[segment_index-1] if segment_index else None
        boundary = segment["start_seconds"]
        entry = {"transition_id": segment["id"], "reference_seconds": boundary,
                 "branch": branch["name"], "target_frequency_hz": target,
                 "first_supported_target_seconds": None, "signed_timing_bias_seconds": None}
        if not branch["minimum_hz"] <= target <= branch["maximum_hz"]:
            entry["status"] = "out_of_range_target"
        elif previous and previous["kind"] != "absent" and previous["monophonic"] and abs(cents(target, frequencies_at(previous, previous["end_native_sample"]-1, native_rate)[0])) <= 50:
            entry["status"] = "not_applicable_no_distinct_pitch_change"
        else:
            stable = [f for f in frames if f["edge_context_complete"]
                      and f["window_start_seconds_audio_relative"] >= boundary-EPS
                      and f["window_end_seconds_audio_relative"] <= segment["end_seconds"]+EPS]
            pairs_exist = any(abs(b["audio_relative_seconds"]-a["audio_relative_seconds"]-HOP/RATE) <= EPS
                              for a,b in zip(stable,stable[1:]))
            if not pairs_exist:
                entry["status"] = "censored_window_resolution"
            else:
                half = branch["frame_samples"]/(2*RATE)
                scan = [f for f in frames if f["edge_context_complete"]
                        and boundary-half-EPS <= f["audio_relative_seconds"] < min(segment["end_seconds"],boundary+.5)+EPS]
                match = None
                for first,second in zip(scan,scan[1:]):
                    if abs(second["audio_relative_seconds"]-first["audio_relative_seconds"]-HOP/RATE) > EPS:
                        continue
                    if all(f["voiced"] and f["frequency_hz"] is not None and abs(cents(f["frequency_hz"],target)) <= 50 for f in (first,second)):
                        match = first["audio_relative_seconds"]
                        break
                entry["status"] = "measured" if match is not None else "target_not_detected"
                if match is not None:
                    entry["first_supported_target_seconds"] = match
                    entry["signed_timing_bias_seconds"] = match-boundary
        rows.append(entry)
    return rows


def verify_wave(path, expected_hash, source):
    raw, digest = read_bytes(path, MAX_AUDIO, expected_hash)
    try:
        with wave.open(io.BytesIO(raw), "rb") as handle:
            require(handle.getnchannels() == source["channels"] == 1
                    and handle.getframerate() == source["sample_rate"] == 48000
                    and handle.getnframes() == source["sample_count"] and handle.getsampwidth() == 2
                    and handle.getcomptype() == "NONE", "source_pcm_header_mismatch")
            require(len(handle.readframes(handle.getnframes())) == source["sample_count"]*2,
                    "source_pcm_extent_mismatch")
    except (wave.Error, EOFError) as exc:
        raise EvaluationError("invalid_generated_pcm") from exc
    return digest, len(raw)


def validate_truth(truth, case):
    require(truth.get("schema_version") == 2 and truth.get("kind") == "synthetic_generated_signal_and_score_truth"
            and truth.get("ground_truth_scope") == "generator_only_not_musician", "unsupported_truth_scope_or_schema")
    require(truth.get("id") == case["id"], "truth_case_identity_mismatch")
    source = truth["source"]
    require(source.get("sample_rate") == 48000 and source.get("channels") == 1
            and type(source.get("sample_count")) is int and 0 < source["sample_count"] <= 576000,
            "truth_source_format")
    duration = source["sample_count"]/48000
    require(abs(number(case["duration_seconds"], 0,120)-duration) <= 1/48000
            and abs(number(source["duration_seconds"])-duration) <= 1/48000, "truth_source_duration")
    require(source.get("origin_evidence") == "synthetic_generator_sample_zero"
            and number(source.get("audio_start_seconds")) == 0, "generator_origin_required")
    artifacts = truth.get("artifacts")
    require(isinstance(artifacts, dict) and set(artifacts) == {"clean","mix","click","noise"}, "truth_components_required")
    for component in artifacts.values():
        fingerprint(component["sha256"])
        require(type(component.get("bytes")) is int and 0 < component["bytes"] <= MAX_AUDIO, "component_byte_bound")
    require(source["sha256"] == artifacts["mix"]["sha256"], "mixture_source_hash_mismatch")
    reference_segments(truth)
    return source


def unsupported_claims(value):
    found = []
    pending = [("",value)]
    flags = {"performance_issue_confirmed","note_correctness_confirmed","musical_error_confirmed",
             "intended_notes_confirmed","real_performance_grading","listening_accepted"}
    while pending:
        path,node = pending.pop()
        if isinstance(node,dict):
            for key,item in node.items():
                here = f"{path}/{key}"
                if ((key in flags and item is not False and item is not None)
                    or (key == "performance_grade" and item not in (None,"not_graded"))
                    or (key in {"intended_notes","identified_string","identified_fret"} and item is not None)):
                    found.append({"path":here,"kind":"unsupported_confirmed_real_note_or_acceptance_claim"})
                if isinstance(item,(dict,list)):
                    pending.append((here,item))
        elif isinstance(node,list):
            pending.extend((f"{path}/{i}",item) for i,item in enumerate(node) if isinstance(item,(dict,list)))
    return found


def validate_pitch(pitch, job, source, registry_hash, alias_path):
    require(pitch.get("schema_version") == 1 and pitch.get("tool") == "pitch"
            and pitch.get("status") == "experimental_candidate_analysis", "unsupported_pitch_schema")
    require(pitch["source"]["sha256"] == job["input_sha256"], "pitch_input_hash_mismatch")
    require(safe_path(pitch["source"]["path"]) == alias_path, "pitch_input_alias_mismatch")
    require(pitch["instrument_context"]["tuning_metadata_sha256"] == registry_hash, "pitch_registry_mismatch")
    require(pitch["provenance"]["worker_sha256"] == job["worker_sha256"], "pitch_worker_revision_mismatch")
    require(pitch["provenance"]["python_version"] == job["versions"]["python"], "pitch_python_version_mismatch")
    settings = pitch["analysis"]
    fixed = {"sample_rate": RATE, "channels":1, "hop_samples":HOP,
             "pyin_resolution_semitones": .2, "pyin_threshold_count":50, "backend":"librosa_pyin",
             "sampling":"explicit_contiguous_excerpt"}
    require(all(settings.get(k) == v for k,v in fixed.items()), "pitch_settings_mismatch")
    require(abs(number(settings["duration_seconds"])-source["sample_count"]/48000) <= 2/RATE,
            "pitch_decoded_duration_mismatch")
    require(abs(number(settings["max_analysis_seconds"])-job["requested_budget_seconds"]) <= EPS,
            "pitch_analysis_budget_mismatch")
    require(number(settings.get("numerical_threads_maximum"),1,2) <= 2, "numerical_thread_bound")
    require(number(settings.get("pyin_timeout_seconds"),1,180) <= 180, "pitch_timeout_bound")
    require(abs(number(pitch["source"]["audio_stream_start_seconds"])-source["audio_start_seconds"]) <= EPS,
            "source_origin_mismatch")
    excerpts = pitch["observations"]["analyzed_excerpts"]
    require(isinstance(excerpts,list) and len(excerpts) == 1, "pilot_exact_excerpt_required")
    excerpt = excerpts[0]
    start,end = number(excerpt["start_seconds"],0),number(excerpt["end_seconds"],0)
    require(abs(start-job["requested_start_seconds"]) <= EPS
            and abs(end-start-job["requested_budget_seconds"]) <= EPS, "pilot_coverage_mismatch")
    spans = [{"start_seconds":start,"end_seconds":end}]
    require(job["observed_coverage_spans"] == spans and settings["coverage_spans_audio_relative"] == spans,
            "recorded_coverage_mismatch")
    require(abs(number(settings["coverage_seconds"])-(end-start)) <= EPS, "coverage_seconds_mismatch")
    require(excerpt["versions"] == {key:job["versions"][key] for key in ("librosa","numpy")}, "pitch_library_version_mismatch")
    branches = excerpt["branches"]
    require(isinstance(branches,list) and len(branches) == 2
            and {b.get("name") for b in branches} == set(BRANCHES), "pitch_branches_required")
    expected_frames = math.ceil((end-start)*RATE/HOP-EPS)
    total = 0
    for branch in branches:
        frame_size,low,high = BRANCHES[branch["name"]]
        require(branch.get("frame_samples") == frame_size and branch.get("minimum_hz") == low
                and branch.get("maximum_hz") == high, "branch_settings_mismatch")
        frames = branch["frames"]
        require(isinstance(frames,list) and len(frames) == expected_frames, "incomplete_frame_grid")
        total += len(frames)
        require(total <= MAX_FRAMES, "frame_count_bound")
        for index,frame in enumerate(frames):
            center = number(frame["audio_relative_seconds"],start,end)
            require(abs(center-(start+index*HOP/RATE)) <= EPS and center < end, "frame_grid_mismatch")
            require(abs(number(frame["source_timeline_seconds"])-(center+source["audio_start_seconds"])) <= EPS,
                    "frame_source_time_mismatch")
            half = frame_size/(2*RATE)
            expected_start,expected_end = max(start,center-half),min(end,center+half)
            require(abs(number(frame["window_start_seconds_audio_relative"])-expected_start) <= EPS
                    and abs(number(frame["window_end_seconds_audio_relative"])-expected_end) <= EPS,
                    "frame_window_extent_mismatch")
            for boundary,value in (("start",expected_start),("end",expected_end)):
                require(abs(number(frame[f"window_{boundary}_seconds_source_timeline"])-(value+source["audio_start_seconds"])) <= EPS,
                        "frame_window_source_time_mismatch")
            complete = center-half >= start-EPS and center+half <= end+EPS
            require(type(frame.get("edge_context_complete")) is bool and frame["edge_context_complete"] == complete,
                    "untrusted_edge_context_flag")
            require(type(frame.get("voiced")) is bool, "voicing_flag_required")
            if frame["frequency_hz"] is not None:
                number(frame["frequency_hz"],1,RATE/2)
                require(frame["voiced"], "unvoiced_nonnull_pitch")
            if frame.get("voicing_probability") is not None:
                number(frame["voicing_probability"],0,1)
    return excerpt, branches


def evaluate_job(job, case, fixture_root, pilot_root, registry_hash):
    truth_path = safe_path(job["truth_path"], pilot_root)
    truth,truth_hash = read_json(truth_path, expected_hash=job["truth_sha256"])
    require(truth_hash == case["truth_sha256"], "case_truth_hash_mismatch")
    original_truth_path = safe_path(case["truth"], fixture_root)
    if original_truth_path != truth_path:
        read_json(original_truth_path, expected_hash=truth_hash)
    source = validate_truth(truth,case)
    component = truth["artifacts"][job["component"]]
    require(job["input_sha256"] == component["sha256"], "switched_input_component")
    input_path = safe_path(job["input_path"],pilot_root)
    original_component_path = safe_path(component["path"],fixture_root)
    mixture_path = safe_path(job["mixture_parent_path"],pilot_root)
    require(job["mixture_parent_sha256"] == truth["artifacts"]["mix"]["sha256"], "mixture_parent_hash_mismatch")
    _, input_bytes = verify_wave(input_path,job["input_sha256"],source)
    if original_component_path != input_path:
        verify_wave(original_component_path,component["sha256"],source)
    verify_wave(mixture_path,job["mixture_parent_sha256"],source)
    require(input_bytes == component["bytes"], "input_component_bytes_mismatch")
    pitch_path = safe_path(job["pitch_path"],pilot_root)
    pitch,pitch_hash = read_json(pitch_path,MAX_PITCH_JSON,job["pitch_sha256"])
    excerpt,branches = validate_pitch(pitch,job,source,registry_hash,input_path)
    segments = reference_segments(truth)
    frame_rows, transition_details, metrics, raw_rows = [],[],[],{}
    for branch in branches:
        rows = []
        for frame in branch["frames"]:
            classified = classify_frame(frame,branch,segments,source["sample_rate"])
            row = {"case_id":job["case_id"], "component":job["component"], "branch":branch["name"],
                   "audio_relative_seconds":frame["audio_relative_seconds"],
                   "source_timeline_seconds":frame["source_timeline_seconds"],
                   "window_start_seconds":frame["window_start_seconds_audio_relative"],
                   "window_end_seconds":frame["window_end_seconds_audio_relative"],
                   "estimated_frequency_hz":frame["frequency_hz"],
                   "voicing_probability":frame.get("voicing_probability"), **classified}
            rows.append(row)
            frame_rows.append(row)
        transitions = transition_rows(branch["frames"],branch,segments,source["sample_rate"])
        transition_details.extend({"case_id":job["case_id"],"component":job["component"],**t} for t in transitions)
        metric = {"branch":branch["name"], **summarize_frames(rows),
                  "transition_metrics":{"counts":dict(Counter(t["status"] for t in transitions)),
                        "timing_bias_seconds":error_summary([t["signed_timing_bias_seconds"] for t in transitions if t["status"]=="measured"])},
                  "conditions":{condition:summarize_frames([r for r in rows if r["condition"]==condition])
                                for condition in sorted({r["condition"] for r in rows})}}
        metrics.append(metric)
        raw_rows[branch["name"]] = rows
    return {"case_id":job["case_id"],"component":job["component"],"status":"completed_measurements",
            "unsupported_claims":unsupported_claims(pitch),
            "coverage_spans":job["observed_coverage_spans"], "branches":metrics,
            "provenance":{"input_sha256":job["input_sha256"],"mixture_parent_sha256":job["mixture_parent_sha256"],
                          "truth_sha256":truth_hash,"pitch_sha256":pitch_hash,"worker_sha256":job["worker_sha256"],
                          "versions":job["versions"],"command":job["command"]}},frame_rows,transition_details,raw_rows


def evaluate(fixture_index,pilot_index):
    fixture_index,pilot_index = safe_path(fixture_index),safe_path(pilot_index)
    bank,bank_hash = read_json(fixture_index)
    pilot,pilot_hash = read_json(pilot_index)
    require(bank.get("schema_version") == 2 and bank.get("suite") == "technical-v2"
            and bank.get("ground_truth_scope") == "generator_only_not_musician", "unsupported_bank_schema")
    cases = bank.get("cases")
    require(isinstance(cases,list) and len(cases) == bank.get("case_count") == 12, "bank_case_count")
    require(len({c["id"] for c in cases}) == 12, "duplicate_bank_case")
    require(abs(sum(number(c["duration_seconds"],0,12) for c in cases)-120) <= EPS
            and number(bank.get("total_duration_seconds")) == 120, "bank_duration_bound")
    registry_hash = fingerprint(bank["instrument_registry_sha256"])
    require(pilot.get("schema_version") == 1 and pilot.get("bank_index_sha256") == bank_hash
            and pilot.get("instrument_registry_sha256") == registry_hash, "pilot_index_binding_mismatch")
    require(number(pilot.get("budget_seconds")) == 30, "pilot_budget_required")
    jobs = pilot.get("jobs")
    require(isinstance(jobs,list) and len(jobs) == 4 and {j["case_id"] for j in jobs} == set(PILOT),
            "mandatory_pilot_jobs_required")
    for job in jobs:
        component,budget = PILOT[job["case_id"]]
        require(job.get("component") == component and number(job.get("requested_budget_seconds")) == budget
                and number(job.get("requested_start_seconds")) == 0, "fixed_pilot_job_mismatch")
        require(job.get("status") == "completed_measurements", "mandatory_pilot_job_incomplete")
        number(job.get("wall_seconds"),0,900)
        fingerprint(job.get("worker_sha256"))
        require(isinstance(job.get("versions"),dict) and set(job["versions"]) == {"librosa","numpy","python"}
                and all(isinstance(v,str) and 0<len(v)<=80 for v in job["versions"].values()), "worker_versions_required")
        require(isinstance(job.get("command"),list) and 1<=len(job["command"])<=32
                and all(isinstance(s,str) and len(s)<=4096 for s in job["command"]), "worker_command_required")
    require(len({job["worker_sha256"] for job in jobs}) == 1
            and len({json.dumps(job["versions"],sort_keys=True) for job in jobs}) == 1, "worker_revision_drift")
    results,frames,transitions = [],[],[]
    all_rows = defaultdict(list)
    by_id = {case["id"]:case for case in cases}
    for job in jobs:
        result,f,t,raw = evaluate_job(job,by_id[job["case_id"]],fixture_index.parent,pilot_index.parent,registry_hash)
        results.append(result)
        frames.extend(f)
        transitions.extend(t)
        for branch,rows in raw.items():
            all_rows[branch].extend(rows)
    alerts = []
    aggregates = []
    for branch,rows in sorted(all_rows.items()):
        aggregate = {"branch":branch,**summarize_frames(rows)}
        aggregate["conditions"] = {condition:summarize_frames([r for r in rows if r["condition"]==condition])
                                   for condition in sorted({r["condition"] for r in rows})}
        aggregates.append(aggregate)
    for result in results:
        for metric in result["branches"]:
            m = metric["stable_monophonic_metrics"]
            prefix = {"case_id":result["case_id"],"branch":metric["branch"]}
            if m["raw_pitch_accuracy"]["denominator"]>=20 and m["raw_pitch_accuracy"]["value"]<.9:
                alerts.append({**prefix,"kind":"low_raw_pitch_accuracy","value":m["raw_pitch_accuracy"]["value"]})
            if m["cents_error"]["n"]>=20 and m["cents_error"]["median_absolute"]>35:
                alerts.append({**prefix,"kind":"high_median_absolute_cents","value":m["cents_error"]["median_absolute"]})
            if m["voicing_false_alarm"]["numerator"]:
                alerts.append({**prefix,"kind":"stable_silence_false_voicing","count":m["voicing_false_alarm"]["numerator"]})
    unsupported_count = sum(len(r["unsupported_claims"]) for r in results)
    result = {"schema_version":1,"suite":"pitch-calibration-v1",
              "status":"generated_fixture_calibration_failed_hard_gates" if unsupported_count else
                       "completed_with_regression_alerts" if alerts else "completed_measurements",
              "ground_truth_scope":"generator_only_not_musician","listening_accepted":False,"real_performance_grading":False,
              "source_audio_bytes_read":True,"source_audio_decoded":False,"inference_invoked":False,
              "bank_index_sha256":bank_hash,"pilot_index_sha256":pilot_hash,"instrument_registry_sha256":registry_hash,
              "evaluator_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "created_at":datetime.now(timezone.utc).isoformat(),"pilot_coverage_seconds":30,
              "case_count":len(results),"frame_count":len(frames),"cases":results,"aggregate_branches":aggregates,
              "quality_alerts":alerts,"hard_failure_count":unsupported_count,
              "unsupported_claim_count":unsupported_count,"hard_gates_passed":unsupported_count == 0,
              "unrequested_bank_cases":[c["id"] for c in cases if c["id"] not in PILOT],
              "metric_policy":{"pitch_tolerance_cents":50,"posthoc_delay_or_tuning_correction":False,
                               "branch_selection_by_truth":False,"p95_minimum_n":20},
              "limitations":["Supplied generated-reference provenance is verified; waveform realism and labels require the separately tested generator.",
                              "These synthetic measurements do not establish actual-take note correctness or musical error confidence.",
                              "pYIN probability remains voicing algorithm evidence, never note-correctness probability."]}
    return result,frames,transitions


def write_atomic(path,data):
    temporary = path.with_name(path.name+".pending")
    require(not temporary.exists() and not temporary.is_symlink(), "temporary_output_exists")
    with temporary.open("x",encoding="utf-8") as handle:
        os.chmod(temporary,0o600)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def write_csv(path,rows,columns):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer,fieldnames=columns,extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k:json.dumps(v,allow_nan=False) if isinstance(v,(list,dict)) else v for k,v in row.items()})
    write_atomic(path,buffer.getvalue())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-index",required=True)
    parser.add_argument("--pilot-index",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--summary",action="store_true")
    args = parser.parse_args()
    started = time.monotonic()
    try:
        output = safe_path(args.output)
        require(output != ALLOWED and not output.exists(), "new_output_directory_required")
        output.parent.mkdir(parents=True,exist_ok=True)
        output.mkdir(mode=0o700)
    except (EvaluationError,OSError) as exc:
        print(f"pitch evaluation: {exc}",file=sys.stderr)
        return 2
    code = 0
    try:
        result,frames,transitions = evaluate(args.fixture_index,args.pilot_index)
        code = 0 if result["hard_gates_passed"] else 1
    except (EvaluationError,OSError,KeyError,TypeError,AttributeError) as exc:
        result = {"schema_version":1,"suite":"pitch-calibration-v1","status":"failed_structural",
                  "error":str(exc),"hard_failure_count":1,"ground_truth_scope":"generator_only_not_musician",
                  "hard_gates_passed":False,
                  "listening_accepted":False,"real_performance_grading":False,"source_audio_decoded":False,
                  "inference_invoked":False,"source_audio_bytes_read":None}
        frames,transitions = [],[]
        code = 1
    result["elapsed_seconds"] = time.monotonic()-started
    paths = {"evaluation_json":str(output/"pitch-calibration.json"),
             "frame_errors_csv":str(output/"pitch-frame-errors.csv"),
             "transition_errors_csv":str(output/"pitch-transition-errors.csv")}
    write_atomic(Path(paths["evaluation_json"]),json.dumps(result,indent=2,allow_nan=False)+"\n")
    write_csv(Path(paths["frame_errors_csv"]),frames,["case_id","component","condition","branch","native_reference_sample",
        "audio_relative_seconds","source_timeline_seconds","window_start_seconds","window_end_seconds",
        "reference_frequency_hz","reference_frequencies_hz","estimated_frequency_hz","estimated_voiced",
        "signed_cents","context","voicing_probability","octave_error","non_octave_pitch_error"])
    write_csv(Path(paths["transition_errors_csv"]),transitions,["case_id","component","transition_id","reference_seconds",
        "branch","target_frequency_hz","first_supported_target_seconds","signed_timing_bias_seconds","status"])
    summary = {**paths,**{k:result.get(k) for k in ("status","ground_truth_scope","listening_accepted","real_performance_grading",
        "source_audio_bytes_read","source_audio_decoded","inference_invoked","case_count","frame_count",
        "pilot_coverage_seconds","hard_failure_count","hard_gates_passed","unsupported_claim_count","quality_alerts","error")}}
    print(json.dumps(summary if args.summary else {**result,**paths},allow_nan=False))
    if code:
        reason = result.get("error") or "unsupported_confirmed_claims"
        print(f"pitch evaluation: {reason}; retained {paths['evaluation_json']}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
