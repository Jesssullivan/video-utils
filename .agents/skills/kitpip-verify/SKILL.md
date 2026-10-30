---
name: kitpip-verify
description: Verify a stored kitpip overlay and its synthetic and consent label chain before compose reads it.
---

# Let an agent prove that a stored overlay is the one rendered and that its labels survived.

**Hook:** MCP tool `avatar_verify` with `avatar.external` `kitpip`, the default (skill `avatar-verify`; proposed as tool 67, drafted in `program/tool-drafts/narrated_video.json`, not yet admitted). Fallback: `just nv-stage JOB avatar_check --segment ID` or `just nv-run JOB`, inside `nix develop .#condense`.

**Capability:** the `avatar_check` stage runs kitpip `verify` on the stored overlay. kitpip re-hashes every file its manifest lists and refuses an unlisted one. The stage then requires `labelled: true`, the frame digest the `avatar` stage measured and the narration's consent ids. Its labels must hold everything the `voice` and `avatar` stages carry, with the job's `labels.persona`. It writes `check.json` and refuses `kitpip_unlabelled` and `label_chain_broken`.

## Use and controls

1. `avatar` and `voice` for the segment must be fresh (`kitpip-overlay`).
2. `just nv-stage JOB avatar_check --segment seg-1`, then read `labelled`, `frames_sha256` and the labels in the stage manifest and `check.json`.

Its only knob is `labels.persona`. A persona change reruns `avatar` and `avatar_check` for every segment, then `place` and what follows. No voice reruns.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply. The check carries the overlay's labels forward; labels only grow.

## Limits

- `verified` means integrity and labels, not lip-sync acceptance. Lip sync stays `pending_operator` until the operator's receipt.
- A refusal here is a verdict: it is recorded for the stage key and holds until the key changes.
- No overlay or frame enters git. Results carry ids, keys and digests.

## Agent iteration

Run `avatar_check` after every `avatar` rerun, and compare `check.json`'s `frames_sha256` with the avatar stage's measurement. Record a mismatch as a dated receipt in `docs/agent-notes/` with job ids, stage keys and digests only.
