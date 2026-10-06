# S2 web_stack lane contract: SvelteKit + Effect v4 + Skeleton v5 fixture and control-layer decision

Status: **Phase 1 contract freeze**, 2026-10-06; **Phase 2 implemented** 2026-10-06
(record in section 13, receipt `web_stack-build-receipt.json`). Lane `web_stack`, workflow D,
wave 2, branch `sprint/20261006-s2/web_stack`, worktree `.local/sprint2/web_stack`.
Tracker: Linear TIN-5613 (related TIN-5551; sibling lane `web_jobs` TIN-5614).
Baseline: `e0da4ca04930ee9a89a83eec402f060366c5d30d`.
Authority: S2 sprint manifest `program/sprints/20261006-s2.json`, repository
`AGENTS.md`, R-HOOK-CONVERGENCE-20261004 / R-N11/R-N12/R-N13. Root administers
review, signed merge, `just` recipes, publication and Linear. This lane never
pushes, merges, writes Linear, edits root-owned files, downloads models, starts
a host daemon or deploys anything.

Design sources reused, not re-decided:
[web UI framework qualification](../../research/2026-10-06-web-ui-framework-qualification.md),
[WEB_UI_DESIGN](../future/WEB_UI_DESIGN.md) (upload/process/compare/annotate/
iterate/download flow, compact overlay), [WEB_BACKEND](../future/WEB_BACKEND.md)
(BFF + control API, `/api/v1` routes, job states, private loopback pilot),
`review/*` (existing local visual language: dark neutral surface, source-time
first, explicit evidence labels).

## 1. Scope

In scope:

1. `web/`: a new, self-contained SvelteKit 2 application (Svelte 5 runes,
   Effect 4, Skeleton 5 on Tailwind 4, `adapter-node`) with a committed
   `pnpm-lock.yaml` and exact version pins (section 3).
2. A server-only control-API client (Effect program, Effect Schema decoding)
   reached exclusively through **stable** SvelteKit server surfaces:
   `+page.server.ts` `load` functions and `+server.ts` endpoints. The browser
   never contacts the control API directly.
3. Routes: `/` (sources), `/jobs/[id]` (status polling), `/api/sources` and
   `/api/jobs/[id]` (BFF JSON endpoints), and clearly labelled prototype
   placeholders `/upload`, `/compare`, `/review`, `/download`.
4. A loopback-only launcher `web/serve.js` around the adapter-node output.
5. `tests/test_web_stack.py`: static contract checks plus a node-gated
   build/integration test against a stdlib mock control API (section 7).
6. Control-layer decision record (section 6) and dated receipts under
   `docs/agent-notes/sprints/20261006-s2/web_stack-*.json`.

Out of scope (explicitly not claimed): the control API itself (owned by
`web_jobs`), uploads, job submission/cancellation, annotations, playback,
any DSP/FFmpeg/analysis, SvelteKit remote functions (section 6.3), SSE events,
identity/auth/CSRF for remote use, hosted deployment, browser hydration or
visual acceptance, accessibility conformance, listening acceptance, AU work,
and any default detector/profile/master change. Prototype screens render a
label only; they expose no control that implies a supported tool argument.

## 2. Owned files

| Path | Role |
| --- | --- |
| `web/package.json`, `web/pnpm-lock.yaml`, `web/.npmrc` | Exact pins, lock, `engine-strict`; no registry credentials |
| `web/.gitignore` | `node_modules/`, `build/`, `.svelte-kit/`, `.env*`, `*.log` |
| `web/svelte.config.js`, `web/vite.config.ts`, `web/tsconfig.json` | adapter-node; dev/preview `host: '127.0.0.1'`, `strictPort: true`; no experimental flags |
| `web/serve.js` | Loopback-only launcher for `build/` (section 5.4) |
| `web/src/app.html`, `web/src/app.css`, `web/src/app.d.ts` | Shell, Tailwind 4 + Skeleton 5 theme import |
| `web/src/lib/schema/control.ts` | Effect Schemas for the assumed control-API subset (section 4) |
| `web/src/lib/server/config.ts` | Env read + loopback URL validation |
| `web/src/lib/server/control-client.ts` | Effect client: bounded fetch, timeout, size cap, decode, tagged errors |
| `web/src/lib/polling.js` | Pure polling policy (JS + JSDoc, `checkJs`) testable by plain `node` |
| `web/src/lib/components/*.svelte` | `PrototypeNotice`, `UnknownValue`, `JobStateBadge`, `ControlApiError` |
| `web/src/routes/**` | Routes listed in section 1 |
| `web/fixtures/control-api/*.json` | Synthetic mock responses (no host paths, no private filenames) |
| `tests/test_web_stack.py` | Lane test module |
| `docs/spec/sprints/WEB_STACK_S2.md` | This contract |
| `docs/agent-notes/sprints/20261006-s2/web_stack-*.json` | Dated receipts |

