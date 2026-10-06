# S2 web_reliability lane contract: WEB demo, failure injections and real-take web rerun

Status: **Phase 1 contract freeze**, 2026-10-06. Lane `web_reliability`,
workflow D, wave 2, branch `sprint/20261006-s2/web_reliability`, worktree
`.local/sprint2/web_reliability`. Tracker: Linear TIN-5616 (related TIN-5550
JOBS / WEB-2, TIN-5551 STACK). Baseline:
`5436b2d008b55ce7cd4ba3b926c00bf44f9943b6`. Authority: S2 sprint manifest
`program/sprints/20261006-s2.json` (lane `web_reliability`), repository
`AGENTS.md`, R-HOOK-CONVERGENCE-20261004 / R-N11/R-N12/R-N13 (TIN-3692 comment
98cf680c-7299-4949-bfb2-60079053ad43). Root administers review, signed merge,
recipes, capability admission, publication and Linear. This lane never pushes,
merges, writes Linear, edits non-owned files, downloads models, starts a daemon
or opens a non-loopback listener.

Design sources reused, not re-decided:

- [MILESTONES](../future/MILESTONES.md) "Milestone acceptance demos", WEB demo:
  executed bounded admission/job/poll/cancel/reconnect/review/private download,
  one rejected input, one interrupted/replayed job, earlier artifacts retained,
  no duplicate publish.
- [WEB_BACKEND](../future/WEB_BACKEND.md): job states, idempotency, recovery
  rules, the failure-injection list and the proposed SLO rows (targets only).
- [WEB_JOBS_S2](WEB_JOBS_S2.md) sections 4-6 and 15: `scripts/web_jobs.py`
  store/supervisor/reconciliation and `scripts/web_api.py` routes, refusal codes,
  projection and `unknowns`.
- [WEB_UI_S2](WEB_UI_S2.md) and the merged `web_ui_binding` work: `/api/v1`
  routes, the SvelteKit BFF under `web/` (`/api/*` endpoints), parity cases.
- [SHARE_EXPORT](../SHARE_EXPORT.md) and the merged `share_export_fix`
  (`docs/agent-notes/sprints/20261006-s2/share_export_fix-handoff.json`):
  re-encodes compare presented packets and exclude edit-list decode-only
  pre-roll. Worker sha256 at baseline:
  `1d831e7c86ef39a0df88ebc2148932bd6d04d66f01e4d1ea7f9aef2683e110f1`.
- `program/capabilities.json`: `share_export.adapters.web_job` is `planned` at
  baseline.

## 1. Scope

In scope:

1. `tests/test_web_reliability.py`: an executable end-to-end WEB demo against an
   in-process `web_api.WebAPIServer` on an ephemeral `127.0.0.1` port, with a
   small synthetic source. It runs at the API level (`/api/v1`) always, and
   through the built BFF when node and pnpm are available and the offline
   install succeeds. Otherwise the BFF arm is skipped with an explicit reason,
   and a skip is never counted as a pass.
2. Bounded failure injections drawn from the WEB_BACKEND list (section 6), with
   the denominator reported as classes run / classes listed. Classes that are
   not run are named and never claimed.
3. One opt-in real-take web job rerun (`WEB_RELIABILITY_REAL=1`). It runs the
   `share_export` preview through `web_api` on the accepted FULLER run export,
   read-only, to confirm the merged share_export fix on the web path (section 7).
4. Lane receipts `docs/agent-notes/sprints/20261006-s2/web_reliability-*.json|md`.

Out of scope (not claimed): edits to `scripts/web_jobs.py`, `scripts/web_api.py`,
`scripts/share_export.py`, `web/`, `scripts/tool_api.py`, `program/*.json`,
recipes, or MCP/review servers. Also out of scope: new job types, uploads beyond
what the parity suite already covers, SSE, hosted/multi-user rollout, TLS,
identity, OS memory/disk/CPU quotas, SLO attainment, the 30-injection target in
WEB_BACKEND, exactly-once execution, browser screenshots or UI rendering claims,
listening, tone, low-register (~32 Hz) preservation of the lossy derivative,
musical correctness, note/phrase verdicts and derivative or master adoption.
There is no detector, profile or master default change.

