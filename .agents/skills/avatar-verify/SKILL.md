---
name: avatar-verify
description: Verify a stored narrator overlay and its synthetic and consent label chain with the avatar external the job names, before compose reads it.
---

# Let an agent prove that a stored overlay is the one rendered and that its labels survived, whatever external drew it.

**Hook:** MCP tool `avatar_verify` (proposed as tool 67, drafted in `program/tool-drafts/narrated_video.json`, not yet admitted). Fallback: `just nv-stage JOB avatar_check --segment ID` or `just nv-run JOB`, inside `nix develop .#condense`.

**Capability:** the `avatar_check` stage dispatches on the job's `avatar.external`. With `kitpip` it runs kitpip `verify` and checks the label chain (skill `kitpip-verify`). With `vrm` it re-checks the likeness consent and approval gates, re-hashes the overlay directory under its `avatar.manifest/v1` and adds the likeness consent id to the labels (skill `vrm-overlay`). Both write `check.json` and refuse `label_chain_broken`. `program/dags/narrated-video.json` names the stage `avatar_verify` with `dispatch.by: avatar.external`.

## Use and controls

1. `avatar` and `voice` for the segment must be fresh (`avatar-overlay`).
2. `just nv-stage JOB avatar_check --segment seg-1`, then read `labelled`, `frames_sha256` and the labels in `check.json`.

Its only knob is `labels.persona`. A persona change reruns `avatar` and `avatar_check` for every segment.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply. The check carries the overlay's labels forward; labels only grow.

## Limits

- `verified` means integrity and labels, not lip-sync acceptance.
- A refusal is a verdict for the stage key and holds until the key changes.
- No overlay or frame enters git. Results carry ids, keys and digests.

## Agent iteration

Run `avatar_check` after every `avatar` rerun, and compare `check.json`'s `frames_sha256` with the avatar stage's measurement. Record a mismatch as a dated receipt in `docs/agent-notes/` with job ids, stage keys and digests only.
