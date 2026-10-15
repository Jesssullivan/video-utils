---
name: condense-captions
description: Write captions on the output clock.
---

# Let an agent run the condense captions stage on one talk with bounded time and typed failures, and inspect what it wrote.

**Hook:** MCP tool `condense_captions` (admitted as tool 54, experimental). Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. The worker is `python -m condense captions`; the talk.toml path rules in docs/spec/CONDENSE_TOOL_CONTRACT.md are checked before it starts.

**Capability:** Map each kept word through the EDL and write SRT and WebVTT cues of at most 2 lines of 42 characters. Reads words and edl.json; writes out/<name>.srt and .vtt beneath the config's work/out paths.

## Use and controls

Fallback recipe: `just condense-captions talk.toml`. Run inside `nix develop .#condense`. Every stage reads one talk.toml; `condense/README.md` gives each rule and default.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply, and no guitar tool accepts its outputs (docs/spec/TIMELINE_CONTRACT.md). The 80 Hz high-pass and levelling apply only to the copy whisper reads. Recordings, transcripts and renders stay out of Git.

## Limits

- Synthetic-media tests cover the stage; listening quality, ASR accuracy and physical A/V sync beyond the avsync probe are not established.
- Caption text is whisper's; it is not a verified transcript.

## Agent iteration

Read the stage's printed summary and the files it wrote (out/<name>.srt and .vtt). Change one talk.toml number, rerun this stage and the ones after it, and compare. A finished stage is not an accepted edit: condense_check gates the render and a person reads the bounds report. Never download a model or upload media implicitly.
