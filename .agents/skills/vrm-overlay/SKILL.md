---
name: vrm-overlay
description: Render and verify the VRM narrator overlay (draft) for each narrated segment from a pinned renderer and a consented, approved model, inside the job store.
---

# Let an agent render the VRM narrator overlay for each segment from its narration's face timeline, bound to a pinned renderer and model by digest, as a draft for the 11-14 bench.

**Hook:** MCP tools `vrm_overlay` (proposed as tool 71) and `vrm_verify` (72), drafted in `program/tool-drafts/narrated_video.json`, not yet admitted. Fallback: `just nv-stage JOB avatar --segment ID`, `just nv-stage JOB avatar_check --segment ID` or `just nv-run JOB`, inside `nix develop .#condense`. Check the pin first with `just vrm-pin-check`.

**Capability:** a job selects the VRM external with `avatar.external = "vrm"` and `avatar.rig` naming a model record in the private `avatars.json`. admit refuses without the model's SP-R13 likeness consent (`vrm_consent_missing`, `vrm_consent_revoked`), its TIN-7130 appearance approval for this model digest (`vrm_approval_missing`), an open badge decision (`vrm_badge_undecided`) and the Internal edition (`vrm_edition_unruled`). The `avatar` stage builds `face.json` (`face.timeline/v1`, `narration_output` clock) from the segment's narrate run at the base's fps. It runs the pinned renderer on the model from the private store, streams its raw RGBA frames into a ProRes 4444 `overlay.mov`, and writes an `avatar.manifest/v1` with the model digest, the VRM meta licence fields, the renderer, the GPU and driver, and `frames_identity: per_host`. `avatar_check` re-hashes that directory, keeps the frame digest and the narration's consent ids, and adds the likeness consent id to the labels. Neither stage writes inside the narrate run or under `artifacts/runs/`.

## Use and controls

1. The model record holds `sha256`, `bytes`, `likenessConsent` (`{id, ruling: SP-R13}`: the id names a `consents.json` row with the `Likeness` scope, `grantedBy: Operator`, an evidence digest and no revocation), `approval` (`ref: TIN-7130`, `state: approved`, `decidedBy: Operator`, `vrmSha256` equal to the model) and `badge: {burnedIn: null}`. The operator writes it. An agent never writes or edits consent or approval.
2. `just vrm-pin-check` must print `ok: true`. Until the real renderer is built, its pin says `commit_pinned_digest_pending`. It refuses `vrm_pin_pending`, and plan shows both avatar stages `blocked`.
3. `just nv-stage JOB avatar --segment seg-1`. Then read `frames`, `frames_sha256`, `frames_identity`, `gpu`, `vrm.meta` and `states` in the stage manifest.

The avatar key holds the model id and digest, `renderSize`, `labels.persona`, the likeness consent id, the approval evidence, the engine kind and lock digest, and the face source. A new model revision reruns every avatar stage and needs a new approval. Overlay `width`, `corner` and `marginPx` are compose knobs.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply. The stage manifest writes `no_time_stretch: false` with mapping `avatar_overlay_v1`, so every guitar tool refuses it.

## Limits

- Draft (SPR-128). The demos keep kitpip (SPR-120), and the switch waits for the 11-14 bench.
- The registered engine is three-vrm in headless Chromium, stepping `vrm.update(1/fps)` once per frame. Blender with the VRM add-on is the fallback. Neither is built here yet. Public CI renders the stub on a synthetic glTF with no mesh, and never downloads a browser.
- GPU raster is not bit-exact. Compare `frames_sha256` only between renders on one host, renderer and driver.
- The face timeline follows loudness only, so lip sync stays `pending_operator`. Whether offline VRM video carries a burned-in badge is open, so `deliver_check` plans `pending_operator`.
- No `.vrm`, texture, frame, face timeline of a real narration or renderer build enters git. Results carry ids, keys and digests.

## Agent iteration

Change `renderSize` alone, rerun `avatar` on the same host, and compare the frame counts and `frames_sha256` of the two stage manifests. Record the comparison as a dated receipt in `docs/agent-notes/`. It holds job ids, stage keys, digests and the GPU renderer string. No frame, model, store path or host name goes in it.
