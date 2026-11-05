---
name: condense-render
description: Render the condensed talk.
---

# Let an agent run the condense render stage on one talk with bounded time and typed failures, and inspect what it wrote.

**Hook:** MCP tool `condense_render` (admitted as tool 52, experimental). Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. The worker is `python -m condense render`; the talk.toml path rules in docs/spec/CONDENSE_TOOL_CONTRACT.md are checked before it starts.

**Capability:** Build mezzanines, render parts in parallel ([encode] jobs, default 2), join them, apply two-pass loudness to -16 LUFS / -1.5 dBTP and encode HEVC with AAC. With [encode] upload = "h264" it also writes <name>.upload.mp4: the same frames as H.264 with no B-frames and a keyframe every 2 s, the edit's audio copied, refused unless its moov box precedes its mdat box (+faststart) and its video starts at pts and dts 0. Reads edl.json and the recordings; writes work/<clip>.mezz.mkv, the parts, the output mp4 and the optional upload copy beneath the config's work/out paths.

## Use and controls

Fallback recipe: `just condense-render talk.toml`. Run inside `nix develop .#condense`. Every stage reads one talk.toml; `condense/README.md` gives each rule and default.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply, and no guitar tool accepts its outputs (docs/spec/TIMELINE_CONTRACT.md). The 80 Hz high-pass and levelling apply only to the copy whisper reads. Recordings, transcripts and renders stay out of Git.

## Limits

- Synthetic-media tests cover the stage; listening quality, ASR accuracy and physical A/V sync beyond the avsync probe are not established.
- A mezzanine is reused when newer than its recording; delete it after changing frame size or rate.

## Agent iteration

Read the stage's printed summary and the files it wrote (work/<clip>.mezz.mkv, the parts, the output mp4 and, with [encode] upload, out/<name>.upload.mp4 with its printed moov offset and audio first pts). Change one talk.toml number, rerun this stage and the ones after it, and compare. A finished stage is not an accepted edit: condense_check gates the render and a person reads the bounds report. Never download a model or upload media implicitly.