## 2. Owned files

| File | Role |
| --- | --- |
| `tests/test_web_reliability.py` | All lane tests (section 8) |
| `docs/spec/sprints/WEB_RELIABILITY_S2.md` | This contract |
| `docs/agent-notes/sprints/20261006-s2/web_reliability-*.json` | Contract freeze, test results, real-take web job, handoff receipts |
| `docs/agent-notes/sprints/20261006-s2/web_reliability-*.md` | Optional human-readable run notes |

Generated outputs are gitignored, since `/artifacts/` is ignored:

- Synthetic and test outputs: `.local/sprint2/web_reliability/artifacts/s2/web_reliability/`
  (metrics JSON, raw receipts, logs). Synthetic state and runs roots live in
  `tempfile.TemporaryDirectory()` and are removed.
- Real-take web job state root, only:
  `.local/sprint2/web_reliability/artifacts/web-jobs/s2-web_reliability-real-<UTCSTAMP>/`.
- The BFF arm may run `pnpm install --frozen-lockfile --offline` and
  `pnpm run build` inside the worktree `web/`. This creates `node_modules/`,
  `.svelte-kit/` and `build/`, all gitignored. The test makes no network fetch.

Read-only: the main checkout `/Users/jess/git/video-utils`,
`artifacts/runs/20261006T041633Z-990aa1bd6737` (tree digest before and after),
other worktrees, `/Users/jess/Documents` and `/Users/jess/Desktop`. The original
take is never opened.

## 3. Reused helpers (import only, never edited)

From `tests/test_web_jobs.py` (as `wj`): `FFMPEG`, `HAVE_FFMPEG`, `FFMPEG_SKIP`,
`SENTINEL`, `make_runs_root`, `make_clip` (2 s `testsrc2` 320x240@24 plus a
32.70 Hz sine, H.264/AAC MOV), `StubBuilder`/`STUB` (modes `succeed`, `sleep`
with a same-group child, `reject`, `garbage`), `Client`/`Response`, `Env`
pattern, `tree_digest`, `sigkill_own_group`, `_host_facts`.
From `tests/test_web_stack.py` (as `ws`): `_ensure_build`, `_App` (test-owned
`node serve.js` in its own process group on a loopback ephemeral port).
From `tests/test_web_parity.py`: the `host_facts` pattern and the
`raw_http` approach for transport-level cases. Product modules: `web_jobs.WebJobs`,
`web_jobs.TERMINAL`, `web_api.WebAPIServer`.

Worker kinds stay honest: an attempt run by a `command_builder` is recorded as
`test_stub`, and one run by the default builder as `tool_api_share_export`.
Receipts report per-attempt `worker_kind`, and stub runs never count toward
"real dispatcher" metrics.

## 4. WEB demo, API arm (`WebDemoApiTest`)

Requires the qualified FFmpeg env (`FFMPEG`/`FFPROBE`). Without it the class is
skipped with `wj.FFMPEG_SKIP`. One ordered test method,
`test_web_demo_end_to_end_api`, uses the `step()` receipt pattern from
`test_web_parity`. Each step records name, request, HTTP status, code, wall ms
(host measurement) and its assertion map. A failed assertion fails the step and
the test. Setup: synthetic runs root `R` (via `make_runs_root` +
`make_clip(RUN-A/export/clip.mov)` + `RUN-A/notes.txt`) and one state root `S`.
Every server binds `127.0.0.1` on port 0.

Instance I1 uses the real dispatcher (`command_builder=None`):

1. **admit**: `POST /api/v1/sources {"selector":"RUN-A/export/clip.mov"}` returns
   `201`, with an `art_` ID and no host path. `GET /api/v1/sources` lists it.
2. **rejected_input**: `POST /api/v1/sources {"selector":"RUN-A/notes.txt"}`
   returns `422` with code `not_media`. `jobs.counts()` and the sources listing
   are unchanged.
