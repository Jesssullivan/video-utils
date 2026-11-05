---
name: avatar-overlay
description: Render the narrator overlay for each narrated segment with the avatar external the job names (kitpip now, the VRM renderer draft later), inside the job store.
---

# Let an agent render the narrator overlay for each segment from its consented narration, with the external the job names.

**Hook:** MCP tool `avatar_overlay` (proposed as tool 66, drafted in `program/tool-drafts/narrated_video.json`, not yet admitted). Fallback: `just nv-stage JOB avatar --segment ID` or `just nv-run JOB`, inside `nix develop .#condense`.

**Capability:** the `avatar` stage dispatches on the job's `avatar.external` (`narrate/video/avatar.py`). `kitpip` is the default and the current implementation (skill `kitpip-overlay`). `vrm` is the renderer draft for the 11-14 bench (skill `vrm-overlay`). Any other value refuses `avatar_external_unknown` at admit. Both write `overlay/overlay.mov` (ProRes 4444, straight alpha) and `overlay/manifest.json` into the stage directory, so compose reads either the same way. `program/dags/narrated-video.json` names the stage `avatar_overlay` with `dispatch.by: avatar.external`. The tool name stays the same when a job moves from kitpip to vrm.

## Use and controls

1. Check the pin of the job's external: `just kitpip-pin-check` or `just vrm-pin-check` must print `ok: true`. A pending pin blocks both avatar stages at plan.
2. `just nv-stage JOB avatar --segment seg-1`, then read `renderer.kind`, `frames`, `frames_sha256`, `fps`, `size` and `states.render` in the stage manifest.

The external's own skill lists the knobs in its key. Overlay `width`, `corner` and `marginPx` are compose knobs and rerun no avatar.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply. The stage manifest writes `no_time_stretch: false` with mapping `avatar_overlay_v1`, so every guitar tool refuses it.

## Limits

- Lip sync stays `pending_operator`. A fresh stage is not an accepted overlay.
- A vrm digest compares only with a render on the same host, renderer and driver (`frames_identity: per_host`).
- No overlay, frame, model or narration enters git. Results carry ids, keys and digests.

## Agent iteration

Change one knob of the external, rerun `avatar` only, and compare `frames_sha256` and the frame count of the two stage manifests. Record the comparison as a dated receipt in `docs/agent-notes/` with job ids, stage keys and digests only.
