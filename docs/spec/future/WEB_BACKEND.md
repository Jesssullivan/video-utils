# Future private web processing backend

Status: proposed, queued; October 6, 2026. Owner lane: `web_backend_future`.
This design adds a future delivery interface to the local practice workflow.
It does not establish a deployed service, supported remote MCP endpoint, web
upload processing, musical accuracy, or AU host acceptance. Root integrates it
with [the future goal](GOAL_WEB_PRACTICE_STUDIO.md), [milestones](MILESTONES.md),
[UI design](WEB_UI_DESIGN.md), and [capabilities](CAPABILITIES_AND_REPO_EVOLUTION.md).

## Decision and existing interfaces

All registered operations can be adapted for a private web workflow. They are
currently local operations, with local path arguments and uneven worker bounds.
A server must add identity, artifact resolution, scheduling, output confinement,
and recovery; opening the existing listening server on a public interface would
not provide those features.

Recommend a SvelteKit server frontend/BFF, a small FastAPI control API, and
separate bounded Python workers calling the existing validated dispatcher.
Rust retains reusable DSP and CLI authority; FFmpeg retains media work; Python
retains offline analysis. The browser and agent adapters use the same durable
job protocol. Start with one operator, one host, SQLite and a private filesystem
artifact store. PostgreSQL and an object store are later placement choices.
Avoid adding Redis, Celery or distributed execution until measured concurrency
or placement requirements warrant them.

Current evidence, inspected October 6:

| Surface | Implemented today | Future work needed |
| --- | --- | --- |
| `program/tools.json` / `scripts/tool_api.py` | 28 typed descriptors, allowlisted workers, validation, deadlines, structured result/limitations | Generate safe web schemas, artifact-ID adapters, admission policy and per-tool output confinement |
| `scripts/mcp_server.py` | Serial stdio JSON-RPC tools and skill prompts; 1 MiB message limit | Remote identity/transport, durable jobs and progress; current cancellation notifications are ignored |
| `scripts/review_server.py` + `review/` | Loopback playback, session metadata, byte ranges and source-bound annotations with revision checks | Workspace authorization, upload, job submission, multi-run iteration and authenticated downloads |
| Existing run graph | Source/upstream hashes, manifests, native clocks, review evidence | Database-backed job/artifact index and atomic publication reconciliation |
| AU integration | Separate native DSP integration lane | Explicit mappings for admitted real-time parameters; no server work in the render callback |

The listening server binds `127.0.0.1`, allows 16 handler workers, checks Host
and Origin, and requires a session token on annotation mutations. Those are
local protections, not user accounts or tenant isolation. The general tool
runner bounds returned JSON at 2 MiB and supervises an owned process group on
timeout; its file-backed logs are not a universal live disk/RSS/CPU quota.
`apply_capture_profile` has a separately qualified supervisor and stricter
source/log/deadline/publication bounds. Do not attribute those bounds to every
descriptor.

## Framework choices and estate reuse

| Option | Fit and consequence | Recommendation |
| --- | --- | --- |
| SvelteKit + Effect + Skeleton | Reuses the user's runes, typed UI and house design patterns; server adapter and auth required for dynamic requests | Preferred UI/BFF; generated HTTP client below framework-specific calls |
| FastAPI | Keeps control/validation near Python tool adapters; OpenAPI client generation possible | Preferred private control API, with a separate durable worker |
| Flask | Small Python HTTP layer is feasible, but typed API/client and async event plumbing require extra conventions | Viable if existing Flask operations outweigh generated-contract benefits |
| Rails + Active Job/Solid Queue | Strong application/identity/admin/job conventions; adds Ruby across an existing Rust/Python product | Choose if concrete estate reuse justifies that boundary; retain the same processing protocol |
| Effect HTTP backend only | Could remove the Python HTTP process while retaining a separate Python worker | Revisit after an Effect v4 job/storage qualification spike; do not implement two schedulers |

The read-only `xoxd.ai` snapshot currently declares Effect `^3.21.2`, Skeleton
`4.15.2`, Svelte `^5.55.5`, SvelteKit `^2.59.1`, and `adapter-static`, with runes
enabled and small Effect Schema/runtime helpers. Reuse patterns deliberately;
this is not an already running dynamic processing stack. Official primary
documentation now describes stable Effect v4 and Skeleton v5 migration. Exact
version pins, schema behavior and component/stylesheet migration need a local
qualification spike before selecting them for this product. See the dated
[research note](../../research/2026-10-06-future-web-backend.md).

