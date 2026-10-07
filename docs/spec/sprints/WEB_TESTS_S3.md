# S3 web_tests lane contract: vitest, Playwright and axe for the web app, plus the house-stack contract

Status: **Phase 1 contract freeze**, 2026-10-07. Lane `web_tests`, sprint
`20261007-s3`, branch `sprint/20261007-s3/web_tests`, worktree
`.local/sprint3/web_tests`. Tracker: Linear TIN-5724.
Baseline: `05a13f209a84eed24f5be592105d164a5cd6205c`.
Authority: `docs/spec/sprints/20261007-S3.md` (stack row and the estate P0
rule "latest Skeleton v5 and latest Effect everywhere"), repository
`AGENTS.md`, R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13.
Root administers review, signed merge, `just` recipes, CI, publication and
Linear. This lane never pushes, merges, writes Linear, edits root-owned or
other lanes' files, downloads models, starts a daemon, or changes web source.

No test, install, build, browser or axe run was executed in this phase. The
only commands run were read-only inspection, `gh api` reads of two estate
default branches and `npm view <pkg> version` (section 3).

## 1. Scope

In scope:

1. **Unit tests (vitest)** for the pure web modules: Effect Schema decoders,
   server form and option builders, the job-request builder, the idempotency
   helper, Cloudflare Access JWT verification with a key generated at test
   run time, the auth mode/allowlist/gate modules, refusal-text mapping,
   polling policy and review logic (section 5.1).
2. **End-to-end tests (Playwright, Chromium only)** against the built
   adapter-node app started by `node serve.js` on loopback with a mocked
   control API replaying committed synthetic fixtures (section 5.2).
3. **Accessibility measurement (@axe-core/playwright)** on every route in
   section 5.3, recorded per route with denominators, ratcheted by a committed
   baseline. The lane changes no web source; needed source fixes are reported
   to root.
4. **House-stack contract** `tests/test_web_house_stack_s3.py` (Python stdlib,
   runs in CI without node) pinning latest Skeleton v5 and latest Effect
   (section 5.4).
5. **Tooling**: exact-pinned devDependencies and scripts in `web/package.json`,
   updated `web/pnpm-lock.yaml`, `web/vitest.config.ts`,
   `web/playwright.config.ts`.
6. **Hand-offs to root** (text only, section 8): `just` recipes `web-unit`,
   `web-e2e`, `web-a11y`; a CI job proposal; any source accessibility fixes.
7. **Receipts** under `docs/agent-notes/sprints/20261007-s3/web_tests-*.json`.

Out of scope (explicitly not claimed): any change to `web/src` non-test
files, `web/vite.config.ts`, `web/tsconfig.json`, `web/pnpm-workspace.yaml`,
`web/.gitignore`, `web/serve.js` or `web/fixtures/`; Firefox/WebKit; visual
regression; performance budgets; screen-reader or manual assistive-technology
acceptance; tailnet-mode end-to-end with a real Cloudflare Access team; real
media, real-take facts or the real control API under Playwright (the existing
Python modules already exercise the real `scripts/web_api.py` in process);
any DSP, detector, profile, master, listening or note-correctness claim;
upgrades of runtime pins (SvelteKit, Svelte, TypeScript, Vite stay as they
are; newer majors on npm are recorded in section 3 as observations only).

## 2. Owned files

| Path | Role |
| --- | --- |
| `docs/spec/sprints/WEB_TESTS_S3.md` | This contract |
| `web/package.json` | Adds devDependencies and scripts only (section 4); no existing pin changes |
| `web/pnpm-lock.yaml` | Regenerated for the added devDependencies only |
| `web/vitest.config.ts` | Standalone vitest config (does not edit `vite.config.ts`) |
| `web/playwright.config.ts` | Chromium project, loopback, one worker, outputs outside `web/` |
| `web/src/**/*.test.ts` | Unit tests next to the module under test (section 5.1) |
| `web/tests/` | Shared unit-test helpers and fixture loaders (no `.test.ts` outside `web/src`) |
| `web/e2e/*.spec.ts` | Playwright specs (section 5.2, 5.3) |
| `web/e2e/global-setup.ts`, `web/e2e/global-teardown.ts` | Start/stop the mock and the built app (own process group only) |
| `web/e2e/mock-control-api.mjs` | `node:http` loopback mock replaying fixtures; request log for assertions |
| `web/e2e/fixtures/control-api/*.json`, `web/e2e/fixtures/README.json` | Committed synthetic responses in real `/api/v1` shapes |
| `web/e2e/fixtures/generate.py` | Regenerates the fixtures from the real control API over synthetic inputs |
| `web/e2e/a11y-baseline.json` | Ratchet of recorded axe violations (may be empty) |
| `tests/test_web_house_stack_s3.py` | House-stack contract and static lane checks (no node needed) |
| `docs/agent-notes/sprints/20261007-s3/web_tests-*.json` | Dated receipts (section 6) |