Generated outputs (`web/node_modules`, `web/build`, `web/.svelte-kit`) are
gitignored. Lane measurement files go only under
`.local/sprint2/web_stack/artifacts/s2/web_stack/` (repo-gitignored). Nothing is
written under `artifacts/runs/*`, `/Users/jess/Documents` or `/Users/jess/Desktop`.

## 3. Frozen toolchain and exact pins

Registry versions observed 2026-10-06 via `pnpm view` (measurement of the
public registry, not of local compatibility). Every `dependencies` and
`devDependencies` value is an exact `MAJOR.MINOR.PATCH` string: no `^`, `~`,
`*`, `x`, ranges, tags, `workspace:`, `file:`, `link:`, git or URL specifiers.
This applies to dev dependencies too (stricter than the minimum DoD).

| Package | Pin | Reason / constraint observed |
| --- | --- | --- |
| `@sveltejs/kit` | `2.70.3` | Latest 2.x. npm `latest` is **3.0.1**; DoD and research require pinning Kit 2. Kit 3 migration is a recorded follow-up, not this lane. |
| `svelte` | `5.57.1` | Runes; satisfies vite-plugin-svelte `^5.46.4`, skeleton-svelte `^5.40.0` |
| `@sveltejs/adapter-node` | `5.5.7` | Peer `@sveltejs/kit ^2.4.0`. `6.0.0` (latest) assumed Kit 3 line; not used. |
| `@sveltejs/vite-plugin-svelte` | `7.3.1` | Kit 2.70.3 peer accepts `^7.0.0`; requires vite 8 |
| `vite` | `8.3.3` | Kit peer `^8.0.0` |
| `effect` | `4.0.1` | Stable Effect 4 (`latest`); Schema imported from the core package |
| `@skeletonlabs/skeleton` | `5.0.1` | Peer `tailwindcss ^4.0.0` |
| `@skeletonlabs/skeleton-svelte` | `5.0.1` | Peer `svelte ^5.40.0` |
| `tailwindcss`, `@tailwindcss/vite` | `4.3.3` | Skeleton 5 styling layer |
| `typescript` | `6.0.3` | npm `latest` is 7.0.2, but Kit 2.70.3 and svelte-check 4.7.6 peers accept only `^5 \|\| ^6` |
| `svelte-check` | `4.7.6` | `pnpm run check` |
| `@types/node` | exact latest 22.x at install | Node 22 runtime types; exact value recorded in the install receipt |

Runtime: node `v22.23.2` (`engines.node: ">=22.12 <23"`), `packageManager:
"pnpm@11.25.0"`. Phase 2 may change a pin **only** when `pnpm install` reports
an actual peer/engine conflict; the receipt records the old pin, new pin and the
verbatim conflict line. No pin changes for preference or to chase newer releases.

### 3.1 Phase 2 toolchain observations (no pin changed)

All twelve frozen pins installed without a peer/engine conflict; `@types/node`
resolved to `22.20.5` (latest 22.x on 2026-10-06). Observed on the lane host:

1. pnpm 11.25.0 reads package-manager settings from `web/pnpm-workspace.yaml`,
   not `.npmrc`; `.npmrc` keeps only `save-exact=true` and comments (no
   credentials). `pnpm-workspace.yaml` sets `strictPeerDependencies: true` and
   `verifyDepsBeforeRun: error` (a script fails instead of silently running an
   online install when dependencies are stale).
