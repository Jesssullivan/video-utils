---
name: condense-recover
description: Rebuild a truncated .mov with untrunc.
---

# Recover a talk recording cut off by a full disk or a crash before condensing it.

**Hook (draft):** MCP tool `condense_recover` in `program/tool-drafts/condense.json`. Not admitted yet: `tools/list` does not show it until root admission (TIN-6511).

**Capability:** Rebuild a recording with no moov atom from a healthy reference made by the same device and app, then report packets found, duration and the share of bytes recovered; fails under 90%. Refuses to overwrite an existing output.

## Use and controls

Fallback recipe: `just condense-recover REF BROKEN FIXED`. Run inside `nix develop .#condense`. Every stage reads one talk.toml; `condense/README.md` gives each rule and default.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply, and no guitar tool accepts its outputs (docs/spec/TIMELINE_CONTRACT.md). The 80 Hz high-pass and levelling apply only to the copy whisper reads. Recordings, transcripts and renders stay out of Git.

## Limits

- untrunc exits 1 even on a full rebuild; the verdict comes from its log and the byte share.
- A short reference rebuilds only part of a long file.

## Agent iteration

Read the Found/Duration lines and the byte share; the log sits beside the output. Try a longer reference from the same session. A rebuilt file still needs a look and a listen; its audio can run longer than its video. Never download a model or upload media implicitly.
