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
| Build command | `pnpm install --frozen-lockfile && pnpm run check && pnpm run build` |
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

## Gate order

Every step must exit zero before the next one runs. The deploy is last and is
the only step that needs the operator go.

1. `pnpm install --frozen-lockfile` (from `site/`)
2. `pnpm run check` (zero errors and zero warnings)
3. `pnpm run build`
4. `node scripts/leak-scan.mjs build` (build surface, every rule)
5. `node scripts/leak-scan.mjs . --surface source` and
   `node scripts/leak-scan.mjs vendor --surface vendor`
6. `PYTHONPATH=tests python3 -m unittest test_public_site_s3 -v` (from the
   repository root; it rebuilds and re-checks the build it just produced)
7. Operator go, then the deploy below

## Deploy command (for the operator, after the go)

With a pinned Wrangler chosen by the operator and credentials supplied only
through the operator's own environment:

```
wrangler pages deploy build --project-name <PROJECT_NAME> --branch <PRODUCTION_BRANCH>
```

run from `site/`. The first deploy of a new project also needs
`wrangler pages project create <PROJECT_NAME> --production-branch <PRODUCTION_BRANCH>`,
which is itself an outward-facing action under the same go.

Root holds the proposed `just` recipe text, including a deploy recipe that
refuses to run unless an explicit operator-go variable is set. That text lives
in the lane's root-requests receipt and is not applied by this lane.

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

These checks have not been run because nothing is served:

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
