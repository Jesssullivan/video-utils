# S3 routes_processing lane contract: upload, source overview, capture review and process routes on real jobs

Status: **Phase 1 contract freeze**, 2026-10-07. Lane `routes_processing`,
sprint `20261007-s3`, branch `sprint/20261007-s3/routes_processing`, worktree
`.local/sprint3/routes_processing`. Tracker: Linear TIN-5718 (S3 parent and
TIN-5546 milestone links are root's). Baseline: `4bd806db3944d05fb4b5cca16a87642a71f5458f`.
Authority: [S3 routing contract](20261007-S3.md) (operator answers of
2026-10-07: full route map, priority capture -> process -> compare -> review ->
deliver, prototype stubs removed), repository `AGENTS.md`,
R-HOOK-CONVERGENCE-20261004 / R-N11/R-N12/R-N13 (TIN-3692 comment
98cf680c-7299-4949-bfb2-60079053ad43). Root administers review, signed merge,
capability admission, recipes, publication and Linear. This lane never pushes,
merges, writes Linear, edits root-owned files, downloads models, starts a
daemon, or writes under accepted `artifacts/runs/*` directories, `~/Documents`
or `~/Desktop`.

Design sources reused, not re-decided: [WEB_UI_DESIGN](../future/WEB_UI_DESIGN.md)
(lifecycle Choose clip -> Probe -> Review capture -> Configure preview ->
Compare -> Process; first five seconds never auto-confirmed as pure noise;
controls derived from tool contracts, no invented defaults),
[WEB_BACKEND](../future/WEB_BACKEND.md), [WEB_JOBS_S2](WEB_JOBS_S2.md) (store,
supervisor, idempotency, cancel, interrupted/retry, atomic publication,
reconciliation), [WEB_UI_S2](WEB_UI_S2.md) and [WEB_STACK_S2](WEB_STACK_S2.md)
(loopback BFF, Host guard, bearer token, Skeleton 5.0.1 / Effect 4.0.1 /
SvelteKit 2.70.3 / Svelte 5 runes), [FULLER_S2](FULLER_S2.md) and
`profiles/fuller.json`, the 2026-10-07 shelf ruling
(`docs/agent-notes/2026-10-07-s2-operator-rulings.md`; `profiles/fuller-shelf.json`
on branch `sprint/20261007-s2r/eq_shelf`, not yet on main at baseline).

## 1. Scope

In scope:

1. Routes in the existing SvelteKit app (`web/`), keeping the exact pinned
   stack and the loopback Host guard (`hooks.server.ts`) and loopback control
   URL/token rules (`lib/server/config.ts`) unchanged:
   - `/upload` (kept; copy and link updates only).
   - `/sources/[id=artifactid]` overview: probe summary (only what the control
     API measured; otherwise **Unknown** with its reason), bound runs, jobs,
     links into capture and process.
   - `/sources/[id=artifactid]/capture`: choose and review a fan-noise capture
     interval bound to the source sha256 and a baseline run; show measured
     interval statistics; never auto-confirm the first 5 s; submit a
     `capture_profile` job.
   - `/sources/[id=artifactid]/process`: FULLER default (requires a reviewed
     interval), `conservative3` explicit, optional bounded shelf only if a
     typed schema exposes it; separate cleanup / tone / dynamics knob groups
     with bounds read from typed tool schemas; no high-pass or notch control or
     default; submits `denoise` or `capture_profile` + `apply_capture_profile`
     jobs; span audition of completed renders (section 8.3).
2. `scripts/web_jobs.py`: from one admitted job type to a **closed allowlist**
   of four job types (`share_export`, `denoise`, `capture_profile`,
   `apply_capture_profile`), each mapped to `tool_api.descriptor` +
   `tool_api.validate` + `tool_api.validate_tool_arguments` +
   `tool_api.worker_command` with bounded outer deadlines; source-bound capture
   review records; schema version 2 with an explicit v1 -> v2 migration; one
   active media job per host.
3. `scripts/web_api.py`: job submission for the allowlist with typed refusals;
   capture review, capture measurement, bound-run and job-type catalogue routes.
4. Tests (section 11), dated receipts and the admission evidence receipts root
   needs to admit the three new `web_job` adapters (section 13).

Out of scope (not claimed): `/runs/[id]`, `/runs/[id]/compare`,
`/runs/[id]/review`, `/runs/[id]/deliver`, `/jobs` index and `/tools` (other
lanes / later priority); hosting, Cloudflare Access/tsidp (auth_hosting lane);
any new DSP, filter, profile or default; admitting a web adapter in
`program/capabilities.json` (root); resumable uploads; level-matched A/B
(`tone_ab`, compare route); listening, musical or note-correctness verdicts;
memory/CPU quotas; exactly-once execution; SLOs; real-take processing in tests.

## 2. Owned files

| Path | Role |
| --- | --- |
| `web/src/routes/upload/` | Upload route (kept) |
| `web/src/routes/sources/` | `[id=artifactid]/+page*`, `capture/+page*`, `process/+page*` (loads and form actions) |
| `web/src/lib/components/processing/` | Capture interval picker, stats panel, preset/knob groups, refusal surfaces, span audition |
| `web/src/lib/server/processing/` | Lane-local control calls, closed Effect 4 Schema decoders for the widened job union, pure option/refusal builders (node-importable, no I/O) |
| `scripts/web_jobs.py` | Allowlist, adapters, capture reviews, schema v2, host media lock |
| `scripts/web_api.py` | New `/api/v1` routes and widened submission |
| `tests/test_web_jobs.py` | Existing S2 lifecycle suite, adjusted only where the allowlist changes an assertion |
| `tests/test_web_processing_s3.py` | New lane suite |
| `docs/spec/sprints/ROUTES_PROCESSING_S3.md` | This contract |
| `docs/agent-notes/sprints/20261007-s3/routes_processing-*.json` | Receipts (contract, tests, build, admission evidence, demo) |

Generated outputs go only under
`.local/sprint3/routes_processing/artifacts/s2/routes_processing/` (gitignored).
Not owned and not edited: `web/src/lib/schema/control.ts`,
`web/src/lib/server/control-client.ts`, `web/src/lib/server/job-request.ts`,
`web/src/routes/api/**`, `web/src/routes/jobs/**`, `/compare`, `/download`,
every root-owned file. Needed changes there are section 13 requests.

## 3. Reused modules (import only)

- `tool_api`: `descriptor(name)`, `validate(args, schema)`,
  `validate_tool_arguments(name, args)`, `worker_command(name, args)`,
  `classify_share_export_result`, `MAX_WORKER_OUTPUT`. The supervisor keeps
  launching the exact `worker_command` argv itself (new session, owned process
  group), never `run_worker` and never a shell.
- `artifact_ids`: `ArtifactIndex.project/resolve/project_source`,
  `check_run_id`, `ARTIFACT_ID`, `SOURCE_ID`. Run outputs are exposed only as
  `art_` IDs and run IDs, never paths.
- `scripts/capture_profile.py` `REVIEW_KEYS` and enumerations are read as the
  review schema source of truth (the web record is a strict subset mapping,
  section 7.2); `profiles/fuller.json` is read for the FULLER preset.
- Existing BFF pieces: `config.ts`, `http.ts`, `control-client.ts` exports
  (`runControl`, `makeBffError`, `toBffError`, `listSources`, `getJob`),
  `idempotency.ts`, `JobStateBadge`, `ControlApiError`, `UnknownValue`,
  `UnknownsBlock`, `ArtifactTable`.

## 4. Route contract (UI)

All pages are server-loaded through the control API; no browser path input
exists anywhere. Draft knob state is local; nothing renders until an explicit
submit. Every submit carries a fresh `ui-<32 hex>` idempotency key; reload
replays rather than duplicates.

| Route | Shows | Primary actions | Must never |
| --- | --- | --- | --- |
| `/upload` | Existing S2 upload (configured byte limit, local-only statement, partial vs accepted) | Upload / admit | Change upload semantics |
| `/sources/[id]` | Source identity (`art_`, `src_`, sha256 prefix, bytes), probe summary fields (duration/rate/channels from bound run manifests or worker proof, else **Unknown** + reason), bound runs (run ID, kind: baseline/candidate, profile, created), capture reviews (status, interval, contamination fields), jobs (type, state, phase, links to `/jobs/[id]`), step links Capture / Process | Open capture, open process | Show a host path; call a stale/missing source current |
| `/sources/[id]/capture` | Baseline run selector (runs whose manifest source sha256 equals this source); native timeline of that run; **empty initial selection**; numeric start/end inputs (seconds, 3 decimals; keyboard operable) plus span loop on the baseline `source.wav` player; measured interval statistics (section 7.4) after an explicit **Measure interval**; contamination fields (music, clicks, ambient music; default `unknown` / `not_reported`); a visible setup-interval warning when the selection overlaps 0-5 s; review status; authorization scope choice | **Measure interval** (no write), **Save review** (creates an immutable review record), **Author profile** (submits `capture_profile` against a saved review) | Prefill, suggest or auto-save an interval; promote a 0-5 s selection to `reviewed_candidate`; claim noise-only |
| `/sources/[id]/process` | Preset choice (FULLER default; conservative3 explicit; mild6/bypass explicit; captured* only if source sha matches their bound sha; fuller-shelf per section 8.2), knob groups Cleanup / Tone / Dynamics / Delivery loudness with schema bounds and FULLER values shown as the preset values, render scope, refusal panel, completed candidates with span audition | **Render full take** (FULLER: `capture_profile` then `apply_capture_profile`; conservative3: `denoise`), cancel/retry via job links | Offer a high-pass, low-cut or notch control; render on knob change; submit FULLER without a reviewed interval; call any output listening-accepted or adopted |

`/compare` and `/download` prototype stubs stay in place unless the
routes_review lane lands their replacements (`/runs/[id]/compare`,
`/runs/[id]/deliver`) before this lane's merge; this lane then removes only the
two stub directories and their nav entries, recorded in the merge receipt.

## 5. Control API additions (`scripts/web_api.py`)

Same loopback bind, Host/Origin checks, bearer token, 16 KiB body bound,
strict JSON (duplicate keys / non-finite refused), closed bodies and typed
`{status:'error', code, error}` refusals without host paths or stderr.

| Method and path | Body / query | Result |
| --- | --- | --- |
| `GET /api/v1/job-types` | none | Closed catalogue: per job type, tool name, admission state (`admitted` / `pending_root_admission`), knob specs copied from the live `tool_api` descriptor (type, min, max, enum, default, description), web-only constraints, timeout bounds, resource class |
| `GET /api/v1/sources/{id}/runs` | none | Runs under `artifacts/runs` whose `manifest.json` source sha256 equals the admitted source: run ID, role (`baseline` = has `source.wav` + `pcm`; `capture_candidate` = has `application-receipt.json`), profile name, PCM rate/channels/sample count/duration, output `art_` IDs; no paths |
| `POST /api/v1/sources/{id}/capture-measurements` | `{run_id, start_seconds, end_seconds}` | Section 7.4 statistics; writes nothing |
| `GET /api/v1/sources/{id}/capture-reviews` | none | Review records for this source (section 7) |
| `POST /api/v1/sources/{id}/capture-reviews` | Section 7.2 | 201 new record, 200 identical replay (same idempotency key + same fingerprint), 409 conflict |
| `POST /api/v1/jobs` | Section 6.2 per type | 202 new, 200 replay, typed refusal |
| `GET /api/v1/runs/{run_id}/media/{role}` | role in `source`, `denoised`, `cleaned`, `processed`, `residue` | Re-hashed WAV bytes for span audition when the run is bound to an admitted source; else typed refusal |

Existing routes are unchanged in path and shape for `share_export` jobs.

## 6. Job-type allowlist (`scripts/web_jobs.py`)

### 6.1 Allowlist and gating

`JOB_TYPES` is a closed, frozen mapping. A submission whose `tool` is not a
key is refused `tool_not_admitted` (400), including all 36 other registered
tools and any unknown string. A key is **runnable** only when
`program/capabilities.json` lists its `adapters.web_job` as `admitted`
(currently only `share_export`); otherwise the submission is refused
`tool_pending_admission` (409) with the capability state, and the UI shows
"pending root admission". Tests exercise the three pending types through an
explicit constructor seam `admitted_tools=` that is test-only (refused unless
`command_builder` is also a test stub), so the product never self-admits.

| Job type | Tool | Web body (besides `tool`, `idempotency_key`) | Server-derived tool args | Timeout bounds (descriptor) | Resource class | Preconditions (typed refusal) |
| --- | --- | --- | --- | --- | --- | --- |
| `share_export` | `share_export` | `source_artifact_id`, `parameters{height,crf,audio_kbps,codec,timeout_seconds}` | unchanged from S2 | 30..900, default 900 | media | unchanged |
| `denoise` | `denoise` | `source_artifact_id`, `parameters{profile,timeout_seconds}` | `input` = re-hashed admitted source path | 1..900, default 600 | media | `profile` in descriptor enum; captured* refused `profile_source_mismatch` when source sha256 differs from the preset's bound sha (web-only, earlier than the worker's own refusal) |
| `capture_profile` | `capture_profile` | `source_artifact_id`, `capture_review_id`, `parameters{preset, reduction_db, noise_floor_db, adaptivity, gain_smooth, integrated_lufs, true_peak_dbtp, peaking_eq?, compressor?, timeout_seconds}` | `input` = source path, `run_dir` = review's baseline run, `review` = review file path, `capture_start_seconds`/`capture_end_seconds` = review interval (never from the body) | 1..60, default 60 | analysis (light; still serialized) | review exists, current, bound (section 7.3), status not `rejected_contaminated`; `preset:'fuller'` forbids any explicit control (expanded exactly from `profiles/fuller.json`); `preset:'custom'` requires every required control |
| `apply_capture_profile` | `apply_capture_profile` | `source_artifact_id`, `capture_profile_job_id`, `parameters{timeout_seconds}` | `input` = source path, `authoring_dir` and `receipt_sha256` read from that job's fenced publication | 12..600, default 600 | media | parent job `succeeded`, same source, published status `authored_unrendered`, review scope `experimental_capture_render`; else `capture_interval_required` / `authoring_not_renderable` |

