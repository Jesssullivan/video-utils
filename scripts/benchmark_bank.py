#!/usr/bin/env python3
"""Standard-library technical-v2 generator; truth never enters discovery workers."""
from __future__ import annotations

from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import random
import time

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "program" / "benchmarks-v2.json"
MIDI = (24, 29, 34, 39, 46, 51, 56, 60, 65)
IDS = ("low32-sustain", "palm-muted-recurrence", "legato-recurrence", "c1-missing-fundamental",
       "tuning-ladder", "legato-transition", "sweep-and-polyphony", "rest-syncopation-tuplets",
       "variable-tempo", "click-overlap-abstention", "timing-reference", "timing-errors")
DURATIONS = (8, 8, 8, 8, 8, 10, 10, 12, 12, 12, 12, 12)
KINDS = ("sustain","palm_mute","legato","missing_fundamental","ladder","legato_transition",
         "sweep_polyphony","tuplets","tempo_ramp","click_overlap","timing_reference","timing_errors")


def validate_configuration(config):
    if config.get("schema_version") != 2 or config.get("suite") != "technical-v2":
        raise ValueError("Unsupported v2 benchmark schema")
    fixtures = config.get("fixtures", [])
    if not isinstance(fixtures, list) or tuple(item.get("id") for item in fixtures) != IDS:
        raise ValueError("technical-v2 requires the twelve registered fixtures in order")
    if tuple(item.get("duration_seconds") for item in fixtures) != DURATIONS or sum(DURATIONS) != 120:
        raise ValueError("technical-v2 duration budget must be exactly 120 seconds")
    if type(config.get("sample_rate")) is not int or config["sample_rate"] != 48000:
        raise ValueError("technical-v2 requires native 48 kHz mono")
    if tuple(item.get("kind") for item in fixtures) != KINDS or any(type(item["duration_seconds"]) is not int for item in fixtures):
        raise ValueError("technical-v2 fixture construction is frozen")
    if any(bool(item.get("legacy_v1",False)) != (position<3) for position,item in enumerate(fixtures)):
        raise ValueError("Legacy waveform delegation is restricted to the first three cases")
    if type(config.get("bpm")) is not int or config["bpm"] != 178 or type(config.get("seed")) is not int or config["seed"] != 20261005:
        raise ValueError("technical-v2 timing and seed are frozen")
    limits = {"max_cases": 12, "max_duration_seconds": 12, "max_total_duration_seconds": 120,
              "worker_timeout_seconds": 120, "overall_timeout_seconds": 600, "max_json_bytes": 5_000_000,
              "max_worker_output_bytes": 8_000_000, "max_decoded_bytes": 3_000_000, "math_threads": 2}
    for key, maximum in limits.items():
        value = config.get("bounds", {}).get(key)
        if type(value) is not int or not 0 < value <= maximum:
            raise ValueError("technical-v2 resource ceiling exceeded")
    if config["bounds"]["max_cases"] < 12 or config["bounds"]["max_total_duration_seconds"] < 120 or config["bounds"]["max_duration_seconds"]<12:
        raise ValueError("Configured budget cannot accommodate the registered bank")
    return config


def hz(midi):
    return 440 * 2 ** ((midi - 69) / 12)


def sample_time(seconds, rate):
    native = round(seconds * rate)
    return native, native / rate


def complement(regions, duration):
    merged = []
    for start, end in sorted(regions):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    gaps, cursor = [], 0.0
    for start, end in merged:
        if start > cursor:
            gaps.append([cursor, start])
        cursor = max(cursor, end)
    if cursor < duration:
        gaps.append([cursor, duration])
    return gaps


def recurrence(first, second, identity="repeat-1"):
    a, b = first
    c, d = second
    return {"id": identity, "first_span_seconds": list(first), "second_span_seconds": list(second),
            "warp_reference": {"source_times_seconds": [a, b], "target_times_seconds": [c, d],
                               "source_offsets_seconds": [0.0, b-a], "target_offsets_seconds": [0.0, d-c],
                               "mapping_kind": "affine"}}