Run outputs (reports, traces, screenshots, raw axe JSON) go to
`artifacts/s2/web_tests/` in the worktree (gitignored), never under `web/` and
never under an accepted `artifacts/runs/*` directory.

## 3. Sources read (remote default branches only; read 2026-10-07)

Estate facts were read with `gh api repos/<owner>/<repo>/contents/<path>?ref=<sha>`
against the remote default branch head, so no sibling working tree was read
and no sibling repository ref was changed.

| Source | Head (commit date, UTC) | Stated by the source | Used here as |
| --- | --- | --- | --- |
| `tinyland-inc/site.scaffold` `main` | `9fef9eea73cb` (2026-10-06T01:35:12Z) | `vitest.config.ts`: `environment: 'node'`, `$lib` alias, include `src/**/*.test.ts`. `playwright.config.ts`: `testDir ./e2e`, chromium project, `PLAYWRIGHT_PORT`, `PLAYWRIGHT_WORKERS`, `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`, one worker in CI. `src/lib/house-stack-contract.test.ts`: Skeleton pair EXACT `5.0.1`, TypeScript exact on the 6.0.x line, packageManager exact, no direct `@zag-js`. `package.json`: `vitest ^4.1.10`, `@playwright/test ^1.62.1`, `effect ^3.22.1` | Layout and naming (`web/e2e/`, `src/**/*.test.ts`), env-var names, exact-pin style of the contract |
| `xoxd-ai/tinyland.dev` `main` (local remote name `github`) | `7422982619e3` (2026-10-02T18:13:22Z) | `package.json`: `@axe-core/playwright ^4.12.1`, `axe-core ^4.13.0`, `fast-check ^4.9.0`, `@fast-check/vitest ^0.4.1`, `@playwright/test ^1.62.1`, `vitest ^4.1.10`, Skeleton `^4.15.2`. `playwright.accessibility.config.ts`: separate a11y config, JSON reporter file, `retries: 0`, `video: off`. `playwright.a11y-hydration.config.ts`: `testMatch '**/a11y-*.spec.ts'` | Separate a11y project with a JSON report and zero retries; fast-check for properties |

Inferences by this lane (not stated by the sources): caret ranges in both
estate repos are not adopted (this repo's `test_web_stack` S2 requires exact
pins); tinyland.dev's Chromium launch flags (`--disable-web-security`,
`--no-sandbox`) are **not** adopted because they would weaken the same-origin
behaviour the BFF tests rely on; site.scaffold's Effect 3 range and
tinyland.dev's Skeleton 4 range are estate drift owned by those repositories
(see `docs/agent-notes/2026-10-07-estate-stack-claim-correction.md`), not a
model for this repo.

npm `latest` observed 2026-10-07T09:50:24Z with `npm view <pkg> version`
(measurement of the registry at that instant; must be re-run and re-recorded
when the tests are written):

| Package | npm latest | Current pin in `web/package.json` | Note |
| --- | --- | --- | --- |
| `@skeletonlabs/skeleton` | 5.0.1 | 5.0.1 | contract pin |
| `@skeletonlabs/skeleton-svelte` | 5.0.1 | 5.0.1 | contract pin |
| `effect` | 4.0.1 | 4.0.1 | contract pin |
| `svelte` | 5.57.2 | 5.57.1 | contract is `5.x` exact; patch drift is an observation |
| `vitest` | 5.0.3 | absent | candidate (section 4) |
| `@playwright/test` | 1.63.0 | absent | candidate |
| `@axe-core/playwright` | 4.13.0 | absent | candidate |
| `axe-core` | 4.14.0 | absent | transitive unless a peer requires a direct pin |
| `fast-check` | 4.10.2 | absent | candidate |
| `@sveltejs/kit` | 3.0.1 | 2.70.3 | observation only; not this lane's upgrade |
| `typescript` | 7.0.2 | 6.0.3 | observation only; not this lane's upgrade |

Host facts observed (not run): `node` v22.23.2 and `pnpm` 11.25.0 on PATH;
`/Applications/Google Chrome.app` reports 154.0.8037.98; the Playwright cache
holds `chromium-1243` and `chromium_headless_shell-1234`. Whether either
cached build is the revision the pinned Playwright expects is **unknown**
until Phase 2. `flake.nix` `core` has no `nodejs` or `pnpm`, so the nix dev
shell used by CI has no node today.

## 4. Dependency and configuration contract