Every derived argument dictionary passes `tool_api.validate(args,
descriptor.inputSchema)` and `tool_api.validate_tool_arguments` at submit
(refusal `invalid_parameters`, field named, value not echoed beyond 200
characters) and again before launch (`launch_refused`). Web-only constraints
are listed in the catalogue and counted separately in M2.

### 6.2 Lifecycle invariants kept

Idempotency fingerprint = canonical
`{tool, source_artifact_id, source_sha256, parameters(expanded), bound
inputs (review id + review sha256 | parent job id + receipt sha256),
capability_revision(tool)}`; replay 200, conflict 409. Cancel (queued ->
cancelled, running -> owned process-group stop), interrupted/failed -> explicit
retry as attempt n+1, startup reconciliation (dead / alive_unowned / unknown;
never signal an unowned process), fenced atomic publication with the
`after_publish_before_commit` fault seam, queue limit, and path-free
projections are unchanged and must hold for every type.

`capability_revision(tool)` = sha256 of the tool descriptor plus the worker
script(s) (`share_export.py`; `media.py`; `capture_profile.py` + `media.py`;
`apply_capture_profile.py` + `capture_application_adapter.py` + `media.py`).

Outer deadline = `parameters.timeout_seconds + 10 s` for every type
(`OUTER_HEADROOM_S`), enforced by the supervisor independent of the worker.