class Signal:
    def __init__(self, definition, config):
        self.rate = config["sample_rate"]
        self.duration = definition["duration_seconds"]
        self.clean = [0.0] * round(self.rate * self.duration)
        self.regions, self.trajectories, self.events = [], [], []

    def event(self, identity, ideal, duration, midi, articulation, beat=None, actual=None, edit=None):
        ideal_sample, ideal_time = sample_time(ideal, self.rate)
        actual_sample, actual_time = sample_time(ideal if actual is None else actual, self.rate)
        if edit == "omitted_attack":
            actual_sample, actual_time = None, None
        fraction = Fraction(beat).limit_denominator(140) if beat is not None else None
        row = {"id": identity, "ideal_onset_native_sample": ideal_sample, "ideal_onset_seconds": ideal_time,
               "ideal_analytic_onset_seconds": ideal, "onset_native_sample": actual_sample,
               "onset_source_seconds": actual_time, "duration_samples": round(duration*self.rate),
               "midi_notes": list(midi), "frequencies_hz": [hz(note) for note in midi],
               "articulation": articulation, "injected_edit": edit,
               "beat_position": {"numerator": fraction.numerator, "denominator": fraction.denominator} if fraction is not None else None}
        if actual_sample is not None:
            row["injected_offset_seconds"] = actual_time-ideal_time
        self.events.append(row)

    def tone(self, start, end, midi, articulation="sustain", condition="clean", gain=.13, picked=False,
             frequencies=None):
        frequencies = frequencies or [hz(note) for note in midi]
        first, start = sample_time(start, self.rate)
        last, end = sample_time(end, self.rate)
        if not 0 <= first < last <= len(self.clean):
            raise ValueError("Generated tone lies outside native source extent")
        for index in range(first, last):
            age = (index-first)/self.rate
            envelope = min(1, age/(.0015 if picked else .008), (last-index)/self.rate/.008)
            if picked:
                envelope *= math.exp(-age/.035)
            value = sum(math.sin(2*math.pi*f*age) for f in frequencies)/len(frequencies)
            if condition == "tanh_distorted":
                value = math.tanh(3.8*value)
            self.clean[index] += gain*max(0, envelope)*value
        self.regions.append({"start_seconds": start, "end_seconds": end, "start_native_sample": first,
                             "end_native_sample": last, "frequencies_hz": frequencies, "midi_notes": list(midi),
                             "monophonic": len(frequencies) == 1, "condition": condition, "articulation": articulation,
                             "expected_abstention_reasons": ["polyphonic_mixture"] if len(frequencies) > 1 else []})

    def glide(self, start, end, first_midi, last_midi):
        first, start = sample_time(start, self.rate)
        last, end = sample_time(end, self.rate)
        f0, f1 = hz(first_midi), hz(last_midi)
        slope = math.log(f1/f0)/(end-start)
        for index in range(first, last):
            age = (index-first)/self.rate
            integral = f0*math.expm1(slope*age)/slope if slope else f0*age
            envelope = min(1, age/.008, (last-index)/self.rate/.008)
            self.clean[index] += .13*max(0, envelope)*math.tanh(2.4*math.sin(2*math.pi*integral))
        self.trajectories.append({"start_seconds": start, "end_seconds": end,
                                  "start_native_sample": first, "end_native_sample": last,
                                  "start_frequency_hz": f0, "end_frequency_hz": f1,
                                  "formula": "log_frequency_linear_time", "monophonic": True,
                                  "condition": "tanh_distorted", "articulation": "legato_glide"})


def tempo_phase(t):
    """Quarter beats since zero, continuous 178→210 BPM on seconds 1..11."""
    if t <= 1:
        return 178*t/60
    elapsed = min(t, 11)-1
    phase = 178/60 + (178*elapsed + 1.6*elapsed*elapsed)/60
    return phase + max(0, t-11)*210/60


def tempo_time(beat):
    if beat <= tempo_phase(1):
        return beat*60/178
    if beat >= tempo_phase(11):
        return 11+(beat-tempo_phase(11))*60/210
    residual = beat*60-178
    return 1+2*residual/(178+math.sqrt(178**2+6.4*residual))


