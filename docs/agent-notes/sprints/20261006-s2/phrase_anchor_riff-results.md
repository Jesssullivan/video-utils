# S2 phrase_anchor_riff results (2026-10-06)

Lane `phrase_anchor_riff`, sprint `20261006-s2`, Linear TIN-5603 (parent TIN-5599).
Contract `docs/spec/sprints/PHRASES_S2.md` (freeze d8875ad, additive notes §12).
Authority: workflow-A phase-2 task; R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13.
Branch `sprint/20261006-s2/phrase_anchor_riff`; root signs merges and owns Linear.
No default, profile, master, catalog or tool admission changed. The original
movie, the accepted run `20261006T041633Z-990aa1bd6737`, Documents/Desktop and
S1 artifacts were only read or not touched. No audio is committed.

## A. Anchor-click arrangement spans (`scripts/phrase_anchor.py`)

**Arithmetic construction (M1).** The operator arrangement expands to 27 units
(24 sixteen-click phrases, 2 eight-click breakdowns, 1 four-click rest), 28
boundaries and 404 intended clicks. Boundary `b` lies at
`t = s0 + phi + (k0 + c_b) * P / r`. Nothing is moved toward an observation.

**Real-take intent projections (M2/M3), inference, not detection.** Fitted grid
`clicks.json` cee9a506…: P = 0.675662 s, phi = 0.510680 s, r = 2. The r = 2
mapping is operator-supplied (≈178 BPM click on the ≈88.8 BPM grid), not
inferred. Each of the three cached candidates gives 28 boundaries and none is
adopted:

| Anchor input (s) | k0 | Snap residual (s) | boundary:0 → boundary:27 (s) | join_confidence over 28 | Boundaries on interpolated half-periods |
| --- | ---: | ---: | --- | --- | ---: |
| 10.2775 | 29 | −0.0303 | 10.308 → 146.791 | 5 supported, 1 weak, 22 uncertain | 28/28 |
| 10.6275 | 30 | −0.0181 | 10.646 → 147.129 | 6 supported, 22 uncertain | 0/28 |
| 10.9775 | 31 | −0.0059 | 10.983 → 147.467 | 6 supported, 22 uncertain | 28/28 |

* All arrangement offsets are even, so with r = 2 an odd anchor index puts
  every boundary on an interpolated half-period rather than a fitted grid beat.
  This is an arithmetic property. It does not say which anchor is right.
* Grid components are measurements: the ±4 operator-click windows contain
  4/4 fitted beats observed at every boundary, and 26–27/28 joins are
  `grid_supported`. The 22 `uncertain` labels are structural: 21/28 boundaries
  follow breakdown 1, plus breakdown and presumed-repeat flags. `join_confidence`
  is a heuristic ordinal, not a probability.
* Every boundary ≥ 7 carries `uncertain_upstream_breakdown`. Breakdown ±1/±2
  click shift hypotheses are emitted as `hypothesis_not_adopted`.
* All boundaries fall inside the 150.96 s source extent.
* Receipt: `phrase_anchor_riff-real-take-spans.json`. Outputs are gitignored
  under `artifacts/s2/phrase_anchor_riff/real-take/`.

**Abstention (M4).** Every output carries
`real_take_phrase_correctness: unknown_until_operator_marks_boundaries`. Scoring
k0 = 30 against the only existing annotation v2 store (`s1-demo-context`,
17041cb3…, one `noise` context annotation) returns `result: null`,
`reason: insufficient_operator_boundaries`, accepted marks 0/10 required. Once
≥ 10 operator marks exist, the scorer reports hits at ±100 ms and ±1 click
(0.3378 s), one-to-one, with MAE denominator = hits. Unmatched boundaries count
as `not_reviewed`, never as false positives.

## B. Continuous-riff generated benchmark (`scripts/phrase_riff_s2.py`)

**Process evidence (M5).** These steps happened in this order:

1. Dev calibration on seed 1009. Run 1 failed its 300 s budget at load
   average ≈ 80–130 on 6 cores: case-5 child timeout, no seal, no truth opened.
   The worker then changed only to reuse S1's own `extract()` output.
2. Run 2 completed in 158 s and chose θ = 0.75, with dev TP@0.5 6/6 at every θ
   and dev negative false candidates 16/10/1. The dev receipt was committed in
   `fde3da6`.
3. The preregistration was committed in `9c4ef5f` (plan 5922debe…).
4. The release was committed in `8df5f7c` (`actor: root_workflow`, quoting the
   workflow task; release 5ceeaaf8…).
5. Held-out generation started at 14:19:21Z. All 16 predictions were globally
   sealed (846c268c…) before scoring opened any truth.