### 6.3 Publication per type

`share_export` keeps the S2 private per-job directory. The other three tools
write where their workers write (`denoise` and `apply_capture_profile`: a fresh
run under `artifacts/runs/`; `capture_profile`: `<baseline run>/capture-profiles/<id>/`).
The job never copies media; it publishes a fenced `publication.json` in the
private job directory recording run ID, output roles with `art_` IDs, sha256
and bytes (re-hashed after the worker exits and checked against the worker's
own manifest/receipt), worker status, and `master_adopted:false`,
`listening_accepted:false`. A worker result naming a run outside
`artifacts/runs`, a symlink, a hash mismatch or a non-fresh directory fails
`publication_failed` and nothing is projected as an artifact.

### 6.4 Schema v2 and one active media job per host

`PRAGMA user_version = 2`: adds `capture_reviews` (append-only, triggers refuse
UPDATE/DELETE), `jobs.bound_input_json`, and widens the tool CHECK to the
allowlist. A v1 database is migrated forward once inside one transaction under
the state-root lock (receipt event `schema_migrated_1_2`); any other version is
refused `schema_version_mismatch`. One supervisor thread runs at most one
attempt at a time per state root; in addition a host-wide advisory `flock` on
`<state-root parent>/.host-media.lock` (path injectable for tests) is held for
the life of every media-class attempt, so two state roots on one host never
run media jobs concurrently. Waiting for the host lock leaves the job `queued`
with phase `waiting_host_media_slot`.

