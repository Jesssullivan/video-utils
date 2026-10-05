# Expanded generated calibration bank

Authority: operator ten-hour parallel goal; R-HOOK-CONVERGENCE-20261004,
R-N12/R-N13. Owner `repo_patterns` currently owns this new specification only.
This began as a research-only contract. Root released implementation after
signed publication `45a1313ccbcb0ecc097f3a017979254e5719a3c6`; the implemented
bank checkpoint is recorded below. Root's publication/source freeze protected `scripts/benchmark.py`,
`tests/test_benchmark.py`, `program/benchmarks.json` and all active full-suite
inputs during planning. Explicitly assigned implementation now owns the runner,
new bank helper/tests/configuration, this spec and its dated receipt; root owns
hooks, recipes, publication and actual composite calibration.

## Definition of done before implementation

Design a deterministic generated bank with at most 12 cases and 120 seconds of
unique source audio. Cover the exact nine-string registry, approximately 32 Hz
preservation, absent-fundamental periodicity, distorted attacks, legato, sweeps,
polyphony, rests, syncopation, tuplets, variable tempo, click overlap and injected
timing/attack edits. Record sample-accurate signal and score truth, independently
check rendered components, and coordinate the pitch/phrase evaluator contracts.
Define task-specific tolerances, abstentions, failure states and resource bounds
before changing the implementation. No model, dataset, real recording or library
download; no heavy build or host configuration change.

After release, completion requires preserved v1 waveform hashes, validated v2
source/component/truth/configuration hashes, meaningful independent metric tests,
a bounded real-worker fixture smoke in a fresh ignored directory, and a durable
receipt of successes, missing coverage and failures. A successful fixture run
does not establish musician accuracy, perceptual restoration or actual-take
listening acceptance. No generated labels enter the operator's corpus/review.

## Current facts and primary research

The published `technical-v1` configuration has three eight-second 48 kHz mono
cases and only restoration, periodic-transient and recurrence measurements.
Its runner requires exactly those three cases, limits mono PCM to 384,000 frames,
and greedily matches event pairs by increasing absolute offset. Quality alerts
are measurements and currently do not fail the process. Its dedicated click
stage analyzes candidates without attenuation. There is no pitch-calibration
stage or note/performance acceptance. Prior passing fixtures demonstrated the
25 ms restoration-delay regression and its repair; they do not qualify a general
guitar-restoration model. Existing receipts remain in
[BENCHMARK_LANE.md](BENCHMARK_LANE.md).

Primary documentation checked October 5, 2026:

- [mir_eval onset implementation](https://github.com/mir-evaluation/mir_eval/blob/main/mir_eval/onset.py)
  scores reference/estimated onset timestamps with a 50 ms default window and
  precision/recall/F-measure. We retain stricter 20 ms click timing separately;
  an onset score does not identify the causal instrument.
- [mir_eval transcription implementation](https://github.com/mir-evaluation/mir_eval/blob/main/mir_eval/transcription.py)
  uses maximum matching with separate onset, pitch and optional offset criteria;
  defaults include 50 ms onset and 50 cents pitch tolerances. These are evaluation
  conventions, not universal thresholds for a musician's mistakes.
- [librosa 0.11 pYIN](https://librosa.org/doc/0.11.0/generated/librosa.pyin.html)
  provides F0 candidates, voicing flags and algorithmic voicing probabilities;
  frame centers and padding affect timestamp interpretation. Its recommended
  minimum is around C2, so use below C2 needs explicit measured calibration.
- [librosa 0.11 DTW](https://librosa.org/doc/0.11.0/generated/librosa.sequence.dtw.html)
  supports constrained alignment and path backtracking. Alignment can absorb
  timing differences; retain pre-warp differences as well as post-warp residuals.
- [mir_eval tempo implementation](https://github.com/mir-evaluation/mir_eval/blob/main/mir_eval/tempo.py)
  accepts two tempo references with a relative-error tolerance. It is not an
  automatic choice of intended meter or a variable-tempo ground-truth protocol.

The choices below are engineering proposals. These sources do not validate the
fixture realism, chosen alert thresholds or nine-string performance detection.
No new dependency on mir_eval is required: an independently tested bounded
matcher may implement the declared scoring convention in the standard library.

## Fixed bank proposal: technical-v2

All new cases are deterministic 48 kHz mono PCM16, with four separately rendered
references: clean generated guitar, click, noise and their mixture. The mixture
must avoid clipping; record common component gain and post-quantization hashes.
Do not claim the quantized mixture equals the sum of independently quantized
components bit for bit; component reconstruction error is bounded by quantization.
Retain the v1 generator definitions and exact waveform hashes for the first
three cases. Total: `3×8 + 8 + 8 + 10 + 10 + 5×12 = 120` seconds, 12 cases.

| ID | Seconds | Generated content and scoring purpose |
| --- | ---: | --- |
| low32-sustain | 8 | Existing 32.000 Hz coherent preservation sentinel, unchanged |
| palm-muted-recurrence | 8 | Existing distorted/rest-containing motif and coincident click attack, unchanged |
| legato-recurrence | 8 | Existing smoothly repeated pitch motion, unchanged |
| c1-missing-fundamental | 8 | C1 periodicity 32.703195663 Hz with harmonic indices 2,3,4,5,7 and exactly zero synthesized F0 coefficient; differentiate octave errors from LF preservation |
| tuning-ladder | 8 | All nine registry MIDI values 24,29,34,39,46,51,56,60,65; paired clean/distorted conditions and declared rests |
| legato-transition | 10 | Sustained low-register pitch transitions and logarithmic glides, with few picked attacks and explicit pitch-transition labels |
| sweep-and-polyphony | 10 | Fast ascending/descending registry pitches plus a three-pitch simultaneous section; low-window ambiguity and monophonic abstention |
| rest-syncopation-tuplets | 12 | Fixed 178 quarter BPM, ordinary rests, offbeat accents and 3/5/7 subdivisions; intentional tuplets are not timing mistakes |
| variable-tempo | 12 | Continuous quarter-beat phase with linear 178→210 BPM ramp on seconds 1–11, preserving pitch/articulation independently |
| click-overlap-abstention | 12 | Click-only template, isolated clicks, clicks coincident with independent distorted picks, sustained C1 and guitar-only lookalike transients |
| timing-reference | 12 | Repeated synthetic score at 178 BPM, with event IDs, real rests and exact no-edit reference |
| timing-errors | 12 | Same score with -25,+25,-60,+60 ms injected attack shifts, one omitted attack and one extra attack; generated interventions, not real performance labels |

Missing-fundamental construction uses explicit harmonic synthesis with recorded
amplitudes/phases. Apply no later nonlinear waveshaper that could regenerate F0
through intermodulation. Check the steady-window coefficients by a joint harmonic
fit or an independently chosen coherent interval, including F0; a single FFT bin
on a noninteger number of cycles is insufficient. Label this a distorted-style
harmonic proxy rather than an amplifier simulation. F0-preservation gain is
`not_applicable_absent_component` for this case, never division by a near-zero
coefficient. The separate 32 Hz sentinel retains its existing protection test.

The ladder has a 0.5-second silent head, nine slots of 0.6-second active pitch
plus 0.15-second rest, and a 0.75-second tail. Each active pitch has 0.3-second
clean and 0.3-second tanh-distorted sections with recorded condition boundaries.
Preserve ascending string 9→1 order and the supplied Eb2→Bb2 interval. The 256 ms
low-register window leaves very few uncontaminated frames per condition; report
that sample count and abstention instead of pretending robust p95 qualification.
The theoretical tuning registry is generator input, not measured recording tuning.

New click templates are 5–120 ms intervals chosen by the generator where both
guitar and noise components are zero. The explicit declaration is generator-only.
Detection is default; attenuation is a separate opt-in fixture experiment with
strength at most 0.5 and separate output hashes. Never publish that declaration
as a valid click-only interval for the actual take.

## Shared truth schema, version 2

`truth.json` records `schema_version: 2`,
`kind: synthetic_generated_signal_and_score_truth`,
`ground_truth_scope: generator_only_not_musician`, generator/configuration/registry
hashes, seed, and source/component byte hashes. `source` includes sample rate,
channels, sample count, mixture SHA-256, `audio_start_seconds: 0` and
`origin_evidence: synthetic_generator_sample_zero`. This is a known generator
origin, never a missing-container-PTS inference for real media.

Keep these task-specific sections explicit:

- `generated_score.events`: stable event ID, optional generator string ID,
  MIDI/frequency or simultaneous pitch set, rational quarter-beat position,
  ideal onset/duration, observed onset/duration in native samples and source
  seconds, articulation and any injected edit. Rest and pitch-transition events
  are distinct from picked-attack events. No observed onset is fabricated for an
  intentionally omitted attack. Include `rounding: nearest_native_sample` and
  both analytic ideal time and integer sample time.
- `pitch_regions`: start/end source seconds, frequencies/MIDI set,
  `monophonic`, condition, articulation and `expected_abstention_reasons`.
  `pitch_trajectories` specify endpoints and logarithmic frequency interpolation
  for glides; there is no forced nearest-note label during a glide.
- `click_events`: native sample and source seconds, amplitude/template ID,
  overlap class (`isolated`, `sustain_overlap`, `pick_overlap`), and separate
  guitar-only lookalike negatives. Store template span and component-zero proof.
- `tempo_segments`: analytic tempo/phase model, continuity anchors,
  quarter-beat units and `pulse_times_seconds`. For the linear ramp, obtain pulses
  from the integral of BPM/60 and round to samples; do not approximate using a
  single global BPM. Tuplets retain rational subdivision positions.
- `phrase_spans_seconds`, `boundaries_seconds`, `recurrence_pairs` and
  `warp_reference` (`source_times_seconds`, `target_times_seconds`,
  `mapping_kind`). Pair coordinates also have phrase-relative versions.
  `observed_articulation_context` and `expected_abstention_reasons` retain rest,
  legato, sweep, polyphony and constant-texture context. Container edges 0/duration
  are not discovery boundaries. Unknown semantic phrase identity remains null.
- Known noise-only spans, steady LF windows, clean-reference comparison spans
  and transition masks. Empty lists mean no applicable reference, not a pass.

Discovery workers receive audio and their normal supported settings only. They
must not receive score events, pitch truth, phrase boundaries or warp references.
Evaluators read those labels afterwards. Root's clarified v2 baseline is
**unseeded for every case**, with no `--bpm` and no truth-derived waveform
template. Historical v1 retains its existing declared178/template controls.
A future explicitly requested declared-BPM experiment must be separately
tagged `reference_grid_supplied`; it is not implemented by the v2 default.
A reference-pair evaluator may use the generated score only
when its output clearly describes a generated reference task, not score-free
discovery. No labels or acceptance states are transferred to real recordings.

## Metrics, tolerances and failure states

Use maximum-cardinality one-to-one event matching within each tolerance, with
minimum absolute error as a deterministic secondary objective. Do not duplicate
credit, greedily sacrifice match count, or fit/subtract a detector delay.
Retain raw matched offsets, unmatched events, sample counts and denominators.
Version this v2 matcher separately from historical v1 scores.

| Task | Primary measurement | Diagnostic and abstention policy |
| --- | --- | --- |
| Click timing | Precision/recall/F1 at ±20 ms, split by overlap class | Also ±10/50 ms; signed median/absolute p95 with N shown; empty truth has null recall and explicit false positives |
| Picked attack discovery | One-to-one P/R/F1 at ±50 ms | Also ±20/100 ms; do not require an attack at every legato pitch transition; report rest/lookalike false positives separately |
| Injected timing | Offset sign and absolute estimation error against -25/+25/-60/+60 ms interventions | ±10 ms error is a proposed calibration alert for resolvable picked attacks, not a human timing-quality threshold; no correction chosen to improve score |
| Pitch | Cents error, voiced coverage, octave errors and chroma-only errors separately | ±50 cents convention; score window-complete monophonic interiors separately from transitions and padded edges; silence false voicing and polyphonic/rapid-transition abstention retained |
| Phrase boundaries | One-to-one P/R/F1 at ±50 ms | ±20/100 ms also reported; no scoring container edges; overlapping windows cannot satisfy one boundary twice |
| Phrase spans/recurrence | Maximum-cardinality one-to-one interval IoU ≥0.5 | Also ≥0.75 diagnostic, paired minimum IoU and unmatched regions; compare relative warp shift/rate against generated mapping without hiding pre-warp differences |
| Tempo | Local pulse errors and segment BPM relative error | Record exact, half/double candidate errors separately, no automatic octave equivalence; a single global estimate on a ramp has no qualified local-tempo pass |
| Restoration | Existing 32 Hz coherent gain, gain-adjusted quiet change, clean-reference error | Keep sample-index alignment and native extent; do not normalize away LF loss or treat a gain-only change as denoising |
| Click attenuation | Event-specific removed high-frequency click component and guitar-error windows | Pick-overlap must abstain; accepted isolated click should retain ≥50% original click amplitude at strength0.5; preserve coherent LF and attack windows |

Quality measurements do not silently become hard model-accuracy gates. Initial
candidate P/R, pitch cents and phrase IoU are baselines; weak/empty output remains
visible. Known safety regressions may form explicit gates: source/hash/extent
changes, alteration on declared bypass, 32 Hz sentinel attenuation below -0.5 dB,
attenuation applied at protected independent pick overlap, or added real-ground-
truth claims. Proposed overlap/LF tolerances reuse existing click tests: under
1% relative guitar-window error and under 1e-5 relative change of the protected
LF complex projection where its denominator is nonzero. Small-N percentiles
always show N and are not throughput or perceptual acceptance.

For a pure isolated generated click at strength0.5, separately flag less than
20% measured high-frequency amplitude reduction as ineffective and more than
50% reduction as excess removal (allow recorded quantization/measurement error).
This proposed fixture alert range is an engineering test, not listening quality.
Zero removal must not receive efficacy credit simply because it preserved the
guitar. Algorithmic pYIN voicing probabilities are not calibrated probabilities
that a note label or musician error is correct.

Use separate structural and evaluation states:
`failed_structural` (tamper, changed worker, extent/path/schema/resource failure),
`completed_with_regression_alerts`, `completed_measurements`,
`unavailable_backend`, `not_requested`, `not_applicable`,
`abstained_expected_context`, and `no_candidates`. `no_candidates` with positive
truth scores missed events; it is not expected abstention. Unqualified schemas
never become zero-error success. Every applicable mandatory task must be scored
before claiming a completed calibration receipt; optional backends remain named.
Continue nonfailed cases within the same bound, retain partial results and
stop scheduling work when the suite deadline expires.

Proposed v2 process exits: 2 for invalid invocation/configuration/path; 1 for
structural failures or explicitly listed hard safety-regression gates; 0 for
completed synthetic measurements, retaining candidate-quality alerts and named
optional-backend abstentions. The JSON `status`, `task_statuses`,
`hard_failure_count` and `quality_alert_count` remain authoritative; exit0 alone
does not establish that an optional task ran or any real-quality criterion passed.
Preserve existing v1 process semantics for historical reproducibility.

## Proposed extension and bounded evaluation

The released extension adds opt-in `--suite technical-v2` to existing `fixtures`/`run`
commands, keeping the default `technical-v1` behavior. A future repeated
`--case ID` selector may choose only registered cases, never an arbitrary input.
The separate `program/benchmarks-v2.json` preserves the original v1 configuration
bytes and hash. No `--case` selector is implemented. Root assigns typed-hook/skill
changes separately. Actual direct commands:

```text
python3 scripts/benchmark.py fixtures --suite technical-v2 --output NEW_DIRECTORY
python3 scripts/benchmark.py run --suite technical-v2 --output NEW_DIRECTORY \
  --profile conservative3 --phrase-backend stdlib
```

Budget: at most 12 cases, each at most 12 seconds, summed duration at most 120
seconds; 48 kHz mono, four PCM16 references, at most 46.08 MB PCM payload before
WAV headers. Stream/clear cases rather than retaining all float arrays. Preserve
the serial worker model, at most two math/FFmpeg threads, 120 seconds per worker,
600 seconds overall including generation/evaluation, 8 MB stdout/stderr each,
5 MB JSON each and 3 MB decoded float PCM per 12-second mono case. Filesystem
output remains new ignored `artifacts/benchmarks/` children. No downloads,
installation, compiler, daemon or acquired recording. Report observed elapsed
time and storage; these bounds are ceilings, not demonstrated platform capacity.

The pitch evaluator's pilot covers exactly 30 source seconds: missing-fundamental
clean8, ladder clean8, legato mixture6 and sweep mixture8. The clean selections
isolate absent synthesized F0 and ladder condition changes; the mixture selections
exercise noise/click ambiguity. Each job records its actual component input hash,
fixture mixture parent hash, truth hash, excerpt source span and pitch-result hash
in a proposed compact `pitch-index.json`. It uses the existing locked optional environment,
explicit excerpt coverage and native-source lineage; absence of that environment
is `unavailable_backend`. The phrase evaluator consumes the generated bank and
existing worker artifacts read-only, with no score supplied to discovery. Root
assigns executable evaluator files and wall-time budget after publication.

## Independent acceptance scenarios

Use analytic/sample-exact reference facts rather than calling the implementation
to generate its own expected answers. Independent tests must include:

1. A maximum-matching counterexample: references0/0.030, estimates0.020/0.050,
   tolerance0.021. Correct count is2; nearest-pair greedy can incorrectly yield1.
2. Exact positive/negative25/60 ms shifts without automatic latency fitting,
   duplicate candidates, empty truth and intentional absent/extra attacks.
3. A deliberately attenuated32 Hz coefficient despite intact harmonics; uniform
   gain cannot earn noise-removal credit; absent-F0 case has no LF-gain ratio.
4. Known harmonic coefficients proving absent synthesized F0 and retained C1
   periodicity; 1200-cent shifts distinguish octave from chroma-only accuracy.
5. Intentional legato/sweep/tuplets/rests that preserve context and avoid false
   definite-error claims; polyphony yields qualified monophonic abstention.
6. Shifted/warped/omitted recurrence regions, unmatched boundaries, and strict
   evidence that a fitted warp does not erase pre-warp timing differences.
7. Source/score/component hash tampering, schema drift, source-time vs relative
   unit confusion, out-of-span labels and exact declared resource ceilings.

Keep raw and scored artifacts plus algorithm/settings/lock/tool/truth hashes in
fresh runs. A failed metric or worker update requires a new comparison; never
modify truth, tolerance or processing alignment to rescue the original receipt.

## Research-only handoff

At 2026-10-05 22:24 UTC, the live source freeze was still active. This lane read
the published benchmark/worker contracts and primary metric documentation and
coordinated the proposed schema/bank with `guitar_features` (pitch) and
`phrase_dag` (phrase). No fixture was generated, evaluator run, dependency
installed, model/media downloaded, or existing runner/test/configuration changed.

Receipt: `repo_patterns | new BENCHMARK_CALIBRATION_LANE.md only | authorized
research/design during root full-suite source freeze | R-N12/R-N13,
R-HOOK-CONVERGENCE-20261004 | technical-v1 existing3cases, no expanded evaluator |
proposed12cases120s and30s pitch pilot; await explicit root release before code`.

## Implemented bank and freeze checkpoint

The opt-in generator, truth-schema2, source/component/native extent receipts,
unseeded v2 restoration/rhythm/click/phrase measurements and maximum-cardinality
event scorer are implemented. V1 defaults/configuration/waveforms remain intact.
`fixtures.json` and all component paths in truth are relative to the fixture
index's parent, not to individual truth files. New generated-score sections
declare `status: complete_generated_score` and `attack_reference_known: true`.
Legacy cases retain attack-time aliases and explicitly unqualified pitch/score
coverage rather than invented full transcripts.

After PCM16 rendering, the absent-F0 case fits sine/cosine coefficients for
harmonic indices1,2,3,4,5,7 jointly on seconds1–7, using native stride24 (2kHz,
above twice its highest generated harmonic). F0 amplitude must be below5e-5;
each known harmonic amplitude must differ by at most5e-5 (about1.64 PCM16 LSB).
This is a declared generated-coefficient bound, not audible missing-pitch proof.
Configuration and registry objects are parsed and hashed from the same byte
snapshots; the legacy generator's source hash is also retained. A changed input
or generator before completion rejects the bank. Nine ladder condition midpoint
envelope/phase resets are recorded as generator nuisance transitions, distinct
from picked attacks, so their detector responses can be reviewed honestly.

The v2 runner evaluates source immutability/native extent, the32Hz sentinel, and
**exact** pre-normalization denoised bypass sample identity. Its profile still
uses measured presentation gain separately; it makes no normalized-master
bypass identity claim. Unrequested click attenuation has an explicit
`not_evaluated` protected-overlap gate. Hard evaluated failures fail the run;
ordinary detector-quality alerts remain measurements. Pitch and expanded phrase
calibration run through the independently assigned read-only evaluators, not
inside this benchmark runner, and are explicitly `not_requested` here. Runtime
status remains the compatible `completed_synthetic_measurements`/`failed` envelope
with detailed metric/task/gate disposition; planned evaluator status names above
are not a claim that every optional calibration task ran.

Sixteen benchmark tests pass locally, covering the seven existing checks plus
registered bounds, all12 previously published v1 component hashes through both
suites, config snapshot drift, rendered-F0 absence/injected-F0 rejection, exact
tuning/condition spans, independent tempo integration/inversion, injected edits,
tuplets/legato/polyphony/overlap context and the non-greedy matching counterexample.
Command: `python3 -m unittest discover -s tests -p 'test_benchmark*.py' -v`.
The latest measured local run took8.460seconds; this is no capacity percentile.

Generation-only smoke produced
`artifacts/benchmarks/technical-v2-bank-first/fixtures.json`, hash
`0787f66631238c6aff089fe06d3b6fc34856689975826bfa4ba53a766784cf64`.
It contains12cases/120seconds/48component WAVs. Independent reads verified all
108truth/component SHA/native-header facts. Rendered clean F0 coefficient was
2.1125001369e-8; retained harmonic amplitudes were approximately
0.129999967,0.079999796,0.049999947,0.040000064,0.020000052. No processing or
musician-quality pass follows from this generation check. Its legacy-runner hash
predates the final runner-only tightening of the bypass gate to exact zero; it
remains a preserved prior receipt. Root generates a fresh final-source bank for
the actual composite pilot. No newest-directory inference is permitted.

Source freeze hashes: runner`9b8dc2a8aea58fcabf0fe74dfb3cfc967319e0a060a44ba7c40d6e57aa4c1656`,
helper`087a67c009bb48abeac78259fc2719c02886e81b956ef8a9c62a22e6ee3913d5`,
v2config`94fe5085f641c430b579d038736b9036962abfabec8bad86dea0ba163ce245ab`.
Original v1config remains
`c115f37df98ef50a0c8d853928ebdce910a1188abe8291d8cf2bdd51c94fdd52`.
The final two runner gate lines were tightened after the focused test process
loaded its module; root's joint source-checkpoint tests cover the final freeze.