def generate(definition, config, legacy_generator):
    rate, duration = config["sample_rate"], definition["duration_seconds"]
    period = 60/config["bpm"]
    if definition.get("legacy_v1"):
        local = dict(config, duration_seconds=8)
        signals, previous = legacy_generator(definition, local)
        truth = enrich_legacy(previous, definition, rate)
        return signals, truth
    signal = Signal(definition, config)
    kind = definition["kind"]
    pairs, phrases = [], []
    harmonics = None
    signal_transitions = []
    if kind == "missing_fundamental":
        harmonics = [{"index": k, "amplitude": amp, "phase_radians": 0.0}
                     for k, amp in ((2,.13),(3,.08),(4,.05),(5,.04),(7,.02))]
        first, last = round(.5*rate), round(7.5*rate)
        f0 = definition["fundamental_hz"]
        for index in range(first, last):
            age = (index-first)/rate
            envelope = min(1, age/.01, (last-index)/rate/.02)
            signal.clean[index] = max(0,envelope)*sum(h["amplitude"]*math.sin(2*math.pi*h["index"]*f0*age) for h in harmonics)
        signal.regions.append({"start_seconds":.5,"end_seconds":7.5,"start_native_sample":first,"end_native_sample":last,
                               "frequencies_hz":[f0],"midi_notes":[24],"monophonic":True,
                               "condition":"missing_fundamental_harmonic_proxy","articulation":"sustain",
                               "expected_abstention_reasons":["harmonic_octave_ambiguity"]})
        signal.event("missing-f0-attack",.5,7,[24],"picked_attack")
    elif kind == "ladder":
        for position, midi in enumerate(MIDI):
            start = .5+position*.75
            signal.tone(start,start+.3,[midi],condition="clean")
            signal.tone(start+.3,start+.6,[midi],condition="tanh_distorted")
            signal.event(f"ladder-{position}",start,.6,[midi],"picked_attack")
            native,actual=sample_time(start+.3,rate)
            signal_transitions.append({"native_sample":native,"source_seconds":actual,
                                       "kind":"generator_condition_boundary_not_picked_attack",
                                       "conditions":["clean","tanh_distorted"],"envelope_phase_reset":True})
    elif kind == "legato_transition":
        sequence = [(0.5,1.4,24),(1.6,2.4,29),(2.6,3.4,34),(3.6,4.4,60),(4.6,5.4,65),(6.0,7.0,24),(7.2,8.0,29)]
        for position,(start,end,midi) in enumerate(sequence):
            signal.tone(start,end,[midi],articulation="legato_sustain",condition="tanh_distorted")
            signal.event(f"legato-{position}",start,end-start,[midi],"picked_attack" if position in (0,5) else "pitch_transition")
            if position+1 < len(sequence) and sequence[position+1][0]-end <= .21:
                following = sequence[position+1]
                signal.glide(end,following[0],midi,following[2])
        phrases = [[.5,5.4],[6,8]]
    elif kind == "sweep_polyphony":
        for group, start in enumerate((.5,2.0)):
            notes = MIDI if group == 0 else tuple(reversed(MIDI))
            for position,midi in enumerate(notes):
                onset = start+position*.08
                signal.tone(onset,onset+.08,[midi],articulation="sweep",condition="tanh_distorted",gain=.12)
                signal.event(f"sweep-{group}-{position}",onset,.08,[midi],"sweep_pitch_transition")
        signal.tone(3.5,5.0,[24,29,34],articulation="polyphonic_chord",condition="tanh_distorted")
        signal.tone(5.5,6.5,[60],condition="tanh_distorted")
        signal.tone(6.7,7.7,[65],condition="tanh_distorted")
        phrases = [[.5,1.22],[2,2.72],[3.5,5]]
    elif kind == "tuplets":
        for group,division in enumerate((3,5,7)):
            base = 1+group*8*period
            for beat in range(4):
                for slot in range(division):
                    at = base+(beat+slot/division)*period
                    beat_position = Fraction(group*8+beat)+Fraction(slot,division)
                    if slot == 1 and beat in (1,3):
                        signal.event(f"rest-{group}-{beat}-{slot}",at,period/division,[],"intentional_rest",beat_position)
                        continue
                    signal.tone(at,at+min(.055,period/division*.7),[24 if slot%2 == 0 else 34],"palm_mute","tanh_distorted",picked=True)
                    signal.event(f"tuplet-{group}-{beat}-{slot}",at,min(.055,period/division*.7),[24 if slot%2 == 0 else 34],"picked_attack",beat_position)
            phrases.append([base,base+4*period])
        for n in range(8):
            at = 9+(n+.5)*period
            if at+.05 < duration:
                signal.tone(at,at+.05,[29],"syncopated_pick","tanh_distorted",picked=True)
                signal.event(f"syncopation-{n}",at,.05,[29],"picked_attack",Fraction(2*n+1,2))
    elif kind == "tempo_ramp":
        for n in range(2,35):
            at = tempo_time(n+.5)
            if at+.08 < duration:
                signal.tone(at,at+.08,[24 if n%2 else 34],"palm_mute","tanh_distorted",picked=True)
                signal.event(f"ramp-{n}",at,.08,[24 if n%2 else 34],"picked_attack",Fraction(2*n+1,2))
        phrases = [[tempo_time(4),tempo_time(12)],[tempo_time(20),tempo_time(28)]]
        pair = recurrence(*phrases)
        source_times = [tempo_time(n) for n in range(4,13)]
        target_times = [tempo_time(n+16) for n in range(4,13)]
        pair["warp_reference"].update(source_times_seconds=source_times,target_times_seconds=target_times,
                                     source_offsets_seconds=[t-source_times[0] for t in source_times],
                                     target_offsets_seconds=[t-target_times[0] for t in target_times],mapping_kind="piecewise_linear")
        pairs = [pair]
    elif kind == "click_overlap":
        signal.tone(1.5,5.0,[24],gain=.06)
        for n in (6,9,15,21):
            at = .3+n*period
            signal.tone(at,at+.08,[51],"independent_pick","tanh_distorted",gain=.22,picked=True)
            signal.event(f"overlap-pick-{n}",at,.08,[51],"picked_attack")
        for n in (1,2,3):
            at = 9+n*.45
            signal.tone(at,at+.02,[65],"lookalike_pick","tanh_distorted",gain=.24,picked=True)
            signal.event(f"lookalike-{n}",at,.02,[65],"picked_attack")
    elif kind in ("timing_reference","timing_errors"):
        pattern = (1,1,0,1,1,0,1,1)
        for group,start in enumerate((2.0,6.0)):
            for step,active in enumerate(pattern):
                at = start+step*period/2
                identity = f"motif-{group}-{step}"
                if not active:
                    signal.event(identity,at,period/2,[],"intentional_rest",Fraction(step,2))
                    continue
                offset,edit = 0.0,None
                if kind == "timing_errors" and group == 1:
                    offset = {0:-.025,1:.025,3:-.06,4:.06}.get(step,0.0)
                    edit = "injected_timing_shift" if offset else None
                    if step == 6:
                        edit = "omitted_attack"
                signal.event(identity,at,.07,[24 if step%2 == 0 else 34],"picked_attack",Fraction(step,2),actual=at+offset,edit=edit)
                if edit != "omitted_attack":
                    signal.tone(at+offset,at+offset+.07,[24 if step%2 == 0 else 34],"palm_mute","tanh_distorted",picked=True)
            phrases.append([start,start+4*period])
        if kind == "timing_errors":
            at = 6+2.5*period/2
            signal.tone(at,at+.045,[29],"extra_pick","tanh_distorted",picked=True)
            signal.event("extra-generated-attack",at,.045,[29],"picked_attack",Fraction(5,4),edit="extra_attack")
        pairs = [recurrence(*phrases)]
    else:
        raise ValueError("Unregistered v2 fixture kind")
    length = len(signal.clean)
    noise = [random_value for random_value in _noise(definition["id"],config["seed"],length)]
    clicks = [0.0]*length
    if kind == "tempo_ramp":
        click_times = [tempo_time(n) for n in range(1,math.floor(tempo_phase(duration))) if tempo_time(n)+.009<duration]
        template = [click_times[0]-.001,click_times[0]+.011]
    else:
        click_times = [.3+n*period for n in range(math.floor((duration-.31)/period)+1)]
        template = [.299,.311]
    # The new fixtures provide a literal clean-template declaration independently
    # verified from rendered guitar/noise components. Legacy waveforms are untouched.
    for index in range(round(template[0]*rate),round(template[1]*rate)):
        noise[index] = 0.0
    click_events = []
    for n,at in enumerate(click_times):
        native,actual = sample_time(at,rate)
        for offset in range(round(.009*rate)):
            if native+offset < length:
                age = offset/rate
                clicks[native+offset] += .10*math.exp(-age/.0018)*math.sin(2*math.pi*3500*age)
        overlapping = [row for row in signal.events if row["articulation"] == "picked_attack" and row["onset_source_seconds"] is not None
                       and abs(row["onset_source_seconds"]-actual) <= 1/rate]
        sustain = any(row["start_seconds"] <= actual < row["end_seconds"] for row in signal.regions)
        click_events.append({"id":f"click-{n}","native_sample":native,"source_seconds":actual,"analytic_seconds":at,
                             "overlap_class":"pick_overlap" if overlapping else "sustain_overlap" if sustain else "isolated",
                             "template_id":"click-3500-exp"})
    mixed = [a+b+c for a,b,c in zip(signal.clean,clicks,noise)]
    if max(abs(value) for value in mixed) >= .999:
        raise ValueError("Generated v2 mixture would clip; do not silently normalize")
    support = [[row["start_seconds"],row["end_seconds"]] for row in signal.regions+signal.trajectories]
    guitar_absent = complement(support,duration)
    truth = {"schema_version":2,"kind":"synthetic_generated_signal_and_score_truth",
             "ground_truth_scope":"generator_only_not_musician","id":definition["id"],"sample_rate":rate,
             "sample_count":length,"audio_start_seconds":0.0,"bpm":None if kind=="tempo_ramp" else config["bpm"],
             "fundamental_hz":definition["fundamental_hz"],"generated_score":{"events":signal.events,"rounding":"nearest_native_sample",
                                                                                         "status":"complete_generated_score","attack_reference_known":True},
             "pitch_regions":signal.regions,"pitch_trajectories":signal.trajectories,"guitar_absent_intervals_seconds":guitar_absent,
             "guitar_onsets_seconds":[e["onset_source_seconds"] for e in signal.events if e["articulation"]=="picked_attack" and e["onset_source_seconds"] is not None],
             "click_times_seconds":[e["source_seconds"] for e in click_events],"click_events":click_events,
             "click_only_template_seconds":template,"noise_only_intervals_seconds":[[0,min(.25,template[0]-.01)]],
             "lf_measurement_interval_seconds":None if kind=="missing_fundamental" else ([.55,.75] if kind=="ladder" else [2,6]),
             "phrase_spans_seconds":phrases,"boundaries_seconds":sorted(set(t for span in phrases for t in span if 0<t<duration)),
             "recurrence_pairs":pairs,"repeated_regions_seconds":phrases[:2] if pairs else [],
             "warp_reference":pairs[0]["warp_reference"] if pairs else None,
             "pulse_times_seconds":[e["source_seconds"] for e in click_events],
             "tempo_segments":[{"start_seconds":0,"end_seconds":1,"start_bpm":178,"end_bpm":178},
                               {"start_seconds":1,"end_seconds":11,"start_bpm":178,"end_bpm":210},
                               {"start_seconds":11,"end_seconds":12,"start_bpm":210,"end_bpm":210}] if kind=="tempo_ramp" else
                              [{"start_seconds":0,"end_seconds":duration,"start_bpm":178,"end_bpm":178}],
             "observed_articulation_context":[{"start_seconds":row["start_seconds"],"end_seconds":row["end_seconds"],"articulation":row["articulation"]} for row in signal.regions+signal.trajectories],
             "expected_abstention_reasons":["polyphonic_mixture","rapid_sweep_window_resolution"] if kind=="sweep_polyphony" else
                                           ["legato_pitch_transition_not_picked_attack"] if kind=="legato_transition" else [],
             "signal_transition_events":signal_transitions,
             "listening_accepted":False,"limitations":config["limitations"]}
    if harmonics is not None:
        truth["missing_fundamental"] = {"frequency_hz":definition["fundamental_hz"],"fundamental_coefficient":0.0,
                                        "harmonics":harmonics,"steady_interval_seconds":[1,7],"nonlinearity_after_synthesis":False}
    return {"clean":signal.clean,"click":clicks,"noise":noise,"mix":mixed},truth