1. Added devDependencies are exact versions (no `^`/`~`, no tag, no alias),
   so `test_web_stack` S2/S3 keep passing: `vitest`, `@playwright/test`,
   `@axe-core/playwright`, `fast-check`. A further direct pin (`axe-core`,
   `playwright`) is added only if strict peer dependencies require it, and is
   recorded with the reason.
2. Version choice rule, applied once at implementation and recorded in the
   pins receipt: the npm `latest` re-checked at that time, unless it is not
   installable against the locked `vite 8.3.3`, node `>=22.12 <23`,
   `strictPeerDependencies: true` or the pnpm release-age policy without
   editing `pnpm-workspace.yaml` (not lane-owned). In that case the newest
   version that installs is pinned and the rejected version and reason are
   recorded. No existing pin moves.
3. Scripts added: `test:unit` (`vitest run`), `test:e2e`
   (`playwright test --project=e2e`), `test:a11y`
   (`playwright test --project=a11y`). Existing scripts are unchanged.
4. `vitest.config.ts`: `environment: 'node'`, `include: ['src/**/*.test.ts']`,
   `$lib` alias, `passWithNoTests: false`, no coverage threshold claimed in S3,
   fast-check global seed fixed at `20261007` with `numRuns: 200` per property.
5. `playwright.config.ts`: `testDir './e2e'`; projects `e2e`
   (`*.spec.ts` except `a11y-*`) and `a11y` (`a11y-*.spec.ts`); Chromium only;
   `workers: 1`; `retries: 0`; `forbidOnly` in CI; base URL
   `http://127.0.0.1:<ephemeral port>` (never a fixed 3000, never `0.0.0.0`);
   reporters `list` plus JSON into `artifacts/s2/web_tests/`; `outputDir`
   under `artifacts/s2/web_tests/`; `video: 'off'`; no launch flag that
   disables web security or the sandbox.
6. Browser ladder, first match wins, recorded in the browser receipt:
   (a) `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`; (b) the Chromium revision the
   pinned Playwright expects, if already in the Playwright cache; (c)
   `channel: 'chrome'` when Google Chrome is installed; (d) a one-time
   `pnpm exec playwright install chromium`, allowed only with the download
   size, source host, revision and install path recorded; (e) typed skip
   `e2e_browser_unavailable` with every e2e and a11y metric reported as
   `not_run`, never as passed.
7. `global-setup.ts` refuses to run against a missing or stale build (any
   file under `web/src`, `web/serve.js` or `web/package.json` newer than
   `web/build/index.js`) with typed code `web_build_stale`; it never builds
   implicitly. It starts the mock on `127.0.0.1:0`, then `node serve.js` in
   its own process group with `HOST=127.0.0.1`, an ephemeral `PORT`,
   `VIDEO_UTILS_CONTROL_API_URL` and `VIDEO_UTILS_CONTROL_API_TOKEN` pointing
   at the mock, and `VIDEO_UTILS_AUTH_MODE` unset (loopback mode).
   `global-teardown.ts` signals only that process group (R-N11: own recorded
   processes only). No daemon outlives the run.
8. Fixture literals are low entropy: the mock token and every idempotency key
   in committed files are repeated-character or counter-style values that
   satisfy the app's patterns; no scanner allowlist is added. Test files never
   contain host paths or `0.0.0.0` (`test_web_stack` S6/S7 scan `web/`).
   The RSA key for JWT tests is generated in memory per run and never written.

## 5. Test protocol

### 5.1 Unit modules (vitest; `pnpm run test:unit`)