**Resources (M10).** Total wall time was 115 s against the 900 s external
timeout: generation 1.9 s, discovery 111.1 s. The maximum per-source wall time
was 16.8 s (limit 120 s), with 2 numeric threads.

**Measured outcome, generated clips only (M6–M9).** 16 clips: seeds
1511/1613 × 8 cohorts. 12 reference pairs, 48 typed endpoints, 4 negative
cases. Totals are sums; abstentions stay in the denominators.

| Arm | Predicted pairs | TP/FP/FN @IoU0.5 (of 12) | TP/FP/FN @IoU0.75 | Endpoint hits 20/50/100 ms (of 48) | Matched endpoint MAE (denominator) | Negative false candidates (through-composed / sustain32, 2 cases each) |
| --- | ---: | --- | --- | --- | --- | --- |
| Araw (frozen S1 baseline) | 5 | 3/2/9 | 0/5/12 | 1/2/3 | 0.3016 s (12) at 0.5; null at 0.75 | 0 / 0 |
| S1_support (frozen S1 treatment) | 0 | 0/0/12 | 0/0/12 | 0/0/0 | null (0) | 0 / 0 |
| R1_lag (θ = 0.75) | 91 | 12/79/0 | 12/79/0 | 13/29/43 | 0.0767 s (48) | 0 / 1 |

* Per-positive-cohort TP@0.5 (of 2 each). R1_lag got 2/2 in all six cohorts.
  Araw got 1/2 in legato, tapping and sweep, and 0/2 elsewhere. S1_support got
  0/2 everywhere.
* Common-reference MAE is null with reason `no_reference_matched_by_all_arms`
  (denominator 0), because S1_support matched nothing. There is therefore no
  common-set MAE comparison.
* S1_support's quiet-gap grouping produced no proposals on contiguous playing.
  This confirms the S1 limitation: its 4/4 quiet-gap result does not transfer to
  back-to-back riffs.
* R1_lag recovered every generated pair, but emitted 79 extra candidates
  (shifted near-duplicates and other lags; cap 10 per clip). These are counted
  as FP. Candidate confidence is null and no precision or calibration claim is
  made.

**Claim boundary.** `continuous_riff_accuracy_scope: generated_only`,
`real_take_accuracy: unknown`, `musical_phrase_identity: unknown`,
`physical_articulation_accepted: false`, `settings_retuned: false`,
`default_adoption: false`. The clips are one synthetic recipe family: tanh
synthesis, the S1 nuisance formulas, and one recurrence pair per positive clip.
Twelve pairs cannot estimate a population rate. Tapping and sweep clips are
recipe constructions, not physical articulation evidence. A sustained 32.7 Hz
note was present (never filtered) in the sustain negatives. R1 has no
activity gate, and θ came from 8 dev clips. Receipts:
`phrase_anchor_riff-evaluation.json` and `phrase_anchor_riff-heldout-score.json`
(byte copy of the raw score, 71759466…).

## C. V2 holdout-bank receipt (M11)

`docs/agent-notes/peers/xoruby/V2-holdout-bank-receipt.json`. Plan 495ad2f3…,
generator 051d8689… at commit f180572b… (verified with git log), output root
rebound to the lane area with generator bytes unchanged. 12 cases × 10 s and
48 PCM16 components were generated in 161.5 s against the 600 s internal and
660 s external limits. Byte reproduction against the existing bank
`heldout-211-307-20261006T0020`: 48/48 components and 12/12 truths identical.

The receipt also records:

* licence: pending operator confirmation (repository MIT; proposed CC BY 4.0
  for cross-repo use);
* reserved seeds 2101–2199;
* "training use of this bank voids video-utils held-out evaluation on it";
* that seeds 211/307 were already used once by video-utils;
* `ground_truth_scope: generator_only_not_musician`;
* that transfer of the audio to XORuby is a separate root action.

Quality metrics were not evaluated.

## Tests (M12)

Under stdlib `python3`, `test_phrase_anchor` + `test_phrase_riff_s2` ran 24
tests: 22 executed and 2 numpy cases skipped. The 22 include 1 real-grid
read-only case that skips in CI. Under the analysis interpreter,
`test_phrase_riff_s2` ran 10/10 with no skips. The regression modules
`test_arrangement_reference`, `test_phrase_proposal_s1` and
`test_benchmark_holdout` ran 47 tests, all OK with 7 skipped.

## Not done / unknown

* Real-take phrase accuracy: needs ≥ 10 operator-marked boundaries.
* Which anchor is the true first phrase start.
* Breakdown 1 execution.
* Click identity and physical/detector latency.
* Listening acceptance.
* Any missed-note or musical-mistake verdict.
* Root actions: merge, Linear update, posting V2 on TIN-5186, and any audio
  transfer.
