# S2 web_jobs lane contract: bounded durable local job service over artifact IDs

Status: **Phase 1 contract freeze**, 2026-10-06. Lane `web_jobs`, workflow D,
wave 2, branch `sprint/20261006-s2/web_jobs`, worktree `.local/sprint2/web_jobs`.
Tracker: Linear TIN-5614 (related TIN-5550 JOBS / WEB-2). Baseline:
`e0da4ca04930ee9a89a83eec402f060366c5d30d`. Authority: S2 sprint manifest
`program/sprints/20261006-s2.json`, repository `AGENTS.md`,
R-HOOK-CONVERGENCE-20261004 / R-N11/R-N12/R-N13 (TIN-3692 comment
98cf680c-7299-4949-bfb2-60079053ad43). Root administers review, signed merge,
recipes, admission, publication and Linear. This lane never pushes, merges,
writes Linear, edits root-owned files, downloads models or starts a daemon.

Design sources reused, not re-decided: [WEB_BACKEND](../future/WEB_BACKEND.md)
(BFF + small control API + bounded workers over the validated dispatcher; one
operator, one host, SQLite, private filesystem; job protocol, idempotency, SLO
targets), [research note](../../research/2026-10-06-future-web-backend.md),
`docs/spec/future/linear-ready-tickets.json` row `JOBS`,
[CAP_IDS_S2](CAP_IDS_S2.md) / [CAPABILITIES](../CAPABILITIES.md)
(`scripts/artifact_ids.py`), `scripts/tool_api.py` (import only),
`scripts/review_server.py` (loopback/Host-check pattern, read only),
[SHARE_EXPORT](../SHARE_EXPORT.md) (`scripts/share_export.py`).

## 1. Scope

In scope:

1. `scripts/web_jobs.py`: durable SQLite job store (WAL, `PRAGMA user_version`
   schema version 1) plus one in-process supervisor that executes **exactly one
   admitted job type**, `share_export` (a short preview/sharing MP4), through
   `tool_api`'s validated dispatcher, timeout-bounded, with process-group
   termination on cancel. Sources and outputs are addressed only by opaque IDs.
2. `scripts/web_api.py`: stdlib `http.server.ThreadingHTTPServer` control API
   bound to `127.0.0.1` with Host/Origin checks and a per-start bearer token:
   `POST /sources`, `POST /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`,
   `POST /jobs/{id}/retry`, `GET /artifacts/{id}`. This is the contract the
   future SvelteKit BFF calls; FastAPI is documented as a later drop-in with the
   same routes, bodies and codes (section 4.6). FastAPI is not installed and is
   not added.
3. `tests/test_web_jobs.py` (section 8) and lane receipts
   `docs/agent-notes/sprints/20261006-s2/web_jobs-*.json`.

Out of scope (not claimed): uploads/multipart bytes (sources are existing files
under `artifacts/runs`); any other tool (probe, denoise, analysis, export);
SSE/event streams (`GET /jobs/{id}/events`), `validating`/`finalizing`/
`cancelling`/`needs_reconciliation` states from WEB_BACKEND (collapsed, see
section 5); multi-user identity, TLS, CSRF beyond the token, remote hosting,
retention/deletion; HTTP byte ranges; OS memory/disk/RSS quotas; exactly-once
execution; any SLO claim; edits to `tool_api.py`, `tools.json`,
`capabilities.json`, recipes, MCP/review servers; DSP, mastering, default
changes, musical/listening acceptance. No host daemon: the server runs only as
a foreground process the operator starts (recipe text handed to root,
section 11) and tests start/stop it in-process on an ephemeral port.

## 2. Owned files

| File | Role |
| --- | --- |
| `scripts/web_jobs.py` | Store, admission, supervisor, publication, reconciliation, CLI (`status`, `reconcile`) |
| `scripts/web_api.py` | Loopback control API and `serve` foreground entrypoint |
| `tests/test_web_jobs.py` | All lane tests (section 8) |
| `docs/spec/sprints/WEB_JOBS_S2.md` | This contract |
| `docs/agent-notes/sprints/20261006-s2/web_jobs-*.json` | Dated receipts (contract, tests, latency, demo) |