SvelteKit remote functions remain experimental in current official docs. Use
qualified `query` for metadata, `form` for progressive submission/review, and
`command` for control mutations. They call the control API and return job IDs;
they never perform decoding, denoising, model inference or video rendering in
the request lifecycle. Keep ordinary endpoints/form actions available behind
the same contract. Runes describe UI state, not processing ownership. Effect
interruption of a browser request must not imply cancellation of a durable job.
Current upstream Kit docs describe v3 configuration; use documentation matching
the eventual locked version rather than copying configuration into the local
v2 scaffold. A static adapter cannot supply dynamic server-side remote queries.

## API and agent contract

Proposed routes use `/api/v1`. Identifiers are opaque references authorized in
the operator workspace; SHA-256 is provenance, not an authorization token.

| Route | Behavior |
| --- | --- |
| `GET /capabilities` | Registry revision, implementation/evidence status, schemas and admitted web controls; no media work |
| `POST /uploads`, `PUT /uploads/{id}/parts/{part}`, `POST /uploads/{id}/complete` | Quota-bound private upload, resumable parts, exact finalized identity; completion queues validation/probe |
| `GET /sources/{id}` | Native timeline/streams, validation state, source hash and approved context |
| `POST /jobs` | Validate authorized inputs/knobs, durably admit, return `202` with job ID; reject unsupported controls |
| `GET /jobs/{id}`, `GET /jobs/{id}/events` | Durable phase/status snapshot and resumable SSE events; polling fallback |
| `POST /jobs/{id}/cancel` | Durable cancellation request; separate acknowledgement from observed process termination |
| `GET /runs/{id}` | Exact graph, artifacts, limitations, measurements and nullable musical hypotheses |
| `GET /artifacts/{id}/content` | Authorized immutable download/playback, byte ranges, source/output identity |
| `GET /runs/{id}/annotations`, `POST /runs/{id}/annotations` | Source-bound point/span annotations with expected revision and evidence class |

The web invocation envelope contains `tool`, `capability_revision`,
`source_id`, authorized `input_artifact_ids`, `parameters`, optional approved
`reference_id`, and `idempotency_key`. The server resolves paths privately,
checks actual hashes, and projects only admitted parameters into the current
local schema. Never accept executable paths, shell commands, global run paths,
arbitrary output directories, arbitrary artifact URLs, or automatic model
downloads through that envelope. Existing local CLI/MCP contracts stay valid.

Idempotency keys are unique per workspace and operation. A canonical request
fingerprint includes source/upstream/reference/profile hashes, capabilities,
tool implementation and relevant dependency/model revisions. In one durable
transaction, record the accepted job and unique key before returning `202`.
Same key/same request returns the original job; same key/different request is
`409`. Keys remain available for the job's retention lifetime, including
cancelled or failed outcomes. Retrying processing requires an explicit new
attempt, never selecting the newest run. Queue transport may redeliver;
publication must be fenced and idempotent. Exactly-once execution is not a
claim of this design.

## Synchronous and queued operations

Synchronous handlers serve bounded metadata, annotation transactions, admission
and cancellation requests. Byte transfer streams outside media workers. Probe,
hashing large uploads and every current processing descriptor run as jobs by
default; faster pure metadata tools may be admitted synchronously only after a
measured size/time bound and separate adapter qualification.

| Registered tools, all 28 | Future execution/admission |
| --- | --- |
| `probe` | Queued upload validation/probe |
| `denoise`, `capture_profile`, `apply_capture_profile` | Queued restoration/profile candidates; bind capture review, profile and source |
| `bpm`, `noise`, `tone`, `notes`, `rhythm`, `phrases`, `clicks`, `pitch`, `meter`, `tonal` | Queued analysis; preserve sparse coverage, multiple hypotheses and unknown values |
| `phrase_compare` | Queued comparison of exact upstream phrase artifacts |
| `export`, `report`, `pipeline`, `markers`, `marked_video`, `editor_marker_plan` | Queued graph/report/delivery work; immutable published artifacts |
| `basic_pitch_compare` | Queued model-backed analysis only when the explicit pinned model is available |
| `benchmark`, `corpus`, `pitch_evaluate`, `phrase_evaluate`, `learned_pitch_evaluate` | Operator/developer-scoped queued validation; exclude from ordinary musician upload defaults |
| `review` | Existing invocation stays queued; separate qualified annotation read/write HTTP adapter can be synchronous |

