---
name: guitar-tone
description: Measure spectral character of distorted down-tuned nine-string guitar for comparative tone analysis without claiming recovered amplifier settings.
---

# Describe recorded spectral balance and attack/sustain changes across comparable passages.

**Hook:** MCP tool `tone` and MCP prompt `guitar-tone`. Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. Skill availability does not imply a server connection has been installed in this agent.

**Capability:** Experimental frequency-band measurements; no automatic amplifier or intended-tone classifier.

## Use and controls

Use MCP `tone`; fallback: `just tool-run tone '{"input":"<input>","run_dir":"<run-dir>"}'`. The direct worker is `python3 scripts/guitar_features.py tone "<input>" --run-dir "<run-dir>"`. Compare the same passage in source, bypass and denoised candidates at matched loudness.

The experimental worker accepts input/run directory only. It samples 4096-point Hann windows (0.256 s at 16 kHz) each second and reports 28–80 Hz (a guard band around 32 Hz), 80–250 Hz, 250–2000 Hz and 2000 Hz–Nyquist bands. These fixed diagnostic bands are not an EQ prescription. Record passage and normalization; averaging muted chugs with leads can hide differences.

## Guitar-specific interpretation

Preserve intentional fundamentals near 32 Hz. Distortion redistributes energy into harmonics and intermodulation products; phone acoustics and room response affect the result. Low-band energy, spectral centroid and clipping indicators do not identify pickup, cabinet, amp, or ideal tone by themselves.

**Review scenario:** A denoiser that brightens the average by removing low-string sustain is a damaging change even if the centroid appears more balanced.

## Agent iteration

Read [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for discovery and receipts. Inspect the input and supported tool schema, propose a small change tied to the intended outcome, run a bounded comparison, and retain the candidate only if its evidence supports that outcome. Research uncertain controls in primary documentation; save findings in `docs/research/` and run settings, versions, source hash, confidence and limitations in the run/receipt. Abstain when the tool cannot establish the requested fact. Never download a model or upload media implicitly.