Generated outputs (gitignored, `/artifacts/` is ignored) go only under
`.local/sprint2/web_jobs/artifacts/s2/web_jobs/`. The product default state
root `artifacts/web-jobs/` is used only when the operator runs the server;
lane runs pass an explicit `--state-root` under `artifacts/s2/web_jobs/`.
Nothing is written under `artifacts/runs/*`, `/Users/jess/Documents` or
`/Users/jess/Desktop`.

## 3. Reused modules (import only, never edited)

- `artifact_ids.ArtifactIndex(root, max_bytes)`: `project(selector)`,
  `project_source(run_id)`, `resolve(artifact_id)` (re-hash; only `current`
  exposes a private path). Its refusal codes are mapped to admission reasons.
- `tool_api`: `descriptor('share_export')`, `validate(args, inputSchema)`,
  `validate_tool_arguments`, `worker_command` (fixed allowlisted script and
  argv, never a shell) and `classify_share_export_result`. `tool_api.run_worker`
  is **not** used for execution because it blocks without exposing the PID and
  cannot be cancelled; `web_jobs` launches the exact `worker_command` argv with
  the same discipline (`start_new_session=True`, `cwd=tool_api.ROOT`, stdin
  `/dev/null`, file-backed stdout/stderr, 2 MiB stdout bound, finite strict JSON
  result) and records PID/PGID before any signal can be needed.
- `share_export` worker: itself enforces source ≤3 GiB, duration ≤300 s,
  audio+video, no-clobber publication and `master_adopted=false`,
  `listening_accepted=false`. FFmpeg comes from `FFMPEG`/`FFPROBE` env.

## 4. Interfaces

### 4.1 Store layout (state root `S`, default `<repo>/artifacts/web-jobs`)

```text
S/                          mode 0700, non-symlink, created if absent
S/jobs.sqlite3              WAL, synchronous=FULL, foreign_keys=ON, busy_timeout=5000
S/jobs/<job_id>/            mode 0700, job-private
S/jobs/<job_id>/.staging-<attempt>-<nonce>/   worker output dir (never served)
S/jobs/<job_id>/attempt-<n>/                  published, immutable after rename
    share.mp4, share.mp4.receipt.json, publication.json
```

`runs_root` (where sources live) and `S` are separate constructor arguments:
`WebJobs(runs_root, state_root, *, max_source_bytes=3 GiB, queue_limit=4,
cancel_grace_s=5, command_builder=None, fault=None)`. `command_builder` and
`fault` are test seams, not HTTP-reachable; every attempt records
`worker_kind` (`tool_api_share_export` or `test_stub`) so receipts cannot
conflate stub runs with the real dispatcher.

### 4.2 SQLite schema v1 (`PRAGMA user_version = 1`)

- `meta(key PRIMARY KEY, value)`: `schema_version`, `instance_id` of the
  current process, `created_at`.
- `sources(source_artifact_id PK, selector, sha256, size_bytes, kind, source_id
  NULL, source_binding, admitted_at)`; selector is private, never returned.
- `jobs(job_id PK, idempotency_key UNIQUE, fingerprint, tool, source_artifact_id
  FK, parameters_json, capability_revision, state, reason_code NULL,
  cancel_requested INTEGER, created_at, updated_at)`.
- `attempts(job_id FK, attempt INTEGER, state, fence TEXT, instance_id,
  worker_kind, pid NULL, pgid NULL, worker_birth NULL, started_at, ended_at,
  reason_code NULL, cancel_receipt_json NULL, liveness NULL,
  PRIMARY KEY(job_id, attempt))`.
- `artifacts(artifact_id PK, job_id FK, attempt, role, rel_path, sha256,
  size_bytes, content_type, published_at)`; `rel_path` is relative to `S`.
