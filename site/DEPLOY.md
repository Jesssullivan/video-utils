# Public site: Cloudflare Pages plan (not applied)

Status: **plan only**. Nothing in this directory has been deployed. No Pages
project exists, no domain is attached, and no request has been made to a served
copy of this site. Creating the project, attaching a domain and deploying are
outward-facing actions that need a **separate operator go**. This lane did not
run Wrangler and Wrangler is not a dependency of this site.

No credential belongs in this repository: no API token, no account id, no
project secret, in any file, script, recipe or workflow.

## What gets published

`site/build/`, produced by `pnpm run build`: five HTML documents (the overview,
features, agent tools, status and the not-found fallback), one data file for
the agent tools page, hashed script and style assets, self-hosted fonts with
their licence text, a favicon and a `_headers` file. No source maps, no service
worker, no redirects file, no media and no raster images.

## Build inputs

| Input | Value |
| --- | --- |
| Root directory | `site` |
| Build command | `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 pnpm install --frozen-lockfile && pnpm run check && pnpm run build` |
| Output directory | `site/build` |
| Node | 22 (`engines.node` is `>=22.13 <23`) |
| Package manager | `pnpm@11.25.0` (the `packageManager` field) |
| Environment variables | none |
| Build-time secrets | none |

The agent tools page reads `program/tools.json` from the repository root while
prerendering, so a build needs the whole repository checked out, not only
`site/`. For that reason **direct upload of a locally built or CI-built
`site/build`** is the recommended path, in place of the Pages git integration.
The estate's other public site deploys the same way.

## Verification gates (in order)

Every gate must meet its condition to proceed before the next one runs. Nothing
below deploys anything, and no browser is downloaded at any step: the browser
suite uses the Chromium revision already in the local Playwright cache, else an
installed Google Chrome, else it skips with the typed code
`e2e_browser_unavailable` (a skip is not a pass and blocks the deploy).

Before the gates, choose an absolute output directory **outside `site/`** (for
example the repository's gitignored run-output directory) and export it:
`export SITE_VERIFY_OUT_DIR=<absolute directory outside site/>`. The Playwright
configuration refuses to run without it (`site_verify_out_dir_required`), so no
report, trace or screenshot is ever written inside `site/`.

| # | Where | Command | Condition to proceed |
| --- | --- | --- | --- |
| 1 | `site/` | `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 pnpm install --frozen-lockfile` | exit 0; the lockfile is unchanged; no browser fetched |
| 2 | `site/` | `pnpm run check` | exit 0 with 0 errors and 0 warnings |
| 3 | `site/` | `pnpm run build` | exit 0; five HTML documents, no source maps |
| 4 | `site/` | `node scripts/leak-scan.mjs build` | exit 0, 0 findings over every rule |
| 5 | `site/` | `node scripts/leak-scan.mjs . --surface source` and `node scripts/leak-scan.mjs vendor --surface vendor` | exit 0, 0 findings each |
| 6 | repository root | `PYTHONPATH=tests python3 -m unittest test_public_site_s3.SiteVerifyBuildTests -v` | 0 failures: 0 broken internal references and fragments (external links listed, never fetched), 0 privacy hits in each of the eight families, existing leak scans clean |
| 7 | repository root | `PYTHONPATH=tests python3 -m unittest test_public_site_s3.GitleaksBuildTests -v` | 0 failures: gitleaks exits 0 with 0 findings on the build and its positive control exits 1 |
| 8 | `site/` | `SITE_VERIFY_OUT_DIR="$SITE_VERIFY_OUT_DIR/playwright" pnpm run verify:browser` | exit 0; `browser-summary.json` in that directory shows V1 to V7 passing (every route at five viewport configurations, 0 console and page errors beyond the declared fallback 404 report, 0 horizontal overflow, 0 external requests, axe 0 violations in light and dark) |
| 9 | repository root | `SITE_VERIFY_BROWSER=1 PYTHONPATH=tests python3 -m unittest test_public_site_s3 -v` | 0 failures; it rebuilds once and re-runs every gate above on the build it produced |
| 10 | `site/` | the deploy below, only after the operator go | see the next section |

Gates 6 and 7 rebuild the site themselves (a stale build is never trusted).
The privacy scan hashes private run outputs of at most 64 MiB by default; set
`SITE_VERIFY_FULL_DIGESTS=1` on gate 6 to hash every file (600 s limit). The
same gitleaks check can be run directly from the repository root:

```
gitleaks dir site/build --config .gitleaks.toml --no-banner --redact --log-level warn \
  --report-format json --report-path "$SITE_VERIFY_OUT_DIR/gitleaks-build.json" --exit-code 1
```

The browser and accessibility results are automated checks on a local static
server that emulates Pages path resolution; they are not a WCAG conformance
claim, not a screen-reader or real-device check, and say nothing about the
served copy.

## Deploy command (for the operator, after the go)

These actions need the operator's go, each one explicitly: choosing the
Cloudflare account, creating the Pages project, choosing and pinning a Wrangler
version, the first `wrangler pages deploy`, every later `wrangler pages deploy`,
attaching a custom domain, and deciding whether preview deployments are public.
None of them has been performed.

With a pinned Wrangler chosen by the operator and credentials supplied only
through the operator's own environment, run from `site/` on the build that gate
9 produced:

```
wrangler pages deploy build --project-name <PROJECT_NAME> --branch <PRODUCTION_BRANCH>
```

The first deploy of a new project also needs
`wrangler pages project create <PROJECT_NAME> --production-branch <PRODUCTION_BRANCH>`,
which is itself an outward-facing action under the same go.

Root holds the proposed `just` recipe text, including a deploy recipe that
refuses to run unless an explicit operator-go variable is set and the browser
and privacy receipts are green. That text lives in the lane root-requests
receipts and is not applied by this lane.

## Decisions the operator has to make

| Decision | Current value |
| --- | --- |
| Pages project name | not chosen |
| Cloudflare account | not chosen, never recorded here |
| Production branch | not chosen |
| Public hostname | not chosen |
| Custom domain | not chosen |
| Whether preview deployments are public | not decided |
| Wrangler version to pin | not pinned |
| Public product name | not chosen (`video-utils` is a working title) |
| Whether the committed carriers under `site/vendor/` stay or are replaced by a package link | root's call |

## Response headers

`static/_headers` sets `X-Content-Type-Options: nosniff`,
`Referrer-Policy: no-referrer`, `X-Frame-Options: DENY` and a deny-all
`Permissions-Policy` for every path. A Content-Security-Policy is **not** set:
the pre-paint theme script and the framework bootstrap are inline, so a policy
needs hashes or a nonce and has not been designed. Treat `csp_enforced` as
false until that work is done and verified on a served copy.

## After a deploy (not performed)

These checks have not been run because nothing is served (the browser suite
above ran only against the local emulation):

- the five documents answer 200 (or 404 for the fallback) with the headers above;
- no request leaves the site's own origin;
- the theme control works from the keyboard and its choice survives a reload;
- contrast ratios in each theme and colour mode.

## Privacy boundary

The site carries no audio, video, still image, spectrogram or metric derived
from a real recording, no recording file name, no content digest, no run
identifier and no private host name. The leak scan and the lane tests enforce
this on every build. The private review application is a separate system; this
site neither links to it nor names where it runs.
