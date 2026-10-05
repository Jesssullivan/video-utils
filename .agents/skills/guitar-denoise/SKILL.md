---
name: guitar-denoise
description: Conservatively reduce background noise in distorted nine-string guitar while preserving low fundamentals, pick attacks and sustain.
---

# Produce a reversible noise-reduction comparison, with protected 32 Hz guitar content.

**Hook:** MCP tool `denoise` and MCP prompt `guitar-denoise`. Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. Skill availability does not imply a server connection has been installed in this agent.

**Capability:** Current FFmpeg restoration profiles; listening acceptance is separate.

## Use and controls

Use MCP `denoise` with `input` and registered `profile`, default `conservative3`; shared `timeout_seconds` is integer 1–900/default 600. Registered profiles are `bypass`, `conservative3`, `mild6`, `captured8`, `captured12` and `captured8-clarity`; inspect the live schema before calling. Fallback: `just clean "<input>" conservative3`. Include bypass and compare the generated matched-level baseline, denoised signal, optional processed signal, final master and residue.

Profile files specify reduction, floor, smoothing and final loudness/peak targets; these are preset controls, not arbitrary MCP arguments. The initial three bypass/3 dB/6 dB comparisons left stronger cleanup unresolved; neither they nor the new stronger candidates have an accepted best tone. Reduction settings are not measured output SNR or a guarantee of transparent removal.

## Source-bound captured comparisons

The captured profiles apply only to original SHA256 `a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`. Their 4.10–4.95-second opening interval is relative to the first decoded original audio sample. Root reviewed and selected it under the user's noise-capture authorization; it is not an operator-exact interval or verified noise-only audio. Sustain, music and other contamination remain uncertain. Source mismatch rejects; never transplant this take's profile or hash to another recording.

The worker copies that interval into private sampling preroll with a 100 ms guard, captures fifteen-band shape per channel, then removes preroll and calibrated denoiser delay so processing starts at original sample zero with native extent retained. This shape is not an independently measured absolute noise floor. Both captured presets use explicit candidate `nf=-40`, `ad=0`, `gs=0`, tracking disabled, with reduction 8 or 12 dB. Stronger reduction and unsmoothed controls can damage pick attacks, low-string sustain/tails or create musical noise. Inspect the capture receipt, removed signal and whole-take transitions rather than assuming the opening sample is clean noise.

`captured8-clarity` adds serial comparison EQ at 300 Hz/−1.5 dB and 2,200 Hz/+1 dB, each Q=0.8, then linked RMS compression: threshold −18 dB, ratio 2:1, attack 15 ms, release 100 ms, knee 3 dB, no makeup gain. A fixed 25% wet/75% dry blend bounds this compressor stage's attenuation to approximately 2.50 dB; it does not bound total denoise/EQ/normalization changes. EQ has frequency-dependent phase and compression changes attack/sustain amplitude. These are experimental settings, not recovered amplifier controls or universally preferable guitar tone.

`denoised.wav` and `residue.wav` remain pure pre-gain denoise and source-minus-denoise. `processed.wav`, when present, contains the subsequent EQ/compression; `cleaned.wav` normalizes that processed signal, otherwise the pure denoised signal. Denoise residue does not show later EQ/compressor changes. Inspect `noise_capture`, `restoration_stages`, hashes and post-denoise timing limitations in the manifest. Read [the refinement contract](../../../docs/spec/RESTORATION_REFINEMENT_LANE.md).

## Guitar-specific interpretation

Do not use speech denoisers by default. No blanket high-pass or mains-hum notch: 32 Hz is musical and 50/60 Hz can overlap a down-tuned note or its spectrum. Inspect palm mutes, harmonic sustain and low-string decay in residue. An unplayed-looking gap may contain sustain, clicks or room reflections.

**Review scenario:** A quieter output that removes a sustained low-string note fails. A source-matched capture is not proof of noise-only content; a brighter/compressed output is not automatically better. Keep bypass when artifacts outweigh measurable benefit.

## Agent iteration

Read [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for discovery and receipts. Inspect the input and supported tool schema, propose a small change tied to the intended outcome, run a bounded comparison, and retain the candidate only if its evidence supports that outcome. Research uncertain controls in primary documentation; save findings in `docs/research/` and run settings, versions, source hash, confidence and limitations in the run/receipt. Abstain when the tool cannot establish the requested fact. Never download a model or upload media implicitly.
