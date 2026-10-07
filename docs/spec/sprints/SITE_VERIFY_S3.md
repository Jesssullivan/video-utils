# S3 site_verify lane contract: browser, accessibility, links, privacy and deploy readiness of the public site

Status: **Phase 1 contract freeze**, 2026-10-07. Lane `site_verify`, sprint
`20261007-s3`, branch `sprint/20261007-s3/site_verify`, worktree
`.local/sprint3/site_verify`. Tracker: Linear TIN-5723 (root writes Linear).
Baseline: `549a14d` (main at lane creation; the public site landed in `f7ff2d6`
under `docs/spec/sprints/PUBLIC_SITE_S3.md`).
Authority: the operator S3 decision for a static public landing on Cloudflare
Pages with no real-take data, the estate P0 stack rule (Skeleton 5.0.1, Effect
4.0.1), repository `AGENTS.md`, R-HOOK-CONVERGENCE-20261004 R-N11/R-N12/R-N13.
Root administers review, signed merge, `just` recipes, CI, publication and
Linear. This lane never pushes, merges, writes Linear, edits a root-owned file,
starts a daemon, downloads a model or a browser, creates a Cloudflare project,
runs Wrangler, or deploys anything.

No numerics, installs, builds or browser runs were performed in this phase.
Every number below that describes the site is a target or a denominator
definition, not a result. Facts about the host toolchain (section 3) were read
with `which`/`--version` only.

## 1. Scope

Verify the already built static site (`site/`, five prerendered documents) and
fix defects found in site source. Five deliverables, matching the lane's
definition of done:

1. **Browser smoke** (Playwright, Chromium only) over every built route at four
   widths and one 200 percent zoom configuration: renders, no console errors,
   no page errors, no horizontal scroll, no external request beyond the
   build-intended list (frozen as empty, section 5.4).
2. **axe** in the light and dark colour modes: 0 violations is the target;
   any residual is listed with a reason. Automated rules only; not a WCAG
   conformance claim.
3. **Internal link check** over the static build: 0 broken; external links are
   listed and never fetched.
4. **V6 privacy scan** of the built output (section 7) with 0 hits, plus
   `gitleaks dir` over the build directory with 0 findings.
5. **Deploy readiness**: `site/DEPLOY.md` states the exact deploy steps, the
   verification gates that precede them, and every decision that needs the
   operator's go. Nothing is deployed.

Supporting work: add `@playwright/test` and `@axe-core/playwright` as exact
devDependencies, update `site/pnpm-lock.yaml`, keep every existing
`test_public_site_s3` check green (no regression of M1 to M24 of the
public_site contract), and keep the existing leak scan clean over the new
harness files without weakening any rule.

Out of scope, explicitly not claimed: any deploy, served-site request, Pages
project, DNS or domain; Firefox or WebKit; real devices; screen-reader
behaviour; WCAG conformance; manual contrast measurement beyond what axe's
`color-contrast` rule evaluates; the five non-default chrome themes (section
6.4); reduced-motion behaviour; a Content-Security-Policy; Bazel targets;
changes to `web/`, tools, skills, detectors, profiles or masters; any listening
or accuracy claim.

## 2. Owned files

| Path | Role |
| --- | --- |
| `docs/spec/sprints/SITE_VERIFY_S3.md` | This contract |
| `site/src/`, `site/static/` | Defect fixes only (authored content stays under the public_site content rules) |
| `site/scripts/` | Unchanged unless a defect requires it; no rule weakened |
| `site/playwright.config.ts` | Playwright configuration (new) |
| `site/e2e/` | Static server, global setup/teardown, route enumeration, smoke and axe specs, axe baseline (new) |
| `site/tests/` | Browser ladder copied from `web/tests/browser-ladder.ts` (new) |
| `site/package.json`, `site/pnpm-lock.yaml` | Two exact devDependencies and one non-lifecycle script |
| `site/DEPLOY.md` | Exact steps, gates and operator decisions |
| `tests/test_public_site_s3.py` | New `SiteVerify*` classes appended; existing classes unchanged except where a regression fix is required and recorded |
| `docs/agent-notes/sprints/20261007-s3/site_verify-*.json` | Receipts |

Not owned and not edited: `site/svelte.config.js`, `site/vite.config.ts`,
`site/tsconfig.json`, `site/pnpm-workspace.yaml`, `site/.gitignore`,
`site/vendor/`, the root `.gitignore`, `.gitleaks.toml`, and every root-owned
file (`scripts/tool_api.py`, `program/tools.json`, `just/workflow.just`,
`scripts/review_server.py`, `scripts/mcp_server.py`, `program/models.json`,
`program/linear.json`, `docs/spec/PROJECT.md`, `.github/workflows/*`). If a
fix needs one of them, the exact diff goes to root in
`site_verify-root-requests.json` (section 11).

