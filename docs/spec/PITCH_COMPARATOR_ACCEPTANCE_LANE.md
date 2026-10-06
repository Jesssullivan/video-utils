# Independent pitch comparator acceptance

Authority: operator's full parallel development request, repository AGENTS.md,
R-HOOK-CONVERGENCE-20261004 / R-N12 / R-N13. Owner `guitar_features` owns this
plan and read-only metric review. `tonal_inference` owns the isolated Basic Pitch
runtime/adapter; its `tonal_audit` owns model/runtime/windowing/clock review.
Root owns admission, actual inference, integration and publication. This lane
changes no current pitch worker, evaluator, catalog or model registration.

The result should show where a learned pitch estimator adds useful evidence for
distorted nine-string practice. It must expose failures on low C1, rapid sweeps,
legato, harmonics and silence rather than declare a winner from favorable
interiors. Model activation, decoded event amplitude and pYIN voicing probability
remain different, uncalibrated measurements. Estimator agreement does not establish
played-note truth, intended notes, strings/frets or real performance mistakes.

## Baseline and fixed cohorts

The published generated pilot reports raw pitch accuracy 319/319 for the high
branch and 745/745 for the low branch, among **3,750 total branch frames**. It also
reports three high-branch false-voiced silence frames and explicit padded,
transition, polyphonic and range exclusions. These controlled eligible-interior
results do not describe all-frame or real-guitar accuracy. Preserve the immutable
[baseline receipt](../agent-notes/2026-10-05-calibration-pilot-results.md) and
[independent audit](../agent-notes/2026-10-05-calibration-contract-review.md).

Use the same hash-bound technical-v2 bank and selected components as the frozen
[pitch calibration contract](PITCH_CALIBRATION_LANE.md). Four serial generated
jobs total exactly **30 input seconds**; each starts at zero. Discovery receives
opaque audio aliases and supported settings, never truth, tuning-derived output
filters or score labels. Each cohort is fixed before examining learned results.

| Job and component | Coverage | Cohorts retained within that span |
| --- | --- | --- |
| c1-missing-fundamental / clean | 0–8 s | C1 periodicity without synthesized F0, sustain, lead/tail guitar absence, harmonic-note hallucination |
| tuning-ladder / clean | 0–8 s | All nine registry pitches, clean versus tanh conditions, 300 ms condition interiors, 150 ms rests, onset/end timing |
| legato-transition / mix | 0–6 s | Low and upper sustain, analytic glides, pitch-change versus picked-attack labels, nuisance mixture and silence; later passage explicitly unrequested |
| sweep-and-polyphony / mix | 0–8 s | Two 80 ms-per-note sweeps, 3.5–5.0 s three-note chord, upper sustain, rests and nuisance mixture; 8–10 s explicitly unrequested |

The source-bound registry retains MIDI 24,29,34,39,46,51,56,60,65 and the supplied
Eb2→Bb2 interval. Operator pitch classes, inferred octaves and theoretical A440
frequencies do not become measured real notes. Generator truth includes genuine
events separately from condition boundaries: a clean/tanh boundary is not a new
note onset. Analytic glides are trajectories rather than invented picked notes.
All absence intervals mean guitar absence, not necessarily silence in a mixture.

For the operator's actual take, use the exact existing pYIN excerpt spans only
when input/timeline hashes agree. Count those as a **separate** bounded discovery
run, never another part of the generated 30-second score. It receives no scored
accuracy, omission verdict or musical-error confidence. Coverage, event density,
octave/activation disagreements and listening-review spans are descriptive.

## Runtime, output and clock admission

The pinned upstream model consumes 22,050 Hz mono windows with 43,844 samples.
Its inference path prepends overlap context, uses overlapping windows and removes
edge output frames before joining arrays. Require adapter receipts to expose
every window, padding count, retained output range and original resampled extent;
do not infer these from a claimed output duration.
[Pinned upstream inference](https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/inference.py),
[pinned constants](https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/constants.py).

Per generated pilot: at most 24 model windows, six excerpts, one CPU session,
two numerical threads, 900 seconds overall, 20 MiB raw numeric arrays, 5,000
events per decoder preset and 100 MiB total result/temporary audio. The admitted
worker has a 600-second run deadline and monitored 1 GiB RSS ceiling; the nested
audit verified owned-process cleanup and measured peak reporting. A future bank
controller may enforce a stricter 180-second per-job limit, but the current
worker must not be described as implementing that proposed limit.
Count actual windows before inference; do not
discard a cohort to satisfy the cap. Timeouts or incomplete jobs retain negative
evidence and cannot receive completed-pilot status. No duplicate inference is
authorized for this review lane, and existing environments remain unchanged.

