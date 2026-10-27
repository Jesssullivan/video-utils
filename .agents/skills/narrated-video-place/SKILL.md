---
name: narrated-video-place
description: Conform a narrated video's base picture and lay each narration segment on its clock, sample-exact.
---

# Let an agent see where every narration segment lands on the picture's clock before any mix.

**Hook:** MCP tool `narrated_video_place` (proposed as tool 64, drafted in `program/tool-drafts/narrated_video.json`, not yet admitted). Fallback: `just nv-run JOB --until place` or `just nv-stage JOB place`, inside `nix develop .#condense`.

**Capability:** `base` conforms the picture: a card or a still becomes `base.png` at the job's size (a still is scaled to fit and padded), and a video becomes constant-rate H.264 `base.mp4` at its own size and rate, with its sound as `clips.wav` (48 kHz mono) when `keepBaseAudio` is true. `place` resamples each segment's narration to 48 kHz and lays it on the base clock: `Auto` starts where the previous segment ends (0 for the first), `AtSeconds` starts at that second. It writes `voice.wav`, `clips.wav` when kept and `placements.json`, and runs Edition.check at Place over the placed stems' labels.

## Use and controls

1. Plan the job (`narrated-video` skill) and fix every admit refusal.
2. `just nv-run JOB --until place`, then read `placements.json` in the place stage directory (`just nv-explain JOB place` names it): each segment's start and end samples, the program's frames and whether clip sound was kept.
3. Move one anchor in the job and run again: only `place` and `mix` should rerun.

Knobs: segment `anchor`, the card or still `tailS`, a video's `keepBaseAudio`. A card or still is extended to the last narration's end plus `tailS`, rounded up to a whole frame; a video keeps its own length.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply. Narration is a new track: nothing is time-stretched, and the place manifest writes `no_time_stretch: false` with mapping `narrated_video_v1`, so every guitar tool and `video-utils verify-run` refuse it. Labels only grow: `synthetic: true`, consent ids and voice ids pass through.

## Limits

- Refusals: `placement_overlap`, `anchor_invalid`, `anchor_needs_deck` (a `Page` anchor), `base_too_short` (a video that ends before the narration), `base_invalid` and the edition codes at Place. A deck base refuses `base_deck_pending` until lane L8; that refusal is not recorded.
- Scaling to the delivery profile and drawing the picture are `compose`'s (L6).
- No still, video, frame or placed stem enters git. Results carry ids and digests.

## Agent iteration

Record a placement comparison as a dated receipt in `docs/agent-notes/` with job ids, stage keys and placement numbers only: no clip, frame, transcript, store path or host name.
