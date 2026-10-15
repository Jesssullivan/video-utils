---
name: condense-events
description: Find silences, fillers and pauses.
---

# Let an agent run the condense events stage on one talk with bounded time and typed failures, and inspect what it wrote.

**Hook (draft):** MCP tool `condense_events` in `program/tool-drafts/condense.json`. Not admitted yet: `tools/list` does not show it until root admission (TIN-6511).

**Capability:** Measure silences and 100 ms RMS frames, merge the two whisper passes into words, and mark pauses, fillers, repeats and unworded bursts. Reads the whisper JSON and the analysis wav; writes work/<clip>.words.json, .events.json and .rms.txt beneath the config's work/out paths.

## Use and controls

Fallback recipe: `just condense-events talk.toml`. Run inside `nix develop .#condense`. Every stage reads one talk.toml; `condense/README.md` gives each rule and default.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply, and no guitar tool accepts its outputs (docs/spec/TIMELINE_CONTRACT.md). The 80 Hz high-pass and levelling apply only to the copy whisper reads. Recordings, transcripts and renders stay out of Git.

## Limits

- Synthetic-media tests cover the stage; listening quality, ASR accuracy and physical A/V sync beyond the avsync probe are not established.
- Filler and repeat detection is lexical and timing-based; a wrong guess speeds a word up, it never cuts one.

## Agent iteration

Read the stage's printed summary and the files it wrote (work/<clip>.words.json, .events.json and .rms.txt). Change one talk.toml number, rerun this stage and the ones after it, and compare. A finished stage is not an accepted edit: condense_check gates the render and a person reads the bounds report. Never download a model or upload media implicitly.