3. **submit_preview**: `POST /api/v1/jobs` with `share_export`, the source,
   `parameters {"height":240,"timeout_seconds":120}` and key `demo-preview-A1`
   returns `202` and `replayed:false`.
4. **poll_terminal**: poll `GET /api/v1/jobs/{A}` every 0.25 s for at most 180 s.
   The job reaches `succeeded`. The attempt has `worker_kind`
   `tool_api_share_export`, `worker_checks.status` `exported_unreviewed`,
   `master_adopted:false` and `listening_accepted:false`. Observed phases are
   recorded.
5. **private_download**: `GET /api/v1/artifacts/{share_mp4 id}` returns `200`.
   The sha256 of the body, the `X-Artifact-Sha256` header and the row `sha256`
   are all equal. `share_receipt` returns `403 artifact_private`.
6. **idempotent_resubmit**: the same body with key `demo-preview-A1` is sent ×3.
   Each returns `200`, `replayed:true` and the same `job_id`. Afterwards there is
   still 1 job, 1 attempt, 1 `attempt-1/` directory, 3 artifact rows and 1
   `publication.json`.

Stop I1 (`server.stop()` + `jobs.close()`; nothing running). Instance I2 uses a
stub builder (modes `sleep`, `sleep`) on the same `S`:

7. **cancel_mid_run**: submit job B (key `demo-cancel-B1`). Wait for `running`
   and the stub heartbeat (pid and child pid). `POST /api/v1/jobs/{B}/cancel`
   returns `202`, and then the job reaches `cancelled`. Both recorded PIDs are
   gone within 10 s, checked with `os.kill(pid, 0)` and no signal sent by the
   test. The cancel receipt has `ack_at <= observed_stop_at`. B has 0 artifacts,
   no `attempt-*` directory and no `.staging-*` directory.
8. **interrupt_mid_run**: submit job C (key `demo-interrupt-C1`) and wait for
   `running` and its heartbeat. Stop I2 mid-run (`server.stop()` +
   `jobs.close()`, which cancels nothing). Then the test SIGKILLs only the stub
   group that its own I2 instance created (`sigkill_own_group`, R-N11 owned
   target), and records `tree_digest(S/jobs/C)`.

Instance I3 is a restart with the real dispatcher, a new port and a new token,
on the same `S`:

9. **reconnect_poll**: `I3.jobs.reconciliation["interrupted"] == 1`. The
   `GET /api/v1/jobs/{A}` projection equals the step-4 projection on every key,
   because job A is terminal. Any differing key is recorded by name and fails
   the step, and nothing is masked. `GET /api/v1/jobs/{C}`
   returns `interrupted`, `liveness:"dead"` and `reason_code:"supervisor_restarted"`.
   The old token is refused with `401 token_required` on the new server.
10. **replay_interrupted**: resubmit job C's exact body. It returns `200`,
    `replayed:true` and the same `job_id`, still `interrupted` with 1 attempt.
    No new run starts.
11. **explicit_retry**: `POST /api/v1/jobs/{C}/retry {}` returns `202` with
    2 attempts. Poll to terminal (≤180 s). The job reaches `succeeded` with
    attempt states `[interrupted, succeeded]`, attempt 2 `worker_kind`
    `tool_api_share_export`, and artifacts only for attempt 2 in `attempt-2/`.
    The attempt-1 staging tree is byte-identical to the step-8 digest (measured
    with `attempt-2/` set aside, as in `test_web_jobs`). Job A's tree digest and
    artifact rows are unchanged, and A's MP4 still downloads with an equal hash.
12. **no_duplicate_publish_audit**: SQLite read-only counts are 3 jobs and
    4 attempts (A1, B1, C1, C2). Artifact rows number 6 (A and C × 3 roles).
    There are 2 publication directories (`A/attempt-1`, `C/attempt-2`) and
    `publication.json` files in only those two. Replaying all three keys returns
    the same three job IDs and changes no count. The `R/artifacts/runs` tree
    digest is unchanged.

Every response passes `assert_no_leak`: no temp base, `R`, `S`, worktree root,
selector-private sentinel or token appears. The checked-response count is a
metric.

