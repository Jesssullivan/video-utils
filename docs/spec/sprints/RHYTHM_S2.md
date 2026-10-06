# S2 rhythm_clicks lane contract (phase 1 freeze)

Lane `rhythm_clicks`, sprint `20261006-s2`, Linear TIN-5602 (parent TIN-5599).
Branch `sprint/20261006-s2/rhythm_clicks`, worktree `.local/sprint2/rhythm_clicks`;
root signs the merge. Authority: the repository AGENTS.md and
R-HOOK-CONVERGENCE-20261004 (R-N11/R-N12/R-N13). This file is the lane's frozen
contract **and** its preregistration: the commit that adds it seals the arms,
seeds, scoring rules and thresholds below. Phase 1 ran no numerics. The
thresholds come from analytic noise estimates (5 ms analysis hop, uniform ±2.5 ms
frame quantization, σ≈1.44 ms) and were not fitted to any output.

## 1. Scope

There are four deliverables. All are offline, bounded, stdlib-first and source-timed.

1. **Click-grid drift model** (`scripts/rhythm.py`). This is an additive
   `linear_period` fit of the detected periodic high-frequency transient train:
   the instantaneous inter-click interval is a linear function of click time.
2. **Detector delay calibration** (`scripts/rhythm.py`). Synthetic probes pass
   through the 16 kHz envelope → novelty → peak path that `analyze()` actually
   uses. The delay is recorded but never applied to existing timestamps.
3. **Attack-preservation A/B** (`scripts/click_attack_ab.py`, new). Synthetic
   coincident and isolated click/attack fixtures run through the existing
   `clicks.experiment` attenuation. The output reports attack energy and
   centroid deltas with denominators. The real take is detection-only.
4. **Per-phrase onset offset relative to the in-recording click**
   (`scripts/phrase_timing.py`, new). Each phrase gets the median, IQR and count
   of guitar-onset offsets from the nearest modelled click, with explicit
   abstention.

Out of scope: tempo/meter/phrase-boundary claims, missed/extra/wrong-note
claims, performance grading, default detector/profile/master adoption, product
tool admission (catalog, MCP and skills are root-owned), physical A/V latency,
and listening acceptance.

## 2. Owned files

| File | Change |
| --- | --- |
| `scripts/rhythm.py` | additive drift fit, delay calibration, per-event compensated field |
| `scripts/clicks.py` | at most additive pass-through of `click_grid_drift` and delay calibration in the no-template path; attenuation logic unchanged |
| `scripts/click_attack_ab.py` | new experimental helper, not a catalog tool |
| `scripts/phrase_timing.py` | new experimental helper, not a catalog tool |
| `tests/test_rhythm.py`, `tests/test_clicks.py` | existing tests unchanged in meaning; new classes appended |
| `tests/test_click_attack_ab.py`, `tests/test_phrase_timing.py` | new |
| `docs/spec/sprints/RHYTHM_S2.md` | this contract |
| `docs/agent-notes/sprints/20261006-s2/rhythm_clicks-*.json` | dated receipts (implementation, evaluation, real-take) |

Generated outputs go only under `artifacts/s2/rhythm_clicks/` (gitignored).
Accepted run directories under `artifacts/runs/*` are read-only inputs.

## 3. Output contracts (additive JSON only)

Existing keys keep their names, types and meaning. Two existing `analysis`
values change from placeholders to measurements, as the definition of done
requires. No consumer outside `rhythm.py` reads them (checked by grep at
freeze). `events.csv` columns are **unchanged**.

### 3.1 `analysis.json` drift

The drift object always appears at top level as `click_grid_drift`. When the
constant grid is non-null, the identical object is also at `click_grid.drift`.
A strongly drifting train can make the constant fit abstain (`click_grid: null`),
so the top-level mirror carries the estimate in that case. `click_grid` is never
synthesized from the drift fit.

Fields of `click_grid_drift`:

