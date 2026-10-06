# S2 web_ui_binding lane contract: bind the SvelteKit UI to the local job control API with CLI/MCP parity

Status: **Phase 1 contract freeze**, 2026-10-06. Lane `web_ui_binding`, workflow D,
wave 2, branch `sprint/20261006-s2/web_ui_binding`, worktree
`.local/sprint2/web_ui_binding`. Tracker: Linear TIN-5615 (related TIN-5547,
TIN-5550; consumes merged lanes `web_stack` TIN-5613 and `web_jobs` TIN-5614).
Baseline: `736f406e7eb979c11fe1811ed555260544dae3ed`. Authority: S2 sprint
manifest `program/sprints/20261006-s2.json`, repository `AGENTS.md`,
R-HOOK-CONVERGENCE-20261004 / R-N11/R-N12/R-N13 (TIN-3692 comment
98cf680c-7299-4949-bfb2-60079053ad43). Root administers review, signed merge,
`just` recipes, admission, publication and Linear. This lane never pushes,
merges, writes Linear, edits root-owned files, downloads models, starts a host
daemon or deploys anything.

Design sources reused, not re-decided: [WEB_STACK_S2](WEB_STACK_S2.md) (SvelteKit
2 + Svelte 5 runes + Effect 4 + Skeleton 5 BFF, loopback config, polling policy,
error codes), [WEB_JOBS_S2](WEB_JOBS_S2.md) (control API, SQLite job store, one
admitted job type `share_export`, idempotency, cancel/retry, artifact-ID
download, explicit unknowns), [WEB_UI_DESIGN](../future/WEB_UI_DESIGN.md)
(upload → process → compare → annotate → iterate → download; compact overlay;
manual notes distinct from automatic candidates), [WEB_BACKEND](../future/WEB_BACKEND.md)
(`/api/v1` naming), `scripts/annotation_v2.py` (source-bound annotation
semantics), `scripts/artifact_ids.py`, `scripts/tool_api.py` and
`scripts/mcp_server.py` (import only, for parity).

## 1. Scope

In scope:

1. **Control-API boundary reconciliation** in `scripts/web_api.py`. The UI
   expects `GET /api/v1/sources` and `GET /api/v1/jobs/{job_id}`; `web_api.py`
   serves `/sources` and `/jobs`. Every route is served under `/api/v1`, and the
   six unversioned web_jobs routes stay as **byte-compatible aliases**, because
   `tests/test_web_jobs.py` (24 named tests) addresses them and must keep passing
   unchanged. New routes exist only under `/api/v1` (section 4).
2. **BFF binding** in `web/src/`: server-only Effect client and Effect Schemas
   aligned to the real web_jobs projection, replacing the assumed subset
   (`control_api_contract_source: "web_jobs_s2_merged"`). BFF JSON endpoints and
   pages for the six lifecycle steps (section 5, section 6).
3. **Parity** (`tests/test_web_parity.py`). The job request the UI/BFF sends
   must validate identically through `tool_api.validate` +
   `tool_api.validate_tool_arguments` as the CLI (`tool_api.py run`) and MCP
   (`tools/call`) call for the same tool and arguments. Results must surface the
   same typed fields (section 8).
4. **Scripted end-to-end walkthrough**: web_api in-process on an ephemeral port
   with a synthetic tiny source, the built BFF as a test-owned child process,
   every BFF endpoint driven to a terminal job state. Recorded as an
   ezgif-style step receipt (section 10).

Out of scope (not claimed): any job type besides `share_export`; denoise, tone,
analysis, marked render or stem jobs in the UI (shown as prototype labels only);
SSE/event streams; multi-user identity, TLS, remote or hosted deployment;
HTTP byte ranges (section 14 risk); default detector/profile/master adoption;
listening acceptance; low-register (~32 Hz) preservation claims about the lossy
share derivative; note-correctness, missed-note or phrase verdicts; edits to
`scripts/web_jobs.py`, `web/serve.js`, `web/svelte.config.js`,
`web/vite.config.ts` or any root-owned file (requests in section 13). No new npm
dependency: `web/pnpm-lock.yaml` is expected byte-unchanged. No host daemon:
the BFF and control API run only in the foreground or as test-owned children
terminated in `tearDown`.

## 2. Owned files

| File | Role |
| --- | --- |
| `scripts/web_api.py` | `/api/v1` routes, aliases, uploads, listings, annotations, source media |
| `web/src/**` | BFF client, schemas, endpoints, pages, components |
| `web/fixtures/**` | Mock control-API fixtures (real web_jobs shapes), parity request fixtures |
| `web/package.json`, `web/pnpm-lock.yaml` | Unchanged unless a script entry is needed (no dependency changes) |
| `tests/test_web_parity.py` | Parity + end-to-end walkthrough (new) |
| `tests/test_web_jobs.py` | Existing tests unchanged; new `/api/v1` classes appended |
| `tests/test_web_stack.py` | Existing IDs retained; rescoped cases listed in section 9.3 |
| `docs/spec/sprints/WEB_UI_S2.md` | This contract (later changes are appended as dated sections) |
| `docs/agent-notes/sprints/20261006-s2/web_ui_binding-*.json` | Receipts: contract freeze, tests, build, parity, walkthrough, handoff |

Generated outputs (gitignored) go only under
`.local/sprint2/web_ui_binding/artifacts/s2/web_ui_binding/`. Tests use
`tempfile.TemporaryDirectory()` runs and state roots. Nothing is written under
the real `artifacts/runs/*`, `/Users/jess/Documents` or `/Users/jess/Desktop`.
The real take is never opened by any test.

## 3. Reused modules (import only, never edited)

- `web_jobs.WebJobs`: `admit_source`, `submit`, `get_job`/`project`, `cancel`,
  `retry`, `open_artifact`, `normalize_parameters`, `db_path`, `runs_root`,
  `runs_dir`, `state_root`, `max_source_bytes`; `web_jobs.strict_json`,
  `closed_object`, `WebJobsError`, `ARTIFACT_ID`, `JOB_ID`, `PARAMETER_KEYS`,
  `_worker_checks` (static, used by the parity test only).
- `artifact_ids.ArtifactIndex(...).resolve(artifact_id)` for source media
  playback (re-hash; only `current` exposes a private path inside the process).
- `annotation_v2`: `validate_annotation`, `validate_store`, `LABELS`, `KINDS`,
  `BASES`, `STATES`, `storage_lock`, `atomic_json`, `request_schema`, and
  `AnnotationStore` through a web session adapter (section 4.5).
