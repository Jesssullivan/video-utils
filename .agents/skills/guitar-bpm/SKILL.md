---
name: guitar-bpm
description: Estimate metronome or guitar tempo candidates in deathcore recordings, including half/double-time ambiguity, without grading performance.
---

# Find plausible pulse periods and observed transient timestamps; keep ambiguity visible.

**Hook:** MCP tool `bpm` and MCP prompt `guitar-bpm`. Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. Skill availability does not imply a server connection has been installed in this agent.

**Capability:** Current bounded classical transient/periodicity analysis; optional librosa only when installed.

## Use and controls

Use MCP `bpm`; fallback: `just analyze "<input>" "<run-dir>"`. Compare candidate families and actual transient timestamps against representative audio, then rerun with a manually confirmed BPM seed if available.

Current worker options: `--backend stdlib|librosa`, `--bpm` (20–400 seed), and `--run-dir`. The automatic family preference is heuristic. Analysis uses a separate mono 16 kHz copy and 5 ms envelope hop; it never changes the master or proves note identity.

## Guitar-specific interpretation

Distorted pick attacks, palm mutes and clicks overlap. Periodic high-frequency transients are not confirmed metronome identities. Breakdown half-time, blast-like passages and tuplets can support several candidates. A chosen BPM does not establish meter or expected note rhythm.

**Review scenario:** Present near 88/177 BPM as an ambiguous family until the operator confirms the pulse; silence should yield unknown rather than a confident tempo.

## Agent iteration

Read [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for discovery and receipts. Inspect the input and supported tool schema, propose a small change tied to the intended outcome, run a bounded comparison, and retain the candidate only if its evidence supports that outcome. Research uncertain controls in primary documentation; save findings in `docs/research/` and run settings, versions, source hash, confidence and limitations in the run/receipt. Abstain when the tool cannot establish the requested fact. Never download a model or upload media implicitly.
