#!/usr/bin/env python3
"""Bounded tuning-aware mixture pitch candidates; not intended-note grading."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

RATE = 16000
HOP = 256
MAX_ANALYSIS_SECONDS = 30
PYIN_TIMEOUT_SECONDS = 180
BRANCHES = (("low_register", 4096, 28, 500), ("high_register", 1024, 200, 2000))
NOTE_NAMES = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("guitar_features_shared", ROOT / "scripts/guitar_features.py")
features = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(features)


def note_mapping(frequency: float, context: dict) -> dict:
    if not math.isfinite(frequency) or frequency <= 0:
        raise ValueError("Pitch frequency must be finite and positive")
    midi_float = 69 + 12 * math.log2(frequency / 440)
    midi = round(midi_float)
    mappings = []
    for string in context.get("tuning_metadata", {}).get("strings", []):
        distance = midi - string["midi"]
        if distance >= 0:
            mappings.append({"string_number": string["string_number"], "open_note": string["note"],
                             "semitones_above_open": distance,
                             "qualification": "hypothetical_not_identified_string_or_fret"})
    return {"note": NOTE_NAMES[midi % 12] + str(midi // 12 - 1), "midi_nearest": midi,
            "cents_from_equal_tempered_note": (midi_float - midi) * 100,
            "frequency_reference_hz": 440 * 2 ** ((midi - 69) / 12),
            "reference_evidence": "theoretical_A4_440_and_registry_inferred_octaves",
            "possible_string_mappings": mappings, "identified_string": None}


def schedule_excerpts(duration: float, budget: float = 20, start: float | None = None) -> list[dict]:
    if (not math.isfinite(duration) or duration <= 0 or not math.isfinite(budget)
            or not 1 <= budget <= MAX_ANALYSIS_SECONDS):
        raise ValueError("Positive finite duration and analysis budget between 1 and 30 seconds required")
    if start is not None:
        if not math.isfinite(start) or not 0 <= start < duration:
            raise ValueError("Start seconds must be finite and inside the recording")
        return [{"start_seconds": start, "end_seconds": min(duration, start + budget)}]
    if duration <= budget:
        return [{"start_seconds": 0.0, "end_seconds": duration}]
    count = math.ceil(budget / 5)
    width = budget / count
    if count == 1:
        return [{"start_seconds": duration - width, "end_seconds": duration}]
    return [{"start_seconds": i * (duration - width) / (count - 1),
             "end_seconds": i * (duration - width) / (count - 1) + width}
            for i in range(count)]


def harmonic_evidence(power, frequency: float, frame_size: int, rate: int = RATE) -> dict:
    """Observed FFT-bin energy near predicted harmonics; not fundamental proof."""
    total = float(sum(power))
    bin_width = rate / frame_size
    used = set()
    partials = []
    for harmonic in range(1, 9):
        target = frequency * harmonic
        if target >= rate / 2:
            break
        center = round(target / bin_width)
        indices = range(max(1, center - 1), min(len(power), center + 2))
        energy = float(sum(power[i] for i in indices))
        used.update(indices)
        partials.append({"harmonic": harmonic, "target_hz": target,
                         "energy_fraction": energy / total if total > 0 else None})
    return {"bin_width_hz": bin_width, "neighborhood_half_width_bins": 1,
            "harmonics": partials,
            "union_energy_fraction": float(sum(power[i] for i in used)) / total if total > 0 else None,
            "interpretation": "spectral_support_not_probability_or_played_fundamental_identity"}


def extract_branches(samples) -> dict:
    """Called in an isolated bounded process; tests may call it directly."""
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
        try:
            configured = int(os.environ.get(variable, "2"))
        except ValueError:
            configured = 2
        os.environ[variable] = str(max(1, min(2, configured)))
    import librosa
    import numpy as np
    signal = np.asarray(samples, dtype=np.float32)
    if signal.ndim != 1 or not len(signal) or not np.isfinite(signal).all():
        raise ValueError("Finite nonempty mono signal required")
    output = []
    for name, frame_size, low, high in BRANCHES:
        pitch, voiced, probability = librosa.pyin(signal, sr=RATE, fmin=low, fmax=high,
                frame_length=frame_size, hop_length=HOP, center=True, fill_na=np.nan,
                resolution=.2, n_thresholds=50)
        powers = np.abs(librosa.stft(signal, n_fft=frame_size, hop_length=HOP, center=True)) ** 2
        frames = []
        for index, (hz, is_voiced, score) in enumerate(zip(pitch, voiced, probability)):
            center_seconds = index * HOP / RATE
            extent_start = max(0.0, center_seconds-frame_size/(2*RATE))
            extent_end = min(len(signal)/RATE, center_seconds+frame_size/(2*RATE))
            if center_seconds >= len(signal)/RATE:
                break
            valid = bool(is_voiced) and bool(np.isfinite(hz))
            frequency = float(hz) if valid else None
            frame = {"center_seconds_in_excerpt": center_seconds,
                     "window_start_seconds_in_excerpt": extent_start,
                     "window_end_seconds_in_excerpt": extent_end,
                     "edge_context_complete": center_seconds >= frame_size/(2*RATE)
                                              and center_seconds+frame_size/(2*RATE) <= len(signal)/RATE,
                     "frequency_hz": frequency,
                     "voiced": bool(is_voiced),
                     "voicing_probability": float(score) if np.isfinite(score) else None,
                     "confidence_kind": "pYIN_algorithm_probability_not_calibrated_for_distorted_guitar"}
            if valid:
                frame["harmonic_evidence"] = harmonic_evidence(powers[:, index], frequency, frame_size)
                alternatives = []
                for factor in (.5, 2):
                    candidate = frequency * factor
                    if 28 <= candidate <= 2000:
                        alternatives.append({"frequency_hz": candidate, "factor": factor,
                                             "harmonic_evidence": harmonic_evidence(powers[:, index], candidate, frame_size),
                                             "status": "unresolved_octave_alternative_not_independent_detection"})
                frame["octave_alternatives"] = alternatives
            else:
                frame["abstention_reason"] = "pYIN_unvoiced_or_no_candidate"
            frames.append(frame)
        output.append({"name": name, "frame_samples": frame_size, "frame_seconds": frame_size/RATE,
                       "minimum_hz": low, "maximum_hz": high, "frames": frames})
    return {"branches": output, "versions": {"librosa": librosa.__version__, "numpy": np.__version__}}


def child_main() -> int:
    try:
        serialized = sys.stdin.read(32_000_001)
        if len(serialized) > 32_000_000:
            raise ValueError("Internal pYIN request exceeds bounded input size")
        payload = json.loads(serialized)
        excerpts = payload["excerpts"]
        if (not isinstance(excerpts, list) or not 1 <= len(excerpts) <= 6
                or sum(len(e["samples"]) for e in excerpts) > RATE*MAX_ANALYSIS_SECONDS):
            raise ValueError("Internal pYIN excerpts exceed bounded analysis coverage")
        results = []
        for excerpt in excerpts:
            if not excerpt["samples"]:
                raise ValueError("Internal pYIN excerpt is empty")
            results.append({"start_seconds": excerpt["start_seconds"], "end_seconds": excerpt["end_seconds"],
                            **extract_branches(excerpt["samples"])})
        print(json.dumps({"excerpts": results}, allow_nan=False))
        return 0
    except (ImportError, ValueError, TypeError, KeyError) as exc:
        print(f"pitch analysis: {exc}", file=sys.stderr)
        return 1


def bounded_extract(excerpts: list[dict]) -> dict:
    command = [sys.executable, str(Path(__file__).resolve()), "--_pyin-worker"]
    completed = subprocess.run(command, input=json.dumps({"excerpts": excerpts}),
            capture_output=True, text=True, timeout=PYIN_TIMEOUT_SECONDS, check=False)
    if completed.returncode:
        raise ValueError(completed.stderr[-2500:] or "pYIN worker failed")
    return json.loads(completed.stdout)


def assemble(raw: dict, context: dict, source_start: float = 0) -> tuple[list[dict], dict]:
    excerpts = []
    candidate_count = 0
    frame_count = 0
    edge_candidates = 0
    for excerpt in raw["excerpts"]:
        start = excerpt["start_seconds"]
        for branch in excerpt["branches"]:
            for frame in branch["frames"]:
                frame_count += 1
                center = start + frame["center_seconds_in_excerpt"]
                frame["audio_relative_seconds"] = center
                frame["source_timeline_seconds"] = source_start + center
                for boundary in ("start", "end"):
                    absolute = start + frame[f"window_{boundary}_seconds_in_excerpt"]
                    frame[f"window_{boundary}_seconds_audio_relative"] = absolute
                    frame[f"window_{boundary}_seconds_source_timeline"] = source_start + absolute
                frequency = frame["frequency_hz"]
                if frequency is not None:
                    candidate_count += 1
                    edge_candidates += not frame["edge_context_complete"]
                    frame["note_mapping"] = note_mapping(frequency, context)
                    for alternative in frame.get("octave_alternatives", []):
                        alternative["note_mapping"] = note_mapping(alternative["frequency_hz"], context)
        excerpts.append(excerpt)
    return excerpts, {"branch_frame_count": frame_count, "voiced_candidate_count": candidate_count,
                      "edge_context_incomplete_candidate_count": edge_candidates,
                      "abstained_frame_count": frame_count-candidate_count,
                      "interpretation": "overlapping_branch_hypotheses_not_unique_notes"}


def atomic_json(path: Path, payload: dict) -> None:
    encoded = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".pitch-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--max-analysis-seconds", type=float, default=20)
    parser.add_argument("--start-seconds", type=float)
    args = parser.parse_args()
    started = time.monotonic()
    try:
        source = args.input.expanduser().resolve(strict=True)
        destination = args.run_dir.expanduser().resolve() / "pitch.json"
        if source == destination or not source.is_file():
            raise ValueError("Input must be a regular file and must differ from output")
        source_stat = source.stat()
        digest = hashlib.sha256()
        with source.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024*1024), b""):
                digest.update(chunk)
        samples, provenance = features.load(source)
        context = features.instrument_context()
        duration = len(samples) / RATE
        spans = schedule_excerpts(duration, args.max_analysis_seconds, args.start_seconds)
        # Quantize excerpt positions to actual analysis samples and disclose their coverage.
        excerpts = []
        for span in spans:
            low = round(span["start_seconds"]*RATE)
            high = min(len(samples), round(span["end_seconds"]*RATE))
            excerpts.append({"start_seconds": low/RATE, "end_seconds": high/RATE,
                             "samples": list(samples[low:high])})
        raw = bounded_extract(excerpts)
        audio = provenance["audio_stream"]
        result = {"schema_version": 1, "tool": "pitch", "status": "experimental_candidate_analysis",
                  "source": {"path": str(source), "sha256": digest.hexdigest(),
                             "audio_stream_start_seconds": float(audio.get("start_time", 0)),
                             "sample_rate": int(audio["sample_rate"]), "channels": audio["channels"]},
                  "instrument_context": context,
                  "analysis": {"sample_rate": RATE, "channels": 1, "duration_seconds": duration,
                               "maximum_input_seconds": 300, "hop_samples": HOP, "hop_seconds": HOP/RATE,
                               "max_analysis_seconds": args.max_analysis_seconds, "numerical_threads_maximum": 2,
                               "pyin_timeout_seconds": PYIN_TIMEOUT_SECONDS, "pyin_resolution_semitones": .2,
                               "pyin_threshold_count": 50, "backend": "librosa_pyin",
                               "sampling": "explicit_contiguous_excerpt" if args.start_seconds is not None else "distributed_excerpts_including_ending",
                               "frame_timestamp": "center_with_explicit_window_extent",
                               "coverage_seconds": sum(e["end_seconds"]-e["start_seconds"] for e in excerpts),
                               "coverage_spans_audio_relative": [{"start_seconds": e["start_seconds"], "end_seconds": e["end_seconds"]} for e in excerpts]},
                  "provenance": {**provenance, "worker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                 "python_version": sys.version.split()[0], "analysis_interpreter": sys.executable},
                  "interpretation": {"note_transcription": "unsupported_candidate_hypotheses_only",
                                     "polyphonic_transcription": "unsupported", "intended_notes": None,
                                     "performance_grade": "not_graded", "tonic": None, "mode": None,
                                     "tuning_measurement": "not_performed_registry_is_theoretical",
                                     "limitations": ["Distortion, chords, clicks and missing fundamentals can create octave and source ambiguity.",
                                         "Long low-frequency windows blur rapid transitions; short high-register windows cannot resolve C1.",
                                         "Separate branches are hypotheses, not unique detected notes or confirmed techniques.",
                                         "Sparse distributed coverage is not full-song transcription; excerpt edges lack original context.",
                                         "pYIN voicing probabilities are not calibrated probabilities of played-note correctness."]}}
        features.inherit_manifest_lineage(result, destination.parent)
        observed, summary = assemble(raw, context, result["source"]["audio_stream_start_seconds"])
        result["observations"] = {"analyzed_excerpts": observed}
        result["summary"] = summary
        result["analysis"]["coverage_fraction"] = result["analysis"]["coverage_seconds"]/duration
        result["analysis"]["coverage_spans_source_timeline"] = [
            {"start_seconds": span["start_seconds"]+result["source"]["audio_stream_start_seconds"],
             "end_seconds": span["end_seconds"]+result["source"]["audio_stream_start_seconds"]}
            for span in result["analysis"]["coverage_spans_audio_relative"]]
        result["analysis"]["elapsed_seconds"] = time.monotonic()-started
        if source.stat().st_size != source_stat.st_size or source.stat().st_mtime_ns != source_stat.st_mtime_ns:
            raise ValueError("Input changed during analysis; output not published")
        atomic_json(destination, result)
        # Console/MCP stays bounded; full per-frame evidence lives in the local artifact.
        print(json.dumps({"pitch_json": str(destination), "schema_version": 1, "status": result["status"],
                          "source": result["source"], "lineage": result["lineage"],
                          "analysis": result["analysis"], "summary": summary}, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        print(f"pitch: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(child_main() if sys.argv[1:] == ["--_pyin-worker"] else main())
