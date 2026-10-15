---
name: condense-check
description: Gate a rendered edit.
---

# Let an agent run the condense check stage on one talk with bounded time and typed failures, and inspect what it wrote.

**Hook (draft):** MCP tool `condense_check` in `program/tool-drafts/condense.json`. Not admitted yet: `tools/list` does not show it until root admission (TIN-6511).

**Capability:** Run the named checks (default all): silence (no 1.0 s gap at -35 dB), loud (within 1 LU, true peak under 0 dBTP), sync (probe and real, within 20 ms) and bounds (whisper re-reads at cuts for a person). Reads the output and edl.json; writes a printed report only beneath the config's work/out paths.

## Use and controls

Fallback recipe: `just condense-check talk.toml`. Run inside `nix develop .#condense`. Every stage reads one talk.toml; `condense/README.md` gives each rule and default.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply, and no guitar tool accepts its outputs (docs/spec/TIMELINE_CONTRACT.md). The 80 Hz high-pass and levelling apply only to the copy whisper reads. Recordings, transcripts and renders stay out of Git.

## Limits

- Synthetic-media tests cover the stage; listening quality, ASR accuracy and physical A/V sync beyond the avsync probe are not established.
- bounds prints text for a person to read; it does not pass or fail on its own.

## Agent iteration

Read the stage's printed summary and the files it wrote (a printed report only). Change one talk.toml number, rerun this stage and the ones after it, and compare. A finished stage is not an accepted edit: condense_check gates the render and a person reads the bounds report. Never download a model or upload media implicitly.