## 7. Capture review contract

### 7.1 Principles

The interval is chosen by the operator on the baseline run's native timeline
(`decoded_source_audio_samples`), bound to the source sha256 and to the
baseline run's manifest and PCM sha256. Nothing in the server or UI creates,
proposes or prefills an interval. The FULLER accepted interval (4.10-4.95 s on
source `a522115f4e72…`) is history, not a default for any source.

### 7.2 Request (closed body)

`{idempotency_key, run_id, expected_source_sha256, start_seconds, end_seconds,
review_status, authorization_scope, music_status, click_status,
ambient_music_status, note, setup_interval_acknowledged}`.
Enumerations are exactly `capture_profile.py`'s. `selected_by` and
`reviewed_by` are fixed by the server to `operator via loopback browser
(unauthenticated assertion)`; `authorization_reference` is server-generated
from the review ID. The client never supplies a hash other than
`expected_source_sha256` (staleness check) and never a path.

### 7.3 Binding and refusals

The server computes source, manifest and `source.wav` sha256 at write time,
writes the review JSON create-only (`O_EXCL`, fsync, at most 16 KiB) as
`<baseline run>/web-capture-reviews/<review_id>.json` with exactly
`REVIEW_KEYS`, and records `{review_id, source_artifact_id, source_sha256,
run_id, manifest_sha256, pcm_sha256, review_sha256, interval, statuses,
overlaps_setup_interval, created_at}` in `capture_reviews`. Refusals:
`source_stale` (expected or current sha256 differs), `run_not_bound` (run
manifest source sha256 differs), `run_not_baseline` (no bounded regular
`manifest.json` + `source.wav`), `interval_out_of_range` (outside native
extent or duration outside 0.1-10 s), `setup_interval_unacknowledged`
(overlaps [0, 5) s without `setup_interval_acknowledged:true`),
`setup_interval_status_refused` (overlaps [0, 5) s with `review_status:
reviewed_candidate`; allowed statuses there are
`reviewed_possible_contamination` and `rejected_contaminated`),
`review_stale` (at job submit: any recorded hash no longer matches).

### 7.4 Measured interval statistics (claim class: measurement of the mixture)

