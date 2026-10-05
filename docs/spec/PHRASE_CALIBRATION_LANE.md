# Phrase calibration: bounded generated-fixture evaluation

Authority: operator's active ten-hour parallel goal, R-HOOK-CONVERGENCE-20261004
and R-N13. Root released implementation after publication
`45a1313ccbcb0ecc097f3a017979254e5719a3c6`. The lane owns the new evaluator,
its tests, this document and its dated receipt. Existing discovery, graph and
comparator scripts remain outside this implementation's ownership.

## Purpose and primary-source basis

Measure automatic structural discovery and relative recurrence alignment on
known-generated signals. Discovery needs no intended score, tonic, mode or
predeclared musical phrase. The evaluator alone reads generated references.
Synthetic reference agreement does not establish musical intent, actual guitar
accuracy, musician correctness, physical A/V sync or listening acceptance.

- [mir_eval segmentation documentation](https://mir-eval.readthedocs.io/latest/api/segment.html)
  distinguishes boundary detection from structural labeling and uses bounded
  one-to-one matching. Its optional endpoint trimming informs the evaluator's
  explicit exclusion of recording start/end boundaries.
- [AudioLabs/FMP evaluation](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C4/C4S5_Evaluation.html)
  explains tolerance-window ambiguity and the dependence of structural references
  on annotation granularity. Therefore duplicate candidates cannot earn repeated
  credit, and phrase/region hierarchy levels are evaluated separately.
- [AudioLabs/FMP structure principles](https://www.audiolabs-erlangen.de/resources/MIR/FMP/C4/C4S1_MusicStructureGeneral.html)
  treats repetition, novelty and homogeneity as different structural cues.
  Generated texture boundaries are not automatically semantic riffs/breakdowns.
- [librosa DTW controls](https://librosa.org/doc/0.11.0/generated/librosa.sequence.dtw.html)
  exposes constrained steps, penalties and banding. Alignment can absorb timing
  differences; a small post-warp residual is not evidence of an unchanged motif.

Use the existing locked libraries or standard-library metric code; no new model,
dataset or package download is authorized by this lane. The chosen evaluation
windows below are project engineering defaults, not universal guitar standards.

## Fixture-bank agreement and separation

The fixture owner is `repo_patterns`. Agreed technical-v2 bank: at most twelve
fixtures and **120 seconds aggregate**, numerical threads at most two. It contains
three legacy eight-second examples, plus C1/missing-fundamental (8s), tuning ladder
(8s), legato transition (10s), sweep/polyphony (10s), rests/syncopation/tuplets
(12s), variable tempo (12s), click overlap (12s), timing reference (12s) and timing
errors (12s). These total twelve fixtures/120 seconds; no later fixture silently
expands the budget.

Truth schema version 2 records waveform hash, native sample extent/rate and
generator-origin zero. Its kind is `synthetic_generated_signal_and_score_truth`,
scope `generator_only_not_musician`. Shared fields are:

- `phrase_spans_seconds`, `boundaries_seconds`, `pulse_times_seconds`,
  `recurrence_pairs` and `warp_reference` with source/target landmark seconds and
  `mapping_kind`.
- `observed_articulation_context`, `expected_abstention_reasons`, and
  `generated_score.events` with stable IDs, native sample onsets, source seconds,
  rational beat positions, durations, MIDI hypotheses and articulation labels.
- Separate actual generated events versus intended generated event IDs for
  intentionally injected −25/+25/−60/+60ms offsets and omit/add experiments.
  These labels describe renderer operations, never mistakes in a real take.

Fixed fixtures use a generated 178 BPM quarter grid with explicit triplet,
quintuplet and septuplet positions. Variable tempo integrates phase through
178→210 BPM; it does not use one false constant grid. Legato/sweep examples
distinguish picked attacks from pitch transitions. Semantic phrase boundaries may
be null. Signals cover intentional 32 Hz low content and upper-register behavior;
low-frequency energy is not labeled nuisance noise merely by frequency.

The discovery subprocess receives waveform/probe settings only. Truth/score,
reference warp and reference boundaries never enter discovery, threshold selection
or DTW path construction. The evaluator attaches them after inference. Evaluate
source copies and processed derivatives separately with explicit DSP-latency
receipts; matching extent/PTS alone does not establish waveform alignment.

## Exact metrics

All times use generated source-sample zero in seconds. Quantize generated truth
from native samples, not a guessed video frame grid. Keep metrics at each tolerance
separate, with raw denominators, unmatched items and abstention counts.

| Measurement | Exact rule |
| --- | --- |
| Boundary precision/recall/F1 | Exclude 0/duration endpoints. Match interior boundaries one-to-one within inclusive 20, 50 and 100ms windows; 50ms is primary. Maximize matched count, then minimize total absolute offset. TP is match count, FP/FN are unmatched estimates/references. P=TP/estimated count, R=TP/reference count, F1=2PR/(P+R); zero denominator yields zero, except both sets empty yields null metrics and `not_applicable_no_boundaries`. Use a 1ns numeric comparison margin only. |
| Boundary displacement | For matched pairs report signed seconds, median absolute error and 95th percentile. Also retain unmatched counts; a perfect matched-error score must not hide low recall. Percentile uses sorted nearest-rank index `ceil(.95*n)-1`; no matches yields null. |
| Region span IoU | `intersection_duration / union_duration` for positive half-open spans. Match one-to-one by maximum count then greatest total IoU at thresholds 0.50 primary and 0.75 diagnostic. Report region P/R/F1, matched mean/median IoU and unmatched counts. Evaluate phrase/texture hierarchy separately; never pool nested reference levels. |
| Recurrence-pair recognition | A pair matches only when both ordered first/second regions match the same generated pair at the selected IoU threshold. One predicted pair earns at most one reference credit. Unordered swapping is not permitted. Report pair P/R/F1 independently of boundary scores. |
| Relative shift | Use phrase-relative mapping `target_offset = delta + rate * source_offset`; exclude absolute container/start offsets. Report signed shift estimate, absolute error in seconds/ms, and evaluation coverage. Null/abstained estimate gives null error and an explicit uncovered item. |
| Relative rate | Rate is second-phrase elapsed seconds per first-phrase elapsed seconds. For affine examples report absolute ratio error and `100*abs(estimated/reference - 1)`. For piecewise tempo, evaluate each declared landmark interval separately; a global ratio near one must not hide early compression followed by later expansion. |
| Warp-curve accuracy | Interpolate the estimated monotonic path at generated landmark times. Report source-axis coverage, mean/95th-percentile absolute target-time error and unmatched/outside-path landmarks. Do not silently extrapolate outside the supported path. |
| Motif detection differences | Compare generated **detectable attack** events, not all pitch transitions. Report one-to-one observed-attack P/R/F1 and unmatched counts independently of musical-error flags. Generated additions/omissions are evaluation labels only. |
| DTW concealment | Retain both unwarped motif timing differences and post-warp alignment residuals. Record injected ≥60ms shifts or ≥10% rate changes whose residual falls below 20ms after warping. Such absorption is diagnostic; the raw change cannot disappear from output or become “no issue.” |
| Abstention and false claims | Report eligible/abstained counts by unknown/weak detector, boundary ambiguity, legato/tapping/sweep, feature mismatch and constrained no-path reason. Count any unsupported confirmed-note/performance claim separately; expected count is zero. |

Macro-average only applicable per-fixture scores; also report micro TP/FP/FN.
Report excluded/null fixture counts. Do not average missing errors as zero or
count abstention as correct localization. Calibration labels stay generator-only,
and no threshold is tuned against the actual Documents recording.

## Test definition of done and acceptance

Metric-oracle tests use small independently specified answers, rather than calling
the production matching routine to generate expected results:

- References `[1,2]`, estimates `[.98,1.02,2]`, 50ms tolerance → TP=2, FP=1,
  FN=0, P=2/3, R=1, F1=0.8. Two estimates near one boundary never earn two hits.
- A 25ms boundary shift fails 20ms and passes 50/100ms. A 101ms shift fails every
  configured window. Empty/empty is null; missing all genuine boundaries is zero.
- Reference `[1,3]`, estimate `[2,4]` → IoU=1/3, no match at 0.5. Estimate
  `[1.2,3.2]` → IoU=1.8/2.2 and matches both thresholds. One whole-recording span
  cannot satisfy multiple smaller reference regions.
- Known affine shift/rate and piecewise landmark maps recover exact oracle metric
  values within 1µs arithmetic tolerance. Uncovered landmarks remain uncovered.
  This verifies metric arithmetic, not detector time resolution.
- Aligned synthetic feature motifs at 50ms frame spacing must retain a 100ms
  injected shift and a 0.8 rate example as relative differences; assess shift
  error ≤30ms and ratio error ≤0.08. Report failure rather than loosen tolerances.
- Qualified synthetic attack evidence permits a detection-gap hypothesis for a
  generated omission. The identical case with unknown confidence or legato hints
  abstains from attack-edit flags. Intentional rests/tuplets do not become false
  definite mistakes. Uniform clicks/constant texture do not establish meter,
  downbeats, tonic, mode, guitar-note identity or phrase semantics.
- A low-cost warped path cannot erase its pre-warp difference record. A no-path,
  silent/constant or feature-mismatch case retains explicit unknown/abstention.
- Wrong source/truth/settings hashes, changed fixture bytes, mismatched sample
  extents, over-budget bank duration/count, excess frame/cell budgets and malformed
  intervals reject evaluation. No downloads or input overwrites occur.

Hard gates are provenance/bounds, exact metric arithmetic, preservation of injected
mechanistic differences, and zero unsupported confirmed-error claims. Audio-derived
phrase F1/IoU are **baseline measurements initially**, not invented pass thresholds
or acceptance of a real player. Record low recall and high abstention honestly.
Freeze seeds/settings before comparison and keep a fixed held-out subset when
subsequent tuning is proposed; never regenerate convenient examples after failure.

The eventual calibration receipt records source/truth/settings/tool hashes,
per-fixture metrics/coverage/status, aggregate counts and limitations. It is saved
as a new immutable artifact, not folded into the real take's ground truth. Root
owns implementation-file assignment, execution, tracker facts and publication
after releasing the current source freeze.

## Implemented operator contract

```sh
python3 scripts/phrase_evaluate.py \
  --fixture-index artifacts/benchmarks/BANK/fixtures.json \
  --pilot-index artifacts/benchmarks/PILOT/phrase-pilot-index.json \
  --output artifacts/benchmarks/NEW-EVALUATION --summary
```

All three paths are required. `--summary` retains the default compact stdout;
it never skips validation, metrics or receipt creation. Inputs and the fresh
output directory must be beneath repository `artifacts/benchmarks`. Symlink
components and parent traversal reject before reads. Output is atomic
`phrase-evaluation.json`, not a replacement of any bank, discovery or real-take
artifact. No audio decoding, inference, subprocess, dependency installation or
network request occurs. WAV bytes are read for hashes and native header extents:
`source_read:true`, `source_audio_decoded:false`, `inference_invoked:false`.

The separate phrase pilot index is schema 1:

```json
{
  "schema_version": 1,
  "bank_index_sha256": "64 lowercase hex digits",
  "instrument_registry_sha256": "64 lowercase hex digits",
  "cases": [{
    "id": "bank-case-id",
    "run_dir": "discovery/case-01",
    "analysis": {"path": "discovery/case-01/analysis.json", "sha256": "..."},
    "phrases": {"path": "discovery/case-01/phrases.json", "sha256": "..."},
    "comparisons": {"path": "discovery/case-01/phrase-comparisons.json", "sha256": "..."}
  }]
}
```

Paths are relative to the pilot index parent, or absolute beneath the same
benchmark artifact root. Artifact receipts may include `settings_sha256`;
comparisons may be null. Each bank case must have exactly one pilot row. Discovery
uses opaque byte-identical raw-mixture aliases and no generated labels or tempo
seed. Raw identity is accepted only when both analysis and phrase source hashes
equal the generated waveform identity; comparison original/input hashes must
also agree. Pilot artifacts must belong to their named run directory. Comparison
upstream hashes are verified before evaluation. Original sample-zero origin is
required; this lane does not calibrate detector latency.

Producer settings hashes, when present, are checked against canonical sorted-key
JSON. A hash derived by the pilot is labeled
`pilot_receipt_verified_producer_receipt_not_recorded`; absent settings receipts
are explicitly derived from the payload. Neither invents an original worker
receipt. The generated source, components, truth, bank/pilot indices, fixed
instrument registry and settings are hash-bound, and stable input bytes are
checked again before publication. Truth context hashes must agree with the bank.

Implemented allocation bounds are 20 MB per JSON file, 64 MB aggregate JSON,
128 levels of JSON nesting, 128 MB per hashed waveform and 512 MB aggregate
hashed inputs; at most 512 matching items, 65,536 matching edges, 60 comparisons
and 384 path landmarks. Duplicate keys, nonfinite values including overflow
exponents, invalid extents/intervals and unknown warp mapping kinds reject.
The evaluator is standard-library only and starts no numerical workers.

Boundary, attack, span and ordered recurrence metrics retain per-fixture and
micro/macro aggregates. Null semantic references are excluded; an explicitly
known empty attack reference still records false positives. Legacy attack-only
truth uses its provided `guitar_onsets_seconds`, while its missing pitch score is
not synthesized. Small-sample p95 is explicitly a descriptive nearest-rank
sample quantile with its count, never a confidence guarantee.

The comparator's `median_relative_offset_seconds` is a median of y-minus-x,
not an affine intercept when rate differs. The evaluator compares that field to
the corresponding generated median and separately publishes the generated
intercept. Raw generated landmark offsets and producer-detected motif offsets
remain alongside their warped residuals. Missing coverage stays null; paths are
never extrapolated beyond their actual support.
Timing-absorption diagnostics require an affected landmark with a generated
offset of at least 60 ms, or both endpoints of an affected rate interval of at
least 10%, to be covered with residuals below 20 ms. Changes outside path support
remain explicitly unknown with affected-coverage counts. Per-attack renderer
injections are retained as separate context and do not by themselves prove warp
absorption or note correspondence.

Compact stdout contains status, evaluation path, fixture count/duration, unsupported
confirmed-claim count, hard-gate result, read/decode/inference flags, generator-only
scope and listening acceptance false. Provenance/structure failures exit 1 with
no promoted receipt. Unsupported confirmed claims retain a valid immutable
diagnostic receipt and compact summary, status
`generated_fixture_calibration_failed_hard_gates`, and exit 1. Low audio-derived
F1/IoU or high abstention remain visible baseline measurements with exit 0;
there is no invented audio-quality pass threshold.