- `model: "linear_period"`: IOI(t) = P0 + r·t; positions are
  t_b = t0 + (P0 + r·t0)·((1+r)^b − 1)/r (→ b as r→0). The fit is a bounded
  1-D search over r ∈ [−0.05, 0.05] s/s, with closed-form least squares for
  (t0, P0) and up to three outlier-rejection passes with threshold
  max(12 ms, 3×1.4826×MAD).
- `period_change_per_second` (r, s/s); `drift_ppm` = 1e6·r / P(t_ref)
  (**ppm of the reference period per second**, invariant to pulse level);
  `drift_ppm_standard_error`; `reference_time_seconds_audio_relative` (midpoint
  of the retained span); `period_at_reference_seconds`;
  `period_at_first_event_seconds`; `period_at_last_event_seconds`;
  `total_period_change_fraction`.
- `residual_ms_rms`, plus `constant_period_residual_ms_rms` on the same retained
  events for comparison.
- `candidate_event_count`, `retained_event_count`, `rejected_event_count`,
  `beat_span`, `coverage`, `pulse_divisor` (1, 2 or 3 relative to the seed),
  `seed_period_seconds`, `seed_provenance`.
- `status` ∈ {`fitted`, `insufficient_events` (fewer than 6 retained events),
  `no_periodic_seed`, `fit_residual_exceeds_bound` (rms > 15 ms)}. Numeric
  estimate fields are non-null **only** when `status == "fitted"`; diagnostics
  remain.
- `confidence_label` ∈ {`strong_drift_evidence`, `limited_drift_evidence`,
  `no_material_drift_evidence` (|drift_ppm| ≤ 3·SE), `not_estimated`}, with
  `confidence_kind: "heuristic_not_probability"`.
- `identity: "periodic_high_frequency_transients_not_verified_metronome"` and
  `interpretation`. The fit does not separate mechanical-metronome wind-down,
  device clock or detector bias.

Event acquisition reuses the high-frequency novelty peaks and thresholds of
`fit_click_grid`. A seeded tracker (constant-grid period, else selected
periodicity, else declared BPM) accepts the nearest peak within ±12 % of the
local period and stops after 3 consecutive misses. It tries pulse divisors 1, 2
and 3, keeps periods ≥ 0.25 s, and selects the fastest divisor with coverage
≥ 0.7. Implementation details may change during development. They freeze at the
evaluation commit (§7).

### 3.2 `analysis.json` detector delay

- `analysis.onset_detector_delay_seconds`: the broadband-path median for the
  `distorted_c1_attack` probe. It is null if that probe class has fewer than
  12/16 detections.
- `analysis.onset_detector_delay_status:
  "measured_on_synthetic_impulses_not_physical_av_offset"`, or
  `"calibration_probe_detection_insufficient"`.
- `analysis.onset_detector_delay_compensated: false`.
  `analysis.physical_capture_latency: "uncalibrated"`.
- `analysis.onset_detector_delay_calibration` contains:
  - `paths`: {`high_frequency_novelty`, `broadband_rms_novelty`}
  - `probes`: {`unit_impulse` (one sample, 0.5), `click_3500hz_exp` (holdout
    click: 3500 Hz, τ 1.8 ms, 9 ms), `distorted_c1_attack` (32.70 Hz, tanh drive
    3.5, 1.5 ms rise, τ 23 ms, 40 ms)}
  - 16 sub-hop offsets (0, 5, …, 75 samples) per probe class, each probe in its
    own 0.25 s cell.
  - Detection is the first path peak in [−10, +40] ms. Delay is the reported
    frame-midpoint time minus the true onset.
  - Per path×probe: `median_seconds`, `q1_seconds`, `q3_seconds`,
    `min_seconds`, `max_seconds`, `probe_count`, `detected_count`,
    `missed_count`.
  - `compensation_table`: `periodic_high_frequency_candidate` →
    high_frequency/click_3500hz_exp; `broadband_attack_candidate` →
    broadband/distorted_c1_attack; librosa kinds → null (`uncalibrated`).
  - The values are deterministic, computed once per process (cached) with the
    same functions and thresholds `analyze()` uses.
- Per event: `source_timeline_seconds` is **unchanged**. A new
  `delay_compensated_source_timeline_seconds` equals source minus the table
  delay, or null with `delay_compensation: "uncalibrated_path"`.