- `tool_api`: `descriptor`, `validate`, `validate_tool_arguments`,
  `ValidationError`, `execute` (parity test only), `load_registry`.
- `mcp_server`: in-process `tools/call` dispatch (parity test only; refused
  cases never launch a worker).

## 4. Control API `/api/v1` (scripts/web_api.py)

Unchanged from WEB_JOBS_S2 section 4.4 for all routes: bind `127.0.0.1` only,
`Host` ∈ {`127.0.0.1:<port>`, `localhost:<port>`}, `Origin` (when present)
matching, `Authorization: Bearer <per-start token>` compared with
`hmac.compare_digest`, strict finite JSON bodies of at most 16 KiB with no
duplicate keys or unknown fields, error body `{"status":"error","code","error"}`,
no host path, selector, stderr, token or state root in any response.

### 4.1 Route table

| Method and path | Alias (unchanged) | Body / query | Success | Notable refusals |
| --- | --- | --- | --- | --- |
| `GET /api/v1/sources` | none (new) | `?limit=1..500` (default 100) | `200 {schema_version:1, sources:[SourceRecord], truncated}` | `400 bad_query` |
| `POST /api/v1/sources` | `POST /sources` | `{"selector": "<run_id>/…/<file>"}` | as WEB_JOBS 4.4 | WEB_JOBS 4.5 admission reasons |
| `POST /api/v1/uploads` | none (new) | raw bytes; section 4.3 | `201 {upload:{upload_id, bytes, sha256}, source: <admission record>}` | section 4.3 |
| `GET /api/v1/sources/{source_artifact_id}/media` | none (new) | none | `200` source bytes, inline, re-hashed | `400 malformed_id`, `404 unknown_source`, `409 source_stale`, `410 source_missing`, `403 confinement_refused` |
| `POST /api/v1/jobs` | `POST /jobs` | as WEB_JOBS 4.4 | `202`/`200 replayed` + **v1 projection** (4.2) | as WEB_JOBS 4.4 |
| `GET /api/v1/jobs` | none (new) | `?source_artifact_id=art_…&limit=1..200` | `200 {schema_version:1, jobs:[JobSummary], truncated}` | `400 malformed_id`/`bad_query` |
| `GET /api/v1/jobs/{job_id}` | `GET /jobs/{id}` | none | `200` v1 projection | `400 malformed_id`, `404 unknown_job` |
| `POST /api/v1/jobs/{job_id}/cancel` | `POST /jobs/{id}/cancel` | `{}` | as WEB_JOBS 4.4 + v1 projection | `404 unknown_job` |
| `POST /api/v1/jobs/{job_id}/retry` | `POST /jobs/{id}/retry` | `{}` | as WEB_JOBS 4.4 + v1 projection | `409 not_retryable`/`prior_worker_alive`/`source_stale` |
| `GET /api/v1/artifacts/{artifact_id}` | `GET /artifacts/{id}` | none | bytes + `X-Artifact-Sha256` | as WEB_JOBS 4.4 + `403 artifact_private` |
| `GET /api/v1/sources/{source_artifact_id}/annotations` | none (new) | none | `200` public annotation store (4.5) | `404 unknown_source`, `409 annotation_source_clock_unknown` |
| `POST /api/v1/sources/{source_artifact_id}/annotations` | none (new) | annotation_v2 request (4.5) | `200 {store, mutation}` | annotation_v2 codes + `400 annotation_actor_refused` |

Aliases share one dispatch table with the v1 routes. The unversioned aliases
return the **legacy** projection (exactly the WEB_JOBS section 6 + section 15
shape), so test_web_jobs bodies do not change. Unknown `/api/v1/*` paths return
`404 route_not_found`. Query strings are allowed only on the two listing
routes; on any other route a query is `400 bad_query`.

### 4.2 v1 job projection

v1 = legacy projection **plus** these keys (all always present):

- `schema_version: 1`.
- `phase`: the latest `events.reason_code` for the job (`submitted`, `claimed`,
  `validating`, `worker_started`, `cancel_requested`, `finalizing`, `published`,
  `reconciled_publication`, `explicit_retry`, `supervisor_restarted`) or `null`.
- `progress`: `{completed, denominator: 6, unit: "lifecycle_steps"}`, counting
  the steps reached in order `submitted, claimed, validating, worker_started,
  finalizing, published` for the latest attempt, or `null` when no event row
  exists. `progress_reason`: `"lifecycle step count from the job event log; not
  an encode fraction; share_export reports no incremental progress"`.
- `eta_seconds: null`, `eta_seconds_reason: "not estimated"`.
- `created_at`, `updated_at` from the `jobs` row.
- `tool_envelope`: `{schema_version, tool, evidence_kind,
  implementation_status, limitations, skill, instrument_context}` built exactly
  as `tool_api.execute` builds its envelope (from `tool_api.descriptor` and
  `tool_api.load_registry`), so web results carry the same typed envelope fields
  as CLI/MCP results (section 8).

Phase/progress use a separate read-only SQLite connection
(`file:<db_path>?mode=ro`, WAL reader). The v1 projection is closed. The BFF
decodes it with `onExcessProperty: "error"`.

`SourceRecord` (listing): `source_artifact_id`, `source_id` (nullable),
`source_binding`, `kind`, `sha256`, `size_bytes`, `admitted_at`, `origin`
(`"upload"` when the private selector's run id begins with `web-upload-`,
otherwise `"run_selector"`), `state: "admitted"`, `rechecked: false`,
`state_reason: "listing does not re-hash; submit and media re-verify"`,
`duration_seconds` (nullable: worker packet extent of the newest succeeded job
for the source, else `null` + `duration_seconds_reason`). The selector is never
returned. `JobSummary`: `job_id`, `state`, `reason_code`, `parameters`,
`created_at`, `updated_at`, `attempt_count`, `artifact_count`. Both listings
order newest first and are bounded (`truncated: true` when the limit cut rows).

### 4.3 Upload admission (`POST /api/v1/uploads`)

- **Disabled by default.** `serve --allow-uploads` (or the `WebAPIServer(...,
  allow_uploads=True)` test seam) enables it; otherwise `403 uploads_disabled`.
  This avoids an unannounced write into the operator's `artifacts/runs`.
- Headers: `Content-Length` required (no chunked: `411 length_required`).
  `Content-Type` ∈ {`video/quicktime`→`.mov`, `video/mp4`→`.mp4`,
  `video/x-m4v`→`.m4v`, `video/x-matroska`→`.mkv`, `video/webm`→`.webm`}, else
  `415 upload_type_refused`. Optional `X-Upload-Label` (≤120 printable ASCII, used
  only in the receipt, never as a path).
