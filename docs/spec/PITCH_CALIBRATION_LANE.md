# Pitch calibration: generated nine-string signals and bounded coverage

Authority: operator-authorized ten-hour goal; repository AGENTS.md;
R-HOOK-CONVERGENCE-20261004 / R-N12 / R-N13. Owner: `guitar_features`.
This document is a research and implementation contract during root's
publication freeze. It changes no active worker, tests, registry or fixture.
Implementation starts only after root releases the lane and assigns source files.

## Goal and fixed pilot

Measure the published `pitch` tool against known-generated signals. Preserve its
separate low/high hypotheses, nullable frequency, octave alternatives and
uncalibrated algorithm voicing probability. These labels are generator truth,
never actual-take note correctness, musician mistakes or listening acceptance.
Legacy `notes` remains the sparse stdlib tool; `pitch` is a separate hook.

Use the agreed [technical-v2 bank](BENCHMARK_CALIBRATION_LANE.md): 12 deterministic
48 kHz mono PCM16 cases, exactly 120 seconds of unique generated audio. Pitch
analysis consumes only the following 30-second pilot; all other bank coverage
is explicitly `not_requested`. Run these four jobs serially with the existing
locked analysis interpreter and no model or package downloads:

| Case | Component | Start / budget | Purpose |
| --- | --- | --- | --- |
| c1-missing-fundamental | clean | 0 / 8 seconds | Known 32.703195663 Hz periodicity with harmonics 2/3/4/5/7 and no synthesized F0 coefficient |
| tuning-ladder | clean | 0 / 8 seconds | All nine registry notes, with clean and tanh-distorted conditions |
| legato-transition | mix | 0 / 6 seconds | Continuous low/high pitch transitions with click/noise interference |
| sweep-and-polyphony | mix | 0 / 8 seconds | Rapid ascending/descending changes and separately identified polyphony |

Every job uses explicit `--start-seconds 0` and the stated
`--max-analysis-seconds`, so default distributed sampling cannot change the
scored coverage. The pitch settings remain the published low branch
28–500 Hz / 4096 samples and high branch 200–2000 Hz / 1024 samples, 16 kHz
analysis, 256-sample hop, 0.2-semitone resolution and 50 thresholds. At most two
numerical threads and 180 seconds per pitch child; the calibration pilot has a
900-second overall deadline. It stops scheduling at the deadline and retains
partial/unavailable results, never a completed-all-tasks claim.

The ladder preserves MIDI 24,29,34,39,46,51,56,60,65 and the supplied Eb2→Bb2
interval. Registry pitch classes are operator supplied, octaves inferred, and
A4=440 frequencies theoretical; those frequencies become exact generator
parameters only inside this synthetic bank. The separate legacy 32.000 Hz
preservation sentinel must not be relabeled as exact C1. Check missing-F0 absence
on its clean steady component with the bank's joint harmonic fit, not a single
FFT bin or a post-synthesis nonlinear transform that could regenerate F0.

## Input and output contracts

The benchmark owner generates the bank, truth and pitch job receipts. A future
`scripts/pitch_calibration.py --fixture-index BANK --pilot-index PILOT --output NEW_DIRECTORY`
will evaluate existing artifacts; it will not invoke pitch or regenerate audio.
Outputs are new directories under ignored `artifacts/benchmarks/`. Root owns the
recipe, hook, report and publication integration after the implementation passes.

`pitch-pilot.json` uses schema version 1 and contains `bank_index_sha256`,
`instrument_registry_sha256`, a 30-second budget and exactly four `jobs`. Each
job records `case_id`, `component` (`clean`/`mix`), input path/hash, mixture-parent
path/hash, truth path/hash, pitch artifact path/hash, command, worker hash,
interpreter/library versions, requested start/budget, observed coverage spans,
wall duration and job status. Clean-component evidence must never be described
as mixture performance. The decoder/sample origin is explicitly
`synthetic_generator_sample_zero`; zero is not inferred from absent WAV PTS.

