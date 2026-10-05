# Agent skill extension lane

Owner: `/root/tool_skills`. Authority: operator-authorized parallel project work,
repository AGENTS.md and R-HOOK-CONVERGENCE-20261004 (TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`). This lane owns repository skills and their
agent contract; root integrates and publishes. The initial freeze ended after signed private publication `be085b4`; initial
source checks and publication are separate from extension readiness. This
specification records the next work without changing global skills, agent
connections or host configuration.

## Current state and extension order

The initial twelve tools/skills are implemented. Bundled frontmatter checks pass,
and the stdio MCP server lists and retrieves all twelve skill prompts. This does
not establish listening acceptance, native editor import or AU/Logic support.

Create each extension skill only after its worker and typed tool contract exist
and their actual behavior can be inspected. Confirm tool name, skill/prompt name,
input/output schema, supported controls, default settings, interpreter/dependency
requirements, runtime bounds and artifact lineage with the owning lane. Worker and skill readiness do not establish MCP publication; the status below
separates those stages. After root’s standalone hosted-CI parser-depth fix, the local MCP catalog
contains nineteen tools with matching live skill prompts. Root’s signed remote
extension publication remains a separate checkpoint; all nineteen local
tools/prompts passed exact skill readback and bundled validation.

| Tool / skill | Owning implementation lane | Intended agent outcome | Current stage |
|---|---|---|---|
| `clicks` / `guitar-clicks` | Rhythm analysis and tool hooks | Identify observed click candidates and their pulse context, keeping pick-attack ambiguity visible. | Worker verified by owner; skill validated; Local MCP readback passed; remote publication pending. |
| `phrase_compare` / `guitar-phrase-compare` | Phrase DAG and tool hooks | Compare discovered recurring regions for duration, attack motif and structural differences without requiring a score. | Worker verified by owner; skill validated; Local MCP readback passed; remote publication pending. |
| `benchmark` / `guitar-benchmark` | Repository patterns, reporting and tool hooks | Compare supported algorithms/settings against annotated examples and synthetic known truth, preserving dataset and detector provenance. | Three-case suite verified by owner; skill validated; Local MCP readback passed; remote publication pending. |
| `review` / `guitar-review` | Reporting/review, phrase DAG and tool hooks | Capture human observations/corrections as hash-bound annotations, retaining machine proposals and uncertainty. | Worker verified; actual demo readback passed; skill validated; Local MCP readback passed; remote publication pending. |
| `pitch` / `guitar-pitch` | Guitar features and tool hooks | Produce bounded dual-resolution pitch candidates using the operator tuning, preserving octave/string ambiguity. | Worker/actual bounded pilot verified; skill validated; local MCP readback passed; remote publication pending. |
| `meter` / `guitar-meter` | Meter inference and tool hooks | Rank pulse-accent cycles and aliases while preserving unknown notation/downbeats. | Worker/actual abstention verified; skill validated; local MCP readback passed; remote publication pending. |
| `tonal` / `guitar-tonal` | Tonal inference and tool hooks | Compare profile/collection hypotheses with null tonic/mode and separate sparse pitch coverage. | All 21 locked tests independently passed; actual receipt verified by owner; skill validated; local MCP readback passed; remote publication pending. |

Use `just tool-info` and `just tool-run` as the shared recipe fallback when a
specialized recipe has not been added. Do not document a direct command, argument
or output as available until it matches the actual worker. MCP prompt names follow
the skill directory; tool names follow the registry. Hook diagnostics remain
advisory under R-N12; a dark client connection has the traceable local recipe
alternative rather than becoming an approval gate.

## Contracts under implementation

The owners supplied the following contracts. All seven extension workers now have verified contracts and matching skills.
All seven have local MCP readback. All nineteen repository skills validate;
remote publication and musical/host acceptance remain separate checkpoints. Registry publication and actual MCP readback are separate checks:

- **Clicks:** `scripts/clicks.py INPUT --run-dir DIR`, optional BPM 20–400,
  paired template start/end, optional attenuation plus an operator click-only
  declaration, and strength 0–0.5. Detection is the default; outputs live in an
  immutable unique child run. A declaration is metadata, not a classifier.
  Optional subtraction protects frequencies below 1200 Hz and requires overlap/
  residue review. NumPy/SciPy use the explicit locked analysis interpreter.
- **Phrase comparison:** `scripts/phrase_compare.py RUN_DIR`, max pairs 1–60
  (default 30), band fraction 0.20, rate bounds 0.5–2.0. Consume hash-consistent
  manifest, `analysis.librosa.features` and discovered recurrence candidates;
  bound windows to 384 frames, pair cells to 100,000 and run cells to 2,000,000.
  Output `phrase-comparisons.json`; no score requirement or onset-stream blending.
- **Review annotations:** `scripts/review_server.py annotations RUN_DIR` reads;
  `annotate RUN_DIR --input JSON_FILE` writes without a server. Draft tool
  operations are read/write (read default); a write requires an input file.
  Expected revision prevents silent lost updates. Finite ordered source spans,
  bounded notes, category/status enums and source/candidate receipts are validated
  by the worker. HTTP serving is a separate local interface, not an MCP tool.
- **Benchmark:** `scripts/benchmark.py fixtures|run --output NEW_DIRECTORY`;
  run exposes profile `bypass|conservative3|mild6` and phrase backend
  `stdlib|librosa`. The first suite is deterministic `technical-v1`; output must
  be new and under `artifacts/benchmarks/`. The owner has verified the actual three-case suite and its six tests.
  Synthetic measurements do not establish actual-take quality.
- **Pitch:** `scripts/pitch.py INPUT --run-dir DIR --max-analysis-seconds N`
  accepts a 1–30 second budget (default 20), optionally `--start-seconds N`.
  Default distributed excerpts include the ending; explicit start is contiguous.
  Fixed dual pYIN branches report coverage, octave alternatives and source/tuning
  lineage. Full frame arrays stay in `pitch.json`; MCP uses a bounded summary.
  No trained model download, full-transcription or intended-note claim.

The worker specifications [review](REVIEW_LANE.md) and
[phrase comparison](PHRASE_COMPARE_LANE.md), [benchmark](BENCHMARK_LANE.md) and
[pitch](PITCH_LANE.md) are the current detailed drafts;
read their latest state when implementation is ready.

## Per-tool purpose, controls and iteration

**Click identification.** Discover click-shaped events, their observed timestamps,
pulse fit, coverage and identity uncertainty. Research spectral template matching,
onset detectors and instrument/transient discrimination in upstream documentation
and primary papers before selecting controls. Inspect actual exposed threshold,
minimum gap, BPM seed, template or detector choices; do not promise a knob absent
from the schema. Compare a bounded few candidates against original playback and
annotated clicks, including overlapping pick attacks. A stable tempo family is
not proof that its events are metronome clicks. Any attenuation is a separate
explicitly implemented operation requiring matched-level and residue review.

**Phrase comparison.** Consume discovered regions, tempo evidence, selected detector
identity and nullable tonal context. Discover phrases, bar proxies and breakdown
hypotheses without predefined intended phrases. Research beat-synchronous MFCC/
chroma/texture representations, novelty and recurrence with their limitations on
distortion. Compare duration, monotonic attack motifs and attack-density evidence;
unknown capture latency does not prevent relative comparisons because a constant
offset cancels. Detector and boundary bias still remain. Exposed similarity,
window or duration controls must match the actual contract. Present changed motifs,
shorter loops, possible skips/rushes and unclear spans as hypotheses with source
timestamps. Approved intended rhythm supports stricter comparisons but never gates
automatic discovery.

**Benchmark.** Define the requested task, example set and known/annotated truth
before comparing settings. Use detector timing error and tolerance, pulse
ambiguity, annotation disagreement, source-time correctness and low-frequency/
transient damage as applicable. Keep synthetic known truth separate from actual
recording annotations and operator listening. Research metrics from primary
sources; persist versions, settings, source/artifact hashes and exclusions. A
single aggregate score must not hide 32 Hz attenuation, tuplets/sweeps failures or
half/double-BPM mistakes. Model/algorithm adoption remains tied to the task's
measured outcomes rather than popularity or a benchmark rank.

**Review annotations.** Record the original source identity, event/span, annotation
kind, evidence and declared review state using the implemented schema. The draft
worker states are `needs_review`, `accepted_observation` and `dismissed_candidate`;
an accepted observation is not a confirmed musical mistake. Capture declared tempo, tuning and expected note/rhythm context
separately from detected evidence. Never auto-approve an intended reference or
change a machine candidate into a confirmed musical mistake because a report was
opened. Preserve prior annotations/lineage on revision and make conflicts visible.
Use source/sample time for reproducibility; editor frame/timecode interpretation
still needs an actual adapter and host proof. Annotation writes stay local and
never imply permission to publish media or change plugins.

**Pitch candidates.** Read the constant tuning registry without changing its
unusual intervals. Research pYIN/YIN windowing, voicing and frequency limits in
upstream documentation; low-register windows need multiple near-32 Hz cycles,
while rapid sweeps/legato need separate temporal-resolution evidence. Preserve
unknown frames, cents, octave/harmonic alternatives and nonexclusive theoretical
string mappings. pYIN voicing probability is not calibrated note correctness.
Polyphony and missing fundamentals require explicit ambiguity. Actual controls,
coverage bounds, interpreter and runtime must come from the implemented worker;
no intended-note, tonic/mode or recovered-fundamental claim follows from tuning.

## Domain and claim boundaries

The instrument is a down-tuned nine-string guitar. Preserve intentional near-32 Hz
fundamentals; `program/instrument.json` carries the operator's custom tuning and
the distinction between stated pitch classes, inferred octaves and theoretical
frequencies. Do not substitute standard/all-fourths tuning. The operator-confirmed
tempo of this take is run context, not a global default for later recordings.

No speech-denoiser default, blanket high-pass or mains-hum notch. Distorted
harmonics, missing fundamentals, polyphony, bends, palm mutes, tapping, legato,
rests, tuplets and sweeps must shape tool use. Detected pulse, four-pulse bar proxy,
recurrence and dominant pitch do not establish meter, intended notes or correctness.
Unknown tonic/mode and absent expected intent do not block structural discovery.
Definite wrong/missed/extra notes or musical mistakes need intended evidence,
calibration where relevant, listening and human judgment.

The existing pipeline evaluates artifact ancestry and comparisons; it does not
autonomously schedule rerenders or optimize knobs. New skills must make that
boundary visible until an actual executor is implemented. Generic JSON/CSV
markers remain review interchange; native Final Cut/Resolve import and AU/Logic
runtime acceptance remain separate milestones.

## Observable acceptance and receipts

- Validate each new skill with bundled `quick_validate.py`. The existing cached
  PyYAML interpreter path is a recorded validation alternative, not a project
  runtime dependency or global installation requirement.
- Exercise real MCP initialization, `tools/list`, `prompts/list`, `prompts/get`
  and a bounded valid call; verify live skill contents, schemas, worker output,
  private artifact handling and errors. Verify recipe fallback behavior too.
- Forward-review realistic cases independently: clicks overlapping palm mutes;
  deliberate triplets/legato; repeated phrases with intentional variation;
  unknown absolute latency; 32 Hz sustain mistaken for noise; missing tonal
  context; annotation conflicts; nonzero/negative source starts; and unsupported
  native editor import. Evaluate resulting actions and claims, not wording alone.
- Preserve source measurements, candidate inference, synthetic checks, actual-take
  review, listening acceptance and application proof as distinct evidence states.
- Record implementation/review receipts in `docs/agent-notes/`, research in
  `docs/research/`, specifications here and factual issue evidence in Linear.
  Root owns publication and synchronization of `program/linear.json`.

After publication release, existing pipeline guidance was aligned with current
defaults: reference tolerance is up to 30 ms capped by its match window, and
reference comparison selects one detector stream rather than combining
SuperFlux/spectral-flux/broadband detections. Revalidate affected skills and live
prompt readback after edits; retain previous tested evidence as an earlier state.

## Forward-review checkpoint

An independent read-only reviewer applied the review, phrase-compare and benchmark
skills to stale concurrent notes, score-free triplet/legato recurrence comparison
with unknown latency, and a request to select a phone-take profile from synthetic
rankings. It found no concrete correction warranted: observations preserve
uncertainty and revisions, relative diagnostics do not become attack-error grades,
and synthetic scores cannot establish real-take sound acceptance. No files were
changed or operator media used. A separate click forward review covered a 178 BPM palm-muted take, ambiguous
20 ms template request and a requested guitar stem. It found no concrete gap:
resolve audio-relative coordinates, detect before any declared click-only
attenuation, preserve overlap abstention, and describe partial processed-mixture
results rather than recovered stems. No execution or media use occurred.
Source validation is not listening evidence.

The pitch skill also received independent read-only forward review using a
request to count every note/string/wrong note across a 150-second take and its
legato ending. No concrete correction was warranted: default 20-second coverage
is explicit, branch voiced frames are not note counts, short/long window bias and
nonunique strings are retained, and unsupported full transcription/grading is
not claimed. No execution or operator media access occurred.

Meter skill forward review independently covered a request to turn a seven-note
chug at a declared 178 BPM into confirmed 7/8 bars and missed-beat flags. No
concrete correction was warranted: investigate accent cycles without inferred
pulse units/downbeats/additive partition, preserve unknown notation and avoid
error grades. Static review used no media or execution. Its local MCP prompt
subsequently passed exact-content readback.

Tonal skill forward review independently covered an open-C/C-major-harmonics
request to select key/mode and flag out-of-scale notes from sparse pitch. No
concrete correction was warranted: no tuning prior, harmonic/relative-mode
ambiguity preserved, null tonic/mode and sparse coverage separate, and no
out-of-scale correctness grades. The review used no execution or media.
Independent locked tonal verification passed all 21 tests in 24.4 seconds,
including missing-fundamental and registry read/hash-race cases.