- `events(seq INTEGER PK AUTOINCREMENT, job_id, attempt, from_state, to_state,
  reason_code, at)`: append-only transition log.
- Triggers: `BEFORE UPDATE OF state` on `jobs` and `attempts` raise `ABORT`
  unless the transition is in the section 5 table; `BEFORE UPDATE`/`DELETE` on
  `artifacts` and `events` raise `ABORT` (immutable rows).

An existing database with a different `user_version` is refused
(`schema_version_mismatch`), never migrated silently.

### 4.3 Identity

- Source: `POST /sources` returns `source_artifact_id` (`art_…` from
  `artifact_ids`) and `source_id` (`src_…` or `null` with
  `source_binding: "unknown"`).
- Job: `job_` + 32 lowercase hex from `secrets.token_hex(16)` (opaque, random).
- Output artifact: `art_` + first 32 hex of
  `sha256("video-utils/web-job-artifact-id/v1\0" + job_id + "\0" + attempt +
  "\0" + role + "\0" + content_sha256)`. Roles: `share_mp4` (`video/mp4`),
  `share_receipt` and `publication` (`application/json`). Distinct domain
  string from `artifact_ids` v1 so the two ID spaces cannot collide by design.
- Request fingerprint: sha256 of canonical JSON (sorted keys, no whitespace) of
  `{tool, source_artifact_id, source_sha256, parameters (defaults filled from
  inputSchema), capability_revision}`, where `capability_revision` = sha256 of
  the canonical `share_export` descriptor JSON + sha256 of
  `scripts/share_export.py` bytes.

### 4.4 Routes (JSON, `Content-Type: application/json`, body ≤16 KiB)

All requests require `Host` ∈ {`127.0.0.1:<port>`, `localhost:<port>`}, an
`Origin` (when present) of `http://127.0.0.1:<port>` or
`http://localhost:<port>`, and `Authorization: Bearer <token>` (32-byte random
per start, printed once to the operator's terminal, compared with
`hmac.compare_digest`). Request bodies are strict finite JSON objects;
duplicate keys and unknown fields are refused. No response contains a host
path, selector, worker stderr or the state root.

| Route | Body | Success | Notable refusals |
| --- | --- | --- | --- |
| `POST /sources` | `{"selector": "<run_id>/…/<file>"}` | `201` new / `200` already admitted: `{source_artifact_id, source_id, source_binding, kind, sha256, size_bytes, state}` | `422` typed admission reason (section 4.5) |
| `POST /jobs` | `{"tool":"share_export","source_artifact_id":"art_…","parameters":{height?,crf?,audio_kbps?,codec?,timeout_seconds?},"idempotency_key":"[A-Za-z0-9._-]{8,128}"}` | `202` new job; `200` + `"replayed": true` same key and fingerprint | `409 idempotency_conflict`; `409 source_stale`/`410 source_missing`; `404 unknown_source`; `400 tool_not_admitted`/`invalid_parameters`; `429 queue_full` |
| `GET /jobs/{id}` | — | `200` job projection (section 6) | `400 malformed_id`, `404 unknown_job` |
| `POST /jobs/{id}/cancel` | `{}` | `202` `cancel_requested` (running), `200` `cancelled` (queued) or terminal no-op with `late_cancel: true` and the actual state | `404 unknown_job` |
| `POST /jobs/{id}/retry` | `{}` | `202` new attempt `n+1` queued; earlier attempt rows and published files unchanged | `409 not_retryable` (only `interrupted`/`failed`), `409 prior_worker_alive`, `409 source_stale` |
| `GET /artifacts/{id}` | — | `200` bytes, `Content-Type`, `Content-Length`, `X-Artifact-Sha256`; re-hashed through the same open descriptor before sending | `400 malformed_id`, `404 unknown_artifact`, `409 artifact_stale`, `410 artifact_missing`, `403 confinement_refused` |