## 5. WEB demo, BFF arm (`WebDemoBffTest`)

The arm runs when `node` and `pnpm` are on PATH and `ws._ensure_build` succeeds
(offline install, then build). It is skipped with the exact reason when a tool
is missing or the offline store lacks packages. A build failure is a test
failure. It is never converted to a skip.

The storyline matches section 4, with a fresh `R`/`S` and the same keys plus a
`bff-` prefix. Requests go through the BFF `/api/*` endpoints (`/api/sources`,
`/api/jobs`, `/api/jobs/{id}`, `/api/jobs/{id}/cancel`, `/api/jobs/{id}/retry`,
`/api/artifacts/{id}`) with a same-origin `Origin` header. The BFF holds no job
state.

- Restart (steps 8-9): the BFF is configured with one control-API URL and token,
  so it is restarted against I3's new URL and token. "Reconnect" means a new BFF
  instance polls the same job ID. Before I3 starts, one extra step
  **control_api_down** sends `GET /api/jobs/{A}` while web_api is stopped. The
  frozen expectation is an HTTP status ≥500, a JSON body with a non-empty
  `code`, no host path and no store change. The exact code is recorded.
- BFF steps that differ from the API arm in status code or body shape are
  recorded per step, with the observed values. They are not silently
  normalized.
- The test-owned `node serve.js` process group is closed in `tearDownClass`.
  It is the only node process this lane starts.

## 6. Failure injections (`FailureInjectionTests`)

The listed denominator is frozen here, before any run, at **11 classes** from
WEB_BACKEND:

- (a) "Failure tests include expired leases, duplicate delivery, quota
  exhaustion, access denial, hash mismatch, model absence and output committed
  before a transport failure": 7 classes.
- (b) The "every accepted job accounted after restart" row: "crash/failure
  injections around enqueue, lease, render and publication": 4 classes.

The property-test topics in WEB_BACKEND (VFR, missing/extra boundaries,
ambiguous notes, partial analysis, stale revisions) are not failure injections
and are not in this denominator.

Each class carries a frozen status: `run_exact` (the listed failure is injected
as stated), `run_adapted` (no such mechanism exists in web_jobs; the closest
real failure is injected and the substitution is stated), `run_partial` (some
sub-cases run and the rest are named as not run) or `not_applicable` (counted in
the listed denominator, never as run). Unless stated, every case uses a stub
builder, a fresh state root and API-level `/api/v1`.