- Bound: `min(WebJobs.max_source_bytes, --max-upload-bytes)` (default 3 GiB;
  tests use 8 MiB). A larger `Content-Length` gives `413 upload_too_large`
  **before** any byte is written. Streamed in 1 MiB chunks with the per-socket
  10 s timeout. A short body gives `400 upload_incomplete`.
- Private staging: a new run directory
  `<runs_root>/artifacts/runs/web-upload-<YYYYMMDDTHHMMSSZ>-<16 hex>/upload/`
  (mode 0700, created with `mkdir` that refuses existing paths). The file is
  written to `source<ext>.partial` (mode 0600,
  `O_CREAT|O_EXCL|O_NOFOLLOW`), sha256 computed while streaming, then `fsync`,
  then `rename` to `source<ext>` and a directory fsync. An existing run is never
  written to.
- Admission: `WebJobs.admit_source({"selector": "<run>/upload/source<ext>"})`.
  An admission refusal (for example `not_media` when `ftyp`/EBML magic is
  missing) removes the whole staged run directory and returns the typed
  admission code with its HTTP status. Any other failure also removes the staged
  directory and returns `500 internal_error` with no detail.
- Response: `upload_id` (`upl_` + 16 hex, the run suffix, which is not a host
  path), byte count, streamed sha256 (which must equal the admission `sha256`,
  else `500 upload_hash_mismatch` and the staging is removed), and the
  admission record.

The "local path" option in the UI is a **run-relative selector**
(`RUN/…/file.mov`) through `POST /api/v1/sources`. Absolute host paths, `..`,
symlinks and URLs are refused by `artifact_ids` with typed codes (WEB_JOBS 4.5).
This is by design: the browser never names a host path.

### 4.4 Source media (`GET /api/v1/sources/{id}/media`)

Serves only sources present in the `sources` table of this state root. The
server re-projects the private selector through `ArtifactIndex`, opens it with
`O_NOFOLLOW`, re-hashes through the open descriptor, compares `fstat`
before and after, and streams with `Content-Disposition: inline`, the stored
`Content-Type` derived from the suffix, and `X-Artifact-Sha256`. It is used only
by the compare player. Download remains artifact-ID only (job outputs). No
`Range` support in S2: `Accept-Ranges: none` is sent and any `Range` header is
ignored (full body).

### 4.5 Annotations (annotation_v2 semantics, source-timed)

Store location: `<state_root>/annotations/<source_artifact_id>/` (mode 0700),
holding `clock-manifest.json` and annotation_v2's `review-annotations-v2.json` +
`.review-annotations-v2.lock`. The single-instance state-root lock from
web_jobs covers it.

- **Source clock.** On the first annotation request for a source,
  `clock-manifest.json` is written once (no-clobber) from the newest succeeded
  job's `worker_checks.video_proof`:
  `timeline.format_start_seconds = timeline.audio_start_seconds =
  source_start_seconds`, `pcm.duration_seconds = source_end_seconds −
  source_start_seconds`, plus `source_sha256`, `source_artifact_id`, `job_id`,
  `attempt`, `clock_basis: "share_export video packet presentation extent
  (inference, not a container probe)"`. Its sha256 is the annotation_v2
  `manifest_sha256`. Without a succeeded job the request returns
  `409 annotation_source_clock_unknown`, the UI states "Source clock unknown —
  run the share preview first", and nothing is saved.
- **Write.** `AnnotationStore` is driven through a duck-typed web session
  adapter (`source_hash`, `manifest_hash`, `manifest`, `manifest_path`,
  `duration`, `audio_start`, `format_start`, `source_min`, `source_max`, `root`,
  `lock`, `provenance_hashes = {}`, `marker_ids = set()`,
  `candidate_hash = None`). If that protocol cannot be satisfied without editing
  annotation_v2, Phase 2 instead composes `validate_annotation`,
  `validate_store`, `storage_lock` and `atomic_json` with identical
  `expected_revision`, idempotency-replay and conflict semantics, and records
  that choice in an appended section. Either way the request schema is
  `annotation_v2.request_schema()`.
- **Authorship boundary.** Web writes require `reported_by == {"actor":
  "operator", "via": "browser"}` and `basis` ∈ {`operator_assertion` (label
  **USER REPORTED**), `operator_context` (label **INTENT**)}. Otherwise the
  response is `400 annotation_actor_refused` before any I/O. Detector hypotheses
  (`detector_hypothesis`, label **REVIEW**) are never created by the browser.
  `share_export` runs no detector, so the UI shows the detector track as
  "No detector hypotheses for this job type", not as an empty pass. Every stored
  record keeps `musical_verdict: "not_established"`.
- **Player time to source time.** span seconds = player `currentTime` +
  `source_start_seconds`. Whether the browser's media clock matches the
  container presentation timeline is unverified (`player_clock_offset_verified:
  false` in the public store projection's companion field `clock`, which also
  repeats `clock_basis`).

## 5. BFF (web/src)

Configuration (server-only, `$env/dynamic/private`):
`VIDEO_UTILS_CONTROL_API_URL` (unchanged loopback validation, WEB_STACK 4) and
`VIDEO_UTILS_CONTROL_API_TOKEN` (new; 16..256 URL-safe characters, never
logged, never serialized to the client, never in an error body). A missing token
with a configured URL gives `503 control_api_unauthenticated`. Upstream `401`
gives `502 control_api_token_refused`.

Endpoints (all JSON unless noted). Mutating endpoints require
`Content-Type: application/json` (uploads: an allowlisted `video/*` type) and a
same-origin request (`Origin` equal to the app origin, or
`Sec-Fetch-Site: same-origin`), else `403 bff_cross_origin_refused`. IDs are
pattern-checked before any upstream call (`invalid_job_id`,
`invalid_artifact_id`, `invalid_source_id`, all 400 with zero upstream
requests).

| BFF endpoint | Upstream |
| --- | --- |
| `GET /api/sources` | `GET /api/v1/sources` |
| `POST /api/sources` | `POST /api/v1/sources` |
| `POST /api/uploads` (raw body streamed, not buffered beyond adapter-node `BODY_SIZE_LIMIT`) | `POST /api/v1/uploads` |
| `GET /api/sources/[id]/media` (streamed) | `GET /api/v1/sources/{id}/media` |
| `GET /api/sources/[id]/jobs` | `GET /api/v1/jobs?source_artifact_id=` |
| `GET`/`POST /api/sources/[id]/annotations` | same path under `/api/v1` |
| `POST /api/jobs` | `POST /api/v1/jobs` |
| `GET /api/jobs/[id]` | `GET /api/v1/jobs/{id}` |
| `POST /api/jobs/[id]/cancel`, `/retry` | same under `/api/v1` |
| `GET /api/artifacts/[id]` (streamed download) | `GET /api/v1/artifacts/{id}` |