Transport refusals: `403 host_refused`/`origin_refused`, `401 token_required`,
`405 method_not_allowed`, `411`/`413 body_too_large`, `415 content_type`,
`400 malformed_json`/`unknown_field`/`missing_field`/`bad_type`,
`503 shutting_down`. Error body: `{"status":"error","code":…,"error":…}`.

`GET /artifacts/{id}` serves only job-published artifacts from the
`artifacts` table; source artifacts are not downloadable through this API.
Serving opens `S/<rel_path>` with `O_NOFOLLOW`, checks each component under `S`
is a non-symlink directory (by `(st_dev, st_ino)` containment, as in
`artifact_ids.dump`), hashes via the descriptor, compares `fstat` before/after
and only then streams in 1 MiB chunks.

### 4.5 Source admission reasons (typed, HTTP 422 unless noted)

`unknown_field`, `missing_field`, `bad_type` (400), `path_escape` (wraps
`artifact_ids` codes `host_path_refused`, `outside_runs_root`,
`symlink_component`, `unsafe_component`, `filter_string_refused`; the original
code is returned as `detail_code`), `not_regular_file`, `executable_refused`,
`too_large` (> `max_source_bytes`), `not_media` (kind is not `video`, or the
leading bytes lack an ISO-BMFF `ftyp` box at offset 4 for `.mov/.mp4/.m4v`, or
an EBML magic for `.mkv/.webm`), `changed_during_hash`. Admission performs no
FFmpeg probe: duration/stream validity are `unknown` until the worker runs, and
a worker rejection (e.g. duration >300 s, no audio) becomes job
`failed` with `reason_code: worker_rejected` and the worker's bounded code.

### 4.6 FastAPI drop-in (documented, not implemented)

A later `FastAPI` app may replace `web_api.py` by mounting the same six routes
on the same `WebJobs` object, keeping body schemas, status codes, error codes,
Host/Origin/token checks and loopback binding. It must not use
`BackgroundTasks` for execution; the supervisor and SQLite store remain the
single scheduler. Tests in section 8 are written against HTTP, so they serve
as the conformance suite for that swap.

## 5. Job lifecycle

States: `queued`, `running`, `succeeded`, `failed`, `cancelled`,
`interrupted`. Allowed transitions (enforced in Python **and** by SQLite
triggers on both `jobs.state` and `attempts.state`):

| From | To |
| --- | --- |
| `queued` | `running`, `cancelled`, `failed` (source changed before start) |
| `running` | `succeeded`, `failed`, `cancelled`, `interrupted` |
| `interrupted`, `failed` | `queued` on **`jobs` only**, via explicit retry that inserts attempt `n+1` |
| terminal attempt states | none |

Attempt states are strictly monotonic (`queued → running → terminal`);
the only job-level re-entry is the explicit retry row, recorded in `events`.
WEB_BACKEND's `validating`/`finalizing` are recorded as `events` phases inside
`running`; `cancelling` is represented by `cancel_requested=1` while `running`;
`needs_reconciliation` is represented by `interrupted` plus
`liveness ∈ {alive_unowned, unknown}`, which blocks retry.

Supervisor (one thread, one running attempt at a time per state root; at most
`queue_limit=4` queued jobs):

1. Claim the oldest `queued` attempt in one `BEGIN IMMEDIATE` transaction,
   setting `running`, a fresh `fence` (random 128-bit), `instance_id`.
2. Re-resolve the source artifact (re-hash). `stale`/`missing` →
   `failed` (`source_changed`/`source_missing`); no worker launched.
3. Build args `{source: <private path>, output: S/jobs/<id>/.staging-…/share.mp4,
   **parameters}`; run `tool_api.validate` + `validate_tool_arguments` +
   `worker_command`. Popen with a new session; immediately persist
   `pid`, `pgid` (= pid, verified with `os.getpgid`) and `worker_birth`
   (`ps -o lstart= -p PID` text, nullable when unavailable).
