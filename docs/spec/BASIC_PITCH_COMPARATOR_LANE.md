# Optional learned pitch comparator lane

**Plan plus model-byte qualification**, October 5, 2026; owner `/root/tonal_inference`.
Authority: operator's ten-hour parallel goal, ending 06:49:34 UTC October 6,
and R-HOOK-CONVERGENCE-20261004 / R-N13. Current ownership is limited to this
file, [qualification research](../research/BASIC_PITCH_QUALIFICATION.md), a dated
qualified-model receipt and a fresh ignored qualification directory. The root
release acquired the official wheel and verified its extracted ONNX bytes.
No comparator worker, dependencies, model entry, MCP hook, skill or inference
claim is created. Root must release explicit implementation ownership and an
exact artifact/dependency manifest before runtime or adapter work.

## Outcome and architecture

Compare the exact official Spotify Basic Pitch 0.4.0 ONNX model with the
existing bounded dual-resolution pYIN and generated pitch bank. Retain neural
note/onset/contour activations and note-event hypotheses with sparse coverage,
source timestamps and limitations. Automatic discovery needs no expected score;
real-note correctness and performance grading remain unknown without separately
qualified annotations. Do not substitute chroma, open-string tuning or agreement
between two estimators for independent played-note evidence.

Prefer an offline CPU-only adapter in an isolated optional environment. The
official model is 230,444 bytes and a matching ONNX Runtime cp314/arm64 wheel
exists, but ordinary Basic Pitch packaging demands incompatible legacy
TensorFlow on Python>3.11 macOS. Use the selected ONNX file, explicit tensor
names, and reviewed upstream windowing/decoding logic with Apache-2.0/NOTICE
attribution. Label the adapter as the **official model with project decoding**
until upstream parity is actually tested; importing the full upstream package
with unrecorded dependency suppression is not an acceptable compatibility claim.

The fixed model accepts mono 22,050 Hz waveform windows of 43,844 samples,
not the existing MIR chroma features. Output note bins cover MIDI21..108, so
C1 is represented but accuracy is unqualified. Source masters remain at their
native rates/channels; resampling is a separate analysis derivative. No model
inference, resampling, decoder or agent action runs in an AU render callback.

## Qualification and admission sequence

1. Preserve official commit `9991303bba609a3b93089d13ec80d1d495083596`,
   the exact source paths, repository LICENSE/NOTICE, distribution metadata and
   model-term inference from the research receipt. Record any contradictory
   weight terms if subsequent inspection finds them.
2. Root selects an explicitly acquired official artifact/container. Verify the
   published archive SHA256 when using the PyPI wheel; inspect actual archive
   contents and extract only allowlisted non-symlink paths with total-size
   bounds. Verify ONNX size and Git blob ID against the pinned source; compute
   and record its SHA256. Git SHA-1, an archive digest and a model-file SHA256
   are distinct identities. **Completed at the 23:04 UTC byte checkpoint:** ONNX
   SHA256 is `2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec`;
   actual size and pinned Git blob identity match. See the
   [durable manifest](../agent-notes/2026-10-05-basic-pitch-qualified-model.json).
3. Root owns registration of that exact file in the model manifest. Mark model
   terms with their actual evidence scope: repository-wide license plus bundled
   artifact inference, not an independently discovered weight license. Explicit
   model prefetch remains separate from running the comparator; refuse missing,
   unregistered or wrong-hash checkpoints rather than downloading silently.
4. Create an isolated optional environment with a complete wheel-only lock.
   Candidate runtime is ONNX Runtime 1.30.0; its cp314 macOS14 arm64 wheel
   SHA256 is
   `8b6169c16a48429890d2f4a0c774ebf54dfe9066a998514aad0518a16d398547`.
   Lock every selected flatbuffers/NumPy/packaging/protobuf wheel. Reuse current
   NumPy only if exact ABI/import/session smoke passes. Do not upgrade the
   existing analysis environment or download a replacement interpreter.
5. Inspect actual graph tensor names, dtypes, ranks, output dimensions and
   operators using the qualified file. Use explicit `CPUExecutionProvider`,
   sequential execution, at most two intra-op threads and one inter-op thread.
   Record runtime/provider/model identities; a successful import alone does not
   qualify inference or demonstrate expected operator support.

Steps 1–2 have byte/provenance receipts. Model registration, isolated dependency
installation and all graph/inference work remain future steps owned by root.

## Proposed typed controls and bounds

All controls below are proposals; no callable tool currently implements them.

| Proposed control | Type / bounds / default | Purpose |
|---|---|---|
| `run_dir` | Required local path | Hash-bound restored input, source timeline and existing pitch bank/annotations. |
| `model_id` | One registered official ONNX ID | Select an already-qualified local artifact; no arbitrary URL or automatic runtime fallback. |
| `max_analysis_seconds` | Finite number 1..30; default 20 | Sparse distributed coverage, including ending, or explicit bounded excerpt. |
| `start_seconds` | Optional finite audio-relative time inside input | Target a passage; exact span and source-time conversion recorded. |
| `onset_threshold` | Finite 0.05..0.95; default 0.5 | Experimental onset activation threshold, not probability of a correct note. |
| `frame_threshold` | Finite 0.05..0.95; default 0.3 | Experimental sustain activation threshold. |
| `minimum_note_length_ms` | Finite 10..250; default 127.70 | Explicit decoding floor; retained beside raw arrays. |
| `melodia_trick` | Boolean; default true | Upstream-style recovery of remaining activations, with harmonic hallucination caveat. |
| `infer_onsets` | Boolean; default true | Upstream-style inferred changes; record that these are not measured pick attacks. |