2. pnpm added `minimumReleaseAgeExclude: [vite@8.3.3]` itself during the first
   install (vite 8.3.3 is younger than pnpm 11's default minimum release age).
   It is committed so frozen installs are reproducible; it is a recorded supply-
   chain exception, not a preference.
3. `engine-strict` is **not** enforced. This host's pnpm runs on its own bundled
   Node runtime (v24.19.0), so pnpm's engine check evaluates that runtime, not the
   `node` on PATH (v22.23.2) that runs svelte-check, vite, the tests and
   `serve.js`. With `engineStrict` on, `pnpm run check` failed with
   `ERR_PNPM_UNSUPPORTED_ENGINE ... Got: v24.19.0`. The `engines` field stays
   declarative and pnpm prints an advisory warning.
4. A first `pnpm install --offline` after the resolving install failed the
   supply-chain policy check with `ERR_PNPM_NO_OFFLINE_META` (package metadata
   not cached). One online `pnpm install --frozen-lockfile` populated the
   metadata cache; afterwards offline frozen installs from an empty
   `node_modules` succeeded. A fresh host therefore needs one online frozen
   install before `--offline` works.

## 4. Control-API boundary (assumed S2 subset, mocked in tests)

The `web_jobs` contract was not yet written at freeze time (no
`WEB_JOBS_S2.md` in its worktree). This lane therefore freezes a **minimal
assumed subset** of the WEB_BACKEND `/api/v1` design and hands the exact
shapes to root/`web_jobs` for alignment (section 9). Receipts carry
`control_api_contract_source: "assumed_s2_subset_pending_web_jobs"` and
`web_jobs_contract_sha256: null` until a merged web_jobs spec exists.

Configuration: `VIDEO_UTILS_CONTROL_API_URL` via `$env/dynamic/private`, e.g.
`http://127.0.0.1:8790`. Accepted only when scheme is `http`, host is exactly
`127.0.0.1` or `[::1]`, a port is present, and path/query/fragment/userinfo are
empty. Anything else (including `localhost`, `0.0.0.0`, LAN or public hosts) is
refused before any network call with `control_api_refused_host`. Unset/empty is
a valid state, `control_api_unconfigured`, rendered as a status message.

| Upstream request | Effect Schema (closed; unknown keys rejected) |
| --- | --- |
| `GET /api/v1/sources` | `{ schema_version: 1, sources: SourceSummary[] (0..500) }` |
| `GET /api/v1/jobs/{job_id}` | `JobSnapshot` |

`SourceSummary`: `source_id` (opaque, `^[A-Za-z0-9_-]{1,128}$`), `label`
(string 1..200), `validation_state` (`pending`, `valid`, `rejected`,
`unknown`), `source_sha256` (64 lowercase hex **or null**), `duration_seconds`
(finite ≥0 **or null**), `sample_rate_hz` (integer 1..768000 **or null**),
`channels` (integer 1..64 **or null**).

`JobSnapshot`: `schema_version: 1`, `job_id` (opaque pattern above), `tool`
(string 1..64), `state` (`queued`, `validating`, `running`, `finalizing`,
`succeeded`, `failed`, `interrupted`, `needs_reconciliation`, `cancelling`,
`cancelled`), `phase` (string **or null**), `source_id` (opaque **or null**),
`created_utc` / `updated_utc` (ISO-8601 Z strings), `progress` =
`{ completed: integer ≥0, denominator: integer ≥1, unit: string }` **or null**
(a fraction is displayed only when this object exists; otherwise "Unknown"),
`eta_seconds` (finite ≥0 **or null**, displayed as an estimate, separate from
elapsed), `error_class` (string **or null**), `limitations` (string[] 0..32).

Client bounds: request timeout 5000 ms (`control_api_timeout`), response body
cap 1 MiB counted while streaming (`control_api_too_large`), `Accept:
application/json`, no redirects followed (`redirect: 'manual'` →
`control_api_http_error`), no cookies/credentials forwarded, no retries inside
one request. Effect tagged errors, each mapped to one stable code:
`control_api_unconfigured` (503), `control_api_refused_host` (503),
`control_api_unreachable` (502), `control_api_timeout` (504),
`control_api_http_error` (502, upstream status recorded), `control_api_too_large`
(502), `control_api_decode_error` (502, Schema issue paths only),
`invalid_job_id` (400, validated before any network call), `job_not_found`
(404, upstream 404). BFF error bodies are `{ status: "error", code, message,
upstream_status: int|null }`; raw upstream bodies and stack traces are never
returned. Upstream 404 for a job is not a decode error.

Interruption of a browser request (navigation, tab close) aborts only the
outgoing fetch; it never implies job cancellation. S2 exposes no cancel action.

## 5. Routes and behavior

5.1 `/` — server `load` calls `GET /api/v1/sources`; renders a table of
sources with every nullable field shown as the literal **Unknown**
(`UnknownValue` component), never `0`, blank or `NaN`. Error codes render via
`ControlApiError` with the code visible. Global prototype banner: "Prototype —
local loopback fixture; no processing is started from this page."

5.2 `/jobs/[id]` — `id` validated against the opaque pattern before any call
(SvelteKit param matcher `jobid`; invalid ids 404 without upstream request).
SSR renders the snapshot; client polling then calls `/api/jobs/[id]`. Polling
policy in `src/lib/polling.js` (pure, frozen constants): base interval 2000 ms;
stop on terminal states `succeeded`, `failed`, `cancelled`,
`needs_reconciliation`, `interrupted`; on error, exponential backoff ×2 capped
at 30000 ms; after 5 consecutive errors stop with `polling_paused` and a manual
**Refresh** button; pause while `document.visibilityState === 'hidden'`. Runes
hold only UI state (`$state`, `$derived`, `$effect` with cleanup); job
authority remains server-side. Progress shows `completed / denominator unit`
only when `progress` is non-null; ETA labelled "estimate".

5.3 Prototype routes `/upload`, `/compare`, `/review`, `/download` render
`PrototypeNotice` with the WEB_UI_DESIGN step name, "Not implemented in S2",
and a link to the design doc. They contain no `<form>`, no `<input>` and no
mutating endpoint.

5.4 Listening surfaces. Vite dev/preview: `host: '127.0.0.1'`,
`strictPort: true`. adapter-node's own default `HOST` is `0.0.0.0`, so the only
supported production start is `node serve.js` (`pnpm start`), which sets
`HOST` to `127.0.0.1` when unset, **refuses** (exit code 2, before importing the
server) any `HOST` other than `127.0.0.1` / `::1`, then imports
`./build/index.js`. Sources contain no `0.0.0.0` or `host: true`. No hosted
deployment, no service manager unit, no background process outside tests.

5.5 Visual language: Skeleton 5 theme tokens with a dark neutral surface and
monospace source-time values echoing `review/style.css`; only Skeleton CSS
utilities plus at most two Skeleton Svelte components are used in S2 (actual
list recorded in the receipt as `skeleton_components_used`). No visual or
accessibility claims follow from the build.

## 6. Control-layer decision

### 6.1 Decision

**Now (S2): SvelteKit server (BFF) + stdlib Python control API. Later:
FastAPI behind the same HTTP/JSON contract, when its triggers are met.**

### 6.2 Reasons

1. **Stdlib-first repository rule.** The Python side is stdlib-first and this
   sprint forbids `pip install`. A FastAPI control API needs Starlette,
   Pydantic and an ASGI server, each requiring a lock, qualification and
   supply-chain review that S2 cannot honestly complete.
2. **Existing qualified pattern.** `scripts/review_server.py` already serves a
   loopback `ThreadingHTTPServer` with Host/Origin checks and revision-checked
   mutations, and `scripts/tool_api.py` is the validated stdlib dispatcher. A
   stdlib control API (`web_jobs`) reuses both without a new runtime.
3. **The BFF isolates the choice.** The browser talks only to SvelteKit; the
   control API stays loopback-only with no CORS surface. Because the BFF
   depends only on the HTTP/JSON shapes in section 4 (decoded by Effect
   Schema), replacing the stdlib server with FastAPI later changes no browser
   code and no Svelte route, only the upstream process.
4. **Typed boundary on the TypeScript side.** Effect Schema decoding plus tagged
   errors give one place where malformed, oversized, slow or missing upstream
   responses become stable, user-visible codes, matching the "explicit
   unknowns" doctrine (nullable fields stay nullable through to the UI).
5. **adapter-node, not adapter-static.** Server `load`/endpoints that call a
   private API need a server runtime; a static adapter cannot provide them.
6. **Single operator, single host.** WEB_BACKEND's pilot is loopback and
   single-operator; stdlib threading is adequate until measured otherwise.
7. **No second scheduler.** Job authority, durability and workers stay in
   Python (`web_jobs`); the Node process holds no queue, timers or job state.

FastAPI triggers (any one, measured or operator-decided): generated OpenAPI
client needed by more than one consumer; SSE/event streaming beyond a polling
fallback; authenticated remote access (identity, CSRF, sessions); concurrency
or validation volume that the stdlib server measurably fails; operator
approval of the dependency set. Effect HTTP as the control API remains rejected
until an Effect 4 job/storage qualification (WEB_BACKEND framework table).

### 6.3 Remote functions not adopted in S2

SvelteKit remote functions are experimental in Kit 2 (opt-in flag) and the
current upstream docs describe Kit 3 configuration; the research note also
found no proven Effect 4 Standard-Schema input adapter. S2 therefore uses the
stable `load` + `+server.ts` path only and records
`remote_functions_qualified: false`. A later lane may add them behind the same
control client after pinning the Kit major they target.

## 7. Test protocol

Module: `tests/test_web_stack.py`, run from the worktree root as
`PYTHONPATH=tests python3 -m unittest test_web_stack -v`. Stdlib only.

Class `WebStackStaticTests` (always runs; no node required):

| ID | Assertion |
| --- | --- |
| S1 | `web/pnpm-lock.yaml` exists, non-empty, has `lockfileVersion`; `web/package.json` exists |
| S2 | Every `dependencies`/`devDependencies` value matches `^\d+\.\d+\.\d+$`; none starts with `^`/`~`; required packages present with majors kit=2, svelte=5, effect=4, skeleton=5, skeleton-svelte=5, adapter-node present; `packageManager == "pnpm@11.25.0"` |
| S3 | Each lock `importers['.']` specifier equals the `package.json` value (stdlib line parse of the lock) |
| S4 | `svelte.config.js` imports `@sveltejs/adapter-node`; no `adapter-static`/`adapter-auto`; no `remoteFunctions` |
| S5 | `web/.gitignore` lists `node_modules`, `build`, `.svelte-kit`, `.env`; `git ls-files web` contains none of them |
| S6 | Secret/host-path scan over git-tracked + to-be-committed files under `web/` (excluding `node_modules/`, `build/`, `.svelte-kit/`) and `web_stack-*.json` receipts (this spec is excluded because it lists the patterns): zero hits for `/Users/`, `/home/`, `/private/`, `/Volumes/`, `/nix/store/`, `C:\`, `_authToken`, `npm_[A-Za-z0-9]{36}`, `ghp_`, `github_pat_`, `-----BEGIN`, `AKIA[0-9A-Z]{16}`; no tracked `.env*`; `.npmrc` has no auth/registry-credential lines |
| S7 | Loopback: `vite.config.ts` has `host: '127.0.0.1'` for server and preview; no `0.0.0.0` or `host: true` in `web/` sources; `package.json` `start` script is `node serve.js` |
| S8 | Prototype route files contain the prototype label and no `<form` / `<input` |
| S9 | Fixture JSON files parse, contain no host paths, and cover the cases in N4 |

Class `WebStackBuildTests` (skips with an explicit reason when `node` or
`pnpm` is not on PATH, or when an offline install reports packages missing from
the local store; any other install/check/build failure **fails**):

| ID | Assertion (timeouts: install 300 s, check 300 s, build 300 s) |
| --- | --- |
| B1 | `pnpm install --frozen-lockfile --offline` exits 0 |
| B2 | `pnpm run check` exits 0 with 0 errors |
| B3 | `pnpm run build` exits 0; `web/build/index.js`, `web/build/handler.js` and `web/build/client/` exist |
| B4 | `node serve.js` with `HOST=0.0.0.0` exits 2 without listening |
| B5 | `node src/lib/polling.js`-based check (plain `node --input-type=module`): terminal states stop; backoff sequence 4000, 8000, 16000, 30000 capped; 5 errors → `polling_paused` |

Class `WebStackIntegrationTests` (same skip rule; depends on B3 output):
a stdlib `ThreadingHTTPServer` mock control API on `127.0.0.1:0` serves
`web/fixtures/control-api/*.json` and counts requests; the built app runs via
`node serve.js` with `HOST=127.0.0.1`, an ephemeral `PORT`, and
`VIDEO_UTILS_CONTROL_API_URL` pointing at the mock; both are terminated in
`tearDown` (process group, 10 s bound). Cases N1–N12:

| ID | Case → expected |
| --- | --- |
| N1 | `/` with valid sources → 200, fixture labels present, null fields render "Unknown" |
| N2 | `/api/jobs/job_running` → 200, `state: running`, `progress: null` preserved |
| N3 | `/api/jobs/job_progress` → 200, `progress.denominator ≥ 1` preserved |
| N4 | `/jobs/job_succeeded` SSR → 200, contains state and source time fields |
| N5 | Unknown key / bad enum in job fixture → 502 `control_api_decode_error`, body lacks upstream text |
| N6 | Upstream 500 → 502 `control_api_http_error`, `upstream_status: 500` |
| N7 | Upstream 404 → 404 `job_not_found` |
| N8 | Mock delay 7 s → 504 `control_api_timeout` within 6.5 s |
| N9 | Mock body > 1 MiB → 502 `control_api_too_large` |
| N10 | `/api/jobs/..%2Fetc` and `/api/jobs/a%20b` → 400 `invalid_job_id`; mock request count unchanged |
| N11 | Restart app with URL unset → `/` 200 with `control_api_unconfigured`; `/api/jobs/x` 503 |
| N12 | Restart app with `http://192.0.2.1:9` and `http://localhost:9` → 503 `control_api_refused_host` returned < 1 s; `/upload` 200 with prototype label |

Optional socket check (recorded, not a test failure if the tool is absent):
`lsof -nP -iTCP -sTCP:LISTEN -a -p <pid>` for the node and mock pids shows only
`127.0.0.1` listeners; otherwise `listen_address_verified: null`.

Directly affected existing modules: none (no shared file is edited). Root runs
the full suite.

## 8. Completion metrics (with denominators and claim classes)

Claim classes: `static_repository_check` (file/text inspection),
`local_build_check` (commands on the lane host, this lock), `synthetic_mock_integration`
(built app against the stdlib mock). None of these is browser, accessibility,
visual, listening, hosted or real-control-API evidence.

| ID | Metric | Pass condition | Class |
| --- | --- | --- | --- |
| M1 | Declared npm dependencies with exact pins | n_exact / n_declared = 1 (both counts reported) | static |
| M2 | Lock importer specifiers equal to package.json | n_match / n_declared = 1 | static |
| M3 | Offline frozen install after one online install | 1/1 exit 0 on the lane host; online install seconds and offline install seconds recorded | local_build |
| M4 | `pnpm run check` | 1/1 exit 0; error count 0; warning count reported | local_build |
| M5 | `pnpm run build` | 3/3 exit 0 from clean `build/` + `.svelte-kit/`; wall seconds per run, median and min–max reported (no target) | local_build |
| M6 | Lock identity | `pnpm-lock.yaml` sha256 recorded; equals committed file sha256 | static |
| M7 | Static test assertions | S1–S9 passing / 9 | static |
| M8 | Build test assertions | B1–B5 passing / 5 (or skipped with reason, counted separately) | local_build |
| M9 | Integration cases | N1–N12 passing / 12 | synthetic_mock_integration |
| M10 | Secret / host-path hits | 0 hits over n scanned files (n reported) | static |
| M11 | Non-loopback listeners during tests | 0 / n observed listeners, or `null` if unverifiable | local_build |

Experimental non-improvement does not apply (no experiment). A pin change,
skipped build class or unmet case is reported, not hidden.

## 9. Unknown / abstain fields the outputs must carry

Every lane receipt (`web_stack-*.json`) carries, explicitly, even when null or
false:

```json
{
  "control_api_contract_source": "assumed_s2_subset_pending_web_jobs",
  "web_jobs_contract_sha256": null,
  "remote_functions_qualified": false,
  "browser_hydration_checked": false,
  "accessibility_checked": false,
  "visual_acceptance": "not_performed",
  "hosted_deployment": false,
  "listen_address_verified": null,
  "offline_install_verified": null,
  "skeleton_components_used": [],
  "kit3_migration": "deferred",
  "pnpm_store_location": "not_recorded_host_specific",
  "lock_sha256": null,
  "build_seconds": null
}
```

The UI carries **Unknown** for every nullable `SourceSummary`/`JobSnapshot`
field and never derives a percentage without `progress.denominator`.

## 10. Experiment / preregistration

This lane runs **no experiment**: no arms, truth set, seeds, scoring or
held-out data, and no numerics or media. Build/install timings are descriptive
measurements of one host with protocol fixed here (M3, M5), not comparisons.
`preregistered: false` because there is nothing to preregister.

## 11. Phases

1. Contract freeze (this document + `web_stack-contract-freeze.json`).
2. Implementation of `web/` and `tests/test_web_stack.py`; one online
   `pnpm install` to create the lock (npm registry only, pinned versions).
3. Measurements M1–M11 → `web_stack-build-receipt.json` (versions, lock sha256,
   install/check/build seconds, test counts, unknown fields).
4. Handoff → `web_stack-handoff.json` with root-owned requests (below).

## 12. Root-owned changes requested (not made by this lane)

`just/workflow.just` additions (root decides placement):

```just
# Local web fixture (prototype). Loopback only; no hosted deployment.
web-install:
    cd web && pnpm install --frozen-lockfile

web-dev port="5173":
    cd web && pnpm exec vite dev --host 127.0.0.1 --port {{quote(port)}} --strictPort

web-build:
    cd web && pnpm install --frozen-lockfile --offline && pnpm run check && pnpm run build

web-serve port="3000" control_api="":
    cd web && HOST=127.0.0.1 PORT={{quote(port)}} VIDEO_UTILS_CONTROL_API_URL={{quote(control_api)}} node serve.js
```

To `web_jobs` / root: add `GET /api/v1/sources` (list) to the control API, or
confirm an alternative; align `JobSnapshot` and `SourceSummary` (section 4),
in particular nullable `progress` with an explicit denominator and nullable
`eta_seconds`. Until aligned, the BFF schema is an assumption, not a contract.

## 13. Phase 2 implementation record

Implemented exactly as sections 1-7 with these recorded additions (none relaxes
a frozen rule):

- `web/pnpm-workspace.yaml` (section 3.1) is an additional owned file.
- `web/src/lib/control-types.ts` holds the client-safe `BffError` type so
  components never import `$lib/server/*`.
- `serve.js` also refuses `SOCKET_PATH` (exit 2); S2 serves only a loopback TCP
  port. B4 checks `HOST` values the wildcard address, `localhost` and
  `192.0.2.1`.
- Control-URL validation is a strict pattern: `http://127.0.0.1:<port>` or
  `http://[::1]:<port>` with an optional trailing `/` and port 1..65535.
- Decode-error messages list Schema issue paths whose segments are schema field
  names or indexes; any other key is rendered `<unexpected_key>` so neither
  upstream values nor upstream key names are echoed.
- N9 has two subcases: declared `Content-Length` over the cap, and a streamed
  body without `Content-Length` (counted while reading).
- N13 is the optional M11 listener check (`lsof`), for the app and the mock;
  it skips with `listen_address_verified: null` when `lsof` is absent.
- The build/integration skip rule also skips when this host's pnpm storage gate
  exits 75 (EX_TEMPFAIL, storage unavailable); any other failure fails.
- Skeleton Svelte components used: `Progress` only (shown only when
  `progress.denominator` is reported).

Measured results, unknowns and denominators are in
`docs/agent-notes/sprints/20261006-s2/web_stack-build-receipt.json`; handoff and
root-owned requests in `web_stack-handoff.json`.

