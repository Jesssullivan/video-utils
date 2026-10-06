---
name: guitar-pipeline
description: Evaluate an existing guitar run's provenance graph with explicit bounded evidence selectors and experimental rhythm or phrase review flags, with an optional approved expected-rhythm reference.
---

# Evaluate a guitar run's evidence graph

**Hook:** MCP tool `pipeline` and MCP prompt `guitar-pipeline`. Launch with `just mcp` and inspect `tools/list` before calling.

**Capability:** Current hash-bound artifact ancestry, automatic candidate review and experimental reference comparisons. This evaluates existing artifacts; it does not rerender analysis, schedule other tools, infer tonic/mode, or autonomously optimize controls.

## Use and controls

Use MCP `pipeline` with `run_dir`, optional `reference` path and optional bounded timeout. Fallback: `just dag "<run-dir>" "<reference-path>"`; omit the reference argument for a candidate-only review. The direct worker is `python3 scripts/dag.py "<run-dir>" [--reference "<path>"]`.

Optional MCP selectors are `clicks_artifact`, `pitch_artifact`, `meter_artifact`,
`tonal_artifact` and `comparisons_artifact`. Each selects at most one exact JSON
path relative to `run_dir`, 1–1024 characters. The direct CLI flags use hyphens,
for example `--pitch-artifact pitch.json` and
`--meter-artifact meter/20261005T000000/meter.json`. Choose actual paths from the
worker receipts, not these illustrative names. There is no implicit newest-file
discovery. Absolute paths, colon, backslash, empty or dot-prefixed components,
traversal, `.partial` staging components and symlinks are rejected before evidence
can be used. Missing or nonregular files fail the invocation. Worker bounds are
20 MB per selected JSON and 40 MB total.

Read [the selector contract](../../../docs/spec/GRAPH_TOOL_CONTRACT.md). Inspect
`dag.json.selected_evidence` for every selected slot: its status, exact selector,
artifact hash, upstream and fixed external-context hashes, settings binding, analyzed-input hash, timing
status and metadata. `not_selected` means no selection was requested; `verified`
means provenance passed. `rejected_*` records source, stale-upstream or settings
mismatch without promoting the artifact into usable evidence. Successful graph
execution can contain rejected slots. Sparse pitch coverage, abstentions and null
meter/tonic/mode must remain visible; verified provenance does not confirm the
musical hypothesis. Run evidence tools independently before selecting their
receipts; the pipeline hook never schedules or executes those tools.
Only verified selections and validated upstream hashes become active graph
inputs. Rejected selections retain an audit hash and status with null metadata;
do not reopen them as usable evidence through a report or agent summary.

Distinguish measured bulk DSP compensation from unresolved detector latency,
acoustic travel and physical A/V sync. A legacy manifest can remain
`dsp_delay_uncalibrated` even when rate, frame count and timestamps match. Inspect
the worker's immutable run-local graph history before comparing reruns; archived
report/marker bytes do not imply previous listening acceptance.

Read [the implemented phrase DAG and reference interface](../../../docs/spec/PHRASE_DAG.md) before constructing a reference. The worker writes `dag.json` and `flags.json`. Inspect original/input hashes, settings/registry/reference hashes, dependency identities and each stage's raw-versus-post-denoise status. Reject modified or unrelated analysis artifacts; a raw-source diagnostic cannot stand in for a restored-input analysis.

The optional version-1 reference must be operator-approved and contain BPM, subdivision, and explicit sorted expected onsets in seconds from the first decoded original audio sample. A matching original source hash is recommended. Phrase spans and declared tuning/tonal context are optional. Default tolerance is up to 30 ms, capped by the subdivision-limited match window. A BPM/subdivision does not generate intended attacks.

For absolute reference-relative early/late candidate labels, the reference needs explicit `onset_latency_seconds`; without it retain uncalibrated offsets for review. Relative duration/onset-motif differences between recurrences can still be marked with unknown absolute latency; constant capture offset cancels, while detector/boundary bias remains uncertain. Explicit zero is a requested correction value, not proof of calibration. Do not invent or auto-approve the reference. Compare one-to-one alignment using actual expected rests, tuplets, grace notes, chords and syncopation. Reference comparison selects one available detector stream (SuperFlux before spectral-flux before broadband) rather than blending or double-counting streams; record the chosen identity.

## Guitar-specific interpretation and acceptance

Protect intentional 32 Hz fundamentals and preserve nine-string articulation context throughout the ancestry graph. Tonic/mode and intended notes may remain null. Distorted mixture attacks can be clicks, guitar, merged legato or detector failures; unmatched attacks remain review candidates, never confirmed missed/extra notes.

Run automatic phrase/bar/breakdown discovery and recurrence-based self-consistency review without requiring a predefined intended phrase. Consume duration and onset-motif differences between recurring regions as candidate issues with timestamps, confidence and comparative evidence. Missing tonic/mode or an absent score does not gate segmentation. A reference rendition inferred from repetition can contain its own mistakes or intentional variation.

An approved reference enables stricter observed/expected attack comparison; it is required for definite correctness or missed/extra-note judgments, alongside listening and calibration evidence. The final attack does not establish phrase release/sustain end. A candidate incomplete phrase, skip, rush or loop-boundary difference may be surfaced without a score, but must remain a hypothesis rather than a definite mistake.

**Review scenario:** An absent expected attack in a legato passage should remain a detection mismatch candidate. A take with no approved reference should still expose discovered phrase/bar/breakdown candidates, recurrence duration/motif differences, and unknown tonal context without definite performance grades. A rerendered report must not invalidate the graph through a report-hash cycle.

## Crash recovery of a demo invocation (`run_demo.py --resume`)

`python3 scripts/run_demo.py --resume INVOCATION_ID [--no-latest]` (fallback `just demo-resume ID`) continues one recorded invocation inside the same run directory under the same ID. It replays the receipt's `resume_arguments` and accepts no other settings. A stage is skipped only when its status is success-terminal, every recorded artifact hash matches, its worker file hash is unchanged and every dependency was also skipped; everything downstream of a rerun stage reruns. Outputs of rerun stages are moved, never deleted, into `demo-invocations/<id>/resume-<n>/displaced/` with their hashes. Any hash drift is a typed refusal that writes nothing: `invalid_invocation_id`, `receipt_not_found`, `receipt_invalid`, `receipt_lacks_resume_arguments`, `invocation_already_terminal`, `orchestrator_may_be_alive`, `prior_worker_group_alive`, `resume_lock_held`, `source_hash_drift`, `media_hash_drift`, `stage_artifact_hash_drift`, `worker_hash_drift`, `snapshot_hash_drift`, `media_outcome_unrecorded_run_dir_exists`. Liveness checks use signal 0 only and never signal another process. Resume is crash recovery, not re-analysis, a settings change or a default-adoption path. The memory ceiling remains unknown.

## Agent iteration

Read [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for discovery and receipts. Inspect the input and supported tool schema, propose a small change tied to the intended outcome, run a bounded comparison, and retain the candidate only if its evidence supports that outcome. Research uncertain controls in primary documentation; save findings in `docs/research/` and run settings, versions, source hash, confidence and limitations in the run/receipt. Abstain when the tool cannot establish the requested fact. Never download a model or upload media implicitly.
