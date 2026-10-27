---
name: narrated-video
description: Plan a labelled narrated video as a stage graph and rerun only the stages a change touches.
---

# Let an agent plan a pre-VFX or simple narrated video from one typed job, with every input bound by digest.

**Hook:** MCP tool `narrated_video_plan` (proposed as tool 62, drafted in `program/tool-drafts/narrated_video.json`, not yet admitted). Root admits it with `narrated_video_run` (63) and the stage tools 64 to 70 in lane L7. Until then the fallback recipes are the hook: `just nv-init`, `just nv-plan`, `just nv-status`, `just nv-explain` and `just nv-verify`, each a `python -m narrate video` command inside `nix develop .#condense`.

**Capability:** `plan` runs the admit gate and keys the 13-stage graph of docs/spec/NARRATED_VIDEO.md. admit checks the narrate job and script digest, consent and revocation, the persona label, the bed record and its acquisition by the operator, tighten on synthetic narration, the knob bounds, the kitpip pin and the edition at Plan. Then each node gets a stage key and one state: `fresh`, `stale`, `corrupt`, `blocked`, `refused`, `not_selected` or `pending_operator`. `explain` prints a stage's key document and each field that changed since its last run. `status` prints the recorded plan. `verify` re-hashes stage directories. None of them runs a stage. In lane L3 the only stage that runs is the kitpip avatar stage, and only in the tests against a stub.

## Use and controls

1. `just nv-init JOB NARRATE_JOB SCRIPT [--still SHA | --card #RRGGBB] [--bed ID]` writes a simple job from the defaults: one segment, a card or a still, no avatar, the bed only when named, edition `Internal` and tighten off (NV-2). Pass `--from FILE` through `python -m narrate video init` for a rendered `NarratedVideo` record instead.
2. `just nv-plan JOB` reads the edition verdict, the refusals, each node's state and reason, and the open operator gates. Fix every admit refusal before any render.
3. Change one knob in the job, then `just nv-explain JOB STAGE`: the `changed` rows name the field, and the rerun set must match the table in the spec's "Stage keys and the store".

Paths come from `NARRATED_VIDEO_ROOT` (default `artifacts/narrated`), `NARRATED_VIDEO_RECORDS` (dhall-to-json renders of narrate jobs, voices, consents and music beds), `NARRATED_VIDEO_EXTERNALS` (the private kitpip pin) with `KITPIP_BIN`, and `NARRATE_STORE`. A job holds digests and record ids, never a path. `just nv-fixture` plans the committed card example. `just nv-test` runs the graph tests.

Knobs worth comparing once the stages land (L4 to L6): `music.duckDb` (6 to 8), `music.bedBelowVoiceLu` (20 by the deck project's ruling 58), avatar `width` (0.18 to 0.26) and `duckMode`. Change one knob, explain, run and compare two verify reports at matched loudness.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply. Every stage manifest that carries narration, an overlay or a bed writes `no_time_stretch: false` and one of `narrated_video_v1`, `avatar_overlay_v1` or `music_bed_v1`, so every guitar tool and `video-utils verify-run` refuse it. The store lives outside `artifacts/runs/` and `artifacts/narrate/`, and the avatar stage never writes inside a narrate run (`avatar_outside_store`). Labels only grow: `synthetic: true`, consent ids, voice ids and the persona pass through every stage. No visible label is required (KP-15).

## Limits

- Never purchase, search for or download a loop or a kitpip build. The operator acquires every bed (`acquiredBy` is `Operator` only). No argument takes a URL.
- kitpip is a pinned external binary checked by digest before every spawn. It is never a flake input and never vendored. Public CI uses the stub in `narrate/tests/fixtures/narrated-video/`, which draws no character.
- Never upload or publish. A client edition gates the bed until the licence PDF digest, a clear Content ID result and a voice-only listen are recorded.
- `fresh` means outputs re-hash to their key. Source checks, a stub render, a real local render, lip sync, listening, Content ID and delivery are separate states, and only the operator closes `pending_operator`.
- `run`, `stage`, `pin-check` and every stage other than avatar arrive in lanes L4 to L6.

## Agent iteration

Plan, change one knob, plan again and explain the stages that went stale. Compare the rerun set with the spec's tested table; a wider set means a knob sits in the wrong stage. Record each comparison as a dated receipt in `docs/agent-notes/` with job ids, keys and digests only: no voice clip, rendered narration, overlay, bed audio, loop name, transcript, store path or host name.