| ID | Listed class | Status | Injection and frozen expected outcome |
| --- | --- | --- | --- |
| FI-1 | expired lease | run_adapted | web_jobs has no lease timer; its equivalent is instance loss with a running attempt (`instance_id` ≠ current). (a) Dead worker: restart, then `interrupted`/`liveness:dead`, then retry reaches `succeeded`. (b) Live unowned worker: restart, then `interrupted` with `alive_unowned` or `unknown`. The new instance sends 0 signals (stub `.sigterm` marker absent, PIDs alive), and retry returns `409 prior_worker_alive` until the test kills its own stub. |
| FI-2 | duplicate delivery | run_exact | (a) 8 concurrent identical `POST /api/v1/jobs` from threads yield 1 job, 1 attempt and 1 publication. Exactly one response is `202` and the others are `200 replayed:true`, all with the same `job_id`. (b) A second supervisor on the same state root is refused with `state_root_locked`, so no double claim is possible. |
| FI-3 | quota exhaustion | run_partial | Run: (a) `queue_limit=4` with 1 running plus 4 queued, where the next submit returns `429 queue_full`; (b) a body over 16 KiB returns `413 body_too_large`; (c) a source over `max_source_bytes=1024` returns `422 too_large`. Store counts are unchanged after each. Not run, because no such quota exists: disk, RSS, CPU and per-operator rate. |
| FI-4 | access denial | run_exact | Missing token and wrong token return `401 token_required`. A bad Host returns `403 host_refused` and a bad Origin returns `403 origin_refused`. `share_receipt` download returns `403 artifact_private`, and an unknown well-formed artifact ID returns `404 unknown_artifact`. Store counts are unchanged and no response leaks a path. |
| FI-5 | hash mismatch | run_exact | (a) Source bytes changed after submit and before claim (`start=False`) end in `failed`/`source_changed` with no worker launched. A new submit returns `409 source_stale`. (b) Published `share.mp4` bytes changed return `409 artifact_stale`. (c) A deleted published file returns `410 artifact_missing`. |
| FI-6 | model absence | not_applicable | `share_export`, the only admitted job type, uses no model. Nothing is injected. |
| FI-7 | output committed before transport failure | run_exact | A raw socket sends a complete `POST /api/v1/jobs` and closes before reading the response. The job is durably committed. The same key returns `200 replayed:true` with the same job and 1 attempt, and the job reaches `succeeded` with 1 publication. The server keeps serving. |
| FI-8 | crash around enqueue | run_exact | Submit with the supervisor not started (`start=False`) gives `202 queued`. Stop the server and store, then restart: the job is still `queued`, then runs to `succeeded` with exactly 1 attempt and 1 publication. |
| FI-9 | crash around lease (claim) | run_adapted | No seam exists between claim and launch. The injection stops the instance after claim with the worker running, then the test kills its own stub. On restart the job is `interrupted`/`dead`. Replay returns the same job, explicit retry produces attempt 2, and attempt-1 staging stays byte-identical. This differs from the demo's step 8 only by a fresh store, and both are counted. |
| FI-10 | crash during render | run_exact | The test SIGKILLs its own instance's running stub group while the server is alive. The job ends `failed` with `reason_code: worker_failed` and 0 artifacts. Explicit retry then reaches `succeeded` at attempt 2, and attempt 1 is unchanged. |
| FI-11 | crash around publication | run_exact | `fault='after_publish_before_commit'`. The test waits for `jobs.crashed`, and the job still shows `running`. On restart, `reconciliation.adopted == 1`, the job is `succeeded` with `reconciled_publication:true`, and there is exactly one `attempt-1/`, 3 artifact rows and 1 stub launch in total. Replay returns the same job. |

Reported: classes run (exact + adapted + partial) / 11 listed, with the
breakdown by status. The frozen plan is 9 run (6 exact, 2 adapted, 1 partial),
1 not applicable and 0 not run. Reported alongside are the executions `n` (one
per lettered sub-case, about 17, plus the demo's interrupt/cancel steps listed
separately), and the lost job records and duplicate publications over those `n`
executions (target 0/0). This is a measurement over these executions only. It
does not meet or claim WEB_BACKEND's 30-injection SLO row.

## 7. Real-take web job rerun (`RealTakeWebJob`, opt-in)

Runs only with `WEB_RELIABILITY_REAL=1` and the qualified FFmpeg env. Otherwise
it is skipped with a reason. This is one structural delivery check, not an
experiment, and it runs one heavy job at a time with nothing else heavy running.

- Runs root: `WEB_RELIABILITY_RUNS_ROOT` (default `ROOT.parents[2]`, the main
  checkout, read-only). Source selector:
  `20261006T041633Z-990aa1bd6737/export/cleaned-video.mov`. Its expected sha256
  prefix `91b2f436` comes from the share_export_fix handoff and is re-hashed at
  admission.
- State root: `ROOT/artifacts/web-jobs/s2-web_reliability-real-<UTCSTAMP>/`,
  inside the gitignored worktree and nothing else. `web_jobs` refuses any
  overlap with `artifacts/runs`.
- The server is an in-process `WebAPIServer` on `127.0.0.1:0` with uploads off,
  using the real dispatcher.
- Request: `POST /api/v1/jobs` with `tool:"share_export"` and parameters
  `{"timeout_seconds":900}`, defaults otherwise (H.264, height 720, CRF 27, AAC
  96 kb/s), key `real-<UTCSTAMP>`. Polling runs every 5 s. **The hard bound is
  1100 s** from submit to terminal (worker 900 s + 10 s outer headroom +
  margin). Past the bound the test records `timed_out_waiting`, closes the
  store (no implicit cancel), cancels via the API, and fails the test.