### 3.3 `click_attack_ab.json` (artifacts/s2/rhythm_clicks/click-ab/<run>/)

- `schema_version`, `tool: "click_attack_ab"`, `status:
  "experimental_synthetic_ab"`, and `arms`: {`isolated`, `coincident`}. Per arm:
  - `generated_click_count` (denominator), and `attenuated_count`,
    `abstained_count`, `analyze_only_count` and `unmatched_generated_click_count`
    (no candidate within 10 ms), each over that denominator.
  - `abstain_reason_counts`.
  - `attack_window_count` (denominator). The attack window is W = [onset −5 ms,
    onset +50 ms].
  - Per window and as median/IQR: `attack_energy_delta_db` (processed vs
    unprocessed mix); `guitar_component_error_db` (energy of removal not
    explained by projection onto the true click, relative to clean-guitar energy
    in W; null with reason when nothing is removed); `centroid_delta_hz_vs_mix`;
    `centroid_delta_hz_vs_clean_guitar`; `baseline_centroid_delta_hz_mix_vs_clean`.
  - `windows_with_abs_energy_delta_over_0_5_db` (count/denominator).
  - The whole-signal `frequency_preservation` from `measure_protected_delta`
    (32 Hz bin and 28–80 Hz).
- `real_take` block: detection-only `clicks.experiment` with no template; a
  candidate count; candidates within 20 ms of a broadband attack candidate
  (`coincident_candidate_count`) versus `isolated_candidate_count`;
  `attenuation_claim: "none_detection_only"`; no audio written.
- Fixed fields: `click_identity: "unverified"`, `listening_ab: "not_performed"`,
  `physical_capture_latency: "uncalibrated"`.

### 3.4 `phrase-timing.json` (artifacts/s2/rhythm_clicks/phrase-timing/<run>/)

Inputs:

- `--analysis` (rhythm `analysis.json`).
- `--phrases`. This is either arrangement-markers JSON (`markers[]` with
  `source_time_seconds`/`end_seconds`, basis
  `reference_conditioned_alignment_candidate`) or `phrases.json`
  `observations.proposed_review_spans` (basis `automatic_review_span`).
- The input is refused unless the phrase file's `analyzed_input_sha256` (or
  source binding) equals the analysis `source.sha256`. File hashes are recorded.

Click reference: drift-model predicted clicks when `click_grid_drift.status ==
"fitted"`, else the constant `click_grid`, else every phrase abstains with
`no_click_grid`. `click_reference.basis` records which applied.
Offset = onset − nearest predicted click. A negative offset means ahead of the
click and a positive one means behind it. Only click-proximal onsets
(|offset| ≤ min(60 ms, P/4)) contribute. Other onsets are counted as
`off_click_onset_count` (subdivisions, not errors). If more than one onset falls
in one click's window, the nearest counts and the rest go to
`additional_onsets_in_window_count`. These are not extra notes.

Each phrase entry contains:

- `phrase_id`, `label`, `label_basis`, `span_source_seconds`.
- `onset_count_in_span`, `click_proximal_onset_count`,
  `off_click_onset_count`, `additional_onsets_in_window_count`.
- `median_offset_ms`, `iqr_ms` [q1, q3], `iqr_width_ms`.
- `median_offset_ms_delay_compensated`, which uses the §3.2 table:
  (onset − d_attack) − (click − d_click).
- `observed_click_basis_median_offset_ms`, which uses observed click candidates
  within 25 ms of the prediction, else null.
- `tendency_label` ∈ {`ahead_of_click`, `behind_click`, `within_5_ms`} (a
  descriptive sign only).
- `status` ∈ {`measured`, `abstained`}, and `abstain_reason` ∈
  {`fewer_than_4_click_proximal_onsets`, `no_click_grid`, `span_outside_analysis`}.

Summary: `phrase_count`, `measured_count` and `abstained_count`, with reasons.
Fixed fields:

- `real_take_status: "unvalidated_until_operator_spot_check"` (real take only;
  synthetic runs carry `synthetic_fixture`)
