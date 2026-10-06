#!/usr/bin/env python3
"""S2 continuous-riff phrase-proposal research and V2 holdout-bank wrapper.

Preregistered generated benchmark (PHRASES_S2 section 5): frozen S1 baseline,
S1 support treatment and one new contiguous lag arm, fresh held-out seeds,
predictions globally sealed before any truth is opened. Generated-only scope;
no product default, profile, master or catalog change; no musical grading.
"""
from __future__ import annotations

import argparse
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
REPO = ROOT
LANE_AREA = ROOT / "artifacts" / "s2" / "phrase_anchor_riff"
SUITE = "s2-riff-1511-1613-v1"
SEEDS = (1511, 1613)
DEV_SEED = 1009
CONSUMED_SEEDS = (211, 307, 617, 719, 1301, 1423)
COHORTS = ("b2b-picked", "syncopated-palm-mute", "legato-transition", "tapping-run",
           "sweep-arpeggio", "aba-transition", "through-composed", "sustain32-fan-click")
POSITIVE_COHORTS = COHORTS[:6]
NEGATIVE_COHORTS = COHORTS[6:]
ARMS = ("Araw", "S1_support", "R1_lag")
DISCARDED_S1_ARMS = ("S2_multiscale",)
NAMESPACES = ("motif", "fill", "nuisance")
COMPONENTS = ("clean", "fan", "noise", "click", "mix")
RATE = 48000
NATIVE_SAMPLES = 8 * RATE
OPEN_STRINGS_MIDI = (24, 29, 34, 39, 46, 51, 56, 60, 65)
PREREG_RECEIPT = "docs/agent-notes/sprints/20261006-s2/phrase_anchor_riff-preregistration.json"
DEV_RECEIPT = "docs/agent-notes/sprints/20261006-s2/phrase_anchor_riff-dev-calibration.json"
# Set once from the committed development receipt (seed 1009 only); None refuses preregistration.
R1_THETA = .75
DEV_RECEIPT_SHA256 = "10d9bd69df2a965f788b3c3d31fac449f748589e53b01a980e0dac899084e33e"
S1_WORKER = "scripts/phrase_proposal_s1.py"
S1_WORKER_SHA256 = "38b736543a83d5c706a8803014f4e308685eee2c84275e9e6768c431b6b8d0e3"
PINS = {
    "scripts/guitar_features.py": "2ed031e8000cbcda92b504db10c98de03f456c90573cbff815cbb940c9ac86fe",
    "scripts/rhythm.py": "264b723ca29e4731da0a12d5dce221e7826a38b67f848ce9f4ffcf8bfe4b35b9",
    "scripts/phrase_evaluate.py": "3e503de277b2fd233fe802595a09a655c89669b0eb820f228e677c1b94b828a5",
    "docs/agent-notes/2026-10-05-phrase-guarded-arms.py": "78ca89de9cea327cc4ec1096a83522781a08bc161819699b69797ca273e2fb6c",
    "program/instrument.json": "bd381207d6615814ebee694148357c00719739ec900aa69c96d71b20779707b0",
    S1_WORKER: S1_WORKER_SHA256,
}
# Root-vendored byte-identical frozen copies (main 8483cc8). PINS keys stay the recorded
# logical names so sealed release bindings (dependency_sha256 == PINS) still compare equal;
# the frozen copy is used when present, and either file must hash to the pinned value.
FROZEN = {"scripts/rhythm.py": "scripts/frozen/rhythm_264b723c.py"}
# Root routing patch 8483cc8 to the S1 worker (TIN-5599). Only these exact (pinned, routed)
# substitutions are accepted: reversing each once must reproduce S1_WORKER_SHA256 bytes.
S1_ROUTING_PATCH = {
    "commit": "8483cc85767f5aa8c1d65c13f2c8c6c914291778",
    "sha256": "85a2ba1d68534ed4adde6363cb246c5db3fa50da1bcce9f461ee656652091e37",
    "substitutions": (
        ("}\nSETTINGS = {\n",
         "}\n# Byte-identical frozen copies; PINS keys stay the recorded logical names (sealed receipts compare PINS).\n"
         'FROZEN = {"scripts/rhythm.py": "scripts/frozen/rhythm_264b723c.py"}\nSETTINGS = {\n'),
        ("require(digest(ROOT / path) == expected, ",
         "require(digest(ROOT / FROZEN.get(path, path)) == expected, "),
        ('load_module(ROOT/"scripts/rhythm.py", "s1_frozen_rhythm")',
         'load_module(ROOT/FROZEN["scripts/rhythm.py"], "s1_frozen_rhythm")'),
    ),
}
FFMPEG_PIN = {"path": "/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffmpeg",
              "sha256": "3a315207e67de78e48c3bbb6b3346663f6a27c02e034d65ac72a12fee74c534a"}
ANALYSIS_PYTHON_DEFAULT = "/Users/jess/git/video-utils/.venv/bin/python"
BUDGETS = {"overall_seconds": 900, "case_seconds": 120, "ffmpeg_seconds": 20, "threads": 2,
           "json_bytes": 2_000_000, "wav_bytes": 1_000_000, "native_seconds": 8, "native_rate": RATE,
           "analysis_rate": 16000, "dev_run_seconds": 300, "dev_runs_maximum": 3,
           "v2_internal_seconds": 600, "v2_external_seconds": 660}
GEOMETRY_BOUNDS = {"gap_seconds": [0., .10], "motif_seconds": [1.40, 1.90], "start_seconds": [.9, 2.4],
                   "aba_motif_seconds": [1.30, 1.70], "aba_b_seconds": [1.00, 1.40], "aba_start_seconds": [.7, 1.3],
                   "occupancy_seconds": [.5, 7.5], "midi_range": [24, 77], "fret_offsets": [0, 12]}
R1_SETTINGS = {"band_maximum_hz": 1800., "log_floor": 1e-10, "zscore_std_floor": 1e-6,
               "lag_seconds": [.8, 4.5], "length_seconds": [.8, 2.4], "length_not_above_lag": True,
               "theta_candidates": [.55, .65, .75], "duplicate_both_span_iou": .75, "proposal_cap": 10,
               "span_seconds": [.5, 4.], "frame_hop_seconds": 256 / 16000,
               "maximal_extension": "per (t, lag): largest window length with mean diagonal similarity >= theta",
               "ranking": "excess = sum over window of (similarity - theta) descending; ties: longer, earlier t, shorter lag",
               "features": "phrase_proposal_s1.extract log-band powers, bands <= 1800 Hz, per-band z-score over clip, frame cosine",
               "quiet_gap_grouping": False}
SILENCE_RULE = {"frame_seconds": .02, "threshold_dbfs": -40., "endpoint_window_seconds": .25,
                "component": "clean_pcm16",
                "rule": "longest sub-threshold run within +-0.25 s of every truth endpoint <= longest run inside motif interiors"}
V2_GENERATOR = "scripts/benchmark_holdout.py"
V2_GENERATOR_SHA256 = "051d8689364564513c34a1ab00a2c23560407e474da12c2bf25e7513dbc81709"
V2_GENERATOR_COMMIT = "f180572b8b51bd408debd55d661e670269d23b8f"
V2_PLAN_SHA256 = "495ad2f3f553b0bd7030ac797b6e8589f37748df657219c075d0fc4ce7491e74"
V2_LICENCE = "pending operator confirmation (repository MIT; proposed CC BY 4.0 for cross-repo use)"
V2_TRAINING_STATEMENT = "training use of this bank voids video-utils held-out evaluation on it"
V2_RESERVED_SEEDS = [2101, 2199]
RELEASE_ACTORS = ("root", "root_workflow")
CLAIMS = {"continuous_riff_accuracy_scope": "generated_only", "real_take_accuracy": "unknown",
          "musical_phrase_identity": "unknown", "physical_articulation_accepted": False,
          "default_adoption": False, "settings_retuned": False, "musical_performance_graded": False,
          "listening_accepted": False, "candidate_confidence": None}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def normalized(value):
    return json.loads(json.dumps(value, allow_nan=False))


def artifact_path(path, existing=False):
    path = Path(path)
    require(".." not in path.parts, "path_traversal")
    if not path.is_absolute():
        path = ROOT / path
    area = LANE_AREA
    require(path.is_relative_to(area) and path != area, "lane_artifacts_required")
    current = area
    require(not area.is_symlink(), "symlink_path")
    for part in path.relative_to(area).parts:
        current = current / part
        require(not current.is_symlink(), "symlink_path")
    if existing:
        require(path.is_file() and not path.is_symlink(), "regular_artifact_required")
    return path


def write_new(path, value):
    path = artifact_path(path)
    raw = encoded(value)
    require(len(raw) <= BUDGETS["json_bytes"], "json_byte_bound")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("xb") as handle:
        handle.write(raw)
    path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


