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
| SPR-120 | kitpip now, VRM after the bench. Internal demos use kitpip v0.1.0. The VRM offline renderer (`avatar.manifest/v1`, a second external) is built as a draft, and the switch waits for the 11-14 go/hold bench |
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
| L9 acceptance | the operator | L7, L8 | listening, lip sync and labels leave `pending_operator` by receipt |

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
| 6 | `avatar` | segment | `overlay.mov` (ProRes 4444) and its manifest, drawn by the job's avatar external (kitpip or vrm) | `avatar_overlay_v1` | edition-gated |
| 7 | `avatar_check` | segment | label-chain result | none | with avatar |
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
KP-15 plans stale.

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
| `deliver_check` | delivery except `handoff`, the bed's licence PDF digest and Content ID result, labels |
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
| Handoff turned on | `handoff` |

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
| `renderer` | `{kind: kitpip \| vrm, name, version}`. A vrm renderer also names its `engine`, its `step` and the `gpu` (`vendor`, `renderer`, `driver`) that drew the frames |
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
clock. Blender with the VRM add-on is the fallback. Neither is built here yet. Its lockfile will be
hash-bound in the pin, and CI never downloads a browser. Tests run a stub renderer.

**Command shape.** The wrapper (`narrate/video/vrm.py`) speaks one:

| Command | Output |
| --- | --- |
| `RENDERER --version` | one JSON line on stdout: `{version, commit}` |
| `RENDERER render --vrm FILE --face FILE --size WxH` | raw RGBA8 frames on stdout (straight alpha, rows top-down), exactly `frames * W * H * 4` bytes, with frames and fps from `face.json`. The last stderr line is one JSON report `{frames, step, renderer: {name, version, engine}, gpu: {vendor, renderer, driver}}` on exit 0, or `{refused, detail}` on exit 1 |

The wrapper hashes the pipe as it streams it into FFmpeg (`prores_ks` 4444, `yuva444p10le`), then
writes `frames.sha256` and the v1 manifest itself. It never passes `--badge` or `--realtime`. It refuses
`vrm_frames_mismatch` when the byte count is not the face timeline's frame count. A report without a
renderer, GPU vendor or driver refuses `vrm_report_invalid`. A renderer refusal is relayed with its own
code. A timeout, a crash, an FFmpeg failure or a renderer off its pin is a failure, not a verdict.

**Face timeline.** `face.json` (`narrate/video/face.py`, schema `face.timeline/v1`) is the renderer's
only view of the narration. It holds one frame per overlay frame on the `narration_output` clock, at the
base's fps. Frame i shows the face at `i * den / num` seconds into its segment's `narration.wav`. Each
frame has a mouth viseme and weight (`sil`, `aa`, `ih`, `ou`, `ee`, `oh`), blink `[left, right]`, the
five VRM mood presets, look `[yaw, pitch]` and head `[yaw, pitch, roll]`. It is bound to the narrate run
by `run_id`, `content_sha256` and the WAV's digest. v1 has one source, `loudness_envelope`. The mouth
opens with the RMS of each frame (`aa`, weight `min(1, 4 rms)`) and closes to `sil` below 0.01. The
eyes blink on a fixed schedule (first at 1.3 s, then every 3.7 s), and mood, look and head stay neutral.
A forced aligner's word timings, phonemes within words and an expression track are later sources.

**The model record.** `avatar.rig` names a record in the private `avatars.json`. The record holds `id`,
`kind: vrm`, the model's `sha256` and `bytes`, a `likenessConsent` (`id`, `scopes`, `grantedBy`,
`grantedAt`, `revokedAt`, `evidenceSha256`), an `approval` (`ref`, `state`, `decidedBy`,
`decidedAt`, `vrmSha256`, `evidenceSha256`) and `badge: {burnedIn: null}`. The model is a
private-store blob found by digest and re-hashed before the renderer spawns. The wrapper reads its VRM
meta from the glTF JSON chunk: `VRMC_vrm` for 1.0, `VRM` for 0.x. It records the licence fields and
nothing else from the meta, so no author or model name. A model with no meta licence refuses
`vrm_meta_missing`, and a file that is not a VRM binary glTF refuses `vrm_invalid`.

**Gates.** admit refuses, and the stage refuses again before the renderer spawns, when:

| Code | Rule |
| --- | --- |
| `vrm_model_missing`, `vrm_model_invalid` | `avatar.rig` names no record, or the record does not read |
| `vrm_digest_mismatch` | `avatar.rigRevisionSha256`, when set, is not the record's `sha256` |
| `vrm_consent_missing`, `vrm_consent_revoked` | the SP-R13 likeness consent lacks the `Likeness` scope or an evidence digest, or is revoked |
| `vrm_approval_missing` | no TIN-7130 approval with `state: approved`, `decidedBy: Operator`, an evidence digest and `vrmSha256` equal to this model. A new model revision needs a new approval |
| `vrm_badge_undecided` | the record sets `badge.burnedIn`. Whether offline VRM video carries a burned-in badge is not ruled: no renderer draws one, and no record may settle it |
| `vrm_edition_unruled` | the edition is not `Internal`. Other editions wait for a ruling after the 11-14 bench |

