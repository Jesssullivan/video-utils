# S2 robustness lane contract (phase 1 freeze)

Lane `robustness`, sprint `20261006-s2`, Linear TIN-5609 (parent TIN-5599).
Branch `sprint/20261006-s2/robustness`, worktree `.local/sprint2/robustness`;
root signs the merge. Authority: the repository AGENTS.md and
R-HOOK-CONVERGENCE-20261004 (R-N11/R-N12/R-N13). This document is the lane's
frozen contract. It implements the PROJECT.md robustness extension row
("broader phone/Photo Booth fixtures, resource limits, interrupted-run recovery,
report regression checks").

Phase 1 ran no numerics, no FFmpeg render and no test. The only reads were
source code, specs and the accepted run's `manifest.json` probe. The lane runs
**no experiment**: it has no arms, no scored candidates and no tunable detector
or profile. The acceptance tolerances in §6 are sealed by the commit that adds
this file, before any fixture is built. They must not be loosened to make an
observed run pass. A failure is recorded as a failure (§8).

## 1. Scope

There are two deliverables.

1. **`run_demo.py --resume INVOCATION_ID`.** This is a crash-recovery path for
   one recorded invocation. It re-validates source and media hashes. It skips
   stages that are success-terminal, hash-verified and whose dependencies were
   also skipped. It reruns the remaining stages in the original order, inside
   the same run directory and under the same invocation ID. It never creates a
   second run directory. Any hash drift produces a typed refusal that writes
   nothing.
2. **Synthetic phone and Photo Booth fixtures through the full pipeline.**
   `tests/support/phone_fixtures.py` builds small FFmpeg fixtures (each ≤10 s).
   `tests/test_phone_fixtures.py` drives each one through
   probe → clean → export packet comparison → rhythm rebase → editor-plan tail
   coverage → report render. It asserts that source rate, channels and
   timeline are preserved and that inputs are never overwritten.

Out of scope: any change to `media.py`, `rhythm.py`, `editor_marker_plan.py`,
`share_export.py`, `report.py` or other workers (they are read and reused, not
edited). Also out of scope: default profile, detector or master adoption; tool
catalog, MCP or skill admission (root-owned, see §9); memory measurement or
limiting; real-take processing in tests; listening acceptance; physical A/V
sync claims; note-correctness or missed-note claims; Final Cut or Resolve import
proof.

## 2. Owned files

| File | Change |
| --- | --- |
| `scripts/run_demo.py` | additive `--resume`; additive receipt fields (§3.2); new-run behaviour unchanged |
| `tests/test_demo.py` | existing tests unchanged in meaning; new `DemoResumeTests` and `DemoResumeProcessTests` classes appended |
| `tests/support/phone_fixtures.py` | new fixture builder (test support only, not a product tool) |
| `tests/test_phone_fixtures.py` | new FFmpeg-backed fixture and pipeline tests |
| `docs/spec/sprints/ROBUSTNESS_S2.md` | this contract |
| `docs/agent-notes/sprints/20261006-s2/robustness-*.json` | dated receipts (contract freeze, implementation, fixture run, handoff) |

Generated outputs go only under `artifacts/s2/robustness/` (gitignored). Test
temporary roots are created there with `tempfile.mkdtemp(dir=…)`. They are
removed on success and retained, with their path attached to the failure, on
failure. Accepted `artifacts/runs/*` directories are read-only. The real take
`/Users/jess/Documents/Movie on 10-5-26 at 3.38 PM.mov` is never opened by any
lane test.

## 3. `--resume` contract

### 3.1 CLI

`run_demo.py --resume INVOCATION_ID [--no-latest]`

- `INVOCATION_ID` must fully match `^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$`.
  Anything else, including path separators, `..` or whitespace, is refused as
  `invalid_invocation_id`.
- `--resume` is mutually exclusive with `INPUT`, `--existing-run`, `--profile`,
  `--capture-interval`, `--capture-review`, `--bpm`, `--backend`, `--features`,
  `--analysis-python` and `--pitch-seconds`. A conflict is an argparse error
  (exit 2). All settings are replayed from the receipt's recorded
  `resume_arguments`. `--no-latest` may only make the recorded setting
  stricter.
- Exit codes match a fresh run: 0 or 1 by the same rules as `main()`'s final
  status, and 1 for any typed refusal.

### 3.2 Additive receipt fields (written by every invocation, fresh or resumed)

These fields are additive. Existing keys keep their names, types and meaning.

- `resume_arguments`. Recorded at bootstrap, before any stage. It holds `mode`,
  `input_path` (resolved absolute path, or null), `input_sha256` (hashed by
  run_demo before the media stage; null in existing-run mode, where
  `existing_run_dir` is set instead), `profile`, `capture_interval`,
  `capture_review`, `bpm`, `backend`, `features`, `analysis_python`,
  `pitch_seconds` and `no_latest`.
- `orchestrator`. Holds `{pid, started_at}` for the current invocation or
  resume attempt.
- Per stage: `started_at`, `completed_at`, and on success
  `artifacts: {run-relative path: sha256}` (the fixed table in §3.4).
  `execution.worker_sha256` already exists and is reused.
- `resume_history[]`. One entry per resume attempt, appended:
  `{resume_index, resumed_at, orchestrator_pid, skipped_stages[],
  rerun_stages[], verified: {source_sha256, manifest_sha256, denoised_sha256,
  cleaned_sha256}, displaced_outputs: {path: sha256},
  orphan_staging_dirs_observed: int, lock: {status: acquired|stale_taken_over,
  prior_pid}, memory_ceiling_bytes: null,
  memory_ceiling_status: "unknown_not_measured"}`.

A receipt without `resume_arguments` (created before this lane) is refused as
`receipt_lacks_resume_arguments`. Resume never infers settings.

### 3.3 Receipt location (no discovery)

1. Read `ROOT/artifacts/demo-invocations/<id>/receipt.json` (bounded at 2 MiB,
   regular file, not a symlink, strict finite JSON).
2. If it is the existing pointer form `{invocation_id, run_dir, receipt}`, the
   pointer's `receipt` must equal
   `<run_dir>/demo-invocations/<id>/receipt.json` exactly. `run_dir` must
   resolve without symlink components, and the target's `invocation_id` must
   equal `<id>`. Any mismatch is `receipt_invalid`.
3. Otherwise the bootstrap file is the full receipt. This happens when the
   orchestrator died before the media stage returned, so no run directory has
   been recorded.

### 3.4 Stage artifacts, success-terminal statuses and dependencies

Success-terminal statuses are `completed`, `measured_candidates`,
`existing_media_verified_unreviewed`,
`existing_delivery_hash_verified_unreviewed` and `not_available` (the last only
for existing-run export). Every other status is rerun: `running`, `starting`,
`failed`, `skipped_dependency_failed`, or a missing stage entry.

| Stage | Recorded artifacts (run-relative) |
| --- | --- |
| media | `manifest.json` plus every `manifest.output_sha256` entry |
| export | `export/outcome.json` plus every `outcome.output_sha256` entry under `export/` |
| rhythm | `analysis.json`, `events.csv` |
| noise / tone / notes / phrases | `noise.json` / `tone.json` / `notes.json` / `phrases.json` |
| clicks, pitch, meter, tonal, comparisons (extended) | the exact selector recorded in `selected_evidence` |
| dag | `dag.json` and `flags.json` when present |
| markers | `markers.json`, `markers.csv` |
| report | `report.html` |

The dependency table is frozen at the implementation commit after reading each
worker's actual inputs. Where a worker's run-directory reads are not fully
enumerated, that stage depends on **all** earlier stages. The minimum edges
are: export, rhythm, noise, tone and notes ← media; phrases ← media, rhythm;
meter ← rhythm; tonal ← rhythm, phrases, pitch; comparisons ← rhythm, phrases;
dag ← every analysis stage; markers ← dag; report ← every stage.

**Skip rule.** A stage is skipped only if all of these hold:

- its status is success-terminal;
- every recorded artifact exists as a regular non-symlink file whose sha256
  equals the recorded value;
- its current worker file hash equals the recorded `execution.worker_sha256`;
- every dependency was skipped.

A completed stage downstream of a rerun stage is itself rerun. Upstream outputs
may change, and AGENTS.md requires downstream invalidation. A stage that is
success-terminal but has a hash mismatch is **not** rerun. It is a typed
refusal (§3.6).

**Displacement.** Before a stage reruns, any of its current output files are
moved, never deleted, into `<run_dir>/demo-invocations/<id>/resume-<n>/displaced/`
with their hashes recorded. Export is the exception: `media.py export`'s own
cached-outcome verification handles an `export/` directory that a killed stage
completed. Existing-run retirement (`OVERWRITTEN_OUTPUTS` against the prior
snapshot) then behaves as in a fresh existing-run invocation. The prior
snapshot is verified and never re-taken.

### 3.5 Run-directory invariants

- If the media stage is success-terminal, the recorded `run_dir` is reused, and
  no `media.py clean` is invoked.
- If the media stage is not success-terminal, a killed `media.py clean` can
  only have left an `artifacts/runs/.staging-*` directory, because publication
  is an atomic rename. Before rerunning media, resume makes a bounded,
  read-only check of at most 10,000 entries of `artifacts/runs/*/manifest.json`.
  It looks for a published run whose `source.sha256` equals
  `resume_arguments.input_sha256` and whose `run_id` timestamp is at or after
  the media stage's `started_at`. One or more matches →
  `media_outcome_unrecorded_run_dir_exists`, listing the candidates. Resume
  never adopts a run by discovery. It counts orphan `.staging-*` directories
  but never deletes them.
- Across every resume scenario in §5, the number of published run directories
  created per invocation is exactly 1.

### 3.6 Typed refusals

Each refusal prints `{"status":"error","reason":<code>,"invocation_id":…,"message":…}`
to stderr and exits 1. It writes nothing: the receipt bytes are unchanged, no
directory or lock is created, and no worker is started. All checks run before
the lock is acquired.

| Code | Condition |
| --- | --- |
| `invalid_invocation_id` | ID fails the regex |
| `receipt_not_found` | no bootstrap receipt for the ID |
| `receipt_invalid` | oversized, symlink, non-finite or malformed JSON, pointer mismatch, ID mismatch |
| `receipt_lacks_resume_arguments` | receipt predates §3.2 |
| `invocation_already_terminal` | receipt `status == "completed_unreviewed"` (nothing to resume). `completed_with_stage_failures`, `failed_preserving_media` and a receipt without a final status are resumable |
| `orchestrator_may_be_alive` | recorded `orchestrator.pid` responds to `os.kill(pid, 0)`. PID reuse gives a safe false refusal |
| `prior_worker_group_alive` | a non-terminal stage's recorded `execution.pid` group responds to `os.killpg(pid, 0)`. No signal is ever delivered (R-N11: inspection only, no cross-session action) |
| `resume_lock_held` | `demo-invocations/<id>/resume.lock` exists and its recorded PID is alive. A dead PID is taken over and recorded |
| `source_hash_drift` | input (or manifest `source.path`) sha256 differs from the recorded value |
| `media_hash_drift` | `manifest.json`, `denoised.wav` or `cleaned.wav` differ, or the native-PCM extent check (`verify_pcm`) fails |
| `stage_artifact_hash_drift` | a success-terminal stage's recorded artifact is missing, a symlink or has a different hash (names stage and path) |
| `worker_hash_drift` | a stage that would be skipped has a changed worker file |
| `snapshot_hash_drift` | existing-run prior snapshot under `demo-history/` differs from its receipt |
| `media_outcome_unrecorded_run_dir_exists` | §3.5 |

## 4. Fixture contract (`tests/support/phone_fixtures.py`)

`build_fixture(kind, directory, *, seconds=6.0, timeout_seconds=60) -> dict`

Bounds:

- `seconds` ≤ 10, otherwise `FixtureError`.
- Every FFmpeg or ffprobe call has an explicit timeout ≤ 60 s and uses
  `-nostdin -n` and `-threads 2`.
- An existing output path is refused (fixtures never overwrite).
- Binaries come from `FFMPEG`/`FFPROBE`. Tests skip with a stated reason when
  the qualified binaries are absent.

The returned receipt holds `kind`, `path`, `sha256`, the exact commands, the
binary paths and sha256s, `expected` values, `measured` probe values and
`unknown` fields. No randomness is used beyond fixed FFmpeg seeds (`anoisesrc`
seed 5609).

**Audio content (all kinds).** The 0.00–1.00 s lead-in is pink noise only
(amplitude 0.02, seed 5609); it is the synthetic capture source. From 1.00 s
the noise continues and adds:

- distorted C1 bursts, `0.3·tanh(3·sin(2π·32.70·t))`, gated 120 ms every
  0.25 s;
- a 3.5 kHz, 9 ms exponential click every 0.5 s.

These are synthetic signal facts, not musical or intended-note references.

| kind | video | audio | timeline features |
| --- | --- | --- | --- |
| `phone` | H.264 360×640 portrait, display matrix rotation 90 (applied by stream-copy remux with `-display_rotation:v:0 90`), ~29.97 fps VFR (frame drop pattern ⇒ ≥2 distinct frame durations), track timescale 30000 | AAC stereo 48 kHz, L≠R gain | audio start ≈ +0.25 s via `-itsoffset 0.25`; audio extends past video end |
| `photo_booth` | H.264 1280×720, time base 1/600, frame-duration cadence cycling 24/25/26 ticks (mean 25 ⇒ 24 fps) | AAC mono 44.1 kHz | audio ends 0.069 s after the last presented video frame end |
| `photo_booth_preroll` | stream-copy cut of `photo_booth` at a non-keyframe (GOP 48), producing an MOV edit list | as source | ≥1 leading decode-only (`D`) video packet verified by ffprobe |
| `phone_hevc` | as `phone` but libx265 `hvc1` | as `phone` | `skipUnless` libx265 is listed by `ffmpeg -encoders` |

Real-take reference: these values were read from the accepted run
`20261006T041633Z-990aa1bd6737` `manifest.json`. They are reported, not
computed.

- Video: H.264 1620×1080, time base 1/600, avg_frame_rate 108930/4549 (≈23.95
  fps, mean ≈25.06 ticks).
- Audio: AAC mono 44.1 kHz, start 0.0, header duration 150.954059 s.
- Video header duration: 150.905 s.

The header-duration difference is 49.059 ms. The lane instruction states
≈69 ms. The fixture uses 0.069 s as instructed, and the discrepancy is carried
as `real_take_audio_tail_reconciled: false`. Header durations are
diagnostic-only in `media.py`, and the presented-frame end may differ. The
photo_booth size of 1280×720 is the instructed fixture size, not the real
take's size.

## 5. Test protocol (≥14 tests; observed: 0 run at freeze)

Run from the worktree root:
`PYTHONPATH=tests python3 -m unittest test_demo test_phone_fixtures -v`, with
`FFMPEG`/`FFPROBE` exported to the qualified nix-store binaries. Heavy fixture
pipeline runs execute sequentially (one heavy job at a time), each under a
600 s subprocess timeout.

**`tests/test_demo.py::DemoResumeTests`** (mocked `invoke`, no media; all
existing tests unchanged):

1. `test_resume_after_orchestrator_crash_mid_stage_skips_verified_prefix`.
   A simulated orchestrator death (an uncaught `BaseException` in `tone`)
   leaves `tone: running`. Resume skips media, export, rhythm and noise,
   reruns tone, then notes, phrases, dag, markers and report per the
   dependency rule, completes, keeps the same `run_dir` and ID, appends
   `resume_history[0]`, and leaves exactly 1 run directory.
2. `test_resume_reruns_failed_stage_and_downstream_only`.
3. `test_resume_displaces_unverified_outputs_without_deleting`.
4. `test_resume_refusals_write_nothing`. Table-driven `subTest` over
   `invalid_invocation_id`, `receipt_not_found`, `receipt_invalid`,
   `receipt_lacks_resume_arguments`, `invocation_already_terminal`,
   `source_hash_drift`, `media_hash_drift`, `stage_artifact_hash_drift`,
   `worker_hash_drift` and `snapshot_hash_drift`. For each it asserts exit 1,
   the typed reason, byte-identical receipt and a before/after file-tree
   equality.
5. `test_resume_refuses_live_orchestrator_and_live_worker_group_without_signalling`.
   Uses a test-owned sleeping child as the "live" PID and asserts it is still
   alive afterwards.
6. `test_resume_lock_held_and_stale_lock_takeover`.
7. `test_resume_media_incomplete_reruns_media_once_and_refuses_unrecorded_run_dir`.
8. `test_resume_existing_run_mode_verifies_snapshot_and_never_resnapshots`.
9. `test_resume_rejects_conflicting_arguments`.
10. `test_stage_timeouts_unchanged_and_recorded`. Resource limits: stage
    timeouts media/export 1200 s, analysis 600 s, optional 300 s,
    dag/markers/report 180 s; `MAX_OUTPUT_BYTES` 2 MiB; `media.TIMEOUT` 600 s,
    probe 60 s; `rhythm.run` 180 s; share_export bound 30–900 s. Each is
    asserted against the constant and the receipt's `timeout_seconds`, and
    `memory_ceiling_status == "unknown_not_measured"`.

**`tests/test_demo.py::DemoResumeProcessTests`** (real subprocesses, stub
workers in an isolated temp ROOT, no FFmpeg):

11. `test_killed_worker_mid_stage_then_resume_completes`. A stub worker
    SIGKILLs itself mid-stage. The stage records `failed` with returncode −9.
    Resume reruns it and completes, with 1 run directory.
12. `test_orchestrator_sigkill_mid_stage_then_resume_completes`. A stub worker
    SIGKILLs its parent `run_demo.py` (its own test-created process) and then
    exits. The receipt shows `running`. Resume completes with identical
    `invocation_id` and `run_dir` and 1 run directory.

**`tests/test_phone_fixtures.py`** (qualified FFmpeg, isolated temp ROOT
containing copies of `scripts/`, `profiles/` and `program/`; run_demo is
invoked as a subprocess with `--no-latest`; repository `artifacts/runs` is never
written):

13. `test_builder_bounds_and_no_overwrite`.
14. `test_phone_fixture_properties`. Asserts rotation side data 90 (sign as
    reported by ffprobe), stereo, 48000 Hz, ≥2 distinct frame durations, audio
    start within 1 AAC frame + 2 ms of 0.25 s.
15. `test_photo_booth_fixture_properties`. Asserts 1280×720, mono, 44100 Hz,
    time base 1/600, frame-duration set ⊆ {24, 25, 26} ticks with all three
    present, and audio end − last presented frame end = 0.069 s ± (1024/44100 +
    0.002) s.
16. `test_preroll_fixture_has_decode_only_packets`.
17. `test_phone_pipeline_conservative3`.
18. `test_photo_booth_pipeline_conservative3`.
19. `test_preroll_pipeline_conservative3`.
20. `test_phone_pipeline_fuller_with_synthetic_capture_interval`.
21. `test_photo_booth_pipeline_fuller_with_synthetic_capture_interval`.
    Uses `--profile fuller --capture-interval 0.2 0.9 --capture-review
    "synthetic fixture lead-in: pink noise only by construction (seed 5609)"`.
    It also asserts that FULLER without an interval refuses
    `capture_interval_required` before any run directory exists.
22. `test_preroll_pipeline_fuller_with_synthetic_capture_interval`.
23. `test_phone_hevc_pipeline_conservative3` (skipUnless libx265).

Pipeline checks per run (tests 17–23), with each check counted in §6:

- **P1 input immutability.** The fixture sha256, size and mtime_ns are
  unchanged after the run.
- **P2 native PCM.** `manifest.pcm` sample_rate and channels equal the fixture
  probe. `sample_count` equals an independent ffprobe decoded-sample count of
  the fixture audio stream. `denoised.wav` and `cleaned.wav` pass
  `ensure_pcm_matches`.
- **P3 timeline.** `manifest.timeline.audio_start_seconds` equals the fixture's
  probed audio start, and `no_time_stretch` is true.
- **P4 export packets.** `export/outcome.json` verification has
  `video_packet_timeline_preserved` and `video_packet_payload_hashes_preserved`
  true, `video_frame_count_preserved` true, and `relative_audio_video_start_verified`
  true with |delta| ≤ `aac_timing_tolerance_seconds`. For `phone`, the
  exported display-matrix rotation equals the source's (measured;
  `rotation_applied_to_pixels: false`). For `photo_booth_preroll`,
  decode-only packet state is reported.
