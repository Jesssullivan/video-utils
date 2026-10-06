# Basic Pitch comparator skill design

Owner: `/root/tool_skills`. Authority: operator-authorized continued parallel
project work; repository AGENTS.md; R-HOOK-CONVERGENCE-20261004 / R-N12 / R-N13.
This assignment owns this new design document only. Existing twenty-three
SKILL.md files remain frozen. Worker admission, recipes, registry activation,
counts, tracker evidence and publication belong to root and their named owners.

## Definition of done before design implementation

- Read qualified runtime/model receipts and the adapter/hook contracts. Preserve
  CPU runtime qualification versus actual adapter execution and musical accuracy.
- Coordinate exact fixed inputs, windows, raw outputs, clocks, model/environment
  hashes, closed controls and resource ceilings with worker and hook owners.
- Explain 172-by-88 model outputs, note/event ambiguity, low C1 representability
  versus accuracy, octave/polyphony/window limitations and unknown correctness.
- Make identify/research/iterate/acceptance instructions useful without implicit
  weights, packages, downloads, score leakage or a musician-correctness verdict.
- Obtain independent adversarial read-only review of the design, record concrete
  gaps and named implementation/admission tasks. Create no new skill or prompt
  until root assigns it after worker readiness.

## Coordination checkpoint

Worker owner: `/root/tonal_inference`; hook owner: `/root/tool_hooks`.
Initial sources: BASIC_PITCH_COMPARATOR_LANE.md, BASIC_PITCH_TOOL_CONTRACT.md,
research/BASIC_PITCH_QUALIFICATION.md and the dated qualified-model receipt.
Parent reports qualified CPU runtime passing; adapter implementation/readiness
is separate and still requires its actual worker receipts. No twenty-fourth
catalog entry or skill availability is claimed by this design.

## Intended future skill behavior

The eventual skill should lead with a bounded learned comparator, not a
musician-correctness classifier. Inspect the registered model/runtime receipt,
input derivative and original lineage, native sample extent/origin and requested
coverage before inference. Refuse missing, unregistered or changed model bytes
and environment identities; there is no implicit download, package repair,
TensorFlow fallback, alternate checkpoint or GPU migration. Qualified CPU
session execution alone does not establish adapter parity or guitar accuracy.

The selected official ONNX model has SHA256
`2c3c1d144bfa61ad236e92e169c13535c880469a12a047d4e73451f2c059a0ec`.
Its mono 22,050 Hz input window contains 43,844 samples. The intended verified
head representation is note/onset `[1,172,88]` and contour `[1,172,264]`, with
note bins MIDI 21–108. A 172-by-88 matrix is neither 172 detected notes nor 88
identified guitar strings. Raw note/onset/contour activations remain finite
numeric evidence with uncalibrated meaning; a null or weak event decision is
not a missed musical note. C1/MIDI 24 is representable, but distortion, absent
fundamentals, octave partials and polyphony require actual qualification.

Preserve theoretical custom tuning, including Eb2→Bb2, without using it as a
forced pitch decoder or tonic prior. Retain event/octave/chord/partial ambiguity,
unknown voicing/correctness, articulation and truncated-context limitations.
Polyphonic hypotheses do not identify strings, frets, fingering, stems or
intended notes. Agreement with pYIN remains estimator agreement, not independent
musician truth; generated comparisons retain generator-only scope.

Excerpts are independently processed and remain sparse: do not concatenate gaps
or imply that unanalysed portions were transcribed. Record each window, resample
count, leading/trailing padding, seam/overlap handling, decoder clock adjustment
and original source-time translation. Model frame spacing is not onset accuracy
or physical capture-latency calibration. The declared 178 BPM is context only;
neither note times nor MIDI tempo metadata can become detected rhythm or a
correctness grid. Retain raw arrays alongside decoder settings and hypotheses.

## Closed controls and iteration design

The current concrete proposal is `basic_pitch_compare` via
`scripts/basic_pitch_compare.py RUN_DIR --max-analysis-seconds SECONDS
[--start-seconds SECONDS] --runtime-python PATH` plus fixed onset/frame threshold
flags. The runtime interpreter is qualified operator configuration, not a
caller-controlled MCP executable argument. Model selection is the single
registered `spotify-basic-pitch-0.4.0-onnx`, not an exposed arbitrary model ID.
Proposed typed fields are required `run_dir`; budget 1–30 seconds/default 20;
optional start >=0 inside extent; onset/frame thresholds 0.05–0.95/defaults
0.5/0.3; and shared timeout integer 1–900/default 600. Final worker qualification,
compact keys and path boundaries remain admission tasks; no new field is callable
through the existing catalog yet. Do not expose model/executable/argv/URL,
decoder objects, grid substitution, score, tuning correction or resampling knobs.

The two fixed decoder contrasts reuse inference arrays and keep model/windows
unchanged. They are project threshold-run/onset-split decoding with minimums
127.7/25 ms, not upstream Melodia parity or caller-selectable duration flags.
Record default versus short-duration differences:
127.70 ms upstream minimum can suppress intentional fast events, while shorter
floors can add harmonic/noise hypotheses. Exact effective sample/frame duration
and strict comparison boundaries need tests before interpretation. Select no
branch, octave or clock offset by generated truth to inflate a score.