- Recorded:
  - state, `reason_code`, `worker_kind` and the full path-free `worker_checks`.
  - Displayed-frame counts: source and output total, presented and decode-only
    video packet counts, `comparison_scope`, `maximum_pts_delta_seconds`,
    `tail_extent_delta_seconds`, and source start/end. These come from an
    allowlisted, path-free key extraction of the job-private
    `share.mp4.receipt.json`, which the test reads locally from its own state
    root because that receipt is `403 artifact_private` over HTTP, plus
    `worker_checks.video_proof.packet_count`.
  - An independent `ffprobe -count_frames` decoded video frame count of the
    downloaded MP4 bytes (timeout 300 s).
  - sha256 and bytes for the source, the downloaded MP4 (vs row and header),
    the receipt and `publication.json`.
  - A replay of the same body (`200`, same job, 1 attempt), artifact rows (3)
    and publication directories (1).
  - The accepted-run tree digest before and after (paths, type, size,
    mtime_ns, sha256).
  - Host facts and `os.getloadavg()` at start and end.
  - Wall seconds from submit to terminal and download seconds, as host
    measurements only.
  - An observation of whether the output sha256 equals the share_export_fix
    real-take sha256 `2eba932a…`. Equality is neither required nor claimed.
- **Frozen confirmation criteria**, all of which are required to call the fix
  confirmed on the web path:
  - state `succeeded` with `worker_checks.status` `exported_unreviewed`.
  - output presented count equals source presented count.
  - output decode-only count is 0, and `comparison_scope` is
    `presented_packets_excluding_edit_list_discard`.
  - the ffprobe decoded frame count equals the output presented count.
  - downloaded sha256 equals the row sha256.
  - replay returns the same job, with 1 publication.
  - the accepted-run tree is unchanged.

  The share_export_fix receipt measured source 3,631 total / 3,621 presented /
  10 decode-only. Equal values here are reported as agreement, not as a
  criterion.
- Outcome handling: a `failed` state or `deadline_exceeded` is a valid recorded
  outcome. The receipt says so, and no promotion is recommended. The tree
  digest equality and replay checks still apply.
- The test writes the raw path-free receipt to
  `artifacts/s2/web_reliability/real-web-job.json`. After review, the lane
  copies it to `docs/agent-notes/sprints/20261006-s2/web_reliability-real-web-job.json`.
  The test asserts that the receipt contains no host path, worktree root,
  selector, token or `/Users/` substring.

## 8. Test protocol

Run from the worktree root:

```bash
export FFMPEG=/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffmpeg
export FFPROBE=/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffprobe
WEB_RELIABILITY_METRICS=artifacts/s2/web_reliability/metrics.json \
  PYTHONPATH=tests timeout 1500 python3 -m unittest test_web_reliability -v
# opt-in, separately, only after the above passes, nothing else heavy running:
WEB_RELIABILITY_REAL=1 PYTHONPATH=tests timeout 1300 \
  python3 -m unittest test_web_reliability.RealTakeWebJob -v
```

Directly affected modules re-run locally (read-only reuse): `test_web_jobs`.
The full suite is root's job. `test_web_parity` and `test_web_stack` run only
if root asks, because their BFF build is shared state in `web/`.

Module layout and minimum named tests (≥16 named; ≥14 must pass, excluding
skips):

| Class | Tests |
| --- | --- |
| `ContractStaticTests` | `test_injection_table_frozen_with_denominator` (11 IDs, statuses as in section 6, each `not_applicable`/`run_partial` row has a reason), `test_servers_bind_loopback_only` (every server constructed by the module has `server_address[0] == "127.0.0.1"`; source scan shows no `0.0.0.0`/`::` bind), `test_receipt_unknowns_shape` (section 9 keys present, closed) |
| `WebDemoApiTest` | `test_web_demo_end_to_end_api` (12 steps, section 4) |
| `WebDemoBffTest` | `test_web_demo_end_to_end_bff` (section 5) |
| `FailureInjectionTests` | `test_fi01_expired_lease_adapted`, `test_fi02_duplicate_delivery`, `test_fi03_quota_exhaustion_partial`, `test_fi04_access_denial`, `test_fi05_hash_mismatch`, `test_fi06_model_absence_not_applicable` (asserts the descriptor references no model and records `not_applicable`; not counted as run), `test_fi07_output_committed_before_transport_failure`, `test_fi08_crash_around_enqueue`, `test_fi09_crash_around_claim_adapted`, `test_fi10_crash_during_render`, `test_fi11_crash_around_publication` |
| `RealTakeWebJob` | `test_real_take_web_job` (opt-in, section 7; not part of the pass count) |

