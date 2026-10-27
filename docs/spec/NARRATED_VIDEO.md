# Narrated video (`narrate/video/`)

Authority: operator direction KP-13 (Linear TIN-7476 comment `94248deb`), rulings
KP-7 (`0f367c48`), KP-14 (`1c16fbda`), NV-1 to NV-5 (`9db389dc`), the deck
project's ruling 59(d) (`e427ecfc`) and KP-15 (`4ab7fc27`), repository AGENTS.md
and R-HOOK-CONVERGENCE-20261004 (R-N11, R-N12, R-N13). This spec is
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
| L5 kitpip pin and avatar | the private pin record, `avatar` and `avatar_check` | kitpip release, L4 | pin tests and one local render with a digest-only receipt |
| L6 compose and delivery | `compose`, `deliver_check`, `handoff`, `just/narrated-video.just` | L5 | alpha, caption, label and profile tests |
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
| 6 | `avatar` | segment | kitpip `overlay.mov` (ProRes 4444) and its manifest | `avatar_overlay_v1` | edition-gated |
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

A stage key is the SHA-256 of canonical JSON over the stage id, a hand-bumped
`impl`, the tool name, version and binary digest, resolved knobs, the edition
and the sorted input digests. The git commit is recorded and kept out of the
key. Freshness re-hashes outputs and never trusts mtimes. The store is
`artifacts/narrated/<job_id>/`, outside `artifacts/runs/`. L3 fixes the
details.

## Editions

| Edition | Synthetic voice | kitpip avatar | Camera or other PiP | Music bed |
| --- | --- | --- | --- | --- |
| `Internal` (default, NV-2) | yes | yes | yes | yes |
| `OwnContent` | yes | yes | yes | yes |
| `ClientVoiceOnly` (default for a client delivery) | refused | refused | refused | only when cleared |
| `ClientNarrated` (59(d)) | yes | yes | refused | only when cleared |

Every client edition gates the bed. A bed is cleared when its private record
holds a certified licence PDF digest and a clear Content ID result
(`MusicBed.licenceCleared`), and the job's `delivery.voiceOnlyListen` names the
receipt of a voice-only listen pass. A client delivery with a synthetic
narrator files as `ClientNarrated`, never as `Internal` or `OwnContent`, so the
bed gate applies to it.

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
  `music`, `tighten`, `captions`, `labels` and `delivery`. A `Deck` records
  `tightenEditsSha256`. `tighten.enabled` defaults to false (see "Tighten").
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
| base | a 1920x1080 card at 30/1, or a still when given |
| avatar | `kitpip`, pin default rig, 512 px render, bottom right, 0.22 of base width, 32 px margin |
| music | `None` unless a bed record id is given. When given: 20 LU under the voice (the deck project's ruling 58), sidechain duck 7 dB, attack 50 ms, release 400 ms, fades 3 s and 5 s, tail 5 s |
| tighten | `{ enabled = False }` (NV-2) |
| labels | no persona, no caption cue, no description line (KP-15) |
| captions | soft, SRT and VTT, not burned |
| delivery | `Web1080p30`, -16 LUFS, -1.5 dBTP, 0.5 LU, `Mono`, no upload, no handoff, no voice-only listen |

`examples/narrated-videos.dhall` holds four jobs: the simple Internal card job
with the fixture bed, the same job with a kitpip avatar and a persona label, a
ClientVoiceOnly deck job with no narrate segment, avatar or bed, and a
ClientNarrated deck job with a narrate segment, an avatar, tighten enabled and
generated tighten edits.
`examples/music-beds.dhall` holds one fixture bed of two generated E-major sine
loops. `check.py` regenerates the loops and the deck placeholders and checks
every digest, every reference, the edition rule at Plan, the persona rule, the
tighten rule and the bounds below. Its self-test mutates the examples 35 ways
and expects each mutation to be refused.

| Bound | Value | Refusal or check |
| --- | --- | --- |
| avatar width | 0.10 to 0.30 | out of bounds |
| `bedBelowVoiceLu` | 10 to 30 | out of bounds |
| `duckDb` | above 0, at most 12 | out of bounds |
| `driftLu` | above 0, at most 0.5 | hard gate |
| `truePeakDbtp` | at most -1.5 | hard gate |
| bed layers | 2 or 3 distinct loops | `bed_layers_invalid` |
| `acquiredBy` | `Operator` | `bed_acquisition_agent` |
| tighten edits on narrate segments | only with `tighten.enabled` | `tighten_on_synthetic` |

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
refuses `label_chain_broken`.

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

The workflow skill is `narrated-video`, with one skill per stage tool. The
fallback recipes are `just nv-quick` and `just nv-run`.

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
| kitpip is never a flake input and never vendored | the private pin record holds digests only, checked before spawn |
| Agents never acquire music | `acquiredBy : < Operator >` |
| Client deliveries stay voice-only, except the synthetic narrator and kitpip avatar under `ClientNarrated` (59(d)). Every client delivery gates the bed | `Edition.check` at Plan, Place and DeliverCheck |
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

- Sidechain attack: 50 ms here (the deck seat's practice). The earlier music-bed
  draft used 20 ms. Not yet compared.
- Whether `ClientNarrated` applies to client deliveries beyond the deck project.
  59(d) rules for that video only. Other client deliveries default to
  `ClientVoiceOnly` until the operator rules.
- The deck's `stems.json` (L8) does not yet carry the pre-tighten take digest
  that `place` needs to bind a tightened take.
- The kitpip release date and its knob set (KP-12).
- Whether kitpip writes `avatar_overlay_v1` itself or the `avatar` stage wraps
  its manifest. L5 decides and keeps the fixture current.