Typed controls include reviewed fan-capture span, reduction intensity, bounded
parametric EQ/compression, loudness/peak targets, click-template strength,
analysis window, phrase alignment bounds and model thresholds where the current
descriptor admits them. Some are nested `capture_profile` settings or profile
data, not standalone EQ/mastering tools. `tone` measures spectra; it is not an
EQ effect. Current authoring permits at most three peaking bands at 160–6000 Hz,
gain ±3 dB and Q 0.5–2, constrained below Nyquist; it does not admit a low shelf
or promise restoration of missing 32 Hz capture. Compression has five coupled
fields, fixed 25% wet and no makeup gain; a single intensity control needs a
documented recipe rather than an invented parameter. Future balance/mastering
stages require their own descriptors,
skills, provenance, listening comparisons and preservation gates. Do not expose
a decorative slider before a supported typed parameter and evidence path exist.

Agent prompts can submit a source-timed user observation such as “rhythm issue
at 42.3 s” through the annotation contract: `source_sha256`, finite source
start/end seconds, category, author/provenance, reviewer-stated claim class,
text, and expected revision. This preserves the supplied statement and avoids
turning it into an automatic confirmed error. Intended-note grading still needs
the appropriate approved reference. Artifact identity, source clock and preview
clock remain separate. AU parameters share units/ranges where explicitly
mapped; network, I/O, queueing, analysis and allocation stay outside AU render.

Future classifier admission also binds label-store revision/hash, selected
source-time regions, feature/model/settings registry IDs, coverage and resource
caps. Return immutable proposals/evidence with nullable calibrated confidence.
Reference-aware comparisons receive an explicitly selected arrangement/reference;
the automatic baseline stays separately inspectable. Original and restored
variants inherit the same parent and evaluation split to prevent leakage. No
request-path training or on-demand checkpoint download is implied.

## Durable state, resource boundaries and recovery

1. Finalize each upload privately; calculate its hash and native timing in a
   validation job. Reject quota/probe failures before processing admission.
2. Persist accepted job, canonical args, registry/worker/model revisions,
   dependency hashes, resource class and attempts. The queue is a durable table,
   not a browser Promise or FastAPI `BackgroundTasks` callback.
3. A worker acquires a lease with an increasing fencing token. Record the owned
   worker/process identities and birth/ancestry evidence before signalling can
   ever be needed. Execute in a job-private workspace with explicit output
   paths; audit existing hardcoded/global artifact behavior before exposure.
4. Commit stage events after stage state is durable. Stream sequence-numbered
   events, replay from the last event ID, and cap slow-subscriber buffers.
   Whole-stage running/waiting is honest progress; numeric fractions require an
   actual denominator. Keep ETA estimates separate from observed work.
5. Validate staged outputs, source/native clock invariants and graph lineage;
   publish a fenced immutable artifact manifest atomically. Artifact writes
   and queue/database state require crash reconciliation, not an assumed atomic
   cross-filesystem transaction.
6. On restart or lease expiry, mark `interrupted` and inspect exact durable
   receipts. Reconcile already published outcomes before retry. Ambiguous
   process ownership or publication becomes `needs_reconciliation`, retaining
   evidence and refusing duplicate publication.

Job states: `queued → validating → running → finalizing → succeeded`; failure
can transition to `failed`, interruption to `interrupted`, and ambiguous recovery
to `needs_reconciliation`. Cancellation transitions through `cancelling` to
`cancelled` only after confirmed owned-worker termination and output inspection.
If finalization already committed, return the actual succeeded outcome with a
late-cancel receipt. Cancelling a request or closing a tab does not cancel work.

Proposed pilot admission: one active media job per host/operator, at most four
queued requests per operator, two codec/filter threads when supported, and
explicit per-tool wall time/source/PCM/disk/RSS limits. Begin upload policy at
300 s, 3 GiB source and 1 GiB native PCM, mono/stereo, 8–192 kHz only for the
qualified capture-application resource class. Other tools need measured equal
or narrower limits before joining that class. Native sample rate/channel count
and timeline must be preserved; analysis resampling stays separately recorded.
Set host-specific RSS and scratch quotas from fixture and actual-demo peaks
before implementation acceptance; an unknown resource limit is not admission.
Reserve low-string content around 32 Hz in acoustic preservation tests.

Worker launchers apply OS/container memory, process, disk and CPU constraints
appropriate to their approved host. Fixed interpreter/media binaries, thread
env, bounded stdout/stderr and input/output allowlists are required. GPU/model
jobs use distinct admitted resource classes and existing approved placement
after capacity checks; no implicit host daemon, checkpoint acquisition or GPU
claim. An HTTP timeout must never silently change the worker's ownership rules.

## Private scope and observability