Require an immutable run manifest with model-file hash, registration evidence,
isolated dependency lock/install receipt, worker/decoder hashes, tensor names and
shapes, provider, library versions, exact command and effective decoder settings.
Read model/license declarations from the qualification owner; this acceptance
review makes no independent license interpretation. Reject stale model/input/
array hashes, wrong tensor schema, object/pickle arrays, NaN/Inf, index overflow,
unrecorded gaps or padded audio promoted into source coverage.

Retain both the raw activation clock and the decoder event clock. Upstream event
conversion applies a window-index adjustment beyond the nominal sample-hop
clock; verify the pinned formula independently at every seam. This adjustment is
not microphone latency calibration. No fitted shift, tuning offset or time warp
may improve benchmark scores after results are observed.
[Pinned event-clock and decoder implementation](https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/note_creation.py).

Raw outputs must retain named `note`, `onset` and `contour` numeric arrays,
per-row excerpt/native/source time, bin-to-MIDI mapping, support/padding/seam
flags and byte hashes. Decoded events retain raw frame indices, unclipped event
times, source spans, MIDI, amplitude, preset and boundary uncertainty. If a
display span is clipped, retain the original event and clipping reason separately.
No note event crosses an unprocessed gap. Effective duration floors are measured
after frame rounding and strict decoder inequalities; a requested 25 ms floor
is not proof that 25 ms notes survive.

