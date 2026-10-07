# S3 take_intake lane contract: one-command intake for the second take

Status: **Phase 1 contract freeze**, 2026-10-07. Lane `take_intake`, sprint
`20261007-s3`, branch `sprint/20261007-s3/take_intake`, worktree
`.local/sprint3/take_intake`. Baseline `452fd467fa6bfd22daf51e8c071bbd4029819a95`.
Tracker: Linear TIN-5186 (XORuby relay issue; root writes Linear, this lane
never does).

Authority, in the order the reassertion note
(`docs/agent-notes/2026-10-07-reassertion.md`) gives:

1. Operator dialogs: `docs/agent-notes/2026-10-05-user-prompts.md` (constant
   tuning, box fan, phrase meaning, product axioms, "the inital esction of mvp
   video provided fan / bg noise capture opprotinity") and
   `docs/agent-notes/2026-10-06-s2-resume.md` (interview: FULLER default with a
   required reviewed per-take capture interval; "a second take will exist by
   2026-10-09").
2. Repository `AGENTS.md` and the plan `docs/spec/PROJECT.md` (S2 status,
   standing evidence boundaries).
3. Interview ruling of 2026-10-07 (`docs/agent-notes/2026-10-07-s2-operator-rulings.md`):
   **"Second take | New take family plus full pipeline | New take_family_id;
   FULLER with a reviewed fan interval, phrase anchoring, timing, marked compact
   export; family id reported to XORuby on TIN-5186"**, and the approved V6
   privacy statement in the same note.
4. R-HOOK-CONVERGENCE-20261004 / R-N11 / R-N12 / R-N13 (TIN-3692 comment
   98cf680c-7299-4949-bfb2-60079053ad43).

Root administers review, signed merge, tool admission, recipe import,
publication, Linear and the XORuby relay. This lane never pushes, merges,
writes Linear, sends the TIN-5186 message, edits root-owned files, downloads
models, starts a daemon, writes under an existing `artifacts/runs/*`
directory of the main checkout, or touches `~/Documents` / `~/Desktop`.
**No real take is processed by this lane.** The second take does not exist yet;
the operator runs `run` on it after review.

## 1. Scope

In scope: `scripts/take_intake.py`, a stdlib-only orchestrator with three
subcommands that reuse existing entrypoints as subprocesses and never
reimplement DSP, analysis or export:

| Subcommand | Effect | Writes |
| --- | --- | --- |
| `plan SOURCE [--family ID] [--arrangement PATH] [--bpm X]` | Read-only intake plan | Nothing (stdout JSON only) |
| `run SOURCE --capture-interval A B --capture-review TEXT [--interval-reviewed-includes-setup] [--family ID] [--arrangement PATH --anchor-seconds S --anchor-source TEXT] [--bpm X] [--features base\|extended] [--analysis-python PATH] [--state-root DIR]` | Runs the ordered stage graph below with resume support | New intake directory under the state root; new pipeline run directory created by `run_demo.py`; nothing else |
| `run --resume INTAKE_ID [--state-root DIR]` | Crash-recovers one recorded intake in place | Same intake directory |
| `packet RUN_DIR` | Builds the evidence packet and the TIN-5186 message draft from a finished or partial intake | `RUN_DIR/evidence-packet.json`, `RUN_DIR/tin-5186-message-draft.json` |

`RUN_DIR` for `packet` is the **intake run directory** written by `run`
(`<state-root>/<family_id>/<intake_id>/`). It binds the pipeline run directory
by its manifest hash. Passing a pipeline `artifacts/runs/<id>` directory is
refused with `not_an_intake_run_dir`; the packet never guesses an intake.

Also in scope: `just/take.just` (root imports it), the skill
`.agents/skills/take-intake/SKILL.md`, the tool draft
`program/tool-drafts/take_intake.json` (closed input schema for root admission),
tests in `tests/test_take_intake.py`, and dated receipts
`docs/agent-notes/sprints/20261007-s3/take_intake-*.json`.

Out of scope (not claimed): processing the real second take; any new DSP,
filter, profile or default; changing FULLER, `conservative3` or the shelf
option; adopting a detector, profile or master; listening, musical, note or
missed-note verdicts; authoring an arrangement reference for the new take;
assigning a corpus split; sending anything to XORuby or Linear; web routes
(the `/sources/[id]/capture` route is referenced as the place to review an
interval, not changed); hosted execution; memory quotas.

## 2. Owned files

| Path | Role |
| --- | --- |
| `scripts/take_intake.py` | Orchestrator: plan / run / resume / packet |
| `tests/test_take_intake.py` | Unit, refusal, resume, packet and gated end-to-end tests; synthetic fixture generator lives inside this module |
| `just/take.just` | Recipes `take-plan`, `take-run`, `take-resume`, `take-packet`, `take-intake-test` |
| `.agents/skills/take-intake/SKILL.md` | Intent, knobs, dependencies, research, iteration, evidence |
| `program/tool-drafts/take_intake.json` | Typed tool descriptor draft for root (`program/tools.json` is root-owned) |
| `docs/spec/sprints/TAKE_INTAKE_S3.md` | This contract |
| `docs/agent-notes/sprints/20261007-s3/take_intake-*.json` | Contract freeze, tests, end-to-end and handoff receipts |

Generated lane outputs go only under
`.local/sprint3/take_intake/artifacts/s2/take_intake/` (gitignored). The
end-to-end run follows the robustness-lane pattern: it copies `scripts/`,
`profiles/` and `program/` into a fresh `artifacts/s2/take_intake/e2e-<UTC>/root/`
and runs there, so the existing entrypoints' hard-coded `ROOT/artifacts/runs`
and `ROOT/artifacts/demo-invocations` land inside the lane directory, never in
the worktree's or the main checkout's `artifacts/runs`.

## 3. Reused entrypoints (subprocess, exact argv, no shell)

| Stage | Entrypoint (unchanged) | Notes |
| --- | --- | --- |
| demo | `scripts/run_demo.py SOURCE --profile fuller --capture-interval A B --capture-review TEXT --features F --backend stdlib --no-latest [--bpm X] [--analysis-python P]` | FULLER default with per-take binding (`media.py bind_capture`); media, export, rhythm, noise, tone, notes, phrases, (extended), dag, markers, report |
| demo resume | `scripts/run_demo.py --resume INVOCATION_ID` | Robustness S2 crash recovery; never re-infers settings |
| flags_triage | `scripts/flags_triage.py RUN --output INTAKE/flags-triage.json` | Frozen rule v1 ordering; no verdicts |
| arrangement_reference | `scripts/arrangement_reference.py REF --run-dir RUN --output INTAKE/arrangement-assessment.json` | Only with `--arrangement`; REF must bind this source's sha256 |
| arrangement_markers | `scripts/arrangement_markers.py RUN --assessment … --output RUN/arrangement-markers.json` | Only with `--arrangement` |
| phrase_anchor | `scripts/phrase_anchor.py spans --clicks RUN/<clicks selector> --arrangement REF --clicks-per-grid-period N --anchor-seconds S --anchor-source TEXT --output INTAKE/phrase-anchor-spans.json` | Only with `--arrangement`, an operator anchor and an extended `clicks` selection |
| phrase_timing | `scripts/phrase_timing.py --analysis RUN/analysis.json --phrases <RUN/arrangement-markers.json or RUN/phrases.json> --output-root INTAKE/phrase-timing --run-kind real_take` | Always `real_take`: direction withheld (`withheld_uncalibrated`) |
| marked_video | `scripts/marked_video.py --run-dir RUN --output RUN/marked-preview --selection phrase-review` (or `all-review --arrangement-markers arrangement-markers.json`) | marked_video requires its output beneath `artifacts/runs`; nested in the new run as in the October 5 precedent |
| marked_compact | `scripts/marked_compact.py RUN --picture-preview RUN/marked-preview --arrangement-markers arrangement-markers.json --output INTAKE/marked-compact` | Only with arrangement markers; otherwise abstains `arrangement_markers_required` |
| share_export | `scripts/share_export.py <marked-compact.mov or marked-video.mov> INTAKE/share/marked-share.mp4 --height 720 --audio-kbps 96 --codec h264 --crf 27 --timeout-seconds 900` | The compact shareable marked clip; master retained |

Imported, not re-implemented: `corpus_split_s1.validate_split` and `SCHEMA`
(row draft check), `corpus.identifier` / `corpus.fingerprint`,
`artifact_ids.source_id_for`, `run_demo.sha256`, `run_demo.strict_json`,
`run_demo.atomic_json`, `media.probe` via `FFPROBE`. `capture_profile.py` /
`apply_capture_profile.py` are **not** in the default chain: the FULLER
template is applied through `run_demo`/`media.py` per-take binding, which is
the path that reproduced the accepted chain byte for byte (FULLER_S2 A1/A2).
The plan lists the capture-profile path as an explicit alternative only.

## 4. Take family identity

- Derived ID, deterministic and content-bound, domain-separated like
  `artifact_ids.source_id_for`:
  `take_family_id = "take-" + sha256(b"video-utils/take-family/v1\0" + source_sha256_ascii)[:16]`.
  It satisfies `corpus.IDENTIFIER`. The same bytes at any path give the same ID.
- `--family ID` overrides the derived ID (must satisfy `corpus.IDENTIFIER`).
- Existing-family registry (read-only, bounded): built-in floor
  `{"demo-oct5-2026", "october5-demo"}` bound to source
  `a522115f4e72e19384fb341bc84369728eceefe49183b8c6367a1008a95176c6`, plus
  every `take_family_id` / `source_sha256` pair found in
  `docs/spec/examples/corpus-split/*.json`,
  `docs/agent-notes/sprints/*/corpus-*.json`,
  `docs/agent-notes/peers/xoruby/*.json` and prior intake states
  `<state-root>/*/*/intake.json` (each file ≤ 2 MB, ≤ 500 files).
- Refusals: `family_collision` (the chosen ID exists with a different
  source), `source_already_registered` (this source sha256 already belongs to a
  family, for example the October 5 take: this is not a new take). Re-running
  `run` for the same source and family after a finished intake refuses with
  `intake_exists` and names the intake ID; a new attempt needs `--resume` or an
  explicit new `--family`.
- Corpus row **draft** (`schema_id: video-utils.take-intake.corpus-row-draft.s3`):
  a `video-utils.corpus-split.s1` record (`id = <family>-take`,
  `origin: real_recording` or `synthetic_fixture` for fixtures,
  `parent_ids: []`, `augmentation_group_ids: []`, `manifest: null`,
  `annotation_refs: []`) with **`split: null`** and
  `split_status: "pending_operator_choice"`. A null split is not a valid
  corpus-split row by design; the plan also reports
  `validate_split` on an in-memory copy with `split: "unassigned"` (written to
  a temporary file beneath the state root's `.scratch/` and deleted), so the
  operator knows the row is admissible once a split is chosen. The lane never
  writes a corpus manifest.

## 5. `plan SOURCE` (read-only)

Output JSON (`schema_id: video-utils.take-intake.plan.s3`, sorted keys,
contains no clock time, so two invocations on the same path are byte-identical):

- `source`: `sha256`, `size_bytes`, `source_id` (`src_…`), `display_name`
  (basename only), location check result.
- `probe`: ffprobe summary only: container duration, video codec / width /
  height / `avg_frame_rate` / `r_frame_rate` / time base, `cfr_vfr_status`
  (`cfr_declared`, `vfr_suspected` or `unknown`), audio codec / sample rate /
  channels / start time. Missing fields are `null` with a reason.
- `take_family_id`, `family_basis` (`derived_v1` or `operator_supplied`),
  `collision_check` (registry files read with their sha256, result).
- `corpus_row_draft` and its `unassigned` admissibility check (section 4).
- `steps`: the ordered stage list of section 6 with, for each, the exact argv
  (with `<CAPTURE_START>`, `<CAPTURE_END>`, `<CAPTURE_REVIEW>`, `<RUN_DIR>`,
  `<INTAKE_DIR>` placeholders where the value does not exist yet), timeout,
  condition and whether it will run, abstain or needs operator input.
- `required_operator_inputs`: `capture_interval` (reviewed per take; the
  `/sources/[id]/capture` web route or `just review` are the review surfaces;
  the first 5.0 s are setup and never auto-confirmed), `capture_review` text,
  optional `arrangement_reference` (a new reference bound to this source's
  sha256; `program/demo-arrangement.json` belongs to the first take and is
  refused), optional `anchor_seconds` + `anchor_source`, optional `bpm`
  ("approximate operator pulse; not an intended score"), and later `split`.
- `unknowns` (section 9) and `claim_boundaries`.

`plan` refuses (exit 2, typed JSON on stderr, nothing written) on:
`source_missing`, `source_not_regular_file`, `source_is_symlink`,
`source_in_repository_tracked_path` (resolved path inside the repository and
either tracked by git or not ignored by `.gitignore`), `source_is_derived_artifact`
(inside any `artifacts/runs/`), `probe_failed`, `family_collision`,
`source_already_registered`, `arrangement_source_mismatch`.

## 6. `run`: ordered stage graph

Pre-flight (inline, before anything is written, in this order):

1. Argument refusals: `capture_interval_required` (no interval),
   `capture_review_required` (empty or > 2000 chars),
   `capture_interval_invalid` (non-finite, start < 0, duration outside
   0.1–10 s: the media.py bounds), `capture_interval_in_setup_window`
   (start < 5.0 s without `--interval-reviewed-includes-setup`),
   `anchor_requires_arrangement`.
2. Source refusals of section 5, then `capture_interval_outside_source`
   (end beyond probed audio duration).
3. Family resolution and collision refusals (section 4).
4. `state_root_invalid`: the state root must resolve beneath `ROOT/artifacts/`
   and not beneath `artifacts/runs/`; default `artifacts/take-intake`.

When `--interval-reviewed-includes-setup` is given, the intake state records
`capture_interval_setup_override: {"start_seconds": A, "setup_window_seconds":
[0.0, 5.0], "operator_flag": true, "recorded_at": …}` and the packet repeats it.
The flag is an operator assertion that the interval was reviewed; it never
claims the interval is noise-only.

Stages (each recorded in `INTAKE/intake.json` with status, argv, exit code,
start/end time, timeout, stdout/stderr tails ≤ 4 KiB with absolute paths
replaced by `<ROOT>`/`<SOURCE>`, output hashes and consumed-input hashes):

| # | Stage | Runs when | Terminal statuses |
| --- | --- | --- | --- |
| 1 | `demo` | always | `completed`, `completed_with_stage_failures` (run_demo exit 1 with a report), `failed`, `killed`, `timed_out` |
| 2 | `flags_triage` | demo produced `flags.json` | `completed`, `failed`, `skipped_dependency_failed` |
| 3 | `arrangement_reference` | `--arrangement` | `completed`, `failed`, `abstained_no_reference` |
| 4 | `arrangement_markers` | 3 completed | as above |
| 5 | `phrase_anchor` | `--arrangement`, anchor and an extended clicks selection | `completed`, `failed`, `abstained_no_reference`, `abstained_no_anchor`, `abstained_clicks_not_selected` |
| 6 | `phrase_timing` | demo produced `analysis.json` and `phrases.json` | `completed`, `failed`, `skipped_dependency_failed` |
| 7 | `marked_video` | demo export verified | `completed`, `failed`, `skipped_dependency_failed` |
| 8 | `marked_compact` | 4 and 7 completed | `completed`, `failed`, `abstained_arrangement_markers_required` |
| 9 | `share_export` | 8 or 7 completed | `completed`, `failed`, `skipped_dependency_failed` |
| 10 | `packet` | always (inline) | `completed`, `failed` |

A stage failure does not delete anything; dependants become
`skipped_dependency_failed`; the overall intake status is `completed`,
`completed_with_abstentions`, `partial` or `failed`. Exit code 0 only for
`completed` / `completed_with_abstentions`.

Source protection: the source's sha256, size and `mtime_ns` are measured
before stage 1 and after the last stage (and on every resume); any change
sets `source_changed` and fails the intake. No stage receives a writable
output path that resolves to the source or its directory.

Resume (`run --resume INTAKE_ID`):

- A per-family lock `INTAKE/.lock` holds the orchestrator PID. A live PID
  refuses `intake_locked`; a dead PID is recorded and taken over (own recorded
  task only, R-N11; no signal is ever sent to any process).
- Stages with a success-terminal status are skipped only if every recorded
  output hash re-verifies; a mismatch or missing output invalidates that stage
  and every later stage (outputs moved aside to `INTAKE/resume-<n>/displaced/`,
  never deleted).
- A `running` stage with a dead orchestrator, or `killed` / `timed_out`, is
  rerun. For `demo`, take_intake binds the run_demo invocation while the child
  runs: it diffs `ROOT/artifacts/demo-invocations/` before and after launch and
  records the single new directory whose `receipt.json`
  `resume_arguments.input_sha256` and `capture_interval` equal this intake's.
  Resume then calls `run_demo.py --resume <id>`. Zero or several candidates
  refuse `demo_invocation_unbound`; a bound invocation is never re-run fresh.
- Recorded arguments are replayed; passing settings with `--resume` refuses
  `resume_settings_conflict`.

## 7. `packet RUN_DIR`

`evidence-packet.json` (`schema_id: video-utils.take-intake.packet.s3`):

- `intake`: family ID, intake ID, status, stage table with numerators and
  denominators (stages completed / stages planned, abstained, failed).
- `stage_hashes`: per stage, sha256 of each output file (run-relative or
  intake-relative selectors only, never absolute paths).
- `signal_versions_consumed`: per analysis stage, the analyzed-input sha256 it
  declares (for example `analysis.json source.sha256` = `denoised.wav`) and
  whether it equals the current manifest's output hash (`current` /
  `stale_invalidated`).
- `tool_versions`: repository HEAD commit and dirty flag, sha256 of every
  invoked script, Python version, FFmpeg/FFprobe version line and binary
  sha256, profile name and profile file sha256.
- `capture`: interval, review text sha256 (text kept locally), setup override
  record, `noise_only_verified_by_worker: false`.
- `phrase_timing`: per-phrase measured signed offsets (median, IQR, count) and
  abstentions with reasons; `direction_status: withheld_uncalibrated`; no
  ahead/behind label.
- `phrase_anchor`: spans or the abstention reason; `adopted: false`.
- `flags_triage`: shown / total, hidden navigation proxies count.
- `deliverables`: marked preview, compact or share outputs with hashes and
  `review_status: exported_unreviewed`.
- `claims`: every reported item is classed `measured`, `inferred`,
  `needs_listening`, `operator_input_required` or `not_performed`
  (section 9 lists the fixed ones).
- `unknowns` (section 9) with explicit nulls and reasons.
- `corpus_row_draft` (split null).

`tin-5186-message-draft.json` (`schema_id: video-utils.take-intake.xoruby-draft.s3`,
closed schema, `status: draft_not_sent`): `take_family_id`, `family_basis`,
`origin`, intake status, stage status counts, probe class fields
(container duration rounded to 0.1 s, video codec, audio codec, sample rate,
channel count, `cfr_vfr_status`), the unknowns list (names only), the claim
class counts, split `null`, and the V6 statement reference
(`docs/agent-notes/2026-10-07-s2-operator-rulings.md`). It must contain **no**
media, no media-content hashes (no 64-hex string at all), no `src_`/`art_`
IDs, no source-timed spans or timestamps, no capture interval values, no
review text, no file names and no host paths. The family ID is a truncated,
domain-separated hash and is the one identifier the operator ruling directs
root to report. Root sends it; the lane never does.

## 8. Completion metrics (with denominators and claim classes)

| ID | Metric | Denominator | Claim class |
| --- | --- | --- | --- |
| M1 | `plan` determinism: byte-identical stdout across 3 invocations on the same path; identical `take_family_id`, `source` and `corpus_row_draft` for the same bytes at 2 different paths | 3/3 and 2/2 | measured (synthetic) |
| M2 | Family ID derivation equals the section 4 formula on 3 fixed sha256 vectors; derived IDs pass `corpus.identifier` | 3/3 | measured |
| M3 | Typed refusals, each with exact reason code and zero bytes written under the state root and the fixture root (directory snapshot before/after): `capture_interval_required`, `capture_review_required`, `capture_interval_invalid` (2 cases), `capture_interval_in_setup_window`, `capture_interval_outside_source`, `source_missing`, `source_is_symlink`, `source_in_repository_tracked_path`, `source_is_derived_artifact`, `family_collision`, `source_already_registered`, `arrangement_source_mismatch`, `anchor_requires_arrangement`, `state_root_invalid`, `resume_settings_conflict`, `intake_locked` | 17/17 | measured |
| M4 | Setup override: an interval starting at 0.2 s with `--interval-reviewed-includes-setup` is accepted and the override record appears in `intake.json` and the packet | 2/2 locations | measured |
| M5 | Resume scenarios with stub stages: (a) child SIGKILLed mid-stage, (b) orchestrator state left `running` with a dead PID, (c) a completed stage's output tampered, (d) a missing output, (e) live-lock refusal; after resume, completed stages skipped only with re-verified hashes and the final stage table equals an uninterrupted run's statuses | 5/5 | measured |
| M6 | Demo-invocation binding: exactly-one-candidate binding accepted; zero and two candidates refuse `demo_invocation_unbound` | 3/3 | measured |
| M7 | Packet completeness: every section 7 key present; every section 9 unknown present with a reason; `direction_status == withheld_uncalibrated` | keys present / keys required | measured |
| M8 | V6 message draft: closed key set; 0 matches for absolute-path, 64-hex, `src_`/`art_`, `.mov`/`.mp4`/`.wav`, and seconds-timestamp patterns; byte size ≤ 4 KiB | 0 violations over 6 pattern checks | measured |
| M9 | Packet and intake state contain 0 absolute host paths | 0 violations | measured |
| M10 | Source unchanged (sha256, size, mtime_ns) across every `run` and `--resume` invocation in the tests and the end-to-end run | n/n invocations | measured |
| M11 | End-to-end synthetic fixture through `run`: per-stage status table with stages completed / planned, abstentions with reasons; `demo` stage statuses from run_demo; export frame count source/export; final loudness and true peak vs profile targets (−18 LUFS, −1.75 dBTP) as measurements; phrase timing phrases measured / phrases total and abstentions; flags shown / total | stages completed / 10 planned | measured (synthetic fixture only); everything audible is `needs_listening` |
| M12 | Low-register guard (static): 0 occurrences of `highpass`, `lowpass` below 60 Hz, `bandreject`, `anequalizer` notch or a mains-frequency filter in the recorded FFmpeg filter graphs of the e2e run | 0 / filter graphs inspected | measured |
| M13 | Owned tests pass: `PYTHONPATH=tests python3 -m unittest test_take_intake -v` | passed / run, skips listed with reasons | measured |
| M14 | Tool draft has a closed input schema whose required fields and refusal codes match the CLI; skill names intent, knobs, dependencies, research, iteration and evidence | checklist items / 8 | review |

Not metrics: listening quality, low-end fullness, fan residue audibility,
phrase correctness, timing direction, note correctness, editor import. They
stay `needs_listening`, `operator_input_required` or `not_performed`.
Experimental non-improvement and recorded failures are valid completion.

## 9. Fixed unknown and boundary fields the outputs must carry

| Field | Value | Class |
| --- | --- | --- |
| `split` | `null`, `split_status: pending_operator_choice` | operator_input_required |
| `arrangement_reference` | `null` unless a source-bound reference is supplied | operator_input_required |
| `operator_bpm` | `null` unless supplied | operator_input_required |
| `meter`, `time_signature`, `tonic`, `mode` | `null`, reason `not_established` | inferred / unknown |
| `capture_interval_noise_only_verified` | `false` | needs_listening |
| `capture_interval_setup_override` | record or `null` | measured (operator flag) |
| `click_identity` | `unverified` | not_performed |
| `physical_capture_latency` | `uncalibrated` | operator_input_required |
| `phrase_timing_direction` | `withheld_uncalibrated` | not_performed |
| `phrase_boundary_correctness` | `unknown`, needs ≥ 10 operator boundaries | operator_input_required |
| `phrase_anchor_adopted` | `false` | — |
| `note_correctness`, `missed_or_extra_notes` | `not_performed`, no approved reference | not_performed |
| `listening_acceptance` | `not_performed` (FULLER-v1 acceptance covers only the accepted October 5 chain) | needs_listening |
| `low_end_fullness_feedback` | `open` | needs_listening |
| `editor_import` | `not_performed` | not_performed |
| `cfr_vfr_status` | measured or `unknown` | measured |
| `memory_ceiling` | `unknown_not_measured` | unknown |
| `xoruby_delivery` | `draft_not_sent` | — |
| `default_adoption` | `none` (no detector, profile or master adopted) | — |

## 10. Test protocol

Module `tests/test_take_intake.py`; run from the worktree root as
`PYTHONPATH=tests python3 -m unittest test_take_intake -v` with
`FFMPEG`/`FFPROBE` exported to the qualified
`/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/` pair.
Tests that need media skip with reason `ffmpeg_unavailable` only when those
binaries cannot be resolved; pure tests always run. Directly affected modules
run locally as well: `test_corpus_split_s1` (imported validator).

| Class | Covers | Fixture |
| --- | --- | --- |
| `FamilyIdTests` | M2 | three fixed hex vectors |
| `PlanTests` | M1, plan refusals of M3, collision and registry reading | `tiny` fixture (below) in a temp dir under `artifacts/s2/take_intake/tests-<pid>/`; a temp registry file injected for `source_already_registered` (the real take is never hashed or opened) |
| `RunRefusalTests` | remaining M3 cases, M4, M10 | `tiny` fixture; refusal cases need no FFmpeg except `capture_interval_outside_source` |
| `ResumeTests` | M5, M6 | stub stage table injected through the module's in-process API (`run_intake(..., stages=…)`), stubs are `python3 -c` children that write small JSON outputs, sleep, or `SIGKILL` themselves; a copied isolated ROOT for the demo-invocation binding cases |
| `PacketTests` | M7, M8, M9 | a constructed intake directory with stub outputs, plus V6 scrub negative controls (a planted absolute path, 64-hex string and `.wav` name must each be caught) |
| `EndToEndTests` | M10, M11, M12 | `take` fixture; gated by `TAKE_INTAKE_E2E=1`; isolated copied ROOT under `artifacts/s2/take_intake/e2e-<UTC>/`; overall bound 1800 s, one heavy job at a time; results to `artifacts/s2/take_intake/e2e-results.json` and the receipt `docs/agent-notes/sprints/20261007-s3/take_intake-e2e.json` |

Synthetic fixtures (generated in the test module with lavfi, `-fflags +bitexact`,
`-threads 1`; never derived from a real take; no V6 restriction):

- `tiny`: 3.0 s, 320×240 `testsrc2` at 24000/1001 fps H.264, mono 44.1 kHz AAC
  of pink noise (amplitude 0.02, seed 5186) in a `.mov`.
- `take`: 12.0 s, 480×320 `testsrc2` at 24000/1001 fps H.264, mono 44.1 kHz AAC,
  `.mov`. Audio by construction: pink noise (amplitude 0.02, seed 5186)
  throughout as the fan stand-in; 0.0–5.0 s setup window containing one
  0.3 s low thump (32.703 Hz plus harmonics 2–6) at 1.5 s; 5.0–7.0 s noise
  only; 7.0–12.0 s a click grid (5 ms 2 kHz bursts, period 0.674 s ≈ 89 BPM)
  and two identical 4-click riff phrases of C1-rooted harmonic stacks
  (32.703 Hz fundamental, harmonics 2–8 with decaying envelopes), then a rest.
  The e2e uses `--capture-interval 5.2 6.8` with review text
  `"synthetic fixture: pink noise only by construction (seed 5186)"`,
  `--features base`, `--backend stdlib`, no arrangement, no BPM.

## 11. Preregistration (single-arm verification, sealed before the run)

This lane runs no comparative experiment: one arm (the existing pipeline,
unchanged), no tuning, no held-out set, no default adoption. The end-to-end
run is a sealed verification with these predictions, recorded before it runs
and reported whatever the outcome:

- Fixture: `take` above, seed 5186, generated once; its sha256 is recorded
  before `run` and not regenerated after results are seen.
- Arm: `take_intake run` with exactly the section 10 arguments. No argument,
  threshold or fixture parameter is changed after the first result; a failing
  stage is reported as failing, and any repair is a new, separately labelled
  run that keeps the first result.
- Predictions: `demo` completes with a report; `flags_triage`, `phrase_timing`,
  `marked_video`, `share_export` and `packet` complete;
  `arrangement_reference`, `arrangement_markers`, `phrase_anchor` and
  `marked_compact` abstain (no reference); intake status
  `completed_with_abstentions` (prediction: 6 completed, 4 abstained, 0 failed of 10);
  phrase timing may abstain per phrase (`fewer_than_4_click_proximal_onsets`
  is an accepted outcome, not a failure); direction is withheld; source
  unchanged; 0 low-register guard violations; V6 draft 0 violations.
- Scoring: M11 table as observed against these predictions, per stage
  `as_predicted` / `differs`, with the reason for each difference.
- Interpretation boundary: a synthetic fixture result says the orchestration,
  refusals, resume and packet work; it says nothing about restoration quality,
  detection accuracy or musical correctness on the real second take.

## 12. Root-owned changes requested (not made by this lane)

1. Root `justfile`: add `import 'just/take.just'`.
2. `program/tools.json` and `scripts/tool_api.py`: admit `take_intake` from
   `program/tool-drafts/take_intake.json` (worker `scripts/take_intake.py`,
   subcommands `plan` and `packet` for MCP; `run` stays a just/CLI action
   because it is long and mutating) once root reviews the lane.
3. `scripts/mcp_server.py`: none beyond the admitted descriptor.
4. TIN-5186: root sends the message draft after the operator runs the real
   second take and reviews the packet.
5. `program/linear.json`: none from this lane.

Exact descriptor and recipe text is returned in the lane handoff's
`root_owned_changes_requested`.

## 13. Phases

1. Contract freeze (this document; receipt `take_intake-contract-freeze.json`).
2. Implementation of `scripts/take_intake.py`, recipes, skill and tool draft.
3. Owned tests (M1–M10, M13) and the sealed end-to-end run (M11, M12).
4. Handoff receipt `take_intake-handoff.json` with hashes, denominators,
   skips with reasons and root requests.