def _noise(identity,seed,length):
    rng = random.Random(seed+sum(identity.encode()))
    for _ in range(length):
        yield rng.uniform(-.012,.012)


def enrich_legacy(previous, definition, rate):
    truth = dict(previous)
    spans = previous["repeated_regions_seconds"]
    pairs = [recurrence(*spans)] if len(spans)==2 else []
    support = [[1.3,7.5]] if definition["kind"]=="sustain" else spans
    if definition["kind"]=="palm_mute":
        support=[*support,*[[onset,onset+.08] for onset in previous["guitar_onsets_seconds"] if not any(a<=onset<b for a,b in spans)]]
    regions = [{"start_seconds":a,"end_seconds":b,"start_native_sample":round(a*rate),"end_native_sample":round(b*rate),
                "frequencies_hz":[definition["fundamental_hz"]],"midi_notes":[24],"monophonic":True,
                "condition":"legacy_v1_proxy","articulation":definition["kind"],"expected_abstention_reasons":["legacy_coverage_not_pitch_qualified"]} for a,b in support]
    truth.update(schema_version=2,kind="synthetic_generated_signal_and_score_truth",ground_truth_scope="generator_only_not_musician",
                 id=definition["id"],generated_score={"events":[],"rounding":"nearest_native_sample","status":"legacy_attack_times_only_not_full_score"},
                 pitch_regions=regions,pitch_trajectories=[],guitar_absent_intervals_seconds=complement(support,8),
                 phrase_spans_seconds=spans,boundaries_seconds=sorted(set(t for span in spans for t in span)),recurrence_pairs=pairs,
                 warp_reference=pairs[0]["warp_reference"] if pairs else None,pulse_times_seconds=previous["click_times_seconds"],
                 click_events=[{"id":f"click-{n}","native_sample":round(t*rate),"source_seconds":round(t*rate)/rate,
                                "analytic_seconds":t,"overlap_class":"legacy_unqualified"} for n,t in enumerate(previous["click_times_seconds"])],
                 observed_articulation_context=[{"start_seconds":a,"end_seconds":b,"articulation":definition["kind"]} for a,b in support],
                 expected_abstention_reasons=["legacy_pitch_truth_not_qualified"],
                 tempo_segments=[{"start_seconds":0,"end_seconds":8,"start_bpm":178,"end_bpm":178}],
                 legacy_v1_waveforms=True)
    return truth


