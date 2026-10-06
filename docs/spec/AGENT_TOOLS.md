# Agent tools and guitar workflows

The operator interface is `just`; agents can reach the same bounded workers
through a repository-owned MCP stdio server. Each tool has one focused skill in
`.agents/skills/`. These skills describe purpose, controls, interpretation,
research and comparison, rather than treating successful execution as musical
acceptance. No global skill installation or agent configuration change is made
by this repository.

## Discovery and invocation

Launch from the repository root with `just mcp`. The server uses newline-delimited
JSON-RPC on stdin/stdout; diagnostics go to stderr. Use MCP initialization and
`notifications/initialized`, then `tools/list` to inspect the current input
schemas. Use `tools/call` to invoke a registered tool. There is no arbitrary shell
or arbitrary worker route.

`prompts/list` exposes a prompt for each skill directory name. `prompts/get` loads
the corresponding `SKILL.md`, with optional input, run directory and intended-goal
context. A skill being committed does not mean a particular agent client has
connected to this server. Use the recipes or the local tool API when no connection
is available:

```bash
python3 scripts/tool_api.py list
python3 scripts/tool_api.py describe denoise
just tool-run denoise '{"input":"/path/take.mov","profile":"conservative3"}'
just clean "/path/take.mov" conservative3
just analyze "/path/take.mov" "/path/run"
just dag "/path/run" "/path/approved-rhythm.json"
just markers "/path/run"
```

Tool results distinguish `tool`, `status`, `evidence_kind`,
`implementation_status`, `instrument_context`, `result`, `limitations` and
`skill`. Inspect errors and worker output; a returned manifest
is processing evidence, not a quality endorsement. Shared timeout settings are
bounded; consult the actual schema rather than assuming unlimited recordings or
exposed controls. Media/model downloads and uploads are never implicit.

## Tool map and capability boundaries

The twenty-seven entries below are present in the current local registry.
The dated reconciliation checkpoint at October 5, 2026, 23:25 UTC found twenty
tools in committed `HEAD` and `origin/main` (`04f64844c2c15d69adda2fc0b1e89a4e2702b82f`),
and twenty-three in the working tree. `pitch_evaluate`, `phrase_evaluate` and
`marked_video` have local worker/typed-hook/skill checks but were unpublished at
that checkpoint. The two evaluator smoke runs use generated fixtures; the
marked-video smoke uses generated VFR media. They do not establish actual-take
accuracy or listening acceptance. Root's later publication and real-run receipts
supersede this checkpoint; `tools/list` describes the checkout a client actually
launches.