| Test file | Unit under test | Cases (minimum) |
| --- | --- | --- |
| `web/src/lib/schema/control.test.ts` | `control.ts` decoders: `SourceList`, `UploadResult`, `JobProjection`, `JobSummary`, `JobList`, `AnnotationRead`, `AnnotationWrite`, `DenoiseParameters`, `CaptureParameters`, `ApplyParameters`, `isJobId`, `isArtifactId` | Each of the 9 files in `web/fixtures/control-api/` decodes or is refused as its README case states (7 accept/refuse cases: 5 accept, `job_bad_unknown_key` and `job_bad_enum` refused); null `source_id`/`duration_seconds` with reasons survive decoding as null; property: adding any unknown key to an accepted object is refused (closed schema) |
| `web/src/lib/server/processing/schema.test.ts` | `JobTypes`, `RunList`, `ReviewList`, `Measurement`, `LaneJobProjection`, `RUN_ID_PATTERN`, `REVIEW_ID_PATTERN` | Every e2e fixture of that shape decodes; unknown key refused; unknown-field blocks are preserved, not defaulted |
| `web/src/lib/server/runs/schema.test.ts` | `RunSummary`, `RunList`, `RunGraph`, `RunLayers`, `Capabilities`, `UnknownFields`, `isEvidenceId`, `isMediaName` | Every e2e fixture decodes; `S2_UNKNOWN_KEYS`/`S3_UNKNOWN_KEYS` all present after decode; nullable BPM/tonic/phrase fields stay null; `Capabilities.tool_count` equals the fixture tool array length |
| `web/src/lib/server/processing/forms.test.ts` | `numeric`, `measurementBody`, `reviewBody`, `denoiseBody`, `authorBody`, `applyBody` | Typed refusals `run_required`, `interval_required`, `invalid_form_key`, `invalid_review_id`; accepted bodies carry exactly the documented keys; no high-pass, low-cut or notch key can be produced |
| `web/src/lib/server/processing/options.test.ts` | `renderableReviews`, `buildPresetOptions`, `groupKnobs`, `boundsText`, `overlapsSetup` | FULLER with no current review: disabled with `capture_interval_required`; with a valid `experimental_capture_render` review: enabled (the 2 UI states of ROUTES_PROCESSING M6); property: `overlapsSetup` is true exactly for intervals intersecting [0, 5) s |
| `web/src/lib/server/job-request.test.ts` | `buildJobRequest` | Accept; refuse bad idempotency key, bad source id, unknown knob, more than `MAX_PARAMETERS`; refusal is typed and nothing is sent |
| `web/src/lib/idempotency.test.ts` | `newFormKey`, `UI_KEY_PATTERN` | `ui` keys match the pattern; `ui-ann` prefix; 1,000 generated keys are distinct; keys come from `crypto.getRandomValues` (spy) |
| `web/src/lib/refusal-text.test.ts` | `refusalText` | Every code in the table maps to non-empty text that never equals the fallback; an unknown code maps to the fallback; no text contains upstream `error` passthrough placeholders, host paths or the control API URL; codes referenced by `forms.ts`, `options.ts` and the auth gate are listed with mapped/unmapped status (unmapped is reported, not failed, unless the code is shown to users without a message) |
| `web/src/lib/server/auth/cf-access.test.ts` | `verifyAccessAssertion`, `parseJwks`, `createJwksCache` | RS256 token signed by a run-time 2048-bit key verifies with injected fetch and clock; refused: wrong `aud`, wrong `iss`, expired, `nbf` in the future beyond skew, tampered signature, `alg: none`, HS256 with the public key as secret, unknown `kid`, modulus below `MIN_RSA_MODULUS_BITS`, assertion above `MAX_ASSERTION_BYTES`, missing `email`; JWKS cache: fresh hit does not refetch, stale use within `JWKS_MAX_STALE_MS` on fetch failure, refusal beyond it |
| `web/src/lib/server/auth/gate.test.ts` | `parseAuthMode`, `parseTailnetConfig`, `resolveAuthConfig`, `parseAllowlist`, `isAllowlisted`, `gateRequest` | Loopback default; non-loopback host 421; tailnet with incomplete config 503; valid token but non-allowlisted email 403; allowlisted 200-path decision; wildcard/domain allowlist entries refused |
| `web/src/lib/server/config.test.ts` | `parseControlApiConfig` | Unconfigured, non-loopback URL refused, missing token, accepted loopback URL |
| `web/src/lib/polling.test.ts` | `nextPollDecision`, `isTerminalState` | Terminal states stop; backoff capped at `POLL_BACKOFF_CAP_MS`; stop after `POLL_MAX_CONSECUTIVE_ERRORS` |
| `web/src/lib/components/review/review-logic.test.ts` | `keyAction`, `KEY_BINDINGS`, `timingDirection`, `timingRows`, `flagGroups`, `annotationRequest`, `gridTicks` | 12 bindings resolve; keys are ignored inside `input,select,textarea` and with alt/ctrl/meta; timing direction is withheld where the module says it is withheld; annotation requests carry operator authorship (USER REPORTED or INTENT) and never a detector actor; no output string asserts a missed, extra or wrong note |

These tests duplicate no verdict of the Python modules; where a Python test
already evaluates the same module through `node` type stripping
(`test_web_processing_s3` M6, `test_web_runs_s3` Policy, `test_auth_hosting_s3`
V/C/G), the vitest file is the in-toolchain version and both stay.

### 5.2 End-to-end specs (Playwright project `e2e`; `pnpm run test:e2e`)