Fixtures:

- Temp dirs are always passed through `Path(...).resolve()`, because macOS
  `/var` is a symlink.
- The synthetic runs root uses `wj.make_runs_root` plus `wj.make_clip` once per
  class, generated with the qualified FFmpeg. The fixture includes 32.70 Hz
  content, but no spectral claim is made. `RUN-A/notes.txt` is the rejected
  input.
- The `R/artifacts/runs` tree digest is checked equal in `tearDownClass`.
- Stub workers are `wj.StubBuilder`, used for cancel, interrupt and injection
  timing where a 2 s real encode is too short to observe. Real-dispatcher
  steps use the default builder.
- No randomness affects assertions. IDs and tokens are random but never
  asserted by value. No seeds are needed.
- Every wait has a bound: stub heartbeat 15 s, poll for stub jobs 30 s, poll
  for real synthetic jobs 180 s, process-gone checks 10 s, BFF start 30 s,
  module-level `timeout 1500`.
- Ownership (R-N11): the test signals only process groups whose leader its own
  `WebJobs` instance spawned and recorded (`sigkill_own_group`). It never
  signals the BFF from outside `_App.close()` and never touches another process.
- `tearDownModule` writes `WEB_RELIABILITY_METRICS` (when set) with per-step
  and per-injection records, skip reasons and counts. The lane then writes
  `web_reliability-tests.json` from it, with the command, worktree commit, pass,
  fail and skip counts, and log sha256.

## 9. Explicit unknown fields (every receipt; closed; `null` values carry `*_reason`)