- **P5 rhythm rebase.** `analysis.json` lineage `status ==
  "hash_bound_run_derivative"`, `timeline_rebased` true, and
  `original_audio_start_seconds` equal to the manifest audio start;
  `filter_or_detector_delay` stays `uncalibrated`.
- **P6 editor tail.** A PTS artifact is built from ffprobe `-show_frames`
  (`clock: original_source_stream_timestamps_seconds`) of the fixture video.
  `editor_marker_plan.make_plan` gets the run's generic markers plus one
  lane-labelled synthetic point in the audio-only tail (`video_end, audio_end`).
  The tail row's disposition must be `outside_video_coverage`, and an in-video
  control point's must not be. When `markers.json` has ≥1 marker, a full
  `editor_marker_plan.build` over the run is also exercised. Otherwise that
  sub-check is recorded `abstained_no_generic_markers`.
- **P7 report.** The `report` stage is `completed`, `report.html` is non-empty,
  the receipt has `listening_accepted: false`, and no stage writes a
  missed-note, extra-note or note-correctness verdict.
- **P8 unknowns preserved** (§7).

If a fixture exposes a defect in a non-owned worker, the lane does not patch
that worker. The test stays written to the correct contract and is marked
`unittest.expectedFailure` with a reference to the
`root_owned_changes_requested` entry and the retained fixture path. The failure
is reported in the handoff receipt and is never silently skipped.