Fixtures: `web/e2e/fixtures/control-api/*.json`, generated by
`web/e2e/fixtures/generate.py` from real `scripts/web_api.py` and
`scripts/web_runs_api.py` responses over synthetic inputs (the builders of
`tests/test_web_runs_s3.py` and `tests/test_web_processing_s3.py`, imported
read-only), with ids rewritten to fixed low-entropy synthetic values and
`claim_class: synthetic_fixture`, `contains_real_media_facts: false` in
`README.json`. The capabilities fixture is the real projection of
`program/tools.json` at generation time. Media bytes served by the mock are
synthesized in node (a sub-second PCM WAV carrying a 32.70 Hz sine, matching
the instrument's low C1, so no fixture implies a high-passed signal); they
are not a recording and support no listening claim. The fixture set contains
two runs so the run pickers render rather than redirect.

The mock keeps an in-memory request log, readable by tests through the mock's
own loopback port (never through the BFF).

| Spec | Requirement | Assertions |
| --- | --- | --- |
| `library.spec.ts` | Clip library `/` | Lists the fixture sources; a source with null duration shows an explicit unknown, not `0` or blank; link to `/sources/[id]` works |
| `upload.spec.ts` | Upload refusal | With uploads disabled in the mock, submitting shows the typed code `uploads_disabled` and its `refusalText`; an unsupported extension shows `upload_type_refused`; the mock log shows zero stored bytes; no upstream `error` string is rendered |
| `source.spec.ts` | Source overview | Probe summary, runs and jobs sections render from fixtures; unknown fields are visible as unknown |
| `capture.spec.ts` | Capture review never auto-confirms the first 5 s | After loading the page (and after reload) the mock log has 0 non-GET requests and 0 review records; interval inputs are empty (`data-no-prefill`); an interval overlapping [0, 5) s shows the setup warning and cannot be saved without the explicit acknowledgement control; nothing in the page pre-checks that control |
| `process.spec.ts` | FULLER requires a reviewed interval | With no current review the FULLER option is rendered disabled with `capture_interval_required` and the mock log has 0 job submissions after an attempted keyboard and pointer activation; with the reviewed-fixture scenario it is enabled; no control is labelled high-pass, low-cut or notch by default |
| `runs.spec.ts` | Run graph, compare, review, deliver render | `/runs`, `/runs/[id]`, `/runs/[id]/compare`, `/runs/[id]/review`, `/runs/[id]/deliver` each render their landmark and heading from fixtures; compare shows `operator_preference` as not recorded; review shows user-reported and detector items with distinct labels; deliver shows editor-import as unverified; the run pickers `/compare`, `/review`, `/download` render a run list |
| `jobs.spec.ts` | Jobs index and detail | `/jobs` lists fixture jobs with state badges; `/jobs/[id]` renders queued, running, succeeded and failed fixtures; a closed-schema-violating fixture renders the typed decode error, not partial data |
| `tools.spec.ts` | Tools page lists 42 tools | Count of `[data-tool]` equals `data-tool-count` equals the fixture `tool_count` equals 42; the Python contract test separately asserts `program/tools.json` holds 42 tools and the fixture matches it, so the number has one source |
| `keyboard.spec.ts` | Keyboard navigation | First Tab focuses the skip link and Enter moves focus to `#main`; every primary-nav link is reachable by Tab in DOM order and has a visible focus indicator (computed outline or box-shadow differs from unfocused); on `/runs/[id]/review` the documented bindings act only when the workspace has focus and are inert in a text field; no keyboard trap (Tab leaves every widget within 50 presses) |
| `no-autoplay.spec.ts` | No autoplay | On each of the 16 routes an init script counts `HTMLMediaElement.prototype.play` calls; with no user gesture after load plus 1 s the count is 0, every media element has `paused === true`, `autoplay === false` and `currentTime === 0` |
| `headers.spec.ts` | Loopback guard stays on | A request with a non-loopback `Host` gets 421; a cross-origin POST to a BFF mutation route is refused with `bff_cross_origin_refused`; the control API token never appears in any response body or page HTML |

Each spec fails on any uncaught page error or `console.error` during the
scenario; the count is reported.

### 5.3 Accessibility (Playwright project `a11y`; `pnpm run test:a11y`)

`a11y-routes.spec.ts` runs `AxeBuilder` with tags `wcag2a`, `wcag2aa`,
`wcag21a`, `wcag21aa`, `wcag22aa` and `best-practice`, with no `disableRules`
and no `exclude`, in both `prefers-color-scheme` light and dark, on:

16 routes: `/`, `/upload`, `/sources/[id]`, `/sources/[id]/capture`,
`/sources/[id]/process`, `/runs`, `/runs/[id]`, `/runs/[id]/compare`,
`/runs/[id]/review`, `/runs/[id]/deliver`, `/jobs`, `/jobs/[id]`, `/tools`,
`/compare`, `/review`, `/download`; plus 3 states: `/upload` after a typed
refusal, `/sources/[id]/process` with the FULLER refusal visible, and `/` with
the control API unconfigured (typed error page). Denominator: 19 scans x 2
colour schemes = 38.

Every violation is written to `artifacts/s2/web_tests/a11y/<scan>.json` and
summarized in the a11y receipt as `{route, scheme, rule_id, impact, wcag_tags,
node_count}`. Gate: the suite fails on any violation not listed in
`web/e2e/a11y-baseline.json`. The baseline is created from the first complete
recorded run only, may only shrink afterwards, and every entry is also sent to
root as a source fix request with the rule, route and failing selector. The
lane fixes only its own test configuration. An empty baseline is the goal, not
a claim made here. axe `incomplete` results (for example contrast that needs
review) are counted and reported, not treated as passes.

Automated axe results are a measurement of the rules axe can evaluate on
synthetic fixtures. They are not a WCAG conformance claim and not evidence
about screen-reader behaviour.

### 5.4 House-stack contract (`tests/test_web_house_stack_s3.py`)

Run as `PYTHONPATH=tests python3 -m unittest test_web_house_stack_s3 -v`.
Stdlib only, no node, no network, no install.

| Class | Assertions |
| --- | --- |
| `HouseStackPins` | `web/package.json` pins exactly `@skeletonlabs/skeleton` `5.0.1`, `@skeletonlabs/skeleton-svelte` `5.0.1`, `effect` `4.0.1` (effect under `dependencies`); `svelte` is an exact `5.x.y`; every declared dependency is an exact version; the lockfile resolves exactly one version of each of the three contract packages and it equals the pin |
| `MajorLatest` | Reads `docs/agent-notes/sprints/20261007-s3/web_tests-npm-latest.json` (`{package, latest, checked_at_utc, command}` recorded from `npm view`); fails if a pin's major is below the recorded latest major for the three contract packages; fails if the record is missing or lacks a timestamp. The test never contacts the registry: staleness of the record is reported as its age in days and is an explicit unknown about today's registry |
| `NoSkeleton4Shim` | No `@skeletonlabs/tw-plugin`; no npm alias, `overrides`, `resolutions` or `patchedDependencies` entry naming a Skeleton package in `web/package.json` or `web/pnpm-workspace.yaml`; no second Skeleton version in the lockfile; no `web/src` import or `app.css` `@import`/`@plugin` from a Skeleton v4-only entry point. The v4-only entry-point list is derived in Phase 2 from the Skeleton v5 migration guide and recorded with its URL and date; until then it is unknown and not asserted from memory |
| `NoEffect3Paths` | No declared `@effect/schema`, `@effect/io`, `@effect/data` or `@effect/stream`; every `effect/<subpath>` import in `web/src` is in the export-key list of `effect@4.0.1` recorded in the receipt from `npm view effect@4.0.1 exports --json`; no import of a subpath that exists only in the Effect 3 line (list derived in Phase 2 from the same registry metadata for the latest 3.x, recorded; unknown until then) |
| `SiteObeysSameRule` | If `site/package.json` exists, the three pins, the exact-version rule and the two shim/path rules apply to it wherever it declares those packages; if absent the test records `site_package_present: false` and passes without claiming anything about a site |
| `LaneStatics` | Added devDependencies are exact; `program/tools.json` holds 42 tools and `web/e2e/fixtures/control-api/` capabilities fixture has the same names; every committed e2e fixture parses with a strict JSON parser (no NaN, no duplicate keys) and contains no host path; `README.json` says `synthetic_fixture`; no file under `web/e2e` or `web/tests` contains `0.0.0.0`, `--no-sandbox`, `--disable-web-security`, `autoplay` used as a launch policy override, or a scanner allowlist; `a11y-baseline.json` entries all carry rule, route and scheme |
| `FixtureDrift` | Re-runs `generate.py` into a temporary directory and compares with the committed fixtures; typed skip `fixture_generation_unavailable` when FFmpeg or a generator dependency is missing (reported, not counted as pass) |

### 5.5 Existing modules that must still pass

`test_web_stack`, `test_web_parity`, `test_web_reliability`,
`test_web_processing_s3`, `test_web_runs_s3`, `test_auth_hosting_s3`, each run
on its own from the worktree root with FFmpeg/FFprobe exported, one at a time,
after the lockfile change. `pnpm run check` and `pnpm run build` must still
succeed. The lane never runs the full suite.

## 6. Receipts and explicit unknown fields

Receipts (JSON, committed, path/sha256 pairs and commit ids only, no host
paths, no tokens):

- `web_tests-contract-freeze.json`: this spec's sha256 and commit.
- `web_tests-npm-latest.json`: per package `latest`, `checked_at_utc`,
  `command`, plus recorded `effect@4.0.1` export keys.
- `web_tests-pins.json`: chosen exact versions, rejected versions with reasons.
- `web_tests-browser.json`: ladder step used, browser name and version,
  download size/source/revision or `null` with `download_performed: false`.
- `web_tests-unit.json`, `web_tests-e2e.json`, `web_tests-a11y.json`: counts
  with denominators, skips with typed reasons, durations.
- `web_tests-root-requests.json`: recipe text, CI proposal, source fixes.
- `web_tests-handoff.json`: summary with claim classes.

Every result receipt carries these fields explicitly, with `null` plus a
reason where not established (never omitted, never defaulted to a pass):

| Field | Meaning when null |
| --- | --- |
| `browser_used`, `browser_version`, `browser_source` | e2e/a11y not run |
| `browser_download_bytes` | no download performed |
| `e2e_status`, `a11y_status` (`ran` / `not_run` + `skip_code`) | suite skipped; metrics are `not_run` |
| `axe_version`, `axe_rules_evaluated_count` | a11y not run |
| `axe_incomplete_count` | a11y not run |
| `wcag_conformance` | always `null`: automated rules do not establish conformance |
| `screen_reader_acceptance` | always `null`: not tested by this lane |
| `firefox_webkit_behaviour` | always `null`: Chromium only |
| `tailnet_mode_e2e` | always `null`: only unit-level JWT/gate tests |
| `real_control_api_under_playwright` | always `null`: mock replay only |
| `real_take_facts_in_fixtures` | always `false`; fixtures are synthetic |
| `listening_claims` | always `null`: none made |
| `npm_latest_at_ci_time` | always `null`: CI does not query the registry |
| `skeleton4_entry_point_list_source`, `effect3_only_subpath_list_source` | list not yet derived; the dependent assertions are reported `not_asserted` |
| `ci_node_available` | not established until root decides section 8.2 |
| `fixture_drift` (`equal` / `differs` / `not_checked` + reason) | generator unavailable |
| `flaky_retries` | always `0` by configuration; a rerun that changes a result is reported as `nondeterministic`, not as a pass |

## 7. Completion metrics, denominators and claim classes

Claim classes: **contract** (static assertion on files), **behaviour**
(observed on synthetic fixtures in this toolchain), **measurement** (recorded
value, no pass threshold implied beyond the stated gate), **inference**,
**unverified** (not tested). No listening claim, no note-correctness or
missed-note verdict, no detector/profile/master adoption arises from this lane.

| ID | Metric | Denominator | Done when | Class |
| --- | --- | --- | --- | --- |
| W1 | House-stack pins exact and equal to recorded npm latest major | 3 contract packages + svelte 5.x | 4/4, lockfile single-version 3/3 | contract |
| W2 | No Skeleton 4 shim, no Effect 3 path | Rules asserted / rules listed in 5.4, with `not_asserted` counted separately | all asserted rules pass; `not_asserted` is 0 or reported as unknown | contract |
| W3 | Added devDependencies exact and lockfile consistent | added packages (>= 4) | 100%; `test_web_stack` S2/S3 pass | contract |
| W4 | Unit test files present and passing | 13 files in 5.1 | 13/13 files, 0 failed tests, 0 skipped without a typed reason; test count reported | behaviour |
| W5 | Schema fixture decode agreement | `web/fixtures/control-api` 7 cases + every e2e fixture file (count reported) | 100% decode as their README states | behaviour |
| W6 | JWT verification cases with a run-time key | 1 accept + 11 refusals + 3 cache cases = 15 | 15/15 | behaviour |
| W7 | Refusal-text coverage | codes in the table (count reported) + codes referenced by builders/gate (count reported) | 100% of table codes non-fallback; unmapped referenced codes listed | behaviour |
| W8 | e2e requirement coverage | 11 specs in 5.2 | 11/11 specs pass, or `not_run` with a typed skip code | behaviour |
| W9 | Capture never auto-confirms | page loads counted (>= 2) | 0 non-GET requests, 0 review records | behaviour |
| W10 | FULLER requires interval in the browser | 2 states | 2/2; 0 job submissions in the refused state | behaviour |
| W11 | Tools listed | 42 (from `program/tools.json`) | 42/42 rendered and equal to registry names | behaviour |
| W12 | No autoplay | 16 routes | 0 `play()` calls and 0 unpaused elements on 16/16 | behaviour |
| W13 | Keyboard navigation | skip link 1, primary-nav links (count reported), review bindings 12, trap check 16 routes | all reachable; 12/12 bindings scoped; 0 traps | behaviour |
| W14 | axe scans executed | 38 (19 scans x 2 schemes) | 38/38 executed and recorded | measurement |
| W15 | axe violations | per scan, by impact | all recorded; 0 outside the baseline; baseline size reported (target 0, not claimed) | measurement |
| W16 | axe `incomplete` | per scan | count reported | measurement |
| W17 | Page errors and `console.error` | scenarios run (count reported) | 0 | behaviour |
| W18 | Existing Python web modules still pass | 6 modules in 5.5 | 6/6 with the same skip set as the baseline commit (skips listed) | behaviour |
| W19 | `pnpm run check` and `pnpm run build` | 2 commands | 2/2 exit 0 | behaviour |
| W20 | Secret and host-path hygiene | lane-owned committed files (count reported) | 0 gitleaks findings without any allowlist; 0 host paths | contract |
| W21 | Root hand-offs delivered | 3 recipes + 1 CI proposal + source-fix list | all present in the root-requests receipt | contract |

A result of "axe found violations in source that the lane cannot fix" or "e2e
skipped because no browser is available" is a valid completion provided it is
recorded with denominators and typed codes; it is never reported as green.

## 8. Root-owned changes this lane will request (not made by the lane)

Final text is delivered in `web_tests-root-requests.json` after Phase 2; the
intended shape is frozen here.

### 8.1 `just` recipes (for `just/workflow.just`)

```just
# Web unit tests (vitest; pure modules, no browser, no control API)
web-unit:
    cd web && pnpm install --frozen-lockfile --offline && pnpm run test:unit

# Web end-to-end tests against the built app with the mocked control API (loopback, foreground, one worker)
web-e2e:
    cd web && pnpm install --frozen-lockfile --offline && pnpm run build && pnpm run test:e2e

# axe accessibility scans on every route (records violations; fails only on ones outside web/e2e/a11y-baseline.json)
web-a11y:
    cd web && pnpm install --frozen-lockfile --offline && pnpm run build && pnpm run test:a11y

# House-stack contract: latest Skeleton v5 and Effect pins (stdlib, no node)
web-house-stack-test:
    PYTHONPATH=tests python3 -m unittest test_web_house_stack_s3 -v
```

### 8.2 CI proposal (for `.github/workflows/ci.yml` and `flake.nix`)

Observation: the nix `core` shell has no `nodejs`/`pnpm`, so today CI cannot
run vitest or Playwright. `tests/test_web_house_stack_s3.py` needs neither and
is picked up by the existing `just check` discovery with no CI change.

Proposal for root to decide (two options, neither applied by the lane):

- **A (preferred, small):** add a `web` dev shell to `flake.nix`
  (`nodejs_22`, `pnpm`) and a CI step
  `nix develop .#web --no-write-lock-file --command just web-unit`. The
  install is the first online step in CI, so the step uses
  `pnpm install --frozen-lockfile` against the committed lockfile. Unit tests
  only; no browser in CI.
- **B (later):** add `web-e2e`/`web-a11y` in CI with a nix-provided Chromium
  passed through `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`, so no browser is
  downloaded at CI time. Requires root to confirm the nixpkgs Chromium is
  compatible with the pinned Playwright; unknown today.

No private recording, media upload or model download is involved in either.

### 8.3 Source fixes

Any axe violation, missing focus indicator, unmapped user-visible refusal code
or autoplay finding is reported to root with route, selector and rule. The
lane does not edit `web/src` non-test files, `web/.gitignore` or
`web/tsconfig.json`; if `pnpm run check` needs a tsconfig or ignore change to
accommodate test files, the exact diff is requested instead.

## 9. Preregistration

The lane runs no experiment with competing arms and adopts nothing. The one
open-outcome measurement is the axe scan (W14-W16); its protocol is sealed by
this commit before any scan is run:

- **Fixtures:** the committed synthetic fixture set of 5.2; no real-take data.
- **Seeds:** fast-check seed `20261007`, 200 runs per property (unit tests);
  Playwright has no randomness, one worker, zero retries.
- **Arms:** one (the app at the lane branch's merge base); 19 scans x light
  and dark. No comparison arm.
- **Scoring:** axe violations and incompletes per scan by impact, tags as in
  5.3; no rule disabled, nothing excluded.
- **Sealed before truth:** the route list, tags and gate are fixed here. After
  the first recorded run the route list and tags may only grow; a rule may not
  be disabled and a selector may not be excluded to reduce a count. The
  baseline file records what was found; it is not tuned.
- **No held-out set:** not applicable; there is no model or detector.

## 10. Doctrine carried

Fixtures keep the approximately 32 Hz register (32.70 Hz synthetic tone; no
high-pass, low-cut or mains-notch control is introduced or defaulted, and the
process spec asserts none is offered by default). Measurements, inferences and
listening claims stay distinct: everything here is contract, behaviour on
synthetic fixtures, or a recorded measurement; no listening claim exists.
User-reported items stay distinguishable from detector hypotheses in the
review assertions. Nullable BPM, meter, tonic, phrase and duration fields must
survive decoding and rendering as unknown. The first 5 s are never
auto-confirmed. No note-correctness or missed-note wording is asserted or
introduced. Non-improvement (violations found, e2e skipped with a typed
reason) is a valid, fully reported completion.