Computed by stdlib code over at most 10 s of the baseline `source.wav`
(PCM s16/s24/s32/f32, parsed from the RIFF header; other formats refused
`pcm_format_unsupported`), per channel: sample peak dBFS (not true peak), RMS
dBFS, 100 ms frame RMS min/median/max dBFS and their spread, count of frames
more than 6 dB above the interval median (`transient_frames`, labelled a
**possible attack/windup indicator**, an inference), clipped sample count
(|x| >= 0.999 FS), frame count denominator. Also reported when present: the
run's existing `noise.json` fields, only if bound to the same source sha256.
Always null with reasons: `noise_only`, `fan_band_energy`,
`music_or_click_presence`, `low_register_content_hz_32`. No statistic
selects, ranks or confirms an interval.

## 8. Process contract

### 8.1 Presets

| Preset | Job path | Interval | Controls |
| --- | --- | --- | --- |
| FULLER (default selection) | `capture_profile` (preset `fuller`) then `apply_capture_profile` | Required: a saved, current review with scope `experimental_capture_render`; without it the render action is disabled with `capture_interval_required` and the server refuses the same code | Verbatim `profiles/fuller.json`: reduction 8 dB, floor -40 dB, adaptivity 0, gain_smooth 0, peaking EQ 160 Hz +2 dB Q 0.7 and 300 Hz +1 dB Q 0.8, compressor -18 dB / 2:1 / 15 ms / 100 ms / 3 dB knee, -18 LUFS / -1.75 dBTP. Listening acceptance covers only the identical chain on source `a522115f4e72` with samples [180810, 218295); every other take/interval shows `listening_acceptance: not_performed` |
| conservative3 (explicit) | `denoise` profile `conservative3` | None | Fixed profile, no knobs except timeout |
| mild6, bypass (explicit) | `denoise` | None | Fixed |
| custom capture | `capture_profile` preset `custom` then apply | Required (as FULLER) | Every control explicit within schema bounds |
| captured8/12/8-clarity | `denoise` | Bound to source `a522115f…` only | Shown unavailable with reason for any other source |

### 8.2 Bounded shelf

The ruling allows one boost-only low shelf (80-160 Hz, 0..+2 dB, Q 0.5-0.707)
as an explicit optional profile; FULLER stays the default. At baseline neither
the `denoise` profile enum nor the `capture_profile` schema exposes
`low_shelf`, so the UI shows **Fuller + low shelf: unavailable — no typed tool
exposes the shelf** and submits nothing. If root merges a typed exposure
before this lane's freeze, the option appears with bounds read from that
schema, never as the default, labelled `unreviewed_trial`.

### 8.3 Knob groups, render scope and audition

Knob groups and bounds come from `GET /api/v1/job-types` (live descriptors):
Cleanup (`reduction_db` 0.01..12, `noise_floor_db` -80..-20, `adaptivity`
0..1, `gain_smooth` 0..50), Tone (`peaking_eq` <= 3 bands, 160..6000 Hz,
-3..+3 dB, Q 0.5..2), Dynamics (`compressor` all-or-none), Delivery
loudness (`integrated_lufs` -70..-5, `true_peak_dbtp` -9..0). There is no
high-pass, low-cut or notch control anywhere and none can be sent (closed
bodies). The UI never clamps; out-of-range values return typed refusals.
Render scope: the admitted tools render the **full take** only (no typed
interval argument). "Preview" is a span audition: loop the same source-time
span on the source and a completed candidate's `cleaned`/`denoised`/`residue`
players; it is labelled **not level-matched** (matched A/B belongs to
`/runs/[id]/compare`). A bounded preview-render job is a section 13 request,
not built here.

## 9. Unknown fields the outputs must carry

Every processing job projection and publication, every capture review and
measurement response carries these keys with value `null` and a reason
string (never omitted, never defaulted):

| Field | Reason (fixed text family) |
| --- | --- |
| `listening_acceptance` | operator listening not performed for this version |
| `master_adopted` | always `false` (boolean, not null): the lane never adopts |
| `low_register_preservation` | ~32 Hz content not measured by a job service |
| `capture_noise_only` | the reviewed interval is not verified noise-only |
| `music_or_click_presence` | operator assertion only unless reviewed_present |
| `fuller_listening_transfer` | FULLER acceptance covers one source/interval only |
| `musical_review` | no note-correctness, missed-note or phrase verdict |
| `level_matched` | span audition is not level-matched |
| `memory_bytes_peak`, `cpu_seconds` | not measured; no OS quota |
| `probe_duration_seconds` (overview) | unknown until a bound run manifest or worker proof exists |

## 10. Completion metrics

Claim classes: **contract** (deterministic test of code behaviour),
**measurement** (computed number with stated denominator), **build** (tool
exit status), **listening** (not performed by this lane; always reported
`not_performed`).