The BFF builds `POST /api/v1/jobs` bodies in one pure module
(`web/src/lib/server/job-request.ts`): `{tool: "share_export",
source_artifact_id, parameters: {only knobs the user set}, idempotency_key}`.
The idempotency key is `ui-` + 32 hex, generated once per rendered form, so a
double submit replays and a changed knob in a re-rendered form is a new job.

Bounds: JSON calls keep the 5000 ms timeout and 1 MiB cap. Streamed media,
upload and download use a 30 s idle timeout, no total cap beyond upstream
`Content-Length`, and pass through `Content-Type`, `Content-Length`,
`X-Artifact-Sha256` and `Content-Disposition`. Upstream typed error codes are
mapped through an allowlist to `{status:"error", code, message,
upstream_status, upstream_code}`. `upstream_code` is the control API `code`
only when it matches `^[a-z_]{1,64}$`. Upstream `error` text is never echoed.

Schemas (`web/src/lib/schema/control.ts`) are replaced with the real shapes:
`SourceRecord`/`SourceList`, `JobSummary`/`JobList`, `JobProjection` (v1,
closed, including `attempts[]`, `artifacts[]`, `unknowns` with every key and
`*_reason`, `tool_envelope`, `phase`, `progress`, `eta_seconds`), `UploadResult`,
`AnnotationStorePublic`. Job states are the six web_jobs states. The four
WEB_BACKEND states that web_jobs collapses are not decoded.

## 6. UI lifecycle binding

Global banner: "Local loopback pilot — private; not a hosted service."
Every nullable/unknown value renders through `UnknownValue` as **Unknown** with
its reason, never `0`, blank or `NaN`.

1. **Upload/admit** (`/upload`): a file input (accept list = section 4.3 types;
   client-side size pre-check is advisory only) and a run-relative selector
   input. Typed refusals render code and plain text (for example
   `upload_too_large`, `upload_type_refused`, `uploads_disabled`, `not_media`,
   `path_escape` + `detail_code`). Success links to the source page.
2. **Process** (`/sources/[id]`): one form for the admitted `share_export` job
   with the five knobs bounded by the descriptor (height 240..1080 even, crf
   18..32, audio_kbps 64..192, codec h264/hevc/copy, timeout_seconds 30..900),
   defaults shown from the descriptor, not invented. Submit → `/jobs/[id]`.
3. **Poll** (`/jobs/[id]`): the existing polling policy (WEB_STACK 5.2, terminal
   set = `succeeded, failed, cancelled, interrupted`). Shows state, `phase`,
   `progress` as "k / 6 lifecycle steps" with `progress_reason`, ETA Unknown,
   attempts with `reason_code`, `liveness`, cancel receipt fields,
   `worker_checks`, and the full `unknowns` block. **Cancel** for queued/running
   and **Retry** for interrupted/failed, each a POST. Closing the tab never
   cancels.
4. **Compare** (on `/jobs/[id]` when succeeded): two `<video>` players, source
   (`/api/sources/[id]/media`) and processed `share_mp4`
   (`/api/artifacts/[id]`), with this fixed note: "Levels are not matched by this
   page. Loudness values shown are the worker's measurements of the share
   derivative; listening comparison not established. Lossy AAC derivative:
   ~32 Hz low-string preservation not measured." `worker_checks.loudness` is
   shown verbatim as a measurement. Without a succeeded share artifact the
   compare region shows the **Prototype** label "Comparison data absent". No
   gain, EQ or normalization is applied in the browser.
5. **Annotate** (`/sources/[id]`, beside compare): "Add note at current time"
   takes the time from the source player, kind from annotation_v2 `KINDS`,
   basis USER REPORTED or INTENT, certainty, the operator's literal quote and a
   note. The list renders two visually separate tracks: **User reported /
   Intent** (operator) and **Detector hypotheses (REVIEW)**. Each record shows
   its `claim_label`, source span and `musical_verdict: not_established`. A
   stale revision (409) keeps the draft and shows the refreshed store.
6. **Iterate**: "Adjust settings" re-renders the process form prefilled with
   the job's parameters and a new idempotency key. The source page lists every
   job for the source (`GET /api/sources/[id]/jobs`) with its artifacts. Earlier
   jobs and artifacts stay listed and downloadable.
7. **Download**: links only to `/api/artifacts/{artifact_id}` for rows with
   `downloadable: true`. Shows sha256 and size from the projection. A
   `share_receipt` row is listed as "private (contains host paths)". No URL,
   form or endpoint accepts a path.

Former prototype routes: `/upload` becomes a bound route. `/compare`,
`/review`, `/download` remain index pages that link to the bound per-job and
per-source views and keep the "Prototype" label for any part not bound in S2
(review overlays, marked video, WAV/marker delivery).

## 7. Explicit unknown and abstain fields the outputs must carry

| Where | Field | Value when unknown |
| --- | --- | --- |
| v1 job projection | all WEB_JOBS section 6 `unknowns` keys + `*_reason` | unchanged, passed through and rendered |
| v1 job projection | `progress` | `null` before any event; otherwise lifecycle steps with `progress_reason` |
| v1 job projection | `eta_seconds` | `null` + `eta_seconds_reason` |
| v1 job projection | `phase` | `null` when no event |
| SourceRecord | `source_id`, `duration_seconds` | `null` + reasons; `rechecked: false` |
| Annotation store | `clock.player_clock_offset_verified` | `false` |
| Annotation store | `listening_acceptance` | `"not_established"` |
| Annotation record | `musical_verdict` | `"not_established"` |
| Compare view | `level_matched` | `false`; `listening_comparison: "not_established"` |
| Compare view | `low_register_preservation` | `null` (lossy derivative, not measured) |
| Walkthrough receipt | `browser_playback_verified`, `hydration_verified` | `null` unless a headless browser actually ran; reason string |
| Walkthrough receipt | `screenshots` | list, or `[]` + `screenshots_skipped_reason` |
| Parity receipt | `encode_byte_determinism` | `"unknown"`: output sha256 equality between CLI and web runs is recorded, not asserted |

## 8. Parity contract

For tool `share_export` with parameters `P` and source `s`:

- **CLI**: `tool_api.py run share_export --arguments {source, output, **P}`.
  Validation is `tool_api.validate(args, inputSchema)` followed by
  `validate_tool_arguments('share_export', args)`.
