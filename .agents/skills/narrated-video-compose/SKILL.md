---
name: narrated-video-compose
description: Compose a narrated video from its base, kitpip overlays, slide pages and mix, with soft captions, a description and optional pre-VFX layers.
---

# Let an agent compose a labelled narrated cut at a delivery profile and hand its layers to an editor, rerunning only compose when a picture knob changes.

**Hook:** MCP tool `narrated_video_compose` (proposed as tool 69, drafted in `program/tool-drafts/narrated_video.json`, not yet admitted). Fallback: `just nv-stage JOB compose`, `just nv-stage JOB handoff` or `just nv-run JOB`, inside `nix develop .#condense`.

**Capability:** `compose` scales the base to the delivery profile and lays on, bottom to top, the slide layers and the kitpip overlays (ProRes 4444, straight alpha), then encodes `video.mp4` (H.264 yuv420p, AAC 48 kHz) with the captions as a soft track, and `video.upload.mp4` without it. It writes `captions.srt` and `captions.vtt` from each narrate run's cues shifted to the segment start, `description.txt` from a fixed template, `chapters.json` and `compose.json` (the layer plan and encode settings). `handoff`, when `delivery.handoff` is set, writes `layers/` (the bare base, each overlay, each slide picture, the voice, clip and ducked bed stems, the captions) and `edit.json` with the stage keys of every input.

## Use and controls

1. `mix` and, with an avatar, every `avatar` and `avatar_check` node must be fresh (`run` runs those when `KITPIP_BIN` resolves to its pin). `just nv-plan JOB` shows what waits.
2. `just nv-stage JOB compose`, then read `compose.json`: the overlay boxes and starts, the slide runs and their layers, and the avatar-off spans.
3. Change one picture knob and run again: only `compose`, `deliver_check` and `handoff` rerun.

Knobs:

| Knob | Default | Effect |
| --- | --- | --- |
| `delivery.profile` | `Web1080p30` | `Web1080p30` 1920x1080 at 30/1, `Talk` 1920x1080 at the base rate, `Contingency` 1280x720 at 30/1 |
| `avatar.corner`, `width`, `marginPx` | `BR`, 0.22, 32 px | the overlay box, a square of `width` of the frame |
| `avatar.avatarOff`, `fadeS` | none, 0.35 s | pages whose whole span hides the overlay, fading out before and in after |
| `slides.layout` | `Full` | `CardLowerLeft` shows each slide as a lower-left card over the held, dimmed next-clip frame |
| `slides.cardWidth`, `marginPx`, `fadeS`, `dimTo` | 0.42, 64 px, 0.35 s, 0.5 | card width, margin, fades and crossfades, held-frame brightness |
| `captions.soft`, `srt`, `vtt` | on | soft track and sidecar files; `burn` refuses in v1 |
| `labels.personaCue`, `extraNotice` | none (KP-15) | an opening caption line and a last description line, kept when set |

A slide page is a `slide` picture by SHA-256 in the private store, a `Base` page (a named span) or a `Hold` (the base frame at its start, held at full brightness, no card). Adjacent slide pages crossfade in place. A slide page lasts at least two fades.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply. The compose and handoff manifests write `no_time_stretch: false` with mapping `narrated_video_v1`, so every guitar tool refuses them. Labels only grow; a stage that drops one refuses `label_chain_broken`. No visible synthetic or AI-persona label is drawn (KP-7, KP-15).

## Limits

- The slide card was built from the deck seat's description of its card (design Addendum B), not from its code. Card fades, crossfades and the dim match that description; an A/B against a deck cut is not recorded.
- Cards of different heights crossfade with the outgoing card's edge visible until the incoming card is opaque.
- `Full` fades are eased against the mean luma under them; card fades are linear. A `Full` fade shorter than the `min_fade_s` that `compose.json` records for it fails the flash gate. A tall slide's card is narrowed to fit the frame height less two margins.
- An `avatarOff` id that names no slide page refuses `page_unknown` at compose.
- Both MP4s drop every input tag and chapter. A tag outside the allowlist, a chapter, an XMP or EXIF block or a local path in an output refuses `metadata_present`; `compose.json` records the tag keys kept. Handoff slide layers lose their PNG text, EXIF, ICC and time chunks, and every other layer is read for XMP, EXIF, a local path or a WAV chunk beyond `fmt `, `data` and `fact`, which refuses `metadata_present`.
- With records from a guarded intake, `deliver_check` reports `visible_text`: `pending_operator` when a shown asset's text went unread or was opaque.
- FCPXML and OTIO export are phase 2. `edit.json` is not verified in an editing application.
- Refusals: `captions_burn_unsupported`, `captions_missing`, `slides_exceed_program`, `overlay_exceeds_base`, `frames_mismatch` and `label_chain_broken`, each recorded for its key. An FFmpeg failure is not recorded.
- No video, overlay, slide picture or caption text enters git. Results carry ids, keys and numbers.

## Agent iteration

Change one knob (`slides.layout`, `avatar.width`, `avatar.avatarOff`), rerun `compose` and `deliver_check`, and compare the two `compose.json` layer plans and the flash results. Record the comparison as a dated receipt in `docs/agent-notes/` with job ids, stage keys and measurements only.