## 6. Completion metrics (denominators and claim classes)

Claim classes:

- **M** — measurement on synthetic fixtures.
- **P** — process-level test assertion.
- **I** — inference.
- **U** — unknown or not measured.

Nothing in this lane is a real-take or listening claim.

1. **Resume scenarios (P).** Passing scenarios / 9 resume tests (1–3, 5–8,
   11–12). Target 9/9.
2. **Typed refusal coverage (P).** Refusal codes asserted to write nothing /
   14 codes in §3.6. Target 14/14. Covered by tests 4–7.
3. **Run-directory invariant (P).** Invocations with exactly 1 published run
   directory / resume-scenario invocations. Target all.
4. **Killed-worker recovery (P).** Runs that resumed to `completed_unreviewed`
   or `completed_with_stage_failures` with an identical ID and run_dir / 2
   (tests 11–12). Target 2/2.
5. **Fixture properties (M).** Fixtures whose probed properties match §4 / 4
   kinds. HEVC is counted as skipped, not passed, when the encoder is absent.
6. **Pipeline matrix (M).** Fixture×profile runs completing P1–P8 / 6 required
   runs (3 fixtures × {conservative3, fuller+synthetic interval}) + 1 optional
   HEVC run. Reported per check, as P_k passes / runs.
7. **Input immutability (M).** Fixture hashes unchanged / all fixture runs.
   Target all. The real take is opened 0 times.