With a VRM avatar, admit also lists `vrm_badge_decision` as an operator gate at `deliver_check`, so
`deliver_check` plans `pending_operator`.

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
| `status JOB [--json]` | `just nv-status` | prints the recorded `graph.json` and its `pending_operator` gates |
| `explain JOB STAGE [--segment ID]` | `just nv-explain` | prints the key document and each field that changed since the stage's last run |
| `verify DIR` | `just nv-verify` | re-hashes a stage directory or every current stage of a job |
| `run JOB [--stages S,...] [--until S] [--force S,...] [--json]` | `just nv-run` | runs the stale stages (`script` to `handoff`, with `avatar` and `avatar_check` when the job has an avatar) and stops at the first refusal. Finished stages stay fresh. Records `graph.json` |
| `pin-check [--externals FILE] [--external kitpip\|vrm]` | `just kitpip-pin-check`, `just vrm-pin-check` | checks the private pin against `program/externals.json` and `KITPIP_BIN` (or, with `--external vrm`, `VRM_RENDERER_BIN`) against the pin. Refuses `kitpip_pin_missing`, `kitpip_pin_pending`, `kitpip_pin_mismatch` or `kitpip_missing`, or the `vrm_` forms (`vrm_renderer_missing` for a missing renderer) |
| `stage JOB STAGE [--segment ID]` | `just nv-stage` | runs one node when every input is fresh, else refuses `stage_input_stale` |
| `fixture --out DIR` | `just nv-fixture` | writes a synthetic workspace: records, a private-store stand-in and a fixture lexical release |
| `init` then `run` | `just nv-quick JOB NARRATE_JOB SCRIPT [ARGS]` | a simple job in one step |

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
| 66 | `kitpip_overlay` | `avatar` |
| 67 | `kitpip_verify` | `avatar_check` |
| 68 | `narrated_video_mix` | `mix` |
| 69 | `narrated_video_compose` | `compose`, `handoff` |
| 70 | `narrated_video_verify` | `deliver_check` |
| 71 | `vrm_overlay` | `avatar` with a vrm external (draft, SPR-128) |
| 72 | `vrm_verify` | `avatar_check` with a vrm external (draft, SPR-128) |

The workflow skill is `narrated-video`, with one skill per stage tool. The
fallback recipes are `just nv-quick` and `just nv-run`. L3 drafts tool 62 in
`program/tool-drafts/narrated_video.json` and writes the first part of the
`narrated-video` skill (plan, status and explain). L4 drafts tools 63, 64, 65
and 68 there, adds `run` to the `narrated-video` skill and writes the
`narrated-video-place`, `music-bed` and `narrated-video-mix` skills. L5 drafts
tools 66 and 67 and writes the `kitpip-overlay` and `kitpip-verify` skills. The VRM
draft drafts tools 71 and 72 and writes the `vrm-overlay` skill. L7 admits them.

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
| `voice` | the script, the narrate job and its records | one narrate run in `narration/` (mapping `narration_v1`), labels from its voices | narrate's own refusals, as failures |
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
| `compose` | `base`, `place`, `mix`, every selected `avatar` and `avatar_check`, slide pictures by digest | `video.mp4`, `video.upload.mp4`, `captions.srt`, `captions.vtt`, `description.txt`, `chapters.json`, `compose.json` | `captions_burn_unsupported`, `captions_missing`, `slides_exceed_program`, `overlay_exceeds_base`, `frames_mismatch`, `label_chain_broken` |
| `deliver_check` | `compose`, the voice and avatar manifests, the bed record | `deliver_check.json`: gate states and `delivery_gate` | the edition codes at DeliverCheck, `label_chain_broken`. A failed gate is a state |
| `handoff` | `base`, `place`, `mix`, `avatar`, `compose` | `layers/` and `edit.json` | `label_chain_broken` |

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
`avatar-<segment>.mov` (each overlay as kitpip wrote it), `slide-<page>.<ext>`
(each slide picture as stored), `voice.wav`, `clips.wav` (when the base kept
its sound), `bed-ducked.wav` (with a bed, before the limiter) and the captions.
`edit.json` holds the placements, the overlay boxes and starts, the slide runs,
the avatar-off spans, the mix gains and the stage key of every input. FCPXML
and OTIO export is phase 2. Until an editor imports one, it stays unverified in
an application.

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
  three-vrm on three.js r186, headless Chromium's GPU path on AMD and every VRM frame rate are unmeasured.
- Whether a GPU render repeats bit for bit on one host is unmeasured. `frames_identity: per_host` is
  the manifest's claim, not a measurement.
- The face timeline follows loudness only. Word timings from a forced aligner and phonemes within
  words come later, so VRM lip sync is not expected to pass review until they land.
- `avatars.json` has no Dhall type yet. `vrm.model_problems` and `vrm.gates` hold its shape.
- The VRM meta permission fields (`avatarPermission`, `commercialUsage` and the rest) are recorded,
  not gated. The model's author and the permission that fits are an open operator decision.
- Whether offline VRM video carries a burned-in badge is open. So is VRM in any edition except
  `Internal`.