- `click_identity: "unverified"`
- `physical_capture_latency: "uncalibrated"`
- `listening_ab: "not_performed"`
- `performance_grading: "not_performed"`
- `expected_rhythm_reference: null`

## 4. Required unknown/abstain fields

Every new output carries these explicitly, with no silent omission:

- `click_identity: "unverified"` (the analysis keeps the existing `identity` strings)
- `physical_capture_latency: "uncalibrated"`
- `listening_ab: "not_performed"`
- `onset_detector_delay_compensated: false`
- drift `status`/`confidence_label`, with nulls on abstention
- phrase `status`/`abstain_reason`
- `real_take_status: "unvalidated_until_operator_spot_check"`
- `expected_rhythm_reference: null`
- `performance_grading: "not_performed"`

A recursive key and value scan in each new test module asserts that no output
contains `missed`, `extra_note`, `wrong_note`, `mistake` or `error_verdict`
tokens. The neutral `additional_onsets_in_window_count` is allowed.

## 5. Completion metrics and claim classes

Claim classes:

- **M-syn**: a measurement on a generated fixture against generator truth.
- **M-real**: a measurement on the real take, with no truth; unvalidated.
- **I**: an inference.
- **L**: a listening claim. None is made in this lane.

| # | Metric (denominator) | Class | Acceptance |
| --- | --- | --- | --- |
| D1 | Constant-grid fixtures (dev: 90 BPM 14 s, 178 BPM 14 s, 88.8 BPM 60 s; 3) | M-syn | `fitted`, \|drift_ppm\| ≤ 250 ppm/s and \|r\| ≤ 2e-4 s/s in 3/3 |
| D2 | Dev drift grid f∈{0.04,0.08,0.12} × BPM∈{150,185,220} (holdout law, 10 s, 9) | M-syn | \|drift_ppm − truth\| ≤ 0.10·\|truth\| in 9/9 |
| D3 | Sealed holdout drift (§7.1; 2 preregistered holdout + 8 sealed = 10) | M-syn | the count within 10 % is reported over 10; pass = 10/10; a failure is reported, not retuned |
| D4 | Abstention: 5-click fixture → `insufficient_events`; silence → `no_periodic_seed` (2) | M-syn | 2/2, numeric fields null |
| C1 | Delay calibration determinism and coverage (2 paths × 3 probes × 16) | M-syn | identical across two calls; detected/missed counts sum to 16 per cell |
| C2 | Timestamp invariance: every event's `source_timeline_seconds` equals the pre-change value on the existing test fixtures (all events) | M-syn | 100 % |
| C3 | Independent compensation check: `clicks()` fixture (90 BPM, phase 0.2, 3500 Hz τ 25 samples, different from the probe) compensated HF event times vs analytic onsets | M-syn | median \|error\| ≤ 2.5 ms (half hop); raw error also reported |
| A1 | A/B isolated arm: attack windows with \|attack_energy_delta_db\| > 0.5 dB (count/attack windows) | M-syn | reported; predicted 0 |
| A2 | A/B coincident arm: attenuated/abstained/analyze_only/unmatched over generated clicks; attenuated fraction coincident vs isolated | M-syn | reported with denominators; predicted coincident attenuated fraction < isolated |
| A3 | 32 Hz and 28–80 Hz complex-bin deltas per arm | M-syn | reported; no blanket high-pass; no claim beyond the DFT measurement |
| A4 | Real take detection-only candidate counts (coincident/isolated over total) | M-real | reported; `attenuation_claim: none_detection_only` |
| P1 | Phrase timing dev fixtures: rushing, dragging and on-time arms | M-syn | per-arm median of \|est − truth\| ≤ 5 ms (compensated primary; raw reported) |
| P2 | Phrase timing sealed eval (§7.2; 3 arms × 4 seeds × 4 phrases = 48 phrases) | M-syn | per-arm median \|error\| ≤ 5 ms for rushing and dragging; the fraction of phrases ≤ 5 ms and sign-correct counts are reported over 16 per arm |
| P3 | Abstention: phrases with 3 click-proximal onsets, and no-grid input | M-syn | 100 % abstained with the correct reason |
| P4 | Real take per-phrase table on the 034521Z analyzed input (phrases over arrangement markers and automatic spans) | M-real | reported with measured/abstained denominators; labelled unvalidated |
| R1 | Real take drift (034521Z `denoised.wav`, sha `cb8a3fa5…`) vs constant residual 5.3 ms | M-real | reported. Wind-down is I only. No adoption. |
| R2 | Regression: rerun `analyze` on the same input reproduces the existing `click_grid` scalars (bpm, period, phase, coverage, median residual) and the event count of 3684 | M-real | exact match, or a difference explained by a recorded producer hash |
| G1 | Existing `test_rhythm`, `test_clicks`, `test_demo` and `test_dag` pass | — | 100 % of their tests |

