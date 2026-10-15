---
name: edl-timeline
description: Validate a condense EDL and map source and output times with the Rust timeline.
---

# Give agents the Rust authority's verdict on an EDL before render, publish or verify-run.

**Hook:** MCP tools `timeline_validate` and `timeline_map` (admitted as tools 47 and 48, implemented). Launch the repository stdio server with `just mcp`; inspect `tools/list` before a call. Both need this checkout's `video-utils` binary (`just cli`).

**Capability:** Run `video-utils timeline validate` on an edl.json and return its receipt: fps, clips, segments, total frames and seconds, the largest frame drift and the file's sha256, or a typed reason (edl_invalid family, too_large, edl_unreadable). Reads one file; writes nothing.

## Use and controls

Use `timeline_validate` before render or publish and `timeline_map` for any placement on the output clock (at most 128 queries per call). Fallback: `video-utils timeline validate EDL` and `video-utils timeline map EDL QUERIES`. `just cli` builds the binary in either dev shell.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply, and no guitar tool accepts its outputs (docs/spec/TIMELINE_CONTRACT.md). The 80 Hz high-pass and levelling apply only to the copy whisper reads. Recordings, transcripts and renders stay out of Git.

## Limits

- Validation proves the EDL's internal contract (frames, contiguity, cuts, totals), not that the edit sounds right or keeps every word.

## Agent iteration

Read status, reason, detail, total_frames and max_drift_frames. There are no knobs; fix the EDL's producer, never the validator. status ok is required before render or publish; it is not listening acceptance. Never download a model or upload media implicitly.
