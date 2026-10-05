---
name: video-probe
description: Inspect audio/video stream identity, sample rate, channels and timeline before restoring a local guitar recording.
---

# Establish the actual input and stream timing before processing.

**Hook:** MCP tool `probe` and MCP prompt `video-probe`. Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. Skill availability does not imply a server connection has been installed in this agent.

**Capability:** Current stream/hash inspection. Loudness and decoded PCM measurements are produced by a clean run, not guaranteed by probe alone.

## Use and controls

Use MCP `probe` with an input path. Fallback: `just tool-run probe '{"input":"<input>"}'`. Direct worker: `python3 scripts/media.py probe "<input>"`. Inspect source hash, audio/video starts, duration, rate, channels, codec and container start; missing audio or unknown timing is a finding to resolve.

Stream selection and worker limits are implementation facts: inspect returned data and help rather than assuming stereo, 48 kHz, or zero start.

## Guitar-specific interpretation

Keep master rate/channels unchanged. Phone audio may already attenuate the 32 Hz fundamental; absence in the recording cannot justify inventing a recovered fundamental. Separate source stream facts from analysis-copy settings.

**Review scenario:** A trimmed video with nonzero audio start must retain its measured relative audio/video offset through export.

## Agent iteration

Read [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for discovery and receipts. Inspect the input and supported tool schema, propose a small change tied to the intended outcome, run a bounded comparison, and retain the candidate only if its evidence supports that outcome. Research uncertain controls in primary documentation; save findings in `docs/research/` and run settings, versions, source hash, confidence and limitations in the run/receipt. Abstain when the tool cannot establish the requested fact. Never download a model or upload media implicitly.