Experimental non-improvement (for example D3 < 10/10, or A2 opposite to the
prediction) is valid completion when it is reported with denominators. Nothing
is adopted as a default.

## 6. Test protocol

Run from the worktree root. Use the stdlib interpreter unless the module is
noted as numpy-gated.

```
PYTHONPATH=tests python3 -m unittest test_rhythm -v          # D1 D2 D4 C1 C2 C3 + existing
PYTHONPATH=tests python3 -m unittest test_phrase_timing -v   # P1 P3, hash-binding refusal, token scan
PYTHONPATH=tests python3 -m unittest test_clicks -v          # existing (numpy tests skip on stdlib)
PYTHONPATH=tests /Users/jess/git/video-utils/.venv/bin/python -m unittest test_clicks test_click_attack_ab -v
PYTHONPATH=tests python3 -m unittest test_demo test_dag -v   # G1 regression
PYTHONPATH=tests python3 -m unittest test_phrase_localization_pilot test_phrase_proposal_s1 -v  # pin check, see §8
```

The `.venv` interpreter is the existing locked analysis environment in the main
checkout. It is used read-only, with no install. Sealed evaluations are skipped
unless an environment variable is set: `RHYTHM_S2_SEALED_EVAL=1` (D3) or
`PHRASE_TIMING_S2_SEALED_EVAL=1` (P2), plus `CLICK_AB_S2_SEALED_EVAL=1` for the
A/B eval seeds. They run once each, after the freeze commit (§7.4).

Fixture definitions (all generated in tests; no media files):

- **Drift dev and eval**: 16 kHz. The click is 3500 Hz sine × exp(−t/1.8 ms),
  9 ms. Spacing follows the holdout law IOI = (60/BPM)·(1 + f·t/10), with phase
  0.2–0.5 s and amplitude 0.06–0.12. Colored noise uses amplitude 0.008–0.016
  and coefficient 0.55–0.85. Sustained distorted guitar tones are drawn from the
  tuning MIDI {24, 29, 34, 39, 46, 51, 56, 60, 65} with no high-pass. Truth is
  r = (60/BPM)·f/10, and drift_ppm truth = 1e6·r/(P0 + r·t_ref) at the fit's
  reported t_ref.
- **Holdout drift cases**:
  - `benchmark_holdout.render_timing_case` for `seed211`/`seed307`
    `timing-reference`, at 48 kHz with guitar motif, click and noise.
  - Decimation to 16 kHz uses a 3-sample boxcar mean then every third sample
    (the attenuation at 3.5 kHz is about 0.94, documented).
  - Truth comes from the case parameters `click_bpm` and `click_drift_fraction`.
  - These seeds are already withheld from setting selection by that plan, and
    this lane does not use them in development.
- **Phrase timing**:
  - 16 kHz audio, with the click period drawn from {0.6757 s, 60/150, 60/185}.
  - Each phrase has 8 click-aligned distorted attacks: tuning notes, drive
    2.6–4.6, decay 15–40 ms, 1.5 ms rise, palm-mute or sustained. The onset is
    click + δ_phrase + N(0, 3 ms) jitter.
  - Each phrase also has 4 off-click subdivision attacks (at P/3 or P/2) and
    one click masked by a coincident attack.
  - Arms: `on_time` δ=0; `rushing` δ∈[−30, −6] ms; `dragging` δ∈[+6, +30] ms.
    Dev uses δ∈{±8, ±15, ±25}.
