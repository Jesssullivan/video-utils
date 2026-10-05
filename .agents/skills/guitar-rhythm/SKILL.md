---
name: guitar-rhythm
description: Discover timing and recurrence differences in technical guitar automatically; use confirmed rhythm and calibration for definite performance grading.
---

# Expose timestamps and potential timing relationships with calibrated uncertainty.

**Hook:** MCP tool `rhythm` and MCP prompt `guitar-rhythm`. Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. Skill availability does not imply a server connection has been installed in this agent.

**Capability:** Current experimental transient offsets; performance-error grading requires an approved reference and calibration.

## Use and controls

Use MCP `rhythm`; fallback: `just analyze "<input>" "<run-dir>"`. Review observed events against original playback. Use confirmed or candidate tempo to discover recurring rhythm/phrase patterns without requiring expected subdivisions or a score. Compare onset motifs and relative drift across recurrences as candidate issues. Establish expected rhythm and recording latency before definite rushed/late or missed/extra-note grading.

Current analysis supports a BPM seed and backend selection. A seed is not a reference score. The reported grid is fitted to recorded transient evidence, so it cannot establish an independent player error or absolute phase. Separate constant capture offset from accumulating drift. Unknown absolute capture latency does not block relative recurrence comparisons: a constant offset cancels, while detector and boundary bias remain uncertain. For an existing run, the pipeline skill can compare attacks against an approved reference and explicit latency correction; resulting mismatch flags remain mixture-transient review candidates.

## Guitar-specific interpretation

Rests, tuplets, syncopation, djent palm mutes, grace notes, legato and sweep picking can invalidate a nearest-beat assumption. Broadband attacks mix clicks, handling and guitar. Preserve signed offsets, confidence and unknowns; never equate every off-beat attack with an error.

**Review scenario:** Deliberate triplets and rests should remain valid. Without an expected-rhythm reference, still discover recurring patterns and mark candidate motif/offset differences for review; leave definite missed/extra-note status unknown.

## Agent iteration

Read [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for discovery and receipts. Inspect the input and supported tool schema, propose a small change tied to the intended outcome, run a bounded comparison, and retain the candidate only if its evidence supports that outcome. Research uncertain controls in primary documentation; save findings in `docs/research/` and run settings, versions, source hash, confidence and limitations in the run/receipt. Abstain when the tool cannot establish the requested fact. Never download a model or upload media implicitly.