| Key | Value / reason |
| --- | --- |
| `listening_acceptance` | `"not_established"` |
| `master_adopted` | `false` (const); derivative not adopted |
| `low_register_preservation` | `null`; the lossy AAC sharing derivative is not measured at ~32 Hz by this lane |
| `musical_review` | `null`; no note-correctness, missed-note or phrase verdicts |
| `decoded_picture_identity` | `null`; packet PTS and frame counts only, no per-picture comparison |
| `physical_capture_sync` | `null`; not verified |
| `slo` | `"not_claimed"`; latencies are measurements on this host |
| `hosted_rollout` | `"not_claimed"`; loopback, single-operator, foreground only |
| `exactly_once` | `"not_claimed"` |
| `memory_bytes_peak`, `cpu_seconds` | `null`; not measured, no OS quota |
| `injection_classes_not_run` | list of IDs with reasons (planned: `["FI-6"]` plus FI-3's unrun sub-cases) |
| `bff_arm` | `"run"` or `null` with the skip reason |
| `ui_rendering` | `null`; no browser render or screenshot in this lane |
| `output_determinism_vs_prior_run` | observed equal / not equal / not compared; never claimed |
| `host_load` | measured `os.getloadavg()` at start and end |

## 10. Completion metrics (denominators and claim classes)

Claim classes are **M** (measurement by test or run), **S** (static check),
**D** (lane declaration, not runtime-verified) and **NE** (explicitly not
established).

| # | Metric | Target / denominator | Class |
| --- | --- | --- | --- |
| 1 | Named tests passing | ≥16 named, ≥14 pass, reported X/Y with skips separate and never counted | M |
| 2 | API demo steps | 12/12 steps pass (section 4) | M |
| 3 | BFF demo steps | k/13 steps (12 + `control_api_down`), or skipped with the exact reason | M |
| 4 | Rejected input | 1/1 typed refusal (`422 not_media`), store counts unchanged | M |
| 5 | Cancel mid-run | owned PIDs gone k/k (k = 2: leader + child); 0 artifacts, 0 staging, `ack_at ≤ observed_stop_at` | M |
| 6 | Reconnect after restart | same-job projection equal 1/1 on new port/token; old token refused | M |
| 7 | Private download hash | downloaded = row = header sha256, n/n downloads | M |
| 8 | Interrupted → replay → explicit retry | 1/1 in demo (+1 in FI-9); earlier artifacts and attempt-1 staging byte-identical | M |
| 9 | Idempotent resubmit / no duplicate publish | r/r replays return the same job; 0 extra jobs, attempts, artifact rows or publication dirs | M |
| 10 | Failure-injection classes | run/listed = (exact + adapted + partial)/11, frozen plan 9/11; FI-6 not applicable; unrun sub-cases named | M |
| 11 | Injection executions | n executions; lost job records 0/n; duplicate publications 0/n | M |
| 12 | Path/token leak | 0 leaking responses over N checked (N reported) | M |
| 13 | Read-only inputs | synthetic `artifacts/runs` digest equal per class; accepted run digest equal (real take) | M |
| 14 | Loopback only, no daemon | every server binds 127.0.0.1; no fork, detach or service registration in the lane | S |
| 15 | Real-take web job | terminal state; frame counts, hashes and replay 1/1; frozen confirmation criteria k/7 | M |
| 16 | Host timings | wall seconds and latencies with host facts and load; no SLO comparison | M |
| 17 | Capability promotion | recommendation in `root_owned_changes_requested` only if metric 15 is 7/7 | D |
| 18 | Diff confined to owned files vs `5436b2d` | 0 files outside section 2 | M |
| 19 | SLOs, hosted rollout, exactly-once, quotas, 30-injection target, listening, low-register, musical correctness | not claimed | NE |

## 11. Preregistration

Not applicable: this lane runs **no experiment**. It compares no arms, tunes no
parameters and has no held-out truth. The demo steps, the injection table and
denominator (section 6) and the real-take confirmation criteria (section 7) are
frozen expectations, fixed in this commit before any run. Outcomes that differ
are recorded as outcomes, and expectations are not edited afterwards. Changes
are appended as a dated section. `preregistered: false` is recorded on purpose.

## 12. Root-owned and non-owned changes (requested, not made)

1. `program/capabilities.json`: **conditional**. Only if the real-take receipt
   meets 7/7 criteria, request
   `share_export.adapters.web_job: "planned"` → `"admitted"`, with evidence
   `docs/agent-notes/sprints/20261006-s2/web_reliability-real-web-job.json`
   (plus `web_reliability-tests.json`). Admission remains root's decision.
2. `scripts/web_jobs.py` (non-owned): `_worker_checks` should add to its
   `video_proof` allowlist `comparison_scope`, `source_packet_count_total`,
   `output_packet_count_total`, `source_presented_packet_count`,
   `output_presented_packet_count`, `source_decode_only_packets` and
   `output_decode_only_packets`. Without that, the public projection and
   `publication.json` cannot show displayed-frame counts after the
   share_export fix. Until then this lane reads them from the private receipt
   locally.
3. `just/workflow.just` (optional, foreground test only):

   ```just
   # S2 web reliability demo + failure injections (in-process loopback; no daemon)
   web-reliability-test:
       PYTHONPATH=tests python3 -m unittest test_web_reliability -v
   ```

## 13. Dependencies and risks

- Host load: share_export_fix measured 427.65 s at load ~106. Under heavier load
  the 900 s worker budget may be exceeded. A timeout is a recorded outcome, not
  a lane defect.
- Owned-process cleanup under extreme load (known from share_export_fix) can
  make cancel/stop timings flaky. Retries are not used to hide flakiness; a
  rerun is recorded as a separate run with both outcomes.
- The BFF arm depends on the offline pnpm store. An unavailable store is a
  skip with a reason.
- The demo intentionally mixes `test_stub` and `tool_api_share_export` attempts
  in one store. Every receipt reports `worker_kind` per attempt.