- **A/B**:
  - 48 kHz with clicks every 0.6757 s.
  - Isolated attacks sit ≥ 150 ms from any click. Coincident attacks sit at
    click + Δ, Δ∈{−5, 0, +2, +5, +10} ms.
  - Notes C1/F1/Bb1/Eb2/Bb2 (MIDI 24, 29, 34, 39, 46), either palm-mute (τ 23 ms)
    or sustained (τ 300 ms), with 32.70 Hz content retained.
  - The template is the first isolated click (window 0–20 ms), declared
    click-only. Strength is 0.5 (the existing cap), with `attenuate=True`.

## 7. Preregistration (sealed by this commit)

1. **Drift (D3).** Eval cases:
   - The 2 preregistered holdout cases (seed211/seed307 `timing-pair` click parameters).
   - 8 sealed generated cases for seeds 9101–9108. Each knob is
     `sha256("rhythm-s2-drift-eval:{seed}:{knob}")[:8] / 2^64`, giving
     f∈U[0.04, 0.12], BPM∈U[80, 220], phase∈U[0.2, 0.5], click amplitude∈U[0.06, 0.12],
     noise amplitude∈U[0.008, 0.016] and tuning note index for the guitar
     tone, over 10 s.
   - Single arm: the frozen `linear_period` estimator.
   - Score: relative error of `drift_ppm`. Pass if ≤ 10 %. Abstention or a
     non-`fitted` status counts as a failure over the 10.
2. **Phrase timing (P2).** Seeds 7301–7304. Knobs use namespace
   `rhythm-s2-phrase-eval:{seed}:{arm}:{phrase}:{knob}`. There are 3 arms × 4
   phrases per seed (48 phrases). δ is drawn from the arm ranges in §6. Jitter
   σ is 3 ms. The click period is drawn uniformly from the three §6 values. The
   primary estimator is `median_offset_ms_delay_compensated`, and the
   secondary is raw `median_offset_ms`. Score per arm: the median over phrases
   of |est − truth| against the phrase's realized median onset offset. Truth is
   the median of the sample-rounded generated offsets of its click-aligned
   attacks. Abstentions stay in the denominator as failures.
3. **A/B.** Dev seeds 1–3 are for test development only. Eval seeds 8101–8104
   use namespace `rhythm-s2-click-ab-eval:{seed}:{knob}`, with 20 isolated and
   20 coincident attacks per seed. The arms are the fixed isolated/coincident
   split with no other treatment. Scores are the §5 A1–A3 quantities, and the
   prediction direction is recorded before the run.
4. **Sealing procedure.** Dev fixtures may guide implementation. Before any
   sealed run, the lane commits the implementation. The receipt
   `docs/agent-notes/sprints/20261006-s2/rhythm_clicks-eval.json` records that
   commit sha, the `rhythm.py`, `phrase_timing.py` and `click_attack_ab.py`
   sha256 values, the seeds and the exact commands. Each sealed run then
   executes once. A post-eval code change cannot be rescored on these seeds.
   Any rerun needs new, newly preregistered seeds, and both results are
   reported. No thresholds or arms are tuned on held-out seeds.

## 8. Root-owned changes requested and known dependency

- **S1 hash pins on `scripts/rhythm.py`.** `scripts/phrase_proposal_s1.py:27`
  and `scripts/phrase_localization_pilot.py:32` pin `scripts/rhythm.py` to
  sha256 `264b723c…`. `verify_pins()` is exercised by
  `tests/test_phrase_proposal_s1.py:141` and by `old_helper()` in
  `tests/test_phrase_localization_pilot.py`. Any `rhythm.py` change required by
  this contract breaks those S1 pins. These files are not lane-owned, and the
  lane will not edit them.

  Requested root decision: vendor a byte-identical frozen copy, for example
  `git show 4b87484:scripts/rhythm.py > scripts/frozen/rhythm_264b723c.py`.
  Then repoint the S1 load and copy sites (`phrase_proposal_s1.py:451`,
  `phrase_localization_pilot.py:582,678,838`) and `verify_pins` to that path,
  while keeping the recorded digest value. The alternative is to accept the
  pin failure as an S1 research-artifact boundary. The exact diff goes in the
  phase-2 `root_owned_changes_requested`.
