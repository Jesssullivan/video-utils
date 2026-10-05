---
name: media-export
description: Export a restored guitar master and synchronized video while retaining original stream timing, sample rate and channels.
---

# Deliver playable media with evidence that restoration preserved timing and source identity.

**Hook:** MCP tool `export` and MCP prompt `media-export`. Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. Skill availability does not imply a server connection has been installed in this agent.

**Capability:** Current WAV and video export for valid run directories; source image stream is preserved where supported.

## Use and controls

Use MCP `export` with a run directory; fallback: `just export "<run-dir>"`. Inspect manifest/source hash, decoded sample count, master rate/channels, audio/video starts and exported codec measurements before delivery.

Use existing delivery profile LUFS/true-peak controls and record actual achieved values. Never silently truncate with shortest-stream behavior or overwrite input. Detect source changes against the run manifest before exporting.

## Guitar-specific interpretation

Preserve the master including 32 Hz content; low-frequency preservation still needs listening/spectral checks. AAC true peaks may differ from WAV. Container start offsets and encoder padding affect timeline checks; compare relative offsets and decoded content, not just rounded duration.

**Review scenario:** A video with delayed audio and unequal stream durations should preserve the original relative timing and image stream without chopping the longer stream.

## Agent iteration

Read [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for discovery and receipts. Inspect the input and supported tool schema, propose a small change tied to the intended outcome, run a bounded comparison, and retain the candidate only if its evidence supports that outcome. Research uncertain controls in primary documentation; save findings in `docs/research/` and run settings, versions, source hash, confidence and limitations in the run/receipt. Abstain when the tool cannot establish the requested fact. Never download a model or upload media implicitly.