The first web pilot remains loopback/private single-operator. A remotely hosted
milestone requires explicit workspace identity, per-source/run/artifact access
checks, TLS, authenticated agent credentials with narrow scope, browser session
and CSRF protection, upload quota/rate enforcement and approved retention. Use
the existing estate identity provider only after an actual integration review;
no new identity provider is implied. Future remote MCP needs its own transport
and authorization qualification rather than exposing stdio through a socket.

Never place original media, private filenames, signed artifact URLs, annotation
text or credentials in ordinary telemetry. Record request/job/tool IDs, timings,
resource peaks, error class and phase counts. Redact worker stderr before
browser responses and retain restricted diagnostic receipts separately.
Downloads are private by default. Retention/deletion policies cover uploads,
derived media, replicas, temporary files and backups; active leases prevent
premature cleanup. Keep source hashes in authorized provenance, not public logs.

## Proposed pilot SLOs and acceptance evidence

These are engineering targets, unmeasured and not an external SLA. Record host,
locked versions, fixture sizes, warm/cold state and load with every result.
Latency denominators include failed requests; report intentional invalid-request
counts separately. Never substitute a synthetic timing result for real listening
or native-editor/AU acceptance.

| Target | Denominator and test condition |
| --- | --- |
| Metadata p95 ≤250 ms | 1,000 authorized metadata requests, 10 concurrent clients, idle declared local host; all completed/failed requests counted |
| Job acceptance p95 ≤500 ms | 100 valid submissions and replays; excludes upload bytes, hashing and media probe, which are separate stages |
| Idle-queue start p95 ≤2 s | 50 admitted lightweight fixture jobs, one worker, no preceding job; loaded wait reported separately |
| Durable phase visible ≤2 s | 100 committed events, including reconnect/replay and slow-client cases |
| Cancel acknowledgement p95 ≤500 ms | 30 owned fixture jobs across validation/render/finalization; includes conflict outcomes |
| Observed stop ≤5 s after worker receives cancel | Same 30 bounded fixtures, measured process inspection/reaping; refusal or uncertainty fails this target and stays explicit |
| Every accepted job accounted after restart | 30 crash/failure injections around enqueue, lease, render and publication; zero lost job records or duplicate artifact publication |
| Every published output passes identity/timing gates | 20 meaningful generated/changed-input cases plus the exact actual demo; hash/native-clock/lineage gates pass before publication |

Compute throughput and completion-time objectives are deferred until separately
measuring representative 30/150/300 s clips and each admitted resource class.
Track queue time, work time, cancel/cleanup time and output publication separately.
Synthetic ground-truth/property tests exercise variable source offsets, VFR,
missing/extra boundaries, ambiguous notes, partial analysis, truncated uploads,
stale revisions and changed source/artifact identities. Failure tests include
expired leases, duplicate delivery, quota exhaustion, access denial, hash
mismatch, model absence and output committed before a transport failure.

## Milestone slices and tracker-ready work

These estimates are planning ranges, shared with the future goal lane, not
independent promises to spend the whole 35–70 hour next-week budget on hosting.
Prioritize local detection/tone evidence before a complete hosted product.

| Ticket title | Scope and definition of done | Estimate |
| --- | --- | --- |
| WEB-1: Generate artifact-ID capability adapters | Cover all 28 descriptor classifications; admit only qualified tools; reject paths/foreign IDs/unsupported knobs; preserve local contracts | 3–4 h |
| WEB-2: Persist bounded local jobs and publication | One operator/host, durable admission, fenced leases, exact retry reconciliation, bounded workers; restart and cancellation failure evidence | 4–6 h |
| WEB-3: Connect one upload-to-review vertical slice | Upload → probe → one restoration candidate → phase/status → compare/annotate → private download; demonstrate repeat/replay and changed-input rejection | 3–4 h |
| WEB-4: Qualify private hosting and resource policy | Auth/access, retention, download/upload policy, bounded output/log/RSS/disk admission and load/SLO receipts; actual host choice explicit | 6–10 h later |
| WEB-5: Qualify remote agent/AU parameter projections | Remote MCP auth/job lifecycle and explicit AU parameter maps; separate realtime constraints and host proofs | Estimate after WEB-1 and AU review |

WEB-1 through WEB-3 total 10–14 h for a narrow private prototype; failure to
qualify output confinement/resources reduces admitted scope rather than hiding
the gap. WEB-4 and WEB-5 remain queued. The demo walkthrough captures upload,
honest phase progress, cancel/retry, original/candidate/residual comparison,
source-timed observation, immutable iteration and download. A local GIF/video
may illustrate the flow; never upload private media to an external GIF service
without separate authorization. Graphical overlays and their licenses live in
the UI/overlay lanes; this backend carries their evidence and source clocks.