8. **Resource limits (P/U).** Timeout constants asserted / 10 listed (test
   10). Memory ceiling = **unknown** (not measured; no RSS limit enforced).
   Wall-clock per pipeline run is reported as a measurement, not a bound.
9. **Test count (P).** Lane-new tests ≥14 (23 planned). Existing `test_demo`
   tests still pass.
10. **Experimental non-improvement.** Not applicable (no experiment). A
    fixture that exposes a non-owned defect is a valid completion state when
    recorded under §5.

## 7. Unknown and abstain fields the outputs must carry

- **Resume receipt:** `memory_ceiling_bytes: null`,
  `memory_ceiling_status: "unknown_not_measured"`, `listening_accepted: false`,
  and `final_media_identity_verification` re-run after resume.
- **Fixture receipts:** `real_take_equivalence: "not_established"`,
  `device_capture_equivalence: "unknown"`, `rotation_applied_to_pixels: false`,
  `real_take_audio_tail_reconciled: false`, `hevc: "run" |
  "skipped_encoder_absent"`, and `capture_interval_noise_only:
  "by_construction_synthetic"` (never a machine-verified claim on real media).
- **Pipeline outputs, retained as produced:**
  `physical_audio_video_sync_verified: false`,
  `music_preservation_listening_verified: false`,
  `filter_or_detector_delay: "uncalibrated..."`, and nullable BPM, meter,
  phrase and tonic fields left null when the worker abstains. Editor rows keep
  `native_contract_unverified` / `outside_video_coverage` / `needs_review`. No
  marker is promoted to a confirmed mistake.