Read schema-2 truth with `ground_truth_scope: generator_only_not_musician`,
component/source hashes, native rate/count, `pitch_regions`, `pitch_trajectories`,
condition/articulation and generator score events. The mixture hash in truth's
`source` may differ from the selected clean input; join through the declared
component hash. An explicitly omitted attack has no invented observed onset.
Discovery receives audio and supported settings only, never these labels.

Read the published pitch schema unchanged: source/lineage, tuning metadata,
analysis coverage/settings and `observations.analyzed_excerpts[].branches[].frames`.
Reject mismatched hashes, worker/settings revisions within a receipt, malformed
or nonfinite timestamps/frequencies, unsupported schemas, duplicate branch
frame centers, overlapping requested excerpts, coverage outside the input, or
coverage beyond the 30-second aggregate pilot. Allow nullable probabilities and
frequency abstentions. Bounds: 5 MB per bank/truth/pilot JSON, 64 MB per pitch
artifact, six excerpts per artifact and 4000 total branch frames per artifact.
Validate counts before calculating metrics. No frame artifacts or audio enter Git.

Write atomic `pitch-calibration.json` with schema version 1, bank/pilot/evaluator
hashes, source/component/truth/pitch hashes, versions/settings and elapsed time.
Each case contains per-branch `counts`, `stable_monophonic_metrics`,
`transition_metrics`, `context_diagnostics`, coverage spans and task statuses.
Include `pitch-frame-errors.csv` with case/component/condition/branch, native
reference sample, audio/source center and window bounds, reference frequency,
estimated frequency, signed cents, eligibility/exclusion reason, algorithm
voicing probability and octave-error classification. Polyphonic rows retain the
reference frequency set and nullable single-pitch error. `pitch-transition-errors.csv`
contains generated transition ID/time, branch, first supported target time,
signed timing bias or censoring reason. Root's report can read these compact
aggregates rather than the multi-megabyte pitch frame tree.

## Metric definitions and exclusions

Evaluate each branch independently; never choose the branch or octave that best
matches truth to inflate a primary result. A reference frequency is evaluated at
`round(frame.audio_relative_seconds × native_sample_rate)`, using native-sample
regions and the declared analytic glide formula. Regions are half-open. Require
component hashes and generator origin before aligning to this sample axis.
No fitted delay, tuning offset, time warp or post-hoc pitch correction is applied.

A stable monophonic frame requires complete excerpt context and its **whole
analysis window** inside one monophonic reference region/trajectory. The true
frequency must be inside that branch's declared range. A stable unvoiced frame
requires its whole window inside a declared guitar-absent interval. Keep
transition-crossing, padded-edge, out-of-range and polyphonic frames separate,
with explicit denominators; short notes may have no complete low-branch window.
Do not turn zero eligible frames into zero error or a pass. An estimated-voiced
frame requires `voiced: true` and a finite positive `frequency_hz`; other
frequency abstentions are not scored as a guessed pitch.

- Signed cents: `1200 × log2(estimated_hz / reference_hz)`. Report median signed
  cents and median absolute cents over eligible frames with estimates; include N.
- Raw pitch accuracy: eligible true-voiced frames with a voiced estimate within
  ±50 cents, divided by eligible true-voiced frames. Abstention is a miss here.
  Raw chroma accuracy uses cents wrapped into [-600,600) with the same threshold
  and denominator; it does not erase octave errors in the primary pitch score.
- Octave error: nonzero nearest octave `k` with `abs(cents−1200k) ≤ 50`.
  Other errors beyond ±50 cents are non-octave pitch errors; retain their signed
  nearest-semitone histogram. Do not double-count an octave error in that bucket.
- Voicing recall: estimated-voiced / eligible true-voiced. Guitar-voicing false
  alarm: estimated-voiced / eligible guitar-absent. Precision uses those TP/FP
  counts. Abstention is reported over all covered frames and each context;
  rates with denominator zero are null with an applicability reason.