- **Admission.** `phrase_timing` and `click_attack_ab` remain experimental
  helpers. MCP/tool descriptors (`program/tools.json`, `scripts/tool_api.py`,
  skills) are requested from root only if root admits them.

## 9. Bounds and doctrine

- Stdlib for `rhythm.py` and `phrase_timing.py`. numpy/scipy only in
  `click_attack_ab.py` through the existing `clicks.dependencies()`.
- One heavy job at a time. Explicit timeouts: FFmpeg 180 s; any real-take
  analysis wrapper 600 s. Single thread.
- FFmpeg comes from the nix store path given by the `FFMPEG`/`FFPROBE` env vars.
- No downloads, daemons, Linear writes, or writes to accepted runs or to the
  original take.
- No blanket high-pass or mains notch. The probe and fixtures retain 32.70 Hz
  content. Attenuation keeps the existing <1200 Hz subtraction protection and the
  0.5 strength cap.
- The arrangement's 404 clicks and phrase lengths are intent, never a forced
  detection count. First-five-second setup sounds are not treated as pure noise.

## 10. Phase-2 implementation amendments (before the evaluation commit)

§3.1 allows implementation details to change until the evaluation commit. These
changes were made on dev fixtures only. No sealed seed (§7) was run, and no
seed211/seed307 parameters were rendered, before the eval receipt.

1. **Tracker selection.** The nearest-peak tracker locked onto dense noise
   peaks in 2 of 20 dev-namespace probes (`rhythm-s2-drift-devprobe`, which is
   not a sealed namespace). In those probes, every anchor produced a full-count
   track, so the noise track won the tie. The frozen tracker works as follows:
   - Within ±12 % of the local period, it picks the peak with the largest
     `strength × exp(−½·(dt / (0.03·local period))²)`.
   - A beat is a miss when that support is below 10 % of the median accepted
     strength.
   - Anchors (the 24 strongest high-frequency peaks plus the middle constant-grid
     event) are ranked by summed accepted strength.
   - The local period is the least-squares slope of the last 8 accepted events,
     bounded to [0.7, 1.3]× the seed period.

   After this change, the dev probe passed 20/20 and D2 passed 9/9.
2. **Divisor selection.** Choose the fastest divisor in {1, 2, 3} that meets
   all of the following:
   - retained coverage (after outlier rejection) ≥ 0.7
   - divided period ≥ 0.25 s
   - when the seed-level fit also qualifies, rms ≤ max(1.25×, +1.5 ms) of that fit

   Every attempt is published in `divisor_attempts`.
3. **Probe count field rename.** §3.2 named `missed_count`, but §4's token
   scan forbids `missed`. The field is now `undetected_count`. It counts
   synthetic calibration probes with no detector peak in the window, not notes.
4. **Additive drift fields.** The drift object also carries:
   - `model_parameters`: anchor t0, IOI intercept P0, r and the retained beat
     range, which phrase timing uses to predict clicks.
   - `tracked_events`: the beat index, time, retained flag and residual of each
     tracked event.
   - `divisor_attempts`, `high_frequency_peak_count`, `selection_rule`,
     `drift_ppm_units` and `click_identity: "unverified"`.
   - `attempted_fit_residual_ms_rms` when the status is
     `fit_residual_exceeds_bound`.
5. **Per-event delay fields.** Each event also carries `delay_compensation`:
   `synthetic_probe_median_subtracted`, `uncalibrated_path` (librosa kinds) or
   `calibration_probe_detection_insufficient`.
6. **Phrase input rules.**
   - Arrangement markers are used only when they have a positive numeric span
     and a non-boundary name. Exclusions are counted.
   - The observed-click set is the `periodic_high_frequency_candidate` events
     plus the drift `tracked_events`.
   - Each phrase records `click_reference_extrapolated` and `tendency_basis`.
