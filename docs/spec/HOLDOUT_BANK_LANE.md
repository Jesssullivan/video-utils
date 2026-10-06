# Preregistered generated holdout bank

Authority: operator reattachment of the active ten-hour parallel goal;
R-HOOK-CONVERGENCE-20261004 / R-N12 / R-N13. Owner `repo_patterns` owns only new
`scripts/benchmark_holdout.py`, `tests/test_benchmark_holdout.py`, this spec and
a dated receipt. Published benchmark runner/helper and v1/v2 configurations stay
frozen. Root owns metadata admission, full bank generation, inference and release.

## Definition of done before code or tests

Implement a bounded metadata plan/validator for seeds **211 and 307**, with six
ten-second cases per seed: low32 sustain, palm-muted recurrence, legato recurrence,
missing-F0 sustain, timing reference and timing errors. Exactly twelve cases and
120 unique seconds at 48 kHz mono PCM16, with separate clean/click/noise/mixture
components. Record fixed recipe, parameter table, published dependencies and
comparison arms before any test or fixture generation. Submit the exact manifest
hash to root for admission. Do not run tests until metadata is admitted; do not
generate the complete bank before root reviews the spec/tests checkpoint.

After admission, unit tests validate independently specified arithmetic, budgets,
source/truth consistency and path/revision rejection. A bounded one-case proof
may show that new waveform parameters and source-time truth agree without
mutating published generators. No inference or algorithm selection occurs in the
proof. Full generation is held until root explicitly releases that checkpoint.
Generated labels enter evaluators only. No actual recording, model/download,
dependency installation, build, canonical worker or corpus annotation is involved.

## Holdout role and fixed discovery comparison

Both seeds are withheld from setting selection. The original development bank
is the only source for choosing the preregistered arms from
[PHRASE_WINDOW_ABLATION_LANE.md](PHRASE_WINDOW_ABLATION_LANE.md): A short-window
control; B contrast/ranking; C acoustic endpoint refinement; D B+C. Freeze their
settings before generating or scoring this bank. Contrast0.10, ranked cap10,
novelty context0.200s, endpoint-search cap0.750s and the unchanged frontend/search
settings are engineering hypotheses, not musical correctness probabilities.
If heldout results inform another knob change, retain that result and require a
new separately admitted seed. Do not relabel a reused seed as untouched.

Discovery receives opaque waveform aliases, probe/normal supported settings and
inferred pulse only; no case names, generated tempo, score, motif durations,
boundaries or warps are function inputs. Parameter/truth manifests belong to
generation/evaluation, not discovery. This is an explicit data-flow contract,
not an adversarial filesystem sandbox. All arm predictions must be saved and
hashed before evaluation reads reference truth.

## Parameter recipe admitted before tests

Recipe identifier `holdout-sha256-v1`. For seed `s`, cohort `c`, and knob `k`,
hash UTF-8 `holdout-sha256-v1:s:c:k`; interpret the first four bytes as unsigned
big-endian integer `n`, and set `u=n/4294967296`. No dependence on Python's random
hash salt or any detector result. Use `c=timing-pair` for both timing-reference
and timing-errors, preserving all nuisance parameters across that intervention.
Case IDs are `seed211-COHORT` and `seed307-COHORT`.

| Parameter | Exact deterministic formula | Scope |
| --- | --- | --- |
| first motif start | `0.6 + 0.3*u(phrase_phase)` seconds | Positive cases |
| motif duration | `0.8 + 1.2*u(motif_duration)` seconds | Positive cases, 4 generated quarter beats |
| between-motif gap | `2.0 + 0.8*u(phrase_gap)` seconds | Positive second start = first + duration + gap |
| guitar gain | `0.65 + 0.35*u(guitar_gain)` | Multiplicative synthesis gain |
| distortion drive | `2.6 + 2.0*u(distortion_drive)` | Tanh proxy for picked/legato cases; missing-F0 harmonic weights only; pure32Hz sine explicitly unaffected |
| noise amplitude | `0.008 + 0.008*u(noise_amplitude)` | Seeded white/low-pass mixture, not measured real fan |
| noise low-pass coefficient | `0.55 + 0.30*u(noise_color)` | First-order seeded-noise color |
| click amplitude | `0.06 + 0.06*u(click_amplitude)` | Independent generated click component |
| initial click BPM | `150 + 70*u(click_bpm)` | Independent of motif tempo |
| click phase | `0.2 + 0.3*u(click_phase)` seconds | First click; subsequent variable pulse intervals |
| click drift fraction | `0.04 + 0.08*u(click_drift)` | Independent linearly changing click interval across the clip |
| subdivision denominator | choose `[3,4,5,7][n(subdivision)%4]` | Intentional motif rests/tuplets, not a player mistake |
| random-noise seed | first8bytes of `noise_stream` hash, unsigned big-endian | `random.Random(seed)` only for component noise |