| ID | Metric | Denominator | Target | Class |
| --- | --- | --- | --- | --- |
| M1 | Allowlist closure: non-allowlisted registry tools + 3 synthetic names refused `tool_not_admitted`; allowlisted-but-unadmitted refused `tool_pending_admission` | 36 + 3 = 39 names; 3 pending types | 39/39; 3/3 | contract |
| M2 | Validation parity: per type, fixed vector table (each knob at min, max, below min, above max, wrong JSON type, non-finite, plus one extra knob, plus omitted required) — web accept/refuse equals `tool_api.validate` + `validate_tool_arguments` on the derived args | Vectors per type counted at test time and reported per type | 100% agreement; web-only stricter refusals listed and counted separately | contract |
| M3 | Unknown knob refusal per type | 4 types | 4/4 | contract |
| M4 | Capture binding refusals: source bytes changed, baseline manifest changed, `source.wav` changed, review file changed, run of another source | 5 mutations | 5/5 refused, store unchanged | contract |
| M5a | No auto-confirmation: capture reviews count after every GET/load path on a fresh source | All GET routes + capture/process page loads (counted) | 0 records created | contract |
| M5b | Setup-interval rule over a deterministic grid of intervals (start 0.0..9.9 s step 0.3, durations 0.1/0.85/3.0 s, statuses x acknowledgement) | Grid size reported (102 intervals x 3 statuses x 2 ack) | 100% of 0-5 s overlaps require ack and refuse `reviewed_candidate`; 100% of non-overlapping intervals do not | contract |
| M6 | FULLER without interval: server `capture_interval_required` and UI option builder returns disabled + same code; with a valid review, enabled | 2 states x (server, UI builder) | 4/4 | contract |
| M7 | FULLER preset fidelity: expanded controls equal `profiles/fuller.json`; `media.post_denoise_filters(FULLER controls, 44100)` vs accepted run `20261006T041633Z-990aa1bd6737` applied-profile stages (read-only) | 11 control fields; 1 chain comparison | 11/11; chain equality reported as `equal` / `differs` with diff (either is a valid outcome) | contract / measurement |
| M8 | Lifecycle per type: replay, conflict, cancel queued, cancel running (owned group gone), interrupted -> retry, publish-crash adoption, deadline -> `deadline_exceeded` | 7 cases x 4 types = 28 | 28/28 | contract |
| M9 | One active media job per host: two `WebJobs` instances on separate state roots sharing the host lock, 6 media jobs | Overlapping-run intervals observed | 0 overlaps | measurement |
| M10 | Path hygiene: response bodies scanned for repository root, state root, `/Users/`, run directory paths | All responses produced in the suite (counted) | 0 hits | contract |
| M11 | Low-end doctrine: exposed knobs / presets containing high-pass, low-cut, notch or a shelf default | All catalogue knobs and preset expansions | 0 | contract |
| M12 | Unknown fields present with reason on every projection type | 4 types x 10 fields + review + measurement | 100% | contract |
| M13 | Existing S2 suites still pass: `test_web_jobs`, `test_web_parity`, `test_web_stack`, `test_web_reliability` | Test counts reported per module, skips listed with reasons | 0 failures; skips are not passes | contract |
| M14 | `pnpm install --offline --frozen-lockfile`, `pnpm check`, `pnpm build` in `web/` | 3 commands | exit 0; svelte-check errors 0 (warnings reported) | build |
| M15 | Stats correctness on analytic fixtures (section 11.2): RMS/peak within 0.01 dB, clip and transient counts exact | Fixtures x channels (counted) | 100% | measurement |
| M16 | Listening, low-register, musical claims | — | `not_performed` / null everywhere | listening |

Experimental non-improvement or a `differs` result in M7 is valid completion.
Admission of the three new adapters is root's decision; the lane's completion
is the evidence receipts, not the admission.

## 11. Test protocol

### 11.1 Commands (from the worktree root)

```
export FFMPEG=/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffmpeg
export FFPROBE=/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffprobe
PYTHONPATH=tests python3 -m unittest test_web_processing_s3 -v
PYTHONPATH=tests python3 -m unittest test_web_jobs test_web_parity test_web_stack test_web_reliability -v
(cd web && pnpm install --offline --frozen-lockfile && pnpm check && pnpm build)
```

One heavy FFmpeg job at a time; every subprocess in tests has an explicit
timeout. The full suite is root's.

### 11.2 Fixtures (synthetic only; the real take is never opened)

- **Source video**: the existing `test_web_jobs` synthetic source helpers
  (deterministic, FFmpeg-generated, skipped with reason when FFmpeg is unset).
- **Baseline run fixture** `make_baseline_run(rate, channels, fmt, seconds,
  seed=20261007)`: `manifest.json` with `source`, `outputs`, `output_sha256`,
  `timeline`, `pcm` provenance objects and a RIFF `source.wav` built in Python:
  0-5 s setup segment (decaying 32.703 Hz + 65.4 Hz tone bursts and a click
  train standing in for amp/windup), 5-8 s stationary seeded LCG noise at
  -42 dBFS RMS, 8-12 s 32.703 Hz sine at -12 dBFS (analytic RMS), one
  full-scale clip burst at a known sample range. Formats f32 and s16; mono and
  stereo.