All run outputs (Playwright output, JSON reports, screenshots, gitleaks
reports) go under `.local/sprint3/site_verify/artifacts/s2/site_verify/`
(gitignored by the root `/artifacts/` rule). Because every file under `site/`
is covered by the public_site source leak scan (rule
`artifact-path-reference`, `developer-filesystem-path`), no file under `site/`
names that directory: the output directory is passed in the environment
variable `SITE_VERIFY_OUT_DIR`, and `site/playwright.config.ts` refuses to run
(typed error `site_verify_out_dir_required`) when it is unset, so Playwright
never creates `site/test-results/` or a report inside `site/`.

## 3. Facts read for this contract

Stated by repository files at baseline:

- `site/package.json`: Skeleton and Skeleton Svelte `5.0.1`, no `effect`
  dependency, `packageManager` `pnpm@11.25.0`, `engines.node` `>=22.13 <23`,
  scripts `check`, `build`, `leak-scan` only. The P0 pins are kept; nothing is
  downgraded; `effect` stays absent (the only admissible pin would be 4.0.1).
- `web/package.json`: `@playwright/test` `1.63.0`, `@axe-core/playwright`
  `4.13.0`. `docs/agent-notes/sprints/20261007-s3/web_tests-browser.json`
  records that Playwright 1.63.0 found its expected Chromium revision already in
  the local Playwright cache (ladder step b), browser version 153.0.8010.12,
  nothing downloaded.
- The built site has five documents: `index.html`, `features.html`,
  `agents.html`, `status.html`, `404.html` (public_site M7), plus
  `agents/__data.json`, hashed `_app/` assets, fonts, `favicon.svg`,
  `_headers`.
- The chrome's pre-paint script (`site/vendor/xoxd-public-chrome/src/fouc.mjs`)
  sets `html[data-mode]` from `localStorage['color-mode']` (`light`, `dark` or
  `system`) and defaults to **dark regardless of `prefers-color-scheme`**.
  Emulating the media feature alone therefore does not switch this site's mode
  (section 6.2).
- The chrome renders two `<nav>` landmarks (full navigation at `lg` and wider,
  quick navigation) and, below `lg`, a menu button that opens a dialog.
- The public_site leak rules forbid, in every file under `site/`: loopback and
  private addresses (including the loopback literal and the unspecified
  address), the loopback host name, developer paths, `artifacts/` paths, tracker
  keys and the tracker host, the forge host, 40-hex and 64-hex strings, run
  identifiers and store paths.
- `.gitleaks.toml` at the repository root extends the gitleaks default ruleset
  with one narrow allowlist.

Read from the host (tool presence only): `node` v22.23.2, `pnpm` 11.25.0,
`gitleaks` 8.30.1 on PATH, a Playwright cache containing a `chromium-1243`
directory, an installed Google Chrome. Under the main checkout,
`artifacts/runs/` holds 626 files (about 4.0 GB); 12 files are larger than
64 MiB (about 2.4 GB together).

Inferred (to be confirmed in Phase 2, each recorded either way):

- `chromium-1243` is the revision Playwright 1.63.0 expects, so ladder step b
  applies without a download.
