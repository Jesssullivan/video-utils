#!/usr/bin/env python3
"""S1 generated phrase-proposal research. No product defaults or musical grading."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
SUITE = "s1-proposal-1301-1423-v1"
SEEDS = (1301, 1423)
COHORTS = ("low32-sustain", "missing-f0-sustain", "ordered-click-only",
           "fan-only", "palm-recurrence", "legato-recurrence")
ARMS = ("Araw", "S1_support", "S2_multiscale")
PINS = {
    "scripts/guitar_features.py": "2ed031e8000cbcda92b504db10c98de03f456c90573cbff815cbb940c9ac86fe",
    "scripts/rhythm.py": "264b723ca29e4731da0a12d5dce221e7826a38b67f848ce9f4ffcf8bfe4b35b9",
    "scripts/phrase_evaluate.py": "3e503de277b2fd233fe802595a09a655c89669b0eb820f228e677c1b94b828a5",
    "docs/agent-notes/2026-10-05-phrase-guarded-arms.py": "78ca89de9cea327cc4ec1096a83522781a08bc161819699b69797ca273e2fb6c",
    "program/instrument.json": "bd381207d6615814ebee694148357c00719739ec900aa69c96d71b20779707b0",
}
SETTINGS = {
    "minimum_hz": 25., "maximum_hz": 6000., "band_count": 32,
    "guitar_support_maximum_hz": 1800., "minimum_low_band_fraction": .60,
    "noise_floor_quantile": .20, "minimum_floor_ratio": 3.,
    "minimum_shape_variation": .03, "minimum_active_frames": 6,
    "minimum_span_seconds": .5, "maximum_span_seconds": 4.,
    "single_gap_seconds": .24, "multiscale_gap_seconds": [.12, .24, .40],
    "minimum_cosine": .80, "sequence_samples": 32,
    "maximum_duration_ratio": 1.30, "duplicate_both_span_iou": .75,
    "proposal_cap": 10, "segment_cap": 60,
    "fft_samples": 4096, "hop_samples": 256,
    "maximum_frames": 1024, "maximum_dimensions": 64,
}
BUDGETS = {"overall_seconds": 900, "case_seconds": 120, "threads": 2,
           "json_bytes": 2_000_000, "wav_bytes": 1_000_000,
           "native_seconds": 8, "native_rate": 48000, "analysis_rate": 16000}
FFMPEG_PIN = {"path": "/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffmpeg",
              "sha256": "3a315207e67de78e48c3bbb6b3346663f6a27c02e034d65ac72a12fee74c534a"}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def artifact_path(path, existing=False):
    path = Path(path)
    require(".." not in path.parts, "path_traversal")
    if not path.is_absolute():
        path = ROOT / path
    area = ROOT / "artifacts"
    require(path.is_relative_to(area) and path != area, "own_artifacts_required")
    current = ROOT
    for part in path.relative_to(ROOT).parts:
        current = current / part
        require(not current.is_symlink(), "symlink_path")
    if existing:
        require(path.is_file() and not path.is_symlink(), "regular_artifact_required")
    return path


def write_new(path, value):
    path = artifact_path(path)
    raw = encoded(value)
    require(len(raw) <= BUDGETS["json_bytes"], "json_byte_bound")
    with path.open("xb") as handle:
        handle.write(raw)
    path.chmod(0o600)


def unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "duplicate_json_key")
        value[key] = item
    return value


def strict_read(path, expected=None):
    path = Path(path)
    require(not path.is_symlink(), "symlink_file")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_size <= BUDGETS["json_bytes"], "json_regular_bound")
        with os.fdopen(os.dup(fd), "rb") as handle:
            raw = handle.read(BUDGETS["json_bytes"] + 1)
        require(len(raw) == before.st_size <= BUDGETS["json_bytes"], "json_read_extent_bound")
        after = os.fstat(fd)
        require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), "json_changed")
    finally:
        os.close(fd)
    if expected is not None:
        require(hashlib.sha256(raw).hexdigest() == expected, "json_sha256_mismatch")
    def constant(value):
        raise ValueError("nonfinite_json")
    def finite_float(value):
        result = float(value)
        require(math.isfinite(result), "nonfinite_json_float")
        return result
    value = json.loads(raw, object_pairs_hook=unique, parse_constant=constant, parse_float=finite_float)
    return value


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_pins():
    for path, expected in PINS.items():
        require(digest(ROOT / path) == expected, "pinned_source_changed:" + path)


def unit(seed, knob):
    return int.from_bytes(hashlib.sha256(f"{SUITE}:{seed}:{knob}".encode()).digest()[:8], "big") / 2**64


def geometry(seed):
    # Motif and nuisance namespaces stay independent; no pulse-aligned construction.
    sample = lambda key, lo, hi: round((lo + (hi-lo)*unit(seed, "motif:"+key))*48000)
    return {"first_start_sample": sample("first", .85, 1.15),
            "second_start_sample": sample("second", 4.10, 4.55),
            "length_samples": sample("length", 1.65, 1.95),
            "note_position_fractions": [0., .083, .167, .253, .365, .443, .527, .611, .717, .803, .889, .961],
            "midi": [24, 29, 34, 29, 24, 39, 46, 34, 24, 51, 39, 29],
            "internal_rest_fractions": [[.305, .351], [.657, .703]]}


def metadata():
    return {"schema_version": 1, "suite": SUITE, "seeds": list(SEEDS),
            "cohorts": list(COHORTS), "case_count": 12, "audio_seconds": 96,
            "arms": list(ARMS), "settings": SETTINGS, "budgets": BUDGETS,
            "dependency_sha256": PINS,
            "ffmpeg": FFMPEG_PIN,
            "generator_geometry": {str(seed): geometry(seed) for seed in SEEDS},
            "baseline": "frozen existing raw2/4/8/16-pulse search; exact guarded load_search and canonical features; same-source unseeded librosa rhythm",
            "scope": "new heldout synthetic seeds; motif recipe family repeats prior pilot and is not a new real-world distribution",
            "scoring": {"pair_iou_thresholds": [.5, .75], "typed_endpoint_tolerances_seconds": [.02, .05, .1],
                        "matching": "maximum cardinality then maximum mean two-span IoU", "negative_fp": "candidate counts by negative cohort",
                        "pair_matched_endpoint_mae": "all four endpoints of matched pairs; denominators explicit; no common-zero improvement claim"},
            "discovery_truth_input": False, "predictions_global_seal_before_truth_read": True,
            "retune_after_heldout": False, "canonical_defaults_activated": False,
            "musical_performance_graded": False, "physical_articulation_accepted": False}


def authorize(plan_path, plan_hash, release_path, release_hash, phase):
    plan = strict_read(plan_path, plan_hash)
    require(plan == metadata(), "preregistration_changed")
    release = strict_read(release_path, release_hash)
    require(release.get("actor") == "root" and release.get("suite") == SUITE
            and phase in release.get("authorized_phases", []), "root_phase_release_required")
    require(release.get("plan_sha256") == plan_hash and release.get("worker_sha256") == digest(__file__)
            and release.get("dependency_sha256") == PINS and release.get("budgets") == BUDGETS,
            "release_binding_changed")
    verify_pins()
    require(digest(FFMPEG_PIN["path"]) == FFMPEG_PIN["sha256"], "qualified_ffmpeg_changed")
    return {"plan_path": str(plan_path), "plan_sha256": plan_hash,
            "release_path": str(release_path), "release_sha256": release_hash,
            "worker_sha256": digest(__file__)}


def deadline(started, case_started=None):
    require(time.monotonic()-started < BUDGETS["overall_seconds"], "overall_deadline")
    if case_started is not None:
        require(time.monotonic()-case_started < BUDGETS["case_seconds"], "case_deadline")


def construct(seed, cohort, rate=48000):
    """Separate generator-only routine. Never called by source discovery."""
    import numpy as np
    require(seed in SEEDS and cohort in COHORTS, "registered_case_required")
    require(type(rate) is int and 256 <= rate <= 48000, "bounded_rate")
    count = 8*rate
    t = np.arange(count)/rate
    phase = 2*math.pi*unit(seed, "nuisance:phase")
    fan = (.775+.225*np.sin(2*math.pi*.61*t+phase)) * (.009*np.sin(2*math.pi*47*t+phase)+.006*np.sin(2*math.pi*71*t+phase))
    rng = np.random.default_rng(int(unit(seed, "nuisance:rng")*2**63))
    noise = .006*(.8+.2*np.sin(2*math.pi*.43*t+phase))*rng.uniform(-1, 1, count)
    click = np.zeros(count)
    period = .337+.056*unit(seed, "nuisance:period")
    origin = .101+.066*unit(seed, "nuisance:origin")
    events = [(origin+i*period, 3500., .033) for i in range(24) if origin+i*period < 8]
    for start in (.30+.15*unit(seed, "nuisance:ordered1"), 4.6+.25*unit(seed, "nuisance:ordered2")):
        events.extend((start+offset, hz, amp) for offset, hz, amp in zip(
            [0., .173, .367, .581, .809, 1.013, 1.227, 1.451],
            [2200., 5100., 1600., 3700., 5100., 2200., 3700., 1600.],
            [.058, .083, .047, .071, .061, .089, .053, .076]))
    if cohort != "fan-only":
        for start, hz, amp in events:
            mask = (t >= start) & (t < start+.012)
            age = t[mask]-start
            click[mask] += amp*np.exp(-age/.0024)*np.sin(2*math.pi*hz*age)
    clean = np.zeros(count)
    envelope = np.maximum(0, np.minimum(1, np.minimum((t-.5)/.02, (7.5-t)/.02)))
    if cohort == "low32-sustain":
        clean = envelope*.17*np.sin(2*math.pi*32*t)
    elif cohort == "missing-f0-sustain":
        fundamental = 440*2**((24-69)/12)
        clean = envelope*sum(amp*np.sin(2*math.pi*k*fundamental*t)
                             for k, amp in [(2,.1), (3,.065), (4,.035), (5,.02), (7,.012)])
    g = geometry(seed)
    refs = []
    if cohort in COHORTS[4:]:
        n = round(g["length_samples"]*rate/48000)
        mt = np.arange(n)/rate
        positions = np.round(np.asarray(g["note_position_fractions"])*g["length_samples"])/48000
        index = np.maximum(0, np.searchsorted(positions, mt, side="right")-1)
        frequencies = 440*2**((np.asarray(g["midi"])-69)/12)
        age = mt-positions[index]
        hz = frequencies[index]
        if cohort == "palm-recurrence":
            amp = np.maximum(0, np.minimum(1, np.minimum(age/.0015, (.055-age)/.004)))*np.exp(-age/.018)
            radians = 2*math.pi*hz*age
        else:
            previous = frequencies[np.maximum(0, index-1)]
            hz = previous*2**(np.log2(hz/previous)*np.minimum(1, age/.024))
            radians = np.cumsum(2*math.pi*hz/rate)
            amp = np.maximum(0, np.minimum(1, np.minimum(mt/.008, (n/rate-mt)/.008)))
        for low, high in g["internal_rest_fractions"]:
            amp[(mt >= round(low*g["length_samples"])/48000) & (mt < round(high*g["length_samples"])/48000)] = 0
        shape = .16*amp*np.tanh(2.2*(np.sin(radians)+.5*np.sin(2*radians)+.25*np.sin(3*radians)))
        for key in ("first_start_sample", "second_start_sample"):
            begin = round(g[key]*rate/48000)
            clean[begin:begin+n] = shape
        refs = [{"id": f"seed{seed}-{cohort}",
                 "first_span_seconds": [g["first_start_sample"]/48000, (g["first_start_sample"]+g["length_samples"])/48000],
                 "second_span_seconds": [g["second_start_sample"]/48000, (g["second_start_sample"]+g["length_samples"])/48000]}]
    mix = clean+fan+noise+click
    require(np.isfinite(mix).all() and float(np.max(np.abs(mix))) < .5, "generated_peak_bound")
    truth = {"schema_version": 1, "suite": SUITE, "seed": seed, "cohort": cohort,
             "duration_seconds": 8., "recurrence_pairs": refs,
             "native_rate": rate, "native_sample_count": count,
             "ground_truth_scope": "generator_only_not_musician", "musical_performance_graded": False,
             "physical_articulation_accepted": False, "geometry": g,
             "missing_f0_nonlinearity_after_synthesis": False}
    return {"clean": clean, "fan": fan, "noise": noise, "click": click, "mix": mix}, truth


def pcm16(samples):
    import numpy as np
    return np.rint(np.asarray(samples)*32768).astype("<i2").tobytes()


def generate(output, authorization):
    started = time.monotonic()
    output = artifact_path(output)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    cases, shared = [], {}
    for seed in SEEDS:
        for cohort in COHORTS:
            began = time.monotonic()
            deadline(started, began)
            components, truth = construct(seed, cohort)
            name = f"case{len(cases):02d}"
            directory = output/name
            directory.mkdir(mode=0o700)
            assets = {}
            encoded_components = {}
            for key, samples in components.items():
                raw = pcm16(samples)
                encoded_components[key] = raw
                path = directory/(key+".wav")
                with wave.open(str(path), "wb") as handle:
                    handle.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
                    handle.writeframes(raw)
                assets[key] = {"path": str(path.relative_to(output)), "sha256": digest(path), "pcm_sha256": hashlib.sha256(raw).hexdigest()}
                if key in ("fan", "noise", "click") and not (key == "click" and cohort == "fan-only"):
                    identity = f"{seed}:{key}"
                    require(identity not in shared or shared[identity] == assets[key]["sha256"], "nuisance_not_shared")
                    shared[identity] = assets[key]["sha256"]
            import numpy as np
            decoded = {key: np.frombuffer(raw, dtype="<i2").astype("int32") for key, raw in encoded_components.items()}
            error = np.abs(decoded["mix"]-sum(decoded[key] for key in ("clean", "fan", "noise", "click")))
            require(int(error.max()) <= 2, "component_sum_two_lsb")
            truth.update(source_sha256=assets["mix"]["sha256"], assets=assets,
                         rendered_component_sum_maximum_lsb=int(error.max()))
            write_new(directory/"truth.json", truth)
            cases.append({"id": name, "seed": seed, "cohort": cohort, "source": assets["mix"],
                          "truth": {"path": str((directory/"truth.json").relative_to(output)), "sha256": digest(directory/"truth.json")},
                          "assets": assets, "elapsed_seconds": time.monotonic()-began})
            deadline(started, began)
    verify_pins()
    require(digest(__file__) == authorization["worker_sha256"], "worker_changed")
    write_new(output/"bank.json", {"schema_version": 1, "suite": SUITE, "cases": cases,
              "shared_nuisance_sha256": shared, "authorization": authorization,
              "elapsed_seconds": time.monotonic()-started, "status": "generated_no_discovery"})
    return output/"bank.json"


def finite_features(features, times, centers, duration):
    import numpy as np
    for value in (features, times, centers):
        require(np.asarray(value).dtype.kind in "fiu", "numeric_nonboolean_features")
    x, t, f = (np.asarray(value, dtype=float) for value in (features, times, centers))
    require(type(duration) in (int, float) and math.isfinite(duration) and 0 < duration <= 12, "bounded_duration")
    require(x.ndim == 2 and 4 <= x.shape[0] <= SETTINGS["maximum_frames"]
            and 2 <= x.shape[1] <= SETTINGS["maximum_dimensions"], "feature_shape_bound")
    require(t.shape == (len(x),) and f.shape == (x.shape[1],), "feature_axes")
    require(all(np.isfinite(value).all() for value in (x, t, f)) and np.all(x >= 0), "finite_nonnegative_features")
    require(np.all(np.diff(t) > 0) and t[0] >= 0 and t[-1] <= duration
            and np.all(np.diff(f) > 0) and f[0] >= 20 and f[-1] <= 8000, "feature_clock_frequency_bounds")
    require(float(np.max(x)) <= 1e12, "feature_value_bound")
    return x, t, f


def interval_iou(a, b):
    return max(0., min(a[1], b[1])-max(a[0], b[0])) / (max(a[1], b[1])-min(a[0], b[0]))


def support_segments(features, times, centers, duration, gap):
    import numpy as np
    x, t, f = finite_features(features, times, centers, duration)
    require(type(gap) in (int, float) and gap in SETTINGS["multiscale_gap_seconds"], "registered_gap")
    low = f <= SETTINGS["guitar_support_maximum_hz"]
    floor = np.quantile(x, SETTINGS["noise_floor_quantile"], axis=0)
    total = x.sum(axis=1)
    energy = x[:, low].sum(axis=1)
    floor_energy = max(float(floor[low].sum()), 1e-12)
    fraction = energy/np.maximum(total, 1e-12)
    active = (energy >= floor_energy*SETTINGS["minimum_floor_ratio"]) & (fraction >= SETTINGS["minimum_low_band_fraction"])
    indices = np.flatnonzero(active)
    if not len(indices):
        return [], {"active_frame_count": 0, "noise_floor_energy": floor_energy}
    breaks = np.flatnonzero(np.diff(t[indices]) > gap)+1
    groups = np.split(indices, breaks)
    step = float(np.median(np.diff(t)))
    result = []
    for group in groups:
        if len(group) < SETTINGS["minimum_active_frames"]:
            continue
        first, last = int(group[0]), int(group[-1])
        begin, end = max(0., float(t[first])-step/2), min(duration, float(t[last])+step/2)
        if not SETTINGS["minimum_span_seconds"] <= end-begin <= SETTINGS["maximum_span_seconds"]:
            continue
        content = np.maximum(0, x[group][:, low]-floor[low])
        shape = content/np.maximum(content.sum(axis=1)[:, None], 1e-12)
        variation = float(np.sqrt(np.mean(np.var(shape, axis=0))))
        if variation < SETTINGS["minimum_shape_variation"]:
            continue
        # Interpolate every frame in the proposed span, including acoustic gaps.
        full = np.maximum(0, x[first:last+1][:, low]-floor[low])
        full = np.log1p(full/floor_energy)
        sample_times = np.linspace(t[first], t[last], SETTINGS["sequence_samples"])
        sequence = np.stack([np.interp(sample_times, t[first:last+1], full[:, j]) for j in range(full.shape[1])], axis=1)
        sequence -= sequence.mean(axis=0)
        norm = float(np.linalg.norm(sequence))
        if norm <= 1e-8:
            continue
        result.append({"span": [begin, end], "gap_seconds": gap,
                       "shape_variation": variation, "active_frames": len(group),
                       "sequence": (sequence/norm).ravel()})
    result.sort(key=lambda row: (row["span"][0], row["span"][1]))
    return result[:SETTINGS["segment_cap"]], {"active_frame_count": len(indices), "noise_floor_energy": floor_energy,
                                             "segment_cap_excluded": max(0, len(result)-SETTINGS["segment_cap"])}


def propose(features, times, centers, duration, *, multiscale=False):
    """Finite clock-bound features only; no score, notes, labels or intended spans."""
    import numpy as np
    require(type(multiscale) is bool, "boolean_arm")
    gaps = SETTINGS["multiscale_gap_seconds"] if multiscale else [SETTINGS["single_gap_seconds"]]
    segments, audits = [], []
    for gap in gaps:
        rows, audit = support_segments(features, times, centers, duration, gap)
        segments.extend(rows)
        audits.append({"gap_seconds": gap, **audit})
    require(len(segments) <= 180, "multiscale_segment_bound")
    candidates = []
    for i, first in enumerate(segments):
        for second in segments[i+1:]:
            a, b = sorted((first, second), key=lambda row: row["span"][0])
            if a["span"][1] > b["span"][0]:
                continue
            lengths = [row["span"][1]-row["span"][0] for row in (a, b)]
            if max(lengths)/min(lengths) > SETTINGS["maximum_duration_ratio"]:
                continue
            cosine = float(np.clip(a["sequence"] @ b["sequence"], -1, 1))
            if cosine < SETTINGS["minimum_cosine"]:
                continue
            candidates.append({"first_span_seconds": a["span"], "second_span_seconds": b["span"],
                               "similarity": cosine, "gap_seconds": [a["gap_seconds"], b["gap_seconds"]],
                               "shape_variation": [a["shape_variation"], b["shape_variation"]],
                               "confidence": None, "performance_issue_confirmed": False})
    candidates.sort(key=lambda row: (-row["similarity"], row["first_span_seconds"], row["second_span_seconds"], row["gap_seconds"]))
    retained = []
    for row in candidates:
        if any(all(interval_iou(row[key], other[key]) >= SETTINGS["duplicate_both_span_iou"]
                   for key in ("first_span_seconds", "second_span_seconds")) for other in retained):
            continue
        retained.append(row)
        if len(retained) == SETTINGS["proposal_cap"]:
            break
    return {"candidates": retained, "support_audits": audits, "segment_count": len(segments),
            "candidate_count_before_deduplication": len(candidates), "proposal_cap_saturated": len(retained) == SETTINGS["proposal_cap"],
            "musical_phrase_identity": "unknown", "truth_supplied": False, "canonical_defaults_activated": False}


def extract(samples):
    """Pinned canonical frontend features and independent logarithmic-band powers."""
    import librosa
    import numpy as np
    y = np.asarray(samples, dtype=np.float32)
    require(y.shape == (128000,) and np.isfinite(y).all(), "analysis_pcm_extent")
    power = np.abs(librosa.stft(y, n_fft=4096, hop_length=256, center=True))**2
    mel = librosa.feature.melspectrogram(S=power, sr=16000, n_fft=4096, n_mels=48, fmin=28)
    mfcc = librosa.feature.mfcc(S=librosa.power_to_db(mel), n_mfcc=12)[1:]
    chroma = librosa.feature.chroma_stft(S=power, sr=16000, n_fft=4096, hop_length=256, tuning=0)
    centroid = librosa.feature.spectral_centroid(S=np.sqrt(power), sr=16000)[0]
    flatness = librosa.feature.spectral_flatness(S=np.sqrt(power))[0]
    rms = librosa.feature.rms(S=np.sqrt(power), frame_length=4096, hop_length=256)[0]
    frame_features = np.vstack((mfcc, chroma*3, np.log1p(centroid), flatness, np.log(np.maximum(rms, 1e-8))))
    times = librosa.frames_to_time(np.arange(power.shape[1]), sr=16000, hop_length=256)
    onsets = librosa.onset.onset_detect(y=y, sr=16000, hop_length=256, units="time", backtrack=False)
    edges = np.geomspace(SETTINGS["minimum_hz"], SETTINGS["maximum_hz"], SETTINGS["band_count"]+1)
    frequencies = np.fft.rfftfreq(4096, 1/16000)
    powers = np.stack([power[(frequencies >= a) & (frequencies < b)].sum(axis=0) for a, b in zip(edges, edges[1:])], axis=1)
    centers = np.sqrt(edges[:-1]*edges[1:])
    return {"features": frame_features, "times": times, "centroid": centroid, "onsets": onsets}, powers, centers


def discover_source(source, expected_sha):
    """Opaque source-only entry. Does not accept bank/case/truth/reference arguments."""
    import numpy as np
    source = artifact_path(source, existing=True)
    require(digest(source) == expected_sha and source.stat().st_size <= BUDGETS["wav_bytes"], "source_identity_bound")
    with wave.open(str(source), "rb") as handle:
        require((handle.getframerate(), handle.getnchannels(), handle.getsampwidth(), handle.getnframes()) == (48000, 1, 2, 384000), "native_pcm_header")
    rhythm = load_module(ROOT/"scripts/rhythm.py", "s1_frozen_rhythm")
    decoded = subprocess.run([FFMPEG_PIN["path"], "-hide_banner", "-loglevel", "error", "-nostdin",
                              "-threads", "1", "-i", str(source), "-map", "0:a:0", "-vn", "-t", "8",
                              "-ac", "1", "-ar", "16000", "-filter_threads", "1", "-threads", "1", "-f", "f32le", "pipe:1"],
                             capture_output=True, timeout=20, check=True)
    require(len(decoded.stdout) == 128000*4, "decoded_pcm_byte_extent")
    samples = np.frombuffer(decoded.stdout, dtype="<f4")
    require(len(samples) == 128000, "analysis_sample_count")
    analysis = rhythm.analyze(samples, source_start=0., bpm=None, backend="librosa")
    grid, selected = analysis.get("click_grid") or {}, analysis.get("selected_periodicity") or {}
    bpm = grid.get("bpm") or selected.get("bpm")
    cache, powers, centers = extract(samples)
    baseline = []
    if bpm is not None:
        require(type(bpm) in (int, float) and math.isfinite(bpm) and 20 <= bpm <= 600, "measured_bpm_bounds")
        period = 60/bpm
        origin = max(0., grid.get("phase_seconds_audio_relative") or 0.) % period
        guard = load_module(ROOT/"docs/agent-notes/2026-10-05-phrase-guarded-arms.py", "s1_frozen_guard")
        cache = guard.validate(cache, period, origin, 8.)
        pulse_features, centroids = guard.aggregate(cache, period, origin, 8.)
        search, search_hash = guard.load_search()
        baseline = search(pulse_features, period, 8., cache["onsets"], origin, centroids)["recurrence_candidates"]
    else:
        period, origin, search_hash = None, None, None
    first = propose(powers, cache["times"], centers, 8., multiscale=False)
    second = propose(powers, cache["times"], centers, 8., multiscale=True)
    require(digest(source) == expected_sha, "source_changed_during_discovery")
    return {"schema_version": 1, "source_sha256": expected_sha,
            "arms": {"Araw": baseline, "S1_support": first["candidates"], "S2_multiscale": second["candidates"]},
            "diagnostics": {"S1_support": {k:v for k,v in first.items() if k != "candidates"},
                            "S2_multiscale": {k:v for k,v in second.items() if k != "candidates"}},
            "baseline_pulse": {"bpm": bpm, "period": period, "origin": origin, "search_sha256": search_hash,
                               "basis": "same_source_unseeded_analysis", "generator_bpm_supplied": False},
            "feature_clock": {"rate": 16000, "hop": 256, "fft": 4096, "centered": True, "frame_count": len(cache["times"])},
            "environment": {"python": sys.version, "numpy": np.__version__,
                            "threads": {key: os.environ.get(key) for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS")},
                            "ffmpeg": FFMPEG_PIN},
            "analysis_pcm_sha256": hashlib.sha256(np.asarray(samples, dtype="<f4").tobytes()).hexdigest(),
            "discovery_truth_input": False, "performance_issue_confirmed": False,
            "listening_accepted": False, "canonical_defaults_activated": False}


def discover(bank_path, bank_hash, output, authorization):
    started = time.monotonic()
    bank_path = artifact_path(bank_path, existing=True)
    bank = strict_read(bank_path, bank_hash)
    require(bank.get("suite") == SUITE and len(bank["cases"]) == 12, "registered_bank_required")
    require([(row["seed"], row["cohort"]) for row in bank["cases"]] == [(seed, cohort) for seed in SEEDS for cohort in COHORTS]
            and bank["authorization"]["worker_sha256"] == authorization["worker_sha256"]
            and bank["authorization"]["plan_sha256"] == authorization["plan_sha256"], "bank_plan_source_binding")
    output = artifact_path(output)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    # Reduce bank to opaque source+hash only. Discovery never reads truth bytes.
    sources = [(artifact_path(bank_path.parent/row["source"]["path"], existing=True), row["source"]["sha256"]) for row in bank["cases"]]
    predictions = []
    for index, (source, source_hash) in enumerate(sources):
        began = time.monotonic()
        deadline(started, began)
        path = output/f"prediction{index:02d}.json"
        # A separate opaque process enforces the per-case bound and isolates labels.
        # subprocess.run owns and reaps only the child it creates on timeout.
        completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "_source",
                                    str(source), source_hash, str(path), authorization["worker_sha256"]],
                                   capture_output=True, text=True,
                                   timeout=min(BUDGETS["case_seconds"], BUDGETS["overall_seconds"]-(time.monotonic()-started)),
                                   check=False)
        require(completed.returncode == 0, "opaque_discovery_failed:"+completed.stderr[-1000:])
        prediction = strict_read(path)
        deadline(started, began)
        predictions.append({"path": path.name, "sha256": digest(path), "source_sha256": source_hash})
        print(json.dumps({"case": index, "status": "sealed_case_truth_unopened", "elapsed_seconds": prediction["elapsed_seconds"]}), flush=True)
    verify_pins()
    require(digest(bank_path) == bank_hash and digest(__file__) == authorization["worker_sha256"], "discovery_bindings_changed")
    write_new(output/"predictions-sealed.json", {"schema_version": 1, "suite": SUITE,
              "status": "all_predictions_sealed_truth_unopened", "bank_sha256": bank_hash,
              "predictions": predictions, "authorization": authorization, "elapsed_seconds": time.monotonic()-started})
    return output/"predictions-sealed.json"


def pair_spans(value):
    if "first_span_seconds" in value:
        return [value["first_span_seconds"], value["second_span_seconds"]]
    return [[value[k+"_start_seconds"], value[k+"_end_seconds"]] for k in ("first", "second")]


def score_rows(references, estimates, duration=8.):
    evaluator = load_module(ROOT/"scripts/phrase_evaluate.py", "s1_frozen_evaluator")
    pairs = []
    for threshold in (.5, .75):
        metric = evaluator.recurrence_metrics(references, estimates, duration, threshold)
        metric.update(reference_count=len(references), estimate_count=len(estimates))
        offsets = [pair_spans(estimates[row["estimate_index"]])[k][v]-pair_spans(references[row["reference_index"]])[k][v]
                   for row in metric["matches"] for k in (0,1) for v in (0,1)]
        metric.update(endpoint_offset_seconds=offsets, endpoint_count=len(offsets),
                      matched_endpoint_mae_seconds=sum(abs(v) for v in offsets)/len(offsets) if offsets else None)
        pairs.append(metric)
    endpoints = []
    for threshold in (.02, .05, .1):
        matches = []
        for k, prefix in enumerate(("first", "second")):
            for v, edge in enumerate(("start", "end")):
                left = [pair_spans(row)[k][v] for row in references]
                right = [pair_spans(row)[k][v] for row in estimates]
                found = evaluator.optimal_matching(left, right, lambda a,b: max(0., 1-abs(a-b)/threshold) if abs(a-b) <= threshold+1e-12 else None)
                matches.extend({"reference_index": i, "estimate_index": j, "endpoint": prefix+"_"+edge,
                                "offset_seconds": right[j]-left[i]} for i,j,_ in found)
        endpoints.append({"threshold": threshold, "reference_count": 4*len(references), "estimate_count": 4*len(estimates),
                          "tp": len(matches), "fp": 4*len(estimates)-len(matches), "fn": 4*len(references)-len(matches), "matches": matches})
    return {"candidate_count": len(estimates), "pair_iou": pairs, "typed_endpoints": endpoints}


def score(bank_path, bank_hash, seal_path, seal_hash, output, authorization):
    bank_path, seal_path = artifact_path(bank_path, existing=True), artifact_path(seal_path, existing=True)
    bank, seal = strict_read(bank_path, bank_hash), strict_read(seal_path, seal_hash)
    require(bank.get("suite") == seal.get("suite") == SUITE and seal.get("bank_sha256") == bank_hash
            and seal.get("status") == "all_predictions_sealed_truth_unopened" and len(seal["predictions"]) == len(bank["cases"]) == 12,
            "global_complete_prediction_seal_required")
    require([(row["seed"], row["cohort"]) for row in bank["cases"]] == [(seed, cohort) for seed in SEEDS for cohort in COHORTS], "fixed_score_cases")
    # Read and verify ALL predictions before opening ANY truth.
    predictions = [strict_read(artifact_path(seal_path.parent/row["path"], existing=True), row["sha256"]) for row in seal["predictions"]]
    for case, row, prediction in zip(bank["cases"], seal["predictions"], predictions):
        require(case["source"]["sha256"] == row["source_sha256"] == prediction["source_sha256"], "prediction_source_binding")
        require(digest(artifact_path(bank_path.parent/case["source"]["path"], existing=True)) == prediction["source_sha256"], "score_source_changed")
        require(set(prediction["arms"]) == set(ARMS) and prediction["discovery_truth_input"] is False, "prediction_contract")
    results = []
    for case, prediction in zip(bank["cases"], predictions):
        truth = strict_read(artifact_path(bank_path.parent/case["truth"]["path"], existing=True), case["truth"]["sha256"])
        require(truth["source_sha256"] == prediction["source_sha256"] and truth["ground_truth_scope"] == "generator_only_not_musician", "truth_binding")
        results.append({"id": case["id"], "seed": case["seed"], "cohort": case["cohort"], "reference_pair_count": len(truth["recurrence_pairs"]),
                        "scores": {arm: score_rows(truth["recurrence_pairs"], prediction["arms"][arm]) for arm in ARMS}})
    aggregate = {}
    for arm in ARMS:
        selected = [row["scores"][arm] for row in results]
        pairs, endpoints = [], []
        for index, threshold in enumerate((.5, .75)):
            rows = [row["pair_iou"][index] for row in selected]
            totals = {key: sum(row[key] for row in rows) for key in ("reference_count", "estimate_count", "tp", "fp", "fn", "endpoint_count")}
            offsets = [v for row in rows for v in row["endpoint_offset_seconds"]]
            totals.update(threshold=threshold, recall=totals["tp"]/totals["reference_count"] if totals["reference_count"] else None,
                          matched_endpoint_mae_seconds=sum(abs(v) for v in offsets)/len(offsets) if offsets else None)
            pairs.append(totals)
        for index, threshold in enumerate((.02, .05, .1)):
            rows = [row["typed_endpoints"][index] for row in selected]
            endpoints.append({"threshold": threshold, **{key: sum(row[key] for row in rows) for key in ("reference_count", "estimate_count", "tp", "fp", "fn")}})
        aggregate[arm] = {"pair_iou": pairs, "typed_endpoints": endpoints,
                          "negative_false_candidates": {cohort: sum(row["scores"][arm]["candidate_count"] for row in results if row["cohort"] == cohort and row["reference_pair_count"] == 0)
                                                        for cohort in COHORTS[:4]}}
    verify_pins()
    require(digest(bank_path) == bank_hash and digest(seal_path) == seal_hash and digest(__file__) == authorization["worker_sha256"], "scoring_bindings_changed")
    for row in seal["predictions"]:
        require(digest(seal_path.parent/row["path"]) == row["sha256"], "prediction_changed_after_scoring")
    write_new(output, {"schema_version": 1, "suite": SUITE, "status": "generated_research_scored",
              "cases": results, "aggregate": aggregate, "authorization": authorization,
              "bank_sha256": bank_hash, "seal_sha256": seal_hash, "truth_read_after_global_seal": True,
              "settings_retuned": False, "canonical_defaults_activated": False,
              "musical_performance_graded": False, "listening_accepted": False})
    return Path(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    registration = sub.add_parser("preregister")
    registration.add_argument("output")
    internal = sub.add_parser("_source", help=argparse.SUPPRESS)
    internal.add_argument("source")
    internal.add_argument("source_sha256")
    internal.add_argument("output")
    internal.add_argument("worker_sha256")
    for name in ("generate", "discover", "score"):
        command = sub.add_parser(name)
        command.add_argument("--plan", required=True)
        command.add_argument("--plan-sha256", required=True)
        command.add_argument("--release", required=True)
        command.add_argument("--release-sha256", required=True)
        if name in ("discover", "score"):
            command.add_argument("--bank", required=True)
            command.add_argument("--bank-sha256", required=True)
        if name == "score":
            command.add_argument("--seal", required=True)
            command.add_argument("--seal-sha256", required=True)
        command.add_argument("output")
    args = parser.parse_args()
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
        try:
            threads = int(os.environ.get(key, "2"))
        except ValueError:
            threads = 2
        os.environ[key] = str(max(1, min(2, threads)))
    if args.command == "preregister":
        write_new(args.output, metadata())
        return 0
    if args.command == "_source":
        require(digest(__file__) == args.worker_sha256, "opaque_worker_changed")
        verify_pins()
        require(digest(FFMPEG_PIN["path"]) == FFMPEG_PIN["sha256"], "qualified_ffmpeg_changed")
        started = time.monotonic()
        prediction = discover_source(args.source, args.source_sha256)
        prediction["elapsed_seconds"] = time.monotonic()-started
        deadline(started, started)
        write_new(args.output, prediction)
        return 0
    authorization = authorize(args.plan, args.plan_sha256, args.release, args.release_sha256, args.command)
    if args.command == "generate":
        result = generate(args.output, authorization)
    elif args.command == "discover":
        result = discover(args.bank, args.bank_sha256, args.output, authorization)
    else:
        result = score(args.bank, args.bank_sha256, args.seal, args.seal_sha256, args.output, authorization)
    print(json.dumps({"path": str(result), "sha256": digest(result), "status": "completed"}), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as exc:
        print(f"S1 phrase research: {exc}", file=sys.stderr)
        raise SystemExit(1)
