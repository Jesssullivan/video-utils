# Changelog

## Unreleased

### Added

- A `Campaign` edition and `narrate video campaign-verdict`: on a Campaign job a machine
  verdict stands where `accept` and the operator outbox stand, and it is the one place
  `public_upload_allowed` reads true. Every other edition reads false and keeps listening
  and lip sync. A failed confidentiality check takes no fix, and the verdict reads admit
  again on the current records. Off by default: nothing runs it, and nothing here publishes.
- `avatar.external: look` (`narrate/video/look.py`): a Campaign job's overlay comes from a
  look record by digest, one clip per voice take. It draws nothing and calls no engine.
- `narrate/video/findings.py`: one typed record per gate code and page, read from
  intake, claims, preflight, `deliver_check.json` and the script and `voice_qa`
  stages, and `narrate video findings JOB`. A gate's exit code and first code stay,
  and no stage key moves.
- `narrate video round` and `campaign-bind`: a round a gate's findings start with
  no Softproxy decision, on a job bound to a campaign only, holding the stages its
  fix may run (`graph.reach`). At the cap the root records `parked`. A client
  edition, and any job with no binding, keeps its decision. Nothing calls these yet.
- `narrate video fix --extend`: one more FIX round per decision past the cap, each
  recorded (TIN-7788, rulings TIN-7125 `0690fe88`, `11296de3`).
- `narrate/serve/modal_batch.py`: a draft sealed Modal app for a
  `RentedAudioCppBatch` VoxCPM2 run, its host side `run_plan`, the
  `voxcpm2-batch-modal` record, and `just narrate-modal-dry-run`, which plays it
  with a fake `modal` client and the fake `audiocpp_cli`. Receipts gain
  `placement`, a render refuses a rented receipt under an on-prem record, and the
  runner gains `--placement` and `--checkpoint-s`. `run_plan` reads each
  consent again from the live file named by `--consents` before any upload, so
  a consent revoked after `plan` refuses `consent_revoked`. Nothing is deployed
  or run (TIN-7994).
- `src/timeline.rs` and `video-utils timeline validate|table|map|quantise`: the
  EDL model, frame quantisation and time map, bit-exact with the frozen
  talk-condense oracle (`tests/fixtures/edl-golden-v1.json`).
- `video-utils verify-run --timeline edl_v1`: condense runs are verified against
  their hash-bound EDL. The default receipt for guitar runs is unchanged.
- `condense publish`: a hash-bound run under `artifacts/condense/<run_id>/`.
- MCP tools 47 to 57: `timeline_validate`, `timeline_map` and the nine condense
  stages, each with a skill.
- Narrated video reruns on one job root: `intake --replace`, a commit counter in
  `current.json`, `JOB/rerun.json`, a compose-only proof in the render stage
  result, `narrate video fix` with a cap of 3 rounds, a `mixed` voice mode with
  `render-stage takes`, and a spend cap per GPU window as a request parameter.
  A FIX binds its decision and its cut: `nv accept` refuses `cut_sent_back` and
  a render of that cut refuses `fix_unchanged_cut`.
  A real mixed window stays refused until the Lease gaps close.

### Changed

- The condense edl stage validates every `edl.json` with the Rust timeline.
- Condense defaults: 2 parallel jobs, 4 whisper threads and a 7200 s limit per
  tool call (`CONDENSE_TOOL_TIMEOUT_S`).
- Narrated video: `deliver_check` adds the `avatar_box` and `slide_match` machine
  gates, which read frames of the composed video, so `nv cut` and the render stage
  result refuse a cut with content under the avatar or a wrong slide. `narrate video
  preflight` and the render stage's `claims_gate` and `preflight` phases refuse the
  same faults before any voice spend, and a result needs a passed preflight
  (TIN-7788). `avatar.boxExempt` and a bundle asset's `avatar_box: exempt` declare a
  render that may reach the box. A page with any sample that has no flat background
  stays `unchecked`, does not fail the gate, and appears in `frame_review` in
  `nv cut` and the result. `deliver_check` moves to impl 3, so an existing cut reruns
  that stage only.
- Narrate: a rented engine must pass the consent record's `hostedAllowed`, and
  the `confidential` job label refuses no engine until the TIN-7994 audit. A demo
  bundle's jobs keep the template's `confidential` and `allowHosted` flags. A rented
  batch uses the `RentedAudioCppBatch` backend. SP-4 health rows stay kept on client
  renders, and no narrate code enforces that limit.
- Narrate: `narrate voices` lists a private voice row that predates the Voice type,
  with missing fields as null or empty, and such a row refuses `consent_invalid`.
- Narrated video: `handoff` waits on `deliver_check` through an `order` edge that
  stays out of its stage key, so existing handoff keys hold. The published DAG gains
  a `row` block whose `tasks_sha256` binds the 16-task Hatchet row (TIN-7788), and
  `narrate/dhall/check.py` holds its `selected_by` and `edition_point` fields to
  the Dhall types.
- Narrated video: `nv run --stages` refuses `stage_input_stale` when a selected
  stage stays stale behind an upstream outside the list, where it used to return
  ok with nothing run (TIN-7788).
- Narrated video: J168 removes the `ip_private` and BS-21 refusals for go-live,
  and the November 30, 2026 audit revisits them. `ip_private` needs no denylist,
  number and geometry entries and the `script` class stop matching, and
  `nv subject` stops refusing `shown_text_unread` except on a `never_name` marker
  and prints `shown_unread` for the Cade worker. `never_name` keeps its list and
  its name match, but a name spelled with a letter outside the confusables floor
  no longer refuses until the audit.

## 0.2.0 (2026-10-15)

### Added

- `condense/`: talk condensing, moved from `Jesssullivan/talk-condense` at commit
  `bf5b9dc` (`docs/spec/CONDENSE.md`).

### Migration from talk-condense

- The package is `condense` instead of `talk_condense`. Every module is
  byte-identical; the tests change only their import lines.
- Recipes are `just condense-<stage>` from the repository root instead of
  `just <stage>`. Run them inside `nix develop .#condense`.
- The whisper model is the registered `ggerganov-whisper-cpp-ggml-small.en`
  entry in `program/models.json`. `just condense-model` fetches it into
  `models/`; the dev shell does not download it.
- The flake keeps talk-condense's nixpkgs revision for this shell: FFmpeg 8.1.2
  and whisper-cpp 1.8.4. `ffmpeg-headless` replaces `ffmpeg-full`; it has every
  filter and encoder the stages use.
- talk-condense had no licence file. Its sole author contributes it under this
  repository's MIT licence.