7. **A/B layout.**
   - Each arm is its own 48 kHz render per seed: 44 clicks, with attacks on
     clicks 2, 4, …, 40 (isolated: +P/2; coincident: +Δ cycling
     {−5, 0, +2, +5, +10} ms).
   - White noise is 0.001.
   - Notes and articulation come from per-attack knobs.
   - An additive `attack_proximal_clicks` split (clicks within 60 ms of an
     attack onset) reports decisions on the overlapped clicks separately from
     the all-click denominator.
8. **Known dependency (§8).** In this worktree, `test_phrase_proposal_s1` and
   `test_phrase_localization_pilot` now fail 6 errors and 1 failure with
   `pinned_dependency_changed:scripts/rhythm.py`. A further failure,
   `test_owned_exited_leader_live_inert_child_cleanup`, also fails at base
   commit 2d9eaa5 in this sandbox and is unrelated.

## 11. Results pointers (post-evaluation; the contract text above is unchanged)

- Implementation and dev results: `docs/agent-notes/sprints/20261006-s2/rhythm_clicks-implementation.json`.
- Sealed preregistration: `rhythm_clicks-eval.json`, committed at 9b01dd9 before any sealed run.
- Sealed results: `rhythm_clicks-eval-results.json`. Each sealed run executed once.
  - D3: 10/10 within 10 % (maximum relative error 2.75 %).
  - P2: per-arm median |error| was 0.78, 1.69 and 1.37 ms (on-time, rushing, dragging).
  - A1: 0/80 isolated attack windows exceeded 0.5 dB.
  - A2: the attenuated fraction was 0.347 for coincident clicks versus 0.830 for isolated clicks. Attack-proximal coincident clicks were 0/80 attenuated.
  - A3: the maximum 32 Hz bin relative delta was 5.1e-9.
- Real take (M-real, unvalidated): `rhythm_clicks-real-take.json`.
  - R2 reproduced the accepted run exactly.
  - R1 measured drift of +1.67 ± 0.41 ppm/s. The interval lengthens by about 0.16 ms across the take. A wind-down reading is an inference only, and nothing is adopted.
  - P4 per-phrase offsets are confounded by onset density and click/onset coincidence. See the diagnostics in that receipt.

## 12. Phase-4 repair: S1 pin resolution (root-owned, not applied by the lane)

The audit's must-fix item is that merging this lane breaks the S1 pins on
`scripts/rhythm.py` (`264b723c…` on main and on merge-base 4b87484; `cd719914…`
on this branch). The lane keeps its `rhythm.py` changes, because the sealed S2
evaluation (§11) ran that code. It does not edit the S1 files.

Instead, `docs/agent-notes/sprints/20261006-s2/rhythm_clicks-pin-resolution.json`
holds a verified root patch, which must land in the same admin merge:

1. Vendor the file with
   `git show 4b87484:scripts/rhythm.py > scripts/frozen/rhythm_264b723c.py`.
   Its sha256 equals the pinned `264b723c…`.
2. Add a `FROZEN` map from logical name to vendored path in
   `phrase_proposal_s1.py` and `phrase_localization_pilot.py`. Then apply it in
   these places:
   - `verify_pins()`
   - the S1 rhythm load site
   - the pilot's `sources/` copy loop
   - `tests/test_phrase_localization_pilot.py:161`

   `PINS` keys and values stay unchanged, so sealed receipts that compare
   `dependency_sha256 == PINS` still match.

These are unit-test measurements taken on a scratch export of this branch. The
S1 test modules give the following results:

| State | Run | Failures | Errors | Skipped |
|---|---|---|---|---|
| Unpatched | 38 | 4 | 6 | 7 |
| Patched | 38 | 1 | 0 | 7 |
| Merge-base | 38 | 1 | 0 | 7 |

The one failure that remains is the unrelated
`test_owned_exited_leader_live_inert_child_cleanup`.

Trade-off: the patch changes the S1 controllers' own `worker_sha256`, so a
sealed S1 run must be replayed at its recorded commit. Root may instead record
an explicit decision to accept the break.