| MCP tool | MCP prompt / repository skill | State and intended output |
|---|---|---|
| `probe` | `video-probe` | Stream, source-hash and timeline inspection; not a complete restoration/measurement run. |
| `denoise` | `guitar-denoise` | Current conservative FFmpeg profiles with matched baseline/residue; listening pending until reviewed. |
| `bpm` | `guitar-bpm` | Current periodicity candidates and fitted transient grid; not confirmed metronome identity, tempo or meter. |
| `noise` | `guitar-noise` | Experimental quiet-interval measurements; a quiet candidate is not a noise-only capture. |
| `tone` | `guitar-tone` | Experimental spectral bands; not amplifier reconstruction or intended-tone classification. |
| `notes` | `guitar-notes` | Experimental sparse periodic pitch candidates; not polyphonic transcription or wrong-note grading. |
| `rhythm` | `guitar-rhythm` | Experimental recorded-transient offsets; intended rhythm and calibration are needed for error grading. |
| `phrases` | `guitar-phrases` | Automatic experimental phrase/bar/breakdown and recurrence candidates; intended phrases are not a prerequisite. |
| `export` | `media-export` | Current local WAV/video delivery with timeline/hash checks; codec and listening acceptance remain distinct. |
| `report` | `guitar-report` | Current local evidence HTML; missing analysis and acceptance remain explicit. |
| `pipeline` | `guitar-pipeline` | Existing-run provenance DAG, automatic candidate/self-consistency review and optional approved-reference comparisons; no automatic analysis scheduling. |
| `markers` | `phrase-markers` | Current generic source-time JSON/CSV review exchange; native editor import remains unverified. |
| `clicks` | `guitar-clicks` | Detection-first click-shaped candidates; optional bounded template attenuation variant, no recovered-stem claim. |
| `phrase_compare` | `guitar-phrase-compare` | Bounded within-take feature alignment and relative review hypotheses, no intended-score prerequisite. |
| `benchmark` | `guitar-benchmark` | Deterministic synthetic fixture generation/evaluation, no actual-take listening acceptance. |
| `review` | `guitar-review` | Source-bound annotation read/write with revision checks; no implicit HTTP server or master acceptance. |
| `pitch` | `guitar-pitch` | Bounded dual-resolution pYIN candidates with explicit coverage and octave/string ambiguity; no full transcription or intended-note grades. |
| `meter` | `guitar-meter` | Pulse-accent cycle/alias hypotheses with explicit unknowns; no confirmed time signature, downbeat or missed-beat grade. |
| `corpus` | `guitar-corpus` | Read-only sparse annotation metadata validation with compact summary; supplied labels/reviewer identities are not authenticated ground truth. |
| `tonal` | `guitar-tonal` | Automatic chroma/profile/collection hypotheses with null tonic/mode, no tuning prior or intended-note grades. |
| `pitch_evaluate` | `guitar-pitch-evaluate` | Source-verified local generated-reference evaluator; validates an existing four-job/30-second pitch pilot without decoding or inference; real-note accuracy unestablished. |
| `phrase_evaluate` | `guitar-phrase-evaluate` | Source-verified local generated-reference boundary/recurrence/alignment evaluator; keeps abstentions, sparse coverage and pre-warp differences; real phrase correctness unestablished. |
| `marked_video` | `guitar-marked-video` | Source-verified local separate burned review preview with generated VFR preservation checks; uncertain callouts, no master overwrite or real-take listening claim. |
| `basic_pitch_compare` | `guitar-basic-pitch` | Optional hash-qualified CPU comparison with retained raw heads, sparse coverage, three clocks and experimental event hypotheses; no intended-note grading. |
| `capture_profile` | `guitar-capture-profile` | Fresh source-bound settings and review receipts; distinguishes authoring-only proposals, authorized unrendered profiles and rejected captures; no DSP or listening acceptance. |
| `editor_marker_plan` | `editor-marker-plan` | Bounded source-time metadata planning with closed calibration profiles and compact summaries; unknown VFR/host mapping abstains, with no native import or executable editor actions. |
| `learned_pitch_evaluate` | `guitar-learned-pitch-evaluate` | Pure evaluation of an existing generated bank, pYIN pilot and learned activations; preserves window exclusions, octave errors, decoder tradeoffs and null unsupported scores without inference or real-note grading. |

Each skill's worker fallback is documented in its `SKILL.md`. Experimental
feature tools use `scripts/guitar_features.py TOOL INPUT --run-dir DIR`; discover
the current schemas from `tools/list`. `phrases` exposes `backend` (`stdlib` or
optional `librosa`) and `bpm` (20–400); `noise`, `tone` and `notes` do not expose
these controls. The librosa backend needs the locked analysis interpreter and an
explicit BPM seed or same-source tempo artifact. Use the environment interpreter
for the MCP server or `VIDEO_UTILS_ANALYSIS_PYTHON` when configured; dependency
installation is never implicit. Proposed controls
must be implemented and validated before an agent promises their effect. The BPM/rhythm
worker supports backend selection and a manual BPM seed. Denoise accepts registered
profiles through MCP. Capture authoring records the existing scoped interval
review and authorization; direct custom-profile application still requires
source/profile validation, while its typed application route remains separate.

Additional extension contracts and worker/registry readiness are tracked in
[the skill extension lane](SKILL_EXTENSION_LANE.md),
[calibration hooks](CALIBRATION_TOOL_CONTRACT.md) and
[marked-video hook](MARKED_VIDEO_TOOL_CONTRACT.md). The latter records 58 targeted
local tests and exact-content readback/bundle validation of all twenty-three
skills/prompts. These are recorded source checks, not a twenty-three-tool remote
publication or actual-take quality receipt. Worker checks, local catalog evidence,
signed remote publication and musical acceptance remain separate states.

The new evaluator hooks require existing `fixture_index`, `pilot_index` and a
fresh `output` directory beneath repository `artifacts/benchmarks`. They accept
only optional integer `timeout_seconds` (1–900, default 120); they do not run
pitch/phrase discovery, regenerate fixtures or acquire private audio. Bounded
source WAV bytes are read for hash/header checks, while `source_audio_decoded`
and `inference_invoked` remain false. Full results stay in local receipts;
synthetic low accuracy and abstention remain visible rather than becoming a
real-performance verdict.

