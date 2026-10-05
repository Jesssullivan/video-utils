---
name: guitar-pipeline
description: Evaluate an existing guitar run's provenance graph and experimental rhythm or phrase review flags, with an optional approved expected-rhythm reference.
---

# Evaluate a guitar run's evidence graph

**Hook:** MCP tool `pipeline` and MCP prompt `guitar-pipeline`. Launch with `just mcp` and inspect `tools/list` before calling.

**Capability:** Current hash-bound artifact ancestry, automatic candidate review and experimental reference comparisons. This evaluates existing artifacts; it does not rerender analysis, schedule other tools, infer tonic/mode, or autonomously optimize controls.

## Use and controls

Use MCP `pipeline` with `run_dir`, optional `reference` path and optional bounded timeout. Fallback: `just dag "<run-dir>" "<reference-path>"`; omit the reference argument for a candidate-only review. The direct worker is `python3 scripts/dag.py "<run-dir>" [--reference "<path>"]`.

Read [the implemented phrase DAG and reference interface](../../../docs/spec/PHRASE_DAG.md) before constructing a reference. The worker writes `dag.json` and `flags.json`. Inspect original/input hashes, settings/registry/reference hashes, dependency identities and each stage's raw-versus-post-denoise status. Reject modified or unrelated analysis artifacts; a raw-source diagnostic cannot stand in for a restored-input analysis.

The optional version-1 reference must be operator-approved and contain BPM, subdivision, and explicit sorted expected onsets in seconds from the first decoded original audio sample. A matching original source hash is recommended. Phrase spans and declared tuning/tonal context are optional. Defaults are 30 ms tolerance and a match window limited by subdivision. A BPM/subdivision does not generate intended attacks.

For absolute reference-relative early/late candidate labels, the reference needs explicit `onset_latency_seconds`; without it retain uncalibrated offsets for review. Relative duration/onset-motif differences between recurrences can still be marked with unknown absolute latency; constant capture offset cancels, while detector/boundary bias remains uncertain. Explicit zero is a requested correction value, not proof of calibration. Do not invent or auto-approve the reference. Compare one-to-one alignment using actual expected rests, tuplets, grace notes, chords and syncopation.

## Guitar-specific interpretation and acceptance

Protect intentional 32 Hz fundamentals and preserve nine-string articulation context throughout the ancestry graph. Tonic/mode and intended notes may remain null. Distorted mixture attacks can be clicks, guitar, merged legato or detector failures; unmatched attacks remain review candidates, never confirmed missed/extra notes.

Run automatic phrase/bar/breakdown discovery and recurrence-based self-consistency review without requiring a predefined intended phrase. Consume duration and onset-motif differences between recurring regions as candidate issues with timestamps, confidence and comparative evidence. Missing tonic/mode or an absent score does not gate segmentation. A reference rendition inferred from repetition can contain its own mistakes or intentional variation.

An approved reference enables stricter observed/expected attack comparison; it is required for definite correctness or missed/extra-note judgments, alongside listening and calibration evidence. The final attack does not establish phrase release/sustain end. A candidate incomplete phrase, skip, rush or loop-boundary difference may be surfaced without a score, but must remain a hypothesis rather than a definite mistake.

**Review scenario:** An absent expected attack in a legato passage should remain a detection mismatch candidate. A take with no approved reference should still expose discovered phrase/bar/breakdown candidates, recurrence duration/motif differences, and unknown tonal context without definite performance grades. A rerendered report must not invalidate the graph through a report-hash cycle.

## Agent iteration

Read [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for discovery and receipts. Inspect the input and supported tool schema, propose a small change tied to the intended outcome, run a bounded comparison, and retain the candidate only if its evidence supports that outcome. Research uncertain controls in primary documentation; save findings in `docs/research/` and run settings, versions, source hash, confidence and limitations in the run/receipt. Abstain when the tool cannot establish the requested fact. Never download a model or upload media implicitly.