- **Run placement**: fixtures live in a per-test temporary runs root for
  path-independent tests; tests that must satisfy `capture_profile.py`'s
  `ROOT/artifacts/runs` confinement create `artifacts/runs/web-s3-fixture-<hex>/`
  inside this worktree only and remove it in `tearDown` (never the main
  checkout, never an existing run).
- **Workers**: lifecycle tests use the existing `command_builder` stub seam
  (sleep / exit / emit-result scripts); real-worker cases for `denoise`
  (bypass, 3 s fixture) and `capture_profile` (authoring only) run once each
  when FFmpeg is set; `apply_capture_profile` real render runs once on the
  synthetic fixture when FFmpeg is set, else skipped with reason.

### 11.3 `tests/test_web_processing_s3.py` cases

`AllowlistTests` (M1, M3, M11): closed catalogue, pending-admission refusal,
test seam refusal without stub. `ParityTests` (M2): generated vector tables
per type against `tool_api`. `CaptureReviewTests` (M4, M5a, M5b, M10, M12):
binding, setup-interval grid, create-only file, replay/conflict, no auto
records. `CaptureStatsTests` (M15). `ProcessTests` (M6, M7): FULLER refusal
server + node-run pure option builder from
`web/src/lib/server/processing/` (node type stripping; skipped with reason
when node is absent), preset expansion, chain comparison. `LifecycleTests`
(M8, M9). `SchemaMigrationTests`: v1 store migrates once, v3 refused,
existing v1 share_export jobs remain readable and retryable.
`tests/test_web_jobs.py`: only assertions that encoded "only share_export" are
updated to the allowlist semantics; every other S2 test stays unchanged.

## 12. Experiment / preregistration

This lane runs **no experiment**: no arms, no scoring against truth, no
held-out data, no tuning. M7's chain comparison and M15's statistics are
deterministic checks against fixed inputs. `preregistered: false`.

## 13. Root-owned changes requested (not made by this lane)

1. `scripts/capabilities.py` `WEB_JOB_ADMISSIONS` add
   `'denoise'`, `'capture_profile'`, `'apply_capture_profile'` ->
   `docs/agent-notes/sprints/20261007-s3/routes_processing-web-job-<tool>.json`
   (evidence receipts written by this lane in phase 3), and
   `program/capabilities.json` `adapters.web_job` `planned` -> `admitted` for
   those three, at root's discretion.
2. `web/src/lib/schema/control.ts`: widen `tool` to the four-literal union,
   `parameters` to a per-tool union, `worker_kind` to the new worker kinds, add
   optional `bound_input` — otherwise the shared `/jobs/[id]` and job listing
   decoders refuse non-share jobs (closed decode). Exact diff delivered in
   phase 2 results; until merged, owned routes use the lane's own decoders.
3. `web/src/lib/server/control-client.ts`: export `requestJson` and
   `decodeWith` so the lane module need not duplicate the transport.