## 8. Phase plan and receipts

- **Phase 1 (this commit).** Contract freeze plus
  `docs/agent-notes/sprints/20261006-s2/robustness-contract-freeze.json`.
- **Phase 2.** Implement `--resume` and the fixtures. Freeze the dependency
  table and the exact fixture commands in
  `robustness-implementation.json`.
- **Phase 3.** Run the owned test modules once with timing. Write
  `robustness-fixture-run.json` with every per-check denominator from §6 and
  any expectedFailure entries.
- **Phase 4.** Write `robustness-handoff.json` with commit SHAs, metrics,
  unknowns and root requests.

## 9. Root-owned changes requested (not made by this lane)

- `just/workflow.just`: add recipe
  `demo-resume invocation_id: python3 scripts/run_demo.py --resume {{quote(invocation_id)}}`.
- `.agents/skills/guitar-pipeline` (skill text): document `--resume`, its skip
  and dependency rule, and the §3.6 refusal codes. Resume is crash recovery,
  not a re-analysis or default-adoption path.
- `program/tools.json` / `scripts/tool_api.py` / `scripts/mcp_server.py`: no
  change required unless root admits `run_demo` as a typed MCP tool. If it
  does, the descriptor needs `resume: {invocation_id: string pattern §3.1}`,
  mutually exclusive with `input`/`existing_run`, and the §3.6 reasons as a
  closed error enum.
