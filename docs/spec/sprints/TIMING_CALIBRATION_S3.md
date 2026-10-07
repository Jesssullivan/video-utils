# S3 timing_calibration lane contract (phase 1 freeze and preregistration)

Lane `timing_calibration`, sprint `20261007-s3`, Linear TIN-5488 (the D4 onsets,
calibrated offsets and drift row). Branch `sprint/20261007-s3/timing_calibration`,
worktree `.local/sprint3/timing_calibration`. Root signs the merge. Authority:

- the approved plan `docs/spec/PROJECT.md`, specifically the D4 row ("calibrated
  offsets/drift") and the S2 status, which records "Per-phrase timing direction on
  the real take is withheld until calibration";
- the operator dialogs in `docs/agent-notes/2026-10-05-user-prompts.md`. Prompt 4
  asks the tool to "identify / mark rhythm issues", and prompt 5 asks it to flag
  where the musician "rushed / miuseed beats". Prompt 6 gives the base metronome
  as "around 178bpm";
- the S2 operator rulings `docs/agent-notes/2026-10-07-s2-operator-rulings.md`
  (phrase_timing descriptor: "measured offsets, direction withheld without
  calibration"; V6 privacy of real-take derivatives);
- the S3 contract `docs/spec/sprints/20261007-S3.md`;
- the repository AGENTS.md and R-HOOK-CONVERGENCE-20261004 (R-N11/R-N12/R-N13).

This file is the lane's frozen contract **and** its preregistration. The commit
that adds it seals the thresholds, tolerances, fixtures, seeds, arms and scoring
rules in sections 5 and 7. Phase 1 ran no numerics, generated no fixture and read
no generated truth. The figures quoted in section 0 were read from existing
committed receipts and an existing gitignored analysis artifact; this lane did not
recompute them. The thresholds below come from analytic error budgets (section
7.6) and were not fitted to any output.

## 0. Problem statement and existing evidence

`scripts/phrase_timing.py` (schema 2) reports a per-phrase signed offset: onset
candidate minus nearest modelled click, both measured in the detector's frame
times. On a real take, `direction` is null with `direction_status:
withheld_uncalibrated` and `physical_capture_latency: "uncalibrated"`
(`docs/spec/sprints/RHYTHM_S2.md` §3.4 and its 2026-10-06 amendment). The reason
is physical. The click is an acoustic metronome in the room, not a DAW track. The
click and the amplified guitar reach the phone or Photo Booth microphone along
different acoustic paths. The onset detectors also respond with different delays
to a click, a palm-muted attack and an open-note attack. A measured
onset-minus-click offset therefore mixes the player's timing with a fixed capture
term:

```
measured_offset = emission_offset
                + acoustic_path_term   ((d_mic_amp - d_mic_metronome) / c)
                + amp_chain_term       (guitar -> amp -> speaker processing latency)
                + detector_bias_term   (b_attack(class) - b_click)
                + residual
```

Device input latency, the ADC, the OS audio buffer and the AAC encoder delay are
**common-mode** within one recording: both sources enter through the same
microphone and the same converter, so this term cancels in the difference. This
is an inference to be qualified in the research note. It does not cover any
signal-dependent processing that the phone might apply.

Existing measurements (M-syn, read, not recomputed):

- Detector delay on synthetic probes, 16 probes per cell, 96/96 cells detected
  (`artifacts/s2/rhythm_clicks/real-take/analysis/analysis.json`,
  `onset_detector_delay_calibration`):
  - `high_frequency_novelty` / `click_3500hz_exp`: median +0.156 ms, IQR
    [−1.016, +1.328] ms.
  - `broadband_rms_novelty` / `distorted_c1_attack`: median +2.344 ms, IQR
    [+1.172, +3.516] ms.
  - `high_frequency_novelty` / `distorted_c1_attack`: median +1.094 ms, maximum
    +13.44 ms.
- Synthetic phrase timing: 48/48 sealed phrases. The per-arm median |error| was
  0.78, 1.69 and 1.37 ms, with acoustic path delay zero by construction
  (`rhythm_clicks-eval-results.json`).
- Real take (M-real, unvalidated): 38/43 arrangement phrases were measured, with
  delay-compensated phrase medians from −19.8 to +16.9 ms. 74/216 click-proximal
  onsets lie within 2.5 ms of an observed high-frequency click candidate, which
  confounds those medians (`rhythm_clicks-real-take.json`, P4_diagnostics).

The lane supplies the missing piece: an operator calibration protocol plus an
analysis that turns those terms into an offset correction with an uncertainty
interval, and a calibrated view that emits direction only when the evidence
supports it.

## 1. Scope

There are four deliverables. All are offline, bounded and stdlib-first. They
analyze only and never write audio. They use source-timed data.

1. **Research note** `docs/research/2026-10-07-capture-latency-calibration.md`.
   It cites primary sources with access dates and states explicit limitations.
   It covers:
   - onset-detection latency and bias by transient type, including rise time and
     perceptual attack time;
   - acoustic path delay (about 2.9 ms/m, with c as a function of temperature);
   - phone and Photo Booth audio input latency, and why it is common-mode within
     one recording;
   - sensorimotor synchronization (negative mean asynchrony), which is why
     "played on the click" is not ground truth;
   - prior art on metronome-relative or beat-relative timing measurement and on
     rhythm-game latency calibration;
   - uncertainty combination (GUM).

   Candidate primary sources to verify in phase 2 (none is cited as verified
   here):
   - Bello et al. 2005, IEEE TSAP 13(5), onset-detection tutorial
   - Dixon 2006, DAFx, "Onset Detection Revisited"
   - Böck, Krebs and Schedl 2012, ISMIR, online onset latency
   - Vos and Rasch 1981 and Gordon 1987, perceptual onset and attack time
   - Repp 2005 and Repp and Su 2013, sensorimotor synchronization reviews
   - Aschersleben 2002
   - Goebl 2001, JASA, onset asynchrony measurement
   - Friberg and Sundström 2002, ensemble timing relative to the beat
   - Cramer 1993, JASA, or ISO 9613-1 for the speed of sound
   - JCGM 100:2008 (GUM)
   - Apple `AVAudioSession.inputLatency` and Android audio-latency documentation

   Each source that cannot be verified is recorded as unverified rather than
   cited.
2. **Operator protocol** (section 4). A guitarist can complete it in under
   3 minutes with the same phone, app, room, amp, metronome and placement as the
   take. It states what each segment calibrates and what stays uncalibrated.
3. **`scripts/timing_calibration.py`**, a closed-schema worker with two
   subcommands:
   - `analyze CALIBRATION_RUN_DIR|FILE --segments SEG.json --distances ... --setup-id ID`
     writes `calibration-record.json` (section 3.1).
   - `apply --phrase-timing PHRASE_TIMING.json --calibration CALIBRATION_RECORD.json --setup-id ID`
     writes a **new** `phrase-timing-calibrated.json` (section 3.2). The input
     phrase-timing file is never modified.

   The module also holds the deterministic synthetic session and take generator
   used by the tests and the sealed evaluation (section 7).
4. **Tests** `tests/test_timing_calibration.py` (section 6), the skill draft
   `.agents/skills/timing-calibration/SKILL.md`, the tool descriptor draft
   `program/tool-drafts/timing_calibration.json`, and dated receipts.

Out of scope:
- processing the real take, or any real-take direction claim
- note-correctness, missed/extra-note or performance-grade verdicts
- tempo, meter or phrase-boundary claims
- adopting a default detector, profile or master, or changing `phrase_timing.py`
  or `rhythm.py`
- catalog, MCP, recipe or skill admission (root-owned)
- physical A/V picture sync
- click-identity verification on the take
- listening acceptance

## 2. Owned files

| File | Change |
| --- | --- |
| `scripts/timing_calibration.py` | new: `analyze`, `apply`, fine-onset reference estimator, uncertainty budget, deterministic synthetic generator, sealed-eval driver |
| `tests/test_timing_calibration.py` | new (section 6) |
| `docs/spec/sprints/TIMING_CALIBRATION_S3.md` | this contract |
| `docs/research/2026-10-07-capture-latency-calibration.md` | new research note |
| `.agents/skills/timing-calibration/SKILL.md` | new skill draft (intent, knobs, dependencies, research, iteration, evidence) |
| `program/tool-drafts/timing_calibration.json` | new descriptor draft for root admission |
| `docs/agent-notes/sprints/20261007-s3/timing_calibration-*.json` | dated receipts (contract freeze, implementation, eval preregistration, eval results, handoff) |

The lane reuses the following read-only, by import, without editing them:
`scripts/rhythm.py` (`envelopes`, `novelty`, `high_frequency_peak_indices`,
`broadband_peak_indices`, `detector_peak_times`, `onset_detector_delay_calibration`,
`decode`, `file_hash`, `atomic_write`, `RATE`, `HOP`) and `scripts/phrase_timing.py`
(`measure`, the schema 2 output). Generated outputs go only under
`artifacts/s2/timing_calibration/` in this worktree (gitignored). Accepted runs
under `artifacts/runs/*`, the original take and `~/Documents` are not
inputs to this lane.

## 3. Output contracts (closed schemas)

Both outputs are closed: the top-level and nested key sets are fixed by this
contract and asserted by tests. An unknown input key is refused with a typed
reason, so it is never silently ignored. Every output carries `schema_version: 1`,
`tool: "timing_calibration"`, producer hashes (`timing_calibration_sha256`,
`rhythm_sha256`, and `phrase_timing_sha256` for apply), a `run_id`, and
`claims {measured[], inferred[], listening: []}`.

### 3.1 `calibration-record.json` (`kind: "capture_latency_calibration_record"`)

**Inputs.**
- `input`. Either:
  - a FILE (WAV/MOV/M4A/MP4, decoded by `rhythm.decode` to 16 kHz mono with FFmpeg
    from the `FFMPEG` env var), or
  - a RUN_DIR containing `denoised.wav` plus `manifest.json`.
  The input's sha256, its kind and the signal chain (`source_audio` or
  `run_denoised` with profile id and manifest sha256) are recorded.
- `--segments SEG.json`: operator-reviewed source-timed spans. Kinds are a closed
  enum:
  - `click_only`: one or more spans, at least 16 isolated clicks in total
  - `offbeat_palm_muted`
  - `offbeat_open`
  - `on_click_palm_muted`

  Each span has `start_seconds`, `end_seconds` and `review_text`.
- `--distances mic_to_metronome=M,mic_to_amp=M[,ear_to_metronome=M,ear_to_amp=M]`.
  Each distance is in metres, bounded to (0, 20].
- `--distance-method measured|estimated`.
- `--room-temp-c T` (optional).
- `--amp-chain analog|declared:MS|unknown`.
- `--setup-id ID`, plus optional `--device-label`, `--app-label`,
  `--metronome-label` and `--placement-note`.

**Fields.**
- `status` ∈ {`calibrated`, `abstained`}. `abstain_reasons[]` is drawn from a
  closed enum:
  - `segment_missing:{kind}`
  - `insufficient_click_events`
  - `insufficient_attack_events:{class}`
  - `click_grid_not_fitted`
  - `distance_out_of_bounds`
  - `expanded_uncertainty_exceeds_decision_margin`
  - `played_on_click_consistency_failed`
  - `decode_failed`

  On `abstained`, the numeric estimate fields are null and the diagnostics stay.
- `capture_setup`: `{setup_id, device_label, app_label, metronome_label,
  placement_note, amp_chain, declared_by: "operator", placement_match_basis:
  "operator_declared_not_measured"}`.
- `distances`: `{values_m, method, per_distance_half_width_m, room_temp_c|null,
  speed_of_sound_interval_m_s}`.
- `reference_definition: "source_emission"`. The primary offset compares pick
  emission at the amp speaker with click emission at the metronome.
  `listener_view` is computed only when both ear distances are given. It is
  arithmetic only and never direction-bearing.
- `components`. Each component carries `{estimate_ms, interval_ms [lo, hi],
  standard_uncertainty_ms, distribution, basis}`:
  - `acoustic_path`: (d_mic_amp − d_mic_metronome)/c, with interval arithmetic
    over the distance half-widths and the c interval.
  - `amp_chain`.
  - `detector_bias`, with per-class entries `click`, `palm_muted_pick_attack` and
    `open_pick_attack`. Each class records:
    - `event_count`, `isolated_event_count`;
    - `detector_minus_fine_median_ms`, with an order-statistic CI;
    - `fine_estimator_synthetic_bias_ms` and its spread;
    - the `synthetic_probe_prior_ms` from `rhythm.onset_detector_delay_calibration()`.

    The entry `legato_tapping_sweep: {status: "uncalibrated"}` is fixed.
  - `attack_class_hull`: the union interval over the two calibrated attack
    classes. It is used because phrase-timing onsets are unclassified.
  - `residual`: a preregistered floor (section 7.6).
- `offset_correction_ms`: `{estimate, expanded_uncertainty_ms (k = 2),
  interval_ms, coverage_factor: 2, combination: "GUM_root_sum_square_of_standard_uncertainties"}`.
  The estimate is acoustic_path + amp_chain + (attack-hull midpoint − click bias).
- `decision_margin_ms: 5.0`, and `abstain_rule: "expanded_uncertainty_ms > decision_margin_ms"`.
- `consistency_check.played_on_click`: `{n, calibrated_median_ms, iqr_ms,
  plausibility_band_ms: [-60, 30], status ∈ {passed, failed, not_available},
  role: "consistency_check_not_ground_truth"}`.
- `click_grid`: per-session period, phase and residual, fitted only on
  `click_only` spans and used to predict masked clicks in `on_click_palm_muted`.
- `detector_identity`: `{rhythm_sha256, rate: 16000, hop: 80, paths:
  ["high_frequency_novelty", "broadband_rms_novelty"]}`.
- Fixed unknowns, which are always present:
  - `human_intent_is_ground_truth: false`
  - `phone_input_latency: "common_mode_within_one_recording_inference"`
  - `av_picture_offset: "not_applicable_audio_only"`
  - `click_identity_in_take: "unverified"`
  - `listening_ab: "not_performed"`
  - `performance_grading: "not_performed"`
  - `expected_rhythm_reference: null`
  - `audio_written: false`
  - `filters_applied: []`
  - `real_take_direction: "not_claimed_by_lane"`

### 3.2 `phrase-timing-calibrated.json` (`kind: "calibrated_phrase_timing_view"`)

**Inputs.** A `phrase_timing` schema 2 JSON and a calibration record. Each must
be a bounded regular `.json` file with no symlink, traversal or URL.

**Refusals.** Refusals are typed and write nothing. The closed enum is:

| Code | Condition |
| --- | --- |
| `calibration_record_required` | the record is missing or unreadable |
| `calibration_record_invalid` | wrong kind or schema, or a closed-schema violation |
| `calibration_abstained` | the record status is not `calibrated` |
| `detector_identity_mismatch` | the record's `rhythm_sha256` differs from the phrase-timing `producer.rhythm_sha256` |
| `setup_id_mismatch` | `--setup-id` differs from `capture_setup.setup_id` |
| `phrase_timing_schema_unsupported` | the phrase-timing file is not schema 2 |
| `output_under_accepted_runs` | the output root is under accepted run directories |

**Fields.**
- `inputs`: `{phrase_timing_path, phrase_timing_sha256, calibration_record_path,
  calibration_record_sha256, setup_id, analyzed_input_sha256}`. Both input hashes
  are re-read after writing and must be unchanged.
- `source_phrase_timing_unmodified: true`.
- `calibration_consumed`: the copied `offset_correction_ms` and
  `decision_margin_ms`.
- `phrases[]`. Each entry is the input phrase entry copied **verbatim** under
  `source_entry`, including `span_source_seconds`, `span_audio_relative_seconds`,
  all measured fields and the original `direction`/`direction_status`. The added
  block is `calibrated`:
  - `basis_field: "median_offset_ms"`. The raw detector-frame median is used,
    never the synthetic-probe-compensated median, so detector bias is not
    counted twice.
  - `calibrated_median_offset_ms` = `median_offset_ms` − correction estimate.
  - `phrase_median_uncertainty_ms` = 1.858·IQR/√n. This is the normal
    approximation 2·1.253·(IQR/1.349)/√n from the phrase's `iqr_width_ms` and
    `click_proximal_onset_count`.
  - `combined_uncertainty_ms` U_phrase = √(U_cal² + U_med²).
  - `direction_threshold_ms` = max(U_phrase, 5.0).
  - `direction` ∈ {`ahead_of_click`, `behind_click`, `within_uncertainty`, null}.
  - `direction_status` ∈ {`calibrated_direction`, `within_uncertainty`,
    `phrase_abstained`}.
  - `listener_view_offset_ms` (null unless the record has a listener view).

  Direction is emitted **only** when |calibrated median| > `direction_threshold_ms`.
  Otherwise it is `within_uncertainty`. A source phrase with `status:
  abstained` gives `direction: null` and `direction_status: phrase_abstained`.
- `direction_meaning`: "sign of the calibrated source-emission offset relative to
  the click; a review hypothesis for listening, never a performance grade".
- Fixed unknowns (all present): the record's fixed unknowns, plus
  `real_take_status` carried from the input and `click_identity: "unverified"`.

## 4. Operator calibration protocol (under 3 minutes)

Use the same phone or Mac, app (Camera or Photo Booth), room, fan state, amp
settings, guitar, metronome model and setting (about 178 BPM) and **placement**
as the take, recorded in one clip on the same day. Do not move the phone,
metronome or amp between this clip and the take. The metronome runs continuously
for the whole clip.

| Step | Time | Action | What it calibrates | What stays uncalibrated |
| --- | --- | --- | --- | --- |
| 0 | ≤ 60 s | With a tape measure, measure mic→metronome and mic→amp speaker centre in metres (also ear→metronome and ear→amp if wanted). If you cannot measure, estimate and choose `estimated` | Acoustic path term (d_mic_amp − d_mic_metronome)/c | Reflections; the exact acoustic centre of the speaker and the metronome |
| 1 | 20 s | **Click only**: metronome running, strings muted with the fretting hand, no picking | Click detector bias on the *real* click (detector frame time vs fine-onset reference), click grid period and phase, room noise floor and click detectability | Click identity in the later take (assumed the same metronome) |
| 2 | ~12 s | **Offbeat palm mutes**: 16 single palm-muted attacks on the low C string, each halfway between two clicks, on every other click | Palm-muted attack detector bias, isolated from click masking | Chords, gain changes, other strings |
| 3 | ~22 s | **Offbeat open notes**: 16 single open-string attacks (mix of low C and higher strings), halfway between clicks, muted again before the next attack (one attack every 4 clicks) | Open-attack detector bias; includes 32.7 Hz content (no high-pass) | Legato, tapping, sweeps (`uncalibrated` by design) |
| 4 | ~12 s | **On the click**: 16 single palm-muted attacks deliberately ON the click, every other click | **Consistency check only**: the calibrated median must fall in the plausibility band; spread estimates sync noise | **Not ground truth**: human sensorimotor synchronization typically anticipates the click (negative mean asynchrony), so this segment cannot set the offset |
| 5 | 10 s | **Click only** again | Bracket: click grid stability across the clip | — |

The total recording time is about 76 s. With the measurements and setup, the
protocol takes under 3 minutes. The operator then reviews and records the five
segment spans in `SEG.json`, just as a capture interval is reviewed, before
running `analyze`.

**How human intent is handled.** The offset estimate never uses segment 4. The
correction combines three things:
- the acoustic path computed from the distances;
- the declared amp-chain term;
- the detector-bias difference. This is measured on the real click and the real
  isolated attacks against a fine-onset reference, whose own bias per transient
  class is fixed from synthetic probes (section 7.6).

Segment 4 can only *fail* a calibration, when its calibrated median lies outside
[−60, +30] ms. Such a value suggests a wrong segment, a half-period association
or moved equipment. Segment 4 can never pass or tune a calibration.

**Recommendation in the protocol text.** Place the phone about equidistant from
the metronome and the amp speaker. The acoustic path estimate then shrinks
towards zero; the distance half-widths still contribute to the uncertainty.

## 5. Completion metrics and claim classes

Claim classes:
- **M-syn**: a measurement on a generated fixture against generator truth.
- **M-real**: a real-take measurement. **None in this lane.**
- **I**: an inference.
- **L**: a listening claim. **None in this lane.**

| # | Metric (denominator) | Class | Acceptance (preregistered) |
| --- | --- | --- | --- |
| T1 | Acoustic path arithmetic: 4 geometry cases (equal, amp farther, metronome farther, measured vs estimated) | M-syn | estimate within 0.01 ms of analytic; truth inside the interval in 4/4 |
| T2 | Detector bias recovery on dev sessions: 3 dev seeds × 3 classes (click, palm-muted, open) = 9 | M-syn | \|estimated b − generator-truth b\| ≤ 1.0 ms in 9/9 (truth = median of detector time − true onset over isolated events) |
| T3 | End-to-end dev: 3 dev seeds × 6 phrases = 18 phrases, arm E1 | M-syn | median \|calibrated median − truth δ\| ≤ 3.0 ms |
| T4 | Low-register detection without high-pass: offbeat open attacks on C1 (32.70 Hz) only, 16 per dev seed × 3 | M-syn | detected ≥ 12/16 per seed (the existing `DELAY_MINIMUM_DETECTIONS`) |
| S1 | Sealed E1 (measured distances), section 7: calibration status over 8 cases; phrases 8 × 6 = 48 | M-syn | calibrated ≥ 7/8; per-arm median \|error\| ≤ 3.0 ms over 48 (abstained phrases or cases count as failures, ∞); coverage (truth δ within calibrated median ± U_phrase) ≥ 0.90 over measured phrases, reported with the denominator |
| S2 | Sealed E2 (estimated distances, injected distance error within the declared half-width) | M-syn | abstention count over 8 reported (no pass bound); on calibrated cases median \|error\| ≤ 3.0 ms and coverage ≥ 0.90, with denominators |
| S3 | Direction correctness over E1 ∪ E2 | M-syn | sign-correct / emitted ≥ 0.95; emissions on on-time phrases (\|δ\| ≤ 2 ms) = 0 over their count; emission rate on \|δ\| ≥ 15 ms phrases reported (predicted ≥ 0.75 for E1) |
| S4 | Sealed E3 stress (placement changed after calibration: amp moved 1.5 m farther) | M-syn | reported only (error, coverage, wrong-sign count); demonstrates the operator-declared placement limit; no pass bound |
| A1 | Abstention battery: (a) click-only < 16 isolated clicks; (b) estimated distances with `amp_chain unknown`, so U ≥ 5.77 ms exceeds the margin by construction; (c) click masked by fan noise (click SNR ≤ −6 dB); (d) segment 4 played on the offbeat but declared on-click (\|median\| ≈ P/2) | M-syn | 4/4 `abstained` with the expected reason; numeric estimates null |
| R1 | Apply refusals: no record, abstained record, detector-identity mismatch, setup-id mismatch, schema-1 phrase timing, output under `artifacts/runs` | M-syn | 6/6 typed refusals; no file written |
| P1 | Preservation: phrase-timing input sha256 before = after apply; every `source_entry` equals the input entry (including `span_source_seconds`) | M-syn | 100 % of phrases over all apply tests |
| P2 | Analysis only: the input audio sha256 is unchanged; outputs are JSON only; `audio_written: false`, `filters_applied: []` | M-syn | 100 % |
| P3 | Closed schema and unknowns: exact key sets; every section 3 fixed unknown present; recursive scan finds no `missed`, `extra_note`, `wrong_note`, `mistake`, `error_verdict` token | M-syn | 100 % |
| G1 | Regression: `test_phrase_timing` and `test_rhythm` pass unchanged (the lane edits neither module) | — | 100 % |

Experimental non-improvement is valid completion when it is reported with
denominators, for example an S1 coverage < 0.90 or an E2 abstaining in 8/8. No
threshold, tolerance or arm is changed after sealed seeds are run. Nothing is
adopted as a default, and the existing `phrase_timing` real-take policy stays
`withheld_uncalibrated` until root admits this tool and an operator calibration
record exists.

## 6. Test protocol

Run from the worktree root with FFmpeg exported
(`FFMPEG=/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffmpeg`,
`FFPROBE=…/ffprobe`) and stdlib `python3`, with no installs:

```
PYTHONPATH=tests python3 -m unittest test_timing_calibration -v   # T1-T4 A1 R1 P1-P3 (+ S1-S4 when sealed env set)
PYTHONPATH=tests python3 -m unittest test_phrase_timing test_rhythm -v   # G1
TIMING_CALIBRATION_S3_SEALED_EVAL=1 PYTHONPATH=tests timeout 1800 python3 -m unittest test_timing_calibration.SealedEvaluationTests -v   # once, after the eval commit
```

Test classes in `tests/test_timing_calibration.py`:
- `AcousticPathTests` (T1)
- `DetectorBiasTests` (T2, T4)
- `EndToEndDevTests` (T3)
- `AbstentionTests` (A1)
- `ApplyRefusalTests` (R1)
- `PreservationTests` (P1, P2)
- `SchemaAndTokenTests` (P3)
- `SealedEvaluationTests` (S1–S4), which is skipped unless the env var is set

Only one CLI test decodes through FFmpeg, on a generated 16 kHz WAV under a
temp dir. It is skipped with a reason when `FFMPEG` is unset. Every other test
calls the pure functions `analyze_samples(...)` and `apply_view(...)`. All
fixtures are generated in-process; there are no media files, and no real-take
derivative is read by the tests.

**Fixture generator** (`timing_calibration.synthetic_session` / `synthetic_take`):
- 16 kHz mono.
- Colored fan-like noise: amplitude U[0.004, 0.012], AR coefficient U[0.55, 0.85].
- Click models, a closed set:
  - `click_3500hz_exp`: the existing probe shape, amplitude U[0.06, 0.12].
  - `mechanical_wood_click`: a 4 ms white-noise burst × exp(−t/0.8 ms) through
    a two-pole resonator at 2.2 kHz, Q 6, normalised to the same peak range.
- Guitar attacks use the existing distorted model:
  - tanh drive 2.6–4.6 and 1.5 ms rise;
  - palm mute τ 15–40 ms, open τ 250–400 ms with 0.6 s sustain decay;
  - notes from tuning MIDI {24, 29, 34, 39, 46, 51, 56, 60, 65}, always including
    C1 = 32.70 Hz in the open segment;
  - no high-pass.
- The whole guitar signal is delayed by the integer-sample-rounded acoustic path
  Δ = (d_mic_amp − d_mic_metronome)/c_true, plus the amp-chain term (0 for
  `analog`).
- Session segments follow section 4. Segment 4 attacks sit at click + μ_player +
  N(0, σ_player), with μ_player and σ_player hidden from `analyze`.
- Take phrases reuse the `test_phrase_timing.phrase_fixture` layout:
  - 8 click-aligned attacks per phrase at click + Δ + δ_phrase + N(0, 3 ms);
  - 4 off-click subdivision attacks;
  - one masking attack;
  - palm-muted or open per attack, at random.

  The take is analyzed with `rhythm.analyze`, then `phrase_timing.measure(...,
  run_kind="synthetic_fixture")`, then `apply_view`. Truth δ is the median of the
  sample-rounded generated emission offsets of the 8 aligned attacks.

## 7. Preregistration (sealed by this commit)

1. **Dev seeds.** Dev seeds 11, 12 and 13 use namespace
   `timing-calibration-s3-dev:{seed}:{arm}:{knob}`. They are for implementation
   and the T-metrics only.
2. **Sealed eval seeds.** Seeds 5501–5508 use namespace
   `timing-calibration-s3-eval:{seed}:{arm}:{knob}`, with each knob drawn as
   `int(sha256(namespace)[:16], 16) / 2**64`. Per case:
   - d_mic_metronome and d_mic_amp ∈ U[0.3, 3.0] m;
   - true room temperature ∈ U[18, 24] °C, with c = 331.3·√(1 + T/273.15);
   - period ∈ {60/178, 0.6757, 60/150} by knob;
   - click model `click_3500hz_exp` for odd seeds and `mechanical_wood_click` for
     even seeds;
   - μ_player ∈ U[−40, +10] ms and σ_player ∈ U[4, 12] ms;
   - noise and click knobs as in section 6;
   - 6 take phrases: 2 on-time (δ ∈ U[−2, +2] ms), 2 ahead (δ ∈ U[−30, −8]
     ms) and 2 behind (δ ∈ U[+8, +30] ms), in an order permuted by knob.
3. **Arms.** All arms use the same frozen estimator.
   - **E1**: measured distances equal to truth, `--distance-method measured`,
     `--room-temp-c 21`.
   - **E2**: estimated distances, each truth + U[−0.25, +0.25] m (inside the
     declared ±0.30 m), `--distance-method estimated`, no temperature.
   - **E3**: E1 calibration, applied to a take whose amp is 1.5 m farther from
     the mic (stress test, reported only).
4. **Scoring.**
   - Per arm: median over phrases of |calibrated median − truth δ|.
     Calibration abstentions and phrase abstentions count as ∞ in that median
     and are reported separately.
   - Coverage = the fraction of measured phrases with truth δ ∈ calibrated
     median ± U_phrase.
   - Direction: sign-correct over emitted directions; emissions on on-time
     phrases; emission rate on |δ| ≥ 15 ms phrases.
   - Rates are always pooled counts over denominators, never averages of
     per-case rates.
5. **Sealing procedure.**
   - Dev fixtures may guide implementation. The fine-onset estimator and the
     isolation rules may change during development and freeze at the evaluation
     commit, as in RHYTHM_S2 §3.1.
   - Before any sealed run, the lane commits the implementation and writes
     `docs/agent-notes/sprints/20261007-s3/timing_calibration-eval.json`. It
     records that commit sha, the sha256 of `timing_calibration.py`, `rhythm.py`
     and `phrase_timing.py`, the seeds and the exact commands.
   - The sealed run executes once.
   - A post-eval code change cannot be rescored on these seeds. Any rerun needs
     newly preregistered seeds, and both results are reported. No threshold,
     tolerance or arm is tuned on held-out seeds.
6. **Thresholds and error budget.** These are analytic, not fitted.
   - **Decision margin.** 5.0 ms, equal to the existing `phrase_timing.WITHIN_MS`.
     The calibration abstains when expanded U (k = 2) > 5.0 ms.
   - **Distance half-widths.** Measured ±0.05 m; estimated ±0.30 m. Each is
     treated as uniform: u = hw/√3.
   - **Speed of sound.** c(T) = 331.3·√(1 + T/273.15) m/s. With a declared
     temperature, T ± 2 °C; otherwise T ∈ [15, 30] °C.
   - **Amp chain.**
     - `analog`: 0 ± 0.1 ms
     - `declared:X`: X ± 0.5 ms
     - `unknown`: uniform [0, 10] ms (u ≈ 2.89 ms, so expanded U ≥ 5.77 ms and
       the calibration always abstains; the operator must declare `analog` or a
       value)
   - **Residual floor.** Uniform ±1.0 ms covers reflections and unmodelled
     terms.
   - **Detector-bias statistical term.** The half-width of the narrowest
     symmetric order-statistic CI of the median with binomial coverage ≥ 0.95,
     divided by 1.96. The minimum isolated events are 16 clicks and 12 of 16
     attacks per class.
   - **Fine-onset estimator.**
     - Initial definition: |x| smoothed by an 8-sample (0.5 ms) moving average.
     - Floor = the median over [−60, −20] ms before the detector event.
     - Peak = the maximum over [−10, +40] ms.
     - Onset = the first crossing of floor + 0.2·(peak − floor), searching
       forward from detector time − 15 ms.
     - Its per-class synthetic bias table comes from the fixed probe set: the
       three `rhythm.DELAY_PROBES`, plus `mechanical_wood_click` and an
       open-sustained C1 probe, at the 16 sub-hop offsets, noise-free. It is
       never computed from eval seeds. The spread term is the half-range over
       those probes, treated as uniform.
   - **Isolation.** No other detector event within ±150 ms of the event.
   - **Plausibility band.** [−60, +30] ms for segment 4. It is wide because
     sensorimotor-synchronization studies report anticipation of tens of
     milliseconds, to be verified in the research note.
   - **Combination.** Expanded U_cal = 2·√(Σ u_i²) over the acoustic, amp,
     click-bias, attack-hull and residual terms (GUM). The attack-hull standard
     uncertainty is the hull half-width/√3, plus the larger class statistical u
     in quadrature. U_phrase = √(U_cal² + U_med²).
   - **Analytic expectation.** These are rough u values in ms, inferred, not
     measured.
     - Each estimated distance contributes 0.51 and each measured one 0.10.
     - The residual contributes 0.58 and the analog amp 0.06.
     - The click and attack statistical terms contribute about 0.5–0.8 each.
       The attack-class hull contributes about 0.3–0.6.
     - Expected U_cal: measured distances about 2.0–3.0 ms, estimated distances
       about 2.5–3.8 ms. Both usually calibrate, and wide detector CIs can push
       either over 5 ms. That abstention is recorded honestly rather than tuned
       away.
     - End-to-end median |error|: about 1–2 ms, from the 3 ms jitter, the
       ±2.5 ms frame quantization and the bias CIs. Hence the 3.0 ms tolerance.

## 8. Root-owned changes requested (not made by the lane)

- **Tool admission.** Admit `timing_calibration_analyze` and
  `timing_calibration_apply` from `program/tool-drafts/timing_calibration.json`
  into `program/tools.json` and `scripts/tool_api.py`, with an MCP hook in
  `scripts/mcp_server.py` and closed schemas copied from section 3. Status is
  `experimental`, with no default adoption. The exact descriptor text goes in the
  phase-2 handoff's `root_owned_changes_requested`.
- **Recipes** (`just/workflow.just`):
  - `timing-calibration-analyze INPUT SEGMENTS DISTANCES METHOD AMP_CHAIN SETUP_ID OUTPUT_ROOT`
  - `timing-calibration-apply PHRASE_TIMING CALIBRATION SETUP_ID OUTPUT_ROOT`

  Both have a 600 s timeout and FFmpeg from the env vars.
- **Skill admission.** The root-side counterpart of
  `.agents/skills/timing-calibration/SKILL.md` (prompt registry and pin, if the
  admission tests require one).
- **Skill wording.** A wording update to `.agents/skills/guitar-phrase-timing/SKILL.md`
  (not lane-owned) pointing to the calibrated view. `phrase_timing.py`'s
  `DIRECTION_POLICY.operator_calibration_input_supported` stays `false`, because
  the calibrated view is a separate artifact, not an input to `phrase_timing`.
- **Linear.** Root records the lane state on TIN-5488. The lane writes no
  tracker entries.

## 9. Bounds and doctrine

- Stdlib only. Single thread. One heavy job at a time. Explicit timeouts: FFmpeg
  decode 180 s; `analyze` 600 s; sealed eval 1800 s.
- Inputs are bounded: audio ≤ 600 s, JSON ≤ 64 MiB.
- No downloads, daemons, Linear writes, writes to `artifacts/runs/*`, the
  original take, `~/Documents` or `~/Desktop`.
- No blanket high-pass, mains notch or filter of any kind; the worker analyzes
  only. Fixtures retain 32.70 Hz content, and T4 checks low-register attack
  detection.
- The arrangement's 404 clicks and phrase lengths are intent, never a detection
  count, and this lane does not use them. First-five-second setup sounds are not
  treated as noise-only.
- Real-take derivatives stay private under V6. This lane creates none.

## 10. Phase 2 implementation clarifications (frozen at the eval commit, before any sealed run)

Section 7.5 allows the fine-onset estimator and the isolation rules to change during
development on dev seeds 11–13, and freezes them at the evaluation commit. The items
below were settled on dev fixtures only. No sealed seed was generated or run before
this section was committed. Thresholds, tolerances, seeds, arms and scoring in
sections 5 and 7 are unchanged.

1. **Isolation (changed from 150 ms).** An event is isolated when no other same-path
   detector event lies in the preceding 100 ms, and no *stronger* same-path event lies
   in the following 100 ms. Reason, measured on dev seeds: the symmetric 150 ms rule
   rejected offbeat attacks whose player jitter brought them within 150 ms of the next
   click, and it also rejected sustain-ripple peaks of low-C open notes (32.70 Hz).
   That left 7–11 of 16 valid attacks per class, below the 12 minimum. The 100 ms
   window still covers the fine-onset windows ([−60, +40] ms).
2. **Association.**
   - Clicks: one high-frequency event per grid beat within ±min(25 ms, 0.1·P), from
     the `click_only` spans only.
   - Offbeat attacks: the earliest broadband event per half-beat slot, within
     ±0.25·P of the half-beat. Its novelty must be at least 1.5× the 95th percentile
     of broadband novelty peaks in the `click_only` spans, so that a click's own
     broadband event is not taken as an attack.
   - `on_click_palm_muted`: for each beat, the magnitude-qualified broadband event
     nearest the predicted click. A status needs at least 8 events; otherwise it is
     `not_available`.
3. **Click grid.**
   - The seed is the median inter-onset interval in the longest `click_only` span.
   - Beat indices are counted incrementally from consecutive intervals. Least
     squares then runs over all `click_only` spans with three MAD rejection passes,
     each with a floor of 12 ms.
   - A grid is fitted only when there are ≥ 8 retained events, the median |residual|
     is ≤ min(25 ms, 0.05·P), and each span with ≥ 4 candidates has coverage ≥ 0.5.
   - The shift in median residual between the first and last span is reported as the
     bracket check.
4. **Fine-onset estimator details.**
   - The 8-sample mean of |x| is trailing (causal).
   - The threshold crossing is linearly interpolated between samples.
   - An event is invalid when it is already above threshold at det − 15 ms, or when
     the peak is ≤ 1.5× the floor.
   - The probe table classes are: `click` ← {unit_impulse, click_3500hz_exp,
     mechanical_wood_click}; `palm_muted_pick_attack` ← distorted_c1_attack;
     `open_pick_attack` ← open_sustained_c1 (C1, τ 300 ms, drive 3.5). Each class bias
     is the midpoint of [min, max] of (fine − true) over its probes × 16 sub-hop
     offsets.
5. **Class standard uncertainty.** u_class = √(u_orderstat² + (fine half-range/√3)²
   [+ (2.5 ms/√3)² when sub-hop phase-locked]). The fine-estimator spread is added in
   quadrature, which is conservative.
   - "Phase-locked" means the circular resultant of the fine onsets' sub-hop phase
     is ≥ 0.9. This happens, for example, when the click period is an exact multiple
     of the 80-sample hop (P = 0.4 s).
   - In that case the take's click phase relative to the hop cannot be assumed to
     match the session's, so the uniform ±half-hop term is added.
6. **Generator realism (section 6).**
   - Offbeat attacks carry player jitter N(0, σ_player).
   - Session and take start at a knob-drawn sub-hop offset (`session_sub_hop`,
     `take_sub_hop`).
   - The session lead is 0.5 s and the gap between segments is 2 beats.
   - Open notes are muted after 2.5 periods with a 10 ms release.
   - All waveforms keep their 32.70 Hz content; nothing is filtered.
7. **Click-coincidence guard in `apply` (stricter; can only withhold).**
   - The dev seeds showed that on "behind" phrases, `phrase_timing`'s nearest-onset
     rule can measure the click's own broadband event (offset ≈ 0) instead of the
     later guitar attack. Before the guard, E1 had 2 wrong-sign emissions over 11
     emitted directions.
   - The record therefore measures `click_grid.click_broadband_self_offset` (the
     median broadband-path offset of clicks relative to the grid in `click_only`
     spans; n ≥ 8).
   - `apply` withholds a phrase with `direction: null`, `direction_status:
     phrase_abstained` and `withheld_basis:
     onset_median_coincides_with_click_self_detection` when |median_offset_ms −
     self offset| ≤ 2.5 ms.
   - Withheld phrases score as ∞ in the error median and are excluded from the
     coverage denominator, as section 7.4 does for phrase abstentions.
   - This is a property of `phrase_timing` (not lane-owned), reported for root.
8. **Closed key sets** are the constants `RECORD_KEYS`, `COMPONENT_KEYS`,
   `CLASS_KEYS`, `OFFSET_KEYS`, `CONSISTENCY_KEYS`, `VIEW_KEYS` and `CALIBRATED_KEYS`
   in `scripts/timing_calibration.py`. They are asserted by `SchemaAndTokenTests`.
   Keys added beyond section 3 are all additive diagnostics:
   - record and view: `limitations`, `rules`, `summary`;
   - offset block: `attempted_estimate`, `attempted_expanded_uncertainty_ms`,
     `standard_uncertainty_budget_ms`;
   - consistency block: `used_in_offset_estimate: false`;
   - calibrated block: `withheld_basis`;
   - class block: `valid_fine_onset_count`, `ci_order_statistics`, `ci_coverage`,
     `sub_hop_phase_resultant`, `sub_hop_phase_locked`, `bias_estimate_ms`,
     `standard_uncertainty_ms`, `interval_ms`.
9. **Abstention and refusals.**
   - A decode failure yields an abstained record with `decode_failed`.
   - Analyze input errors are typed refusals that write nothing: `segments_invalid`,
     `distances_invalid`, `amp_chain_invalid`, `input_invalid`, `audio_too_long`.
   - SEG.json is closed: `{schema_version: 1, segments[], source_sha256?, note?}`.
     Each span has exactly `{kind, start_seconds, end_seconds, review_text}`, and
     spans must not overlap.
10. **Dev-seed results (M-syn, dev seeds 11–13, not sealed).**
    - T2: 9/9 class biases within 1.0 ms of generator truth, maximum deviation
      ≈ 0.21 ms.
    - T3 (E1): median |error| 1.90 ms over 18 phrases, with 5 withheld counted as ∞.
      Over the 13 measured phrases it is 1.09 ms, with coverage 13/13 and 8 emitted
      directions, all sign-correct.
    - T4: 16/16 C1-only open attacks per seed.
    - A1: 4/4 abstained with the expected reason.

## 11. Post-eval fix R2 (after the sealed run; evaluated only on new seeds)

**R1 result.** The single sealed run at eval commit `4ad7e01` is recorded in
`timing_calibration-eval-results.json`.
- **S1 failed:** E1 calibrated 4/8, and the median |error| over 48 phrases is ∞.
- Every abstention was `click_grid_not_fitted`.
- Where a grid fitted:
  - median |error| was 1.08 ms (E1) and 1.07 ms (E2);
  - coverage was 17/18 (E1) and 18/18 (E2);
  - sign-correct was 34/34;
  - emissions on on-time phrases were 0/24.

Seeds 5501–5508 are **not rescored**.

**Diagnosis** (read-only, unchanged code). In `click_only` spans the
high-frequency peak picker passes fan-noise peaks, 2–10× as many as there are clicks,
because no attack sets its adaptive maximum. The median-IOI seed then comes from
spurious intervals. The failure reproduced on extra dev seeds 14, 16 and 20 (dev
namespace).

**Change.** High-frequency peaks in each `click_only` span are kept only when their
novelty is ≥ 0.3 × the median of the strongest ceil(span_seconds / 2) peaks. The
strongest peaks are clicks at any tempo ≥ 30 BPM. These strong events feed:
- the grid seed and fit;
- click association;
- click isolation.

The change was developed on dev seeds 11–21 only: 11/11 grids fitted, and the extra
dev seeds 14, 16 and 20 gave E1 3/3 calibrated, 0 wrong signs and coverage 13/14.
All dev tests pass (25, 1 skipped).

**R2 preregistration.** The R2 seeds are 5601–5608 in the same
`timing-calibration-s3-eval:{seed}:{arm}:{knob}` namespace. They use the same arms,
thresholds, tolerances and scoring (sections 5 and 7). R2 runs once at the commit
recorded in `timing_calibration-eval-r2.json`, through
`SealedEvaluationR2Tests` with `TIMING_CALIBRATION_S3_SEALED_EVAL_R2=1`. Both R1 and
R2 are reported.
