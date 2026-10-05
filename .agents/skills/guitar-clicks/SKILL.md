---
name: guitar-clicks
description: Detect metronome-shaped transient candidates and compare an optional bounded template attenuation variant, preserving nine-string guitar low content and overlap uncertainty.
---

# Inspect clicks and compare conservative attenuation

**Hook:** MCP tool `clicks` and MCP prompt `guitar-clicks`; inspect `tools/list` for publication status and the current schema. The bounded NumPy/SciPy worker is implemented. Detection is the default and never writes an audio derivative.

## Use and controls

Use `clicks` with `input`, `run_dir`, optional `bpm` (20–400), and a bounded timeout. Optional paired `template_start`/`template_end` select one 5–120 ms waveform from decoded input audio-relative seconds, not source/video zero. `attenuate` defaults false; opt-in attenuation requires that template plus `template_click_only:true`, recording an operator click-only declaration. `strength` is 0–0.5, default 0.5. This declaration is metadata, not machine verification of identity; do not invent it from a correlation score.

Recipe fallback after registry publication: `just tool-run clicks '{"input":"<input>","run_dir":"<run-dir>"}'`. Direct worker: `python scripts/clicks.py "<input>" --run-dir "<run-dir>" [--bpm BPM] [--template-start START --template-end END] [--attenuate --template-click-only] [--strength 0.25]`. Use the explicit locked analysis interpreter for NumPy/SciPy; no call installs dependencies or downloads models.

Read [the click contract](../../../docs/spec/CLICK_LANE.md) and [primary research](../../../docs/research/CLICK_RESEARCH.md). Without a template, inspect periodic high-frequency transient proposals. With one, inspect waveform fit, residual/overlap evidence and rejected candidates. Identity remains unverified even for accepted fits. Correlation/residual/recurrence guards are recorded fixed algorithm settings, not exposed tuning knobs in this version.

## Guitar-specific comparison and acceptance

Palm mutes, pick attacks, taps and metronome clicks can share spectra. AGC, accents, AAC artifacts and room reflections can invalidate a fixed template. Overlap abstention is useful evidence; never compensate for rejected overlaps by increasing strength beyond the schema or deleting all percussive content.

The optional subtraction estimate is capped at 50% and removes estimate DFT bins below 1.2 kHz before subtraction; the master is not high-passed. This protects measured low-frequency bins including near 32 Hz but leaves low-frequency click content and may introduce ringing. The component estimate is not a recovered original metronome stem.

Outputs occupy a new immutable `run_dir/clicks/<run-id>/`: `clicks.json` and `click-events.csv`, plus `click-attenuated.wav`/`click-estimate.wav` only for attenuation. Verify source/native PCM rate, channels, extent, hashes and original-source lineage. Bounds are 600 seconds, one/two channels, 8–192 kHz and at most 16 million interleaved native samples; the strictest bound applies.

Compare the variant and untouched input at matched loudness, audition the estimate/residue, inspect overlap abstentions and low-frequency measurements, and retain bypass when desired attacks/sustain or phrase tails are harmed. Candidate count, accepted waveform-fit count and attenuation count are different evidence; none proves click identity or listening acceptance. This worker neither normalizes nor changes timing/remuxes video.

**Review scenario:** An isolated repeated click may be attenuated while a coincident guitar attack abstains. A near-32 Hz sustain must remain preserved. If a suitable click-only template is unavailable, return detection findings and uncertainty rather than claiming removal.

## Agent iteration

Identify the intended click treatment, inspect source timing and operator template context, propose a bounded detection/strength comparison, run into a fresh child artifact directory, and compare fit/residue/listening evidence. Research controls in the linked primary sources and actual schema before promising them. Follow [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for provenance and receipts; keep input media and variants local and ignored.
