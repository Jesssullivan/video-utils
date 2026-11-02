# Narrated video (`narrate/video/`)

Authority: operator direction KP-13 (Linear TIN-7476 comment `94248deb`), rulings
KP-7 (`0f367c48`), KP-14 (`1c16fbda`), NV-1 to NV-5 (`9db389dc`), the deck
project's ruling 59(d) (`e427ecfc`), KP-15 (`4ab7fc27`), NV-6 (`92605219`),
KP-19 (`f446ae28`) and NV-8 (`df0ed8e6`), SPR-120 and SPR-128 (Linear TIN-7125 comments
`59b5cb12` and `33022456`), repository AGENTS.md and
R-HOOK-CONVERGENCE-20261004 (R-N11, R-N12, R-N13). This spec is
written before the code that implements it. Where it names a later lane, that
lane owns the code and may refine a detail here in the same PR that implements
it.

A narrated video is a script read in a consented synthetic voice over a base
picture, with captions, labels and an optional music bed and kitpip avatar. It
serves pre-VFX and simple narration jobs. One typed job describes it. A stage
graph plans the job, runs only the stages whose inputs changed and writes a
hash-bound manifest per stage. It is a speech workflow beside `narrate/` and
`./condense`. The guitar axioms do not apply, and no stage time-stretches
source media.

## Operator decisions (2026-10-27)

| Id | Decision |
| --- | --- |
| NV-1 | This repository may name `kitpip`. The narrate `Consent` type gains an optional `persona` field whose real value stays private. No kitpip repository URL or art enters this repository, and the kitpip pin lives in a private record |
| NV-2 | Simple-job defaults: edition `Internal` until a first listening receipt. A mono mix when a bed is present, until an A/B. No music bed in a client delivery until the licence PDF, the Content ID check and a voice-only listen pass. Tighten off for synthetic narration. These are defaults: a project may override tighten (see "Tighten") |
| NV-3 | An agent may read and summarise a vendor's public licence terms. The operator downloads the certified licence PDF, and its digest goes into the private `MusicBed` record. Agents never purchase |
| NV-4 | The no-avatar half starts now: L2 spec and types, L3 graph core, L4 simple path with voice and music bed. kitpip plugs in after its procedural-geometry release (KP-12) merges |
| KP-7, KP-14 | The overlay shows the narrator mark with no visible "AI persona" badge. Client deliveries stay voice-only with picture-in-picture off, except where 59(d) applies |
| 59(d) | The deck project's ship cut carries the kitpip avatar. Its "picture-in-picture off" meant no camera of the operator, not the avatar. For that video this supersedes the voice-only part of KP-14. The `ClientNarrated` edition carries it |
| KP-15 | No visible synthetic or AI-persona label is required in captions, descriptions or on-frame marks. Manifest metadata (`synthetic: true`, consent ids, persona) stays. This supersedes KP-7's "labels in captions and description" |
| NV-6 | `ClientNarrated` is the default edition of every client delivery: synthetic voice and kitpip allowed, the bed gated on licence and Content ID. `ClientVoiceOnly` stays available per project. This supersedes the voice-only part of KP-14 for client deliveries |
| KP-19 | kitpip's default overlay is the unadorned character, with no ring, picture-in-picture background or logo stamp. `--badge` restores the ring and mark. The wrapper never passes it |
| NV-8 | kitpip stayed opt-in until lane L6 landed. The avatar is now on by default (KP-13, NV-6), and a job can still turn it off |
| SPR-120 | kitpip now, VRM after the bench. Internal demos use kitpip v0.1.0. The VRM offline renderer (`avatar.manifest/v1`, a second external) is built as a draft, and the switch waits for the 11-14 bench |
| SPR-128 | The VRM offline renderer draft goes into this repository: `avatar.manifest/v1`, a second external and synthetic rig fixtures, ready for the 11-14 bench. The demos keep kitpip (see "Avatar externals and `avatar.manifest/v1`") |

