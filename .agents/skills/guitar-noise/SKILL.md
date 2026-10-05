---
name: guitar-noise
description: Identify candidate background-noise intervals and measurements in nine-string guitar recordings before choosing a denoising profile.
---

# Separate measured quietness and spectral observations from a confirmed noise-only profile.

**Hook:** MCP tool `noise` and MCP prompt `guitar-noise`. Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. Skill availability does not imply a server connection has been installed in this agent.

**Capability:** Experimental quiet-interval analysis; candidates need listening confirmation.

## Use and controls

Use MCP `noise`; fallback: `just tool-run noise '{"input":"<input>","run_dir":"<run-dir>"}'`. The direct worker is `python3 scripts/guitar_features.py noise "<input>" --run-dir "<run-dir>"`. Inspect candidate intervals together with the original audio and annotate clicks, sustained guitar and handling events before selecting a noise capture.

The experimental worker accepts input/run directory only. It analyzes a separate mono 16 kHz copy in 0.5 s RMS blocks and suggests the lowest 10% of blocks, capped at 20 spans. Its quietness threshold is fixed in this version. Compare candidate level and repeatability; propose capture settings separately to the denoise skill after a listening-confirmed annotation.

## Guitar-specific interpretation

A quiet interval can contain a 32 Hz fundamental, long distorted decay or sparse metronome clicks. A steady low-frequency line can be intended guitar rather than hum. Never authorize a high-pass/notch or a noise-only capture based solely on RMS or stationarity.

**Review scenario:** A low-string sustain below the overall noise threshold remains wanted content and must not become the noise profile.

## Agent iteration

Read [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for discovery and receipts. Inspect the input and supported tool schema, propose a small change tied to the intended outcome, run a bounded comparison, and retain the candidate only if its evidence supports that outcome. Research uncertain controls in primary documentation; save findings in `docs/research/` and run settings, versions, source hash, confidence and limitations in the run/receipt. Abstain when the tool cannot establish the requested fact. Never download a model or upload media implicitly.