`marked_video` requires existing `run_dir` and fresh `output` beneath repository
`artifacts/runs`; optional `selection` is `phrase-review` (default), `recurrences`
or `all-review`, and integer `timeout_seconds` is 1–900 (default 600). It consumes
current export/DAG/flags/markers, reencodes picture and copies AAC. Picture
timestamps/count, AAC payload/timing and decoded PCM identity are independently
checked. Callouts remain uncertain review hypotheses. This is a separate
shareable preview, not native editor import or replacement of the clean master.

## Nine-string interpretation and comparison

This toolset targets deathcore, technical and virtuoso guitar recorded on nine
strings, down-tuned to fundamentals near 32 Hz. Do not apply a generic vocal or
six-string cleanup assumption. A 32 Hz period is 31.25 ms; multiple cycles are
needed for low-register periodicity evidence. Pitch windows, transient timing
resolution and the source master are different objects and must be reported
separately. Current feature analysis uses a separate mono 16 kHz copy; original
masters retain source channels and rate.

Low frequency is musical content until evidence shows otherwise. A blanket
high-pass, rumble removal or mains-frequency notch can remove an intended low
note. Distortion creates strong harmonics and intermodulation; a 64 Hz peak does
not settle whether a 32 Hz fundamental is missing, masked or absent. Chords,
sweeps, bends and rapid chugs can invalidate a single-pitch estimate. Phone audio
that never captured the lowest fundamental cannot be truthfully described as
recoverable through these utilities.

Rhythm assessment must represent rests, syncopation, tuplets, changing meter,
palm mutes, legato and sweep picking. An event nearest a quarter-note grid is not
a correct/incorrect judgment. Keep observed attack candidates separate from
confirmed guitar attacks, expected-rhythm notes and independently calibrated
latency. Automatic structure discovery and recurrence-based issue hypotheses do
not require a predefined intended phrase. A supplied intended reference is needed
for definite correctness judgments, including missed/extra notes, wrong notes or
confirmed phrase mistakes.

The operator confirmed “phase mistakes” means **musical phrase mistakes**.
Signal-phase troubleshooting is outside this project workflow. The phrase lane
consumes source/probe and denoise evidence, candidate or confirmed click/BPM,
nullable tonic/mode/pitch evidence, repeated-pattern proposals and recurrence
comparisons. Intended flags include incomplete phrases, loop start/end mismatch,
skips, rushes and unclear spans with source timestamps and confidence. Current
workers provide periodicity and envelope suggestions, nullable tonal context,
and source-timestamped review spans. The pipeline adds experimental
reference-relative attack/phrase comparisons and generic markers. The tonal tool
adds ranked profile/collection fits while retaining null tonic/mode; confirmed
tonality, semantic phrase grading and native editor imports remain unproven. Discover structure despite missing tonal/intent context; recurrence
duration and onset-motif differences can be review candidates. A hypothesis does
not establish a definite error when the relevant expected pattern is unknown.

Use the following agent loop for every tool:

1. Identify the intended outcome, source/run and available capability; inspect
   the skill, schema and input facts.
2. Propose a small, reversible setting comparison. Identify which observations
   would favor the candidate and which would reveal harm.
3. Run on a bounded representative passage or take; retain bypass/source and
   settings. Compare at matched loudness, inspect residue where relevant, and
   preserve low-string attacks and decays.
4. Research uncertain controls in primary documentation; separate documented
   algorithm behavior from performance measured on this recording.
5. Record hashes, versions, settings, intervals, measured results, confidence
   kind, missing reference data and listening status. Accept, iterate or abstain
   based on the requested outcome rather than on tool exit status.

### Agent graph and context ancestry

The implemented existing-run graph declares
`denoise → bpm → notes (nullable tonic/mode) → phrases → flags → report`, with
parallel tone and raw-click diagnostics. Dedicated pitch, tonal and meter tools
produce separate hash-bound evidence; their calls do not turn the artifact graph
into an autonomous scheduler. Use `pipeline` to evaluate it; it does
not rerender analyses or schedule tool calls. Stages record source/artifact,
settings, registry and reference hashes, dependency identities, and
`preliminary_raw_source` versus `post_denoise` context. The latter requires a
hash-verified restored input from the manifest. Preserve source analysis beside
cleaned analysis so processing artifacts never become the only evidence.

`pipeline` can select exact click/pitch/meter/tonal/comparison receipts through
its five optional run-relative artifact selectors. Selection verification checks
source/upstream/settings/context bindings and retains rejected/not-selected
slots; it never chooses the newest receipt implicitly. A verified selected
legacy pitch payload can carry a **derived current canonical-PCM binding**
instead of a producer manifest receipt, and derived settings instead of a
producer settings receipt. A missing producer worker hash stays `not_recorded`;
compatible current media does not recreate historical producer proof. Preserve
these scope fields beside sampled coverage and timing uncertainty.

