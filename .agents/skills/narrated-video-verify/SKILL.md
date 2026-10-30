---
name: narrated-video-verify
description: Check a composed narrated video against its delivery profile, loudness, flash, caption and operator gates, and read what it may be used for.
---

# Let an agent read every delivery gate of a composed cut and compare two runs, without marking any operator gate passed.

**Hook:** MCP tool `narrated_video_verify` (proposed as tool 70, drafted in `program/tool-drafts/narrated_video.json`, not yet admitted). Fallback: `just nv-stage JOB deliver_check` or `just nv-run JOB`, inside `nix develop .#condense`.

**Capability:** `deliver_check` probes `video.mp4` and writes `deliver_check.json` with one state per gate (`passed`, `failed`, `pending_operator` or `not_applicable`) and a `delivery_gate`. A failed machine gate is a state, not a refusal. The stage refuses only an edition refusal at the DeliverCheck point and a broken label chain, re-derived from the voice and avatar manifests.

| Gate | Passes when |
| --- | --- |
| `profile` | H.264 yuv420p, AAC 48 kHz, the profile's size and rate, the delivery's channel count, the planned frame count and a soft caption track when `captions.soft` |
| `loudness` | the delivered sound is within `driftLu` of `targetLufs` and its true peak at or under `truePeakDbtp` |
| `flash` | at every slide change, the largest adjacent-frame jump in mean luma is at most 30% (relative to the darker frame, floor Y 16); `not_applicable` without slides |
| `captions` | the files asked for exist; the persona cue opens the captions and `extraNotice` ends `description.txt` when set |
| `listening`, `lip_sync` | never here: `pending_operator` until the operator's receipt |
| `bed_licence_pdf`, `bed_content_id` | with `upload` and a bed: the record holds the certified licence PDF digest and a clear Content ID result |

`delivery_gate.internal_review_allowed` is true when every machine gate passes. `upload_gates_closed` also needs `upload`, closed bed gates and, in a client edition with a bed, `voiceOnlyListen`. `public_upload_allowed` also needs every operator state closed (`operator_states_open` empty). Verified is not accepted: deliver_check never closes listening or lip sync, so it never reports a public upload as allowed. Uploading, sending and Content ID stay operator actions.

## Use and controls

1. `compose` must be fresh.
2. `just nv-stage JOB deliver_check`, then read `gates`, `flash.changes`, `loudness`, `profile.findings` and `delivery_gate`.
3. With `upload` and an open bed gate the node plans `pending_operator`. Recording the licence digest or the Content ID result in the private bed record reruns only `deliver_check`.
4. The operator's decision closes `listening` and `lip_sync`: `just nv-accept JOB GATE sp:dec:<ulid> VIDEO_SHA256` records it for the current render, by Softproxy decision id only. VIDEO_SHA256 is the cut the decision saw, from the Softproxy proposal. A decision about an earlier cut refuses. After a bed record update reruns only `deliver_check`, pass the same decision again for the same cut. An agent passes on an id the operator's accept produced and never writes one. Each row reads `resolution: form_only`: accept checked the id's form, not Softproxy. Free text, a machine gate, the `visible_text` gate and an unknown gate refuse. A partial `visible_text` keeps `deliver_check` at `pending_operator` after both acceptances, until a re-intake reads every shown asset's text. `deliver_check` keys on the job's digest, so an edit to `job.json` reruns it, and accept refuses `deliver_check_stale` until it has. A malformed `graph.json` refuses accept `store_invalid` with nothing recorded. `status` recomputes `accepted` and `pending_operator` and refuses `graph_stale` when `graph.json` differs, so a hand edit cannot hide a gate. See "Operator acceptance" in docs/spec/NARRATED_VIDEO.md.

## Speech, not guitar

Speech workflow, not a guitar default: the guitar axioms in AGENTS.md do not apply. deliver_check writes no media and no timeline of its own; the composed manifests it reads carry `no_time_stretch: false` with mapping `narrated_video_v1`.

## Limits

- The 30% flash limit is the deck seat's gate (design Addendum B). The jump formula is this lane's reading of it, not a port of the deck's check.
- Machine gates are measurements. Listening, lip sync, Content ID and delivery are separate operator states, and this stage never closes one.
- Reports carry ids, digests and numbers: no video, frame, caption text or store path.

## Agent iteration

Compare two `deliver_check.json` reports from runs that differ by one knob, at matched loudness. Record the comparison as a dated receipt in `docs/agent-notes/` with job ids, stage keys and gate states only.