The complete parameter table and recipe hashes appear in `holdout-plan.json`.
No manual overrides or seed changes are accepted by this version. Metadata
validation reconstructs the frozen parameter table and rejects altered values,
dependency hashes, identities, roles or resource ceilings. The parameter table
does not contain a detector score or a generated audio quality acceptance label.

## Signal and truth design

Positive motifs have independent placement and durations0.8–2.0s with legitimate
rests/subdivisions. Their generated quarter tempo is derived only for truth;
click timing remains independent. Reference/error pairs share every parameter
and ideal event ID. The error case applies the same preregistered ±25/60ms
interventions and one omit/add experiment, retaining actual versus ideal native
sample onsets. A missing observed attack has null actual onset, never an invented
time. Actual shifted windows must remain positive, ordered and inside ten seconds.

Negative low32 and missing-F0 cases retain nearly continuous musical sustain,
independent changing clicks, slowly changing colored noise and bounded
click-shaped guitar nuisance transients. No declared recurrence means a generated
evaluation negative, not absence of music or a semantic claim about a real riff.
Missing-F0 uses harmonic synthesis without any post-synthesis nonlinearity that
regenerates F0. Its coefficient check is performed on a transient-free steady
clean span and records absolute tolerances after PCM16 quantization. Pure32Hz
preservation remains distinct from inferred C1 missing-fundamental periodicity.

Schema2 truth retains source/component hashes, native sample count/rate/channels,
generator sample-zero origin, registry/dependency/plan hashes, recurrence pairs,
pitch support, articulation, exact score/native timestamps and injected edits.
Quantize truth once with nearest-native-sample rounding. Component paths are
relative to the bank index parent. All generated audio/metadata stay ignored;
the repository stores only implementation, frozen recipe/spec and receipts.

## Bounded interfaces and acceptance

The admission checkpoint implements only `plan` and `validate PLAN`.
After metadata admission, implement a **single-case**
`proof --plan PLAN --case REGISTERED_ID --output NEW_DIRECTORY`. `plan --output`
may save a new metadata-only artifact. There is no full-generation operation
before root admits this checkpoint. New directories must be local children of
`artifacts/benchmarks/`; reject symlink components, traversal, existing outputs,
arbitrary seeds/cases and malformed/oversized metadata. Metadata JSON is capped
at1MB. One proof is at most ten seconds/480,000 mono frames/four PCM16 components,
with bounded elapsed work, at most two numeric threads and no subprocess/media
acquisition. Future full generation is at most12cases/120seconds/46.08MB raw
component payload, serial cases and600seconds overall.

Passes establish recipe, source/time/hash and generated construction consistency,
not recurrence accuracy. Required tests are independent known SHA-byte arithmetic,
exact seed/cohort budget, ref/error nuisance equality, mixed-component quantization
error bounds, actual event/native-time translation and rejected tamper/path cases.
A bad coefficient, inconsistent truth or changed dependency is a structural
failure. Unknown/missing quality metrics are not passes. Record the admission
hash, test evidence and one-case result before root chooses full-bank execution.

## Initial checkpoint

At2026-10-05 23:53UTC the repository was at signed published baseline `eb378bd`;
parallel report/experiment/receipt owner work was dirty and preserved. No test,
holdout fixture or inference was run for this lane before writing this contract.
The next checkpoint is a concrete metadata artifact/hash for root admission.

The metadata-only checkpoint is saved at
`artifacts/benchmarks/holdout-admission-211-307/holdout-plan.json`, SHA256
`495ad2f3f553b0bd7030ac797b6e8589f37748df657219c075d0fc4ce7491e74`;
recipe SHA256
`0f8223e9adc4deb113c87a5b231b76bec33f573feabb03ec32bd8f565a5a3c63`.
No tests, audio generation or inference preceded this artifact. Root admission
was pending at that checkpoint. Root subsequently admitted this exact hash and
released tests plus one timing-errors construction proof. Full-bank generation
remains unimplemented and requires a separate root review.

## Admitted single-case proof implementation