- **MCP**: in-process `mcp_server` `tools/call {name, arguments}`, which calls
  `tool_api.execute`. A validation failure is JSON-RPC `-32602` before any
  worker starts.
- **Web**: the exact body the BFF sends (`job-request.ts`, captured on the wire
  by a recording control API in the e2e test, plus committed fixtures
  `web/fixtures/parity/*.json` generated by the same module) →
  `POST /api/v1/jobs` → `WebJobs.normalize_parameters` (202 vs `400
  invalid_parameters`). On claim the supervisor validates the built args again
  through the same two tool_api functions.

Verdict parity: for every case in the frozen case table, accept/refuse is equal
across CLI-validation, MCP and web. The table has at least 20 cases:
defaults `{}`; each integer knob at its minimum and maximum (8); each integer
knob one below its minimum and one above its maximum (8); odd height `722→721`;
codec `"av1"`; unknown knob `bitrate`; boolean `true` for `crf`; float `27.5`
for `crf`; string `"27"` for `crf`. Message text is not compared; only verdicts
and, for web, the code `invalid_parameters`. Any disagreement fails the test.
Divergences are never whitelisted silently. A divergence found in Phase 2 is
recorded in the parity receipt and handed to root as a finding.

Result parity (FFmpeg-gated): the same synthetic source run once through
`tool_api.execute` (CLI/MCP path) and once as a web job with equal `P`.

- `tool_envelope` keys (`schema_version, tool, evidence_kind,
  implementation_status, limitations, skill, instrument_context`) equal 7/7
  with the CLI envelope.
- `web_jobs._worker_checks(cli_result['result'])` equals the web attempt's
  `worker_checks` on: `status, source_sha256, source_bytes, settings, codecs,
  dimensions, video_encode_count, video_proof.{method, packet_count,
  source_start_seconds, source_end_seconds}, audio_proof, master_adopted,
  listening_accepted`.
- `output_sha256`/`output_bytes`/`loudness` equality is recorded, not asserted
  (`encode_byte_determinism: "unknown"`).

## 9. Test protocol

Run from the worktree root:

```bash
export FFMPEG=/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffmpeg
export FFPROBE=/nix/store/mv3x2v2pr6pwvwj7cdyh8nci2q1wpnjq-ffmpeg-headless-8.1.2-bin/bin/ffprobe
PYTHONPATH=tests python3 -m unittest test_web_parity -v
PYTHONPATH=tests python3 -m unittest test_web_jobs -v
PYTHONPATH=tests python3 -m unittest test_web_stack -v
(cd web && pnpm install --frozen-lockfile --offline && pnpm run check && pnpm run build)
```

Directly affected modules re-run locally (no edits): `test_artifact_ids`,
`test_share_export_tool`, and the annotation_v2 test module if one exists.
Root runs the full suite. Heavy jobs: at most one FFmpeg job at a time. Each
subprocess has an explicit timeout (install/check/build 300 s, job poll 300 s,
BFF start 30 s).

### 9.1 Fixtures

- **Synthetic runs root** (temp, resolved first): `R/artifacts/runs/RUN-A/`
  with `manifest.json` (sentinel source path, asserted absent from every
  response) and `export/clip.mov` generated once per class with the qualified
  FFmpeg (`testsrc2=size=320x240:rate=24:duration=2` +
  `sine=frequency=32.70:sample_rate=44100:duration=2`, H.264/AAC MOV; C1
  content, no spectral claim), as in WEB_JOBS 8. Upload payloads are the same
  clip bytes, plus a 2-byte `bad.mov`, a `notes.txt` and an oversize
  zero-filled payload (`max_upload_bytes + 1`, which is refused before
  streaming).
- **State root** `T/state`, separate from `R`.
- **Stub worker** (`command_builder`, `worker_kind: test_stub`) only for cancel
  and queue cases. Parity/e2e result cases use the real dispatcher.
- **Mock control API** fixtures under `web/fixtures/control-api/` regenerated in
  real v1 shapes (sources list with null `source_id`/`duration_seconds`; job
  queued with `progress: null`; job running with lifecycle progress; job
  succeeded with artifacts and worker_checks; job failed `worker_rejected`;
  decode-error cases: unknown key, bad state enum). `README.json` changes
  `control_api_contract_source` to `web_jobs_s2_merged`.
- No seeds: no randomness affects assertions. IDs and tokens are random and
  never asserted by value.
- FFmpeg-, node- or pnpm-dependent tests skip with an explicit reason when the
  tool is missing. The skip count is reported and never counted as a pass.

### 9.2 `tests/test_web_parity.py` (new; ≥16 named tests)

Class `ParityValidationTests` (no FFmpeg, no node):

1. `test_case_table_frozen_and_covers_all_knobs` (≥20 cases, every key in `PARAMETER_KEYS`)
2. `test_cli_and_web_validation_verdicts_agree`
3. `test_mcp_tools_call_refuses_same_cases_before_worker` (JSON-RPC `-32602`; no worker process)
4. `test_bff_parity_fixtures_match_job_request_module_shape` (closed body keys; key pattern)
5. `test_v1_projection_tool_envelope_matches_tool_api_envelope`

Class `ParityResultTests` (FFmpeg):

6. `test_cli_and_web_share_export_typed_fields_agree`

Class `ControlApiV1Tests` (FFmpeg for success paths; stub otherwise):

