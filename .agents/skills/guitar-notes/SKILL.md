---
name: guitar-notes
description: Inspect experimental low-register pitch candidates in distorted nine-string recordings; compare intended notes only with confirmed tuning and a reference.
---

# Surface periodic pitch candidates and ambiguity for annotation, not automatic wrong-note judgments.

**Hook:** MCP tool `notes` and MCP prompt `guitar-notes`. Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. Skill availability does not imply a server connection has been installed in this agent.

**Capability:** Experimental dominant-periodicity estimates; not validated polyphonic transcription.

## Use and controls

Use MCP `notes`; fallback: `just tool-run notes '{"input":"<input>","run_dir":"<run-dir>"}'`. The direct worker is `python3 scripts/guitar_features.py notes "<input>" --run-dir "<run-dir>"`. Inspect candidate windows with audio/spectra; record actual tuning and the lowest intended fundamental before proposing fret/note interpretations.

The experimental worker accepts input/run directory only; its sparse autocorrelation uses 0.256 s frames, a 28–1000 Hz range and at most 120 frames. Range/window controls are not yet exposed. Preserve alternate octaves and unknown results. This sampling cannot transcribe every note in rapid passages; review sustained lows and sweeps separately.

## Guitar-specific interpretation

Distorted harmonics, missing fundamentals, chords, bends and sweeps create octave and instrument-identity ambiguity. A 32 Hz cycle lasts 31.25 ms; pitch windows need multiple cycles and their duration must not be confused with onset precision. Abstain on chords or inconsistent periodicity. Confirm concert reference/tuning and expected notes before labeling wrong notes or assigning string/fret.

**Review scenario:** A strong 64 Hz harmonic with weak 32 Hz energy must retain the low-octave possibility; a chord cannot be presented as an accurately transcribed single note.

## Agent iteration

Read [the agent tool contract](../../../docs/spec/AGENT_TOOLS.md) for discovery and receipts. Inspect the input and supported tool schema, propose a small change tied to the intended outcome, run a bounded comparison, and retain the candidate only if its evidence supports that outcome. Research uncertain controls in primary documentation; save findings in `docs/research/` and run settings, versions, source hash, confidence and limitations in the run/receipt. Abstain when the tool cannot establish the requested fact. Never download a model or upload media implicitly.