The MCP tool registry also describes recommended prior tools and the
identify/research/iterate/acceptance loop. Its recommendations are advisory,
not an enforced runtime scheduler. Individual tool calls remain independently
usable; unsupported controls do not become available through a skill. The
phrase worker reads same-source analysis/notes context and rejects mismatched,
invalid or oversized inputs.

For exact approved-reference semantics, calibration and matching constraints,
read [the phrase DAG interface](PHRASE_DAG.md). Default reference tolerance is
up to 30 ms capped by the match window. The comparator selects a single detector
stream (SuperFlux before spectral-flux before broadband); it never blends or
double-counts those streams. Without an approved reference,
still discover phrase/bar/breakdown proposals and recurrence-based duration or
onset-motif differences, retaining candidate spans and unknown tonal context.
Intended phrases are not an input prerequisite. With a reference, one-to-one attack
comparison still yields mixture-transient mismatch candidates, not confirmed
note errors. Absolute reference-relative early/late labels require an explicit latency
correction value; that declaration still needs a calibration receipt for
musician-facing claims. Unknown capture latency does not block relative loop
duration or onset-motif comparison: a constant offset cancels, while detector
and boundary bias remain uncertain. A four-pulse bar proxy and 4/8/16-pulse
recurrence proposals do not confirm meter or intended phrase length.

Use `markers` for generic source-time CSV/JSON from validated flags. Marker status
remains `needs_review`. Native Final Cut Pro and DaVinci Resolve imports require
future adapters mapping source sample time through the actual clip origin and
frame rate/timecode, with separate application proof. Generic marker export does
not establish those integrations.

Research belongs in `docs/research/`; durable receipts belong in
`docs/agent-notes/`. Original media, rendered outputs and checkpoints remain out
of Git. New runtime hook or plugin configuration requires an explicit target and
is not inferred from a skill invocation. Global authority is
R-HOOK-CONVERGENCE-20261004 (TIN-3692 comment
`98cf680c-7299-4949-bfb2-60079053ad43`); hooks remain advisory under R-N12.

## Primary references and validation

[FFmpeg afftdn](https://ffmpeg.org/ffmpeg-filters.html#afftdn) documents reduction,
noise floor, smoothing, profile capture and residue modes. Its
[loudnorm documentation](https://ffmpeg.org/ffmpeg-filters.html#loudnorm) explains
measured normalization. These are control references, not proof of transparent
guitar restoration. See [the repository research](../research/RESEARCH.md) for
additional upstream references, model/license qualification and limitations.

Skill frontmatter/scaffold checks use the bundled skill-creator
`quick_validate.py`; behavioral review must separately exercise realistic cases:
low-string sustain proposed as noise, ambiguous half/double BPM, distorted
harmonic octave confusion, deliberate tuplets/rests, missing tuning/reference,
reference-relative phrase comparisons, and nonzero stream starts. Synthetic
behavior checks and actual demo listening are separate evidence states. Neither
MCP discovery nor a skill validator establishes AU or Logic compatibility.

The optional extended `just demo` and existing-run `just evaluate` workflows run
the evidence stages sequentially and select exact receipts. The `pipeline` hook
is the graph evaluator; it does not schedule audio processing. Corpus metadata
validation accepts `manifest`, optional `local_root` and bounded deadline; see
[its contract](CORPUS_TOOL_CONTRACT.md). No recording bytes or models are opened
by that operation.

### Restoration and report integration boundary

The restoration worker retains `denoised.wav` as pure denoising and
optionally writes `processed.wav` for subsequent peaking EQ/compression before
normalizing the delivery `cleaned.wav`. `residue.wav` is source minus pure
denoising before gain; it does not measure removal or alteration caused by EQ,
compression or normalization. Analysis on `denoised.wav` therefore describes a
different processing stage from a tone/dynamics-enhanced delivery. Source-level
stage support and new profile controls require their own real-run and registry
receipts; they are not implied by the twenty-seven-tool catalog.

The published enhanced report shows the restoration chain and captured-noise
interval beside the clean player, labels the residue's stage scope and displays
selected manifest/settings/producer bindings, including legacy pitch's derived
bindings and unrecorded producer identity. Actual mobile playback and visual
checks are documented separately from listening acceptance. The report's
analysis-input allowlist currently excludes `processed.wav`; extending it alone
would not extend upstream feature/DAG lineage support. Keep delivery and analyzed
stage labels separate until that coordinated contract is verified.
