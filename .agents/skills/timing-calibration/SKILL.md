---
name: timing-calibration
description: Calibrate the capture-latency offset between an in-room acoustic metronome click and amplified distorted nine-string pick attacks from a short operator clip plus mic distances, then write a calibrated phrase-timing view that emits ahead/behind only beyond the stated uncertainty; experimental, analysis only, never a performance grade or missed-note verdict.
---

# Calibrate click-relative phrase timing (experimental draft; not yet admitted)

Hooks `timing_calibration_analyze` and `timing_calibration_apply` are **drafts** in `program/tool-drafts/timing_calibration.json`; root admits them. The worker is `scripts/timing_calibration.py`. Read [the lane contract](../../../docs/spec/sprints/TIMING_CALIBRATION_S3.md) and [the research note](../../../docs/research/2026-10-07-capture-latency-calibration.md) before relying on a record.

**Intent.** A musician woodshedding with an acoustic metronome wants to know whether a phrase was ahead of or behind the click. `phrase_timing` measures onset − click, but that number also contains:

- the path difference between the amp and the metronome to the phone mic (about 2.9 ms per metre);
- any amp-chain latency;
- the detectors' different delays on a click compared with a pick attack.

This tool estimates that capture offset, with a GUM expanded uncertainty (k = 2), from a short calibration clip. It then re-expresses phrase offsets relative to the click as calibrated source-emission offsets. Direction is emitted only when the evidence exceeds the uncertainty.

**Operator protocol (under 3 minutes, same phone, app, room, fan, amp settings, metronome, about 178 BPM, and the same placement as the take; one clip, same day, nothing moved).**

| Step | Time | Action | What it calibrates |
| --- | --- | --- | --- |
| 0 | ≤ 60 s | Measure mic→metronome and mic→amp speaker centre (optionally ear→metronome and ear→amp) | The acoustic path term |
| 1 | 20 s | Click only, strings muted | Click detector bias, the click grid, click detectability |
| 2 | ~12 s | 16 single palm mutes on low C, halfway between clicks, every other click | Palm-muted attack bias |
| 3 | ~22 s | 16 single open notes (including low C), halfway between clicks, muted again, every 4 clicks | Open attack bias (32.70 Hz kept; nothing is filtered) |
| 4 | ~12 s | 16 palm mutes deliberately **on** the click | Consistency check only, never truth |
| 5 | 10 s | Click only again | Grid stability bracket |

Then review the five spans in `SEG.json` (`{"schema_version": 1, "segments": [{"kind", "start_seconds", "end_seconds", "review_text"}]}`, source-timed, kinds `click_only`, `offbeat_palm_muted`, `offbeat_open` and `on_click_palm_muted`). This is the same kind of review as a fan-capture interval. Tip: place the phone about equidistant from the amp speaker and the metronome.

**Knobs.**
- `analyze`:
  - `--distances mic_to_metronome=M,mic_to_amp=M[,ear_to_metronome=M,ear_to_amp=M]`, each in (0, 20] m;
  - `--distance-method measured|estimated`, giving ±0.05 m or ±0.30 m;
  - `--room-temp-c` (±2 °C; when omitted, 15–30 °C is assumed);
  - `--amp-chain analog|declared:MS|unknown`. `unknown` always abstains, so declare `analog` or a value;
  - `--setup-id`, plus optional device, app, metronome and placement labels.
- `apply`: `--phrase-timing`, `--calibration`, `--setup-id`.
- There are no tuning knobs. The decision margin (5 ms), the isolation rules and the fine-onset estimator are frozen (spec §§7 and 10).

**Dependencies.** `rhythm` and `phrase_timing` must have produced the phrase-timing JSON for the take using the **same `rhythm.py`**. The record's `detector_identity.rhythm_sha256` must match the phrase-timing `producer.rhythm_sha256`, or `apply` refuses. FFmpeg/FFprobe come from the `FFMPEG`/`FFPROBE` environment variables. The work is stdlib Python, single-threaded, with a 180 s decode and a 600 s analyze timeout.

**Evidence.**
- The record:
  - `status`: `calibrated` or `abstained`, with closed-enum `abstain_reasons`;
  - `components`: acoustic path, amp chain, detector bias per class with order-statistic CIs, the attack-class hull and the residual floor;
  - `offset_correction_ms`: estimate, expanded U and interval;
  - `consistency_check.played_on_click`;
  - the click grid, including the click's own broadband self-offset;
  - fixed unknowns: `human_intent_is_ground_truth: false`, `phone_input_latency: common_mode_within_one_recording_inference`, `click_identity_in_take: unverified`, `listening_ab: not_performed`, `performance_grading: not_performed`, `audio_written: false`, `filters_applied: []`, `real_take_direction: not_claimed_by_lane`.
- The view copies every phrase-timing entry verbatim under `source_entry` and adds a `calibrated` block:
  - calibrated median;
  - U_phrase = √(U_cal² + (1.858·IQR/√n)²);
  - direction threshold max(U_phrase, 5 ms);
  - `direction`: `ahead_of_click`, `behind_click`, `within_uncertainty` or null;
  - `withheld_basis`.

  Phrases whose onset median coincides (±2.5 ms) with the click's own broadband self-offset are withheld: the measurement may be the click, not the guitar.

**Refusals (typed; nothing is written).** `calibration_record_required`, `calibration_record_invalid`, `calibration_abstained`, `detector_identity_mismatch`, `setup_id_mismatch`, `phrase_timing_schema_unsupported`, `output_under_accepted_runs`. For analyze inputs: `segments_invalid`, `distances_invalid`, `amp_chain_invalid`, `input_invalid`, `audio_too_long`.

**Limits.**
- Direction is a review hypothesis for listening, never a grade, a missed-note claim or a "mistake".
- Legato, tapping and sweeps are uncalibrated. Phrase onsets are unclassified, so the palm/open hull is used.
- Phone signal-dependent processing is unmodelled.
- Placement match is operator-declared. Moving the amp 1.5 m shifts the truth by about 4.4 ms (stress arm E3).
- Never derive ahead/behind from a raw `phrase_timing` offset yourself.
- No real take has been calibrated by this lane, and no real-take direction is claimed.

**Research and iteration.**
- If a record abstains, read `abstain_reasons`:
  - re-record with more clicks or isolated attacks;
  - measure distances instead of estimating them;
  - declare the amp chain;
  - reduce fan masking.

  Do not loosen thresholds.
- If `consistency_check` fails, check the segment spans and whether anything moved.
- Keep every record and view, and compare them across sessions.
- Record listening feedback separately, with its authorship.
