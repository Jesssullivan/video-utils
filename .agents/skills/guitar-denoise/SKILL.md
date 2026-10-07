---
name: guitar-denoise
description: Conservatively reduce background noise in distorted nine-string guitar while preserving low fundamentals, pick attacks and sustain.
---

# Produce a reversible noise-reduction comparison, with protected 32 Hz guitar content.

**Hook:** MCP tool `denoise` and MCP prompt `guitar-denoise`. Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. Skill availability does not imply a server connection has been installed in this agent.

**Capability:** Current FFmpeg restoration profiles; listening acceptance is separate.

## Use and controls

Use MCP `denoise` with `input` and registered `profile`, default `conservative3`; shared `timeout_seconds` is integer 1–900/default 600. Registered profiles are `bypass`, `conservative3`, `mild6`, `captured8`, `captured12` and `captured8-clarity`; inspect the live schema before calling. Fallback: `just clean "<input>" conservative3`. The CLI/recipe default is `fuller` (operator decision 2026-10-06), which needs `--capture-interval START END --capture-review TEXT` reviewed for this take and otherwise refuses with `capture_interval_required`; the MCP `denoise` descriptor is frozen and does not yet accept that interval or the `fuller` profile. Include bypass and compare the generated matched-level baseline, denoised signal, optional processed signal, final master and residue.

Profile files specify reduction, floor, smoothing and final loudness/peak targets; these are preset controls, not arbitrary MCP arguments. The initial three bypass/3 dB/6 dB comparisons left stronger cleanup unresolved; neither they nor the new stronger candidates have an accepted best tone. Reduction settings are not measured output SNR or a guarantee of transparent removal.

## Source-bound captured comparisons

The captured profiles apply only to original SHA256 `a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`. Their 4.10–4.95-second opening interval is relative to the first decoded original audio sample. Root reviewed and selected it under the user's noise-capture authorization; it is not an operator-exact interval or verified noise-only audio. Sustain, music and other contamination remain uncertain. Source mismatch rejects; never transplant this take's profile or hash to another recording.

The worker copies that interval into private sampling preroll with a 100 ms guard, captures fifteen-band shape per channel, then removes preroll and calibrated denoiser delay so processing starts at original sample zero with native extent retained. This shape is not an independently measured absolute noise floor. Both captured presets use explicit candidate `nf=-40`, `ad=0`, `gs=0`, tracking disabled, with reduction 8 or 12 dB. Stronger reduction and unsmoothed controls can damage pick attacks, low-string sustain/tails or create musical noise. Inspect the capture receipt, removed signal and whole-take transitions rather than assuming the opening sample is clean noise.

`captured8-clarity` adds serial comparison EQ at 300 Hz/−1.5 dB and 2,200 Hz/+1 dB, each Q=0.8, then linked RMS compression: threshold −18 dB, ratio 2:1, attack 15 ms, release 100 ms, knee 3 dB, no makeup gain. A fixed 25% wet/75% dry blend bounds this compressor stage's attenuation to approximately 2.50 dB; it does not bound total denoise/EQ/normalization changes. EQ has frequency-dependent phase and compression changes attack/sustain amplitude. These are experimental settings, not recovered amplifier controls or universally preferable guitar tone.

## Optional low shelf (`fuller-shelf`, unreviewed trial)

Operator ruling 2026-10-07 allows one capped, reversible low shelf as an explicit profile option. Profile key `low_shelf` is a single object `{frequency_hz, gain_db, q}` rendered as FFmpeg `lowshelf` (`t=q`, `r=f64`) before peaking EQ, compression and loudnorm. Bounds (inclusive): frequency 80–160 Hz, gain 0 to +2 dB (boost only; any negative gain, including −0.0, is refused as a cut), Q 0.5–0.707 (at or below 1/√2 the shelf is monotonic, so a boost never dips below unity). At most one shelf per profile; a list or a repeated key is refused. Refusals carry typed codes `low_shelf_invalid`, `low_shelf_multiple`, `low_shelf_frequency_out_of_bounds`, `low_shelf_cut_refused`, `low_shelf_gain_out_of_bounds`, `low_shelf_q_out_of_bounds`, `low_shelf_review_status_required`, `low_shelf_review_status_invalid` and `low_shelf_above_nyquist`, before hashing or decode. A shelf profile must carry `operator_review_status: "unreviewed_trial"` and `listening_acceptance: "not_performed"`; only the operator can widen those after listening. Peaking EQ keeps its 160–6000 Hz bounds; there is still no high-pass, low cut, notch or high shelf.

`fuller` remains the default and is unchanged. `profiles/fuller-shelf.json` is FULLER plus the tone_ab trial shelf at 100 Hz, +1.5 dB, Q 0.7: `just clean "<input>" fuller-shelf --capture-interval START END --capture-review TEXT` (the same capture interval requirement applies). The shelf is reversible procedurally: re-render the unchanged source with `fuller`; never invert a shelf from a rendered master. The tone_ab real-take delta was measured with the shelf after loudnorm and does not transfer to this chain. A synthetic C1 fixture measurement shows the bounded boost only. Preference requires operator listening at matched level against `fuller`; a measured low-band gain is not a listening result. The shelf does not recreate an uncaptured fundamental, the in-room amp tone or a measured microphone response.

`denoised.wav` and `residue.wav` remain pure pre-gain denoise and source-minus-denoise. `processed.wav`, when present, contains the subsequent EQ/compression; `cleaned.wav` normalizes that processed signal, otherwise the pure denoised signal. Denoise residue does not show later EQ/compressor changes. Inspect `noise_capture`, `restoration_stages`, hashes and post-denoise timing limitations in the manifest. Read [the refinement contract](../../../docs/spec/RESTORATION_REFINEMENT_LANE.md).

## Guitar-specific interpretation

Do not use speech denoisers by default. No blanket high-pass or mains-hum notch: 32 Hz is musical and 50/60 Hz can overlap a down-tuned note or its spectrum. Inspect palm mutes, harmonic sustain and low-string decay in residue. An unplayed-looking gap may contain sustain, clicks or room reflections.

**Review scenario:** A quieter output that removes a sustained low-string note fails. A source-matched capture is not proof of noise-only content; a brighter/compressed output is not automatically better. Keep bypass when artifacts outweigh measurable benefit.

## Agent iteration

Read [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for discovery and receipts. Inspect the input and supported tool schema, propose a small change tied to the intended outcome, run a bounded comparison, and retain the candidate only if its evidence supports that outcome. Research uncertain controls in primary documentation; save findings in `docs/research/` and run settings, versions, source hash, confidence and limitations in the run/receipt. Abstain when the tool cannot establish the requested fact. Never download a model or upload media implicitly.