def solve(matrix, values):
    """Small pivoted linear solve for independent rendered harmonic verification."""
    rows = [list(row)+[value] for row,value in zip(matrix,values)]
    for column in range(len(rows)):
        pivot = max(range(column,len(rows)),key=lambda r:abs(rows[r][column]))
        rows[column],rows[pivot] = rows[pivot],rows[column]
        if abs(rows[column][column]) < 1e-12:
            raise ValueError("Singular rendered harmonic reference")
        scale = rows[column][column]
        rows[column] = [x/scale for x in rows[column]]
        for row in range(len(rows)):
            if row != column:
                amount = rows[row][column]
                rows[row] = [x-amount*y for x,y in zip(rows[row],rows[column])]
    return [row[-1] for row in rows]


def verify_missing_render(samples, rate, truth):
    """Verify PCM bytes after rendering; include F0 in joint sin/cos regression."""
    specification = truth["missing_fundamental"]
    indices = [1]+[h["index"] for h in specification["harmonics"]]
    f0 = specification["frequency_hz"]
    first,last = (round(t*rate) for t in specification["steady_interval_seconds"])
    # Subsample with a bounded anti-alias-safe stride for highest generated harmonic.
    stride = 24
    width = 2*len(indices)
    gram = [[0.0]*width for _ in range(width)]
    rhs = [0.0]*width
    for native in range(first,last,stride):
        basis = [value for k in indices for value in (math.sin(2*math.pi*k*f0*native/rate),math.cos(2*math.pi*k*f0*native/rate))]
        for a in range(width):
            rhs[a] += basis[a]*samples[native]
            for b in range(a,width):
                gram[a][b] += basis[a]*basis[b]
    for a in range(width):
        for b in range(a):
            gram[a][b] = gram[b][a]
    coefficients = solve(gram,rhs)
    amplitudes = [math.hypot(coefficients[2*n],coefficients[2*n+1]) for n in range(len(indices))]
    checks = [abs(value-h["amplitude"])<=5e-5 for value,h in zip(amplitudes[1:],specification["harmonics"])]
    passed = amplitudes[0] < 5e-5 and all(checks)
    if not passed:
        raise ValueError("Rendered missing-F0 harmonic construction failed independent coefficient check")
    return {"status":"verified_rendered_pcm16_harmonic_coefficients","method":"joint_sine_cosine_fit_including_f0",
            "steady_interval_seconds":specification["steady_interval_seconds"],"native_stride":stride,
            "harmonic_indices":indices,"measured_amplitudes":amplitudes,"absolute_tolerance":5e-5,
            "fundamental_present":False,"scope":"rendered_generated_clean_component_only"}