Keep frequency bounds fixed to the full trained MIDI range for the first pilot;
do not silently suppress low octaves to match standard guitar. Pitch bend/MIDI
exports are later additions. The 178 BPM declaration never changes note-event
times or imposes a note grid. MIDI tempo metadata is not tempo detection.

Initial resource ceilings: **30 seconds total**, six independently processed
excerpts, **24 model windows**, one worker/session at a time, two numerical
threads, 180-second worker wall deadline, proposed 1 GiB RSS ceiling, 20 MiB
raw array allowance, 5,000 decoded events and 100 MiB result/temporary-audio
allowance. Separately cap new dependency-wheel cache/environment storage at
512 MiB during the feasibility smoke; existing shared caches are not reclaimed.
Budget exceedance yields a partial/failure receipt rather than dropping evidence
silently. These are fail-fast design bounds, not measured performance promises;
RSS monitoring on this host must be tested before claiming enforcement. Preserve
owned-process identity before signalling a timed-out worker under R-N11.

Reuse inference arrays for at most two fixed decoder presets. The upstream
127.70 ms floor may reject sixteenths, thirty-seconds and eighth-note triplets
at 178 BPM. The first technical comparison proposes **25 ms**, not acceptance
of shorter outputs: rounding and the decoder's strict duration inequality can
make the effective minimum longer than the requested value. Verify this with
boundary tests. Lowering the floor can add noise or distortion partials.

## Timeline, provenance and output

Use the verified `denoised.wav` derivative by default. Validate its manifest hash,
sample extent and source lineage, plus current tuning/model/dependency identities.
Process excerpts separately; never concatenate gaps into apparently continuous
notes. Retain actual coverage and uncovered intervals. Match the four existing
pYIN five-second spans for the first actual comparison when their upstream
hashes remain current; add no more than ten seconds only for a declared case.

Record resampled count, leading/trailing padding, overlap removal and the exact
upstream decoder clock adjustment. Test events at the start, end and every
window seam; its empirical window-index correction is not capture-latency
calibration. Convert excerpt-relative times through decoded audio origin to
original source time without time stretching. Boundary-straddling notes carry
truncated-context uncertainty instead of invented full extents.

Save independent immutable `learned-pitch/<run-id>/` artifacts: finite named
numeric NPZ arrays (never object/pickle arrays), JSON note hypotheses, settings,
coverage, model/runtime/tuning/source hashes and a comparison receipt. The main
`pitch.json`, media master, source and current DAG stay intact. Every activation
has `confidence_kind: uncalibrated_model_activation`; notes retain octave,
chord/partial and articulation ambiguity. No identified string, stem, intended
note, tonic/mode or performance-issue verdict follows from this operation.

## Meaningful evaluation and work allocation

Use the same generated label timelines as the current bank when compatible;
new fixtures must describe generated events independently of detector outputs.
Report event precision/recall, octave-error counts, voiced/unknown coverage,
pitch-active frame overlap, start/end residual distributions, runtime/peak RSS
and default-versus-short-floor differences. Match overlapping pitches without
forcing one note per frame; report ambiguous labels and excluded spans. Synthetic
agreement never establishes the actual recording's note correctness.

- **C1 and missing fundamental:** clean 32.703 Hz, harmonics-only 2/3/5, weak
  fundamental plus dominant octave, and tuning detuning/bend controls. Preserve
  low-octave alternatives; report hallucinated independent harmonic notes.
- **Distorted ladder and power chords:** fixed amplitude-normalized harmonic
  ladders, clipping levels, C1/G1 or custom-tuning chord stacks, pedal-tone
  repetitions and silence/noise/click overlap. Measure false polyphony separately
  from correct overlapping-note detection.
- **Legato and sweep:** continuous pitch slides, attack-softened hammer/pull
  envelopes and labeled 40–170 ms sequences across low/high register, including
  window seams. Report merged/split hypotheses and frame/onset uncertainty;
  absence of a model event is not a missed musical note.
- **Actual take:** the matched sparse pYIN excerpts and ending. Compare two
  estimators and expose disagreeing spans for listening. Ground-truth metrics
  are unavailable unless separately supplied source-bound annotations qualify.

Proposed **4–6 development hours** after root admission: 1 hour for acquisition,
manifest/lock and bounded session smoke; 1.5–2 hours for audited adapter and
provenance/timing; 1–1.5 hours for bank/event metrics; 0.5–1 hour for actual
comparison, hook/skill contracts and handoff. If wheel/ABI/model qualification
fails, retain the successful classical pitch tooling and record the exact gap.
There is no implicit TensorFlow build, GPU migration, replacement model or host
repair fallback. This estimate fits within the current horizon only if root
prioritizes and releases the lane; it is not a completed-work claim.

Done for this research lane: pinned source and artifact inventory, explicit
weight-term evidence scope, wheel compatibility analysis, practical bounded
interface and a testable plan. Future runtime acceptance additionally requires
qualified bytes, installed locked wheels, measured bounded inference, synthetic
metrics and actual-take comparison before any MCP/skill is advertised as ready.
