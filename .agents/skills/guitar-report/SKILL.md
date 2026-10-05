---
name: guitar-report
description: Produce a local evidence report comparing guitar restoration, low-frequency preservation and rhythm candidates without overstating listening or performance acceptance.
---

# Make processed outputs, measured differences and uncertain analysis reviewable in one local report.

**Hook:** MCP tool `report` and MCP prompt `guitar-report`. Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. Skill availability does not imply a server connection has been installed in this agent.

**Capability:** Current portable HTML report; R/Quarto research views are optional and separately verified.

## Use and controls

Use MCP `report` with a run directory; fallback: `just report "<run-dir>"`. Include original/matched-level comparison, processed audio, residue, video where available, measured levels, analysis events and provenance.

For optional click, pitch, meter, tonal and recurrence-comparison panels, first
select exact existing receipts with the `pipeline` tool's five bounded evidence
selectors. Read [the graph contract](../../../docs/spec/GRAPH_FEATURES.md) and
[the report contract](../../../docs/spec/REPORT_FEATURES.md). The renderer opens
only graph-verified selections after current artifact/upstream and fixed tuning
registry hashes match. It does not discover the newest experiment automatically.
Rejected or not-selected slots remain visible as those states.

Show sparse pitch excerpt coverage, analysis-window extent and voicing ambiguity;
keep nullable meter/tonic/mode and comparison attack-edit abstention. A verified
artifact is provenance evidence, not a confirmed musical interpretation. Preserve
previous report bytes through the graph's history receipt before a graph rerun.

Report existing run artifacts; do not fill missing measurements with invented defaults. Record versions, model/checkpoint identities if used, settings, hashes, interval annotations and unresolved limitations. Reports stay local and media remains ignored by Git.

## Guitar-specific interpretation

Keep source facts, candidate inferences and operator listening acceptance separate. Mention 32 Hz protection, low-band evidence and speech-denoiser exclusion. BPM confidence is heuristic; note/meter/phrase/rhythm grades require references. A synthetic pass or louder master cannot prove this guitar sounds better.

**Review scenario:** A run missing rhythm analysis should still report restoration honestly; a run without listening acceptance must not say the sound is approved.

## Agent iteration

Read [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for discovery and receipts. Inspect the input and supported tool schema, propose a small change tied to the intended outcome, run a bounded comparison, and retain the candidate only if its evidence supports that outcome. Research uncertain controls in primary documentation; save findings in `docs/research/` and run settings, versions, source hash, confidence and limitations in the run/receipt. Abstain when the tool cannot establish the requested fact. Never download a model or upload media implicitly.