- Transition timing: for a generated pitched boundary with sufficient following
  stable support, scan complete-excerpt frames from one half-window before the
  boundary through the earlier of the next pitch boundary or 0.5 seconds after
  this boundary. Locate the first of two consecutive frames within ±50 cents of
  the target frequency; crossing-window frames remain eligible for this scan.
  Report its unshifted signed offset from the generated boundary, including
  negative lookahead bias. Stable interiors establish target support; restricting
  the scan to those interiors would manufacture a half-window delay. If no two
  full-window following-target frames fit, report
  `censored_window_resolution`; if eligible support exists but no target appears,
  report `target_not_detected`. No pitch change within ±50 cents is
  `not_applicable_no_distinct_pitch_change`. These are detector findings, not
  missed notes.
  Glides retain instantaneous-frequency error rather than invented picked events.
- Polyphony, clicks and absent-fundamental contexts retain candidate/abstention
  counts and harmonic alternatives; polyphony receives no forced single-note
  accuracy score. Report out-of-range voiced responses separately. Histogram
  pYIN probability by observed context; do not label it note-correctness confidence
  or calibrate a real-recording verdict from these synthetic bins.

Aggregate by summing numerators/denominators per branch and condition; retain
individual cases and never average ratios with missing denominators. Show N for
all timing/error summaries; publish p95 only with at least 20 applicable values,
otherwise null `insufficient_samples`. Small-N ladder interiors cannot establish
robust accuracy, platform equivalence or real-guitar performance.

## Tests, acceptance and rollout

Before any benchmark score, independent metric unit tests must prove: exact
matches; +100-cent errors; ±1200-cent errors counted separately despite chroma
matches; abstentions counted in pitch/voicing denominators; false voicing during
silence; null metrics for absent denominators; mixed/polyphonic exclusions;
window-complete versus transition/padded-edge masks; nonzero source-origin
translation without fitted correction; and deterministic reference-sample rounding.
Use hand-constructed reference/estimate arrays, not the generator's own scorer.

Structural tests reject altered component/truth/pitch hashes, switched clean/mix
labels, registry/settings drift, duplicate/unsorted or nonfinite frames,
unsupported schema, extra coverage, missing mandatory jobs and deadline-truncated
receipts. Expected generated notes and the unusual tuning interval remain intact.
The missing-F0 independent signal check and existing pitch distorted-C1,
missing-fundamental, sweep, legato and silence fixtures remain required.

A bounded actual pilot must process the agreed four jobs and produce all
applicable per-branch metrics with explicit exclusions; artifact/source hashes
must remain unchanged. Hard failures are provenance/schema/path/resource
violations or new real-note/correctness claims. Initial model-quality results are
baselines: poor pitch, octave errors, low voiced coverage and timing bias remain
visible quality alerts, not silently tuned-away failures. Diagnostic alerts:
stable monophonic raw pitch accuracy below 0.90 when eligible true-voiced N≥20,
or median absolute cents above 35 when estimated-voiced N≥20, and any
stable-silence false voicing. These are synthetic
engineering sentinels, not musician acceptance thresholds.

States match the bank protocol: `failed_structural`,
`completed_with_regression_alerts`, `completed_measurements`, `unavailable_backend`,
`not_requested`, `not_applicable`, `abstained_expected_context`, `no_candidates`.
Exit 2 means invalid invocation; 1 means structural failure; 0 means completed
measurement with explicit optional/unavailable states. No candidates against
applicable positive truth remains missed detection, never expected abstention.
A partial pilot cannot claim all-task completion. Root publishes the receipt and
tracker facts after source checks and the actual generated pilot; real take
listening, transcription and intended-note assessment stay separate.

## Primary research

Checked October 5, 2026. Official
[librosa pYIN documentation](https://librosa.org/doc/0.11.0/generated/librosa.pyin.html)
distinguishes frequency, voicing flags and voicing probability, and explains
centered frames/padding. The pitch/voicing terminology and 50-cent comparison
convention are informed by the official
[mir_eval melody implementation](https://github.com/mir-evaluation/mir_eval/blob/main/mir_eval/melody.py).
No new mir_eval dependency is required. The full-window masks, context exclusions,
30-second sampling budget and alert thresholds above are explicit project choices;
neither source establishes accuracy on distorted nine-string recordings.