def create_fixtures(output, config, legacy_generator, pcm_writer, pcm_reader, digest, write_json, deadline=None):
    validate_configuration(config)
    generator_hash=digest(Path(__file__))
    if CONFIG.is_symlink() or CONFIG.stat().st_size>5_000_000:
        raise ValueError("Unsafe v2 configuration snapshot")
    config_bytes=CONFIG.read_bytes()
    if json.loads(config_bytes)!=config:
        raise ValueError("V2 configuration changed after parsing")
    config_hash=hashlib.sha256(config_bytes).hexdigest()
    legacy_path=Path(legacy_generator.__code__.co_filename).resolve()
    legacy_hash=digest(legacy_path)
    registry = ROOT/"program"/"instrument.json"
    if registry.is_symlink() or registry.stat().st_size>1_000_000:
        raise ValueError("Unsafe instrument registry snapshot")
    registry_bytes=registry.read_bytes()
    instrument = json.loads(registry_bytes)
    if tuple(row["midi"] for row in instrument["strings"]) != MIDI:
        raise ValueError("Generator registry differs from the nine-string calibration contract")
    registry_hash = hashlib.sha256(registry_bytes).hexdigest()
    cases = []
    for definition in config["fixtures"]:
        if deadline is not None and time.monotonic() >= deadline:
            raise ValueError("Overall benchmark generation deadline reached")
        directory = output/definition["id"]
        directory.mkdir(mode=0o700)
        signals,truth = generate(definition,config,legacy_generator)
        artifacts = {}
        for component,samples in signals.items():
            path = directory/f"{component}.wav"
            pcm_writer(path,samples,config["sample_rate"])
            artifacts[component] = {"path":str(path.relative_to(output)),"sha256":digest(path),"bytes":path.stat().st_size}
        truth.update(artifacts=artifacts,generator_sha256=generator_hash,configuration_sha256=config_hash,
                     instrument_registry_sha256=registry_hash,
                     legacy_generator_sha256=legacy_hash,
                     source={"path":artifacts["mix"]["path"],"sha256":artifacts["mix"]["sha256"],"sample_rate":config["sample_rate"],
                             "channels":1,"sample_count":truth["sample_count"],"duration_seconds":definition["duration_seconds"],
                             "audio_start_seconds":0.0,"origin_evidence":"synthetic_generator_sample_zero"},
                     rounding="nearest_native_sample",common_component_gain=1.0,
                     component_sum_quantization_error_bound=2/32768)
        if "missing_fundamental" in truth:
            rendered,rate = pcm_reader(directory/"clean.wav",576000)
            truth["rendered_missing_fundamental_verification"] = verify_missing_render(rendered,rate,truth)
        if not definition.get("legacy_v1"):
            start,end = (round(t*config["sample_rate"]) for t in truth["click_only_template_seconds"])
            if any(signals[component][index] != 0 for component in ("clean","noise") for index in range(start,end)):
                raise ValueError("Generated click-only template assertion is false")
            truth["click_template_provenance"] = {"scope":"generator_only","guitar_and_noise_zero":True,
                                                  "source_interval_seconds":truth["click_only_template_seconds"]}
        write_json(directory/"truth.json",truth)
        cases.append({"id":definition["id"],"duration_seconds":definition["duration_seconds"],
                      "truth":str((directory/"truth.json").relative_to(output)),"truth_sha256":digest(directory/"truth.json")})
        del signals
    if digest(Path(__file__)) != generator_hash or digest(CONFIG) != config_hash or digest(registry) != registry_hash or digest(legacy_path)!=legacy_hash:
        raise ValueError("Generator/configuration/registry changed during fixture generation")
    index = {"schema_version":2,"suite":"technical-v2","case_count":len(cases),"total_duration_seconds":120,
             "ground_truth_scope":"generator_only_not_musician","cases":cases,"generator_sha256":generator_hash,
             "configuration_sha256":config_hash,"instrument_registry_sha256":registry_hash,
             "legacy_generator_sha256":legacy_hash,
             "generated_at":datetime.now(timezone.utc).isoformat(),"listening_accepted":False}
    write_json(output/"fixtures.json",index)
    return index
