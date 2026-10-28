---
name: narrated-video
description: Plan a labelled narrated video as a stage graph and rerun only the stages a change touches.
---

# Let an agent plan a pre-VFX or simple narrated video from one typed job, with every input bound by digest.

**Hook:** MCP tools `narrated_video_plan` (proposed as tool 62) and `narrated_video_run` (63), drafted in `program/tool-drafts/narrated_video.json`, not yet admitted. Root admits them with the stage tools 64 to 70 in lane L7. Until then the fallback recipes are the hook: `just nv-init`, `just nv-plan`, `just nv-run`, `just nv-stage`, `just nv-quick`, `just nv-status`, `just nv-explain`, `just nv-verify` and `just kitpip-pin-check`, each a `python -m narrate video` command inside `nix develop .#condense`.

**Capability:** `plan` runs the admit gate and keys the 13-stage graph of docs/spec/NARRATED_VIDEO.md. admit checks the narrate job and script digest, consent and revocation, the persona label, the bed record and its acquisition by the operator, tighten on synthetic narration, the knob bounds, the kitpip pin and the edition at Plan. Then each node gets a stage key and one state: `fresh`, `stale`, `corrupt`, `blocked`, `refused`, `not_selected` or `pending_operator`. `explain` prints a stage's key document and each field that changed since its last run. `status` prints the recorded plan. `verify` re-hashes stage directories. `run` runs the stale stages one at a time and stops at the first refusal: lane L4 runs `script`, `voice`, `voice_qa`, `base`, `place`, `music` and `mix`, so a simple job ends with a mixed stem, and lane L5 adds `avatar` and `avatar_check` per segment when the job has an avatar and `KITPIP_BIN` resolves to its pin. `stage` runs one node whose inputs are fresh. `compose`, `deliver_check` and `handoff` wait for lane L6; `run` lists them under `waiting_on_lane`.

## Use and controls

1. `just nv-init JOB NARRATE_JOB SCRIPT [--still SHA | --card #RRGGBB] [--bed ID]` writes a simple job from the defaults: one segment, a card or a still, no avatar unless `--avatar --persona P` (opt-in until L6, see "Avatar opt-in until L6" in the spec), the bed only when named, edition `Internal` and tighten off (NV-2). `--client` makes a client delivery: edition `ClientNarrated` (NV-6). The defaults voice a synthetic segment, so `--edition ClientVoiceOnly` refuses `edition_voice_refused`. A project that needs operator takes only passes `--from FILE` through `python -m narrate video init` with a rendered `NarratedVideo` record.
2. `just nv-plan JOB` reads the edition verdict, the refusals, each node's state and reason, and the open operator gates. Fix every admit refusal before any render.
3. `just nv-run JOB` runs the stale stages inside `narrate/bounded.sh`. Read `ran`, `refused` with its node and detail, and `waiting_on_lane`. A recorded refusal (`recorded: true`) holds until its key changes; an unrecorded one (a missing source, no lexical release, an engine down) clears on the next run. `just nv-quick JOB NARRATE_JOB SCRIPT [--bed ID]` does init and run in one step.
4. Change one knob in the job, then `just nv-explain JOB STAGE`: the `changed` rows name the field, and the rerun set must match the table in the spec's "Stage keys and the store". Run again and compare `ran` with that set.
5. If a run stops at the 900 s limit, run it again: finished stages stay fresh.

Paths come from `NARRATED_VIDEO_ROOT` (default `artifacts/narrated`), `NARRATED_VIDEO_RECORDS` (dhall-to-json renders of narrate jobs, voices, consents and music beds), `NARRATED_VIDEO_EXTERNALS` (the private kitpip pin) with `KITPIP_BIN`, and `NARRATE_STORE`. `run` also needs `NARRATE_STORE` (every source by digest) and `NARRATE_LEXICAL_DIR`, and its records directory holds `engines.json` and `pronunciation.json`. A job holds digests and record ids, never a path. `just nv-fixture` plans the committed card example and runs `nv-quick` on a synthetic workspace. `just nv-test` runs the graph and simple-path tests. The stage skills are `narrated-video-place`, `music-bed`, `kitpip-overlay`, `kitpip-verify` and `narrated-video-mix`.

Knobs worth comparing: `music.duckDb` (6 to 8), `music.bedBelowVoiceLu` (20 by the deck project's ruling 58) and `duckMode` (L4, rerun only `mix`), and avatar `width` (0.18 to 0.26, L6). Change one knob, explain, run and compare two `mix` measurements at matched voice loudness.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply. Every stage manifest that carries narration, an overlay or a bed writes `no_time_stretch: false` and one of `narrated_video_v1`, `avatar_overlay_v1` or `music_bed_v1`, so every guitar tool and `video-utils verify-run` refuse it. The store lives outside `artifacts/runs/` and `artifacts/narrate/`, and the avatar stage never writes inside a narrate run (`avatar_outside_store`). Labels only grow: `synthetic: true`, consent ids, voice ids and the persona pass through every stage. No visible label is required (KP-15).

## Limits

- Never purchase, search for or download a loop or a kitpip build. The operator acquires every bed (`acquiredBy` is `Operator` only). No argument takes a URL.
- kitpip is a pinned external binary checked by digest before every spawn. It is never a flake input and never vendored. Public CI uses the stub in `narrate/tests/fixtures/narrated-video/`, which draws no character.
- Never upload or publish. A client edition gates the bed until the licence PDF digest, a clear Content ID result and a voice-only listen are recorded.
- `fresh` means outputs re-hash to their key. Source checks, a stub render, a real local render, lip sync, listening, Content ID and delivery are separate states, and only the operator closes `pending_operator`.
- `just kitpip-pin-check` checks the private pin against `program/externals.json` and `KITPIP_BIN` against the pin. A pin whose release binary digest is pending blocks the avatar stages (`kitpip_pin_pending`). `compose`, `deliver_check` and `handoff` (L6) are still to come. A deck base waits for lane L8 (`base_deck_pending`).
- The fixture voice is a sine from the fake engine. Its numbers check the pipeline; they say nothing about how a narration sounds.

## Agent iteration

Plan, change one knob, plan again and explain the stages that went stale. Compare the rerun set with the spec's tested table; a wider set means a knob sits in the wrong stage. Record each comparison as a dated receipt in `docs/agent-notes/` with job ids, keys and digests only: no voice clip, rendered narration, overlay, bed audio, loop name, transcript, store path or host name.
