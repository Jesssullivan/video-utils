---
name: guitar-denoise
description: Conservatively reduce background noise in distorted nine-string guitar while preserving low fundamentals, pick attacks and sustain.
---

# Produce a reversible noise-reduction comparison, with protected 32 Hz guitar content.

**Hook:** MCP tool `denoise` and MCP prompt `guitar-denoise`. Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. Skill availability does not imply a server connection has been installed in this agent.

**Capability:** Current FFmpeg restoration profiles; listening acceptance is separate.

## Use and controls

Use MCP `denoise` with input and a registered profile, starting with `conservative3`; fallback: `just clean "<input>" conservative3`. Include `bypass` and compare the generated matched-level baseline, processed master and residue.

Profiles expose `reduction_db`, `noise_floor_db`, `gain_smooth`, `integrated_lufs`, and `true_peak_dbtp`. The initial floor is heuristic; tracking is disabled. Begin at 3 dB reduction; 6 dB is a comparison candidate, not automatic improvement. Noise capture requires an explicitly confirmed interval and authorized profile field; inspect `scripts/media.py --help` and profile validation before proposing unsupported options.

## Guitar-specific interpretation

Do not use speech denoisers by default. No blanket high-pass or mains-hum notch: 32 Hz is musical and 50/60 Hz can overlap a down-tuned note or its spectrum. Inspect palm mutes, harmonic sustain and low-string decay in residue. An unplayed-looking gap may contain sustain, clicks or room reflections.

**Review scenario:** A quieter output that removes a sustained low-string note fails. Keep bypass when artifacts outweigh measurable benefit.

## Agent iteration

Read [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for discovery and receipts. Inspect the input and supported tool schema, propose a small change tied to the intended outcome, run a bounded comparison, and retain the candidate only if its evidence supports that outcome. Research uncertain controls in primary documentation; save findings in `docs/research/` and run settings, versions, source hash, confidence and limitations in the run/receipt. Abstain when the tool cannot establish the requested fact. Never download a model or upload media implicitly.