4. `web/src/routes/api/jobs/+server.ts` and `lib/server/job-request.ts`:
   accept the closed union (only needed if root prefers the JSON endpoint over
   the lane's form actions).
5. Follow-ups for root's backlog, not this sprint: typed `low_shelf` exposure
   on `capture_profile` per the ruling; a bounded preview-render tool with a
   typed interval argument; `just/workflow.just` recipe text if the serve
   entrypoint gains flags.

## 14. Phases

Phase 1 (this commit): contract only, no numerics. Phase 2: web_jobs/web_api
allowlist, capture reviews, schema v2, host lock, tests M1-M13, M15. Phase 3:
routes and components, pnpm check/build (M14), admission evidence receipts,
synthetic walkthrough receipt. Risks: shared decoder strictness (request 2);
`capture_profile` confinement to `ROOT/artifacts/runs` (fixture placement
above); eq_shelf merge timing (section 8.2).

## 15. Phase 2 implementation record (2026-10-07)

Implemented on `sprint/20261007-s3/routes_processing` (contract phases 2 and 3
together). Receipts: `docs/agent-notes/sprints/20261007-s3/routes_processing-*.json`.
Sections 1-14 above stay the frozen contract; this section records what was
built, what differs, and why. Claim classes as in section 10.

### 15.1 Built

- `scripts/web_jobs.py`: closed `JOB_TYPES` allowlist (frozen mapping) with
  per-type resource class, closed parameter keys, bound field, worker scripts
  for `capability_revision(tool)` and listed web-only constraints; admission
  gate read from `program/capabilities.json` (`tool_pending_admission`, 409);
  test-only `admitted_tools=` seam refused without a stub `command_builder`;
  schema v2 (`jobs.bound_input_json`, append-only `capture_reviews` with
  DB-level CHECKs for the first-five-seconds rule, tool allowlist/immutable
  triggers) and a one-time v1 -> v2 migration (`schema_migrated_1_2` in `meta`
  and `events`); host media lock `<state-root parent>/.host-media.lock`
  (injectable) with queued phase `waiting_host_media_slot`; capture review
  create/list, bound-run listing, interval measurement, run media and the job
  type catalogue.
- `scripts/web_api.py`: the six section-5 routes; `POST /api/v1/jobs` accepts
  the allowlist; per-tool `tool_envelope`; processing job rows in
  `GET /api/v1/jobs` add `tool` and `bound_input` (share_export rows unchanged).
- Web (`web/`): `/sources/[id]` overview (identity, probe summary from bound run
  manifests or Unknown, bound runs, reviews, jobs of every type with phase),
  `/sources/[id]/capture` (baseline run selector, empty interval, native
  timeline, span loop on the baseline `source.wav`, Measure / Save review /
  Author FULLER actions), `/sources/[id]/process` (preset choice from the pure
  `options.ts` builder, knob groups with bounds from the live catalogue, author
  -> render steps, conservative3/mild6/bypass, captured* only for their source,
  shelf unavailable, span audition labelled not level-matched),
  `/sources/[id]/runs/[run]/media/[role]` BFF media proxy. Lane-local closed
  Effect 4 decoders and transport under `lib/server/processing/`.
  `/compare` and `/download` stubs were left in place (routes_review has not
  landed replacements in this worktree).

### 15.2 Deviations from sections 1-14 (all recorded, none silently)

1. **apply_capture_profile launch path.** `tool_api.worker_command` has no
   `apply_capture_profile` branch (it raises `tool has no allowlisted worker`;
   `tool_api.execute` runs `ApplicationAdapter` in-process). The supervisor
   launches `python scripts/tool_api.py run apply_capture_profile --arguments
   <canonical json>` (fixed argv, no shell) in its owned process group; the
   worker the adapter starts runs in its own session, so cancel/deadline signals
   stop the adapter but the worker is bounded by its own inner deadline
   (outer - 10 s). Recorded as a limitation, not containment.
2. **Real apply render not run in this worktree.**
   `tool_api.validate_tool_arguments('apply_capture_profile')` refuses any path
   component starting with `.`; this worktree lives under `.local/`, so the
   real-worker apply case skips with that reason. Root's run from the main
   checkout covers it (2026-10-07: succeeded on the synthetic fixture,
   `docs/agent-notes/sprints/20261007-s3/root-real-worker-check.json`; the
   `apply_capture_profile` web_job adapter is admitted on that receipt). Stub
   lifecycle cases (M8) cover apply fully.
3. **Form actions need `ORIGIN`.** adapter-node reports an `https://` app origin
   unless `ORIGIN` is set, so SvelteKit's CSRF check refuses every form POST
   (403) under the current `serve.js` / `just web-serve`. Pages show
   `data-origin-warning` in that state; the walkthrough sets
   `ORIGIN=http://127.0.0.1:<port>`. Root request: default `ORIGIN` in
   `serve.js` (section 15.4).
4. **share_export shape kept.** share_export projections and job rows keep the
   exact S2 shape (S2 suites assert it), so M12 covers the three processing
   types plus review and measurement; share_export keeps the S2 unknown block.
5. **M7 field count.** `profiles/fuller.json` has 13 control fields counted as
   6 scalars + 2 EQ bands + 5 compressor fields (the contract's "11" undercounted).
6. **Capture page "Author" is FULLER only**; custom controls live on the
   process page. Web authoring requires scope `experimental_capture_render`
   (authoring-only drafts are refused `capture_interval_required` with
   `detail_code: review_scope_authoring_only`).
7. **Host lock scope.** "Host-wide" holds for state roots that share a parent
   directory (the default lock path); unrelated parents need the injected path.

### 15.3 Results (measurement / contract / build; listening not performed)

See the tests and build receipts for denominators. Summary at commit time:
M1 39/39 and 3/3; M2 parity 130/130 general vectors (7 web-only stricter
vectors counted separately); M3 4/4; M4 5/5 store unchanged; M5a 0 reviews
after 7 API routes and 3 built-app page loads; M5b 612/612, 0 violations;
M6 4/4; M7 13/13 fields, chain `equal` against the accepted run (read only);
M8 28/28; M9 0 overlaps across 6 media jobs on 2 state roots; M10 0 leaks over
every scanned response; M11 0 hits; M12 50/50; M15 57/57; M16 listening,
low-register and musical claims `not_performed` / null. Real workers:
denoise (bypass) and capture_profile (FULLER authoring) succeeded on a
synthetic 7 s fixture; apply skipped (15.2.2).

### 15.4 Root-owned requests

Listed with exact text in the lane result and in
`docs/agent-notes/sprints/20261007-s3/routes_processing-root-requests.json`:
WEB_JOB_ADMISSIONS + `capabilities.json` admissions (root's decision),
`control.ts` widening (type-checked and decode-tested candidate),
`control-client.ts` exports, `serve.js` ORIGIN default, and backlog items
(typed `low_shelf`, bounded preview-render tool, apply path rule).