Music-bed levels (NV-2, from the deck seat's answers the operator adopted): the
bed sits 20 dB under the voice and a sidechain ducks it a further 6 to 8 dB
under the foreground. The operator picked the 20 dB level from a
matched-loudness A/B (the deck project's ruling 58). Fades are 3 s in and 5 s
out. Narration is re-measured at -16 LUFS integrated, and the whole mix is
never loudness-normalised. Drift over 0.5 LU or a true peak above -1.5 dBTP fails.
Bed audio never enters git.

## Lanes

| Step | Owns | Starts after | Done when |
| --- | --- | --- | --- |
| L2 spec and types | this spec, the `TIMELINE_CONTRACT.md` amendment, `narrate/dhall/{Edition,MusicBed,NarratedVideo}.dhall`, the Consent `persona` field, examples and their checks | the design | `just narrate-dhall-check` passes, the contract rows run red then green |
| L3 graph core | `narrate/video/{graph,keys,store,admit}.py`, `program/dags/narrated-video.json`, the kitpip stub, `init`, `plan`, `status`, `explain` | L2 | key, invalidation and freshness tests |
| L4 simple path | `script`, `voice`, `voice_qa`, `base`, `place`, `music`, `mix` | L3 | `nv-quick` on fixtures yields a mixed stem. Audio tests pass |
| L5 kitpip pin and avatar | `program/externals.json` (the public registration), the private pin record, `pin-check`, `avatar` and `avatar_check`, tools 66 and 67 drafts and skills | kitpip release, L4 | pin tests and one local render with a digest-only receipt |
| L6 compose and delivery | `compose`, `deliver_check`, `handoff`, `just/narrated-video.just`, the slide card, the avatar default (NV-8) | L5 | alpha, caption, label, profile, slide and flash tests |
| L7 tools and skills | tool drafts and 8 skills, admission of tools 62 to 70 | L6 | `just mcp` lists the tools, admission tests pass |
| L8 deck seam | the deck seat with L3 to L6 owners | L6 | a fake-deck fixture passes, then one internal deck cut |
| L9 acceptance | the operator | L7, L8 | listening, lip sync and labels leave `pending_operator` by receipt. `accept` records listening and lip sync by Softproxy decision id |

L2 adds types, checks and a contract amendment. It adds no runtime primitive, so
it adds no MCP tool or skill. Each later stage lands with its typed MCP hook
draft and skill (L7 admits them).

## Stages

```text
admit -> script -> voice[seg] -> voice_qa[seg] --+
base --------------------------------------------+--> place -> avatar[seg] -> avatar_check[seg] --+
music -------------------------------------------+-----------> mix --------------------------------+--> compose -> deliver_check -> handoff (opt-in)
```

| # | Stage | Fan-out | Outputs | Mapping | Optional |
| --- | --- | --- | --- | --- | --- |
| 0 | `admit` | none | `admit.json` gate results, read-only. Edition check at Plan | none | no |
| 1 | `script` | segment | lexical findings (advisory, R-N12) and the spoken-text digest | none | no |
| 2 | `voice` | segment | one narrate run under `artifacts/narrate/<run_id>/` | `narration_v1` | no |
| 3 | `voice_qa` | segment | narrate verify and evaluate receipt | none | no |
| 4 | `base` | none | conformed `base.mp4` and `base.json` (fps, size, length, clip sound if kept) | none | no |
| 5 | `place` | none | `placements.json`, `voice.wav` and `clips.wav` on the base clock. Edition check at Place | `narrated_video_v1` | no |
| 6 | `avatar` | segment | `overlay.mov` (ProRes 4444) and its manifest, drawn by the job's avatar external (kitpip or vrm). Tool `avatar_overlay` | `avatar_overlay_v1` | edition-gated |
| 7 | `avatar_check` | segment | label-chain result. Tool `avatar_verify` | none | with avatar |
| 8 | `music` | none | `bed.wav` (48 kHz) and the bed manifest | `music_bed_v1` | yes |
| 9 | `mix` | none | `mix.wav`, ducked bed stem, measured loudness, true peak and duck depth | `narrated_video_v1` | no |
| 10 | `compose` | none | `video.mp4`, upload copy, captions, `description.txt`, chapters | `narrated_video_v1` | no |
| 11 | `deliver_check` | none | `deliver_check.json`: per-gate states and `delivery_gate`. Edition check at DeliverCheck | none | no |
| 12 | `handoff` | none | pre-VFX layers and `edit.json` | `narrated_video_v1` | yes |

Stages without an edge between them run in parallel, at most 2 at once, each
inside `narrate/bounded.sh`. kitpip runs once per segment, on that segment's
narrate run, so its admission chain (narrate manifest, `synthetic: true`,
consent ids, output digest) stays intact.

`program/dags/narrated-video.json` publishes this table, and
`narrate/video/graph.py` holds the same table. A test keeps the two equal.

## Stage keys and the store

Lane L3 implements this section in `narrate/video/{keys,store,graph,admit}.py`.

A stage key is the SHA-256 of the canonical JSON of a key document. The
document holds the stage id, the segment, a hand-bumped `impl`, the tool name,
version and binary digest, the FFmpeg identity on render stages, the resolved
knobs, the edition and the sorted inputs. The render stages are `base`,
`place`, `music`, `mix`, `compose` and `handoff`. Their FFmpeg identity is the
SHA-256 of the first line of `ffmpeg -version`. The `voice` tool's binary
digest is the SHA-256 of its engine's sorted file digests (binary and
weights), or null for an engine that pins no file. The git commit is recorded in
the stage manifest and kept out of the key.
A stage's `impl` rises when its output changes for the same inputs. `voice`
is at 2 because KP-15 removed its caption label, so a voice rendered before
KP-15 plans stale. `base`, `compose`, `handoff` and `deliver_check` are at 2
for TIN-7788 (see "Compose and delivery").

Canonical JSON has sorted keys, no whitespace and UTF-8. `dhall-to-json` writes
the Double `-16.0` as `-16`, so an integral number is written as an integer and
any other float as its repr string. A non-finite number refuses.

A key reads three kinds of input:

- **Knobs.** Each job or record field belongs to the first stage whose output
  depends on it (table below). A field that only a later stage reads reruns
  only that stage and what follows it.
- **Sources.** SHA-256 digests of private-store blobs: the script, still,
  video, deck files and bed loops. With a private store named, `plan` blocks a
  stage whose source is missing (`source_missing`).
- **Upstream inputs.** An upstream node's manifest `content_sha256`, or one
  measured value from it. `avatar` reads only the base's measured `fps`, so a
  deck re-assembled at the same rate keeps every overlay fresh.

| Stage | Knobs |
| --- | --- |
| `script` | narrate job id, input kind, lexical pin |
| `voice` | the narrate job record without its gates, its voice records, its engine record (no endpoint, files by digest) and its pronunciation table's digest |
| `voice_qa` | the narrate job's gates |
| `base` | base kind and fields except `tailS`, delivery profile |
| `place` | segment ids and anchors, `tailS`, `keepBaseAudio`, `tighten`, `labels.persona` |
| `avatar` | rig and rig revision (the pin's default rig when unset), render size, `labels.persona` |
| `avatar_check` | `labels.persona` |
| `music` | bed id, each layer's digest, bytes, rate, channels, tempo factor and gain, 48 kHz |
| `mix` | the music block except the bed id, delivery loudness, true peak, drift and channels |
| `compose` | avatar corner, width, margin, `avatarOff` and `fadeS`, the slides block, captions, labels, delivery profile |
| `deliver_check` | the job's digest, which covers all of delivery with `handoff`, plus the bed's licence PDF digest and Content ID result, labels and the guarded intake's visible-text summary |
| `handoff` | none beyond its inputs |

A stage manifest's `content_sha256` leaves out `run_dir`, `created_utc` and
the commit. A rerun that writes the same outputs therefore keeps every
downstream key, and the cascade stops there. A stage may list an output under
`volatile_outputs` when its bytes differ between identical runs only by a run id
and a time. The `voice` stage lists its narrate run's own `manifest.json` and
records that run's `content_sha256` in its measurements instead. Freshness still
re-hashes a volatile output, and `volatile_outputs` may name only listed outputs.

`admit` is a gate, not a data input. It runs at every plan. Its refusal blocks
every other stage. Its codes are `narrate_job_missing`,
`script_digest_mismatch`, `consent_missing`, `consent_revoked`,
`persona_label_missing`, `bed_record_missing`, `bed_acquisition_agent`,
`bed_layers_invalid`, `tighten_on_synthetic`, `knob_out_of_bounds`,
`slides_invalid`, `page_unknown`, `avatar_external_unknown`,
`kitpip_pin_mismatch`, `vrm_pin_mismatch`, the VRM gate codes (`vrm_model_missing`,
`vrm_model_invalid`, `vrm_digest_mismatch`, `vrm_consent_missing`, `vrm_consent_revoked`,
`vrm_approval_missing`, `vrm_badge_undecided`, `vrm_edition_unruled`) and the three edition codes.

| State | Meaning |
| --- | --- |
| `fresh` | the current directory has this key and re-hashes |
| `stale` | no run, a changed key, or an upstream node that is not fresh. The key is unknown until the upstream runs |
| `corrupt` | the current directory has this key but fails re-hashing. A run moves it to `history/` |
| `blocked` | admit refused, FFmpeg, kitpip or a source is missing, or an upstream node is blocked or refused |
| `refused` | the stage refused for this exact key. It stays refused until the key changes |
| `not_selected` | an optional stage the job turns off: no avatar, a segment's avatar off, no bed, handoff off |
| `pending_operator` | `deliver_check` is fresh but an operator gate (licence PDF, Content ID) is open |

The store:

```text
artifacts/narrated/<job_id>/        NARRATED_VIDEO_ROOT overrides artifacts/narrated
  job.json                          the NarratedVideo record (dhall-to-json render)
  graph.json                        the last recorded plan (init, plan --record)
  current.json                      {stages: {node: {key, dir, content_sha256}}, refusals: {node: {key, code, detail}}}
  history/                          stage directories that failed re-hashing, moved aside
  stages/<stage>[/<segment>]/<key16>/  one finished stage: its outputs and manifest.json (kind nv_stage)
```

A stage writes into `<key16>.partial/`, which is renamed into place when the
stage finishes. `current.json` then points at it. `plan` never reads a partial
directory. `current.json` replaces symlinks, and a symlink in a stage directory
makes it `corrupt`. Freshness re-hashes every listed output, refuses an
unlisted file, checks the manifest's own digest and key, and never reads an
mtime. The store refuses a root under `artifacts/runs/` or `artifacts/narrate/`.
v1 keeps every stage directory until the operator removes the job.

| Change | Reruns (tested) |
| --- | --- |
| Bed level | `mix`, `compose`, `deliver_check` |
| One segment's script | that segment's `script`, `voice`, `voice_qa`, `avatar` and `avatar_check`, then `place`, `mix`, `compose`, `deliver_check` |
| Overlay width | `compose`, `deliver_check` |
| Avatar-off pages or slide layout | `compose`, `deliver_check`, and `handoff` when it is on |
| kitpip rig or pin | every `avatar` and `avatar_check`, then `compose`, `deliver_check` |
| Persona label | every `avatar` and `avatar_check`, then `place`, `mix`, `compose`, `deliver_check`. No voice |
| Deck re-assembled with the same takes | `base`, `place`, `mix`, `compose`, `deliver_check` |
| Content ID result recorded | `deliver_check` |
| Handoff turned on | `handoff`, and `deliver_check` because it keys on the job's digest |

### kitpip pin and the stub

kitpip is registered publicly and pinned privately (NV-1). `program/externals.json`
registers it: the record shape, the manifest schema `kitpip.manifest/v0`, the
mapping `avatar_overlay_v1`, how a binary resolves and the gate states. It holds
no pin value, and a test refuses a registration that holds one. The pin itself
is a private externals record, named by `NARRATED_VIDEO_EXTERNALS`. It holds the
version, the full source commit, per-system binary digests and byte counts, the
manifest schema, the mapping, the default rig (id, revision and the SHA-256 of
its rendered JSON) and a gate state. It holds no URL, path or host, and loading
refuses one.

A pin whose release binary does not exist yet names the commit, leaves its
binary table empty and says `gate_state: commit_pinned_digest_pending`. It
resolves `pending`: plan blocks both avatar stages with `kitpip_pin_pending`, and
`pin-check` refuses the same code. A pin with a digest says
`registered_hash_bound_not_accepted`. `KITPIP_BIN` names the binary. Its digest
and size are checked against the pin at plan and again before every spawn. A
mismatch refuses `kitpip_pin_mismatch` and nothing runs. A missing binary blocks
the avatar stages (`kitpip_missing`).

kitpip prints one JSON line. The wrapper relays a refusal line
(`{"refused": code}`, exit 1) with kitpip's own code in the narrate stderr
shape. It never passes `--allow-unlabelled-test`, `--pipe` or `--badge`, so the
overlay is the unadorned default character (KP-19). The avatar stage runs
`analyze`, `render` and `verify` into its partial directory in the job store.
It refuses `avatar_outside_store` when that directory lies inside the narrate
run or under `artifacts/runs/`.

Public CI runs `narrate/tests/fixtures/narrated-video/kitpip_stub.py`, pinned
by the test-only record `kitpip-externals.json` beside it. The stub speaks the
command shape of kitpip at the pinned commit. It draws an opaque square on a
transparent ProRes 4444 field, so every corner pixel is transparent. It holds no
kitpip art and draws each kitpip refusal on request.

### Avatar stages (lane L5)

`run` runs `avatar` and `avatar_check` once per segment when the job has an
avatar block, the segment's `avatar` is on and `KITPIP_BIN` resolves to its pin.

| Stage | Reads | Runs | Writes | Refuses |
| --- | --- | --- | --- | --- |
| `avatar` | the segment's narrate run, the base's measured `fps`, the pin | `analyze RUN --fps N/D --rig ID --out analyze/`, `render prosody.json --rig ID --size WxH --encode mov --out overlay/`, `verify overlay/` | `overlay/` (kitpip's manifest, `overlay.mov`, `frames.sha256`, `prosody.json`) and `analyze/` | kitpip's own codes, `kitpip_unlabelled`, `kitpip_pin_mismatch` (schema, rig or rig revision not the keyed one), `label_chain_broken`, `avatar_outside_store` |
| `avatar_check` | the stored overlay, the `voice` and `avatar` manifests | `verify overlay/` | `check.json` (labelled, frame digest, consent ids, the avatar's content digest) | `kitpip_unlabelled`, `label_chain_broken` (a frame digest or consent id that differs, or a dropped label) |

kitpip writes `avatar_overlay_v1` into its own manifest, and the avatar stage
manifest records the same mapping with the narration's run id and content
digest. The stage manifest measures frames, the frame digest, fps, size, the rig
and `show_badge`. Its states are `source_checks: passed`, `render: stub` or
`local`, and `lip_sync: pending_operator`. Only the operator closes lip sync.

### Avatar externals and `avatar.manifest/v1`

SPR-120 and SPR-128 add a second avatar external, the VRM offline renderer, as a draft for the 11-14
bench. The demos keep kitpip. A job picks its external with `avatar.external`: `kitpip` (the default)
or `vrm`. Any other value refuses `avatar_external_unknown`. Both externals write `overlay/overlay.mov`
(ProRes 4444, straight alpha) and `overlay/manifest.json` into the avatar stage directory, so `compose`
and `handoff` read either one the same way. `narrate/video/avatar.py` sends each avatar node to its
external.

`avatar.manifest/v1` (`narrate/video/avatar_manifest.py`) is the overlay manifest of both:

| Field | Meaning |
| --- | --- |
| `schema`, `kind` | `avatar.manifest/v1`, `avatar_overlay` |
| `renderer` | `{kind: kitpip \| vrm, name, version}`. A vrm renderer also names its `engine` (`kind` and `lock_sha256` as pinned), its `step` (the rational `{num, den}` equal to `1 / rate`, as the renderer reported it) and the `gpu` (`vendor`, `renderer`, `driver`) that drew the frames |
| `synthetic`, `consent_ids`, `voice_ids` | the narration's labels |
| `rig` | `{id, sha256}`. For vrm, the model record id and the model's SHA-256 |
| `rate`, `size`, `frames`, `frames_sha256` | the overlay's rational fps, size, frame count and the SHA-256 of its frames as drawn |
| `frames_identity` | `bit_exact`, or `per_host`: `frames_sha256` matches only another render on the same host, renderer and driver. Every vrm overlay is `per_host`, because GPU raster is not bit-exact |
| `outputs` | every file in the overlay directory except the manifest, with its SHA-256 |
| `timeline` | `avatar_overlay_v1`, `no_time_stretch: false`, clock `narration_output` |
| vrm only | `vrm` (`sha256`, `bytes`, `spec_version` `1.0` or `0.x`, `meta`: the licence fields of the model's VRM meta), `face` (the face timeline's schema, digest, clock and source), `likeness_consent_id`, `approval` (`ref`, `evidence_sha256`) and `badge: {burned_in: false, decision: open}` |

`kitpip.manifest/v0`, which kitpip 0.1.0 and the stub write, stays accepted. It reads as renderer kind
`kitpip` with `frames_identity` unstated, so every kitpip overlay rendered before v1 keeps its key and
stays fresh. The kitpip registration lists both schemas (`manifest_schemas`), and a kitpip pin may name
either. kitpip's stage keys do not change.

### VRM external (draft)

`program/externals.json` registers `vrm` with no pin value: the record shape, the manifest schema
`avatar.manifest/v1`, the mapping `avatar_overlay_v1`, the face schema `face.timeline/v1`, the engine,
the command shape, the gates and how the renderer resolves. The pin is the `vrm` entry of the same
private externals record (`NARRATED_VIDEO_EXTERNALS`). It holds the version, the source commit,
per-system renderer digests and byte counts, the engine (`kind` and the SHA-256 of its dependency lock),
a visibility and a gate state, and no URL, path or host. `VRM_RENDERER_BIN` names the renderer. Its
digest and size are checked against the pin at plan and again before every spawn. A mismatch refuses
`vrm_pin_mismatch`. A pin with no renderer digest yet says `commit_pinned_digest_pending` and blocks
both avatar stages (`vrm_pin_pending`). No renderer blocks them as `vrm_renderer_missing`.

**Engine.** The registered engine is `@pixiv/three-vrm` on three.js in headless Chromium, driven by
Puppeteer or Playwright. For each face frame the page sets the expressions, look-at and head from
`face.json` and calls `vrm.update(1 / fps)` once, so time moves only by frame steps, never by the wall
clock. That stepping is the renderer's contract. The wrapper cannot watch the page's clock, so it checks
the renderer's report instead: `step` must be the rational `{num, den}` equal to `1 / fps`, and
`renderer.engine.kind` must be the pin's `engine.kind`. Blender with the VRM add-on is the fallback.
Neither is built here yet. Its lockfile will be hash-bound in the pin, and CI never downloads a browser.
Tests run a stub renderer.

**Command shape.** The wrapper (`narrate/video/vrm.py`) speaks one:

| Command | Output |
| --- | --- |
| `RENDERER --version` | one JSON line on stdout: `{version, commit}` |
| `RENDERER render --vrm FILE --face FILE --size WxH` | raw RGBA8 frames on stdout (straight alpha, rows top-down), exactly `frames * W * H * 4` bytes, with frames and fps from `face.json`. The last stderr line is one JSON report `{frames, step: {num, den}, renderer: {name, version, engine: {kind}}, gpu: {vendor, renderer, driver}}` on exit 0, or `{refused, detail}` on exit 1 |

The wrapper hashes the pipe as it streams it into FFmpeg (`prores_ks` 4444, `yuva444p10le`), then writes
`frames.sha256` and the v1 manifest itself. It never passes `--badge` or `--realtime`. It refuses
`vrm_frames_mismatch` when the byte count is not the face timeline's frame count. A report without a
renderer, GPU vendor or driver, with a step other than `{num, den}` equal to `1 / fps`, or with an
engine kind other than the pin's refuses `vrm_report_invalid`. The manifest records the pin's engine
kind and lock digest, so the overlay traces to the engine lock without the stage manifest. A renderer
refusal is relayed with its own code. A timeout, a crash, an FFmpeg failure or a renderer off its pin is
a failure, not a verdict.

**Face timeline.** `face.json` (`narrate/video/face.py`, schema `face.timeline/v1`) is the renderer's
only view of the narration. It holds one frame per overlay frame on the `narration_output` clock, at the
base's fps. Frame i shows the face at `i * den / num` seconds into its segment's `narration.wav`: its
loudness window starts at sample `floor(i * rate * den / num)` and ends where frame i + 1 starts, and a
remainder shorter than one frame at the end is not drawn. Each frame has a mouth viseme and weight
(`sil`, `aa`, `ih`, `ou`, `ee`, `oh`), blink `[left, right]`, the five VRM mood presets, look `[yaw,
pitch]` and head `[yaw, pitch, roll]`. It is bound to the narrate run by `run_id`, `content_sha256` and
the WAV's digest. v1 has one source, `loudness_envelope`. The mouth opens with the RMS of each frame
(`aa`, weight `min(1, 4 rms)`) and closes to `sil` below 0.01. The eyes blink on a fixed schedule (first
at 1.3 s, then every 3.7 s), and mood, look and head stay neutral. A forced aligner's word timings,
phonemes within words and an expression track are later sources.

**The model record.** `avatar.rig` names a record in the private `avatars.json`. The record holds `id`,
`kind: vrm`, the model's `sha256` and `bytes`, a `likenessConsent` reference (`id`, `ruling: SP-R13`),
an `approval` (`ref`, `state`, `decidedBy`, `decidedAt`, `vrmSha256`, `evidenceSha256`) and `badge:
{burnedIn: null}`. The model is a private-store blob found by digest and re-hashed before the renderer
spawns. The wrapper reads its VRM meta from the glTF JSON chunk: `VRMC_vrm` for 1.0, `VRM` for 0.x. It
records the licence fields and nothing else from the meta, so no author or model name. A model with no
meta licence refuses `vrm_meta_missing`, and a file that is not a VRM binary glTF refuses `vrm_invalid`.

**Likeness consent.** The consent itself is not in the model record. `likenessConsent.id` names a row
of `consents.json`, the table voice consent goes through, typed by `narrate/dhall/Consent.dhall`. Its
`Scope` union has a `Likeness` alternative for SP-R13. The row's `scopes` list holds `Likeness`, its
`grantedBy` is `Operator`, its `evidenceSha256` is a 64-hex digest and its `revokedAt` is null. A consent
written inside the model record grants nothing. Revoking the row in `consents.json` stops the next plan
and the next render. `Likeness` never grants a voice: a voice or job scope of `Likeness` refuses
`consent_scope` (`narrate/policy.py`, and `narrate/dhall/check.py` for the examples).

**Gates.** admit refuses, and the stage refuses again before the renderer spawns, when:

| Code | Rule |
| --- | --- |
| `vrm_model_missing`, `vrm_model_invalid` | `avatar.rig` names no record, or the record does not read |
| `vrm_digest_mismatch` | `avatar.rigRevisionSha256`, when set, is not the record's `sha256` |
| `vrm_consent_missing`, `vrm_consent_revoked` | `likenessConsent` has no non-empty `id` or its `ruling` is not `SP-R13`; the id names no `consents.json` row; the row's `scopes` is not a list holding `Likeness`, its `grantedBy` is not `Operator` or it has no evidence digest; or the row is revoked |
| `vrm_approval_missing` | no TIN-7130 approval with `state: approved`, `decidedBy: Operator`, an evidence digest and `vrmSha256` equal to this model. A new model revision needs a new approval |
| `vrm_badge_undecided` | the record sets `badge.burnedIn`. Whether offline VRM video carries a burned-in badge is not ruled: no renderer draws one, and no record may settle it |
| `vrm_edition_unruled` | the edition is not `Internal`. Other editions wait for a ruling after the 11-14 bench |

With a VRM avatar, admit also lists `vrm_badge_decision` as an operator gate at `deliver_check`, so
`deliver_check` plans `pending_operator`. `deliver_check` reports the gate as well: when an avatar stage
measured renderer kind `vrm`, `gates.vrm_badge_decision` is `pending_operator`, so
`delivery_gate.operator_states_open` lists it and `public_upload_allowed` stays false on that gate alone.
`handoff` copies each overlay's manifest beside its layer, so the open badge, `frames_identity: per_host`
and the likeness consent id travel with `avatar-<segment>.mov`.

**Stages.** `avatar` builds `face.json` from the segment's narrate run at the base's fps, renders the
model and writes the overlay. `avatar_check` re-hashes the overlay directory under its v1 manifest,
keeps the frame digest the avatar stage measured and the narration's consent ids, and grows the labels.
`frames_sha256` is the digest of the renderer's raw RGBA stream. The ProRes encode is not lossless, so
`avatar_check` cannot recompute that digest from `overlay.mov`. The stage labels add the likeness consent
id to the narration's consent ids. The avatar key holds `external`, the model id and digest,
`renderSize`, the persona, the likeness consent id, the approval's ref and evidence digest, the engine
kind and lock digest and the face schema and source. The tool identity is the renderer's version and
digest. Its states are `source_checks: passed`, `render: stub` or `local`, `lip_sync: pending_operator`,
`appearance_approval: approved`, `badge_decision: open` and `frames_identity: per_host`.

Public CI runs `narrate/tests/fixtures/narrated-video/vrm_renderer_stub.py`, pinned by the test-only
`vrm-externals.json` beside it, on a synthetic model from `vrm_rig_fixture.py`. The model is a binary
glTF with VRM 1.0 or 0.x meta and no mesh. The stub draws a square with eye marks that close on a blink
and a mouth bar as tall as the mouth weight, on a transparent field. It holds no model art.

## Commands

`python -m narrate video <command>`, standard library and FFmpeg, inside
`nix develop .#condense`. A refusal prints `{"ok": false, "refused": code,
"detail": ...}` on stderr and exits 1.

| Command | Recipe | Effect |
| --- | --- | --- |
| `init --job ID --narrate-job ID --script FILE [--still SHA \| --card #RRGGBB] [--bed ID] [--edition E] [--client] [--persona P \| --no-avatar]` | `just nv-init` | writes a simple job from `NarratedVideo.defaults`, with the avatar on where the edition allows one (NV-8). `--client` makes a client delivery: `ClientNarrated` (NV-6); another edition refuses `edition_not_client`. The defaults voice a synthetic segment, so `--edition ClientVoiceOnly` refuses `edition_voice_refused`: a voice-only job comes through `--from` (the deck example). admit refuses (a voice without consent, an avatar without a persona) before anything is written |
| `init --job ID --from FILE` | | writes a rendered record, or the one with that id in a list of them |
| `plan JOB [--record] [--json]` | `just nv-plan` | keys every node and prints its state, reason and key. Read-only. `--record` writes `graph.json`. Exit 1 when admit refuses |
| `status JOB [--json]` | `just nv-status` | prints the recorded `graph.json` and its `pending_operator` gates. Refuses `graph_stale` when it lists an acceptance `acceptance.json` does not hold |
| `explain JOB STAGE [--segment ID]` | `just nv-explain` | prints the key document and each field that changed since the stage's last run |
| `verify DIR` | `just nv-verify` | re-hashes a stage directory or every current stage of a job |
| `run JOB [--stages S,...] [--until S] [--force S,...] [--json]` | `just nv-run` | runs the stale stages (`script` to `handoff`, with `avatar` and `avatar_check` when the job has an avatar) and stops at the first refusal. Finished stages stay fresh. Records `graph.json` |
| `pin-check [--externals FILE] [--external kitpip\|vrm]` | `just kitpip-pin-check`, `just vrm-pin-check` | checks the private pin against `program/externals.json` and `KITPIP_BIN` (or, with `--external vrm`, `VRM_RENDERER_BIN`) against the pin. Refuses `kitpip_pin_missing`, `kitpip_pin_pending`, `kitpip_pin_mismatch` or `kitpip_missing`, or the `vrm_` forms (`vrm_renderer_missing` for a missing renderer) |
| `stage JOB STAGE [--segment ID]` | `just nv-stage` | runs one node when every input is fresh, else refuses `stage_input_stale` |
| `stage JOB voice --from-run RUN_DIR [--segment ID] [--replace]` | `just nv-stage-voice-from-run JOB RUN_DIR` | adopts a narrate run already rendered and verified elsewhere (`narrate render --prerendered` for an `AudioCppBatch` engine) as the voice node instead of voicing it. See "Adopting a rendered run" |
| `fixture --out DIR` | `just nv-fixture` | writes a synthetic workspace: records, a private-store stand-in and a fixture lexical release |
| `init` then `run` | `just nv-quick JOB NARRATE_JOB SCRIPT [ARGS]` | a simple job in one step |
| `intake BUNDLE --out DIR --narrate-template ID --voice ID --engine ID (--persona P \| --no-avatar) [--job ID] [--store DIR] [--tail-s S] [--denylist FILE] [--denylist-sha256 HEX]` | `just narrated-video-intake` | a demo bundle to a job and one narrate job per beat, claims gated (see "Demo bundle intake"). Writes nothing on a refusal |
| `claims BUNDLE [--denylist FILE] [--denylist-sha256 HEX]` | `just narrated-video-claims` | the private-terms guard and the spoken-number claims gate alone, one row per segment. Exit 1 when a segment refuses |
| `fixture --out DIR --bundle` | `just nv-intake-fixture` | also writes the synthetic bundle `demo-fixture` under `DIR/bundle/` |
| `accept JOB --gate G --decision ID --video-sha256 HEX` | `just nv-accept JOB GATE DECISION VIDEO` | records the operator's acceptance of `listening` or `lip_sync` for the current `deliver_check` render, by Softproxy decision id and the sha256 of the cut it saw. See "Operator acceptance" |
| `subject JOB [--json]` | `just nv-subject` | prints the job's guard subject: every text its records hold that it voices or labels, written and spoken. The Cade narrate worker reads it in its own process for the BS-21 guard. Refuses `shown_text_unread` for a job that shows an asset with no guarded intake's marker. See "Guard subject and cut" |
| `cut JOB [--json]` | `just nv-cut` | prints the current `deliver_check` render, its machine gate states, the operator gates still pending and the gates an acceptance of that render closed. Digests and gate names only. Refuses `machine_gates_failed` when a machine gate failed. See "Guard subject and cut" |

Paths come from flags or the environment: `--root` (`NARRATED_VIDEO_ROOT`),
`--records` (`NARRATED_VIDEO_RECORDS`, the directory of `jobs.json`,
`voices.json`, `consents.json`, `music-beds.json` and, for a VRM avatar, `avatars.json`), `--externals`
(`NARRATED_VIDEO_EXTERNALS`, the private pin record of both avatar externals), `--store` (`NARRATE_STORE`) and `--lexical`
(`NARRATE_LEXICAL_DIR`). `run` and `stage` need the store, because every source
comes from it by digest. Their records directory also holds `engines.json` and
`pronunciation.json` for narrate. `just nv-fixture` plans the committed card
example against the committed records. It then runs `nv-quick --no-avatar` end
to end on a synthetic workspace through `deliver_check` and prints the mix
measurements and the delivery gates. `nv-run`, `nv-stage` and
`nv-quick` run inside `narrate/bounded.sh`.

## Adopting a rendered run

An `AudioCppBatch` engine renders out of process: `narrate plan` writes the
batch, the GPU window runs it, and `narrate render CONFIG --prerendered DIR`
makes the run. The `voice` stage cannot do that itself (`run_voice` would refuse
`prerendered_required`), so `stage JOB voice --from-run RUN_DIR` adopts that run
(TIN-7564). The segment defaults to the job's only one. `script` must be fresh.

1. The narrate job is admitted first, against this job's records and private
   store, exactly as the stage's own render would admit it (`policy.admit` over
   the segment's script): the engine rules, every voice the narrate job names,
   consent with its stored evidence, its scopes, `allowedEngines` and the hosted
   rules. A run rendered against other records, or before a consent narrowed,
   is refused with narrate's own code (`consent_scope`, `consent_missing`,
   `engine_not_allowed`, `hosted_not_allowed` and the rest).
2. The run must be a directory with a `manifest.json`, outside `artifacts/runs/`,
   with no symlink in it (`voice_run_missing`, `voice_run_manifest_missing`,
   `voice_run_in_guitar_runs`, `voice_run_invalid`).
3. It is copied into the stage's `narration/`, and the copy, never the source, is
   checked by `narrate verify`: every digest, `synthetic: true`, mapping
   `narration_v1`, `no_time_stretch: false` and `content_sha256`
   (`voice_run_unverified`).
4. A test-mode batch refuses `voice_run_test_mode` (the flag
   `prerendered_test_mode`, or `engine.synthesis.test_mode`).
5. The chunk gates must hold: every chunk lists its take and a QA status, the
   counts in `qa.chunks` agree, and no chunk failed its measured gate
   (`voice_chunk_gate_failed`).
6. The run must be what the stage would render (`voice_run_mismatch`, naming the
   first field that differs): the narrate job's fields, gates and seed with no
   overrides or rewrite; the segment's script digest and input kind; the engine
   record narrate writes (every field and the knobs the stage's own
   `narrate.toml` gives, such as `fit_speed_max` and `audiocpp_clone`, with
   pinned files compared by digest, never by path, and the batch's own
   `synthesis` record left out); the voice records by speaker, for the voices
   the script uses (a named speaker the script leaves out is not required),
   with clips, transcripts, consents, scopes and tempo; the lexical release; and
   the pronunciation table.

Each refusal is a failure, not a verdict: nothing is recorded, and another run
may be adopted. The stage manifest is the one a local render writes, with
`states.render: adopted` and `measurements.adopted` holding the run id and
content digest, never the source path. `voice_qa` and the stages after it run as
usual, and `voice_qa` scores against the narrate job's gates from the records,
never the gates a run's manifest carries. Adopting the run the node already
holds runs every check on `RUN_DIR` again and is then a no-op; another run
refuses `voice_already_fresh` unless `--replace` is given. `--replace` runs every
check on `RUN_DIR` in place first, and only a run that passes them archives the
node to `history/`, so a run that would be refused never costs the node it would
replace. These two refusals print on stderr as `{"ok": false, "refused", ...}`.
`narrate render --result-line` and `narrate verify --result-line` print the
`{ok, run_id, content_sha256}` line a workflow task reads before it adopts;
verify prints it with `ok: false` and a `reason` even when the manifest is
missing or unreadable.

## Editions

| Edition | Synthetic voice | kitpip avatar | Camera or other PiP | Music bed |
| --- | --- | --- | --- | --- |
| `Internal` (default, NV-2) | yes | yes | yes | yes |
| `OwnContent` | yes | yes | yes | yes |
| `ClientNarrated` (default for a client delivery, NV-6) | yes | yes | refused | only when cleared |
| `ClientVoiceOnly` (per project) | refused | refused | refused | only when cleared |

Every client edition gates the bed. A bed is cleared when its private record
holds a certified licence PDF digest and a clear Content ID result
(`MusicBed.licenceCleared`), and the job's `delivery.voiceOnlyListen` names the
receipt of a voice-only listen pass. A client delivery files as
`ClientNarrated` unless its project picks `ClientVoiceOnly` (NV-6), never as
`Internal` or `OwnContent`, so the bed gate applies to it.
`Edition.clientDefault`, `NarratedVideo.defaults.clientEdition`, `check.py`'s
`CLIENT_DEFAULT_EDITION` and `init --client` hold the same default, and the type
test asserts it.

One rule, `Edition.check`, runs at three points. Each point builds its own
leaves (`syntheticVoice`, `avatar`, `pip`, `bed`, `bedCleared`) from what it
can see, so a check that one point misses is still made at the next:

| Point | Stage | Leaves come from |
| --- | --- | --- |
| `Plan` | `admit` | the job: any segment is a synthetic voice, any avatar block is an avatar, `music` is a bed. A job has no camera field, so `pip` is false (`NarratedVideo.planLeaves`) |
| `Place` | `place` | the placed stems' manifests: a stem whose manifest says `synthetic: true`, any overlay, and any camera PiP in an imported deck's stems |
| `DeliverCheck` | `deliver_check` | the label set re-derived from the composed leaves |

Refusals are `edition_voice_refused`, `edition_pip_refused` and
`edition_bed_refused`, each naming its point. `narrate/dhall/narrated-video-test.dhall`
asserts every code alone at every point. `narrate/dhall/check.py` ports the rule,
and `narrate/tests/test_narrated_video_types.py` pins the port to that table.
L3, L4 and L6 call the same port at their points.

## Types (`narrate/dhall/`)

`package.dhall` adds `Edition`, `MusicBed` and `NarratedVideo`. Real jobs, bed
records and pins stay in the private store. A job holds digests and store ids,
never paths. The executor reads the `dhall-to-json` render.

- **`NarratedVideo`**: `id`, `edition`, `base` (`Still`, `Card`, `Video` or an
  imported `Deck`), `segments` (each a narrate job id, its script digest, an
  anchor and a per-segment avatar switch), an optional `avatar`, an optional
  `music`, `tighten`, `captions`, `labels`, `delivery` and optional `slides`
  (see "Slides"). The avatar block adds `avatarOff` (page ids) and `fadeS`. A
  `Deck` records `tightenEditsSha256`. `tighten.enabled` defaults to false (see
  "Tighten").
- **`MusicBed`**: 2 or 3 layers, each a loop by SHA-256 with bytes, rate,
  channels, source, tempo factor (0.5 to 2.0) and gain. A licence block holds the
  terms reference, the certified PDF digest and the Content ID state. The
  acquisition block's `acquiredBy` has one constructor, `Operator`, so a record
  that says an agent acquired the bed cannot type-check.
- **`Edition`**: the four editions, the three points, the refusal codes and
  `check`.
- **`Consent.persona`** (NV-1): `Optional Text`, `None` by default
  (`Consent.default`). When a segment's voice has a consent persona, the job's
  `labels.persona` must equal it. An avatar needs `labels.persona` too. Both
  refuse `persona_label_missing`. A narrate render does not read the field. The
  value stays in the private record.

`dhall-to-json` drops union tags, so every union payload is a record keyed by
its constructor (`Base.Card { card = ... }` renders `{"card": {...}}`, and
`Anchor.AtSeconds { atSeconds = 1.5 }` renders `{"atSeconds": 1.5}`). Empty
alternatives render as their names (`"Auto"`, `"NotRun"`).

Defaults (`NarratedVideo.defaults`, asserted in the type test):

| Field | Default |
| --- | --- |
| edition | `Internal` |
| clientEdition | `ClientNarrated` (NV-6), the edition of a client delivery |
| base | a 1920x1080 card at 30/1, or a still when given |
| avatar | on where the edition allows one (NV-8): `kitpip`, pin default rig, 512 px render, bottom right, 0.22 of base width, 32 px margin, no `avatarOff` page, 0.35 s fades |
| slides | `None`. The block's defaults: layout `Full`, card 0.42 of the frame wide, 64 px margin, 0.35 s fades, held frame at 0.5 brightness |
| music | `None` unless a bed record id is given. When given: 20 LU under the voice (the deck project's ruling 58), sidechain duck 7 dB, attack 50 ms, release 400 ms, fades 3 s and 5 s, tail 5 s |
| tighten | `{ enabled = False }` (NV-2) |
| labels | no persona, no caption cue, no description line (KP-15) |
| captions | soft, SRT and VTT, not burned |
| delivery | `Web1080p30`, -16 LUFS, -1.5 dBTP, 0.5 LU, `Mono`, no upload, no handoff, no voice-only listen |

**Avatar default (NV-8).** `init` turns the kitpip avatar on for an edition
that allows one (`Internal`, `OwnContent`, `ClientNarrated`) and off for
`ClientVoiceOnly`. An avatar needs `labels.persona`, so `init` without
`--persona P` refuses `persona_label_missing` and names `--no-avatar` as the
other way out. A job turns the avatar off with `avatar = None`, per segment
with `avatar = False`, or for named pages with `avatar.avatarOff`. With the
avatar on, `compose` waits for `avatar` and `avatar_check`: it never composes a
cut without an overlay the job asked for. A pin whose release binary digest is
pending blocks both (`kitpip_pin_pending`).

`examples/narrated-videos.dhall` holds five jobs: the simple Internal card job
with the fixture bed, the same job with a kitpip avatar and a persona label, a
ClientVoiceOnly deck job with no narrate segment, avatar or bed, a
ClientNarrated deck job with a narrate segment, an avatar, tighten enabled and
generated tighten edits, and the avatar job with two generated slide pictures as
a lower-left card, a base page, a 0.4 s hold and the avatar off on the second
slide.
`examples/music-beds.dhall` holds one fixture bed of two generated E-major sine
loops. `check.py` regenerates the loops, the deck placeholders and the two
slide pictures (320x180 RGB PNG in stored deflate blocks, so every zlib writes
the same bytes) and checks every digest, every reference, the edition rule at
Plan, the persona rule, the tighten rule, the slide rules and the bounds below.
Its self-test mutates the narrated-video examples 48 ways and expects each
mutation to be refused.

| Bound | Value | Refusal or check |
| --- | --- | --- |
| avatar width | 0.10 to 0.30 | out of bounds |
| `bedBelowVoiceLu` | 10 to 30 | out of bounds |
| `duckDb` | above 0, at most 12 | out of bounds |
| `driftLu` | above 0, at most 0.5 | hard gate |
| `truePeakDbtp` | at most -1.5 | hard gate |
| bed layers | 2 or 3 distinct loops | `bed_layers_invalid` |
| bed layer `tempoFactor` | 0.5 to 2.0 | out of bounds |
| `acquiredBy` | `Operator` | `bed_acquisition_agent` |
| tighten edits on narrate segments | only with `tighten.enabled` | `tighten_on_synthetic` |
| `avatar.fadeS` | 0 to 2.0 | out of bounds |
| `avatar.avatarOff` | ids of the job's pages | `page_unknown` |
| `slides.cardWidth` | 0.25 to 0.60 | out of bounds |
| `slides.fadeS` | above 0, at most 2.0 | out of bounds |
| `slides.dimTo` | 0 to 1.0 | out of bounds |
| slide pages | unique ids, in order, none overlapping, each slide page at least two fades long | `slides_invalid` |

## Music bed

- An agent never purchases, searches for or downloads a loop, and spends no
  credits. The operator acquires every loop, and the record names the ruling
  that allowed it.
- No tool takes a URL. Loops are found by SHA-256 in the private store.
- No public upload until the record holds the certified licence PDF digest and
  a Content ID result: `delivery_gate.public_upload_allowed` stays false
  until both exist. A client edition also needs the voice-only listen pass.
- One limiter, in `mix`. The sidechain keys on the whole foreground, voice and
  kept clip sound alike.

## Tighten

Tighten trims dead air, spans that are silent and still at once. It is off by
default for synthetic narration (NV-2), because narrate's pause settings set the
pacing. A project may set `tighten.enabled: true` as a per-project override.
The deck project does: its motion-aware tighten took one cut's dead air from
40.3 s to 0.0 s (its rulings 58 to 60).

In phase 1 only an imported `Deck` applies tighten, in the deck's own
assembler. `Deck.tightenEditsSha256` names the edits it applied.
`check.py` refuses tighten edits on narrate segments while tighten is off
(`tighten_on_synthetic`). Edits on operator takes need no override.

A tightened take no longer equals its narrate run's output, so `place` binds it
through the deck's `stems.json`. Per page that file carries the take digest, the
pre-tighten take digest and the tighten edits digest. `place` requires the edits
digest to equal `Deck.tightenEditsSha256` and the pre-tighten digest to equal
the narrate run's `output_sha256["narration.wav"]`. Without that binding it
refuses `voice_stem_unbound`. The labels pass through a tightened take
unchanged.

## Labels

Labels are manifest metadata, and they only grow. A stage with any synthetic
input writes `synthetic: true` and the union of upstream consent ids and voice
ids. `persona` passes through unchanged. A stage that drops or alters one
refuses `label_chain_broken`. In the audio chain the persona joins at `place`,
whose key holds `labels.persona`: `voice` and `voice_qa` carry no persona. The
overlay chain joins it at `avatar`, whose manifest carries it, so `avatar` keys
it too. A persona change reruns `place`, the avatar stages and what follows
them, and no voice.

No visible synthetic or AI-persona label is required in captions,
`description.txt` or on the frame (KP-15). `labels.personaCue` (an opening
caption cue) and `labels.extraNotice` (a `description.txt` line) are optional
and default to none. When a job sets one, the stages keep it. The overlay
carries no visible badge (KP-7).

## Timeline

Every stage manifest that carries narration, an overlay or a bed writes
`no_time_stretch: false` and one of the three mappings in
`docs/spec/TIMELINE_CONTRACT.md` ("Narrated-video mappings"). Guitar tools and
`video-utils verify-run` refuse all three.

## Tools and skills (L7)

Tool numbers are proposals. Root assigns them at admission in
`program/tools.json`. Every tool takes `timeout_seconds` from 1 to 900 and
never a URL, an executable or a shell string.

| # | Tool | Covers |
| --- | --- | --- |
| 62 | `narrated_video_plan` | `admit`, keys, states |
| 63 | `narrated_video_run` | stale stages, resumable after a timeout |
| 64 | `narrated_video_place` | `base`, `place` |
| 65 | `music_bed_build` | `music` |
| 66 | `avatar_overlay` | `avatar`, by the job's `avatar.external` (kitpip, or the vrm draft) |
| 67 | `avatar_verify` | `avatar_check`, by the job's `avatar.external` |
| 68 | `narrated_video_mix` | `mix` |
| 69 | `narrated_video_compose` | `compose`, `handoff` |
| 70 | `narrated_video_verify` | `deliver_check` |

The workflow skill is `narrated-video`, with one skill per stage tool. The
fallback recipes are `just nv-quick` and `just nv-run`. L3 drafts tool 62 in
`program/tool-drafts/narrated_video.json` and writes the first part of the
`narrated-video` skill (plan, status and explain). L4 drafts tools 63, 64, 65
and 68 there, adds `run` to the `narrated-video` skill and writes the
`narrated-video-place`, `music-bed` and `narrated-video-mix` skills. L7 admits them.

The avatar tools are neutral (TIN-7788). `avatar_overlay` and `avatar_verify`
name the `avatar` and `avatar_check` stages whatever external draws the
overlay. `program/dags/narrated-video.json` gives both stages
`dispatch: {by: avatar.external, default: kitpip, externals: [kitpip, vrm]}`,
and `narrate/video/avatar.py` sends each node to its external. The tool names
stay the same when a job moves from kitpip to vrm, so the DAG, a catalog row
that pins the DAG and a guard record that names a stage tool keep them across
the swap. The skills are `avatar-overlay` and `avatar-verify`. The
implementation skills stay: `kitpip-overlay`, `kitpip-verify` and
`vrm-overlay`.

They replace the drafts `kitpip_overlay` (66), `kitpip_verify` (67),
`vrm_overlay` (71) and `vrm_verify` (72). None of those was admitted to
`program/tools.json`, so no alias is kept. A consumer that pinned the DAG
before this change, at `kitpip_overlay` and `kitpip_verify`, keeps its pinned
blob until it re-pins. The stage keys do not change: a key holds the external's
own tool (`kitpip` or the vrm renderer) and its digest, not the MCP tool name.

## Simple path (lane L4)

Lane L4 runs `script`, `voice`, `voice_qa`, `base`, `place`, `music` and `mix`
(`narrate/video/{speech,place,music,mix,run}.py`). `run` plans the job and
runs one runnable node at a time until none is left that the call may run. A
node runs only when every upstream node is fresh, so its key is known before it
starts. Lane L5 adds `avatar` and `avatar_check` (see "Avatar stages (lane
L5)"), and lane L6 adds `compose`, `deliver_check` and `handoff` (see "Compose
and delivery"). No stage waits on a lane, so `waiting_on_lane` is empty.

A refusal is a verdict or a failure. A verdict repeats for the same key, such as
a level gate, an edition refusal or an overlap. The store records it, and the
node stays `refused` until its key changes. A failure says nothing about the
key, such as a source missing from the store, no lexical release, an FFmpeg
crash or an engine that does not answer. Nothing is recorded, so `run` retries
it. `--force S` archives a fresh stage to `history/` and clears its refusal.

| Stage | Reads | Writes | Refuses |
| --- | --- | --- | --- |
| `script` | the segment's script by digest, through its narrate job's input adapter, and the pinned lexical release | `script.json` (spoken-text digest), `lexical.json` (advisory findings, R-N12) | `input_invalid`. Findings never refuse |
| `voice` | the script, the narrate job and its records, or with `--from-run` a run rendered elsewhere | one narrate run in `narration/` (mapping `narration_v1`), labels from its voices | narrate's own refusals, as failures; with `--from-run` the adoption refusals in "Adopting a rendered run" |
| `voice_qa` | the narrate run | `qa.json`: verify receipt and `narrate evaluate` metrics against the job's gates | `voice_unverified`, `voice_qa_failed` (a measured gate failed). `not_measured` never fails. Listening stays `pending_operator` |
| `base` | a card colour, or a still or video by digest | `base.png` for a card or still at the job's size, or `base.mp4` (constant-rate H.264 at the video's own size and rate) with `clips.wav` when `keepBaseAudio`. `base.json` | `base_invalid`. A deck refuses `base_deck_pending` until lane L8 |
| `place` | `base`, every `voice` and `voice_qa` | `voice.wav` and `clips.wav` at 48 kHz on the base clock, `placements.json` | `anchor_needs_deck`, `anchor_invalid`, `placement_overlap`, `base_too_short` and the edition codes at Place |
| `music` | the bed record and its loops by digest | `bed.wav`, one arranged cycle at 48 kHz, and `bed.json` | `bed_acquisition_agent`, `bed_digest_mismatch` |
| `mix` | `place` and `music` | `mix.wav`, `bed-ducked.wav` and `mix.json` | `foreground_not_normalised`, `loudness_drift`, `true_peak_exceeded`, `label_chain_broken` |

Placement. `Auto` starts where the previous segment ends, and the first segment
starts at 0. `AtSeconds` starts at that second. `Page` needs a deck base.
Each narration is resampled to 48 kHz and placed sample-exact. Nothing is
time-stretched. A card or still is extended to the last narration's end plus
`tailS`, rounded up to a whole frame. A video base keeps its own length and
must hold every segment.

The bed. Each loop must have the record's byte count. It becomes 48 kHz mono
with its gain, and with one FFmpeg `atempo` when its tempo factor is not 1.
The cycle is the least common multiple of the layer lengths when that is at
most 120 s, so every loop repeats whole. Otherwise it is the longest layer, and
the record says `cycle_rule: longest`. A sum that would clip is scaled down as a
whole and recorded. The stage measures the cycle's integrated loudness.

Mix levels (NV-2, the deck project's ruling 58):

1. The placed voice is re-measured. A voice further than `driftLu` from
   `targetLufs` refuses `foreground_not_normalised`. Nothing loudness-normalises
   the voice or the mix.
2. The bed is tiled to the program's length and set `bedBelowVoiceLu` (20)
   under the measured voice.
3. A duck envelope lowers the bed by `duckDb` (7). `Sidechain` keys it on the
   foreground, voice and kept clip sound, at -45 dBFS per 10 ms block.
   `EdlEnvelope` keys it on the placed spans. The gain moves `duckDb` per
   `attackMs` going down and per `releaseMs` coming back.
4. Fades run `fadeInS` (3 s) from the start and `fadeOutS` (5 s) to the end.
   With a bed on a card or still, the program runs to the last narration's end
   plus the music `tailS`, rounded up to a whole frame.
5. One limiter, FFmpeg `alimiter` with latency compensation and no auto level,
   sits 0.5 dB under `truePeakDbtp` (-2.0 dBFS for -1.5 dBTP).
6. The mix is measured. Drift over `driftLu` refuses `loudness_drift`. A true
   peak above `truePeakDbtp` refuses `true_peak_exceeded`.

`mix` records the applied duck depth: the median envelope depth over keyed
blocks. A depth outside 6 to 8 dB adds the flag `duck_outside_6_8_db`. The deck
playbook's gate, a duck of at least 3 dB, is recorded as `gates.duck_min_3db`.
Mono is the default. `Stereo` writes the mix on both channels at -3.01 dB each,
so the integrated loudness stays at the target. The program length in `mix`
measurements is the length `compose` (L6) renders.

`just nv-fixture` runs this path on generated inputs: the fake engine's sine
voice, the two E-major loops and a colour card. Measured on 2026-10-27 at this
lane's head: voice -15.8 LUFS, mix -15.8 LUFS (drift 0.2 LU), true peak
-9.1 dBTP and a 7.0 dB duck. These are fixture numbers, not a listening result.

## Compose and delivery (lane L6)

Lane L6 runs `compose`, `deliver_check` and `handoff`
(`narrate/video/{compose,deliver,handoff}.py`).

| Stage | Reads | Writes | Refuses |
| --- | --- | --- | --- |
| `compose` | `base`, `place`, `mix`, every selected `avatar` and `avatar_check`, slide pictures by digest | `video.mp4`, `video.upload.mp4`, `captions.srt`, `captions.vtt`, `description.txt`, `chapters.json`, `compose.json` | `captions_burn_unsupported`, `captions_missing`, `slides_exceed_program`, `overlay_exceeds_base`, `frames_mismatch`, `metadata_present`, `label_chain_broken` |
| `deliver_check` | `compose`, the voice and avatar manifests, the bed record | `deliver_check.json`: gate states and `delivery_gate` | the edition codes at DeliverCheck, `label_chain_broken`. A failed gate is a state |
| `handoff` | `base`, `place`, `mix`, `avatar`, `compose` | `layers/` and `edit.json` | `metadata_present`, `label_chain_broken` |

Profiles. The deck project's own profiles port in phase 2. These are this
lane's, each H.264 High in yuv420p with AAC-LC at 48 kHz:

| Profile | Size | Rate | CRF | Preset | Audio |
| --- | --- | --- | --- | --- | --- |
| `Web1080p30` | 1920x1080 | 30/1 | 18 | fast | 192 kb/s |
| `Talk` | 1920x1080 | the base's | 16 | fast | 256 kb/s |
| `Contingency` | 1280x720 | 30/1 | 23 | veryfast | 128 kb/s |

Compose. The base is scaled to fit the profile and padded black. Layers sit
on it bottom to top: slide layers, then the avatar overlays. Each overlay
(ProRes 4444, straight alpha, decoded by FFmpeg's default ProRes decoder) is
scaled to a square `avatar.width` of the frame wide, placed `marginPx` from its
corner and starts at its segment's start on the base clock. `video.mp4`
carries the captions as a soft `mov_text` track when `captions.soft` is set.
`video.upload.mp4` holds the same picture and sound with no caption track.
`captions.burn` refuses in v1 (the design keeps it off). Captions are each
narrate run's cues (its `narration.srt`, else `narration.vtt`) shifted to the
segment's start. `labels.personaCue`, when set, sits on its own line above the
first cue's text. `description.txt` follows a fixed template: the job id, the
length, the segment count, the chapters (one per page, else one per segment,
titled by id) and `labels.extraNotice` as its last line when set. No visible
synthetic label is added (KP-15).

Metadata. Both MP4s are encoded with `-map_metadata -1`, `-map_chapters -1`
and the bit-exact flags (TIN-7788). `-map_metadata -1` alone keeps an input's
chapter with an empty title, so `-map_chapters -1` is needed too. Then
`narrate/video/strip.py` checks what each file holds:

| Check | Passes when |
| --- | --- |
| container tags | only `major_brand`, `minor_version` and `compatible_brands` |
| stream tags | only a three-letter `language`, the muxer's default `handler_name` (`VideoHandler`, `SoundHandler`, `SubtitleHandler`), `vendor_id` `[0][0][0][0]` and FFmpeg's bit-exact `encoder` name (`Lavc` and a codec, no version) |
| chapters | none |
| bytes | no XMP packet, no EXIF block and no local path: the job store, the private store, the records directory or the home directory |
| text outputs | `compose.json`, `chapters.json`, `description.txt` and the captions hold no local path |

Anything else refuses `metadata_present`. The detail names the file and the
tag key or the kind of finding, never a value or a path. `compose.json`
records the tag keys each MP4 kept under `metadata`. The H.264 stream keeps
x264's settings SEI. It names the encoder settings and no input. compose and
handoff moved to impl 2 with this change, so a cut composed before it plans
stale and reruns. `base` writes `clips.wav` with `-map_metadata -1` and
`-map_chapters -1` as well: without them FFmpeg's WAV muxer keeps a source
clip's title and comment in a `LIST`/`INFO` chunk, and `clips.wav` reaches the
handoff layers. `base` moved to impl 2 for it. `music` and `place` decode the
same way, but they rewrite the samples, so their outputs do not change.

Avatar-off pages. Every page `avatar.avatarOff` lists hides the overlays for
its whole span. They fade out over `avatar.fadeS` (0.35 s) ending at the
page's start, stay hidden through it and fade in over `fadeS` from its end. A
page that starts the program hides the overlay from its first frame. Adjacent
listed pages merge into one span. This is the deck pattern of switching the
avatar off on dense screens. `compose` refuses `page_unknown` for an id that
names none of the job's slide pages, so it never drops one without a word.

### Slides

`slides` names pages on the base clock. A page shows the base (`Base`, a named
span), a slide picture by SHA-256 from the private store (`Slide`), or a `Hold`.
Adjacent slide pages form a run.

- A run fades in over `fadeS` from its start and out over `fadeS` to its end.
  At a page change inside a run the incoming slide starts `fadeS/2` early and
  fades in over `fadeS` above the outgoing one, which stays opaque until
  `fadeS/2` after the change: a crossfade in place.
- `Full` shows each slide over the whole frame, fitted and padded black. Each
  of its fades is eased against what is under it (the base, or the outgoing
  slide): `compose` measures both mean lumas and shapes the alpha so the
  frame's mean luma changes by the same ratio on every frame. A linear ramp
  puts most of a dark-to-light step on its first frames. `compose.json`
  records both lumas and the shortest fade that keeps each step within the
  flash gate (`min_fade_s`).
- `CardLowerLeft` is the deck seat's slide card, built here from its
  description only (design Addendum B, the deck project's ruling 59(b)). No deck
  code or asset was read or copied. Each slide is a card `cardWidth` (0.42) of
  the frame wide at its own aspect ratio, `marginPx` (64) from the left and
  bottom edges, narrower when a tall slide would not fit the frame height less
  two margins. Card fades are linear. Under the card, the base frame at the
  run's end (the next clip's first frame) is held, fading in with the card,
  and a black layer dims it to `dimTo` (0.5) of its brightness, lifting as the
  card fades out. The avatar keeps its own corner.
- A `Hold` page shows no card and holds the base frame at its start at full
  brightness, as the deck's 0.4 s end page does.
- On a card or still base the picture never changes, so nothing is held there.

`slides` is off by default (`None`), and its layout default is `Full`. A
slide page shorter than two fades refuses `slides_invalid` at admit. A page
that ends after the program refuses `slides_exceed_program` at compose.

### Deliver check

| Gate | Passes when |
| --- | --- |
| `profile` | H.264 yuv420p and AAC at 48 kHz, the profile's size and rate, the delivery's channel count, the planned frame count and one caption track with `captions.soft` |
| `loudness` | the delivered sound (after the AAC encode) is within `driftLu` of `targetLufs` and its true peak is at or under `truePeakDbtp` |
| `flash` | at each slide change the largest adjacent-frame mean-luma jump is at most 30%. `not_applicable` without slides |
| `captions` | the files `captions` asks for exist, the persona cue opens the first cue and `extraNotice` ends `description.txt` when set |
| `listening`, `lip_sync` | `pending_operator` here. Lip sync only with an overlay |
| `bed_licence_pdf`, `bed_content_id` | with `upload` and a bed: the record holds the licence PDF digest and a clear Content ID result, else `pending_operator` |
| `visible_text` | records from a guarded intake: `passed` when the guard read a text source for every shown asset and none was opaque. `pending_operator` when one was unread or opaque, or when the marker holds no summary. `not_applicable` without a guarded intake. `deliver_check.json` repeats the summary under `visible_text`. admit lists the open gate as `visible_text_unread`, so `plan` and `status` show `deliver_check` as `pending_operator` |

Flash. A slide change is a run's start and end, each page change inside a
run, and a hold's start and end. Within `fadeS` plus one frame of each change
the stage takes the mean luma Y (8-bit, FFmpeg `signalstats`) of every frame.
A jump is |Y1 - Y0| / max(min(Y0, Y1), 16): relative to the darker frame, with
video black as the floor. The 30% limit is the deck seat's gate. The formula is
this lane's reading of "the largest mean-luma jump between adjacent frames",
not a port of the deck's check.

`delivery_gate.internal_review_allowed` is true when every machine gate passes.
`upload_gates_closed` also needs `upload`, a closed bed gate and, for a client
edition with a bed, `voiceOnlyListen`. `public_upload_allowed` also needs every
operator state closed (`operator_states_open` empty): verified is not accepted.
`deliver_check` never closes listening itself (NV-2: internal until a first
listening receipt), and an overlay without lip-sync acceptance stays private,
so it never reports a public upload as allowed. Every field is a gate state:
uploading, sending and Content ID stay operator actions.

### Handoff

`handoff` runs when `delivery.handoff` is set. `layers/` holds `base.mp4` (the
base at the profile, no overlay, slide, caption or sound),
`avatar-<segment>.mov` (each overlay as its external, kitpip or vrm, wrote it),
`avatar-<segment>.manifest.json` (that overlay's manifest),
`slide-<page>.png` (each slide picture with its metadata stripped), `voice.wav`, `clips.wav`
(when the base kept its sound), `bed-ducked.wav` (with a bed, before the
limiter) and the captions. `edit.json` holds the placements, the overlay boxes
and starts (each with its layer, manifest file and digest, renderer kind and
frames identity), the slide runs, the avatar-off spans, the mix gains and the
stage key of every input. FCPXML and OTIO export is phase 2. Until an editor
imports one, it stays unverified in an application.

A slide layer keeps a PNG's critical chunks and its colour chunks (`tRNS`,
`gAMA`, `cHRM`, `sRGB`, `sBIT`, `pHYs`, `bKGD`), so its pixels and their bytes
stay the same. It loses every text chunk (`tEXt`, `zTXt`, `iTXt`, which carry
XMP), `eXIf`, `iCCP`, `tIME` and any unknown chunk. A picture that is not a PNG
is decoded to one first. `edit.json` lists each slide's source digest
(`sha256`), its layer digest (`layer_sha256`) and the chunk types dropped
(`stripped`). FFmpeg applies no ICC profile when it composes, so a layer
without `iCCP` shows what the cut shows. The overlays are copied as their
external wrote them, because their manifests bind the bytes.

Then every layer but `base.mp4`, which compose's MP4 check reads, is read as
it is (`strip.check_layer`). Its bytes must hold no XMP packet, no EXIF block
and no local path, and a WAV must hold only `fmt `, `data` and `fact` chunks.
A MOV or MP4 layer, such as an avatar overlay, is also probed with `ffprobe`. It
must hold no chapter and no tag outside compose's allowlist, the mov muxer's
vendor id `FFMP` and an FFmpeg library version, so a title, artist, comment or
handler name the external wrote refuses. Anything else refuses
`metadata_present`, naming the file and the chunk, the tag key or the kind of
finding. The check never rewrites a layer, so the overlays and their
manifests keep the bytes their digests bind. `edit.json` lists the layers
checked under `metadata_checked`.

## Operator acceptance

Linear TIN-7788, design P1. `deliver_check` leaves `listening` and `lip_sync` at
`pending_operator`. `accept` is the one write path that closes them. It records
the operator's decision against one gate of the current `deliver_check` render.
It takes a Softproxy decision id and nothing else: `sp:dec:` and a 26-character
upper-case Crockford base32 ULID, the form Softproxy writes for a decision.
`--video-sha256` is required and names the cut the decision saw. It must be the
current composed video, so a decision about one render never closes a later one.

| Input | Result |
| --- | --- |
| `listening`, or `lip_sync` with an overlay, that `deliver_check` reports `pending_operator`, a well-formed id and the current video's sha256 | one row appended to `acceptance.json`, exit 0 |
| the same gate, id and render again | no new row, `recorded: false`, exit 0 |
| no `--decision`, or an empty one | `decision_missing` |
| free text such as `GO`, `yes` or `lgtm`, a GO line or another record's id such as `sp:prp:` | `decision_free_text` |
| `sp:dec:` with a wrong length, lower case, a letter outside Crockford base32, a time past 48 bits or a trailing character | `decision_invalid` |
| `profile`, `loudness`, `flash` or `captions` | `gate_automated`. A decision never closes a machine gate |
| `bed_licence_pdf` or `bed_content_id` | `gate_record_bound`. They close through the private `MusicBed` record |
| `visible_text` | `gate_intake_bound`. It closes when a re-intake's private-terms guard reads the text of every shown asset |
| `vrm_badge_decision` | `vrm_badge_undecided` until a ruling settles the badge |
| any other gate name | `gate_unknown` |
| `lip_sync` without an overlay | `gate_not_applicable` |
| a gate of this render that holds another decision | `gate_already_accepted` |
| an id that already accepted another cut of this job, or any cut of another job under the store root | `decision_bound_elsewhere` |
| no `--video-sha256`, or an empty one | `video_sha256_missing` |
| `--video-sha256` that is not 64 lower-case hex characters | `video_sha256_invalid` |
| `--video-sha256` that is not the current composed video | `video_mismatch` |
| an `acceptance.json` with a row `accept` would refuse, such as a machine gate, `vrm_badge_decision` or a malformed digest, one that names two cuts for one render or one that is not a regular file | `store_invalid` |
| no `deliver_check` run, one that fails re-hashing, or a `compose` newer than it | `deliver_check_missing`, `deliver_check_corrupt` or `deliver_check_stale` |
| a `deliver_check` render whose job digest is not that of `job.json` on disk | `deliver_check_stale` |
| a `graph.json` that is not an `nv_graph` record with nodes and operator gates, or not a regular file | `store_invalid`, and `stage_symlink` for a symlink. Nothing is recorded |

Each row holds the gate, the decision id, `resolution`, `accepted_utc`, the job
digest, the `deliver_check` stage key and content digest, and the composed
video's sha256. `resolution` is `form_only`: `accept` checked the id's form,
not that Softproxy holds it. One acceptance binds one render. One decision
binds one cut, the composed video the operator judged. It may close both gates
of that cut, so one GO covers listening and lip sync for that render version.
A new cut opens both gates again until it has its own decision. The earlier
decision refuses `decision_bound_elsewhere` there. A rerun of `deliver_check`
alone, such as a licence PDF digest or a Content ID result recorded in the bed
record, keeps the video. It also opens both gates of its new render. `accept`
then records the same decision against that render, with no second operator
decision. A decision binds one job: `accept` reads every job's
`acceptance.json` under the store root, under one lock at that root, before it
records one.

`acceptance.json` sits in the job directory beside `job.json` and is
append-only. `job.json` stays the `NarratedVideo` record as rendered, so no
stage key and no private-terms binding moves, and `verify` still re-hashes every
stage. `plan` and `run` list the acceptances that bind a fresh `deliver_check`
and the current composed video under `accepted`, with their `resolution`, and
drop the gates they close from `pending_operator`. A row for another video
closes nothing. `status` trusts no operator view in `graph.json`. It
recomputes `accepted` and `pending_operator` and refuses `graph_stale` when the
recorded ones differ. The job digest must be that of `job.json`, and the
nodes must be the ones `job.json` gives, `deliver_check` among them. `admit`
must list every gate `job.json` opens and every gate the current
`deliver_check` render reports from the records. `accepted` must be the rows
that bind that render and the current video. `pending_operator` must be
`admit`'s list less the gates they close. `deliver_check` must show
`pending_operator` while `admit` holds a gate at it. `graph.json` carries no
signature, so one hand edit still passes `status`: it rewrites the
`deliver_check` node's key and state and drops a records gate from both lists.
`plan` recomputes every state from the store and the records.
`deliver_check` keys on the job's digest, and `accept` refuses a render made
for another `job.json`. A row therefore never pairs a new job with an old
render. `accept` checks `graph.json` before it writes `acceptance.json`, so a
malformed graph refuses with nothing recorded.
Reading `acceptance.json` re-checks every row, so a hand-written row for a
machine gate or the VRM badge refuses `store_invalid` and closes nothing.
`accept` updates a recorded `graph.json` whose `deliver_check` row is that
render, and recomputes its `pending_operator` from `admit`'s list. `admit` and the `deliver_check` report stay
as they were, so `public_upload_allowed` stays false. An acceptance drops only
`listening_acceptance` and `lip_sync_acceptance`. A `visible_text_unread` gate
stays in `pending_operator`, so a partial `visible_text` keeps `deliver_check`
at `pending_operator` after both acceptances. A re-intake that reads every
shown asset reruns `deliver_check`. Once the same decision is recorded for both
gates of that render, `deliver_check` plans `fresh` (tested). Upload, sending and
Content ID stay operator actions.

`accept` checks the id's form, not its meaning. It cannot tell whether
Softproxy holds an Operator accept under that id. The caller resolves that
first: in the Cade demo DAG, the decision poll reads the decision and calls
`accept` only for a GO. The id is the receipt a reader resolves.

## Guard subject and cut

Linear TIN-7788, SPR-220. The Cade worker runs the narrated-video DAG as Hatchet
tasks (xoxd-ai/cade-infra `config/hatchet-workflows.json`, row
`client-video-narrated-render`). Its `bs21_privacy_guard` task checks every
text in the job's subject against the private name and term lists before any
render task runs. Every render task checks the same texts again before it acts
(xoxd-ai/cade `src/bs21-guard.ts`). Hatchet carries ids only, so the worker
reads the texts with `subject` inside its own process. `narrate/video/subject.py`
lists them in this order:

| Field | Text | Where it appears |
| --- | --- | --- |
| `narration` | each segment's written text, read as the `script` stage reads it | the captions |
| `spoken` | the same segment's text after the narrate job's pronunciation table and its pinned upstream table, in `render.py`'s chunks, one chunk per line | the voice |
| `title` | the job id, each segment id and each slide page id | `description.txt` and `chapters.json` |
| `caption` | `labels.personaCue`, when set | above the first cue |
| `description` | `labels.extraNotice`, when set | the last line of `description.txt` |
| `label` | `labels.persona`, when set | every stage manifest from `place` on |

An asset's own text, such as a still, a slide, a plot, a clip or a deck, is not
in the subject, so the BS-21 name list never reads it. Only the intake's
private-terms guard reads it, against the `nv` denylist (`private_terms.py`,
`visible_text.py`). A name must be on that denylist for shown text to refuse it.
The `visible_text` gate stays open while a guarded intake left an asset unread.
With no guarded intake that gate reads `not_applicable`. J168 removes `subject`'s
`shown_text_unread` refusal for go-live, so a job with no guarded intake's marker
can show text no check reads. The November 30, 2026 audit revisits that.

`subject` refuses `subject_too_large` above 4096
texts or 200000 UTF-16 code units in one text, the limits the Cade guard holds.
The guard measures with JavaScript's `String.length`, so `subject` counts the
same units: an emoji is 1 Python character and 2 units. A
segment whose narrate job is not in the records refuses `records_invalid`, and
a script missing from the store refuses `source_missing`. A script that does
not load refuses `input_invalid`, and that refusal quotes none of the script.
A pronunciation table with no record refuses `pronunciation_unknown`, a text the
tables refuse to say refuses `pronunciation_refused`, and a lexical release that
does not match the pin refuses `lexical_missing` or `lexical_digest_mismatch`.
It writes only a
scratch copy inside the job directory and removes it. The caller never logs its
output.

`cut` prints the current `deliver_check` render as `accept` binds it: the
composed video's sha256, the `deliver_check` stage key and content digest, the
machine gate states, `internal_review_allowed`, the gates still
`pending_operator` and the gates an acceptance of that same render closed. An
acceptance of an earlier cut closes nothing. It holds digests and gate names
only. The Cade worker's `outbox_post` task names this cut when it asks Jess for
her decision, and `accept` later checks the same sha256. It refuses as `accept`
does: `deliver_check_missing`, `deliver_check_corrupt`, `deliver_check_stale`,
`deliver_check_invalid`, `store_invalid` or `stage_symlink`.

`deliver_check` records a failed machine gate as a state and finishes, with
`delivery_gate.internal_review_allowed` false. `cut` refuses
`machine_gates_failed` for that cut, and the refusal names the failed gates. A
cut that failed `flash`, a photosensitivity risk, or `loudness`, `profile` or
`captions` therefore never reaches Jess as a request for a decision. A
`deliver_check` with no machine gate state or no `delivery_gate` refuses
`deliver_check_invalid`.

## Demo bundle intake

Linear TIN-7735. A demo bundle is a directory that a producing lane writes in its own private repository, as
`docs/demo/<slug>/`. `python -m narrate video intake` turns it into the records this spec already defines: one
`NarratedVideo` job and one narrate `Job` per beat. It adds no schema (SPR-84): `job.check_shape` and admit accept
its output unchanged. No real bundle, asset, receipt or render enters this repository. The tests use the synthetic
bundle `demo-fixture` (`narrate/video/fixture.py`).

### Format

The parser (`narrate/video/bundle.py`) is strict. JSON files hold at most 4 MiB, `script.md` at most 1 MiB. A key
that repeats, an unknown field or a missing field refuses `bundle_invalid`. Ids are 1 to 64 of `a-z`, `0-9`, `.`,
`_` and `-`, starting with a letter or digit.

`manifest.json` is `{"assets": [...]}`, with an optional `slug` equal to the directory's name and an optional
`privacy` block (see "Private terms"). Each asset has these fields:

| Field | Rule |
| --- | --- |
| `id` | an id, unique in the manifest |
| `path` | a relative POSIX path inside the bundle: no leading `/`, no `.`, `..` or empty part, no backslash, no symlink on the way. It ends in `.png`, `.mp4` or `.gif` to match `kind` |
| `sha256` | 64 lowercase hex digits. The file is hashed, and a different digest refuses `asset_digest_mismatch` |
| `kind` | `png`, `mp4` or `gif`. The bytes must match: the PNG signature, an MP4 `ftyp` box, or `GIF87a`/`GIF89a` |
| `receipt` | non-empty text naming the asset's source receipt (`asset_unreceipted` when empty) |
| `size` | optional `{w, h}`. A PNG's header must hold the same size |
| `fps` | optional `{num, den}`, recorded and never used |
| `text` | optional `{path, sha256}` on a `png` or `mp4` asset: the text source of what it shows on screen (see "Private terms"). `path` follows the asset path rules and ends in `.svg` or `.json`. The file is hashed, and a different digest refuses `asset_digest_mismatch`. It is read and bound, never copied to the store |

`script.md` is a sequence of beats. Before the first beat it allows one `# title` line, notes (lines starting with
`>`) and blank lines. A beat is:

````text
## intro

- target_s: 8
- asset_id: slide-a
- claims: build-ms, files

```voiced
The exact words to speak, with every number spelled as read.

A blank line starts a paragraph.
```
````

The heading is `## ` and the beat id, unique in the script. The three `- key: value` lines are each required once,
in any order. `target_s` is seconds above 0 and at most 3600, with up to three decimals. `asset_id` names a manifest
asset. `claims` is a comma-separated list of distinct claim ids, or empty. One ```` ```voiced ```` block holds the
words to speak, closed by a ```` ``` ```` line. Notes and blank lines may sit anywhere in a beat. Any other line
refuses `script_invalid` with its line number. A beat without its three lines refuses `beat_invalid`, and a beat with
no voiced block or an empty one refuses `beat_voiced_missing`.

`claims.json` is a list of claims, each with exactly three fields:

```json
{"id": "build-ms",
 "value": {"spoken": "seventeen point eight seven seven milliseconds", "number": 17.877, "unit": "ms"},
 "receipt": "the receipt that measured it"}
```

`number` is a JSON number, compared as an exact decimal. `unit` is `""` for a bare count, `ordinal`, one of the
gate's canonical units (`percent`, `pp`, `s`, `ms`, `us`, `ns`, `min`, `h`, `day`, `week`, `month`, `year`, `Hz`,
`kHz`, `MHz`, `GHz`, `dB`, `dBA`, `dBFS`, `LUFS`, `LU`, `dBTP`, `V`, `mV`, `A`, `mA`, `W`, `kW`, `mW`, `ohm`,
`N`, `kN`, `Nm`, `Pa`, `kPa`, `MPa`, `GPa`, `K`, `m`, `cm`, `mm`, `um`, `km`, `in`, `ft`, `g`, `kg`, `mg`, `degC`,
`degF`, `deg`, `B`, `KB`, `MB`, `GB`, `TB`, `bit`, `fps`, `px`, `rpm`, `ppm`, `x`, `USD`) or two of them joined by
`/` (`m/s`, `N/m`). A claim names the canonical unit: `Nm`, not `N·m`, and `um`, not `µm`. `spoken` must read, through the gate's own extractor, as exactly
that one number and unit, else `claim_invalid`. `receipt` is text or `null`. An empty or `null` receipt is legal
in the file, and the claims gate refuses every number that relies on it.

### Refusals

| Code | When |
| --- | --- |
| `bundle_invalid` | a file is missing, malformed, too large or has a missing or unknown field; an asset path leaves the bundle |
| `asset_missing` | an asset file is absent, not a regular file, or reached through a symlink |
| `asset_digest_mismatch` | an asset file does not hash to its manifest `sha256`, when it is read or when its store copy is hashed |
| `asset_kind_mismatch` | an asset's extension, bytes or PNG size differ from its manifest entry |
| `asset_unreceipted` | an asset's receipt is empty |
| `asset_text_invalid` | an asset's text source is malformed: an SVG that is not UTF-8 (another byte-order mark, a NUL or a declared encoding other than UTF-8), is not well-formed, holds a document type or entity declaration anywhere or has no `svg` root, or a JSON file that is not `nv_asset_text` schema 1 with at most 10000 strings of at most 4096 characters, or a file over 4 MiB. A `text` field on a GIF, or with a missing or unknown field, refuses `bundle_invalid`, and a path that does not end in `.svg` or `.json` refuses `asset_kind_mismatch` |
| `asset_unknown` | a beat's `asset_id` is not in the manifest |
| `asset_needs_conversion` | a beat cites a GIF. No stage reads GIF: a slide is a still picture and the base is one video. The producer converts it to a PNG or an MP4 in the bundle, with its own digest and receipt. An unused GIF is listed in `unused_assets` and never refused |
| `asset_video_multiple` | beats cite two different MP4s: one MP4 becomes the base, and no stage joins clips |
| `script_invalid`, `beat_invalid`, `beat_voiced_missing` | the script rules above |
| `voiced_not_verbatim` | narrate's Markdown adapter would not speak the voiced text as written: inline markup, a `[bracketed]` line, a heading or a `Sources:` line |
| `claim_invalid`, `claim_unknown` | a claim breaks its rules; a beat cites a claim id that `claims.json` lacks |
| `denylist_missing`, `denylist_misplaced`, `denylist_digest_mismatch`, `denylist_invalid`, `denylist_pin_invalid`, `privacy_undeclared`, `private_term` | the private-terms guard (see "Private terms"): the declared denylist is not given, lies inside the bundle or a git work tree, is not bound or malformed, the operator's pin is malformed or names a private lane for an undeclared bundle, or a text says one of its terms |
| `number_unclaimed`, `claim_unreceipted`, `claim_ambiguous`, `number_ambiguous` | the claims gate, per segment (below) |
| `narrate_job_missing`, `records_invalid`, `voice_unknown`, `engine_unknown`, `engine_not_allowed`, `consent_scope`, `confidential_engine_refused` | the template narrate job, voice or engine cannot voice a confidential job |
| `pronunciation_unknown`, `pronunciation_refused`, `pronunciation_adds_number`, `lexical_missing`, `lexical_digest_mismatch` | the template's pronunciation table has no record; narrate's normaliser refuses a beat; a table makes narrate say a number word or digit group that the voiced text lacks; the template pins the narration register and its xoxd-lexical release (`NARRATE_LEXICAL_DIR`) is absent or does not match its pin |
| `out_exists`, `store_conflict`, `narrate_job_exists` | the output directory is not new or empty (or fills while the intake runs); the store holds a different file, a symlink or a directory under a digest name, or `--store` is `--out` itself; the records hold a different narrate job with a new job's id |
| admit's codes | the converted job fails admit at Plan, such as `slides_invalid` for a PNG beat shorter than two fades |

### Conversion

| Bundle | Becomes |
| --- | --- |
| a beat | a segment with the beat's id, anchored `AtSeconds` at the beat's start. Beats run back to back from 0, each `target_s` long |
| its voiced text | a narrate Markdown input: front matter `slide: <beat id>` and `target_seconds: <target_s>`, a blank line and the voiced text. Its SHA-256 is the narrate job's `inputSha256` and the segment's `scriptSha256` |
| its narrate job | `<job>-<beat>`: a copy of the template narrate job (`--narrate-template`: lexical pin, pronunciation table, scope, gates, post settings) with `input` `Markdown`, `confidential` true, `allowHosted` false, no speakers table, and `voice` and `engine` from `--voice` and `--engine` |
| a PNG beat | a `Slide` page by SHA-256 over the beat's span, layout `Full` |
| an MP4 beat | a `Base` page over the beat's span. The MP4 is the base video (`keepBaseAudio` false) |
| no MP4 | the default card (`#101820`, 1920x1080 at 30/1), held `--tail-s` (default 1 s) after the last narration |
| the job | edition `Internal`, no music bed, tighten off, the default captions and delivery. The kitpip avatar is on with `--persona P` and off with `--no-avatar`, and one of them is required (NV-8) |

The base video runs from program second 0. A PNG beat covers it with a full-frame slide, and an MP4 beat shows the
video's own seconds at that span. A bundle that wants a clip from its first frame cites it in its first beat, or
cuts the clip so that its seconds line up with the beat. narrate fits each narration to its beat's `target_s` within
the template's `fitMaxStretch`. `place` still refuses `placement_overlap` or `base_too_short` when a narration cannot
fit.

The intake writes nothing until every check passes, including admit on the converted job against the merged
records and the pronunciation check below. Then it checks every store target (absent, or a regular file with the
same digest; anything else refuses `store_conflict`) before it creates anything. It copies each cited asset into a
temporary file in the store, opening every path component without following a symlink, and hashes the copy: a copy
that does not match the manifest `sha256` refuses `asset_digest_mismatch`. It builds the output tree in a temporary
sibling of `--out`, links each store file into place without replacing one, and renames the tree to `--out`. A
refusal at any step removes the temporary files, the store files this run added and the directories it created, so
`--out` stays absent or empty and a retry can use it. The result in a new or empty `--out` is:

```text
OUT/
  narrated-video.json   the NarratedVideo record, as `init --from` reads it
  records/              the input record renders, with one narrate job per beat added to jobs.json
  intake.json           the run manifest (kind nv_bundle_intake)
STORE/                  --store, default OUT/store: each beat's Markdown as <sha256>.md and each cited asset as
                        <sha256>.png or <sha256>.mp4
```

`intake.json` names the bundle by slug and by the digests of its three files, never by path. `inputs.records_sha256`
is the tree digest of the records directory it read (docs/spec/RENDER_STAGE.md), or `null` when that tree holds a
symlink or a file that is not regular. It holds the job id and
digest, the narrate template, voice and engine, and one row per segment. Each row holds the narrate job, script
digest, span, asset (id, kind, digest, receipt, text source), shown layer and the claims result. It also holds
`visible_text` (the shown assets read, unread and opaque to the guard), `unused_assets`,
the store digests written, the digest of every output, admit's verdict and pending operator gates, the template's
pronunciation table id and pinned upstream release (or `null`), and the states `source_checks: passed`,
`claims: passed`, `pronunciation_numbers: passed`, `private_terms`, `visible_text`, `producer_review:
pending_operator`, `render: not_run` and `listening: pending_operator`. Then
`init --job ID --from OUT/narrated-video.json --records OUT/records` and `run` proceed as for any job. The beats'
narrate jobs are confidential, so the engine must be one that `Engine.mayRunConfidential` admits.

### Claims gate

`narrate/video/claims.py` extracts every number a voiced text speaks. It reads digits (`17.877`, `1,024`, `42%`,
`3rd`, `12ms`, `3.5 million`) and spelled-out English cardinals, decimals and ordinals ("one hundred and five",
"seventeen point eight seven seven", "a hundred", "twenty-one", "twenty first", "minus five"). After a number it reads
the unit words ("milliseconds", "percent", "per cent", "%", "frames per second", "metres per second") as one
canonical unit. A number without a unit word has the unit `""`. Each number must match exactly one claim that the
beat cites, with the same number and unit and a non-empty receipt.

The engineering units read like this (TIN-7735). Each word form has a singular and a plural.

| Canonical unit | Symbols after a number | Spoken words |
| --- | --- | --- |
| `Pa`, `kPa`, `MPa`, `GPa` | `Pa`, `kPa`, `MPa`, `GPa` | pascals, kilopascals, megapascals, gigapascals |
| `N`, `kN` | `N`, `kN` | newtons, kilonewtons |
| `Nm` | `N·m`, `N⋅m`, `N.m`, `N m`, `N-m`, `Nm` | newton metres, newton meters, newton-metres |
| `dBA` | `dBA` | decibels A-weighted, A-weighted decibels |
| `um` | `um`, `µm`, `μm` | micrometres, micrometers, microns |
| `us` | `us`, `µs`, `μs` | microseconds |
| `K` | none | kelvin, kelvins |
| `rpm` | `rpm`, `RPM` | revolutions per minute |
| `ppm` | `ppm`, `PPM` | parts per million |

The gate also reads `dB`, `mm`, `ms`, `kHz`, `MHz`, `A`, `mA`, `V`, `mV`, `W`, `mW`, `°C`, `m/s`, `g`, `kg` and `%`.
"K" is not a symbol, because "17 K" and "4K" may mean thousands: kelvin is read only as the word. A symbol with a
mark the word pattern splits on ("°C", "µs", "Ω", "N·m") reads the same attached ("20°C") or as the next word
("20 °C"). A listed symbol over a unit reads as both ("5 µm/s" is `um/s`, "5 °C/min" is `degC/min`, "40 N·m/s" is
`Nm/s`), and "per" takes a symbol after it ("5 N per m" is `N/m`). Units never convert: "17 MPa" does not match a
claim of 17000 `kPa`, and "45 dBA" does not match a `dB` claim.

| Per-number result | Code |
| --- | --- |
| no cited claim has that number and unit | `number_unclaimed` |
| only cited claims without a receipt match | `claim_unreceipted` |
| two cited claims with receipts match | `claim_ambiguous` |
| the reading is not one value | `number_ambiguous` |

The gate fails closed. These readings are ambiguous and never match:

- adjacent number words that do not form one number ("nineteen eighty four", "one two three");
- fractions and vague quantities ("one third", "two thirds", "a half", "a third", "an eighth", "quarter", "dozen",
  "couple", "twice"), plural scale words ("hundreds", "thousands", "millions", "tens of thousands"), "-fold" words
  ("tenfold", "ten-fold", "10 fold"), "nil", "nought", "naught" and decade words ("teens", "the nineties"):
  reason `fraction_or_vague_quantity`;
- a scale word with no count before it ("hundred files", "thousand users"): `scale_without_count`;
- "point" and digit words with no whole part ("point five");
- "second" where it may be the ordinal or the unit ("twenty second", "one hundred second");
- a Roman numeral of two or more capital I, V and X ("World War II", "Phase IV"): `roman_numeral`;
- a dash other than a hyphen inside one word chunk between number words (an en or em dash, or U+2212, between
  "five" and "hundred"): `dash_between_numbers`;
- digit tokens that are not one plain number ("1.2.3", "10:30", "1/2", "2026-10-29", "MP4", "1,23", "4K", "5M",
  any chunk with a non-ASCII numeral such as "½", "²" or an Arabic-Indic digit): `digits_not_one_number`;
- a whole ten with an attached "s" ("the 90s", "1990s"), a decade or seconds: `decade_or_seconds`. "12s" and
  "30 s" are seconds;
- a number followed by a word that may scale it or that names a unit the gate does not read:
  `unknown_scale_or_unit`. These are a single letter other than "a" and "I" ("17 K", "3 B", "17 M"), a scale
  abbreviation (`k`, `bn`, `mn`, `mln`, `mio`, `tn`, `mil`, `thou`, `grand`, `lakh`, `crore` and their variants), a
  lower-case unit of up to five letters with no vowel ("kph", "kbps", "Mb" in lower case), a binary prefix
  ("GiB", "MiB"), a mixed-case unit ("Mbps", "kWh"), a unit symbol in another case ("mpa", "Kpa", "dba", "kn",
  "Min", "MPA", "PA", "KG", "MS") and the capital units `MW`, `MV`, `MA`, `KM`, `PB`, `EB`, `KPH`, `MPH`, `BPM`,
  `KBPS` and `MBPS`. The all-capital symbols `KB`, `MB`, `GB`, `TB`, `LUFS`, `LU`, `RPM` and `PPM` read as units;
- a unit the gate does not read: `psi`, `bar`, `mbar`, `atm`, `torr`, `hPa`, `mmHg`, `inHg`, `ppb`, `ppt` and
  their spoken forms, and an SI prefix said as its own word ("5 mega pascals", "5 milli seconds", "5 mega"):
  `unknown_scale_or_unit`;
- a chunk with a unit mark (µ, μ, °, Ω, ·, ⋅, ‰, ℃) that is not a listed symbol ("5 µA", "5 mΩ", "5 °K",
  "5 Ω·m", "5 µm·s"): `unknown_scale_or_unit`;
- a unit that runs on into another one, joined in its chunk ("5 kN-m", "5 kN·m", "5 N·mm", "5 N-type", "5 dB(A)")
  or followed by another unit ("5 Pa s", "5 kN m", "5 kilonewton metres", "5 degrees kelvin"), and "per square" or
  "per cubic" after a unit ("5 newtons per square metre"): `unknown_scale_or_unit`;
- a unit joined by "/" to something that is not a unit ("5 m/furlong"): `unit_not_read`. "5 m/s" and
  "five km/h" read as `m/s` and `km/h`.

A hyphen joins words: U+002D, U+2010, U+2011 (the non-breaking hyphen) and the soft hyphen, so "five‑hundred"
written with U+2011 reads as 500, never as 5. A possessive or contraction of a number word ("five's", "seven’s")
reads as the number. Unit symbols match in their exact case after digits or spelled numbers ("twelve ms"): "m" is
metres and "M" is not a unit, "mW" is milliwatts and "MW" is ambiguous, "MB" is megabytes and "Mb" is ambiguous,
"MPa" is megapascals and "mpa" and "MPA" are ambiguous. Other words after a number, acronyms such as "MCP" and
"PRs" among them, leave it a bare count. An acronym that is a unit symbol in capitals ("GPA", "PA") is refused, and
the script rewords it.

"one" is always the number 1, and "first" and "second" alone are the ordinals 1 and 2: a script that uses them as
ordinary words cites a claim or rewords. "once", "single", "both", "none", and "a" before anything but a scale word
or an ordinal are not numbers. A cited claim that no number uses is listed in `unused_claims` and never refused.

The gate reads the voiced text as written. narrate then says it through the template's pronunciation table, and,
when the template pins the narration register, the xoxd-lexical upstream table first. narrate's own guard refuses an
entry that changes digits or a recognised numeric literal, but not one that turns a word into number words. So
`intake`, after admit, says each beat's paragraphs through the same `Normaliser` and refuses
`pronunciation_adds_number` when the spoken form holds a number word, vague quantity, Roman numeral or digit group
that the written form lacks. Units are not compared: a table may spell out "LUFS". With the narration register
pinned, the intake reads the release from `NARRATE_LEXICAL_DIR` and refuses `lexical_missing` without it.
`claims` alone reads no records and does not run this check.

`claims` runs the private-terms guard and then the gate on `script.md` and `claims.json` and prints
`{ok, bundle, segments, private_terms}`, one row per
segment with its status, codes, mentions (text, number, unit, kind, status, claim and receipt, or code and reason)
and unused claims. A refused gate exits 1 with the first segment's code on stderr. `intake` runs the same gate
first. A refusal prints the per-segment report and writes nothing. A pass copies the report into `intake.json`.

### Private terms

Linear TIN-7735, SPR-220. A `never_name` bundle must not name a party. An `ip_private` bundle marks work whose numbers
and geometry were private. J168 (TIN-7125 `9738d494`) and SPR-339 (`1786d297`) remove the `ip_private` and BS-21
refusals for go-live, and the November 30, 2026 audit revisits them, so `ip_private` is recorded and refuses nothing. A
bundle declares this in `manifest.json`:

```json
"privacy": {"ip_private": true, "never_name": false, "denylist_sha256": "<64 lowercase hex digits>"}
```

`ip_private` and `never_name` are required booleans, and `denylist_sha256` binds the denylist by digest. Any other
field, or a value of the wrong type, refuses `bundle_invalid`. When `never_name` is true, `claims` and `intake` need
the denylist through `--denylist FILE` or `NARRATED_VIDEO_DENYLIST`. The file lives outside the bundle and outside
every git work tree, and only its digest appears in a record.

The bundle's own manifest cannot be the only binding, because whoever edits the bundle can drop the block or bind
another list. The operator of a lane marked private sets `NARRATED_VIDEO_DENYLIST` and pins the list's digest with
`--denylist-sha256 HEX` or `NARRATED_VIDEO_DENYLIST_SHA256`. A pin marks the lane private: a bundle that declares
neither flag refuses `privacy_undeclared`, and the file must hash to the pin whatever the manifest binds. The guard
(`narrate/video/private_terms.py`) fails closed:

| Code | When |
| --- | --- |
| `denylist_missing` | a flag is true or a pin is set and no file is given, the file is absent, not a regular file or a symlink, or the manifest names no `denylist_sha256` and no pin is set |
| `denylist_misplaced` | the file lies inside the bundle or inside a git work tree |
| `denylist_digest_mismatch` | the file's bytes do not hash to the pin, or with no pin to `denylist_sha256`, or the manifest binds another digest than the pin |
| `denylist_pin_invalid` | the pin is not 64 lowercase hex digits |
| `privacy_undeclared` | a pin is set and the manifest declares neither `ip_private` nor `never_name` |
| `denylist_invalid` | the file is over 1 MiB, not UTF-8 JSON, repeats a key, is not `{kind: "nv_denylist", schema_version: 1, salt, entries}` with 1 to 10000 entries, holds a malformed entry, or lacks the class a flag needs |
| `private_term` | a name entry matches a text the job speaks, shows or records |
| `private_terms_stale` | at every records load, a narrate job or the pronunciation table it names differs from what a guarded intake recorded, or a private lane's records hold no marker; at `init`, `plan`, `run` and `explain`, the NarratedVideo record is not the one the guarded intake wrote |

`salt` is 32 to 128 random lowercase hex digits with at least 8 distinct digits. Records carry the file's digest,
and the salt keeps that digest from confirming a guessed short list, the reason Cade's claims gate keeps no digest
of its name list.

Each entry is `{id, class, literal}`, `{id, class, regex}` or `{id, class: "number", number, unit}`. `class` is
`number`, `geometry` or `name`. `never_name` needs at least one name entry. Number and geometry entries parse and do
not match (J168). The reading rules below stay for the audit, shared with xoxd-ai/cade. A literal holds 2 to 256 letters or digits. A name entry is never a number entry. An entry id
must not match any entry, number entries included. Reports name entries by position and never carry an id, so an
id that spells a term in a form the entries do not read ("angle-12-5") still never reaches a log. A number entry's
`unit` is `null` or a unit the claims gate reads. It is kept for the record and no longer narrows the match.

A regex holds at most 512 characters of a subset that cade `src/bs21-guard.ts` reads the same way: ASCII letters,
digits and spaces, the escapes `\s`, `\d`, `\b`, `\.` and `\-`, `.`, groups `(` and `(?:`, `|`, character classes
of those (a bare `-` only last) and the quantifiers `?`, `*`, `+`, `{n}`, `{n,}` and `{n,m}`. Both compile it
case-insensitive, with `.` matching every character and `\s`, `\d` and `\b` reading ASCII only. It must not match
empty or blank text, before or after its separators are removed.

Matching fails closed and over-matches on purpose. Before J168 a text refused as class `script` when one of its letters was not
ASCII after NFKD, mark stripping and case folding, or when one word mixes letters of two scripts. So small capitals
and Greek, Cyrillic, Armenian and Lisu letters refuse in a guarded bundle, while "é", "ß" and fullwidth Latin letters
fold to ASCII and pass. Each text is then folded: NFKD, combining marks stripped, case folded, the Cyrillic, Greek
and Latin look-alike letters that `CONFUSABLES` lists mapped to Latin, and every decimal digit mapped to ASCII. A
literal matches when its letters and digits occur in the text's letters and digits, anywhere. So "FixtureCorp",
"fixture-corp.com", "#FixtureCorp", "Fixture" plus a soft hyphen or word joiner plus "Corp", "F" plus Cyrillic "і"
plus "xture Corp", "Fixture Corps" and "Fixture Corporation" all match the literal "Fixture Corp". A literal also
matches in a looser fold of both the entry and the text, where `i`, `l`, `1`, `|` and `!` read as `l` and `0` reads
as `o`. So "ZorbIax" with a capital I, "Zorb|ax", "Zorb1ax", "Z0rblax" and "F1xture Corp" match. A regex runs on the NFKC text, on the fold with punctuation as spaces, and with its separators
removed on the fold's letters and digits, so `chamfer\s+angle` also matches "ChamferAngle". A number entry matches
its value in any unit in any of these forms: a mention the claims gate's extractor reads; a digit run read whole,
at its one decimal point and as a grouped integer ("3.375" for 3375), or, when it holds a comma or two separators,
group by group and at its last separator ("12,5", ".5"); a middle dot, an Arabic decimal separator or a one-dot
leader as the point ("12·5"); a point with spaces around it ("12 .5", "12 . 5"); a fraction ("25/2", "12 1/2") or a
vulgar fraction ("12½", "12 and 1/2"); digit groups of 3 split by a space, a no-break or thin space, an apostrophe
or an underscore, read joined ("3 375", "3'375", "3_375"); an exponent ("1.25e1"); fullwidth or other decimal
digits; and its English spelling ("twelve point five", "twelve point fifty", "twelve point five zero", "twelve dot
five", "twelve comma five", "twelve and a half", "12 and a half", "twelve and 1/2", "one hundred and five"). The
whole part is also read as two pairs ("thirty three seventy five") and digit by digit ("one two point five", "three
three seven five" from 3 digits up). Hyphen-joined digits ("12-5") are not read as a decimal, because dates would
then match. Inflections the fold does not reach, abbreviations and other
leetspeak ("Z3rblax") need entries of their own. `narrate/tests/fixtures/narrated-video/nv-denylist-conformance.json` holds the cases both
repositories must agree on. cade keeps a byte-identical copy. The grouped, exponent, pair, digit-by-digit and
trailing-zero forms are tested here only (`test_a_grouped_exponent_or_spelled_number_refuses`) until cade reads them
and the shared fixture adds them in step.

The guard checks these texts, in this order, and refuses at the first group that matches:

| Group | Texts | Reported as |
| --- | --- | --- |
| record | the slug, each asset's id, path, receipt and text source path, each beat's id and asset id, each claim's id and receipt, and at intake the bundle directory's name and the job id; the numbers records hold: each asset's `size` and `fps` (with `num/den`), each beat's `target_s` and the start and end the intake writes for it | `slug`, `asset#N`, `beat#N`, `claim#N` and `job`, by position |
| voiced | each beat's voiced text, which the captions show | the beat id |
| claim | each claim's `spoken` text | the claim id |
| label | `--persona` at intake | `labels` |
| visible | at intake, the text source of each asset a beat shows (below), its strings joined into one text | `asset#N`, by manifest position |
| spoken | each paragraph after the pronunciation tables, at intake | the beat id |
| joined | each two adjacent voiced texts, and at intake each two adjacent spoken paragraphs, read as one text; it reports only an entry neither part matches alone | `a+b`, the two beat ids |

The guard is built before any other bundle check. Record texts are checked first and named by position, so a
refusal never repeats a private id. A report holds `{status, ip_private, never_name, denylist_sha256, pinned,
entries, checked, matches}`. Each match names its segment, group, the entry's position (`entry`, null for class
`script`) and class, and a refusal detail names the entry by position too. No other refusal echoes a bundle value it
refuses: a malformed beat id, `target_s`, `asset_id`, asset `kind` or claim `value.unit` is named by its field, and an
unknown key is counted. Every other refusal of `claims` and `intake` whose detail an entry matches, or that holds a
backslash escape (repr of a format character), keeps its code and has its detail withheld. So does every refusal
while a given denylist cannot be read, and while a pin is set and no denylist is bound yet. No report or detail
holds the matched text, a literal, a pattern or a denylist number, so a refusal may go to a log. A pass records
`private_terms` and the state `private_terms: passed` in `intake.json`. A bundle with no `privacy` block and no pin
records `not_declared`. A denylist given to such a bundle still runs.

A guarded intake writes `records/private-terms.json` (schema 2): the guard's status and digest, the digest of the
NarratedVideo record it wrote to `narrated-video.json` and the narrate jobs its segments name, and, per narrate job,
the digests of the job record and of the pronunciation table it names. It also holds `visible_text`: the intake's
visible-text state and the unread and opaque asset positions, which `deliver_check` reports (TIN-7788). The state
is `passed` exactly when both lists are empty and `partial` otherwise. When an `intake.json` lies beside the records,
its `states.visible_text` and its `visible_text` unread and opaque lists must equal the marker's. Every load of that records directory checks
it and refuses `private_terms_stale` on a change, so a table edited after intake cannot add a spoken term. `init`,
`plan`, `run` and `explain` also refuse a NarratedVideo record that is not the one the intake wrote. So an edited
persona label or a segment pointed at another narrate job refuses, and so does a job built from `init` flags. A
records directory with no marker refuses too when the `intake.json` beside it says the guard passed or refused, or
when `NARRATED_VIDEO_DENYLIST` or `NARRATED_VIDEO_DENYLIST_SHA256` is set. The intake's own `--records` input is
exempt, because the operator's base records come from no intake. Deleting both the marker and `intake.json` outside
a private lane still removes the check, so the producer keeps OUT where the bundle lives. So does deleting the
marker and editing the `intake.json` status to `not_declared`, outside a private lane; both edits need write access
to OUT itself, which the producer controls. A pinned lane refuses either way.

Visible text (TIN-7788). A slide or plot shows text the script never says: a title, axis labels, a legend, tick
values. The guard reads no pixels, and this repository has no OCR dependency. So an asset names its on-screen text
in a text source, bound by digest in its manifest `text` field (`narrate/video/visible_text.py`):

| Source | What counts |
| --- | --- |
| `.svg`, the vector the picture was drawn from | every run of character data and every comment, including character references as the XML parser decodes them, and the `aria-label` and `xlink:title` attributes. A plotting library that draws glyphs as paths writes each label as a comment beside them. The `metadata`, `style` and `script` elements are skipped, because none of them is drawn. A `script` still makes the source opaque. The file must be UTF-8 |
| `.json`, `{"kind": "nv_asset_text", "schema_version": 1, "texts": [...]}` | each string the producer drew. An empty list says the asset draws no text |

An SVG source is opaque when it may draw text that no string names. It holds an
`image`, `feImage`, `foreignObject` or another embedding element. It runs script
through a `script` element or an event handler attribute. It refers to another
file through an `href` or a `url()` that is not a `#` fragment, a CSS `@import`,
a CSS `image()` or `image-set()`, a CSS backslash escape or an
`xml-stylesheet` processing instruction. A presentation attribute such as
`fill` or `filter` takes CSS as `style` does, so a backslash in an attribute in
no namespace counts as an escape. A `data-*` attribute or a namespaced one,
such as `inkscape:export-filename`, is metadata: a `url()` there counts, a
backslash does not. Or it
gives no string at all, as text outlined to paths does. Its strings are still
guarded. A JSON source is never opaque. Text outlined to paths beside another
string, such as a `title`, is not opaque. The guard cannot compare the SVG with
the picture's pixels, so that text stays the producer's review.

The guard reads each shown asset's strings joined by newlines as one `visible` text, so a term split across two
labels still matches. Only assets a beat shows are read. `intake.json` lists them under `visible_text` as `read`
(with a text source), `unread` (without one) and `opaque` (read, with an opaque SVG), by manifest position, and each
segment row's `asset.text` holds the source's kind and digest or `null`. The state `visible_text` is `passed` when
every shown asset had a text source and none was opaque, `partial` otherwise, and `not_declared` when no denylist
runs. An unread or opaque asset does not refuse at intake. The records marker carries the state, and `deliver_check`
reports it as the operator gate `visible_text`, so a partial cut keeps `operator_states_open` non-empty and
`public_upload_allowed` false. The intake's admit reads the same summary, so `intake.json` lists
`visible_text_unread` under `admit.pending_operator` exactly when the state is `partial`. Whether a private lane
should refuse one at intake is open.

The guard reads text only. These pass it, and the producer reviews them:

| Not read | Why |
| --- | --- |
| a paraphrase or a translation | no entry spells it |
| the pixels of a slide, plot or clip with no text source or an opaque one, and text burned into an MP4 or GIF frame | the guard reads no pixels and runs no OCR; on-screen asset text reaches the video, and the `visible_text` gate holds the delivery at the operator |
| a text source's drawing that differs from its picture | the digest binds the file, not that it matches the picture; the producer keeps them in step |
| asset container metadata (PNG text chunks, MP4 atoms) | it is not shown. The intake copies asset bytes by digest into the private store, and the outputs drop it: compose checks both MP4s and handoff strips each slide layer ("Compose and delivery") |
| a job or records written another way than intake | no intake ran, so no marker exists, and J168 removes `subject`'s refusal for such a job |

The intake states record `private_terms` and, beside it, `producer_review: pending_operator` for these. Tests use
invented terms only.

## Deck import

A slide deck assembled outside this repository enters as a `Deck` base by
digest: its video, its timeline and a `stems.json` with per-page voice start
and end, take digests and gains on the deck clock. `place` checks each take
digest against its narrate run's `output_sha256["narration.wav"]` and refuses a
mismatch (`voice_stem_unbound`). A deck that tightened a synthetic take causes
that mismatch. The deck's own assembler, content and configuration stay in the
deck's private repository.

## Safety

| Rule | Enforced by |
| --- | --- |
| No voice clip, rendered narration, overlay, frame, bed audio, loop name, vendor stack or asset id, licence PDF, transcript, client text, host name or personal path in git, CI or logs | `tests/test_public_tree.py`. Tool results carry ids and digests |
| kitpip is never a flake input and never vendored | `program/externals.json` registers the shape with no pin value; the private pin record holds digests and ids only, checked before spawn |
| No `.vrm` model, VRM texture, rendered frame, face timeline of a real narration or renderer build enters git. The VRM renderer is pinned like kitpip, with its engine lock hash-bound. CI never downloads a browser | the synthetic GLB and stub renderer in `narrate/tests/fixtures/narrated-video/`, and `program/externals.json` with no pin value |
| A VRM overlay needs the model's likeness consent (SP-R13) and appearance approval (TIN-7130). Only the Internal edition carries one until a ruling | `vrm.gates` at admit, and again before the renderer spawns |
| Agents never acquire music | `acquiredBy : < Operator >` |
| Client deliveries default to `ClientNarrated`: the synthetic narrator and kitpip avatar, no camera picture-in-picture (NV-6). `ClientVoiceOnly` stays available per project. Every client delivery gates the bed | `Edition.check` at Plan, Place and DeliverCheck |
| Never loudness-normalise the mix. One limiter at -1.5 dBTP. Drift over 0.5 LU fails | `Delivery` bounds, `loudness_drift`, `true_peak_exceeded` |
| Never write under `artifacts/runs/` or inside a narrate run | the store layout, `avatar_outside_store` |
| Verified is not accepted | separate states: source checks, stub render, local render, lip sync, listening, Content ID, delivery |

## Decided bed level

The deck project's ruling 58 settled the bed level: the operator picked 20 dB
under the voice from a matched-loudness A/B. The meaning follows the deck's
bed recipe: the un-ducked bed sits 20 dB under the voice, and the sidechain
then ducks it 7 dB. `bedBelowVoiceLu = 20` before the duck is the default, and
it stays a knob.

## Unknowns

- The sidechain threshold (-45 dBFS per 10 ms block) is a starting value. It
  has not been compared on a real narration with breaths and room tone.
- `Stereo` writes the mono mix on both channels at -3.01 dB each. Whether the
  operator wants a true stereo bed is open (NV-2 keeps mono until an A/B).
- A video base keeps its own size and rate in `base`. `compose` scales it to
  the delivery profile (lane L6).

- Sidechain attack: 50 ms here (the deck seat's practice). The earlier music-bed
  draft used 20 ms. Not yet compared.
- The deck's `stems.json` (L8) does not yet carry the pre-tighten take digest
  that `place` needs to bind a tightened take.
- Only the x86_64-linux kitpip binary is pinned. Darwin and aarch64 need a
  build on those systems.
- The first real kitpip render ran on the fixture voice
  (`docs/agent-notes/2026-10-28-kitpip-010-avatar-render.md`). A render of a
  real narration, and its time on an idle builder, are not recorded.
- The slide card matches the deck seat's description. No matched A/B against a
  deck cut is recorded. Cards of different heights crossfade with the outgoing
  card's edge visible until the incoming card is opaque.
- The flash formula is an inference from the deck seat's figures. Its exact
  formula was not read.
- Even eased, a `Full` fade cannot keep a step within 30% when the slide and
  what is under it differ too much in mean luma for the fade's frame count
  (video black to white needs 11 frames at 30 fps, over 0.35 s). The gate
  then fails, and `min_fade_s` in `compose.json` names the fade that passes.
- Burned captions and the deck project's own delivery profiles are not built.
- The VRM renderer itself (the three-vrm page, its Puppeteer or Playwright driver and their lockfile)
  is not built. Its pin stays `commit_pinned_digest_pending` until it is, and only the stub has rendered.
  three-vrm on three.js r186, GPU raster in headless Chromium on the target host and every VRM frame rate
  are unmeasured.
- Whether a GPU render repeats bit for bit on one host is unmeasured. `frames_identity: per_host` is
  the manifest's claim, not a measurement.
- The face timeline follows loudness only. Word timings from a forced aligner and phonemes within
  words come later, so VRM lip sync is not expected to pass review until they land.
- `avatars.json` has no Dhall type yet. `vrm.model_problems` and `vrm.gates` hold its shape. The likeness
  consent it names is typed (`Consent.Scope.Likeness`); `Consent.Type` has no ruling field, so the SP-R13
  ruling is the `Likeness` scope itself plus the model record's `likenessConsent.ruling`.
- `accept` reads a decision id's form only. Whether Softproxy holds an Operator accept under it is the
  caller's check, and no tool here resolves the id. Rows say `resolution: form_only` until one does.
- The acceptance lock is a local `flock` at the store root. Two hosts writing one store root at once are
  not covered. `plan --record` and `run` write `graph.json` outside that lock. An `accept` that lands while
  one runs can leave `graph.json` without its row. That view shows fewer acceptances, never more, and the
  next `plan --record` adds the row.
- The VRM meta permission fields (`avatarPermission`, `commercialUsage` and the rest) are recorded,
  not gated. The model's author and the permission that fits are an open operator decision.
- Whether offline VRM video carries a burned-in badge is open. So is VRM in any edition except
  `Internal`.
- The claims gate reads English number words and the units listed in "Demo bundle intake". A number said in
  another language reads as a bare count or not at all. A unit outside the table reads as a bare count unless
  its shape marks it as a possible scale (single letters, scale abbreviations, vowel-less lower-case units,
  binary prefixes, mixed-case units and the listed capital ones). A real word unit outside the table ("beats
  per minute") still reads as a bare count. Roman numerals with L, C, D or M ("CLI", "MD") are not read, because
  they collide with common acronyms. The gate checks that a receipt is named, not what the receipt says.
- The pronunciation check compares the number tokens of a paragraph before and after the tables, not their
  values or order: an entry that only reorders a paragraph's number words passes. narrate's chunker normalises per
  chunk, and the check normalises per paragraph, so an entry that matches across a chunk boundary is read
  differently. `claims` alone does not check pronunciation tables.
- A demo bundle's MP4 plays from program second 0 under every beat. A bundle with clips at several
  offsets, or more than one clip, needs a deck base or a later stage.