4. Wait with the attempt's `timeout_seconds` (+10 s outer headroom; worker
   enforces its own D-10). Poll `cancel_requested` every 100 ms.
5. Cancel: verify `os.getpgid(pid) == recorded pgid == pid`, `killpg(SIGTERM)`,
   wait `cancel_grace_s`, then `killpg(SIGKILL)` if still alive; reap; write a
   cancel receipt (`actor`, `target_ownership`, ruling R-N11, `ack_at`,
   `signal_at`, `observed_stop_at`, `signal_target`, `returncode`); remove the
   job-private staging dir; attempt → `cancelled`. Never signal a PID whose
   PGID does not match.
6. Success: `classify_share_export_result`; verify the staged `share.mp4` and
   receipt exist, are regular, sizes match the worker result and sha256 matches
   the reported `sha256`; write `publication.json` (job_id, attempt, fence,
   artifact rows); fsync; `rename(staging, attempt-<n>)` (same filesystem,
   refuses an existing target); then in one transaction insert `artifacts`
   rows and set `succeeded` **conditional on `state='running' AND fence=?`**.
7. Failure (non-zero exit, malformed result, timeout, domain failure):
   `failed` with typed `reason_code` (`worker_rejected`, `worker_failed`,
   `deadline_exceeded`, `malformed_result`, `publication_failed`); staging dir
   is retained for inspection but never served.

Startup reconciliation (every `WebJobs` construction, before serving):

- For each `running` attempt with `instance_id ≠ current`:
  - `S/jobs/<id>/attempt-<n>/publication.json` exists with matching job,
    attempt and fence and hashes verify → insert missing `artifacts` rows and
    mark `succeeded` with `reconciled_publication: true` (adopt, never
    republish).
  - else the recorded PID is not alive, or alive with a different
    `worker_birth` → `interrupted`, `liveness: dead`.
  - else (same PID and birth alive, or birth unknown and PID alive) →
    `interrupted`, `liveness: alive_unowned` (or `unknown`); **no signal** is
    sent (R-N11: the new process did not create it); retry is refused with
    `prior_worker_alive` until a later reconcile observes it dead.
- `queued` attempts remain queued and run after restart.
- Retry (`POST /jobs/{id}/retry`) inserts attempt `n+1` with a new staging dir
  and publishes to `attempt-<n+1>/`; any earlier `attempt-*` directory and
  staging dir is left byte-identical.

## 6. Public job projection and explicit unknowns

`GET /jobs/{id}` returns (closed): `job_id`, `tool`, `state`, `reason_code`,
`replayed` (only on submit), `source_artifact_id`, `source_id`,
`source_binding`, `parameters` (defaults filled), `capability_revision`,
`idempotency_key`, `cancel_requested`, `attempts` (each: `attempt`, `state`,
`worker_kind`, `reason_code`, `started_at`, `ended_at`, `liveness`,
`reconciled_publication`, `cancel` {`ack_at`, `observed_stop_at`,
`signal_target`} or null), `artifacts` (each: `artifact_id`, `attempt`,
`role`, `sha256`, `size_bytes`, `content_type`), `claim_class`
(`job_state_record`), and `unknowns`.

`unknowns` (closed, every key always present; value `null` plus a sibling
`*_reason`, or the stated constant):

| Key | Value / reason |
| --- | --- |
| `listening_acceptance` | `"not_established"` |
| `master_adopted` | `false` (const) |
| `low_register_preservation` | `null`; lossy AAC sharing derivative, ~32 Hz content not measured by this lane |
| `musical_review` | `null`; no note correctness, missed-note or phrase verdicts |
| `source_duration_seconds` | `null` until the worker reports it; admission does not probe |
| `memory_bytes_peak`, `cpu_seconds` | `null`; not measured, no OS quota |
| `exactly_once` | `"not_claimed"` |
| `slo` | `"not_claimed"`; local measurements only |
| `worker_birth` | `null` when `ps` evidence unavailable |

## 7. Bounds