Retain the declared full model note range, MIDI 21–108, without an instrument
filter chosen from reference notes. A C1 bin is representable in that range;
representation alone is not tested C1 accuracy. Contour bins and decoded bend
estimates, if available, remain distinct from semitone note activations.
[Pinned frequency-bin declarations](https://github.com/spotify/basic-pitch/blob/9991303bba609a3b93089d13ec80d1d495083596/basic_pitch/constants.py).

The model owner confirms two fixed presets reusing identical arrays: floor
127.70 ms and technical floor 25 ms, with onset/frame thresholds 0.5/0.3. The
adapter uses **project threshold-active runs with local onset splits**; it does
not claim upstream Melodia or complete postprocessing parity. Persist that
decoder identity and effective controls beside every event list. The model and
window/clock source may be qualified independently of project event decoding.
Record deviations before inference. Do not choose the best decoder per truth
region; publish both, including extra harmonic notes and false positives.

## Independent metrics and fair comparisons

Publish three views with separate denominators rather than one accuracy number:

1. **Native evidence:** preserve unchanged pYIN low/high complete-window scores
   and exclusions. Score ML activations/events at their audited clocks, retaining
   transition, seam, padding, chord and absence labels. A roughly two-second ML
   input window is not a verified 64 or 256 ms DSP window; its receptive-field
   extent is unknown unless independently established. Conservative whole-input
   support inside one truth region can yield no eligible ladder/sweep interiors;
   report null and N=0 rather than borrow pYIN eligibility.
2. **Paired timestamps:** use a predeclared 16 ms audio-relative grid. Pair ML
   activation rows by nearest audited raw time within one-half nominal ML hop,
   with earlier-row tie breaking and no interpolation of pitches/events. Mark
   unavailable pairs instead of copying nearby estimates. Compare each pYIN
   branch separately at the same times. Preserve branch-range and input-context
   masks, and report how many frames each mask removes. This pointwise view is
   explicitly a label comparison, not equal temporal resolution or complete
   receptive-field evidence.
3. **Event and articulation diagnostics:** match decoded events to generated
   score events, never to every `pitch_regions` row or every spectral transient.
   Keep picked attacks, legato pitch transitions, sweeps, sustain and chord
   voices separate. pYIN has no native picked-event detector; report its
   transition evidence independently rather than fabricate comparable notes.

For monophonic ML top-one diagnostics, choose highest raw note activation with
lowest-MIDI deterministic tie breaking, before reading truth. Publish fixed
threshold voiced coverage and ±50 cent raw pitch/chroma scores with all eligible
true-voiced timestamps in the denominator, including abstentions. A candidate at
an octave gets chroma agreement but remains an octave error. Publish absolute
and signed cents, octave and other semitone errors, false guitar-voicing during
absence, recall/precision and explicit Ns/nulls. Do not combine low/high pYIN
hypotheses into apparently recovered polyphonic notes or select a branch by truth.

For ML polyphony retain the entire thresholded pitch set: micro TP/FP/FN at
±50 cents, cardinality error, missing chord voices, extra harmonic voices and
empty-set behavior. One-to-one pitch matching maximizes cardinality then minimizes
absolute cents; deterministic ties use ascending reference/output IDs. Never
remove harmonics using ground truth. C1 missing-F0 gets separate fundamental
recall, octave substitution, extra-partial pitch count and absence false alarms.
Its rendered missing-F0 signal qualification remains the bank owner's evidence.

Predeclare event onset tolerance 50 ms and pitch tolerance 50 cents. Report both
onset-only and onset-plus-offset matches; offset tolerance is the larger of
50 ms and 20% of reference duration. Match one-to-one by maximum cardinality,
then minimum summed absolute onset residual, with stable ID ties. Report FP,
FN and all unmatched short/sweep/legato events, event overlap, merged/split
hypotheses and duration residuals. A detected onset is not necessarily a picked
attack. Boundary-truncated references/events have a separate cohort and cannot
silently vanish from counts. Glides use analytic instantaneous pitch diagnostics,
not arbitrary note boundaries; with no bend estimate, mark the missing continuous
representation rather than round the reference glide into favorable semitones.

Publish signed onset/end residual distributions, negative timing bias, N and
small-N null p95. Aggregate micro counts by sum and retain case/register/
articulation/component strata. Do not average undefined rates, omit noisy cases,
threshold-sweep on this pilot or declare statistical superiority from few
controlled events. Runtime/RSS/output bytes and coverage complement quality;
no combined leaderboard score is authorized.

## Acceptance and independent review

Before numerical acceptance, independent manual oracles must cover octave-only
chroma agreement, abstention as an accuracy miss, silence false positives,
multiple harmonic hypotheses against one note, one output matching only one
chord voice, tie-stable matching, duplicated/split events, short-note omissions,
legato without a pick, and differing grids/coverage. Clock oracles cover source
offsets, first/last windows, every overlap seam, padding and unshifted negative
residuals. Decoder tests distinguish requested and effective minimum duration.

Admission requires complete provenance/resource checks and the four fixed
cohorts, or an explicit partial/unavailable receipt. Numerical quality is an
honest baseline: low-register failure, octave substitution, extra harmonics,
silence false alarms, merged sweeps and missing sustain remain visible even if
execution succeeds. Runtime/model validation and metric correctness are separate
from useful musical accuracy, real-take listening and future Logic acceptance.

The independent reviewer reads concrete immutable arrays/event manifests and
recomputes a small fixed oracle subset without rerunning inference. Report source,
runtime, model, timeline, metric and listening states separately. Any proposed
evaluator implementation is a later root-owned release; the published 17-test
pitch evaluator and catalog remain frozen throughout this planning lane.

## Concrete frozen receipt readback, October 6 UTC

The runtime owner and nested audit supplied concrete receipts. Independent
acceptance readback loaded existing numeric arrays only; it did not import ONNX
Runtime, invoke a model, decode source audio or rerun inference.

| Artifact | Verified identity / scope |
| --- | --- |
| Durable runtime receipt | SHA256 `31db3fe2cefff4caae8f83dc6defdf286aef227752a0bda3c7b14bcd0a313cc4`; installed-runtime audit is owned by `tonal_audit` |
| Actual `comparison.json` | SHA256 `ef86dbcaa1743d44ff24e2aa635deddaadce6a25653b35b537329e2a22b50e37`; earlier conservative run `20261005T211103Z-c6d0bac2fcd2` |
| Actual activation NPZ | SHA256 `61c6bbbe235a5ae9386854cd9d855294b08b8abbdbb71b63961113483d6429ff`; 32 finite arrays, four 430-row excerpts |
| Corrected generated `inference.json` | SHA256 `67cd53bcebc357c9469e208455e02fb1c6e9a719a4d66cde273d16ea8f85f8dc`; separate 12-second stepped-harmonic pilot |
| Corrected generated activation NPZ | SHA256 `fa35adc5d24b8081e5f523e03aa055d3d012c3e21094d4959949e05f68576590`; 32 finite arrays, four 258-row excerpts |

Actual coverage is 20 seconds, four five-second excerpts including the ending,
16 model windows, and 17/65 project events at 127.7/25 ms respectively. The
analysis-input SHA256 `dbd8b40eaf9928eb2f80791cfbdc9c3562ed10b57bcf859ad96d8a202fc93b12`
matches the existing pYIN input from that earlier run. Excerpt endpoints differ
by at most 30.167 microseconds from independent 16 kHz/22,050 Hz quantization;
do not claim byte-identical resampled inputs or perfectly identical endpoints.
This receipt does not analyze the newer clarity render or grade the full take.
Each five-second excerpt has 142/430 rows from entirely unpadded input windows.
That count is not stable monophonic eligibility or musical correctness.

The corrected **linear** missing-F0 proxy gives **0/258 C1 top-one membership**:
133 threshold-active C2 rows, 29 C3 rows, 95 C4 rows and one top-one abstention
at threshold 0.3. The earlier nonlinear missing-F0 proxy could regenerate F0
and is superseded. These are all-frame descriptive output counts, not native
context-qualified recall, polyphonic note correctness or real-take performance.
All four three-second pilot excerpts have **zero** rows from model input windows
without padding, so this pilot cannot provide conservative whole-input-support
accuracy. Its sweep/tapping labels mean phase-discontinuous stepped harmonic
proxies, not qualified physical legato or tapping articulation.

Three stored clocks were independently recomputed at fixed rows. At row 142,
nominal and empirical model times are 1.648616780 s while input-window projection
is 1.640090703 s. At row 172, nominal is 1.996916100 s, empirical model time
1.986590023 s and input-window projection 1.988390023 s. Preserve all three;
none establishes microphone latency. The project decoder gates corrected elapsed
duration using `>=`: 127.7 ms accepts eleven nominal hops (127.709751 ms), unlike
upstream's rounded-frame strict inequality. At the model-clock correction step,
three hops can span only 24.503855 ms and fail the project 25 ms floor; four hops
span 36.113832 ms. Minimum duration is therefore clock/index dependent.

Still pending: exact fixed-bank 30-second cohort discovery, paired-grid and
native-context denominators, absence false alarms, complete fundamental versus
harmonic-set metrics, event TP/FP/FN and residuals, chord voice cardinality,
glide/sweep/sustain/legato strata and source-offset oracles. The current 12-second
pilot does not replace those cohorts. Admission of an experimental MCP hook and
skill does not imply any of these quality metrics passed or that the main DAG
automatically selects learned pitch.

## Pure evaluator candidate: CLI only

Root released a separate stdlib/finite-array reader implementation:
`scripts/learned_pitch_evaluate.py --fixture-index BANK --pyin-pilot-index PYIN
--learned-pilot-index ML --output NEW_DIRECTORY --summary`. It receives existing
artifacts only and performs no audio decoding, model inference or downloads.
The published `pitch_evaluate.py` stays unchanged. The new candidate is CLI only;
catalog, MCP, skill and recipe admission require root's separate review. The
existing 12-second proxy and sparse actual receipt do not satisfy its fixed bank
index, so no complete-cohort acceptance score is claimed from those artifacts.

The implemented learned index is schema 1 with `bank_index_sha256`,
`instrument_registry_sha256`, `model_sha256`, `adapter_sha256`,
`runtime_manifest_sha256`, `budget_seconds: 30` and exactly four `jobs`.
Each job has `case_id`, `component`, `status: completed_measurements`,
`input_path`/`input_sha256`, `truth_path`/`truth_sha256`,
`comparison_path`/`comparison_sha256` and
`activations_path`/`activations_sha256`. Paths are absolute beneath repository
`artifacts/benchmarks` or relative to the index. It requires a full bound
`comparison.json`, not an unbound `inference.json`. Comparison settings must
declare the fixed project decoder and 127.7/25 ms presets, 0.5/0.3 thresholds,
explicit start zero and the fixed job budget. Identity fields bind the known
qualified model SHA and supplied adapter/runtime receipts; package installation
and model-file byte requalification remain the separate runtime audit's scope.
The existing pYIN index supplies canonical component/mixture/header validation
and immutable bank truth bindings. Historical actual discovery receipts never
enter a generated-truth scoring index.

Require finite named numeric arrays without pickle/object data, verified shapes,
clock/window-index formulas, model support maps and exact excerpt coverage before
calculating metrics. Keep primary model-clock metrics and predeclared nominal/
input-projection sensitivity views labeled separately; never choose the clock
with the lowest error. Enforce existing file/resource/path bounds, including
uncompressed NPZ byte limits and strict JSON metadata. Record raw-array bytes read
and no source decoding/inference honestly; waveform hash/header reads, if used,
must be declared rather than claiming no source reads.

The implemented reader additionally verifies supplied event frame identities
against a recomputation of the fixed project decoder from raw arrays. Event
mean note activation and maximum onset activation are independently recomputed
from those arrays with 1e-7 numerical tolerance; malformed DEFLATE becomes a
structural diagnostic rather than escaping the receipt path. It audits
boundary flags; offset metrics exclude truncated references and boundary-touching
estimates with explicit counts, while onset-only findings remain visible. This is
activation postprocessing verification, not model inference or audio decoding.
Matching uses min-cost maximum bipartite matching; articulation strata report
recall from the global assignment instead of incorrectly counting every other
articulation's predictions as false positives.

Save `learned-pitch-calibration.json`, `learned-pitch-frame-errors.csv` and
`learned-pitch-event-errors.csv`; compact stdout follows full validation.
Structural mismatches retain diagnostics without promoted scores and exit 1.
Trusted numerical receipts with unsupported real-note/listening claims retain
metrics and fail claim gates with exit 1. Fresh-output violations exit 2.
Poor model quality remains visible regression-alert baseline evidence with
exit 0; it cannot be tuned into a synthetic pass. Independent manual oracles
cover matching conflicts, octave-only agreement, negative residuals, duplicate
events and unsafe arrays. Structural generated tests do not run Basic Pitch.