7. `test_v1_routes_and_aliases_share_codes` (each of the 6 aliased routes: the v1 status and code equal the alias status and code for success and for ≥1 refusal)
8. `test_v1_loopback_host_origin_token_refusals`
9. `test_sources_listing_is_path_free_and_bounded`
10. `test_upload_bounds_and_typed_refusals_leave_no_staging` (disabled, oversize, bad type, chunked, short body, no-ftyp; staged dirs = 0 after each)
11. `test_upload_success_admits_and_is_idempotent_by_hash` (same bytes twice → same `source_artifact_id`, distinct `upload_id`, admission `201` then `200`)
12. `test_source_media_rehashes_and_refuses_changed_bytes`
13. `test_iterate_new_job_keeps_earlier_artifacts` (job A then job B with `crf` changed; A's attempt-1 bytes are sha256-equal before and after)
14. `test_annotation_clock_unknown_then_saved_replayed_and_conflicted`
15. `test_annotation_authorship_boundary_and_detector_track_distinct` (browser detector/agent refused; a synthetic detector record seeded directly into the store renders with `claim_label: REVIEW` separate from USER REPORTED)
16. `test_jobs_listing_by_source`

Class `EndToEndWalkthrough` (node + pnpm build + FFmpeg; section 10):

17. `test_walkthrough_upload_process_compare_annotate_iterate_download`

### 9.3 `tests/test_web_jobs.py` and `tests/test_web_stack.py`

- `test_web_jobs`: the 24 existing named tests and 2 opt-in classes stay
  byte-unchanged and must pass. They use the unversioned aliases.
- `test_web_stack`: S1–S7, B1–B5 and N1–N13 keep their IDs. Rescoped, with the
  reason recorded in the tests receipt:
  - S8 changes from "prototype routes contain no form" to "bound routes post
    only to `/api/*` BFF endpoints; no client file contains the control API
    URL, the token env name or `fetch('http://`; remaining prototype routes
    keep the label".
  - S9 covers the new fixture set.
  - N2/N3 assert `progress: null` preserved and lifecycle progress preserved.
  - N4 asserts SSR state, the unknowns block and the compare note.
  - N12's `/upload` expectation changes from the prototype label to the bound
    page rendering `control_api_refused_host`.
- New static S10: the client bundle (`build/client/**`) contains no token value,
  no `VIDEO_UTILS_CONTROL_API_TOKEN` and no `127.0.0.1:<control port>`.
- New N14–N18 against the mock:
  - N14: upload refusal code mapping.
  - N15: cross-origin POST refused with zero upstream calls.
  - N16: invalid artifact ID refused with zero upstream calls.
  - N17: download pass-through headers.
  - N18: upstream 401 gives `control_api_token_refused`.

## 10. End-to-end walkthrough receipt (ezgif-style steps)

In-process `WebAPIServer` (real dispatcher, `allow_uploads=True`,
`max_upload_bytes = 8 MiB`) on `127.0.0.1:0` over a synthetic runs root.
Built BFF via `node serve.js` (`HOST=127.0.0.1`, ephemeral `PORT`,
`BODY_SIZE_LIMIT=9M`, URL + token env) as a test-owned process group, which
is killed in `tearDownClass`. Steps, each recorded as `{step, name, request
(method + BFF path), http_status, code, started_at, wall_ms, assertions:
{name: bool}}`:

1. `GET /` → empty sources list renders.
2. `POST /api/uploads` (clip bytes) → 201, admission record.
3. `POST /api/sources` with an absolute path → typed `path_escape` refusal
   shown; `POST /api/sources` `RUN-A/export/clip.mov` → 201.
4. `POST /api/jobs` defaults → 202 `queued`.
5. Poll `GET /api/jobs/{A}` (2 s policy, 300 s bound) → terminal. Record the
   sequence of `state`/`phase`/`progress` observed.
6. `GET /jobs/{A}` SSR → compare region has both players and the fixed
   level/low-register note (or the Prototype label when A failed).
7. `GET /api/sources/{id}/media` → bytes re-hash equal to admission `sha256`.
8. `POST /api/sources/{id}/annotations` USER REPORTED note at 1.0 s → saved;
   replay → `replayed`; stale revision → 409.
9. `POST /api/jobs` with `crf: 30` and a new key → job B → poll to terminal.
10. `GET /api/sources/{id}/jobs` → A and B listed; A artifacts sha256 unchanged.
11. `GET /api/artifacts/{A share_mp4}` → sha256 of bytes = `X-Artifact-Sha256`
    = projection row; `share_receipt` → `403 artifact_private` mapped.
12. Cancel: submit job C, cancel while queued or running → `cancelled` or
    `cancel_requested`→`cancelled`; no artifacts for C.
13. Screenshots (optional): if Google Chrome or a Playwright-cached
    Chromium binary exists locally, `--headless=new --screenshot` of `/`,
    `/sources/{id}`, `/jobs/{A}` at 1280×900 into
    `artifacts/s2/web_ui_binding/screens/`. Otherwise `screenshots: []` with
    `screenshots_skipped_reason`. Screenshots are SSR captures. They do not
    show hydration or playback (`hydration_verified: null` unless proven).

Receipt files: `artifacts/s2/web_ui_binding/walkthrough.json` (gitignored, full)
and `docs/agent-notes/sprints/20261006-s2/web_ui_binding-walkthrough.json`
(committed, path-free: no host paths, token or port-qualified URLs; IDs,
hashes, byte counts, timings, host facts `uname -sm`, CPU model, Python, node,
pnpm and FFmpeg versions). Timings describe this host only; no SLO.

The real take is not used. An optional, separately invoked
(`WEB_UI_DEMO=1`) read-only variant may admit the accepted FULLER run's
`export/cleaned-video.mov` by selector into a lane-local state root, with
uploads disabled and before/after tree hashes of the accepted run equal. The
known `share_export` "video packet count changed" rejection (WEB_JOBS 15) is a
valid recorded outcome, and the compare view must then show the Prototype
label.

## 11. Completion metrics (denominators and claim classes)

Claim classes: **M** measurement by test/run; **S** static check; **D** lane
declaration not runtime-verified; **NE** explicitly not established.

| # | Metric | Target / denominator | Class |
| --- | --- | --- | --- |
| 1 | test_web_parity named tests | ≥16 named pass X/X; skips reported separately | M |
| 2 | test_web_jobs unchanged tests | 24/24 pass with qualified FFmpeg; 0 existing assertions edited | M |
| 3 | test_web_stack | all retained IDs + S10 + N14–N18 pass X/X; rescoped IDs listed with reasons | M |
| 4 | v1 route coverage | 12/12 v1 routes exercised; 6/6 aliases equal v1 status/code | M |
| 5 | Loopback/Host/Origin/token on v1 | 4 refusal classes × v1 route families: 0 accepted | M |
| 6 | Parity validation verdicts | agree k/n across CLI, MCP, web, n ≥ 20 cases; 0 disagreements | M |
| 7 | Parity typed fields | envelope 7/7 keys equal; worker_checks structural keys equal 1/1 run; output byte equality recorded (NE for determinism) | M |
| 8 | Upload refusals | 6/6 typed codes; 0 staged dirs or partial files remain | M |
| 9 | Iterate retention | earlier job artifacts sha256-equal 1/1; distinct job IDs | M |
| 10 | Annotation semantics | clock-unknown refusal, save, replay, stale conflict, out-of-bounds span, authorship refusal: 6/6; USER REPORTED vs REVIEW tracks distinct 2/2 | M |
| 11 | Download | bytes sha256 = header = projection 1/1; private receipt refused; path-like IDs refused with 0 upstream calls | M |
| 12 | E2E walkthrough | steps completed k/12 (+ step 13 optional); terminal state reached; per-step wall_ms | M |
| 13 | pnpm offline | `install --frozen-lockfile --offline` exit 0, `check` 0 errors, `build` exit 0; lock sha256 unchanged | M |
| 14 | Leak scan | 0 host paths, selectors, tokens in BFF/control-API responses and client bundle | M |
| 15 | Confinement | synthetic runs tree: pre-existing entries hash-equal, only `web-upload-*` added; real `artifacts/runs` untouched (0 writes) | M |
| 16 | Diff confined to owned files vs baseline | 0 files outside section 2 | M |
| 17 | Foreground only | no fork/daemonize/launchd; BFF/API children killed in tearDown | S |
| 18 | Screenshots | n captured or skipped with reason | M/D |
| 19 | Browser hydration/playback, level matching, accessibility | not established unless measured | NE |
| 20 | Listening, ~32 Hz preservation of the derivative, musical correctness | not claimed | NE |

## 12. Preregistration

Not applicable: this lane runs **no experiment**. It compares no processing
arms, tunes nothing, uses no held-out truth and adopts no default. Tests use
fixed deterministic synthetic fixtures, and timings are descriptive. The parity
case table in section 8 is frozen here before implementation, so the case set
is not chosen after seeing results. `preregistered: false` is recorded
deliberately.

## 13. Root-owned changes (requested, not made)

1. `just/workflow.just` recipe text (foreground; two terminals; not daemons):

   ```just
   # Private loopback job control API (foreground; Ctrl-C stops it). Prints url + token once.
   web-api-serve port="8790" state_root="artifacts/web-jobs" *flags="":
       python3 scripts/web_api.py serve --port {{quote(port)}} --state-root {{quote(state_root)}} {{flags}}

   # Local SvelteKit BFF (foreground). Requires the token printed by web-api-serve.
   web-ui-serve port="5179" api="http://127.0.0.1:8790":
       cd web && pnpm install --frozen-lockfile --offline && pnpm run build && \
       HOST=127.0.0.1 PORT={{quote(port)}} BODY_SIZE_LIMIT=3G VIDEO_UTILS_CONTROL_API_URL={{quote(api)}} node serve.js
   ```

   `VIDEO_UTILS_CONTROL_API_TOKEN` is exported by the operator in that shell;
   it is never a recipe argument (no token in shell history or `just` echo).
   Uploads stay off unless the operator passes `flags="--allow-uploads"`.
2. `web/serve.js` (web_stack-owned): optionally default `BODY_SIZE_LIMIT` to a
   documented bound when unset, so uploads above adapter-node's 512 KiB default
   do not fail with an untyped 413. Until then, uploads larger than the operator's
   `BODY_SIZE_LIMIT` fail at the BFF with `413`, which is mapped to
   `upload_too_large`.
3. `scripts/web_jobs.py` (web_jobs-owned), optional future: public
   `list_sources(limit)`, `list_jobs(source_artifact_id, limit)` and
   `latest_phase(job_id)` read methods, plus a configured `upload_root` outside
   `artifacts/runs`, so that uploads need not create `web-upload-*` run
   directories. S2 implements these read-only in `web_api.py` without editing
   web_jobs.
4. `program/capabilities.json`: none. `share_export.adapters.web_job` /
   `web_ui` promotion is a root admission decision after review.
5. `scripts/tool_api.py`, `program/tools.json`, `scripts/mcp_server.py`: none.

## 14. Dependencies and risks

- No `Range` support: Safari may refuse to play `<video>` without byte ranges,
  while Chromium plays full-body responses. Recorded as
  `browser_playback_verified: null`, not hidden.
- Upload staging lives inside `runs_root/artifacts/runs` because web_jobs
  admission is confined there. It is off by default for the operator's repo
  (section 4.3; root request 3).
- Read-only SQLite listings read the web_jobs schema v1 directly. A schema
  change in web_jobs must update `web_api.py` (guarded by `PRAGMA user_version`
  check → `500 schema_version_mismatch`).
- The annotation clock is an inference from video packet extent. Player-time
  mapping is unverified.
- `pnpm` offline install depends on the populated local store (web_stack
  receipt). No dependency change is planned. If offline install fails for a
  missing-store reason, build-dependent tests skip with that reason and are
  reported as skips.
- Changes after this freeze are appended as dated sections, not edited in place.

## 15. Phase 2 implementation record (appended 2026-10-06)

Implementation on `sprint/20261006-s2/web_ui_binding` after the freeze commit
`9db2ec8b18746c50d7fe037c371f2b67b99622ed`. Sections 1–14 are unchanged; this
section records what was built, the deviations and why. Receipts:
`docs/agent-notes/sprints/20261006-s2/web_ui_binding-{tests,build,parity,walkthrough,handoff}.json`.

### 15.1 Control API (`scripts/web_api.py`)

- One dispatch table: six unversioned aliases (legacy projection) and twelve
  `/api/v1` method/route pairs (v1 projection). `tests/test_web_jobs.py` is
  byte-unchanged and passes 24/24 (2 opt-in classes skipped).
- Query strings are accepted only by the two GET listing actions. Any other
  route, **including the aliases**, answers `400 bad_query` (section 4.1 read
  literally). No existing test sends a query.
- Additive fields, all always present: v1 projection `phase_reason`;
  SourceRecord `source_id_reason`; upload response `schema_version` and
  `upload.deduplicated`. Additive refusal codes: `upload_empty` (400) and
  `upload_label_refused` (400).
- **Upload idempotency by hash.** `artifact_ids` binds an artifact ID to
  selector plus content, so two staging runs can never share an ID. After
  streaming, the server looks for an earlier `web-upload-*` admission of the same
  SHA-256. If one exists and still re-verifies, the new staging run is removed and
  the earlier admission is returned (`200`, `deduplicated: true`). Otherwise the
  new run is admitted (`201`).
- Each upload run holds `upload/source<ext>` and `upload-receipt.json`. The
  receipt records the label, bytes, SHA-256, content type and time. Nothing is
  named `manifest.json`, so the source binding stays `unknown`.
- Annotations use the duck-typed `AnnotationStore` session adapter
  (`WebAnnotationSession`), so the fallback composition was not needed.
  `GET` returns `{schema_version, store, clock}` and `POST` returns
  `{schema_version, store, mutation, clock}`.
- The authorship refusal (`annotation_actor_refused`) is raised before any
  database or file access. The clock-unknown refusal creates no directory.
- Phase and progress come from a separate `mode=ro` connection, so they can
  lead or lag `state` by one event. `phase_reason` says so.

### 15.2 BFF (`web/src`)

- The error body now has six keys: `status`, `code`, `message`,
  `upstream_status`, `upstream_code` and `upstream_detail_code`.
- A typed upstream 4xx keeps its HTTP status and is returned with
  `code: control_api_refused`; the upstream code is carried in `upstream_code`.
  Upstream 401 maps to `502 control_api_token_refused`. A `404 unknown_*` maps to
  `job_not_found`, `source_not_found` or `artifact_not_found`.
- New BFF codes: `control_api_unauthenticated`, `control_api_token_refused`,
  `control_api_refused`, `bff_cross_origin_refused`, `bff_host_refused`,
  `bff_content_type_refused`, `bff_length_required`, `bff_body_too_large`,
  `invalid_request`, `invalid_artifact_id`, `invalid_source_id`,
  `source_not_found` and `artifact_not_found`.
- **Same-origin check.** Without `ORIGIN`, adapter-node reports `url.origin` as
  `https://…`, so a correct `Origin: http://127.0.0.1:<port>` never matched. The
  check therefore also accepts `http://<Host>` when Host is a loopback host.
- **Host guard (hardening, not in the freeze).** `src/hooks.server.ts` refuses
  any Host other than 127.0.0.1, [::1] or localhost with `421 bff_host_refused`,
  before routing. This blocks DNS rebinding and matches the control API's Host
  check.
- Job and artifact IDs are checked against the strict patterns
  (`job_[0-9a-f]{32}`, `art_[0-9a-f]{32}`) before any upstream call. The
  WEB_STACK opaque-ID pattern is retired.
- `job-request.ts` checks only the request shape. Knob values are forwarded
  unchanged, so `tool_api` (through `WebJobs.normalize_parameters`) is the only
  validator. The process form uses `novalidate` for the same reason.
- `web/fixtures/parity/requests.json` is generated by `generate.mjs`, which
  imports the `.ts` module with Node's type stripping.
- Knob bounds and defaults come from `src/lib/share-export-knobs.json`, a mirror
  of `tool_api.descriptor('share_export')`. `test_web_parity` test 1 asserts it
  equals the descriptor.
- `polling.js` is unchanged. Its terminal set also contains
  `needs_reconciliation`, which web_jobs never emits; the four web_jobs terminal
  states all stop polling.

### 15.3 Tests

- The parity case table has 25 cases: the 23 frozen cases plus two accepted
  codec cases (`hevc`, `copy`). The table is mirrored in
  `web/fixtures/parity/cases.json`.
- Tests 14 and 15 (annotations) use a stub worker that reports a synthetic
  `video_proof` extent of 0–2 s. That extent is a fixture value, not a
  measurement. The walkthrough uses the real worker's extent.
- The mock fixtures are regenerated from real `web_api` responses by
  `web/fixtures/control-api/generate_fixtures.py`. The succeeded job comes from a
  real FFmpeg encode of the synthetic clip. Job IDs are rewritten to fixed values.
- Rescoped `test_web_stack` IDs: S8, S9, N2, N3, N4 and N12 as frozen. Also
  rescoped (not in the freeze list):
  - N1: banner text and SourceRecord fields.
  - N5: the six-key error body.
  - N6–N10 and N18: request paths use the strict fixture job IDs.
  - N14: uses `application/octet-stream`, because SvelteKit's own CSRF check
    answers form content types first.
  - N15: adds the Host-guard case.
- **Pre-existing baseline failure.** S6 fails at baseline `736f406` and on this
  branch for the same reason. `docs/agent-notes/sprints/20261006-s2/web_stack-handoff.json`
  line 6 records an absolute `worktree` path. That file is a web_stack receipt
  that this lane may not edit, and S6 is not weakened to pass it. The fix is a
  root request.

### 15.4 Outcome (claim classes as in section 11)

- **M:** test_web_parity has 17/17 named tests passing, plus 1 opt-in demo
  test that is skipped by default.
- **M:** test_web_jobs passes 24/24 unchanged.
- **M:** test_web_stack passes 32/33. The one failure is the baseline S6 issue.
- **M:** parity verdicts agree 25/25 across CLI, MCP and web, with 0
  disagreements and 0 workers launched by the MCP check.
- **M:** the tool envelope matches 7/7 keys, and the structural worker checks
  are equal on 1/1 real run.
- **M:** the walkthrough completed 12/12 steps with 3 headless screenshots.
- **M:** the pnpm offline install, check (0 errors, 0 warnings) and build all
  succeed. The lock hash is unchanged.
- **NE:** browser playback, hydration, level matching, listening, ~32 Hz
  preservation in the derivative and musical correctness are not established.

## 16. Phase 4 repair: test_web_jobs EPERM flake (appended 2026-10-06)

The audit reran the suite at `4446c23` and recorded an ERROR in
`test_web_jobs.WebJobsTests.test_interrupted_then_replayed_and_retried_keeps_earlier_artifacts`.
The traceback ends in the test harness (`Env.kill_detached` → `os.killpg` →
`PermissionError: [Errno 1]`), not in `web_api.py`.

- **M:** Darwin `killpg(2)` returns EPERM, not ESRCH, when every member of a
  process group is a zombie. A probe on this host produced 20/20 EPERM. The
  harness first sends SIGKILL to its own stub group. `Popen.poll()` can then
  still report the leader as running, and the second `killpg` raises EPERM.
- **M:** the failure reproduced at `4446c23` under 6-way concurrency in 2 of 36
  executions of the two tests that use the path. Both failures were at the
  same harness line. The base `736f406` snapshot passed 48/48 executions. The
  harness code and `scripts/web_jobs.py` are byte-identical to base. The
  `web_api.py` diff has no process, signal or shutdown change. The base/HEAD
  difference is within run-to-run variation (inference, not a significance test).
- **Fix:** the shared helper `sigkill_own_group` in `tests/test_web_jobs.py`
  treats EPERM on a test-owned group as nothing left to signal. The cleanup
  sites in `test_web_parity.py` and `test_web_stack.py` follow the same pattern.
  `process.wait(timeout=10)` still fails the test if the leader survives.
  `liveness == 'dead'` assertions still catch a surviving worker.
- **M:** after the fix, the same stress passed 60/60 executions. The owned suite
  passed `test_web_jobs` 24/24 (2 opt-in skips) and `test_web_parity` 17/17
  (1 opt-in skip). `test_web_stack` passed 32/33. S6 still fails on this branch
  because base lacks main `97ebce6`. With main's file overlaid, the static group
  passed 10/10. `cargo test --locked -j 1` reported 27 passed and 1 ignored.