Queue ≤4 queued + 1 running per state root; request body ≤16 KiB; handler
threads `daemon_threads=True`, `request_queue_size=8`; source ≤3 GiB
(configurable lower for tests); worker stdout ≤2 MiB, share result ≤16 KiB
(tool_api); `timeout_seconds` 30–900 per descriptor (default 900); cancel
grace 5 s; DB busy timeout 5 s. Shutdown (`server.shutdown()` /
`WebJobs.close()`) stops accepting work, cancels nothing implicitly, and leaves
running attempts to be reconciled on next start (closing a tab or stopping the
server is not a cancel).

## 8. Test protocol

Run from the worktree root:

```bash
export FFMPEG=/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffmpeg
export FFPROBE=/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffprobe
PYTHONPATH=tests python3 -m unittest test_web_jobs -v
```

Directly affected modules re-run locally (read-only reuse, no edits):
`test_artifact_ids test_share_export_tool`. Root runs the full suite.

Fixtures (all under `tempfile.TemporaryDirectory()`, `Path(...).resolve()`
first because macOS `/var` is a symlink and `safe_path` refuses symlink
components):

- **Synthetic runs root**: `R/artifacts/runs/RUN-A/manifest.json`
  (`source.sha256 = sha256("fixture-source")`, `source.path` sentinel string
  asserted absent from every response), `RUN-A/export/clip.mov` generated once
  per class with the qualified FFmpeg: `testsrc2=size=320x240:rate=24:duration=2`
  + `sine=frequency=32.70:sample_rate=44100:duration=2` (C1 content; no spectral
  claim is made), H.264/AAC in MOV; `RUN-A/notes.txt`, a `#!` file, a
  `chmod 0o755` file, a symlink escaping `R`, a `.partial` file, a FIFO, a
  2-byte `bad.mov` without `ftyp`.
- **State root**: `T/state` (separate from `R`).
- **Stub worker** (`worker_kind: test_stub`): a Python one-liner command built
  by the test `command_builder` that writes a heartbeat file and sleeps up to
  60 s; used only for cancel/interrupt/latency cases where a real encode is too
  short to observe. Real-dispatcher tests use the default builder.
- FFmpeg-dependent tests skip with an explicit reason when `FFMPEG` is unset
  (the skip count is reported, never counted as a pass).
- No randomness affects assertions; job IDs/tokens are random but never
  asserted by value. No seeds needed.

Named tests (minimum 18; ≥15 required):

1. `test_schema_version_wal_and_triggers_installed` (user_version 1,
   `journal_mode=wal`, illegal transition `succeeded→running` aborts in SQL)
2. `test_server_binds_loopback_and_refuses_bad_host_origin_and_token`
3. `test_admit_source_returns_ids_without_host_path`
4. `test_rejected_inputs_have_typed_reasons` (unknown field, non-media
   `notes.txt`, `bad.mov`, oversize with `max_source_bytes=1024`, `..`, absolute
   path, escaping symlink, executable, `.partial`, FIFO; store unchanged after
   each)
5. `test_unknown_fields_and_unadmitted_tool_refused_on_submit`
6. `test_real_share_export_job_succeeds_and_publishes_atomically` (FFmpeg;
   output only under `S/jobs/<id>/attempt-1/`, no `.staging-*` remains,
   artifact sha256 equals served bytes)
7. `test_idempotent_replay_returns_same_job_and_no_duplicate_publish` (same
   key ×3 → one job, one attempt, one `attempt-1`, artifact count unchanged)
8. `test_same_key_different_request_conflicts`
9. `test_cancel_queued_job`
10. `test_cancel_during_run_kills_owned_process_group` (stub with a child
    process in the same group; both PIDs gone; receipt has `ack_at ≤
    observed_stop_at`; no artifacts; staging removed)