The worker now supports `proof --plan PLAN --case seed211-timing-errors --output
NEW_DIRECTORY` (or the registered307 counterpart). It requires the exact
root-admitted plan byte hash; it does not mutate admission metadata. Outputs are
four PCM16 WAV files, `truth.json` and schema2 `fixtures.json`, with paths relative
to that index. The proof role is `single_case_construction_proof_not_inference`;
there is no discovery, quality metric, score-based knob choice or full-bank
operation. The full12-row metadata plan remains separate from this one-case index.

For each four-quarter motif, attacks have rational beat positions
`[0,d,2*d,3*d,3*d+1,3*d+2]/d`, where `d` is the admitted subdivision denominator.
Second-motif quarter attacks shift by +25,-25,+60,-60ms respectively. The first
of its final two subdivision attacks is omitted; a separately identified extra
attack occurs halfway between the last intended attack and motif end. The first
motif remains unedited. All attacks use a tapered exponential palm-mute envelope,
the admitted gain/drive, and MIDI24,29,34,29,24,39. Support is capped at40ms and
trimmed at the declared motif endpoint. This precisely describes the generated
intervention, not a performance judgment or a physical amplifier model.

The seeded-noise component uses a half-white/half-first-order-low-pass mixture.
The independent3.5kHz exponential click component has admitted level/phase and
interval `60/click_bpm * (1 + click_drift_fraction*t/10)`. Clean/click/noise are
summed before separate nearest-PCM16 quantization; rendered component sum versus
rendered mixture must differ by at most two PCM16 LSB. Clipping is a rejection,
never an implicit gain change. Native headers, all component hashes, actual and
ideal timestamp translations, null omission, event IDs, source mixture receipt
and generated sample-zero origin are checked. Dependency and worker byte hashes
must remain unchanged across proof execution. One serial stdlib renderer uses
no numerical thread pool, download, subprocess or real media.

Separating setting selection from holdout evaluation follows the motivation in
[Dwork et al., Generalization in Adaptive Data Analysis and Holdout Reuse](https://arxiv.org/abs/1506.02629).
This preregistration workflow does not implement their differentially private
reusable-holdout mechanism or claim its statistical guarantees.

## Full-generation code checkpoint (execution held)

After review of9tests and the one-case proof, root authorized full-generation
**implementation only**. Actual12/120 generation waits until the independent
phrase owner freezes exactA/B/C/D math and harness source and root releases
execution. The admitted plan/recipe bytes stay unchanged. Historical one-case
proof provenance binds its earlier renderer revision; it is not silently
attributed to this extension. There is no holdout-derived setting selection.

Implement `generate --plan PLAN --output NEW_DIRECTORY [--timeout-seconds600]`.
Accept only the admitted byte hash, exact twelve registered rows/120seconds,
native48kHz mono and a positive deadline no greater than600seconds. Cases run
serially without a numeric thread pool; generated labels are outputs only, with
no discovery call. A failure preserves an explicit `failure.json` listing
completed cases and does not create a successful aggregate index. Source/config/
renderer hashes are checked before and after every case. Safe fresh paths,
bounded48WAV payloads and bounded metadata remain mandatory.

Timing-reference uses identical nuisance parameters and score positions to
timing-errors with all interventions disabled. Palm-muted recurrence uses the
unedited motif and short distorted pick envelopes. Legato recurrence uses
continuous gently tapered note segments at the same intentional subdivision
positions; only its motif beginnings are picked attacks, remaining events are
pitch transitions. Low32 is a pure32Hz sustain on0.5–9.3seconds with no distortion
applied to its fundamental. Missing-F0 uses C1harmonics2,3,4,5,7 on that span,
varying coefficients with admitted gain/drive, and no post-synthesis nonlinearity.
Both negative cohorts include separately labelled40ms click-shaped guitar
nuisance transients on0.4and9.45seconds; their declared recurrence list is empty.
The transient-free missing-F0clean PCM interval1–7seconds must pass the frozen
independent joint sinusoidal regression with absolute5e-5coefficient tolerance,
including F0 as a fitted regressor. All six cohorts use the same previously
specified noise/click recipe; timing intervention pairs share those components
exactly. No generated template/truth/BPM becomes a discovery input.

Aggregate schema2 `fixtures.json` contains twelve cases with relative
source/component/truth paths and hashes, native extents, case durations, renderer/
dependency/admitted-plan hashes, bounded elapsed work and explicit generator-only
truth scope. Each truth uses bank-index-relative paths; proof outputs retain
their original single-directory relative-path contract. New tests exercise
budget/deadline/aggregation/failure receipts with mock cases or the existing
proof, rather than generating a heldout bank before root's release.