def _unique(pairs):
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
        after = os.fstat(fd)
        require(len(raw) == before.st_size and (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
                "json_changed")
    finally:
        os.close(fd)
    if expected is not None:
        require(hashlib.sha256(raw).hexdigest() == expected, "json_sha256_mismatch")

    def constant(_):
        raise ValueError("nonfinite_json")

    def finite_float(text):
        result = float(text)
        require(math.isfinite(result), "nonfinite_json_float")
        return result

    return json.loads(raw, object_pairs_hook=_unique, parse_constant=constant, parse_float=finite_float)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pinned_file(path):
    """On-disk file carrying the pinned bytes of a logical PINS path (frozen copy when vendored)."""
    frozen = FROZEN.get(path)
    return ROOT / frozen if frozen and (ROOT / frozen).is_file() else ROOT / path


def s1_worker_identity():
    """'pinned' for the exact S1 bytes, or 'root_routing_8483cc8' when only the recorded routing differs."""
    raw = (ROOT / S1_WORKER).read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual == S1_WORKER_SHA256:
        return "pinned"
    require(actual == S1_ROUTING_PATCH["sha256"], "pinned_source_changed:" + S1_WORKER)
    text = raw.decode("utf-8")
    for pinned, routed in S1_ROUTING_PATCH["substitutions"]:
        require(text.count(routed) == 1, "pinned_source_changed:" + S1_WORKER)
        text = text.replace(routed, pinned)
    require(hashlib.sha256(text.encode("utf-8")).hexdigest() == S1_WORKER_SHA256, "pinned_source_changed:" + S1_WORKER)
    require((ROOT / FROZEN["scripts/rhythm.py"]).is_file(), "pinned_source_changed:scripts/rhythm.py")
    return "root_routing_8483cc8"


def verify_pins():
    for path, expected in PINS.items():
        if path == S1_WORKER:
            s1_worker_identity()
        else:
            require(digest(pinned_file(path)) == expected, "pinned_source_changed:" + path)


def s1_module():
    s1_worker_identity()
    return load_module(ROOT / S1_WORKER, "s2_frozen_phrase_proposal_s1")


# ------------------------------------------------------------ geometry ----

def unit(seed, namespace, knob):
    require(namespace in NAMESPACES, "unregistered_namespace")
    return int.from_bytes(hashlib.sha256(f"{SUITE}:{seed}:{namespace}:{knob}".encode()).digest()[:8], "big") / 2**64


class Draw:
    """Deterministic named draws; every value derives from sha256(suite:seed:namespace:knob)."""

    def __init__(self, seed, namespace, prefix):
        self.seed, self.namespace, self.prefix = seed, namespace, prefix

    def u(self, name):
        return unit(self.seed, self.namespace, f"{self.prefix}:{name}")

    def uniform(self, name, low, high):
        return low + (high - low) * self.u(name)

    def integer(self, name, low, high):
        return low + min(high - low, int(self.u(name) * (high - low + 1)))

    def choice(self, name, values):
        return values[self.integer(name, 0, len(values) - 1)]

    def child(self, prefix):
        return Draw(self.seed, self.namespace, f"{self.prefix}:{prefix}")


def seconds_to_samples(value):
    return int(round(value * RATE))


def pitch(draw, name, low, high):
    return draw.integer(name, low, high)


def differs_enough(sequence, motif):
    """Fill/B differs from A in at least half of compared note positions (start- and end-aligned)."""
    count = min(len(sequence), len(motif))
    if count == 0:
        return True
    start = sum(a != b for a, b in zip(sequence[:count], motif[:count]))
    end = sum(a != b for a, b in zip(sequence[-count:], motif[-count:]))
    return 2 * start >= count and 2 * end >= count


def step_motif(draw, length, steps_options, include_probability, low, high, articulation, *, palm_rest=False):
    count = draw.choice("steps", steps_options)
    included = [0] + [k for k in range(1, count) if draw.u(f"include{k}") < include_probability(k)]
    if palm_rest:
        anchor = draw.integer("rest_anchor", 1, count - 5)
        included = sorted(set(k for k in included if not anchor < k < anchor + 4) | {0, anchor} |
                          ({anchor + 4} if anchor + 4 < count else set()))
    onsets = [int(round(k * length / count)) for k in included]
    notes = [[onset, pitch(draw, f"pitch{i}", low, high), articulation, None] for i, onset in enumerate(onsets)]
    iois = [b - a for a, b in zip(onsets, onsets[1:] + [length])]
    return notes, iois, count


def legato_motif(draw, length, low, high):
    count = draw.choice("steps", (8, 10, 12))
    included = [0] + [k for k in range(1, count) if draw.u(f"include{k}") < .85]
    onsets = [int(round(k * length / count)) for k in included]
    current, notes = draw.integer("start_pitch", low, high), []
    for i, onset in enumerate(onsets):
        if i:
            current = min(high, max(low, current + draw.choice(f"step{i}", (-3, -2, -1, 1, 2, 3))))
        notes.append([onset, current, "legato", None])
    iois = [b - a for a, b in zip(onsets, onsets[1:] + [length])]
    return notes, iois, count


TAP_SHAPES = (0, 3, 5, 7, 8, 10, 12, 15)


def tap_motif(draw, length):
    step = draw.uniform("step_seconds", .07, .11)
    count = max(8, int(round(length / seconds_to_samples(step))))
    base = draw.integer("base", 51, 62)
    shape = sorted({0} | {draw.choice(f"shape{i}", TAP_SHAPES) for i in range(3)})
    notes = []
    for k in range(count):
        onset = int(round(k * length / count))
        notes.append([onset, base + draw.choice(f"tone{k}", shape), "tap", round(draw.uniform(f"attack{k}", .002, .004), 6)])
    iois = [b[0] - a[0] for a, b in zip(notes, notes[1:])] + [length - notes[-1][0]]
    return notes, iois, count


SWEEP_CHORDS = {"minor": (0, 3, 7, 12, 15, 19, 24, 27, 31), "major": (0, 4, 7, 12, 16, 19, 24, 28, 31)}


def sweep_phrase(draw, length):
    """Repeated 6-9 note sweeps (25-45 ms per note, up/down) each followed by a held top/bottom note."""
    notes, cursor, index = [], 0, 0
    while cursor < length:
        sweep = draw.child(f"sweep{index}")
        count = sweep.integer("count", 6, 9)
        root = sweep.integer("root", 34, 41)
        tones = [root + interval for interval in SWEEP_CHORDS[sweep.choice("quality", ("minor", "major"))][:count]]
        if sweep.u("direction") < .5:
            tones.reverse()
        for i, tone in enumerate(tones):
            if cursor >= length:
                break
            notes.append([cursor, tone, "sweep", None])
            cursor += seconds_to_samples(sweep.uniform(f"ioi{i}", .025, .045))
        cursor += seconds_to_samples(sweep.uniform("hold", .15, .35))
        index += 1
    return notes


def forward_fill(draw, start, end, iois, make_pitch, articulation, motif_pitches, attack=None):
    """Fill [start, end) with notes whose inter-onset intervals are drawn from the supplied pool."""
    for attempt in range(64):
        trial = draw.child(f"attempt{attempt}")
        notes, cursor, index = [], start, 0
        while cursor < end:
            notes.append([cursor, make_pitch(trial, index), articulation,
                          None if attack is None else round(trial.uniform(f"attack{index}", *attack), 6)])
            cursor += trial.choice(f"ioi{index}", iois)
            index += 1
        if differs_enough([row[1] for row in notes], motif_pitches):
            return notes
    raise ValueError("fill_distinctness_unsatisfied")


def legato_pitch_maker(low, high):
    """Stepwise legato walk; state resets at index 0 of every fill attempt."""
    state = {}

    def make(trial, index):
        if index == 0:
            state["current"] = trial.integer("start_pitch", low, high)
        else:
            state["current"] = min(high, max(low, state["current"] + trial.choice(f"step{index}", (-3, -2, -1, 1, 2, 3))))
        return state["current"]
    return make


def through_composed(draw, start, end):
    step = seconds_to_samples(draw.uniform("step_seconds", .12, .20))
    notes, cursor, index, seen = [], start, 0, set()
    while cursor < end:
        for attempt in range(16):
            candidate = pitch(draw, f"pitch{index}:{attempt}", 24, 58)
            gram = tuple([row[1] for row in notes[-3:]] + [candidate])
            if len(gram) < 4 or gram not in seen:
                break
        if len(gram) == 4:
            require(gram not in seen, "through_composed_repeat_unavoidable")
            seen.add(gram)
        notes.append([cursor, candidate, "picked", None])
        cursor += step * draw.choice(f"ioi{index}", (1, 1, 2, 1, 3))
        index += 1
    return notes


LINK_REGISTERS = {"picked": (24, 46), "palm": (24, 36), "legato": (34, 58), "tap": (51, 77), "sweep": (34, 72)}


def place(notes, offset):
    return [[row[0] + offset, row[1], row[2], row[3]] for row in notes]


def geometry(seed, cohort):
    """Pure-Python, deterministic per-case geometry; truth spans native-sample rounded before synthesis."""
    require(cohort in COHORTS, "registered_cohort_required")
    motif = Draw(seed, "motif", cohort)
    fill = Draw(seed, "fill", cohort)
    occupancy = [seconds_to_samples(.5), seconds_to_samples(7.5)]
    segments, notes, pairs, gaps, checks = [], [], [], [], {}
    if cohort in NEGATIVE_COHORTS:
        if cohort == "through-composed":
            notes = through_composed(fill.child("through"), *occupancy)
            segments.append({"role": "through_composed", "start_sample": occupancy[0], "end_sample": occupancy[1]})
        else:
            notes = [[occupancy[0], 24, "sustain", None]]
            segments.append({"role": "sustain_c1", "start_sample": occupancy[0], "end_sample": occupancy[1]})
        return {"seed": seed, "cohort": cohort, "role": "negative_no_generated_recurrence_reference",
                "occupancy_samples": occupancy, "segments": segments, "notes": notes, "truth_pairs": [],
                "gap_samples": [], "checks": {"fill_distinct": None, "gap_bound": None}}
    aba = cohort == "aba-transition"
    bounds = GEOMETRY_BOUNDS
    length = seconds_to_samples(motif.uniform("length", *(bounds["aba_motif_seconds"] if aba else bounds["motif_seconds"])))
    start = seconds_to_samples(motif.uniform("start", *(bounds["aba_start_seconds"] if aba else bounds["start_seconds"])))
    gap = seconds_to_samples(motif.uniform("gap", *bounds["gap_seconds"]))
    a_draw = motif.child("A")
    attack = None
    if cohort in ("b2b-picked", "aba-transition"):
        a_notes, iois, _ = step_motif(a_draw, length, (12, 14, 16), lambda k: .6, 24, 46, "picked")
        maker, articulation, fill_iois = (lambda t, i: pitch(t, f"pitch{i}", 24, 46)), "picked", iois
    elif cohort == "syncopated-palm-mute":
        a_notes, iois, count = step_motif(a_draw, length, (12, 15, 18), lambda k: .75 if k % 3 else .3, 24, 36, "palm",
                                          palm_rest=True)
        step = length / count
        fill_iois = [v for v in iois if v <= 3 * step + 1] or [int(round(step))]
        maker, articulation = (lambda t, i: pitch(t, f"pitch{i}", 24, 36)), "palm"
    elif cohort == "legato-transition":
        a_notes, iois, _ = legato_motif(a_draw, length, 34, 58)
        maker, articulation, fill_iois = legato_pitch_maker(34, 58), "legato", iois
    elif cohort == "tapping-run":
        a_notes, iois, _ = tap_motif(a_draw, length)
        maker, articulation, fill_iois, attack = (lambda t, i: pitch(t, f"pitch{i}", 51, 77)), "tap", iois, (.002, .004)
    else:
        a_notes = sweep_phrase(a_draw, length)
        iois = None
    a_pitches = [row[1] for row in a_notes]
    first = start
    if aba:
        b_length = seconds_to_samples(motif.uniform("b_length", *bounds["aba_b_seconds"]))
        gap2 = seconds_to_samples(motif.uniform("gap2", *bounds["gap_seconds"]))
        for attempt in range(64):
            b_notes, _, _ = step_motif(motif.child(f"B{attempt}"), b_length, (12, 14, 16), lambda k: .6, 24, 46, "picked")
            if differs_enough([row[1] for row in b_notes], a_pitches):
                break
        else:
            raise ValueError("b_distinctness_unsatisfied")
        b_start = first + length + gap
        second = b_start + b_length + gap2
        layout = [("fill_x", occupancy[0], first), ("motif_a1", first, first + length), ("link1", first + length, b_start),
                  ("motif_b", b_start, b_start + b_length), ("link2", b_start + b_length, second),
                  ("motif_a2", second, second + length), ("fill_y", second + length, occupancy[1])]
        gaps = [gap, gap2]
        checks["b_distinct"] = differs_enough([row[1] for row in b_notes], a_pitches)
    else:
        second = first + length + gap
        layout = [("fill_x", occupancy[0], first), ("motif_a1", first, first + length), ("link1", first + length, second),
                  ("motif_a2", second, second + length), ("fill_y", second + length, occupancy[1])]
        gaps = [gap]
    distinct = []
    for role, begin, end in layout:
        segments.append({"role": role, "start_sample": begin, "end_sample": end})
        if end <= begin:
            continue
        if role in ("motif_a1", "motif_a2"):
            notes.extend(place(a_notes, begin))
        elif role == "motif_b":
            notes.extend(place(b_notes, begin))
        elif role.startswith("link"):
            link_art = "picked" if aba else (articulation if iois is not None else "sweep")
            low, high = LINK_REGISTERS[link_art]
            choices = [m for m in range(low, high + 1) if m not in (a_pitches[0], a_pitches[-1])]
            notes.append([begin, fill.child(role).choice("pitch", choices), link_art, None if link_art != "tap" else .003])
        else:
            if iois is None:
                for attempt in range(64):
                    filled = place(sweep_phrase(fill.child(f"{role}:{attempt}"), end - begin), begin)
                    if differs_enough([row[1] for row in filled], a_pitches):
                        break
                else:
                    raise ValueError("fill_distinctness_unsatisfied")
            else:
                filled = forward_fill(fill.child(role), begin, end, fill_iois, maker, articulation, a_pitches, attack)
            distinct.append(differs_enough([row[1] for row in filled], a_pitches))
            notes.extend(filled)
    notes.sort(key=lambda row: row[0])
    pairs.append({"id": f"seed{seed}-{cohort}", "first_span_samples": [first, first + length],
                  "second_span_samples": [second, second + length],
                  "first_span_seconds": [first / RATE, (first + length) / RATE],
                  "second_span_seconds": [second / RATE, (second + length) / RATE]})
    checks.update(fill_distinct=all(distinct), gap_bound=all(0 <= g <= seconds_to_samples(.10) for g in gaps))
    if cohort == "syncopated-palm-mute":
        checks["palm_fill_ioi_below_motif_rest"] = max(fill_iois) < max(iois)
    return {"seed": seed, "cohort": cohort, "role": "positive_one_recurrence_pair", "occupancy_samples": occupancy,
            "motif_samples": length, "start_samples": start, "gap_samples": gaps, "segments": segments,
            "notes": notes, "truth_pairs": pairs, "checks": checks}


def validate_geometry(item):
    """Structural geometry checks; failures are construction failures, not quality metrics."""
    bounds = GEOMETRY_BOUNDS
    for row in item["notes"]:
        require(bounds["midi_range"][0] <= row[1] <= bounds["midi_range"][1], "midi_out_of_range")
        require(item["occupancy_samples"][0] <= row[0] < item["occupancy_samples"][1], "note_outside_occupancy")
    if item["truth_pairs"]:
        aba = item["cohort"] == "aba-transition"
        length = item["motif_samples"] / RATE
        low, high = bounds["aba_motif_seconds"] if aba else bounds["motif_seconds"]
        require(low - 1e-4 <= length <= high + 1e-4, "motif_length_out_of_range")
        start = item["start_samples"] / RATE
        low, high = bounds["aba_start_seconds"] if aba else bounds["start_seconds"]
        require(low - 1e-4 <= start <= high + 1e-4, "start_out_of_range")
        require(all(0 <= g / RATE <= .10 + 1e-9 for g in item["gap_samples"]), "gap_above_100ms")
        pair = item["truth_pairs"][0]
        require(pair["second_span_samples"][1] <= item["occupancy_samples"][1], "motif_outside_occupancy")
        require(all(value is not False for value in item["checks"].values()), "geometry_check_failed")
    return True


def all_geometry(seeds):
    return {str(seed): {cohort: geometry(seed, cohort) for cohort in COHORTS} for seed in seeds}


def scoring_definition():
    return {"pair_iou_thresholds": [.5, .75], "typed_endpoint_tolerances_seconds": [.02, .05, .1],
            "matching": "phrase_proposal_s1.score_rows: maximum cardinality then maximum mean two-span IoU",
            "reference_totals": {"positive_pairs": 12, "typed_endpoints": 48, "negative_cases": 4},
            "matched_endpoint_mae": "all four endpoints of matched pairs; denominator 4 x matched pairs; null if none",
            "common_reference_mae": "references matched by all three arms at IoU 0.5; denominator 4 x common; null with reason if empty",
            "per_positive_cohort_tp": "over 2 references each", "negative_false_candidates": "candidate count per negative cohort over 2 cases",
            "aggregation": "sums, never averages of rates; abstentions stay in denominators"}


def metadata():
    require(R1_THETA in R1_SETTINGS["theta_candidates"] and DEV_RECEIPT_SHA256 is not None, "theta_not_calibrated")
    s1 = s1_module()
    value = {"schema_version": 1, "suite": SUITE, "seeds": list(SEEDS), "dev_seed": DEV_SEED,
             "consumed_seeds_excluded": list(CONSUMED_SEEDS), "cohorts": list(COHORTS),
             "positive_cohorts": list(POSITIVE_COHORTS), "negative_cohorts": list(NEGATIVE_COHORTS),
             "case_count": 16, "audio_seconds": 128, "native_rate": RATE, "channels": 1, "sample_format": "pcm16",
             "components": list(COMPONENTS), "geometry_bounds": GEOMETRY_BOUNDS, "silence_cue_rule": SILENCE_RULE,
             "generator_geometry": all_geometry(SEEDS),
             "arms": {"Araw": "phrase_proposal_s1.discover_source Araw, unchanged frozen S1 baseline",
                      "S1_support": "phrase_proposal_s1.discover_source S1_support, settings unchanged",
                      "R1_lag": "contiguous lag-matrix recurrence on S1 log-band powers"},
             "discarded_before_sealing": list(DISCARDED_S1_ARMS),
             "s1_settings": s1.SETTINGS, "r1_settings": dict(R1_SETTINGS, theta=R1_THETA),
             "dev_calibration": {"receipt": DEV_RECEIPT, "receipt_sha256": DEV_RECEIPT_SHA256, "seed": DEV_SEED,
                                 "rule": "maximize dev TP@IoU0.5 minus dev negative false candidates; ties -> larger theta",
                                 "reported_as_heldout": False},
             "budgets": BUDGETS, "dependency_sha256": PINS, "ffmpeg": FFMPEG_PIN,
             "analysis_python": {"path": ANALYSIS_PYTHON_DEFAULT, "numpy": "2.5.3", "librosa": "0.11.0",
                                 "env": "VIDEO_UTILS_ANALYSIS_PYTHON"},
             "scoring": scoring_definition(),
             "discovery_truth_input": False, "predictions_global_seal_before_truth_read": True,
             "retune_after_heldout": False, "canonical_defaults_activated": False,
             **{key: value for key, value in CLAIMS.items() if key != "candidate_confidence"}}
    return normalized(value)


# ------------------------------------------------------------ synthesis ----

def nuisance(seed, t):
    """S1 nuisance formulas under the S2 namespace (fan, noise, ordered and periodic clicks)."""
    import numpy as np
    count = len(t)
    phase = 2 * math.pi * unit(seed, "nuisance", "phase")
    fan = (.775 + .225 * np.sin(2 * math.pi * .61 * t + phase)) * (.009 * np.sin(2 * math.pi * 47 * t + phase)
                                                                   + .006 * np.sin(2 * math.pi * 71 * t + phase))
    rng = np.random.default_rng(int(unit(seed, "nuisance", "rng") * 2**63))
    noise = .006 * (.8 + .2 * np.sin(2 * math.pi * .43 * t + phase)) * rng.uniform(-1, 1, count)
    click = np.zeros(count)
    period = .337 + .056 * unit(seed, "nuisance", "period")
    origin = .101 + .066 * unit(seed, "nuisance", "origin")
    events = [(origin + i * period, 3500., .033) for i in range(24) if origin + i * period < 8]
    for start in (.30 + .15 * unit(seed, "nuisance", "ordered1"), 4.6 + .25 * unit(seed, "nuisance", "ordered2")):
        events.extend((start + offset, hz, amp) for offset, hz, amp in zip(
            [0., .173, .367, .581, .809, 1.013, 1.227, 1.451],
            [2200., 5100., 1600., 3700., 5100., 2200., 3700., 1600.],
            [.058, .083, .047, .071, .061, .089, .053, .076]))
    for start, hz, amp in events:
        mask = (t >= start) & (t < start + .012)
        age = t[mask] - start
        click[mask] += amp * np.exp(-age / .0024) * np.sin(2 * math.pi * hz * age)
    return fan, noise, click, {"click_period_seconds": period, "click_origin_seconds": origin}


def hz(midi):
    return 440. * 2 ** ((midi - 69) / 12)


def render_clean(item):
    """Tanh-distorted note synthesis (S1 shape); ~32.7 Hz content is never filtered."""
    import numpy as np
    clean = np.zeros(NATIVE_SAMPLES)
    notes = item["notes"]
    end_occ = item["occupancy_samples"][1]
    ends = [row[0] for row in notes[1:]] + [end_occ]
    release = 96
    index = 0
    while index < len(notes):
        onset, midi, articulation, attack = notes[index]
        if articulation == "legato":
            group = [index]
            while group[-1] + 1 < len(notes) and notes[group[-1] + 1][2] == "legato" and notes[group[-1] + 1][0] == ends[group[-1]]:
                group.append(group[-1] + 1)
            begin, stop = notes[group[0]][0], min(NATIVE_SAMPLES, ends[group[-1]] + release)
            frequency = np.zeros(stop - begin)
            amplitude = np.zeros(stop - begin)
            previous = hz(notes[group[0]][1])
            for g in group:
                a, b = notes[g][0] - begin, (ends[g] if g != group[-1] else stop) - begin
                age = np.arange(b - a) / RATE
                target = hz(notes[g][1])
                frequency[a:b] = previous * 2 ** (math.log2(target / previous) * np.minimum(1, age / .024))
                amplitude[a:b] = .75 + .25 * np.exp(-age / .08)
                previous = target
            radians = np.cumsum(2 * math.pi * frequency / RATE)
            age = np.arange(stop - begin) / RATE
            envelope = amplitude * np.minimum(1, age / .008)
            tail = np.arange(stop - begin) + begin - ends[group[-1]]
            envelope *= np.clip(1 - tail / release, 0, 1)
            clean[begin:stop] += .16 * envelope * np.tanh(2.2 * (np.sin(radians) + .5 * np.sin(2 * radians) + .25 * np.sin(3 * radians)))
            index = group[-1] + 1
            continue
        if articulation == "palm":
            stop = min(NATIVE_SAMPLES, onset + int(.055 * RATE))
        else:
            stop = min(NATIVE_SAMPLES, ends[index] + release)
        age = np.arange(stop - onset) / RATE
        radians = 2 * math.pi * hz(midi) * age
        if articulation == "palm":
            envelope = np.maximum(0, np.minimum(1, np.minimum(age / .0015, (.055 - age) / .004))) * np.exp(-age / .018)
        else:
            rise, decay = {"picked": (.0015, .6), "tap": (attack or .003, .35), "sweep": (.001, .3),
                           "sustain": (.005, 12.)}[articulation]
            envelope = np.minimum(1, age / rise) * np.exp(-age / decay)
            tail = np.arange(stop - onset) + onset - ends[index]
            envelope *= np.clip(1 - tail / release, 0, 1)
        clean[onset:stop] += .16 * envelope * np.tanh(2.2 * (np.sin(radians) + .5 * np.sin(2 * radians) + .25 * np.sin(3 * radians)))
        index += 1
    t = np.arange(NATIVE_SAMPLES) / RATE
    clean *= np.clip(np.minimum((t - .5) / .02, (7.5 - t) / .02), 0, 1)
    return clean


def pcm16(samples):
    import numpy as np
    return np.rint(np.asarray(samples) * 32768).astype("<i2").tobytes()


def subthreshold_runs(samples):
    """Per 20 ms frame: True when frame RMS < -40 dBFS."""
    import numpy as np
    frame = int(SILENCE_RULE["frame_seconds"] * RATE)
    count = len(samples) // frame
    frames = np.asarray(samples[:count * frame], dtype=float).reshape(count, frame)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    return rms < 10 ** (SILENCE_RULE["threshold_dbfs"] / 20), frame


def longest_run(mask, indices):
    best = current = 0
    previous = None
    for i in indices:
        if mask[i] and previous is not None and i == previous + 1 and current:
            current += 1
        elif mask[i]:
            current = 1
        else:
            current = 0
        previous = i
        best = max(best, current)
    return best


def silence_cue(clean_pcm, item):
    import numpy as np
    data = np.frombuffer(clean_pcm, dtype="<i2").astype(float) / 32768
    mask, frame = subthreshold_runs(data)
    centers = (np.arange(len(mask)) + .5) * frame / RATE
    pair = item["truth_pairs"][0] if item["truth_pairs"] else None
    if pair is None:
        occupancy = [i for i, c in enumerate(centers) if .52 <= c <= 7.48]
        return {"applicable": False, "longest_subthreshold_run_frames_in_occupancy": longest_run(mask, occupancy)}
    interior = []
    for span in (pair["first_span_samples"], pair["second_span_samples"]):
        interior.extend(i for i in range(len(mask)) if i * frame >= span[0] and (i + 1) * frame <= span[1])
    interior_max = longest_run(mask, sorted(set(interior)))
    endpoints = {}
    window = SILENCE_RULE["endpoint_window_seconds"]
    for key in ("first_span_samples", "second_span_samples"):
        for edge, sample in zip(("start", "end"), pair[key]):
            seconds = sample / RATE
            near = [i for i, c in enumerate(centers) if abs(c - seconds) <= window]
            endpoints[f"{key.split('_')[0]}_{edge}"] = longest_run(mask, near)
    return {"applicable": True, "interior_longest_run_frames": interior_max, "endpoint_longest_run_frames": endpoints,
            "passed": all(value <= interior_max for value in endpoints.values())}


def construct(seed, cohort):
    """Generator-only routine. Never called by source discovery."""
    require(seed in SEEDS or seed == DEV_SEED, "registered_seed_required")
    return _construct(seed, cohort)


def _construct(seed, cohort):
    import numpy as np
    item = geometry(seed, cohort)
    validate_geometry(item)
    t = np.arange(NATIVE_SAMPLES) / RATE
    fan, noise, click, nuisance_meta = nuisance(seed, t)
    clean = render_clean(item)
    mix = clean + fan + noise + click
    require(np.isfinite(mix).all() and float(np.max(np.abs(mix))) < .5, "generated_peak_bound")
    components = {"clean": clean, "fan": fan, "noise": noise, "click": click, "mix": mix}
    truth = {"schema_version": 1, "suite": SUITE, "seed": seed, "cohort": cohort, "duration_seconds": 8.,
             "recurrence_pairs": [{"id": row["id"], "first_span_seconds": row["first_span_seconds"],
                                   "second_span_seconds": row["second_span_seconds"]} for row in item["truth_pairs"]],
             "native_rate": RATE, "native_sample_count": NATIVE_SAMPLES,
             "ground_truth_scope": "generator_only_not_musician", "musical_performance_graded": False,
             "physical_articulation_accepted": False, "geometry": item, "nuisance": nuisance_meta,
             "peak_absolute_mix": float(np.max(np.abs(mix)))}
    return components, truth


# ------------------------------------------------------------ R1 arm ----

def interval_iou(a, b):
    return max(0., min(a[1], b[1]) - max(a[0], b[0])) / (max(a[1], b[1]) - min(a[0], b[0]))


def r1_lag(powers, centers, times, theta):
    """Contiguous lag-matrix recurrence; no quiet-gap grouping, no truth, BPM or geometry input."""
    import numpy as np
    require(theta in R1_SETTINGS["theta_candidates"], "registered_theta_required")
    x = np.asarray(powers, dtype=float)
    f = np.asarray(centers, dtype=float)
    require(x.ndim == 2 and x.shape[0] >= 4 and x.shape[1] == len(f) and np.isfinite(x).all() and np.all(x >= 0),
            "r1_feature_shape")
    z = np.log10(x[:, f <= R1_SETTINGS["band_maximum_hz"]] + R1_SETTINGS["log_floor"])
    z = (z - z.mean(axis=0)) / np.maximum(z.std(axis=0), R1_SETTINGS["zscore_std_floor"])
    norms = np.linalg.norm(z, axis=1)
    unitary = z / np.maximum(norms, 1e-12)[:, None]
    unitary[norms <= 1e-12] = 0
    similarity = unitary @ unitary.T
    hop = R1_SETTINGS["frame_hop_seconds"]
    n = len(similarity)
    lag_low, lag_high = math.ceil(R1_SETTINGS["lag_seconds"][0] / hop - 1e-9), math.floor(R1_SETTINGS["lag_seconds"][1] / hop + 1e-9)
    len_low, len_high = math.ceil(R1_SETTINGS["length_seconds"][0] / hop - 1e-9), math.floor(R1_SETTINGS["length_seconds"][1] / hop + 1e-9)
    candidates = []
    for lag in range(lag_low, min(lag_high, n - len_low) + 1):
        diagonal = np.diagonal(similarity, offset=lag)
        cumulative = np.concatenate(([0.], np.cumsum(diagonal)))
        best = np.zeros(len(diagonal), dtype=int)
        best_mean = np.zeros(len(diagonal))
        for length in range(len_low, min(len_high, lag, len(diagonal)) + 1):
            means = (cumulative[length:] - cumulative[:-length]) / length
            hit = means >= theta
            best[:len(means)][hit] = length
            best_mean[:len(means)][hit] = means[hit]
        for start in np.flatnonzero(best):
            length = int(best[start])
            mean = float(best_mean[start])
            candidates.append((-(length * (mean - theta)), -length, int(start), lag, mean))
    candidates.sort()
    retained = []
    for negative_excess, negative_length, start, lag, mean in candidates:
        length = -negative_length
        row = {"first_span_seconds": [start * hop, (start + length) * hop],
               "second_span_seconds": [(start + lag) * hop, (start + lag + length) * hop],
               "similarity": mean, "excess": -negative_excess, "lag_seconds": lag * hop,
               "confidence": None, "performance_issue_confirmed": False}
        span = row["first_span_seconds"][1] - row["first_span_seconds"][0]
        if not R1_SETTINGS["span_seconds"][0] <= span <= R1_SETTINGS["span_seconds"][1]:
            continue
        if any(all(interval_iou(row[key], other[key]) >= R1_SETTINGS["duplicate_both_span_iou"]
                   for key in ("first_span_seconds", "second_span_seconds")) for other in retained):
            continue
        retained.append(row)
        if len(retained) == R1_SETTINGS["proposal_cap"]:
            break
    return {"candidates": retained, "candidate_count_before_deduplication": len(candidates), "theta": theta,
            "frame_count": n, "proposal_cap_saturated": len(retained) == R1_SETTINGS["proposal_cap"],
            "musical_phrase_identity": "unknown", "truth_supplied": False}


def source_child(source, source_sha256, output, worker_sha256, mode):
    """Opaque per-source discovery. Accepts no truth, cohort, reference, BPM or geometry."""
    import numpy as np
    require(mode in ("heldout", "dev"), "registered_mode_required")
    require(digest(__file__) == worker_sha256, "opaque_worker_changed")
    verify_pins()
    require(digest(FFMPEG_PIN["path"]) == FFMPEG_PIN["sha256"], "qualified_ffmpeg_changed")
    started = time.monotonic()
    s1 = s1_module()
    source = artifact_path(source, existing=True)
    captured = []
    frozen_extract = s1.extract

    def capturing_extract(samples):
        # Reuse S1's own decoded PCM and log-band powers; S1 behaviour is unchanged.
        result = frozen_extract(samples)
        captured.append((np.array(samples, dtype="<f4", copy=True), result))
        return result

    s1.extract = capturing_extract
    try:
        base = s1.discover_source(source, source_sha256)
    finally:
        s1.extract = frozen_extract
    require(len(captured) == 1, "r1_feature_capture_failed")
    samples, (cache, powers, centers) = captured[0]
    pcm_hash = hashlib.sha256(np.asarray(samples, dtype="<f4").tobytes()).hexdigest()
    require(pcm_hash == base["analysis_pcm_sha256"], "r1_analysis_pcm_differs_from_s1")
    thetas = [R1_THETA] if mode == "heldout" else list(R1_SETTINGS["theta_candidates"])
    require(all(theta is not None for theta in thetas), "theta_not_calibrated")
    arms = {"Araw": base["arms"]["Araw"], "S1_support": base["arms"]["S1_support"]}
    diagnostics = {"S1_support": base["diagnostics"]["S1_support"]}
    for theta in thetas:
        name = "R1_lag" if mode == "heldout" else f"R1_lag@{theta:.2f}"
        result = r1_lag(powers, centers, cache["times"], theta)
        arms[name] = result.pop("candidates")
        diagnostics[name] = result
    require(digest(source) == source_sha256, "source_changed_during_discovery")
    return {"schema_version": 1, "suite": SUITE, "mode": mode, "source_sha256": source_sha256, "arms": arms,
            "discarded_before_sealing": list(DISCARDED_S1_ARMS), "diagnostics": diagnostics,
            "baseline_pulse": base["baseline_pulse"], "feature_clock": base["feature_clock"],
            "environment": base["environment"], "analysis_pcm_sha256": base["analysis_pcm_sha256"],
            "r1_analysis_pcm_sha256": pcm_hash, "r1_feature_source": "captured_phrase_proposal_s1_extract_call",
            "elapsed_seconds": time.monotonic() - started,
            "discovery_truth_input": False, "performance_issue_confirmed": False,
            "listening_accepted": False, "canonical_defaults_activated": False}


# ------------------------------------------------------ authorization ----

def git(args, timeout=20):
    try:
        return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def git_blob_sha256(revision, relative):
    completed = git(["show", f"{revision}:{relative}"])
    if completed is None or completed.returncode != 0:
        return None
    return hashlib.sha256(completed.stdout).hexdigest()


def git_is_ancestor(commit):
    if not (isinstance(commit, str) and 7 <= len(commit) <= 64 and all(c in "0123456789abcdef" for c in commit)):
        return False
    completed = git(["merge-base", "--is-ancestor", commit, "HEAD"])
    return completed is not None and completed.returncode == 0


def authorize(plan_path, plan_hash, release_path, release_hash, phase):
    require(phase in ("generate", "discover", "score"), "registered_phase_required")
    try:
        plan = strict_read(plan_path, plan_hash)
    except (ValueError, OSError) as exc:
        raise ValueError("preregistration_changed") from exc
    require(plan == metadata(), "preregistration_changed")
    require(git_blob_sha256("HEAD", PREREG_RECEIPT) == plan_hash, "preregistration_uncommitted")
    require(release_path is not None and release_hash is not None, "release_required")
    try:
        release = strict_read(release_path, release_hash)
    except (ValueError, OSError) as exc:
        raise ValueError("release_binding_changed") from exc
    require(isinstance(release, dict) and release.get("actor") in RELEASE_ACTORS and release.get("suite") == SUITE
            and phase in release.get("authorized_phases", []), "release_required")
    quote = release.get("authorization_quote")
    require(isinstance(quote, str) and quote.strip(), "release_required")
    commit = release.get("prereg_commit")
    require(git_is_ancestor(commit) and git_blob_sha256(commit, PREREG_RECEIPT) == plan_hash, "release_binding_changed")
    require(release.get("plan_sha256") == plan_hash and release.get("worker_sha256") == digest(__file__)
            and release.get("dependency_sha256") == PINS and release.get("budgets") == BUDGETS, "release_binding_changed")
    verify_pins()
    require(digest(FFMPEG_PIN["path"]) == FFMPEG_PIN["sha256"], "qualified_ffmpeg_changed")
    return {"plan_path": str(plan_path), "plan_sha256": plan_hash, "release_path": str(release_path),
            "release_sha256": release_hash, "worker_sha256": digest(__file__), "prereg_commit": commit,
            "actor": release["actor"]}


# ------------------------------------------------- generate / discover ----

def deadline(started, budget, case_started=None):
    require(time.monotonic() - started < budget, "overall_deadline")
    if case_started is not None:
        require(time.monotonic() - case_started < BUDGETS["case_seconds"], "case_deadline")


def generate(output, authorization, seeds=SEEDS, budget=BUDGETS["overall_seconds"]):
    import numpy as np
    started = time.monotonic()
    output = artifact_path(output)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    cases, shared = [], {}
    for seed in seeds:
        for cohort in COHORTS:
            began = time.monotonic()
            deadline(started, budget, began)
            components, truth = construct(seed, cohort)
            name = f"case{len(cases):02d}"
            directory = output / name
            directory.mkdir(mode=0o700)
            assets, raw_components = {}, {}
            for key in COMPONENTS:
                raw = pcm16(components[key])
                raw_components[key] = raw
                path = directory / (key + ".wav")
                with wave.open(str(path), "wb") as handle:
                    handle.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
                    handle.writeframes(raw)
                require(path.stat().st_size <= BUDGETS["wav_bytes"], "wav_byte_bound")
                assets[key] = {"path": str(path.relative_to(output)), "sha256": digest(path),
                               "pcm_sha256": hashlib.sha256(raw).hexdigest()}
                if key in ("fan", "noise", "click"):
                    identity = f"{seed}:{key}"
                    require(identity not in shared or shared[identity] == assets[key]["sha256"], "nuisance_not_shared")
                    shared[identity] = assets[key]["sha256"]
            decoded = {key: np.frombuffer(raw, dtype="<i2").astype("int32") for key, raw in raw_components.items()}
            error = int(np.abs(decoded["mix"] - sum(decoded[key] for key in ("clean", "fan", "noise", "click"))).max())
            require(error <= 2, "component_sum_two_lsb")
            cue = silence_cue(raw_components["clean"], truth["geometry"])
            require(not cue["applicable"] or cue["passed"], "silence_cue_present")
            truth.update(source_sha256=assets["mix"]["sha256"], assets=assets,
                         construction_checks={"rendered_component_sum_maximum_lsb": error, "peak_below_0_5": True,
                                              "gaps_at_most_100ms": True, "silence_cue": cue,
                                              "fill_and_b_distinct": truth["geometry"]["checks"]})
            truth_hash = write_new(directory / "truth.json", truth)
            cases.append({"id": name, "seed": seed, "cohort": cohort, "source": assets["mix"],
                          "truth": {"path": str((directory / "truth.json").relative_to(output)), "sha256": truth_hash},
                          "assets": assets, "elapsed_seconds": time.monotonic() - began})
            deadline(started, budget, began)
    verify_pins()
    require(digest(__file__) == authorization["worker_sha256"], "worker_changed")
    write_new(output / "bank.json", {"schema_version": 1, "suite": SUITE, "seeds": list(seeds), "cases": cases,
                                     "shared_nuisance_sha256": shared, "authorization": authorization,
                                     "elapsed_seconds": time.monotonic() - started, "status": "generated_no_discovery"})
    return output / "bank.json"


def expected_cases(seeds):
    return [(seed, cohort) for seed in seeds for cohort in COHORTS]


def analysis_python():
    return os.environ.get("VIDEO_UTILS_ANALYSIS_PYTHON") or sys.executable


def child_environment():
    environment = dict(os.environ)
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
        environment[key] = str(BUDGETS["threads"])
    return environment


def discover(bank_path, bank_hash, output, authorization, seeds=SEEDS, mode="heldout", budget=BUDGETS["overall_seconds"],
             started=None):
    started = time.monotonic() if started is None else started
    bank_path = artifact_path(bank_path, existing=True)
    bank = strict_read(bank_path, bank_hash)
    require(bank.get("suite") == SUITE and [(row["seed"], row["cohort"]) for row in bank["cases"]] == expected_cases(seeds)
            and bank["authorization"]["worker_sha256"] == authorization["worker_sha256"]
            and bank["authorization"].get("plan_sha256") == authorization.get("plan_sha256"), "bank_plan_source_binding")
    output = artifact_path(output)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    # Reduce the bank to opaque source path + hash; discovery never reads truth bytes.
    sources = [(artifact_path(bank_path.parent / row["source"]["path"], existing=True), row["source"]["sha256"])
               for row in bank["cases"]]
    predictions, maximum = [], 0.
    for index, (source, source_hash) in enumerate(sources):
        began = time.monotonic()
        deadline(started, budget, began)
        path = output / f"prediction{index:02d}.json"
        remaining = budget - (time.monotonic() - started)
        completed = subprocess.run([analysis_python(), str(Path(__file__).resolve()), "_source", str(source), source_hash,
                                    str(path), authorization["worker_sha256"], mode],
                                   capture_output=True, text=True, env=child_environment(),
                                   timeout=max(1., min(BUDGETS["case_seconds"], remaining)), check=False)
        require(completed.returncode == 0, "opaque_discovery_failed:" + completed.stderr[-1000:])
        prediction = strict_read(path)
        elapsed = time.monotonic() - began
        maximum = max(maximum, elapsed)
        deadline(started, budget, began)
        predictions.append({"path": path.name, "sha256": digest(path), "source_sha256": source_hash,
                            "child_elapsed_seconds": prediction["elapsed_seconds"], "wall_seconds": elapsed})
        print(json.dumps({"case": index, "status": "sealed_case_truth_unopened", "wall_seconds": round(elapsed, 3)}), flush=True)
    verify_pins()
    require(digest(bank_path) == bank_hash and digest(__file__) == authorization["worker_sha256"], "discovery_bindings_changed")
    write_new(output / "predictions-sealed.json", {"schema_version": 1, "suite": SUITE, "mode": mode,
              "status": "all_predictions_sealed_truth_unopened", "bank_sha256": bank_hash, "predictions": predictions,
              "authorization": authorization, "elapsed_seconds": time.monotonic() - started,
              "maximum_source_wall_seconds": maximum})
    return output / "predictions-sealed.json"


# --------------------------------------------------------------- score ----

def score_case(s1, references, estimates):
    row = s1.score_rows(references, estimates)
    for metric in row["pair_iou"]:
        metric["matched_reference_offsets"] = [
            {"reference_index": match["reference_index"],
             "offsets_seconds": [s1.pair_spans(estimates[match["estimate_index"]])[k][v]
                                 - s1.pair_spans(references[match["reference_index"]])[k][v] for k in (0, 1) for v in (0, 1)]}
            for match in metric["matches"]]
    return row


def mae(offsets):
    return (sum(abs(v) for v in offsets) / len(offsets)) if offsets else None


def aggregate(results, arms):
    """Sums over cases; MAE denominators explicit; abstentions stay in denominators."""
    out = {}
    for arm in arms:
        selected = [row["scores"][arm] for row in results]
        pairs = []
        for index, threshold in enumerate((.5, .75)):
            rows = [row["pair_iou"][index] for row in selected]
            totals = {key: sum(row[key] for row in rows) for key in ("reference_count", "estimate_count", "tp", "fp", "fn")}
            offsets = [v for row in rows for match in row["matched_reference_offsets"] for v in match["offsets_seconds"]]
            totals.update(threshold=threshold, matched_endpoint_mae_seconds=mae(offsets),
                          mae_denominator=len(offsets), mae_denominator_rule="4 x matched pairs")
            pairs.append(totals)
        endpoints = []
        for index, threshold in enumerate((.02, .05, .1)):
            rows = [row["typed_endpoints"][index] for row in selected]
            endpoints.append({"threshold": threshold, **{key: sum(row[key] for row in rows)
                                                       for key in ("reference_count", "estimate_count", "tp", "fp", "fn")}})
        cohorts = {}
        for cohort in POSITIVE_COHORTS:
            rows = [row for row in results if row["cohort"] == cohort]
            cohorts[cohort] = {"tp_iou_0.5": sum(row["scores"][arm]["pair_iou"][0]["tp"] for row in rows),
                               "tp_iou_0.75": sum(row["scores"][arm]["pair_iou"][1]["tp"] for row in rows),
                               "reference_count": sum(row["reference_pair_count"] for row in rows)}
        negatives = {}
        for cohort in NEGATIVE_COHORTS:
            rows = [row for row in results if row["cohort"] == cohort and row["reference_pair_count"] == 0]
            negatives[cohort] = {"false_candidates": sum(row["scores"][arm]["candidate_count"] for row in rows),
                                 "case_count": len(rows)}
        out[arm] = {"pair_iou": pairs, "typed_endpoints": endpoints, "per_positive_cohort_tp": cohorts,
                    "negative_false_candidates": negatives,
                    "negative_false_candidates_total": sum(v["false_candidates"] for v in negatives.values())}
    matched = {arm: {(row["id"], match["reference_index"]): match["offsets_seconds"]
                     for row in results for match in row["scores"][arm]["pair_iou"][0]["matched_reference_offsets"]}
               for arm in arms}
    common = sorted(set.intersection(*(set(value) for value in matched.values()))) if arms else []
    common_mae = {"reference_keys": [list(key) for key in common], "denominator": 4 * len(common),
                  "denominator_rule": "4 x references matched at IoU 0.5 by every arm"}
    if common:
        common_mae["mae_seconds"] = {arm: mae([v for key in common for v in matched[arm][key]]) for arm in arms}
        common_mae["reason"] = None
    else:
        common_mae["mae_seconds"] = {arm: None for arm in arms}
        common_mae["reason"] = "no_reference_matched_by_all_arms"
    return {"arms": out, "common_reference_mae": common_mae}


def read_truth(path, expected):
    return strict_read(path, expected)


def score(bank_path, bank_hash, seal_path, seal_hash, output, authorization, seeds=SEEDS, arms=ARMS, mode="heldout"):
    bank_path, seal_path = artifact_path(bank_path, existing=True), artifact_path(seal_path, existing=True)
    bank, seal = strict_read(bank_path, bank_hash), strict_read(seal_path, seal_hash)
    count = len(expected_cases(seeds))
    require(bank.get("suite") == seal.get("suite") == SUITE and seal.get("bank_sha256") == bank_hash and seal.get("mode") == mode
            and seal.get("status") == "all_predictions_sealed_truth_unopened" and len(seal.get("predictions", [])) == len(bank["cases"]) == count,
            "global_complete_prediction_seal_required")
    require([(row["seed"], row["cohort"]) for row in bank["cases"]] == expected_cases(seeds), "fixed_score_cases")
    # Read and verify ALL predictions before opening ANY truth.
    predictions = []
    for row in seal["predictions"]:
        try:
            predictions.append(strict_read(artifact_path(seal_path.parent / row["path"], existing=True), row["sha256"]))
        except ValueError as exc:
            raise ValueError("sealed_prediction_changed") from exc
    for case, row, prediction in zip(bank["cases"], seal["predictions"], predictions):
        require(case["source"]["sha256"] == row["source_sha256"] == prediction["source_sha256"], "prediction_source_binding")
        require(digest(artifact_path(bank_path.parent / case["source"]["path"], existing=True)) == prediction["source_sha256"],
                "score_source_changed")
        require(set(arms) <= set(prediction["arms"]) and prediction["discovery_truth_input"] is False
                and not set(DISCARDED_S1_ARMS) & set(prediction["arms"]), "prediction_contract")
    s1 = s1_module()
    results = []
    for case, prediction in zip(bank["cases"], predictions):
        truth = read_truth(artifact_path(bank_path.parent / case["truth"]["path"], existing=True), case["truth"]["sha256"])
        require(truth["source_sha256"] == prediction["source_sha256"]
                and truth["ground_truth_scope"] == "generator_only_not_musician", "truth_binding")
        results.append({"id": case["id"], "seed": case["seed"], "cohort": case["cohort"],
                        "reference_pair_count": len(truth["recurrence_pairs"]),
                        "scores": {arm: score_case(s1, truth["recurrence_pairs"], prediction["arms"][arm]) for arm in arms}})
    summary = aggregate(results, arms)
    verify_pins()
    require(digest(bank_path) == bank_hash and digest(seal_path) == seal_hash and digest(__file__) == authorization["worker_sha256"],
            "scoring_bindings_changed")
    for row in seal["predictions"]:
        require(digest(seal_path.parent / row["path"]) == row["sha256"], "prediction_changed_after_scoring")
    document = {"schema_version": 1, "suite": SUITE, "mode": mode, "status": "generated_research_scored",
                "cases": results, "aggregate": summary, "arms": list(arms), "authorization": authorization,
                "bank_sha256": bank_hash, "seal_sha256": seal_hash, "truth_read_after_global_seal": True,
                "scoring": scoring_definition(), "canonical_defaults_activated": False, **CLAIMS}
    write_new(output, document)
    return Path(output), document


# --------------------------------------------------------- development ----

def choose_theta(summary):
    """Dev rule: maximize TP@IoU0.5 minus negative false candidates; ties -> larger theta."""
    rows = []
    for theta in R1_SETTINGS["theta_candidates"]:
        arm = summary["arms"][f"R1_lag@{theta:.2f}"]
        value = arm["pair_iou"][0]["tp"] - arm["negative_false_candidates_total"]
        rows.append({"theta": theta, "tp_iou_0.5": arm["pair_iou"][0]["tp"],
                     "negative_false_candidates": arm["negative_false_candidates_total"], "objective": value})
    best = max(rows, key=lambda row: (row["objective"], row["theta"]))
    return best["theta"], rows


def dev_calibrate(output, run_index):
    require(type(run_index) is int and 1 <= run_index <= BUDGETS["dev_runs_maximum"], "dev_run_bound")
    started = time.monotonic()
    budget = BUDGETS["dev_run_seconds"]
    verify_pins()
    output = artifact_path(output)
    authorization = {"actor": "lane_development_calibration", "plan_sha256": None, "worker_sha256": digest(__file__),
                     "basis": "PHRASES_S2 section 5.3 development calibration on seed 1009 only; not held-out"}
    bank = generate(output / "bank", authorization, seeds=(DEV_SEED,), budget=budget)
    bank_hash = digest(bank)
    seal = discover(bank, bank_hash, output / "run", authorization, seeds=(DEV_SEED,), mode="dev", budget=budget,
                    started=started)
    arms = ("Araw", "S1_support") + tuple(f"R1_lag@{theta:.2f}" for theta in R1_SETTINGS["theta_candidates"])
    path, document = score(bank, bank_hash, seal, digest(seal), output / "dev-score.json", authorization,
                           seeds=(DEV_SEED,), arms=arms, mode="dev")
    theta, rows = choose_theta(document["aggregate"])
    elapsed = time.monotonic() - started
    require(elapsed <= budget, "dev_run_deadline")
    receipt = {"schema_version": 1, "suite": SUITE, "kind": "development_calibration_not_heldout", "dev_seed": DEV_SEED,
               "run_index": run_index, "runs_maximum": BUDGETS["dev_runs_maximum"], "theta_candidates": R1_SETTINGS["theta_candidates"],
               "rule": "maximize dev TP@IoU0.5 minus dev negative false candidates; ties -> larger theta",
               "objective_rows": rows, "chosen_theta": theta, "worker_sha256": authorization["worker_sha256"],
               "bank_sha256": bank_hash, "seal_sha256": digest(seal), "score_sha256": digest(path),
               "score_path": str(path.relative_to(ROOT)), "elapsed_seconds": elapsed,
               "dev_aggregate": document["aggregate"], "reported_as_heldout": False,
               "dependency_sha256": PINS, "ffmpeg": FFMPEG_PIN, **CLAIMS}
    write_new(output / "dev-calibration.json", receipt)
    return output / "dev-calibration.json", receipt


# ------------------------------------------------------------- V2 bank ----

def load_holdout():
    path = ROOT / V2_GENERATOR
    require(not path.is_symlink() and digest(path) == V2_GENERATOR_SHA256, "holdout_generator_changed")
    module = load_module(path, "s2_v2_benchmark_holdout")
    module.ARTIFACTS = LANE_AREA  # only the output root is rebound; generator bytes unchanged
    return module


def v2_generate_child(plan_path, bank_dir):
    module = load_holdout()
    return module.generate(Path(plan_path), Path(bank_dir), BUDGETS["v2_internal_seconds"])


def v2_bank(output, reference_fixtures):
    started = time.monotonic()
    output = artifact_path(output)
    require(output.name.startswith("v2-bank-"), "v2_output_name_required")
    require(not output.exists(), "output_exists")
    module = load_holdout()
    plan_path = output / "plan.json"
    plan_hash = module.write_new(plan_path, module.make_plan())
    require(plan_hash == V2_PLAN_SHA256, "holdout_plan_changed")
    plan, validated = module.validate_plan(plan_path)
    require(validated == plan_hash, "holdout_plan_changed")
    completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), "_v2_generate", str(plan_path), str(output / "bank")],
                               capture_output=True, text=True, timeout=BUDGETS["v2_external_seconds"], check=False,
                               env=dict(child_environment(), OMP_NUM_THREADS="1"))
    require(completed.returncode == 0, "v2_generation_failed:" + completed.stderr[-1000:])
    result = json.loads(completed.stdout)
    fixtures_path = artifact_path(output / "bank" / "fixtures.json", existing=True)
    fixtures = strict_read(fixtures_path, result["fixtures_sha256"])
    require(fixtures["plan_sha256"] == V2_PLAN_SHA256 and fixtures["generator_sha256"] == V2_GENERATOR_SHA256, "v2_binding_changed")
    reference = strict_read(reference_fixtures) if reference_fixtures else None
    reference_hash = digest(reference_fixtures) if reference_fixtures else None
    previous = {row["id"]: row for row in reference["cases"]} if reference else {}
    cases, same_components, same_truths = [], 0, 0
    for row in fixtures["cases"]:
        components = {name: receipt["sha256"] for name, receipt in sorted(row["components"].items())}
        old = previous.get(row["id"])
        if old:
            same_components += sum(old["components"].get(name, {}).get("sha256") == value for name, value in components.items())
            same_truths += old["truth"]["sha256"] == row["truth"]["sha256"]
        cases.append({"id": row["id"], "seed": row["seed"], "cohort": row["cohort"],
                      "mix_sha256": row["components"]["mix"]["sha256"], "component_sha256": components,
                      "truth_json": {"path": row["truth"]["path"], "sha256": row["truth"]["sha256"]}})
    observed_commit = git(["log", "-1", "--format=%H", "--", V2_GENERATOR])
    observed_commit = observed_commit.stdout.decode().strip() if observed_commit is not None and observed_commit.returncode == 0 else None
    receipt = {
        "schema_version": 1, "kind": "v2_holdout_bank_receipt", "peer": "xoruby", "suite": fixtures["suite"],
        "plan_sha256": plan_hash, "recipe_sha256": plan["recipe_sha256"], "generator_sha256": V2_GENERATOR_SHA256,
        "generator_commit": V2_GENERATOR_COMMIT, "generator_commit_observed": observed_commit,
        "generator_output_root_rebinding": {"attribute": "ARTIFACTS", "admitted_value": "artifacts/benchmarks",
                                            "rebound_to": str(LANE_AREA.relative_to(ROOT)), "generator_bytes_unchanged": True},
        "operations": ["holdout-plan (make_plan + write_new)", "holdout-validate (validate_plan)",
                       "holdout-generate (generate, internal timeout 600 s, external child timeout 660 s)"],
        "bank_relative_path": str((output / "bank").relative_to(ROOT)),
        "fixtures": {"path": str(fixtures_path.relative_to(ROOT)), "sha256": result["fixtures_sha256"]},
        "truth_json_relative_paths": "bank-relative: <case-id>/truth.json (listed per case)",
        "case_count": len(cases), "component_count": sum(len(row["component_sha256"]) for row in cases),
        "total_duration_seconds": fixtures["total_duration_seconds"], "cases": cases,
        "generator_elapsed_seconds": fixtures["elapsed_seconds"], "wrapper_elapsed_seconds": time.monotonic() - started,
        "internal_timeout_seconds": BUDGETS["v2_internal_seconds"], "external_timeout_seconds": BUDGETS["v2_external_seconds"],
        "reproduction": {"reference_fixtures_path": str(reference_fixtures) if reference_fixtures else None,
                         "reference_fixtures_sha256": reference_hash,
                         "identical_components": same_components if reference else None, "component_denominator": 48,
                         "identical_truths": same_truths if reference else None, "truth_denominator": 12,
                         "basis": "byte sha256 equality per component WAV and per truth JSON"},
        "licence": V2_LICENCE, "reserved_seed_range": {"first": V2_RESERVED_SEEDS[0], "last": V2_RESERVED_SEEDS[1],
                                                      "use": "future evaluation-only V2 extensions; requires a new admitted plan because the generator is fixed to seeds 211/307"},
        "training_use_statement": V2_TRAINING_STATEMENT,
        "prior_use_disclosure": "seeds 211/307 were already used once by video-utils for the frozen A/B/C/D phrase-window evaluation",
        "ground_truth_scope": "generator_only_not_musician",
        "audio_transfer": "transfer of audio to XORuby is a separate root action; audio is never committed",
        "audio_committed": False, "quality_metrics": "not_evaluated", "listening_accepted": False,
        "inference_executed": False, "real_recording_labels": False}
    write_new(output / "receipt.json", receipt)
    return output / "receipt.json", receipt


