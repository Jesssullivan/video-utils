#!/usr/bin/env python3
"""Create a fresh ignored synthetic S2 practice fixture, never a real take.

The run is the S1 10 s synthetic 32.703 Hz + 130.813 Hz tone run (source name
starts with ``synthetic-``). Synthetic S2 layers sit beside it: tone-ab.json
with three 0.5 s excerpt pairs and a trial file, flags-triage.json (6 flags:
2 shown, 1 suppressed, 3 navigation), two phrase_anchor spans files, a
phrase-timing.json (3 measured rows, 1 abstained) and a detector phrases.json
(3 spans). Every number here is generated UI fixture data, not a measurement
of a recorded guitar performance.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

RATE = 44100
SECONDS = 10
EXCERPT_FRAMES = 22050
EXCERPT_STARTS = (44100, 176400, 308700)


def tone(index):
    time = index / RATE
    return 0.085 * math.sin(2 * math.pi * 32.703 * time) + 0.021 * math.sin(2 * math.pi * 130.813 * time)


def write_pcm16(path, samples):
    data = struct.pack("<%dh" % len(samples), *(int(round(max(-1, min(1, value)) * 32767)) for value in samples))
    write_riff(path, 1, 16, data)


def write_f32(path, samples):
    write_riff(path, 3, 32, struct.pack("<%df" % len(samples), *samples))


def write_riff(path, tag, bits, data):
    block = bits // 8
    fmt = struct.pack("<HHIIHH", tag, 1, RATE, RATE * block, block, bits)
    with open(path, "xb") as stream:
        stream.write(b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(data)) + b"WAVE")
        stream.write(b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")
    return sha(path)


def make_fixture(output, repo=None):
    repo = Path(repo or Path(__file__).resolve().parents[1]).resolve()
    output = Path(output).resolve()
    if not output.is_relative_to(repo / "artifacts") or output.exists():
        raise ValueError("output must be a fresh directory under this worktree's ignored artifacts/")
    run, layers = output / "run", output / "layers"
    run.mkdir(parents=True)
    (layers / "tone_ab").mkdir(parents=True)
    source = [tone(index) for index in range(SECONDS * RATE)]
    variants = {"baseline.wav": 1.0, "source.wav": 1.0, "denoised.wav": 0.97, "processed.wav": 1.12,
                "cleaned.wav": 1.4, "residual.wav": 0.03}
    for name, scale in variants.items():
        write_pcm16(run / name, [value * scale for value in source])
    hashes = {name: sha(run / name) for name in variants}
    source_hash = hashes["baseline.wav"]
    manifest = {"run_id": "synthetic-practice-s2-run", "source": {"path": "synthetic-practice-s2.wav", "sha256": source_hash},
                "timeline": {"audio_start_seconds": 2, "format_start_seconds": 1, "no_time_stretch": True},
                "pcm": {"duration_seconds": SECONDS, "sample_rate": RATE, "sample_count": SECONDS * RATE, "channels": 1},
                "outputs": {"baseline": "baseline.wav", "source": "source.wav", "denoised": "denoised.wav",
                            "processed": "processed.wav", "cleaned": "cleaned.wav", "residual": "residual.wav"},
                "output_sha256": hashes}
    manifest_hash = dump(run / "manifest.json", manifest)
    dump(run / "applied-profile.json", {"schema_version": 1, "name": "synthetic-fuller-profile",
                                        "description": "Synthetic fixture profile; no audio processing occurred."})
    markers = [{"source_time_seconds": 4, "end_seconds": 4.8, "name": "phrase_recurrence_review",
                "confidence": "heuristic_not_probability", "status": "needs_review"}]
    dump(run / "markers.json", {"source_sha256": source_hash, "markers": markers})

    # tone_ab: three excerpt pairs (X/Y blind), plus a whole-take trial file.
    blind = [{"pair": 1, "X": "delivery_master", "Y": "source"}, {"pair": 2, "X": "source", "Y": "delivery_master"},
             {"pair": 3, "X": "delivery_master", "Y": "source"}]
    gains = {"delivery_master": -2.9, "source": -0.2, "trial_lowshelf": -3.1}
    scales = {"delivery_master": 1.4, "source": 1.0}
    pairs = []
    for index, start in enumerate(EXCERPT_STARTS, 1):
        files = {}
        for side in ("X", "Y"):
            arm = blind[index - 1][side]
            factor = scales[arm] * 10 ** (gains[arm] / 20)
            name = f"excerpt-{index}-{side}.wav"
            write_f32(layers / "tone_ab" / name, [source[i] * factor for i in range(start, start + EXCERPT_FRAMES)])
            files[side] = {"file": name, "sha256": sha(layers / "tone_ab" / name), "frames": EXCERPT_FRAMES,
                           "sample_rate": RATE, "channels": 1, "static_gain_db": gains[arm], "level_matched": True,
                           "excerpt_lufs_informational": -20.5 - index * 0.1 - (0.3 if side == "Y" else 0),
                           "sample_peak_dbfs": -18.0 - index * 0.2, "true_peak_dbtp": None}
        pairs.append({"pair": index, "start_sample": start, "end_sample_exclusive": start + EXCERPT_FRAMES,
                      "start_seconds": start / RATE, "center_seconds": (start + EXCERPT_FRAMES / 2) / RATE,
                      "extent_verified": True, "files": files})
    write_f32(layers / "tone_ab" / "trial-lowshelf.wav", [value * 1.45 for value in source])
    reasons = {key: f"Synthetic fixture: {key} is a listening or unmeasured field." for key in
               ("operator_preference", "perceived_fullness", "nasal_quality", "fundamental_32hz_presence",
                "monitoring_device", "true_peak_dbtp", "fan_only_gain", "music_only_gain")}
    tone_ab = {"schema_version": 1, "tool": "tone_ab", "status": "completed",
               "run": {"run_id": manifest["run_id"], "source_sha256": source_hash, "manifest_sha256": manifest_hash,
                       "pcm": manifest["pcm"]},
               "region": {"start_seconds": 0.5, "end_seconds": 9.5, "start_sample": 22050, "end_sample_exclusive": 418950,
                          "sample_rate": RATE},
               "loudness_match": {"match_lu_delta": 0.02, "match_status": "matched", "target_lufs": -21.0,
                                  "meter": "synthetic fixture value (not an FFmpeg loudnorm measurement)",
                                  "per_arm": {arm: {"gain_db": gain} for arm, gain in gains.items()}},
               "excerpts": {"pairs": pairs, "blind_key": blind, "frames_per_file": EXCERPT_FRAMES,
                            "blind_key_notice": "Listen to the X/Y files before reading blind_key.",
                            "operator_preference": None, "format": "native rate/channels f32 WAV"},
               "operator_preference": None,
               "experiment": {"arm": "trial_lowshelf", "status": "rejected_or_unreviewed_trial", "adopted": False,
                              "controls": {"type": "lowshelf", "frequency_hz": 100.0, "gain_db": 1.5, "width": 0.7, "width_type": "q"},
                              "file": "trial-lowshelf.wav", "sha256": sha(layers / "tone_ab" / "trial-lowshelf.wav")},
               "limitations": ["Synthetic fixture excerpts; no listening review exists."],
               "unknown_field_reasons": reasons, "perceived_fullness": None, "nasal_quality": None,
               "fundamental_32hz_presence": None, "monitoring_device": None, "true_peak_dbtp": None,
               "fan_only_gain": None, "music_only_gain": None, "listening_accepted": False, "default_adopted": False,
               "master_changed": False}
    dump(layers / "tone_ab" / "tone-ab.json", tone_ab)

    # Detector phrases (analysis input differs from the tone denoised stage).
    analysis_input = hashlib.sha256(b"synthetic-analysis-input-differs-from-tone-denoised").hexdigest()
    detector_spans = [
        {"start_seconds": 0.5, "end_seconds": 2.0, "kind": "low_register_riff_or_breakdown_candidate", "label": "riff_region_1",
         "confidence": None, "uncertainty": "automatic_region_musical_phrase_interpretation_unverified",
         "source_start_seconds": 2.5, "source_end_seconds": 4.0},
        {"start_seconds": 2.0, "end_seconds": 4.5, "kind": "multifeature_recurrence_candidate", "score": 0.83,
         "uncertainty": "recurrence_estimate_not_approved_intended_score", "source_start_seconds": 4.0, "source_end_seconds": 6.5},
        {"start_seconds": 5.0, "end_seconds": 7.0, "kind": "spectral_texture_region_candidate", "label": "texture_2",
         "confidence": None, "uncertainty": "texture_estimate", "source_start_seconds": 7.0, "source_end_seconds": 9.0}]
    dump(layers / "phrases.json", {"schema_version": 1, "tool": "phrases", "status": "experimental",
                                   "source": {"sha256": analysis_input},
                                   "lineage": {"status": "verified_canonical_derivative", "input_sha256": analysis_input,
                                               "original_source_sha256": source_hash,
                                               "timeline_basis": "hash_matched_canonical_pcm_original_audio_stream_start"},
                                   "observations": {"proposed_review_spans": detector_spans},
                                   "interpretation": {"semantic_phrases": "automatic_feature_hypotheses_no_score_required"}})

    # Arrangement intent spans for two anchors.
    arrangement_hash = dump(layers / "arrangement.json", {"schema_version": 1, "synthetic": True,
                                                         "sections": ["verse", "breakdown", "chorus", "rest", "outro"]})
    for k0, shift in ((3, 0.0), (4, 0.25)):
        units = [("verse:1", "phrase", 2.0, 3.5), ("verse:2", "phrase", 3.5, 5.0), ("breakdown1:1", "breakdown", 5.0, 6.0),
                 ("chorus:1", "phrase", 6.0, 8.0), ("chorus_rest:1", "rest", 8.0, 8.5), ("outro:1", "phrase", 11.5, 12.5)]
        unit_rows = []
        for identifier, kind, start, end in units:
            start, end = start + shift, end + shift
            cover = "within_source" if end <= 12 else ("outside_source" if start >= 12 else "partially_outside_source")
            unit_rows.append({"id": identifier, "kind": kind, "section_id": identifier.split(":")[0], "section_unit_index": 1,
                              "musical_phrase": kind == "phrase", "coverage": cover, "start_source_seconds": start,
                              "end_source_seconds": end, "click_count": 4,
                              "basis": "operator_intent_projected_on_fitted_grid_not_detection", "section_provenance": "operator_supplied"})
        joins = [(2.0, "supported", ["nominal"], "grid_supported", False), (3.5, "supported", ["nominal"], "grid_supported", False),
                 (5.0, "weak", ["nominal"], "grid_weak", False), (6.0, "uncertain", ["breakdown_execution_uncertain"], "grid_supported", False),
                 (8.0, "uncertain", ["uncertain_upstream_breakdown"], "grid_supported", False),
                 (8.5, "uncertain", ["uncertain_upstream_breakdown"], "grid_supported", True)]
        boundaries = [{"id": f"boundary:{index}", "source_seconds": seconds + shift, "join_confidence": join,
                       "structural_status": structural, "coverage": "within_source", "confidence_kind": "heuristic_not_probability",
                       "grid": {"grid_label": grid, "on_interpolated_half_period": half},
                       "checker_cross_reference": {"checker_status": "matched_boundary_candidate" if index < 3 else "no_checker_boundary"}}
                      for index, (seconds, join, structural, grid, half) in enumerate(joins)]
        dump(layers / f"spans-k{k0}.json", {
            "schema_version": 1, "tool": "phrase_anchor", "status": "intent_projection_not_detection",
            "claim_class": "inference_intent_projection_not_detection", "default_adoption": False,
            "click_identity": "unverified", "detector_delay": "uncalibrated", "physical_capture_latency": "uncalibrated",
            "meter": "unknown", "downbeat_confirmed": False,
            "breakdown1_execution": "unknown_operator_reported_possible_rush_or_skip",
            "real_take_phrase_correctness": "unknown_until_operator_marks_boundaries",
            "missed_or_extra_notes": "not_assessed_no_approved_reference", "listening_acceptance": "not_performed",
            "lattice": {"operator_click_period_seconds": 0.25},
            "provenance": {"original_source_sha256": source_hash, "arrangement_sha256": arrangement_hash,
                           "grid_analyzed_input_sha256": analysis_input, "timeline_no_stretch_verified": True,
                           "anchor": {"k0": k0, "status": "review_candidate_not_confirmed_downbeat", "adopted": False}},
            "uncertainty_summary": {"boundary_count": 6, "join_confidence": {"supported": 2, "weak": 1, "uncertain": 3}},
            "limitations": ["Synthetic fixture intent spans; not detected phrases."],
            "units": unit_rows, "boundaries": boundaries})

    # Phrase timing: 3 measured rows and 1 abstained row.
    def timing_row(index, label, start, end, median, tendency):
        measured = median is not None
        return {"phrase_id": f"span-{index}", "label": label, "label_basis": "automatic_review_span",
                "span_source_seconds": [start, end], "click_proximal_onset_count": 6 if measured else 2,
                "median_offset_ms": median, "iqr_ms": [median - 4, median + 3] if measured else None,
                "median_offset_ms_delay_compensated": median - 2.2 if measured else None,
                "iqr_ms_delay_compensated": [median - 6.2, median + 0.8] if measured else None,
                "tendency_label": tendency, "tendency_basis": "median_offset_ms_delay_compensated" if measured else None,
                "status": "measured" if measured else "abstained",
                "abstain_reason": None if measured else "fewer_than_4_click_proximal_onsets"}
    dump(layers / "phrase-timing.json", {
        "schema_version": 1, "tool": "phrase_timing", "status": "experimental_unvalidated_measurement",
        "run_kind": "synthetic_fixture", "real_take_status": "unvalidated_until_operator_spot_check",
        "click_identity": "unverified", "physical_capture_latency": "uncalibrated", "phrase_basis": "automatic_review_span",
        "detector_delay": {"status": "synthetic_probe_medians_applied", "attack_delay_seconds": 0.0023, "click_delay_seconds": 0.0002},
        "inputs": {"analyzed_input_sha256": analysis_input},
        "summary": {"phrase_count": 4, "measured_count": 3, "abstained_count": 1},
        "phrases": [timing_row(0, "riff_region_1", 2.5, 4.0, -12.0, "ahead_of_click"),
                    timing_row(1, None, 4.0, 6.5, 9.5, "behind_click"),
                    timing_row(2, "texture_2", 7.0, 9.0, 1.5, "within_5_ms"),
                    timing_row(3, "INTENT/time estimate: Breakdown 1", 5.0, 6.0, None, None)],
        "limitations": ["Synthetic fixture rows; offsets are generated, not measured from a recording."]})

    # Flags triage: 6 flags = 2 shown + 1 suppressed + 3 navigation.
    def flag(kind, start, end, confidence="unvalidated_automatic_phrase_candidate"):
        return {"kind": kind, "source_time_seconds": start, "end_seconds": end, "confidence": confidence, "status": "needs_review",
                "performance_issue_confirmed": False}
    navigation = [flag("four_pulse_group_review_candidate", seconds, seconds + 1.0, "navigation_proxy_not_confirmed_bar")
                  for seconds in (1.0, 5.0, 9.0)]
    shown = [{"flag_index": 1, "flag_id": "flag-0001-synthetic", "window_id": "grid_+00", "tier": "T2",
              "tier_name": "automatic_recurrence", "selected_evidence_hash_bound": False, "crosses_window_boundary": False,
              "flag": flag("automatic_recurrence_review_candidate", 2.5, 3.5)},
             {"flag_index": 4, "flag_id": "flag-0004-synthetic", "window_id": "grid_+01", "tier": "T3",
              "tier_name": "register_or_ending_texture", "selected_evidence_hash_bound": False, "crosses_window_boundary": False,
              "flag": flag("low_register_riff_or_breakdown_candidate", 6.5, 7.5)}]
    suppressed = [{"flag_index": 2, "flag_id": "flag-0002-synthetic", "window_id": "grid_+00", "tier": "T4",
                   "tier_name": "spectral_texture_region", "selected_evidence_hash_bound": False, "crosses_window_boundary": False,
                   "reason": "lower_priority_in_window", "winner_flag_id": "flag-0001-synthetic",
                   "flag": flag("spectral_texture_region_candidate", 3.0, 4.0)}]
    hidden = [{"flag_index": index, "flag_id": f"flag-000{index}-synthetic", "reason": "navigation_proxy_hidden_by_default",
               "flag": item} for index, item in zip((0, 3, 5), navigation)]
    dump(layers / "flags-triage.json", {
        "schema_id": "video-utils.flags-triage.s2", "schema_version": 1, "source_sha256": source_hash,
        "flags_sha256": hashlib.sha256(b"synthetic-flags").hexdigest(), "manifest_sha256": manifest_hash,
        "timeline": {"axis": "original_source_stream_timestamps_seconds"},
        "window_basis": {"kind": "click_grid_16_period_navigation_windows", "period_seconds": 0.25, "window_seconds": 4.0,
                         "phase_seconds_source": 1.0, "bar_or_downbeat_identified": False,
                         "note": "navigation windows from a periodic transient grid; not bars, phrases or meter"},
        "windows": ["grid_+00", "grid_+01", "grid_+02"],
        "priority_rule": {"id": "flags-triage-priority-v1", "numeric_confidence_used": False, "per_window_shown_maximum": 1},
        "denominators": {"total_flags": 6, "navigation_hidden": 3, "suppressed_lower_priority": 1, "shown": 2,
                         "window_count": 3, "windows_with_shown": 2},
        "shown": shown, "suppressed": suppressed, "hidden_navigation": hidden,
        "view": "default_review_ordering_not_verdict", "musical_verdict": "not_established",
        "listening_acceptance": "not_established"})
    return {"run": str(run), "layers": str(layers), "source_sha256": source_hash, "manifest_sha256": manifest_hash,
            "analysis_input_sha256": analysis_input, "arrangement": str(layers / "arrangement.json"),
            "evidence": "generated_ui_fixture_not_a_recorded_guitar_performance"}


def compose_arguments(fixture):
    """Keyword arguments for practice_s2_bundle.compose over this fixture."""
    layers = Path(fixture["layers"])
    return {"tone_ab": layers / "tone_ab", "flags_triage": layers / "flags-triage.json",
            "detector_phrases": layers / "phrases.json",
            "phrase_spans": [layers / "spans-k3.json", layers / "spans-k4.json"],
            "phrase_timing": [layers / "phrase-timing.json"], "arrangement": layers / "arrangement.json"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(make_fixture(args.output)))
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