- Adding the two devDependencies leaves `pnpm run check` at 0 errors and
  0 warnings (SvelteKit's generated tsconfig type-checks `site/tests/**/*.ts`).
- The fallback document triggers one browser-generated console message for the
  main-document 404 status when reached through an unknown path (section 5.3).

## 4. Dependency and harness contract

### 4.1 Pins

Added to `site/package.json` `devDependencies`, exact versions:

| Package | Pin | Reason |
| --- | --- | --- |
| `@playwright/test` | `1.63.0` | Same as `web/`; its Chromium revision is already cached, so no browser download is needed |
| `@axe-core/playwright` | `4.13.0` | Same as `web/` |

The transitive `axe-core` and `playwright-core` versions are whatever the lock
resolves and are recorded in the receipt. Install command (registry fetch for
these pinned packages is allowed; browser download is not):

```
cd site && PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 pnpm add --save-dev --save-exact @playwright/test@1.63.0 @axe-core/playwright@4.13.0
cd site && PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 pnpm install --frozen-lockfile
```

The exact commands, exit statuses and durations are recorded in
`site_verify-install.json`. No `pnpm exec playwright install` is ever run. One
script is added: `"verify:browser": "playwright test"`. No lifecycle script.
Skeleton stays at `5.0.1` (2/2 in package.json, no other version in the lock),
`effect` stays absent (0 lock entries), and `wrangler` stays absent.

### 4.2 Harness files

- `site/tests/browser-ladder.ts`: a copy of `web/tests/browser-ladder.ts`
  (steps a env executable, b cached expected revision, c installed Chrome,
  e typed skip `e2e_browser_unavailable`; step d, an operator-run install, is
  never executed). The chosen step and browser version are recorded.
- `site/e2e/static-server.mjs` (Node standard library only): serves the build
  directory read-only on the IPv4 loopback interface on an ephemeral port.
  Path resolution emulates Cloudflare Pages for an adapter-static build:
  exact file; else `<path>.html`; else `<path>/index.html`; else `404.html`
  with status 404. Responses carry the `/*` headers from `build/_headers`.
  The loopback address is assembled at run time from its four octets, so no
  file under `site/` contains the literal and no leak rule needs an exception.
  It refuses any path that resolves outside the build directory.
- `site/e2e/global-setup.ts`, `global-teardown.ts`: start and stop that server,
  export its origin to the specs; the server never outlives the run.
- `site/e2e/routes.ts`: enumerates routes from the HTML files present in the
  fresh build at run time (`index.html` maps to `/`, `<name>.html` to
  `/<name>`, `404.html` to the not-found probe `/site-verify-not-found`). The
  route count R is read, never hardcoded; R = 5 is expected at baseline.
- `site/e2e/smoke.spec.ts`, `site/e2e/a11y.spec.ts`,
  `site/e2e/a11y-baseline.json` (starts as `{"schema_version": 1,
  "violations": []}`; any entry needs `reason`, `rule_id`, `route`, `scheme`,
  `width`, `node_count`).
- `site/playwright.config.ts`: Chromium only, one worker, zero retries,
  `serviceWorkers: 'block'`, video off, screenshots only on failure, traces on
  failure, all outputs and a JSON reporter under `SITE_VERIFY_OUT_DIR`, no flag
  that disables web security or the sandbox.

The harness writes one summary, `<SITE_VERIFY_OUT_DIR>/browser-summary.json`,
which the Python tests and the receipts read.

## 5. Browser smoke protocol (deliverable 1)

### 5.1 Viewport configurations (5)

| id | CSS viewport | deviceScaleFactor | Meaning |
| --- | --- | --- | --- |
| `w375` | 375 x 812 | 1 | Small phone width |
| `w390` | 390 x 844 | 1 | Current phone width |
| `w768` | 768 x 1024 | 1 | Tablet portrait |
| `w1280` | 1280 x 800 | 1 | Desktop |
| `z200` | 640 x 400 | 2 | A 1280 x 800 window at 200 percent zoom |

`z200` is an emulation: layout at 200 percent browser zoom equals layout at
half the CSS viewport with doubled device pixels. It is not the browser's zoom
control and is recorded as `zoom_method: "viewport_emulation"`.

### 5.2 Cases and per-case checks

Cases = R routes x 5 configurations (25 at R = 5). Each case runs in a fresh
browser context in the site's default mode (no stored preference, so dark).
A case passes only if every check holds:

1. Navigation status: 200 for content routes, 404 for the not-found probe.
2. Renders: `main#content` visible with non-empty text; exactly one visible
   `<h1>`; a non-empty `<title>`; the site header (`data-testid=
   "public-navigation"`) visible; a `<footer>` attached; at least one `<nav>`
   with an accessible name attached; the not-found probe shows the fallback
   heading.
3. Hydration: the client bootstrap ran (the SvelteKit start module loaded with
   status 200 and no page error); recorded, not inferred from markup.
4. Console: 0 messages of type `error`, 0 `pageerror` events. Warnings are
   counted and listed, not failing.
5. Horizontal scroll: `document.documentElement.scrollWidth <=
   document.documentElement.clientWidth` after load and after scrolling to the
   bottom; the overflow in CSS pixels is recorded (target 0).
6. Requests: every request URL is recorded. Requests to any origin other than
   the local server origin, `data:` and `blob:` are aborted by a context route
   (never fulfilled from the network) and listed; target: the list equals the
   build-intended external list (section 5.4).

One extra check per route at `w1280` (R cases): the first Tab press focuses the
skip link, and its target `#content` exists. This is a partial keyboard check,
not a keyboard walkthrough.

### 5.3 Declared allowance (frozen before any run)

On the not-found probe only, a console `error` whose text reports a 404 status
and whose location URL equals the probe URL is classified
`expected_document_404` (the browser's own report of the document status the
fallback is designed to return), counted separately and listed. No other
allowance exists. If Phase 2 observes no such message the allowance is unused
and reported as 0.

### 5.4 Build-intended external requests

Frozen as **empty**. Fonts, favicon and scripts are self-hosted; the site has
no analytics, beacon or third-party origin (public_site section 5.4). Any
external request observed is a defect to fix in site source, or, if framework
code requires it, a recorded deviation with the exact URL and the measured
cause. The external list is reported even when empty.

## 6. Accessibility protocol (deliverable 2)

### 6.1 Rules

`@axe-core/playwright` 4.13.0 with tags `wcag2a`, `wcag2aa`, `wcag21a`,
`wcag21aa`, `wcag22aa`, `best-practice` (the same set as `web/`), no rule
disabled, nothing excluded. `incomplete` results are counted and listed, never
treated as passes.

### 6.2 Colour modes

A scan in mode M sets `localStorage['color-mode'] = M` through an init script
before navigation and emulates `prefers-color-scheme: M`, then asserts
`html[data-mode="M"]` before analysing. A scan whose mode assertion fails is a
failed scan, not a scan of the wrong mode. Theme stays the default `xoxd`.

### 6.3 Scans

R routes x 2 modes (`light`, `dark`) x 2 widths (`w1280`, `w375`), plus one
state scan per mode: the mobile navigation dialog open at `w375` (menu button
activated, dialog visible). Total = 4R + 2 (22 at R = 5). Every scan writes a
per-scan JSON (axe version, tags, rule ids evaluated, violations, incomplete,
pass and inapplicable counts) under `SITE_VERIFY_OUT_DIR`.

Target: 0 violations over all scans. A residual is admissible only when it is
in `site/e2e/a11y-baseline.json` with a reason, and only when the defect is in
an unmodifiable vendored carrier or framework output; a defect in authored
`site/src/` is fixed, never baselined. Claim class: automated-check results
only; they say nothing about screen readers, cognitive load, or rules axe cannot
evaluate.

### 6.4 Not scanned (recorded as unknown)

The five non-default themes the chrome offers (`scaffold`, `pine`, `rose`,
`catppuccin`, `trans`), the `system` preference value, reduced motion, forced
colours, and any width not listed.

## 7. Link check and V6 privacy scan (deliverables 3 and 4)

Both are Python standard library code in `tests/test_public_site_s3.py`, run
on the build the test just produced (never a stale build).

### 7.1 Internal link check

References collected: `href`, `src` and `srcset` attributes in every HTML
document; `url(...)` in every CSS file; relative static and dynamic import
specifiers (`./`, `../`, and root-relative) in every JS file; `__data.json`
targets of prerendered loads. Resolution follows the section 4.2 Pages
emulation. A fragment (`#id`, or `<path>#id`) must name an `id` present in the
target document. Reported: references checked L, broken 0 (target), fragment
references F, broken fragments 0 (target). External references (any URL with a
scheme or `//` prefix, and `mailto:`) are listed with the document they occur
in and are never fetched; `fetched_external: 0`.

Self-test: a synthetic build tree in a temp directory with one good and one
broken reference of each kind and one good and one missing fragment; the
checker must report exactly the broken ones.

### 7.2 Privacy scan (V6)

Applied to every file under the fresh `site/build/`. Text files are matched as
text; binary files (fonts) are scanned as bytes for the exact identifiers in
families 7 and 8 only, and counted separately. Pattern families (8), each
compiled case-insensitively where meaningful, with literals assembled from
fragments at run time:

| # | Family | Catches |
| --- | --- | --- |
| 1 | Tailnet names | the `ts.net` suffix, the word `tailnet`, Tailscale-style `tail<hex>` labels |
| 2 | Private and special addresses | IPv4 10/8, 172.16/12, 192.168/16, 100.64/10, 127/8, 169.254/16, the unspecified address, IPv6 `fc00::/7` and `fe80::/10`, loopback `::1` |
| 3 | Estate host names | the bare words `neo`, `sting`, `honey` (word-bounded), and this host's short name read at test time |
| 4 | Private-zone and tunnel hosts | the public_site `private-estate-hostname` and `internal-hostname` rules, applied verbatim |
| 5 | Artifact paths | `artifacts/`, `.local/sprint`, `runs/<date>T`, `experiments/<date>T` |
| 6 | Linear URLs and keys | the `linear.app` host and `TIN-<n>` keys |
| 7 | Digests of private-run files | sha256 (hex, upper and lower case, and base64 SRI form) of files under the main checkout's `artifacts/runs/`, plus every 64-hex string recorded in text manifests there |
| 8 | Real-take identifiers | the public_site M13 identifier set (source sha256, recording name forms, run directory names) |

Digest collection (family 7): the default run hashes every file of at most
64 MiB and reads every recorded 64-hex string from `.json`, `.txt`, `.md`,
`.csv` and `.tsv` files of at most 4 MiB. Files larger than 64 MiB are counted
as `not_hashed` (expected 12) and are covered only by the generic
`content-hash-64` leak rule (any 64-hex string in the build is already a
finding). An opt-in full run (`SITE_VERIFY_FULL_DIGESTS=1`, 600 s timeout)
hashes every file; Phase 2 runs it once and records it. When no main checkout
or no `artifacts/runs/` is found, the family reports `identifiers: 0,
checked: false`, never a pass over an unknown set.

Reported: files scanned (text T, binary B), identifiers per family with their
count K, files hashed H of total N, hits per family (target 0 each, 0 total).
A hit inside framework code is not silently allowed: it is either fixed or
recorded as an exact-string deviation with file, offset and measured cause,
reported apart from the raw hit count.

Self-test: one positive and one negative synthetic fixture per family (invented
names under reserved zones, documentation-range lookalikes for the negative,
digests of a synthetic temp file); the scanner fires on every positive and
none of the negatives.

### 7.3 gitleaks

```
gitleaks dir site/build --config .gitleaks.toml --no-banner --redact --log-level warn \
  --report-format json --report-path "$SITE_VERIFY_OUT_DIR/gitleaks-build.json" --exit-code 1
```

run from the worktree root with a 120 s timeout. Target: exit 0, 0 findings.
Positive control: the same command over a temp directory holding one synthetic
credential-shaped string assembled at run time must exit 1, so a pass means the
tool ran and could fire. gitleaks version and config digest are recorded.
Skipped with reason `gitleaks_unavailable` only if the binary is absent; nothing
is installed.

The public_site build leak scan (M11, 24 rules, Node and Python) and source
scan (M12, which now also covers `site/e2e/`, `site/tests/` and
`site/playwright.config.ts`) remain gates and must stay at 0 findings.

## 8. Deploy readiness (deliverable 5)

`site/DEPLOY.md` keeps its existing statements (plan only, nothing deployed,
separate operator go, no credential in the repository, decision table) and
adds, in order: the dependency install, `check`, `build`, the leak scans, the
link check, the privacy scan and gitleaks, the browser smoke and axe suites
(with how `SITE_VERIFY_OUT_DIR` is set and that no browser is downloaded), the
lane tests, then the deploy. Each step names its exact command and the
condition to proceed. The deploy section names exactly which actions need the
operator's go: choosing the Cloudflare account, creating the Pages project,
choosing and pinning a Wrangler version, the first and every later
`wrangler pages deploy`, attaching a custom domain, and deciding whether
previews are public. DEPLOY.md is itself under the source leak scan, so it
names no output path, host, tracker key or URL.

## 9. Completion metrics

Claim classes: **M** measured by a command in this lane on the authored site
build or on synthetic fixtures; **I** inferred; **U** unknown or not performed.
Every M metric is reported as numerator/denominator with the command, exit
status and duration in a receipt. None is an accuracy, listening, served or
conformance claim.

| # | Metric | Target | Class |
| --- | --- | --- | --- |
| V1 | Smoke cases passing all six checks (section 5.2) | 5R/5R (25/25 at R = 5), R read from the build | M |
| V2 | Console errors over all smoke cases, excluding the declared `expected_document_404` allowance; page errors | 0 and 0; allowance count reported | M |
| V3 | Smoke cases with horizontal overflow | 0 of 5R; max overflow px reported | M |
| V4 | External requests observed vs build-intended list | observed list equals the empty list; 0 fetched | M |
| V5 | First-Tab skip-link check at `w1280` | R/R | M |
| V6 | axe scans executed with the mode assertion holding | (4R + 2)/(4R + 2) (22/22) | M |
| V7 | axe violations over all scans | 0; any residual listed in the baseline with a reason; incomplete count reported | M |
| V8 | Broken internal references and broken fragments | 0 of L and 0 of F; externals listed, 0 fetched | M |
| V9 | Link-checker self-test verdicts | all fixtures correct | M |
| V10 | Privacy hits per family over T text and B binary files | 0 in each of 8 families; K, H, N reported | M |
| V11 | Privacy-scanner self-test verdicts | 8/8 positives fire, 0/8 negatives fire | M |
| V12 | gitleaks on the build; positive control | exit 0 with 0 findings; control exit 1 | M |
| V13 | Existing leak scans (M11 build, M12 source incl. new harness files) | 0 and 0 findings, no rule changed | M |
| V14 | `pnpm install --frozen-lockfile`, `pnpm run check` (0 errors, 0 warnings), `pnpm run build` after the devDependency change | 3/3 exit 0 | M |
| V15 | Pins: new devDependencies exact; Skeleton 5.0.1 2/2 and sole lock version; `effect` absent; `wrangler` absent | holds | M |
| V16 | Browser bytes downloaded by the lane | 0; ladder step and browser version recorded | M |
| V17 | `test_public_site_s3` existing tests (public_site M1 to M21) | all pass or skip with the module's stated reasons; 0 failures | M |
| V18 | DEPLOY.md required statements and ordered gate commands (section 8) | all present, checked by test | M |
| V19 | Deploy actions performed | 0 | M |
| V20 | Site source defects found and fixed | count and list, each with the check that found it | M |
| V21 | Equivalence of the local static server to Cloudflare Pages path resolution | not proven | I |
| V22 | Firefox, WebKit, real-device, screen-reader, non-default theme, reduced-motion checks | not performed | U |

Valid completion includes a justified accessibility residual in vendored or
framework code, a recorded framework deviation, or an unused allowance,
provided each is reported with its denominator. A failing V1, V7 without a
baseline reason, V8, V10, V12, V13 or V14 is not completion.

## 10. Test protocol

### 10.1 Python (standard library)

Module `tests/test_public_site_s3.py`, run from the worktree root:

```
PYTHONPATH=tests python3 -m unittest test_public_site_s3 -v
```

Directly affected modules run alongside: `test_web_stack`,
`test_tool_contracts`. The full suite is root's.

New classes appended (existing classes keep their behaviour):

1. `SiteVerifySpecTests` (always): this spec exists and contains section 12;
   present `site_verify-*.json` receipts are JSON, carry `lane: "site_verify"`,
   never claim a deploy, and carry every section 12 field with an allowed value.
2. `SiteVerifyPinTests` (always): V15; the two devDependency pins and their
   lock specifiers; `verify:browser` script present and no lifecycle script;
   `site/playwright.config.ts` reads `SITE_VERIFY_OUT_DIR` and sets no
   browser-download or security-disabling option; the static server has no
   loopback literal (also enforced by V13).
3. `LinkCheckSelfTests` and `PrivacyScanSelfTests` (always): V9 and V11 on
   synthetic fixtures generated in a `tempfile.TemporaryDirectory`.
4. `SiteVerifyBuildTests` (skipped with a stated reason unless `node`, `pnpm`
   and `site/node_modules/` exist): uses a module-level, once-per-process fresh
   build shared with the existing `BuildTests` (check and build 300 s each;
   never `pnpm install`, never network flags); then V8, V10, V13 on that build.
5. `GitleaksBuildTests` (skipped with `gitleaks_unavailable` if the binary is
   absent; needs the fresh build): V12 including the positive control.
6. `BrowserSuiteTests` (opt-in: runs only when `SITE_VERIFY_BROWSER=1`, and
   skips with `e2e_browser_unavailable` when the ladder finds no browser): runs
   `pnpm exec playwright test` from `site/` against the fresh build with a
   900 s timeout and `SITE_VERIFY_OUT_DIR` set to a temp directory, then asserts
   V1 to V7 from `browser-summary.json`.
7. `DeployDocTests` (always): V18.

The opt-in full digest run is `SITE_VERIFY_FULL_DIGESTS=1` on
`SiteVerifyBuildTests` (600 s timeout).

### 10.2 Playwright

From `site/`, after a fresh build:

```
SITE_VERIFY_OUT_DIR=<worktree>/artifacts/s2/site_verify/playwright pnpm run verify:browser
```

Specs: `e2e/smoke.spec.ts` (5R smoke cases plus R skip-link checks) and
`e2e/a11y.spec.ts` (4R + 2 scans). One worker, zero retries, 60 s per test.

### 10.3 Fixtures and limits

Fixtures are fully synthetic and generated at run time: invented host names
under reserved zones, digests of synthetic temp files, placeholder
credential shapes assembled from fragments. The site under test is the authored
public site built from repository source; it contains no real-take media,
timing or digest. No seeds are needed: nothing is random. No media fixture
exists. Every subprocess has an explicit timeout (scanner 60 s, gitleaks 120 s,
check and build 300 s each, Playwright 900 s, full digests 600 s). At most one
build or browser run at a time. Nothing reads or writes `/Users/jess/Documents`
or `/Users/jess/Desktop`; `artifacts/runs/` in the main checkout is only read.

## 11. Root-owned changes anticipated (requested, never applied)

Recorded as exact text in `site_verify-root-requests.json` in Phase 2:

- `just/workflow.just`: a `site-verify` recipe running the section 8 gates in
  order (install, check, build, leak scans, lane tests, browser suite with
  `SITE_VERIFY_OUT_DIR` under the root artifacts directory), and an amendment to
  the proposed `site-pages-deploy` recipe so it also requires the browser and
  privacy receipts to be green.
- `.github/workflows/ci.yml`: whether CI runs the browser suite is root's call;
  the proposal is the static gates only (no browser in hosted CI unless root
  provisions one).
- Any defect whose fix lies in `site/svelte.config.js`, `site/vite.config.ts`,
  `site/pnpm-workspace.yaml`, `site/.gitignore` or `site/vendor/`.

## 12. Explicit unknown fields

Receipts `site_verify-install.json`, `site_verify-browser.json`,
`site_verify-a11y.json`, `site_verify-links-privacy.json` and
`site_verify-handoff.json` carry every field below. A field keeps its frozen
value unless a receipt in this lane proves otherwise; none may be dropped.

| Field | Frozen value | Meaning |
| --- | --- | --- |
| `deployed` | `false` | Nothing was deployed |
| `served_check` | `"not_performed"` | No request to a served copy |
| `pages_project_name`, `cloudflare_account`, `public_hostname`, `custom_domain`, `wrangler_version` | `null` | Operator decisions |
| `server_kind` | `"local_static_emulation"` | Results are on a local emulation of Pages path resolution |
| `pages_equivalence` | `"inferred"` | V21 |
| `response_headers_on_pages` | `"unknown"` | Only the local server applied `_headers` |
| `browser_engines` | `["chromium"]` | Firefox and WebKit not run |
| `browser_download_bytes` | `0` | Lane downloaded nothing |
| `zoom_method` | `"viewport_emulation"` | Section 5.1 |
| `real_device_check` | `"not_performed"` | |
| `wcag_conformance` | `"not_claimed"` | axe results are automated checks only |
| `screen_reader_check` | `"not_performed"` | |
| `contrast_basis` | `"axe_color_contrast_rule_only"` | Incomplete contrast nodes stay unknown |
| `keyboard_walkthrough` | `"not_performed"` | Only the first-Tab skip-link check (V5) runs |
| `reduced_motion_verified` | `false` | |
| `non_default_themes_scanned` | `false` | Five themes not scanned |
| `csp_enforced` | `false` | |
| `external_links_fetched` | `0` | Listed, never fetched |
| `artifact_digests_complete` | `false` unless the full digest run is recorded, then `true` | Section 7.2 |
| `real_take_accuracy`, `low_register_pitch_accuracy` | `"unknown"` | The site says so; this lane does not measure it |
| `listening_acceptance` | `"not_claimed"` | |
| `effect_in_site` | `"absent"` | |
| `media_shown` | `0` | |

## 13. Experiment and preregistration

This lane runs **no experiment**. There are no arms, seeds, held-out sets or
scores, and nothing is tuned against an outcome. `preregistered: false`. What
is sealed by this commit before any install, build or browser run: the viewport
set (5.1), the per-case checks (5.2), the single console allowance (5.3), the
empty external-request list (5.4), the axe tags, modes and scan count (6), the
link-check reference kinds (7.1), the eight privacy families and digest policy
(7.2), the gitleaks command (7.3), and the metric targets (9).

## 14. Phase 2 results (2026-10-07)

Implemented on `sprint/20261007-s3/site_verify` (harness, fixes and tests in
`152baa1`; receipts and this section after it). Sections 1 to 13 are unchanged.
Receipts: `site_verify-install.json`, `site_verify-browser.json`,
`site_verify-a11y.json`, `site_verify-links-privacy.json`,
`site_verify-handoff.json`, `site_verify-root-requests.json`. Run outputs stay
in the lane's gitignored output directory. Nothing was deployed (V19 = 0).

### 14.1 Results by metric (M unless marked)

Final run: `SITE_VERIFY_OUT_DIR=<out>/final SITE_VERIFY_BROWSER=1
SITE_VERIFY_FULL_DIGESTS=1 PYTHONPATH=tests python3 -m unittest
test_public_site_s3 -v`, exit 0, 85 tests, 0 failures, 1 skip (the existing
`private_app_hostname` reason), 484 s. The Playwright part ran 52/52 tests in
131 s.

| # | Result |
| --- | --- |
| V1 | 25/25 smoke cases pass all six checks; R = 5 read from the build |
| V2 | 0 console errors and 0 page errors; `expected_document_404` allowance used 5 times (one per not-found probe case); 0 warnings |
| V3 | 0 of 25 cases overflow; max 0 px |
| V4 | observed external requests `[]` equal the frozen `[]`; 0 fetched; 400 local requests |
| V5 | 5/5 first-Tab skip-link checks |
| V6 | 22/22 axe scans with `html[data-mode]` matching the requested mode |
| V7 | 0 violations; baseline empty; 46 incomplete results on 122 nodes (rules `color-contrast`, `aria-valid-attr-value`, `aria-hidden-focus`, all on vendored chrome nodes), recorded as unknown |
| V8 | 0 broken of 200 internal references; 0 broken of 4 fragment references; 0 external references; 0 fetched |
| V9 | link-checker self-test reports exactly its 8 broken references and 2 broken fragments |
| V10 | 0 hits in each of 8 families over 25 text and 10 binary files; family 7: default run K = 862 identifiers, H = 614 of N = 626 files hashed (12 over 64 MiB not hashed); full run K = 871, 626 of 626 (`artifact_digests_complete: true`); family 8: 47 identifiers |
| V11 | 8/8 positives fire, 0/8 negatives fire; upper-case hex, base64 SRI and binary-embedded digests also caught |
| V12 | gitleaks 8.30.1 exit 0 with 0 findings on the build; positive control exit 1 with 1 finding (`generic-api-key`) |
| V13 | build leak scan 0 findings (24 rules); source scan 0 findings, harness files included (Node: 38 files) |
| V14 | frozen install, check (0 errors, 0 warnings), build: 3/3 exit 0 |
| V15 | `@playwright/test` 1.63.0 and `@axe-core/playwright` 4.13.0 exact; Skeleton 5.0.1 2/2 and sole lock version; `effect` and `wrangler` absent |
| V16 | 0 browser bytes; ladder step b, Chromium 153.0.8010.12 from the existing `chromium-1243` cache entry; cache entries identical before and after |
| V17 | every pre-existing class of the module passes (BuildTests now shares the once-per-process fresh build, as section 10.1 item 4 specifies) |
| V18 | DEPLOY.md gate commands present in order; operator-go actions named |
| V19 | 0 deploy actions |
| V20 | 2 defects found and fixed, below |
| V21 (I) | local server equivalence to Pages path resolution and headers: inferred, not proven |
| V22 (U) | Firefox, WebKit, real devices, screen readers, non-default themes, reduced motion: not performed |

### 14.2 Defects found and fixed (V20)

- **D1** (found by smoke check 4 on the not-found probe, 5/5 viewports):
  SvelteKit's default client `handleError` wrote the router's
  `Not found: /site-verify-not-found` error to `console.error` on every
  fallback visit. Fixed in `site/src/hooks.client.ts`: status 404 is not
  logged; every other client error still is.
- **D2** (found by smoke check 5 at w375 and w390 on all five routes): the
  vendored chrome's quick navigation could not shrink, pushing the theme and
  menu buttons past the viewport (document width 441 px; overflow 66 px at 375,
  51 px at 390). Fixed in `site/src/app.css` (`.site-chrome__quick` gets
  `min-width: 0`, `overflow-x: auto` and padding for the focus ring). No
  vendored file changed.

### 14.3 Deviations and observations

- An extra harness module `site/e2e/support.ts` (shared context, request
  blocking and hydration evidence) sits beside the section 4.2 files.
- Smoke records one supplementary hydration probe that is not a pass
  condition: the header's scroll listener (attached after hydration) set the
  compact class in 23 of 23 scrollable cases; 2 cases were not scrollable.
- The link checker also resolves the fallback document's references at a
  nested path, because Pages serves it at any depth.
- Wall time depends on host load: before the fixes, a run exceeded the 900 s
  cap (exit 124) while failing cases restarted the worker at a load average
  near 130 on 6 CPUs; after the fixes the suite took 691 s at that load and
  131 s at a load average near 30. The cap was not changed.
- pnpm refused `pnpm run build` after the script was added
  (`ERR_PNPM_VERIFY_DEPS_BEFORE_RUN`) until a second
  `pnpm install --frozen-lockfile`; the lockfile did not change. pnpm printed
  an engine warning naming node v24.19.0 while the scripts ran under the
  PATH node v22.23.2 (recorded by global setup); the warning's source is
  inferred to be pnpm's own runtime.
- Directly affected modules: `test_web_stack` passes; six
  `test_tool_contracts` tests that drive MCP tool calls fail with and without
  the FFmpeg variables. The lane changed no file they read; attribution to a
  pre-existing or load-related cause is inferred, and root's full suite decides.
