---
name: kitpip-overlay
description: Render the kitpip narrator overlay for each narrated segment from a pinned kitpip binary, inside the job store.
---

# Let an agent render the narrator overlay for each segment from its consented narration, bound to a pinned binary by digest.

**Hook:** MCP tool `kitpip_overlay` (proposed as tool 66, drafted in `program/tool-drafts/narrated_video.json`, not yet admitted). Fallback: `just nv-stage JOB avatar --segment ID` or `just nv-run JOB`, inside `nix develop .#condense`. Check the pin first with `just kitpip-pin-check`.

**Capability:** the `avatar` stage resolves `KITPIP_BIN` against the private pin record (`NARRATED_VIDEO_EXTERNALS`) and checks its SHA-256 and size at plan and again before every spawn. It runs kitpip `analyze` on the segment's narrate run at the base's frame rate, `render` at `renderSize` (WxH, ProRes 4444 `overlay.mov`) and `verify`, all inside the stage's partial directory in the job store. It never writes inside the narrate run or under `artifacts/runs/` (`avatar_outside_store`). It relays kitpip's own refusal codes and adds `kitpip_missing`, `kitpip_pin_pending`, `kitpip_pin_mismatch`, `kitpip_unlabelled` and `label_chain_broken`. It never passes `--allow-unlabelled-test`, `--pipe` or `--badge`, so the overlay is kitpip's unadorned default character (KP-19).

## Use and controls

1. The job needs an `avatar` block and `labels.persona` (`just nv-init ... --avatar --persona P`; opt-in until L6, NV-8). `voice` for the segment and `base` must be fresh.
2. `just kitpip-pin-check` must print `ok: true`. While the pin's release binary digest is pending it refuses `kitpip_pin_pending`, and plan shows both avatar stages `blocked`.
3. `just nv-stage JOB avatar --segment seg-1`, then read `frames`, `frames_sha256`, `fps`, `size`, `rig` and `states.render` in the stage manifest.

Knobs in the avatar key: `rig`, `rigRevisionSha256` (the pin's default rig revision when unset), `renderSize` and `labels.persona`. Overlay `width`, `corner` and `marginPx` are compose knobs (L6): changing them reruns no avatar. Set `segments[].avatar` false to hide the overlay on a dense screen.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply. The stage manifest writes `no_time_stretch: false` with mapping `avatar_overlay_v1`, so every guitar tool refuses it. The overlay keeps `synthetic: true`, the narration's consent ids and voice ids, and the job's persona.

## Limits

- kitpip is never a flake input and never vendored. Its pin is private (NV-1); `program/externals.json` registers the shape only. No kitpip repository URL, art or binary enters git.
- Public CI renders the synthetic stub, an opaque square on a transparent field. A real render is local, CPU-only and bounded by `narrate/bounded.sh`.
- No visible label is drawn (KP-7, KP-15). Lip sync stays `pending_operator`; a fresh stage is not an accepted overlay.
- No overlay, frame or narration enters git. Results carry ids, keys and digests.

## Agent iteration

Change `rig` or `renderSize` alone, rerun `avatar`, and compare `frames_sha256` and the frame count of the two stage manifests. Record the comparison as a dated receipt in `docs/agent-notes/` with job ids, stage keys and digests only: no overlay, frame, store path or host name.