Current proposed bounds are thirty analyzed seconds, twenty-four windows, one
CPU session, two numerical threads, 600-second overall deadline and 1 GiB RSS.
The newer 600-second proposal supersedes the earlier 180-second feasibility
ceiling. Excerpt, RSS, disk, event and array caps require actual enforcement
evidence; a proposal must not become a measured or enforced guarantee. Compact
stdout should point to full immutable local array/settings/event receipts rather
than print arrays.

Research pinned official inference/constants/decoder and the model paper through
[qualification research](../research/BASIC_PITCH_QUALIFICATION.md). Change one
supported knob, reuse frozen inference where allowed, compare fresh receipts and
report coverage, disagreements, exclusions and unknowns. No best decoder,
real-note accuracy, timing-performance grade or AU/Logic acceptance is inferred.

## Named admission tasks and adversarial review

1. `basic-pitch-worker-contract` — tonal owner supplies implemented CLI/schema,
   output heads/clocks, runtime/model bindings and enforced resource receipts.
2. `basic-pitch-hook-contract` — hook owner locks only supported typed controls,
   fixed dispatch, explicit isolated interpreter and bounded failure semantics.
3. `basic-pitch-skill-admission` — root assigns a new skill only after meaningful
   generated C1/polyphony/short-sweep/seam tests and actual sparse-take evidence.
4. `basic-pitch-skill-forward-review` — independent read-only review challenges
   low-C1 confidence, raw matrix counts, short polyphonic sweeps, unknown voicing,
   model/environment mismatch, score leakage and tempo/timing claims.
5. `basic-pitch-catalog-proof` — after explicit root activation, validate the new
   bundle and exact local prompt/schema readback; publication remains separate.

Design questions awaiting owners: final skill name; admitted path/control bounds;
raw-window versus stitched-array clocks; model/environment receipt paths;
enforcement/peak RSS; compact output/error keys. Project decoding has no upstream
parity claim. The design does not block existing twenty-three tools or marked MVP.

## Design review checkpoint

Independent eight-case read-only adversarial review found no concrete instruction
gap. It preserved C1 representability limits, raw head/count ambiguity, short
polyphonic/window uncertainty, explicit model/runtime identities and unknown
tempo/timing/correctness. This review qualifies the design only, not adapter or
runtime admission. See [the reviewer-owned dated receipt](../agent-notes/2026-10-05-agent-iteration-skill-review.md).
Final typed proposals were subsequently aligned with the hook owner's draft;
existing skills and catalog were not changed.

## Root admission and skill implementation DoD

Root now admits `basic_pitch_compare` as the twenty-fourth primitive after frozen
worker `8bc17166c48ff6dccf33fd0eb17d3257535d6d91c83df0afed51b9c59dc75ee1`,
seventeen passing tests, qualified CPU runtime and independent audit readback.
This supersedes the earlier docs-only admission hold for Basic Pitch only.
Ownership now also includes new `.agents/skills/guitar-basic-pitch/SKILL.md`;
the original twenty-three skills remain unchanged. Capture-profile remains design
only and creates no twenty-fifth tool.

Before skill creation: inspect the complete fixed adapter and final hook fields;
record exact model/environment/source identities, sparse span/window contexts,
three clocks, fixed project decoding and observed missing-F0 failure. Verify
bundled structure and independent adversarial behavior, then all twenty-four
exact initialized MCP prompts/schema once the hook owner activates it. Keep
source checks, adapter CPU proof, generated metrics, real-note truth, listening
and signed publication separate.

## Implemented skill and local proof

The new skill matches the admitted fixed fields: required run path under
`artifacts/runs`, finite budget 1–30/default 20, optional nonnegative start,
activation thresholds 0.05–0.95/defaults 0.5/0.3 and timeout 1–900/default 600.
No MCP model/interpreter argument is exposed. It preserves manifest original
lineage versus verified derivative identity, native extent, approximately
1.988-second window context, three raw clocks and fixed project duration presets.
The observed zero-of-258 missing-F0 C1 top-one result and actual twenty-second
17/65 event hypotheses remain visible without tuning-based rescue or grading.

All twenty-four bundles pass the existing validator with cached PyYAML, and an
actual initialized MCP stdio session returns twenty-four tools/prompts with exact
content for every registered SKILL.md and empty stderr. The live Basic Pitch
schema bounds/defaults and absence of arbitrary model/interpreter fields were
checked directly. Existing twenty-three skills were not edited by this lane.

The hook owner reports five focused tests passing, including real two-second
qualified CPU inference via MCP, immutable source/context/hash/array receipts,
and missing/changed model/runtime refusal before decode. Worker-owner seventeen
tests and actual sparse pilot are separate recorded evidence in
[the runtime receipt](../agent-notes/2026-10-05-basic-pitch-runtime.json).

Independent read-only actual-skill review found no behavioral gap for raw head
counts, short polyphony, C1/missing-F0 rescue, event-count truth, whole-take grades
or automatic runtime/model fallback. It identified stale planning status in the
linked hook contract; the hook owner has been asked to reconcile current local
admission versus publication before release. These checks do not establish
real-note truth, listening acceptance, upstream full-decoder parity or Logic.

The hook owner reconciled that contract to admitted/current implementation.
Independent final readback confirms the publication-coherence finding is closed.
Its combined sixty-five targeted checks passed without skips, owner-reported.
The Basic Pitch skill and local twenty-four-tool proof are complete and frozen
for root publication; capture-profile design remains unadmitted. Capture design
readback also preserves the distinction between authoring-only nonrunnable output
and already-existing render authority without recurring confirmation.
