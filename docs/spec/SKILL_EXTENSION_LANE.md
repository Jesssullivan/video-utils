# Agent skill extension lane

Owner: `/root/tool_skills`. Authority: operator-authorized parallel project work,
repository AGENTS.md and R-HOOK-CONVERGENCE-20261004 (TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`). This lane owns repository skills and their
agent contract; root integrates and publishes. Existing skill/contract files are
frozen until root announces the first push. This new specification records the
next work without changing global skills, agent connections or host configuration.

## Current state and extension order

The initial twelve tools/skills are implemented. Bundled frontmatter checks pass,
and the stdio MCP server lists and retrieves all twelve skill prompts. This does
not establish listening acceptance, native editor import or AU/Logic support.

Create each extension skill only after its worker and typed tool contract exist
and their actual behavior can be inspected. Confirm tool name, skill/prompt name,
input/output schema, supported controls, default settings, interpreter/dependency
requirements, runtime bounds and artifact lineage with the owning lane. Until
then, the rows below are proposed extensions, not callable capabilities.

| Proposed tool / skill | Owning implementation lane | Intended agent outcome |
|---|---|---|
| `clicks` / `guitar-clicks` | Rhythm analysis and tool hooks | Identify observed click candidates and their pulse context, keeping pick-attack ambiguity visible. |
| `phrase_compare` / `guitar-phrase-compare` | Phrase DAG and tool hooks | Compare discovered recurring regions for duration, attack motif and structural differences without requiring a score. |
| `benchmark` / `guitar-benchmark` | Repository patterns, reporting and tool hooks | Compare supported algorithms/settings against annotated examples and synthetic known truth, preserving dataset and detector provenance. |
| review annotations / `guitar-review` | Reporting/review, phrase DAG and tool hooks | Capture human confirmations/corrections as hash-bound annotations, retaining machine proposals and uncertainty. Final tool name follows the implemented registry. |

Use `just tool-info` and `just tool-run` as the shared recipe fallback when a
specialized recipe has not been added. Do not document a direct command, argument
or output as available until it matches the actual worker. MCP prompt names follow
the skill directory; tool names follow the registry. Hook diagnostics remain
advisory under R-N12; a dark client connection has the traceable local recipe
alternative rather than becoming an approval gate.

## Contracts under implementation

The owners have supplied these drafts; implementation/readiness verification is
still required before skill/registry publication:

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
- **Benchmark:** the repository patterns lane is named in the hook specification;
  the exact worker interface and artifact contract remain unknown to this lane. Do not advertise the skill/tool before those
  facts and behavioral checks exist.

The worker specifications [review](REVIEW_LANE.md) and
[phrase comparison](PHRASE_COMPARE_LANE.md) are the current detailed drafts;
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

After root's first-push announcement, align existing pipeline guidance with the
current defaults: reference tolerance is up to 30 ms capped by its match window,
and reference comparison selects one detector stream rather than combining
SuperFlux/spectral-flux/broadband detections. Revalidate affected skills and live
prompt readback after edits; retain previous tested evidence as an earlier state.