11. `test_late_cancel_after_success_reports_actual_state`
12. `test_interrupted_then_replayed_and_retried_keeps_earlier_artifacts`
    (attempt 1 succeeds; attempt 2 on a second job is abandoned mid-run by
    closing `WebJobs` without shutdown and the test killing its own stub;
    restart → `interrupted, liveness: dead`; replay of the submit returns the
    same interrupted job; explicit retry → attempt 2 published to `attempt-2/`;
    `attempt-1/` bytes and earlier job's artifacts unchanged)
13. `test_reconcile_alive_unowned_worker_is_not_signalled_and_blocks_retry`
14. `test_reconnect_and_poll_after_restart` (new server instance, new port and
    token, same state root; `GET /jobs/{id}` returns the same projection)
15. `test_crash_after_publish_before_commit_is_adopted_not_republished`
    (`fault='after_publish_before_commit'`; restart → `succeeded`,
    `reconciled_publication: true`, exactly one `attempt-1/`, one set of rows)
16. `test_source_changed_after_submit_fails_without_worker`
17. `test_artifact_download_confinement` (malformed IDs, path-like IDs, unknown
    ID, symlink swapped into a published attempt dir → `confinement_refused`,
    changed bytes → `artifact_stale`, deleted → `artifact_missing`; responses
    never contain `S` or `R` path strings; `R/artifacts/runs` tree hash
    unchanged across the whole test class)
18. `test_queue_limit_and_body_limit`
19. `test_projection_carries_all_unknowns_and_claim_class`
20. `test_schema_version_mismatch_refused`

Opt-in measurement (not part of the pass count): `WEB_JOBS_MEASURE=1` runs
`test_measure_local_latencies` (section 9).

## 9. Local latency measurement (measurement only, no SLO claim)

Run once after tests pass, in-process server on an ephemeral port, idle local
host, one heavy job at a time, explicit 600 s timeout. Record host
(`uname -a`, CPU model), Python and FFmpeg versions, warm/cold state, and every
denominator including failures. Output
`artifacts/s2/web_jobs/latency.json` (gitignored) and receipt
`docs/agent-notes/sprints/20261006-s2/web_jobs-latency.json`.

| Measurement | Denominator / condition | Worker |
| --- | --- | --- |
| `GET /jobs/{id}` p50/p95/max | 500 sequential + 500 over 10 concurrent clients | none |
| `POST /jobs` acceptance p50/p95 | 50 new submissions (queue drained between batches of 4) + 50 replays | stub |
| Cancel acknowledgement p50/p95 | 10 running stub jobs | stub |
| Observed stop after signal | same 10 | stub |
| Restart → reconciled | 10 abandoned running attempts | stub |
| Real share export wall time | 3 runs of the 2 s synthetic clip | tool_api |

These numbers describe this host only; WEB_BACKEND targets remain unmeasured
engineering targets and no comparison verdict is asserted.

## 10. Actual-demo read-only job (not an experiment)

One bounded job through the HTTP API with `runs_root=/Users/jess/git/video-utils`
(read-only) and `state_root=.local/sprint2/web_jobs/artifacts/s2/web_jobs/demo-state`:
admit `20261006T041633Z-990aa1bd6737/export/cleaned-video.mov` from the accepted
FULLER run, submit `share_export` with defaults (H.264 720p CRF27 AAC96),
timeout 900 s, poll to terminal, download the MP4 by artifact ID and compare its
sha256 to the published row; replay the submit once (must return the same job,
no second publication). Before/after tree hash (paths + sha256 + size +
mtime_ns) of the accepted run must be equal. Receipt
`docs/agent-notes/sprints/20261006-s2/web_jobs-demo-receipt.json` holds IDs,
hashes, byte counts, state, wall time and the worker's structural checks but
**no host path**. A worker rejection (e.g. duration or stream constraint) is a
valid recorded outcome. This is a structural delivery check; it makes no
listening, low-end, tone or musical claim, and the derivative is not adopted.

## 11. Completion metrics (denominators and claim classes)

Claim classes: **M** measurement by test/run; **S** static check; **D** lane
declaration not runtime-verified; **NE** explicitly not established.

| # | Metric | Target / denominator | Class |
| --- | --- | --- | --- |
| 1 | Named tests passing | ≥18 named (≥15 required), reported X/X with skip count separate | M |
| 2 | Rejected-input cases refused with expected typed reason, store unchanged | ≥10/10 | M |
| 3 | Illegal state transitions refused by SQLite triggers | all non-allowed pairs of the 6 states tested: 0 accepted | M |
| 4 | Idempotent replay | 3/3 replays return the same job; 0 duplicate jobs, attempts or publications | M |
| 5 | Interrupted → replay → explicit retry | 1/1 scenario; earlier attempt artifacts byte-identical (sha256 equal) | M |
| 6 | Crash after publish before commit | adopted 1/1; publications = 1 | M |
| 7 | Cancel during run | owned group processes terminated k/k (k ≥ 2 PIDs); 0 artifacts published | M |
| 8 | Reconnect/poll after restart | projection equal 1/1; queued job still runs after restart | M |
| 9 | Unowned live worker not signalled | 0 signals sent; retry refused | M |
| 10 | Confinement | 0 responses containing state/runs root path; 0 writes under `artifacts/runs` (tree hash equal); ≥6 hostile download cases refused | M |
| 11 | Real dispatcher jobs | n succeeded / n submitted on synthetic fixture, reported with worker structural checks | M |
| 12 | Actual demo job | terminal state, hashes, replay = same job 1/1, accepted run tree hash unchanged | M |
| 13 | Local latencies (section 9) | p50/p95/max with stated n including failures | M |
| 14 | Diff confined to owned files vs `e0da4ca` | 0 files outside the owned list | M |
| 15 | No host daemon / foreground only | server code path has no fork/daemonize/launchd; only foreground `serve` | S |
| 16 | Memory/CPU/disk quotas, exactly-once, SLOs | not measured / not claimed | NE |
| 17 | Listening, low-register preservation, musical correctness of outputs | not claimed | NE |

## 12. Preregistration

Not applicable: this lane runs **no experiment**. It compares no arms, tunes no
parameters and has no held-out truth; tests use fixed deterministic fixtures
and latency numbers are descriptive measurements. `preregistered: false` is
recorded deliberately.

## 13. Root-owned changes (requested, not made)

1. `just/workflow.just` (foreground only, no daemon):

   ```just
   # Private loopback job control API (foreground; Ctrl-C stops it). Not a daemon.
   web-jobs-serve port="0" state_root="artifacts/web-jobs":
       python3 scripts/web_api.py serve --port {{quote(port)}} --state-root {{quote(state_root)}}
   ```

2. `program/capabilities.json`: none now. `share_export.adapters.web_job`
   stays `planned`; promoting it is a root admission decision after review of
   this lane's evidence.
3. `scripts/tool_api.py`: none required. Optional future: a public
   `spawn_worker(command) -> Popen` helper so supervisors do not duplicate
   `run_worker`'s launch discipline.
4. CI: `test_web_jobs` is discovered by unittest; FFmpeg-dependent cases need
   the qualified `FFMPEG`/`FFPROBE` env or report skips.

## 14. Dependencies and risks

- `artifact_ids.ArtifactIndex` is in-memory; `web_jobs` persists admitted
  source rows in SQLite and re-projects on restart (re-hash) before resolving.
- Same-host single-filesystem `rename` gives atomic publication; DB commit and
  rename are not one transaction, hence the fenced `publication.json` and
  reconciliation adoption.
- `worker_birth` via `ps` is best effort; when unavailable, a live PID yields
  `liveness: unknown` and blocks retry rather than guessing.
- share_export has no SIGTERM handler; group termination plus job-private
  staging removal covers cleanup. Worker children that start their own session
  are outside the owned group (same limitation as the descriptor states).
- The web_stack / web_ui_binding / web_reliability lanes consume this route
  contract; changes after freeze are appended as a dated section, not edited
  in place.