# ----------------------------------------------------------------- CLI ----

def write_release(output, plan_hash, prereg_commit, actor, quote):
    require(actor in RELEASE_ACTORS and isinstance(quote, str) and quote.strip(), "release_required")
    release = {"actor": actor, "suite": SUITE, "authorized_phases": ["generate", "discover", "score"],
               "plan_sha256": plan_hash, "worker_sha256": digest(__file__), "dependency_sha256": PINS,
               "budgets": BUDGETS, "prereg_commit": prereg_commit, "authorization_quote": quote,
               "observed_at_unix": time.time()}
    return write_new(output, release)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preregister").add_argument("output")
    geometry_cmd = sub.add_parser("geometry-check", help="Pure-Python geometry checks for a seed; no audio")
    geometry_cmd.add_argument("--seed", type=int, required=True)
    internal = sub.add_parser("_source", help=argparse.SUPPRESS)
    for name in ("source", "source_sha256", "output", "worker_sha256", "mode"):
        internal.add_argument(name)
    v2child = sub.add_parser("_v2_generate", help=argparse.SUPPRESS)
    v2child.add_argument("plan")
    v2child.add_argument("bank")
    dev = sub.add_parser("dev-calibrate")
    dev.add_argument("--run-index", type=int, required=True)
    dev.add_argument("output")
    release = sub.add_parser("write-release")
    release.add_argument("--plan-sha256", required=True)
    release.add_argument("--prereg-commit", required=True)
    release.add_argument("--actor", required=True, choices=RELEASE_ACTORS)
    release.add_argument("--authorization-quote-file", required=True)
    release.add_argument("output")
    v2 = sub.add_parser("v2-bank")
    v2.add_argument("--output", required=True)
    v2.add_argument("--reference-fixtures")
    for name in ("generate", "discover", "score"):
        command = sub.add_parser(name)
        command.add_argument("--plan", required=True)
        command.add_argument("--plan-sha256", required=True)
        command.add_argument("--release")
        command.add_argument("--release-sha256")
        if name in ("discover", "score"):
            command.add_argument("--bank", required=True)
            command.add_argument("--bank-sha256", required=True)
        if name == "score":
            command.add_argument("--seal", required=True)
            command.add_argument("--seal-sha256", required=True)
        command.add_argument("output")
    args = parser.parse_args(argv)
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
        try:
            threads = int(os.environ.get(key, "2"))
        except ValueError:
            threads = 2
        os.environ[key] = str(max(1, min(BUDGETS["threads"], threads)))
    if args.command == "preregister":
        result = {"path": args.output, "sha256": write_new(args.output, metadata())}
    elif args.command == "geometry-check":
        require(args.seed in SEEDS or args.seed == DEV_SEED, "registered_seed_required")
        rows = {cohort: validate_geometry(geometry(args.seed, cohort)) for cohort in COHORTS}
        result = {"seed": args.seed, "geometry_checks_passed": rows, "audio_generated": False}
    elif args.command == "_source":
        prediction = source_child(args.source, args.source_sha256, args.output, args.worker_sha256, args.mode)
        require(prediction["elapsed_seconds"] < BUDGETS["case_seconds"], "case_deadline")
        write_new(args.output, prediction)
        return 0
    elif args.command == "_v2_generate":
        result = v2_generate_child(args.plan, args.bank)
    elif args.command == "dev-calibrate":
        path, receipt = dev_calibrate(args.output, args.run_index)
        result = {"path": str(path), "sha256": digest(path), "chosen_theta": receipt["chosen_theta"],
                  "objective_rows": receipt["objective_rows"], "elapsed_seconds": receipt["elapsed_seconds"]}
    elif args.command == "write-release":
        quote = Path(args.authorization_quote_file).read_text()
        result = {"path": args.output, "sha256": write_release(args.output, args.plan_sha256, args.prereg_commit, args.actor, quote)}
    elif args.command == "v2-bank":
        path, receipt = v2_bank(args.output, args.reference_fixtures)
        result = {"path": str(path), "sha256": digest(path), "reproduction": receipt["reproduction"]}
    else:
        authorization = authorize(args.plan, args.plan_sha256, args.release, args.release_sha256, args.command)
        if args.command == "generate":
            path = generate(args.output, authorization)
        elif args.command == "discover":
            path = discover(args.bank, args.bank_sha256, args.output, authorization)
        else:
            path, _ = score(args.bank, args.bank_sha256, args.seal, args.seal_sha256, args.output, authorization)
        result = {"path": str(path), "sha256": digest(path), "status": "completed"}
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)[:1000]}), file=sys.stderr)
        raise SystemExit(1)
