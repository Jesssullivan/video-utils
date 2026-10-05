---
name: guitar-pipeline
description: Evaluate an existing guitar run's provenance graph and experimental rhythm or phrase review flags, with an optional approved expected-rhythm reference.
---

# Evaluate a guitar run's evidence graph

**Hook:** MCP tool `pipeline` and MCP prompt `guitar-pipeline`. Launch with `just mcp` and inspect `tools/list` before calling.

**Capability:** Current hash-bound artifact ancestry and experimental reference comparisons. This evaluates existing artifacts; it does not rerender analysis, schedule other tools, infer tonic/mode, or autonomously optimize controls.

## Use and controls

Use MCP `pipeline` with `run_dir`, optional `reference` path and optional bounded timeout. Fallback: `just dag "<run-dir>" "<reference-path>"`; omit the reference argument for a candidate-only review. The direct worker is `python3 scripts/dag.py "<run-dir>" [--reference "<path>"]`.

Read [the implemented phrase DAG and reference interface](../../../docs/spec/PHRASE_DAG.md) before constructing a reference. The worker writes `dag.json` and `flags.json`. Inspect original/input hashes, settings/registry/reference hashes, dependency identities and each stage's raw-versus-post-denoise status. Reject modified or unrelated analysis artifacts; a raw-source diagnostic cannot stand in for a restored-input analysis.

The optional version-1 reference must be operator-approved and contain BPM, subdivision, and explicit sorted expected onsets in seconds from the first decoded original audio sample. A matching original source hash is recommended. Phrase spans and declared tuning/tonal context are optional. Defaults are 30 ms tolerance and a match window limited by subdivision. A BPM/subdivision does not generate intended attacks.

For early/late candidate labels, the reference needs explicit `onset_latency_seconds`; without it retain uncalibrated offsets for review. Explicit zero is a requested correction value, not proof of calibration. Do not invent or auto-approve the reference. Compare one-to-one alignment using actual expected rests, tuplets, grace notes, chords and syncopation.

## Guitar-specific interpretation and acceptance

Protect intentional 32 Hz fundamentals and preserve nine-string articulation context throughout the ancestry graph. Tonic/mode and intended notes may remain null. Distorted mixture attacks can be clicks, guitar, merged legato or detector failures; unmatched attacks remain review candidates, never confirmed missed/extra notes.

Reference-relative phrase flags concern observed/expected attack alignment. The final attack does not establish release/sustain end. Incomplete phrase, skip, rush and loop-boundary claims need an intended reference and listening evidence beyond the envelope proposal.

**Review scenario:** An absent expected attack in a legato passage should remain a detection mismatch candidate. A take with no approved reference should expose candidate spans and unknown tonal context without performance grades. A rerendered report must not invalidate the graph through a report-hash cycle.

## Agent iteration

Read [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for discovery and receipts. Inspect the input and supported tool schema, propose a small change tied to the intended outcome, run a bounded comparison, and retain the candidate only if its evidence supports that outcome. Research uncertain controls in primary documentation; save findings in `docs/research/` and run settings, versions, source hash, confidence and limitations in the run/receipt. Abstain when the tool cannot establish the requested fact. Never download a model or upload media implicitly.
